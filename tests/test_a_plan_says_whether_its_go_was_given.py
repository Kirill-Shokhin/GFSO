"""The plan last written says whether a go was given on it (`written_plan.given_at`): None until a go on THIS file, set
by it, None again when a new file is written — so the page shows a plan awaiting its go beside a standing graph, and
guesses nothing from times or goal text (ui, 2026-11-19)."""
from __future__ import annotations

from gfso import tools_llm as TL
from gfso.core.types import Mode
from tests.test_a_solo_chat_writes_its_own_plan_and_the_person_gives_the_go import ASKED, _filled, no_model  # noqa: F401
from tests.test_the_mode_decides_who_holds_what import _engine


def test_the_go_marks_its_file_and_a_new_file_starts_unmarked(no_model):
    e = _engine(Mode.SOLO)
    text = _filled(TL.plan(e, ASKED)["text"])
    TL.plan(e, plan=text)
    assert TL.written_plan(e.project_name, e)["given_at"] is None
    TL.auto_decompose(e, plan=text, user_said="да, делай")
    assert TL.written_plan(e.project_name, e)["given_at"] is not None
    TL.plan(e, plan=text.replace("prints the line count", "prints the count of lines"))
    assert TL.written_plan(e.project_name, e)["given_at"] is None
