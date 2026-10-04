---------------------------- MODULE FsmSystem ----------------------------
(* GFSO phase-2.1: the SYSTEM composition — multiple nodes over one shared queue,
   the CANCEL cascade, the async timeout monitor, and CRASH/RECOVERY.

   Extends FsmSpike (one-node instrument, proven there both ways) with what Lean
   cannot see and the spike deferred:
   - two nodes (root + child, E_D edge) interleaving over the shared signal queue;
   - the cascade: ENTERING CANCELLING — by the issuer's CANCEL or by ESCALATED's timeout
     (his silence takes the cancellation's own path, §12.5) — enqueues CANCEL for each
     live descendant (loop.py `_execute_effects`: mutations return affected children);
   - CRASH: the process dies and restarts. What persists is exactly what the code
     persists (graph state + audit log in SQLite, deadlines are data); what is LOST
     is exactly what lives in process memory: the in-flight signal QUEUE and the
     monitor's dedup dict. state = fold(log) — the log is durable, the queue is not.

   Per node, as in FsmSpike: the contract clock `overdue` and the rework counter `iter`
   belong to the CURRENT packet version and reset on every new one (re-ASSIGN or
   ACCEPT_CHALLENGE; not on REJECT_CHALLENGE); the monitor dedups per state VISIT (a
   transition, or a new version, opens a new visit — loop.py's (state, state_entered_at)
   key); `pv` is the packet-version parity history variable. One flag carries both the
   deadline and the per-state bounds (the named abstraction of FsmSpike).

   NAMED BOUNDARY (found by construction, kept honest): an ASSIGN still in the
   queue at crash time is a task that NEVER EXISTED (creation is the ASSIGN
   transition, logged only when processed). No log entry → nothing to recover →
   the protocol cannot move what was never created. Durable ingress (a write-ahead
   signal journal) would be an ADAPTER-level extension, not an FSM change; the
   properties below therefore exclude runs resting in IDLE. The transition table
   lives in FsmTable. *)

EXTENDS FsmTable

CONSTANTS QueueCap, MaxCrashes

Root == "root"
Child == "child"
Nodes == {Root, Child}

Msg == [node: Nodes, sig: Sigs]
Parent(n) == IF n = Child THEN Root ELSE "none"

VARIABLES
  state,        \* [Nodes -> States]
  iter,         \* [Nodes -> 0..MaxIterations], per packet version
  queue,        \* shared signal queue (process memory — lost on crash)
  mark,         \* monitor dedup per node and visit (process memory — lost on crash)
  overdue,      \* per-node contract clocks (data: survive crash; reset by a new version)
  crashesLeft,  \* crash budget (finite: liveness is meaningless under infinite crashes)
  pv,           \* [Nodes -> BOOLEAN] packet-version parity (log-derived: survives crash)
  cons          \* [Nodes -> BOOLEAN] consent on the current version (log-derived: survives crash)

vars == <<state, iter, queue, mark, overdue, crashesLeft, pv, cons>>

TypeOK ==
  /\ state \in [Nodes -> States]
  /\ iter \in [Nodes -> 0..MaxIterations]
  /\ queue \in Seq(Msg)
  /\ Len(queue) <= QueueCap + 2   \* actors ≤ QueueCap-2, + ≤ 1 pending TIMEOUT per node (2 nodes)
  /\ mark \in [Nodes -> States \cup {"NONE"}]
  /\ overdue \in [Nodes -> BOOLEAN]
  /\ crashesLeft \in 0..MaxCrashes
  /\ pv \in [Nodes -> BOOLEAN]
  /\ cons \in [Nodes -> BOOLEAN]

Init ==
  /\ state = [n \in Nodes |-> "IDLE"]
  /\ iter = [n \in Nodes |-> 0]
  /\ queue = <<[node |-> Root, sig |-> "ASSIGN"], [node |-> Child, sig |-> "ASSIGN"]>>
  /\ mark = [n \in Nodes |-> "NONE"]
  /\ overdue = [n \in Nodes |-> FALSE]
  /\ crashesLeft = MaxCrashes
  /\ pv = [n \in Nodes |-> FALSE]
  /\ cons = [n \in Nodes |-> FALSE]

(* §12.7: a child's first ASSIGN is refused under a CANCELLING or terminal parent. Applied where
   the engine applies admissibility — when the signal is PROCESSED, not when it is sent: an
   ASSIGN sent earlier may be dequeued after the cascade fired, and is then rejected. *)
Admissible(n, sig) ==
  Parent(n) = "none" \/ ~FirstIssue(state[n], sig) \/ state[Parent(n)] \notin IssuingBarred

(* The cascade (§12.6/§15.1): the root ENTERING CANCELLING sends CANCEL to each live
   descendant; each runs its own handshake. Two-node instance: Root -> {Child}. It fires on
   entry by either route — the issuer's CANCEL, or ESCALATED's timeout — since the silence
   takes the cancellation's path precisely so that the live subtree goes with it. *)
CascadeFor(n, ns) ==
  IF n = Root /\ ns = "CANCELLING" /\ state[n] # "CANCELLING"
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
         \* and its system-level behaviour is checked at N=1 (FsmSpike, full alphabet + reopens);
         \* the finality-gate's GRAPH predicate (consumption/settlement/replanning) is code-tested.
         \* A named scope choice, mirroring the cascade model's reduced-alphabet choice.
         ns  == IF Admissible(n, sig) THEN Step(state[n], sig, iter[n], MaxReopens, TRUE, cons[n])
                ELSE "REJECT"
         nv  == ns # "REJECT" /\ NewVersion(sig)
     IN IF ns = "REJECT"
        THEN /\ queue' = Tail(queue)
             /\ UNCHANGED <<state, iter, mark, overdue, pv, cons>>
        ELSE /\ state' = [state EXCEPT ![n] = ns]
             /\ iter' = IF nv THEN [iter EXCEPT ![n] = 0]
                        ELSE IF state[n] = "VALIDATING" /\ sig = "FAIL" /\ iter[n] < MaxIterations
                          THEN [iter EXCEPT ![n] = @ + 1] ELSE iter
             /\ mark' = IF ns # state[n] \/ nv THEN [mark EXCEPT ![n] = "NONE"] ELSE mark
             /\ overdue' = IF nv THEN [overdue EXCEPT ![n] = FALSE] ELSE overdue
             /\ pv' = IF nv THEN [pv EXCEPT ![n] = ~@] ELSE pv
             /\ cons' = [cons EXCEPT ![n] = ConsentNext(@, sig, ns)]
             /\ queue' = Tail(queue) \o CascadeFor(n, ns)
  /\ UNCHANGED crashesLeft

(* Hostile actors: two slots reserved (monitor + cascade never starved — real queue
   is unbounded). No guard on the PARENT's state at send time: a node's issuer can move on
   it whatever the parent is doing (G2 below); the one move the parent's state restricts,
   a child's first ASSIGN, is refused at processing (`Admissible`). *)
ActorSend(n, sig) ==
  /\ Len(queue) < QueueCap - 2
  /\ queue' = Append(queue, [node |-> n, sig |-> sig])
  /\ UNCHANGED <<state, iter, mark, overdue, crashesLeft, pv, cons>>

(* timeout_monitor per node: only CREATED tasks (graph.active_tasks() — an IDLE node
   does not exist in the graph), overdue, dedup per visit.
   Its queue guard is PER NODE: a fire is held back only while this node's own previous
   TIMEOUT is still in the queue (at most one pending per node — a stale one included, so
   stale delivery is still modeled). It used to share the global slot cap with the actors;
   the real queue is unbounded, and once an issuer may re-ASSIGN a live node forever (v4.1's
   ESCALATED) that shared cap became an artifact that bites: other nodes' fires and actor
   traffic kept the bounded queue full at exactly the moments this node's fire was enabled,
   so it was enabled infinitely often but never continuously and WEAK fairness let it starve.
   TLC found that lasso on FsmCascade3 under the shared cap (root held in CANCELLING, and in
   another run in OFFERED, while a descendant cycled OFFERED → OVERDUE → ESCALATED →
   re-ASSIGN). With the per-node guard the fire is disabled only by its own pending TIMEOUT,
   which the fair pump drains, so WF is adequate. (Strong fairness on the shared-cap monitor
   was tried and dropped: TLC's liveness check under SF did not finish in 36 min.) *)
MonitorFire(n) ==
  /\ overdue[n]
  /\ state[n] \notin (Terminal \cup {"IDLE"})
  /\ mark[n] # state[n]
  /\ \A i \in 1..Len(queue) : queue[i] # [node |-> n, sig |-> "TIMEOUT"]
  /\ queue' = Append(queue, [node |-> n, sig |-> "TIMEOUT"])
  /\ mark' = [mark EXCEPT ![n] = state[n]]
  /\ UNCHANGED <<state, iter, overdue, crashesLeft, pv, cons>>

BecomeOverdue(n) ==
  /\ ~overdue[n]
  /\ overdue' = [overdue EXCEPT ![n] = TRUE]
  /\ UNCHANGED <<state, iter, queue, mark, crashesLeft, pv, cons>>

(* CRASH/RECOVERY in one atomic step: the process dies and comes back.
   Persists (SQLite): graph state, iteration, deadlines (overdue is data), the log.
   Lost (process memory): the in-flight queue, the monitor's dedup dict. *)
Crash ==
  /\ crashesLeft > 0
  /\ crashesLeft' = crashesLeft - 1
  /\ queue' = <<>>
  /\ mark' = [n \in Nodes |-> "NONE"]
  /\ UNCHANGED <<state, iter, overdue, pv, cons>>

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
Live == States \ (Terminal \cup {"IDLE"})

(* F1, crash included — per node: no live state is held forever with no signal processed
   (read off (state, pv), as in FsmSpike). Resting in IDLE — never created — is excluded. *)
WaitsEnd ==
  \A n \in Nodes, s \in Live, b \in BOOLEAN : []<>(state[n] # s \/ pv[n] # b)

(* F2+F3, crash included — per node: every node comes to rest in a terminal (or in IDLE,
   never created), or processes infinitely many new packet versions, each an issuer's act. *)
NoOwnerlessDivergence ==
  \A n \in Nodes :
    \/ <>[](state[n] \in Terminal \cup {"IDLE"})
    \/ ([]<>(pv[n] = TRUE) /\ []<>(pv[n] = FALSE))

TerminalAbsorbing ==
  \A n \in Nodes, t \in Terminal : []((state[n] = t) => [](state[n] = t))

(* Inv-8, per node, on every reachable graph state. *)
OwnerHasMoveInv == \A n \in Nodes : OwnerHasMove(state[n], iter[n], MaxReopens, TRUE, cons[n])

(* The model carries no Del identities, so "a node's issuer is Del(parent)" is not checked
   here. What is: `OwnerHasMoveInv` gives every node in an issuer-owned state an admissible
   issuer move, whatever the parent's state, and `ActorSend` puts no guard on the parent's
   state, so that move is sendable.
   REACHABILITY PROBE — expected VIOLATED: a child waiting on its issuer under a parent that
   is settled, escalated or cancelling IS reachable, so G2's case is exercised. *)
ProbeSettledParentWaitingChild ==
  ~(state[Root] \in {"DONE", "ABANDONED", "ESCALATED", "CANCELLING"}
    /\ state[Child] \in IssuerOwned)

(* §12.7, issuing children: every IDLE → OFFERED step of a child is taken under a parent that
   is neither CANCELLING nor terminal — an ACTION property, since no history variable records
   the parent's state at issuance. Then the REACHABILITY PROBE, expected VIOLATED: a child's
   first ASSIGN reaches the head of the queue under a CANCELLING or terminal parent, so the
   refusal is exercised (and by the property the child stays IDLE). *)
ChildIssuedOnlyUnderLiveParent ==
  [][\A n \in Nodes : (Parent(n) # "none" /\ state[n] = "IDLE" /\ state'[n] = "OFFERED")
                      => state[Parent(n)] \notin IssuingBarred]_vars

ProbeIssueUnderClosedParent ==
  ~(\E n \in Nodes : Parent(n) # "none" /\ Len(queue) > 0
       /\ Head(queue) = [node |-> n, sig |-> "ASSIGN"] /\ state[n] = "IDLE"
       /\ state[Parent(n)] \in IssuingBarred)

============================================================================
