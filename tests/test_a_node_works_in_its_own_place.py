"""A node executed by a registered executor works in a place of its own, and its delivery is what is validated.

The executors of one plan registered on one directory shared its live tree while the dispatcher ran them in
parallel, so a validator's build read a sibling's half-edited file — a torn read (§8.6): a false FAIL, or a PASS
over a tree that is not the node's delivery. Where the registered directory is a git repository, each node's
session runs in its own worktree, its delivery is a commit (§11.3), its validation reads that worktree, and a part
that PASSes joins where its parent works; a conflict is the whole's to integrate (§8.7, the glue), named in its
packet. A directory that is not a repository behaves as before. Fake agent runners, real git.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

from gfso import delegate, tools as T, tools_llm as TL
from gfso.adapters import worktrees as W
from gfso.adapters.llm.stub import StubLLM
from gfso.core.protocol.procedure import probe_id
from gfso.core.types import PlaceUnavailable, State, TaskId, nodes_root
from gfso.delegate import Dispatcher, _auto_validate
from gfso.engine.joins import NOT_ON_ITS_BRANCH, Joins
from gfso.sessions import run_consent, run_executor
from gfso.workspaces import _ensure_place, _workspace, land_accepted, left_to_merge, node_workspace
from gfso.roster import AgentRegistry
from tests import test_one_session_carries_a_scope as S
from tests.support import criterion, instrument_passes, make_engine, REGISTER

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="the node workspaces are git worktrees")

_RISK = REGISTER


def _git(cwd, *args) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout.strip()


def _repo(path: Path) -> Path:
    path.mkdir(exist_ok=True)
    (path / "README").write_text("starter\n")
    for args in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "starter")):
        _git(path, *args)
    return path


def _fenced(payload) -> str:
    return "```json\n" + json.dumps(payload) + "\n```"


class _Executor:
    """One executor session: writes its files where it was started, meets the other sessions there (so they run
    at once), reads what its directory holds, and delivers."""

    def __init__(self, tid, files, meet=None):
        self.tid, self.files, self.meet = tid, files, meet
        self.cwd = self.packet = None
        self.saw: set = set()
        self.calls: list = []

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.cwd, self.packet = cwd, user
        self.calls.append({"duration_ms": 1, "output_tokens": 1})
        for name, text in self.files.items():
            (Path(cwd) / name).write_text(text)
        if self.meet is not None:
            self.meet.wait(20)
        self.saw = {p.name for p in Path(cwd).iterdir()}
        return _fenced({"status": "delivered", "summary": f"{self.tid}: written", "self_validation": "PASS"})

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


class _Validator:
    """One validation: says where it stood, and passes the node's criteria on their pinned probes."""

    def __init__(self, e, tid, where: dict):
        self.e, self.tid, self.where, self.calls = e, str(tid), where, []

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.where[self.tid] = cwd
        self.calls.append({"duration_ms": 1, "output_tokens": 1})
        crits = [c.name for c in self.e.graph.get_task(TaskId(self.tid)).spec.criteria]
        parts = self.e.parts_procedure(TaskId(self.tid))      # the DONE parts' pinned checks, as the packet hands them
        return _fenced({"verdict": "PASS", "failed_criteria": [], "per_criterion": [
            {"criterion": c, "verdict": "pass", "evidence": "ran it: it holds", "behaviours": [f"{c} holds"],
             "probe": [{"command": f"check {c}", "expect": "it holds", "behaviour": f"{c} holds"}]
             + [{"id": probe_id(pc.name, p), "command": p.command, "expect": p.expect, "behaviour": p.behaviour}
                for pc in parts.get(c, ()) for p in (pc.check or ())]} for c in crits]})

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def _plan(tmp_path, git=True, whole="kirill"):
    """A whole (`whole` executes it) over two parts held by two registered executors on one directory."""
    base = _repo(tmp_path / "ws") if git else (tmp_path / "ws")
    base.mkdir(exist_ok=True)
    e = make_engine(llm=StubLLM(), validate_signals=True)
    e.start()
    e.project_name = "p"
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    for aid, kind in (("exec-1", "llm-executor"), ("exec-2", "llm-executor"), ("exec-3", "llm-executor"),
                      ("val-1", "llm-validator")):
        agents.register(aid, kind, workdir=str(base), project="p")
    T.create_task(e, "par", {"description": "the whole", "criteria": [criterion("g", "G holds")]}, assignee=whole)
    T.decompose(e, "par", [{"task_id": tid, "spec": {"description": f"part {tid}", "criteria": [criterion(f"{tid}_ok")]},
                            "assignee": ex, "covers": ["g"]} for tid, ex in (("a", "exec-2"), ("b", "exec-3"))],
                accepted_risks=_RISK)
    if whole == "exec-1":
        T.signal(e, "par", "ACCEPT", "exec-1")
    return e, agents, base


def _drive(e, d, until, bound: float = 90.0) -> None:
    """The dispatcher's rounds until `until` holds, bounded by wall time, not by a count of rounds: a round's length is
    the machine's (a git child per session on a loaded runner), so a count measured something else than the wait."""
    end = time.monotonic() + bound
    while not until():
        assert time.monotonic() < end, f"not reached in {bound}s: {({t.id: t.state.name for t in e.all_tasks()})}"
        d.dispatch_once()
        time.sleep(0.05)
        e.wait_idle()


def _run(e, agents, sessions: dict, until, validated: dict | None = None):
    d = Dispatcher(e, agents, poll=30,
                   runner=lambda en, t, ex, ag: run_executor(en, t, ex, ag, _llm=sessions[str(t)]),
                   validator_runner=lambda en, t, ag, **k: _auto_validate(
                       en, t, ag, _llm=_Validator(en, t, validated if validated is not None else {}), **k))
    _drive(e, d, until)
    return d


def _until(pred, timeout=20.0) -> None:
    end = time.monotonic() + timeout

    def holds():
        try:
            return pred()
        except subprocess.CalledProcessError:    # a git read beside the system's own ref work: not yet, the bound decides
            return False
    while not holds():
        assert time.monotonic() < end, "not reached in time"
        time.sleep(0.05)


def _in(e, *tids, states=(State.VALIDATING, State.DONE)):
    return lambda: all(e.graph.get_state(TaskId(t)) in states for t in tids)


