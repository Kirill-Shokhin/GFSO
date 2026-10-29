"""Nothing of the host is mounted into a project's container: its base too stands in the project's volume — the user's
HEAD imported at the root's start by the user's own git (a bundle), cloned inside under no config or hook of theirs,
checked out LF — and the root's accepted result lands back in their repository as the branch `gfso/<project>/accepted`,
by `git fetch` of a bundle alone: their working tree and their branches untouched (the author, 2026-10-28: «изоляция
значит изоляция … бесшовно и одинаково в любой системе»; measured: Docker Desktop's host file sharing threw I/O errors
for 35 min on bind mounts, and a row died). `in_chat` work, done on the host, is refused under a container execution."""
import json
import subprocess
import time
from datetime import datetime
from types import SimpleNamespace

import pytest

import gfso.adapters.execution as E
import gfso.adapters.worktrees as W
import gfso.tools_llm as TL
import gfso.workspaces as WS
from gfso.adapters.execution import ContainerExecution
from gfso.core.types import PlaceUnavailable, State
from tests.support import make_engine
from tests.test_a_session_holds_only_its_own_place import IMAGE, _docker

live = pytest.mark.skipif(not _docker(), reason=f"needs docker and {IMAGE}")


def _git(cwd, *args) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def _inside(x, *args) -> str:
    """git over the base in the volume, as the system runs it (`W.git`)."""
    r = W.git(x.base, *args, execution=x)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.fixture
def user(tmp_path):
    """The user's repository on the host: CRLF checkout, a hook of theirs, a node branch left from before the base
    moved in, an `accepted` of an earlier root, and work of theirs not committed."""
    (base := tmp_path / "w" / "ws").mkdir(parents=True)
    _git(base, "init", "-q", "-b", "main")
    _git(base, "config", "core.autocrlf", "true")
    (base / "f.txt").write_bytes(b"one\r\ntwo\r\n")
    _git(base, "add", "f.txt")
    _git(base, "commit", "-qm", "base")
    _git(base, "branch", "gfso/p/old")
    _git(base, "branch", "gfso/p/accepted")
    (base / ".git" / "hooks" / "post-checkout").write_text("#!/bin/sh\ntouch HOOK-RAN\n")
    (base / ".git" / "info" / "exclude").write_bytes(b"*.log\n")
    (base / "mine.txt").write_text("the user's, not committed\n")
    return base


@pytest.fixture
def x(tmp_path, user, monkeypatch):
    monkeypatch.setattr(E, "_SESSIONS", {})
    monkeypatch.setattr(E, "_STARTED", {})
    record: dict = {}
    x = ContainerExecution(f"t{time.time_ns()}", IMAGE, None, str(tmp_path / "state"), str(user), "p")
    x.volume.record, x.volume.root = (record.get, record.__setitem__), lambda: "root@1"
    yield x
    x.stop()
    x.volume.remove()


def _imported(x) -> dict:
    return json.loads(x.volume.record[0]("volume:imported"))


def _mounts(container: str) -> list:
    got = subprocess.run(["docker", "inspect", "-f", "{{json .HostConfig.Mounts}}", container], capture_output=True,
                         text=True)
    return json.loads(got.stdout)


