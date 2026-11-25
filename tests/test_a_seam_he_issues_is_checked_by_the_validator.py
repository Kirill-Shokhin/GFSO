"""A seam the person issues whose check he gave the project's validator is checked by it before its result reaches him
(the author, 2026-11-20: «по gfso на шве (то есть перед тем как принести результат мне) должен стоять обязательный.
который проверит на соответствие исходному замыслу и соответствие всем явным критериям и не даст сказать готово … и
мне не придется держать в памяти критерии неедльной давности … и система заставит уходить на реворк после
непрохождения шва»). Who checks is his appointment, at a seam too (2026-11-23: «издатель назначает валидатора и
точка»): by default himself, and the validator between him and an agent working in its chat (`validation.his_check`).

Where the validator checks it, it checks each delivery against every criterion. The check stands before the delivery: the holder's DELIVER of a tree is refused
while the validator's latest check of that tree failed or none was made, naming what failed and the lift — rework, have
it checked again (`validate_result` on the node at work), deliver the tree that passed (§12.16 (ii): a standing verdict
under the current criteria indicts that tree). Once delivered, his PASS stands on that check; past a FAIL of the
validator's his own hand does not turn it into a pass. The system makes none of his moves: his FAIL is his own."""
from __future__ import annotations

import contextlib
import json
import subprocess

import pytest

import gfso.packets as P
import gfso.tools as T
import gfso.tools_llm as TL
from gfso.config import CALLER, STANDING, Principal
from gfso.core.protocol.invariants import INTENT
from gfso.core.types import AgentId, Mode, TaskId
from gfso.delegate import Dispatcher, ensure_dispatcher
from gfso.engine import validation as V
from gfso.engine.verdicts import observations
from gfso.roster import AgentRegistry
from gfso.signin import PAGE
from tests.support import REGISTER, a_repository, criterion, instrument_passes, make_engine
import gfso.validate as VAL

SEAM, HOLDER = "root.eng", "engineering"
HUMAN = "yana"     # …on no roster, in no chat: a human (`roster`: unlisted ids are humans)
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


def _issued(tmp_path, staffed: bool = True, mode=None, checker: str = "validator", holder: str = HOLDER,
            in_chat: bool = False):
    """His root and a seam he issues from it to `engineering` from his page — under `mode`, none by default — with,
    where `staffed`, the project's validator registered, where `in_chat` its holder working in its chat before the
    issue, and `checker` his appointment of who checks it (None: none made); and the answer his issue got."""
    a_repository(tmp_path)    # …where his roles work: a repository, as every directory a role is named in
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    if mode is not None:      # …a mode's seams below his root are held by a registered executor
        e.set_mode(mode, None, AgentId("user"))
        assert not TL.register_agent(e, HOLDER, "llm-executor", workdir=str(tmp_path)).get("refused")
        ensure_dispatcher(e).stop()
    if staffed:
        assert not TL.register_agent(e, "p-val", "llm-validator", workdir=str(tmp_path)).get("refused")
        ensure_dispatcher(e).stop()
    if in_chat:
        e.performs_in_chat(holder)
    _call(PAGE, "create_task", e, "root", {"description": "his goal", "criteria": [criterion("g")]}, assignee="user")
    covers = [c.name for c in e.graph.get_task(TaskId("root")).spec.criteria]     # …his words' too, under a mode
    out = _call(PAGE, "decompose", e, "root", [{"task_id": SEAM, "assignee": holder, "covers": covers,
                                                "spec": {"description": "a direction", "criteria": [criterion("d")]}}],
                accepted_risks=REGISTER)
    e.wait_idle()
    if checker is not None:
        assert _call(PAGE, "set_checker", e, SEAM, checker, agent="user")["checker"] == checker
    T.signal(e, SEAM, "ACCEPT", holder)
    return e, out


def _fails(e):
    e.record_exec_verdict(TaskId(SEAM), "FAIL", ["d"], "p-val", per_criterion=[
        {"criterion": "d", "verdict": "fail", "evidence": "ran check d: it printed NO", "divergences": ["printed NO"]},
        {"criterion": INTENT, "verdict": "pass", "evidence": "read against his words: it answers them"}])


def _checked(e, tree, passes=True):
    """The validator's check of the holder's committed `tree` before its delivery (`judging_before_delivery`)."""
    with e.judging_before_delivery(SEAM, tree, f"c-{tree}"):
        instrument_passes(e, TaskId(SEAM), validator="p-val") if passes else _fails(e)


