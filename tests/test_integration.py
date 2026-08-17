"""Integration tests: full flows through Engine (L2)."""
from gfso.core.types import (
    AcceptedRiskItem, Predictability,
    State, Signal, TaskId, AgentId, SignalData,
    Spec, Criteria, Task, CriterionMapping, DepEdge,
    DispatchPayload, AgentPort,
)
from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.llm.stub import StubLLM


class AutoAgent(AgentPort):
    """Auto-responds: ASSIGN→ACCEPT→DELIVER→PASS."""
    def __init__(self):
        self.dispatches: list[DispatchPayload] = []

    def dispatch(self, agent_id, payload):
        self.dispatches.append(payload)
        match payload.signal:
            case Signal.ASSIGN:
                return SignalData(signal=Signal.ACCEPT, task_id=payload.task.id, source=agent_id)
            case Signal.ACCEPT:
                return SignalData(signal=Signal.DELIVER, task_id=payload.task.id, source=agent_id)
            case Signal.DELIVER:
                return SignalData(signal=Signal.PASS, task_id=payload.task.id, source=agent_id)
            case _:
                return None


def _engine(agent=None, validate=False) -> Engine:
    return Engine(
        storage=MemoryStorage(),
        agents=agent or AutoAgent(),
        llm=StubLLM(),
        validate_signals=validate,
    )


def test_revise_is_reassign_same_id_no_cascade():
    """Canon v3.7 Inv-1 (§14.4): REVISION = re-ASSIGN under the SAME id → OFFERED (NOT the CANCEL signal —
    no CANCELLING pass), each version appended to the log (Inv-7). The subtree is RETAINED (revision ≠
    abandonment): no cascade. Coverage staleness from a criteria change SURFACES via CHECK-1
    (surface-don't-destroy). The gate is the FSM's: ASSIGN needs the issuer role."""
    from gfso.adapters.agents.human import HumanAgent
    from gfso.core.types import AcceptedRiskItem
    import pytest
    A, B = AgentId("alice"), AgentId("bob")
    eng = Engine(MemoryStorage(), HumanAgent(), llm=StubLLM(), validate_signals=True)
    eng.start()

    def sp(d, *c, neg=()):
        return Spec(d, tuple(Criteria(n, t) for n, t in c), accepted_risks=neg)

    # Leaf revise (the planning case): SAME id, spec applied, logged as a second ASSIGN — NO CANCEL involved.
    eng.assign_task(TaskId("leaf"), sp("leaf", ("a", "a")), A); eng.wait_idle()
    eng.revise(TaskId("leaf"), sp("leaf", ("a", "a2"), neg=(AcceptedRiskItem("ext"),)), A); eng.wait_idle()
    lf = eng.get_task(TaskId("leaf"))
    assert lf.id == TaskId("leaf")                                    # SAME id — references survive
    assert lf.state == State.OFFERED                                   # revision → OFFERED (executor re-ACCEPTs)
    assert lf.spec.criteria[0].description == "a2" and [n.item for n in lf.spec.accepted_risks] == ["ext"]
    sigs = [a.signal for a in eng.audit_log(TaskId("leaf")) if not a.rejected]
    assert Signal.CANCEL not in sigs and sigs.count(Signal.ASSIGN) >= 2  # re-ASSIGN logged, no CANCEL

    # Parent revise: the subtree is RETAINED (revise ≠ abandon). Changing only ACCEPTED_RISKS here leaves coverage
    # intact → the child survives, no cascade.
    eng.assign_task(TaskId("p"), sp("p", ("g", "g")), A); eng.wait_idle()
    eng.decompose_task(TaskId("p"), [(TaskId("k"), sp("k", ("x", "x")), B)],
                       [CriterionMapping("g", TaskId("k"))]); eng.wait_idle()
    eng.revise(TaskId("p"), sp("p", ("g", "g"), neg=(AcceptedRiskItem("re"),)), A); eng.wait_idle()
    assert eng.get_task(TaskId("p")).id == TaskId("p")                          # same id
    assert [c.id for c in eng.get_active_children(TaskId("p"))] == [TaskId("k")]  # subtree RETAINED (no cascade)
    assert [n.item for n in eng.get_task(TaskId("p")).spec.accepted_risks] == ["re"]  # field re-authored

    # A criteria re-author that strands coverage does NOT destroy the child — the staleness SURFACES via CHECK-1
    # (the g->k mapping now dangles), which the agent must resolve (surface-don't-destroy).
    eng.revise(TaskId("p"), sp("p", ("g2", "renamed")), A); eng.wait_idle()
    assert [c.id for c in eng.get_active_children(TaskId("p"))] == [TaskId("k")]        # still there
    assert not {c.check_name: c for c in eng.get_checks(TaskId("p"))}["CHECK-1:coverage"].passed

    # Gate: the ISSUER may re-author a delegated OFFERED leaf; the EXECUTOR may not.
    eng.assign_task(TaskId("q"), sp("q", ("g", "g")), A); eng.wait_idle()
    eng.decompose_task(TaskId("q"), [(TaskId("d"), sp("d", ("z", "z")), B)],
                       [CriterionMapping("g", TaskId("d"))]); eng.wait_idle()
    eng.revise(TaskId("d"), sp("d", ("z2", "tight")), A); eng.wait_idle()   # issuer alice ✓
    assert eng.get_task(TaskId("d")).spec.criteria[0].description == "tight"
    with pytest.raises(ValueError):
        eng.revise(TaskId("d"), sp("d", ("z3", "no")), B)                  # executor bob ✗
    eng.stop()


