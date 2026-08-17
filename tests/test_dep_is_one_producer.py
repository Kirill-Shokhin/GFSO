"""A Dep criterion names ONE producer, and anything else is refused at the door.

Lived: a criterion arrived carrying `depends_on: ["root.parser", "root.regex"]`, was stored
verbatim, and surfaced later as a dependency edge whose `from` was a list — which crashed the cycle
check with `unhashable type: 'list'` and killed a run four hours in. A seam is criteria-content
(§10): two producers are two criteria, not one criterion naming two.
"""
import pytest

from gfso.tools import _spec_from


def test_two_producers_in_one_criterion_are_refused_with_a_usable_message():
    with pytest.raises(ValueError) as e:
        _spec_from({"description": "d", "criteria": [
            {"name": "dep__both", "description": "g", "depends_on": ["root.parser", "root.regex"]}]})
    msg = str(e.value)
    assert "root.parser" in msg and "one `depends_on` criterion for each producer" in msg


def test_one_producer_is_the_normal_case():
    spec = _spec_from({"description": "d", "criteria": [
        {"name": "dep__parser", "description": "g", "depends_on": "root.parser"}]})
    assert spec.criteria[0].depends_on == "root.parser"


def test_no_dependency_stays_no_dependency():
    spec = _spec_from({"description": "d", "criteria": [{"name": "plain", "description": "g"}]})
    assert spec.criteria[0].depends_on is None
