"""Every reader of a delivery reads it BY ITS ID from the project's store, kept first if absent: the judge, a join, a
landing — whatever became of the place it was made in. Its loss is no verdict, never a FAIL; a base with no git is given
a repository, so no directory is judged as it stands; any git holding the commit delivers it, a plain clone too; the
guards keep their comparators read from the record; and no session in a container holds the store writable.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

import gfso.adapters.execution as E
import gfso.store as ST
import gfso.tools as T
import gfso.tools_llm as TL
import gfso.workspaces as WS
from gfso.adapters import worktrees as W
from gfso.adapters.execution import STORE_DIR, ContainerExecution, LocalExecution, PlaceContainer
from gfso.adapters.snapshots import NotTheDelivery, Uncopied, snapshot
from gfso.core.types import AgentId, Mode, State, TaskId
from gfso.roster import AgentRegistry
from tests.support import REGISTER, criterion, instrument_passes, make_engine
from tests.test_a_chat_delivery_is_the_tree_it_handed_in import _Reads, _commit, _git, _in_chat, _repo, _take
from tests.test_a_delivery_is_the_systems_from_deliver_on import _deliver, _gone, _kept, _keeps, _unregistered


@pytest.fixture(autouse=True)
def _a_roster_of_its_own(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))


def _pruned(repo, wt) -> None:
    """The linked worktree `wt` removed as the person removes it, its branch with it, and git's own gc taking what no
    ref names any more: the commit delivered there is in no git of theirs."""
    _git(repo, "worktree", "remove", "--force", str(wt))
    _git(repo, "branch", "-D", "side")
    _git(repo, "reflog", "expire", "--expire=now", "--all")
    _git(repo, "gc", "-q", "--prune=now")


def _delivered_from_a_worktree(tmp_path):
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    _git(repo, "worktree", "add", "-q", "-b", "side", str(wt := tmp_path / "wt"))
    head, out = _deliver(e, wt, "v1\n", place=str(wt))
    assert out["accepted"], out
    _pruned(repo, wt)
    assert subprocess.run(["git", "-C", str(repo), "cat-file", "-e", head], capture_output=True).returncode, \
        "the delivered commit still stands in the person's repository: nothing is shown"
    return repo, e, head


def test_a_removed_places_delivery_is_judged_and_landed_by_its_id(tmp_path):
    """Read from the place it was made in, a delivery whose place was removed was a missing object — the delivery's FAIL
    (`NotTheDelivery`) — and its landing had nothing to name."""
    repo, e, head = _delivered_from_a_worktree(tmp_path)
    # …the judge's own read (`_validator_texts`, `_observe_pins`): from the directory it stands in, by the id
    with snapshot(TL._read_by_id(e, e.delivered(TaskId("root")), repo, None), tmp_path / "judge",
                  LocalExecution(), delivered=e.delivered(TaskId("root"))) as at:
        assert (Path(at) / "f.txt").read_text().strip() == "v1", "the judge did not read the delivery by its id"
    instrument_passes(e, TaskId("root"), "validator")
    assert T.signal(e, "root", "PASS", "user")["accepted"]
    landed = lambda: subprocess.run(["git", "-C", str(repo), "rev-parse", "-q", "--verify", "gfso/p/accepted"],
                                    capture_output=True, text=True).stdout.strip()
    for _ in range(300):                                    # …the PASS lands it, on the dispatcher's turn
        if landed():
            break
        time.sleep(0.1)
    assert landed() == head, "the accepted result did not land by its id"
    e.stop()


def test_a_part_delivered_from_a_removed_clone_is_joined_by_its_id(tmp_path):
    """A part its holder delivered from a plain clone of the project, the clone then removed: its commit is named for
    its whole to merge and is there to merge, read from the store into the whole's repository."""
    base = _repo(tmp_path)
    e = make_engine(validate_signals=True)
    e.start()
    e.project_name = "p"
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    agents.register("val-1", "llm-validator", workdir=str(base), project="p")
    T.create_task(e, "par", {"description": "the whole", "criteria": [criterion("g", "G holds")]}, assignee="kirill")
    T.decompose(e, "par", [{"task_id": t, "spec": {"description": f"part {t}", "criteria": [criterion(f"{t}_ok")]},
                            "assignee": "kirill", "covers": ["g"]} for t in ("a", "b")], accepted_risks=REGISTER)
    T.signal(e, "par", "ACCEPT", "kirill")
    T.signal(e, "a", "ACCEPT", "kirill")
    _git(tmp_path, "clone", "-q", str(base), str(clone := tmp_path / "clone"))
    (clone / "a.c").write_text("A\n")
    sha = _commit(clone, "a.c")
    out = TL.TOOLS["signal"](e, "a", "DELIVER", "kirill", result="a.c", place=str(clone))
    assert out["accepted"], out
    _kept()
    instrument_passes(e, TaskId("a"), "validator")
    assert T.signal(e, "a", "PASS", "kirill")["accepted"]
    e.wait_idle()
    _gone(clone)
    named = dict(WS.left_to_merge(e, agents, e.graph.get_task(TaskId("par"))))
    assert f"`git merge {sha}`" in named.get("a", ""), named
    _git(base, "merge", "-q", "--no-edit", sha)            # …the holder's own move: the commit is there to merge
    assert (base / "a.c").read_text() == "A\n"
    e.stop()


