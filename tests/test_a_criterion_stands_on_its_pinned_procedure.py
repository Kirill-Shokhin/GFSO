"""A criterion is decided by the procedure it pinned; what the validator names beyond it is exploration.

Measured on AUTO coreutils (2026-10-10, every role on one cheap model): 7 of 19 validations decided nothing, and
every one would still be refused by the engine as it stood — by the FORM of the report, not by missing coverage.
Four named behaviours (`\\0NNN`, a mid-line `\\r`, LANG variants) that the criterion's OWN pinned probe exercises,
run and cited by id, and labelled that probe with one behaviour; the report that passed repeated the same command
once per label. Two put a seam criterion only under the free-text `seams` note. Two did not parse over a top-level
`failed_criteria` the record derives from the entries anyway.

A1 and Inv-1's pre-registration say which half binds: a criterion is decided by its pinned procedure, so where the
report ran ALL of it and it held, a behaviour named without a label of its own is recorded as named but not
separately observed. Nothing else moves: a procedure run short, an owed part probe, a standing finding, an observed
divergence decide exactly as before (Inv-2, Inv-3).

CONTROL: make `procedure.named_beyond_procedure` return `{}` and the acceptance tests go red; drop its `not in unrun`
clause and the short-procedure control goes red.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.adapters.llm.structured import parse_structured
from gfso.core.protocol.invariants import verdict_report_defects
from gfso.core.protocol.procedure import coverage, probe_id, unaccounted_for
from gfso.core.types import TaskId
from gfso.packets import _validator_packet
from gfso.tools_llm import _VALIDATOR_SCHEMA, _listed_failed, _report_contradicts_itself
from tests.support import DENIAL_ENTRY, UNMODELLED_FAULT, criterion, make_engine, REGISTER

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY", "justification": "no precedent",
          "invalidation_condition": "one occurs", "p": 0.01, "impact": "the run stops and is resumed"}, DENIAL_ENTRY]
ESC = "Escape decoding"
SWEEP = {"behaviour": "escapes match GNU", "command": ". h.sh; for s in '\\0101' '\\01011' 'a\\rb'; do c echo -e $s; done; echo ok",
         "expect": "ok"}
OTHER = {"behaviour": "\\c stops output", "command": ". h.sh; c echo -e 'a\\cb'; echo ok", "expect": "ok"}
NAMED = ["\\c stops output and every escape matches GNU", "\\0NNN with up to 3 octal digits after the 0 matches GNU"]


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


@pytest.fixture
def engine():
    made = []

    def _make(*checks):
        e = make_engine()
        e.start()
        T.create_task(e, "root", {"description": "echo", "accepted_risks": _RISK,
                                  "criteria": [{"name": ESC, "description": "echo -e decodes as GNU does",
                                                "check": list(checks)}]}, assignee="me")
        T.signal(e, "root", "ACCEPT", "me")
        T.signal(e, "root", "DELIVER", "me", result="built it")
        e.wait_idle()
        made.append(e)
        return e
    yield _make
    for e in made:
        e.stop()


def _ran(probe, label=NAMED[0], **kw):
    return {"id": probe_id(ESC, probe).split("#", 1)[1], "command": probe["command"], "expect": "ok",
            "behaviour": label, **kw}


def _entry(*probes, verdict="pass", **kw):
    return {"criterion": ESC, "verdict": verdict, "evidence": "the pinned sweep printed only ok",
            "behaviours": list(NAMED), "probe": list(probes), "divergences": [], **kw}


# === (a) the criterion stands on its procedure ===

def test_a_named_behaviour_the_whole_pinned_procedure_ran_over_is_not_a_refusal(engine):
    """The root.echo shape: one pinned sweep, run and cited by id, labelled with the first behaviour only."""
    e = engine(SWEEP)
    out = e.record_exec_verdict("root", "PASS", [], "validator", per_criterion=[_entry(_ran(SWEEP))],
                                require_probe=True)
    assert out["verdict"] == "PASS", out
    rec = e.get_exec_verdict(TaskId("root"))
    assert rec["named_beyond_the_procedure"] == {ESC: [NAMED[1]]}, (
        "the behaviour named past the procedure must stay visible in the record, as named but not separately observed")


def test_the_record_says_nothing_was_named_beyond_when_every_label_is_there(engine):
    e = engine(SWEEP)
    e.record_exec_verdict("root", "PASS", [], "validator", require_probe=True,
                          per_criterion=[_entry(_ran(SWEEP), _ran(SWEEP, NAMED[1]))])
    assert e.get_exec_verdict(TaskId("root"))["named_beyond_the_procedure"] == {}


def test_a_procedure_run_short_keeps_the_label_rule(engine):
    """CONTROL — two pinned probes, one run: the unlabelled behaviour is still unobserved, and the refusal says so
    together with the probe the procedure pinned and the report skipped."""
    e = engine(SWEEP, OTHER)
    with pytest.raises(ValueError) as ex:
        e.record_exec_verdict("root", "PASS", [], "validator", per_criterion=[_entry(_ran(SWEEP))],
                              require_probe=True)
    assert NAMED[1] in str(ex.value) and "PINS" in str(ex.value), str(ex.value)


def test_a_procedure_the_ledger_says_was_never_run_keeps_the_refusal(engine):
    """CONTROL — the probe is cited, the run's tools show no shell: nothing of the procedure ran here."""
    e = engine(SWEEP)
    with pytest.raises(ValueError) as ex:
        e.record_exec_verdict("root", "PASS", [], "validator", per_criterion=[_entry(_ran(SWEEP))],
                              require_probe=True, tools_used={"Read": 3})
    assert "no shell" in str(ex.value)


