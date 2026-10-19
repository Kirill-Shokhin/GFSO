"""A validation call that was CUT mid-flight looked exactly like a validator that answered badly.

Measured on a paid run (2026-09-06, `database_engine`): the call ran fifteen minutes, came back with
232 tokens — one sentence, "I'll inspect the delivery and run real probes" — and cost $0.00. Zero
cost with non-zero time is a transport that stopped, not a model that validated poorly, but everything
downstream saw only "the report did not parse". So the layer escalated to a tier three times the
price, spent the node's one retry on it, parked the node, and the run ended there with the delivery
never having been validated even once.

The two want opposite handling: a thin report is answered by a bigger model, a severed pipe by
dialling again. What tells them apart is an observation rather than an inference — the provider
reading the CLI's stream sees it end with no result event — where the product had been
reconstructing the fact from a symptom (short text, no brace).

Two rules are pinned here, and each has its control. The BUDGET: a cut call does not consume the
retry that exists to buy a second VALIDATION, because it produced no first one. The BOUND: the
redials end, since an installation that cannot complete the same call twice running has a fault a
third attempt does not reach.
"""
from __future__ import annotations

import time
import types

import gfso.tools as T
from gfso import delegate as D
from gfso.core.types import AgentId, Mode
from gfso.delegate import Dispatcher
from tests.support import criterion, make_engine, REGISTER
from tests.test_delegate import _agents

_RISK = REGISTER


def _a_delivery(e):
    T.create_task(e, "par", {"description": "parent",
                             "criteria": [criterion("g", "G")],
                             "accepted_risks": _RISK}, assignee="a-human")
    T.decompose(e, "par", [{"task_id": "kid", "spec": {"description": "the work",
                             "criteria": [criterion("k", "K")]}, "assignee": "exec-1", "covers": ["g"]}], accepted_risks=REGISTER)
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
    parked = "kid" in {str(x) for x in e.parking.parked_validations()}
    e.stop()
    return tiers, parked


def test_a_cut_call_does_not_park_the_node_on_the_transport(tmp_path, monkeypatch):
    monkeypatch.delenv("GFSO_VALIDATOR_RETRY_MODEL", raising=False)   # escalation ON, the default
    tiers, parked = _drive(tmp_path, "no-verdict:torn", passes=2)
    assert not parked, \
        "two cut calls parked the node for a person, though nothing had validated the delivery yet"
    assert all(t is None for t in tiers), \
        f"a bigger model was bought for a severed pipe, which it does not repair: {tiers}"


def test_a_thin_report_still_spends_the_retry_and_still_escalates(tmp_path, monkeypatch):
    """The control. Without it the test above passes on a dispatcher that never parks and never
    escalates — which would silence the whole mechanism instead of narrowing it. The escalation is the
    installation's to name (off by default since 2026-09-27), so the control names it."""
    monkeypatch.setenv("GFSO_VALIDATOR_RETRY_MODEL", "opus")
    tiers, parked = _drive(tmp_path, "no-verdict", passes=2)
    assert parked, "a validator that answered twice and decided nothing is the issuer's call (§2.3)"
    assert any(t is not None for t in tiers), \
        f"the escalation that answers a thin report must survive this change: {tiers}"


def test_the_redials_end(tmp_path, monkeypatch):
    """The bound. Past its own budget a cut call falls through to the ordinary path and parks."""
    monkeypatch.delenv("GFSO_VALIDATOR_RETRY_MODEL", raising=False)
    _, parked = _drive(tmp_path, "no-verdict:torn", passes=D.TORN_REDIALS + 2)
    assert parked, \
        f"after {D.TORN_REDIALS} redials plus the ordinary retry the node must reach a person — " \
        f"an unbounded redial is the loop Inv-5 exists against"


def test_where_the_system_is_the_issuer_no_verdict_is_asked_again_not_parked(tmp_path, monkeypatch):
    """Parking after two reports with no verdict tells the ISSUER to decide. Under AUTO the root's issuer
    is the customer, who may not move — measured live, it took the project back instead. A system issuer
    owes the verdict within T_validate and can only obtain one, so its instrument is asked again."""
    monkeypatch.setattr(D, "REVALIDATE_S", 0.3); monkeypatch.setattr(D, "REVALIDATE_IDLE_S", 0.3)
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("exec-2", "llm-executor"), ("val-1", "llm-validator"))
    e.project_name = "p"
    e.workforce.publish_executor_pool({"exec-1": "p", "exec-2": "p"})
    T.create_task(e, "par", {"description": "parent", "criteria": [criterion("g", "G")],
                             "accepted_risks": _RISK}, assignee="exec-1")
    T.decompose(e, "par", [{"task_id": "kid", "spec": {"description": "the work", "criteria": [criterion("k", "K")]}, "assignee": "exec-2", "covers": ["g"]}], accepted_risks=REGISTER)
    T.signal(e, "par", "ACCEPT", "exec-1")
    e.set_mode(Mode.AUTO, None, AgentId("agent"))
    T.signal(e, "kid", "ACCEPT", "exec-2")
    T.signal(e, "kid", "DELIVER", "exec-2", result="did it")
    tiers = []
    d = Dispatcher(e, agents, runner=lambda *a: None,
                   validator_runner=lambda *a, **k: tiers.append(1) or "no-verdict")
    for _ in range(4):
        d.dispatch_once()
        time.sleep(0.8)
    parked = "kid" in {str(x) for x in e.parking.parked_validations()}
    e.stop()
    assert not parked and len(tiers) >= 3, (parked, len(tiers))


def test_a_scope_whose_validation_twice_left_no_verdict_is_asked_again(monkeypatch):
    """The scope's door into the re-ask shares its rule with the node's (`_reask_wait`): a delta that gave the re-ask a
    wait and changed only the node's caller left the scope's raising a TypeError on its second verdict-less run, the
    thread dying with its slot held (critic over session a597fc08)."""
    timers = []
    monkeypatch.setattr(D, "_system_issues", lambda *a: True)
    monkeypatch.setattr(D.threading, "Timer", lambda wait, *a: timers.append(wait) or types.SimpleNamespace(
        daemon=True, start=lambda: None))
    e = make_engine()
    d = D.Dispatcher(e, types.SimpleNamespace(list=lambda: {}, get=lambda k: None),
                     scope_validator=lambda *a, **k: "no-verdict")
    monkeypatch.setattr(d._engine, "scope_members", lambda top: [])
    monkeypatch.setattr(d, "_scope_key", lambda members: "K")
    d._validate_scope_guarded("root", "K")
    d._validate_scope_guarded("root", "K")
    assert timers == [D.REVALIDATE_S], timers


def test_the_issuers_contact_runs_only_where_it_can(monkeypatch, tmp_path):
    """A registered workdir that is not there made the issuer's run return nothing — `Unavailable`, uncounted, asked
    again for ever; a transport without agent runs (`generic`) failed every issuer turn. Neither is a place for contact,
    and the question is then asked as before contact existed (critic over session a597fc08)."""
    gone = tmp_path / "gone"
    monkeypatch.setattr(D, "validator_workdir", lambda engine, agents, node: str(gone))
    assert D._contact_place(None, None, "n") is None
    monkeypatch.setattr(D, "validator_workdir", lambda engine, agents, node: str(tmp_path))
    assert D._contact_place(None, None, "n") == str(tmp_path)
    monkeypatch.setattr(D, "provider", lambda: "generic")
    assert D._contact_place(None, None, "n") is None
