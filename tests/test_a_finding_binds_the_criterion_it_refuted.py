"""A validator's own finding binds the criterion it refuted until its issuer rules it outside that criterion, naming
it, and is demanded while it can run.

Measured (AUTO GB_c_compiler_tmp5cb096): root.pp passed every PINNED probe and took 35 FAILs over 271 findings, some
naming files in a past validation's pruned scratch (`root.pp_1791646628/dt/hh3.c`), `undecidable` every round. One, a
`<wchar.h>` program of a sibling's scope, the executor took for a dependency and BLOCKed on, closing a cycle the root's
split could not repair. Its way out is a CHALLENGE naming the finding, and the issuer's ruling on it (§10.2: the
signature that decides a criterion is his). Two proxies for that ruling failed (critics over f0584f3, ca228e0): the
packet's version erased every finding at a deadline extension; the criterion's text kept a disputed finding through an
accepted challenge and wiped an undisputed criterion's at a retyped full stop.

CONTROLS: make `without_retired` return the set unchanged and the ruling test goes red; key findings by the criterion's
text (drop those whose `refuted_text` differs from the text now) and the reword test goes red; let
`validation.ruling_refusal` take a ruling on any signal and the out-of-ruling test goes red; drop the existence rule of
`unrerunnable` and the vanished-file test goes red, drop the delivery exclusion and the in-delivery test goes red, cut
`{inputs:X}` alone or let a bare backslash start a path and the inputs/escape test goes red; stamp from the spec at
record time and the validated-text test goes red; give `_standing_findings` no delivery and the issuer's view test goes
red. A ruling is bounded and contacted, read, and binds the next round: let `findings.ruling_defect` skip the challenge's words,
or the machine ruling skip the contact rule, and their tests go red; take the retirement out of claim_drift's
`narrowed`, the closure's `checked_by` or `get_verdict` and the reading test goes red; drop the RULED OUT lines from the
validator packet, the round from `probe_id`, or the refusal of a re-filed finding, and the last test goes red.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timedelta

import pytest

import gfso.tools as T
from gfso import issuer as I
from gfso.core.protocol.procedure import unrerunnable
from gfso.packets import _executor_packet, _validator_packet
from gfso.core.types import AgentId, TaskId
from tests.support import REGISTER, UNMODELLED_FAULT, DENIAL_ENTRY, criterion, make_engine
from tests.test_the_issuer_answers_a_dispute import _ContactLLM, _IssuerLLM

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY", "justification": "no precedent",
          "invalidation_condition": "one occurs", "p": 0.01, "impact": "the run stops and is resumed"}, DENIAL_ENTRY]
_OWN = "./cc p_wide.c; echo exit=$?"


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _seam():
    """`kid` executed by exec-1 and issued by `me` — a seam — on two criteria, delivered."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g")], "accepted_risks": _RISK},
                  assignee="me")
    T.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "part", "criteria": [
        criterion("conf"), criterion("other")]}, "assignee": "exec-1", "covers": ["g"]}], accepted_risks=REGISTER)
    T.signal(e, "root", "ACCEPT", "me")
    _delivered(e)
    return e


def _delivered(e, result="built it"):
    if e.graph.get_state(TaskId("kid")).name == "OFFERED":
        T.signal(e, "kid", "ACCEPT", "exec-1")
    T.signal(e, "kid", "DELIVER", "exec-1", result=result)
    e.wait_idle()


def _refute(e, command, crits=("conf",), workdir=None):
    """A FAIL on `crits` by the validator's own probe `command`; the other criteria pass on their pinned checks."""
    e.record_exec_verdict("kid", "FAIL", list(crits), "validator", workdir=workdir, per_criterion=[
        {"criterion": c, "verdict": "fail", "evidence": "it rejected the program",
         "probe": [{"behaviour": "wide characters", "command": command, "expect": "exit=0"}]} for c in crits]
        + [e_ for e_ in _pinned(e) if e_["criterion"] not in crits])
    T.signal(e, "kid", "FAIL", "me", failed_criteria=list(crits))
    e.wait_idle()


