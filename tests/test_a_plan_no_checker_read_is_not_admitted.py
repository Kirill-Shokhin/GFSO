"""A plan is admitted on a Level-2 verdict about THAT plan, and on nothing else.

Two ways it was admitted on a verdict about another one, both reproduced by an outside reviewer:
- the checker's reply did not parse: the empty round stored nothing, marked the node verified, and the LAST
  record — about a plan since changed — was read as the current verdict;
- the issuer answered a dispute with ACCEPT_CHALLENGE: the child's contract changed in place, and the
  parent's verdict, read against the old criteria, stood over criteria no checker had read.
"""
from __future__ import annotations

import dataclasses
import json

import pytest

import gfso.decompose as D
import gfso.issuer as I
import gfso.tools as T
import gfso.tools_llm as TL
from gfso.core.graph.review import measured
from gfso.core.types import AgentId, Criteria, Mode, Signal, SignalData, TaskId
from gfso.critic import runner as CR
from tests.support import criterion, make_engine, REGISTER

_RISK = REGISTER
ROOT, KID = TaskId("root"), TaskId("kid")


@pytest.fixture(autouse=True)
def _the_plan_gate_on(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "1")      # the suite runs with it off; this file is about it


def _reviewed_plan():
    """An AUTO root with one child and a CLEAN Level-2 verdict standing over it."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.workforce.publish_executor_pool({"exec-1": "p", "exec-2": "p"})
    e.set_mode(Mode.AUTO, None, AgentId("agent"))
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "accepted_risks": _RISK,
                                       "criteria": [criterion("g", "g holds")]})
    T.decompose(e, "root", [{"task_id": "kid", "covers": ["g"], "spec": {
        "name": "kid", "description": "a part", "accepted_risks": _RISK,
        "criteria": [criterion("kid_c", "K holds")]}}], accepted_risks=REGISTER)
    e.wait_idle()
    e._graph._storage.store_critique(ROOT, json.dumps({
        "semantic_covered": True, "conflicts": [],
        "criteria_verdicts": [{"criterion": "g", "verdict": "sufficient", "why": "ok"}]}))
    root = e._graph.get_task(ROOT)
    root.verified = True
    e._graph.save_task(root)
    assert e.open_l2_findings(ROOT) == []
    return e


class _Unreadable:
    """A checker that answers, and says nothing a verdict can be read from."""
    calls, _model, stage_hint = [], "x", ""

    def complete(self, prompt=None, context=None, **k):
        self.calls.append({"cost_usd": 0.1})
        return "sorry, I cannot"

    def tag_last(self, *a):
        return None

    def __getattr__(self, name):
        return lambda *a, **k: None


def test_an_unreadable_review_of_a_changed_plan_admits_nothing():
    e = _reviewed_plan()
    kid = e.graph.get_task(KID)
    e.revise(KID, dataclasses.replace(kid.spec, criteria=kid.spec.criteria + (
        Criteria("z", "Z", check=kid.spec.criteria[0].check),)), e.graph.issuer_of(KID))
    e.wait_idle()
    CR.review_decomposition(e, ROOT, llm=_Unreadable())
    assert e.open_l2_findings(ROOT) is None, "the old verdict was read as the verdict on the new plan"
    assert e.execution_blocked_by(KID)


def test_a_contract_changed_by_an_accepted_dispute_stales_the_verdict_over_it():
    e = _reviewed_plan()

    def signal(sig, source, **kw):
        e.send_signal_sync(SignalData(signal=sig, task_id=KID, source=AgentId(source), **kw))
        e.wait_idle()
    kid = e.graph.get_task(KID)
    signal(Signal.CHALLENGE, str(kid.assignee), reason="kid_c cannot hold")
    signal(Signal.ACCEPT_CHALLENGE, str(e.graph.issuer_of(KID)), new_spec=dataclasses.replace(
        kid.spec, criteria=(Criteria("weaker", "much less", check=kid.spec.criteria[0].check),)))
    assert [c.name for c in e.graph.get_task(KID).spec.criteria] == ["weaker"]
    assert e.open_l2_findings(ROOT) is None and e.execution_blocked_by(KID)


class _Checker:
    """Reads the plan as sufficient, names one obligation of the goal, and — when re-asked — says it is
    still undecided; or, unreadable, says nothing."""
    _model, stage_hint = "x", ""

    def __init__(self, readable: bool, goal: bool = True):
        self.readable, self.goal, self.calls = readable, goal, []

    def complete(self, prompt=None, context=None, **k):
        self.calls.append({"cost_usd": 0.0})
        p = prompt or ""
        if not self.readable or ('"gaps"' in p and not self.goal):
            return "sorry, I cannot"
        if '"gaps"' in p:
            return json.dumps({"gaps": [{"obligation": "reports missing keys", "admits": "a tool that ignores keys"}]})
        if '"decided"' in p:
            return json.dumps({"decided": []})
        return json.dumps({"criteria": [{"criterion": "g", "verdict": "sufficient", "why": "ok"}], "conflicts": []})

    def __getattr__(self, n):
        return lambda *a, **k: None


def test_an_unreadable_round_does_not_erase_the_goals_undecided_obligations():
    """The obligations belong to the goal text; only a reading of the criteria against it removes one. A
    round that stored "no verdict" with an empty list erased them, and the next readable round — the goal
    unchanged, so it re-checks the list on record — found none, and the gate opened (critic round 7)."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.workforce.publish_executor_pool({"exec-1": "p", "exec-2": "p"})
    e.set_mode(Mode.AUTO, None, AgentId("agent"))
    T.TOOLS["create_task"](e, "root", {"description": "the goal: a config linter", "accepted_risks": _RISK,
                                       "criteria": [criterion("g", "g holds")]})
    T.decompose(e, "root", [{"task_id": "kid", "covers": ["g"], "spec": {
        "name": "kid", "description": "a part", "accepted_risks": _RISK,
        "criteria": [criterion("kid_c", "K holds")]}}], accepted_risks=REGISTER)
    e.wait_idle()
    CR.review_decomposition(e, ROOT, llm=_Checker(True))
    assert e.open_l2_findings(ROOT) == ["undecided: reports missing keys"]
    kid = e.graph.get_task(KID)
    e.revise(KID, dataclasses.replace(kid.spec, criteria=kid.spec.criteria + (
        Criteria("z", "Z", check=kid.spec.criteria[0].check),)), e.graph.issuer_of(KID))
    e.wait_idle()
    CR.review_decomposition(e, ROOT, llm=_Checker(False))
    CR.review_decomposition(e, ROOT, llm=_Checker(True))
    assert e.open_l2_findings(ROOT) == ["undecided: reports missing keys"], "erased by a round that read nothing"
    assert e.execution_blocked_by(KID)


