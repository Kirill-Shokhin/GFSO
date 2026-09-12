"""The dispatcher asks whether the working directory is there NOW, before it spends anything.

This is not a second copy of the registration rule. Registration answers "does this place exist" at
the moment a role is put on the roster; the spawn answers "is it still there", which is a different
fact and has two live sources: the roster is a json file the registry invites people to edit by hand
and re-reads on every access, so an entry can arrive without ever passing `register`; and a
directory that existed at registration can be moved or deleted before the node is picked up.

Spawning anyway is the expensive answer — the transport raises into a handler that only logs, no
signal is sent, and the node is never retried, so the run stops with nothing said about why.
"""
import json
import time

import pytest
from pathlib import Path

from gfso import tools as T
from gfso.core.types import TaskId
from gfso.delegate import AgentRegistry, Dispatcher, run_executor
from tests.support import make_engine


class _LoudLLM:
    """Any call on this is a failure of the test: nothing may be spent before the place is checked."""
    def __getattr__(self, name):
        raise AssertionError(f"the executor was built and asked for {name!r} with no workdir")


@pytest.fixture()
def engine():
    """One node awaiting `exec-1` - and the engine STOPPED afterwards.

    These tests start dispatcher rounds, so an engine left running keeps worker threads alive past
    the test that made them; a thread that outlives its test is a defect handed to whoever runs
    next, in a suite that has already paid for one run killing another's.
    """
    e = make_engine(validate_signals=True)
    e.start()
    T.create_task(e, "n1", {"name": "Nail", "description": "hammer a nail",
                            "criteria": [{"name": "flush", "description": "nail is flush"}]},
                  assignee="exec-1")
    try:
        yield e
    finally:
        e.stop()


def test_a_hand_written_roster_entry_pointing_nowhere_does_not_spawn(tmp_path, engine):
    """The hole the registration guard cannot close: nothing passed through `register`."""
    roster = tmp_path / "agents.json"
    roster.write_text(json.dumps({
        "exec-1": {"kind": "llm-executor", "model": "sonnet",
                   "workdir": str(tmp_path / "never-created")}}), encoding="utf-8")
    agents = AgentRegistry(str(roster))
    assert agents.get("exec-1")["workdir"].endswith("never-created")   # it really is on the roster

    out = run_executor(engine, TaskId("n1"), "exec-1", agents, _llm=_LoudLLM())

    assert out["status"] == "no_workdir"
    assert "not an existing directory" in out["error"]


def test_the_node_is_left_where_it_was(tmp_path, engine):
    """No signal is forged on a refusal to spawn: the node keeps its state for its issuer."""
    roster = tmp_path / "agents.json"
    roster.write_text(json.dumps({
        "exec-1": {"kind": "llm-executor", "workdir": str(tmp_path / "gone")}}), encoding="utf-8")
    before = engine.get_task("n1").state
    run_executor(engine, TaskId("n1"), "exec-1", AgentRegistry(str(roster)), _llm=_LoudLLM())
    assert engine.get_task("n1").state == before


def test_a_directory_deleted_after_registration_is_caught(tmp_path, engine):
    """Registered legitimately, then the place went away — the roster still names it."""
    place = tmp_path / "work"
    place.mkdir()
    agents = AgentRegistry(str(tmp_path / "agents.json"))
    agents.register("exec-1", "llm-executor", workdir=str(place))
    place.rmdir()

    out = run_executor(engine, TaskId("n1"), "exec-1", agents, _llm=_LoudLLM())
    assert out["status"] == "no_workdir"


def test_the_place_is_named_in_the_answer(tmp_path, engine):
    """A refusal that does not say WHICH directory sends the reader back to the roster to guess."""
    missing = str(tmp_path / "gone")
    roster = tmp_path / "agents.json"
    roster.write_text(json.dumps({"exec-1": {"kind": "llm-executor", "workdir": missing}}),
                      encoding="utf-8")
    out = run_executor(engine, TaskId("n1"), "exec-1", AgentRegistry(str(roster)), _llm=_LoudLLM())
    assert out["workdir"] == missing


