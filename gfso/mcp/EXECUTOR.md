# GFSO executor protocol (v1)

> **v2 exists:** `ORCHESTRATOR.md` — separated roles (orchestrator + `gfso-decomposer` /
> `gfso-executor` / `gfso-validator` agents in `.claude/agents/`), parallel delegation over the
> `next_steps` frontier, external validation instead of self-report. Use v2 when the role agents are
> available; this v1 protocol remains the single-agent fallback.

## Setup (once)
Register the gfso MCP server in Claude Code — it is spawned at session start (stdio) and ALSO serves the live
UI over the same Engine, so tools + UI are one process:
```
claude mcp add gfso -- python -m gfso.mcp.server         # env GFSO_DB_PATH / GFSO_UI_PORT (default 8000)
```
Then in any chat the `gfso` tools are available and the graph UI is live at **http://localhost:8000** — tell
the user that URL so they watch every node appear + change as you work. (`GFSO_MCP_UI=0` disables the UI.)

You operate a GFSO task graph through the `gfso` MCP tools. The graph is the plan and the source of truth;
your job is to drive it to completion. **The graph drives — you execute exactly what it tells you.**

## The loop (this is the whole job)

1. **Start the task.** If the graph is empty, call `create_task` to make the root node (a short `name` + a
   full `description`). It appears in the UI immediately — the human watches the same graph live.
2. Call **`auto_decompose(request)`** on the root if it is a multi-part goal (it builds the children +
   criteria + dependencies through the protocol). For a trivial task you may skip straight to executing.
   Then call **`list_holes()`** — a decomposed graph can come back with unmet structural checks; resolve them
   (edit the offending node) ∨ consciously declare them (NEGLECTED) up front, before you start signalling.
3. **Then loop, and do EXACTLY what each directive says:**
   ```
   while True:
       step = next_step()
       if step.complete: break          # the root is DONE/PASS — finished
       do(step.directive)               # perform the one action it names, then continue
   ```

## What each `action` means

- **accept** — `signal(task, "ACCEPT", source=<executor>)`. Then, if the node is multi-part, `auto_decompose`
  / `decompose` it; if atomic, go execute it.
- **execute** — this is the REAL work. Do it in your workspace (write the code / files / produce the artifact)
  so the node's `criteria` actually hold. Then `signal(task, "DELIVER", source=<executor>, result=...)`.
- **validate** — check the deliverable against the node's `criteria`. If every criterion holds,
  `signal(task, "PASS", source=<issuer>)`; otherwise `signal(task, "FAIL", source=<issuer>, failed_criteria=[...])`.
- **deliver** (aggregate) — all children PASSED; integrate them and `signal(task, "DELIVER", ...)`. The
  parent's criteria must hold over the REAL aggregate, not mocks.
- **rework** — a node FAILED; fix the work so its criteria hold, then DELIVER again.
- **resolve** — a node is BLOCKED; clear the blocker, then `signal(task, "RESOLVE_BLOCK", ...)`. If the BLOCK
  had named a prerequisite node (`blocker_task_id`), the resolve ADJUDICATES the provisional dependency it
  recorded: plain resolve = confirm; pass `blocker_task_id` = the corrected source; pass `external=true` if
  the blocker turned out to have no producer node (retracts the edge — it was an external-conditions event).
  When you hit an UNDECLARED dependency on another node's output, BLOCK **with** `blocker_task_id=<that node>`
  — this records the discovered dependency (feeds q_Dep) instead of losing it.
- **cancel_ack** — a node is CANCELLING (an issuer CANCEL opened the two-step abandon handshake, §6.3).
  Confirm it: `signal(task, "CANCEL_ACK", source=<executor>, in_flight="what was done/undone at cancellation")`
  → the node settles to CANCELLED (terminal, V=⊥). You confirm, not dispute — cancellation is authoritative.

## Discipline (non-negotiable)

- **Do not stop early.** `next_step` only returns `complete` when the root is DONE/PASS. If it hands you a
  directive, there is work left — do it.
- **Do not skip nodes or fake completion.** Every node's `criteria` are its contract; satisfy them for real.
- **One directive at a time.** Do what `next_step` says, then call it again. Don't free-wheel — the graph,
  not your preference, decides the order (children before parents, dependencies respected).
- **Roles (v1): you are BOTH issuer and executor.** Pass YOUR agent id as `source` on every signal — the
  `<issuer>`/`<executor>` labels above are the same party here (a child's issuer = its parent's assignee,
  which is you). If a signal is rejected with "X is not issuer/executor", read the expected id in the error
  and resend with that `source`.
- **Fix structural holes BEFORE you accept/execute a node.** A revision (revise/reneglect/edit_criteria =
  re-ASSIGN, same id) drops the node back to REVIEW — so set a node's NEGLECTED and repair its coverage FIRST,
  then run it through accept→execute→deliver→PASS (else you re-open a node you'd already progressed).
  `list_holes` shows what's open; `map_criterion(parent, child, criterion)` binds an existing child to a parent
  criterion (repairs a dangling/absent coverage mapping — `decompose` only maps NEW children).
- **Abandon ≠ revise.** `signal(task, "CANCEL", ...)` abandons a node — it cascades CANCEL to the whole
  subtree and each node awaits CANCEL_ACK. To change a node's spec, use `revise`/`edit_criteria` (revision:
  same id, subtree retained, no cascade) — never CANCEL+recreate.
- Inspect a node any time with `get_task` / `project`; see the whole graph with `get_graph`.

> v1 limitation: completion is self-reported (you signal PASS). External objective verification is a later
> layer — for now the protocol forces you THROUGH every node, in order, to completion.
>
> Note on `verified`: it is an ADVISORY L2 flag (was the decomposition semantically re-validated?), NOT the
> node's execution status. A node can be DONE/PASS with `verified:false` — that only means no L2 pass has run
> on it, not that it is incomplete. Read `state` (+ `done_reason`) for real progress; ignore `verified` in v1.
