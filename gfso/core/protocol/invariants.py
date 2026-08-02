"""Protocol invariants. Pure validation functions.

NB Invariant 1 (criteria immutability) has NO named function here BY DESIGN: it is enforced
structurally — every in-place criteria change on a SET_STATE raises InvariantViolation at the
mutation chokepoint (core/graph/mutations.py::_set_state), and the only sanctioned change paths
are revision (re-ASSIGN, §6.4 Inv-1) and the pre-acceptance CHALLENGE channel (APPLY_SPEC).
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
                           failed_criteria: Sequence[str]) -> list[str]:
    """Is this validation report a VERDICT at all? (§2.2 V(t) = ⋀ᵢ cᵢ over the node's criteria.)

    A verdict is the conjunction over the WHOLE contract. So a report is not a verdict — it is ⊥,
    an absence of value (§2.2/§3.2: ⊥ is not a third scale value, and it is not pass) — when it:
      - leaves a criterion unspoken (an unevaluated conjunct is ⊥, never pass);
      - speaks of something that is not a criterion of this node (it answers another contract);
      - disagrees with itself: `verdict` PASS while a conjunct is not pass, or `failed_criteria`
        ≠ the non-pass conjuncts (the issuer's FAIL payload must BE the report's own red set).

    Measured live (BCB/93, the false-PASS this rule closes): the validator ran the suite correctly,
    reported `test_values: fail` with real failing evidence, and still returned verdict PASS with
    empty failed_criteria — excusing the red conjunct as "NEGLECTED-declared, out of scope". A
    node's criteria ARE its obligation (§2.2); NEGLECTED holds risk factors of the DECOMPOSITION
    (§5.1) and can never retire a criterion — that path is CHALLENGE (spec defect → the issuer
    resolves) or revision, both logged. Returns the defect lines (empty = a well-formed verdict).
    """
    names = [str(c) for c in criteria]
    known = set(names)
    spoken = {str(e.get("criterion")): str(e.get("verdict", "")).lower() for e in per_criterion}
    defects = []

    for missing in [n for n in names if n not in spoken]:
        defects.append(f"criterion '{missing}' has no verdict — V = AND over ALL criteria (§2.2); "
                       f"an unevaluated criterion is ⊥, not pass")
    for foreign in [n for n in spoken if n not in known]:
        defects.append(f"'{foreign}' is not a criterion of this node — the contract's criteria are "
                       f"the entire obligation ({', '.join(names) or 'none'})")

    red = {n for n, v in spoken.items() if n in known and v != "pass"}
    if verdict == "PASS" and red:
        defects.append(f"verdict PASS contradicts the report's own evidence: {', '.join(sorted(red))} "
                       f"did not pass. A criterion is the obligation (§2.2) — NEGLECTED (§5.1) holds "
                       f"risks of the decomposition and never retires one; to change the contract, "
                       f"CHALLENGE it (spec defect) — a verdict cannot excuse it")
    if verdict == "FAIL" and not red:
        defects.append("verdict FAIL but every criterion passed in the report's own evidence")
    if red != set(failed_criteria) & known or (set(failed_criteria) - known):
        defects.append(f"failed_criteria {sorted(set(failed_criteria))} ≠ the report's own non-pass "
                       f"criteria {sorted(red)} — the issuer's FAIL payload must be the red set (Inv-3)")
    return defects