def _delivers(e, tree=None, holder: str = HOLDER):
    """The holder's DELIVER — of `tree` as the system records a chat's commit, or of a place recording none."""
    out = T.signal(e, SEAM, "DELIVER", holder, result="it holds", self_validation="PASS",
                   **({"_recorded": (tree, f"c-{tree}", None)} if tree else {}))
    e.wait_idle()
    return out


def _state(e):
    return e.graph.get_state(TaskId(SEAM)).name


# ── 1. the validator checks every delivery of his seam, and nobody removes it ───────────────────────────────────────

def test_the_validator_he_appointed_checks_his_seam_against_every_criterion(tmp_path):
    e, _ = _issued(tmp_path)
    t = e.graph.get_task(TaskId(SEAM))
    assert V.owed_observer(e.graph, t) is not None
    assert e.observes_by_itself(TaskId(SEAM)) and e.checker(TaskId(SEAM)) == "validator"
    assert {c.name for c in t.spec.criteria} == {"d"}, "a human's node: no criterion of his words pinned to this git"


def test_his_seam_is_checked_by_the_validator_where_its_holder_works_in_a_chat_too(tmp_path):
    e, _ = _issued(tmp_path, checker=None, in_chat=True)
    assert e.scope_at(SEAM) is not None
    assert e.observes_by_itself(TaskId(SEAM)) and e.checker(TaskId(SEAM)) == "validator"


@pytest.mark.parametrize("later", ["performs_in_chat", "registered"])
def test_a_human_on_the_record_that_becomes_an_agent_of_the_system_is_checked_by_the_validator(tmp_path, later):
    """Monotone, the safe way: once the name works in a chat or is registered, the work is an agent's, and the validator
    checks it by default — his bare PASS no longer closes it."""
    e, _ = _issued(tmp_path, checker=None, holder=HUMAN)
    if later == "performs_in_chat":
        e.performs_in_chat(HUMAN)
    else:
        e.workforce.publish_roster({**e.workforce.roster(), HUMAN: "llm-executor"})
    assert V.his_check(e.graph, e.graph.get_task(TaskId(SEAM))) == "validator" and e.persons_seam(SEAM)
    _delivers(e, holder=HUMAN)
    assert not _call(PAGE, "signal", e, SEAM, "PASS", "user").get("accepted")


def test_a_human_on_the_record_stays_one_where_no_roster_is_published_now(tmp_path):
    e, _ = _issued(tmp_path, checker=None, holder=HUMAN)
    e.graph.roster = None
    assert V.his_check(e.graph, e.graph.get_task(TaskId(SEAM))) == "self" and not e.persons_seam(SEAM)
    _delivers(e, holder=HUMAN)
    assert _call(PAGE, "signal", e, SEAM, "PASS", "user")["state"] == "DONE"


def test_a_node_issued_before_records_were_kept_is_classified_once_at_its_first_read(tmp_path):
    """A human's node issued before who executes it was recorded: its first read classifies it from the roster as it
    stands and writes the record, and his bare PASS closes it."""
    e, _ = _issued(tmp_path, checker=None, holder=HUMAN)
    e._storage.store_critique(V.executes_key(SEAM), "[]")          # …as a node handed over before this record
    assert V.his_check(e.graph, e.graph.get_task(TaskId(SEAM))) == "self"
    assert json.loads(e._storage.get_critique(V.executes_key(SEAM))) == [{"assignee": HUMAN, "human": True}]
    _delivers(e, holder=HUMAN)
    assert _call(PAGE, "signal", e, SEAM, "PASS", "user")["state"] == "DONE"


def test_a_human_that_became_an_agent_stays_one_after_it_is_unregistered(tmp_path):
    """The switch to an agent is recorded when read: an agent's session delivered, its name unregistered after, and the
    validator still checks it."""
    e, _ = _issued(tmp_path, checker=None, holder=HUMAN)
    roster = e.workforce.roster()
    e.workforce.publish_roster({**roster, HUMAN: "llm-executor"})
    assert V.his_check(e.graph, e.graph.get_task(TaskId(SEAM))) == "validator"
    _delivers(e, holder=HUMAN)
    e.workforce.publish_roster(roster)
    assert V.his_check(e.graph, e.graph.get_task(TaskId(SEAM))) == "validator" and e.persons_seam(SEAM)
    assert not _call(PAGE, "signal", e, SEAM, "PASS", "user").get("accepted")