def test_a_delivery_no_store_holds_is_no_verdict_never_a_fail(tmp_path):
    """Its objects gone from the store and from every place: no copy, so no verdict — ⊥ to the node's bound and its
    issuer — where it was read as the delivery's own FAIL (`NotTheDelivery`)."""
    repo, e, head = _delivered_from_a_worktree(tmp_path)
    _gone(ST._where(e, None)[0])
    with pytest.raises(Uncopied) as got:
        with snapshot(TL._read_by_id(e, e.delivered(TaskId("root")), repo, None), tmp_path / "judge",
                      LocalExecution(), delivered=e.delivered(TaskId("root"))):
            pass
    assert not isinstance(got.value, NotTheDelivery)
    # …and the same object missing where a copy is packed from: no verdict either
    with pytest.raises(Uncopied):
        with snapshot(repo, tmp_path / "judge2", LocalExecution(), delivered=e.delivered(TaskId("root"))):
            pass
    e.stop()


def test_a_judge_registered_below_a_work_trees_top_stands_in_that_directory_of_its_commit(tmp_path):
    """The commit recorded is the whole work tree's, its judge registered in `repo/pkg`: mapped onto the checkout's top,
    it found none of its files and FAILed true work (critic over 4ac5e3a). It stands in `pkg` of the checkout."""
    repo = _repo(tmp_path)
    (pkg := repo / "pkg").mkdir()
    e = _in_chat(tmp_path, pkg)
    _take(e, repo)
    (pkg / "f.txt").write_text("v1\n")
    head = _commit(repo, "pkg/f.txt")
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="pkg/f.txt", self_validation="PASS")
    assert out["accepted"] and e.delivered(TaskId("root"))[1] == head, out
    TL.validate_result(e, "root", _llm=(llm := _Reads()))
    assert llm.read == "v1" and Path(llm.cwd).name == "pkg", (llm.cwd, llm.read)
    e.stop()


def test_a_directory_with_no_git_is_refused_where_it_is_named_and_never_made_a_repository(tmp_path):
    """The system never makes the person's directory a repository nor commits it blindly: refused at registration with
    the lift, and at the go for a role registered before the refusal was — the directory left as it was."""
    (plain := tmp_path / "plain").mkdir()
    (plain / "notes.txt").write_text("the person's\n")
    e = make_engine(validate_signals=True, state_timeout=0)
    e.project_name = "p"
    out = TL.TOOLS["register_agent"](e, "val-1", "llm-validator", workdir=str(plain))
    assert out.get("refused") and "git init" in out["error"], out
    AgentRegistry().register("exec-1", "llm-executor", workdir=str(plain), project="p")   # …from before the refusal
    went = TL.auto_decompose(e, "write f", spec={"name": "f", "root_criteria": [criterion("f", "f holds")]})
    assert went.get("refused") and "git init" in went["error"] and "exec-1" in went["error"], went
    assert not (plain / ".git").exists(), "the system made the person's directory a repository"


