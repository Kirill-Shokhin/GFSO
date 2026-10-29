"""An execution place that cannot start anything is the environment's state, not a node's failure: while it is down
nobody can move, as under the account's limit (docs/notes/PROJECT_CLOCK.md, case 14). Measured on
GB_sql_database_tnij0m952 (2026-10-26): launched with Docker Desktop not running, every executor session died at once,
was redialled four times as a CUT call, then read twice as an unreadable report and PARKED; for 40 min under AUTO the
parked leaf's machine issuer met the same dead daemon at every ask, said nothing, and its asks backed off 2, 4, 8, 16 min
while the bounds ran. The place now reports itself unavailable, the booking stops the project as the system, the round
is given back, and the monitor starts the project once the place answers its probe."""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

import gfso.tools as T
import gfso.tools_llm as TL
from gfso import decompose as DEC, delegate as D, issuer as I, sessions as S
from gfso.adapters import execution as E
from gfso.adapters.llm.headless import ClaudeCodeProvider
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.core.types import Mode, PlaceUnavailable, TaskId
from gfso.delegate import Dispatcher
from tests.support import criterion, make_engine
from tests.test_a_cut_call_does_not_spend_the_nodes_retry import _an_offer
from tests.test_delegate import _agents
from tests.test_the_mode_decides_who_holds_what import _admit, _engine, _kid

#: What the docker CLI says when Docker Desktop is not running (probed 2026-10-26 on a pipe nobody serves).
DOWN = ("failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine; check if the path is correct "
        "and if the daemon is running: open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.")


class _Docker:
    """The docker CLI as the server reaches it (`execution.run`), its daemon `up` or not; nothing real is started."""
    def __init__(self):
        self.up, self.calls = False, []

    def __call__(self, args, **kw):
        self.calls.append(list(args[:2]))
        out = "ok\n" if args[1:2] == ["run"] else "29.7.2\n"          # …a storage probe's file read back, or the version
        return subprocess.CompletedProcess(args, 0 if self.up else 1, out if self.up else "",
                                           "" if self.up else DOWN)


def _place(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "run", docker := _Docker())
    (base := tmp_path / "ws").mkdir(exist_ok=True)
    ex = E.ContainerExecution("e3-linux", "img", str(tmp_path / "env"), str(tmp_path / "state"), str(base), "p")
    monkeypatch.setattr(D, "execution_of", lambda *a, **k: ex)
    monkeypatch.setattr(S, "project_llm", lambda engine, model, agents=None: ClaudeCodeProvider(model, execution=ex))
    return ex, docker


def test_the_place_says_it_is_down_in_the_daemons_own_words(tmp_path, monkeypatch):
    ex, docker = _place(tmp_path, monkeypatch)
    assert ex.unavailable() == DOWN
    try:
        ex.popen(["claude", "-p"], env={}, cwd=str(tmp_path / "ws"))
        raise AssertionError("a launch the place cannot start was not refused")
    except PlaceUnavailable as e:
        assert e.place == "e3-linux" and str(e) == f"the execution place e3-linux is unavailable: {DOWN}"
    assert ["docker", "run"] not in docker.calls, "a container was asked of a daemon that is not there"
    docker.up = True
    assert ex.unavailable() is None and E.LocalExecution().unavailable() is None


def test_a_session_its_place_could_not_start_is_neither_cut_nor_a_report_and_stops_the_project(tmp_path, monkeypatch):
    ex, docker = _place(tmp_path, monkeypatch)
    llm = ClaudeCodeProvider("haiku", execution=ex)
    assert llm.run_agent("sys", "packet", ("Read",), cwd=str(tmp_path / "ws")) == ""
    c = llm.calls[-1]
    assert c["ended"] == "unavailable" and c["place"] == "e3-linux" and not c["transport_torn"], c
    e = make_engine(llm=None)
    e.record_llm_usage("executor", llm, TaskId("n"))
    stop = e.paused()
    assert stop and stop["by"] == "system" and stop["place"] == "e3-linux" and not stop.get("until"), stop
    assert stop["why"] == f"the execution place e3-linux is unavailable: {DOWN}", stop


