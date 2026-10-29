"""A file the user's repository tracks by Git LFS comes into the agents' copy as its content and leaves in a delivery as
its pointer; what of the user's the copy lacks is said in the answer of the call that starts the work (the author,
2026-10-29: the user's agent must SEE what did not come in; carry the LFS objects, materialized by the system with no
config of the user's run, and never commit an LFS file's content as a blob)."""
import hashlib
import inspect
import io
import json
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

import gfso.adapters.execution as E
import gfso.adapters.lfs as L
import gfso.adapters.snapshots as S
import gfso.adapters.worktrees as W
import gfso.tools_llm as TL
from gfso.adapters.execution import ContainerExecution
from gfso.core.types import Mode
from tests.test_a_session_holds_only_its_own_place import IMAGE, _docker
from tests.support import REGISTER, criterion, make_engine
from tests.test_the_users_plan_and_the_stop_hold_in_every_door import _engine

CONTENT = b"\x00big binary\r\n" * 100


def _store(tmp_path, content=CONTENT):
    store = tmp_path / "store"
    oid = hashlib.sha256(content).hexdigest()
    (at := store / oid[:2] / oid[2:4] / oid).parent.mkdir(parents=True)
    at.write_bytes(content)
    return str(store), oid, at


def _smudged(data: bytes, stores) -> tuple:
    out = io.BytesIO()
    return L.smudge(io.BytesIO(data), out, stores), out.getvalue()


def test_a_pointer_parses_and_nothing_else_does():
    oid = "a" * 64
    assert L.parse(L.pointer(oid, 12)) == (oid, 12)
    assert L.parse(b"plain text\n") is None
    assert L.parse(L.pointer(oid, 12).replace(b"a" * 64, b"A" * 64)) is None, "an oid is lowercase hex"
    assert L.parse(L.pointer(oid, 12) + b"x" * L.LONGEST) is None, "longer than a pointer is content"


def test_a_pointer_is_written_as_its_verified_object_else_left_a_pointer(tmp_path):
    store, oid, at = _store(tmp_path)
    p = L.pointer(oid, len(CONTENT))
    assert _smudged(p, [str(tmp_path / "none"), store]) == (True, CONTENT), "found in a borrowed store"
    assert _smudged(b"not a pointer", [store]) == (False, b"not a pointer")
    assert _smudged(L.pointer("b" * 64, 3), [store]) == (False, L.pointer("b" * 64, 3)), "no object: the pointer"
    at.write_bytes(CONTENT[:-1])                                        # mutation: the size is not the pointer's
    assert _smudged(p, [store]) == (False, p)
    at.write_bytes(CONTENT[:-1] + b"?")                                 # …nor the sha256, at the right size
    assert _smudged(p, [store]) == (False, p)


def test_content_is_staged_as_its_pointer_and_kept_in_the_store(tmp_path):
    store = str(tmp_path / "s")
    out = io.BytesIO()
    L.clean(io.BytesIO(CONTENT), out, store)
    oid = hashlib.sha256(CONTENT).hexdigest()
    assert out.getvalue() == L.pointer(oid, len(CONTENT))
    assert open(L.path_in(store, oid), "rb").read() == CONTENT
    again = io.BytesIO()
    L.clean(io.BytesIO(out.getvalue()), again, store)
    assert again.getvalue() == out.getvalue(), "a pointer stays itself"


def test_a_clone_reads_the_store_of_the_objects_it_borrows(tmp_path):
    (alt := tmp_path / "c" / "objects" / "info").mkdir(parents=True)
    (alt / "alternates").write_text("../../base/.git/objects\n")
    assert L.stores_of(str(tmp_path / "c")) == [str(tmp_path / "c" / "lfs" / "objects"),
                                               str(tmp_path / "base" / ".git" / "lfs" / "objects")]


# ---- the filter as git runs it (here on the host, with this interpreter as the system's python) ----

_PY = '"' + sys.executable.replace("\\", "/") + '"'


def _g(cwd, *args, lfs=True, **kw):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *W.APART,
                           *(L.filter_args(_PY) if lfs else ()), *args], cwd=cwd, capture_output=True, check=True,
                          env={**W.subprocess_env(), **W.NO_CONFIG}, **kw).stdout


#: a git with no LFS filter at all: the host's git-lfs, or the system's, taken off
_NO_LFS = ("-c", "filter.lfs.process=", "-c", "filter.lfs.smudge=", "-c", "filter.lfs.clean=",
           "-c", "filter.lfs.required=false")


