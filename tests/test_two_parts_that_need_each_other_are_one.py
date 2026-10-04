"""A dependency order contact refuted is repaired by the system, and a reshape can name what it creates.

Measured (AUTO GB_c_compiler_tmp5cb096): root.pp BLOCKed on root.libc while the plan had root.libc depending on root.pp
— a cycle (§15.5), whose one restoring move is a re-decomposition. Asked of a model, the root's machine issuer
answered six times, every repair refused, and the root was cancelled with 8 of its 10 parts passed. Which children
the cycle runs through, their criteria, what they covered and who consumes them are all in the graph: the system
merges them into one child in one re-admission, and their consumers read the merged child.

The merge keeps the members' work (§12.16 (ii)): it waits for a member's pending verdict, the merged child's place
starts from their branches and their PASSed parts', and its terms are the widest of theirs.

CONTROLS: take the `repair` branch out of `settle` and the merge test goes red (the question reaches a model turn,
which has no client here); make `_repointed` return [] and the consumer tests go red (left on a cancelled
producer); resolve `reads` against standing children only and the same-act read goes red; drop the VALIDATING wait, or
count a wait as an answer, and the wait test goes red; empty `carried_work`, or leave the DONE parts out of it, and the
work-keeping test goes red; drop the merged child's terms and the merge test goes red.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from gfso import issuer as I, tools as T
from gfso.adapters import worktrees as W
from gfso.core.protocol.procedure import probe_id
from gfso.workspaces import _enter_workspace, _ensure_place, _workspace
from gfso.core.types import Mode, State, TaskId
from gfso.delegate import AgentRegistry
from tests.support import criterion
from tests.test_the_mode_decides_who_holds_what import _admit, _engine, _kid
from tests.test_a_node_works_in_its_own_place import _repo


def _deps(e, tid) -> set:
    return {str(c.depends_on) for c in e.graph.get_task(TaskId(tid)).spec.criteria if c.depends_on}


_DUE = [datetime.now() + timedelta(hours=h) for h in (4, 8, 16)]


def _terms(kid: dict, due, bound: int, risk: str) -> dict:
    """A child with its own deadline, rework bound and a risk its packet sets aside."""
    kid["spec"]["accepted_risks"] = [{"item": risk, "predictability": "EXTRAORDINARY", "justification": "out of scope",
                                      "invalidation_condition": "it is asked for", "p": 0.01, "impact": "rework"}]
    return {**kid, "deadline": due.isoformat(), "max_iterations": bound}


def _ring(mode=Mode.AUTO):
    """pp covers g, libc (reading pp) covers h, cc (reading both) covers i — and contact confirmed pp needs libc."""
    e = _engine(mode)
    T.TOOLS["create_task"](e, "root", {"description": "the compiler", "criteria": [
        criterion("g", "G holds"), criterion("h", "H holds"), criterion("i", "I holds")]})
    _admit(e, "root", _terms(_kid("root.pp", ["g"], criterion("builds", "pp builds"), criterion("kp", "macros expand")),
                             _DUE[0], 2, "the host has no <wchar.h>"),
           _terms(_kid("root.libc", ["h"], criterion("builds", "libc builds"), criterion("kl", "headers parse")),
                  _DUE[1], 5, "locales other than C"),
           _terms(_kid("root.cc", ["i"], criterion("kc", "it compiles")), _DUE[2], 3, "no optimiser"))
    for producer, consumer in (("root.pp", "root.libc"), ("root.libc", "root.cc"), ("root.pp", "root.cc")):
        T.TOOLS["add_dependency"](e, producer, consumer)
    e.add_dependency(TaskId("root.libc"), TaskId("root.pp"), discovered=True, glue="p_wide.c includes <wchar.h>")
    e.wait_idle()
    return e


def test_a_refuted_order_is_merged_into_one_child_before_any_model_is_asked(tmp_path):
    e = _ring()
    root = e.graph.get_task(TaskId("root"))
    assert e.dep_order_refuted(root.id) and e.dep_order_cycle_children(root.id) == [["root.libc", "root.pp"]]
    assert (root.id, "repair") in I.open_questions(e)
    out = I.settle(e, AgentRegistry(path=str(tmp_path / "agents.json")), root.id, "repair", str(root.assignee), None)
    e.wait_idle()
    assert out == {"status": "applied", "move": "merge"}, out
    merged = e.graph.get_task(TaskId("root.libc_pp"))
    assert merged is not None and merged.state not in (State.CANCELLING, State.ABANDONED)
    assert {c.name for c in merged.spec.criteria} == {"builds (libc)", "kl", "builds (pp)", "kp"}
    assert all(c.check for c in merged.spec.criteria), "a member's pinned procedure was not carried by reference"
    assert not _deps(e, "root.libc_pp"), "the seam between two members survived the merge"
    assert {m.criterion_name for m in e.graph.get_task(root.id).criterion_mappings
            if str(m.child_id) == "root.libc_pp"} == {"g", "h"}
    assert all(e.graph.get_state(TaskId(m)) in (State.CANCELLING, State.ABANDONED) for m in ("root.pp", "root.libc"))
    assert _deps(e, "root.cc") == {"root.libc_pp"}, "a consumer of a member was left waiting on a cancelled node"
    assert e.dep_order_refuted(root.id) is None
    # the members' terms, the widest of them; the consumer's own stay as they were
    assert merged.deadline == _DUE[1].replace(microsecond=merged.deadline.microsecond) and merged.max_iterations == 5
    assert {n.item for n in merged.spec.accepted_risks} == {"the host has no <wchar.h>", "locales other than C"}
    cc = e.graph.get_task(TaskId("root.cc"))
    assert abs((cc.deadline - _DUE[2]).total_seconds()) < 1 and cc.max_iterations == 3
    e.stop()


def test_a_member_whose_delivery_awaits_its_verdict_is_not_merged_until_it_has_one(tmp_path):
    e = _ring()
    pp = e.graph.get_task(TaskId("root.pp"))
    T.signal(e, "root.pp", "ACCEPT", str(pp.assignee))
    T.signal(e, "root.pp", "DELIVER", str(pp.assignee), result="pp built")
    e.wait_idle()
    assert e.graph.get_state(TaskId("root.pp")) == State.VALIDATING
    root = e.graph.get_task(TaskId("root"))
    out = I.settle(e, AgentRegistry(path=str(tmp_path / "agents.json")), root.id, "repair", str(root.assignee), None)
    assert out["status"] == "waiting", out
    assert e.graph.get_task(TaskId("root.libc_pp")) is None and e.graph.get_state(TaskId("root.pp")) == State.VALIDATING
    I._answered(e, "g", "repair", out, root.id)
    assert e.tally("answers:g:repair") == 0, "a wait was counted as an answer toward closing the node"
    e.stop()


@pytest.mark.skipif(shutil.which("git") is None, reason="the node workspaces are git worktrees")
def test_the_merged_child_starts_from_its_members_work_and_their_passed_parts(tmp_path):
    """Dropped, a member's committed work and its PASSed parts stood on branches nothing joined: the merged child
    started from the base and redid them (§12.16 (ii))."""
    base = _repo(tmp_path / "ws")
    e = _ring()
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    for a in ("exec-1", "exec-2"):
        agents.register(a, "llm-executor", workdir=str(base), project="p")
    _admit(e, "root.pp", _kid("root.pp.lex", ["builds", "kp"], criterion("kx", "it lexes")))
    lex = e.graph.get_task(TaskId("root.pp.lex"))
    for tid, name in (("root.pp", "pp.c"), ("root.libc", "libc.c"), ("root.pp.lex", "lex.c")):
        t = e.graph.get_task(TaskId(tid))
        w = _workspace(e, agents, t)
        _ensure_place(e, agents, t, w)
        (Path(w[1]) / name).write_text(f"/* {tid} */\n")
        W.commit_all(w[0], w[1], f"{tid} works", "t")
    lex.state = State.DONE                      # a part that PASSed and never joined its whole
    e.graph.save_task(lex)
    root = e.graph.get_task(TaskId("root"))
    assert I.merge_the_refuted_cycle(e, root, str(root.assignee)) == {"status": "applied", "move": "merge"}
    e.wait_idle()
    place, unjoined, _w = _enter_workspace(e, agents, e.graph.get_task(TaskId("root.libc_pp")),
                                           [e.graph.get_task(TaskId("root.libc_pp"))])
    assert not unjoined, unjoined
    assert {"pp.c", "libc.c", "lex.c"} <= {p.name for p in Path(place).iterdir()}
    e.stop()


def test_a_holders_split_is_not_merged_by_the_system():
    """The negative control: where the user's agent holds the split, its re-decomposition is his move."""
    e = _ring(Mode.SOLO)
    root = e.graph.get_task(TaskId("root"))
    assert I.held_by_a_holder(e, str(root.assignee)) and e.dep_order_refuted(root.id)
    assert I.merge_the_refuted_cycle(e, root, str(root.assignee)) is None
    assert e.graph.get_task(TaskId("root.libc_pp")) is None
    e.stop()


