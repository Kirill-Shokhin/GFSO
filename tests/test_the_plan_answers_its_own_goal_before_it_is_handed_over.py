"""The question the gate will ask, asked by whoever writes the answer — and asked until the gate is answered.

`auto_decompose` converged by its own instruments (an empty fold, ONE repair round over the goal's undecided
obligations) and handed over a plan whose admission gate then opened 37 Level-2 findings, repaired by the machine
issuer one answer at a time (gb-coreutils, 2026-10-30; ~25 min on c_compiler). The author: «каким образом
автодекомпоз не проходит L2 если он по постановке его проходит?». The authoring now runs the gate's own review,
repairs exactly its findings — with the checker's reasons — and reviews again, until clean or until the open count
stops falling; the review it ran is the record the gate reads.

The switch stays: the measurement arm must still be able to author a plan this has NOT pre-repaired.
"""
import json

import pytest

import gfso.decompose as D
import gfso.tools as T
from gfso.config import sufficiency_at_authoring
from gfso.core.types import Stage, TaskId
from gfso.critic.types import NodeCritique
from tests.support import criterion, make_engine, REGISTER

ROOT = TaskId("root")


@pytest.fixture(autouse=True)
def _the_plan_gate_on(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "1")


def _plan():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "accepted_risks": REGISTER,
                                       "criteria": [criterion("g", "g holds")]})
    T.decompose(e, "root", [{"task_id": "kid", "covers": ["g"], "spec": {
        "name": "kid", "description": "a part", "accepted_risks": REGISTER,
        "criteria": [criterion("kid_c", "K holds")]}}], accepted_risks=REGISTER)
    e.wait_idle()
    return e


class _Planner:
    def __init__(self):
        self.calls = []


def _gate(monkeypatch, counts):
    """The admission's review, scripted: each run stores the record of the plan as it stands — `counts[i]` open
    undecided obligations on the i-th run, None for a check that read nothing — marks it current and returns the
    critique, exactly as the real one does, its calls labelled as the critic labels them. A repair round edits the
    plan, which retires that record. Returns (reviews, repairs) as they happen."""
    reviews, repairs = [], []

    def review(engine, rid, llm=None):
        n = counts[min(len(reviews), len(counts) - 1)]
        reviews.append(n)
        llm.calls += [{"stage": str(Stage.L2_CHECKER)}, {"stage": str(Stage.UNDECIDED_OBLIGATIONS)}]
        gaps = [{"obligation": f"o{i}", "admits": f"a result that skips o{i}"} for i in range(n or 0)]
        engine._graph._storage.store_critique(rid, json.dumps({
            "semantic_covered": None if n is None else n == 0, "conflicts": [], "goal_read": True,
            "criteria_verdicts": [{"criterion": "g", "verdict": "sufficient", "why": "ok"}],
            "undecided_obligations": gaps}))
        t = engine._graph.get_task(rid)
        t.verified = True
        engine._graph.save_task(t)
        return NodeCritique(str(rid), gate_passed=True, semantic_covered=None if n is None else n == 0,
                            undecided_obligations=tuple(gaps), goal_read=True,
                            semantic_findings="\n".join(f"[undecided] {g['obligation']} — admits: {g['admits']}"
                                                        for g in gaps))

    def refine(engine, request, root_id, *a, findings="", **k):
        spec = D.extract_spec(engine, root_id)
        if not findings:
            return False, spec, []                    # the requested refine round: converged by its own fold
        repairs.append(findings)
        t = engine._graph.get_task(TaskId(root_id))
        t.verified = False                            # an edit retires the review
        engine._graph.save_task(t)
        return True, spec, []

    monkeypatch.setattr(D, "review_decomposition", review)
    monkeypatch.setattr(D, "_refine_round", refine)
    return reviews, repairs


def _auto(e, llm=None):
    return D.decompose_into(e, "", root_id="root", llm=llm or _Planner(), depth=1)


def test_the_plan_is_repaired_until_the_gate_it_will_meet_passes(monkeypatch):
    e = _plan()
    reviews, repairs = _gate(monkeypatch, [3, 1, 0])
    res = _auto(e)
    assert reviews == [3, 1, 0] and len(repairs) == 2
    assert "o0 — admits: a result that skips o0" in repairs[0], \
        "the repair reads the gate's findings WITH the checker's reasons, not their bare names"
    assert e.open_l2_findings(ROOT) == [], "the gate reads the review the authoring ran — no question re-asked"
    assert not res.undecided_obligations and not res.note


def test_a_count_that_stops_falling_stops_the_loop_and_the_gate_reads_what_stands(monkeypatch):
    e = _plan()
    reviews, repairs = _gate(monkeypatch, [3, 2, 2, 2, 1, 0])
    res = _auto(e)
    assert reviews == [3, 2, 2, 2], "no new minimum for two rounds ends it — a fall later is not waited for"
    assert len(repairs) == 3
    assert e.open_l2_findings(ROOT) == ["undecided: o0", "undecided: o1"], "the last review is current"
    assert res.undecided_obligations == ("o0", "o1") and "2 Level-2 finding(s)" in res.note
    assert "holds the children" in res.note


def test_a_fold_that_changes_nothing_stops_the_loop(monkeypatch):
    e = _plan()
    reviews, _ = _gate(monkeypatch, [2])
    monkeypatch.setattr(D, "_refine_round", lambda engine, r, rid, *a, **k: (False, D.extract_spec(engine, rid), []))
    _auto(e)
    assert reviews == [2] and e.open_l2_findings(ROOT) == ["undecided: o0", "undecided: o1"]


def test_a_check_that_read_nothing_is_said_and_never_read_as_clean(monkeypatch):
    e = _plan()
    reviews, repairs = _gate(monkeypatch, [None])
    res = _auto(e)
    assert reviews == [None] and repairs == []
    assert e.open_l2_findings(ROOT) is None and "no verdict" in res.note and not res.undecided_obligations


def test_a_review_already_running_is_said_and_never_read_as_clean(monkeypatch):
    e = _plan()
    reviews, repairs = _gate(monkeypatch, [2])
    assert e.claims.begin_review(ROOT) is not None          # someone else's check over this version
    res = _auto(e)
    assert reviews == [] and repairs == []
    assert "already running" in res.note and not res.undecided_obligations


def test_the_authorings_review_is_priced_apart_from_the_gates_later_ones(monkeypatch):
    e = _plan()
    _gate(monkeypatch, [0])
    llm = _Planner()
    _auto(e, llm)
    assert [c["stage"] for c in llm.calls] == [Stage.AUTHORING_GATE, Stage.AUTHORING_OBLIGATIONS]


def test_the_measurement_arm_can_author_a_plan_this_has_not_touched(monkeypatch):
    assert sufficiency_at_authoring() is True
    monkeypatch.setenv("GFSO_SUFFICIENCY_AT_AUTHORING", "0")
    assert sufficiency_at_authoring() is False
    e = _plan()
    reviews, repairs = _gate(monkeypatch, [3])
    _auto(e)
    assert reviews == [] and repairs == []
