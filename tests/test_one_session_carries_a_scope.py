"""A split one session of its executor builds and checks whole is ONE piece of work: one executor session for
the scope, one validation over every node of it, each node's own verdict recorded and signed parts first.

The same task must take the same time as a leaf of a large plan or as a whole project: a 2.6-minute task took
39 to 70 minutes when every piece got its own session, its own validation and its own wait. Within κ — what
one executor session realizes and checks (§3.7) — the executor absorbs the structure and presents one result
(§10.3); the validation at the scope's top runs every node's criteria, so a FAIL still names its node (§4.4).
A node above κ is not a leaf, and its split is owed (§3.7, §11.5). All with fake agent runners — no network.
"""
from __future__ import annotations

import json
import time

import gfso.delegate as D
import gfso.tools as T
import gfso.tools_llm as TL
from gfso.core.protocol.procedure import probe_id
from gfso.core.types import AgentId, Mode, Signal, State, TaskId
from gfso.decompose.build import build_graph_live
from gfso.delegate import Dispatcher
from gfso.roster import AgentRegistry
from gfso.engine.validation import record_stands, split_owed
from gfso.issuer import Verbs, open_questions, settle
from tests.support import criterion, instrument_passes, make_engine, REGISTER

_RISK = REGISTER
_NODES = ("root", "root.a", "root.b")


class _LLM:
    """A fake agent runner answering from a queue — every call is one session, counted."""

    def __init__(self, *texts):
        self._texts = list(texts)
        self.calls, self.packets = [], []

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.packets.append(user)
        self.calls.append({"duration_ms": 1, "output_tokens": 1})
        return self._texts.pop(0)

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def _fenced(payload) -> str:
    return "```json\n" + json.dumps(payload) + "\n```"


def _project(tmp_path, fits=True, mode=Mode.AUTO):
    """AUTO (or `mode`) over a root and two parts with a Dep between them, the split judged to fit one session."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    for aid, kind in (("exec-1", "llm-executor"), ("exec-2", "llm-executor"), ("val-1", "llm-validator")):
        agents.register(aid, kind, workdir=str(tmp_path), project="p")
    D.publish_the_workforce(e, agents.list())
    e.set_mode(mode, None, AgentId("agent"))
    T.create_task(e, "root", {"description": "the goal", "accepted_risks": _RISK,
                              "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    kid = lambda i: {"id": i, "name": i, "description": f"part {i}", "volume": "~40 lines, 2 checks",
                     "fits_one_session": fits, "criteria": [criterion(f"{i}_ok", f"{i} holds")]}
    build_graph_live({"name": "g", "root_criteria": [criterion("g", "G holds")],
                      "subtasks": [kid("a"), kid("b")],
                      "mappings": [{"criterion": "g", "child_id": "a"}, {"criterion": "g", "child_id": "b"}],
                      "deps": [{"from": "a", "to": "b", "glue": "b reads what a wrote"}],
                      "accepted_risks": _RISK, "scope": [],
                      "whole_volume": "~80 lines, 5 checks", "whole_fits_one_session": fits},
                     "the goal", e, assignee=str(e.graph.get_task(TaskId("root")).assignee))
    e.wait_idle()
    return e, agents


def _delivered(*tids) -> str:
    return _fenced({"nodes": [{"task_id": t, "status": "delivered", "summary": f"{t}: written and checked",
                               "self_validation": "PASS"} for t in tids]})


def _entry(tid, crit, verdict="pass") -> dict:
    return {"task_id": tid, "criterion": crit, "verdict": verdict,
            "evidence": "ran it: it holds" if verdict == "pass" else "ran it: it does not hold",
            "behaviours": [f"{crit} holds"], "divergences": [] if verdict == "pass" else ["it does not hold"],
            "probe": [{"command": f"check {crit}", "expect": "it holds", "behaviour": f"{crit} holds"}]}


def _entries(e, t, failing=()) -> list:
    """A node's entries as its validator reports them — each criterion's own probe and, as the packet asks, the
    pinned probes of the parts already DONE that the criterion rests on."""
    def _one(c):
        x = _entry(str(t.id), c.name, "fail" if (str(t.id), c.name) in failing else "pass")
        x["probe"] += [{"id": probe_id(pc.name, p), "command": p.command, "expect": p.expect, "behaviour": p.behaviour}
                       for pc in e.parts_procedure(t.id).get(c.name, ()) for p in pc.check]
        return x
    return [_one(c) for c in t.spec.criteria]


def _report(e, failing=()) -> str:
    """The validator's one report over whatever of the scope waits in VALIDATING."""
    entries = [x for t in e.all_tasks() if t.state == State.VALIDATING for x in _entries(e, t, failing)]
    return _fenced({"verdict": "FAIL" if failing else "PASS", "per_criterion": entries,
                    "failed_criteria": [c for _, c in failing]})


