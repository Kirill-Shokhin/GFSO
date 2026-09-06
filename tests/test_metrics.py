"""Tests for graph/metrics.py — all 5 metrics from paper §15.2."""
import json

from gfso.core.types import TaskId, AgentId, Task, Spec, Criteria, State, DoneReason, DepEdge
from gfso.core.graph import Graph, q_T, q_D, q_V, q_Dep, q_Del, false_fail_share
from gfso.adapters.storage.memory import MemoryStorage
from gfso import tools as T
from tests.support import make_engine


def _task(tid, state=State.EXECUTING, assignee="a1", done_reason=None, was_challenged=False, parent_id=None):
    t = Task(
        id=TaskId(tid), spec=Spec("t", ()), state=state,
        assignee=AgentId(assignee) if assignee else None,
        done_reason=done_reason, parent_id=TaskId(parent_id) if parent_id else None,
    )
    t.was_challenged = was_challenged
    return t


def _graph(*tasks):
    g = Graph(MemoryStorage())
    for t in tasks:
        g.save_task(t)
    return g


# === q_T: spec quality ===

def test_q_T_perfect():
    g = _graph(
        _task("t1", State.DONE, done_reason=DoneReason.PASS),
        _task("t2", State.DONE, done_reason=DoneReason.PASS),
    )
    assert q_T(g) == 1.0

def test_q_T_half_challenged():
    g = _graph(
        _task("t1", State.DONE, done_reason=DoneReason.PASS, was_challenged=True),
        _task("t2", State.DONE, done_reason=DoneReason.PASS),
    )
    assert q_T(g) == 0.5

def test_q_T_empty_population_is_undefined():
    g = _graph()
    assert q_T(g) is None   # ⊥ (§21): no observations is not "100%"

def test_q_T_challenged_then_cancelled_still_counts():
    # Event-timeliness (v3.8): a challenged contract that DIED (ABANDONED — the worst spec-defect
    # outcome) stays counted. The old DONE-gate dropped exactly these trajectories.
    g = _graph(
        _task("t1", State.DONE, done_reason=DoneReason.PASS),
        _task("t2", State.ABANDONED, was_challenged=True),
    )
    assert q_T(g) == 0.5

def test_q_T_challenge_counts_at_the_event():
    # The metric moves the moment CHALLENGE happens (§14.6 "CHALLENGE → q_T event"), not at DONE.
    g = _graph(
        _task("t1", State.CHALLENGED, was_challenged=True),
        _task("t2", State.EXECUTING),
    )
    assert q_T(g) == 0.5


# === q_D: decomposition quality ===

def test_q_D_good_decomposition():
    g = _graph(
        _task("p", State.DONE, done_reason=DoneReason.PASS),
        _task("c1", State.DONE, done_reason=DoneReason.PASS, parent_id="p"),
        _task("c2", State.DONE, done_reason=DoneReason.PASS, parent_id="p"),
    )
    assert q_D(g) == 1.0

def test_q_D_bad_decomposition():
    # All children pass but parent fails → decomposition missed something
    g = _graph(
        _task("p", State.DONE, done_reason=DoneReason.FAIL),
        _task("c1", State.DONE, done_reason=DoneReason.PASS, parent_id="p"),
        _task("c2", State.DONE, done_reason=DoneReason.PASS, parent_id="p"),
    )
    assert q_D(g) == 0.0

def test_q_D_atomic_tasks_ignored():
    # Atomic tasks (no children) don't count → empty population → ⊥
    g = _graph(
        _task("t1", State.DONE, done_reason=DoneReason.PASS),
    )
    assert q_D(g) is None

def test_q_D_rework_counts_as_defect():
    # Parent in REWORKING (FAILed its own validation, not yet DONE) while all children pass — the case the
    # old DONE-gated formula MISSED (parent not DONE → excluded → q_D≡1). New: this IS the defect.
    p = _task("p", State.REWORKING)
    p.iteration = 1  # INCREMENT_ITERATION fires only on VALIDATING+FAIL→REWORKING
    g = _graph(
        p,
        _task("c1", State.DONE, done_reason=DoneReason.PASS, parent_id="p"),
        _task("c2", State.DONE, done_reason=DoneReason.PASS, parent_id="p"),
    )
    assert q_D(g) == 0.0

def test_q_D_reworked_to_pass_still_a_defect():
    # Parent FAILed its own validation once then reworked to PASS; children all pass. The old formula
    # counted this GOOD (done_reason PASS); the false-positive-D defect DID occur → it must count.
    p = _task("p", State.DONE, done_reason=DoneReason.PASS)
    p.iteration = 1
    g = _graph(
        p,
        _task("c1", State.DONE, done_reason=DoneReason.PASS, parent_id="p"),
    )
    assert q_D(g) == 0.0

