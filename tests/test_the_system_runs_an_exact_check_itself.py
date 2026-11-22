"""A pinned probe whose `expect` is the whole printed output (`exact`) is run by the system itself on a fresh copy of
the delivery, before and apart from the validator, and where it printed otherwise the criterion fails whatever the
validator said.

Before it a pinned probe "held" on the validator's word alone, and FM-3 has no structural guard (§9.10): the false
PASS is the defect, a false FAIL costs a round. Inv-2 (§12.8): an observed divergence is that criterion's fail. The
first cut ran it in the validator's copy after the validator, read stdout alone and skipped a node with no place of
its own: correct work printing to stderr, or a probe that creates its state, failed (critic over 38c16f9).

CONTROLS (each breaks exactly its test): drop the stderr arm of `observe.printed` — the stderr test; run
`_observe_pins` after `_validator_texts` — the stateful test; require `_NODES in workdir` in `_observe_pins` — the
no-place test; drop the `blind` note in `with_engine_observations` — the not-observed test; `_observe_pins` → {} —
the mismatch tests."""
from __future__ import annotations

import json
import subprocess

import pytest

from tests.support import committed

from gfso import tools as T
from gfso import observe, tools_llm as TL
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.core.protocol.procedure import part_credit, probe_id, procedure_digest, with_engine_observations
from gfso.core.types import Criteria, Probe, Spec
from gfso.engine.verdicts import criterion_version
from gfso.observe import observe_place
from gfso.packets import observed_lines
from gfso.adapters.execution import LocalExecution
from gfso.workspaces import execution_of
from tests.test_the_executor_starts_from_what_its_checks_print import _node
from tests.test_validate_result import _eng, _fenced

CMD = "cat out.txt"
#: creates the state it reads: a second run in the same tree prints otherwise
STATEFUL = "if [ -e t.db ]; then echo 'Error: table t already exists'; else touch t.db; echo created; fi"


class _Says:
    """A validator that passes `c` and cites its pinned probe as held, whatever the place holds — having run it in its
    working directory first where `runs`."""
    def __init__(self, cmd, expect, runs=False, edit=None):
        self.cmd, self.expect, self.runs, self.edit = cmd, expect, runs, edit
        self.calls, self.last_tool_calls, self.on_tick, self.stage_hint = [], {"Bash": 1}, None, ""

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        if self.edit:
            subprocess.run([LocalExecution().shell(), "-c", self.edit], cwd=cwd, capture_output=True)
        if self.runs:
            subprocess.run([LocalExecution().shell(), "-c", self.cmd], cwd=cwd, capture_output=True)
        self.calls.append({"duration_ms": 1, "input_tokens": 1, "output_tokens": 1})
        return _fenced({"verdict": "PASS", "failed_criteria": [], "per_criterion": [
            {"criterion": "c", "verdict": "pass", "evidence": "ran it, it printed what it pins",
             "behaviours": ["it greets"], "divergences": [],
             "probe": [{"id": probe_id("c", {"command": self.cmd}), "behaviour": "it greets", "command": self.cmd,
                        "expect": self.expect, "held": True}]}]})

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def _validated(tmp_path, printed: str, exact: bool = True, cmd: str = CMD, expect: str = "hello", runs=False,
               node=True, before=lambda e: None, cite: str = None, edit: str = None, keep=None) -> dict:
    # a node's own place (its validation runs in a copy of it) — or a shared one, which the validator works in itself
    place = tmp_path / ".gfso-nodes-p" / "n" if node else tmp_path / "work"
    place.mkdir(parents=True)
    (place / "out.txt").write_text(printed + "\n")
    e = _eng()
    T.create_task(e, "n", {"description": "greet", "criteria": [{"name": "c", "description": "prints hello", "check": [
        {"behaviour": "it greets", "command": cmd, "expect": expect, "exact": exact}]}]}, "alice")
    if keep is not None:
        keep["e"] = e
    T.signal(e, "n", "ACCEPT", "alice")
    T.signal(e, "n", "DELIVER", "alice", result="out.txt", _recorded=committed(place))
    before(e)
    try:
        return TL.validate_result(e, "n", _llm=_Says(cmd, expect if cite is None else cite, runs, edit),
                                  workdir=str(place))
    finally:
        e.stop()


@pytest.mark.parametrize("batch", ["0", "1"])      # one run of the whole contract; runs each carrying a share
def test_a_held_exact_probe_that_prints_otherwise_fails(tmp_path, monkeypatch, batch):
    monkeypatch.setenv("GFSO_VALIDATION_BATCH", batch)
    out = _validated(tmp_path, "goodbye")
    assert out["verdict"] == "FAIL" and out["failed_criteria"] == ["c"], out
    why = json.dumps(out)
    assert probe_id("c", {"command": CMD}) in why and "goodbye" in why and "hello" in why, why


