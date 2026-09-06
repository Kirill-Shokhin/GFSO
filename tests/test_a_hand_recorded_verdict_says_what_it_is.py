"""What a verdict recorded BY HAND is, and what it is not.

`record_verdict` is the door a person uses where no instrument stands — the canon's degenerate case
(§14.5: with no independent seam, the explicit record IS the guarantee). Two things a wave of testers
established about it on 2026-09-02, both about the record's honesty rather than its permission:

* the seam gate compares the reviewer's NAME to the executor's, so a name invented in the same
  breath satisfies it. That is the canon's named boundary, not a bug to be patched away — FM-3's
  false-PASS is guarded by no structural CHECK (§13.6), only by q_V at runtime. What the product
  owes is to not LAUNDER it: a record asserted by an unregistered party must say so, everywhere it
  is read, so nothing downstream can present it as an instrument's verdict.
* a verdict recorded on a node that has already settled changed nothing and said `recorded: true`,
  then directed the caller to a signal the FSM refuses.
"""
import pytest

from gfso import tools as T
from tests.support import make_engine


def _delivered(assignee="worker"):
    e = make_engine(check_interval=10_000)
    e.start()
    T.create_task(e, "n", {"description": "leaf", "criteria": [{"name": "c", "description": "C"}]},
                  assignee=assignee)
    T.signal(e, "n", "ACCEPT", assignee)
    T.signal(e, "n", "DELIVER", assignee, result="did it")
    return e


def test_a_verdict_from_an_unregistered_reviewer_is_recorded_as_asserted_not_instrumented():
    """The gate checks a name; the RECORD has to carry what kind of party stood behind it."""
    e = _delivered()
    assert T.record_verdict(e, "n", "PASS", reviewer="somebody", observed={"c": "I ran it"})["recorded"]
    v = T.get_verdict(e, "n")
    assert v["verdict"] == "PASS"
    assert v["by_hand"] is True, "a hand-recorded verdict must be legible as one"
    assert "asserted" in v["independence"].lower()
    e.stop()


def test_a_registered_instruments_verdict_is_not_marked_as_asserted():
    """…and the mark must MEAN something: an instrument's record does not carry it."""
    e = _delivered()
    e.record_exec_verdict("n", "PASS", [], "val-1",
                          per_criterion=[{"criterion": "c", "verdict": "pass", "evidence": "ran it"}])
    v = T.get_verdict(e, "n")
    assert v["verdict"] == "PASS" and v["by_hand"] is False
    e.stop()


def test_a_verdict_on_a_settled_node_is_refused_and_names_the_only_route_back():
    """`recorded: true` on a DONE node, then "signal it" — which the FSM then refuses (§14.3)."""
    e = _delivered()
    T.record_verdict(e, "n", "PASS", reviewer="somebody", observed={"c": "I ran it"})
    T.signal(e, "n", "PASS", "worker")
    assert e.get_task("n").state.name == "DONE"

    out = T.record_verdict(e, "n", "PASS", reviewer="another", observed={"c": "I ran it too"})
    assert out["recorded"] is False
    assert "DONE" in out["error"] and "reopen" in out["error"].lower()
    e.stop()


def test_a_refused_report_is_not_reported_as_never_validated():
    """A judge ran, reported, and the engine refused the report as ⊥ (§11.2) — which is not the same
    situation as nobody having looked, and it is the one that needs a decision.

    The note said "it has not been validated" while the refused report sat further down the same
    object, and a tester polled for fifteen minutes before scrolling into it (agent door,
    2026-09-02). What the reader needs first is that a decision is owed and what the two ways out are.
    """
    e = _delivered()
    e.record_rejected_report("n", "criterion 'c' carries no reproducible probe",
                             [{"criterion": "c", "verdict": "pass", "evidence": "looked at it"}])
    v = T.get_verdict(e, "n")
    assert v["verdict"] is None
    assert "REFUSED" in v["note"] and "record_verdict" in v["note"]
    assert v.get("refused_report"), "…and what it managed to observe is right there"
    e.stop()


def test_a_report_that_only_under_observes_never_becomes_a_failure():
    """"⊥ is not a pass" and it is not a FAIL either (§11.2) — the executor has nothing to fix.

    A wave read a refusal that says in so many words "this is the instrument's gap, not the
    executor's: do not send the node to rework over it" and then saw the node in REWORKING with the
    directive "the validator FAILED it". The engine's own rule is the one written here, so this is
    the pin: a report that refutes nothing and merely leaves a declared behaviour unobserved is
    REFUSED as ⊥, and nothing about the node moves.
    """
    e = _delivered()
    with pytest.raises(ValueError) as bottom:
        e.record_exec_verdict("n", "PASS", [], "val-1", require_probe=True, per_criterion=[
            {"criterion": "c", "verdict": "pass", "behaviours": ["it sorts", "it is stable"],
             "probe": [{"command": "python -c 'print(1)'", "expect": "1", "behaviour": "it sorts"}]}])
    assert "⊥" in str(bottom.value) and "do not send the node to rework" in str(bottom.value)
    assert e.get_task("n").state.name == "VALIDATING", "nothing moved: there is no verdict to move on"
    assert e.get_exec_verdict("n") is None, "…and no FAIL was written behind the refusal"
    e.stop()


def test_replacing_the_criteria_says_what_it_left_uncovered():
    """The verb that creates the obligation is the one that has to name it.

    Replacing the set dangles every criterion→child mapping it does not re-name. A caller who added
    five criteria to a root learnt — one paid review round later, from a `CHECK-1:coverage` line in a
    raw body — that all six were unmapped, including the ones they had never touched (two doors,
    2026-09-02, five rebuild calls each).
    """
    e = make_engine(check_interval=10_000)
    e.start()
    T.create_task(e, "root", {"description": "r", "criteria": [{"name": "c", "description": "C"}],
                              "accepted_risks": [{"item": "an unmodelled environment fault",
                                                  "predictability": "EXTRAORDINARY"}]},
                  assignee="agent")
    T.create_task(e, "kid", {"description": "k", "criteria": [{"name": "k1", "description": "K"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "c")

    out = T.edit_criteria(e, "root", [{"name": "c", "description": "C"},
                                      {"name": "d", "description": "a new obligation"}],
                          agent="agent")
    # …and only the NEW one: a criterion whose name survives the replacement keeps its mapping,
    # which is more than the wave's report assumed and is worth pinning as the actual behaviour.
    assert out["still_uncovered"] == ["d"]
    assert "map_criterion" in out["still_uncovered_note"]
    e.stop()
