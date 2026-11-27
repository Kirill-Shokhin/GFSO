"""A pinned check the system ran on a delivery is handed to its validator as that run, never as a command to run.

Measured 2026-11-27 (validator round 7 on cut_private_reaches, 00:20→00:50): one validation ran the pinned 11-minute
suite twice — the system's own run, which a PASS stands on (`validate._observe_pins`), and the validator agent's, of
the same command over the same delivery. Its packet said «run `<command>`» under a prompt reading «run every pinned
probe», with «need not be run again» beside it. The second run observes nothing the first did not.

A check not exact that printed text its `expect` — a substring proxy — does not match is handed as that run too, with
what it printed: the output IS an observation (§10.2), and the validator decides from it, running the check itself
only where that output cannot show the behaviour. Measured: replay r1's validator re-ran the suite for ~11 min because
its pin expected «0 failed», a line green pytest never prints (it printed «5110 passed»). One the system did not run,
or that printed nothing, stays the validator's to run (`accounting.the_systems_run`).

CONTROL: render the command whatever `seen` says (`ran = False` in `packets._probe_line`) and the first and third tests
go red; hand every run as decided (`run = DECIDED`) and the second does.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.core.protocol.accounting import with_engine_observations
from gfso.core.protocol.procedure import probe_id
from gfso.core.types import Criteria, Probe
from gfso.packets import validator_packet
from tests.support import DENIAL_ENTRY, UNMODELLED_FAULT, make_engine

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY", "justification": "no precedent",
          "invalidation_condition": "one occurs", "p": 0.01, "impact": "the run stops and is resumed"}, DENIAL_ENTRY]
CMD = "python -m pytest -q -k long_suite_marker"


@pytest.fixture
def node(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "accepted_risks": _RISK, "criteria": [
        {"name": "suite", "description": "the suite passes",
         "check": [{"behaviour": "the suite", "command": CMD, "expect": "0 failed"}]}]}, assignee="me")
    e.wait_idle()
    t = e.graph.get_task("root")
    yield e, t, probe_id("suite", t.spec.criteria[0].check[0])
    e.stop()


def test_a_pinned_check_the_system_ran_is_handed_once_as_its_run(node):
    e, t, pid = node
    text = validator_packet(e, t, "built it", ".", seen={("root", pid): {"matched": True, "printed": True,
                                                                          "out": "3 passed, 0 failed"}})
    assert f"[{pid}] — the suite: the system RAN `{CMD}` on this delivery" in text and "never run it again" in text
    assert f"run `{CMD}`" not in text, text
    assert "it printed «3 passed, 0 failed»" in text, "told not to run it, the validator is not shown what it printed"


def test_a_pinned_check_the_system_could_not_run_is_the_validators_to_run(node):
    e, t, pid = node
    for seen in (None, {("root", pid): {"note": "not run: no shell to run it in"}},
                 {("root", pid): {"rc": 0, "printed": "", "matched": False}},
                 {("root", pid): {"rc": 127, "printed": "pytest: command not found", "matched": False}}):
        text = validator_packet(e, t, "built it", ".", seen=seen)
        assert f"run `{CMD}`" in text and "the system RAN" not in text, text


def test_a_pinned_check_whose_proxy_missed_is_handed_with_what_it_printed(node):
    """The replay r1 shape: green pytest printed «5110 passed», the pin expected «0 failed»."""
    e, t, pid = node
    text = validator_packet(e, t, "built it", ".", seen={("root", pid): {
        "rc": 0, "printed": "....\n5110 passed in 640s", "out": "5110 passed in 640s", "matched": False}})
    assert f"the system RAN `{CMD}` on this delivery" in text and "substring proxy" in text, text
    assert "5110 passed in 640s" in text, "the validator is not shown what the system's run printed"
    assert f"run `{CMD}`" not in text, text


def test_citing_what_the_systems_run_printed_is_evidence_for_the_record():
    """The record reads such a report as the packet hands it: a pass citing the pin with an `expect` that is part of
    what the system's run printed stands; one citing the missed proxy is ⊥ (`accounting._reproduced`)."""
    p = Probe("the suite", CMD, "0 failed")
    c = Criteria("suite", "the suite passes", check=(p,))
    pid = probe_id("suite", p)
    seen = {pid: {"rc": 0, "printed": "....\n5110 passed in 640s", "out": "5110 passed in 640s", "matched": False}}
    cite = lambda expect: [{"criterion": "suite", "verdict": "pass", "evidence": "the system's run", "behaviours":
                            ["the suite"], "probe": [{"id": pid, "command": CMD, "expect": expect,
                                                      "behaviour": "the suite"}]}]
    assert with_engine_observations(cite("5110 passed"), [c], {}, seen)[0]["verdict"] == "pass"
    assert with_engine_observations(cite("0 failed"), [c], {}, seen)[0]["verdict"] == "undecidable"


def test_an_exact_check_that_did_not_match_is_handed_as_decided(monkeypatch):
    """An exact pin's run decides it either way — an output other than its pin fails its criterion whatever the
    validator says — so one that did not match is handed as that run too, its output shown."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "accepted_risks": _RISK, "criteria": [
        {"name": "out", "description": "prints ok",
         "check": [{"behaviour": "prints ok", "command": "./tool", "expect": "ok", "exact": True}]}]}, assignee="me")
    e.wait_idle()
    t = e.graph.get_task("root")
    pid = probe_id("out", t.spec.criteria[0].check[0])
    text = validator_packet(e, t, "built it", ".", seen={("root", pid): {"matched": False, "printed": True,
                                                                          "out": "not ok"}})
    e.stop()
    assert "the system RAN `./tool` on this delivery" in text and "printed «not ok»" in text, text


def test_the_record_keeps_the_expect_the_validator_cited_for_an_own_pin(node):
    """Cited `{id, held, expect}` as the packet asks where the proxy missed, the stored record reads the line the
    validator cited from the system's output — not the pin's own, which that run did not print (critic over b4129a7)."""
    e, t, pid = node
    T.signal(e, "root", "ACCEPT", "me")
    T.signal(e, "root", "DELIVER", "me", result="built it")
    e.record_exec_verdict("root", "PASS", [], "val-1", require_probe=True, per_criterion=[
        {"criterion": "suite", "verdict": "pass", "evidence": "the system's run printed 5110 passed",
         "behaviours": ["the suite"], "probe": [{"id": pid, "held": True, "expect": "5110 passed"}], "divergences": []}])
    (probe,) = e.get_exec_verdict("root")["per_criterion"][0]["probe"]
    assert probe["expect"] == "5110 passed" and probe["command"] == CMD, probe
