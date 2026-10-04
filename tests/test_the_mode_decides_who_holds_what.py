"""The MODE is the user's one choice of who holds which nodes — and a lock, not a default.

SOLO: the user-agent holds everything. SEMI: it holds the top of the tree (by default the root), the
system the rest. AUTO: the system holds every node, the root included, and the user-agent is the goal's
customer — the root's ISSUER — who does not intervene. The consistent assignments are connected top
parts of the tree, so the mode is one depth boundary; under it the Del of every issued node comes from
the mode, and the doors refuse a move the mode gave to the system.
"""
from __future__ import annotations

import contextlib
import dataclasses as _dc
import json
import threading
import time
from datetime import timedelta

import pytest

import gfso.tools as T
import gfso.tools_llm as TL
from gfso import issuer as I
from gfso.decompose.build import build_graph_live
from gfso.decompose.extract import extract_spec
from gfso.sessions import run_consent
from gfso.roster import AgentRegistry
from gfso.core.types import register_of, AgentId, Mode, Register, Signal, SignalData, State, TaskId
from tests.support import DENIAL_ENTRY, criterion, instrument_passes, make_engine, REGISTER

_RISK = REGISTER


def _engine(mode=None, boundary=None):
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.workforce.publish_executor_pool({"exec-1": "p", "exec-2": "p", "elsewhere": "other-project"})
    if mode is not None:
        e.set_mode(mode, boundary, AgentId("agent"))
    return e


def _kid(task_id, covers, *criteria, description=""):
    """A child as `decompose` takes it: its contract and the parent criteria it carries."""
    return {"task_id": task_id, "covers": list(covers),
            "spec": {"description": description or task_id, "criteria": list(criteria)}}


def _admit(e, parent, *kids):
    """The split admitted whole (§11.5), its register written with it by its decomposer (§9.2)."""
    out = T.TOOLS["decompose"](e, parent, list(kids), accepted_risks=_RISK)
    e.wait_idle()
    return out


def _goal(e):
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("kid", ["g"], criterion("k", "K holds"), description="a part"))
    return e.graph.get_task(TaskId("root")), e.graph.get_task(TaskId("kid"))


def _uncarried(e, issuer):
    """A plan question the canon's way: the admitted root revised by its plan's issuer to add `h`, which no child
    carries — a hole after admission is a flag on the plan (§12.10), never a refused admission (§11.5)."""
    ok, why = I.apply_move(e, TaskId("root"), "plan", issuer, {"move": "add_criterion", "justification": "goal",
                                                                "criteria": [criterion("h", "H holds")]})
    assert ok, why
    e.wait_idle()


def test_with_no_mode_nothing_changes():
    e = _engine()
    root, kid = _goal(e)
    assert (str(root.assignee), str(kid.assignee)) == ("agent", "agent")
    assert str(e.graph.issuer_of(TaskId("root"))) == "agent"


def test_auto_hands_every_node_to_the_system_and_keeps_the_customer_as_the_roots_issuer():
    e = _engine(Mode.AUTO)
    root, kid = _goal(e)
    assert str(root.assignee) == "exec-1"
    assert str(kid.assignee) == "exec-2", "a child under its own parent's executor would have no seam"
    assert str(e.graph.issuer_of(TaskId("root"))) == "agent", \
        "the root's executor would be its own issuer — answering its own disputes (§10.3)"
    assert "elsewhere" not in {str(a) for a in e.workforce.executor_pool()}, "another project's executor"


def test_auto_refuses_the_customers_moves_on_the_work():
    e = _engine(Mode.AUTO)
    _goal(e)
    out = TL.TOOLS["edit_criteria"](e, "kid", [criterion("k", "K, easier")])
    assert out.get("error") and "AUTO" in out["error"], out
    # the refusal must not hand the customer the mode as ITS way out: measured live, the AUTO customer
    # read "To take control back, set_mode(...)", switched the mode itself and held the project
    assert "set_mode" not in out["error"] and "ask" in out["error"], out
    out = TL.TOOLS["signal"](e, "root", "CANCEL", "agent", reason="I changed my mind")
    assert out.get("error") and "AUTO" in out["error"], "the customer's own signal is a move on the work"


def test_semi_leaves_the_holder_its_issuer_moves_and_takes_the_childrens_splits():
    e = _engine(Mode.SEMI)
    root, kid = _goal(e)
    assert (str(root.assignee), str(kid.assignee)) == ("agent", "exec-1")
    # the child's CONTRACT is the holder's (it is the child's issuer) …
    out = TL.TOOLS["edit_criteria"](e, "kid", [criterion("k", "K, stated sharper")])
    assert not out.get("error") or "SEMI" not in str(out.get("error")), out
    # … its SPLIT is the system's
    out = TL.TOOLS["create_task"](e, "grandkid", {"description": "deeper",
                                                  "criteria": [criterion("x", "X")]}, parent_id="kid")
    assert out.get("error") and "semi" in out["error"], out


def test_a_name_that_contradicts_the_mode_is_refused_not_obeyed():
    e = _engine(Mode.SEMI)
    T.TOOLS["create_task"](e, "root", {"description": "g", "accepted_risks": _RISK,
                                       "criteria": [criterion("g", "G")]})
    out = T.TOOLS["create_task"](e, "kid", {"description": "part", "criteria": [criterion("k", "K")]},
                                 parent_id="root", assignee="agent")
    assert out.get("error") and "only the user changes it" in out["error"], out


def test_semis_default_boundary_is_the_middle_of_the_plans_depth():
    e = _engine(Mode.SEMI)
    _goal(e)
    assert e.holder_boundary() == 1, "root + children: the agent holds the root, the system the rest"


class _FakeLLM:
    def __init__(self, payload):
        self._text = "```json\n" + json.dumps(payload) + "\n```"
        self.calls, self.packets = [], []

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.packets.append(user)
        self.calls.append({"duration_ms": 1, "output_tokens": 1})
        return self._text

    def complete(self, prompt, context=""):
        return self.run_agent(context, prompt, ())

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def test_under_auto_the_system_answers_the_roots_questions_and_may_not_narrow_its_criteria():
    e = _engine(Mode.AUTO)
    root, _ = _goal(e)
    assert I.system_mover(e, _Roster(), TaskId("root"), "escalation") == "agent", \
        "under AUTO the system moves for the customer"
    spec = I.spec_with(root, [{"name": "g", "description": "G, loosened", "check": [
        {"behaviour": "b", "command": "test -d . && echo 0", "expect": "0"}]}])
    assert I.narrowing_at_the_root(e, root, spec), "a reworded root criterion is a narrowed contract"
    kept = I.spec_with(root, [{"name": c.name, "description": c.description,
                               "check": [{"behaviour": p.behaviour, "command": p.command,
                                          "expect": p.expect} for p in c.check]}
                              for c in root.spec.criteria]
                       + [{"name": "extra", "description": "E", "check": [
                           {"behaviour": "b", "command": "test -d . && echo 0", "expect": "0"}]}])
    assert I.narrowing_at_the_root(e, root, kept) is None, "adding to the goal is allowed"


def test_under_auto_an_accepted_dispute_re_pins_a_root_probe_and_keeps_the_users_words():
    """The root's probe of «Comment handling» expected 5 tokens where its own text gives 6; the machine issuer accepted
    with the probe corrected eight times, the answer was cut to additions and read as «changed nothing», and the root
    closed by count (AUTO haiku sql_database, 2026-10-14). The text is the user's word; the probe is the issuer's."""
    e = _engine(Mode.AUTO)
    two = {"name": "h", "description": "H holds", "check": criterion("h")["check"] * 2}
    two["check"] = [{**p, "command": f"{p['command']} # {i}"} for i, p in enumerate(two["check"])]
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds"), two]})
    _admit(e, "root", _kid("kid", ["g", "h"], criterion("k", "K holds"), description="a part"))
    stored_h = [p.command for p in e.graph.get_task("root").spec.criteria[1].check]
    T.signal(e, "root", "ACCEPT", "exec-1")
    T.signal(e, "root", "CHALLENGE", "exec-1", reason="g's pinned probe expects what g's own text refutes")
    e.wait_idle()
    probe = {"behaviour": "b", "command": "test -d . && echo 6", "expect": "6"}
    llm = _FakeLLM({"decision": "accept", "justification": "the probe's expected output contradicts g's text",
                    "criteria": [{"name": "g", "description": "G, loosened", "check": [probe]},
                                 {"name": "h", "description": "H holds", "check": [probe]}]})
    out = I.answer_the_challenge(e, TaskId("root"), "agent", _llm=llm)
    e.wait_idle()
    t = e.graph.get_task("root")
    assert out["status"] == "accepted", out
    assert t.state == State.OFFERED, "the corrected contract is re-consented (Inv-1)"
    g, h = t.spec.criteria[:2]
    assert [p.command for p in g.check] == [probe["command"]], "the disputed probe was re-pinned"
    assert g.description == "G holds", "the user's word stands, whatever the answer says"
    assert [p.command for p in h.check] == stored_h, "a criterion nobody disputed keeps its probes"
    # a re-issue answers no dispute: it re-pins nothing at the root
    ok, why = I._reassign(e, t, "agent", {"criteria": [{"name": "g", "description": "G holds", "check": [
        {"behaviour": "b", "command": "test -d . && echo ok", "expect": "ok"}]}]}, "re-issue", None)
    assert [p.command for p in e.graph.get_task("root").spec.criteria[0].check] == [probe["command"]], (ok, why)


