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
import random
from pathlib import Path

import pytest

import gfso.decompose as D
import gfso.engine as E
import gfso.engine.admission as A

from gfso import tools as T
from gfso.core.handlers.structural import check_procedure
from gfso.core.protocol.procedure import (admission_defects, probes_off_the_workdir, probes_unittest_cannot_import,
                                        shared_scratch)
from gfso.core.protocol.shell import commands
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
    # …and the shapes the first guard let by (ENG_QUEUE P1, reproduced 2026-11-14): each runs the program off a path
    # that does not hold the delivery, as the shapes above do
    "cd {inputs} && python p.py",
    "cd \"{inputs}\" && python3 p.py",
    "PYTHONPATH=. python -I {inputs}/p.py",                            # -I and -E ignore PYTHONPATH
    "PYTHONPATH=. python -E {inputs}/p.py",
    "py.test {inputs}/p.py",
    "/usr/bin/python3 {inputs}/p.py",
    "python3.11 {inputs}/p.py",
    "cd {inputs} && PYTHONPATH=. python p.py",                         # `.` is now the probe's own directory
    # …and what a pattern over the whole string still let by (critic, 2026-11-14): the shell's own reading decides
    "PYTHONPATH=. python {inputs}/a.py && python {inputs}/p.py",       # a prefix sets the first command only
    "cd {inputs} && python -m pytest -q p.py",
    "cd {inputs} && python -m p",
    "python3 -X dev {inputs}/p.py",
    "pytest -k parse {inputs}/p.py",
    "cd {inputs} && python ./p.py",
    "bash -c 'cd {inputs} && python p.py'",
    "cd {inputs} && PYTHONPATH=$PYTHONPATH:. python p.py",
    # …and what a split that gave up, or read flags and variables word by word, still let by (critic 4, 2026-11-14),
    # each verdict taken from a real run
    "python -Ic 'import json_parser'",                                  # -I before -c: the directory is dropped
    "cd {inputs} && python -Im pytest p.py",
    "cd {inputs} && python -m pytest -o pythonpath=. p.py",            # relative to where pytest starts
    "PYTHONPATH=.; python {inputs}/p.py",                              # a shell variable, never exported
    "{ cd {inputs}; python p.py; }",                                   # a brace group is no subshell
    "{ cd {inputs}; }; PYTHONPATH=. python p.py",
    "python {inputs}/p.py  # it's the parser's own check",             # an apostrophe in a comment
    "echo 'a;b' && cd {inputs} && python p.py",
    "out=$(cd {inputs} && python p.py) && test \"$out\" = OK",         # a command substitution runs too
    "python3 \"{inputs}/p.py\" 2>&1 | tee /dev/null",
    "for f in {inputs}/*.py; do python \"$f\"; done",
])
def test_a_program_that_imports_the_delivery_off_its_own_directory_is_named(command):
    assert probes_off_the_workdir(_crit(command)) == {"parses": [command]}


_TEST_FILE = {"test_p.py": "import unittest\nimport json_parser\n\n\nclass Case(unittest.TestCase):\n"
                           "    def test_one(self):\n        self.assertEqual(json_parser.parse('1'), 1)\n"}


_FROM_ITS_FILE = "import os, sys\nsys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))\nimport json_parser\n"


