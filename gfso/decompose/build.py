"""Build a CORE graph from a structured decomposition spec THROUGH the FSM (signals) — the SINGLE build path.

Every node enters the graph via a logged ASSIGN (no `_graph.save_task` bypass); Dep is criteria-content
(§2): a seam = a `depends_on` criterion on the CONSUMER, declared at creation so no post-hoc cascade fires;
the DepEdge is derived (`graph.dep_edges()`).
"""
from __future__ import annotations

import dataclasses
import logging
from typing import Optional

from gfso.engine import AdmissionRefused, Engine
from gfso.config import ROOT_ID
from gfso.core.protocol.procedure import probes_from as _checks_of
from gfso.core.types import (
    Spec, Criteria, AcceptedRiskItem, CriterionMapping, TaskId, AgentId,
    Signal, SignalData, State, Register, register_of,
)

log = logging.getLogger(__name__)


def build_graph_live(d: dict, request: str, engine: Engine, root_id: str = ROOT_ID,
                     assignee: str = "human", max_iterations: int | None = None,
                     child_assignee: str | None = None, contract_fixed: bool = False) -> tuple[Engine, TaskId, list[str]]:
    """Build the decomposition into a LIVE (started) engine THROUGH the FSM — the canon-faithful counterpart
    to the offline `build_graph`. The root enters via a logged ASSIGN (if absent); the children via
    `decompose_task` (one ASSIGN each), with each Dep seam declared as a `depends_on` CRITERION **at
    creation** (§2 Dep=criteria-content) so no post-hoc `add_dependency` fires (which would CANCEL+re-ASSIGN
    the consumer and cascade). Every node thus enters the graph by a signal — no `_graph.save_task` bypass.

    Returns (engine, root_id, dropped): `dropped` lists every spec item that could NOT be placed, with its
    reason — nothing is filtered silently; the caller's repair loop feeds these back to the audit.
    Re-running with a corrected spec is safe: an ASSIGN on an existing live node is a REVISION (same id,
    subtree retained, v3.7 §12.3 Inv-1) — wholesale rebuild = wholesale revise.
    `contract_fixed`: the split's author is not the node's issuer, so the node's contract stands as issued (Inv-1)
    and the split maps onto its criteria — the spec's own root criteria are not applied."""
    rid, A = TaskId(root_id), AgentId(assignee)
    # QUIESCE the dispatcher for the signal burst: the build is not atomic (root ASSIGN → children
    # ASSIGNs land milliseconds apart), and an event-driven dispatcher evaluating the half-built graph
    # races it — observed live: the root spawned as an EXECUTING "leaf" before its children existed,
    # and a consumer spawned before its producer node was created. Dispatch resumes on the settled
    # graph (the counter nests across the repair loop's re-builds; _dispatch_wake pokes the loop).
    engine._dispatch_quiesce = getattr(engine, "_dispatch_quiesce", 0) + 1
    try:
        return _build_graph_live(held_contract(d, engine.graph.get_task(rid)) if contract_fixed else d, request,
                                 engine, rid, A, max_iterations, AgentId(child_assignee) if child_assignee else A,
                                 contract_fixed)
    finally:
        engine._dispatch_quiesce = max(0, getattr(engine, "_dispatch_quiesce", 1) - 1)
        if not engine._dispatch_quiesce:
            getattr(engine, "_dispatch_wake", lambda: None)()


