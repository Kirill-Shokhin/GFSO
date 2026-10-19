"""A refusal's advice is a path the engine admits: a NEW split starts by `decompose`, never by one `create_task`.

Critic r12 over the admission-as-one-act stack: the texts an agent reads — the one-root refusal, the bare-ASSIGN
refusal and `create_task`'s own description — offered `create_task(parent_id=…, covers=[…])` as the way to put a
node under a parent, while a parent's FIRST child is always refused: one child alone carries no split register, and
the admission gates on it (§11.5, CHECK-4). `create_task` only adds a child to a split that already stands.
"""
from __future__ import annotations

import gfso.tools as T
from gfso.core.types import TaskId
from gfso.engine.validation import child_not_admitted
from tests.support import REGISTER, criterion, make_engine


def _root(e):
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("a", "A"), criterion("b", "B")]}, "agent")
    e.wait_idle()


def _child(k, c):
    return {"task_id": k, "spec": {"description": f"part {k}", "criteria": [criterion(f"{k}_ok", k)]},
            "assignee": "agent", "covers": [c]}


def test_the_one_root_refusal_starts_the_split_by_decompose_and_its_advice_is_admitted():
    e = make_engine()
    e.start()
    _root(e)
    msg = T.create_task(e, "x", {"description": "another part", "criteria": [criterion("x_ok", "X")]})["error"]
    assert msg.index("decompose(") < msg.index("create_task(")
    # the advice, followed in its order: the split admitted whole, then one child added to the split that stands
    T.decompose(e, "root", [_child("x", "a"), _child("y", "b")], accepted_risks=REGISTER)
    out = T.create_task(e, "z", {"description": "one more", "criteria": [criterion("z_ok", "Z")]},
                        parent_id="root", covers=["b"])
    e.wait_idle()
    assert "error" not in out and e.graph.get_task(TaskId("z")) is not None
    e.stop()


def test_a_first_child_through_create_task_is_refused_toward_decompose():
    e = make_engine()
    e.start()
    _root(e)
    out = T.create_task(e, "x", {"description": "part", "criteria": [criterion("x_ok", "X")]},
                        parent_id="root", covers=["a", "b"])
    assert "decompose" in out["error"] and "create_task(" not in out["error"]
    assert e.graph.get_task(TaskId("x")) is None
    e.stop()


def test_the_bare_assign_refusal_reserves_create_task_for_a_standing_split():
    e = make_engine()
    e.start()
    _root(e)
    msg = child_not_admitted(e.graph, "root", "x")
    assert msg.index("decompose") < msg.index("create_task(") and "already stands" in msg
    e.stop()


def test_create_tasks_description_reserves_parent_and_covers_for_a_standing_split():
    doc = T.create_task.__doc__
    assert "already stands" in doc and "decompose(parent, children, accepted_risks=" in doc
    assert "MANDATORY on a node you" not in doc
