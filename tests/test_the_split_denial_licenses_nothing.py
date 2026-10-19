"""A split's denial by S is in its register and licenses nothing (§9.2, §9.5).

The register's one denial entry states the split's odds of being refuted at contact — "the parent fails while every
child passes". Rendered to a validator under "the plan set these aside — do not fail the node for a gap that lives
only here", it would excuse exactly the composition failure it names; to an executor under "do not gold-plate
against these", it would tell the whole's executor its glue need not hold (critic r4, 2026-10-04). And a split is
one hypothesis: two denials are not a register CHECK-4 admits.

CONTROL: render `spec.accepted_risks` where `spec.set_aside` is read, or drop the count from CHECK-4, or let the
builder keep a listed denial beside the schema's own — and these go red.
"""
from gfso import packets
from gfso.core.graph.projection import render_node_projection
from gfso.core.handlers.structural import check_accepted_risks
from gfso.core.types import register_of, AcceptedRiskItem, AgentId, Criteria, CriterionMapping, Register, Spec, TaskId
from gfso.decompose.build import build_graph_live
from gfso.decompose.extract import extract_spec
from tests.support import REGISTER_SPLIT, DENIAL, DENIAL_ENTRY, REGISTER_ITEMS, UNMODELLED_FAULT, criterion, make_engine, pinned


def _whole():
    """root (a whole, its register carrying its denial) over one leaf whose own split is not yet made."""
    e = make_engine()
    e.start()
    e.assign_task(TaskId("root"), Spec("a parser", (Criteria("g", "parses", check=pinned("g")),),
                                       accepted_risks=REGISTER_ITEMS), AgentId("pm"))
    e.wait_idle()
    e.decompose_task(TaskId("root"), [(TaskId("leaf"), Spec("parse numbers", (Criteria(
        "n", "numbers", check=pinned("n")),), accepted_risks=REGISTER_ITEMS), AgentId("w"))],
        criterion_mappings=[CriterionMapping("g", TaskId("leaf"))], register=REGISTER_SPLIT)
    e.wait_idle()
    return e


def test_the_denial_is_not_set_aside_for_the_validator_nor_the_executor():
    e = _whole()
    root = e.graph.get_task(TaskId("root"))
    for packet in (packets._validator_packet(e, root, "delivered", None),
                   packets._scope_validator_packet(e, [(root, "delivered", root.spec.criteria)], None, None,
                                                     frozenset({"root"})),
                   packets._executor_packet(e, root, "ws"),
                   packets._scope_node_block(e, 1, root, root, frozenset({"root"}))):
        assert UNMODELLED_FAULT.item in packet, "a risk event the split accepts is still shown"
        assert DENIAL.item not in packet, "the split's denial read as a risk the plan set aside"
    e.stop()


def test_a_reviewer_reads_no_childs_denial_as_set_aside():
    """Canon v4.1 (§9.2): a leaf has no register — the child's is its own split's, so the child here is split."""
    e = _whole()
    e.decompose_task(TaskId("leaf"), [(TaskId("leaf.n"), Spec("digits", (Criteria("d", "digits", check=pinned("d")),)),
                                       AgentId("w"))], [CriterionMapping("n", TaskId("leaf.n"))], register=REGISTER_SPLIT)
    e.wait_idle()
    text = render_node_projection(e.graph.get_task(TaskId("root")), [e.graph.get_task(TaskId("leaf"))], [], [])
    assert f"ACCEPTED_RISKS: {DENIAL.item}" not in text
    assert f"ACCEPTED_RISKS: {UNMODELLED_FAULT.item}" in text
    e.stop()


def test_a_split_carries_one_denial():
    e = _whole()
    root = e.graph.get_task(TaskId("root"))
    # the split's register, which CHECK-4 reads (canon v4.1 §9.2) — not the packet's pre-fill
    two = Register((*REGISTER_ITEMS, AcceptedRiskItem.denial_of(0.3, "a second guess")))
    r = check_accepted_risks(type(root)(**{**root.__dict__, "register": two}), [e.graph.get_task(TaskId("leaf"))])
    assert not r.passed and "2 entries state this split's denial" in r.details, r.details
    assert check_accepted_risks(root, [e.graph.get_task(TaskId("leaf"))]).passed
    e.stop()


def test_the_builder_keeps_one_denial_and_the_extract_hands_it_back_under_its_own_key():
    """A fold round added the schema's `denial` beside one the extract had listed inside `accepted_risks`."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    d = {"root_criteria": [criterion("g", "G holds")],
         "subtasks": [{"id": "a", "description": "part", "criteria": [criterion("ga", "A")]}],
         "mappings": [{"criterion": "g", "child_id": "a"}], "deps": [],
         "accepted_risks": [UNMODELLED_FAULT.to_dict(), DENIAL_ENTRY],
         "denial": {"p": 0.25, "justification": "the fold's own estimate"}}
    build_graph_live(d, "the goal", e, root_id="root", assignee="agent")
    e.wait_idle()
    reg = register_of(e.graph.get_task(TaskId("root"))).items
    assert [n.p for n in reg if n.denial] == [0.25], "the schema's denial wins, the listed one goes"
    back = extract_spec(e, "root")
    assert not any(n.get("denial") for n in back["accepted_risks"])
    assert back["denial"] == {"p": 0.25, "justification": "the fold's own estimate"}
    e.stop()


def test_the_level_under_review_shows_the_denial_apart_from_the_risks_it_accepts():
    """The L2 checker is told an entry naming an uncertain EVENT covers a gap; the denial names "the parent fails while
    every child passes" — under the register it would cover every gap at that level (critic r4, 2026-10-04)."""
    e = _whole()
    text = render_node_projection(e.graph.get_task(TaskId("root")), [e.graph.get_task(TaskId("leaf"))], [], [])
    register = text.split("## ACCEPTED_RISKS")[1].split("\n## ")[0]
    assert UNMODELLED_FAULT.item in register and DENIAL.item not in register, register
    assert "NOT an accepted risk" in text and "covers no gap" in text
    e.stop()
