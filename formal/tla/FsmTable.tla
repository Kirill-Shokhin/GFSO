---------------------------- MODULE FsmTable ----------------------------
(* THE shared transition table — the single TLA+ image of
   gfso/core/protocol/fsm.py::transition (verbatim rows, the iteration guard,
   the universal-CANCEL catch-all, revision §6.4 Inv-1, and the R′ REOPEN edge
   §6.3 with its double gate). Every model in this directory EXTENDS this
   module; the table exists in exactly one place. *)

EXTENDS Naturals, Sequences

CONSTANTS MaxIterations, MaxReopens

States == {"IDLE", "REVIEW", "CHALLENGED", "EXECUTING", "BLOCKED", "VALIDATING",
           "REWORK", "CANCELLING", "TIMEOUT", "DONE", "CANCELLED", "ESCALATED"}
Terminal == {"DONE", "CANCELLED", "ESCALATED"}                      \* enums.py TERMINAL_STATES
Reassignable == {"REVIEW", "CHALLENGED", "EXECUTING", "BLOCKED",    \* enums.py REASSIGNABLE_STATES
                 "VALIDATING", "REWORK"}
QuasiTerminal == {"DONE", "CANCELLED"}                              \* enums.py QUASI_TERMINAL_STATES (R', §6.3)

P2P == {"ASSIGN", "ACCEPT", "CHALLENGE", "ACCEPT_CHALLENGE", "REJECT_CHALLENGE",
        "DELIVER", "BLOCK", "RESOLVE_BLOCK", "PASS", "FAIL", "CANCEL", "CANCEL_ACK"}
Sigs == P2P \cup {"TIMEOUT"}                                        \* TIMEOUT is systemic, not P2P (§6.2)

(* fsm.py `transition`; "REJECT" = table lookup miss → engine audit-rejects. `it` =
   the graph-side iteration counter (GuardContext); `ro` = the sign-agnostic reopen
   counter and `consumed` = the finality-gate verdict (GuardContext, computed by the
   graph at the chokepoint in the same atomic step — Инв-7, no TOCTOU). *)
Step(s, sig, it, ro, consumed) ==
  CASE s = "IDLE"       /\ sig = "ASSIGN"           -> "REVIEW"
    [] s = "IDLE"       /\ sig = "TIMEOUT"          -> "TIMEOUT"    \* DECLARED DIVERGENCE: v4.0 Inv-5 exempts IDLE (§14.4) — row scheduled for removal
    [] s = "REVIEW"     /\ sig = "ACCEPT"           -> "EXECUTING"
    [] s = "REVIEW"     /\ sig = "CHALLENGE"        -> "CHALLENGED"
    [] s = "REVIEW"     /\ sig = "TIMEOUT"          -> "TIMEOUT"
    [] s = "CHALLENGED" /\ sig = "ACCEPT_CHALLENGE" -> "REVIEW"
    [] s = "CHALLENGED" /\ sig = "REJECT_CHALLENGE" -> "EXECUTING"
    [] s = "CHALLENGED" /\ sig = "TIMEOUT"          -> "TIMEOUT"
    [] s = "EXECUTING"  /\ sig = "DELIVER"          -> "VALIDATING"
    [] s = "EXECUTING"  /\ sig = "BLOCK"            -> "BLOCKED"
    [] s = "EXECUTING"  /\ sig = "TIMEOUT"          -> "TIMEOUT"
    [] s = "BLOCKED"    /\ sig = "RESOLVE_BLOCK"    -> "EXECUTING"
    [] s = "BLOCKED"    /\ sig = "TIMEOUT"          -> "ESCALATED"   \* block IS the escalation
    [] s = "VALIDATING" /\ sig = "PASS"             -> "DONE"
    [] s = "VALIDATING" /\ sig = "FAIL"             -> IF it < MaxIterations
                                                       THEN "REWORK" ELSE "DONE"  \* DONE(fail)
    [] s = "VALIDATING" /\ sig = "TIMEOUT"          -> "DONE"        \* DONE(auto_pass), §16.7
    [] s = "REWORK"     /\ sig = "DELIVER"          -> "VALIDATING"
    [] s = "REWORK"     /\ sig = "BLOCK"            -> "BLOCKED"
    [] s = "REWORK"     /\ sig = "TIMEOUT"          -> "TIMEOUT"
    [] s = "TIMEOUT"    /\ sig = "TIMEOUT"          -> "ESCALATED"   \* repeated timeout
    [] s = "CANCELLING" /\ sig = "CANCEL_ACK"       -> "CANCELLED"
    [] s = "CANCELLING" /\ sig = "TIMEOUT"          -> "CANCELLED"   \* cancellation authoritative
    [] s \notin Terminal /\ s # "CANCELLING"
                        /\ sig = "CANCEL"           -> "CANCELLING"  \* universal catch-all (§6.3)
    [] s \in Reassignable /\ sig = "ASSIGN"         -> "REVIEW"      \* revision, same id (§6.4 Inv-1)
    [] s \in QuasiTerminal /\ sig = "ASSIGN"
                          /\ ~consumed
                          /\ ro < MaxReopens        -> "REVIEW"      \* R' REOPEN (§6.3): finality-gate ∧ counter
    [] OTHER                                        -> "REJECT"

============================================================================
