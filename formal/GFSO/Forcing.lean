/-
  GFSO — a one-cell perturbation measurement, FROZEN on the table with OVERDUE. No canon claim rests on it: the
  table is not the canon's, and the canon's forcing is over the log (`LogLanguage.lean`, §13.4).

  OBJECT. The table as it stood before OVERDUE's removal — the first timeouts of OFFERED, CHALLENGED, EXECUTING and
  REWORKING into OVERDUE, its own row timeout → ESCALATED and CANCEL → CANCELLING, REJECT_CHALLENGE into EXECUTING
  before consent — in local frozen copies (`step41`, `owner41`, `inv8_41`, `variant41`, `noOverdue41`,
  `preC1_41`), not `FsmCanon.canonStep` (`frozen_differs_only_on_the_changed_cells` names where they differ). Every
  count below is a fact about that table.

  METHOD. One cell's destination replaced (`setCell`), the other 39 held, every destination tried: this tests local
  stability, not forcing.

  WHAT IT CHECKS: `bare` forces no destination (`bare_forces_nothing`); the rows with Inv-1's
  re-consent rule force 27 cells by count (`rows_force_twenty_seven`, `the_partition`); the frozen table meets the
  five further conditions (`canon_satisfies_all`), each independent of `bare` and the rows by a one-cell witness
  (`five_are_independent`), which leave three, four or six destinations (`timeouts_collapse`,
  `cancelling_timeout_freedom`, `resolutions_collapse`); with `waitsEnd` two timeout cells are forced
  (`waitsEnd_forces_two_timeout_cells`); two machines meeting Inv-5's first sentence whose timeout chains do not
  all settle (`the_two_machines_in_the_gap`; §12.12 and §12.13 derive both).

  WHAT IT DOES NOT CHECK:
   (a) The five do not pin the machine: two behaviourally distinct frozen siblings meet them
       (`the_vector_does_not_pin_the_machine`).
   (b) One cell at a time: `bare_forces_nothing` is a lower bound on freedom, the other counts upper bounds
       conditional on the rest of the table. `setCell` only redirects defined cells, so `inv5` and `inv8_41` cannot
       fail in the family and deadlock-freedom survives through the catch-all rows (`bare_conjuncts_never_bind`):
       the negative result is about this family, not about adequacy in general. `setCell` cannot remove an edge
       (nothing on §11.4's removal grades) and ignores the retry guard (`the_fail_cell_is_measured_guard_free`).
   (c) The role predicates do not move here (`roles_are_constant_here`) and each is extensionally its own state
       (`roles_are_extensionally_the_labels`); that the conditions apply to a rival machine is not shown here.

  Over the fixed alphabet, canon-internal; the wall of §20.7 is untouched.
-/
import GFSO.FsmCanon

namespace GFSO.Forcing
open GFSO.Fsm GFSO.Fsm.St GFSO.Fsm.Sig GFSO.FsmCanon

set_option maxRecDepth 4000000
set_option maxHeartbeats 4000000

abbrev Table := St → Sig → Bool → Option St

/-! ### The frozen table, with OVERDUE

Copied cell for cell from `FsmCanon.canonStep` at commit 5ef624d (comments dropped, the guard renamed `b`), with every
definition that reads the table or the owner map. Still taken from `FsmCanon`, table-independent: `sender`, `Party`,
`hasMove`, `settle`. -/

/-- The canon table as it stood with OVERDUE (frozen). -/
def step41 (s : St) (sig : Sig) (b : Bool) : Option St :=
  match s with
  | IDLE => match sig with
    | ASSIGN => some OFFERED
    | CANCEL => some CANCELLING
    | _ => none
  | OFFERED => match sig with
    | ACCEPT => some EXECUTING
    | CHALLENGE => some CHALLENGED
    | Sig.TIMEOUT => some OVERDUE
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | CHALLENGED => match sig with
    | ACCEPT_CHALLENGE => some OFFERED
    | REJECT_CHALLENGE => some EXECUTING
    | Sig.TIMEOUT => some OVERDUE
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | EXECUTING => match sig with
    | DELIVER => some VALIDATING
    | BLOCK => some BLOCKED
    | CHALLENGE => some CHALLENGED
    | Sig.TIMEOUT => some OVERDUE
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
    | FAIL => some (if b then REWORKING else ESCALATED)
    | Sig.TIMEOUT => some ESCALATED
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | REWORKING => match sig with
    | DELIVER => some VALIDATING
    | BLOCK => some BLOCKED
    | CHALLENGE => some CHALLENGED
    | Sig.TIMEOUT => some OVERDUE
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | CANCELLING => match sig with
    | CONFIRM_CANCEL => some ABANDONED
    | Sig.TIMEOUT => some ABANDONED
    | _ => none
  | OVERDUE => match sig with
    | Sig.TIMEOUT => some ESCALATED
    | CANCEL => some CANCELLING
    | _ => none
  | DONE => none
  | ABANDONED => none
  | ESCALATED => match sig with
    | ASSIGN => some OFFERED
    | CANCEL => some CANCELLING
    | Sig.TIMEOUT => some CANCELLING
    | _ => none

/-- The owner map as it stood (frozen): OVERDUE the issuer's. -/
def owner41 : St → Option Party
  | OFFERED | EXECUTING | REWORKING | CANCELLING => some Party.executor
  | CHALLENGED | BLOCKED | VALIDATING | OVERDUE | ESCALATED => some Party.issuer
  | IDLE | DONE | ABANDONED => none

/-- Inv-8 over all twelve constructors with the owner map as it stood (frozen). -/
def inv8_41 (f : Table) : Bool :=
  allSt.all (fun s => match owner41 s with
    | none => true
    | some p => hasMove f s p)

/-- The auto_pass sibling of the frozen table (`FsmCanon.variant_*` on the current one). -/
def variant41 (s : St) (sig : Sig) (b : Bool) : Option St :=
  match s, sig with
  | VALIDATING, Sig.TIMEOUT => some DONE
  | _, _ => step41 s sig b

/-- The frozen table with OVERDUE relabelled to ESCALATED on the timeout cells (frozen). NB this is
    NOT the v4.1 canon: REJECT_CHALLENGE still goes to EXECUTING at both bit values. -/
def noOverdue41 (s : St) (sig : Sig) (b : Bool) : Option St :=
  match step41 s sig b with
  | some OVERDUE => some ESCALATED
  | other => other

/-- The frozen table without the post-consent CHALLENGE cells (frozen). -/
def preC1_41 (s : St) (sig : Sig) (b : Bool) : Option St :=
  match s, sig with
  | EXECUTING, CHALLENGE => none
  | REWORKING, CHALLENGE => none
  | _, _ => step41 s sig b

/-- The frozen copy agrees with `canonStep` off the v4.1 cells: the four first timeouts, the OVERDUE row,
    REJECT_CHALLENGE. -/
theorem frozen_differs_only_on_the_changed_cells :
    (allSt.all (fun s => allSig.all (fun g =>
      (((s == OFFERED) || (s == CHALLENGED) || (s == EXECUTING) || (s == REWORKING))
        && (g == Sig.TIMEOUT))
      || (s == OVERDUE) || ((s == CHALLENGED) && (g == REJECT_CHALLENGE))
      || [false, true].all (fun b => step41 s g b == canonStep s g b)))) = true := by decide

/-- the table with ONE cell's destination replaced; applied only to `cells`, which are defined already, it
    changes no cell's definedness, and it ignores the
    retry guard — (b) in the header. -/
def setCell (f : Table) (s0 : St) (g0 : Sig) (t : St) : Table :=
  fun s g b => if (s == s0) && (g == g0) then some t else f s g b

def adm (f : Table) (s : St) (g : Sig) : Bool := (f s g false).isSome || (f s g true).isSome

/-! ### The roles — stated by what their occupant may do, not by the state's name -/

def isOffer (f : Table) (s : St) : Bool := adm f s ACCEPT
def isWork (f : Table) (s : St) : Bool := adm f s DELIVER
def isValidation (f : Table) (s : St) : Bool := adm f s PASS && adm f s FAIL
def isDispute (f : Table) (s : St) : Bool := adm f s ACCEPT_CHALLENGE && adm f s REJECT_CHALLENGE
def isBlockedRole (f : Table) (s : St) : Bool := adm f s RESOLVE_BLOCK
def isClosing (f : Table) (s : St) : Bool := adm f s CONFIRM_CANCEL

/-! ### Adequacy — WEAKER than §13.1's bare adequacy (see `bare`) -/

/-- Inv-5's first sentence **as §12.12 writes it**: every non-terminal but IDLE has a timeout cell that is defined. -/
def inv5 (f : Table) : Bool :=
  allSt.all (fun s => isTerminal s || (s == IDLE) || (f s Sig.TIMEOUT false).isSome)

/-- Every timeout chain SETTLES: following only timeout edges from any state reaches a terminal. Stronger
    than `inv5` (`the_two_machines_in_the_gap`) and than Inv-5 (a) alone, which a decision ⇄ closing cycle
    meets (§12.12). -/
def timeoutEndsFrom (f : Table) : Nat → St → Bool
  | 0, s => isTerminal s
  | Nat.succ n, s =>
      isTerminal s || (match f s Sig.TIMEOUT false with
        | some t => if t == s then false else timeoutEndsFrom f n t
        | none => false)

def waitsEnd (f : Table) : Bool :=
  allSt.all (fun s => isTerminal s || (s == IDLE) || timeoutEndsFrom f 12 s)

/-- the BACKWARD closure from the terminals: one fixpoint for the whole table, where a forward
    search costs one per start state. `back` is monotone and inflationary, so the length test is a
    genuine fixpoint test, and fuel 12 = |St| always saturates. -/
def back (f : Table) (good : List St) : List St :=
  allSt.filter (fun s => good.contains s ||
    allSig.any (fun g => [false, true].any (fun b =>
      match f s g b with | some t => good.contains t | none => false)))

def backN (f : Table) : Nat → List St → List St
  | 0, good => good
  | Nat.succ n, good =>
      let nxt := back f good
      if nxt.length == good.length then good else backN f n nxt

/-- §13.1's deadlock-freedom: from every state SOME terminal is reachable by SOME path; that a wait ends is
    `waitsEnd`. -/
def liveEnds (f : Table) : Bool :=
  let good := backN f 12 (allSt.filter isTerminal)
  allSt.all (fun s => good.contains s)

/-- `bare` = deadlock-freedom + `inv5` + `inv8_41` (the frozen owner map). Inv-6 is automatic: a `Table` is a
    function. It omits §13.1's row-exit clause, so it is weaker than bare adequacy; "bare adequacy" in this
    file's comments names this predicate. -/
def bare (f : Table) : Bool := inv5 f && liveEnds f && inv8_41 f

/-! ### The §11.4 rows with Inv-1's re-consent rule, as conditions on the destination's role.

Two of the nine clauses, ASSIGN's and ACCEPT_CHALLENGE's, are Inv-1's (`FsmCanon.canon_reassign_to_offered`,
`acceptChallenge_dest_inv1_forced`), so the count rests on both. -/

