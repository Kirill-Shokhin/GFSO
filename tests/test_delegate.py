"""Delegation machinery: registry roundtrip + kind semantics; the dispatcher's autostart-by-Del
(one spawn per node×iteration, unregistered = passive, kind-guard); the executor report → wrapped
FSM signals (consent = the executor's own report); auto-validation with auto-verdict (FAIL →
FSM REWORK loop); unparsed reports never signal. All with fake agent-runners — no network."""
import json

import pytest

from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.llm.stub import StubLLM
from gfso.core.types import TaskId
from gfso import tools as T
from gfso.delegate import AgentRegistry, Dispatcher, run_executor, EXECUTOR_SCHEMA


def _eng():
    e = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=True)
    e.start()
    return e


def _agents(tmp_path, *entries):
    a = AgentRegistry(path=str(tmp_path / "agents.json"))
    for aid, kind in entries:
        a.register(aid, kind)
    return a


def _fenced(payload):
    return "```json\n" + json.dumps(payload) + "\n```"


class _AgentLLM:
    """Fake agent-runner returning queued reports (executor round(s), then validator rounds)."""
    def __init__(self, *texts):
        self._texts = list(texts)
        self.calls = []
        self.packets = []

    def run_agent(self, system, user, allowed_tools, cwd=None):
        self.packets.append({"system": system, "user": user, "tools": allowed_tools, "cwd": cwd})
        self.calls.append({"duration_ms": 900, "output_tokens": 70})
        return self._texts.pop(0)

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def _node(e, tid="n1", assignee="exec-1"):
    T.create_task(e, tid, {"name": "Nail", "description": "hammer a nail",
                           "criteria": [{"name": "flush", "description": "nail is flush"}]},
                  assignee=assignee)


def test_registry_roundtrip_and_kinds(tmp_path):
    a = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    assert a.get("exec-1")["kind"] == "llm-executor"
    assert a.default_validator() == "val-1"
    assert a.get("nobody") is None                       # unregistered = human
    with pytest.raises(ValueError):
        a.register("x", "human")                         # humans are never registered
    b = AgentRegistry(path=str(tmp_path / "agents.json"))
    assert b.get("val-1")["kind"] == "llm-validator"     # persisted across instances


def _dispatch_validate(e, agents, verdict_payload):
    """One dispatcher round with a fake validator; waits for the worker thread."""
    import time
    from gfso.delegate import Dispatcher, _auto_validate
    llm = _AgentLLM(_fenced(verdict_payload))
    d = Dispatcher(e, agents,
                   validator_runner=lambda en, t, a: _auto_validate(en, t, a, _llm=llm))
    started = d.dispatch_once()
    for _ in range(200):
        if not llm._texts:      # the canned verdict was consumed
            break
        time.sleep(0.01)
    e.wait_idle()
    return started, llm


def test_delivered_report_wraps_accept_deliver_then_dispatcher_autovalidates(tmp_path):
    e = _eng()
    _node(e)
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    llm = _AgentLLM(_fenced({"status": "delivered", "summary": "nail at wall.md; flush verified",
                             "self_validation": "flush: met"}))
    out = run_executor(e, TaskId("n1"), "exec-1", agents, _llm=llm)
    e.wait_idle()
    assert out["status"] == "delivered"
    assert e.get_state(TaskId("n1")).name == "VALIDATING"   # executor round ends at delivery
    assert "hammer a nail" in llm.packets[0]["user"]        # packet embeds the contract
    assert "Write" in llm.packets[0]["tools"]               # executor gets work tools
    # the DISPATCHER picks the delivered node up and auto-validates + auto-signals (ONE path for
    # delegated and self-executed deliveries alike)
    started, vllm = _dispatch_validate(e, agents, {"verdict": "PASS", "per_criterion": [
        {"criterion": "flush", "verdict": "pass", "evidence": "ran check"}], "failed_criteria": []})
    assert "validate:n1" in started
    assert e.get_state(TaskId("n1")).name == "DONE"
    assert "Write" not in vllm.packets[0]["tools"]          # validator is read-only


def test_fail_verdict_drives_rework_loop_with_feedback(tmp_path):
    e = _eng()
    _node(e)
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    run_executor(e, TaskId("n1"), "exec-1", agents,
                 _llm=_AgentLLM(_fenced({"status": "delivered", "summary": "done-ish",
                                         "self_validation": "flush: met"})))
    e.wait_idle()
    _dispatch_validate(e, agents, {"verdict": "FAIL", "per_criterion": [
        {"criterion": "flush", "verdict": "fail", "evidence": "bent"}], "failed_criteria": ["flush"]})
    assert e.get_state(TaskId("n1")).name == "REWORK"       # auto-FAIL → the FSM's own rework loop
    # the NEXT executor round carries the failed criteria as feedback
    llm2 = _AgentLLM(_fenced({"status": "delivered", "summary": "fixed", "self_validation": "ok"}))
    run_executor(e, TaskId("n1"), "exec-1", agents, _llm=llm2)
    e.wait_idle()
    assert "REWORK" in llm2.packets[0]["user"] and "flush" in llm2.packets[0]["user"]
    _dispatch_validate(e, agents, {"verdict": "PASS", "per_criterion": [
        {"criterion": "flush", "verdict": "pass", "evidence": "ok"}], "failed_criteria": []})
    assert e.get_state(TaskId("n1")).name == "DONE"