def test_a_challenge_after_a_fail_questions_the_criteria_that_fail_cited():
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [
        criterion("Comment handling in lexical analysis", "comments skipped"), criterion("other", "O")]})
    _admit(e, "root", _kid("kid", ["Comment handling in lexical analysis", "other"], criterion("k", "K")))
    T.signal(e, "root", "ACCEPT", "exec-1")
    T.signal(e, "root", "DELIVER", "exec-1", result="r")
    T.signal(e, "root", "FAIL", "agent", failed_criteria=["Comment handling in lexical analysis"])
    T.signal(e, "root", "CHALLENGE", "exec-1", reason="the comment handling probe contradicts the lexer's")
    e.wait_idle()
    assert I.questioned(e, e.graph.get_task("root")) == {"Comment handling in lexical analysis"}


def test_under_semi_the_holder_keeps_its_discretion():
    e = _engine(Mode.SEMI)
    _goal(e)
    assert I.system_mover(e, _Roster(), TaskId("kid"), "dispute") is None, \
        "the child's issuer is the holder; answering its dispute is the holder's move"
    assert I.system_mover(e, _Roster(), TaskId("kid"), "repair") == "exec-1", \
        "the child's split is its executor's"


def test_past_two_contracts_the_issuer_is_asked_and_a_next_one_must_change_what_failed(monkeypatch):
    """§12.15: a counter at ESCALATED "would, exhausted, leave the owner of a live goal only CANCEL or silence"; under
    AUTO the machine IS that owner. The count used to close the node before any issuer turn was asked (critic over
    session 475ba784). Past it the issuer decides, told the count; a contract changing only the date is refused."""
    e = _engine(Mode.AUTO)
    _goal(e)
    monkeypatch.setattr(I, "extensions_granted", lambda engine, task_id: I.MAX_EXTENSIONS)
    monkeypatch.setattr(I, "_still_open", lambda *a: True)          # the node stands ESCALATED
    asked = []
    monkeypatch.setattr(I, "issuer_turn", lambda *a, refusal="", **k: asked.append(refusal) or {"status": "applied"})
    I.settle(e, _Roster(), TaskId("kid"), "escalation", "exec-1", verbs=None)
    assert asked and "none reached a verdict" in asked[0], asked
    assert e.graph.get_state(TaskId("kid")) != State.CANCELLING, "nobody decided to close it"
    monkeypatch.setattr(I, "seam_keeping_executor", lambda engine, task, other: task.assignee)
    kid = e.graph.get_task(TaskId("kid"))
    ok, why = I._reassign(e, kid, "exec-1", {"extend_hours": 24}, "again", None)
    assert not ok and "change what failed" in why, why
    ok, why = I._reassign(e, kid, "exec-1", {"max_iterations": kid.max_iterations + 2}, "a raised budget", None)
    assert ok, why


def test_the_issuers_questions_are_answered_from_contact_and_the_splits_are_not(monkeypatch, tmp_path):
    """What failed or what blocks is a fact of the workspace, so the issuer's questions — the dispute, the escalation,
    the external block, the parked node — are asked where the node's work is; the split's questions are the
    executor's planning over the map and are asked as before."""
    e = _engine(Mode.AUTO)
    _goal(e)
    monkeypatch.setattr(I, "_still_open", lambda *a: True)
    asked = []
    monkeypatch.setattr(I, "issuer_turn", lambda *a, where=None, **k: asked.append(where) or {"status": "applied"})
    verbs = I.Verbs(llm=None, busy=lambda *a: contextlib.nullcontext(), review=None, refine=None,
                    place=lambda engine, agents, node: str(tmp_path))
    for q in ("dispute", "escalation", "external", "parked", "repair"):
        I.settle(e, _Roster(), TaskId("kid"), q, "exec-1", verbs=verbs)
    assert asked == [str(tmp_path)] * 4 + [None], asked


def test_a_system_held_parent_gives_its_own_consent():
    e = _engine(Mode.AUTO)
    _goal(e)
    assert e.graph.get_state(TaskId("root")) == State.OFFERED
    out = run_consent(e, TaskId("root"), "exec-1", _Roster(),
                      _llm=_FakeLLM({"decision": "accept", "reason": "the split carries it"}))
    e.wait_idle()
    assert out["status"] == "accepted", out
    assert e.graph.get_state(TaskId("root")) == State.EXECUTING


def test_with_no_mode_the_system_answers_only_the_disputes_it_always_answered():
    e = _engine()
    _goal(e)
    assert I.system_mover(e, _Roster(), TaskId("kid"), "dispute") == "agent"
    assert I.system_mover(e, _Roster(), TaskId("kid"), "escalation") is None,         "a solo user's escalation is theirs to decide; the system must not write or close their contract"


def test_a_holder_cannot_take_a_system_node_back_by_reassigning_it():
    e = _engine(Mode.SEMI)
    _goal(e)
    out = TL.TOOLS["reassign"](e, "kid", "agent")
    assert out.get("error") and "only the user changes it" in out["error"], out


def test_a_switched_and_restored_mode_leaves_a_different_record():
    e = _engine(Mode.AUTO)
    first = e.mode()
    e.set_mode(Mode.SOLO, None, AgentId("agent"))
    e.set_mode(Mode.AUTO, None, AgentId("agent"))
    assert e.mode() != first and e.mode()["seq"] == first["seq"] + 2


def test_a_restated_criterion_keeps_what_the_answer_did_not_speak_to():
    e = _engine()
    root, _ = _goal(e)
    glued = _dc.replace(root.spec, criteria=root.spec.criteria + (
        _dc.replace(root.spec.criteria[0], name="dep__x", depends_on=TaskId("kid")),))
    task = _dc.replace(root, spec=glued)
    spec = I.spec_with(task, [{"name": "g", "description": "G, restated", "check": [
        {"behaviour": "b", "command": "test -d . && echo 0", "expect": "0"}]}])
    assert [c.name for c in spec.criteria] == ["g", "dep__x"], "the Dep glue would be severed silently"


def test_one_node_is_asked_one_question_at_a_time():
    e = _engine(Mode.AUTO)
    _goal(e)
    nodes = [str(n) for n, _ in I.open_questions(e)]
    assert len(nodes) == len(set(nodes))


def test_a_review_that_left_no_verdict_is_not_progress(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "1")                          # the gate this question is about
    e = _engine(Mode.AUTO)
    _goal(e)
    e.wait_idle()
    assert not e.split_holes(TaskId("root")), "precondition: only the Level-2 verdict is missing"
    assert (TaskId("root"), "plan") in I.open_questions(e), "the plan gate holds the children"
    verbs = I.Verbs(llm=None, busy=None, review=lambda engine, node: {}, refine=None)
    with pytest.raises(I.Unavailable):
        # neither progress nor the issuer's failure: the model layer did not answer, and the node is
        # asked again later, uncounted (a rate limit must not close a goal)
        I.settle(e, _Roster(), TaskId("root"), "plan", "exec-1", verbs)


def test_a_restated_probe_keeps_its_pinned_inputs():
    e = _engine()
    root, _ = _goal(e)
    c = root.spec.criteria[0]
    pinned = _dc.replace(c, check=(_dc.replace(c.check[0], inputs=(("in.txt", "x"),)),))
    task = _dc.replace(root, spec=_dc.replace(root.spec, criteria=(pinned,)))
    p = pinned.check[0]
    spec = I.spec_with(task, [{"name": c.name, "description": "restated", "check": [
        {"behaviour": p.behaviour, "command": p.command, "expect": p.expect}]}])
    assert spec.criteria[0].check[0].inputs == (("in.txt", "x"),), "the corpus would be dropped"


def test_a_plan_repair_does_not_spend_the_re_issue_budget():
    e = _engine(Mode.AUTO)
    root, _ = _goal(e)
    ok, why = I.apply_move(e, TaskId("root"), "plan", "exec-1", {
        "move": "add_criterion", "justification": "the goal also needs H",
        "criteria": [{"name": "h", "description": "H holds", "check": [
            {"behaviour": "b", "command": "test -d . && echo 0", "expect": "0"}]}]})
    assert ok, why
    assert I.extensions_granted(e, TaskId("root")) == 0, "a repair is not a re-issue of the contract"


