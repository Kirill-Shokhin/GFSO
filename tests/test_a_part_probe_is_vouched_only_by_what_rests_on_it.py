"""A passed criterion vouches, without `held`, only for the part probes it rests on (critic, 2026-10-11).

Under the whole's own criterion X the validator explored with the part probe's very command and saw it fail; X passed on
its own grounds, and the part probe — owed by A and B, cited by neither — was credited as holding through X.
"""
from __future__ import annotations

from gfso.core.protocol.procedure import part_credit, part_criteria, parts_not_shown_holding, probe_id, unrun_parts
from gfso.core.types import Criteria, Probe

_P = part_criteria("root.cat", [Criteria("flags", check=(Probe("cat flags", "make test", "all 12 pass"),))])
_PARTS = {"A": _P, "B": _P}
_IDS = [probe_id(c.name, p) for c in _P for p in c.check]
_OWN = [Criteria("A", "a"), Criteria("B", "b"), Criteria("X", "docs", check=())]


def _report(cited_under: str, verdict_b: str = "pass") -> list[dict]:
    seen = {"criterion": cited_under, "verdict": "pass",
            "probe": [{"command": "make test", "expect": "README builds", "observed": "3 failed"}]}
    return [seen] + [{"criterion": c, "verdict": v, "evidence": "e", "probe": []}
                     for c, v in (("A", "pass"), ("B", verdict_b)) if c != cited_under]


def test_an_unrelated_passed_criterion_does_not_vouch_for_a_part_probe():
    assert unrun_parts(_PARTS, _report("X"), own=_OWN) == {"A": _IDS, "B": _IDS}
    _, why = part_credit(_PARTS, _report("X"), own=_OWN)
    assert any("does not rest on it" in w for ws in why.values() for w in ws)
    assert parts_not_shown_holding(_PARTS, _report("X", verdict_b="fail"), own=_OWN), \
        "a FAIL on B must still read the part as not shown holding — not as a refuted split"


def test_control_the_criterion_that_rests_on_it_still_vouches():
    assert "A" not in unrun_parts(_PARTS, _report("A"), own=_OWN)

