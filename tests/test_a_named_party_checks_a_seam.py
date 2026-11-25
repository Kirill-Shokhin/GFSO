"""A seam the person issues is checked by a party he names (the author, 2026-11-24: «надо понимать кто проверяющий еще
до проверки то. и уметь его назначать через интерфейс — для общего случая»). Validating is two acts (§10.2): the check,
anyone the issuer appoints, and the signature, his. At a seam the check is not the executor's (§10.3). So he may name any
party of the project — never the executor —, who checks is said before any check, his PASS waits on that party's PASS
record, its FAIL binds (Inv-2), anyone else's record stands beside it, and the validator does not observe it by itself."""
from __future__ import annotations

import contextlib

import pytest

import gfso.tools as T
import gfso.tools_llm as TL
from gfso.config import CALLER, Principal
from gfso.core.types import AgentId, Mode, TaskId
from gfso.delegate import Dispatcher, ensure_dispatcher
from gfso.engine import validation as V
from gfso.core.graph.metrics import pass_stands_refuted, pass_was_refuted, q_V_reversed
from gfso.engine.verdicts import CLOSING, ledger_read, observations, refuted_versions
from gfso.roster import AgentRegistry
from gfso.signin import PAGE
from tests.support import REGISTER, a_repository, criterion, instrument_passes, make_engine

SEAM, HOLDER, CHECKER, OTHER, ROLE = "root.eng", "engineering", "rev", "ann", "exec-2"
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


def _issued(tmp_path, checker=CHECKER):
    """His root, a seam he issues from his page to `engineering`, the project's validator registered and two more parties
    on its roster; `checker` his appointment from his page (None: none)."""
    a_repository(tmp_path)
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    assert not TL.register_agent(e, "p-val", "llm-validator", workdir=str(tmp_path)).get("refused")
    ensure_dispatcher(e).stop()
    e.workforce.publish_roster({**e.workforce.roster(), HOLDER: "llm-executor", ROLE: "llm-executor",
                                CHECKER: "external", OTHER: "external"})
    _call(PAGE, "create_task", e, "root", {"description": "his goal", "criteria": [criterion("g")]}, assignee="user")
    covers = [c.name for c in e.graph.get_task(TaskId("root")).spec.criteria]
    _call(PAGE, "decompose", e, "root", [{"task_id": SEAM, "assignee": HOLDER, "covers": covers,
                                          "spec": {"description": "a direction", "criteria": [criterion("d")]}}],
          accepted_risks=REGISTER)
    e.wait_idle()
    if checker is not None:
        out = _call(PAGE, "set_checker", e, SEAM, checker, agent="user")
        assert out.get("checker") == checker, out
    T.signal(e, SEAM, "ACCEPT", HOLDER)
    return e


def _delivered(tmp_path):
    e = _issued(tmp_path)
    assert T.signal(e, SEAM, "DELIVER", HOLDER, result="it holds", self_validation="PASS").get("accepted")
    e.wait_idle()
    assert e.graph.get_state(TaskId(SEAM)).name == "VALIDATING"
    return e


def _record(e, who, verdict="PASS"):
    """`who`'s verdict on the delivery, recorded by its own hand: what it ran per criterion."""
    crits = e.graph.get_task(TaskId(SEAM)).spec.criteria
    return T.record_verdict(e, SEAM, verdict, reviewer=who, failed_criteria=["d"] if verdict == "FAIL" else None,
                            observed={c.name: {"note": f"ran the check for `{c.name}`: it printed "
                                                       + ("NO" if verdict == "FAIL" and c.name == "d" else "OK"),
                                               "ran": [p.command for p in c.check]} for c in crits})


def _his_pass(e):
    return _call(PAGE, "signal", e, SEAM, "PASS", "user")