def test_two_parts_run_at_once_each_in_its_own_tree(tmp_path):
    e, agents, base = _plan(tmp_path)
    meet = threading.Barrier(2)
    sessions = {"a": _Executor("a", {"a.c": "A\n"}, meet), "b": _Executor("b", {"b.c": "B\n"}, meet)}
    _run(e, agents, sessions, _in(e, "a", "b"))
    places = nodes_root(base) / "p"
    assert not (base.parent / ".gfso-nodes-ws").exists(), "nothing beside the user's repository"
    assert sessions["a"].cwd == str(places / "a") and sessions["b"].cwd == str(places / "b")
    assert "a.c" in sessions["a"].saw and "a.c" not in sessions["b"].saw, "a sibling's edit is not in my tree"
    assert "b.c" in sessions["b"].saw and "b.c" not in sessions["a"].saw
    assert f"Working directory: {places / 'a'}" in sessions["a"].packet
    # the delivery is a commit, its executor's, naming the node
    assert _git(base, "log", "-1", "--format=%an|%s", "gfso/p/a") == "exec-2|gfso: a delivery"
    assert _git(base, "show", "gfso/p/a:a.c") == "A"


def test_a_nodes_validator_reads_that_nodes_own_tree(tmp_path):
    e, agents, _ = _plan(tmp_path, whole="exec-1")      # a system issuer, which signs its instrument's verdict
    sessions = {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"}), "par": _Executor("par", {})}
    where: dict = {}
    _run(e, agents, sessions, _in(e, "a", "b", states=(State.DONE,)), validated=where)
    # …each in a COPY of that node's own tree (§10.3: the validator must not be able to change what it judges)
    assert all(where[k].endswith("delivery") and f".gfso-scratch-{k}" in where[k] for k in ("a", "b")), where
    assert node_workspace(e, agents, "a") == sessions["a"].cwd


def _as_it_stands(base: Path) -> dict:
    """The user's repository as they hold it, read without git (a read of git's may refresh the index): the branch
    checked out, its commit, the index's bytes and every file of the working tree."""
    head = (base / ".git" / "HEAD").read_text()
    branch = head.split("refs/heads/", 1)[1].strip()
    return {"HEAD": head, "commit": (base / ".git" / "refs" / "heads" / branch).read_text(),
            "index": (base / ".git" / "index").read_bytes(),
            "tree": {str(p.relative_to(base)): p.read_bytes() for p in base.rglob("*")
                     if p.is_file() and ".git" not in p.relative_to(base).parts}}


def test_a_hosts_root_lands_as_its_accepted_branch_and_leaves_the_users_tree_as_it_was(tmp_path):
    """An executor with no execution works on this host, and the base is the user's own repository: every node's work,
    the root's too, stands in a place of the system's, and the root's PASS lands its accepted commit as the branch
    `gfso/<project>/accepted` — their checked-out branch, its index and its tree as they were (the promise of
    ORCHESTRATOR.md "Where it runs"; the root's merge into their branch held it by a line asking for `git switch`)."""
    e, agents, base = _plan(tmp_path, whole="exec-1")
    before = _as_it_stands(base)
    sessions = {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"}),
                "par": _Executor("par", {"par.c": "the whole\n"})}
    _run(e, agents, sessions, _in(e, "par", states=(State.DONE,)))
    places = nodes_root(base) / "p"
    assert sessions["par"].cwd == str(places / "par")
    assert {"a.c", "b.c"} <= sessions["par"].saw, "the whole's session sees its parts, joined"
    _until(lambda: e.next_steps()["complete"] is True and not places.joinpath("par").exists())
    assert _as_it_stands(base) == before, "the user's branch, index or tree was written"
    tree, _ = e.accepted_delivery(TaskId("par"))
    assert _git(base, "rev-parse", "gfso/p/accepted^{tree}") == tree
    assert {_git(base, "show", f"gfso/p/accepted:{f}") for f in ("a.c", "b.c", "par.c")} == {"A", "B", "the whole"}
    assert {"gfso: a joins par", "gfso: b joins par"} <= set(_git(base, "log", "--format=%s", "gfso/p/accepted").splitlines())
    # …and the joined places go, their branches with them: what they held is on the accepted branch
    _until(lambda: _git(base, "branch", "--list", "gfso/*") == "gfso/p/accepted")
    assert not any(places.joinpath(t).exists() for t in ("a", "b", "par"))
    e.stop()


class _Merger(_Executor):
    """The whole's session that does its integration: merges every branch its packet names, the part's side winning."""

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        for b in re.findall(r"on branch `([^`]+)`", user):
            _git(cwd, "merge", "--no-edit", "-X", "theirs", b)
        return super().run_agent(system, user, allowed_tools, cwd=cwd, timeout=timeout)


class _HalfMerger(_Executor):
    """The whole's session that starts the merge its packet names, meets the conflict, and delivers without resolving."""

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        for b in re.findall(r"on branch `([^`]+)`", user):
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "merge", "--no-edit", b], cwd=cwd,
                           capture_output=True)
        return super().run_agent(system, user, allowed_tools, cwd=cwd, timeout=timeout)


def test_a_whole_that_leaves_a_merge_unresolved_is_not_delivered(tmp_path):
    """Committed as it stood, the half-done merge concluded with the conflict markers in the files and the tree then
    contained the part's branch, so the hold let it through (finder over 190f4db)."""
    e, agents, base, said, sessions = _conflicting(tmp_path, _HalfMerger("par", {}))
    _run(e, agents, sessions, lambda: any("merge left unfinished" in m for m in said))
    assert e.graph.get_state(TaskId("par")) in (State.EXECUTING, State.REWORKING)
    e.stop()


class _Nester(_Executor):
    """A part's session that delivers a nested repository — `inner_commit` or not — and, once its packet names the
    refusal, does what it says: deletes the inner `.git`, untracks the gitlink where there is one, delivers again."""

    def __init__(self, tid, files, inner_commit=True):
        super().__init__(tid, files)
        self.inner_commit = inner_commit

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        dep = Path(cwd) / "dep"
        if "git rm --cached <path>" in user:
            shutil.rmtree(dep / ".git", onerror=lambda f, p, _: (Path(p).chmod(0o700), f(p)))
            subprocess.run(["git", "rm", "-q", "--cached", "dep"], cwd=cwd, capture_output=True)
        elif not dep.exists():
            dep.mkdir()
            (dep / "d.c").write_text("D\n")
            _git(dep, "init", "-q")
            if self.inner_commit:
                _git(dep, "add", "-A")
                _git(dep, "commit", "-q", "-m", "inner")
        return super().run_agent(system, user, allowed_tools, cwd=cwd, timeout=timeout)


