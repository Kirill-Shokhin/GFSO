"""Delegation machinery: registry roundtrip + kind semantics; the dispatcher's autostart-by-Del
(one spawn per node×iteration, unregistered = passive, kind-guard); the executor report → wrapped
FSM signals (consent = the executor's own report); auto-validation with auto-verdict (FAIL →
FSM REWORKING loop); unparsed reports never signal. All with fake agent-runners — no network."""
import json
import threading
import time

import pytest

from gfso.adapters.llm.stub import StubLLM
import gfso.tools_llm as TL
from gfso.core.types import (TaskId, AgentId, Spec, Criteria, CriterionMapping, Verdict,
                             DepEdge, Signal)
from gfso import tools as T
from gfso.config import MODEL_VALIDATOR_RETRY
import gfso.delegate as D
from gfso.delegate import (AgentRegistry, Dispatcher, run_executor, EXECUTOR_SCHEMA,
                           _auto_validate, _checker_validate)
from tests.support import make_engine
from gfso.decompose.build import build_graph_live


def _eng():
    e = make_engine(llm=StubLLM(), validate_signals=True)
    e.start()
    return e


def _agents(tmp_path, *entries):
    """Registers with a `workdir`, because the registry now refuses an agent role without one.

    An executor or validator with no working directory would be spawned where the SERVER stands —
    the state home — and the two ways that failed were both silent: the executor's spawn raised into
    a handler that only logged and the node was never retried, and the validator's error was
    discarded so the node sat in VALIDATING forever."""
    a = AgentRegistry(path=str(tmp_path / "agents.json"))
    for aid, kind in entries:
        a.register(aid, kind, workdir=str(tmp_path))
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
    llm = _AgentLLM(_fenced(verdict_payload))
    d = Dispatcher(e, agents,
                   validator_runner=lambda en, t, a, model_override=None, sign=True:
                   _auto_validate(en, t, a, _llm=llm, model_override=model_override, sign=sign))
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
        {"criterion": "flush", "verdict": "pass", "evidence": "ran check", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}], "failed_criteria": []})
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
        {"criterion": "flush", "verdict": "fail", "evidence": "bent", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}], "failed_criteria": ["flush"]})
    assert e.get_state(TaskId("n1")).name == "REWORKING"       # auto-FAIL → the FSM's own rework loop
    # the NEXT executor round carries the failed criteria as feedback
    llm2 = _AgentLLM(_fenced({"status": "delivered", "summary": "fixed", "self_validation": "ok"}))
    run_executor(e, TaskId("n1"), "exec-1", agents, _llm=llm2)
    e.wait_idle()
    assert "REWORKING" in llm2.packets[0]["user"] and "flush" in llm2.packets[0]["user"]
    _dispatch_validate(e, agents, {"verdict": "PASS", "per_criterion": [
        {"criterion": "flush", "verdict": "pass", "evidence": "ok", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}], "failed_criteria": []})
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
        {"criterion": "flush", "verdict": "pass", "evidence": "checked", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}], "failed_criteria": []})
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
    assert e.get_state(TaskId("u1")).name == "OFFERED"       # NO signal forged on a broken report


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
        time.sleep(0.01)
    assert started == ["a1"] and ran == [("a1", "exec-1")]
    assert d.dispatch_once() == []                          # dedup: one spawn per node×iteration
    e.stop()


def test_dispatcher_event_driven_autostarts_on_transition(tmp_path):
    """The dispatcher is EVENT-DRIVEN, not tight-polling: with a long safety interval (poll=30s), starting
    it and then assigning a node to a registered executor still autostarts within a beat — woken by the
    ASSIGN→OFFERED transition, not by a poll tick."""
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
    a.register("exec-x", "llm-executor", workdir=str(tmp_path), validator="val-special")
    a.register("exec-y", "llm-executor", workdir=str(tmp_path))
    assert a.validator_for("exec-x") == "val-special"    # per-executor instrument override
    assert a.validator_for("exec-y") == "val-default"    # falls back to the first registered validator
    assert a.validator_for("agent") == "val-default"     # self-executed nodes get the default too


def _child(e, tid, parent="par", assignee="exec-1", crit="c", parent_crit="g"):
    T.create_task(e, tid, {"description": tid, "criteria": [{"name": crit, "description": crit.upper()}]},
                  assignee=assignee, parent_id=parent)
    T.map_criterion(e, parent, tid, parent_crit)   # §13.4: L0-complete plan before executing children


def _drive_done(e, tid, assignee="exec-1"):
    """Take a delegated child to DONE — through the seam, not around it.

    This helper used to sign the issuer's PASS bare, on the belief that "issuer ≠ Del" was itself
    the separation §14.5 asks for. It is not: a seam needs an independent verdict for THIS delivery
    whoever signs it (the false PASS the agent door found on 2026-08-22). The verdict here is the
    issuer's own recorded observation, which is what a person judging by hand does."""
    t = e.get_task(TaskId(tid))
    T.signal(e, tid, "ACCEPT", assignee)
    T.signal(e, tid, "DELIVER", assignee, result=f"{tid} out")
    T.record_verdict(e, tid, "PASS", reviewer="agent",
                     observed={c.name: f"ran {tid} and read its output"
                               for c in t.spec.criteria if not c.depends_on})
    T.signal(e, tid, "PASS", "agent")


def test_accept_spawn_gated_on_dependency_producers(tmp_path):
    """A consumer whose Dep PRODUCER isn't DONE must NOT be autostarted — spawning before its input
    exists just hits a missing file and BLOCKs (observed live in the dual run). The gate opens the
    instant the producer reaches DONE, and only then does the consumer spawn."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                "predictability": "EXTRAORDINARY"}]})
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
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                "predictability": "EXTRAORDINARY"}]})
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


def test_multi_blocker_report_records_all_edges_and_gates_on_every_producer(tmp_path):
    """The executor's blocked report carries blocker_task_ids — EVERY named node records an edge
    (observed live: a 3-blocker deadlock reported through the singular schema recorded 0 edges →
    q_Dep starved, auto-resolve blind). The node then auto-resolves only when ALL producers are DONE."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                "predictability": "EXTRAORDINARY"}]})
    _child(e, "p1"); _child(e, "p2"); _child(e, "cli")
    llm = _AgentLLM(_fenced({"status": "blocked", "summary": "stopped at imports",
                             "reason": "need p1 and p2 outputs",
                             "blocker_task_ids": ["p1", "p2"]}))
    run_executor(e, TaskId("cli"), "exec-1", agents, _llm=llm)
    e.wait_idle()
    assert e.get_state(TaskId("cli")).name == "BLOCKED"
    disc = sorted(str(x.from_id) for x in e.get_dependencies()
                  if x.discovered and str(x.to_id) == "cli")
    assert disc == ["p1", "p2"]                              # BOTH edges recorded
    d = Dispatcher(e, agents, runner=lambda *a: None)
    _drive_done(e, "p1")
    d.dispatch_once()
    assert e.get_state(TaskId("cli")).name == "BLOCKED"      # one producer still pending → no resolve
    _drive_done(e, "p2")
    started = d.dispatch_once()
    assert e.get_state(TaskId("cli")).name != "BLOCKED"      # all producers DONE → confirm-all
    assert "cli" in started                                  # dropped seen-key ⟹ fresh executor run
    assert not [x for x in e.get_dependencies()
                if x.discovered and str(x.to_id) == "cli" and x.provisional]  # set confirmed
    e.stop()


