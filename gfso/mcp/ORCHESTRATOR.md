# GFSO — the user-agent protocol

You (the agent session) operate a GFSO task graph through the `gfso` tools. GFSO turns a goal into a
VERIFIED plan (nodes with decidable criteria, dependency seams, declared risks) and then FORCES honest
execution through a closed 12-signal protocol: every node is delivered, independently validated against
its criteria, and passed/failed on evidence — nothing completes by impression. The graph is the single
source of truth; the human watches it live in the UI (http://localhost:8000). "Done" = root DONE/PASS
in the GRAPH, never a chat summary.

**Your identity is `agent`.** Nodes you create default to Del=`agent` (= you execute them); your
signals are signed as you automatically. Del is load-bearing: a node assigned to someone else only
moves on THEIR signals — the FSM rejects yours. Never work around that; it is the point.

## The loop (both regimes start the same)

1. **Structure — never by hand.** `auto_decompose(request, root_id, depth)` is THE one decomposition
   verb, dispatched by the target's state: on an empty project it AUTHORS the root from the request
   itself (no hand `create_task` needed) and builds the verified subtree; on an already-decomposed
   node it runs `depth` REFINE rounds over what exists (+1 iteration: new findings fold in as a
   verified revision — children keep their Del and their own NEGLECTED/scope; `request` may be
   omitted, the node's contract is the request); on a child (`root_id=<child>`) it recurses one level.
   depth 1 for a simple goal; `fast=true` on simple tasks (~1.5× faster, same structural shape).
   Then `list_holes()` — resolve or consciously declare every residue BEFORE executing.
2. **Drive by the frontier.** Loop `next_steps(root)` until `complete=true`. Each step tells you the
   node, the action, and whether it is YOURS (`mine`). Foreign steps (mine=false) are visible so you
   know what the graph waits on — hands off; surface them to the user if they block you.
3. **Execute your leaves for real** (the work itself, in the workspace), then
   `signal(task, "DELIVER", result=<paths + how EACH criterion is met + how to verify>)` — the result
   text is the validator's input; write it so an independent checker needs nothing else.
4. **Validate — self-pass is structurally impossible.** PASS on a node you executed yourself is
   REJECTED by the FSM unless a FRESH independent verdict (a `validate_node` run for the CURRENT
   delivery) is on record with verdict PASS — a FAIL verdict blocks it, a rework stales it
   (verifier ≠ executor, §6.5). So after each DELIVER either (a) a registered `llm-validator`
   auto-validates and auto-signals the verdict for you (register one once — recommended), or
   (b) you call `validate_node(task_id, workdir=…)` and then relay: `PASS`, or
   `FAIL(failed_criteria=<copied from the report>)` → the node returns as a `rework` step — fix
   exactly those criteria and re-deliver (max_iterations bounds the cycle). A `verdict: null`
   report is NEVER a pass — read report_text and decide as issuer.
5. **Blocked / defective spec:** `BLOCK(reason, blocker_task_id=<node you actually need>)` records the
   discovered dependency — never route around it informally. A wrong contract = `CHALLENGE`, or fix it
   with `revise`/`edit_criteria` (same id, subtree retained; CANCEL only to truly abandon — it cascades).

## Choosing the regime (per NODE, not per task)

Self-execute a node when it needs YOUR session context — the user's ongoing intent, files you
already hold, judgment calls mid-work, anything you'd have to re-explain to a fresh worker.
Delegate a node (assign it to a registered executor) when it is a SELF-CONTAINED mechanical leaf:
its criteria + inputs fully specify it, and `next_steps` marks it `parallel_ok` alongside others —
that is free parallelism. Mixing inside one graph is the normal case. Assign to a HUMAN's name when
the work is theirs in reality (physical action, a decision above you) — the graph then honestly
waits for them. Validation needs no choice: with a registered llm-validator every delivery is
auto-validated and auto-verdicted regardless of who executed.

## Delegation (parallel regime — optional, registry-driven)

To run nodes on PARALLEL workers instead of executing them yourself, register the roles once:
`register_agent("exec-1", "llm-executor", workdir=…)` + `register_agent("val-1", "llm-validator")`.
From then on your ONLY act is assignment: create/`reassign` a node to `exec-1` and the system does the
rest — spawns the executor in its workdir, wraps its report into ACCEPT/DELIVER/BLOCK/CHALLENGE (its
consent is its own report), auto-runs the validator on delivery, and auto-signals the verdict
(PASS → DONE; FAIL → automatic rework loop with the failed criteria as feedback). You stay the issuer AND THE NARRATOR:
after delegating, POLL `next_steps`/`get_graph` every couple of minutes and REPORT progress to the
user each time (what finished, what runs, what blocks) — a silent orchestrator leaves the human
staring at an opaque wait; resolve BLOCKs/CHALLENGEs, handle the one escalation (an unparsed report).
Humans are never registered — assign a node to a person's name and the system waits for THEIR signals
(they act via the UI). Mixed graphs are normal: some nodes yours, some workers', some human.

## Discipline

- The gate reads CORE, not the chat: if a summary and the graph disagree, the graph is the truth.
- Do not stop early, do not skip nodes: `next_steps` reports complete only at root DONE/PASS.
- Revise, don't recreate: spec changes keep the node id and its subtree.
- One graph per project; `use_project(name)` switches YOUR SESSION's project (other agent sessions
  on the same server are unaffected), `project=` on any verb overrides per-call. A dependency across
  projects is unrepresentable by design — related goals live in ONE project.
