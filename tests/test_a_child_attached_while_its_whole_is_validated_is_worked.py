"""A machine signed an AUTO root's PASS while the issuer's answer to a child's `outside` row attached a new part: the gate
admits that PASS at a seam (§12.8), so the root stood DONE over `root.late`, its places cleared under the part's session,
no step offered on it, its only settling exit a cancel — then `complete`. A parent is the AND of its active children."""
import dataclasses
import json
import threading
import time
from types import SimpleNamespace as N

from gfso import issuer as I
from gfso import tools as T
from gfso.core.protocol.procedure import probe_id
from gfso.core.types import AgentId, Mode, Signal, SignalData, State, TaskId
from gfso.delegate import Dispatcher, _auto_validate
from gfso import delegate as DG
from gfso.roster import AgentRegistry
from tests.support import REGISTER, criterion, instrument_passes, make_engine

SEEN = "a subquery in NOT IN (SELECT …) gives NULL"
LATE = {"move": "add_child", "justification": "the goal's SQL has subqueries", "child": {
    "name": "late", "description": "NOT IN over a subquery", "covers": ["g"], "criteria": [
        {"name": "late_ok", "description": "NOT IN gives the SQL answer", "check": [
            {"behaviour": "not in", "command": "check late_ok", "expect": "0"}]}]}}


class _Validator:
    """One validation that passes the node's every criterion on its pinned probes; `first` runs inside it."""

    def __init__(self, e, tid, verdict="PASS", outside=(), first=None):
        self.e, self.tid, self.verdict, self.outside, self.first, self.calls = e, str(tid), verdict, list(outside), first, []

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.calls.append({"duration_ms": 1, "output_tokens": 1})
        if self.first:
            self.first()
        tid, parts = TaskId(self.tid), self.e.parts_procedure(TaskId(self.tid))
        crits = self.e.graph.get_task(tid).spec.criteria
        failed = [c.name for c in crits] if self.verdict == "FAIL" else []
        return "```json\n" + json.dumps({"verdict": self.verdict, "failed_criteria": failed, "outside": self.outside, "per_criterion": [
            {"criterion": c.name, "verdict": self.verdict.lower(), "evidence": "ran it", "behaviours": [f"{c.name} holds"],
             "probe": [{"command": p.command, "expect": p.expect, "behaviour": p.behaviour} for p in c.check or ()]
             + [{"id": probe_id(pc.name, p), "command": p.command, "expect": p.expect, "behaviour": p.behaviour}
                for pc in parts.get(c.name, ()) for p in (pc.check or ())]} for c in crits]}) + "\n```"

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


class _Issuer:
    def __init__(self, answer):
        self.text, self.calls = "```json\n" + json.dumps(answer) + "\n```", []

    def complete(self, prompt, context=""):
        self.calls.append({"duration_ms": 1, "output_tokens": 1})
        return self.text

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def _until(pred, why, timeout=20.0):
    end = time.monotonic() + timeout
    while not pred():
        assert time.monotonic() < end, why
        time.sleep(0.01)