def test_mixed_phantom_auto_resolve_drops_only_the_bogus_edge(tmp_path):
    """One phantom source among real blockers must not retract the REAL edges (the old all-or-nothing
    external=True did exactly that): the auto-resolver adjudicates the corrected set = the real
    sources, so only the bogus edge goes."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                "predictability": "EXTRAORDINARY"}]})
    _child(e, "prod"); _child(e, "blk")
    _drive_done(e, "prod")
    T.signal(e, "blk", "ACCEPT", "exec-1")
    T.signal(e, "blk", "BLOCK", "exec-1", reason="need prod + a name that is not a node",
             blocker_task_ids=["prod"])
    # the observed-live phantom shape: a provisional edge whose source node does not exist
    e.graph._storage.add_dep_edge(DepEdge(TaskId("ghost"), TaskId("blk"), discovered=True,
                                          glue="", provisional=True))
    d = Dispatcher(e, agents, runner=lambda *a: None)
    d.dispatch_once()
    assert e.get_state(TaskId("blk")).name != "BLOCKED"
    disc = [(str(x.from_id), x.provisional) for x in e.get_dependencies()
            if x.discovered and str(x.to_id) == "blk"]
    assert disc == [("prod", False)]         # real edge confirmed; the phantom edge retracted
    e.stop()


def test_dep_gate_holds_on_not_yet_created_producer(tmp_path):
    """The mid-build race (observed live): during a build the consumer's ASSIGN can land milliseconds
    BEFORE its producer's — an unknown producer must read as NOT ready, not as vacuously satisfied
    (the old `prod is not None and …` skipped the edge → the consumer spawned into a doomed run)."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"))
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                "predictability": "EXTRAORDINARY"}]})
    T.create_task(e, "cons", {"description": "consumer", "criteria": [
        {"name": "c", "description": "C"},
        {"name": "dep__prod", "description": "reads prod's output", "depends_on": "prod"}]},
        assignee="exec-1", parent_id="par")
    T.map_criterion(e, "par", "cons", "g")   # §13.4: L0-complete before exec
    d = Dispatcher(e, agents, runner=lambda *a: None)
    assert "cons" not in d.dispatch_once()            # producer node does not exist yet → gated
    _child(e, "prod")
    assert "cons" not in d.dispatch_once()            # exists but not DONE → still gated
    _drive_done(e, "prod")
    assert "cons" in d.dispatch_once()                # producer PASSed → the gate opens
    e.stop()


def test_dispatch_quiesced_while_build_bursts(tmp_path):
    """A wholesale build/rebuild is a non-atomic signal burst; dispatching a half-built graph races it
    (observed live: the root spawned as an EXECUTING 'leaf' before its children existed). The build
    raises engine._dispatch_quiesce → dispatch_once is silent; on exit it pokes _dispatch_wake."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"))
    _node(e, "q1")
    d = Dispatcher(e, agents, runner=lambda *a: None)
    e._dispatch_quiesce = 1
    assert d.dispatch_once() == []                    # quiesced → nothing dispatched
    e._dispatch_quiesce = 0
    assert "q1" in d.dispatch_once()                  # resumed on the settled graph
    woken = []
    e._dispatch_wake = lambda: woken.append(True)
    spec = {"name": "goal", "root_criteria": [{"name": "r", "description": "R"}],
            "subtasks": [{"id": "a", "description": "A",
                          "criteria": [{"name": "ca", "description": "CA"}]}],
            "mappings": [{"criterion": "r", "child_id": "a"}], "deps": [], "accepted_risks": [
                {"item": "none material", "predictability": "STATISTICAL",
                 "justification": "-", "invalidation": "-"}]}
    build_graph_live(spec, "goal", e, root_id="broot", assignee="exec-1")
    assert getattr(e, "_dispatch_quiesce", 0) == 0 and woken   # counter cleared + the loop poked
    e.stop()


def test_parent_validation_waits_for_children_and_rejected_verdict_frees_key(tmp_path):
    """(a) A prematurely delivered parent must not burn validator runs: its PASS is structurally
    rejected until every child passes (Theorem-1 gate; observed live — two doomed PASSes). The
    validate spawn WAITS for the children. (b) If a verdict IS rejected (gate raced), that is NOT
    'no verdict': the dedup key is freed (no retry burned) and the node revalidates once the
    children settle — the same dispatcher, a fresh run."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    T.create_task(e, "par", {"description": "parent",
                             "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                "predictability": "EXTRAORDINARY"}]}, assignee="exec-1")
    _child(e, "kid", assignee="exec-2")               # unregistered = human-ish, dispatcher passive
    T.signal(e, "par", "ACCEPT", "exec-1")
    T.signal(e, "par", "DELIVER", "exec-1", result="premature aggregate")
    ok = {"verdict": "PASS",
          "per_criterion": [{"criterion": "g", "verdict": "pass", "evidence": "aggregate checked", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}],
          "failed_criteria": []}
    llm = _AgentLLM(_fenced(ok), _fenced(ok))
    d = Dispatcher(e, agents, runner=lambda *a: None,
                   validator_runner=lambda en, t, a: _auto_validate(en, t, a, _llm=llm))
    # (a) the gate: children not settled → no validator spawn at all
    assert not any("par" in s for s in d.dispatch_once())
    assert len(llm._texts) == 2
    # (b) the rejected path itself. The frontier no longer OFFERS a validate step on a parent whose
    # children are open (a verdict there is refused, and putting it at the head of the frontier is
    # what left a live run waiting nineteen minutes on a verdict nobody could give), so the race
    # this covers — a queued run whose graph moved under it — is exercised where it lives: the
    # guarded validation path, with the round already claimed.
    vkey = d._round_key(e.get_task(TaskId("par")), "v:")
    d._seen.add(vkey)
    threading.Thread(target=d._validate_guarded, args=(TaskId("par"), 0), daemon=True).start()
    for _ in range(300):                              # verdict consumed + guarded postlude done
        if len(llm._texts) == 1 and vkey not in d._seen:
            break
        time.sleep(0.01)
    e.wait_idle()
    assert e.get_state(TaskId("par")).name == "VALIDATING"    # the PASS was FSM-rejected
    assert vkey not in d._seen                                # key freed for a later revalidation
    assert not d._retried                                     # NOT burned as a no-verdict retry
    T.signal(e, "kid", "ACCEPT", "exec-2")
    T.signal(e, "kid", "DELIVER", "exec-2", result="kid out")
    # a seam needs the verdict on the record whoever signs it (§14.5); the issuer records what it
    # observed and then signs — "issuer ≠ Del" is a rule about the signature, not the evidence
    T.record_verdict(e, "kid", "PASS", reviewer="exec-1", observed={"c": "ran the child's output"})
    T.signal(e, "kid", "PASS", "exec-1")
    assert "validate:par" in d.dispatch_once()                # children settled → fresh validation
    for _ in range(300):
        if not llm._texts:
            break
        time.sleep(0.01)
    e.wait_idle()
    assert e.get_state(TaskId("par")).name == "DONE"          # this PASS survived the gate
    e.stop()


def test_auto_validate_reuses_fresh_recorded_verdict(tmp_path):
    """A fresh recorded verdict for the CURRENT generation (e.g. a manual validate_result already
    ran) is SIGNED directly by the dispatcher — no duplicate validator spawn (observed live:
    one duplicate run per rework cycle, minutes + tokens each)."""
    e = _eng()
    _node(e)
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    run_executor(e, TaskId("n1"), "exec-1", agents,
                 _llm=_AgentLLM(_fenced({"status": "delivered", "summary": "done",
                                         "self_validation": "flush: met"})))
    e.wait_idle()
    assert e.get_state(TaskId("n1")).name == "VALIDATING"
    e.record_exec_verdict(TaskId("n1"), "PASS", [], "validate_result")   # fresh manual verdict
    e._graph.authorized_validators = {"val-1"}      # the dispatcher syncs this each pass
    unused = _AgentLLM("never popped")
    assert _auto_validate(e, TaskId("n1"), agents, _llm=unused) == "pass"
    assert unused.packets == []                       # verdict reused, no validator spawned
    e.wait_idle()
    assert e.get_state(TaskId("n1")).name == "DONE"   # signed from the record
    e.stop()


