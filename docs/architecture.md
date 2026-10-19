# GFSO Architecture v4

## Invariant

**The FSM transition table IS the architecture.** `(State, Signal, Guard) → (NewState, [Effects])`. The table is the single source of truth for all system behavior. No hidden middleware, hooks, or plugins. If something happens, a row in the table says so.

Guards are simple predicates on graph state, read off `GuardContext` (`iteration`/`max_iterations` on the rework loop; `consumed`/`reopens`/`max_reopens` on the R′ finality gate). Effects are skeletal (task_id only). The event loop hydrates effects from graph + signal data before passing to handlers.

**Division of responsibility:** FSM decides WHICH effects. Graph provides DATA. Handlers EXECUTE. The composition root (`gfso/runtime.py::build_engine_from_env`, entered through `gfso/cli.py`) COMPOSES.

## FSM Transition Table (from paper §12 + vision doc)

> **Canon names = code identifiers (the v4.0 naming lag is CLOSED).** The enum migration landed:
> the code ships `OFFERED`, `REWORKING`, `ABANDONED` (the system trigger keeps the
> lowercase name `timeout`), `CONFIRM_CANCEL`, the register field `ACCEPTED_RISKS`, `AUTO_PASS`, and
> FM-3 `Veracity` / FM-5 `Freshness` — so a name in this document is the canon's and the code's at
> once. The read-shim that decoded the pre-migration spellings is gone with the migration that
> needed it: one vocabulary is written, and the same one is read. (One older read-map survives and is
> a different thing — a pre-v3.7 `DONE(reason=CANCELLED)` row is mapped to `ABANDONED` on read, which
> is why `DoneReason.CANCELLED` is still a member.) Section references here are v4.0 numbering.
>
> **The two rows that diverged from the canon in SHAPE are closed** (corners #3 and #1 of
> `formal/README.md`), so the table below is canon-shaped and no longer carries a declared gap.
>
> **(1)** `(VALIDATING, FAIL, iter >= max)` now targets **ESCALATED**, as §12.5 routes the exhausted
> `FAIL↔REWORKING` loop and as §8.3 requires ("DONE is reached through acceptance (PASS), **never through fail**" — v4.1; the
> parenthesis read "PASS ∨ auto_pass" while auto_pass existed). The canon has no "V = fail, settled" terminal — its negatives are
> ABANDONED = ⊥ and ESCALATED = attention — exhausting the retry loop IS the escalation trigger (§19.1:
> automatic handling failed ⟹ the "trust, but see" attention mode), and a DONE(fail) would additionally
> be consumable under R′, letting a Dep consumer read-and-build on a failure. The terminal carries
> `done_reason=FAIL`, so a verdict-escalation stays distinguishable from a timeout one and the
> standing-FAIL metric populations (q_D's exhausted arm, `false_fail_share`) still see it.
>
> **(2)** `(IDLE, timeout)` is **removed**: v4.0 Inv-5 exempts IDLE **by name** (§12.12), the pre-contract
> state having no clock of its own and its starvation surfacing as the parent's timeout. The motive the
> row was written for — a crash orphan, observable in IDLE because CREATE_TASK persisted while the
> ASSIGN's landing did not — is met where the defect lives: `Engine._recover_orphans` finishes the
> interrupted transition at startup, through the queue, validated and logged.

```
(State, Signal, Guard)           → NewState      Effects
───────────────────────────────────────────────────────────────────
(IDLE, ASSIGN)                   → OFFERED        [MutateGraph, RunChecks, Dispatch]   # Recommend removed
(OFFERED, ACCEPT)                 → EXECUTING     [MutateGraph, Dispatch]
(OFFERED, CHALLENGE)              → CHALLENGED    [MutateGraph, Dispatch]
(OFFERED, timeout)                → ESCALATED     [MutateGraph]          # the lapse hands over at once
(CHALLENGED, ACCEPT_CHALLENGE)   → OFFERED        [MutateGraph, RunChecks, Dispatch]
(CHALLENGED, REJECT_CHALLENGE, consented)  → EXECUTING  [MutateGraph, Dispatch] # back to the interrupted wait
(CHALLENGED, REJECT_CHALLENGE, ¬consented) → OFFERED    [MutateGraph, Dispatch] # no ACCEPT of this version yet
(CHALLENGED, timeout)            → ESCALATED     [MutateGraph]          # escalates §12.5 (no auto-accept)
(EXECUTING, DELIVER)             → VALIDATING    [MutateGraph, Dispatch]
(EXECUTING, BLOCK)               → BLOCKED       [MutateGraph, Dispatch] # +RECORD_DEP per named blocker (§11.2)
(EXECUTING, timeout)             → ESCALATED     [MutateGraph]
(BLOCKED, RESOLVE_BLOCK)         → EXECUTING     [MutateGraph(ADJUDICATE_DEP), MutateGraph, Dispatch] # confirm/re-attribute/retract (§11.2)
(BLOCKED, timeout)               → ESCALATED     [MutateGraph]          # direct, see below
(VALIDATING, PASS)               → DONE          [MutateGraph, Dispatch]
(VALIDATING, FAIL, iter < max)   → REWORKING        [MutateGraph, Dispatch]
(VALIDATING, FAIL, iter >= max)  → ESCALATED     [MutateGraph, Dispatch] # reason=fail carried onto the handover (§12.2)
(VALIDATING, timeout)            → ESCALATED     [MutateGraph, Dispatch] # T_validate alone, from DELIVER (§16.14)
(EXECUTING, CHALLENGE)           → CHALLENGED    [MutateGraph, Dispatch] # the post-consent dispute (§12.4)
(REWORKING, CHALLENGE)           → CHALLENGED    [MutateGraph, Dispatch]
(REWORKING, DELIVER)                → VALIDATING    [MutateGraph, Dispatch]
(REWORKING, BLOCK)                  → BLOCKED       [MutateGraph, Dispatch] # +RECORD_DEP as above
(REWORKING, timeout)                → ESCALATED     [MutateGraph]
(ESCALATED, timeout)             → CANCELLING    [MutateGraph, Dispatch] # the issuer's silence CLOSES, and the subtree cascades (§12.5)
(ESCALATED, ASSIGN)              → OFFERED       [MutateGraph(APPLY_SPEC), …]  # his revision: raise the bound / change the criteria
(CANCELLING, CONFIRM_CANCEL)         → ABANDONED     [MutateGraph, Dispatch] # in_flight logged (T11)
(CANCELLING, timeout)            → ABANDONED     [MutateGraph]          # cancellation is authoritative (§12.6)
(ANY_NON_TERM \ CANCELLING, CANCEL) → CANCELLING [MutateGraph, Dispatch] # opens the handshake; cascades CANCEL to subtree (§11.2)
(REASSIGNABLE, ASSIGN+spec)      → OFFERED        [MutateGraph(APPLY_SPEC), MutateGraph, RunChecks, Dispatch]
                                                 # REVISION (§12.3 Inv-1): re-ASSIGN same id, no cascade; excluded: IDLE, CANCELLING, terminals
(DONE|ABANDONED, ASSIGN,
   ¬consumed ∧ reopens<max)      → OFFERED        [MutateGraph(REOPEN), MutateGraph, RunChecks, Dispatch]
                                                 # R′ REOPEN (§12.10): a gated re-ASSIGN, NOT a 13th signal — see below
```

Terminal states: DONE (with reason: pass/auto — acceptance only, §8.3) and ABANDONED (V=⊥). **ESCALATED
is NOT terminal** (§12.5): it is the ISSUER's waiting state, the mirror under Inv-4 of OFFERED, where
the EXECUTOR owes the answer. It carries reason=fail when it was reached by the exhausted validation loop
rather than by a clock, and it admits his three answers — re-ASSIGN (raise the bound / change the
criteria, one act by Inv-1), CANCEL (close it, cascading the live subtree), and its own timeout, which
closes it through CANCELLING — silence must close rather than drift toward a pass, and must take
the live subtree with it, which escalation never touched. **DONE and ABANDONED
are QUASI-terminal (R′, §12.10):** a re-ASSIGN out of them is admitted under a DOUBLE gate — (i) the
finality-gate: the terminal is not CONSUMED, read off the log from the moment it settled and, once
logged, standing (§12.14) — the parent has not DELIVERed since (a later FAIL does not give the child back),
no Dep-consumer has stood in work on the result since, no re-admission since has given a criterion it is
mapped to a new covering child (a sibling co-covering from the first admission consumes nothing), and the
parent's current version still maps it to a criterion; a settled cascade alone consumes nothing); (ii) `reopens < max_reopens` (ONE sign-agnostic per-node counter next to
max_iterations, default 1 — restores Inv-5 finiteness for the new outgoing edge). Both gate inputs ride
GuardContext, computed by the graph in the SAME `process_signal` step as the edge — gate+edge are one
log-serialized atomic act (Inv-7, no TOCTOU with a concurrent DELIVER). The REOPEN mutation spends the
counter, drops `done_reason` (V=pass is RE-EARNED in OFFERED, never resurrected), and generation-stamps
stale the recorded independent verdict. The generation is `(iteration, reopens, revisions)` — the third
member because §12.10 admits a re-ASSIGN from VALIDATING and §19.7 voids the pending delivery with it,
while neither of the first two moves on a revision; and it is captured when a validation RUN STARTS
(`Engine.generation_of`, handed to `record_exec_verdict`), because a verdict is about the delivery the
validator read, not about whatever the node has become by the time it finishes. The self-PASS gate
compares all three; q_V/false_fail_share compare the reopen generation. A pass-terminal reopened under the SAME criteria whose fresh run
FAILs sets `false_positive` — exactly q_V's pass→later-fail member. ESCALATED needs nothing from R′:
finality is a property of settlements, and its exits are ordinary live-node edges.

