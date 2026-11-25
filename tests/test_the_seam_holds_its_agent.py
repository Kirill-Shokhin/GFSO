"""The system's reminder at a console's stop (`gfso.hold`): a console ending its turn while a node its taken name holds
owes a move of its own is told that move, once — an executor moves by signals alone, none of them "stop" (§11.2), and
every live state has an owner with a move (§12.13 Inv-8). Read through the one GET that marks nothing
(`tools_llm.held_steps`), in process here, the server's own route where the door is the point.

Each test ran red on the tree before it (no hook, no read, no `persons`); the mutation named in its docstring turns it
red again."""
from __future__ import annotations

import dataclasses as dc
import io
import json
import subprocess
import time
import urllib.error

import pytest
from starlette.testclient import TestClient

import gfso.tools as T
import gfso.tools_llm as TL
from gfso import config, hold as H, serverctl, signin
from gfso.api.server import create_app
from gfso.config import STANDING, Principal
from gfso.core.types import State, TaskId
from gfso.decompose import kept as K
from gfso.delegate import ensure_dispatcher
from gfso.signin import PAGE
from tests.support import a_repository, criterion, instrument_passes, make_engine
from tests.test_the_mode_decides_who_holds_what import Mode, _engine
from tests.test_a_seam_he_issues_is_checked_by_the_validator import (CONSOLE, HOLDER, SEAM, _as, _checked, _delivers,
                                                                      _issued, _state)
