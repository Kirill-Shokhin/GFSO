"""With no mode set the system answers a dispute at a seam only. A node whose issuer is its own executor has no
counterparty to its CHALLENGE — "a dispute against oneself is meaningless" (§10.3) — and its answer is its holder's:
the system answering it is a party outside Del deciding the contract under the holder's name (Thm 11, §11.6).

Measured on the UI stream (2026-10-26): no mode, `create_task` root held by `agent`, ACCEPT, a CHALLENGE naming a
validator's finding — 4 s later the sweep's issuer model accepted it, retired the finding, and the log row read
ACCEPT_CHALLENGE source=`agent`, a justification `agent` never wrote.

CONTROL: drop the `assignee != issuer` clause in `system_mover`'s no-mode branch and the first test goes red; the seam
test is its pair — the system still answers there, as it always did.
"""
from __future__ import annotations

import contextlib
import threading

import gfso.tools as T
from gfso import issuer as I
from gfso.core.types import Signal, State, TaskId
from tests.support import criterion
from tests.test_a_ruling_is_part_of_the_acceptance import _challenged_with_a_finding
from tests.test_the_issuer_answers_a_dispute import _ContactLLM
from tests.test_the_mode_decides_who_holds_what import _RISK, _Roster, _engine, _kid


def _sweep(e, tmp_path, pid):
    """One sweep of the system's questions, its issuer model faked to accept and rule the finding out."""
    llm = _ContactLLM({"decision": "accept", "justification": "the model's ruling", "retire_findings": [pid]},
                      ran={"Bash": 1})
    verbs = I.Verbs(llm=lambda m, **k: llm, busy=lambda *a: contextlib.nullcontext(), review=None, refine=None,
                    place=lambda en, ag, n: str(tmp_path))
    before = set(threading.enumerate())
    I.answer_open_questions(e, _Roster(), lambda k: True, lambda *a, **k: None, threading.Semaphore(1), verbs, {})
    for th in set(threading.enumerate()) - before:
        th.join(10)
    e.wait_idle()
    return llm


def _root(e, **kw):
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]}, **kw)
    e.wait_idle()


def test_the_system_does_not_answer_a_self_assigned_roots_own_dispute(tmp_path):
    e = _engine()
    _root(e)
    pid = _challenged_with_a_finding(e, "root", "g")
    llm = _sweep(e, tmp_path, pid)
    assert not llm.calls and e.graph.get_state(TaskId("root")) == State.CHALLENGED, "the system answered it"
    assert not [x for x in e.audit_log(TaskId("root")) if x.signal == Signal.ACCEPT_CHALLENGE]
    (step,) = [s for s in T.next_steps(e)["steps"] if s["task_id"] == "root"]
    assert step["mine"] and "CHALLENGED" in step["directive"], step
    # …and the holder's own answer lifts it, signed by its true author
    out = T.signal(e, "root", "ACCEPT_CHALLENGE", "agent", retire_findings=[pid], justification="not g's")
    e.wait_idle()
    assert out["accepted"] and e.regression_probes(TaskId("root")) == {}, out
    e.stop()


def test_control_the_system_still_answers_a_dispute_at_a_seam(tmp_path):
    e = _engine()
    e.record_root_issuer(TaskId("root"), "agent")
    _root(e, assignee="exec-1")
    assert str(e.graph.issuer_of(TaskId("root"))) == "agent" != str(e.graph.get_task(TaskId("root")).assignee)
    pid = _challenged_with_a_finding(e, "root", "g")
    llm = _sweep(e, tmp_path, pid)
    assert llm.calls and e.graph.get_state(TaskId("root")) == State.OFFERED, "the seam's dispute went unanswered"
    e.stop()


def test_a_machine_issuing_to_itself_keeps_the_systems_answer():
    """Only the AGENT's own node is its holder's to answer: a registered executor issuing to itself has no other live
    mover, and with no answer its dispute would wait out its bound into an ESCALATED nobody moves (critic over af0d0a2)."""
    e = _engine()
    e.record_root_issuer(TaskId("root"), "agent")
    T.TOOLS["create_task"](e, "root", {"description": "g", "criteria": [criterion("g", "G holds")]}, assignee="exec-1")
    T.signal(e, "root", "ACCEPT", "exec-1")
    T.TOOLS["decompose"](e, "root", [{**_kid("c", ["g"], criterion("k", "K holds")), "assignee": "exec-1"}],
                         accepted_risks=_RISK)
    T.signal(e, "c", "CHALLENGE", "exec-1", reason="k is unmeetable as written")
    assert str(e.graph.issuer_of(TaskId("c"))) == "exec-1" == str(e.graph.get_task(TaskId("c")).assignee)
    assert I.system_mover(e, _Roster(), TaskId("c"), "dispute") == "exec-1"
