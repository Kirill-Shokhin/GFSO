"""A node revised while its run sits in the dispatcher's queue must not be run twice.

`_round_key` builds a round from the node's whole GENERATION — (iteration, reopens, revisions) —
because a revision that moved no counter left a spent key and the node was never re-executed. The
staleness guard beside it, `_fresh`, compared `iteration` alone. So the two halves of one fact
disagreed: after a `revise`, the dedup key is new (the dispatcher spawns a second, correct run) and
the guard still calls the QUEUED run fresh (the first run proceeds too). Measured: two paid executor
runs on one node, the node left in VALIDATING carrying the SUPERSEDED delivery — to be judged
against criteria it was never given — while the run that did the right work had its DELIVER refused
by the FSM. `revise` and `reopen` both land the node in OFFERED, an executor state, so the state
check catches neither.

Control: compare `t.iteration != expect_gen[0]` in `_fresh` instead of the whole generation, and
both cases below go red.
"""
from dataclasses import replace

from gfso.core.types import AgentId, TaskId
from gfso.delegate import Dispatcher
from gfso import tools as T

from tests.support import instrument_passes
from tests.test_delegate import _agents, _eng, _node


def _revise(engine, tid, description):
    """Re-author the node's contract the way the issuer's own verb does."""
    t = engine.get_task(TaskId(tid))
    engine.revise(TaskId(tid), replace(t.spec, description=description),
                  AgentId(str(engine.issuer_of(TaskId(tid)) or "boss")))
    engine.wait_idle()


def test_a_run_queued_before_a_revision_is_stale(tmp_path):
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"))
    _node(e, "t1")
    ran = []
    d = Dispatcher(e, agents, runner=lambda en, tid, ex, ag: ran.append(str(tid)))

    queued_gen = e.get_task(TaskId("t1")).id and (
        e.get_task(TaskId("t1")).iteration,
        e.get_task(TaskId("t1")).reopens,
        e.get_task(TaskId("t1")).revisions)
    _revise(e, "t1", "hammer a DIFFERENT nail")

    d._run_guarded(TaskId("t1"), "exec-1", queued_gen)
    assert ran == [], ("the queued run worked a contract that no longer exists — and the dispatcher "
                       "has already spawned a second, correct one for the new round")
    e.stop()


def test_a_run_queued_before_a_reopen_is_stale(tmp_path):
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"))
    _node(e, "t1")
    ran = []
    d = Dispatcher(e, agents, runner=lambda en, tid, ex, ag: ran.append(str(tid)))
    queued_gen = (0, 0, 0)

    T.signal(e, "t1", "ACCEPT", "exec-1")
    T.signal(e, "t1", "DELIVER", "exec-1", result="out")
    instrument_passes(e, TaskId("t1"), "val-1")
    issuer = AgentId(str(e.issuer_of(TaskId("t1"))))
    T.signal(e, "t1", "PASS", str(issuer))
    e.wait_idle()
    e.reopen(TaskId("t1"), issuer)            # R' (§14.3) — an engine verb, not a P2P signal
    e.wait_idle()
    assert e.get_task(TaskId("t1")).reopens == 1

    d._run_guarded(TaskId("t1"), "exec-1", queued_gen)
    assert ran == [], "a run queued before the REOPEN is a run of the pre-reopen contract"
    e.stop()


def test_the_current_generation_still_runs(tmp_path):
    """The POSITIVE control: the guard must not refuse the round it was queued for."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"))
    _node(e, "t1")
    ran = []
    d = Dispatcher(e, agents, runner=lambda en, tid, ex, ag: ran.append(str(tid)))
    t = e.get_task(TaskId("t1"))
    d._run_guarded(TaskId("t1"), "exec-1", (t.iteration, t.reopens, t.revisions))
    assert ran == ["t1"]
    e.stop()
