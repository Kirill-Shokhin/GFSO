---------------------------- MODULE FsmCascade3 ----------------------------
(* Cascade TRANSITIVITY (2.1 remainder): a depth-2 chain root → mid → leaf.
   The cascade rule is the same at every level (ENTERING CANCELLING — by CANCEL or by
   ESCALATED's timeout — enqueues CANCEL per live child; loop.py `_execute_effects`);
   this instance checks that it composes THROUGH an intermediate node, interleaved with
   the monitor and a crash at any point (a queued cascade-CANCEL can die with the queue —
   the monitor must still move the orphaned descendants).

   Per node, as in FsmSpike/FsmSystem: `overdue` and `iter` belong to the current packet
   version and reset on every new one; the monitor dedups per visit; `pv` is the
   packet-version parity history variable.

   The actor alphabet is REDUCED to the cascade-relevant core (named modeling
   choice, keeps the space tractable): full hostility over the complete alphabet is
   checked at N=1 (FsmSpike) and N=2 (FsmSystem); this run isolates depth.
   CONSENT (v4.1) is not carried: without CHALLENGE no node reaches CHALLENGED, so the
   one cell that reads it (REJECT_CHALLENGE) is never processed; Step gets FALSE. *)

EXTENDS FsmTable

CONSTANTS QueueCap, MaxCrashes

Nodes == {"root", "mid", "leaf"}
ChildOf(n) == IF n = "root" THEN "mid" ELSE IF n = "mid" THEN "leaf" ELSE "none"
Parent(n) == IF n = "leaf" THEN "mid" ELSE IF n = "mid" THEN "root" ELSE "none"

(* Cancel/cascade core only: DELIVER/PASS branches are exercised at N=1/N=2 with the
   full alphabet; here they only multiply the liveness graph (a full-alphabet attempt
   OOM'd on 13.5M states × 10 temporal branches). *)
ActorSigs == {"ASSIGN", "ACCEPT", "CANCEL", "CONFIRM_CANCEL"}

Msg == [node: Nodes, sig: Sigs]

VARIABLES state, iter, queue, mark, overdue, crashesLeft, pv

vars == <<state, iter, queue, mark, overdue, crashesLeft, pv>>

TypeOK ==
  /\ state \in [Nodes -> States]
  /\ iter \in [Nodes -> 0..MaxIterations]
  /\ queue \in Seq(Msg)
  /\ Len(queue) <= QueueCap + 3   \* actors ≤ QueueCap-2 (3 initial ASSIGNs), + ≤ 1 pending TIMEOUT per node
  /\ mark \in [Nodes -> States \cup {"NONE"}]
  /\ overdue \in [Nodes -> BOOLEAN]
  /\ crashesLeft \in 0..MaxCrashes
  /\ pv \in [Nodes -> BOOLEAN]

Init ==
  /\ state = [n \in Nodes |-> "IDLE"]
  /\ iter = [n \in Nodes |-> 0]
  /\ queue = <<[node |-> "root", sig |-> "ASSIGN"], [node |-> "mid", sig |-> "ASSIGN"],
               [node |-> "leaf", sig |-> "ASSIGN"]>>
  /\ mark = [n \in Nodes |-> "NONE"]
  /\ overdue = [n \in Nodes |-> FALSE]
  /\ crashesLeft = MaxCrashes
  /\ pv = [n \in Nodes |-> FALSE]

(* §12.7: a child's first ASSIGN is refused under a CANCELLING or terminal parent, applied at
   processing (the reason is in FsmSystem). *)
Admissible(n, sig) ==
  Parent(n) = "none" \/ ~FirstIssue(state[n], sig) \/ state[Parent(n)] \notin IssuingBarred

CascadeFor(n, ns) ==
  LET c == ChildOf(n) IN
  IF ns = "CANCELLING" /\ state[n] # "CANCELLING" /\ c # "none"
     /\ state[c] \notin (Terminal \cup {"CANCELLING", "IDLE"})
  THEN <<[node |-> c, sig |-> "CANCEL"]>>
  ELSE <<>>

Process ==
  /\ Len(queue) > 0
  /\ LET m   == Head(queue)
         n   == m.node
         sig == m.sig
         \* R' reopen DISABLED here as at N=2 (consumed=TRUE) — named scope choice; the reopen
         \* edge is checked at N=1 (FsmSpike), the graph gate is code-tested.
         ns  == IF Admissible(n, sig) THEN Step(state[n], sig, iter[n], MaxReopens, TRUE, FALSE)
                ELSE "REJECT"
         nv  == ns # "REJECT" /\ NewVersion(sig)
     IN IF ns = "REJECT"
        THEN /\ queue' = Tail(queue)
             /\ UNCHANGED <<state, iter, mark, overdue, pv>>
        ELSE /\ state' = [state EXCEPT ![n] = ns]
             /\ iter' = IF nv THEN [iter EXCEPT ![n] = 0]
                        ELSE IF state[n] = "VALIDATING" /\ sig = "FAIL" /\ iter[n] < MaxIterations
                          THEN [iter EXCEPT ![n] = @ + 1] ELSE iter
             /\ mark' = IF ns # state[n] \/ nv THEN [mark EXCEPT ![n] = "NONE"] ELSE mark
             /\ overdue' = IF nv THEN [overdue EXCEPT ![n] = FALSE] ELSE overdue
             /\ pv' = IF nv THEN [pv EXCEPT ![n] = ~@] ELSE pv
             /\ queue' = Tail(queue) \o CascadeFor(n, ns)
  /\ UNCHANGED crashesLeft

ActorSend(n, sig) ==
  /\ Len(queue) < QueueCap - 2
  /\ queue' = Append(queue, [node |-> n, sig |-> sig])
  /\ UNCHANGED <<state, iter, mark, overdue, crashesLeft, pv>>

(* Per-node queue guard (at most one pending TIMEOUT per node) — the shared slot cap starved
   a node's fire under WF once issuers can re-ASSIGN forever; the reason is in FsmSystem. *)
MonitorFire(n) ==
  /\ overdue[n]
  /\ state[n] \notin (Terminal \cup {"IDLE"})
  /\ mark[n] # state[n]
  /\ \A i \in 1..Len(queue) : queue[i] # [node |-> n, sig |-> "TIMEOUT"]
  /\ queue' = Append(queue, [node |-> n, sig |-> "TIMEOUT"])
  /\ mark' = [mark EXCEPT ![n] = state[n]]
  /\ UNCHANGED <<state, iter, overdue, crashesLeft, pv>>

BecomeOverdue(n) ==
  /\ ~overdue[n]
  /\ overdue' = [overdue EXCEPT ![n] = TRUE]
  /\ UNCHANGED <<state, iter, queue, mark, crashesLeft, pv>>

Crash ==
  /\ crashesLeft > 0
  /\ crashesLeft' = crashesLeft - 1
  /\ queue' = <<>>
  /\ mark' = [n \in Nodes |-> "NONE"]
  /\ UNCHANGED <<state, iter, overdue, pv>>

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
Live == States \ (Terminal \cup {"IDLE"})

WaitsEnd ==
  \A n \in Nodes, s \in Live, b \in BOOLEAN : []<>(state[n] # s \/ pv[n] # b)

NoOwnerlessDivergence ==
  \A n \in Nodes :
    \/ <>[](state[n] \in Terminal \cup {"IDLE"})
    \/ ([]<>(pv[n] = TRUE) /\ []<>(pv[n] = FALSE))

TerminalAbsorbing ==
  \A n \in Nodes, t \in Terminal : []((state[n] = t) => [](state[n] = t))

OwnerHasMoveInv == \A n \in Nodes : OwnerHasMove(state[n], iter[n], MaxReopens, TRUE, FALSE)

(* No Del identities here either (see FsmSystem): "the issuer is Del(parent)" is not checked.
   REACHABILITY PROBE — expected VIOLATED: a leaf waiting on its issuer while mid is
   settled, escalated or cancelling. *)
ProbeSettledParentWaitingChild ==
  ~(state["mid"] \in {"DONE", "ABANDONED", "ESCALATED", "CANCELLING"}
    /\ state["leaf"] \in IssuerOwned)

(* §12.7 issuing children (see FsmSystem): the action property and its probe, expected VIOLATED. *)
ChildIssuedOnlyUnderLiveParent ==
  [][\A n \in Nodes : (Parent(n) # "none" /\ state[n] = "IDLE" /\ state'[n] = "OFFERED")
                      => state[Parent(n)] \notin IssuingBarred]_vars

ProbeIssueUnderClosedParent ==
  ~(\E n \in Nodes : Parent(n) # "none" /\ Len(queue) > 0
       /\ Head(queue) = [node |-> n, sig |-> "ASSIGN"] /\ state[n] = "IDLE"
       /\ state[Parent(n)] \in IssuingBarred)

============================================================================
