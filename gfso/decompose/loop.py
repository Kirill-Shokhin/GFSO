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

import sys
from pathlib import Path

from gfso.core.types import LLMProviderPort


def _progress(msg: str, cb=None) -> None:
    """Human-visible pipeline progress. Always STDERR (stdout is the MCP stdio channel and must stay
    clean); `cb(msg)` additionally forwards to a transport-side channel (e.g. MCP progress
    notifications) when one is wired."""
    print(f"[decompose] {msg}", file=sys.stderr, flush=True)
    if cb is not None:
        try:
            cb(msg)
        except Exception:
            pass  # progress is presentation — it must never break the pipeline


def _tag(llm, stage: str) -> None:
    """Label the llm's last call with its stage (duck-typed: only stat-collecting adapters have tag_last)."""
    if hasattr(llm, "tag_last"):
        llm.tag_last(stage)


def _stat_line(llm) -> str:
    """One-line cost readout of the llm's LAST call + the running total. Duck-typed on `calls`
    holding stat DICTS (the headless adapter); anything else (fakes, API adapter) → plain 'done'."""
    calls = getattr(llm, "calls", None)
    if not calls or not isinstance(calls[-1], dict):
        return "done"
    c = calls[-1]
    dicts = [x for x in calls if isinstance(x, dict)]
    total = sum((x.get("output_tokens") or 0) for x in dicts)
    retries = sum(1 for x in dicts if x.get("parse_failed"))
    secs = (c.get("duration_ms") or 0) / 1000
    line = (f"done in {secs:.0f}s · {(c.get('output_tokens') or 0) / 1000:.1f}k tokens "
            f"· Σ {total / 1000:.1f}k tokens")
    return line + (f" · ⚠ {retries} parse-retry" if retries else "")


def _hint(llm, stage: str) -> None:
    """Tell the adapter which stage is about to run, so its live token ticks carry the stage name."""
    if hasattr(llm, "stage_hint"):
        llm.stage_hint = stage


def _spec_line(spec: dict) -> str:
    """Shape readout of a structured spec (what is about to be built)."""
    return (f"spec: {len(spec.get('subtasks', []))} subtasks · {len(spec.get('deps', []))} seams · "
            f"{len(spec.get('root_criteria', []))} root criteria · {len(spec.get('neglected', []))} risks")

_PROMPTS = Path(__file__).parent / "prompts"
SEARCH_PROMPT = (_PROMPTS / "search.md").read_text(encoding="utf-8")
AUDIT_PROMPT = (_PROMPTS / "audit.md").read_text(encoding="utf-8")

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
            "in the structure and vice versa — with ONE principled exception: N scope-BOUNDARY items "
            "(no materialization probability) stay in this prose and shape how root_criteria are drawn; "
            "only genuine risk EVENTS transcribe into `neglected`."},
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
            "The RISK REGISTER — ONLY uncertain EVENTS with a real materialization probability that this "
            "decomposition ignores. predictability verdict per event: STATISTICAL = P estimable but rare "
            "(justification must state why neglecting is acceptable); EXTRAORDINARY = genuinely "
            "unprecedented (no precedent AND not derivable from known models); ORDINARY events may NOT be "
            "neglected — they must be a subtask instead. A deliberate SCOPE BOUNDARY (a capability the goal "
            "does not include) is NOT a risk — it has no P: keep it in basis_markdown's N section and "
            "encode it in how root_criteria are drawn; do NOT put it here.",
            "items": {"type": "object", "properties": {
                "item": {"type": "string"},
                "predictability": {"type": "string", "enum": ["STATISTICAL", "EXTRAORDINARY"]},
                "justification": {"type": "string"},
                "invalidation": {"type": "string", "description": "when to revisit this neglect"}},
                "required": ["item", "predictability", "justification", "invalidation"]}},
    },
    "required": ["name", "basis_markdown", "root_criteria", "subtasks", "mappings", "deps", "neglected"],
}


def _lean_schema() -> dict:
    """AUDIT_SCHEMA without the prose `basis_markdown` field — the LEAN final: the double emission
    (prose basis + its structured transcription in one output) is the pipeline's cost center; in lean
    mode the graph is the artifact (at depth≥2 the carried prose basis from the intermediate rounds is
    still returned as d_md). Scope boundaries stay encoded in how root_criteria are drawn."""
    import copy
    s = copy.deepcopy(AUDIT_SCHEMA)
    del s["properties"]["basis_markdown"]
    s["required"] = [k for k in s["required"] if k != "basis_markdown"]
    s["properties"]["neglected"]["description"] = s["properties"]["neglected"]["description"].replace(
        "keep it in basis_markdown's N section and encode it in", "encode it in")
    return s


AUDIT_SCHEMA_LEAN = _lean_schema()

# The repair call PATCHES: every field optional — the corrective audit re-emits ONLY what it changes
# (a full-spec re-emission on a 16-subtask graph cost 33.7k output tokens / 312s, observed live).
AUDIT_SCHEMA_PATCH = {**AUDIT_SCHEMA_LEAN, "required": []}


