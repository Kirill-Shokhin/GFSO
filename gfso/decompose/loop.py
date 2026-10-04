"""The decompose loop — SEARCH (text recall) ↔ AUDIT (structured graph spec), incremental at depth>1.

Reproduces the E2 reference-method as a callable. SEARCH is a plain-text exhaustive hole-hunt; AUDIT is a
forced-structured call emitting the decomposition AS structure (D/Dep/V/N) — the audit is GFSO-aware and
reasons in native model thinking; the GRAPH-form spec is the sole carried state at EVERY depth, and the
ONE textual read of the state is the built graph's own projection (`Engine.project`) — no separate
prose representation exists anywhere.

Refinement is INCREMENTAL: round 1 emits the full spec; every later round the searcher reads the rendered
state and hunts only genuinely new holes, and the auditor emits a FOLD-PATCH (adds/updates/removals only)
that the orchestrator merges programmatically — the model never re-emits converged content, so it cannot
drop or compress it (the ×n re-emission cost and the fold-degradation of the earlier prose-carry loop are
both removed by construction). The loop stops early on ALREADY-COVERED (searcher) or an empty fold (audit).

A decomposition function is **single-level by definition**: it decomposes ONE node into its children.
Recursion = call it again on a child. The flat spec (root criteria + subtasks + mappings + deps + accepted_risks
+ scope) is therefore the correct one-level encoding; deeper trees are separate calls. `depth` is the
iteration count of the search↔audit refinement (the depth-of-working-through dial), not tree depth.
"""
from __future__ import annotations

import sys
from pathlib import Path

from gfso.adapters.llm.stats import _hint, _stat_line, tag_stage
from gfso.core.types import LLMProviderPort, Stage
from gfso.config import MODEL_DEFAULT
from gfso.llm import llm_factory


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


def _spec_line(spec: dict) -> str:
    """Shape readout of a structured spec (what is about to be built)."""
    return (f"spec: {len(spec.get('subtasks', []))} subtasks · {len(spec.get('deps', []))} seams · "
            f"{len(spec.get('root_criteria', []))} root criteria · {len(spec.get('accepted_risks', []))} risks")


def shape(spec: dict) -> tuple[int, int, int]:
    """(|D|, |Dep|, |V|) — V counts root spanning criteria + every child's node-local criteria."""
    n_v = len(spec.get("root_criteria", [])) + sum(len(c.get("criteria", []))
                                                   for c in spec.get("subtasks", []))
    return len(spec.get("subtasks", [])), len(spec.get("deps", [])), n_v

_PROMPTS = Path(__file__).parent / "prompts"
SEARCH_PROMPT = (_PROMPTS / "search.md").read_text(encoding="utf-8")
AUDIT_PROMPT = (_PROMPTS / "audit.md").read_text(encoding="utf-8")

