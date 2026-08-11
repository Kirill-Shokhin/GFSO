# formal/tla — the concurrent half of the protocol, model-checked

The Lean development (`formal/GFSO/`) machine-checks the protocol's **static** half:
per-node properties of the FSM table (determinism, timeout termination, the cancel
handshake reaching a terminal). This directory checks what Lean cannot see — the
**concurrent system half**: the engine's runtime composition, where many signal sources
interleave through one queue and an asynchronous timeout monitor races the actors.

Model premises are the canon's own (v3.9 §4.8, delta D3): the evaluation act is atomic
(one `process_signal` call = one model step) and time is the causal order of queue
events — no global clock is assumed anywhere.

## Spike (ROADMAP DoD 2.0) — DONE

`FsmSpike.tla` — ONE node, the full 12-signal alphabet, hostile actors (any P2P signal
at any time; the engine's rejection path is part of the model), the timeout monitor as
a separate process with its real semantics from `gfso/engine/loop.py::timeout_monitor`:
per-(task, state) dedup, a monotone deadline clock, and **stale delivery** — a fired
TIMEOUT rides the queue and may land after the state has moved.

The transition function `Step` is a verbatim image of
`gfso/core/protocol/fsm.py::transition`, including the iteration guard on
VALIDATING+FAIL, the universal-CANCEL catch-all, revision (re-ASSIGN → REVIEW,
§14.4 Inv-1) and the **R′ REOPEN edge** (§14.3): DONE/CANCELLED + ASSIGN under the
double gate `¬consumed ∧ ro < MaxReopens` → REVIEW. `consumed` (the finality-gate
verdict) is modeled as a monotone environment fact like `overdue` — it may land at
any moment or never; the checked claim is finiteness over EVERY consumption
trajectory. The reopen counter is spent in the same atomic step as the edge (Inv-7).

Checked by TLC over the **complete** state space (86 616 distinct states,
MaxReopens = 2):

| Property | Meaning | Result |
|---|---|---|
| `TypeOK` | state/iteration/queue/reopens stay well-typed and bounded | holds |
| `Termination` | **Inv-5 at the system level, R′-strengthened to `<>[]`(terminal)**: every behavior eventually reaches a terminal state AND STAYS terminal — gated reopens included; max_reopens restores finiteness for the new outgoing edge exactly as §6.3 claims | holds |
| `EscalatedAbsorbing` | ESCALATED stays fully terminal (the R′ edge exists only on DONE/CANCELLED) | holds |
| `FinalityAbsorbing` | a FINAL quasi-terminal (consumed ∨ reopens exhausted) is absorbing — потреблён ∨ исчерпан счётчик ⟹ заперт (§6.3) | holds |

**R′ regression the model caught (and the code fix it forced).** With the reopen
edge added, the FIRST run refuted `Termination`: the monitor's dedup keyed on the
last-FIRED state, so a node could leave a fired-in state through a terminal and
REOPEN back into it before any cleanup tick (…→ CANCELLING(fired) → CANCELLED →
reopen → … → CANCELLING again) — the monitor stayed silent forever and a withheld
CANCEL_ACK stuck the node: an Inv-5 violation reachable only through R′, invisible
to the unit tests. Fix in `loop.py::timeout_monitor`: dedup per state **VISIT** —
key = (state, `state_entered_at`), every state change restamps the entry ⟹ a
re-entered state fires again. The model mirrors this as `mark` resetting on every
processed state change. The green run above is post-fix; the pre-fix table is the
refuted artifact.

**Negative control** (`FsmSpikeNoMonitor.cfg`): the same system with a dead monitor
(no fairness on `MonitorFire`). `Termination` fails with a lasso counterexample — the
node sits in CANCELLING forever while the executor withholds CANCEL_ACK. That is
exactly the FSM-deadlock class §14.2 assigns to CANCEL_ACK, and the live-observed
stuck-node defect (probe-hardening G3). The instrument demonstrably fails on a broken
system; the green run above is not vacuous.

Named modeling choices:
- One queue slot is reserved for the monitor (`ActorSend` caps at `QueueCap - 1`) —
  the real queue is unbounded, so actors can never starve the monitor; the bound only
  keeps the state space finite.
- `overdue` eventually becomes true (weak fairness on `BecomeOverdue`) = "a deadline
  or state-age bound exists". The deadline-less node with `GFSO_STATE_TIMEOUT=0` is
  the KNOWN open end recorded at probe-hardening — excluded from the claim by
  construction, not silently.
- Bounds: `MaxIterations = 2`, `QueueCap = 3` (complete search within them).

## System model (DoD 2.1) — first result

`FsmSystem.tla` — the composition Lean cannot see: two nodes (root + child, E_D edge)
over ONE shared queue, the CANCEL cascade (entering CANCELLING enqueues CANCEL per
live descendant), the per-node monitor, and **crash/recovery**. The crash step loses
exactly what the process keeps in memory (the in-flight signal queue, the monitor's
dedup dict) and keeps exactly what the code persists (graph state, iteration, the
audit log, deadlines) — `state = fold(log)`: the log is durable, the queue is not.

TLC over the **complete** state space — 16 156 261 distinct states, temporal checking
over 113M states, no error (~44 min, 20 workers):

| Property | Meaning | Result |
|---|---|---|
| `TypeOK` | well-typedness incl. queue bound (cascade appends net ≤ 0) | holds |
| `Termination` | **Inv-5 through a crash**: every CREATED node reaches a terminal state — the monitor re-derives its pressure from persistent data (deadlines) and needs none of its lost memory; hostile actors, stale TIMEOUTs, revisions and a worst-point crash included | holds |
| `TerminalAbsorbing` | terminals absorbing, per node | holds |

**Named boundary (found by construction):** an ASSIGN still in the queue at crash
time is a task that NEVER EXISTED — creation is the processed ASSIGN transition, only
then logged; no log entry → nothing to recover → the protocol cannot terminate what
was never created (`Termination` quantifies over Terminal ∪ {IDLE}; a node leaves
IDLE at most once, so the disjunct is no escape hatch). Signal-level seamlessness
("no in-flight signal is ever lost") requires a write-ahead journal of INCOMING
signals — an adapter-level extension, not an FSM change; candidate registered debt,
adjacent to the parked finality/rollback question.

**Dispatcher dedup (node×iteration) — subsumed, closed by argument + tests, not a
new model.** The hostile-actor action already sends ARBITRARY signals at any time —
which includes every duplicate/stale delivery a crashed-and-restarted dispatcher
(its dedup sets are process memory) could ever produce. The green Termination/TypeOK
therefore already prove the PROTOCOL safe under duplicated dispatch; the dispatcher's
dedup keys are an EFFICIENCY discipline (don't burn duplicate LLM runs), not a safety
mechanism — exercised live (probe-hardening G6: revision staleness) and unit-tested.

**Cascade transitivity (`FsmCascade3.tla`) — the depth-2 chain, closed.** root→mid→leaf,
the same cascade rule composing THROUGH an intermediate node, a crash allowed at any
point (a queued cascade-CANCEL dies with the queue — the monitor terminates the
orphans from persisted data). Complete 5 275 552-state search, temporal over 52.7M:
no error. Actor alphabet reduced to the cancel/cascade core {ASSIGN, ACCEPT, CANCEL,
CANCEL_ACK} — a named choice: full hostility is proven at N=1 and N=2; the first
full-alphabet attempt OOM'd the liveness graph (13.5M states × 10 branches), and the
dropped branches only multiply that graph without touching the cascade mechanism.

**R′ at N≥2 — a named scope choice.** The N=2/N=3 models call
`Step(…, MaxReopens, TRUE)`: the reopen edge is DISABLED there. Rationale: the edge
is per-node (one re-ASSIGN row) and its system-level liveness incl. the monitor
interaction is checked at N=1 with the full alphabet; the finality-gate's GRAPH
predicate (consumption / cascade settlement / replanning) is not a transition-table
object — it is unit-tested code (`tests/test_reopen.py`). With the arm unreachable,
the N≥2 checked objects are semantically unchanged from their green runs (their
`mark` also keeps the pre-R′ last-fired-state abstraction, which their runs proved
adequate for a node that cannot exit a terminal; the code's per-visit dedup only
fires MORE often, which is monotone for the liveness those runs claim).

**DoD 2.1 status: the modeled scope is CLOSED** — interleaving over a shared queue
(N=2, full alphabet), the monitor as a live process (stale fires included), the
cancel handshake and cascade through depth 2, crash/recovery (= signal loss),
system-level liveness (Termination) and terminal absorption; R′ reopens at N=1
(gated finality, absorption-in-the-limit); determinism is
structural (Step is a function; Lean holds the per-node static half). The transition
table has ONE shared image (`FsmTable.tla`) — models cannot drift apart.
Runtimes: the spike config is CI-grade (seconds); `FsmSystem.cfg` ~45 min,
`FsmCascade3.cfg` ~13 min (local/nightly; TLC heap 20g for the cascade run).

## Clock semantics (Inv-5's binding — answered from code, kept honest)

One engine process has ONE clock: the `ClockPort` (`SystemClock = time.time()`, epoch
wall time) — the monitor compares ABSOLUTE persisted deadlines against it. Deadlines
are data (ISO strings in SQLite), not running timers ⟹ process sleep/suspend for N
hours is handled correctly by construction: on wake the next 10s tick sweeps every
deadline that passed meanwhile (first fire → TIMEOUT / spec-targets, a tick later →
ESCALATED). Restart = the same shape (the model's Crash step): the monitor's memory
is disposable, pressure re-derives from persisted data.

Trust boundary, named: the guarantee is exactly as strong as the server clock.
Clock jumped FORWARD ⟹ mass overdue is indistinguishable from real overdue (incl.
VALIDATING → DONE(auto_pass), §24.7 — a clock tamper can force auto-acceptance;
T11 keeps the auto_pass provenance visible). Clock jumped BACKWARD ⟹ the monitor
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
java -cp tools/tla2tools.jar tlc2.TLC -workers auto -config FsmSpikeNoMonitor.cfg FsmSpike.tla   # expect a violation
```
