"""An absence has to SHOW, and the refusal has to say that is what went wrong.

A stranger on the MCP door had every one of the three nodes in an HONEST run refused as ⊥ on the
first report, at a paid validator round each, and worked out why from the records: a probe whose
`expect` is the empty string is discarded, and the behaviours it observed are then counted unobserved
(wave 23, 2026-09-03). Their case was `grep -rin configparser iniq/` with `expect: ""` for the
behaviour "no reference to configparser anywhere under iniq/" — a real command, really run, labelled
with the behaviour it observes.

The discard is RIGHT and stays: empty output cannot tell "there are no matches" from "the command
never ran", which is the ⊥ this product exists to refuse. What was wrong is that nothing said so
where it binds. The report's author — the instrument — read a schema that asked for "what its output
must show" with no hint that nothing is not an answer, and the refusal it got back said "unobserved",
which reads as "you wrote no probe" to someone looking straight at their probe. The same instrument
then passed the identical check written to print something.

Two gaps, opposite repairs: write a probe, versus make this probe show its result. The engine can
tell them apart, so it says which.
"""
from __future__ import annotations

import pytest

from gfso import tools as T
from gfso.core.protocol.invariants import probes_that_expected_nothing, underprobed
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine

_SILENT_PROBE = [{"criterion": "no_configparser", "verdict": "pass",
                  "evidence": "grep found nothing",
                  "behaviours": ["no reference to configparser anywhere under iniq/"],
                  "probe": [{"command": "grep -rin configparser iniq/", "expect": "",
                             "behaviour": "no reference to configparser anywhere under iniq/"}]}]


def test_the_rule_still_discards_a_probe_that_proves_nothing():
    """The teeth stay: an empty expectation leaves the behaviour unobserved."""
    assert underprobed(_SILENT_PROBE) == {
        "no_configparser": ["no reference to configparser anywhere under iniq/"]}


def test_and_the_engine_can_tell_that_gap_from_a_missing_probe():
    assert probes_that_expected_nothing(_SILENT_PROBE) == {
        "no_configparser": ["grep -rin configparser iniq/"]}
    assert probes_that_expected_nothing(
        [dict(_SILENT_PROBE[0], probe=[])]) == {}, "a report with NO probe is the other gap"


def test_the_refusal_names_the_discarded_probe_rather_than_calling_it_missing():
    e = make_engine()
    e.start()
    T.create_task(e, "leaf", {"description": "a leaf",
                              "criteria": [{"name": "no_configparser",
                                            "description": "no configparser anywhere"}],
                              "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                  "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    e.wait_idle()
    T.signal(e, "leaf", "ACCEPT", "exec-1")
    T.signal(e, "leaf", "DELIVER", "exec-1", result="built it")

    with pytest.raises(ValueError) as caught:
        e.record_exec_verdict(TaskId("leaf"), "PASS", [], "val-1", per_criterion=_SILENT_PROBE)

    said = str(caught.value)
    assert "discarded for expecting no output" in said, said
    assert "grep -rin configparser iniq/" in said, said
    assert "echo exit=$?" in said, "the repair has to be shown, not only the diagnosis"
    e.stop()


def test_the_same_absence_written_to_show_its_result_is_accepted():
    """The negative control, and the thing the tester's own next round did."""
    e = make_engine()
    e.start()
    T.create_task(e, "ok", {"description": "a leaf",
                            "criteria": [{"name": "no_configparser",
                                          "description": "no configparser anywhere"}],
                            "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    e.wait_idle()
    T.signal(e, "ok", "ACCEPT", "exec-1")
    T.signal(e, "ok", "DELIVER", "exec-1", result="built it")

    rec = e.record_exec_verdict(
        TaskId("ok"), "PASS", [], "val-1",
        per_criterion=[{"criterion": "no_configparser", "verdict": "pass",
                        "evidence": "grep -rc found 0 files matching; exit=1",
                        "behaviours": ["no reference to configparser anywhere under iniq/"],
                        "probe": [{"command": "grep -rin configparser iniq/; echo exit=$?",
                                   "expect": "exit=1",
                                   "behaviour": "no reference to configparser anywhere under iniq/"}]}])

    assert rec["verdict"] == "PASS"
    e.stop()
