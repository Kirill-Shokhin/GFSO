"""A seam the person issues is checked by the project's validator, always, before its result reaches him (the author,
2026-11-20: «по gfso на шве (то есть перед тем как принести результат мне) должен стоять обязательный. который
проверит на соответствие исходному замыслу и соответствие всем явным критериям и не даст сказать готово … и мне не
придется держать в памяти критерии неедльной давности … и система заставит уходить на реворк после непрохождения шва»).

At every node he issues to another name the validator checks each delivery against every criterion, his words'
included, and nobody turns that off. The check stands before the delivery: the holder's DELIVER of a tree is refused
while the validator's latest check of that tree failed or none was made, naming what failed and the lift — rework, have
it checked again (`validate_result` on the node at work), deliver the tree that passed (§12.16 (ii): a standing verdict
under the current criteria indicts that tree). Once delivered, his PASS stands on that check; past a FAIL of the
validator's his own hand does not turn it into a pass. The system makes none of his moves: his FAIL is his own."""
from __future__ import annotations

import contextlib
import subprocess

import pytest

import gfso.tools as T
import gfso.tools_llm as TL
from gfso.config import CALLER, Principal
from gfso.core.protocol.invariants import INTENT
from gfso.core.types import TaskId
from gfso.delegate import Dispatcher, ensure_dispatcher
from gfso.engine import validation as V
from gfso.roster import AgentRegistry
from gfso.signin import PAGE
from tests.support import REGISTER, a_repository, criterion, instrument_passes, make_engine

SEAM, HOLDER = "root.eng", "engineering"
#: the holder's own console
CONSOLE = Principal(HOLDER, (HOLDER,), "tok-eng", "token")


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    monkeypatch.delenv("GFSO_VALIDATE_INTERNAL", raising=False)


@contextlib.contextmanager
def _as(p: Principal):
    token = CALLER.set(p)
    try:
        yield
    finally:
        CALLER.reset(token)


def _call(p, verb, e, *a, **kw):
    with _as(p):
        return TL.TOOLS[verb](e, *a, **kw)


