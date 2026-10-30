"""A verdict is about the result as it stood at DELIVER (§11.3), and no judge's run reaches another's copy of it.

A judge's copy was taken from the place's live tree: a process its executor left running changed a tracked file after
DELIVER, and the judge saw a delivery that was never handed in (DELIVER f=broken, judged f=passing); a file the
executor's `.gitignore` hid — a hidden `impl.py` that `main.py` imports, a binary c_compiler's 46 probes ran — rode into
the judge's instrument undelivered. The copy is now a checkout of the commit DELIVER recorded, and nothing else
(JOINT judge-on-the-delivered-tree); what the result needs built is built there, in the judge's container, before any
check: DELIVER's `build` when given ("" = nothing), else `make` where the tree has a Makefile at its root, else nothing.
A failed build is the delivery's FAIL with its output, and the executor's next packet says what ran.
A validation's batches ran in one container holding their whole round: a process one batch's validator left behind
rewrote another batch's copy. Each batch is a root of its own; its siblings are read-only to it.
Live: containers of e3-linux-agent:2, named `gfso-sg3…`."""
import hashlib
import re
import socket
import threading
import time
import tracemalloc
from pathlib import Path

import pytest

import gfso.adapters.snapshots as S
import gfso.issuer as I
import gfso.adapters.worktrees as W
from gfso.adapters import lfs
from gfso import packets as P
from gfso import tools as T
from gfso import tools_llm as TL
from gfso.adapters.execution import LocalExecution, scratch_of
from gfso.adapters.snapshots import BuildFailed, NotTheDelivery, Uncopied, changed, snapshot
from gfso.core.types import Signal, TaskId, hold_places
from gfso.issuer import signal_ok
from tests.support import criterion, make_engine
from tests.test_the_issuer_answers_a_dispute import _ContactLLM, _disputed
from tests.test_the_runs_of_a_validation_do_not_share_a_tree import _Run
from tests.test_the_systems_git_runs_in_the_place_it_reads import _sh, live, project  # noqa: F401 — the fixture
from tests.test_validate_result import _eng, _fenced
from gfso.delegate import _classify_no_verdict


class _Judge(_Run):
    """A validator that touches nothing: it says what it found in the file the delivery is about, and passes."""

    def __init__(self, x):
        super().__init__(threading.Barrier(1), [])
        self.x, self.filtered, self.had = x, None, []

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.calls.append({"duration_ms": 1, "input_tokens": 1, "output_tokens": 1})
        self.seen.append(self.x.files.read_bytes(str(Path(cwd) / "f")))
        self.had.append(sorted(self.x.files.listdir(cwd)))
        # …its own git in its copy, as a validator's may run: no filter of the executor's runs under it
        self.x.session(cwd).run(["sh", "-c", "git add -A && git status && git diff --cached"], cwd=cwd, timeout=60)
        self.filtered = self.x.session(cwd).run(["test", "-e", "/tmp/filter-ran"], cwd=cwd, timeout=60).returncode == 0
        return self.answer(user, Path(cwd))


def _delivered(x, monkeypatch, flip: bool, build=None, before: str = ""):
    """Node `big` delivered from place `a` with f=broken and an ignored `secret`, its commit recorded — and, where
    `flip`, a process its executor left running rewriting f and `secret` after DELIVER, as they stand when the judge
    comes. Then validated: (the answer, the judge, the engine)."""
    a = x.own / "a"
    # …and a filter its agent planted: every file passed through as it is, the container it runs in marked
    _sh(x, a, "printf '#!/bin/sh\\ntouch /tmp/filter-ran\\ncat\\n' > .git/f.sh && git config filter.m.clean 'sh .git/f.sh'"
              " && mkdir -p .git/info && echo '* filter=m' > .git/info/attributes && echo broken > f"
              " && echo secret > .gitignore && echo hidden > secret" + (f" && {before}" if before else ""))
    tree = W.commit_all(x.base, a, "gfso: big delivery", "exec-a", execution=x, branch="gfso/p/a")
    if flip:
        _sh(x, a, "setsid sh -c 'sleep 1; echo passing > f; echo forged > secret' >/dev/null 2>&1 </dev/null &")
        for _ in range(60):
            if x.files.read_bytes(str(a / "secret")) == b"forged\n":
                break
            time.sleep(0.5)
        assert x.files.read_bytes(str(a / "f")) == b"passing\n", "the leftover process rewrote the place"
    monkeypatch.setattr(TL, "execution_of", lambda *_: x)
    monkeypatch.setenv("GFSO_VALIDATION_BATCH", "0")
    e = _eng()
    T.create_task(e, "big", {"description": "f", "criteria": [
        criterion("one", check=[{"behaviour": "b", "command": "cat f", "expect": "passing"}])]}, "alice")
    T.signal(e, "big", "ACCEPT", "alice")
    assert signal_ok(e, TaskId("big"), Signal.DELIVER, "alice", result="f", artifact=tree, commit=W.head(a, execution=x),
                     build=build)
    judge = _Judge(x)
    out = TL.validate_result(e, "big", workdir=str(a), _llm=judge, _spawn=lambda: judge)
    return out, judge, e


@live
def test_live_a_place_changed_after_deliver_changes_nothing_judged(project, monkeypatch):
    """A leftover rewriting a tracked file and an ignored one after DELIVER: the judge sees the delivered f and no
    ignored file at all — what it judges is the recorded commit, whatever the place holds when it comes."""
    out, judge, e = _delivered(project, monkeypatch, flip=True)
    e.stop()
    assert judge.seen == [b"broken\n"], "the judge saw the place as the leftover left it, not as delivered"
    assert "secret" not in judge.had[0], judge.had
    assert out["verdict"] == "PASS"