def test_a_node_from_before_the_record_that_an_agent_worked_reads_as_an_agents(tmp_path):
    """No record, its executor since dropped from the roster: a session of the system's on its ledger shows an agent
    worked it, so the validator checks it."""
    e, _ = _issued(tmp_path, mode=Mode.SEMI, checker=None)
    _delivers(e)
    e._storage.log_usage({"ts": "2026-11-20T10:00:00", "stage": "executor", "model": "m", "node_id": SEAM})
    e._storage.store_critique(V.executes_key(SEAM), "[]")          # …as a node handed over before this record
    e.workforce.publish_roster({k: v for k, v in e.workforce.roster().items() if k != HOLDER})
    assert V.his_check(e.graph, e.graph.get_task(TaskId(SEAM))) == "validator" and e.persons_seam(SEAM)
    assert not _call(PAGE, "signal", e, SEAM, "PASS", "user").get("accepted")


def test_a_node_handed_over_with_no_roster_is_an_agents_for_good(tmp_path):
    """Before a roster is published nobody is a human: the ASSIGN records an agent, and a roster published after its
    delivery, the name not on it, turns no validator off."""
    e, _ = _issued(tmp_path, staffed=False, checker=None, holder="ext")
    assert e.graph.roster is None
    e.workforce.publish_roster({"p-val": "llm-validator"})
    assert V.his_check(e.graph, e.graph.get_task(TaskId(SEAM))) == "validator"
    _delivers(e, holder="ext")
    assert not _call(PAGE, "signal", e, SEAM, "PASS", "user").get("accepted")


@pytest.mark.parametrize("first, then", [(HUMAN, "exec-1"), ("exec-1", HUMAN)])
def test_a_reassign_hands_the_words_criterion_with_the_check_to_the_new_del(tmp_path, first, then):
    """One classification, at each hand-over: the words criterion is there iff the Del is an agent of the system, as the
    checker is the validator — a re-ASSIGN is a new version, its criteria re-consented (§12.3)."""
    a_repository(tmp_path)
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.workforce.publish_roster({"exec-1": "llm-executor"})
    _call(PAGE, "create_task", e, "root", {"description": "his goal", "criteria": [criterion("g")]}, assignee="user")
    _call(PAGE, "decompose", e, "root", [{"task_id": SEAM, "assignee": first, "covers": ["g"],
                                          "spec": {"description": "a direction", "criteria": [criterion("k")]}}],
          accepted_risks=REGISTER)
    e.wait_idle()
    assert not _call(PAGE, "reassign", e, SEAM, then).get("refused")
    e.wait_idle()
    t = e.graph.get_task(TaskId(SEAM))
    words = INTENT in {c.name for c in t.spec.criteria}
    assert str(t.assignee) == then and words == (then == "exec-1"), [c.name for c in t.spec.criteria]
    assert V.his_check(e.graph, t) == ("validator" if then == "exec-1" else "self")
    assert not [p for c in t.spec.criteria for p in c.check if "git" in p.command] or then == "exec-1"


def test_with_no_roster_a_read_records_nothing_and_takes_no_one_for_a_human(tmp_path):
    e, _ = _issued(tmp_path, checker=None, holder=HUMAN)
    e._storage.store_critique(V.executes_key(SEAM), "[]")
    e.graph.roster = None
    assert V.his_check(e.graph, e.graph.get_task(TaskId(SEAM))) == "validator"
    assert e._storage.get_critique(V.executes_key(SEAM)) == "[]"


def test_an_agent_of_the_system_unregistered_after_its_delivery_is_still_checked_by_the_validator(tmp_path):
    e, _ = _issued(tmp_path, mode=Mode.SEMI, checker=None)
    _delivers(e)
    e.workforce.publish_roster({k: v for k, v in e.workforce.roster().items() if k != HOLDER})
    assert e.persons_seam(SEAM)
    assert not _call(PAGE, "signal", e, SEAM, "PASS", "user").get("accepted")


