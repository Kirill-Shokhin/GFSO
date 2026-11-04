"""A machine signed an AUTO root's PASS while the issuer's answer to a child's `outside` row attached a new part: the gate
admits that PASS at a seam (§12.8), so the root stood DONE over `root.late`, its places cleared under the part's session,
its only settling exit a cancel — then `complete`, the base without the part. A parent is the AND of its active children:
the delivery is re-presented while it is VALIDATING, and a DONE whose claim no longer holds earns it again by REOPEN."""
import json
import threading
import time
from types import SimpleNamespace as N

from gfso import delegate as DG
from gfso import issuer as I
from gfso import tools as T
from gfso.adapters import worktrees as W
from gfso.adapters.llm.stub import StubLLM
from gfso.core.graph.metrics import q_V_reversed
from gfso.core.protocol.procedure import probe_id
from gfso.core.types import AgentId, Mode, Signal, SignalData, State, TaskId
from gfso.delegate import Dispatcher, _auto_validate
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


def _the_race(e, agents, monkeypatch, verdict="PASS"):
    """One pass starts the root's validation and the issuer's turn; the turn lands its child while the validator runs."""
    running, landed, out = threading.Event(), threading.Event(), {}

    def settle(engine, ag, task_id, question, actor, verbs):
        if "turn" in out:
            return {"status": "gone"}
        running.wait(20)      # …a turn landing before the pass reads the frontier leaves no VALIDATE step in that pass
        out["turn"] = I.issuer_turn(engine, task_id, question, actor, _llm=_Issuer(LATE))
        e.wait_idle()
        landed.set()
        return out["turn"]

    monkeypatch.setattr(I, "settle", settle)
    v = _Validator(e, "root", verdict=verdict, first=lambda: (running.set(), landed.wait(20)))

    def validator(engine, task_id, ag, **k):
        out["validated"] = _auto_validate(engine, task_id, ag, _llm=v, **k)
        return out["validated"]

    d = Dispatcher(e, agents, poll=30, max_concurrent=2, runner=lambda *a: None, consent_runner=lambda *a: None,
                   validator_runner=validator)
    started = d.dispatch_once()
    assert "validate:root" in started, started
    _until(lambda: "validated" in out, f"the validation did not end: {out}")
    e.wait_idle()
    assert out["turn"]["status"] == "applied", out
    return d, out


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
        self.first, self.verdicts, self.at_done, self.runs = {}, {}, [], 0
        e.on_transition(self._at_done)                 # …ahead of the dispatcher's own: a reader before its join is marked
        self.d = Dispatcher(e, self.agents, poll=30, runner=self._execute, consent_runner=self._consent,
                            validator_runner=self._validate)

    def _at_done(self, tid=None, old=None, new=None, signal=None):
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
        return {"status": "gone"}       # …the `outside` question is the test's to answer, at the moment it is about (`attach`)

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