class _Validator(_LLM):
    """A validator that reads the graph when it is called, failing the named criteria on its first call."""

    def __init__(self, e, *rounds):
        super().__init__()
        self._e, self._rounds = e, list(rounds)

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.packets.append(user)
        self.calls.append({"duration_ms": 1, "output_tokens": 1})
        return _report(self._e, self._rounds.pop(0) if self._rounds else ())


def _dispatcher(e, agents, executor, validator, per_node: list):
    return Dispatcher(e, agents, poll=30,
                      runner=lambda en, t, *a, **k: per_node.append(("exec", str(t))),
                      validator_runner=lambda en, t, *a, **k: per_node.append(("validate", str(t))),
                      consent_runner=lambda en, t, *a, **k: per_node.append(("consent", str(t))) or {
                          "status": "not_offered"},
                      scope_runner=lambda en, t, ex, ag: D.run_scope_executor(en, t, ex, ag, _llm=executor),
                      scope_validator=lambda en, t, ag, sign=True: D._auto_validate_scope(en, t, ag, _llm=validator,
                                                                                         sign=sign))


def _drive(e, d, until, rounds=200) -> None:
    for _ in range(rounds):
        d.dispatch_once()
        time.sleep(0.03)
        e.wait_idle()
        if until():
            return


def _states(e) -> dict:
    return {t: e.graph.get_state(TaskId(t)).name for t in _NODES}


def test_a_scope_is_one_session_and_one_validation(tmp_path):
    e, agents = _project(tmp_path)
    assert {str(e.graph.get_task(TaskId(t)).assignee) for t in _NODES} == {"exec-1"}
    executor, per_node = _LLM(_delivered("root.a", "root.b", "root")), []
    validator = _Validator(e)
    d = _dispatcher(e, agents, executor, validator, per_node)
    _drive(e, d, lambda: e.graph.get_state(TaskId("root")) == State.DONE)
    assert _states(e) == {t: "DONE" for t in _NODES}
    assert len(executor.calls) == 1, "one executor session for the whole scope"
    assert len(validator.calls) == 1, "one validation over every node of it"
    assert per_node == [], "no node of the scope got a session, a consent or a validation of its own"
    packet = executor.packets[0]
    assert packet.index("`root.a`") < packet.index("`root.b`") < packet.index("the scope's top")
    for t in _NODES:
        rec = e.get_exec_verdict(TaskId(t))
        assert rec and rec["verdict"] == "PASS" and rec["validator"] == "val-1", (t, rec)
        assert {p["criterion"] for p in rec["per_criterion"]} == {c.name for c in e.graph.get_task(TaskId(t)).spec.criteria}
    e.stop()


def test_a_part_that_fails_is_reworked_with_its_whole_in_one_session_as_a_leaf_would_be(tmp_path):
    """The whole's FAIL through its part is true (Thm 1), and the whole is re-delivered in the same session that
    reworks the part: a failed round costs one session and one validation, as the same task posed as a leaf does —
    one task costs the same wherever the seam falls. Waiting for the part's PASS first cost one more of each. The
    consumer beside the failing producer has no true verdict yet: it is re-presented and re-delivered over the fix —
    it does not wait in VALIDATING across the producer's rework, which outlasted T_validate (critic, 2026-09-28)."""
    e, agents = _project(tmp_path)
    executor = _LLM(_delivered("root.a", "root.b", "root"), _delivered("root.a", "root.b", "root"))
    per_node = []
    validator = _Validator(e, {("root.a", "a_ok")})
    d = _dispatcher(e, agents, executor, validator, per_node)
    _drive(e, d, lambda: e.graph.get_state(TaskId("root.a")) == State.REWORKING
           and e.graph.get_state(TaskId("root")) == State.REWORKING)
    assert _states(e) == {"root": "REWORKING", "root.a": "REWORKING", "root.b": "OFFERED"}
    b = e.graph.get_task(TaskId("root.b"))
    assert b.revisions == 1 and not any(a.signal == Signal.FAIL for a in e.audit_log(b.id)),         "re-presented by its issuer, no FAIL and no round of its budget spent"
    fail = next(a for a in reversed(e.audit_log(TaskId("root"))) if a.signal == Signal.FAIL)
    assert list(fail.failed_criteria) == ["g"], "the whole fails on its own criterion mapped to the failing part"
    _drive(e, d, lambda: e.graph.get_state(TaskId("root")) == State.DONE)
    assert _states(e) == {t: "DONE" for t in _NODES}
    assert len(executor.calls) == 2 and len(validator.calls) == 2 and per_node == [],         "two rounds, two sessions, two validations — the leaf's count"
    assert len([a for a in e.audit_log(TaskId("root")) if a.signal == Signal.FAIL]) == 1
    rework = executor.packets[1]
    assert "a_ok" in rework and "REWORKING" in rework, "the rework session is told what failed and why"
    assert "Already" not in rework.split("`root.b`")[1].split("##")[0], "the re-presented consumer is work again"
    assert "Already" not in rework.split("`root`")[-1].split("##")[0], "the failed whole is work again too"
    e.stop()


