"""A criterion that states an intention decides nothing, and a PASS then means whatever the validator felt like checking.

Measured on `c_compiler` (2026-09-19/20). The root criterion read "for ANY accepted program the
compiler's output matches gcc" — a text quantified over an infinite domain, so nothing about it
returns pass/fail in finite time. The engine admitted it, and the procedure was supplied later, by
whoever validated, out of their own head, differently each round: `invariants.underprobed` asks only
that every behaviour the REPORT names carries a probe, which a validator satisfies by naming three
behaviours and probing three. The root closed DONE/PASS by an independent validator, and 205 probes
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

from pathlib import PurePosixPath

import pytest

import gfso.tools as T
from gfso.packets import _executor_packet, _validator_packet
from gfso.core.protocol.procedure import (claim_digest, laid, orphaned_regression, probe_id, procedure_digest, tokenized,
                                          unrun_regression, without_pinned_runs)
from gfso.core.types import AgentId, Criteria, Probe, Signal, SignalData, Spec, TaskId, register_of
from tests.support import REGISTER, UNMODELLED_FAULT, criterion, make_engine, DENIAL_ENTRY

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY", "justification": "no precedent", "invalidation_condition": "one occurs", "p": 0.01, "impact": "the run stops and is resumed"}, DENIAL_ENTRY]


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


def _engine_holding(*criteria):
    """A node whose criteria pin no procedure, put into the graph BEHIND the admission gate.

    Since v4.1 the gate sits on the ISSUER's ASSIGN (§14.4 conformance: a refusal must be liftable
    by the refused party's own moves, and the executor cannot author the contract he is offered), so
    this state is no longer reachable through a door — it is what a row written by an older build
    looks like when it is read back. The structural check still has to name it."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("placeholder")],
                              "accepted_risks": _RISK}, assignee="me")
    e.wait_idle()
    t = e._graph.get_task("root")
    t.spec = Spec(t.spec.description, tuple(
        Criteria(c["name"], c.get("description", ""),
                 check=tuple(Probe.of(p) for p in (c.get("check") or ())))
        for c in criteria), accepted_risks=t.spec.accepted_risks)
    e._graph.save_task(t)
    e._recompute_checks("root")
    return e


def _intention(name="matches_gcc"):
    """The real shape: a criterion whose text quantifies over what nobody can enumerate."""
    return {"name": name, "description": "for ANY accepted program the output matches gcc"}


# === the contract ===

def test_a_criterion_without_a_procedure_is_a_named_hole():
    e = _engine_holding(_intention())
    holes = [h["check"] for h in T.list_holes(e)["holes"]]
    assert "A1:procedure" in holes, "an intention passed for a criterion and nothing said so"
    e.stop()


def test_the_hole_names_the_criterion_and_the_way_out():
    e = _engine_holding(_intention(), criterion("exits_zero"))
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
    e = _engine_holding({"name": "c", "description": "it works",
                         "check": [{"behaviour": "it works", "command": "", "expect": "ok"}]})
    assert "A1:procedure" in [h["check"] for h in T.list_holes(e)["holes"]]
    e.stop()


# === the gate: the procedure is fixed BEFORE the work ===

def test_the_contract_is_not_admitted_until_it_carries_its_procedure():
    """The gate is the ISSUER's, at ASSIGN (§14.4 conformance): the party refused is the party who
    can lift the refusal by his own move. It used to refuse the EXECUTOR's ACCEPT — the same demand
    addressed to the one party who cannot author the contract he was handed."""
    e = make_engine()
    e.start()
    out = T.create_task(e, "root", {"description": "goal", "criteria": [_intention()],
                                    "accepted_risks": _RISK}, assignee="me")
    assert "pin no check" in str(out).lower(), out
    assert e.graph.get_task("root") is None, "a contract nothing can decide entered the graph"
    e.stop()


