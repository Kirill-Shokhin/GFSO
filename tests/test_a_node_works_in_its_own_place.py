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
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

from gfso import delegate, tools as T
from gfso.adapters import worktrees as W
from gfso.adapters.llm.stub import StubLLM
from gfso.core.protocol.procedure import probe_id
from gfso.core.types import State, TaskId
from gfso.delegate import Dispatcher, _auto_validate
from gfso.sessions import run_executor
from gfso.workspaces import _ensure_place, _workspace, node_workspace
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


def _run(e, agents, sessions: dict, until, validated: dict | None = None, rounds=300):
    d = Dispatcher(e, agents, poll=30,
                   runner=lambda en, t, ex, ag: run_executor(en, t, ex, ag, _llm=sessions[str(t)]),
                   validator_runner=lambda en, t, ag, **k: _auto_validate(
                       en, t, ag, _llm=_Validator(en, t, validated if validated is not None else {}), **k))
    for _ in range(rounds):
        d.dispatch_once()
        time.sleep(0.05)
        e.wait_idle()
        if until():
            return d
    raise AssertionError(f"not reached: {({t.id: t.state.name for t in e.all_tasks()})}")


def _until(pred, timeout=20.0) -> None:
    end = time.monotonic() + timeout
    while not pred():
        assert time.monotonic() < end, "not reached in time"
        time.sleep(0.05)


def _in(e, *tids, states=(State.VALIDATING, State.DONE)):
    return lambda: all(e.graph.get_state(TaskId(t)) in states for t in tids)


def test_two_parts_run_at_once_each_in_its_own_tree(tmp_path):
    e, agents, base = _plan(tmp_path)
    meet = threading.Barrier(2)
    sessions = {"a": _Executor("a", {"a.c": "A\n"}, meet), "b": _Executor("b", {"b.c": "B\n"}, meet)}
    _run(e, agents, sessions, _in(e, "a", "b"))
    places = tmp_path / ".gfso-nodes-ws" / "p"
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
    assert where == {"a": sessions["a"].cwd, "b": sessions["b"].cwd}
    assert node_workspace(e, agents, "a") == sessions["a"].cwd


def test_a_part_that_passed_joins_where_its_whole_works(tmp_path):
    e, agents, base = _plan(tmp_path, whole="exec-1")
    sessions = {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"}),
                "par": _Executor("par", {"par.c": "the whole\n"})}
    _run(e, agents, sessions, _in(e, "par", states=(State.DONE,)))
    places = tmp_path / ".gfso-nodes-ws" / "p"
    assert sessions["par"].cwd == str(places / "par")
    assert {"a.c", "b.c"} <= sessions["par"].saw, "the whole's session sees its parts, joined"
    # the whole PASSed too, and joined the base, where every part now stands — and the joined places are gone
    _until(lambda: (base / "par.c").exists() and not places.joinpath("par").exists())
    assert all((base / f).exists() for f in ("a.c", "b.c", "par.c"))
    assert {"gfso: a joins par", "gfso: b joins par", "gfso: par joins the base"} <= set(
        _git(base, "log", "--format=%s").splitlines())
    _until(lambda: _git(base, "branch", "--list", "gfso/*") == "")
    assert not any(places.joinpath(t).exists() for t in ("a", "b", "par"))


