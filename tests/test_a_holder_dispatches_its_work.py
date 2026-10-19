"""DISPATCH — how the user-agent performs a node it holds (axis 2; axis 1, the mode, says WHO holds it).

The holder consents and stays the node's executor: Del and every signal are its own (§10.1), and how it performs
inside its own scope has no seam (§10.3). Under dispatch the work runs in a clean session of the project's
registered executor — the holder's hands — which the system starts only AFTER the holder's ACCEPT, in the node's
own place. In its own chat nothing structural keeps the work inside the contract (§16.9 exception 11: a SOLO agent
built the whole task first and posed the root afterwards as a receipt); a session started only after consent does.
All with fake agent runners — no network.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import gfso.delegate as D
import gfso.sessions as S
import gfso.tools as T
import gfso.tools_llm as TL
from gfso.core.graph.model import generation_of_task
from gfso.core.types import AgentId, Mode, Signal, State, TaskId
from gfso.decompose.build import build_graph_live
from gfso.delegate import Dispatcher
from gfso.roster import AgentRegistry
from gfso.config import VALIDATION_CLAIM_TTL
from gfso.core.types.ports import SystemClock
from tests.support import criterion, make_engine, REGISTER


class _LLM:
    """A fake executor session: it records where it ran and what it was told, and delivers."""

    def __init__(self):
        self.cwd, self.packets, self.calls = [], [], []

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.cwd.append(cwd)
        self.packets.append(user)
        self.calls.append({"duration_ms": 1, "output_tokens": 1})
        return "```json\n" + json.dumps({"status": "delivered", "summary": "written and checked: it holds",
                                         "self_validation": "PASS"}) + "\n```"

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def _project(tmp_path, hands="exec-1"):
    """SOLO over one leaf root the user-agent holds; `hands` = the executor that performs it (None: in its chat)."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    for aid, kind in (("exec-1", "llm-executor"), ("val-1", "llm-validator")):
        agents.register(aid, kind, workdir=str(tmp_path), project="p")
    D.publish_the_workforce(e, agents.list())
    e.set_mode(Mode.SOLO, None, AgentId("agent"), hands=hands)
    T.create_task(e, "root", {"description": "the goal", "accepted_risks": REGISTER,
                              "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    return e, agents


def _dispatcher(e, agents, ran: list, llm=None):
    def _run(en, t, ex, ag):
        ran.append((str(t), str(ex)))
        return D.run_executor(en, t, ex, ag, _llm=llm) if llm is not None else {"status": "delivered"}
    return Dispatcher(e, agents, poll=30, runner=_run,
                      validator_runner=lambda en, t, *a, **k: None,
                      consent_runner=lambda en, t, *a, **k: ran.append(("consent", str(t))) or {"status": "x"})


def _pass(e, d, rounds=40):
    for _ in range(rounds):
        d.dispatch_once()
        time.sleep(0.03)
        e.wait_idle()


def _state(e, tid="root"):
    return e.graph.get_task(TaskId(tid)).state


def test_the_hands_never_consent_for_the_holder(tmp_path):
    e, agents = _project(tmp_path)
    ran = []
    _pass(e, _dispatcher(e, agents, ran))
    assert _state(e) == State.OFFERED, "the dispatcher consented in the holder's place (Inv-1)"
    assert ran == [], f"work or a consent session started before the holder's ACCEPT: {ran}"


def test_after_the_holders_accept_its_hands_perform_and_report_in_its_name(tmp_path):
    e, agents = _project(tmp_path)
    ran, llm = [], _LLM()
    d = _dispatcher(e, agents, ran, llm)
    assert TL.TOOLS["signal"](e, "root", "ACCEPT", "agent").get("accepted")
    _pass(e, d)
    assert ran == [("root", "agent")], f"one session, run for the holder: {ran}"
    assert llm.cwd == [str(tmp_path)], "the session runs where the hands work"
    assert _state(e) in (State.VALIDATING, State.DONE)
    deliver = [x for x in e._audit.get_entries() if x.task_id == TaskId("root") and x.signal == Signal.DELIVER]
    assert [str(x.source) for x in deliver] == ["agent"], "the delivery is the holder's, Del unchanged"
    assert str(e.graph.get_task(TaskId("root")).assignee) == "agent"


def test_in_chat_the_holder_performs_and_nothing_is_started(tmp_path):
    e, agents = _project(tmp_path, hands=None)
    ran = []
    d = _dispatcher(e, agents, ran)
    assert TL.TOOLS["signal"](e, "root", "ACCEPT", "agent").get("accepted")
    _pass(e, d)
    assert ran == [] and _state(e) == State.EXECUTING


def test_the_holder_is_told_to_consent_and_then_to_wait_not_to_build(tmp_path):
    e, _ = _project(tmp_path)
    step = lambda: next(s for s in TL.TOOLS["next_steps"](e)["steps"] if s.get("task_id") == "root")
    assert "do not build it yourself" in step()["directive"] and "exec-1" in step()["directive"]
    TL.TOOLS["signal"](e, "root", "ACCEPT", "agent")
    e.wait_idle()
    s = step()
    assert s["mine"] and s["directive"].startswith("PERFORMED BY exec-1"), s["directive"]


def test_in_chat_the_holder_is_told_to_execute(tmp_path):
    e, _ = _project(tmp_path, hands=None)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "agent")
    e.wait_idle()
    s = next(s for s in TL.TOOLS["next_steps"](e)["steps"] if s.get("task_id") == "root")
    assert "PERFORMED BY" not in s["directive"]


def test_the_mode_records_how_the_holder_performs(tmp_path):
    e, _ = _project(tmp_path)
    assert (e.mode()["perform"], e.mode()["hands"]) == ("dispatch", "exec-1")
    assert e.hands_of("agent") == "exec-1" and e.hands_of("exec-1") is None and e.hands_of("someone") is None
    e.set_mode(Mode.SOLO, None, AgentId("agent"), hands=None)
    assert e.mode()["perform"] == "in_chat" and e.hands_of("agent") is None
    e.set_mode(Mode.AUTO, None, AgentId("agent"), hands=None)
    assert "perform" not in e.mode(), "under AUTO the user-agent holds nothing to perform"


def test_a_round_queued_for_a_node_that_is_offered_again_waits_for_the_holder(tmp_path):
    """The round's own guard, apart from the pass that queues it: the node is in OFFERED when the slot comes."""
    e, agents = _project(tmp_path)
    ran = []
    d = _dispatcher(e, agents, ran)
    d._run_guarded(TaskId("root"), "agent", generation_of_task(e.graph.get_task(TaskId("root"))))
    e.wait_idle()
    assert _state(e) == State.OFFERED and ran == []


def _scoped(tmp_path):
    """SOLO-dispatch over a root and two parts judged to fit one session: one session of the hands carries them."""
    e, agents = _project(tmp_path)
    kid = lambda i: {"id": i, "name": i, "description": f"part {i}", "volume": "~40 lines, 2 checks",
                     "fits_one_session": True, "criteria": [criterion(f"{i}_ok", f"{i} holds")]}
    build_graph_live({"name": "g", "root_criteria": [criterion("g", "G holds")], "subtasks": [kid("a"), kid("b")],
                      "mappings": [{"criterion": "g", "child_id": "a"}, {"criterion": "g", "child_id": "b"}],
                      "deps": [], "accepted_risks": REGISTER, "scope": [],
                      "whole_volume": "~80 lines, 5 checks", "whole_fits_one_session": True},
                     "the goal", e, assignee="agent")
    e.wait_idle()
    return e, agents


def test_one_session_of_the_hands_carries_the_holders_scope_only_after_its_consent(tmp_path):
    e, agents = _scoped(tmp_path)
    scoped = []
    d = Dispatcher(e, agents, poll=30, runner=lambda *a, **k: scoped.append("node"),
                   validator_runner=lambda *a, **k: None, consent_runner=lambda *a, **k: {"status": "x"},
                   scope_runner=lambda en, t, ex, ag: scoped.append((str(t), str(ex))) or {"status": "reported"},
                   scope_validator=lambda *a, **k: None)
    assert D.session_scope(e, agents, e.graph.get_task(TaskId("root.a"))) is not None, "the scope is the hands'"
    _pass(e, d, 20)
    assert scoped == [] and all(_state(e, t) == State.OFFERED for t in ("root.a", "root.b"))
    for t in ("root.a", "root.b"):
        assert TL.TOOLS["signal"](e, t, "ACCEPT", "agent").get("accepted"), t
    _pass(e, d, 20)
    # (a session that signals nothing gets its one retry — the fake reports nothing)
    assert scoped and set(scoped) == {("root", "agent")}, scoped


class _Revised(_LLM):
    """The holder revises the contract while its hands work (a move the directive leaves it), then the hands deliver."""

    def __init__(self, e):
        super().__init__()
        self._e = e

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        if not self.calls:
            T.edit_criteria(self._e, "root", [criterion("g2", "G2 holds")], agent="agent", reason="other")
            self._e.wait_idle()
        return super().run_agent(system, user, allowed_tools, cwd, timeout)


def test_a_contract_revised_while_the_hands_work_is_not_consented_to_for_the_holder(tmp_path):
    e, agents = _project(tmp_path)
    d = _dispatcher(e, agents, [], _Revised(e))
    assert TL.TOOLS["signal"](e, "root", "ACCEPT", "agent").get("accepted")
    _pass(e, d, 20)
    log = [x.signal for x in e._audit.get_entries() if x.task_id == TaskId("root") and not x.rejected]
    assert log.count(Signal.ACCEPT) == 1 and Signal.DELIVER not in log, log
    assert _state(e) == State.OFFERED, "the new version waits for the holder's own ACCEPT"


def _signals(e, tid="root"):
    return [(x.signal.name, str(x.source)) for x in e._audit.get_entries() if x.task_id == TaskId(tid) and not x.rejected]


def test_a_session_asked_for_on_an_offered_holders_node_consents_to_nothing(tmp_path):
    e, agents = _project(tmp_path)
    assert D.run_executor(e, TaskId("root"), "agent", agents, _llm=_LLM())["status"] == "not_consented"
    assert ("ACCEPT", "agent") not in _signals(e)


def test_a_revision_between_the_dispatch_and_the_session_is_not_consented_for_the_holder(tmp_path, monkeypatch):
    e, agents = _project(tmp_path)
    assert TL.TOOLS["signal"](e, "root", "ACCEPT", "agent").get("accepted")
    e.wait_idle()
    orig, done = e.accepted_moves, []

    def revised_in_the_window(tid):           # read by the round right before it calls the session
        if not done:
            done.append(1)
            T.edit_criteria(e, "root", [criterion("g2", "G2 holds")], agent="agent", reason="other")
            e.wait_idle()
        return orig(tid)
    monkeypatch.setattr(e, "accepted_moves", revised_in_the_window)
    _pass(e, _dispatcher(e, agents, [], _LLM()), 10)
    assert _signals(e).count(("ACCEPT", "agent")) == 1 and _state(e) == State.OFFERED, _signals(e)


def test_a_member_revised_while_the_scope_place_is_made_is_not_consented_for_the_holder(tmp_path, monkeypatch):
    e, agents = _scoped(tmp_path)
    for t in ("root.a", "root.b"):
        TL.TOOLS["signal"](e, t, "ACCEPT", "agent")
    e.wait_idle()
    orig, done = S._enter_workspace, []

    def ew(*a, **k):
        if not done:
            done.append(1)
            T.edit_criteria(e, "root.a", [criterion("a2", "A2 holds")], agent="agent", reason="other")
            e.wait_idle()
        return orig(*a, **k)
    monkeypatch.setattr(S, "_enter_workspace", ew)

    class _All(_LLM):
        def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
            self.calls.append({"duration_ms": 1, "output_tokens": 1})
            return "```json\n" + json.dumps({"nodes": [{"task_id": t, "status": "delivered", "summary": "ok",
                                                        "self_validation": "PASS"}
                                                       for t in ("root.a", "root.b", "root")]}) + "\n```"
    llm = _All()
    d = Dispatcher(e, agents, poll=30, runner=lambda *a, **k: None, validator_runner=lambda *a, **k: None,
                   consent_runner=lambda *a, **k: {"status": "x"},
                   scope_runner=lambda en, t, ex, ag: S.run_scope_executor(en, t, ex, ag, _llm=llm),
                   scope_validator=lambda *a, **k: None)
    _pass(e, d, 10)
    assert _signals(e, "root.a").count(("ACCEPT", "agent")) == 1, _signals(e, "root.a")


def test_a_superseded_session_neither_runs_beside_the_next_nor_writes_into_its_delivery(tmp_path):
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init",
                                                "--allow-empty"]):
        subprocess.run(["git", "-C", str(tmp_path), *cmd], check=True)
    e, agents = _project(tmp_path)
    assert TL.TOOLS["signal"](e, "root", "ACCEPT", "agent").get("accepted")
    e.wait_idle()
    revised, live, overlap, places = threading.Event(), [], [], []

    class _Slow(_LLM):
        def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
            n = len(places)
            places.append(cwd)
            overlap.append(list(live))
            live.append(n)
            if n == 0:                        # the first version's session outlives its version
                revised.wait(10)
                Path(cwd, "stale_v1.txt").write_text("written after v1 was superseded")
            out = super().run_agent(system, user, allowed_tools, cwd, timeout)
            live.remove(n)
            return out
    d = _dispatcher(e, agents, [], _Slow())
    d.dispatch_once()
    time.sleep(0.3)
    T.edit_criteria(e, "root", [criterion("g2", "G2 holds")], agent="agent", reason="other")
    e.wait_idle()
    assert TL.TOOLS["signal"](e, "root", "ACCEPT", "agent").get("accepted")
    e.wait_idle()
    _pass(e, d, 10)
    revised.set()
    _pass(e, d, 60)
    assert len(places) == 2 and overlap == [[], []], f"sessions overlapped: {overlap}"
    git = lambda *a: subprocess.run(["git", "-C", places[1], *a], capture_output=True, text=True).stdout
    assert "stale_v1.txt" not in git("show", "--stat", "--format=%s", "HEAD"), "v1's writes in v2's delivery"
    assert "superseded" in git("log", "--format=%s", "-3")


