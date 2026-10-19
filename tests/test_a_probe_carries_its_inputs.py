"""A pinned probe carries the files it reads, and nothing the executor writes can stand in for them.

Measured on `c_compiler` (2026-09-20/21): two central probes iterated over `torture_corpus/*.c` and
`reject_corpus/*.c`, corpora the EXECUTOR wrote. They grew from 60/36 files to 79 under a node that
closed with `procedure_moved_since_authoring: false` — a fixed command over an input that moved
while its digest did not. The corpus is now part of the probe: its digest moves when it does, and
the system lays it down at validation time in a directory the validator owns.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from gfso import packets, tools as T
from gfso.core.handlers.structural import check_procedure
import pytest

from gfso.core.protocol.procedure import (coverage, materialize_inputs, probe_id, procedure_digest, unrun_pinned,
                                          reads_an_unpinned_set, unread_inputs, unsafe_input_paths)
from gfso.engine.verdicts import criterion_version
from gfso.core.types import Criteria, Probe, Spec, TaskId, Task, State
from gfso.adapters.storage.sqlite import SqliteStorage
from tests.support import make_engine, REGISTER

_CMD = "for f in {inputs}/*.c; do ./cc $f || echo FAIL $f; done; echo done"


def _probe(**files) -> Probe:
    return Probe("compiles the corpus", _CMD, "done", files or {"a.c": "int main(){return 0;}"})


def test_the_two_shapes_a_door_hands_over_read_as_one():
    as_map = Probe.of({"behaviour": "b", "command": _CMD, "expect": "done",
                       "inputs": {"a.c": "x", "b.c": "y"}})
    as_list = Probe.of({"behaviour": "b", "command": _CMD, "expect": "done",
                        "inputs": [{"path": "b.c", "content": "y"}, {"path": "a.c", "content": "x"}]})
    assert as_map == as_list and as_map.inputs == (("a.c", "x"), ("b.c", "y"))
    assert Probe.of(as_map.to_dict()) == as_map


def test_a_probe_without_inputs_keeps_the_id_and_digest_it_had_before():
    p = Probe("b", "./cc t.c", "ok")
    assert probe_id("c", p) == f"c#{hashlib.sha256(b'./cc t.c').hexdigest()[:8]}"
    assert "inputs" not in p.to_dict()


def test_the_corpus_moving_moves_the_procedure_without_renaming_the_probe():
    """The digest is what says "the procedure moved"; the id is what a REPORT is matched by, and a
    report carries no inputs — so seeding the id with them would break the match for exactly the
    probes that pin a corpus, and demote an honest verdict."""
    before = [Criteria("c", "compiles", check=(_probe(**{"a.c": "int x;"}),))]
    grown = [Criteria("c", "compiles", check=(_probe(**{"a.c": "int x;", "b.c": "int y;"}),))]
    assert procedure_digest(before) != procedure_digest(grown)
    assert probe_id("c", before[0].check[0]) == probe_id("c", grown[0].check[0])
    assert criterion_version(before[0].description, [p.to_dict() for p in before[0].check])         != criterion_version(grown[0].description, [p.to_dict() for p in grown[0].check]),         "claim_drift reads the version — a swapped corpus must be visible there"


def test_the_corpus_is_laid_down_by_the_system_where_the_validator_looks(tmp_path):
    crit = [Criteria("c", "compiles", check=(_probe(**{"sub/a.c": "int x;"}),))]
    dirs = materialize_inputs(crit, tmp_path)
    (d,) = dirs.values()
    assert (d / "sub" / "a.c").read_text(encoding="utf-8") == "int x;"
    assert tmp_path in d.parents


def test_an_input_that_would_land_outside_its_directory_is_refused_at_admission(tmp_path):
    """At ADMISSION — through the door, not only in the helper: a corpus that cannot be laid down
    as pinned would be laid down in part, and a command over a strict subset of the pinned set is
    the defect this whole change is against, recreated by its own repair."""
    e = make_engine()
    e.start()
    for i, bad in enumerate(("../escape.c", "/etc/x", "C:/x.c", "")):
        crit = [Criteria("c", "compiles", check=(_probe(**{bad: "int x;"}),))]
        assert unsafe_input_paths(crit) == {"c": [bad]}
        out = T.create_task(e, f"leaf{i}", {"description": "a leaf", "accepted_risks": REGISTER,
            "criteria": [{"name": "c", "description": "compiles",
                          "check": [_probe(**{bad: "int x;"}).to_dict()]}]}, assignee="agent")
        assert "outside" in str(out).lower(), out
        assert e.graph.get_task(f"leaf{i}") is None
        with pytest.raises(ValueError):            # and never laid down in part
            materialize_inputs(crit, tmp_path / "m")
        assert not (tmp_path / "escape.c").exists()
        assert check_procedure(Task(TaskId("t"), Spec("goal", tuple(crit)),
                                    state=State.IDLE)).passed is False
    e.stop()


def test_inputs_the_command_never_names_are_said_not_refused():
    p = Probe("b", "./cc tests/*.c", "done", {"a.c": "int x;"})
    crit = [Criteria("c", "compiles", check=(p,))]
    assert unread_inputs(crit) == {"c": ["./cc tests/*.c"]}
    r = check_procedure(Task(TaskId("t"), Spec("goal", tuple(crit)), state=State.IDLE))
    assert r.passed and "{inputs}" in r.details


def test_the_inputs_survive_the_disk(tmp_path):
    spec = Spec("goal", (Criteria("c", "compiles", check=(_probe(),)),))
    back = SqliteStorage._spec_from_json(SqliteStorage._spec_to_json(spec))
    assert back.criteria[0].check[0].inputs == spec.criteria[0].check[0].inputs


def test_what_the_executor_wrote_cannot_stand_in_for_the_pinned_corpus(tmp_path):
    """The property, end to end: the command the validator is given reads the ISSUER's files.

    The delivery holds a file of the same name with different content — the shape the `c_compiler`
    corpus had — and the substituted command points away from it, at what the system wrote from the
    contract. Without the substitution the same command would read whatever the workspace held."""
    delivery = tmp_path / "workdir"
    (delivery / "sub").mkdir(parents=True)
    (delivery / "sub" / "a.c").write_text("int main(){return 1;}  /* the executor's own */",
                                          encoding="utf-8")
    e = make_engine()
    e.start()
    probe = Probe("compiles the corpus", "for f in {inputs}/sub/*.c; do ./cc $f; done", "done",
                  {"sub/a.c": "int main(){return 0;}"})
    T.create_task(e, "leaf", {"description": "a leaf",
                              "criteria": [{"name": "c", "description": "compiles",
                                            "check": [probe.to_dict()]}],
                              "accepted_risks": REGISTER},
                  assignee="agent")
    e.wait_idle()
    packet = packets._validator_packet(e, e.graph.get_task(TaskId("leaf")), "built it", str(delivery),
                                  str(tmp_path / "scratch"))
    laid = next(f for f in (tmp_path / "scratch" / "probe_inputs").rglob("a.c"))
    assert laid.read_text(encoding="utf-8") == "int main(){return 0;}"
    assert str(laid.parent.parent) in packet, "the command was not pointed at the pinned corpus"
    assert str(delivery) not in packet.split("Working directory")[0]
    e.stop()


def test_the_by_hand_door_lays_the_corpus_down_too():
    """The door where this project's false passes were measured must not be the one door this never
    reaches: a person validating by hand was shown a literal `{inputs}` and the only resolution
    available to them was the delivery — the defect, exactly."""
    e = make_engine()
    e.start()
    T.create_task(e, "leaf", {"description": "a leaf",
                              "criteria": [{"name": "c", "description": "compiles",
                                            "check": [_probe().to_dict()]}],
                              "accepted_risks": REGISTER},
                  assignee="agent")
    e.wait_idle()
    out = T.probe_inputs(e, "leaf")
    (one,) = out["probes"]
    assert "{inputs}" not in one["command"] and one["inputs_dir"] in one["command"]
    assert Path(one["inputs_dir"], "a.c").read_text(encoding="utf-8").startswith("int main")
    assert one["files"] == ["a.c"]
    e.stop()


def test_the_validator_is_handed_the_laid_down_directory_not_the_delivery(tmp_path):
    e = make_engine()
    e.start()
    T.create_task(e, "leaf", {"description": "a leaf",
                              "criteria": [{"name": "c", "description": "compiles",
                                            "check": [_probe().to_dict()]}],
                              "accepted_risks": REGISTER},
                  assignee="agent")
    e.wait_idle()
    packet = packets._validator_packet(e, e.graph.get_task(TaskId("leaf")), "built it", ".", str(tmp_path))
    laid = tmp_path / "probe_inputs"
    assert "{inputs}" not in packet and str(laid) in packet
    assert any(f.name == "a.c" for f in laid.rglob("*"))
    e.stop()


def test_the_executor_reads_the_inputs_its_contract_will_be_run_over(tmp_path):
    """The inputs are part of what will be RUN, so part of the executor's contract (Inv-1). Named without their
    contents, the c_compiler root executor searched the file system for them and read the plan's own copies (EVIDENCE_LOG §13.34).
    It gets a copy outside its place; the validator still lays its own from the contract."""
    e = make_engine()
    e.start()
    T.create_task(e, "leaf", {"description": "a leaf",
                              "criteria": [{"name": "c", "description": "compiles",
                                            "check": [_probe(**{"sub/a.c": "int main(){return 0;}"}).to_dict()]}],
                              "accepted_risks": REGISTER},
                  assignee="agent")
    e.wait_idle()
    work = tmp_path / "work"
    crits = packets._executor_packet(e, e.graph.get_task(TaskId("leaf")), str(work)).split("## Inputs")[0]
    assert "{inputs}/" not in crits, "the command still names a directory the executor cannot see"
    d = Path(re.search(r"= (\S*gfso-check-inputs-\S+?): the 1 file", crits).group(1))
    assert (d / "sub" / "a.c").read_text(encoding="utf-8") == "int main(){return 0;}"
    assert work not in d.parents, "a copy inside the executor's place would be delivered with the work"
    e.stop()


def test_the_record_counts_a_probe_the_gate_accepted(tmp_path):
    """A probe reported by its laid-down command and no id: the gate reads it through this round's inputs
    directories and accepts the PASS, so the closure's count must read it the same way — counted "never run" it put a
    false red into the record (GB_c_compiler_tmokgz344, root.vec 0/1 over a probe that ran)."""
    p = _probe(**{"a.c": "int x;"})
    crit = [Criteria("c", "compiles", check=(p,))]
    dirs = materialize_inputs(crit, tmp_path)
    ran = p.command.replace("{inputs}", next(iter(dirs.values())).as_posix())
    report = [{"criterion": "c", "verdict": "pass", "probe": [{"command": ran, "expect": "done"}]}]
    assert unrun_pinned(crit, report, dirs.items()) == {}, "the gate accepts it — the premise"
    assert coverage(crit, report, dirs.items())["pinned_probes_run"] == 1