def test_a_held_exact_probe_that_prints_it_passes(tmp_path):
    assert _validated(tmp_path, "hello")["verdict"] == "PASS"


def test_correct_work_that_prints_its_error_to_stderr_passes(tmp_path):
    assert _validated(tmp_path, "Error: no such table t", cmd="cat out.txt >&2",
                      expect="Error: no such table t")["verdict"] == "PASS"


def test_a_probe_that_creates_its_state_passes_though_the_validator_ran_it_first(tmp_path):
    """The validator of a shared place works in the place itself and leaves `t.db` there: the system's run is the
    delivery's, made before it."""
    assert _validated(tmp_path, "", cmd=STATEFUL, expect="created", runs=True, node=False)["verdict"] == "PASS"


def test_a_node_with_no_place_of_its_own_still_gets_the_system_s_run(tmp_path):
    out = _validated(tmp_path, "goodbye", node=False)
    assert out["verdict"] == "FAIL" and out["failed_criteria"] == ["c"], out


def test_a_probe_the_system_could_not_run_is_recorded_as_the_validator_s_word(tmp_path, monkeypatch):
    seen = {}

    def _no_shell(e):
        # …no shell for the system's own run alone: the judge's copy is made with one (`snapshots._checkout`)
        real, kind = TL._observe_pins, type(execution_of(e))

        def _shell_less(*a, **k):
            with monkeypatch.context() as m:
                m.setattr(kind, "shell", lambda self: None)
                return real(*a, **k)
        monkeypatch.setattr(TL, "_observe_pins", _shell_less)
        seen["e"] = e
    assert _validated(tmp_path, "goodbye", before=_no_shell)["verdict"] == "PASS"
    evidence = json.dumps(T.get_verdict(seen["e"], "n", _trim=False))
    assert f"did not run exact pinned check {probe_id('c', {'command': CMD})} itself (not run: no shell" in evidence
    assert "the validator's word" in evidence, evidence


def test_the_packet_matches_an_exact_check_by_the_same_rule_and_says_it_does_not(tmp_path):
    (tmp_path / "out.txt").write_text("Error: no such table t\n")
    committed(tmp_path)                     # …the observation reads the place's commit
    e, t = _node({"behaviour": "errs", "command": "cat out.txt >&2", "expect": "Error: no such table t", "exact": True},
                 {"behaviour": "greets", "command": "cat out.txt", "expect": "hello", "exact": True})
    rows = observe_place(e, [t], str(tmp_path))["root"]
    assert [r.get("matched") for r in rows] == [True, False]
    assert observed_lines(rows).count("the system's own run of this EXACT check does not match") == 1


_OLD = [Criteria("out", "prints hi", check=(Probe("greets", "echo hi", "hi"),
                                            Probe("files", "cat {inputs}/a", "x", (("a", "x"),))))]


def test_a_probe_stored_before_exact_keeps_its_digest_and_version():
    """Computed on main before the field existed (98ea31f)."""
    assert procedure_digest(_OLD) == "22e254cd570381c8"
    assert criterion_version("prints hi", [p.to_dict() for p in _OLD[0].check]) == [
        "prints hi", [["greets", "echo hi", "hi", []], ["files", "cat {inputs}/a", "x", [["a", "x"]]]]]
    assert [probe_id("out", p) for p in _OLD[0].check] == ["out#56a79f3b", "out#f1e846c3"]
    assert "exact" not in _OLD[0].check[0].to_dict()
    now = [Criteria("out", "prints hi", check=(Probe("greets", "echo hi", "hi", exact=True), _OLD[0].check[1]))]
    assert procedure_digest(now) != "22e254cd570381c8", "dropping `exact` loosens the check: the digest says so"
    assert criterion_version("prints hi", [p.to_dict() for p in now[0].check]) != criterion_version(
        "prints hi", [p.to_dict() for p in _OLD[0].check])


def test_exact_travels_through_every_door():
    p = Probe.of({"behaviour": "b", "command": "echo hi", "expect": "hi", "exact": True})
    assert p.exact and Probe.of(p.to_dict()) == p and not Probe.of({"command": "x", "exact": "yes"}).exact
    spec = Spec("d", (Criteria("c", "c holds", check=(p,)),))
    assert SqliteStorage._spec_from_json(SqliteStorage._spec_to_json(spec)).criteria[0].check[0].exact


