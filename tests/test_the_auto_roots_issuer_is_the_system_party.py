"""Under AUTO the root's issuer is the system party acting for the person (§10.4: autonomous — the LLM the issuer, the
human «oversight at the level above»), recorded at the root's creation; `party_kind` reads a party's kind from what the
party is, never from the project's mode. ONE RULE moves a goal's issuer with AUTO, at a switch of mode and on the
one-time reading of a stored AUTO project: a root handed over (its Del not his) goes into AUTO from the person to the
system party and out of it back to him, the move logged, its logged ASSIGN untouched; a root he holds himself keeps him
its issuer, and its parts keep him theirs (Del(root), Inv-7) — his moves at his own door, which the mode's lock no
longer refuses him (Inv-8: the owner keeps a move; MODE_REDUCTION §3b).

CONTROLS (each run, each red): let `record_root_issuer` keep the person under AUTO — the first test; drop `party_kind`'s
system branch — the first two; drop `_the_system_party_where_auto_created` from `start` — both stored projects' tests;
drop the switch's move of the roots' issuer — the AUTO→SOLO/SEMI and the no-mode→AUTO tests; drop `_his_role` from
`mode_holder` — both cases of the held root's parts; drop `_hand_over`'s Del filter — those and the settled root's;
read a refusal by the current mover's name alone (`refused_on_this_version`) — the refusal's test."""
from __future__ import annotations

import json

import pytest

import gfso.tools as T
import gfso.tools_llm as TL
from gfso import issuer as I
from gfso.config import SYSTEM
from gfso.core.graph.model import issuer_moves_key, root_issuer_key
from gfso.core.types import AgentId, DoneReason, Mode, Signal, State, TaskId
from gfso.delegate import Dispatcher
from gfso.engine.validation import party_kind, signer_refusal
from tests.support import REGISTER, criterion, make_engine, pinned
from tests.test_delegate import _agents
from tests.test_the_mode_decides_who_holds_what import _admit, _engine, _kid

ROOT = TaskId("root")
SPEC = {"description": "the goal", "criteria": [criterion("g", "G holds")], "accepted_risks": REGISTER}
ROLES = (("exec-1", "llm-executor"), ("exec-2", "llm-executor"), ("val-1", "llm-validator"))


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _new_auto():
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", SPEC)
    e.wait_idle()
    return e


def _dispatcher(e, tmp_path):
    agents = _agents(tmp_path, *ROLES)
    return agents, Dispatcher(e, agents, poll=30, runner=lambda *a, **k: None, validator_runner=lambda *a, **k: None)


def _runs_unattended(e, tmp_path):
    """The root, delivered by its executor and checked by the instrument, is signed by the system: DONE."""
    agents, d = _dispatcher(e, tmp_path)
    assert d._issuer_is_automated(ROOT), "the system no longer signs the AUTO root"
    assert d._resolves_blocks_for(ROOT), "the system no longer resolves the AUTO root's blocks"
    assert I.system_mover(e, agents.list(), ROOT, "dispute") == SYSTEM
    assert e.persons_seam(ROOT), "the AUTO root stopped being a seam issued in the person's name"
    assert signer_refusal(e.graph, ROOT, Signal.ACCEPT_CHALLENGE, "user") is None, "his ruling there was refused"
    assert signer_refusal(e.graph, ROOT, Signal.ACCEPT_CHALLENGE, "exec-2") is not None
    T.signal(e, "root", "ACCEPT", "exec-1")
    T.signal(e, "root", "DELIVER", "exec-1", result="built it")
    e.wait_idle()
    e._graph.authorized_validators = {"val-1"}
    e.record_exec_verdict(ROOT, "PASS", [], "val-1", tools_used={"Bash": 1}, per_criterion=[
        {"criterion": "g", "verdict": "pass", "evidence": "ran it", "probe": [
            {"command": p.command, "expect": p.expect, "behaviour": p.behaviour} for p in pinned("g")]}])
    out = T.signal(e, "root", "PASS", "val-1")
    e.wait_idle()
    assert e.graph.get_state(ROOT).name == "DONE", out


