"""The Level-2 review record, and the KEY a finding is named by.

The key is the string a caller passes to `dispute_finding`, and it was built in three independent
places that had to agree byte for byte: the execution gate, the verb that accepts a dispute, and
the delta baseline the next review compares against. Three spellings of one name is three chances
for a dispute to be refused as "not an open finding" while the gate holds the node shut on exactly
that finding (register 2026-08-22, finding 4).

The three kinds of finding — a criterion the children do not carry, a conflict between children,
an obligation of the node's own goal that none of its criteria decides — are all named here.
"""
from __future__ import annotations

import hashlib
import json

from gfso.core.graph.projection import probe_view
from gfso.core.types import CriticVerdict, register_of


#: the setting a node's session fit is kept under, its id appended (`Engine.record_session_fit`)
SESSION_FIT = "session_fit:"


def _digest(x) -> str:
    return hashlib.sha256(json.dumps(x, sort_keys=True, default=str).encode()).hexdigest()[:24]


def _criteria(task) -> dict:
    return {c.name: [c.description, sorted(map(probe_view, c.check or ()), key=str)] for c in task.spec.criteria}


def goal_key(task) -> str:
    """What the reading of a node's goal obligations reads — its id, goal text and declared scope exclusions — as one
    digest: the obligations on record are this text's, re-read only when it moves."""
    return _digest([str(task.id), task.spec.description, list(task.spec.scope)])


def side_id(said) -> str:
    """The node a conflict's side names — `root.wc (wc-counts)`: the id before its criterion's gloss."""
    return str(said).split()[0] if str(said).split() else ""


def review_read(graph, task) -> dict:
    """What a node's Level-2 review READS (`Engine.project`), in parts: the node's context — its goal (`goal_key`: id,
    text, scope) and its split's register, which the checker takes as law; its own criteria with their pins and its
    coverage; each active child's goal text, criteria with their pins, the packet's pre-filled ACCEPTED_RISKS (its
    issuer's word, §10.1) and the deferral of its split the parent's plan wrote (§8.6); the Dep edges between those
    children, as the projection tags them. Nothing else moves its verdict — not who executes a child (§10.1), not a
    child's name, scope or own split's register, nothing inside a child's subtree: its split is a re-admission of the
    child (§11.5), not a part of the plan the parent's review read. As JSON reads it back, so a stored part compares
    with a fresh one."""
    kids = sorted(graph.get_active_children(task.id), key=lambda k: str(k.id))
    ids = {str(k.id) for k in kids}
    return json.loads(json.dumps({
        "node": str(task.id),
        "context": {"goal": goal_key(task), "register": [n.to_dict() for n in register_of(task).items]},
        "criteria": _criteria(task),
        "covers": sorted([m.criterion_name, str(m.child_id)] for m in task.criterion_mappings or ()),
        "children": {str(k.id): {"goal": k.spec.description, "criteria": _criteria(k),
                                 "prefill": [n.item for n in k.spec.set_aside],
                                 "deferral": (json.loads(graph.setting(f"{SESSION_FIT}{k.id}") or "null") or {}).get("after")}
                     for k in kids},
        "deps": sorted([str(e.from_id), str(e.to_id), e.glue or "", bool(e.discovered), bool(e.provisional)]
                       for e in graph.dep_edges() if str(e.from_id) in ids and str(e.to_id) in ids)},
        sort_keys=True, default=str))


def read_stamp(graph, task) -> str:
    """`review_read` as one digest: the verdict is current while it stands."""
    return _digest(review_read(graph, task))


def measured(rec: dict) -> bool:
    """Did the round that wrote this review record reach a verdict? One that did not — no checker, an
    unreadable or incomplete plan verdict, a goal that could not be read — is no baseline to count
    progress against: against it an alternating checker reset the unproductive count (critic rounds 9,
    10). The same reading for records older than the flag: a verdict is a `semantic_covered` of True or
    False."""
    return rec.get("measured", rec.get("semantic_covered") is not None)


def progress_baseline(rec: dict) -> "list[str] | None":
    """The findings to count the next review's progress against: this record's, if its round measured;
    else the last measuring round's, carried through (None when there never was one)."""
    return finding_keys(rec) if measured(rec) else rec.get("baseline_findings")


def finding_keys(rec: dict, exclude_disputed: bool = True) -> list[str]:
    """Every finding in a stored review, by the name a dispute must use.

    `exclude_disputed` drops the ones already answered in writing (what the GATE asks); pass False
    for "what did this review say at all" (what a delta baseline asks)."""
    disputed = set((rec.get("disputes") or {}).keys()) if exclude_disputed else set()
    return [k for k, _, _ in _findings(rec) if k not in disputed]