def test_inflight_validator_lock_suppresses_concurrent_duplicates(tmp_path):
    """In-flight validator lock (registered debt — E3 it-2 live log: three parallel validators on
    one VALIDATING node): a second spawn on the same node generation (node, iteration, reopens)
    returns inflight=True WITHOUT running an agent; the dispatcher path reads it as 'rejected'
    (dedup key freed, the one no-verdict retry never burned); the lock releases after the run."""
    e = _eng()
    _node(e)
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    run_executor(e, TaskId("n1"), "exec-1", agents,
                 _llm=_AgentLLM(_fenced({"status": "delivered", "summary": "done",
                                         "self_validation": "flush: met"})))
    e.wait_idle()
    assert e.get_state(TaskId("n1")).name == "VALIDATING"

    release = threading.Event()

    class _Blocking(_AgentLLM):
        def run_agent(self, system, user, allowed_tools, cwd=None):
            release.wait(5)
            return super().run_agent(system, user, allowed_tools, cwd)

    slow = _Blocking(_fenced({"verdict": "PASS", "per_criterion": [
        {"criterion": "flush", "verdict": "pass", "evidence": "ran", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}], "failed_criteria": []}))
    first: dict = {}
    t = threading.Thread(target=lambda: first.update(TL.validate_result(e, "n1", _llm=slow)))
    t.start()
    for _ in range(500):                                      # first run claims the slot
        if e._val_inflight:
            break
        time.sleep(0.01)
    assert e._val_inflight

    dup = TL.validate_result(e, "n1", _llm=_AgentLLM("unused"))
    assert dup.get("inflight") is True                        # suppressed, no verdict field

    fast = _AgentLLM("unused")
    assert _auto_validate(e, TaskId("n1"), agents, _llm=fast) == "rejected"
    assert fast.packets == []                                 # no duplicate agent spawned

    release.set()
    t.join(5)
    assert first["verdict"] == "PASS"                         # the holder finished normally
    assert not e._val_inflight                                # lock released after the run
    e.stop()


def test_stale_queued_run_releases_slot_without_spawning(tmp_path):
    """TOCTOU: a queued run can win its semaphore slot minutes after the dispatch decision — if the
    node has moved on (delivered / revised / new iteration), the run must abort WITHOUT an LLM spawn
    (observed live: a second-generation queued run fired on a node already in VALIDATING)."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    _node(e, "t1")
    ran = []
    d = Dispatcher(e, agents, runner=lambda en, tid, ex, ag: ran.append(str(tid)))
    # fresh: OFFERED at iteration 0 → runs
    d._run_guarded(TaskId("t1"), "exec-1", 0)
    assert ran == ["t1"]
    # stale by state: the node delivered meanwhile → the queued run drops
    T.signal(e, "t1", "ACCEPT", "exec-1")
    T.signal(e, "t1", "DELIVER", "exec-1", result="out")
    d._run_guarded(TaskId("t1"), "exec-1", 0)
    assert ran == ["t1"]                                  # no second run
    # stale validate: iteration mismatch drops AND frees the key for a fresh dispatch.
    # The key is built the way the dispatcher builds it — id plus the node's GENERATION
    # (iteration, reopens, revisions); a literal in the old id#iteration shape would assert the
    # freeing of a key nothing ever claimed.
    vkey = d._round_key(e.get_task(TaskId("t1")), "v:")
    d._seen.add(vkey)
    validated = []
    d._validate = lambda en, t, a: validated.append(str(t)) or "pass"
    d._validate_guarded(TaskId("t1"), 5)                  # node is at iteration 0, not 5
    assert not validated and vkey not in d._seen
    d._validate_guarded(TaskId("t1"), 0)                  # fresh: VALIDATING at iteration 0
    assert validated == ["t1"]
    e.stop()


def test_a_reassigned_node_is_not_run_as_its_old_executor(tmp_path):
    """The queued run acted as the executor it was queued for, after the node had been reassigned.

    Measured on a live E3 run 2026-08-22: `root.matcher` moved from exec-1 to exec-2 between the
    dispatch decision and the slot, and the run made its signals as exec-1 — two ACCEPTs and a
    DELIVER refused with "exec-1 is not executor for root.matcher (executor=exec-2)", the agent call
    paid for, and the graph stalled for ten minutes while the frontier kept offering the same step.
    Del is part of what goes stale, and freeing the slot has to free the ROUND with it: a
    reassignment moves no generation counter, so the claim would otherwise be one nobody spends."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("exec-2", "llm-executor"))
    _node(e, "t1")
    ran = []
    d = Dispatcher(e, agents, runner=lambda en, tid, ex, ag: ran.append(f"{tid}:{ex}"))
    d._claim(d._round_key(e.get_task(TaskId("t1"))))   # the round the old dispatch decision claimed
    e.reassign(TaskId("t1"), AgentId("exec-2"))
    e.wait_idle()
    assert str(e.get_task(TaskId("t1")).assignee) == "exec-2"
    d._run_guarded(TaskId("t1"), "exec-1", 0)         # …the slot the OLD dispatch won
    assert ran == [], "a run as the old executor makes signals the FSM refuses"
    assert d._round_key(e.get_task(TaskId("t1"))) not in d._seen, "the round is freed with the slot"
    assert "t1" in d.dispatch_once()                  # …and the next pass sends it to exec-2
    e.stop()