def test_a_named_checker_is_said_before_any_check(tmp_path):
    e = _issued(tmp_path)
    assert V.his_check(e.graph, e.graph.get_task(TaskId(SEAM))) == CHECKER
    assert e.checker(TaskId(SEAM)) == CHECKER
    with _as(PAGE):
        assert T.get_task(e, SEAM)["checker"] == CHECKER
    assert not observations(e._storage, TaskId(SEAM))


def test_no_record_of_the_named_checker_blocks_his_pass(tmp_path):
    e = _delivered(tmp_path)
    out = _his_pass(e)
    assert not out.get("accepted") and CHECKER in out["error"], out
    assert e.graph.get_state(TaskId(SEAM)).name == "VALIDATING"


def test_the_named_checkers_pass_record_unlocks_his_pass(tmp_path):
    e = _delivered(tmp_path)
    assert (out := _record(e, CHECKER))["recorded"], out
    assert _his_pass(e)["state"] == "DONE"


def test_the_named_checkers_fail_binds(tmp_path):
    e = _delivered(tmp_path)
    assert _record(e, CHECKER, "FAIL")["recorded"]
    with contextlib.suppress(ValueError):
        instrument_passes(e, TaskId(SEAM), validator="p-val")
    _record(e, "user")                                  # …his own hand: beside it, it lifts nothing
    assert _record(e, CHECKER).get("recorded") is False, "its own later PASS does not undo its FAIL"
    out = _his_pass(e)
    assert not out.get("accepted") and CHECKER in out["error"], out
    assert _call(PAGE, "signal", e, SEAM, "FAIL", "user", failed_criteria=["d"])["state"] == "REWORKING"


@pytest.mark.parametrize("other", [OTHER, "p-val", "user"])
def test_another_partys_record_does_not_unlock_his_pass(tmp_path, other):
    e = _delivered(tmp_path)
    if other == "p-val":
        instrument_passes(e, TaskId(SEAM), validator="p-val")       # …a validate_result run: evidence
    else:
        assert _record(e, other)["recorded"]
    assert not _his_pass(e).get("accepted")
    assert e.graph.get_state(TaskId(SEAM)).name == "VALIDATING"


@pytest.mark.parametrize("name, says", [(HOLDER, "§10.3"), ("system", "system party"), ("liveness", "liveness watch")])
def test_the_executor_and_the_systems_names_are_refused_as_checker(tmp_path, name, says):
    e = _issued(tmp_path, checker=None)
    out = _call(PAGE, "set_checker", e, SEAM, name, agent="user")
    assert out.get("refused") and says in out["error"], out
    assert not e.checker_choices(TaskId(SEAM)), "a refused choice wrote it"


def test_the_validator_does_not_observe_a_named_checkers_node_by_itself(tmp_path):
    e = _delivered(tmp_path)
    t = e.graph.get_task(TaskId(SEAM))
    assert V.owed_observer(e.graph, t) is None and not e.observed_here(t.id) and not e.observes_by_itself(t.id)
    assert not Dispatcher(e, AgentRegistry(path=str(tmp_path / "agents.json")))._validate_here(t)
    assert not e.persons_seam(SEAM)


def test_checker_choices_list_the_eligible_names_to_the_issuer_alone(tmp_path):
    e = _issued(tmp_path, checker=None)
    with _as(PAGE):
        offered = T.get_task(e, SEAM)["checker_choices"]
    assert offered[:2] == ["validator", "self"] and {CHECKER, OTHER} <= set(offered), offered
    assert not {HOLDER, "user", "agent", "system", "liveness", "p-val", ROLE} & set(offered), offered
    with _as(CONSOLE):
        assert "checker_choices" not in T.get_task(e, SEAM), "the executor appoints nothing"