def test_an_executor_round_on_a_dead_place_is_given_back_and_runs_again_once_the_place_answers(tmp_path, monkeypatch):
    """The measured run end to end through the real executor door: no CUT redial, no unreadable report, no park — the
    project stopped as the system, nothing started while it stands, and the round runs again after the place answers."""
    ex, docker = _place(tmp_path, monkeypatch)
    monkeypatch.setattr(S, "_enter_workspace", lambda engine, agents_, task, order: (str(tmp_path / "ws"), [], None))
    monkeypatch.setattr(S, "_executor_packet", lambda *a, **k: "packet")
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    _an_offer(e)
    said = []
    e.emit_info = lambda src, msg, _s=said: _s.append(msg)
    d = Dispatcher(e, agents)
    for _ in range(4):
        d.dispatch_once()
        time.sleep(0.4)
    spawned = lambda: sum("executor exec-1 spawned" in m for m in said)
    assert spawned() == 1, said
    assert not any("CUT" in m or "DID NOT PARSE" in m or "PARKED" in m for m in said), said
    assert "kid" not in {str(x) for x in e.parking.parked_executions()}
    assert (e.paused() or {}).get("place") == "e3-linux", e.paused()
    e.lift_the_system_stop(time.time())
    assert e.paused(), "started while the place was still down"
    docker.up = True
    e.lift_the_system_stop(time.time())
    assert e.paused() is None and any("the execution place e3-linux answers" in m for m in said), said
    docker.up = False                      # down again: the round given back is run, and stops the project again
    for _ in range(4):
        d.dispatch_once()
        time.sleep(0.4)
    assert spawned() == 2 and (e.paused() or {}).get("place") == "e3-linux", said
    e.stop()


def test_a_parked_node_s_machine_issuer_meets_the_dead_place_as_the_stop_and_is_asked_again_at_the_start(
        tmp_path, monkeypatch):
    """(2) Under AUTO the parked leaf's issuer WAS asked — its turn died on the same dead place, booked nothing, said
    nothing, and backed off 120 s doubling with the project running. Now the turn stops the project, the line is said,
    and its question is due again a second past the start."""
    ex, docker = _place(tmp_path, monkeypatch)
    e = _engine(Mode.AUTO)
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("exec-2", "llm-executor"), ("val-1", "llm-validator"))
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("root.part", ["g"], criterion("k", "K holds")))
    said = []
    e.emit_info = lambda src, msg, _s=said: _s.append(msg)
    d = Dispatcher(e, agents, runner=lambda *a: {"status": "unparsed"}, consent_runner=lambda *a: {"status": "unparsed"})
    for _ in range(8):
        d.dispatch_once()
        time.sleep(0.5)
    assert "root.part" in {str(x) for x in e.parking.parked_executions()}     # parked by reports that came, unread
    assert (e.paused() or {}).get("place") == "e3-linux", ("the issuer's dead place stopped nothing", said)
    assert any("the issuer's turn on parked was not answered" in m for m in said), said
    _, not_before, _ = d._issuer_attempts["root.part#0#0#parked"]
    assert not_before - time.monotonic() < 5, "the parked node's question waits past the place's return"
    asked = []
    monkeypatch.setattr(I, "settle", lambda en, ag, t, q, a, v: asked.append((str(t), q, a)) or {"status": "gone"})
    docker.up = True
    e.lift_the_system_stop(time.time())
    time.sleep(1.2)
    d.dispatch_once()
    time.sleep(0.3)
    assert ("root.part", "parked", "exec-1") in asked, asked
    e.stop()


def test_only_the_system_s_stop_is_started_by_the_probe(tmp_path):
    """A person's stop over the place's is the person's; a place stop over a limit stop starts only when both are gone;
    a restarted engine re-arms the start from the stop's record."""
    e = make_engine(llm=None)
    e.probe_the_place_with(lambda place: None)
    e.stop_for_the_place("e3-linux", "the execution place e3-linux is unavailable: down")
    e.pause("alice", "mine, over the system's")
    e.lift_the_system_stop(time.time())
    assert e.paused()["by"] == "alice" and "place" not in e.paused()
    e.resume("alice")
    e.stop_for_the_limit("executor", time.time() + 3600)
    e.stop_for_the_place("e3-linux", "the execution place e3-linux is unavailable: down")
    assert e.paused()["place"] == "e3-linux" and e.paused()["until"]
    e.lift_the_system_stop(time.time())
    assert e.paused(), "started while the limit still stood"
    e.resume("x")
    db = str(tmp_path / "p.db")
    e = make_engine(storage=SqliteStorage(db), llm=None)
    e.stop_for_the_place("e3-linux", "down")
    e = make_engine(storage=SqliteStorage(db), llm=None, check_interval=0.1)
    e.probe_the_place_with(lambda place: None)
    e.start()
    t0 = time.time()
    while e.paused() and time.time() - t0 < 5:
        time.sleep(0.1)
    assert e.paused() is None, "a restarted engine never started the project its dead place had stopped"
    e.stop()


