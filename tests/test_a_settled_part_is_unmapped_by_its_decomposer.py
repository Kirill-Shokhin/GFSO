"""A settled part whose pinned check resolves on no tree is lifted by its decomposer's re-decomposition, never a ruling
(docs/notes/SETTLED_PART_UNRESOLVABLE_CHECK.md): past consumption REOPEN is refused and recovery is the issuer's
re-decomposition (§12.14, :1394), a settled child the re-admission leaves mapped to nothing is admitted (§11.5, :1135).
The `decompose` door merges what it is told with what stands (the 2026-08-21 damage), so it takes the unmap explicitly
(`unmap`). A live child left unmapped is CHECK-1b's orphan as before; a settled one leaves the parent's procedure, stays
DONE and is consumed. An honest lift and the 2026-10-04 escape (later work broke the part, it is unmapped) look the same
to the engine, so each unmap of a settled part is a record where the seam is signed (Thm 11): who, when, and the part's
last re-run on the parent's delivery — read by `checks_no_longer_run`, so `get_verdict`, `claim_drift`, `narrowed` and the
closure record say it.

CONTROLS: drop the `unmap` pruning in `tools.decompose` and the first test goes red; drop `record_unmaps` from
`admission.admit`, the record tests; read the unmap rows out of `validation.checks_no_longer_run`, the record test's
`get_verdict` half; drop `checks_no_longer_run` from `closures.closure_of`, its closure half; drop `record_stands` from
`validation.last_rerun`, the FAIL-and-rework test; read `parts_not_shown_holding` alone there, the other-criterion test;
read the verdict of record alone there instead of `observations`, the earlier-round test; take the newest reading in
place of the failing one among those standing, the any-order test; drop `beside` from the engine's `parts_read`, the
landed-after-the-unmap test. The re-run is read when the row is read, through the protocol's own signals: frozen at the
unmap, or read off one record, the rows went stale (critics over a7b9480, a27426f)."""
import json

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from gfso import tools as T
from gfso import tools_llm as TL
from gfso.core.protocol.procedure import probe_id
from gfso.core.types import AgentId, CriterionMapping, Mode, Signal, SignalData, State, TaskId
from gfso.engine.closures import closure_of
from gfso.engine.verdicts import OBSERVATIONS, ledger_write, observations
from gfso.mcp.server import _bind
from tests.support import REGISTER, criterion, make_engine
from tests.test_a_check_of_the_plan_is_not_the_goal import _settled

ROOT, A = TaskId("root"), TaskId("root.a")
UNMAP_A = [{"criterion_name": "g", "child_id": "root.a"}]


def _kid(cid, covers, *names):
    return {"task_id": cid, "assignee": "carol", "covers": list(covers),
            "spec": {"description": cid, "criteria": [criterion(n) for n in names or (cid.split(".")[-1],)]}}


def _split(e, *kids, agent="alice", **kw):
    out = TL.TOOLS["decompose"](e, parent_id="root", agent=agent, accepted_risks=REGISTER, children=list(kids), **kw)
    e.wait_idle()
    return out


