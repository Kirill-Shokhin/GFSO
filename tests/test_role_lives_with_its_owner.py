"""A registered executor role is dispatchable only while the party that registered it is still here.

Measured 2026-08-19: a delegated run reached its cost ceiling, wrote its record and exited — and the
engine went on executing the same graph, spending past the envelope and editing the very workspace
the recorded score had been computed against. The registration outlived the registrant, so the
dispatcher had somebody to start work for when nobody was waiting for it.

What is asserted here is the whole shape of the answer, because each half is a way to get it wrong:
the lapse must stop DISPATCH and nothing else (no signal, no state change — the graph must resume
exactly where it stood), a role that names no owner must stay available (a liveness signal nobody
supplied is not a death), and the return of the same owner must need no separate act.
"""
from __future__ import annotations

import time

import gfso.tools as T
from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.storage.memory import MemoryStorage
from gfso.delegate import AgentRegistry, Dispatcher
from gfso.engine import Engine


def _graph_with_one_leaf(e) -> None:
    T.create_task(e, "root", {"name": "goal", "description": "a goal",
                              "criteria": [{"name": "c1", "description": "the thing is done"}],
                              # a split carries its register (§13.1) — without it CHECK-4 stands and
                              # the plan is never admitted to execution, so nothing would dispatch
                              # for reasons that have nothing to do with what is under test
                              "accepted_risks": [{"item": "the thing may be harder than it looks",
                                                  "predictability": "statistical",
                                                  "justification": "accepted for this fixture",
                                                  "invalidation_condition": "it turns out impossible"}]},
                  "alice")
    T.create_task(e, "leaf", {"name": "leaf", "description": "do the thing",
                              "criteria": [{"name": "k", "description": "the thing is done"}]},
                  "worker", parent_id="root")
    T.map_criterion(e, "root", "leaf", "c1")
    T.signal(e, "root", "ACCEPT", "alice")


def _settle(e, spawned, secs: float = 2.5):
    """Wait for the dispatch thread to finish moving the graph.

    The dispatcher spawns in a THREAD and now sends ACCEPT there too (ACCEPT fixes the start of the
    obligation, §14.2), so the state a test reads immediately after `dispatch_once` depends on
    scheduling. These tests are about the RULE, not about timing, so they read a settled graph.
    """
    for _ in range(int(secs / 0.05)):
        if spawned and e.get_task("leaf").state.name != "OFFERED":
            return
        time.sleep(0.05)


def _setup(tmp_path, live: set):
    e = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=True, state_timeout=0)
    e.start()
    _graph_with_one_leaf(e)
    reg = AgentRegistry(path=str(tmp_path / "agents.json"))
    reg.register("worker", "llm-executor", workdir=str(tmp_path), client="session-7")
    reg.set_owner_liveness(lambda c: c in live)
    spawned: list[str] = []
    d = Dispatcher(e, reg, runner=lambda *a, **k: spawned.append(a[1] if len(a) > 1 else "?"))
    return e, reg, d, spawned


def test_dispatch_stops_when_the_owner_is_gone_and_nothing_else_moves(tmp_path):
    live = {"session-7"}
    e, reg, d, spawned = _setup(tmp_path, live)
    assert d.dispatch_once(), "precondition: with the owner present the leaf is dispatched"
    _settle(e, spawned)                      # the spawn thread sends ACCEPT — let it land first

    before = {n["id"]: n["state"] for n in T.get_graph(e)["nodes"]}
    live.clear()                                   # the client goes away; its lease lapses
    d._seen.clear()                                # a fresh round, so only liveness can decide
    assert d.dispatch_once() == [], "work was started for a role whose owner is gone"

    after = {n["id"]: n["state"] for n in T.get_graph(e)["nodes"]}
    assert after == before, "the lapse moved node state — it must stop dispatch and nothing else"
    e.stop()


def test_the_whole_arc_in_one_scenario_present_gone_returned(tmp_path):
    """Present → gone → returned, against the real dispatcher, in ONE run.

    Split across two scenarios this proves less than it looks: "it dispatches" and "it dispatches
    again" can both hold while the lapse in between never actually bit. The arc is what the
    criterion asks for, so the arc is what is run.
    """
    live = {"session-7"}
    e, reg, d, spawned = _setup(tmp_path, live)
    assert d.dispatch_once(), "with the owner present the leaf must be dispatched"

    live.clear()                                   # the client goes away
    d._seen.clear()
    assert d.dispatch_once() == [], "work was started for a role whose owner is gone"

    live.add("session-7")                          # the same client is back
    d._seen.clear()
    assert d.dispatch_once(), "the returning owner did not resume dispatch on the next cycle"
    e.stop()


