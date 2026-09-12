"""A judging call that was CUT mid-flight looked exactly like a judge that answered badly.

Measured on a paid run (2026-09-06, `database_engine`): the call ran fifteen minutes, came back with
232 tokens — one sentence, "I'll inspect the delivery and run real probes" — and cost $0.00. Zero
cost with non-zero time is a transport that stopped, not a model that judged poorly, but everything
downstream saw only "the report did not parse". So the layer escalated to a tier three times the
price, spent the node's one retry on it, parked the node, and the run ended there with the delivery
never having been judged even once.

The two want opposite handling: a thin report is answered by a bigger model, a severed pipe by
dialling again. What tells them apart is an observation rather than an inference — the provider
reading the CLI's stream sees it end with no result event — where the product had been
reconstructing the fact from a symptom (short text, no brace).

Two rules are pinned here, and each has its control. The BUDGET: a cut call does not consume the
retry that exists to buy a second JUDGEMENT, because it produced no first one. The BOUND: the
redials end, since an installation that cannot complete the same call twice running has a fault a
third attempt does not reach.
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


def _drive(tmp_path, outcome, passes):
    """Run the dispatcher `passes` times against a validator that always ends the same way."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    _a_delivery(e)
    tiers = []

    def _fake(engine, task_id, agents_, model_override=None, sign=True):
        tiers.append(model_override)
        return outcome

    d = Dispatcher(e, agents, runner=lambda *a: None, validator_runner=_fake)
    for _ in range(passes):
        d.dispatch_once()
        time.sleep(1.0)
    parked = "kid" in {str(x) for x in e.parked_validations()}
    e.stop()
    return tiers, parked


def test_a_cut_call_does_not_park_the_node_on_the_transport(tmp_path, monkeypatch):
    monkeypatch.delenv("GFSO_VALIDATOR_RETRY_MODEL", raising=False)   # escalation ON, the default
    tiers, parked = _drive(tmp_path, "no-verdict:torn", passes=2)
    assert not parked, \
        "two cut calls parked the node for a person, though nothing had judged the delivery yet"
    assert all(t is None for t in tiers), \
        f"a bigger model was bought for a severed pipe, which it does not repair: {tiers}"


def test_a_thin_report_still_spends_the_retry_and_still_escalates(tmp_path, monkeypatch):
    """The control. Without it the test above passes on a dispatcher that never parks and never
    escalates — which would silence the whole mechanism instead of narrowing it."""
    monkeypatch.delenv("GFSO_VALIDATOR_RETRY_MODEL", raising=False)
    tiers, parked = _drive(tmp_path, "no-verdict", passes=2)
    assert parked, "a judge that answered twice and decided nothing is the issuer's call (§11.2)"
    assert any(t is not None for t in tiers), \
        f"the escalation that answers a thin report must survive this change: {tiers}"


def test_the_redials_end(tmp_path, monkeypatch):
    """The bound. Past its own budget a cut call falls through to the ordinary path and parks."""
    monkeypatch.delenv("GFSO_VALIDATOR_RETRY_MODEL", raising=False)
    _, parked = _drive(tmp_path, "no-verdict:torn", passes=D.TORN_REDIALS + 2)
    assert parked, \
        f"after {D.TORN_REDIALS} redials plus the ordinary retry the node must reach a person — " \
        f"an unbounded redial is the loop Inv-5 exists against"