@pytest.mark.parametrize("first", [_Checker(False), None], ids=["unreadable", "no_checker"])
def test_a_round_that_did_not_read_the_goal_does_not_stamp_it_read(first):
    """A first round with no checker, or an unreadable one, stored the current goal text with an empty
    obligations list; the next readable round took the goal as read and re-checked nothing — the gate
    opened on a plan whose obligations no one had named (critic round 8)."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.workforce.publish_executor_pool({"exec-1": "p", "exec-2": "p"})
    e.set_mode(Mode.AUTO, None, AgentId("agent"))
    T.TOOLS["create_task"](e, "root", {"description": "the goal: a config linter", "accepted_risks": _RISK,
                                       "criteria": [criterion("g", "g holds")]})
    T.decompose(e, "root", [{"task_id": "kid", "covers": ["g"], "spec": {
        "name": "kid", "description": "a part", "accepted_risks": _RISK,
        "criteria": [criterion("kid_c", "K holds")]}}], accepted_risks=REGISTER)
    e.wait_idle()
    CR.review_decomposition(e, ROOT, llm=first)
    assert e.stored_review_findings(ROOT) is None, "a round that read nothing is no baseline for progress"
    CR.review_decomposition(e, ROOT, llm=_Checker(True))
    assert e.open_l2_findings(ROOT) == ["undecided: reports missing keys"]


def _auto_plan():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.workforce.publish_executor_pool({"exec-1": "p", "exec-2": "p"})
    e.set_mode(Mode.AUTO, None, AgentId("agent"))
    T.TOOLS["create_task"](e, "root", {"description": "the goal: a config linter", "accepted_risks": _RISK,
                                       "criteria": [criterion("g", "g holds")]})
    T.decompose(e, "root", [{"task_id": "kid", "covers": ["g"], "spec": {
        "name": "kid", "description": "a part", "accepted_risks": _RISK,
        "criteria": [criterion("kid_c", "K holds")]}}], accepted_risks=REGISTER)
    e.wait_idle()
    return e


def test_a_goal_reading_that_failed_is_no_reading():
    """Every reading of the goal unparseable returned `()` — "no gaps" — the gate opened on it, and each later
    round re-checked the empty list (critic round 9). A failed reading is ⊥: no verdict, and read next time."""
    e = _auto_plan()
    CR.review_decomposition(e, ROOT, llm=_Checker(True, goal=False))
    assert e.open_l2_findings(ROOT) is None, "the plan verdict alone opened the gate"
    CR.review_decomposition(e, ROOT, llm=_Checker(True))
    assert e.open_l2_findings(ROOT) == ["undecided: reports missing keys"]


def test_progress_is_counted_against_the_last_round_that_measured():
    """After a round that read nothing, the next review — findings unchanged — counted as progress and reset
    the machine issuer's unproductive count (critic round 9): the baseline rides through the empty round."""
    e = _auto_plan()
    CR.review_decomposition(e, ROOT, llm=_Checker(True))
    first = e.stored_review_findings(ROOT)
    CR.review_decomposition(e, ROOT, llm=_Checker(False))
    assert e.stored_review_findings(ROOT) == first
    CR.review_decomposition(e, ROOT, llm=None)
    assert e.stored_review_findings(ROOT) == first