def _whole(*crits, settle=True):
    """alice's root; carol's root.a covering g, settled."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    TL.TOOLS["create_task"](e, task_id="root", spec={"description": "goal", "criteria": [criterion(c) for c in crits or ("g",)]},
                            assignee="alice", agent="alice")
    _split(e, _kid("root.a", crits or ("g",)))
    if settle:
        _settled(e, "root.a")
    return e


def _pins(e, crit="g"):
    return {p.command for c in e.parts_procedure(ROOT).get(crit, ()) for p in c.check}


def test_unmap_takes_a_settled_parts_checks_off_its_whole_and_leaves_it_done_and_consumed():
    e = _whole()
    assert _pins(e), "the settled part's check is not demanded of its whole to begin with"
    out = _split(e, _kid("root.b", ["g"]), unmap=UNMAP_A)
    assert not (isinstance(out, dict) and out.get("error")), out
    assert not _pins(e), "the unmapped settled part's check is still run over the whole's delivery"
    a = e.graph.get_task(A)
    assert a.state == State.DONE and e.graph.is_consumed(a) and e.reopen_refusal(A)
    assert ("g", "root.b") in {(m.criterion_name, str(m.child_id)) for m in e.graph.get_task(ROOT).criterion_mappings}
    e.stop()


def test_unmap_of_a_live_child_leaves_an_orphan_and_is_refused():
    e = _whole(settle=False)
    out = _split(e, _kid("root.b", ["g"]), unmap=UNMAP_A)
    assert isinstance(out, dict) and (out.get("refused") or out.get("error")) and "CHECK-1b" in str(out), out
    assert not e.graph.get_task(TaskId("root.b")), "a refused admission issued a child"
    e.stop()


def test_unmap_left_out_a_child_added_merges_with_the_coverage_that_stands():
    e = _whole("g", "h")
    _split(e, _kid("root.b", ["h"]))
    pairs = {(m.criterion_name, str(m.child_id)) for m in e.graph.get_task(ROOT).criterion_mappings}
    assert {("g", "root.a"), ("h", "root.a"), ("h", "root.b")} <= pairs, pairs
    assert _pins(e, "g") and e.claim_drift(ROOT)["checks_no_longer_run"] == []
    e.stop()


def test_unmap_is_the_decomposers_move_alone():
    e = _whole()
    out = _split(e, _kid("root.b", ["g"]), unmap=UNMAP_A, agent="mallory")
    assert (out.get("refused") or out.get("error")) and "alice" in str(out), out
    assert _pins(e), "a foreign unmap took the settled part's check off"
    e.stop()


def test_unmap_of_a_pair_that_does_not_stand_is_refused_not_ignored():
    e = _whole()
    out = _split(e, _kid("root.b", ["g"]), unmap=[{"criterion_name": "g", "child_id": "root.zz"}])
    assert (out.get("refused") or out.get("error")) and "root.zz" in str(out), out
    e.stop()


def _verdict_on_the_whole(e, verdict, per_criterion, by="validator"):
    """The whole's verdict recorded by the engine's own writer, its accounting of the parts' checks with it; each of the
    whole's own pinned checks reported run and holding."""
    own = {c.name: [{"id": probe_id(c.name, p), "behaviour": p.behaviour, "command": p.command, "expect": p.expect,
                     "held": True} for p in c.check] for c in e.graph.get_task(ROOT).spec.criteria}
    per_criterion = [{**x, "probe": own[x["criterion"]] + x.get("probe", [])} for x in per_criterion]
    failed = [x["criterion"] for x in per_criterion if x["verdict"] == "fail"]
    out = e.record_exec_verdict(ROOT, verdict, failed, by, per_criterion=per_criterion)
    assert str(out["verdict"]) == verdict, out
    return out


def _the_parts_check(e, crit="g"):
    (pid,) = [probe_id(c.name, p) for c in e.parts_procedure(ROOT)[crit] for p in c.check]
    return pid


def _cited(pid, held):
    return {"id": pid, "behaviour": "b", "command": "x", "held": held}


def test_unmap_record_names_the_decomposer_the_time_and_the_parts_last_rerun():
    e = _whole()
    # …the whole delivered and its validation did not show the part's check holding there (the live case's plain FAIL)
    _verdict_on_the_whole(e, "FAIL", [{"criterion": "g", "verdict": "fail", "evidence": "x"}])
    commands = _pins(e)
    _split(e, _kid("root.b", ["g"]), unmap=UNMAP_A)
    rows = T.get_verdict(e, "root")["checks_no_longer_run"]
    assert {r["command"] for r in rows} == commands, rows
    (row,) = rows
    assert row["decided_by"] == "alice" and row["at"] and row["node"] == "root" and row["criterion"] == "g", row
    assert row["part"] == "root.a" and row["rerun"] == "failing" and "while failing" in row["says"], row
    drift = e.claim_drift(ROOT)
    assert drift["checks_no_longer_run"] == rows and drift["narrowed"] is None, drift
    _settled(e, "root")
    assert closure_of(e, ROOT)["checked_by"]["checks_no_longer_run"] == rows
    e.stop()


def test_unmap_record_of_a_part_no_delivery_re_ran_says_so():
    e = _whole()
    _split(e, _kid("root.b", ["g"]), unmap=UNMAP_A)
    (row,) = e.checks_no_longer_run(ROOT)
    assert row["rerun"] == "never re-run" and row["rerun_record"] is None and "never re-run" in row["says"], row
    e.stop()


