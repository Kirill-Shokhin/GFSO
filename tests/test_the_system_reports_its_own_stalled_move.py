"""A move the system owes is made in time, or the system says it is stuck. Inv-8 promises only that a move exists; a
dispute the issuer failed to rule froze a row 2 h 26 m (series 2 REF 2), disputes over findings shown without their
inputs looped 5 h (series 3) — both seen by a human, hours late. The sweep that owes the move now says so itself: one
TECH REPORT per node version and question, nothing else changed."""
import threading

import pytest

import gfso.issuer as I
import tests.test_the_mode_decides_who_holds_what as M
from gfso.core.types import Mode, TaskId
from gfso.roster import AgentRegistry
from tests.test_the_mode_decides_who_holds_what import _auto_goal
from tests.support import issuer_sweep


def _sweeper(e, agents, monkeypatch, status, real=False):
    """`real`: the graph's own questions and their movers, not scripted ones."""
    q = {"now": [(TaskId("root"), "dispute")]}
    if not real:
        monkeypatch.setattr(I, "open_questions", lambda en: q["now"])
        monkeypatch.setattr(I, "system_mover", lambda *a, **k: "exec-1")
    monkeypatch.setattr(I, "settle", lambda *a, **k: dict(status))
    ledger, owed, cap = {}, {}, threading.Semaphore(1)

    def sweep():
        issuer_sweep(e, agents, lambda k: True, lambda *a, **k: None, cap, None, ledger, owed)
        ledger.update({g: (w, 0.0, n) for g, (w, _, n) in ledger.items()})   # every sweep runs past the wait
    return sweep, q, owed


def _backdate(owed):
    owed.update({k: (since - I.STUCK_S - 1, *rest) for k, (since, *rest) in owed.items()})


def _stuck(e):
    return [r for r in e.tech_reports() if r["actor"] == "liveness"]


def test_answers_that_leave_the_question_standing_are_reported_once(tmp_path, monkeypatch):
    e, agents = _auto_goal(tmp_path)
    sweep, _, _ = _sweeper(e, agents, monkeypatch, {"status": "noop"})
    for _ in range(I.STUCK_ANSWERS):
        sweep()
    assert not _stuck(e), "reported before the count was reached"
    for _ in range(3):
        sweep()
    reports = _stuck(e)
    assert len(reports) == 1 and "dispute" in reports[0]["text"] and reports[0]["node"] == "root"


def test_a_question_owed_past_its_bound_is_reported(tmp_path, monkeypatch):
    e, agents = _auto_goal(tmp_path)
    sweep, _, owed = _sweeper(e, agents, monkeypatch, {"status": "unavailable", "why": "the place changed"})
    sweep()
    assert not _stuck(e)
    _backdate(owed)
    sweep()
    sweep()
    assert len(_stuck(e)) == 1 and "unanswered" in _stuck(e)[0]["text"]


def _plan_question(tmp_path, monkeypatch, mode):
    """A root whose plan question is open (a criterion no child carries, §12.10) — the person's with no mode, the
    system's under AUTO (`system_mover`)."""
    e = M._engine(mode)
    M._goal(e)
    monkeypatch.setattr(e, "split_holes", lambda t: ["h"] if str(t) == "root" else [])
    assert (TaskId("root"), "plan") in I.open_questions(e)
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    agents.register("exec-1", "llm-executor", workdir=str(tmp_path))
    return e, agents


def _owed_past_the_bound(e, agents, monkeypatch):
    sweep, _, owed = _sweeper(e, agents, monkeypatch, {"status": "unavailable", "why": "x"}, real=True)
    sweep()
    _backdate(owed)
    sweep()
    return _stuck(e)


def test_a_persons_move_is_never_reported_as_the_systems_stall(tmp_path, monkeypatch):
    """No mode: the root's plan question is the person's (§10.1), and a person's silence is no fault (§12.2) — it was
    said "the system is stuck on its own move" after 1801 s (rdl tr-1, 2026-11-23)."""
    e, agents = _plan_question(tmp_path, monkeypatch, None)
    assert I.system_mover(e, agents, TaskId("root"), "plan") is None
    assert not _owed_past_the_bound(e, agents, monkeypatch)


def test_control_the_systems_own_plan_question_past_its_bound_is_reported(tmp_path, monkeypatch):
    e, agents = _plan_question(tmp_path, monkeypatch, Mode.AUTO)
    assert I.system_mover(e, agents, TaskId("root"), "plan") is not None
    reports = _owed_past_the_bound(e, agents, monkeypatch)
    assert len(reports) == 1 and "plan" in reports[0]["text"] and reports[0]["node"] == "root"


