"""An accepted risk that cannot be read back is not a register, it is a sentence.

§9.2 makes the ACCEPTED_RISKS register the place a decomposition declares what it knowingly does not
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

Canon v4.1 (§9.2): the register is the split's, written by its decomposer with the split; a pre-filled one in the
packet is task data, not the split's register. So the split's register reads back under `accepted_risks_recorded`,
and the packet's pre-fill under its own name, `prefilled_accepted_risks` — each whole, neither as the other.
"""
from __future__ import annotations

from gfso import tools as T
from fastapi.testclient import TestClient
from gfso.api.server import create_app
from gfso.core.types import TaskId
from tests.support import DENIAL_ENTRY, criterion, make_engine

_RISK = {"item": "a flaky network", "predictability": "STATISTICAL",
         "justification": "measured at 2 in 1000 calls over the last month",
         "invalidation_condition": "if the failure rate exceeds 1%", "p": 0.002,
         "impact": "a request is retried", "component": "", "denial": False}


def _with_a_risk(e):
    """The register where §9.2 puts it: on the split, written by its decomposer with it."""
    T.create_task(e, "n", {"description": "goal", "criteria": [criterion("c", "C")]}, assignee="agent")
    T.decompose(e, "n", [{"task_id": "k", "spec": {"description": "part", "criteria": [criterion("k", "K")]},
                          "assignee": "agent", "covers": ["c"]}], accepted_risks=[_RISK, DENIAL_ENTRY])


def test_the_verb_that_creates_it_reads_it_back_whole():
    """The verb that writes the packet's pre-fill answers with it whole — as the pre-fill, not as the split's register."""
    e = make_engine()
    e.start()

    out = T.create_task(e, "n", {"description": "goal", "criteria": [criterion("c", "C")],
                                 "accepted_risks": [_RISK]}, assignee="agent")

    assert out.get("prefilled_accepted_risks", [None])[0] == _RISK, out
    assert out["accepted_risks_recorded"] == [], "a pre-fill read back as the split's register"
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

    with TestClient(create_app(e)) as c:          # the page's read: the one shaping of a node (D-F16)
        out = c.get("/api/tasks/n").json()

    assert out["accepted_risks_recorded"][0] == _RISK, out["accepted_risks_recorded"]
    assert out["accepted_risks"] == [_RISK["item"], DENIAL_ENTRY["item"]], "the item text stays first-class"
    e.stop()
