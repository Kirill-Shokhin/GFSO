"""The moves AUTO offers its machine issuer and its customer can land: a re-decomposition replaces a child under its own
name, `drop_dependency` is offered only where it applies, a probe reads only what it pins, and an AUTO customer on an
empty project is told its one act (GB_c_compiler_tmp5cb096, GB_spreadsheet_engine_tmpekc132)."""
from __future__ import annotations


from gfso import issuer as I, tools as T, tools_llm as TL
from gfso.core.protocol.procedure import admission_defects
from gfso.core.types import Criteria, Mode, Probe, State, TaskId
from gfso.delegate import AgentRegistry
from tests.support import criterion
from tests.test_the_mode_decides_who_holds_what import _admit, _engine, _goal, _kid


def test_below_the_root_the_machine_issuers_cancel_lands(tmp_path):
    """The `cancel` move the escalation, parked and external questions offer a machine issuer must land under AUTO."""
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("root.part", ["g"], criterion("k", "K holds")), _kid("root.other", ["g"], criterion("o", "O")))
    T.signal(e, "root", "ACCEPT", str(e.graph.get_task(TaskId("root")).assignee))
    e.wait_idle()
    other = e.graph.get_task(TaskId("root.other"))
    ok, why = I._cancel(e, other, str(e.graph.issuer_of(other.id)), {"move": "cancel"}, "spent", None)
    e.wait_idle()
    assert ok, why
    assert e.graph.get_state(TaskId("root.other")) in (State.CANCELLING, State.ABANDONED)


def test_the_system_does_not_cancel_the_users_goal_under_auto():
    """CANCEL is the refusal of the task (§11.2): at an AUTO root the machine moving for the customer is offered only the
    continuation, and its `cancel` answer is refused — one cancelled a root "all 22 criteria pass" over the standing FAIL
    that escalated it (GB_sql_database_tncfrm404). Below the root, and at a root the user holds, `cancel` stays."""
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("root.part", ["g"], criterion("k", "K holds")))
    root, part = e.graph.get_task(TaskId("root")), e.graph.get_task(TaskId("root.part"))
    for q in ("escalation", "parked", "external"):
        assert "cancel" not in I.moves_for(e, root, q), q
        assert "cancel" in I.moves_for(e, part, q), q
    ok, why = I.apply_move(e, TaskId("root"), "escalation", str(e.graph.issuer_of(root.id)), {"move": "cancel"})
    assert not ok and "not a move for this question" in why
    assert "closing it is theirs" in I.issuer_context(e, TaskId("root"), "escalation")
    held = _engine(Mode.SOLO)
    T.TOOLS["create_task"](held, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    assert "cancel" in I.moves_for(held, held.graph.get_task(TaskId("root")), "escalation")


def test_a_refuted_split_of_the_users_plan_stops_the_run_instead_of_being_remade(monkeypatch):
    """A plan the user handed in whole is theirs under AUTO, as the root's criteria are: where contact refutes its split
    the system does not re-split it — a weak model doing so turned "plan given" into its own plan (2, 9 and 16 nodes
    added on the sql × haiku 4.5 rows) — it stops the run, sessions finishing, with the reason; no model is asked."""
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("root.part", ["g"], criterion("k", "K holds")))
    monkeypatch.setattr(I, "_still_open", lambda *a: True)
    asked = []
    monkeypatch.setattr(I, "issuer_turn", lambda *a, **k: asked.append(a) or {"status": "applied"})
    I.settle(e, AgentRegistry(), TaskId("root"), "repair", "exec-1", verbs=None)
    assert asked and not e.paused(), "a plan the system authored is the system's to repair"
    e.give_users_plan("root")
    asked.clear()
    out = I.settle(e, AgentRegistry(), TaskId("root"), "repair", "exec-1", verbs=None)
    assert out["status"] == "users" and not asked
    # …"refuted" only where contact refuted it on the log; this question was opened by hand (critic over f96e6f8, E)
    assert e.paused() and "the plan the user gave cannot go on at root" in e.paused()["why"]
    e.resume("test")
    monkeypatch.setattr(e, "decomposition_refuted", lambda tid: "root FAILED g while root.part passed")
    I.settle(e, AgentRegistry(), TaskId("root"), "repair", "exec-1", verbs=None)
    assert "the plan the user gave is refuted at root" in e.paused()["why"]


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
    # …AND IT LANDS: two definitions of `_cancelled_producers` had diverged, and the offered move raised (OD-1)
    ok, why = I.apply_move(e, TaskId("root"), "repair", str(root.assignee),
                           {"move": "drop_dependency", "child_id": "root.part"})
    assert ok, why
    assert not [d for d in e.get_dependencies() if str(d.to_id) == "root.part"]


def test_a_probe_over_empty_pinned_code_or_stdin_is_refused_at_admission():
    """The machine's repair parts pinned 0-byte `.sql`/`.c`/`.sh` inputs on their first ASSIGN (40 in
    GB_sql_database_tncfrm404, 79 in GB_c_compiler_tne9g0864). An empty expected output under `diff` and an empty file
    passed as an argument (`tail -n 1 a e b`, a coreutils plan's probe) are cases of their own and stay admissible."""
    def defects(cmd, **files):
        return [d for d in admission_defects([Criteria("k", "K", check=(
            Probe("b", cmd, "PASS", inputs=tuple(files.items())),))]) if "EMPTY" in d]
    assert defects("./sql < {inputs}/q.sql | diff - {inputs}/q.out && echo PASS", **{"q.sql": "", "q.out": "1\n"})
    assert defects(". {inputs}/h.sh; r {inputs}/v.c; echo ok", **{"h.sh": "r(){ cc $1; }", "v.c": ""})
    assert not defects("./sql < {inputs}/q.sql | diff - {inputs}/q.out && echo PASS", **{"q.sql": "x;", "q.out": ""})
    assert not defects("cd {inputs}; diff <(./tail -n 1 a e) <(tail -n 1 a e) && echo PASS", a="1\n", e="")


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