def test_with_no_mode_a_registered_issuers_node_is_not_the_systems_to_decide():
    e = _engine()
    _goal(e)
    assert I.system_mover(e, _Roster(), TaskId("root"), "plan") is None
    assert I.system_mover(e, _Roster(), TaskId("root"), "escalation") is None


class _Roster:
    """The two registered executors of this project, as the dispatcher's roster answers."""
    _ids = {"exec-1": {"kind": "llm-executor", "project": "p", "workdir": "."},
            "exec-2": {"kind": "llm-executor", "project": "p", "workdir": "."}}

    def get(self, agent_id):
        return self._ids.get(str(agent_id))


def test_the_decomposer_challenges_a_defect_of_its_own_packet_to_the_packets_issuer():
    """§11.5, §9.7: a plan-gate defect sourced in the node's OWN contract is no split's to repair — the decomposer's
    report of it is a CHALLENGE to the packet's issuer. A system-held parent had no such move between its consent
    and its delivery round: its plan question offered split moves and a dispute of the finding only."""
    e = _engine(Mode.AUTO)
    _goal(e)
    _admit(e, "kid", _kid("kid.a", ["k"], criterion("a", "A holds")))
    kid = TaskId("kid")
    mover = I.system_mover(e, _Roster(), kid, "plan")
    assert mover == str(e.graph.get_task(kid).assignee), "the plan question is the node's executor's"
    assert I.apply_move(e, kid, "plan", mover, {"move": "challenge", "justification": ""})[0] is False, \
        "a challenge names what is defective"
    ok, why = I.apply_move(e, kid, "plan", mover, {"move": "challenge", "items": ["k"],
                                                   "justification": "k cannot be decided by any procedure"})
    assert ok, why
    e.wait_idle()
    assert e.graph.get_task(kid).state == State.CHALLENGED
    assert (e.challenge_reason(kid) or "").startswith("[k] ")
    assert dict(I.open_questions(e)).get(kid) == "dispute", "the packet's issuer now owes the answer"
    assert I.system_mover(e, _Roster(), kid, "dispute") == str(e.graph.issuer_of(kid)) != mover


def test_a_rejected_challenge_is_seen_and_spends_the_plans_budget():
    """Rejected, the challenge returns the node to the same findings: unseen by the next plan turn and ending the plan
    episode, it was raised again without end where the issuer is a holder no machine budget bounds (critic, 2026-10-07:
    14 rounds, nothing spent)."""
    e = _engine(Mode.AUTO)
    _goal(e)
    _admit(e, "kid", _kid("kid.a", ["k"], criterion("a", "A holds")))
    kid = TaskId("kid")
    mover = I.system_mover(e, _Roster(), kid, "plan")
    assert I.apply_move(e, kid, "plan", mover, {"move": "challenge", "items": ["k"],
                                                "justification": "k cannot be decided"})[0]
    e.wait_idle()
    e.send_signal_sync(SignalData(signal=Signal.REJECT_CHALLENGE, task_id=kid,
                                  source=AgentId(str(e.graph.issuer_of(kid))), justification="k is decided by its probe"))
    e.wait_idle()
    ctx = I.issuer_context(e, kid, "plan")
    assert "k cannot be decided" in ctx and "k is decided by its probe" in ctx
    I.apply_move(e, kid, "plan", mover, {"move": "challenge", "items": ["k"], "justification": "second try"})
    e.wait_idle()
    issuer = str(e.graph.issuer_of(kid))
    e.send_signal_sync(SignalData(signal=Signal.ACCEPT_CHALLENGE, task_id=kid, source=AgentId(issuer),
                                  new_spec=e.graph.get_task(kid).spec))
    e.wait_idle()
    assert "REJECTED" not in I.issuer_context(e, kid, "plan"), "an answered, re-versioned contract is no longer that one"
    before = (e.tally("admitted:g"), e.tally("answers:g:plan:0"))
    I._answered(e, "g", "plan", {"status": "applied", "move": "challenge"}, kid)
    assert (e.tally("admitted:g"), e.tally("answers:g:plan:0")) == (before[0], before[1] + 1)


def test_the_issuers_context_builds_on_a_real_tree_for_every_question():
    """The context read a field no Spec has (`mappings`) — on any node with a parent or children it
    raised before the model was ever called, so no machine issuer answered in a real graph."""
    e = _engine(Mode.AUTO)
    _goal(e)
    e.wait_idle()
    for node in ("root", "kid"):
        for q in I.QUESTIONS:
            assert "# The question" in I.issuer_context(e, TaskId(node), q)


def test_a_question_whose_answers_keep_failing_is_asked_rarely_never_muted(tmp_path):
    """A model call that does not complete is not the issuer's decision and closes nothing. Muting the
    node after a count of such settles latched on its generation: an outage of under an hour silenced
    every later question — a dispute, an escalation — and the node's bounds then cancelled the goal.
    The wait doubles up to a cap instead; after it passes, the node is asked again."""
    e, agents = _auto_goal(tmp_path)
    task = e.graph.get_task(TaskId("root"))
    gen = f"root#{task.iteration}#{task.reopens}"
    asked = []

    def claim(key):
        asked.append(key)
        return False                      # never run: the test is about whether it is ASKED

    I.answer_open_questions(e, agents, claim, None, None, None, {gen: (0, 50, 0.0)})
    assert asked == ["q:root"], "however many settles failed, the question is asked once its wait passed"
    assert I.backoff(50) == I.MAX_BACKOFF_S and I.backoff(0) == I.BACKOFF_S


def _sweeps(e, agents, settles, monkeypatch):
    """Run one sweep per scripted settle outcome; return the nodes the machine issuer closed."""
    closed, script = [], iter(settles)
    monkeypatch.setattr(I, "settle", lambda *a, **k: next(script))
    monkeypatch.setattr(I, "_close", lambda *a, **k: closed.append(a[2]) or {"status": "cancelled"})
    ledger, cap = {}, threading.Semaphore(1)
    for _ in settles:
        before = set(threading.enumerate())
        I.answer_open_questions(e, agents, lambda k: True, lambda *a, **k: None, cap, None, ledger)
        for th in set(threading.enumerate()) - before:
            th.join(5)
    return closed


def _auto_goal(tmp_path):
    e = _engine(Mode.AUTO)
    _goal(e)
    _uncarried(e, str(e.graph.issuer_of(TaskId("kid"))))
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    agents.register("exec-1", "llm-executor", workdir=str(tmp_path))
    return e, agents


def test_a_converging_plan_is_not_closed_on_a_fix_no_review_has_read(tmp_path, monkeypatch):
    """Each applied plan fix counted as a settle that moved nothing (three closed the AUTO root — the user's
    goal — before the review of the third ran), and then as an answer under a cap of twelve (the same, at
    twelve). A plan whose reviews keep moving is closed by neither: fix, review, fix, review…"""
    e, agents = _auto_goal(tmp_path)
    fix, review = {"status": "applied", "kind": "fix"}, {"status": "applied", "kind": "review"}
    assert _sweeps(e, agents, [fix, review] * 10, monkeypatch) == []


def test_a_plan_episode_is_bounded_but_never_closed_on_a_fix_no_review_has_read(tmp_path, monkeypatch):
    """A plan's answers are bounded per episode (a measure read off the gate's contents between reviews let
    a plan grow its root without bound: hole and finding keys change for reasons other than convergence).
    At the bound the node is closed — unless its review is due, which then runs first."""
    e, agents = _auto_goal(tmp_path)
    fix, review = {"status": "applied", "kind": "fix"}, {"status": "applied", "kind": "review"}
    assert _sweeps(e, agents, [fix] * I.MAX_PLAN_ANSWERS, monkeypatch) == []
    monkeypatch.setattr(I, "review_due", lambda *a: True)
    assert _sweeps(e, agents, [review], monkeypatch) == [], "the due review runs before any close"
    monkeypatch.setattr(I, "review_due", lambda *a: False)
    assert _sweeps(e, agents, [fix], monkeypatch) == [TaskId("root")]


def test_whatever_closes_the_plan_question_ends_its_episode(tmp_path, monkeypatch):
    """A plan cleared once — by a review, or by a dispute of its last finding — and reopened later (a child
    re-issued) starts with its budget whole: only a review's opening ended the episode, so a plan cleared by
    disputes came back already spent and its converging second episode was cancelled."""
    e, agents = _auto_goal(tmp_path)
    fix = {"status": "applied", "kind": "fix", "move": "revise_child"}
    closes_once = {"armed": False}
    real = I.open_questions

    def questions(eng):
        if closes_once["armed"]:          # the read right after the closing answer: the question is gone
            closes_once["armed"] = False
            return []
        return real(eng)                  # ...and on the next sweep a re-issued child has reopened it
    monkeypatch.setattr(I, "open_questions", questions)

    def settles():
        for _ in range(I.MAX_PLAN_ANSWERS - 1):
            yield fix
        closes_once["armed"] = True       # a dispute clears the last finding
        yield dict(fix, move="dispute")
        for _ in range(5):
            yield fix
    script = settles()
    closed, served = [], []
    monkeypatch.setattr(I, "settle", lambda *a, **k: served.append(1) or next(script))
    monkeypatch.setattr(I, "_close", lambda *a, **k: closed.append(a[2]) or {"status": "cancelled"})
    ledger, cap = {}, threading.Semaphore(1)
    for _ in range(I.MAX_PLAN_ANSWERS + 5):
        before = set(threading.enumerate())
        I.answer_open_questions(e, agents, lambda k: True, lambda *a, **k: None, cap, None, ledger)
        for th in set(threading.enumerate()) - before:
            th.join(5)
    assert closed == [] and len(served) == I.MAX_PLAN_ANSWERS + 5, (closed, len(served))