def _two():
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("root.part", ["g"], criterion("k", "K holds")), _kid("root.other", ["g"], criterion("o", "O")))
    T.TOOLS["add_dependency"](e, "root.part", "root.other")
    e.wait_idle()
    return e, e.graph.get_task(TaskId("root"))


def test_a_reshape_that_replaces_a_child_hands_its_consumers_to_the_replacement():
    e, root = _two()
    ok, why = I._readmit(e, root, {"drop": ["root.part"], "children": [
        {"name": "part", "covers": ["g"], "criteria": [criterion("k2", "K holds, as replaced")]}]})
    e.wait_idle()
    assert ok, why
    assert _deps(e, "root.other") == {"root.part_2"}
    e.stop()


def test_a_reshape_reads_a_child_it_creates_by_its_name():
    e, root = _two()
    ok, why = I._readmit(e, root, {"children": [
        {"name": "lexer", "covers": ["g"], "criteria": [criterion("kl", "it lexes")]},
        {"name": "checker", "covers": ["g"], "reads": ["lexer"], "criteria": [criterion("kc", "it checks")]}]})
    e.wait_idle()
    assert ok, why
    assert _deps(e, "root.checker") == {"root.lexer"}
    e.stop()


def _found(e, tid, crit, command):
    """A finding of the validator's own standing on `tid`'s criterion `crit`, as a FAIL leaves it."""
    e._graph._storage.store_critique(TaskId(f"{tid}#regression-probes"), json.dumps({crit: [
        {"id": probe_id(crit, {"command": command}), "behaviour": "found by contact", "command": command,
         "as_run": command, "expect": "exit=0"}]}))


