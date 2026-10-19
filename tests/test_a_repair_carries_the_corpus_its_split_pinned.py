"""A child a repair adds carries the corpus its split already pinned under the same probe command.

Measured (AUTO haiku coreutils, 2026-10-12, two rows): the machine issuer re-wrote a dropped child's probe — a command
reading `{inputs}` — into the child that was to carry its work, and could not re-write the files it reads; the
admission refused the child "its probe reads {inputs} and pins nothing there" six times and the root closed by count.

CONTROL: drop `_with_corpora` from `_new_child` and the first test goes red; the second shows nothing is invented.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso import issuer as I
from gfso.core.types import TaskId
from tests.support import REGISTER, criterion, make_engine

CMD = "cat {inputs}/x.txt"
CORPUS = {"x.txt": "the corpus\n"}


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _split():
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g")]}, assignee="me")
    probe = {"behaviour": "reads the corpus", "command": CMD, "expect": "the corpus", "inputs": CORPUS}
    T.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "part", "criteria": [
        {**criterion("reads"), "check": [probe]}]}, "assignee": "exec-1", "covers": ["g"]}], accepted_risks=REGISTER)
    return e


def _add(e, command):
    return I.apply_move(e, TaskId("root"), "plan", str(e.graph.issuer_of(TaskId("kid"))), {
        "move": "add_child", "justification": "carries kid's work", "child": {
            "name": "kid2", "description": "part, again", "covers": ["g"], "criteria": [{
                **criterion("reads"), "check": [{"behaviour": "reads the corpus", "command": command,
                                                 "expect": "the corpus"}]}]}})


def test_the_added_child_carries_the_corpus_pinned_under_its_command():
    e = _split()
    ok, why = _add(e, "cat  {inputs}/x.txt")
    assert ok, why
    (p,) = e.graph.get_task(TaskId("root.kid2")).spec.criteria[0].check
    assert dict(p.inputs) == CORPUS
    e.stop()


def test_a_command_no_child_pinned_carries_nothing():
    e = _split()
    ok, why = _add(e, "cat {inputs}/y.txt")
    assert not ok and "pins nothing there" in why, why
    e.stop()


def test_a_command_two_obligations_pin_over_different_files_carries_the_criterions_own_or_none():
    """Two children pin one command over different corpora (one split of the past rows): the criterion's own goes; a
    criterion that pinned it nowhere carries neither, and the admission refuses as before (critic r4)."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g")]}, assignee="me")
    T.decompose(e, "root", [
        {"task_id": k, "spec": {"description": k, "criteria": [{**criterion(n), "check": [
            {"behaviour": "reads", "command": CMD, "expect": "x", "inputs": {"x.txt": f"corpus {k}\n"}}]}]},
         "assignee": "exec-1", "covers": ["g"]} for k, n in (("kid", "reads"), ("other", "also"))],
        accepted_risks=REGISTER)
    assert _add(e, CMD)[0]
    (p,) = e.graph.get_task(TaskId("root.kid2")).spec.criteria[0].check
    assert dict(p.inputs) == {"x.txt": "corpus kid\n"}
    ok, why = I.apply_move(e, TaskId("root"), "plan", str(e.graph.issuer_of(TaskId("kid"))), {
        "move": "add_child", "justification": "x", "child": {"name": "kid3", "description": "x", "covers": ["g"],
            "criteria": [{**criterion("third"), "check": [{"behaviour": "reads", "command": CMD, "expect": "x"}]}]}})
    assert not ok and "pins nothing there" in why, why
    e.stop()


def test_the_nodes_own_pinned_corpus_is_carried_by_a_child_that_takes_its_criterion():
    """A repair moved one of the root's own criteria onto a new child: the corpus was pinned on the root alone, and the
    child was refused (GB_coreutils_tmsfo4636 root.pipeline, critic r5)."""
    e = make_engine()
    e.start()
    probe = {"behaviour": "reads the corpus", "command": CMD, "expect": "the corpus", "inputs": CORPUS}
    T.create_task(e, "root", {"description": "goal", "criteria": [{**criterion("g"), "check": [probe]}]},
                  assignee="me")
    T.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "part", "criteria": [criterion("k")]},
                             "assignee": "exec-1", "covers": ["g"]}], accepted_risks=REGISTER)
    ok, why = I.apply_move(e, TaskId("root"), "plan", str(e.graph.issuer_of(TaskId("kid"))), {
        "move": "add_child", "justification": "g's own check", "child": {"name": "g_check", "description": "x",
            "covers": ["g"], "criteria": [{**criterion("g"), "check": [{"behaviour": "reads", "command": CMD,
                                                                          "expect": "the corpus"}]}]}})
    assert ok, why
    (p,) = e.graph.get_task(TaskId("root.g_check")).spec.criteria[0].check
    assert dict(p.inputs) == CORPUS
    e.stop()
