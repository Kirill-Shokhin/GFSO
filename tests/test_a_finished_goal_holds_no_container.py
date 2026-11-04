"""A goal over holds nothing on the person's machine: a run's whole set of containers stood idle past its root's DONE, for as
long as the project was left unstopped (a row, measured: 18 containers). Its volumes stay; a reopen starts them again."""
import subprocess
import threading
from contextlib import suppress
from functools import partial
from types import SimpleNamespace as N

import gfso.delegate as DG
from gfso.core.types.enums import State
from gfso.delegate import Dispatcher

from tests.support import make_engine


_IN_FLIGHT = DG.in_flight


class _Works(Exception):
    pass


def _dispatcher(monkeypatch, states, joining=(), unjoined=(), landed=True):
    e, stops, running = make_engine(), [], []
    tasks = [N(id=f"t{i}", state=s, iteration=0, reopens=0, revisions=0, done_reason=None, false_positive=False,
               assignee="agent")
             for i, s in enumerate(states)]
    monkeypatch.setattr(e, "all_tasks", lambda: tasks)
    monkeypatch.setattr(e.joins, "joining_nodes", lambda: list(joining))
    monkeypatch.setattr(e.joins, "unjoined_roots", lambda: dict.fromkeys(unjoined, "why"))
    monkeypatch.setattr(e.joins, "root_landed", lambda t: landed)
    monkeypatch.setattr(e.graph, "get_parent", lambda tid: None)
    monkeypatch.setattr(DG, "in_flight", lambda: running)
    monkeypatch.setattr(DG, "execution_of", lambda *a: N(stop=lambda: stops.append(1)))
    d = Dispatcher(e, N())
    d.running = running
    monkeypatch.setattr(d, "_publish_the_roster", lambda: None)
    monkeypatch.setattr(d, "_rejoin", lambda: setattr(d, "_rejoined_once", True))

    def works():                                 # …past the rest, the round's work: not this test's
        raise _Works

    monkeypatch.setattr(d, "_resolve_ready_blocks", works)
    poll = d.dispatch_once

    def once():
        with suppress(_Works):
            return poll()

    d.dispatch_once = once
    return d, tasks, stops


def test_a_goal_over_ends_its_containers_once(monkeypatch):
    d, _, stops = _dispatcher(monkeypatch, [State.DONE, State.DONE, State.ABANDONED])
    d._rejoined_once = True
    d.dispatch_once(), d.dispatch_once()
    assert stops == [1]


def test_what_may_still_run_keeps_them(monkeypatch):
    """A parent's acceptance settles none of its children (§11.3); a result landing, or not landed, is still the run's."""
    for states, joining, unjoined in (([State.DONE, State.EXECUTING], (), ()), ([State.DONE], ("t0",), ()),
                                      ([State.DONE], (), ("t0",)), ([], (), ())):
        d, _, stops = _dispatcher(monkeypatch, states, joining, unjoined)
        d._rejoined_once = True
        d.dispatch_once()
        assert stops == [], (states, joining, unjoined)


def test_clearing_the_places_is_work_still_running(monkeypatch):
    """The join's mark cleared, its places going: a rest then stopped the container they were going through (critic)."""
    d, tasks, _ = _dispatcher(monkeypatch, [State.DONE])
    monkeypatch.setattr(DG, "in_flight", _IN_FLIGHT)
    seen = []
    monkeypatch.setattr(d._engine.graph, "get_task", lambda tid: tasks[0])
    monkeypatch.setattr(DG, "join_whole", lambda *a: None)
    monkeypatch.setattr(DG, "land_accepted", lambda *a: None)
    monkeypatch.setattr(DG, "clear_workspaces", lambda *a: seen.extend(DG.in_flight()))
    monkeypatch.setattr(d, "_released", lambda tid: None)
    d._join("t0")
    assert [w for w in seen if w.get("verb") == "clear_workspaces" or "clear_workspaces" in str(w)], seen


def _a_root_to_land(monkeypatch, states=(State.DONE,)):
    d, tasks, _ = _dispatcher(monkeypatch, list(states))
    cleared = []
    monkeypatch.setattr(d._engine.graph, "get_task", lambda tid: next(t for t in tasks if t.id == tid))
    monkeypatch.setattr(DG, "join_whole", lambda *a: None)
    monkeypatch.setattr(DG, "land_accepted", lambda *a: None)
    monkeypatch.setattr(DG, "clear_workspaces", lambda e, a, t: cleared.append(t.id))
    monkeypatch.setattr(d, "_released", lambda tid: None)
    d._rejoined_once = True
    return d, tasks, cleared


def test_a_root_landing_with_no_verdict_coming_clears_at_once(monkeypatch):
    d, _, cleared = _a_root_to_land(monkeypatch)
    d._join("t0")
    assert cleared == ["t0"]