@pytest.mark.parametrize("command, files", [
    # a path a program adds from where IT lies is `{inputs}` or above it, never the delivery (critic 5, run in a
    # container: ModuleNotFoundError each) — the boilerplate a model writes picturing `{inputs}` as `tests/`
    ("python3 {inputs}/p.py", {"p.py": _FROM_ITS_FILE}),
    ("python3 {inputs}/p.py", {"p.py": "import sys\nfrom pathlib import Path\n"
                                       "sys.path.insert(0, str(Path(__file__).resolve().parent.parent))\n"
                                       "import json_parser\n"}),
    ("python3 {inputs}/p.py", {"p.py": "import os, sys\nROOT = os.path.dirname(os.path.abspath(__file__))\n"
                                       "sys.path.insert(0, ROOT)\nimport json_parser\n"}),
    ("python3 {inputs}/p.py", {"p.py": "# no sys.path tricks needed\nimport json_parser\n"}),
    ("pytest -q {inputs}/test_p.py", {**_TEST_FILE, "conftest.py": "import os, sys\n"
                                      "sys.path.insert(0, os.path.dirname(__file__))\n"}),
    ("cd {inputs} && cd .. && python3 -m pytest -q", _TEST_FILE),     # the parent of `{inputs}` holds it
    ("cd {inputs} && python3 -m doctest t.txt", {"t.txt": ">>> import json_parser\n>>> json_parser.parse('1')\n1\n"}),
    # a pinned script runs what it names, from where it says
    ("bash {inputs}/run.sh", {"run.sh": "python3 \"$(dirname \"$0\")/p.py\"\n", "p.py": _IMPORTS_THE_DELIVERY}),
    ("sh {inputs}/run.sh", {"run.sh": "cd \"$(dirname \"$0\")\"; python3 p.py\n", "p.py": _IMPORTS_THE_DELIVERY}),
    ("bash -euo pipefail {inputs}/run.sh", {"run.sh": "cd \"$(dirname \"$0\")\" && python3 p.py\n",
                                            "p.py": _IMPORTS_THE_DELIVERY}),
    # …however the script asks where it lies (critic 6, each run in a container: ModuleNotFoundError)
    *[("bash {inputs}/run.sh", {"run.sh": body, "p.py": _IMPORTS_THE_DELIVERY}) for body in (
        'SCRIPT_DIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"\npython3 "$SCRIPT_DIR/p.py"\n',
        'DIR="$(cd "$(dirname "$0")" >/dev/null 2>&1 && pwd)"; cd "$DIR"; python3 p.py\n',
        'DIR="$(dirname "$(readlink -f "$0")")"\npython3 "$DIR/p.py"\n',
        'DIR=$(cd "$(dirname "$0")" && pwd -P)\npython3 "$DIR/p.py"\n',
        'DIR="$(dirname "$(realpath "$0")")"; cd "$DIR" && python3 p.py\n',
        'python3 "${0%/*}/p.py"\n')],
])
def test_what_a_probe_runs_through_its_own_files_is_read(command, files):
    assert probes_off_the_workdir(_crit(command, files)) == {"parses": [command]}


@pytest.mark.parametrize("command", [
    "diff <(python3 {inputs}/p.py) <(echo OK)",                       # a process substitution runs its command
    "bash -o pipefail -c 'python3 {inputs}/p.py | cat'",
    "I={inputs}; python3 $I/p.py",                                     # `{inputs}` held in a variable
    "I={inputs}; cd $I && python3 p.py",
    "chmod +x {inputs}/p.py && {inputs}/p.py",                         # run by its `#!`
    "function f { cd {inputs}; python3 p.py; }; f",
    "eval 'cd {inputs} && python3 p.py'",
    "PYTHONSAFEPATH=1 python3 -c 'import json_parser'",               # as -P: the directory is dropped
    "bash -eo pipefail -c 'python3 {inputs}/p.py'",                    # each o of a cluster takes the next word
    "bash -euo pipefail -c 'cd {inputs} && python3 p.py'",
    "cd {inputs} && PYTHONPATH=$(pwd) python3 p.py",                   # the current directory is `{inputs}` there
    "cd {inputs} && PYTHONPATH=$PWD python3 p.py",
])
def test_the_shell_s_less_common_forms_are_read_as_it_runs_them(command):
    assert probes_off_the_workdir(_crit(command)) == {"parses": [command]}


@pytest.mark.parametrize("command", [
    "cd {inputs} && python -m unittest",                               # discovery: test*.py from here
    "cd {inputs} && python -m unittest -v test_p.Case",                # a module by its dots, with its class
    "cd {inputs} && python -m unittest discover -p 'test_*.py'",
    "python -I -m unittest discover -s {inputs}",
])
def test_unittest_runs_what_it_discovers_or_is_named(command):
    assert probes_off_the_workdir(_crit(command, _TEST_FILE)) == {"parses": [command]}


