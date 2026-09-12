"""The deadline was write-once: set at creation, and unreachable by anything afterwards.

Inv-1 (§14.4) names the four packet fields a revision exists to change — "criteria, **deadline**,
ACCEPTED_RISKS, Del" — and §14.6 walks the case end to end: a RESOLVE_BLOCK moves Feature B from d7
to d9, the node re-consents, and CHECK-3 is re-checked against Testing's d12. None of that could
happen here. Probed 2026-09-07: a revision carrying a new deadline was ACCEPTED — the node went to
OFFERED and the executor re-consented, so a real contract change had occurred — and the date did not
move. A verb that accepts a decision and discards it is worse than one that refuses, because the
caller has no way to learn which of the two happened.

The only exit left was CANCEL, which cascades the subtree — precisely what Inv-1 says a revision
must not do ("A revision does NOT cascade").

What this does NOT change: a node without a deadline is not defective. That is the canon's own
position (§10 — a deadline is a design decision) and a declared corner of this implementation
(`formal/README.md` #6, "absence of deadlines stays silent"), so the builder that sets none is
left alone. `None` here means KEEP, exactly as it does for the executor.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import gfso.tools as T
from tests.support import UNMODELLED_FAULT, make_engine

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]
_SPEC = {"description": "a goal", "accepted_risks": _RISK,
         "criteria": [{"name": "c1", "description": "C1 holds"}]}


def _with_a_deadline(e, days):
    T.create_task(e, "root", dict(_SPEC), assignee="agent",
                  deadline=(datetime.now() + timedelta(days=days)).isoformat())
    return e.get_task("root").deadline


def test_a_revision_moves_the_deadline_it_carries():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    first = _with_a_deadline(e, 5)
    later = (datetime.now() + timedelta(days=14)).isoformat()

    out = T.revise(e, "root", dict(_SPEC), agent="agent", deadline=later)
    assert out and "error" not in out and out["state"] == "OFFERED", \
        f"the revision itself must still be a revision — re-consent, no cascade: {out}"
    moved = e.get_task("root").deadline
    assert moved != first and moved.isoformat()[:16] == later[:16], \
        f"asked for {later}, node carries {moved} — the field Inv-1 names was dropped in silence"
    e.stop()


def test_a_revision_that_says_nothing_about_it_keeps_it():
    """The control. `None` is KEEP, as it is for the executor — a revision about the criteria is not
    a revision that clears the schedule."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    first = _with_a_deadline(e, 5)
    T.revise(e, "root", {**_SPEC, "criteria": [{"name": "c1", "description": "C1 holds, sharpened"}]},
             agent="agent")
    assert e.get_task("root").deadline == first, "a revision silently cleared the deadline"
    e.stop()


def test_a_spec_dict_cannot_smuggle_one():
    """A spec is not where a packet field lives, and the refusal says where it does live — the
    silent drop this whole file is about had exactly this shape."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    _with_a_deadline(e, 5)
    try:
        T.revise(e, "root", {**_SPEC, "deadline": "2026-12-01"}, agent="agent")
    except ValueError as ex:
        assert "`deadline`" in str(ex) and "revise(..., deadline=" in str(ex), \
            f"the refusal must name the carrier, not merely reject: {ex}"
    else:
        raise AssertionError("a spec dict carrying a packet field went through and was dropped")
    e.stop()