@live
def test_live_a_place_as_delivered_is_judged(project, monkeypatch):
    out, judge, e = _delivered(project, monkeypatch, flip=False)
    e.stop()
    assert judge.seen == [b"broken\n"] and out["verdict"] == "PASS"
    assert not judge.filtered, "the executor's filter ran in its judge's container"


@live
def test_live_a_failing_build_is_the_deliverys_fail_and_its_executors_next_packet_says_it(project, monkeypatch):
    out, judge, e = _delivered(project, monkeypatch, flip=False, before="printf 'all:\\n\\techo no-compiler >&2; exit 7\\n' > Makefile")
    try:
        assert judge.seen == [], "no check ran over a delivery whose build failed"
        assert out["verdict"] == "FAIL" and out["failed_criteria"] == ["one"], out
        said = P._last_delivery_text(e, [e.graph.get_task(TaskId("big"))])
        assert "Makefile's default target" in said and "exited 2" in said and "no-compiler" in said, said
        # …and nothing stands on the node: the next delivery's own build is the re-check — a `make` kept as a finding
        # was demanded of a redelivery with no Makefile, a FAIL only an issuer lifted (critic over 909e417)
        assert e.regression_probes(TaskId("big")) == {}, e.regression_probes(TaskId("big"))
    finally:
        e.stop()


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
    assert tried.returncode != 0, "a batch reaches another's directory"
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
#: (before DELIVER, after it, the cause it is refused for — None: a checkout of exactly the recorded tree) — in a base
#: whose clones are made with filemode and symlinks off, as E3's. What the place holds after DELIVER no longer matters:
#: the copy is the recorded commit, read from objects hashed again (`snapshots._CHECKOUT`), so every change after
#: DELIVER — a file added, deleted or filtered, a git redirected — is judged as delivered, not refused
_CASES = {
    "a new script made executable": ("printf 'x\n' > run.sh && chmod +x run.sh", "", None),
    "a tracked file made executable": ("chmod +x b.txt", "", None),
    "a tracked link checked out as a file": (f"ln -s b.txt l.txt && git add l.txt && {_COMMIT} && rm l.txt && "
                                             "git checkout -- l.txt", "", None),
    "an ignored build left after": ("printf 'build/\n' > .gitignore", "mkdir -p build && echo x > build/x", None),
    "an untracked file added after": ("", "echo rigged > conftest.py", None),
    "a .gitignore that hides itself added after": ("", "printf '.gitignore\nconftest.py\n' > .gitignore && "
                                                       "echo rigged > conftest.py", None),
    "a tracked file deleted after": ("", "rm b.txt", None),
    "a delivered module named as the judge's own imports, then a change": (
        "printf 'import os\\nos._exit(0)\\n' > json.py && cp json.py shutil.py && cp json.py subprocess.py && "
        "cp json.py hashlib.py && cp json.py threading.py", "echo rigged > b.txt", None),
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
            + _FILTER.format(d=".cd"), None),
    "a gitfile to a config with a filter hiding a change": (
        _HIDDEN, "cp -a .git .gd && rm -rf .git && printf 'gitdir: .gd\n' > .git && " + _FILTER.format(d=".gd"), None),
}


@live
def test_live_an_object_of_the_delivery_rewritten_in_its_place_after_deliver_is_not_judged(project):
    """git reads an object by its id and does not hash it again: a loose object the executor rewrote after DELIVER
    would check out as a delivery nobody made. Committed without a branch, the object stands in the place alone (taken
    back into the base, a pack there would be read first)."""
    x, a = project, project.own / "a"
    _sh(x, a, "echo mine > m.txt")
    tree = W.commit_all(x.base, a, "gfso: a delivery", "exec-a", execution=x)
    commit = W.head(a, execution=x)
    _sh(x, a, "o=$(git rev-parse HEAD:m.txt) && n=$(printf forged | git hash-object --stdin -w) && "
              "f=.git/objects/$(echo $o | cut -c1-2)/$(echo $o | cut -c3-) && chmod u+w $f && "
              "cp .git/objects/$(echo $n | cut -c1-2)/$(echo $n | cut -c3-) $f && test \"$(git cat-file -p $o)\" = forged")
    x.files.mkdir(str(round_ := x.own / ".gfso-scratch-a" / "a_1"))
    # …refused where the pack is taken in (`index-pack` names each object by its content: the forged one is not the
    # delivery's, which is then missing), and where an object is hashed again before the checkout
    with pytest.raises(NotTheDelivery, match="is missing|does not hold what its id names"):
        with snapshot(a, Path(TL._own_place(str(round_), 0, x)) / "delivery", x, delivered=(tree, commit, "")):
            pass


@live
@pytest.mark.parametrize("case", list(_CASES))
def test_live_a_copy_is_the_recorded_tree_whatever_the_place_holds(project, case):
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
        with snapshot(a, batch / "delivery", x, delivered=(tree, commit, "")) as at:
            refused, differs = None, changed(a, at, x, commit)
            linked = x.session(at).run(["test", "-L", "l.txt"], cwd=at, timeout=60).returncode == 0
    except NotTheDelivery as e:
        refused = str(e)
    assert refused is None if cause is None else cause in str(refused), refused
    if cause is None:
        assert differs == [], f"the copy is not the recorded tree: {differs}"
        assert linked == ("link" in case), "a delivered link is a link in the judge's copy"


