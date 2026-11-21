"""The customer must read the plan whole, and the file lies in gfso's home, outside the person's folder: a fresh client's
auto mode stopped there on a prompt, before the go, with no one present (measured, 2026-11-05). The answer holds the
text beside the path; the file stays what a note and the go take. The verbs run for real, only the model is faked."""
from __future__ import annotations

import shutil
import json
import threading
import time
from types import SimpleNamespace

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp.shared.memory import create_connected_server_and_client_session

from gfso import config, tools_llm as TL
from gfso.api.server import create_app
from gfso.config import agent_id
from gfso.decompose import NoPlan, artifact as A, planning
from gfso.decompose.build import build_graph_live
from gfso.mcp import server as MS
from gfso.mcp.server import create_server
from tests.support import make_engine, written
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
    return (written(TL.plan, make_engine(), GOAL) if verb == "plan"
            else written(TL.refine_plan, make_engine(), written(TL.plan, make_engine(), GOAL)["path"], "a note"))


@pytest.mark.parametrize("undecided, refined", [(0, False), (2, False), (0, True), (2, True)])
def test_the_plan_says_to_give_the_go_and_rounds_are_rationed(undecided, refined):
    """Three rounds on a plan with nothing undecided: 8:28 of 17 minutes and a worse plan, 0→1→8→3 (e2e1, 2026-11-09)."""
    said = TL._after_the_plan(undecided, [{"note": "n", "answer": "what changed"}] if refined else [])
    assert "auto_decompose(plan=path)" in said and "a few minutes" in said and "one line" in said
    assert ("The note is answered" in said) is refined
    assert ("2–3 minutes" in said) is (not refined) and ("the person's result" in said) is (not refined)
    assert said.startswith("Nothing is undecided: give the go") is (undecided == 0 and not refined)


def test_a_note_its_round_left_open_is_not_spent():
    """Told "the one note is answered", the customer gave the go on a plan whose review held open the very criterion the
    round added (2026-11-13): a NOT ANSWERED round sends it back to the note."""
    said = TL._after_the_plan(3, [{"note": "n", "answer": "changed\nNOT ANSWERED — still open: x"}])
    assert "The note is answered" not in said and "not spent" in said and "auto_decompose(plan=path)" in said


def test_a_round_the_refine_gate_refuses_is_not_invited():
    """After an answered note, a later NOT ANSWERED one: `refine_plan` refuses the file (`_answered`), so the answer
    sends the customer to the go, never to a round that is refused (whole-batch critic, 2026-11-17)."""
    notes = [{"note": "a", "answer": "changed"}, {"note": "b", "answer": "NOT ANSWERED — still open: x"}]
    said = TL._after_the_plan(3, notes)
    assert "refine again" not in said and "refused" in said and "auto_decompose(plan=path)" in said


@pytest.mark.parametrize("verb, refined", [("plan", False), ("refine_plan", True)])
def test_a_refined_plan_is_read_as_refined_off_the_file_itself(home, verb, refined):
    assert ("The note is answered" in _written(verb)["say"]) is refined


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



def _forget():
    """No plan written before: the next call writes it again (a written plan is kept on disk under its handle)."""
    TL._PLANNING.clear()
    shutil.rmtree(TL._kept.data_dir() / "plans" / "kept", ignore_errors=True)

@pytest.mark.parametrize("verb", ["plan", "refine_plan"])
def test_a_plan_past_the_limit_is_answered_by_its_path_and_one_at_it_by_its_text(home, monkeypatch, verb):
    chars = _written(verb)["chars"]
    _forget()
    monkeypatch.setattr(TL, "PLAN_TEXT_MAX", chars)
    assert "text" in _written(verb)
    _forget()
    monkeypatch.setattr(TL, "PLAN_TEXT_MAX", chars - 1)
    out = _written(verb)
    assert "text" not in out and A.parse(_bytes(out).decode())["goal"] == GOAL
    assert "`path`" in out["how_to_read"], "where to read it, said in the answer that has no text"


