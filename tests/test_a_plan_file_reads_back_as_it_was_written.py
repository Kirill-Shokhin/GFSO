"""A plan is an artifact of its own, handed between parties as a config is (the author, 2026-10-31: «передача плана должна
быть по смыслу схожей на передача .yaml … легковесной и вполне даже быть своим форматом»; «проект … может быть
следствием конкретного плана»). The file reads back exactly as it was written; it carries the goal it answers, the
executor-relative fit apart from the plan (κ is the actor's, §3.7), the checks' files once by content; a note's answer
is what changed in the plan; the go builds the project from the file as it stands, the customer's plan from then on."""
from __future__ import annotations

import json
import tomllib
from types import SimpleNamespace

import pytest

from gfso import tools as T, tools_llm as TL
from gfso.core.types import Mode, TaskId
from gfso.decompose import artifact as A, planning as P
from tests.support import criterion
from tests.test_the_mode_decides_who_holds_what import _engine

GOAL = "Build ./wc2.\nIt counts lines, words and bytes; a missing file exits 1.\n"
FILE = "int main(void) {\n\treturn 0;\n}\n"
ODD = "a\x7fb\x01c"                 # characters JSON leaves bare (DEL) or a literal string may not hold


def _plan() -> dict:
    probe = lambda c, **kw: {"behaviour": "b", "command": c, "expect": "OK\n2", **kw}  # noqa: E731
    return {"name": "wc2", "root_criteria": [{"name": "counts", "description": "counts match wc",
                                              "check": [probe("./wc2 {inputs}/a.c", inputs={"a.c": FILE})]}],
            "subtasks": [{"id": "core", "name": "counting", "description": "it's the counter",
                          "criteria": [{"name": "c1", "description": ODD, "depends_on": "io",
                                        "check": [probe("cc {inputs}/a.c", inputs={"a.c": FILE}, exact=True)]}],
                          "volume": "~200 lines", "fits_one_session": True, "writes": ["wc.c"], "runs": []},
                         {"id": "io", "name": "files", "description": "opens files\r\nquotes '''", "criteria": [],
                          "writes": [], "runs": ["root.core"]}],
            "mappings": [{"criterion": "counts", "child_id": "core"}],
            "deps": [{"from": "io", "to": "core", "glue": "open_file()"}],
            "accepted_risks": [{"item": "f", "p": 0.05, "impact": "low"}],
            "denial": {"p": 0.1, "justification": "j"}, "scope": [], "whole_volume": "~400 lines",
            "whole_fits_one_session": False}


def test_the_file_reads_back_exactly_as_written():
    review = {"by": "m", "gate_passed": True, "semantic_covered": False,
              "undecided_obligations": [{"obligation": "o", "admits": "a"}], "conflicts": []}
    notes = [{"note": "add -l\nplease", "by": "m", "answer": "part added: l"}]
    got = A.parse(A.render(GOAL, _plan(), review, notes, executor="claude-haiku-5-5"))
    assert got == {"goal": GOAL, "spec": _plan(), "review": review, "notes": notes, "executor": "claude-haiku-5-5"}


def test_the_fit_marks_and_the_checks_files_sit_apart_from_the_plan():
    doc = tomllib.loads(A.render(GOAL, _plan()))
    assert doc["format"] == A.FORMAT and doc["goal"] == GOAL
    assert not any(k in s for s in doc["plan"]["subtasks"] for k in ("volume", "fits_one_session"))
    assert "whole_volume" not in doc["plan"] and doc["fit"]["whole_volume"] == "~400 lines"
    assert doc["fit"]["parts"][0] == {"id": "core", "volume": "~200 lines", "fits_one_session": True}
    (h,) = doc["inputs"]                       # one file, used twice, written once
    assert doc["inputs"][h] == FILE and doc["plan"]["root_criteria"][0]["check"][0]["inputs"] == {"a.c": h}


def test_a_file_of_another_format_is_refused():
    with pytest.raises(ValueError, match="not a gfso-plan/1"):
        A.parse('format = "x"\n')


def test_a_notes_answer_is_what_the_round_changed_in_the_plan():
    old, new = _plan(), _plan()
    new["subtasks"].append({"id": "l", "name": "-l option", "criteria": []})
    new["subtasks"][0]["criteria"][0]["description"] = "sharper"
    new["subtasks"][0]["criteria"].append({"name": "c2", "description": "d"})
    new["mappings"].append({"criterion": "counts", "child_id": "l"})
    new["deps"] = []
    assert P.changes(old, new) == ["part added: l — -l option", "core: criterion added: c2",
                                   "core: criterion changed: c1", "mapping added: counts ← l",
                                   "dependency removed: io → core"]
    assert P.changes(old, _plan()) == ["the round folded, but no part, criterion, mapping, dependency or risk differs"]


def test_the_go_builds_the_project_from_the_file_as_it_stands(monkeypatch, tmp_path):
    seen = {}

    def built(engine, request, root_id, **kw):
        seen.update(request=request, spec=kw["spec"])
        T.TOOLS["create_task"](engine, root_id, {"description": request, "criteria": [criterion("g", "G holds")]})
        return SimpleNamespace(root_id=TaskId(root_id), holes=[], stats={}, d_md="", undecided_obligations=[], note="")
    monkeypatch.setattr(TL, "decompose_into", built)
    path = tmp_path / "p.gfso"
    path.write_text(A.render(GOAL, _plan()), encoding="utf-8")
    e = _engine(Mode.AUTO)
    out = TL.auto_decompose(e, plan=str(path))
    assert seen == {"request": GOAL, "spec": _plan()} and e.users_plan() is True
    assert "error" not in out, out      # a plan handed in calls no model: none answering is no provider's fault


def test_the_go_refuses_a_second_source_of_the_plan_or_another_goal(tmp_path):
    text = A.render(GOAL, _plan())
    with pytest.raises(ValueError, match="not both"):
        TL.auto_decompose(_engine(Mode.AUTO), plan=text, spec=_plan())
    with pytest.raises(ValueError, match="differs from the goal"):
        TL.auto_decompose(_engine(Mode.AUTO), "another goal", plan=text)


def test_the_plan_verbs_need_no_project():
    assert {"plan", "refine_plan"} <= T.PROJECTLESS_VERBS and {"plan", "refine_plan"} <= set(TL._RAW_TOOLS)
