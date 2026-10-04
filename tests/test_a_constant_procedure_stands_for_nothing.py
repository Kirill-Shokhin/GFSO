"""A criterion stands on its pinned procedure only if that procedure can fail (critic, 2026-10-11).

`echo ok` pinned as a criterion's whole procedure, run and cited, carried two behaviours the validator named and never
probed to a PASS: a probe that emits a constant must not stand in for a behaviour nobody observed (`emits_a_constant`).
"""
from __future__ import annotations


import pytest

import gfso.tools as T
from gfso.core.protocol.invariants import emits_a_constant
from gfso.core.protocol.procedure import probe_id
from gfso.core.types import TaskId
from tests.support import DENIAL_ENTRY, UNMODELLED_FAULT, make_engine

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY", "justification": "no precedent",
          "invalidation_condition": "one occurs", "p": 0.01, "impact": "x"}, DENIAL_ENTRY]
_C = "Escape decoding"
_NAMED = ["escapes match GNU", "\0NNN matches GNU", "mid-line \r matches GNU"]


def _record(check: dict, monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "echo", "accepted_risks": _RISK,
                              "criteria": [{"name": _C, "description": "echo -e decodes as GNU does", "check": [check]}]},
                  assignee="me")
    T.signal(e, "root", "ACCEPT", "me")
    T.signal(e, "root", "DELIVER", "me", result="built")
    e.wait_idle()
    probe = dict(check, id=probe_id(_C, check).split("#", 1)[1], behaviour=_NAMED[0])
    entry = {"criterion": _C, "verdict": "pass", "evidence": "the pinned check printed ok", "behaviours": _NAMED,
             "probe": [probe], "divergences": []}
    try:
        return e.record_exec_verdict("root", "PASS", [], "validator", per_criterion=[entry], require_probe=True,
                                     tools_used={"Bash": 1})["verdict"]
    finally:
        e.stop()


def test_a_constant_procedure_is_not_admitted(monkeypatch):
    """Whole procedure a constant: the criterion forbids nothing, and the contract is not admitted at all — named only,
    an AUTO root on `sql_database` passed four such criteria at 0.09 held-out (`procedure.hollow_procedures`)."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "echo", "accepted_risks": _RISK, "criteria": [
        {"name": _C, "description": "echo -e decodes as GNU does", "check": [{"command": "echo ok", "expect": "ok"}]}]},
                  assignee="me")
    assert e.graph.get_task(TaskId("root")) is None or e.graph.get_state(TaskId("root")).name == "IDLE"
    e.stop()


def test_control_a_procedure_that_can_fail_still_carries_them(monkeypatch):
    sweep = {"command": ". h.sh; for s in '\0101' 'a\rb'; do c echo -e $s; done; echo ok", "expect": "ok"}
    assert str(_record(sweep, monkeypatch)).upper().endswith("PASS")


def test_control_a_probe_whose_later_line_runs_the_work_is_no_constant():
    """`echo 'building'` then `./run_tests.sh` on its own line runs work; read as one line, a real probe was refused."""
    assert emits_a_constant("echo 'Complex SELECT test'") and not emits_a_constant("echo 'building'\n./run_tests.sh")
