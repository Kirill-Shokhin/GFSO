---------------------------- MODULE FsmSystem ----------------------------
(* GFSO phase-2.1: the SYSTEM composition — multiple nodes over one shared queue,
   the CANCEL cascade, the async timeout monitor, and CRASH/RECOVERY.

   Extends FsmSpike (one-node instrument, proven there both ways) with what Lean
   cannot see and the spike deferred:
   - two nodes (root + child, E_D edge) interleaving over the shared signal queue;
   - the cascade: entering CANCELLING enqueues CANCEL for each live descendant
     (loop.py `_execute_effects`: mutations return affected children);
   - CRASH: the process dies and restarts. What persists is exactly what the code
     persists (graph state + audit log in SQLite, deadlines are data); what is LOST
     is exactly what lives in process memory: the in-flight signal QUEUE and the
     monitor's dedup dict (`last_timeout_state`). state = fold(log) — the log is
     durable, the queue is not.

   The recovery claim checked here (Termination): every CREATED node still reaches
   a terminal state after any single crash at any point — the monitor re-derives
   pressure from persistent data (deadlines), needing none of its lost memory.

   NAMED BOUNDARY (found by construction, kept honest): an ASSIGN still in the
   queue at crash time is a task that NEVER EXISTED (creation is the ASSIGN
   transition, logged only when processed). No log entry → nothing to recover →
   the protocol cannot terminate what was never created. Durable ingress (a
   write-ahead signal journal) would be an ADAPTER-level extension, not an FSM
   change; the property below therefore quantifies over created nodes:
   Terminal ∪ {IDLE}. The transition table lives in FsmTable. *)

EXTENDS FsmTable

CONSTANTS QueueCap, MaxCrashes

Root == "root"
Child == "child"
Nodes == {Root, Child}

Msg == [node: Nodes, sig: Sigs]

VARIABLES
  state,        \* [Nodes -> States]
  iter,         \* [Nodes -> 0..MaxIterations]
  queue,        \* shared signal queue (process memory — lost on crash)
  mark,         \* monitor dedup per node (process memory — lost on crash)
  overdue,      \* deadline clocks (data: monotone, survive crash)
  crashesLeft   \* crash budget (finite: liveness is meaningless under infinite crashes)

vars == <<state, iter, queue, mark, overdue, crashesLeft>>

TypeOK ==
  /\ state \in [Nodes -> States]
  /\ iter \in [Nodes -> 0..MaxIterations]
  /\ queue \in Seq(Msg)
  /\ Len(queue) <= QueueCap
  /\ mark \in [Nodes -> States \cup {"NONE"}]
  /\ overdue \in [Nodes -> BOOLEAN]
  /\ crashesLeft \in 0..MaxCrashes

Init ==
  /\ state = [n \in Nodes |-> "IDLE"]
  /\ iter = [n \in Nodes |-> 0]
  /\ queue = <<[node |-> Root, sig |-> "ASSIGN"], [node |-> Child, sig |-> "ASSIGN"]>>
  /\ mark = [n \in Nodes |-> "NONE"]
  /\ overdue = [n \in Nodes |-> FALSE]
  /\ crashesLeft = MaxCrashes

(* The cascade (§6.2/§7.1): the root entering CANCELLING sends CANCEL to each live
   descendant; each runs its own handshake. Two-node instance: Root -> {Child}. *)
CascadeFor(n, ns, sig) ==
  IF n = Root /\ ns = "CANCELLING" /\ sig = "CANCEL"
     /\ state[Child] \notin (Terminal \cup {"CANCELLING", "IDLE"})
  THEN <<[node |-> Child, sig |-> "CANCEL"]>>
  ELSE <<>>

