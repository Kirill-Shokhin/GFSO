"""A structured reply that does not parse is asked again WITH what failed — told only "could not be parsed", a model
re-emitted the same malformed fold six calls of six (E3 c_compiler, own plan, 2026-10-23)."""
import json

from gfso.adapters.llm.headless import ClaudeCodeProvider
from gfso.adapters.llm.structured import RETRY_SUFFIX, retry_suffix

SCHEMA = {"type": "object", "required": ["subtasks", "root_criteria"]}


def test_an_invalid_reply_is_told_the_error_and_where():
    fold = json.dumps({"subtasks": [{"check": [{"command": "x", "inputs": {"a.c": "int main(){}"}}]}], "root_criteria": []})
    broken = fold.replace("}]}]", "}]]", 1).replace(", ", ",\n", 1)      # a criterion's closer lost, as measured
    said = retry_suffix("```json\n" + broken + "\n```", SCHEMA)
    assert said.startswith(RETRY_SUFFIX) and "line 2" in said and "root_criteria" in said and "close every array" in said


def test_a_reply_missing_keys_is_told_which():
    assert "root_criteria" in retry_suffix('```json\n{"subtasks": []}\n```', SCHEMA).split("required keys:")[1]


def test_a_valid_complete_reply_adds_nothing():
    assert retry_suffix('```json\n{"subtasks": [], "root_criteria": []}\n```', SCHEMA) == RETRY_SUFFIX


def test_the_headless_port_asks_again_with_it():
    port = object.__new__(ClaudeCodeProvider)
    port.calls, asked = [], []
    replies = iter(['```json\n{"subtasks": [}\n```', '```json\n{"subtasks": [], "root_criteria": []}\n```'])
    port._call = lambda system, user, *a, **k: asked.append(user) or next(replies)
    assert port.complete_structured("s", "u", SCHEMA) == {"subtasks": [], "root_criteria": []}
    assert "The JSON is invalid" in asked[1]