_COVERED = "ALREADY-COVERED"

# `fast` pace-suffixes — USER-content additions (frozen prompt CORES untouched; same sanctioned class
# as the ALREADY-COVERED sentinel). Measured on the wordfreq simple task (runs/v2_speed/suffix_*.json):
# baseline 106s/9.8k out → both suffixes 63-77s/5.6-7.4k out, holes==[], 0 repairs, shape parity
# (the audit suffix MUST carry the keep-NEGLECTED clause — without it the register got dropped → repair).
# ⚠ SIMPLE TASKS ONLY — measured on the complex T01 reference (2026-07-04): 2× cheaper (325s/32k →
# 167s/17k) but coverage −9/45 on the basis (35→26; V-criteria content is what compresses away).
SEARCH_FAST = ("Pace note: this is a SIMPLE task — keep the enumeration TIGHT: one short line per "
               "hole/component (its falsifier in a few words), no derivations, no re-verification "
               "prose, no closing narration. Completeness of ITEMS matters; wordiness does not.")
AUDIT_FAST = ("Pace note: this is a SIMPLE task — write the basis TIGHTLY: short prose lines, no "
              "coverage narration or self-check text (the structure carries the checks). Names "
              "EXACT and lossless between prose and structure — drop nothing; the NEGLECTED risk "
              "register stays COMPLETE (each risk with its predictability verdict, justification, "
              "invalidation).")


def _search(llm: LLMProviderPort, request: str, prev_md: str, fast: bool = False) -> str:
    if prev_md:
        # The sentinel is an I/O-FORMAT convention only: the frozen prompt already mandates "say so
        # explicitly rather than manufacturing holes" — this fixes the wording so the loop can detect it.
        user = (f"# TASK\n{request}\n\n# CURRENT DECOMPOSITION\n{prev_md}\n\n"
                "A current decomposition is provided — find everything it is still missing or wrongly "
                "scoped (only genuinely new holes, each with its falsifier). If, per your rules, the real "
                f"requirement space is already covered, begin your reply with the single line {_COVERED}.")
    else:
        user = f"# TASK\n{request}\n\nFirst pass: no decomposition is provided — produce the exhaustive enumeration."
    if fast:
        user += "\n\n" + SEARCH_FAST
    return llm.complete(user, SEARCH_PROMPT)


def _audit_text(llm: LLMProviderPort, request: str, prev_md: str, holes: str) -> str:
    """An INTERMEDIATE audit round: fold + re-emit the canonical basis as PROSE ONLY (the carried .md
    state). The structured spec is emitted once, on the FINAL round — intermediate structure would be
    thrown away, and the graph must never receive a half-converged plan."""
    user = (f"# TASK\n{request}\n\n"
            + (f"# CURRENT DECOMPOSITION\n{prev_md}\n\n# NEW HOLES TO FOLD IN\n{holes}\n\n"
               if prev_md else f"# EXHAUSTIVE ENUMERATION TO REDUCE\n{holes}\n\n")
            + "Re-emit the FULL canonical basis decomposition as prose markdown (D components, Dep seams "
              "with direction + glue, V criteria, N scope-exclusions, then the basis width). Prose only — "
              "no structured transcription on this round.")
    return llm.complete(user, AUDIT_PROMPT)


def _audit(llm: LLMProviderPort, request: str, prev_md: str, holes: str, emit_basis: bool = False,
           fast: bool = False) -> dict:
    prose = ("as `basis_markdown` (prose) AND the structured fields (its lossless transcription)"
             if emit_basis else
             "as the structured fields ONLY — a faithful, LOSSLESS transcription into the schema "
             "(no prose re-emission; drop nothing, every basis item appears once in the structure)")
    if prev_md:
        user = (f"# TASK\n{request}\n\n# CURRENT DECOMPOSITION\n{prev_md}\n\n# NEW HOLES TO FOLD IN\n{holes}\n\n"
                f"Fold the new holes into the current decomposition and re-emit the FULL canonical basis — {prose}.")
    else:
        user = (f"# TASK\n{request}\n\n# EXHAUSTIVE ENUMERATION TO REDUCE\n{holes}\n\n"
                f"Reduce this to the canonical basis — emit it {prose}.")
    if fast:
        user += "\n\n" + AUDIT_FAST
    return llm.complete_structured(AUDIT_PROMPT, user, AUDIT_SCHEMA if emit_basis else AUDIT_SCHEMA_LEAN)