from tests.test_a_write_past_the_system_is_witnessed_never_blocked import _git


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    monkeypatch.delenv("GFSO_VALIDATE_INTERNAL", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
    monkeypatch.delenv("CLAUDE_CTX_WINDOW", raising=False)
    monkeypatch.setattr(H, "STATUSLINE", tmp_path / "ctx")    # …never the machine's own consoles' measures


def _held(tmp_path):
    """His seam to `engineering`, taken, its name working in a chat here."""
    e, _ = _issued(tmp_path)
    e.performs_in_chat(HOLDER)
    return e


def _asked(e, p=CONSOLE, at=None, **over):
    """The hook's read, signed by `p`, as the route serves it — its steps on node `at` alone, where named."""
    def ask(project):
        with _as(p):
            out = {**TL.held_steps(e), **over}
        return {**out, "steps": [s for s in out["steps"] if s.get("task_id") == at]} if at else out
    return ask


def _stop(e, p=CONSOLE, **event):
    return H.decide({"session_id": "s", "hook_event_name": "Stop", **event}, "p", _asked(e, p))


def test_its_own_step_holds_every_stop_naming_its_directive_verbatim_and_the_read_marks_nothing(tmp_path):
    """Stopping is no move: a stop the hook already turned back (`stop_hook_active`) is turned back again, and the way
    out is a move, which takes the step off. A plan the project waits on stays unsaid by the hook's read. CONTROL: the
    reason without the directive — red; `stop_hook_active` read as a release — red; `held_steps` saying the plan
    (`said_a_plan`) — red."""
    e = _held(tmp_path)
    K.open_writing("p", "plan-a1b2", "plan")
    K.mark("p", "plan-a1b2", state="written")
    with _as(CONSOLE):
        own = next(s for s in TL.next_steps(e)["steps"] if s.get("mine") and not s.get("optional"))
    out = _stop(e)
    assert own["task_id"] == SEAM and out["decision"] == "block" and len(out["reason"]) <= H.CAP, out
    assert f"You are on {SEAM}: {own['directive'][:300]}" in out["reason"] and "Not handed in" in out["reason"], out
    assert _stop(e, stop_hook_active=True) == out
    assert TL.plans_of("p") == {"plans": {"written": ["plan-a1b2"]}}, "the hook's read said the plan"
    assert T.signal(e, SEAM, "BLOCK", HOLDER, reason="which line ending does he want?")["accepted"]
    e.wait_idle()
    assert _stop(e, stop_hook_active=True) == {}, "a move did not take the step off"


def test_a_console_whose_own_work_runs_in_the_background_is_not_held(tmp_path):
    """Work in flight — a subagent, a background command, a monitor — is the console's own work: Claude Code names it in
    the Stop event (`background_tasks`) and wakes the console when it ends, so a stop then is no standing — once the
    wait has a bound (Inv-5): a monitor, or a scheduled wakeup (`session_crons`); a subagent alone could hang forever,
    so the one move asked is to set a wake. With nothing in flight the console is held on its moves. CONTROLS:
    `background_tasks` unread — red; the bound unread — red."""
    e = _held(tmp_path)
    agent = [{"id": "a1", "type": "subagent", "status": "running", "description": "a build"}]
    unbounded = H.decide({"background_tasks": agent}, "p", _asked(e))
    assert unbounded["decision"] == "block" and "fallback wake" in unbounded["reason"], unbounded
    assert H.decide({"background_tasks": agent, "session_crons": [{"id": "c1"}]}, "p", _asked(e)) == {}
    assert H.decide({"background_tasks": [*agent, {"id": "m1", "type": "monitor"}]}, "p", _asked(e)) == {}
    assert H.decide({"background_tasks": []}, "p", _asked(e))["decision"] == "block"
    assert H.decide({}, "p", _asked(e))["decision"] == "block"


def test_background_work_asks_a_bound_only_of_a_console_that_owes_a_move_and_never_past_the_ceiling(tmp_path):
    """The bound on background work is asked where the console's name owes a move — its wait is the one that must end
    (Inv-5); a console owing nothing stops whatever runs beside it, and at the window's ceiling a stop goes through first,
    unbounded work or not (the closing ritual takes it from there). CONTROL: the bound asked before the frontier is
    read — red on the first assert; the ceiling read after the bound — red on the second."""
    e = _held(tmp_path)
    agent = [{"id": "a1", "type": "subagent", "status": "running", "description": "a build"}]
    high = _transcript(tmp_path, 760_000)
    assert H.decide({**high, "background_tasks": agent}, "p", _asked(e), ceiling=75, window=1_000_000) == {}
    assert T.signal(e, SEAM, "BLOCK", HOLDER, reason="which line ending does he want?")["accepted"]
    e.wait_idle()
    assert _stop(e, background_tasks=agent) == {}, "a console owing no move was asked to bound unrelated work"


def _transcript(tmp_path, n):
    tr = tmp_path / f"t{n}.jsonl"
    rec = lambda used, side=False: json.dumps({"type": "assistant", "isSidechain": side, "message": {
        "usage": {"input_tokens": 10, "cache_read_input_tokens": used}}})
    tr.write_text("\n".join([rec(n - 10), rec(1, side=True)]) + "\n", encoding="utf-8")
    return {"session_id": "s", "transcript_path": str(tr)}


def test_at_the_fill_ceiling_of_a_known_window_a_stop_goes_through_and_below_it_is_held(tmp_path, monkeypatch):
    """The window is known, never guessed: the statusline's measure when present and fresh, else given at install,
    else set outside (`CLAUDE_CTX_WINDOW`); with none the ceiling is off. 367k of a 1M window at 75% is held, 760k goes
    through, recording nothing. CONTROL: a fallback window of 200k — 367k reads 183% and goes through; the env unread,
    the statusline unread, its staleness unread, the ceiling unread — each red."""
    monkeypatch.setattr(H, "STATUSLINE", tmp_path / "ctx")
    e = _held(tmp_path)
    low, high = _transcript(tmp_path, 367_000), _transcript(tmp_path, 760_000)
    assert H.used(high["transcript_path"]) == 760_000
    assert H.decide(low, "p", _asked(e), ceiling=75, window=1_000_000)["decision"] == "block"
    assert H.decide(high, "p", _asked(e), ceiling=75, window=1_000_000) == {}
    assert H.decide(high, "p", _asked(e), ceiling=75)["decision"] == "block", "a window guessed"
    assert H.decide(high, "p", _asked(e))["decision"] == "block", "no window known, yet the default ceiling stood"
    assert H.decide(high, "p", _asked(e), window=1_000_000) == {}, "the ceiling is not on by default"
    assert H.decide(high, "p", _asked(e), ceiling=0, window=1_000_000)["decision"] == "block", "0 did not turn it off"
    monkeypatch.setenv("CLAUDE_CTX_WINDOW", "800000")
    assert H.decide(low, "p", _asked(e), ceiling=40, window=10_000_000)["decision"] == "block", "--window comes before the env"
    assert H.decide(low, "p", _asked(e), ceiling=40) == {}
    (tmp_path / "ctx").mkdir()
    sl = tmp_path / "ctx" / "s.json"
    sl.write_text(json.dumps({"size": 1_000_000, "used": 760_000, "ts": time.time()}))
    assert H.decide(low, "p", _asked(e), ceiling=75, window=10_000_000) == {}, "the statusline's measure unread"
    sl.write_text(json.dumps({"size": 1_000_000, "used": 760_000, "ts": time.time() - H.FRESH_S - 5}))
    assert H.decide(low, "p", _asked(e), ceiling=75, window=10_000_000)["decision"] == "block", "a stale measure read"


def test_a_step_its_hands_perform_holds_no_stop_and_wakes_no_wait_its_offer_does(tmp_path):
    """Solo with dispatch: after his ACCEPT the root's work is `exec-1`'s, «do not build it yourself» — no honest move
    is left in the console, and its wait agrees. The offer before it holds nothing either: it binds no one until
    ACCEPT and abstention discharges it (§12.9). CONTROL: the PERFORMED BY
    step left non-optional — the stop is held with no move to make."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.set_mode(Mode.SOLO, None, "user", hands="exec-1")
    T.create_task(e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    assert H.decide({}, "p", _asked(e, STANDING)) == {}, "an offer binds no one until ACCEPT; abstention discharges it"
    assert T.signal(e, "root", "ACCEPT", "user")["accepted"]
    e.wait_idle()
    with _as(STANDING):
        out = TL.next_steps(e)
    assert any("PERFORMED BY exec-1" in s["directive"] for s in out["steps"]), out["steps"]
    assert H.decide({}, "p", _asked(e, STANDING)) == {}
    assert TL.needs_its_customer(out) is None


def _solo_root(state="EXECUTING"):
    """His solo project, its root taken by his own agent — and, for VALIDATING, delivered with no validator registered."""
    e = _engine(Mode.SOLO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    assert T.signal(e, "root", "ACCEPT", "user")["accepted"]
    if state == "VALIDATING":
        with _as(STANDING):
            out = T.signal(e, "root", "DELIVER", "user", result="it holds", self_validation="PASS")
        assert out.get("accepted"), out
        e.wait_idle()
    return e


def test_once_delivered_the_holder_owes_nothing_observed_or_not(tmp_path):
    """The observation of a delivery is the seam's validator's step, the system's — never the holder's move: after his
    DELIVER the console stops, a validator registered or not; the PASS left is his (`persons`, the door's own rule,
    `tools.persons_move`). CONTROL: the OBSERVE step read as the holder's — the console held on the system's step."""
    e = _solo_root("VALIDATING")
    with _as(STANDING):
        assert any(str(s.get("directive")).startswith("OBSERVE THIS DELIVERY") for s in TL.next_steps(e)["steps"])
    assert H.decide({}, "p", _asked(e, STANDING)) == {}
    # …its dispatcher stopped before the validator is: the PASS is the test's own, never a live validation's in flight
    ensure_dispatcher(e).stop()
    assert not TL.register_agent(e, "p-val", "llm-validator", workdir=str(a_repository(tmp_path))).get("refused")
    assert H.decide({}, "p", _asked(e, STANDING)) == {}
    instrument_passes(e, TaskId("root"), validator="p-val")
    with _as(STANDING):
        his = [s for s in TL.next_steps(e)["steps"] if s.get("task_id") == "root" and s.get("mine")]
    assert his and all(s.get("persons") for s in his), his
    assert H.decide({}, "p", _asked(e, STANDING)) == {}


def test_an_observation_owed_holds_no_issuer_whoever_it_is(tmp_path):
    """The OBSERVE step is the system's whatever node it stands on: read with no `persons` on it — an issuer who is
    not the person — it still holds no stop. CONTROL: the hook reading an OBSERVE step as the holder's — held."""
    e = _solo_root("VALIDATING")
    ask = _asked(e, STANDING)
    steps = [{**s, "persons": False} for s in ask("p")["steps"]]
    assert any(str(s["directive"]).startswith("OBSERVE") and s.get("mine") for s in steps), steps
    assert H.decide({}, "p", lambda p: {**ask(p), "steps": steps}) == {}


def test_a_console_with_no_gfso_connection_is_said_not_held(tmp_path, monkeypatch):
    """A call that signs nothing (`signin.BARE`: no credential, or a gfso connection that has taken no name) reads as
    `user` and no move of its frontier could be made from it. Through the route: a bridge logged in as him
    (`act_as('user')`) is held, one that took no name is not. CONTROL: BARE not read as unsigned — the console is held
    as `user`."""
    e = _solo_root()
    out = H.decide({}, "p", _asked(e, signin.BARE))
    assert "decision" not in out and "act_as('user')" in out["systemMessage"], out
    c = TestClient(create_app(e), base_url="http://127.0.0.1:8000")
    c.cookies.clear()
    monkeypatch.setattr(signin, "LIVE_LEASES", lambda: [])
    signin.take("his-lease", "user")
    his = c.get("/api/steps", headers={config.LEASE_HEADER: "his-lease"}).json()
    assert (his["signer"], his.get("unsigned")) == ("user", None) and his["steps"], his
    bare = c.get("/api/steps", headers={config.LEASE_HEADER: "untaken-lease"}).json()
    assert bare.get("unsigned") is True, bare
    signin.let_go("his-lease")


def test_a_wrong_project_or_a_refused_connection_is_said_not_held(tmp_path):
    """A 404 is no project by that name, not a server down; a connection whose taken name was refused signs as no one
    and is not held as the person. CONTROL: the 404 read as unreachable — red; `refused` unread — the console held as
    `user`."""
    def gone(project):
        raise urllib.error.HTTPError("http://x", 404, "not found", {}, None)
    assert H.decide({}, "nope", gone) == {"systemMessage": "no project nope on the server"}
    e = _engine(Mode.SOLO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    assert T.signal(e, "root", "ACCEPT", "user")["accepted"]
    lost = Principal("user", (), signin.REFUSED, "not signed in", None, "`eng` was taken by another connection")
    out = H.decide({}, "p", _asked(e, lost))
    assert "decision" not in out and "taken by another connection" in out["systemMessage"], out


def test_the_persons_own_console_in_solo_is_held_on_his_root_and_as_an_auto_customer_is_not(tmp_path):
    """One name for him and his agent (`user`): the frontier decides, not a record of names in a chat. His solo root
    EXECUTING owes its DELIVER; an `auto` root VALIDATING is the system's to sign (`mode_holder`), nothing his. CONTROL:
    the in-chat record as the gate — the solo console is let stop."""
    e = _engine(Mode.SOLO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    assert T.signal(e, "root", "ACCEPT", "user")["accepted"]
    out = H.decide({}, "p", _asked(e, STANDING))
    assert out["decision"] == "block" and "You are on root: " in out["reason"] and "DELIVER" in out["reason"], out
    a = _engine(Mode.AUTO)
    T.TOOLS["create_task"](a, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    a.wait_idle()
    a._graph.save_task(dc.replace(a.graph.get_task(TaskId("root")), state=State.VALIDATING))
    assert H.decide({}, "p", _asked(a, STANDING)) == {}


@pytest.mark.parametrize("move", ["validate", "challenge", "block"])
def test_a_move_of_the_persons_reminds_nothing(tmp_path, move):
    """An issuer move on a node he issued — PASS/FAIL at VALIDATING, ACCEPT/REJECT_CHALLENGE at CHALLENGED,
    RESOLVE_BLOCK at BLOCKED — is `persons` on the frontier: a wait on him, even read as his own. CONTROL: `_mark_mine`
    setting no `persons` — red; the hook reading `mine` alone — red."""
    e = _held(tmp_path)
    if move == "validate":
        _checked(e, "tree-1")
        assert _delivers(e, "tree-1").get("accepted")
    else:
        assert T.signal(e, SEAM, move.upper(), HOLDER, reason="which line ending does he want?")["accepted"]
    e.wait_idle()
    assert _state(e) == {"validate": "VALIDATING", "challenge": "CHALLENGED", "block": "BLOCKED"}[move]
    his = [s for s in _asked(e, PAGE, at=SEAM)("p")["steps"] if s.get("mine")]
    assert his and all(s.get("persons") for s in his), his
    assert H.decide({"session_id": "s"}, "p", _asked(e, PAGE, at=SEAM, in_chat=True)) == {}
    assert _stop(e) == {}, "the holder is reminded of his move"


def test_another_partys_or_an_optional_step_reminds_nothing(tmp_path):
    """CONTROL: the hook reading every step — red."""
    e = _held(tmp_path)
    steps = _asked(e)("p")["steps"]
    for s in ({**x, "mine": False} for x in steps), ({**x, "optional": True} for x in steps):
        assert H.decide({}, "p", lambda p, s=list(s): {**_asked(e)(p), "steps": s}) == {}


def test_a_stopped_run_a_settled_root_or_no_graph_reminds_nothing(tmp_path):
    """CONTROL: `run`, `complete` or an empty frontier unread — red."""
    e = _held(tmp_path)
    assert H.decide({}, "p", _asked(e, complete=True)) == {}
    e.stops.pause("user", "enough for today")
    assert _stop(e) == {}
    empty = make_engine(validate_signals=True, state_timeout=0)
    empty.start()
    assert H.decide({}, "p", _asked(empty, in_chat=True)) == {}


def test_another_console_is_not_reminded_and_the_route_signs_by_the_calls_credential(tmp_path):
    """A console whose signer owns no step here is let stop. Through the server's own route the frontier is the
    signer's: the token signs as its name, a bare call as `user`; `in_chat` says which name works in a chat, as
    information. CONTROL: `in_chat` read as true — red."""
    e = _held(tmp_path)
    assert _stop(e, Principal("other", ("other",), "t", "token")) == {}
    c = TestClient(create_app(e), base_url="http://127.0.0.1:8000")
    c.cookies.clear()
    bare = c.get("/api/steps").json()
    assert (bare["signer"], bare["in_chat"]) == ("user", False), bare
    signed = c.get("/api/steps", headers={"Authorization": f"Bearer {signin.issue(HOLDER)[1]}"}).json()
    assert (signed["signer"], signed["in_chat"]) == (HOLDER, True) and signed["steps"] and "run" in signed, signed


def test_the_task_it_is_on_comes_first_whatever_the_frontier_ranks_first(tmp_path):
    """Its latest move in the log names the task it is on (`current`, the system's record, no state of the hook's):
    told first, and only its directive whole — a reminder of another task would pull it off the one it is carrying.
    CONTROL: the frontier's order alone — t1 comes first; `current` read off another signer's moves — red."""
    e = _held(tmp_path)
    assert _asked(e)("p")["current"] == SEAM, "the node of its latest move, its ACCEPT"
    assert _asked(e, STANDING)("p")["current"] == SEAM, "his own latest move: the ASSIGN his split issued"
    assert _asked(e, Principal("other", ("other",), "t", "token"))("p")["current"] is None
    steps = [_own(1), _own(2), _own(3)]           # …the frontier ranks t1 first; the console moved last on t2
    lines = H.decide({}, "p", lambda p: {"steps": steps, "current": "t2"})["reason"].splitlines()
    assert lines[1].startswith("You are on t2: DELIVER t2") and "DELIVER t1" not in "\n".join(lines), lines


def _own(n, state="EXECUTING", **over):
    return {"task_id": f"t{n}", "action": "deliver", "state": state, "mine": True,
            "directive": f"DELIVER t{n}: " + "do the work and hand it in. " * 30, **over}


def test_many_open_moves_say_one_directive_whole_and_name_the_rest_in_one_line():
    """Twenty moves of its own: one directive, one line naming the rest, under the cap. CONTROL: every directive
    listed — past the cap."""
    steps = [_own(n) for n in range(20)]
    out = H.decide({}, "p", lambda p: {"steps": steps, "current": "t7"})["reason"]
    assert len(out) <= H.CAP and out.count("DELIVER t") == 1 and "You are on t7: DELIVER t7" in out, out
    assert out.splitlines()[-1].startswith("and 19 more open: t0, t1, t2 …"), out


def test_a_node_a_fail_sent_back_is_named_second():
    """CONTROL: rework not read apart — it hides in the count."""
    steps = [_own(1), _own(2, "REWORKING", directive="FIX AND RE-DELIVER t2 — failed on k: the check printed NO.\nmore"),
             _own(3)]
    lines = H.decide({}, "p", lambda p: {"steps": steps, "current": "t3"})["reason"].splitlines()
    assert lines[1].startswith("You are on t3: ") and lines[2] == (
        "- t2 back in rework: FIX AND RE-DELIVER t2 — failed on k: the check printed NO.") and lines[3] == (
        "and 1 more open: t1"), lines
    fresh = H.decide({}, "p", lambda p: {"steps": steps})["reason"].splitlines()
    assert fresh[1].startswith("The most urgent: t1: "), fresh


def test_a_subagent_or_a_driven_cli_is_not_reminded(tmp_path, monkeypatch):
    """CONTROL: `agent_id` and the entrypoint unread — red."""
    e = _held(tmp_path)
    assert _stop(e, agent_id="a1") == {}
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "sdk-py")
    assert _stop(e) == {}


def test_with_no_server_the_console_stops_and_is_told(monkeypatch, capsys):
    """The hook's own transport, to a port that answers nothing; a run that raises says nothing and exits 0. CONTROL:
    the read's failure let out — red."""
    monkeypatch.setattr(serverctl, "BASE", "http://127.0.0.1:9")
    assert H.decide({"session_id": "s"}, "p") == {"systemMessage": "gfso not reachable"}
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    monkeypatch.setattr("sys.argv", ["hold", "p"])
    with pytest.raises(SystemExit) as ex:
        H.main()
    assert ex.value.code == 0 and capsys.readouterr().out == ""


def test_it_is_installed_once_in_the_places_own_settings_kept_out_of_git(tmp_path):
    """Run twice, one Stop entry, another project's its own, the ceiling on at 60 by default; with no window known
    install says the ceiling is inert where the statusline measures none; removed, the person's own hooks stay; the file
    git ignores. CONTROL: the project's entry not matched — two entries; the inert line unsaid — red."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    s = repo / ".claude" / "settings.local.json"
    s.parent.mkdir()
    mine = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "mine"}]}]}}
    s.write_text(json.dumps(mine))
    said = [H.install(repo, p) for p in ("p", "p", "p2")]
    assert all("inert" in x for x in said), said
    assert "inert" not in H.install(repo, "p", window=1_000_000)
    cmds = [h["command"] for g in json.loads(s.read_text())["hooks"]["Stop"] for h in g["hooks"]]
    assert sorted(c.split(f"-m {H.MARK} ")[1] for c in cmds if H.MARK in c) == [
        "p --ceiling 60 --window 1000000", "p2 --ceiling 60"], cmds
    assert "mine" in cmds
    assert subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", ".claude/settings.local.json"]).returncode == 0
    H.install(repo, "p2", remove=True)
    H.install(repo, "p", remove=True)
    assert json.loads(s.read_text()) == mine
