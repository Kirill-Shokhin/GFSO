"""The record has always PROMISED this refutation. Nothing did it.

`tools_used` is written beside every verdict, straight from the transport's own event stream, and the
comment next to it says a claim of execution "is refuted structurally, without parsing a word of its
prose". Grep the tree: the field had one reader -- a test asserting the contradiction is STORED. So a
judge could pass a criterion on a probe it never ran, the engine would keep the evidence that this had
happened, and no rule anywhere would read it. A promise with no mechanism, and a test pinning the
false belief rather than checking it.

The rule is the same demotion `underprobed` already makes, asking a different question: not "was
enough probed" but "did the probing happen at all". Two guards keep it from becoming a worse defect
than the one it closes, and both are exercised below.
"""
from __future__ import annotations

from gfso.core.protocol.invariants import unrun_probes
from tests.test_validate_result import _delivered_node, _eng

_PROBE = [{"command": "pytest -q", "expect": "passed"}]


def _report():
    return [{"criterion": "flush", "verdict": "fail", "evidence": "Executed: check() -> not flush",
             "behaviours": ["b"], "probe": list(_PROBE)},
            {"criterion": "holds", "verdict": "pass", "evidence": "ran it",
             "behaviours": ["b"], "probe": list(_PROBE)}]


def _recorded(tools_used):
    e = _eng()
    _delivered_node(e)
    e.record_exec_verdict("n1", "FAIL", ["flush"], "validate_result",
                          per_criterion=_report(), tools_used=tools_used)
    rec = e.get_exec_verdict("n1")
    return {c["criterion"]: c["verdict"] for c in rec["per_criterion"]}


def test_a_pass_on_a_command_nobody_ran_is_not_a_pass():
    assert _recorded({"Read": 2})["holds"] == "undecidable"


def test_the_same_report_stands_when_the_shell_is_in_the_ledger():
    """The control that makes the test above mean something: nothing here demotes on its own."""
    assert _recorded({"Read": 2, "Bash": 3})["holds"] == "pass"


def test_no_ledger_refutes_nothing():
    """An EMPTY ledger is bottom ABOUT THE LEDGER, not evidence that nothing ran (bottom is not zero,
    §11.2). A transport that reports no tool events would otherwise refute every verdict it carries."""
    assert _recorded(None)["holds"] == "pass"
    assert _recorded({})["holds"] == "pass"


def test_a_refutation_is_left_alone():
    """A rule against false PASSES that suppresses a true NEGATIVE is worse than the hole it guards --
    paid for once here already (2026-08-21: a correct FAIL over garbage work was thrown away, and the
    work went back looking accepted). A FAIL is a decision, whatever the ledger says."""
    assert _recorded({"Read": 2})["flush"] == "fail"


def test_the_rule_itself_reads_the_tool_name_not_the_string():
    """`Bash(pytest:*)` is Bash. A scoped allowlist entry must not read as a shell-less run."""
    assert unrun_probes(_report(), {"Bash(pytest:*)": 1}) == []
    assert unrun_probes(_report(), {"Read": 1}) == ["holds"]