def test_rmw_preserves_name_clears_done_reason_and_map_criterion():
    """RMW re-author must carry `name` (BUG: dropped) and clear the ABANDONED tombstone flag; map_criterion
    binds an existing child to repair coverage that a decompose/re-author left dangling (the covers blocker)."""
    from gfso.adapters.agents.human import HumanAgent
    from gfso.core.types import AcceptedRiskItem, State, DoneReason
    A = AgentId("alice")
    eng = Engine(MemoryStorage(), HumanAgent(), llm=StubLLM(), validate_signals=True)
    eng.start()
    eng.assign_task(TaskId("n"), Spec("desc", (Criteria("k", "keep"),), name="Human Label"), A); eng.wait_idle()
    eng.edit_accepted_risks(TaskId("n"), (AcceptedRiskItem("x"),), A); eng.wait_idle()
    t = eng.get_task(TaskId("n"))
    assert t.spec.name == "Human Label"                             # name carried through RMW
    assert t.done_reason is None and t.state == State.OFFERED        # tombstone flag cleared on re-author

    eng.assign_task(TaskId("p"), Spec("p", (Criteria("g", "g"),),
                    accepted_risks=(AcceptedRiskItem("an unmodelled environment fault",
                                                     Predictability.EXTRAORDINARY),)), A); eng.wait_idle()
    eng.decompose_task(TaskId("p"), [(TaskId("c"), Spec("c", (Criteria("z", "z"),)), A)], None); eng.wait_idle()
    checks = lambda: {c.check_name: c for c in eng.get_checks(TaskId("p"))}
    assert not checks()["CHECK-1:coverage"].passed                  # g uncovered (child unmapped)
    eng.map_criterion(TaskId("p"), TaskId("c"), "g"); eng.wait_idle()
    assert checks()["CHECK-1:coverage"].passed                      # bound → coverage repaired
    # the mapping went through the LOGGED FSM (child re-authored with covers), not a silent direct write
    assert any(a.signal == Signal.ASSIGN and not a.rejected for a in eng.audit_log(TaskId("c")))
    eng.stop()


def test_pass_requires_all_children_passed_theorem1():
    """Theorem 1 at runtime (§15.1): a decomposed parent cannot PASS until every active child has PASSed —
    enforced at the validation layer, not just advised by next_step."""
    from gfso.adapters.agents.human import HumanAgent
    from gfso.core.types import State
    A = AgentId("alice")
    eng = Engine(MemoryStorage(), HumanAgent(), llm=StubLLM(), validate_signals=True)
    eng.start()
    eng.assign_task(TaskId("p"), Spec("p", (Criteria("g", "g"),),
                    accepted_risks=(AcceptedRiskItem("an unmodelled environment fault",
                                                     Predictability.EXTRAORDINARY),)), A); eng.wait_idle()
    eng.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("p"), source=A)); eng.wait_idle()
    eng.decompose_task(TaskId("p"), [(TaskId("c"), Spec("c", (Criteria("z", "z"),)), A)],
                       [CriterionMapping("g", TaskId("c"))]); eng.wait_idle()
    eng.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("p"), source=A, result="x")); eng.wait_idle()
    e = eng.send_signal_sync(SignalData(signal=Signal.PASS, task_id=TaskId("p"), source=A)); eng.wait_idle()
    assert e is None or e.rejected                                # child not PASSed → parent PASS refused
    assert eng.get_state(TaskId("p")) == State.VALIDATING

    # PASS the child, then the parent PASS is allowed. The child shares the parent's Del (alice) —
    # an INTERNAL node (D6, §14.5): it self-verifies, no independent verdict demanded. The parent is
    # the ROOT = the public seam "done" must cross — ITS self-PASS still requires the recorded
    # verdict (verifier ≠ executor gate fires ON the seam, not on every node).
    eng.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("c"), source=A)); eng.wait_idle()
    eng.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("c"), source=A, result="ok")); eng.wait_idle()
    eng.send_signal_sync(SignalData(signal=Signal.PASS, task_id=TaskId("c"), source=A)); eng.wait_idle()
    assert eng.get_state(TaskId("c")) == State.DONE               # internal self-validation (D6)
    e = eng.send_signal_sync(SignalData(signal=Signal.PASS, task_id=TaskId("p"), source=A)); eng.wait_idle()
    assert e is None or e.rejected                                # ROOT self-pass without a verdict → refused
    eng.record_exec_verdict(TaskId("p"), "PASS", [], "validate_result")
    eng.send_signal_sync(SignalData(signal=Signal.PASS, task_id=TaskId("p"), source=A)); eng.wait_idle()
    assert eng.get_state(TaskId("p")) == State.DONE and eng.get_task(TaskId("p")).done_reason.name == "PASS"
    eng.stop()