def test_a_part_that_fails_again_fails_its_whole_again(tmp_path):
    """Each failed round of the part is a failed round of the whole — as each failing round of a leaf is its own."""
    e, agents = _project(tmp_path)
    executor = _LLM(*[_delivered("root.a", "root.b", "root")] * 3)
    validator = _Validator(e, {("root.a", "a_ok")}, {("root.a", "a_ok")})
    d = _dispatcher(e, agents, executor, validator, [])
    _drive(e, d, lambda: e.graph.get_state(TaskId("root")) == State.DONE)
    assert len(executor.calls) == 3 and len(validator.calls) == 3
    assert len([a for a in e.audit_log(TaskId("root")) if a.signal == Signal.FAIL]) == 2
    e.stop()


def test_a_consumer_beside_a_producer_reworked_in_an_earlier_run_is_not_signed(tmp_path):
    """Its criteria read that output, which is about to change: signed on its own look it was never checked against
    the producer's fix. Held only on producers failing in THIS run, it was (critic, 2026-09-28)."""
    e, agents = _project(tmp_path)
    _drive(e, _dispatcher(e, agents, _LLM(_delivered("root.a", "root.b", "root")), _NeverAnswers(), []),
           lambda: e.graph.get_state(TaskId("root")) == State.VALIDATING, rounds=40)
    e.record_exec_verdict(TaskId("root.a"), "FAIL", ["a_ok"], "val-1", per_criterion=[_entry("root.a", "a_ok", "fail")],
                          require_probe=True)
    assert D._signal(e, TaskId("root.a"), Signal.FAIL, "exec-1", failed_criteria=("a_ok",), reason="a does not hold")
    e.wait_idle()
    D._sign_scope(e, e.graph.get_task(TaskId("root")), {"root.b": {"verdict": "PASS", "failed_criteria": []}}, "val-1", True)
    e.wait_idle()
    assert e.graph.get_state(TaskId("root.b")) == State.OFFERED, "re-presented over its producer's rework, not PASSed"
    e.stop()


def test_a_hand_pass_on_a_whole_whose_part_was_delivered_again_is_refused(tmp_path):
    """The PASS gate reads the record's currency, not only its generation: a holder's PASS on a whole signed over a
    part's rework that broke it was admitted while every surface called the record stale (critic, 2026-09-28)."""
    e, agents = _project(tmp_path)
    _drive(e, _dispatcher(e, agents, _LLM(_delivered("root.a", "root.b", "root")), _NeverAnswers(), []),
           lambda: e.graph.get_state(TaskId("root")) == State.VALIDATING, rounds=40)

    def _pass(t):
        e.wait_idle()
        time.sleep(0.05)                               # past the clock's tick: a tie counts as after (`record_stands`)
        e.record_exec_verdict(TaskId(t), "PASS", [], "val-1", require_probe=True,
                              per_criterion=_entries(e, e.graph.get_task(TaskId(t))))
    _pass("root")
    e.record_exec_verdict(TaskId("root.a"), "FAIL", ["a_ok"], "val-1", per_criterion=[_entry("root.a", "a_ok", "fail")],
                          require_probe=True)
    assert D._signal(e, TaskId("root.a"), Signal.FAIL, "exec-1", failed_criteria=("a_ok",), reason="a does not hold")
    assert D._signal(e, TaskId("root.a"), Signal.DELIVER, "exec-1", result="a fixed", self_validation="PASS")
    for t in ("root.a", "root.b"):
        _pass(t)
        why = []
        assert D._signal(e, TaskId(t), Signal.PASS, "exec-1", _why=why), why
    e.wait_idle()
    why = []
    assert not D._signal(e, TaskId("root"), Signal.PASS, "agent", _why=why)
    assert "no appointed observer has observed this delivery" in why[0], why
    _pass("root")
    assert D._signal(e, TaskId("root"), Signal.PASS, "agent", _why=why), why
    e.stop()


def test_a_scope_is_carried_by_one_session_only_where_an_llm_validator_is_bound(tmp_path):
    """Its deliveries carry no self-check of their own and wait for the scope's one validation: with no instrument
    they waited for nothing, parts stuck in VALIDATING (critic, 2026-09-28)."""
    e, agents = _project(tmp_path)
    d = _dispatcher(e, agents, _LLM(), _LLM(), [])
    part = e.graph.get_task(TaskId("root.a"))
    assert d._session_scope(part) is not None
    agents.unregister("val-1")
    assert d._session_scope(part) is None, "no instrument: the per-node path, whose delivery relays its self-check"
    e.stop()


