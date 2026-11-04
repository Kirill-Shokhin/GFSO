"""A node that ended — passed and joined, or cancelled — holds no container: its place's, its client's and its
commands' end, its directories and CLI state kept; reopened, its next session starts them again. Standing until the
project stopped, a done node's containers counted against every other's (SECURITY.md)."""
import os
from types import SimpleNamespace

import gfso.adapters.execution as E
import gfso.delegate as DL
from gfso.core.types import State, TaskId


def _dispatcher(monkeypatch, state, joining=(), scope=None):
    released = []
    task = SimpleNamespace(id=TaskId("a"), state=state)
    monkeypatch.setattr(DL, "session_scope", lambda e, a, t: scope)
    engine = SimpleNamespace(graph=SimpleNamespace(get_task=lambda tid: task),
                             joins=SimpleNamespace(joining_nodes=lambda: list(joining)))
    monkeypatch.setattr(DL, "_place_of", lambda e, a, t: ("a", "/places/a", "gfso/a"))
    monkeypatch.setattr(DL, "made", lambda e, w: True)
    monkeypatch.setattr(DL, "execution_of", lambda e, a=None: SimpleNamespace(release=released.append))
    monkeypatch.setattr(DL, "release_rounds", lambda ex, p: released.append(f"rounds of {p}"))
    d = DL.Dispatcher.__new__(DL.Dispatcher)
    d._engine, d._agents = engine, None
    return d, released


def test_a_node_that_passed_or_was_cancelled_ends_its_places_containers(monkeypatch):
    for state in (State.DONE, State.ABANDONED):
        d, released = _dispatcher(monkeypatch, state)
        d._released("a")
        assert released == ["/places/a", "rounds of /places/a"], state


def test_its_rounds_go_with_it_and_no_other_nodes(monkeypatch, tmp_path):
    """Filing a finding reads what its command names in a round, in the round's own container, after its run ended it: such
    a container stood idle to the project's end (a row: every node whose verdict named a round's path, none other)."""
    place = tmp_path / ".gfso-nodes-ws" / "p" / "a"
    place.mkdir(parents=True)
    ex = E.ContainerExecution.__new__(E.ContainerExecution)
    ex.container, ex.project_name = "c", "p"
    stopped = []

    def session(name):
        return SimpleNamespace(stop=lambda: stopped.append(name))

    at = lambda sub: os.path.normcase(place.parent / sub)
    monkeypatch.setattr(E, "_SESSIONS", {("c", at(".gfso-scratch-a/r_1/batch1")): session("round"),
                                         ("c", at(".gfso-scratch-ab/r_1/batch1")): session("a longer name's"),
                                         ("c", at("a")): session("its place"),
                                         ("other", at(".gfso-scratch-a/r_1/batch1")): session("another project's")})
    E.release_rounds(ex, str(place))
    assert stopped == ["round"]
    E.release_rounds(SimpleNamespace(), str(place))


def test_a_node_still_joining_or_at_work_keeps_them(monkeypatch):
    d, released = _dispatcher(monkeypatch, State.DONE, joining=("a",))
    d._released("a")
    d2, released2 = _dispatcher(monkeypatch, State.EXECUTING)
    d2._released("a")
    assert released == [] and released2 == []


def test_a_scope_member_that_ended_leaves_its_scopes_place_alone(monkeypatch):
    """A member of a session scope works in its top's place: its PASS ended the containers the scope's rework ran in
    (critic B8). The place goes with the node that owns it."""
    d, released = _dispatcher(monkeypatch, State.DONE, scope=SimpleNamespace(id=TaskId("root")))
    d._released("a")
    assert released == []
