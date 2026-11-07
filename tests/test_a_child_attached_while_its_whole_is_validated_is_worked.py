"""A machine signed an AUTO root's PASS while the issuer's answer to a child's `outside` row attached a new part: the gate
admits that PASS at a seam (§12.8), so the root stood DONE over `root.late`, its places cleared under the part's session,
its only settling exit a cancel — then `complete`, the base without the part. A parent is the AND of its active children:
a machine's PASS reads them in its own step of the log, and the delivery is re-presented; a part's ASSIGN after that step
meets the issuing condition (§12.7) and attaches nothing. Both orders are forced below, around the step itself."""
import json
import threading
import time

import pytest

from gfso import delegate as DG
from gfso import issuer as I
from gfso import tools as T
from gfso.adapters import worktrees as W
from gfso.adapters.llm.stub import StubLLM
from gfso.core.graph.metrics import q_V_reversed
from gfso.core.protocol.procedure import probe_id
from gfso.core.types import AgentId, Mode, Signal, SignalData, State, TaskId
from gfso.core.graph.model import admission_key
from gfso.core.graph.mutations import InvariantViolation
from gfso.core.types import settled_positive
from gfso.core.types.enums import Verdict
from gfso.delegate import Dispatcher, _auto_validate
from gfso.driver import _frontier_line
from gfso.engine import loop
from gfso.inflight import _inflight
from gfso.roster import AgentRegistry
from gfso.sessions import run_executor
from tests import test_one_session_carries_a_scope as S
from tests.support import REGISTER, criterion, instrument_passes, make_engine
from tests.test_a_node_works_in_its_own_place import _Executor, _git, _repo

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
        tid = TaskId(self.tid)
        crits, parts = self.e.graph.get_task(tid).spec.criteria, self.e.parts_procedure(tid)   # …as its packet read them
        if self.first:
            self.first()
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


def _goal(e, tmp_path, split=True):
    e.start()
    e.project_name = "p"
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    for aid, kind in (("exec-1", "llm-executor"), ("exec-2", "llm-executor"), ("val-1", "llm-validator")):
        agents.register(aid, kind, workdir=str(tmp_path), project="p")
    e.workforce.publish_executor_pool({"exec-1": "p", "exec-2": "p"})
    e.set_mode(Mode.AUTO, None, AgentId("agent"))
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    if split:
        T.TOOLS["decompose"](e, "root", [{"task_id": "root.kid", "covers": ["g"], "spec": {
            "description": "a part", "criteria": [criterion("k", "K holds")]}}], accepted_risks=REGISTER)
    e.wait_idle()
    once = Dispatcher(e, agents, runner=lambda *a: None)
    once._publish_the_roster()                                               # …whose instrument signs for the issuer
    e._events._on_transition.remove(once._on_bus)                            # …and no second dispatcher joining beside the test's
    return agents


def _delivered_whole(tmp_path):
    """An AUTO root VALIDATING, its one part DONE, the part's verdict carrying an `outside` row: asked of the root's issuer."""
    e = make_engine(validate_signals=True, state_timeout=0)
    agents = _goal(e, tmp_path)
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


def _the_race(e, agents, verdict="PASS"):
    """The validator is running when a part lands: the signature's own step reads it."""
    out = {}

    def turn():
        out["turn"] = I.issuer_turn(e, TaskId("root"), "outside", "agent", _llm=_Issuer(LATE))
        e.wait_idle()

    out["validated"] = _auto_validate(e, TaskId("root"), agents, _llm=_Validator(e, "root", verdict=verdict, first=turn))
    e.wait_idle()
    assert out["turn"]["status"] == "applied", out
    return None, out


# ── the real route: git, the plan gate on, sessions and joins for real ──