def test_upper_convenience_edit_accepted_risks_and_edit_criteria():
    """UPPER layer = RMW over REVISE: edit_accepted_risks / edit_criteria change one field, carry the rest, and
    desugar to the logged signal path (no bypass)."""
    from gfso.adapters.agents.human import HumanAgent
    from gfso.core.types import AcceptedRiskItem
    A = AgentId("alice")
    eng = Engine(MemoryStorage(), HumanAgent(), llm=StubLLM(), validate_signals=True)
    eng.start()
    eng.assign_task(TaskId("n"), Spec("node", (Criteria("k", "keep"),), accepted_risks=(AcceptedRiskItem("old"),),
                                      scope=("payments — deliberately out",)), A)
    eng.wait_idle()

    eng.edit_accepted_risks(TaskId("n"), (AcceptedRiskItem("new1"), AcceptedRiskItem("new2")), A)
    t = eng.get_task(TaskId("n"))
    assert [x.item for x in t.spec.accepted_risks] == ["new1", "new2"]      # field changed
    assert [c.name for c in t.spec.criteria] == ["k"]                   # rest carried
    assert t.spec.scope == ("payments — deliberately out",)             # the scope tag is carried (§13.1)

    eng.edit_criteria(TaskId("n"), (Criteria("k2", "tighter"),), A)
    t = eng.get_task(TaskId("n"))
    assert [c.name for c in t.spec.criteria] == ["k2"]
    assert [x.item for x in t.spec.accepted_risks] == ["new1", "new2"]       # rest carried
    assert t.spec.scope == ("payments — deliberately out",)             # scope-пометка carried
    # logged via signals (RMW → revise → ASSIGN-from-OFFERED by the issuer; no bypass)
    sigs = [a.signal for a in eng.audit_log(TaskId("n")) if not a.rejected]
    assert sigs.count(Signal.ASSIGN) >= 3              # initial ASSIGN + edit_accepted_risks + edit_criteria

    # reassign (Del change) on a not-yet-committed node → issuer re-ASSIGNs to a new executor (logged)
    eng.reassign(TaskId("n"), AgentId("bob"))
    t = eng.get_task(TaskId("n"))
    assert t.assignee == AgentId("bob") and t.was_reassigned is True
    assert t.state == State.OFFERED  # no cascade, still authorable
    eng.stop()


def test_full_happy_path():
    """ASSIGN → OFFERED → ACCEPT → EXECUTING → DELIVER → VALIDATING → PASS → DONE."""
    engine = _engine()
    engine.start()

    task = engine.assign_task(
        TaskId("t1"),
        Spec("build feature", (Criteria("works", "works"),), ("risks",)),
        AgentId("dev"),
    )

    engine.wait_idle()
    assert engine.get_state(TaskId("t1")) == State.DONE

    task = engine.get_task(TaskId("t1"))
    assert task.done_reason is not None

    # Audit trail exists
    entries = engine.audit_log(TaskId("t1"))
    assert len(entries) > 0
    assert any(e.signal == Signal.ASSIGN for e in entries)
    assert any(e.new_state == State.DONE for e in entries)

    engine.stop()