def test_the_same_contract_is_admitted_once_the_procedure_is_written():
    """The control — the gate must be about the procedure, not about refusing everything."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "accepted_risks": _RISK,
                              "criteria": [dict(_intention(), check=[
                                  {"behaviour": "hello world compiles and runs",
                                   "command": "T=$(mktemp -d); ./mycc t/hello.c -o $T/h && $T/h",
                                   "expect": "hello"}])]}, assignee="me")
    e.wait_idle()
    assert e.graph.get_task("root") is not None
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
        e.record_exec_verdict("root", "PASS", [], "validator",
                              per_criterion=[{"criterion": "exits_zero", "verdict": "pass",
                                              "evidence": "looked at it, seems fine"}])
    assert "PINS" in str(ex.value) and "exits_zero" in str(ex.value)
    e.stop()


def test_the_same_pass_stands_when_the_pinned_probe_was_run():
    e = _engine(criterion("exits_zero"))
    _delivered(e)
    c = e.graph.get_task("root").spec.criteria[0]
    out = e.record_exec_verdict(
        "root", "PASS", [], "validator",
        per_criterion=[{"criterion": "exits_zero", "verdict": "pass", "evidence": "ran it",
                        "probe": [{"id": probe_id(c.name, c.check[0]),
                                   "behaviour": c.check[0].behaviour,
                                   "command": c.check[0].command, "expect": c.check[0].expect}]}])
    assert out["verdict"] == "PASS"
    e.stop()


def test_a_pinned_probe_cited_by_its_hash_under_its_criterion_counts_as_run():
    """The hash names the probe; the criterion is the entry it is reported under. Measured 2026-09-27: a
    validator ran every pinned probe of a root, cited them as `568a2aaa`, rewrote the commands onto one
    line — and the report was refused as "the procedure was not run", then paid again on Opus."""
    e = _engine(criterion("exits_zero"))
    _delivered(e)
    c = e.graph.get_task("root").spec.criteria[0]
    bare = probe_id(c.name, c.check[0]).split("#", 1)[1]
    out = e.record_exec_verdict(
        "root", "PASS", [], "validator",
        per_criterion=[{"criterion": "exits_zero", "verdict": "pass", "evidence": "ran it",
                        "probe": [{"id": bare, "behaviour": c.check[0].behaviour,
                                   "command": c.check[0].command + "  # reformatted", "expect": "it holds"}]}])
    assert out["verdict"] == "PASS"
    e.stop()


def test_a_once_refuting_probe_cited_by_its_hash_counts_as_re_run():
    """The regression set is shown to the validator in the same `crit#hash` form as the pinned probes,
    so it reads the bare hash the same way — else a rework round refuses what the first round accepted."""
    reg = {"exits_zero": [{"id": "exits_zero#1a2b3c4d", "command": "run it"}]}
    ran = [{"criterion": "exits_zero", "verdict": "pass", "probe": [{"id": "1a2b3c4d", "command": "run  it"}]}]
    assert unrun_regression(reg, ran) == {}
    assert unrun_regression(reg, [dict(ran[0], probe=[{"id": "ffffffff", "command": "other"}])])


def test_a_hash_from_another_criterion_does_not_count_as_this_ones_probe():
    e = _engine(criterion("exits_zero"), criterion("prints_help"))
    _delivered(e)
    a, b = e.graph.get_task("root").spec.criteria
    with pytest.raises(ValueError) as ex:
        e.record_exec_verdict(
            "root", "PASS", [], "validator",
            per_criterion=[{"criterion": a.name, "verdict": "pass", "evidence": "ran it",
                            "probe": [{"id": probe_id(b.name, b.check[0]).split("#", 1)[1],
                                       "behaviour": a.check[0].behaviour, "command": "true  # other",
                                       "expect": "it holds"}]},
                           {"criterion": b.name, "verdict": "pass", "evidence": "ran it",
                            "probe": [{"id": probe_id(b.name, b.check[0]), "behaviour": b.check[0].behaviour,
                                       "command": b.check[0].command, "expect": b.check[0].expect}]}])
    assert "PINS" in str(ex.value) and a.name in str(ex.value)
    e.stop()


def test_a_report_that_quotes_the_command_counts_as_having_run_it():
    """Matching by id is a convenience; the command is the identity. A rule that forced ids would
    teach a validator to paste ids instead of running commands — the fabrication this all exists against."""
    e = _engine(criterion("exits_zero"))
    _delivered(e)
    c = e.graph.get_task("root").spec.criteria[0]
    out = e.record_exec_verdict(
        "root", "PASS", [], "validator",
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
        "root", "FAIL", ["exits_zero"], "validator",
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
    e.record_exec_verdict("root", "FAIL", ["exits_zero"], "validator",
                          per_criterion=[{"criterion": "exits_zero", "verdict": "fail",
                                          "evidence": "it exits 1",
                                          "probe": [{"behaviour": "exit code on an empty file",
                                                     "command": "./x empty.c; echo $?",
                                                     "expect": "0"}]}])
    assert "exits_zero" in e.regression_probes("root"), "what contact found was thrown away"
    c = e.graph.get_task("root").spec.criteria[0]
    with pytest.raises(ValueError) as ex:
        e.record_exec_verdict(
            "root", "PASS", [], "validator",
            per_criterion=[{"criterion": "exits_zero", "verdict": "pass", "evidence": "fixed",
                            "probe": [{"command": c.check[0].command, "expect": "it holds",
                                       "behaviour": c.check[0].behaviour}]}])
    assert "REFUTED" in str(ex.value)
    e.stop()


def test_the_pinned_contract_is_not_rewritten_behind_the_executor():
    """The regression set is the NODE's history, not the criterion's text: growing the contract at
    validation time would move it under the executor, which is exactly what Inv-1 forbids. Promotion
    into the contract stays the issuer's act."""
    e = _engine(criterion("exits_zero"))
    _delivered(e)
    before = procedure_digest(e.graph.get_task("root").spec.criteria)
    e.record_exec_verdict("root", "FAIL", ["exits_zero"], "validator",
                          per_criterion=[{"criterion": "exits_zero", "verdict": "fail",
                                          "evidence": "no", "probe": [{"behaviour": "b",
                                                                       "command": "./x", "expect": "0"}]}])
    assert procedure_digest(e.graph.get_task("root").spec.criteria) == before
    e.stop()