def _signal(e, sig, **kw):
    out = e.send_signal(SignalData(signal=sig, task_id=ROOT, source=AgentId("alice"), **kw))
    e.wait_idle()
    assert out is None or not out.rejected, out
    return out


def _delivered(e):
    """The whole delivered by its executor through the protocol's signals, to VALIDATING."""
    if e.graph.get_task(ROOT).state == State.OFFERED:
        _signal(e, Signal.ACCEPT)
    _signal(e, Signal.DELIVER, result="the whole")
    assert e.graph.get_task(ROOT).state == State.VALIDATING, e.graph.get_task(ROOT).state


def test_unmap_record_of_a_failing_part_survives_the_fail_and_its_rework():
    """The ordinary flow: the whole's FAIL shows the part not holding, the FAIL signal moves the whole to rework (a new
    generation), and its decomposer unmaps the part. Read off the record of record alone, the row said «not re-run» —
    the escape the record exists to name went unnamed (critic over a7b9480)."""
    e = _whole()
    _delivered(e)
    _verdict_on_the_whole(e, "FAIL", [{"criterion": "g", "verdict": "fail", "evidence": "broke",
                                       "probe": [_cited(_the_parts_check(e), False)]}])
    _signal(e, Signal.FAIL, result="g failed", failed_criteria=["g"])
    assert e.graph.get_task(ROOT).state == State.REWORKING
    _split(e, _kid("root.b", ["g"]), unmap=UNMAP_A)
    (row,) = e.checks_no_longer_run(ROOT)
    assert row["rerun"] == "failing" and not row["rerun_on_this_delivery"], row
    assert "last re-run: failing on the whole's delivery of" in row["says"] and "(iteration 0)" in row["says"], row
    assert "not re-run on this delivery" in row["says"] and row["rerun_record"]["verdict"] == "FAIL", row
    e.stop()


def test_unmap_record_of_a_part_held_on_an_earlier_round_is_not_held_on_this_delivery():
    """A PASS of round 0 credits the part, the part is unmapped, the whole is reworked and validated again at round 1 —
    where the part's check is no longer run. Frozen at the unmap, the row went on saying «held on this delivery»."""
    e = _whole()
    _delivered(e)
    _verdict_on_the_whole(e, "PASS", [{"criterion": "g", "verdict": "pass", "evidence": "ran",
                                       "probe": [_cited(_the_parts_check(e), True)]}])
    _split(e, _kid("root.b", ["g"]), unmap=UNMAP_A)
    (row,) = e.checks_no_longer_run(ROOT)
    assert row["rerun"] == "held" and row["rerun_on_this_delivery"] and "holding on this delivery" in row["says"], row
    _verdict_on_the_whole(e, "FAIL", [{"criterion": "g", "verdict": "fail", "evidence": "b's half is missing"}])
    _signal(e, Signal.FAIL, result="g failed", failed_criteria=["g"])
    _delivered(e)
    _verdict_on_the_whole(e, "FAIL", [{"criterion": "g", "verdict": "fail", "evidence": "still"}])
    (row,) = e.checks_no_longer_run(ROOT)
    assert row["rerun"] == "held" and not row["rerun_on_this_delivery"], row
    assert "holding on this delivery" not in row["says"] and "(iteration 0), not re-run on this delivery" in row["says"], row
    assert row["rerun_record"]["iteration"] == 0 and e.graph.get_task(ROOT).iteration == 1, row
    e.stop()


def test_unmap_record_of_a_voided_pass_is_not_held_on_this_delivery():
    e = _whole()
    _delivered(e)
    _verdict_on_the_whole(e, "PASS", [{"criterion": "g", "verdict": "pass", "evidence": "ran",
                                       "probe": [_cited(_the_parts_check(e), True)]}])
    e._graph.void_pending_pass(ROOT, "the delivery no longer stands")
    _split(e, _kid("root.b", ["g"]), unmap=UNMAP_A)
    (row,) = e.checks_no_longer_run(ROOT)
    assert row["rerun"] == "held" and not row["rerun_on_this_delivery"] and "not re-run on this delivery" in row["says"], row
    e.stop()