def test_he_turns_the_validator_off_at_his_seam_and_on_again(tmp_path):
    """Who checks is his appointment at a seam too (the author, 2026-11-23: «издатель назначает валидатора и точка»):
    the default between him and an agent in its chat is the validator, and his word changes it either way."""
    e, _ = _issued(tmp_path, checker=None, in_chat=True)
    assert not _call(PAGE, "set_checker", e, SEAM, "self", agent="user").get("refused")
    assert not e.persons_seam(SEAM) and V.owed_observer(e.graph, e.graph.get_task(TaskId(SEAM))) is None
    assert not _call(PAGE, "set_checker", e, SEAM, "validator", agent="user").get("refused")
    assert [m["checker"] for m in e.checker_choices(TaskId(SEAM))] == ["self", "validator"]
    assert e.persons_seam(SEAM) and e.checker(TaskId(SEAM)) == "validator"
    off = _call(CONSOLE, "set_checker", e, SEAM, "self", user_said="сам", agent=HOLDER)
    assert off.get("refused") and "not the issuer" in off["error"], "its executor appoints nothing"


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
    before = VAL._before_its_delivery(e, SEAM, str(repo), None)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD", "HEAD^{tree}"], capture_output=True,
                          text=True).stdout.split()
    assert (before["commit"], before["tree"]) == tuple(head), before
    with e.judging_before_delivery(SEAM, before["tree"], before["commit"]):
        assert e.delivered(TaskId(SEAM))[:2] == (before["tree"], before["commit"])
        instrument_passes(e, TaskId(SEAM), validator="p-val")
    assert e.delivered(TaskId(SEAM)) is None and _state(e) == "EXECUTING"
    assert e.current_exec_verdict(TaskId(SEAM))["tree"] == before["tree"]
    (tmp_path / "bare").mkdir()
    assert "not the top of a git repository" in VAL._before_its_delivery(e, SEAM, str(tmp_path / "bare"), None)["error"]


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


# ── 5. a FAIL forces rework: the tree it names is not handed in again, his FAIL included ───────────────────────────

def _passed_then_he_fails(e, validator_fails: bool):
    _checked(e, "tree-1")
    assert _delivers(e, "tree-1").get("accepted")
    _fails(e) if validator_fails else instrument_passes(e, TaskId(SEAM), validator="p-val")
    assert _call(PAGE, "signal", e, SEAM, "FAIL", "user", failed_criteria=["d"])["state"] == "REWORKING"


def test_the_tree_his_own_fail_named_is_not_handed_in_again(tmp_path):
    """The validator passed the tree, he read it and FAILed it: his FAIL is a verdict on that tree, rework is owed."""
    e, _ = _issued(tmp_path)
    _passed_then_he_fails(e, validator_fails=False)
    again = _delivers(e, "tree-1")
    assert not again.get("accepted") and "FAIL" in again["error"], again
    _checked(e, "tree-2")
    assert _delivers(e, "tree-2").get("accepted")


def test_a_fresh_pass_of_the_failed_tree_does_not_lift_the_fail(tmp_path):
    """Past the validator's FAIL and his, a new passing check of the unchanged tree is no rework."""
    e, _ = _issued(tmp_path)
    _passed_then_he_fails(e, validator_fails=True)
    with contextlib.suppress(ValueError):           # …the record itself refused: the FAIL stands (Inv-2)
        _checked(e, "tree-1")
    again = _delivers(e, "tree-1")
    assert not again.get("accepted") and "FAIL" in again["error"], again


def test_the_holders_next_step_at_his_seam_is_the_check_before_the_delivery(tmp_path):
    e, _ = _issued(tmp_path)
    _passed_then_he_fails(e, validator_fails=True)
    with _as(CONSOLE):
        steps = [s for s in T.next_steps(e)["steps"] if s.get("task_id") == SEAM]
    assert steps and all("validate_result" in s["directive"] for s in steps), steps


# ── 6. a refused report is about the tree it was made on ───────────────────────────────────────────────────────────

def _refused_twice(e, tree):
    entries = [{"criterion": c.name, "verdict": "pass", "evidence": f"ran the check for `{c.name}`: it holds",
                "behaviours": [p.behaviour for p in c.check],
                "probe": [{"behaviour": p.behaviour, "command": p.command, "expect": p.expect} for p in c.check]}
               for c in e.graph.get_task(TaskId(SEAM)).spec.criteria][:1]
    with e.judging_before_delivery(SEAM, tree, f"c-{tree}"):
        for _ in range(2):
            e.record_rejected_report(TaskId(SEAM), "could not decide d", entries)
        assert e.refusals_on_this_delivery(TaskId(SEAM)) == 2
        assert e.reusable_from_refused(TaskId(SEAM)), "the entry is reusable on its own tree"