# === the record says what it reached ===

def test_the_verdict_records_the_procedure_it_ran_and_how_far_it_went():
    e = _engine(criterion("exits_zero"))
    _delivered(e)
    c = e.graph.get_task("root").spec.criteria[0]
    e.record_exec_verdict(
        "root", "PASS", [], "validator",
        per_criterion=[{"criterion": "exits_zero", "verdict": "pass", "evidence": "ran both",
                        "probe": [{"command": c.check[0].command, "expect": "it holds",
                                   "behaviour": c.check[0].behaviour},
                                  {"command": "./x weird.c", "expect": "0",
                                   "behaviour": "my own exploration"}]}])
    rec = e.get_exec_verdict("root")
    assert rec["procedure_digest"] == procedure_digest(e.graph.get_task("root").spec.criteria)
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
    one. A contract pins its probes in the CONTRACT's wording; the validator enumerates behaviours in
    its own and often labels nothing. So the pinned probe arrives labelled beside the validator's
    unlabelled ones, the mode flips on its presence, and the validator's own probes stop counting —
    a report demoted because evidence was ADDED. Found by two independent workers while the corpus
    was being brought onto this contract, which is how a rule that only bites in live runs gets
    caught before a live run pays for it.
    """
    e = _engine(criterion("exits_zero"))
    _delivered(e)
    c = e.graph.get_task("root").spec.criteria[0]
    out = e.record_exec_verdict(
        "root", "PASS", [], "validator",
        per_criterion=[{"criterion": "exits_zero", "verdict": "pass", "evidence": "ran both",
                        "behaviours": ["the binary exits zero", "it prints the count"],
                        "probe": [{"command": c.check[0].command, "expect": "it holds",
                                   "behaviour": c.check[0].behaviour},        # pinned, labelled
                                  {"command": "./x t.txt", "expect": "3"},    # validator's, unlabelled
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
    e.record_exec_verdict("root", "FAIL", ["exits_zero"], "validator",
                          per_criterion=[{"criterion": "exits_zero", "verdict": "fail",
                                          "evidence": "it exits 1",
                                          "probe": [{"behaviour": "exit code", "command": "./x; echo $?",
                                                     "expect": "0"}]}])
    T.edit_criteria(e, "root", [criterion("exit_status")], agent="me")   # the plan repair renames it
    e.wait_idle()
    orphans = orphaned_regression(e.graph.get_task("root").spec.criteria, e.regression_probes("root"))
    assert "exits_zero" in orphans, "the refutation was retired by a rename, in silence"
    e.stop()


def test_a_procedure_that_cannot_fail_is_refused_and_a_constant_beside_a_real_probe_is_named():
    """`echo ok` as a criterion's whole procedure: its fail-extension is empty, FORM decidable on the literal command
    (§9.6, §20.10), refused at admission. Beside a probe that runs the work it is only said — whether that one can SEE a
    divergence is FM-3, which no structural check guards (§9.10)."""
    hollow = {"behaviour": "it works", "command": "echo ok", "expect": "ok"}
    e = _engine({"name": "c1", "description": "the compiler matches gcc", "check": [hollow]})
    assert e.graph.get_task(TaskId("root")) is None, "a goal over a hollow procedure was created"
    e.stop()
    e = _engine({"name": "c1", "description": "the compiler matches gcc",
                 "check": [hollow, {"behaviour": "it builds", "command": "make -q all; echo exit=$?", "expect": "exit=0"}]})
    said = [c for c in T.get_checks(e, "root") if c["check"] == "A1:procedure"][0]
    assert said["verdict"] in ("met", "met_vacuously") and "cannot come out false" in (said.get("details") or "")
    assert T.signal(e, "root", "ACCEPT", "me").get("accepted") is True
    e.stop()


def test_a_report_cannot_buy_coverage_with_junk_probes():
    """Padding the report with unlabelled probes used to forgive named behaviours by list order.

    The mixed-label repair (a pinned probe arrives labelled beside the validator's unlabelled ones)
    over-corrected from "unlabelled probes count for nothing" to "they count for anything": three
    `echo ok` probes bought a clean report on a criterion naming three behaviours and probing one.
    Forgiveness is now bounded by the bar the unlabelled arm always used — cardinality.

    The label rule governs a criterion that pins NO procedure (a `dep__*` seam, a row from an older build): one that
    pins one stands on it, run whole, and what the report names past it is exploration
    (`test_a_criterion_stands_on_its_pinned_procedure`).
    """
    e = _engine_holding({"name": "exits_zero", "description": "it exits zero"})
    _delivered(e)
    with pytest.raises(ValueError) as ex:
        e.record_exec_verdict(
            "root", "PASS", [], "validator",
            per_criterion=[{"criterion": "exits_zero", "verdict": "pass", "evidence": "ran it",
                            "behaviours": ["exits zero", "prints the count", "reads stdin"],
                            "probe": [{"command": "run it; echo exit=$?", "expect": "exit=0",
                                       "behaviour": "exits zero"},
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
    return e.graph.get_task("root").spec.criteria[0]


def test_a_narrowing_after_authoring_is_named_on_the_node():
    """Narrowing is the ISSUER's right and is never forbidden — the existing machinery is the one
    that carries it: an edit is a re-ASSIGN the executor re-consents to, and it stales the Level-2
    review so the changed plan is checked again. What was missing was only the RECORD the author
    asked for: the claim as AUTHORED, kept beside the claim as it stands, so a narrowing is a fact
    on the node instead of an archaeology exercise over the log."""
    e = _engine(criterion("exits_zero"))
    c = _narrowed_and_delivered(e)
    e.record_exec_verdict(
        "root", "PASS", [], "validator",
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


def test_an_untouched_pre_fill_is_no_movement_of_the_claim():
    """The node's packet carries its issuer's pre-fill and it has no split: nothing moved. Read at authoring off the
    packet and now off the split's register (empty), the pre-fill read as dropped and the claim as moved — a false
    flag on every leaf with a pre-fill once the register stopped falling back to the packet (§9.2)."""
    e = _engine(criterion("exits_zero"))
    drift = e.claim_drift(TaskId("root"))
    assert drift["risks_dropped"] == [] and drift["risks_added"] == [] and drift["narrowed"] is False, drift
    assert e._authoring_digest(TaskId("root")) == claim_digest(e.graph.get_task("root").spec,
                                                               register_of(e.graph.get_task("root")))
    e.stop()


def test_a_criterion_rewritten_after_it_was_refuted_leaves_the_narrowing_undecided():
    """Whether new wording is sharper or looser is not decidable from structure, so a criterion
    rewritten after a FAIL named it cannot be reported as "not narrowed". Measured on `json_parser`
    (2026-09-21): FAILed on "ValueError", rewritten to "TypeError or ValueError" as a spec defect,
    and `claim_drift` said `narrowed: false`. The same rewording with no refutation stays False."""
    def _reworded(refute: bool):
        e = _engine(criterion("exits_zero"))
        _delivered(e)
        if refute:
            e.record_exec_verdict("root", "FAIL", ["exits_zero"], "validator",
                                  per_criterion=[{"criterion": "exits_zero", "verdict": "fail",
                                                  "evidence": "it exits 1",
                                                  "probe": [{"behaviour": "exit code",
                                                             "command": "./x; echo $?",
                                                             "expect": "0"}]}])
            T.signal(e, "root", "FAIL", "me", failed_criteria=["exits_zero"])
            e.wait_idle()
        T.edit_criteria(e, "root", [criterion("exits_zero", "exits zero or one")], agent="me",
                        reason="spec_defect")
        e.wait_idle()
        d = e.claim_drift("root")
        e.stop()
        return d
    after_fail = _reworded(True)
    assert after_fail["reworded_after_refutation"] == ["exits_zero"]
    assert after_fail["narrowed"] is None, "a rewrite after a refutation was reported as a green"
    plain = _reworded(False)
    assert plain["reworded_after_refutation"] == [] and plain["narrowed"] is False


def test_the_narrowing_is_undecided_on_every_door_a_refutation_arrives_by():
    """Three shapes the first version got wrong, each found by an outside reviewer running it:
    a refutation recorded as a verdict alone (`validate_result` sends no signal and the issuer may
    revise straight out of VALIDATING) · a loosened `expect` with the command unchanged · and the
    converse — a rewrite made BEFORE the refutation, followed by a re-ASSIGN that copies it, which
    is no rewrite after anything and must not be reported as one."""
    def _fail_by_verdict(e):
        e.record_exec_verdict("root", "FAIL", ["exits_zero"], "validator",
                              per_criterion=[{"criterion": "exits_zero", "verdict": "fail",
                                              "evidence": "it exits 1",
                                              "probe": [{"behaviour": "exit code",
                                                         "command": "./x; echo $?", "expect": "0"}]}])

    e = _engine(criterion("exits_zero"))
    _delivered(e)
    _fail_by_verdict(e)                                    # no FSM FAIL: the node stays VALIDATING
    T.edit_criteria(e, "root", [criterion("exits_zero", "exits zero or one")], agent="me",
                    reason="spec_defect")
    e.wait_idle()
    d = e.claim_drift("root")
    assert d["reworded_after_refutation"] == ["exits_zero"] and d["narrowed"] is None
    # …and the ordinary loop after it — rework, a second FAIL, this time signalled — must not
    # launder the first refutation: it validated the old wording, and that wording is gone.
    _delivered(e)
    _fail_by_verdict(e)
    T.signal(e, "root", "FAIL", "me", failed_criteria=["exits_zero"])
    e.wait_idle()
    assert e.claim_drift("root")["narrowed"] is None, "a later FAIL hid the earlier refutation"
    e.stop()

    # A rewrite made before any work, then a refutation of the rewritten text: nothing moved after.
    e = _engine(criterion("exits_zero"))
    T.edit_criteria(e, "root", [criterion("exits_zero", "exits zero or one")], agent="me")
    e.wait_idle()
    _delivered(e)
    _fail_by_verdict(e)
    d = e.claim_drift("root")
    assert d["reworded_after_refutation"] == [] and d["narrowed"] is False
    e.stop()

    e = _engine(criterion("exits_zero"))
    _delivered(e)
    _fail_by_verdict(e)
    T.signal(e, "root", "FAIL", "me", failed_criteria=["exits_zero"])
    e.wait_idle()
    loose = criterion("exits_zero")
    loose["check"] = [dict(loose["check"][0], expect="it holds, or nearly")]
    T.edit_criteria(e, "root", [loose], agent="me", reason="spec_defect")
    e.wait_idle()
    d = e.claim_drift("root")
    assert d["reworded_after_refutation"] == ["exits_zero"] and d["narrowed"] is None, (
        "a loosened expectation under an unchanged command was reported as no narrowing")
    e.stop()

    e = _engine(criterion("exits_zero"))
    T.edit_criteria(e, "root", [criterion("exits_zero", "exits zero or one")], agent="me")
    e.wait_idle()
    _delivered(e)
    T.signal(e, "root", "FAIL", "me", failed_criteria=["exits_zero"])
    e.wait_idle()
    T.revise(e, "root", max_iterations=9, agent="me")     # a re-ASSIGN that copies the contract
    e.wait_idle()
    d = e.claim_drift("root")
    assert d["reworded_after_refutation"] == [], "a rewrite before the refutation was dated after it"
    e.stop()


def test_a_verdict_records_the_version_it_validated_not_the_one_standing_when_it_lands():
    """A validation runs for minutes and `edit_criteria` is accepted while the node is VALIDATING,
    so the spec can move between the DELIVER and the verdict. The refuted version is the one the
    delivery was validated against; recording the new one named a refutation nobody made."""
    e = _engine(criterion("exits_zero"))
    _delivered(e)
    g = e.graph.generation_of("root")
    T.edit_criteria(e, "root", [criterion("exits_zero", "v2 text")], agent="me")
    e.wait_idle()
    e.record_exec_verdict("root", "FAIL", ["exits_zero"], "validator", generation=g,
                          per_criterion=[{"criterion": "exits_zero", "verdict": "fail",
                                          "evidence": "it exits 1",
                                          "probe": [{"behaviour": "exit code",
                                                     "command": "./x; echo $?", "expect": "0"}]}])
    d = e.claim_drift("root")
    assert d["reworded_after_refutation"] == ["exits_zero"] and d["narrowed"] is None, (
        "the validated wording is gone and the report did not say so")
    e.stop()



def _seam_with_pinned(bad):
    """A child `exec-1` executes and `me` issues — a seam — its criterion pinning `bad`, delivered."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g")], "accepted_risks": _RISK},
                  assignee="me")
    T.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "part", "criteria": [criterion("conf", check=[bad])]}, "assignee": "exec-1", "covers": ["g"]}], accepted_risks=REGISTER)
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "me")
    T.signal(e, "kid", "ACCEPT", "exec-1")
    T.signal(e, "kid", "DELIVER", "exec-1", result="built it")
    e.wait_idle()
    return e


