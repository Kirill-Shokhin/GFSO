"""The surface the product tells you to poll has to know what the log already knows.

An ordinary user — not attacking anything, just shipping a 200-line script — was told by the DELIVER
reply: *"an independent validator is bound to this node and judges this delivery by itself — wait for
it (`get_verdict` reads the result)"*. They polled `get_verdict` every twenty seconds for four
minutes and got twelve identical lines of `"provenance": "none", "verdict": null`. The automatic
judging had died eleven seconds after they started. `gfso log` had already written *"validator
produced no verdict twice — the ISSUER must decide … no automatic verdict will arrive"*.

Their words: *"This is where I would have given up. The tool had pointed me at `get_verdict`, and
`get_verdict` was the one surface that didn't know."* Asked for the single change that would have
helped them most, they named this one (wave 25, 2026-09-05).

Two facts had to reach that read, and they had two different causes. The node is PARKED — the
dispatcher's deliberate "nothing more is coming" — and that was simply never rendered. And the
report a validator produced but the engine could not parse was kept NOWHERE, so the note that exists
for a refused report had nothing to fire on; under delegation the tool's caller is the dispatcher,
which reads a verdict and nothing else, so "see the validate_result output" named a place no person
could look.
"""
from __future__ import annotations

from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine


def _delivered(e, tid="leaf"):
    T.create_task(e, tid, {"description": "a leaf",
                           "criteria": [{"name": "c", "description": "C"}],
                           "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                               "predictability": "EXTRAORDINARY"}]},
                  assignee="exec-1")
    e.wait_idle()
    T.signal(e, tid, "ACCEPT", "exec-1")
    T.signal(e, tid, "DELIVER", "exec-1", result="built it")
    e.wait_idle()


def test_a_parked_node_says_so_where_the_user_was_told_to_look():
    e = make_engine()
    e.start()
    _delivered(e)
    e._validation_parked.add("leaf")          # what the dispatcher does after two ⊥ reports

    out = T.get_verdict(e, "leaf")

    assert out["automatic_validation"] == "gave up", out
    assert "Waiting is the one thing that will not work" in out["note"], out["note"]
    assert "record_verdict" in out["note"], "the way out is not named"
    e.stop()


def test_and_the_ordinary_read_is_unchanged_while_the_judging_is_alive():
    """The negative control: a node still being judged must not be told to give up on it."""
    e = make_engine()
    e.start()
    _delivered(e)

    out = T.get_verdict(e, "leaf")

    assert "automatic_validation" not in out, out
    assert "GIVEN UP" not in out["note"]
    e.stop()


def test_an_unparsed_report_is_kept_on_the_node_like_a_refused_one():
    """`record_rejected_report` is what `get_verdict`'s existing note is built from."""
    e = make_engine()
    e.start()
    _delivered(e)
    e.record_rejected_report(TaskId("leaf"),
                             "the validator's report did not parse — no verdict could be read from it",
                             None)

    out = T.get_verdict(e, "leaf")

    assert "REFUSED the report" in out["note"], out["note"]
    assert out["refused_report"]["why_it_is_not_a_verdict"].startswith(
        "the validator's report did not parse"), out
    e.stop()
