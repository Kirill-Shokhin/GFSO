"""Q = (q_T, q_D, q_V, q_Dep, q_Del). Self-measuring from graph (Thm 10).

Formulas from paper §15.4/§15.6 (v3.8 — event-timely: each metric counts its defect at the protocol
event, on the population where the event could be observed; a defect trajectory ending
ABANDONED/ESCALATED stays counted; empty population → None (⊥ — undefined, rendered as a dash: no
observations is not "100%")):
  q_T   = 1 − |{n : challenged ∨ criteria changed for a spec defect}| / |{n : contract issued (ASSIGN)}|
  q_D   = 1 − |{n : non-atomic, own validation FAILed while all active children passed}|
              / |{n : non-atomic, own verdict (pass∨fail) while all active children passed}|  (auto_pass excluded)
  q_V   = 1 − |{n : false_positive}| / |{n : DONE(pass) ∨ DONE(auto)}|   (a PASS later found wrong, §15.4)
  q_Dep = |declared| / |declared ∪ discovered|
  q_Del = 1 − |{n : re-ASSIGN(capability_mismatch)}| / |{n : contract issued (ASSIGN)}|
"""
from __future__ import annotations

from typing import Optional

from gfso.core.types import State, Signal, DoneReason, Verdict, passed, settled_positive
from .model import Graph


# Where a node's own FAIL comes to REST. Exhausting the rework loop settles in ESCALATED (§12.5 —
# the canon carries no terminal for "V = fail, settled"; DONE is reached through acceptance only,
# §12.4), and the terminal carries DoneReason.FAIL so a verdict-escalation stays distinguishable
# from a timeout one. DONE(fail) is kept in the set because graphs written before that routing
# still hold such nodes — reading history correctly is not the same as producing it.
# …and ABANDONED, now that the issuer can CLOSE an escalated node: the node's own FAIL still
# stands (nobody overturned it), it just came to rest one state further on. The
# `done_reason == FAIL` conjunct every reader pairs with this set is what keeps an ordinary
# cancellation — which carries no reason — out of the population.
_STANDING_FAIL_STATES = (State.ESCALATED, State.DONE, State.ABANDONED)


#: What each number is ABOUT — in the module that computes it, so every door reads ONE writing.
#: (The UI carried its own copy until 2026-09-02 and it had DRIFTED: it defined q_D as "joint
#: sufficiency + non-redundancy" — not what the formula above counts — and gave q_Del an
#: "iteration overflow" term that is in no formula. A second writing of a rule is a defect.)
#: What each number is ABOUT — because two independent readers took a true number for a defect.
#: `q_T = 0.0` after fixing every criterion the plan gate flagged is CORRECT (§15.4 counts a
#: criteria change for a spec defect against the contracts AS ISSUED, not against whoever fixed
#: them), and `q_V = 1.0` on a graph with one unverified node is correct too (it counts pass→fail
#: reversals, and there were none). A right number read as a wrong one is a defect of the surface.
#: Not a Q member (§15.4) and served with them anyway, because the canon says to read a low q_D
#: TOGETHER with it — and unlike every q_*, HIGH is the bad direction here. A reader given six
#: numbers of which one runs the other way, unlabelled, reads it backwards.
DIAGNOSTIC_MEANS = {
    "false_fail_share": "over-strict validation, NOT a quality score and read the OPPOSITE way to "
                        "the q_* above: HIGH is bad. It is the share of standing FAILs that a "
                        "recorded independent PASS contradicts. A low q_D beside a high share here "
                        "means the validator, not the decomposition (§16.9).",
}

