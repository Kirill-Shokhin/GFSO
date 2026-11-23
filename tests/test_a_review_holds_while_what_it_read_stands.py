"""A Level-2 review answers what it READ (§9.1): the goal's obligations, read once per text of the goal and kept (§11.5: a
re-check does not re-read what is settled); the disputes of its findings, which stand while the finding recurs (§9.7);
and its verdict, current while the parts it read stand — the parent's own contract, coverage and register, its children's
criteria, the Dep edges between them — and not retired by anything inside a child's subtree (§12.10).

Filed from a hand-built graph (tr-4, 2026-11-23): ~20 review runs to assemble one plan, most re-disputing findings
already answered, the root's review staled within the hour by a child's split and a child's scope."""
import dataclasses
import json

import pytest

from gfso import tools
from gfso.core.graph.review import finding_keys
from gfso.core.types import AcceptedRiskItem, AgentId, CriterionMapping, Register, TaskId
from gfso.critic import runner as R
from tests.support import DENIAL, REGISTER_ITEMS, REGISTER_SPLIT, UNMODELLED_FAULT, declare, make_engine, spec


class _LLM:
    """The three readers, told apart by their prompts; `conflict` and `why` set what the checker says this round."""
    _model = "fake"

    def __init__(self):
        self.calls, self.conflicts = [], [{"between": ["kid", "kid2"], "why": "clash"}]

    def complete(self, prompt="", context="", **k):
        if "DECOMPOSITION LEVEL UNDER CHECK" in prompt:
            self.calls.append("checker")
            return json.dumps({"criteria": [{"criterion": "c1", "verdict": "insufficient", "why": "thin"},
                                            {"criterion": "c2", "verdict": "sufficient", "why": "ok"}],
                               "conflicts": self.conflicts})
        if "AS ITS READING NAMED THEM" in prompt:
            self.calls.append("decide")
            return json.dumps({"decided": [], "open": [{"n": "1", "admits": "x"}]})
        if "Name every obligation" in prompt:
            self.calls.append("read")
            return json.dumps({"gaps": [{"obligation": "sorts", "admits": "a"}]})
        self.calls.append("other")
        return "{}"


@pytest.fixture
def e(monkeypatch):
    monkeypatch.setattr(R, "SUFFICIENCY_READINGS", 1)
    monkeypatch.setattr(R, "CHECKER_READINGS", 1)
    eng = make_engine(llm=_LLM(), check_interval=10_000)
    eng.start()
    eng.assign_task(TaskId("root"), spec("goal", "c1", "c2"), AgentId("user"))
    eng.wait_idle()
    eng.decompose_task(TaskId("root"), [(TaskId("kid"), spec("part", "k1"), AgentId("user")),
                                        (TaskId("kid2"), spec("part2", "k2"), AgentId("user"))],
                       [CriterionMapping("c1", TaskId("kid")), CriterionMapping("c2", TaskId("kid2"))],
                       register=REGISTER_SPLIT)
    eng.wait_idle()
    yield eng
    eng.stop()


def _review(e, node="root"):
    e._llm.calls.clear()
    R.review_decomposition(e, TaskId(node))
    e.wait_idle()
    return e.get_critique(TaskId(node))


def _verified(e, node="root") -> bool:
    return e.graph.get_task(TaskId(node)).verified


# (a) the goal's obligations, read once per what the reading reads

def test_an_unchanged_goal_is_read_once(e):
    first = _review(e)
    assert first["goal_obligations"] and e._llm.calls.count("read") == 1
    again = _review(e)
    assert "read" not in e._llm.calls, "the obligations on record are the unchanged goal's"
    assert again["goal_obligations"] == first["goal_obligations"]


def test_what_the_reading_reads_moving_reads_it_again(e):
    """The reading reads the goal's scope exclusions with its text: an exclusion declared is a different question."""
    _review(e)
    tools.edit_scope(e, "root", ["no network — offline only"], agent="user")
    e.wait_idle()
    _review(e)
    assert e._llm.calls.count("read") == 1, "a scope moved: the goal is read again"
    t = e.graph.get_task(TaskId("root"))
    e.revise(TaskId("root"), dataclasses.replace(t.spec, description="goal, sorted"), AgentId("user"))
    e.wait_idle()
    _review(e)
    assert e._llm.calls.count("read") == 1, "the text moved: read again"


# (b) a dispute stands while its finding recurs

def test_a_dispute_stands_while_its_finding_recurs(e):
    rec = _review(e)
    keys = finding_keys(rec)
    conflict = next(k for k in keys if k.startswith("conflict:"))
    undecided = next(k for k in keys if k.startswith("undecided:"))
    for k in ("c1", conflict, undecided):
        e.dispute_review_finding(TaskId("root"), k, "answered: why it is wrong", AgentId("user"))
    assert finding_keys(e.get_critique(TaskId("root"))) == []
    e._llm.conflicts = [{"between": ["kid2", "kid"], "why": "the same clash, worded anew this round"}]
    rec = _review(e)
    assert finding_keys(rec) == [], "the same criterion, conflict and obligation: each dispute stands"
    carried = rec["disputes"]["conflict: kid2, kid — the same clash, worded anew this round"]
    assert carried["why"] == "answered: why it is wrong" and carried["was"] == conflict