@pytest.mark.parametrize("matched, verdict", [(False, "fail"), (True, "pass"), (None, "pass")])
def test_a_part_probe_held_is_overruled_only_by_a_mismatch_the_system_saw(matched, verdict):
    """The part's probe, cited `held: true` under the whole's criterion: credited unless the system saw it print other
    than its pin — then it is held by nobody, and the criterion resting on it fails (`part_credit` reads the result)."""
    part = Criteria("kid/k", "k holds", check=(Probe("k", "./k", "7", exact=True),))
    pid = probe_id(part.name, part.check[0])
    parts = {"g": (part,)}
    report = [{"criterion": "g", "verdict": "pass", "evidence": "ok", "probe": [{"id": pid, "held": True}]}]
    seen = {} if matched is None else {pid: {"matched": matched, "out": "8"}}
    (e,) = with_engine_observations(report, (Criteria("g", "g holds"),), parts, seen)
    assert e["verdict"] == verdict
    credited, _ = part_credit(parts, [e])
    assert (pid in credited) == (verdict == "pass")


# A pin that is NOT exact is run by the system too, its `expect` read as a part of what it prints; a PASS over it stands
# only where that run shows the pin's `expect` or the one the report cites — else ⊥, never a FAIL (an `expect` in
# words shows in no output). CONTROLS: `contains` → `shows` in `observe.printed` — the substring test; `_reproduced`
# returning `e` — the two ⊥ tests; drop the cited arm of `_reproduced` — the words test.

def test_a_pin_not_exact_whose_output_shows_its_expect_as_a_part_passes(tmp_path):
    """…the pin's own `expect` decides, whatever the report cites."""
    assert _validated(tmp_path, "well, hello there", exact=False, cite="nothing it printed")["verdict"] == "PASS"


def test_a_pass_over_a_pin_not_exact_the_delivery_does_not_reproduce_is_no_verdict(tmp_path):
    keep = {}
    out = _validated(tmp_path, "goodbye", exact=False, keep=keep)
    assert out["verdict"] is None and out.get("failed_criteria") in (None, []), out
    assert "which shows neither 'hello' nor what the report cites" in out["verdict_defects"], out


def test_a_pin_in_words_passes_on_the_part_of_the_system_s_run_the_report_cites(tmp_path):
    assert _validated(tmp_path, "hello", exact=False, expect="it greets the user", cite="hello")["verdict"] == "PASS"


def test_a_pin_in_words_with_a_citation_the_delivery_does_not_print_is_no_verdict(tmp_path):
    """The validator changed what it ran over (here: its copy's `out.txt`) and cites what it then saw."""
    out = _validated(tmp_path, "goodbye", exact=False, expect="it greets the user", cite="hello",
                     edit="echo hello > out.txt")
    assert out["verdict"] is None, out


# A pin not exact the system ran and got no answer from: past its bound or past the observation's budget, ⊥ as an exact
# pin's; a 126/127 over a program the delivery names by a path, the delivery's FAIL; a 126/127 over a bare name, or an
# empty output, the validator's word. CONTROLS: `unseen` over exact pins only — the two ⊥ tests; `delivery_lacks` →
# False — the path test; drop `o.get("rc") not in NOT_RUN_RC` from `unshown` — the bare-name test; drop the
# `printed`-is-not-blank clause from `unshown` — the empty test.

def test_a_pin_not_exact_past_its_bound_is_no_verdict(tmp_path, monkeypatch):
    monkeypatch.setattr(observe, "PROBE_S", 1)
    out = _validated(tmp_path, "hello", exact=False, cmd="sleep 3; cat out.txt")
    assert out["verdict"] is None and "did not finish" in out["verdict_defects"], out


def test_a_pin_not_exact_the_observations_budget_left_unrun_is_no_verdict(tmp_path, monkeypatch):
    monkeypatch.setattr(TL, "OBSERVE_S", 0)
    monkeypatch.setattr(TL, "FRESH_S", 0)
    assert _validated(tmp_path, "hello", exact=False)["verdict"] is None


def test_a_pin_not_exact_whose_program_the_delivery_lacks_fails(tmp_path):
    out = _validated(tmp_path, "hello", exact=False, cmd="./prog")
    assert out["verdict"] == "FAIL" and out["failed_criteria"] == ["c"], out


def test_a_pin_not_exact_whose_bare_named_program_the_shell_did_not_find_is_the_validators_word(tmp_path):
    assert _validated(tmp_path, "hello", exact=False, cmd="no_such_tool_here")["verdict"] == "PASS"


def test_a_pin_not_exact_whose_correct_output_is_empty_is_the_validators_word(tmp_path):
    out = _validated(tmp_path, "", exact=False, expect="Empty output")
    assert out.get("verdict") == "PASS", out