class _Run:
    """An AUTO run in a git base with `l2_gate=1`: the dispatcher's own passes, its sessions fakes that write a file each,
    its validator fake, its issuer's turn real. `complete` said while the part's file is not in the base is a failure."""

    def __init__(self, tmp_path, monkeypatch, split=True):
        self.base = _repo(tmp_path / "ws")
        self.e = e = make_engine(llm=StubLLM(), validate_signals=True)
        self.agents = _goal(e, self.base, split)
        e.set_settings({"l2_gate": "1"}, AgentId("agent"), "the gate as it stands by default; the suite's conftest has it off")
        self.lied, self.turned, self.tmp = [], False, tmp_path
        self.sessions = {"root.kid": ("kid.txt", "the part\n"), "root": ("root.txt", "the whole\n"),
                         "root.late": ("late.txt", "the late part\n")}
        monkeypatch.setattr(DG, "ISSUER_VERBS", I.Verbs(llm=None, busy=_inflight, review=self._review, refine=None))
        monkeypatch.setattr(I, "settle", self._settle)
        self.first, self.verdicts, self.at_done, self.runs, self.over_open = {}, {}, [], 0, []
        self.answer, self.in_turn, self.go, self.validated = None, threading.Event(), threading.Event(), []
        self.go.set()
        e.on_transition(self._at_done)                 # …ahead of the dispatcher's own: a reader before its join is marked
        self.d = Dispatcher(e, self.agents, poll=30, runner=self._execute, consent_runner=self._consent,
                            validator_runner=self._validate)

    def _at_done(self, tid=None, old=None, new=None, signal=None):
        if new == State.DONE:
            self.over_open += [str(k.id) for k in self.e.graph.get_active_children(tid) if not settled_positive(k)]
        if str(tid) == "root" and new == State.DONE:
            self.at_done.append((self.e.graph.get_task(TaskId("root")).reopens, self.e.next_steps(TaskId("root")).get("complete"),
                                 self.d._over(), self.in_base("late.txt")))

    def _review(self, e, node):
        """The record `review_decomposition` would write: no model here."""
        e._graph._storage.store_critique(TaskId(node), json.dumps({
            "node_id": node, "gate_passed": True, "semantic_covered": True, "criteria_verdicts": [], "conflicts": [],
            "model": "test", "ts": "2026-07-19 00:00:00"}))
        t = e.graph.get_task(TaskId(node))
        t.verified = True
        e._graph.save_task(t)
        return {"stats": [{"cost_usd": 0}]}

    def _settle(self, e, agents, tid, question, actor, verbs):
        if question == "plan" and I.review_due(e, tid):
            return I._review(e, tid, verbs)
        if question != "outside":
            return {"status": "gone"}
        if self.answer is None:         # …unread: the validation starts, and the row is the test's to answer when it is about it (`attach`)
            return {"status": "unparsed"}
        if e.graph.get_state(tid) != State.VALIDATING:      # …the turn this file is about: over the delivery
            return {"status": "gone"}
        self.in_turn.set()
        self.go.wait(20)
        return I.issuer_turn(e, tid, question, actor, _llm=_Issuer(self.answer))

    def attach(self):
        assert I.issuer_turn(self.e, TaskId("root"), "outside", "agent", _llm=_Issuer(LATE))["status"] == "applied"
        self.e.wait_idle()
        self.turned = True

    def _execute(self, e, tid, executor, agents):
        name, text = self.sessions[str(tid)]
        self.runs += 1
        text += f"{self.runs}\n"                       # …each session's tree its own, its report's words the same
        return run_executor(e, tid, executor, agents, _llm=_Executor(str(tid), {name: text}))

    def _consent(self, e, tid, executor, agents):
        T.signal(e, str(tid), "ACCEPT", executor)
        return {"status": "accepted"}

    def _validate(self, e, tid, agents, **k):
        self.validated.append((str(tid), len([x for x in e.audit_log(tid) if x.signal == Signal.DELIVER and not x.rejected])))
        row = [{"what": SEEN, "evidence": "printed NULL"}] if str(tid) == "root.kid" else []
        said = self.verdicts.get(str(tid)) or ["PASS"]
        return _auto_validate(e, tid, agents, _llm=_Validator(e, tid, verdict=said.pop(0) if len(said) > 1 else said[0], outside=row,
                                                              first=self.first.pop(str(tid), None)), **k)

    def in_base(self, name):
        return (self.base / name).exists()

    def done(self):
        complete = self.e.next_steps(TaskId("root")).get("complete")
        if complete is True and not self.in_base("late.txt"):
            self.lied.append({t.id: t.state.name for t in self.e.all_tasks()})
        return complete is True and not self.e.joins.joining_nodes()

    def drive(self, until=None, rounds=400):
        S._drive(self.e, self.d, until or self.done, rounds, pause=0.02)
        states = {str(t.id): t.state.name for t in self.e.all_tasks()}
        assert (until or self.done)(), f"not reached: {states}, base {sorted(p.name for p in self.base.iterdir())}"

    def state(self, tid="root"):
        return self.e.graph.get_state(TaskId(tid))