def test_a_plan_answers_at_once_and_its_same_call_again_reads_it_written_once(home, monkeypatch):
    """A call held for the minutes a plan is written held its client's turn, and the person with it (the author,
    2026-11-15): it starts the writing and answers; the run's `next_steps` names it, and the wait ends on it."""
    calls, release = [], threading.Event()

    def slow(*a, **k):
        calls.append(1)
        release.wait(5)
        return _authored(*a, **k)
    monkeypatch.setattr(planning._decompose, "decompose_into", slow)
    e = make_engine()
    t0 = time.monotonic()
    first = TL.plan(e, GOAL)
    while not calls:
        time.sleep(0.01)
    again = TL.plan(e, GOAL)
    h = first["writing"]
    assert time.monotonic() - t0 < 4 and first["started"] and not again["started"] and h.startswith("plan-")
    assert again["writing"] == h and f'plan(writing="{h}")' in first["say"]
    assert TL.next_steps(e)["plans"] == {"writing": [h]}
    release.set()
    out = TL.wait_for_the_customer(e, seconds=10)
    assert f'plan(writing="{h}")' in out["needs_you"] and out["plans"] == {"written": [h]}
    a = written(TL.plan, e, writing=h)
    assert "plans" not in TL.next_steps(e), "read, it is no longer news"
    assert a == TL.plan(e, GOAL) == TL.plan(e, writing=h) and a["text"].encode() == _bytes(a) and len(calls) == 1


def test_a_written_plan_nobody_read_ends_one_wait_only(home):
    """An unread plan made every later wait end at once (critic's probe: 0.0 s): said once, it is not news again."""
    e = make_engine()
    h = TL.plan(e, GOAL)["writing"]
    assert TL.wait_for_the_customer(e, seconds=10)["needs_you"].startswith("a plan asked for is written")
    later = TL.wait_for_the_customer(e, seconds=0.5)
    assert "needs_you" not in later and later["waited_seconds"] >= 0.5, later
    assert TL.plan(e, writing=h)["path"], "…and it is still read by its handle"
    assert TL.plan(e, writing="plan-0000000000")["refused"], "a handle nothing holds is refused, never written anew"


def _done(e, h):
    while "writing" in (TL.plans_of(e.project_name).get("plans") or {}):
        time.sleep(0.01)


def test_a_written_plan_nobody_read_outlives_the_hour_and_a_restart(home, monkeypatch):
    """A chat agent hands the turn back and its person comes back after lunch, or after a restart: the plan paid for is
    still theirs (critic: a sweep after an hour deleted it unread, and the next `plan` wrote and paid for it again)."""
    monkeypatch.setattr(TL._kept, "KEPT_S", 0)
    e = make_engine()
    h = TL.plan(e, GOAL)["writing"]
    _done(e, h)
    TL._PLANNING.clear()                                            # …the server restarted
    TL._kept.sweep()                                                # …and the hour went by
    assert TL.plans_of(e.project_name)["plans"] == {"written": [h]}
    calls = []
    monkeypatch.setattr(planning._decompose, "decompose_into", lambda *a, **k: calls.append(1) or _authored(*a, **k))
    assert TL.plan(e, GOAL)["path"] and not calls, "its same call reads it, never writes it again"
    assert TL.plans_of(e.project_name) == {}, "read, it is no more news"
    TL._kept.sweep()                                                # read, it goes KEPT_S after
    assert TL.plan(e, writing=h)["refused"]


def test_a_plan_said_once_stays_listed_until_read(home):
    """A wait or a chat's reply carried it: it ends no later wait, and is still named to the one who asked."""
    e = make_engine()
    h = TL.plan(e, GOAL)["writing"]
    _done(e, h)
    TL.said_a_plan(e.project_name, TL.next_steps(e))
    assert TL.plans_of(e.project_name)["plans"] == {"unread": [h]}
    assert TL.needs_its_customer(TL.next_steps(e)) is None, "said once, the run's own news comes next"
    TL.plan(e, writing=h)
    assert TL.plans_of(e.project_name) == {}


def test_a_new_plan_asked_for_is_the_one_the_project_waits_on(home):
    """The person reworded the task: the plan written before, never read, is no news for the rest of the project
    (critic: it ended every later wait and masked the run's news for a chat client)."""
    e = make_engine()
    first = TL.plan(e, GOAL)["writing"]
    _done(e, first)
    second = TL.plan(e, "Another goal.")["writing"]
    _done(e, second)
    assert TL.plans_of(e.project_name)["plans"] == {"written": [second]}
    assert TL.plan(e, writing=first)["path"], "…the first is still read by its handle"
    assert TL.plans_of(e.project_name)["plans"] == {"written": [second]}