def test_the_named_checkers_move_is_on_its_frontier_and_his_step_names_the_wait(tmp_path):
    e = _delivered(tmp_path)
    theirs = [s for s in T.next_steps(e, actor=CHECKER)["steps"] if s.get("task_id") == SEAM]
    assert theirs and all(s["mine"] and "record_verdict" in s["directive"] for s in theirs), theirs
    his = [s for s in T.next_steps(e, actor="user")["steps"] if s.get("task_id") == SEAM]
    assert his and all(CHECKER in s["directive"] for s in his), his
    _record(e, CHECKER)
    assert not [s for s in T.next_steps(e, actor=CHECKER)["steps"] if s.get("task_id") == SEAM and s["mine"]]


# ── who may be named: a party that makes its own moves ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("role", ["p-val", ROLE])
def test_a_role_of_the_system_nothing_drives_to_check_is_refused(tmp_path, role):
    """Named, a registered role would never record a verdict (nothing drives it to), and the validator named by its own
    name would switch its own run off: the node would wait for ever."""
    e = _issued(tmp_path, checker=None)
    out = _call(PAGE, "set_checker", e, SEAM, role, agent="user")
    assert out.get("refused") and "a role of the system" in out["error"] and "`validator`" in out["error"], out


def test_a_human_outside_the_system_and_a_name_in_a_chat_are_admitted(tmp_path):
    e = _issued(tmp_path, checker=None)
    e.performs_in_chat("chatty")
    with _as(PAGE):
        assert "chatty" in T.get_task(e, SEAM)["checker_choices"]
    for name in ("yana", "chatty"):              # …yana on no roster, in no chat: a human (`a_human`)
        out = _call(PAGE, "set_checker", e, SEAM, name, agent="user")
        assert out.get("checker") == name, out
        assert e.checker(TaskId(SEAM)) == name


# ── its gate is the one gate; its FAIL is not shopped away; a reassign lapses it ──────────────────────────────────

def test_after_the_named_pass_anyone_elses_later_fail_does_not_hold_his_pass(tmp_path):
    e = _delivered(tmp_path)
    _record(e, CHECKER)
    _record(e, OTHER, "FAIL")
    e.record_exec_verdict(TaskId(SEAM), "FAIL", ["d"], "p-val", per_criterion=[
        {"criterion": c.name, "verdict": "fail" if c.name == "d" else "pass", "evidence": "ran it: NO"}
        for c in e.graph.get_task(TaskId(SEAM)).spec.criteria])
    assert _his_pass(e)["state"] == "DONE"


@pytest.mark.parametrize("to", [OTHER, "validator", "self"])
def test_a_named_checkers_fail_is_not_lifted_by_appointing_another(tmp_path, to):
    e = _delivered(tmp_path)
    _record(e, CHECKER, "FAIL")
    out = _call(PAGE, "set_checker", e, SEAM, to, agent="user")
    assert out.get("refused") and "FAIL" in out["error"] and "edit_criteria" in out["error"], out
    assert e.named_checker(TaskId(SEAM)) == CHECKER


def test_the_validators_binding_fail_at_his_seam_is_not_lifted_by_appointing_another(tmp_path):
    e = _issued(tmp_path, checker="validator")
    T.signal(e, SEAM, "DELIVER", HOLDER, result="it holds", self_validation="PASS")
    e.wait_idle()
    e.record_exec_verdict(TaskId(SEAM), "FAIL", ["d"], "p-val", per_criterion=[
        {"criterion": c.name, "verdict": "fail" if c.name == "d" else "pass", "evidence": "ran it: NO",
         **({"quote": "his goal"} if c.name != "d" else {})}
        for c in e.graph.get_task(TaskId(SEAM)).spec.criteria])
    for to in (CHECKER, "self"):
        out = _call(PAGE, "set_checker", e, SEAM, to, agent="user")
        assert out.get("refused") and "FAIL" in out["error"], out
    assert not _his_pass(e).get("accepted")


def test_an_appointment_lapses_where_the_named_party_becomes_the_executor(tmp_path):
    e = _issued(tmp_path)
    assert not _call(PAGE, "reassign", e, SEAM, CHECKER).get("refused")
    e.wait_idle()
    assert e.named_checker(TaskId(SEAM)) is None and e.checker(TaskId(SEAM)) != CHECKER
    assert V.his_check(e.graph, e.graph.get_task(TaskId(SEAM))) in ("validator", "self")