def _the_part_stands_in_the_base(run):
    assert run.lied == [], f"`complete` said over a base without the part: {run.lied}"
    assert run.in_base("late.txt") and run.in_base("kid.txt")
    assert run.e.next_steps()["complete"] is True and run.e.next_steps(TaskId("root"))["complete"] is True
    assert _git(run.base, "log", "--format=%s", "-1").startswith("gfso: root joins the base")


def test_a_part_attached_while_the_validator_ran_reaches_the_base(tmp_path, monkeypatch):
    run = _Run(tmp_path, monkeypatch)
    try:
        run.first["root"] = run.attach
        run.drive()
        assert run.turned and run.e.graph.get_task(TaskId("root")).reopens == 0, "held at the signature, no reopen spent"
        _the_part_stands_in_the_base(run)
    finally:
        run.e.stop()


def _force_around_the_pass(run, monkeypatch, assign_first):
    """The log's one pump, around the root's machine PASS: the issuer's whole turn begins, every read of its admission over
    a VALIDATING root, and its ASSIGN is stepped on one side of that PASS or the other. No clock decides the order."""
    real, armed, turn, ended = loop.process_signal, [1], {}, threading.Event()

    def attach():
        turn.update(I.issuer_turn(run.e, TaskId("root"), "outside", "agent", _llm=_Issuer(LATE)))
        ended.set()

    def step(sd, graph, agents, llm, q, *rest):
        if not (armed and str(sd.task_id) == "root" and sd.signal == Signal.PASS):
            return real(sd, graph, agents, llm, q, *rest)
        armed.clear()
        threading.Thread(target=attach, daemon=True).start()
        while str((other := q.get(timeout=20)).task_id) != "root.late":
            real(other, graph, agents, llm, q, *rest)
            q.task_done()
        if assign_first:
            real(other, graph, agents, llm, q, *rest)
            ended.wait(20)                               # …the admission whole, ahead of the PASS
            real(sd, graph, agents, llm, q, *rest)
        else:
            real(sd, graph, agents, llm, q, *rest)
            real(other, graph, agents, llm, q, *rest)
        q.task_done()

    monkeypatch.setattr(loop, "process_signal", step)
    return armed, turn, ended


def test_an_add_child_stepped_before_the_pass_holds_it_and_the_part_reaches_the_base(tmp_path, monkeypatch):
    run = _Run(tmp_path, monkeypatch)
    armed, turn, ended = _force_around_the_pass(run, monkeypatch, assign_first=True)
    try:
        run.drive()
        assert not armed and ended.is_set() and turn["status"] == "applied", turn
        refused = [a for a in run.e.audit_log(TaskId("root")) if a.signal == Signal.PASS and a.rejected]
        assert refused and "root.late" in refused[0].error, refused
        assert run.over_open == [] and run.e.graph.get_task(TaskId("root")).reopens == 0, run.over_open
        _the_part_stands_in_the_base(run)
    finally:
        run.e.stop()


def test_an_add_child_stepped_after_the_pass_attaches_nothing_and_leaves_no_record(tmp_path, monkeypatch):
    """The issuing condition, in the ASSIGN's own step (§12.7): the turn is refused, nothing of its act stands, and the goal
    is complete without the part — the row it answered unanswered, on the record."""
    run = _Run(tmp_path, monkeypatch)
    armed, turn, ended = _force_around_the_pass(run, monkeypatch, assign_first=False)
    e, root = run.e, TaskId("root")
    try:
        was = []
        real_admit, e._admit = e._admit, lambda *a, **k: (was.append((e._storage.get_critique(admission_key(root)),
                                                                      list(e._storage.get_dep_edges()))), real_admit(*a, **k))[1]
        run.drive(lambda: ended.is_set() and e.next_steps(root).get("complete") is True and not e.joins.joining_nodes())
        assert not armed and turn["status"] == "refused" and "§12.7" in turn["why"], turn
        assert e.graph.get_task(TaskId("root.late")) is None and run.over_open == [] and e.open_nodes() == []
        assert e._storage.get_critique(admission_key(root)) == was[-1][0] and e._storage.get_dep_edges() == was[-1][1]
        assert e.next_steps()["complete"] is True and e.graph.get_task(root).reopens == 0
        assert run.in_base("kid.txt") and run.in_base("root.txt") and not run.in_base("late.txt")
        assert [o["what"] for o in e.outside_the_criteria(root, own=False)] == [SEEN], "the row stands, unanswered"
        assert SEEN in str(e.next_steps(root)["questions_left_standing"]) and SEEN in str(e.next_steps()["questions_left_standing"])
    finally:
        e.stop()


