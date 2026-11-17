"""What the person must hear before the work runs reached them only in the client's words: the plan (what it splits into,
what its repair took back, what stays open), where the work runs, what of their repository the agents lack, the goal the
work is held to. The system now shows the plan on the project's page when it is written, records the go's facts where
the page reads them, and keeps the switches that are the person's (the mode, `in_chat`) to the person's own page."""
from __future__ import annotations


from fastapi.testclient import TestClient
import pytest

from gfso import config, serverctl, signin, tools_llm as TL
from gfso.api.server import create_app
from gfso.core.types import Mode
from gfso.decompose import artifact as A
from gfso.mcp.server import _with_ui_link
from gfso.runtime import ProjectRegistry
from tests.support import carried_by_the_system, criterion, make_engine, written
from tests.test_a_plan_s_answer_holds_its_text import home  # noqa: F401 — the fixture
from tests.test_a_plan_the_go_refuses_says_so import _by_build
from tests.test_the_go_only_adds_to_the_plan import GOAL, _plan, go  # noqa: F401 — `go` is a fixture
from tests.test_the_mode_decides_who_holds_what import _engine

KEYS = {"path", "written_at", "goal", "executor", "parts", "root_criteria", "deps", "open", "taken_back",
        "refused_by_the_go", "undecided", "notes", "documents"}


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    monkeypatch.setenv("GFSO_STORAGE", "memory")
    reg = ProjectRegistry()
    return reg.engine(), TestClient(create_app(reg.engine(), registry=reg))


def test_a_written_plan_is_told_on_the_feed_and_read_by_the_page(home, monkeypatch, tmp_path):
    """CONTROL: drop `_kept.wrote` in `_shown` and the read answers {}; drop the frame's branch and no `plan_written`."""
    e, client = _client(monkeypatch, tmp_path)
    assert client.get("/api/plan").json() == {}
    with client.websocket_connect("/ws/events") as ws:
        out = written(TL.plan, e, GOAL)
        e.emit_info("end", "of this test's frames")      # …read up to it: a frame never sent would block the read
        frames = []
        while (frames := frames + [ws.receive_json()])[-1].get("source") != "end":
            pass
    assert [f["msg"] for f in frames if f["type"] == "plan_written"] == [f"the plan is written: {out['path']}"]
    got = client.get("/api/plan").json()
    assert set(got) == KEYS and got["path"] == out["path"] and got["goal"] == GOAL and got["documents"] == []
    assert [p["id"] for p in got["parts"]] == [s["id"] for s in _plan()["subtasks"]]
    assert all(set(p) == {"id", "name", "description", "criteria", "split_after"} for p in got["parts"])
    assert got["root_criteria"] == [c["name"] for c in _plan()["root_criteria"]] and got["refused_by_the_go"] == []
    assert got["deps"] == [[d["from"], d["to"]] for d in _plan()["deps"]]
    with open(out["path"], "w", encoding="utf-8") as f:
        f.write("not a plan file [")
    assert client.get("/api/plan").json() == {}, "a kept file that no longer reads is no plan"   # CONTROL: drop the try
    TL._kept.forget_project(e.project_name)
    assert client.get("/api/plan").json() == {}, "a deleted project shows no plan"


@pytest.fixture
def opened(monkeypatch):
    """The pages opened, none really: windows allowed, the server on loopback, nothing opened yet in this process."""
    got = []
    monkeypatch.setattr(serverctl, "open_outside", got.append)
    monkeypatch.setattr(serverctl, "_OPENED", set())
    monkeypatch.setenv("GFSO_OPEN_PAGE", "1")
    monkeypatch.delenv("GFSO_NO_WINDOWS", raising=False)
    return got