def test_a_scope_run_is_not_cut_to_the_bound_of_a_node_that_waited_longest(monkeypatch):
    """One run serves every node in it; a top that had waited must not cut a run over fresh deliveries to its own
    remainder (critics, 2026-09-28: 119 s, then 299 s, every verdict ⊥)."""
    left = {"root.a": 3599, "root.b": 3599, "root": 299}
    monkeypatch.setattr(TL, "_validation_cap", lambda t: left[str(t.id)])
    assert TL._scope_cap([(type("T", (), {"id": k})(), "", []) for k in ("root", "root.a", "root.b")]) == 3599


def test_a_split_nobody_judged_keeps_a_session_and_a_validation_per_node(tmp_path):
    e, agents = _project(tmp_path, fits=False)
    assert {str(e.graph.get_task(TaskId(t)).assignee) for t in ("root.a", "root.b")} == {"exec-2"}
    executor, validator, per_node = _LLM(), _LLM(), []
    d = _dispatcher(e, agents, executor, validator, per_node)
    for t in _NODES:
        e.record_session_fit(TaskId(t), "", None)
    _drive(e, d, lambda: ("exec", "root.a") in per_node and ("consent", "root") in per_node, rounds=40)
    assert ("exec", "root.a") in per_node and ("consent", "root") in per_node
    D._signal(e, TaskId("root.a"), Signal.DELIVER, "exec-2", result="a.py written")
    _drive(e, d, lambda: ("validate", "root.a") in per_node, rounds=40)
    assert ("validate", "root.a") in per_node, "its delivery is validated on its own"
    assert executor.calls == [] and validator.calls == [], "no scope session, no scope validation"
    e.stop()


def test_a_node_judged_past_one_session_is_not_delivered_as_a_leaf_until_its_executor_splits_it(tmp_path):
    """Above κ a node is not a leaf and its split is owed (§3.7, §11.5). The refusal falls on the executor's own act,
    the DELIVER, whose lift — his split — is his move (§12.16 (ii)); refusing the issuer's PASS at a seam would leave
    the lift with the counterparty."""
    e, _ = _project(tmp_path, fits=False)
    kid = e.graph.get_task(TaskId("root.a"))
    assert str(e.graph.issuer_of(kid.id)) != str(kid.assignee), "a seam"
    assert D._signal(e, kid.id, Signal.ACCEPT, str(kid.assignee))
    refused = []
    assert not D._signal(e, kid.id, Signal.DELIVER, str(kid.assignee), result="a.py", _why=refused)
    assert "split is owed" in refused[0] and "§3.7" in refused[0] and "auto_decompose" in refused[0]
    assert (e.pass_blocked_by(kid.id) or {}).get("kind") != "split_owed", "the issuer's PASS is not the refused act"
    T.decompose(e, "root.a", [{"task_id": "root.a.x", "spec": {"description": "a first part of a",
                                                               "criteria": [criterion("x_ok", "x holds")]},
                               "covers": ["a_ok"]}], accepted_risks=_RISK)   # admitted whole (§11.5)
    e.wait_idle()
    assert split_owed(e._graph, e.graph.get_task(kid.id)) is None, "the split is the lift"
    e.stop()


def test_a_whole_failed_by_its_part_is_told_so_not_told_its_own_check_failed(tmp_path):
    """The whole's FAIL is true — a whole is not attained while a part fails (Thm 1) — and it cites the criteria
    mapped to that part (Inv-3). What its own check found is not a failure: the rework says so."""
    e, agents = _project(tmp_path)
    executor, per_node = _LLM(_delivered("root.a", "root.b", "root"), _delivered("root.a", "root")), []
    d = _dispatcher(e, agents, executor, _Validator(e, {("root.a", "a_ok")}), per_node)
    _drive(e, d, lambda: len(executor.calls) == 2)
    fail = next(a for a in reversed(e.audit_log(TaskId("root"))) if a.signal == Signal.FAIL)
    assert "root.a" in fail.reason and "Thm 1" in fail.reason
    whole = executor.packets[1].split("the scope's top")[1]
    assert "the validator FAILED" not in whole, "the whole's own check passed: it is not told otherwise"
    assert "g (through `root.a`)" in whole and "re-delivered once those parts have PASSED" in whole
    e.stop()