def test_a_scope_validation_that_met_the_dead_place_spends_no_retry_and_parks_nothing(tmp_path, monkeypatch):
    """The scope's door as the node's: a `PlaceUnavailable` out of its validation (the snapshot's copy or its removal
    in the container) is the place's stop, not a validation that returned no verdict (critic over 849b6f2)."""
    e = make_engine(llm=None)

    def down(*a, **k):
        raise PlaceUnavailable("e3-linux", DOWN)
    d = Dispatcher(e, _agents(tmp_path), scope_validator=down)
    monkeypatch.setattr(e, "scope_members", lambda top: [])
    monkeypatch.setattr(d, "_scope_key", lambda members: "K")
    monkeypatch.setattr(d, "_give_back", lambda key, delay: None)
    for _ in range(2):
        d._validate_scope_guarded(TaskId("root"), "K")
    assert not d._retried and "root" not in {str(x) for x in e.parking.parked_validations()}, d._retried
    assert (e.paused() or {}).get("place") == "e3-linux", e.paused()


def test_a_round_the_dead_place_refused_keeps_the_conversation_it_would_continue(tmp_path, monkeypatch):
    """A round cut at its turn cap is continued by the next; a round that never started forgot that conversation."""
    ex, docker = _place(tmp_path, monkeypatch)
    llm = ClaudeCodeProvider("haiku", execution=ex)
    sid = "11111111-2222-3333-4444-555555555555"
    forgot = []
    monkeypatch.setattr(llm, "forget", forgot.append)
    assert llm.run_agent("sys", "packet", ("Read",), cwd=str(tmp_path / "ws"), session=sid) == ""
    assert llm.calls[-1]["ended"] == "unavailable" and not forgot, "the refused round forgot the node's conversation"


def test_a_probe_that_raises_is_a_place_that_does_not_answer_and_the_monitor_lives_on():
    """Raised inside `lift`, the probe ended the monitor's thread: no bound fired again (Inv-5)."""
    e = make_engine(llm=None, check_interval=0.1)
    answer = {"raise": True}

    def probe(place):
        if answer["raise"]:
            raise KeyError("e3-linux")
    e.probe_the_place_with(probe)
    e.stop_for_the_place("e3-linux", "the execution place e3-linux is unavailable: down")
    e.start()
    time.sleep(0.6)
    assert e.paused() and any(x.name == "gfso-timeout-monitor" for x in threading.enumerate()), "the monitor died"
    answer["raise"] = False
    t0 = time.time()
    while e.paused() and time.time() - t0 < 5:
        time.sleep(0.1)
    assert e.paused() is None, "the place answered and the monitor never started the project"
    e.stop()


# ── every door names the place, not a limit (critic over b5f7350, 2026-10-27) ─────────────────────────────────


def _dead_place(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "run", _Docker())
    (tmp_path / "ws").mkdir(exist_ok=True)
    ex = E.ContainerExecution("e3-linux", "img", str(tmp_path / "env"), str(tmp_path / "state"), str(tmp_path / "ws"), "p")
    monkeypatch.setattr(TL, "execution_of", lambda *a, **k: ex)
    return ex


def test_the_validation_door_names_the_place_down(tmp_path, monkeypatch):
    ex = _dead_place(tmp_path, monkeypatch)
    e = make_engine(llm=None)
    e.start()
    T.TOOLS["create_task"](e, "root", {"description": "r", "criteria": [criterion("c", "C")]})
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="x")
    out = TL.TOOLS["validate_result"](e, task_id="root", workdir=str(tmp_path / "ws"),
                                      _llm=ClaudeCodeProvider("haiku", execution=ex))
    assert "execution place e3-linux" in str(out.get("error")) and "usage limit" not in str(out.get("error")), out
    assert e.paused() and e.paused().get("place") == "e3-linux"
    e.stop()


def test_the_planning_door_says_no_plan_was_written_not_that_it_was_unreadable(tmp_path, monkeypatch):
    _dead_place(tmp_path, monkeypatch)
    monkeypatch.setattr(DEC, "_default_llm", lambda model, execution=None: ClaudeCodeProvider(model, execution=execution))
    monkeypatch.setattr(TL, "_work_place_documents", lambda *a, **k: "")
    e = make_engine(llm=None)
    out = TL.TOOLS["auto_decompose"](e, request="build a calculator", root_id="root", depth=1)
    assert out.get("root_id") is None and "execution place e3-linux" in str(out.get("error")), out
    assert "parseable" not in str(out.get("error"))
    assert not any(c.get("parse_failed") for c in out.get("stats") or ())
