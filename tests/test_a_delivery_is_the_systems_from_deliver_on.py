"""A delivery is the system's from DELIVER on: its commit kept by id in the
project's own store, whatever becomes of the place it was made in; nothing written by a DELIVER refused; tree or no
tree the project's record; a chat registered nowhere delivers a commit of the project's repository from the
work tree it names, never one inferred.
"""
from __future__ import annotations

import inspect
import json
import os
import shutil
import threading
import time

import pytest

import gfso.past as PA
import gfso.store as ST
import gfso.tools as T
import gfso.tools_llm as TL
import gfso.workspaces as WS
from gfso.core.types import AgentId, Mode, TaskId
from tests.support import REGISTER, criterion, make_engine, reviewer_passes
from tests.test_a_chat_delivery_is_the_tree_it_handed_in import _commit, _git, _in_chat, _repo, _take


@pytest.fixture(autouse=True)
def _a_roster_of_its_own(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))


def _kept():
    """Every keep started, ended: the keep is the system's act after DELIVER, in the background."""
    for t in [t for t in threading.enumerate() if t.name.startswith(ST.KEEPING)]:
        t.join(120)
        # …a keep still running reads as no keep at all: the validator's runs read {} with nothing on the feed
        assert not t.is_alive(), f"{t.name} still running after 120 s: the keep was slow, not refused"


def _gone(place) -> None:
    """`place` removed as the person removes it — once no process stands in it any more."""
    for _ in range(100):
        try:
            return shutil.rmtree(place, onerror=lambda f, p, _: (os.chmod(p, 0o700), f(p)))
        except PermissionError:
            time.sleep(0.2)
    shutil.rmtree(place)


def _store(e) -> str:
    return ST._where(e, None)[0]


def _keeps(e) -> dict:
    out = _git(_store(e), "for-each-ref", "--format=%(refname) %(objectname)", ST.KEEP)
    return dict(ln.split() for ln in out.splitlines())


def _why(e) -> list:
    """What the keep said on the feed where it failed — a red seen only in another's run names its cause."""
    return [r["message"] for r in e.pipeline_log() if r.get("source") == "delivery"]


def _deliver(e, repo, text: str, **kw) -> tuple[str, dict]:
    (repo / "f.txt").write_text(text)
    head = _commit(repo, "f.txt")
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="f.txt written", self_validation="PASS", **kw)
    _kept()
    return head, out


def test_a_host_delivery_is_kept_in_the_systems_store_and_outlives_its_place(tmp_path):
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    _take(e, repo)
    head, out = _deliver(e, repo, "v1\n")
    assert out["accepted"], out
    assert _keeps(e) == {f"{ST.KEEP}{head}": head}, ("the delivery is not kept by its id in the project's store", _why(e))
    assert json.loads(e.graph.setting(ST.KEPT + head))["place"] == str(repo)
    e.stop()                                                  # …its observer's run ends first: Windows holds a cwd open
    _gone(repo)
    (fresh := tmp_path / "fresh").mkdir()
    _git(fresh, "init", "-q")
    ST.lay(e, None, head, fresh, "refs/heads/got")
    assert _git(fresh, "show", "got:f.txt") == "v1", "the delivery is not read back by its id once its place is gone"


def test_a_second_delivery_does_not_overwrite_the_first(tmp_path):
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    _take(e, repo)
    first, _ = _deliver(e, repo, "v1\n")
    was = e.graph.setting(ST.KEPT + first)
    assert TL.TOOLS["signal"](e, "root", "FAIL", "user", failed_criteria=["f"], reason="v2 wanted",
                              user_said="нет, нужна v2")["accepted"]
    second, out = _deliver(e, repo, "v2\n")
    assert out["accepted"], out
    assert _keeps(e) == {f"{ST.KEEP}{first}": first, f"{ST.KEEP}{second}": second}
    ST.keep(e, None, first, None, tmp_path).join(120)   # …kept again from elsewhere: the first record stands
    assert e.graph.setting(ST.KEPT + first) == was and _keeps(e)[f"{ST.KEEP}{first}"] == first


