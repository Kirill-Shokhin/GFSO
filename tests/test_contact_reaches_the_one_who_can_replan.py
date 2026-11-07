"""What contact shows about the plan reaches the one whose move repairs it (docs/notes/OWN_PLAN_REPLANNING_MOVES.md).

Row GB_sql_database_tnkid4876: 0 CHALLENGE — the first-round packet never offered it and TECH_REPORT sent "a pinned check
contradicts the contract" to the system's maker, so a pin missing `-lm` travelled 24 min as BLOCK + 4 tech reports
(§11.3). And a validator wrote "observed but outside the stated criteria … NOT IN (SELECT …) give NULL" — the row's
held-out miss — in prose no channel carried (FM-1.f is read at contact, §8.3): now a structured `outside`, recorded
with the verdict, decided by nothing (Inv-2), shown wherever the node's issuer decides about it or its parent's split,
and ASKED of that issuer once (the `outside` question), its answer retiring it from every later read.

CONTROLS (each breaks exactly its test): drop `CHALLENGE_WHEN` from `_executor_packet` — the packet test; put "a pinned
check contradicts the contract" back into TECH_REPORT — the tech-report test; drop `**_outside(outside)` from the
exec-verdict record in `store_verdict` — the recorded test; drop the `outside_text` line of `issuer_context` — the
issuer test; write `outside` into the record always — the unchanged test; drop `qs.append("outside")` from
`open_questions` — the asked test and the three that answer it; drop `engine.answer_outside` from `issuer_turn`, or `k
not in answered` from `outside_observations` — the asked test and the two answered tests; read an issuer question's
observations off the node instead of its parent's split (`holder = task.id`) — the sibling test and the issuer test;
sort `outside_the_criteria` oldest first — the newest test; show the evidence whole (`_tail`) — the evidence test; let
`decline` pass without its reason — the reason test; drop `not engine.users_plan()` from `open_questions` — the
user's-plan test."""
import json

from gfso import issuer as I
from gfso import tools as T
from gfso import tools_llm as TL
from gfso.core.types import TaskId
from gfso.engine.verdicts import OBSERVATIONS, OUTSIDE_ANSWERED, ledger_read, ledger_write
from gfso.issuer import issuer_context
from gfso.packets import SHOWN_FINDINGS, TECH_REPORT, _executor_packet
from tests.test_validate_result import _ValidatorLLM, _delivered_node, _eng, _fenced

SEEN = "a subquery in NOT IN (SELECT …) gives NULL"


def _entry(name: str) -> dict:
    return {"criterion": name, "verdict": "pass", "evidence": "ran it", "behaviours": ["the criterion holds"],
            "divergences": [], "probe": [{"command": f"check {name}", "expect": "it holds"}]}


def _validated(outside=None) -> tuple:
    e = _eng()
    _delivered_node(e, extra_dep=True)
    report = {"verdict": "PASS", "per_criterion": [_entry("flush"), _entry("holds")], "failed_criteria": []}
    if outside is not None:
        report["outside"] = outside
    return e, TL.validate_result(e, "n1", _llm=_ValidatorLLM(_fenced(report)))


def test_the_first_round_packet_offers_challenge_and_says_what_it_buys():
    e = _eng()
    T.create_task(e, "n", {"description": "link it", "criteria": [{"name": "c", "description": "links", "check": [
        {"behaviour": "links", "command": "cc main.c -o m", "expect": "ok"}]}]}, "alice")
    packet = _executor_packet(e, e.graph.get_task(TaskId("n")), None)
    e.stop()
    assert "REWORKING" not in packet
    assert 'Report `status: "challenge"`, naming the criterion' in packet
    assert "does not build or link as written" in packet and "reads an input that is empty or absent" in packet
    assert "installs a corrected contract" in packet and "returns the work unchanged" in packet
    assert "`blocked` leaves the pin as it is" in packet


def test_a_defect_of_the_tasks_contract_is_a_challenge_not_a_tech_report():
    said = TECH_REPORT["description"]
    assert "pinned check contradicts the contract" not in said
    assert "is no tech report: it is the executor's CHALLENGE" in said