def _delivered_whole(tmp_path):
    """An AUTO root VALIDATING, its one part DONE, the part's verdict carrying an `outside` row: asked of the root's issuer."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    for aid, kind in (("exec-1", "llm-executor"), ("exec-2", "llm-executor"), ("val-1", "llm-validator")):
        agents.register(aid, kind, workdir=str(tmp_path), project="p")
    e.workforce.publish_executor_pool({"exec-1": "p", "exec-2": "p"})
    e.set_mode(Mode.AUTO, None, AgentId("agent"))
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    T.TOOLS["decompose"](e, "root", [{"task_id": "root.kid", "covers": ["g"], "spec": {
        "description": "a part", "criteria": [criterion("k", "K holds")]}}], accepted_risks=REGISTER)
    e.wait_idle()
    Dispatcher(e, agents, runner=lambda *a: None)._publish_the_roster()      # …whose instrument signs for the issuer
    _through_a_seam(e, agents, "root.kid", outside=[{"what": SEEN, "evidence": "printed NULL"}])
    _deliver(e, "root")
    assert I.open_questions(e) == [(TaskId("root"), "outside")], I.open_questions(e)
    return e, agents


def _deliver(e, tid):
    who = str(e.graph.get_task(TaskId(tid)).assignee)
    if e.graph.get_state(TaskId(tid)) == State.OFFERED:
        assert "error" not in (out := T.signal(e, tid, "ACCEPT", who)), out
    assert "error" not in (out := T.signal(e, tid, "DELIVER", who, result=f"{tid} out")), out
    e.wait_idle()


def _through_a_seam(e, agents, tid, **kw):
    _deliver(e, tid)
    assert _auto_validate(e, TaskId(tid), agents, _llm=_Validator(e, tid, **kw)) == "pass"
    e.wait_idle()


def _the_race(e, agents, monkeypatch, verdict="PASS"):
    """One pass starts the root's validation and the issuer's turn; the turn lands its child while the validator runs."""
    landed, out = threading.Event(), {}

    def settle(engine, ag, task_id, question, actor, verbs):
        if "turn" in out:
            return {"status": "gone"}
        out["turn"] = I.issuer_turn(engine, task_id, question, actor, _llm=_Issuer(LATE))
        e.wait_idle()
        landed.set()
        return out["turn"]

    monkeypatch.setattr(I, "settle", settle)
    v = _Validator(e, "root", verdict=verdict, first=lambda: landed.wait(20))

    def validator(engine, task_id, ag, **k):
        out["validated"] = _auto_validate(engine, task_id, ag, _llm=v, **k)
        return out["validated"]

    d = Dispatcher(e, agents, poll=30, runner=lambda *a: None, consent_runner=lambda *a: None, validator_runner=validator)
    started = d.dispatch_once()
    assert "validate:root" in started, started
    _until(lambda: "validated" in out, f"the validation did not end: {out}")
    e.wait_idle()
    assert out["turn"]["status"] == "applied", out
    return d, out


def test_a_part_attached_while_the_validator_ran_is_not_signed_over(tmp_path, monkeypatch):
    e, agents = _delivered_whole(tmp_path)
    try:
        d, out = _the_race(e, agents, monkeypatch)
        assert e.graph.get_state(TaskId("root")) != State.DONE and out["validated"] == "rejected", out
        rec = e.get_exec_verdict(TaskId("root"))
        assert rec["superseded_verdict"] == "PASS" and rec["per_criterion"], "the verdict stays on the record, not signed"
    finally:
        e.stop()


def test_it_is_re_presented_and_comes_again_with_the_part_in_what_is_validated(tmp_path, monkeypatch):
    """What a verdict accepts is the commit DELIVER recorded (§11.3), which holds no later part, so waiting and validating
    that commit again would land the result without it. Inv-8 walked: part PASS → join → root re-delivered → PASS."""
    e, agents = _delivered_whole(tmp_path)
    try:
        d, out = _the_race(e, agents, monkeypatch)
        assert {s["task_id"]: s["action"] for s in e.next_steps()["steps"]}["root"] == "accept"
        T.signal(e, "root", "ACCEPT", str(e.graph.get_task(TaskId("root")).assignee))
        e.wait_idle()
        assert "root.late" in {s["task_id"] for s in e.next_steps()["steps"]}, "a part with no one moving it (Inv-8)"
        _through_a_seam(e, agents, "root.late")
        _until(lambda: not e.joins.joining_nodes(), "its join did not end")
        assert "root" in {s["task_id"] for s in e.next_steps()["steps"]}, "the whole's re-delivery has no one moving it"
        _deliver(e, "root")
        del out["validated"]
        assert "validate:root" in d.dispatch_once()
        _until(lambda: "validated" in out, "the re-delivery was not validated")
        e.wait_idle()
        _until(lambda: not e.joins.joining_nodes(), "the root's join did not end")
        assert out["validated"] == "pass" and e.graph.get_state(TaskId("root")) == State.DONE
        assert sum(a.signal == Signal.DELIVER and not a.rejected for a in e.audit_log(TaskId("root"))) == 2
        assert e.next_steps(TaskId("root"))["complete"] is True and e.next_steps()["complete"] is True
    finally:
        e.stop()


def test_a_part_that_fails_or_is_cancelled_leaves_someone_moving(tmp_path, monkeypatch):
    for how in ("fail", "cancel"):
        tmp = tmp_path / how
        tmp.mkdir()
        e, agents = _delivered_whole(tmp)
        try:
            _the_race(e, agents, monkeypatch)
            T.signal(e, "root", "ACCEPT", str(e.graph.get_task(TaskId("root")).assignee))
            e.wait_idle()
            if how == "fail":
                _deliver(e, "root.late")
                assert _auto_validate(e, TaskId("root.late"), agents, _llm=_Validator(e, "root.late", verdict="FAIL")) == "fail"
                e.wait_idle()
                assert "root.late" in {s["task_id"] for s in e.next_steps()["steps"]}, "its rework"
            else:
                issuer = str(e.graph.issuer_of(TaskId("root.late")))
                assert "error" not in (o := T.signal(e, "root.late", "CANCEL", issuer, reason="off the goal")), o
                e.wait_idle()
                for _ in range(3):
                    if e.graph.get_state(TaskId("root.late")) != State.CANCELLING:
                        break
                    T.signal(e, "root.late", "CONFIRM_CANCEL", str(e.graph.get_task(TaskId("root.late")).assignee), in_flight="none")
                    e.wait_idle()
                assert e.graph.get_state(TaskId("root.late")) == State.ABANDONED
                assert "root" in {s["task_id"] for s in e.next_steps()["steps"]}, "the whole has no one moving it"
        finally:
            e.stop()


def test_a_standing_pass_is_not_replayed_over_a_part_attached_since(tmp_path):
    e, agents = _delivered_whole(tmp_path)
    try:
        instrument_passes(e, TaskId("root"))
        assert I.issuer_turn(e, TaskId("root"), "outside", "agent", _llm=_Issuer(LATE))["status"] == "applied"
        e.wait_idle()
        assert _auto_validate(e, TaskId("root"), agents, _llm=_Validator(e, "root")) == "rejected"
        assert e.graph.get_state(TaskId("root")) == State.OFFERED, "re-presented, not signed"
    finally:
        e.stop()


def test_a_fail_over_open_parts_stays_signed(tmp_path, monkeypatch):
    e, agents = _delivered_whole(tmp_path)
    try:
        _, out = _the_race(e, agents, monkeypatch, verdict="FAIL")
        assert out["validated"] == "fail" and e.graph.get_state(TaskId("root")) == State.REWORKING, out
    finally:
        e.stop()


def test_where_the_system_does_not_issue_it_waits_and_its_bound_hands_it_over(tmp_path, monkeypatch):
    """A person keeps the node's issuer moves; the machine does not sign over them, and a lapse hands the delivery to him."""
    e, agents = _delivered_whole(tmp_path)
    try:
        monkeypatch.setattr(DG, "_system_issues", lambda *a: False)
        _, out = _the_race(e, agents, monkeypatch)
        assert out["validated"] == "rejected" and e.graph.get_state(TaskId("root")) == State.VALIDATING, out
        assert e.get_exec_verdict(TaskId("root"))["verdict"] == "PASS"
        assert "root.late" in {s["task_id"] for s in e.next_steps()["steps"]}, "a part with no one moving it (Inv-8)"
        e.send_signal(SignalData(signal=Signal.TIMEOUT, task_id=TaskId("root")))
        e.wait_idle()
        assert e.graph.get_state(TaskId("root")) == State.ESCALATED
        assert "root" in {s["task_id"] for s in e.next_steps()["steps"]}, "the escalation's decision has no one named"
    finally:
        e.stop()


