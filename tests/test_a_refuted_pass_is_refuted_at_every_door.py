"""Asking about a node BY NAME must not get a better answer than asking about the graph.

`refuted_passes` — a node standing at PASS while its own current record says FAIL — was built on
2026-09-02 and put on the whole-graph answer only. The scoped answer, which is what `next_step(<id>)`
gives and what every signal reply carries, kept its own COMPLETE branch and never consulted it. A
stranger on the CLI door found the two surfaces contradicting each other about one node in one
second (wave 23, 2026-09-03), and it reproduced on the live server first try:

    gfso status w23atk-lazy2        -> [X] ... PASS CONTRADICTED ... frontier: NOT COMPLETE
    next_steps root_id=w23atk-lazy2 -> {"complete": true, "directive": "COMPLETE — ... "}
    next_steps (no root_id)         -> {"complete": false, "refuted_passes": ["w23atk-lazy2"]}

The door a program consumes was the one that lied — the docs tell an agent to loop on `next_steps`
until it reports complete.
"""
from __future__ import annotations

from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine


def _a_node_standing_at_pass_over_its_own_fail(e, tid="leaf"):
    """PASS signed on an honest verdict, then the instrument's real FAIL lands after the close.

    This is the shape the mechanism exists for: the late record is accepted (it is q_V's discovery
    carrier) but the node is already terminal, so the signature stays and the record contradicts it.
    """
    T.create_task(e, tid, {"description": "a leaf that claimed more than it did",
                           "criteria": [{"name": "file_exists", "description": "NEVER.txt exists"}],
                           "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                               "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    e.wait_idle()
    T.signal(e, tid, "ACCEPT", "exec-1")
    T.signal(e, tid, "DELIVER", "exec-1", result="done, I think")
    T.record_verdict(e, tid, "PASS", reviewer="judge",
                     observed={"file_exists": "ran `ls NEVER.txt` and read the listing"})
    T.signal(e, tid, "PASS", "exec-1")   # the issuer signs; the judge's record is what opens the gate
    e.wait_idle()
    assert e.get_state(TaskId(tid)).name == "DONE"
    # The ENGINE's path, not the hand door: `record_verdict` refuses a settled node outright, and
    # the case this mechanism exists for is precisely the instrument whose verdict lands after the
    # signature — accepted as evidence (it is q_V's discovery carrier), refused as a signal.
    e.record_exec_verdict(TaskId(tid), "FAIL", ["file_exists"], "instrument",
                          per_criterion=[{"criterion": "file_exists", "verdict": "fail",
                                          "evidence": "ran `ls NEVER.txt`: No such file or directory",
                                          "behaviours": ["NEVER.txt exists"]}])
    e.wait_idle()
    assert e.refuted_passes() == [tid], "the probe never produced a refuted pass at all"


def test_the_scoped_answer_refuses_complete_exactly_as_the_whole_graph_one_does():
    e = make_engine()
    e.start()
    _a_node_standing_at_pass_over_its_own_fail(e, "leaf")

    whole = e.next_steps()
    scoped = e.next_steps(TaskId("leaf"))
    v1 = e.next_step(TaskId("leaf"))

    assert whole["complete"] is False and whole["refuted_passes"] == ["leaf"]
    assert scoped["complete"] is False, (
        "asking about the node by name answered COMPLETE over a green that is not green")
    assert scoped["refuted_passes"] == ["leaf"], (
        "the name of the contradicted node has to arrive as DATA at every door that reports it")
    assert v1["complete"] is False, "next_step (v1) is the door a signal reply calls"
    e.stop()


def test_a_root_that_is_genuinely_done_still_answers_complete():
    """The negative control: this fix must not make an earned green unreachable."""
    e = make_engine()
    e.start()
    T.create_task(e, "ok", {"description": "an honest leaf",
                            "criteria": [{"name": "c", "description": "C"}],
                            "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    e.wait_idle()
    T.signal(e, "ok", "ACCEPT", "exec-1")
    T.signal(e, "ok", "DELIVER", "exec-1", result="built it")
    T.record_verdict(e, "ok", "PASS", reviewer="judge", observed={"c": "ran the check, it printed OK"})
    T.signal(e, "ok", "PASS", "exec-1")
    e.wait_idle()

    assert e.next_steps(TaskId("ok"))["complete"] is True
    assert e.next_step(TaskId("ok"))["complete"] is True
    e.stop()
