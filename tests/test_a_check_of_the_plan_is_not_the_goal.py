"""A settled part's pinned check, run on the finished whole, is a check of the plan — and the plan the system wrote stays
open to contact, the goal and a plan a person handed in do not.

GB_coreutils_tnyzqh948, 2026-11-04, AUTO: `root.dispatch` pinned `cat: not implemented` while its siblings were stubs and
settled; mapped to 17 root criteria, the pin failed each on the finished program (the system runs a part's exact pin on the
whole, `with_engine_observations`) and stood as 17 findings. The executor disputed it truly; the issuer was barred from
the ruling and could only reject, the pin could not be revised (a DONE child) and a child added beside it did not lift it,
so the root reworked to its ceiling. Retiring the finding alone stops nothing: the pin still runs.

CONTROLS: read `users_dispute` for the ruling in `answer_the_challenge`, or drop `without_pins` from
`validation.parts_procedure`, and the first test goes red; drop the handed-in check from `_system_may_lift`, or "users" from `settle`'s
stop, and the handed-in test goes red; let `runs_pin` take the command alone, or `findings_a_ruling_could_lift` skip the task's own
pins or its pinless criteria, and the goal test goes red. Each test holds its own pair: every one fails on the code before.
"""
from __future__ import annotations

import contextlib
import dataclasses as dc
import json

import pytest

import gfso.tools as T
from gfso import issuer as I
from gfso.core.protocol.procedure import probe_id, with_engine_observations
from gfso.core.types import AgentId, DoneReason, RevisionReason, State, TaskId
from gfso.tools_llm import TOOLS as LOCKED
from tests.support import criterion
from tests.test_the_issuer_answers_a_dispute import _ContactLLM
from tests.test_the_mode_decides_who_holds_what import _admit, _engine, _kid, Mode, _Roster

STUB, STUB_SAYS = "./cat </dev/null; echo rc=$?", "cat: not implemented\nrc=1"
KEPT, KEPT_SAYS = "./cat f", "x"
OWN = "./cc wide.c"
ROOT = TaskId("root")


def _pin(name, command, expect, exact=True):
    return {"name": name, "description": f"{name} holds",
            "check": [{"behaviour": name, "command": command, "expect": expect, "exact": exact}]}


def _settled(e, tid):
    e._graph.save_task(dc.replace(e.graph.get_task(TaskId(tid)), state=State.DONE, done_reason=DoneReason.PASS))


def _whole(root_criteria=None):
    """An AUTO root whose every criterion is mapped to one settled part pinning the stub check and a sound one."""
    e = _engine(Mode.AUTO)
    crits = root_criteria or [criterion("g", "G holds"), criterion("h", "H holds")]
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": crits})
    _admit(e, "root", _kid("root.part", [c["name"] for c in crits], _pin("routes", STUB, STUB_SAYS), _pin("kept", KEPT, KEPT_SAYS)))
    _settled(e, "root.part")
    return e


def _finding(crit, command=STUB, expect=" ".join(STUB_SAYS.split())):
    return {"id": probe_id(crit, {"command": command}), "behaviour": "b", "command": command, "as_run": command, "expect": expect}


def _disputed(e, *found, tid="root"):
    """`tid` holding these findings, and its executor's CHALLENGE naming each by id. Returns the ids."""
    ledger = {}
    for crit, f in found:
        ledger.setdefault(crit, []).append(f)
    e._graph._storage.store_critique(TaskId(f"{tid}#regression-probes"), json.dumps(ledger))
    t = e.graph.get_task(TaskId(tid))
    if t.state == State.OFFERED:
        assert T.signal(e, tid, "ACCEPT", str(t.assignee))["accepted"]
    ids = [f["id"] for _, f in found]
    assert T.signal(e, tid, "CHALLENGE", str(t.assignee), reason=f"{', '.join(ids)} cannot pass on correct work")["accepted"]
    e.wait_idle()
    return ids


def _rule(e, tmp_path, ids, tid=ROOT, actor="agent"):
    llm = _ContactLLM({"decision": "accept", "justification": "ran it: false on correct work", "retire_findings": ids},
                      ran={"Bash": 1})
    out = I.answer_the_challenge(e, tid, actor, _llm=llm, where=str(tmp_path))
    e.wait_idle()
    return out, llm


