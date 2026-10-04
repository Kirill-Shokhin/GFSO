"""The moves AUTO offers its machine issuer and its customer can land: a re-decomposition replaces a child under its own
name, `drop_dependency` is offered only where it applies, a probe reads only what it pins, and an AUTO customer on an
empty project is told its one act (GB_c_compiler_tmp5cb096, GB_spreadsheet_engine_tmpekc132)."""
from __future__ import annotations

import threading

from gfso import issuer as I, tools as T, tools_llm as TL
from gfso.core.protocol.procedure import admission_defects
from gfso.core.types import Criteria, Mode, Probe, State, TaskId
from gfso.delegate import AgentRegistry
from tests.support import criterion
from tests.test_the_mode_decides_who_holds_what import _admit, _engine, _goal, _kid


def _spent_root(tmp_path):
    """AUTO, the root at work, a child cancelled so the root's repair question is open; the ledger as three
    unproductive settles left it (the critic's probe, round 2)."""
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("root.part", ["g"], criterion("k", "K holds")), _kid("root.other", ["g"], criterion("o", "O")))
    T.TOOLS["add_dependency"](e, "root.part", "root.other")
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    for a in ("exec-1", "exec-2"):
        agents.register(a, "llm-executor", workdir=str(tmp_path))
    T.signal(e, "root", "ACCEPT", str(e.graph.get_task(TaskId("root")).assignee))
    T.signal(e, "root.part", "CANCEL", str(e.graph.issuer_of(TaskId("root.part"))), reason="dropped")
    e.wait_idle()
    return e, agents


def _sweep(e, agents, ledger):
    claims = set()

    def claim(k):
        return k not in claims and not claims.add(k)

    before = set(threading.enumerate())
    I.answer_open_questions(e, agents, claim, lambda t, redispatch=False: claims.discard(f"q:{t}"),
                            threading.Semaphore(4), None, ledger)
    for th in set(threading.enumerate()) - before:
        th.join(10)
    e.wait_idle()


def test_below_the_root_a_spent_question_is_still_its_machine_issuers_to_close(tmp_path):
    e, agents = _spent_root(tmp_path)
    out = I._close(e, agents, TaskId("root.other"), "external", "spent")
    e.wait_idle()
    assert out["status"] == "cancelled", out


def test_a_reshape_replaces_a_child_under_its_own_name_in_one_act():
    """The re-decomposition §15.5 leaves as the only repair must be able to land: a child the same act drops is gone
    when the replacement's id is chosen (a dropped child keeps its id, Inv-7, so the replacement takes a fresh one)."""
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("root.part", ["g"], criterion("k", "K holds")), _kid("root.other", ["g"], criterion("o", "O")))
    root = e.graph.get_task(TaskId("root"))
    ok, why = I._readmit(e, root, {"drop": ["root.part"], "children": [
        {"name": "part", "covers": ["g"], "criteria": [criterion("k2", "K holds, as replaced")]}]})
    e.wait_idle()
    assert ok, why
    assert e.graph.get_task(TaskId("root.part_2")) is not None
    assert e.graph.get_state(TaskId("root.part")) in (State.CANCELLING, State.ABANDONED)


def _two_parts():
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("root.part", ["g"], criterion("k", "K holds")), _kid("root.other", ["g"], criterion("o", "O")))
    T.TOOLS["add_dependency"](e, "root.other", "root.part")
    e.wait_idle()
    return e, e.graph.get_task(TaskId("root"))


def test_drop_dependency_is_offered_only_where_a_producer_was_cancelled():
    e, root = _two_parts()
    assert "drop_dependency" not in I.moves_for(e, root, "repair")
    ok, why = I.apply_move(e, TaskId("root"), "repair", str(root.assignee),
                           {"move": "drop_dependency", "child_id": "root.part"})
    assert not ok and "not a move for this question" in why
    T.signal(e, "root.other", "CANCEL", str(e.graph.issuer_of(TaskId("root.other"))), reason="no longer needed")
    e.wait_idle()
    assert "drop_dependency" in I.moves_for(e, root, "repair")


def test_a_probe_reading_inputs_it_does_not_pin_is_refused_at_admission():
    """`f={inputs}/t; tr … < $f` against `/usr/bin/tr … < $f` with no `t` pinned: both fail alike, `cmp` agrees, the
    probe passes having read nothing — measured on a plan of this repository's own (base_coreutils.json)."""
    reads = Probe("tr agrees", "f={inputs}/t; cmp <(./tr a b < $f) <(tr a b < $f)", "no output")
    pinned_too = Probe("tr agrees", "f={inputs}/t; cmp <(./tr a b < $f) <(tr a b < $f)", "no output", inputs=(("t", "abc"),))
    assert any("pins nothing there" in d for d in admission_defects([Criteria("k", "K", check=(reads,))]))
    assert not any("pins nothing there" in d for d in admission_defects([Criteria("k", "K", check=(pinned_too,))]))


def test_an_auto_customer_on_an_empty_project_is_told_its_one_act():
    """Offered the manual path on an empty AUTO project, a customer took `create_task`, was refused without the verb
    that states a goal, set about writing the code itself and quit (GB_spreadsheet_engine_tmpekc132)."""
    e = _engine(Mode.AUTO)
    said = T.next_step(e)["directive"]
    assert "auto_decompose" in said and "create_task" not in said, said
    out = TL.TOOLS["create_task"](e, "goal", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    assert out.get("refused") and "auto_decompose" in out["error"], out