def test_an_outside_observation_is_recorded_with_the_verdict_and_decides_nothing():
    e, out = _validated([{"what": SEEN, "evidence": "SELECT 1 WHERE 1 NOT IN (SELECT 2) printed NULL"}])
    e0, out0 = _validated()
    try:
        assert (out["verdict"], out["failed_criteria"]) == (out0["verdict"], out0["failed_criteria"]) == ("PASS", [])
        rec = e.get_exec_verdict(TaskId("n1"))
        assert rec["outside"] == [{"what": SEEN, "evidence": "SELECT 1 WHERE 1 NOT IN (SELECT 2) printed NULL"}], rec
        assert rec["per_criterion"] == e0.get_exec_verdict(TaskId("n1"))["per_criterion"]
    finally:
        e.stop()
        e0.stop()


def test_it_reaches_the_machine_issuer_of_the_node_and_of_its_parents_split_and_the_holders_read():
    e, _ = _validated([{"what": SEEN, "evidence": "printed NULL"}])
    try:
        for tid, question in (("n1", "escalation"), ("goal", "repair"), ("goal", "plan")):
            ctx = issuer_context(e, TaskId(tid), question)
            assert f"`n1`: {SEEN}" in ctx and "is FM-1.f, which the split's own moves close" in ctx, (tid, question)
        read = T.get_task(e, "goal")["outside_the_criteria"]
        assert read["observations"] == [{"node": "n1", "what": SEEN, "evidence": "printed NULL"}]
        assert "judge each against the goal statement" in read["judge"]
    finally:
        e.stop()


def test_a_report_without_outside_is_unchanged():
    e, _ = _validated()
    try:
        assert "outside" not in e.get_exec_verdict(TaskId("n1"))
        assert "outside the written criteria" not in issuer_context(e, TaskId("goal"), "repair")
        assert "outside_the_criteria" not in T.get_task(e, "goal")
        assert "goal" not in _asked(e) or _asked(e)["goal"] != "outside"
    finally:
        e.stop()


class _Issuer:
    """The machine issuer's model: one canned answer, every packet it was handed kept."""
    def __init__(self, answer: dict):
        self._text, self.calls, self.packets = "```json\n" + json.dumps(answer) + "\n```", [], []

    def complete(self, prompt, context=""):
        self.packets.append(prompt)
        self.calls.append({"duration_ms": 1, "output_tokens": 1})
        return self._text

    def tag_last(self, stage):
        self.calls[-1]["stage"] = stage


def _asked(e) -> dict:
    return {str(t): q for t, q in I.open_questions(e)}


def _declined(e, why="the goal names no subqueries") -> dict:
    return I.issuer_turn(e, TaskId("goal"), "outside", "boss", _llm=_Issuer({"move": "decline", "justification": why}))


def test_a_pass_with_an_outside_observation_asks_the_nodes_issuer_once():
    e, out = _validated([{"what": SEEN, "evidence": "printed NULL"}])
    try:
        assert out["verdict"] == "PASS" and e.get_exec_verdict(TaskId("n1"))["verdict"] == "PASS"
        # asked at the split it lies in, whose holder is the node's issuer — the node's own verdict untouched
        assert _asked(e).get("goal") == "outside" and "n1" not in _asked(e), _asked(e)
        assert str(e.graph.issuer_of(TaskId("n1"))) == str(e.graph.get_task(TaskId("goal")).assignee)
        llm = _Issuer({"move": "decline", "justification": "the goal names no subqueries"})
        assert I.issuer_turn(e, TaskId("goal"), "outside", "boss", _llm=llm)["status"] == "applied"
        assert f"`n1`: {SEEN}" in llm.packets[0] and "`decline`" in llm.packets[0]
        assert "goal" not in _asked(e), "answered once, it is not asked again"
    finally:
        e.stop()


def test_a_plan_the_user_handed_in_is_not_asked_to_take_it(monkeypatch):
    """Only the plan's author writes into it, and `settle` STOPS the run on a split question there: asked, an
    observation that fails nothing would stop the user's run."""
    e, _ = _validated([{"what": SEEN, "evidence": "printed NULL"}])
    try:
        monkeypatch.setattr(e, "users_plan", lambda: True)
        assert _asked(e).get("goal") != "outside" and f"`n1`: {SEEN}" in issuer_context(e, TaskId("goal"), "repair")
    finally:
        e.stop()


def test_a_decline_without_a_reason_answers_nothing():
    e, _ = _validated([{"what": SEEN, "evidence": "printed NULL"}])
    try:
        assert _declined(e, why="")["status"] == "refused" and _asked(e).get("goal") == "outside"
    finally:
        e.stop()


