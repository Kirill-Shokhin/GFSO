"""The engine refused the re-delivery and the frontier told the executor to deliver — same second.

Measured on a live run (2026-09-06, `http2_protocol`, arm G): the root's criteria had FAILed while
the children covering them were untouched since that FAIL, so contact refuted the DECOMPOSITION and
the gate refused a re-DELIVER — correctly. The frontier, in the same second, answered
*"AGGREGATE 'root': all its children PASSED — integrate them … DELIVER"*. The executor obeyed the
directive, was refused twice, and the run ended with the root still EXECUTING after 93 minutes and
$9.40. Advice the engine forbids is worse than no advice.

The REWORKING branch had already learnt this (2026-08-20, the same wall, three rounds). The EXECUTING
branch had not, and asked its own question a third time — so the fix is one owner for "would a
re-delivery be refused right now", asked by the rule and by both branches of the frontier.
"""
from __future__ import annotations

from gfso import tools as T
from gfso.core.types import TaskId, Verdict
from tests.support import UNMODELLED_FAULT, instrument_passes, make_engine

_RISKS = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]


def _parent_failed_over_untouched_children():
    """A root whose criterion FAILed while its only covering child stands passed and untouched."""
    e = make_engine(check_interval=10_000)
    e.start()
    T.create_task(e, "root", {"description": "the whole", "criteria": [{"name": "c1", "description": "C1 over the integrated whole"}],
                              "accepted_risks": _RISKS}, assignee="agent")
    T.create_task(e, "root.kid", {"description": "a part", "criteria": [{"name": "k1", "description": "K1"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "root.kid", "c1")
    e.wait_idle()

    T.signal(e, "root.kid", "ACCEPT", "agent")
    T.signal(e, "root.kid", "DELIVER", "agent", result="built the part; ran its check, it printed OK",
             self_validation="PASS")
    T.signal(e, "root.kid", "PASS", "agent")
    e.wait_idle()

    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="integrated the parts; ran the whole, it printed OK",
             self_validation="PASS")
    e.record_exec_verdict(TaskId("root"), Verdict.FAIL, ["c1"], "val-1",
                          per_criterion=[{"criterion": "c1", "verdict": "fail",
                                          "evidence": "ran the integrated whole: c1 does not hold",
                                          "behaviours": ["C1 holds over the whole"],
                                          "probe": [{"command": "run the whole", "expect": "C1",
                                                     "behaviour": "C1 holds over the whole"}]}])
    T.signal(e, "root", "FAIL", "agent", failed_criteria=["c1"])
    e.wait_idle()
    return e


def test_the_directive_names_the_repair_the_engine_will_accept():
    """The live shape: the plan was revised after the FAIL, so the node is EXECUTING again — and the
    gate still refuses a re-delivery, because the children covering the failed criterion were never
    touched. That is the branch the run died in; the REWORKING branch had been fixed a fortnight
    earlier and this one had not."""
    e = _parent_failed_over_untouched_children()

    # the repair the arm actually attempted: a revision that did NOT touch the failed criterion
    # (it reworded the goal), then re-accept and try to aggregate again.
    T.revise(e, "root", {"description": "the whole, restated",
                         "criteria": [{"name": "c1", "description": "C1 over the integrated whole"}],
                         "accepted_risks": _RISKS}, agent="agent")
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "agent")
    e.wait_idle()
    assert e.get_state(TaskId("root")).name == "EXECUTING", "the live shape is an EXECUTING parent"

    step = e.next_step(TaskId("root"))
    refused = T.signal(e, "root", "DELIVER", "agent", result="re-integrated, nothing else changed")

    assert refused["accepted"] is False and "refuted the DECOMPOSITION" in refused["error"], refused
    assert step["action"] != "deliver", (
        "the frontier must not advise the one signal the gate refuses — that is the wall the run "
        f"ended against; it said: {step['directive'][:120]}")
    assert "REPAIR THE PLAN" in step["directive"] and "do NOT re-deliver" in step["directive"], step


def test_a_node_the_gate_would_admit_is_still_told_to_deliver():
    """The negative control: an ordinary aggregate must keep its ordinary directive."""
    e = make_engine(check_interval=10_000)
    e.start()
    T.create_task(e, "root", {"description": "the whole", "criteria": [{"name": "c1", "description": "C1"}],
                              "accepted_risks": _RISKS}, assignee="agent")
    T.create_task(e, "root.kid", {"description": "a part", "criteria": [{"name": "k1", "description": "K1"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "root.kid", "c1")
    e.wait_idle()
    T.signal(e, "root.kid", "ACCEPT", "agent")
    T.signal(e, "root.kid", "DELIVER", "agent", result="built it; ran the check, it printed OK",
             self_validation="PASS")
    T.signal(e, "root.kid", "PASS", "agent")
    T.signal(e, "root", "ACCEPT", "agent")
    e.wait_idle()

    step = e.next_step(TaskId("root"))

    assert step["action"] == "deliver" and "AGGREGATE" in step["directive"], step
    e.stop()


def test_it_does_not_advise_a_PASS_the_plan_gate_refuses():
    """A delivered parent whose own plan has gone red is told to repair it, not to sign.

    `pass_blocked_by` is the one owner of "why a PASS here is refused whoever signs it", and the
    VALIDATING branch — the only branch that ever advises a PASS — did not consult it. The shape:
    the parent is delivered, every active child has passed (so the AND is satisfied), and a covering
    child is then CANCELled, leaving a mapping to a node that has left the decomposition. The plan
    stops passing the Syntactic level, which is the second of the three grounds `validation.py`
    refuses a PASS on and the one the affordance surface never modelled. The frontier said
    "signal PASS if every criterion holds"; every PASS came back refused.

    CONTROL: drop the `pass_blocked_by` consultation from the VALIDATING branch and this goes red
    while the ordinary-aggregate control above stays green.
    """
    e = make_engine(check_interval=10_000)
    e.start()
    T.create_task(e, "root", {"description": "the whole",
                              "criteria": [{"name": "c1", "description": "C1"},
                                           {"name": "c2", "description": "C2"}],
                              "accepted_risks": _RISKS}, assignee="agent")
    for kid, crit in (("root.kid", "c1"), ("root.other", "c2")):
        T.create_task(e, kid, {"description": "a part",
                               "criteria": [{"name": "k1", "description": "K1"}]},
                      assignee="agent", parent_id="root")
        T.map_criterion(e, "root", kid, crit)
    e.wait_idle()
    for kid in ("root.kid", "root.other"):
        T.signal(e, kid, "ACCEPT", "agent")
        T.signal(e, kid, "DELIVER", "agent", result="built it; ran the check, it printed OK")
        instrument_passes(e, TaskId(kid), "agent")
        T.signal(e, kid, "PASS", "agent")
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="assembled the parts")
    e.wait_idle()
    assert e.get_state(TaskId("root")).name == "VALIDATING"

    T.create_task(e, "root.spare", {"description": "a spare part",
                                    "criteria": [{"name": "s1", "description": "S1"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "root.spare", "c2")
    e.wait_idle()
    T.signal(e, "root.spare", "CANCEL", "agent", reason="the part is not wanted after all")
    e.wait_idle()
    assert e.get_state(TaskId("root")).name == "VALIDATING"
    assert e.pass_blocked_by(TaskId("root")) is not None

    step = e.next_step(TaskId("root"))
    assert "REPAIR THE PLAN" in (step.get("directive") or ""),         f"the frontier advised a signal the engine refuses by rule: {step.get('directive')}"
    assert "signal PASS if every criterion holds" not in (step.get("directive") or "")
    # …and the engine really would have refused it, so this is not a rule the frontier invented.
    assert T.signal(e, "root", "PASS", "agent").get("accepted") is False
    e.stop()


def test_a_recorded_verdict_is_not_hidden_behind_a_plan_repair():
    """The repair above must not out-rank a verdict already on the record.

    `pass_blocked_by` answers about a PASS; a FAIL is not gated by it. Asked first, the plan-repair
    step therefore replaced "advising a signal the engine refuses" with something worse — it hid the
    FAIL the engine ACCEPTS behind a repair the engine refuses. Measured on this shape: the two
    repairs the directive prescribed were both rejected (`map_criterion` because the child is DONE
    and a `covers` is a revision; `edit_criteria` because it would destroy coverage), while the
    suppressed `signal FAIL` was accepted and moved the node to REWORKING. A poll loop with no
    executable move.

    CONTROL: drop the `current_exec_verdict(...) is None` condition and this goes red.
    """
    e = make_engine(check_interval=10_000)
    e.start()
    T.create_task(e, "root", {"description": "the whole",
                              "criteria": [{"name": "c1", "description": "C1"},
                                           {"name": "c2", "description": "C2"}],
                              "accepted_risks": _RISKS}, assignee="agent")
    for kid, crit in (("root.kid", "c1"), ("root.other", "c2")):
        T.create_task(e, kid, {"description": "a part",
                               "criteria": [{"name": "k1", "description": "K1"}]},
                      assignee="agent", parent_id="root")
        T.map_criterion(e, "root", kid, crit)
    e.wait_idle()
    for kid in ("root.kid", "root.other"):
        T.signal(e, kid, "ACCEPT", "agent")
        T.signal(e, kid, "DELIVER", "agent", result="built it; ran the check, it printed OK")
        instrument_passes(e, TaskId(kid), "agent")
        T.signal(e, kid, "PASS", "agent")
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "agent")
    T.signal(e, "root", "DELIVER", "agent", result="assembled the parts")
    e.wait_idle()

    # an independent instrument has already judged THIS delivery, and it said FAIL
    e.record_exec_verdict(TaskId("root"), "FAIL", ["c1"], "judge",
                          per_criterion=[{"criterion": "c1", "verdict": "fail",
                                          "evidence": "ran it; c1 does not hold"},
                                         {"criterion": "c2", "verdict": "pass",
                                          "evidence": "ran it; c2 holds"}])
    # …and only then does the plan go red under it
    T.create_task(e, "root.spare", {"description": "a spare part",
                                    "criteria": [{"name": "s1", "description": "S1"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "root.spare", "c2")
    e.wait_idle()
    T.signal(e, "root.spare", "CANCEL", "agent", reason="not wanted after all")
    e.wait_idle()
    assert e.pass_blocked_by(TaskId("root")) is not None, "the shape needs a blocked PASS"

    step = e.next_step(TaskId("root"))
    assert "SIGN THE VERDICT" in (step.get("directive") or ""), \
        f"the recorded verdict was hidden behind a plan repair: {step.get('directive')}"
    # …and the engine really does accept it, so the step is executable.
    assert T.signal(e, "root", "FAIL", "agent", failed_criteria=["c1"]).get("accepted") is True
    e.stop()