def test_a_host_executor_below_a_work_trees_top_is_refused_where_it_is_named_and_at_the_go(tmp_path):
    """No place of its own is cut from a directory below a work tree's top: its sessions shared the live tree, and no
    verdict could come — refused before a session is paid for, the top named."""
    repo = _repo(tmp_path)
    (sub := repo / "sub").mkdir()
    e = make_engine(validate_signals=True, state_timeout=0)
    e.project_name = "p"
    out = TL.TOOLS["register_agent"](e, "exec-1", "llm-executor", workdir=str(sub))
    assert out.get("refused") and f"register it at {repo.as_posix()}" in out["error"].replace("\\", "/"), out
    AgentRegistry().register("exec-1", "llm-executor", workdir=str(sub), project="p")   # …from before the refusal
    went = TL.auto_decompose(e, "write f", spec={"name": "f", "root_criteria": [criterion("f", "f holds")]})
    assert went.get("refused") and "exec-1" in went["error"] and "not its top" in went["error"], went


def test_a_deliver_with_no_commit_where_its_judge_has_a_directory_is_refused_and_writes_nothing(tmp_path):
    """Accepted, no judge could read it and no verdict could ever come: refused before any write, its lift named."""
    (plain := tmp_path / "plain").mkdir()
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    AgentRegistry().register("val-1", "llm-validator", workdir=str(plain), project="p")   # …from before the refusal
    e.set_mode(Mode.SOLO, None, AgentId("user"), hands=None)
    T.create_task(e, "root", {"description": "write f", "accepted_risks": REGISTER,
                              "criteria": [criterion("f", "f.txt says v1")]})
    e.wait_idle()
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="done", self_validation="PASS")
    assert not out["accepted"] and out.get("refused") and "place=" in out["error"], out
    assert e.graph.get_state(TaskId("root")).name == "EXECUTING"
    assert ST._where(e, None, make=False)[0] is None, "a refused DELIVER made the project's store"
    e.stop()


def test_a_chat_in_an_unregistered_linked_worktree_is_told_where_its_work_is_never_judged_on_the_start(tmp_path):
    """The author's own case: a chat committing in a linked worktree nobody registered delivers with no `place`, and
    the project's repository still stands on the start — judged, the start FAILed. Refused, the work tree named."""
    repo = _repo(tmp_path)
    e = _unregistered(tmp_path, repo)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    _git(repo, "worktree", "add", "-q", "-b", "side", str(wt := tmp_path / "wt"))
    (wt / "f.txt").write_text("v1\n")
    _commit(wt, "f.txt")
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="f.txt", self_validation="PASS")
    assert not out["accepted"] and f"place={wt}" in out["error"], out
    assert TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="f.txt", self_validation="PASS",
                              place=str(wt))["accepted"], "delivered from where the work is"
    e.stop()


def test_a_commit_of_an_unrelated_repository_is_refused_and_writes_nothing(tmp_path):
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    (other := tmp_path / "elsewhere").mkdir()
    _git(other, "init", "-q")
    (other / "README").write_text("another project\n")
    _commit(other, "README")
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="done", self_validation="PASS", place=str(other))
    assert not out["accepted"] and "shares no history" in out["error"], out
    assert not _git(other, "for-each-ref", "refs/gfso/") and ST._where(e, None, make=False)[0] is None
    e.stop()