def _pinned(e) -> list:
    """Each criterion passed on its pinned procedure and nothing else."""
    return [{"criterion": c.name, "verdict": "pass", "evidence": "the pinned check holds",
             "probe": [{"behaviour": p.behaviour, "command": p.command, "expect": p.expect} for p in c.check]}
            for c in e.graph.get_task(TaskId("kid")).spec.criteria]


def _pass(e, workdir=None):
    return e.record_exec_verdict("kid", "PASS", [], "validator", workdir=workdir, per_criterion=_pinned(e))


def _id(e, crit="conf") -> str:
    return e.regression_probes(TaskId("kid"))[crit][0]["id"]


def test_no_revision_retires_a_finding_only_the_issuers_ruling_naming_it_does():
    e = _seam()
    _refute(e, _OWN, crits=("conf", "other"))
    t = e.graph.get_task(TaskId("kid"))
    e.revise(t.id, t.spec, AgentId("me"), deadline=datetime.now() + timedelta(days=3))     # an extension
    T.edit_criteria(e, "kid", [criterion("conf", "conf description."), criterion("other")], agent="me")  # a retyping
    _delivered(e, "fixed it")
    assert set(e.regression_probes(TaskId("kid"))) == {"conf", "other"}
    with pytest.raises(ValueError, match="REFUTED"):
        _pass(e)
    T.signal(e, "kid", "FAIL", "me", failed_criteria=["conf"])
    gone = _id(e)
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"finding {gone} tests <wchar.h>, root.libc's scope, not conf")
    out = T.signal(e, "kid", "ACCEPT_CHALLENGE", "me", retire_findings=[gone],
                   justification="wide characters are libc's; conf asks for none")
    e.wait_idle()
    assert out["accepted"] and out["retired_findings"] == [gone], out
    assert set(e.regression_probes(TaskId("kid"))) == {"other"}, "the ruling retired more, or less, than it named"
    (r,) = e.claim_drift(TaskId("kid"))["retired_findings"]
    assert (r["id"], r["by"], r["why"]) == (gone, "me", "wide characters are libc's; conf asks for none")
    e.stop()


def test_a_finding_is_retired_by_nothing_but_that_ruling():
    e = _seam()
    _refute(e, _OWN)
    out = T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"{_id(e)} is outside conf", retire_findings=[_id(e)])
    assert not out["accepted"] and "ACCEPT_CHALLENGE only" in out["error"], out
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"{_id(e)} is outside conf")
    out = T.signal(e, "kid", "ACCEPT_CHALLENGE", "me", retire_findings=["conf#nothere"])
    assert not out["accepted"] and e.graph.get_state(TaskId("kid")).name == "CHALLENGED", out
    assert "conf" in e.regression_probes(TaskId("kid"))
    e.stop()


def test_the_machine_issuer_retires_what_its_acceptance_names():
    e = _seam()
    _refute(e, _OWN)
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"{_id(e)} is root.libc's scope")
    llm = _IssuerLLM({"decision": "accept", "justification": "<wchar.h> is libc's", "retire_findings": [_id(e)]})
    out = I.answer_the_challenge(e, TaskId("kid"), "me", _llm=llm)
    e.wait_idle()
    assert out["status"] == "accepted", out
    assert "conf" not in e.regression_probes(TaskId("kid"))
    assert "retire_findings" in llm.packets[0] and _id_text(llm.packets[0])
    e.stop()


def test_a_ruling_on_a_finding_named_by_its_bare_hash_stands():
    """Executors name a finding by its bare hash ("Probes 0f075147 and 94cafe8f"); read by the full id only, the
    issuer's ruling on it was refused (AUTO haiku coreutils, root.build, 2026-10-12)."""
    e = _seam()
    _refute(e, _OWN)
    bare = _id(e).rsplit("#", 1)[-1]
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"Finding [{bare}] is root.libc's scope")
    llm = _ContactLLM({"decision": "accept", "justification": "libc's", "retire_findings": [bare]}, ran={"Bash": 1})
    assert I.answer_the_challenge(e, TaskId("kid"), "me", _llm=llm)["status"] == "accepted"
    assert "conf" not in e.regression_probes(TaskId("kid"))
    e.stop()


