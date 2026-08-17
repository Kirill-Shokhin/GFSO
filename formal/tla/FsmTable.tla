---------------------------- MODULE FsmTable ----------------------------
(* THE shared transition table — the single TLA+ image of
   gfso/core/protocol/fsm.py::transition (verbatim rows, the iteration guard,
   the universal-CANCEL catch-all, revision §6.4 Inv-1, and the R′ REOPEN edge
   §6.3 with its double gate). Every model in this directory EXTENDS this
   module; the table exists in exactly one place. *)

EXTENDS Naturals, Sequences

CONSTANTS MaxIterations, MaxReopens

States == {"IDLE", "OFFERED", "CHALLENGED", "EXECUTING", "BLOCKED", "VALIDATING",
           "REWORKING", "CANCELLING", "OVERDUE", "DONE", "ABANDONED", "ESCALATED"}
Terminal == {"DONE", "ABANDONED", "ESCALATED"}                      \* enums.py TERMINAL_STATES
Reassignable == {"OFFERED", "CHALLENGED", "EXECUTING", "BLOCKED",    \* enums.py REASSIGNABLE_STATES
                 "VALIDATING", "REWORKING"}
QuasiTerminal == {"DONE", "ABANDONED"}                              \* enums.py QUASI_TERMINAL_STATES (R', §6.3)

P2P == {"ASSIGN", "ACCEPT", "CHALLENGE", "ACCEPT_CHALLENGE", "REJECT_CHALLENGE",
        "DELIVER", "BLOCK", "RESOLVE_BLOCK", "PASS", "FAIL", "CANCEL", "CONFIRM_CANCEL"}
Sigs == P2P \cup {"TIMEOUT"}                                        \* TIMEOUT is systemic, not P2P (§6.2)

(* fsm.py `transition`; "REJECT" = table lookup miss → engine audit-rejects. `it` =
   the graph-side iteration counter (GuardContext); `ro` = the sign-agnostic reopen
   counter and `consumed` = the finality-gate verdict (GuardContext, computed by the
   graph at the chokepoint in the same atomic step — Инв-7, no TOCTOU). *)
Step(s, sig, it, ro, consumed) ==
  CASE s = "IDLE"       /\ sig = "ASSIGN"           -> "OFFERED"
    \* No (IDLE, TIMEOUT) row: v4.0 Inv-5 exempts IDLE by name (§14.4) — the pre-contract state
    \* carries no clock, and its starvation surfaces as the PARENT's timeout. A crash orphan is
    \* recovered by finishing the interrupted ASSIGN (Engine._recover_orphans), not by this edge.
    [] s = "OFFERED"     /\ sig = "ACCEPT"           -> "EXECUTING"
    [] s = "OFFERED"     /\ sig = "CHALLENGE"        -> "CHALLENGED"
    [] s = "OFFERED"     /\ sig = "TIMEOUT"          -> "OVERDUE"
    [] s = "CHALLENGED" /\ sig = "ACCEPT_CHALLENGE" -> "OFFERED"
    [] s = "CHALLENGED" /\ sig = "REJECT_CHALLENGE" -> "EXECUTING"
    [] s = "CHALLENGED" /\ sig = "TIMEOUT"          -> "OVERDUE"
    [] s = "EXECUTING"  /\ sig = "DELIVER"          -> "VALIDATING"
    [] s = "EXECUTING"  /\ sig = "BLOCK"            -> "BLOCKED"
    [] s = "EXECUTING"  /\ sig = "TIMEOUT"          -> "OVERDUE"
    [] s = "BLOCKED"    /\ sig = "RESOLVE_BLOCK"    -> "EXECUTING"
    [] s = "BLOCKED"    /\ sig = "TIMEOUT"          -> "ESCALATED"   \* block IS the escalation
    [] s = "VALIDATING" /\ sig = "PASS"             -> "DONE"
    [] s = "VALIDATING" /\ sig = "FAIL"             -> IF it < MaxIterations
                                                       THEN "REWORKING" ELSE "ESCALATED"
                                                       \* exhausted rework escalates (§14.3); the
                                                       \* canon has no "V = fail, settled" terminal
    [] s = "VALIDATING" /\ sig = "TIMEOUT"          -> "DONE"        \* DONE(auto_pass), §16.7
    [] s = "REWORKING"     /\ sig = "DELIVER"          -> "VALIDATING"
    [] s = "REWORKING"     /\ sig = "BLOCK"            -> "BLOCKED"
    [] s = "REWORKING"     /\ sig = "TIMEOUT"          -> "OVERDUE"
    [] s = "OVERDUE"    /\ sig = "TIMEOUT"          -> "ESCALATED"   \* repeated timeout
    [] s = "CANCELLING" /\ sig = "CONFIRM_CANCEL"       -> "ABANDONED"
    [] s = "CANCELLING" /\ sig = "TIMEOUT"          -> "ABANDONED"   \* cancellation authoritative
    [] s \notin Terminal /\ s # "CANCELLING"
                        /\ sig = "CANCEL"           -> "CANCELLING"  \* universal catch-all (§6.3)
    [] s \in Reassignable /\ sig = "ASSIGN"         -> "OFFERED"      \* revision, same id (§6.4 Inv-1)
    [] s \in QuasiTerminal /\ sig = "ASSIGN"
                          /\ ~consumed
                          /\ ro < MaxReopens        -> "OFFERED"      \* R' REOPEN (§6.3): finality-gate ∧ counter
    [] OTHER                                        -> "REJECT"

============================================================================
