"""The rework bound is ONE number, whichever door creates the node.

It was four: `core.types.primitives.Task`, `core.types.effects.MutateGraph`, the storage DDL, and
`Engine.assign_task`'s own `if max_iterations is None` — and after the default moved 3 → 12 on
2026-09-20, two of them still said 3. The consequential one was `assign_task`: it is the door
`create_task` uses and the door `auto_decompose` authors the ROOT through, so the node the raise was
made for — a root that escalates on exhausted rework — kept the old bound while the change was
reported as shipped. A rule spelled in several places is a rule whose value depends on which door
wrote the row (§14.4 Inv-1: the bound is a packet field, one contract).
"""
from __future__ import annotations

import gfso.tools as T
from gfso.core.types import DEFAULT_MAX_ITERATIONS
from gfso.core.types.effects import MutateGraph
from gfso.core.types.primitives import Task
from tests.support import make_engine


def _engine():
    e = make_engine(None, llm=None, validate_signals=True, state_timeout=0)
    e.start()
    return e


def test_every_door_that_creates_a_node_uses_the_same_bound():
    e = _engine()
    try:
        # The agent's door.
        T.create_task(e, "hand", {"description": "made by hand",
                                  "criteria": [{"name": "c", "description": "d"}]})
        # The engine's own convenience, which is also what authors a root. It hangs under `hand`
        # because a project has exactly one parentless node; the bound is a field of the CONTRACT
        # and does not depend on where in the tree the door was pointed.
        e.assign_task("authored", e.get_task("hand").spec, "agent", parent_id="hand")
        e.wait_idle()
        for tid in ("hand", "authored"):
            assert e.get_task(tid).max_iterations == DEFAULT_MAX_ITERATIONS, (
                f"{tid} got {e.get_task(tid).max_iterations}, not the one default")
    finally:
        e.stop()


def test_the_types_agree_with_the_constant():
    assert Task.__dataclass_fields__["max_iterations"].default == DEFAULT_MAX_ITERATIONS
    assert MutateGraph.__dataclass_fields__["max_iterations"].default == DEFAULT_MAX_ITERATIONS
