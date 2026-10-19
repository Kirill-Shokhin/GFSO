"""The split's ACCEPTED_RISKS register is its decomposer's, admitted with the split — not a packet field (§9.2, §11.5).

"As the split's attribute, the register is its decomposer Del(t)'s statement about his own split, authored and changed
only with it … A register carried in the task's own fields, a pre-filled one, is task data, not the split's register."
One field carried both, so the decomposer could change his own register only through a revision his issuer made,
re-offering the node — an extra round in AUTO, and in SEMI a move that was not his (sync audit 2026-10-04, A-F6).

CONTROL: route `edit_accepted_risks` by Del back to the revision, or let CHECK-4 read the packet over the split's own
register, or drop the version record — and these go red.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
import gfso.tools_llm as TL
from gfso.core.types import AgentId, Mode, Register, State, TaskId, register_of
from gfso.engine.validation import AdmissionRefused
from tests.support import DENIAL_ENTRY, REGISTER, criterion, make_engine

_RISK = {"item": "the host restarts mid-run", "predictability": "EXTRAORDINARY", "p": 0.01,
         "impact": "the run resumes", "justification": "no precedent here", "invalidation_condition": "one occurs"}


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _issued(lead="lead", worker="worker"):
    """A root issued by `lead` to `worker`, consented to, not yet split."""
    e = make_engine()
    e.start()
    e.assign_task(TaskId("root"), T._spec_from({"description": "goal", "criteria": [criterion("a", "A")]}),
                  AgentId(worker), issuer=AgentId(lead))
    T.signal(e, "root", "ACCEPT", worker)
    return e


def _split(lead="lead", worker="worker"):
    """A root issued by `lead` to `worker`, who splits it — the split admitted whole, its register with it (§11.5)."""
    e = _issued(lead, worker)
    T.decompose(e, "root", [{"task_id": "root.k", "spec": {"description": "k", "criteria": [criterion("k1", "K")]},
                             "assignee": worker, "covers": ["a"]}], accepted_risks=REGISTER)
    e.wait_idle()
    return e


def test_the_decomposer_writes_his_own_register_with_no_revision_and_no_re_offer():
    e = _split()
    T.edit_accepted_risks(e, "root", [_RISK], agent="lead")       # the issuer's word: the packet's pre-fill, a revision
    assert e.graph.get_state(TaskId("root")) == State.OFFERED
    T.signal(e, "root", "ACCEPT", "worker")
    out = T.edit_accepted_risks(e, "root", [_RISK, DENIAL_ENTRY], agent="worker")
    root = e.graph.get_task(TaskId("root"))
    assert root.state == State.EXECUTING, "the decomposer's own register re-offered his node"
    assert [n.item for n in register_of(root).items if not n.denial] == [_RISK["item"]]
    assert [n.item for n in root.spec.accepted_risks] == [_RISK["item"]], "the packet's pre-fill, the issuer's"
    assert "split's register" in out["written_as"]
    # each version on record (Thm 11): the admission's and the edit's, both the decomposer's
    assert [v["by"] for v in e.register_versions(TaskId("root"))] == ["worker", "worker"]
    e.stop()


def test_check_4_reads_the_splits_register_and_not_the_packets_pre_fill():
    """Canon v4.1 §11.5 ("its register — changes only by a re-admission"): CHECK-4 reads the split's register at its
    re-admission, so emptying it is refused naming CHECK-4 whatever the packet's pre-fill holds, and nothing changes."""
    e = _split()
    T.edit_accepted_risks(e, "root", REGISTER, agent="lead")     # a well-formed pre-fill in the packet …
    T.signal(e, "root", "ACCEPT", "worker")
    with pytest.raises(AdmissionRefused, match="CHECK-4"):     # … does not stand for the split's own register
        e.admit_register(TaskId("root"), Register(), AgentId("worker"))
    assert register_of(e.graph.get_task(TaskId("root"))).items == Register(T._accepted_risks_from(REGISTER)).items
    assert e.graph.get_state(TaskId("root.k")) == State.OFFERED, "the refusal touched the issued child"
    # the admission door carries the register with the split
    T.decompose(e, "root", [{"task_id": "root.m", "spec": {"description": "m", "criteria": [criterion("m1", "M")]},
                             "assignee": "worker", "covers": ["a"]}], accepted_risks=REGISTER)
    assert not any(h["check"].startswith("CHECK-4") for h in T.list_holes(e)["holes"])
    e.stop()