def test_a_role_naming_no_owner_stays_available(tmp_path):
    """Absence of a declared lifetime is not a lapsed one — otherwise installing this feature would
    stop every registration made before it and every door that carries no lease."""
    live: set = set()
    e = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=True, state_timeout=0)
    e.start()
    _graph_with_one_leaf(e)
    reg = AgentRegistry(path=str(tmp_path / "agents.json"))
    reg.register("worker", "llm-executor", workdir=str(tmp_path))       # no client named
    reg.set_owner_liveness(lambda c: c in live)                          # nothing is live
    spawned: list = []
    d = Dispatcher(e, reg, runner=lambda *a, **k: spawned.append(a))
    assert d.dispatch_once(), "an untagged role was treated as owned by a dead client"
    e.stop()


def test_a_probe_that_throws_does_not_stop_the_work(tmp_path):
    e, reg, d, spawned = _setup(tmp_path, {"session-7"})
    reg.set_owner_liveness(lambda c: (_ for _ in ()).throw(RuntimeError("no answer")))
    d._seen.clear()
    assert d.dispatch_once(), "a broken liveness probe silently halted the engine"
    e.stop()


def test_the_lapse_is_said_once_not_once_per_cycle(tmp_path):
    live = {"session-7"}
    e, reg, d, spawned = _setup(tmp_path, live)
    live.clear()
    for _ in range(3):
        d._seen.clear()
        d.dispatch_once()
    said = [r for r in e.pipeline_log(limit=100) if "owner" in (r.get("message") or "")]
    assert len(said) == 1, f"the departure was logged {len(said)} times — once per dispatch cycle"
    assert "session-7" in said[0]["message"], "the entry does not name whose departure it reports"
    e.stop()


def test_the_server_hands_the_dispatcher_its_own_lease_answer(tmp_path, monkeypatch):
    """The join across the layer boundary — the half a unit test cannot see.

    The leases live in the HTTP layer and the dispatcher a layer below it, so the answer travels as
    an installed function. Everything above passes with that function absent: the roles simply stay
    available, exactly as they did before the feature. This is the test that fails if the server
    stops installing it — the failure mode where a rule holds in the layer that states it and is
    never applied by the layer that acts.
    """
    from fastapi.testclient import TestClient
    from gfso.api.server import create_app
    from gfso.delegate import default_agents
    from tests.test_integration import _engine

    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))
    import gfso.delegate as D
    D._DEFAULT_AGENTS = None                       # a roster for this test, not the machine's
    app = create_app(_engine())
    with TestClient(app) as c:
        reg = default_agents()
        reg.register("w", "llm-executor", workdir=str(tmp_path), client="session-9")
        assert not reg.owner_is_live("w"), "an unheard-of client counted as present"
        c.post("/api/lease", json={"id": "session-9"})
        assert reg.owner_is_live("w"), "the server's own lease did not reach the dispatcher"
        c.delete("/api/lease/session-9")
        assert not reg.owner_is_live("w"), "dropping the lease left the role dispatchable"
    D._DEFAULT_AGENTS = None


def test_a_run_already_started_is_left_to_finish(tmp_path):
    """The lapse stops STARTING work, never the work already running.

    Killing an in-flight executor would take back nothing — the tokens are spent and the files are
    half-written — and would turn a lapse into a destructive act, which is the one thing this must
    not be. So the gate sits before the spawn and has no reach past it.
    """
    live = {"session-7"}
    e, reg, d, spawned = _setup(tmp_path, live)
    assert d.dispatch_once(), "precondition: a run is started while the owner is present"
    _settle(e, spawned)                      # the spawn runs in a thread — read it once it has run
    started = list(spawned)
    assert started, "precondition: the spawn thread actually ran"
    live.clear()
    d._seen.clear()
    d.dispatch_once()
    assert spawned == started, "the lapse reached back into a run that had already begun"
    e.stop()


def test_a_settled_graph_produces_no_lapse_at_all(tmp_path):
    """Nothing ready to dispatch means nothing to refuse: a finished project must not report that it
    went quiet, or the log fills with departures of work nobody was waiting for."""
    live = {"session-7"}
    e, reg, d, spawned = _setup(tmp_path, live)
    T.signal(e, "leaf", "ACCEPT", "worker")
    T.signal(e, "leaf", "DELIVER", "worker", result="done")
    T.record_verdict(e, "leaf", "PASS", [], "alice", observed={"k": "checked by hand"})        # the parent's Del is the issuer here
    T.signal(e, "leaf", "PASS", "alice")
    assert T.get_task(e, "leaf")["state"] == "DONE", "precondition: the work is settled"

    live.clear()                                            # the owner leaves a finished project
    d._seen.clear()
    assert d.dispatch_once() == []
    said = [r for r in e.pipeline_log(limit=100) if "owner" in (r.get("message") or "")]
    assert said == [], "a settled project reported a lapse nobody was waiting on"
    e.stop()
