"""A validator is handed what an outside critic is handed first: the goal in the person's own words — on every node, a
part reading its nearest whole's, not only where `answers_the_persons_words` is judged — and it is asked the critic's
question before the criteria one by one. Without the words a part's validator read the planner's text as the goal
(critic over the rewrite, 2026-11-27); the author: «сравнивать надо по промптам а не по результатам прогонов».

CONTROL: return "" where no criterion carries `answers_the_persons_words` (`packets._persons_words`) and the first
test goes red; stop at the node itself (no walk up) and the part's case goes red; read every act, not the person's
(`PERSONS_ACTS`), and both go red."""
from __future__ import annotations

from pathlib import Path

import pytest

import gfso.tools as T
from gfso.core.types import TaskId
from gfso.packets import validator_packet
from tests.support import REGISTER, criterion, make_engine

WORDS = "сделай так чтобы отчёт читался с телефона"


@pytest.fixture
def e(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "the goal", "criteria": [criterion("g")]}, assignee="me")
    T.decompose(e, "root", [{"task_id": "root.a", "spec": {"description": "a part, as the planner wrote it",
                                                            "criteria": [criterion("a_ok")]},
                             "assignee": "me", "covers": ["g"]}], accepted_risks=REGISTER)
    e.wait_idle()
    e.hear("root", "request", WORDS)
    e.hear("root", "plan", "PLANNERS-TEXT the agreed plan")          # …the agent's, never the person's
    e.hear("root.a", "checker", "validator x appointed")             # …the system's: no stop for the walk
    yield e
    e.stop()


@pytest.mark.parametrize("node", ["root", "root.a"])
def test_the_persons_words_reach_a_validator_with_no_criterion_of_theirs(e, node):
    text = validator_packet(e, e.graph.get_task(TaskId(node)), "built it", ".")
    assert "the goal this delivery serves" in text and WORDS in text, text
    assert "PLANNERS-TEXT" not in text and "validator x appointed" not in text, "a non-person act printed as the goal"


def test_the_validator_is_asked_the_whole_against_the_goal_first():
    prompt = (Path(__file__).parents[1] / "gfso" / "mcp" / "prompts" / "validator.md").read_text(encoding="utf-8")
    assert "not for exploring beyond the contract" not in prompt, "the line forbidding the critic's method is back"
    whole, each = prompt.index("**The whole, against the goal"), prompt.index("**For each criterion, in order")
    assert prompt.index("**Does the delivery answer the goal?**") < whole < each, "the goal is not asked first"
