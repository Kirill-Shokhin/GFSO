"""§12.16: "A packet with no deadline does not conform." With the default switched off (`GFSO_DEFAULT_DEADLINE_S=0`) the
engine writes none, so a version typing none is refused, and the refusal says the issuer types one."""
from __future__ import annotations

from datetime import datetime, timedelta

import gfso.tools as T
from gfso.core.types import TaskId
from tests.support import criterion, make_engine

_SPEC = {"description": "a goal", "criteria": [criterion("c1", "C1 holds")]}


def _create(e, **kw):
    try:
        return T.create_task(e, "root", dict(_SPEC), assignee="me", **kw) or {}
    except ValueError as ex:
        return {"error": str(ex)}


def test_with_no_default_a_packet_typing_no_deadline_is_refused_and_one_typing_it_is_not(monkeypatch):
    monkeypatch.setenv("GFSO_DEFAULT_DEADLINE_S", "0")
    e = make_engine()
    e.start()
    out = _create(e)
    e.wait_idle()
    assert e.graph.get_task(TaskId("root")) is None and all(w in out.get("error", "") for w in ("no default deadline", "issuer types one")), out
    out = _create(e, deadline=(datetime.now() + timedelta(days=1)).isoformat())
    e.wait_idle()
    assert "error" not in out and e.graph.get_task(TaskId("root")).deadline is not None, out
    e.stop()