def _issuer_first(tmp_path, monkeypatch, answer):
    """The root delivered with the part's row standing and the issuer's turn held open: no pass starts its validation."""
    run = _Run(tmp_path, monkeypatch)
    run.answer = answer
    run.go.clear()
    run.drive(lambda: run.in_turn.is_set())
    assert run.state() == State.VALIDATING and ("root", 1) not in run.validated
    assert not [s for s in run.d.dispatch_once() if s == "validate:root"] and ("root", 1) not in run.validated
    run.go.set()
    return run


def test_the_issuers_part_comes_before_any_validation_of_the_whole(tmp_path, monkeypatch):
    run = _issuer_first(tmp_path, monkeypatch, LATE)
    try:
        run.drive()
        assert [v for v in run.validated if v[0] == "root"] == [("root", 2)], run.validated
        assert run.over_open == [] and "questions_left_standing" not in run.e.next_steps()
        _the_part_stands_in_the_base(run)
    finally:
        run.e.stop()


def test_nothing_attached_the_delivery_is_validated_as_it_stands(tmp_path, monkeypatch):
    run = _issuer_first(tmp_path, monkeypatch, {"move": "decline", "justification": "NULL there is the SQL's own answer"})
    e, root = run.e, TaskId("root")
    try:
        run.drive(lambda: e.next_steps(root).get("complete") is True and not e.joins.joining_nodes())
        assert [v for v in run.validated if v[0] == "root"] == [("root", 1)], run.validated
        assert "questions_left_standing" not in e.next_steps(root) and e.graph.get_task(TaskId("root.late")) is None
    finally:
        e.stop()


def test_a_question_never_answered_holds_no_validation_and_the_person_hears_it(tmp_path, monkeypatch):
    """A turn that ended leaving it open is the issuer's say: the question goes on at its rate, the validation starts, and a
    goal ending over it says what stood."""
    run = _Run(tmp_path, monkeypatch)
    e, root = run.e, TaskId("root")
    said, emit = [], e.emit_info
    monkeypatch.setattr(e, "emit_info", lambda src, msg: (said.append(msg), emit(src, msg))[1])
    try:
        run.drive(lambda: run.d._over())
        assert ("root", 1) in run.validated and e.graph.get_state(root) == State.DONE
        for out in (e.next_steps(), e.next_steps(root)):
            assert out["complete"] is True and SEEN in str(out["questions_left_standing"]), out
        assert SEEN in _frontier_line(e.next_steps())
        run.d.dispatch_once()
        assert [m for m in said if "the goal is over" in m and SEEN in m], said
    finally:
        e.stop()


def test_a_review_that_moved_nothing_lifts_the_hold_though_it_counts_nothing(tmp_path, monkeypatch):
    """`plan` standing on a VALIDATING whole, its review due, a checker with no readable verdict: `unproductive`, the rate's
    counts both zero. Read off those counts the hold lasted to T_validate; before the hold it validated and signed."""
    e = make_engine(validate_signals=True, state_timeout=0)
    agents, ran, go = _goal(e, tmp_path), threading.Event(), threading.Event()
    _through_a_seam(e, agents, "root.kid")
    _deliver(e, "root")
    e.set_settings({"l2_gate": "1"}, AgentId("agent"), "the gate as it stands by default; the suite's conftest has it off")
    # …the one thing set by hand: what puts `plan` on this node, the rest of the turn real
    monkeypatch.setattr(e, "decomposition_refuted", lambda t: "run review_decomposition(root) first" if str(t) == "root" else None)
    assert I.open_questions(e) == [(TaskId("root"), "plan")] and I.review_due(e, TaskId("root")), I.open_questions(e)

    def review(en, node):
        ran.set()
        go.wait(20)
        return {"stats": [{"cost_usd": 0}]}

    monkeypatch.setattr(DG, "ISSUER_VERBS", I.Verbs(llm=None, busy=_inflight, review=review, refine=None))
    d = Dispatcher(e, agents, poll=30, runner=lambda *a: None, consent_runner=lambda *a: None,
                   validator_runner=lambda *a, **k: "rejected")
    try:
        assert "validate:root" not in d.dispatch_once()
        assert ran.wait(20) and "validate:root" not in d.dispatch_once()
        go.set()
        _until(lambda: "q:root" not in d._seen, "the turn did not end")
        key = I._asked_key(e.graph.get_task(TaskId("root")), "plan")
        assert d._issuer_attempts[key][0] == d._issuer_attempts[key][2] == 0, d._issuer_attempts
        assert (TaskId("root"), "plan") in I.open_questions(e) and "validate:root" in d.dispatch_once()
    finally:
        go.set()
        e.stop()