_NAME_DESC = {"type": "object", "properties": {
    "name": {"type": "string"}, "description": {"type": "string"},
    # THE PROCEDURE, WRITTEN WITH THE CRITERION AND BEFORE ANY WORK. A criterion is a DECIDABLE
    # predicate (§2, A1); "for any accepted program the output matches gcc" decides nothing on its
    # own, and what used to close that gap was the validator inventing a probe set at validation time —
    # a different one each round, so a PASS said only what the validator felt like checking. Authoring
    # it here is the issuer side's job and nobody else's: the user writes the requirement, the
    # system writes the procedure that makes it decidable, and it is fixed before the executor
    # starts (Inv-1, §12.3). Measured on `c_compiler` (2026-09-19/20): the root closed PASS by an
    # independent validator and 205 probes written from the same contract found 34 real divergences.
    "check": {"type": "array", "description":
        "THE DECISION PROCEDURE for this criterion — what will actually be run to decide it, written "
        "NOW, before the work exists. Each item: {behaviour: the conjunct it observes, command: how "
        "to observe it, runnable as written by someone who was not the executor, expect: what the "
        "output must show}. A criterion quantified over an infinite domain ('for ANY input …') is "
        "not decidable as text: pin the finite, representative set that decides it — including the "
        "edge cases the requirement implies — and let the residue be visible rather than pretended "
        "away. Refer to the promised interface (the binary, the endpoint, the file) even though it "
        "does not exist yet; that is exactly what makes the check a pre-registered claim. Never "
        "write a command that only restates the criterion ('review the code') — it must produce an "
        "observation someone else can compare with `expect`. Test data the command reads (programs "
        "to compile, documents to parse, request bodies) goes into the probe's own `inputs` and the "
        "command names their directory `{inputs}` (e.g. `for f in {inputs}/*.c; do …; done`): the "
        "system writes them at validation time, so they cannot move under the check. A probe program longer "
        "than a one-line expression, or one carrying quoted data inside a quoted command, is an input too: "
        "put it in `inputs` as a file and run it from `{inputs}` so it still sees the working directory's modules "
        "(`PYTHONPATH=. python {inputs}/edge_cases.py`, each program its own file name) — inlined, one lost "
        "escape makes the probe check the "
        "quoting. Scratch files are the run's own (`T=$(mktemp -d); … > $T/out`), never a fixed `/tmp/x` — "
        "nodes are validated at once. Never point a "
        "command at test data the executor will write — its object would change while the check "
        "reads as unchanged.",
        "items": {"type": "object", "properties": {
            "behaviour": {"type": "string"}, "command": {"type": "string"},
            "expect": {"type": "string"},
            "inputs": {"type": "array", "description":
                       "files the command reads, pinned with it: relative paths under `{inputs}`",
                       "items": {"type": "object", "properties": {
                           "path": {"type": "string"}, "content": {"type": "string"}},
                           "required": ["path", "content"]}}},
            "required": ["behaviour", "command", "expect"]}}},
    "required": ["name", "description", "check"]}

# THE SEAM'S INPUT, COUNTED IN THE SAME CALL. A seam — an independent validation, and a wait for it — belongs
# where one agent's capacity ends (κ bounds executing AND checking, §3.7; a node is a leaf when within it, the
# root not exempt, §15.2; below it an agent self-verifies and presents one result, §10.3). Nobody but the
# decomposer has the plan in view, and estimating a piece of work is the obvious count anyone makes; so it
# writes the volume and its judgement against the named executor, and the build places the seams from them.
_VOLUME = ("the obvious count of the work: roughly how much has to be written (lines, files) and how many "
           "checks run — the ground for the judgement beside it")
_FITS = ("can ONE session of the executor named under # EXECUTOR write this subtask AND run every one of its "
         "checks directly, holding all its requirements at once? Judged from the volume you counted, "
         "against that executor")
_WHOLE_FITS = ("the same question for the WHOLE node being split — every subtask together with the "
               "integration: could one session of the named executor build and check all of it? The node is "
               "split for the plan either way; this decides whether its pieces are validated each on its "
               "own or once, at the node, as one executor's work")

