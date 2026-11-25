"""A rule with an owner keeps no copy elsewhere: the executor compare, the undecided line, a typed seam finding's identity."""
from __future__ import annotations

import copy
import pickle
import re
from pathlib import Path

from gfso.decompose.seams import RUNS, SeamFinding

GFSO = Path(__file__).resolve().parents[1] / "gfso"


def _hits(pattern: str) -> list[str]:
    rx = re.compile(pattern)
    return [f"{p.relative_to(GFSO)}:{i}" for p in GFSO.rglob("*.py")
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if rx.search(line)]


def test_whether_a_party_is_the_nodes_executor_is_asked_of_its_owner_alone():
    # …a check's author compared by hand with the node's assignee, in either spelling (other compares of assignees — one
    # Del over a scope, a split's author — are other rules)
    hits = _hits(r"validator.*==\s*str\(\s*\w+\.assignee")
    assert not hits, hits


def test_an_undecided_line_is_worded_by_its_owner_alone():
    hits = [h for h in _hits(r"\[undecided[\] ]") if "review.py" not in h]
    assert not hits, hits


def test_a_seam_finding_keeps_its_kind_and_part_through_a_copy():
    f = SeamFinding("the lexer's probes run the parser", RUNS, "lexer")
    for g in (copy.copy(f), copy.deepcopy(f), pickle.loads(pickle.dumps(f))):
        assert (str(g), g.kind, g.part) == (str(f), RUNS, "lexer")