def rows (f : Table) : Bool :=
  (allSt.all (fun s => match f s ASSIGN false with
      | some t => isOffer f t | none => true))
  && (match f OFFERED ACCEPT false with | some t => isWork f t | none => true)
  && (allSt.all (fun s => match f s DELIVER false with
      | some t => isValidation f t | none => true))
  && (allSt.all (fun s => match f s PASS false with
      | some t => settle t == Settle.pass | none => true))
  && (allSt.all (fun s => match f s BLOCK false with
      | some t => isBlockedRole f t | none => true))
  && (allSt.all (fun s => match f s CHALLENGE false with
      | some t => isDispute f t | none => true))
  && (allSt.all (fun s => match f s ACCEPT_CHALLENGE false with
      | some t => isOffer f t | none => true))
  && (allSt.all (fun s => match f s CANCEL false with
      | some t => isClosing f t | none => true))
  && (allSt.all (fun s => match f s CONFIRM_CANCEL false with
      | some t => settle t == Settle.abandoned | none => true))

theorem canon_meets_rows : rows step41 = true := by decide

/-! ### The five further conditions and the canon clause each encodes

 · `settlementProvenance` — §12.5's "the clock never invents a verdict", generalized to every signal: DONE only by
   PASS, ABANDONED only out of a closing.
 · `noResumption` — §12.5's "the way back to work on the node runs through the handover, never around it": no
   timeout into a work state.
 · `ownershipOnEdges` — Inv-8's edge clause (§12.13), over `owner41`.
 · `versionProvenance` — §12.15's "a packet version enters only through OFFERED and only by the issuer's act",
   keyed to the sender: RESOLVE_BLOCK and REJECT_CHALLENGE are issuer acts too, so the resolution cells keep
   OFFERED (`resolutions_collapse`).
 · `entryExclusivity` — §12.11's "a challenge, block or delivery stands only by its asking": the rows' converse,
   a validation state entered only by DELIVER, a dispute only by CHALLENGE, a blocked state only by BLOCK. -/