def test_a_validation_queued_behind_other_sessions_is_the_systems_wait_not_the_holders_move(tmp_path):
    e, agents = _project(tmp_path)
    started, gate = [], threading.Event()
    d = Dispatcher(e, agents, poll=30, max_concurrent=1, runner=lambda *a, **k: {"status": "x"},
                   validator_runner=lambda en, t, *a, **k: started.append(str(t)) or gate.wait(5),
                   consent_runner=lambda *a, **k: {"status": "x"})
    TL.TOOLS["signal"](e, "root", "ACCEPT", "agent")
    TL.TOOLS["signal"](e, "root", "DELIVER", "agent", result="done; it holds", self_validation="PASS")
    e.wait_idle()
    d._cap.opening.acquire()                          # every slot taken by other nodes' sessions
    try:
        _pass(e, d, 10)
        assert started == [] and _state(e) == State.VALIDATING
        steps = [s for s in TL.TOOLS["next_steps"](e).get("steps") or [] if s.get("task_id") == "root"]
        assert not any(s.get("mine") for s in steps), steps
    finally:
        d._cap.opening.release()
        gate.set()


def test_a_queued_validation_stays_the_systems_wait_however_long_the_queue():
    """The claim TTL is for a claim nobody stands behind; a queued one always has its round behind it."""
    class _Later(SystemClock):
        off = 0.0

        def now(self):
            return super().now() + self.off
    clock = _Later()
    e = make_engine(clock=clock)
    e.start()
    T.create_task(e, "root", {"description": "x", "criteria": [criterion("a")]}, assignee="agent")
    e.wait_idle()
    key = e.claims.queue_validation(TaskId("root"))
    clock.off = VALIDATION_CLAIM_TTL + 1
    assert e.claims.validation_in_flight(TaskId("root"))
    e.claims.dequeue_validation(key)
    assert not e.claims.validation_in_flight(TaskId("root"))
    e.stop()


