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

from gfso.core.types import CriticVerdict


def finding_keys(rec: dict, exclude_disputed: bool = True) -> list[str]:
    """Every finding in a stored review, by the name a dispute must use.

    `exclude_disputed` drops the ones already answered in writing (what the GATE asks); pass False
    for "what did this review say at all" (what a delta baseline asks)."""
    disputed = set((rec.get("disputes") or {}).keys()) if exclude_disputed else set()
    out = [str(v.get("criterion")) for v in rec.get("criteria_verdicts") or ()
           if v.get("verdict") != CriticVerdict.SUFFICIENT]
    out += ["conflict: " + ", ".join(c.get("between") or ()) for c in rec.get("conflicts") or ()]
    out += ["undecided: " + str(g.get("obligation", "")) for g in rec.get("undecided_obligations") or ()]
    return [k for k in out if k not in disputed]
