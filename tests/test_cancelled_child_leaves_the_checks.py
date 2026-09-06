"""A refused subtask stops gating the plan it is no longer part of.

The structural checks are read from a CACHE, and a cancelled node leaves the decomposition at CANCEL
(§14.3; its V = ⊥, and Thm 1 operates only on tasks with V ≠ ⊥) while staying in the graph as
provenance. `Engine._recompute_checks` has always ranged over the ACTIVE children — but nothing
recomputed on a cancellation, so the cache went on naming tombstones. Measured live: a goal was
revised, the four subtasks belonging to the old plan were refused, and CHECK-1b kept reporting them
as orphans; since the pre-execution gate reads that cache, the graph could not be executed again and
the protocol's own way to drop planned work was unusable.
"""
from __future__ import annotations

import gfso.tools as T
from gfso.engine import Engine
from tests.support import make_engine


def _eng() -> Engine:
    e = make_engine(llm=None, validate_signals=True, state_timeout=0)
    e.start()                    # signals are applied by the loop thread; without it nothing lands
    return e


def _plan_with_one_orphan(e) -> None:
    T.create_task(e, "root", {"name": "goal", "description": "a goal",
                              "criteria": [{"name": "c1", "description": "the one thing wanted"}]},
                  "alice")
    T.create_task(e, "kept", {"name": "kept", "description": "does the thing",
                              "criteria": [{"name": "k", "description": "the thing is done"}]},
                  "alice", parent_id="root")
    T.create_task(e, "dropped", {"name": "dropped", "description": "a subtask the goal no longer wants",
                                 "criteria": [{"name": "d", "description": "something else"}]},
                  "alice", parent_id="root")
    T.map_criterion(e, "root", "kept", "c1")     # (parent, child, criterion)


def _orphan_hole(e):
    return [h for h in T.list_holes(e)["holes"] if "no_orphan" in h["check"]]


def test_a_cancelled_child_stops_being_an_orphan():
    e = _eng()
    _plan_with_one_orphan(e)
    assert _orphan_hole(e), "precondition: the unmapped child is reported as an orphan"

    assert T.signal(e, "dropped", "CANCEL", "alice")["state"] == "CANCELLING"
    assert T.signal(e, "dropped", "CONFIRM_CANCEL", "alice")["state"] == "ABANDONED"

    assert not _orphan_hole(e), \
        "the refused child still gates the plan it left — the checks cache was never recomputed"
    e.stop()


def test_the_refusal_leaves_the_node_in_the_graph():
    """Dropping work from the plan must not drop it from the record (§15.1: nothing is deleted)."""
    e = _eng()
    _plan_with_one_orphan(e)
    T.signal(e, "dropped", "CANCEL", "alice")
    T.signal(e, "dropped", "CONFIRM_CANCEL", "alice")

    assert T.get_task(e, "dropped")["state"] == "ABANDONED"
    assert any(n["id"] == "dropped" for n in T.get_graph(e)["nodes"]), \
        "the tombstone vanished from the graph — provenance, not just the plan, was dropped"
    e.stop()
