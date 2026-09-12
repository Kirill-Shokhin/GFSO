"""The pinned decision procedure: its identity, its digest, and what it is to have RUN it.

Why this module exists at all. A criterion is typed as a decidable predicate (§10, A1), but a text
like "for ANY accepted program the output matches gcc" decides nothing on its own — the domain is
infinite. What used to close the gap was the VALIDATOR: it invented a probe set at judging time, a
different one each round, and the engine asked only that every behaviour the validator ITSELF had
named carry a probe (`invariants.underprobed`). So a PASS said "the judge checked what the judge
felt like checking", and the one number the canon makes non-negotiable — when the graph says PASS,
the promise was executed — could not be read off the graph at all. Measured on `c_compiler`
(2026-09-19/20): a root closed PASS by an independent judge, and a 205-probe corpus written from
the same contract found 34 real divergences inside that closed tree.

The procedure is therefore part of the criterion, authored with it and before execution
(pre-registration is Inv-1's, §14.4 — criteria are fixed at ASSIGN and no change is silent), and
the residue is stated rather than closed: behaviour outside P is unchecked — the FM-3 boundary
(Ch. 8), which no structural check guards and this one does not pretend to.
"""
from __future__ import annotations

import hashlib
import re
from typing import Iterable, Mapping, Sequence

from gfso.core.types import Criteria, Probe
from gfso.core.protocol.invariants import emits_a_constant, underprobed


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def probe_id(criterion_name: str, probe: Probe | Mapping) -> str:
    """The stable name of one pinned probe: `<criterion>#<8 hex over the command it pins>`.

    The identity is the COMMAND, not the position: a procedure that gains a probe must not rename
    the ones already there, or a report naming what it ran would stop matching what was pinned the
    round before — and the growth of the regression set is the point (§13.5 / the append rule).
    """
    cmd = _norm(probe.get("command", "") if isinstance(probe, Mapping) else probe.command)
    beh = _norm(probe.get("behaviour", "") if isinstance(probe, Mapping) else probe.behaviour)
    seed = cmd or beh
    return f"{_norm(criterion_name)}#{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:8]}"


def probes_from(criterion: Mapping) -> tuple[Probe, ...]:
    """The pinned procedure as an authoring door hands it over: `{"check": [{behaviour, command,
    expect}]}`. One reader for every door — the decomposer, the agent door and the HTTP door each
    parse a criterion, and a key one of them silently ignores is a contract that arrives without
    its procedure and gates nothing."""
    raw = (criterion or {}).get("check") or ()
    if isinstance(raw, Mapping):
        raw = [raw]
    out = []
    for p in raw:
        if isinstance(p, Probe):
            out.append(p)
        elif isinstance(p, Mapping):
            out.append(Probe(str(p.get("behaviour", "") or ""), str(p.get("command", "") or ""),
                             str(p.get("expect", "") or "")))
    return tuple(out)


def pinned_probes(criteria: Iterable[Criteria]) -> dict[str, list[dict]]:
    """{criterion name: [{id, behaviour, command, expect}]} — the procedure as the contract pins it."""
    out: dict[str, list[dict]] = {}
    for c in criteria or ():
        out[c.name] = [{"id": probe_id(c.name, p), "behaviour": p.behaviour,
                        "command": p.command, "expect": p.expect}
                       for p in (c.check or ())]
    return out


def procedure_digest(criteria: Iterable[Criteria]) -> str:
    """A 16-hex digest over every pinned probe of a contract, criterion by criterion.

    Recorded with a PASS so the verdict names WHAT was run, not only that something was. It is a
    pure function of the spec, so the audit log's stored spec of every ASSIGN reproduces it — no
    second copy of the contract has to be kept in step with the first.
    """
    h = hashlib.sha256()
    for c in sorted(criteria or (), key=lambda x: _norm(x.name)):
        h.update(b"\x00" + _norm(c.name).encode("utf-8"))
        for p in sorted(c.check or (), key=lambda p: (_norm(p.command), _norm(p.behaviour))):
            h.update(b"\x01" + _norm(p.behaviour).encode("utf-8"))
            h.update(b"\x02" + _norm(p.command).encode("utf-8"))
            h.update(b"\x03" + _norm(p.expect).encode("utf-8"))
    return h.hexdigest()[:16]