def _audit_fix(llm: LLMProviderPort, request: str, spec: dict, problems: list[str]) -> dict:
    """The builder's repair call — a PATCH: the built graph exposed structural holes / lost items; the
    audit corrects its own transcription by re-emitting ONLY the fields it changes (the caller merges).
    Content stays the audit's; this only repairs STRUCTURE (a mapping name that drifted from a criterion
    name, a missing verdict, a lost item)."""
    user = (f"# TASK\n{request}\n\n# YOUR CURRENT DECOMPOSITION (structured)\n```json\n"
            f"{__import__('json').dumps(spec, ensure_ascii=False)}\n```\n\n"
            "# STRUCTURAL PROBLEMS THE BUILT GRAPH EXPOSED\n"
            + "\n".join(f"- {p}" for p in problems)
            + "\n\nEmit a PATCH: re-emit ONLY the top-level fields you change, complete (a re-emitted field "
              "REPLACES the old one wholesale; omitted fields are kept as-is). Fix ONLY what the problems "
              "require — exact-match mapping/criterion names, add missing predictability verdicts, restore "
              "lost items; do not rework converged content.")
    return llm.complete_structured(AUDIT_PROMPT, user, AUDIT_SCHEMA_PATCH)


def decompose_spec(request: str, depth: int = 1, model: str = "sonnet",
                   llm: LLMProviderPort | None = None, progress=None, emit_basis: bool | None = None,
                   fast: bool = False) -> dict:
    """Run search↔audit up to `depth` times (the quality dial, exactly as calibrated in E2: trivial task →
    depth 1 = one search + one audit); the STRUCTURED spec is emitted only on the FINAL round —
    intermediate rounds carry the basis as prose (.md). Early exit: if a pass-2+ searcher reports the
    space ALREADY-COVERED, the loop finalizes immediately (fewer tokens on small tasks; `depth` stays the
    upper bound, never a padding target).

    `emit_basis` policy (measured, wordfreq A/C/E probes): at depth=1 the FULL prose-first final is both
    equally fast and MORE stable (all lean runs drifted a mapping name → a repair round; prose-first runs
    were clean — the auditor copies names from the prose it just wrote), so depth=1 defaults to True; at
    depth≥2 the final defaults to LEAN (structure only — re-emitting the grown basis is the cost center,
    and the carried intermediate prose is returned as `basis_markdown`, one search behind the structure).
    Pass an explicit bool to override either way.

    `fast` appends the measured pace-suffixes (SEARCH_FAST/AUDIT_FAST — user content, cores untouched):
    wordfreq simple task 106s/9.8k → 63-77s/5.6-7.4k out with holes==[], 0 repairs, shape parity
    (runs/v2_speed/). Content quality vs the frozen judge is UNMEASURED — the author's Pareto call;
    default stays False."""
    if emit_basis is None:
        emit_basis = depth <= 1
    if llm is None:
        from gfso.runtime import llm_factory
        llm = llm_factory(model)
    if getattr(llm, "on_tick", "absent") is None:  # adapter streams live ticks and none wired yet
        llm.on_tick = lambda msg: _progress(msg, progress)
    depth = max(1, depth)
    prev_md = ""
    for i in range(depth):
        # progress format: ROUND first, ROLE second — the round is the outer grouping, the roles rotate
        # inside it (1/2 searcher → 1/2 auditor → 2/2 searcher → …).
        _progress(f"{i + 1}/{depth} searcher…", progress)
        _hint(llm, f"{i + 1}/{depth} searcher")
        holes = _search(llm, request, prev_md, fast=fast)
        _tag(llm, f"search-{i + 1}")
        _progress(f"{i + 1}/{depth} searcher {_stat_line(llm)} · +{len(holes) / 1000:.1f}k chars findings",
                  progress)
        covered = prev_md and holes.lstrip().upper().startswith(_COVERED)
        if covered:
            _progress(f"{i + 1}/{depth} searcher: ALREADY-COVERED — finalizing early", progress)
        if i == depth - 1 or covered:
            # final round: fold (nothing new if covered) and emit the structured spec in one call
            _progress(f"{i + 1}/{depth} auditor (final: "
                      f"{'basis + spec' if emit_basis else 'spec, lean'})…", progress)
            _hint(llm, f"{i + 1}/{depth} auditor")
            spec = _audit(llm, request, prev_md, holes, emit_basis=emit_basis, fast=fast) or {}
            _tag(llm, f"audit-final-{i + 1}")
            _progress(f"{i + 1}/{depth} auditor {_stat_line(llm)}", progress)
            if spec:
                if not emit_basis and prev_md:
                    spec.setdefault("basis_markdown", prev_md)  # carried prose (one search behind)
                _progress(_spec_line(spec), progress)
            return spec
        _progress(f"{i + 1}/{depth} auditor (fold → basis.md)…", progress)
        _hint(llm, f"{i + 1}/{depth} auditor")
        prev_md = _audit_text(llm, request, prev_md, holes) or prev_md
        _tag(llm, f"audit-{i + 1}")
        _progress(f"{i + 1}/{depth} auditor {_stat_line(llm)}", progress)
    return {}


def decompose_text(request: str, depth: int = 1, model: str = "sonnet",
                   llm: LLMProviderPort | None = None) -> str:
    """Just the markdown basis (the D artifact)."""
    return decompose_spec(request, depth=depth, model=model, llm=llm).get("basis_markdown", "")
