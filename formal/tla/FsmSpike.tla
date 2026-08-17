---------------------------- MODULE FsmSpike ----------------------------
(* GFSO protocol under concurrency — the first spike.

   ONE node, the full signal alphabet, hostile actors (any P2P signal at any time —
   the engine's rejection path is part of the model, visibility≠enforcement), and
   the timeout monitor as an ASYNC process with its real loop.py semantics: fires
   TIMEOUT once per (task, state) [dedup dict], driven by the deadline clock
   (monotone: once overdue, always overdue). A fired TIMEOUT rides the queue and
   may land AFTER the state has moved — the staleness is real and deliberately
   modeled.

   Model premises are the canon's (v3.9 §4.8, delta D3): the evaluation act is
   ATOMIC (= one Process step), time is the CAUSAL ORDER of queue events — no
   global clock. The transition table lives in FsmTable (one place for all models).

   Checked: TypeOK (safety), Termination (liveness: every behavior reaches a
   terminal state under fairness = Инв-5 at the SYSTEM level, not just per-state). *)

EXTENDS FsmTable

CONSTANT QueueCap

VARIABLES
  state,     \* the node's FSM state
  iter,      \* graph-side iteration counter (guard input, fsm.py VALIDATING+FAIL)
  queue,     \* the signal queue (loop.py); one Process step = one process_signal call
  mark,      \* timeout_monitor's last_timeout_state dedup: last state a TIMEOUT fired in
  overdue,   \* the deadline clock: monotone (a real deadline, once passed, stays passed)
  ro,        \* R' (§6.3): the sign-agnostic reopen counter (graph-side, like iter)
  consumed   \* R' finality-gate input: the node got consumed in the graph (parent staked its
             \* aggregate / a Dep-consumer built on the result / the hole was replanned around).
             \* Modeled as a monotone environment fact, like overdue: consumption may land at an
             \* arbitrary moment and (at this abstraction) does not un-land — the checked claim is
             \* that reopens stay finite over EVERY consumption trajectory, including "never".

vars == <<state, iter, queue, mark, overdue, ro, consumed>>

TypeOK ==
  /\ state \in States
  /\ iter \in 0..MaxIterations
  /\ queue \in Seq(Sigs)
  /\ Len(queue) <= QueueCap
  /\ mark \in States \cup {"NONE"}
  /\ overdue \in BOOLEAN
  /\ ro \in 0..MaxReopens
  /\ consumed \in BOOLEAN

Init ==
  /\ state = "IDLE"
  /\ iter = 0
  /\ queue = <<"ASSIGN">>       \* the transaction opens with ASSIGN (§6.1)
  /\ mark = "NONE"
  /\ overdue = FALSE
  /\ ro = 0
  /\ consumed = FALSE

(* One protocol step: dequeue, transition or reject. Atomicity per D3 — the reopen gate reads
   `consumed` and spends `ro` in the SAME step as the edge (Инв-7: gate+edge are one log-
   serialized act; a queued DELIVER cannot interleave between check and reopen).
   `mark` resets on every state CHANGE = the monitor's per-VISIT dedup key (loop.py keys on
   (state, state_entered_at); a state change restamps entered_at ⟹ a re-entered state is a
   fresh visit). The earlier last-fired-state dedup was REFUTED by this model once the R'
   edge existed: leave a fired-in state through a terminal, REOPEN back in before any
   cleanup — the monitor stays silent and a withheld CONFIRM_CANCEL sticks the node forever. *)
Process ==
  /\ Len(queue) > 0
  /\ LET sig == Head(queue)
         ns  == Step(state, sig, iter, ro, consumed)
     IN /\ queue' = Tail(queue)
        /\ IF ns = "REJECT"
             THEN UNCHANGED <<state, iter, ro, mark>>
             ELSE /\ state' = ns
                  /\ iter' = IF state = "VALIDATING" /\ sig = "FAIL" /\ iter < MaxIterations
                               THEN iter + 1 ELSE iter    \* INCREMENT_ITERATION effect
                  /\ ro' = IF state \in QuasiTerminal /\ sig = "ASSIGN"
                             THEN ro + 1 ELSE ro          \* REOPEN mutation spends the counter
                  /\ mark' = IF ns # state THEN "NONE" ELSE mark   \* new visit ⟹ dedup cleared
  /\ UNCHANGED <<overdue, consumed>>

