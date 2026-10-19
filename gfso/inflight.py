"""What this process is doing right now: one entry per running piece of long work (`_inflight`), read by
`/api/runtime` (`in_flight`) so a reconcile from another session sees work in flight and does not restart under it."""
from __future__ import annotations

import contextlib
import time
from gfso.config import DEFAULT_PROJECT


# WHAT THIS PROCESS IS DOING RIGHT NOW: one entry per running piece of long work — its verb, the
# project and node it works on, since when. Read by `/api/runtime`: the verbs (`busy`) let a
# reconcile arriving from another session see there is work in flight and decline to restart the
# server out from under it — a killed server does not take its `claude` children with it; the
# entries (`in_flight`) are what the page counts for its own project.
# ONE ENTRY PER CALL. As a set of names, the first of two concurrent `validate_result` calls to
# finish cleared the flag while the second was still running; as a count by name, two parallel runs
# of one verb on two nodes were one fact with no project — so the page counted token ticks instead,
# and lost every executor that was running tools rather than streaming (2026-09-24).
INFLIGHT: dict = {}


def _inflight(name: str, engine=None, task_id=None):
    @contextlib.contextmanager
    def _track():
        key = object()
        with _INFLIGHT_LOCK:
            INFLIGHT[key] = {"verb": name,
                             "project": None if engine is None
                             else (engine.project_name or DEFAULT_PROJECT),
                             "task_id": None if task_id is None else str(task_id),
                             "since": round(time.time(), 1)}
        try:
            yield
        finally:
            with _INFLIGHT_LOCK:
                del INFLIGHT[key]
    return _track()


def in_flight() -> list[dict]:
    """The work running in this process now, oldest first — copies, so a reader holds no lock."""
    with _INFLIGHT_LOCK:
        return sorted((dict(w) for w in INFLIGHT.values()), key=lambda w: w["since"])


_INFLIGHT_LOCK = __import__("threading").Lock()
