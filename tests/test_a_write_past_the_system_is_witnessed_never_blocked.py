"""A console's write to its repository while no node of the project is at work there is recorded as the project's own
and told to the agent — never blocked (`gfso.witness`, the hook; `past.witness`, the decision). One predicate with the
measure (`past.at_work`); git's status of the tree read before and after each call, paired by the call's id.

Each test ran red on main before it (no witness); the mutation named in its docstring turns it red again.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import gfso.past as P
import gfso.tools as T
import gfso.tools_llm as TL
from gfso.core.types import AgentId, Mode
from tests.support import REGISTER, criterion, make_engine
from gfso import witness as Wt
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.runtime import ProjectRegistry
from gfso.api.server import create_app
from gfso.config import CALLER, Principal
from tests.test_work_past_the_system_is_counted_from_records import OLD, _cancelled, _commit, _deliver, _git, _in_chat


@pytest.fixture(autouse=True)
def _a_roster_of_its_own(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path / "data"))         # …the person's record of where hooks stand


@pytest.fixture
def repo(tmp_path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _commit(r, "README", when=OLD)
    return r


def _call(e, cwd, write=lambda: None, tool="Bash", n=[0], end="PostToolUse") -> dict:
    """One tool call seen by the hook: its PreToolUse, what it does, its end — the system answering in process."""
    n[0] += 1
    ask = lambda project, body: P.witness(e, body["repository"], body["tool"], body["paths"])
    ev = {"tool_name": tool, "tool_use_id": f"t{n[0]}", "cwd": str(cwd)}
    assert Wt.observe({**ev, "hook_event_name": "PreToolUse"}, "p", ask) == {}
    write()
    return Wt.observe({**ev, "hook_event_name": end}, "p", ask)


def test_a_write_with_no_node_at_work_is_recorded_and_said_and_one_under_a_node_at_work_is_not(repo):
    """CONTROL: `past.witness` ignoring `at_work` — the write under the node at work is recorded."""
    e = _in_chat(repo)
    assert _call(e, repo, lambda: (repo / "a.txt").write_text("a")) == {}
    _deliver(e)
    out = _call(e, repo, lambda: (repo / "a.txt").write_text("b"))
    said = out["hookSpecificOutput"]
    assert said["hookEventName"] == "PostToolUse" and "take the node" in said["additionalContext"].lower()
    assert "decision" not in out and "decision" not in said, "the witness blocks nothing"
    seen = TL.TOOLS["metrics"](e)["witnessed"]
    assert seen["count"] == 1 and "a.txt" in seen["last"][0]["text"], seen


def test_a_node_taken_before_its_accept_named_a_repository_covers_its_holders_write_where_the_hook_stands(repo):
    """Finding A: a node taken before an ACCEPT recorded its repository — a direction held for months, in a project with
    no role registered anywhere — was at work nowhere, and its holder was told to take a node the protocol refuses (it
    is taken). The project's hook installed in the repository is the project working there. CONTROL: attachment read
    from the ACCEPT row alone — the write is recorded and the holder told to take the node."""
    e = _a_direction()
    Wt.install(repo, "p")
    assert _call(e, repo, lambda: (repo / "a.txt").write_text("a")) == {}
    assert e.witnessed_writes() == []


def _a_direction(project="p"):
    """A project with no role anywhere whose root its holder took by the door that records no repository."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = project
    e.set_mode(Mode.SOLO, None, AgentId("user"), hands=None)
    T.create_task(e, "root", {"description": "a direction", "accepted_risks": REGISTER,
                              "criteria": [criterion("f", "f.txt says v1")]})
    e.wait_idle()
    assert T.signal(e, "root", "ACCEPT", "user")["accepted"]
    return e


def test_a_call_binds_no_repository_only_the_persons_install_does(repo, monkeypatch):
    """Where a project works is the person's act — the hook installed there for it —, never what a call or a request
    body names: a console that went into another repository, or any caller of the door, would bind it for good and hide
    every hand commit there under the project's taken nodes. A call from a repository the hook is not installed in is
    answered by the records there. CONTROL: the call's repository kept as the project's — the write is silenced and the
    hand commit is in work."""
    q = _in_chat(repo, project="q", take=False)
    dev = _a_direction("dev")
    monkeypatch.setattr(P, "OPEN", lambda: [q, dev])
    assert "say" in P.witness(dev, str(repo), "Bash", ["x"], "k1")
    hand = _commit(repo, "hand.txt")
    got = TL.TOOLS["metrics"](q)["past_the_system"][0]
    assert (got["commits"], got["in_work"]) == ([hand], []), got
    Wt.install(repo, "dev")
    assert P.witness(dev, str(repo), "Bash", ["y"], "k2") == {}
    assert TL.TOOLS["metrics"](q)["past_the_system"][0]["in_work"] == [hand]