def test_revision_resets_spawn_key(tmp_path):
    """A REVISED node (re-ASSIGN, same id → OFFERED) is fresh work: its consumed spawn key must not
    block the re-run (observed live: a refined root kept its key and was never re-executed)."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"))
    _node(e, "r1")
    d = Dispatcher(e, agents, runner=lambda *a: None)
    assert "r1" in d.dispatch_once()
    assert d.dispatch_once() == []                    # key consumed — dedup holds
    t = e.get_task(TaskId("r1"))
    e.revise(TaskId("r1"), Spec("hammer TWO nails", t.spec.criteria, name=t.spec.name),
             AgentId("exec-1"))                       # issuer of a root = its own assignee
    d._on_bus(TaskId("r1"), None, None, Signal.ASSIGN)   # what the transition bus delivers
    assert "r1" in d.dispatch_once()                  # stale key dropped → the revised node re-runs
    e.stop()


def test_autoverdict_accepted_on_child_nodes_and_human_issuer_skipped(tmp_path):
    """(a) A registered validator's PASS/FAIL is the issuer's role-V instrument — accepted by the FSM
    on CHILD nodes too (before: only roots worked — the issuer check rejected it, found by the
    author's question). (b) A node whose ISSUER is a human keeps the human's verdict: the dispatcher
    never auto-validates it."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    # child under an agent-issued parent → auto-validated, validator verdict ACCEPTED by the FSM
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                "predictability": "EXTRAORDINARY"}]})
    T.create_task(e, "kid", {"description": "child", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="exec-1", parent_id="par")
    T.map_criterion(e, "par", "kid", "g")
    T.signal(e, "kid", "ACCEPT", "exec-1")
    T.signal(e, "kid", "DELIVER", "exec-1", result="done; see files")
    started, _ = _dispatch_validate(e, agents, {"verdict": "PASS", "per_criterion": [
        {"criterion": "k", "verdict": "pass", "evidence": "ran", "behaviours": ["the criterion holds"], "probe": [{"command": "pytest -q", "expect": "passed"}]}], "failed_criteria": []})
    assert "validate:kid" in started
    assert e.get_state(TaskId("kid")).name == "DONE"          # val-1's PASS survived the issuer check
    # human-issued node → the dispatcher stays out
    T.create_task(e, "hpar", {"description": "human parent",
                              "criteria": [{"name": "h", "description": "H"}],
                              "accepted_risks": [{"item": "an unmodelled environment fault",
                                                 "predictability": "EXTRAORDINARY"}]}, assignee="kirill")
    T.create_task(e, "hkid", {"description": "human child",
                              "criteria": [{"name": "c", "description": "C"}]}, assignee="kirill",
                  parent_id="hpar")
    T.map_criterion(e, "hpar", "hkid", "h")
    T.signal(e, "hkid", "ACCEPT", "kirill")
    T.signal(e, "hkid", "DELIVER", "kirill", result="done by hand")
    started, _ = _dispatch_validate(e, agents, {"verdict": "PASS", "per_criterion": [], "failed_criteria": []})
    assert not any("hkid" in s for s in started)              # human issuer keeps the verdict
    assert e.get_state(TaskId("hkid")).name == "VALIDATING"
    e.stop()


def test_unittest_checker_is_a_deterministic_hidden_test_validator(tmp_path):
    """The `unittest-checker` validator kind (the E0 design the user asked for): a deterministic
    hidden-test oracle. It runs the project's hidden unittest suite against the delivered solution.py,
    maps each test method to the criterion of the same name, and returns a verdict with per-criterion
    evidence — no LLM, no false-PASS, and the executor never sees the tests. Golden → PASS, naive →
    FAIL with the failing criteria named."""
    test_code = (
        "import unittest\n"
        "class TestCases(unittest.TestCase):\n"
        "    def test_returns_two(self):\n        self.assertEqual(f(), 2)\n"
        "    def test_positive(self):\n        self.assertGreater(f(), 0)\n")
    canon = tmp_path / "canon.py"; canon.write_text(test_code, encoding="utf-8")
    ws = tmp_path / "ws"; ws.mkdir()
    mp = tmp_path / "oracle.json"
    mp.write_text(json.dumps({"proj": {"task_id": "t", "canonical": str(canon),
                  "workdir": str(ws), "criteria": ["test_returns_two", "test_positive"]}}), encoding="utf-8")

    class _E:
        _project_name = "proj"
    cfg = {"oracle_map": str(mp)}

    (ws / "solution.py").write_text("def f():\n    return 2\n", encoding="utf-8")
    out = _checker_validate(_E(), TaskId("root"), cfg)
    assert out["verdict"] == "PASS" and out["failed_criteria"] == []
    assert {p["criterion"] for p in out["per_criterion"]} == {"test_returns_two", "test_positive"}

    (ws / "solution.py").write_text("def f():\n    return -5\n", encoding="utf-8")   # fails both
    out = _checker_validate(_E(), TaskId("root"), cfg)
    assert out["verdict"] == "FAIL" and "test_positive" in out["failed_criteria"]

    (ws / "solution.py").unlink()                                                    # nothing delivered
    out = _checker_validate(_E(), TaskId("root"), cfg)
    assert out["verdict"] == "FAIL" and set(out["failed_criteria"]) == {"test_returns_two", "test_positive"}


def test_unittest_checker_kind_registers_and_is_the_default_validator(tmp_path):
    """…and it must be registered WITH its oracle map.

    Registered without one it could never produce a verdict — the map is where its hidden tests
    are — while still being the first registered validator, which silently disabled any
    llm-validator registered after it, for the whole server."""
    a = AgentRegistry(path=str(tmp_path / "agents.json"))
    with pytest.raises(ValueError, match="oracle_map"):
        a.register("val-1", "unittest-checker")
    a.register("val-1", "unittest-checker", oracle_map=str(tmp_path / "map.json"))
    assert a.default_validator() == "val-1"
    assert a.get("val-1")["kind"] == "unittest-checker"
    assert a.get("val-1")["oracle_map"].endswith("map.json")


def test_executor_turn_cap_is_declared_with_the_role(tmp_path):
    """`max_turns` is a term of the AGENT's contract: how many steps one run may take.

    It had no place in the roster, so a delegated executor ran under whatever the transport
    defaulted to while an externally-driven one ran under an explicit cap — two runs of "the same
    agent" differing in a way nothing recorded, which is exactly the confound that makes a
    comparison between them measure the harness instead of the discipline."""
    seen = {}

    class _LLM:
        calls: list = []

        def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None, max_turns=None):
            seen["max_turns"] = max_turns
            return '{"status": "delivered", "summary": "ok", "self_validation": "ran"}'

    reg = AgentRegistry(path=str(tmp_path / "agents.json"))
    reg.register("exec-1", "llm-executor", workdir=str(tmp_path), max_turns=50)
    assert reg.get("exec-1")["max_turns"] == 50

    e = _eng()
    e.assign_task(TaskId("n1"), Spec("n", (Criteria("c", "c"),)), AgentId("exec-1"))
    e.wait_idle()
    run_executor(e, TaskId("n1"), "exec-1", reg, _llm=_LLM())
    assert seen["max_turns"] == 50
    e.stop()


def test_a_roster_edited_on_disk_takes_effect(tmp_path):
    """The registry's own docstring promises a roster "editable by hand", and it is a per-process
    singleton — so it read the file once, at server start, and every later edit was invisible.

    Measured, live: a probe rewrote the roster to point two executors at its own workspace, the
    server kept the entry from the run before it, and both agents worked in a directory belonging to
    a different experiment. The graph looked healthy and the verdicts judged the wrong tree, which is
    the worst available failure — a wrong answer rather than a missing one."""
    path = tmp_path / "agents.json"
    path.write_text(json.dumps({"exec-1": {"kind": "llm-executor", "workdir": str(tmp_path / "A")}}),
                    encoding="utf-8")
    reg = AgentRegistry(path=str(path))
    assert reg.get("exec-1")["workdir"].endswith("A")

    time.sleep(0.01)                      # a distinct mtime, not a same-second write
    path.write_text(json.dumps({
        "exec-1": {"kind": "llm-executor", "workdir": str(tmp_path / "B")},
        "val-1": {"kind": "llm-validator", "workdir": str(tmp_path / "V")}}), encoding="utf-8")
    assert reg.get("exec-1")["workdir"].endswith("B"), "the edit never reached the running registry"
    assert reg.default_validator() == "val-1", "a validator added on disk stayed invisible"
    assert set(reg.list()) == {"exec-1", "val-1"}


