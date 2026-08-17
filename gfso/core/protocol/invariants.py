"""Protocol invariants. Pure validation functions.

NB Invariant 1 (criteria immutability) has NO named function here BY DESIGN: it is enforced
structurally — every in-place criteria change on a SET_STATE raises InvariantViolation at the
mutation chokepoint (core/graph/mutations.py::_set_state), and the only sanctioned change paths
are revision (re-ASSIGN, §14.4 Inv-1) and the pre-acceptance CHALLENGE channel (APPLY_SPEC).
A `validate_criteria_immutable` helper used to live here, defined but never called — dead code
that read as protection; removed (visibility ≠ enforcement)."""
from __future__ import annotations

from typing import Mapping, Sequence

from gfso.core.types import SignalData, Signal


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
    if verdict == "PASS" and red:
        defects.append(f"verdict PASS contradicts the report's own evidence: {', '.join(sorted(red))} "
                       f"did not pass. A criterion is the obligation (§10) — ACCEPTED_RISKS (§13.1) holds "
                       f"risks of the decomposition and never retires one; to change the contract, "
                       f"CHALLENGE it (spec defect) — a verdict cannot excuse it")
    if verdict == "FAIL" and not red:
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
            good = [p for p in probes
                    if str(p.get("command", "")).strip() and str(p.get("expect", "")).strip()]
            behaviours = [b for b in (e.get("behaviours") or []) if str(b).strip()]
            if not good:
                defects.append(
                    f"criterion '{name}' carries no reproducible probe — a verdict states what it "
                    f"OBSERVED, so every criterion needs `probe: [{{command, expect}}]`: the command "
                    f"to re-run against the delivered artifact, and what its output must show. "
                    f"Judgment with no re-runnable observation is not evidence")
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
        good = [p for p in probes
                if str(p.get("command", "")).strip() and str(p.get("expect", "")).strip()]
        behaviours = [str(b).strip() for b in (e.get("behaviours") or []) if str(b).strip()]
        if behaviours and len(good) < len(behaviours):
            out[str(e.get("criterion"))] = behaviours[len(good):]
    return out
