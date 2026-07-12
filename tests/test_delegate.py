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


def test_multi_blocker_report_records_all_edges_and_gates_on_every_producer(tmp_path):
    """The executor's blocked report carries blocker_task_ids — EVERY named node records an edge
    (observed live: a 3-blocker deadlock reported through the singular schema recorded 0 edges →
    q_Dep starved, auto-resolve blind). The node then auto-resolves only when ALL producers are DONE."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}]})
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
    from gfso.core.types import DepEdge
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}]})
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
    T.create_task(e, "par", {"description": "parent", "criteria": [{"name": "g", "description": "G"}]})
    T.create_task(e, "cons", {"description": "consumer", "criteria": [
        {"name": "c", "description": "C"},
        {"name": "dep__prod", "description": "reads prod's output", "depends_on": "prod"}]},
        assignee="exec-1", parent_id="par")
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
    from gfso.decompose.build import build_graph_live
    spec = {"name": "goal", "root_criteria": [{"name": "r", "description": "R"}],
            "subtasks": [{"id": "a", "description": "A",
                          "criteria": [{"name": "ca", "description": "CA"}]}],
            "mappings": [{"criterion": "r", "child_id": "a"}], "deps": [], "neglected": [
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
    import time
    from gfso.delegate import _auto_validate
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    T.create_task(e, "par", {"description": "parent",
                             "criteria": [{"name": "g", "description": "G"}]}, assignee="exec-1")
    _child(e, "kid", assignee="exec-2")               # unregistered = human-ish, dispatcher passive
    T.signal(e, "par", "ACCEPT", "exec-1")
    T.signal(e, "par", "DELIVER", "exec-1", result="premature aggregate")
    ok = {"verdict": "PASS", "per_criterion": [], "failed_criteria": []}
    llm = _AgentLLM(_fenced(ok), _fenced(ok))
    d = Dispatcher(e, agents, runner=lambda *a: None,
                   validator_runner=lambda en, t, a: _auto_validate(en, t, a, _llm=llm))
    # (a) the gate: children not settled → no validator spawn at all
    assert not any("par" in s for s in d.dispatch_once())
    assert len(llm._texts) == 2
    # (b) force past the gate to exercise the rejected path (a race can still produce it)
    d._children_settled = lambda tid: True
    assert "validate:par" in d.dispatch_once()
    for _ in range(300):                              # verdict consumed + guarded postlude done
        if len(llm._texts) == 1 and "v:par#0" not in d._seen:
            break
        time.sleep(0.01)
    e.wait_idle()
    assert e.get_state(TaskId("par")).name == "VALIDATING"    # the PASS was FSM-rejected
    assert "v:par#0" not in d._seen                           # key freed for a later revalidation
    assert not d._retried                                     # NOT burned as a no-verdict retry
    del d.__dict__["_children_settled"]                       # restore the real gate
    T.signal(e, "kid", "ACCEPT", "exec-2")
    T.signal(e, "kid", "DELIVER", "exec-2", result="kid out")
    T.signal(e, "kid", "PASS", "exec-1")                      # issuer ≠ Del → accepted
    assert "validate:par" in d.dispatch_once()                # children settled → fresh validation
    for _ in range(300):
        if not llm._texts:
            break
        time.sleep(0.01)
    e.wait_idle()
    assert e.get_state(TaskId("par")).name == "DONE"          # this PASS survived the gate
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
    # fresh: REVIEW at iteration 0 → runs
    d._run_guarded(TaskId("t1"), "exec-1", 0)
    assert ran == ["t1"]
    # stale by state: the node delivered meanwhile → the queued run drops
    T.signal(e, "t1", "ACCEPT", "exec-1")
    T.signal(e, "t1", "DELIVER", "exec-1", result="out")
    d._run_guarded(TaskId("t1"), "exec-1", 0)
    assert ran == ["t1"]                                  # no second run
    # stale validate: iteration mismatch drops AND frees the key for a fresh dispatch
    d._seen.add("v:t1#5")
    validated = []
    d._validate = lambda en, t, a: validated.append(str(t)) or "pass"
    d._validate_guarded(TaskId("t1"), 5)                  # node is at iteration 0, not 5
    assert not validated and "v:t1#5" not in d._seen
    d._validate_guarded(TaskId("t1"), 0)                  # fresh: VALIDATING at iteration 0
    assert validated == ["t1"]
    e.stop()


def test_revision_resets_spawn_key(tmp_path):
    """A REVISED node (re-ASSIGN, same id → REVIEW) is fresh work: its consumed spawn key must not
    block the re-run (observed live: a refined root kept its key and was never re-executed)."""
    from gfso.core.types import Signal, Spec, AgentId
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