def test_a_record_from_a_round_that_read_nothing_before_the_flag_does_not_count_as_read():
    """A stored record older than `goal_read`, from a round that read nothing: goal stamped, no obligations,
    no verdict. Taken as read, the next round re-checked an empty list and the gate opened (critic round 9)."""
    e = _auto_plan()
    e._graph._storage.store_critique(ROOT, json.dumps({"semantic_covered": None, "criteria_verdicts": [],
                                                       "undecided_obligations": [],
                                                       "goal_text": "the goal: a config linter"}))
    CR.review_decomposition(e, ROOT, llm=_Checker(True))
    assert e.open_l2_findings(ROOT) == ["undecided: reports missing keys"]


class _GoalOnceThenNothing:
    """The first reading of the goal names a gap; the one after the repair round is unreadable."""
    _model, stage_hint = "x", ""

    def __init__(self):
        self.n, self.calls = 0, []

    def complete(self, prompt=None, context=None, **k):
        if '"gaps"' in (prompt or ""):
            self.n += 1
            if self.n == 1:
                return json.dumps({"gaps": [{"obligation": "reports missing keys", "admits": "x"}]})
        return "sorry"

    def __getattr__(self, n):
        return lambda *a, **k: None


def test_an_unreadable_reading_after_the_authoring_repair_leaves_the_obligations_standing(monkeypatch):
    """⊥ from the re-reading crashed the decomposition verb after the graph was built (critic round 10);
    nothing measured closed, so every obligation named stands."""
    e = _auto_plan()
    monkeypatch.setattr(D, "_refine_round", lambda *a, **k: (True, {}, []))
    _, _, residue = D._close_the_goals_obligations(e, "req", ROOT, "agent", _GoalOnceThenNothing(), {}, [], None)
    assert residue == ("reports missing keys",)