def test_nobody_but_the_decomposer_admits_the_splits_register():
    e = _split()
    with pytest.raises(ValueError, match="decomposer"):
        e.admit_register(TaskId("root"), Register(), AgentId("somebody"))
    e.stop()


def test_a_leaf_has_no_register_and_its_executor_cannot_write_one_into_his_own_validation():
    """§9.2: "a leaf's is vacuous". Admitted with no split, an executor's entry landed in the validator's packet for his
    own delivery — "do not fail the node for a gap that lives only here" (critic r4 over A-F6, A2)."""
    e = _split()
    T.decompose(e, "root", [{"task_id": "root.x", "spec": {"description": "x", "criteria": [criterion("x1", "X")]},
                             "assignee": "exec", "covers": ["a"]}], accepted_risks=REGISTER)
    with pytest.raises(ValueError, match="vacuous"):
        e.admit_register(TaskId("root.x"), Register(), AgentId("exec"))
    with pytest.raises(ValueError, match="not the issuer"):           # routed to the packet: the issuer's, refused
        T.edit_accepted_risks(e, "root.x", [_RISK], agent="exec")
    assert register_of(e.graph.get_task(TaskId("root.x"))).items == ()
    e.stop()


def test_a_refused_admission_leaves_no_register_behind():
    """The register rides the admission; refused, the split never stood, so neither does its register (Thm 11 records
    acts that happened) — it was admitted before the per-child guards ran (critic r4 over A-F6, B2).
    Canon v4.1: the node's FIRST split, so no admitted register stands before it either."""
    e = _issued()
    bad = {"task_id": "root.y", "covers": ["a"], "assignee": "worker",
           "spec": {"description": "y", "criteria": [{"name": "y1", "description": "no check pinned"}]}}
    with pytest.raises(ValueError, match="pin no check"):
        T.decompose(e, "root", [bad], accepted_risks=REGISTER)
    assert e.register_versions(TaskId("root")) == []
    e.stop()


def test_a_split_deferred_past_consent_is_authored_then_not_narrowed():
    """§11.5: the executor admits his split "at or after the node's issue". Its first register is how the split was
    authored; read against the register before consent it showed as a narrowing (critic r4 over A-F6).
    Canon v4.1: a split is admitted with its register (§11.5), so the authoring is the node's FIRST split; the later
    register is a re-admission (§11.5) its battery passes, and only then is it read as risks added."""
    e = _issued()
    T.decompose(e, "root", [{"task_id": "root.z", "spec": {"description": "z", "criteria": [criterion("z1", "Z")]},
                             "assignee": "worker", "covers": ["a"]}], accepted_risks=[_RISK, DENIAL_ENTRY])
    drift = e.claim_drift(TaskId("root")) or {}
    assert not drift.get("risks_added"), drift
    # the entry's text must not name the root's criterion `a` as a token — "a later exclusion" did, and §11.5's
    # re-admission now refuses that register by CHECK-4 (an entry naming an own criterion is no risk, §9.2)
    T.edit_accepted_risks(e, "root", [_RISK, DENIAL_ENTRY, {**_RISK, "item": "the later exclusion"}], agent="worker")
    assert (e.claim_drift(TaskId("root")) or {}).get("risks_added") == ["the later exclusion"]
    e.stop()


def test_under_semi_the_issuers_pre_fill_is_his_move_on_a_node_held_below():
    """The door's mode lock named `edit_accepted_risks` the split owner's move, so the holder — the node's issuer — was
    refused his own route to the packet's pre-fill on a node a machine executes (critic r4 over A-F6, B1)."""
    e = make_engine()
    e.start()
    e.project_name = "p"
    e.workforce.publish_executor_pool({"exec-1": "p", "exec-2": "p"})
    e.set_mode(Mode.SEMI, None, AgentId("agent"))
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G")]})
    T.TOOLS["decompose"](e, "root", [{"task_id": "kid", "covers": ["g"],
                                      "spec": {"description": "a part", "criteria": [criterion("k", "K")]}}],
                         accepted_risks=REGISTER)
    e.wait_idle()
    out = TL.TOOLS["edit_accepted_risks"](e, "kid", [_RISK], agent="agent")
    assert "error" not in out and "pre-filled" in out["written_as"], out
    e.stop()
