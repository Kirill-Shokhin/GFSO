"""A split's admission (§11.5) — the decomposer's act on his own node, outside the twelve signals and logged.

Over the graph and its store alone, so a host embedding the core with no `Engine` performs the same act the engine
does: the split AS IT WILL STAND is built once (`will_stand` → `Split`), the Syntactic battery reads it before anything
is written (`refuse_unless_syntactic`), and the writes apply it — the children's ASSIGNs (the protocol's own signals)
in `Split.issue` order, the node's mappings set to `Split.node`'s, the split's register (`admit_register`).
"""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from typing import Optional

from gfso.core.graph import Graph
from gfso.core.graph.model import admission_key, dep_scope, drops_key, non_leaf_ids, register_log_key
from gfso.core.graph.mutations import InvariantViolation, Schedule, producers_of, with_its_seams
from gfso.core.protocol.procedure import admission_defects
from gfso.core.handlers.structural import run_structural
from gfso.core.types import (TERMINAL_STATES, AgentId, CriterionMapping, Register, Signal, SignalData, State,
                             Task, TaskId)

from .loop import refresh_checks
from .validation import AdmissionRefused, hole_kind, issuing_condition, no_live_deadline


@dataclasses.dataclass(frozen=True)
class Split:
    """The split AS IT WILL STAND once this admission's writes apply — the one object the battery reads and the writes
    apply. Checked over one description and written from others, the act was refused after it had written (a mapping
    counted and never stored, a contract revised before a refused admission, a re-issued child's old Dep edge read as
    standing — critic r8)."""
    node: Task          # its contract, its mappings onto the children below, its register
    children: tuple     # the active children, each with the contract this act gives it
    edges: tuple        # the Dep pairs of the node's scope, a re-issued child's declared ones from its new criteria
    deadlines: dict     # the standing deadlines CHECK-3 reads
    issue: tuple        # the ids this act ASSIGNs, producers before their consumers
    drops: tuple        # the children it leaves out


def will_stand(graph: Graph, parent, children: list[tuple], covers: dict, register: Optional[Register] = None,
               replace: bool = False, drops: tuple = (), contract=None) -> Split:
    """The split this admission leaves: its active children without the `drops`, the named `children`
    (`(id, spec, assignee, …)`) re-issued or created, the node under its new `contract` where one is given, mapped by
    `covers` (child → criteria) — onto the standing pairs, or replacing them — only onto its criteria and its active
    children, and carrying `register` where one is given."""
    out = {str(d) for d in drops}
    mine = {str(k.id): k for k in graph.get_active_children(parent.id) if str(k.id) not in out}
    for cid, spec, assignee, *_ in children:
        was = mine.get(str(cid))
        mine[str(cid)] = (dataclasses.replace(was, spec=spec, assignee=assignee) if was is not None else
                          Task(id=TaskId(str(cid)), spec=spec, assignee=assignee, parent_id=parent.id))
    spec = contract if contract is not None else parent.spec
    names = {c.name for c in spec.criteria}
    # a standing pair goes with its criterion or its child, as a re-authoring prunes it; a pair this act declares
    # stands as declared, so the battery names the one onto no criterion or no child (CHECK-1's invalid mapping)
    kept = () if replace else tuple(m for m in parent.criterion_mappings
                                    if m.criterion_name in names and str(m.child_id) in mine)
    added = tuple(CriterionMapping(c, TaskId(str(cid))) for cid, cs in covers.items() for c in cs)
    pairs = {(m.criterion_name, str(m.child_id)): m for m in kept + added}
    node = dataclasses.replace(parent, spec=spec, criterion_mappings=tuple(pairs.values()),
                               register=register if register is not None else parent.register)
    named = {str(c[0]) for c in children}
    scoped, deadlines = dep_scope(graph, parent.id)
    edges = ({(str(e.from_id), str(e.to_id)) for e in scoped
              if str(e.to_id) not in out and (e.discovered or str(e.to_id) not in named)}
             | {(p, cid) for cid in named for p in producers_of(mine[cid].spec)})
    return Split(node, tuple(mine.values()), tuple(sorted(edges)), deadlines,
                 _producers_first([str(c[0]) for c in children], edges), tuple(drops))