def settlesOnlyByPass (f : Table) : Bool :=
  allSt.all (fun s => allSig.all (fun g => [false, true].all (fun b =>
    match f s g b with
    | some t => (settle t != Settle.pass) || (g == PASS)
    | none => true)))

def abandonsOnlyFromClosing (f : Table) : Bool :=
  allSt.all (fun s => allSig.all (fun g => [false, true].all (fun b =>
    match f s g b with
    | some t => (settle t != Settle.abandoned) || isClosing f s
    | none => true)))

def settlementProvenance (f : Table) : Bool := settlesOnlyByPass f && abandonsOnlyFromClosing f

def noResumption (f : Table) : Bool :=
  allSt.all (fun s => match f s Sig.TIMEOUT false with
    | some t => !(isWork f t) | none => true)

def ownershipOnEdges (f : Table) : Bool :=
  allSt.all (fun s => allSig.all (fun g => [false, true].all (fun b =>
    match f s g b with
    | some t => (owner41 t).isSome || isTerminal t
    | none => true)))

def versionProvenance (f : Table) : Bool :=
  allSt.all (fun s => allSig.all (fun g => [false, true].all (fun b =>
    match f s g b with
    | some t => !(isOffer f t) || (sender g == some Party.issuer)
    | none => true)))

def entryExclusivity (f : Table) : Bool :=
  allSt.all (fun s => allSig.all (fun g => [false, true].all (fun b =>
    match f s g b with
    | some t =>
        (!(isValidation f t) || (g == DELIVER))
        && (!(isDispute f t) || (g == CHALLENGE))
        && (!(isBlockedRole f t) || (g == BLOCK))
    | none => true)))

