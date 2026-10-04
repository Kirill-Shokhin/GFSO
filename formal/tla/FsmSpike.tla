---------------------------- MODULE FsmSpike ----------------------------
(* GFSO protocol under concurrency — the one-node instrument.

   ONE node, the full signal alphabet, hostile actors (any P2P signal at any time —
   the engine's rejection path is part of the model, visibility≠enforcement), and
   the timeout monitor as an ASYNC process with its real loop.py semantics: fires
   TIMEOUT once per state VISIT [dedup keyed on (state, state_entered_at)], driven by
   the contract's clock. A fired TIMEOUT rides the queue and may land AFTER the state
   has moved — the staleness is real and deliberately modeled.

   Model premises are the canon's (§12.4; §12.8 for the atomicity of an evaluation):
   the evaluation act is ATOMIC (= one Process step), time is the CAUSAL ORDER of queue
   events — no global clock. The transition table lives in FsmTable (one place for all
   models).

   The contract clock. `overdue` = "a bound of the CURRENT packet version has passed".
   It is monotone within a version and RESETS on every new packet version (a re-ASSIGN —
   first, revision, REOPEN — or an ACCEPT_CHALLENGE): every entry into OFFERED carries a
   deadline ahead of it, so a re-ASSIGN is never born overdue. NAMED ABSTRACTION: the
   model does not separate the packet's deadline from the per-state answer bounds — one
   flag carries both — so it cannot state that a CHALLENGE re-sent after a
   REJECT_CHALLENGE under the same version is bounded by the deadline alone; what it does
   check is that such a loop ends, because the flag is not reset by it.
   The rework counter `iter` counts FAILs under one packet version: it resets on every new
   version and NOT on REJECT_CHALLENGE (the dispute's negative answer keeps the contract).

   Checked: TypeOK, OwnerHasMoveInv (Inv-8 on every reachable state), WaitsEnd,
   NoOwnerlessDivergence, FinalityAbsorbing — Properties, below. *)

EXTENDS FsmTable

CONSTANT QueueCap

VARIABLES
  state,     \* the node's FSM state
  iter,      \* graph-side iteration counter (guard input, fsm.py VALIDATING+FAIL), per version
  queue,     \* the signal queue (loop.py); one Process step = one process_signal call
  mark,      \* timeout_monitor's dedup: the state it last fired in during the current VISIT
  overdue,   \* the current packet version's clock: monotone within a version, reset by a new one
  ro,        \* R' (§12.14): the sign-agnostic reopen counter (graph-side, like iter)
  consumed,  \* R' finality-gate input: the node got consumed in the graph (parent staked its
             \* aggregate / a Dep-consumer built on the result / the hole was replanned around).
             \* Modeled as a monotone environment fact: consumption may land at an arbitrary
             \* moment and (at this abstraction) does not un-land — the checked claim is that
             \* reopens stay finite over EVERY consumption trajectory, including "never".
  pv,        \* packet-version parity: flips on every accepted new version (history variable —
             \* it is what lets a property say "infinitely many new versions")
  cons       \* consent logged on the current packet version (FsmTable `ConsentNext`); read by
             \* REJECT_CHALLENGE, which returns to OFFERED before consent and EXECUTING after (v4.1)

vars == <<state, iter, queue, mark, overdue, ro, consumed, pv, cons>>

TypeOK ==
  /\ state \in States
  /\ iter \in 0..MaxIterations
  /\ queue \in Seq(Sigs)
  /\ Len(queue) <= QueueCap
  /\ mark \in States \cup {"NONE"}
  /\ overdue \in BOOLEAN
  /\ ro \in 0..MaxReopens
  /\ consumed \in BOOLEAN
  /\ pv \in BOOLEAN
  /\ cons \in BOOLEAN

Init ==
  /\ state = "IDLE"
  /\ iter = 0
  /\ queue = <<"ASSIGN">>       \* the transaction opens with ASSIGN (§11.2)
  /\ mark = "NONE"
  /\ overdue = FALSE
  /\ ro = 0
  /\ consumed = FALSE
  /\ pv = FALSE
  /\ cons = FALSE

(* One protocol step: dequeue, transition or reject. Atomicity per §12.14 — the reopen gate
   reads `consumed` and spends `ro` in the SAME step as the edge (Inv-7: gate+edge are one
   log-serialized act; a queued DELIVER cannot interleave between check and reopen).
   `mark` resets on every state CHANGE and on every new packet version = the monitor's
   per-VISIT dedup key (loop.py keys on (state, state_entered_at); a transition restamps
   entered_at ⟹ a re-entered state, or OFFERED re-offered under a new version, is a fresh
   visit). The earlier last-fired-state dedup was REFUTED by this model once the R' edge
   existed: leave a fired-in state through a terminal, REOPEN back in before any cleanup —
   the monitor stays silent and a withheld CONFIRM_CANCEL sticks the node forever. *)
Process ==
  /\ Len(queue) > 0
  /\ LET sig == Head(queue)
         ns  == Step(state, sig, iter, ro, consumed, cons)
         nv  == ns # "REJECT" /\ NewVersion(sig)
     IN /\ queue' = Tail(queue)
        /\ IF ns = "REJECT"
             THEN UNCHANGED <<state, iter, ro, mark, overdue, pv, cons>>
             ELSE /\ state' = ns
                  /\ iter' = IF nv THEN 0                    \* a new version: a new forecast
                             ELSE IF state = "VALIDATING" /\ sig = "FAIL" /\ iter < MaxIterations
                               THEN iter + 1 ELSE iter      \* INCREMENT_ITERATION effect
                  /\ ro' = IF state \in QuasiTerminal /\ sig = "ASSIGN"
                             THEN ro + 1 ELSE ro          \* REOPEN mutation spends the counter
                  /\ mark' = IF ns # state \/ nv THEN "NONE" ELSE mark   \* new visit ⟹ dedup cleared
                  /\ overdue' = IF nv THEN FALSE ELSE overdue  \* a new contract, a live deadline
                  /\ pv' = IF nv THEN ~pv ELSE pv
                  /\ cons' = ConsentNext(cons, sig, ns)
  /\ UNCHANGED consumed

(* Hostile/arbitrary actors: any P2P signal at any time. One queue slot is reserved for
   the monitor (the real queue is unbounded — the monitor is never starved by actors). *)
ActorSend(sig) ==
  /\ Len(queue) < QueueCap - 1
  /\ queue' = Append(queue, sig)
  /\ UNCHANGED <<state, iter, mark, overdue, ro, consumed, pv, cons>>

(* loop.py timeout_monitor: overdue node, not terminal, dedup per visit. The enqueued
   TIMEOUT does NOT carry the state it was fired for — staleness modeled faithfully.
   NB after a reopen the node is non-terminal again (OFFERED) — the monitor's pressure
   resumes exactly as the code's does. *)
MonitorFire ==
  /\ overdue
  /\ state \notin Terminal
  /\ mark # state
  /\ Len(queue) < QueueCap
  /\ queue' = Append(queue, "TIMEOUT")
  /\ mark' = state
  /\ UNCHANGED <<state, iter, overdue, ro, consumed, pv, cons>>

(* The current version's bound passes at an arbitrary moment and never un-passes within the
   version. Inv-5's premise: a bound EXISTS — deadline-less + timeout-off is the named open
   end (probe-hardening session), excluded from the claim by construction. *)
BecomeOverdue ==
  /\ ~overdue
  /\ overdue' = TRUE
  /\ UNCHANGED <<state, iter, queue, mark, ro, consumed, pv, cons>>

(* Consumption lands at an arbitrary moment (a parent DELIVERs upward, a Dep-consumer
   ACCEPTs and builds, the hole gets replanned around) — no fairness: it may also NEVER
   land, and the bound on reopens must then come from the counter alone. *)
BecomeConsumed ==
  /\ ~consumed
  /\ consumed' = TRUE
  /\ UNCHANGED <<state, iter, queue, mark, overdue, ro, pv, cons>>

Next ==
  \/ Process
  \/ MonitorFire
  \/ BecomeOverdue
  \/ BecomeConsumed
  \/ \E sig \in P2P : ActorSend(sig)

(* Weak fairness: the pump keeps pumping, a passed deadline is eventually noticed,
   the monitor eventually fires when persistently enabled. Actors get NO fairness —
   they may go silent forever (that is the stuck-node scenario Inv-5 exists for) — and
   no obligation to act: an actor may also re-ASSIGN forever, which is the issuer's
   decision, logged each time, and what `NoOwnerlessDivergence` admits by name. *)
Spec ==
  /\ Init
  /\ [][Next]_vars
  /\ WF_vars(Process)
  /\ WF_vars(MonitorFire)
  /\ WF_vars(BecomeOverdue)

(* NEGATIVE CONTROL (FsmSpikeNoMonitor.cfg): the same system with NO fairness on the
   monitor — a dead monitor. `WaitsEnd` MUST fail here (the checker demonstrably can
   fail; the counterexample is exactly the live-observed defect class: a stuck
   non-terminal node with no escape — probe-hardening G3). *)
SpecNoMonitor ==
  /\ Init
  /\ [][Next]_vars
  /\ WF_vars(Process)
  /\ WF_vars(BecomeOverdue)

(* NEGATIVE CONTROL (FsmSpikeNoDeadline.cfg): a live monitor but a contract whose bound
   never has to pass. `DivergenceUnlessStall` MUST fail here: under one packet version
   the actors can cycle a node forever through loops no counter bounds — BLOCK ↔
   RESOLVE_BLOCK (TLC's counterexample), or the post-consent CHALLENGE ↔ REJECT_CHALLENGE
   dispute — and it is the deadline, not a counter, that ends them. *)
SpecNoDeadline ==
  /\ Init
  /\ [][Next]_vars
  /\ WF_vars(Process)
  /\ WF_vars(MonitorFire)

----------------------------------------------------------------------------
(* Properties *)

Live == States \ (Terminal \cup {"IDLE"})

(* Inv-8 on every reachable state: the owner of the state the node is in has an admissible
   move of his own. *)
OwnerHasMoveInv == OwnerHasMove(state, iter, ro, consumed, cons)

(* F1 — WAITS END (Inv-5 as written): no live state is held forever with no signal
   processed. "No signal processed" is read off (state, pv): every accepted transition
   either changes the state or is OFFERED's re-ASSIGN, which flips pv (FsmTable). A run
   resting in IDLE is excluded (IDLE is not in Live: nothing was issued, nobody waits). *)
WaitsEnd ==
  \A s \in Live, b \in BOOLEAN : []<>(state # s \/ pv # b)

(* F2+F3 at run level — NO OWNERLESS DIVERGENCE: every behaviour comes to rest in a
   terminal (or in IDLE, never issued), or it processes infinitely many NEW packet
   versions — each one an issuer's act (re-ASSIGN or ACCEPT_CHALLENGE). No run cycles
   forever inside one contract: rework is bounded by the counter and the contract by its
   deadline; and no run unmakes verdicts without bound (REOPEN spends max_reopens). This
   replaces v4.0's `Termination == <>[](state \in Terminal)`, which is the wrong property
   once ESCALATED is live: the issuer may legitimately keep re-ASSIGNing a goal he means
   to continue, and a counter on that would re-create the ownerless state by fiat. *)
NoOwnerlessDivergence ==
  \/ <>[](state \in Terminal \cup {"IDLE"})
  \/ ([]<>(pv = TRUE) /\ []<>(pv = FALSE))

(* For the NoDeadline control only: without a deadline a run can also fail by STALLING,
   which `WaitsEnd` already names; the implication isolates the other failure — a run in
   which every wait ends and the node still cycles forever under one packet version. *)
DivergenceUnlessStall == WaitsEnd => NoOwnerlessDivergence

(* Quasi-terminal finality (§12.14): a FINAL quasi-terminal — consumed, or with the
   reopen budget spent — is absorbing: consumed ∨ counter exhausted ⟹ locked. *)
FinalityAbsorbing ==
  [](\A t \in QuasiTerminal :
       (state = t /\ (consumed \/ ro = MaxReopens)) => [](state = t))

============================================================================
