"""The structured-reply parser — the one gate every LLM verdict passes through.

A verdict that fails to parse is treated as NO verdict everywhere upstream (the checkers, the
validator), and no verdict fails CLOSED. So a parser that drops a perfectly good reply is not a
cosmetic bug: it stalls the graph while looking like model failure. Observed live: a reply that
echoed the schema in one fenced block and answered in the next parsed as nothing.
"""
from gfso.adapters.llm.structured import parse_structured, schema_instruction

SCHEMA = {"type": "object",
          "properties": {"verdict": {"type": "string"}, "why": {"type": "string"}},
          "required": ["verdict", "why"]}


def test_plain_fenced_block():
    assert parse_structured('```json\n{"verdict": "atomic", "why": "one obligation"}\n```',
                            SCHEMA)["verdict"] == "atomic"


def test_bare_json_without_a_fence():
    assert parse_structured('{"verdict": "separable", "why": "two"}', SCHEMA)["verdict"] == "separable"


def test_schema_echo_before_the_answer_is_skipped():
    """The live defect: two fenced blocks. The first parses as JSON but carries no required key —
    it must be skipped, not swallow the reply (a greedy match spanned both and parsed neither)."""
    reply = ('```json\n' + str(SCHEMA).replace("'", '"') + '\n```\n\n'
             '```json\n{"verdict": "atomic", "why": "one obligation probed by several inputs"}\n```')
    parsed = parse_structured(reply, SCHEMA)
    assert parsed is not None and parsed["verdict"] == "atomic"


def test_prose_around_the_block():
    reply = 'Here is my judgement.\n\n```json\n{"verdict": "atomic", "why": "x"}\n```\n\nHope that helps.'
    assert parse_structured(reply, SCHEMA)["why"] == "x"


def test_missing_required_key_is_no_verdict():
    assert parse_structured('```json\n{"verdict": "atomic"}\n```', SCHEMA) is None


def test_unparseable_is_no_verdict():
    assert parse_structured("I think it is atomic.", SCHEMA) is None
    assert parse_structured("", SCHEMA) is None


def test_nested_object_survives_the_non_greedy_match():
    reply = ('```json\n{"verdict": "separable", "why": "two", '
             '"concerns": [{"name": "a", "criteria": ["c1"]}]}\n```')
    assert parse_structured(reply, SCHEMA)["concerns"][0]["name"] == "a"


def test_instruction_carries_the_schema():
    assert '"required"' in schema_instruction(SCHEMA)