DONE is one state; completion reason is metadata in the MutateGraph mutation. Cancellation is NOT a DONE
reason — canon §12.6 gives it its own two-step handshake `CANCEL→CANCELLING→CONFIRM_CANCEL→ABANDONED`
(mirror of ASSIGN→ACCEPT; CONFIRM_CANCEL = the sole staffed exit from CANCELLING, an FSM-deadlock signal
carrying the executor's in-flight report). **11 states in enum**: IDLE, OFFERED, CHALLENGED, EXECUTING,
BLOCKED, VALIDATING, REWORKING, CANCELLING, DONE, ABANDONED, ESCALATED. Pre-v3.7 DBs stored
cancellation as DONE(reason=CANCELLED) — migrated on read in the SQLite adapter. A node stored in the
retired OVERDUE is moved to ESCALATED when the database opens, logged as a migration (not a signal);
audit rows that name OVERDUE keep their text and read as ESCALATED (`RETIRED_STATES`).

ESCALATED resolution is INSIDE the FSM (§12.5). It was written as outside it, which singled out one issuer act as extra-protocol while ASSIGN, PASS, FAIL, CANCEL and REJECT_CHALLENGE are all inside — and left a state meaning "someone must decide" admitting no act of the decider. Measured cost: an agent whose root escalated built a second root beside it, then a third, and closed the goal on a childless leaf.

**Discovered-Dep (§11.2/§15.4, two-phase):** a BLOCK naming undeclared prerequisite NODE(s)
(`blocker_task_ids`; `blocker_task_id` = single-blocker shorthand) emits RECORD_DEP PER named node —
provisional discovered edges (provenance = the BLOCK, T11; one BLOCK may surface several prerequisites,
an edge each); RESOLVE_BLOCK adjudicates the set: payload-free = confirm all, `blocker_task_ids` = the
corrected FULL set (SET semantics — unlisted provisionals retract, listed sources confirm), `external` =
retract all (non-producible blocker → the FM-5 freshness line). An escalated-unresolved provisional stays
counted — this is what feeds q_Dep's denominator. Records and E_Dep are two reads of one store:
`Graph.dep_edges()` returns every record (q_Dep, the projections); `dep_edges(adopted=True)` returns E_Dep —
the declared edges and the confirmed discoveries that close no cycle — and it is what CHECK-2/3, the
execution order, consumption and the dispatcher read. A record is OPEN while the BLOCK that made it stands;
when the node leaves BLOCKED with the record unanswered (a re-ASSIGN, a CANCEL, the bound) it is CLOSED —
counted, never adopted, asking nothing. An asking record (open, or confirmed and not adopted) on a cycle of
live waits — E_Dep, the asking records, a parent's wait on its children, each while its producer is
unfinished — is what cannot come first (`dep_order_refutations`): an open one is the blocked node's
issuer's to answer (`order_refuted_by`; its BLOCK does not clear itself; a refutation retracts it and the
node resumes); one confirmed (a confirmed producer later reopened) or raised again after a block of the
same contract was answered refutes the plan's order at the split both ends sit under (`dep_order_refuted`),
whose issuer re-decomposes. `dep_edges()` leaves closed records out — only q_Dep reads them
(`dep_edges(closed=True)`).

## Design Decisions

**Validation at the SEAM (§10.3).** A node is PUBLIC ⟺ it is a delegation seam: a root, or
Del(child) ≠ Del(parent). The gate (engine/validation.py) demands a recorded independent verdict for
the delivery that stands ONLY there — and it asks about the NODE, not about the name signing: an
issuer is no more entitled to a bare PASS than the executor is, since §10.3 asks for independent
validation rather than for a different signature. The record can come from the instrument
(`validate_result`) or from a person stating what they observed (`record_verdict`, whose records carry
`by_hand` so nothing downstream reads a self-named party as an instrument). An authorized instrument
opens the gate by what it RECORDED, not by whose name is on the signal: the rule used to step aside
for any id on the validator roster, and `source` is caller-supplied on the CLI and HTTP doors, so
`register_agent(<any id>, "llm-validator")` plus one `signal ... PASS <that id>` closed a root that
had delivered nothing — no verdict on the record at all (2026-09-05). Every instrument path in the
product already writes its verdict before signing it, so what the narrowing removed is a signature
standing on nothing. What the dispatcher may NOT do is reuse an executor's own
self-report as that verdict: the record names who produced it, and the executor's signature is not an
independent one. An INTERNAL node (same Del as its parent — the executor's own private
decomposition) has no seam of its own: its guarantee is carried by the validation of the public result
it rolls up into (T1 non-redundancy). Where the validation stands is decided by κ (§3.7, §10.3):
`auto_decompose` records, per node, the volume of its work and whether one session of the executor's model
builds and checks it; the instrument validates at every seam and at the top of every scope one session
carries, and a node inside such a scope is covered by that scope's validation (`validation.observed_here`).
Where a registered executor holds the whole scope, the dispatcher runs it as one piece: one executor
session over every open node in build order (`delegate.run_scope_executor`), then one validator run over
every delivered node, each node's own verdict recorded and signed parts first (`tools_llm.validate_scope`,
`delegate._sign_scope`); a failing part fails the wholes above it on the criteria mapped to it. A childless
node judged larger than one session gets no session: its split is owed (`validation.split_owed`), and where
the system moves for its executor the machine issuer's `split` question runs the refine round on it.
Under a mode a PASS at an observed node stands on an appointed observer's record, never on the executor's
`self_validation`. `GFSO_VALIDATE_INTERNAL=1` observes every delivery, for measurement. The ROOT is always a seam: "done" (root DONE/PASS) never
completes on a self-stamp. Revision reasons are typed in the packet (§15.8:
`spec_defect | scope_expansion | capability_mismatch | other`) — q_T counts typed spec-defect criteria
changes, q_Del narrows to capability_mismatch where typed and keeps its documented over-approximation
where untyped.