def _validator_fails(e):
    e.record_exec_verdict(TaskId(SEAM), "FAIL", ["d"], "p-val", per_criterion=[
        {"criterion": c.name, "verdict": "fail" if c.name == "d" else "pass", "evidence": "ran it: NO",
         **({"quote": "his goal"} if c.name != "d" else {})}
        for c in e.graph.get_task(TaskId(SEAM)).spec.criteria])


# ── what a signature reads is the named party's record; how a name not yet signable comes to sign ────────────────

def test_the_advised_verdict_and_get_verdict_read_the_named_partys_record_others_beside_it(tmp_path):
    e = _delivered(tmp_path)
    _record(e, CHECKER)
    _record(e, OTHER, "FAIL")
    his = [s for s in T.next_steps(e, actor="user")["steps"] if s.get("task_id") == SEAM]
    assert his and all("SIGN THE VERDICT" in s["directive"] and f"by {CHECKER} — PASS" in s["directive"]
                       and f"{OTHER} recorded FAIL" in s["directive"] for s in his), his   # …the one beside, named
    v = T.get_verdict(e, SEAM)
    assert (v["verdict"], v["validator"], v["checker"]) == ("PASS", CHECKER, CHECKER), v
    assert [(o["validator"], o["verdict"]) for o in v["others"]] == [(OTHER, "FAIL")], v


def test_a_named_party_that_cannot_sign_yet_is_told_how_in_the_reply_and_his_step(tmp_path):
    e = _issued(tmp_path, checker=None)
    out = _call(PAGE, "set_checker", e, SEAM, "yana", agent="user")
    assert "`gfso agent yana`" in out["say"], out
    T.signal(e, SEAM, "DELIVER", HOLDER, result="it holds", self_validation="PASS")
    e.wait_idle()
    with _as(PAGE):
        his = [s for s in TL.next_steps(e, actor="user")["steps"] if s.get("task_id") == SEAM]
    assert his and all("`gfso agent yana`" in s["directive"] for s in his), his


def test_a_fail_that_never_bound_does_not_hold_a_new_appointment(tmp_path):
    """Where he checks it himself an instrument's FAIL is evidence beside his check, no appointed checker's: it binds
    neither his PASS nor his next appointment (one answer, `by_the_appointee`)."""
    e = _issued(tmp_path, checker="self")
    T.signal(e, SEAM, "DELIVER", HOLDER, result="it holds", self_validation="PASS")
    e.wait_idle()
    _validator_fails(e)
    out = _call(PAGE, "set_checker", e, SEAM, OTHER, agent="user")
    assert out.get("checker") == OTHER, out


# ── one verdict of record: every reader reads the named party's, others' beside it ────────────────────────────────

def _closed_over_others_fails(tmp_path):
    """The named party PASSed, two others FAILed after it — by hand and by the instrument —, and he signed."""
    e = _delivered(tmp_path)
    _record(e, CHECKER)
    _record(e, OTHER, "FAIL")
    _validator_fails(e)
    assert _his_pass(e)["state"] == "DONE"
    return e


def test_every_reader_reads_the_named_partys_pass_as_the_verdict(tmp_path):
    e = _closed_over_others_fails(tmp_path)
    t, tid = e.graph.get_task(TaskId(SEAM)), TaskId(SEAM)
    for rec in (e.get_exec_verdict(tid), e.current_exec_verdict(tid), e.graph.exec_verdict_record(tid)):
        assert (rec["verdict"], rec["validator"]) == ("PASS", CHECKER), rec
    assert not (e.closure_of(tid) or {}).get("refuted"), e.closure_of(tid)
    assert not pass_was_refuted(e.graph, t) and not pass_stands_refuted(e.graph, t)
    assert SEAM not in q_V_reversed(e.graph)
    v = T.get_verdict(e, SEAM)
    assert (v["verdict"], v["validator"]) == ("PASS", CHECKER) and "contradicts_state" not in v, v
    assert not [s for s in T.next_steps(e, actor="user")["steps"] if "RECOVER" in s.get("directive", "")]
    assert not T.next_steps(e, actor="user").get("refuted_passes")