def test_a_refused_delivery_writes_nothing(tmp_path):
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    _take(e, repo)
    (inner := repo / "vendor" / "lib").mkdir(parents=True)
    _git(inner, "init", "-q")
    (inner / "x").write_text("x\n")
    _commit(inner, "x")
    nested = _commit(repo, "vendor/lib")
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="done", self_validation="PASS")
    _kept()
    assert not out["accepted"] and "vendor/lib" in out["error"], out
    assert not _git(repo, "for-each-ref", "refs/gfso/"), "a refused DELIVER wrote a ref into the person's repository"
    assert not _keeps(e) and e.graph.setting(ST.KEPT + nested) is None, "a refused DELIVER was kept"


def test_a_linked_worktree_named_delivers_its_commit(tmp_path):
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    _git(repo, "worktree", "add", "-q", "-b", "side", str(wt := tmp_path / "wt"))
    head, out = _deliver(e, wt, "v1\n", place=str(wt))
    assert out["accepted"] and e.delivered(TaskId("root"))[1] == head, out
    assert _keeps(e) == {f"{ST.KEEP}{head}": head}


def _unregistered(tmp_path, repo):
    """A solo chat in a project that recorded its repository, with no role registered anywhere."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.graph.store_setting(WS.REPOSITORY, str(repo))
    e.set_mode(Mode.SOLO, None, AgentId("user"), hands=None)
    T.create_task(e, "root", {"description": "write f", "accepted_risks": REGISTER,
                              "criteria": [criterion("f", "f.txt says v1")]})
    e.wait_idle()
    return e


def test_an_unregistered_chat_names_the_work_tree_it_committed_in(tmp_path):
    """Only the sender knows where its work is: a chat with no registered place delivers a commit of the project's
    repository from the work tree it names, refused before any write where it names none."""
    repo = _repo(tmp_path)
    e = _unregistered(tmp_path, repo)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    head, out = _deliver(e, repo, "v1\n")
    assert not out["accepted"] and out.get("refused") and _NAME in out["error"], out
    assert ST._where(e, None, make=False)[0] is None, "a refused DELIVER made the project's store"
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="f.txt written", self_validation="PASS",
                             place=str(repo))
    _kept()
    assert out["accepted"] and e.delivered(TaskId("root"))[1] == head, out
    assert _keeps(e) == {f"{ST.KEEP}{head}": head}, _why(e)
    e.stop()


#: the lift every refusal of a chat's DELIVER that names nothing past the start names
_NAME = "name the work tree you committed in: place=<its path>"

#: a chat with its judge registered at the person's main tree — every real project with a mode has one, so the judge's
#: directory always answers — and one registered nowhere: neither has its delivery inferred from a HEAD
CHATS = pytest.mark.parametrize("chat", [_in_chat, _unregistered], ids=["judge at the main tree", "registered nowhere"])


def _work_in_a_linked_worktree(tmp_path, chat=_unregistered, branch="side"):
    repo = _repo(tmp_path)
    e = chat(tmp_path, repo)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    _git(repo, "worktree", "add", "-q", "-b", branch, str(wt := tmp_path / "wt"))
    (wt / "f.txt").write_text("v1\n")
    _commit(wt, "f.txt")
    return repo, e, wt


def _refused(e, **kw) -> str:
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="f.txt", self_validation="PASS", **kw)
    assert not out["accepted"] and out.get("refused") and _NAME in out["error"], out
    assert e.delivered(TaskId("root")) is None and ST._where(e, None, make=False)[0] is None
    return out["error"]


@CHATS
@pytest.mark.parametrize("main", ["untracked", "clean"])
def test_a_chats_work_in_a_linked_worktree_is_never_its_start_said_done(tmp_path, chat, main):
    """The work committed in an unregistered linked worktree, the main tree with a file of the person's untracked or
    clean: refused without naming the worktree, then `nothing_to_commit` delivered the START, its judge FAILing true
    work (critics over ac9dcaa, f96cb2b, p2 and p3). Refused, the worktree named; no word hands the start in."""
    repo, e, wt = _work_in_a_linked_worktree(tmp_path, chat)
    if main == "untracked":
        (repo / "notes.txt").write_text("the person's\n")
    assert f"place={wt}" in _refused(e)
    assert "nothing_to_commit" not in inspect.signature(TL.signal).parameters, "a word that hands in the start"
    e.stop()


@CHATS
def test_the_persons_commit_on_main_is_never_a_chats_delivery(tmp_path, chat):
    """The work in a linked worktree, the person committing on main meanwhile: main's HEAD was delivered as the
    agent's work (critics over ac9dcaa, f96cb2b p1). Refused, nothing inferred from the main tree."""
    repo, e, wt = _work_in_a_linked_worktree(tmp_path, chat)
    (repo / "his.txt").write_text("his\n")
    _commit(repo, "his.txt")
    assert f"place={wt}" in _refused(e)
    e.stop()


