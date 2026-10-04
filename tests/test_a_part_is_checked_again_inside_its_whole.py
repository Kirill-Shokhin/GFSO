"""A part's PASS is a verdict on the part's own delivery; inside its whole's later delivery it is checked again.

Measured on E3 (2026-09-28), a plan run node by node. A part passed on its pinned probes. The WHOLE's executor, a
separate session, then rewrote the part's module in the shared working directory — the rewritten module raised a
plain ValueError where the part's criterion required a specific subclass. The whole's validation read only the
whole's own criteria and passed, and the root closed DONE with four held-out failures. Nothing the currency rule
reads had moved: the part was never delivered or failed again.

A whole's result is its subtree's artifact as it stands when the WHOLE is delivered (§11.3); the part's criteria
are what secure the whole's criteria mapped to it (§2.4, §4.3). So the whole's validation runs every DONE part's
pinned probes over the whole's delivery, under the criterion that part is mapped to: skipped, that criterion is ⊥;
failing, it FAILs. Parts validated in the same run as their whole — one scope's validation — are not asked twice.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.core.protocol.procedure import laid_down_dirs, probe_id
from gfso.core.types import State, TaskId
from gfso.packets import _validator_packet
from tests.support import REGISTER, UNMODELLED_FAULT, criterion, instrument_passes, make_engine, DENIAL_ENTRY
from tests.test_one_session_carries_a_scope import (_LLM, _Validator, _delivered, _dispatcher, _drive, _project)

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY", "justification": "no precedent", "invalidation_condition": "one occurs", "p": 0.01, "impact": "the run stops and is resumed"}, DENIAL_ENTRY]
_RAISES = {"behaviour": "a malformed document raises JSONParseError",
           "command": "python -c \"import json_parser as j; j.parse('{')\"", "expect": "JSONParseError"}


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _whole_delivered_over_a_passed_part(own=None, part=_RAISES):
    """`kid` executed by `exec-1` and passed on its own delivery; then its whole, `root`, is delivered."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "a JSON library", "accepted_risks": _RISK,
                              "criteria": [criterion("parses", **({"check": [own]} if own else {}))]},
                  assignee="me")
    T.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "the parser module",
                             "criteria": [criterion("errors", check=[part])]}, "assignee": "exec-1", "covers": ["parses"]}], accepted_risks=REGISTER)
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "me")
    T.signal(e, "kid", "ACCEPT", "exec-1")
    T.signal(e, "kid", "DELIVER", "exec-1", result="json_parser.py written")
    e.wait_idle()
    instrument_passes(e, "kid", "validator")
    T.signal(e, "kid", "PASS", "me")
    T.signal(e, "root", "DELIVER", "me", result="the library, json_parser.py rewritten")
    e.wait_idle()
    assert e.graph.get_state(TaskId("kid")) == State.DONE and e.graph.get_state(TaskId("root")) == State.VALIDATING
    return e


def _part_pid(e) -> str:
    c = e.graph.get_task(TaskId("kid")).spec.criteria[0]
    return probe_id(f"kid/{c.name}", c.check[0])


def _entry(e, verdict="pass", with_part=False, **part) -> dict:
    own = e.graph.get_task(TaskId("root")).spec.criteria[0].check[0]
    probes = [{"behaviour": own.behaviour, "command": own.command, "expect": own.expect}]
    if with_part:
        probes.append({"id": _part_pid(e), "behaviour": _RAISES["behaviour"], "command": _RAISES["command"],
                       "expect": _RAISES["expect"], **part})
    return {"criterion": "parses", "verdict": verdict, "behaviours": [own.behaviour, _RAISES["behaviour"]],
            "evidence": "ran both" if verdict == "pass" else "the part's probe printed ValueError",
            "probe": probes, **({"divergences": ["raises ValueError, not JSONParseError"]}
                                if verdict == "fail" else {})}