def _repo(tmp_path):
    (base := tmp_path / "ws").mkdir()
    _g(base, "init", "-q", "-b", "main")
    (base / ".gitattributes").write_bytes(b"*.bin filter=lfs diff=lfs merge=lfs -text\n")
    (base / "big.bin").write_bytes(CONTENT)
    (base / "gone.bin").write_bytes(b"its object will be lost")
    _g(base, "add", "-A")
    _g(base, "commit", "-qm", "base")
    return base


def test_a_raw_blob_at_an_lfs_path_checks_out_as_it_stands_without_hanging(tmp_path):
    """A teammate without git-lfs commits an asset after `lfs track` (git-lfs: "should have been pointers"): past a
    pipe's size, a filter writing before it had read all hung both ends — the import never finished (critic, run)."""
    (base := tmp_path / "ws").mkdir()
    _g(base, "init", "-q", "-b", "main")
    (base / ".gitattributes").write_bytes(b"*.bin filter=lfs diff=lfs merge=lfs -text\n")
    raw = bytes(range(256)) * (4 * 2 ** 12)                            # 4 MiB, no pointer
    (base / "raw.bin").write_bytes(raw)
    _g(base, "add", "-A", lfs=False)
    _g(base, "commit", "-qm", "raw", lfs=False)
    (base / "raw.bin").unlink()
    _g(base, "checkout", "--", "raw.bin", timeout=60)
    assert (base / "raw.bin").read_bytes() == raw


def _is_pointer(repo, rev, path, lfs=True) -> bool:
    return L.parse(_g(repo, "cat-file", "blob", f"{rev}:{path}", lfs=lfs)) is not None


def test_a_staging_under_the_systems_filter_commits_pointers_and_without_it_content(tmp_path):
    base = _repo(tmp_path)
    assert _is_pointer(base, "HEAD", "big.bin") and (base / "big.bin").read_bytes() == CONTENT
    (base / "big.bin").write_bytes(b"changed by the agent")
    assert W.stage(lambda *a: subprocess.run(["git", *W.APART, *L.filter_args(_PY), *a], cwd=base, text=True,
                                             capture_output=True, env={**W.subprocess_env(), **W.NO_CONFIG})
                   ).returncode == 0, "DELIVER's own staging"
    staged = _g(base, "cat-file", "blob", ":big.bin")
    assert L.parse(staged) == (hashlib.sha256(b"changed by the agent").hexdigest(), 20)
    assert (base / ".git" / "lfs" / "objects").is_dir()
    # …the control: the same staging with no filter commits the content — what the check above would catch
    _g(base, "rm", "-qf", "--cached", "big.bin", lfs=False)    # …else the index's stat cache keeps the staged pointer
    _g(base, "add", "big.bin", lfs=False)
    assert _g(base, "cat-file", "blob", ":big.bin", lfs=False) == b"changed by the agent"


def test_the_host_says_what_the_import_leaves_out_and_carries_what_it_holds(tmp_path):
    base = _repo(tmp_path)
    oid = L.parse(_g(base, "cat-file", "blob", "HEAD:gone.bin"))[0]
    git = E._host_git(base)
    held, missing = E._lfs_of(base, git)
    assert len(held) == 2 and missing == []
    assert E.left_out(base) == []
    (base / ".git" / "lfs" / "objects" / oid[:2] / oid[2:4] / oid).unlink()
    (base / "mine.txt").write_text("not committed")
    said = E.left_out(base)
    assert said[0].startswith(f"1 changed or untracked files of {base} are not in the agents' copy - commit them")
    assert said[1].startswith("1 files tracked by Git LFS have no object") and "gone.bin" in said[1]
    assert list(E._lfs_of(base, git)[0]) == [L.parse(_g(base, "cat-file", "blob", "HEAD:big.bin"))[0]]
    assert E.left_out(tmp_path / "no-git") == []