@live
def test_live_a_root_imports_the_users_head_lf_without_their_config_or_hooks_and_nodes_clone_from_it(x, user):
    head = _git(user, "rev-parse", "HEAD")
    a = x.own / "a"
    assert W.ensure(x.base, a, "gfso/p/a", x.base, execution=x), "a node's clone, made from the base in the volume"
    assert _imported(x) == {**_imported(x), "for": "root@1", "commit": head}, "the record: which root, which commit"
    assert x.files.read_bytes(str(x.base / "f.txt")) == b"one\ntwo\n", "checked out LF"
    assert x.files.read_bytes(str(a / "f.txt")) == b"one\ntwo\n"
    assert not x.files.exists(str(x.base / "mine.txt")), "the HEAD, not the user's uncommitted work"
    assert "autocrlf" not in _inside(x, "config", "--local", "--list")
    assert not x.files.exists(str(x.base / ".git" / "hooks" / "post-checkout"))
    assert not x.files.exists(str(x.base / "HOOK-RAN")) and not (user / "HOOK-RAN").exists()
    assert x.files.read_bytes(str(x.base / ".git" / "info" / "exclude")) == b"*.log\n"
    branches = _inside(x, "for-each-ref", "--format=%(refname:short)", "refs/heads/").split()
    assert "gfso/p/old" in branches and "gfso/p/accepted" not in branches, \
        "the project's node branches left from before come in; an earlier root's accepted does not"
    W.commit_all(x.base, a, "work", "agent", x, branch="gfso/p/a")
    assert _inside(x, "rev-parse", "gfso/p/a") == W.head(a, x), "a delivery taken back into the base in the volume"
    assert x.session(str(a)).run(["git", "fsck", "--connectivity-only"], cwd=str(a), timeout=120).returncode == 0
    for c in [x.container, x.session(str(a)).container, x.session(str(x.base)).container]:
        assert [m for m in _mounts(c) if m["Type"] == "bind"] == [], f"{c}: nothing of the host"
    assert any(m.get("VolumeOptions", {}).get("Subpath") == ".gfso-base" for m in _mounts(x.container))


def _engine(x, *roots):
    """A project as `root_created` and `land_accepted` read it: its roots, its record, its log; its execution `x`."""
    said, tasks, kept = [], list(roots), []
    e = SimpleNamespace(graph=SimpleNamespace(setting=x.volume.record[0], store_setting=x.volume.record[1],
                                              get_task=lambda i: next((t for t in tasks + kept if t.id == i), None)),
                        project_name="p", all_tasks=lambda: tasks, tasks=tasks, kept=kept,
                        emit_info=lambda who, text: said.append(text), said=said, accepted=[None])
    e.accepted_delivery = lambda task_id: (e.accepted[0], None)
    x.volume.root, x.volume.said = (lambda: WS.root_key(e)), (lambda text: said.append(text))
    return e


def _root(name="root", state=State.EXECUTING):
    return SimpleNamespace(id=name, parent_id=None, state=state, created_at=datetime.now())


def _joined(x) -> str:
    """A part joined into the base by the root's work, in the volume — its commit."""
    x.session(str(x.base)).run(["sh", "-c", "echo joined > joined.txt"], cwd=str(x.base), timeout=120)
    _inside(x, "add", "joined.txt")
    _inside(x, "commit", "-qm", "a part joined")
    return _inside(x, "rev-parse", "HEAD")


@live
def test_live_the_import_is_the_roots_and_no_start_ever_imports_over_it(x, user, monkeypatch):
    """The critic's case: the project's first start comes before its root (`auto_decompose` reads places first); the
    root adopts that import; a restart in mid-root — a switch turned, Docker restarted — imports nothing."""
    monkeypatch.setattr(WS, "execution_of", lambda engine, agents=None: x)
    e = _engine(x)
    x.run(["true"], cwd=str(x.base), timeout=120).check_returncode()
    first = _imported(x)
    assert first["for"] is None and first["commit"] == _git(user, "rev-parse", "HEAD")
    joined = _joined(x)
    _git(user, "commit", "-q", "--allow-empty", "-m", "the user moved on")
    _git(user, "branch", "-f", "gfso/p/old")
    e.tasks.append(root := _root())
    x.stop()                                 # …a start before the root's own act ran: still nothing imported
    assert _inside(x, "rev-parse", "HEAD") == joined, "a start never imports over a record"
    WS.root_created(e, None, root)
    assert _imported(x) == {**first, "for": WS.root_key(e)}, "adopted, not imported again"
    for _ in range(2):
        x.stop()
        assert _inside(x, "rev-parse", "HEAD") == joined, "a restart re-imports nothing over the root's work"
    assert _imported(x)["for"] == WS.root_key(e)