def test_a_plan_whose_writing_failed_ends_the_wait_and_says_where_why_is(home, monkeypatch):
    """A refused writing left nothing listed and the wait ran its whole length on a dead plan (critic)."""
    monkeypatch.setattr(planning._decompose, "decompose_into",
                        lambda *a, **k: (_ for _ in ()).throw(NoPlan("no criterion", [])))
    e = make_engine()
    h = TL.plan(e, GOAL)["writing"]
    _done(e, h)
    out = TL.wait_for_the_customer(e, seconds=5)
    assert out["needs_you"].startswith("a plan asked for was not written") and out["waited_seconds"] < 5
    assert "error" in TL.plan(e, writing=h)


def test_a_plan_asked_again_after_its_failure_was_read_is_listed_and_ends_the_wait(home, monkeypatch):
    """The same request asked again — the path a failed writing's or a restart's answer steers to — kept the read record
    and its error, so the plan written again was named to no one and every wait ran out on it (critic's probe).
    CONTROL: drop `or key not in _PLANNING` from `tools_llm._once` and the listing stays empty."""
    fail = [True]

    def author(*a, **k):
        if fail.pop() if fail else False:
            raise NoPlan("no criterion", [])
        return _authored(*a, **k)
    monkeypatch.setattr(planning._decompose, "decompose_into", author)
    e = make_engine()
    h = TL.plan(e, GOAL)["writing"]
    _done(e, h)
    assert "error" in TL.plan(e, writing=h)                       # …the failure read
    assert TL.plan(e, GOAL)["writing"] == h
    _done(e, h)
    assert TL.plans_of(e.project_name)["plans"] == {"written": [h]}
    out = TL.wait_for_the_customer(e, seconds=5)
    assert out.get("needs_you", "").startswith("a plan asked for is written") and out["waited_seconds"] < 5, out


def test_a_wait_on_a_plan_being_written_does_not_end_on_what_already_stood(home, monkeypatch):
    """A move of the caller's already standing ended every wait at once while the plan was still written: a wait with
    no move that waits (critic)."""
    release = threading.Event()
    monkeypatch.setattr(planning._decompose, "decompose_into", lambda *a, **k: release.wait(5) and _authored(*a, **k))
    monkeypatch.setattr(TL, "needs_its_customer",
                        lambda out, real=TL.needs_its_customer: real(out) or "1 move(s) are yours")
    e = make_engine()
    TL.plan(e, GOAL)
    out = TL.wait_for_the_customer(e, seconds=0.6)
    release.set()
    assert out["waited_seconds"] >= 0.6 and "needs_you" not in out, out


def test_a_plan_written_during_a_wait_ends_it_whoever_else_was_told(home, monkeypatch):
    """Two consoles on one project: the other one's reply said the plan first, and this wait never ended on it (critic)."""
    release = threading.Event()
    monkeypatch.setattr(planning._decompose, "decompose_into", lambda *a, **k: release.wait(5) and _authored(*a, **k))
    e = make_engine()
    h = TL.plan(e, GOAL)["writing"]
    real, once = TL.next_steps, []

    def steps(*a):
        out = real(*a)
        if not once:
            once.append(1)
            release.set()
            _done(e, h)
            TL.said_a_plan(e.project_name, real(*a))                # …another console was told meanwhile
        return out
    monkeypatch.setattr(TL, "next_steps", steps)
    out = TL.wait_for_the_customer(e, seconds=5)
    assert out.get("needs_you", "").startswith("a plan asked for is written") and out["waited_seconds"] < 5, out


def test_what_arises_during_a_writing_ends_the_wait(home, monkeypatch):
    """Only what stood when the wait began is set aside: a run stuck since does end it (critic)."""
    release = threading.Event()
    monkeypatch.setattr(planning._decompose, "decompose_into", lambda *a, **k: release.wait(5) and _authored(*a, **k))
    e = make_engine()
    TL.plan(e, GOAL)
    seen = iter([None] + ["the run is stuck: x"] * 1000)
    monkeypatch.setattr(TL, "needs_its_customer", lambda out: next(seen))
    out = TL.wait_for_the_customer(e, seconds=5)
    release.set()
    assert out.get("needs_you") == "the run is stuck: x" and out["waited_seconds"] < 5, out