def _issued(tmp_path, staffed: bool = True):
    """His root and a seam he issues from it to `engineering` from his page — no mode — with, where `staffed`, the
    project's validator registered; and the answer his issue got."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    if staffed:
        assert not TL.register_agent(e, "p-val", "llm-validator", workdir=str(tmp_path)).get("refused")
        ensure_dispatcher(e).stop()
    _call(PAGE, "create_task", e, "root", {"description": "his goal", "criteria": [criterion("g")]}, assignee="user")
    out = _call(PAGE, "decompose", e, "root", [{"task_id": SEAM, "assignee": HOLDER, "covers": ["g"],
                                                "spec": {"description": "a direction", "criteria": [criterion("d")]}}],
                accepted_risks=REGISTER)
    e.wait_idle()
    T.signal(e, SEAM, "ACCEPT", HOLDER)
    return e, out


def _fails(e):
    e.record_exec_verdict(TaskId(SEAM), "FAIL", ["d"], "p-val", per_criterion=[
        {"criterion": "d", "verdict": "fail", "evidence": "ran check d: it printed NO", "divergences": ["printed NO"]},
        {"criterion": INTENT, "verdict": "pass", "evidence": "read against his words: it answers them"}])


def _checked(e, tree, passes=True):
    """The validator's check of the holder's committed `tree` before its delivery (`judging_before_delivery`)."""
    with e.judging_before_delivery(SEAM, tree, f"c-{tree}"):
        instrument_passes(e, TaskId(SEAM), validator="p-val") if passes else _fails(e)


def _delivers(e, tree=None):
    """The holder's DELIVER — of `tree` as the system records a chat's commit, or of a place recording none."""
    out = T.signal(e, SEAM, "DELIVER", HOLDER, result="it holds", self_validation="PASS",
                   **({"_recorded": (tree, f"c-{tree}", None)} if tree else {}))
    e.wait_idle()
    return out


def _state(e):
    return e.graph.get_state(TaskId(SEAM)).name


# ── 1. the validator checks every delivery of his seam, and nobody removes it ───────────────────────────────────────

def test_the_validator_checks_his_seam_against_every_criterion_his_words_included(tmp_path):
    e, _ = _issued(tmp_path)
    t = e.graph.get_task(TaskId(SEAM))
    assert V.owed_observer(e.graph, t) is not None
    assert e.observes_by_itself(TaskId(SEAM)) and e.checker(TaskId(SEAM)) == "validator"
    assert {c.name for c in t.spec.criteria} == {"d", INTENT}


def test_his_seam_is_checked_by_the_validator_where_its_holder_works_in_a_chat_too(tmp_path):
    e, _ = _issued(tmp_path)
    e.performs_in_chat(HOLDER)
    assert e.scope_at(SEAM) is not None
    assert e.observes_by_itself(TaskId(SEAM)) and e.checker(TaskId(SEAM)) == "validator"


def test_no_one_turns_the_validator_off_at_his_seam_and_he_may_ask_it_again(tmp_path):
    e, _ = _issued(tmp_path)
    e.performs_in_chat(HOLDER)
    off = _call(PAGE, "set_checker", e, SEAM, "self", agent="user")
    assert off.get("refused") and "validator checks every delivery" in off["error"], off
    assert not _call(PAGE, "set_checker", e, SEAM, "validator", agent="user").get("refused")
    assert e.checker(TaskId(SEAM)) == "validator"


# ── 2. before the result reaches him: the holder's delivery waits for the check of its tree ─────────────────────────

def test_a_tree_the_validator_has_not_checked_is_not_delivered(tmp_path):
    e, _ = _issued(tmp_path)
    out = _delivers(e, "tree-1")
    assert not out.get("accepted") and "has not checked this tree" in out["error"] \
        and "validate_result" in out["error"], out
    assert _state(e) == "EXECUTING"


def test_a_tree_whose_check_failed_is_not_delivered_and_the_refusal_names_what_failed(tmp_path):
    e, _ = _issued(tmp_path)
    _checked(e, "tree-1", passes=False)
    out = _delivers(e, "tree-1")
    assert not out.get("accepted") and "failed on d" in out["error"] and "validate_result" in out["error"], out
    assert _state(e) == "EXECUTING"
    with _as(CONSOLE):
        steps = [s for s in T.next_steps(e)["steps"] if s.get("task_id") == SEAM]
    assert steps, "the holder is told its move"


def test_a_tree_checked_after_its_repair_is_delivered_and_his_page_signs_on_that_check(tmp_path):
    e, _ = _issued(tmp_path)
    _checked(e, "tree-1", passes=False)
    _checked(e, "tree-2")
    assert not _delivers(e, "tree-1").get("accepted"), "the failed tree, not the one that passed"
    assert _delivers(e, "tree-2").get("accepted")
    assert _state(e) == "VALIDATING"
    assert _call(PAGE, "signal", e, SEAM, "PASS", "user")["state"] == "DONE"


def test_the_tree_a_delivery_failed_on_is_not_handed_in_again(tmp_path):
    """The validator's FAIL of a delivered tree is its latest check of that tree: after his FAIL the holder reworks."""
    e, _ = _issued(tmp_path)
    _checked(e, "tree-1")
    assert _delivers(e, "tree-1").get("accepted")
    _fails(e)
    assert not _call(PAGE, "signal", e, SEAM, "PASS", "user").get("accepted")
    assert _call(PAGE, "signal", e, SEAM, "FAIL", "user", failed_criteria=["d"])["state"] == "REWORKING"
    with _as(CONSOLE):
        steps = [s for s in T.next_steps(e)["steps"] if s.get("task_id") == SEAM]
    assert any("FIX AND RE-DELIVER" in s["directive"] and "d" in s["directive"] for s in steps), steps
    again = _delivers(e, "tree-1")
    assert not again.get("accepted") and "failed on d" in again["error"], again
    _checked(e, "tree-2")
    assert _delivers(e, "tree-2").get("accepted")


