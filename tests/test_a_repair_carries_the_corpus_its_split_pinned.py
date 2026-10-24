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
from gfso.core.protocol.procedure import materialize_inputs, pinned_files, with_named_files
from gfso.core.types import Criteria, Probe, TaskId
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


def test_a_child_naming_the_files_without_their_content_gets_the_content_its_split_pins():
    """The measured shape (GB_sql_database_tnajs5800, 2026-10-22): the machine issuer re-homed the root's probes into
    an integration child with the command reworded and every file NAMED under `{inputs}/<name>` with an empty body —
    it reads a projection that shows commands, never the corpus — and every validation read empty inputs for twelve
    rounds. The content is the split's own, carried by file under the criterion; the path's token is normalized away.
    CONTROL: drop `with_named_files` from `_new_child` and this goes red."""
    e = _split()
    ok, why = I.apply_move(e, TaskId("root"), "plan", str(e.graph.issuer_of(TaskId("kid"))), {
        "move": "add_child", "justification": "integration", "child": {
            "name": "kid2", "description": "the whole, integrated", "covers": ["g"], "criteria": [{
                **criterion("reads"), "check": [{"behaviour": "reads the corpus", "command": CMD + " || echo FAIL",
                                                 "expect": "the corpus", "inputs": {"{inputs}/x.txt": ""}}]}]}})
    assert ok, why
    (p,) = e.graph.get_task(TaskId("root.kid2")).spec.criteria[0].check
    assert dict(p.inputs) == CORPUS, dict(p.inputs)
    e.stop()


def test_a_path_naming_the_token_is_laid_down_where_the_command_reads_it(tmp_path):
    """`{inputs}` is substituted in the command; a stored path carrying it is the same file — laid down inside the
    probe's directory, not under a literal `{inputs}` the command never reads (contracts stored so stay runnable)."""
    c = Criteria("reads", check=(Probe.of({"behaviour": "b", "command": CMD, "expect": "x",
                                           "inputs": {"{inputs}/x.txt": "the corpus\n"}}),))
    (d,) = materialize_inputs([c], tmp_path).values()
    assert (d / "x.txt").read_text(encoding="utf-8") == "the corpus\n"


def test_one_criterion_two_probes_over_one_file_name_each_get_their_own():
    """Two probes of one criterion over different `in.sql` (critic, 2026-10-22): by command first, so neither lends
    the other its corpus; reworded, a name pinned with two contents is given neither."""
    crit = {"name": "c", "check": [{"command": "a < {inputs}/in.sql | grep X", "inputs": {"in.sql": "ONE"}},
                                   {"command": "a < {inputs}/in.sql | grep Y", "inputs": {"in.sql": "TWO"}}]}
    files = pinned_files([crit])
    again = with_named_files({"name": "c", "check": [
        {"command": "a < {inputs}/in.sql | grep Y", "inputs": {"in.sql": ""}},
        {"command": "a < {inputs}/in.sql | grep Y || echo F", "inputs": {"in.sql": ""}}]}, files)
    assert [p["inputs"]["in.sql"] for p in again["check"]] == ["TWO", ""]


def test_an_accepted_dispute_naming_the_files_keeps_their_content():
    """The third door (`spec_with`'s `_probes`): a re-pin naming the files empty keeps what the criterion pinned."""
    stored = Criteria("reads", check=(Probe.of({"behaviour": "b", "command": CMD, "expect": "x",
                                                "inputs": {"x.txt": "the corpus\n"}}),))
    (p,) = I._probes(stored, (Probe.of({"behaviour": "b", "command": CMD + " && echo ok", "expect": "ok",
                                        "inputs": {"x.txt": ""}}),))
    assert dict(p.inputs) == {"x.txt": "the corpus\n"}