def test_the_whole_s_validator_is_handed_the_part_s_pinned_check_under_the_criterion_it_rests_on():
    e = _whole_delivered_over_a_passed_part()
    packet = _validator_packet(e, e.graph.get_task(TaskId("root")), "the library", None)
    parses = packet.split("**parses**")[1].split("\n- **")[0]
    assert f"PART’S PINNED CHECK [{_part_pid(e)}]" in parses and _RAISES["command"] in parses
    assert "report it ONCE, under this id, in the probe list of any one criterion that rests on it" in parses
    e.stop()


def test_a_whole_s_pass_that_skips_its_part_s_pinned_probe_is_not_a_verdict():
    e = _whole_delivered_over_a_passed_part()
    with pytest.raises(ValueError) as ex:
        e.record_exec_verdict("root", "PASS", [], "validator", per_criterion=[_entry(e)])
    assert _part_pid(e) in str(ex.value) and "parses" in str(ex.value)
    out = e.record_exec_verdict("root", "PASS", [], "validator", per_criterion=[_entry(e, with_part=True)])
    assert out["verdict"] == "PASS", out
    e.stop()


def test_the_part_s_probe_is_accounted_for_by_its_command_under_the_whole_s_criterion():
    e = _whole_delivered_over_a_passed_part()
    out = e.record_exec_verdict("root", "PASS", [], "validator",
                                per_criterion=[_entry(e, with_part=True, id="")])
    assert out["verdict"] == "PASS", out
    e.stop()


def test_the_part_s_probe_failing_over_the_whole_s_delivery_fails_the_whole_on_the_mapped_criterion():
    e = _whole_delivered_over_a_passed_part()
    out = e.record_exec_verdict("root", "FAIL", ["parses"], "validator",
                                per_criterion=[_entry(e, "fail", with_part=True, expect="ValueError")])
    assert out == {"verdict": "FAIL", "failed_criteria": ["parses"]}
    e.stop()


def test_a_hand_pass_on_the_whole_cites_the_part_s_probe_it_ran():
    e = _whole_delivered_over_a_passed_part()
    own = e.graph.get_task(TaskId("root")).spec.criteria[0].check[0]
    with pytest.raises(ValueError):
        e.record_reviewer_verdict("root", "PASS", [], "rev", observed={
            "parses": {"note": "ran it, it holds", "ran": [own.command]}})
    e.record_reviewer_verdict("root", "PASS", [], "rev", observed={
        "parses": {"note": "ran both, both hold", "ran": [own.command, _part_pid(e)]}})
    assert e.get_exec_verdict(TaskId("root"))["verdict"] == "PASS"
    e.stop()


def test_a_scope_validating_parts_and_whole_together_does_not_demand_the_parts_twice(tmp_path):
    e, agents = _project(tmp_path)
    validator = _Validator(e)
    d = _dispatcher(e, agents, _LLM(_delivered("root.a", "root.b", "root")), validator, [])
    _drive(e, d, lambda: e.graph.get_state(TaskId("root")) == State.DONE)
    assert len(validator.calls) == 1 and "PART’S PINNED CHECK" not in validator.packets[0]
    assert e.get_exec_verdict(TaskId("root"))["verdict"] == "PASS"
    e.stop()


def test_a_whole_reworked_beside_a_part_that_passed_in_an_earlier_run_runs_its_probes(tmp_path):
    """The whole's rework session is where a passed part's module gets rewritten — the E3 shape inside a scope. The
    consumer fails, its producer passed: the second session reworks the consumer and re-delivers the whole beside
    the producer already DONE, and the whole's validation runs the producer's pinned probe, not the consumer's,
    which is validated in the same run under its own name."""
    e, agents = _project(tmp_path)
    executor = _LLM(_delivered("root.a", "root.b", "root"), _delivered("root.b", "root"))
    validator = _Validator(e, {("root.b", "b_ok")})
    d = _dispatcher(e, agents, executor, validator, [])
    _drive(e, d, lambda: e.graph.get_state(TaskId("root")) == State.DONE)
    assert len(executor.calls) == 2 and len(validator.calls) == 2
    last = validator.packets[-1]
    assert "## Node `root.a`" not in last and "PART’S PINNED CHECK [root.a/a_ok#" in last
    assert "PART’S PINNED CHECK [root.b/b_ok#" not in last, "the part validated in the same run is not asked twice"
    assert "PART’S PINNED CHECK" not in validator.packets[0]
    e.stop()