def _refuted(e, tid, pinned_run, own="python -m jp {d}/deep.json", dirs=()):
    e.record_exec_verdict(tid, "FAIL", ["conf"], "validator", inputs_dirs=dirs, per_criterion=[{
        "criterion": "conf", "verdict": "fail", "evidence": "ModuleNotFoundError",
        "probe": [{"behaviour": "escapes", "expect": "OK", "command": pinned_run},
                  {"behaviour": "deep nesting", "command": own, "expect": "ValueError"}]}])


_BAD = {"behaviour": "escapes", "command": "python {inputs}/t.py", "expect": "OK",
        "inputs": [["t.py", "import json"]]}


def _laid(pid):
    return f"C:/x/.gfso-scratch-ws/kid_1/probe_inputs/{pid.replace('#', '_')}"


def test_at_a_seam_the_issuer_s_accepted_challenge_withdraws_the_pinned_run_and_the_validator_s_own_finding_stays():
    """Kept, the withdrawn command failed the node on every later round and the accepted challenge came back
    in a loop (automatic json_parser, 2026-09-28). A finding of the validator's own stays — even one whose
    command reads a file in the withdrawn probe's inputs directory."""
    e = _seam_with_pinned(_BAD)
    pid = probe_id("conf", Probe.of(_BAD))
    _refuted(e, "kid", f"python {_laid(pid)}/t.py", own=f"python -m jp {_laid(pid)}/deep.json",
             dirs=((pid, _laid(pid)),))
    T.signal(e, "kid", "FAIL", "me", failed_criteria=["conf"])
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason="the probe's script cannot import the module it tests")
    t = e.graph.get_task("kid")
    good = Probe.of({"behaviour": "escapes", "command": "python -c 'escapes()'", "expect": "OK"})
    entry = e.send_signal_sync(SignalData(signal=Signal.ACCEPT_CHALLENGE, task_id=TaskId("kid"), source=AgentId("me"),
                                          new_spec=Spec(t.spec.description, (Criteria("conf", "c", check=(good,)),))))
    assert entry is not None and not entry.rejected, entry and entry.error
    assert [p["as_run"] for p in e.regression_probes("kid")["conf"]] == ["python -m jp {inputs:" + pid + "}/deep.json"]
    e.stop()