def _children_from_spec(engine, d: dict, ns, existing_kids: set, C, max_iterations):
    """Read the spec's subtasks into (id, spec, actor) triples — and name what was dropped.

    Building the graph is two jobs: deciding WHAT the children are — ids namespaced under
    the root, deps collected per consumer, every unusable item recorded rather than filtered
    in silence — and LANDING them through the FSM. They lived in one body of eighty
    statements, so a reader after either walked both. Returns
    (children, mappings, deps_by_consumer, dropped)."""
    ids = {str(c["id"]) for c in d.get("subtasks", [])}
    dropped: list[str] = []  # NOTHING is filtered silently — every dropped item is surfaced (returned + logged)
    deps_by_consumer: dict = {}
    for dep in d.get("deps", []):
        f, t = str(dep.get("from", "")), str(dep.get("to", ""))
        if f == t:
            dropped.append(f"dep {f}->{t}: self-dependency (audit defect)")
            continue
        if f not in ids or t not in ids:
            dropped.append(f"dep {f}->{t}: endpoint not a subtask id")
            continue
        seen = deps_by_consumer.setdefault(t, [])
        if not any(ef == f for ef, _ in seen):               # dedup a repeated (producer→consumer) seam
            seen.append((f, dep.get("glue", "")))

    children = []
    for c in d.get("subtasks", []):
        cid = str(c["id"])
        crit = [Criteria(x["name"], x.get("description", ""), check=_checks_of(x))
                for x in c.get("criteria", [])]
        crit += [Criteria(name=f"dep__{f}", description=glue, depends_on=TaskId(ns(f)))
                 for f, glue in deps_by_consumer.get(cid, [])]
        # ONE CRITERION PER NAME. A refine re-derives the set, and a name that appears twice — the
        # decomposer restating a criterion, or a `dep__x` seam described differently on two passes —
        # produced a contract carrying both, with contradictory text under one label. Measured on the
        # human door 2026-08-22: `dep__D1_scaffold` twice, one naming a package that had been renamed
        # away and one naming the real one. It is not only confusing: `record_verdict` takes its
        # evidence as a mapping keyed BY CRITERION NAME, so two criteria of one name cannot be
        # validated separately at all — one silently overwrites the other. The last statement wins,
        # which on a re-derivation is the current one.
        _by_name = {}
        for x in crit:
            _by_name[x.name] = x
        crit = list(_by_name.values())
        # a rebuild-as-revision must not stomp what belongs to OTHER authors (Inv-1): the child's Del
        # is the issuer's separate act (a Del change = the q_Del event), and the child's OWN
        # ACCEPTED_RISKS/scope/risk registers belong to the CHILD'S decomposer (§9.2: ACCEPTED_RISKS is authored
        # per-decomposition — «родитель НЕ авторствует ACCEPTED_RISKS детей») — preserve both; `A` and empty
        # registers apply only to NEW children. The subtree itself is retained by revision semantics.
        existing_child = engine.graph.get_task(TaskId(ns(cid)))
        child_actor = AgentId(existing_child.assignee) if existing_child and existing_child.assignee else C
        child_neg = existing_child.spec.accepted_risks if existing_child else ()
        child_scope = existing_child.spec.scope if existing_child else ()
        child_risk = existing_child.spec.risk_components if existing_child else ()
        # …and WHICH OF THE PARENT'S RISK COMPONENTS this child is the mitigation for (CHECK-5):
        # the decomposer authors it on a new child, and a refine carries what stands rather than
        # emptying the record the check reads.
        child_covers = tuple(c.get("covers_risks") or ()) or (
            existing_child.spec.covers_risks if existing_child else ())
        children.append((TaskId(ns(cid)), Spec(c.get("description", ""), tuple(crit),
                                               accepted_risks=child_neg, risk_components=child_risk,
                                               scope=child_scope, name=c.get("name", ""),
                                               covers_risks=child_covers), child_actor))

    valid = {c["name"] for c in d.get("root_criteria", [])}
    mappings = []
    for m in d.get("mappings", []):
        if m.get("criterion") not in valid:
            dropped.append(f"mapping '{m.get('criterion')}'->{m.get('child_id')}: no such root criterion "
                           f"(audit name drift — coverage will show as a CHECK-1 hole)")
        elif str(m.get("child_id")) not in ids:
            dropped.append(f"mapping '{m.get('criterion')}'->{m.get('child_id')}: no such subtask id")
        else:
            mappings.append(CriterionMapping(m["criterion"], TaskId(ns(str(m["child_id"])))))

    return children, mappings, deps_by_consumer, dropped


