"""The decompose loop — SEARCH (text recall) ↔ AUDIT (one structured output: prose + graph spec).

Reproduces the E2 reference-method as a callable. SEARCH is a plain-text exhaustive hole-hunt; AUDIT is a
single forced-structured call whose `basis_markdown` field is the canonical decomposition in WORDS (the
durable D artifact, written first so prose quality is preserved) and whose remaining fields are that same
decomposition AS structure (D/Dep/V/N) — the audit is GFSO-aware, so it self-transcribes; there is no
separate naive transcriber.

A decomposition function is **single-level by definition**: it decomposes ONE node into its children.
Recursion = call it again on a child. The flat spec (root criteria + subtasks + mappings + deps + neglected)
is therefore the correct one-level encoding; deeper trees are separate calls. `depth` is the iteration
count of the search↔audit refinement (the depth-of-working-through dial), not tree depth.
"""
from __future__ import annotations

from pathlib import Path

from gfso.adapters.llm.claude import ClaudeLLM

_PROMPTS = Path(__file__).parent / "prompts"
SEARCH_PROMPT = (_PROMPTS / "search.md").read_text(encoding="utf-8")
AUDIT_PROMPT = (_PROMPTS / "audit.md").read_text(encoding="utf-8")

MODELS = {"haiku": "claude-haiku-4-5-20251001", "sonnet": "claude-sonnet-4-6", "opus": "claude-opus-4-8"}

_NAME_DESC = {"type": "object", "properties": {
    "name": {"type": "string"}, "description": {"type": "string"}}, "required": ["name", "description"]}

# AUDIT structured output: a PROSE field (the quality artifact) + the same decomposition as graph spec.
AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "basis_markdown": {"type": "string", "description":
            "The COMPLETE canonical basis decomposition in prose markdown — the durable artifact: D "
            "components, Dep seams (direction + glue), V criteria (spanning invariants and node-local), N "
            "scope-exclusions. Write this fully and carefully FIRST; the structured fields below are its "
            "faithful, LOSSLESS transcription — drop nothing, add nothing, every prose item appears once "
            "in the structure and vice versa."},
        "name": {"type": "string", "description":
            "A SHORT title (≤6 words) for the whole node — the UI label; the request text is the full description."},
        "root_criteria": {"type": "array", "description":
            "The SPANNING invariants — V criteria that span multiple subtasks / belong to the whole node.",
            "items": _NAME_DESC},
        "subtasks": {"type": "array", "description":
            "The D components. Each: a stable snake_case id, a SHORT name (≤6 words, the node title), a fuller "
            "description, and its own node-local criteria (boundary-state / single-component V items it owns).",
            "items": {"type": "object", "properties": {
                "id": {"type": "string"}, "name": {"type": "string"}, "description": {"type": "string"},
                "criteria": {"type": "array", "items": _NAME_DESC}},
                "required": ["id", "name", "description", "criteria"]}},
        "mappings": {"type": "array", "description":
            "Coverage: which subtask establishes which root criterion (every root criterion → >=1 subtask; "
            "every subtask → >=1 mapping).",
            "items": {"type": "object", "properties": {
                "criterion": {"type": "string"}, "child_id": {"type": "string"}},
                "required": ["criterion", "child_id"]}},
        "deps": {"type": "array", "description":
            "Dep seams: {from: producer subtask id, to: consumer subtask id, glue: the seam truth-maker}.",
            "items": {"type": "object", "properties": {
                "from": {"type": "string"}, "to": {"type": "string"}, "glue": {"type": "string"}},
                "required": ["from", "to", "glue"]}},
        "neglected": {"type": "array", "description":
            "N scope-exclusions. predictability: EXTRAORDINARY = out-of-goal scope-exclusion (the usual "
            "case); ORDINARY = an in-domain predictable risk that must be mitigated; STATISTICAL = aggregate.",
            "items": {"type": "object", "properties": {
                "item": {"type": "string"},
                "predictability": {"type": "string", "enum": ["ORDINARY", "STATISTICAL", "EXTRAORDINARY"]},
                "justification": {"type": "string"}, "invalidation": {"type": "string"}},
                "required": ["item", "justification"]}},
    },
    "required": ["name", "basis_markdown", "root_criteria", "subtasks", "mappings", "deps", "neglected"],
}


def _search(llm: ClaudeLLM, request: str, prev_md: str) -> str:
    if prev_md:
        user = (f"# TASK\n{request}\n\n# CURRENT DECOMPOSITION\n{prev_md}\n\n"
                "A current decomposition is provided — find everything it is still missing or wrongly "
                "scoped (only genuinely new holes, each with its falsifier).")
    else:
        user = f"# TASK\n{request}\n\nFirst pass: no decomposition is provided — produce the exhaustive enumeration."
    return llm.complete(user, SEARCH_PROMPT)


def _audit(llm: ClaudeLLM, request: str, prev_md: str, holes: str) -> dict:
    if prev_md:
        user = (f"# TASK\n{request}\n\n# CURRENT DECOMPOSITION\n{prev_md}\n\n# NEW HOLES TO FOLD IN\n{holes}\n\n"
                "Fold the new holes into the current decomposition and re-emit the FULL canonical basis — "
                "as `basis_markdown` (prose) AND the structured fields (its lossless transcription).")
    else:
        user = (f"# TASK\n{request}\n\n# EXHAUSTIVE ENUMERATION TO REDUCE\n{holes}\n\n"
                "Reduce this to the canonical basis — emit it as `basis_markdown` (prose) AND the structured "
                "fields (its lossless transcription).")
    return llm.complete_structured(AUDIT_PROMPT, user, AUDIT_SCHEMA)


def decompose_spec(request: str, depth: int = 1, model: str = "sonnet",
                   llm: ClaudeLLM | None = None) -> dict:
    """Run search↔audit `depth` times; return the final AUDIT structured dict (basis_markdown + spec)."""
    llm = llm or ClaudeLLM(model=MODELS.get(model, model))
    prev_md, spec = "", {}
    for _ in range(max(1, depth)):
        holes = _search(llm, request, prev_md)
        spec = _audit(llm, request, prev_md, holes) or {}
        prev_md = spec.get("basis_markdown", "")
    return spec


def decompose_text(request: str, depth: int = 1, model: str = "sonnet",
                   llm: ClaudeLLM | None = None) -> str:
    """Just the markdown basis (the D artifact)."""
    return decompose_spec(request, depth=depth, model=model, llm=llm).get("basis_markdown", "")