def test_a_named_behaviour_with_an_observed_divergence_is_a_fail(engine):
    """CONTROL — a divergence under the behaviour named past the procedure is that criterion's value (Inv-2): marked
    pass beside it the report is no verdict, and spoken as fail it is the FAIL, recorded."""
    e = engine(SWEEP)
    seen = ["\\0101 printed A1 where GNU prints A"]
    with pytest.raises(ValueError) as ex:
        e.record_exec_verdict("root", "PASS", [], "validator", require_probe=True,
                              per_criterion=[_entry(_ran(SWEEP), divergences=seen)])
    assert "divergence" in str(ex.value)
    out = e.record_exec_verdict("root", "FAIL", [ESC], "validator", require_probe=True,
                                per_criterion=[_entry(_ran(SWEEP), verdict="fail", divergences=seen)])
    assert out == {"verdict": "FAIL", "failed_criteria": [ESC]}


# === (b) a seam criterion is answered in its own entry ===

def test_a_seam_criterion_left_to_the_seams_note_is_refused_saying_what_to_add():
    """The root.build shape: `dep__root.cat_core` covered only under the free-text `seams`, which carries no verdict
    word and no probe — so the record cannot read a verdict there, and the refusal names the entry to write."""
    d = verdict_report_defects(["Build", "dep__root.cat_core"], "PASS",
                               [{"criterion": "Build", "verdict": "pass"}], [])
    assert len(d) == 1 and "own `per_criterion` entry" in d[0] and "criterion: 'dep__root.cat_core'" in d[0], d


def test_the_validator_is_told_a_seam_criterion_needs_its_own_entry():
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "root", "criteria": [criterion("g", "G")]}, assignee="agent")
    T.decompose(e, "root", [{"task_id": k, "spec": {"description": k, "criteria": [criterion("k" + k, k.upper())]},
                             "assignee": "worker", "covers": ["g"]} for k in ("a", "b")], accepted_risks=REGISTER)
    T.add_dependency(e, "a", "b", glue="b reads a")
    e.wait_idle()
    text = _validator_packet(e, e.graph.get_task(TaskId("b")), "built it", ".")
    seam = text.split("**dep__a**", 1)[1].split("\n- **", 1)[0]
    assert "SEAM criterion" in seam and "OWN `per_criterion` entry" in seam, seam
    assert "SEAM criterion" not in text.split("**kb**", 1)[1].split("\n- **", 1)[0]
    e.stop()