# AUDIT structured output: the decomposition as graph spec (the graph is the artifact; its one
# textual read is Engine.project — the model never emits prose).
AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description":
            "A SHORT title (≤6 words) for the whole node — the UI label; the request text is the full description."},
        "root_criteria": {"type": "array", "description":
            "The node's WHOLE contract: its spanning invariants, AND for each component the goal names requirements "
            "of, one criterion listing those requirements as the goal states them (mapped to that child) — every "
            "requirement of the goal is decided by a criterion here, never only by a child's.",
            "items": _NAME_DESC},
        "subtasks": {"type": "array", "description":
            "The D components. Each: a stable snake_case id, a SHORT name (≤6 words, the node title), a fuller "
            "description, and its own concrete criteria (the requirements of its piece, each with its probes).",
            "items": {"type": "object", "properties": {
                "id": {"type": "string"}, "name": {"type": "string"}, "description": {"type": "string"},
                "criteria": {"type": "array", "items": _NAME_DESC},
                "volume": {"type": "string", "description": _VOLUME},
                "fits_one_session": {"type": "boolean", "description": _FITS}},
                "required": ["id", "name", "description", "criteria", "volume", "fits_one_session"]}},
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
        "accepted_risks": {"type": "array", "description":
            "The RISK REGISTER — ONLY uncertain EVENTS with a real materialization probability that this "
            "decomposition ignores. predictability verdict per event: STATISTICAL = P estimable but rare "
            "(justification must state why carrying it as an accepted risk is acceptable); EXTRAORDINARY = genuinely "
            "unprecedented (no precedent AND not derivable from known models); ORDINARY events may NOT be "
            "accepted_risks — they must be a subtask instead. An entry never decides how the result behaves on an "
            "input the goal describes ('lone surrogates are accepted rather than rejected'): that is a behaviour, "
            "certain once built, so it is decided in a criterion, which the validator then checks — an input of a "
            "kind the goal names stays the goal's however large or deep it is, at sizes the environment holds; only "
            "the arrival of what the "
            "goal does not describe at all (load on a scale it never mentions, a failing environment) is an event. "
            "A deliberate SCOPE BOUNDARY (a capability the goal "
            "does not include) is NOT a risk — it has no P: put it in the `scope` field (objectified on the "
            "goal, visible in the graph), NOT here; it also shapes which root_criteria exist.",
            "items": {"type": "object", "properties": {
                "item": {"type": "string"},
                "predictability": {"type": "string", "enum": ["STATISTICAL", "EXTRAORDINARY"]},
                "justification": {"type": "string"},
                "invalidation": {"type": "string", "description": "when to revisit this accepted risk"},
                "p": {"type": "number", "description": "your estimate of the probability the event materializes "
                      "during this goal's run, in (0, 1] — the register's roll-up reads it (§9.4)"},
                "impact": {"type": "string", "description": "what it costs the goal when it does"},
                "component": {"type": "string", "description": "the risk component (a group of correlated factors "
                              "with one root cause) this entry accepts as a group, where it does; else empty"}},
                "required": ["item", "predictability", "justification", "invalidation", "p", "impact"]}},
        "scope": {"type": "array", "description":
            "Deliberate SCOPE-BOUNDARY exclusions — capabilities the goal does NOT include (no materialization "
            "probability; NOT risks, distinct from `accepted_risks`). Each: the excluded capability + why it is "
            "safely out. Recording them here OBJECTIFIES the exclusion ON THE GOAL (it becomes visible in the "
            "graph, not an implicit absence). Emit here every scope-exclusion the basis names in its N section.",
            "items": {"type": "object", "properties": {
                "item": {"type": "string"}, "why_out": {"type": "string"}},
                "required": ["item", "why_out"]}},
        "denial": {"type": "object", "description":
            "This split's own denial by S: the probability that its composition claim is refuted at contact — "
            "the whole FAILs while every child passes. Use the recorded refutation rate of comparable splits when "
            "you were given one; else your estimate, and say what it rests on.",
            "properties": {"p": {"type": "number", "description": "in (0, 1]"},
                           "justification": {"type": "string"}},
            "required": ["p", "justification"]},
        "whole_volume": {"type": "string", "description": _VOLUME + " — for the WHOLE node being split"},
        "whole_fits_one_session": {"type": "boolean", "description": _WHOLE_FITS},
    },
    "required": ["name", "root_criteria", "subtasks", "mappings", "deps", "accepted_risks", "denial",
                 "whole_volume", "whole_fits_one_session"],
}

# The repair call PATCHES: every field optional — the corrective audit re-emits ONLY what it changes
# (a full-spec re-emission on a 16-subtask graph cost 33.7k output tokens / 312s, observed live).
AUDIT_SCHEMA_PATCH = {**AUDIT_SCHEMA, "required": []}

_SUBTASK_ITEM = AUDIT_SCHEMA["properties"]["subtasks"]["items"]