@pytest.mark.parametrize("inner_commit, checked, cause", [
    (True, True, "nested git repositories"), (True, False, "nested git repositories"),
    (False, True, "could not be staged")],
    ids=["refused at DELIVER", "control: no check at DELIVER", "an inner repository with no commit: unstaged, held"])
def test_a_delivery_holding_a_nested_repository_is_refused_with_its_cause_until_lifted(tmp_path, monkeypatch,
                                                                                         inner_commit, checked, cause):
    """§12.16 (ii): refused only at the judge's copy, the node was re-asked blind until it escalated — its executor
    never told what to lift; with no commit inside, staging failed unread and the delivery went in without the files.
    Held at DELIVER, named in its next packet, and lifted by the executor's own moves, it is then judged."""
    if not checked:
        monkeypatch.setattr("gfso.reports.W.nested", lambda *a, **k: [])
    e, agents, base = _plan(tmp_path)
    said: list = []
    e.on_info(lambda src, msg: said.append(msg))
    where: dict = {}
    sessions = {"a": _Nester("a", {"a.c": "A\n"}, inner_commit), "b": _Executor("b", {"b.c": "B\n"})}
    d = _run(e, agents, sessions, lambda: any("delivery held" in m for m in said)
             or any(x.signal.name == "DELIVER" for x in e.audit_log(TaskId("a"))), validated=where)
    assert checked == any("NOT delivered" in m and cause in m and "(dep)" in m for m in said)
    if checked:
        assert e.graph.get_state(TaskId("a")) in (State.EXECUTING, State.REWORKING)
        assert not any(x.signal.name == "DELIVER" for x in e.audit_log(TaskId("a"))), "nothing recorded as delivered"
        # …by the SAME dispatcher: the held round's retry may already be claimed by it (the hold lands while a round
        # runs), and a second one on this engine claimed it again — two sessions of `a` in one place, the later one's
        # packet, built over the lifted delivery, read here
        _drive(e, d, lambda: "a" in where)
        assert "NOT handed in" in sessions["a"].packet and cause in sessions["a"].packet
        assert _git(base, "show", "gfso/p/a:dep/d.c") == "D", "its files are in the delivered tree"
    e.stop()


def _conflicting(tmp_path, whole):
    e, agents, base = _plan(tmp_path, whole="exec-1")
    said: list = []
    e.on_info(lambda src, msg: said.append(msg))
    sessions = {"a": _Executor("a", {"shared.c": "A\n"}), "b": _Executor("b", {"shared.c": "B\n"}), "par": whole}
    return e, agents, base, said, sessions


def test_a_whole_that_does_not_merge_a_conflicting_part_is_not_delivered(tmp_path):
    """G13's shape (GB_sql_database_tn03ao788): the root's executor, told to merge parts that conflicted, rewrote
    their files instead and delivered a tree without a part's work."""
    e, agents, base, said, sessions = _conflicting(tmp_path, _Executor("par", {}))
    _run(e, agents, sessions, lambda: any("delivery held" in m for m in said))
    named = [b for b in ("gfso/p/a", "gfso/p/b") if f"on branch `{b}`" in sessions["par"].packet]
    assert len(named) == 1 and "Parts NOT joined into your workspace" in sessions["par"].packet
    assert e.graph.get_state(TaskId("par")) in (State.EXECUTING, State.REWORKING), "handed in without its part's work"
    # the merge was aborted where it ran: the base holds no conflict markers
    assert _git(base, "status", "--porcelain") == ""
    e.stop()


def test_a_whole_that_merges_its_conflicting_part_is_delivered_with_both(tmp_path):
    """The control: the same plan, the whole's session merging what its packet names — DONE, and both parts' work
    reach the accepted branch."""
    e, agents, base, said, sessions = _conflicting(tmp_path, _Merger("par", {}))
    _run(e, agents, sessions, _in(e, "par", states=(State.DONE,)))
    _until(lambda: e.next_steps()["complete"] is True)
    assert "Parts NOT joined into your workspace" in sessions["par"].packet
    assert not any("delivery held" in m for m in said)
    named = [b for b in ("gfso/p/a", "gfso/p/b") if f"on branch `{b}`" in sessions["par"].packet]
    assert _git(base, "show", "gfso/p/accepted:shared.c") == ("A" if named == ["gfso/p/a"] else "B")
    e.stop()


def test_a_directory_that_is_not_a_repository_is_refused_at_the_go(tmp_path, door):
    """A base with no git: shared by every node, no delivery from it had a commit to be judged by, and its sessions
    were paid for with no verdict possible. The go is refused with the lift — the person's agent makes it a
    repository —, and the system makes none of the directory."""
    e, agents, base = _plan(tmp_path, git=False, whole="exec-1")
    out = TL._no_place_at_the_go(e)
    assert out and "git init" in out["error"], out
    assert not (base / ".git").exists()


def test_a_scopes_session_and_its_validation_share_the_scopes_one_tree(tmp_path):
    _repo(tmp_path)
    e, agents = S._project(tmp_path)
    where: dict = {}

    class _Session(S._LLM):
        def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
            where["session"] = cwd
            (Path(cwd) / "scope.c").write_text("built\n")
            return super().run_agent(system, user, allowed_tools, cwd, timeout)

    class _Check(S._Validator):
        def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
            where["validation"] = cwd
            return super().run_agent(system, user, allowed_tools, cwd, timeout)

    executor, validator = _Session(S._delivered("root.a", "root.b", "root")), _Check(e)
    _drive(e, S._dispatcher(e, agents, executor, validator, []), lambda: e.graph.get_state(TaskId("root")) == State.DONE)
    place = nodes_root(tmp_path) / "p" / "root"
    assert where["session"] == str(place)
    assert where["validation"].endswith("delivery") and ".gfso-scratch-root" in where["validation"], where
    # one tree, a commit per node's delivery in build order; its parts join nothing (their whole works there), and
    # the top, at its PASS, lands as the accepted branch, the user's own untouched
    _until(lambda: not place.exists() and e.next_steps()["complete"] is True)
    assert not (tmp_path / "scope.c").exists()
    assert _git(tmp_path, "log", "--format=%s", "-4", "gfso/p/accepted").splitlines() == [
        "gfso: root delivery", "gfso: root.b delivery", "gfso: root.a delivery", "starter"]


