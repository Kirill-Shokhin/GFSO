"""DoD 2.4 — the conformance bridge: the code is mechanically tied to the CHECKED model.

Two legs:
1. TABLE EQUIVALENCE (exhaustive): parse formal/tla/FsmTable.tla AT TEST TIME and compare
   the model's Step against the real core `transition()` over the complete
   (state × signal × guard) space. Either side drifting = red test — the TLA+ image can
   never silently diverge from fsm.py.
2. TRACE REPLAY (refinement): seeded random signal walks driven through the LIVE engine
   (the process_signal path, effects applied); the engine's state trajectory must equal
   the model's step-by-step — including rejections and terminal absorption.
"""
import random
import re
from pathlib import Path

from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.core.protocol.fsm import transition
from gfso.core.types import State, Signal, SignalData, GuardContext, TaskId, AgentId
from gfso import tools as T
from gfso.tools import _spec_from

TLA_TABLE = Path(__file__).resolve().parent.parent / "formal" / "tla" / "FsmTable.tla"

SPEC_DICT = {"description": "x", "criteria": [{"name": "a", "description": "A"}]}


# ── the model, parsed from its own source ────────────────────────────────────

def _parse_model():
    text = TLA_TABLE.read_text(encoding="utf-8")

    def parse_set(name):
        m = re.search(rf'{name} ==\s*\{{(.*?)\}}', text, re.S)
        assert m, f"set {name} not found in FsmTable.tla"
        return set(re.findall(r'"(\w+)"', m.group(1)))

    terminal = parse_set("Terminal")
    reassignable = parse_set("Reassignable")
    quasi = parse_set("QuasiTerminal")

    # Simple rows: s = "X" /\ sig = "Y" -> "Z" (the FAIL row's arrow goes to IF — excluded here)
    rows = {(s, sig): ns for s, sig, ns in
            re.findall(r's = "(\w+)"\s+/\\ sig = "(\w+)"\s+-> "(\w+)"', text)}

    fail = re.search(r'sig = "FAIL"\s*->\s*IF it < MaxIterations\s*'
                     r'THEN "(\w+)" ELSE "(\w+)"', text, re.S)
    cancel = re.search(r'\\notin Terminal.*?sig = "CANCEL"\s*-> "(\w+)"', text, re.S)
    reassign = re.search(r'\\in Reassignable\s+/\\ sig = "ASSIGN"\s*-> "(\w+)"', text, re.S)
    # R' REOPEN (§14.3): QuasiTerminal + ASSIGN under ~consumed /\ ro < MaxReopens
    reopen = re.search(r'\\in QuasiTerminal\s+/\\ sig = "ASSIGN"\s*'
                       r'/\\ ~consumed\s*/\\ ro < MaxReopens\s*-> "(\w+)"', text, re.S)
    assert fail and cancel and reassign and reopen, "special rows not found in FsmTable.tla"

    def step(s, sig, it, max_it, ro=0, max_ro=1, consumed=True):
        if (s, sig) in rows:
            return rows[(s, sig)]
        if s == "VALIDATING" and sig == "FAIL":
            return fail.group(1) if it < max_it else fail.group(2)
        if sig == "CANCEL" and s not in terminal and s != "CANCELLING":
            return cancel.group(1)
        if sig == "ASSIGN" and s in reassignable:
            return reassign.group(1)
        if sig == "ASSIGN" and s in quasi and not consumed and ro < max_ro:
            return reopen.group(1)
        return "REJECT"

    return step, terminal


MODEL_STEP, MODEL_TERMINAL = _parse_model()