def test_the_call_that_starts_the_work_says_what_the_agents_copy_lacks(tmp_path, monkeypatch):
    base = _repo(tmp_path)
    (base / "mine.txt").write_text("not committed")
    x = ContainerExecution(f"t{time.time_ns()}", IMAGE, None, str(tmp_path / "state"), str(base), "p")
    monkeypatch.setattr(TL, "execution_of", lambda engine, agents=None: x)
    monkeypatch.setattr(TL._decompose, "default_llm", lambda *a, **k: None)
    monkeypatch.setattr(TL, "decompose_into", lambda engine, request, root_id, **kw: SimpleNamespace(
        root_id=root_id, holes=[], stats={"calls": 1}, d_md="", undecided_obligations=[], note=""))
    e = _engine(Mode.AUTO)
    e.record_llm_usage = lambda *a: None
    got = TL.auto_decompose(e, "the goal", spec={"name": "p"})
    assert got["not_imported"] == E.left_out(base) and "1 changed or untracked files" in got["not_imported"][0]
    assert "not_imported" in TL.start_project(e), "no import yet: said where the work starts again"
    e.graph.store_setting("volume:imported", '{"for": "root@1", "commit": "c"}')
    assert "not_imported" not in TL.start_project(e), "the import done: its root's answer said it"
    (base / "mine.txt").unlink()
    e.graph.store_setting("volume:imported", "")
    assert "not_imported" not in TL.start_project(e), "nothing left out: nothing said"


def test_the_root_made_by_hand_says_what_the_agents_copy_lacks(tmp_path, monkeypatch):
    base = _repo(tmp_path)
    (base / "mine.txt").write_text("not committed")
    x = ContainerExecution(f"t{time.time_ns()}", IMAGE, None, str(tmp_path / "state"), str(base), "p")
    monkeypatch.setattr(TL, "execution_of", lambda engine, agents=None: x)
    e = make_engine()
    e.start()
    root = TL.TOOLS["create_task"](e, "root", {"description": "goal", "criteria": [criterion("a", "A")],
                                               "accepted_risks": REGISTER}, assignee="me")
    assert root["not_imported"] == E.left_out(base) and "1 changed or untracked files" in root["not_imported"][0]
    kid = TL.TOOLS["create_task"](e, "root.x", {"description": "x", "criteria": [criterion("x1", "X")]},
                                  assignee="me", parent_id="root", covers=["a"])
    assert "not_imported" not in kid, "said where the root is made, not at every node"
    assert "not_imported" not in TL.TOOLS["create_task"](e, "other", {"description": "a second root"}), "refused"


def test_a_module_the_work_tree_holds_never_runs_in_the_filter(tmp_path):
    base = _repo(tmp_path)
    for m in ("base64", "zlib", "hashlib", "subprocess"):           # …git starts the filter at the work tree's top
        (base / f"{m}.py").write_text(f"open({str(base / 'RAN')!r}, 'a').write('{m}')\nraise SystemExit(7)\n")
    (base / "big.bin").write_bytes(b"changed")
    _g(base, "add", "-A")
    assert L.parse(_g(base, "cat-file", "blob", ":big.bin")) == (hashlib.sha256(b"changed").hexdigest(), 7)
    assert not (base / "RAN").exists(), "a delivered module ran under the system's git"


def test_one_filter_process_serves_a_git_call_and_the_repositorys_own_does_not_replace_it(tmp_path, monkeypatch):
    base = _repo(tmp_path)
    for i in range(20):
        (base / f"f{i}.bin").write_bytes(b"x" * i)
    _g(base, "config", "filter.lfs.process", f"touch {(tmp_path / 'THEIRS').as_posix()}", lfs=False)
    _g(base, "config", "filter.lfs.clean", f"touch {(tmp_path / 'THEIRS').as_posix()}", lfs=False)
    monkeypatch.setenv("GIT_TRACE", str(trace := tmp_path / "trace"))
    _g(base, "add", "-A")
    starts = [ln for ln in trace.read_text(errors="replace").splitlines() if "run_command" in ln and " -I -c " in ln]
    assert len(starts) == 1, starts
    assert not (tmp_path / "THEIRS").exists(), "the repository's own filter ran under the system's git"
    assert all(_is_pointer(base, "", f"f{i}.bin") for i in range(20))


def test_the_judges_command_line_rides_argv_on_windows(tmp_path):
    given = {"inherited": W.INHERITED, "spec": W.DELIVERED, "stage": inspect.getsource(W.stage), "kept_out": {}}
    at = "C:/" + "x" * 120
    line = subprocess.list2cmdline(["python3", "-c", S._JUDGES_GIT, at, "a" * 40, "b" * 40, at, json.dumps(given),
                                    *W.APART, *L.filter_args("python3")])
    assert len(line) < 16_000, len(line)                    # …CreateProcess's bound is 32767


