"""A node larger than one session of its executor is worked, not disputed: GL_cc_light1's executor never built the
compiler node a cycle's merge made — eight sessions of 2–11 turns, each a CHALLENGE or a BLOCK "beyond one sitting",
quoting the prompt's own words ("genuinely multi-part beyond one sitting" — a defect to challenge). The engine then
took the executor's word for κ: the issuer's `split`, the planner authoring it, six one-part splits (036b282, 45f3221,
3b8f855) — a judge κ cannot have. κ is the issuer's forecast in the packet (§12.15 Φ3), refuted only by its log.

Now: size is no defect in the executor's prompt or packet; such a node is worked across sessions by the handover,
delivered and validated at its seam by its criteria. A "too large" report is answered by the move that keeps the work
going: REJECT_CHALLENGE returns it to consented work under the same contract (§11.3), a size BLOCK is resolved (it
resumes); the issuer has no `split`; a plan the user gave still stops with the reason. §3.7's "owes a split" stays the
plan author's own judgement at authoring (`split_owed`).

CONTROLS: put back the "beyond one sitting" defect in `executor.md` and the packet test goes red; give the issuer back
`split` and the schema test goes red.
"""
import json
import time
from pathlib import Path

from gfso import delegate as DG, issuer as I, tools as T
from gfso.adapters.llm import budget as B
from gfso.adapters.llm.stub import StubLLM
from gfso.core.types import AgentId, Mode, State, TaskId
from gfso.delegate import Dispatcher, _auto_validate
from gfso.inflight import _inflight
from gfso.packets import CHALLENGE_WHEN
from gfso.roster import AgentRegistry
from gfso.sessions import run_executor
from tests.support import REGISTER, criterion, make_engine
from tests.test_a_child_attached_while_its_whole_is_validated_is_worked import _Validator
from tests.test_a_node_works_in_its_own_place import _fenced, _repo
from tests.test_a_session_hands_over_at_its_context_budget import Worker

LARGE = "the criteria bundle four subsystems: this is more than one sitting"
PROMPT = (Path(I.__file__).parents[1] / "mcp" / "prompts" / "executor.md").read_text(encoding="utf-8")


class _Answers:
    def __init__(self, answer):
        self.text, self.calls, self.prompts = "```json\n" + json.dumps(answer) + "\n```", [], []

    def complete(self, prompt, context=""):
        self.prompts.append(prompt)
        self.calls.append({"duration_ms": 1, "output_tokens": 1})
        return self.text

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def _ring(tmp_path, cycle=False):
    """cg, fe and pp, each covering its criterion of the compiler, in a real git base with the plan gate on, cg reading fe
    and fe reading pp; with `cycle`, contact confirmed pp needs cg."""
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
    for producer, consumer in (("root.pp", "root.fe"), ("root.fe", "root.cg")):
        T.TOOLS["add_dependency"](e, producer, consumer)
    if cycle:
        e.add_dependency(TaskId("root.cg"), TaskId("root.pp"), discovered=True, glue="its check runs through the binary")
    e.wait_idle()
    e.set_settings({"l2_gate": "1"}, AgentId("agent"), "the gate as it stands by default; the suite's conftest has it off")
    return e, agents, base


def _node(e):
    """The first part of the compiler, the one nothing else waits for."""
    return e.graph.get_task(TaskId("root.pp"))


def _reviewed(e, node="root"):
    """The plan's review, current (`Engine`'s gate lets the node work): no model here."""
    e._graph._storage.store_critique(TaskId(node), json.dumps({
        "node_id": node, "gate_passed": True, "semantic_covered": True, "criteria_verdicts": [], "conflicts": [],
        "model": "t", "ts": "2026-11-06 00:00:00"}))
    e.graph.update_task(TaskId(node), verified=True)


class _Builder(Worker):
    """An executor that builds: its context grows a turn at a time past the window's ceiling, so its work goes on in a
    fresh session on the handover; it writes its file and delivers when the work is done."""

    def __init__(self, tid):
        super().__init__(work=30, window=200_000, step=4)
        self.tid, self.cwds = str(tid), []

    def agent_round(self, system, user, allowed_tools, cwd, timeout, max_turns, session):
        self.cwds.append(cwd)
        out = super().agent_round(system, user, allowed_tools, cwd, timeout, max_turns, session)
        if out != "REPORT":
            return out
        (Path(cwd) / "cc.c").write_text("/* the whole compiler */\n")
        return _fenced({"status": "delivered", "summary": f"{self.tid}: built and checked", "self_validation": "PASS"})


def test_size_is_no_defect_in_what_the_executor_is_told():
    assert "beyond one sitting" not in PROMPT and "SIZE is no" in PROMPT
    assert "cannot carry" not in CHALLENGE_WHEN and "size is none of these" in CHALLENGE_WHEN.lower()


def test_a_node_larger_than_a_session_is_worked_across_sessions_delivered_and_validated_at_its_seam(tmp_path):
    e, agents, _base = _ring(tmp_path)
    try:
        node = _node(e)
        _reviewed(e)
        assert "error" not in (o := T.signal(e, str(node.id), "ACCEPT", str(node.assignee))), o
        e.wait_idle()
        builder = _Builder(node.id)
        out = run_executor(e, node.id, str(node.assignee), agents, _llm=builder)
        e.wait_idle()
        assert out["status"] == "delivered", out
        reopened = [p for p in builder.prompts if B.HANDOVER in p]
        assert builder.closed and reopened, "the work did not go on in a second session by the handover"
        assert "beyond one sitting" not in builder.prompts[0]
        assert e.graph.get_state(node.id) == State.VALIDATING
        once = Dispatcher(e, agents, runner=lambda *a: None)
        once._publish_the_roster()                                       # …whose instrument signs for the issuer
        e._events._on_transition.remove(once._on_bus)
        assert _auto_validate(e, node.id, agents, _llm=_Validator(e, node.id)) == "pass"
        e.wait_idle()
        assert e.graph.get_state(node.id) == State.DONE and not e.graph.get_children(node.id)
    finally:
        e.stop()


