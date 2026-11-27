"""A refusal no re-asked validation changes is not asked again — one rule, whatever mix of classes it carries.

§12.2: ⊥ is no event; VALIDATING's bound ends its wait and hands the node to its issuer — with its record (Thm 11). A
check past its whole bound times out again on the same tree; a criterion not decidable as written is refused again.
Decided per class, a refusal carrying both was re-asked every half minute, paid, until T_validate; and in a scope the
nodes waiting on an undecided part carry no refusal of their own, so read as re-askable they hid the part's class from
the scope's route (critic over 36121d2). At the lapse the issuer — machine or person — is told, for every criterion
not passed, the validator's word, its evidence and what that class asks of him.

CONTROL: make `accounting.not_asked_again` decide one class at a time and the mix test goes red; read every undecided
node's error in `validate._sign_scope` and the scope test does; drop `refused_why` from `issuer_context` / the parked
frontier directive and the text tests do.
"""
from __future__ import annotations

import pytest

import gfso.issuer as I
import gfso.tools as T
import gfso.validate as VAL
from gfso.core.protocol.accounting import not_asked_again
from gfso.core.protocol.invariants import PAST_BOUND
from gfso.core.types import State, TaskId
from gfso.engine.frontier import NodeSteps
from tests.support import criterion, make_engine
from tests.test_one_session_carries_a_scope import _NeverAnswers, _LLM, _delivered, _dispatcher, _drive, _project

WRITTEN = "not decidable as written: 'feels fast' names nothing to observe on the delivery"
UNREACHED = "could not observe it: make fails in the copy, ./prog was never built"
SAID = ["sorts ascending", "stable under ties"]


def _node():
    e = make_engine(check_interval=10_000)
    e.start()
    T.create_task(e, "n", {"description": "leaf", "criteria": [criterion(c, c.upper()) for c in "abc"]},
                  assignee="worker")
    T.signal(e, "n", "ACCEPT", "worker")
    T.signal(e, "n", "DELIVER", "worker", result="did it")
    return e


def _entry(name, word, evidence, **marks):
    return {"criterion": name, "verdict": word, "evidence": evidence, "behaviours": SAID[:1],
            "probe": [{"behaviour": SAID[0], "command": f"check {name}", "expect": "it holds"}], "divergences": [],
            **marks}


def _refused(e, *entries):
    with pytest.raises(ValueError) as bottom:
        e.record_exec_verdict("n", "FAIL", [x["criterion"] for x in entries if x["verdict"] != "pass"], "val-1",
                              require_probe=True, per_criterion=list(entries))
    e.record_rejected_report(TaskId("n"), str(bottom.value), list(entries))   # …kept as `validate._record_node` keeps it
    return str(bottom.value)


def _classified(why):
    said = type("E", (), {"emit_info": lambda self, *a: None})()
    return VAL._classify_no_verdict(said, "n", {"error": why, "stats": [{"cost_usd": 0.1}]})


def test_a_check_past_its_bound_beside_a_criterion_not_decidable_as_written_is_not_asked_again():
    """«not decidable as written» is one reading of the text: spent once a second run on this delivery read it so."""
    e = _node()
    entries = (_entry("a", "undecidable", "the system's run of a#1 did not finish", **{
        PAST_BOUND: ["a#1"], "past_bound_whole": True}), _entry("b", "not_decidable", WRITTEN),
        _entry("c", "pass", "it holds"))
    first = _refused(e, *entries)
    assert "NOT ASKED AGAIN" not in first and _classified(first) == "no-verdict", first
    why = _refused(e, *entries)
    assert why.startswith("NOT ASKED AGAIN") and "a — " in why and "b — " in why, why
    assert _classified(why) == "no-verdict:spent", why
    e.stop()


def test_an_undecidable_beside_them_is_still_asked_again():
    """CONTROL — «nothing observed decides it» is the instrument's ⊥, which another validation can cure."""
    e = _node()
    why = _refused(e, _entry("b", "not_decidable", WRITTEN), _entry("c", "undecidable", UNREACHED),
                   _entry("a", "pass", "it holds"))
    assert "NOT ASKED AGAIN" not in why and _classified(why) == "no-verdict", why
    e.stop()


def test_a_scope_whose_part_is_not_decidable_reaches_the_route_not_asked_again(tmp_path):
    """The whole and the consumer wait on the undecided part, with no refusal of their own: the part's class decides."""
    e, agents = _project(tmp_path)
    _drive(e, _dispatcher(e, agents, _LLM(_delivered("root.a", "root.b", "root")), _NeverAnswers(), []),
           lambda: e.graph.get_state(TaskId("root")) == State.VALIDATING, rounds=40)
    refusal = not_asked_again({"a_ok": [f"not decidable as written — the validator: «{WRITTEN}»"]}, [], refused_before=1)
    verdicts = {"root.a": {"verdict": None, "failed_criteria": [], "error": refusal},
                "root.b": {"verdict": "PASS", "failed_criteria": []}, "root": {"verdict": "PASS", "failed_criteria": []}}
    ret = VAL._sign_scope(e, e.graph.get_task(TaskId("root")), verdicts, "val-1", True)
    assert ret != "no-verdict" and ret == "no-verdict:spent", ret
    e.stop()


def test_the_machine_issuer_is_told_an_undecidable_criterions_evidence_at_the_lapse(monkeypatch):
    e = _node()
    _refused(e, _entry("b", "not_decidable", WRITTEN), _entry("c", "undecidable", UNREACHED),
             _entry("a", "pass", "it holds"))
    monkeypatch.setattr(I, "_validation_lapsed", lambda engine, task: True)
    text = I.issuer_context(e, "n", "escalation")
    assert UNREACHED in text and WRITTEN in text and "c — undecidable" in text, text[-1500:]
    assert "rewrite it decidable here, or re-present it" in text and "rewrite it so the delivery can decide it" in text
    e.stop()


def test_the_person_is_told_it_on_their_frontier():
    e = _node()
    _refused(e, _entry("c", "undecidable", UNREACHED), _entry("a", "pass", "it holds"), _entry("b", "pass", "it holds"))
    e.parking.park_validation(TaskId("n"))
    t = e.graph.get_task(TaskId("n"))
    step = NodeSteps(e).step_out(t, "VALIDATE", "validate it")
    assert UNREACHED in step["directive"] and "c — undecidable" in step["directive"], step["directive"][-800:]
    e.stop()
