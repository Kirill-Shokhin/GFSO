"""A child that reached DONE on the timeout locked its whole ancestry, permanently and quietly.

The canon is not ambiguous about what auto_pass is. §12.2: "DONE is reached through acceptance
(PASS ∨ auto_pass), never through fail". §14.3 calls the VALIDATING→DONE edge auto-ACCEPTANCE, and
§24.7 explains whom it protects — an executor who would otherwise wait for an issuer forever. The
conjunction at the parent asks whether a child was accepted, not whether its pass was earned.

The code asked the second question. Probed 2026-09-07 end to end: the child is terminal, the
parent's PASS is refused with "not all children have PASSed", `reopen` is refused because the parent
already consumed the child, and `next_step` answers `stuck: false` while advising the very signal
the engine forbids. No exit existed from anywhere. This divergence has been reported and promised
closed across many sessions; what was missing each time was not the diagnosis but this file.

Accepting it is only half. An acceptance the parent stands on unremarked is the lock's mirror image:
a green nobody can weigh. So the closure predicate carries `auto_accepted`, and the completion says
which parts of the result nobody checked — the making-explicit answer to a weaker conjunct.
"""
from __future__ import annotations

import gfso.tools as T
from gfso.core.types import Signal, SignalData, TaskId
from tests.support import make_engine

_RISK = [{"item": "an unmodelled environment fault", "predictability": "EXTRAORDINARY"}]


def _graph():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "root", {"description": "a goal", "accepted_risks": _RISK,
                              "criteria": [{"name": "g", "description": "G holds"}]},
                  assignee="agent")
    T.create_task(e, "kid", {"description": "the work",
                             "criteria": [{"name": "k", "description": "K holds"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "g")
    return e


def _timed_out_child(e):
    """Put the child through the canon's own auto-acceptance edge — the signal the monitor sends."""
    T.signal(e, "kid", "ACCEPT", "agent")
    T.signal(e, "kid", "DELIVER", "agent", result="did the work")
    e.send_signal(SignalData(signal=Signal.TIMEOUT, task_id=TaskId("kid")))
    e.wait_idle()
    task = e.get_task("kid")
    assert task.state.name == "DONE" and task.done_reason.name == "AUTO_PASS", \
        f"the probe cannot see its subject: the child is {task.state.name}/{task.done_reason}"


def _parent_claims_the_aggregate(e):
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="the aggregate")
    T.record_verdict(e, "root", "PASS", reviewer="rev",
                     observed={"g": "read the child's artifact end to end; it holds"})
    return T.signal(e, "root", "PASS", "agent")


def test_the_parents_conjunction_accepts_a_child_the_clock_accepted():
    e = _graph()
    _timed_out_child(e)
    out = _parent_claims_the_aggregate(e)
    assert out.get("accepted") is True, \
        f"the parent is locked behind a terminal child with no way back: {out.get('error')}"
    assert e.get_task("root").state.name == "DONE"
    e.stop()


def test_the_completion_says_which_part_nobody_checked():
    e = _graph()
    _timed_out_child(e)
    _parent_claims_the_aggregate(e)
    assert e.auto_accepted_closures(TaskId("root")) == ["kid"], \
        "the scoped list must find it — a subtree is the parent edges, not a spelling of the ids"
    step = T.next_step(e, "root")
    assert step.get("complete") is True
    assert "kid" in (step.get("auto_accepted_closures") or []), \
        "a result standing on an unchecked part must say so where the reader already looks"
    assert "CLOCK" in (step.get("auto_accepted_note") or ""), \
        "the note has to name what happened, not merely flag the node"
    e.stop()


def test_a_child_that_actually_failed_still_blocks():
    """The control. The conjunction is narrowed to the canon's reading, not loosened in general:
    a child that did not settle positively must still hold its parent."""
    e = _graph()
    T.signal(e, "kid", "ACCEPT", "agent")
    T.signal(e, "kid", "DELIVER", "agent", result="a first attempt")
    T.record_verdict(e, "kid", "FAIL", reviewer="rev", failed_criteria=["k"],
                     observed={"k": "ran it: red on the first case"})
    T.signal(e, "kid", "FAIL", "agent", failed_criteria=["k"])
    out = _parent_claims_the_aggregate(e)
    assert out.get("accepted") is False and "children" in str(out.get("error")), \
        f"a parent passed over a child in rework: {out}"
    e.stop()