def test_disputes_do_not_spend_a_plans_budget(tmp_path, monkeypatch):
    """A fix stales the review and its disputes with it, so a rightly disputed finding comes back at every
    review; counted, the disputes cancelled a converging plan under dispute-first order."""
    e, agents = _auto_goal(tmp_path)
    dispute = {"status": "applied", "kind": "fix", "move": "dispute"}
    assert _sweeps(e, agents, [dispute] * (I.MAX_PLAN_ANSWERS * 2), monkeypatch) == []


def test_a_semi_goal_with_no_split_is_not_delivered_by_its_holder():
    """SEMI is a boundary in the plan's depth; a goal with no split has nothing below it, and its holder
    doing all the work is SOLO under another name — measured twice, the semi holder authored a childless
    root and wrote everything itself, leaving the system nothing and the study of its issuer no decision."""
    e = _engine(Mode.SEMI)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "accepted_risks": _RISK,
                                       "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    out = TL.TOOLS["signal"](e, "root", "ACCEPT", "agent")
    assert out.get("error") and "split it first" in out["error"], "refused only at DELIVER, the work was all done"
    solo = _engine(Mode.SOLO)
    T.TOOLS["create_task"](solo, "root", {"description": "the goal", "accepted_risks": _RISK,
                                          "criteria": [criterion("g", "G holds")]})
    solo.wait_idle()
    TL.TOOLS["signal"](solo, "root", "ACCEPT", "agent")
    assert not TL.TOOLS["signal"](solo, "root", "DELIVER", "agent", result="mine").get("error")


def test_the_split_the_semi_refusal_asks_for_is_reachable_by_the_holders_own_call():
    """The refusal of a childless semi ACCEPT names its lift: split it. Measured live, the holder then called
    `auto_decompose(executor="agent")`, was refused with `set_mode` as the way out — the user's choice, not
    its own move — asked to switch to solo and stopped. The refusal must name the holder's own lift."""
    e = _engine(Mode.SEMI)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "accepted_risks": _RISK,
                                       "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    out = TL.TOOLS["auto_decompose"](e, "split the goal", root_id="root", executor="agent")
    assert out.get("error") and "without `executor`" in out["error"], out
    assert "set_mode" not in out["error"], "the lift is the holder's own call, not the user's mode"


def test_the_machine_issuer_may_not_dispute_a_finding_already_disputed():
    """A dispute of a finding already disputed closes nothing; uncounted, it could be paid for without end."""
    e = _engine(Mode.AUTO)
    root, kid = _goal(e)
    e._graph._storage.store_critique(TaskId("root"), json.dumps({
        "semantic_covered": False, "criteria_verdicts": [{"criterion": "g", "verdict": "sufficient"}],
        "conflicts": [{"between": ["kid", "root"], "why": "f1"}, {"between": ["kid", "root"], "why": "f2"}]}))
    r = e._graph.get_task(TaskId("root"))
    r.verified = True
    e._graph.save_task(r)
    (first, *_) = e.open_l2_findings(TaskId("root"))
    assert I.apply_move(e, TaskId("root"), "plan", "agent", {"move": "dispute", "criterion": first,
                                                              "justification": "wrong"})[0]
    done, why = I.apply_move(e, TaskId("root"), "plan", "agent", {"move": "dispute", "criterion": first,
                                                                   "justification": "wrong again"})
    assert not done and "already disputed" in why, why


def test_a_finding_already_disputed_is_not_disputed_again_under_another_spelling():
    """Two findings that differ only by a dash: the issuer's own near-match and the engine's exact match
    were two rules for one key, and a disputed key passed both — the dispute "applied" every time, open
    findings unchanged, nothing counted (critic round 7). One resolver: a disputed finding is refused."""
    e = _engine(Mode.AUTO)
    _goal(e)
    e._graph._storage.store_critique(TaskId("root"), json.dumps({
        "semantic_covered": False, "criteria_verdicts": [{"criterion": "g", "verdict": "sufficient"}],
        "conflicts": [{"between": ["kid", "root"], "why": "writes x-y"},
                      {"between": ["kid", "root"], "why": "writes x—y"}]}))
    r = e._graph.get_task(TaskId("root"))
    r.verified = True
    e._graph.save_task(r)
    f1, f2 = e.open_l2_findings(TaskId("root"))
    assert I.apply_move(e, TaskId("root"), "plan", "agent", {"move": "dispute", "criterion": f1,
                                                              "justification": "wrong"})[0]
    done, why = I.apply_move(e, TaskId("root"), "plan", "agent", {"move": "dispute", "criterion": f1,
                                                                   "justification": "wrong again"})
    assert not done and "already disputed" in why, why
    assert e.open_l2_findings(TaskId("root")) == [f2], "the other finding took a dispute written for this one"


def test_the_builder_does_not_take_a_semi_goal_it_did_not_split(monkeypatch):
    """The rule lived at the door, and `auto_decompose`'s own builder accepted the root inside the process
    BEFORE building a split — a build whose model proposed no children left a childless root in work, and
    the holder was refused only at DELIVER, the whole work done first (critic round 7)."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = _engine(Mode.SEMI)
    e.record_root_issuer(TaskId("root"), AgentId("agent"))
    build_graph_live({"name": "g", "subtasks": [], "mappings": [], "deps": [], "accepted_risks": _RISK,
                      "root_criteria": [{"name": "g", "description": "G holds", "check": [
                          {"behaviour": "b", "command": "test -d . && echo 0", "expect": "0"}]}]},
                     "the goal", e, "root", assignee="agent", child_assignee="exec-1")
    e.wait_idle()
    assert e.graph.get_state(TaskId("root")) == State.OFFERED, "taken with nothing below it"


def test_a_node_the_semi_holder_holds_below_the_root_is_not_taken_without_a_split():
    """With a boundary of 2 the holder holds depth 1 too; a child it holds and works itself is the same
    SOLO under another name one level down — the rule is on the held node, not on the root (critic round 7)."""
    e = _engine(Mode.SEMI, 2)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G")]})
    _admit(e, "root", _kid("kid", ["g"], criterion("k", "K"), description="the whole thing"))
    assert str(e.graph.get_task(TaskId("kid")).assignee) == "agent"
    assert not TL.TOOLS["signal"](e, "root", "ACCEPT", "agent").get("error"), "the root has its split"
    out = TL.TOOLS["signal"](e, "kid", "ACCEPT", "agent")
    assert out.get("error") and "split it first" in out["error"], out


def test_work_taken_before_semi_was_chosen_is_not_refused_below_its_boundary():
    """An issued node keeps its Del across a change of mode (Inv-1). A leaf the agent took in SOLO lies
    below the SEMI boundary set later; refusing its DELIVER left one lift — split away work already done
    (critic round 8). The rule reads whether the MODE holds the node, not only whose name it carries."""
    e = _engine(Mode.SOLO)
    _goal(e)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "agent")
    assert TL.TOOLS["signal"](e, "kid", "ACCEPT", "agent").get("accepted"), "the leaf taken in SOLO"
    e.set_mode(Mode.SEMI, None, AgentId("agent"))
    assert not e.held_by_the_user_agent(e.depth_of(TaskId("kid")))
    out = TL.TOOLS["signal"](e, "kid", "DELIVER", "agent", result="done")
    assert not out.get("error"), out


def test_the_next_step_does_not_advise_taking_a_held_node_with_no_split():
    """The step said TAKE, the engine refused the ACCEPT: one wasted call per held node (critic round 8)."""
    e = _engine(Mode.SEMI)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "accepted_risks": _RISK,
                                       "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    step = TL.TOOLS["next_step"](e)
    assert step.get("action") == "revise" and "split it first" in step.get("directive", ""), step


def test_a_held_node_whose_split_was_cancelled_is_told_to_split_not_to_deliver():
    """A root taken UNDER SEMI with its split, every child then cancelled: handing it in is one person's work
    under another mode's name; the step and the engine both say split (critic rounds 9, 13)."""
    e = _engine(Mode.SEMI)
    _goal(e)
    assert TL.TOOLS["signal"](e, "root", "ACCEPT", "agent").get("accepted")
    TL.TOOLS["signal"](e, "kid", "CANCEL", "agent", reason="not needed")
    e.send_signal_sync(SignalData(signal=Signal.CONFIRM_CANCEL, task_id=TaskId("kid"), in_flight="nothing begun",
                                  source=e.graph.get_task(TaskId("kid")).assignee))   # settled: out of the plan (§12.6)
    e.wait_idle()
    assert not e.graph.get_active_children(TaskId("root"))
    step = TL.TOOLS["next_step"](e)
    assert step.get("action") == "revise" and "split it first" in step.get("directive", ""), step
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "agent", result="mine")
    assert out.get("error") and "split it first" in out["error"], out