def test_a_role_with_no_workdir_at_all_is_not_caught_here(tmp_path, engine):
    """Positive control: `external` and hand-driven roles carry no workdir and must reach the
    ordinary path — this guard fires on a workdir that is WRONG, never on the absence of one."""
    roster = tmp_path / "agents.json"
    roster.write_text(json.dumps({"exec-1": {"kind": "llm-executor"}}), encoding="utf-8")
    try:
        out = run_executor(engine, TaskId("n1"), "exec-1", AgentRegistry(str(roster)),
                           _llm=_LoudLLM())
    except AssertionError as ex:                 # the loud llm was reached, which is the point
        assert "was built and asked" in str(ex)
        return
    assert out.get("status") != "no_workdir"


def test_a_real_directory_still_reaches_the_executor(tmp_path, engine):
    """Positive control: a guard that refused everything would pass every test above."""
    place = tmp_path / "work"
    place.mkdir()
    agents = AgentRegistry(str(tmp_path / "agents.json"))
    agents.register("exec-1", "llm-executor", workdir=str(place))
    try:
        out = run_executor(engine, TaskId("n1"), "exec-1", agents, _llm=_LoudLLM())
    except AssertionError as ex:
        assert "was built and asked" in str(ex)
        return
    assert out.get("status") != "no_workdir"


# ---------------------------------------------------------------------------------------------
# Through the DISPATCHER, which is the path that actually runs. Asking inside `run_executor` is
# too late there: ACCEPT has already fixed the obligation and the round's key is spent, so a
# refusal that said "the node stays where it is" had in fact started the node and left it in
# EXECUTING forever - the transport crash it replaced, with a better sentence.
# ---------------------------------------------------------------------------------------------

def _dispatcher(engine, agents):
    return Dispatcher(engine, agents)


def test_the_dispatcher_does_not_start_a_node_whose_place_is_gone(tmp_path, engine):
    place = tmp_path / "work"
    place.mkdir()
    agents = AgentRegistry(str(tmp_path / "agents.json"))
    agents.register("exec-1", "llm-executor", workdir=str(place))
    place.rmdir()

    d = _dispatcher(engine, agents)
    d.dispatch_once()
    # A WINDOW, not an immediate read: `wait_idle` does not wait for the dispatcher's worker
    # thread, and read straight away this assertion passes whether or not the guard returns -
    # measured on a mutant that kept the message and dropped the `return` (OFFERED at once,
    # EXECUTING 1.5 s later).
    for _ in range(60):
        time.sleep(0.01)
        assert engine.get_task("n1").state.name == "OFFERED", "the node was started with nowhere to work"
    engine.wait_idle()


def test_restoring_the_directory_lets_the_next_pass_dispatch_it(tmp_path, engine):
    """The round must be FREED, not spent: a node held back by a fixable fact has to be reachable
    once the fact is fixed, or the refusal is a stall with a nicer message."""
    place = tmp_path / "work"
    place.mkdir()
    agents = AgentRegistry(str(tmp_path / "agents.json"))
    agents.register("exec-1", "llm-executor", workdir=str(place))
    place.rmdir()

    ran = []
    d = _dispatcher(engine, agents)
    d._runner = lambda en, tid, ex, ag: ran.append(str(tid))
    d.dispatch_once()
    # The run happens on a worker thread, so "it did not run" needs a WINDOW, not an immediate
    # read: asserting straight after the call passes whether or not the guard is there.
    for _ in range(50):
        time.sleep(0.01)
        assert ran == [], "the node was dispatched into a directory that is not there"
    engine.wait_idle()

    place.mkdir()                                    # the fact is fixed
    d.dispatch_once()
    for _ in range(200):
        if ran:
            break
        time.sleep(0.01)
    assert ran == ["n1"], "the node was never picked up again after the directory came back"