def _copy(x, before: str, build, after="") -> tuple:
    """Place `a` delivered after `before` — its Makefile's product ignored and left stale there — then `after` (a
    command in the place, or a call); the
    judge's copy built under the declared `build`: (its files, {name: content}, what ran)."""
    a = x.own / "a"
    _sh(x, a, "printf 'app.bin\\n' > .gitignore && echo stale > app.bin" + (f" && {before}" if before else ""))
    tree = W.commit_all(x.base, a, "gfso: a delivery", "exec-a", execution=x, branch="gfso/p/a")
    commit = W.head(a, execution=x)
    if callable(after):
        after()
    elif after:
        _sh(x, a, after)
    x.files.mkdir(str(round_ := x.own / ".gfso-scratch-a" / "a_1"))
    batch, built = Path(TL._own_place(str(round_), 0, x)), []
    with snapshot(a, batch / "delivery", x, delivered=(tree, commit, build), built=built) as at:
        names = sorted(x.files.listdir(at))
        return names, {n: x.files.read_bytes(str(Path(at) / n)) for n in names if n != ".git"}, built


_MAKEFILE = "printf 'app.bin:\\n\\tprintf fresh > app.bin\\n' > Makefile"


@live
def test_live_a_hidden_file_the_delivery_imports_is_not_in_the_judges_copy(project):
    names, files, _ = _copy(project, "printf 'import impl\\n' > main.py && printf 'impl.py\\n' >> .gitignore && "
                                     "printf 'ok = 1\\n' > impl.py", "")
    assert "main.py" in names and "impl.py" not in names and "app.bin" not in names, names


@live
def test_live_no_cache_of_the_places_reaches_the_judges_copy(project):
    """`DELIVERED` leaves caches out of a delivery, and a copy of the place carried them in with their times: a forged
    `__pycache__/mod.cpython-311.pyc` whose header matched the source's size and mtime made `mod.f()` answer what the
    delivered source does not (measured: 41 against `return 99`). A checkout of the commit holds none of them."""
    names, files, _ = _copy(project, "printf 'def f():\\n    return 99\\n' > mod.py && mkdir -p __pycache__ && "
                                     "echo forged > __pycache__/mod.cpython-311.pyc && echo forged > main.o", "")
    assert "mod.py" in names and "__pycache__" not in names and "main.o" not in names, names


@live
def test_live_no_rule_read_from_the_base_at_judging_time_changes_the_copy(project):
    """The base's `info/exclude` and `info/attributes` are writable by the sessions working in the base: written after
    DELIVER, read when a judge's copy is made, they could hide a planted file or rewrite a delivered one. The copy is
    the recorded tree under a git of its own: no rule of the base's is read."""
    x = project
    info = x.base / ".git" / "info"
    names, files, _ = _copy(x, "", "", after=lambda: (
        x.files.write_bytes(str(info / "attributes"), b"* text eol=crlf\n"),
        x.files.write_bytes(str(info / "exclude"), b"*\n")))
    assert files["b.txt"] == b"base\n", files["b.txt"]


@live
def test_live_a_makefile_tree_is_built_by_default_and_its_product_is_there_for_the_checks(project):
    names, files, built = _copy(project, _MAKEFILE, None)
    assert files["app.bin"] == b"fresh", "the judge built the delivered tree, not the executor's stale product"
    assert "Makefile's default target" in built[0], built


@live
def test_live_a_declared_build_wins_over_the_makefile(project):
    names, files, built = _copy(project, _MAKEFILE, "printf declared > out.txt")
    assert files.get("out.txt") == b"declared" and "app.bin" not in names, names
    assert "declared at DELIVER (`printf declared > out.txt`)" in built[0], built


@live
def test_live_an_empty_build_builds_nothing(project):
    names, files, built = _copy(project, _MAKEFILE, "")
    assert "app.bin" not in names and built[0].startswith("nothing: DELIVER declared nothing"), (names, built)


@live
def test_live_a_failing_build_raises_with_its_output(project):
    with pytest.raises(BuildFailed, match=r"exited 3[\s\S]*broke-here") as e:
        _copy(project, "", "echo broke-here; exit 3")
    assert e.value.command == "echo broke-here; exit 3"


@live
def test_live_the_build_runs_in_the_judges_container(project):
    x = project
    _, files, _ = _copy(x, "", "hostname > built-on")
    batch = x.own / ".gfso-scratch-a" / "a_1" / "batch1"
    # …a container of the judge's batch: not the host's, not the project's — and ended with the build, so the run that
    # follows has a fresh one (`release`)
    judge = x.session(str(batch)).run(["hostname"], cwd=str(batch), timeout=60).stdout.strip()
    on = files["built-on"].decode().strip()
    assert on not in (socket.gethostname(), x.run(["hostname"], cwd=str(x.own), timeout=60).stdout.strip()), on
    assert on != judge, "the build's container still stood after it"


#: a build that reads what a delivered link names, and says when it reaches nothing
_READ = "cat {} > seen 2>/dev/null || echo unreachable > seen"


def _judged(x, place, at, tree, commit, build) -> bytes:
    """What the build `build` left in `seen`, in the judge's copy of `place`'s delivery made at `at`."""
    with snapshot(place, at, x, delivered=(tree, commit, build)) as copy:
        return x.files.read_bytes(str(Path(copy) / "seen"))


@live
def test_live_a_delivered_link_into_the_nodes_temp_reads_nothing_written_there_after_deliver(project):
    """The node's temp was mounted writable in its executor's container and in its judge's: a delivered link into it
    read what the executor wrote there after DELIVER. A judge's temp is its own."""
    x, a = project, project.own / "a"
    t = Path(x.temp_of(str(a)))
    x.files.write_bytes(str(t / "impl"), b"delivered\n")
    _sh(x, a, f"ln -s {x.to_inside(str(t / 'impl'))} impl.txt")
    tree, commit = W.commit_all(x.base, a, "gfso: a delivery", "exec-a", execution=x), W.head(a, execution=x)
    x.files.write_bytes(str(t / "impl"), b"forged\n")
    x.files.mkdir(str(round_ := x.own / ".gfso-scratch-a" / "a_1"))
    batch = Path(TL._own_place(str(round_), 0, x))
    assert _judged(x, a, batch / "delivery", tree, commit, _READ.format("impl.txt")) == b"unreachable\n"