def claim_digest(spec) -> str:
    """A digest over the WHOLE claim: the criteria, their pinned procedures, the risk register and
    the declared scope.

    `procedure_digest` answers "did the CHECK move"; that is not the same question as "did the
    CLAIM move", and reading the first as the second is a false green. Measured on `c_compiler`
    (2026-09-20/21): the procedures never changed, so the closure read `procedure_moved_since_
    authoring: false` — while the agent grew the accepted-risk register from seven entries to nine
    after the work had started, and six of the divergences an independent corpus later found in
    that closed tree sat behind exactly those entries. Narrowing by exclusion is the cheapest way
    to make a claim true, which is why it is the one that has to be visible.
    """
    h = hashlib.sha256()
    h.update(procedure_digest(spec.criteria or ()).encode("utf-8"))
    for n in sorted(spec.accepted_risks or (), key=lambda r: _norm(r.item)):
        h.update(b"\x10" + _norm(n.item).encode("utf-8"))
    for x in sorted(spec.scope or ()):
        h.update(b"\x11" + _norm(x).encode("utf-8"))
    return h.hexdigest()[:16]


def criteria_without_procedure(criteria: Iterable[Criteria]) -> list[str]:
    """The criteria that pin no runnable probe — i.e. that decide nothing as written (A1).

    A probe with no command pins nothing: the whole defect being repaired here is a procedure
    supplied later out of someone's head, and a behaviour named with no way to observe it is that
    same defect written one line higher.

    A SEAM criterion (`depends_on` — the `dep__<producer>` encoding of a declared Dep) is not in
    this population, and not as a convenience: it is not a claim the consumer decides at all. It
    DECLARES a coupling; what makes the coupling true is the producer's own PASS, and the claim
    that the joined parts constitute the parent is the **integration implication**, which the canon
    attributes to the PARENT and to no child (§5.2; §3.4 "a forgotten glue criterion = FM-1" — at
    the parent's level). Demanding a probe here would put the integration truth-maker on the wrong
    node, and — measured while landing this rule — it made every graph carrying a declared seam
    unexecutable, with no door able to supply what was demanded. A caller who WANTS the seam probed
    from the consumer's side may still pin one (`add_dependency(..., check=[…])`).
    """
    return [c.name for c in (criteria or ())
            if not c.depends_on and not any(_norm(p.command) for p in (c.check or ()))]


def degenerate_procedures(criteria: Iterable[Criteria]) -> dict[str, list[str]]:
    """{criterion: [pinned commands that cannot observe the artefact at all]}.

    A command like `echo ok` satisfies "a criterion carries its check" and decides nothing: it
    cannot come out false, so the criterion it pins forbids nothing (§2.1 — a criterion without a
    non-empty fail-extension is not a criterion). This does NOT refuse: whether a probe is
    SENSITIVE to a real divergence is FM-3, and §13.6 is explicit that no structural check guards
    it — a regex that pretended to would be the false green one level up. What it does is make the
    obvious floor VISIBLE, so a hollow procedure is named on the node and in the closure instead of
    passing as coverage. The list is deliberately short and literal: constant emitters with no
    pipeline behind them.
    """
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        bad = [p.command for p in (c.check or ())
               if _norm(p.command) and emits_a_constant(p.command)]
        if bad:
            out[c.name] = bad
    return out


def unrun_pinned(criteria: Sequence[Criteria],
                 per_criterion: Sequence[Mapping]) -> dict[str, list[str]]:
    """{criterion: [pinned probe ids the report does not account for]} — over PASSED criteria only.

    A criterion the report refutes is not asked to have run the rest of its procedure: a refutation
    is already the verdict, and demanding the full sweep before a FAIL may be spoken would buy
    silence, not coverage. A criterion left `undecidable` is likewise not a claim of execution.
    """
    reported: dict[str, set[str]] = {}
    verdicts: dict[str, str] = {}
    for e in per_criterion or ():
        name = _norm(e.get("criterion"))
        verdicts[name] = str(e.get("verdict", "")).strip().lower()
        raw = e.get("probe")
        probes = ([p for p in raw if isinstance(p, Mapping)] if isinstance(raw, (list, tuple))
                  else [raw] if isinstance(raw, Mapping) else [])
        ran = reported.setdefault(name, set())
        for p in probes:
            if str(p.get("id", "")).strip():
                ran.add(str(p.get("id")).strip())
            # …AND BY THE COMMAND WHEN THE ID IS ABSENT. A report that ran the pinned command and
            # spelled no id has still run it; refusing it would teach the reader to paste ids
            # instead of commands, which is the fabrication this whole module exists against.
            ran.add(probe_id(name, p))
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        name = _norm(c.name)
        if verdicts.get(name) not in ("pass", "passed"):
            continue
        missing = [probe_id(c.name, p) for p in (c.check or ())
                   if _norm(p.command) and probe_id(c.name, p) not in reported.get(name, set())]
        if missing:
            out[c.name] = missing
    return out