def test_a_question_that_closes_starts_its_clock_over(tmp_path, monkeypatch):
    e, agents = _auto_goal(tmp_path)
    sweep, q, owed = _sweeper(e, agents, monkeypatch, {"status": "unavailable", "why": "x"})
    sweep()
    _backdate(owed)
    q["now"] = []                      # answered: the question left before the next sweep
    sweep()
    assert set(owed) == {I.SETTLED}
    q["now"] = [(TaskId("root"), "dispute")]
    sweep()
    assert not _stuck(e), "a question asked anew inherited the old one's time"


def test_control_without_the_monitor_nothing_is_said(tmp_path, monkeypatch):
    e, agents = _auto_goal(tmp_path)
    monkeypatch.setattr(I, "open_questions", lambda en: [(TaskId("root"), "dispute")])
    monkeypatch.setattr(I, "system_mover", lambda *a, **k: "exec-1")
    monkeypatch.setattr(I, "settle", lambda *a, **k: {"status": "noop"})
    ledger, cap = {}, threading.Semaphore(1)
    for _ in range(I.STUCK_ANSWERS + 3):
        issuer_sweep(e, agents, lambda k: True, lambda *a, **k: None, cap, None, ledger)
        ledger.update({g: (w, 0.0, n) for g, (w, _, n) in ledger.items()})
    assert not _stuck(e)


def test_a_plan_converging_is_not_stuck_and_one_that_stops_is(tmp_path, monkeypatch):
    """The plan question moves by degrees: a review that leaves fewer findings open is progress though the question
    stands (gb-c-compiler-tnpji8716: 44 → 8 findings in 27 min, said stuck at 1814 s)."""
    e, agents = _auto_goal(tmp_path)
    sweep, q, owed = _sweeper(e, agents, monkeypatch, {"status": "unavailable", "why": "x"})
    q["now"] = [(TaskId("root"), "plan")]
    left = {"n": 44}
    monkeypatch.setattr(e, "split_holes", lambda t: [])
    monkeypatch.setattr(e, "open_l2_findings", lambda t: None if left["n"] is None else ["f"] * left["n"])
    sweep()
    for n in (29, None, 21, None, 10, 8):    # None: an answer changed the plan, its review not yet run (minutes)
        if n is not None:
            _backdate(owed)
        left["n"] = n
        sweep()
    assert not _stuck(e), "a converging plan was said stuck"
    _backdate(owed)                    # no fall since: owed past the bound
    sweep()
    assert len(_stuck(e)) == 1 and "plan" in _stuck(e)[0]["text"]


def test_a_new_version_of_the_node_counts_its_findings_afresh(tmp_path, monkeypatch):
    """The least count belongs to one version of the node: a refined plan opening at 20 findings and falling to 12
    converges, though 12 is above the earlier version's 8."""
    e, agents = _auto_goal(tmp_path)
    sweep, q, owed = _sweeper(e, agents, monkeypatch, {"status": "unavailable", "why": "x"})
    q["now"] = [(TaskId("root"), "plan")]
    left = {"n": 8}
    monkeypatch.setattr(e, "split_holes", lambda t: [])
    monkeypatch.setattr(e, "open_l2_findings", lambda t: ["f"] * left["n"])
    sweep()
    root = e.graph.get_task(TaskId("root"))
    monkeypatch.setattr(type(root), "iteration", property(lambda self: 7), raising=False)
    for n in (20, 16, 12):
        _backdate(owed)
        left["n"] = n
        sweep()
    assert not _stuck(e), "a new version's convergence was measured against the old version's least"


def test_answers_that_keep_a_plan_converging_are_not_counted_against_it(tmp_path, monkeypatch):
    """Both counts run from the last move: answers that each leave the plan standing but its findings falling are not
    "in a row without moving it"; once the fall stops, STUCK_ANSWERS more of them are."""
    e, agents = _auto_goal(tmp_path)
    sweep, q, _ = _sweeper(e, agents, monkeypatch, {"status": "noop"})
    q["now"] = [(TaskId("root"), "plan")]
    left = {"n": 44}
    monkeypatch.setattr(e, "split_holes", lambda t: [])
    monkeypatch.setattr(e, "open_l2_findings", lambda t: ["f"] * left["n"])
    for i in range(2 * I.STUCK_ANSWERS):
        if i % 4 == 0:
            left["n"] -= 1
        sweep()
    assert not _stuck(e), "answers that kept a plan converging were counted as standing"
    for _ in range(I.STUCK_ANSWERS + 2):
        sweep()
    assert len(_stuck(e)) == 1


# ── the watch withdraws what it said once it no longer holds: nobody signs as the watch, so a report it left open stood
# for ever — 110 of 112 open on one project, 79 addressed to the person over a stall never the system's (2026-11-24)

