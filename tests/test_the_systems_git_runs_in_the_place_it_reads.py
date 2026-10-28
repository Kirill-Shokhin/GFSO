"""The system's git over a repository an agent writes runs in THAT place's own container, so the config the agent
planted — a filter `.gitattributes` names, a fsmonitor, a driver — runs where the agent already works and reaches no
other place. In the project's container, which mounts every place, an agent's `core.fsmonitor` read and wrote the
others' at `git add -A` and forged a clone in the export (critics, three times); asking the config before use was a
race. Each scenario plants a filter that writes a mark into the places it must not reach, and the work still moves:
the delivery taken back into the base, a judge's copy compared, a child started from its parent's place, a part
joined into the base whose config the root's agent wrote. Live: containers of e3-linux-agent:2, named `gfso-sg3…`."""
import subprocess
import time

import pytest

import gfso.adapters.execution as E
import gfso.adapters.worktrees as W
from gfso.adapters.execution import ContainerExecution
from gfso.adapters.snapshots import snapshot
from tests.test_a_session_holds_only_its_own_place import IMAGE, _docker, _git

live = pytest.mark.skipif(not _docker(), reason=f"needs docker and {IMAGE}")


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "_SESSIONS", {})
    monkeypatch.setattr(E, "_SWITCH", {})
    (base := tmp_path / "work" / "ws").mkdir(parents=True)
    _git(base, "init", "-q")
    (base / "b.txt").write_text("base\n")
    _git(base, "add", "b.txt")
    _git(base, "commit", "-qm", "base")
    x = ContainerExecution(f"sg3-{time.time_ns()}", IMAGE, None, str(tmp_path / "state"), str(base), "p")
    try:
        for n in ("a", "b"):
            assert W.ensure(base, x.own / n, f"gfso/p/{n}", base, execution=x)
        yield x
    finally:
        x.stop()
        x.volume.remove()


def _sh(x, cwd, command: str) -> None:
    r = x.session(str(cwd)).run(["sh", "-c", command], cwd=str(cwd), timeout=120)
    assert r.returncode == 0, r.stderr


def _plant(x, repo, *targets) -> None:
    """In `repo`, by the agent working there: a filter over every file that passes it through and marks `targets`."""
    marks = " ".join(f'"{x.to_inside(str(t))}"' for t in targets)
    x.files.write_bytes(str(repo / ".git" / "evil.sh"),
                        f"#!/bin/sh\nfor d in {marks}; do echo pwned > \"$d/MARK\" 2>/dev/null; done\ncat\n".encode())
    _sh(x, repo, "git config filter.evil.clean 'sh .git/evil.sh' && git config filter.evil.smudge 'sh .git/evil.sh'"
                 " && mkdir -p .git/info && echo '* filter=evil' >> .git/info/attributes")


def _unmarked(x, *places) -> None:
    for p in places:
        assert not x.files.exists(str(p / "MARK")) and not (p / "MARK").exists(), f"the planted filter reached {p}"


@live
def test_live_a_delivery_and_a_judges_copy_run_their_agents_filter_in_their_own_place(project):
    x, base = project, project.base
    a, b = x.own / "a", x.own / "b"
    _plant(x, a, b, base)
    _sh(x, a, "echo w > w.txt")
    W.commit_all(base, a, "gfso: a delivery", "exec-a", execution=x, branch="gfso/p/a")
    _unmarked(x, b, base)
    shown = subprocess.run(["git", "show", "gfso/p/a:w.txt"], cwd=base, capture_output=True, text=True)
    assert shown.stdout == "w\n", "the delivery is taken back into the base, whole"
    x.files.mkdir(str(round_ := x.own / ".gfso-scratch-a" / "a_1"))
    edits = []
    with snapshot(a, round_ / "delivery", x, edits) as at:
        _sh(x, at, "echo judged > w.txt")
    assert edits == ["w.txt"]
    _unmarked(x, b, base)


@live
def test_live_a_child_starts_from_its_parents_place_and_a_part_joins_the_base_the_root_wrote(project):
    x, base = project, project.base
    a, b, c = x.own / "a", x.own / "b", x.own / "c"
    _plant(x, a, b, base)
    _sh(x, a, "echo parent > p.txt && git add p.txt && git -c user.name=a -c user.email=a@a commit -qm parent")
    assert W.ensure(base, c, "gfso/p/c", a, execution=x)
    assert x.files.read_bytes(str(c / "p.txt")) == b"parent\n", "the parent's commit, carried by bundle"
    _unmarked(x, b, base)
    W.commit_all(base, a, "gfso: a delivery", "exec-a", execution=x, branch="gfso/p/a")
    _plant(x, base, a, b, c)                                                         # …by the root's agent
    assert W.merge(base, base, "gfso/p/a", "gfso: a joins the base", execution=x) is None
    assert (base / "p.txt").read_text() == "parent\n"
    _unmarked(x, a, b, c)


@live
def test_live_a_bundle_past_its_cap_is_not_carried(project, monkeypatch):
    """The source's agent holds the temp a bundle passes through: a huge file in its place read whole would fill the
    server's memory (critic over 61bf915). Past the cap the carry fails, read no further."""
    x, a = project, project.own / "a"
    _sh(x, a, "echo parent > p.txt && git add p.txt && git -c user.name=a -c user.email=a@a commit -qm parent")
    monkeypatch.setattr(W, "BUNDLE_CAP", 16)
    with pytest.raises(OSError, match="not carried"):
        W.ensure(project.base, project.own / "c", "gfso/p/c", a, execution=x)
