# formal/tla — the concurrent half of the protocol, model-checked

The Lean development (`formal/GFSO/`) machine-checks the protocol's **static** half:
per-node properties of the FSM table (determinism, Inv-8 ownership, pure timeout chains
ending, the cancel handshake reaching a terminal). This directory checks what Lean cannot
see — the **concurrent system half**: the engine's runtime composition, where many signal
sources interleave through one queue and an asynchronous timeout monitor races the actors.

Model premises are the canon's own (§12.4, and §12.8 for the atomicity of an evaluation):
the evaluation act is atomic (one `process_signal` call = one model step) and time is the
causal order of queue events — no global clock is assumed anywhere.

## The table (`FsmTable.tla`) — v4.1, the table the engine carries

One shared image of `gfso/core/protocol/fsm.py::transition`, which every model EXTENDS.
It carries the canon's v4.1 base machine, which the engine has landed cell for cell (declared in
the module header, the same cells `formal/GFSO/Fsm.lean` declares):
- the first timeouts of OFFERED, CHALLENGED, EXECUTING and REWORKING → ESCALATED — a missed bound
  hands the decision over at once; OVERDUE is no state (not in `States`, not in `IssuerOwned`,
  no row), in the table or in the engine;
- (CHALLENGED, REJECT_CHALLENGE) → OFFERED when the executor has not consented to the current
  packet version, EXECUTING when he has. The consent datum is `Step`'s `cons` argument,
  maintained by `ConsentNext` (set by an accepted ACCEPT, cleared by a new version). FsmSpike and
  FsmSystem carry it per node as a variable `cons`; FsmCascade3 passes FALSE, since its reduced
  alphabet has no CHALLENGE and the cell is never reached there;
- the post-consent CHALLENGE and VALIDATING's timeout → ESCALATED.
`tests/test_model_conformance.py` parses this file and compares it with `fsm.py` on every cell,
both sides of every guard. The module also carries Inv-8's owner
sets and signal senders, and `NewVersion(sig)` — a re-ASSIGN or an ACCEPT_CHALLENGE, the
only two ways a new packet version enters, both through OFFERED and both the issuer's.

## What is checked, and why not `Termination`

v4.0's models checked `Termination == <>[](state ∈ Terminal)`. Once ESCALATED is the
issuer's live waiting state, that is the wrong property: the issuer may legitimately keep
re-ASSIGNing a goal he means to continue (OFFERED → … → ESCALATED → re-ASSIGN → OFFERED),
and a counter on that would re-create the ownerless state by fiat. It is replaced by three
statements, each with its own ground:

| Property | Meaning |
|---|---|
| `WaitsEnd` | F1, Inv-5 as written: no live state (non-terminal, not IDLE) is held forever with no signal processed. Read off (state, packet-version parity): every accepted transition either changes the state or is OFFERED's re-ASSIGN, which flips the parity |
| `NoOwnerlessDivergence` | F2+F3 at run level: every behaviour comes to rest in a terminal (or in IDLE — never issued), or processes infinitely many NEW packet versions, each an issuer's act (re-ASSIGN or ACCEPT_CHALLENGE). No run cycles forever inside one contract, and no run unmakes verdicts without bound |
| `OwnerHasMoveInv` | Inv-8 on every reachable state: the owner of the state the node is in has an admissible move of his own |
| `ChildIssuedOnlyUnderLiveParent` (N ≥ 2) | §12.7 issuing children: a child's FIRST ASSIGN (IDLE → OFFERED) never happens under a CANCELLING or terminal parent — nothing is issued into a fired cascade. An ACTION property; see the N ≥ 2 section |

`EscalatedAbsorbing` is dropped (ESCALATED is no longer absorbing). `FinalityAbsorbing`
(FsmSpike) and `TerminalAbsorbing` (N ≥ 2) are kept.

