"""A structural move through a door is signed, and only by the one who holds the role the move is keyed by — the node's
issuer for its contract, its Del for its split (`engine.moves.DOOR_KEYS`); unsigned, the signer is the door's standing
identity. Before, an unsigned `decompose` of carol's node passed and the log named carol, a `reassign` named alice:
Thm 11 wants every decision's author on record (ui's human-door critic, 2026-11-14). And a goal set through a signed
door is issued by its signer (§15.2: the root is created by the goal's issuer), who then holds its issuer moves.

CONTROL: drop the signer check from `tools_llm._mode_lock` and the refusals below pass through."""
from gfso import tools_llm as TL
from gfso.core.types import TaskId
from tests.support import REGISTER, criterion, make_engine


def _people():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    TL.TOOLS["create_task"](e, task_id="root", spec={"description": "goal", "criteria": [criterion("g")]},
                            assignee="alice", agent="alice")
    return e


def _split(e, agent):
    return TL.TOOLS["decompose"](e, parent_id="root", agent=agent, accepted_risks=REGISTER, children=[
        {"task_id": "root.a", "assignee": "carol", "covers": ["g"], "spec": {"description": "a", "criteria": [criterion("a")]}}])


def test_an_unsigned_or_foreign_split_is_refused_and_the_holders_is_taken():
    e = _people()
    for agent in (None, "mallory"):
        out = _split(e, agent)
        assert out.get("refused") or out.get("error"), out
        assert "alice" in str(out), out                     # it names who holds the move
    assert not e.graph.get_task(TaskId("root.a"))
    out = _split(e, "alice")
    assert e.graph.get_task(TaskId("root.a")) is not None, out
    e.stop()


def test_a_reassign_is_the_issuers_move():
    e = _people()
    _split(e, "alice")
    e.wait_idle()
    out = TL.TOOLS["reassign"](e, task_id="root.a", assignee="dave", agent="carol")
    assert (out.get("refused") or out.get("error")) and str(e.graph.get_task(TaskId("root.a")).assignee) == "carol", out
    TL.TOOLS["reassign"](e, task_id="root.a", assignee="dave", agent="alice")
    assert str(e.graph.get_task(TaskId("root.a")).assignee) == "dave"
    e.stop()


def test_a_goal_set_for_another_is_issued_by_its_signer():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    TL.TOOLS["create_task"](e, task_id="root", spec={"description": "goal", "criteria": [criterion("g")]},
                            assignee="techlead", agent="pm")
    assert str(e.graph.issuer_of(TaskId("root"))) == "pm"
    moves = TL.TOOLS["available_actions"](e, task_id="root", agent="pm")
    assert "edit_criteria" in moves.get("moves", {}), moves
    assert "edit_criteria" not in TL.TOOLS["available_actions"](e, task_id="root", agent="techlead").get("moves", {})
    e.stop()


def test_the_offer_names_who_signs_each_move():
    e = _people()
    got = TL.TOOLS["available_actions"](e, task_id="root", agent="*").get("moves", {})
    assert got.get("decompose") == "alice" and got.get("edit_criteria") == "alice", got
    e.stop()


def test_the_offer_names_who_a_page_signs_a_verdict_as():
    """`record_verdict` is a check (§10.2), so neither `performed_by` nor `moves` names its signer, and a root's issuer is
    not on the node: the page copied the door's default rule (ui, 2026-11-15). `checks` carries the name the door's own
    default reads (`moves.role_holder`). CONTROL: drop `checks` from `tools.available_actions` and this fails."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    TL.TOOLS["create_task"](e, task_id="root", spec={"description": "goal", "criteria": [criterion("g")]},
                            assignee="techlead", agent="pm")
    TL.TOOLS["decompose"](e, parent_id="root", agent="techlead", accepted_risks=REGISTER, children=[
        {"task_id": "root.a", "assignee": "carol", "covers": ["g"], "spec": {"description": "a", "criteria": [criterion("a")]}}])
    look = lambda n: TL.TOOLS["available_actions"](e, task_id=n, agent="*").get("checks")
    assert look("root") == {"record_verdict": "pm", "validate_result": "pm", "review_decomposition": "techlead"}
    assert look("root.a")["record_verdict"] == "techlead" and look("root.a")["review_decomposition"] == "carol"
    assert all(look("root")[v] == TL._holder_of(e, v, {"task_id": "root"}) for v in look("root"))
    e.stop()


def test_a_split_the_system_authors_is_signed_by_its_author():
    """`auto_decompose` signs by `author` — the argument the doors pin for it: offered to its Del and signed by `agent`
    it had no way through (critic, 2026-11-14)."""
    e = _people()
    assert TL.TOOLS["available_actions"](e, task_id="root", agent="alice")["moves"].get("auto_decompose") == "alice"
    out = TL.TOOLS["auto_decompose"](e, request="split it", root_id="root", author="mallory")
    assert "'mallory' is not the executor" in str(out), out
    out = TL.TOOLS["auto_decompose"](e, request="split it", root_id="root", author="alice")
    assert "is not the executor" not in str(out), out
    e.stop()
