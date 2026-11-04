"""The customer must read the plan whole, and the file lies in gfso's home, outside the person's folder: a fresh client's
auto mode stopped there on a prompt, before the go, with no one present (measured, 2026-11-05). The answer holds the
text beside the path; the file stays what a note and the go take. The verbs run for real, only the model is faked."""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp.shared.memory import create_connected_server_and_client_session

from gfso import tools_llm as TL
from gfso.api.server import create_app
from gfso.config import agent_id
from gfso.decompose import NoPlan, artifact as A, planning
from gfso.decompose.build import build_graph_live
from gfso.mcp.server import create_server
from tests.support import make_engine
from tests.test_the_go_only_adds_to_the_plan import GOAL, _plan


def _authored(e, request, root_id, **_):
    """What the authoring model leaves on the scratch graph: the plan, built."""
    return SimpleNamespace(root_id=build_graph_live(_plan(), request, e, root_id=root_id, assignee=agent_id())[1])


@pytest.fixture
def home(monkeypatch, tmp_path):
    """The state directory, here; no model anywhere."""
    monkeypatch.setattr(planning, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(TL, "_PLANNING", {})
    monkeypatch.setattr(planning._decompose, "default_llm", lambda *a, **k: SimpleNamespace(calls=[]))
    monkeypatch.setattr(planning._decompose, "decompose_into", _authored)
    monkeypatch.setattr(planning._decompose, "refine_with", lambda *a, **k: (False, None, []))
    monkeypatch.setattr(planning, "_review", lambda *a, **k: {"by": "m"})
    return tmp_path


def _written(verb: str) -> dict:
    return (TL.plan(make_engine(), GOAL) if verb == "plan"
            else TL.refine_plan(make_engine(), TL.plan(make_engine(), GOAL)["path"], "a note"))


def _bytes(out: dict) -> bytes:
    with open(out["path"], "rb") as f:
        return f.read()


@pytest.mark.parametrize("verb", ["plan", "refine_plan"])
def test_the_answer_holds_the_files_text_byte_for_byte(home, verb):
    out = _written(verb)
    assert out["text"].encode() == _bytes(out)
    assert out["chars"] == len(out["text"])


def test_the_refine_answer_holds_what_the_round_changed(home):
    assert A.parse(_written("refine_plan")["text"])["notes"][-1]["note"] == "a note"


@pytest.mark.parametrize("verb", ["plan", "refine_plan"])
def test_a_plan_past_the_limit_is_answered_by_its_path_and_one_at_it_by_its_text(home, monkeypatch, verb):
    chars = _written(verb)["chars"]
    monkeypatch.setattr(TL, "_PLANNING", {})
    monkeypatch.setattr(TL, "PLAN_TEXT_MAX", chars)
    assert "text" in _written(verb)
    monkeypatch.setattr(TL, "_PLANNING", {})
    monkeypatch.setattr(TL, "PLAN_TEXT_MAX", chars - 1)
    out = _written(verb)
    assert "text" not in out and A.parse(_bytes(out).decode())["goal"] == GOAL
    assert "`path`" in out["how_to_read"], "where to read it, said in the answer that has no text"


def test_a_call_joining_one_under_way_and_one_reading_it_after_get_the_text(home, monkeypatch):
    calls, release = [], threading.Event()

    def slow(*a, **k):
        calls.append(1)
        release.wait(5)
        return _authored(*a, **k)
    monkeypatch.setattr(planning._decompose, "decompose_into", slow)
    e = make_engine()
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(TL.plan, e, GOAL)
        while not calls:
            time.sleep(0.01)
        second = pool.submit(TL.plan, e, GOAL)
        release.set()
        a, b = first.result(), second.result()
    assert a == b == TL.plan(e, GOAL) and a["text"].encode() == _bytes(a) and len(calls) == 1


def test_a_refused_plan_names_no_path_and_holds_no_text(home, monkeypatch):
    monkeypatch.setattr(planning._decompose, "decompose_into",
                        lambda *a, **k: (_ for _ in ()).throw(NoPlan("no criterion", [])))
    out = TL.plan(make_engine(), GOAL)
    assert "error" in out and not {"path", "text"} & set(out)


def test_the_go_reads_the_file_and_not_the_text_it_was_answered(home):
    out = _written("plan")
    edited = A.render("Another goal.\n", _plan())
    with open(out["path"], "wb") as f:
        f.write(edited.encode())
    assert TL._the_go(make_engine(), out["path"], "", None)[0] == "Another goal.\n"


def _by_mcp(e, *args):
    """Each call's answer as a client of the MCP door reads it: said first, the text last, on a session of its own."""
    async def go():
        got = []
        async with create_connected_server_and_client_session(create_server(e)._mcp_server) as session:
            for verb, kw in args:
                got.append(await session.call_tool(verb, kw))
        return got
    return anyio.run(go)


def test_the_mcp_door_answers_with_the_text_and_a_second_call_still_says(home):
    e = make_engine()
    (first, joined) = _by_mcp(e, ("plan", {"request": GOAL}), ("plan", {"request": GOAL}))
    for out in (json.loads(first.content[0].text), json.loads(joined.content[0].text)):
        assert out["text"].encode() == _bytes(out)
        keys = list(out)
        assert keys[0] == "say" and keys[-1] == "text"


def test_the_mcp_door_answers_a_refine_with_the_text(home):
    e = make_engine()
    path = TL.plan(e, GOAL)["path"]
    (out,) = _by_mcp(e, ("refine_plan", {"plan": path, "note": "a note"}))
    out = json.loads(out.content[0].text)
    assert out["text"].encode() == _bytes(out) and A.parse(out["text"])["notes"][-1]["note"] == "a note"


def test_the_http_door_answers_with_the_text(home):
    out = TestClient(create_app(make_engine())).post("/api/run/plan", json={"request": GOAL}).json()
    assert out["text"].encode() == _bytes(out)