def test_a_ruling_on_a_finding_its_challenge_spelled_with_underscores_stands():
    """`Dispatch_modes_and_errors#e6326df4`: the stored id has spaces and the hash follows a `#`; six rulings on it
    were refused and the node closed by count (GB_coreutils_tmsfo4636, critic r5)."""
    e = _seam()
    _refute(e, _OWN)
    bare = _id(e).rsplit("#", 1)[-1]
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"Finding the_conf_criterion#{bare} is root.libc's scope")
    llm = _ContactLLM({"decision": "accept", "justification": "libc's", "retire_findings": [_id(e)]}, ran={"Bash": 1})
    assert I.answer_the_challenge(e, TaskId("kid"), "me", _llm=llm)["status"] == "accepted"
    assert "conf" not in e.regression_probes(TaskId("kid"))
    e.stop()


def test_a_hash_two_criteria_share_is_disputed_under_both_and_the_issuer_rules_by_full_id():
    """One probe refuted two criteria (four nodes of the past rows): disputed by its bare hash it is disputed under
    both, so a ruling on either stands (root.tr, 2026-10-12); but the ruling is the act, and an issuer retiring by the
    bare hash is told the full ids to choose from — not that the probe is not demanded (critic over the 10-12 fix)."""
    e = _seam()
    _refute(e, _OWN, crits=("conf", "other"))
    bare = _id(e).rsplit("#", 1)[-1]
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"Finding [{bare}] is root.libc's scope")
    llm = _ContactLLM({"decision": "accept", "justification": "libc's", "retire_findings": [bare]}, ran={"Bash": 1})
    out = I.answer_the_challenge(e, TaskId("kid"), "me", _llm=llm)
    assert out["status"] == "unparsed" and _id(e, "conf") in out["why"] and _id(e, "other") in out["why"], out
    out = T.signal(e, "kid", "ACCEPT_CHALLENGE", "me", retire_findings=[_id(e, "other")], justification="libc's")
    assert out["accepted"] and set(e.regression_probes(TaskId("kid"))) == {"conf"}, out
    e.stop()


def test_retiring_one_criterions_finding_settles_nothing_of_the_other_the_same_probe_refuted():
    """One probe refuted two criteria — two findings; the ruling retires `conf`'s only. `other`'s still stands and is
    no settled matter, its observation kept (critic r6)."""
    e = _seam()
    _refute(e, _OWN, crits=("conf", "other"))
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"finding {_id(e)} is root.libc's scope")
    assert T.signal(e, "kid", "ACCEPT_CHALLENGE", "me", retire_findings=[_id(e)], justification="libc's")["accepted"]
    e.wait_idle()
    assert "other" in e.regression_probes(TaskId("kid"))
    packet = _executor_packet(e, e.graph.get_task(TaskId("kid")), "ws")
    assert "it rejected the program" in packet and _id(e, "other") not in str(e.rework_settled(TaskId("kid"))), packet
    e.stop()


def test_a_malformed_contract_in_an_acceptance_is_refused_not_raised():
    e = _seam()
    _refute(e, _OWN)
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason="the probe asks for root.libc's scope")
    llm = _IssuerLLM({"decision": "accept", "justification": "fixed", "criteria": ["conf"]})
    assert I.answer_the_challenge(e, TaskId("kid"), "me", _llm=llm)["status"] == "refused"
    e.stop()


def test_a_retired_finding_is_no_order_in_the_next_packet():
    """Retired by its issuer's ruling, the validator's probe is shown to the executor no more: it bound nothing, and
    no ruling could retire what was already retired (critic over this fix, tmsami100 after #47)."""
    e = _seam()
    _refute(e, _OWN)
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"finding {_id(e)} is root.libc's scope")
    T.signal(e, "kid", "ACCEPT_CHALLENGE", "me", retire_findings=[_id(e)], justification="libc's")
    e.wait_idle()
    packet = _executor_packet(e, e.graph.get_task(TaskId("kid")), "ws")
    assert _OWN not in packet and "An earlier version" not in packet, packet
    e.stop()


