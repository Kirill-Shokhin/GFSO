"""A criterion that states an intention decides nothing, and a PASS then means whatever the judge felt like checking.

Measured on `c_compiler` (2026-09-19/20). The root criterion read "for ANY accepted program the
compiler's output matches gcc" — a text quantified over an infinite domain, so nothing about it
returns pass/fail in finite time. The engine admitted it, and the procedure was supplied later, by
whoever validated, out of their own head, differently each round: `invariants.underprobed` asks only
that every behaviour the REPORT names carries a probe, which a judge satisfies by naming three
behaviours and probing three. The root closed DONE/PASS by an independent judge, and 205 probes
written from the same contract found 34 real divergences inside that closed tree.

So the one number the canon will not bend on — when the graph says PASS, the promise was executed —
was not readable off the graph at all. These tests pin the repair in all three places it has to
hold: the contract carries the procedure (A1, §10), execution does not open without it (Inv-1's
pre-registration, §14.4 — a check written after the work describes what was built), and a PASS that
skips a pinned probe is not a verdict (§11.2: ⊥ is not pass). Plus the honest residue: the record
says what was run, so "checked by P, behaviour outside P unchecked" is a fact a reader can see
rather than a boundary someone has to remember (FM-3, Ch. 8).
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.core.protocol.procedure import orphaned_regression, probe_id, procedure_digest
from gfso.core.types import Criteria, Probe
from tests.support import UNMODELLED_FAULT, criterion, make_engine

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY",
          "justification": "no precedent", "invalidation_condition": "one occurs"}]


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _engine(*criteria):
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": list(criteria),
                              "accepted_risks": _RISK}, assignee="me")
    e.wait_idle()
    return e


def _intention(name="matches_gcc"):
    """The real shape: a criterion whose text quantifies over what nobody can enumerate."""
    return {"name": name, "description": "for ANY accepted program the output matches gcc"}


# === the contract ===

def test_a_criterion_without_a_procedure_is_a_named_hole():
    e = _engine(_intention())
    holes = [h["check"] for h in T.list_holes(e)["holes"]]
    assert "A1:procedure" in holes, "an intention passed for a criterion and nothing said so"
    e.stop()


def test_the_hole_names_the_criterion_and_the_way_out():
    e = _engine(_intention(), criterion("exits_zero"))
    said = [h for h in T.list_holes(e)["holes"] if h["check"] == "A1:procedure"][0]["details"]
    assert "matches_gcc" in said and "exits_zero" not in said, (
        "the hole must name WHICH criterion decides nothing, not the whole contract")
    assert "check" in said, "a refusal that does not say what to write is a wall"
    e.stop()


def test_a_criterion_that_pins_its_procedure_closes_the_hole():
    e = _engine(criterion("exits_zero"))
    assert [h for h in T.list_holes(e)["holes"] if h["check"] == "A1:procedure"] == []
    e.stop()


def test_a_behaviour_with_no_command_pins_nothing():
    """The defect written one line higher: a procedure that names what to observe and not how."""
    e = _engine({"name": "c", "description": "it works",
                 "check": [{"behaviour": "it works", "command": "", "expect": "ok"}]})
    assert "A1:procedure" in [h["check"] for h in T.list_holes(e)["holes"]]
    e.stop()


# === the gate: the procedure is fixed BEFORE the work ===

def test_execution_does_not_open_on_a_criterion_that_decides_nothing():
    e = _engine(_intention())
    out = T.signal(e, "root", "ACCEPT", "me")
    assert out.get("accepted") is False, "work started against a contract nothing could decide"
    assert "pin no check" in str(out).lower() or "its own criteria" in str(out).lower()
    e.stop()


def test_the_same_node_starts_once_the_procedure_is_written():
    """The control — the gate must be about the procedure, not about refusing everything."""
    e = _engine(_intention())
    assert T.signal(e, "root", "ACCEPT", "me").get("accepted") is False
    T.edit_criteria(e, "root", [dict(_intention(), check=[
        {"behaviour": "hello world compiles and runs",
         "command": "./mycc t/hello.c -o /tmp/h && /tmp/h", "expect": "hello"}])], agent="me")
    e.wait_idle()
    assert T.signal(e, "root", "ACCEPT", "me").get("accepted") is True
    e.stop()


# === the verdict: a pass that skipped the pinned probe is not a verdict ===

def _delivered(e):
    T.signal(e, "root", "ACCEPT", "me")
    T.signal(e, "root", "DELIVER", "me", result="built it")
    e.wait_idle()


def test_a_pass_that_skips_the_pinned_probe_is_not_a_verdict():
    e = _engine(criterion("exits_zero"))
    _delivered(e)
    with pytest.raises(ValueError) as ex:
        e.record_exec_verdict("root", "PASS", [], "judge",
                              per_criterion=[{"criterion": "exits_zero", "verdict": "pass",
                                              "evidence": "looked at it, seems fine"}])
    assert "PINS" in str(ex.value) and "exits_zero" in str(ex.value)
    e.stop()


def test_the_same_pass_stands_when_the_pinned_probe_was_run():
    e = _engine(criterion("exits_zero"))
    _delivered(e)
    c = e.get_task("root").spec.criteria[0]
    out = e.record_exec_verdict(
        "root", "PASS", [], "judge",
        per_criterion=[{"criterion": "exits_zero", "verdict": "pass", "evidence": "ran it",
                        "probe": [{"id": probe_id(c.name, c.check[0]),
                                   "behaviour": c.check[0].behaviour,
                                   "command": c.check[0].command, "expect": c.check[0].expect}]}])
    assert out["verdict"] == "PASS"
    e.stop()


def test_a_report_that_quotes_the_command_counts_as_having_run_it():
    """Matching by id is a convenience; the command is the identity. A rule that forced ids would
    teach a judge to paste ids instead of running commands — the fabrication this all exists against."""
    e = _engine(criterion("exits_zero"))
    _delivered(e)
    c = e.get_task("root").spec.criteria[0]
    out = e.record_exec_verdict(
        "root", "PASS", [], "judge",
        per_criterion=[{"criterion": "exits_zero", "verdict": "pass", "evidence": "ran it",
                        "probe": [{"behaviour": c.check[0].behaviour, "command": c.check[0].command,
                                   "expect": "it holds"}]}])
    assert out["verdict"] == "PASS"
    e.stop()


def test_a_refutation_is_not_asked_to_sweep_the_whole_procedure_first():
    """A FAIL is already a decision. Demanding the full sweep before one may be spoken buys silence,
    not coverage — the same asymmetry §11.2 draws for an unobserved conjunct."""
    e = _engine(criterion("exits_zero"))
    _delivered(e)
    out = e.record_exec_verdict(
        "root", "FAIL", ["exits_zero"], "judge",
        per_criterion=[{"criterion": "exits_zero", "verdict": "fail",
                        "evidence": "it exits 1",
                        "probe": [{"behaviour": "exit code", "command": "run it; echo $?",
                                   "expect": "0"}]}])
    assert out["verdict"] == "FAIL"
    e.stop()


# === what contact found is re-run next time ===

def test_a_probe_that_once_refuted_the_node_must_be_re_run_to_pass_it():
    e = _engine(criterion("exits_zero"))
    _delivered(e)
    e.record_exec_verdict("root", "FAIL", ["exits_zero"], "judge",
                          per_criterion=[{"criterion": "exits_zero", "verdict": "fail",
                                          "evidence": "it exits 1",
                                          "probe": [{"behaviour": "exit code on an empty file",
                                                     "command": "./x empty.c; echo $?",
                                                     "expect": "0"}]}])
    assert "exits_zero" in e.regression_probes("root"), "what contact found was thrown away"
    c = e.get_task("root").spec.criteria[0]
    with pytest.raises(ValueError) as ex:
        e.record_exec_verdict(
            "root", "PASS", [], "judge",
            per_criterion=[{"criterion": "exits_zero", "verdict": "pass", "evidence": "fixed",
                            "probe": [{"command": c.check[0].command, "expect": "it holds",
                                       "behaviour": c.check[0].behaviour}]}])
    assert "REFUTED" in str(ex.value)
    e.stop()


def test_the_pinned_contract_is_not_rewritten_behind_the_executor():
    """The regression set is the NODE's history, not the criterion's text: growing the contract at
    judging time would move it under the executor, which is exactly what Inv-1 forbids. Promotion
    into the contract stays the issuer's act."""
    e = _engine(criterion("exits_zero"))
    _delivered(e)
    before = procedure_digest(e.get_task("root").spec.criteria)
    e.record_exec_verdict("root", "FAIL", ["exits_zero"], "judge",
                          per_criterion=[{"criterion": "exits_zero", "verdict": "fail",
                                          "evidence": "no", "probe": [{"behaviour": "b",
                                                                       "command": "./x", "expect": "0"}]}])
    assert procedure_digest(e.get_task("root").spec.criteria) == before
    e.stop()