Q_MEANS = {
    "q_T": "the criteria AS ISSUED: 1 − (contracts challenged or changed for a spec defect) / "
           "(contracts issued). Fixing bad criteria is what LOWERS it — the score is about the "
           "authoring, never about the fixer (§15.4). So a plan repaired on the Level-2 gate's "
           "findings drives it DOWN, and 0.0 after obeying the gate is the expected reading, not a "
           "verdict on the person obeying: it measures what the DECOMPOSER issued, and the gate's "
           "whole job is to find that the issued contract was thin.",
    "q_D": "composition claims refuted at contact: parents that failed while every child passed (the q_D "
           "event, §15.4). A refutation, whatever refuted it — a split that missed something, a declared "
           "risk that bit, a false verdict on either side; charging the split needs the cause, read from "
           "the log (§16.9). ⊥ until some parent reaches its own verdict with all children passed.",
    "q_V": "verdicts that held: 1 − (passes later REFUTED) / (passes recorded) (§15.4). A pass is "
           "refuted when a later check fails it AS DELIVERED under the criteria it passed; a `reopen` "
           "alone is not that — it retires the verdict, not the record of it, so the node stays in the "
           "population without counting against it. A reopened node whose fresh run FAILs the same "
           "re-delivered result is exactly the pass→later-fail term (§15.4), and it counts from that "
           "FAIL though the node is no longer DONE; a fresh run on another result refutes nothing of "
           "the old pass. 1.0 therefore means nothing that passed has been contradicted as delivered — "
           "NOT that everything was independently verified, and NOT that no verdict was ever withdrawn.",
    "q_Dep": "dependencies declared up front vs discovered at runtime through BLOCK.",
    "q_Del": "delegation correctness: nodes reassigned for capability mismatch.",
}

def q_T(graph: Graph) -> Optional[float]:
    """Task quality (canon §15.4/§15.6, v3.8): 1 − (contested contracts) / (issued contracts).

    High q_T = specs are clear. Low q_T = specs get challenged often. Event-timely: the defect counts
    at its protocol event (CHALLENGE, §15.7 "CHALLENGE → q_T event"), NOT gated on DONE — a challenged
    contract that dies in ABANDONED/ESCALATED (the worst spec-defect outcome) stays counted. Population
    = issued contracts (every node is created via ASSIGN, §15.1) ⟹ numerator ⊆ denominator.
    The canon numerator also includes "criteria changed for a spec defect" — instrumented via the
    §15.4 reason typing: a revision carrying reason=SPEC_DEFECT that changes criteria counts
    (scope expansion per §15.4 is sanctioned — reason=SCOPE_EXPANSION never counts); an UNTYPED
    criteria change stays uncounted (the documented under-approximation, now only for untyped acts).
    """
    all_tasks = graph._storage.get_all_tasks()
    if not all_tasks:
        return None  # empty population → ⊥ (§15.4: нет наблюдений — не «100%»)
    challenged, repaired = q_T_numerator(graph)
    return 1.0 - (len(challenged) + len(repaired)) / len(all_tasks)


def q_T_numerator(graph: Graph) -> tuple[list[str], list[str]]:
    """q_T's numerator, split by where the spec defect was met: (challenged — a CHALLENGE no REJECT_CHALLENGE refuted,
    repaired — criteria changed for a spec defect, unchallenged). The one owner the metric and its explanation read."""
    refuted = _every_challenge_refuted(_fail_events(graph)[1])
    tasks = graph._storage.get_all_tasks()
    challenged = [str(t.id) for t in tasks if t.was_challenged and str(t.id) not in refuted]
    return challenged, [str(t.id) for t in tasks if t.spec_defect_criteria_change and str(t.id) not in challenged]


def _every_challenge_refuted(timeline: dict) -> set:
    """The nodes whose every CHALLENGE the log shows answered by a REJECT_CHALLENGE — off q_T's count (§15.4, v4.1: "a
    CHALLENGE no REJECT_CHALLENGE refuted"). A challenge still standing, accepted, superseded by a revision or closed by
    a CANCEL keeps its node counted; the flag set on entry and never cleared counted refuted ones too (C-F2b)."""
    out = set()
    for tid, rows in timeline.items():
        seen = standing = False
        for _ts, sig, new in rows:
            if new == State.CHALLENGED.name:
                seen = standing = True
            elif standing:
                if sig != Signal.REJECT_CHALLENGE.name:
                    break                              # one challenge not refuted: the node counts
                standing = False
        else:
            if seen and not standing:
                out.add(tid)
    return out


def _fail_events(graph: Graph) -> tuple[dict, dict]:
    """({task: [ts of its own FAILs]}, {task: [(ts, signal, new_state) …]}) — the log, folded once.

    Folded here rather than per node because q_D asks the same question of every parent and the log
    is one read: the whole trail, oldest first, by node.
    """
    fails: dict = {}
    timeline: dict = {}
    for row in graph._storage.load_audit():
        if row.get("rejected"):
            continue                               # a refused signal moved nothing
        tid = str(row.get("task_id"))
        timeline.setdefault(tid, []).append(
            (str(row.get("ts") or ""), row.get("signal"), row.get("new_state")))
        if row.get("signal") == Signal.FAIL.name:
            fails.setdefault(tid, []).append(str(row.get("ts") or ""))
    return fails, timeline


