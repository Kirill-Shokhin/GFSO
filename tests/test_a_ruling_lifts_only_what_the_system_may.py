"""What a ruling on a part's check may lift, read by a critic on 9c51566, each case built here and red there.

Lifted only by the system's issuer under AUTO over a plan it wrote: under SOLO, SEMI or no mode a self-signed ruling closed
the root over a check its parent would rework on. Only a check of a part the finding's own criterion rests on; only by
the pin's whole expectation or a whole line of it (`rc=1` was found in `rc=10`, `ok` in `not ok`); only that check as it
stood at the ruling, another corpus or expectation pinned since being another check, a new part pinning the same one the same
one. Never a criterion's last check, at any depth. Below a handed-in plan's root too the run stops with the signal. A
later finding by the ruled command with another expectation is a refutation, not "filed again". The record says what no
longer runs, who decided, and a whole above the ruling reads `narrowed` as unknown.

CONTROLS: drop `_system_may_lift` from `_ruled_out`, and the first test goes red; read `parts` whole in
`findings_a_ruling_could_lift`, the criterion test; `same_expectation` by `in`, the expectation test; drop `then` from
`_pins_lifted`, the corpus test; drop the `users_plan` refusal in `answer_the_challenge`, the handed-in test; `_as_filed`
returning `found`, the refutation test; `keeps_own` always true in `_pins_lifted`, the last-check test; drop `_lifted`
from `narrowed`, the record test.
"""
from __future__ import annotations

import contextlib
import dataclasses as dc
import json

import pytest

import gfso.tools as T
from gfso import issuer as I
from gfso.core.protocol.procedure import probe_id
from gfso.core.types import State, TaskId
from tests.support import criterion
from tests.test_a_check_of_the_plan_is_not_the_goal import (KEPT, KEPT_SAYS, ROOT, STUB, STUB_SAYS, _disputed, _fails_seen,
                                                            _finding, _pin, _pins, _rule, _settled, _standing, _whole)
from tests.test_the_issuer_answers_a_dispute import _ContactLLM
from tests.test_the_mode_decides_who_holds_what import Mode, _admit, _engine, _kid, _Roster


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _strip_pins(e, tid, name):
    t = e.graph.get_task(TaskId(tid))
    e._graph.save_task(dc.replace(t, spec=dc.replace(t.spec, criteria=tuple(
        dc.replace(c, check=()) if c.name == name else c for c in t.spec.criteria))))


def _deep(leaf_pins, mid_crit=None):
    """AUTO: root → mid → a settled leaf."""
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("mid", ["g"], mid_crit or criterion("m", "M holds")))
    _admit(e, "mid", _kid("leaf", ["m"], *leaf_pins))
    _settled(e, "leaf")
    return e, TaskId("mid")


@pytest.mark.parametrize("mode", [None, Mode.SOLO, Mode.SEMI])
def test_a_self_signed_ruling_keeps_the_parts_check_and_an_auto_one_lifts_it(tmp_path, mode):
    e = _engine(mode)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("root.part", ["g"], _pin("routes", STUB, STUB_SAYS)))
    _settled(e, "root.part")
    ids = _disputed(e, ("g", _finding("g")))
    out = T.signal(e, "root", "ACCEPT_CHALLENGE", str(e.graph.issuer_of(ROOT)), retire_findings=ids, justification="not g's")
    e.wait_idle()
    assert out["accepted"] and _standing(e) == set(), out
    assert STUB in _pins(e, "g"), f"a ruling under {mode} lifted a part's check: the parent would rework on it"
    assert T.get_verdict(e, "root")["retired_after_refutation"][0]["decided_by"] == "person"
    e.stop()


def test_the_systems_ruling_under_semi_keeps_the_check_too(tmp_path):
    e = _engine(Mode.SEMI)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("mid", ["g"], criterion("m", "M holds")))
    _admit(e, "mid", _kid("leaf", ["m"], _pin("routes", STUB, STUB_SAYS)))
    _settled(e, "leaf")
    mid = TaskId("mid")
    ids = _disputed(e, ("m", _finding("m")), tid="mid")
    out, _ = _rule(e, tmp_path, ids, mid, str(e.graph.issuer_of(mid)))
    assert out["status"] == "accepted" and STUB in _pins(e, "m", mid), out
    e.stop()


def test_a_finding_speaks_only_for_a_check_its_own_criterion_rests_on(tmp_path):
    e = _engine(Mode.AUTO)
    crits = [criterion("g", "G holds"), criterion("h", "H holds")]
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": crits})
    _admit(e, "root", _kid("root.a", ["h"], _pin("routes", STUB, STUB_SAYS)), _kid("root.b", ["g"], _pin("kept", KEPT, KEPT_SAYS)))
    _settled(e, "root.a"), _settled(e, "root.b")
    ids = _disputed(e, ("g", _finding("g")), ("h", _finding("h")))
    out, _ = _rule(e, tmp_path, ids)
    assert out["status"] == "accepted" and _standing(e) == {ids[0]}, "a pin under h spoke for a finding under g"
    e.stop()


