"""A task's criteria are a finite NONEMPTY set of decidable predicates (§2.2) — and the engine held it nowhere.

Measured (spreadsheet_engine, AUTO, every role on one small model, 2026-10-11): the plan author's fold failed to
parse, its retry answered `{}`, and `auto_decompose` built a root with `criteria: []`. A system executor took it,
delivered, and the delivery waited in VALIDATING for a verdict over nothing until the clock escalated it; the
reply had said "the gate will refuse execution". Four defects, one per test group: the packet was admitted, the
gate passed over the empty set, the empty authoring was built, and the reply promised a refusal no gate makes.
"""
from __future__ import annotations

import dataclasses
import json

import pytest

import gfso.tools as T
import gfso.tools_llm as TL
from gfso import decompose as D
from gfso.core.types import AgentId, Criteria, Mode, Signal, SignalData, Spec, TaskId
from gfso.core.handlers.structural import check_procedure
from gfso.decompose.extract import extract_spec
from tests.support import REGISTER, criterion, emptied, instrument_passes, make_engine, pinned
from tests.test_an_edge_is_not_deleted_by_omission import _a_producer_and_a_consumer


def _engine(mode=None):
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.workforce.publish_executor_pool({"exec-1": "p", "exec-2": "p"})
    if mode is not None:
        e.set_mode(mode, None, AgentId("agent"))
    return e


# === 1. the admission: no door installs a packet over no criteria ===

def test_an_assign_over_no_criteria_is_refused_by_name_and_lifted_by_typing_one():
    e = _engine()
    out = T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [], "accepted_risks": REGISTER})
    assert out.get("error") and "§2.2" in out["error"], out
    assert e.graph.get_task(TaskId("root")) is None, "a packet over no criteria was installed"
    # the lift is the issuer's own move: the same call, with a criterion typed
    out = T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")],
                                             "accepted_risks": REGISTER})
    assert not out.get("error"), out
    assert [c.name for c in e.graph.get_task(TaskId("root")).spec.criteria] == ["g"]
    e.stop()


def test_a_revision_that_empties_the_contract_is_refused_and_one_that_keeps_a_criterion_is_not():
    e = _engine()
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")],
                                       "accepted_risks": REGISTER})
    e.wait_idle()
    out = TL.TOOLS["edit_criteria"](e, "root", [], "agent")
    assert out.get("error") and "§2.2" in out["error"], out
    assert [c.name for c in e.graph.get_task(TaskId("root")).spec.criteria] == ["g"]
    out = TL.TOOLS["edit_criteria"](e, "root", [criterion("h", "H holds")], "agent")
    assert not out.get("error"), out
    assert [c.name for c in e.graph.get_task(TaskId("root")).spec.criteria] == ["h"]
    e.stop()


def test_a_raw_assign_lands_nowhere_over_no_criteria():
    """The doors call the admission; a signal sent past them meets the same rule where the packet lands."""
    e = _engine()
    for crit, lands in (((), False), ((Criteria("g", "G holds", check=pinned("g")),), True)):
        tid = TaskId("bare" if not crit else "kept")
        e.send_signal_sync(SignalData(signal=Signal.ASSIGN, task_id=tid, source=AgentId("agent"),
                                      assignee=AgentId("agent"), spec=Spec("the goal", crit)))
        e.wait_idle()
        assert (e.graph.get_task(tid) is not None) is lands, (crit, lands)
        if lands:
            break
    e.stop()


def test_an_accepted_dispute_cannot_answer_with_an_empty_contract():
    e = _engine()
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")],
                                       "accepted_risks": REGISTER}, assignee="exec-1")
    e.wait_idle()
    root = e.graph.get_task(TaskId("root"))

    def answer(criteria):
        e.send_signal_sync(SignalData(signal=Signal.CHALLENGE, task_id=root.id, source=AgentId("exec-1"),
                                      reason="g cannot hold"))
        e.wait_idle()
        e.send_signal_sync(SignalData(signal=Signal.ACCEPT_CHALLENGE, task_id=root.id, source=e.graph.issuer_of(root.id),
                                      new_spec=dataclasses.replace(root.spec, criteria=criteria)))
        e.wait_idle()
        return [c.name for c in e.graph.get_task(root.id).spec.criteria]

    assert answer(()) == ["g"], "the answer to a dispute installed a contract over no criteria"
    assert answer((Criteria("weaker", "less", check=pinned("weaker")),)) == ["weaker"]
    e.stop()


# === 2. the gate: zero criteria is not ready ===

@pytest.mark.parametrize("empty", [True, False])
def test_the_execution_gate_does_not_pass_over_the_empty_set(empty):
    e = _engine()
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")],
                                       "accepted_risks": REGISTER}, assignee="exec-1")
    e.wait_idle()
    if empty:
        emptied(e, "root")
    held = e.execution_blocked_by(TaskId("root"))
    assert bool(held) is empty, held
    if empty:
        assert "§2.2" in held["why"] and "edit_criteria" in held["opens_with"], held
    e.stop()