def test_a_partial_clone_is_read_with_no_fetch_and_what_it_lacks_is_said(tmp_path, monkeypatch):
    src = _repo(tmp_path)
    (src / "d").mkdir()
    (src / "d" / "far.bin").write_bytes(b"in a directory the clone leaves out")
    _g(src, "add", "-A")
    _g(src, "commit", "-qm", "far")
    _g(src, "config", "uploadpack.allowFilter", "true", lfs=False)
    clone = tmp_path / "clone"
    _user(*_NO_LFS, "clone", "-q", "--sparse", "--filter=blob:none", src.as_uri(), str(clone), cwd=tmp_path)
    monkeypatch.setenv("GIT_TRACE", str(trace := tmp_path / "trace"))
    said = E.left_out(clone)
    _, no_object = E._lfs_of(clone, E._host_git(clone))
    with pytest.raises(OSError, match="partial clone"):
        E._carried_in(clone, "p", tmp_path)
    fetches = [ln for ln in trace.read_text(errors="replace").splitlines() if "fetch" in ln and "run_command" in ln]
    assert fetches == [], fetches
    assert said[0].startswith("1 objects of the history of") and "partial clone" in said[0], said
    assert no_object == ["big.bin", "gone.bin"], "the store is empty: a blob read is not a blob fetched"


# ---- live: the round trip in a project's volume ----

live = pytest.mark.skipif(not (_docker() and shutil.which("git-lfs")), reason=f"needs docker, {IMAGE} and git-lfs")


def _user(*args, cwd):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                          capture_output=True).stdout


def _users_project(tmp_path, monkeypatch):
    """(the user's repository, its LFS files committed by their own git-lfs — `gone.bin`'s object lost —, a container
    execution over it, what the import said, the project's record)."""
    monkeypatch.setattr(E, "_SESSIONS", {})
    monkeypatch.setattr(E, "_STARTED", {})
    (base := tmp_path / "w" / "ws").mkdir(parents=True)
    _user("init", "-q", "-b", "main", cwd=base)
    _user("lfs", "install", "--local", cwd=base)                       # …the user's own git-lfs made the commit
    _user("lfs", "track", "*.bin", cwd=base)
    (base / "big.bin").write_bytes(CONTENT)
    (base / "gone.bin").write_bytes(b"its object is lost")
    _user("add", "-A", cwd=base)
    _user("commit", "-qm", "base", cwd=base)
    gone = L.parse(_user("cat-file", "blob", "HEAD:gone.bin", cwd=base))[0]
    (base / ".git" / "lfs" / "objects" / gone[:2] / gone[2:4] / gone).unlink()
    record, said = {}, []
    x = ContainerExecution(f"t{time.time_ns()}", IMAGE, None, str(tmp_path / "state"), str(base), "p")
    x.volume.record, x.volume.root, x.volume.said = (record.get, record.__setitem__), lambda: "root@1", said.append
    return base, x, said, record