def test_a_finding_says_the_pin_whole_or_a_whole_line_of_it(tmp_path):
    expect = "not ok\nrc=10"
    e = _engine(Mode.AUTO)
    crits = [criterion(n, n) for n in ("a", "b", "c", "d")]
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": crits})
    _admit(e, "root", _kid("root.part", ["a", "b", "c", "d"], _pin("routes", STUB, expect)))
    _settled(e, "root.part")
    ids = _disputed(e, ("a", _finding("a", STUB, "rc=1")), ("b", _finding("b", STUB, "ok")),
                    ("c", _finding("c", STUB, "not ok rc=10")), ("d", _finding("d", STUB, "rc=10")))
    out, _ = _rule(e, tmp_path, ids)
    assert out["status"] == "accepted" and _standing(e) == set(ids[:2]), (out, _standing(e))
    e.stop()


def test_a_ruling_lifts_the_check_as_it_stood_and_a_new_part_with_the_same_one_stays_lifted(tmp_path):
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    pin = {**_pin("routes", STUB, STUB_SAYS)}
    pin["check"] = [{**pin["check"][0], "inputs": {"f": "corpus one"}}]
    _admit(e, "root", _kid("root.part", ["g"], pin, _pin("kept", KEPT, KEPT_SAYS)))
    _settled(e, "root.part")
    ids = _disputed(e, ("g", _finding("g")))
    assert _rule(e, tmp_path, ids)[0]["status"] == "accepted" and STUB not in _pins(e, "g")
    _admit(e, "root", _kid("root.twin", ["g"], {**pin, "name": "routes_too"}))
    _settled(e, "root.twin")
    assert STUB not in _pins(e, "g"), "the same check under a new part is the one the ruling lifted"

    def _repinned(**over):
        part = e.graph.get_task(TaskId("root.part"))
        return dc.replace(part, spec=dc.replace(part.spec, criteria=tuple(
            dc.replace(c, check=tuple(dc.replace(p, **over) for p in c.check)) if c.name == "routes" else c
            for c in part.spec.criteria)))
    was = e.graph.get_task(TaskId("root.part"))
    e._graph.save_task(_repinned(inputs={"f": "corpus two"}))
    assert STUB in _pins(e, "g"), "another corpus is another check: the ruling outlived what it ruled on"
    e._graph.save_task(was)
    e.stop()


def test_below_a_handed_in_root_a_ruling_is_the_persons_and_the_run_stops(tmp_path):
    e, mid = _deep([_pin("routes", STUB, STUB_SAYS), _pin("kept", KEPT, KEPT_SAYS)])
    e.give_users_plan(ROOT)
    ids = _disputed(e, ("m", _finding("m")), tid="mid")
    issuer = str(e.graph.issuer_of(mid))
    llm = _ContactLLM({"decision": "accept", "justification": "false", "retire_findings": ids}, ran={"Bash": 1})
    verbs = I.Verbs(llm=lambda m, **k: llm, busy=lambda *a: contextlib.nullcontext(), review=None, refine=None,
                    place=lambda en, ag, n: str(tmp_path))
    out = I.settle(e, _Roster(), mid, "dispute", issuer, verbs)
    e.wait_idle()
    assert out["status"] == "users" and e.paused() and "only the user changes a check" in out["why"], out
    assert _standing(e, mid) == set(ids) and STUB in _pins(e, "m", mid) and e.graph.get_state(mid) == State.CHALLENGED
    assert e.plans_own_findings(mid) == [], "the system's question and its door read a handed-in plan as open"
    e.stop()


def _report(crit, expect):
    return [{"criterion": crit, "verdict": "fail", "evidence": "it printed otherwise",
             "probe": [{"behaviour": "b", "command": STUB, "expect": expect}]}]


def test_the_ruled_command_with_another_expectation_refutes_and_with_the_pins_does_not(tmp_path):
    e = _whole([criterion("g", "G holds")])
    ids = _disputed(e, ("g", _finding("g")))
    assert _rule(e, tmp_path, ids)[0]["status"] == "accepted"
    assert "g" not in e._refiled_rulings(ROOT, _report("g", "rc=0 and the real text"), ()), "no validator can refute by this command"
    assert "g" in e._refiled_rulings(ROOT, _report("g", STUB_SAYS), ()) and "g" in e._refiled_rulings(ROOT, _report("g", "rc=1"), ())
    e.record_exec_verdict(ROOT, "FAIL", ["g"], "val-1", per_criterion=_report("g", "rc=0 and the real text"))
    e.wait_idle()
    (fresh,) = e.regression_probes(ROOT)["g"]
    assert fresh["id"] != ids[0] and fresh["expect"] == "rc=0 and the real text" and fresh["id"] not in e.plans_own_findings(ROOT)
    e.stop()