def test_a_turn_that_never_ends_holds_the_delivery_no_longer_than_its_bound(tmp_path, monkeypatch):
    run = _Run(tmp_path, monkeypatch)
    run.answer, _ = LATE, run.go.clear()
    e, root = run.e, TaskId("root")
    try:
        run.drive(lambda: run.in_turn.is_set())
        e.send_signal(SignalData(signal=Signal.TIMEOUT, task_id=root))
        e.wait_idle()
        assert e.graph.get_state(root) == State.ESCALATED and (root, "escalation") in I.open_questions(e)
    finally:
        run.go.set()
        e.stop()


def test_a_part_that_landed_before_the_validation_began_is_delivered_too(tmp_path, monkeypatch):
    """Attached before the pass read the frontier, the part landed, and a validation of the commit DELIVER recorded, which
    cannot hold it, signed and landed the result without it: re-presented instead, with no such validation paid for."""
    run = _Run(tmp_path, monkeypatch)
    validated, real = [], run._validate

    def counting(e, tid, agents, **k):
        if str(tid) == "root":
            validated.append(len([a for a in e.audit_log(TaskId(tid)) if a.signal == Signal.DELIVER and not a.rejected]))
        return real(e, tid, agents, **k)

    run.d._validate = counting
    one_at_a_time, a_pass, session = threading.Lock(), run.d.dispatch_once, run.d._runner

    def passing():
        with one_at_a_time:
            return a_pass()

    def delivering(e, tid, executor, agents):        # …no pass reads between the root's DELIVER and the turn after it
        if str(tid) != "root" or run.turned:
            return session(e, tid, executor, agents)
        with one_at_a_time:
            out = session(e, tid, executor, agents)
            e.wait_idle()
            run.attach()
            return out

    run.d.dispatch_once, run.d._runner = passing, delivering
    try:
        run.drive()
        assert validated == [2] and run.e.graph.get_task(TaskId("root")).reopens == 0, validated
        _the_part_stands_in_the_base(run)
    finally:
        run.e.stop()


def test_a_second_done_reads_landed_only_when_its_join_says_so(tmp_path, monkeypatch):
    """Sampled in the bus at the DONE itself, ahead of the dispatcher marking its join: `_landed` was the bare id then, so
    a reopened root read `complete` and over, with the base lacking what it was reopened for."""
    run = _Run(tmp_path, monkeypatch)
    e, root = run.e, TaskId("root")
    try:
        run.drive(lambda: e.next_steps(root).get("complete") is True)
        e.reopen(root, e.graph.issuer_of(root))
        e.wait_idle()
        run.drive(lambda: e.graph.get_task(root).reopens == 1 and e.next_steps(root).get("complete") is True
                  and not e.joins.joining_nodes())
        assert [s[0] for s in run.at_done] == [0, 1], run.at_done
        assert run.at_done[1][1] is not True and run.at_done[1][2] is False, run.at_done
    finally:
        e.stop()


