"""The Level-2 discharge floor, bisected by three doors and rebuilt to match its own message.

Waves 23–25 all ended at the same place and one of them handed over the bisection outright:

    shortest REFUSED: "no"    (2 chars)
    shortest ACCEPTED: "xy"   (2 chars)

Length was never what separated them. The rule asked whether EVERY WORD was in a blocklist, and gave
up entirely past six words — so `"The entailment does hold."`, which is the literal restatement its
own refusal message names, sailed through, as did `"This finding does not apply here."`, `"Blue
kettle."` and a paragraph of Lorem ipsum. One tester discharged thirteen findings — including three
proofs that a contract was jointly unsatisfiable — with about sixty characters of nonsense, and
`execution_admitted` flipped to true.

Two rules replace it, both on FORM and declared as such:

* a text built ENTIRELY out of the vocabulary of assent, negation and restatement says nothing about
  the plan, at any length;
* a dispute must carry three words that are not that vocabulary.

Three, not more. The shortest honest dispute in this repository's own suite — "uncertainty is about
wording, not entailment" — has exactly three, and on 2026-09-04 a stricter floor was built, run
against that suite, and reverted inside a minute: a rule that refuses honest work is worse than the
hole it closes. Filler prose of the right length still passes. That is the declared limit, and
claiming otherwise is what the old message did.
"""
from __future__ import annotations

import pytest

from gfso import tools as T
from gfso.tools import _is_pure_assent
from tests.support import UNMODELLED_FAULT, make_engine

#: verbatim from the three doors' reports
BYPASSES = ["xy", "zz", "Kettle.", "Blue kettle.", "It holds.", "The entailment does hold.",
            "It does hold.", "Not applicable.", "This finding does not apply here.",
            "This finding is incorrect and does not apply here."]

#: honest disputes — this repository's own suite, and the shortest one it contains
HONEST = ["uncertainty is about wording, not entailment",
          "k1 covers c1 through the documented contract",
          "kid's own criteria already carry both c1 and c2",
          "the obligation is carried by alpha_standalone and beta_standalone, added since"]


def _a_node_with_an_open_finding(e):
    T.create_task(e, "root", {"description": "goal",
                              "criteria": [{"name": "c1", "description": "C1"}],
                              "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                  "predictability": "EXTRAORDINARY"}]},
                  assignee="agent")
    e.wait_idle()


@pytest.mark.parametrize("why", BYPASSES)
def test_every_sentence_that_defeated_the_old_floor_is_refused(why):
    e = make_engine()
    e.start()
    _a_node_with_an_open_finding(e)

    out = T.dispute_finding(e, "root", "c1", why)

    assert out.get("refused") is True, f"{why!r} discharged a finding: {out}"
    e.stop()


@pytest.mark.parametrize("why", HONEST)
def test_and_every_honest_dispute_still_passes_the_floor(why):
    """The half that matters more: this rule was reverted once for failing exactly here."""
    e = make_engine()
    e.start()
    _a_node_with_an_open_finding(e)

    # Past the floor it meets the NEXT question — this node has no review to dispute against — and
    # that refusal, not the floor's, is what an honest sentence must reach. The distinction is the
    # whole test: being turned away at the door is not the same as being answered inside it.
    with pytest.raises(ValueError) as caught:
        T.dispute_finding(e, "root", "c1", why)

    said = str(caught.value)
    assert "no current Level-2 verdict" in said, f"the floor refused an honest dispute: {said}"
    e.stop()


def test_an_honest_short_observation_is_not_a_restatement():
    """The same predicate guards `record_verdict`, where terse truth is normal and must survive."""
    assert _is_pure_assent("no output, exit 0") is False
    assert _is_pure_assent("exit code 1 as expected") is False
    assert _is_pure_assent("ran the test and it passed") is False
    assert _is_pure_assent("ok") is True
    assert _is_pure_assent("looks green") is True


def test_the_limit_is_stated_rather_than_overclaimed():
    """Filler of the right length still passes — recorded here so nobody re-discovers it as news."""
    assert _is_pure_assent(
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor.") is False