def _closed_over_an_open_part(tmp_path, monkeypatch):
    """The window past the re-ask: the child lands between the reading and the signature, the seam's gate admits the PASS
    (§12.8), and the root stands DONE over it — the shape of the canon's recovery, a child under a closed parent."""
    e, agents = _delivered_whole(tmp_path)
    cleared = []
    monkeypatch.setattr(DG, "clear_workspaces", lambda en, a, t: cleared.append(str(t.id)))
    d = Dispatcher(e, agents, poll=30, runner=lambda *a: None, consent_runner=lambda *a: None)
    d._rejoined_once = True
    instrument_passes(e, TaskId("root"))
    assert I.issuer_turn(e, TaskId("root"), "outside", "agent", _llm=_Issuer(LATE))["status"] == "applied"
    e.wait_idle()
    assert DG._signal(e, TaskId("root"), Signal.PASS, "val-1")
    e.wait_idle()
    _until(lambda: not e.joins.joining_nodes(), "the root's join did not end")
    time.sleep(0.05)      # the `_join` thread past its clearing, whichever way that went
    assert e.graph.get_state(TaskId("root")) == State.DONE and e.graph.get_state(TaskId("root.late")) != State.DONE
    return e, agents, d, cleared


def test_open_nodes_under_a_passed_root_get_their_steps_and_one_answer(tmp_path, monkeypatch):
    e, agents, d, _ = _closed_over_an_open_part(tmp_path, monkeypatch)
    try:
        whole, scoped = e.next_steps(), e.next_steps(TaskId("root"))
        assert whole["complete"] is False and scoped["complete"] is False, (whole, scoped)
        assert whole["open_nodes"] == scoped["open_nodes"] == ["root.late"]
        assert {s["task_id"] for s in whole["steps"]} == {s["task_id"] for s in scoped["steps"]} == {"root.late"}
        assert e.next_step(TaskId("root"))["task_id"] == "root.late"
        assert d.dispatch_once(), "the step reached nobody"
    finally:
        e.stop()