@pytest.mark.parametrize("command, files", [
    ("PYTHONPATH=. python {inputs}/p.py", None),                       # the contract names the path
    ("python -m pytest {inputs}/p.py", None),                          # -m puts the working directory first
    ("python -c \"import json_parser\"", None),                         # so does -c
    ("python {inputs}/p.py", {"p.py": "import json, sys\nprint(json.dumps(sys.argv))\n"}),   # stdlib only
    ("python {inputs}/p.py", {"p.py": "import helper\n", "helper.py": "X = 1\n"}),           # its own inputs
    ("python {inputs}/p.py", {"p.py": "import sys, os\nsys.path.insert(0, os.getcwd())\n"
                                      "import json_parser\n"}),                              # arranges its path
    ("./parser_cli < {inputs}/p.py", None),                            # not a Python program run
    ("python p.py", None),                                             # a program of the delivery's own, run there
    ("PYTHONPATH=$PWD python {inputs}/p.py", None),                    # a path the contract names, not relative
    ("cd {inputs} && PYTHONPATH=/work python p.py", None),
    ("cd {inputs} && PYTHONPATH=\"$OLDPWD\" python p.py", None),       # quoted, still the working directory
    ("(cd {inputs} && make) && PYTHONPATH=. python {inputs}/p.py", None),   # the subshell's cd ends with it
    ("cd {inputs} && cd - && python p.py", None),                      # back out: the delivery's own p.py
    ("export PYTHONPATH=$PWD && cd {inputs} && python p.py", None),
    ("PYTHONPATH=. python -W error {inputs}/p.py", None),              # -W's value is not -E
    ("python {inputs}/p.py", {"p.py": "import helper\n", "helper.py": "import os\n"}),   # its helper too
    ("pytest -q {inputs}/p.py", {"p.py": "import subprocess, pytest\n"}),                 # the runner, not the delivery
    ("PYTHONPATH=.; export PYTHONPATH; python {inputs}/p.py", None),   # set, then exported
    ("PYTHONPATH=. bash -c 'python {inputs}/p.py'", None),             # the environment is carried in
    ("pytest -o pythonpath=. {inputs}/p.py", None),
    ("pytest -opythonpath=. {inputs}/p.py", None),
    ("pytest --override-ini=pythonpath=. {inputs}/p.py", None),
    ("python -m unittest discover -s {inputs}", _TEST_FILE),           # -m puts the working directory first
    ("cd {inputs} | true; python p.py", None),                         # a piped cd runs in its own subshell
    ("cat <<EOF > note\ncd {inputs}\nEOF\npython p.py", None),         # a here-document is text, not commands
    ("python -Im json_parser.cli", None),                              # the delivery's module: not this guard's
    ("declare -x PYTHONPATH=.; python3 {inputs}/p.py", None),          # every way a variable is exported
    ("export PYTHONPATH; PYTHONPATH=.; python3 {inputs}/p.py", None),
    ("set -a; PYTHONPATH=.; python3 {inputs}/p.py", None),
    ("diff <(PYTHONPATH=. python3 {inputs}/p.py) <(echo OK)", None),
    ("python {inputs}/p.py", {"p.py": "import sys\nsys.path.insert(0, '.')\nimport json_parser\n"}),
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
        assignee="user")
    assert "PYTHONPATH=." in str(out), out
    assert e.graph.get_task("leaf") is None
    T.create_task(e, "leaf", {**raw, "criteria": [
        {"name": "parses", "description": "parses a number", "check": [good[0].check[0].to_dict()]}]},
        assignee="user")
    t = e.graph.get_task("leaf")
    assert t is not None
    with pytest.raises(ValueError, match="PYTHONPATH"):
        e.revise(t.id, dataclasses.replace(t.spec, criteria=tuple(bad)), AgentId("user"))
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
                                                      "expect": "1"}]}]}, assignee="user")
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
        D._build_verified(spec, "req", make_engine(), "root", "user", llm=None)
    assert told and told[0] == lines, "told what the admission would refuse, before the build"
    assert not D._refused_probes(built[0]), "and the build got the repaired plan"


def test_a_field_the_repairer_re_emits_as_null_keeps_the_plan_s_own(monkeypatch):
    """`"subtasks": null` in a repair patch replaced the split with nothing, and the rebuild crashed on it (c_compiler,
    haiku, 2026-10-31): a field re-emitted as null is not re-emitted."""
    spec = {"root_criteria": [{"name": "c", "check": [{"behaviour": "b", "command": "./prog --c", "expect": "0"}]}],
            "subtasks": [{"id": "a", "criteria": [{"name": "k", "check": [{"behaviour": "b", "command": "./prog --c",
                                                                         "expect": "0"}]}]}], "mappings": []}
    built, rounds = [], iter([["a mapping drifted"], []])
    monkeypatch.setattr(D, "build_graph_live", lambda sp, *a, **k: built.append(sp) or (None, "root", []))
    monkeypatch.setattr(D, "_problems", lambda *a, **k: next(rounds))
    monkeypatch.setattr(D, "_audit_fix", lambda *a, **k: {"subtasks": None, "mappings": [{"criterion": "c", "child_id": "a"}]})
    D._build_verified(spec, "req", make_engine(), "root", "user", llm=None)
    assert len(built) == 2 and built[-1]["subtasks"] == spec["subtasks"] and built[-1]["mappings"] == [{"criterion": "c", "child_id": "a"}]


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


