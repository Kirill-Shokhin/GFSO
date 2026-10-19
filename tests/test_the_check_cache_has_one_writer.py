"""The cached L0 checks have one writer, and a re-admission does not re-check a settled child (D-7; §11.5).

The RunChecks effect kept its own copy of the recompute and read EVERY child: after a challenge's re-install
(ACCEPT_CHALLENGE, no new spec) an abandoned child was back in CHECK-1b and gated the plan. And a child whose verdict is
settled, left mapped to nothing by a criterion's removal, was flagged where the only lift was a false mapping.

CONTROL: give the effect its old `graph.get_children` copy, or drop the DONE exemption from CHECK-1b, and these go red.
"""
from gfso.core.handlers.structural import check_non_redundancy
from gfso.core.types import AgentId, Criteria, CriterionMapping, Signal, SignalData, Spec, State, TaskId
from tests.support import REGISTER_SPLIT, make_engine, pinned


def _send(e, sig, tid, src, **kw):
    e.send_signal(SignalData(signal=sig, task_id=TaskId(tid), source=AgentId(src), **kw))
    e.wait_idle()


def _split(e):
    """A split admitted whole (§11.5); then the criterion `dropped` covered is revised away — an orphan, the flag a
    revision after admission leaves (§12.10), never a refused admission."""
    g, h = (Criteria(n, n, check=pinned(n)) for n in "gh")
    e.assign_task(TaskId("r"), Spec("goal", (g, h)), AgentId("lead"))
    e.wait_idle()
    _send(e, Signal.ACCEPT, "r", "lead")
    e.decompose_task(TaskId("r"), [
        (TaskId("kept"), Spec("kept", (Criteria("k", "k", check=pinned("k")),)), AgentId("w")),
        (TaskId("dropped"), Spec("dropped", (Criteria("d", "d", check=pinned("d")),)), AgentId("w"))],
        criterion_mappings=[CriterionMapping("g", TaskId("kept")), CriterionMapping("h", TaskId("dropped"))],
        register=REGISTER_SPLIT)
    e.wait_idle()
    e.edit_criteria(TaskId("r"), (g,), AgentId("lead"))
    _send(e, Signal.ACCEPT, "r", "lead")


def _check(e, name):
    return next(c for c in e.get_checks(TaskId("r")) if c.check_name.startswith(name))


def test_an_abandoned_child_stays_out_of_the_cache_after_a_challenges_reinstall():
    e = make_engine()
    e.start()
    _split(e)
    assert not _check(e, "CHECK-1b").passed, "the unmapped child is an orphan while it is active"
    _send(e, Signal.CANCEL, "dropped", "lead", reason="not needed")
    _send(e, Signal.CONFIRM_CANCEL, "dropped", "w")
    assert e.graph.get_state(TaskId("dropped")) == State.ABANDONED
    assert _check(e, "CHECK-1b").passed
    _send(e, Signal.CHALLENGE, "r", "lead", reason="unclear")
    e.send_signal(SignalData(signal=Signal.ACCEPT_CHALLENGE, task_id=TaskId("r"),
                             source=e.graph.issuer_of(TaskId("r"))))
    e.wait_idle()
    assert e.graph.get_state(TaskId("r")) == State.OFFERED, "the challenge's re-install went through"
    assert "dropped" not in (_check(e, "CHECK-1b").details or ""), _check(e, "CHECK-1b")
    e.stop()


def test_a_settled_child_is_not_rechecked_for_its_mapping():
    e = make_engine()
    e.start()
    _split(e)
    r, kept = e.graph.get_task(TaskId("r")), e.graph.get_task(TaskId("kept"))
    kept.state = State.DONE
    r.criterion_mappings = (CriterionMapping("g", TaskId("dropped")),)
    assert check_non_redundancy(r, [kept, e.graph.get_task(TaskId("dropped"))]).passed
    kept.state = State.EXECUTING
    assert not check_non_redundancy(r, [kept, e.graph.get_task(TaskId("dropped"))]).passed
    e.stop()
