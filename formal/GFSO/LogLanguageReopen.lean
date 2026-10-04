/-
  GFSO — R′ over the log (§13.5).

  `FsmCanon` excludes R′, its gate being a log fact (§12.14). Here the gate is an INPUT at the settlements, as FAIL's
  retry guard is at FAIL (`bitsAt`), and R′'s form (§12.14) stands in place of `pTerminal` as two halves:
  `pUnmakeOnly` (a settlement unmade only by the gated signal where the gate holds) and `pReopenAdmit` (there it is
  admitted). At a gate that never holds `pUnmakeOnly` IS `pTerminal`: the base is `max_reopens` = 0.

  CHECKED, under every reading of the missed bound's owner: `forced`, `the_only_exit_is_an_offer`,
  `off_the_settlements_nothing_moves`, `admission_carries_five`, and `the_form_is_chosen` — a rival gating CANCEL
  is equally forced, so the vocabulary does not choose the form.
-/
import GFSO.LogLanguageLoadsIssuer  -- chained, not needed: the heavy log-kernel modules build one after another

namespace GFSO.LogLanguage.Reopen
open GFSO.Fsm GFSO.Fsm.Sig GFSO.LogLanguage W

set_option maxRecDepth 100000
set_option maxHeartbeats 0

/-- The gated signal `g` reads R′'s gate at the settlements; FAIL reads its retry guard everywhere. -/
def bitsAt (g : Sig) (r : Rec) (s : Sig) : List Bool :=
  if s == FAIL then bools else if s == g && term r.w then bools else [true]

/-- A settlement is unmade only by `g` where the gate holds; at `g = ASSIGN` R′'s rule. -/
def pUnmakeOnly (g : Sig) : Principle := fun _ r s b o => !(term r.w && o.isSome) || (s == g && b)
/-- Where the gate holds, the gated signal is admitted. -/
def pReopenAdmit (g : Sig) : Principle := fun _ r s b o => !(s == g && term r.w && b) || o.isSome

def generalR : List Principle :=
  [pInitiation, pCancel, pInv5, pInv8Edges, pChallengeReach, pWorkReports, pReportsNeedVersion]
def fullR (g : Sig) (admit : Bool) : List Principle :=
  sigMeanings ++ generalR ++ [pRevision, pUnmakeOnly g] ++ (if admit then [pReopenAdmit g] else []) ++ clauses

def cellOutsR (P : List Principle) (rd : Option Bool) (r : Rec) (s : Sig) (b : Bool) : List (Option Rec) :=
  outs.filter fun o => P.all fun p => p rd r s b o
def succsR (g : Sig) (P : List Principle) (rd : Option Bool) (r : Rec) : List Rec :=
  (allSig.map fun s => (bitsAt g r s).map fun b => (cellOutsR P rd r s b).filterMap id).flatten.flatten
def reachR (g : Sig) (P : List Principle) (rd : Option Bool) : Nat → List Rec → List Rec
  | 0, acc => acc
  | n + 1, acc =>
      let nxt := (acc.map (succsR g P rd)).flatten.foldl (fun a x => if a.contains x then a else a ++ [x]) acc
      if nxt.length == acc.length then acc else reachR g P rd n nxt
def reachableR (g : Sig) (P : List Principle) (rd : Option Bool) : List Rec := reachR g P rd 12 [start]
def cellsR (g : Sig) (P : List Principle) (rd : Option Bool) : List (Rec × Sig × Bool) :=
  ((reachableR g P rd).map fun r => (allSig.map fun s => (bitsAt g r s).map fun b => (r, s, b)).flatten).flatten
def notForcedR (g : Sig) (P : List Principle) (rd : Option Bool) : List (Rec × Sig × Bool) :=
  (cellsR g P rd).filter fun ⟨r, s, b⟩ => (cellOutsR P rd r s b).length != 1

/-- Every reachable cell is forced, under every reading; the same 22 records as the base. -/
theorem forced :
    readings.all (fun rd => (notForcedR ASSIGN (fullR ASSIGN true) rd).length == 0 &&
      (reachableR ASSIGN (fullR ASSIGN true) rd).length == 22) = true := by decide +kernel

/-- Out of a settlement the one move is ASSIGN under the gate, into an unconsented offer with no FAIL on it — the
    target fixed by ASSIGN's meaning (`pInstall`). -/
theorem the_only_exit_is_an_offer :
    readings.all (fun rd => (cellsR ASSIGN (fullR ASSIGN true) rd).all (fun ⟨r, s, b⟩ =>
      !(term r.w) || cellOutsR (fullR ASSIGN true) rd r s b ==
        (if s == ASSIGN && b then [some ⟨offer, false, false⟩] else [none]))) = true := by decide +kernel

/-- Every other reachable cell has the base's forced outcome. -/
theorem off_the_settlements_nothing_moves :
    readings.all (fun rd => (cellsR ASSIGN (fullR ASSIGN true) rd).all (fun ⟨r, s, b⟩ =>
      term r.w || cellOutsR (fullR ASSIGN true) rd r s b == cellOuts full rd r s b)) = true := by decide +kernel

/-- Without the admission half, exactly the five gated ASSIGN cells over the reachable settlements stay open. -/
theorem admission_carries_five :
    readings.all (fun rd => (notForcedR ASSIGN (fullR ASSIGN false) rd).length == 5) = true := by decide +kernel

/-- With CANCEL as the gated signal the machine is equally forced. -/
theorem the_form_is_chosen :
    readings.all (fun rd => (notForcedR CANCEL (fullR CANCEL true) rd).length == 0) = true := by decide +kernel

end GFSO.LogLanguage.Reopen