def test_the_merged_child_carries_its_members_standing_findings(tmp_path):
    e = _ring()
    _found(e, "root.pp", "builds", "./cc p_wide.c; echo exit=$?")
    _found(e, "root.libc", "kl", "./cc -E wchar.c; echo exit=$?")
    root = e.graph.get_task(TaskId("root"))
    assert I.merge_the_refuted_cycle(e, root, str(root.assignee)) == {"status": "applied", "move": "merge"}
    e.wait_idle()
    carried = e.regression_probes(TaskId("root.libc_pp"))
    assert {k: [p["command"] for p in v] for k, v in carried.items()} == {
        "builds (pp)": ["./cc p_wide.c; echo exit=$?"], "kl": ["./cc -E wchar.c; echo exit=$?"]}
    assert carried["builds (pp)"][0]["id"] == probe_id("builds (pp)", {"command": "./cc p_wide.c; echo exit=$?"})
    e.stop()


def test_a_replacement_under_the_same_name_carries_the_findings_too():
    e, root = _two()
    _found(e, "root.part", "k", "./x f.c; echo $?")
    ok, why = I._readmit(e, root, {"drop": ["root.part"], "children": [
        {"name": "part", "covers": ["g"], "criteria": [criterion("k", "K holds, as replaced")]}]})
    e.wait_idle()
    assert ok, why
    assert [p["command"] for p in e.regression_probes(TaskId("root.part_2"))["k"]] == ["./x f.c; echo $?"]
    e.stop()