def test_a_dispute_answers_one_finding_and_leaves_with_it(e):
    rec = _review(e)
    conflict = next(k for k in finding_keys(rec) if k.startswith("conflict:"))
    e.dispute_review_finding(TaskId("root"), conflict, "answered", AgentId("user"))
    e._llm.conflicts = [{"between": ["kid", "kid2"], "why": "one"}, {"between": ["kid", "kid2"], "why": "another"}]
    rec = _review(e)
    assert [k for k in finding_keys(rec) if k.startswith("conflict:")] == ["conflict: kid, kid2 — another"], \
        "one dispute to one finding: a second conflict between the same children is open"
    e._llm.conflicts = []
    rec = _review(e)
    assert not any(k.startswith("conflict:") for k in rec.get("disputes") or {}), "no conflict recurs: its dispute goes"
    e._llm.conflicts = [{"between": ["kid", "kid2"], "why": "back"}]
    assert "conflict: kid, kid2 — back" in finding_keys(_review(e)), "a dispute gone does not come back"


def test_a_dispute_stays_on_its_own_finding_whatever_order_they_come_in(e):
    """Two conflicts between the same children: the one disputed keeps its dispute when the checker lists them the
    other way round — the order traded them, and the argued one came back open (critic over bf9efb4)."""
    e._llm.conflicts = [{"between": ["kid", "kid2"], "why": "formats clash"},
                        {"between": ["kid", "kid2"], "why": "ordering clash"}]
    _review(e)
    e.dispute_review_finding(TaskId("root"), "conflict: kid, kid2 — formats clash", "answered", AgentId("user"))
    e._llm.conflicts = list(reversed(e._llm.conflicts))
    rec = _review(e)
    assert [k for k in finding_keys(rec) if k.startswith("conflict:")] == ["conflict: kid, kid2 — ordering clash"]
    assert "conflict: kid, kid2 — formats clash" in (rec.get("disputes") or {})


# (c) a verdict stands while what its review read stands

def test_activity_inside_a_child_leaves_the_parents_review_current(e):
    _review(e)
    assert _verified(e)
    e.decompose_task(TaskId("kid"), [(TaskId("kid.a"), spec("a", "ka"), AgentId("user")),
                                     (TaskId("kid.b"), spec("b", "kb"), AgentId("user"))],
                     [CriterionMapping("k1", TaskId("kid.a")), CriterionMapping("k1", TaskId("kid.b"))],
                     register=REGISTER_SPLIT)
    e.wait_idle()
    assert _verified(e), "the child's split is the child's admission"
    declare(e, "kid.a", "kid.b")
    e.wait_idle()
    assert _verified(e), "a Dep edge inside the child's subtree"
    tools.edit_scope(e, "kid", ["no GUI"], agent="user")
    e.wait_idle()
    assert _verified(e), "the child's own scope"
    t = e.graph.get_task(TaskId("kid.a"))
    e.revise(TaskId("kid.a"), dataclasses.replace(t.spec, description="a, reworded"), AgentId("user"))
    e.wait_idle()
    assert _verified(e), "a grandchild's goal is the child's review's, not the parent's"
    e.reassign(TaskId("kid2"), AgentId("someone"))
    e.wait_idle()
    assert _verified(e), "who executes a child"


@pytest.mark.parametrize("edit", ["child_goal", "child_criteria", "parent_criteria", "covers", "dep"])
def test_what_the_review_read_moving_stales_it(e, edit):
    _review(e)
    assert _verified(e)
    if edit == "child_goal":
        t = e.graph.get_task(TaskId("kid"))
        e.revise(TaskId("kid"), dataclasses.replace(t.spec, description="part, reworded"), AgentId("user"))
    elif edit == "child_criteria":
        e.edit_criteria(TaskId("kid"), spec("part", "k1", "k1b").criteria, AgentId("user"))
    elif edit == "parent_criteria":
        e.edit_criteria(TaskId("root"), spec("goal", "c1", "c2", "c3").criteria, AgentId("user"))
    elif edit == "covers":
        r = e.graph.get_task(TaskId("root"))
        e._graph.save_task(dataclasses.replace(r, criterion_mappings=r.criterion_mappings
                                               + (CriterionMapping("c1", TaskId("kid2")),)))
        e._recompute_checks(TaskId("root"), stale_review=False)
    else:
        declare(e, "kid", "kid2")
    e.wait_idle()
    assert not _verified(e)


def _reword(e, node, name, text):
    """`name`'s text rewritten, its pins kept."""
    t = e.graph.get_task(TaskId(node))
    e.edit_criteria(TaskId(node), tuple(dataclasses.replace(c, description=text) if c.name == name else c
                                        for c in t.spec.criteria), AgentId("user"))
    e.wait_idle()


