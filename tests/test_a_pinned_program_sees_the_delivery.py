"""A pinned program run from `{inputs}` sees the delivery through the contract, not through the environment.

Measured on E3 `json_parser` (2026-09-28): ten of the plan's thirteen probes were `python {inputs}/x.py` over a
program that does `import json_parser`. Python searches the script's own directory — the one the system lays
the inputs down in — not the working directory, so in a clean interpreter each raised ModuleNotFoundError; an
executor had written a `.pth` into the shared environment to make them pass, and one run's validator then
tested ANOTHER run's module through it. The authoring prompt said `PYTHONPATH=. python {inputs}/x.py` and was
broken twelve times of thirteen, so the rule now stands where the contract is admitted.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

import gfso.decompose as D
import gfso.engine as E
import gfso.engine.admission as A

from gfso import tools as T
from gfso.core.handlers.structural import check_procedure
from gfso.core.protocol.procedure import probes_off_the_workdir, shared_scratch
from gfso.core.types import AgentId, Criteria, Probe, Spec, State, Task, TaskId
from tests.support import make_engine, REGISTER

_IMPORTS_THE_DELIVERY = "import json_parser as j\nassert j.parse('1') == 1\nprint('OK')\n"


def _crit(command: str, files: dict | None = None) -> list[Criteria]:
    return [Criteria("parses", "parses a number",
                     check=(Probe("parses 1", command, "OK", files or {"p.py": _IMPORTS_THE_DELIVERY}),))]


@pytest.mark.parametrize("command", [
    "python {inputs}/p.py",
    "python3 -u {inputs}/p.py",
    "cd . && python \"{inputs}/p.py\"",
    "pytest -q {inputs}/p.py",
])
def test_a_program_that_imports_the_delivery_off_its_own_directory_is_named(command):
    assert probes_off_the_workdir(_crit(command)) == {"parses": [command]}


@pytest.mark.parametrize("command, files", [
    ("PYTHONPATH=. python {inputs}/p.py", None),                       # the contract names the path
    ("python -m pytest {inputs}/p.py", None),                          # -m puts the working directory first
    ("python -c \"import json_parser\"", None),                         # so does -c
    ("python {inputs}/p.py", {"p.py": "import json, sys\nprint(json.dumps(sys.argv))\n"}),   # stdlib only
    ("python {inputs}/p.py", {"p.py": "import helper\n", "helper.py": "X = 1\n"}),           # its own inputs
    ("python {inputs}/p.py", {"p.py": "import sys, os\nsys.path.insert(0, os.getcwd())\n"
                                      "import json_parser\n"}),                              # arranges its path
    ("./parser_cli < {inputs}/p.py", None),                            # not a Python program run
])
def test_what_already_sees_the_working_directory_is_left_alone(command, files):
    assert probes_off_the_workdir(_crit(command, files)) == {}


def test_the_contract_is_refused_at_admission_and_the_issuer_lifts_it_by_naming_the_path():
    """Through the doors — creation and revision — not only in the helper; the lift is the issuer's own honest
    act (§12.16 (ii)): the same program, run with the path it needs written into the command."""
    e = make_engine()
    e.start()
    raw = {"description": "a leaf", "accepted_risks": REGISTER}
    bad, good = _crit("python {inputs}/p.py"), _crit("PYTHONPATH=. python {inputs}/p.py")
    out = T.create_task(e, "leaf", {**raw, "criteria": [
        {"name": "parses", "description": "parses a number", "check": [bad[0].check[0].to_dict()]}]},
        assignee="agent")
    assert "PYTHONPATH=." in str(out), out
    assert e.graph.get_task("leaf") is None
    T.create_task(e, "leaf", {**raw, "criteria": [
        {"name": "parses", "description": "parses a number", "check": [good[0].check[0].to_dict()]}]},
        assignee="agent")
    t = e.graph.get_task("leaf")
    assert t is not None
    with pytest.raises(ValueError, match="PYTHONPATH"):
        e.revise(t.id, dataclasses.replace(t.spec, criteria=tuple(bad)), AgentId("agent"))
    e.stop()


def test_the_battery_shows_it_on_the_node():
    r = check_procedure(Task(TaskId("t"), Spec("goal", tuple(_crit("python {inputs}/p.py"))), state=State.IDLE))
    assert r.passed is False and "PYTHONPATH=." in r.details


@pytest.mark.parametrize("command, shared", [
    ("printf 'a' > /tmp/u1; ./uniq /tmp/u1", True),
    ("./cat /tmp/bigf 2>/tmp/err", True),
    ("seq 5 > /var/tmp/x && ./head /var/tmp/x", True),
    ("T=$(mktemp -d); printf 'a' > $T/u1; ./uniq $T/u1", False),
    ("./cat {inputs}/tmp/a.txt ./tmp/b.txt", False),
    ("mktemp -p /tmp", False),
    ("seq 3 > /tmp/.cu_$$; ./cat /tmp/.cu_$$", False),              # $$ makes it the run's own
    ("cd /tmp; printf 'a' > f1; ./uniq f1", True),                  # measured: 9 of 12 such in one plan
    ("D=/tmp; printf 'a' > $D/u1", True),
    ("printf a > /dev/shm/u1", True),
    ("f=$(mktemp /tmp/u.XXXXXX); printf a > $f", False),
    ("T=$(mktemp -d -p /tmp); printf a > $T/u", False),
    ("for sz in 1 2; do head -c $sz x > /tmp/B$sz; done", True),     # a loop variable is the same file each run
    ("cc t.c -o /tmp/$t && /tmp/$t", True),
])
def test_scratch_at_a_path_every_run_shares_is_named(command, shared):
    """Two nodes validated at once over `/tmp/u1` overwrite each other's files mid-check (the coreutils plan's
    `tail` and `uniq` both did): the verdict is then the schedule's, not the procedure's."""
    crit = [Criteria("c", "d", check=(Probe("b", command, "ok"),))]
    assert bool(shared_scratch(crit)) is shared


def test_shared_scratch_is_refused_at_admission():
    e = make_engine()
    e.start()
    out = T.create_task(e, "leaf", {"description": "a leaf", "accepted_risks": REGISTER, "criteria": [
        {"name": "c", "description": "d", "check": [{"behaviour": "b", "command": "seq 3 > /tmp/s; ./head /tmp/s",
                                                      "expect": "1"}]}]}, assignee="agent")
    assert "mktemp" in str(out) and e.graph.get_task("leaf") is None
    e.stop()


def test_the_plan_s_author_repairs_what_the_admission_would_refuse_before_the_build(monkeypatch):
    """A refusal met AT the build ended a 347-second authoring (coreutils, a shared `/tmp` path): the repair loop
    before the build knew only twin probes. Every probe shape a door refuses now goes back to the author first."""
    bad = {"name": "g", "check": [{"behaviour": "b", "command": "seq 3 > /tmp/s; ./head /tmp/s", "expect": "1"},
                                  {"behaviour": "p", "command": "python {inputs}/p.py", "expect": "OK",
                                   "inputs": {"p.py": _IMPORTS_THE_DELIVERY}}]}
    spec = {"root_criteria": [bad], "subtasks": []}
    lines = D._refused_probes(spec)
    assert len(lines) == 2 and any("mktemp" in x for x in lines) and any("PYTHONPATH=." in x for x in lines)
    told, built = [], []
    fixed = {"root_criteria": [{"name": "g", "check": [
        {"behaviour": "b", "command": "T=$(mktemp -d); seq 3 > $T/s; ./head $T/s", "expect": "1"},
        {"behaviour": "p", "command": "PYTHONPATH=. python {inputs}/p.py", "expect": "OK",
         "inputs": {"p.py": _IMPORTS_THE_DELIVERY}}]}]}
    monkeypatch.setattr(D, "_audit_fix", lambda llm, req, sp, problems, ex: told.append(problems) or fixed)

    def _stop(sp, *a, **k):
        built.append(sp)
        raise RuntimeError("stop at the build")
    monkeypatch.setattr(D, "build_graph_live", _stop)
    with pytest.raises(RuntimeError):
        D._build_verified(spec, "req", make_engine(), "root", "agent", llm=None)
    assert told and told[0] == lines, "told what the admission would refuse, before the build"
    assert not D._refused_probes(built[0]), "and the build got the repaired plan"


def test_a_contract_in_force_is_re_presented_though_a_rule_since_would_refuse_it(monkeypatch):
    """A re-ASSIGN keeping the criteria installs nothing (§12.10): it re-presents the contract the node was admitted
    under. Refusing it under a probe rule added since left a machine issuer's re-presentation refused and the node
    waiting for a move nobody would make (§12.16 (ii)). A contract that CHANGES is admitted on today's terms."""
    e = make_engine()
    e.start()
    old = Spec("a leaf", tuple(_crit("python {inputs}/p.py")))
    monkeypatch.setattr(A, "admission_defects", lambda crit: [])       # admitted before the rule existed
    e.assign_task(TaskId("n"), old, AgentId("boss"))
    e.wait_idle()
    monkeypatch.undo()
    e._revise(TaskId("n"), old, AgentId("boss"))                      # the same contract, re-presented
    e.wait_idle()
    assert e.graph.get_state(TaskId("n")) == State.OFFERED
    changed = Spec("a leaf, restated", tuple(_crit("python {inputs}/p.py")) + (
        Criteria("also", "another", check=(Probe("b", "true", "", ()),)),))
    with pytest.raises(ValueError):
        e._revise(TaskId("n"), changed, AgentId("boss"))
    e.stop()
