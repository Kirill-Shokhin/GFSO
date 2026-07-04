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
(REVIEW, ACCEPT)                 → EXECUTING     [MutateGraph, Dispatch]
(REVIEW, CHALLENGE)              → CHALLENGED    [MutateGraph, Dispatch]
(REVIEW, timeout)                → TIMEOUT       [MutateGraph]
(CHALLENGED, ACCEPT_CHALLENGE)   → REVIEW        [MutateGraph, RunChecks, Dispatch]
(CHALLENGED, REJECT_CHALLENGE)   → EXECUTING     [MutateGraph, Dispatch]
(CHALLENGED, timeout)            → TIMEOUT       [MutateGraph]          # escalates §6.3 (§v3.6: no auto-accept)
(EXECUTING, DELIVER)             → VALIDATING    [MutateGraph, Dispatch]
(EXECUTING, BLOCK)               → BLOCKED       [MutateGraph, Dispatch] # +RECORD_DEP when blocker_task_id named (§6.2)
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
```

Terminal states: DONE (with reason: pass/fail/auto), ESCALATED, CANCELLED (V=⊥).

DONE is one state; completion reason is metadata in the MutateGraph mutation. Cancellation is NOT a DONE
reason — canon v3.7 §6.3 gives it its own two-step handshake `CANCEL→CANCELLING→CANCEL_ACK→CANCELLED`
(mirror of ASSIGN→ACCEPT; CANCEL_ACK = the sole staffed exit from CANCELLING, an FSM-deadlock signal
carrying the executor's in-flight report). **12 states in enum**: IDLE, REVIEW, CHALLENGED, EXECUTING,
BLOCKED, VALIDATING, REWORK, CANCELLING, DONE, CANCELLED, TIMEOUT, ESCALATED. Pre-v3.7 DBs stored
cancellation as DONE(reason=CANCELLED) — migrated on read in the SQLite adapter.

ESCALATED resolution is outside FSM — admin action (re-assign or close). Escalation crosses hierarchy levels which the per-task FSM cannot model.

**Discovered-Dep (§6.2/§7.2, two-phase):** a BLOCK naming an undeclared prerequisite NODE
(`blocker_task_id`) emits RECORD_DEP — a provisional discovered edge (provenance = the BLOCK, T11);
RESOLVE_BLOCK adjudicates it: payload-free = confirm, `blocker_task_id` = re-attribute, `external` =
retract (non-producible blocker → the FM-5 currency line). An escalated-unresolved provisional stays
counted — this is what feeds q_Dep's denominator.

## Design Decisions

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

## Module Structure

```
gfso/
  core/                     ← Level 1: protocol standard (pure library, zero runtime)
    types/
      primitives.py         # Task, Spec, Criteria, CriterionMapping, DepEdge, GuardContext
      enums.py              # State(10), Signal(13), Verdict, FM(7), AutonomyLevel
      effects.py            # MutateGraph, RunChecks, Recommend, Dispatch
      ports.py              # StoragePort, LLMProviderPort, AgentPort
    protocol/
      fsm.py                # (State, Signal, GuardContext) → (NewState, [Effect]) — THE TABLE
      invariants.py         # Criteria immutability, binary V, FAIL requires criteria
      validation.py         # Signal role mapping from paper §6.2
    handlers/
      structural.py         # CHECK-1-6: coverage (CriterionMapping), DAG, deadlines, NEGLECTED, risk_components, delegation
      constraint.py         # CHECK-7-8: sufficiency, consistency (optional Z3)
      recommend.py          # System LLM: neglected, decomposition, patterns
    graph/
      model.py              # G = (N, E_D, E_Dep, σ) over StoragePort
      mutations.py          # Mutation → G'. Cascade returns affected child ids. Invariant enforcement.
      metrics.py            # Q = (q_T, q_D, q_V, q_Dep, q_Del) — paper §7.2 formulas
      index.py              # Context building for Recommend + Dispatch

  engine/                   ← Level 2: framework (imports core only)
    __init__.py             # Engine facade: signal/query/metrics/events/audit/decomposition API
    loop.py                 # Event loop + timeout monitor (dedup). Pre-validates effects.
    audit.py                # AuditEntry signal log (Th.11 structural transparency)
    events.py               # EventBus: on_transition, on_error, on_reject (isolated callbacks)
    validation.py           # Signal role enforcement + invariant 3 check

  adapters/                 ← Level 3: pluggable implementations (imports core ports only)
    storage/memory.py       # In-memory StoragePort
    llm/stub.py             # Stub LLMProviderPort
    agents/human.py         # Human AgentPort (logging)
    agents/llm_agent.py     # LLM AgentPort (uses LLMProviderPort)

  main.py                   ← Level 3: CLI entry point