def test_a_holder_who_issues_his_own_node_lifts_a_withdrawn_probe_s_refutation_and_the_record_says_so():
    """Where the issuer is the executor, revising his own procedure is his lift (§14.4 (ii)); kept, the withdrawn
    probe's run refused every later PASS. The move is not silent: claim_drift names the criterion."""
    e = _engine(criterion("conf", check=[_BAD]))
    _delivered(e)
    pid = probe_id("conf", Probe.of(_BAD))
    _refuted(e, "root", f"python {_laid(pid)}/t.py", dirs=((pid, _laid(pid)),))
    T.signal(e, "root", "FAIL", "me", failed_criteria=["conf"])
    T.signal(e, "root", "CHALLENGE", "me", reason="I would rather check something else")
    t = e.graph.get_task("root")
    ok = Probe.of({"behaviour": "escapes", "command": "test -d . && echo ok", "expect": "ok"})
    e.send_signal_sync(SignalData(signal=Signal.ACCEPT_CHALLENGE, task_id=TaskId("root"), source=AgentId("me"),
                                  new_spec=Spec(t.spec.description, (Criteria("conf", "c", check=(ok,)),),
                                                accepted_risks=t.spec.accepted_risks)))
    assert [p["command"] for p in e.regression_probes("root")["conf"]] == ["python -m jp {d}/deep.json"]
    assert "conf" in e.claim_drift(TaskId("root"))["reworded_after_refutation"]
    e.stop()


