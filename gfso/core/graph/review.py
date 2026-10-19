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
    out = [str(v.get("criterion")) for v in rec.get("criteria_verdicts") or ()
           if v.get("verdict") != CriticVerdict.SUFFICIENT]
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
        out.append(_base if _n == 1 and not _why else f"{_base} — {_why or _n}")
    out += ["undecided: " + str(g.get("obligation", "")) for g in rec.get("undecided_obligations") or ()]
    return [k for k in out if k not in disputed]