def _producers_first(ids: list, edges) -> tuple:
    """The issue order: a child after every producer this act re-issues with it. Issued one ASSIGN at a time in the
    caller's order, a consumer's new edge met its producer's OLD one and the signal gate refused a phantom cycle
    mid-issue (critic r8). Producers first, every edge a new contract meets runs into a node already re-issued or one
    this act does not touch, so it is an edge of the split as it will stand, which the battery found acyclic."""
    left, done = list(ids), []
    while left:
        ready = [i for i in left if not {a for a, b in edges if b == i and a in left}] or left[:1]
        done += ready
        left = [i for i in left if i not in ready]
    return tuple(done)


def refuse_unless_syntactic(graph: Graph, parent, children: list[tuple], covers: dict,
                            register: Optional[Register] = None, replace: bool = False, drops: tuple = (),
                            contract=None, check: bool = True) -> Split:
    """§11.5: "a split is admitted to execution only if it passes [the Syntactic level], save what no act of its
    decomposer lifts, which is reported rather than gated". The battery runs over the split as it WILL stand
    (`will_stand`) before anything of the act is written, and the act then writes THAT split (`Split`). It sat on each
    child's ACCEPT instead, a refusal its executor could not lift under any delegation (§12.16 (ii); sync audit,
    corner 9). What breaks a split admitted clean — a revision of the contract, a child cancelled — is a flag on the
    decomposer's plan (§12.10), never a hold on work already issued. `check=False`: the object without the battery
    (an engine whose signal validation is off gates no plan)."""
    split = will_stand(graph, parent, children, covers, register, replace, drops, contract)
    kids = list(split.children)
    holes = () if not check else tuple(
        f"{c.check_name}: {c.details}"
        for c in run_structural(split.node, kids, list(split.edges), non_leaf_ids(graph, kids), split.deadlines)
        if not c.passed and not c.skipped and hole_kind(c.check_name) == "gate")
    if holes:
        raise AdmissionRefused(f"the split of {parent.id} as it would stand fails the Syntactic level, and a split "
                               f"is admitted to execution only if it passes (§11.5): " + "; ".join(holes)
                               + " — admit it whole in one `decompose`: every criterion covered (`covers`), the "
                               "split's register (`accepted_risks`), a child the split no longer has dropped (`drops`); "
                               "a standing child named unchanged keeps its contract and its work",
                               holes)
    return split


def named_unchanged(graph: Graph, parent, child: tuple) -> bool:
    """Does this act name a standing child of `parent` with its contract as it stands — its packet (§10.1), executor
    and deadline (when one is named)? Such a child is part of the split as it will stand and is not re-issued: a
    re-admission changes the split, a revision changes a child's contract (§11.5, §12.10), and re-ASSIGNing it re-offered
    work in progress, dropped its delivery and reopened a passed child (critic r14). The criteria it covers are no part
    of it: "a split maps each child to the criteria of t it is responsible for" (§2.4) — a remap is the split's
    (critic r15)."""
    cid, spec, assignee, *rest = child
    t = graph.get_task(TaskId(str(cid)))
    return (t is not None and str(t.parent_id) == str(parent.id) and t.spec == spec
            and str(t.assignee) == str(assignee) and (not rest or rest[0] is None or rest[0] == t.deadline))