def test_the_keep_imports_the_pack_its_admission_verified_and_leaves_nothing_behind(tmp_path):
    """The admission verifies a pack in the system's temp, the store untouched; the keep takes THAT pack — the sender's
    repository gone by then — and its directory goes with the keep."""
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    (repo / "f.txt").write_text("v1\n")
    head = _commit(repo, "f.txt")
    pack = ST.admit(e, None, head, repo)
    assert pack and Path(pack).is_file() and ST._where(e, None, make=False)[0] is None, pack
    _gone(repo)
    ST.keep(e, None, head, repo, repo, pack=pack).join(120)
    assert _keeps(e).get(f"{ST.KEEP}{head}") == head and not Path(pack).parent.exists()
    e.stop()


def test_a_corrupted_object_in_the_senders_git_is_his_refusal_at_deliver(tmp_path):
    """An object that does not hold what its id names, in the sender's own repository: refused at DELIVER with his
    lift, nothing written — the keep's check came after, and the system then stopped on it, the sender never told."""
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    _take(e, repo)
    (repo / "f.txt").write_text("v1\n")
    (repo / "g.txt").write_text("something else\n")
    _commit(repo, "f.txt", "g.txt")
    good, bad = (repo / ".git" / "objects" / (b := _git(repo, "rev-parse", f"HEAD:{n}"))[:2] / b[2:]
                 for n in ("f.txt", "g.txt"))
    os.chmod(good, 0o644)
    good.write_bytes(bad.read_bytes())                    # …f.txt's id now names g.txt's content
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="f.txt", self_validation="PASS")
    assert not out["accepted"] and "git fsck" in out["error"], out
    assert ST._where(e, None, make=False)[0] is None, "a refused DELIVER made the project's store"
    e.stop()


def test_a_plain_clone_of_the_project_delivers_its_commit(tmp_path):
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    _git(tmp_path, "clone", "-q", str(repo), str(clone := tmp_path / "clone"))
    head, out = _deliver(e, clone, "v1\n", place=str(clone))
    assert out["accepted"] and e.delivered(TaskId("root"))[1] == head, out
    assert _keeps(e) == {f"{ST.KEEP}{head}": head}
    e.stop()


def test_the_tree_bomb_guard_holds_a_checkout_to_what_its_place_held_at_deliver(tmp_path, monkeypatch):
    """The place's measure read when the delivery was kept is the comparator, not the place as it stands later (§5): a
    tree laying past it is refused, its place present or not."""
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    _take(e, repo)
    (repo / "big.bin").write_bytes(b"x" * (512 * 1024))
    head, out = _deliver(e, repo, "v1\n")
    assert out["accepted"], out
    rec = json.loads(e.graph.setting(ST.KEPT + head))
    assert rec.get("du_kib"), f"the keep recorded no measure of its place: {rec}"
    e.graph.store_setting(ST.KEPT + head, json.dumps({**rec, "du_kib": 1}))
    monkeypatch.setattr(W, "LAY_MARGIN_KIB", 0)
    with pytest.raises(NotTheDelivery, match="past what its place held"):
        with snapshot(ST.held(e, None, head), tmp_path / "judge", LocalExecution(), delivered=e.delivered(TaskId("root"))):
            pass
    e.stop()


def test_a_chat_delivers_beside_a_store_of_many_keeps(tmp_path):
    """The store's refs went on the command line: at some 1200 keeps Windows refused it (WinError 206), and every chat
    DELIVER was refused with a lift its sender cannot make (critic over 60d27c5)."""
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    _take(e, repo)
    start = _git(repo, "rev-parse", "HEAD")
    ST._keep(e, None, start, str(repo), str(repo), None)
    subprocess.run(["git", "-C", ST._where(e, None)[0], "update-ref", "--stdin"], check=True,
                   input="".join(f"create {ST.KEEP}many/{i} {start}\n" for i in range(1500)).encode())
    head, out = _deliver(e, repo, "v1\n")
    assert out["accepted"], out
    assert _keeps(e).get(f"{ST.KEEP}{head}") == head
    e.stop()


