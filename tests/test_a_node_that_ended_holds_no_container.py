"""A node that ended — passed and joined, or cancelled — holds no container: its place's, its client's and its
commands' end, its directories and CLI state kept; reopened, its next session starts them again. Standing until the
project stopped, a done node's containers counted against every other's (SECURITY.md)."""
from types import SimpleNamespace

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
    d = DL.Dispatcher.__new__(DL.Dispatcher)
    d._engine, d._agents = engine, None
    return d, released


def test_a_node_that_passed_or_was_cancelled_ends_its_places_containers(monkeypatch):
    for state in (State.DONE, State.ABANDONED):
        d, released = _dispatcher(monkeypatch, state)
        d._released("a")
        assert released == ["/places/a"], state


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
