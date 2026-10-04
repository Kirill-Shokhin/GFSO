"""A record must not assert a registration it never checked (§15.7, and the wave that found it).

`validate_result` takes the validator's NAME from the caller. That is right — an ad-hoc validator is one of
the two documented ways to get a verdict, and requiring registration first would close the door the
docs send a new user through. What was wrong is what the read then said about it: a stranger passed
`validator="w23http-ghost-instrument"`, a name invented in that same call and in no roster, and
`get_verdict` answered *"produced by the registered instrument named in `validator`"* with
`by_hand: false` beside it (HTTP door, wave 23, 2026-09-03).

The validation was genuine — the same ghost name on a node with real criteria came back FAIL with
running evidence — so the verdict is not the defect. The CLAIM about who produced it is: §15.7 says
the engine cannot verify a self-named party's independence, and the honest consequence is to say so
rather than to upgrade the name for free. The roster is a fact the engine already holds.
"""
from __future__ import annotations

from gfso import tools as T
from tests.support import criterion, instrument_passes, make_engine, REGISTER


def _validated_by(e, name, tid="leaf"):
    T.create_task(e, tid, {"description": "a leaf",
                           "criteria": [criterion("c", "C")],
                           "accepted_risks": REGISTER},
                  assignee="exec-1")
    e.wait_idle()
    T.signal(e, tid, "ACCEPT", "exec-1")
    T.signal(e, tid, "DELIVER", "exec-1", result="built it")
    # …reported through the shared fixture, which answers the procedure the contract PINS: the
    # subject here is what the record says about WHO validated, and a report that skipped the pinned
    # probe would never reach that question — it would be refused as ⊥ first.
    instrument_passes(e, tid, validator=name)
    return T.get_verdict(e, tid)


def test_a_name_nobody_registered_is_not_called_a_registered_instrument():
    e = make_engine()
    e.start()
    e._graph.authorized_validators = {"val-1"}

    out = _validated_by(e, "ghost-instrument")

    assert out["provenance"] == "instrument"          # the run WAS an instrument run
    assert "registered instrument" not in out["independence"], out["independence"]
    assert "not on the validator roster" in out["independence"], out["independence"]
    e.stop()


def test_a_registered_validator_is_still_read_as_one():
    """The negative control: the honest case must not acquire a warning it has not earned."""
    e = make_engine()
    e.start()
    e._graph.authorized_validators = {"val-1"}

    out = _validated_by(e, "val-1")

    assert out["provenance"] == "instrument"
    assert "not on the validator roster" not in out["independence"], out["independence"]
    e.stop()