**Parallelism is registration, not a second driver.** `next_steps` returns the whole actionable
frontier with `parallel_ok` on the execute-class steps — pairwise independent by construction, each a
leaf whose Dep producers have PASSED — and `delegate.Dispatcher` spawns a thread per ready step under
a concurrency cap, gating each spawn on its producers and wrapping the report into
ACCEPT/DELIVER/BLOCK. Nothing else needs to schedule: an orchestrator that assigns nodes to
registered executors gets concurrency, dependency order and signal translation from the engine, while
one that keeps every node assigned to itself gets none of it and serialises — which is a property of
the assignment, not of the protocol. Independence is a CLAIM the executors act on: two subtasks that
write one artifact are not independent whatever their topics, so the split declares the Dep (or gives
each its own artifact), and a coupling that slips through surfaces at runtime as BLOCK — a discovered
Dep edge with an owner, which is what q_Dep divides by.

**What a graph costs (`/api/usage`).** Every internal model call is recorded with the ROLE that made
it — decomposer, Level-2 review, validator, executor — and totalled per project: tokens, dollars, and
a per-role split (surfaced in the observation window, not beside the quality metrics: those are
properties of the graph, while spend is a property of one way of working it — with people at the
nodes there are no calls to report). `costed_calls` rides beside the money because a transport that reports no price
(any OpenAI-compatible endpoint) contributes zero, and a total that cannot tell "not reported" from
"free" is the ⊥-as-zero error in the one column where it looks like a fact. An executor's turn budget
is declared with its role (`register_agent(..., max_turns=N)`) for the same reason its model is: two
runs of "the same agent" under different caps are not the same agent.

**Guarded transition (VALIDATING + FAIL).** One of two guarded families (the other is REOPEN under the R′ finality gate). Iteration counter lives in graph task node, not FSM state — FSM stays memoryless except for this one predicate read. Alternative was splitting FAIL/FAIL_FINAL into two signals, but that inflates the signal set for what is a single semantic action (validation failed).

**DONE is one state.** DONE is reached by PASS alone since v4.1 (a timed-out validation goes to ESCALATED); rows written before that change carry DONE(auto) as metadata in the graph, and it is the same FSM state. Simplifies the FSM — terminal is terminal. Reason is recorded by MutateGraph for metrics. What DONE does NOT carry is a verdict of fail: acceptance is its only route in (§8.3), the exhausted rework loop hands the node to its issuer in ESCALATED(fail) instead, and DONE(cancelled) is a pre-v3.7 encoding migrated on read.

**Every wait's timeout → ESCALATED directly.** OFFERED, CHALLENGED, EXECUTING, REWORKING, BLOCKED and VALIDATING all hand a lapse to the issuer at once. There used to be a transit, OVERDUE, between a first and a second timeout: it admitted no progress signal and no revision, so its owner held only CANCEL, and its one exit was the second timeout into the state where the decision is actually made. It is gone, and re-ASSIGN is admitted in every live state but IDLE and CANCELLING.

