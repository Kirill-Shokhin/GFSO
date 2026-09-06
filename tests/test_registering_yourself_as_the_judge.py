"""Registering an identity as the instrument does not make it independent OF ITSELF (§14.5).

Found by a stranger on the CLI door (wave 23, 2026-09-03) and then reproduced against the live
server with a paired control, because the tester's own diagnosis of it was wrong. What they reported
was "the seam gate checks that a verdict EXISTS, not that it says PASS". What actually happened:
earlier in the same session they had called

    register_agent(agent_id="agent", kind="llm-validator", workdir=..., project="w23atk5")

— an ordinary, documented call — and `agent` is the standing identity every door hands a caller who
does not name themselves. The gate opens for a registered instrument's signature, because such a
signature IS the judgement rather than an impression about one. So the identity that executes became
the identity whose signature closes the seam, and after that one call a leaf could be delivered with
"I claim it is done (nothing was written)" and signed DONE by its own executor, with no verdict on
the record at all.

The control that settled it, on one live server, one minute apart:

    signer `agent`      (in the roster)  -> PASS ACCEPTED,  no verdict recorded
    signer `probe-exec` (not in it)      -> PASS REFUSED,  "needs an independent verdict"

The roster is one server-wide fact by design, so the registration made in one project opened the
gate in another — but the cross-project reach is not the defect and is not what this fixes. The
defect is that `source == Del` was never asked on the instrument branch: verifier ≠ executor is a
statement about the NODE's two parties, and no registration can satisfy it by collapsing them.

SINCE 2026-09-05 THE BRANCH IS GONE, not merely narrowed. Excluding the node's own executor was the
right cut and it left the class open: "the signature IS the judgement" is true only where a
signature cannot be typed, and `source` is caller-supplied on the CLI and HTTP doors (only MCP
derives it from the transport). A conformance audit probed the rest of it — `register_agent("ghost-
val", "llm-validator")` and one `signal ... PASS ghost-val` closed a root that had delivered
"nothing was actually written", with no verdict record and q_V reporting 1.0. So a public node now
needs a current verdict on the record whoever signs; every instrument path in the product already
wrote one before signing, so nothing legitimate was taken away.
"""
from __future__ import annotations

import pytest

from gfso import tools as T
from gfso.core.types import Verdict, TaskId
from tests.support import UNMODELLED_FAULT, make_engine


def _engine():
    """Started, because the engine is event-driven: a node does not exist until the bus settles."""
    e = make_engine()
    e.start()
    return e


def _leaf(e, tid="leaf", assignee="agent"):
    T.create_task(e, tid, {"description": "a leaf that never does the work",
                           "criteria": [{"name": "file_exists", "description": "NEVER.txt exists"}],
                           "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                               "predictability": "EXTRAORDINARY"}]},
                  assignee=assignee)
    e.wait_idle()
    T.signal(e, tid, "ACCEPT", assignee)
    T.signal(e, tid, "DELIVER", assignee, result="I claim it is done (nothing was written).")
    e.wait_idle()
    assert e.get_state(TaskId(tid)).name == "VALIDATING", "the probe never reached the seam at all"


def test_a_registered_instrument_cannot_open_the_seam_on_its_OWN_node():
    """The executor of a node is not independent of it, whatever the roster says about the id."""
    e = _engine()
    e._graph.authorized_validators = {"agent"}      # what `register_agent(agent, llm-validator)` publishes
    _leaf(e, "leaf", assignee="agent")

    out = T.signal(e, "leaf", "PASS", "agent")

    assert out["accepted"] is False, (
        "the node's own executor signed its own PASS with NO verdict on record, because the id had "
        "been registered as an instrument — this is the whole promise of the product, refused")
    assert e.get_state(TaskId("leaf")).name == "VALIDATING"
    assert "independent verdict" in (out.get("error") or "")
    e.stop()


def test_an_instrument_opens_the_seam_ON_THE_VERDICT_IT_PRODUCED():
    """This asserted something narrower than it looked, and the difference was a hole.

    It was written as "an instrument's signature IS the judgement", and it passed with NO verdict on
    the record — the signature alone opened the seam. That reading holds only where a signature
    cannot be typed, and `source` is caller-supplied on two of the three doors: `register_agent`
    plus one `signal` closed a root that had delivered "nothing was actually written" (audited and
    probed 2026-09-05, F1). The narrowing keeps exactly what this leg was for — the delegated
    regime, where `val-1` signs the verdict it just produced on a node executed by `exec-1` — and
    drops what it never meant to say. Every instrument path in the product already records first.
    """
    e = _engine()
    e._graph.authorized_validators = {"val-1"}
    _leaf(e, "leaf", assignee="exec-1")

    assert T.signal(e, "leaf", "PASS", "val-1")["accepted"] is False, "a bare signature closed it"

    t = e.get_task(TaskId("leaf"))
    e.record_reviewer_verdict(TaskId("leaf"), Verdict.PASS, [], reviewer="val-1",
                              observed={c.name: "ran it, it printed what it should"
                                        for c in t.spec.criteria})
    out = T.signal(e, "leaf", "PASS", "val-1")

    assert out["accepted"] is True, out.get("error")
    assert e.get_state(TaskId("leaf")).name == "DONE"
    e.stop()


def test_the_refusal_names_the_registration_rather_than_only_the_rule():
    """A caller who registered themselves needs to be told THAT, or they read the refusal as a bug.

    The tester who found this filed it as "the gate checks existence, not content" and attacked it
    for another hour on that theory. The engine knows exactly which of the two situations it is in —
    an ordinary executor, or an executor who is also on the validator roster — and saying so is the
    difference between a wall and an answer.
    """
    e = _engine()
    e._graph.authorized_validators = {"agent"}
    _leaf(e, "leaf", assignee="agent")

    err = (T.signal(e, "leaf", "PASS", "agent").get("error") or "")

    assert "roster" in err and "independent of itself" in err, err
    assert "judge your own work" in err, err
    e.stop()
