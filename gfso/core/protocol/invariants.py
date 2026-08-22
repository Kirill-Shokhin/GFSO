"""Protocol invariants. Pure validation functions.

NB Invariant 1 (criteria immutability) has NO named function here BY DESIGN: it is enforced
structurally — every in-place criteria change on a SET_STATE raises InvariantViolation at the
mutation chokepoint (core/graph/mutations.py::_set_state), and the only sanctioned change paths
are revision (re-ASSIGN, §14.4 Inv-1) and the pre-acceptance CHALLENGE channel (APPLY_SPEC).
A `validate_criteria_immutable` helper used to live here, defined but never called — dead code
that read as protection; removed (visibility ≠ enforcement)."""
from __future__ import annotations

import re

from typing import Mapping, Sequence

from gfso.core.types import SignalData, Signal, Verdict


def validate_fail_has_criteria(signal_data: SignalData) -> bool:
    """Invariant 3: FAIL must specify failed criteria."""
    if signal_data.signal != Signal.FAIL:
        return True
    return len(signal_data.failed_criteria) > 0


def verdict_report_defects(criteria: Sequence[str], verdict: str,
                           per_criterion: Sequence[Mapping],
                           failed_criteria: Sequence[str],
                           require_probe: bool = False) -> list[str]:
    """Is this validation report a VERDICT at all? (§10 V(t) = ⋀ᵢ cᵢ over the node's criteria.)

    A verdict is the conjunction over the WHOLE contract. So a report is not a verdict — it is ⊥,
    an absence of value (§10/§11.2: ⊥ is not a third scale value, and it is not pass) — when it:
      - leaves a criterion unspoken (an unevaluated conjunct is ⊥, never pass);
      - speaks of something that is not a criterion of this node (it answers another contract);
      - disagrees with itself: `verdict` PASS while a conjunct is not pass, or `failed_criteria`
        ≠ the non-pass conjuncts (the issuer's FAIL payload must BE the report's own red set).

    Measured live (BCB/93, the false-PASS this rule closes): the validator ran the suite correctly,
    reported `test_values: fail` with real failing evidence, and still returned verdict PASS with
    empty failed_criteria — excusing the red conjunct as "ACCEPTED_RISKS-declared, out of scope". A
    node's criteria ARE its obligation (§10); ACCEPTED_RISKS holds risk factors of the DECOMPOSITION
    (§13.1) and can never retire a criterion — that path is CHALLENGE (spec defect → the issuer
    resolves) or revision, both logged. Returns the defect lines (empty = a well-formed verdict).

    `require_probe` adds the EVIDENCE-INSTRUMENT clause — off for a human reviewer, on for the LLM
    validator: every criterion's entry must carry a PROBE, a command to run plus the observation
    expected of it, so the claim can be RE-RUN against the judged artifact instead of believed.
    Measured live (`EVIDENCE_LOG` §13.5): replaying the checkable claims of one run against the
    exact snapshot they judged, **four of seven described behaviour the artifact did not have**
    ("returns two blocks", "the helpers are absent", an IndexError that does not occur). The
    validator's own contract already says executed evidence outranks judgment; nothing checked that
    an execution happened. This is A1's decidability clause one level down: a criterion whose check
    cannot be re-run mechanically is not decided by this report.
    """
    names = [str(c) for c in criteria]
    known = set(names)
    spoken = {str(e.get("criterion")): str(e.get("verdict", "")).lower() for e in per_criterion}
    defects = []

    for missing in [n for n in names if n not in spoken]:
        defects.append(f"criterion '{missing}' has no verdict — V = AND over ALL criteria (§10); "
                       f"an unevaluated criterion is ⊥, not pass")
    for foreign in [n for n in spoken if n not in known]:
        defects.append(f"'{foreign}' is not a criterion of this node — the contract's criteria are "
                       f"the entire obligation ({', '.join(names) or 'none'})")

    red = {n for n, v in spoken.items() if n in known and v != "pass"}
    if verdict == Verdict.PASS and red:
        defects.append(f"verdict PASS contradicts the report's own evidence: {', '.join(sorted(red))} "
                       f"did not pass. A criterion is the obligation (§10) — ACCEPTED_RISKS (§13.1) holds "
                       f"risks of the decomposition and never retires one; to change the contract, "
                       f"CHALLENGE it (spec defect) — a verdict cannot excuse it")
    if verdict == Verdict.FAIL and not red:
        defects.append("verdict FAIL but every criterion passed in the report's own evidence")
    if red != set(failed_criteria) & known or (set(failed_criteria) - known):
        defects.append(f"failed_criteria {sorted(set(failed_criteria))} ≠ the report's own non-pass "
                       f"criteria {sorted(red)} — the issuer's FAIL payload must be the red set (Inv-3)")

    if require_probe:
        for e in per_criterion:
            name = str(e.get("criterion"))
            if name not in known:
                continue                       # already reported as foreign, above
            # A criterion is routinely a CONJUNCTION, and one probe over one conjunct passes it
            # while another conjunct is broken. Measured: a root closed DONE with a criterion
            # naming three behaviours (N/P/D loops · hold-space accumulation · multi-line address
            # ranges) and one honest, reproducing probe over the first — the second failed against
            # the reference implementation. Reproducibility is not coverage, so the report must
            # enumerate what the criterion demands and carry a probe for each.
            raw = e.get("probe")
            probes = ([p for p in raw if isinstance(p, Mapping)] if isinstance(raw, (list, tuple))
                      else [raw] if isinstance(raw, Mapping) else [])
            # A REFUTATION'S EXPECTED OUTPUT CAN BE NOTHING. `expect` is what makes a probe
            # re-runnable, and for a criterion the report FAILED the observation is often an
            # absence — "`grep -r flush tests/` prints nothing" — which has no expected line to
            # quote. Measured on the human door 2026-08-21: a garbage delivery was caught exactly
            # right and its FAIL was refused at the report level over empty `expect` fields, so bad
            # work went back looking accepted. A command with a stated verdict of `fail` and
            # evidence behind it is a probe; it is only a PASS that needs the expectation spelled.
            _refuting = e.get("verdict") == "fail" and str(e.get("evidence", "")).strip()
            good = [p for p in probes
                    if str(p.get("command", "")).strip()
                    and (str(p.get("expect", "")).strip() or _refuting)]
            behaviours = [b for b in (e.get("behaviours") or []) if str(b).strip()]
            if not good:
                defects.append(
                    f"criterion '{name}' carries no reproducible probe — a verdict states what it "
                    f"OBSERVED, so every criterion needs `probe: [{{command, expect}}]`: the command "
                    f"to re-run against the delivered artifact, and what its output must show. "
                    f"Judgment with no re-runnable observation is not evidence. When the behaviour "
                    f"IS an absence — nothing printed, no file written, no second line — make the "
                    f"absence PRINT: pipe through `wc -l` and expect `0`, `echo \"EXIT=$?\"`, or "
                    f"`test ! -e x && echo ABSENT`. An empty `expect` is not an observation of "
                    f"silence, it is the absence of an observation, and nothing can tell the two "
                    f"apart afterwards")
            elif not behaviours:
                defects.append(
                    f"criterion '{name}' names no behaviours — list what it DEMANDS, one entry per "
                    f"conjunct, so a probe can be shown for each. A criterion asserted whole and "
                    f"tested in part is the false-PASS this field exists to close")
    return defects