def test_a_delivery_commits_no_cache_a_sibling_would_collide_on(tmp_path):
    """Two sessions importing one shared module each leave its bytecode cache; committed, the second join conflicts on
    it, and one left in the base aborts the join (critic r2, 2026-10-04). A delivery is everything but caches."""
    base = _repo(tmp_path / "ws")
    place = tmp_path / "place"
    W.ensure(base, place, "gfso/p/a", base)
    (place / "a.py").write_text("x = 1\n")
    (place / "__pycache__").mkdir()
    (place / "__pycache__" / "common.cpython-311.pyc").write_bytes(b"\0")
    (place / "lib.o").write_bytes(b"\0")
    W.commit_all(base, place, "gfso: a delivery", "exec-1", branch="gfso/p/a")
    assert _git(base, "ls-tree", "-r", "--name-only", "gfso/p/a").splitlines() == ["README", "a.py"]


def test_a_whole_is_not_validated_over_parts_still_joining(tmp_path, monkeypatch):
    """A part's join runs off the signal path; until it lands, its whole is not validated over a place without it, and
    the root's DONE is not `complete` until the base holds the root's result (critic r2, 2026-10-04)."""
    gate, real = threading.Event(), delegate.join_whole
    monkeypatch.setattr(delegate, "join_whole", lambda *a: (gate.wait(20), real(*a))[1])
    e, agents, base = _plan(tmp_path)                  # the whole is a person's
    T.signal(e, "par", "ACCEPT", "kirill")
    sessions = {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"})}
    d = _run(e, agents, sessions, _in(e, "a", "b"))
    for t in ("a", "b"):
        if e.graph.get_state(TaskId(t)) == State.VALIDATING:
            instrument_passes(e, t, "validator")
            T.signal(e, t, "PASS", "kirill")
    e.wait_idle()
    _until(lambda: set(e.joins.joining_nodes()) == {"a", "b"})
    assert not d._children_settled(TaskId("par")), "a whole is not validated over parts still joining"
    gate.set()
    _until(lambda: e.joins.joining_nodes() == [])
    assert d._children_settled(TaskId("par"))
    e.stop()


def test_the_root_is_not_complete_while_its_result_is_joining_the_base():
    """`complete` is read as "the base holds the result" — the E3 arm scores the base on it (critic r2, 2026-10-04)."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g")]}, assignee="me")
    T.signal(e, "root", "ACCEPT", "me")
    T.signal(e, "root", "DELIVER", "me", result="done")
    e.wait_idle()
    instrument_passes(e, "root", "validator")
    e.joins.mark_joining("root", True)
    T.signal(e, "root", "PASS", "me")
    e.wait_idle()
    assert e.graph.get_state(TaskId("root")) == State.DONE
    out = e.next_steps()
    assert out["complete"] is False and any(w["task_id"] == "root" for w in out["in_flight"])
    assert e.next_steps(TaskId("root"))["complete"] is False, "asked by the root's name too"
    e.joins.mark_joining("root", False)
    assert e.next_steps()["complete"] is True and e.next_steps(TaskId("root"))["complete"] is True
    e.stop()


def _accepted_checked_out(tmp_path, base) -> Path:
    """The user works on `gfso/p/accepted` in a worktree of theirs: the system lands only on a branch nobody works on."""
    _git(base, "branch", "gfso/p/accepted")
    _git(base, "worktree", "add", "-q", str(wt := tmp_path / "users-wt"), "gfso/p/accepted")
    return wt


def test_a_root_whose_result_did_not_land_is_not_complete_until_it_does(tmp_path, monkeypatch):
    """A refused landing is not a landed one: the accepted branch checked out in a worktree of the user's refuses it,
    and `complete` waits — named with the branch that holds the result, stuck, retried — until it lands (critic r3,
    2026-10-04: the refused join read as complete)."""
    monkeypatch.setattr(delegate, "JOIN_RETRY_S", 0)    # the backoff has its own test
    e, agents, base = _plan(tmp_path, whole="exec-1")
    wt = _accepted_checked_out(tmp_path, base)
    sessions = {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"}),
                "par": _Executor("par", {"par.c": "the whole\n"})}
    d = _run(e, agents, sessions, _in(e, "par", states=(State.DONE,)))
    _until(lambda: "par" in e.joins.unjoined_roots())
    out = e.next_steps()
    assert out["complete"] is False and out["stuck"] is True and "did not land" in out["directive"], out
    assert "gfso/p/par" in out["directive"], "the branch that holds the result is named (critic r4)"
    gate, real = threading.Event(), W.land
    monkeypatch.setattr(W, "land", lambda *a, **k: (gate.wait(20), real(*a, **k))[1])
    d.dispatch_once()                                   # WHILE a retry runs, the refusal still stands (critic r4)
    _until(lambda: "par" in e.joins.joining_nodes())
    assert e.next_steps()["stuck"] is True, "a retry erased the refusal: the root read 'being joined'"
    gate.set()
    _until(lambda: not e.joins.joining_nodes())
    monkeypatch.setattr(W, "land", real)
    assert e.next_steps()["stuck"] is True
    _git(base, "worktree", "remove", str(wt))           # the branch is freed, by whoever holds it
    d.dispatch_once()
    _until(lambda: not e.joins.unjoined_roots() and not e.joins.joining_nodes())
    assert _git(base, "show", "gfso/p/accepted:par.c") == "the whole" and e.next_steps()["complete"] is True
    assert not (base / "par.c").exists()


def test_a_held_whole_is_not_told_to_aggregate_over_parts_still_joining(tmp_path, monkeypatch):
    """The frontier and the validation door read a whole over its parts only once their results stand where it works
    (critic r3, 2026-10-04: SEMI's AGGREGATE step and `validate_result` read the base ahead of the merges)."""
    gate = threading.Event()
    real = W.merge
    monkeypatch.setattr(W, "merge", lambda *a, **k: (gate.wait(20), real(*a, **k))[1])
    e, agents, base = _plan(tmp_path)
    T.signal(e, "par", "ACCEPT", "kirill")
    _run(e, agents, {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"})}, _in(e, "a", "b"))
    for t in ("a", "b"):
        if e.graph.get_state(TaskId(t)) == State.VALIDATING:
            instrument_passes(e, t, "validator")
            T.signal(e, t, "PASS", "kirill")
    e.wait_idle()
    _until(lambda: set(e.joins.joining_nodes()) == {"a", "b"})
    step = e.next_step(TaskId("par"))
    assert "AGGREGATE" not in step.get("directive", ""), step
    gate.set()
    _until(lambda: e.joins.joining_nodes() == [])
    assert "AGGREGATE" in e.next_step(TaskId("par")).get("directive", "")
    e.stop()


def test_a_refused_root_join_is_retried_less_often_each_time(tmp_path, monkeypatch):
    """Every try is a landing in the user's own repository, and a refusal waits on a person: the retry backs off
    instead of spinning with the dispatch loop (critic r4, 2026-10-04: about four tries a second)."""
    e, agents, base = _plan(tmp_path, whole="exec-1")
    _accepted_checked_out(tmp_path, base)
    sessions = {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"}),
                "par": _Executor("par", {"par.c": "the whole\n"})}
    d = _run(e, agents, sessions, _in(e, "par", states=(State.DONE,)))
    _until(lambda: "par" in e.joins.unjoined_roots() and not e.joins.joining_nodes())
    tries = []
    real = W.land
    monkeypatch.setattr(W, "land", lambda *a, **k: (tries.append(a[1]), real(*a, **k))[1])
    for _ in range(20):
        d.dispatch_once()
        time.sleep(0.01)
    assert tries == [], f"retried inside its delay: {tries}"
    first = d._retry_at["par"][1]
    d._retry_at["par"] = (0, first)                     # the delay has run out
    d.dispatch_once()
    _until(lambda: tries and not e.joins.joining_nodes())
    assert d._retry_at["par"][1] == 2 * first, "the next delay doubles"
    e.stop()


def test_a_root_is_complete_only_on_the_word_that_its_result_landed():
    """Where a join is owed, `complete` reads the host's word that the result LANDED — not the absence of a join
    mark, which a reader sees between the root's DONE and the host's mark, and after a restart (critic r4)."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g")]}, assignee="me")
    e.joins.set_join_owed(lambda t: str(t.id) == "root")
    T.signal(e, "root", "ACCEPT", "me")
    T.signal(e, "root", "DELIVER", "me", result="done")
    e.wait_idle()
    instrument_passes(e, "root", "validator")
    T.signal(e, "root", "PASS", "me")                   # DONE, and no host has marked anything yet
    e.wait_idle()
    out = e.next_steps(TaskId("root"))
    assert out["complete"] is False and out["stuck"] is False, out
    assert e.next_steps()["complete"] is False
    e.joins.mark_joining("root", True)
    e.joins.mark_joining("root", False)                       # landed
    assert e.next_steps()["complete"] is True and e.next_steps(TaskId("root"))["complete"] is True
    e.stop()


def test_a_held_whole_is_told_which_parts_to_merge_and_on_what_branch(tmp_path):
    """A whole its holder performs in their own tree on this host has no place of the system's, and the system merges
    nothing into the user's repository: each passed part ends its join on its own branch, and the whole's AGGREGATE step
    names it with the commit to merge, since integrating it is the whole's work (§8.7) — told only "all children
    passed", a holder aggregates without it (critic r4, 2026-10-04)."""
    e, agents, base = _plan(tmp_path)
    before = _as_it_stands(base)
    T.signal(e, "par", "ACCEPT", "kirill")
    _run(e, agents, {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"})}, _in(e, "a", "b"))
    for t in ("a", "b"):
        if e.graph.get_state(TaskId(t)) == State.VALIDATING:
            instrument_passes(e, t, "validator")
            T.signal(e, t, "PASS", "kirill")
    e.wait_idle()
    _until(lambda: not e.joins.joining_nodes() and "AGGREGATE" in e.next_step(TaskId("par")).get("directive", ""))
    step = e.next_step(TaskId("par"))["directive"]
    assert all(f"on `gfso/p/{t}`" in step and f"`git merge {_git(base, 'rev-parse', f'gfso/p/{t}')}`" in step
               for t in ("a", "b")), step
    assert _as_it_stands(base) == before, "the user's branch, index or tree was written"
    e.stop()


def test_a_held_whole_is_told_its_parts_to_merge_by_a_process_started_after_they_passed(tmp_path):
    """What a held whole still has to merge is read from the record and git, not kept in memory: a server restarted
    after its parts passed told it to aggregate with no part named (critic). A part its holder merged is named no more."""
    e, agents, base = _plan(tmp_path)
    T.signal(e, "par", "ACCEPT", "kirill")
    _run(e, agents, {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"})}, _in(e, "a", "b"))
    for t in ("a", "b"):
        if e.graph.get_state(TaskId(t)) == State.VALIDATING:
            instrument_passes(e, t, "validator")
            T.signal(e, t, "PASS", "kirill")
    e.wait_idle()
    _until(lambda: not e.joins.joining_nodes() and e.graph.get_state(TaskId("b")) == State.DONE)
    e.joins = Joins(e.graph)                            # …the process that passed them is gone
    Dispatcher(e, agents, runner=lambda *a: None)
    step = e.next_step(TaskId("par"))["directive"]
    assert "AGGREGATE" in step and all(f"on `gfso/p/{t}`" in step for t in ("a", "b")), step
    _git(base, "merge", "-q", "--no-edit", "gfso/p/a")  # …the holder's own move, in their own tree
    step = e.next_step(TaskId("par"))["directive"]
    assert "gfso/p/a" not in step and "on `gfso/p/b`" in step, step
    e.stop()


def test_a_part_whose_whole_works_over_another_repository_is_named_with_where_its_commit_is(tmp_path):
    """Its accepted commit is in its own base alone: `git merge <sha>` where the whole works named an object that
    repository did not have (critic) — now the commit is read by its id from the project's store into that repository,
    and the merge named there is one it can make."""
    e, agents, base = _plan(tmp_path, whole="exec-1")
    other = _repo(tmp_path / "other")
    agents.register("exec-1", "llm-executor", workdir=str(other), project="p")
    sessions = {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"}), "par": _Executor("par", {})}
    _run(e, agents, sessions, _in(e, "a", "b", states=(State.DONE,)))
    named = dict(left_to_merge(e, agents, e.graph.get_task(TaskId("par"))))
    assert set(named) == {"a", "b"}, named
    sha = re.search(r"`git merge (\w+)`", named["a"]).group(1)
    assert _git(_workspace(e, agents, e.graph.get_task(TaskId("par")))[0], "cat-file", "-t", sha) == "commit", named["a"]
    # …and once merged where the whole works it is named no more (its AGGREGATE repeated it). CONTROL: test the
    # part's own base instead of the whole's tree in `left_to_merge` and "a" stays named.
    place = _workspace(e, agents, e.graph.get_task(TaskId("par")))[0]
    for argv in (["fetch", str(base), "gfso/p/a"], ["merge", "--no-edit", "--allow-unrelated-histories", "FETCH_HEAD"]):
        # …a merge makes a commit: an identity of its own — CI's Windows runner has none ("Committer identity unknown")
        got = subprocess.run(["git", "-C", str(place), "-c", "user.name=t", "-c", "user.email=t@t", *argv],
                             capture_output=True, text=True)
        assert got.returncode == 0, (argv, got.stderr)
    assert set(dict(left_to_merge(e, agents, e.graph.get_task(TaskId("par"))))) == {"b"}
    e.stop()


def test_a_whole_a_person_holds_under_a_system_root_joins_the_roots_result_with_its_parts(tmp_path, door):
    """ONE rule, whatever performed a node: its delivered commit joins its whole's place. A whole the person holds in
    their own tree, under a root the system holds, is named its parts to merge; its delivery — the commit its DELIVER
    recorded — joins the root's place like any part's branch. It joined nothing, and the accepted result held only the
    system's leaf and the root: the person's whole and both its parts dropped out (critic, a control at its parent)."""
    base = _repo(tmp_path / "ws")
    e = make_engine(llm=StubLLM(), validate_signals=True)
    e.start()
    e.project_name = "p"
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    for aid, kind in (("exec-1", "llm-executor"), ("exec-2", "llm-executor"), ("exec-3", "llm-executor"),
                      ("exec-4", "llm-executor"), ("val-1", "llm-validator")):
        agents.register(aid, kind, workdir=str(base), project="p")
    T.create_task(e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]}, assignee="exec-1")
    T.decompose(e, "root", [{"task_id": "c", "spec": {"description": "a leaf", "criteria": [criterion("c_ok")]},
                             "assignee": "exec-4", "covers": ["g"]},
                            {"task_id": "mid", "spec": {"description": "the person's whole", "criteria": [criterion("m")]},
                             "assignee": "kirill", "covers": ["g"]}], accepted_risks=_RISK)
    T.decompose(e, "mid", [{"task_id": t, "spec": {"description": f"part {t}", "criteria": [criterion(f"{t}_ok")]},
                            "assignee": ex, "covers": ["m"]} for t, ex in (("a", "exec-2"), ("b", "exec-3"))],
                accepted_risks=_RISK)
    T.signal(e, "root", "ACCEPT", "exec-1")
    T.signal(e, "mid", "ACCEPT", "kirill")
    sessions = {t: _Executor(t, {f"{t}.c": f"{t.upper()}\n"}) for t in ("a", "b", "c", "root")}
    d = _run(e, agents, sessions, lambda: _in(e, "a", "b")() and _in(e, "c", states=(State.DONE,))())
    for t in ("a", "b"):
        if e.graph.get_state(TaskId(t)) == State.VALIDATING:
            instrument_passes(e, t, "validator")
            T.signal(e, t, "PASS", "kirill")
    e.wait_idle()
    _until(lambda: not e.joins.joining_nodes() and len(left_to_merge(e, agents, e.graph.get_task(TaskId("mid")))) == 2)
    for _, why in left_to_merge(e, agents, e.graph.get_task(TaskId("mid"))):   # …the person's own moves, in their tree
        _git(base, "merge", "-q", "--no-edit", re.search(r"`git merge (\w+)`", why).group(1))
    _by_hand(e, base, "mid", "kirill", {"mid.c": "MID\n"})
    _drive(e, d, lambda: e.next_steps()["complete"] is True)
    assert e.next_steps()["complete"] is True, {t.id: t.state.name for t in e.all_tasks()}
    assert _git(base, "ls-tree", "--name-only", "gfso/p/accepted").split() == [
        "README", "a.c", "b.c", "c.c", "mid.c", "root.c"]
    assert _git(base, "log", "-1", "--format=%s") == "mid by hand", "the system wrote the user's branch"
    e.stop()


@pytest.fixture
def door(tmp_path, monkeypatch):
    """The door a chat delivers through (`tools_llm.signal`) reads the process's roster: the test's own."""
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))


def _by_hand(e, repo: Path, tid, who, files: dict, apart: bool = False) -> str:
    """A person performs `tid` in their own repository and delivers its committed HEAD, naming that tree, through the
    door that records it (`tools_llm.signal`) — `apart`: on a branch of theirs, their checked-out one restored."""
    was = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if apart:
        _git(repo, "switch", "-q", "-c", f"{who}-{tid}")
    for name, text in files.items():
        (repo / name).write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"{tid} by hand")
    sha = _git(repo, "rev-parse", "HEAD")
    out = TL.TOOLS["signal"](e, tid, "DELIVER", who, result="done", place=str(repo))
    assert out["accepted"] and "not_recorded" not in out, out
    if apart:
        _git(repo, "switch", "-q", was)
    e.wait_idle()
    return sha


def _passed(e, *tids, by="kirill"):
    for t in tids:
        if e.graph.get_state(TaskId(t)) == State.VALIDATING:
            instrument_passes(e, t, "validator")
            T.signal(e, t, "PASS", by)
    e.wait_idle()


def test_a_root_the_person_holds_on_this_host_lands_as_its_accepted_branch(tmp_path, door):
    """The container path names a chat root's recorded delivery `gfso/<project>/accepted`; on this host the same root
    got no branch at all, though every user is promised it (ORCHESTRATOR "Where it runs", critic)."""
    e, agents, base = _plan(tmp_path)
    T.signal(e, "par", "ACCEPT", "kirill")
    d = _run(e, agents, {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"})}, _in(e, "a", "b"))
    _passed(e, "a", "b")
    _until(lambda: not e.joins.joining_nodes() and len(left_to_merge(e, agents, e.graph.get_task(TaskId("par")))) == 2)
    for _, why in left_to_merge(e, agents, e.graph.get_task(TaskId("par"))):
        _git(base, "merge", "-q", "--no-edit", re.search(r"`git merge (\w+)`", why).group(1))
    sha = _by_hand(e, base, "par", "kirill", {"par.c": "the whole\n"})
    _passed(e, "par")
    _drive(e, d, lambda: subprocess.run(["git", "rev-parse", "-q", "--verify", "gfso/p/accepted"], cwd=base,
                                        capture_output=True).returncode == 0)
    assert _git(base, "rev-parse", "gfso/p/accepted") == sha == _git(base, "rev-parse", "HEAD")
    assert json.loads(e.graph.setting("landed"))["branch"] == "gfso/p/accepted"
    e.stop()


def _by_hand_alone(tmp_path, judge: Path, project="p"):
    """A root the person performs by hand, its judge standing in `judge` — registered under `project`."""
    e = make_engine(llm=StubLLM(), validate_signals=True)
    e.start()
    e.project_name = "p"
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    agents.register("val-1", "llm-validator", workdir=str(judge), project=project)
    T.create_task(e, "par", {"description": "the whole", "criteria": [criterion("g", "G holds")],
                             "accepted_risks": _RISK}, assignee="kirill")
    T.signal(e, "par", "ACCEPT", "kirill")
    return e, agents


@pytest.mark.parametrize("shape", ["an unscoped judge", "its judge moved after DELIVER"])
def test_a_roots_delivery_lands_in_the_repository_its_deliver_recorded_it_in(tmp_path, door, shape):
    """Where a chat's delivery was recorded is a fact of its DELIVER, kept in the log: read back from the project's
    roles it was missed under a judge the roster falls back to (`validator_for`) and under one registered elsewhere
    since, and the root landed nowhere, nothing said (critic)."""
    base = _repo(tmp_path / "ws")
    e, agents = _by_hand_alone(tmp_path, base, project=None if shape == "an unscoped judge" else "p")
    sha = _by_hand(e, base, "par", "kirill", {"par.c": "the whole\n"})
    if shape == "its judge moved after DELIVER":
        agents.register("val-1", "llm-validator", workdir=str(_repo(tmp_path / "elsewhere")), project="p")
    _passed(e, "par")
    assert land_accepted(e, agents, e.graph.get_task(TaskId("par"))) is None
    assert _git(base, "rev-parse", "gfso/p/accepted") == sha
    e.stop()


def test_a_roots_commit_recorded_with_no_repository_is_said_never_landed_unsaid(tmp_path):
    """A delivery the log kept no repository for — recorded before it did — is a reason the Dispatcher says, not a
    None it reads as landed."""
    base = _repo(tmp_path / "ws")
    e, agents = _by_hand_alone(tmp_path, base)
    tree, sha, _ = W.read_head(base)
    assert T.signal(e, "par", "DELIVER", "kirill", result="done", _recorded=(tree, sha, None))["accepted"]
    _passed(e, "par")
    said = land_accepted(e, agents, e.graph.get_task(TaskId("par"))) or ""
    assert sha[:12] in said, "landed unsaid"
    assert NOT_ON_ITS_BRANCH in said, "…and the frontier says to deliver it again, never to merge a branch none names"
    assert W.git(base, "rev-parse", "-q", "--verify", "refs/heads/gfso/p/accepted").returncode, "nothing named"
    e.stop()


def _all_by_hand(tmp_path, judge=None, b="anna"):
    """A whole the person holds over two parts another person performs by hand: no place of the system's anywhere —
    `b` a registered executor on the base instead."""
    base = _repo(tmp_path / "ws")
    e = make_engine(llm=StubLLM(), validate_signals=True)
    e.start()
    e.project_name = "p"
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    agents.register("val-1", "llm-validator", workdir=str(judge or base), project="p")
    agents.register("exec-2", "llm-executor", workdir=str(base), project="p")
    T.create_task(e, "par", {"description": "the whole", "criteria": [criterion("g", "G holds")]}, assignee="kirill")
    T.decompose(e, "par", [{"task_id": t, "spec": {"description": f"part {t}", "criteria": [criterion(f"{t}_ok")]},
                            "assignee": who, "covers": ["g"]} for t, who in (("a", "anna"), ("b", b))], accepted_risks=_RISK)
    T.signal(e, "par", "ACCEPT", "kirill")
    T.signal(e, "a", "ACCEPT", "anna")
    if b == "anna":
        T.signal(e, "b", "ACCEPT", "anna")
    return e, agents, base


def test_a_whole_whose_parts_another_person_performed_by_hand_is_named_each(tmp_path, door):
    """Every part is placeless, recorded under `refs/gfso/<p>/delivered/<part>` where its judge stands: the whole was told
    only "integrate them", its parts' commits read nowhere (critic)."""
    e, agents, base = _all_by_hand(tmp_path)
    shas = {t: _by_hand(e, base, t, "anna", {f"{t}.c": f"{t}\n"}, apart=True) for t in ("a", "b")}
    _passed(e, "a", "b")
    Dispatcher(e, agents, runner=lambda *a: None)
    step = e.next_step(TaskId("par"))["directive"]
    assert all(f"`git merge {shas[t]}`" in step for t in ("a", "b")), step
    e.stop()


def test_a_part_performed_by_hand_in_another_repository_is_named_there_with_no_tree_guessed(tmp_path, door):
    """A whole with no place has no tree the system can read: each part is named in the repository its DELIVER was
    recorded in, never told to be fetched into another part's repository taken for the whole's (critic)."""
    other = _repo(tmp_path / "other")
    e, agents, base = _all_by_hand(tmp_path, judge=other, b="exec-2")
    sha = _by_hand(e, other, "a", "anna", {"a.c": "a\n"}, apart=True)
    _passed(e, "a")
    named = dict(left_to_merge(e, agents, e.graph.get_task(TaskId("par"))))
    assert set(named) == {"a"} and str(other) in named["a"], named
    assert f"`git merge {sha}`" in named["a"] and "git fetch" not in named["a"], named
    e.stop()


def test_a_whole_the_person_holds_under_a_declared_execution_is_named_its_parts_done_by_hand(tmp_path, door, monkeypatch):
    """What a chat delivered is recorded in the user's repository on this host under either execution: a project whose
    roles declare one named none of them to the whole its holder integrates (critic)."""
    e, agents, base = _all_by_hand(tmp_path)
    shas = {t: _by_hand(e, base, t, "anna", {f"{t}.c": f"{t}\n"}, apart=True) for t in ("a", "b")}
    _passed(e, "a", "b")
    monkeypatch.setenv("GFSO_EXECUTIONS_PATH", str(declared := tmp_path / "executions.json"))
    declared.write_text(json.dumps({"docker": {"image": "gfso-agent:x"}}))
    agents.register("exec-2", "llm-executor", workdir=str(base), project="p", execution="docker")
    named = dict(left_to_merge(e, agents, e.graph.get_task(TaskId("par"))))
    assert set(named) == {"a", "b"} and all(f"`git merge {shas[t]}`" in named[t] for t in named), named
    e.stop()


def test_a_part_whose_work_is_in_another_repository_never_holds_its_whole_back(tmp_path):
    """A system's part placed over another repository than its whole's is named to it (`left_to_merge`), not listed as a
    join its session must lift: listed so, the whole could never DELIVER, and lifting it grafted one repository's
    history into another (critic: on main DONE in one session, so 2 sessions and 150 rounds EXECUTING)."""
    e, agents, base = _plan(tmp_path, whole="exec-1")
    other = _repo(tmp_path / "other")
    agents.register("exec-2", "llm-executor", workdir=str(other), project="p")
    sessions = {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"}), "par": _Executor("par", {})}
    _run(e, agents, sessions, _in(e, "par", states=(State.DONE,)))
    e.stop()


def test_a_passed_part_joins_its_wholes_place_not_the_users_base(tmp_path):
    """Until a seam passes the whole, the base holds none of its parts: a part that passes before the whole's session
    began makes the whole's place and joins there (critic r5, 2026-10-04: the parts landed in the base, and a whole
    that then failed left work no root verdict covered in the scored tree)."""
    e, agents, base = _plan(tmp_path, whole="exec-1")
    sessions = {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"}),
                "par": _Executor("par", {"par.c": "the whole\n"})}
    seen = []
    _run(e, agents, sessions, lambda: (seen.append((e.graph.get_state(TaskId("par")), (base / "a.c").exists(),
                                                    (base / "b.c").exists())),
                                       e.graph.get_state(TaskId("par")) == State.DONE)[1])
    _until(lambda: e.next_steps()["complete"] is True)
    early = [s for s in seen if s[0] != State.DONE]
    assert early and not any(a or b for _, a, b in early), f"a part reached the base before the whole: {early}"
    assert not any((base / f).exists() for f in ("a.c", "b.c", "par.c")), "the user's tree was written"
    assert _git(base, "ls-tree", "--name-only", "gfso/p/accepted").split() == ["README", "a.c", "b.c", "par.c"]
    e.stop()


def test_a_place_is_cut_from_where_its_whole_works_made_first_up_the_tree(tmp_path):
    """Two levels down, a part's place is cut from its whole's place, that one made first from ITS whole's — so what
    already joined above (a producer the part's criterion reads) is in the part's tree (critic r6, 2026-10-04: cut from
    the base while the whole had no place yet, the part started without it)."""
    base = _repo(tmp_path / "ws")
    e = make_engine(llm=StubLLM())
    e.start()
    e.project_name = "p"
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    for aid in ("exec-1", "exec-2", "exec-3"):
        agents.register(aid, "llm-executor", workdir=str(base), project="p")
    T.create_task(e, "r", {"description": "top", "criteria": [criterion("t")]}, assignee="exec-1")
    for whole, part, crit, holder, mine in (("r", "g", "t", "exec-2", "m"), ("g", "c", "m", "exec-3", "l")):
        T.decompose(e, whole, [{"task_id": part, "spec": {"description": part, "criteria": [criterion(mine)]},
                                "assignee": holder, "covers": [crit]}], accepted_risks=_RISK)
    e.wait_idle()
    rw = _workspace(e, agents, e.graph.get_task(TaskId("r")))
    _ensure_place(e, agents, e.graph.get_task(TaskId("r")), rw)
    (Path(rw[1]) / "h.py").write_text("H = 1\n")                     # a producer that joined the top's place
    _git(rw[1], "add", "-A")
    _git(rw[1], "commit", "-q", "-m", "h joins r")
    cw = _workspace(e, agents, e.graph.get_task(TaskId("c")))
    _ensure_place(e, agents, e.graph.get_task(TaskId("c")), cw)
    assert (Path(cw[1]) / "h.py").exists(), "the part's tree misses what joined above it"
    assert Path(_workspace(e, agents, e.graph.get_task(TaskId("g")))[1]).is_dir(), "its whole's place was made first"
    assert not (base / "h.py").exists()
    e.stop()


def test_a_parents_consent_is_asked_in_its_own_place_not_the_base(tmp_path):
    """A parent's consent asked before its executor made its place worked in the base, sharing the base's model-client
    state with the root's executor — whose conversations its readers then read (measured, a stand-in model driving the
    real CLI 2.1.310). Asked in its own place, made now as its first session would make it, it holds a state of its own."""
    base = _repo(tmp_path / "ws")
    e = make_engine(llm=StubLLM())
    e.start()
    e.project_name = "p"
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    for aid in ("exec-1", "exec-2", "exec-3"):
        agents.register(aid, "llm-executor", workdir=str(base), project="p")
    T.create_task(e, "r", {"description": "top", "criteria": [criterion("t")]}, assignee="exec-1")
    for whole, part, crit, holder, mine in (("r", "g", "t", "exec-2", "m"), ("g", "c", "m", "exec-3", "l")):
        T.decompose(e, whole, [{"task_id": part, "spec": {"description": part, "criteria": [criterion(mine)]},
                                "assignee": holder, "covers": [crit]}], accepted_risks=_RISK)
    e.wait_idle()
    assert node_workspace(e, agents, "g") is None, "no session of g has made its place yet"
    asked = []

    class _Consent:
        calls = []

        def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
            asked.append(cwd)
            self.calls.append({"duration_ms": 1, "output_tokens": 1})
            return _fenced({"decision": "accept", "reason": "ok"})

        def tag_last(self, stage):
            pass

    run_consent(e, TaskId("g"), "exec-2", agents, _llm=_Consent())
    assert asked and asked[0] == node_workspace(e, agents, "g") and Path(asked[0]) != base, asked
    e.stop()


@pytest.mark.real_consent
def test_a_consent_that_meets_its_place_down_waits_and_is_not_parked(tmp_path, monkeypatch):
    """Its place made first now, a consent meets a place that is down before any model call: the stop a booked call
    makes, waited out, never "signalled nothing twice — PARKED" (critic over the consent's own place)."""
    base = _repo(tmp_path / "ws")
    e = make_engine(llm=StubLLM())
    e.start()
    e.project_name = "p"
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    for aid in ("exec-1", "exec-2"):
        agents.register(aid, "llm-executor", workdir=str(base), project="p")
    T.create_task(e, "r", {"description": "top", "criteria": [criterion("t")]}, assignee="exec-1")
    T.decompose(e, "r", [{"task_id": "g", "spec": {"description": "g", "criteria": [criterion("m")]},
                          "assignee": "exec-2", "covers": ["t"]}], accepted_risks=REGISTER)
    e.wait_idle()

    def down(*a, **k):
        raise PlaceUnavailable("box", "docker daemon is not running")
    monkeypatch.setattr(W, "ensure", down)
    d = Dispatcher(e, agents)
    for _ in range(2):
        d._consent_guarded(TaskId("r"), "exec-1")
    assert e.paused(), "the place down is its project's stop"
    e.stop()