def test_two_refused_reports_on_one_tree_leave_a_repaired_tree_checkable(tmp_path):
    """§12.16 (ii): the holder lifts the refusal by his own move — a new tree is a new thing to check."""
    e, _ = _issued(tmp_path)
    _refused_twice(e, "tree-1")
    with e.judging_before_delivery(SEAM, "tree-2", "c-tree-2"):
        assert e.refusals_on_this_delivery(TaskId(SEAM)) == 0
        with _as(CONSOLE):
            assert VAL._refuse_validation(e, SEAM, "the tree", str(tmp_path), object(), None)[0] is None


def test_the_third_run_refused_on_one_tree_names_the_holders_lift_not_validating(tmp_path):
    e, _ = _issued(tmp_path)
    _refused_twice(e, "tree-1")
    with e.judging_before_delivery(SEAM, "tree-1", "c-tree-1"), _as(CONSOLE):
        stop = VAL._refuse_validation(e, SEAM, "the tree", str(tmp_path), object(), None)[0]
    said = stop and stop["error"]
    assert said and "VALIDATING" not in said and "changed tree" not in said, stop
    assert said.index("CHALLENGE") < said.index("a repair of what failed"), said


def test_a_check_of_a_new_tree_reuses_nothing_from_a_report_on_another(tmp_path):
    """A check of tree-2 stands on tree-2 alone: entries of a refused report on tree-1 are not its."""
    e, _ = _issued(tmp_path)
    _refused_twice(e, "tree-1")
    with e.judging_before_delivery(SEAM, "tree-2", "c-tree-2"):
        crits, kept = VAL._left_to_validate(e, e.graph.get_task(TaskId(SEAM)))
    assert not kept and len(crits) == len(e.graph.get_task(TaskId(SEAM)).spec.criteria)


# ── 7. a check stands on the delivery it observed; his FAIL's why reaches the next check; no delivery mid-check ────

def test_a_delivery_recording_no_tree_is_observed_only_by_a_check_made_after_it(tmp_path):
    """A check of a committed tree before the delivery is no observation of a delivery that recorded no tree."""
    e, _ = _issued(tmp_path)
    _checked(e, "tree-X")
    assert _delivers(e).get("accepted")
    assert not _call(PAGE, "signal", e, SEAM, "PASS", "user").get("accepted")
    instrument_passes(e, TaskId(SEAM), validator="p-val")
    assert _call(PAGE, "signal", e, SEAM, "PASS", "user")["state"] == "DONE"


def test_his_fail_and_its_words_reach_the_next_check_and_the_rework(tmp_path):
    """The validator passed the tree and he FAILed it: why he did is what the repair and its check must decide."""
    e, _ = _issued(tmp_path)
    _checked(e, "tree-1")
    _delivers(e, "tree-1")
    instrument_passes(e, TaskId(SEAM), validator="p-val")
    why = "the second page still prints the old totals"
    assert _call(PAGE, "signal", e, SEAM, "FAIL", "user", failed_criteria=["d"], reason=why)["state"] == "REWORKING"
    t = e.graph.get_task(TaskId(SEAM))
    assert why in P._validator_packet(e, t, "the tree", str(tmp_path))
    assert why in P._rework_section(e, t)
    with _as(CONSOLE):
        steps = [s for s in T.next_steps(e)["steps"] if s.get("task_id") == SEAM]
    assert steps and all(why in s["directive"] for s in steps), steps


def test_no_delivery_lands_while_a_check_before_it_runs(tmp_path):
    e, _ = _issued(tmp_path)
    _checked(e, "tree-1")
    with e.judging_before_delivery(SEAM, "tree-2", "c-tree-2"):
        out = _delivers(e, "tree-1")
    assert not out.get("accepted") and "running now" in out["error"], out
    assert _delivers(e, "tree-1").get("accepted")


# ── 8. which check stands for a tree: one owner (`validation.standing_check`) ─────────────────────────────────────

def _entries(e):
    """A passing report's entries over every criterion of the seam, each with its pinned probe and behaviours."""
    return [{"criterion": c.name, "verdict": "pass", "evidence": f"ran the check for `{c.name}`: it holds",
             "behaviours": [p.behaviour for p in c.check],
             "probe": [{"behaviour": p.behaviour, "command": p.command, "expect": p.expect} for p in c.check]}
            for c in e.graph.get_task(TaskId(SEAM)).spec.criteria]


