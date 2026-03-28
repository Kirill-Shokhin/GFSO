# GFSO Architecture v4

## Invariant

**The FSM transition table IS the architecture.** `(State, Signal, Guard) → (NewState, [Effects])`. The table is the single source of truth for all system behavior. No hidden middleware, hooks, or plugins. If something happens, a row in the table says so.

Guards are simple predicates on graph state (only where needed — currently one: iteration check). Effects are skeletal (task_id only). The event loop hydrates effects from graph + signal data before passing to handlers.

**Division of responsibility:** FSM decides WHICH effects. Graph provides DATA. Handlers EXECUTE. Main.py COMPOSES.

## FSM Transition Table (from paper §6 + vision doc)

```
(State, Signal, Guard)           → NewState      Effects
───────────────────────────────────────────────────────────────────
(IDLE, ASSIGN)                   → REVIEW        [MutateGraph, RunChecks, Recommend, Dispatch]
(REVIEW, ACCEPT)                 → EXECUTING     [MutateGraph, Dispatch]
(REVIEW, CHALLENGE)              → CHALLENGED    [MutateGraph, Dispatch]
(REVIEW, timeout)                → TIMEOUT       [MutateGraph]
(CHALLENGED, ACCEPT_CHALLENGE)   → REVIEW        [MutateGraph, RunChecks, Dispatch]
(CHALLENGED, REJECT_CHALLENGE)   → EXECUTING     [MutateGraph, Dispatch]
(CHALLENGED, timeout)            → REVIEW        [MutateGraph]          # auto-accept, see below
(EXECUTING, DELIVER)             → VALIDATING    [MutateGraph, Dispatch]
(EXECUTING, BLOCK)               → BLOCKED       [MutateGraph, Dispatch]
(EXECUTING, timeout)             → TIMEOUT       [MutateGraph]
(BLOCKED, RESOLVE_BLOCK)         → EXECUTING     [MutateGraph, Dispatch]
(BLOCKED, timeout)               → ESCALATED     [MutateGraph]          # direct, see below
(VALIDATING, PASS)               → DONE          [MutateGraph, Dispatch]
(VALIDATING, FAIL, iter < max)   → REWORK        [MutateGraph, Dispatch]
(VALIDATING, FAIL, iter >= max)  → DONE          [MutateGraph, Dispatch] # reason=fail in mutation
(VALIDATING, timeout)            → DONE          [MutateGraph, Dispatch] # reason=auto in mutation
(REWORK, DELIVER)                → VALIDATING    [MutateGraph, Dispatch]
(REWORK, BLOCK)                  → BLOCKED       [MutateGraph, Dispatch]
(REWORK, timeout)                → TIMEOUT       [MutateGraph]
(TIMEOUT, timeout)               → ESCALATED     [MutateGraph]          # repeated timeout
(ANY_NON_TERMINAL, CANCEL)       → DONE          [MutateGraph, Dispatch] # reason=cancelled
```

Terminal states: DONE (with reason: pass/fail/auto/cancelled), ESCALATED.

DONE is one state. Completion reason is metadata in MutateGraph mutation, not a separate FSM state. 10 states in enum: IDLE, REVIEW, CHALLENGED, EXECUTING, BLOCKED, VALIDATING, REWORK, DONE, TIMEOUT, ESCALATED.

ESCALATED resolution is outside FSM — admin action (re-assign or close). Escalation crosses hierarchy levels which the per-task FSM cannot model.

## Design Decisions

**Guarded transition (VALIDATING + FAIL).** Only transition with a guard. Iteration counter lives in graph task node, not FSM state — FSM stays memoryless except for this one predicate read. Alternative was splitting FAIL/FAIL_FINAL into two signals, but that inflates the signal set for what is a single semantic action (validation failed).

**DONE is one state.** DONE(pass), DONE(fail), DONE(auto), DONE(cancelled) are the same FSM state with different metadata in the graph. Simplifies the FSM — terminal is terminal. Reason is recorded by MutateGraph for metrics.

**BLOCKED timeout → ESCALATED directly.** Other timeouts go through TIMEOUT state first. BLOCKED skips this: the block itself IS the escalation signal. The team already knows there's a problem. Adding a TIMEOUT intermediate is unnecessary indirection.

**CHALLENGED timeout = auto-accept.** Goes directly to REVIEW without emitting ACCEPT_CHALLENGE. This is NOT a silent mutation — the timeout signal arrives through the queue like any other signal. The FSM processes it and transitions. The MutateGraph effect records the auto-accept. No signal emission needed because auto-accept is benign (return to REVIEW), not an escalation.

**VALIDATING timeout now includes Dispatch.** Executor must be notified that their delivery was auto-accepted. Symmetry with all other terminal transitions.

**TIMEOUT is transient.** TIMEOUT state exists between first and second timeout. If CANCEL arrives before the next timeout monitor tick, task goes to DONE instead of ESCALATED. This is a natural intervention window (one tick), not a designed guarantee.

**CANCEL_ACK is not a protocol signal.** CANCEL → DONE is immediate. CANCEL_ACK is a notification from dispatcher to agent ("your task was cancelled"). Handled by adapters, no state change, no FSM row.

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