def _reported(e, agents, monkeypatch):
    sweep, q, owed = _sweeper(e, agents, monkeypatch, {"status": "unavailable", "why": "x"})
    sweep()
    _backdate(owed)
    sweep()
    assert len(_stuck(e)) == 1
    return sweep, q


def _withdrawn(e):
    return [r for r in e.tech_reports(resolved=True) if r["actor"] == I.WATCH and r.get("resolved_at")]


def _said(question, node="root"):
    return (f"the system is stuck on its own move: it owes the {question} question on {node} for 1801s; 0 answer(s) in "
            f"a row left it standing, 0 turn(s) went unanswered")


def test_a_report_is_withdrawn_when_its_question_closes(tmp_path, monkeypatch):
    e, agents = _auto_goal(tmp_path)
    sweep, q = _reported(e, agents, monkeypatch)
    q["now"] = []
    sweep()
    (r,) = _withdrawn(e)
    assert not _stuck(e) and r["resolved_by"] == I.WATCH
    assert r["how"] == "the system no longer owes the dispute question on root: it closed"


@pytest.mark.parametrize("said, now", [("dispute", "escalation"), ("repair", "dispute")])
def test_a_question_lapsed_or_masked_into_another_the_system_owes_stays_reported(tmp_path, monkeypatch, said, now):
    """`open_questions` keeps one question per node: a dispute lapsing by its clock into escalation, or a repair masked
    by a dispute, leaves the node's stall standing — withdrawn as «closed», it hid the defect the watch exists to say."""
    e, agents = _auto_goal(tmp_path)
    sweep, q, owed = _sweeper(e, agents, monkeypatch, {"status": "unavailable", "why": "x"})
    q["now"] = [(TaskId("root"), said)]
    sweep()
    _backdate(owed)
    sweep()
    assert len(_stuck(e)) == 1
    q["now"] = [(TaskId("root"), now)]
    sweep()
    assert [said in r["text"] for r in _stuck(e)] == [True] and not _withdrawn(e)
    q["now"] = []                      # …and once nothing the system owes stands on the node, it is withdrawn
    sweep()
    assert not _stuck(e) and len(_withdrawn(e)) == 1


def test_a_report_is_withdrawn_when_its_move_is_no_longer_the_systems(tmp_path, monkeypatch):
    e, agents = _auto_goal(tmp_path)
    sweep, _ = _reported(e, agents, monkeypatch)
    monkeypatch.setattr(I, "system_mover", lambda *a, **k: None)
    sweep()
    (r,) = _withdrawn(e)
    assert not _stuck(e) and r["how"] == "the system no longer owes the dispute question on root: its move is not the system's"


def test_a_report_is_withdrawn_when_its_node_takes_a_new_version(tmp_path, monkeypatch):
    e, agents = _auto_goal(tmp_path)
    sweep, _ = _reported(e, agents, monkeypatch)
    root = e.graph.get_task(TaskId("root"))
    monkeypatch.setattr(type(root), "iteration", property(lambda self: 7), raising=False)
    sweep()
    (r,) = _withdrawn(e)
    assert not _stuck(e) and "new version" in r["how"]


def test_control_a_stall_that_holds_stays_reported(tmp_path, monkeypatch):
    e, agents = _auto_goal(tmp_path)
    sweep, _ = _reported(e, agents, monkeypatch)
    for _ in range(3):
        sweep()
    assert len(_stuck(e)) == 1 and not _withdrawn(e)


def test_what_an_earlier_run_said_is_settled_at_the_first_sweep(tmp_path, monkeypatch):
    """The run that filed them is gone with its `owed`: the next run's first sweep withdraws each report on a question it
    no longer owes on a node it owes nothing on, and leaves standing the one it still owes."""
    e, agents = _auto_goal(tmp_path)
    for node, question in (("kid", "plan"), ("root", "dispute")):
        e.tech_report(_said(question, node), role="system", actor=I.WATCH, task_id=node)
    sweep, _, _ = _sweeper(e, agents, monkeypatch, {"status": "unavailable", "why": "x"})   # owes root's dispute only
    sweep()
    (r,) = _withdrawn(e)
    assert r["text"] == _said("plan", "kid") and [s["text"] for s in _stuck(e)] == [_said("dispute")]


def test_control_no_one_else_resolves_a_report_not_theirs(tmp_path, monkeypatch):
    """The watch withdraws its own; an agent or a person neither its author nor its addressee is still refused."""
    e, agents = _auto_goal(tmp_path)
    _reported(e, agents, monkeypatch)
    (r,) = _stuck(e)
    for by in {"exec-1", "user", "system"} - {r["addressee"]}:
        assert isinstance(e.resolve_report(r["id"], "closing it", by), str), by
    assert _stuck(e)