@live
def test_live_a_roots_judge_reads_nothing_of_the_base_as_it_stands_now(project):
    """A root's place is the base, mounted read-only in its judge's container and in the container of the system's
    exact checks: a delivered absolute link read the base's ignored file as the executor had changed it since."""
    x, base = project, project.base
    _sh(x, base, f"printf 'secret\\n' > .gitignore && echo delivered > secret && "
                 f"ln -s {x.to_inside(str(base / 'secret'))} link.txt")
    tree, commit = W.commit_all(base, base, "gfso: root", "exec-root", execution=x), W.head(base, execution=x)
    _sh(x, base, "echo forged > secret")
    x.files.mkdir(str(round_ := scratch_of(base, "p") / "root_1"))
    batch = Path(TL._own_place(str(round_), 0, x))
    assert _judged(x, base, batch / "delivery", tree, commit, _READ.format("link.txt")) == b"unreachable\n"
    with x.scratch("gfso-exact-", system=True) as tmp:            # …the system's own run of the exact checks
        x.files.mkdir(str(Path(tmp) / "exact"))
        assert _judged(x, base, Path(tmp) / "exact" / "delivery", tree, commit,
                       _READ.format("link.txt")) == b"unreachable\n"


@live
def test_live_a_batchs_build_reads_nothing_of_a_sibling_batch(project):
    """A round was mounted read-only beneath each batch, and every batch's copy of the whole place (`delivery.place`,
    ignored files included) with it: batch 1's build read batch 2's secret."""
    x, a = project, project.own / "a"
    _sh(x, a, "echo delivered > f")
    tree, commit = W.commit_all(x.base, a, "gfso: a delivery", "exec-a", execution=x), W.head(a, execution=x)
    x.files.mkdir(str(round_ := x.own / ".gfso-scratch-a" / "a_1"))
    one, two = (Path(TL._own_place(str(round_), i, x)) for i in (0, 1))
    x.files.write_bytes(str(two / "delivery.place" / "secret"), b"sibling\n")
    assert _judged(x, a, one / "delivery", tree, commit,
                   _READ.format(x.to_inside(str(two / "delivery.place" / "secret")))) == b"unreachable\n"


@live
def test_live_an_object_rewritten_once_the_delivery_is_taken_in_is_never_read(project, monkeypatch):
    """Objects were hashed through the stores they lay in, then checked out through them again: an executor's process
    swapping one between the two made the judge see what was never delivered. The commit's objects are streamed from
    the executor's store once, into the copy, and everything after reads the copy. The window: right after that read."""
    x, a = project, project.own / "a"
    _sh(x, a, "echo mine > m.txt")
    tree, commit = W.commit_all(x.base, a, "gfso: a delivery", "exec-a", execution=x), W.head(a, execution=x)
    pointed = W.pointed

    def _then_forged(repo, revs, execution):
        _sh(x, a, "o=$(git rev-parse HEAD:m.txt) && n=$(printf forged | git hash-object --stdin -w) && "
                  "f=.git/objects/$(echo $o | cut -c1-2)/$(echo $o | cut -c3-) && chmod u+w $f && "
                  "cp .git/objects/$(echo $n | cut -c1-2)/$(echo $n | cut -c3-) $f")
        return pointed(repo, revs, execution)
    monkeypatch.setattr(W, "pointed", _then_forged)
    x.files.mkdir(str(round_ := x.own / ".gfso-scratch-a" / "a_1"))
    with snapshot(a, Path(TL._own_place(str(round_), 0, x)) / "delivery", x, delivered=(tree, commit, "")) as at:
        assert x.files.read_bytes(str(Path(at) / "m.txt")) == b"mine\n"


@live
def test_live_an_object_the_deliverys_own_store_lost_is_the_deliverys_not_the_machines(project):
    """A blob of the recorded tree deleted from the place after DELIVER failed the pack and was booked as never copied —
    asked again until a person stepped in (critic over the judged tree, run). The delivery's own store is its own."""
    x, a = project, project.own / "a"
    _sh(x, a, "echo mine > m.txt")
    tree, commit = W.commit_all(x.base, a, "gfso: a delivery", "exec-a", execution=x), W.head(a, execution=x)
    _sh(x, a, "o=$(git rev-parse HEAD:m.txt) && rm -f .git/objects/$(echo $o | cut -c1-2)/$(echo $o | cut -c3-)")
    x.files.mkdir(str(round_ := x.own / ".gfso-scratch-a" / "a_1"))
    with pytest.raises(NotTheDelivery, match="cannot give back"):
        with snapshot(a, Path(TL._own_place(str(round_), 0, x)) / "delivery", x, delivered=(tree, commit, "")):
            pass