def test_a_reopened_pass_its_fresh_run_failed_stands_green_after_its_rework(tmp_path, monkeypatch):
    """`false_positive` is q_V's history. Read as the node's present it held the root `refuted_passes` and NOT COMPLETE for
    good, the directive saying its current verdict is FAIL, over a PASS of this generation that landed."""
    run = _Run(tmp_path, monkeypatch, split=False)
    run.sessions["root"] = ("root.txt", "the whole ")
    run.verdicts["root"] = ["PASS", "FAIL", "PASS"]
    e, root = run.e, TaskId("root")
    try:
        cleared, clear = threading.Event(), DG.clear_workspaces
        monkeypatch.setattr(DG, "clear_workspaces", lambda *a: (clear(*a), cleared.set())[0])
        run.drive(lambda: e.next_steps(root).get("complete") is True and cleared.is_set())
        e.reopen(root, e.graph.issuer_of(root))
        e.wait_idle()
        run.drive(lambda: e.graph.get_task(root).false_positive and e.next_steps(root).get("complete") is True
                  and not e.joins.joining_nodes())
        assert e.refuted_passes() == [] and e.next_steps()["complete"] is True, e.next_steps()
        assert q_V_reversed(e._graph) == ["root"], "the history stands: that pass was found wrong"
        assert run.in_base("root.txt") and (run.base / "root.txt").read_text().endswith(f"{run.runs}\n"), "the rework's tree landed"
    finally:
        e.stop()


def test_landing_again_moves_the_accepted_branch(tmp_path):
    base, ref = _repo(tmp_path / "ws"), "refs/heads/gfso/p/accepted"
    first = W.land(base, ref, None, None)
    assert _git(base, "rev-parse", ref) == first
    (base / "late.txt").write_text("the late part\n")
    _git(base, "add", "-A")
    _git(base, "commit", "-q", "-m", "the whole again")
    second = W.land(base, ref, None, first, _git(base, "rev-parse", "HEAD^{tree}"))
    assert second != first and _git(base, "rev-parse", ref) == second == _git(base, "rev-parse", "HEAD")
    assert _git(base, "show", f"{ref}:late.txt") == "the late part"


# ── its edges ──

def test_nothing_moves_a_refuted_pass_under_auto_and_the_directive_says_so(tmp_path, monkeypatch):
    """Who holds the way back: under AUTO the door refuses it from anyone and nothing in the system makes it. The state
    stands, and it stops the whole-graph frontier, so nothing new starts."""
    e, agents = _delivered_whole(tmp_path)
    monkeypatch.setattr(DG, "clear_workspaces", lambda *a: None)
    d = Dispatcher(e, agents, poll=30, runner=lambda *a: None, consent_runner=lambda *a: None)
    d._rejoined_once = True
    try:
        instrument_passes(e, TaskId("root"))
        assert DG._signal(e, TaskId("root"), Signal.PASS, "val-1")
        e.wait_idle()
        _until(lambda: not e.joins.joining_nodes(), "join")
        rec = dict(e.get_exec_verdict(TaskId("root")), verdict=Verdict.FAIL, failed_criteria=["g"], reopens=0)
        e._graph._storage.store_exec_verdict(TaskId("root"), json.dumps(rec))
        assert e.refuted_passes() == ["root"], "the probe made no refuted pass"
        d.dispatch_once()
        e.wait_idle()
        assert e.graph.get_state(TaskId("root")) == State.DONE and e.graph.get_task(TaskId("root")).reopens == 0
        out = e.next_steps()
        assert out["complete"] is False and out["refuted_passes"] == ["root"] and not out.get("steps"), out
        assert "nothing in the system makes" in out["directive"] and "made without you" not in out["directive"], out
    finally:
        e.stop()


def test_under_auto_no_signature_closes_a_whole_over_a_part_whoever_signs(tmp_path):
    e, agents = _delivered_whole(tmp_path)
    try:
        instrument_passes(e, TaskId("root"))
        assert I.issuer_turn(e, TaskId("root"), "outside", "agent", _llm=_Issuer(LATE))["status"] == "applied"
        e.wait_idle()
        assert "root.late" in str(T.signal(e, "root", "PASS", "agent"))
        assert e.graph.get_state(TaskId("root")) == State.VALIDATING
    finally:
        e.stop()


