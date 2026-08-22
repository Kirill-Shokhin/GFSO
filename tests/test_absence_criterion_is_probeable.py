"""A criterion that FORBIDS must still be probeable, and the prompt must say how.

`record_exec_verdict(require_probe=True)` refuses a verdict whose criterion carries no probe, and a
probe's `expect` is defined as a substring of the command's REAL output. An absence ("does not import
the stdlib parser") is observed as an EMPTY result, which has no substring to name — so the required
form is unreachable unless the command is written to print something. Measured 2026-08-19: a run died
at its first delivery, twice over, on exactly one criterion of that shape; the validator's other
eleven criteria all carried probes. The requirement was satisfiable and the way to satisfy it was
never stated — so this pins the statement, not the wording of any one example.
"""
from __future__ import annotations

from pathlib import Path

PROMPT = Path(__file__).resolve().parents[1] / "gfso" / "mcp" / "prompts" / "validator.md"


def test_validator_prompt_says_how_to_probe_an_absence():
    text = PROMPT.read_text(encoding="utf-8").lower()
    assert "absence" in text, "the prompt never mentions the absence case"
    # The two halves that make the form reachable: the observation must be MADE to print, and the
    # honest exits stay closed (no omission, no fabrication).
    assert any(k in text for k in ("$?", "grep -c")), \
        "no concrete way to turn an empty result into a printable observation"
    assert "fabricate" in text, \
        "the prompt must keep the dishonest exit closed while opening the reachable one"


def test_the_prompt_defines_a_behaviour_as_separately_falsifiable():
    """A behaviour is what can be false on its own — not a clause.

    The engine demotes a criterion whose behaviours are not all observed, so the enumeration decides
    what evidence can ever satisfy it. Measured live: a validator split "a role with no client tag
    is treated as always-available" into three behaviours — available, not a crash, not permanently
    lapsed — which are one fact said three ways, and no evidence could cover them all. Two nodes
    escalated over complete work. The rule stands; what it counts had to be defined.
    """
    text = PROMPT.read_text(encoding="utf-8").lower()
    assert "false on its own" in text or "separately falsifiable" in text
    assert "one behaviour, not two" in text or "cannot fail independently" in text