def test_an_acceptance_echoing_the_criteria_as_they_stand_decides_nothing():
    """Eleven acceptances re-sent the node's criteria unchanged and retired nothing; each re-offered it unchanged and it
    was challenged again (AUTO haiku coreutils, root.build, 2026-10-12). CONTROL: test only that `criteria` is
    present — the echo passes as a decision."""
    e = _seam()
    _refute(e, _OWN)
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason="the probe asks for root.libc's scope")
    echo = [criterion("conf"), criterion("other")]
    llm = _IssuerLLM({"decision": "accept", "justification": "the contract is satisfiable as written", "criteria": echo})
    assert I.answer_the_challenge(e, TaskId("kid"), "me", _llm=llm)["status"] == "unparsed"
    assert e.graph.get_state(TaskId("kid")).name == "CHALLENGED"
    e.stop()


def _id_text(packet: str) -> bool:
    return "standing on this node" in packet and "[conf#" in packet


def test_a_finding_names_the_text_it_refuted_as_validated():
    e = _seam()
    T.edit_criteria(e, "kid", [criterion("conf", "conf, rewritten while it was validated"), criterion("other")],
                    agent="me")
    _refute(e, _OWN)
    assert e.regression_probes(TaskId("kid"))["conf"][0]["refuted_text"] == "conf description"
    e.stop()


def test_a_path_under_pinned_inputs_or_an_escape_is_never_gone():
    assert unrerunnable({"as_run": "./cc {inputs:conf#1}/tests/a.c"}, ["conf#1"]) == ""
    assert unrerunnable({"as_run": r"printf '#if 1 \nowhere\x.h\n' | ./cc -E -"}, None) == ""
    assert unrerunnable({"as_run": "./cc /nowhere/at/all/a.c"}, None)


def test_the_issuer_sees_what_the_engine_demands(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    e = _seam()
    _refute(e, f"test -f {(ws / 'dist' / 'cc').as_posix()}; echo exit=$?", workdir=str(ws))
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason="dist/cc is not mine")
    said = I.issuer_context(e, TaskId("kid"), "dispute")
    assert "dist/cc" in said and "shown, not demanded" not in said, said
    e.stop()


def test_a_finding_is_demanded_while_the_file_it_names_stands_and_shown_once_it_is_gone(tmp_path):
    prog = tmp_path / ".gfso-scratch-ws" / "kid_1791646628" / "dt" / "hh3.c"
    prog.parent.mkdir(parents=True)
    prog.write_text("int main(void){return 0;}")
    e = _seam()
    _refute(e, f"./cc {prog.as_posix()}; echo exit=$?")
    _delivered(e, "fixed it")
    with pytest.raises(ValueError, match="REFUTED"):
        _pass(e)                                        # a validator's program in its scratch, still standing: it runs
    shutil.rmtree(tmp_path / ".gfso-scratch-ws")
    packet = _validator_packet(e, e.graph.get_task(TaskId("kid")), "fixed it", None, scratch=str(tmp_path / "r2"))
    assert "no longer exist here" in packet and "shown, not demanded" in packet
    assert _pass(e)["verdict"] == "PASS", "a finding no round can re-run held the node undecidable"
    e.stop()


def test_a_missing_file_inside_the_delivery_is_still_demanded(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    e = _seam()
    _refute(e, f"test -f {(ws / 'dist' / 'cc').as_posix()}; echo exit=$?", workdir=str(ws))
    _delivered(e, "fixed it")
    with pytest.raises(ValueError, match="REFUTED"):
        _pass(e, workdir=str(ws))
    e.stop()


def test_the_issuer_judging_a_challenge_sees_the_findings_standing_under_it():
    e = _seam()
    _refute(e, _OWN)
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason="p_wide.c tests <wchar.h>, root.libc's scope, not conf")
    e.wait_idle()
    said = I.issuer_context(e, TaskId("kid"), "dispute")
    assert "standing on this node" in said and _OWN in said, said
    e.stop()