def test_a_refuted_split_gets_no_session_and_its_repair_is_asked(tmp_path, monkeypatch):
    """The whole fails its own criterion while every part passes: contact refuted the split, whose repair is a
    revision (the re-delivery gate refuses a re-delivery) — no session is spent before it."""
    monkeypatch.setattr(D, "answer_open_questions", lambda *a, **k: [])   # the question, not its answer
    e, agents = _project(tmp_path)
    executor, per_node = _LLM(_delivered("root.a", "root.b", "root"), _delivered("root")), []
    d = _dispatcher(e, agents, executor, _Validator(e, {("root", "g")}), per_node)
    _drive(e, d, lambda: False, rounds=40)
    assert _states(e) == {"root": "REWORKING", "root.a": "DONE", "root.b": "DONE"}
    assert len(executor.calls) == 1, "no session over a split contact refuted"
    assert (TaskId("root"), "repair") in open_questions(e)
    e.stop()


def test_a_block_on_a_node_of_the_same_scope_is_not_signalled(tmp_path):
    """A node of the scope is the session's own work, and a block on it resolves only when it is DONE — which waits
    on the scope's validation, which waits on the blocked node. Measured: the scope stood with nothing to run."""
    e, agents = _project(tmp_path)
    first = _fenced({"nodes": [
        {"task_id": "root.a", "status": "delivered", "summary": "a written", "self_validation": "PASS"},
        {"task_id": "root.b", "status": "blocked", "summary": "", "self_validation": "FAIL",
         "reason": "needs a's file", "blocker_task_ids": ["root.a"]},
        {"task_id": "root", "status": "blocked", "summary": "", "self_validation": "FAIL",
         "reason": "b is blocked", "blocker_task_ids": ["root.b"]}]})
    executor, per_node = _LLM(first, _delivered("root.b", "root")), []
    d = _dispatcher(e, agents, executor, _Validator(e), per_node)
    _drive(e, d, lambda: e.graph.get_state(TaskId("root")) == State.DONE)
    assert _states(e) == {t: "DONE" for t in _NODES}
    assert not any(a.signal == Signal.BLOCK for t in _NODES for a in e.audit_log(TaskId(t)))
    assert len(executor.calls) == 2
    e.stop()


def test_a_node_whose_split_is_owed_gets_no_session_and_the_system_splits_it(tmp_path, monkeypatch):
    """Its DELIVER as a leaf is refused, so a session on it is thrown away (measured: two, then parked). Its split
    is its executor's move, which the system makes with the refine round (question `split`)."""
    monkeypatch.setattr(D, "answer_open_questions", lambda *a, **k: [])   # the question, not its answer
    e, agents = _project(tmp_path, fits=False)
    per_node = []
    d = _dispatcher(e, agents, _LLM(), _LLM(), per_node)
    _drive(e, d, lambda: False, rounds=20)
    assert not any(k == "exec" and t in ("root.a", "root.b") for k, t in per_node), per_node
    assert (TaskId("root.a"), "split") in open_questions(e)
    idle = Verbs(llm=None, busy=None, review=None, refine=lambda en, node: {"subtasks": []})
    assert settle(e, agents, TaskId("root.a"), "split", "exec-2", idle)["status"] == "unproductive",         "a round that split nothing moved nothing: counted and backed off, never progress"
    asked = []

    def _split(en, node):
        asked.append(node)
        T.decompose(en, node, [{"task_id": node + ".x", "covers": ["a_ok"],
                                "spec": {"description": "a first part", "criteria": [criterion("x_ok", "x holds")]}}],
                    accepted_risks=_RISK)
        en.wait_idle()
        return {"subtasks": [{"id": node + ".x"}]}
    out = settle(e, agents, TaskId("root.a"), "split", "exec-2", Verbs(llm=None, busy=None, review=None, refine=_split))
    assert out["status"] == "applied" and asked == ["root.a"], out
    e.stop()


def test_under_a_holder_issuer_the_split_is_still_its_executors_and_no_session_is_spent(tmp_path, monkeypatch):
    """Under a holder issuer (SEMI) the part's split is its EXECUTOR's move (§11.5) — a system executor's, so the
    system's — and it maps onto the holder's contract without re-authoring it (`held_contract`, Inv-1). It was the
    holder's step while the round re-authored the node's criteria; either way no session is spent on a DELIVER that
    would be refused (critic, 2026-09-28)."""
    monkeypatch.setattr(D, "answer_open_questions", lambda *a, **k: [])
    e, agents = _project(tmp_path, fits=False, mode=Mode.SEMI)
    assert str(e.graph.issuer_of(TaskId("root.a"))) == "agent", "the holder issues the parts"
    per_node = []
    _drive(e, _dispatcher(e, agents, _LLM(), _LLM(), per_node), lambda: False, rounds=15)
    assert ("exec", "root.a") not in per_node
    assert (TaskId("root.a"), "split") in open_questions(e), "the split is its executor's — the system's — move"
    e.stop()


