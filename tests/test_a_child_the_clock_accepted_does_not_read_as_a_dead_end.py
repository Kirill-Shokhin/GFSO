"""The frontier's "this wait can never end" guard, at the three edges where it was wrong.

The guard exists because a delivered parent over an ESCALATED child polls for ever: the AND over
the children (Thm 1) can never be satisfied and nothing said so. It was installed asking
`not passed(k) and k.state in TERMINAL_STATES` over `get_children`, and that spelling is wrong in
three directions at once:

* **AUTO_PASS.** `passed` refuses the timeout close, which the canon counts AS acceptance
  (§12.2, §14.3, §24.7) and which the PASS gate itself accepts. So a child accepted by the clock was
  reported as "settled WITHOUT passing", and the run was told to FAIL the parent and re-decompose —
  over a graph whose very next PASS the engine accepts. A guard that mints a destructive instruction
  on a healthy graph is worse than the stall it replaced.
* **Tombstones.** `get_children` includes ABANDONED, which has LEFT the decomposition (§15.1 keeps
  it as provenance). One cancelled child turned a live `validate` step into "stuck, FAIL the parent"
  — while an independent verdict was mid-flight.
* **A finished root.** The same strict predicate decided whether a run is COMPLETE, so a root closed
  by the clock was answered `stuck: true`, "the block is structural", with `blocked_by: []` and no
  signal any party could send.

And the guard was asked in an order that let work in flight hide a stranded node — the in-flight
test is a property of Del (`state in (EXECUTING, REWORKING)` and the roster calls the assignee an
executor), not of anything running.

Controls, each breaking one thing: put `passed` back in `_never_passes` and the first two cases go
red; read `get_children` there and the tombstone case does; put `passed` back in
`_frontier_terminal` and the finished-root case does; ask `in_flight_nodes()` before
`stranded_nodes()` and the masking case does.
"""
import pytest

from gfso import tools as T
from gfso.core.types import DoneReason, State, TaskId
from gfso.engine import Engine
from tests.support import make_engine


@pytest.fixture
def engine():
    e = make_engine()
    e.start()
    try:
        yield e
    finally:
        e.stop()


def _graph(engine, kids=("k1",)):
    """root with `kids` beneath it, each covering one of root's criteria."""
    risks = [{"item": "an unmodelled environment fault", "predictability": "EXTRAORDINARY"}]
    T.create_task(engine, "root", {"description": "root",
                                   "criteria": [{"name": f"c{i}", "description": f"c{i} d"}
                                                for i, _ in enumerate(kids)],
                                   "accepted_risks": risks}, assignee="boss")
    for i, k in enumerate(kids):
        T.create_task(engine, k, {"description": k,
                                  "criteria": [{"name": "x", "description": "x d"}]},
                      assignee="worker", parent_id="root")
        T.map_criterion(engine, "root", k, f"c{i}")
    engine.wait_idle()


def _close(engine, node_id, reason):
    """Put a node into DONE with the given reason, the way its own settlement would."""
    t = engine._graph.get_task(TaskId(node_id))
    t.state, t.done_reason = State.DONE, reason
    engine._graph.save_task(t)


def test_a_child_accepted_by_the_clock_is_not_a_dead_end(engine: Engine):
    _graph(engine)
    _close(engine, "k1", DoneReason.AUTO_PASS)
    engine.wait_idle()

    assert engine._never_passes(TaskId("root")) == [], \
        "a child the clock accepted still satisfies its parent's AND (§12.2, §24.7)"
    answer = engine.next_step()
    assert not (answer.get("stuck") and "settled WITHOUT passing" in answer.get("directive", "")), \
        f"the guard fired over an accepted child: {answer.get('directive')}"


def test_an_escalated_child_is_still_a_dead_end(engine: Engine):
    """The POSITIVE control: the case the guard exists for must still fire."""
    _graph(engine)
    t = engine._graph.get_task(TaskId("k1"))
    t.state, t.done_reason = State.ESCALATED, DoneReason.FAIL
    engine._graph.save_task(t)
    engine.wait_idle()

    assert [str(k.id) for k in engine._never_passes(TaskId("root"))] == ["k1"]


def test_a_cancelled_child_left_the_decomposition_and_does_not_block_it(engine: Engine):
    _graph(engine, kids=("k1", "k2"))
    for node in ("k1", "k2"):
        _close(engine, node, DoneReason.PASS)
    t = engine._graph.get_task(TaskId("k2"))
    t.state, t.done_reason = State.ABANDONED, None
    engine._graph.save_task(t)
    engine.wait_idle()

    assert engine._never_passes(TaskId("root")) == [], \
        "an ABANDONED tombstone is provenance (§15.1), not an unsatisfied conjunct"