def refuse_what_the_act_cannot_take(graph: Graph, parent, children: list[tuple], reopen_refusal, drops: tuple = (),
                                    register: Optional[Register] = None) -> None:
    """Everything the admission names, classified BEFORE the first write (§11.5: whole or nothing). The node: an
    admission is its decomposer's while it is live and not closing (§12.7). A named child: an active one is re-issued,
    an unknown id created; one that has LEFT the split — dropped, being cancelled, or a terminal R′ will not reopen
    (`reopen_refusal`, §12.14) — or that is ANOTHER node's child (D is a forest, §15.3: ASSIGN on its id would re-author
    that other split) cannot be taken by this act. A drop: only an active child not yet terminal (§11.5). A register:
    only where a split will stand (§9.2, a leaf's is vacuous). Read one at a time inside the act, each of these was
    refused after the act had written (critic r7, r9)."""
    holes = []
    if parent.state in (State.IDLE, State.CANCELLING) or parent.state in TERMINAL_STATES:
        holes.append(f"{parent.id} is {parent.state.name}: a split is admitted while its node is issued, live and not "
                     f"closing (§12.7)")
    active = {str(k.id) for k in graph.get_active_children(parent.id)}
    for cid, *_ in children:
        t = graph.get_task(TaskId(str(cid)))
        if t is None:
            continue
        mine = str(t.parent_id) == str(parent.id)
        # out of the active set and not settled = dropped by an earlier re-admission, or being cancelled (§12.6)
        # …a passed child named as it stands stays where it stands: only a CHANGED one is a reopen (§12.14)
        why = (None if t.state == State.DONE and named_unchanged(graph, parent, (cid, *_)) else
               reopen_refusal(t.id) if t.state in TERMINAL_STATES else
               f"{cid} was dropped by an earlier re-admission or is being cancelled"
               if str(t.id) not in active or t.state == State.CANCELLING else None)
        if not mine:
            holes.append(f"{cid} is {t.parent_id or 'a root'}'s, not {parent.id}'s — a node has one parent (§15.3); "
                         f"a child of this split takes an id of its own")
        elif why:
            holes.append(f"{why} — it has left this split; a child that replaces it takes a new id")
    named = {str(c[0]) for c in children}
    for d in drops:
        t = graph.get_task(TaskId(str(d)))
        if t is None or str(d) not in active or t.state in TERMINAL_STATES:
            holes.append(f"{d} is not an active, unsettled child of {parent.id}: a re-admission drops only those (§11.5)")
        elif str(d) in named:
            holes.append(f"{d} is both named and dropped by this act — the split as it will stand either has it or not")
    if register is not None and not (active - {str(d) for d in drops}) | named:
        holes.append(f"no split of {parent.id} will stand, and a leaf's register is vacuous (§9.2) — the register is "
                     f"admitted with the split it qualifies")
    if holes:
        raise AdmissionRefused(f"the admission of {parent.id}'s split cannot take what it names (§11.5): "
                               + "; ".join(holes), tuple(holes))


def refuse_a_d_cycle(graph: Graph, task_id, parent_id) -> None:
    """D is a DAG (§15.3: "a cycle → infinite recursion → an A1 violation"). CHECK-2 sees one
    split at a time; the ancestor chain is only visible here, so the edge that would CLOSE a
    cycle is refused at the door rather than reported after the fact — a self-parented node was
    accepted through `create_task` and then owned itself, which no later check can undo (its own
    children query returns itself, and the AND gate would wait on it forever)."""
    if not parent_id:
        return
    if str(parent_id) == str(task_id):
        raise ValueError(f"{task_id} cannot be its own parent — D must be a DAG (§15.3)")
    seen, cur = {str(task_id)}, graph.get_task(parent_id)
    while cur is not None:
        if str(cur.id) in seen:
            raise ValueError(
                f"parent {parent_id} is a descendant of {task_id} — this edge would close a "
                f"cycle in the decomposition graph, and D must be a DAG (§15.3)")
        seen.add(str(cur.id))
        cur = graph.get_task(cur.parent_id) if cur.parent_id else None


