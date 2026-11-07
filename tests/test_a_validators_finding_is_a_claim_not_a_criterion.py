"""Two classes (the author, 2026-11-04: «есть исходные критерии а есть придуманные походу»). The plan's criteria and their
pins: as they were. A validator's own finding: not a criterion (§2.2, §12.8) but his claim about the work at his verdict,
standing while the next independent validator reproduces it.

GB_coreutils_tnyzqh948: the validator ran `printf ... > $T/v; ./cat -vT ...`, printed vT-same, and his report wrote
`T=$(mktemp -d); ./cat -vT $T/v; echo` expecting `vT`, under an entry that said it failed only on another probe. Filed as a
refutation, it fails on any program; later rounds said so in words, and the root reworked on it for hours.

CONTROLS: file every unsaid probe in `refuting_probes` and the filing test goes red; drop the `by_hand` and assignee checks in
`_file_findings`, the independence test; drop the `pins` skip in `findings_not_reproduced`, the plan's-check test; drop the
command check there, the as-filed test; keep the mark in `record_not_reproduced` when filed again, the reproduced test; drop
`RETURNED`, the person's test; drop `_criterion_now` from `_unreproduced`, the record test.
"""
from __future__ import annotations

import dataclasses as dc
import json

import pytest

import gfso.tools as T
from gfso.core.protocol.procedure import probe_id, refuting_probes, with_engine_observations
from gfso.core.types import AgentId, Criteria, Probe, RevisionReason, TaskId
from tests.support import criterion
from tests.test_a_check_of_the_plan_is_not_the_goal import ROOT, STUB, STUB_SAYS, _finding, _pin, _settled, _standing, _whole
from tests.test_the_mode_decides_who_holds_what import Mode, _admit, _engine, _kid

BROKEN, SAID = "T=$(mktemp -d); ./cat -vT $T/v; echo", "vT"
OUT = "cat: /tmp/x/v: No such file or directory"


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _one_root_with(*found):
    e = _whole([criterion("g", "G holds")])
    e._graph._storage.store_critique(TaskId("root#regression-probes"), json.dumps({"g": list(found)}))
    return e


def _entry(verdict="pass", **probe):
    pinned = {"id": "g#x", "command": "check g", "expect": "it holds"}
    return [{"criterion": "g", "verdict": verdict, "evidence": "ran it", "behaviours": ["b"],
             "probe": [{**pinned, "behaviour": "b"}, {"behaviour": "b", "expect": "whatever it printed", **probe}]}]


def _says_not_refuting(command=BROKEN, **more):
    return _entry(id=_finding("g", BROKEN, SAID)["id"], command=command, printed=OUT,
                  not_refuting="reads a file it never creates: the -vT requirement holds on a real file", **more)


def _record(e, report, validator="val-1", verdict="FAIL", failed=("g",), **kw):
    """Through the engine's own record, a FAIL that takes the report's filings without asking a PASS's whole procedure."""
    report = [{**x, "verdict": "fail"} for x in report] if verdict == "FAIL" else report
    e.record_exec_verdict(ROOT, "FAIL", list(failed), validator, per_criterion=report, by_hand=kw.get("by_hand", False))
    e.wait_idle()


def test_beside_a_probe_that_did_not_hold_one_that_says_nothing_is_no_refutation():
    entry = {"criterion": "c", "verdict": "fail", "evidence": "fails only on the pin", "probe": [
        {"id": "pin", "command": STUB, "expect": "x", "held": False},
        {"command": BROKEN, "expect": SAID, "behaviour": "own probe, byte-compared"},
        {"command": "./own", "expect": "y", "held": False}]}
    assert {p["command"] for p in refuting_probes([entry])["c"]} == {STUB, "./own"}
    alone = {"criterion": "c", "verdict": "fail", "evidence": "my probe refutes it", "probe": [{"command": "./own", "expect": "y"}]}
    assert [p["command"] for p in refuting_probes([alone])["c"]] == ["./own"], "a validator's only refutation went unfiled"