def test_a_root_closed_by_the_clock_is_complete_and_says_how(engine: Engine):
    risks = [{"item": "an unmodelled environment fault", "predictability": "EXTRAORDINARY"}]
    T.create_task(engine, "root", {"description": "root",
                                   "criteria": [{"name": "c", "description": "c d"}],
                                   "accepted_risks": risks}, assignee="boss")
    engine.wait_idle()
    _close(engine, "root", DoneReason.AUTO_PASS)
    engine.wait_idle()

    answer = engine.next_step(TaskId("root"))
    assert answer.get("complete") is True, answer.get("directive")
    assert not answer.get("stuck")
    # …and it does not pass the close off as an earned one.
    assert "root" in (answer.get("auto_accepted") or []) or answer.get("closed_by") or \
        "auto" in repr(answer).lower(), f"the closure's provenance is not reported: {answer}"


def test_work_in_flight_does_not_hide_a_stranded_node(engine: Engine):
    """A stranded node is a fact no running work can change, so it must not be masked by one.

    The shape that produced it live: root -> mid -> {g1 PASS, g2 ESCALATED}, with root and mid in
    EXECUTING and the roster calling their assignee an executor. `mid` can never close, the frontier
    offers no step, and the in-flight branch — whose test is `state in (EXECUTING, REWORKING)` plus
    a roster kind, i.e. a property of Del — answered `stuck: false`, "poll again in a minute".
    """
    risks = [{"item": "an unmodelled environment fault", "predictability": "EXTRAORDINARY"}]
    T.create_task(engine, "root", {"description": "root",
                                   "criteria": [{"name": "c", "description": "c d"}],
                                   "accepted_risks": risks}, assignee="boss")
    T.create_task(engine, "mid", {"description": "mid",
                                  "criteria": [{"name": "m0", "description": "m0 d"},
                                               {"name": "m1", "description": "m1 d"}],
                                  "accepted_risks": risks}, assignee="worker", parent_id="root")
    T.map_criterion(engine, "root", "mid", "c")
    for i, g in enumerate(("g1", "g2")):
        T.create_task(engine, g, {"description": g,
                                  "criteria": [{"name": "x", "description": "x d"}]},
                      assignee="worker", parent_id="mid")
        T.map_criterion(engine, "mid", g, f"m{i}")
    engine.wait_idle()

    _close(engine, "g1", DoneReason.PASS)
    g2 = engine._graph.get_task(TaskId("g2"))
    g2.state, g2.done_reason = State.ESCALATED, DoneReason.FAIL
    engine._graph.save_task(g2)
    for node in ("root", "mid"):
        t = engine._graph.get_task(TaskId(node))
        t.state = State.EXECUTING
        engine._graph.save_task(t)
    engine._roster = {"worker": "llm-executor", "boss": "llm-executor"}
    engine.wait_idle()

    answer = engine.next_steps()
    assert not answer.get("steps"), f"a step exists, so this is not the masking case: {answer}"
    assert answer.get("stuck") is True, answer.get("directive")
    assert "g2" in (answer.get("blocked_by") or []), answer


def test_a_tombstone_does_not_pre_empt_work_in_flight(engine: Engine):
    """Cancellation is an ORDINARY event and must not turn every later poll into "stuck".

    `stranded_nodes()` names ABANDONED nodes too, and asking it before the in-flight branch made a
    single tombstone — a child refused after the goal was revised, which `engine/loop.py`'s own
    comment records happening four at a time — answer `stuck: true` for the rest of the run, with
    the destructive advice to re-decompose around a node somebody had deliberately cancelled, while
    an independent verdict was mid-flight.

    The shape is the live one: one child delivered with a judge already claimed on it (so it offers
    no step and IS in flight), one child passed, one cancelled.

    CONTROL: let the pre-emption test read `stranded` instead of `_blocking` and this goes red.
    """
    _graph(engine, kids=("k1", "k2", "k3"))
    T.signal(engine, "root", "ACCEPT", "boss")          # root is at work, so it offers no step
    T.signal(engine, "k1", "ACCEPT", "worker")
    T.signal(engine, "k1", "DELIVER", "worker", result="out")
    engine.wait_idle()
    assert engine._graph.get_task(TaskId("k1")).state is State.VALIDATING
    claim = engine.begin_validation(TaskId("k1"))       # a judge is running on this delivery
    assert claim is not None
    _close(engine, "k2", DoneReason.PASS)
    k3 = engine._graph.get_task(TaskId("k3"))
    k3.state, k3.done_reason = State.ABANDONED, None    # cancelled, and covering nothing now
    engine._graph.save_task(k3)
    engine.wait_idle()

    answer = engine.next_steps()
    assert not answer.get("steps"), f"a step exists, so the pre-emption question does not arise: {answer}"
    assert not answer.get("stuck"),         f"a tombstone was read as a node the graph cannot move past: {answer.get('directive')}"
    assert answer.get("in_flight"), f"the judge that IS running was not reported: {answer}"

    # …AND WHEN NOTHING IS IN FLIGHT EITHER, the tombstone still must not be the answer. The first
    # repair put the reading only on the pre-emption test, so `blocked_by` and the directive beside
    # it went on naming the cancelled node and prescribing a re-decomposition around it.
    engine.end_validation(claim)
    quiet = engine.next_steps()
    assert "k3" not in (quiet.get("blocked_by") or []),         f"a tombstone was named as what the graph is blocked by: {quiet}"
    assert "ABANDONED" not in (quiet.get("directive") or ""), quiet.get("directive")