# The FOLD patch (refinement rounds): fine-grained adds/updates/removals ONLY. A top-level field
# replacement (AUDIT_SCHEMA_PATCH) would make `subtasks` ≈ a full re-emission on every round — the
# ×n cost center; the fold instead names the delta and the orchestrator merges it deterministically.
FOLD_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description":
            "SHORT title (≤6 words) for the whole node — set it on the first fold (empty state); "
            "omit thereafter unless renaming."},
        "add_subtasks": {"type": "array", "items": _SUBTASK_ITEM, "description":
            "NEW D components (genuinely new truth-makers). Same shape as subtasks."},
        "update_subtasks": {"type": "array", "items": _SUBTASK_ITEM, "description":
            "Sharpened EXISTING components, matched by id — each replaces its node wholesale "
            "(re-emit the node complete: name, description, ALL its criteria)."},
        "remove_subtask_ids": {"type": "array", "items": {"type": "string"}, "description":
            "Ballast / merged-away components (their mappings and seams are cleaned up automatically)."},
        "add_root_criteria": {"type": "array", "items": _NAME_DESC},
        "remove_root_criteria_names": {"type": "array", "items": {"type": "string"}},
        "add_mappings": {"type": "array", "items": AUDIT_SCHEMA["properties"]["mappings"]["items"]},
        "remove_mappings": {"type": "array", "items": AUDIT_SCHEMA["properties"]["mappings"]["items"]},
        "add_deps": {"type": "array", "items": AUDIT_SCHEMA["properties"]["deps"]["items"]},
        "remove_deps": {"type": "array", "items": {"type": "object", "properties": {
            "from": {"type": "string"}, "to": {"type": "string"}}, "required": ["from", "to"]}},
        "add_accepted_risks": {"type": "array", "items": AUDIT_SCHEMA["properties"]["accepted_risks"]["items"]},
        "remove_accepted_risks_items": {"type": "array", "items": {"type": "string"}},
        "add_scope": {"type": "array", "items": AUDIT_SCHEMA["properties"]["scope"]["items"]},
        "remove_scope_items": {"type": "array", "items": {"type": "string"}},
        "denial": AUDIT_SCHEMA["properties"]["denial"],
        "whole_volume": AUDIT_SCHEMA["properties"]["whole_volume"],
        "whole_fits_one_session": AUDIT_SCHEMA["properties"]["whole_fits_one_session"],
    },
    "required": [],
}


_COVERED = "ALREADY-COVERED"

# `fast` pace-suffixes — USER-content additions (frozen prompt CORES untouched; same sanctioned class
# as the ALREADY-COVERED sentinel). Measured on the wordfreq simple task (runs/v2_speed/suffix_*.json):
# baseline 106s/9.8k out → both suffixes 63-77s/5.6-7.4k out, holes==[], 0 repairs, shape parity
# (the audit suffix MUST carry the keep-ACCEPTED_RISKS clause — without it the register got dropped → repair).
# ⚠ SIMPLE TASKS ONLY — measured on the complex T01 reference (2026-07-04): 2× cheaper (325s/32k →
# 167s/17k) but coverage −9/45 on the basis (35→26; V-criteria content is what compresses away).
SEARCH_FAST = ("Pace note: this is a SIMPLE task — keep the enumeration TIGHT: one short line per "
               "hole/component (its falsifier in a few words), no derivations, no re-verification "
               "prose, no closing narration. Completeness of ITEMS matters; wordiness does not.")
AUDIT_FAST = ("Pace note: this is a SIMPLE task — keep the reduction TIGHT: no narration or "
              "self-check text (the structure carries the checks). Names EXACT — drop nothing; the "
              "ACCEPTED_RISKS risk register stays COMPLETE (each risk with its predictability verdict, "
              "its estimate p and impact, justification, invalidation). NB: reworded 2026-07-09 for the prose-free loop; the "
              "measured 63-77s numbers below are from the prose-era wording.")


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


