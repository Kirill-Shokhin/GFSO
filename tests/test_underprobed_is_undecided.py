"""A criterion whose named behaviours were not all probed is UNDECIDED — never passed.

Measured: a root closed DONE on a criterion naming three behaviours (N/P/D loops · hold-space
accumulation · multi-line address ranges) with one HONEST probe of the first — it re-ran and
reproduced exactly what it claimed. The second behaviour was broken and the artifact failed the
classic hold-space idiom outright. Reproducibility is not coverage.

The first version of this rule REFUSED such a report outright, and the next run died 37 minutes in:
the node stalled on ⊥ and the run ended over an incomplete proof. Demotion is the honest reading —
the report IS a verdict, the unobserved conjunct simply is not decided (§11.2: ⊥ is not pass).
"""
from gfso.core.protocol.invariants import underprobed


def test_untested_behaviours_are_named():
    gaps = underprobed([{"criterion": "c", "behaviours": ["parses", "round-trips", "rejects junk"],
                         "probe": [{"command": "pytest -q", "expect": "passed"}]}])
    assert gaps == {"c": ["round-trips", "rejects junk"]}


def test_a_fully_probed_conjunction_is_not_flagged():
    assert underprobed([{"criterion": "c", "behaviours": ["a", "b"],
                         "probe": [{"command": "x", "expect": "1"},
                                   {"command": "y", "expect": "2"}]}]) == {}


def test_a_probe_without_an_expectation_does_not_count_as_one():
    """Otherwise the rule is satisfied by padding the list with empty entries."""
    assert underprobed([{"criterion": "c", "behaviours": ["a", "b"],
                         "probe": [{"command": "x", "expect": "1"}, {"command": "y"}]}]) == {"c": ["b"]}