def test_a_validation_running_or_queued_keeps_the_places_and_its_end_clears_them(monkeypatch):
    """A holder signed the root while a validation ran: cleared at the landing, its round died and the verdict that could
    refute the signature with it. Whatever that verdict says (PASS, FAIL, none), the claim's end is what lets them go."""
    for take, end in (("begin_validation", "end_validation"), ("queue_validation", "dequeue_validation")):
        d, _, cleared = _a_root_to_land(monkeypatch)
        key = getattr(d._engine.claims, take)("t0")
        d._join("t0")
        d.dispatch_once()
        assert cleared == [], take
        getattr(d._engine.claims, end)(key)
        d.dispatch_once(), d.dispatch_once()
        assert cleared == ["t0"], take


def test_any_nodes_validation_holds_them_since_the_clearing_ends_every_round(monkeypatch):
    d, _, cleared = _a_root_to_land(monkeypatch, (State.DONE, State.DONE))
    key = d._engine.claims.begin_validation("t1")
    d._join("t0")
    assert cleared == []
    d._engine.claims.end_validation(key)
    d.dispatch_once()
    assert cleared == ["t0"]


def test_a_stopped_project_still_clears_what_a_verdict_held(monkeypatch):
    d, _, cleared = _a_root_to_land(monkeypatch)
    key = d._engine.claims.begin_validation("t0")
    d._join("t0")
    d._engine.claims.end_validation(key)
    monkeypatch.setattr(d._engine, "paused", lambda: {"why": "the user's stop"})
    d.dispatch_once()
    assert cleared == ["t0"]


def test_a_root_reopened_while_held_is_its_next_joins_to_clear(monkeypatch):
    d, tasks, cleared = _a_root_to_land(monkeypatch)
    key = d._engine.claims.begin_validation("t0")
    d._join("t0")
    d._engine.claims.end_validation(key)
    tasks[0].state = State.OFFERED
    d.dispatch_once()
    tasks[0].state = State.DONE
    d.dispatch_once()
    assert cleared == []
    d._join("t0")
    assert cleared == ["t0"]


def test_a_root_held_and_joining_again_is_not_cleared_under_its_join(monkeypatch):
    d, _, cleared = _a_root_to_land(monkeypatch)
    key = d._engine.claims.begin_validation("t0")
    d._join("t0")
    d._engine.claims.end_validation(key)
    monkeypatch.setattr(d._engine.joins, "root_landed", lambda t: False)
    d.dispatch_once()
    assert cleared == []


def test_a_restart_over_a_held_root_clears_it_through_the_first_rejoin(monkeypatch):
    """A restart keeps neither the claim nor what it held: the first pass reads the place still standing, as it does for a
    process stopped between a DONE and its join."""
    d, _, _ = _a_root_to_land(monkeypatch)
    went = threading.Event()
    monkeypatch.setattr(DG, "clear_workspaces", lambda *a: went.set())
    monkeypatch.setattr(d, "_rejoin", partial(Dispatcher._rejoin, d))
    monkeypatch.setattr(d, "_will_join", lambda tid: True)
    d._rejoined_once = False
    d.dispatch_once()
    assert went.wait(10)


def test_a_done_whose_join_is_not_marked_yet_keeps_them(monkeypatch):
    """Readable before the bus marks its join: stopped here, the join then starts them and nothing ends them (critic)."""
    d, _, stops = _dispatcher(monkeypatch, [State.DONE], landed=False)
    d._rejoined_once = True
    d.dispatch_once()
    assert stops == []


def test_what_ran_since_and_a_stop_that_failed_are_asked_again(monkeypatch):
    d, _, stops = _dispatcher(monkeypatch, [State.DONE])
    d._rejoined_once = True
    d.dispatch_once()
    d.running.append({"project": d._engine.project_name or DG.DEFAULT_PROJECT})
    d.dispatch_once()
    d.running.clear()
    d.dispatch_once(), d.dispatch_once()
    assert stops == [1, 1], "a verb that moved no node may have started one"
    d, _, stops = _dispatcher(monkeypatch, [State.DONE])
    d._rejoined_once = True
    tries = []

    def stop():
        tries.append(1)
        if len(tries) == 1:
            raise subprocess.TimeoutExpired("docker", 60)

    monkeypatch.setattr(DG, "execution_of", lambda *a: N(stop=stop))
    d.dispatch_once(), d.dispatch_once(), d.dispatch_once()
    assert tries == [1, 1]


def test_a_start_asks_first_whether_the_result_landed(monkeypatch):
    """A server stopped between a root's DONE and its join left nothing in memory to say so: `_rejoin`'s first pass reads it."""
    d, _, stops = _dispatcher(monkeypatch, [State.DONE])
    d.dispatch_once()
    assert stops == [] and d._rejoined_once
    d.dispatch_once()
    assert stops == [1]


def test_a_reopen_works_again_and_a_later_end_rests_again(monkeypatch):
    d, tasks, stops = _dispatcher(monkeypatch, [State.DONE])
    d._rejoined_once = True
    d.dispatch_once()
    tasks[0].state = State.OFFERED
    d.dispatch_once()
    assert not d._rested
    tasks[0].state = State.DONE
    d.dispatch_once()
    assert stops == [1, 1]