def test_no_ruling_takes_a_criterions_last_check_at_any_depth(tmp_path):
    e, mid = _deep([_pin("routes", STUB, STUB_SAYS)])
    _strip_pins(e, "mid", "m")
    ids = _disputed(e, ("m", _finding("m")), tid="mid")
    _rule(e, tmp_path, ids, mid, str(e.graph.issuer_of(mid)))
    assert STUB in _pins(e, "m", mid), "the criterion was left with no check at all"
    e.stop()


def test_a_ruling_that_left_its_pin_running_does_not_void_that_pins_fail(tmp_path):
    """The pin runs and fails, so a PASS is refused; read as the ruling's subject the FAIL was ⊥ too: no verdict could be
    recorded (critic over 9971bef). A check that still runs is no ruled finding; lifted, it is."""
    def fail(tid, ids):
        return e._refiled_rulings(tid, [{"criterion": "m", "verdict": "fail", "evidence": "x", "probe": [
            {"id": ids[0], "behaviour": "b", "command": STUB, "expect": STUB_SAYS, "held": False}]}], ())

    e, mid = _deep([_pin("routes", STUB, STUB_SAYS)])
    _strip_pins(e, "mid", "m")
    ids = _disputed(e, ("m", _finding("m")), tid="mid")
    _rule(e, tmp_path, ids, mid, str(e.graph.issuer_of(mid)))
    assert STUB in _pins(e, "m", mid) and fail(mid, ids) == {}
    e.stop()
    e, mid = _deep([_pin("routes", STUB, STUB_SAYS), _pin("kept", KEPT, KEPT_SAYS)])
    ids = _disputed(e, ("m", _finding("m")), tid="mid")
    _rule(e, tmp_path, ids, mid, str(e.graph.issuer_of(mid)))
    assert STUB not in _pins(e, "m", mid) and list(fail(mid, ids)) == ["m"], "a check lifted stays the ruling's subject"
    e.stop()


def test_a_check_lifted_from_this_criterion_is_its_rulings_subject_though_another_runs_it(tmp_path):
    e, mid = _deep([_pin("routes", STUB, STUB_SAYS), _pin("kept", KEPT, KEPT_SAYS)])
    ids = _disputed(e, ("m", _finding("m")), tid="mid")
    _rule(e, tmp_path, ids, mid, str(e.graph.issuer_of(mid)))
    parts = e.parts_procedure
    e.parts_procedure = lambda tid: {**parts(tid), "other": list(parts(tid).get("m", ())) + [dc.replace(next(iter(parts(tid)["m"])), check=(
        dc.replace(next(iter(parts(tid)["m"])).check[0], command=STUB, expect=STUB_SAYS),))]}
    assert list(e._refiled_rulings(mid, [{"criterion": "m", "verdict": "fail", "evidence": "x", "probe": [
        {"id": ids[0], "behaviour": "b", "command": STUB, "expect": STUB_SAYS, "held": False}]}], ())) == ["m"]
    e.stop()


def test_the_record_says_what_no_longer_runs_and_a_whole_above_does_not_read_unnarrowed(tmp_path):
    e, mid = _deep([_pin("routes", STUB, STUB_SAYS), _pin("kept", KEPT, KEPT_SAYS)])
    assert e.claim_drift(ROOT)["narrowed"] is False
    ids = _disputed(e, ("m", _finding("m")), tid="mid")
    assert _rule(e, tmp_path, ids, mid, str(e.graph.issuer_of(mid)))[0]["status"] == "accepted"
    (ruled,) = T.get_verdict(e, "mid")["retired_after_refutation"]
    assert ruled["command"] == STUB and ruled["decided_by"] == "system"
    for node in ("mid", "root"):
        (gone,) = T.get_verdict(e, node)["checks_no_longer_run"]
        assert gone["command"] == STUB and gone["decided_by"] == "system" and gone["node"] == "mid" and gone["criterion"] == "m"
        assert gone["check"] == probe_id("leaf/routes", {"command": STUB}) and "no longer runs" in gone["says"]
    assert e.claim_drift(ROOT)["narrowed"] is None, "a check lifted below read as nothing narrowed above"
    assert json.dumps(e.claim_drift(ROOT))
    e.stop()
