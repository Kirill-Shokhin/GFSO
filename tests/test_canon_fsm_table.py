"""The engine's transition table against the CANON's own table, parsed from §14.3 at test time.

Why this exists. The FSM table lives in six encodings — the canon (§14.3), `gfso/core/protocol/
fsm.py`, `formal/tla/FsmTable.tla`, `formal/GFSO/Fsm.lean`, `docs/architecture.md` and the
agent-facing `gfso/mcp/ORCHESTRATOR.md` — and until now only two of them were checked against each
other mechanically (`test_model_conformance.py`: code ↔ TLA). Both could agree and both be wrong
about the canon; that is exactly what corners #3 (`VALIDATING+FAIL@max → DONE(fail)`, an edge the
canon denies) and #4 (`REWORKING+BLOCK`, an edge the canon's diagram omitted) were, and both were
found by a human reading prose. v4.0 writes the admissible sets out per state as a markdown table,
so the reading can be mechanical from here on.

Two directions, and the second is the load-bearing one:
  * every canon edge is implemented (a missing edge = a channel the protocol promises and the
    engine refuses);
  * every engine edge is in the canon (an EXTRA edge is the corner-#3 class: the engine inventing a
    transition the canon does not carry).

Out of scope, deliberately: the R′ REOPEN edge out of DONE/ABANDONED. §14.3 states it as a named
extension over the base machine, gated on a GRAPH predicate (consumption) rather than on state, so
it is not a row of this table; it is covered by `tests/test_reopen.py` and the TLA+ model.
"""
import re
from pathlib import Path

import pytest

from gfso.core.protocol.fsm import transition
from gfso.core.types import (Criteria, GuardContext, Signal, SignalData, Spec, State,
                             TaskId)

CANON = Path(__file__).resolve().parents[1] / "docs/applied_gfso_v4_en.md"
ROW = re.compile(r"^\|\s*([A-Z][A-Z ／/]*[A-Z])\s*\|\s*(.+?)\s*\|\s*$")
#: the canon writes the system trigger in lowercase (`timeout`) to keep it apart from the SIGNAL
#: `TIMEOUT` it shares a name with; both denote the same Signal member here.
TRIGGER = "timeout"


def _canon_rows() -> dict[State, dict[Signal, set[State]]]:
    """§14.3's per-state admissible sets: {state: {signal: {possible targets}}}."""
    lines = CANON.read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("| State | Admissible signals"))
    out: dict[State, dict[Signal, set[State]]] = {}
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        m = ROW.match(line)
        if not m:
            continue
        states, body = m.group(1), m.group(2)
        if "—" in body or "terminal" in body:          # the terminals row: no base-machine edges
            for s in re.split(r"\s*/\s*", states):
                out[State[s.strip()]] = {}
            continue
        edges: dict[Signal, set[State]] = {}
        for part in body.split("·"):
            part = re.sub(r"\*\*|`", "", part).strip()
            sig, _, targets = part.partition("→")
            if not targets:
                continue
            sig = sig.strip()
            name = "TIMEOUT" if sig == TRIGGER else sig
            tset = set()
            for t in re.split(r"∨", targets):
                t = re.sub(r"\(.*?\)", "", t).strip()   # drop the guard gloss: "(retries left)"
                if t:
                    tset.add(State[t])
            edges[Signal[name]] = tset
        out[State[states.strip()]] = edges
    return out


CANON_ROWS = _canon_rows()


def _engine(state: State, signal: Signal, *, iteration=0, max_iterations=3, consumed=True):
    # ASSIGN carries a packet by Inv-1: a revision IS the new contract, and the engine refuses a
    # packet-less one. Supplying it here is what makes the re-ASSIGN row testable at all.
    spec = Spec("re-issued", (Criteria("c", "d"),), name="n") if signal is Signal.ASSIGN else None
    r = transition(state, SignalData(signal=signal, task_id=TaskId("t"), spec=spec),
                   GuardContext(iteration=iteration, max_iterations=max_iterations,
                                reopens=0, max_reopens=1, consumed=consumed))
    return r[0] if r else None