def executor_line(executor: str) -> str:
    """The input fact the fit is judged against — which executor runs one session."""
    # …AND WHAT A SESSION IS. Named by its model alone, the haiku decomposer judged coreutils (~1900 lines) beyond one
    # session three times of three, where one bare haiku session had written 1611 lines and run its checks in 38
    # turns; told that a session is an agent working turn by turn with files and a shell, it judged it within (probe,
    # 2026-10-12). The fit places the seams, so a session misdescribed puts seams below κ that the work pays for.
    return ("\n\n# EXECUTOR\nEach session is one run of " + (executor or "the user's own agent (its model is not "
            "known to the system — judge against one session of a current coding agent)")
            + ": an agent with file-editing and shell tools working turn by turn — each turn can write or edit a "
              "whole file, or build and run any number of checks — within its turn budget where one is named. "
              "Judge `fits_one_session` / `whole_fits_one_session` against that session.")


def _audit_fold(llm: LLMProviderPort, request: str, state_md: str, holes: str,
                fast: bool = False, executor: str = "") -> dict:
    """THE audit call — every round is the same operation (state, findings) → fold-patch; round 1 is
    just the empty-state case (the whole enumeration reduces to the canonical basis as adds). The
    orchestrator carries the full state and merges deterministically — the audit emits ONLY what
    changes, so converged content physically cannot be dropped or compressed by re-emission."""
    user = (f"# TASK\n{request}\n\n# CURRENT CANONICAL DECOMPOSITION (carried by the orchestrator)\n"
            f"{state_md or '(empty — first round)'}\n\n# NEW FINDINGS TO FOLD IN\n{holes}\n\n"
            "Fold: classify each finding against the current basis — a true duplicate of an existing "
            "item is a no-op; a genuinely new truth-maker is an add; a finding that sharpens an existing "
            "item is an update (re-emit that node complete); ballast or a wrong scope decision is the "
            "corresponding remove/add. On the first round (empty state) this reduces the whole "
            "enumeration to the canonical basis as adds, including `name`. Emit ONLY the changes as a "
            "fold-patch — omitted content is kept verbatim by the orchestrator. Keep the state "
            "well-formed: an added root criterion or subtask carries its coverage (add_mappings); an "
            "added seam names existing subtask ids. If nothing new carries a distinct falsifier, emit "
            "an empty patch.") + executor_line(executor)
    if fast:
        user += "\n\n" + AUDIT_FAST
    return llm.complete_structured(AUDIT_PROMPT, user, FOLD_SCHEMA)


def _apply_removals(s: dict, patch: dict, ops: list) -> None:
    """The removal phase of a fold, in place: subtasks, root criteria, mappings, risks.

    Removals run FIRST and clean what referenced them (a removed subtask takes its mappings
    and seams with it — referential integrity by construction). Split out because the merge
    is three phases and only the first one is about taking things away.
    """
    rm_ids = {str(x) for x in patch.get("remove_subtask_ids", [])} & {str(c.get("id")) for c in s["subtasks"]}
    if rm_ids:
        s["subtasks"] = [c for c in s["subtasks"] if str(c.get("id")) not in rm_ids]
        s["mappings"] = [m for m in s["mappings"] if str(m.get("child_id")) not in rm_ids]
        s["deps"] = [d for d in s["deps"]
                     if str(d.get("from")) not in rm_ids and str(d.get("to")) not in rm_ids]
        ops.append(f"-D {', '.join(sorted(rm_ids))}")
    rm_rc = {str(x) for x in patch.get("remove_root_criteria_names", [])} \
        & {str(c.get("name")) for c in s["root_criteria"]}
    if rm_rc:
        s["root_criteria"] = [c for c in s["root_criteria"] if str(c.get("name")) not in rm_rc]
        s["mappings"] = [m for m in s["mappings"] if str(m.get("criterion")) not in rm_rc]
        ops.append(f"-V(root) {len(rm_rc)}")
    for key, tgt, idf in (("remove_mappings", "mappings",
                           lambda x: (str(x.get("criterion")), str(x.get("child_id")))),
                          ("remove_deps", "deps", lambda x: (str(x.get("from")), str(x.get("to"))))):
        rm = {idf(x) for x in patch.get(key, [])}
        kept = [x for x in s[tgt] if idf(x) not in rm]
        if len(kept) != len(s[tgt]):
            ops.append(f"-{tgt} {len(s[tgt]) - len(kept)}")
            s[tgt] = kept
    for key, tgt, idf in (("remove_accepted_risks_items", "accepted_risks", lambda x: str(x.get("item"))),
                          ("remove_scope_items", "scope", lambda x: str(x.get("item")))):
        rm = {str(x) for x in patch.get(key, [])}
        kept = [x for x in s[tgt] if idf(x) not in rm]
        if len(kept) != len(s[tgt]):
            ops.append(f"-{tgt} {len(s[tgt]) - len(kept)}")
            s[tgt] = kept



