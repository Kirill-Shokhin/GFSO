"""Deciding not to pay is the same question as refusing the verdict, asked before the money.

`record_verdict` and `Engine.record_exec_verdict` both refuse a verdict on a node with no criteria,
by name: V is the conjunction over the node's criteria (§10), and over the empty set that is
vacuously true, which is not a judgement. Both refusals are instant and free.

The dispatcher asked the same question after spending. A stranger's criteria-less node was delivered
and the bound instrument was fired at it TWICE — a full paid validator run each — before the
retry-and-park path printed "AUTOMATIC VALIDATION GAVE UP", while `record_verdict` on that same node
answered correctly in milliseconds (MCP door, wave 24, 2026-09-04). Their own summary: *the right
check exists; it sits downstream of the spend.*

Fifth instance in three days of one shape — a guard standing on the far side of what it guards.
"""
from __future__ import annotations

import pathlib
import tempfile

from gfso import tools as T
from gfso.core.types import TaskId
from gfso.delegate import AgentRegistry, Dispatcher
from tests.support import UNMODELLED_FAULT, make_engine


def _roster(tmp: pathlib.Path):
    reg = AgentRegistry(str(tmp / "roster.json"))
    reg.register("exec-1", "llm-executor", model="haiku", workdir=str(tmp))
    reg.register("val-1", "llm-validator", model="sonnet", workdir=str(tmp))
    return reg


def _delivered(e, tid, criteria):
    T.create_task(e, tid, {"description": "a node", "criteria": criteria,
                           "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                               "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    e.wait_idle()
    T.signal(e, tid, "ACCEPT", "exec-1")
    T.signal(e, tid, "DELIVER", "exec-1", result="claimed done")
    e.wait_idle()
    assert e.get_state(TaskId(tid)).name == "VALIDATING"


def test_no_instrument_is_spent_on_a_node_with_no_criteria():
    tmp = pathlib.Path(tempfile.mkdtemp())
    e = make_engine()
    e.start()
    _delivered(e, "hollow", [])
    d = Dispatcher(e, _roster(tmp), runner=lambda *a: None)

    started = d.dispatch_once()

    assert not [x for x in started if str(x).startswith("validate:")], (
        f"a validator was dispatched at an empty contract: {started}")
    e.stop()


def test_and_the_reason_is_on_the_record_rather_than_silence():
    """A node that simply stops being judged looks like a broken dispatcher; this one says why."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    e = make_engine()
    e.start()
    said: list = []
    e.emit_info = lambda tag, msg: said.append(msg)      # the info channel, captured
    _delivered(e, "hollow", [])
    Dispatcher(e, _roster(tmp), runner=lambda *a: None).dispatch_once()

    assert any("nothing a verdict could be ABOUT" in m for m in said), said
    assert any("edit_criteria" in m for m in said), "the repair is not named"
    e.stop()


def test_a_node_WITH_a_contract_is_dispatched_exactly_as_before():
    """The negative control: this is about the empty set, not about auto-validation."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    e = make_engine()
    e.start()
    _delivered(e, "real", [{"name": "c", "description": "C"}])
    d = Dispatcher(e, _roster(tmp), runner=lambda *a: None)

    started = d.dispatch_once()

    assert "validate:real" in started, started
    e.stop()