**The contract clock, per packet version.** `overdue` = "a bound of the CURRENT packet
version has passed": monotone within a version, RESET on every new version (a re-ASSIGN is
never born overdue). The rework counter `iter` counts FAILs under one version: it resets on
every new version (first ASSIGN, revision incl. out of ESCALATED, ACCEPT_CHALLENGE, REOPEN)
and NOT on REJECT_CHALLENGE. The monitor dedups per state VISIT, and a new version opens a
new visit (loop.py's `(state, state_entered_at)` key).

**Named abstractions of the clock — what these models cannot state.** One flag carries both
the packet's deadline and the per-state answer bounds. So the models do NOT express: that
VALIDATING is bounded by T_validate alone, counted from DELIVER, and never by the deadline;
that a state entered after its bound has passed admits no signal before its timeout (here a
signal already queued may still be processed first — e.g. a FAIL-entered REWORKING after
the deadline is not forced to ESCALATED at once); or that a CHALLENGE re-sent after a
REJECT_CHALLENGE under one version is bounded by the deadline alone. What they do check is
that such loops end: the flag is not reset by them. No expiry is attributed to a party.

## Spike — `FsmSpike.tla`

ONE node, the full 12-signal alphabet, hostile actors (any P2P signal at any time; the
engine's rejection path is part of the model), the timeout monitor as a separate process
with its real semantics from `gfso/engine/loop.py::timeout_monitor` (per-visit dedup, stale
delivery — a fired TIMEOUT rides the queue and may land after the state has moved), and the
**R′ REOPEN edge** (§12.14): DONE/ABANDONED + ASSIGN under `¬consumed ∧ ro < MaxReopens`,
with `consumed` a monotone environment fact that may land at any moment or never.

TLC, complete state space, `MaxIterations = 2`, `MaxReopens = 2`, `QueueCap = 3`, one property
per run: **480 008 states generated, 173 922 distinct, depth 35** (v4.0: 86 616 distinct —
the packet-version parity doubles it).

| Spec / cfg | Property | Result |
|---|---|---|
| `Spec` (`FsmSpike.cfg`) | `TypeOK` | holds |
| | `OwnerHasMoveInv` | holds |
| | `WaitsEnd` | holds (38 s) |
| | `NoOwnerlessDivergence` | holds |
| | `FinalityAbsorbing` | holds |
| `SpecNoMonitor` (`FsmSpikeNoMonitor.cfg`) — negative control | `WaitsEnd` | **violated**, as it must be: a lasso holding OFFERED forever, overdue, the actors sending only rejected signals and the dead monitor never firing |
| | `NoOwnerlessDivergence` | violated (the same stall) |
| `SpecNoDeadline` (`FsmSpikeNoDeadline.cfg`) — negative control | `DivergenceUnlessStall` (= `WaitsEnd ⇒ NoOwnerlessDivergence`) | **violated**, as it must be: every wait ends and the node still cycles forever under ONE version — TLC's lasso is EXECUTING ↔ BLOCKED by BLOCK/RESOLVE_BLOCK with `iter` at its bound. No counter bounds that loop (nor the post-consent CHALLENGE ↔ REJECT_CHALLENGE one); the deadline does |
| | (sanity) the same implication under `Spec` | holds |

**R′ regression the model caught earlier (kept as record).** With the reopen edge added,
v4.0's first run refuted `Termination`: the monitor's dedup keyed on the last-FIRED state, so
a node could leave a fired-in state through a terminal and REOPEN back into it before any
cleanup tick — the monitor stayed silent and a withheld CONFIRM_CANCEL stuck the node. Fixed
in `loop.py::timeout_monitor` (dedup per state VISIT); the models mirror it as `mark`
resetting on every processed state change — and, in v4.1, on every new packet version.

## System models — `FsmSystem.tla` (N = 2) and `FsmCascade3.tla` (depth 2)

`FsmSystem`: root + child over ONE shared queue, the full alphabet, the CANCEL cascade, the
per-node monitor, and **crash/recovery** (the crash loses exactly what the process keeps in
memory — the in-flight queue, the monitor's dedup — and keeps what the code persists: graph
state, iteration, deadlines, the log). `FsmCascade3`: root → mid → leaf, the cascade rule
composing through an intermediate node, crash included; actor alphabet reduced to
{ASSIGN, ACCEPT, CANCEL, CONFIRM_CANCEL} (a named choice — full hostility is at N = 1 and 2).

v4.1 changes to both, besides the properties:
- **The cascade fires on ENTERING CANCELLING by either route** — the issuer's CANCEL or
  ESCALATED's timeout. It used to fire on CANCEL only, a model defect: the silence takes the
  cancellation's path precisely so that the live subtree goes with it. `CascadeFor` skips
  IDLE children (as well as terminal and already-cancelling ones), so the delta's case of a
  cascade over unissued children does not arise in the models — consistent with nothing
  being owed on a node that was never issued.
- **Per-visit monitor dedup** (as FsmSpike) — the N ≥ 2 models used to keep the last-fired-
  state dedup, adequate only while nothing could re-enter a state; ESCALATED's re-ASSIGN can.
- **The monitor's queue guard is per node** (at most one pending TIMEOUT per node, a stale one
  included). Under the old shared slot cap TLC refuted both liveness properties on FsmCascade3
  with a starvation lasso: a descendant's issuer re-ASSIGNing forever (OFFERED → OVERDUE →
  ESCALATED → re-ASSIGN) kept the bounded queue full at exactly the moments another node's
  fire was enabled — root held in CANCELLING (`NoOwnerlessDivergence`) and in OFFERED
  (`WaitsEnd`); enabled infinitely often, never continuously, so weak fairness let it starve.
  The real queue is unbounded, so this was the model's artifact, not the protocol's. Strong
  fairness on the shared-cap monitor was tried and dropped (its liveness check had not
  finished after 36 min). With the per-node guard a fire is disabled only by its own pending
  TIMEOUT, which the fair pump drains, so WF is adequate.
  The guard also RESTRICTS the model: the engine can hold two pending TIMEOUTs for one node,
  the model at most one. That is safe for `WaitsEnd` and `NoOwnerlessDivergence`: a TIMEOUT
  edge only moves a node further down its timeout chain (toward ESCALATED, CANCELLING,
  ABANDONED) and never creates a packet version, so an extra delivery can only end a wait,
  never prolong one or add a version. What is NOT checked: a stale TIMEOUT crossing into a new
  packet version. TIMEOUT carries no visit/version key, in the model or in the engine, so one
  fired under the old version can send a fresh OFFERED to ESCALATED (v4.1; OVERDUE before); the model admits that run
  and no property here rejects it. It is an engine item.
