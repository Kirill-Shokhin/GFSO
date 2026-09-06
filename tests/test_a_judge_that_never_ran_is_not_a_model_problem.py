"""When no model ran, retrying on a bigger one buys nothing but the bill.

The no-verdict retry escalates the judge's tier, and the reasoning behind that is sound: a report
that comes back thin is usually a coverage-discipline gap, and a stronger model closes it first try.
It answers a MODEL-QUALITY problem.

On 2026-09-05 three paid runs died having spent both of their attempts on a judge that never reached
a model at all -- a roster leftover whose registered directory held none of the delivery. Each attempt
announced "a fuller report is usually a coverage-discipline gap", a confident diagnosis of something
that had not happened, and the second one parked the node for good.

Two things follow, and they are the same thing said at two levels: the tier is escalated only when a
model actually ran, and the line the reader gets is what the tool OBSERVED (`error`) rather than a
cause reconstructed from a cost of zero.
"""
from __future__ import annotations

import time

import gfso.tools as T
from gfso import delegate as D
from gfso.delegate import Dispatcher
from tests.support import make_engine
from tests.test_delegate import _agents

_RISK = [{"item": "an unmodelled environment fault", "predictability": "EXTRAORDINARY"}]


def _a_delivery(e):
    T.create_task(e, "par", {"description": "parent",
                             "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": _RISK}, assignee="a-human")
    T.create_task(e, "kid", {"description": "the work",
                             "criteria": [{"name": "k", "description": "K"}]},
                  assignee="exec-1", parent_id="par")
    T.map_criterion(e, "par", "kid", "g")
    T.signal(e, "kid", "ACCEPT", "exec-1")
    T.signal(e, "kid", "DELIVER", "exec-1", result="did it")


def _dispatch(tmp_path, verdict_result):
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    _a_delivery(e)
    tiers = []

    def _fake(engine, task_id, agents_, model_override=None, sign=True):
        tiers.append(model_override)
        return verdict_result

    d = Dispatcher(e, agents, runner=lambda *a: None, validator_runner=_fake)
    d.dispatch_once()
    time.sleep(1.0)
    d.dispatch_once()          # the retry, if one was queued
    time.sleep(1.0)
    e.stop()
    return tiers


def test_a_judge_that_never_ran_is_retried_on_its_own_tier(tmp_path, monkeypatch):
    monkeypatch.delenv("GFSO_VALIDATOR_RETRY_MODEL", raising=False)   # escalation ON, the default
    tiers = _dispatch(tmp_path, "no-verdict:never-ran")
    assert tiers and all(t is None for t in tiers), (
        f"a bigger model was bought for a judge that never reached one: {tiers}")


def test_a_report_that_came_back_thin_still_escalates(tmp_path, monkeypatch):
    """The negative control. Without it the test above passes on a dispatcher that never escalates."""
    monkeypatch.delenv("GFSO_VALIDATOR_RETRY_MODEL", raising=False)
    tiers = _dispatch(tmp_path, "no-verdict")
    assert "opus" in tiers, f"the coverage-discipline escalation is gone: {tiers}"


def test_the_line_says_what_the_tool_OBSERVED(tmp_path, monkeypatch):
    """`validate_result` returns an `error` naming what stopped the judging, and this layer used to
    throw it away and reconstruct a cause from a cost of zero: "it was refused before it started".
    That sentence stood over the three dead runs, and the arm reading the log then wrote a THIRD
    invented cause on top of it. Zero spend is a fact about the money and about nothing else."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    T.create_task(e, "n", {"description": "the work",
                           "criteria": [{"name": "c", "description": "C"}]}, assignee="exec-1")
    T.signal(e, "n", "ACCEPT", "exec-1")
    T.signal(e, "n", "DELIVER", "exec-1", result="did it")

    said: list = []
    monkeypatch.setattr(e, "emit_info", lambda src, msg: said.append(msg))
    _observed = "the judge stands in a directory holding none of this delivery"
    monkeypatch.setattr(D, "_judge_with",
                        lambda *a, **k: {"verdict": None, "error": _observed})
    e._graph.authorized_validators = {"val-1"}
    ret = D._auto_validate(e, "n", agents)

    assert any(_observed in m for m in said), said
    assert not any("refused before it started" in m for m in said), said
    assert ret == "no-verdict:never-ran", ret
    e.stop()
