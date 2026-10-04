"""A part's pinned probe observed over the whole's delivery is ONE fact, whichever criterion of the whole rests on it.

A whole's validation runs again each DONE part's pinned procedure over the whole's delivery (§11.3, §4.3), under the
whole's criteria the part is mapped to. The probe's command, expectation and artifact do not depend on which of them
it is read under, and its id names the part, so cited as holding once it was observed for all of them. Demanded again
under each, the automatic coreutils run (GB_coreutils_tmlqc3001) had six root reports refused whose every part probe
was cited holding once — about half the run's validation spend, nothing unobserved among it.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.core.protocol.procedure import part_criteria, probe_id, unrun_parts
from gfso.core.types import Criteria, Probe, State, TaskId
from tests.support import REGISTER, criterion, instrument_passes, make_engine
from tests.test_a_part_is_checked_again_inside_its_whole import _RAISES, _RISK

_PART = part_criteria("root.cat", [Criteria("flags", check=(Probe("cat flags", "cat -n f", "ok"),))])
_PARTS = {"A": _PART, "B": _PART}          # two criteria of the whole rest on the same part
_ID = probe_id(_PART[0].name, _PART[0].check[0])


def _report(held_under_a, b_probes=()):
    return [{"criterion": "A", "verdict": "pass", "probe": [{"id": _ID, "held": held_under_a, "command": "as pinned",
                                                           "expect": "ok"}]},
            {"criterion": "B", "verdict": "pass", "probe": list(b_probes)}]


def test_cited_holding_under_one_criterion_it_is_observed_for_every_criterion_on_the_part():
    assert unrun_parts(_PARTS, _report(True)) == {}


def test_cited_failing_anywhere_it_is_not_credited_elsewhere():
    # one observation: reported not holding, it holds for no criterion resting on it — the one citing it included
    assert unrun_parts(_PARTS, _report(False)) == {"A": [_ID], "B": [_ID]}
    # holding under A, failing under C (which the validator failed): the observations disagree, so neither A nor B
    # is credited with either
    contradicted = _report(True) + [{"criterion": "C", "verdict": "fail", "probe": [
        {"id": _ID, "held": False, "command": "as pinned", "expect": "ok"}]}]
    assert unrun_parts({**_PARTS, "C": _PART}, contradicted) == {"A": [_ID], "B": [_ID]}


def test_not_cited_at_all_it_is_still_unrun():
    assert unrun_parts(_PARTS, _report(True)[1:] + [{"criterion": "A", "verdict": "pass", "probe": []}]) == {
        "A": [_ID], "B": [_ID]}


# …AND "SHOWN HOLDING" READS THE SAME ONE OBSERVATION: a whole failing over a part shown holding is the refuted-split
# pattern (§15.4), which refuses re-delivering the aggregate unchanged. Read per criterion only, a criterion that
# points to the part's probe written out under another read as "not shown holding", and the refutation went silent.

@pytest.fixture
def _whole_over_a_passed_part(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "a JSON library", "accepted_risks": _RISK,
                              "criteria": [criterion("parses"), criterion("other")]}, assignee="me")
    T.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "the parser module",
                             "criteria": [criterion("errors", check=[_RAISES])]}, "assignee": "exec-1",
                             "covers": ["parses", "other"]}], accepted_risks=REGISTER)
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "me")
    T.signal(e, "kid", "ACCEPT", "exec-1")
    T.signal(e, "kid", "DELIVER", "exec-1", result="x")
    e.wait_idle()
    instrument_passes(e, "kid", "validator")
    T.signal(e, "kid", "PASS", "me")
    T.signal(e, "root", "DELIVER", "me", result="lib")
    e.wait_idle()
    yield e
    e.stop()


def _entries(e, cite_under_other):
    c = e.graph.get_task(TaskId("kid")).spec.criteria[0]
    part = {"id": probe_id(f"kid/{c.name}", c.check[0]), "behaviour": _RAISES["behaviour"],
            "command": _RAISES["command"], "expect": _RAISES["expect"], "held": True}
    out = []
    for name, v in (("parses", "pass"), ("other", "fail")):
        own = next(x for x in e.graph.get_task(TaskId("root")).spec.criteria if x.name == name).check[0]
        probes = [{"behaviour": own.behaviour, "command": own.command, "expect": own.expect}]
        probes += [dict(part)] if name == "parses" or cite_under_other else []
        out.append({"criterion": name, "verdict": v, "behaviours": [own.behaviour], "evidence": "ran", "probe": probes,
                    **({"divergences": ["wrong"]} if v == "fail" else {})})
    return out


@pytest.mark.parametrize("cite_under_other", [True, False])
def test_a_whole_failing_over_a_part_shown_holding_once_is_a_refuted_split(_whole_over_a_passed_part, cite_under_other):
    e = _whole_over_a_passed_part
    e.record_exec_verdict("root", "FAIL", ["other"], "validator", per_criterion=_entries(e, cite_under_other))
    T.signal(e, "root", "FAIL", "me", failed_criteria=["other"])
    e.wait_idle()
    out = T.signal(e, "root", "DELIVER", "me", result="unchanged")
    e.wait_idle()
    assert not out.get("accepted") and e.graph.get_state(TaskId("root")) == State.REWORKING, out
