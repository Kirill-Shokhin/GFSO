"""The per-stage table was right and the reader still had to do the division.

`usage` returns a total and a split by stage. The question a bill actually raises -- what is the
expensive part, and how much of it -- was one division away and nobody did it. That is not a
hypothetical reader: on 2026-09-05 I read an instrument's `usage_inner_agent_only` as a run's total
and was out by 3x, on a measurement whose PRE-REGISTERED question was precisely the judge's share of
spend, with the true split ($2.33 of $3.44, 68% on judging) sitting inside the same object.

A surface whose stated doctrine is that a metric arrives with what it means owes the division too.
"""
from __future__ import annotations

import inspect

import gfso.tools as T


def _out(total, stages):
    return T._where_the_money_went({"cost_usd": total,
                                    "by_stage": {k: {"cost_usd": v} for k, v in stages.items()}})


def test_the_largest_stage_is_named_with_its_share():
    got = _out(3.4414, {"l2-checker": 0.5112, "validate_result": 2.3282, "search-1": 0.0671})
    assert got["largest_stage"]["stage"] == "validate_result"
    assert got["largest_stage"]["share"] == 0.677
    assert "68%" in got["largest_stage"]["means"] and "$2.33 of $3.44" in got["largest_stage"]["means"]


def test_a_project_that_spent_nothing_claims_nothing():
    """⊥ is not zero, and a share of nothing is not a fact about anything: an empty bill says
    nothing rather than naming a 100% stage that does not exist."""
    assert _out(0.0, {}) == {}
    assert _out(0.0, {"l2-checker": 0.0}) == {}


def test_one_stage_carries_the_whole_bill():
    got = _out(1.5, {"validate_result": 1.5})
    assert got["largest_stage"]["share"] == 1.0


def test_it_rides_on_the_verb_itself():
    """The control: a helper nothing calls is a helper that helps nobody."""
    assert "_where_the_money_went" in inspect.getsource(T.usage)
