"""The issuer's ruling that retires a validator's finding is part of his ACCEPT_CHALLENGE, names only the findings the
CHALLENGE named by id, holds while the ruled criterion reads as that act left it, and over the user's own goal is the
user's alone; a finding on a seam a merge drops keeps gating the merged child (`engine.findings`).

Measured by a critic over 868ede5, each reproduced: under AUTO the system answering a root's dispute retired a
finding on the user's own criterion; a ruling on `conf` outlived a tightened `conf`, and the validator's re-filed FAIL
was refused as "ruled outside this criterion"; a CHALLENGE naming one finding and mentioning another criterion in
passing let the acceptance retire that criterion's findings too; a finding on a seam between two merged members went
under a criterion the merged child has not, gating nothing; and the ruling, recorded after ACCEPT_CHALLENGE returned
and only while that was the node's last act, was lost — with an exception — when the dispatcher's ACCEPT came first.

A critic over 3982699 found three more: a validator's `t.c` of one round took the id of another round's `t.c`, so a
new program's FAIL was refused as a ruled finding's; the system answered an AUTO root's dispute it could not rule on,
and the finding came back until the rework bound cancelled the root; a member all of whose criteria read another member
handed its findings to no criterion of the merged child. A finding's id now carries the content of the scratch files
it ran; a dispute at an AUTO root naming a finding is the user's question (`Engine.users_dispute`).

CONTROLS: let the system move on the user's question (`system_mover`) or lock the door to the user's answer, and the
AUTO test goes red; stop lapsing rulings in `findings.rulings` and the tightening test goes red; let `ruling_defect`
take a criterion's name in place of a finding's id and the incidental-mention test goes red; map a dropped seam to
nothing in `_merged`'s `onto`, or an all-seam member to its own criteria alone, and the seam tests go red; fold the
round out of a finding's id without its files' content and the same-name test goes red; record the ruling apart from
the signal (drop `retire_findings` from the log row) and the interleaving test goes red. Each has a paired control.
"""
from __future__ import annotations

import json

import pytest

import gfso.tools as T
from gfso import issuer as I
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.core.protocol.procedure import orphaned_regression, probe_id
from gfso.core.types import Mode, Signal, SignalData, TaskId
from gfso.packets import _validator_packet
from tests.support import criterion, emptied
from tests.test_a_finding_binds_the_criterion_it_refuted import _OWN, _delivered, _id, _pinned, _refute, _seam
from tests.test_the_issuer_answers_a_dispute import _ContactLLM
from tests.test_the_mode_decides_who_holds_what import _Roster, _admit, _engine, _goal, _kid
from gfso.tools_llm import TOOLS as LOCKED
from tests.test_two_parts_that_need_each_other_are_one import _found, _ring


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _challenged_with_a_finding(e, tid: str, crit: str, reason: str = "{pid} is not {crit}'s") -> str:
    """`tid` holding one validator finding on `crit`, challenged by its executor (naming it by id, by default)."""
    cmd = "./cc wide.c; echo exit=$?"
    pid = probe_id(crit, {"command": cmd})
    e._graph._storage.store_critique(TaskId(f"{tid}#regression-probes"), json.dumps({crit: [
        {"id": pid, "behaviour": "b", "command": cmd, "as_run": cmd, "expect": "exit=0"}]}))
    t = e.graph.get_task(TaskId(tid))
    if t.state.name == "OFFERED":
        assert T.signal(e, tid, "ACCEPT", str(t.assignee))["accepted"]
    assert T.signal(e, tid, "CHALLENGE", str(t.assignee), reason=reason.format(pid=pid, crit=crit))["accepted"]
    e.wait_idle()
    return pid


def _auto_root(e):
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    e.wait_idle()


def test_a_ruling_on_the_users_own_goal_is_the_users_question(tmp_path):
    e = _engine(Mode.AUTO)
    _auto_root(e)
    pid = _challenged_with_a_finding(e, "root", "g")
    assert I.system_mover(e, _Roster(), TaskId("root"), "dispute") is None, "the system moves on the user's question"
    llm = _ContactLLM({"decision": "accept", "justification": "not g", "retire_findings": [pid]}, ran={"Bash": 1})
    out = I.answer_the_challenge(e, TaskId("root"), "agent", _llm=llm, where=str(tmp_path))
    assert out["status"] == "users" and not llm.packets, out
    (step,) = [s for s in T.next_steps(e)["steps"] if s["task_id"] == "root"]
    assert step["mine"] and "THE USER'S QUESTION" in step["directive"] and pid in step["directive"], step
    assert [p["id"] for p in e.regression_probes(TaskId("root"))["g"]] == [pid]
    # …and the user's own ruling there is his to make, through the door the mode otherwise locks
    out = LOCKED["signal"](e, "root", "ACCEPT_CHALLENGE", "agent", retire_findings=[pid], justification="not my goal")
    e.wait_idle()
    assert out["accepted"] and e.regression_probes(TaskId("root")) == {}, out
    e.stop()