def test_a_part_s_probe_over_its_own_inputs_is_not_met_by_the_whole_s_same_command_over_the_whole_s(tmp_path):
    """A part's probe and the whole's may pin one command over different files: each is laid down in its own
    directory, named by its own id, and a run over the whole's files does not account for the part's."""
    cmd = "python {inputs}/t.py"
    own = {"behaviour": "parses a document", "command": cmd, "expect": "OK", "inputs": [["t.py", "whole"]]}
    part = {"behaviour": "raises JSONParseError", "command": cmd, "expect": "OK", "inputs": [["t.py", "part"]]}
    e = _whole_delivered_over_a_passed_part(own, part)
    packet = _validator_packet(e, e.graph.get_task(TaskId("root")), "the library", None, scratch=str(tmp_path))
    dirs = dict(laid_down_dirs(e.validation_procedure(TaskId("root")), tmp_path))
    pid_own, pid_part = probe_id("parses", own), _part_pid(e)
    assert pid_own.split("#")[1] == pid_part.split("#")[1] and dirs[pid_own] != dirs[pid_part]
    assert (dirs[pid_part] / "t.py").read_text(encoding="utf-8") == "part"
    assert f"PART’S PINNED CHECK [{pid_part}]" in packet and dirs[pid_part].as_posix() in packet

    def ran(*pids):
        return [{"criterion": "parses", "verdict": "pass", "evidence": "ran it", "probe": [
            {"behaviour": "b", "command": f"python {dirs[i].as_posix()}/t.py", "expect": "OK"} for i in pids]}]
    with pytest.raises(ValueError) as ex:
        e.record_exec_verdict("root", "PASS", [], "validator", per_criterion=ran(pid_own),
                              inputs_dirs=tuple(dirs.items()))
    assert pid_part in str(ex.value)
    out = e.record_exec_verdict("root", "PASS", [], "validator", per_criterion=ran(pid_own, pid_part),
                                inputs_dirs=tuple(dirs.items()))
    assert out["verdict"] == "PASS", out
    e.stop()


def _refused_redelivery_after(e, entry) -> str:
    """Record `entry` as the whole's FAIL, take it into rework, and re-deliver — the refusal, or '' if admitted."""
    e.record_exec_verdict("root", "FAIL", ["parses"], "validator", per_criterion=[entry])
    T.signal(e, "root", "FAIL", "me", failed_criteria=["parses"])
    e.wait_idle()
    assert e.graph.get_state(TaskId("root")) == State.REWORKING
    out = T.signal(e, "root", "DELIVER", "me", result="the library, the part's module repaired")
    e.wait_idle()
    return "" if e.graph.get_state(TaskId("root")) == State.VALIDATING else str(out)


def test_a_whole_failed_through_its_part_s_probe_is_repaired_by_its_own_executor():
    """The whole's delivery broke a part that had passed: its children's criteria, read on the delivered result,
    do not all hold (§8.5), so this is no refuted decomposition — the whole's executor repairs and re-delivers.
    The control is the shape a validator following the packet writes when the part's probe HELD beside a failing
    probe of the whole's own: every child holds on the delivered result, the q_D pattern, and its re-delivery over
    the unchanged plan is refused (critic r1, 2026-10-04: "ran" in place of "failed" switched that refusal off)."""
    e = _whole_delivered_over_a_passed_part()
    assert _refused_redelivery_after(e, _entry(e, "fail", with_part=True, held=False)) == ""
    e.stop()
    e = _whole_delivered_over_a_passed_part()
    assert "contact refuted the DECOMPOSITION" in _refused_redelivery_after(e, _entry(e, "fail", with_part=True,
                                                                                    held=True))
    e.stop()