def test_under_auto_the_page_opens_once_when_the_plan_is_written(home, opened):
    """The go opens the page under AUTO; the plan before it is the person's to read, so its write opens it too, through
    the same door — once: the page re-reads itself, and a plan, its note and the go opened three tabs. CONTROL: drop
    `open_the_page` in `_shown` and nothing opens; drop the `_OPENED` check and the second write opens a second tab."""
    written(TL.plan, make_engine(), GOAL)
    assert opened == [], "with no mode the go opens nothing, nor does the plan"
    e = carried_by_the_system(make_engine())
    written(TL.plan, e, GOAL + "Under AUTO.\n")         # …another request: the same one answers its kept writing
    written(TL.plan, e, GOAL + "Under AUTO, again.\n")
    assert opened == [serverctl.ui_link(e.project_name)]
    out = _with_ui_link("auto_decompose", {"root_id": "root", "goal_as_given": GOAL}, e.project_name, e)
    assert "page_opened" not in out and "open in their browser" not in out["say"] and out["ui"] in out["say"]


def test_with_no_windows_the_page_is_not_said_open(opened, monkeypatch):
    """`GFSO_NO_WINDOWS` opened nothing, and the go said "it is open in their browser now". CONTROL: drop
    `windows_allowed()` in `open_the_page` and it is said open."""
    monkeypatch.setenv("GFSO_NO_WINDOWS", "1")
    assert serverctl.open_the_page("p") is False
    out = _with_ui_link("auto_decompose", {"root_id": "root", "goal_as_given": GOAL}, "p", _engine(Mode.AUTO))
    assert "page_opened" not in out and "open in their browser" not in out["say"] and opened == []


def _noted(answer: str, spec=None) -> str:
    return A.render(GOAL, spec or _plan(), {"by": "m", "gate_passed": True}, notes=[{"note": "n", "answer": answer}])


def test_a_second_round_over_an_answered_note_is_refused_unless_the_go_refuses_the_file(home):
    """Three rounds of notes on a plan with nothing undecided: 8:28 of a 17-minute run, and worse (2026-11-09).
    CONTROL: return None first in `_answered` and the first assertion is red."""
    e = make_engine()
    no = TL.TOOLS["refine_plan"](e, _noted("what changed"), "another point")
    assert no.get("refused") and "answered note" in no["error"] and "plan(request)" in no["error"], no
    assert "path" in written(TL.refine_plan, e, _noted("x\nNOT ANSWERED — still open: y"), "sharper"), "not spent"
    assert "path" in written(TL.refine_plan, e, _noted("what changed", _by_build()), "the go's points"), "go refuses"


def _worked(caller):
    e = _engine()
    TL.TOOLS["create_task"](e, "root", {"description": "goal", "criteria": [criterion("a", "A")]}, assignee="user")
    assert e.all_tasks()
    token = config.CALLER.set(caller)
    try:
        return e, TL.TOOLS["set_mode"](e, mode="solo", user_said="the person wants solo")
    finally:
        config.CALLER.reset(token)


def test_once_there_is_work_the_mode_is_the_persons_page_move_not_the_agents():
    """An AUTO customer that met a stall passed the person's words itself and took the nodes (measured live).
    CONTROL: return None first in `_not_the_persons` and the standing agent's switch goes through."""
    _, out = _worked(config.STANDING)
    assert out.get("refused") and "the person's own choice" in out["error"] and "gfso ui" in out["error"], out
    _, out = _worked(signin.PAGE)
    assert "the person's own choice" not in str(out.get("error")), out


def test_the_go_records_where_it_runs_what_is_left_out_and_the_goal_as_given(go):
    """Said only if the client read `list_agents` and named `not_imported`: the go's answer and the graph read now carry
    both, and the goal verbatim, by the same reading; the go's `say` leads with the host. CONTROL: publish no `on_host`
    in `publish_the_workforce` and every assertion on it is red."""
    e = _engine(Mode.AUTO)
    TL._delegation().publish_the_workforce(e, {f"exec-{n}": {"kind": "llm-executor", "project": "p"} for n in (1, 2)})
    out = TL.auto_decompose(e, plan=A.render(GOAL, _plan(), {"by": "m", "gate_passed": True}))
    said = {"runs_on_host": True, "not_imported": [], "goal_as_given": GOAL}
    assert {k: out[k] for k in said} == said
    assert {k: TL.TOOLS["get_graph"](e)["mode"][k] for k in said} == said
    assert _with_ui_link("auto_decompose", out, "p", e)["say"].startswith("First: this project's work runs on this machine")


