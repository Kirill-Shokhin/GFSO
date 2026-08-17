---------------------------- MODULE FsmCascade3 ----------------------------
(* Cascade TRANSITIVITY (2.1 remainder): a depth-2 chain root → mid → leaf.
   The cascade rule is the same at every level (entering CANCELLING enqueues CANCEL
   per live child — loop.py `_execute_effects`); this instance checks that it
   composes THROUGH an intermediate node, interleaved with the monitor and a crash
   at any point (a queued cascade-CANCEL can die with the queue — the monitor must
   still terminate the orphaned descendants).

   The actor alphabet is REDUCED to the cascade-relevant core (named modeling
   choice, keeps the space tractable): full hostility over the complete alphabet is
   proven at N=1 (FsmSpike) and N=2 (FsmSystem); this run isolates depth. *)

EXTENDS FsmTable

CONSTANTS QueueCap, MaxCrashes

Nodes == {"root", "mid", "leaf"}
ChildOf(n) == IF n = "root" THEN "mid" ELSE IF n = "mid" THEN "leaf" ELSE "none"

(* Cancel/cascade core only: DELIVER/PASS branches are exercised at N=1/N=2 with the
   full alphabet; here they only multiply the liveness graph (first attempt OOM'd on
   13.5M states × 10 temporal branches). *)
ActorSigs == {"ASSIGN", "ACCEPT", "CANCEL", "CONFIRM_CANCEL"}

Msg == [node: Nodes, sig: Sigs]

VARIABLES state, iter, queue, mark, overdue, crashesLeft

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
  /\ queue = <<[node |-> "root", sig |-> "ASSIGN"], [node |-> "mid", sig |-> "ASSIGN"],
               [node |-> "leaf", sig |-> "ASSIGN"]>>
  /\ mark = [n \in Nodes |-> "NONE"]
  /\ overdue = [n \in Nodes |-> FALSE]
  /\ crashesLeft = MaxCrashes

CascadeFor(n, ns, sig) ==
  LET c == ChildOf(n) IN
  IF ns = "CANCELLING" /\ sig = "CANCEL" /\ c # "none"
     /\ state[c] \notin (Terminal \cup {"CANCELLING", "IDLE"})
  THEN <<[node |-> c, sig |-> "CANCEL"]>>
  ELSE <<>>

Process ==
  /\ Len(queue) > 0
  /\ LET m   == Head(queue)
         n   == m.node
         sig == m.sig
         \* R' reopen DISABLED here as at N=2 (consumed=TRUE) — named scope choice; the reopen
         \* edge's liveness is checked at N=1 (FsmSpike), the graph gate is code-tested.
         ns  == Step(state[n], sig, iter[n], MaxReopens, TRUE)
     IN IF ns = "REJECT"
        THEN /\ queue' = Tail(queue)
             /\ UNCHANGED <<state, iter>>
        ELSE /\ state' = [state EXCEPT ![n] = ns]
             /\ iter' = IF state[n] = "VALIDATING" /\ sig = "FAIL" /\ iter[n] < MaxIterations
                          THEN [iter EXCEPT ![n] = @ + 1] ELSE iter
             /\ queue' = Tail(queue) \o CascadeFor(n, ns, sig)
  /\ UNCHANGED <<mark, overdue, crashesLeft>>

ActorSend(n, sig) ==
  /\ Len(queue) < QueueCap - 2
  /\ queue' = Append(queue, [node |-> n, sig |-> sig])
  /\ UNCHANGED <<state, iter, mark, overdue, crashesLeft>>

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
  \/ \E n \in Nodes, sig \in ActorSigs : ActorSend(n, sig)

Spec ==
  /\ Init
  /\ [][Next]_vars
  /\ WF_vars(Process)
  /\ \A n \in Nodes : WF_vars(MonitorFire(n)) /\ WF_vars(BecomeOverdue(n))

----------------------------------------------------------------------------
Termination == <>[](\A n \in Nodes : state[n] \in (Terminal \cup {"IDLE"}))

TerminalAbsorbing ==
  \A n \in Nodes, t \in Terminal : []((state[n] = t) => [](state[n] = t))

============================================================================