def test_the_canon_table_parsed():
    """A parser that silently reads nothing would make every assertion below vacuous."""
    assert len(CANON_ROWS) == len(State), f"parsed {len(CANON_ROWS)} of {len(State)} states"
    assert CANON_ROWS[State.IDLE] == {Signal.ASSIGN: {State.OFFERED},
                                      Signal.CANCEL: {State.CANCELLING}}
    assert CANON_ROWS[State.VALIDATING][Signal.FAIL] == {State.REWORKING, State.ESCALATED}


@pytest.mark.parametrize("state", list(State))
def test_every_canon_edge_is_implemented(state):
    for signal, targets in CANON_ROWS[state].items():
        got = {_engine(state, signal),
               _engine(state, signal, iteration=9, max_iterations=3)}  # both sides of the guard
        got.discard(None)
        assert got & targets, (f"canon §14.3 admits {state.name} --{signal.name}--> "
                               f"{{{', '.join(t.name for t in targets)}}}; the engine gives "
                               f"{{{', '.join(t.name for t in got) or 'nothing'}}}")


@pytest.mark.parametrize("state", list(State))
def test_the_engine_invents_no_edge_the_canon_denies(state):
    """The corner-#3 direction: an edge the canon does not carry is a category the engine made up."""
    for signal in Signal:
        for it in (0, 9):
            target = _engine(state, signal, iteration=it, max_iterations=3)
            if target is None:
                continue
            if state in (State.DONE, State.ABANDONED) and signal is Signal.ASSIGN:
                continue                        # R′ REOPEN — a named extension, not a base row
            admitted = CANON_ROWS[state].get(signal, set())
            assert target in admitted, (
                f"the engine takes {state.name} --{signal.name}--> {target.name}, which §14.3 does "
                f"not admit (it admits {{{', '.join(t.name for t in admitted) or 'nothing'}}})")


def test_the_terminals_stay_terminal():
    for state in (State.DONE, State.ABANDONED, State.ESCALATED):
        assert CANON_ROWS[state] == {}
        for signal in Signal:
            if state in (State.DONE, State.ABANDONED) and signal is Signal.ASSIGN:
                continue                        # R′ again
            assert _engine(state, signal) is None


# ── the guard's own negative controls ────────────────────────────────────────────────────────────
# A guard is not working until it has gone RED on a planted defect of each class it claims to catch.
# These plant the two classes in-process (the parsed canon on one side, the engine on the other) and
# assert the checks above fail — so a refactor that quietly defuses them fails here first.

def test_control_a_missing_engine_edge_is_caught(monkeypatch):
    monkeypatch.setitem(CANON_ROWS, State.BLOCKED,
                        {**CANON_ROWS[State.BLOCKED], Signal.DELIVER: {State.VALIDATING}})
    with pytest.raises(AssertionError, match="the engine gives"):
        test_every_canon_edge_is_implemented(State.BLOCKED)


def test_control_b_an_invented_engine_edge_is_caught(monkeypatch):
    import tests.test_canon_fsm_table as mod   # itself, by name — never the import block
    monkeypatch.setattr(mod, "_engine",
                        lambda state, signal, **kw: State.DONE
                        if (state is State.BLOCKED and signal is Signal.PASS) else None)
    with pytest.raises(AssertionError, match="does not admit"):
        test_the_engine_invents_no_edge_the_canon_denies(State.BLOCKED)


def test_control_c_a_silent_parser_is_caught(monkeypatch):
    """The vacuity control: if §14.3 is reformatted and the parser reads nothing, everything above
    passes trivially. That is the failure mode this project has hit repeatedly (a falsely green
    guard), so the parse itself is asserted."""
    import tests.test_canon_fsm_table as mod   # itself, by name — never the import block

    class _Empty:                     # a canon whose table header survives but whose rows do not
        def read_text(self, **kw):
            return "| State | Admissible signals (→ target) |\n|---|---|\n"

    monkeypatch.setattr(mod, "CANON", _Empty())
    assert _canon_rows() == {}, "a table with no rows must parse to nothing…"
    monkeypatch.setattr(mod, "CANON_ROWS", _canon_rows())
    with pytest.raises(AssertionError):        # …and the vacuity assertion must then fail
        test_the_canon_table_parsed()
