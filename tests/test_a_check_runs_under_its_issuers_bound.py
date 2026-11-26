"""A pinned check may carry its issuer's own bound (`Probe.bound_s`): the system runs it under that bound — the default
`PROBE_S` where none is stated, logged as supplied (§2.5's rule for a deadline) — and never past the validation's own
bound. One fixed bound nobody could state made a slow honest check undecidable on every delivery: a whole suite pinned
at ~9 minutes passed in its validator's run, 5093 of 5093, and its report was ⊥ because the system's own run was cut
at 60 s. A FAIL stays the validator's to show (§8.4); what moved is only how long the system's run may take.

Driven through the doors that write criteria (`create_task`, `edit_criteria`) and the system's own run at validation;
`PROBE_S` is set low so a stated bound of seconds stands in for one of minutes.

CONTROLS (each breaks exactly its tests): `observe.bound_of` → `PROBE_S` — the four validations under a stated bound;
drop `bound_s` from `Probe.of` — those, the door's refusals and the round trip; drop the `unrunnable_bounds` rung — the
refusals; `_pins_budget` without the stated bounds — the budget test; drop the `UNDER_THE_DEFAULT` mark — the supplied
test."""
from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

import gfso.observe as O
import gfso.validate as VAL
from gfso import tools as T
from gfso.core.protocol import procedure
from gfso.core.types import Criteria, Probe
from gfso.decompose import loop
from gfso import issuer
from tests.support import committed
from tests.test_the_system_runs_an_exact_check_itself import _Says, _validated
from tests.test_validate_result import _eng

SLOW = "sleep 2; cat out.txt"
#: what the record says of a check cut at the default bound, its issuer having stated none
DEFAULT = "under the system's default bound"


@pytest.fixture
def short(monkeypatch):
    """The default bound at one second: a check of two is past it, as a suite of minutes is past sixty."""
    monkeypatch.setattr(O, "PROBE_S", 1)


def test_a_check_past_the_default_inside_its_stated_bound_decides_its_criterion(tmp_path, short):
    assert _validated(tmp_path, "hello", cmd=SLOW, bound_s=6)["verdict"] == "PASS"


def test_a_check_inside_its_stated_bound_fails_wrong_work_on_the_systems_run(tmp_path, short):
    out = _validated(tmp_path, "goodbye", cmd=SLOW, bound_s=6)
    assert out["verdict"] == "FAIL" and out["failed_criteria"] == ["c"], out


def test_a_check_with_no_stated_bound_runs_under_the_default_logged_as_supplied(tmp_path, short):
    out = _validated(tmp_path, "hello", cmd=SLOW)
    assert out.get("verdict") not in ("PASS", "FAIL"), out
    assert DEFAULT in json.dumps(out), out


def test_a_check_past_its_own_stated_bound_is_undecided_under_the_longer_default(tmp_path):
    """A bound stated shorter than the default is the issuer's too: the system's run does not outlast it."""
    out = _validated(tmp_path, "hello", cmd="sleep 3; cat out.txt", bound_s=1)
    assert out.get("verdict") not in ("PASS", "FAIL"), out
    assert DEFAULT not in json.dumps(out), out


def test_a_check_bound_written_by_edit_criteria_is_kept_and_decides(tmp_path, short):
    place = tmp_path / ".gfso-nodes-p" / "n"
    place.mkdir(parents=True)
    (place / "out.txt").write_text("hello\n")
    e = _eng()
    probe = {"behaviour": "it greets", "command": SLOW, "expect": "hello", "exact": True}
    T.create_task(e, "n", {"description": "greet", "criteria": [{"name": "c", "description": "prints hello",
                                                                  "check": [probe]}]}, "alice")
    got = T.edit_criteria(e, "n", [{"name": "c", "description": "prints hello", "check": [{**probe, "bound_s": 6}]}], "alice")
    assert not (got or {}).get("error"), got
    assert [p.bound_s for p in e.graph.get_task("n").spec.criteria[0].check] == [6]
    T.signal(e, "n", "ACCEPT", "alice")
    T.signal(e, "n", "DELIVER", "alice", result="out.txt", _recorded=committed(place))
    try:
        out = VAL.validate_result(e, "n", _llm=_Says(SLOW, "hello"), workdir=str(place))
    finally:
        e.stop()
    assert out["verdict"] == "PASS", out


