"""GL_cc_light1: five parts each waiting on the others through the binary merged into one node, 11 criteria, the whole
compiler, its plan's author having judged three of them past a session. Its executor said so, truly: CHALLENGE, BLOCK,
CHALLENGE, FAIL; the issuer answered REJECT_CHALLENGE or `reassign`, for no move made a split, 40 minutes, tree unchanged.

A merge of parts judged past a session owes its split before work, by the path his judgement opens anywhere else, and its
author reads the cycle. A merge of what fits stays one node. The executor's report has a move of the issuer's that does it.
The refine's model is the one thing faked: what it was given is asserted, and its split goes through the real admission."""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from gfso import delegate as DG, issuer as I, tools as T
from gfso.adapters import worktrees as W
from gfso.adapters.llm.stub import StubLLM
from gfso.core.types import AgentId, Mode, State, TaskId
from gfso.delegate import Dispatcher
from gfso.engine.validation import AdmissionRefused
from gfso.inflight import _inflight
from gfso.roster import AgentRegistry
from gfso.workspaces import _ensure_place, _enter_workspace, _workspace
from tests.support import REGISTER, criterion, make_engine
from tests.test_a_node_works_in_its_own_place import _repo

MERGED = TaskId("root.cg_fe_pp")
LARGE = "the criteria bundle four subsystems: this is more than one sitting"