def test_a_child_that_stands_keeps_its_admission_when_its_sibling_is_refused(tmp_path, monkeypatch):
    """No mode, a seam, a split of two, a holder's PASS stepped between their ASSIGNs: the first child stands under the DONE.
    Taken back, the log would name a split without the child it issued; refused as a defect, as any half-split is said."""
    e = make_engine(validate_signals=True, state_timeout=0)
    real, assigned = loop.process_signal, []

    def step(sd, *rest):
        if str(sd.task_id) in ("n1", "n2") and sd.signal == Signal.ASSIGN:
            assigned.append(str(sd.task_id))
            if len(assigned) == 2:
                real(SignalData(signal=Signal.PASS, task_id=TaskId("kid"), source=AgentId("agent")), *rest)
        real(sd, *rest)

    monkeypatch.setattr(loop, "process_signal", step)
    e.start()
    T.create_task(e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]}, assignee="agent")
    T.decompose(e, "root", [{"task_id": "kid", "assignee": "exec-1", "covers": ["g"],
                             "spec": {"description": "a part", "criteria": [criterion("k", "K")]}}], accepted_risks=REGISTER)
    T.decompose(e, "kid", [{"task_id": "kid.a", "assignee": "agent", "covers": ["k"],
                            "spec": {"description": "below", "criteria": [criterion("a", "A")]}}], accepted_risks=REGISTER)
    e.wait_idle()
    try:
        assert "error" not in (o := T.signal(e, "kid", "ACCEPT", "exec-1")), o
        assert "error" not in (o := T.signal(e, "kid", "DELIVER", "exec-1", result="early")), o
        instrument_passes(e, TaskId("kid"))
        with pytest.raises(InvariantViolation, match="is DONE"):
            T.decompose(e, "kid", [{"task_id": t, "assignee": "agent", "covers": ["k"], "spec": {
                "description": f"part {t}", "criteria": [criterion(f"{t}c", "C")]}} for t in ("n1", "n2")])
        e.wait_idle()
        first, second = assigned[:2]
        assert e.graph.get_state(TaskId("kid")) == State.DONE and e.graph.get_task(TaskId(second)) is None
        assert e.graph.get_state(TaskId(first)) == State.OFFERED
        assert first in json.loads(e._storage.get_critique(admission_key(TaskId("kid"))))[-1]["issued"]
    finally:
        e.stop()


