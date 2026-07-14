# GFSO Architecture v4

## Invariant

**The FSM transition table IS the architecture.** `(State, Signal, Guard) → (NewState, [Effects])`. The table is the single source of truth for all system behavior. No hidden middleware, hooks, or plugins. If something happens, a row in the table says so.

Guards are simple predicates on graph state (only where needed — currently one: iteration check). Effects are skeletal (task_id only). The event loop hydrates effects from graph + signal data before passing to handlers.

**Division of responsibility:** FSM decides WHICH effects. Graph provides DATA. Handlers EXECUTE. Main.py COMPOSES.

## FSM Transition Table (from paper §6 + vision doc)

```
(State, Signal, Guard)           → NewState      Effects
───────────────────────────────────────────────────────────────────
(IDLE, ASSIGN)                   → REVIEW        [MutateGraph, RunChecks, Dispatch]   # Recommend removed (§v3.6)
(IDLE, timeout)                  → TIMEOUT       [MutateGraph]          # Инв-5 total over non-terminals (crash-orphan escape)
(REVIEW, ACCEPT)                 → EXECUTING     [MutateGraph, Dispatch]
(REVIEW, CHALLENGE)              → CHALLENGED    [MutateGraph, Dispatch]
(REVIEW, timeout)                → TIMEOUT       [MutateGraph]
(CHALLENGED, ACCEPT_CHALLENGE)   → REVIEW        [MutateGraph, RunChecks, Dispatch]
(CHALLENGED, REJECT_CHALLENGE)   → EXECUTING     [MutateGraph, Dispatch]
(CHALLENGED, timeout)            → TIMEOUT       [MutateGraph]          # escalates §6.3 (§v3.6: no auto-accept)
(EXECUTING, DELIVER)             → VALIDATING    [MutateGraph, Dispatch]
(EXECUTING, BLOCK)               → BLOCKED       [MutateGraph, Dispatch] # +RECORD_DEP per named blocker (§6.2)
(EXECUTING, timeout)             → TIMEOUT       [MutateGraph]
(BLOCKED, RESOLVE_BLOCK)         → EXECUTING     [MutateGraph(ADJUDICATE_DEP), MutateGraph, Dispatch] # confirm/re-attribute/retract (§6.2)
(BLOCKED, timeout)               → ESCALATED     [MutateGraph]          # direct, see below
(VALIDATING, PASS)               → DONE          [MutateGraph, Dispatch]
(VALIDATING, FAIL, iter < max)   → REWORK        [MutateGraph, Dispatch]
(VALIDATING, FAIL, iter >= max)  → DONE          [MutateGraph, Dispatch] # reason=fail in mutation
(VALIDATING, timeout)            → DONE          [MutateGraph, Dispatch] # reason=auto in mutation
(REWORK, DELIVER)                → VALIDATING    [MutateGraph, Dispatch]
(REWORK, BLOCK)                  → BLOCKED       [MutateGraph, Dispatch] # +RECORD_DEP as above
(REWORK, timeout)                → TIMEOUT       [MutateGraph]
(TIMEOUT, timeout)               → ESCALATED     [MutateGraph]          # repeated timeout
(CANCELLING, CANCEL_ACK)         → CANCELLED     [MutateGraph, Dispatch] # in_flight logged (T11)
(CANCELLING, timeout)            → CANCELLED     [MutateGraph]          # cancellation is authoritative (§6.3)
(ANY_NON_TERM \ CANCELLING, CANCEL) → CANCELLING [MutateGraph, Dispatch] # opens the handshake; cascades CANCEL to subtree (§6.2)
(REASSIGNABLE, ASSIGN+spec)      → REVIEW        [MutateGraph(APPLY_SPEC), MutateGraph, RunChecks, Dispatch]
                                                 # REVISION (§6.4 Inv-1): re-ASSIGN same id, no cascade; excluded: TIMEOUT, CANCELLING, terminals
(DONE|CANCELLED, ASSIGN,
   ¬consumed ∧ reopens<max)      → REVIEW        [MutateGraph(REOPEN), MutateGraph, RunChecks, Dispatch]
                                                 # R′ REOPEN (§6.3): a gated re-ASSIGN, NOT a 13th signal — see below
```

