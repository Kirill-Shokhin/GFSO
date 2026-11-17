"""IN_CHAT — a delivery made in the user's own chat is judged as the commit it handed in (§11.3), not as the directory
goes on to be.

The holder performs the node in its chat, in the user's repository; DELIVER came through the door with no commit, so the
judge copied the live directory, and anything written there after DELIVER was judged as delivered (the torn read
`snapshots` exists against). At DELIVER the system now keeps the commit the chat's repository stands on under a ref of
its own and the judge checks that commit out; what is not committed is no part of the delivery and is named, as only
what is committed enters a project.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import gfso.tools_llm as TL
from gfso.adapters.execution import LocalExecution
from gfso.adapters.snapshots import snapshot
from gfso.core.types import AgentId, Mode, TaskId
import gfso.tools as T
from tests.support import criterion, make_engine, REGISTER


@pytest.fixture(autouse=True)
def _a_roster_of_its_own(tmp_path, monkeypatch):
    """Each test registers its validator against its own repository; in the process's shared roster that role stood
    for every later test, and their chat deliveries were read in this file's repository (refused over its vendor/lib,
    7 tests of another file in one suite)."""
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))


def _git(repo, *a) -> str:
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout.strip()


def _commit(repo, *paths) -> str:
    _git(repo, "add", *paths)
    _git(repo, "-c", "user.name=u", "-c", "user.email=u@x", "commit", "-q", "-m", "work")
    return _git(repo, "rev-parse", "HEAD")


def _repo(tmp_path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "README").write_text("start\n")
    _commit(repo, "README")
    return repo


def _in_chat(tmp_path, repo):
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    assert not TL.TOOLS["register_agent"](e, "val-1", "llm-validator", workdir=str(repo)).get("refused")
    e.set_mode(Mode.SOLO, None, AgentId("user"), hands=None)
    T.create_task(e, "root", {"description": "write f", "accepted_risks": REGISTER,
                              "criteria": [criterion("f", "f.txt says v1")]})
    e.wait_idle()
    return e


def _delivered_v1(tmp_path):
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    (repo / "f.txt").write_text("v1\n")
    head = _commit(repo, "f.txt")
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="f.txt written", self_validation="PASS")
    return repo, e, head, out


def test_a_chat_delivery_is_its_committed_head_kept_and_what_is_not_committed_is_named(tmp_path):
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    (repo / "f.txt").write_text("v1\n")
    head = _commit(repo, "f.txt")
    (repo / "notes.txt").write_text("the user's own, never committed\n")
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="f.txt written", self_validation="PASS")
    assert out["accepted"] and "notes.txt" in out.get("not_delivered", ""), out
    got = e.delivered(TaskId("root"))
    assert got is not None and got[1] == head, f"an in_chat DELIVER recorded no commit, or another: {got}"
    assert _git(repo, "rev-parse", "HEAD") == head and _git(repo, "status", "--porcelain") == "?? notes.txt"
    assert head in _git(repo, "for-each-ref", "--format=%(objectname)", "refs/gfso/"), "the delivery is kept by no ref"
    assert "notes.txt" not in _git(repo, "ls-tree", "-r", "--name-only", head)


def test_the_judge_reads_the_delivery_not_what_was_written_after_it(tmp_path):
    repo, e, _, _ = _delivered_v1(tmp_path)
    (repo / "f.txt").write_text("v2 — written after DELIVER\n")
    with snapshot(repo, tmp_path / "judge", LocalExecution(), delivered=e.delivered(TaskId("root"))) as at:
        assert (Path(at) / "f.txt").read_text().strip() == "v1"


class _Reads:
    """A fake validator that reads f.txt where it is started, and reports nothing parseable (the cwd is the point)."""

    def __init__(self):
        self.cwd, self.read, self.calls = None, None, []

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.cwd = cwd
        self.read = (Path(cwd) / "f.txt").read_text().strip() if cwd and (Path(cwd) / "f.txt").is_file() else None
        self.calls.append({"duration_ms": 1, "output_tokens": 1})
        return "no report"

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def test_the_validator_of_a_chat_delivery_runs_in_its_checkout_not_in_the_users_tree(tmp_path):
    """Live 2026-11-13 (inchat-live-1113-1835): the commit was recorded and the lone validator still ran in the user's
    repository — a run alone on this host copied only a node's place — and judged the line written after DELIVER."""
    repo, e, _, _ = _delivered_v1(tmp_path)
    (repo / "f.txt").write_text("v2 — written after DELIVER\n")
    llm = _Reads()
    TL.validate_result(e, "root", _llm=llm)
    assert llm.cwd and Path(llm.cwd).resolve() != repo.resolve(), f"the validator ran in the user's tree: {llm.cwd}"
    assert llm.read == "v1", llm.read


def test_a_stray_repository_committed_is_refused_at_deliver_with_what_lifts_it(tmp_path):
    """A nested repository records only its commit: no checkout holds its files, so the judge would FAIL every delivery
    (critic over 1569a97) — refused at DELIVER instead, where the chat lifts it, nothing sent."""
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    (inner := repo / "vendor" / "lib").mkdir(parents=True)
    _git(inner, "init", "-q")
    (inner / "x").write_text("x\n")
    _commit(inner, "x")
    _commit(repo, "vendor/lib")
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="done", self_validation="PASS")
    assert not out["accepted"] and "vendor/lib" in out["error"] and "git rm --cached" in out["error"], out
    assert e.graph.get_state(TaskId("root")).name == "EXECUTING"


def test_the_users_own_submodule_is_no_stray(tmp_path):
    """A gitlink the user's HEAD already records is theirs: the delivery carries it as their commit does."""
    repo = _repo(tmp_path)
    (inner := tmp_path / "sub").mkdir()
    _git(inner, "init", "-q")
    (inner / "y").write_text("y\n")
    _commit(inner, "y")
    _git(repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(inner), "sub")
    _git(repo, "-c", "user.name=u", "-c", "user.email=u@x", "commit", "-q", "-m", "sub")
    e = _in_chat(tmp_path, repo)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    (repo / "f.txt").write_text("v1\n")
    _commit(repo, "f.txt")
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="done", self_validation="PASS")
    assert out["accepted"] and e.delivered(TaskId("root")), out


def test_a_judge_below_the_repositorys_top_is_said_not_recorded(tmp_path):
    repo = _repo(tmp_path)
    (sub := repo / "sub").mkdir()
    e = _in_chat(tmp_path, sub)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="done", self_validation="PASS")
    assert out["accepted"] and "not the top of a git repository" in out.get("not_recorded", ""), out


def test_a_deliver_the_machine_refuses_records_nothing(tmp_path):
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="before consent")
    assert not out["accepted"] and not _git(repo, "for-each-ref", "refs/gfso/"), "a refused DELIVER moved a ref"
