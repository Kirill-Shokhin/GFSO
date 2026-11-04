"""A goal over holds nothing on the person's machine: a run's whole set of containers stood idle past its root's DONE, for as
long as the project was left unstopped (a row, measured: 18 containers). Its volumes stay; a reopen starts them again."""
import subprocess
from contextlib import suppress
from types import SimpleNamespace as N

import gfso.delegate as DG
from gfso.core.types.enums import State
from gfso.delegate import Dispatcher

from tests.support import make_engine


class _Works(Exception):
    pass


def _dispatcher(monkeypatch, states, joining=(), unjoined=(), landed=True):
    e, stops, running = make_engine(), [], []
    tasks = [N(id=f"t{i}", state=s) for i, s in enumerate(states)]
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