def test_a_finished_project_witnesses_nothing(repo):
    """CONTROL: the terminal root not read — the write is recorded and the agent told to stop."""
    e = _in_chat(repo)
    _cancelled(e)
    assert _call(e, repo, lambda: (repo / "a.txt").write_text("a")) == {}
    assert e.witnessed_writes() == []


def test_a_persons_edit_between_two_calls_is_no_calls(repo):
    """Each end is compared with its own call's start, never with the call before it (that blamed the person's editor,
    r4)."""
    e = _in_chat(repo)
    _deliver(e)
    assert _call(e, repo) == {}
    (repo / "mine.txt").write_text("the person's own editor")
    assert _call(e, repo) == {}
    assert e.witnessed_writes() == []


def test_of_two_calls_at_once_the_one_that_wrote_is_judged_against_its_own_start(repo):
    """Claude Code runs calls in parallel: the second starts after the first wrote. CONTROL: the reading kept per
    session, not per call — the second's start overwrites the first's, and the write is unseen."""
    e = _in_chat(repo)
    _deliver(e)
    ask = lambda project, body: P.witness(e, body["repository"], body["tool"], body["paths"])
    ev = lambda n, kind: {"tool_name": "Bash", "tool_use_id": n, "session_id": "s", "cwd": str(repo),
                          "hook_event_name": kind}
    Wt.observe(ev("a", "PreToolUse"), "p", ask)
    (repo / "a.txt").write_text("a")
    Wt.observe(ev("b", "PreToolUse"), "p", ask)
    assert Wt.observe(ev("a", "PostToolUse"), "p", ask), "the write of the first call went unseen"


def test_another_consoles_node_covers_no_write_and_one_write_seen_by_two_calls_is_recorded_once(repo):
    """The console is silent only where its own principal holds a node at work there; and overlapping calls that saw
    one write file it once (they multiplied `count`). CONTROL: `t.holder in me` dropped — the other's write is
    silenced; the `key` test dropped — two records."""
    e = _in_chat(repo)
    token = CALLER.set(Principal("other", ("other",), "t", "token"))
    try:
        ask = lambda project, body: P.witness(e, body["repository"], body["tool"], body["paths"], body["key"])
        ev = lambda n, kind: {"tool_name": "Bash", "tool_use_id": n, "cwd": str(repo), "hook_event_name": kind}
        Wt.observe(ev("a", "PreToolUse"), "p", ask)
        Wt.observe(ev("b", "PreToolUse"), "p", ask)
        (repo / "a.txt").write_text("a")
        assert Wt.observe(ev("a", "PostToolUse"), "p", ask) and Wt.observe(ev("b", "PostToolUse"), "p", ask)
    finally:
        CALLER.reset(token)
    assert len(e.witnessed_writes()) == 1, e.witnessed_writes()


def test_a_node_of_another_project_open_here_covers_its_holders_write(repo, tmp_path, monkeypatch):
    """The server holds every project: the console's node at work in another project on the repository covers its
    write. CONTROL: `_works` reading the asking project alone — the write is recorded."""
    e = _in_chat(repo)
    _deliver(e)
    q = _in_chat(repo, project="q")
    monkeypatch.setattr(P, "OPEN", lambda: [e, q])
    assert _call(e, repo, lambda: (repo / "a.txt").write_text("a")) == {}
    assert e.witnessed_writes() == []


def test_a_node_of_a_project_only_on_disk_covers_its_holders_write_and_its_record_is_not_opened(repo, tmp_path,
                                                                                              monkeypatch):
    """After a restart a project the server has not opened yet still holds its taken node: read from its record, no
    engine built. CONTROL: `_work_of` answering nothing for a path (only open projects read) — the write is
    recorded."""
    e = _in_chat(repo)
    _deliver(e)
    (data := tmp_path / "data").mkdir()
    q = _in_chat(repo, project="q", storage=SqliteStorage(str(data / "q.db")))
    q.stop()
    monkeypatch.setenv("GFSO_DATA_DIR", str(data))
    monkeypatch.setenv("GFSO_DB_PATH", str(data / "gfso.db"))
    reg = ProjectRegistry()
    reg._engines["p"] = e
    monkeypatch.setattr(P, "OPEN", reg.projects)
    assert str(data / "q.db") in map(str, reg.projects())
    assert _call(e, repo, lambda: (repo / "a.txt").write_text("a")) == {}
    assert e.witnessed_writes() == [] and set(reg._engines) == {"p"}, "q opened to be read"


def test_the_hook_takes_no_optional_lock_and_writes_no_index(repo):
    """A status beside the console's own `git commit` takes the index's lock it needs (`index.lock` exists) and
    rewrites the index. CONTROL: `--no-optional-locks` dropped — the index is rewritten."""
    f = repo / "README"
    st = f.stat()
    time.sleep(1.1)
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))      # …stat changed, content not: a refresh
    before = (repo / ".git" / "index").stat().st_mtime_ns
    assert Wt.tree(repo) == {}
    assert (repo / ".git" / "index").stat().st_mtime_ns == before, "the hook wrote the index"