def test_a_regression_line_is_shown_runnable_this_round_and_re_run_by_command_or_id(tmp_path):
    """The round's inputs directory is laid down fresh each time and the store collapsed a program onto one line,
    so the command a FAIL recorded could not be run as shown the next round: the validator ran its own version,
    no command matched, and one PASS was refused three times (automatic json_parser, 2026-09-28). The directory
    is now named in the stored command and laid down again at display, and the command shown matches."""
    e = _seam_with_pinned(_BAD)
    pid = probe_id("conf", Probe.of(_BAD))
    old, new = tmp_path / "r1", tmp_path / "r2"
    d_old = (old / "probe_inputs" / pid.replace("#", "_"))
    d_old.mkdir(parents=True)
    own = f'cd ws && PYTHONPATH=. python "{d_old.as_posix()}/t.py"\necho done'
    e.record_exec_verdict("kid", "FAIL", ["conf"], "validator", inputs_dirs=((pid, d_old),), per_criterion=[{
        "criterion": "conf", "verdict": "fail", "evidence": "ModuleNotFoundError",
        "probe": [{"behaviour": "escapes", "expect": "OK", "command": own}]}])
    (stored,) = e.regression_probes("kid")["conf"]
    assert stored["as_run"] == 'cd ws && PYTHONPATH=. python "{inputs:' + pid + '}/t.py"\necho done'
    packet = _validator_packet(e, e.graph.get_task("kid"), "fixed it", None, scratch=str(new))
    d_new = new / "probe_inputs" / pid.replace("#", "_")
    shown = f'cd ws && PYTHONPATH=. python "{d_new.as_posix()}/t.py"\necho done'
    assert shown in packet and "report it under this id" in packet
    T.signal(e, "kid", "FAIL", "me", failed_criteria=["conf"])
    T.signal(e, "kid", "DELIVER", "exec-1", result="fixed it")
    e.wait_idle()
    out = e.record_exec_verdict("kid", "PASS", [], "validator", inputs_dirs=((pid, d_new),), per_criterion=[{
        "criterion": "conf", "verdict": "pass", "evidence": "holds",
        "probe": [{"behaviour": "escapes", "command": f"python {d_new.as_posix()}/t.py", "expect": "OK"},
                  {"behaviour": "escapes", "command": shown, "expect": "done"}]}])
    assert out["verdict"] == "PASS", out
    e.stop()


