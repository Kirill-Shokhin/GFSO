"""An INTERNAL node closed DONE/PASS on a roster id's signature with no verdict of any kind.

§14.5 D6 says an internal node — one whose Del equals its parent's — self-verifies rather than being
judged independently, and §11.2 says ⊥ is not a pass. The engine held both: a PASS on such a node
with no self-check and no recorded verdict was refused… **when the signer was the node's own
executor**. The guard's condition was `signal_data.source == task.assignee`.

On an internal node the role check admits exactly two parties: the executor, and an id on
`authorized_validators` (§14.5's per-role exception, which the engine implements for PASS/FAIL). The
second walked straight past this guard. `graph.is_public(task)` is False for an internal node, so the
seam branch below never ran either. Nothing was left.

Probed 2026-09-08, with a paired control on one graph:

    child delivered "I wrote nothing at all"
      signed by 'val-1' (on the roster)   -> accepted, DONE/PASS
                                             verdict record: None · provenance: none
                                             per_criterion: []
      signed by 'alice' (its executor)    -> refused, with the correct sentence

The difference between a refusal and a false close was one name on a roster. And the child's
DONE/PASS is a conjunct of Thm 1's AND at its parent, so the ⊥ does not stay put — it propagates
upward as a pass.

The rule the seam branch was corrected to on 2026-09-05 is the one that was missing here: *an id on
a roster is a CLAIM about who is signing; the record is the evidence that judging happened.* So the
guard now asks for the record and not for the name — which is also why nothing legitimate is lost,
and the two positive cases below are the proof of that rather than a courtesy.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.core.types import AgentId, TaskId
from tests.support import UNMODELLED_FAULT, make_engine

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]


def _internal_child(self_validation: str | None = None):
    """A child whose Del equals its parent's — internal by §14.5's own criterion — mid-delivery."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "r", {"description": "the goal", "accepted_risks": _RISK,
                           "criteria": [{"name": "g", "description": "G holds"}]}, assignee="alice")
    T.create_task(e, "k", {"description": "a private step",
                           "criteria": [{"name": "c", "description": "C holds"}]},
                  assignee="alice", parent_id="r")
    T.map_criterion(e, "r", "k", "g")
    T.signal(e, "k", "ACCEPT", "alice")
    T.signal(e, "k", "DELIVER", "alice", result="I wrote nothing at all",
             **({"self_validation": self_validation} if self_validation else {}))
    return e


def _roster(e, who: str):
    """What `register_agent(<id>, "llm-validator")` publishes, and what the dispatcher republishes."""
    e._graph.authorized_validators.add(who)
    return e


def test_a_roster_name_does_not_close_an_internal_node_over_nothing() -> None:
    e = _roster(_internal_child(), "val-1")
    assert not e._graph.is_public(e.get_task("k"))          # the branch under test is the internal one

    out = T.signal(e, "k", "PASS", "val-1")

    assert out.get("accepted") is False, (
        f"an internal node reached {e.get_task('k').state.name} on a signature with no verdict "
        f"behind it — `get_verdict` answers {T.get_verdict(e, 'k').get('verdict')!r} about the node "
        f"that just closed. ⊥ is not a pass (§11.2), whoever's name is on it."
    )
    assert e.get_task("k").state.name == "VALIDATING"
    assert "no self-check for this delivery" in out["error"]


def test_the_same_delivery_signed_by_its_executor_is_refused_the_same_way() -> None:
    """The paired control that makes the finding legible: one graph, two signers, one rule.

    This half always passed. It is here so that a future change which re-narrows the guard to the
    executor shows up as the two halves disagreeing, rather than as one of them quietly going green.
    """
    out = T.signal(_internal_child(), "k", "PASS", "alice")

    assert out.get("accepted") is False
    assert "no self-check for this delivery" in out["error"]


def test_the_canon_s_own_internal_path_still_closes() -> None:
    """§14.5 D6: "DELIVER carries `self_validation`". That records a verdict, so the node closes."""
    e = _internal_child(self_validation="PASS")

    assert T.signal(e, "k", "PASS", "alice").get("accepted") is True
    assert e.get_task("k").state.name == "DONE"


def test_a_validator_that_actually_judges_still_closes_it() -> None:
    """And the roster id is not banned — it is asked for the same thing everyone else is.

    Every instrument path in this product records its verdict and then signs it, so the requirement
    is one they already meet; what is refused is a signature standing on nothing.
    """
    e = _roster(_internal_child(), "val-1")
    T.record_verdict(e, "k", "PASS", reviewer="val-1",
                     observed={"c": "ran the check for c; it printed OK"})

    assert T.signal(e, "k", "PASS", "val-1").get("accepted") is True
    assert e.get_task("k").state.name == "DONE"


def test_a_seam_node_is_untouched_by_this_guard() -> None:
    """The internal branch must not start answering for the seam: they carry different rules.

    A root is always public (§14.5), so it goes to the seam branch and gets the seam's sentence —
    about an INDEPENDENT verdict, not about a self-check.
    """
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "solo", {"description": "a goal", "accepted_risks": _RISK,
                              "criteria": [{"name": "g", "description": "G holds"}]},
                  assignee="ann")
    T.signal(e, "solo", "ACCEPT", "ann")
    T.signal(e, "solo", "DELIVER", "ann", result="done")

    out = T.signal(e, "solo", "PASS", "ann")

    assert out.get("accepted") is False
    assert "independent verdict" in out["error"], out["error"]
