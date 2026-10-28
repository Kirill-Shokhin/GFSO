"""The runs of one validation, side by side, each validate their own copy of the place as it stands on disk.

GB_sql_database_tngtvm580 (2026-10-25): the root's validation ran in 12 batches at once, all in the root's place, and
its pinned checks begin with `make clean`. One run's clean took `./sql_database` from under another's probes; the
validators fled to copies in their scratch, whose paths then stood in the filed findings — a false root FAIL over a
tree that passes every root check alone. Fake validators, real git, and a real container where one is at hand.
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import threading
import time
from pathlib import Path

import pytest

from gfso import tools as T
from gfso import tools_llm as TL
from gfso.adapters import snapshots as S
from gfso.adapters import worktrees as W
from gfso.adapters.execution import ContainerExecution, LocalExecution, scratch_of
from gfso.delegate import _classify_no_verdict
from tests.support import criterion
from tests.test_validate_result import _eng, _fenced

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="a node's place is a git worktree")

_LINE = re.compile(r"PINNED CHECK \[([^\]]+)\] — ([^:]+): run `([^`]+)`")
_BS = chr(92)


def _git(cwd, *args) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def place(tmp_path):
    """A node's place beside its base: a delivery commit with a built binary, an ignored object file, an uncommitted
    note — what the validator judges is all of it."""
    base = tmp_path / "base"
    base.mkdir()
    (base / ".gitignore").write_text("*.o\n")
    (base / "main.c").write_text("int main(void) { return 0; }\n")
    for args in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "starter")):
        _git(base, *args)
    at = tmp_path / ".gfso-nodes-base" / "proj" / "big"
    W.ensure(base, at, "gfso/proj/big", base)
    (at / "app").write_text("the delivered build\n")
    _git(at, "add", "-A")
    _git(at, "commit", "-q", "-m", "gfso: big delivery")
    (at / "main.o").write_text("an object file\n")
    (at / "notes.txt").write_text("not committed\n")
    return base, at


class _Run:
    """One validator run: meets the other run, then does what a pinned check does in its cwd — `make clean` takes the
    build away, a `touch` moves a time, a test leaves a read-only directory — and answers naming its cwd."""

    def __init__(self, meet: threading.Barrier, seen: list, spell=Path.as_posix, edit: bool = False):
        self.meet, self.seen, self.spell, self.edit = meet, seen, spell, edit
        self.calls, self.last_tool_calls = [], {}
        self.on_tick = self.stage_hint = None

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.calls.append({"duration_ms": 1, "input_tokens": 1, "output_tokens": 1})
        here = Path(cwd)
        self.meet.wait(20)
        had = sorted(p.name for p in here.iterdir() if p.name != ".git")
        (here / "app").unlink(missing_ok=True)                                  # the pinned `make clean`…
        os.utime(here / ".gitignore", (1, 1))                                   # …a `touch`: no edit
        (ro := here / "out" / "ro").mkdir(parents=True, exist_ok=True)
        (ro / "f").write_text("x")
        os.chmod(ro / "f", stat.S_IREAD)
        os.chmod(ro, stat.S_IREAD | stat.S_IEXEC)
        if self.edit:
            (here / "main.c").write_text("int main(void) { return 1; }\n")
        self.meet.wait(20)
        self.seen.append({"cwd": cwd, "had": had, "packet": user})
        return self.answer(user, here)

    def answer(self, user, here) -> str:
        entries = []
        for name in ("one", "two"):
            mine = [(i, b, c) for i, b, c in _LINE.findall(user) if i.startswith(f"{name}#")]
            if mine:
                entries.append({"criterion": name, "verdict": "pass", "evidence": f"ran it in {self.spell(here)}",
                                "behaviours": [b for _, b, _ in mine],
                                "probe": [{"id": i, "behaviour": b, "command": f"cd {self.spell(here)} && {c}",
                                           "expect": "ok"} for i, b, c in mine]})
        return _fenced({"verdict": "PASS", "failed_criteria": [], "per_criterion": entries})

    def tag_last(self, stage):
        if self.calls:                                     # …as the port's: a validation may have made none
            self.calls[-1]["stage"] = stage


def _task(e, n: int):
    T.create_task(e, "big", {"description": "criteria, one run each", "criteria": [
        criterion(c, check=[{"behaviour": f"b{c}", "command": "make clean; ./app", "expect": "ok"}])
        for c in ("one", "two")[:n]]}, "alice")
    T.signal(e, "big", "ACCEPT", "alice")
    T.signal(e, "big", "DELIVER", "alice", result="built it")


def _validate(monkeypatch, at, n: int = 2, **run):
    monkeypatch.setenv("GFSO_VALIDATION_BATCH", "1" if n > 1 else "0")
    e = _eng()
    _task(e, n)
    meet, seen = threading.Barrier(n), []
    out = TL.validate_result(e, "big", workdir=str(at), _llm=_Run(meet, seen, **run),
                             _spawn=lambda: _Run(meet, seen, **run))
    return e, out, seen


def _commands(e) -> list:
    return [p["command"] for x in e.get_exec_verdict(T.TaskId("big"))["per_criterion"] for p in x["probe"]]


def test_each_run_validates_its_own_copy_of_the_place_and_the_report_names_the_place(monkeypatch, place):
    base, at = place
    e, out, seen = _validate(monkeypatch, at)
    assert len(seen) == 2
    cwds = {s["cwd"] for s in seen}
    assert len(cwds) == 2 and str(at) not in cwds                      # …a copy per run, neither the place
    for s in seen:
        assert s["had"] == [".gitignore", "app", "main.c", "main.o", "notes.txt"], s["had"]   # …the place on disk
        assert "a copy of the delivery's directory" in s["packet"] and s["cwd"] in s["packet"]
        assert "run no git command that writes (no commit, checkout -b, gc, worktree prune)" in s["packet"]
        assert "is not reached" not in s["packet"]                    # …the copy shares the base's refs
        assert str(at) not in s["packet"] and at.as_posix() not in s["packet"]
    assert (at / "app").is_file() and (at / "main.o").is_file()         # …and no run's clean reached the delivery
    assert out["verdict"] == "PASS"
    cmds = _commands(e)
    assert cmds and all(c.startswith(f"cd {at.as_posix()} && ") for c in cmds), cmds   # …read as run in the place
    assert all(not Path(c).exists() for c in cwds)                       # …the copies gone, read-only dirs and all
    assert _git(base, "worktree", "list", "--porcelain").count("worktree ") == 1       # …and nothing registered (the place is a repository of its own)
    e.stop()


def test_a_single_run_validates_a_copy_too(monkeypatch, place):
    """Nothing runs beside it, and still not in the place: the validator judges the delivery and must not be able to
    change it (§10.3) — an edit of its own, made in the place, went into the next commit as the executor's (security,
    2026-10-27). Its packet names the copy, as a batch's does."""
    _, at = place
    e, out, seen = _validate(monkeypatch, at, n=1)
    assert len(seen) == 1 and seen[0]["cwd"] != str(at) and seen[0]["cwd"].endswith("delivery")
    assert "a copy of the delivery's directory" in seen[0]["packet"]
    e.stop()