def test_an_open_node_holds_the_places_and_its_settling_clears_them(tmp_path, monkeypatch):
    e, agents, d, cleared = _closed_over_an_open_part(tmp_path, monkeypatch)
    try:
        assert cleared == [], "cleared under an open part: its uncommitted work went with them"
        d.dispatch_once()
        assert cleared == []
        _through_a_seam(e, agents, "root.late")
        _until(lambda: not e.joins.joining_nodes(), "its join did not end")
        d.dispatch_once()
        assert cleared == ["root"]
        assert e.next_steps()["complete"] is True and e.next_steps(TaskId("root"))["complete"] is True
    finally:
        e.stop()


def test_a_stop_rests_the_containers_and_keeps_the_places_for_the_open_node(tmp_path, monkeypatch):
    e, agents, d, cleared = _closed_over_an_open_part(tmp_path, monkeypatch)
    stops = []
    try:
        monkeypatch.setattr(DG, "execution_of", lambda *a: N(stop=lambda: stops.append(1)))
        monkeypatch.setattr(e, "paused", lambda: {"why": "the user's stop"})
        d.dispatch_once()
        assert stops == [1] and cleared == [], (stops, cleared)
    finally:
        e.stop()


def test_a_node_issued_by_nobody_holds_them_and_is_named_with_no_step(tmp_path, monkeypatch):
    """IDLE has no clock: nothing lapses it. The places wait, the disk's cost, and the answer names it instead of "finished"."""
    e, agents, d, cleared = _closed_over_an_open_part(tmp_path, monkeypatch)
    try:
        real = e.all_tasks()
        kid = e.graph.get_task(TaskId("root.late"))
        monkeypatch.setattr(e, "all_tasks", lambda: [t if t.id != kid.id else dataclasses.replace(kid, state=State.IDLE) for t in real])
        out = e.next_steps()
        assert out["complete"] is False and out["open_nodes"] == ["root.late"] and out["steps"] == [], out
        d.dispatch_once()
        assert cleared == []
    finally:
        e.stop()