def test_a_holders_signature_lands_where_an_instruments_is_held(tmp_path):
    """Under no mode, at a seam (§12.8): one step, two signers."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]}, assignee="agent")
    T.decompose(e, "root", [{"task_id": "kid", "assignee": "exec-1", "covers": ["g"],
                             "spec": {"description": "a part", "criteria": [criterion("k", "K")]}}], accepted_risks=REGISTER)
    T.decompose(e, "kid", [{"task_id": "kid.a", "assignee": "agent", "covers": ["k"],
                            "spec": {"description": "below", "criteria": [criterion("a", "A")]}}], accepted_risks=REGISTER)
    e.wait_idle()
    e._graph.authorized_validators = {"val-1"}
    try:
        assert "error" not in (o := T.signal(e, "kid", "ACCEPT", "exec-1")), o
        assert "error" not in (o := T.signal(e, "kid", "DELIVER", "exec-1", result="early")), o
        instrument_passes(e, TaskId("kid"))
        why = []
        assert not DG._signal(e, TaskId("kid"), Signal.PASS, "val-1", _why=why) and "kid.a" in why[0], why
        assert e.graph.get_state(TaskId("kid")) == State.VALIDATING
        assert "error" not in (o := T.signal(e, "kid", "PASS", "agent")), o
        e.wait_idle()
        assert e.graph.get_state(TaskId("kid")) == State.DONE and e.passes_over_open_parts() == ["kid"]
    finally:
        e.stop()


def test_a_holder_keeps_his_moves_and_is_named_them(tmp_path):
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    agents.register("exec-1", "llm-executor", workdir=str(tmp_path), project="p")
    T.create_task(e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]}, assignee="agent")
    T.decompose(e, "root", [{"task_id": "kid", "assignee": "exec-1", "covers": ["g"],
                             "spec": {"description": "a part", "criteria": [criterion("k", "K")]}}], accepted_risks=REGISTER)
    T.decompose(e, "kid", [{"task_id": "kid.a", "assignee": "agent", "covers": ["k"],
                            "spec": {"description": "below", "criteria": [criterion("a", "A")]}}], accepted_risks=REGISTER)
    e.wait_idle()
    try:
        assert "error" not in (o := T.signal(e, "kid", "ACCEPT", "exec-1")), o
        assert "error" not in (o := T.signal(e, "kid", "DELIVER", "exec-1", result="early")), o
        instrument_passes(e, TaskId("kid"))
        assert "error" not in (o := T.signal(e, "kid", "PASS", "agent")), o
        e.wait_idle()
        d = Dispatcher(e, agents, poll=30, runner=lambda *a: None, consent_runner=lambda *a: None)
        d.dispatch_once()
        e.wait_idle()
        assert e.graph.get_state(TaskId("kid")) == State.DONE and e.graph.get_task(TaskId("kid")).reopens == 0
        assert e.graph.get_state(TaskId("kid.a")) != State.CANCELLING
        out = e.next_steps(TaskId("kid"))
        assert out["complete"] is False and out["open_nodes"] == ["kid.a"] and "reopen('kid')" in out["directive"], out
    finally:
        e.stop()


def test_a_stale_pass_moves_nothing_of_a_node_no_longer_validating(tmp_path):
    """A PASS arriving after a re-ASSIGN and its ACCEPT, or after a lapse: re-presenting it was a decision no issuer made."""
    def again(e):
        I.issuer_turn(e, TaskId("root"), "outside", "agent", _llm=_Issuer(LATE))
        e.wait_idle()
        DG._represent(e, e.graph.get_task(TaskId("root")), str(e.graph.issuer_of(TaskId("root"))), {"root.late"})
        e.wait_idle()
        T.signal(e, "root", "ACCEPT", str(e.graph.get_task(TaskId("root")).assignee))
        e.wait_idle()

    def lapse(e):
        I.issuer_turn(e, TaskId("root"), "outside", "agent", _llm=_Issuer(LATE))
        e.wait_idle()
        e.send_signal(SignalData(signal=Signal.TIMEOUT, task_id=TaskId("root")))
        e.wait_idle()

    for name, move, state in (("rework", again, State.EXECUTING), ("lapse", lapse, State.ESCALATED)):
        tmp = tmp_path / name
        tmp.mkdir()
        e, agents = _delivered_whole(tmp)
        try:
            out = _auto_validate(e, TaskId("root"), agents, _llm=_Validator(e, "root", first=lambda m=move, en=e: m(en)))
            e.wait_idle()
            t = e.graph.get_task(TaskId("root"))
            assert out == "rejected" and t.state == state, (name, out, t.state)
            assert t.revisions == (1 if name == "rework" else 0), (name, t.revisions)
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


def test_the_verdict_stays_on_the_record_superseded(tmp_path, monkeypatch):
    e, agents = _delivered_whole(tmp_path)
    try:
        _, out = _the_race(e, agents)
        assert e.graph.get_state(TaskId("root")) == State.OFFERED and out["validated"] == "rejected", out
        rec = e.get_exec_verdict(TaskId("root"))
        assert rec["superseded_verdict"] == "PASS" and rec["per_criterion"]
    finally:
        e.stop()


def test_a_fail_over_open_parts_stays_signed(tmp_path, monkeypatch):
    e, agents = _delivered_whole(tmp_path)
    try:
        _, out = _the_race(e, agents, verdict="FAIL")
        assert out["validated"] == "fail" and e.graph.get_state(TaskId("root")) == State.REWORKING, out
    finally:
        e.stop()


def test_where_the_system_does_not_issue_it_waits_and_its_bound_hands_it_over(tmp_path, monkeypatch):
    """A person keeps the node's issuer moves; the machine does not sign over them, and a lapse hands the delivery to him."""
    e, agents = _delivered_whole(tmp_path)
    try:
        monkeypatch.setattr(DG, "_system_issues", lambda *a: False)
        _, out = _the_race(e, agents)
        assert out["validated"] == "rejected" and e.graph.get_state(TaskId("root")) == State.VALIDATING, out
        assert e.get_exec_verdict(TaskId("root"))["verdict"] == "PASS"
        assert "root.late" in {s["task_id"] for s in e.next_steps()["steps"]}, "a part with no one moving it (Inv-8)"
        e.send_signal(SignalData(signal=Signal.TIMEOUT, task_id=TaskId("root")))
        e.wait_idle()
        assert e.graph.get_state(TaskId("root")) == State.ESCALATED
        assert "root" in {s["task_id"] for s in e.next_steps()["steps"]}, "the escalation's decision has no one named"
    finally:
        e.stop()
