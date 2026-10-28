"""A verdict is about the result as it stood at DELIVER (§11.3), and no judge's run reaches another's copy of it.

A judge's copy is taken from the place's live tree: a process its executor left running changed a tracked file after
DELIVER, and the judge saw a delivery that was never handed in (DELIVER f=broken, judged f=passing). The copy's tracked
files are held against the tree DELIVER recorded; a copy that is not it is no copy, and no validator starts on it.
A validation's batches ran in one container holding their whole round: a process one batch's validator left behind
rewrote another batch's copy. Each batch is a root of its own; its siblings are read-only to it.
Live: containers of e3-linux-agent:2, named `gfso-sg3…`."""
import threading
import time
from pathlib import Path

import pytest

import gfso.adapters.worktrees as W
from gfso import tools as T
from gfso import tools_llm as TL
from gfso.adapters.snapshots import NotTheDelivery, snapshot
from gfso.core.types import Signal, TaskId
from gfso.issuer import signal_ok
from tests.support import criterion
from tests.test_the_runs_of_a_validation_do_not_share_a_tree import _Run
from tests.test_the_systems_git_runs_in_the_place_it_reads import _sh, live, project  # noqa: F401 — the fixture
from tests.test_validate_result import _eng


class _Judge(_Run):
    """A validator that touches nothing: it says what it found in the file the delivery is about, and passes."""

    def __init__(self, x):
        super().__init__(threading.Barrier(1), [])
        self.x, self.filtered = x, None

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.calls.append({"duration_ms": 1, "input_tokens": 1, "output_tokens": 1})
        self.seen.append(self.x.files.read_bytes(str(Path(cwd) / "f")))
        # …its own git in its copy, as a validator's may run: no filter of the executor's runs under it
        self.x.session(cwd).run(["sh", "-c", "git add -A && git status && git diff --cached"], cwd=cwd, timeout=60)
        self.filtered = self.x.session(cwd).run(["test", "-e", "/tmp/filter-ran"], cwd=cwd, timeout=60).returncode == 0
        return self.answer(user, Path(cwd))


def _delivered(x, monkeypatch, flip: bool):
    """Node `big` delivered from place `a` with f=broken, its commit recorded — and, where `flip`, a process its
    executor left running rewriting f after DELIVER, as it stands when the judge comes. Then validated."""
    a = x.own / "a"
    # …and a filter its agent planted: every file passed through as it is, the container it runs in marked
    _sh(x, a, "printf '#!/bin/sh\\ntouch /tmp/filter-ran\\ncat\\n' > .git/f.sh && git config filter.m.clean 'sh .git/f.sh'"
              " && mkdir -p .git/info && echo '* filter=m' > .git/info/attributes && echo broken > f")
    tree = W.commit_all(x.base, a, "gfso: big delivery", "exec-a", execution=x, branch="gfso/p/a")
    if flip:
        _sh(x, a, "setsid sh -c 'sleep 1; echo passing > f' >/dev/null 2>&1 </dev/null &")
        for _ in range(60):
            if x.files.read_bytes(str(a / "f")) == b"passing\n":
                break
            time.sleep(0.5)
        assert x.files.read_bytes(str(a / "f")) == b"passing\n", "the leftover process rewrote the place"
    monkeypatch.setattr(TL, "execution_of", lambda *_: x)
    monkeypatch.setenv("GFSO_VALIDATION_BATCH", "0")
    e = _eng()
    T.create_task(e, "big", {"description": "f", "criteria": [
        criterion("one", check=[{"behaviour": "b", "command": "cat f", "expect": "passing"}])]}, "alice")
    T.signal(e, "big", "ACCEPT", "alice")
    assert signal_ok(e, TaskId("big"), Signal.DELIVER, "alice", result="f", artifact=tree, commit=W.head(a, execution=x))
    judge = _Judge(x)
    out = TL.validate_result(e, "big", workdir=str(a), _llm=judge, _spawn=lambda: judge)
    e.stop()
    return out, judge


@live
def test_live_a_place_changed_after_deliver_is_not_judged(project, monkeypatch):
    out, judge = _delivered(project, monkeypatch, flip=True)
    assert judge.seen == [], "no validator started on a copy that is not the delivery"
    assert out["verdict"] is None
    never = [c for c in judge.calls if c.get("ended") == "uncopied"]
    assert len(never) == 1 and "changed after DELIVER" in never[0]["error"] and "f" in never[0]["error"], never


@live
def test_live_a_place_as_delivered_is_judged(project, monkeypatch):
    out, judge = _delivered(project, monkeypatch, flip=False)
    assert judge.seen == [b"broken\n"] and out["verdict"] == "PASS"
    assert not judge.filtered, "the executor's filter ran in its judge's container while the copy was held to DELIVER"