def test_a_part_that_conflicts_is_left_unjoined_and_named_to_its_whole(tmp_path):
    e, agents, base = _plan(tmp_path, whole="exec-1")
    said: list = []
    e.on_info(lambda src, msg: said.append(msg))
    sessions = {"a": _Executor("a", {"shared.c": "A\n"}), "b": _Executor("b", {"shared.c": "B\n"}),
                "par": _Executor("par", {})}
    _run(e, agents, sessions, _in(e, "par", states=(State.DONE,)))
    _until(lambda: e.joins.joining_nodes() == [])            # the root's own join lands before the base is read
    named = [b for b in ("gfso/p/a", "gfso/p/b") if f"on branch `{b}`" in sessions["par"].packet]
    assert len(named) == 1 and "Parts NOT joined into your workspace" in sessions["par"].packet
    left = named[0].rsplit("/", 1)[1]
    # the merge was aborted where it ran: the base holds the other part, whole and clean, and no conflict markers
    assert (base / "shared.c").read_text() == ("B\n" if left == "a" else "A\n")
    assert _git(base, "status", "--porcelain") == ""
    # the unjoined branch and its tree stay, and are named, at the root's PASS
    _until(lambda: any("not joined into the base are kept" in m for m in said))
    assert (tmp_path / ".gfso-nodes-ws" / "p" / left).is_dir()
    assert _git(base, "branch", "--list", named[0]).strip().endswith(named[0])