def _pins(e, crit, tid=ROOT):
    return {p.command for c in e.parts_procedure(tid).get(crit, ()) for p in c.check}


def _standing(e, tid=ROOT):
    return {p["id"] for ps in e.regression_probes(tid).values() for p in ps}


def _fails_seen(e):
    """Which of the root's criteria the system fails when the stub pin prints other than it pins, the rest matching."""
    t, parts = e.graph.get_task(ROOT), e.parts_procedure(ROOT)
    pins = {probe_id(c.name, p): p for cs in parts.values() for c in cs for p in c.check}
    seen = {i: {"matched": p.command != STUB, "out": "rc=0"} for i, p in pins.items()}
    report = [{"criterion": c.name, "verdict": "pass", "evidence": "ran it"} for c in t.spec.criteria]
    return {x["criterion"] for x in with_engine_observations(report, t.spec.criteria, parts, seen) if x["verdict"] == "fail"}


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def test_the_system_rules_a_stub_pin_out_of_the_whole_and_the_part_stays_as_it_settled(tmp_path):
    e = _whole()
    assert _fails_seen(e) == {"g", "h"}
    ids = _disputed(e, ("g", _finding("g")), ("h", _finding("h")))
    assert _standing(e) == set(ids) and STUB in _pins(e, "g")
    out, llm = _rule(e, tmp_path, ids)
    assert out["status"] == "accepted" and e.graph.get_state(ROOT) == State.OFFERED, out
    assert _standing(e) == set(), "the findings stayed demanded"
    assert _pins(e, "g") == _pins(e, "h") == {KEPT}, "the sound pin goes with the stub one, or the stub one still runs"
    assert _fails_seen(e) == set(), "retired alone, the finding left the pin failing every criterion on the part"
    part = e.graph.get_task(TaskId("root.part"))
    assert part.state == State.DONE and STUB in {p.command for c in part.spec.criteria for p in c.check}
    assert "only say a settled part's pinned check" in llm.packets[0] and ids[0] in llm.packets[0]
    e.stop()


def test_a_ruling_lifts_a_pin_under_the_criterion_it_names_and_for_as_long_as_its_text_stands(tmp_path):
    e = _whole()
    ids = _disputed(e, ("g", _finding("g")), ("h", _finding("h")))
    out, _ = _rule(e, tmp_path, ids[:1])
    assert out["status"] == "accepted", out
    assert _fails_seen(e) == {"h"} and _pins(e, "h") == {STUB, KEPT}, "a ruling on g spoke for h"
    t = e.graph.get_task(ROOT)
    tightened = dc.replace(t.spec, criteria=tuple(dc.replace(c, description="G, as rewritten") if c.name == "g" else c
                                                  for c in t.spec.criteria))
    e.revise(ROOT, tightened, AgentId("agent"), reason=RevisionReason.OTHER)
    e.wait_idle()
    assert _fails_seen(e) == {"g", "h"} and ids[0] in _standing(e), "a ruling outlived the text it ruled on"
    e.stop()


def test_what_names_the_goal_stays_the_persons_beside_a_pin_the_system_rules_out(tmp_path):
    """Asked to rule on all at once: the plan's check lands; the validator's own finding, the same command read his own
    way, and a pin that is a copy of the root's own stay demanded."""
    e = _whole([_pin("g", "./g", "ok"), _pin("h", "./h", "ok"), _pin("copied", KEPT, KEPT_SAYS)])
    found = [("g", _finding("g")), ("g", _finding("g", OWN, "exit=0")), ("h", _finding("h", STUB, "rc=0, its real output")),
             ("g", _finding("g", KEPT, KEPT_SAYS))]
    ids = _disputed(e, *found)
    out, _ = _rule(e, tmp_path, ids)
    assert out["status"] == "accepted", out
    assert _standing(e) == set(ids[1:]), "the system ruled on the user's goal, or not on its own check"
    assert STUB not in _pins(e, "g") and STUB in _pins(e, "h"), "a ruling lifted what it did not land on"
    # …and asked of those alone, the answer is the user's, by name, the question's door open to him
    assert T.signal(e, "root", "ACCEPT", str(e.graph.get_task(ROOT).assignee))["accepted"]
    assert T.signal(e, "root", "CHALLENGE", str(e.graph.get_task(ROOT).assignee), reason=", ".join(ids[1:]))["accepted"]
    e.wait_idle()
    out, _ = _rule(e, tmp_path, ids[1:])
    assert out["status"] == "users" and all(i in out["why"] for i in ids[1:]) and _standing(e) == set(ids[1:]), out
    (step,) = [s for s in T.next_steps(e)["steps"] if s["task_id"] == "root"]
    assert step["mine"] and "THE USER'S QUESTION" in step["directive"], step
    e.stop()


