"""A revision of a finished node is a reopen (Inv-1), and the R′ gate holds on both verbs (§14.3).

This file exists because of a finding that was WITHDRAWN, and it is worth keeping for that reason.

A stranger on the HTTP door reported at HIGH that `revise` walks past the CONSUMED lock `reopen`
enforces, with both responses quoted: `reopen` refused — *"finally locked (§14.3) … never a reopen"* —
and `revise` on the same child answered 200 with the node back in OFFERED (wave 23, 2026-09-03).

It did not reproduce. Building the state the report describes — a parent that has staked its
aggregate on a finished child — the state machine refuses BOTH verbs, because the R′ gate lives at
the FSM chokepoint (`ASSIGN` out of a quasi-terminal, double-gated on `consumed` ∧ reopens), and
every one of these verbs is an `ASSIGN` under Inv-1. Asked for the state rather than the conclusion,
the tester answered from their own transcript: the two calls were EIGHT calls apart, and in between
their own earlier `edit_criteria` had dropped the root from DONE to OFFERED and destroyed every
mapping onto the child, while a sibling holding a Dep on it was reopened. The engine's own check, in
the same call as the `revise`, read *"children addressing no parent criterion"*. Nothing was staked
on that child any more, so admitting the revision was correct — and they withdrew the finding.

Two things are worth having afterwards. The property itself, pinned here so the next reader does not
have to re-derive it from a report. And the shape of the mistake, which is not the tester's alone: a
refusal and an acceptance seconds apart in a transcript look like a contradiction, and are only one
if nothing moved in between.
"""
from __future__ import annotations

import pytest

from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine


def _parent_staking_on_a_finished_child(e):
    """Child DONE and its parent's aggregate DELIVERed on top of it — which is what CONSUMED means."""
    T.create_task(e, "par", {"description": "the parent",
                             "criteria": [{"name": "g", "description": "G holds"}],
                             "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                 "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    T.create_task(e, "par.kid", {"description": "the child",
                                 "criteria": [{"name": "k", "description": "K holds"}]},
                  assignee="exec-1", parent_id="par")
    T.map_criterion(e, "par", "par.kid", "g")
    e.wait_idle()
    T.signal(e, "par.kid", "ACCEPT", "exec-1")
    T.signal(e, "par.kid", "DELIVER", "exec-1", result="child built")
    T.record_verdict(e, "par.kid", "PASS", reviewer="judge",
                     observed={"k": "ran the k check and read K-OK"})
    T.signal(e, "par.kid", "PASS", "exec-1")
    T.signal(e, "par", "ACCEPT", "exec-1")
    T.signal(e, "par", "DELIVER", "exec-1", result="aggregate delivered on the child's result")
    e.wait_idle()
    kid = e.get_task(TaskId("par.kid"))
    assert kid.state.name == "DONE" and e.graph.is_consumed(kid), (
        "the probe never produced a CONSUMED child, so it cannot see its subject")


def test_neither_reopen_nor_revise_moves_a_consumed_node():
    e = make_engine()
    e.start()
    _parent_staking_on_a_finished_child(e)

    assert "CONSUMED" in (T.reopen(e, "par.kid", "exec-1") or {}).get("error", "")
    # The two doors refuse in two SHAPES — `reopen` answers with a reason, `revise` raises out of the
    # engine — and that difference is why the report read as a contradiction. It is worth pinning as
    # it is rather than smoothing over: the caller is refused either way, and what the wave actually
    # exposed is that one of the two is harder to read than the other.
    with pytest.raises(ValueError, match="finality-gate"):
        T.revise(e, "par.kid", {"description": "rewritten out from under its parent",
                                "criteria": [{"name": "x", "description": "X"}],
                                "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                    "predictability": "EXTRAORDINARY"}]},
                 "exec-1")

    kid = e.get_task(TaskId("par.kid"))
    assert kid.state.name == "DONE", "a consumed child was sent back to OFFERED by `revise`"
    assert [c.name for c in kid.spec.criteria] == ["k"], (
        "the contract its parent staked its aggregate on was replaced under it")
    e.stop()


def test_the_read_modify_write_verbs_answer_to_the_same_gate():
    """`edit_criteria` is `revise` with the rest carried, so it reaches the same FSM edge."""
    e = make_engine()
    e.start()
    _parent_staking_on_a_finished_child(e)

    with pytest.raises(ValueError, match="finality-gate"):
        T.edit_criteria(e, "par.kid", [{"name": "x", "description": "X"}], "exec-1")

    assert [c.name for c in e.get_task(TaskId("par.kid")).spec.criteria] == ["k"]
    e.stop()


def test_a_live_node_is_still_revised_normally():
    """The negative control: the gate is about FINISHED nodes and must not reach a node in play."""
    e = make_engine()
    e.start()
    T.create_task(e, "live", {"description": "still in play",
                              "criteria": [{"name": "c", "description": "C"}],
                              "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                  "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    e.wait_idle()

    out = T.edit_criteria(e, "live", [{"name": "c2", "description": "C2"}], "exec-1")

    assert "error" not in out, out
    assert [c.name for c in e.get_task(TaskId("live")).spec.criteria] == ["c2"]
    e.stop()