def _the_persons_again(e, tmp_path, mode):
    """A switch out of AUTO hands the live root back to him, as when the record said his name: his to sign, the system's
    no longer, the move logged."""
    e.set_mode(mode, None, AgentId("user"))
    agents, d = _dispatcher(e, tmp_path)
    assert str(e.graph.issuer_of(ROOT)) == "user"
    assert e.issuer_kind(ROOT) == "holder" and e.holder_signs(ROOT)
    assert not d._issuer_is_automated(ROOT), "the system still signs a root the person issues again"
    assert I.system_mover(e, agents.list(), ROOT, "dispute") is None
    (moved,) = json.loads(e._storage.get_setting(issuer_moves_key(ROOT)))
    assert (moved["from"], moved["to"]) == (SYSTEM, "user"), moved


def test_a_new_auto_roots_issuer_is_the_system_party(tmp_path):
    e = _new_auto()
    assert e._storage.get_setting(root_issuer_key(ROOT)) == SYSTEM
    assert str(e.graph.issuer_of(ROOT)) == SYSTEM
    assign = next(a for a in e.audit_log(ROOT) if a.signal == Signal.ASSIGN)
    assert str(assign.source) == SYSTEM, "the root's ASSIGN is not signed by its issuer"
    _runs_unattended(e, tmp_path)
    e.stop()


def test_the_kind_is_the_partys_not_the_modes():
    bare = make_engine()
    assert party_kind(bare.graph, SYSTEM) == "machine", "the system party read as a machine only through a mode"
    for mode, kind in ((None, "person"), (Mode.SOLO, "holder"), (Mode.SEMI, "holder"), (Mode.AUTO, "holder")):
        g = _engine(mode)
        assert party_kind(g.graph, "user") == kind, mode
        assert party_kind(g.graph, SYSTEM) == "machine", mode
        g.stop()