def test_a_dispute_of_the_plans_check_alone_asks_the_person_nothing_and_his_door_stays(tmp_path):
    e = _whole()
    ids = _disputed(e, ("g", _finding("g")), ("h", _finding("h")))
    (step,) = [s for s in T.next_steps(e)["steps"] if s["task_id"] == "root"]
    assert "keep waiting" in step["directive"] and "THE USER'S QUESTION" not in step["directive"], step
    out = LOCKED["signal"](e, "root", "ACCEPT_CHALLENGE", "agent", retire_findings=ids, justification="not my goal")
    e.wait_idle()
    assert out["accepted"] and _standing(e) == set() and STUB in _pins(e, "g"), "the person's ruling keeps the part's check"
    e.stop()


def test_a_plan_handed_in_is_never_changed_it_stops_with_the_signal(tmp_path):
    e = _whole()
    e.give_users_plan(ROOT)
    answers = [{"decision": "reject", "justification": "implement it"}]
    verbs = lambda answer: I.Verbs(llm=lambda m, **k: _ContactLLM(answer, ran={"Bash": 1}), busy=lambda *a: contextlib.nullcontext(),
                                   review=None, refine=None, place=lambda en, ag, n: str(tmp_path))
    ids = _disputed(e, ("g", _finding("g")), ("h", _finding("h")))
    out = I.settle(e, _Roster(), ROOT, "dispute", "agent", verbs(answers[0]))
    e.wait_idle()
    assert out["status"] == "applied" and not e.paused(), "a rejection is an answer: nothing stops"
    assert T.signal(e, "root", "CHALLENGE", str(e.graph.get_task(ROOT).assignee), reason=", ".join(ids))["accepted"]
    e.wait_idle()
    out = I.settle(e, _Roster(), ROOT, "dispute", "agent", verbs({"decision": "accept", "justification": "false", "retire_findings": ids}))
    e.wait_idle()
    assert out["status"] == "users" and e.paused() and "only the user changes a check" in out["why"], out
    assert _standing(e) == set(ids) and STUB in _pins(e, "g") and e.graph.get_state(ROOT) == State.CHALLENGED
    # …and even the person's own ruling on a finding leaves a check of his own plan to his re-plan
    assert T.signal(e, "root", "ACCEPT_CHALLENGE", "agent", retire_findings=ids, justification="not my goal")["accepted"]
    e.wait_idle()
    assert STUB in _pins(e, "g") and _standing(e) == set()
    e.stop()


def test_a_ruling_below_the_root_lifts_the_pin_there_and_for_the_whole_above_it(tmp_path):
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("mid", ["g"], criterion("m", "M holds")))
    _admit(e, "mid", _kid("leaf", ["m"], _pin("routes", STUB, STUB_SAYS), _pin("kept", KEPT, KEPT_SAYS)))
    _settled(e, "leaf")
    mid = TaskId("mid")
    ids = _disputed(e, ("m", _finding("m")), tid="mid")
    out, _ = _rule(e, tmp_path, ids, mid, str(e.graph.issuer_of(mid)))
    assert out["status"] == "accepted" and _pins(e, "m", mid) == {KEPT}, out
    _settled(e, "mid")
    assert STUB not in _pins(e, "g") and KEPT in _pins(e, "g"), "the whole above still demands what was ruled out below"
    e.stop()