def test_a_directory_that_is_not_a_repository_is_shared_as_before(tmp_path):
    e, agents, base = _plan(tmp_path, git=False, whole="exec-1")
    said: list = []
    e.on_info(lambda src, msg: said.append(msg))
    meet = threading.Barrier(2)
    sessions = {"a": _Executor("a", {"a.c": "A\n"}, meet), "b": _Executor("b", {"b.c": "B\n"}, meet),
                "par": _Executor("par", {})}
    where: dict = {}
    _run(e, agents, sessions, _in(e, "a", "b", states=(State.DONE,)), validated=where)
    assert sessions["a"].cwd == sessions["b"].cwd == str(base) == where["a"] == where["b"]
    assert {"a.c", "b.c"} <= sessions["a"].saw
    assert sum("is not the top of a git repository" in m for m in said) == 1
    assert not (tmp_path / ".gfso-nodes-ws").exists()


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
    S._drive(e, S._dispatcher(e, agents, executor, validator, []), lambda: e.graph.get_state(TaskId("root")) == State.DONE)
    place = tmp_path.parent / f".gfso-nodes-{tmp_path.name}" / "p" / "root"
    assert where == {"session": str(place), "validation": str(place)}
    # one tree, a commit per node's delivery in build order; its parts join nothing (their whole works there), and
    # the top, at its PASS, joins the base
    _until(lambda: (tmp_path / "scope.c").exists() and not place.exists() and e.joins.joining_nodes() == [])
    assert _git(tmp_path, "log", "-1", "--format=%s").splitlines() == ["gfso: root joins the base"]
    assert _git(tmp_path, "log", "--format=%s", "-4", "HEAD^2").splitlines() == [
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
    W.commit_all(base, place, "gfso: a delivery", "exec-1")
    assert _git(base, "ls-tree", "-r", "--name-only", "gfso/p/a").splitlines() == ["README", "a.py"]


def test_a_whole_is_not_validated_over_parts_still_joining(tmp_path, monkeypatch):
    """A part's join runs off the signal path; until it lands, its whole is not validated over a place without it, and
    the root's DONE is not `complete` until the base holds the root's result (critic r2, 2026-10-04)."""
    gate, seen = threading.Event(), {}
    real = W.merge

    def held(base, into, branch, message):
        gate.wait(20)
        return real(base, into, branch, message)
    monkeypatch.setattr(W, "merge", held)
    e, agents, base = _plan(tmp_path)                  # the whole is a person's: validated where the parts join
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
    _until(lambda: e.joins.joining_nodes() == [] and (base / "a.c").exists() and (base / "b.c").exists())
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


def test_a_root_whose_result_did_not_land_is_not_complete_until_it_does(tmp_path, monkeypatch):
    """A refused merge is not a landed one: an untracked file in the base that the root's delivery would overwrite
    aborts the join, and `complete` waits — named with the branch that holds the result, stuck, retried — until the
    base takes it (critic r3, 2026-10-04: the refused join read as complete)."""
    monkeypatch.setattr(delegate, "JOIN_RETRY_S", 0)    # the backoff has its own test
    e, agents, base = _plan(tmp_path, whole="exec-1")
    (base / "par.c").write_text("a stray file nobody committed\n")
    sessions = {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"}),
                "par": _Executor("par", {"par.c": "the whole\n"})}
    d = _run(e, agents, sessions, _in(e, "par", states=(State.DONE,)))
    _until(lambda: "par" in e.joins.unjoined_roots())
    out = e.next_steps()
    assert out["complete"] is False and out["stuck"] is True and "did not land" in out["directive"], out
    assert "gfso/p/par" in out["directive"], "the branch that holds the result is named (critic r4)"
    gate, real = threading.Event(), W.merge
    monkeypatch.setattr(W, "merge", lambda *a: (gate.wait(20), real(*a))[1])
    d.dispatch_once()                                   # WHILE a retry runs, the refusal still stands (critic r4)
    _until(lambda: "par" in e.joins.joining_nodes())
    assert e.next_steps()["stuck"] is True, "a retry erased the refusal: the root read 'being joined'"
    gate.set()
    _until(lambda: not e.joins.joining_nodes())
    monkeypatch.setattr(W, "merge", real)
    assert e.next_steps()["stuck"] is True
    (base / "par.c").unlink()                           # the base is cleared, by whoever holds it
    d.dispatch_once()
    _until(lambda: not e.joins.unjoined_roots() and not e.joins.joining_nodes())
    assert (base / "par.c").read_text() == "the whole\n" and e.next_steps()["complete"] is True


def test_a_held_whole_is_not_told_to_aggregate_over_parts_still_joining(tmp_path, monkeypatch):
    """The frontier and the validation door read a whole over its parts only once their results stand where it works
    (critic r3, 2026-10-04: SEMI's AGGREGATE step and `validate_result` read the base ahead of the merges)."""
    gate = threading.Event()
    real = W.merge
    monkeypatch.setattr(W, "merge", lambda *a: (gate.wait(20), real(*a))[1])
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
    """Every try is a merge and an abort on the user's own base, and a refusal waits on a person: the retry backs off
    instead of spinning with the dispatch loop (critic r4, 2026-10-04: about four tries a second)."""
    e, agents, base = _plan(tmp_path, whole="exec-1")
    (base / "par.c").write_text("a stray file nobody committed\n")
    sessions = {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"}),
                "par": _Executor("par", {"par.c": "the whole\n"})}
    d = _run(e, agents, sessions, _in(e, "par", states=(State.DONE,)))
    _until(lambda: "par" in e.joins.unjoined_roots() and not e.joins.joining_nodes())
    tries = []
    real = W.merge
    monkeypatch.setattr(W, "merge", lambda *a: (tries.append(a[2]), real(*a))[1])
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


def test_a_held_whole_is_told_which_parts_did_not_merge_and_on_what_branch(tmp_path):
    """A part whose merge was refused ends its join on its own branch; the whole's AGGREGATE step names it, since
    integrating it is the whole's work (§8.7) — told only "all children passed", a holder aggregates without it
    (critic r4, 2026-10-04)."""
    e, agents, base = _plan(tmp_path)
    (base / "a.c").write_text("a stray file nobody committed\n")
    T.signal(e, "par", "ACCEPT", "kirill")
    _run(e, agents, {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"})}, _in(e, "a", "b"))
    for t in ("a", "b"):
        if e.graph.get_state(TaskId(t)) == State.VALIDATING:
            instrument_passes(e, t, "validator")
            T.signal(e, t, "PASS", "kirill")
    e.wait_idle()
    _until(lambda: not e.joins.joining_nodes() and (base / "b.c").exists())
    step = e.next_step(TaskId("par")).get("directive", "")
    assert "AGGREGATE" in step and "gfso/p/a" in step and "gfso/p/b" not in step, step
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
    assert (base / "a.c").exists() and (base / "b.c").exists() and (base / "par.c").exists()
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
