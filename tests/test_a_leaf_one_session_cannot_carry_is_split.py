"""The leaf test (§3.7) read at contact: a leaf the system executes that fails the same criteria round after round is
above its holder's κ, and its split is owed — on the version that stands, after the round that may challenge, and
never with a refusal nobody can lift."""
import dataclasses

import gfso.delegate as D
from gfso.core.types import AgentId, RevisionReason, Signal, State, TaskId
from gfso.issuer import Verbs, settle
from gfso.packets import _rework_section
from tests.test_one_session_carries_a_scope import _LLM, _dispatcher, _entry, _free_claim, _project


def _leaves(tmp_path, monkeypatch):
    """AUTO over root → a, b with nobody's session judgement: each node takes a session of its own."""
    monkeypatch.setattr(D, "answer_open_questions", lambda *a, **k: [])
    e, agents = _project(tmp_path, fits=False)
    for t in ("root", "root.a", "root.b"):
        e.record_session_fit(TaskId(t), "", None)
    return e, agents, _dispatcher(e, agents, _LLM(), _LLM(), [])


def _fail_once(e, tid, crit):
    t = e.graph.get_task(TaskId(tid))
    ex = str(t.assignee)
    if t.state == State.OFFERED:
        assert D._signal(e, t.id, Signal.ACCEPT, ex)
    assert D._signal(e, t.id, Signal.DELIVER, ex, result="r", self_validation="PASS"), e.graph.get_state(t.id)
    e.wait_idle()
    key = _free_claim(e, tid)
    e.record_exec_verdict(t.id, "FAIL", [crit], "val-1", per_criterion=[_entry(tid, crit, "fail")],
                          require_probe=True, log_at=key.log_at if key else None)
    if key:
        e.claims.end_validation(key)
    iss = str(e.graph.issuer_of(t.id))
    assert (D._signal(e, t.id, Signal.FAIL, "val-1", failed_criteria=(crit,), reason="no")
            or D._signal(e, t.id, Signal.FAIL, iss, failed_criteria=(crit,), reason="no"))
    e.wait_idle()


def _leaf(e):
    return e.graph.get_task(TaskId("root.a"))


def test_the_round_after_three_equal_fails_may_challenge_and_the_fourth_owes_the_split(tmp_path, monkeypatch):
    e, _, d = _leaves(tmp_path, monkeypatch)
    for _ in range(3):
        _fail_once(e, "root.a", "a_ok")
    assert not d._split_owed_said(_leaf(e)) and e.split_owed(TaskId("root.a")) is None
    assert "a_ok failed in each of the last 3 rounds" in _rework_section(e, _leaf(e))
    _fail_once(e, "root.a", "a_ok")
    assert d._split_owed_said(_leaf(e)) and e.split_owed(TaskId("root.a")) is not None
    e.stop()


def test_a_new_version_lapses_the_refutation_and_resets_the_rounds(tmp_path, monkeypatch):
    e, _, d = _leaves(tmp_path, monkeypatch)
    for _ in range(4):
        _fail_once(e, "root.a", "a_ok")
    assert d._split_owed_said(_leaf(e))
    leaf = _leaf(e)
    spec = dataclasses.replace(leaf.spec, description=leaf.spec.description + " (criterion corrected)")
    e.revise(leaf.id, spec, AgentId(str(e.graph.issuer_of(leaf.id))), reason=RevisionReason.SPEC_DEFECT)
    e.wait_idle()
    assert e.split_owed(TaskId("root.a")) is None
    assert e.stuck_on(TaskId("root.a")) == [] and not d._split_owed_said(_leaf(e))
    e.stop()


def test_a_split_that_builds_nothing_gives_the_session_back_and_its_rounds_stay_spent(tmp_path, monkeypatch):
    e, agents, d = _leaves(tmp_path, monkeypatch)
    for _ in range(4):
        _fail_once(e, "root.a", "a_ok")
    assert d._split_owed_said(_leaf(e))
    idle = Verbs(llm=None, busy=None, review=None, refine=lambda en, node: {"subtasks": []})
    assert settle(e, agents, TaskId("root.a"), "split", "exec-2", idle)["status"] != "applied"
    assert e.split_owed(TaskId("root.a")) is None and not d._split_owed_said(_leaf(e))
    _fail_once(e, "root.a", "a_ok")          # one fresh round: the four already judged are not counted again
    assert not d._split_owed_said(_leaf(e))
    e.stop()


def test_rounds_a_scope_refutation_spent_are_not_a_leafs_own(tmp_path, monkeypatch):
    e, _, d = _leaves(tmp_path, monkeypatch)
    for _ in range(4):
        _fail_once(e, "root.a", "a_ok")
    e.refute_session_fit(TaskId("root"), [e.graph.get_task(TaskId("root")), _leaf(e)])
    assert e.spent_fails(TaskId("root.a")) == 4
    assert not d._split_owed_said(_leaf(e)) and e.split_owed(TaskId("root.a")) is None
    e.stop()
