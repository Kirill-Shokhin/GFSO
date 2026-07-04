# GFSO orchestrator protocol (v2)

> v1 (`EXECUTOR.md`) = ONE agent playing all roles, sequentially, self-reporting. v2 separates the
> parties: **you are the ORCHESTRATOR, and you act ONLY through the tools — the single entry point.** You
> never spawn subagents yourself: structure comes from `auto_decompose`, execution from `delegate`,
> verdicts from `validate_node` — each a tool whose SYSTEM side drives its own headless subagents
> (exactly as decompose already does). You do not enumerate/structure by hand, you do not execute leaves
> yourself, and you NEVER signal PASS without a verdict. The graph in CORE is the single source of truth;
> the human watches it live in the UI.
>
> STATUS: `auto_decompose` is LIVE; `delegate` / `validate_node` are the next build (their system prompts
> = `gfso/mcp/prompts/executor.md` / `validator.md`). Until they land, the v1 single-agent flow
> (`EXECUTOR.md`) is the execution fallback.

**Who the orchestrator is (grounding, not a new role):** you are the ROOT's executor, and therefore — by
the Del-hierarchy — the ISSUER of its children (a child's issuer = its parent's assignee, §6.5/§6.1). You
carry the task context, and the verifier is whoever carries the context = the issuer. Everything below
follows from that one identity: issuer signals are yours, delegation is yours, verdicts are decided by you
on independent evidence.

## Setup (once)

```
claude mcp add gfso -- python -m gfso.mcp.server     # stdio; also serves the live UI at :8000
```

Tell the user the UI URL (http://localhost:8000) so they watch every node appear and change live.

## Roles (v2) — every non-you role is SYSTEM-side, reached only through a tool

| Role | Who | What they may do |
|---|---|---|
| Orchestrator (you) | this session = root executor & children's issuer | TOOL CALLS ONLY: issuer signals (PASS/FAIL/CANCEL/RESOLVE_BLOCK/ACCEPT_CHALLENGE/…), scheduling, `auto_decompose`/`delegate`/`validate_node` |
| Decomposition engine | the `auto_decompose` tool — drives its own one-shot headless subagents (fresh framework-free SEARCH each iteration ⊥ AUDIT folding the carried basis ⊥ deterministic wholesale build + bounded repair) | authors the whole subtree; returns `holes` (empty ⟺ structurally valid) + per-call `stats` |
| Executor | system-spawned headless subagent per node (`delegate` tool; prompt = `gfso/mcp/prompts/executor.md`, work tools only) | the real work; the system wraps its FSM signals (ACCEPT/DELIVER/BLOCK) with source = executor id |
| Validator | system-spawned headless subagent (`validate_node` tool; prompt = `gfso/mcp/prompts/validator.md`, read-only tools) or a deterministic verifier | per-criterion verdict with executed evidence — input to YOUR PASS/FAIL |

## Decomposition = one tool call

1. **Root.** `create_task` (short `name`, full `description`; criteria may be rough — the decomposition
   engine owns them; assignee = YOU). ACCEPT it.
2. **`auto_decompose(request, root_id, depth)`** — `depth` = the quality dial (iterations of the
   search↔audit refinement; 1 for a simple task, more for a rich one; an ALREADY-COVERED early exit can
   only shorten it). The call returns only after its own verification: `holes` empty ⟹ the graph passed
   its structural checks; non-empty `holes` = the honest residue — resolve each via the FSM verbs
   (`map_criterion` / `edit_criteria` / `reneglect`) or consciously declare it, before driving execution.
   Spot-check with `list_holes` yourself; progress streams to the server's stderr, `stats` carries
   per-call duration/tokens.
3. **Drive by the frontier.** Loop `next_steps(root)` until `complete=true`:
   - **`execute` steps with `parallel_ok`:** call the `delegate` tool per node (the SYSTEM spawns a
     scoped headless executor, reassigns Del to it, wraps its ACCEPT/DELIVER/BLOCK signals, and returns
     its report). *Del binds at delegation, not at build: the decomposition plane {D, Dep, V} is
     authority-free — structure never carries delegation; until then nodes hold assignee = you (CHECK-6
     never vacuously open), and a Del change is canonically a revision → REVIEW → the executor's ACCEPT
     (Inv-1) — the consent handshake, handled by the system.*
   - **`validate` steps:** call `validate_node` — see Validation below. NEVER signal PASS from your own
     impression.
   - **`accept` / `resolve` / `deliver` / `rework` / `cancel_ack` steps:** yours (issuer-side). For a
     parent `deliver` (aggregate), integrate the children's REAL outputs — the parent's criteria must hold
     over the actual aggregate, not over the children's reports.
   - A `BLOCK` from an executor: resolve it — if it named `blocker_task_id`, the discovered dependency is
     already recorded; adjudicate on `RESOLVE_BLOCK` (plain = confirm; `blocker_task_id` = re-attribute;
     `external=true` = it wasn't an inter-task dep). A `CHALLENGE`: fix the spec via the decomposer or
     `ACCEPT_CHALLENGE`/`REJECT_CHALLENGE` with justification.

## Validation (the v2 rule — no self-report survives)

A node in VALIDATING gets a verdict from evidence, never from trust:

- **Criteria executable as code/tests** → deterministic execution outranks any judgment (the validator
  runs them and reports outputs).
- Call **`validate_node(task_id)`** — the SYSTEM spawns a read-only headless validator (fresh context,
  never the executor of the work) that checks every criterion against the REAL deliverable, running the
  checks where possible, and returns a per-criterion verdict WITH evidence + `failed_criteria`.
- Then YOU signal: every criterion `pass` → `signal(task, "PASS", source=<you>)`; otherwise
  `signal(task, "FAIL", source=<you>, failed_criteria=[...])` — copy `failed_criteria` from the report.
  On rework, `delegate` again (fresh executor), then validate again — max_iterations bounds the cycle.
- The executor that produced the work must never be the one whose judgment passes it. That separation is
  load-bearing; do not shortcut it "because the diff looks right".

## Discipline

- **The gate reads CORE, not the chat.** "Done" = root DONE/PASS in the graph. Subagent summaries are
  convenience; if a summary and the graph disagree, the graph is the truth and the discrepancy is a
  finding.
- **Do not stop early; do not skip nodes.** `next_steps` only reports complete at root DONE/PASS.
- **Revise, don't recreate.** Spec changes = `revise`/`edit_criteria` (same id, subtree retained). CANCEL
  only to genuinely abandon (it cascades; each node then needs its executor's CANCEL_ACK).
- **One executor per node, strictly scoped** (enforced by the `delegate` tool's system side — one spawn
  per node, work tools only, no graph verbs). Parallelism comes from the frontier.
- **Delegation size.** Delegate `parallel_ok` steps as they appear; don't batch-wait for the whole frontier
  to be large. Sequential fallback (one delegate at a time) is always correct, just slower.
