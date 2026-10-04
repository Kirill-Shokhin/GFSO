"""A refine whose model answered nothing re-authored a live root to `criteria: []`.

V over no criteria is vacuously true, so the goal's contract became one nothing can fail — a false
"done" waiting for any delivery. Seen 2026-09-24 when a stubbed model answered `{}` to an
`auto_decompose` over a project that already had its root. The round authored nothing; the contract
that stands must be kept.
"""
from __future__ import annotations

import gfso.tools as T
from gfso.core.types import TaskId
from gfso.decompose.build import build_graph_live
from tests.support import criterion, make_engine, REGISTER


def test_an_authoring_with_no_criteria_leaves_the_roots_contract_standing():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")],
                              "accepted_risks": REGISTER})
    e.wait_idle()
    build_graph_live({}, "the goal", e, root_id="root", assignee="agent")
    e.wait_idle()
    assert [c.name for c in e.graph.get_task(TaskId("root")).spec.criteria] == ["g"]
