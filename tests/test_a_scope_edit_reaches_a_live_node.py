"""`edit_scope` on an issued node is a revision typed scope_expansion (§15.4) that takes. The door sent its cause as a
plain string, the engine's loop read it as a RevisionReason, and the re-ASSIGN was dropped on every live node with no
refusal on the log; a revision's cause is now typed at the call, where a wrong one fails loudly."""
from __future__ import annotations

import pytest

from gfso import tools_llm as TL
from gfso.core.types import State, TaskId
from tests.test_every_verb_answers import _engine, _seeded


def test_a_scope_edit_on_an_issued_node_takes_and_is_typed():
    e = _seeded(_engine())
    assert e.graph.get_task(TaskId("root")).state == State.OFFERED
    out = TL.TOOLS["edit_scope"](e, "root", ["vectors — out of this goal"], agent="agent")
    assert "error" not in out, out
    assert e.graph.get_task(TaskId("root")).spec.scope == ("vectors — out of this goal",)
    assert e.audit_log(TaskId("root"))[-1].revision_reason == "SCOPE_EXPANSION"


def test_an_untyped_cause_fails_at_the_call():
    e = _seeded(_engine())
    t = e.graph.get_task(TaskId("root"))
    with pytest.raises(TypeError, match="RevisionReason"):
        e.revise(t.id, t.spec, t.assignee, reason="scope_expansion")
