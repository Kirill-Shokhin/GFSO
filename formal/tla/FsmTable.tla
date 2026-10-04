---------------------------- MODULE FsmTable ----------------------------
(* THE shared transition table — the single TLA+ image of
   gfso/core/protocol/fsm.py::transition (verbatim rows, the iteration guard,
   the universal-CANCEL catch-all, revision §12.3 Inv-1, and the R′ REOPEN edge
   §12.14 with its double gate). Every model in this directory EXTENDS this
   module; the table exists in exactly one place.

   v4.1 — the table the engine carries, cell for cell (fsm.py read 2026-09-25;
   the same cells `formal/GFSO/Fsm.lean` names in its header):
     * (OFFERED | CHALLENGED | EXECUTING | REWORKING, TIMEOUT) -> ESCALATED —
       a missed bound hands the decision over at once; OVERDUE is no state here
       (not in States, not in IssuerOwned, no row) and none in the engine;
     * (CHALLENGED, REJECT_CHALLENGE) -> OFFERED when the executor has NOT consented
       to the current packet version, EXECUTING when he has. The consent datum is
       Step's `cons` argument; each model carries it per node (FsmCascade3 passes
       FALSE: its reduced alphabet has no CHALLENGE, so the cell is never reached);
     * (EXECUTING|REWORKING, CHALLENGE) -> CHALLENGED and (VALIDATING, TIMEOUT) ->
       ESCALATED;
     * Reassignable: every non-terminal except IDLE and CANCELLING.
   `tests/test_model_conformance.py` parses this table and compares it with fsm.py
   on every cell, both sides of every guard. *)

EXTENDS Naturals, Sequences

CONSTANTS MaxIterations, MaxReopens

States == {"IDLE", "OFFERED", "CHALLENGED", "EXECUTING", "BLOCKED", "VALIDATING",
           "REWORKING", "CANCELLING", "DONE", "ABANDONED", "ESCALATED"}   \* the canon's eleven (v4.1)
Terminal == {"DONE", "ABANDONED"}                                   \* enums.py TERMINAL_STATES
\* ESCALATED is NOT here: terminal means the work is over (accepted / refused by authority),
\* and ESCALATED is the ISSUER's waiting state — the mirror of OFFERED under Inv-4 (§12.5, §12.9).
Reassignable == {"OFFERED", "CHALLENGED", "EXECUTING", "BLOCKED",    \* enums.py REASSIGNABLE_STATES
                 "VALIDATING", "REWORKING", "ESCALATED"}            \* …the issuer's revision IS his move