@live
def test_live_lfs_files_come_in_as_content_and_a_delivery_commits_their_pointers(tmp_path, monkeypatch):
    base, x, said, _ = _users_project(tmp_path, monkeypatch)
    try:
        x.run(["true"], cwd=str(x.base), timeout=120).check_returncode()
        assert x.files.read_bytes(str(x.base / "big.bin")) == CONTENT, "materialized, verified, by the system"
        assert L.parse(x.files.read_bytes(str(x.base / "gone.bin"))), "no object: the pointer stays"
        assert "1 files tracked by Git LFS have no object" in said[-1], said
        assert W.git(x.base, "status", "--porcelain", execution=x).stdout == "", "the base reads clean"
        a = x.own / "a"
        W.ensure(x.base, a, "gfso/p/a", x.base, execution=x)
        assert x.files.read_bytes(str(a / "big.bin")) == CONTENT, "a node's clone reads the base's store"
        x.session(str(a)).run(["sh", "-c", "printf new > big.bin"], cwd=str(a), timeout=120).check_returncode()
        W.commit_all(x.base, a, "work", "agent", x, branch="gfso/p/a")
        blob = lambda path, *lfs: x.session(str(a)).run(["git", *W.APART, *lfs, "cat-file", "blob", f"HEAD:{path}"],
                                                        cwd=str(a), timeout=120).stdout
        assert L.parse(blob("big.bin").encode()) == (hashlib.sha256(b"new").hexdigest(), 3), "a pointer committed"
        assert L.parse(blob("gone.bin").encode()) is not None
        assert x.files.read_bytes(L.path_in(str(a / ".git" / "lfs" / "objects"), hashlib.sha256(b"new").hexdigest())) \
            == b"new", "its content kept in the clone's store"
        # …the agent's own git, no `-c` of the system's (the image has no git-lfs): the clone's and the base's own config
        # name the system's filter, so it reads them clean and commits a pointer
        own = lambda at, *args: x.session(str(at)).run(["git", *args], cwd=str(at), timeout=120)
        assert own(x.base, "status", "--porcelain").stdout == "" and own(a, "status", "--porcelain").stdout == ""
        for at in (a, x.base):                                         # …a node's clone, and the root's base
            x.session(str(at)).run(["sh", "-c", "printf mine > big.bin"], cwd=str(at), timeout=120).check_returncode()
            own(at, "-c", "user.name=a", "-c", "user.email=a@a", "commit", "-qam", "own").check_returncode()
            assert L.parse(own(at, "cat-file", "blob", "HEAD:big.bin").stdout.encode()) == \
                (hashlib.sha256(b"mine").hexdigest(), 4), f"the agent's `commit -a` in {at} committed a pointer"
        # …the control: its git with the filter taken off stages the content, as the checks above would see
        env = {"GIT_INDEX_FILE": str(a / ".git" / "control-index")}
        off = ("-c", "filter.lfs.process=", "-c", "filter.lfs.required=false")
        for args in (("read-tree", "HEAD"), ("add", "big.bin")):
            x.session(str(a)).run(["git", *W.APART, *off, *args], cwd=str(a), timeout=120, env=env).check_returncode()
        assert x.session(str(a)).run(["git", *W.APART, "cat-file", "blob", ":big.bin"], cwd=str(a), timeout=120,
                                     env=env).stdout == "mine"
    finally:
        x.stop()
        x.volume.remove()


@live
def test_live_an_lfs_object_made_inside_reaches_the_parent_that_joins_it_and_the_users_store(tmp_path, monkeypatch):
    base, x, _, record = _users_project(tmp_path, monkeypatch)
    new = hashlib.sha256(b"new").hexdigest()
    try:
        x.run(["true"], cwd=str(x.base), timeout=120).check_returncode()
        since = json.loads(record["volume:imported"])["commit"]
        a, p = x.own / "a", x.own / "p"
        W.ensure(x.base, a, "gfso/p/a", x.base, execution=x)
        x.session(str(a)).run(["sh", "-c", "printf new > big.bin && printf lost > lost.bin"], cwd=str(a),
                              timeout=120).check_returncode()
        W.commit_all(x.base, a, "work", "agent", x, branch="gfso/p/a")
        assert x.files.read_bytes(L.path_in(str(x.base / ".git" / "lfs" / "objects"), new)) == b"new", \
            "carried into the base with the delivery's commits"
        W.ensure(x.base, p, "gfso/p/p", x.base, execution=x)
        assert W.merge(x.base, p, "gfso/p/a", "join a", execution=x) is None
        assert x.files.read_bytes(str(p / "big.bin")) == b"new", "the parent that joins it reads its content"
        # …an object no store holds any more: the landing names its file
        x.run(["sh", "-c", f"rm -f .git/lfs/objects/*/*/{hashlib.sha256(b'lost').hexdigest()}"], cwd=str(x.base),
              timeout=120).check_returncode()
        x.session(str(a)).run(["sh", "-c", "rm -rf .git/lfs"], cwd=str(a), timeout=120).check_returncode()
        assert W.merge(x.base, x.base, "gfso/p/a", "join a", execution=x) is None
        sha = W.land(x.base, "refs/heads/gfso/p/accepted", x, since)
        assert W.land_lfs(x.base, sha, since, x) == ["lost.bin"]
        assert (base / ".git" / "lfs" / "objects" / new[:2] / new[2:4] / new).read_bytes() == b"new"
        # …the user's own git-lfs checks the landed branch out from their store, no remote asked
        _user("checkout", "-q", "gfso/p/accepted", "--", "big.bin", cwd=base)
        assert (base / "big.bin").read_bytes() == b"new"
    finally:
        x.stop()
        x.volume.remove()
