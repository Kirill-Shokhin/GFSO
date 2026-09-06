"""«The node revalidates on the graph's next change» — true, useless alone, and it waited out a run.

When the FSM refuses an instrument's verdict, two very different things can be happening. Some
refusals are TRANSIENT: the children have not settled yet, and the graph really will change. Some are
STANDING: the node's own decomposition no longer passes the Syntactic level, and nothing will change
that except a person repairing the plan. The line the reader got was identical in both cases, and the
FSM's actual reason went to the log alone — so an unattended run sits out its whole ceiling on a
refusal nobody can read.

This became reachable the moment a parent's PASS started re-reading its own L0 (the same audit's F2),
which is exactly the standing kind.
"""
from __future__ import annotations

import inspect
import pathlib
import tempfile

import pytest

import gfso.tools as T
from gfso import delegate as D
from gfso.core.types import Verdict
from tests.support import UNMODELLED_FAULT, make_engine
from tests.test_delegate import _agents

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def test_the_refusal_reaches_the_reader_with_its_reason(monkeypatch):
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    agents = _agents(pathlib.Path(tempfile.mkdtemp()), ("exec-1", "llm-executor"),
                     ("val-1", "llm-validator"))
    T.create_task(e, "par", {"description": "parent",
                             "criteria": [{"name": "g", "description": "G"}],
                             "accepted_risks": _RISK}, assignee="a-human")
    T.create_task(e, "kid", {"description": "the work",
                             "criteria": [{"name": "k", "description": "K"}]},
                  assignee="exec-1", parent_id="par")
    T.map_criterion(e, "par", "kid", "g")
    T.signal(e, "kid", "ACCEPT", "exec-1")
    T.signal(e, "kid", "DELIVER", "exec-1", result="did it")
    # …and the PARENT is delivered too, or the refusal under test is about the STATE rather than
    # about the children — which the first cut of this test measured instead, greenly.
    T.signal(e, "par", "ACCEPT", "a-human")
    T.signal(e, "par", "DELIVER", "a-human", result="aggregate")
    e.wait_idle()

    said: list = []
    monkeypatch.setattr(e, "emit_info", lambda src, msg: said.append(msg))
    e._graph.authorized_validators = {"val-1"}
    # A verdict the FSM will refuse: PASS on the PARENT while its child is still unsettled.
    monkeypatch.setattr(D, "_judge_with", lambda *a, **k: {"verdict": Verdict.PASS})
    D._auto_validate(e, "par", agents)

    rejected = [m for m in said if "REJECTED by the FSM" in m]
    assert rejected, said
    assert "not all children have PASSed" in rejected[0], rejected[0]
    assert "list_holes" in rejected[0], "the standing kind needs an address, not just a wait"
    e.stop()


def test_the_signal_helper_only_collects_a_reason_when_asked():
    """The control: `_signal` stays a boolean for every caller that does not want the text, so this
    cannot quietly become a second return channel nobody reads."""
    sig = inspect.signature(D._signal)
    assert sig.parameters["_why"].default is None