def test_the_hands_work_again_after_the_holder_rejects_their_dispute(tmp_path):
    """REJECT_CHALLENGE returns the node to work under the same version (§12.4): the round must be free again."""
    class _DisputesFirst(_LLM):
        def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
            if not self.calls:
                self.calls.append({"duration_ms": 1, "output_tokens": 1})
                return "```json\n" + json.dumps({"status": "challenge", "summary": "the probe is defective",
                                                 "reason": "criterion g cannot be met as written"}) + "\n```"
            return super().run_agent(system, user, allowed_tools, cwd, timeout)
    e, agents = _project(tmp_path)
    llm = _DisputesFirst()
    d = _dispatcher(e, agents, [], llm)
    assert TL.TOOLS["signal"](e, "root", "ACCEPT", "agent").get("accepted")
    _pass(e, d, 20)
    assert _state(e) == State.CHALLENGED
    assert TL.TOOLS["signal"](e, "root", "REJECT_CHALLENGE", "agent", justification="g is met as written").get(
        "accepted")
    _pass(e, d, 20)
    assert len(llm.calls) == 2 and _state(e) in (State.VALIDATING, State.DONE), (len(llm.calls), _state(e))


def test_reading_the_graph_tells_the_holder_its_move(tmp_path):
    e, _ = _project(tmp_path)
    nxt = TL.TOOLS["get_graph"](e).get("next", "")
    assert "ACCEPT" in nxt and "do not build it yourself" in nxt, nxt