def test_an_independent_validator_that_does_not_reproduce_a_finding_ends_its_demand_and_the_record_says_so():
    f = _finding("g", BROKEN, SAID)
    e = _one_root_with(f)
    assert _standing(e) == {f["id"]}
    _record(e, _says_not_refuting())
    assert _standing(e) == set(), "re-run, shown and answered, it is still demanded"
    (row,) = T.get_verdict(e, "root")["findings_not_reproduced"]
    assert (row["id"], row["command"], row["by"], row["printed"]) == (f["id"], BROKEN, "val-1", OUT) and "never creates" in row["why"]
    assert e.claim_drift(ROOT)["narrowed"] is None
    t = e.graph.get_task(ROOT)      # …said of the criterion as written: a later act rewriting it ends that, as it ends a ruling
    e.revise(ROOT, dc.replace(t.spec, criteria=tuple(dc.replace(c, description="G, rewritten") for c in t.spec.criteria)),
             AgentId("agent"), reason=RevisionReason.OTHER)
    e.wait_idle()
    assert _standing(e) == {f["id"]}, "said of a criterion no longer written"
    e.stop()


def test_in_the_same_round_a_pass_over_it_stands_and_the_next_pass_owes_nothing():
    f = _finding("g", BROKEN, SAID)
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "a leaf goal", "criteria": [criterion("g", "G holds")]})
    e._graph._storage.store_critique(TaskId("root#regression-probes"), json.dumps({"g": [f]}))
    assert e.record_exec_verdict(ROOT, "PASS", [], "val-1", per_criterion=_says_not_refuting(), require_probe=True)["verdict"] == "PASS"
    e.wait_idle()
    assert _standing(e) == set(), "passed over it, and it stayed demanded of the next round"
    assert e.record_exec_verdict(ROOT, "PASS", [], "val-1", per_criterion=_entry(command="./x"), require_probe=True)["verdict"] == "PASS"
    e.stop()


def test_the_executor_has_no_hand_in_it_nor_a_hand_record():
    f = _finding("g", BROKEN, SAID)
    e = _one_root_with(f)
    _record(e, _says_not_refuting(), validator=str(e.graph.get_task(ROOT).assignee))
    _record(e, _says_not_refuting(), by_hand=True)
    assert _standing(e) == {f["id"]}, "the one the finding binds took it off"
    _record(e, _says_not_refuting())
    assert _standing(e) == set()
    e.stop()


def test_a_line_that_only_names_the_finding_does_not_end_it():
    """As a substring each of these ended `./cat -vT f`, none running it (critic over 01d7579); a `cd` before it is its run."""
    f = _finding("g", BROKEN, SAID)
    e = _one_root_with(f)
    for wrapped in (f"echo not run: {BROKEN}", f": {BROKEN}", f"true || {BROKEN}", f"{BROKEN}_other"):
        _record(e, _says_not_refuting(command=wrapped))
        assert _standing(e) == {f["id"]}, wrapped
    _record(e, _says_not_refuting(command=f'cd "my dir" && {BROKEN}'))
    assert _standing(e) == set()
    e.stop()
    filed = _finding("g", f"cd delivery && {BROKEN}", SAID)
    e = _one_root_with(filed)
    _record(e, _entry(id=filed["id"], command=f"cd delivery && {BROKEN}", printed=OUT, not_refuting="never required"))
    assert _standing(e) == set(), "filed with its `cd`, run as filed"
    e.stop()


def test_a_finding_ended_and_then_reproduced_under_its_id_stands_again():
    """Reworded, citing its id: not filed anew, and it read as not reproduced with a FAIL on it (critic)."""
    f = _finding("g", BROKEN, SAID)
    e = _one_root_with(f)
    _record(e, _says_not_refuting())
    assert _standing(e) == set()
    _record(e, _entry(id=f["id"], command=f"{BROKEN} # reworded", held=False))
    assert _standing(e) == {f["id"]}
    assert not T.get_verdict(e, "root").get("findings_not_reproduced")
    e.stop()


def test_a_report_that_ran_no_shell_ends_no_finding():
    f = _finding("g", BROKEN, SAID)
    e = _one_root_with(f)
    e.record_exec_verdict(ROOT, "FAIL", ["g"], "val-1", per_criterion=[{**x, "verdict": "fail"} for x in _says_not_refuting()],
                          tools_used={"Read": 3})
    e.wait_idle()
    assert _standing(e) == {f["id"]}
    e.record_exec_verdict(ROOT, "FAIL", ["g"], "val-1", per_criterion=[{**x, "verdict": "fail"} for x in _says_not_refuting()],
                          tools_used={"Bash": 1})
    e.wait_idle()
    assert _standing(e) == set()
    e.stop()