def test_a_part_s_failure_reported_by_its_laid_command_is_read_with_that_round_s_directories(tmp_path):
    """A part's probe over inputs, reported by the command as laid down — no id: the record reads it while the
    round's directories still name it, so the whole's executor is not stalled behind a refusal meant for a split."""
    part = {"behaviour": "raises JSONParseError", "command": "python {inputs}/t.py", "expect": "OK",
            "inputs": [["t.py", "part"]]}
    e = _whole_delivered_over_a_passed_part(part=part)
    _validator_packet(e, e.graph.get_task(TaskId("root")), "the library", None, scratch=str(tmp_path))   # lays them down
    dirs = dict(laid_down_dirs(e.validation_procedure(TaskId("root")), tmp_path))
    laid = {"behaviour": "b", "command": f"python {dirs[_part_pid(e)].as_posix()}/t.py", "expect": "OK",
            "held": False}
    own = e.graph.get_task(TaskId("root")).spec.criteria[0].check[0]
    e.record_exec_verdict("root", "FAIL", ["parses"], "validator", inputs_dirs=tuple(dirs.items()), per_criterion=[
        {"criterion": "parses", "verdict": "fail", "evidence": "the part's program printed ValueError",
         "behaviours": ["b"], "divergences": ["ValueError"],
         "probe": [{"behaviour": own.behaviour, "command": own.command, "expect": own.expect}, laid]}])
    T.signal(e, "root", "FAIL", "me", failed_criteria=["parses"])
    e.wait_idle()
    T.signal(e, "root", "DELIVER", "me", result="repaired")
    e.wait_idle()
    assert e.graph.get_state(TaskId("root")) == State.VALIDATING
    e.stop()


def test_a_command_the_whole_pins_too_does_not_account_for_the_part_s_expectation():
    """One command, two expectations: the whole's run of it shows the whole's; the part's is accounted for only
    under the part's id (critic r1, 2026-10-04)."""
    shared = {"behaviour": "the suite", "command": "python -m pytest tests -q", "expect": "passed"}
    part = dict(shared, behaviour="the subclass test", expect="test_errors.py::test_subclass PASSED")
    e = _whole_delivered_over_a_passed_part(own=shared, part=part)
    one = [{"criterion": "parses", "verdict": "pass", "evidence": "ran it", "behaviours": ["the suite"],
            "probe": [dict(shared)]}]
    with pytest.raises(ValueError) as ex:
        e.record_exec_verdict("root", "PASS", [], "validator", per_criterion=one)
    assert _part_pid(e) in str(ex.value)
    one[0]["probe"].append(dict(part, id=_part_pid(e), held=True))
    assert e.record_exec_verdict("root", "PASS", [], "validator", per_criterion=one)["verdict"] == "PASS"
    e.stop()