@live
def test_live_a_new_root_imports_again_unless_the_earlier_one_still_works_there(x, user, monkeypatch):
    monkeypatch.setattr(WS, "execution_of", lambda engine, agents=None: x)
    e = _engine(x, old := _root("old"))
    x.run(["true"], cwd=str(x.base), timeout=120).check_returncode()
    joined, kept = _joined(x), _inside(x, "rev-parse", "gfso/p/old")
    W.git(x.base, "branch", "-f", "gfso/p/old", joined, execution=x).check_returncode()
    _git(user, "commit", "-q", "--allow-empty", "-m", "the user moved on")
    e.tasks[:] = [new := _root("new")]
    e.kept.append(old)                                   # …the earlier root still stands, working
    WS.root_created(e, None, new)
    assert _inside(x, "rev-parse", "HEAD") == joined and "still works there" in e.said[-1]
    old.state = State.DONE
    WS.root_created(e, None, new)
    assert _inside(x, "rev-parse", "HEAD") == _git(user, "rev-parse", "HEAD"), "a new root starts from the user's HEAD"
    assert _inside(x, "rev-parse", "gfso/p/old") == joined != kept, "a branch standing in the volume is never overwritten"
    assert _imported(x)["for"] == WS.root_key(e)


@live
def test_live_a_base_with_no_git_is_imported_once_and_its_result_lands_beside_it(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "_SESSIONS", {})
    monkeypatch.setattr(E, "_STARTED", {})
    (base := tmp_path / "w" / "ws").mkdir(parents=True)
    (base / "f.txt").write_text("the user's\n")
    record: dict = {}
    x = ContainerExecution(f"t{time.time_ns()}", IMAGE, None, str(tmp_path / "state"), str(base), "p")
    x.volume.record = (record.get, record.__setitem__)
    monkeypatch.setattr(WS, "execution_of", lambda engine, agents=None: x)
    e = _engine(x, old := _root("old"))
    try:
        x.session(str(x.base)).run(["sh", "-c", "echo work > f.txt && echo new > w.txt"], cwd=str(x.base),
                                   timeout=120).check_returncode()
        assert _imported(x)["commit"] == "tree"
        (base / "f.txt").write_text("the user's, changed\n")
        x.stop()
        old.state = State.DONE
        e.tasks[:] = [new := _root("new")]
        WS.root_created(e, None, new)
        x.stop()
        assert x.files.read_bytes(str(x.base / "f.txt")) == b"work\n" and x.files.exists(str(x.base / "w.txt")), \
            "a root's work in a base with no git is never written over"
        assert "imported once" in e.said[-1] and _imported(x)["for"] == WS.root_key(e)
        assert WS.land_accepted(e, None, new) is None, e.said
        out = tmp_path / "w" / ".gfso-accepted-ws" / "p"
        assert (out / "f.txt").read_text() == "work\n" and (out / "w.txt").read_text() == "new\n"
        assert (base / "f.txt").read_text() == "the user's, changed\n", "the user's directory untouched"
    finally:
        x.stop()
        x.volume.remove()


@live
def test_live_the_import_says_what_of_the_users_did_not_come_in(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "_SESSIONS", {})
    monkeypatch.setattr(E, "_STARTED", {})
    (src := tmp_path / "subsrc").mkdir()
    _git(src, "init", "-q")
    _git(src, "commit", "-q", "--allow-empty", "-m", "s")
    (base := tmp_path / "w" / "ws").mkdir(parents=True)
    _git(base, "init", "-q", "-b", "main")
    (base / ".gitattributes").write_bytes(b"*.bin filter=lfs diff=lfs merge=lfs -text\n")
    _git(base, "add", ".gitattributes")
    _git(base, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(src), "sub")
    _git(base, "commit", "-qm", "base")
    (base / "mine.txt").write_text("not committed\n")
    record: dict = {}
    x = ContainerExecution(f"t{time.time_ns()}", IMAGE, None, str(tmp_path / "state"), str(base), "p")
    x.volume.record = (record.get, record.__setitem__)
    e = _engine(x)
    try:
        x.run(["true"], cwd=str(x.base), timeout=120).check_returncode()
        text = next(t for t in e.said if "imported" in t)
        assert _git(base, "rev-parse", "HEAD")[:12] in text
        assert "not imported: 1 changed or untracked files - commit them" in text
        assert "1 submodules stand empty inside" in text and "Git LFS are pointers" in text
        assert x.files.listdir(str(x.base / "sub")) == []
        # …a gitlink the agent moved to a commit of its choosing: landing never fetches the submodule's remote
        _git(base / "sub", "remote", "set-url", "origin", str(tmp_path / "no-such-remote"))
        W.git(x.base, "update-index", "--cacheinfo", f"160000,{'1' * 40},sub", execution=x).check_returncode()
        _inside(x, "commit", "-qm", "moved the submodule")
        monkeypatch.setattr(WS, "execution_of", lambda engine, agents=None: x)
        assert WS.land_accepted(e, None, SimpleNamespace(id="root")) is None, e.said
        assert _git(base, "rev-parse", "gfso/p/accepted") == _inside(x, "rev-parse", "HEAD")
    finally:
        x.stop()
        x.volume.remove()