def _opened(storage):
    e = make_engine(storage, validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.workforce.publish_executor_pool({"exec-1": "p", "exec-2": "p"})
    return e


def _stored(created_under_auto: bool, refused: str = ""):
    """A project an earlier build wrote — its AUTO root's issuer recorded and its ASSIGN logged under the person's name,
    created under the AUTO record or before it began (a switch into AUTO an earlier build allowed) — reopened.
    `refused`: a move of the root's issuer refused on this version before the reopen, signed in the person's name as
    that build signed the system's moves."""
    storage = make_engine()._storage
    e = _opened(storage)
    if created_under_auto:
        e.set_mode(Mode.AUTO, None, AgentId("user"))
    e._storage.store_setting(root_issuer_key(ROOT), "user")
    e.assign_task(ROOT, T._spec_from(SPEC), AgentId("exec-1"))
    e.wait_idle()
    if not created_under_auto:
        e.set_mode(Mode.AUTO, None, AgentId("user"))
        e._storage.store_setting(root_issuer_key(ROOT), "user")       # …as the earlier switch left it
        e._storage.store_setting(issuer_moves_key(ROOT), "")
    if refused:
        e.record_refused_move(ROOT, Signal.REJECT_CHALLENGE, "user", refused)
    e.stop()
    assert str(e.graph.issuer_of(ROOT)) == "user"
    return _opened(storage)


def test_a_stored_auto_root_issued_by_the_person_reads_the_system_party_and_runs_as_before(tmp_path):
    e = _stored(created_under_auto=True)
    assert str(e.graph.issuer_of(ROOT)) == SYSTEM
    assign = next(a for a in e.audit_log(ROOT) if a.signal == Signal.ASSIGN)
    assert str(assign.source) == "user", "the logged ASSIGN was rewritten"
    assert '"from": "user", "to": "system"' in e._storage.get_setting(issuer_moves_key(ROOT))
    _runs_unattended(e, tmp_path)
    e.stop()


def test_a_stored_root_an_earlier_build_switched_into_auto_runs_to_its_verdict_unattended(tmp_path):
    """Created before its AUTO record began, its issuer the person's: left so, under AUTO nobody could sign it (the
    system makes no move of his, the mode's lock refuses his door). It gets the move a switch makes now, logged."""
    e = _stored(created_under_auto=False)
    assert str(e.graph.issuer_of(ROOT)) == SYSTEM
    (moved,) = json.loads(e._storage.get_setting(issuer_moves_key(ROOT)))
    assert (moved["from"], moved["to"], moved["why"]) == ("user", SYSTEM, "switched into AUTO by an earlier build")
    _runs_unattended(e, tmp_path)
    e.stop()


@pytest.mark.parametrize("mode", [Mode.SOLO, Mode.SEMI])
def test_a_switch_out_of_auto_hands_the_root_back_to_the_person(tmp_path, mode):
    e = _new_auto()
    _the_persons_again(e, tmp_path, mode)
    e.stop()


def test_a_switch_into_auto_hands_his_roots_held_by_others_to_the_system_party(tmp_path):
    """With no mode, a goal he issued to an executor is his; switched into AUTO the system makes its issuer moves, as it
    did when the mode re-typed his name — now by the logged move of the role to the system party."""
    e = _engine()
    T.create_task(e, "root", SPEC, assignee="exec-1", agent="user")
    e.wait_idle()
    assert str(e.graph.issuer_of(ROOT)) == "user"
    e.set_mode(Mode.AUTO, None, AgentId("user"))
    assert str(e.graph.issuer_of(ROOT)) == SYSTEM
    _runs_unattended(e, tmp_path)
    e.stop()




KIDS = ("root.kid", "root.talk", "root.late")


def _his_held_root(switched: bool):
    """The critic's state: under SEMI the person holds the root, its parts went to exec-1 — `root.kid` delivered,
    `root.talk` disputed, `root.late` escalated — and the project went into AUTO over it: by a switch now, or (`switched`
    False) as an earlier build stored that switch, reopened so the one-time reading runs."""
    storage = make_engine()._storage
    e = _opened(storage)
    e.set_mode(Mode.SEMI, 1, AgentId("user"))
    T.create_task(e, "root", {"description": "the goal", "criteria": [
        criterion("g", "G holds"), criterion("h", "H holds"), criterion("j", "J holds")], "accepted_risks": REGISTER})
    e.wait_idle()
    _admit(e, "root", _kid("root.kid", ["g"], criterion("k", "K holds")),
           _kid("root.talk", ["h"], criterion("t", "T holds")), _kid("root.late", ["j"], criterion("l", "L holds")))
    assert TL.TOOLS["signal"](e, "root", "ACCEPT", "user")["accepted"]
    for kid, sig, kw in (("root.kid", "ACCEPT", {}), ("root.kid", "DELIVER", {"result": "built k"}),
                         ("root.talk", "CHALLENGE", {"reason": "T cannot hold as written"})):
        assert T.signal(e, kid, sig, "exec-1", **kw)["accepted"], (kid, sig)
    e.wait_idle()
    late = e.graph.get_task(TaskId("root.late"))
    late.state, late.done_reason = State.ESCALATED, DoneReason.FAIL
    e.graph.save_task(late)
    if switched:
        e.set_mode(Mode.AUTO, None, AgentId("user"))
        return e
    e._storage.store_setting("mode", json.dumps({"mode": "auto", "boundary": None, "by": "user", "seq": 2,
                                                 "log_at": len(e._audit)}))
    e.stop()
    return _opened(storage)


@pytest.mark.parametrize("switched", [True, False], ids=["a switch now", "an earlier build's switch, read at start"])
def test_under_auto_every_move_owed_on_his_held_roots_parts_is_made_by_him(tmp_path, switched):
    """Del(root) is his, so he issues its parts (Inv-7; a stand-in from above is excluded, §12.13): neither act moves it,
    and the system makes no move of his. So each move owed there is his, taken at his own door — the verdict on the
    delivery, the dispute, the escalation —, `next_steps` names him, and the feed says it waits on him (Inv-8: in every
    state the owner has a move). A CHANGE: before, under AUTO the person's name was a machine's, and the system made
    these issuer moves in his name, unattended; now a move signs as its own party and the system never signs as him.
    What had no mover at all, his split and consent on what he holds, is his at his door too."""
    e = _his_held_root(switched)
    assert str(e.graph.issuer_of(ROOT)) == "user" and not e._storage.get_setting(issuer_moves_key(ROOT))
    agents, _ = _dispatcher(e, tmp_path)
    for kid in KIDS:
        assert str(e.graph.issuer_of(TaskId(kid))) == "user" and e.issuer_kind(TaskId(kid)) == "holder", kid
        assert e.mode_holder(kid, "issuer") is None, f"the door holds {kid}'s issuer move from its owner"
    assert I.system_mover(e, agents.list(), TaskId("root.talk"), "dispute") is None
    said = [p["message"] for p in e._storage.get_pipeline() if p["source"] == "mode"]
    assert any(m.startswith("root, root.kid, root.talk, root.late are yours under auto") for m in said), said
    steps = {s["task_id"]: s for s in T.next_steps(e, actor="user")["steps"]}
    for kid in KIDS:
        assert (steps[kid]["performed_by"], steps[kid]["mine"]) == ("user", True), steps[kid]
        assert "NOT YOURS" not in steps[kid]["directive"], steps[kid]["directive"]
    out = TL.TOOLS["signal"](e, "root.talk", "REJECT_CHALLENGE", "user", reason="T holds as written")
    assert out.get("accepted"), out
    out = TL.TOOLS["signal"](e, "root.late", "CANCEL", "user", reason="J is not needed")
    assert out.get("accepted"), out
    e._graph.authorized_validators = {"val-1"}
    e.record_exec_verdict(TaskId("root.kid"), "PASS", [], "val-1", tools_used={"Bash": 1}, per_criterion=[
        {"criterion": "k", "verdict": "pass", "evidence": "ran it", "probe": [
            {"command": p.command, "expect": p.expect, "behaviour": p.behaviour} for p in pinned("k")]}])
    assert e.holder_signs(TaskId("root.kid")), "the observation signed for him"
    out = TL.TOOLS["signal"](e, "root.kid", "PASS", "user")
    e.wait_idle()
    assert out.get("accepted") and e.graph.get_state(TaskId("root.kid")) == State.DONE, out
    e.stop()


@pytest.mark.parametrize("switched", [True, False], ids=["a switch now", "an earlier build's switch, read at start"])
def test_a_settled_root_he_held_himself_stays_his_by_either_act(switched):
    """One rule for the switch and the reading at start: a root he holds himself keeps him its issuer (§10.1: at a
    self-assigned root its own executor), settled or not — the switch moved a settled one, the reading did not."""
    storage = make_engine()._storage
    e = _opened(storage)
    e.set_mode(Mode.SOLO, None, AgentId("user"))
    T.create_task(e, "root", SPEC)
    e.wait_idle()
    T.signal(e, "root", "CANCEL", "user", reason="not wanted")
    e.wait_idle()
    T.signal(e, "root", "CONFIRM_CANCEL", "user")
    e.wait_idle()
    if switched:
        e.set_mode(Mode.AUTO, None, AgentId("user"))
    else:
        e._storage.store_setting("mode", json.dumps({"mode": "auto", "boundary": None, "by": "user", "seq": 2,
                                                     "log_at": len(e._audit)}))
        e.stop()
        e = _opened(storage)
    assert str(e.graph.issuer_of(ROOT)) == "user" and not e._storage.get_setting(issuer_moves_key(ROOT))
    e.stop()


def test_a_refusal_logged_before_the_reading_is_the_issuer_roles_after_it():
    """A refusal is read by the role on that version (`issuer_at`), not by the current mover's name: refused while the
    log signed the system's moves `user`, it is the system party's after the one-time reading, so the system does not
    retry, blind, a move already refused there."""
    e = _stored(created_under_auto=True, refused="the dispute's ruling named no criterion")
    assert str(e.graph.issuer_of(ROOT)) == SYSTEM
    assert "named no criterion" in I.refused_on_this_version(e, ROOT, SYSTEM)
    assert I.refused_on_this_version(e, ROOT, "exec-2") == ""
    e.stop()