def test_a_dispute_leaves_with_an_edit_to_what_it_argued_about(e):
    """A criterion's finding is about its text and its coverers' criteria; a conflict's, about its children's criteria."""
    rec = _review(e)
    conflict = next(k for k in finding_keys(rec) if k.startswith("conflict:"))
    for k in ("c1", conflict):
        e.dispute_review_finding(TaskId("root"), k, "answered", AgentId("user"))
    _reword(e, "root", "c2", "c2, reworded")
    assert "c1" not in finding_keys(_review(e)), "an edit to another criterion: the dispute of c1 stands"
    _reword(e, "root", "c1", "c1, now demanding more")
    rec = _review(e)
    assert "c1" in finding_keys(rec), "c1 itself rewritten: the argument was about the old text"
    assert conflict not in finding_keys(rec), "the conflict's children untouched: its dispute stands"
    _reword(e, "kid", "k1", "k1, thinned")
    assert conflict in finding_keys(_review(e)), "a side's criteria rewritten: the argument was about the old ones"


def test_the_childs_packet_is_read_and_its_own_splits_register_is_not(e):
    """Under each part the parent's review reads the packet's pre-filled ACCEPTED_RISKS — its issuer's word — and not
    the register of the part's own split, which bounds the part's claim, not this split's."""
    _review(e)
    e.decompose_task(TaskId("kid"), [(TaskId("kid.a"), spec("a", "ka"), AgentId("user"))],
                     [CriterionMapping("k1", TaskId("kid.a"))], register=REGISTER_SPLIT)
    e.wait_idle()
    own = AcceptedRiskItem("the part's own split leaves locale formats out", UNMODELLED_FAULT.predictability,
                           "no locale in the fixture", "a locale appears", 0.01, "the part is re-split")
    e.admit_register(TaskId("kid"), Register((own, DENIAL)), AgentId("user"))
    e.wait_idle()
    assert own.item not in e.project(TaskId("root")), "the part's own split's register is not the parent's to read"
    assert _verified(e), "a re-admission of the part's own split"
    t = e.graph.get_task(TaskId("kid"))
    e.revise(TaskId("kid"), dataclasses.replace(t.spec, accepted_risks=REGISTER_ITEMS + (AcceptedRiskItem(
        "no GPU on the runner"),)), AgentId("user"))
    e.wait_idle()
    assert "no GPU on the runner" in e.project(TaskId("root"))
    assert not _verified(e), "the packet's pre-fill is read: its revision stales the parent's review"


# what a finding is about is the part of the review's read its question reads — one rule, every kind

def _dispute(e, key):
    e.dispute_review_finding(TaskId("root"), key, "answered", AgentId("user"))


def _conflict(rec):
    return next(k for k in finding_keys(rec) if k.startswith("conflict:"))


def test_a_conflict_is_about_its_sides_by_id_the_node_itself_included(e):
    e._llm.conflicts = [{"between": ["root (c1)", "kid (k1: parses)"], "why": "the node against its part"}]
    _dispute(e, _conflict(_review(e)))
    e._llm.conflicts = [{"between": ["kid (k1, glossed anew)", "root"], "why": "the node against its part"}]
    assert not any(k.startswith("conflict:") for k in finding_keys(_review(e))), "the same sides by id: it stands"
    _reword(e, "root", "c1", "c1, now demanding more")
    assert any(k.startswith("conflict:") for k in finding_keys(_review(e))), "the node's side rewritten: it leaves"


def test_a_finding_reads_the_nodes_register(e):
    _review(e)
    _dispute(e, "c1")
    e.admit_register(TaskId("root"), Register((UNMODELLED_FAULT, AcceptedRiskItem.denial_of(0.3, "now riskier"))),
                     AgentId("user"))
    e.wait_idle()
    assert "c1" in finding_keys(_review(e)), "the register the checker takes as law replaced: the dispute leaves"


def test_a_finding_reads_the_nodes_goal_and_scope(e):
    tools.edit_scope(e, "root", ["no network — offline only"], agent="user")
    e.wait_idle()
    _review(e)
    _dispute(e, "undecided: sorts")
    assert "undecided: sorts" not in finding_keys(_review(e)), "nothing moved: it stands"
    tools.edit_scope(e, "root", [], agent="user")
    e.wait_idle()
    assert "undecided: sorts" in finding_keys(_review(e)), "the scope it was argued under cleared: it leaves"


def test_an_obligation_stands_while_what_decided_it_stands(e):
    _review(e)
    _dispute(e, "undecided: sorts")
    e.edit_criteria(TaskId("kid"), spec("part", "k1", "k1b").criteria, AgentId("user"))
    e.wait_idle()
    assert "undecided: sorts" not in finding_keys(_review(e)), "a decider added: the argument stands"
    _reword(e, "kid", "k1", "k1, thinned")
    assert "undecided: sorts" in finding_keys(_review(e)), "a decider it was argued over changed: it leaves"


def test_a_deferral_recorded_stales_the_parents_review(e):
    declare(e, "kid2", "kid")
    e.wait_idle()
    _review(e)
    assert _verified(e)
    e.record_session_fit(TaskId("kid"), "larger than a session", False,
                         after={"producers": ["kid2"], "why": "its split reads kid2's format"})
    assert "split after kid2" in e.project(TaskId("root"))
    assert not _verified(e), "the deferral is the parent's plan, and its review read it"