def test_the_dispatcher_says_which_place_is_missing(tmp_path, engine):
    place = tmp_path / "work"
    place.mkdir()
    agents = AgentRegistry(str(tmp_path / "agents.json"))
    agents.register("exec-1", "llm-executor", workdir=str(place))
    place.rmdir()

    # ONLY the dispatcher's own voice is captured. Capturing `emit_info` as well let
    # `run_executor`'s message satisfy this test, which then said nothing about the dispatcher.
    said = []
    d = _dispatcher(engine, agents)
    d._say_once = lambda key, msg: said.append(msg)
    d.dispatch_once()
    for _ in range(200):
        if said:
            break
        time.sleep(0.01)
    engine.wait_idle()
    assert any("work" in s and "not a directory" in s for s in said), said


def test_the_dispatchers_refusal_is_ascii(tmp_path, engine):
    place = tmp_path / "work"
    place.mkdir()
    agents = AgentRegistry(str(tmp_path / "agents.json"))
    agents.register("exec-1", "llm-executor", workdir=str(place))
    place.rmdir()

    said = []
    d = _dispatcher(engine, agents)
    d._say_once = lambda key, msg: said.append(msg)
    d.dispatch_once()
    for _ in range(200):
        if said:
            break
        time.sleep(0.01)
    engine.wait_idle()
    assert said, "the dispatcher held the node back and said nothing"
    for s in said:
        s.encode("cp1251")           # a dash or ellipsis here dies on a Windows console


def test_a_live_directory_still_starts_the_node(tmp_path, engine):
    """Positive control: a guard that held everything back would pass every case above."""
    place = tmp_path / "work"
    place.mkdir()
    agents = AgentRegistry(str(tmp_path / "agents.json"))
    agents.register("exec-1", "llm-executor", workdir=str(place))

    ran = []
    d = _dispatcher(engine, agents)
    d._runner = lambda en, tid, ex, ag: ran.append(str(tid))
    d.dispatch_once()
    for _ in range(200):
        if ran:
            break
        time.sleep(0.01)
    assert ran == ["n1"]


def test_the_same_fact_is_said_again_when_it_recurs(tmp_path, engine):
    """"Once" kept forever means once per server lifetime: a directory that goes away, comes back,
    and goes away again was held back in silence the second time."""
    place = tmp_path / "work"
    place.mkdir()
    agents = AgentRegistry(str(tmp_path / "agents.json"))
    agents.register("exec-1", "llm-executor", workdir=str(place))

    said = []
    d = _dispatcher(engine, agents)
    d._runner = lambda en, tid, ex, ag: None
    _real = d._say_once
    def _spy(key, msg, _r=_real, _s=said):
        out = _r(key, msg)               # only what it ACTUALLY said, not every call
        if out:
            _s.append(msg)
        return out
    d._say_once = _spy

    place.rmdir()
    d.dispatch_once()
    for _ in range(200):
        if said:
            break
        time.sleep(0.01)
    assert len(said) == 1

    place.mkdir()                      # the place is back: the round runs and the notice is released
    d.dispatch_once()
    engine.wait_idle()
    for _ in range(50):
        time.sleep(0.01)

    # A NEW ROUND. The dedup key is per node x iteration and round 2 has now spent it; in life a
    # rework or a re-ASSIGN produces the next one. Building a whole rework cycle here would test the
    # FSM, not the thing under test, which is whether the notice was released.
    d._seen.clear()
    place.rmdir()                      # ...and gone again
    d.dispatch_once()
    for _ in range(200):
        if len(said) > 1:
            break
        time.sleep(0.01)
    assert len(said) == 2, "the second absence was held back in silence"


def test_it_is_not_repeated_while_the_fact_stands(tmp_path, engine):
    """Positive control: releasing the notice must not turn it into a message per pass."""
    place = tmp_path / "work"
    place.mkdir()
    agents = AgentRegistry(str(tmp_path / "agents.json"))
    agents.register("exec-1", "llm-executor", workdir=str(place))
    place.rmdir()

    said = []
    d = _dispatcher(engine, agents)
    _real = d._say_once
    def _spy(key, msg, _r=_real, _s=said):
        out = _r(key, msg)               # only what it ACTUALLY said, not every call
        if out:
            _s.append(msg)
        return out
    d._say_once = _spy
    for _ in range(4):
        d.dispatch_once()
        for _ in range(30):
            time.sleep(0.005)
    assert len(said) == 1, said