@CHATS
def test_the_refusal_names_no_tree_nor_branch_of_the_persons(tmp_path, chat):
    """The refusal listed the main tree at the person's commit as where the work may be (critic over f96cb2b, p9): it
    names the linked worktree and a branch past the start nobody has checked out — never the main tree nor his
    branch."""
    repo, e, wt = _work_in_a_linked_worktree(tmp_path, chat)
    (repo / "README").write_text("his\n")
    his = _commit(repo, "README")
    _git(wt, "branch", "loose", _git(wt, "rev-parse", "HEAD"))
    no = _refused(e)
    assert f"place={wt}" in no and "branch `loose`" in no, no
    assert f"`place={repo}`" not in no and his[:12] not in no, no
    e.stop()


def test_a_solo_chat_committing_on_the_work_branch_delivers_it_with_no_place(tmp_path):
    """The honest chat: its tree switched to the work's branch as its ACCEPT's answer tells it, the work committed there
    — delivered with nothing named."""
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    _take(e, repo)
    head, out = _deliver(e, repo, "v1\n")
    assert out["accepted"] and e.delivered(TaskId("root"))[1] == head, out
    e.stop()


def test_the_work_branch_in_a_linked_worktree_is_delivered_while_the_person_commits_on_main(tmp_path):
    """The work's branch is the system's: its tip past the start is the work, wherever it is checked out — the
    person's commit on main beside it never."""
    repo, e, wt = _work_in_a_linked_worktree(tmp_path, _in_chat, branch="gfso/p/work")
    work = _git(wt, "rev-parse", "HEAD")
    (repo / "his.txt").write_text("his\n")
    _commit(repo, "his.txt")
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="f.txt", self_validation="PASS")
    assert out["accepted"] and e.delivered(TaskId("root"))[1] == work, out
    e.stop()


@pytest.mark.parametrize("by", ["path", "commit"])
def test_a_named_place_or_commit_delivers_its_commit(tmp_path, by):
    repo, e, wt = _work_in_a_linked_worktree(tmp_path, _in_chat)
    work = _git(wt, "rev-parse", "HEAD")
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="f.txt", self_validation="PASS",
                             place=str(wt) if by == "path" else work)
    assert out["accepted"] and e.delivered(TaskId("root"))[1] == work, out
    assert by == "path" or ("named by its id" in out["notice"] and "stands on" not in out["notice"]), out
    e.stop()


def _two_parts(tmp_path):
    """The root split into parts a and b, a delivered on the work's branch in the person's tree, the tree switched back
    to his branch and his own commit made there."""
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    T.decompose(e, "root", [{"task_id": n, "assignee": "user", "covers": ["f"],
                             "spec": {"description": f"part {n}", "criteria": [criterion(n, f"{n}.txt")]}}
                            for n in ("a", "b")], accepted_risks=REGISTER)
    e.wait_idle()
    main = _git(repo, "symbolic-ref", "--short", "HEAD")
    assert TL.TOOLS["signal"](e, "a", "ACCEPT", "user")["accepted"]
    _git(repo, "switch", "-q", "-c", "gfso/p/work")
    (repo / "a.txt").write_text("a\n")
    _commit(repo, "a.txt")
    assert TL.TOOLS["signal"](e, "a", "DELIVER", "user", result="a.txt", self_validation="PASS")["accepted"]
    e.wait_idle()
    return repo, e, main


