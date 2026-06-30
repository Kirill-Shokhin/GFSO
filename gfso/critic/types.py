"""Typed results of the L2 critic — no strings-as-transport (structured everywhere).

A `Hole` is one analyst finding; a `Verdict` is the judge's ruling on it; a
`NodeCritique` is the whole per-node result (gate outcome + holes + verdicts).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hole:
    """One analyst finding (SEARCH stage). Plain-language, with a concrete reason."""
    where: str
    what: str
    why: str


_NO_LAW = ("", "none", "n/a", "—", "-")


@dataclass(frozen=True)
class Verdict:
    """The judge's adjudication of one analyst hole. The judge names the violated method
    law (or `none`); `ruling` is DERIVED from that — the LLM cannot rubber-stamp a verdict,
    it must name a real law to confirm."""
    finding: str                # which analyst hole (its `what`, abbreviated)
    law_violated: str           # method law/article + FM tag, or "none" if not a defect
    element: str = ""           # D | Dep | V | N   (when a law is violated)
    reason: str = ""

    @property
    def ruling(self) -> str:
        return "DISMISSED" if self.law_violated.strip().lower() in _NO_LAW else "CONFIRMED"


@dataclass(frozen=True)
class NodeCritique:
    """Per-node L2 result. gate_passed=False ⇒ L2 not run (leaf or L0/L1 failed)."""
    node_id: str
    gate_passed: bool
    l0l1_failures: tuple[str, ...] = ()   # check names that gated L2 out
    holes: tuple[Hole, ...] = ()
    verdicts: tuple[Verdict, ...] = ()

    @property
    def confirmed(self) -> tuple[Verdict, ...]:
        return tuple(v for v in self.verdicts if v.ruling == "CONFIRMED")