def test_control_an_auto_roots_dispute_naming_no_finding_is_the_systems(tmp_path):
    e = _engine(Mode.AUTO)
    _auto_root(e)
    _challenged_with_a_finding(e, "root", "g", reason="g cannot be decided as written")
    assert I.system_mover(e, _Roster(), TaskId("root"), "dispute") == "agent"
    out = LOCKED["signal"](e, "root", "REJECT_CHALLENGE", "agent", justification="it can")
    assert not out.get("accepted"), "the customer intervened in a dispute the system answers"
    e.stop()


def test_control_the_system_rules_on_a_part_it_issued(tmp_path):
    e = _engine(Mode.AUTO)
    _goal(e)
    pid = _challenged_with_a_finding(e, "kid", "k")
    issuer = str(e.graph.issuer_of(TaskId("kid")))
    llm = _ContactLLM({"decision": "accept", "justification": "not k", "retire_findings": [pid]}, ran={"Bash": 1})
    out = I.answer_the_challenge(e, TaskId("kid"), issuer, _llm=llm, where=str(tmp_path))
    e.wait_idle()
    assert out["status"] == "accepted", out
    assert e.regression_probes(TaskId("kid")) == {}
    e.stop()


def _ruled(e) -> str:
    """kid's finding on `conf` ruled out by its issuer, the challenge naming it."""
    _refute(e, _OWN)
    gone = _id(e)
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"{gone} is libc's")
    assert T.signal(e, "kid", "ACCEPT_CHALLENGE", "me", retire_findings=[gone], justification="not conf")["accepted"]
    e.wait_idle()
    return gone


def _refiled(e):
    return e.record_exec_verdict("kid", "FAIL", ["conf"], "validator", per_criterion=[
        {"criterion": "conf", "verdict": "fail", "evidence": "wide chars rejected",
         "probe": [{"behaviour": "wide characters", "command": _OWN, "expect": "exit=0"}]}]
        + [x for x in _pinned(e) if x["criterion"] != "conf"])


def _validator_sees(e, tmp_path) -> str:
    return _validator_packet(e, e.graph.get_task(TaskId("kid")), "again", None, scratch=str(tmp_path / "r2"))


def test_a_ruling_lapses_when_its_criterion_is_rewritten(tmp_path):
    e = _seam()
    gone = _ruled(e)
    T.edit_criteria(e, "kid", [criterion("conf", "conf, and wide characters compile"), criterion("other")], agent="me")
    _delivered(e, "again")
    assert [p["id"] for p in e.regression_probes(TaskId("kid"))["conf"]] == [gone], "the ruling outlived its text"
    assert e.retired_findings(TaskId("kid")) == [] and f"RULED OUT by its issuer [{gone}]" not in _validator_sees(
        e, tmp_path)
    assert _refiled(e)["verdict"] == "FAIL", "the tightened criterion's refutation was refused as ruled out"
    e.stop()


def test_control_a_ruling_stands_while_its_criterion_reads_the_same(tmp_path):
    e = _seam()
    gone = _ruled(e)
    T.edit_criteria(e, "kid", [criterion("conf"), criterion("other", "other, reworded")], agent="me")
    _delivered(e, "again")
    assert "conf" not in e.regression_probes(TaskId("kid"))
    assert f"RULED OUT by its issuer [{gone}]" in _validator_sees(e, tmp_path)
    with pytest.raises(ValueError, match="ruled outside this criterion"):
        _refiled(e)
    e.stop()


def test_a_criterion_mentioned_in_passing_is_not_disputed():
    e = _seam()
    _refute(e, _OWN, crits=("conf", "other"))
    cid, oid = _id(e, "conf"), _id(e, "other")
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"finding {cid} is libc's scope; the other criterion is fine")
    out = T.signal(e, "kid", "ACCEPT_CHALLENGE", "me", retire_findings=[cid, oid], justification="x")
    assert not out["accepted"] and oid in out["error"], out
    assert set(e.regression_probes(TaskId("kid"))) == {"conf", "other"}
    assert e.graph.get_state(TaskId("kid")).name == "CHALLENGED"
    out = T.signal(e, "kid", "ACCEPT_CHALLENGE", "me", retire_findings=[cid], justification="libc's")   # control
    assert out["accepted"] and set(e.regression_probes(TaskId("kid"))) == {"other"}, out
    e.stop()


