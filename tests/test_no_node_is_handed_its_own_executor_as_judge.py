"""Verifier ≠ executor is a property of the PAIR, so it belongs where the pair is chosen (§14.5).

The gate refuses such a signature — `registering yourself as the judge` closed that on 2026-09-03.
One layer above it, the roster went on HANDING OUT the pairing: an id may hold both kinds, and a
stranger registered `w24cli-judge` as an `llm-validator` and made the same id the executor of a root.
The dispatcher bound the instrument to the work it had done itself, the verdict was recorded with
`provenance: self`, and the root closed DONE/PASS (CLI door, wave 24, 2026-09-04).

The disclosure text is what makes it sharp. A self-report is legitimate on an INTERNAL node because
"the guarantee is carried by the independent validation of the public result ABOVE it" — and on a
root there is nothing above it, so the sentence promised a guarantee that does not exist.

Refusing a signature and then offering the same pairing again is one rule enforced at one door and
handed out at the next. With no other judge the honest answer is none: the node waits for its issuer,
who is told to register one.
"""
from __future__ import annotations

import pathlib
import tempfile

from gfso.delegate import AgentRegistry


def _roster():
    d = pathlib.Path(tempfile.mkdtemp())
    return AgentRegistry(str(d / "roster.json")), d


def test_an_id_that_is_both_is_not_its_own_judge():
    reg, d = _roster()
    reg.register("judge", "llm-validator", model="sonnet", workdir=str(d), project="p1")

    assert reg.validator_for("judge", project="p1") is None, (
        "the node's own executor was handed to it as its instrument")


def test_a_self_naming_override_does_not_get_around_it():
    """`validator=` at registration wins over everything — except over being the executor."""
    reg, d = _roster()
    reg.register("other", "llm-validator", model="sonnet", workdir=str(d), project="p1")
    reg.register("exec-1", "llm-executor", model="haiku", workdir=str(d), project="p1",
                 validator="exec-1")

    assert reg.validator_for("exec-1", project="p1") == "other"


def test_an_ordinary_pair_is_chosen_exactly_as_before():
    """The negative control: this is about ONE pairing, not about binding judges at all."""
    reg, d = _roster()
    reg.register("judge", "llm-validator", model="sonnet", workdir=str(d), project="p1")
    reg.register("exec-1", "llm-executor", model="haiku", workdir=str(d), project="p1")

    assert reg.validator_for("exec-1", project="p1") == "judge"