/-- the rows and the five. `bare` is not a conjunct: every single-cell edit meets it (`bare_forces_nothing`),
    and leaving it out spares the kernel re-deciding reachability per destination. -/
def above (f : Table) : Bool :=
  rows f && settlementProvenance f && noResumption f && ownershipOnEdges f
  && versionProvenance f && entryExclusivity f

def full (f : Table) : Bool := bare f && above f

/-- The frozen table satisfies all of it. -/
theorem canon_satisfies_all : full step41 = true := by decide

/-- …and every timeout chain of it settles. -/
theorem canon_waits_end : waitsEnd step41 = true := by decide

/-! ### (1) Bare adequacy forces nothing -/

def cells : List (St × Sig) :=
  allSt.flatMap (fun s => allSig.filterMap (fun g =>
    if (step41 s g false).isSome then some (s, g) else none))

def freedom (pred : Table → Bool) (s : St) (g : Sig) : List St :=
  allSt.filter (fun t => pred (setCell step41 s g t))

theorem forty_cells : cells.length = 40 := by decide

/-- For every defined cell, every one of the twelve states is an adequate destination. -/
theorem bare_forces_nothing :
    cells.all (fun c => (freedom bare c.1 c.2).length == 12) = true := by decide

/-! ### (2) The rows force twenty-seven of the forty -/

/-- the twelve cells the rows leave open: the nine timeouts, and the three resolution cells -/
def isFreeCell (c : St × Sig) : Bool :=
  (c.2 == Sig.TIMEOUT) || (c.2 == REJECT_CHALLENGE) || (c.2 == RESOLVE_BLOCK) || (c.2 == FAIL)

theorem twelve_free_cells : (cells.filter isFreeCell).length = 12 := by decide

/-- A COUNT, not a disjunction green at any count: exactly twenty-seven cells have a one-element freedom set
    under the rows. -/
theorem rows_force_twenty_seven :
    (cells.filter (fun c => (freedom rows c.1 c.2).length == 1)).length = 27 := by decide

/-- and the twenty-eighth, OFFERED/ACCEPT, is forced up to the one behaviour class
    EXECUTING ≡ REWORKING (`FsmCanon.canon_exec_rework_same`). 27 + 1 + 12 = 40. -/
theorem accept_forced_up_to_the_rework_class :
    freedom rows OFFERED ACCEPT = [EXECUTING, REWORKING] := by decide

/-! ### (3) What the five leave -/

/-- Every timeout cell but CANCELLING's is left with the three lapse/closing states. At OVERDUE and ESCALATED one
    is the self-loop, which `inv5` admits, Inv-5 (a) excludes (§12.12), and of this file's conditions only
    `waitsEnd` excludes (`the_two_machines_in_the_gap`). -/