_SPELLINGS = {
    "native": str,
    "msys": lambda p: "/" + p.drive[0].lower() + p.as_posix()[2:] if p.drive else p.as_posix(),
    "lower drive": lambda p: p.as_posix()[0].lower() + p.as_posix()[1:],
    "doubled": lambda p: str(p).replace(_BS, _BS * 2),
}


@pytest.mark.parametrize("spelling", sorted(_SPELLINGS))
def test_the_copy_is_mapped_back_in_the_spelling_the_report_used(monkeypatch, place, spelling):
    """A finding left naming the removed copy stays demanded over a directory that no longer exists."""
    _, at = place
    e, _, _ = _validate(monkeypatch, at, spell=_SPELLINGS[spelling])
    want = _SPELLINGS[spelling](at).replace(_BS * 2, _BS)
    named = {c.split(" && ")[0][3:].replace(_BS * 2, _BS) for c in _commands(e)}
    assert named and all(n.lower() == want.lower() and n[:2] == want[:2] for n in named), (named, want)
    e.stop()


def test_swap_keeps_every_spelling_and_takes_no_neighbour():
    """The critic's cases over d0fc0b5: msys written back as `C:/` broke a PATH entry, `/mnt/c/` became `/mntC:/`."""
    wd, tree = Path("C:/w/n/p/root"), Path("C:/w/n/p/.gfso-scratch-root/r/batch1/delivery")
    t = tree.as_posix()[2:]
    cases = {
        "PATH=/c/w/n/p/root/bin:$PATH": f"PATH=/c{t}/bin:$PATH",
        "X=/a:/c/w/n/p/root/bin": f"X=/a:/c{t}/bin",
        "cd /mnt/c/w/n/p/root": f"cd /mnt/c{t}",
        "cd /cygdrive/c/w/n/p/root": f"cd /cygdrive/c{t}",
        "c:/W/n/p/root/x": f"c:{t}/x",
        str(wd) + _BS + "a": str(tree) + _BS + "a",
        str(wd).replace(_BS, _BS * 2): str(tree).replace(_BS, _BS * 2),
        "C:/w/n/p/root.select/x": "C:/w/n/p/root.select/x",
        "/x/c/w/n/p/root": "/x/c/w/n/p/root",
        "xC:/w/n/p/root": "xC:/w/n/p/root",
    }
    for s, want in cases.items():
        assert S.swap(s, wd, tree) == want, s
        assert S.swap(want, tree, wd).lower() == s.lower()


