"""The node read the page's panel is built from (`GET /api/tasks/{id}`) carries what the tool door's `get_task` carries —
the validator findings standing on it, which an ACCEPT_CHALLENGE ruling names by id. The route shaped the node itself
and lost them: the panel's ruling picker found none and sent the acceptance bare (ui, 2026-10-26).

CONTROL: shape the route from `task_out` again and the test goes red."""
from __future__ import annotations

from fastapi.testclient import TestClient

import gfso.tools as T
from gfso.api.server import create_app
from gfso.core.types import Mode, TaskId
from tests.test_a_ruling_is_part_of_the_acceptance import _auto_root, _challenged_with_a_finding, _no_l2  # noqa: F401
from tests.test_the_mode_decides_who_holds_what import _engine


def test_the_panel_reads_the_findings_a_ruling_names():
    e = _engine(Mode.AUTO)
    _auto_root(e)
    pid = _challenged_with_a_finding(e, "root", "g")
    body = TestClient(create_app(e)).get("/api/tasks/root").json()
    assert [p["id"] for p in body["regression_probes"]["g"]] == [pid]
    assert body["regression_probes"] == T.get_task(e, "root")["regression_probes"]
    assert body["audit"] and "children" in body and e.regression_probes(TaskId("root"))
