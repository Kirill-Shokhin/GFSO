"""The issuer ruling on a dispute stands where the validation stood: the inputs it laid, the findings over them, and
what retiring one of them lifts.

c_compiler, the system's own plan, AUTO haiku, 2026-11-06 (scratchpad/ccfull_diag): `root.preprocessor.pp-rest` rests
on its DONE part `ppcore`, so its validation runs ppcore's pinned checks (`parts_procedure`) and a validator's findings
over them stood under four of pp-rest's criteria, each running `{inputs:<ppcore's pin>}/c.pp`. Three defects of the
issuer's turn, each reproduced here in that shape. Its packet laid only pp-rest's own inputs and showed the findings'
commands with the token unresolved: the issuer could not open the file and ruled on the text. The executor's CHALLENGE
named a probe under one criterion and the issuer retired it under all four; the cut to what the dispute named read the
criterion written beside the hash, and three retirements went without a word — the part's pin kept running under those
criteria, four FAILs. And below an AUTO root the issuer was never told what retiring such a finding lifts, and held the
layout to be the part's contract.

CONTROLS (each test red on the code before, d2e6d6a): lay `task.spec.criteria` in `_ask`, or show `as_run` without
`laid`, and the inputs test goes red; read `findings.named` by the criterion written beside a hash and the ruling test
goes red; drop `ruled`'s refusal and the unknown-id test goes red; say the lift at an AUTO root only and the packet test
goes red.
"""
from __future__ import annotations

import dataclasses as dc
import json
import re
from pathlib import Path

import pytest

import gfso.tools as T
from gfso import issuer as I
from gfso.core.protocol.procedure import inputs_token, probe_id
from gfso.core.types import DoneReason, State, TaskId
from tests.support import criterion
from tests.test_the_issuer_answers_a_dispute import _ContactLLM
from tests.test_the_mode_decides_who_holds_what import Mode, _admit, _engine, _kid

WHOLE, PART = TaskId("root.pp"), "root.pp.core"
CRITS = ("conditional-errors-rejected", "ifndef-elif-nesting", "undef-and-line", "predefined-and-errors")
#: the part's pin: one output line per source line, over a pinned input
LAYOUT = {"behaviour": "skipped groups", "command": "cc -o $T/pp src/*.c && $T/pp {inputs}/c.pp 2>&1", "expect": "a\nd", "exact": True,
          "inputs": {"c.pp": "a\n#if 0\nb\n#endif\nd\n"}}


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _pin_id(e) -> str:
    (pid,) = {probe_id(c.name, p) for cs in e.parts_procedure(WHOLE).values() for c in cs for p in c.check
              if p.command == LAYOUT["command"]}
    return pid


def _layout_pinned(e) -> set:
    """The whole's criteria its part's layout pin still runs under."""
    return {k for k, cs in e.parts_procedure(WHOLE).items() for c in cs for p in c.check if p.command == LAYOUT["command"]}


def _pp_rest():
    """An AUTO plan's node below the root, every criterion resting on its DONE part's layout pin, the validator's finding
    over that pin standing under each of them — one probe, one hash — and its executor's CHALLENGE naming it under
    the first criterion only, as the real one did."""
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid(str(WHOLE), ["g"], *[criterion(c) for c in CRITS], description="the preprocessor's rest"))
    _admit(e, str(WHOLE), _kid(PART, CRITS, {"name": "pp-conditionals", "description": "skips", "check": [LAYOUT]}))
    e._graph.save_task(dc.replace(e.graph.get_task(TaskId(PART)), state=State.DONE, done_reason=DoneReason.PASS))
    run = LAYOUT["command"].replace("{inputs}", inputs_token(_pin_id(e)))   # the part's pin, run as the validator ran it
    found = {c: [{"id": probe_id(c, {"command": run}), "behaviour": "rests on the part's skipped groups",
                  "command": run, "as_run": run, "expect": "a d"}] for c in CRITS}
    e._graph._storage.store_critique(TaskId(f"{WHOLE}#regression-probes"), json.dumps(found))
    t = e.graph.get_task(WHOLE)
    if t.state == State.OFFERED:
        assert T.signal(e, str(WHOLE), "ACCEPT", str(t.assignee))["accepted"]
    h = probe_id("", {"command": run}).rsplit("#", 1)[-1]
    assert T.signal(e, str(WHOLE), "CHALLENGE", str(t.assignee),
                    reason=f"The part pins one layout and the exact pins the other: {CRITS[0]}#{h} cannot pass. "
                           f"The others rest on the same part checks.")["accepted"]
    e.wait_idle()
    return e, h


class _Sees(_ContactLLM):
    """The contact issuer, noting which paths its packet names exist while it runs."""

    def __init__(self, payload, ran):
        super().__init__(payload, ran)
        self.paths: dict = {}

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.paths = {p: Path(p).exists() for p in re.findall(r"\$T/pp (\S+?/c\.pp)", user)}
        return super().run_agent(system, user, allowed_tools, cwd, timeout)


def _rule(e, tmp_path, retire):
    llm = _Sees({"decision": "accept", "justification": "ran it: no one layout meets both", "retire_findings": retire},
                ran={"Bash": 1})
    out = I.answer_the_challenge(e, WHOLE, str(e.graph.issuer_of(WHOLE)), _llm=llm, where=str(tmp_path))
    e.wait_idle()
    return out, llm


def _standing(e) -> set:
    return {p["id"] for ps in e.regression_probes(WHOLE).values() for p in ps}


def test_the_issuer_runs_the_findings_over_the_inputs_the_validation_lays(tmp_path):
    e, h = _pp_rest()
    _, llm = _rule(e, tmp_path, [])
    findings = llm.packets[0].split("## The validator's findings standing on this node", 1)[1]
    assert "{inputs:" not in findings, "a finding's command shown with its token unresolved"
    assert llm.paths and all(llm.paths.values()), f"the part's inputs were not laid where the packet says: {llm.paths}"
    e.stop()


def test_a_probe_ruled_out_under_every_criterion_it_stands_on_lifts_the_part_pin_under_each(tmp_path):
    e, h = _pp_rest()
    assert _layout_pinned(e) == set(CRITS)
    out, _ = _rule(e, tmp_path, [f"{c}#{h}" for c in CRITS])
    assert out["status"] == "accepted", out
    assert _standing(e) == set(), f"retirements dropped without a word: {_standing(e)}"
    assert _layout_pinned(e) == set(), "the part's pin still runs where its finding was retired"
    e.stop()


def test_a_ruling_naming_what_stands_nowhere_is_refused_by_name(tmp_path):
    e, h = _pp_rest()
    out, _ = _rule(e, tmp_path, [f"{CRITS[0]}#{h}", "conditionals#deadbeef"])
    assert out["status"] == "refused" and "conditionals#deadbeef" in out["why"], out
    assert len(_standing(e)) == len(CRITS) and e.graph.get_state(WHOLE) == State.CHALLENGED
    e.stop()


def test_below_the_root_the_issuer_is_told_what_retiring_a_finding_over_a_part_pin_lifts(tmp_path):
    e, h = _pp_rest()
    _, llm = _rule(e, tmp_path, [])
    said = llm.packets[0]
    assert "only say a settled part's pinned check does not hold" in said and f"{CRITS[1]}#{h}" in said
    assert "stops running that check under" in said
    e.stop()