def refuse_a_contract_that_pins_nothing(graph: Graph, task_id, spec) -> None:
    """A packet is admitted only if every criterion carries the procedure that decides it (A1).

    The requirement is the product's operationalization of A1 (§2 types a criterion as a
    DECIDABLE predicate, and an intention is not one) under Inv-1's pre-registration: written
    before the work it is a claim, written after it a description of whatever got built. It sits
    on the ISSUER's own act because of §12.16's conformance clause — a refusal must be liftable by
    the refused party's own moves, and the executor cannot author the contract he is offered.
    Until v4.1 it refused his ACCEPT instead, which is the same demand addressed to the one
    party who cannot meet it."""
    # …ON A CONTRACT BEING INSTALLED. A re-ASSIGN that keeps the criteria re-presents the contract in force
    # (§12.10), which was admitted on its own terms; refusing it under a probe rule added since leaves its issuer
    # only a rewrite of the probes — a move the machine issuer re-presenting a delivery does not make, so the
    # node waited in VALIDATING for a move nobody would make (§12.16 (ii)).
    standing = graph.get_task(task_id)
    if spec is None or (standing is not None and standing.spec.criteria == spec.criteria):
        return
    if defects := admission_defects(spec.criteria):
        raise ValueError(f"{task_id} cannot be assigned: " + "; ".join(defects))


def deadlines_the_act_sets(graph: Graph, parent, children: list[tuple]) -> dict:
    """§11.5: the admission gates the deadlines IT sets — a child's not inside a live parent's (item (6)), and a Dep
    crossing CHECK-3 reads where some choice of them orders every edge; the decomposer lifts both by his own choice.
    Where no choice orders them all — an end fixed, or the parent's deadline in the way — nothing is refused: the
    crossings stand as CHECK-3's flag for the issuers whose deadlines bound the choice. Returns the defaults
    `Schedule` chose for the children typing none (§2.5) — the deadlines this admission sets beside the typed ones."""
    now = datetime.now()
    # THE ACT: every child this admission gives a version — a re-issued one too, standing on its own deadline, typed
    # as it was or, where supplied, re-chosen if it no longer fits (critic r2 over F3: left out, a re-issued child's
    # new Dep was invisible to the writer)
    act, typed = {}, {}
    for cid, spec, _a, *rest in children:
        cid, t, given = str(cid), graph.get_task(cid), (rest[0] if rest else None)
        stands = t.deadline if t is not None and t.deadline is not None and t.deadline > now and not given else None
        act[cid] = (given or (stands if stands and not t.deadline_supplied else None), producers_of(spec),
                    stands if stands and t.deadline_supplied else None)
        if given:
            typed[cid] = given
    if spent := [cid for cid, dl in typed.items() if dl <= now]:
        # the whole admission, before any child is issued — refused one ASSIGN at a time, the split stood half-made
        raise ValueError(f"{', '.join(spent)}: a deadline already passed — a task is given out with a live deadline, "
                         f"one still ahead (§2.5)")
    if parent.deadline is not None and parent.deadline > now:
        for cid, dl in typed.items():
            if dl >= parent.deadline:
                raise ValueError(f"{cid}'s deadline {dl:%Y-%m-%d %H:%M} is not inside its parent {parent.id}'s "
                                 f"({parent.deadline:%Y-%m-%d %H:%M}) — a child that may finish when its parent is "
                                 f"due cannot compose into it (§11.5, item (6)); give one before it")
    defaults = Schedule(graph, parent, act).defaults()
    # A CHILD ITS ASSIGN WILL CARRY NO DEADLINE FOR asks the packet gate's own question here, new or re-issued: a
    # re-issued one whose deadline has lapsed under a parent leaving no default was refused mid-act (critic r10)
    for c in (c for c, (d, _r, _k) in act.items() if d is None and not defaults.get(c)):
        t = graph.get_task(c)
        if why := no_live_deadline(graph, t, None if t is not None else parent.id):
            raise ValueError(f"{c} types no deadline: {why}")
    sets = {**{c: d for c, (d, _r, _k) in act.items() if d}, **{c: d for c, d in defaults.items() if d}}
    # the choice is of "the deadlines the admission sets, its unissued children's" (§11.5): an issued child's stands
    # fixed — its re-issue is a revision, whose crossing is a flag (§12.10), at this door as at `add_dependency`
    issued = {c for c in act if graph.get_task(c) is not None}
    free = Schedule(graph, parent, {c: ((sets.get(c) if c in issued else None), r, None)
                                          for c, (_d, r, _k) in act.items()})
    dl = lambda tid: sets.get(tid) or free.standing(tid)
    # gated "where some such choice orders every edge" (§11.5): the system, the deadlines it sets freed, not each
    # edge — bounded by the parent only while its deadline is ahead; the defaults are ordered wherever an order
    # with a margin of lead exists, so the decomposer types the rest
    crossed = [(p, c) for c in sets for p in act[c][1] if (pd := dl(p)) and pd >= sets[c]]
    if crossed and free.orderable():
        p, c = crossed[0]
        raise ValueError(f"{c} depends on {p}, whose deadline {dl(p):%Y-%m-%d %H:%M} is not before {c}'s "
                         f"{sets[c]:%Y-%m-%d %H:%M} — a consumer cannot be due before its producer (CHECK-3, §11.5); "
                         f"order the deadlines this split sets")
    return {c: d for c, d in defaults.items() if d and d != act[c][2]}   # a re-issued child that still fits rides as is