def orphaned_regression(criteria: Iterable[Criteria], regression: Mapping) -> dict[str, list[str]]:
    """{criterion name no longer in the contract: [the probes that once refuted it]}.

    The regression set is keyed by criterion NAME, and a plan repair may rename or replace the
    criterion — which is a NORMAL path here, not a corner: a FAIL that indicts the decomposition is
    answered by repairing it. The obligation then evaporates silently: nothing matches the new
    name, nothing is demanded, and the node passes over a repair that was never re-observed.

    It cannot be fixed by demanding the probe against a criterion that no longer exists — the
    contract legitimately moved. So it is SAID instead: an orphaned refutation is residue, named in
    the closure, exactly like the behaviour outside the pinned set. Found by an outside reviewer
    the day this landed; the silent version is the one this whole change exists against.
    """
    have = {_norm(c.name) for c in (criteria or ())}
    return {name: [p.get("id") for p in probes]
            for name, probes in (regression or {}).items() if _norm(name) not in have}


def coverage(criteria: Sequence[Criteria], per_criterion: Sequence[Mapping]) -> dict:
    """What a verdict records about its own reach: the digest, the pinned count, and what was run
    BEYOND the pinned set — the honest half of "checked by P, behaviour outside P unchecked"."""
    pinned = pinned_probes(criteria)
    pinned_ids = {i["id"] for v in pinned.values() for i in v}
    extra = 0
    for e in per_criterion or ():
        name = _norm(e.get("criterion"))
        raw = e.get("probe")
        probes = ([p for p in raw if isinstance(p, Mapping)] if isinstance(raw, (list, tuple))
                  else [raw] if isinstance(raw, Mapping) else [])
        for p in probes:
            pid = str(p.get("id", "")).strip() or probe_id(name, p)
            if pid not in pinned_ids and _norm(p.get("command", "")):
                extra += 1
    # …AND HOW MANY OF THEM THIS REPORT ACTUALLY ACCOUNTED FOR. `pinned_probes` is a property of
    # the CONTRACT; on its own it answers "how much procedure exists", never "how much was run" —
    # and it was being written identically on every door, including the one that records an
    # internal node's self-report, where nothing pinned runs at all (§14.5 D6). A record that says
    # `pinned_probes: 2` over a closure that ran none is the false green this change exists to
    # remove, on the change's own surface. So the count of what RAN is stored beside it, computed
    # from the report, and the two can be compared by anyone reading the record.
    ran = 0
    for c in criteria or ():
        name = _norm(c.name)
        reported = set()
        for e in per_criterion or ():
            if _norm(e.get("criterion")) != name:
                continue
            raw = e.get("probe")
            ps = ([p for p in raw if isinstance(p, Mapping)] if isinstance(raw, (list, tuple))
                  else [raw] if isinstance(raw, Mapping) else [])
            for p in ps:
                if str(p.get("id", "")).strip():
                    reported.add(str(p.get("id")).strip())
                reported.add(probe_id(name, p))
        ran += sum(1 for p in (c.check or ())
                   if _norm(p.command) and probe_id(c.name, p) in reported)
    return {"procedure_digest": procedure_digest(criteria),
            "pinned_probes": sum(len(v) for v in pinned.values()),
            "pinned_probes_run": ran,
            "criteria_with_procedure": sum(1 for v in pinned.values() if v),
            "criteria_total": len(pinned),
            "probes_beyond_the_procedure": extra}


def refuting_probes(per_criterion: Sequence[Mapping]) -> dict[str, list[dict]]:
    """{criterion: [the probes that REFUTED it this round]} — the regression set's new members.

    What contact found is bought with the run (§13.5 verify-vs-explore), and dropping it after
    paying is what makes the next round pay again: the executor fixes what was named, the next
    judge writes its own probes, and the same defect walks back in unobserved.

    It is kept as the NODE's history, deliberately not folded into the criterion. The pinned
    procedure is the ISSUER's pre-registered claim (Inv-1, §14.4) and growing it silently at
    judging time would be the contract moving under the executor — the very thing pre-registration
    forbids; an issuer who wants a finding made permanent promotes it with `edit_criteria`, and
    `claim_drift` then shows the promotion. Only refuting probes enter: a passing exploration tells
    a later round nothing it must re-run.
    """
    out: dict[str, list[dict]] = {}
    for e in per_criterion or ():
        if str(e.get("verdict", "")).strip().lower() not in ("fail", "failed"):
            continue
        name = _norm(e.get("criterion"))
        raw = e.get("probe")
        probes = ([p for p in raw if isinstance(p, Mapping)] if isinstance(raw, (list, tuple))
                  else [raw] if isinstance(raw, Mapping) else [])
        for p in probes:
            if not _norm(p.get("command", "")):
                continue
            out.setdefault(name, []).append(
                {"id": probe_id(name, p), "behaviour": _norm(p.get("behaviour", "")) or "found by contact",
                 "command": _norm(p.get("command", "")), "expect": _norm(p.get("expect", ""))})
    return out