def test_a_record_after_the_close_still_refutes_and_the_close_keeps_the_named_pass(tmp_path):
    """§15.4: a later fail, measured from the close — a post-hoc check refutes whoever runs it."""
    e = _closed_over_others_fails(tmp_path)
    _validator_fails(e)
    assert ledger_read(e._storage, SEAM, CLOSING)["validator"] == CHECKER
    assert pass_was_refuted(e.graph, e.graph.get_task(TaskId(SEAM)))


def test_a_run_begun_before_the_close_stays_beside_the_named_pass(tmp_path):
    """§15.4's later fail is a check over a COMPLETED node: a run the instrument began while the node was validated, landing
    after his PASS, was a check of the delivery beside the named party's, not a post-hoc one."""
    e = _delivered(tmp_path)
    _record(e, CHECKER)
    began = len(e._audit)
    assert _his_pass(e)["state"] == "DONE"
    e.record_exec_verdict(TaskId(SEAM), "FAIL", ["d"], "p-val", log_at=began, per_criterion=[
        {"criterion": c.name, "verdict": "fail" if c.name == "d" else "pass", "evidence": "ran it: NO",
         **({"quote": "his goal"} if c.name != "d" else {})}
        for c in e.graph.get_task(TaskId(SEAM)).spec.criteria])
    assert e.get_exec_verdict(TaskId(SEAM))["validator"] == CHECKER
    assert not pass_was_refuted(e.graph, e.graph.get_task(TaskId(SEAM)))
    assert [r["validator"] for r in observations(e._storage, TaskId(SEAM))][-1] == "p-val", "kept on the ledger"


def test_a_pass_standing_before_the_appointment_goes_beside_it(tmp_path):
    """Named after another party recorded PASS, the named party's record is still the one his PASS waits on."""
    e = _issued(tmp_path, checker=None)
    T.signal(e, SEAM, "DELIVER", HOLDER, result="it holds", self_validation="PASS")
    e.wait_idle()
    instrument_passes(e, TaskId(SEAM), validator="p-val")
    assert _call(PAGE, "set_checker", e, SEAM, CHECKER, agent="user").get("checker") == CHECKER
    assert e.current_exec_verdict(TaskId(SEAM)) is None
    assert [o["validator"] for o in T.get_verdict(e, SEAM).get("others", [])] == ["p-val"]
    assert not _his_pass(e).get("accepted")
    _record(e, CHECKER)
    assert _his_pass(e)["state"] == "DONE"


def test_appointing_a_party_whose_pass_stands_seats_it_as_the_verdict(tmp_path):
    """Named `rev`, `ann` checked meanwhile, then he appoints `ann`: her standing PASS is the verdict his PASS reads."""
    e = _delivered(tmp_path)
    _record(e, OTHER)
    assert _call(PAGE, "set_checker", e, SEAM, OTHER, agent="user").get("checker") == OTHER
    v = T.get_verdict(e, SEAM)
    assert (v["verdict"], v["validator"]) == ("PASS", OTHER) and not v.get("others"), v
    assert _his_pass(e)["state"] == "DONE"


def test_switching_away_and_back_reseats_the_first_partys_pass(tmp_path):
    e = _delivered(tmp_path)
    _record(e, CHECKER)
    for to in (OTHER, CHECKER):
        assert _call(PAGE, "set_checker", e, SEAM, to, agent="user").get("checker") == to
    assert T.get_verdict(e, SEAM)["validator"] == CHECKER
    assert _his_pass(e)["state"] == "DONE"