def test_a_deliver_the_engine_refuses_after_admission_writes_nothing(tmp_path):
    """Admission reads the sender's git and writes nothing: a DELIVER the engine's own rules then refuse made no store,
    no object, no record."""
    repo = _repo(tmp_path)
    e = _in_chat(tmp_path, repo)
    _take(e, repo)
    (repo / "f.txt").write_text("v1\n")
    head = _commit(repo, "f.txt")
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="", self_validation="PASS")
    _kept()
    assert not out["accepted"], out
    assert ST._where(e, None, make=False)[0] is None, "a refused DELIVER made the project's store"
    assert e.graph.setting(ST.KEPT + head) is None and not _git(repo, "for-each-ref", "refs/gfso/")
    e.stop()


def test_a_projects_deletion_removes_its_store_on_this_host(tmp_path):
    repo = _repo(tmp_path)
    e = _unregistered(tmp_path, repo)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    assert _deliver(e, repo, "v1\n", place=str(repo))[1]["accepted"]
    at = Path(ST._where(e, None)[0])
    e.stop()
    assert at.is_dir()
    WS.drop_host_files("p")
    assert not at.exists(), "the deleted project's store stands"


def test_the_one_time_migration_keeps_what_the_log_names_and_names_what_it_cannot(tmp_path):
    """On a scratch database alone: a project made before its store has its logged commits kept by their id, a
    delivery recorded with no commit named, and a role's directory with no git named with its lift, never made one."""
    repo = _repo(tmp_path)
    e = _unregistered(tmp_path, repo)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "user")
    head, _ = _deliver(e, repo, "v1\n", place=str(repo))
    _gone(ST._where(e, None)[0])                          # …as before the store was
    e.graph.store_setting(ST.KEPT + head, None)
    assert TL.TOOLS["signal"](e, "root", "FAIL", "user", failed_criteria=["f"], reason="again",
                              user_said="нет, ещё раз")["accepted"]
    got = T.signal(e, "root", "DELIVER", "user", result="done", self_validation="PASS")   # …a record with no commit
    assert got["accepted"], got
    (plain := tmp_path / "plain").mkdir()                 # …a role's directory from before a no-git one was refused
    AgentRegistry().register("old-exec", "llm-executor", workdir=str(plain), project="p")
    agents = TL._delegation().default_agents()
    got = ST.migrate(e, None, WS.repository(e, agents), WS.unjudged(e, agents))
    assert head in got["kept"] and _keeps(e).get(f"{ST.KEEP}{head}") == head, got
    assert ("root", State.VALIDATING.name) in got["no_commit"], got
    assert [a for a, why in got["no_repository"] if "git init" in why] == ["old-exec"], got
    assert not (plain / ".git").exists()
    e.stop()


def test_no_session_in_a_container_holds_the_store_writable(tmp_path, monkeypatch):
    """The store is the system's: in the slice before, the base was the store and a root's session had it writable —
    a keep deleted, a prune of what it named. Read off the mounts the system names, never by running a container."""
    monkeypatch.setattr(E, "_SESSIONS", {})
    (base := tmp_path / "work" / "ws").mkdir(parents=True)
    (tmp_path / "e.env").write_text("NOTHING=1\n")
    x = ContainerExecution("tstore", "img", str(tmp_path / "e.env"), str(tmp_path / "state"), str(base), "p")
    store = x.own / STORE_DIR
    for p in (store, store / ".git" / "objects", x.own):
        assert x.session(str(p)) is x, f"a session's container holds {p}"
    places = [x.base, x.own / "a", x.own / ".gfso-scratch-a" / "a_1", x.own / ".gfso-scratch-a" / "a_1" / "batch0",
              x.own / ".gfso-tmp" / "t", x.own / ".gfso-sys" / "s", x.own / ".gfso-state" / "+"]
    for p in places:
        s = x.session(str(p))
        assert isinstance(s, PlaceContainer), p
        for d, _ in s._mounts():
            assert not (d == store or store.is_relative_to(d) or d.is_relative_to(store)), \
                f"the session at {p} mounts {d}, which holds the store"