- **Inv-8 across the graph (G1/G2)** — what is and is not checked. The models carry no Del
  identities, so "a node's issuer is Del(parent)" is NOT model-checked. What is checked:
  `OwnerHasMoveInv` gives every node in an issuer-owned state (CHALLENGED, BLOCKED,
  VALIDATING, ESCALATED) an admissible issuer move in every reachable graph state,
  and `ActorSend` puts no guard on the parent's state, so that move is sendable whatever the
  parent is doing. `ProbeSettledParentWaitingChild` (a reachability probe, expected VIOLATED)
  shows the case is exercised: a child waiting on its issuer under a settled, escalated or
  cancelling parent is reachable.
- **Issuing children (§12.7).** A child's FIRST ASSIGN (IDLE → OFFERED) is refused while its
  parent is CANCELLING or terminal — a child issued after the cascade fired would escape it;
  moves on children already issued stay admissible in every parent state. The rule is not a
  table row (the table is per node): `FsmTable` names `IssuingBarred` and `FirstIssue`, and
  each model's `Admissible(n, sig)` applies it with its own parent relation inside `Process`,
  i.e. when the signal is PROCESSED, as the engine applies admissibility — a guard on the
  actor's SEND would not do, since an ASSIGN sent under a live parent can be dequeued after
  the cascade fired. `ChildIssuedOnlyUnderLiveParent` is an ACTION property (no history
  variable records the parent's state at issuance): every child IDLE → OFFERED step is taken
  under a parent outside `IssuingBarred`. `ProbeIssueUnderClosedParent` (expected VIOLATED)
  shows the refusal is exercised: a child's first ASSIGN at the head of the queue under a
  CANCELLING or terminal parent is reachable — only through a crash that lost the queued
  ASSIGN (TLC's shortest trace: crash, CANCEL the still-IDLE root, send the child's ASSIGN).
  *What the earlier results say about the guarded models.* Nothing, by transfer: the guard is
  not a removed actor action but a changed outcome of `Process`, the action `WF_vars(Process)`
  is about (a dequeued ASSIGN that used to issue the child is now rejected). So the
  full-constant rows below were measured on the permissive model and are NOT claimed for the
  guarded one; the guarded models were re-checked at `QueueCap = 3` (the table after the
  constants). At that size FsmSystem's state counts coincide with the permissive model's
  (the refused case needs the crash, which leaves little the refusal can change);
  FsmCascade3's graph is smaller.

Constants (repo cfgs): `MaxIterations = 1`, `MaxReopens = 1` (R′ disabled at N ≥ 2 —
`consumed = TRUE`; the reopen edge is checked at N = 1), `QueueCap = 4`, `MaxCrashes = 1`.

Measured 2026-09-22, one property per run (see Running). Full constants (the repo cfgs):
FsmSystem **47 759 264 states generated, 15 773 982 distinct, depth 34**; FsmCascade3
**48 679 155 generated, 15 958 664 distinct, depth 33**. The liveness checks at these sizes
run 35 min to hours each, so every liveness property was ALSO checked at `QueueCap = 3`
(same other constants): FsmSystem 1 873 196 generated / 624 686 distinct, FsmCascade3
3 513 499 generated / 1 174 176 distinct.

| Model | Property | Full constants (`QueueCap = 4`) | `QueueCap = 3` |
|---|---|---|---|
| FsmSystem | `TypeOK` | holds | holds |
| | `OwnerHasMoveInv` | holds | — |
| | `ProbeSettledParentWaitingChild` (probe) | violated at depth 7, as intended | — |
| | `NoOwnerlessDivergence` | NOT RUN to completion (queued) | holds (2 min) |
| | `WaitsEnd` | NOT RUN to completion (queued) | holds (9 min) |
| | `TerminalAbsorbing` | NOT RUN to completion (queued) | holds (1.5 min) |
| FsmCascade3 | `TypeOK` | holds | — |
| | `OwnerHasMoveInv` | holds | — |
| | `ProbeSettledParentWaitingChild` (probe) | violated, as intended | — |
| | `NoOwnerlessDivergence` | holds (35 min) | — |
| | `WaitsEnd` | NOT completed (liveness phase still running at hand-off, > 35 min) | holds (22 min) |
| | `TerminalAbsorbing` | NOT RUN to completion (queued) | holds (5 min) |

**The guarded models (§12.7 issuing children), `QueueCap = 3`**, measured 2026-09-23, one
property per run, `-lncheck final -workers 8`, 8 GB heap. FsmSystem **1 873 196 generated /
624 686 distinct, depth 34** (the permissive counts); FsmCascade3 **3 476 787 generated /
1 162 128 distinct, depth 33** (permissive: 3 513 499 / 1 174 176). The full-constant rows
above are the permissive model's and are not claimed for this one (see *Issuing children*).

| Property | FsmSystem | FsmCascade3 |
|---|---|---|
| `TypeOK` | holds | holds |
| `OwnerHasMoveInv` | holds | holds |
| `ChildIssuedOnlyUnderLiveParent` (action) | holds | holds |
| `ProbeIssueUnderClosedParent` (probe) | violated at depth 6, as intended | violated at depth 6, as intended |
| `ProbeSettledParentWaitingChild` (probe) | violated at depth 7, as intended | violated at depth 10, as intended |
| `NoOwnerlessDivergence` | holds (53 s) | holds (2.7 min) |
| `WaitsEnd` | holds (5.6 min) | holds (18 min) |
| `TerminalAbsorbing` | holds (57 s) | holds (3.4 min) |

**The current table (OVERDUE removed, REJECT_CHALLENGE reading consent), `QueueCap = 3`**, measured 2026-09-24,
one property per run, 8 workers; the tables above were measured on the table WITH OVERDUE and are kept as its
record. FsmSpike (`FsmSpike.cfg`): every property holds, 505 016 generated / 181 770 distinct, depth 35; its negative
controls `SpecNoMonitor` and `SpecNoDeadline` are violated, as they must be. FsmSystem **2 274 136 generated /
753 106 distinct, depth 33**; FsmCascade3 **2 320 559 generated / 751 088 distinct, depth 29**.

| Property | FsmSystem | FsmCascade3 |
|---|---|---|
| `TypeOK` | holds | holds |
| `OwnerHasMoveInv` | holds | holds |
| `ChildIssuedOnlyUnderLiveParent` (action) | holds | holds |
| `ProbeIssueUnderClosedParent` (probe) | violated at depth 7, as intended | violated at depth 7, as intended |
| `ProbeSettledParentWaitingChild` (probe) | violated at depth 8, as intended | violated at depth 10, as intended |
| `NoOwnerlessDivergence` | holds (71 s) | holds (1.9 min) |
| `WaitsEnd` | holds (6.6 min) | holds (10.5 min) |
| `TerminalAbsorbing` | holds (85 s) | holds (2.5 min) |

The full-constant (`QueueCap = 4`) runs were not repeated on the current table.

Negative control: with `Admissible` forced TRUE (the permissive model), TLC refutes
`ChildIssuedOnlyUnderLiveParent` on both models in 6 steps (crash, CANCEL the IDLE root, the
child's ASSIGN processed under the CANCELLING root) — the property has teeth.

Under the OLD shared-cap monitor guard (full constants, the refuted artifact, see above):
FsmCascade3 `NoOwnerlessDivergence` and `WaitsEnd` VIOLATED (starvation lassos),
`TerminalAbsorbing` held (46 min, 80.7M behaviour-graph nodes).


**Named boundary (found by construction):** an ASSIGN still in the queue at crash time is a
task that NEVER EXISTED — creation is the processed ASSIGN, only then logged; nothing to
recover. The properties therefore exclude runs resting in IDLE. Signal-level seamlessness
needs a write-ahead journal of incoming signals — an adapter-level extension, not an FSM change.

**Dispatcher dedup (node×iteration) — subsumed.** The hostile-actor action already sends
arbitrary signals at any time, which includes every duplicate/stale delivery a restarted
dispatcher could produce; the dispatcher's dedup keys are an efficiency discipline, not a
safety mechanism.

## Clock semantics (Inv-5's binding — answered from code, kept honest)

One engine process has ONE clock: the `ClockPort` (`SystemClock = time.time()`, epoch
wall time) — the monitor compares ABSOLUTE persisted deadlines against it. Deadlines
are data (ISO strings in SQLite), not running timers ⟹ process sleep/suspend for N
hours is handled correctly by construction: on wake the next 10s tick sweeps every
deadline that passed meanwhile (the engine today: first fire → OVERDUE / spec-targets, a tick
later → ESCALATED; the v4.1 table: first fire → ESCALATED). Restart = the same shape (the model's Crash step): the monitor's memory
is disposable, pressure re-derives from persisted data.

Trust boundary, named: the guarantee is exactly as strong as the server clock.
Clock jumped FORWARD ⟹ mass overdue is indistinguishable from real overdue. (Under
v4.1's VALIDATING → ESCALATED a clock tamper can no longer
force an acceptance, only hand the move back to the issuer. The engine's current behaviour,
the v4.0 routing, still sends that timeout to DONE(auto_pass) until it lands the change, and
there Thm 11 keeps the auto_pass provenance visible.) Clock jumped BACKWARD ⟹ the monitor
goes silent until real time catches up (Inv-5 pressure suspended, nothing corrupted —
log order is insertion order). Tamper-RESISTANT time (monotonic anchors, signed time)
is the external-implementor open end recorded at probe-hardening — out of core scope.
Registered debt (design named): one aware-UTC discipline at the ingress/`datetime.now()`
surfaces — today naive datetimes mean server-local time consistently; normalizing to
aware-UTC at the ClockPort boundary removes the timezone ambiguity for foreign writers.

## Running

TLC is a Java program (dev-side tooling only — nothing here touches the `gfso`
package or its dependencies).

```
scoop bucket add java && scoop install temurin-lts-jdk       # once
# tools/tla2tools.jar: https://github.com/tlaplus/tlaplus/releases/latest/download/tla2tools.jar
cd formal/tla
java -cp tools/tla2tools.jar tlc2.TLC -workers auto -config FsmSpike.cfg FsmSpike.tla
java -cp tools/tla2tools.jar tlc2.TLC -workers auto -config FsmSpikeNoMonitor.cfg FsmSpike.tla    # expect WaitsEnd violated
java -cp tools/tla2tools.jar tlc2.TLC -workers auto -config FsmSpikeNoDeadline.cfg FsmSpike.tla   # expect a violation
java -Xmx20g -cp tools/tla2tools.jar tlc2.TLC -lncheck final -workers 16 -config FsmCascade3.cfg FsmCascade3.tla
java -Xmx20g -cp tools/tla2tools.jar tlc2.TLC -lncheck final -workers 16 -config FsmSystem.cfg FsmSystem.tla
```

The numbers above were measured one property per run (a scratch cfg holding the repo cfg's
SPECIFICATION and CONSTANTS and exactly one INVARIANT or PROPERTY line); the N ≥ 2 runs with
`-lncheck final` (liveness checked once, on the complete graph — the periodic checks roughly
double a run). The full-constant FsmSystem liveness runs and FsmCascade3's `WaitsEnd` /
`TerminalAbsorbing` had not completed when this was written; they are the pending rows above.