def test_a_bare_hash_disputes_the_probe_under_every_criterion_it_stands():
    """One probe refuted under two criteria, disputed by its bare hash: read as naming neither, each ruling on both was
    refused whole and root.tr closed by count (AUTO haiku coreutils, 2026-10-12). A full id still qualifies."""
    e = _seam()
    _refute(e, _OWN, crits=("conf", "other"))
    cid, oid = _id(e, "conf"), _id(e, "other")
    h = cid.rsplit("#", 1)[-1]
    assert h == oid.rsplit("#", 1)[-1], "one command, one hash"
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"findings {h} under conf and other ask what the spec does not")
    out = T.signal(e, "kid", "ACCEPT_CHALLENGE", "me", retire_findings=[cid, oid], justification="outside both")
    assert out["accepted"] and not e.regression_probes(TaskId("kid")), out
    e.stop()


def test_the_machine_issuer_lands_what_the_dispute_named():
    """The executor named the probe under one criterion by its full id and the other in prose; the issuer ruled on
    both. Refused whole, the same four ids came back three times; landed in part, the rest stays demanded."""
    e = _seam()
    _refute(e, _OWN, crits=("conf", "other"))
    cid, oid = _id(e, "conf"), _id(e, "other")
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"Finding [{cid}] (and the same under the other) is libc's")
    llm = _ContactLLM({"decision": "accept", "justification": "libc's", "retire_findings": [cid, oid]}, ran={"Bash": 1})
    assert I.answer_the_challenge(e, TaskId("kid"), "me", _llm=llm)["status"] == "accepted"
    assert set(e.regression_probes(TaskId("kid"))) == {"other"}
    e.stop()


def test_a_ruling_only_on_the_twin_the_dispute_did_not_name_is_told_so_not_counted_as_refused():
    """Disputed `conf#h` by full id, ruled `other#h` only: the cut read the hash against the ruling's own list and kept
    it, and the gate refused the ruling whole — a counted refusal (critic over the 10-12 cut)."""
    e = _seam()
    _refute(e, _OWN, crits=("conf", "other"))
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"Finding {_id(e, 'conf')} is libc's")
    llm = _ContactLLM({"decision": "accept", "justification": "x", "retire_findings": [_id(e, "other")]}, ran={"Bash": 1})
    out = I.answer_the_challenge(e, TaskId("kid"), "me", _llm=llm)
    assert out["status"] == "unparsed" and "did not name" in out["why"], out
    e.stop()


def test_a_finding_on_a_seam_the_merge_drops_gates_the_members_carried_criteria():
    e = _ring()
    _found(e, "root.libc", "dep__root.pp", "./cc -E pp_out.c; echo exit=$?")
    _found(e, "root.pp", "kp", "./cc -E macros.c; echo exit=$?")                    # control: not a seam
    root = e.graph.get_task(TaskId("root"))
    assert I.merge_the_refuted_cycle(e, root, str(root.assignee)) == {"status": "applied", "move": "merge"}
    e.wait_idle()
    merged = e.graph.get_task(TaskId("root.libc_pp"))
    carried = e.regression_probes(merged.id)
    assert {k: [p["carried_from"].split(":")[0] for p in v] for k, v in carried.items()} == {
        "builds (libc)": ["root.libc"], "kl": ["root.libc"], "kp": ["root.pp"]}, carried
    assert not orphaned_regression(merged.spec.criteria, carried), "a carried finding gates nothing"
    e.stop()


def _interleaved(e):
    """The dispatcher's ACCEPT for the re-offered node landing right after an accepted ACCEPT_CHALLENGE, before its
    sender reads the reply — as `send_signal_sync`'s wait allows."""
    send = e.send_signal_sync

    def with_the_dispatcher(sd, *a, **kw):
        entry = send(sd, *a, **kw)
        if sd.signal == Signal.ACCEPT_CHALLENGE and entry is not None and not entry.rejected:
            send(SignalData(signal=Signal.ACCEPT, task_id=sd.task_id, source=e.graph.get_task(sd.task_id).assignee))
        return entry
    e.send_signal_sync = with_the_dispatcher


@pytest.mark.parametrize("dispatcher", [True, False], ids=["interleaved", "control"])
def test_the_ruling_is_the_acceptance_itself(tmp_path, dispatcher):
    e = _seam()
    _refute(e, _OWN)
    gone = _id(e)
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"{gone} is libc's")
    if dispatcher:
        _interleaved(e)
    out = T.signal(e, "kid", "ACCEPT_CHALLENGE", "me", retire_findings=[gone], justification="not conf")
    e.wait_idle()
    assert out["accepted"] and "conf" not in e.regression_probes(TaskId("kid")), out
    assert e.graph.get_state(TaskId("kid")).name == ("EXECUTING" if dispatcher else "OFFERED")
    (row,) = [x for x in e.audit_log(TaskId("kid")) if x.signal == Signal.ACCEPT_CHALLENGE]
    assert row.retire_findings == (gone,), "the ruling is not on the act's own log row"
    db = SqliteStorage(str(tmp_path / "log.db"))
    db.append_audit(e._audit._to_row(row))
    assert e._audit._from_row(db.load_audit()[-1]).retire_findings == (gone,), "the ruling does not survive a restart"
    e.stop()


