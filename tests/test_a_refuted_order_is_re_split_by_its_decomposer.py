"""A dependency order contact refuted is re-decomposed by its split's decomposer, and a reshape can name what it creates.

Measured (AUTO GB_c_compiler_tmp5cb096): root.pp BLOCKed on root.libc while the plan had root.libc depending on root.pp
— a cycle, which "only a re-decomposition restores" (§15.5). The system used to merge the cycle's children into one
node; on c_compiler × Haiku 5.5 that folded the whole compiler into one node, whose executor never built it. A merge
is no re-decomposition: the split's decomposer answers the `repair` question by re-cutting it in ONE re-admission —
the children the cycle runs through dropped, those that replace them added, their consumers handed over, their work
and their findings carried (§12.16 (ii)). A member's delivery awaiting its verdict is work in hand: the question waits
for it.

CONTROLS: put the merge back in `settle` and the first test goes red (no question reaches the decomposer, a merged
child stands); drop the VALIDATING wait and the wait test goes red; make `_repointed` return [] and the consumer tests
go red; resolve `reads` against standing children only and the same-act read goes red; empty `carried_work` and the
work-keeping test goes red.
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
    return {str(x.from_id) for x in e.graph.declared_edges(TaskId(tid))}


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


def _asked(monkeypatch):
    asked = []
    monkeypatch.setattr(I, "_still_open", lambda *a: True)
    monkeypatch.setattr(I, "issuer_turn", lambda engine, tid, q, actor, *a, **k: asked.append((str(tid), q, actor))
                        or {"status": "applied"})
    return asked


_RESPLIT = {"move": "reshape", "justification": "pp needs the headers libc parses: cut the headers out first",
            "drop": ["root.pp", "root.libc"], "children": [
                {"name": "headers", "covers": ["h"], "replaces": ["root.libc"],
                 "criteria": [criterion("kl", "headers parse")]},
                {"name": "pp", "covers": ["g"], "reads": ["headers"], "replaces": ["root.pp"],
                 "criteria": [criterion("kp", "macros expand")]}]}


def test_a_refuted_order_goes_to_its_decomposer_as_a_re_decomposition_and_is_not_merged(tmp_path, monkeypatch):
    e = _ring()
    root = e.graph.get_task(TaskId("root"))
    assert e.dep_order_refuted(root.id) and e.dep_order_cycle_children(root.id) == [["root.libc", "root.pp"]]
    assert (root.id, "repair") in I.open_questions(e)
    asked = _asked(monkeypatch)
    I.settle(e, AgentRegistry(path=str(tmp_path / "agents.json")), root.id, "repair", str(root.assignee), None)
    e.wait_idle()
    assert asked == [("root", "repair", str(root.assignee))], asked
    assert {str(k.id) for k in e.graph.get_active_children(root.id)} == {"root.pp", "root.libc", "root.cc"}
    assert "reshape" in I.QUESTIONS["repair"]["ask"] and "reshape" in I.moves_for(e, root, "repair")
    # …and the decomposer's own re-cut lifts it, the consumer handed over
    ok, why = I.apply_move(e, root.id, "repair", str(root.assignee), _RESPLIT)
    e.wait_idle()
    assert ok, why
    assert e.dep_order_refuted(root.id) is None
    assert _deps(e, "root.cc") == {"root.headers", "root.pp_2"}, _deps(e, "root.cc")
    assert _deps(e, "root.pp_2") == {"root.headers"}
    e.stop()


def test_a_member_whose_delivery_awaits_its_verdict_holds_the_question_until_it_has_one(tmp_path, monkeypatch):
    e = _ring()
    pp = e.graph.get_task(TaskId("root.pp"))
    T.signal(e, "root.pp", "ACCEPT", str(pp.assignee))
    T.signal(e, "root.pp", "DELIVER", str(pp.assignee), result="pp built")
    e.wait_idle()
    assert e.graph.get_state(TaskId("root.pp")) == State.VALIDATING
    root = e.graph.get_task(TaskId("root"))
    asked = _asked(monkeypatch)
    out = I.settle(e, AgentRegistry(path=str(tmp_path / "agents.json")), root.id, "repair", str(root.assignee), None)
    assert out["status"] == "waiting" and not asked, out
    assert e.graph.get_state(TaskId("root.pp")) == State.VALIDATING
    e.stop()


@pytest.mark.skipif(shutil.which("git") is None, reason="the node workspaces are git worktrees")
def test_the_re_split_starts_from_its_members_work_and_their_passed_parts(tmp_path):
    """Dropped, a member's committed work and its PASSed parts stood on branches nothing joined: its replacement
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
        W.commit_all(w[0], w[1], f"{tid} works", "t", branch=w[2])
    lex.state = State.DONE                      # a part that PASSed and never joined its whole
    e.graph.save_task(lex)
    root = e.graph.get_task(TaskId("root"))
    ok, why = I.apply_move(e, root.id, "repair", str(root.assignee), _RESPLIT)
    e.wait_idle()
    assert ok, why
    pp = e.graph.get_task(TaskId("root.pp_2"))
    place, unjoined, _w = _enter_workspace(e, agents, pp, [pp])
    assert not unjoined, unjoined
    assert {"pp.c", "lex.c"} <= {p.name for p in Path(place).iterdir()}
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


def test_a_replacement_under_the_same_name_carries_the_findings_too():
    e, root = _two()
    _found(e, "root.part", "k", "./x f.c; echo $?")
    ok, why = I._readmit(e, root, {"drop": ["root.part"], "children": [
        {"name": "part", "covers": ["g"], "criteria": [criterion("k", "K holds, as replaced")]}]})
    e.wait_idle()
    assert ok, why
    assert [p["command"] for p in e.regression_probes(TaskId("root.part_2"))["k"]] == ["./x f.c; echo $?"]
    e.stop()