def admit(graph: Graph, storage, log_at, parent_id, children: list[tuple], covers: Optional[dict] = None, *,
          replace: bool = False, register: Optional[Register] = None, drops: tuple = (), contract=None,
          max_iterations: Optional[int] = None, send, revise=None, reopen_refusal=None,
          check: bool = True) -> Split:
    """A split's admission (§11.5) — ONE act for every door: the engine's `decompose_task`, a child created into a
    split, and a host embedding the core with no `Engine`. Whole or nothing: everything the act names is classified
    and every refusal read BEFORE the first write, over the split as it will stand (`Split`); then the writes apply
    that split — the node's contract (`revise`, the issuer's act, its Dep seams carried), the children's ASSIGNs
    (`send`, the protocol's own signals) producers first, the node's coverage, the drops, the register. Assembled
    once per door, the act was refused after it had written five rounds in a row (critics r5–r10).

    `children`: (id, spec, assignee[, deadline]) — created, or re-issued under its id. `covers`: child → criteria;
    `replace` = those are the node's WHOLE coverage, else they add to the standing pairs. `log_at()`: the log's
    length now, where the act's records stand in it."""
    parent = graph.get_task(TaskId(str(parent_id)))
    if parent is None:
        raise ValueError(f"parent {parent_id} not found")
    covers = {str(k): tuple(v) for k, v in (covers or {}).items()}
    contract = with_its_seams(parent.spec, contract)          # the contract the revision will write, seams carried
    if contract is not None and contract != parent.spec and revise is None:
        raise ValueError(f"{parent.id}'s contract changes with its split, and only its issuer revises it (§10.1)")
    before = (set(parent.criterion_mappings), parent.register, parent.spec)
    defaults = _refuse_before_writing(graph, parent, children, reopen_refusal, drops, register)
    split = refuse_unless_syntactic(graph, parent, children, covers, register, replace, drops, contract, check)
    if contract is not None and contract != parent.spec:
        revise(contract)                                    # the act's first write: refused, nothing stands
    record_admission(storage, log_at(), parent.id, split)
    issued = {str(c[0]): c for c in children if not named_unchanged(graph, parent, c)}
    _issue(graph, send, parent, issued, split.issue, covers, defaults, max_iterations)
    node = graph.get_task(parent.id)
    if set(node.criterion_mappings) != set(split.node.criterion_mappings):
        # a pair onto a child this act does not issue — standing unchanged, or settled — is the split's too (§2.4)
        node.criterion_mappings = tuple(split.node.criterion_mappings)
        graph.save_task(node)
    record_drops(storage, log_at(), parent.id, drops)
    for d in (d for d in drops if graph.get_state(TaskId(str(d))) != State.CANCELLING):
        send(SignalData(signal=Signal.CANCEL, task_id=TaskId(str(d)), source=parent.assignee,
                        reason=f"the re-decomposition of '{parent.id}' no longer contains this child (§11.5)"))
    if register is not None:     # the split's register rides its admission (§9.2), and the battery has read it
        admit_register(graph, storage, log_at(), parent.id, register, AgentId(parent.assignee), validate=False)
    node = graph.get_task(parent.id)
    # …a re-admission that changes nothing — no child issued or dropped, the node's contract, coverage and register as
    # they were — leaves the plan the review read, and its verdict, standing (critic r15)
    refresh_checks(graph, parent.id, stale_review=bool(issued or drops)
                   or before != (set(node.criterion_mappings), node.register, node.spec))
    return split