theorem timeouts_collapse :
    (cells.all (fun c => !(c.2 == Sig.TIMEOUT) || (c.1 == CANCELLING) ||
      (freedom above c.1 c.2 == [CANCELLING, OVERDUE, ESCALATED]))) = true := by decide

theorem cancelling_timeout_freedom :
    freedom above CANCELLING Sig.TIMEOUT = [CANCELLING, ABANDONED, OVERDUE, ESCALATED] := by decide

/-- The three resolution cells: re-consent, resume the work (one class), or the lapse/closing path. OFFERED
    survives because `versionProvenance` is keyed to the sender. -/
theorem resolutions_collapse :
    freedom above CHALLENGED REJECT_CHALLENGE
      = [OFFERED, EXECUTING, REWORKING, CANCELLING, OVERDUE, ESCALATED]
    ∧ freedom above BLOCKED RESOLVE_BLOCK
      = [OFFERED, EXECUTING, REWORKING, CANCELLING, OVERDUE, ESCALATED]
    ∧ freedom above VALIDATING FAIL
      = [OFFERED, EXECUTING, REWORKING, CANCELLING, OVERDUE, ESCALATED] := by decide

/-- 27 forced + 12 free + OFFERED/ACCEPT = 40, the sets disjoint (a free cell has all twelve destinations open
    under the rows). -/
theorem the_partition :
    (cells.filter (fun c => (freedom rows c.1 c.2).length == 1)).length
      + (cells.filter isFreeCell).length + 1 = cells.length
    ∧ cells.all (fun c => !(isFreeCell c) || ((freedom rows c.1 c.2).length == 12)) = true := by
  decide

/-- Why `bare_forces_nothing` is weak: across the family each of `bare`'s three conjuncts holds at EVERY edit,
    two by construction (`setCell` keeps definedness; `inv5` and `inv8_41` are definedness predicates). -/
theorem bare_conjuncts_never_bind :
    cells.all (fun c => allSt.all (fun t =>
      inv5 (setCell step41 c.1 c.2 t)
      && inv8_41 (setCell step41 c.1 c.2 t)
      && liveEnds (setCell step41 c.1 c.2 t))) = true := by decide

/-- `waitsEnd` with the five FORCES two free cells to the frozen table's value — CANCELLING's timeout to
    ABANDONED, ESCALATED's to CANCELLING — and cuts OVERDUE's to two. It removes at OVERDUE the self-loop; at
    ESCALATED the self-loop and OVERDUE, whose timeout returns to ESCALATED; at CANCELLING the self-loop and two
    destinations whose timeout path cycles back. -/
theorem waitsEnd_forces_two_timeout_cells :
    (allSt.filter (fun t => above (setCell step41 CANCELLING Sig.TIMEOUT t)
        && waitsEnd (setCell step41 CANCELLING Sig.TIMEOUT t))) = [ABANDONED]
    ∧ (allSt.filter (fun t => above (setCell step41 ESCALATED Sig.TIMEOUT t)
        && waitsEnd (setCell step41 ESCALATED Sig.TIMEOUT t))) = [CANCELLING]
    ∧ (allSt.filter (fun t => above (setCell step41 OVERDUE Sig.TIMEOUT t)
        && waitsEnd (setCell step41 OVERDUE Sig.TIMEOUT t))).length = 2 := by decide

/-! ### What the five do NOT do -/

/-- Negative control: two behaviourally distinct frozen siblings satisfy `full` — `noOverdue41` with eleven
    states, `preC1_41` without the post-consent CHALLENGE cells — so the five fix neither the state set nor
    those edges. `preC1_41` passes only because `bare` lacks §13.1's row-exit clause (cf. §13.3). -/
theorem the_vector_does_not_pin_the_machine :
    full noOverdue41 = true ∧ full preC1_41 = true := by decide

/-! ### The gap between Inv-5's first sentence and waits ending -/

def idleParkStep (s : St) (g : Sig) (b : Bool) : Option St :=
  match s, g with | VALIDATING, Sig.TIMEOUT => some IDLE | _, _ => step41 s g b

def overdueSelfLoop (s : St) (g : Sig) (b : Bool) : Option St :=
  match s, g with | OVERDUE, Sig.TIMEOUT => some OVERDUE | _, _ => step41 s g b

/-- Both pass `bare` and in neither does every timeout chain settle; the IDLE park fails Inv-8's edge clause
    (`ownershipOnEdges`), the self-loop does not, so that clause refuses one and `waitsEnd` both. -/