def test_work_taken_before_semi_is_handed_in_whatever_its_depth():
    """The default boundary moves with the tree, so work the agent took in SOLO was admitted or refused by how
    deep an unrelated branch was (critic round 13). Consent given before the mode is honoured at any depth."""
    e = _engine(Mode.SOLO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal",
                                       "criteria": [criterion("g", "G holds"), criterion("h", "H holds")]})
    _admit(e, "root", *(_kid(kid, [c], criterion(kid, "it holds")) for kid, c in (("a", "g"), ("b", "h"))))
    _admit(e, "a", _kid("a1", ["a"], criterion("x", "X"), description="deeper"))
    TL.TOOLS["signal"](e, "root", "ACCEPT", "agent")
    assert TL.TOOLS["signal"](e, "b", "ACCEPT", "agent").get("accepted")
    e.set_mode(Mode.SEMI, None, AgentId("agent"))
    assert e.held_by_the_user_agent(e.depth_of(TaskId("b"))), "b lies above the moved boundary"
    out = TL.TOOLS["signal"](e, "b", "DELIVER", "agent", result="done")
    assert not out.get("error"), out


def test_a_reassign_the_mode_refuses_names_a_lift_the_caller_can_make():
    """`reassign` takes a name it cannot leave out, and the refusal told it to leave the name out
    (critic round 10). It names the executors the mode would accept."""
    e = _engine(Mode.SEMI)
    _goal(e)
    out = TL.TOOLS["reassign"](e, "kid", "agent")
    assert out.get("error") and "exec-2" in out["error"], out


def test_the_plan_question_carries_what_holders_decided_on_and_not_what_they_did_not():
    """Measured against a holder on one graph (2026-09-25, one plan decision, 4 forks): asked what the decision
    rested on, it named the review's findings WITH reasons and the children's whole contracts — the context gave
    keys and names — and did not use the deadline or the rework count; a repair still reads what failed."""
    e = _engine(Mode.AUTO)
    _goal(e)
    ctx = I.issuer_context(e, TaskId("root"), "plan")
    assert "K holds" in ctx, "the child's criterion text"
    assert "no current review of this version of the plan" in ctx, "⊥ printed as none"
    assert "deadline" not in ctx and "rework" not in ctx and "# What happened" not in ctx
    assert "# The goal" not in ctx, "a root's goal is its own description"
    e._graph._storage.store_critique(TaskId("root"), json.dumps({
        "semantic_covered": False, "criteria_verdicts": [{"criterion": "g", "verdict": "insufficient",
                                                          "why": "K does not entail G"}]}))
    r = e._graph.get_task(TaskId("root"))
    r.verified = True
    e._graph.save_task(r)
    assert "`g` — K does not entail G" in I.issuer_context(e, TaskId("root"), "plan")
    assert "rework" in I.issuer_context(e, TaskId("kid"), "escalation"), "the escalation still reads the trail"
    assert "# What happened" in I.issuer_context(e, TaskId("root"), "repair"), "a repair reads what failed"


def test_a_mode_record_from_before_log_at_honours_earlier_consent():
    """A SEMI record written before `log_at` cannot place itself in the log; read as "after", it refused work
    consented under SOLO, the only lift splitting it away (critic round 14)."""
    e = _engine(Mode.SOLO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "accepted_risks": _RISK,
                                       "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    TL.TOOLS["signal"](e, "root", "ACCEPT", "agent")
    e.set_mode(Mode.SEMI, None, AgentId("agent"))
    rec = {k: v for k, v in e.mode().items() if k != "log_at"}
    e._graph._storage.store_setting("mode", json.dumps(rec))
    assert not TL.TOOLS["signal"](e, "root", "DELIVER", "agent", result="done").get("error")


def test_a_held_node_is_not_handed_in_over_a_split_that_has_not_worked():
    """A split that merely EXISTED let the holder deliver its own work over a child nobody started, cancel the
    child, and pass the root on an independent verdict — SOLO under SEMI's name (critic round 15, reproduced).
    The delivery is the aggregate of the children, so it waits for them."""
    e = _engine(Mode.SEMI)
    _goal(e)
    assert TL.TOOLS["signal"](e, "root", "ACCEPT", "agent").get("accepted")
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "agent", result="I wrote it all myself")
    assert out.get("error") and "have not passed" in out["error"], out
    assert e.graph.get_state(TaskId("root")) == State.EXECUTING
    cancelled = TL.TOOLS["signal"](e, "kid", "CANCEL", "agent", reason="not needed")
    e.send_signal_sync(SignalData(signal=Signal.CONFIRM_CANCEL, task_id=TaskId("kid"), in_flight="nothing begun",
                                  source=e.graph.get_task(TaskId("kid")).assignee))   # settled: out of the plan (§12.6)
    e.wait_idle()
    assert "execute it directly" not in json.dumps(cancelled, default=str), "advice the engine refuses"
    assert "split it first" in TL.TOOLS["signal"](e, "root", "DELIVER", "agent", result="mine").get("error", "")


def test_a_revision_of_work_taken_before_semi_is_consented_again():
    """Work consented under SOLO is kept under a later SEMI at DELIVER; a revision re-offers the SAME work, so
    refusing the re-consent would leave only splitting it away (critic round 15)."""
    e = _engine(Mode.SOLO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "accepted_risks": _RISK,
                                       "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    TL.TOOLS["signal"](e, "root", "ACCEPT", "agent")
    e.set_mode(Mode.SEMI, None, AgentId("agent"))
    TL.TOOLS["edit_criteria"](e, "root", [criterion("g", "G holds"), criterion("h", "H holds")])
    e.wait_idle()
    assert e.graph.get_state(TaskId("root")) == State.OFFERED
    assert TL.TOOLS["signal"](e, "root", "ACCEPT", "agent").get("accepted")


def _run_child(e, kid):
    """The system's executor takes, delivers and has the child passed on an independent verdict."""
    who = str(e.graph.get_task(TaskId(kid)).assignee)
    for s, kw in ((Signal.ACCEPT, {}), (Signal.DELIVER, {"result": "done"})):
        e.send_signal_sync(SignalData(signal=s, task_id=TaskId(kid), source=AgentId(who), **kw))
        e.wait_idle()
    instrument_passes(e, TaskId(kid))
    TL.TOOLS["signal"](e, kid, "PASS", str(e.graph.issuer_of(TaskId(kid))))
    e.wait_idle()


def test_work_taken_before_semi_and_then_split_waits_for_its_children(monkeypatch):
    """The pre-mode exemption is about a MISSING split only: a node consented under SOLO and split under SEMI was
    handed in over a child nobody started, the child cancelled, the root passed (critic round 16)."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = _engine(Mode.SOLO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "accepted_risks": _RISK,
                                       "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    TL.TOOLS["signal"](e, "root", "ACCEPT", "agent")
    e.set_mode(Mode.SEMI, None, AgentId("agent"))
    _admit(e, "root", _kid("kid", ["g"], criterion("k", "K holds"), description="a part"))
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "agent", result="all mine")
    assert out.get("error") and "have not passed" in out["error"], out
    rec = {k: v for k, v in e.mode().items() if k != "log_at"}          # a record older than `log_at`
    e._graph._storage.store_setting("mode", json.dumps(rec))
    assert "have not passed" in TL.TOOLS["signal"](e, "root", "DELIVER", "agent", result="mine").get("error", "")


def test_a_revision_of_work_taken_before_semi_is_handed_in_after_its_re_consent():
    """Reading the LATEST consent moved the refusal from the offer to the delivery (critic round 16): the
    re-ACCEPT came after the mode, and DELIVER then said "split it first"."""
    e = _engine(Mode.SOLO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "accepted_risks": _RISK,
                                       "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    TL.TOOLS["signal"](e, "root", "ACCEPT", "agent")
    e.set_mode(Mode.SEMI, None, AgentId("agent"))
    TL.TOOLS["edit_criteria"](e, "root", [criterion("g", "G holds"), criterion("h", "H holds")])
    e.wait_idle()
    assert TL.TOOLS["signal"](e, "root", "ACCEPT", "agent").get("accepted")
    assert not TL.TOOLS["signal"](e, "root", "DELIVER", "agent", result="done").get("error")


def test_a_held_root_in_rework_is_not_told_to_fix_it_by_hand(monkeypatch):
    """After a root FAIL the holder adds a repair child; the step said "FIX AND RE-DELIVER 'root'" — a DELIVER
    the engine refuses, and in semi an instruction to do the work by hand (critic round 16)."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = _engine(Mode.SEMI)
    _goal(e)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "agent")
    _run_child(e, "kid")
    assert not TL.TOOLS["signal"](e, "root", "DELIVER", "agent", result="aggregate").get("error")
    e.record_exec_verdict(TaskId("root"), "FAIL", ["g"], "validate_result",
                          per_criterion=[{"criterion": "g", "verdict": "fail", "evidence": "g broke"}])
    TL.TOOLS["signal"](e, "root", "FAIL", "agent", failed_criteria=["g"])
    T.TOOLS["create_task"](e, "fix", {"description": "repair g", "criteria": [criterion("f", "F holds")]},
                           parent_id="root", covers=["g"])
    e.wait_idle()
    for s in TL.TOOLS["next_steps"](e).get("steps", []):
        assert not (s.get("task_id") == "root" and "DELIVER" in (s.get("directive") or "")), s
    assert "DELIVER" not in TL.TOOLS["available_actions"](e, "root", "agent").get("actions", [])
    _run_child(e, "fix")
    assert not TL.TOOLS["signal"](e, "root", "DELIVER", "agent", result="aggregate").get("error")


