/-
  GFSO — the canon's table of the protocol machine (§12.4), the base machine. `Fsm.lean` is the
  engine's conformance mirror, so claims about the canon live here; `mirror_agrees_with_canon` ties the
  two tables cell for cell, so a change to either side breaks a proof.

  SCOPE. R′ (§12.14) is excluded: "R′'s gate reads consumption, a log fact, not a state-resident datum,
  so no finite composite of states and counters is a deterministic automaton on it" (§12.14).
  The states are §12.1's eleven (`canonSt`). The constructor `St.OVERDUE` survives only for the frozen
  table of `Forcing.lean` and the lapse record's image in `LogLanguageAgrees`: here its row is empty,
  its owner `none`, no cell enters it, and canon-side statements quantify over `canonSt`.

  BIT ABSTRACTION. The table's Bool input `b` is the retry guard at FAIL (rounds left under `max_iterations`)
  and the consent datum at REJECT_CHALLENGE (§13.1), ignored elsewhere. Every statement below explores both values of `b` in
  every state, so a fact that needs the log (that `b = true` at REJECT_CHALLENGE presupposes an ACCEPT)
  is not visible here: it is `LogLanguage.lean`'s, which forces the table over the log and proves it
  agrees with this one (`LogLanguage.agrees_with_the_canon`). v4.0's auto_pass cell survives as §13.2's
  witness (`variantStep`). Inv-8 is checked below (`owner`, `inv8_canon`).
-/
import GFSO.Fsm

namespace GFSO.FsmCanon
open GFSO.Fsm GFSO.Fsm.St GFSO.Fsm.Sig

/-- The canon's eleven states: `allSt` without OVERDUE. -/
def canonSt : List St := allSt.filter (fun s => s != OVERDUE)

theorem canonSt_eleven : canonSt.length = 11 ∧ canonSt.contains OVERDUE = false := by decide

/-- The canon's transition table (§12.4, base machine). `b`: at FAIL, rounds remain; at
    REJECT_CHALLENGE, consent (an ACCEPT) is logged on the current packet version; ignored
    elsewhere. -/
def canonStep (s : St) (sig : Sig) (b : Bool) : Option St :=
  match s with
  | IDLE => match sig with
    | ASSIGN => some OFFERED
    | CANCEL => some CANCELLING
    | _ => none
  | OFFERED => match sig with
    | ACCEPT => some EXECUTING
    | CHALLENGE => some CHALLENGED
    | Sig.TIMEOUT => some ESCALATED
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | CHALLENGED => match sig with
    | ACCEPT_CHALLENGE => some OFFERED
    | REJECT_CHALLENGE => some (if b then EXECUTING else OFFERED)   -- the interrupted wait (§12.4)
    | Sig.TIMEOUT => some ESCALATED
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | EXECUTING => match sig with
    | DELIVER => some VALIDATING
    | BLOCK => some BLOCKED
    | CHALLENGE => some CHALLENGED     -- C-1, the post-consent CHALLENGE (§13.3)
    | Sig.TIMEOUT => some ESCALATED
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | BLOCKED => match sig with
    | RESOLVE_BLOCK => some EXECUTING
    | Sig.TIMEOUT => some ESCALATED
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | VALIDATING => match sig with
    | PASS => some DONE
    | FAIL => some (if b then REWORKING else ESCALATED)   -- `docs/architecture.md` corner #3
    | Sig.TIMEOUT => some ESCALATED
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | REWORKING => match sig with
    | DELIVER => some VALIDATING
    | BLOCK => some BLOCKED        -- §12.4's rule: REWORKING carries BLOCK and CHALLENGE
    | CHALLENGE => some CHALLENGED -- as EXECUTING does
    | Sig.TIMEOUT => some ESCALATED
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | CANCELLING => match sig with
    | CONFIRM_CANCEL => some ABANDONED
    | Sig.TIMEOUT => some ABANDONED
    | _ => none
  | OVERDUE => none                  -- no canon state
  | DONE => none
  | ABANDONED => none
  -- The issuer's decision (§12.5), held by Inv-4's reading, clause (2) (§12.9).
  | ESCALATED => match sig with
    | ASSIGN => some OFFERED
    | CANCEL => some CANCELLING
    | Sig.TIMEOUT => some CANCELLING     -- silence takes the closing's path (§12.5)
    | _ => none

