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


def test_a_probe_that_names_its_behaviour_covers_it():
    """Coverage, not cardinality, when the report says which behaviour a command observed.

    One command often observes two behaviours — a single test asserting both — and counting demanded
    a second command that would observe nothing new. Measured live: five criteria whose evidence was
    complete, a named passing test per behaviour, were demoted because the validator had enumerated
    more behaviours than commands. A demotion firing on complete evidence teaches its reader to
    route around it.
    """
    gaps = underprobed([{"criterion": "c",
                         "behaviours": ["it stops dispatch", "it changes no state"],
                         "probe": [{"command": "pytest -q t.py::test_both", "expect": "1 passed",
                                    "behaviour": "it stops dispatch"},
                                   {"command": "pytest -q t.py::test_both", "expect": "1 passed",
                                    "behaviour": "it changes no state"}]}])
    assert gaps == {}


def test_a_behaviour_no_probe_names_is_still_unobserved():
    """The rule that caught the real false close survives: naming some behaviours does not excuse
    the rest, and the untouched one is reported by name."""
    gaps = underprobed([{"criterion": "c",
                         "behaviours": ["it stops dispatch", "it changes no state"],
                         "probe": [{"command": "pytest -q", "expect": "1 passed",
                                    "behaviour": "it stops dispatch"}]}])
    assert gaps == {"c": ["it changes no state"]}


def test_unnamed_probes_are_still_counted():
    """An older report carries no labels; the strict reading stays the safe one."""
    gaps = underprobed([{"criterion": "c",
                         "behaviours": ["a", "b", "c3"],
                         "probe": [{"command": "pytest -q", "expect": "passed"}]}])
    assert gaps == {"c": ["b", "c3"]}


def test_the_link_survives_the_validator_paraphrasing_its_own_list():
    """Both strings are the validator's own prose, and it rewrites its own labels.

    Measured live: a criterion whose behaviour read "it changes no state" carried a probe labelled
    "lapse handling mutates no node state" — the same behaviour, the same test, demoted because the
    two strings were not identical. What must exist is the LINK; recognising it is the engine's job.
    """
    gaps = underprobed([{"criterion": "c",
                         "behaviours": ["mutates no node state"],
                         "probe": [{"command": "pytest -q", "expect": "1 passed",
                                    "behaviour": "lapse handling mutates no node state at all"}]}])
    assert gaps == {}


def test_an_unrelated_label_does_not_cover_a_behaviour():
    """Tolerant matching must not become no matching: a label about something else leaves the
    behaviour unobserved, which is the case this rule exists for."""
    gaps = underprobed([{"criterion": "c",
                         "behaviours": ["mutates no node state", "stops the spawn"],
                         "probe": [{"command": "pytest -q", "expect": "1 passed",
                                    "behaviour": "stops the spawn"}]}])
    assert gaps == {"c": ["mutates no node state"]}


def test_one_command_with_a_fused_label_covers_the_behaviours_it_names():
    """A single command really observing two behaviours gets ONE label for both.

    Measured live 2026-08-20: behaviours ["pytest exits 0", "at least 1 test collected and run"]
    against the label "pytest exits 0 with >=1 test collected and run" — the same run, genuinely
    observing both. Containment caught the first and missed the second ("at least 1" vs ">=1"), so
    a COMPLETE report was refused, re-run, refused again, and the node parked. Four of ten
    validator runs that hour were spent on the writer's phrasing.
    """
    gaps = underprobed([{"criterion": "tests_pass",
                         "behaviours": ["pytest exits 0", "at least 1 test collected and run"],
                         "probe": [{"command": "pytest -q", "expect": "passed",
                                    "behaviour": "pytest exits 0 with >=1 test collected and run"}]}])
    assert gaps == {}


def test_overlap_matching_does_not_swallow_an_unrelated_label():
    """The tolerance must stay a tolerance: a label about something else leaves the behaviour
    unobserved, which is the whole point of the rule."""
    gaps = underprobed([{"criterion": "c",
                         "behaviours": ["hold space accumulates across lines",
                                        "the parser rejects an unterminated s command"],
                         "probe": [{"command": "pytest -q", "expect": "1 passed",
                                    "behaviour": "hold space accumulates across lines"}]}])
    assert gaps == {"c": ["the parser rejects an unterminated s command"]}