def test_q_D_auto_pass_excluded():
    # auto_pass (issuer inaction, done_reason AUTO_PASS) is not a validation verdict → parent out of scope.
    p = _task("p", State.DONE, done_reason=DoneReason.AUTO_PASS)  # iteration 0 → never failed own validation
    g = _graph(
        p,
        _task("c1", State.DONE, done_reason=DoneReason.PASS, parent_id="p"),
    )
    assert q_D(g) is None  # empty denominator (auto-passed parent excluded) → ⊥

def test_q_D_mixed_half():
    good = _task("pg", State.DONE, done_reason=DoneReason.PASS)
    bad = _task("pb", State.REWORKING)
    bad.iteration = 1
    g = _graph(
        good, _task("cg", State.DONE, done_reason=DoneReason.PASS, parent_id="pg"),
        bad, _task("cb", State.DONE, done_reason=DoneReason.PASS, parent_id="pb"),
    )
    assert q_D(g) == 0.5


# === q_V: validation quality (1 - false_positives / passed) ===

def test_q_V_no_false_positives():
    g = _graph(
        _task("t1", State.DONE, done_reason=DoneReason.PASS),
        _task("t2", State.DONE, done_reason=DoneReason.PASS),
    )
    assert q_V(g) == 1.0

def test_q_V_half_false_positive():
    t1 = _task("t1", State.DONE, done_reason=DoneReason.PASS)
    t1.false_positive = True
    g = _graph(t1, _task("t2", State.DONE, done_reason=DoneReason.PASS))
    assert q_V(g) == 0.5

def test_q_V_auto_pass_counts():
    # auto-pass included in denominator (can also be false positive)
    t1 = _task("t1", State.DONE, done_reason=DoneReason.AUTO_PASS)
    t1.false_positive = True
    g = _graph(t1, _task("t2", State.DONE, done_reason=DoneReason.PASS))
    assert q_V(g) == 0.5

def test_q_V_ignores_fail():
    g = _graph(
        _task("t1", State.DONE, done_reason=DoneReason.PASS),
        _task("t2", State.DONE, done_reason=DoneReason.FAIL),
    )
    assert q_V(g) == 1.0

def test_q_V_posthoc_fail_verdict_is_the_discovery_carrier():
    # A validate_result FAIL recorded over an already-DONE(pass) node = "pass → later found wrong":
    # the metric derives it from the verdict store (no flag write needed).
    g = _graph(
        _task("t1", State.DONE, done_reason=DoneReason.PASS),
        _task("t2", State.DONE, done_reason=DoneReason.PASS),
    )
    g._storage.store_exec_verdict(TaskId("t1"), json.dumps(
        {"verdict": "FAIL", "failed_criteria": ["c1"], "validator": "val", "iteration": 0}))
    assert q_V(g) == 0.5

def test_q_V_acceptance_time_pass_verdict_not_counted():
    g = _graph(_task("t1", State.DONE, done_reason=DoneReason.PASS))
    g._storage.store_exec_verdict(TaskId("t1"), json.dumps(
        {"verdict": "PASS", "failed_criteria": [], "validator": "val", "iteration": 0}))
    assert q_V(g) == 1.0


# === false_fail_share: over-strict-validator DIAGNOSTIC (outside Q, §24.5) ===

def test_false_fail_share_posthoc_pass_overturns_standing_fail():
    # Mirror of q_V's carrier: an independent PASS recorded over DONE(fail) = "fail → later
    # found wrong". One of two standing FAILs overturned → share 0.5. HIGH = bad.
    g = _graph(
        _task("t1", State.DONE, done_reason=DoneReason.FAIL),
        _task("t2", State.DONE, done_reason=DoneReason.FAIL),
    )
    g._storage.store_exec_verdict(TaskId("t1"), json.dumps(
        {"verdict": "PASS", "failed_criteria": [], "validator": "val", "iteration": 3}))
    assert false_fail_share(g) == 0.5


def test_false_fail_share_fail_verdict_is_not_an_overturn():
    # The validator AGREEING with the standing FAIL is the ordinary case, not a discovery.
    g = _graph(_task("t1", State.DONE, done_reason=DoneReason.FAIL))
    g._storage.store_exec_verdict(TaskId("t1"), json.dumps(
        {"verdict": "FAIL", "failed_criteria": ["c1"], "validator": "val", "iteration": 3}))
    assert false_fail_share(g) == 0.0


