"""§12.16: "A packet with no deadline does not conform." The engine writes a default into a packet its issuer left
undated — always, a server's `GFSO_DEFAULT_DEADLINE_S=0` read as unset: a plan file types no deadline, so writing none
refused every part of a plan at its go. Where no default fits — under a parent whose deadline has passed — a version
typing none is refused, and the refusal says the issuer types one."""
from __future__ import annotations

from datetime import datetime, timedelta

import gfso.tools as T
from gfso.core.types import TaskId
from tests.support import REGISTER, criterion, make_engine

_SPEC = {"description": "a goal", "criteria": [criterion("c1", "C1 holds")]}


def _create(e, tid="root", **kw):
    try:
        return T.create_task(e, tid, dict(_SPEC), assignee="me", **kw) or {}
    except ValueError as ex:
        return {"error": str(ex)}


def test_a_server_switching_the_default_off_still_has_one_written(monkeypatch):
    monkeypatch.setenv("GFSO_DEFAULT_DEADLINE_S", "0")
    e = make_engine()
    e.start()
    out = _create(e)
    e.wait_idle()
    t = e.graph.get_task(TaskId("root"))
    assert "error" not in out and t is not None and t.deadline is not None and t.deadline_supplied, out
    e.stop()


def test_where_no_default_fits_a_packet_typing_none_is_refused():
    e = make_engine()
    e.start()
    T.create_task(e, "root", {**_SPEC, "accepted_risks": REGISTER}, assignee="me")   # …a split's register (§9.2)
    e.wait_idle()
    root = e.graph.get_task(TaskId("root"))
    root.deadline = datetime.now() - timedelta(hours=1)
    e._graph.save_task(root)
    out = _create(e, "kid", parent_id="root")
    e.wait_idle()
    assert e.graph.get_task(TaskId("kid")) is None and all(
        w in out.get("error", "") for w in ("leaves no time inside its own for a default", "issuer types one")), out
    e.stop()