Terminal states: DONE (with reason: pass/fail/auto), ESCALATED, CANCELLED (V=⊥). **DONE and CANCELLED
are QUASI-terminal (R′, §6.3):** a re-ASSIGN out of them is admitted under a DOUBLE gate — (i) the
finality-gate: the terminal is not CONSUMED in the graph (positive: the parent has not DELIVERed the
aggregate that presumes this pass AND no Dep-consumer has ACCEPTed into work on the result; negative:
the cascade has not settled OR the parent has not replanned around the hole — a sibling covering the
same criterion); (ii) `reopens < max_reopens` (ONE sign-agnostic per-node counter next to
max_iterations, default 1 — restores Инв-5 finiteness for the new outgoing edge). Both gate inputs ride
GuardContext, computed by the graph in the SAME `process_signal` step as the edge — gate+edge are one
log-serialized atomic act (Инв-7, no TOCTOU with a concurrent DELIVER). The REOPEN mutation spends the
counter, drops `done_reason` (V=pass is RE-EARNED in REVIEW, never resurrected), and generation-stamps
stale the recorded independent verdict (records carry `(iteration, reopens)`; the self-PASS gate and
q_V/false_fail_share compare both). A pass-terminal reopened under the SAME criteria whose fresh run
FAILs sets `false_positive` — exactly q_V's pass→later-fail member. ESCALATED stays fully terminal.