@pytest.mark.parametrize("record", [
    {"semantic_covered": None, "undecided_obligations": [], "goal_text": "the goal: a config linter",
     "criteria_verdicts": [{"criterion": "g", "verdict": "sufficient", "why": "ok"}]},
    {"semantic_covered": True, "undecided_obligations": [], "goal_text": "the goal: a config linter",
     "criteria_verdicts": [{"criterion": "g", "verdict": "sufficient", "why": "ok"}]},
], ids=["incomplete", "goal_unread_but_stored_clean"])
def test_a_record_from_before_the_flag_is_read_afresh(record):
    """Two kinds of record from before `goal_read` never read the goal yet carry a verdict: an incomplete one,
    and one whose goal reading failed and was stored as clean — indistinguishable from a real clean reading.
    Both opened the gate (critic round 10); a record without the flag is read once more."""
    e = _auto_plan()
    e._graph._storage.store_critique(ROOT, json.dumps(record))
    CR.review_decomposition(e, ROOT, llm=_Checker(True))
    assert e.open_l2_findings(ROOT) == ["undecided: reports missing keys"]


class _Gap(_Checker):
    """Reads the plan as NOT carrying its criterion `g`."""

    def complete(self, prompt=None, context=None, **k):
        if '"gaps"' in (prompt or "") or '"decided"' in (prompt or ""):
            return super().complete(prompt, context, **k)
        return json.dumps({"criteria": [{"criterion": "g", "verdict": "insufficient", "why": "no"}],
                           "conflicts": []})


class _Incomplete(_Checker):
    """Answers the plan question leaving the parent's criterion out — an incomplete verdict."""

    def complete(self, prompt=None, context=None, **k):
        if '"gaps"' in (prompt or "") or '"decided"' in (prompt or ""):
            return super().complete(prompt, context, **k)
        return json.dumps({"criteria": [{"criterion": "other", "verdict": "sufficient", "why": "x"}], "conflicts": []})


def test_an_incomplete_verdict_is_no_progress_baseline():
    """An incomplete plan verdict is no verdict; counted as the baseline, an alternating checker reset the
    issuer's unproductive count (critic round 10)."""
    e = _auto_plan()
    CR.review_decomposition(e, ROOT, llm=_Gap(True))
    first = e.stored_review_findings(ROOT)
    assert len(first) == 2, first
    CR.review_decomposition(e, ROOT, llm=_Incomplete(True))
    assert e.stored_review_findings(ROOT) == first


def test_a_dispute_needs_a_verdict_that_stands():
    """A round that read nothing carries the goal reading on record with no verdict; a dispute against it
    "discharged" a finding no gate held, and the reply read as clean (critic round 11)."""
    e = _auto_plan()
    CR.review_decomposition(e, ROOT, llm=_Checker(True))
    CR.review_decomposition(e, ROOT, llm=_Checker(False))
    with pytest.raises(ValueError, match="no current Level-2 verdict"):
        e.dispute_review_finding(ROOT, "undecided: reports missing keys", "wrong", AgentId("agent"))


def test_a_node_split_with_no_request_is_split_by_its_own_contract(monkeypatch):
    """The split SEMI asks for ("split it first", auto_decompose with no request) reached the decomposer as an
    empty task, and the node's contract was re-authored from nothing (critic round 11)."""
    e = _auto_plan()
    T.TOOLS["create_task"](e, "leaf", {"description": "parse numbers", "criteria": [criterion("n", "N parses")]},
                           parent_id="root", covers=["g"])
    e.wait_idle()
    seen = []

    def _spy(request, **k):
        seen.append(request)
        raise RuntimeError("stop here")

    monkeypatch.setattr(D, "decompose_spec", _spy)
    with pytest.raises(RuntimeError):
        D.decompose_into(e, "", root_id="leaf", assignee="exec-2", llm=object())
    assert "parse numbers" in seen[0] and "n: N parses" in seen[0], seen