# === the record says what it reached ===

def test_the_verdict_records_the_procedure_it_ran_and_how_far_it_went():
    e = _engine(criterion("exits_zero"))
    _delivered(e)
    c = e.get_task("root").spec.criteria[0]
    e.record_exec_verdict(
        "root", "PASS", [], "judge",
        per_criterion=[{"criterion": "exits_zero", "verdict": "pass", "evidence": "ran both",
                        "probe": [{"command": c.check[0].command, "expect": "it holds",
                                   "behaviour": c.check[0].behaviour},
                                  {"command": "./x weird.c", "expect": "0",
                                   "behaviour": "my own exploration"}]}])
    rec = e.get_exec_verdict("root")
    assert rec["procedure_digest"] == procedure_digest(e.get_task("root").spec.criteria)
    assert rec["pinned_probes"] == 1 and rec["criteria_with_procedure"] == 1
    assert rec["probes_beyond_the_procedure"] == 1, (
        "the closure has to be able to say what was checked BEYOND the pinned set — and, by "
        "difference, what nothing reached (FM-3 named, not closed)")
    e.stop()


def test_the_digest_is_a_function_of_the_procedure_alone():
    """It is recomputable from the contract, so the stored spec of every ASSIGN reproduces it and
    no second copy has to be kept in step."""
    a = (Criteria("c", "d", check=(Probe("b", "run x", "ok"),)),)
    b = (Criteria("c", "d", check=(Probe("b", "run  x", "ok"),)),)      # whitespace only
    assert procedure_digest(a) == procedure_digest(b)
    assert procedure_digest(a) != procedure_digest(
        (Criteria("c", "d", check=(Probe("b", "run y", "ok"),)),))


