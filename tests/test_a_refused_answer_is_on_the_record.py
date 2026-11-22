"""An issuer's answer to a dispute that the system refuses before any signal is on the record with its reason, so the
next turn reads it (`refused_on_this_version`) instead of starting blind.

Measured (stranger run s16b, 2026-11-16, replayed on its state): the root sat CHALLENGED 20 min while the system's
issuer answered 12 times; each ACCEPT of the executor's true point was refused before any signal (a ruling only the
user may make; an underived re-pin) and nothing was written, so each new turn repeated the mistake, until a REJECT —
which needs only a shell run — landed, wrong. A refusal is a move that moved nothing: Thm 11 wants it on the log with
its reason, as every refusal at the signal already is.

CONTROL: drop the record in `answer_the_challenge`'s refusing paths and both tests go red.
"""
from __future__ import annotations

from tests.support import a_place
from gfso import issuer as I
from gfso.core.types import Mode, Signal, TaskId
from tests.test_a_ruling_is_part_of_the_acceptance import _auto_root, _challenged_with_a_finding, _no_l2  # noqa: F401
from tests.test_the_issuer_answers_a_dispute import _ContactLLM
from tests.test_the_mode_decides_who_holds_what import _engine


def _refusals(e, tid="root"):
    return [a for a in e.audit_log(TaskId(tid)) if a.rejected and str(a.source) == "user"]


def test_an_acceptance_refused_before_the_signal_is_read_by_the_next_turn(tmp_path):
    e = _engine(Mode.AUTO)
    _auto_root(e)
    pid = _challenged_with_a_finding(e, "root", "g")
    llm = _ContactLLM({"decision": "accept", "justification": "not g", "retire_findings": [pid]}, ran={"Bash": 1})
    out = I.answer_the_challenge(e, TaskId("root"), "user", _llm=llm, where=a_place(tmp_path))
    assert out["status"] == "users", out
    (row,) = _refusals(e)
    assert row.signal == Signal.ACCEPT_CHALLENGE and row.error and out["why"][:60] in row.error, row
    told = I.refused_on_this_version(e, TaskId("root"), "user")
    assert told and "ACCEPT_CHALLENGE" in told and out["why"][:60] in told, told
    assert e.graph.get_state("root").name == "CHALLENGED"


def test_a_rejection_that_ran_nothing_is_read_by_the_next_turn(tmp_path):
    e = _engine(Mode.AUTO)
    _auto_root(e)
    _challenged_with_a_finding(e, "root", "g")
    llm = _ContactLLM({"decision": "reject", "justification": "it stands"}, ran={})
    out = I.answer_the_challenge(e, TaskId("root"), "user", _llm=llm, where=a_place(tmp_path))
    assert out["status"] == "uncontacted", out
    (row,) = _refusals(e)
    assert row.signal == Signal.REJECT_CHALLENGE and "ran nothing" in row.error, row
    assert "ran nothing" in I.refused_on_this_version(e, TaskId("root"), "user")