def test_a_retired_finding_over_laid_inputs_is_named_settled_not_ordered(tmp_path):
    """A finding over the round's laid inputs is stored with the directory as a token, so its own run in the FAIL never
    matched its retired id: the executor kept the order and disputed it eight more times (critic r5, tmsami100 #47);
    an observation the round's other probes still carry stays, and the retired id is named settled beside it."""
    e = _seam_with_pinned(_BAD)
    pid = probe_id("conf", Probe.of(_BAD))
    d = tmp_path / "r1" / "probe_inputs" / pid.replace("#", "_")
    d.mkdir(parents=True)
    own = f"python {d.as_posix()}/t.py --own"
    e.record_exec_verdict("kid", "FAIL", ["conf"], "validator", inputs_dirs=((pid, d),), per_criterion=[{
        "criterion": "conf", "verdict": "fail", "evidence": "the own run broke",
        "probe": [{"behaviour": "escapes", "expect": "OK", "command": own}]}])
    T.signal(e, "kid", "FAIL", "me", failed_criteria=["conf"])
    (fid,) = [p["id"] for p in e.regression_probes("kid")["conf"]]
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"finding {fid} is another node's")
    assert T.signal(e, "kid", "ACCEPT_CHALLENGE", "me", retire_findings=[fid], justification="it is")["accepted"]
    e.wait_idle()
    packet = _executor_packet(e, e.graph.get_task("kid"), "ws")
    assert own not in packet and "the own run broke" not in packet, packet
    e.stop()


def test_a_stored_command_names_its_round_s_directory_and_nothing_around_it():
    pid = "conf#1a2b3c4d"
    d = PurePosixPath("C:/Users/John Smith/w/.s/k_1/probe_inputs/conf_1a2b3c4d")
    cmd = f'PYTHONPATH="C:/e3/ws" python "{d}/t.py" < {d}/in.json'
    named = tokenized(cmd, ((pid, d),))
    assert named == 'PYTHONPATH="C:/e3/ws" python "{inputs:conf#1a2b3c4d}/t.py" < {inputs:conf#1a2b3c4d}/in.json'
    assert laid(named, {pid: "D:/n"}) == 'PYTHONPATH="C:/e3/ws" python "D:/n/t.py" < D:/n/in.json'


