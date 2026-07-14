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

1. **Structure — the verb by default; MANUAL where context must be studied (below).**
   `auto_decompose(request, root_id, depth)` is THE one decomposition
   verb, dispatched by the target's state: on an empty project it AUTHORS the root from the request
   itself (no hand `create_task` needed) and builds the verified subtree; on an already-decomposed
   node it runs `depth` REFINE rounds over what exists (+1 iteration: new findings fold in as a
   verified revision — children keep their Del and their own NEGLECTED/scope; completed children are
   FROZEN; a BLOCKED child's reason feeds the fold as runtime contact; `request` may be omitted — the
   node's OWN contract is the request, and a passed `request` is NOT applied on refine (the result
   carries a note): to change the goal itself, `revise` the node first, then refine; a TERMINAL target
   is refused — a completed goal is frozen); on a child (`root_id=<child>`) it recurses one level.
   depth 1 for a simple goal; `fast=true` on simple tasks (~1.5× faster, same structural shape).
   Then `list_holes()` — resolve or consciously declare every residue BEFORE executing.

   **The MANUAL regime (narrow-domain goals).** When the decomposition needs STUDIED context —
   project sources, docs, meaning an LLM's weights don't carry — auto_decompose cannot study it
   for you: study the context YOURSELF, then hand-build (`create_task`/`decompose`/
   `edit_criteria`/`map_criterion`) or repair auto_decompose's base. In this regime the L2 check
   is your NECESSITY, not an option — the loop (measured: a checker REPAIRS entailment but cannot
   RECALL absent content; one refine round recovered exactly the missing-content axes):
   `list_holes` (structure, L0/L1) → **one `auto_decompose` refine round over YOUR built graph**
   (the hole-hunt: recalls what you forgot; your structure, ids and Del are preserved — new
   findings fold in as a revision) → `review_decomposition(node)` (the L2 checker: per parent
   criterion — do the mapped children's criteria causally carry it; + semantic conflicts;
   ADVISORY) → fix via the verbs or consciously declare NEGLECTED → re-run, until no gaps.
   Freshness lives on the node: `get_review(node)` is a FREE read (never spends an LLM) returning
   the stored verdict + `verified` — True while the decomposition is UNCHANGED since the review;
   ANY shape edit (criteria, mappings, deps, a child's re-ASSIGN) auto-stales it, the record
   stays for comparison. Re-run `review_decomposition` to refresh; for a second opinion pass
   `model="opus"`. The verdict is an a-priori estimate — execution (q_D) keeps the last word.
2. **Drive by the frontier.** Loop `next_steps(root)` until `complete=true`. Each step tells you the
   node, the action, and whether it is YOURS (`mine`). Foreign steps (mine=false) are visible so you
   know what the graph waits on — hands off; surface them to the user if they block you.
3. **Execute your leaves for real** (the work itself, in the workspace), then
   `signal(task, "DELIVER", result=<paths + how EACH criterion is met + how to verify>)` — the result
   text is the validator's input; write it so an independent checker needs nothing else.
4. **Validate — self-pass is structurally impossible AT THE SEAM.** Validation fires on PUBLIC
   nodes (§6.5 D6): the ROOT and every node whose executor differs from its parent's (a delegation
   seam). There, a PASS by the node's own executor is REJECTED by the FSM unless a FRESH
   independent verdict (a `validate_result` run for the CURRENT delivery) is on record with
   verdict PASS — a FAIL verdict blocks it, a rework or a reopen stales it (verifier ≠ executor).
   So after such a DELIVER either (a) a registered `llm-validator` auto-validates and auto-signals
   the verdict for you (register one once — recommended), or (b) you call
   `validate_result(task_id, workdir=…)` and then relay: `PASS`, or
   `FAIL(failed_criteria=<copied from the report>)` → the node returns as a `rework` step — fix
   exactly those criteria and re-deliver (max_iterations bounds the cycle). A `verdict: null`
   report is NEVER a pass — read report_text and decide as issuer.
   An INTERNAL node (same executor as its parent — your own private decomposition) self-verifies:
   your DELIVER's self-validation is its record, and its guarantee is carried by the public
   result's validation (T1) — you may PASS it directly; running `validate_result` there is still
   allowed and useful when you want per-node evidence. "Done" (root DONE/PASS) ALWAYS crosses the
   root seam — it never completes on a self-stamp.
5. **Blocked / defective spec:** `BLOCK(reason, blocker_task_ids=[<EVERY node you actually need>])`
   records each discovered dependency — list ALL blockers, never collapse them into one or into prose
   (an unlisted blocker is an invisible edge), and never route around one informally. A wrong contract =
   `CHALLENGE`, or fix it with `revise`/`edit_criteria` (same id, subtree retained; CANCEL only to truly
   abandon — it cascades). A DONE/CANCELLED node is quasi-terminal: `reopen(task_id)` returns it to
   REVIEW to RE-EARN its verdict (R′, §6.3) — but only while it is not CONSUMED (no parent aggregate
   staked on it, no dependent built on it, no replacement planned around it) and reopens remain
   (max_reopens, default 1). A consumed terminal is final — recover by re-decomposition, not reopen.

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