def _fold_merge(spec: dict, patch: dict) -> tuple[dict, list[str]]:
    """Deterministic merge of a fold-patch into the carried spec: removals → updates → adds (deduped).
    Removing a subtask cleans its mappings and seams (referential integrity by construction). Returns
    (new spec, human-readable op summary); an empty summary ⟺ the patch changed nothing (converged)."""
    s = {k: (list(v) if isinstance(v, list) else v) for k, v in spec.items()}
    for key in ("subtasks", "root_criteria", "mappings", "deps", "accepted_risks", "scope"):
        s.setdefault(key, [])
    ops: list[str] = []

    if patch.get("name") and patch["name"] != s.get("name"):
        s["name"] = patch["name"]
        ops.append("name")
    for k in ("denial", "whole_volume", "whole_fits_one_session"):
        if k in patch and patch[k] != s.get(k):
            s[k] = patch[k]
            ops.append(k)

    _apply_removals(s, patch, ops)

    upd = {str(c.get("id")): _keeping_the_pinned_inputs(c, s["subtasks"])
           for c in patch.get("update_subtasks", [])}
    changed = [str(c.get("id")) for c in s["subtasks"] if str(c.get("id")) in upd and upd[str(c.get("id"))] != c]
    if changed:
        s["subtasks"] = [upd.get(str(c.get("id")), c) for c in s["subtasks"]]
        ops.append(f"~D {', '.join(changed)}")
    unknown_upd = [c for cid, c in upd.items() if cid not in {str(c.get("id")) for c in s["subtasks"]}]

    def _add(tgt: str, items: list, idf) -> None:
        have = {idf(x) for x in s[tgt]}
        new = [x for x in items if idf(x) not in have]
        if new:
            s[tgt] = s[tgt] + new
            ops.append(f"+{tgt} {len(new)}")
    _add("subtasks", list(patch.get("add_subtasks", [])) + unknown_upd, lambda x: str(x.get("id")))
    _add("root_criteria", patch.get("add_root_criteria", []), lambda x: str(x.get("name")))
    _add("mappings", patch.get("add_mappings", []),
         lambda x: (str(x.get("criterion")), str(x.get("child_id"))))
    _add("deps", patch.get("add_deps", []), lambda x: (str(x.get("from")), str(x.get("to"))))
    _add("accepted_risks", patch.get("add_accepted_risks", []), lambda x: str(x.get("item")))
    _add("scope", patch.get("add_scope", []), lambda x: str(x.get("item")))
    return s, ops


def _keeping_the_pinned_inputs(replacement: dict, current: list) -> dict:
    """A rewritten subtask keeps the FILES its probes pinned, where the command still reads them.

    An update replaces a subtask wholesale, and the model that writes it reads the projection —
    which shows a probe's command and not the corpus behind `{inputs}`. So a refine round that
    touched a subtask for any reason returned criteria whose commands still said `{inputs}` and
    whose inputs were gone: at validation time nothing is laid down, the token is never substituted,
    and the validator is handed a literal `{inputs}`. This is one level deeper than the class
    `extract.py` already records paying for — "one refine round stripped every pinned check off a
    contract that had just been authored with one".

    Matched by criterion name and command, which is what makes it a CARRY rather than a merge: an
    issuer who genuinely moves the corpus writes a different command, or edits the criterion through
    the door that says so."""
    was = {str(c.get("id")): c for c in current}.get(str(replacement.get("id")))
    if not was:
        return replacement
    pinned = {(str(c.get("name")), str(p.get("command"))): p.get("inputs")
              for c in (was.get("criteria") or []) for p in (c.get("check") or []) if p.get("inputs")}
    if not pinned:
        return replacement
    out = dict(replacement)
    # "absent" and "empty" are different acts: an issuer who writes `inputs: []` under the same
    # command has decided to drop the corpus, and writing the old one back would undo his decision
    # silently — the mirror of the loss this carry exists against.
    def _probe(c, p) -> dict:
        if "inputs" in p:
            return p
        was = pinned.get((str(c.get("name")), str(p.get("command"))))
        return dict(p, inputs=was) if was else p

    out["criteria"] = [dict(c, check=[_probe(c, p) for p in (c.get("check") or [])])
                       for c in (replacement.get("criteria") or [])]
    return out