def test_false_fail_share_population_is_standing_fails_only():
    # DONE(pass)/mid-flow nodes are out: a reworked FAIL is unknowable (the work changed).
    g = _graph(
        _task("t1", State.DONE, done_reason=DoneReason.PASS),
        _task("t2", State.REWORKING),
    )
    assert false_fail_share(g) is None  # ⊥: no standing FAILs at all


def test_false_fail_share_stays_out_of_Q():
    # §24.5: a diagnostic key rides NEXT TO Q in engine.metrics(), never as a 6th q_*.
    e = make_engine(llm=None)
    m = e.metrics()
    assert set(k for k in m if k.startswith("q_")) == {"q_T", "q_D", "q_V", "q_Dep", "q_Del"}
    assert "false_fail_share" in m


# === q_Dep: dependency health ===

def test_q_Dep_all_declared():
    g = _graph(_task("t1"), _task("t2"))
    g._storage.add_dep_edge(DepEdge(TaskId("t1"), TaskId("t2"), discovered=False))
    assert q_Dep(g) == 1.0

def test_q_Dep_half_discovered():
    g = _graph(_task("t1"), _task("t2"), _task("t3"))
    g._storage.add_dep_edge(DepEdge(TaskId("t1"), TaskId("t2"), discovered=False))
    g._storage.add_dep_edge(DepEdge(TaskId("t2"), TaskId("t3"), discovered=True))
    assert q_Dep(g) == 0.5

def test_q_Dep_no_deps_is_undefined():
    g = _graph(_task("t1"))
    assert q_Dep(g) is None   # ⊥ (§21)


# === q_Del: delegation quality (1 - reassigned/done) ===

def test_q_Del_no_reassignment():
    g = _graph(
        _task("t1", State.DONE, done_reason=DoneReason.PASS),
        _task("t2", State.DONE, done_reason=DoneReason.PASS),
    )
    assert q_Del(g) == 1.0

def test_q_Del_half_reassigned():
    t1 = _task("t1", State.DONE, done_reason=DoneReason.PASS)
    t1.was_reassigned = True
    g = _graph(
        t1,
        _task("t2", State.DONE, done_reason=DoneReason.PASS),
    )
    assert q_Del(g) == 0.5

def test_q_Del_empty_population_is_undefined():
    g = _graph()
    assert q_Del(g) is None   # ⊥ (§21)

def test_q_Del_reassigned_then_cancelled_still_counts():
    # Event-timeliness (v3.8): a mis-delegated node that never reaches DONE stays counted
    # (Inv-1: the re-ASSIGN-with-Del-change event is what q_Del counts).
    t2 = _task("t2", State.ABANDONED)
    t2.was_reassigned = True
    g = _graph(_task("t1", State.DONE, done_reason=DoneReason.PASS), t2)
    assert q_Del(g) == 0.5

def test_q_Del_reassign_counts_at_the_event():
    t1 = _task("t1", State.EXECUTING)
    t1.was_reassigned = True
    g = _graph(t1, _task("t2", State.EXECUTING))
    assert q_Del(g) == 0.5


def test_q_T_says_which_kind_of_spec_defect_each_node_carried():
    """Both members of the canon's numerator are spec defects, found at opposite ends.

    A CHALLENGE is an executor meeting a broken contract while working under it; a criteria change is
    one caught BEFORE the work — often by this product's own plan gate. A user who had just closed
    nine gate findings correctly read the resulting q_T as a grade on themselves (agent door,
    2026-09-02). The number is the canon's and does not move; what it is made of is now legible.
    """
    e = make_engine(check_interval=10_000)
    e.start()
    T.create_task(e, "a", {"description": "a", "criteria": [{"name": "c", "description": "C"}]},
                  assignee="worker")
    T.create_task(e, "b", {"description": "b", "criteria": [{"name": "c", "description": "C"}]},
                  assignee="worker")
    T.signal(e, "a", "CHALLENGE", "worker", reason="this criterion cannot be met as written")
    # the issuer revises: a root's issuer is its own Del (§14.2)
    T.edit_criteria(e, "b", [{"name": "c", "description": "sharper"}], agent="worker",
                    reason="spec_defect")
    e.wait_idle()

    m = T.metrics(e)["q_T_from"]
    assert m["disputed_by_an_executor"] == ["a"]
    assert m["repaired_before_the_work"] == ["b"]
    assert sorted(m["counted_against"]) == ["a", "b"], "both still count — the canon's numerator"
    e.stop()