def _active(children) -> list:
    """The children in the decomposition for q_D: every one not ABANDONED (§15.4) — a CANCELLING child is still
    there and not passing."""
    return [c for c in children if c.state != State.ABANDONED]


def _verdict_while_children_passed(log: tuple[dict, dict], t, children, signal: Signal) -> bool:
    """Did this parent's OWN validation say `signal` (PASS or FAIL) at a moment when every child active THEN was
    passing? Both arms read the moment off the log (§15.4: a node is in a set iff the log records its event,
    "whatever state it reaches later") — the PASS arm read the current state, and a REOPEN of a whole that had
    passed took it out of q_D (critic B1). `children` are all of them, tombstones included: a child CANCELLING at
    the verdict and ABANDONED since was active and not passing then."""
    _, timeline = log
    own = [r[0] for r in timeline.get(str(t.id), ()) if r[1] == signal.name]
    if not own:   # no trail — the current-state proxy, and only here
        now = (passed(t) if signal == Signal.PASS else
               t.iteration > 0 or (t.state in _STANDING_FAIL_STATES and t.done_reason == DoneReason.FAIL))
        return now and all(passed(c) for c in _active(children))
    # ISO-8601 stamps of one format compare as strings; the log is the ordering, not the clock.
    return any(_all_passing_at([timeline.get(str(c.id), ()) for c in children], ts) for ts in own)


def _all_passing_at(trails: list, ts: str) -> bool:
    """Was every child active at `ts` DONE on a PASS then? — each one's last entry not after that moment says so; a
    child ABANDONED by then had left the decomposition, and one with no entry by then was not passing."""
    last = [before[-1] if (before := [r for r in rows if r[0] <= ts]) else None for rows in trails]
    active = [r for r in last if r is None or r[2] != State.ABANDONED.name]
    return bool(active) and all(r is not None and r[1] == Signal.PASS.name and r[2] == State.DONE.name
                                for r in active)


def q_D(graph: Graph) -> Optional[float]:
    """The observed rate of composition claims refuted at contact (canon §15.4, §15.4): a non-atomic parent
    whose OWN validation returns FAIL while all its active children pass. Its cause is not in the event —
    forgotten glue (FM-1), a declared risk that bit (FM-5/FM-6), or a false verdict on either side (FM-3)
    give the same pattern — and is read from the log. q_D = 1 − (such refutations) /
    (non-atomic parents that reached their own verdict — PASS or FAIL — with all active children passing).

    NB the earlier `DONE`-gated formula was degenerate: DONE ⟹ V=pass, so on {all-children-pass, DONE} the
    numerator ≡ denominator ⟹ q_D ≡ 1; the defect (it manifests as FAIL→REWORKING, never DONE) was unobservable.

    Signal of "parent FAILed its own validation ≥ once" = `iteration > 0` (INCREMENT_ITERATION fires ONLY on
    VALIDATING+FAIL→REWORKING, fsm.py) OR done_reason==FAIL (rework exhausted). auto_pass (done_reason==AUTO_PASS) is
    issuer inaction, not a verdict → excluded (§16.14). q_D observes only the DETECTED subset — a blind spot
    shared by parent and children still passes wrongly and stays in §15.4's residual.

    WHILE ALL CHILDREN PASSED is a fact about the moment of the FAIL, and it was read off the
    CURRENT state. `iteration > 0` counts any rework round the node has ever had, so a parent that
    FAILed while a child was still red — where its aggregate could not have been right, and the
    decomposition is not what was wrong — was counted as a q_D event as soon as that
    child went green afterwards. The log carries the moment (Thm 11), so the moment is what is read:
    each of the parent's FAIL entries is weighed against the children as they stood then. Where the
    log says nothing about this node (a graph assembled without one), the current-state proxy the
    formula always used stands in, and it is the only place the approximation still lives.
    """
    all_tasks = graph._storage.get_all_tasks()
    log = _fail_events(graph)
    denom = 0
    defects = 0
    for t in all_tasks:
        everyone = graph.get_children(t.id)
        children = _active(everyone)
        if not children:
            continue  # atomic, or nothing left of its decomposition — no claim to score
        failed_own = _verdict_while_children_passed(log, t, everyone, Signal.FAIL)
        passed_own = _verdict_while_children_passed(log, t, everyone, Signal.PASS)
        if not (failed_own or passed_own):
            continue  # parent has not reached its own verdict with its children green → out of scope
        denom += 1
        if failed_own:
            defects += 1
    if denom == 0:
        return None  # empty population → ⊥ (§15.4)
    return 1.0 - defects / denom