@live
def test_live_landing_refuses_the_accepted_branch_checked_out_in_a_linked_worktree(x, user, monkeypatch, tmp_path):
    monkeypatch.setattr(WS, "execution_of", lambda engine, agents=None: x)
    e = _engine(x)
    x.run(["true"], cwd=str(x.base), timeout=120).check_returncode()
    _joined(x)
    _git(user, "worktree", "add", "-q", str(tmp_path / "linked"), "gfso/p/accepted")
    before = _git(user, "rev-parse", "gfso/p/accepted")
    assert "is checked out there" in WS.land_accepted(e, None, SimpleNamespace(id="root"))
    assert _git(user, "rev-parse", "gfso/p/accepted") == before


@live
def test_live_a_lost_volume_under_the_import_record_is_the_place_down_never_imported_again(x):
    x.run(["true"], cwd=str(x.base), timeout=120).check_returncode()
    x.stop()
    subprocess.run(["docker", "volume", "rm", "-f", x.volume.name], capture_output=True, check=True)
    with pytest.raises(PlaceUnavailable, match="is gone"):
        x.run(["true"], cwd=str(x.base), timeout=120)
    assert subprocess.run(["docker", "volume", "inspect", x.volume.name], capture_output=True).returncode != 0


@live
def test_live_a_roots_pass_lands_on_the_accepted_branch_and_the_users_tree_and_branches_stay(x, user, monkeypatch):
    main, status = _git(user, "rev-parse", "main"), _git(user, "status", "--porcelain")
    x.session(str(x.base)).run(["sh", "-c", "echo between > b.txt && git add b.txt && "
                                            "git -c user.name=g -c user.email=g@g commit -qm between && "
                                            "echo accepted > a.txt && git add a.txt && "
                                            "git -c user.name=g -c user.email=g@g commit -qm accepted"],
                               cwd=str(x.base), timeout=120).check_returncode()
    accepted = _inside(x, "rev-parse", "HEAD")
    monkeypatch.setattr(WS, "execution_of", lambda engine, agents=None: x)
    e = _engine(x)
    # …the PASS accepted another tree than the base's HEAD holds now (a leftover moved it): nothing lands (critic)
    e.accepted[0] = _inside(x, "rev-parse", "HEAD~1^{tree}")
    stood = subprocess.run(["git", "rev-parse", "--verify", "-q", "gfso/p/accepted"], cwd=user, capture_output=True,
                           text=True).stdout
    assert "not the" in WS.land_accepted(e, None, SimpleNamespace(id="root"))
    assert subprocess.run(["git", "rev-parse", "--verify", "-q", "gfso/p/accepted"], cwd=user, capture_output=True,
                          text=True).stdout == stood != accepted + "\n", "nothing landed"
    e.accepted[0] = _inside(x, "rev-parse", "HEAD^{tree}")
    assert WS.land_accepted(e, None, SimpleNamespace(id="root")) is None, e.said
    assert _git(user, "rev-parse", "gfso/p/accepted") == accepted and accepted[:12] in e.said[0]
    assert _git(user, "show", "gfso/p/accepted:a.txt") == "accepted"
    assert _git(user, "rev-parse", "main") == main and _git(user, "status", "--porcelain") == status, \
        "the user's branch and working tree as they were"
    assert (user / "mine.txt").read_text() == "the user's, not committed\n" and not (user / "a.txt").exists()
    x.volume.record[1]("volume:imported", json.dumps({**_imported(x), "commit": _inside(x, "rev-parse", "HEAD~1")}))
    _git(user, "branch", "-f", "gfso/p/accepted", "main")
    _git(user, "checkout", "-q", "gfso/p/accepted")
    assert "is checked out there" in WS.land_accepted(e, None, SimpleNamespace(id="root"))
    _git(user, "checkout", "-q", "main")
    _git(user, "reflog", "expire", "--expire=now", "--all")
    _git(user, "gc", "-q", "--prune=now")
    assert subprocess.run(["git", "cat-file", "-e", accepted], cwd=user).returncode != 0
    assert WS.land_accepted(e, None, SimpleNamespace(id="root")) is None, \
        "a bundle over a commit the user's repository lacks is carried whole"
    assert _git(user, "rev-parse", "gfso/p/accepted") == accepted
    out = x.parent.parent / "out"
    E.export_places("p", {**{k: x.volume.record[0](k) for k in ("volume:places", "volume:state")},
                          "volume:base": str(x.base), "volume:image": IMAGE}, str(out))
    heads = subprocess.run(["git", "bundle", "list-heads", str(out / "p" / "gfso-refs.bundle")], capture_output=True,
                           text=True, cwd=user).stdout
    assert accepted in heads and "refs/heads/gfso/p/old" in heads, "the export carries the base's branches"
    assert (out / "p" / ".gfso-base" / "a.txt").read_text() == "accepted\n"


