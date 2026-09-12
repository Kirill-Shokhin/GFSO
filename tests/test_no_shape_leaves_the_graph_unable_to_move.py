"""An instrument for the CLASS both of today's locks belonged to, not a third instance of it.

Two were found on 2026-09-07 — a child accepted by the clock whose parent's conjunction refused it
for good, and a contract holding nothing a verdict could be about — and the author's note on the
first is the reason this file exists: it had been reported, diagnosed and promised closed across
about ten sessions. Each time the instance was patched. What was never built is a rule that fails on
the SHAPE, so the eleventh cannot arrive quietly.

The shape is not "the graph is waiting". A graph waiting for a person is healthy, and says so
(`stuck: true` with a recovery, or a node advertising a move). The shape is the DISAGREEMENT: the
run is unfinished, nothing anywhere admits a move from any role, and the surface still answers
`stuck: false` — "the graph is working, poll again in a minute" over a graph that cannot advance.
Both locks looked exactly like that from outside, and the third will too.

The sweep below walks the shapes a real run passes through. It is deliberately cheap and
deliberately broad: catching one more of these is worth more than proving anything about any one of
them, and the guard has to be run on graphs nobody thought to suspect.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.core.types import Signal, SignalData, TaskId
from tests.support import UNMODELLED_FAULT, assert_the_graph_can_still_move, make_engine

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]


def _two_children(e):
    T.create_task(e, "root", {"description": "a goal", "accepted_risks": _RISK,
                              "criteria": [{"name": "g", "description": "G holds"}]},
                  assignee="agent")
    for kid in ("a", "b"):
        T.create_task(e, kid, {"description": f"work {kid}",
                               "criteria": [{"name": kid, "description": f"{kid} holds"}]},
                      assignee="agent", parent_id="root")
        T.map_criterion(e, "root", kid, "g")
    return e


def _accepted(out, what, node):
    """A REFUSED signal is not a step. The sweep drove its shapes through `T.signal` and never
    looked at the answer, so when the plan gate refused every child signal the shapes were never
    built at all — eight of the ten named states were simply OFFERED, and the sweep reported green
    over graphs it had not constructed. A guard blind to its own subject, for the second time in
    this file's history."""
    assert out.get("accepted"), f"{what} on {node} was REFUSED: {out.get('error') or out}"
    return out


def _delivered(e, node):
    # ACCEPT only where the state admits it: a node in REWORKING is already under contract and
    # re-delivers directly (§14.3). Sending it anyway made the rework loop refuse on its first turn,
    # so the shape named "spent its rework bound and escalated" never escalated — and that is the
    # one shape a root's conjunction cannot survive.
    if e.get_task(node).state.name == "OFFERED":
        _accepted(T.signal(e, node, "ACCEPT", "agent"), "ACCEPT", node)
    _accepted(T.signal(e, node, "DELIVER", "agent", result=f"{node} done"), "DELIVER", node)


def _judged(e, node, verdict="PASS", failed=()):
    T.record_verdict(e, node, verdict, reviewer="rev", failed_criteria=list(failed),
                     observed={c.name: f"ran the check for {c.name}"
                               for c in e.get_task(node).spec.criteria if not c.depends_on})
    _accepted(T.signal(e, node, verdict, "agent",
                       **({"failed_criteria": list(failed)} if failed else {})), verdict, node)


def _engine():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    return _two_children(e)


def _claim_the_aggregate(e):
    """Drive the parent as far as it will go — where a lock BITES, not merely where it exists.

    The first version of this sweep never delivered the root, so the shape it was written for
    (a settled child the parent's conjunction refuses) was never reached: eleven cases green with
    the lock deliberately restored. A guard blind to its own subject is the defect it guards
    against, wearing a name.
    """
    if e.get_task("root").state.name == "OFFERED":
        T.signal(e, "root", "ACCEPT", "agent")
    if e.get_task("root").state.name == "EXECUTING":
        T.signal(e, "root", "DELIVER", "agent", result="the aggregate")
    if e.get_task("root").state.name == "VALIDATING":
        T.record_verdict(e, "root", "PASS", reviewer="rev",
                         observed={"g": "read what the children produced; it holds"})
        T.signal(e, "root", "PASS", "agent")


