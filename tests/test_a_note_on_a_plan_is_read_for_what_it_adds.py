"""A customer's note on a plan is read for what it ADDS to the goal's demands on the result, the goal beside it: read as a
goal, «fix only this input, keep every other check» became duties no check of the work decides, and every note of a
live in_chat run came back NOT ANSWERED (haiku, 2026-11-17: undecided 0 → 2 → 5). Measured live on haiku after the
change: those notes read to none (2/2); a note adding `sub` to a regex engine read to its 2–3 duties (2/2)."""
from __future__ import annotations

from types import SimpleNamespace

from gfso.critic import runner


def _asked(**kw) -> str:
    said = {}
    llm = SimpleNamespace(complete=lambda prompt, context: said.update(prompt=prompt, context=context) or '{"gaps": []}')
    runner.goal_obligations(llm, "Write wc.py.", **kw)
    return said


def test_notes_are_read_beside_their_goal_for_what_they_add_and_a_goal_alone_as_before():
    noted = _asked(notes="Fix only the combining input; keep every other check.")
    assert "# THE GOAL" in noted["prompt"] and "Write wc.py." in noted["prompt"]
    assert "# THE CUSTOMER'S NOTES ON THE PLAN" in noted["prompt"] and "keep every other check" in noted["prompt"]
    assert "When you are given the customer's notes on a plan" in noted["context"]
    alone = _asked()
    assert "# GOAL\nWrite wc.py." in alone["prompt"] and "NOTES" not in alone["prompt"]