def test_the_actions_offered_on_a_held_node_are_the_ones_the_engine_admits():
    e = _engine(Mode.SEMI)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "accepted_risks": _RISK,
                                       "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    out = TL.TOOLS["available_actions"](e, "root", "agent")
    assert "ACCEPT" not in out.get("actions", []), out


def test_a_held_node_is_not_handed_in_while_its_split_leaves_a_criterion_uncarried(monkeypatch):
    """The delivery waits for what the PASS waits for, the plan's Syntactic level included: a criterion added to
    the root with no child to carry it was delivered as the holder's own work and covered afterwards by a child
    that printed "ok" (critic round 17)."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = _engine(Mode.SEMI)
    _goal(e)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "agent")
    _run_child(e, "kid")
    TL.TOOLS["edit_criteria"](e, "root", [criterion("g", "G holds"), criterion("h", "H holds")])
    e.wait_idle()
    TL.TOOLS["signal"](e, "root", "ACCEPT", "agent")
    out = TL.TOOLS["signal"](e, "root", "DELIVER", "agent", result="aggregate + H written by me")
    assert out.get("error") and "does not carry its contract" in out["error"], out
    step = TL.TOOLS["next_step"](e)
    assert step.get("task_id") == "root" and "COVER THE PLAN" in step.get("directive", ""), step


def test_moving_semis_boundary_does_not_turn_semi_consent_into_consent_before_the_mode():
    """A re-record of the same mode moved `log_at`, so every ACCEPT given under SEMI read as given before it and
    the holder could cancel its split and deliver alone (critic round 17)."""
    e = _engine(Mode.SEMI)
    _goal(e)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "agent")
    e.set_mode(Mode.SEMI, 1, AgentId("agent"), said="keep semi, the root is mine")
    TL.TOOLS["signal"](e, "kid", "CANCEL", "agent", reason="not needed")
    e.send_signal_sync(SignalData(signal=Signal.CONFIRM_CANCEL, task_id=TaskId("kid"), in_flight="nothing begun",
                                  source=e.graph.get_task(TaskId("kid")).assignee))   # settled: out of the plan (§12.6)
    e.wait_idle()
    assert "split it first" in TL.TOOLS["signal"](e, "root", "DELIVER", "agent", result="all mine").get("error", "")


def test_after_a_root_fail_the_held_holder_is_told_to_re_aggregate_not_to_fix_by_hand(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = _engine(Mode.SEMI)
    _goal(e)
    TL.TOOLS["signal"](e, "root", "ACCEPT", "agent")
    _run_child(e, "kid")
    TL.TOOLS["signal"](e, "root", "DELIVER", "agent", result="aggregate")
    e.record_exec_verdict(TaskId("root"), "FAIL", ["g"], "validate_result",
                          per_criterion=[{"criterion": "g", "verdict": "fail", "evidence": "g broke"}])
    TL.TOOLS["signal"](e, "root", "FAIL", "agent", failed_criteria=["g"])
    T.TOOLS["create_task"](e, "fix", {"description": "repair g", "criteria": [criterion("f", "F holds")]},
                           parent_id="root", covers=["g"])
    e.wait_idle()
    _run_child(e, "fix")
    # "touched since the FAIL" is the LOG's order: the gate read it off state_entered_at, and a coarse Windows
    # tick tied the repair child's PASS with the root's FAIL (critic round 18) — a clock that says otherwise
    # must not decide it
    fix = e.graph.get_task(TaskId("fix"))
    fix.state_entered_at = e.graph.get_task(TaskId("root")).state_entered_at - timedelta(seconds=1)
    e._graph.save_task(fix)
    for s in TL.TOOLS["next_steps"](e).get("steps", []):
        if s.get("task_id") == "root":
            assert "Fix exactly that" not in s.get("directive", "") and "not yours to write" in s["directive"], s


def test_the_machine_issuer_can_reshape_a_split_whose_children_need_each_other(monkeypatch):
    """Measured live (AUTO json_parser): a child BLOCKed on a sibling that already depended on it, the Dep cycle
    froze every sibling, and the issuer's only moves added to a child — it restated one unchanged, refused, and
    looped. The canon's re-decomposition drops the issued child (§11.5) and covers around it."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal",
                                       "criteria": [criterion("g", "G holds"), criterion("h", "H holds")]})
    _admit(e, "root", _kid("a", ["g"], criterion("ka", "A holds")),
           _kid("b", ["h"], criterion("kb", "B holds"), criterion("dep__a", "reads a's result", depends_on="a")))
    wa, wb = (str(e.graph.get_task(TaskId(k)).assignee) for k in ("a", "b"))
    e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("a"), source=AgentId(wa)))
    e.send_signal_sync(SignalData(signal=Signal.BLOCK, task_id=TaskId("a"), source=AgentId(wa), reason="needs b",
                                  blocker_task_ids=(TaskId("b"),)))
    e.wait_idle()
    # the BLOCK's record is provisional, not an edge of E_Dep (§15.5): the plan is not frozen over it — the
    # split's issuer is asked to repair its ORDER, which contact refuted
    assert not any("cycle" in h.details for h in e.split_holes(TaskId("root")))
    assert (TaskId("a"), "external") in I.open_questions(e)
    assert "`a` needs `b`" in I.issuer_context(e, TaskId("a"), "external")
    issuer = str(e.graph.issuer_of(TaskId("b")))
    ok, why = I.apply_move(e, TaskId("root"), "repair", issuer, {"move": "revise_child", "child_id": "b",
                           "criteria": [criterion("kb", "B holds")], "justification": "drop the loop"})
    assert not ok and "drop_child" in why, why
    assert I.apply_move(e, TaskId("root"), "repair", issuer, {"move": "drop_child", "child_id": "b",
                        "justification": "a and b need each other"})[0]
    e.send_signal_sync(SignalData(signal=Signal.CONFIRM_CANCEL, task_id=TaskId("b"), source=AgentId(wb)))
    e.wait_idle()
    ok, why = I.apply_move(e, TaskId("root"), "plan", issuer, {"move": "add_child", "justification": "b, no loop",
                           "child": {"name": "b", "description": "b", "criteria": [criterion("kb", "B holds")],
                                     "covers": ["h"]}})
    assert ok, why
    rb = e.graph.get_task(TaskId("root.b"))
    assert I.apply_move(e, TaskId("root"), "plan", issuer, {"move": "drop_child", "child_id": "root.b",
                        "justification": "cut wrong again"})[0]
    e.send_signal_sync(SignalData(signal=Signal.CONFIRM_CANCEL, task_id=TaskId("root.b"),
                                  source=AgentId(str(rb.assignee))))
    e.wait_idle()
    ok, why = I.apply_move(e, TaskId("root"), "plan", issuer, {"move": "add_child", "justification": "again",
                           "child": {"name": "b", "description": "b", "criteria": [criterion("kb", "B holds")],
                                     "covers": ["h"]}})
    assert ok and e.graph.get_task(TaskId("root.b_2")) is not None, why   # a dropped child's id does not block the name
    # the re-admission covering around the dropped child carried no mapping onto it (§12.6: out of the plan), so
    # there is nothing left for a re-issue to prune
    assert e.split_holes(TaskId("root")) == []
    assert not I.apply_move(e, TaskId("root"), "plan", issuer, {"move": "resplit", "justification": "prune b"})[0]
    assert not I.apply_move(e, TaskId("root"), "plan", issuer, {"move": "drop_child", "child_id": "b",
                            "justification": "again"})[0], "a settled child stays in the split"