@live
@pytest.mark.parametrize("question", ["dispute", "escalation"])
def test_live_an_issuer_rules_on_the_recorded_tree_of_a_place_its_rework_changed_since(project, monkeypatch, question):
    """Series 2 REF 2 froze 2 h 26 min with no model call: the rework session had edited tracked files before it
    challenged, the issuer's copy was held against the recorded tree and refused ("the place changed after DELIVER: 4
    tracked file(s) differ"), and the contact was retried ×7 with doubling waits. The issuer's copy is the judges'
    checkout of the recorded commit: what the place holds now does not matter, and the ruling is made — whatever it
    asks: a contact on a question other than a dispute copied the live place (critic over the judged tree)."""
    x, a = project, project.own / "a"
    _sh(x, a, "echo delivered > f")
    tree, commit = W.commit_all(x.base, a, "gfso: a delivery", "exec-a", execution=x), W.head(a, execution=x)
    _sh(x, a, "echo reworked > f && echo new > g")                     # …the rework session's edits, uncommitted
    seen = []

    class _Reads(_ContactLLM):
        def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
            seen.append((x.files.read_bytes(str(Path(cwd) / "f")), x.files.exists(str(Path(cwd) / "g"))))
            return super().run_agent(system, user, allowed_tools, cwd, timeout)
    monkeypatch.setattr(I, "_execution", lambda *_: x)
    e = make_engine()
    e.start()
    try:
        _disputed(e)
        monkeypatch.setattr(e, "delivered", lambda *ids: (tree, commit, ""))
        llm = _Reads({"decision": "reject", "justification": "ran it: c holds on the delivered tree"}, ran={"Bash": 1})
        if question == "dispute":
            out = I.answer_the_challenge(e, TaskId("leaf"), "worker", _llm=llm, where=str(a))
            assert out["status"] == "rejected", out
        else:
            I._ask(e, TaskId("leaf"), question, "worker", I.MOVE_SCHEMA, "", None, llm, str(a))
        e.wait_idle()
        assert seen == [(b"delivered\n", False)], seen
    finally:
        e.stop()


def test_a_checkout_that_cannot_be_made_is_refused_never_the_live_place(tmp_path, monkeypatch):
    """Where the checkout failed for any cause but the two it names, the copy fell back to the place itself — the live
    tree, everything the executor left in it — on a host that runs its judges there."""
    place = tmp_path / "work" / ".gfso-nodes-ws" / "p" / "a"
    place.mkdir(parents=True)

    def _no_pack(*_):
        raise OSError("no pack")
    monkeypatch.setattr(S, "_checkout", _no_pack)
    with pytest.raises(Uncopied, match="no checkout of the delivery c0ffee"):
        with snapshot(place, tmp_path / "round" / "delivery", LocalExecution(), delivered=("t", "c0ffee", "")) as at:
            pytest.fail(f"a run was handed {at}")


#: a REGRESSION line as the packet writes it: its id and the command to run
_REGRESSION = re.compile(r"REGRESSION \[([^\]]+)\][^`]*run `([^`]+)`")


class _Refuter(_Judge):
    """Round 1: writes `probe.sh` beside its copy — in its own batch, as validators do —, leaves a process behind that
    keeps writing in its batch, and FAILs `one` over the probe: a finding naming that file. Round 2: tries to read
    round 1's probe directly, then runs each REGRESSION line of its packet as written, in its own container, and says
    what it printed."""

    def __init__(self, x):
        super().__init__(x)
        self.rounds, self.reran, self.first, self.earlier = 0, [], None, None

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.calls.append({"duration_ms": 1, "input_tokens": 1, "output_tokens": 1})
        self.rounds += 1
        here, sh = Path(cwd), lambda c: self.x.session(cwd).run(["bash", "-c", c], cwd=cwd, timeout=120)
        if self.rounds == 1:
            self.x.files.write_bytes(str(here.parent / "probe.sh"), b"echo refuted\nexit 1\n")
            sh("setsid sh -c 'while :; do date +%s%N >> ../alive; sleep 0.2; done' >/dev/null 2>&1 </dev/null &")
            self.first = (here.parent / "probe.sh").as_posix()
            probe = f"sh {self.first}"
            return _fenced({"verdict": "FAIL", "failed_criteria": ["one"], "per_criterion": [
                {"criterion": "one", "verdict": "fail", "evidence": "the probe printed refuted", "behaviours": ["b"],
                 "probe": [{"id": "p1", "behaviour": "b", "command": probe, "expect": "held"}]}]})
        self.earlier = sh(f"cat {self.first}").returncode
        for fid, cmd in _REGRESSION.findall(user):
            r = sh(cmd)
            self.reran.append((fid, r.stdout.strip(), r.returncode, cmd, r.stderr))
        return _fenced({"verdict": "FAIL", "failed_criteria": ["one"], "per_criterion": [
            {"criterion": "one", "verdict": "fail", "evidence": "re-ran", "behaviours": ["b"],
             "probe": [{"id": fid, "behaviour": "b", "command": "re-ran", "expect": "held"} for fid, *_ in self.reran]}]})


#: a delivered Makefile whose default build, in round 2, rewrites every probe file it can reach: what was laid
#: read-only beside its batch, the round before it, and what a re-run makes afresh in its batch, made in advance
_FORGER = (b"all:\n\tfor f in ../../batch1.laid/*/batch1/probe.sh ../../../*/batch1/probe.sh "
           b"../regression/*/batch1/probe.sh; do "
           b"printf 'echo held\\nexit 0\\n' > $$f 2>/dev/null; done; for d in ../../batch1.laid/*; do "
           b"mkdir -p ../regression/$${d##*/}/batch1 && "
           b"printf 'echo held\\nexit 0\\n' > ../regression/$${d##*/}/batch1/probe.sh; done; true\n")