def test_the_executor_is_told_a_finding_outside_its_criterion_is_a_challenge_not_a_block():
    e = _seam()
    _refute(e, _OWN)
    text = _executor_packet(e, e.graph.get_task(TaskId("kid")), None)
    assert 'status: "challenge"' in text and "not a dependency" in text
    e.stop()


def test_a_ruling_retires_only_what_the_challenge_disputed():
    e = _seam()
    _refute(e, _OWN, crits=("conf", "other"))
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"{_id(e, 'other')} asks for wide characters, root.libc's scope")
    out = T.signal(e, "kid", "ACCEPT_CHALLENGE", "me", retire_findings=[_id(e, "conf")], justification="both go")
    assert not out["accepted"] and "does not name" in out["error"], out
    out = T.signal(e, "kid", "ACCEPT_CHALLENGE", "me", retire_findings=[_id(e, "other")], justification="libc's")
    assert out["accepted"], out                        # the challenge named the finding by its id: it may go
    assert set(e.regression_probes(TaskId("kid"))) == {"conf"}
    e.stop()


def test_a_machine_ruling_that_retires_must_have_run_something(tmp_path):
    e = _seam()
    _refute(e, _OWN)
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"{_id(e)} is root.libc's scope")
    llm = _ContactLLM({"decision": "accept", "justification": "libc's", "retire_findings": [_id(e)]}, ran={"Read": 1})
    out = I.answer_the_challenge(e, TaskId("kid"), "me", _llm=llm, where=str(tmp_path))
    assert out["status"] == "uncontacted", out
    assert "conf" in e.regression_probes(TaskId("kid"))
    e.stop()


def test_a_retirement_reads_as_narrowed_wherever_the_pass_is_read():
    e = _seam()
    _refute(e, _OWN)
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"{_id(e)} is root.libc's scope")
    T.signal(e, "kid", "ACCEPT_CHALLENGE", "me", retire_findings=[_id(e)], justification="libc's")
    drift = e.claim_drift(TaskId("kid"))
    assert drift["retired_after_refutation"] == ["conf"] and drift["narrowed"] is None, drift
    assert T.get_verdict(e, "kid")["retired_after_refutation"][0]["why"] == "libc's"
    _delivered(e, "fixed it")
    _pass(e)
    T.signal(e, "kid", "PASS", "me")
    e.wait_idle()
    assert e.closure_of(TaskId("kid"))["checked_by"]["retired_after_refutation"] == ["conf"]
    e.stop()


def test_the_ruling_reaches_the_next_validator_and_a_refiled_finding_is_no_refutation(tmp_path):
    e = _seam()
    for rnd in ("kid_1791646628", "kid_1791649999"):           # the validator wrote the same program in each round
        (prog := tmp_path / ".gfso-scratch-ws" / rnd / "p_wide.c").parent.mkdir(parents=True)
        prog.write_text("#include <wchar.h>\nint main(void){return 0;}")
    first = f"./cc {(tmp_path / '.gfso-scratch-ws' / 'kid_1791646628' / 'p_wide.c').as_posix()}; echo exit=$?"
    _refute(e, first)
    gone = _id(e)
    T.signal(e, "kid", "CHALLENGE", "exec-1", reason=f"{gone} is root.libc's scope")
    T.signal(e, "kid", "ACCEPT_CHALLENGE", "me", retire_findings=[gone], justification="wide characters are libc's")
    _delivered(e, "built it again")
    packet = _validator_packet(e, e.graph.get_task(TaskId("kid")), "built", None, scratch=str(tmp_path / "r2"))
    assert f"RULED OUT by its issuer [{gone}]" in packet and "wide characters are libc's" in packet
    again = first.replace("kid_1791646628", "kid_1791649999")      # the same probe, filed from a later round
    with pytest.raises(ValueError, match="ruled outside this criterion"):
        e.record_exec_verdict("kid", "FAIL", ["conf"], "validator", per_criterion=[
            {"criterion": "conf", "verdict": "fail", "evidence": "it rejected the program",
             "probe": [{"behaviour": "wide characters", "command": again, "expect": "exit=0"}]}]
            + [x for x in _pinned(e) if x["criterion"] != "conf"])
    e.stop()