def test_of_two_checks_of_one_tree_with_no_signal_between_the_fail_decides(tmp_path):
    """Two checks with no signal between them stand at one place in the log: their order is the ledger's."""
    e, _ = _issued(tmp_path)
    _checked(e, "tree-1")
    _checked(e, "tree-1", passes=False)
    out = _delivers(e, "tree-1")
    assert not out.get("accepted") and "failed on d" in out["error"], out


def test_a_run_of_an_earlier_round_landing_during_a_check_of_another_tree_is_no_check_of_it(tmp_path):
    e, _ = _issued(tmp_path)
    _checked(e, "tree-1")
    _delivers(e, "tree-1")
    stale = e.graph.generation_of(TaskId(SEAM))
    _fails(e)
    assert _call(PAGE, "signal", e, SEAM, "FAIL", "user", failed_criteria=["d"])["state"] == "REWORKING"
    with e.judging_before_delivery(SEAM, "tree-2", "c-tree-2"), pytest.raises(V.StaleRun):
        instrument_passes(e, TaskId(SEAM), validator="p-val", generation=stale)
    out = _delivers(e, "tree-2")
    assert not out.get("accepted") and "has not checked this tree" in out["error"], out


def test_a_check_of_an_earlier_round_does_not_stand_for_the_tree_in_this_one(tmp_path):
    """A check stands for the round its run was claimed in: past a FAIL, the tree is checked again."""
    e, _ = _issued(tmp_path)
    _checked(e, "tree-2")
    _checked(e, "tree-1")
    _delivers(e, "tree-1")
    _fails(e)
    assert _call(PAGE, "signal", e, SEAM, "FAIL", "user", failed_criteria=["d"])["state"] == "REWORKING"
    out = _delivers(e, "tree-2")
    assert not out.get("accepted") and "has not checked this tree" in out["error"], out


def test_a_seam_is_its_parents_holders_and_moves_with_him(tmp_path):
    """One reading of the issuer: Del(parent), the role moving at its change (§10.1). His root handed to bob, the seam
    under it is bob's: no longer the person's, nor his to appoint its checker — and nobody's under no mode, where no PASS
    waits for a chosen validator."""
    e, _ = _issued(tmp_path, checker=None)
    e._storage.update_task(TaskId("root"), assignee="bob")
    t = e.graph.get_task(TaskId(SEAM))
    assert not e.persons_seam(SEAM) and V.his_check(e.graph, t) is None
    mine = _call(PAGE, "set_checker", e, SEAM, "validator", agent="user")
    assert mine.get("refused") and "'bob'" in mine["error"], mine
    for checker in ("self", "validator"):
        bobs = TL.set_checker(e, SEAM, checker, user_said="так", agent="bob")
        assert bobs.get("refused") and "under a mode" in bobs["error"], bobs
    assert not e.checker_choices(TaskId(SEAM))


def test_under_semi_his_agent_lifts_no_validator_and_signs_no_bare_pass(tmp_path):
    """His chat connection signs as his name: a node it gives a registered executor is checked by the validator, and
    from that connection neither `set_checker('self')` nor a PASS stands for his act — only his page does."""
    e, _ = _issued(tmp_path, mode=Mode.SEMI, checker=None)
    assert e.persons_seam(SEAM)
    off = _call(STANDING, "set_checker", e, SEAM, "self", user_said="сам", agent="user")
    assert off.get("refused") and "page" in off["error"], off
    assert not e.checker_choices(TaskId(SEAM))
    _delivers(e)
    assert not _call(STANDING, "signal", e, SEAM, "PASS", "user").get("accepted")
    assert _state(e) == "VALIDATING"


def test_his_own_check_is_his_act_and_a_bare_pass_by_his_name_is_not(tmp_path):
    """Where he keeps the check himself his PASS counts only as his act: his page, or his words."""
    e, _ = _issued(tmp_path, checker=None, holder=HUMAN)
    assert V.his_check(e.graph, e.graph.get_task(TaskId(SEAM))) == "self"
    _delivers(e, holder=HUMAN)
    bare = _call(STANDING, "signal", e, SEAM, "PASS", "user")
    assert not bare.get("accepted") and "user_said" in bare["error"], bare
    assert _call(STANDING, "signal", e, SEAM, "PASS", "user", user_said="принимаю")["state"] == "DONE"


