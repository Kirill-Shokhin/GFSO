"""The structured-reply parser — the one gate every LLM verdict passes through.

A verdict that fails to parse is treated as NO verdict everywhere upstream (the checkers, the
validator), and no verdict fails CLOSED. So a parser that drops a perfectly good reply is not a
cosmetic bug: it stalls the graph while looking like model failure. Observed live: a reply that
echoed the schema in one fenced block and answered in the next parsed as nothing.
"""
import json

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
    reply = 'Here is my assessment.\n\n```json\n{"verdict": "atomic", "why": "x"}\n```\n\nHope that helps.'
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



REPORT = {"type": "object", "required": ["verdict", "per_criterion"],
          "properties": {"verdict": {"type": "string"}, "seams": {"type": "string"},
                         "failed_criteria": {"type": "array", "items": {"type": "string"}},
                         "per_criterion": {"type": "array", "items": {"type": "object", "properties": {
                             "criterion": {"type": "string"}, "verdict": {"type": "string"},
                             "probe": {"type": "array", "items": {"type": "object"}}}}}}}
WHOLE = json.dumps({"verdict": "PASS", "per_criterion": [
    {"criterion": "a", "verdict": "pass", "probe": [{"command": "grep -c '^}]' f", "expect": "0"}]}],
    "seams": "none", "failed_criteria": []})


def test_a_top_key_written_inside_the_last_entry_closes_what_was_left_open():
    """The entry and `per_criterion` left open before `"seams"`: 23 of 25 unreadable batch reports kept from two rows
    (AUTO haiku coreutils), each a whole batch run again. The closers go before the comma that precedes the key."""
    o = parse_structured(WHOLE.replace("}]}], \"seams\"", "}], \"seams\""), REPORT)
    assert o == json.loads(WHOLE)


def test_a_top_key_met_inside_the_open_list_closes_the_list():
    assert parse_structured(WHOLE.replace("}]}], \"seams\"", "}]}, \"seams\""), REPORT) == json.loads(WHOLE)


def test_control_a_report_cut_short_or_with_no_sunk_key_stays_unread():
    assert parse_structured(WHOLE[:WHOLE.index("\"seams\"") - 2], REPORT) is None
    assert parse_structured(WHOLE[:-20], REPORT) is None
    # a key nested objects also declare (`verdict`) names no level: nothing is closed for it
    moved = json.dumps({"per_criterion": [{"criterion": "a", "probe": []}], "verdict": "PASS"})
    assert parse_structured(moved.replace("[]}], \"verdict\"", "[]}, \"verdict\""), REPORT) is None