def _refuse_before_writing(graph: Graph, parent, children: list[tuple], reopen_refusal, drops: tuple,
                           register) -> dict:
    """Every refusal the act holds, read before it writes anything; returns the deadlines it sets (§2.5). A standing
    child named unchanged is not issued, so what is read of a child being given out — its pinned procedure, its
    deadline still ahead — is not read of it (critic r15: a passed child named with its spent deadline refused the act)."""
    refuse_what_the_act_cannot_take(graph, parent, children, reopen_refusal or _settled, drops, register)
    children = [c for c in children if not named_unchanged(graph, parent, c)]
    for cid, spec, *_ in children:
        refuse_a_d_cycle(graph, cid, parent.id)
        if why := issuing_condition(parent, cid):
            raise ValueError(why)
        refuse_a_contract_that_pins_nothing(graph, cid, spec)
    refuse_a_dep_cycle(graph, children, drops)
    return deadlines_the_act_sets(graph, parent, children)


def refuse_a_dep_cycle(graph: Graph, children: list[tuple], drops: tuple = ()) -> None:
    """CHECK-2's Dep clause over the WHOLE graph as the act will leave it (§9.5: "CHECK-2 holds of the whole graph"):
    every adopted edge, a named child's declared ones taken from its new criteria, a dropped child's gone. Read inside
    the parent's subtree alone, a re-issued child closing a cycle through another branch passed the battery and was
    refused at its ASSIGN mid-act (critic r11); read before the battery as a plain error, a ring among the authored
    children ended the authoring instead of reaching its repair loop."""
    named = {str(c[0]): producers_of(c[1]) for c in children}
    out = {str(d) for d in drops}
    below: dict = {}
    for a, b in ({(str(e.from_id), str(e.to_id)) for e in graph.dep_edges(adopted=True)
                  if str(e.to_id) not in out and (e.discovered or str(e.to_id) not in named)}
                 | {(p, cid) for cid, ps in named.items() for p in ps}):
        below.setdefault(a, set()).add(b)

    def returns(x) -> bool:
        """Does following the edges out of x come back to x?"""
        seen, todo = set(), list(below.get(x, ()))
        while todo:
            y = todo.pop()
            if y == x:
                return True
            if y not in seen:
                seen.add(y)
                todo += below.get(y, ())
        return False
    if cyc := sorted(x for x in named if returns(x)):
        raise AdmissionRefused(f"{', '.join(cyc)} would close a Dep cycle (CHECK-2, §9.5): a consumer waits for its "
                               f"producer, so one edge on the ring is backwards", tuple(f"CHECK-2: {x} would close a Dep cycle — one edge on the ring is backwards" for x in cyc))


def _settled(task_id) -> str:
    return f"{task_id} is settled"


def _issue(graph: Graph, send, parent, by_id: dict, order: tuple, covers: dict, defaults: dict,
           max_iterations) -> None:
    """The admitted split's ASSIGNs, producers first (`Split.issue`), of the children `by_id` holds — a standing child
    named unchanged is not among them. Every refusal the gate holds was read before the act; one met here anyway is a
    defect of that reading, said aloud rather than left as a silent half-split."""
    for cid in (c for c in order if c in by_id):
        child_id, spec, assignee, *rest = by_id[cid]
        deadline = rest[0] if rest else None
        # …the child's own rework bound where the act names one (a merged child keeps its members'), else the act's
        bound = (rest[1] if len(rest) > 1 else None) or max_iterations
        supplied = deadline is None and defaults.get(cid) is not None
        entry = send(SignalData(
            signal=Signal.ASSIGN, task_id=TaskId(str(child_id)), spec=spec, source=parent.assignee,
            assignee=assignee, parent_id=parent.id, deadline=defaults[cid] if supplied else deadline,
            deadline_supplied=supplied, covers=tuple(covers.get(cid, ())),
            # the rework bound is a term of the CONTRACT (§12.3), chosen by whoever issues the node
            **({"max_iterations": bound} if bound else {})))
        if entry is not None and entry.rejected:
            raise InvariantViolation(f"the admission of {parent.id}'s split passed its gate and its ASSIGN of {cid} "
                                     f"was refused — a refusal the admission did not read: {entry.error}")