theorem the_two_machines_in_the_gap :
    bare idleParkStep = true ∧ waitsEnd idleParkStep = false
      ∧ ownershipOnEdges idleParkStep = false
    ∧ bare overdueSelfLoop = true ∧ waitsEnd overdueSelfLoop = false
      ∧ ownershipOnEdges overdueSelfLoop = true := by decide

/-! ### Independence of the five -/

def clockResumes (s : St) (g : Sig) (b : Bool) : Option St :=
  match s, g with | OVERDUE, Sig.TIMEOUT => some EXECUTING | _, _ => step41 s g b

def clockReoffers (s : St) (g : Sig) (b : Bool) : Option St :=
  match s, g with | OVERDUE, Sig.TIMEOUT => some OFFERED | _, _ => step41 s g b

def clockDelivers (s : St) (g : Sig) (b : Bool) : Option St :=
  match s, g with | OVERDUE, Sig.TIMEOUT => some VALIDATING | _, _ => step41 s g b

/-- and the battery can come out false, so `canon_satisfies_all` is not green by shape -/
theorem control_battery_can_fail : above clockDelivers = false := by decide

/-- Each condition is independent of `bare` AND of the rows, which do the forcing; each witness a one-cell
    edit. -/
theorem five_are_independent :
    (bare variant41 && rows variant41 && !(settlementProvenance variant41))
    && (bare clockResumes && rows clockResumes && !(noResumption clockResumes))
    && (bare idleParkStep && rows idleParkStep && !(ownershipOnEdges idleParkStep))
    && (bare clockReoffers && rows clockReoffers && !(versionProvenance clockReoffers))
    && (bare clockDelivers && rows clockDelivers && !(entryExclusivity clockDelivers)) = true := by
  decide

/-- each of the FIVE witnesses differs from the canon at exactly one cell, its own — the
    settlement witness and the IDLE park at (VALIDATING, timeout), the three clock witnesses at
    (OVERDUE, timeout). `overdueSelfLoop` is not one of the five and is covered by the gap theorem. -/
theorem witnesses_are_one_cell_edits :
    ([(variant41, VALIDATING), (idleParkStep, VALIDATING), (clockResumes, OVERDUE),
      (clockReoffers, OVERDUE), (clockDelivers, OVERDUE)].all (fun w =>
      allSt.all (fun s => allSig.all (fun g =>
        ((s == w.2) && (g == Sig.TIMEOUT)) ||
        [false, true].all (fun b => step41 s g b == w.1 s g b))))) = true := by decide

/-! ### The measurement's own limits, machine-checked rather than promised -/

/-- `setCell` only redirects, so no role predicate moves anywhere in this measurement. -/
theorem roles_are_constant_here :
    (cells.all (fun c => allSt.all (fun t =>
      allSt.all (fun s =>
        (isOffer (setCell step41 c.1 c.2 t) s == isOffer step41 s)
        && (isWork (setCell step41 c.1 c.2 t) s == isWork step41 s)
        && (isValidation (setCell step41 c.1 c.2 t) s == isValidation step41 s)
        && (isDispute (setCell step41 c.1 c.2 t) s == isDispute step41 s)
        && (isBlockedRole (setCell step41 c.1 c.2 t) s == isBlockedRole step41 s)
        && (isClosing (setCell step41 c.1 c.2 t) s == isClosing step41 s))))) = true := by
  decide

/-- …and on the frozen table each role is extensionally its own state: here the role reading is the name
    reading. -/
theorem roles_are_extensionally_the_labels :
    allSt.filter (isValidation step41) = [VALIDATING]
    ∧ allSt.filter (isOffer step41) = [OFFERED]
    ∧ allSt.filter (isClosing step41) = [CANCELLING]
    ∧ allSt.filter (isDispute step41) = [CHALLENGED]
    ∧ allSt.filter (isBlockedRole step41) = [BLOCKED]
    ∧ allSt.filter (isWork step41) = [EXECUTING, REWORKING] := by decide

/-- `setCell` ignores the retry guard, so at the one guard-dependent cell the family measured does not contain
    the frozen table itself. -/
theorem the_fail_cell_is_measured_guard_free :
    (allSt.all (fun t => allSig.any (fun g => [false, true].any (fun b =>
      setCell step41 VALIDATING FAIL t VALIDATING g b != step41 VALIDATING g b)))) = true := by
  decide

end GFSO.Forcing
