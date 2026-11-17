"""A pinned command carrying a placeholder the system never fills — `{exec}`, `{workspace}`, `{target}` — runs as
written, so no run can match it and no truthful report can cite it as run (§12.16 (ii)): `{exec}` ×142 in one AUTO
run's pins (tmyl10584, 2026-10-20). It is refused at admission, where its issuer lifts it by writing the command out;
the system's own `{inputs}` / `{inputs:<id>}`, and braces the shell or a program reads, stay admissible."""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.core.protocol.procedure import admission_defects
from gfso.core.types import Criteria, Probe, TaskId
from tests.support import DENIAL_ENTRY, UNMODELLED_FAULT, make_engine

_RISK = {"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY", "justification": "no precedent",
         "invalidation_condition": "one occurs", "p": 0.01, "impact": "x"}


def _defects(command: str) -> list[str]:
    inputs = (("want", "ok"), ("in", "x")) if "{inputs}" in command else ()
    return admission_defects([Criteria("c", "it runs", check=(Probe("it runs", command, "ok", inputs=inputs),))])


@pytest.mark.parametrize("command", ["{exec} --version", "cd {workspace} && make test", "test -x {target}/bin/tool"])
def test_a_placeholder_no_run_fills_is_refused(command):
    (why,) = _defects(command)
    assert "{" in why and "fills" in why


def test_the_issuers_assign_is_refused_and_lifted_by_writing_it_out(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    e = make_engine()
    e.start()
    try:
        spec = lambda cmd: {"description": "a tool", "accepted_risks": [_RISK, DENIAL_ENTRY],
                            "criteria": [{"name": "c", "description": "it runs", "check": [{"command": cmd, "expect": "ok"}]}]}
        assert "{exec}" in str(T.create_task(e, "root", spec("{exec} --version"), assignee="me"))
        assert e.graph.get_task(TaskId("root")) is None or e.graph.get_state(TaskId("root")).name == "IDLE"
        T.create_task(e, "root2", spec("./tool --version"), assignee="me")
        assert e.graph.get_state(TaskId("root2")).name == "OFFERED"
    finally:
        e.stop()


@pytest.mark.parametrize("command", [
    "diff {inputs}/want <(./tool < {inputs}/in)", "./tool {inputs:c#1a2b3c4d}/in", "awk '{print $1}' out.txt",
    'printf "%s" "${HOME}" | ./tool', "find . -name '*.c' -exec wc -l {} +", "echo a{b,c} | ./tool",
    "./tool '{\"key\": 1}'", "for i in {1..3}; do ./tool $i; done",
    "cat > a.c <<'EOF'\nstruct s v = {a};\nEOF\ncc a.c && ./a.out"])
def test_control_the_systems_tokens_and_the_shells_braces_are_admitted(command):
    assert _defects(command) == []