# === (c) the failed list is derived where the report leaves it out ===

def test_a_report_without_a_failed_list_parses_and_derives_it():
    """The root.tail shape: no top-level `failed_criteria`."""
    report = '```json\n{"verdict": "FAIL", "per_criterion": [{"criterion": "a", "verdict": "pass"}, ' \
             '{"criterion": "b", "verdict": "fail"}]}\n```'
    parsed = parse_structured(report, _VALIDATOR_SCHEMA)
    assert parsed is not None
    assert _listed_failed(parsed) == ["b"] and _report_contradicts_itself(parsed) is None


def test_a_failed_list_that_disagrees_with_its_entries_is_still_refused():
    """CONTROL — a list that is THERE is the report's own claim, and one naming what its entries pass decides nothing."""
    parsed = {"verdict": "FAIL", "failed_criteria": ["a"], "per_criterion": [{"criterion": "a", "verdict": "pass"},
                                                                              {"criterion": "b", "verdict": "fail"}]}
    assert _listed_failed(parsed) == ["a"] and "contradict" in _report_contradicts_itself(parsed)


def test_a_failed_list_short_of_its_entries_is_read_off_them():
    """A FAIL whose list named one of its three red entries was refused whole, three validations of four nodes left no
    verdict and the clock escalated two delivered parts (GB_sql_database_tmwsep280, 2026-10-15)."""
    reds = [{"criterion": c, "verdict": "fail"} for c in ("x", "y", "z")]
    for listed in (["x"], []):
        parsed = {"verdict": "FAIL", "failed_criteria": listed, "per_criterion": reds}
        assert _listed_failed(parsed) == ["x", "y", "z"] and _report_contradicts_itself(parsed) is None
    assert "contradict" in _report_contradicts_itself({"verdict": "PASS", "failed_criteria": [], "per_criterion": reds})


def test_the_root_build_shape_is_read_and_a_report_cut_short_is_not():
    """The root.build shape — `failed_criteria` written inside the last entry, nothing closed after it — is the shape 23
    of 25 unreadable batch reports had, each whole (`structured._restored`); cut before the report's own fields, it
    stays a parse failure."""
    entry = '```json\n{"verdict": "PASS", "per_criterion": [{"criterion": "a", "verdict": "pass", '
    read = parse_structured(entry + '"failed_criteria": []}\n```', _VALIDATOR_SCHEMA)
    assert read is not None and read["failed_criteria"] == [] and read["per_criterion"] == [{"criterion": "a",
                                                                                           "verdict": "pass"}]
    assert parse_structured(entry + '"evidence": "ran"}\n```', _VALIDATOR_SCHEMA) is None


def test_a_criterion_short_on_another_count_is_refused_for_everything_it_is_short_of(engine):
    """CONTROL — the whole pinned procedure ran, but a probe that refuted this criterion before was not re-run: the
    criterion does not stand, and the behaviour named past the procedure is named in its refusal as before."""
    e = engine(SWEEP)
    regression = {ESC: [{"id": f"{ESC}#deadbeef", "command": "printf '\\0101' | ./echo -e"}]}
    gaps = unaccounted_for(e.graph.get_task(TaskId("root")), [_entry(_ran(SWEEP))], False, "validator", regression)
    assert NAMED[1] in gaps[ESC] and any("REFUTED" in g for g in gaps[ESC]), gaps


def test_the_record_names_nothing_beyond_a_procedure_run_short(engine):
    """CONTROL — a behaviour is exploration only past a procedure run WHOLE; short of it, it is an unobserved conjunct
    and the record must not file it as exploration."""
    crit = engine(SWEEP, OTHER).graph.get_task(TaskId("root")).spec.criteria
    assert coverage(crit, [_entry(_ran(SWEEP))])["named_beyond_the_procedure"] == {}
    assert coverage(crit, [_entry(_ran(SWEEP), _ran(OTHER))])["named_beyond_the_procedure"] == {ESC: [NAMED[1]]}