def _at_work(tmp_path, signal):
    e, agents, _ = _ring(tmp_path)
    node = _node(e)
    _reviewed(e)
    assert "error" not in (o := T.signal(e, str(node.id), "ACCEPT", str(node.assignee))), o
    if signal:
        assert "error" not in (o := T.signal(e, str(node.id), signal, str(node.assignee), reason=LARGE)), o
    e.wait_idle()
    return e, agents, node


def test_a_too_large_challenge_is_answered_by_the_work_going_on_under_its_contract(tmp_path, monkeypatch):
    e, agents, node = _at_work(tmp_path, "CHALLENGE")
    try:
        assert set(I.ISSUER_SCHEMA["properties"]["decision"]["enum"]) == {"accept", "reject"}
        assert "split" not in I.MOVES and all("split" not in q["moves"] for k, q in I.QUESTIONS.items() if k != "split")
        monkeypatch.setattr(I, "_ask", lambda *a, **k: ({"decision": "reject", "justification": "size is no defect: work it"},
                                                        None))
        out = I.issuer_turn(e, node.id, "dispute", str(e.graph.issuer_of(node.id)))
        e.wait_idle()
        assert out["status"] == "applied", out
        assert e.graph.get_state(node.id) == State.EXECUTING, "the work did not resume under its contract"
        assert e.session_fit(node.id) is None and not e.graph.get_children(node.id)
        assert "names no defect" in I.QUESTIONS["dispute"]["ask"]
    finally:
        e.stop()


def test_a_block_saying_only_its_size_resumes_and_no_split_is_made_for_it(tmp_path):
    e, agents, node = _at_work(tmp_path, "BLOCK")
    try:
        assert (node.id, "external") in I.open_questions(e), I.open_questions(e)
        refused = I.issuer_turn(e, node.id, "external", str(e.graph.issuer_of(node.id)),
                                _llm=_Answers({"move": "split", "justification": LARGE}))
        assert refused["status"] == "refused" and e.session_fit(node.id) is None, refused
        out = I.issuer_turn(e, node.id, "external", str(e.graph.issuer_of(node.id)), _llm=_Answers(
            {"move": "resolve_block", "action": "it names no prerequisite: the work is its own", "justification": "size"}))
        e.wait_idle()
        assert out["status"] == "applied" and e.graph.get_state(node.id) == State.EXECUTING, out
        assert not e.graph.get_children(node.id)
    finally:
        e.stop()


def test_a_plan_the_user_gave_still_stops_with_the_reason(tmp_path):
    e, agents, _ = _ring(tmp_path, cycle=True)
    try:
        e.give_users_plan(TaskId("root"))
        assert (TaskId("root"), "repair") in I.open_questions(e)
        out = I.settle(e, agents, TaskId("root"), "repair", str(e.graph.get_task(TaskId("root")).assignee),
                       I.Verbs(llm=None, busy=_inflight, review=None, refine=None))
        assert out["status"] == "users" and "only the user re-plans" in out["why"], out
        assert {str(k.id) for k in e.graph.get_active_children(TaskId("root"))} == {"root.pp", "root.fe", "root.cg"}
    finally:
        e.stop()


def test_a_challenge_under_a_review_gone_stale_opens_its_plan_and_then_is_answered(tmp_path, monkeypatch):
    """The root's `plan` opened only for an OFFERED child held by the gate: with its review stale, a CHALLENGED child's
    answer was refused until the clock. The rounds below are the dispatcher's."""
    e, agents, node = _at_work(tmp_path, None)
    try:
        root = e.graph.get_task(TaskId("root"))
        e.graph.update_task(root.id, verified=False)
        assert "error" not in (o := T.signal(e, str(node.id), "CHALLENGE", str(node.assignee), reason=LARGE)), o
        e.wait_idle()
        assert (root.id, "plan") in I.open_questions(e) and e.execution_blocked_by(node.id), I.open_questions(e)
        answers = _Answers({"decision": "reject", "justification": "size is no defect: work it"})
        monkeypatch.setattr(I, "_ran_a_shell", lambda ran: True)
        monkeypatch.setattr(DG, "ISSUER_VERBS", I.Verbs(llm=lambda m, **k: answers, busy=_inflight,
                                                        review=lambda en, n: (_reviewed(en, n), {"stats": [{"cost_usd": 0}]})[1],
                                                        refine=None))
        d = Dispatcher(e, agents, poll=30, runner=lambda *a: None, consent_runner=lambda *a: {"status": "accepted"},
                       validator_runner=lambda *a, **k: "rejected")
        end = time.monotonic() + 20
        while e.graph.get_state(node.id) == State.CHALLENGED:
            assert time.monotonic() < end, (I.open_questions(e), e.graph.get_state(node.id))
            d.dispatch_once()
            time.sleep(0.02)
        e.wait_idle()
        assert e.graph.get_task(root.id).verified and answers.calls and e.graph.get_state(node.id) == State.EXECUTING
    finally:
        e.stop()