def test_selfexecuted_delivery_also_autovalidated(tmp_path):
    """The guinea-pig regime: the agent executes ITSELF (no executor registration) — with a registered
    llm-validator the dispatcher still auto-validates its delivery and auto-signals the verdict."""
    e = _eng()
    _node(e, "s1", assignee="agent")
    agents = _agents(tmp_path, ("val-1", "llm-validator"))   # validator only
    T.signal(e, "s1", "ACCEPT", "agent")
    T.signal(e, "s1", "DELIVER", "agent", result="did it myself; see files")
    started, _ = _dispatch_validate(e, agents, {"verdict": "PASS", "per_criterion": [
        {"criterion": "flush", "verdict": "pass", "evidence": "checked"}], "failed_criteria": []})
    assert "validate:s1" in started
    assert e.get_state(TaskId("s1")).name == "DONE"          # verdict signed by val-1, not the agent


def test_challenge_and_unparsed_paths(tmp_path):
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"))
    _node(e, "c1")
    run_executor(e, TaskId("c1"), "exec-1", agents,
                 _llm=_AgentLLM(_fenced({"status": "challenge", "summary": "-",
                                         "reason": "criteria undecidable"})))
    e.wait_idle()
    assert e.get_state(TaskId("c1")).name == "CHALLENGED"   # issuer resolves
    _node(e, "u1")
    out = run_executor(e, TaskId("u1"), "exec-1", agents, _llm=_AgentLLM("no json here"))
    e.wait_idle()
    assert out["status"] == "unparsed"
    assert e.get_state(TaskId("u1")).name == "REVIEW"       # NO signal forged on a broken report


def test_dispatcher_autostarts_only_registered_executors(tmp_path):
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    _node(e, "a1", assignee="exec-1")                       # registered executor → starts
    _node(e, "h1", assignee="kirill")                       # human → passive
    _node(e, "v1", assignee="val-1")                        # kind-guard: validator ≠ executor
    ran = []

    def fake_runner(engine, task_id, executor_id, ag):
        ran.append((str(task_id), executor_id))

    d = Dispatcher(e, agents, runner=fake_runner)
    started = d.dispatch_once()
    for _ in range(100):                                    # the run happens on a worker thread
        if ran:
            break
        import time
        time.sleep(0.01)
    assert started == ["a1"] and ran == [("a1", "exec-1")]
    assert d.dispatch_once() == []                          # dedup: one spawn per node×iteration
    e.stop()


def test_dispatcher_event_driven_autostarts_on_transition(tmp_path):
    """The dispatcher is EVENT-DRIVEN, not tight-polling: with a long safety interval (poll=30s), starting
    it and then assigning a node to a registered executor still autostarts within a beat — woken by the
    ASSIGN→REVIEW transition, not by a poll tick."""
    import time
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"))
    ran = []
    d = Dispatcher(e, agents, poll=30, runner=lambda en, tid, ex, ag: ran.append(str(tid)))
    d.start()
    try:
        _node(e, "n1", assignee="exec-1")                 # transition wakes the loop — well under 30s
        for _ in range(200):
            if ran:
                break
            time.sleep(0.01)
        assert ran == ["n1"]                              # autostarted from the transition, not a poll tick
    finally:
        d.stop()
        e.stop()


def test_per_executor_validator_override(tmp_path):
    a = _agents(tmp_path, ("val-default", "llm-validator"), ("val-special", "llm-validator"))
    a.register("exec-x", "llm-executor", validator="val-special")
    a.register("exec-y", "llm-executor")
    assert a.validator_for("exec-x") == "val-special"    # per-executor instrument override
    assert a.validator_for("exec-y") == "val-default"    # falls back to the first registered validator
    assert a.validator_for("agent") == "val-default"     # self-executed nodes get the default too


def _child(e, tid, parent="par", assignee="exec-1", crit="c"):
    T.create_task(e, tid, {"description": tid, "criteria": [{"name": crit, "description": crit.upper()}]},
                  assignee=assignee, parent_id=parent)