def underprobed(per_criterion: Sequence[Mapping]) -> dict[str, list[str]]:
    """Criteria whose named behaviours outnumber their probes → {criterion: untested behaviours}.

    NOT a malformed report: the verdict is well-formed, its EVIDENCE is short of what the criterion
    demands. So this is not ⊥ at the report level (that would stall the node and end the run over an
    incomplete proof), it is ⊥ at the CRITERION level — an unobserved conjunct is not decided, so it
    cannot be `pass` (§11.2: ⊥ is not pass), and the node goes back for rework naming exactly what
    was never observed. Measured: a criterion naming three behaviours passed on one honest probe of
    the first, and the delivery closed as done with the second broken.
    """
    out: dict[str, list[str]] = {}
    for e in per_criterion or ():
        raw = e.get("probe")
        probes = ([p for p in raw if isinstance(p, Mapping)] if isinstance(raw, (list, tuple))
                  else [raw] if isinstance(raw, Mapping) else [])
        _refuting = e.get("verdict") == "fail" and str(e.get("evidence", "")).strip()
        good = [p for p in probes
                if str(p.get("command", "")).strip()
                and (str(p.get("expect", "")).strip() or _refuting)]   # an absence has no `expect`
        behaviours = [str(b).strip() for b in (e.get("behaviours") or []) if str(b).strip()]
        if not behaviours:
            continue
        # WHICH behaviours a probe observes, when the report says so. Counting was a proxy for
        # coverage and it is wrong in both directions: one command can honestly observe two
        # behaviours (a single test asserting both), and two commands can observe the same one
        # twice. Measured live on this repository's own graph: five criteria whose evidence was
        # complete — a named test per behaviour, run and passing — were demoted because the
        # validator had enumerated more behaviours than commands. A demotion that fires on complete
        # evidence teaches its reader to route around it, which is how a guard becomes decoration.
        claimed = {str(p.get("behaviour", "")).strip().lower()
                   for p in good if str(p.get("behaviour", "")).strip()}
        if claimed:
            # Matched by containment either way, because both strings are the validator's own prose
            # and it paraphrases its own list — "it changes no state" against "lapse handling mutates
            # no node state". Requiring them identical made the LINK depend on wording, so complete
            # evidence was demoted over a rewritten label. What must exist is the link; recognising
            # it is the engine's business, not the writer's.
            # …and containment ALONE is still too literal, because one command legitimately observes
            # several behaviours and gets ONE fused label for all of them. Measured 2026-08-20 on a
            # live run: behaviours ["pytest exits 0", "at least 1 test collected and run"] against
            # the label "pytest exits 0 with >=1 test collected and run" — the same command, really
            # observing both. Containment caught the first and missed the second ("at least 1" vs
            # ">=1"), so a complete report was refused, the validation was re-run, and a second
            # refusal parked the node. Four of ten validator runs in that hour were spent on this,
            # and the barrier was the writer's phrasing, never the coverage.
            # So the fallback is overlap of CONTENT words: a behaviour counts as observed when most
            # of what it says appears in a label. This must not become "no matching at all" — an
            # unrelated label still leaves the behaviour unobserved, which is the case the rule
            # exists for — hence a high bar and a floor under how much must overlap.
            _NOISE = {"the", "a", "an", "is", "are", "it", "its", "and", "or", "of", "to", "in",
                      "on", "with", "that", "this", "no", "not", "at", "least", "than", "be"}

            def _words(s: str) -> set:
                return {w for w in re.findall(r"[a-z0-9_]+", s.lower()) if w not in _NOISE}

            def _covered(b: str) -> bool:
                bl = b.strip().lower()
                if any(bl in c or c in bl for c in claimed):
                    return True
                bw = _words(bl)
                if len(bw) < 2:              # too little content to judge overlap on
                    return False
                return any(len(bw & _words(c)) / len(bw) >= 0.6 for c in claimed)

            if missing := [b for b in behaviours if not _covered(b)]:
                out[str(e.get("criterion"))] = missing
            continue
        # No labels: cardinality stays the only mechanical proxy available, and the strict reading
        # is the safe one — the case it was built for is a criterion of three behaviours probed once.
        if len(good) < len(behaviours):
            out[str(e.get("criterion"))] = behaviours[len(good):]
    return out