@pytest.mark.parametrize("bound", [0, -5, "600", True, float("inf"), 10**400])
def test_a_check_bound_that_is_no_seconds_is_refused_at_the_door(bound):
    e = _eng()
    try:
        got = T.create_task(e, "n", {"description": "greet", "criteria": [{"name": "c", "description": "prints hello",
            "check": [{"behaviour": "it greets", "command": "cat out.txt", "expect": "hello", "bound_s": bound}]}]})
    finally:
        e.stop()
    assert procedure.UNBOUNDED_CHECK in json.dumps(got, ensure_ascii=False) and e.graph.get_task("n") is None, got


def test_a_check_bound_past_the_validations_own_bound_is_refused(monkeypatch):
    monkeypatch.setenv("GFSO_BOUND_VALIDATING", "100")
    crit = lambda s: [Criteria("c", "prints hello", check=(Probe("it greets", "cat out.txt", "hello", bound_s=s),))]
    assert any(procedure.UNBOUNDED_CHECK in d for d in procedure.admission_defects(crit(101)))
    assert not any(procedure.UNBOUNDED_CHECK in d for d in procedure.admission_defects(crit(100)))


def test_the_validations_own_bound_caps_the_checks_stated_bounds():
    p = lambda s=None: (("n", "c#1"), None, Probe("b", "cmd", "x", exact=True, bound_s=s))
    assert VAL._pins_budget([p(500), p()], None) == VAL.OBSERVE_S + 2 * VAL.FRESH_S + 500
    assert VAL._pins_budget([p(500), p()], 120) == 120


def test_a_stated_check_bound_round_trips_and_moves_the_procedure():
    q = Probe("b", "cmd", "x", exact=True, bound_s=540)
    assert Probe.of(q.to_dict()) == q and "bound_s" not in Probe("b", "cmd", "x").to_dict()
    digest = lambda p: procedure.procedure_digest([Criteria("c", check=(p,))])
    assert digest(q) != digest(Probe("b", "cmd", "x", exact=True))


def test_the_plans_prompts_say_a_check_may_state_its_bound_from_one_owner():
    for said in (loop.AUDIT_PROMPT, issuer._prompt()):
        assert f"runs {procedure.PROBE_S} seconds at most" in said and "`bound_s`" in said
    for schema in (loop.AUDIT_SCHEMA, issuer._CRITERIA):
        assert json.dumps(procedure.BOUND_TEXT) in json.dumps(schema)
    assert f"left out, {procedure.PROBE_S}" in procedure.BOUND_TEXT


def test_an_issuers_restated_check_keeps_its_stated_bound():
    """A machine issuer restating a pinned check without `bound_s` (its answer names the same command) keeps the bound the
    check states, as its pinned inputs are kept: dropped, the restatement alone sent a long check back to ⊥."""
    stored = Criteria(name="c", check=(Probe(behaviour="suite", command="make test", expect="ok", bound_s=600.0),))
    (kept,) = issuer._probes(stored, (Probe(behaviour="suite", command="make test", expect="ok"),))
    assert kept.bound_s == 600.0
    (other,) = issuer._probes(stored, (Probe(behaviour="x", command="make other", expect="ok"),))
    assert other.bound_s is None, "a new command states its own bound"


def test_a_check_bound_past_the_budget_is_spent_once_it_had_the_whole_budget(monkeypatch):
    """A stated bound longer than what the validation can give: the check that had the whole budget and was cut by it is
    spent — a re-ask gives it no more, and each re-ask is paid (critic over the stated bound); one cut behind another is
    re-run alone next, with the whole budget, so it is not."""
    def fresh(ex, bash, c, p, tree, t, *a):
        time.sleep(min(t, 1.2))
        return {"note": f"did not finish in {t:.0f} s"}
    monkeypatch.setattr(O, "_fresh_run", fresh)
    ex = SimpleNamespace(shell=lambda: "sh")
    c = Criteria(name="c", check=(Probe(behaviour="a", command="slow a", expect="ok", bound_s=10.0),
                                  Probe(behaviour="b", command="slow b", expect="ok", bound_s=10.0)))
    (_, first), (_, second) = O.run_checks(ex, [("k", c, p) for p in c.check], "place", "tree", 1.5)
    assert first["timed_out"] and first["whole"], first
    assert second["timed_out"] and not second["whole"], second
