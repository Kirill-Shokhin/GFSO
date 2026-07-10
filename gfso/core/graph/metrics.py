"""Q = (q_T, q_D, q_V, q_Dep, q_Del). Self-measuring from graph (Th.10).

Formulas from paper §7.2/§13 (v3.8 — event-timely: each metric counts its defect at the protocol
event, on the population where the event could be observed; a defect trajectory ending
CANCELLED/ESCALATED stays counted; empty population → None (⊥ — undefined, rendered as a dash: no
observations is not "100%")):
  q_T   = 1 − |{n : challenged ∨ criteria changed for a spec defect}| / |{n : contract issued (ASSIGN)}|
  q_D   = 1 − |{n : non-atomic, own validation FAILed while all active children passed}|
              / |{n : non-atomic, own verdict (pass∨fail) while all active children passed}|  (auto_pass excluded)
  q_V   = 1 − |{n : false_positive}| / |{n : DONE(pass) ∨ DONE(auto)}|   (a PASS later found wrong, §16.5)
  q_Dep = |declared| / |declared ∪ discovered|
  q_Del = 1 − |{n : re-ASSIGN(capability_mismatch)}| / |{n : contract issued (ASSIGN)}|
"""
from __future__ import annotations

from typing import Optional

from gfso.core.types import State, DoneReason
from .model import Graph


def q_T(graph: Graph) -> Optional[float]:
    """Task quality (canon §7.2/§13, v3.8): 1 − (contested contracts) / (issued contracts).

    High q_T = specs are clear. Low q_T = specs get challenged often. Event-timely: the defect counts
    at its protocol event (CHALLENGE, §6.6 "CHALLENGE → q_T event"), NOT gated on DONE — a challenged
    contract that dies in CANCELLED/ESCALATED (the worst spec-defect outcome) stays counted. Population
    = issued contracts (every node is created via ASSIGN, §7.1) ⟹ numerator ⊆ denominator.
    The canon numerator also includes "criteria changed for a spec defect" (scope expansion per §5.1 is
    sanctioned, not a defect); the revision REASON is not instrumented (§16.5) — the counted subset is
    challenges (an under-approximation until reason typing lands).
    """
    all_tasks = graph._storage.get_all_tasks()
    if not all_tasks:
        return None  # empty population → ⊥ (§13: нет наблюдений — не «100%»)
    challenged = sum(1 for t in all_tasks if t.was_challenged)
    return 1.0 - challenged / len(all_tasks)


def q_D(graph: Graph) -> Optional[float]:
    """Decomposition quality (canon §7.2/§13, v3.8): the false-positive-D defect = a non-atomic parent
    whose OWN validation returns FAIL while all its active children pass (FM-1 forgotten glue — the
    children compose-pass yet the parent's own criteria fail; §3.1/§4.1). q_D = 1 − (such defects) /
    (non-atomic parents that reached their own verdict — PASS or FAIL — with all active children passing).

    NB the earlier `DONE`-gated formula was degenerate: DONE ⟹ V=pass, so on {all-children-pass, DONE} the
    numerator ≡ denominator ⟹ q_D ≡ 1; the defect (it manifests as FAIL→REWORK, never DONE) was unobservable.

    Signal of "parent FAILed its own validation ≥ once" = `iteration > 0` (INCREMENT_ITERATION fires ONLY on
    VALIDATING+FAIL→REWORK, fsm.py) OR done_reason==FAIL (rework exhausted). auto_pass (done_reason==AUTO) is
    issuer inaction, not a verdict → excluded (§16.7). q_D observes only the DETECTED subset — a blind spot
    shared by parent and children still passes wrongly and stays in §16.5's residual.
    (Simultaneity: a parent's own validation runs after it delivers its aggregate, i.e. post-children; the
    current all-children-pass state is the faithful proxy for "while all children were passing".)
    """
    all_tasks = graph._storage.get_all_tasks()
    denom = 0
    defects = 0
    for t in all_tasks:
        children = graph.get_active_children(t.id)  # cancelled tombstones not part of the decomposition
        if not children:
            continue  # atomic task — no decomposition to score
        if not all(c.state == State.DONE and c.done_reason == DoneReason.PASS for c in children):
            continue  # not all children passing → the false-positive-D precondition is absent
        failed_own = t.iteration > 0 or (t.state == State.DONE and t.done_reason == DoneReason.FAIL)
        passed_own = t.state == State.DONE and t.done_reason == DoneReason.PASS
        if not (failed_own or passed_own):
            continue  # parent has not reached its own verdict yet (or auto_pass = no verdict) → out of scope
        denom += 1
        if failed_own:
            defects += 1
    if denom == 0:
        return None  # empty population → ⊥ (§13)
    return 1.0 - defects / denom


def q_V(graph: Graph) -> Optional[float]:
    """Validation quality: 1 − |{t : V=pass, later found wrong}| / |{t : V=pass}|.

    Paper §7.2: measures false positive rate in validation. The discovery CARRIER is the existing
    independent-validation instrument run POST-HOC: a `validate_node` FAIL recorded over a node that
    is already DONE(pass/auto) is the "pass → later found wrong" event (the verdict store keeps one
    record per node, so a post-hoc FAIL replaces the acceptance-time PASS). Derived at metric time
    from the verdict store — no new mutation surface; the `false_positive` flag additionally honors a
    manual/storage mark. Discovery stays external by nature (§16.5: a complaint / incident / audit is
    what makes someone re-run the check — without any re-check q_V remains optimistic; that blind
    zone is the canon's, not the instrument's).
    """
    import json as _json
    all_tasks = graph._storage.get_all_tasks()
    passed = [t for t in all_tasks if t.state == State.DONE
              and t.done_reason in (DoneReason.PASS, DoneReason.AUTO)]
    if not passed:
        return None  # empty population → ⊥ (§13)

    def _later_failed(t) -> bool:
        if t.false_positive:
            return True
        raw = graph._storage.get_exec_verdict(t.id)
        if not raw:
            return False
        return _json.loads(raw).get("verdict") == "FAIL"

    false_positives = sum(1 for t in passed if _later_failed(t))
    return 1.0 - false_positives / len(passed)


def q_Dep(graph: Graph) -> Optional[float]:
    """Dependency health: declared / (declared ∪ discovered).

    High q_Dep = deps were known upfront. Low = surprise blocks from hidden deps.
    """
    edges = graph.dep_edges()
    if not edges:
        return None  # empty population → ⊥ (§13)
    declared = sum(1 for e in edges if not e.discovered)
    total = len(edges)
    return declared / total


def q_Del(graph: Graph) -> Optional[float]:
    """Delegation quality (canon §7.2/§13, v3.8): 1 − (mis-delegations) / (issued contracts).

    High q_Del = right executor chosen first time. Low = capability mismatches. Event-timely: the
    defect counts at its protocol event (re-ASSIGN with a Del change — §6.4 Inv-1 "это событие и
    считает q_Del"), NOT gated on DONE — a reassigned node that never reaches DONE stays counted.
    Population = issued contracts (Del is total from ASSIGN) ⟹ numerator ⊆ denominator.
    The canon counts only re-ASSIGN(capability_mismatch); the reassignment REASON is not instrumented
    (§16.5) — the code counts every Del change (an over-approximation until reason typing lands).
    """
    all_tasks = graph._storage.get_all_tasks()
    if not all_tasks:
        return None  # empty population → ⊥ (§13)
    reassigned = sum(1 for t in all_tasks if t.was_reassigned)
    return 1.0 - reassigned / len(all_tasks)
