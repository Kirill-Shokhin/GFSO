"""After the coverage-discipline refusals fell to zero, THIS became the dominant wasted round.

Two honest runs on the same afternoon (2026-09-05), one through each door, drove real libraries to a
green root. Neither hit a single report refused for naming behaviours it never probed — the class
that had been 140 of 151 wasted judgements. What they hit instead, twice in one run, was a paid
judging round that produced `verdict: null` because the report **did not parse**.

One of the two diagnoses in those reports was wrong, and checking it is why this test exists: a
```json fence parses fine and always did. What does not is a report that writes a sentence and then
emits its JSON with no fence at all — `json.loads` meets the prose and fails, the engine records no
verdict, and the node waits for a judgement that was sitting in the reply.

What is recovered is a VALID object introduced by prose. Nothing is repaired: malformed JSON, an
unterminated object and a reply with no object at all all still produce no verdict, because ⊥ is not
a pass and a parser that guesses would be manufacturing one.
"""
from __future__ import annotations

from gfso.adapters.llm.structured import parse_structured

SCHEMA = {"required": ["criteria"]}

#: a probe command containing a brace inside a string — why the scan is string-aware and not a regex
REPORT = ('{"criteria": [{"criterion": "c", "verdict": "pass", '
          '"evidence": "ran `grep -c \\"^}\\" file`", "probe": []}]}')


def test_the_shape_that_cost_the_rounds():
    assert parse_structured("I ran the tests. Here is my report:\n\n" + REPORT, SCHEMA)


def test_prose_on_both_sides():
    assert parse_structured("Here you go:\n" + REPORT + "\nHope that helps.", SCHEMA)


def test_a_brace_inside_a_quoted_command_does_not_end_the_object():
    out = parse_structured(REPORT, SCHEMA)
    assert out and out["criteria"][0]["evidence"].endswith("file`")


def test_the_shapes_that_already_worked_still_do():
    assert parse_structured("```json\n" + REPORT + "\n```", SCHEMA)
    assert parse_structured(REPORT, SCHEMA)
    assert parse_structured('{"type": "object"}\n\n' + REPORT, SCHEMA), (
        "a schema echo before the real answer must not swallow it")


def test_nothing_malformed_is_rescued():
    """The half that matters more: a parser that guesses would be manufacturing a verdict."""
    assert parse_structured('{"criteria": [,,]}', SCHEMA) is None
    assert parse_structured('{"criteria": [{"criterion": "c"', SCHEMA) is None
    assert parse_structured("I could not run the tests, sorry.", SCHEMA) is None
    assert parse_structured("", SCHEMA) is None
