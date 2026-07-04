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

FENCED = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)

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
    """A dict satisfying the schema's `required` keys, or None."""
    m = FENCED.search(text or "")
    raw = m.group(1) if m else (text or "").strip()
    try:
        obj = json.loads(raw, strict=False)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    if any(k not in obj for k in schema.get("required", [])):
        return None
    return obj