class _Answers:
    def __init__(self, answer):
        self.text, self.calls = "```json\n" + json.dumps(answer) + "\n```", []

    def complete(self, prompt, context=""):
        self.calls.append({"duration_ms": 1, "output_tokens": 1})
        return self.text

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def _ring(tmp_path, fits):
    """cg, fe and pp, each covering its criterion of the compiler, in a real git base with the plan gate on; contact confirmed
    pp needs cg while the plan has cg reading fe and fe reading pp. `fits` is the plan's author's word on each."""
    base = _repo(tmp_path / "ws")
    e = make_engine(llm=StubLLM(), validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    for a, kind in (("exec-1", "llm-executor"), ("exec-2", "llm-executor"), ("val-1", "llm-validator")):
        agents.register(a, kind, workdir=str(base), project="p")
    e.workforce.publish_executor_pool({"exec-1": "p", "exec-2": "p"})
    e.set_mode(Mode.AUTO, None, AgentId("agent"))
    T.TOOLS["create_task"](e, "root", {"description": "the compiler", "criteria": [
        criterion("g", "G"), criterion("h", "H"), criterion("i", "I")]})
    T.TOOLS["decompose"](e, "root", [{"task_id": f"root.{n}", "covers": [c], "spec": {
        "description": f"the {n}", "criteria": [criterion(f"{n}_ok", f"{n} holds")]}} for n, c in (("pp", "g"), ("fe", "h"), ("cg", "i"))],
        accepted_risks=REGISTER)
    for n, fit in fits.items():
        e.record_session_fit(TaskId(f"root.{n}"), f"about {'400' if fit else '4000'} lines of {n}", fit)
    for producer, consumer in (("root.pp", "root.fe"), ("root.fe", "root.cg")):
        T.TOOLS["add_dependency"](e, producer, consumer)
    e.add_dependency(TaskId("root.cg"), TaskId("root.pp"), discovered=True, glue="its check runs through the binary")
    e.wait_idle()
    e.set_settings({"l2_gate": "1"}, AgentId("agent"), "the gate as it stands by default; the suite's conftest has it off")
    return e, agents, base


def _work(e, agents):
    """What each member committed before the merge."""
    for n in ("pp", "fe", "cg"):
        t = e.graph.get_task(TaskId(f"root.{n}"))
        w = _workspace(e, agents, t)
        _ensure_place(e, agents, t, w)
        (Path(w[1]) / f"{n}.c").write_text(f"/* {n} */\n")
        W.commit_all(w[0], w[1], f"{n} works", "t", branch=w[2])


def _merge(e):
    root = e.graph.get_task(TaskId("root"))
    assert e.dep_order_cycle_children(root.id) and I.merge_the_refuted_cycle(e, root, str(root.assignee)) == {
        "status": "applied", "move": "merge"}
    e.wait_idle()
    kids = {str(k.id) for k in e.graph.get_active_children(root.id)}
    assert len(kids) == 1, kids
    return e.graph.get_task(TaskId(next(iter(kids))))


class _Author:
    """The refine round: what it reads is the node's own contract, as the real one's; its split the real admission's."""

    def __init__(self, e):
        self.e, self.read = e, []

    def __call__(self, en, node):
        t = en.graph.get_task(TaskId(node))
        self.read.append(t.spec.description)
        crits = [c.name for c in t.spec.criteria]
        T.decompose(en, node, [{"task_id": f"{node}.thin", "covers": crits[:1], "spec": {
            "description": "the binary end to end", "criteria": [criterion("thin_ok", "a program compiles and runs")]}},
            {"task_id": f"{node}.rest", "covers": crits[1:], "spec": {
                "description": "the rest, through it", "criteria": [criterion("rest_ok", "all of it holds")]}}],
            accepted_risks=REGISTER)
        en.wait_idle()
        return {"stats": []}


def _dispatcher(e, agents, monkeypatch, author):
    spawned = []
    monkeypatch.setattr(DG, "ISSUER_VERBS", I.Verbs(llm=None, busy=_inflight, review=lambda *a: {"stats": [{"cost_usd": 0}]},
                                                    refine=author, keep=DG._keep_the_place))
    return Dispatcher(e, agents, poll=30, runner=lambda en, tid, *a: spawned.append(str(tid)),
                      consent_runner=lambda en, tid, *a: (spawned.append(str(tid)), {"status": "accepted"})[1], validator_runner=lambda *a, **k: "rejected"), spawned


def _until_split(e, d, node):
    end = time.monotonic() + 20
    while not e.graph.get_active_children(node):
        assert time.monotonic() < end, (I.open_questions(e), e.graph.get_state(node))
        d.dispatch_once()
        time.sleep(0.02)
    e.wait_idle()


def test_a_merge_of_parts_past_a_session_is_split_before_any_work_and_its_parts_carry_theirs(tmp_path, monkeypatch):
    e, agents, _ = _ring(tmp_path, {"pp": False, "fe": False, "cg": True})
    try:
        _work(e, agents)
        node = _merge(e)
        assert e.split_owed(node.id) is not None and "about 4000 lines of pp" in e.session_fit(node.id)["volume"]
        author = _Author(e)
        d, spawned = _dispatcher(e, agents, monkeypatch, author)
        _until_split(e, d, node.id)
        assert str(node.id) not in spawned, "a session spent on a node whose split is owed"
        said = author.read[0]
        assert "each need the others" in said and "thin end to end" in said and "root.cg" in said and "the pp" in said, said
        assert {str(k.id) for k in e.graph.get_active_children(node.id)} == {f"{node.id}.thin", f"{node.id}.rest"}
        for part in e.graph.get_active_children(node.id):
            place, unjoined, _w = _enter_workspace(e, agents, part, [part])
            assert not unjoined and {"pp.c", "fe.c", "cg.c"} <= {p.name for p in Path(place).iterdir()}, (part.id, unjoined)
    finally:
        e.stop()


def test_a_small_merged_pair_still_works_as_one_node(tmp_path, monkeypatch):
    e, agents, _ = _ring(tmp_path, {"pp": True, "fe": True, "cg": True})
    try:
        node = _merge(e)
        assert e.split_owed(node.id) is None and e.session_fit(node.id) is None
        assert "each need the others" not in node.spec.description
        assert (node.id, "split") not in I.open_questions(e)
    finally:
        e.stop()


def _at_work_on_a_leaf(tmp_path, signal):
    e, agents, _ = _ring(tmp_path, {"pp": True, "fe": True, "cg": True})
    node = _merge(e)
    # the plan's review, current (`Engine`'s gate lets the node work)
    e._graph._storage.store_critique(TaskId("root"), json.dumps({"node_id": "root", "gate_passed": True, "semantic_covered": True,
                                                                 "criteria_verdicts": [], "conflicts": [], "model": "t", "ts": "2026-11-06 00:00:00"}))
    e.graph.update_task(TaskId("root"), verified=True)
    assert "error" not in (o := T.signal(e, str(node.id), "ACCEPT", str(node.assignee))), o
    if signal != "ACCEPTED":
        assert "error" not in (o := T.signal(e, str(node.id), signal, str(node.assignee), reason=LARGE)), o
    e.wait_idle()
    return e, agents, node


def test_a_true_challenge_that_the_work_is_past_a_session_has_a_move_that_does_it(tmp_path, monkeypatch):
    e, agents, node = _at_work_on_a_leaf(tmp_path, "CHALLENGE")
    try:
        assert (node.id, "dispute") in I.open_questions(e)
        out = I.issuer_turn(e, node.id, "dispute", str(e.graph.issuer_of(node.id)),
                            _llm=_Answers({"decision": "split", "justification": "so it is"}))
        e.wait_idle()
        assert out["status"] == "applied" and e.split_owed(node.id) is not None, out
        assert e.graph.get_state(node.id) == State.EXECUTING and (node.id, "split") in I.open_questions(e)
        d, _ = _dispatcher(e, agents, monkeypatch, _Author(e))
        _until_split(e, d, node.id)
    finally:
        e.stop()


def test_a_block_saying_so_has_it_too(tmp_path, monkeypatch):
    e, agents, node = _at_work_on_a_leaf(tmp_path, "BLOCK")
    try:
        assert (node.id, "external") in I.open_questions(e), I.open_questions(e)
        out = I.issuer_turn(e, node.id, "external", str(e.graph.issuer_of(node.id)),
                            _llm=_Answers({"move": "split", "justification": LARGE}))
        e.wait_idle()
        assert out["status"] == "applied" and e.graph.get_state(node.id) == State.OFFERED, out
        assert LARGE in e.session_fit(node.id)["volume"] and node.spec.criteria == e.graph.get_task(node.id).spec.criteria
        d, spawned = _dispatcher(e, agents, monkeypatch, _Author(e))
        _until_split(e, d, node.id)
        assert str(node.id) not in spawned
    finally:
        e.stop()


def test_a_node_already_split_or_a_holders_is_not_the_moves(tmp_path, monkeypatch):
    e, agents, node = _at_work_on_a_leaf(tmp_path, "CHALLENGE")
    act = lambda: (True, "")
    try:
        assert "split already" in I._split_owed_with(e, e.graph.get_task(TaskId("root")), LARGE, act)[1]
        monkeypatch.setattr(e, "mode", lambda: None)
        assert "its executor's own move" in I._split_owed_with(e, node, LARGE, act)[1] and e.session_fit(node.id) is None
    finally:
        e.stop()


def test_a_plan_the_user_gave_is_not_offered_the_move(tmp_path, monkeypatch):
    e, agents, node = _at_work_on_a_leaf(tmp_path, "BLOCK")
    try:
        monkeypatch.setattr(I, "users_plan", lambda g: True)
        monkeypatch.setattr(e, "users_plan", lambda: True)
        assert "split" not in I.moves_for(e, node, "external") and e.session_fit(node.id) is None
        assert "only the user" in I._split_owed_with(e, node, LARGE, lambda: (True, ""))[1]
    finally:
        e.stop()


def test_a_split_decided_with_no_contact_is_held_to_the_rule_a_rejection_is(tmp_path, monkeypatch):
    e, agents, node = _at_work_on_a_leaf(tmp_path, "CHALLENGE")
    try:
        monkeypatch.setattr(I, "_ask", lambda *a, **k: ({"decision": "split", "justification": "so it reads"}, {"Read": 1}))
        out = I.issuer_turn(e, node.id, "dispute", str(e.graph.issuer_of(node.id)))
        assert out["status"] == "uncontacted" and "split ran nothing" in out["why"], out
        assert e.session_fit(node.id) is None and e.graph.get_state(node.id) == State.CHALLENGED
    finally:
        e.stop()


def test_a_spent_deadline_names_the_way_and_a_split_not_taken_leaves_no_judgement(tmp_path):
    e, agents, node = _at_work_on_a_leaf(tmp_path, "BLOCK")
    try:
        e.graph.update_task(node.id, deadline=datetime.now() - timedelta(hours=1))
        out = I.issuer_turn(e, node.id, "external", str(e.graph.issuer_of(node.id)),
                            _llm=_Answers({"move": "split", "justification": LARGE}))
        e.wait_idle()
        assert out["status"] == "refused" and "reassign" in out["why"], out
        assert e.split_owed(node.id) is None and e.graph.get_state(node.id) != State.OFFERED
    finally:
        e.stop()


def test_a_session_s_uncommitted_work_reaches_both_parts(tmp_path, monkeypatch):
    e, agents, node = _at_work_on_a_leaf(tmp_path, "CHALLENGE")
    try:
        w = _workspace(e, agents, node)
        _ensure_place(e, agents, node, w)
        (Path(w[1]) / "written.c").write_text("/* uncommitted */\n")
        assert I.issuer_turn(e, node.id, "dispute", str(e.graph.issuer_of(node.id)),
                             _llm=_Answers({"decision": "split", "justification": "so it is"}))["status"] == "applied"
        e.wait_idle()
        d, _ = _dispatcher(e, agents, monkeypatch, _Author(e))
        _until_split(e, d, node.id)
        for part in e.graph.get_active_children(node.id):
            place, unjoined, _w = _enter_workspace(e, agents, part, [part])
            assert not unjoined and (Path(place) / "written.c").exists(), part.id
    finally:
        e.stop()


def test_a_refines_one_part_answer_is_refused_and_its_next_round_lifts_it(tmp_path):
    e, agents, _ = _ring(tmp_path, {"pp": False, "fe": True, "cg": True})
    rounds = []

    def refine(en, node):
        t = en.graph.get_task(TaskId(node))
        rounds.append(node)
        if len(rounds) > 1:
            return _Author(en)(en, node)
        try:
            T.decompose(en, node, [{"task_id": f"{node}.all", "covers": [c.name for c in t.spec.criteria], "spec": {
                "description": "all of it", "criteria": [criterion("all_ok", "it holds")]}}], accepted_risks=REGISTER)
        except AdmissionRefused as no:                # …as `decompose_into`'s repair loop reads it
            return {"error": str(no)}
        return {"stats": []}

    verbs = I.Verbs(llm=None, busy=_inflight, review=None, refine=refine)
    try:
        node = _merge(e)
        out = I.settle(e, agents, node.id, "split", str(node.assignee), verbs)
        assert out["status"] == "refused" and "split of one part" in out["why"] and not e.graph.get_active_children(node.id), out
        assert I.settle(e, agents, node.id, "split", str(node.assignee), verbs)["status"] == "applied"
        assert len(e.graph.get_active_children(node.id)) == 2
    finally:
        e.stop()


def test_a_holders_one_part_at_a_time_on_a_node_owed_its_split_stands(tmp_path):
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.workforce.publish_executor_pool({"exec-1": "p"})
    e.set_mode(Mode.SOLO, None, AgentId("agent"))
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G")]})
    e.wait_idle()
    root = TaskId("root")
    try:
        assert str(e.graph.get_task(root).assignee) == "agent"
        e.record_session_fit(root, "about 4000 lines", False)
        assert e.split_owed(root) is not None
        part = {"description": "a first part", "criteria": [criterion("a_ok", "A")]}
        # …bare on a childless node the split's register is what is owed (CHECK-4), its own rule and its lift named
        said = T.create_task(e, "root.a", part, parent_id="root", covers=["g"])
        assert "CHECK-4" in said["error"] and "split of one part" not in said["error"], said
        T.decompose(e, "root", [{"task_id": "root.a", "covers": ["g"], "spec": part}], accepted_risks=REGISTER)
        out = T.create_task(e, "root.b", {"description": "the next", "criteria": [criterion("b_ok", "B")]}, parent_id="root", covers=["g"])
        e.wait_idle()
        assert "error" not in str(out)[:40] and {str(k.id) for k in e.graph.get_active_children(root)} == {"root.a", "root.b"}, out
    finally:
        e.stop()


def test_a_challenge_under_a_review_gone_stale_opens_its_plan_and_then_the_split_lands(tmp_path, monkeypatch):
    """The root's `plan` opened only for an OFFERED child held by the gate: with its review stale, a CHALLENGED child's `split`
    and `reject` were refused until the clock. Drop b onto a, b settles, a challenges: the rounds below are the dispatcher's."""
    e, agents, node = _at_work_on_a_leaf(tmp_path, "ACCEPTED")
    try:
        root = e.graph.get_task(TaskId("root"))
        e.graph.update_task(root.id, verified=False)
        assert "error" not in (o := T.signal(e, str(node.id), "CHALLENGE", str(node.assignee), reason=LARGE)), o
        e.wait_idle()
        assert (root.id, "plan") in I.open_questions(e) and e.execution_blocked_by(node.id), I.open_questions(e)
        author = _Author(e)

        def review(en, n):
            en._graph._storage.store_critique(TaskId(n), json.dumps({
                "node_id": n, "gate_passed": True, "semantic_covered": True, "criteria_verdicts": [], "conflicts": [],
                "model": "t", "ts": "2026-11-06 00:00:00"}))
            en.graph.update_task(TaskId(n), verified=True)
            return {"stats": [{"cost_usd": 0}]}

        answers = _Answers({"decision": "split", "justification": "so it is"})
        monkeypatch.setattr(DG, "ISSUER_VERBS", I.Verbs(llm=lambda m, **k: answers, busy=_inflight, review=review, refine=author))
        d = Dispatcher(e, agents, poll=30, runner=lambda *a: None, consent_runner=lambda *a: {"status": "accepted"},
                       validator_runner=lambda *a, **k: "rejected")
        _until_split(e, d, node.id)
        assert e.graph.get_task(root.id).verified and answers.calls
    finally:
        e.stop()