def test_where_the_work_runs_is_on_the_graph_before_the_go():
    """The page says the work runs on this machine as soon as the roster says so, not only from the go's record.
    CONTROL: publish no `on_host` in `publish_the_workforce` and the first assertion is red."""
    e = _engine(Mode.AUTO)
    for execution, on_host in ((None, True), ("default", False)):
        TL._delegation().publish_the_workforce(e, {"exec-1": {"kind": "llm-executor", "project": "p",
                                                              **({"execution": execution} if execution else {})}})
        assert TL._tools.graph_read(e)["mode"]["runs_on_host"] is on_host


def test_where_the_work_runs_is_said_with_no_mode_too():
    """A project with no mode, its executors on this machine: the graph's `heard` says so (ui critic, 2026-11-17).
    CONTROL: drop `heard` from `graph_read` and it is red."""
    e = _engine(None)
    TL._delegation().publish_the_workforce(e, {"exec-1": {"kind": "llm-executor", "project": "p"}})
    assert TL._tools.graph_read(e)["mode"] is None and TL._tools.graph_read(e)["heard"]["runs_on_host"] is True


@pytest.mark.parametrize("mode", [None, Mode.SOLO, Mode.SEMI, Mode.AUTO])
def test_every_fresh_go_says_where_it_runs_and_what_its_copy_lacks(mode):
    """Outside AUTO the go said nothing, and the struck instruction was the only carrier of both lines (critic).
    CONTROL: drop the `elif` branch in `_link_and_say` and every mode but AUTO is red."""
    out = _with_ui_link("auto_decompose", {"root_id": "root", "runs_on_host": True, "not_imported": ["a.txt"],
                                           "goal_as_given": GOAL}, "p", _engine(mode))
    assert out["say"].startswith(TL.ON_HOST) and "a.txt" in out["say"] and "goal_as_given" in out["say"]


def test_the_plan_says_where_its_work_will_run(home):
    """CONTROL: drop the `runs_on_host` line in `_shown` and the first assertion is red."""
    e = _engine()
    TL._delegation().publish_the_workforce(e, {"exec-1": {"kind": "llm-executor", "project": "p"}})
    assert written(TL.plan, e, GOAL)["say"].startswith(TL.ON_HOST)
    TL._delegation().publish_the_workforce(e, {"exec-1": {"kind": "llm-executor", "project": "p", "execution": "d"}})
    assert not written(TL.plan, e, GOAL + "In a container.\n")["say"].startswith(TL.ON_HOST)


def test_the_page_reads_the_goals_documents_as_composed_not_split_off_its_text(home, monkeypatch, tmp_path):
    """A document's own `## ` heading reads as a boundary in the goal's text: the page gets the list the goal was
    composed from, refined plans of that goal included. CONTROL: drop `_kept.keep_documents` in `plan` and it is []."""
    doc = {"path": "spec.md", "text": "The spec.\n\n## Its own heading\n\nMore of it.\n"}
    monkeypatch.setattr(TL, "_documents_named", lambda engine, request: [doc])
    e, client = _client(monkeypatch, tmp_path)
    out = written(TL.plan, e, GOAL)
    got = client.get("/api/plan").json()
    assert got["documents"] == [doc] and got["goal"].startswith(GOAL) and "## Its own heading" in got["goal"]
    written(TL.refine_plan, e, out["path"], "a note")
    assert client.get("/api/plan").json()["documents"] == [doc], "a refined plan of the goal carries them too"