class _SaysOneThingDoesAnother(_LLM):
    """A scope report whose verdict and failed list name a criterion its own entries pass."""

    def __init__(self, e):
        super().__init__()
        self._e = e

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.packets.append(user)
        self.calls.append({"duration_ms": 1, "output_tokens": 1})
        return _fenced({**json.loads(_report(self._e)[8:-4]), "verdict": "FAIL", "failed_criteria": ["a_ok"]})


def test_a_scope_report_contradicting_its_own_entries_decides_nothing(tmp_path):
    """The per-node record refuses such a report as ⊥ (Inv-3); read off its entries alone it signed a PASS."""
    e, agents = _project(tmp_path)
    executor, per_node = _LLM(_delivered("root.a", "root.b", "root")), []
    validator = _SaysOneThingDoesAnother(e)
    # …until the refusal is ON THE RECORD, not until the validator was first called: the record lands after the run
    _drive(e, _dispatcher(e, agents, executor, validator, per_node),
           lambda: (e.rejected_report(TaskId("root.a")) or {}).get("defects"), rounds=40)
    assert e.graph.get_state(TaskId("root.a")) == State.VALIDATING and e.graph.get_state(TaskId("root")) == State.VALIDATING
    assert "must be the red set" in str((e.rejected_report(TaskId("root.a")) or {}).get("defects"))
    e.stop()


class _SkipsAPart(_Validator):
    """Leaves one node's criteria out of its first report, so only that node is short of a verdict."""

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        text = super().run_agent(system, user, allowed_tools, cwd, timeout)
        if len(self.calls) > 1:
            return text
        body = json.loads(text[8:-4])
        body["per_criterion"] = [x for x in body["per_criterion"] if x["task_id"] != "root.a"]
        return _fenced(body)


def test_one_parts_missing_verdict_re_buys_only_that_part(tmp_path):
    """A standing record is reused per node while nothing it is built from was delivered again or failed since: the
    part's ⊥ changed no artifact, so the whole's and the sibling's records stand."""
    e, agents = _project(tmp_path)
    executor, per_node = _LLM(_delivered("root.a", "root.b", "root")), []
    validator = _SkipsAPart(e)
    _drive(e, _dispatcher(e, agents, executor, validator, per_node), lambda: e.graph.get_state(TaskId("root")) == State.DONE)
    assert _states(e) == {t: "DONE" for t in _NODES}
    retry = validator.packets[1]
    assert "## Node `root.a`" in retry and "## Node `root` " not in retry and "## Node `root.b`" not in retry
    e.stop()


def test_what_failed_through_parts_is_read_only_for_the_fail_it_was_recorded_with(tmp_path):
    """The attribution is recorded when the scope signs the FAIL, keyed to the generation it opened — a later FAIL of
    another origin (a holder's, by hand) is never re-labelled "failed through its part" (critic, 2026-09-28)."""
    e, agents = _project(tmp_path)
    e.note_failed_through_parts(TaskId("root"), {"g": ["root.a"]})
    assert e.failed_through_parts(TaskId("root")) == {"g": ["root.a"]}
    root = e.graph.get_task(TaskId("root"))
    e.revise(root.id, root.spec, AgentId("agent"), reason=None)          # a new version: another generation
    e.wait_idle()
    assert e.failed_through_parts(TaskId("root")) == {}
    e.stop()


def test_a_wholes_record_does_not_stand_once_a_part_below_it_is_delivered_again(tmp_path):
    """A whole's result is its subtree's artifact: a part re-delivered (or failed) after the whole's record makes that
    record a verdict on a result that no longer stands — it is not current for a signature (critic, 2026-09-28)."""
    e, agents = _project(tmp_path)
    executor = _LLM(_delivered("root.a", "root.b", "root"))
    _drive(e, _dispatcher(e, agents, executor, _NeverAnswers(), []), lambda: e.graph.get_state(TaskId("root")) == State.VALIDATING, rounds=40)
    for t in ("root", "root.b"):
        e.record_exec_verdict(TaskId(t), "PASS", [], "val-1", per_criterion=[
            _entry(t, c.name) for c in e.graph.get_task(TaskId(t)).spec.criteria], require_probe=True)
    assert e.current_exec_verdict(TaskId("root")) is not None
    e.record_exec_verdict(TaskId("root.a"), "FAIL", ["a_ok"], "val-1", per_criterion=[_entry("root.a", "a_ok", "fail")],
                          require_probe=True)
    why = []
    assert D._signal(e, TaskId("root.a"), Signal.FAIL, "exec-1", failed_criteria=("a_ok",), reason="a does not hold",
                     _why=why), why
    e.wait_idle()
    for _ in range(100):                               # the FAIL reaches the log a moment after it is admitted
        if e.current_exec_verdict(TaskId("root")) is None:
            break
        time.sleep(0.02)
    assert e.current_exec_verdict(TaskId("root")) is None, "the part failed after the whole's record"
    assert e.current_exec_verdict(TaskId("root.b")) is None, "b consumes a, which failed after b's record"
    e.stop()