def once_settled_positive(t) -> bool:
    """Did this node EVER close without a refusal — whether or not it still stands there?

    q_V's population was `settled_positive`, read off the CURRENT state, and §15.4's own carrier
    falls out of it: a DONE that is reopened and then FAILs is "exactly the pass→later-fail term of
    q_V", and by the time that term exists the node is in REWORKING, i.e. no longer DONE. So the
    node left the denominator AND the numerator together, and the one event the canon names as q_V's
    discovery carrier moved the metric by nothing at all. `false_positive` is set precisely at that
    fresh FAIL (and by a manual mark), so it is what says "this once settled positive" after the
    settlement has been taken back.
    """
    return settled_positive(t) or t.false_positive


def _pass_recorded(graph: Graph) -> list:
    """q_V's population, "a PASS was recorded" (§15.4): a node standing settled positive, or once settled so — a
    reopen erases V = pass, not the record of it, which the log keeps."""
    logged = {str(r.get("task_id")) for r in graph._storage.load_audit()
              if r.get("signal") == Signal.PASS.name and not r.get("rejected")}
    return [t for t in graph._storage.get_all_tasks() if once_settled_positive(t) or str(t.id) in logged]


def pass_was_refuted(graph: Graph, t) -> bool:
    """"This pass was later found wrong" — the q_V event, with one owner.

    Exported because it is not only a metric: a node in this state is a node whose surfaces say PASS
    while its own current record says FAIL, and until 2026-09-02 the ONLY place that fact was said
    was inside q_V. Measured on the CLI door: a signed PASS, an instrument returning FAIL four
    seconds later, the FSM correctly refusing that signal on a terminal node — and `status` printing
    `[x] DONE` and the frontier answering COMPLETE for good. The engine knew, by name.

    A record from a SUPERSEDED reopen generation is a verdict on the old cycle, not on this pass
    (R′ §12.14: the reopen already dropped that verdict; the refuted-old-pass case is carried by the
    `false_positive` flag, set at the fresh run's first FAIL).
    """
    if t.false_positive:
        return True
    rec = graph.exec_verdict_record(t.id)
    return bool(rec) and rec.get("verdict") == Verdict.FAIL and rec.get("reopens", 0) == t.reopens


def q_V(graph: Graph) -> Optional[float]:
    """Validation quality: 1 − |{t : V=pass, later found wrong}| / |{t : V=pass}|.

    Paper §15.4: measures false positive rate in validation. The discovery CARRIER is the existing
    independent-validation instrument run POST-HOC: a `validate_result` FAIL recorded over a node that
    is already DONE(pass/auto) is the "pass → later found wrong" event (the verdict store keeps one
    record per node, so a post-hoc FAIL replaces the acceptance-time PASS). Derived at metric time
    from the verdict store — no new mutation surface; the `false_positive` flag additionally honors a
    manual/storage mark. Discovery stays external by nature (§15.4: a complaint / incident / audit is
    what makes someone re-run the check — without any re-check q_V remains optimistic; that blind
    zone is the canon's, not the instrument's).
    """
    # "a PASS was recorded" (§15.4): every node that completed WITHOUT a refusal, auto_pass included (§15.6 records
    # that close apart from a pass — and counts it here), and it stays in once a reopen has taken the settlement
    # back (§12.14) — whether its fresh run then failed the same artifact or not: the record is the log's.
    positives = _pass_recorded(graph)
    if not positives:
        return None  # empty population → ⊥ (§15.4)

    def _later_failed(t) -> bool:
        return pass_was_refuted(graph, t)

    return 1.0 - len([t for t in positives if _later_failed(t)]) / len(positives)