@pytest.mark.parametrize("built_under", [None, Mode.SOLO])
def test_a_plan_built_before_semi_is_handed_over_below_the_boundary_not_worked(built_under):
    """Every node of a plan built before SEMI names the user-agent (Del is kept, Inv-1); the holder was told to
    take the leaf and executed it with no refusal (critic round 18). Below the boundary it hands it over."""
    e = _engine(built_under)
    _goal(e)
    assert str(e.graph.get_task(TaskId("kid")).assignee) == "agent"
    e.set_mode(Mode.SEMI, None, AgentId("agent"), said="semi please")
    assert "ACCEPT" not in TL.TOOLS["available_actions"](e, "kid", "agent").get("actions", [])
    steps = [s for s in TL.TOOLS["next_steps"](e).get("steps", []) if s.get("task_id") == "kid"]
    assert steps and "HAND OVER" in steps[0]["directive"], steps
    assert "hand it over" in TL.TOOLS["signal"](e, "kid", "ACCEPT", "agent").get("error", "")
    out = T.TOOLS["reassign"](e, "kid", "exec-1", reason="other")
    assert not (out or {}).get("error"), out
    assert str(e.graph.get_task(TaskId("kid")).assignee) == "exec-1"


def test_moving_the_boundary_up_hands_a_held_node_over_rather_than_admitting_it():
    """With boundary 2 a depth-1 node the agent holds was refused without a split; one record later, the
    boundary at 1, the same node with the same missing split was taken and delivered (critic round 18)."""
    e = _engine(Mode.SEMI, 2)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("mid", ["g"], criterion("m", "M holds")))
    assert "split it first" in TL.TOOLS["signal"](e, "mid", "ACCEPT", "agent").get("error", "")
    e.set_mode(Mode.SEMI, 1, AgentId("agent"), said="the root is enough for me")
    assert "hand it over" in TL.TOOLS["signal"](e, "mid", "ACCEPT", "agent").get("error", "")


def test_a_reshape_never_dissolves_the_split(monkeypatch):
    """Dropping every child turned the root into a leaf its own executor then worked whole (critic round 19)."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal",
                                       "criteria": [criterion("g", "G holds"), criterion("h", "H holds")]})
    _admit(e, "root", *(_kid(k, [c], criterion(f"k{k}", "it holds")) for k, c in (("a", "g"), ("b", "h"))))
    issuer = str(e.graph.issuer_of(TaskId("a")))
    assert I.apply_move(e, TaskId("root"), "plan", issuer, {"move": "drop_child", "child_id": "a",
                        "justification": "reshape"})[0]
    ok, why = I.apply_move(e, TaskId("root"), "plan", issuer, {"move": "drop_child", "child_id": "b",
                           "justification": "and the other"})
    assert not ok and "last active child" in why, why


def test_a_replacement_named_like_a_drop_still_closing_takes_a_fresh_id(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal",
                                       "criteria": [criterion("g", "G holds"), criterion("h", "H holds")]})
    _admit(e, "root", *(_kid(k, [c], criterion("k" + k[-1], "it holds"))
                        for k, c in (("root.a", "g"), ("root.b", "h"))))
    issuer = str(e.graph.issuer_of(TaskId("root.a")))
    assert I.apply_move(e, TaskId("root"), "plan", issuer, {"move": "drop_child", "child_id": "root.b",
                        "justification": "reshape"})[0]
    assert e.graph.get_state(TaskId("root.b")) == State.CANCELLING
    ok, why = I.apply_move(e, TaskId("root"), "plan", issuer, {"move": "add_child", "justification": "again",
                           "child": {"name": "b", "description": "b", "criteria": [criterion("kb", "B holds")],
                                     "covers": ["h"]}})
    assert ok and e.graph.get_task(TaskId("root.b_2")) is not None, why


def test_a_node_below_the_boundary_is_told_to_hand_over_whatever_is_under_it(monkeypatch):
    """A below-boundary node with a finished split read "COVER THE PLAN … hand it over" (critic round 19)."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = _engine()
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("mid", ["g"], criterion("m", "M holds")))
    _admit(e, "mid", _kid("leaf", ["m"], criterion("l", "L holds")))
    e.set_mode(Mode.SEMI, 1, AgentId("agent"), said="the root is mine")
    mid = e.graph.get_task(TaskId("mid"))
    assert str(mid.assignee) == "agent" and not e.held_by_the_user_agent(e.depth_of(TaskId("mid")))
    assert e.frontier.steps._held_step_verb(mid, e.graph.get_active_children(TaskId("mid"))) == "HAND OVER"


def test_a_child_the_issuer_adds_declares_the_siblings_it_reads(monkeypatch):
    """A machine-added child that checks its siblings' work could not write the Dep (Ch. 2) and could only
    BLOCK on them — measured live, the BLOCKs closed a cycle and froze the plan."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("root.a", ["g"], criterion("ka", "A holds"), description="a"))
    issuer = str(e.graph.issuer_of(TaskId("root.a")))
    _uncarried(e, issuer)                                  # the hole the new child covers
    bad, why = I.apply_move(e, TaskId("root"), "plan", issuer, {"move": "add_child", "justification": "whole",
                            "child": {"name": "guard", "description": "checks the whole", "reads": ["root.zz"],
                                      "criteria": [criterion("kg", "the whole holds")], "covers": ["h"]}})
    assert not bad and "not an active child" in why
    ok, why = I.apply_move(e, TaskId("root"), "plan", issuer, {"move": "add_child", "justification": "whole",
                           "child": {"name": "guard", "description": "checks the whole", "reads": ["root.a"],
                                     "criteria": [criterion("kg", "the whole holds")], "covers": ["h"]}})
    assert ok, why
    assert ("root.a", "root.guard") in {(str(d.from_id), str(d.to_id)) for d in e.get_dependencies()
                                        if not d.provisional}


def test_the_issuers_answer_language_is_pinned_to_the_users_own_sentence():
    """"The language the goal is written in" left it to inference: an English goal got a German plan answer, and
    German criteria in the user's goal. The instruction quotes the user's opening sentence instead."""
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "Build the parser. Then the rest.",
                                       "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("kid", ["g"], criterion("k", "K holds"), description="a part"))
    ctx = I.issuer_context(e, TaskId("kid"), "escalation")
    assert "same language as this sentence the user wrote: «Build the parser.»" in ctx


def test_the_issuer_maps_a_new_criterion_to_the_child_that_already_carries_it(monkeypatch):
    """After an add_criterion the issuer had no move to map an existing child: it restated the child, was
    refused, and looped (measured live)."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = _engine(Mode.AUTO)
    _goal(e)
    issuer = str(e.graph.issuer_of(TaskId("kid")))
    _uncarried(e, issuer)
    assert any("h" in x.details for x in e.split_holes(TaskId("root")))
    ok, why = I.apply_move(e, TaskId("root"), "plan", issuer, {"move": "revise_child", "child_id": "kid",
                           "covers": ["h"], "justification": "kid decides h already"})
    assert ok, why
    e.wait_idle()
    assert e.split_holes(TaskId("root")) == []


def test_the_system_can_take_a_criterion_naming_entry_out_of_the_splits_own_register():
    """A CHECK-4 hole on the root's register — an entry naming the root's own criterion — had no plan move that
    reaches it: the machine answered `revise_child` eighteen times and ran out (AUTO json_parser, 2026-09-27).
    `drop_risk` removes such entries and nothing else: adding would narrow the user's goal at an AUTO root.
    Canon v4.1 §11.5: the split's register "changes only by a re-admission", so no door now writes such an entry into
    an admitted split — the hole is a row written BEHIND that gate, as an older build left it, and `drop_risk`'s own
    write is a re-admission the battery passes once the entry is out."""
    e = _engine(Mode.AUTO)
    good = {"item": "a host kills the process mid-parse", "predictability": "EXTRAORDINARY",
            "justification": "no precedent here", "invalidation_condition": "one occurs", "p": 0.01,
            "impact": "the parse is retried"}
    _goal(e)
    t = e._graph.get_task(TaskId("root"))      # behind the gate: the entry naming `g` in the split's own register
    t.register = Register(T._accepted_risks_from([good, {"item": "g may fail on deep input",
                                                         "predictability": "EXTRAORDINARY"}, DENIAL_ENTRY]))
    e._graph.save_task(t)
    e._recompute_checks(TaskId("root"))
    assert any(h["check"].startswith("CHECK-4") for h in T.list_holes(e)["holes"])
    root = e.graph.get_task(TaskId("root"))
    assert "g may fail on deep input" in I.issuer_context(e, TaskId("root"), "plan")     # in view, root included
    assert not I.MOVES["drop_risk"](e, root, "exec-1", {"items": [good["item"]]}, "", None)[0]   # not flagged
    ok, why = I.MOVES["drop_risk"](e, root, "exec-1", {"items": ["g may fail on deep input"]}, "why", None)
    assert ok, why
    assert [n.item for n in register_of(e.graph.get_task(TaskId("root"))).items if not n.denial] == [good["item"]]
    assert not any(h["check"].startswith("CHECK-4") for h in T.list_holes(e)["holes"])