def _walk(e, steps):
    for act in steps:
        act(e)
        assert_the_graph_can_still_move(e)
    # …AND THEN AT THE END, where a parent meets what its children became.
    _claim_the_aggregate(e)
    assert_the_graph_can_still_move(e)


@pytest.mark.parametrize("name,steps", [
    ("nothing has started yet", []),
    ("one child accepted, one untouched",
     [lambda e: T.signal(e, "a", "ACCEPT", "agent")]),
    ("one child delivered and awaiting a verdict",
     [lambda e: _delivered(e, "a")]),
    ("one child passed, the other not started",
     [lambda e: _delivered(e, "a"), lambda e: _judged(e, "a")]),
    ("one child accepted BY THE CLOCK — the lock of 2026-09-07",
     [lambda e: _delivered(e, "a"),
      lambda e: e.send_signal(SignalData(signal=Signal.TIMEOUT, task_id=TaskId("a"))),
      lambda e: e.wait_idle()]),
    ("a child in rework",
     [lambda e: _delivered(e, "a"), lambda e: _judged(e, "a", "FAIL", ("a",))]),
    ("a child that spent its rework bound and escalated",
     [lambda e: _delivered(e, "a"),
      lambda e: [(_delivered(e, "a") if e.get_task("a").state.name == "REWORKING" else None,
                  _judged(e, "a", "FAIL", ("a",)))
                 for _ in range(4)]]),
    ("a child blocked on a sibling",
     [lambda e: T.signal(e, "a", "ACCEPT", "agent"),
      lambda e: T.signal(e, "a", "BLOCK", "agent", reason="waiting on b",
                         blocker_task_ids=["b"])]),
    ("a child cancelled out of the plan",
     [lambda e: T.signal(e, "a", "CANCEL", "agent", reason="out of scope"),
      lambda e: T.signal(e, "a", "CONFIRM_CANCEL", "agent")]),
    # THE SHAPE THE SWEEP DID NOT HAVE, and the one a real run dies on: one child settled WITHOUT
    # passing while every sibling is done and the parent is delivered. The parent's AND can never be
    # satisfied, so no verdict arrives — and the frontier used to answer "the graph is working,
    # poll again in a minute" over it, for ever.
    ("a child settled without passing while its sibling is done",
     [lambda e: [(_delivered(e, "a"), _judged(e, "a", "FAIL", ("a",))) for _ in range(4)],
      lambda e: _delivered(e, "b"), lambda e: _judged(e, "b")]),
    ("both children accepted by the clock",
     [lambda e: _delivered(e, "a"), lambda e: _delivered(e, "b"),
      lambda e: e.send_signal(SignalData(signal=Signal.TIMEOUT, task_id=TaskId("a"))),
      lambda e: e.send_signal(SignalData(signal=Signal.TIMEOUT, task_id=TaskId("b"))),
      lambda e: e.wait_idle()]),
])
def test_the_graph_can_always_move_or_says_it_cannot(name, steps):
    e = _engine()
    try:
        _walk(e, steps)
    finally:
        e.stop()


def test_the_instrument_fires_on_a_graph_that_really_cannot_move(monkeypatch):
    """The negative control. A rule that has never been seen red is a rule nobody has tested —
    and this one guards a shape that, by construction, is not supposed to occur."""
    e = _engine()
    _delivered(e, "a")
    # every role loses every affordance, while the frontier keeps reporting an ordinary wait
    monkeypatch.setattr(T, "available_actions", lambda *a, **k: {"actions": []})
    with pytest.raises(AssertionError, match="NO node admits a move"):
        assert_the_graph_can_still_move(e)
    e.stop()
