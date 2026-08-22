"""Q = (q_T, q_D, q_V, q_Dep, q_Del). Self-measuring from graph (Thm 10).

Formulas from paper §15.2/§21 (v3.8 — event-timely: each metric counts its defect at the protocol
event, on the population where the event could be observed; a defect trajectory ending
ABANDONED/ESCALATED stays counted; empty population → None (⊥ — undefined, rendered as a dash: no
observations is not "100%")):
  q_T   = 1 − |{n : challenged ∨ criteria changed for a spec defect}| / |{n : contract issued (ASSIGN)}|
  q_D   = 1 − |{n : non-atomic, own validation FAILed while all active children passed}|
              / |{n : non-atomic, own verdict (pass∨fail) while all active children passed}|  (auto_pass excluded)
  q_V   = 1 − |{n : false_positive}| / |{n : DONE(pass) ∨ DONE(auto)}|   (a PASS later found wrong, §24.5)
  q_Dep = |declared| / |declared ∪ discovered|
  q_Del = 1 − |{n : re-ASSIGN(capability_mismatch)}| / |{n : contract issued (ASSIGN)}|
"""
from __future__ import annotations

from typing import Optional

from gfso.core.types import State, DoneReason, Verdict, passed, settled_positive
from .model import Graph


# Where a node's own FAIL comes to REST. Exhausting the rework loop settles in ESCALATED (§14.3 —
# the canon carries no terminal for "V = fail, settled"; DONE is reached through acceptance only,
# §12.2), and the terminal carries DoneReason.FAIL so a verdict-escalation stays distinguishable
# from a timeout one. DONE(fail) is kept in the set because graphs written before that routing
# still hold such nodes — reading history correctly is not the same as producing it.
_STANDING_FAIL_STATES = (State.ESCALATED, State.DONE)


def q_T(graph: Graph) -> Optional[float]:
    """Task quality (canon §15.2/§21, v3.8): 1 − (contested contracts) / (issued contracts).

    High q_T = specs are clear. Low q_T = specs get challenged often. Event-timely: the defect counts
    at its protocol event (CHALLENGE, §14.6 "CHALLENGE → q_T event"), NOT gated on DONE — a challenged
    contract that dies in ABANDONED/ESCALATED (the worst spec-defect outcome) stays counted. Population
    = issued contracts (every node is created via ASSIGN, §15.1) ⟹ numerator ⊆ denominator.
    The canon numerator also includes "criteria changed for a spec defect" — instrumented via the
    §24.5 reason typing: a revision carrying reason=SPEC_DEFECT that changes criteria counts
    (scope expansion per §13.1 is sanctioned — reason=SCOPE_EXPANSION never counts); an UNTYPED
    criteria change stays uncounted (the documented under-approximation, now only for untyped acts).
    """
    all_tasks = graph._storage.get_all_tasks()
    if not all_tasks:
        return None  # empty population → ⊥ (§21: нет наблюдений — не «100%»)
    contested = sum(1 for t in all_tasks
                    if t.was_challenged or t.spec_defect_criteria_change)
    return 1.0 - contested / len(all_tasks)