def _code_step(state: State, sig: Signal, it: int, max_it: int,
               ro: int = 0, max_ro: int = 1, consumed: bool = True) -> str:
    # ASSIGN carries a spec: both live branches (CREATE on IDLE, revision on reassignable)
    # require one; the model's ASSIGN rows are exactly those two. (The R' reopen branch also
    # accepts spec=None — reopen under the standing contract — covered by the replay walk.)
    sd = SignalData(signal=sig, task_id=TaskId("t"),
                    spec=_spec_from(SPEC_DICT) if sig == Signal.ASSIGN else None)
    res = transition(state, sd, GuardContext(iteration=it, max_iterations=max_it,
                                             reopens=ro, max_reopens=max_ro, consumed=consumed))
    return "REJECT" if res is None else res[0].name


def test_table_equivalence_exhaustive():
    """Every (state × signal × guard-side) agrees between fsm.py and FsmTable.tla —
    both sides of the iteration guard AND all four sides of the R' double gate."""
    checked = 0
    for state in State:
        for sig in Signal:
            for it in (0, 3):  # both sides of the iteration guard (max_iterations=3)
                for ro in (0, 1):  # both sides of the reopen counter (max_reopens=1)
                    for consumed in (False, True):  # both sides of the finality-gate
                        expect = MODEL_STEP(state.name, sig.name, it, 3, ro, 1, consumed)
                        got = _code_step(state, sig, it, 3, ro, 1, consumed)
                        assert got == expect, (
                            f"DRIFT at ({state.name}, {sig.name}, iter={it}, "
                            f"ro={ro}, consumed={consumed}): model={expect} code={got}")
                        checked += 1
    assert checked == len(State) * len(Signal) * 2 * 4


def test_model_terminals_match_code():
    from gfso.core.types import TERMINAL_STATES
    assert MODEL_TERMINAL == {s.name for s in TERMINAL_STATES}


# ── trace replay through the live engine ────────────────────────────────────

def _walk(e: Engine, tid: str, seed: int, steps: int = 200):
    T.create_task(e, tid, SPEC_DICT, "w")
    e.wait_idle()
    assert e.get_state(TaskId(tid)).name == "OFFERED"

    # The walk's single node has no parent and no Dep consumers ⟹ the graph's finality-gate
    # computes consumed=False on its quasi-terminals — the model mirrors that; reopens live
    # (max_reopens defaults to 1), so the walk exercises the R' edge AND its exhaustion.
    model_state, model_iter, model_ro = "OFFERED", 0, 0
    rng = random.Random(seed)
    alphabet = list(Signal)
    absorbed = 0
    for step in range(steps):
        sig = rng.choice(alphabet)
        e.send_signal(SignalData(
            signal=sig, task_id=TaskId(tid), source=AgentId("w"),
            spec=_spec_from(SPEC_DICT) if sig == Signal.ASSIGN else None))
        e.wait_idle()

        ns = MODEL_STEP(model_state, sig.name, model_iter, 3, model_ro, 1, False)
        if ns != "REJECT":
            if model_state == "VALIDATING" and sig.name == "FAIL" and model_iter < 3:
                model_iter += 1
            if model_state in ("DONE", "ABANDONED") and sig.name == "ASSIGN":
                model_ro += 1  # the REOPEN mutation spends the counter
            model_state = ns

        got = e.get_state(TaskId(tid)).name
        assert got == model_state, f"seed {seed} step {step} ({sig.name}): " \
                                   f"model={model_state} engine={got}"
        if model_state in MODEL_TERMINAL and model_ro >= 1:
            absorbed += 1
            if absorbed >= 10:  # verified final absorption under fire (reopen spent); walk done
                break


def test_trace_replay_through_live_engine():
    """Refinement: the LIVE engine (queue → process_signal → effects) follows the checked
    model step-for-step on random walks. Signal validation off = the FSM-core is the
    object (role/issuer checks are a stricter outer filter, not table semantics);
    monitor idle (huge interval) so trajectories are deterministic."""
    e = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=False,
               check_interval=10_000)
    e.start()
    try:
        for i, seed in enumerate((11, 22, 33, 44, 55)):
            _walk(e, f"n{i}", seed)
    finally:
        e.stop()