def test_the_copy_is_made_and_removed_where_the_work_runs(monkeypatch, place):
    """Host-side, a container's symlink is no link: the copy is the execution's, as a delivery's commit is."""
    class _Seen(LocalExecution):
        def __init__(self):
            self.ops = []

        def copy_tree(self, src, dst):
            self.ops.append("copy")
            super().copy_tree(src, dst)

        def remove_tree(self, path):
            self.ops.append("remove")
            super().remove_tree(path)
    ex = _Seen()
    monkeypatch.setattr(TL, "execution_of", lambda *_: ex)
    _, at = place
    e, out, _ = _validate(monkeypatch, at)
    assert out["verdict"] == "PASS" and sorted(ex.ops) == ["copy"] * 2 + ["remove"] * 2, ex.ops
    e.stop()


def test_a_committed_file_a_run_changed_is_said_and_the_delivery_is_untouched(monkeypatch, place):
    """Compared before it goes: a changed committed file is named, as a stray in the place is — a fact for the record
    (a pinned `make` may rebuild a committed binary), not a verdict. A touch alone changes nothing."""
    _, at = place
    e, out, _ = _validate(monkeypatch, at, edit=True)
    assert out["validator_edits"] == ["app", "main.c"]          # …the clean's deletion and the edit, not .gitignore
    assert (at / "main.c").read_text() == "int main(void) { return 0; }\n"
    e.stop()


def test_the_copy_is_a_repository_of_its_own(place, tmp_path):
    """Copied as is, a worktree's relative `.git` names nothing; pointed back, the runs would share one index and a
    run's commit would move the delivery's branch."""
    _, at = place
    branch = _git(at, "rev-parse", "HEAD")
    with S.snapshot(at, tmp_path / "copy", LocalExecution()) as c:
        assert _git(c, "rev-parse", "HEAD") == branch
        assert _git(c, "status", "--porcelain", "--untracked-files=no") == ""
        _git(c, "commit", "-q", "--allow-empty", "-m", "a validator's commit")
    assert _git(at, "rev-parse", "HEAD") == branch and not (tmp_path / "copy").exists()


def _image() -> str | None:
    if not shutil.which("docker"):
        return None
    r = subprocess.run(["docker", "image", "inspect", "e3-linux-agent:2"], capture_output=True)
    return "e3-linux-agent:2" if r.returncode == 0 else None


@pytest.mark.skipif(_image() is None, reason="needs docker and the e3-linux-agent:2 image")
def test_a_link_made_in_a_container_survives_its_copy_there(tmp_path):
    """The critic's cont2 over d0fc0b5: a checkout by either side's git (core.symlinks=false) lost the link; `cp -a`
    inside keeps it, the copy is a repository of its own there, its edits are read there (on the host the link is no
    file to read), and a read-only directory a test made does not stop its removal."""
    root = tmp_path / "w"
    base = root / "base"
    (root / "state").mkdir(parents=True)
    (root / "env").write_text("")
    base.mkdir()
    (base / "a.sh").write_text("echo hi\n", newline="\n")
    for args in (("init", "-q"), ("config", "core.symlinks", "false"), ("add", "-A"), ("commit", "-q", "-m", "s")):
        _git(base, *args)
    place = root / ".gfso-nodes-base" / "proj" / "root"
    W.ensure(base, place, "gfso/proj/root", base)
    ex = ContainerExecution("snap", _image(), str(root / "env"), str(root / "state"), str(base), "proj")
    sh = lambda cmd, cwd: ex.run(["sh", "-c", cmd], cwd=str(cwd), timeout=60)
    try:
        sh("ln -s a.sh run.sh && echo built > out.bin", place)
        W.commit_all(base, place, "delivery", "agent", ex)
        head = sh("git rev-parse HEAD", place).stdout.strip()
        at = root / ".gfso-nodes-base" / "proj" / ".gfso-scratch-root" / "r" / "batch1" / "delivery"
        at.parent.mkdir(parents=True)
        edits: list = []
        with S.snapshot(place, at, ex, edits) as c:
            assert sh("test -L run.sh && readlink run.sh", c).stdout.strip() == "a.sh"
            assert sh("git rev-parse HEAD", c).stdout.strip() == head
            sh("rm out.bin && echo bye >> a.sh && touch run.sh && git commit -qam v && "
               "mkdir -p ro && touch ro/f && chmod a-w ro ro/f", c)
        assert edits == ["a.sh", "out.bin"] and not at.exists()
        assert sh("git rev-parse HEAD", place).stdout.strip() == head                 # …the delivery's branch stays
        assert sh("test -L run.sh && echo LINK", place).stdout.strip() == "LINK"
        assert _git(base, "worktree", "list", "--porcelain").count("worktree ") == 1
    finally:
        sh("rm -f run.sh", place)                           # a container's link is no file the host can remove
        ex.stop()


