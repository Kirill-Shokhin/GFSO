"""What this process is doing right now: one entry per running piece of long work (`_inflight`), read by
`/api/runtime` (`in_flight`) so a reconcile from another session sees work in flight and does not restart under it."""
from __future__ import annotations

import contextlib
import logging
import time
from gfso.config import DEFAULT_PROJECT

log = logging.getLogger(__name__)


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
# Told of every entry and exit, with the work in flight after it — the server pushes that to open pages, which would
# otherwise learn a process started or ended only on a clock of their own. Called UNDER the lock, with the list taken
# under it: outside, two threads crossing a start and an end queued their lists out of order and a page was left showing
# a finished session at work (critic, 2026-10-26). So a listener must not block and must not read `in_flight()`;
# a failing one is logged, never raised into the work.
LISTENERS: list = []


def _changed() -> None:
    now = _snapshot()
    for cb in list(LISTENERS):
        try:
            cb(now)
        except Exception:
            log.exception("an in-flight listener failed")


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
            _changed()
        try:
            yield
        finally:
            with _INFLIGHT_LOCK:
                del INFLIGHT[key]
                _changed()
    return _track()


def in_flight() -> list[dict]:
    """The work running in this process now, oldest first — copies, so a reader holds no lock."""
    with _INFLIGHT_LOCK:
        return _snapshot()


def _snapshot() -> list[dict]:
    """`in_flight()` for a caller already holding the lock."""
    return sorted((dict(w) for w in INFLIGHT.values()), key=lambda w: w["since"])


_INFLIGHT_LOCK = __import__("threading").Lock()