def test_one_node_is_never_dispatched_twice_for_the_same_round(tmp_path):
    """Two paid runs on one contract — the defect a bare check-then-add allows, measured live.

    `dispatch_once` runs from two places by design (the poll loop and the transition wake), so the
    dedup claim has to be atomic; and the key has to carry the node's GENERATION, or the mechanism
    that made a REVISED node fresh work (marking it and dropping its keys) can drop a key moments
    after its first claim — which is exactly how one node came to be executed twice on its very first
    assign. Both halves are asserted: concurrent rounds claim once, and a revision is a NEW round
    without anything being un-remembered."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"))
    ran: list = []
    d = Dispatcher(e, agents, poll=30, runner=lambda en, tid, ex, ag: ran.append(str(tid)))
    _node(e, "n1", assignee="exec-1")

    # The window is TINY on a fast path, and a control that cannot open it proves nothing about the
    # lock (measured: with the lock removed, four barriered rounds still claimed once). So the
    # membership test is made slow — exactly the shape of the race — and the claim must still be
    # granted once.
    class _SlowSet(set):
        def add(self, item):                               # the WRITE lags the read
            time.sleep(0.05)                               # …so a second caller checks before it lands
            return super().add(item)

    d._seen = _SlowSet(d._seen)
    barrier = threading.Barrier(4)

    def pass_once():
        barrier.wait()
        d.dispatch_once()

    threads = [threading.Thread(target=pass_once) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    for _ in range(200):
        if ran:
            break
        time.sleep(0.01)
    assert ran == ["n1"], f"one round, {len(ran)} runs: {ran}"

    # …and a REVISION is a fresh round: the key changes because the generation is in it.
    e.revise(TaskId("n1"), Spec("n", (Criteria("c", "c2"),)), AgentId("exec-1"))
    e.wait_idle()
    d.dispatch_once()
    for _ in range(200):
        if len(ran) >= 2:
            break
        time.sleep(0.01)
    assert ran == ["n1", "n1"], "a revised node must be re-executed"
    e.stop()


def test_an_unreadable_executor_report_is_retried_once_then_parked_out_loud(tmp_path):
    """An unparsed report forges no signal — correctly — so the node stays where it was, and the
    dispatcher's spent key meant it was never picked up again: one leaf of a delegated run sat in
    OFFERED for the rest of the run on a single unreadable report, while the graph looked merely
    busy. One retry, then a parked node WITH a reason."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"))
    tries = []

    def runner(en, tid, ex, ag):
        tries.append(str(tid))
        return {"task_id": str(tid), "status": "unparsed", "report_text": "…"}

    d = Dispatcher(e, agents, poll=30, runner=runner)
    _node(e, "n1", assignee="exec-1")
    d.dispatch_once()
    for _ in range(200):
        if tries:
            break
        time.sleep(0.01)
    assert tries == ["n1"]

    d.dispatch_once()                                  # the retry the first unparsed report earns
    for _ in range(200):
        if len(tries) >= 2:
            break
        time.sleep(0.01)
    assert tries == ["n1", "n1"]

    d.dispatch_once()                                  # …and no third: parked, with a line saying so
    time.sleep(0.2)
    assert tries == ["n1", "n1"]
    said = " ".join(r["message"] for r in e.pipeline_log())
    assert "PARKED" in said and "issuer" in said
    e.stop()


def test_no_executor_is_spawned_under_a_plan_the_gate_refuses(tmp_path, monkeypatch):
    """The execution gate lives on ACCEPT, and the dispatcher spawns the executor BEFORE that signal
    exists — the report is what produces it. So a leaf under a plan the gate refuses had its executor
    spawned, worked and reported, and only then was the ACCEPT rejected: a paid call thrown away,
    repeatedly, while the plan sat unfixed. The gate's question is asked first now, exactly as the
    dependency one is."""
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"))
    ran: list = []
    d = Dispatcher(e, agents, poll=30, runner=lambda en, tid, ex, ag: ran.append(str(tid)))

    # a parent whose plan carries an open Level-0 hole: a criterion no child covers
    e.assign_task(TaskId("p"), Spec("p", (Criteria("c1", "c1"), Criteria("uncovered", "nobody"))),
                  AgentId("boss"))
    e.wait_idle()
    e.decompose_task(TaskId("p"),
                     [(TaskId("p.kid"), Spec("kid", (Criteria("k", "k"),)), AgentId("exec-1"))],
                     [CriterionMapping("c1", TaskId("p.kid"))])
    e.wait_idle()

    d.dispatch_once()
    time.sleep(0.3)
    assert ran == [], "an executor was paid for under a plan the gate refuses"
    e.stop()


def test_a_node_the_plan_gate_holds_back_is_said_out_loud(tmp_path, monkeypatch):
    """A gate that only refuses is indistinguishable from a dead dispatcher.

    Execution is gated on the parent's plan passing its checks (§13.4), and the dispatcher asks that
    question before paying for a run — correctly, since the ACCEPT would be refused and the
    executor's work with it. But it did so in silence: measured 2026-08-20 on the shipped
    `autonomous_org` demo, whose loop drives only this dispatcher and never the frontier's own
    review step, two children sat in OFFERED for half an hour over an empty workspace with nothing
    anywhere saying why. Said once per node, and it names the step that opens the gate."""
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                 "predictability": "EXTRAORDINARY"}]})
    _child(e, "kid")
    said = []
    e.on_info(lambda src, msg: said.append(msg))
    d = Dispatcher(e, agents, runner=lambda *a: None)
    assert d.dispatch_once() == []                       # the plan has no Level-2 verdict yet
    gate = [m for m in said if m.startswith("kid: not started")]
    assert gate, f"the dispatcher said nothing about holding 'kid' back: {said}"
    assert "review_decomposition('par')" in gate[0]      # …and names the step that opens it
    d.dispatch_once()
    assert len([m for m in said if m.startswith("kid: not started")]) == 1   # once, not per poll
    e.stop()


def test_a_registration_does_not_erase_another_sessions_roles(tmp_path):
    """The roster is one file shared by every session, and writing it was read-modify-write.

    A process that had loaded the file before someone else's registration wrote that registration
    away. Measured 2026-08-21: a measurement run staffed three executors, two test sessions
    registered their own roles minutes later, and when the run's node came back for rework NONE of
    the three existed — the dispatcher correctly refused to spawn for roles that were not there, the
    node stood still for twenty-five minutes, and the run ended `graph_stalled`. Nobody withdrew
    those roles; they were overwritten.

    `unregister` is the other half: taking a role out existed nowhere, so every process that wanted
    one gone edited the shared file by hand — which is the same defect with a different author."""
    roster = tmp_path / "roster.json"
    a = AgentRegistry(path=str(roster))
    b = AgentRegistry(path=str(roster))                  # a second session, its own snapshot

    a.register("run-exec-1", "llm-executor", workdir=str(tmp_path))
    b.register("tester-exec-1", "llm-executor", workdir=str(tmp_path))
    a.register("run-exec-2", "llm-executor", workdir=str(tmp_path))   # `a` has not seen b's write

    on_disk = json.loads(roster.read_text(encoding="utf-8"))
    assert set(on_disk) == {"run-exec-1", "tester-exec-1", "run-exec-2"}

    # …and a run tidying up after itself removes only what it staffed, in the directory it staffed.
    assert a.unregister("run-exec-1", workdir=str(tmp_path))["unregistered"] == "run-exec-1"
    assert a.unregister("tester-exec-1", workdir=str(tmp_path / "elsewhere"))["unregistered"] is None
    assert set(json.loads(roster.read_text(encoding="utf-8"))) == {"tester-exec-1", "run-exec-2"}


