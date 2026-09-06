"""An executor that FAILED its own delivery closed the node DONE, with a recorded verdict of PASS.

§14.2 puts a WORD in `self_validation` -- the executor's own verdict -- and §14.5 D6 rests an internal
node's completion on it. The human door has always insisted on that word (`_self_check_verdict` raises
on anything else). The delegated door took a free string and asked a different question: is it empty.
Every non-empty answer became PASS.

Probed directly on 2026-09-05, before the fix: `FAIL` -> DONE/PASS. `the tests do not pass` -> DONE/PASS.
`checked` -> DONE/PASS. Only the empty string was refused. One field, two doors, two contracts -- and
the delegated one could hear good news only.
"""
from __future__ import annotations

import pathlib
import tempfile

import pytest

import gfso.tools as T
from gfso import delegate as D
from gfso.core.types import Verdict
from tests.support import make_engine
from tests.test_delegate import _agents

_RISK = [{"item": "an unmodelled environment fault", "predictability": "EXTRAORDINARY"}]


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _delivered(said):
    """An INTERNAL node (Del == its parent's) delivered with `said` as its self-check."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    _agents(pathlib.Path(tempfile.mkdtemp()), ("exec-1", "llm-executor"))
    T.create_task(e, "par", {"description": "p", "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": _RISK}, assignee="exec-1")
    T.create_task(e, "kid", {"description": "w", "criteria": [{"name": "k", "description": "K"}]},
                  assignee="exec-1", parent_id="par")
    T.map_criterion(e, "par", "kid", "g")
    T.signal(e, "kid", "ACCEPT", "exec-1")
    D._report_into_signals(e, "kid", "exec-1", e.get_task("kid"),
                           {"status": "delivered", "summary": "did it", "self_validation": said},
                           "delivered", type("L", (), {"calls": []})(), lambda *a, **k: None)
    e.wait_idle()
    out = (e.get_state("kid").name, (e.get_exec_verdict("kid") or {}).get("verdict"))
    e.stop()
    return out


def test_a_self_reported_FAIL_does_not_close_the_node():
    state, recorded = _delivered("FAIL")
    assert state != "DONE", "the executor failed its own work and the node completed anyway"
    assert recorded == Verdict.FAIL, recorded


def test_a_self_reported_PASS_still_closes_it():
    """The control. §14.5 D6 is why this path exists at all: without it a subtree delegated to one
    role deadlocks, nothing independent fires (correctly) and nothing signs."""
    assert _delivered("PASS") == ("DONE", Verdict.PASS)


def test_a_verdict_word_with_a_reason_after_it_is_still_a_verdict():
    assert _delivered("PASS - all green")[0] == "DONE"


@pytest.mark.parametrize("said", ["the tests do not pass", "checked", "looks fine", ""])
def test_prose_decides_nothing_and_nothing_is_guessed(said):
    """⊥ is not a pass (§11.2), and it is not a fail either: the node waits for its issuer, which is
    exactly what the empty field already did. Nothing here reads intent out of prose."""
    state, recorded = _delivered(said)
    assert (state, recorded) == ("VALIDATING", None), (said, state, recorded)


def test_the_word_is_read_the_way_the_other_door_reads_it():
    assert D._decided_self_check("pass") == Verdict.PASS
    assert D._decided_self_check("FAIL: two tests red") == Verdict.FAIL
    assert D._decided_self_check("passed the tests") is None      # not the word, a claim about them
    assert D._decided_self_check(None) is None
