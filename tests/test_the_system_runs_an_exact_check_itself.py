"""A pinned probe whose `expect` is the whole printed output (`exact`) is run by the system itself in the copy the
validator worked in, and where it printed otherwise the criterion fails whatever the validator said.

Before it a pinned probe "held" on the validator's word alone, and FM-3 has no structural guard (§9.10): the false
PASS is the defect, a false FAIL costs a round. Inv-2 (§12.8): an observed divergence is that criterion's fail.

CONTROL: make `tools_llm._observe_exact` return {} — `test_a_held_exact_probe_that_prints_otherwise_fails` goes red
and nothing else here does."""
from __future__ import annotations

import json

import pytest

from gfso import tools as T
from gfso import tools_llm as TL
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.core.protocol.procedure import part_credit, probe_id, procedure_digest, with_engine_observations
from gfso.core.types import Criteria, Probe, Spec
from gfso.engine.verdicts import criterion_version
from tests.test_validate_result import _eng, _fenced

CMD = "cat out.txt"
PID = probe_id("c", {"command": CMD})


class _Says:
    """A validator that passes `c` and cites its pinned probe as held, whatever the place holds."""
    def __init__(self):
        self.calls, self.last_tool_calls, self.on_tick, self.stage_hint = [], {"Bash": 1}, None, ""

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        self.calls.append({"duration_ms": 1, "input_tokens": 1, "output_tokens": 1})
        return _fenced({"verdict": "PASS", "failed_criteria": [], "per_criterion": [
            {"criterion": "c", "verdict": "pass", "evidence": "ran it, it printed hello", "behaviours": ["it greets"],
             "divergences": [],
             "probe": [{"id": PID, "behaviour": "it greets", "command": CMD, "expect": "hello", "held": True}]}]})

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def _validated(tmp_path, printed: str, exact: bool = True) -> dict:
    place = tmp_path / ".gfso-nodes-p" / "n"      # a node's own place: its validation runs in a copy of it
    place.mkdir(parents=True)
    (place / "out.txt").write_text(printed + "\n")
    e = _eng()
    T.create_task(e, "n", {"description": "greet", "criteria": [{"name": "c", "description": "prints hello", "check": [
        {"behaviour": "it greets", "command": CMD, "expect": "hello", "exact": exact}]}]}, "alice")
    T.signal(e, "n", "ACCEPT", "alice")
    T.signal(e, "n", "DELIVER", "alice", result="out.txt")
    try:
        return TL.validate_result(e, "n", _llm=_Says(), workdir=str(place))
    finally:
        e.stop()


@pytest.mark.parametrize("batch", ["0", "1"])      # one run of the whole contract; runs each carrying a share
def test_a_held_exact_probe_that_prints_otherwise_fails(tmp_path, monkeypatch, batch):
    monkeypatch.setenv("GFSO_VALIDATION_BATCH", batch)
    out = _validated(tmp_path, "goodbye")
    assert out["verdict"] == "FAIL" and out["failed_criteria"] == ["c"], out
    why = json.dumps(out)
    assert PID in why and "goodbye" in why and "hello" in why, why


def test_a_held_exact_probe_that_prints_it_passes(tmp_path):
    assert _validated(tmp_path, "hello")["verdict"] == "PASS"


def test_a_probe_not_exact_stands_on_the_validator_s_word(tmp_path):
    assert _validated(tmp_path, "goodbye", exact=False)["verdict"] == "PASS"


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