def _his_commit(repo, main) -> None:
    _git(repo, "switch", "-q", main)
    (repo / "his.txt").write_text("his\n")
    _commit(repo, "his.txt")


@pytest.mark.parametrize("by", ["nothing", "path", "commit"])
def test_a_part_taken_after_the_persons_commit_starts_from_the_work_branch(tmp_path, by):
    """Part a delivered, the person committing on main, part b taken: its ACCEPT recorded his commit as the start, and b
    committed on the work's branch in a linked worktree was refused named or not (critic over 1d84a75). Delivered."""
    repo, e, main = _two_parts(tmp_path)
    _his_commit(repo, main)
    assert TL.TOOLS["signal"](e, "b", "ACCEPT", "user")["accepted"]
    _git(repo, "worktree", "add", "-q", str(wt := tmp_path / "wt"), "gfso/p/work")
    (wt / "b.txt").write_text("b\n")
    b1 = _commit(wt, "b.txt")
    out = TL.TOOLS["signal"](e, "b", "DELIVER", "user", result="b.txt", self_validation="PASS",
                             **{"nothing": {}, "path": {"place": str(wt)}, "commit": {"place": b1}}[by])
    assert out["accepted"] and e.delivered(TaskId("b"))[1] == b1, out
    e.stop()


def test_a_reopened_part_after_the_persons_commit_starts_from_the_work_branch(tmp_path):
    """Part a PASSed, the tree switched back to main and the person committing there, a REOPENed: its ACCEPT recorded his
    commit as the start, and a2 committed on the work's branch descends from it no way (critic over 1d84a75). Delivered."""
    repo, e, main = _two_parts(tmp_path)
    reviewer_passes(e, "a", "val-1")
    assert TL.TOOLS["signal"](e, "a", "PASS", "user")["accepted"]
    e.wait_idle()
    _his_commit(repo, main)
    assert not T.reopen(e, "a", "user").get("error")
    e.wait_idle()
    assert TL.TOOLS["signal"](e, "a", "ACCEPT", "user")["accepted"]
    _git(repo, "switch", "-q", "gfso/p/work")
    (repo / "a.txt").write_text("a2\n")
    a2 = _commit(repo, "a.txt")
    out = TL.TOOLS["signal"](e, "a", "DELIVER", "user", result="a.txt", self_validation="PASS")
    assert out["accepted"] and e.delivered(TaskId("a"))[1] == a2, out
    e.stop()


def test_a_named_place_at_the_start_is_refused(tmp_path):
    """Named or not, the commit the work started from is never its delivery: its judge FAILs true work (s21)."""
    repo, e, wt = _work_in_a_linked_worktree(tmp_path, _in_chat)
    no = _refused(e, place=str(repo))
    assert "the commit the work started from" in no and f"place={wt}" in no, no
    e.stop()


@pytest.mark.parametrize("by", ["nothing", "path"])
def test_a_revised_node_re_delivers_its_committed_work_after_its_re_consent(tmp_path, by):
    """The work committed, the node revised (§12.10) and re-ACCEPTed — that ACCEPT recording the work as its HEAD —:
    its DELIVER of the identical artifact was refused as the start, its lift an empty commit, a false report. The start
    is the first ACCEPT's: delivered, its range in the record of work past the system its commits (it was empty); the
    start itself still refused."""
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    _take(e, repo)
    (repo / "f.txt").write_text("v1\n")
    work = _commit(repo, "f.txt")
    T.revise(e, "root", max_iterations=9, agent="user")      # …a re-ASSIGN: the executor's re-consent is asked
    e.wait_idle()
    assert TL.TOOLS["signal"](e, "root", "ACCEPT", "user")["accepted"]
    assert e.audit_log(TaskId("root"))[-1].commit == work, "the re-ACCEPT did not record the committed work"
    assert "the commit the work started from" in _refused(e, place=PA.start_of(e, "root"))
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="f.txt", self_validation="PASS",
                             **({"place": str(repo)} if by == "path" else {}))
    assert out["accepted"] and e.delivered(TaskId("root"))[1] == work, out
    assert work in json.loads(e.graph.setting(PA.DELIVERED))[work]["changes"], "the delivery's range lists none of its commits"
    e.stop()