class _NeverAnswers(_LLM):
    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.calls.append({"duration_ms": 1, "output_tokens": 1})
        return ""


def test_a_delivered_node_whose_split_became_owed_is_told_to_split_not_to_be_observed(tmp_path):
    """Its PASS is refused while the split is owed; advising the observation first bought a paid validation and then
    the refusal (critic, 2026-09-28)."""
    e, _ = _project(tmp_path, mode=Mode.SOLO)
    kid = e.graph.get_task(TaskId("root.a"))
    assert str(e.graph.issuer_of(kid.id)) == str(kid.assignee), "internal under SOLO: the divergence binds its signer"
    for sig, kw in ((Signal.ACCEPT, {}), (Signal.DELIVER, {"result": "a.py", "self_validation": "PASS"})):
        why = []
        assert D._signal(e, kid.id, sig, str(kid.assignee), _why=why, **kw), why
    e.wait_idle()
    e.record_session_fit(kid.id, "~2000 lines, 40 checks", False)
    step = next(s for s in T.next_steps(e)["steps"] if s["task_id"] == "root.a")
    assert "split is owed" in step["directive"] and "OBSERVE THIS DELIVERY" not in step["directive"], step
    e.stop()


def test_per_node_reuse_does_not_replay_a_record_that_no_longer_stands(tmp_path):
    """Reuse asks what the gate asks (`record_stands`): read off the generation alone, a PASS over parts delivered
    again since was replayed into a gate that refused it, with no validator run, until the bound passed."""
    e, agents = _project(tmp_path, fits=False)
    for t in _NODES:
        e.record_session_fit(TaskId(t), "", None)
    for t in ("root.a", "root.b", "root"):
        ex = str(e.graph.get_task(TaskId(t)).assignee)
        assert D._signal(e, TaskId(t), Signal.ACCEPT, ex)
        assert D._signal(e, TaskId(t), Signal.DELIVER, ex, result="done", self_validation="PASS")
        e.wait_idle()
        e.record_exec_verdict(TaskId(t), "PASS", [], "val-1", require_probe=True,
                              per_criterion=_entries(e, e.graph.get_task(TaskId(t))))
        if t != "root":
            assert D._signal(e, TaskId(t), Signal.PASS, str(e.graph.issuer_of(TaskId(t))))
            e.wait_idle()
    rec = json.loads(e._graph._storage.get_exec_verdict(TaskId("root")))
    e._graph._storage.store_exec_verdict(TaskId("root"), json.dumps({**rec, "log_at": 0}))   # made before the parts
    assert e.current_exec_verdict(TaskId("root")) is None
    validator = _Validator(e)
    D._auto_validate(e, TaskId("root"), agents, _llm=validator, sign=False)
    assert len(validator.calls) == 1, "validated again, not replayed"
    assert e.current_exec_verdict(TaskId("root")) is not None, "and the fresh record stands"
    e.stop()


def _semi_scope_below_the_holder(tmp_path):
    """SEMI: the holder issues X, and X's split (x1 → x2) is one session of X's executor."""
    e, agents = _project(tmp_path, fits=False, mode=Mode.SEMI)
    kid = lambda i: {"id": i, "name": i, "description": f"part {i}", "volume": "~40 lines, 2 checks",
                     "fits_one_session": True, "criteria": [criterion(f"{i}_ok", f"{i} holds")]}
    a = e.graph.get_task(TaskId("root.a"))
    build_graph_live({"name": "a", "root_criteria": [criterion("a_ok", "a holds")],
                      "subtasks": [kid("x1"), kid("x2")],
                      "mappings": [{"criterion": "a_ok", "child_id": "x1"}, {"criterion": "a_ok", "child_id": "x2"}],
                      "deps": [{"from": "x1", "to": "x2", "glue": "x2 reads x1"}], "accepted_risks": _RISK,
                      "scope": [], "whole_volume": "~80 lines", "whole_fits_one_session": True},
                     "part a", e, root_id="root.a", assignee=str(a.assignee))
    e.record_session_fit(TaskId("root.b"), "~40 lines, 2 checks", True)   # a leaf beside it, not the subject
    e.wait_idle()
    return e, agents


