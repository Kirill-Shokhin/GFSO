"""A node's input is its packet and its declared edges (M1, §15.5). A part started after a sibling joined their whole
took that sibling's work from the whole's tree with no edge in the plan, and whether it did followed the order the parts
happened to start in: on 104 recorded projects, 442 of 970 nodes with siblings started after a sibling with no path to
them was DONE. Now it starts from where the whole stood when it entered the split; a producer comes by its edge. And what
it reads as the base holds no sibling's delivery, by its name or its id.

CONTROLS: let `_ensure_place` take no ground and the first test goes red; let `_before_a_part_joins` ground a part admitted
later on the first join's commit and the third does; mount the base itself read-only (`Volume.mount`) and the live one does."""
from __future__ import annotations

import subprocess
import time

import gfso.tools as T
from gfso.adapters import worktrees as W
from gfso.adapters.execution import ContainerExecution, PlaceContainer
from gfso.core.graph.model import grounds_key
from gfso.core.types import State, TaskId
from gfso.delegate import Dispatcher, _auto_validate
from gfso.sessions import run_executor
from tests.test_a_node_works_in_its_own_place import _Executor, _Validator, _plan, _until
from tests.test_a_session_holds_only_its_own_place import IMAGE, project  # noqa: F401 — a fixture
from tests.support import criterion, REGISTER


def _done(e, *tids):
    return all(e.graph.get_state(TaskId(t)) == State.DONE for t in tids)


def _dispatched(e, agents, sessions, until, held=(), rounds=1200):
    """Sessions run as the dispatcher starts them, those `held` only once a part has joined the whole."""
    def runner(en, t, ex, ag):
        end = time.monotonic() + 8
        while str(t) in held and not en.graph.setting(grounds_key("par")) and time.monotonic() < end:
            time.sleep(0.02)
        return run_executor(en, t, ex, ag, _llm=sessions[str(t)])

    validated: dict = {}
    d = Dispatcher(e, agents, poll=30, runner=runner, validator_runner=lambda en, t, ag, **k: _auto_validate(
        en, t, ag, _llm=_Validator(en, t, validated), **k))
    for _ in range(rounds):
        d.dispatch_once()
        time.sleep(0.05)
        e.wait_idle()
        if until():
            return
    raise AssertionError(f"not reached: {({t.id: t.state.name for t in e.all_tasks()})}")


def _part(name, by="exec-2"):
    return {"task_id": name, "spec": {"description": f"part {name}", "criteria": [criterion(f"{name}_ok")]},
            "assignee": by, "covers": ["g"]}