DONE is one state; completion reason is metadata in the MutateGraph mutation. Cancellation is NOT a DONE
reason — canon v3.7 §6.3 gives it its own two-step handshake `CANCEL→CANCELLING→CANCEL_ACK→CANCELLED`
(mirror of ASSIGN→ACCEPT; CANCEL_ACK = the sole staffed exit from CANCELLING, an FSM-deadlock signal
carrying the executor's in-flight report). **12 states in enum**: IDLE, REVIEW, CHALLENGED, EXECUTING,
BLOCKED, VALIDATING, REWORK, CANCELLING, DONE, CANCELLED, TIMEOUT, ESCALATED. Pre-v3.7 DBs stored
cancellation as DONE(reason=CANCELLED) — migrated on read in the SQLite adapter.

ESCALATED resolution is outside FSM — admin action (re-assign or close). Escalation crosses hierarchy levels which the per-task FSM cannot model.

**Discovered-Dep (§6.2/§7.2, two-phase):** a BLOCK naming undeclared prerequisite NODE(s)
(`blocker_task_ids`; `blocker_task_id` = single-blocker shorthand) emits RECORD_DEP PER named node —
provisional discovered edges (provenance = the BLOCK, T11; one BLOCK may surface several prerequisites,
an edge each); RESOLVE_BLOCK adjudicates the set: payload-free = confirm all, `blocker_task_ids` = the
corrected FULL set (SET semantics — unlisted provisionals retract, listed sources confirm), `external` =
retract all (non-producible blocker → the FM-5 currency line). An escalated-unresolved provisional stays
counted — this is what feeds q_Dep's denominator.

## Design Decisions

**Validation at the SEAM (D6, §6.5).** A node is PUBLIC ⟺ it is a delegation seam: a root, or
Del(child) ≠ Del(parent). The verifier≠executor gate (engine/validation.py) demands a recorded
independent verdict ONLY there; an INTERNAL node (same Del as its parent — the executor's own private
decomposition) legitimately self-verifies (its DELIVER carries `self_validation`), and its guarantee is
carried by the validation of the public result it rolls up into (T1 non-redundancy). The dispatcher's
auto-validation instrument follows the same rule (`GFSO_VALIDATE_INTERNAL=1` = the opt-in
every-delivery dial for measurement runs). The ROOT is always a seam: "done" (root DONE/PASS) never
completes on a self-stamp. Revision reasons are typed in the packet (§16.5:
`spec_defect | scope_expansion | capability_mismatch | other`) — q_T counts typed spec-defect criteria
changes, q_Del narrows to capability_mismatch where typed and keeps its documented over-approximation
where untyped.

**Guarded transition (VALIDATING + FAIL).** Only transition with a guard. Iteration counter lives in graph task node, not FSM state — FSM stays memoryless except for this one predicate read. Alternative was splitting FAIL/FAIL_FINAL into two signals, but that inflates the signal set for what is a single semantic action (validation failed).

**DONE is one state.** DONE(pass), DONE(fail), DONE(auto), DONE(cancelled) are the same FSM state with different metadata in the graph. Simplifies the FSM — terminal is terminal. Reason is recorded by MutateGraph for metrics.

**BLOCKED timeout → ESCALATED directly.** Other timeouts go through TIMEOUT state first. BLOCKED skips this: the block itself IS the escalation signal. The team already knows there's a problem. Adding a TIMEOUT intermediate is unnecessary indirection.

**CHALLENGED timeout → TIMEOUT (escalates, §6.3).** A pending challenge that times out is an unresolved spec dispute, not a benign event — it escalates via the standard timeout sub-FSM (→ TIMEOUT → ESCALATED), never auto-accepts. (Earlier drafts auto-accepted → REVIEW; that silently resolved a dispute in the issuer's favour and was removed — matches table row and canon §6.3.)

**VALIDATING timeout now includes Dispatch.** Executor must be notified that their delivery was auto-accepted. Symmetry with all other terminal transitions.

**TIMEOUT is transient.** TIMEOUT state exists between first and second timeout. If CANCEL arrives before the next timeout monitor tick, task goes to CANCELLING instead of ESCALATED. This is a natural intervention window (one tick), not a designed guarantee. TIMEOUT accepts no progress signals (§6.3) — only repeated timeout or the universal CANCEL.

**CANCEL_ACK — two-step handshake (canon v3.7 §6.3, SYNCED).** Cancellation is `CANCEL(issuer)→CANCELLING→CANCEL_ACK(executor)→CANCELLED`, mirroring ASSIGN→ACCEPT. CANCEL_ACK is an FSM-deadlock signal: the sole staffed exit from CANCELLING, carrying the executor's in-flight state (`SignalData.in_flight`) onto the audit log (T11). `CANCELLING--timeout-->CANCELLED` — cancellation is authoritative, executor silence still completes it (without the in-flight report). The cascade fires on CANCEL (entering CANCELLING): every live descendant gets its own CANCEL and runs its own handshake.

**Revision = re-ASSIGN, same id (canon v3.7 §6.4 Inv-1, SYNCED).** A packet change on a live node is ONE re-ASSIGN under the same id → REVIEW (the executor re-ACCEPTs/CHALLENGEs); the APPLY_SPEC mutation re-authors in place and the superseded version lives in the append-only log (Inv-7). No CANCEL signal, no CANCELLING pass, no cascade — subtree retained; staleness surfaces via CHECK-1/CHECK-1b/CHECK-3. Not accepted from TIMEOUT (no progress signals), CANCELLING, or terminals.

**REWORK has no CHALLENGE.** REWORK criteria = same criteria as original ASSIGN (immutable per protocol invariant). Challenging criteria you already executed against is incoherent. REWORK only accepts DELIVER or BLOCK.

**BLOCKED → RESOLVE_BLOCK always → EXECUTING.** Even if entered from REWORK. EXECUTING and REWORK have identical allowed signals (DELIVER, BLOCK, timeout). The iteration counter in graph state preserves rework context. No semantic difference.

**Iteration counter in graph task node.** `task.iteration: int`. Incremented on REWORK entry. Checked by FSM guard on FAIL. Counter is graph state, not FSM state.

## Typed Effects

```python
@dataclass
class MutateGraph:
    task_id: TaskId
    mutation: MutationType       # → graph/

@dataclass
class RunChecks:
    task_id: TaskId              # → handlers/

@dataclass
class Recommend:
    task_id: TaskId              # → handlers/

@dataclass
class Dispatch:
    task_id: TaskId
    signal: Signal               # → adapters/agents/

```

EmitSignal removed — was only used for ESCALATE which is now handled by repeated timeout.

## Runtime: Event Loop

```python
# engine/loop.py — event loop (L2)
def event_loop(graph, agents, llm, queue, audit, events):
    while True:
        signal = queue.get()
        state = graph.get_state(signal.task_id)

        # Guard context for transitions that need it
        ctx = graph.get_guard_context(signal.task_id)  # {iteration, max_iterations}

        transition = fsm.transition(state, signal, ctx)
        if transition is None:
            reject(signal); continue

        new_state, effects = transition

        for effect in effects:
            match effect:
                case MutateGraph(task_id, mutation):
                    affected = graph.apply(task_id, mutation)
                    for child_id in affected:          # cascade: affected children
                        queue.put(CancelSignal(child_id))
                case RunChecks(task_id):
                    task = graph.get_task(task_id)
                    children = graph.get_children(task_id)
                    results = handlers.run_checks(task, children)
                    graph.store_check_results(task_id, results)
                case Recommend(task_id):
                    ctx = graph.build_context(task_id)
                    recommendation = handlers.recommend(ctx)
                    graph.store_recommendation(task_id, recommendation)
                case Dispatch(task_id, sig):
                    agent = graph.get_assignee(task_id)
                    payload = graph.build_dispatch_payload(task_id, sig)
                    response = agents.dispatch(agent, payload)
                    if response:
                        queue.put(response)

# Background: timeout monitor
def timeout_monitor(graph, queue):
    while True:
        sleep(CHECK_INTERVAL)
        for task in graph.active_tasks():
            if task.timed_out():
                queue.put(TimeoutSignal(task.id))
```

**Key changes from v3:**
- `graph.apply()` returns affected child task_ids, not signals. main.py decides to emit CANCEL for each. Signal generation stays in composition root, not graph.
- `handlers.run_checks()` returns results. Stored in graph for Dispatch payload and metrics.
- `handlers.recommend()` returns recommendation. Stored in graph for Dispatch payload.
- `fsm.transition()` takes guard context as third argument.

## Module Structure (current layout; the layer rules are ENFORCED by tests/test_layering.py)

```
gfso/
  core/                     ← L0: the protocol STANDARD (canon-governed; pure, zero deps)
    types/
      primitives.py         # Task, Spec, Criteria (full: input/expected/n/timeout), DepEdge, SignalData
      enums.py              # State(12; DONE/CANCELLED quasi-terminal §6.3), Signal(13 = 12 protocol
                            # + TIMEOUT), Verdict, FM(7), RevisionReason (§16.5 typing)
      effects.py            # MutateGraph (incl. dep_from/dep_froms), RunChecks, Recommend, Dispatch
      ports.py              # StoragePort (mandatory core incl. the append-only signal log),
                            # LLMProviderPort, AgentPort, VerifierPort, ClockPort, RunnerPort
                            # (+ their stdlib defaults SystemClock/ThreadRunner — zero-dep, live here)
    protocol/               # fsm.py = THE TABLE · invariants.py · validation.py (role map)
    handlers/               # CHECK-1-6 structural · CHECK-7-8 numeric-bound tier (capability-honest
                            # skips; the formula/solver tier is a declared, unimplemented extension)
    graph/                  # model · mutations (incl. RECORD_DEP/ADJUDICATE_DEP) · metrics (∅→None) · projection

  engine/                   ← L1: the reference runtime (imports CORE ONLY — the layer gate)
    loop.py                 # process_signal = the substrate-free protocol step; event_loop = the
                            # default pump; timeout_monitor reads the ClockPort (Инв-5)
    __init__.py             # Engine facade (takes clock=/runner= ports); audit.py; events.py; validation.py
                            # (verifier≠executor gate; record_reviewer_verdict refuses reviewer==Del)

  tools.py                  ← L1: the STRUCTURAL action surface (core+engine only; ships with the core dist)
  tools_llm.py              ← L2: the LLM verbs (auto_decompose/review_decomposition/validate_result); its TOOLS =
                            #     the COMPLETE transport registry (structural ∪ LLM)

  adapters/                 ← port implementations (import core only)
    storage/ (sqlite, memory) · agents/ (human, …) · llm/ (stub | headless Claude CLI, generic
    OpenAI-compatible) · verifiers/

  decompose/ · critic/ · delegate.py · runtime.py   ← L2: the AI product (search↔audit monada,
                            # L2 validate, registry+dispatcher, DI/llm_factory/ProjectRegistry)
  mcp/ · api/ · web/ · cli.py · driver.py · main.py ← binding: the doors (generated from tools_llm.TOOLS)

packaging/core_manifest.py  ← THE gfso-core cut line (core + engine + tools.py + neutral stdlib
                            # adapters); closure + zero-deps proven by tests/test_core_dist.py;
                            # build_core.py builds the wheel (version injected from the main pyproject)
examples/                   ← one working script per entry door (tests/test_examples.py runs the
                            # deterministic ones live)
```

## Dependency Matrix (mechanically enforced — a violation is a red CI)

```
core/            → core/ only          (hermetic; stdlib-only)
engine/          → core/               (the ONE framework edge)
tools.py         → core/ + engine/     (structural surface — no LLM, no adapters)
adapters/        → core/               (port implementations)
decompose|critic|delegate|runtime|tools_llm → anything below binding
mcp|api|web|cli|driver|main            → everything (and NOTHING below imports them)
```


## Why Each Module Exists (forcing argument)

**Level 1 (core/):**

| Module | Why it exists | Merge with any neighbor → breaks what |
|---|---|---|
| types/ | Zero deps, everything depends on it | Merge anything IN → import cycles |
| protocol/ | Pure FSM table + invariants + role validation | Merge with graph → FSM depends on storage |
| handlers/ | Effect execution: checks + recommend | Merge with protocol → pure FSM becomes impure. Merge with graph → state acquires check/LLM concerns |
| graph/ | Persistent state + mutations + metrics | Merge with protocol → FSM depends on storage. Merge with handlers → state acquires check/LLM concerns |

**Level 2 (engine/):** Single module. Imports all of core/, provides framework API. Cannot be split further — audit, events, validation, loop are tightly coupled around the signal processing pipeline.

**Level 3 (adapters/, main.py):** Pluggable. Implements core/ ports. engine/ doesn't know which adapters exist.

No upward dependencies. L1 never imports L2. L2 never imports L3.

## Level-2 semantic validation — the ONE map (canon §5.4)

⚠ Naming collision, named explicitly: "L1/L2/L3" above = CODE LAYERS; "Level 0/1/2" here =
the canon's CHECK levels (§5.4: L0 topology · L1 formal entailment · **L2 = causal/semantic
correctness, pre-contact**). The two scales are unrelated. (The collision feeds the parked
naming-overhaul; until then this section is the disambiguation.)

Level 2 is NOT one component — it is one FUNCTION with four deliberate surfaces, split by
the QUESTION each asks. Two prior designs are deliberately dead: the monolithic analyst⊥judge
critic (E2-refuted: polices form, cannot move content) and the SEARCH-in-diff-mode hole-hunt
as the standalone verb (the opposite extreme — "what is missing" is the DECOMPOSER's question;
it lives in refine and only there):

| Surface | Question it asks | Where | Who needs it |
|---|---|---|---|
| **L2-inside-decompose** | "what is missing from the space" (recall) | `decompose/loop.py` search↔audit at build/refine time | every `auto_decompose` graph — the DEFAULT path; on-demand re-runs = the "AI refine" button / refine rounds |
| **Standalone L2 CHECKER** | "does the DECLARED mapping causally entail" (§5.4's own question): per parent criterion — mapped children's criteria taken as facts ⇒ sufficient / insufficient-with-named-gap / uncertain; + semantic FM-2 conflicts CHECK-8 can't see | `critic/runner.py` (frozen role `critic/prompts/checker.md`), exposed as `review_decomposition` (MCP · `POST /api/run/review_decomposition` · CLI; the name split is deliberate: `review_*` = pre-contact over the PLAN, `validate_result` = post-contact over the RESULT) | externally-authored / hand-edited graphs that never passed through decompose |
| **UI door** | the same checker, one click | the sidebar "AI review" button; per-criterion verdicts rendered, ADVISORY (fix via FSM verbs or declare NEGLECTED) | the pure-UI human — the ONLY consumer for whom the standalone checker is load-bearing |
| **Runtime detection** | "did a mapping that LOOKED sufficient fail live" | `core/graph/metrics.py::q_D` | everyone — **the real Level-2 verdict**: the axis is checkable only by execution (§5.4-bis) |

Epistemic status, held everywhere (§5.4-bis/§18.1): no pre-contact instrument VERIFIES Level 2 —
the checker is the canon's LLM-review APPROXIMATION (an a-priori estimate over the faithfulness
axis; its own verdict is itself a Level-2 claim), which is why it is advisory by construction
and q_D keeps the last word. Staging (critic/runner.py): the L0/L1 structural gate BLOCKS the
checker — L2 presupposes a structurally complete graph; the verdict never auto-fixes; an
INCOMPLETE per-criterion verdict is treated as NO verdict (never read as clean). Run economics
follow §5.4-bis's marginal rule (VERIFY while marginal c_check < prevented FORM-risk): L0 is
mandated, the checker is ON-DEMAND — spent where the caller judges the risk worth one call
(hand-authored graphs, external issuers, load-bearing seams), never auto-fired per ASSIGN.
`validate_result` is NOT on this map: it is EXECUTION validation, post-contact — the contact
itself, not a pre-contact check level (a recurring conflation, named here on purpose).

## System LLM vs Agent LLM

| | System LLM | Agent LLM |
|---|---|---|
| Location | core/handlers/recommend.py | adapters/agents/llm_agent.py |
| Prompts | Ours, fixed — our IP | User's, custom |
| Graph access | Receives hydrated GraphContext | No graph access |
| Replaceable | No (or at own risk) | Yes, fully pluggable |
| Effect type | Recommend | Dispatch |
| Paper section | §7.3 (AI layer) | §6.5 (agent-agnostic role filler) |

Both use LLMProviderPort (in core/types/ports.py). Different roles, different locations, shared provider.

## Runtime Model

- **Engine** (engine/) receives signals via `send_signal()` or `assign_task()` → queue
- **Event loop** (engine/loop.py) validates → FSM transition → pre-validates effects → executes → audit → events
- **Timeout monitor** (background) fires on the node deadline AND — opt-in — on per-state age: every
  state change stamps `state_entered_at`, and a state older than `GFSO_STATE_TIMEOUT` seconds emits
  the timeout trigger. **Default 0 = OFF**: the mechanism for Инв-5 finiteness beyond node deadlines
  is built and tested, but the clock-binding question is OPEN (a real deployment should anchor to
  real UTC dates or stronger — tamper-resistant time is an implementor's open end); a deadline-less
  node therefore waits indefinitely unless the knob is set. Deduplicated per state VISIT —
  (task, state, `state_entered_at`): keying on the last-fired state alone went silent when an R′
  reopen re-entered a fired-in state through a terminal (an Инв-5 hole found by the TLC spike model,
  see `formal/tla/README.md`); a state change restamps the entry, so a re-entered state fires again.
- **Graph store** persists G via StoragePort
- **Audit trail** records every signal with timestamp, old/new state, effects, errors — APPEND-ONLY in
  storage (SQLite `audit_log` table): the log hydrates on engine construction, so the T11/Инв-7 trail
  survives restarts (in-memory only on MemoryStorage, consistent with its ephemerality)

## Ablation Support

| Remove | Effect on system |
|---|---|
| core/handlers/constraint.py | CHECK-7-8 skipped. CHECK-1-6 still work |
| core/handlers/recommend.py | Recommend becomes no-op. Protocol + graph + checks still work |
| adapters/llm/ | System + Agent LLM degraded to stubs. Everything else works |
| adapters/agents/llm_agent.py | No AI workers. Human agents still work |
| engine/ | Use core/ as pure library. Call protocol.transition() + mutations.apply() directly |

---

# v3.6 — mutation surface, closure & interfaces

> This section extends the CORE-FSM architecture above with the track-b work (the upper authoring layer, the
> single-chokepoint closure, decompose, and the one-action-surface/three-transport interface model). A few of
> the earlier v4-era FSM details above predate track-b and are pending a fuller doc-reconciliation pass; where
> they conflict, THIS section is current (e.g. Recommend is no longer auto-emitted on ASSIGN; CHALLENGED-timeout
> escalates rather than auto-accepting; revise does not cascade — see below).

## Two layers — every mutation is a logged signal
Any actor (human via UI, agent via MCP/CLI) mutates the graph through the SAME closed FSM — there is no exit from it.

```
   UI / MCP / CLI            — thin transports; send upper-layer calls
        │
   UPPER API (convenience compositions — read-modify-write):
     decompose · revise · reneglect · edit_criteria · reassign · add/remove_dependency · map_criterion
        │  desugars to ↓ (never bypasses)
   LOWER API = THE CANON FSM — send_signal() + reads
     CLOSED alphabet: 12 P2P signals + TIMEOUT (frozen by test):
     ASSIGN ACCEPT CHALLENGE BLOCK DELIVER CANCEL_ACK ACCEPT_CHALLENGE REJECT_CHALLENGE PASS FAIL CANCEL RESOLVE_BLOCK
     every signal → audited mutation (loop → audit). No 13th.
        │
   graph / storage
```

### Authoring ops are NOT new signals — they desugar to existing ones
| Upper op | Desugars to (lower) | Notes |
|---|---|---|
| create | `ASSIGN` (IDLE → CREATE_TASK effect) | node creation IS the ASSIGN effect (logged) |
| decompose | one `ASSIGN` per child (+ `covers` → parent mapping effect) | mappings = the child's declaration, logged; a FULL mappings list SETS the parent's coverage (pairs absent from it are removed — reconcile); `None` adds without wiping |
| **revise** | re-`ASSIGN` (SAME id) → REVIEW | revision per Inv-1 §6.4 (v3.7): NOT a CANCEL; version appended to the log (Inv-7); **subtree RETAINED — no cascade**; staleness surfaces via CHECK-1/1b/3; issuer-gated |
| reneglect / edit_criteria | revise (RMW) | change one field, carry the rest |
| add_dependency (declared) | re-`ASSIGN` of the **consumer** (gains a `depends_on` criterion) | Dep is criteria-content (§2.2); edge derived |
| map_criterion | re-`ASSIGN` of the child carrying `covers` | binds an existing child to a parent criterion (logged) |
| reassign | re-`ASSIGN` with a new executor | Del change per Inv-1 (q_Del) |
| **reopen** | re-`ASSIGN` out of DONE/CANCELLED → REVIEW | R′ (§6.3): double-gated (finality of consumption ∧ max_reopens); verdict re-earned, never resurrected; consumed terminal = finally locked (recover by re-decomposition) |
| **abandon** | `CANCEL` → CANCELLING → `CANCEL_ACK` → CANCELLED | two-step handshake (§6.3); **cascades CANCEL to subtree**; never deleted (§7.3.1) |

**Surface-don't-destroy** (canon v3.7, SYNCED). abandon = `CANCEL` → opens the handshake and cascades the
subtree (its sub-work served a contract that no longer exists, §7.1); each node settles CANCELLING→CANCELLED
on its executor's CANCEL_ACK (or timeout — cancellation is authoritative). revise = re-`ASSIGN` (same id) →
the node continues under a new contract in REVIEW: its **subtree is RETAINED, no cascade**; coverage staleness
(uncovered new criterion / dangling mapping) is SURFACED by CHECK-1 / non-redundancy for the agent to resolve
∨ declare, not destroyed. The only IN-PLACE spec change is `ACCEPT_CHALLENGE`.

## Decomposition surface — one operation over graph state (canon v3.8 era)

`auto_decompose` is the single decomposition verb, dispatched by the target's state; `depth` N ≡ init +
(N−1) refine applications of the same operation:

- **init** (empty project / undecomposed node): one SEARCH (exhaustive recall) + one AUDIT fold over the
  EMPTY state → the graph-form spec; the root node itself is authored from the request (no hand-created
  root); built through the FSM (`build_graph_live`) and verified (`list_holes` + a bounded patch-repair
  loop — an honest `holes` residue, never a silent partial).
- **refine** (an already-decomposed node; also recursion = the same verb on a child): BOTH roles read
  the graph's REAL projection (+ any unmet checks); the auditor emits a FOLD-PATCH (add/update/remove),
  applied to the extracted graph state (`extract.py` = the exact data inverse of the build; patch ids
  normalized from the projection's namespace) — converged content is never re-emitted, so it cannot be
  dropped or compressed; the merge is deterministic and the result rebuilds wholesale as a REVISION.
  Early exits: ALREADY-COVERED (searcher) / an empty fold (auditor).
- **The live graph only ever holds verified states, and a rebuild is idempotent + jurisdiction-aware:** an
  untouched child receives ZERO signals (an executing node keeps executing); each operation authors only its
  own level — the target node's criteria/NEGLECTED/scope and the children's contracts + coverage + seams;
  the children's Del and their OWN registers belong to other authors (the issuer; the child's own
  decomposer, §5.1) and pass through untouched.
- **Removal is surfaced, never silent:** coverage reconciles to the decomposer's full mapping set, so a
  child the auditor dropped becomes an unmapped (non-redundancy) hole — visible in the streamed fold ops,
  the returned `holes`, and `list_holes`/UI/frontier — and abandoning the work itself stays the issuer's
  explicit `CANCEL`.
- There is NO separate prose representation: the one textual read of the state — for the refine roles,
  the returned artifact, and any human — is the graph's own projection (`Engine.project`).

## Closure invariant (proven)
- **Static:** every authored-state write lives in `core/graph/mutations.py::apply`, called ONLY by
  `engine/loop.py::_execute_effects` (the event loop), which records an audit entry per signal.
- **Build:** `decompose` builds THROUGH the FSM (`build_graph_live`); the old offline `build_graph` (direct
  `save_task`) was DELETED — one build path, no offline authored-state write.
- **Discovered-Dep is signal-driven (v3.7, closed):** BLOCK carrying `blocker_task_ids` (or the singular
  shorthand) emits RECORD_DEP per named blocker (provisional edges), RESOLVE_BLOCK emits ADJUDICATE_DEP
  (confirm all / corrected full set / retract all) — both through `mutations.apply` (§6.2/§7.2).
  `add_dependency(discovered=True)` remains as a test/offline convenience only, off every HTTP/MCP/CLI
  surface.
- **Derived caches** (check results, `verified`, critique, recommendation) persist but carry NO authored-contract
  state — recomputable projections of signal-driven state, not mutations.

⟹ A hole in mutability appears ONLY if code writes graph state outside `apply` (grep `save_task`); a duplicate of
a verb appears ONLY if logic is put in a transport instead of the Engine. Both are single, greppable invariants.

## Interfaces — one Engine, one action surface (`tools.py`), three transports
The **Engine is the single source of all logic**; `gfso/tools.py` is the SINGLE action surface over it; the three
transports (MCP · CLI · HTTP) are GENERATED from that one `TOOLS` registry. Adding an authoring verb = ONE Engine
method + ONE `tools.TOOLS` entry → it appears on all three at once, zero per-adapter edits.

```
   Engine (CORE)  ── the one place all logic lives; every verb is an Engine method
     │
   gfso/tools.py  ── the SINGLE action surface: (engine,*args) → JSON dict, one fn per verb (TOOLS registry)
     ├─ gfso/mcp     MCP server — binds each TOOLS fn as an MCP tool (stdio)          ← the agent
     ├─ gfso/driver  `gfso run` — binds each TOOLS fn to argv                          ← scripts / CI / subagents
     └─ gfso/api     HTTP `POST /api/run/{tool}` — dispatches to TOOLS                 ← the UI (browser client)
                     (+ bespoke typed GET reads: task detail / graph / metrics / …)
```

- `runtime.build_engine_from_env` = the shared CORE constructor (one Engine from `GFSO_DB_PATH`).
- HTTP **reads** stay bespoke typed routes (view-specific shapes for the UI — reads aren't a mutation surface).
- **Live mirroring:** one process (`gfso mcp` / `gfso serve --mcp`) hosts MCP + HTTP + UI over ONE Engine, so the
  UI's `/ws/events` reflects the agent's writes live. Separate processes share only SQLite (poll, no live WS).
- **Versioning:** the transports + the UI are DERIVED mirrors of the Engine's verb surface (via `tools.py`).

---

# The scaling contract — semantic vs runtime invariance

> Embedding the core as a library into your own host (storage/clock/runtime behind the ports)
> has its own pre-registered acceptance suite and wiring reference: `docs/embeddability_acceptance.md`.

**What embedding at scale PRESERVES (guaranteed — semantic invariance).** The protocol semantics
are pure per-node functions: `fsm.transition(state, signal, guard_ctx)`, the invariants, the L0/L1
checks, and the Q metrics are all computed from one node (+ its children/edges) with no hidden
global state; system state is `fold(log)` over the append-only signal log (StoragePort mandatory
core). One signal's full step is `engine.loop.process_signal` — substrate-free (no thread, no
blocking queue). Conformance is therefore TRACE-CHECKABLE: replay a signal log through
`process_signal` on any host and the states must match.

**What it does NOT preserve (by design — no runtime invariance).** A loaded distributed host
(Spark/Flink/stream processor, multi-region) rewrites the RUNTIME 100%: the stdlib defaults
(SystemClock, ThreadRunner, queue pump, timeout monitor thread) are reference plumbing, not the
product. The seams are ports — ClockPort, RunnerPort, StoragePort, LLMProviderPort/AgentPort —
and the rewrite happens BEHIND them; the FSM table, mutations, checks and metrics are not touched.

**Named discipline points for a distributed runtime (the FSM does not change):**

- **Operational trichotomy needs no global clock (happens-before is already enough).** The three
  operational phases (before / concurrent / after an evaluation event) are a partition by a strict
  CAUSAL order — no single clock is assumed (canon §4.8: Axiom 2 is discharged, the phase count is
  axiom-free). Distributed time = happens-before partial order IS that causal order, so the taxonomy
  holds directly; the middle cell just reads as "concurrent" (FM-5 = a read/write race) instead of
  "during". Watermarks/partition-local validation events are needed only for the optional *linear*
  reading, not for the taxonomy.
- **Cross-shard AND-aggregation + the verifier≠executor gate → partition by SUBTREE.** A project
  boundary is already a Dep-closure boundary (ProjectRegistry) — the ready-made partition unit.
  Traffic is leaf-heavy/root-light, so the tree shape matches the load shape; a root spanning
  shards needs a saga over child-PASS events, not a distributed transaction.
- **Dispatch effects → idempotency.** Effects may be re-delivered on a distributed substrate;
  consumer-side dedup is the discipline (the dispatcher's node×iteration dedup key is the
  reference pattern).
- **T11 total log order → partial order + merge.** The single-process log is totally ordered;
  shards produce per-partition logs. `state = fold(log)` survives as fold over a merged partial
  order IF each node's signals stay on one partition (subtree partitioning gives exactly that).
- **Read scale is not the core's problem.** 100k readers of a public graph = CQRS / materialized
  views over the log; the write path (the FSM) does not participate.