@live
def test_live_a_standing_finding_reruns_the_probe_it_was_filed_over_and_its_rounds_processes_end(project, monkeypatch):
    """A batch's container outlived its run, and the next round mounted the earlier ones read-only to re-run the probes
    a standing finding names: the delivered code run there (a `make`, a test, a process either left) rewrote
    `../probe.sh`, and the next round re-ran the forged one (critic over the judged tree: rc 0). The system keeps each
    probe file's content as the finding is filed; a re-run lays it from that record, read-only, into the judge's own
    batch, and a judge mounts no earlier round. A batch's container ends with its run, its leftovers with it."""
    x, a = project, project.own / "a"
    _sh(x, a, "echo delivered > f")
    x.files.write_bytes(str(a / "Makefile"), _FORGER)
    tree = W.commit_all(x.base, a, "gfso: big delivery", "exec-a", execution=x, branch="gfso/p/a")
    monkeypatch.setattr(TL, "execution_of", lambda *_: x)
    monkeypatch.setattr(P, "execution_of", lambda *_: x)
    monkeypatch.setenv("GFSO_VALIDATION_BATCH", "0")
    e = _eng()
    hold_places(x.files)                       # …as a project's execution holds its places: a round is read through it
    try:
        T.create_task(e, "big", {"description": "f", "criteria": [
            criterion("one", check=[{"behaviour": "b", "command": "cat f", "expect": "delivered"}])]}, "alice")
        T.signal(e, "big", "ACCEPT", "alice")
        judge = _Refuter(x)
        deliver = lambda: signal_ok(e, TaskId("big"), Signal.DELIVER, "alice", result="f", artifact=tree,
                                    commit=W.head(a, execution=x))
        assert deliver()
        assert TL.validate_result(e, "big", workdir=str(a), _llm=judge, _spawn=lambda: judge)["verdict"] == "FAIL"
        (first,) = [r for r in x.files.listdir(str(scratch_of(a, "p"))) if not r.endswith(".laid")]
        batch = scratch_of(a, "p") / first / "batch1"
        alive = x.files.read_bytes(str(batch / "alive"))
        time.sleep(1.5)
        assert x.files.read_bytes(str(batch / "alive")) == alive, "round 1's leftover process outlived its run"
        x.files.write_bytes(str(batch / "probe.sh"), b"echo held\nexit 0\n")    # …rewritten after its finding was filed
        T.signal(e, "big", "FAIL", "alice", failed_criteria=["one"])
        assert deliver(), e.graph.get_task(TaskId("big")).state
        TL.validate_result(e, "big", workdir=str(a), _llm=judge, _spawn=lambda: judge)
        assert judge.rounds == 2 and judge.reran, "round 2 was handed the standing finding to re-run"
        assert [(out, rc) for _, out, rc, *_ in judge.reran] == [("refuted", 1)], judge.reran
        assert judge.earlier != 0, "round 2's judge reads round 1's directory"
    finally:
        hold_places(x.files, False)
        e.stop()


def _lfs_delivery(x, content: bytes) -> tuple:
    """Place `a` delivering `big.bin` through Git LFS — committed as its pointer by the system's filter, its content
    kept in the place's own store: (tree, commit, the object's id)."""
    a = x.own / "a"
    _sh(x, a, "printf '*.bin filter=lfs diff=lfs merge=lfs -text\\n' > .gitattributes")
    x.files.write_bytes(str(a / "big.bin"), content)
    tree = W.commit_all(x.base, a, "gfso: an lfs delivery", "exec-a", execution=x, branch="gfso/p/a")
    blob = x.session(str(a)).run(["git", *W.APART, "cat-file", "blob", "HEAD:big.bin"], cwd=str(a), timeout=60).stdout
    assert lfs.parse(blob.encode()) == (hashlib.sha256(content).hexdigest(), len(content)), "committed as a pointer"
    return tree, W.head(a, execution=x), hashlib.sha256(content).hexdigest()


@live
def test_live_an_lfs_file_reads_as_its_content_in_the_judges_copy_and_a_forged_object_never(project):
    """The judge's copy was a fresh repository holding the delivered tree's LFS pointers only: every check reading an
    LFS file read a pointer and failed falsely. The objects its pointers name are carried into the copy's own store,
    each kept only where its size and sha256 are the pointer's, and checked out under the system's filter."""
    x, a = project, project.own / "a"
    content = b"\x00lfs content\r\n" * 4096
    tree, commit, oid = _lfs_delivery(x, content)
    x.files.mkdir(str(round_ := x.own / ".gfso-scratch-a" / "a_1"))
    with snapshot(a, Path(TL._own_place(str(round_), 0, x)) / "delivery", x, delivered=(tree, commit, "")) as at:
        assert x.files.read_bytes(str(Path(at) / "big.bin")) == content, "the judge read a pointer"
    for store in (a, x.base):          # …forged at its pointer's size in every store the place reads
        x.files.write_bytes(lfs.path_in(str(store / ".git" / "lfs" / "objects"), oid), b"F" * len(content))
    with snapshot(a, Path(TL._own_place(str(round_), 1, x)) / "delivery", x, delivered=(tree, commit, "")) as at:
        got = x.files.read_bytes(str(Path(at) / "big.bin"))
    assert lfs.parse(got) == (oid, len(content)), "a forged object read as the delivery's content"


@live
@pytest.mark.parametrize("gone", ["rm -rf .git/lfs/objects",
                                  "rm -rf .git/lfs/objects && echo x > .git/lfs/objects",
                                  "rm -rf .git/lfs/objects && e=$(git commit-tree $(git mktree </dev/null) -m x) && "
                                  "git update-ref refs/replace/$(git rev-parse HEAD) $e"])
def test_live_a_build_that_takes_the_copys_lfs_objects_fails_rather_than_leave_their_pointers(project, gone):
    """A delivered build that took the copy's LFS objects and changed an LFS file had the file put back as its POINTER,
    and every check read the pointer (critics over the bounds: removed, the store made a file, a replace ref hiding the
    pointers). Which files the checkout wrote as content is read before any build runs; one whose object is gone after
    it is the delivery breaking its judge's copy — its FAIL, never a pointer judged as the delivery."""
    x, a = project, project.own / "a"
    tree, commit, _ = _lfs_delivery(x, b"\x00lfs content\r\n" * 4096)
    x.files.mkdir(str(round_ := x.own / ".gfso-scratch-a" / "a_1"))
    with pytest.raises(BuildFailed, match="removed the Git LFS object of big.bin"):
        with snapshot(a, Path(TL._own_place(str(round_), 0, x)) / "delivery", x,
                      delivered=(tree, commit, f"{gone} && printf changed > big.bin")):
            pass