def test_challenge_flow():
    """ASSIGN → CHALLENGE → ACCEPT_CHALLENGE → ACCEPT → EXECUTING."""

    class ChallengeAgent(AgentPort):
        def __init__(self):
            self.call_count = 0

        def dispatch(self, agent_id, payload):
            self.call_count += 1
            match payload.signal:
                case Signal.ASSIGN:
                    return SignalData(signal=Signal.CHALLENGE, task_id=payload.task.id, source=agent_id, reason="bad spec")
                case Signal.CHALLENGE:
                    return SignalData(signal=Signal.ACCEPT_CHALLENGE, task_id=payload.task.id, source=agent_id)
                case Signal.ACCEPT_CHALLENGE:
                    return SignalData(signal=Signal.ACCEPT, task_id=payload.task.id, source=agent_id)
                case _:
                    return None

    engine = _engine(ChallengeAgent())
    engine.start()
    engine.assign_task(TaskId("t1"), Spec("task", (Criteria("c1", "c1"),), ("r",)), AgentId("dev"))

    engine.wait_idle()
    assert engine.get_state(TaskId("t1")) == State.EXECUTING
    engine.stop()


def test_cancel_cascade_two_step_handshake():
    """v3.7 §14.2/§14.3: CANCEL opens the handshake (→ CANCELLING) and cascades CANCEL to the subtree;
    each node settles to ABANDONED on its executor's CONFIRM_CANCEL (in_flight logged, Thm 11)."""

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent())

    # Pre-create parent + child
    parent = Task(id=TaskId("p"), spec=Spec("parent", ()), assignee=AgentId("a"), state=State.EXECUTING)
    child = Task(id=TaskId("c1"), spec=Spec("child", ()), assignee=AgentId("a"), state=State.EXECUTING, parent_id=TaskId("p"))
    engine.graph.save_task(parent)
    engine.graph.save_task(child)

    engine.start()
    engine.send_signal(SignalData(signal=Signal.CANCEL, task_id=TaskId("p"), reason="cancelled"))
    engine.wait_idle()

    # Handshake open on parent AND (via cascade CANCEL) on the child
    assert engine.get_state(TaskId("p")) == State.CANCELLING
    assert engine.get_state(TaskId("c1")) == State.CANCELLING

    # Executor settles both with CONFIRM_CANCEL → ABANDONED (terminal, V=⊥, no done_reason)
    for tid in ("p", "c1"):
        engine.send_signal(SignalData(signal=Signal.CONFIRM_CANCEL, task_id=TaskId(tid),
                                      source=AgentId("a"), in_flight="stopped mid-work"))
    engine.wait_idle()
    for tid in ("p", "c1"):
        t = engine.get_task(TaskId(tid))
        assert t.state == State.ABANDONED and t.done_reason is None
    acked = [e for e in engine.audit_log(TaskId("p")) if e.signal == Signal.CONFIRM_CANCEL and not e.rejected]
    assert acked and acked[0].in_flight == "stopped mid-work"   # in-flight report logged (Thm 11)
    engine.stop()


def test_block_records_provisional_discovered_dep_and_resolve_adjudicates():
    """v3.7 §14.2/§15.2 two-phase discovered-Dep: BLOCK naming a prerequisite NODE records a provisional
    discovered edge (provenance = the BLOCK); RESOLVE_BLOCK adjudicates — confirm (default), re-attribute
    (corrected blocker_task_id), or retract (external=True, non-producible → FM-5 line). Feeds q_Dep."""

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent())
    A = AgentId("a")
    producer = Task(id=TaskId("prod"), spec=Spec("producer", ()), assignee=A, state=State.EXECUTING)
    other = Task(id=TaskId("other"), spec=Spec("other producer", ()), assignee=A, state=State.EXECUTING)
    consumer = Task(id=TaskId("cons"), spec=Spec("consumer", ()), assignee=A, state=State.EXECUTING)
    for t in (producer, other, consumer):
        engine.graph.save_task(t)
    engine.start()

    def _edges():
        return [(e.from_id, e.to_id, e.provisional) for e in engine.get_dependencies() if e.discovered]

    # BLOCK naming the prerequisite → provisional edge; q_Dep denominator becomes non-vacuous
    engine.send_signal(SignalData(signal=Signal.BLOCK, task_id=TaskId("cons"), source=A,
                                  reason="needs prod's schema", blocker_task_id=TaskId("prod")))
    engine.wait_idle()
    assert _edges() == [(TaskId("prod"), TaskId("cons"), True)]
    assert engine.metrics()["q_Dep"] == 0.0  # 0 declared / 1 discovered

    # Plain RESOLVE_BLOCK → confirms (provisional=False, still counted)
    engine.send_signal(SignalData(signal=Signal.RESOLVE_BLOCK, task_id=TaskId("cons"), source=A,
                                  action="prod delivered the schema"))
    engine.wait_idle()
    assert _edges() == [(TaskId("prod"), TaskId("cons"), False)]

    # Mis-attribution → re-attribute to the real source on resolve
    engine.send_signal(SignalData(signal=Signal.BLOCK, task_id=TaskId("cons"), source=A,
                                  reason="thought it was other", blocker_task_id=TaskId("other")))
    engine.wait_idle()
    engine.send_signal(SignalData(signal=Signal.RESOLVE_BLOCK, task_id=TaskId("cons"), source=A,
                                  blocker_task_id=TaskId("prod")))
    engine.wait_idle()
    assert (TaskId("other"), TaskId("cons"), True) not in _edges()      # provisional retracted

    # External (non-producible) blocker → retract on resolve; and a bare BLOCK records nothing
    engine.send_signal(SignalData(signal=Signal.BLOCK, task_id=TaskId("other"), source=A,
                                  reason="vendor API down"))            # no blocker_task_id → no edge
    engine.wait_idle()
    engine.send_signal(SignalData(signal=Signal.RESOLVE_BLOCK, task_id=TaskId("other"), source=A,
                                  external=True))
    engine.wait_idle()
    assert all(to != TaskId("other") for _, to, _p in _edges())
    engine.stop()