def test_an_answered_observation_leaves_every_later_view_and_stays_on_the_record():
    e, _ = _validated([{"what": SEEN, "evidence": "printed NULL"}])
    try:
        assert _declined(e)["status"] == "applied"
        for tid, question in (("n1", "escalation"), ("goal", "repair"), ("prod", "external")):
            assert SEEN not in issuer_context(e, TaskId(tid), question), (tid, question)
        assert "outside_the_criteria" not in T.get_task(e, "goal")
        assert e.get_exec_verdict(TaskId("n1"))["outside"][0]["what"] == SEEN, "the record is kept whole"
        said = ledger_read(e._storage, TaskId("n1"), OUTSIDE_ANSWERED, [])
        assert [(a["what"], a["move"], a["why"]) for a in said] == [(SEEN, "decline", "the goal names no subqueries")]
    finally:
        e.stop()


def test_a_move_answers_the_observation_too():
    e, _ = _validated([{"what": SEEN, "evidence": "printed NULL"}])
    try:
        add = {"move": "add_child", "justification": "the goal's SQL has subqueries", "child": {
            "name": "subqueries", "description": "NOT IN over a subquery", "covers": ["hung"], "criteria": [
                {"name": "not_in", "description": "NOT IN (SELECT …) gives the SQL answer", "check": [
                    {"behaviour": "not in", "command": "check not_in", "expect": "0"}]}]}}
        out = I.issuer_turn(e, TaskId("goal"), "outside", "boss", _llm=_Issuer(add))
        assert out["status"] == "applied", out
        assert _asked(e).get("goal") != "outside", _asked(e)
        assert ledger_read(e._storage, TaskId("n1"), OUTSIDE_ANSWERED, [])[0]["move"] == "add_child"
    finally:
        e.stop()


def test_a_siblings_external_question_shows_the_observation_of_another_child_of_the_split():
    e, _ = _validated([{"what": SEEN, "evidence": "printed NULL"}])
    try:
        assert f"`n1`: {SEEN}" in issuer_context(e, TaskId("prod"), "external")
    finally:
        e.stop()


def _many(e, n: int) -> None:
    ledger_write(e._storage, TaskId("n1"), OBSERVATIONS, ledger_read(e._storage, TaskId("n1"), OBSERVATIONS, []) + [
        {"verdict": "PASS", "outside": [{"what": f"obs-{i:02d}", "evidence": ""}], "log_at": 1000 + i} for i in range(n)])


def test_the_view_is_newest_first_under_its_cap():
    e, _ = _validated([{"what": SEEN, "evidence": "printed NULL"}])
    try:
        _many(e, SHOWN_FINDINGS + 4)
        ctx = issuer_context(e, TaskId("goal"), "outside")
        newest = f"obs-{SHOWN_FINDINGS + 3:02d}"
        assert newest in ctx and ctx.index(newest) < ctx.index(f"obs-{SHOWN_FINDINGS + 2:02d}")
        assert "obs-00" not in ctx and "… and 5 more observations" in ctx, ctx[-600:]
    finally:
        e.stop()


def test_evidence_is_cut_to_its_tail_in_the_packet_and_kept_whole_on_the_record():
    long = "x" * 4990 + "END-OF-RUN"
    e, _ = _validated([{"what": SEEN, "evidence": long}])
    try:
        ctx = issuer_context(e, TaskId("goal"), "outside")
        assert "END-OF-RUN" in ctx and "x" * 400 not in ctx
        assert e.get_exec_verdict(TaskId("n1"))["outside"][0]["evidence"] == long
    finally:
        e.stop()


def test_an_answer_retires_only_what_its_packet_showed_inline():
    """Past the inline cap the rest went to a file the zero-tool issuer cannot read; marking every one answered lost the
    earliest — in the measured row, the hole itself (critic over d6c48ea). The rest stays asked."""
    e, _ = _validated([{"what": SEEN, "evidence": "printed NULL"}]
                      + [{"what": f"obs-{i:02}", "evidence": "x"} for i in range(SHOWN_FINDINGS + 4)])
    try:
        assert _declined(e)["status"] == "applied"
        left = [o["what"] for o in e.outside_the_criteria(TaskId("goal"), own=False)]
        assert len(left) == 5 and _asked(e).get("goal") == "outside", left
    finally:
        e.stop()