def record_admission(storage, log_at: int, parent_id: TaskId, split: Split) -> None:
    """The admission is a logged act of its own (§11.5); a child enters a split only by one (`child_not_admitted`)."""
    key = admission_key(parent_id)
    log_ = json.loads(storage.get_critique(key) or "[]")
    log_.append({"log_at": log_at, "children": [str(k.id) for k in split.children], "issued": list(split.issue),
                 "drops": [str(d) for d in split.drops],
                 "mappings": [[m.criterion_name, str(m.child_id)] for m in split.node.criterion_mappings]})
    storage.store_critique(key, json.dumps(log_))


def record_drops(storage, log_at: int, parent_id: TaskId, drops: tuple) -> None:
    """The children this re-admission leaves out, recorded with the act (§11.5) — out of the plan from here (§12.6);
    their CANCELs follow, each settling at its own pace."""
    if drops:
        log_ = json.loads(storage.get_critique(drops_key(parent_id)) or "[]")
        log_ += [{"child": str(d), "log_at": log_at} for d in drops]
        storage.store_critique(drops_key(parent_id), json.dumps(log_))


def admit_register(graph: Graph, storage, log_at: int, task_id: TaskId, register: Register, agent: AgentId,
                   validate: bool = True) -> Task:
    """The split's register admitted with it (§11.5) — by Del(t), while the node is issued, live and not closing
    (§12.7), no revision and no re-offer: the register is the split's attribute, not a packet field (§9.2). A new
    version is a re-admission — "the split … and its register — changes only by a re-admission, the battery running
    over the split as it will then stand" — so the battery reads it first (`validate`), a refusal its decomposer lifts
    himself. Each version is recorded with its author, time and place in the signal log (Thm 11)."""
    t = graph.get_task(task_id)
    if t is None:
        raise ValueError(f"task {task_id} not found")
    if str(agent) != str(t.assignee):
        raise ValueError(f"the register of {task_id}'s split is its decomposer's — {t.assignee}, its Del — to "
                         f"write, not {agent}'s (§9.2); its issuer's word on risks is the packet's pre-filled "
                         f"ACCEPTED_RISKS, a revision (§10.1)")
    if t.state in (State.IDLE, State.CANCELLING) or t.state in TERMINAL_STATES:
        raise ValueError(f"{task_id} is {t.state.name}: a split is admitted on a node issued, live and not closing "
                         f"(§11.5, §12.7)")
    if not graph.get_active_children(task_id):
        raise ValueError(f"{task_id} has no split: a leaf's register is vacuous (§9.2) — the register is admitted "
                         f"with the split it qualifies (`decompose(…, accepted_risks=…)`); the executor's word on a "
                         f"leaf's risks is no register, and its issuer's is the packet's pre-fill")
    if validate:
        refuse_unless_syntactic(graph, t, [], {}, register)
    t.register = Register(tuple(register.items), tuple(register.components))
    graph.save_task(t)
    key = register_log_key(task_id)
    log_ = json.loads(storage.get_critique(key) or "[]")
    log_.append({"at": datetime.now().isoformat(timespec="seconds"), "by": str(agent), "log_at": log_at,
                 "items": [n.to_dict() for n in t.register.items], "components": list(t.register.components)})
    storage.store_critique(key, json.dumps(log_))
    return t