def carried_disputes(before: dict, rec: dict) -> dict:
    """The disputes of the last review that stand over this one: each carried onto a finding of the same kind on the same
    thing (`_findings`) whose question reads what the dispute argued over, unchanged (`_stands`) — one dispute to one
    finding, so a dispute of one conflict between two children answers no second one. A finding that does not recur, or
    one whose read moved, takes its dispute with it. A round that measured nothing names no finding, and carries every
    dispute as it stood. The dispute keeps what it was argued over: a decider added since is no part of its argument."""
    disputes = (before or {}).get("disputes") or {}
    if not measured(rec):
        return dict(disputes)
    old = {k: (what, about) for k, what, about in _findings(before)}
    pool: list = []
    for k, d in disputes.items():
        what, about = (d["what"], d["about"]) if d.get("what") and isinstance(d.get("about"), dict) else old.get(k, (None, None))
        if what is not None and about is not None:
            pool.append((k, d, what, about))
    out, found = {}, _findings(rec)
    # …every finding's own key first, then what is about the same thing: in one greedy pass two conflicts between the
    # same sides traded disputes by the order the checker listed them in (critic over bf9efb4)
    for same_key in (True, False):
        for k, what, about in found:
            if k in out:
                continue
            hit = next((x for x in pool if (x[0] == k or not same_key) and x[2] == what and _stands(x[3], about)), None)
            if hit is not None:
                pool.remove(hit)
                was, d = hit[0], hit[1]
                out[k] = {**d, "what": what, "about": hit[3], **({} if was == k else {"was": was})}
    return out


def finding_about(rec: dict, key: str) -> dict:
    """The finding `key` of a stored review as a dispute records it: {what: its kind and the thing it names, about: what
    its question read} (`carried_disputes`)."""
    return next(({"what": what, "about": about} for k, what, about in _findings(rec) if k == key), {})


def _stands(then, now) -> bool:
    """Does what a dispute was argued over stand in what the finding's question reads now? Unchanged, save its deciders,
    read monotonically: every one it was argued over stands unchanged, and one added since moves nothing."""
    if then is None or now is None:
        return False
    if {k: v for k, v in then.items() if k != "deciders"} != {k: v for k, v in now.items() if k != "deciders"}:
        return False
    return all(now.get("deciders", {}).get(d) == v for d, v in (then.get("deciders") or {}).items())


def _findings(rec: dict) -> list[tuple[str, str, "dict | None"]]:
    """(key, what, about) for every finding of a stored review: its key, its kind and the thing it names (a criterion by
    name, a conflict by its sides' ids, an obligation by its text), and the part of the review's read (`review_read`) its
    question reads — the node's context with each; for a criterion, its text and pins and each child mapped to it, that
    child's criteria and pre-fill; for a conflict, each side's criteria — the node's own where the side is the node; for
    an obligation, the criteria that can decide it, the node's own and its mapped children's. None where the record holds
    no read (written before it was kept)."""
    read = rec.get("read")
    kids = (read or {}).get("children") or {}
    mapped = lambda name: sorted({c for n, c in (read or {}).get("covers") or () if name is None or n == name})
    def about(**parts):
        """The node's context with the parts this finding's question reads; None with no read on record."""
        return None if read is None else {"context": read["context"], **parts}
    def criteria_of(i):
        """The criteria the review read of `i`: the node's own, or its child's."""
        return read["criteria"] if i == read["node"] else (kids.get(i) or {}).get("criteria")
    out = [(str(v.get("criterion")), f"criterion: {v.get('criterion')}",
            about(criterion=(read["criteria"].get(str(v.get("criterion"))) if read else None),
                  children={i: [criteria_of(i), (kids.get(i) or {}).get("prefill")] for i in mapped(str(v.get("criterion")))}
                  if read else None))
           for v in rec.get("criteria_verdicts") or () if v.get("verdict") != CriticVerdict.SUFFICIENT]
    # A KEY NAMES ONE FINDING. Keyed on the participants alone, three separately reasoned conflicts
    # between the same two children were one key — and one four-word dispute closed all three at
    # once, with the record able to show only that a key had been answered (adversary, wave 25,
    # 2026-09-05: open findings went 13 → 10 on a single call). What distinguishes them is the
    # REASON, so the reason distinguishes the key; the first words of it are enough to be readable
    # and are handed back verbatim under `dispute_keys`, so nothing has to be typed from memory.
    _seen: dict = {}
    for c in rec.get("conflicts") or ():
        _base = "conflict: " + ", ".join(c.get("between") or ())
        _n = _seen[_base] = _seen.get(_base, 0) + 1
        _why = " ".join(str(c.get("why") or "").split())[:60]
        sides = sorted({side_id(x) for x in c.get("between") or ()})
        out.append((_base if _n == 1 and not _why else f"{_base} — {_why or _n}", "conflict: " + ", ".join(sides),
                    about(sides={i: criteria_of(i) for i in sides} if read else None)))
    deciders = ({f"{i}/{n}": v for i in [read["node"], *mapped(None)] for n, v in (criteria_of(i) or {}).items()}
                if read else None)
    out += [(f"undecided: {g.get('obligation', '')}", f"undecided: {g.get('obligation', '')}", about(deciders=deciders))
            for g in rec.get("undecided_obligations") or ()]
    return out