/-- The settlement mode, the observable's second part (§12.11): DONE ↦ pass, ABANDONED ↦ abandoned,
    every non-terminal `live` — ESCALATED included (§12.5). Which route closed an ABANDONED (CANCEL or
    the issuer's silence), like whether EXECUTING was entered through a FAIL, is log data the state does
    not carry (Inv-7, §12.11). -/
inductive Settle | pass | abandoned | live
deriving DecidableEq, Repr

def settle : St → Settle
  | DONE => Settle.pass | ABANDONED => Settle.abandoned
  | _ => Settle.live

/-! ### The v4.1 cells -/

/-- OVERDUE's row is empty, and no cell at either value of `b` enters it (§12.12). -/
theorem canon_never_enters_overdue :
    (allSt.all (fun s => allSig.all (fun g => [false, true].all (fun b =>
      canonStep s g b != some OVERDUE)))) = true
    ∧ (allSig.all (fun g => [false, true].all (fun b => (canonStep OVERDUE g b).isNone))) = true := by
  decide

/-- §12.4's timeout rule for the party waits: every canon non-terminal but IDLE, ESCALATED and
    CANCELLING times out to ESCALATED. -/
theorem canon_first_timeouts_hand_over :
    (canonSt.all (fun s => isTerminal s || (s == IDLE) || (s == ESCALATED) || (s == CANCELLING)
      || (canonStep s Sig.TIMEOUT false == some ESCALATED))) = true := by
  decide

/-- §12.4's REJECT_CHALLENGE rule at both values of the consent bit. -/
theorem canon_reject_returns_to_the_wait :
    canonStep CHALLENGED REJECT_CHALLENGE false = some OFFERED
    ∧ canonStep CHALLENGED REJECT_CHALLENGE true = some EXECUTING := by
  decide

/-! ### The behavioural quotient (§12.11) -/

/-- EXECUTING and REWORKING agree on every signal at both values of `b`: one behaviour class,
    REWORKING an attribution label (§12.11). -/
theorem canon_exec_rework_same :
    (allSig.all (fun g => [false, true].all (fun b =>
      canonStep EXECUTING g b == canonStep REWORKING g b))) = true := by
  decide

/-- The other canon non-terminals are pairwise separated by their rows alone. -/
theorem canon_others_pairwise_distinct :
    (canonSt.all (fun s => canonSt.all (fun t =>
      (s == t) || isTerminal s || isTerminal t
      || ((s == EXECUTING) && (t == REWORKING)) || ((s == REWORKING) && (t == EXECUTING))
      || !(allSig.all (fun g => [false, true].all (fun b =>
             canonStep s g b == canonStep t g b)))))) = true := by
  decide

/-- The two terminals share the empty row; only the settlement mode separates them
    (`canon_settlement_separates_terminals`), so the observable must carry it. -/
theorem canon_terminals_share_rows :
    (canonSt.all (fun s => canonSt.all (fun t =>
      !(isTerminal s && isTerminal t) ||
      allSig.all (fun g => [false, true].all (fun b => canonStep s g b == canonStep t g b))))) = true := by
  decide

theorem canon_settlement_separates_terminals :
    (canonSt.all (fun s => canonSt.all (fun t =>
      (s == t) || !(isTerminal s && isTerminal t) || (settle s != settle t)))) = true := by
  decide

/-- The joint observable (settlement mode ⊕ row) separates every pair of canon states other than
    REWORKING in one check: non-terminal pairs by row, terminal pairs by settlement, cross pairs by both.
    With `canon_exec_rework_same`: eleven states, ten behaviour classes, under the bit abstraction; over
    the log CHALLENGED splits by consent (§12.11). -/
theorem canon_ten_pairwise_distinct :
    (canonSt.all (fun s => canonSt.all (fun t =>
      (s == t) || (s == REWORKING) || (t == REWORKING)
      || (settle s != settle t)
      || !(allSig.all (fun g => [false, true].all (fun b =>
             canonStep s g b == canonStep t g b)))))) = true := by
  decide

/-- Inside the engine mirror EXECUTING and REWORKING agree too (the canon-vs-mirror identity is
    `mirror_agrees_with_canon`). -/
theorem engine_agrees_on_rework_row :
    (allSig.all (fun g => [false, true].all (fun b =>
      step EXECUTING g b == step REWORKING g b))) = true := by
  decide

/-- The two tables agree on every cell (state × signal × `b`), OVERDUE's included. The engine side is
    cross-checked by `tests/test_model_conformance.py`, not by Lean. -/
theorem mirror_agrees_with_canon :
    (allSt.all (fun s => allSig.all (fun g => [false, true].all (fun b =>
      step s g b == canonStep s g b)))) = true := by
  decide

/-- C-1: CHALLENGE from both work states into CHALLENGED. -/
theorem canon_challenge_after_consent :
    canonStep EXECUTING CHALLENGE false = some CHALLENGED
    ∧ canonStep REWORKING CHALLENGE false = some CHALLENGED
    ∧ canonStep REWORKING CHALLENGE true = some CHALLENGED := by
  decide

/-! ### Inv-8 (Obligation-Ownership), §12.13 — the per-state clause

`owner` is a per-state stipulation transcribing §12.13's owner table, not read off the transitions: at
ESCALATED the owner's moves are catch-alls, so a "whose exits are these" test would be vacuous there.
Decided: the stipulated owner has an admissible signal of his own in every state of the domain, at both
values of `b` — a move's existence, not its adequacy. The timeout has no sender, so it is never the
owner's move. The edge clause is not checked here; over the log it is `LogLanguage.pInv8Edges`. -/

/-- The two roles of the transaction (§10.1). -/
inductive Party | issuer | executor
deriving DecidableEq, Repr

/-- Who sends each signal (§11.2's two tables). The system timeout has no sender. -/
def sender : Sig → Option Party
  | ACCEPT | CHALLENGE | BLOCK | DELIVER | CONFIRM_CANCEL => some Party.executor
  | ASSIGN | ACCEPT_CHALLENGE | REJECT_CHALLENGE | PASS | FAIL | CANCEL | RESOLVE_BLOCK =>
      some Party.issuer
  | Sig.TIMEOUT => none

/-- §12.13's owner table. `none` exactly outside Inv-8's domain — IDLE and the two terminals — and at
    OVERDUE, which is no canon state. -/
def owner : St → Option Party
  | OFFERED | EXECUTING | REWORKING | CANCELLING => some Party.executor
  | CHALLENGED | BLOCKED | VALIDATING | ESCALATED => some Party.issuer
  | IDLE | DONE | ABANDONED | OVERDUE => none

/-- `p` holds an admissible move of his own in `s`, at EVERY value of `b` (the bit is state-resident
    data, not a choice of the party). -/
def hasMove (f : St → Sig → Bool → Option St) (s : St) (p : Party) : Bool :=
  [false, true].all (fun b => allSig.any (fun g => (sender g == some p) && (f s g b).isSome))

/-- Inv-8 over a given list of states. -/
def inv8On (f : St → Sig → Bool → Option St) (ss : List St) : Bool :=
  ss.all (fun s => match owner s with
    | none => true
    | some p => hasMove f s p)

/-- Inv-8 over the whole table — every canon state, reachable or not. -/
def inv8 (f : St → Sig → Bool → Option St) : Bool := inv8On f canonSt

/-- Over `canonSt` the owner is undefined exactly at IDLE and the two terminals. -/
theorem owner_domain :
    (canonSt.all (fun s => (owner s).isNone == ((s == IDLE) || isTerminal s))) = true
    ∧ owner OVERDUE = none := by
  decide

/-- **Inv-8's per-state clause holds of the canon's base machine.** -/
theorem inv8_canon : inv8 canonStep = true := by decide

/-- …and of the engine mirror. -/
theorem inv8_mirror : inv8 step = true := by decide

/-- NEGATIVE CONTROL — v4.0's terminal ESCALATED (§12.13): an empty row, whose owner has nothing to
    send. Inv-8 fails, and only there. -/
def v40EscalatedStep (s : St) (sig : Sig) (b : Bool) : Option St :=
  match s with
  | ESCALATED => none
  | _ => canonStep s sig b

theorem control_inv8_fails_on_empty_escalated :
    inv8 v40EscalatedStep = false
    ∧ inv8On v40EscalatedStep (canonSt.filter (fun s => s != ESCALATED)) = true := by
  decide

/-- NEGATIVE CONTROL — the row-comparison shape can come out `false`. -/
theorem control_exec_blocked_differ :
    (allSig.all (fun g => [false, true].all (fun b =>
      canonStep EXECUTING g b == canonStep BLOCKED g b))) = false := by
  decide

/-! ### §13.2: bare adequacy pins no destination — the auto_pass witness

`variantStep` is the canon table with v4.0's cell (VALIDATING, timeout) → DONE(auto_pass). Decided: it
has the canon's timeout exits and satisfies Inv-8, agrees with the canon off that cell, and is
observably distinct on it. -/

def variantStep (s : St) (sig : Sig) (b : Bool) : Option St :=
  match s, sig with
  | VALIDATING, Sig.TIMEOUT => some DONE           -- the sole edit: auto_pass, not escalate
  | _, _ => canonStep s sig b

/-- Both tables give every canon non-terminal but IDLE a timeout exit — Inv-5's first clause, stated of
    the mirror as `Fsm.timeout_defined`. -/
theorem variant_and_canon_both_timeout_defined :
    (canonSt.all (fun s => isTerminal s || (s == IDLE) ||
        ((canonStep s Sig.TIMEOUT false).isSome && (variantStep s Sig.TIMEOUT false).isSome))) = true := by
  decide

/-- They differ observably on that cell: a live wait in ESCALATED, its row non-empty, against a
    settled DONE. -/
theorem variant_differs_on_validating_timeout :
    canonStep VALIDATING Sig.TIMEOUT false = some ESCALATED
    ∧ variantStep VALIDATING Sig.TIMEOUT false = some DONE
    ∧ settle ESCALATED = Settle.live ∧ settle DONE = Settle.pass
    ∧ (canonStep ESCALATED ASSIGN false).isSome = true := by
  decide

/-- Both satisfy Inv-8: the free cell survives Inv-8's place in adequacy (§13.1). -/
theorem variant_and_canon_both_inv8 : inv8 canonStep = true ∧ inv8 variantStep = true := by
  decide

/-- Off that cell the variant is the canon: a one-cell perturbation. -/
theorem variant_agrees_off_validating_timeout :
    (allSt.all (fun s => allSig.all (fun g =>
      ((s == VALIDATING) && (g == Sig.TIMEOUT)) ||
      [false, true].all (fun b => canonStep s g b == variantStep s g b)))) = true := by
  decide

/-! ### §13.3: the backbone, and ESCALATED's fold

The rows force the backbone's roles, not distinct states (§13.3); the states, with the whole table, are
forced over the log (`LogLanguage.lean`). Decided here: OVERDUE is out of the table
(`canon_never_enters_overdue`) and REWORKING is the one label (`canon_ten_pairwise_distinct`).

`noEscalatedStep` routes every entry into ESCALATED to ABANDONED. It still gives every non-terminal state
but IDLE a timeout (`noEscalated_still_timeout_defined`) — a check a timeout self-loop would also pass,
so its deadlock-freedom is derived (§12.13), not decided — and satisfies Inv-8 over its reachable states
(`witnesses_satisfy_inv8`). What the fold removes, and why the state stays, is §12.13's and §13.3's:
Inv-4's reading, clause (2), the same ground as CANCELLING's. -/

def noEscalatedStep (s : St) (sig : Sig) (b : Bool) : Option St :=
  match canonStep s sig b with
  | some ESCALATED => some ABANDONED     -- fold the issuer's waiting state into the cancel terminal
  | other => other

theorem noEscalated_still_timeout_defined :
    (canonSt.all (fun s => isTerminal s || (s == IDLE) ||
        (noEscalatedStep s Sig.TIMEOUT false).isSome)) = true := by
  decide

theorem noEscalated_omits_escalated :
    (allSt.all (fun s => allSig.all (fun g =>
      [false, true].all (fun b => noEscalatedStep s g b != some ESCALATED)))) = true := by
  decide

/-- The canon reaches ESCALATED (the exhausted rework loop), so the fold removes a state the canon has. -/
theorem canon_reaches_escalated :
    canonStep VALIDATING FAIL false = some ESCALATED := by decide


/-! ### §13.3: a removed exit strands success — a canon-internal witness

Not checked: the distinctness of the backbone states over every adequate protocol — a universal over an
unbounded protocol class, outside `decide`. Checked: the weaker canon-internal necessary condition at
one point, DELIVER — without it DONE is unreachable from EXECUTING. Reachability does not give this
uniformly: the catch-alls (re-ASSIGN, the timeouts) leave paths around some exits (RESOLVE_BLOCK, ACCEPT). -/

def succsC (step : St → Sig → Bool → Option St) (s : St) : List St :=
  (allSig.filterMap (fun g => step s g false)) ++ (allSig.filterMap (fun g => step s g true))

def reachN (step : St → Sig → Bool → Option St) : Nat → List St → List St
  | 0, fr => fr
  | Nat.succ n, fr =>
      let nxt := (fr.flatMap (succsC step)).filter (fun t => !(fr.contains t))
      if nxt.isEmpty then fr else reachN step n (fr ++ nxt)

def reachesDONE (step : St → Sig → Bool → Option St) (s : St) : Bool :=
  (reachN step 12 [s]).contains DONE

/-- The canon table with EXECUTING's DELIVER exit removed. -/
def noDeliver (s : St) (g : Sig) (b : Bool) : Option St :=
  match s, g with | EXECUTING, DELIVER => none | _, _ => canonStep s g b

/-- DONE is reachable from EXECUTING in the canon and not without DELIVER: a necessary condition of
    DELIVER's being forced, not the forcedness over all protocols. -/
theorem canon_exec_reaches_done : reachesDONE canonStep EXECUTING = true := by decide
theorem nodeliver_strands_done : reachesDONE noDeliver EXECUTING = false := by decide

/-! ### §11.4's removal grades over the fixed alphabet

Each theorem below is a canon-internal necessary condition of a §11.4 grade — removing the edge degrades
the canon's own table — read under the bit abstraction. That every adequate protocol needs the edge
quantifies over an unbounded class of protocols and is not derived (§20.4, §20.7).
 • FATAL — cut the signal and its target is unreachable: ASSIGN, BLOCK, CHALLENGE, DELIVER
   (`nodeliver_strands_done`), PASS (`noPass_strands_done`). ACCEPT, fatal in §11.4, is on this table only the sole content edge
   into consent: the table admits REJECT_CHALLENGE at `b = true` into EXECUTING, and that `b = true`
   presupposes a logged ACCEPT is visible only over the log (`LogLanguage.accept_fatal`).
 • SOLE-PROVIDER — the target still reached through a catch-all; decided is which content edges carry
   the source to the target: CANCEL, CONFIRM_CANCEL, RESOLVE_BLOCK, REJECT_CHALLENGE, ACCEPT_CHALLENGE
   (`acceptChallenge_sole_content_reoffer`). FAIL's grade is derived in the canon and witnessed by no
   theorem here.
 • INVARIANT-FORCED, orthogonal to strength — the removal leaves a reachable state whose owner has no
   move: CONFIRM_CANCEL alone (`inv8_forces_exactly`).
The kinds (a)–(c) below group the witnesses by what they show, orthogonally to these tiers. Destinations
(§13.2): re-ASSIGN's and ACCEPT_CHALLENGE's are fixed by §12.4's third rule; RESOLVE_BLOCK's,
REJECT_CHALLENGE's and FAIL's are free under bare adequacy and forced over the log (§13.4). -/

def dropEdge (f : St → Sig → Bool → Option St) (s0 : St) (sig0 : Sig) :
    St → Sig → Bool → Option St :=
  fun s sig b => if (s == s0) && (sig == sig0) then none else f s sig b

def dropSig (f : St → Sig → Bool → Option St) (sig0 : Sig) :
    St → Sig → Bool → Option St :=
  fun s sig b => if sig == sig0 then none else f s sig b

def reaches (f : St → Sig → Bool → Option St) (src tgt : St) : Bool :=
  (reachN f 12 [src]).contains tgt

/-- §12.4's catch-alls — re-ASSIGN (as `ASSIGN`; used only at sources other than IDLE), CANCEL, the
    timeout — excluded when asking whether a content signal is the sole provider of a transition, else
    re-ASSIGN masks every in-contract edge. -/
def isCatchAll (g : Sig) : Bool := (g == ASSIGN) || (g == CANCEL) || (g == Sig.TIMEOUT)

/-! KIND (a) — channel existence: cut the edge and its target is unreachable from IDLE. DELIVER's is
    `nodeliver_strands_done` above. -/

theorem canon_idle_reaches_validating : reaches canonStep IDLE VALIDATING = true := by decide
theorem noAssign_strands_start :
    reaches (dropEdge canonStep IDLE ASSIGN) IDLE VALIDATING = false := by decide

theorem canon_reaches_blocked : reaches canonStep IDLE BLOCKED = true := by decide
theorem noBlock_strands_blocked :
    reaches (dropSig canonStep BLOCK) IDLE BLOCKED = false := by decide

theorem canon_reaches_challenged : reaches canonStep IDLE CHALLENGED = true := by decide
theorem noChallenge_strands_challenged :
    reaches (dropSig canonStep CHALLENGE) IDLE CHALLENGED = false := by decide

/-- CANCEL is not fatal for ABANDONED: ESCALATED's timeout opens the closing without it. What the
    removal loses is §11.4's CANCEL row; CONFIRM_CANCEL's in-flight report survives on the clock's route. -/
theorem canon_reaches_abandoned : reaches canonStep IDLE ABANDONED = true := by decide
/-- …and that route is the only one left: stated cell-wise, because every other state loses its way
    into CANCELLING. -/
theorem noCancel_keeps_the_silence :
    dropSig canonStep CANCEL ESCALATED Sig.TIMEOUT false = some CANCELLING := by decide

theorem noCancel_leaves_only_the_silence :
    (allSt.all (fun s => (s == ESCALATED) || allSig.all (fun g =>
      [false, true].all (fun b =>
        dropSig canonStep CANCEL s g b != some CANCELLING)))) = true := by decide

/-- The contract-changing edges go to OFFERED (§12.4's third rule): re-ASSIGN from every
    reassignable state (also `Fsm.reassign_to_offered`) and ACCEPT_CHALLENGE, whose `new_spec` is a
    revision (`acceptChallenge_dest_inv1_forced`). Decided: the canon table carries them; that every adequate protocol must is not
    machine-checked. -/
theorem canon_reassign_to_offered :
    (canonSt.all (fun s => !(isReassignable s) || (canonStep s ASSIGN false == some OFFERED))) = true := by
  decide
theorem acceptChallenge_dest_inv1_forced :
    canonStep CHALLENGED ACCEPT_CHALLENGE false = some OFFERED
    ∧ canonStep CHALLENGED ACCEPT_CHALLENGE true = some OFFERED := by
  decide

/-- ACCEPT is the sole content edge from OFFERED into EXECUTING (catch-alls excluded) — not a fatality
    claim (the grades above). -/
theorem accept_sole_content_consent :
    (allSig.all (fun g => [false, true].all (fun b =>
      isCatchAll g || !(canonStep OFFERED g b == some EXECUTING) || (g == ACCEPT)))) = true := by decide

/-! KIND (b) — resolution: the edge is the sole content provider of its source's progress transition in
    this table, catch-alls excluded. Excluding re-ASSIGN is a stipulation whose lifting is the
    destination question (§13.2); REJECT_CHALLENGE's destination is `canon_reject_returns_to_the_wait`,
    forced over the log in `LogLanguage.lean`. -/

theorem resolveBlock_sole_content_resume :
    (allSig.all (fun g => [false, true].all (fun b =>
      isCatchAll g || !(canonStep BLOCKED g b == some EXECUTING) || (g == RESOLVE_BLOCK)))) = true := by
  decide

/-- The content edges from CHALLENGED into OFFERED: ACCEPT_CHALLENGE at either `b`, and REJECT_CHALLENGE
    exactly at `b = false` (no consent logged). -/
theorem acceptChallenge_sole_content_reoffer :
    (allSig.all (fun g => [false, true].all (fun b =>
      isCatchAll g || !(canonStep CHALLENGED g b == some OFFERED) || (g == ACCEPT_CHALLENGE)
      || ((g == REJECT_CHALLENGE) && !b)))) = true := by
  decide

theorem rejectChallenge_sole_content_resume :
    (allSig.all (fun g => [false, true].all (fun b =>
      isCatchAll g || !(canonStep CHALLENGED g b == some EXECUTING) || (g == REJECT_CHALLENGE)))) = true := by
  decide

/-- PASS — fatal: "DONE is entered only through PASS" (§12.4), so DONE is unreachable without it. -/
theorem canon_reaches_done : reaches canonStep IDLE DONE = true := by decide
theorem noPass_strands_done : reaches (dropSig canonStep PASS) IDLE DONE = false := by decide
theorem canon_pass_is_genuine : canonStep VALIDATING PASS false = some DONE := by decide

/-- Contrast: in the variant DONE stays reachable without PASS, and only through the auto_pass cell —
    PASS's fatality is that cell's absence (`variant_noPass_only_autopass_into_done`). -/
theorem variant_noPass_keeps_done : reaches (dropSig variantStep PASS) IDLE DONE = true := by decide
theorem variant_noPass_only_autopass_into_done :
    (allSt.all (fun s => allSig.all (fun g => [false, true].all (fun b =>
      !((dropEdge variantStep VALIDATING PASS) s g b == some DONE)
      || ((s == VALIDATING) && (g == Sig.TIMEOUT)))))) = true := by decide

/-! KIND (c) — genuineness: a catch-all keeps the terminal reachable, and only the degenerate route into
    it survives the removal. -/

/-- Without CONFIRM_CANCEL the only edge into ABANDONED is CANCELLING's timeout, which carries no
    in-flight report (§12.6). CONFIRM_CANCEL is FSM-typed (§11.4) and Inv-8-forced
    (`noConfirm_breaks_inv8`). -/
theorem noConfirm_only_timeout_into_abandoned :
    (allSt.all (fun s => allSig.all (fun g => [false, true].all (fun b =>
      !((dropEdge canonStep CANCELLING CONFIRM_CANCEL) s g b == some ABANDONED)
      || (g == Sig.TIMEOUT))))) = true := by decide
theorem canon_confirm_is_genuine : canonStep CANCELLING CONFIRM_CANCEL false = some ABANDONED := by decide

/-! ### CANCELLING's fold: the one-step cancel (§13.3)

`oneStepCancel` settles a CANCEL directly in ABANDONED, with no CANCELLING and no CONFIRM_CANCEL. It
still gives every non-terminal state but IDLE a timeout (`oneStepCancel_still_timeout_defined`) and
satisfies Inv-8 over its reachable states; its deadlock-freedom and finiteness are derived (§12.13,
§20.4), not decided. So deadlock does not hold CANCELLING; Inv-4's reading, clause (2), does (§12.13),
and given it Inv-8 makes CONFIRM_CANCEL its owner's move (`noConfirm_breaks_inv8`). -/

def oneStepCancel (s : St) (sig : Sig) (b : Bool) : Option St :=
  match s, sig with
  | CANCELLING, _ => none                                       -- CANCELLING no longer exists
  | OVERDUE, _ => none                                          -- no canon state
  | _, CANCEL => if isTerminal s then none else some ABANDONED  -- cancel settles in one step
  -- The issuer's silence settles in one step too: with no closing there is nothing for it to open.
  | ESCALATED, Sig.TIMEOUT => some ABANDONED
  | _, _ => canonStep s sig b

theorem oneStepCancel_still_timeout_defined :
    (canonSt.all (fun s => isTerminal s || (s == IDLE) || (s == CANCELLING) ||
        (oneStepCancel s Sig.TIMEOUT false).isSome)) = true := by decide
theorem oneStepCancel_omits_cancelling :
    (allSt.all (fun s => allSig.all (fun g =>
      [false, true].all (fun b => oneStepCancel s g b != some CANCELLING)))) = true := by decide

/-! ### Every §13.3 witness satisfies Inv-8

A witness omits a state (ESCALATED, CANCELLING), and a row it keeps for an unreachable state binds
nobody, so the check reads the states reachable from IDLE (`inv8Reach`). The canon passes the table-wide
`inv8` too. -/

/-- Inv-8 over the states reachable from IDLE. -/
def inv8Reach (f : St → Sig → Bool → Option St) : Bool := inv8On f (reachN f 12 [IDLE])

set_option maxRecDepth 4000 in
theorem witnesses_satisfy_inv8 :
    inv8Reach canonStep = true
    ∧ inv8Reach variantStep = true
    ∧ inv8Reach noEscalatedStep = true
    ∧ inv8Reach oneStepCancel = true := by
  decide

/-- The reachable-state restriction does no work for the canon or the relabeling witnesses: they pass
    table-wide. Only `oneStepCancel` needs it — its CANCELLING row is empty by construction, and
    CANCELLING is unreachable there (`oneStepCancel_omits_cancelling`). -/
theorem witnesses_inv8_tablewide :
    inv8 variantStep = true ∧ inv8 noEscalatedStep = true
    ∧ inv8 oneStepCancel = false := by
  decide

/-! ### Inv-8-forced: CONFIRM_CANCEL

Without CONFIRM_CANCEL, CANCELLING stays reachable (by CANCEL, and through ESCALATED's timeout) but its owner, the
executor, holds only the timeout. The target is not stranded, so the strength grade stands; Inv-8 breaks
instead. Canon-internal, like every witness here. -/

set_option maxRecDepth 4000 in
theorem noConfirm_breaks_inv8 :
    inv8Reach (dropSig canonStep CONFIRM_CANCEL) = false
    ∧ reaches (dropSig canonStep CONFIRM_CANCEL) IDLE CANCELLING = true
    ∧ hasMove (dropSig canonStep CONFIRM_CANCEL) CANCELLING Party.executor = false := by
  decide

set_option maxRecDepth 8000 in
/-- Exactly one: over the whole alphabet, the single-signal removal that breaks Inv-8 on a reachable
    state is CONFIRM_CANCEL. ASSIGN passes vacuously: without it only IDLE, CANCELLING and ABANDONED are
    reachable, where Inv-8 holds for want of anything else. -/
theorem inv8_forces_exactly :
    allSig.filter (fun g => !(inv8Reach (dropSig canonStep g))) = [CONFIRM_CANCEL] := by
  decide

/-! ### C-1's edges are not forced by the timeout axis or by Inv-8

`preC1Step` is the canon without (EXECUTING|REWORKING, CHALLENGE) → CHALLENGED. It keeps the timeout exit
of every canon non-terminal but IDLE and Inv-8 (the executor keeps DELIVER and BLOCK), and CHALLENGED
stays reachable through OFFERED. Decided: the timeout axis and Inv-8 do not force the two edges. What forces them is argued,
not decided: CHALLENGE's row read in every work-active state (§13.3) and the dispute's closures after
consent (§16.12). -/

def preC1Step (s : St) (sig : Sig) (b : Bool) : Option St :=
  match s, sig with
  | EXECUTING, CHALLENGE => none
  | REWORKING, CHALLENGE => none
  | _, _ => canonStep s sig b

set_option maxRecDepth 4000 in
theorem preC1_adequate_without_the_edges :
    (canonSt.all (fun s => isTerminal s || (s == IDLE) || (preC1Step s Sig.TIMEOUT false).isSome)) = true
    ∧ inv8 preC1Step = true ∧ inv8Reach preC1Step = true
    ∧ reaches preC1Step IDLE CHALLENGED = true := by
  decide

/-- …and it differs from the canon on at most those two cells; that it differs on both is
    `canon_challenge_after_consent`. -/
theorem preC1_differs_only_on_the_c1_cells :
    (allSt.all (fun s => allSig.all (fun g =>
      (((s == EXECUTING) || (s == REWORKING)) && (g == CHALLENGE)) ||
      [false, true].all (fun b => canonStep s g b == preC1Step s g b)))) = true := by
  decide

/-! NEGATIVE CONTROLS — the classification shapes can come out the other way, so the greens above are
    not vacuous. -/

theorem control_reaches_nonvacuous : reaches canonStep IDLE DONE = true := by decide
/-- The sole-content-provider shape with the wrong signal (CHALLENGE, which goes to CHALLENGED, not
    EXECUTING) is false — the `.all` discriminates. -/
theorem control_sole_content_false :
    (allSig.all (fun g => [false, true].all (fun b =>
      isCatchAll g || !(canonStep OFFERED g b == some EXECUTING) || (g == CHALLENGE)))) = false := by
  decide

end GFSO.FsmCanon