def test_a_dispute_the_protocol_cannot_carry_still_reaches_the_issuer(tmp_path):
    """An executor that disputes its contract mid-rework was answered with silence and a dead node.

    CHALLENGE is admissible from OFFERED only (§14.3) — a contract is disputed before it is taken,
    not while reworking under it. So when a reworking executor said the spec was wrong, the signal
    was refused, nothing else happened, and the node stayed exactly where it was with its round
    already spent: no re-spawn, no step, no line. Measured 2026-08-21 on a measurement run — the
    leaf contested at 01:27 and the graph never moved again; the run ended `graph_stalled`
    twenty-five minutes later, and the only trace was a `signal rejected` line in the audit.

    The dispute is not converted into work and the executor is not simply re-run (the same contract
    reproduces the same dispute, and pays for it). It becomes a step for the ISSUER, who is the only
    party who can change a contract — and a revision settles it by construction, because the node
    goes back to OFFERED for its executor to take afresh."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                 "predictability": "EXTRAORDINARY"}]})
    _child(e, "kid")
    T.signal(e, "kid", "ACCEPT", "exec-1")
    T.signal(e, "kid", "DELIVER", "exec-1", result="first try")
    T.signal(e, "kid", "FAIL", "agent", failed_criteria=["c"])
    assert e.get_state(TaskId("kid")).name == "REWORKING"

    llm = _AgentLLM(_fenced({"status": "challenge", "summary": "cannot be done as written",
                             "reason": "criterion c contradicts the parent's own scope"}))
    run_executor(e, TaskId("kid"), "exec-1", agents, _llm=llm)
    e.wait_idle()

    assert e.get_state(TaskId("kid")).name == "REWORKING"        # the refused signal moved nothing
    step = next(s for s in T.next_steps(e)["steps"] if s["task_id"] == "kid")
    assert "DISPUTES THE CONTRACT" in step["directive"]
    assert "contradicts the parent's own scope" in step["directive"]
    assert "revise" in step["directive"] and "reassign" in step["directive"]

    T.revise(e, "kid", {"description": "kid", "criteria": [{"name": "c", "description": "C, fixed"}]},
             agent="agent")
    e.wait_idle()
    later = next(s for s in T.next_steps(e)["steps"] if s["task_id"] == "kid")
    assert "DISPUTES THE CONTRACT" not in later["directive"]     # settled by the revision itself
    e.stop()


def test_a_node_that_already_refused_a_report_starts_at_the_retry_tier(tmp_path, monkeypatch):
    """Spending the cheap tier again on a node that has already refused once buys the same refusal.

    Measured across the recent runs (2026-08-21): 44 refused reports against 57 recorded verdicts,
    one node reaching FIVE refusals. A refused report is kept beside the node with a count, and that
    count survives a restart and a fresh delivery — where the in-process retry key does not. The
    retry tier is where the coverage discipline actually gets met, so a node with a refusal behind it
    starts there."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    T.create_task(e, "solo", {"description": "the work", "criteria": [{"name": "k", "description": "K"}],
                              "accepted_risks": [{"item": "an unmodelled environment fault",
                                                  "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    T.signal(e, "solo", "ACCEPT", "exec-1")
    T.signal(e, "solo", "DELIVER", "exec-1", result="did it")
    e.record_rejected_report(TaskId("solo"), "criterion k was never decided")

    seen = {}

    def _fake_validate(engine, task_id, agents_, model_override=None):
        seen["model"] = model_override
        return "rejected"

    d = Dispatcher(e, agents, runner=lambda *a: None, validator_runner=_fake_validate)
    d._validate_guarded(TaskId("solo"))
    assert seen["model"] == MODEL_VALIDATOR_RETRY      # …not the role's cheap default
    e.stop()


def test_a_roster_that_cannot_be_read_is_not_treated_as_an_empty_one(tmp_path):
    """Two testers' whole rosters vanished in a day, and one spent a run wondering why no validator
    ever fired.

    The merge in `_write` exists to stop a read-modify-write from erasing other processes'
    registrations — and it read the file through `_load`, which KEEPS the previous in-memory snapshot
    when the file cannot be parsed. So a roster caught mid-write by a concurrent process merged onto
    a stale snapshot and wrote everyone else's roles out of existence, through the one path the merge
    did not check (measured 2026-08-21). Losing one registration is recoverable; erasing the rest is
    not, so this refuses."""
    path = tmp_path / "agents.json"
    _ROSTER = json.dumps({"other-run-exec": {"kind": "llm-executor"}})
    path.write_text(_ROSTER, encoding="utf-8")
    reg = AgentRegistry(str(path))
    assert "other-run-exec" in reg.list()

    path.write_text(_ROSTER[:30], encoding="utf-8")            # a write caught half-done
    with pytest.raises(ValueError, match="could not be read"):
        reg.register("mine-1", "llm-executor", workdir=str(tmp_path))
    assert path.read_text(encoding="utf-8") == _ROSTER[:30]    # …and nothing was written over it

    path.write_text(_ROSTER, encoding="utf-8")
    reg.register("mine-1", "llm-executor", workdir=str(tmp_path))
    assert set(json.loads(path.read_text(encoding="utf-8"))) == {"other-run-exec", "mine-1"}


def test_the_executor_can_name_the_sibling_it_is_blocked_on(tmp_path):
    """A discovered dependency went unrecorded because whoever found it had nothing to point at.

    The packet listed only DECLARED upstream deps, so an executor blocked on work a SIBLING owns had
    no id for `blocker_task_ids` — the field that records a discovered Dep and feeds q_Dep. Measured
    twice on 2026-08-21: a README node spawned into an empty directory and blocked in prose, and a
    packaging node needed a `__main__.py` another child was writing. Both were real edges the plan
    never declared."""
    e = _eng()
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                 "predictability": "EXTRAORDINARY"}]})
    for kid in ("core", "readme"):
        T.create_task(e, kid, {"description": kid, "criteria": [{"name": "k", "description": "K"}]},
                      assignee="exec-1", parent_id="par")
    packet = run_executor.__globals__["_executor_packet"](e, e.get_task(TaskId("readme")), str(tmp_path))
    assert "`core`" in packet and "blocker_task_ids" in packet
    assert "NOT your work" in packet          # …named so it can be waited on, not done
    e.stop()