@live
def test_live_a_build_that_cleans_the_lfs_store_but_leaves_the_files_is_judged_on_them(project):
    """A build that cleans the copy's LFS store (`git lfs prune`, `rm -rf .git/lfs`) and leaves its files as the
    checkout wrote them took nothing the checks read: judged on the content (critic over the LFS check — failed)."""
    x, a = project, project.own / "a"
    content = b"\x00lfs content\r\n" * 4096
    tree, commit, _ = _lfs_delivery(x, content)
    x.files.mkdir(str(round_ := x.own / ".gfso-scratch-a" / "a_1"))
    with snapshot(a, Path(TL._own_place(str(round_), 0, x)) / "delivery", x,
                  delivered=(tree, commit, "rm -rf .git/lfs")) as at:
        assert x.files.read_bytes(str(Path(at) / "big.bin")) == content


@live
@pytest.mark.parametrize("build", ["", "rm -rf .git/lfs"])
def test_live_a_pointer_shaped_file_outside_the_lfs_filter_stays_its_text(project, build):
    """A file that holds an LFS pointer's text but no LFS attribute (a fixture) is checked out as its text: read as
    smudged by its blob alone, it was overwritten with the object's content, or failed once the store was cleaned
    (critic over the LFS check). Which files were smudged is what the checkout wrote, path by path."""
    x, a = project, project.own / "a"
    content = b"\x00lfs content\r\n" * 4096
    _lfs_delivery(x, content)
    pointer = x.session(str(a)).run(["git", *W.APART, "cat-file", "blob", "HEAD:big.bin"], cwd=str(a), timeout=60).stdout
    x.files.write_bytes(str(a / "fixture.txt"), pointer.encode())
    tree = W.commit_all(x.base, a, "gfso: a fixture", "exec-a", execution=x, branch="gfso/p/a")
    x.files.mkdir(str(round_ := x.own / ".gfso-scratch-a" / "a_1"))
    with snapshot(a, Path(TL._own_place(str(round_), 0, x)) / "delivery", x,
                  delivered=(tree, W.head(a, execution=x), build)) as at:
        assert x.files.read_bytes(str(Path(at) / "fixture.txt")) == pointer.encode()
        assert x.files.read_bytes(str(Path(at) / "big.bin")) == content


@live
def test_live_a_build_that_writes_an_lfs_files_pointer_back_has_its_content_put_back(project):
    """The pointer is the blob a smudged LFS file is committed as: written back by the build it matched the tree, was
    kept, and the checks read it (critic over the LFS check). A file its checkout wrote as content is put back as it."""
    x, a = project, project.own / "a"
    content = b"\x00lfs content\r\n" * 4096
    tree, commit, _ = _lfs_delivery(x, content)
    x.files.mkdir(str(round_ := x.own / ".gfso-scratch-a" / "a_1"))
    with snapshot(a, Path(TL._own_place(str(round_), 0, x)) / "delivery", x,
                  delivered=(tree, commit, "git cat-file blob HEAD:big.bin > big.bin")) as at:
        assert x.files.read_bytes(str(Path(at) / "big.bin")) == content, "the checks read the pointer"


@live
def test_live_a_delivery_past_the_old_cap_is_judged_and_never_held_in_the_servers_memory(project, monkeypatch):
    """`_packed` read the whole pack into the server's memory, capped at 512 MiB, and above it the delivery was never
    judged. The pack streams from the place's container into the copy's: with the cap lowered to 1 MiB, a 48 MiB
    incompressible delivery is judged, and the server's own allocations stay far below its size."""
    x, a = project, project.own / "a"
    _sh(x, a, "head -c 48M /dev/urandom > big.dat && sha256sum big.dat | cut -d' ' -f1 > big.sum")
    tree = W.commit_all(x.base, a, "gfso: a large delivery", "exec-a", execution=x, branch="gfso/p/a")
    commit, want = W.head(a, execution=x), x.files.read_bytes(str(a / "big.sum"))
    monkeypatch.setattr(W, "BUNDLE_CAP", 1 << 20)
    x.files.mkdir(str(round_ := x.own / ".gfso-scratch-a" / "a_1"))
    batch = Path(TL._own_place(str(round_), 0, x))
    tracemalloc.start()
    try:
        with snapshot(a, batch / "delivery", x, delivered=(tree, commit, "")) as at:
            peak = tracemalloc.get_traced_memory()[1]
            got = x.session(at).run(["sh", "-c", "sha256sum big.dat | cut -d' ' -f1"], cwd=at, timeout=120).stdout
    finally:
        tracemalloc.stop()
    assert got.encode() == want, "the judge's copy is not the delivery"
    assert peak < 8 << 20, f"the server held {peak >> 20} MiB of a 48 MiB delivery"