(* One process_signal step: pop, transition or reject, append cascade (net <= 0). *)
Process ==
  /\ Len(queue) > 0
  /\ LET m   == Head(queue)
         n   == m.node
         sig == m.sig
         \* R' reopen deliberately DISABLED at N=2 (consumed=TRUE): the reopen edge is per-node
         \* and its system-level liveness is checked at N=1 (FsmSpike, full alphabet + reopens);
         \* the finality-gate's GRAPH predicate (consumption/settlement/replanning) is code-tested.
         \* A named scope choice, mirroring the cascade model's reduced-alphabet choice below.
         ns  == Step(state[n], sig, iter[n], MaxReopens, TRUE)
     IN IF ns = "REJECT"
        THEN /\ queue' = Tail(queue)
             /\ UNCHANGED <<state, iter>>
        ELSE /\ state' = [state EXCEPT ![n] = ns]
             /\ iter' = IF state[n] = "VALIDATING" /\ sig = "FAIL" /\ iter[n] < MaxIterations
                          THEN [iter EXCEPT ![n] = @ + 1] ELSE iter
             /\ queue' = Tail(queue) \o CascadeFor(n, ns, sig)
  /\ UNCHANGED <<mark, overdue, crashesLeft>>

(* Hostile actors: two slots reserved (monitor + cascade never starved — real queue
   is unbounded). *)
ActorSend(n, sig) ==
  /\ Len(queue) < QueueCap - 2
  /\ queue' = Append(queue, [node |-> n, sig |-> sig])
  /\ UNCHANGED <<state, iter, mark, overdue, crashesLeft>>

(* timeout_monitor per node: only CREATED tasks (graph.active_tasks() — an IDLE node
   does not exist in the graph), overdue, dedup per state. One slot reserved for the
   cascade. *)
MonitorFire(n) ==
  /\ overdue[n]
  /\ state[n] \notin (Terminal \cup {"IDLE"})
  /\ mark[n] # state[n]
  /\ Len(queue) < QueueCap - 1
  /\ queue' = Append(queue, [node |-> n, sig |-> "TIMEOUT"])
  /\ mark' = [mark EXCEPT ![n] = state[n]]
  /\ UNCHANGED <<state, iter, overdue, crashesLeft>>

BecomeOverdue(n) ==
  /\ ~overdue[n]
  /\ overdue' = [overdue EXCEPT ![n] = TRUE]
  /\ UNCHANGED <<state, iter, queue, mark, crashesLeft>>

(* CRASH/RECOVERY in one atomic step: the process dies and comes back.
   Persists (SQLite): graph state, iteration, deadlines (overdue is data).
   Lost (process memory): the in-flight queue, the monitor's dedup dict. *)
Crash ==
  /\ crashesLeft > 0
  /\ crashesLeft' = crashesLeft - 1
  /\ queue' = <<>>
  /\ mark' = [n \in Nodes |-> "NONE"]
  /\ UNCHANGED <<state, iter, overdue>>

Next ==
  \/ Process
  \/ Crash
  \/ \E n \in Nodes : MonitorFire(n) \/ BecomeOverdue(n)
  \/ \E n \in Nodes, sig \in P2P : ActorSend(n, sig)

(* Fairness: pump + per-node monitor/deadline. Actors and Crash get none (may never
   act — and crash may strike at the worst point; the budget keeps behaviors sane). *)
Spec ==
  /\ Init
  /\ [][Next]_vars
  /\ WF_vars(Process)
  /\ \A n \in Nodes : WF_vars(MonitorFire(n)) /\ WF_vars(BecomeOverdue(n))

----------------------------------------------------------------------------
(* Инв-5 at the SYSTEM level, crash included: eventually-forever every node is
   terminal — or IDLE, the never-created case (its ASSIGN died in the queue: no log
   entry, nothing to recover — the named boundary above; a node leaves IDLE at most
   once, so the disjunction is not an escape hatch). *)
Termination == <>[](\A n \in Nodes : state[n] \in (Terminal \cup {"IDLE"}))

TerminalAbsorbing ==
  \A n \in Nodes, t \in Terminal : []((state[n] = t) => [](state[n] = t))

============================================================================