QuasiTerminal == {"DONE", "ABANDONED"}                              \* enums.py QUASI_TERMINAL_STATES (R', §12.14)

P2P == {"ASSIGN", "ACCEPT", "CHALLENGE", "ACCEPT_CHALLENGE", "REJECT_CHALLENGE",
        "DELIVER", "BLOCK", "RESOLVE_BLOCK", "PASS", "FAIL", "CANCEL", "CONFIRM_CANCEL"}
Sigs == P2P \cup {"TIMEOUT"}                                        \* TIMEOUT is systemic, not P2P (§12.2)

(* Inv-8 (Obligation-Ownership, v4.1): the party who owes each live state's next move,
   and who sends each signal (§12.13, §11.2). IDLE and the terminals have no owner; the timeout
   is nobody's move. *)
ExecutorOwned == {"OFFERED", "EXECUTING", "REWORKING", "CANCELLING"}
IssuerOwned   == {"CHALLENGED", "BLOCKED", "VALIDATING", "ESCALATED"}
ExecutorSigs  == {"ACCEPT", "CHALLENGE", "BLOCK", "DELIVER", "CONFIRM_CANCEL"}
IssuerSigs    == {"ASSIGN", "ACCEPT_CHALLENGE", "REJECT_CHALLENGE", "PASS", "FAIL",
                  "CANCEL", "RESOLVE_BLOCK"}

(* A new packet version enters only through OFFERED and only by the issuer's act: a
   re-ASSIGN (the first ASSIGN, a revision, a REOPEN) or an ACCEPT_CHALLENGE (a new spec).
   Every accepted signal into OFFERED is one of the two, and the only accepted self-loop
   in the table is OFFERED's re-ASSIGN — which is why the models can read "no signal was
   processed" off (state, packet-version parity) alone. *)
NewVersion(sig) == sig \in {"ASSIGN", "ACCEPT_CHALLENGE"}

(* Consent (v4.1): whether an ACCEPT is logged on the CURRENT packet version — set by an
   accepted ACCEPT, cleared by every new version, untouched otherwise (a rejected signal
   changes nothing). It is what REJECT_CHALLENGE reads. *)
ConsentNext(cons, sig, ns) ==
  IF ns = "REJECT" THEN cons
  ELSE IF NewVersion(sig) THEN FALSE
  ELSE IF sig = "ACCEPT" THEN TRUE
  ELSE cons

(* Issuing a child (§12.7): the FIRST ASSIGN of a child node (IDLE → OFFERED) is refused while
   the parent is CANCELLING or terminal — a child issued after the cascade fired would escape
   it. Moves on children already issued stay admissible in every parent state. Not a table
   row — the table is per node; each model applies it with its own parent relation. *)
IssuingBarred == Terminal \cup {"CANCELLING"}
FirstIssue(s, sig) == s = "IDLE" /\ sig = "ASSIGN"

(* fsm.py `transition`; "REJECT" = table lookup miss → engine audit-rejects. `it` =
   the graph-side iteration counter (GuardContext); `ro` = the sign-agnostic reopen
   counter and `consumed` = the finality-gate verdict (GuardContext, computed by the
   graph at the chokepoint in the same atomic step — Inv-7, no TOCTOU); `cons` = consent
   logged on the current packet version (read by REJECT_CHALLENGE only). *)
Step(s, sig, it, ro, consumed, cons) ==
  CASE s = "IDLE"       /\ sig = "ASSIGN"           -> "OFFERED"
    \* No (IDLE, TIMEOUT) row: Inv-5 exempts IDLE by name (§12.12) — the pre-contract state
    \* carries no clock, and its starvation surfaces as the PARENT's timeout. A crash orphan is
    \* recovered by finishing the interrupted ASSIGN (Engine._recover_orphans), not by this edge.
    [] s = "OFFERED"     /\ sig = "ACCEPT"           -> "EXECUTING"
    [] s = "OFFERED"     /\ sig = "CHALLENGE"        -> "CHALLENGED"
    [] s = "OFFERED"     /\ sig = "TIMEOUT"          -> "ESCALATED"   \* v4.1: hands over at once
    [] s = "CHALLENGED" /\ sig = "ACCEPT_CHALLENGE" -> "OFFERED"
    [] s = "CHALLENGED" /\ sig = "REJECT_CHALLENGE" -> IF cons THEN "EXECUTING" ELSE "OFFERED"
                                                       \* v4.1: the wait the challenge interrupted
    [] s = "CHALLENGED" /\ sig = "TIMEOUT"          -> "ESCALATED"   \* v4.1
    [] s = "EXECUTING"  /\ sig = "DELIVER"          -> "VALIDATING"
    [] s = "EXECUTING"  /\ sig = "BLOCK"            -> "BLOCKED"
    [] s = "EXECUTING"  /\ sig = "CHALLENGE"        -> "CHALLENGED"  \* v4.1 C-1: a dispute after consent
    [] s = "EXECUTING"  /\ sig = "TIMEOUT"          -> "ESCALATED"   \* v4.1
    [] s = "BLOCKED"    /\ sig = "RESOLVE_BLOCK"    -> "EXECUTING"
    [] s = "BLOCKED"    /\ sig = "TIMEOUT"          -> "ESCALATED"   \* block IS the escalation
    [] s = "VALIDATING" /\ sig = "PASS"             -> "DONE"
    [] s = "VALIDATING" /\ sig = "FAIL"             -> IF it < MaxIterations
                                                       THEN "REWORKING" ELSE "ESCALATED"
                                                       \* exhausted rework escalates (§12.5); the
                                                       \* canon has no "V = fail, settled" terminal
    [] s = "VALIDATING" /\ sig = "TIMEOUT"          -> "ESCALATED"   \* back to the issuer,
                                                       \* no verdict invented
    [] s = "REWORKING"     /\ sig = "DELIVER"          -> "VALIDATING"
    [] s = "REWORKING"     /\ sig = "BLOCK"            -> "BLOCKED"
    [] s = "REWORKING"     /\ sig = "CHALLENGE"        -> "CHALLENGED"  \* v4.1 C-1
    [] s = "REWORKING"     /\ sig = "TIMEOUT"          -> "ESCALATED"   \* v4.1
    [] s = "ESCALATED"  /\ sig = "TIMEOUT"          -> "CANCELLING"  \* the issuer's silence CLOSES
                                                       \* (§12.5): V=⊥, never a pass
    [] s = "CANCELLING" /\ sig = "CONFIRM_CANCEL"       -> "ABANDONED"
    [] s = "CANCELLING" /\ sig = "TIMEOUT"          -> "ABANDONED"   \* cancellation authoritative
    [] s \notin Terminal /\ s # "CANCELLING"
                        /\ sig = "CANCEL"           -> "CANCELLING"  \* universal catch-all (§12.6)
    [] s \in Reassignable /\ sig = "ASSIGN"         -> "OFFERED"      \* revision, same id (§12.3 Inv-1)
    [] s \in QuasiTerminal /\ sig = "ASSIGN"
                          /\ ~consumed
                          /\ ro < MaxReopens        -> "OFFERED"      \* R' REOPEN (§12.14): finality-gate ∧ counter
    [] OTHER                                        -> "REJECT"

(* Inv-8 on the table: in every owned state, the owner has an admissible move of his own
   at every value of the retry guard. A state-only fact, checked as an invariant by each
   model over the states it actually reaches. *)
OwnerHasMove(s, it, ro, consumed, cons) ==
  /\ s \in IssuerOwned   => \E g \in IssuerSigs   : Step(s, g, it, ro, consumed, cons) # "REJECT"
  /\ s \in ExecutorOwned => \E g \in ExecutorSigs : Step(s, g, it, ro, consumed, cons) # "REJECT"

============================================================================