def test_multi_blocker_records_edge_per_prerequisite_and_adjudicates_the_set():
    """One BLOCK may surface SEVERAL undeclared prerequisites (§14.2: an edge per surfaced
    prerequisite — observed live: three blockers collapsed into prose recorded 0 edges, starving
    q_Dep and blinding auto-resolve). blocker_task_ids records a provisional edge PER existing node
    (a non-node → the FM-5 line, skipped); RESOLVE_BLOCK adjudicates the SET: payload-free confirms
    all, a corrected FULL set retracts the unlisted and writes the listed, external retracts all."""

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent())
    A = AgentId("a")
    for tid in ("p1", "p2", "p3", "c1", "c2", "c3"):
        engine.graph.save_task(Task(id=TaskId(tid), spec=Spec(tid, ()), assignee=A,
                                    state=State.EXECUTING))
    engine.start()

    def _edges(to):
        return sorted((str(e.from_id), e.provisional) for e in engine.get_dependencies()
                      if e.discovered and str(e.to_id) == to)

    # BLOCK with the plural payload (+ legacy singular merged in) → an edge per EXISTING node
    engine.send_signal(SignalData(signal=Signal.BLOCK, task_id=TaskId("c1"), source=A,
                                  reason="needs p1+p2+p3",
                                  blocker_task_id=TaskId("p3"),
                                  blocker_task_ids=(TaskId("p1"), TaskId("p2"), TaskId("ghost"))))
    engine.wait_idle()
    assert _edges("c1") == [("p1", True), ("p2", True), ("p3", True)]  # ghost → no edge (FM-5 line)
    assert engine.metrics()["q_Dep"] == 0.0                            # 0 declared / 3 discovered

    # payload-free RESOLVE_BLOCK confirms the whole set
    engine.send_signal(SignalData(signal=Signal.RESOLVE_BLOCK, task_id=TaskId("c1"), source=A,
                                  action="all delivered"))
    engine.wait_idle()
    assert _edges("c1") == [("p1", False), ("p2", False), ("p3", False)]

    # corrected FULL set: c2 blocked on (p1, p2); the issuer adjudicates the truth as (p2, p3)
    engine.send_signal(SignalData(signal=Signal.BLOCK, task_id=TaskId("c2"), source=A,
                                  reason="thought p1+p2",
                                  blocker_task_ids=(TaskId("p1"), TaskId("p2"))))
    engine.wait_idle()
    engine.send_signal(SignalData(signal=Signal.RESOLVE_BLOCK, task_id=TaskId("c2"), source=A,
                                  blocker_task_ids=(TaskId("p2"), TaskId("p3"))))
    engine.wait_idle()
    assert _edges("c2") == [("p2", False), ("p3", False)]              # p1 retracted, p3 written

    # external retracts the whole provisional set (non-producible blocker — the FM-5 currency line)
    engine.send_signal(SignalData(signal=Signal.BLOCK, task_id=TaskId("c3"), source=A,
                                  reason="vendor down, and I mis-blamed two nodes",
                                  blocker_task_ids=(TaskId("p1"), TaskId("p2"))))
    engine.wait_idle()
    engine.send_signal(SignalData(signal=Signal.RESOLVE_BLOCK, task_id=TaskId("c3"), source=A,
                                  external=True))
    engine.wait_idle()
    assert _edges("c3") == []
    engine.stop()