def test_the_delivery_imported_through_a_pinned_helper_is_named():
    files = {"p.py": "import helper\nprint(helper.X)\n", "helper.py": "import json_parser\nX = json_parser.parse('1')\n"}
    assert probes_off_the_workdir(_crit("python {inputs}/p.py", files)) == {"parses": ["python {inputs}/p.py"]}


_TEST_FILE = {"test_p.py": "import json_parser\n\ndef test_parses():\n    assert json_parser.parse('1') == 1\n"}


@pytest.mark.parametrize("command", [
    "pytest -q {inputs}", "cd {inputs} && pytest -q", "cd {inputs} && python -m unittest", "python -I -m pytest -q {inputs}",
    "for f in {inputs}/*.py; do python \"$f\"; done", "PYTHONPATH={inputs} python {inputs}/test_p.py",
    "export PYTHONPATH=. && cd {inputs} && python test_p.py", "timeout -s KILL 30 python {inputs}/test_p.py",
])
def test_a_runner_or_a_loop_over_the_probe_s_own_directory_is_named(command):
    assert probes_off_the_workdir(_crit(command, _TEST_FILE)) == {"parses": [command]}


@pytest.mark.parametrize("command, files", [
    ("PYTHONPATH=$(pwd) python {inputs}/test_p.py", _TEST_FILE),
    ("pytest -q {inputs}", {**_TEST_FILE, "conftest.py": "import sys, os\nsys.path.insert(0, os.getcwd())\n"}),
    ("pytest -o pythonpath=. {inputs}/test_p.py", _TEST_FILE),
    ("pytest -q {inputs}", {"test_p.py": "import subprocess\n", "sample.py": "import requests\n"}),
    ("python {inputs}/p.py", {"p.py": "x = " + "+".join(["1"] * 5000) + "\n"}),   # too deep to parse: decides nothing
    # …parsed but too deep to read back (`ast.unparse`): decides nothing either (3.14 parses the one above)
    ("python {inputs}/p.py", {"p.py": "x = " + "+".join(["1"] * 600) + "\n"}),
])
def test_what_sees_the_working_directory_through_a_runner_is_left_alone(command, files):
    assert probes_off_the_workdir(_crit(command, files)) == {}


def test_the_reader_never_gives_up():
    """Whatever the text — an unclosed quote, a stray `)`, a backslash at the end — the shell's reading of it is
    some list of commands, never an exception that would leave the guard to guess (the split it replaced fell back
    to whitespace on an apostrophe and read a comment as commands)."""
    rng = random.Random(20261114)
    alphabet = ["'", '"', "`", "\\", "$(", ")", "(", "{", "}", ";", "&", "|", "#", "\n", "<<", "EOF", " ", "cd",
                "{inputs}", "python", "p.py", "-Im", "PYTHONPATH=.", "export", "${x}", "2>&1"]
    for _ in range(3000):
        cmd = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 30)))
        commands(cmd)
        probes_off_the_workdir(_crit(cmd))


@pytest.mark.parametrize("command, refused", [
    ("python -m unittest {inputs}/test_p.py", True),                 # a path outside where it starts: never imported
    ("python3 -m unittest -v {inputs}/test_p.py", True),
    ("PYTHONPATH=. python -m unittest {inputs}/test_p.py", True),     # the path is not what fails here
    ("cd {inputs} && python -m unittest test_p.py", False),           # inside the directory it starts in
    ("cd {inputs} && python -m unittest test_p", False),
    ("python -m unittest discover -s {inputs}", False),
    ("python -m pytest {inputs}/test_p.py", False),
    ("cd {inputs} && python3 -I -m unittest test_p.py", True),        # the start directory is off the path there
    ("cd {inputs} && PYTHONSAFEPATH=1 python3 -m unittest test_p.py", True),
    ("python -I -m unittest discover -s {inputs} -p test_p.py", False),
    ("bash {inputs}/run.sh", True),                                    # …inside a pinned script too
    ("python -m unittest discover -s {inputs} -p test_p.py", False),  # what the refusal offers
])
def test_unittest_named_a_file_it_cannot_import_is_refused(command, refused):
    """unittest turns a file path outside the directory it starts in into a module name it cannot import, so the probe
    fails over any delivery and decides nothing (critics over the probe guard, run in a container, 2026-11-14)."""
    crit = _crit(command, {"test_p.py": "import unittest\n\n\nclass C(unittest.TestCase):\n    def test_a(self):\n"
                                        "        pass\n", "run.sh": "python3 -m unittest \"$(dirname \"$0\")/test_p.py\"\n"})
    assert bool(probes_unittest_cannot_import(crit)) is refused
    assert any("unittest cannot import" in d for d in admission_defects(crit)) is refused