def _admit(engine, rid, changed, mappings, max_iterations, register, drops, dropped: list, contract=None) -> bool:
    """The admission (§11.5), one act: the root's contract where this round re-authors it, the children it issues, its
    register, its drops. Does the split stand? What refused it, or what it dropped, goes into `dropped` in the spec's
    ids — the repair loop's problems; refused, nothing of it was written, the contract included (critic r8)."""
    try:
        engine.decompose_task(rid, changed, mappings or None, max_iterations, register=register, drops=drops,
                              contract=contract)
        engine.wait_idle()
    except AdmissionRefused as no:
        dropped += [f"the admission refused the split — {h.replace(f'{rid}.', '')}" for h in no.holes]
        return False
    dropped += [f"child {c}: dropped by the re-decomposition — cancelled, with its subtree" for c in drops]
    return True


def _this_round(engine, rid, changed, mappings, max_iterations, authored: tuple, drops, dropped: list,
                contract) -> bool:
    """ONE ACT: the children, the root's contract and the register this round changes are one re-admission of the
    split (§11.5) — revised first and admitted after, a refused admission left the contract re-authored over the old
    split (critic r8). A root with no split has nothing to admit: its contract is a plain revision. Does it stand?"""
    register = _root_register(engine, rid, authored)
    node = engine.graph.get_task(rid)
    moved = register is not None and register.items != register_of(node).items
    # …AND ITS COVERAGE: the criteria a child covers are the split's (§2.4), so a round that only remaps changes the
    # split and is its re-admission — it was dropped in silence, no child having changed (critic r17)
    remapped = set(mappings or ()) != set(node.criterion_mappings)
    if changed or drops or (engine.graph.get_active_children(rid) and (contract is not None or moved or remapped)):
        return _admit(engine, rid, changed, mappings, max_iterations, register, drops, dropped, contract)
    if contract is not None:
        engine.revise(rid, contract, engine.graph.issuer_of(rid)); engine.wait_idle()
    return True


def _the_children_this_split_drops(engine, rid, children) -> tuple:
    """A re-decomposition that drops an ISSUED child cancels it (§11.5).

    The split is the parent's claim about what constitutes it, and a child the new split does not
    contain is no longer part of that claim — but its contract does not lapse because the plan moved
    (§12.13: every live child keeps its owner). Left alone it went on working, unmapped, for a goal
    nobody was aggregating it into: ballast if the new split is right, and paid for either way. So
    the drop travels with the re-admission, which reads the split without it and then sends the
    issuer's own CANCEL, with its cascade and its CONFIRM_CANCEL in-flight report. A TERMINAL child is
    not dropped at all — it stays in the split with its settled verdict (Inv-7), and
    `_children_that_changed` already leaves it frozen."""
    keep = {str(cid) for cid, _, _ in children}
    # …one already being cancelled included: "one already being cancelled [leaves] as the abandoned node it becomes"
    # (§11.5) — left out, it stood in the battery as an orphan only its executor's CONFIRM_CANCEL lifted (critic r7)
    return tuple(c.id for c in engine.graph.get_active_children(TaskId(rid))
                 if str(c.id) not in keep and c.state not in (State.DONE, State.ABANDONED))


