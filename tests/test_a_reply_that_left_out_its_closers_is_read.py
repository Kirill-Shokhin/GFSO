"""A structured reply that closed a probe and opened the next criterion inside the last one's `check` is read with the
closers put back where its schema places the next key: a whole plan's fold failed six calls of six that way, and no goal
was built (E3 c_compiler, own plan, 2026-10-23). A reply cut short stays unread."""
import json

from gfso.adapters.llm.structured import parse_structured

PROBE = {"type": "object", "properties": {"command": {"type": "string"}, "expect": {"type": "string"},
                                          "inputs": {"type": "object"}}}
CRIT = {"type": "object", "properties": {"name": {"type": "string"}, "check": {"type": "array", "items": PROBE}}}
SCHEMA = {"type": "object", "required": [], "properties": {
    "subtasks": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "string"}, "criteria": {"type": "array", "items": CRIT}}}},
    "root_criteria": {"type": "array", "items": CRIT}}}

WHOLE = {"subtasks": [{"id": "lex", "criteria": [
            {"name": "tokens", "check": [{"command": "r a.c", "expect": "ok", "inputs": {"a.c": "int f(int a[],int b){}"}}]},
            {"name": "errors", "check": [{"command": "r b.c", "expect": "1"}]}]}],
         "root_criteria": [{"name": "builds", "check": [{"command": "make", "expect": "0"}]}]}


def _fenced(text: str) -> str:
    return "```json\n" + text + "\n```"


def test_a_criterion_opened_inside_the_last_ones_check_is_put_back_where_it_belongs():
    text = json.dumps(WHOLE)
    broken = text.replace('"}}]}, {"name": "errors"', '"}}, {"name": "errors"', 1)   # the criterion's `]}` lost
    assert broken != text
    assert parse_structured(_fenced(broken), SCHEMA) == WHOLE


def test_a_repair_that_would_merge_two_items_into_one_reads_nothing():
    named = {"type": "object", "required": [], "properties": {
        "subtasks": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "id": {"type": "string"}, "criteria": {"type": "array", "items": CRIT}}}}}}
    whole = {"subtasks": [{"name": "A", "id": "a", "criteria": [{"name": "c", "check": [{"command": "x", "inputs": {}}]}]},
                          {"name": "B", "id": "b", "criteria": [{"name": "d", "check": [{"command": "y"}]}]}]}
    text = json.dumps(whole)
    broken = text.replace('{}}]}]}, {"name": "B"', '{}}, {"name": "B"', 1)      # B opened inside A's last criterion
    assert broken != text
    got = parse_structured(_fenced(broken), named)
    assert got is None or [s["id"] for s in got["subtasks"]] == ["a", "b"], got


def test_a_reply_cut_short_stays_unread():
    text = json.dumps(WHOLE)
    assert parse_structured(_fenced(text[: len(text) // 2]), SCHEMA) is None


def test_a_comma_before_a_closer_inside_a_string_is_the_strings():
    text = json.dumps(WHOLE).replace('"make"', '"make ,]"', 1)
    broken = text.replace('"}}]}, {"name": "errors"', '"}}, {"name": "errors"', 1)
    got = parse_structured(_fenced(broken), SCHEMA)
    assert got["root_criteria"][0]["check"][0]["command"] == "make ,]"