def q_V_reversed(graph: Graph) -> list[str]:
    """WHICH passes were later found wrong — q_V's numerator, by name.

    The number alone was unreadable: a reader watched it go 0.5 then 0.8 with nothing saying which
    node had had its PASS taken back (measured on the human door 2026-08-21, beside a `q_T` that
    does name its nodes). Derived from the same predicate q_V counts with, so the list and the
    number can never disagree."""
    return [str(t.id) for t in _pass_recorded(graph) if pass_was_refuted(graph, t)]


def false_fail_share(graph: Graph) -> Optional[float]:
    """DIAGNOSTIC — deliberately OUTSIDE Q (§8.4/§15.4): false-FAIL is the guarantee-safe direction
    of FM-3 (it cannot create a false acceptance — DONE only via PASS §12.4, AND absorbs fail §7.2),
    so it is NOT a Q component; what the canon names aggregatable is the SHARE of false-FAILs as an
    over-strict-validator / griefing-issuer diagnostic. HIGH = bad (unlike q_*).

    Discovery carrier mirrors q_V's exactly: an independent-validation PASS standing over a node
    that ended DONE(fail) (rework exhausted) is the "fail → later found wrong" event — a post-hoc
    re-run, or a mid-flow independent PASS the issuer FAILed anyway (a standing FAIL contradicted
    by a recorded independent PASS is precisely the contested case this diagnostic exists for).
    Population = standing FAILs (DONE(fail)) only: a mid-flow FAIL later reworked is unknowable —
    the work changed, the later PASS proves nothing about the earlier verdict.

    Cross-read vs q_D (§16.9): q_D's numerator counts a parent's own-validation FAILs while all
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
        return None  # empty population → ⊥ (§15.4)

    def _overturned(t) -> bool:
        rec = graph.exec_verdict_record(t.id)
        return (bool(rec) and rec.get("verdict") == Verdict.PASS
                and rec.get("reopens", 0) == t.reopens)  # same generation only (R′ §12.14)

    return sum(1 for t in failed if _overturned(t)) / len(failed)


def q_Dep(graph: Graph) -> Optional[float]:
    """Dependency health: declared / (declared ∪ discovered).

    What it measures, exactly (§15.5, restated in v4.1): of the dependencies that were DISCOVERED —
    the ones a BLOCK exposed — how many the plan had declared in advance. It is not a share of S:
    nobody observes S's dependency structure, and an edge nothing ever ran into is not in either
    half. High = the blockers met were the ones the plan already knew about.

    Its named blind zone (§15.8/Ch. 15 Cor 2): the DECLARED count is the plan author's own dial —
    Dep is stated in one direction, an edge no criterion references is no defect, and nothing
    adjudicates a declared edge — so a plan can raise its own q_Dep by declaring more.
    """
    edges = graph.dep_edges(closed=True)      # a record closed unanswered still counts (§15.5)
    if not edges:
        return None  # empty population → ⊥ (§15.4)
    declared = sum(1 for e in edges if not e.discovered)
    total = len(edges)
    return declared / total


def q_Del(graph: Graph) -> Optional[float]:
    """Delegation quality (canon §15.4/§15.6, v3.8): 1 − (mis-delegations) / (issued contracts).

    High q_Del = right executor chosen first time. Low = capability mismatches. Event-timely: the
    defect counts at its protocol event (re-ASSIGN with a Del change — Inv-1, §15.4 "это событие и
    считает q_Del"), NOT gated on DONE — a reassigned node that never reaches DONE stays counted.
    Population = issued contracts (Del is total from ASSIGN) ⟹ numerator ⊆ denominator.
    The canon counts only re-ASSIGN(capability_mismatch) — instrumented via the §15.4 reason
    typing: a node whose Del changes under a TYPED reason counts only when that reason is
    CAPABILITY_MISMATCH; a node whose Del changed UNTYPED keeps the documented over-approximation
    (every untyped Del change counts, so the metric never silently improves by omitting the reason).
    """
    all_tasks = graph._storage.get_all_tasks()
    if not all_tasks:
        return None  # empty population → ⊥ (§15.4)
    reassigned = sum(1 for t in all_tasks
                     if (t.reassign_capability_mismatch if t.reassign_reason_typed
                         else t.was_reassigned))
    return 1.0 - reassigned / len(all_tasks)