def test_the_systems_own_mark_is_not_the_reports_word_on_its_other_probes():
    """Its observation marks a pin `held: false`; read as the report's, a true refutation beside it was not filed (critic)."""
    pin = Criteria(name="g", description="d", check=(Probe(behaviour="b", command="check g", expect="it holds", exact=True),))
    own = {"behaviour": "b", "command": "./cat bigfile", "expect": "the whole file"}
    pid = probe_id("g", {"command": "check g"})
    sees = lambda verdict, *probes: refuting_probes(with_engine_observations(
        [{"criterion": "g", "verdict": verdict, "evidence": "x", "probe": list(probes)}], [pin], None,
        {pid: {"out": "stub", "matched": False}}))["g"]
    assert {p["command"] for p in sees("fail", own)} == {"./cat bigfile", "check g"}
    assert {p["command"] for p in sees("pass", own)} == {"check g"}, "what the report passed refuted nothing: 1,414 findings once"
    assert {p["command"] for p in sees("fail", own, {**own, "command": "named", "held": False, "system_saw": True})} == {
        "named", "check g"}, "a report does not speak as the system"
    said = [{"criterion": "g", "verdict": "fail", "evidence": "x", "probe": [own, {**own, "command": "other", "held": False}]}]
    assert {p["command"] for p in refuting_probes(said)["g"]} == {"other"}, "the report's own word still stands"


def test_only_a_run_as_filed_with_its_output_and_its_why_ends_it():
    f = _finding("g", BROKEN, SAID)
    e = _one_root_with(f)
    for report in (_says_not_refuting(command="T=$(mktemp -d); printf x > $T/v; ./cat -vT $T/v"),
                   _says_not_refuting(ran=False), _says_not_refuting(held=False),
                   _entry(id=f["id"], command=BROKEN, not_refuting="no output shown")):
        _record(e, report)
        assert _standing(e) == {f["id"]}, report
    _record(e, _says_not_refuting())
    assert _standing(e) == set()
    e.stop()


def test_a_check_of_the_plan_is_not_a_validators_claim():
    """A run of a part's pin, and of the node's own, stays with `pins_ruled_out` and the criteria: no report takes it off."""
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("root.part", ["g"], _pin("routes", STUB, STUB_SAYS)))
    _settled(e, "root.part")
    pin, own = _finding("g"), _finding("g", BROKEN, SAID)
    e._graph._storage.store_critique(TaskId("root#regression-probes"), json.dumps({"g": [pin, own]}))
    _record(e, _says_not_refuting() + [{"criterion": "g", "verdict": "pass", "evidence": "x", "probe": [
        {"id": pin["id"], "command": STUB, "expect": "x", "printed": "y", "not_refuting": "stale"}]}])
    assert _standing(e) == {pin["id"]}, "a validator's word took off a check of the plan, or left his own class standing"
    assert e.plans_own_findings(ROOT) == [pin["id"]], "the two classes are one partition: the plan's check, the issuer's move"
    e.stop()


def test_reproduced_by_a_later_validator_it_stands_again_and_in_one_report_filing_wins():
    f = _finding("g", BROKEN, SAID)
    e = _one_root_with(f)
    _record(e, _says_not_refuting())
    assert _standing(e) == set()
    refiles = [{"criterion": "g", "verdict": "fail", "evidence": "it refutes", "probe": [{"command": BROKEN, "expect": SAID, "behaviour": "b"}]}]
    _record(e, refiles)
    assert _standing(e) == {f["id"]}, "an independent reproduction did not bring it back"
    _record(e, refiles + _says_not_refuting())
    assert _standing(e) == {f["id"]}, "one report both filed and dismissed it"
    e.stop()


def test_a_person_returns_it_and_then_no_run_takes_it_off():
    f = _finding("g", BROKEN, SAID)
    e = _one_root_with(f)
    _record(e, _says_not_refuting())
    assert T.TOOLS["return_finding"](e, "root", f["id"], "the goal asks for it") == {"returned": f["id"]}
    assert _standing(e) == {f["id"]}
    _record(e, _says_not_refuting())
    assert _standing(e) == {f["id"]}, "a validator overrode the person"
    assert "error" in T.TOOLS["return_finding"](e, "root", "g#gone", "why")
    e.stop()