def test_a_part_attached_past_the_re_ask_reaches_the_base_through_a_reopen(tmp_path, monkeypatch):
    """The window between the reading and the signature: the root closes over the part, lands without it, and earns its
    verdict again by §12.14; the places stand through it (a clearing took a session's uncommitted work)."""
    run = _Run(tmp_path, monkeypatch)
    real, armed = DG._signal, []

    def signing(e, tid, sig, source, **kw):
        if str(tid) == "root" and sig == Signal.PASS and not armed:
            armed.append(1)
            run.attach()
        return real(e, tid, sig, source, **kw)

    monkeypatch.setattr(DG, "_signal", signing)
    cleared, clear = [], DG.clear_workspaces
    monkeypatch.setattr(DG, "clear_workspaces", lambda e, a, t: (
        cleared.append({k.id: k.state.name for k in e.all_tasks()}), clear(e, a, t))[1])
    try:
        run.drive()
        assert armed and run.e.graph.get_task(TaskId("root")).reopens == 1
        _the_part_stands_in_the_base(run)
        assert cleared and all(set(c.values()) <= {"DONE", "ABANDONED"} for c in cleared), cleared
    finally:
        run.e.stop()


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
    the reopened root read `complete` and over, with the base lacking what it was reopened for."""
    run = _Run(tmp_path, monkeypatch)
    real, armed = DG._signal, []

    def signing(e, tid, sig, source, **kw):
        if str(tid) == "root" and sig == Signal.PASS and not armed:
            armed.append(1)
            run.attach()
        return real(e, tid, sig, source, **kw)

    monkeypatch.setattr(DG, "_signal", signing)
    try:
        run.drive()
        assert [s[0] for s in run.at_done] == [0, 1], run.at_done
        assert run.at_done[1][1] is not True and run.at_done[1][2] is False, run.at_done
        _the_part_stands_in_the_base(run)
    finally:
        run.e.stop()


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
        DG._earn_again(e, e.graph.get_task(root), "the test's reason")
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

def _closed_over_a_part(tmp_path, monkeypatch, reopens=0):
    """The root DONE over an open part, as the window past the re-ask leaves it."""
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
    t = e.graph.get_task(TaskId("root"))
    t.reopens = reopens
    e._graph.save_task(t)
    assert t.state == State.DONE and e.graph.get_state(TaskId("root.late")) != State.DONE
    return e, agents, d, cleared


def test_both_ways_of_asking_answer_what_is_open(tmp_path, monkeypatch):
    e, agents, d, _ = _closed_over_a_part(tmp_path, monkeypatch)
    try:
        for out in (e.next_steps(), e.next_steps(TaskId("root"))):
            assert out["complete"] is False and out["open_nodes"] == ["root.late"] and out["steps"] == [], out
            assert "made without you" in out["directive"], out["directive"]
    finally:
        e.stop()


def test_the_system_reopens_it_and_the_places_stand(tmp_path, monkeypatch):
    e, agents, d, cleared = _closed_over_a_part(tmp_path, monkeypatch)
    said = []
    emit = e.emit_info
    monkeypatch.setattr(e, "emit_info", lambda src, msg: (said.append(msg), emit(src, msg))[1])
    try:
        d.dispatch_once()
        e.wait_idle()
        assert e.graph.get_state(TaskId("root")) == State.OFFERED and e.graph.get_task(TaskId("root")).reopens == 1
        assert cleared == []
        assert [m for m in said if "reopened by its issuer" in m and "root.late" in m], said
        assert "root" in {s["task_id"] for s in e.next_steps()["steps"]}
    finally:
        e.stop()


def test_a_reopen_refused_cancels_the_part_and_complete_says_so(tmp_path, monkeypatch):
    e, agents, d, cleared = _closed_over_a_part(tmp_path, monkeypatch, reopens=1)
    said = []
    emit = e.emit_info
    monkeypatch.setattr(e, "emit_info", lambda src, msg: (said.append(msg), emit(src, msg))[1])
    try:
        d._consent = lambda *a: {"status": "accepted"}
        d.dispatch_once()
        e.wait_idle()
        assert e.graph.get_state(TaskId("root")) == State.DONE and [m for m in said if "stands final" in m], said
        reason = [a for a in e.audit_log(TaskId("root.late")) if a.signal == Signal.CANCEL and not a.rejected]
        assert reason, "no one moved the part"
        for _ in range(50):
            if e.graph.get_state(TaskId("root.late")) == State.ABANDONED:
                break
            d.dispatch_once()
            e.wait_idle()
            time.sleep(0.02)
        assert e.graph.get_state(TaskId("root.late")) == State.ABANDONED
        for out in (e.next_steps(), e.next_steps(TaskId("root"))):
            assert out["complete"] is True and out["cancelled_after_the_close"] == ["root.late"], out
        d.dispatch_once()
        assert cleared == ["root"], "held by the open part, cleared once it settled"
    finally:
        e.stop()


def test_a_refuted_pass_under_auto_is_reopened_and_past_its_count_stands_said(tmp_path, monkeypatch):
    """The directive tells the customer this move is "made without you"; nothing made it."""
    for spent in (0, 1):
        tmp = tmp_path / str(spent)
        tmp.mkdir()
        e, agents = _delivered_whole(tmp)
        d = Dispatcher(e, agents, poll=30, runner=lambda *a: None, consent_runner=lambda *a: None)
        d._rejoined_once = True
        said = []
        emit = e.emit_info
        monkeypatch.setattr(e, "emit_info", lambda src, msg, em=emit, s=said: (s.append(msg), em(src, msg))[1])
        monkeypatch.setattr(DG, "clear_workspaces", lambda *a: None)
        try:
            instrument_passes(e, TaskId("root"))
            assert DG._signal(e, TaskId("root"), Signal.PASS, "val-1")
            e.wait_idle()
            _until(lambda: not e.joins.joining_nodes(), "join")
            t = e.graph.get_task(TaskId("root"))
            t.reopens = spent
            e._graph.save_task(t)
            rec = dict(e.get_exec_verdict(TaskId("root")), verdict="FAIL", failed_criteria=["g"], reopens=spent)
            e._graph._storage.store_exec_verdict(TaskId("root"), json.dumps(rec))
            assert e.refuted_passes() == ["root"], "the probe made no refuted pass"
            d.dispatch_once()
            e.wait_idle()
            if spent:
                assert e.graph.get_state(TaskId("root")) == State.DONE and [m for m in said if "stands final" in m], said
                assert e.next_steps()["complete"] is False, "a refuted final pass is not called complete"
            else:
                assert e.graph.get_state(TaskId("root")) == State.OFFERED and e.graph.get_task(TaskId("root")).reopens == 1
        finally:
            e.stop()


def test_no_reopen_starts_beside_a_clearing_still_running(tmp_path, monkeypatch):
    e, agents, d, _ = _closed_over_a_part(tmp_path, monkeypatch)
    try:
        monkeypatch.setattr(DG, "in_flight", lambda: [{"project": "p", "verb": "clear_workspaces"}])
        d.dispatch_once()
        assert e.graph.get_state(TaskId("root")) == State.DONE
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


def test_a_stop_starts_no_reopen_and_rests_the_containers_keeping_the_places(tmp_path, monkeypatch):
    e, agents, d, cleared = _closed_over_a_part(tmp_path, monkeypatch)
    stops = []
    try:
        monkeypatch.setattr(DG, "execution_of", lambda *a: N(stop=lambda: stops.append(1)))
        monkeypatch.setattr(e, "paused", lambda: {"why": "the user's stop"})
        d.dispatch_once()
        assert stops == [1] and cleared == [] and e.graph.get_state(TaskId("root")) == State.DONE, (stops, cleared)
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
        _, out = _the_race(e, agents, monkeypatch)
        assert e.graph.get_state(TaskId("root")) == State.OFFERED and out["validated"] == "rejected", out
        rec = e.get_exec_verdict(TaskId("root"))
        assert rec["superseded_verdict"] == "PASS" and rec["per_criterion"]
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
