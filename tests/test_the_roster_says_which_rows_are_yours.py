"""The roster is server-wide by design, and two doors read it as a leak.

`list_agents` is deliberately not scoped by project -- the answer says so in as many words, and the
reason is real: the roster IS one shared file, and a caller whose executor has no validator of its
own inherits one from it. Wave 26 (2026-09-06) still filed it twice: `project=w26-http` came back
with twenty-five roles across seventeen other projects, absolute workdirs and all.

That is not an isolation defect and this does not make it one. What was missing is the reading aid
the verb's own docstring promises ("both are about the READING, not about isolation"): nothing told a
caller WHICH rows were theirs, and `match=` only helps if you happened to name your roles with a
prefix. Roles carry their project, so the ordering can.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

import gfso.tools_llm as TL
from tests.support import make_engine

_ROSTER = {
    "theirs-val": {"kind": "llm-validator", "model": "sonnet", "workdir": "w", "project": "theirs"},
    "mine-val": {"kind": "llm-validator", "model": "sonnet", "workdir": "w", "project": "mine"},
    "shared-val": {"kind": "llm-validator", "model": "sonnet", "workdir": "w"},
}


@pytest.fixture
def roster(monkeypatch):
    p = Path(tempfile.mkdtemp()) / "agents.json"
    p.write_text(json.dumps(_ROSTER), encoding="utf-8")
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(p))
    return p


def _read(roster, project):
    e = make_engine()
    e.project_name = project
    return TL.list_agents(e)


def test_your_own_roles_are_named(roster):
    assert _read(roster, "mine")["yours"] == ["mine-val"]


def test_and_sorted_first(roster):
    assert list(_read(roster, "mine")["agents"])[0] == "mine-val"


def test_the_shared_roster_is_still_whole(roster):
    """The boundary is not moved: everyone's roles are still returned, because that is what the
    roster IS. Hiding them would break the inheritance the verb exists to make visible."""
    out = _read(roster, "mine")
    assert set(out["agents"]) == set(_ROSTER)
    assert out["total"] == 3
    assert "server-wide" in out["scope"]


def test_a_project_with_no_roles_of_its_own_says_so(roster):
    out = _read(roster, "nobody")
    assert out["yours"] == []
    assert set(out["agents"]) == set(_ROSTER), "still whole, still shared"


def test_the_roster_reads_without_a_graph(roster):
    """It is a SERVER fact, not a project one, and one caller reads it with no engine at all."""
    assert TL.list_agents(None)["yours"] == []
