"""At the root's close the project's validation and contact rounds and its temp go, each round out of the record of the
rounds standing; the base, a place that did not join and anything else of the project's directory stay."""
from types import SimpleNamespace as N

import pytest

from gfso import workspaces as WS
from gfso.adapters.execution import LocalExecution, scratch_of
from gfso.core.protocol.procedure import round_of
from gfso.core.types import PlaceUnavailable, nodes_root
from gfso.engine.findings import _ROUND, record_round
from tests.support import make_engine


def _project(tmp_path):
    base = tmp_path / "repo"
    base.mkdir()
    own, ex = nodes_root(base) / "p", LocalExecution()
    # …this host's rounds, a node's and the base's, and one laid among the project's places before they moved
    rounds = [scratch_of(base, "p", ex) / "root_1", scratch_of(own / "n1", "p", ex) / "n1_2", own / ".gfso-scratch-.repo" / "root_0"]
    for r in rounds:
        (r / "build").mkdir(parents=True)
        (r / "build" / "a.o").write_text("x")
    (own / "n2" / "src").mkdir(parents=True)          # a place that did not join
    return base, own, rounds


def _cleared(tmp_path, monkeypatch, holder_has_a_workdir=True):
    e = make_engine(llm=None, check_interval=10_000)
    monkeypatch.setattr(e, "project_name", "p", raising=False)
    base, own, rounds = _project(tmp_path)
    for r in rounds:
        record_round(e.graph, str(r), True)
    root = N(id="root", assignee="a")
    monkeypatch.setattr(e, "all_tasks", lambda: [])
    monkeypatch.setattr(WS, "llm_factory", lambda *a, **k: N(forget=lambda c: None))
    monkeypatch.setattr(WS, "where_it_runs", lambda *a: N(stop=lambda: None))
    class Held(LocalExecution):                    # …a container execution's base and temp, its files on this host
        pass
    ex = Held()
    ex.base, ex.tmp = base, own / ".gfso-tmp"
    (ex.tmp / "node-1").mkdir(parents=True)
    monkeypatch.setattr(WS, "ContainerExecution", Held)
    monkeypatch.setattr(WS, "execution_of", lambda *a: ex)
    monkeypatch.setattr(WS, "_place_of", lambda e_, a, t: (str(base), None, None) if holder_has_a_workdir else None)
    WS.clear_workspaces(e, None, root)
    return e, base, own, rounds


def test_the_rounds_go_and_the_record_says_so(tmp_path, monkeypatch):
    e, base, own, rounds = _cleared(tmp_path, monkeypatch)
    assert not any(p.name.startswith(".gfso-scratch-") or p.name == ".gfso-tmp" for p in own.iterdir())
    assert not any(r.parent.exists() for r in rounds), "this host's scratch too"
    assert all(e.graph.setting(_ROUND + round_of(r)[1]) == "0" for r in rounds)


def test_a_root_held_with_no_workdir_still_clears(tmp_path, monkeypatch):
    """The person holding the root has no roster workdir: the base is the execution's."""
    e, base, own, rounds = _cleared(tmp_path, monkeypatch, holder_has_a_workdir=False)
    assert not any(p.name.startswith(".gfso-scratch-") for p in own.iterdir())


def test_the_container_stops_however_the_clearing_ends(monkeypatch):
    """A place gone mid-way raises out of the places' loop: the project's container still stops."""
    stops = []
    monkeypatch.setattr(WS, "where_it_runs", lambda *a: N(stop=lambda: stops.append(1)))
    def gone(*a):
        raise PlaceUnavailable("p", "its volume v is gone")
    monkeypatch.setattr(WS, "_remove_joined_places", gone)
    with pytest.raises(PlaceUnavailable):
        WS.clear_workspaces(make_engine(llm=None, check_interval=10_000), None, N(id="root"))
    assert stops == [1]


def test_what_is_not_a_round_stays(tmp_path, monkeypatch):
    _, base, own, _ = _cleared(tmp_path, monkeypatch)
    assert base.is_dir() and (own / "n2" / "src").is_dir()
