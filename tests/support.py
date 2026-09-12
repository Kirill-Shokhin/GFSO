"""The suite's construction kit — one owner for the objects the tests keep building by hand.

Fifty-four test bodies built an `Engine` themselves, in five drifting spellings of the same three
decisions (which storage, whether signals are validated, how often the monitor wakes). That is the
off-diagonal element the FORM ratchet counts as `T1_engine_built_by_hand`: a constructor argument
that gains a meaning — as `state_timeout` and `runner` both did — has to be found in fifty-four
places, and the ones that are only *nearly* the same are exactly where a test stops testing what its
name says. The same happened to the Spec builder: `_spec` existed six times with four signatures.

The defaults here are the ENGINE's own defaults, deliberately: this module owns the *spelling* of
construction, not the policy of any test. A test that wants a non-default engine still says so, and
now says so in one vocabulary.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.storage.memory import MemoryStorage
from gfso.core.types.ports import ClockPort, RunnerPort, StoragePort
from gfso import tools as T
from gfso.core.types import AcceptedRiskItem, Criteria, Predictability, Spec
from gfso.engine import Engine

#: What a decomposition declares it knowingly does not cover. Every graph the engine admits needs a
#: non-empty register (STD-1 / CHECK-4), so the suite carries one rather than inventing it per file.
UNMODELLED_FAULT = AcceptedRiskItem("an unmodelled environment fault", Predictability.EXTRAORDINARY)


def make_engine(
    storage: Optional[StoragePort] = None,
    *,
    agents=None,
    llm=None,
    check_interval: float = 10.0,
    validate_signals: bool = True,
    critique_log_path: Optional[str] = None,
    state_timeout: Optional[float] = None,
    clock: Optional[ClockPort] = None,
    runner: Optional[RunnerPort] = None,
) -> Engine:
    """An engine over in-memory storage and a human agent port, unless told otherwise.

    `storage=None` means MemoryStorage and `agents=None` means HumanAgent: each is what a test
    overrides when the test is ABOUT that port — persistence, or an agent that answers by itself —
    and passing them everywhere else only hid which tests those were.
    """
    return Engine(
        storage if storage is not None else MemoryStorage(),
        agents if agents is not None else HumanAgent(),
        llm=llm,
        check_interval=check_interval,
        validate_signals=validate_signals,
        critique_log_path=critique_log_path,
        state_timeout=state_timeout,
        clock=clock,
        runner=runner,
    )


def spec(description: str = "goal", *criteria: str, risks: bool = True) -> Spec:
    """A contract with one decidable criterion per name given, and the standard risk register.

    `risks=False` builds the register-less spec the CHECK-4 tests need — the one shape that must
    stay expressible, since a missing register is a defect the suite has to be able to construct.
    """
    return Spec(
        description=description,
        criteria=tuple(Criteria(c, f"{c} description") for c in (criteria or ("c1",))),
        accepted_risks=(UNMODELLED_FAULT,) if risks else (),
    )


def reviewer_passes(engine, task_id, reviewer: str = "reviewer") -> None:
    """Record an honest reviewer PASS: one observation line per criterion the node actually has.

    Scaffolding, not a subject — a great many tests need a node past its seam before they can look
    at what they are really about (REOPEN, the FM-1 repair, the D6 gate). They used to reach for
    `record_reviewer_verdict(id, "PASS", [], "reviewer")`, whose empty observation set is precisely
    the evidence-free PASS the engine now refuses (§11.2: a conjunct nobody spoke to is ⊥, and ⊥
    does not carry a pass). Written once and reading the criteria off the node, so the scaffolding
    cannot drift away from a contract a test changes.
    """
    task = engine.get_task(task_id)
    engine.record_reviewer_verdict(
        task_id, "PASS", [], reviewer,
        observed={c.name: f"checked `{c.name}` by hand against the delivery: it holds"
                  for c in task.spec.criteria if not c.depends_on})


def instrument_passes(engine, task_id, validator: str = "validate_result", **kw) -> dict:
    """Record an instrument PASS that speaks to every criterion — the engine-level twin of
    `reviewer_passes`, for the many tests that need a node judged before they can look at what they
    are about. Written once and reading the contract off the node, so it cannot fall behind a test
    that changes the criteria."""
    task = engine.get_task(task_id)
    return engine.record_exec_verdict(
        task_id, "PASS", [], validator,
        per_criterion=[{"criterion": c.name, "verdict": "pass",
                        "evidence": f"ran the check for `{c.name}`: it holds"}
                       for c in task.spec.criteria], **kw)


def assert_the_graph_can_still_move(engine, root="root"):
    """No node may sit in a state nothing can move while the graph reports itself healthy.

    THE CLASS, not another instance of it. Two locks were found and fixed on 2026-09-07 — a child
    accepted by the clock whose parent's conjunction refused it forever, and a `criteria: []`
    contract nothing could judge — and the author's note on the first was that it had been reported
    and promised closed across about ten sessions. Instances get patched; what was missing every
    time is a rule that fails on the SHAPE, so the eleventh cannot arrive quietly.

    The shape is not "a node is stuck" — a graph waiting for a person is healthy and says so. It is
    the DISAGREEMENT: the run is unfinished, nothing anywhere has an admissible move, and the
    surface still answers `stuck: false` ("the graph is working — poll again in a minute"). That is
    what both locks looked like from outside, and it is decidable from two reads.
    """
    step = T.next_step(engine, root)
    if step.get("complete") or step.get("stuck"):
        return step
    states = {str(t.id): t.state.name for t in engine.all_tasks()}
    terminal = {"DONE", "ABANDONED", "ESCALATED"}

    # (1) SOMETHING must admit a move. The coarse half.
    movable = {str(t.id): acts for t in engine.all_tasks()
               if (acts := (T.available_actions(engine, str(t.id)) or {}).get("actions"))}
    assert movable, (
        "the graph is neither complete nor stuck, and NO node admits a move from any role — "
        f"the frontier says {step.get('directive', '')!r} over a graph that cannot advance. "
        f"States: {states}")

    # (2) …AND WHAT IT SAYS IT IS WAITING FOR MUST BE ABLE TO ARRIVE. The sharp half, and the one
    # that catches a lock: a node advertising a move it will be refused still counts as "movable"
    # above, so the coarse half stayed green through the very defect it was written for (measured
    # while writing it — eleven cases green with the lock deliberately restored). What no lock can
    # fake is the object of the wait. In the 2026-09-07 case the root waited on two children that
    # were already DONE, under `stuck: false` and the directive "finish those children".
    for wait in (step.get("waiting") or []):
        finished = [w for w in (wait.get("waits_on") or []) if states.get(str(w)) in terminal]
        assert not finished, (
            f"{wait.get('task_id')} is said to be waiting for {finished}, and they are already "
            f"{[states[str(w)] for w in finished]} — nothing further can arrive from them, so this "
            f"is a wait that cannot end. The graph reports `stuck: false` and says "
            f"{wait.get('opens_with', '')!r}. States: {states}")
    return step


def workdir(base, *parts) -> str:
    """A registrable working directory, created.

    The roster refuses a `workdir` that is not an existing directory — a role registered against a
    place that is not there is spawned into nothing, and a validator sent to one judges an empty
    tree. Tests that use directory NAMES as identity tokens ("theirs" vs "mine") still need those
    directories to exist, and this is the one line that says so.
    """
    p = Path(base).joinpath(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return str(p)