def test_a_fail_that_never_bound_leaves_the_verdicts_place_at_an_appointment(tmp_path):
    e = _issued(tmp_path, checker="self")
    T.signal(e, SEAM, "DELIVER", HOLDER, result="it holds", self_validation="PASS")
    e.wait_idle()
    _validator_fails(e)
    assert _call(PAGE, "set_checker", e, SEAM, OTHER, agent="user").get("checker") == OTHER
    v = T.get_verdict(e, SEAM)
    assert v.get("verdict") is None and [o["validator"] for o in v["others"]] == ["p-val"], v
    _record(e, OTHER)
    assert _his_pass(e)["state"] == "DONE"


def test_a_fail_beside_the_named_record_keeps_the_version_it_refuted(tmp_path):
    """claim_drift reads what a FAIL refuted: one standing beside the verdict of record refuted it too."""
    e = _delivered(tmp_path)
    _record(e, OTHER, "FAIL")
    assert "d" in refuted_versions(e._storage, TaskId(SEAM))


def test_before_the_named_record_the_issuers_step_is_a_wait_not_his_move(tmp_path):
    e = _delivered(tmp_path)
    with _as(PAGE):
        out = TL.next_steps(e, actor="user")
    his = [s for s in out["steps"] if s.get("task_id") == SEAM]
    assert his and all(s.get("optional") and not s.get("persons") and f"waits on {CHECKER}'s record" in s["directive"]
                       for s in his), his
    assert TL.needs_its_customer({"steps": his}) is None, "his `gfso wait` does not wake on it"
    _record(e, CHECKER, "FAIL")                    # …its binding FAIL is his move again
    with _as(PAGE):
        his = [s for s in TL.next_steps(e, actor="user")["steps"] if s.get("task_id") == SEAM]
    assert his and all(s["mine"] and not s.get("optional") for s in his), his


def test_what_is_in_flight_at_a_named_node_names_its_checkers_record_not_the_instrument(tmp_path):
    e = _delivered(tmp_path)
    busy = [n for n in e.in_flight_nodes() if n["task_id"] == SEAM]
    assert busy and "record_verdict" in busy[0]["opens_with"] and "validate_result" not in busy[0]["opens_with"], busy


# ── the verdict of record is the appointee's: whoever the appointment names, its record alone takes the place ──────

def _self_checked(tmp_path):
    e = _issued(tmp_path, checker="self")
    T.signal(e, SEAM, "DELIVER", HOLDER, result="it holds", self_validation="PASS")
    e.wait_idle()
    return e


def _not_refuted(e):
    t, tid = e.graph.get_task(TaskId(SEAM)), TaskId(SEAM)
    assert not (e.closure_of(tid) or {}).get("refuted"), e.closure_of(tid)
    assert not pass_was_refuted(e.graph, t) and SEAM not in q_V_reversed(e.graph)


def test_a_fail_recorded_before_a_switch_to_self_is_no_later_fail_of_his_pass(tmp_path):
    e = _delivered(tmp_path)
    _record(e, OTHER, "FAIL")
    assert _call(PAGE, "set_checker", e, SEAM, "self", agent="user").get("checker") == "self"
    assert (e.get_exec_verdict(TaskId(SEAM)) or {}).get("validator") != OTHER
    assert _his_pass(e)["state"] == "DONE"
    _not_refuted(e)


def test_where_he_checks_it_himself_a_passers_by_fail_stands_beside_his_pass(tmp_path):
    e = _self_checked(tmp_path)
    _record(e, OTHER, "FAIL")
    assert _his_pass(e)["state"] == "DONE"
    _not_refuted(e)
    assert [o["validator"] for o in T.get_verdict(e, SEAM).get("others", [])] == [OTHER]