def _program(tmp_path, rnd: str, body: str) -> str:
    """A validator's own `t.c` in round `rnd`'s scratch, and the command that runs it."""
    (prog := tmp_path / ".gfso-scratch-d1" / rnd / "t.c").parent.mkdir(parents=True, exist_ok=True)
    prog.write_text(body)
    return f"./cc {prog.as_posix()}; echo exit=$?"


def _fails_conf(e, command):
    return e.record_exec_verdict("kid", "FAIL", ["conf"], "validator", per_criterion=[
        {"criterion": "conf", "verdict": "fail", "evidence": "it rejected the program",
         "probe": [{"behaviour": "a program", "command": command, "expect": "exit=0"}]}]
        + [x for x in _pinned(e) if x["criterion"] != "conf"])


@pytest.mark.parametrize("second", ["#define M 1\nint main(void){return M-1;}", "#include <wchar.h>\nint main(){}"],
                         ids=["another-program", "control-the-same-program"])
def test_a_finding_is_the_program_it_ran_not_the_name_it_gave_it(tmp_path, second):
    e = _seam()
    _refute(e, _program(tmp_path, "kid_1791646628", "#include <wchar.h>\nint main(){}"))
    gone = _id(e)
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"{gone} is libc's")
    T.signal(e, "kid", "ACCEPT_CHALLENGE", "me", retire_findings=[gone], justification="wide characters are libc's")
    _delivered(e, "again")
    again = _program(tmp_path, "kid_1791999999", second)
    if second.startswith("#define"):
        assert _fails_conf(e, again)["verdict"] == "FAIL", "a new program's refutation was refused as a ruled one"
        assert [p["id"] for p in e.regression_probes(TaskId("kid"))["conf"]] != [gone]
    else:
        with pytest.raises(ValueError, match="ruled outside this criterion"):
            _fails_conf(e, again)
    e.stop()


def test_a_finding_filed_under_an_id_of_before_still_gates_and_is_met_by_its_rerun():
    """Filed before content entered the id, a finding keeps its id: it is demanded, and a later round's re-run meets it."""
    e = _seam()
    cmd = "./cc .gfso-scratch-d1/kid_1791646628/t.c; echo exit=$?"
    e._graph._storage.store_critique(TaskId("kid#regression-probes"), json.dumps({"conf": [
        {"id": probe_id("conf", {"command": cmd}), "behaviour": "b", "command": cmd, "as_run": cmd,
         "expect": "exit=0"}]}))
    with pytest.raises(ValueError, match="REFUTED"):
        e.record_exec_verdict("kid", "PASS", [], "validator", per_criterion=_pinned(e))
    rerun = {"behaviour": "b", "command": cmd.replace("1791646628", "1791700000"), "expect": "exit=0"}
    report = [{**x, "probe": x["probe"] + [rerun]} if x["criterion"] == "conf" else x for x in _pinned(e)]
    assert e.record_exec_verdict("kid", "PASS", [], "validator", per_criterion=report)["verdict"] == "PASS"
    e.stop()


@pytest.mark.parametrize("libc_own", [False, True], ids=["all-seams", "control-own-criterion"])
def test_a_member_whose_criteria_all_read_another_member_hands_its_findings_to_the_merged_work(libc_own):
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "c", "criteria": [criterion("g"), criterion("h")]})
    _admit(e, "root", _kid("root.pp", ["g"], criterion("kp", "macros expand")),
           _kid("root.libc", ["h"], criterion("dep__pp", "reads pp's result", depends_on="root.pp"),
                criterion("kl", "headers parse")))
    e.add_dependency(TaskId("root.libc"), TaskId("root.pp"), discovered=True, glue="p_wide.c includes <wchar.h>")
    e.wait_idle()
    if not libc_own:      # an all-seams member is no packet the admission issues (§2.2): one stored before it held that
        emptied(e, "root.libc", seams=True)
    _found(e, "root.libc", "dep__pp", "./cc -E pp_out.c; echo exit=$?")
    root = e.graph.get_task(TaskId("root"))
    assert I.merge_the_refuted_cycle(e, root, str(root.assignee)) == {"status": "applied", "move": "merge"}
    e.wait_idle()
    merged = e.graph.get_task(TaskId("root.libc_pp"))
    # the rule reads the packet that LANDS: the merged child decides criteria of its own, whatever a member held
    assert any(not c.depends_on for c in merged.spec.criteria), merged.spec.criteria
    carried = e.regression_probes(merged.id)
    assert set(carried) == ({"kl"} if libc_own else {"kp"}), carried
    assert not orphaned_regression(merged.spec.criteria, carried), "a carried finding gates nothing"
    e.stop()
