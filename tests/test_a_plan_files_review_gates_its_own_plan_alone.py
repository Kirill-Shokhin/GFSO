"""The go on a plan file whose review the system ran turns the Level-2 gate off under that plan alone. It turned the gate
off for the whole project (`set_settings(l2_gate=0)`), so on a shared graph one split's go changed the gate of every
other goal in it (s20g1; docs/notes/STREAM_PLAN_IN_FORMAT.md G5). A file its customer wrote carries no review: its
split is gated as any other."""
from __future__ import annotations

import pytest

from gfso import tools_llm as TL
from gfso.core.types import TaskId
from gfso.decompose import artifact as A
from gfso.engine.validation import l2_gate_on
from tests.test_the_go_only_adds_to_the_plan import GOAL, _plan
from tests.test_the_mode_decides_who_holds_what import _engine, _goal


@pytest.fixture(autouse=True)
def _gate_on(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "1")


def _go_under_the_kid(review: dict, by_the_system: bool):
    e = _engine()
    _goal(e)
    text = A.render(GOAL, _plan(), review)
    if by_the_system:
        TL._planning.mark_reviewed(text)                # …as `plan` records the review it ran over this very text
    TL.auto_decompose(e, plan=text, root_id="kid")
    g = e.graph
    return e, g, g.get_task(TaskId("root")), g.get_task(TaskId("kid"))


def test_a_reviewed_file_turns_the_gate_off_under_its_own_plan_alone():
    e, g, root, kid = _go_under_the_kid({"by": "m", "gate_passed": True}, True)
    assert g.get_active_children(kid.id), "the file's plan stands under the kid"
    assert not l2_gate_on(g, kid) and not l2_gate_on(g, g.get_active_children(kid.id)[0])
    assert l2_gate_on(g, root), "the other plan of the graph keeps its gate"
    assert g.setting("l2_gate") != "0", "the project's own switch is untouched"


def test_a_file_with_no_review_is_gated_as_any_split():
    e, g, root, kid = _go_under_the_kid({}, False)
    assert l2_gate_on(g, kid)


def test_a_review_line_in_the_file_is_no_review():
    """`[review] by = …` in the agent's own file turned the gate off: only the system's own record of its review counts."""
    e, g, root, kid = _go_under_the_kid({"by": "me", "gate_passed": True}, False)
    assert l2_gate_on(g, kid)