```

## Dependency Matrix

```
core/types/      → nothing
core/protocol/   → core/types
core/handlers/   → core/types (+ optional Z3)
core/graph/      → core/types (no protocol knowledge)
engine/          → core/ (types + protocol + handlers + graph)
adapters/        → core/types/ports only
main.py          → engine + adapters
```

No upward dependencies. No cycles. handlers/ and protocol/ both Layer 1 (pure on types). graph/ is Layer 2 (stateful, depends on types only — not protocol).

## Why Each Module Exists (forcing argument)

**Level 1 (core/):**

| Module | Why it exists | Merge with any neighbor → breaks what |
|---|---|---|
| types/ | Zero deps, everything depends on it | Merge anything IN → import cycles |
| protocol/ | Pure FSM table + invariants + role validation | Merge with graph → FSM depends on storage |
| handlers/ | Effect execution: checks + recommend | Merge with protocol → pure FSM becomes impure. Merge with graph → state acquires Z3/LLM deps |
| graph/ | Persistent state + mutations + metrics | Merge with protocol → FSM depends on storage. Merge with handlers → state acquires Z3/LLM deps |

**Level 2 (engine/):** Single module. Imports all of core/, provides framework API. Cannot be split further — audit, events, validation, loop are tightly coupled around the signal processing pipeline.

**Level 3 (adapters/, main.py):** Pluggable. Implements core/ ports. engine/ doesn't know which adapters exist.

No upward dependencies. L1 never imports L2. L2 never imports L3.

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
- **Timeout monitor** (background) checks deadlines → emits timeout signals (deduplicated per task)
- **Graph store** persists G via StoragePort
- **Audit trail** records every signal with timestamp, old/new state, effects, errors

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
| decompose | one `ASSIGN` per child (+ `covers` → parent mapping effect) | mappings = the child's declaration, logged |
| **revise** | re-`ASSIGN` (SAME id) → REVIEW | revision per Inv-1 §6.4 (v3.7): NOT a CANCEL; version appended to the log (Inv-7); **subtree RETAINED — no cascade**; staleness surfaces via CHECK-1/1b/3; issuer-gated |
| reneglect / edit_criteria | revise (RMW) | change one field, carry the rest |
| add_dependency (declared) | re-`ASSIGN` of the **consumer** (gains a `depends_on` criterion) | Dep is criteria-content (§2.2); edge derived |
| map_criterion | re-`ASSIGN` of the child carrying `covers` | binds an existing child to a parent criterion (logged) |
| reassign | re-`ASSIGN` with a new executor | Del change per Inv-1 (q_Del) |
| **abandon** | `CANCEL` → CANCELLING → `CANCEL_ACK` → CANCELLED | two-step handshake (§6.3); **cascades CANCEL to subtree**; never deleted (§7.3.1) |

**Surface-don't-destroy** (canon v3.7, SYNCED). abandon = `CANCEL` → opens the handshake and cascades the
subtree (its sub-work served a contract that no longer exists, §7.1); each node settles CANCELLING→CANCELLED
on its executor's CANCEL_ACK (or timeout — cancellation is authoritative). revise = re-`ASSIGN` (same id) →
the node continues under a new contract in REVIEW: its **subtree is RETAINED, no cascade**; coverage staleness
(uncovered new criterion / dangling mapping) is SURFACED by CHECK-1 / non-redundancy for the agent to resolve
∨ declare, not destroyed. The only IN-PLACE spec change is `ACCEPT_CHALLENGE`.

## Closure invariant (proven)
- **Static:** every authored-state write lives in `core/graph/mutations.py::apply`, called ONLY by
  `engine/loop.py::_execute_effects` (the event loop), which records an audit entry per signal.
- **Build:** `decompose` builds THROUGH the FSM (`build_graph_live`); the old offline `build_graph` (direct
  `save_task`) was DELETED — one build path, no offline authored-state write.
- **Discovered-Dep is signal-driven (v3.7, closed):** BLOCK carrying `blocker_task_id` emits RECORD_DEP
  (provisional edge), RESOLVE_BLOCK emits ADJUDICATE_DEP (confirm/re-attribute/retract) — both through
  `mutations.apply` (§6.2/§7.2). `add_dependency(discovered=True)` remains as a test/offline convenience
  only, off every HTTP/MCP/CLI surface.
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