def q_D(graph: Graph) -> Optional[float]:
    """Decomposition quality (canon §15.2/§21, v3.8): the false-positive-D defect = a non-atomic parent
    whose OWN validation returns FAIL while all its active children pass (FM-1 forgotten glue — the
    children compose-pass yet the parent's own criteria fail; §11.1/§12.1). q_D = 1 − (such defects) /
    (non-atomic parents that reached their own verdict — PASS or FAIL — with all active children passing).

    NB the earlier `DONE`-gated formula was degenerate: DONE ⟹ V=pass, so on {all-children-pass, DONE} the
    numerator ≡ denominator ⟹ q_D ≡ 1; the defect (it manifests as FAIL→REWORKING, never DONE) was unobservable.

    Signal of "parent FAILed its own validation ≥ once" = `iteration > 0` (INCREMENT_ITERATION fires ONLY on
    VALIDATING+FAIL→REWORKING, fsm.py) OR done_reason==FAIL (rework exhausted). auto_pass (done_reason==AUTO_PASS) is
    issuer inaction, not a verdict → excluded (§24.7). q_D observes only the DETECTED subset — a blind spot
    shared by parent and children still passes wrongly and stays in §24.5's residual.
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
        if not all(passed(c) for c in children):
            continue  # not all children passing → the false-positive-D precondition is absent
        failed_own = t.iteration > 0 or (t.state in _STANDING_FAIL_STATES
                                         and t.done_reason == DoneReason.FAIL)
        passed_own = passed(t)
        if not (failed_own or passed_own):
            continue  # parent has not reached its own verdict yet (or auto_pass = no verdict) → out of scope
        denom += 1
        if failed_own:
            defects += 1
    if denom == 0:
        return None  # empty population → ⊥ (§21)
    return 1.0 - defects / denom


def _q_V_later_failed(graph: Graph, t) -> bool:
    """"This pass was later found wrong" — the q_V event, with one owner.

    A record from a SUPERSEDED reopen generation is a verdict on the old cycle, not on this pass
    (R′ §14.3: the reopen already dropped that verdict; the refuted-old-pass case is carried by the
    `false_positive` flag, set at the fresh run's first FAIL)."""
    if t.false_positive:
        return True
    rec = graph.exec_verdict_record(t.id)
    return bool(rec) and rec.get("verdict") == Verdict.FAIL and rec.get("reopens", 0) == t.reopens


def q_V(graph: Graph) -> Optional[float]:
    """Validation quality: 1 − |{t : V=pass, later found wrong}| / |{t : V=pass}|.

    Paper §15.2: measures false positive rate in validation. The discovery CARRIER is the existing
    independent-validation instrument run POST-HOC: a `validate_result` FAIL recorded over a node that
    is already DONE(pass/auto) is the "pass → later found wrong" event (the verdict store keeps one
    record per node, so a post-hoc FAIL replaces the acceptance-time PASS). Derived at metric time
    from the verdict store — no new mutation surface; the `false_positive` flag additionally honors a
    manual/storage mark. Discovery stays external by nature (§24.5: a complaint / incident / audit is
    what makes someone re-run the check — without any re-check q_V remains optimistic; that blind
    zone is the canon's, not the instrument's).
    """
    all_tasks = graph._storage.get_all_tasks()
    # settled_positive, not passed: this population is every node that completed WITHOUT a
    # refusal, auto_pass included (§21 records that close apart from a pass — and counts it here).
    positives = [t for t in all_tasks if settled_positive(t)]
    if not positives:
        return None  # empty population → ⊥ (§21)

    def _later_failed(t) -> bool:
        return _q_V_later_failed(graph, t)

    return 1.0 - len([t for t in positives if _later_failed(t)]) / len(positives)


def q_V_reversed(graph: Graph) -> list[str]:
    """WHICH passes were later found wrong — q_V's numerator, by name.

    The number alone was unreadable: a reader watched it go 0.5 then 0.8 with nothing saying which
    node had had its PASS taken back (measured on the human door 2026-08-21, beside a `q_T` that
    does name its nodes). Derived from the same predicate q_V counts with, so the list and the
    number can never disagree."""
    return [str(t.id) for t in graph._storage.get_all_tasks()
            if settled_positive(t) and _q_V_later_failed(graph, t)]


def false_fail_share(graph: Graph) -> Optional[float]:
    """DIAGNOSTIC — deliberately OUTSIDE Q (§12.2/§24.5): false-FAIL is the guarantee-safe direction
    of FM-3 (it cannot create a false acceptance — DONE only via PASS §14.3, AND absorbs fail §11.3),
    so it is NOT a Q component; what the canon names aggregatable is the SHARE of false-FAILs as an
    over-strict-validator / griefing-issuer diagnostic. HIGH = bad (unlike q_*).

    Discovery carrier mirrors q_V's exactly: an independent-validation PASS standing over a node
    that ended DONE(fail) (rework exhausted) is the "fail → later found wrong" event — a post-hoc
    re-run, or a mid-flow independent PASS the issuer FAILed anyway (a standing FAIL contradicted
    by a recorded independent PASS is precisely the contested case this diagnostic exists for).
    Population = standing FAILs (DONE(fail)) only: a mid-flow FAIL later reworked is unknowable —
    the work changed, the later PASS proves nothing about the earlier verdict.

    Cross-read vs q_D (§24.5): q_D's numerator counts a parent's own-validation FAILs while all
    children pass — an over-strict validator's false-FAILs INFLATE that numerator (contaminate
    q_D downward). The canon keeps both formulas untouched (false-FAIL is guarantee-safe, the
    share is the named diagnostic): read a low q_D TOGETHER with this share — high false_fail_share
    marks the over-strict-validator systematics as the candidate cause before blaming D. No
    subtraction is defined (mid-flow false-FAILs are unknowable — population mismatch by design).
    """
    all_tasks = graph._storage.get_all_tasks()
    failed = [t for t in all_tasks
              if t.state in _STANDING_FAIL_STATES and t.done_reason == DoneReason.FAIL]
    if not failed:
        return None  # empty population → ⊥ (§21)

    def _overturned(t) -> bool:
        rec = graph.exec_verdict_record(t.id)
        return (bool(rec) and rec.get("verdict") == Verdict.PASS
                and rec.get("reopens", 0) == t.reopens)  # same generation only (R′ §14.3)

    return sum(1 for t in failed if _overturned(t)) / len(failed)


def q_Dep(graph: Graph) -> Optional[float]:
    """Dependency health: declared / (declared ∪ discovered).

    High q_Dep = deps were known upfront. Low = surprise blocks from hidden deps.
    """
    edges = graph.dep_edges()
    if not edges:
        return None  # empty population → ⊥ (§21)
    declared = sum(1 for e in edges if not e.discovered)
    total = len(edges)
    return declared / total


def q_Del(graph: Graph) -> Optional[float]:
    """Delegation quality (canon §15.2/§21, v3.8): 1 − (mis-delegations) / (issued contracts).

    High q_Del = right executor chosen first time. Low = capability mismatches. Event-timely: the
    defect counts at its protocol event (re-ASSIGN with a Del change — §14.4 Inv-1 "это событие и
    считает q_Del"), NOT gated on DONE — a reassigned node that never reaches DONE stays counted.
    Population = issued contracts (Del is total from ASSIGN) ⟹ numerator ⊆ denominator.
    The canon counts only re-ASSIGN(capability_mismatch) — instrumented via the §24.5 reason
    typing: a node whose Del changes under a TYPED reason counts only when that reason is
    CAPABILITY_MISMATCH; a node whose Del changed UNTYPED keeps the documented over-approximation
    (every untyped Del change counts, so the metric never silently improves by omitting the reason).
    """
    all_tasks = graph._storage.get_all_tasks()
    if not all_tasks:
        return None  # empty population → ⊥ (§21)
    reassigned = sum(1 for t in all_tasks
                     if (t.reassign_capability_mismatch if t.reassign_reason_typed
                         else t.was_reassigned))
    return 1.0 - reassigned / len(all_tasks)