@live
def test_live_a_project_from_before_keeps_its_clones_once_its_base_moves_in(tmp_path, monkeypatch):
    """A live project whose places stood on the host (copied in) or already in the volume, its base still the host's
    (no import record), restarted: its base imported with its node branches, every clone reading through it."""
    monkeypatch.setattr(E, "_SESSIONS", {})
    monkeypatch.setattr(E, "_STARTED", {})
    (base := tmp_path / "w" / "ws").mkdir(parents=True)
    _git(base, "init", "-q", "-b", "main")
    (base / "f.txt").write_text("base\n")
    _git(base, "add", "f.txt")
    _git(base, "commit", "-qm", "base")
    (a := tmp_path / "w" / ".gfso-nodes-ws" / "p" / "a").mkdir(parents=True)  # …a clone as the host made it before
    _git(a, "init", "-q")
    (a / ".git" / "objects" / "info" / "alternates").write_bytes(b"../../../../../ws/.git/objects\n")
    _git(a, "checkout", "-q", "-b", "gfso/p/a", _git(base, "rev-parse", "HEAD"))
    (a / "w.txt").write_text("work\n")
    _git(a, "add", "w.txt")
    _git(a, "commit", "-qm", "work")
    _git(base, "fetch", "-q", str(a), "gfso/p/a:gfso/p/a")
    record: dict = {}
    x = ContainerExecution(f"t{time.time_ns()}", IMAGE, None, str(tmp_path / "state"), str(base), "p")
    x.volume.record = (record.get, record.__setitem__)
    clone = x.own / "a"
    try:
        for again in (False, True):
            if again:            # …the shape of a volume made before the base moved in: records, no base in it
                x.stop()
                del record["volume:imported"]
                x.volume._one_shot(IMAGE, ["--mount", f"type=volume,src={x.volume.name},dst=/to"],
                                   ["rm -rf /to/.gfso-base"], "drop").check_returncode()
            r = x.session(str(clone)).run(["git", "fsck", "--connectivity-only"], cwd=str(clone), timeout=120)
            assert r.returncode == 0, r.stderr
            assert _inside(x, "rev-parse", "gfso/p/a") == W.head(clone, x), "its branch in the base, as before"
            assert not W.ensure(x.base, clone, "gfso/p/a", x.base, execution=x), "its place reused as it stands"
            assert W.merge(x.base, x.base, "gfso/p/a", "join", execution=x) is None
            assert x.files.read_bytes(str(x.base / "w.txt")) == b"work\n"
    finally:
        x.stop()
        x.volume.remove()