def test_a_report_is_not_demoted_for_adding_the_pinned_probe():
    """The mixed shape is the NORMAL one, and it used to be punished.

    `underprobed` flips from counting probes to matching their labels the moment any probe carries
    one. A contract pins its probes in the CONTRACT's wording; the judge enumerates behaviours in
    its own and often labels nothing. So the pinned probe arrives labelled beside the judge's
    unlabelled ones, the mode flips on its presence, and the judge's own probes stop counting —
    a report demoted because evidence was ADDED. Found by two independent workers while the corpus
    was being brought onto this contract, which is how a rule that only bites in live runs gets
    caught before a live run pays for it.
    """
    e = _engine(criterion("exits_zero"))
    _delivered(e)
    c = e.get_task("root").spec.criteria[0]
    out = e.record_exec_verdict(
        "root", "PASS", [], "judge",
        per_criterion=[{"criterion": "exits_zero", "verdict": "pass", "evidence": "ran both",
                        "behaviours": ["the binary exits zero", "it prints the count"],
                        "probe": [{"command": c.check[0].command, "expect": "it holds",
                                   "behaviour": c.check[0].behaviour},        # pinned, labelled
                                  {"command": "./x t.txt", "expect": "3"},    # judge's, unlabelled
                                  {"command": "./x t.txt; echo $?", "expect": "0"}]}])
    assert out["verdict"] == "PASS"
    e.stop()


def test_a_refutation_orphaned_by_a_plan_repair_is_named_not_lost():
    """Renaming a criterion used to retire its refutation in silence.

    The regression set is keyed by criterion NAME, and repairing the plan after a FAIL — renaming
    or replacing the criterion — is a normal path here, not a corner. The obligation to re-run what
    contact found then matched nothing, was demanded of nobody, and the node could pass over a
    repair no one re-observed. It cannot be enforced against a criterion that no longer exists (the
    contract legitimately moved), so it is SAID: named in the closure as residue, beside the
    behaviour outside the pinned set. Found by an outside reviewer the day this landed.
    """
    e = _engine(criterion("exits_zero"))
    _delivered(e)
    e.record_exec_verdict("root", "FAIL", ["exits_zero"], "judge",
                          per_criterion=[{"criterion": "exits_zero", "verdict": "fail",
                                          "evidence": "it exits 1",
                                          "probe": [{"behaviour": "exit code", "command": "./x; echo $?",
                                                     "expect": "0"}]}])
    T.edit_criteria(e, "root", [criterion("exit_status")], agent="me")   # the plan repair renames it
    e.wait_idle()
    orphans = orphaned_regression(e.get_task("root").spec.criteria, e.regression_probes("root"))
    assert "exits_zero" in orphans, "the refutation was retired by a rename, in silence"
    e.stop()