(* Hostile/arbitrary actors: any P2P signal at any time. One queue slot is reserved for
   the monitor (the real queue is unbounded — the monitor is never starved by actors). *)
ActorSend(sig) ==
  /\ Len(queue) < QueueCap - 1
  /\ queue' = Append(queue, sig)
  /\ UNCHANGED <<state, iter, mark, overdue, ro, consumed>>

\* (mark is UNCHANGED here and in the monitor's own step — only a processed state
\*  change opens a new visit; loop.py's dict mutates only at fire time / state change.)

(* loop.py timeout_monitor: overdue node, not terminal, dedup per state. The enqueued
   TIMEOUT does NOT carry the state it was fired for — staleness modeled faithfully.
   NB after a reopen the node is non-terminal again (OFFERED) — the monitor's pressure
   resumes exactly as the code's does (dedup is per state, and the state changed). *)
MonitorFire ==
  /\ overdue
  /\ state \notin Terminal
  /\ mark # state
  /\ Len(queue) < QueueCap
  /\ queue' = Append(queue, "TIMEOUT")
  /\ mark' = state
  /\ UNCHANGED <<state, iter, overdue, ro, consumed>>

(* The deadline passes at an arbitrary moment and never un-passes. Инв-5's premise:
   a deadline (or state-age bound) EXISTS — deadline-less+timeout-off is the named
   open end (probe-hardening session), excluded from the claim by construction. *)
BecomeOverdue ==
  /\ ~overdue
  /\ overdue' = TRUE
  /\ UNCHANGED <<state, iter, queue, mark, ro, consumed>>

(* Consumption lands at an arbitrary moment (a parent DELIVERs upward, a Dep-consumer
   ACCEPTs and builds, the hole gets replanned around) — no fairness: it may also NEVER
   land, and finiteness must then come from the counter alone (Инв-5). *)
BecomeConsumed ==
  /\ ~consumed
  /\ consumed' = TRUE
  /\ UNCHANGED <<state, iter, queue, mark, overdue, ro>>

Next ==
  \/ Process
  \/ MonitorFire
  \/ BecomeOverdue
  \/ BecomeConsumed
  \/ \E sig \in P2P : ActorSend(sig)

(* Weak fairness: the pump keeps pumping, a passed deadline is eventually noticed,
   the monitor eventually fires when persistently enabled. Actors get NO fairness —
   they may go silent forever (that is the stuck-node scenario Инв-5 exists for). *)
Spec ==
  /\ Init
  /\ [][Next]_vars
  /\ WF_vars(Process)
  /\ WF_vars(MonitorFire)
  /\ WF_vars(BecomeOverdue)

(* NEGATIVE CONTROL (FsmSpikeNoMonitor.cfg): the same system with NO fairness on the
   monitor — a dead monitor. Termination MUST fail here (the checker demonstrably can
   fail; and the counterexample is exactly the live-observed defect class: a stuck
   non-terminal node with no escape — probe-hardening G3). *)
SpecNoMonitor ==
  /\ Init
  /\ [][Next]_vars
  /\ WF_vars(Process)
  /\ WF_vars(BecomeOverdue)

----------------------------------------------------------------------------
(* Properties *)

(* Инв-5 at the system level, R'-strengthened: EVERY behavior eventually reaches a
   terminal state AND STAYS terminal — no interleaving of hostile actors, stale
   TIMEOUTs, revisions and gated REOPENs can keep a node live forever. With the R'
   edge, plain <>(terminal) would be too weak (a reopen legally leaves DONE); the
   claim is absorption-in-the-limit: max_reopens exhausts (or consumption locks the
   node) and the node settles. This is precisely §6.3's "max_reopens восстанавливает
   конечность при появившемся у DONE/ABANDONED исходящем ребре (Инв-5)". *)
Termination == <>[](state \in Terminal)

(* ESCALATED stays FULLY terminal — the R' edge exists only on DONE/ABANDONED. *)
EscalatedAbsorbing == [](state = "ESCALATED" => [](state = "ESCALATED"))

(* Quasi-terminal finality (§6.3): a FINAL quasi-terminal — consumed, or with the
   reopen budget spent — is absorbing: потреблён ∨ исчерпан счётчик ⟹ заперт. *)
FinalityAbsorbing ==
  [](\A t \in QuasiTerminal :
       (state = t /\ (consumed \/ ro = MaxReopens)) => [](state = t))

============================================================================