def test_a_human_issuer_gets_the_judging_and_keeps_the_signature(tmp_path, monkeypatch):
    """Two testers registered a validator, bound it, and watched nothing happen at all.

    Auto-validation fired only when the ISSUER was automated — the rule that a human's verdict is
    never taken from them — and it skipped the whole path rather than splitting it at the signature.
    So a person who had registered an `llm-validator` and bound it to their executor got no judging
    either, on both doors, while `register_agent` promised it fires "on EVERY delivery" (measured
    2026-08-21). Registering an instrument IS asking for the judging; §14.5 keeps only the signature
    theirs — so it runs, it records, and the person signs."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                 "predictability": "EXTRAORDINARY"}]},
                  assignee="a-human")                       # …an unregistered name: a person
    T.create_task(e, "kid", {"description": "the work", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="exec-1", parent_id="par")
    T.map_criterion(e, "par", "kid", "g")
    T.signal(e, "kid", "ACCEPT", "exec-1")
    T.signal(e, "kid", "DELIVER", "exec-1", result="did it")

    seen = []

    def _fake(engine, task_id, agents_, model_override=None, sign=True):
        seen.append((str(task_id), sign))
        return "recorded"

    d = Dispatcher(e, agents, runner=lambda *a: None, validator_runner=_fake)
    d.dispatch_once()
    time.sleep(1.0)
    assert seen == [("kid", False)]                          # …judged, and NOT signed for them
    assert e.get_state(TaskId("kid")).name == "VALIDATING"
    e.stop()


def test_a_validator_standing_somewhere_else_is_not_this_works_judge(tmp_path):
    """"First registered serves everyone" on a server-wide roster means the oldest entry of whoever
    came first.

    Measured twice (2026-08-20 and 21): a run's node judged by another run's validator standing in a
    scratch directory, and a tester who avoided it only by reading the help — "if I had registered an
    executor without an explicit validator, my package would have been judged by an agent standing in
    an unrelated directory". When an executor HAS a workspace and no instrument stands in it, the
    honest answer is none: the node waits for its issuer, who is told to register one."""
    a = AgentRegistry(path=str(tmp_path / "agents.json"))
    a.register("their-val", "llm-validator", workdir=str(tmp_path / "somewhere-else"))
    a.register("my-exec", "llm-executor", workdir=str(tmp_path / "my-work"))
    assert a.validator_for("my-exec") is None                 # …not their-val

    a.register("my-val", "llm-validator", workdir=str(tmp_path / "my-work"))
    assert a.validator_for("my-exec") == "my-val"             # …the one standing in the work
    a.register("pinned", "llm-validator", workdir=str(tmp_path / "somewhere-else"))
    a.register("my-exec", "llm-executor", workdir=str(tmp_path / "my-work"), validator="pinned")
    assert a.validator_for("my-exec") == "pinned"             # …an explicit binding still wins


def test_a_recorded_verdict_is_a_settled_outcome_and_is_not_retried(tmp_path, monkeypatch):
    """Every judged-for-you verdict was followed by a second paid run over the same delivery.

    A human issuer's node is judged and NOT signed (§14.5), so it stays in VALIDATING by design —
    and the retry branch read that state as "the validator died", queued a retry and spent another
    run minutes after the first had already answered (measured on the human door 2026-08-22, ~$1.4 of
    a $4.38 run went to literal duplicates). A settled outcome is settled whoever signs it."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                 "predictability": "EXTRAORDINARY"}]},
                  assignee="a-human")
    T.create_task(e, "kid", {"description": "the work", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="exec-1", parent_id="par")
    T.map_criterion(e, "par", "kid", "g")
    T.signal(e, "kid", "ACCEPT", "exec-1")
    T.signal(e, "kid", "DELIVER", "exec-1", result="did it")

    runs = []
    d = Dispatcher(e, agents, runner=lambda *a: None,
                   validator_runner=lambda en, t, a, model_override=None, sign=True:
                   (runs.append(str(t)) or "recorded"))
    d.dispatch_once()
    time.sleep(1.0)
    d.dispatch_once()
    time.sleep(1.0)
    assert runs == ["kid"]                      # …judged once, not once per poll
    e.stop()


def test_another_projects_validator_does_not_judge_this_projects_work(tmp_path):
    """A person who registered NOTHING had their nodes judged, and billed, by a stranger's role.

    Measured on the human door 2026-08-22: `val-1` — left in the shared roster by an experiment,
    standing in its scratch directory — auto-validated four nodes of a project that had registered no
    roles at all, $2.43 of a $4.38 run. The project name is the isolation boundary everywhere else;
    a role registered under another project is not this project's instrument."""
    a = AgentRegistry(path=str(tmp_path / "agents.json"))
    a.register("their-val", "llm-validator", workdir=str(tmp_path / "theirs"), project="their-run")
    assert a.validator_for(None, project="my-run") is None       # …not theirs
    assert a.validator_for("nobody", project="my-run") is None

    # …and a role registered with NO project is UNSCOPED, not foreign: the measurement arm registers
    # through the library and names none, and excluding it left a run with no validator at all
    # (measured 2026-08-22).
    a.register("library-val", "llm-validator", workdir=str(tmp_path / "arm"))
    assert a.validator_for(None, project="my-run") == "library-val"

    a.register("my-val", "llm-validator", workdir=str(tmp_path / "mine"), project="my-run")
    assert a.validator_for(None, project="my-run") == "my-val"
    assert a.validator_for(None, project="their-run") == "their-val"


def test_a_project_with_no_validator_is_not_a_validator_that_failed(tmp_path):
    """A graph that never had an instrument was reported as an instrument that failed twice.

    `_auto_validate` returned a bare None when no `llm-validator` is registered, and the caller reads
    None as "the run died": it queued a retry (a paid model run) and then parked the node for its
    issuer with "validator produced no verdict twice". An absence and a failure are opposite facts
    (register 2026-08-22, finding 6)."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"))          # …executor only, no judge
    _node(e, "t1", assignee="exec-1")
    d = Dispatcher(e, agents, runner=lambda *a: None)
    T.signal(e, "t1", "ACCEPT", "exec-1")
    T.signal(e, "t1", "DELIVER", "exec-1", result="out")

    d._validate_guarded(TaskId("t1"), 0)
    assert not d._retried, "a missing instrument was counted as a failed one"
    assert e.get_state(TaskId("t1")).name == "VALIDATING"            # …it waits for its issuer
    assert not e.validation_parked(TaskId("t1")) if hasattr(e, "validation_parked") else True


def test_the_roster_can_be_read_without_reading_everyone_elses(tmp_path, monkeypatch):
    """A caller with two roles was answered with forty-five, ~4.5k tokens of other people's work.

    The roster IS server-wide and stays so — that is the isolation model, and the answer keeps
    saying it. What was missing is a way to READ it: a filter and a bound (measured on the human
    door 2026-08-22)."""
    path = tmp_path / "roster.json"
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(path))
    reg = AgentRegistry(path=str(path))
    for i in range(30):
        reg.register(f"other-{i}", "llm-executor", workdir=str(tmp_path))
    reg.register("w17-exec-1", "llm-executor", workdir=str(tmp_path))
    reg.register("w17-val-1", "llm-validator", workdir=str(tmp_path))

    mine = TL.TOOLS["list_agents"](None, match="w17")
    assert sorted(mine["agents"]) == ["w17-exec-1", "w17-val-1"] and mine["total"] == 32
    # …and WHO would judge that executor: `validator: null` means "no override", not "nobody", and
    # the binding by workspace was unconfirmable from anywhere after registration.
    assert mine["agents"]["w17-exec-1"]["judged_by"] == "w17-val-1"
    assert "server-wide" in mine["scope"]                    # …the shared roster still says so

    capped = TL.TOOLS["list_agents"](None)
    assert len(capped["agents"]) == 25 and "`limit=0` returns all" in capped["note"]
    assert len(TL.TOOLS["list_agents"](None, limit=0)["agents"]) == 32


def test_the_project_rule_does_not_shadow_the_workdir_rule(tmp_path):
    """Two selection rules met and the newer one won by arriving first, undoing the older one.

    Scoping by project (2026-08-22) and standing in the same directory as the work (2026-08-20) are
    two INDEPENDENT coordinates of one choice, and the project branch returned before the workdir
    match was ever consulted: with a project named, the alphabetically-first unscoped judge beat the
    judge standing exactly where the artifact is — the very failure the workdir rule was built from,
    restored by the rule that was meant to be orthogonal to it.
    """
    a = AgentRegistry(path=str(tmp_path / "agents.json"))
    a.register("aaa-elsewhere", "llm-validator", workdir=str(tmp_path / "elsewhere"))
    a.register("zzz-in-the-work", "llm-validator", workdir=str(tmp_path / "work"))
    a.register("exec-1", "llm-executor", workdir=str(tmp_path / "work"), project="run-7")

    # both judges are unscoped, so both are candidates — and the one standing in the work wins
    assert a.validator_for("exec-1", project="run-7") == "zzz-in-the-work"

    # scope still comes FIRST: a judge of another project is not a candidate at all, even standing here
    b = AgentRegistry(path=str(tmp_path / "agents2.json"))
    b.register("theirs", "llm-validator", workdir=str(tmp_path / "work"), project="other-run")
    b.register("exec-1", "llm-executor", workdir=str(tmp_path / "work"), project="run-7")
    assert b.validator_for("exec-1", project="run-7") is None


def test_a_self_report_is_not_a_recorded_verdict_the_instrument_may_skip(tmp_path, monkeypatch):
    """The executor's own self-check was reused as if a validator had produced it — and SIGNED with
    the validator's name.

    An internal node carries `self_validation` in its DELIVER packet, and §14.5 D6 makes that its
    record: legal, and stored. The reuse rule below it exists for a different fact — "a fresh
    recorded verdict for this delivery already stands, so do not pay for a second run" — and it read
    the self-report as one. Two consequences, measured on the HTTP door 2026-09-02: the instrument
    never ran on four nodes although this deployment asks it to (`GFSO_VALIDATE_INTERNAL`), and the
    audit trail attributed every one of those PASSes to the registered validator role, which had
    judged nothing. `get_verdict` said the opposite in the same breath — SELF-REPORTED by the
    executor. The provenance surface is the one that may not lie.
    """
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                 "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    T.create_task(e, "kid", {"description": "the work", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="exec-1", parent_id="par")          # same Del as its parent ⟹ INTERNAL
    T.map_criterion(e, "par", "kid", "g")
    T.signal(e, "kid", "ACCEPT", "exec-1")
    T.signal(e, "kid", "DELIVER", "exec-1", result="did it", self_validation="PASS")

    e._graph.authorized_validators = {"val-1"}      # what the dispatcher publishes each round
    judged = []
    monkeypatch.setattr(D, "_judge_with",
                        lambda *a, **k: (judged.append(str(a[2])) or {"verdict": Verdict.PASS}))
    out = D._auto_validate(e, "kid", agents)

    assert judged == ["kid"], "the instrument must run: a self-report is not an independent verdict"
    assert out == "pass"
    e.stop()


def test_a_parent_delivered_over_unfinished_children_costs_nothing_to_refuse(tmp_path):
    """Two testers, two doors, one day: a parent went to VALIDATING while its children were still
    OFFERED/EXECUTING, and both read that as the validator being pointed at a tree without the work.

    DELIVER stays admissible — §14.3 says so and the engine is not narrower than the canon. What is
    pinned here is the PRICE: Thm 1 makes the parent's verdict the AND over its children, so there is
    nothing to decide until they settle, and the refusal must come before any model is touched. This
    is the regression pin for that guard, written after a wave read the situation as a burned round.
    """
    class _Explodes:
        def run_agent(self, *a, **k):
            raise AssertionError("a model was spent on a verdict the gate would refuse")

    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                 "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    T.create_task(e, "kid", {"description": "the work", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="exec-1", parent_id="par")
    T.map_criterion(e, "par", "kid", "g")
    T.signal(e, "par", "ACCEPT", "exec-1")
    T.signal(e, "par", "DELIVER", "exec-1", result="claims it is done")   # …while `kid` is OFFERED

    e._graph.authorized_validators = {"val-1"}
    assert D._auto_validate(e, "par", agents, _llm=_Explodes()) == "rejected"
    assert e._graph.get_task(TaskId("par")).state.name == "VALIDATING"    # …and it waits, honestly
    e.stop()


def test_a_consumer_is_not_spawned_while_its_producer_is_unfinished(tmp_path):
    """A tester watched a node enter EXECUTING and BLOCK itself on an input that did not exist yet,
    while `next_steps` had listed it under `waiting` with the three nodes it waits on.

    The spawn gate is what must hold here: a run started before its producers deliver can only end in
    the BLOCK it already reported, and it is paid for. This pins the gate itself — what the wave saw
    around it (six re-ASSIGNs from the plan rounds, then a BLOCK/RESOLVE cycle) is not reproduced
    here and is recorded as unexplained rather than guessed at.
    """
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"))
    for tid in ("prod", "cons"):
        T.create_task(e, tid, {"description": tid,
                               "criteria": [{"name": "c", "description": "C"}]}, assignee="exec-1")
    T.add_dependency(e, "prod", "cons", glue="cons reads what prod writes")

    spawned = []
    d = Dispatcher(e, agents, runner=lambda *a, **k: spawned.append(str(a[1])))
    d.dispatch_once()
    time.sleep(0.5)
    assert "prod" in spawned, "…and the control: the producer IS spawned, so the probe can see one"
    assert "cons" not in spawned, "a consumer spawned before its producer can only BLOCK"
    e.stop()


def test_a_node_with_children_is_not_spawned_as_if_it_were_a_leaf(tmp_path):
    """The dispatcher started an executor on a parent whose children had never run.

    The run re-did at the parent what the children were about to do, and the node then sat in
    VALIDATING for 24 minutes while they caught up (HTTP door, 2026-09-02). `next_steps` never
    offered it — it said `review`, the plan step — so the two rules disagreed about what is
    actionable, and the frontier was right: a non-leaf aggregates (Thm 1), it does not execute.
    """
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"))
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": [{"item": "an unmodelled environment fault",
                                                 "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    T.create_task(e, "kid", {"description": "the work", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="exec-1", parent_id="par")
    T.map_criterion(e, "par", "kid", "g")

    spawned = []
    d = Dispatcher(e, agents, runner=lambda *a, **k: spawned.append(str(a[1])))
    d.dispatch_once()
    time.sleep(0.5)
    assert "kid" in spawned, "…the control: the leaf IS spawned, so the probe can see one"
    assert "par" not in spawned, "a parent's work is its children's"
    e.stop()


def test_a_judge_that_belongs_to_no_project_says_so(tmp_path, monkeypatch):
    """The roster is one shared file, and a project that registered nothing gets whichever unscoped
    role came first.

    On the CLI door 2026-09-02 that was `val-1`, a leftover of a measurement run whose registered
    workdir points into that run's scratch directory, and it signed every node of a stranger's graph.
    The choice is deliberate — the arm's library roles carry no project either — so what is owed is
    not a refusal but a sentence, said where the person driving the graph reads it.
    """
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("stranger-val", "llm-validator"))
    T.create_task(e, "n", {"description": "the work",
                           "criteria": [{"name": "c", "description": "C"}]}, assignee="exec-1")
    T.signal(e, "n", "ACCEPT", "exec-1")
    T.signal(e, "n", "DELIVER", "exec-1", result="did it")

    said = []
    monkeypatch.setattr(e, "emit_info", lambda src, msg: said.append(msg))
    monkeypatch.setattr(e, "project_name", "mine", raising=False)
    monkeypatch.setattr(D, "_judge_with", lambda *a, **k: {"verdict": Verdict.PASS})
    e._graph.authorized_validators = {"stranger-val"}
    D._auto_validate(e, "n", agents)

    assert any("belongs to NO project" in m and "stranger-val" in m for m in said), said
    e.stop()


def test_registering_a_validator_says_what_it_will_judge(tmp_path, monkeypatch):
    """Registering the EXECUTOR first answers "nobody yet — register one here and it binds, in either
    order". Registering the validator second answered nothing at all, so the promised binding was
    unconfirmable until an execution was judged 25 minutes later (HTTP door, 2026-09-02). The
    question is symmetric; the answer is now too."""
    reg = AgentRegistry(path=str(tmp_path / "agents.json"))
    monkeypatch.setattr(TL, "_roster", lambda engine=None: reg)
    e = _eng()

    first = TL.register_agent(e, "w-exec", "llm-executor", workdir=str(tmp_path / "work"))
    assert "nobody YET" in str(first["will_be_judged_by"])

    second = TL.register_agent(e, "w-val", "llm-validator", workdir=str(tmp_path / "work"))
    assert second["will_judge"] == ["w-exec"], "the loop the first registration opened is closed"
    e.stop()


def test_a_judge_that_works_in_its_own_scratch_is_still_this_projects_judge(tmp_path):
    """A judge's REGISTERED workdir is where it works, not where the work is.

    `_judge_with` points it at the delivery at call time (the executor's workdir first), so requiring
    the two to be EQUAL measured the wrong thing — and it refused the measurement arm's own
    validator, which stands in a private scratch on purpose so one run cannot judge another's
    leftovers. Cost, measured 2026-09-02: auto-validation never fired, the arm waited 25 minutes for
    a verdict nobody was going to give, and a $20 run ended `validation_stalled`.

    What keeps a stranger out is the PROJECT scope; place breaks a tie inside it. With NO project
    there is nothing else, so place is the whole rule and none is the honest answer (the 2026-08-20
    measurement, unchanged — the test above still pins it).
    """
    a = AgentRegistry(path=str(tmp_path / "agents.json"))
    a.register("arm-exec", "llm-executor", workdir=str(tmp_path / "ws"), project="run-7")
    a.register("arm-val", "llm-validator", workdir=str(tmp_path / "scratch"), project="run-7")
    assert a.validator_for("arm-exec", project="run-7") == "arm-val"

    a.register("near", "llm-validator", workdir=str(tmp_path / "ws"), project="run-7")
    assert a.validator_for("arm-exec", project="run-7") == "near", "place still breaks the tie"

    b = AgentRegistry(path=str(tmp_path / "b.json"))
    b.register("their-val", "llm-validator", workdir=str(tmp_path / "elsewhere"))
    b.register("my-exec", "llm-executor", workdir=str(tmp_path / "mine"))
    assert b.validator_for("my-exec") is None, "with no project, place is the whole rule"