def test_unmap_record_stands_whichever_door_admits_and_leaves_with_the_pair_mapped_again():
    """The engine's own door installs a full set (the refine path): leaving the settled part out there is the same act,
    on the same record. Mapped again, its check runs again and the row leaves."""
    e = _whole()
    kid = _kid("root.b", ["g"])
    e.decompose_task(ROOT, [(TaskId("root.b"), T._named_spec(e, kid), "carol")], [CriterionMapping("g", TaskId("root.b"))])
    e.wait_idle()
    (row,) = e.checks_no_longer_run(ROOT)
    assert row["decided_by"] == "alice" and row["part"] == "root.a", row
    T.TOOLS["map_criterion"](e, "root", "root.a", "g", agent="alice")
    assert e.checks_no_longer_run(ROOT) == [] and _pins(e)
    e.stop()


def test_unmap_record_of_a_part_shown_holding_says_it_held():
    e = _whole()
    _verdict_on_the_whole(e, "PASS", [{"criterion": "g", "verdict": "pass", "evidence": "ran",
                                       "probe": [_cited(_the_parts_check(e), True)]}])
    _split(e, _kid("root.b", ["g"]), unmap=UNMAP_A)
    (row,) = e.checks_no_longer_run(ROOT)
    assert row["rerun"] == "held" and "holding" in row["says"], row
    assert row["rerun_record"]["verdict"] == "PASS" and row["rerun_record"]["log_at"] is not None, row
    e.stop()


def test_unmap_record_of_a_check_shown_failing_under_another_criterion_reads_failing():
    """`parts_not_shown_holding` names only the criteria a report fails that rest on the part; a check reported not
    holding under another one is failing on this delivery all the same (critic over b1db1bb)."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    TL.TOOLS["create_task"](e, task_id="root", spec={"description": "goal", "criteria": [criterion("g"), criterion("h")]},
                            assignee="alice", agent="alice")
    _split(e, _kid("root.a", ["g"]), _kid("root.c", ["h"]))
    _settled(e, "root.a")
    _verdict_on_the_whole(e, "FAIL", [{"criterion": "g", "verdict": "pass", "evidence": "ran"},
                                      {"criterion": "h", "verdict": "fail", "evidence": "broke",
                                       "probe": [_cited(_the_parts_check(e), False)]}])
    _split(e, _kid("root.b", ["g"]), unmap=UNMAP_A)
    (row,) = e.checks_no_longer_run(ROOT)
    assert row["rerun"] == "failing" and "while failing" in row["says"], row
    e.stop()


def _appointed():
    """A SOLO whole the person appointed ann to check, delivered: ann's record is the verdict of record, a passer-by's
    lands on the ledger beside it."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    e.set_mode(Mode.SOLO, None, AgentId("user"))
    e.workforce.publish_roster({"ann": "external"})
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g")]})
    T.decompose(e, "root", [{"task_id": "root.a", "spec": {"description": "a", "criteria": [criterion("a")]},
                             "assignee": "user", "covers": ["g"]}], accepted_risks=REGISTER)
    e.wait_idle()
    _settled(e, "root.a")
    e.set_checker(ROOT, "ann", AgentId("user"), "ann checks it", on_his_page=True)
    T.signal(e, "root", "ACCEPT", "user")
    e.wait_idle()
    T.signal(e, "root", "DELIVER", "user", result="the whole")
    e.wait_idle()
    return e


def test_unmap_record_reads_a_failing_run_on_this_delivery_whoever_recorded_it_and_in_any_order():
    """Two runs on one delivery — the appointed party's and a passer-by's — one shows the part failing. Read off the
    newest record and «on this delivery» only off the verdict of record, the row said «holding on this delivery» with the
    failing run unmentioned, or «failing … not re-run on this delivery», false (critic over a27426f)."""
    for first, then in ((("validator", "FAIL"), ("ann", "PASS")), (("ann", "PASS"), ("validator", "FAIL"))):
        e = _appointed()
        for who, v in (first, then):
            _verdict_on_the_whole(e, v, [{"criterion": "g", "verdict": v.lower(), "evidence": "ran",
                                          "probe": [_cited(_the_parts_check(e), v == "PASS")]}], by=who)
        T.decompose(e, "root", [{"task_id": "root.b", "spec": {"description": "b", "criteria": [criterion("b")]},
                                 "assignee": "user", "covers": ["g"]}], accepted_risks=REGISTER, unmap=UNMAP_A)
        e.wait_idle()
        (row,) = e.checks_no_longer_run(ROOT)
        assert row["rerun"] == "failing" and row["rerun_on_this_delivery"], (first, row)
        assert "unmapped while failing on this delivery" in row["says"], (first, row)
        e.stop()