def test_discovered_edge_contradicting_declared_seam_surfaces_named_cycle_hole():
    """A BLOCK-discovered edge is GROUND TRUTH from contact; when it contradicts a declared seam
    the resulting cycle must be VISIBLE (a named CHECK-2 hole on the parent) IMMEDIATELY — the
    recorded-but-invisible shape was the live deadlock (list_holes stayed [] over a live 2-cycle
    because nothing refreshed the parent's cached checks after RECORD_DEP)."""

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent())
    A = AgentId("a")
    engine.graph.save_task(Task(id=TaskId("par"), spec=Spec("par", ()), assignee=A,
                                state=State.EXECUTING))
    for tid in ("x", "y"):
        engine.graph.save_task(Task(id=TaskId(tid), spec=Spec(tid, ()), assignee=A,
                                    state=State.EXECUTING, parent_id=TaskId("par")))
    engine.start()
    engine.add_dependency(TaskId("x"), TaskId("y"))       # declared: y depends on x
    engine.send_signal(SignalData(signal=Signal.BLOCK, task_id=TaskId("x"), source=A,
                                  reason="actually I consume y's output",
                                  blocker_task_ids=(TaskId("y"),)))
    engine.wait_idle()
    dag = [h for h in engine.graph_holes() if h["check"] == "CHECK-2:dag"]
    assert dag and "x" in dag[0]["details"] and "y" in dag[0]["details"]
    # and the refine/repair instruments receive the DIRECTION, not just the cycle: the declared
    # seam is named as refuted by the discovered (contact) edge
    from gfso.decompose import _dep_contradictions
    contr = _dep_contradictions(engine)
    assert len(contr) == 1 and "`x` depends on `y`" in contr[0] and "refuted" in contr[0]
    engine.stop()


def test_rework_flow():
    """FAIL with iteration < max → REWORKING → DELIVER → PASS → DONE."""

    class ReworkAgent(AgentPort):
        def __init__(self):
            self.fail_count = 0

        def dispatch(self, agent_id, payload):
            match payload.signal:
                case Signal.ASSIGN:
                    return SignalData(signal=Signal.ACCEPT, task_id=payload.task.id, source=agent_id)
                case Signal.ACCEPT:
                    return SignalData(signal=Signal.DELIVER, task_id=payload.task.id, source=agent_id)
                case Signal.DELIVER:
                    self.fail_count += 1
                    if self.fail_count <= 1:
                        return SignalData(signal=Signal.FAIL, task_id=payload.task.id, source=agent_id, failed_criteria=("c1",))
                    return SignalData(signal=Signal.PASS, task_id=payload.task.id, source=agent_id)
                case Signal.FAIL:
                    return SignalData(signal=Signal.DELIVER, task_id=payload.task.id, source=agent_id)
                case _:
                    return None

    engine = _engine(ReworkAgent())
    engine.start()
    engine.assign_task(TaskId("t1"), Spec("task", (Criteria("c1", "c1"),), ("r",)), AgentId("dev"))

    engine.wait_idle()
    assert engine.get_state(TaskId("t1")) == State.DONE
    assert engine.get_task(TaskId("t1")).iteration == 1
    engine.stop()


def test_exhausted_rework_escalates_and_stays_a_verdict():
    """FAIL past max_iterations settles in ESCALATED, not DONE (§14.3, corner #3).

    Driven through the live engine, not the transition table: what matters downstream is that the
    node ends in an attention terminal carrying its verdict — so a Dep consumer cannot read-and-build
    on it as a DONE result (§14.3 R′), and the standing-FAIL metric populations still see it.
    """
    from gfso.core.types import DoneReason
    from gfso.core.graph.metrics import false_fail_share

    class AlwaysFailAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            match payload.signal:
                case Signal.ASSIGN:
                    return SignalData(signal=Signal.ACCEPT, task_id=payload.task.id, source=agent_id)
                case Signal.ACCEPT | Signal.FAIL:
                    return SignalData(signal=Signal.DELIVER, task_id=payload.task.id, source=agent_id)
                case Signal.DELIVER:
                    return SignalData(signal=Signal.FAIL, task_id=payload.task.id, source=agent_id,
                                      failed_criteria=("c1",))
                case _:
                    return None

    engine = _engine(AlwaysFailAgent())
    engine.start()
    engine.assign_task(TaskId("t1"), Spec("task", (Criteria("c1", "c1"),), ("r",)), AgentId("dev"))
    engine.wait_idle()
    t = engine.get_task(TaskId("t1"))
    assert t.state == State.ESCALATED
    assert t.done_reason == DoneReason.FAIL           # the verdict, not a timeout escalation
    assert t.iteration == t.max_iterations
    assert false_fail_share(engine._graph) == 0.0     # the population is non-empty and unoverturned
    engine.stop()


def test_metrics_after_flow():
    """Metrics are computable after task completion."""
    engine = _engine()
    engine.start()

    engine.assign_task(TaskId("t1"), Spec("task", (Criteria("c1", "c1"),), ("r",)), AgentId("dev"))
    engine.wait_idle()

    m = engine.metrics()
    assert "q_T" in m
    assert "q_D" in m
    assert "q_V" in m
    assert "q_Dep" in m
    assert "q_Del" in m
    # q_T should be 1.0 (no challenges in happy path)
    assert m["q_T"] == 1.0
    engine.stop()