def _children_that_changed(engine, rid, children, mappings, dropped: list) -> list:
    """The children whose contract actually differs — and which are FROZEN.

    A child already built with the same spec needs no re-ASSIGN — the criteria it covers are the split's (§2.4) and
    ride the admission's mappings — and a terminal one admits none at all: the FSM would reject it, so the
    unapplied change is surfaced as a problem rather than lost into a refused signal.
    """
    changed = []
    # …and only a child still IN the split stands unchanged: one that left it (dropped, settled out) is named to the act
    # so the act refuses it as such, not as a mapping onto a missing child (critic r7 P5)
    active = {str(k.id) for k in engine.graph.get_active_children(rid)}
    for cid_t, spec_c, actor in children:
        ex = engine.graph.get_task(cid_t)
        if ex is not None and ex.spec == spec_c and str(ex.id) in active:
            continue
        # COMPLETED work is FROZEN: a terminal node admits no revision (§12.3 — the FSM would reject
        # the re-ASSIGN anyway; observed live: a refine fold updated DONE children and its intent
        # vanished into rejected signals). Surface the unapplied change as a problem instead — the
        # repair loop (or the honest holes residue) routes the new obligation to a NEW subtask.
        # ESCALATED is not here: the node is waiting for its issuer, not finished, and a revision is
        # precisely what it admits (§12.5) — so the change applies rather than being dropped.
        if ex is not None and ex.state in (State.DONE, State.ABANDONED):
            dropped.append(f"child {cid_t}: {ex.state.name} is settled — finished work is frozen, "
                           f"the intended contract change was NOT applied; route new "
                           f"obligations to a NEW subtask (or leave the child as built)")
            continue
        changed.append((cid_t, spec_c, actor))
    return changed


def _fits_whole(d: dict) -> bool:
    """The decomposer judged the node AND every piece of it to fit one session of the named executor."""
    return bool(d.get("whole_fits_one_session")) and all(bool(c.get("fits_one_session"))
                                                         for c in d.get("subtasks", []))


def _whose_the_children_are(engine, d: dict, rid: TaskId, parent_del, C):
    """The executor of the NEW children. A split whose whole the decomposer judged to fit one session of the
    executor is that executor's own internal work (§10.3, below κ): its children keep the parent's Del, so no
    seam — no validation, no wait — stands on each piece. Only where the system holds the parent: a mode's
    boundary between the user's agent and the system stays a seam by what the user chose. Otherwise, under a
    mode, the mode's executor for that depth (a refine round used to hand new children the parent's own Del,
    internal by accident); with no mode, the caller's choice as before."""
    held = engine.held_by_the_user_agent(engine.depth_of(rid))
    if held is None:
        return C
    if not held and _fits_whole(d):
        return AgentId(parent_del)
    if str(C) != str(parent_del):
        return C
    return engine.del_at(engine.depth_of(rid) + 1, AgentId(parent_del)) or C


def _record_the_session_fit(engine, d: dict, rid: TaskId, ns) -> None:
    """Keep the decomposer's count and judgement beside the contract, node by node (`record_session_fit`)."""
    if "whole_fits_one_session" in d:
        engine.record_session_fit(rid, str(d.get("whole_volume", "")), bool(d.get("whole_fits_one_session")))
    for c in d.get("subtasks", []):
        if "fits_one_session" in c:
            engine.record_session_fit(TaskId(ns(str(c["id"]))), str(c.get("volume", "")),
                                      bool(c.get("fits_one_session")))


def held_contract(d: dict, node) -> dict:
    """The spec with the node's contract as ISSUED in place of the one it authored: a split's author who is not the
    node's issuer maps onto the criteria he was given and re-authors none (Inv-1, §10.1) — so the build revises
    nothing on the node, and a mapping onto a name the contract lacks is a CHECK-1 hole the repair loop sees."""
    if node is None:
        return d
    # …ALL of them, its Dep seams included: CHECK-1 reads every criterion of the node (§9.5), so a seam left out of
    # the names a mapping may target was a hole no repair round could close (critic r5)
    return {**d, "root_criteria": [{"name": c.name, "description": c.description} for c in node.spec.criteria]}


def refined_root_spec(existing: Spec, request: str, criteria: tuple, accepted_risks: tuple,
                     scope: tuple, derived_name: str) -> Spec:
    """The contract a REFINE round writes over an already-decomposed root — one named place.

    The decomposer OWNS the root's criteria: it re-authors them to the derived V-set so the child
    `covers` mappings resolve against real criteria. Everything the decomposer does NOT author is
    carried across, and the list of those is the reason this is a function rather than a literal
    inside the round: it was a hand-built `Spec(...)` in the middle of a 90-line routine, and it
    silently dropped `risk_components` — the fourth POSITIONAL field, never passed, defaulted to
    `()` on every refine.

    The data loss was the smaller half. CHECK-5 (STD-3, §9.4 — a risk node per grouped component)
    quantifies over exactly that tuple, so emptying it does not make the check FAIL, it makes it
    VACUOUS. Probed end to end 2026-09-07: a root with two components reads `CHECK-5 … no children
    to cover 2 risk components` (RED), and one refine later reads `no risk components defined`
    (GREEN) — nothing covered, no child added. A rule true at zero X, and a step that makes the zero.
    """
    return dataclasses.replace(existing, description=existing.description or request, criteria=criteria,
                               accepted_risks=accepted_risks, scope=scope, name=existing.name or derived_name)