def _split(fits: bool, whole: bool = True) -> dict:
    kid = lambda i: {"id": i, "name": i, "description": i, "volume": "~150 lines, 4 checks",
                     "fits_one_session": fits,
                     "criteria": [criterion(f"{i}_ok", f"{i} holds")]}
    return {"name": "g", "root_criteria": [criterion("g", "G holds")], "subtasks": [kid("a"), kid("b")],
            "mappings": [{"criterion": "g", "child_id": "a"}, {"criterion": "g", "child_id": "b"}],
            "deps": [], "accepted_risks": _RISK, "scope": [],
            "whole_volume": "~300 lines, 9 checks", "whole_fits_one_session": whole}


def test_under_auto_a_split_one_session_carries_stays_with_its_executor_and_the_seam_is_at_its_top():
    """κ bounds executing and checking (§3.7); below it the executor presents one result (§10.3). A split the
    decomposer judged to fit one session of the executor keeps the parent's Del — no seam, no validation and
    no wait per piece — and the same goal as a leaf of a larger plan would get the same answer. The judgement
    is kept beside the contract and read back by a refine round."""
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "accepted_risks": _RISK,
                                       "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    build_graph_live(_split(True), "the goal", e, assignee=str(e.graph.get_task(TaskId("root")).assignee))
    kids = e.graph.get_active_children(TaskId("root"))
    assert {str(k.assignee) for k in kids} == {str(e.graph.get_task(TaskId("root")).assignee)}
    assert e.fits_one_session(TaskId("root"))
    assert not e.observed_here(kids[0].id) and e.observed_here(TaskId("root"))
    got = extract_spec(e)
    assert got["whole_fits_one_session"] is True and got["subtasks"][0]["fits_one_session"] is True


def test_under_auto_a_split_past_one_session_puts_a_seam_on_every_piece():
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "accepted_risks": _RISK,
                                       "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    root_del = str(e.graph.get_task(TaskId("root")).assignee)
    build_graph_live(_split(True, whole=False), "the goal", e, assignee=root_del)
    kids = e.graph.get_active_children(TaskId("root"))
    assert all(str(k.assignee) != root_del for k in kids)
    assert all(e.observed_here(k.id) for k in kids)


def test_two_holes_one_revision_opened_are_lifted_by_one_reshape(monkeypatch):
    """C9-MOVES: the issuer adds criterion `h` while the split's register already names `h` — a coverage hole and a
    register hole at once. Each single move is a partial re-admission and is refused for the hole it leaves; the
    decomposer's one act lifting both is `reshape` (§11.5: the split and its register change only by a re-admission,
    the battery over the split as it will then stand)."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = _engine(Mode.AUTO)
    _goal(e)
    names_h = {"item": "h may misbehave on empty input", "predictability": "EXTRAORDINARY",
               "justification": "no precedent here", "invalidation_condition": "one occurs", "p": 0.01,
               "impact": "a retry"}
    T.TOOLS["decompose"](e, "root", [_kid("a", ["g"], criterion("ka", "A holds"))],
                         accepted_risks=_RISK + [names_h])
    e.wait_idle()
    root = e.graph.get_task(TaskId("root"))
    actor = str(root.assignee)
    assert I.MOVES["add_criterion"](e, root, actor, {"criteria": [criterion("h", "H holds")]}, "the goal grew", None)[0]
    e.wait_idle()
    holes = {h["check"].split(":")[0] for h in T.list_holes(e, "root")["holes"]}
    assert {"CHECK-1", "CHECK-4"} <= holes, holes
    root = e.graph.get_task(TaskId("root"))
    child = {"name": "h part", "description": "carries h", "criteria": [criterion("kh", "H part holds")], "covers": ["h"]}
    assert not I.MOVES["add_child"](e, root, actor, {"child": child}, "cover h", None)[0]
    assert not I.MOVES["drop_risk"](e, root, actor, {"items": [names_h["item"]]}, "names h", None)[0]
    ok, why = I.MOVES["reshape"](e, root, actor, {"children": [child], "items": [names_h["item"]]}, "both at once", None)
    assert ok, why
    e.wait_idle()
    assert not T.list_holes(e, "root")["holes"]
    e.stop()


def test_a_dispute_rejected_without_contact_is_not_a_reason_to_close_the_node(tmp_path):
    """A rejection whose run used no shell is refused — and is not one of the answers that close a node: the dispute
    is not adjudicated yet. Counted as unproductive, three such sweeps cancelled the node whose challenge nobody had
    run (critic over session a597fc08) — `head`'s end, sooner. MAX_ANSWERS still bounds the question."""
    e = _engine(Mode.AUTO)
    _goal(e)
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    for a in ("exec-1", "exec-2"):
        agents.register(a, "llm-executor", workdir=str(tmp_path))
    ex = str(e.graph.get_task(TaskId("kid")).assignee)
    T.signal(e, "kid", "ACCEPT", ex)
    T.signal(e, "kid", "CHALLENGE", ex, reason="criterion k: the oracle prints its own path")
    e.wait_idle()

    class _NoShell:
        def __init__(self):
            self.calls, self.last_tool_calls = [], {}

        def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
            self.calls.append({})
            self.last_tool_calls = {"Read": 1}
            return '```json\n{"decision": "reject", "justification": "gnulib strips the directory"}\n```'

        def tag_last(self, stage):
            pass

    verbs = I.Verbs(llm=lambda m: _NoShell(), busy=lambda *a: contextlib.nullcontext(), review=None, refine=None,
                    place=lambda engine, agents, node: str(tmp_path))
    ledger, cap = {}, threading.Semaphore(1)
    for _ in range(I.MAX_UNPRODUCTIVE + 1):
        before = set(threading.enumerate())
        I.answer_open_questions(e, agents, lambda k: True, lambda *a, **k: None, cap, verbs, ledger)
        for th in set(threading.enumerate()) - before:
            th.join(10)
        e.wait_idle()
        ledger.update({g: (n, w, 0.0) for g, (n, w, _) in ledger.items()})     # past the backoff
    assert e.graph.get_state(TaskId("kid")) == State.CHALLENGED, "the dispute still stands, the node is not closed"
    assert all(n == 0 for n, _, _ in ledger.values()), ledger


def test_a_child_the_issuer_added_is_found_under_the_name_it_gave():
    """The machine issuer added `root_parser_executor_memory`, stored as `root.root_parser_executor_memory`, then named it
    back without the prefix and was refused twice — "not a child of root" — until the root closed by count
    (GB_sql_database_tmwsep280, 2026-10-15)."""
    e = _engine(Mode.AUTO)
    _goal(e)
    ok, why = I.apply_move(e, TaskId("root"), "plan", "exec-1", {"move": "add_child", "justification": "j", "child": {
        "name": "root_mem", "description": "memory", "covers": ["g"], "criteria": [criterion("m", "M holds")]}})
    assert ok, why
    e.wait_idle()
    assert e.graph.get_task(TaskId("root.root_mem")) is not None
    ok, why = I.apply_move(e, TaskId("root"), "plan", "exec-1",
                           {"move": "drop_child", "justification": "j", "child_id": "root_mem"})
    assert ok, why


def test_a_name_dropped_and_added_again_finds_the_live_child():
    e = _engine(Mode.AUTO)
    _goal(e)
    add = lambda: I.apply_move(e, TaskId("root"), "plan", "exec-1", {"move": "add_child", "justification": "j", "child": {
        "name": "a", "description": "a part", "covers": ["g"], "criteria": [criterion("m", "M holds")]}})
    assert add()[0]
    e.wait_idle()
    assert I.apply_move(e, TaskId("root"), "plan", "exec-1", {"move": "drop_child", "justification": "j", "child_id": "a"})[0]
    e.wait_idle()
    assert add()[0]
    e.wait_idle()
    assert I._child_ref(e, e.graph.get_task(TaskId("root")), "a") == "root.a_2"


def test_a_new_child_reads_a_sibling_named_without_its_parent():
    """`reads: [D1, D2, D3]` for `root.D1`… was "not an active child of root" and, with two more such answers, closed the
    root by count (GB_sql_database_tmx1h7240, 2026-10-15)."""
    e = _engine(Mode.AUTO)
    _goal(e)
    add = lambda child: I.apply_move(e, TaskId("root"), "plan", "exec-1",
                                     {"move": "add_child", "justification": "j", "child": child})
    assert add({"name": "part2", "description": "a part", "covers": ["g"], "criteria": [criterion("p", "P")]})[0]
    e.wait_idle()
    ok, why = add({"name": "glue", "description": "reads the part", "covers": ["g"], "reads": ["part2"],
                   "criteria": [criterion("r", "R holds")]})
    assert ok, why