@live
def test_live_a_batchs_leftover_process_cannot_reach_another_batchs_copy(project):
    x, a = project, project.own / "a"
    _sh(x, a, "echo delivered > f")
    round_ = x.own / ".gfso-scratch-a" / "a_1"
    x.files.mkdir(str(round_))
    one = Path(TL._own_place(str(round_), 0, x))
    two = Path(TL._own_place(str(round_), 1, x))
    inside = lambda p: x.to_inside(str(p))
    v1 = x.session(str(one))
    # batch 1's validator leaves a process behind that keeps writing where batch 2's copy will stand
    _sh(x, one, f"setsid sh -c 'while :; do echo forged > \"{inside(two)}/delivery/f\"; "
                f"mkdir -p \"{inside(round_)}/batch9\"; sleep 0.2; done' >/dev/null 2>&1 </dev/null &")
    tried = v1.run(["sh", "-c", f'echo x > "{inside(two)}/x"'], cwd=str(one), timeout=60)
    assert tried.returncode != 0 and "Read-only" in tried.stderr, tried.stderr
    with snapshot(a, two / "delivery", x) as at:
        time.sleep(2)
        assert x.files.read_bytes(str(Path(at) / "f")) == b"delivered\n", "batch 1's leftover rewrote batch 2's copy"
    assert not x.files.exists(str(round_ / "batch9")), "batch 1's leftover wrote its round"
    with pytest.raises(OSError, match="already stands"):
        TL._own_place(str(round_), 0, x)


_FILTER = "git config --file {d}/config filter.f.clean 'git cat-file blob HEAD:b.txt' && mkdir -p {d}/info && " \
          "printf 'b.txt filter=f\n' > {d}/info/attributes && printf 'changed\n' > b.txt"
#: …the redirected git kept where the delivered `.gitignore` hides it: else it is an untracked file of its own
_HIDDEN = "printf '.cd/\n.gd/\n' > .gitignore"
_COMMIT = "git -c user.name=a -c user.email=a@a commit -qm l"
#: (before DELIVER, after it, the cause it is refused for — None: judged) — in a base whose clones are made with filemode and symlinks off, as E3's
_CASES = {
    "a new script made executable": ("printf 'x\n' > run.sh && chmod +x run.sh", "", None),
    "a tracked file made executable": ("chmod +x b.txt", "", None),
    "a tracked link checked out as a file": (f"ln -s b.txt l.txt && git add l.txt && {_COMMIT} && rm l.txt && "
                                             "git checkout -- l.txt", "", None),
    "an ignored build left after": ("printf 'build/\n' > .gitignore", "mkdir -p build && echo x > build/x", None),
    "an untracked file added after": ("", "echo rigged > conftest.py", "changed after DELIVER"),
    "a .gitignore that hides itself added after": ("", "printf '.gitignore\nconftest.py\n' > .gitignore && "
                                                       "echo rigged > conftest.py", "changed after DELIVER"),
    "a tracked file deleted after": ("", "rm b.txt", "changed after DELIVER"),
    "a real pytest run before": ("mkdir -p tests && printf 'def test_a():\\n    assert 1\\n' > tests/test_a.py && "
                                 "(python3 -m pytest -q tests >/dev/null 2>&1 || true) && mkdir -p .pytest_cache && "
                                 "printf '*\\n' > .pytest_cache/.gitignore", "", None),
    "a ruff cache before": ("mkdir -p .ruff_cache && printf '*\\n' > .ruff_cache/.gitignore && echo x > .ruff_cache/d",
                            "", None),
    "a venv before": ("mkdir -p .venv/lib && printf '*\\n' > .venv/.gitignore && echo x > .venv/lib/y", "", None),
    "a .gitignore that hides itself made before": ("printf '.*\\n*.log\\n' > .gitignore && echo x > c.py", "", None),
    "a nested repository": ("mkdir dep && cd dep && git init -q && echo d > d.c && git add -A && " + _COMMIT, "",
                            "nested repositories (dep)"),
    "a submodule": ("mkdir /tmp/subsrc && cd /tmp/subsrc && git init -q && echo s > s.c && git add -A && " + _COMMIT
                    + " && cd - >/dev/null && git -c protocol.file.allow=always submodule add -q /tmp/subsrc sub",
                    "", "nested repositories (sub)"),
    "a commondir to a config with a filter hiding a change": (
        _HIDDEN, "mkdir -p .cd && cp -a .git/objects .git/refs .git/HEAD .cd/ && printf '../.cd\n' > .git/commondir && "
            + _FILTER.format(d=".cd"), "changed after DELIVER"),
    "a gitfile to a config with a filter hiding a change": (
        _HIDDEN, "cp -a .git .gd && rm -rf .git && printf 'gitdir: .gd\n' > .git && " + _FILTER.format(d=".gd"), "changed after DELIVER"),
}


@live
@pytest.mark.parametrize("case", list(_CASES))
def test_live_a_copy_is_held_to_its_delivery_as_deliver_took_it(project, case):
    before, after, cause = _CASES[case]
    x, a = project, project.own / "a"
    for repo in (x.base, a):
        _sh(x, repo, "git config core.filemode false && git config core.symlinks false")
    if before:
        _sh(x, a, before)
    tree = W.commit_all(x.base, a, "gfso: a delivery", "exec-a", execution=x, branch="gfso/p/a")
    commit = W.head(a, execution=x)
    if after:
        _sh(x, a, after)
    x.files.mkdir(str(round_ := x.own / ".gfso-scratch-a" / "a_1"))
    batch = Path(TL._own_place(str(round_), 0, x))
    try:
        with snapshot(a, batch / "delivery", x, delivered=(tree, commit)):
            refused = None
    except NotTheDelivery as e:
        refused = str(e)
    assert refused is None if cause is None else cause in str(refused), refused