def test_another_criterion_s_withdrawn_probe_does_not_take_this_one_s_finding():
    reg = {"api_errors": [{"id": "api_errors#aa", "command": "python -m pytest -q"}]}
    assert without_pinned_runs(reg, {"perf#bb": "python -m pytest -q"}) == reg


def test_a_pinned_probe_s_refuting_run_is_demanded_once_as_the_pinned_probe(tmp_path):
    """One probe entry carries one id. A pinned probe's refuting run stored under an id of its own was a second
    demand beside the pinned one that no report could meet (one pass refused three times, 2026-09-28): the
    regression set holds the validator's own findings, and the pinned probe is demanded as itself."""
    e = _seam_with_pinned(_BAD)
    pid = probe_id("conf", Probe.of(_BAD))
    d1 = tmp_path / "r1" / "probe_inputs" / pid.replace("#", "_")
    e.record_exec_verdict("kid", "FAIL", ["conf"], "validator", inputs_dirs=((pid, d1),), per_criterion=[{
        "criterion": "conf", "verdict": "fail", "evidence": "ModuleNotFoundError",
        "probe": [{"id": pid.split("#")[1], "behaviour": "escapes", "expect": "OK",
                   "command": f"python {d1.as_posix()}/t.py"}]}])
    assert e.regression_probes("kid").get("conf", []) == []
    assert e.rework_findings("kid")[0][2] == [f"python {d1.as_posix()}/t.py"]   # the executor sees it as run
    T.signal(e, "kid", "FAIL", "me", failed_criteria=["conf"])
    T.signal(e, "kid", "DELIVER", "exec-1", result="fixed it")
    e.wait_idle()
    d2 = tmp_path / "r2" / "probe_inputs" / pid.replace("#", "_")
    out = e.record_exec_verdict("kid", "PASS", [], "validator", inputs_dirs=((pid, d2),), per_criterion=[{
        "criterion": "conf", "verdict": "pass", "evidence": "holds",
        "probe": [{"id": pid.split("#")[1], "behaviour": "escapes", "command": f'python "{d2.as_posix()}/t.py"',
                   "expect": "OK"}]}])
    assert out["verdict"] == "PASS", out
    e.stop()


def test_a_finding_over_a_withdrawn_probe_s_inputs_is_shown_not_demanded(tmp_path):
    """Its files are not laid down any more, so it cannot be re-run as recorded — a FAIL on "no such file"
    would stand on nothing the current contract faults (§14.4 (ii))."""
    reg = {"conf": [{"id": "conf#aa", "command": "x", "as_run": "python -m jp {inputs:conf#gone}/deep.json"}]}
    ran = [{"criterion": "conf", "verdict": "pass", "probe": [{"command": "other", "expect": "ok"}]}]
    assert unrun_regression(reg, ran, layable={"conf#here"}) == {}
    assert unrun_regression(reg, ran, layable={"conf#gone"}) == {"conf": ["conf#aa"]}


def test_two_probes_of_one_criterion_on_one_command_are_refused_at_admission():
    """A probe is named by its command: the second would be laid down over the first and never run."""
    twin = [{"behaviour": "a", "command": "python {inputs}/p.py", "expect": "ok", "inputs": [["p.py", "A"]]},
            {"behaviour": "b", "command": "python {inputs}/p.py", "expect": "ok", "inputs": [["p.py", "B"]]}]
    e = make_engine()
    e.start()
    out = T.create_task(e, "root", {"description": "goal", "criteria": [criterion("conf", check=twin)],
                                    "accepted_risks": _RISK}, assignee="me")
    assert "two probes of one criterion run one command" in out.get("error", "")
    assert e.graph.get_task("root") is None
    e.stop()


def test_the_record_counts_what_the_gate_accepted_through_the_inputs_directory():
    """A pinned probe reported by its laid-down command and no id is accepted at the seam, and the stored record
    must say it ran: recorded "0 of 1" it read as a broken promise the engine had kept (GB_c_compiler_tmokgz344)."""
    e = _seam_with_pinned(_BAD)
    pid = probe_id("conf", Probe.of(_BAD))
    out = e.record_exec_verdict(
        "kid", "PASS", [], "validator", inputs_dirs=((pid, _laid(pid)),), tools_used={"Bash": 1},
        per_criterion=[{"criterion": "conf", "verdict": "pass", "evidence": "ran it",
                        "probe": [{"behaviour": "escapes", "command": f"python {_laid(pid)}/t.py", "expect": "OK"}]}])
    assert out["verdict"] == "PASS"
    assert e.get_exec_verdict("kid")["pinned_probes_run"] == 1
    e.stop()
