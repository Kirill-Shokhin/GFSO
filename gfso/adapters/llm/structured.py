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
    return (
        "\n\n# OUTPUT FORMAT (mechanical requirement, not content guidance)\n"
        "Return your answer as ONE fenced ```json code block containing a single object that conforms "
        "to this JSON schema (every `required` key present, exact key names):\n"
        f"```json\n{json.dumps(schema)}\n```"
    )


def parse_structured(text: str, schema: dict):
    """The FIRST candidate in the reply that is a dict carrying the schema's `required` keys, or None.

    Candidates: each fenced block in order, then the bare text. Trying them all is what makes a
    schema-echo (or any preamble block) harmless — it parses as JSON but lacks the required keys, so
    it is skipped rather than swallowing the real answer."""
    candidates = [m.group(1) for m in FENCED.finditer(text or "")] + [(text or "").strip()]
    for raw in candidates:
        try:
            obj = json.loads(raw, strict=False)
        except Exception:
            continue
        if isinstance(obj, dict) and all(k in obj for k in schema.get("required", [])):
            return obj
    return None