def merge_regression(stored: Mapping, found: Mapping) -> dict[str, list[dict]]:
    """The node's regression set, grown by this round and never shrunk (dedup by probe id)."""
    out = {k: list(v) for k, v in (stored or {}).items()}
    for name, probes in (found or {}).items():
        have = {p.get("id") for p in out.get(name, ())}
        out.setdefault(name, []).extend(p for p in probes if p.get("id") not in have)
    return out


def unrun_regression(regression: Mapping, per_criterion: Sequence[Mapping]) -> dict[str, list[str]]:
    """{criterion: [ids of once-refuting probes this PASS did not re-run]}.

    A criterion that failed here before passes now only if the observation that refuted it was
    made again. Anything else is a pass over an untested repair.
    """
    ran: dict[str, set[str]] = {}
    verdicts: dict[str, str] = {}
    for e in per_criterion or ():
        name = _norm(e.get("criterion"))
        verdicts[name] = str(e.get("verdict", "")).strip().lower()
        raw = e.get("probe")
        probes = ([p for p in raw if isinstance(p, Mapping)] if isinstance(raw, (list, tuple))
                  else [raw] if isinstance(raw, Mapping) else [])
        s = ran.setdefault(name, set())
        for p in probes:
            if str(p.get("id", "")).strip():
                s.add(str(p.get("id")).strip())
            s.add(probe_id(name, p))
    out: dict[str, list[str]] = {}
    for name, probes in (regression or {}).items():
        if verdicts.get(_norm(name)) not in ("pass", "passed"):
            continue
        missing = [p["id"] for p in probes if p.get("id") not in ran.get(_norm(name), set())]
        if missing:
            out[name] = missing
    return out


def unaccounted_for(task, per_criterion: Sequence[Mapping], by_hand: bool, validator_id,
                    regression: Mapping, internal: bool = False) -> dict[str, list[str]]:
    """{criterion: [what this report did not account for]} — ONE owner for that question.

    Three sources, one answer: the behaviours the report itself named and did not probe
    (`underprobed`), the procedure the CONTRACT pinned and the report skipped, and the probes that
    already REFUTED this node once. They are three ways of saying the same thing — a conjunct
    nobody observed cannot carry a pass (§11.2) — and they lived as three appended blocks inside a
    verdict recorder that had grown past the size the suite's FORM ratchet holds at zero. That
    ratchet is not decoration: a rule appended to a long function is a rule nobody finds later.

    The one exemption is the canon's own degenerate case: on an INTERNAL node (its Del is its
    parent's) §14.5 D6 has the executor self-verify, and the guarantee is the validation of the
    public result ABOVE it. There is no seam, so there is no independent party whose procedure this
    would be — and demanding it there froze every internal node in VALIDATING, which is the worse
    defect. The demand stands wherever the verdict is somebody else's: every seam, every instrument.
    """
    gaps = underprobed(per_criterion)
    # The D6 exemption is narrowed to the case that HAS it. §14.5 D6 lets an INTERNAL node
    # self-verify; at a seam independence is owed and a self-judgement is not a verdict at all. The
    # caller guarantees that upstream today, and the repo's own recurring class is a rule that
    # holds at one door and not at the next — so it is checked here, where the rule lives.
    if task is None or (bool(by_hand) and internal and str(validator_id) == str(task.assignee)):
        return gaps
    for name, ids in unrun_pinned(task.spec.criteria, per_criterion).items():
        gaps.setdefault(name, []).append(
            "the procedure this criterion PINS was not run: " + ", ".join(ids)
            + " — the contract fixed these before the work (Inv-1, §14.4); a pass that skips them "
              "is a pass on a procedure invented at judging time")
    # What contact already found here was paid for with a round (§13.5). Re-running it is what makes
    # a repair CHECKED rather than asserted: the loop this closes is the executor fixing what was
    # named while the next judge writes fresh probes and never looks there again.
    for name, ids in unrun_regression(regression, per_criterion).items():
        gaps.setdefault(name, []).append(
            "a probe that REFUTED this criterion in an earlier round was not re-run: "
            + ", ".join(ids)
            + " — a pass over a repair nobody re-observed is not a verdict on the repair")
    return gaps