def test_the_system_signs_no_fail_of_his(tmp_path):
    """His FAIL is his issuer move (§10.2): a validator's FAIL on a delivery stands on the record, the node waits."""
    e, _ = _issued(tmp_path)
    _checked(e, "tree-1")
    _delivers(e, "tree-1")
    _fails(e)
    Dispatcher(e, AgentRegistry(path=str(tmp_path / "agents.json"))).dispatch_once()
    e.wait_idle()
    assert _state(e) == "VALIDATING"


def test_the_check_before_the_delivery_judges_the_committed_tree_and_moves_nothing(tmp_path):
    """`validate_result` on the node at work judges the holder's HEAD as delivered (`delivered`), its record naming
    that tree; a place that is no repository's top is refused naming the lift."""
    e, _ = _issued(tmp_path)
    repo = a_repository(tmp_path / "repo")
    before = TL._before_its_delivery(e, SEAM, str(repo), None)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD", "HEAD^{tree}"], capture_output=True,
                          text=True).stdout.split()
    assert (before["commit"], before["tree"]) == tuple(head), before
    with e.judging_before_delivery(SEAM, before["tree"], before["commit"]):
        assert e.delivered(TaskId(SEAM))[:2] == (before["tree"], before["commit"])
        instrument_passes(e, TaskId(SEAM), validator="p-val")
    assert e.delivered(TaskId(SEAM)) is None and _state(e) == "EXECUTING"
    assert e.current_exec_verdict(TaskId(SEAM))["tree"] == before["tree"]
    (tmp_path / "bare").mkdir()
    assert "not the top of a git repository" in TL._before_its_delivery(e, SEAM, str(tmp_path / "bare"), None)["error"]


# ── 3. a delivery recording no tree: observed after it lands, its PASS bound ────────────────────────────────────────

def test_his_pass_is_refused_while_the_validators_observation_is_owed(tmp_path):
    """His own reading recorded by his hand is his, and adds to the check: it is not the validator's observation."""
    e, _ = _issued(tmp_path)
    assert _delivers(e).get("accepted")
    assert not _call(PAGE, "signal", e, SEAM, "PASS", "user").get("accepted")
    instrument_passes(e, TaskId(SEAM), validator="user", by_hand=True)
    out = _call(PAGE, "signal", e, SEAM, "PASS", "user")
    assert not out.get("accepted") and "observ" in out["error"], out
    assert _state(e) == "VALIDATING"


def test_his_pass_is_refused_past_the_validators_fail_and_his_own_record_does_not_lift_it(tmp_path):
    e, _ = _issued(tmp_path)
    _delivers(e)
    _fails(e)
    with contextlib.suppress(ValueError):                # …his own observation, recorded by his hand
        instrument_passes(e, TaskId(SEAM), validator="user", by_hand=True)
    assert not _call(PAGE, "signal", e, SEAM, "PASS", "user").get("accepted")


def test_on_the_validators_pass_his_page_signs(tmp_path):
    e, _ = _issued(tmp_path)
    _delivers(e)
    instrument_passes(e, TaskId(SEAM), validator="p-val")
    assert _call(PAGE, "signal", e, SEAM, "PASS", "user")["state"] == "DONE"


# ── 4. staffing ──────────────────────────────────────────────────────────────

def test_a_seam_issued_with_no_validator_names_its_registration_at_the_delivery_and_his_pass(tmp_path):
    e, _ = _issued(tmp_path, staffed=False)
    assert "llm-validator" in str(_delivers(e).get("staff"))
    refused = _call(PAGE, "signal", e, SEAM, "PASS", "user")
    assert not refused.get("accepted") and "llm-validator" in str(refused), refused
    (tmp_path / "s").mkdir()
    staffed, _ = _issued(tmp_path / "s")
    assert "staff" not in _delivers(staffed)