# === 3. the authoring: an empty plan is an honest error, not an empty root ===

_PLAN = {"name": "Thing", "root_criteria": [criterion("rc", "the whole holds")],
         "subtasks": [{"id": "a", "name": "A", "description": "do A", "criteria": [criterion("a1", "A ok")],
                       "volume": "small", "fits_one_session": True}],
         "mappings": [{"criterion": "rc", "child_id": "a"}], "deps": [],
         "accepted_risks": [{"item": "provider outage", "predictability": "STATISTICAL", "justification": "rare",
                             "invalidation": "seen", "p": 0.01, "impact": "waits"}],
         "denial": {"p": 0.1, "justification": "fixture"}, "whole_volume": "small", "whole_fits_one_session": False}


class _Model:
    """The plan author as measured: every structured call answers `{}` (a parse failure, then a retry that
    parsed as "nothing"), unless a plan is queued for the n-th structured call."""

    def __init__(self, plans=None, gaps=()):
        self.plans, self.gaps, self.calls, self.structured = dict(plans or {}), list(gaps), [], 0

    def complete(self, prompt, context=""):
        self.calls.append({"stage": "x", "output_tokens": 1})
        if "Name the obligations of the GOAL" in prompt:
            return "```json\n" + json.dumps({"gaps": [{"obligation": g, "admits": "a result that ignores it"}
                                                      for g in self.gaps]}) + "\n```"
        return "ALREADY-COVERED" if "CURRENT DECOMPOSITION" in prompt else "holes"

    def complete_structured(self, system, user, schema):
        self.structured += 1
        self.calls.append({"output_tokens": 1, "parse_failed": self.structured not in self.plans})
        return self.plans.get(self.structured, {})


def _auto(monkeypatch, model, request="ship the spreadsheet engine"):
    monkeypatch.setattr(D, "_default_llm", lambda m: model)
    e = _engine(Mode.AUTO)
    return e, TL.auto_decompose(e, request)


def test_an_authoring_that_produced_no_plan_builds_no_root(monkeypatch):
    e, out = _auto(monkeypatch, _Model())
    assert e.graph.get_task(TaskId("root")) is None, "a root over no criteria was built and issued"
    assert out.get("error") and "§2.2" in out["error"] and "again" in out["error"], out
    # …and the project is unchanged, so the customer's own call again is the lift
    model = _Model(plans={1: {"name": _PLAN["name"], "add_root_criteria": _PLAN["root_criteria"],
                              "add_subtasks": _PLAN["subtasks"], "add_mappings": _PLAN["mappings"],
                              "add_accepted_risks": _PLAN["accepted_risks"], "denial": _PLAN["denial"]}})
    monkeypatch.setattr(D, "_default_llm", lambda m: model)
    out = TL.auto_decompose(e, "ship the spreadsheet engine")
    assert not out.get("error"), out
    assert [c.name for c in e.graph.get_task(TaskId("root")).spec.criteria] == ["rc"]
    e.stop()


def test_an_empty_authoring_is_retried_within_the_repair_budget(monkeypatch):
    """The fold came back empty; the repair round the admission's refusal opens authors the plan."""
    e, out = _auto(monkeypatch, _Model(plans={2: _PLAN}))
    assert not out.get("error"), out
    assert [c.name for c in e.graph.get_task(TaskId("root")).spec.criteria] == ["rc"]
    e.stop()


# === 4. the reply: "the gate will refuse" only where a gate does ===

def test_the_reply_promises_no_refusal_over_a_root_no_gate_holds(monkeypatch):
    leaf = {k: v for k, v in _PLAN.items() if k not in ("subtasks", "mappings")}
    patch = {"name": leaf["name"], "add_root_criteria": leaf["root_criteria"],
             "add_accepted_risks": leaf["accepted_risks"], "denial": leaf["denial"]}
    e, out = _auto(monkeypatch, _Model(plans={1: patch}, gaps=["empty cells read as zero"]))
    assert out.get("undecided_obligations"), out
    assert not e.graph.get_active_children(TaskId("root"))
    assert e.execution_blocked_by(TaskId("root")) is None
    assert "refuse" not in out["holes_note"], out["holes_note"]
    assert "no split" in out["holes_note"], out["holes_note"]
    e.stop()


@pytest.mark.parametrize("gate", ["1", "0"])
def test_the_reply_names_the_refusal_only_where_the_gate_holds_the_children(monkeypatch, gate):
    monkeypatch.setenv("GFSO_L2_GATE", gate)
    patch = {"name": _PLAN["name"], "add_root_criteria": _PLAN["root_criteria"], "add_subtasks": _PLAN["subtasks"],
             "add_mappings": _PLAN["mappings"], "add_accepted_risks": _PLAN["accepted_risks"],
             "denial": _PLAN["denial"]}
    e, out = _auto(monkeypatch, _Model(plans={1: patch}, gaps=["empty cells read as zero"]))
    assert out.get("undecided_obligations") and not out.get("holes"), out
    kids = e.graph.get_active_children(TaskId("root"))
    held = bool(kids) and all(e.execution_blocked_by(k.id) for k in kids)
    assert held is (gate == "1")
    assert ("refuse" in out["holes_note"]) is held, out["holes_note"]
    e.stop()