def _audit_fix(llm: LLMProviderPort, request: str, spec: dict, problems: list[str],
               executor: str = "") -> dict:
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
              "require — exact-match mapping/criterion names, add missing predictability verdicts and STD-1 fields (p, impact, justification, invalidation), restore "
              "lost items; do not rework converged content. Any subtask criteria you re-emit must pass the "
              "per-node completeness test (no Result may pass them all yet fail the node's obligation) — a "
              "patched node carries its concrete obligation, not a coarse restatement; do not re-open "
              "converged nodes you are not patching.") + executor_line(executor)
    return llm.complete_structured(AUDIT_PROMPT, user, AUDIT_SCHEMA_PATCH)


def decompose_spec(request: str, model: str = MODEL_DEFAULT,
                   llm: LLMProviderPort | None = None, progress=None,
                   fast: bool = False, label: str = "1/1", executor: str = "") -> dict:
    """THE INIT ROUND — one search + one fold over the EMPTY state: the exhaustive enumeration reduces
    to the canonical basis (spec form). This is the single spec-space operation; every further
    refinement is the SAME operation applied to the BUILT GRAPH as the state (`refine` in
    gfso.decompose — extract → search over the projection → fold → rebuild as revision), so
    decompose(depth=N) ≡ init + build + (N−1) × refine — one monadic operation over graph state.

    There is NO model-emitted prose anywhere: the auditor reasons in native thinking (measured tie vs
    prose-first on the T01 reference, D/Dep/V 32/39 both, 2026-07-08) and the ONE textual read of the
    state is the built graph's own projection (`Engine.project`) — no separate renderer exists.

    `fast` appends the measured pace-suffixes (SEARCH_FAST/AUDIT_FAST — user content, cores untouched):
    wordfreq simple task 106s/9.8k → 63-77s/5.6-7.4k out with holes==[], 0 repairs, shape parity
    (runs/v2_speed/). Content quality vs the frozen validator is UNMEASURED — the author's Pareto call;
    default stays False."""
    if llm is None:
        llm = llm_factory(model)
    if getattr(llm, "on_tick", "absent") is None:  # adapter streams live ticks and none wired yet
        llm.on_tick = lambda msg: _progress(msg, progress)
    _progress(f"{label} searcher…", progress)
    _hint(llm, f"{label} searcher")
    holes = _search(llm, request, "", fast=fast)
    tag_stage(llm, Stage.SEARCH)
    _progress(f"{label} searcher {_stat_line(llm)} · +{len(holes) / 1000:.1f}k chars findings", progress)
    _progress(f"{label} auditor (fold, first round)…", progress)
    _hint(llm, f"{label} auditor")
    patch = _audit_fold(llm, request, "", holes, fast=fast, executor=executor) or {}
    tag_stage(llm, Stage.AUDIT_FOLD)
    spec, ops = _fold_merge({}, patch)
    if not ops:
        _progress(f"{label} auditor {_stat_line(llm)} · empty fold — no basis emitted (failed first round)",
                  progress)
        return {}
    d, dep, v = shape(spec)
    _progress(f"{label} auditor {_stat_line(llm)} · |D|={d} |Dep|={dep} |V|={v}", progress)
    _progress(_spec_line(spec), progress)
    return spec


