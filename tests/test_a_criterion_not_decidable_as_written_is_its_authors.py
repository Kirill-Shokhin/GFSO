"""A criterion its validator finds not decidable as written is a defect of its text: not asked again, its author's.

A report whose only gaps are criteria the validator calls `not_decidable` is no verdict (§2.3) — and no FAIL either, the
executor has nothing to fix. Re-asked as a labelling gap is, it looped under AUTO: one retry, then a paid re-ask every
REVALIDATE_S until VALIDATING's bound, then the same contract re-presented to the same ⊥ (critic over b4129a7). By
§9.7 and §11.2 (form item (1)) it is sourced in the task: the dispatcher asks no more, as for a check past its whole
bound — one rule, `accounting.not_asked_again` —, and the issuer is told each criterion with the validator's why. A labelling gap — a behaviour named, no labelled probe — stays re-asked: a retry cures it.

CONTROL: route `no-verdict:spent` as a plain `no-verdict` in the dispatcher and the dispatcher tests go red; drop the
as-written class from `accounting.not_asked_again` and the record test does.
"""
from __future__ import annotations

import time

import pytest

import gfso.issuer as I
import gfso.tools as T
from gfso.core.types import TaskId
from gfso.delegate import Dispatcher
from gfso.validate import _classify_no_verdict
from tests.support import criterion, make_engine
from tests.test_a_validator_that_never_ran_is_not_a_model_problem import _a_delivery
from tests.test_delegate import _agents

WHY = "not decidable as written: 'feels fast' names nothing to observe on the delivery"


def _delivered():
    e = make_engine(check_interval=10_000)
    e.start()
    T.create_task(e, "n", {"description": "leaf", "criteria": [criterion("a", "A"), criterion("b", "B")]},
                  assignee="worker")
    T.signal(e, "n", "ACCEPT", "worker")
    T.signal(e, "n", "DELIVER", "worker", result="did it")
    return e


#: behaviours no label of another matches (`invariants._unobserved_by_label` reads overlap of content words)
SAID = ["sorts ascending", "stable under ties", "rejects empty input"]


def _entry(name, word, evidence, behaviours=1, probes=1):
    return {"criterion": name, "verdict": word, "evidence": evidence, "behaviours": SAID[:behaviours],
            "probe": [{"behaviour": SAID[k], "command": f"check {name}", "expect": "it holds"}
                      for k in range(probes)], "divergences": []}


def _refused(e, *entries):
    with pytest.raises(ValueError) as bottom:
        e.record_exec_verdict("n", "FAIL", [x["criterion"] for x in entries if x["verdict"] != "pass"], "val-1",
                              require_probe=True, per_criterion=list(entries))
    e.record_rejected_report(TaskId("n"), str(bottom.value), list(entries))   # …kept as `validate._record_node` keeps it
    return str(bottom.value)


def _said(e):
    return type("E", (), {"emit_info": lambda self, *a: None})()


def test_a_refusal_over_criteria_not_decidable_as_written_says_it_is_not_asked_again():
    e = _delivered()
    entries = (_entry("a", "not_decidable", WHY, behaviours=3), _entry("b", "pass", "it holds", 1))
    first = _refused(e, *entries)        # …one reading: asked once more, a second run's reading spends it
    assert not first.startswith("NOT ASKED AGAIN") and WHY in first, first
    why = _refused(e, *entries)
    assert why.startswith("NOT ASKED AGAIN") and WHY in why, why
    assert _classify_no_verdict(_said(e), "n", {"error": why, "stats": [{"cost_usd": 0.1}]}) == "no-verdict:spent"
    e.stop()


def test_a_labelling_gap_beside_it_stays_re_asked():
    """CONTROL — a behaviour named and probed by nothing labelled: a retry can cure it, so it is asked again."""
    e = _delivered()
    why = _refused(e, _entry("a", "not_decidable", WHY), _entry("b", "pass", "it holds", behaviours=2))
    assert "NOT ASKED AGAIN" not in why, why
    assert _classify_no_verdict(_said(e), "n", {"error": why, "stats": [{"cost_usd": 0.1}]}) == "no-verdict"
    e.stop()


def _dispatch(tmp_path, ret, rounds=3):
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    _a_delivery(e)
    runs = []
    d = Dispatcher(e, agents, runner=lambda *a: None,
                   validator_runner=lambda *a, **k: runs.append(1) or ret)
    for _ in range(rounds):
        d.dispatch_once()
        time.sleep(0.5)
    log = " ".join(str(r.get("message")) for r in e.pipeline_log())
    parked = "kid" in {str(x) for x in e.parking.parked_validations()}
    e.stop()
    return len(runs), log, parked


def test_where_the_system_issues_it_waits_for_the_issuer(tmp_path, monkeypatch):
    monkeypatch.setattr("gfso.delegate.system_issues", lambda *a: True)
    runs, log, parked = _dispatch(tmp_path, "no-verdict:spent")
    assert runs == 1, runs
    assert "NOT ASKED AGAIN" in log and not parked, log[-600:]


def test_a_person_issuer_is_told_on_their_frontier_at_once(tmp_path):
    """A person issuing the node waits on nothing silent: after its retry the refusal parks as any other does, its
    validator's why in the refused report (critic over cc4da2d: in VALIDATING for 14 days, their step «VALIDATE»)."""
    runs, log, parked = _dispatch(tmp_path, "no-verdict:spent")
    assert runs == 1 and parked, (runs, parked)


def test_nothing_observed_is_the_instruments_not_the_texts():
    """CONTROL — «I observed nothing deciding it» (`undecidable`) is re-asked, never «rewrite the criterion»: a delivery
    that did not build went that way when one word carried both (critic over cc4da2d)."""
    e = _delivered()
    why = _refused(e, _entry("a", "undecidable", "could not observe: make fails, ./prog not built"),
                   _entry("b", "pass", "it holds"))
    assert "NOT ASKED AGAIN" not in why, why
    assert _classify_no_verdict(_said(e), "n", {"error": why, "stats": [{"cost_usd": 0.1}]}) == "no-verdict"
    e.stop()


def test_a_labelling_gap_is_retried_then_parked_as_before(tmp_path):
    """CONTROL — the re-askable class keeps its route: one retry, then the issuer's park."""
    runs, log, parked = _dispatch(tmp_path, "no-verdict")
    assert runs == 2 and parked and "NOT ASKED AGAIN" not in log, (runs, parked)


def test_the_issuer_is_told_each_criterion_and_why(monkeypatch):
    """The lapse's question names each criterion not passed, with the validator's word and evidence, and what it asks."""
    e = _delivered()
    _refused(e, _entry("a", "not_decidable", WHY), _entry("b", "pass", "it holds"))
    monkeypatch.setattr(I, "_validation_lapsed", lambda engine, task: True)
    text = I.issuer_context(e, "n", "escalation")
    assert "Why its validation decided nothing" in text and WHY in text and "a — not_decidable" in text, text[-1500:]
    e.stop()