def test_where_he_checks_it_himself_the_instruments_fail_binds_neither_his_pass_nor_his_appointment(tmp_path):
    """§10.2: the check is the one he appoints — himself —, and the instrument's is an implementation's check of its own:
    evidence beside it, not the check's record Inv-2 binds. The PASS gate and the appointment guard read that one
    answer: neither refuses over it."""
    e = _self_checked(tmp_path)
    _validator_fails(e)
    assert e.pass_blocked_by(TaskId(SEAM)) is None
    assert _his_pass(e)["state"] == "DONE"
    _not_refuted(e)
    assert [o["validator"] for o in T.get_verdict(e, SEAM).get("others", [])] == ["p-val"]


def test_where_he_checks_it_himself_his_own_fail_holds_his_appointment(tmp_path):
    e = _self_checked(tmp_path)
    _record(e, "user", "FAIL")
    out = _call(PAGE, "set_checker", e, SEAM, OTHER, agent="user")
    assert out.get("refused") and "FAIL" in out["error"], out
    assert not _his_pass(e).get("accepted")


def test_a_named_partys_hand_pass_is_not_the_instruments_after_a_switch_to_the_validator(tmp_path):
    e = _delivered(tmp_path)
    _record(e, CHECKER)
    assert _call(PAGE, "set_checker", e, SEAM, "validator", agent="user").get("checker") == "validator"
    v = T.get_verdict(e, SEAM)
    assert v.get("verdict") is None and [o["validator"] for o in v["others"]] == [CHECKER], v
    assert (e.pass_blocked_by(TaskId(SEAM)) or {}).get("kind") == "unobserved"
    assert not _his_pass(e).get("accepted")


