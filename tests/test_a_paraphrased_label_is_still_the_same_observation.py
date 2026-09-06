"""A present, run probe was refused because its label was a paraphrase — and the refusal said the
report "names behaviours it never observed", which was false about it.

HTTP door, wave 27 (2026-09-06). The validator probed `module_location` with
`python -c "…os.path.abspath('ratelimit.py')"`, labelled that probe *"ratelimit.py exists at exactly
the target path"*, and had listed the behaviour as *"…exists at exactly
C:/Users/…/gfso-wave27/http/ratelimit.py"*. Same fact, same command. The coverage rule measured the
shared words against the BEHAVIOUR's own word set — inflated by the absolute path — scored 4/13, and
threw away a fully evidenced PASS. Cost: one wasted run at $0.24 and a retry on a model three times
dearer, which the product's own advice recommended.

The rule stays: an unobserved conjunct cannot carry a pass (§11.2), and that is what the demotion is
for. What changes is that the overlap is measured against the SHORTER side, with a floor so a
two-word label cannot match everything — and the demotion now says which labels the link was sought
in, so a wording gap is legible as one instead of reading as missing evidence.
"""
from __future__ import annotations

from gfso.core.protocol.invariants import probe_labels, underprobed

_PATH = "C:/Users/kasho/AppData/Local/Temp/gfso-wave27/http/ratelimit.py"


def _entry(behaviours, label, criterion="module_location"):
    return [{"criterion": criterion, "verdict": "pass", "evidence": "ran it",
             "behaviours": behaviours,
             "probe": [{"command": "python -c \"import os; print(os.path.abspath('ratelimit.py'))\"",
                        "expect": _PATH, "behaviour": label}]}]


def test_the_measured_case_is_no_longer_refused():
    said = _entry([f"ratelimit.py exists at exactly {_PATH}"],
                  "ratelimit.py exists at exactly the target path")

    assert underprobed(said) == {}, (
        "the probe is present, ran, and observes the behaviour — the words differ because one side "
        "carries the literal path")


def test_an_unrelated_label_still_leaves_the_behaviour_unobserved():
    """The negative control, and the reason the rule exists at all."""
    said = _entry(["the bucket refills continuously between calls"],
                  "the module imports without error")

    assert underprobed(said) == {"module_location": ["the bucket refills continuously between calls"]}


def test_a_two_word_label_cannot_stand_in_for_everything():
    """The floor: measuring against the shorter side must not make a stub label match any behaviour."""
    said = _entry(["the bucket refuses a cost larger than its capacity"], "it works")

    assert said and underprobed(said), "a label with nothing in it observes nothing"


def test_the_labels_are_reported_beside_the_miss():
    """So a reader can see a WORDING gap for what it is, rather than as missing evidence."""
    said = _entry(["the bucket refills continuously between calls"],
                  "the module imports without error")

    assert probe_labels(said) == {"module_location": ["the module imports without error"]}


def test_several_behaviours_under_one_fused_label_still_pass():
    """The case the earlier loosening was built for, kept: one command honestly observing two facts."""
    said = _entry(["pytest exits 0", "at least 1 test collected and run"],
                  "pytest exits 0 with >=1 test collected and run")

    assert underprobed(said) == {}