def test_the_split_of_an_issued_node_keeps_its_contract_whatever_the_caller_typed(monkeypatch):
    """The MCP door requires `request`, so a holder told to "split it first" types something — and the
    decomposer saw only that, re-deriving the node's contract from it (critic round 12). An issued node is
    split by its own contract, the request riding along as guidance."""
    e = _auto_plan()
    T.TOOLS["create_task"](e, "leaf", {"description": "parse numbers", "criteria": [criterion("n", "N parses")]},
                           parent_id="root", covers=["g"])
    e.wait_idle()
    seen = []

    def _spy(request, **k):
        seen.append(request)
        raise RuntimeError("stop here")

    monkeypatch.setattr(D, "decompose_spec", _spy)
    with pytest.raises(RuntimeError):
        D.decompose_into(e, "split it please", root_id="leaf", assignee="exec-2", llm=object())
    assert "parse numbers" in seen[0] and "n: N parses" in seen[0] and "split it please" in seen[0], seen


def test_a_round_that_reached_no_verdict_reports_nothing_closed(monkeypatch):
    """The reply said "0 new, 2 closed" beside `execution_admitted: false` after a round that read nothing
    (critic round 12): nothing is compared unless this round measured."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.TOOLS["create_task"](e, "root", {"description": "the goal: a config linter", "accepted_risks": _RISK,
                                       "criteria": [criterion("g", "g holds")]})
    T.decompose(e, "root", [{"task_id": "kid", "covers": ["g"], "spec": {
        "name": "kid", "description": "a part", "accepted_risks": _RISK,
        "criteria": [criterion("kid_c", "K holds")]}}], accepted_risks=REGISTER)
    e.wait_idle()
    CR.review_decomposition(e, ROOT, llm=_Gap(True))
    monkeypatch.setattr(TL, "llm_factory", lambda model: _Checker(False))
    out = TL.TOOLS["review_decomposition"](e, "root")
    assert not out.get("error") and out["gate_passed"], out
    assert out.get("closed_since_last_review") is None, out.get("delta_note")



def test_a_split_keeps_the_callers_goal_text_on_a_root_that_had_none(monkeypatch):
    """The combined contract-plus-guidance text is what the DECOMPOSER reads; a root made with a name and no
    description took it as its goal, the user's own words under a "how to split it" header (critic round 13)."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.TOOLS["create_task"](e, "root", {"name": "thing", "description": "", "accepted_risks": _RISK,
                                       "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    seen = []
    monkeypatch.setattr(D, "decompose_spec", lambda request, **k: seen.append(request) or {"x": 1})
    monkeypatch.setattr(D, "_build_verified", lambda spec, request, *a, **k: (_ for _ in ()).throw(
        RuntimeError(request)))
    with pytest.raises(RuntimeError) as err:
        D.decompose_into(e, "a CLI that parses A and emits B", root_id="root", assignee="agent", llm=object())
    assert str(err.value) == "a CLI that parses A and emits B", "the build took the decomposer's text as the goal"
    assert "g: G holds" in seen[0]


def test_a_review_that_raises_again_only_what_was_disputed_is_not_the_issuers_failure_to_move():
    """A finding answered in writing and raised again by the review of a plan that changed since counted as a
    review that moved nothing; three such — one per re-issued child — closed a converging AUTO root (critic,
    2026-09-27). The disagreement is the checker's reading, answered again by a dispute; it closes nothing."""
    e = _auto_plan()
    CR.review_decomposition(e, ROOT, llm=_Gap(True))
    for key in e.open_l2_findings(ROOT) or ():
        e.dispute_review_finding(ROOT, key, "the child's criterion carries it", AgentId("agent"))
    T.edit_criteria(e, "kid", [criterion("kid_c", "K holds"), criterion("kid_d", "D holds")], agent="exec-1")
    e.wait_idle()
    assert e.open_l2_findings(ROOT) is None                          # the plan changed: its review is stale
    verbs = I.Verbs(llm=None, busy=None, refine=None,
                    review=lambda engine, node: (CR.review_decomposition(engine, node, llm=_Gap(True)),
                                                 {"stats": {"calls": 1}})[1])
    out = I.settle(e, None, ROOT, "plan", "exec-1", verbs)
    assert out.get("kind") == "review" and out["status"] not in I._COUNTED, out