def _drive_done(e, tid, assignee="exec-1"):
    """Take a delegated child to DONE. Issuer = parent.assignee = agent ≠ Del, so the issuer's PASS
    needs no gate verdict (the verifier≠executor gate only bites when source == the node's Del)."""
    T.signal(e, tid, "ACCEPT", assignee)
    T.signal(e, tid, "DELIVER", assignee, result=f"{tid} out")
    T.signal(e, tid, "PASS", "agent")


def test_accept_spawn_gated_on_dependency_producers(tmp_path):
    """A consumer whose Dep PRODUCER isn't DONE must NOT be autostarted — spawning before its input
    exists just hits a missing file and BLOCKs (observed live in the dual run). The gate opens the
    instant the producer reaches DONE, and only then does the consumer spawn."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}]})
    _child(e, "prod"); _child(e, "cons")
    T.add_dependency(e, "prod", "cons")                       # cons consumes prod's delivery
    d = Dispatcher(e, agents, runner=lambda *a: None)
    started = d.dispatch_once()
    assert "prod" in started and "cons" not in started       # producer free; consumer gated on it
    _drive_done(e, "prod")
    assert e.get_state(TaskId("prod")).name == "DONE"
    assert "cons" in d.dispatch_once()                        # dependency satisfied → consumer spawns
    e.stop()


def test_resolved_block_auto_clears_and_respawns_executor(tmp_path):
    """A BLOCKED node auto-resolves once its recorded producer is DONE: RESOLVE_BLOCK(confirm) fires and
    the node's spawn-dedup key is dropped so a FRESH executor run picks it up — both in ONE poll. Contrast:
    a block on an INVENTED name (no such node → the mutation layer records no Dep edge) has no producer to
    wait on and correctly STAYS BLOCKED for a human — the auto-resolver never touches producer-less blocks."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}]})
    _child(e, "prod"); _child(e, "blk"); _child(e, "ph")
    _drive_done(e, "prod")
    # blk works far enough to find it needs prod, then BLOCKs on it (records the provisional prod→blk Dep)
    T.signal(e, "blk", "ACCEPT", "exec-1")
    T.signal(e, "blk", "BLOCK", "exec-1", reason="need prod", blocker_task_id="prod")
    # ph blocks on a name that is not a real node → no edge recorded → producer-less
    T.signal(e, "ph", "ACCEPT", "exec-1")
    T.signal(e, "ph", "BLOCK", "exec-1", reason="need ghost", blocker_task_id="ghost")
    assert e.get_state(TaskId("blk")).name == "BLOCKED"
    assert e.get_state(TaskId("ph")).name == "BLOCKED"
    d = Dispatcher(e, agents, runner=lambda *a: None)
    started = d.dispatch_once()
    assert e.get_state(TaskId("blk")).name != "BLOCKED"      # producer DONE → confirm
    assert "blk" in started                                  # dropped seen-key ⟹ fresh executor run
    assert e.get_state(TaskId("ph")).name == "BLOCKED"       # producer-less block stays for a human
    assert "ph" not in started
    e.stop()


def test_autoverdict_accepted_on_child_nodes_and_human_issuer_skipped(tmp_path):
    """(a) A registered validator's PASS/FAIL is the issuer's role-V instrument — accepted by the FSM
    on CHILD nodes too (before: only roots worked — the issuer check rejected it, found by the
    author's question). (b) A node whose ISSUER is a human keeps the human's verdict: the dispatcher
    never auto-validates it."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    # child under an agent-issued parent → auto-validated, validator verdict ACCEPTED by the FSM
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}]})
    T.create_task(e, "kid", {"description": "child", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="exec-1", parent_id="par")
    T.signal(e, "kid", "ACCEPT", "exec-1")
    T.signal(e, "kid", "DELIVER", "exec-1", result="done; see files")
    started, _ = _dispatch_validate(e, agents, {"verdict": "PASS", "per_criterion": [
        {"criterion": "k", "verdict": "pass", "evidence": "ran"}], "failed_criteria": []})
    assert "validate:kid" in started
    assert e.get_state(TaskId("kid")).name == "DONE"          # val-1's PASS survived the issuer check
    # human-issued node → the dispatcher stays out
    T.create_task(e, "hpar", {"description": "human parent",
                              "criteria": [{"name": "h", "description": "H"}]}, assignee="kirill")
    T.create_task(e, "hkid", {"description": "human child",
                              "criteria": [{"name": "c", "description": "C"}]}, assignee="kirill",
                  parent_id="hpar")
    T.signal(e, "hkid", "ACCEPT", "kirill")
    T.signal(e, "hkid", "DELIVER", "kirill", result="done by hand")
    started, _ = _dispatch_validate(e, agents, {"verdict": "PASS", "per_criterion": [], "failed_criteria": []})
    assert not any("hkid" in s for s in started)              # human issuer keeps the verdict
    assert e.get_state(TaskId("hkid")).name == "VALIDATING"
    e.stop()