def test_a_runs_record_names_the_tree_its_claim_named_when_it_began(tmp_path):
    """The place moved under a run (a check before the next delivery began): its record is of what it read."""
    e, _ = _issued(tmp_path)
    _checked(e, "tree-1")
    _delivers(e, "tree-1")
    claim = e.claims.begin_validation(TaskId(SEAM), tree="tree-1")
    with e.judging_before_delivery(SEAM, "tree-2", "c-tree-2"):
        VAL._record_node(e, e.graph.get_task(TaskId(SEAM)), _entries(e), {}, "p-val", object(), claim, None,
                        str(tmp_path), None)
    e.claims.end_validation(claim)
    assert e.current_exec_verdict(TaskId(SEAM))["tree"] == "tree-1"


def test_a_mode_set_after_his_seam_was_issued_leaves_it_his(tmp_path):
    """His seam is his by who issued it, not by the mode now."""
    e, _ = _issued(tmp_path)
    e.set_mode(Mode.SEMI, None, AgentId("user"))
    assert not _delivers(e, "tree-1").get("accepted")
    _checked(e, "tree-1")
    assert _delivers(e, "tree-1").get("accepted")
    _fails(e)
    assert not _call(PAGE, "signal", e, SEAM, "PASS", "user").get("accepted")


def test_under_semi_a_node_he_issues_below_his_root_is_his_seam(tmp_path):
    """Every seam he issues, at any depth: past the validator's FAIL his own hand does not turn it into a pass."""
    e, _ = _issued(tmp_path, mode=Mode.SEMI)
    assert e.persons_seam(SEAM) and e.checker(TaskId(SEAM)) == "validator"
    assert INTENT in {c.name for c in e.graph.get_task(TaskId(SEAM)).spec.criteria}, "his words, as at every seam of his"
    assert _delivers(e).get("accepted")
    _fails(e)
    with contextlib.suppress(ValueError):
        instrument_passes(e, TaskId(SEAM), validator="user", by_hand=True)
    assert not _call(PAGE, "signal", e, SEAM, "PASS", "user").get("accepted")
    assert _state(e) == "VALIDATING"