def test_events_fire():
    """on_transition callback fires on state changes."""
    transitions = []
    engine = _engine()
    engine.on_transition(lambda tid, old, new, sig: transitions.append((tid, new.name)))
    engine.start()

    engine.assign_task(TaskId("t1"), Spec("task", (Criteria("c1", "c1"),), ("r",)), AgentId("dev"))
    engine.wait_idle()

    assert len(transitions) > 0
    states_seen = [t[1] for t in transitions]
    assert "OFFERED" in states_seen
    assert "DONE" in states_seen
    engine.stop()


def test_decompose_task():
    """decompose_task creates children with parent-child edges + criterion mappings."""
    engine = _engine()
    engine.start()

    parent = engine.assign_task(
        TaskId("p"), Spec("parent", (Criteria("perf", "fast"), Criteria("security", "safe")), ("risks",)),
        AgentId("pm"),
    )
    engine.wait_idle()

    children = engine.decompose_task(
        TaskId("p"),
        [
            (TaskId("c1"), Spec("perf work", (Criteria("latency", "< 100ms"),)), AgentId("dev1")),
            (TaskId("c2"), Spec("security audit", (Criteria("no_vulns", "0 CVEs"),)), AgentId("dev2")),
        ],
        criterion_mappings=[
            CriterionMapping("perf", TaskId("c1")),
            CriterionMapping("security", TaskId("c2")),
        ],
    )

    assert len(children) == 2
    assert engine.get_children(TaskId("p")) != []

    parent = engine.get_task(TaskId("p"))
    assert len(parent.criterion_mappings) == 2

    engine.wait_idle()
    # Children should have been ASSIGN'd and processed
    assert engine.get_state(TaskId("c1")) is not None
    assert engine.get_state(TaskId("c2")) is not None
    engine.stop()


def test_add_dependency():
    """Declared dep = criteria-content on the consumer (derived edge); discovered = stored edge; q_Dep counts both."""
    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None
    engine = _engine(NoopAgent())  # tasks stay in OFFERED (re-authorable), not auto-completed
    engine.start()

    engine.assign_task(TaskId("t1"), Spec("a", (), ("r",)), AgentId("d"))
    engine.assign_task(TaskId("t2"), Spec("b", (), ("r",)), AgentId("d"))
    engine.wait_idle()

    engine.add_dependency(TaskId("t1"), TaskId("t2"), discovered=False)  # t2 depends on t1 (declared → t2's criterion)
    engine.add_dependency(TaskId("t2"), TaskId("t1"), discovered=True)   # surfaced via BLOCK (stored)

    deps = engine.get_dependencies()
    assert len(deps) == 2
    declared = [d for d in deps if not d.discovered]
    discovered = [d for d in deps if d.discovered]
    assert len(declared) == 1 and declared[0].from_id == TaskId("t1") and declared[0].to_id == TaskId("t2")
    assert len(discovered) == 1
    # the declared edge is derived from t2's criteria, not stored
    assert any(c.depends_on == TaskId("t1") for c in engine.get_task(TaskId("t2")).spec.criteria)

    assert engine.metrics()["q_Dep"] == 0.5  # 1 declared / 2 total
    engine.stop()


def test_tasks_by_state():
    """Query tasks by state."""

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent())
    engine.start()

    engine.assign_task(TaskId("t1"), Spec("a", (), ("r",)), AgentId("d"))
    engine.wait_idle()

    review_tasks = engine.tasks_by_state(State.OFFERED)
    assert any(t.id == TaskId("t1") for t in review_tasks)

    all_tasks = engine.all_tasks()
    assert len(all_tasks) >= 1
    engine.stop()


def test_tasks_by_assignee():
    """Query tasks by assignee."""

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent())
    engine.start()

    engine.assign_task(TaskId("t1"), Spec("a", (), ("r",)), AgentId("alice"))
    engine.assign_task(TaskId("t2"), Spec("b", (), ("r",)), AgentId("bob"))
    engine.wait_idle()

    alice_tasks = engine.tasks_by_assignee(AgentId("alice"))
    assert len(alice_tasks) == 1
    assert alice_tasks[0].id == TaskId("t1")
    engine.stop()


