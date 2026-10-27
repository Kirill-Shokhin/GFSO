"""What contact shows about the plan reaches the one whose move repairs it (docs/notes/OWN_PLAN_REPLANNING_MOVES.md).

Row GB_sql_database_tnkid4876: 0 CHALLENGE — the first-round packet never offered it and TECH_REPORT sent "a pinned check
contradicts the contract" to the system's maker, so a pin missing `-lm` travelled 24 min as BLOCK + 4 tech reports
(§11.3). And a validator wrote "observed but outside the stated criteria … NOT IN (SELECT …) give NULL" — the row's
held-out miss — in prose no channel carried (FM-1.f is read at contact, §8.3): now a structured `outside`, recorded
with the verdict, decided by nothing (Inv-2), shown to the node's issuer and to its parent's.

CONTROLS (each breaks exactly its test): drop `CHALLENGE_WHEN` from `_executor_packet` — the packet test; put "a pinned
check contradicts the contract" back into TECH_REPORT — the tech-report test; drop `**_outside(outside)` from the
exec-verdict record in `store_verdict` — the recorded test; drop the `outside_text` line of `issuer_context` — the
issuer test; write `outside` into the record always — the unchanged test."""
from gfso import tools as T
from gfso import tools_llm as TL
from gfso.core.types import TaskId
from gfso.issuer import issuer_context
from gfso.packets import TECH_REPORT, _executor_packet
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
            assert f"`n1`: {SEEN}" in ctx and "is FM-1.f — add the criterion" in ctx, (tid, question)
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
    finally:
        e.stop()