def test_an_internal_nodes_self_check_is_not_the_named_partys_record(tmp_path):
    """Below the person's seam a part self-verifies, its DELIVER report its record (§10.3) — unless its issuer named a
    party to check it: then that party's record is the verdict's place, and the self-report stands beside it."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.set_mode(Mode.SOLO, None, AgentId("user"))
    e.workforce.publish_roster({OTHER: "external"})
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g")]})
    T.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "part", "criteria": [criterion("k")]},
                             "assignee": "user", "covers": ["g"]}], accepted_risks=REGISTER)
    e.wait_idle()
    e.set_checker(TaskId("kid"), OTHER, AgentId("user"), "ann checks it")
    assert e.named_checker(TaskId("kid")) == OTHER
    for tid in ("root", "kid"):
        T.signal(e, tid, "ACCEPT", "user")
    T.signal(e, "kid", "DELIVER", "user", result="ran `check k`: it printed OK", self_validation="PASS")
    e.wait_idle()
    assert e.get_exec_verdict(TaskId("kid")) is None, e.get_exec_verdict(TaskId("kid"))
    assert [r["validator"] for r in e.others_records(TaskId("kid"))] == ["user"]
    e.stop()


def test_an_instrument_run_at_a_named_node_leaves_the_named_partys_move_on_the_frontier(tmp_path):
    e = _delivered(tmp_path)
    assert e.claims.begin_validation(TaskId(SEAM)) is not None
    theirs = [s for s in T.next_steps(e, actor=CHECKER)["steps"] if s.get("task_id") == SEAM]
    assert theirs and all(s["mine"] and "record_verdict" in s["directive"] for s in theirs), theirs
    busy = [n for n in e.in_flight_nodes() if n["task_id"] == SEAM]
    assert busy and "record_verdict" in busy[0]["opens_with"] and CHECKER in busy[0]["opens_with"], busy


def test_an_appointment_coming_back_with_a_reassign_away_is_said(tmp_path):
    e = _issued(tmp_path)
    out = _call(PAGE, "reassign", e, SEAM, CHECKER)
    assert CHECKER in str(out.get("checker", "")) and "lapse" in str(out.get("checker", "")), out
    e.wait_idle()
    out = _call(PAGE, "reassign", e, SEAM, ROLE)
    assert e.named_checker(TaskId(SEAM)) == CHECKER
    assert CHECKER in str(out.get("checker", "")) and "again" in str(out.get("checker", "")), out


# ── one record the verdict surface and the gate read; under «self» the instrument is evidence, and named ───────────

@pytest.mark.parametrize("first", [CHECKER, "self"])
def test_a_switch_to_the_validator_seats_the_fail_its_gate_decides_on(tmp_path, first):
    """Under the validator at his seam any FAIL on the tree decides (`standing_check`): the seat reads that FAIL, not a
    later PASS that stood beside it — get_verdict and the gate say one thing."""
    e = _issued(tmp_path, checker=first)
    T.signal(e, SEAM, "DELIVER", HOLDER, result="it holds", self_validation="PASS")
    e.wait_idle()
    _validator_fails(e)
    instrument_passes(e, TaskId(SEAM), validator="p-val")
    assert _call(PAGE, "set_checker", e, SEAM, "validator", agent="user").get("checker") == "validator"
    assert (e.pass_blocked_by(TaskId(SEAM)) or {}).get("kind") == "observed_fail"
    v = T.get_verdict(e, SEAM)
    assert (v["verdict"], v["validator"]) == ("FAIL", "p-val"), v
    assert not _his_pass(e).get("accepted")


def test_where_he_checks_it_himself_an_instrument_run_is_no_wait(tmp_path):
    e = _self_checked(tmp_path)
    assert e.claims.begin_validation(TaskId(SEAM)) is not None
    with _as(PAGE):
        his = [s for s in TL.next_steps(e, actor="user")["steps"] if s.get("task_id") == SEAM]
    assert his and all(s["mine"] and not s.get("optional") for s in his), his
    busy = [n for n in e.in_flight_nodes() if n["task_id"] == SEAM]
    assert busy and "arrives by itself" not in busy[0]["opens_with"] and "validate_result" not in busy[0]["opens_with"], busy
    assert not T.observed_by_itself(e, e.graph.get_task(TaskId(SEAM)))


def test_a_named_checker_told_to_move_records_while_an_instrument_runs(tmp_path):
    """The step his frontier gives the named party is taken by the door while an instrument runs: its record lands beside
    the verdict, so nothing races — else anyone re-running the instrument held the appointed check off. Where the
    instrument IS the check, the record still waits for it."""
    e = _delivered(tmp_path)
    assert e.claims.begin_validation(TaskId(SEAM)) is not None
    steps = [s for s in TL.next_steps(e, actor=CHECKER)["steps"] if s.get("task_id") == SEAM]
    assert steps and steps[0]["mine"], steps
    out = _record(e, CHECKER)
    assert out.get("recorded"), out
    e2 = _delivered(tmp_path / "v")
    assert _call(PAGE, "set_checker", e2, SEAM, "validator", agent="user").get("checker") == "validator"
    assert e2.claims.begin_validation(TaskId(SEAM)) is not None
    assert _record(e2, CHECKER).get("validation_in_flight")


def test_where_he_checks_it_himself_an_instruments_fail_beside_is_named_when_he_signs(tmp_path):
    e = _self_checked(tmp_path)
    _validator_fails(e)
    with _as(PAGE):
        his = [s for s in TL.next_steps(e, actor="user")["steps"] if s.get("task_id") == SEAM]
    assert his and all("p-val" in s["directive"] and "FAIL" in s["directive"] for s in his), his
    out = _his_pass(e)
    assert out["state"] == "DONE" and "p-val" in str(out.get("signed_beside")), out


def test_who_checks_a_settled_node_is_not_appointed_anew(tmp_path):
    """§12.14: a settled node's verdict stands; an appointment there would re-decide nothing and show it beside itself."""
    e = _self_checked(tmp_path)
    assert _his_pass(e)["state"] == "DONE"
    out = _call(PAGE, "set_checker", e, SEAM, OTHER, agent="user")
    assert out.get("refused") and "settled" in out["error"], out