def test_a_reading_whose_call_never_ended_is_removed_a_day_after(repo):
    """A denied or cut-short call has no Post: its reading would stay forever. CONTROL: `_drop_stale` not called at
    PreToolUse — the day-old reading stays."""
    d = repo / ".git" / "gfso-witness"
    d.mkdir()
    old, fresh = d / "gone.json", d / "kept.json"
    for x in (old, fresh):
        x.write_text("{}")
    os.utime(old, (time.time() - Wt.KEPT_S - 60,) * 2)
    Wt.observe({"tool_name": "Bash", "tool_use_id": "t", "cwd": str(repo), "hook_event_name": "PreToolUse"}, "p",
               lambda *a: {})
    assert not old.exists() and fresh.exists() and (d / "t.json").exists()


def test_a_failed_call_that_wrote_is_witnessed_too(repo):
    """CONTROL: `PostToolUseFailure` out of `EVENTS` — the write goes unseen."""
    e = _in_chat(repo)
    _deliver(e)
    out = _call(e, repo, lambda: (repo / "a.txt").write_text("a"), end="PostToolUseFailure")
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUseFailure"


def test_a_checkout_or_a_merge_that_leaves_the_tree_clean_is_no_write_nor_is_the_systems_own_door(repo):
    """A merge of what the system accepted moves HEAD and writes files git already holds: no status line changes.
    CONTROL: `OWN_DOOR` unread — the system's own move is charged."""
    e = _in_chat(repo)
    _deliver(e)
    _git(repo, "branch", "side")
    _git(repo, "switch", "-q", "side")
    _commit(repo, "s.txt")
    _git(repo, "switch", "-q", "main")
    assert _call(e, repo, lambda: _git(repo, "merge", "-q", "--ff-only", "side")) == {}
    assert _call(e, repo, lambda: _git(repo, "switch", "-q", "side")) == {}
    assert _call(e, repo, lambda: (repo / "a.txt").write_text("a"), tool="mcp__gfso__signal") == {}
    assert e.witnessed_writes() == []


def test_another_worktree_of_the_repository_is_the_same_repository(repo, tmp_path):
    """A node taken in the main checkout is at work in every worktree of the repository. CONTROL: `past.repository`
    naming the worktree's top — the write in the linked worktree is recorded."""
    e = _in_chat(repo)
    _git(repo, "worktree", "add", "-q", str(wt := tmp_path / "wt"), "-b", "w")
    assert _call(e, wt, lambda: (wt / "a.txt").write_text("a")) == {}
    assert e.witnessed_writes() == []


def test_it_is_installed_only_in_the_repositorys_own_settings_kept_out_of_git(repo):
    """Run twice, one entry per event; removed, the person's own hooks stay; the file git ignores. CONTROL: no exclude
    written — git sees the file."""
    s = repo / ".claude" / "settings.local.json"
    s.parent.mkdir()
    s.write_text(json.dumps({"hooks": {"PostToolUse": [{"matcher": "Edit", "hooks": [{"type": "command",
                                                                                      "command": "mine"}]}]}}))
    Wt.install(repo, "p")
    Wt.install(repo, "p")
    hooks = json.loads(s.read_text())["hooks"]
    assert {ev: sum(Wt.MARK in h["command"] for g in hooks[ev] for h in g["hooks"]) for ev in Wt.EVENTS} == {
        ev: 1 for ev in Wt.EVENTS}
    assert subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", ".claude/settings.local.json"]).returncode == 0
    assert _git(repo, "status", "--porcelain") == ""
    Wt.install(repo, "p", remove=True)
    assert json.loads(s.read_text()) == {"hooks": {"PostToolUse": [{"matcher": "Edit", "hooks": [
        {"type": "command", "command": "mine"}]}]}}


def test_a_hook_run_that_fails_says_nothing_and_exits_zero(monkeypatch, capsys):
    """CONTROL: `main` letting the error out — the person's console breaks."""
    monkeypatch.setattr(Wt, "observe", lambda *a: 1 / 0)
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    monkeypatch.setattr("sys.argv", ["witness", "p"])
    with pytest.raises(SystemExit) as ex:
        Wt.main()
    assert ex.value.code == 0 and capsys.readouterr().out == ""


def test_the_door_records_under_the_calls_credential(repo):
    """The hook's transport (`POST /api/witness`). CONTROL: the route unmounted — 404/405."""
    e = _in_chat(repo)
    _deliver(e)
    r = TestClient(create_app(e)).post("/api/witness", json={"project": "p", "repository": str(repo), "tool": "Edit",
                                                             "paths": ["a.txt"]})
    assert r.status_code == 200 and "say" in r.json(), r.text
    assert e.witnessed_writes()[-1]["actor"]