@live
def test_live_a_delivery_no_copy_can_be_made_of_fails_and_its_executors_next_packet_says_why(project, monkeypatch):
    """A delivery no judge's copy could be made of was booked as a validator that never started: asked again, and
    again, with no verdict and no cause in the executor's packet. It is the delivery's FAIL, the cause said."""
    def _refused(*_):
        raise NotTheDelivery("the tree DELIVER recorded cannot be read back as recorded: its object x is missing")
    monkeypatch.setattr(S, "_checkout", _refused)
    out, judge, e = _delivered(project, monkeypatch, flip=False)
    try:
        assert judge.seen == [] and out.get("verdict") == "FAIL" and out["failed_criteria"] == ["one"], out.get("verdict_defects")
        said = P._last_delivery_text(e, [e.graph.get_task(TaskId("big"))])
        assert "FAILED unjudged" in said and "object x is missing" in said, said
        assert e.regression_probes(TaskId("big")) == {}, "the system's own copy left a finding standing"
    finally:
        e.stop()


@live
def test_live_a_copy_failing_for_a_cause_not_the_deliverys_is_no_verdict(project, monkeypatch):
    """Every failure of making the copy had become the delivery's FAIL — a Docker error, a pack outrunning its time, a
    full disk. A FAIL is a verdict on the delivery: only what the delivery causes is one; the rest is asked again."""
    def _docker_down(*_):
        raise OSError("docker exec: the daemon did not answer")
    monkeypatch.setattr(S, "_checkout", _docker_down)
    out, judge, e = _delivered(project, monkeypatch, flip=False)
    try:
        assert judge.seen == [] and out.get("verdict") is None, out
        assert "could not be copied" in out["error"] and not e.rejected_report(TaskId("big")), out
        assert _classify_no_verdict(e, TaskId("big"), out) == "no-verdict:never-ran", "asked again, not a FAIL"
    finally:
        e.stop()


#: a build that "succeeds" and leaves a process rewriting a delivered source after it, and one that regenerates a
#: tracked file differently — both delivered files the checks must see as delivered
_LEFT_BEHIND = (b"all:\n\tsetsid sh -c 'sleep 2; printf clean > main.c' >/dev/null 2>&1 </dev/null &\n"
                b"\tprintf generated-now > gen.c\n")


@live
def test_live_a_builds_processes_end_with_it_and_its_changes_to_delivered_files_are_put_back(project):
    """The build left a process behind: `_build` said it succeeded, and 4 s later the copy's `main.c` read `clean` — a
    check would pass a tree never delivered (critic over 909e417). Its processes end with it, and a delivered file it
    changed is put back as delivered; what it adds beside them stays."""
    x, a = project, project.own / "a"
    _sh(x, a, "echo 'int main(void){return 1;}' > main.c && echo delivered > gen.c")
    x.files.write_bytes(str(a / "Makefile"), _LEFT_BEHIND)
    tree, commit = W.commit_all(x.base, a, "gfso: a delivery", "exec-a", execution=x), W.head(a, execution=x)
    x.files.mkdir(str(round_ := x.own / ".gfso-scratch-a" / "a_1"))
    built: list = []
    with snapshot(a, Path(TL._own_place(str(round_), 0, x)) / "delivery", x, delivered=(tree, commit, None),
                  built=built) as at:
        time.sleep(4)
        assert x.files.read_bytes(str(Path(at) / "main.c")) == b"int main(void){return 1;}\n", "the build's leftover"
        assert x.files.read_bytes(str(Path(at) / "gen.c")) == b"delivered\n", "a delivered file the build rewrote"
    assert "put back as delivered" in built[0] and "gen.c" in built[0], built


@live
def test_live_an_issuer_rules_on_a_delivery_no_copy_can_be_made_of(project, monkeypatch):
    """A delivery its own doing left uncopyable sent its issuer's contact to `Unavailable`, retried forever. The
    issuer is told why and rules on that."""
    def _refused(*_):
        raise NotTheDelivery("the delivery holds nested repositories (dep)")
    monkeypatch.setattr(S, "_checkout", _refused)
    monkeypatch.setattr(I, "_execution", lambda *_: project)
    e = make_engine()
    e.start()
    try:
        _disputed(e)
        monkeypatch.setattr(e, "delivered", lambda *ids: ("t" * 40, "c" * 40, ""))
        llm = _ContactLLM({"decision": "accept", "justification": "no copy: nested repositories"}, ran={})
        answer, _ = I._ask(e, TaskId("leaf"), "dispute", "worker", I.ISSUER_SCHEMA, "", None, llm,
                           str(project.own / "a"))
        assert answer and answer.get("decision") == "accept", answer
        assert "NO COPY of this delivery" in llm.packets[-1] and "nested repositories (dep)" in llm.packets[-1]
    finally:
        e.stop()


@live
def test_live_a_copy_of_a_place_as_it_stands_has_a_git_of_its_own(project):
    """An issuer asked about a node not yet delivered rules on its place as it stands: in the copy's container, which
    mounts its round alone, the copy's git reads its history and shows the work not yet committed — a git borrowing
    the base's objects by a relative path read nothing there (row 4, c_compiler, 2026-10-30)."""
    x, a = project, project.own / "a"
    _sh(x, a, "echo one > c.txt && git add c.txt && git -c user.name=t -c user.email=t@t commit -qm committed"
              " && echo uncommitted >> c.txt && echo new > n.txt")
    round_ = x.own / ".gfso-scratch-a" / "issuer_1"
    x.files.mkdir(str(round_))
    with snapshot(a, round_ / "place", x) as at:
        s = x.session(at)
        run = lambda *cmd: s.run(list(cmd), cwd=at, timeout=60)
        log, status = run("git", "log", "--format=%s"), run("git", "status", "--porcelain")
        assert log.returncode == 0 and log.stdout.split() == ["committed"], (log.stdout, log.stderr)
        assert status.returncode == 0 and set(status.stdout.split()) >= {"M", "c.txt", "??", "n.txt"}, status
        assert run("test", "-e", ".git/objects/info/alternates").returncode != 0, "it borrows still"
        assert run("git", "fsck", "--connectivity-only").returncode == 0