def test_a_call_joining_a_writing_makes_it_the_one_its_project_waits_on(home, monkeypatch):
    """Asked again while still written, after another plan was asked or the project re-made: it is listed (critic)."""
    release = threading.Event()
    monkeypatch.setattr(planning._decompose, "decompose_into", lambda *a, **k: release.wait(5) and _authored(*a, **k))
    e = make_engine()
    h = TL.plan(e, GOAL)["writing"]
    TL._kept.forget_project(e.project_name)                          # …deleted and re-made under its name
    assert TL.plan(e, GOAL)["writing"] == h
    assert TL.plans_of(e.project_name)["plans"] == {"writing": [h]}
    release.set()
    _done(e, h)
    assert TL.plans_of(e.project_name)["plans"] == {"written": [h]}


def test_a_plan_superseded_while_written_is_let_go_once_kept(home, monkeypatch):
    """Its file appeared after the release ran, and nothing ever removed it (critic)."""
    monkeypatch.setattr(TL._kept, "KEPT_S", 0)
    release = threading.Event()
    slow = lambda *a, **k: release.wait(5) and _authored(*a, **k)
    monkeypatch.setattr(planning._decompose, "decompose_into", slow)
    e = make_engine()
    first = TL.plan(e, GOAL)["writing"]
    second = TL.plan(e, "Another goal.")["writing"]
    release.set()
    _done(e, second)
    while TL._kept.answer(first) is None:
        time.sleep(0.01)
    TL._kept.sweep()
    assert TL._kept.answer(first) is None and TL._kept.answer(second) is not None


def test_a_deleted_project_waits_on_no_plan(home):
    e = make_engine()
    h = TL.plan(e, GOAL)["writing"]
    _done(e, h)
    TL._kept.forget_project(e.project_name)
    assert TL.plans_of(e.project_name) == {}


def test_with_no_server_the_plan_is_written_in_the_call(home):
    """The CLI's direct path ends its process with the call: a writing in a thread would die unwritten (critic)."""
    token = config.WRITTEN_IN_THE_CALL.set(True)
    try:
        out = TL.plan(make_engine(), GOAL)
    finally:
        config.WRITTEN_IN_THE_CALL.reset(token)
    assert "writing" not in out and out["path"]


def test_a_refused_plan_names_no_path_and_holds_no_text(home, monkeypatch):
    monkeypatch.setattr(planning._decompose, "decompose_into",
                        lambda *a, **k: (_ for _ in ()).throw(NoPlan("no criterion", [])))
    out = written(TL.plan, make_engine(), GOAL)
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
            await session.call_tool("act_as", {"name": "user"})      # …the person's agent, logged in as him
            for verb, kw in args:
                while "writing" in json.loads((r := await session.call_tool(verb, kw)).content[0].text):
                    await anyio.sleep(0.01)
                got.append(r)
        return got
    return anyio.run(go)


def test_the_mcp_door_answers_with_the_text_and_a_second_call_still_says(home):
    e = make_engine()
    (first, joined) = _by_mcp(e, ("plan", {"request": GOAL}), ("plan", {"request": GOAL}))
    for out in (json.loads(first.content[0].text), json.loads(joined.content[0].text)):
        assert out["text"].encode() == _bytes(out)
        keys = list(out)
        assert keys[0] == "say" and keys[-1] == "text"


def test_the_door_sends_ampersands_and_brackets_as_they_are_and_says_what_a_client_shows(home):
    """A background result showed `&amp;` in the plan's commands (116 in M4), its file and this door holding `&`."""
    (r,) = _by_mcp(make_engine(), ("plan", {"request": "Build a && b > c < d.\n"}))
    assert "&amp;" not in r.content[0].text and "a && b > c < d" in r.content[0].text
    out = json.loads(r.content[0].text)
    assert out["text"].encode() == _bytes(out)
    assert "&" not in out["how_to_read"]


def test_the_listing_declares_the_room_for_a_plan_and_for_no_other_verb(home):
    async def go():
        async with create_connected_server_and_client_session(create_server(make_engine())._mcp_server) as session:
            return (await session.list_tools()).tools
    metas = {t.name: t.meta for t in anyio.run(go) if t.meta}
    assert set(metas) == {"plan", "refine_plan"}
    assert all(m == {"anthropic/maxResultSizeChars": 500_000} for m in metas.values())
    assert TL.PLAN_TEXT_MAX < 500_000, "the plan rides whole, in the room its answer declares"