def test_under_semi_the_holder_is_told_the_whole_over_a_failing_part_fails(tmp_path):
    """A whole is not attained while a part fails (Thm 1): that FAIL is true now and is its issuer's step. Listed as
    a wait for the part's rework, the whole sat in VALIDATING past T_validate and escalated (critic, 2026-09-28)."""
    e, agents = _semi_scope_below_the_holder(tmp_path)
    assert str(e.graph.issuer_of(TaskId("root.a"))) == "agent" and e.scope_top(TaskId("root.a.x1")).id == TaskId("root.a")
    run = _delivered("root.a.x1", "root.a.x2", "root.a")
    d = _dispatcher(e, agents, _LLM(run, run), _Validator(e, {("root.a.x1", "x1_ok")}), [])
    _drive(e, d, lambda: e.graph.get_state(TaskId("root.a.x1")) == State.REWORKING, rounds=60)
    assert e.graph.get_state(TaskId("root.a")) == State.VALIDATING
    step = next(s for s in T.next_steps(e)["steps"] if s["task_id"] == "root.a")
    assert "FAIL on a_ok" in step["directive"] and "Thm 1" in step["directive"], step
    assert D._signal(e, TaskId("root.a"), Signal.FAIL, "agent", failed_criteria=("a_ok",), reason="x1 fails")
    e.stop()


def _free_claim(e, tid):
    """The validation slot, once a run the dispatcher started over it has let go — the drive stops at a state, not at
    the end of the runs that state started."""
    until = time.time() + 10
    while (key := e.claims.begin_validation(TaskId(tid))) is None and time.time() < until:
        time.sleep(0.05)
    return key


def test_a_record_is_placed_where_its_run_began_not_where_it_landed(tmp_path):
    """Its verdict is on the artifact as it was when the run began: a footing failed while the run was in flight is
    after the record, which then does not stand (critic, 2026-09-28)."""
    e, agents = _project(tmp_path)
    _drive(e, _dispatcher(e, agents, _LLM(_delivered("root.a", "root.b", "root")), _NeverAnswers(), []),
           lambda: e.graph.get_state(TaskId("root")) == State.VALIDATING, rounds=40)
    key = _free_claim(e, "root")
    e.record_exec_verdict(TaskId("root.a"), "FAIL", ["a_ok"], "val-1", per_criterion=[_entry("root.a", "a_ok", "fail")],
                          require_probe=True)
    assert D._signal(e, TaskId("root.a"), Signal.FAIL, "exec-1", failed_criteria=("a_ok",), reason="a does not hold")
    e.wait_idle()
    e.record_exec_verdict(TaskId("root"), "PASS", [], "val-1", require_probe=True, log_at=key.log_at,
                          per_criterion=[_entry("root", c.name) for c in e.graph.get_task(TaskId("root")).spec.criteria])
    e.claims.end_validation(key)
    assert e.current_exec_verdict(TaskId("root")) is None
    e.stop()


def test_a_run_whose_claim_was_reclaimed_still_records_where_it_began(tmp_path):
    """The place travels with the run: kept in a slot shared by generation, a second run reclaiming it after the TTL
    overwrote the first run's place, and the slow run's PASS stood over a part fixed after it read (critic,
    2026-09-28)."""
    e, agents = _project(tmp_path)
    _drive(e, _dispatcher(e, agents, _LLM(_delivered("root.a", "root.b", "root")), _NeverAnswers(), []),
           lambda: e.graph.get_state(TaskId("root")) == State.VALIDATING, rounds=40)
    slow = _free_claim(e, "root")
    assert D._signal(e, TaskId("root.a"), Signal.FAIL, "exec-1", failed_criteria=("a_ok",), reason="a does not hold")
    e.wait_idle()
    e.claims._val_inflight[slow.key] = e._clock.now() - 10_000             # the slow run outlived the claim's TTL
    fast = e.claims.begin_validation(TaskId("root"))
    assert fast is not None and fast.log_at > slow.log_at
    e.claims.end_validation(fast)
    e.record_exec_verdict(TaskId("root"), "PASS", [], "val-1", require_probe=True, log_at=slow.log_at,
                          per_criterion=[_entry("root", c.name) for c in e.graph.get_task(TaskId("root")).spec.criteria])
    assert e.current_exec_verdict(TaskId("root")) is None, "read before a's FAIL: it does not stand"
    e.stop()


def test_an_undated_record_over_a_footing_stands_only_if_it_refuses(tmp_path):
    """A ledger row from before records carried their place in the log: a FAIL still binds (Inv-2), a PASS costs a
    validation rather than signing over a footing nobody can say did not move."""
    e, _ = _project(tmp_path)
    root = e.graph.get_task(TaskId("root"))
    gen = dict(zip(("iteration", "reopens", "revisions"), (root.iteration, root.reopens, root.revisions)))
    assert record_stands(e._graph, e._audit, root, {"verdict": "FAIL", **gen})
    assert not record_stands(e._graph, e._audit, root, {"verdict": "PASS", **gen})
    e.stop()