@pytest.mark.parametrize("network", [None, {"mode": "off"}])
def test_what_an_executor_made_unreadable_in_its_place_does_not_stop_its_copy(tmp_path, network):
    """Copied by the agent's user, one `chmod 000` in the executor's own place failed every copy, and where places stand
    apart its delivery was then never judged (critic over the judges slice). By root in the project's container, under
    every switch: the copy stands, its owner kept, so a judge — the agent's user — works in it."""
    if not (image := _image()):
        pytest.skip("no docker image")
    root = tmp_path / "w"
    (base := root / "base").mkdir(parents=True)
    (root / "state").mkdir()
    ex = ContainerExecution("snap", image, None, str(root / "state"), str(base), "chmodprobe", network=network)
    sh = lambda cmd, cwd: ex.run(["sh", "-c", cmd], cwd=str(cwd), timeout=60)
    try:
        sh("mkdir -p d && echo x > f && echo y > d/g && chmod 000 f d", base)
        (at := scratch_of(base, "chmodprobe") / "r" / "delivery").parent.mkdir(parents=True)
        ex.copy_tree(str(base), str(at))
        with pytest.raises(OSError, match="already exists"):     # …never INTO what stands there (critic 3)
            ex.copy_tree(str(base), str(at))
        assert sh("chmod u+rwX f d && cat f d/g && touch new && echo WROTE", at).stdout.split() == ["x", "y", "WROTE"]
    finally:
        sh("chmod -R u+rwX .", base)
        ex.stop()


class _Timed(_Run):
    """A run that only takes its time, logging when it stood where."""

    def __init__(self, log: list):
        super().__init__(threading.Barrier(1), [])
        self.log = log

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.calls.append({"duration_ms": 1, "input_tokens": 1, "output_tokens": 1})
        t = time.monotonic()
        time.sleep(0.3)
        self.log.append(("run", cwd, t, time.monotonic()))
        return self.answer(user, Path(cwd))


class _Copies(LocalExecution):
    """A host whose copy of `batch<fail>` cannot be made — `fail` raises it — and whose other copies take their time."""

    def __init__(self, log: list, fail=(1, 2), raise_=lambda: OSError(1314, "A required privilege is not held")):
        self.log, self.fail, self.raise_ = log, fail, raise_

    def copy_tree(self, src, dst):
        if any(f"batch{i}" in dst for i in self.fail):
            Path(dst, "half").mkdir(parents=True)                  # …a partial copy, as a cut `cp -a` leaves
            raise self.raise_()
        t = time.monotonic()
        time.sleep(0.3)
        super().copy_tree(src, dst)
        self.log.append(("copy", dst, t, time.monotonic()))


def _timed(monkeypatch, at, ex):
    monkeypatch.setattr(TL, "execution_of", lambda *_: ex)
    monkeypatch.setenv("GFSO_VALIDATION_BATCH", "1")
    e = _eng()
    _task(e, 2)
    out = TL.validate_result(e, "big", workdir=str(at), _llm=_Timed(ex.log), _spawn=lambda: _Timed(ex.log))
    return e, out


def _overlap(a, b) -> bool:
    return a[2] < b[3] and b[2] < a[3]