def _register_of(d: dict) -> tuple:
    """The split's register as the spec writes it: its risk events, and ONE denial (§9.5) — the schema's top-level
    `denial`, else one written inside the list; a fold round adding the key beside a listed one left two, and CHECK-4
    read "has one" (critic r4)."""
    # The schema is a CALIBRATED artifact: a model answers in the vocabulary it was asked in, and a key the parser
    # does not read returns an EMPTY register silently — a CHECK-4 hole the plan never had. Which is why this key and
    # the one in the prompt schema move together.
    listed = tuple(AcceptedRiskItem.of(n) for n in d.get("accepted_risks", []))
    denials = ((AcceptedRiskItem.denial_of(d["denial"].get("p"), d["denial"].get("justification", "")),)
               if isinstance(d.get("denial"), dict) else ()) + tuple(n for n in listed if n.denial)
    return tuple(n for n in listed if not n.denial) + denials[:1]


def _root_register(engine: Engine, rid: TaskId, register: tuple) -> Optional[Register]:
    """The register this round admits with the root's split: the one it authored, the components standing kept — or
    the one standing, where it authored none."""
    standing = register_of(engine.graph.get_task(rid))
    return Register(tuple(register), standing.components) if register else (standing if standing.items else None)


def _build_graph_live(d: dict, request: str, engine: Engine, rid: TaskId,
                      A: AgentId, max_iterations: int | None = None,
                      C: AgentId | None = None, contract_fixed: bool = False) -> tuple[Engine, TaskId, list[str]]:
    root_id = str(rid)
    # Whose the ROOT is and whose the WORK is are two questions. `A` answers the first (the root's
    # Del, and so the ISSUER of every child, §10.1); `C` answers the second. They coincide unless a
    # caller asked to delegate the children — which is what a caller passing an executor's id almost
    # always meant, and getting the first when they wanted the second locked one out of their own
    # plan for fifteen minutes (measured 2026-08-21).
    C = C or A
    root_crit = tuple(Criteria(c["name"], c.get("description", ""), check=_checks_of(c))
                      for c in d.get("root_criteria", []))
    scp = tuple(f"{s['item']} — {s['why_out']}" if s.get("why_out") else s["item"]
                for s in d.get("scope", []))  # §9.2 scope-boundary exclusions — objectified on the root
    existing = engine.graph.get_task(rid)
    # The ROOT's two acts belong to two parties: re-authoring its contract is its ISSUER's (the goal's
    # issuer, `Graph.issuer_of` — the root's own Del only at a self-assigned root), and ACCEPT is its
    # EXECUTOR's consent. Using A for either would be a foreign actor re-authoring or accepting someone
    # else's root (correctly rejected by the issuer/executor guards).
    root_actor = A if existing is None else AgentId(existing.assignee)
    contract = None   # the root's contract as this round re-authors it — written with the split, never before it
    if existing is None:
        engine.assign_task(rid, Spec(request, root_crit, (), scope=scp, name=d.get("name", "")), A,
                           max_iterations=max_iterations); engine.wait_idle()
    elif not contract_fixed:   # …and only where the split's author is its issuer (`held_contract`)
        # The decomposer OWNS the root's CRITERIA: it re-authors them to the derived V-set, so the child
        # `covers` mappings resolve against real criteria. An issuer's hand-written root criteria are
        # pseudo-criteria (untrusted) — keeping them would strand coverage (CHECK-1 fail). But the human's
        # NAME and DESCRIPTION are their framing of the goal — PRESERVE them (only fall back to the derived
        # text if absent). Re-author is safe: revise retains the subtree (no cascade). IDEMPOTENT: an
        # unchanged contract emits no signal (a refine that didn't touch the root leaves it in place).
        new_spec = refined_root_spec(existing.spec, request, root_crit, existing.spec.accepted_risks, scp,
                                     d.get("name", ""))
        # …BUT AN AUTHORING THAT CAME BACK WITH NO CRITERIA IS NOT A CONTRACT. A model that answered
        # `{}` re-authored a live root to `criteria: []` (seen 2026-09-24 on a stubbed model) — and V
        # over no criteria is vacuously true, so the goal's contract became one nothing can fail. The
        # round authored nothing; the contract that stands is kept.
        if not root_crit and existing.spec.criteria:
            new_spec = existing.spec
        contract = new_spec if new_spec != existing.spec else None
    # Child ids are NAMESPACED under the root: spec ids are LLM-chosen domain words (proration_engine, ...)
    # in a flat global TaskId namespace — two decompositions of similar domains WILL collide, and a colliding
    # ASSIGN is a same-id REVISION of the OTHER tree's node (observed live: cross-tree corruption). Namespacing
    # makes collisions impossible by construction; a repair re-build of the SAME root maps to the same ids =
    # the intended wholesale revision.
    existing_kids = {str(c.id) for c in engine.graph.get_active_children(rid)}

    def ns(cid: str) -> str:
        """Namespace a spec id into the live graph's id space (`<root>.<id>`), so two decompositions
    of different roots cannot collide on `a`."""
        if cid in existing_kids:   # a HAND-built child carries a bare id — a rebuild must be a REVISION
            return cid             # of that node, never a namespaced duplicate (observed live: refine over
                                   # a manual graph doubled the subtree, C1..C9 + root.C1..C9)
        return cid if cid.startswith(f"{root_id}.") else f"{root_id}.{cid}"

    C = _whose_the_children_are(engine, d, rid, root_actor, C)
    children, mappings, deps_by_consumer, dropped = _children_from_spec(
        engine, d, ns, existing_kids, C, max_iterations)
    # IDEMPOTENT REBUILD: an untouched child costs ZERO signals — its live state (EXECUTING, a
    # delivered result, its own registers) survives a parent-level refine; only a child whose contract
    # actually changed is re-ASSIGNed (→ OFFERED: the executor re-consents, Inv-1); coverage is the split's.
    changed = _children_that_changed(engine, rid, children, mappings, dropped)
    drops = _the_children_this_split_drops(engine, rid, children)
    if not _this_round(engine, rid, changed, mappings, max_iterations, _register_of(d), drops, dropped, contract):
        return engine, rid, dropped   # nothing of this split stands: no contract, no register, no consent
    _record_the_session_fit(engine, d, rid, ns)
    for item in dropped:
        log.warning(f"build_graph_live dropped: {item}")
    # a decomposed root is being worked on → ACCEPT it so it is EXECUTING (with children), not OFFERED: a
    # parent that still shows 'accept' interleaved with its children confuses the executor's next_step order.
    # …BUT ONLY WHERE THE CALLER IS THE ONE CONSENTING. At a self-assigned root the builder is its
    # executor; where the goal was handed to a system executor, consent is THAT executor's (Inv-1: a
    # version binds its executor only by his ACCEPT), and its own consent round gives it.
    # AFTER the split, not before: the consent is to the goal AS SPLIT, and the engine's rules on it (a
    # held node in SEMI is not taken without a split) see the split that exists — accepted first, a build
    # that proposed no children left a childless root in work, past the rule (critic round 7).
    if engine.graph.get_state(rid) == State.OFFERED and str(engine.graph.issuer_of(rid)) == str(root_actor):
        engine.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=rid, source=root_actor)); engine.wait_idle()
    return engine, rid, dropped