**CHALLENGED timeout → ESCALATED (§12.2).** A pending challenge that times out is an unresolved spec dispute, not a benign event — it goes to its issuer, never auto-accepts. (Earlier drafts auto-accepted → OFFERED; that silently resolved a dispute in the issuer's favour and was removed.)

**VALIDATING timeout hands the decision back, and accepts nothing.** The issuer who did not validate within T_validate is asked again in ESCALATED; the delivery stays in the log and his re-ASSIGN re-presents it (§16.14). Until v4.1 this closed `DONE(auto_pass)` — the one timeout that invented a verdict, and one a parent's executor could obtain over his own child by letting its VALIDATING lapse. `DoneReason.AUTO_PASS` stays a member because rows written before this change carry it; nothing produces it any more.

**CONFIRM_CANCEL — two-step handshake (canon §12.6; code synced at v3.7).** Cancellation is `CANCEL(issuer)→CANCELLING→CONFIRM_CANCEL(executor)→ABANDONED`, mirroring ASSIGN→ACCEPT. CONFIRM_CANCEL is an FSM-deadlock signal: the sole staffed exit from CANCELLING, carrying the executor's in-flight state (`SignalData.in_flight`) onto the audit log (T11). `CANCELLING--timeout-->ABANDONED` — cancellation is authoritative, executor silence still completes it (without the in-flight report). The cascade fires on CANCEL (entering CANCELLING): every live descendant gets its own CANCEL and runs its own handshake.

**Revision = re-ASSIGN, same id (canon §12.3 Inv-1; code synced at v3.7).** A packet change on a live node is ONE re-ASSIGN under the same id → OFFERED (the executor re-ACCEPTs/CHALLENGEs); the APPLY_SPEC mutation re-authors in place and the superseded version lives in the append-only log (Inv-7). No CANCEL signal, no CANCELLING pass, no cascade — subtree retained; staleness surfaces via CHECK-1/CHECK-1b/CHECK-3. Not accepted from IDLE (no packet yet), CANCELLING, or terminals.

**The dispute is open after consent (v4.1).** EXECUTING and REWORKING admit CHALLENGE (§12.4): the defects the a-priori battery cannot see — FM-1.d, FM-2, FM-3's form — are met in the work, and routed through BLOCK the dispute lost both of its §16.12 closures (REJECT_CHALLENGE's justification and ACCEPT_CHALLENGE's positive one). What ACCEPT protects is untouched: the contract binds until the issuer answers, and REJECT_CHALLENGE returns the node to the wait the challenge interrupted under the same packet version, deadline and rework count — EXECUTING when an ACCEPT of the current version stands in the log, OFFERED when none does (a challenge raised from the offer; sending it to EXECUTING would put the executor to work on terms he never accepted). Consent is read off the log (`engine.audit.consented_on_current_version`: an ACCEPT after the latest version-installing event — an ASSIGN in any form, including a revision and a REOPEN, or an ACCEPT_CHALLENGE; a pre-consent REJECT_CHALLENGE enters OFFERED and installs nothing), into `GuardContext.consented`. The same reading says whether a node is reworking (`Engine.in_rework`: a FAIL on the current version, in EXECUTING or REWORKING), so a rework resumed in EXECUTING by a rejected challenge or a resolved block keeps its failed-criteria pointer in the packet and the directive.

**BLOCKED → RESOLVE_BLOCK always → EXECUTING.** Even if entered from REWORKING. EXECUTING and REWORKING have identical allowed signals (DELIVER, BLOCK, **CHALLENGE** since v4.1, timeout). The iteration counter in graph state preserves rework context. No semantic difference.

RESOLVE_BLOCK is the PURE-UNBLOCK edge: it reports that the blocker is gone. Where the blocker stands, the engine refuses it and the refusal names what the node's ISSUER — BLOCKED's owner under Inv-8 — can do himself: `external=true` if he worked around it, a corrected `blocker_task_ids` if the edge was misattributed (both adjudicate a PROVISIONAL edge only), `remove_dependency` and a revision where the contract no longer needs that input, or CANCEL. Waiting, where none of those is true, is the honest state rather than a further move: BLOCKED carries its own bound and its expiry hands the decision to the issuer at ESCALATED. §12.16's conformance clause (ii) is why the list is the issuer's own moves — a refusal whose only lift is the counterparty's act does not conform.

**Iteration counter in graph task node.** `task.iteration: int`. Incremented on REWORKING entry, checked by the FSM guard on FAIL, and reset by every new packet version — a revision, an ACCEPT_CHALLENGE or a REOPEN (Φ3, §12.3): `max_iterations` is the issuer's forecast for ONE contract, so counting a previous contract's refusals against a repaired one spends the new forecast before the work begins. Counter is graph state, not FSM state.

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

`EmitSignal` stays in the `Effect` union but no FSM row emits one: escalation is reached by a repeated timeout, and the one signal the system generates for itself — the cascade CANCEL — is put on the queue by the loop (below), not returned as an effect.

## Runtime: Event Loop

```python
# engine/loop.py — event loop (L1)
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
- `graph.apply()` returns affected child task_ids, not signals; the engine loop (`gfso/engine/loop.py`) puts a CANCEL on the queue for each. Signal generation stays out of the graph.
- `handlers.run_checks()` returns results. Stored in graph for Dispatch payload and metrics.
- `handlers.recommend()` returns recommendation. Stored in graph for Dispatch payload.
- `fsm.transition()` takes guard context as third argument.

## Module Structure (current layout; the layer rules are ENFORCED by tests/test_layering.py)

```
gfso/
  core/                     ← L0: the protocol STANDARD (canon-governed; pure, zero deps)
    types/
      primitives.py         # Task, Spec, Criteria (full: input/expected/n/timeout), DepEdge, SignalData,
                            # and the ANSWERS the system gives: SignalOutcome/Refusal (what a refused
                            # transition says: kind · why · route) and Wait (why a node is not on the
                            # frontier and what would open it)
      enums.py              # State(12; DONE/ABANDONED quasi-terminal §12.6), Signal(13 = 12 protocol
                            # + TIMEOUT), Verdict, CriticVerdict, Stage (the ledger's roles),
                            # FM(7), RevisionReason (§15.8 typing)
      effects.py            # MutateGraph (incl. dep_from/dep_froms), RunChecks, Recommend, Dispatch
      ports.py              # StoragePort (mandatory core incl. the append-only signal log),
                            # LLMProviderPort, AgentPort, VerifierPort, ClockPort, RunnerPort
                            # (+ their stdlib defaults SystemClock/ThreadRunner — zero-dep, live here)
    protocol/               # fsm.py = THE TABLE (+ `not_admissible_here`: why a signal moves nothing
                            # here and where the intent goes) · invariants.py · validation.py (role map)
    handlers/               # CHECK-1-6 structural · CHECK-7-8 numeric-bound tier (capability-honest
                            # skips; the formula/solver tier is a declared, unimplemented extension)
    graph/                  # model · mutations (incl. RECORD_DEP/ADJUDICATE_DEP) · metrics (∅→None) ·
                            # projection · review.py (`finding_keys` — the ONE name a Level-2 finding
                            # carries, read by the gate, the dispute verb and the delta baseline)

  engine/                   ← L1: the reference runtime (imports CORE ONLY — the layer gate)
    loop.py                 # process_signal = the substrate-free protocol step; event_loop = the
                            # default pump; timeout_monitor reads the ClockPort (Inv-5)
    frontier.py             # what the graph owes next: `NodeSteps` (the move one node owes, its words) and
                            # `Frontier` (the walk: every owed move in order, or why nothing is open)
    claims.py · joins.py    # in-memory state the engine holds beside the log: who runs a model over a node
    workforce.py            # now (`Claims`), where a passed result stands (`Joins`), who works here as the
    parking.py              # dispatcher published it (`Workforce`), what waits on an undecided park (`Parking`)
    __init__.py             # Engine facade (takes clock=/runner= ports); audit.py; events.py; verdicts.py
                            # (one writer of the verdict record); validation.py — the gates, one rule
                            # family per signal (`_pass_rules` / `_accept_rules` / `_resolve_block_rules`
                            # / `_deliver_rules`): a SEAM's PASS needs a verdict for the delivery that
                            # stands, whoever signs; `record_reviewer_verdict` refuses reviewer==Del

  tools.py                  ← L1: the STRUCTURAL action surface (core+engine only; ships with the core dist)
  tools_llm.py              ← L2: the LLM verbs (auto_decompose/review_decomposition/validate_result); its TOOLS =
                            #     the COMPLETE transport registry (structural ∪ LLM)

  adapters/                 ← port implementations (import core only)
    storage/ (sqlite, memory) · agents/ (human, …) · llm/ (stub | headless Claude CLI, generic
    OpenAI-compatible) · verifiers/

  decompose/ · critic/ · delegate.py · runtime.py   ← L2: the AI product (search↔audit monada,
                            # L2 validate, registry+dispatcher, DI/llm_factory/ProjectRegistry)
  config.py · places.py     ← leaves with NO gfso imports, readable from anywhere: the settings
                            # vocabulary, and where a path is (is it cheap to stat, what is its
                            # normal form, do two spellings name one place). Both exist so a rule
                            # kept in two layers cannot move in one of them.
  mcp/ · api/ · web/ · cli.py · driver.py · main.py ← binding: the doors (generated from tools_llm.TOOLS).
                            # api/server.py mounts one concern at a time — pages · reads · acts ·
                            # ledgers · lifecycle · runtime · events — rather than one body of routes;
                            # mcp/connect.py is the stdio bridge (it breaks and rebuilds when a call
                            # goes unanswered, instead of hanging on an orphaned session)

packaging/core_manifest.py  ← THE gfso-core cut line (core + engine + tools.py + neutral stdlib
                            # adapters); closure + zero-deps proven by tests/test_core_dist.py;
                            # build_core.py builds the wheel (version read from gfso/__init__.py —
                            # the one place it is written; the pyproject key is dynamic)
gfso/examples/              ← one working script per entry door, INSIDE the package so the wheel
                            # carries them (`gfso demo`); tests/test_examples.py runs the
                            # deterministic ones live
```

## Dependency Matrix (mechanically enforced — a violation is a red CI)

```
core/            → core/ only          (hermetic; stdlib-only)
engine/          → core/ + engine/     (the ONE framework edge)
tools.py         → core/ + engine/     (structural surface — no LLM, no adapters)
adapters/        → core/ + adapters/   (port implementations, and each other)
config.py|places.py → NOTHING (gfso-import-free leaves; admissible from any layer)
decompose|critic|delegate|runtime|tools_llm → anything below binding
mcp|api|web|cli|driver|main|doctor     → everything (and NOTHING below imports them)
```


## Why Each Module Exists (forcing argument)

**L0 (core/):**

| Module | Why it exists | Merge with any neighbor → breaks what |
|---|---|---|
| types/ | Zero deps, everything depends on it | Merge anything IN → import cycles |
| protocol/ | Pure FSM table + invariants + role validation | Merge with graph → FSM depends on storage |
| handlers/ | Effect execution: checks + recommend | Merge with protocol → pure FSM becomes impure. Merge with graph → state acquires check/LLM concerns |
| graph/ | Persistent state + mutations + metrics | Merge with protocol → FSM depends on storage. Merge with handlers → state acquires check/LLM concerns |

**L1 (engine/):** Single module. Imports all of core/, provides framework API. Cannot be split further — audit, events, validation, loop are tightly coupled around the signal processing pipeline.

**L3 (adapters/):** Pluggable. Implements core/ ports. engine/ doesn't know which adapters exist.

No upward dependencies, and the matrix above is the one the gate enforces (`tests/test_layering.py`) — including the part this prose used to round off: `gfso.adapters` may import `gfso.core` and other adapters, and binding (`mcp`/`api`/`web`/`cli`/`driver`/`main`/`doctor`) is the only place allowed to import binding.

## The Level-2 review — the ONE map (canon §9.5)

⚠ Naming collision, named explicitly: the CODE LAYERS above are L0 `core/` · L1 `engine/`,
`tools.py` · L2 `tools_llm.py`, `decompose/`, `critic/`, `delegate.py`, `runtime.py` · L3
`adapters/`, with binding above all of them. The canon's VERIFICATION LEVELS are a different scale
entirely (§9.5, Morris: **Syntactic** = level 0, topology · **Semantic** = level 1, formal
entailment · **Pragmatic** = level 2, causal correctness, pre-contact) — the collision is at "2",
where a code layer and a verification level share a number and mean nothing alike. Note also that
"semantic" belongs to verification level 1 — what `review_decomposition` reaches for is the
Pragmatic level, which the canon marks a permanent boundary rather than a solved check (Ch. 20), so
what runs here is an approximation to it, not the level itself. (The collision feeds the parked
naming-overhaul; until then this section is the disambiguation.)

Level 2 is NOT one component — it is one FUNCTION with four deliberate surfaces, split by
the QUESTION each asks. Two prior designs are deliberately dead: the monolithic analyst⊥validator
critic (E2-refuted: polices form, cannot move content) and the SEARCH-in-diff-mode hole-hunt
as the standalone verb (the opposite extreme — "what is missing" is the DECOMPOSER's question;
it lives in refine and only there):

| Surface | Question it asks | Where | Who needs it |
|---|---|---|---|
| **L2-inside-decompose** | "what is missing from the space" (recall) | `decompose/loop.py` search↔audit at build/refine time | every `auto_decompose` graph — the DEFAULT path; on-demand re-runs = the "AI refine" button / refine rounds |
| **Standalone L2 CHECKER** | "does the DECLARED mapping causally entail" (§9.5's own question): per parent criterion — mapped children's criteria taken as facts ⇒ sufficient / insufficient-with-named-gap / uncertain; + semantic FM-2 conflicts CHECK-8 can't see | `critic/runner.py` (frozen role `critic/prompts/checker.md`), exposed as `review_decomposition` (MCP · `POST /api/run/review_decomposition` · CLI; the name split is deliberate: `review_*` = pre-contact over the PLAN, `validate_result` = post-contact over the RESULT) | externally-authored / hand-edited graphs that never passed through decompose |
| **UI door** | the same checker, one click | the sidebar "AI review" button; per-criterion verdicts rendered, ADVISORY (fix via FSM verbs or declare ACCEPTED_RISKS) | the pure-UI human — the ONLY consumer for whom the standalone checker is load-bearing |
| **Runtime detection** | "did a mapping that LOOKED sufficient fail live" | `core/graph/metrics.py::q_D` | everyone — **the real Level-2 verdict**: the axis is checkable only by execution (§9.9) |

Epistemic status, held everywhere (§9.9 / Ch. 20's Level-2 boundary): no pre-contact instrument VERIFIES Level 2 —
the checker is the canon's LLM-review APPROXIMATION (an a-priori estimate over the faithfulness
axis; its own verdict is itself a Level-2 claim), which is why it is advisory by construction
and q_D keeps the last word. Staging (critic/runner.py): the L0/L1 structural gate BLOCKS the
checker — L2 presupposes a structurally complete graph; the verdict never auto-fixes; an
INCOMPLETE per-criterion verdict is treated as NO verdict (never read as clean). Run economics
follow §9.9's marginal rule (VERIFY while marginal c_check < prevented FORM-risk): L0 is
mandated, the checker is ON-DEMAND — spent where the caller deems the risk worth one call
(hand-authored graphs, external issuers, load-bearing seams), never auto-fired per ASSIGN.
`validate_result` is NOT on this map: it is EXECUTION validation, post-contact — the contact
itself, not a pre-contact check level (a recurring conflation, named here on purpose).

## System LLM vs Agent LLM

| | System LLM | Agent LLM |
|---|---|---|
| Location | core/handlers/recommend.py | adapters/agents/ (the AgentPort implementations) |
| Prompts | Ours, fixed — our IP | User's, custom |
| Graph access | Receives hydrated GraphContext | No graph access |
| Replaceable | No (or at own risk) | Yes, fully pluggable |
| Effect type | Recommend | Dispatch |
| Paper section | §17.1 (AI layer) | §10.3 (agent-agnostic role filler) |

Both use LLMProviderPort (in core/types/ports.py). Different roles, different locations, shared provider.

## Runtime Model

- **Engine** (engine/) receives signals via `send_signal()` or `assign_task()` → queue
- **Event loop** (engine/loop.py) validates → FSM transition → pre-validates effects → executes → audit → events
- **Timeout monitor** (background) fires on the bound §11.2 gives each state: the packet deadline in
  the WORK states (EXECUTING, REWORKING); the deadline and the state's own bound, whichever comes
  first, in the ANSWER states (OFFERED, CHALLENGED, BLOCKED); **T_validate alone**, counted from
  DELIVER, in VALIDATING; the state's own bound only in the PROTOCOL states (CANCELLING,
  ESCALATED). The per-state bounds are protocol parameters — defaults in `config._STATE_BOUND_DEFAULTS`,
  each overridable by `GFSO_BOUND_<STATE>` — and they are ON, because a bound that can be switched off
  is not a bound. Every entry into OFFERED carries a live deadline: `GFSO_DEFAULT_DEADLINE_S` (24 h)
  is written into a packet the issuer left undated, inside the parent's own deadline and marked
  `deadline_supplied`, so CHECK-3 does not read the engine's default as the issuer's ordering claim.
  `GFSO_STATE_TIMEOUT` remains as the opt-in age clock over ALL states (0 = off); the clock-binding
  question stays OPEN (a real deployment should anchor to real UTC dates or stronger — tamper-resistant
  time is an implementor's open end). A bound already passed fires ON ENTRY, so a state entered after
  its bound admits no signal before its timeout (§11.5). Deduplicated per state VISIT —
  (task, state, `state_entered_at`): keying on the last-fired state alone went silent when an R′
  reopen re-entered a fired-in state through a terminal (an Inv-5 hole found by the TLC spike model,
  see `formal/tla/README.md`); a state change restamps the entry, so a re-entered state fires again.
- **Graph store** persists G via StoragePort
- **Audit trail** records every signal with timestamp, old/new state, effects, errors — APPEND-ONLY in
  storage (SQLite `audit_log` table): the log hydrates on engine construction, so the T11/Inv-7 trail
  survives restarts (in-memory only on MemoryStorage, consistent with its ephemerality)

## Ablation Support

| Remove | Effect on system |
|---|---|
| core/handlers/constraint.py | CHECK-7-8 skipped. CHECK-1-6 still work |
| core/handlers/recommend.py | Recommend becomes no-op. Protocol + graph + checks still work |
| adapters/llm/ | System + Agent LLM degraded to stubs. Everything else works |
| adapters/agents/human.py | Nothing to hand a node to: dispatch to a person is what this port does (delegation to an LLM executor is `delegate.py`, not an agent adapter) |
| engine/ | Use core/ as pure library. Call protocol.transition() + mutations.apply() directly |

---

# v3.6 — mutation surface, closure & interfaces

> This section extends the CORE-FSM architecture above with the track-b work (the upper authoring layer, the
> single-chokepoint closure, decompose, and the one-action-surface/three-transport interface model). Where the two conflict, THIS section is current (e.g. Recommend is no longer auto-emitted on ASSIGN; CHALLENGED-timeout
> escalates rather than auto-accepting; revise does not cascade — see below).

## Two layers — every mutation is a logged signal
Any actor (human via UI, agent via MCP/CLI) mutates the graph through the SAME closed FSM — there is no exit from it.

```
   UI / MCP / CLI            — thin transports; send upper-layer calls
        │
   UPPER API (convenience compositions — read-modify-write):
     decompose · revise · edit_accepted_risks · edit_criteria · reassign · add/remove_dependency · map_criterion
        │  desugars to ↓ (never bypasses)
   LOWER API = THE CANON FSM — send_signal() + reads
     CLOSED alphabet: 12 P2P signals + TIMEOUT (frozen by test):
     ASSIGN ACCEPT CHALLENGE BLOCK DELIVER CONFIRM_CANCEL ACCEPT_CHALLENGE REJECT_CHALLENGE PASS FAIL CANCEL RESOLVE_BLOCK
     every signal → audited mutation (loop → audit). No 13th.
        │
   graph / storage
```

### Authoring ops are NOT new signals — they desugar to existing ones
| Upper op | Desugars to (lower) | Notes |
|---|---|---|
| create | `ASSIGN` (IDLE → CREATE_TASK effect) | node creation IS the ASSIGN effect (logged) |
| decompose | one `ASSIGN` per child (+ `covers` → parent mapping effect) | mappings = the child's declaration, logged; a FULL mappings list SETS the parent's coverage (pairs absent from it are removed — reconcile); `None` adds without wiping |
| **revise** | re-`ASSIGN` (SAME id) → OFFERED | revision per Inv-1 §12.3: NOT a CANCEL; version appended to the log (Inv-7); **subtree RETAINED — no cascade**; staleness surfaces via CHECK-1/1b/3; issuer-gated |
| edit_accepted_risks / edit_criteria | revise (RMW) | change one field, carry the rest |
| add_dependency (declared) | re-`ASSIGN` of the **consumer** (gains a `depends_on` criterion) | Dep is criteria-content (§2); edge derived |
| map_criterion | a re-admission of the parent's split (§11.5), no child signal | binds an existing child to a parent criterion — the mapping is the split's (§2.4); logged as the admission it is |
| reassign | re-`ASSIGN` with a new executor | Del change per Inv-1 (q_Del) |
| **reopen** | re-`ASSIGN` out of DONE/ABANDONED → OFFERED | R′ (§12.15): double-gated (finality of consumption ∧ max_reopens); verdict re-earned, never resurrected; consumed terminal = finally locked (recover by re-decomposition) |
| **abandon** | `CANCEL` → CANCELLING → `CONFIRM_CANCEL` → ABANDONED | two-step handshake (§12.6); **cascades CANCEL to subtree**; never deleted (§17.1) |

**Surface-don't-destroy** (canon §12.6; code synced at v3.7). abandon = `CANCEL` → opens the handshake and cascades the
subtree (its sub-work served a contract that no longer exists, §15.1); each node settles CANCELLING→ABANDONED
on its executor's CONFIRM_CANCEL (or timeout — cancellation is authoritative). revise = re-`ASSIGN` (same id) →
the node continues under a new contract in OFFERED: its **subtree is RETAINED, no cascade**; coverage staleness
(uncovered new criterion / dangling mapping) is SURFACED by CHECK-1 / non-redundancy for the agent to resolve
∨ declare, not destroyed. The only IN-PLACE spec change is `ACCEPT_CHALLENGE`.

## Decomposition surface — one operation over graph state (canon §17.1; code synced at v3.8)

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
  own level — the target node's criteria/ACCEPTED_RISKS/scope and the children's contracts + coverage + seams;
  the children's Del and their OWN registers belong to other authors (the issuer; the child's own
  decomposer, §9.2) and pass through untouched.
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
- **Discovered-Dep is signal-driven (closed at v3.7):** BLOCK carrying `blocker_task_ids` (or the singular
  shorthand) emits RECORD_DEP per named blocker (provisional edges), RESOLVE_BLOCK emits ADJUDICATE_DEP
  (confirm all / corrected full set / retract all) — both through `mutations.apply` (§11.2/§15.4).
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
     ├─ gfso/mcp     MCP server — binds each TOOLS fn as an MCP tool; mounted on the one server over
     │               streamable HTTP at `/mcp`, which `gfso connect` bridges to a client's stdio ← the agent
     ├─ gfso/driver  `gfso run` — binds each TOOLS fn to argv                          ← scripts / CI / subagents
     └─ gfso/api     HTTP `POST /api/run/{tool}` — dispatches to TOOLS                 ← the UI (browser client)
                     (+ bespoke typed GET reads: task detail / graph / metrics / …)
```

- `runtime.build_engine_from_env` = the shared CORE constructor (one Engine from `GFSO_DB_PATH`).
  Every setting it reads is owned by `gfso/config.py` — the one module that touches the environment
  (`GFSO_L2_GATE` stays a direct read at its enforcement point, deliberately): the provider and its
  billing mode, storage and model tiers, paths, and the measured dials — `GFSO_VALIDATION_BATCH`
  (how many probes one validator run owes at most — pinned, the parts' pinned ones each once, regression lines —
  and so how much of a validation runs in parallel; a criterion owing more is split between runs and read as their
  conjunction) and
  `GFSO_VALIDATOR_RETRY_MODEL` (a tier for the retry after a ⊥ report; unset, the retry stays on the node's own tier), and
  `GFSO_SYSTEM_MODEL` (the model every system-side role runs on — the plan's author and reviewer, the issuer's function,
  and any executor or validator whose roster entry names none; read when the server starts). The
  declaration in `data/serve.json` is applied through `config.fill_env_gaps` wherever a server is
  started — it fills what nobody said and never overrules an explicit export, which is what lets a
  measurement run turn a switch off and keep it off.
- HTTP **reads** stay bespoke typed routes (view-specific shapes for the UI — reads aren't a mutation surface).
- **Live mirroring:** ONE process (raised by `gfso up`; `gfso serve` is that process in the foreground) hosts MCP + HTTP + UI over ONE Engine, so the
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
  CAUSAL order — no single clock is assumed (canon §8.2: CA2, the single clock, is redundant *for the operational taxonomy* — the phase count is
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

## Code ↔ canon corners (flagged, not patched — canon is truth)

*(The three that were LIVE divergences of the ENGINE from the canon — **#3**, an edge the canon denies,
**#1**, a row the canon exempts, and **#5**, a failure mode routed to the wrong repair — are now
CLOSED or landed in part: the engine carries the canon's shape and each entry records what landed. The rest
are settled by the canon and kept because the Lean encoding is where they show, or are engine gaps.)*

1. **IDLE has no timeout — the canon's position; the engine now agrees (CLOSED).**
   `gfso/core/protocol/fsm.py` used to carry an `(IDLE, TIMEOUT)` row, added under the **v3.9**
   reading in which Inv-5 was total over non-terminals; v4 exempts IDLE by name (§12.2, §12.12), so the
   row was removed. What it had been written for — a crash orphan, observable in IDLE because
   CREATE_TASK persisted while the same ASSIGN's landing did not, and at a root with no parent whose
   clock could surface it — is answered where the defect lives: `Engine._recover_orphans` re-sends the
   packet-less ASSIGN at startup, so the interrupted transition finishes through the queue — validated,
   logged (Thm 11), never a silent state write (`tests/test_inv5_timeout.py`). In Lean
   `Fsm.idle_has_no_timeout` proves `step IDLE TIMEOUT _ = none`, and the finiteness theorems keep their
   explicit `s ≠ IDLE` hypothesis — the exemption in the type rather than papered over.
2. **IDLE + CANCEL → CANCELLING — settled by the canon, not a divergence.** §12.4's IDLE row carries it;
   arguably vacuous, encoded faithfully because it is what both the canon and the code say.
3. **`(VALIDATING, FAIL, iteration ≥ max)` — the edge the canon denies is GONE (CLOSED).**
   The code, `Fsm.lean`, `FsmTable.tla` and `docs/architecture.md` now route the exhausted rework loop
   to ESCALATED, the canon's target (§12.4, §12.5); before, it entered DONE, which §12.4 enters only
   through PASS. The record carries `done_reason=FAIL`, so a verdict-escalation stays distinguishable
   from the timeout routes into ESCALATED — without which the standing-FAIL metric populations (q_D's
   exhausted arm, `false_fail_share`) would have silently emptied, a blind metric reading as a clean
   one. The live path is tested through the engine, not the table alone
   (`tests/test_integration.py::test_exhausted_rework_escalates_and_stays_a_verdict`).
4. **`(REWORKING, BLOCK) → BLOCKED` — the engine had an edge the v4.0 DIAGRAM omitted; RESOLVED in
   favour of the engine.** `fsm.py` and `Fsm.lean` route BLOCK from REWORKING to BLOCKED; the edge is
   derived (§12.4's rules), and §12.4 now writes the admissible sets out per state, closing the
   diagram-only gap that let this hide. Consequence (`FsmCanon.canon_exec_rework_same`): EXECUTING ≡
   REWORKING behaviourally — REWORKING an attribution label (§12.11).

5. **The re-DELIVER refusal prescribed the wrong repair for an FM-1 failure (OPEN on (a); (b) landed).**
   `gfso/engine/validation.py` refuses a parent's re-delivery when its FAILed criteria
   are covered by children untouched since that FAIL — an engine gap of its own: after a re-presentation
   (a false FAIL among its cases) the canon admits "the re-delivery of an identical artifact" (§12.10), so
   the refusal does not conform to §12.16 (ii) — and its message routed the repair DOWNWARD: *"Rework
   flows DOWN: reopen the covering child … and rework it there"*. A parent's criterion failing while
   every child passes its own is q_D's event, "whatever caused it" (§15.4; the cause is not q_D's to read,
   §16.9); where the cause is the split, the defect is the decomposition's, its repair a **re-admission of the parent's
   split** (§11.5) by its decomposer, who owns it (§9.7). A re-admission reopens no child, so the
   finality gate is not involved.

   Observed live (`EVIDENCE_LOG` §13.3, `markdown_renderer`): following the message's own route the
   arm hit a wall, because `Graph.is_consumed` locks a DONE child on which any Dep-consumer built,
   and a graph with 20 seams over 11 nodes has no unlocked covering child. On the re-admission route
   the wall is not reached. Two things follow for the engineer, and the second is what keeps the fix
   honest: (a) the refusal message must name the re-admission remedy; (b) adding coverage so that
   `⋀children ⊨ cᵢ` is the repair, while lowering `cᵢ` to what the children already deliver is a false
   close wearing the same shape — the two are told apart by what CHECK-1/CHECK-7 say after the repair
   and by whether the fail-extension of `cᵢ` shrank. Without that discriminator both moves would have
   to be forbidden, and the only legal repair would be lost with them.

   **What landed** (`_refuted_coverage_refusal`, `tests/test_fm1_repair.py` — one planted case per
   class). (a) Not landed: the refusal still names a revision of the parent under Inv-1 (`validation.py`), a
   packet change that repairs no mapping — the split changes only by a re-admission (§11.5); the message is
   engineering's to change. (b) The discriminator reads
   the criteria as they stood when contact refuted them (snapshotted on the verdict record) against
   the criteria now, and disposes of each failed criterion: a criterion REMOVED, or LOOSENED where
   loosening is decidable — same metric, same operator, a bound admitting strictly more, the
   numeric tier where CHECK-7 is O(n) — is refused as a false close, its fail-extension having
   shrunk; a criterion EDITED undecidably is admitted once the revised plan's checks have spoken
   again (L0 clean plus a current, dispositioned L2 verdict — the check must have HAPPENED, never
   that the checker is right, and `GFSO_L2_GATE=0` opts out of that half exactly as it does at the
   execution gate); an UNREPAIRED criterion (unchanged, every coverer untouched) keeps the original
   refusal — the engine's non-conformance above, which this gate carries across the OFFERED→EXECUTING
   route of a re-presentation, where §12.10 admits the identical re-delivery; a touched coverer passes
   as before. Two scope notes on the engine's design: the gate follows the node across that route
   rather than firing in REWORKING alone, since a revision leaves REWORKING and the criterion-lowering
   route would otherwise never be examined; and it keys on the node HAVING a decomposition rather than on its mappings, since
   deleting the refuted criterion also deletes the mapping that pointed at it — a mapping-keyed
   trigger would have let exactly the false close through. A leaf stays out of scope: its contract
   belongs to the issuer above, whose CHECK-1 surfaces any hole a rewrite leaves.

   *(Threshold note, parked with a reason: the engine's point — "consumed while any Dep-consumer
   exists" — locks earlier than the moment §12.14 adopts. Moving it is not needed once (a) and (b)
   stand; if the wall reappears on the re-admission route, that is the measurement that would justify
   touching it.)*

6. **The vertical deadline rule now has a pre-exec check; CHECK-3 is unchanged.** Deadline coherence along D is form item (6) (§4.5), which CHECK-3 does not guard
   (§9.5, §20.10). It is L0 by construction (two packet fields, no domain knowledge), so it rides in a check of its own (`check_vertical_deadlines`,
   `tests/test_structural.py`): a child whose deadline is not strictly before its parent's is flagged
   at the battery — flagged, not refused. §11.5 gates it over an admission's unissued children while the parent's deadline is ahead; there
   the engine's flag is an engine gap. What the check adds is the implementation's guard, **not** CHECK-3's canon definition — the rule enforced here is §4.5 item (6), and any prose that
   credits it to CHECK-3 is wrong about the canon. A packet with no deadline does not conform; a logged
   default is admissible (§12.16).

7. **Non-redundancy beyond the topological proxy — still open, and stated where it shows.**
   CHECK-1b tests "every child is mapped to some parent criterion" and is renamed to its honest name,
   `CHECK-1b:no_orphan` (a decision of the v4.0 naming pass, not a canon §; form item (3) keeps the name
   *non-redundancy*). No pre-execution CHECK tests non-redundancy's formal face (§9.6, §20.10). Left open
   deliberately, with the proxy named as a proxy rather than dressed up as the condition.

8. **§15.9's triage ORDER is not what `next_step` implements — named, not silently adopted.**
   `Frontier._frontier` orders by action priority and then by id, not by §15.9's order. The gap is real
   and the fix is cheap — but it changes the ORDER in which an agent is driven through a graph, which is
   a measured quantity of the E3 arm (C3 cost, and through it C1/C2 attribution). Landing it inside a
   naming migration would confound the next measurement with a behavioural change, so it is recorded
   here and lands as its own change, measured against a run that did not have it.

9. **The execution gate was a SELECTION from the Syntactic level; it is now the level (CLOSED, with two
   gaps open).** §11.5 makes the Syntactic level (§9.5) the admission condition, save what no act of the
   decomposer lifts, which is reported. The engine gated four of the seven rows: ACCEPTED_RISKS (4),
   risk nodes (5) and leaf delegation (6) were computed, surfaced by `get_checks`/`list_holes`, and
   never blocked an ACCEPT — so a decomposition with an empty register was admitted. **What was argued
   for it, and why it did not survive:** gating the register had been tried and measured — an agent
   that cannot start until the register is non-empty writes a register in order to start, so the gate
   bought fabricated entries and `edit_accepted_risks` churn. That is a fact about an incentive, not
   about whose rule it is; a fabricated register is evidence against its author (§16.9, exception 7),
   while an ungated canon level is a silent one. The gate now runs every row of the level
   (`gfso/engine/validation.py`), pinned in both directions by `tests/test_structural.py` — every canon
   row gates, and CHECK-1c (anti-mock, an engineering addition with no canon row) does not. Cost,
   measured: 45 test fixtures were building decomposed nodes with no register and now carry one.
   **Closed since (2026-10-04):** CHECK-3 gates only the admission that sets the deadlines, where some choice of them
   orders every edge (`Engine._refuse_deadlines_the_admission_cannot_order`); met afterwards it is §12.10's flag,
   named in the frontier's step as the consumer's issuer's with his two moves and in `list_holes` as `kind: flag`
   (`validation.hole_kind`). The Syntactic-level gate on a whole's PASS binds only where the whole's issuer is its Del
   (`validation.whole_waits_for_its_parts`); at a seam the PASS lands and the departure from AND is said (§12.8).
   **Placement closed (2026-10-05):** the level runs at the split's admission, the decomposer's own act (§11.5), over
   the split as it will stand — its children, their coverage, its register — and refuses the split whole, no child
   issued (`gfso/engine/admission.py`, every door that adds a child or changes the register). The child's ACCEPT no
   longer reads its parent's Level-0 holes. What breaks a split admitted clean — a revision of the contract, a child
   cancelled — is §12.10's flag on the decomposer's plan, never a hold on issued work. **Residue:** with the Level-2
   gate on (corner 10) a revision of the contract, or a child's settled cancellation, stales the review, and no fresh
   one runs while a Level-0 hole stands — so an unstarted child the decomposer executes himself waits for his
   repair; another executor's child goes on.

10. **The pre-execution Level-2 gate is an ENGINEERING corner, declared — not a canon row.**
   The engine refuses a child's first ACCEPT while its parent's decomposition carries no current,
   dispositioned causal review (`GFSO_L2_GATE`, on by default) — where the child's executor is the decomposer. The canon licenses no such gate:
   admission is the Syntactic level (§11.5), and the Pragmatic level is checkable only by execution
   (§9.1, §20.2). What the gate enforces is therefore weaker than its name suggested and is stated as
   such in the code: **not** the checker's verdict but the verify-vs-explore decision (§9.9) taken once
   and made mechanical — the check must have HAPPENED over this version of the plan, and each finding
   must have been either repaired or disputed in writing (`dispute_finding`). The verdict stays
   advisory; contact keeps the last word (q_D). `GFSO_L2_GATE=0` is the explicit EXPLORE branch, chosen
   by configuration rather than by an agent skipping a step. The grade: an engineering discipline
   consistent with §9.9 in what it asks, carrying no canon authority. It refuses the child's ACCEPT only where the
   decomposer is the child's executor, who lifts it by his own moves — the review and the disposition of its
   findings (§12.16 (ii)); another executor's child is not refused, and the system holds its own spawn there instead
   (`Engine.execution_blocked_by`, read by the dispatcher), a person taking it exploring (§9.9). A review is current
   for one version of the plan: an admission, a revision of the parent's or a child's contract, and a child's
   settled cancellation each stale it;
   measured on the live substrate (BCB/120: three L0-clean plans, every planted entailment hole named,
   zero false gaps). Two earlier citations claimed more — an address, **13.4-bis**, that exists in no
   version of the canon, and the label "Level 2" used as if §9.5 gated the Pragmatic level. Both are
   corrected in place (`gfso/engine/validation.py`, `tests/test_l2_gate.py`); what the gate does is
   unchanged.

11. **Three §9.5/§12.4 rows the engine read wrongly, and one signal it should never have taken
   (CLOSED).** Repairs, not corners — each is the canon's own sentence, and the code now says it:
   **CHECK-2** verified acyclicity of Dep and called it the row for D, so D-acyclicity (§9.5, §15.3) was
   checked nowhere; a node could be created as its own parent through the authoring door (measured). It
   is now decided where each part of it is visible — the split's own shape in `check_dag`, the ancestor
   chain at the ASSIGN that would close a cycle (`Engine._assert_no_d_cycle`). **CHECK-6** quantified
   over every child where §9.5 quantifies over the split's leaves (a root names its executor at its
   creation, §15.2). **`VALIDATING · ASSIGN→OFFERED`**, a row of §12.4 that §12.14 leans on for
   pre-registration, was refused outright over measured churn; it is admitted now, and the
   re-presentation price §12.10 names is charged instead — the pending PASS is voided at the revision,
   so the node cannot settle on a verdict about a contract it no longer carries. And **`TIMEOUT`**, a
   system mechanism, not a signal (§12.2), was reachable through the tool door: sent on a node in
   VALIDATING it produced `DONE(auto_pass)`, a terminal around the AND gate (Thm 1), around verifier ≠
   executor (§10.3) and around Inv-3. The door now closes on the twelve P2P signals and the engine
   refuses a system signal that carries a sender.

12. **The composition function `fᵢ` does not exist in the model; CHECK-7 hardcodes ONE of them.**
   The canon's split may declare "the **composition function** fᵢ by which its responsible children's
   criteria secure it" (§2.4), which the Semantic level reads (§9.1) and CHECK-7 tests under (§9.6). In
   the code `CriterionMapping` carries only the pair ⟨criterion name, child⟩ — there is nowhere to put
   fᵢ — and `check_sufficiency` supplies a fixed one: it parses numeric bounds and **sums** the
   children's values, so the canon's own worked example (100 + 100 ≤ 200) is checked and, say, a
   max-composition (`latency = max(a, b)`) or a conjunction over booleans is not: such criteria fall into
   the `beyond_tier` bucket and the check reports itself skipped rather than green — the honest half of
   the present state. The gap is therefore not a false PASS but a **missing primitive**: CHECK-7 runs
   mechanically only where the intended fᵢ happens to match the built-in sum (CHECK-8, joint
   satisfiability, reads no fᵢ). Closing it is design work, not a patch — fᵢ must be authored somewhere
   an agent can write it (a field on the mapping), typed enough for the solver (sum / max / min /
   conjunction / a formula for SMT), and defaulted for the existing graphs. Cost, honestly: a schema
   field + a migration of 149 stored graphs + the CHECK-7 dispatch + the authoring verb and its prompt.
   **Not started; declared here so the Semantic level is not read as more than it is.**

13. **The register carries STD-1's estimate; §9.4's roll-up is not computed.** `AcceptedRiskItem` carries `p` and
   `impact` (STD-1's estimate), STD-3's `component`, and the split's own denial entry (§9.5), and CHECK-4 refuses an
   entry without them on a decomposed node. What is still nowhere is the roll-up P(≥ 1) = 1 − ∏(1 − Pᵢ) over STD-3's
   components (§9.4), and `invalidation_condition` is stored and surfaced but never checked for having fired.
   **Open.**

14. **STD-3 components are records; their factorization is the author's.** A component is named on the split
   (`risk_components`), and a child's claim to mitigate it is recorded on that child (`covers_risks`), as `covers`
   records a criterion's; CHECK-5 reads the record and is ⊥, not met, where none exists — the substring match over
   descriptions is gone. Which factors group into which component stays the decomposer's statement (§9.4: the grouping
   method is an implementation choice), unchecked beyond its form.

15. **Inv-4 (Obligation-Symmetry) has no code object; its checkable content is Inv-8.** Of the eight
   invariants, seven are enforced or machine-checked: Inv-1, Inv-2, Inv-3, Inv-5 (pure timeout chains in
   Lean, run level in TLC), Inv-6, Inv-7, and Inv-8 (`FsmCanon.inv8_canon`, `inv8_mirror`). Inv-4
   operates only through the reading §12.9 adopts: its clause (1) is what Inv-8 checks, its clause (2)
   pins CANCELLING and ESCALATED (§12.13). The meta-check this entry used to ask for — "every state gives
   EACH role a move" — was the wrong shape: in the issuer's waits (CHALLENGED, BLOCKED, VALIDATING) only
   the issuer has one, correctly. Inv-8 asks for the OWNER's move, which is what is decided. The
   engine's own conformance to it is the test suite's (`tests/test_model_conformance.py`), not Lean's.

**Two boundaries the E3 measurement walked into, delineated rather than patched (2026-08-16).**

* **A vacuous Level-2 pass.** The gate reported `semantic_covered: true` over `criteria_checked: 0`
  — truthfully, since the node it was checking carried no criteria at all. The hole is closed on the
  structural side (CHECK-1 now fails a node that has children and no criteria of its own: by A1 an
  empty criteria set makes the node unverifiable, not covered), but the CHECKER itself still cannot
  tell "nothing to check" from "nothing to report". Kept as a boundary because the fix belongs to
  the checker's own contract, which is a measured artefact — its wording is calibrated (`EVIDENCE_LOG` §13.6) and
  changing it silently would confound the next reading of C1.

* **`ESCALATED` — the issuer's waiting state, not a settlement (§12.5).** Its entries, owner, moves and
  silent closing are §12.5 and §12.13's; the engine's re-ASSIGN out of it may omit the spec, never a live
  deadline. "The executor says the contract is wrong" does not come here: that is CHALLENGE (§12.4). The
  rework bound is a packet field (§12.3), finite, its value unfixed (§12.15).

**Named abstraction (not a drift): the R′ reopen edge is not in the per-node Lean automaton.** `fsm.py`
admits a gated re-ASSIGN out of DONE/ABANDONED (R′, §12.14) whose gate is a GRAPH predicate (§12.14;
`fsm.py` reads the consumption and counter halves from its GuardContext) — outside the per-node
signature this file models. Lean holds the terminal-absorbing base automaton (under R′ a terminal is
absorbing once final, §12.14); over the log, with the gate an input at the settlements, R′'s cells are
machine-checked forced (`LogLanguageReopen.forced`, §13.5); the reopen edge is TLC-checked at one
node (`formal/tla/FsmSpike.tla`) and its graph gate is code-tested (`tests/test_reopen.py`).