def test_in_chat_is_refused_under_a_container_execution_with_what_lifts_it(monkeypatch):
    """The user's own agent works on the host, where nothing of the project's places stands: what it did there would
    never be what is judged (§11.3) — refused, both ways round, never left to fail later."""
    e = make_engine()
    monkeypatch.setattr(TL, "declaring_role", lambda engine, agents=None: {"execution": "e3-linux"})
    got = TL.set_mode(e, "solo", perform="in_chat")
    assert got["refused"] and "'e3-linux'" in got["error"] and 'perform="dispatch"' in got["error"]
    assert TL.mode_staffing(e, "solo", "in_chat")["missing"] == got["error"], "the page reads the same rule"
    monkeypatch.setattr(e, "mode", lambda: {"mode": "solo", "perform": "in_chat"})
    got = TL.register_agent(e, "p-exec", "llm-executor", workdir=".", execution="e3-linux")
    assert got["refused"] and "in_chat work is done on this host" in got["error"]


def test_the_host_takes_only_a_bundle(tmp_path, monkeypatch):
    """The bytes come out of a temp the base's sessions write; handed anything else, the host's git opened a repository
    named inside it, a network path too (critic over a99ea34). No git runs on what is no bundle."""
    ran = []
    monkeypatch.setattr(E, "run", lambda *a, **kw: ran.append(a) or subprocess.CompletedProcess(a, 0, "", ""))
    assert "no git bundle" in E.fetched_on_host(tmp_path, b"//attacker/share/repo\n")
    assert ran == []
    assert E.fetched_on_host(tmp_path, b"# v2 git bundle\nabc HEAD\n\nPACK") == "" and ran


def test_a_commit_left_without_its_blobs_is_fetched_again_never_landed(tmp_path, monkeypatch):
    """A fetch that failed leaves the commit and its tree in the user's store without their blobs; a landing retried
    on them found the commit and set the branch to what no checkout reads (critic over e59b9d5, run)."""
    env = {"GIT_AUTHOR_NAME": "a", "GIT_AUTHOR_EMAIL": "a@a", "GIT_COMMITTER_NAME": "a", "GIT_COMMITTER_EMAIL": "a@a",
           "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z"}
    g = lambda repo, *a, **kw: subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True,
                                              env={**W.subprocess_env(), **env}, **kw)
    full, user = tmp_path / "full", tmp_path / "user"
    for r in (full, user):
        g(tmp_path, "init", "-q", "-b", "main", str(r))
    (full / "a.txt").write_text("the content\n")
    g(full, "add", "a.txt")
    sha = g(full, "commit-tree", g(full, "write-tree").stdout.strip(), "-m", "c").stdout.strip()
    g(full, "update-ref", "HEAD", sha)
    (user / "u.txt").write_text("u\n")
    g(user, "add", "u.txt")
    g(user, "commit", "-qm", "u")
    blob = g(full, "rev-parse", "HEAD:a.txt").stdout.strip()            # …the commit planted, its blob not
    tree = subprocess.run(["git", "-C", str(user), "mktree", "--missing"], capture_output=True,   # …bytes: a text
                          input=f"100644 blob {blob}\ta.txt\n".encode()).stdout.decode().strip()  # stdin ends in CRLF
    assert g(user, "commit-tree", tree, "-m", "c").stdout.strip() == sha
    bundle = g(full, "bundle", "create", str(tmp_path / "b"), "HEAD")
    monkeypatch.setattr(W, "git", lambda *a, **kw: subprocess.CompletedProcess(a, 0, sha + "\n", ""))
    monkeypatch.setattr(W, "_bundled", lambda *a: (tmp_path / "b").read_bytes())
    g(user, "update-ref", "refs/heads/gfso/q/accepted", sha)          # …as the old landing left one: a ref on it
    with pytest.raises(OSError, match="could not be fetched"):        # git's own fetch trusts that ref: refused,
        W.land(user, "refs/heads/gfso/p/accepted", None, None, tree)  # never said landed
    assert g(user, "rev-parse", "--verify", "-q", "gfso/p/accepted").returncode != 0
    g(user, "update-ref", "-d", "refs/heads/gfso/q/accepted")
    assert bundle.returncode == 0 and W.land(user, "refs/heads/gfso/p/accepted", None, None, tree) == sha
    assert g(user, "rev-list", "--objects", "--missing=error", "gfso/p/accepted").returncode == 0, "landed whole"
    assert g(user, "cat-file", "blob", f"{sha}:a.txt").stdout == "the content\n"