@pytest.mark.parametrize("cause", ["privilege", "timeout"])
def test_runs_that_could_not_copy_take_the_place_one_at_a_time(monkeypatch, place, tmp_path, cause):
    """The fallback must not reopen the race: WinError 1314 on a host that may not make links, or a `cp -a` past its
    time on a large root. The partial copy goes; the runs stand in the place in turn; the report is not lost."""
    _, at = place
    raise_ = (lambda: OSError(1314, "privilege")) if cause == "privilege" else         (lambda: subprocess.TimeoutExpired(["cp", "-a"], 1800))
    ex = _Copies([], raise_=raise_)
    e, out = _timed(monkeypatch, at, ex)
    runs = [x for x in ex.log if x[0] == "run"]
    assert [r[1] for r in runs] == [str(at)] * 2
    assert not _overlap(*runs), runs
    assert out["verdict"] == "PASS"
    assert not list(at.parent.glob(".gfso-scratch-big/*/batch*/delivery"))      # …no partial copy left
    e.stop()


class _Apart(_Copies):
    """The same failing copies where places stand apart (`ExecutionPort.apart`): a container's."""
    apart = True


def test_where_places_stand_apart_a_run_that_could_not_copy_is_not_judged_in_the_executors_place(monkeypatch, place):
    """There the place is its executor's container and CLI state, and its tree a run could change (§10.3): no run, no
    verdict — a validator that never started, said as such: no refusal booked, no stop of a place that answers, and
    asked again on its own tier, not a bigger one (critics over this slice)."""
    _, at = place
    ex = _Apart([])
    e, out = _timed(monkeypatch, at, ex)
    assert not [x for x in ex.log if x[0] == "run"]
    assert out["verdict"] is None and "could not be copied" in out["error"] and "nothing was validated" in out["error"]
    assert not e.rejected_report(T.TaskId("big")) and e.paused() is None
    assert _classify_no_verdict(e, T.TaskId("big"), out) == "no-verdict:never-ran"
    e.stop()


def test_where_places_stand_apart_a_root_judged_in_one_run_is_judged_in_a_copy(monkeypatch, place):
    """A lone run copies only a node's clone on this host; a root's base, where places stand apart, too — else it would
    find no copy and judge nothing (critic over this slice)."""
    base, _ = place
    ex = _Apart([], fail=())
    monkeypatch.setattr(TL, "execution_of", lambda *_: ex)
    monkeypatch.setenv("GFSO_VALIDATION_BATCH", "0")
    e = _eng()
    _task(e, 1)
    out = TL.validate_result(e, "big", workdir=str(base), _llm=_Timed(ex.log), _spawn=lambda: _Timed(ex.log))
    runs = [x for x in ex.log if x[0] == "run"]
    assert len(runs) == 1 and runs[0][1] != str(base) and runs[0][1].endswith("delivery")
    assert out["verdict"] == "PASS"
    e.stop()


def test_a_run_in_the_place_never_stands_beside_a_copy_being_taken(monkeypatch, place):
    """One copy failed, the other is being taken: a `make clean` in the place then would tear that copy."""
    _, at = place
    ex = _Copies([], fail=(1,))
    e, out = _timed(monkeypatch, at, ex)
    (copy,) = [x for x in ex.log if x[0] == "copy"]
    (alone,) = [x for x in ex.log if x[0] == "run" and x[1] == str(at)]
    assert not _overlap(copy, alone), ex.log
    assert out["verdict"] == "PASS"
    e.stop()


def test_the_runs_cap_is_read_once_its_copy_stands(monkeypatch, place):
    """What is left of T_validate when the run starts: read before the copy, the run outlives the visit by its time."""
    _, at = place
    order: dict = {}

    class _Ex(LocalExecution):
        def copy_tree(self, src, dst):
            order.setdefault(threading.get_ident(), []).append("copy")
            super().copy_tree(src, dst)
    real = TL._validation_cap
    monkeypatch.setattr(TL, "_validation_cap",
                        lambda t, g: order.setdefault(threading.get_ident(), []).append("cap") or real(t, g))
    monkeypatch.setattr(TL, "execution_of", lambda *_: _Ex())
    e, out, _ = _validate(monkeypatch, at)
    runs = [o for o in order.values() if "copy" in o]
    assert len(runs) == 2 and all(o[:2] == ["copy", "cap"] for o in runs), order
    e.stop()


def test_an_unreadable_comparison_costs_no_finished_report(monkeypatch, place):
    """What a run changed is informational: its reading failing is a log line, never a lost report."""
    _, at = place

    def _boom(*_):
        raise RuntimeError("git died")
    monkeypatch.setattr(S, "changed", _boom)
    e, out, _ = _validate(monkeypatch, at, edit=True)
    assert out["verdict"] == "PASS" and "validator_edits" not in out
    e.stop()
