"""A pinned exact check the system runs that does not finish within its own bound decided nothing (A1 (i), §2.3): the
criterion resting on it is ⊥ — no PASS stands over it (Inv-2), and no FAIL either: an honest slow check is no defect of
the work, the executor has nothing to fix. The first form put it in `failed_criteria` and reworked honest work; read as
the validator's word, a looping wrong delivery hid from the system's FAIL (security's critic, 2026-10-31). A check the
OBSERVATION's budget cut short decided nothing either — ⊥, but not past its WHOLE bound, so it is asked again with the
whole budget rather than handed to the issuer. The mark is the system's alone."""
from __future__ import annotations

import json

import gfso.observe as O
import gfso.tools_llm as TL
from gfso.delegate import _classify_no_verdict
from gfso.core.protocol.procedure import BOUND_SPENT, PAST_BOUND, PAST_WHOLE, probe_id, with_engine_observations
from gfso.core.types import Criteria, Probe
from tests.test_the_system_runs_an_exact_check_itself import _validated

CMD = "cat out.txt"
C = Criteria("c", "prints hello", check=(Probe("it greets", CMD, "hello", exact=True),))
PID = probe_id("c", C.check[0])
SAID = [{"criterion": "c", "verdict": "pass", "evidence": "ran it", "probe": [{"id": PID, "held": True}]}]


def test_past_its_own_bound_the_criterion_is_undecided_not_the_judges_word():
    (got,) = with_engine_observations(SAID, [C], None, {PID: {"note": "did not finish in 60 s", "timed_out": True}})
    assert got["verdict"] == "undecidable" and got[PAST_BOUND] == [PID]


def test_cut_by_the_observations_budget_it_is_undecided_and_asked_again():
    """As the runner marks it (`observe.observed`): not run for want of budget → `timed_out`, not `whole`."""
    cut = {"note": "not run: the observation's time ran out", "timed_out": True, "whole": False}
    (got,) = with_engine_observations(SAID, [C], None, {PID: cut})
    assert got["verdict"] != "pass" and got.get(PAST_BOUND) and not got.get(PAST_WHOLE)


def test_a_report_cannot_mark_its_own_entries_past_the_bound():
    forged = [{**SAID[0], "verdict": "fail", PAST_BOUND: [PID]}]
    assert all(PAST_BOUND not in e for e in with_engine_observations(forged, [C], None, {}))
    assert all(PAST_BOUND not in e for e in with_engine_observations(forged, [C], None, {PID: {"matched": True}}))


def test_a_looping_delivery_is_no_pass_and_no_fail(tmp_path, monkeypatch):
    """⊥: the report is refused, the node stays in VALIDATING for the retry and the issuer — not DONE, not reworked."""
    monkeypatch.setattr(O, "PROBE_S", 2)
    out = _validated(tmp_path, "hello", cmd="while :; do :; done; cat out.txt")
    assert out.get("verdict") not in ("PASS", "FAIL"), out
    assert "did not finish within the time they were given" in json.dumps(out), out


def test_a_validators_evidenced_fail_is_not_erased_by_the_absence():
    said = [{"criterion": "c", "verdict": "fail", "evidence": "it looped, I killed it", "probe": [{"id": PID, "held": False}]}]
    (got,) = with_engine_observations(said, [C], None, {PID: {"note": "did not finish in 60 s", "timed_out": True}})
    assert got["verdict"] == "fail" and PAST_BOUND not in got


def test_a_looping_check_after_slow_honest_ones_is_no_pass(tmp_path, monkeypatch):
    """The delivery's own code spends the observation's budget: a loop placed after slow checks met a cut bound, not
    its own, and passed on the judge's word (critic over the first form)."""
    monkeypatch.setattr(O, "PROBE_S", 2)
    monkeypatch.setattr(TL, "OBSERVE_S", 0, raising=False)
    monkeypatch.setattr(TL, "FRESH_S", 1.5, raising=False)
    out = _validated(tmp_path, "hello", cmd="sleep 1.6; while :; do :; done; cat out.txt")
    assert out.get("verdict") not in ("PASS", "FAIL"), out


def test_a_whole_bound_spent_is_not_asked_again(tmp_path, monkeypatch):
    """Given its whole bound and still unfinished, the same tree times out again: the refusal says so, and the
    dispatcher reads it as `no-verdict:bound` — no paid re-ask every half minute until T_validate (critic)."""
    monkeypatch.setattr(O, "PROBE_S", 2)
    out = _validated(tmp_path, "hello", cmd="while :; do :; done; cat out.txt")
    assert BOUND_SPENT in str(out.get("verdict_defects")), out
    said = type("E", (), {"emit_info": lambda self, *a: None})()
    assert _classify_no_verdict(said, "n", out) == "no-verdict:bound"


def test_a_bound_the_budget_cut_is_asked_again(tmp_path, monkeypatch):
    """Cut by the shared budget, the check never had its own bound: the re-run with the whole budget may decide it."""
    monkeypatch.setattr(O, "PROBE_S", 2)
    monkeypatch.setattr(TL, "OBSERVE_S", 0, raising=False)
    monkeypatch.setattr(TL, "FRESH_S", 1.5, raising=False)
    out = _validated(tmp_path, "hello", cmd="sleep 1.6; while :; do :; done; cat out.txt")
    assert out.get("verdict") not in ("PASS", "FAIL") and BOUND_SPENT not in str(out.get("verdict_defects")), out