# === round 2: a seam decides nothing, and a subtask's contract is the plan's too ===

def test_a_contract_of_seams_alone_is_refused_and_one_with_its_own_criterion_is_not():
    """Measured by probe: `edit_criteria(cons, [])` kept the carried `dep__prod` and the consumer ran to DONE over no
    check — a seam is made true by the producer's PASS and decides nothing about this node's result."""
    e = make_engine()
    e.start()
    _a_producer_and_a_consumer(e)
    out = TL.TOOLS["edit_criteria"](e, "root.cons", [], "agent")
    assert out.get("error") and "§2.2" in out["error"], out
    assert any(not c.depends_on for c in e.graph.get_task(TaskId("root.cons")).spec.criteria)
    out = TL.TOOLS["edit_criteria"](e, "root.cons", [criterion("own", "its own result holds")], "agent")
    assert not out.get("error"), out
    assert {c.name for c in e.graph.get_task(TaskId("root.cons")).spec.criteria} == {"own", "dep__root.prod"}
    e.stop()


def test_the_execution_gate_holds_a_node_of_seams_alone():
    e = make_engine()
    e.start()
    _a_producer_and_a_consumer(e)
    assert e.execution_blocked_by(TaskId("root.cons")) is None
    emptied(e, "root.cons", seams=True)
    assert [c.name for c in e.graph.get_task(TaskId("root.cons")).spec.criteria] == ["dep__root.prod"]
    assert e.execution_blocked_by(TaskId("root.cons")), "a node deciding nothing of its own was ready to execute"
    e.stop()


@pytest.mark.parametrize("seam", [False, True], ids=["bare", "with-a-seam"])
def test_a_subtask_with_no_criterion_builds_no_plan(monkeypatch, seam):
    """Measured by probe: a subtask authored with `criteria: []` crashed the call after the root was issued, the root
    left OFFERED and unsplit. It is the empty root's defect one level down, and gets the same answer."""
    b = {"id": "b", "name": "B", "description": "do B", "criteria": [], "volume": "small", "fits_one_session": True}
    patch = {"name": _PLAN["name"], "add_root_criteria": _PLAN["root_criteria"], "add_subtasks": _PLAN["subtasks"] + [b],
             "add_mappings": _PLAN["mappings"] + [{"criterion": "rc", "child_id": "b"}],
             "add_deps": [{"from": "a", "to": "b", "glue": "b reads a"}] if seam else [],
             "add_accepted_risks": _PLAN["accepted_risks"], "denial": _PLAN["denial"]}
    e, out = _auto(monkeypatch, _Model(plans={1: patch}))
    assert out.get("error") and "b" in out["error"] and "§2.2" in out["error"], out
    assert e.graph.get_task(TaskId("root")) is None, "the root was issued over a plan that cannot be admitted"
    e.stop()


def _settled_seams_only(done: bool):
    """Old data: a consumer whose contract holds only its seam — emptied after its ACCEPT, or after its DONE."""
    e = make_engine()
    e.start()
    _a_producer_and_a_consumer(e)

    def sig(tid, s, **kw):
        e.send_signal_sync(SignalData(signal=s, task_id=TaskId(tid), source=AgentId("agent"), **kw))
        e.wait_idle()
    for tid in ("root.prod", "root.cons"):
        sig(tid, Signal.ACCEPT)
        if tid == "root.cons" and not done:
            emptied(e, tid, seams=True)
        sig(tid, Signal.DELIVER, result="made")
        if tid == "root.cons" and not done:
            return e, instrument_passes
        instrument_passes(e, TaskId(tid))
        e.wait_idle()
        sig(tid, Signal.PASS)
    emptied(e, "root.cons", seams=True)
    return e, None


def test_a_verdict_over_seams_alone_is_refused_where_it_lands():
    e, passes = _settled_seams_only(done=False)
    with pytest.raises(ValueError, match="nothing a verdict"):
        passes(e, TaskId("root.cons"))
    e.stop()


def test_a_settled_child_of_seams_alone_neither_blocks_a_refine_nor_holes_its_plan():
    e, _ = _settled_seams_only(done=True)
    cons = e.graph.get_task(TaskId("root.cons"))
    assert cons.state.name == "DONE" and [c.name for c in cons.spec.criteria] == ["dep__root.prod"]
    D._no_plan(extract_spec(e, "root"), e, "root", _Model(), contract_fixed=False)   # no NoPlan
    assert check_procedure(cons).passed
    e.stop()
