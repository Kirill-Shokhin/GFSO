"""The word decided differently depending on which guard read it.

The top-level verdict travels as a string and was compared with `== Verdict.PASS`; the per-criterion
one is declared `enum: ["pass","fail","undecidable"]` and the reply parser enforces no enum. Five
sites read the per-criterion field and only one lowered it, while the top-level field in the SAME
json object is upper-case — an invitation to a model to mix them. What that bought:

* `"pass"` in the top-level field matched NEITHER arm, so every integrity check fell through as a
  no-op, the string was stored verbatim, and nothing downstream recognised it — the parent's AND
  never closed, no signal was sent, and the node sat in VALIDATING for ever WITH a verdict on it;
* `"pass"` per criterion skipped the probe-reality check, so a PASS whose probe was never run was
  RECORDED — a false PASS reachable by a letter;
* `"FAIL"` per criterion was refused for carrying no reproducible probe, so a genuine refutation
  was thrown away and the node stalled.
"""
import pytest

from gfso.core.protocol.invariants import (decided_verdict, spoken_verdict, unrun_probes,
                                           verdict_report_defects)
from gfso.core.types import Verdict

_RED = [{"criterion": "c1", "verdict": "fail", "evidence": "it broke"}]
_UNRUN = [{"criterion": "c1", "verdict": "pass", "evidence": "ok",
           "probe": {"command": "pytest -k flush", "expect": "1 passed"}}]


@pytest.mark.parametrize("word", ["PASS", "pass", "Pass", " pass "])
def test_a_pass_over_a_red_criterion_is_refused_however_it_is_spelled(word):
    assert verdict_report_defects(["c1"], word, _RED, ["c1"]), (
        f"a PASS spelled {word!r} walked past the check that its own evidence contradicts it")


@pytest.mark.parametrize("word", ["pass", "PASS", "Pass"])
def test_an_unrun_probe_is_caught_however_the_criterion_spells_its_pass(word):
    entry = [dict(_UNRUN[0], verdict=word)]
    assert unrun_probes(entry, {"Read": 3}) == ["c1"], (
        f"a criterion passing on a probe nobody ran was accepted, spelled {word!r}")


@pytest.mark.parametrize("word,want", [("PASS", Verdict.PASS), ("pass", Verdict.PASS),
                                       ("FAIL", Verdict.FAIL), (" fail ", Verdict.FAIL)])
def test_the_word_is_coerced_to_the_enum(word, want):
    assert decided_verdict(word) == want


@pytest.mark.parametrize("word", ["maybe", "", None, "PASSED", "ok"])
def test_a_third_word_is_refused_rather_than_stored(word):
    """V is two-valued (§11.2). A third word decides nothing — and stored verbatim it leaves the
    node waiting for a signal nobody can send."""
    with pytest.raises(ValueError, match="not a verdict"):
        decided_verdict(word)


def test_the_per_criterion_reader_is_one_reader():
    assert spoken_verdict("PASS") == spoken_verdict("pass") == spoken_verdict(" Pass ") == "pass"
    assert spoken_verdict(None) == ""


def test_a_fail_is_still_a_fail_in_lower_case():
    """Positive control: the coercion must not turn a refutation into something else."""
    assert not verdict_report_defects(["c1"], "fail", _RED, ["c1"])
    assert not verdict_report_defects(["c1"], Verdict.FAIL, _RED, ["c1"])