def test_the_plans_measured_ride_in_the_answer():
    """A coreutils plan ran 88–105k characters and a C compiler's 184–279k (2026-11-05, 11-11): past the 80,000 the
    answer held, `path` stood alone and the customer read a file outside the person's folder, meeting prompts. The room a
    tool declares replaces the client's token cap for its text (code.claude.com/docs/en/mcp, "Scope"), up to 500,000."""
    assert TL.PLAN_TEXT_MAX >= 280_000


def test_the_largest_plan_the_limit_lets_through_fits_the_room_declared(home, monkeypatch):
    room = TL.PLAN_TEXT_MAX - len(A.render("", _plan())) - 100
    text = A.render('a "quoted" && b > c\n' * (room // 20), _plan())
    monkeypatch.setattr(planning, "author", lambda *a, **k: text)
    (r,) = _by_mcp(make_engine(), ("plan", {"request": "x"}))
    assert TL.PLAN_TEXT_MAX * .9 < len(text) <= TL.PLAN_TEXT_MAX
    assert "text" in json.loads(r.content[0].text) and len(r.content[0].text) <= 500_000


def test_the_entry_and_the_go_say_the_person_does_not_see_the_answer_and_give_the_link(monkeypatch):
    monkeypatch.setattr(MS, "_ui_link", lambda p: "http://u/?project=x")
    e = make_engine()
    monkeypatch.setattr(e, "mode", lambda: {"mode": "auto"})
    for verb, base in (("use_project", {"active": "x"}), ("auto_decompose", {"root_id": "root"})):
        out = MS._with_ui_link(verb, dict(base), "x", e if verb == "auto_decompose" else None)
        assert out["say"].startswith("The person does not see this tool's answer: write this link in your reply's text now, on a line of its own with nothing else on it, not in thinking: "
                                     "http://u/?project=x"), out["say"]


def test_the_mcp_door_answers_a_refine_with_the_text(home):
    e = make_engine()
    path = written(TL.plan, e, GOAL)["path"]
    (out,) = _by_mcp(e, ("refine_plan", {"plan": path, "note": "a note"}))
    out = json.loads(out.content[0].text)
    assert out["text"].encode() == _bytes(out) and A.parse(out["text"])["notes"][-1]["note"] == "a note"


def test_the_http_door_answers_with_the_text(home):
    with TestClient(create_app(make_engine())) as c:
        out = written(lambda: c.post("/api/run/plan", json={"request": GOAL}).json())
    assert out["text"].encode() == _bytes(out)


def test_under_auto_the_door_refuses_a_go_with_no_plan_read_and_takes_the_plan_file(home, monkeypatch):
    """The author: «пока заказчик не убедится… запускать нельзя». A request on an empty `auto` project planned and ran in
    one call, the customer reading nothing (audit, 11-07); the plan file's go passes the door, and so does a request
    with no mode set."""
    e = make_engine()
    monkeypatch.setattr(e, "mode", lambda: {"mode": "auto"})
    (no,) = _by_mcp(e, ("auto_decompose", {"request": GOAL}))
    assert json.loads(no.content[0].text)["refused"] == "the plan unread" and not list(e.all_tasks())
    assert MS._unread_go("auto_decompose", e, {"plan": "p.gfso"}) is None
    assert MS._unread_go("auto_decompose", make_engine(), {"request": GOAL}) is None
    # …and a second goal: a request making a new root in a project already holding one is refused the same way (critic,
    # 11-07: the finished project's own hint led there), while a refine of a node there passes
    full = make_engine()
    monkeypatch.setattr(full, "all_tasks", lambda: [SimpleNamespace(id="root")])
    monkeypatch.setattr(full, "mode", lambda: {"mode": "auto"})
    assert MS._unread_go("auto_decompose", full, {"request": "another", "root_id": "root2"})["refused"] == "the plan unread"
    assert MS._unread_go("auto_decompose", full, {"root_id": "root"}) is None


@pytest.mark.parametrize("kind", ["code", "chat"])
def test_a_plan_being_written_names_a_wake_only_to_a_client_that_has_one(kind):
    token = config.CLIENT.set(kind)
    try:
        said = TL._being_written("plan-0123456789", "p1", True)["say"]
    finally:
        config.CLIENT.reset(token)
    assert ("`gfso wait project=p1`" in said) is (kind == "code") and 'plan(writing="plan-0123456789")' in said, said
    assert ("Hand the turn back" in said) is (kind == "chat"), said