def test_a_rewrite_two_levels_down_is_read_on_the_root_s_delivery():
    """root → mid → leaf: leaf and mid passed on their own deliveries, then root's executor rewrote leaf's module.
    A DONE part's procedure, demanded again above it, is the whole of what its validation ran — leaf's probe
    included (critic r1, 2026-10-04: only mid's was demanded, and root closed DONE)."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "a library", "accepted_risks": _RISK,
                              "criteria": [criterion("works")]}, assignee="me")
    T.decompose(e, "root", [{"task_id": "mid", "spec": {"description": "the package", "accepted_risks": _RISK,
                             "criteria": [criterion("parses")]}, "assignee": "exec-1", "covers": ["works"]}], accepted_risks=REGISTER)
    T.decompose(e, "mid", [{"task_id": "leaf", "spec": {"description": "the parser module", "criteria": [criterion("errors", check=[_RAISES])]}, "assignee": "exec-2", "covers": ["parses"]}], accepted_risks=REGISTER)
    e.wait_idle()
    for tid, who in (("root", "me"), ("mid", "exec-1"), ("leaf", "exec-2")):
        T.signal(e, tid, "ACCEPT", who)
    for tid, who, up in (("leaf", "exec-2", "exec-1"), ("mid", "exec-1", "me")):
        T.signal(e, tid, "DELIVER", who, result=f"{tid} written")
        e.wait_idle()
        instrument_passes(e, tid, "validator")
        T.signal(e, tid, "PASS", up)
        e.wait_idle()
    T.signal(e, "root", "DELIVER", "me", result="the library, json_parser.py rewritten")
    e.wait_idle()
    leaf_pid = probe_id("mid/leaf/errors", e.graph.get_task(TaskId("leaf")).spec.criteria[0].check[0])
    own_only = [{"criterion": "works", "verdict": "pass", "evidence": "ran it", "behaviours": ["b"],
                 "probe": [{"behaviour": p.behaviour, "command": p.command, "expect": p.expect,
                            **({"id": probe_id(c.name, p)} if "/" in c.name else {})}
                           for c in e.validation_procedure(TaskId("root"))
                           for p in (c.check or ()) if c.name != "mid/leaf/errors"]}]
    with pytest.raises(ValueError) as ex:
        e.record_exec_verdict("root", "PASS", [], "validator", per_criterion=own_only)
    assert leaf_pid in str(ex.value)
    e.stop()


def test_a_pass_over_a_part_probe_reported_not_holding_is_not_a_verdict():
    """What the probe showed is the criterion's value: `held: false` under `pass` is the report contradicting itself
    (Inv-2) — refused, as a divergence under a pass is (critic r2, 2026-10-04: it closed the node DONE)."""
    e = _whole_delivered_over_a_passed_part()
    with pytest.raises(ValueError) as ex:
        e.record_exec_verdict("root", "PASS", [], "validator", per_criterion=[_entry(e, with_part=True, held=False)])
    assert "did not hold" in str(ex.value)
    e.stop()


def test_a_fail_that_does_not_show_the_part_holding_leaves_the_repair_to_the_whole():
    """The refusal rests on the pattern "every child passes on the delivered result", and a report that does not say
    the part's probe held — an instrument leaving `held` out, a hand record that cannot say it — has not shown it:
    the whole's executor re-delivers (critic r2, 2026-10-04: both stalled behind "the decomposition was refuted")."""
    e = _whole_delivered_over_a_passed_part()
    assert _refused_redelivery_after(e, _entry(e, "fail", with_part=True)) == ""
    e.stop()
    e = _whole_delivered_over_a_passed_part()
    own = e.graph.get_task(TaskId("root")).spec.criteria[0].check[0]
    e.record_reviewer_verdict("root", "FAIL", ["parses"], "rev", observed={
        "parses": {"note": "the part's module raises ValueError now", "ran": [own.command, _part_pid(e)],
                   "divergences": ["raises ValueError, not JSONParseError"]}})
    T.signal(e, "root", "FAIL", "me", failed_criteria=["parses"])
    e.wait_idle()
    T.signal(e, "root", "DELIVER", "me", result="repaired")
    e.wait_idle()
    assert e.graph.get_state(TaskId("root")) == State.VALIDATING
    e.stop()