def test_a_delivery_before_its_record_is_read_from_its_nodes_first_accept():
    """A DELIVER whose range no record keeps is read from where its node's work started: a re-ACCEPT's HEAD, the work
    itself, left it empty."""
    log = [("n", s, None, None, c, "r", "user", 0) for s, c in (("ACCEPT", "s0"), ("ACCEPT", "w"), ("DELIVER", "w"))]
    assert PA._deliveries([{"landed": None, "delivered": {}, "log": log}], "k", {"r": "k"})[2] == [("w", "s0")]


def test_a_root_taken_at_the_go_re_delivers_its_work_after_its_first_accept(tmp_path):
    """A root taken at the go holds no ACCEPT: the one its revision asks records the work committed since — the go's
    record is the start, and the work is delivered."""
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    e.graph.store_setting(f"{PA.CHAT_START}root", json.dumps({"branch": "master", "head": _git(repo, "rev-parse", "HEAD")}))
    _git(repo, "switch", "-q", "-c", "gfso/p/work")
    (repo / "f.txt").write_text("v1\n")
    work = _commit(repo, "f.txt")
    assert TL.TOOLS["signal"](e, "root", "ACCEPT", "user")["accepted"]
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="f.txt", self_validation="PASS")
    assert out["accepted"] and e.delivered(TaskId("root"))[1] == work, out
    e.stop()


def test_an_unrelated_repository_is_refused_in_a_project_made_before_its_repository_was_recorded(tmp_path):
    """The refusal read the recorded repository alone — none for every project made before the record —, so an
    unrelated repository named by `place=` was admitted and its roots entered the store (critic over ac9dcaa)."""
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    e.graph.store_setting(WS.REPOSITORY, "")                  # …a project made before the record
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    (other := tmp_path / "elsewhere").mkdir()
    _git(other, "init", "-q")
    (other / "README").write_text("another project\n")
    _commit(other, "README")
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="done", self_validation="PASS", place=str(other))
    assert not out["accepted"] and "shares no history" in out["error"], out
    assert ST._where(e, None, make=False)[0] is None
    e.stop()


def test_a_shallow_clone_is_refused_with_the_lift_that_unshallows_it(tmp_path):
    """Its boundary failed the admission's `index-pack --strict`, and the sender was told to repair a repository that
    is whole (critic over ac9dcaa): the store keeps a delivery with its history, which joins and landing read."""
    repo = _repo(tmp_path)
    (repo / "g.txt").write_text("g\n")
    _commit(repo, "g.txt")
    e = _in_chat(tmp_path, repo)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    _git(tmp_path, "clone", "-q", "--depth", "1", (repo / ".git").as_uri(), str(clone := tmp_path / "clone"))
    _, out = _deliver(e, clone, "v1\n", place=str(clone))
    assert not out["accepted"] and "git fetch --unshallow" in out["error"] and "fsck" not in out["error"], out
    assert ST._where(e, None, make=False)[0] is None
    e.stop()


def test_the_projects_repository_is_recorded_at_its_first_role_and_derived_for_an_older_one(tmp_path):
    repo = _repo(tmp_path)
    _git(repo, "worktree", "add", "-q", "-b", "side", str(wt := tmp_path / "wt"))
    e = _in_chat(tmp_path, wt)                                # …its first role, registered in a linked worktree
    assert WS.repository(e, TL._delegation().default_agents()) == str(repo), "recorded by its main worktree"
    e.graph.store_setting(WS.REPOSITORY, "")                  # …a project made before the record
    assert WS.repository(e, TL._delegation().default_agents()) == str(repo), "not derived from its role's workdir"
    bare = make_engine(validate_signals=True, state_timeout=0)
    bare.project_name = "q"
    assert WS.repository(bare, TL._delegation().default_agents()) is None, "a repository named by nothing"