def test_unmap_record_reads_a_run_that_lands_after_the_unmap_on_the_delivery_it_judged():
    """The 2026-10-04 escape itself: the unmap is admitted while the whole's validation runs on the same delivery, and its
    FAIL lands citing the part's check not holding. Read over the procedure as it stood at landing, the record kept no
    word of the part, and the row said «never re-run» (critic over a27426f)."""
    e = _whole()
    _delivered(e)
    pid, began = _the_parts_check(e), len(e._audit)
    _split(e, _kid("root.b", ["g"]), unmap=UNMAP_A)
    e.record_exec_verdict(ROOT, "FAIL", ["g"], "validator", log_at=began, per_criterion=[
        {"criterion": "g", "verdict": "fail", "evidence": "the part's check broke", "probe": [_cited(pid, False)]}])
    (row,) = e.checks_no_longer_run(ROOT)
    assert row["rerun"] == "failing" and row["rerun_on_this_delivery"], row
    e.stop()


def test_unmap_waits_for_a_validation_of_the_whole_in_flight_and_its_failing_run_is_on_the_record():
    """The system's run observes the part's pinned check at its start and merges it over the procedure standing when its
    report lands: an unmap admitted between took the part out, the failing check was dropped, the whole recorded PASS and
    the row said «never re-run» (critic over 6d9f7a7). The race is refused, naming the run and its lift: wait for its
    verdict, then unmap (§12.16 (ii)); nothing of the act is written."""
    e = _whole()
    _delivered(e)
    claim = e.claims.begin_validation(ROOT)
    out = _split(e, _kid("root.b", ["g"]), unmap=UNMAP_A)
    assert (out.get("refused") or out.get("error")) and "validation" in str(out) and "in flight" in str(out), out
    assert _pins(e) and not e.graph.get_task(TaskId("root.b")) and e.checks_no_longer_run(ROOT) == []
    _verdict_on_the_whole(e, "FAIL", [{"criterion": "g", "verdict": "fail", "evidence": "broke",
                                       "probe": [_cited(_the_parts_check(e), False)]}])
    e.claims.end_validation(claim)
    _split(e, _kid("root.b", ["g"]), unmap=UNMAP_A)
    (row,) = e.checks_no_longer_run(ROOT)
    assert row["rerun"] == "failing" and row["rerun_on_this_delivery"], row
    e.stop()


def test_unmap_record_of_a_run_recorded_before_the_reading_existed_says_unknown():
    e = _whole()
    _delivered(e)
    _verdict_on_the_whole(e, "PASS", [{"criterion": "g", "verdict": "pass", "evidence": "ran",
                                       "probe": [_cited(_the_parts_check(e), True)]}])
    ledger_write(e._storage, ROOT, OBSERVATIONS, [{k: v for k, v in r.items() if k != "parts_read"}
                                                  for r in observations(e._storage, ROOT)])
    e._storage.store_exec_verdict(ROOT, json.dumps({k: v for k, v in json.loads(e._storage.get_exec_verdict(ROOT)).items()
                                                    if k != "parts_read"}))
    _split(e, _kid("root.b", ["g"]), unmap=UNMAP_A)
    (row,) = e.checks_no_longer_run(ROOT)
    assert row["rerun"] == "unknown" and "never re-run" not in row["says"] and "predates" in row["says"], row
    # …and the signer reads where that record stands and what it was: the page repeats `says` verbatim
    rec = row["rerun_record"]
    where = "on this delivery" if row["rerun_on_this_delivery"] else "not re-run on this delivery"
    assert where in row["says"] and f"last record: {rec['verdict']} of {rec['ts']}" in row["says"], row
    e.stop()


def test_unmap_reaches_the_agent_over_mcp():
    e = _whole()
    srv = FastMCP("p")
    srv.add_tool(_bind(e, TL.TOOLS["decompose"]), name="decompose")
    got = {}

    async def main():
        async with create_connected_server_and_client_session(srv._mcp_server, raise_exceptions=False) as c:
            got["schema"] = next(t.inputSchema for t in (await c.list_tools()).tools if t.name == "decompose")
    try:
        anyio.run(main)
    finally:
        e.stop()
    assert "unmap" in got["schema"]["properties"], got["schema"]