def test_send_signal_sync():
    """send_signal_sync returns audit entry."""

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent())
    engine.start()

    # Pre-create task in EXECUTING state
    task = Task(id=TaskId("t1"), spec=Spec("t", ()), state=State.EXECUTING, assignee=AgentId("d"))
    engine.graph.save_task(task)

    entry = engine.send_signal_sync(SignalData(signal=Signal.BLOCK, task_id=TaskId("t1"), reason="blocked"))

    assert entry is not None
    assert entry.new_state == State.BLOCKED
    assert not entry.rejected
    engine.stop()


# === Validation enforcement ===

def test_validation_rejects_fail_without_criteria():
    """FAIL without failed_criteria is rejected when validation enabled."""

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent(), validate=True)
    engine.start()

    task = Task(id=TaskId("t1"), spec=Spec("t", (Criteria("c1", "c1"),)),
                state=State.VALIDATING, assignee=AgentId("d"))
    engine.graph.save_task(task)

    entry = engine.send_signal_sync(
        SignalData(signal=Signal.FAIL, task_id=TaskId("t1"), source=AgentId("d"),
                   failed_criteria=()),  # empty — should be rejected
    )
    assert entry is not None
    assert entry.rejected
    engine.stop()


def test_validation_rejects_missing_source():
    """Non-system signal without source is rejected when validation enabled."""

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent(), validate=True)
    engine.start()

    task = Task(id=TaskId("t1"), spec=Spec("t", ()), state=State.EXECUTING, assignee=AgentId("d"))
    engine.graph.save_task(task)

    entry = engine.send_signal_sync(
        SignalData(signal=Signal.BLOCK, task_id=TaskId("t1"), source=None),  # no source
    )
    assert entry is not None
    assert entry.rejected
    engine.stop()


def test_validation_allows_system_signals_without_source():
    """System signals (TIMEOUT) don't need source."""

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent(), validate=True)
    engine.start()

    task = Task(id=TaskId("t1"), spec=Spec("t", ()), state=State.EXECUTING, assignee=AgentId("d"))
    engine.graph.save_task(task)

    entry = engine.send_signal_sync(
        SignalData(signal=Signal.TIMEOUT, task_id=TaskId("t1")),
    )
    assert entry is not None
    assert not entry.rejected
    assert entry.new_state == State.OVERDUE
    engine.stop()


def test_agent_cannot_sign_the_clock():
    """§14.2: the timeout "is not a P2P signal (no agent sends it) but a system mechanism enforcing
    finiteness". Both doors refuse it, and the defect is planted the way it actually happened — a node
    the executor itself walked to VALIDATING, where (VALIDATING, TIMEOUT) routes to DONE(auto_pass):
    a terminal reached around the AND gate (Thm 1), around verifier ≠ executor (§14.5) and around
    Inv-3, none of which a system signal ever meets (validation returns early for Role.SYSTEM)."""
    import pytest
    from gfso import tools
    from gfso.adapters.agents.human import HumanAgent

    engine = Engine(MemoryStorage(), HumanAgent(), llm=StubLLM(), validate_signals=True)
    engine.start()
    A = AgentId("alice")
    engine.assign_task(TaskId("root"), Spec("root", (Criteria("c1", "c1"),)), A); engine.wait_idle()
    engine.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("root"), source=A)); engine.wait_idle()
    engine.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("root"), source=A, result="x"))
    engine.wait_idle()
    assert engine.get_state(TaskId("root")) == State.VALIDATING

    # (1) the tool door: the alphabet is the twelve P2P signals, by name
    with pytest.raises(ValueError, match="not a P2P signal"):
        tools.signal(engine, "root", "TIMEOUT", source="alice")

    # (2) the engine, reached directly: a SOURCED system signal is an agent impersonating the clock
    entry = engine.send_signal_sync(
        SignalData(signal=Signal.TIMEOUT, task_id=TaskId("root"), source=A))
    engine.wait_idle()
    assert entry is not None and entry.rejected

    # the node did NOT settle either way
    t = engine.get_task(TaskId("root"))
    assert t.state == State.VALIDATING and t.done_reason is None
    engine.stop()


# === Callback tests ===

def test_on_reject_fires():
    """on_reject callback fires on rejected signals."""
    rejections = []

    class NoopAgent(AgentPort):
        def dispatch(self, agent_id, payload):
            return None

    engine = _engine(NoopAgent())
    engine.on_reject(lambda tid, sig, state: rejections.append((tid, sig.name, state.name)))
    engine.start()

    # Send invalid signal: PASS to IDLE task
    task = Task(id=TaskId("t1"), spec=Spec("t", ()), state=State.IDLE, assignee=AgentId("d"))
    engine.graph.save_task(task)
    engine.send_signal_sync(SignalData(signal=Signal.PASS, task_id=TaskId("t1"), source=AgentId("d")))

    assert len(rejections) == 1
    assert rejections[0][1] == "PASS"
    engine.stop()
