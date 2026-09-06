"""Provider-agnostic structured-output machinery — OURS, not the transport's.

No provider is trusted to enforce a schema: the instruction appends the JSON schema to the user
content, and `parse` validates the reply (fenced block preferred, strict=False tolerates literal
control chars inside strings — the dominant LLM-JSON defect). Every LLMProviderPort adapter
(headless Anthropic, generic OpenAI-compatible) composes these same three pieces, which is what
makes the one-shot layer provider-portable by construction.
"""
from __future__ import annotations

import json
import re

# Every fenced block, each matched up to its OWN closing fence. A greedy single match spanned from
# the first fence to the last, so a reply that emitted more than one block (observed live: models
# echo the schema, then answer) parsed as nothing — and a checker with no verdict is a checker that
# silently fails closed. Blocks are tried in order; the first that satisfies the schema wins.
FENCED = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

RETRY_SUFFIX = ("\n\nYour previous output could not be parsed against the schema "
                "(missing required keys or invalid JSON). Re-emit the ONE fenced json "
                "object, complete and valid.")


def schema_instruction(schema: dict) -> str:
    """The sentence appended to a prompt that makes the model answer in a schema we can parse.

    One owner, because every verb that reads structure appends it: two spellings would be two
    contracts with the model, and the parse failure they cause is charged to the caller's round."""
    return (
        "\n\n# OUTPUT FORMAT (mechanical requirement, not content guidance)\n"
        "Return your answer as ONE fenced ```json code block containing a single object that conforms "
        "to this JSON schema (every `required` key present, exact key names):\n"
        f"```json\n{json.dumps(schema)}\n```"
    )


def _bare_objects(text: str) -> list:
    """Every top-level `{...}` in the text, brace-balanced and string-aware, outermost first.

    Not a JSON parser and not a repairer: it only decides where an object STARTS and ENDS so the
    real parser can be handed a clean candidate. A quoted brace inside a probe command
    (`grep -c "^}" file`) is exactly why this counts strings and escapes rather than regexing.
    """
    out, i, n = [], 0, len(text)
    while True:
        start = text.find("{", i)
        if start < 0:
            return out
        depth, j, in_str, esc = 0, start, False, False
        while j < n:
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    out.append(text[start:j + 1])
                    break
            j += 1
        if depth != 0:                     # unterminated: nothing further can balance either
            return out
        i = j + 1


def parse_structured(text: str, schema: dict):
    """The FIRST candidate in the reply that is a dict carrying the schema's `required` keys, or None.

    Candidates: each fenced block in order, then the bare text. Trying them all is what makes a
    schema-echo (or any preamble block) harmless — it parses as JSON but lacks the required keys, so
    it is skipped rather than swallowing the real answer."""
    # …AND THE FIRST BALANCED OBJECT IN THE BARE TEXT, which is the shape that actually cost
    # money. Fenced blocks were handled and so was a bare payload; what was not is a report that
    # writes a sentence first and then emits its JSON WITHOUT a fence — `json.loads` sees the
    # prose and fails, the engine records no verdict, and the node waits for a judgement that
    # was sitting in the reply. Measured on two honest runs the same afternoon (2026-09-05):
    # after the coverage-discipline refusals fell to zero, THIS became the dominant reason a
    # paid judging round decided nothing — two of the two runs hit it, one twice.
    # Balanced braces, string-aware: a substring found by regex would split on the first `}`
    # inside a quoted probe command. Malformed JSON still fails — what is recovered is a VALID
    # object that happened to be introduced by prose, never a repaired one.
    candidates = ([m.group(1) for m in FENCED.finditer(text or "")]
                  + [(text or "").strip()] + _bare_objects(text or ""))
    for raw in candidates:
        try:
            obj = json.loads(raw, strict=False)
        except Exception:
            continue
        if isinstance(obj, dict) and all(k in obj for k in schema.get("required", [])):
            return obj
    return None
