"""An accepted risk that cannot be read back is not a register, it is a sentence.

§13.1 makes the ACCEPTED_RISKS register the place a decomposition declares what it knowingly does not
cover, and CHECK-4 demands a predictability verdict per factor; the invalidation condition is what
turns an acceptance into something anyone can later revoke. `edit_accepted_risks` has answered with
the whole record since 2026-08-21 — and every OTHER read of a node kept returning bare item strings,
so a caller who classified a risk, justified it and named its invalidation condition got back the
sentence they started from.

Three doors reported it in three waves, in almost the same words: *"I could not confirm from any
surface that predictability and the invalidation conditions were stored"* (MCP, 2026-09-03),
*"`create_task` echoed my structured accepted_risks back as a bare string"* (CLI, 2026-09-04),
*"validated on write and dropped on read … the invalidation condition is the entire point of the
register"* (HTTP, 2026-09-04).

The HTTP door had half of it under a second name (`accepted_risks_detail`, without the invalidation
condition) — one fact in two spellings, one of them incomplete, which is the shape this codebase
keeps finding in itself. One name now, four fields, with the old key kept as an alias for a release.
"""
from __future__ import annotations

from gfso import tools as T
from gfso.api.models import task_to_out
from gfso.core.types import TaskId
from tests.support import make_engine

_RISK = {"item": "a flaky network", "predictability": "STATISTICAL",
         "justification": "measured at 2 in 1000 calls over the last month",
         "invalidation_condition": "if the failure rate exceeds 1%"}


def _with_a_risk(e):
    return T.create_task(e, "n", {"description": "goal",
                                  "criteria": [{"name": "c", "description": "C"}],
                                  "accepted_risks": [_RISK]}, assignee="agent")


def test_the_verb_that_creates_it_reads_it_back_whole():
    e = make_engine()
    e.start()

    rec = _with_a_risk(e)["accepted_risks_recorded"][0]

    assert rec == _RISK, rec
    e.stop()


def test_and_so_does_every_later_read_of_the_node():
    e = make_engine()
    e.start()
    _with_a_risk(e)
    e.wait_idle()

    assert T.get_task(e, "n")["accepted_risks_recorded"][0] == _RISK
    e.stop()


def test_the_http_door_carries_all_four_fields_under_the_same_name():
    """The door that had it under a second name, missing the field that makes it revocable."""
    e = make_engine()
    e.start()
    _with_a_risk(e)
    e.wait_idle()

    out = task_to_out(e.get_task(TaskId("n"))).model_dump()

    assert out["accepted_risks_recorded"][0] == _RISK, out["accepted_risks_recorded"]
    assert out["accepted_risks_detail"] == out["accepted_risks_recorded"], (
        "the deprecated alias must not drift from what it aliases")
    assert out["accepted_risks"] == [_RISK["item"]], "the item text stays first-class"
    e.stop()