def test_a_procedure_that_cannot_fail_is_named_and_does_not_refuse():
    """`echo ok` satisfies "a criterion carries its check" and decides nothing.

    Whether a probe can SEE a divergence is FM-3, and §13.6 is explicit that no structural check
    guards it — one that claimed to would be the false green one level up. So the floor is SAID,
    not enforced: the check still passes, and the node says out loud that these commands emit a
    constant and cannot come out false, so a criterion they decide forbids nothing (§2.1).
    """
    e = _engine({"name": "c1", "description": "the compiler matches gcc",
                 "check": [{"behaviour": "it works", "command": "echo ok", "expect": "ok"}]})
    said = [c for c in T.get_checks(e, "root") if c["check"] == "A1:procedure"][0]
    assert said["verdict"] in ("met", "met_vacuously"), "sensitivity is FM-3 — it must not refuse"
    assert "cannot come out false" in (said.get("details") or ""), (
        "a hollow procedure passed as coverage with nothing said about it")
    assert T.signal(e, "root", "ACCEPT", "me").get("accepted") is True
    e.stop()


def test_a_report_cannot_buy_coverage_with_junk_probes():
    """Padding the report with unlabelled probes used to forgive named behaviours by list order.

    The mixed-label repair (a pinned probe arrives labelled beside the judge's unlabelled ones)
    over-corrected from "unlabelled probes count for nothing" to "they count for anything": three
    `echo ok` probes bought a clean report on a criterion naming three behaviours and probing one.
    Forgiveness is now bounded by the bar the unlabelled arm always used — cardinality.
    """
    e = _engine(criterion("exits_zero"))
    _delivered(e)
    c = e.get_task("root").spec.criteria[0]
    with pytest.raises(ValueError) as ex:
        e.record_exec_verdict(
            "root", "PASS", [], "judge",
            per_criterion=[{"criterion": "exits_zero", "verdict": "pass", "evidence": "ran it",
                            "behaviours": ["exits zero", "prints the count", "reads stdin"],
                            "probe": [{"command": c.check[0].command, "expect": "it holds",
                                       "behaviour": c.check[0].behaviour},
                                      # THREE of them — the count the first bound forgave. A test
                                      # that sends one is weaker than the finding it commemorates,
                                      # and this one was: the padding attack was reproduced through
                                      # the real door at three while the test passed at one.
                                      {"command": "echo ok", "expect": "ok"},
                                      {"command": "echo ok2", "expect": "ok2"},
                                      {"command": "echo ok3", "expect": "ok3"}]}])
    assert "NOT OBSERVED" in str(ex.value) or "never observed" in str(ex.value)
    e.stop()


def _narrowed_and_delivered(e):
    """A node whose claim shrank after it was authored: an exclusion added, then the work done."""
    T.edit_accepted_risks(e, "root", [
        {"item": "vector types are not implemented", "predictability": "EXTRAORDINARY",
         "justification": "out of the goal", "invalidation_condition": "the goal names them"}],
        agent="me")
    e.wait_idle()
    _delivered(e)
    return e.get_task("root").spec.criteria[0]


def test_a_narrowing_after_authoring_is_named_on_the_node():
    """Narrowing is the ISSUER's right and is never forbidden — the existing machinery is the one
    that carries it: an edit is a re-ASSIGN the executor re-consents to, and it stales the Level-2
    review so the changed plan is checked again. What was missing was only the RECORD the author
    asked for: the claim as AUTHORED, kept beside the claim as it stands, so a narrowing is a fact
    on the node instead of an archaeology exercise over the log."""
    e = _engine(criterion("exits_zero"))
    c = _narrowed_and_delivered(e)
    e.record_exec_verdict(
        "root", "PASS", [], "judge",
        per_criterion=[{"criterion": "exits_zero", "verdict": "pass",
                        "evidence": "ran it; the added exclusion of vector types is outside the "
                                    "goal as stated and does not bear on this criterion",
                        "probe": [{"command": c.check[0].command, "expect": "it holds",
                                   "behaviour": c.check[0].behaviour}]}])
    assert T.signal(e, "root", "PASS", "me").get("accepted") is True
    cb = (e.closure_of("root") or {}).get("checked_by") or {}
    assert cb.get("claim_moved_since_authoring") is True
    assert "vector types" in str(cb.get("narrowed_after_authoring")), (
        "a flag that does not say WHICH exclusion was added sends the reader to another verb; "
        "a green node is read where it stands")
    e.stop()