def test_a_validator_registered_where_no_commit_records_a_tree_is_told_his_seams_cannot_force_rework(tmp_path):
    """In a repository with no commit, no delivery records a tree; below a work tree's top it records the top's commit
    and its judge stands there (`judged_at`); a directory with no git at all is refused, with its lift."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.project_name = "p"
    (plain := tmp_path / "plain").mkdir()
    assert "git init" in TL.register_agent(e, "p-val", "llm-validator", workdir=str(plain)).get("error", "")
    (bare := tmp_path / "nocommit").mkdir()
    subprocess.run(["git", "-C", str(bare), "init", "-q"], check=True)
    out = TL.register_agent(e, "p-val2", "llm-validator", workdir=str(bare))
    ensure_dispatcher(e).stop()
    assert "no git repository with a commit" in str(out.get("seam_boundary")), out
    repo = a_repository(tmp_path / "repo")
    (sub := repo / "sub").mkdir()
    assert "seam_boundary" not in TL.register_agent(e, "p-val3", "llm-validator", workdir=str(sub))
    assert "seam_boundary" not in TL.register_agent(e, "p-val4", "llm-validator", workdir=str(repo))


# ── 9. who checks is his appointment: himself by default, the validator in his chat ───────────────────────────────

def _his_own_check(e, tid=SEAM):
    """His reading of the delivery, recorded by his hand: the check he makes as its issuer (§10.2)."""
    return T.record_verdict(e, tid, "PASS", reviewer="user", observed={
        c.name: {"note": f"checked `{c.name}` by hand against what was handed in: it holds",
                 "ran": [p.command for p in c.check]}
        for c in e.graph.get_task(TaskId(tid)).spec.criteria})


def test_a_node_he_issues_to_a_human_is_checked_by_him_and_his_pass_needs_no_validator(tmp_path):
    e, _ = _issued(tmp_path, checker=None, holder=HUMAN)
    assert not e.persons_seam(SEAM) and V.owed_observer(e.graph, e.graph.get_task(TaskId(SEAM))) is None
    assert "staff" not in _delivers(e, holder=HUMAN)
    # …his bare PASS: check and signature both his, one person's (§10.2)
    assert _call(PAGE, "signal", e, SEAM, "PASS", "user")["state"] == "DONE"
    assert not [r for r in observations(e._storage, TaskId(SEAM)) if r.get("validator") == "p-val"]


def test_a_humans_node_he_fails_goes_to_rework_on_his_criteria(tmp_path):
    e, _ = _issued(tmp_path, checker=None, holder=HUMAN)
    _delivers(e, holder=HUMAN)
    assert _call(PAGE, "signal", e, SEAM, "FAIL", "user", failed_criteria=["d"])["state"] == "REWORKING"


def test_a_registered_role_he_issues_to_is_checked_by_the_validator_by_default(tmp_path):
    """Any agent of the system — his own in his chat, a registered role — is checked by the system's validator unless he
    appoints himself; a semi delivery does not wait on his hand."""
    e, _ = _issued(tmp_path, mode=Mode.SEMI, checker=None)
    assert e.persons_seam(SEAM) and e.checker(TaskId(SEAM)) == "validator"
    assert not _call(PAGE, "set_checker", e, SEAM, "self", agent="user").get("refused")
    assert not e.persons_seam(SEAM)


def test_a_validator_he_appoints_on_a_humans_node_is_owed_before_his_pass(tmp_path):
    e, _ = _issued(tmp_path, holder=HUMAN)
    assert e.persons_seam(SEAM) and e.checker(TaskId(SEAM)) == "validator"
    assert _delivers(e, holder=HUMAN).get("accepted")
    with contextlib.suppress(ValueError):
        _his_own_check(e)
    out = _call(PAGE, "signal", e, SEAM, "PASS", "user")
    assert not out.get("accepted") and "observ" in out["error"], out
    instrument_passes(e, TaskId(SEAM), validator="p-val")
    assert _call(PAGE, "signal", e, SEAM, "PASS", "user")["state"] == "DONE"


def test_a_humans_node_carries_no_pin_reading_this_repositorys_git(tmp_path):
    """Its work is met in meetings and other repositories: a pin over this `git log` decides nothing of it."""
    e, _ = _issued(tmp_path, checker=None, holder=HUMAN)
    crits = e.graph.get_task(TaskId(SEAM)).spec.criteria
    assert INTENT not in {c.name for c in crits}
    assert not [p for c in crits for p in c.check if "git" in p.command], crits


def _solo_root_delivered(mode=Mode.SOLO):
    """His own root under `mode`, held and worked by his agent in his chat, delivered."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.set_mode(mode, None, AgentId("user"))
    T.create_task(e, "root", {"description": "his goal", "criteria": [criterion("g")]})
    T.signal(e, "root", "ACCEPT", "user")
    T.signal(e, "root", "DELIVER", "user", result="ran g: it holds", self_validation="PASS")
    e.wait_idle()
    return e


def test_between_him_and_his_agent_in_his_chat_the_validator_checks_by_default():
    e = _solo_root_delivered()
    assert V.his_check(e.graph, e.graph.get_task(TaskId("root"))) == "validator"
    out = _call(PAGE, "signal", e, "root", "PASS", "user")
    assert not out.get("accepted") and "observ" in out["error"], out
    e.stop()


@pytest.mark.parametrize("mode", [Mode.SOLO, Mode.SEMI])
def test_between_him_and_his_agent_in_his_chat_his_own_check_suffices_where_he_appoints_himself_on_his_page(mode):
    """His agent signs as his name there: lifting the validator from its connection would be the executor choosing its
    own checker (§10.3), so it is his hand alone — his page; the validator back is admitted from anywhere."""
    e = _solo_root_delivered(mode)
    off = _call(STANDING, "set_checker", e, "root", "self", user_said="сам проверю", agent="user")
    assert off.get("refused") and "page" in off["error"], off
    assert not e.checker_choices(TaskId("root")), "a refused choice wrote it"
    if mode == Mode.SOLO:     # …under semi his root waits for its split before any delivery
        assert not _call(PAGE, "signal", e, "root", "PASS", "user").get("accepted")
    assert not _call(STANDING, "set_checker", e, "root", "validator", user_said="проверяй", agent="user").get("refused")
    assert not _call(PAGE, "set_checker", e, "root", "self", agent="user").get("refused")
    assert V.his_check(e.graph, e.graph.get_task(TaskId("root"))) == "self"
    if mode == Mode.SOLO:
        assert _call(PAGE, "signal", e, "root", "PASS", "user")["state"] == "DONE"
    e.stop()


