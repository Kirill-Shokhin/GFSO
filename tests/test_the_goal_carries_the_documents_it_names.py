"""A goal's request that names a document in the place its work will be done carries that document in its contract.

The plan author, its auditors and the root's reviewer read only text; a request saying "implement what prompt.md
specifies" reached them as its summary, and the plan contradicted the statement the root's executor read in its
workdir (spreadsheet_engine, AUTO haiku — EVIDENCE_LOG §13.38).
"""
from __future__ import annotations

import gfso.tools_llm as TL
from gfso.core.types import TaskId
from gfso.roster import AgentRegistry
from tests.support import REGISTER, criterion, make_engine

_PLAN = {"name": "g", "root_criteria": [criterion("g", "G holds")],
         "subtasks": [{"id": "a", "name": "a", "description": "part a", "criteria": [criterion("a_ok", "a holds")]}],
         "mappings": [{"criterion": "g", "child_id": "a"}], "deps": [], "accepted_risks": REGISTER, "scope": []}


def _goal(tmp_path, monkeypatch, request: str, roles=(("exec-1", "llm-executor", "base", "p"),)) -> str:
    """The root's contract after `auto_decompose(request)` in project p, with `roles` (id, kind, dir, project)
    registered; each dir holds a prompt.md saying whose it is."""
    reg = AgentRegistry(str(tmp_path / "roster.json"))
    for aid, kind, d, proj in roles:
        (tmp_path / d).mkdir(exist_ok=True)
        (tmp_path / d / "prompt.md").write_text(f"THE STATEMENT IN {d}", encoding="utf-8")
        reg.register(aid, kind, workdir=str(tmp_path / d), project=proj)
    (tmp_path / "outside.md").write_text("A FILE OUTSIDE EVERY BASE", encoding="utf-8")
    monkeypatch.setattr(TL, "_roster", lambda engine=None: reg)
    e = make_engine(validate_signals=True, state_timeout=0)
    e.project_name = "p"
    e.start()
    TL.auto_decompose(e, request.format(t=tmp_path), spec=dict(_PLAN))
    return e.graph.get_task(TaskId("root")).spec.description


def test_a_named_document_in_the_work_place_is_in_the_goals_contract(tmp_path, monkeypatch):
    desc = _goal(tmp_path, monkeypatch, "Implement what prompt.md specifies; read {t}/base/prompt.md in full.")
    assert desc.count("THE STATEMENT IN base") == 1, "one document named twice is carried once"


def test_only_this_projects_place_is_read(tmp_path, monkeypatch):
    desc = _goal(tmp_path, monkeypatch, "See {t}/theirs/prompt.md and {t}/outside.md and nothing.md.",
                 roles=(("exec-1", "llm-executor", "base", "p"), ("exec-9", "llm-executor", "theirs", "q")))
    assert "THE DOCUMENTS THIS REQUEST NAMES" not in desc


def test_an_unscoped_role_is_no_place_of_this_project(tmp_path, monkeypatch):
    desc = _goal(tmp_path, monkeypatch, "Read prompt.md in full.", roles=(("x-1", "llm-executor", "stranger", None),))
    assert "THE DOCUMENTS THIS REQUEST NAMES" not in desc


def test_the_name_met_again_is_the_document_already_carried(tmp_path, monkeypatch):
    desc = _goal(tmp_path, monkeypatch, "Implement {t}/a/prompt.md; read prompt.md in full.",
                 roles=(("exec-1", "llm-executor", "a", "p"), ("exec-2", "llm-executor", "b", "p")))
    assert "THE STATEMENT IN a" in desc and "THE STATEMENT IN b" not in desc


def test_a_validators_place_is_the_works_place_too(tmp_path, monkeypatch):
    desc = _goal(tmp_path, monkeypatch, "Read prompt.md in full.", roles=(("p-val", "llm-validator", "base", "p"),))
    assert "THE STATEMENT IN base" in desc


class _Reader:
    """A read-only run of the work's place that names one file — the plan author's own read is what is tested."""
    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None, max_turns=None):
        assert set(allowed_tools) == {"Read", "Glob", "Grep"}, "the place is read, never written"
        return '```json\n{"files": ["prompt.md", "Makefile"]}\n```'


def test_a_plan_the_system_writes_carries_the_files_its_place_names(tmp_path, monkeypatch):
    """A customer's summary named no file, and the plan's author never saw the binary, its input or its output
    (GB_sql_database_tmu9cb784): the place is read before the plan, and what it names is carried verbatim."""
    reg = AgentRegistry(str(tmp_path / "roster.json"))
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "prompt.md").write_text("THE STATEMENT IN base", encoding="utf-8")
    (tmp_path / "base" / "Makefile").write_text("THE BUILD IN base", encoding="utf-8")
    reg.register("exec-1", "llm-executor", workdir=str(tmp_path / "base"), project="p")
    monkeypatch.setattr(TL, "_roster", lambda engine=None: reg)
    monkeypatch.setattr(TL, "llm_factory", lambda model=None: _Reader())
    e = make_engine(validate_signals=True, state_timeout=0)
    e.project_name = "p"
    e.record_llm_usage = lambda *a, **k: None
    carried = TL._named_documents(e, "a summary " + TL._work_place_documents(e, "a summary", "m"))
    assert "THE STATEMENT IN base" in carried and "THE BUILD IN base" in carried, "a build file without a suffix too"
