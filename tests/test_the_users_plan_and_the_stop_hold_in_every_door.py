"""A plan the user handed in is theirs at every node, and a stop starts nothing — at every door (critic over f622997).

Under AUTO a node of the user's plan takes additions only, as the root's goal does: a re-issued contract keeps its
criteria, an accepted dispute below the root re-pins nothing (a part's expected output re-pinned to what the build
printed contradicted the root's own, GB_sql_database_tne9fg736), and `promote` adds no child to the user's split. A
session that waited for its slot starts nothing once the run is stopped, so `stopped` is not read while one is still to
come; the plan review and the scope validation are in flight for every reader; and a stop the system sets names the
user's way out."""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import gfso.delegate as D
from gfso import issuer as I, tools as T, tools_llm as TL
from gfso.core.types import Mode, TaskId
from gfso.delegate import Dispatcher
from gfso.engine.validation import users_criteria
from gfso.inflight import in_flight
from tests.support import criterion
from tests.test_delegate import _agents
from tests.test_the_mode_decides_who_holds_what import _FakeLLM, _admit, _engine, _kid


def _users_part():
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("root.part", ["g"], criterion("k", "K holds")))
    return e, e.graph.get_task(TaskId("root.part"))


def test_a_reissued_contract_of_the_users_part_keeps_its_criteria():
    e, part = _users_part()
    loose = [{"name": "k", "description": "K, loosened", "check": [
        {"behaviour": "b", "command": "test -d . && echo 0", "expect": "0"}]}]
    assert I.spec_with(part, loose, additions_only=False).criteria[0].description == "K, loosened"
    e.give_users_plan("root")
    assert users_criteria(e.graph, part), "every node of the user's plan is the user's"
    spec = I.spec_with(part, loose, additions_only=users_criteria(e.graph, part))
    assert spec.criteria[0].description == "K holds", "the system adds to the user's part, never rewrites it"
    e.stop()


def test_promote_is_not_offered_into_the_users_plan():
    e, part = _users_part()
    assert "promote" in I.moves_for(e, part, "external")
    e.give_users_plan("root")
    assert "promote" not in I.moves_for(e, part, "external")
    e.stop()


def test_a_session_waiting_for_its_slot_starts_nothing_once_stopped(tmp_path):
    e, _ = _users_part()
    d = Dispatcher(e, _agents(tmp_path, ("exec-1", "llm-executor")), max_concurrent=1)
    d._seen.add("b#round")
    d._cap.opening.acquire()                      # a holds the one slot
    ran, stopped = [], []

    def b():
        with d._slot(d._cap.opening, "b#round") as go:
            (ran if go else stopped).append(1)
    t = threading.Thread(target=b)
    t.start()
    time.sleep(0.2)
    assert not ran, "b waits for the slot"
    TL.TOOLS["stop_project"](e, why="w", by="u")
    d._cap.opening.release()                      # a finished
    t.join(2)
    assert not ran and stopped, "b started nothing after the stop"
    assert "b#round" not in d._seen, "its claim is free: the start dispatches it again"
    assert TL.run_state(e)["state"] == "stopped"
    d._cap.opening.acquire()                      # the slot came back
    d._cap.opening.release()
    e.stop()


def test_the_plan_review_and_the_scope_validation_are_in_flight(monkeypatch):
    e, _ = _users_part()
    assert D.ISSUER_VERBS.review is not TL.review_decomposition
    seen = D._in_flight_as("review_decomposition", lambda engine, node: [w["verb"] for w in in_flight()])(e, "root")
    assert seen == ["review_decomposition"]
    got = []
    monkeypatch.setattr(D, "_which_instrument_validates", lambda *a: "val-1")
    monkeypatch.setattr(D, "_standing_verdicts", lambda *a: {})
    monkeypatch.setattr(D, "validator_workdir", lambda *a, **k: ".")
    monkeypatch.setattr(e, "scope_members", lambda tid: [SimpleNamespace(id="root.part",
                                                                         state=SimpleNamespace(name="VALIDATING"))])
    monkeypatch.setattr(D.T, "validate_scope", lambda *a, **k: got.append([w["verb"] for w in in_flight()])
                        or {"inflight": True})
    D._auto_validate_scope(e, TaskId("root"), SimpleNamespace(get=lambda a: {}))
    assert got == [["validate_scope"]]
    e.stop()


def test_a_stop_the_system_sets_names_the_users_way_out(monkeypatch):
    e, _ = _users_part()
    e.give_users_plan("root")
    monkeypatch.setattr(I, "_still_open", lambda *a: True)
    I.settle(e, None, TaskId("root"), "repair", "exec-1", verbs=None)
    why = e.paused()["why"]
    assert "auto_decompose" in why and "set_mode" in why and "start_project" in why, why
    e.stop()


def test_an_accepted_dispute_does_not_re_pin_a_check_of_the_users_part():
    """Below the root of the user's plan an accepted dispute may only add: re-pinned to what a build printed, a part's
    expected output contradicted the root's and the root failed on it to the ceiling (GB_sql_database_tne9fg736 09:30)."""
    e, part = _users_part()
    e.give_users_plan("root")
    ex = str(part.assignee)
    T.signal(e, "root.part", "ACCEPT", ex)
    T.signal(e, "root.part", "CHALLENGE", ex, reason="criterion k: its check expects the wrong output")
    e.wait_idle()
    (p,) = e.graph.get_task(TaskId("root.part")).spec.criteria[0].check
    llm = _FakeLLM({"decision": "accept", "justification": "the build prints 1", "criteria": [
        {"name": "k", "description": "K holds", "check": [{"behaviour": p.behaviour, "command": p.command,
                                                           "expect": "what the build printed"}]}]})
    out = I.answer_the_challenge(e, TaskId("root.part"), str(e.graph.issuer_of(TaskId("root.part"))), _llm=llm)
    assert out["status"] != "accepted", out
    assert e.graph.get_task(TaskId("root.part")).spec.criteria[0].check[0].expect == p.expect
    e.stop()