def test_a_pass_on_the_whole_made_before_its_part_was_judged_does_not_stand():
    """A hand PASS on the whole while the part was still in validation demanded nothing of the part; once the part is
    judged and passes, the whole's PASS no longer covers the procedure its validation now runs (critic r2)."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "a JSON library", "accepted_risks": _RISK,
                              "criteria": [criterion("parses")]}, assignee="me")
    T.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "the parser module", "criteria": [criterion("errors", check=[_RAISES])]}, "assignee": "exec-1", "covers": ["parses"]}], accepted_risks=REGISTER)
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "me")
    T.signal(e, "kid", "ACCEPT", "exec-1")
    T.signal(e, "kid", "DELIVER", "exec-1", result="json_parser.py written")
    T.signal(e, "root", "DELIVER", "me", result="the library")
    e.wait_idle()
    own = e.graph.get_task(TaskId("root")).spec.criteria[0].check[0]
    with pytest.raises(ValueError) as ex:
        e.record_reviewer_verdict("root", "PASS", [], "rev",
                                  observed={"parses": {"note": "it holds", "ran": [own.command]}})
    assert "'kid' is VALIDATING" in str(ex.value)
    instrument_passes(e, "kid", "validator")
    T.signal(e, "kid", "PASS", "me")
    e.wait_idle()
    with pytest.raises(ValueError):            # …and once it has passed, the PASS must run the part's probe
        e.record_reviewer_verdict("root", "PASS", [], "rev",
                                  observed={"parses": {"note": "it holds", "ran": [own.command]}})
    e.stop()


def test_two_parts_pinning_one_command_are_each_accounted_for_by_their_own_id():
    """One command pinned by two parts with two expectations: a report of the command shows one of them — each part's
    probe is accounted for only under its own id (critic r2, 2026-10-04)."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "a library", "accepted_risks": _RISK,
                              "criteria": [criterion("works")]}, assignee="me")
    cmd = "python -m pytest tests -q"
    T.decompose(e, "root", [{"task_id": k, "assignee": "exec-1", "covers": ["works"],
                             "spec": {"description": k, "criteria": [criterion("ok", check=[
                                 {"behaviour": f"{k} holds", "command": cmd, "expect": exp}])]}}
                            for k, exp in (("ka", "test_a PASSED"), ("kb", "test_b PASSED"))], accepted_risks=REGISTER)
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "me")
    for k in ("ka", "kb"):
        T.signal(e, k, "ACCEPT", "exec-1")
        T.signal(e, k, "DELIVER", "exec-1", result=k)
        e.wait_idle()
        instrument_passes(e, k, "validator")
        T.signal(e, k, "PASS", "me")
        e.wait_idle()
    T.signal(e, "root", "DELIVER", "me", result="the library")
    e.wait_idle()
    own = e.graph.get_task(TaskId("root")).spec.criteria[0].check[0]
    pid = {k: probe_id(f"{k}/ok", e.graph.get_task(TaskId(k)).spec.criteria[0].check[0]) for k in ("ka", "kb")}
    base = {"behaviour": own.behaviour, "command": own.command, "expect": own.expect}
    one = [{"criterion": "works", "verdict": "pass", "evidence": "ran it", "behaviours": ["b"],
            "probe": [base, {"id": pid["ka"], "command": cmd, "expect": "test_a PASSED", "behaviour": "a", "held": True}]}]
    with pytest.raises(ValueError) as ex:
        e.record_exec_verdict("root", "PASS", [], "validator", per_criterion=one)
    assert pid["kb"] in str(ex.value)
    e.stop()


@pytest.mark.parametrize("held_by_its_issuer", [False, True])
def test_a_pass_over_an_open_part_waits_only_where_its_issuer_can_lift_it(held_by_its_issuer):
    """§12.8: the issuer's check reads the delivered result, not the children, and the departure from AND is read off
    the log; §12.16 (ii): a stricter refusal conforms only where its sender lifts it by his own moves. A whole whose
    issuer is also its Del (the parts' issuer) waits for them; at a seam the PASS lands and the departure is said
    (sync audit, B-F4 = A-F2)."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "a JSON library", "accepted_risks": _RISK,
                              "criteria": [criterion("parses")]}, assignee="lead")
    T.decompose(e, "root", [{"task_id": "mid", "spec": {"description": "the parser", "accepted_risks": _RISK, "criteria": [criterion("errors")]}, "assignee": "lead" if held_by_its_issuer else "w", "covers": ["parses"]}], accepted_risks=REGISTER)
    e.wait_idle()
    mid_exec = e.graph.get_task(TaskId("mid")).assignee
    T.decompose(e, "mid", [{"task_id": "leaf", "spec": {"description": "the lexer", "criteria": [criterion("tokens")]}, "assignee": "w2", "covers": ["errors"]}], accepted_risks=REGISTER)
    for tid, who in (("root", "lead"), ("mid", mid_exec)):
        T.signal(e, tid, "ACCEPT", who)
    T.signal(e, "mid", "DELIVER", mid_exec, result="the parser, its lexer still open")
    e.wait_idle()
    instrument_passes(e, TaskId("mid"), "validator")
    out = T.signal(e, "mid", "PASS", "lead")
    if held_by_its_issuer:
        assert out.get("accepted") is False and "not all children have PASSed" in out.get("error", ""), out
    else:
        assert out.get("accepted") is True, out
        assert e.passes_over_open_parts() == ["mid"]
    e.stop()
