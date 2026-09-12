"""An executor that reported it could not do the work had its node moved on as a delivery.

`EXECUTOR_SCHEMA` declares `status` with an `enum` of three — delivered, blocked, challenge — and
`parse_structured` validates the presence of KEYS, never their types or their enumerations. So the
declaration reads as a guarantee and is a comment. That is true of all seven `enum`s in the package;
six of them fail CLOSED (an unknown word becomes not-SUFFICIENT, not-`atomic`, not-PASS) and this one
failed OPEN, because the dispatch was `if challenge / elif blocked / else`, and `else` was DELIVERED.

Probed 2026-09-08:

    {"status": "failed", "summary": "could not do it"}   parses
                                                         → DELIVER sent
                                                         → node EXECUTING → VALIDATING

so an executor disclaiming its own work put the node where a validator is then paid to judge the
artifact its author said does not exist. A word the contract does not define decides nothing, and
⊥ is not a delivery (§11.2).

WHERE THE GUARD SITS is half the repair. The first version of it checked the status in the CALLER,
one frame above the dispatch — and the probe that had just found the defect, which calls
`_report_into_signals` directly, walked straight past it and still reported VALIDATING. A guard a
caller can step around is a shape this repository has paid for before, so it moved down to the
`elif` beside the branches it guards, where no caller can miss it. `_decided_status` owns the word;
the dispatch enforces it; the round's return value only reports what it amounted to.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.core.types import TaskId
from gfso.delegate import EXECUTOR_SCHEMA, _decided_status, _report_into_signals
from gfso.adapters.llm.structured import parse_structured
from tests.support import UNMODELLED_FAULT, make_engine

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]


class _NoCalls:
    calls: list = []


def _accepted_node():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "n", {"description": "the work", "accepted_risks": _RISK,
                           "criteria": [{"name": "g", "description": "G holds"}]},
                  assignee="worker")
    T.signal(e, "n", "ACCEPT", "worker")
    return e


def _report(e, report: dict):
    said: list[str] = []
    _report_into_signals(e, TaskId("n"), "worker", e.get_task("n"), report,
                         _decided_status(report.get("status")) or str(report.get("status")),
                         _NoCalls(), said.append)
    e.wait_idle()
    return e.get_task("n").state.name, " ".join(said)


@pytest.mark.parametrize("word", ["failed", "give_up", "error", "done", "partial", "", "  "])
def test_a_word_outside_the_contract_moves_nothing(word: str) -> None:
    state, said = _report(_accepted_node(), {"status": word, "summary": "could not do it"})

    assert state == "EXECUTING", (
        f"status {word!r} is none of the three the contract defines and the node moved to {state} "
        f"anyway. The dispatch's `else` branch is what reads an undecided report as a delivery."
    )
    assert "none of delivered / blocked / challenge" in said, said


def test_the_schema_does_not_stop_it_and_that_is_the_point() -> None:
    """The guard cannot be replaced by "the enum will catch it" — the enum catches nothing.

    Kept as a test rather than a comment because the obvious future repair is to delete the guard
    and trust the schema; this says out loud that the schema is not a check.
    """
    assert parse_structured('{"status": "failed", "summary": "x"}', EXECUTOR_SCHEMA) == {
        "status": "failed", "summary": "x"}
    assert parse_structured('{"status": 7, "summary": "x"}', EXECUTOR_SCHEMA) == {
        "status": 7, "summary": "x"}


@pytest.mark.parametrize("raw,expected", [
    ("delivered", "delivered"), ("DELIVERED", "delivered"), (" blocked ", "blocked"),
    ("Challenge", "challenge"), ("failed", None), ("give_up", None), (7, None), (None, None),
])
def test_the_three_words_are_read_whatever_their_casing(raw, expected) -> None:
    """What is refused is a FOURTH meaning, not a model's capitalisation."""
    assert _decided_status(raw) == expected


def test_a_delivery_still_delivers() -> None:
    state, _ = _report(_accepted_node(), {"status": "delivered", "summary": "did it"})
    assert state == "VALIDATING"


def test_a_block_still_blocks() -> None:
    state, _ = _report(_accepted_node(), {"status": "blocked",
                                          "reason": "waiting on something outside",
                                          "blocker_task_ids": []})
    assert state == "BLOCKED"


def test_a_challenge_from_executing_is_still_contested_not_swallowed() -> None:
    """The third word's path is unchanged, including the case where the FSM refuses it.

    §14.3 admits CHALLENGE from OFFERED only; an executor disputing the contract mid-work has its
    reason recorded and the node left in its hands (`engine.contest`). That is a different thing
    from an undecided word, and this test exists so the two do not get merged by a later tidy-up.
    """
    e = _accepted_node()
    state, said = _report(e, {"status": "challenge", "reason": "the spec is ambiguous"})

    assert state == "EXECUTING"
    assert "none of delivered / blocked / challenge" not in said, (
        "a CHALLENGE the FSM refuses is a contested contract, not an undecided report"
    )
