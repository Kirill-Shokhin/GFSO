"""Which nodes a live party works now: a person or the user's own console moving a node over the MCP door runs no process
of this server, so `in_flight` never names it and the page could only guess (the author, 2026-11-14: «иначе как инчат
должен быть видим как процесс?»). Read by `/api/runtime` (`working`) and pushed to open pages. An entry is a property of
a LIVE party, never of an identity: it opens on a move that leaves the node at work in the mover's hands, and closes when
the node leaves work or the mover's last connection is gone."""
from __future__ import annotations

import logging
import threading
import time
import weakref

from gfso.config import DEFAULT_PROJECT
from gfso.core.types import State, TaskId

log = logging.getLogger(__name__)

#: the states a node is worked in by its holder
AT_WORK = frozenset({State.EXECUTING, State.REWORKING})
#: (project, task_id, principal, via) → its entry
WORKING: dict = {}
#: Told of every change with the list after it — under the lock, as `inflight.LISTENERS` are and for its reason: two
#: changes crossing outside it reached a page out of order. So a listener must not block nor read `working()`.
LISTENERS: list = []
_LOCK = threading.Lock()
#: the engines whose transitions already close entries — one subscription each, made by the first entry on it
_WATCHED: weakref.WeakSet = weakref.WeakSet()


def moved(engine, task_id: str, principal: str, via: str = "mcp", person: str | None = None) -> None:
    """`principal` moved `task_id` and was not refused: if the node is now at work in its hands, it is seen worked —
    through the door `via` names, whose own liveness ends it (`gone`: a bridge's leases; `page_gone`: a person's
    last open page)."""
    t = engine.graph.get_task(TaskId(task_id))
    project = engine.project_name or DEFAULT_PROJECT
    key = (project, str(task_id), principal, via)     # …one entry a door: each ends by its own door's liveness
    with _LOCK:
        # watched first, whatever the node's state: an engine made again under the same project (a reopen) had its
        # node's entry standing from the old one, never closed by the new engine's transitions (critic)
        if engine not in _WATCHED:
            _WATCHED.add(engine)
            engine.on_transition(lambda tid, old, new, sig: new in AT_WORK or _drop(
                lambda k: k[:2] == (project, str(tid))))
        if t is None or t.state not in AT_WORK or str(t.assignee) != principal:
            # …a transition read before it was watched: none at work is seen, nor anyone's but its holder's
            held = str(t.assignee) if t is not None and t.state in AT_WORK else None
            stale = [k for k in WORKING if k[:2] == (project, str(task_id)) and k[2] != held]
            for k in stale:
                del WORKING[k]
            if stale:
                _changed()
            return
        if key in WORKING:
            return
        WORKING[key] = {"project": project, "task_id": str(task_id), "principal": principal,
                        "since": round(time.time(), 1), "via": via, "person": person}
        _changed()


def gone(principals) -> None:
    """These parties hold no live bridge now: what they worked through one is no longer seen worked."""
    _drop(lambda k: k[2] in principals and WORKING[k]["via"] == "mcp")


def page_gone(person: str) -> None:
    """This person has no page open now: what they worked from one is no longer seen worked."""
    _drop(lambda k: WORKING[k]["via"] == "page" and WORKING[k]["person"] == person)


def working() -> list[dict]:
    """What live parties work now, oldest first — copies, so a reader holds no lock."""
    with _LOCK:
        return _snapshot()


def _drop(which) -> None:
    with _LOCK:
        keys = [k for k in WORKING if which(k)]
        for k in keys:
            del WORKING[k]
        if keys:
            _changed()


def _snapshot() -> list[dict]:
    return sorted((dict(w) for w in WORKING.values()), key=lambda w: w["since"])


def _changed() -> None:
    now = _snapshot()
    for cb in list(LISTENERS):
        try:
            cb(now)
        except Exception:
            log.exception("a working listener failed")