def test_a_part_started_after_its_sibling_joined_does_not_hold_its_work(tmp_path):
    e, agents, _ = _plan(tmp_path, whole="exec-1")
    sessions = {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"})}
    _dispatched(e, agents, sessions, lambda: sessions["b"].saw, held=("b",))
    assert "a.c" not in sessions["b"].saw, "a sibling's work came with no edge in the plan"


def test_an_edge_brings_its_producer_to_its_consumer_and_opens_nothing_to_another(tmp_path):
    e, agents, _ = _plan(tmp_path, whole="exec-1")
    T.decompose(e, "par", [_part("c")], accepted_risks=REGISTER)
    T.add_dependency(e, "a", "b")
    sessions = {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"}), "c": _Executor("c", {"c.c": "C\n"})}
    _dispatched(e, agents, sessions, lambda: sessions["b"].saw and sessions["c"].saw, held=("c",))
    assert "a.c" in sessions["b"].saw
    assert "a.c" not in sessions["c"].saw, "another part's edge opened a sibling's work to it"


def test_a_part_admitted_after_a_join_stands_on_what_the_whole_then_held(tmp_path):
    e, agents, _ = _plan(tmp_path, whole="exec-1")
    sessions = {"a": _Executor("a", {"a.c": "A\n"}), "b": _Executor("b", {"b.c": "B\n"}), "par": _Executor("par", {}),
                "c": _Executor("c", {"c.c": "C\n"})}
    _dispatched(e, agents, sessions, lambda: e.graph.setting(grounds_key("par")), held=("b",))
    _until(lambda: _done(e, "a"))
    T.decompose(e, "par", [_part("c")], accepted_risks=REGISTER)
    _dispatched(e, agents, sessions, lambda: sessions["c"].saw)
    assert "a.c" in sessions["c"].saw, "its decomposer's fixing saw that work: the part stands on it"


def test_live_a_session_reads_no_delivery_through_the_base_and_a_join_brings_it(project):  # noqa: F811
    """A delivery carried into the base as a branch was every session's to read, by its name or its id, judged or not
    (critic, live). The place it joins reads it, its objects in its own store."""
    base = project.base
    W.git(base, "init", "-q", execution=project)
    (W._fs(project)).files.write_bytes(str(base / "f.txt"), b"base\n")
    W.git(base, "add", "-A", execution=project)
    W.git(base, "commit", "-q", "-m", "first", execution=project)
    project.volume.read_again(project.image)
    places = {n: project.own / n for n in ("a", "b", "par")}
    for n, p in places.items():
        assert W.ensure(base, p, f"gfso/p/{n}", base, execution=project)
    W._fs(project).files.write_bytes(str(places["a"] / "a.txt"), b"a\n")
    W.commit_all(base, places["a"], "a's delivery", "exec", execution=project, branch="gfso/p/a")
    sha = W.git(base, "rev-parse", "refs/heads/gfso/p/a", execution=project).stdout.strip()
    assert sha

    def cmd(place, script):
        s = project.session(str(place), "agent-1")
        assert isinstance(s, PlaceContainer)
        c = s.client()
        c.commands_env()
        return subprocess.run(["docker", "exec", "-w", s.to_inside(str(place)), c.commands.name, "sh", "-c", script],
                              capture_output=True, text=True)

    other = cmd(places["b"], f"git -c safe.directory='*' cat-file -e {sha}; echo id=$?; git -c safe.directory='*' -C {project.to_inside(str(base))} "
                             "for-each-ref refs/heads/gfso; echo end")
    assert "id=0" not in other.stdout and "gfso/p/a" not in other.stdout, f"a sibling's delivery read: {other.stdout}"

    assert W.merge(base, places["par"], "gfso/p/a", "a joins", execution=project) is None
    joined = cmd(places["par"], f"git -c safe.directory='*' log --format=%H -- a.txt; git -c safe.directory='*' fsck --connectivity-only >/dev/null 2>&1; echo fsck=$?; cat a.txt")
    assert sha in joined.stdout and "fsck=0" in joined.stdout and "a\n" in joined.stdout, joined.stdout + joined.stderr

    # …and a later part's ground in a place holding what no other does: a commit by no ref, carried by a bundle
    anchor = W.git(places["par"], "rev-parse", "HEAD", execution=project).stdout.strip()
    late = project.own / "late"
    assert W.ensure(base, late, "gfso/p/late", places["par"], execution=project, ground=lambda: anchor)
    assert W.git(late, "rev-parse", "HEAD", execution=project).stdout.strip() == anchor


def test_live_a_base_standing_on_a_node_branch_imports(tmp_path):
    """The user continuing from `gfso/<p>/accepted`: the copy dropped the node branches and its HEAD named nothing, so a new
    project could not start (critic, reproduced)."""
    base = tmp_path / "work" / "ws"
    base.mkdir(parents=True)
    for a in (["init", "-q"], ["config", "user.email", "x@x"], ["config", "user.name", "x"],
              ["commit", "-q", "--allow-empty", "-m", "one"], ["checkout", "-q", "-b", "gfso/p/accepted"]):
        subprocess.run(["git", *a], cwd=base, check=True)
    (tmp_path / "e.env").write_text("NOTHING=1\n")
    x = ContainerExecution(f"t{time.time_ns()}", IMAGE, str(tmp_path / "e.env"), str(tmp_path / "state"), str(base), "p")
    try:
        x.start()
        assert W.git(base, "rev-parse", "--verify", W.READ_REF, execution=x).returncode == 0
    finally:
        x.stop()
        x.volume.remove()
