/-
  GFSO — the protocol as a language over the log: the forcing of §13.4, over the table of §12.4.

  `Forcing.lean`'s per-cell perturbation of a frozen table tests local stability, not forcing; this module asks over the log.

  VOCABULARY. A record `Rec` is §13.4's record: the open wait `w`, consent to the current version `c`, a FAIL on
  it `f` (set by any FAIL, `pFail`). FAIL's retry bit is an input, as in `FsmCanon.canonStep`. A record for a
  missed bound (`lapse`) is kept, its owner the reading `rd` — nobody, the executor, the issuer — each run.

  PRINCIPLES. Each reads ONE transition (record, signal, bit, outcome), so a cell admitting exactly one outcome over
  the whole outcome space is forced in §13.4's sense: `sigMeanings`, `general`, the reassignable set `pRevision`,
  and `clauses` — Inv-4's entries `decisionEntries` and C1 (Inv-7), C2 (Inv-8), C3 (Inv-1), C4 (Inv-5).
  Authoritative cancellation is not among them (`authority_is_derived`).

  CHECKED: `forced`, `never_lapses`, `accept_fatal` here; `readings_agree`, `agrees_with_the_canon` —
  each forced outcome is `FsmCanon.canonStep`'s with REWORKING folded into EXECUTING and the table's bit read off
  the record at REJECT_CHALLENGE, from the input at FAIL — and `authority_is_derived` in `LogLanguageAgrees`; the
  loads in the LogLanguageLoads modules; the missed bound as a channel in `LogLanguageLapse`. Scope §13.6:
  deterministic machines over this vocabulary.
-/
import GFSO.Forcing  -- chained (FsmCanon comes with it): the heavy modules build one after another

namespace GFSO.LogLanguage
open GFSO.Fsm GFSO.Fsm.Sig

set_option maxRecDepth 100000
set_option maxHeartbeats 0

/-- The open wait on the log; `lapse` = a bound was missed. -/
inductive W | idle | offer | work | chal | block | deliv | hand | lapse | close | done | aband
deriving DecidableEq, Repr

structure Rec where
  w : W
  c : Bool
  f : Bool
deriving DecidableEq, Repr

open W

def allW : List W := [idle, offer, work, chal, W.block, deliv, hand, lapse, close, done, aband]
def bools : List Bool := [false, true]
def allRec : List Rec := (allW.map fun w => (bools.map fun c => bools.map fun f => (⟨w, c, f⟩ : Rec)).flatten).flatten
def outs : List (Option Rec) := none :: allRec.map some
def allSig : List Sig :=
  [ACCEPT, CHALLENGE, BLOCK, DELIVER, CONFIRM_CANCEL, ASSIGN, ACCEPT_CHALLENGE, REJECT_CHALLENGE, PASS, FAIL,
   CANCEL, RESOLVE_BLOCK, Sig.TIMEOUT]
def bitsOf : Sig → List Bool | FAIL => bools | _ => [true]

def term : W → Bool | done => true | aband => true | _ => false
def isExec : Sig → Bool
  | ACCEPT => true | CHALLENGE => true | BLOCK => true | DELIVER => true | CONFIRM_CANCEL => true | _ => false
def catchAll : Sig → Bool | ASSIGN => true | CANCEL => true | _ => false
def install : Sig → Bool | ASSIGN => true | ACCEPT_CHALLENGE => true | _ => false
/-- the question each answer answers (§11.2) -/
def answers : Sig → Option W
  | ACCEPT => some offer | ACCEPT_CHALLENGE => some chal | REJECT_CHALLENGE => some chal
  | RESOLVE_BLOCK => some W.block | PASS => some deliv | FAIL => some deliv | CONFIRM_CANCEL => some close
  | _ => none
/-- the question each report opens (§11.2) -/
def opens : Sig → Option W
  | CHALLENGE => some chal | BLOCK => some block | DELIVER => some deliv | CANCEL => some close | _ => none
def isQuestion : W → Bool | chal => true | block => true | deliv => true | _ => false

/-- Each wait's owner, read off the log for C2: §12.13's owner table, a per-state input (§13.4). IDLE and the
    settlements have none; the lapse's is the reading `rd`. `some true` = the executor. -/
def ownerExec (rd : Option Bool) : W → Option Bool
  | offer => some true | work => some true | close => some true
  | chal => some false | block => some false | deliv => some false | hand => some false
  | lapse => rd
  | _ => none

abbrev Principle := Option Bool → Rec → Sig → Bool → Option Rec → Bool

/-! ### The signals' meanings (§11.2) -/
def pAnswer : Principle := fun _ r s _ o =>
  match answers s with
  | none => true
  | some q => term r.w || (o.isSome == (r.w == q))
def pOpens : Principle := fun _ _ s _ o =>
  match opens s, o with
  | some q, some x => x.w == q
  | _, _ => true
def pInstall : Principle := fun _ _ s _ o =>
  !install s || o.isNone || o == some ⟨offer, false, false⟩
def pLogged : Principle := fun _ r s _ o =>
  match o with
  | none => true
  | some x => install s ||
      ((r.c ≤ x.c) && (r.f ≤ x.f) && (x.c == r.c || s == ACCEPT) && (x.f == r.f || s == FAIL))
def pAccept : Principle := fun _ _ s _ o =>
  match o with
  | none => true
  | some x => !(s == ACCEPT && !x.c)
def pPass : Principle := fun _ _ s _ o => !(s == PASS) || o.isNone || (o.map (·.w)) == some done
/-- CONFIRM_CANCEL's meaning (§13.4): it settles the closing. -/
def pConfirm : Principle := fun _ _ s _ o => !(s == CONFIRM_CANCEL) || o.isNone || (o.map (·.w)) == some aband
def pFail : Principle := fun _ _ s b o =>
  match o with
  | none => true
  | some x => !(s == FAIL) || (x.f && !(!b && x.w == work))

/-! ### General sentences of the canon -/
def pTerminal : Principle := fun _ r _ _ o => !(term r.w && o.isSome)
/-- ASSIGN initiates (§11.2); IDLE has no clock (§12.12). -/
def pInitiation : Principle := fun _ r s _ o =>
  !(r.w == idle) || (if s == ASSIGN then o.isSome else !(s == Sig.TIMEOUT && o.isSome))
def pCancel : Principle := fun _ r s _ o => !(s == CANCEL) || term r.w || (o.isSome == !(r.w == close))
def pInv5 : Principle := fun _ r s _ o => !(s == Sig.TIMEOUT) || term r.w || r.w == idle || o.isSome
/-- Inv-8's edge clause (§12.13). -/
def pInv8Edges : Principle := fun rd _ _ _ o =>
  match o with
  | none => true
  | some x => term x.w || (ownerExec rd x.w).isSome
def pChallengeReach : Principle := fun _ r s _ o => !(s == CHALLENGE) || !(r.w == offer || r.w == work) || o.isSome
def pWorkReports : Principle := fun _ r s _ o => !(s == DELIVER || s == BLOCK) || !(r.w == work) || o.isSome
/-- No report (CHALLENGE, BLOCK, DELIVER) out of a closing (§12.6). -/
def pReportsNeedVersion : Principle := fun _ r s _ o =>
  !((s == CHALLENGE || s == BLOCK || s == DELIVER) && r.w == close && o.isSome)
/-- Authoritative cancellation (out of the closing only to abandonment); not in `full`: `authority_is_derived`. -/
def pClosingAuth : Principle := fun _ r _ _ o => !(r.w == close) || o.isNone || (o.map (·.w)) == some aband
/-- The reassignable set (§12.3). -/
def pRevision : Principle := fun _ r s _ o =>
  !(s == ASSIGN) || term r.w || r.w == idle || (o.isSome == !(r.w == close))
/-- The reassignable set excluding the lapse (OVERDUE), as it stood; only a flip (`the_old_exception_is_idle`). -/
def pRevision41 : Principle := fun _ r s _ o =>
  !(s == ASSIGN) || term r.w || r.w == idle || (o.isSome == !(r.w == close || r.w == lapse))

/-! ### The clauses -/
/-- C1, Inv-7's "a state is what stands on the log" (§12.11), clause by clause. -/
def c1 : Principle := fun _ r s _ o =>
  match o with
  | none => true
  | some x =>
      (!isQuestion x.w || opens s == some x.w) && (!(x.w == close) || s == CANCEL || s == Sig.TIMEOUT) &&
      (!(x.w == lapse) || s == Sig.TIMEOUT) &&
      !(x.w == offer && x.c) && (!(x.w == done) || s == PASS) && (!(x.w == aband) || r.w == close)
/-- C2, Inv-8's owner-exclusivity (§12.13); one node, so the cascade is read as the catch-all CANCEL. -/
def c2 : Principle := fun rd r s _ o =>
  o.isNone || s == Sig.TIMEOUT || catchAll s || term r.w ||
    (match ownerExec rd r.w with | some e => e == isExec s | none => false)
/-- C3, Inv-1's "the executor is bound to a version's work only by his ACCEPT of it" (§12.3): work, block and
    delivery records carry consent. -/
def c3 : Principle := fun _ _ _ _ o =>
  match o with
  | none => true
  | some x => !(x.w == work || x.w == W.block || x.w == deliv) || x.c
/-- Inv-4's two channels (§12.9, clause (2)): the issuer's decision, and the executor's acknowledgment of a closing. -/
def isChannel : W → Bool | hand => true | close => true | _ => false
/-- C4, Inv-5 (a)–(c) (§12.12); (a) read as leaving the state. -/
def c4 : Principle := fun _ r s _ o =>
  !(s == Sig.TIMEOUT) ||
    (match o with
     | none => true
     | some x => !(x.w == r.w) && (isChannel x.w || (r.w == close && x.w == aband)) &&
         (!(x.w == close) || r.w == hand))
/-- C4 with the missed bound counted as a channel of its own (§13.4) — a flip. -/
def c4Lapse : Principle := fun _ r s _ o =>
  !(s == Sig.TIMEOUT) ||
    (match o with
     | none => true
     | some x => !(x.w == r.w) && (isChannel x.w || x.w == lapse || (r.w == close && x.w == aband)) &&
         (!(x.w == close) || r.w == hand))
/-- Inv-4's entries into the decision, sharpened by the alternative reading of its routes (§12.12, §13.4): only a
    party wait's timeout (`isPartyWait`, the lapse not among them) or FAIL with no rounds left. -/
def isPartyWait : W → Bool | offer => true | work => true | chal => true | W.block => true | deliv => true | _ => false
def decisionEntries : Principle := fun _ r s b o =>
  !((o.map (·.w)) == some hand) || (s == Sig.TIMEOUT && isPartyWait r.w) || (s == FAIL && !b)

def sigMeanings : List Principle := [pAnswer, pOpens, pInstall, pLogged, pAccept, pPass, pConfirm, pFail]
def general : List Principle :=
  [pTerminal, pInitiation, pCancel, pInv5, pInv8Edges, pChallengeReach, pWorkReports, pReportsNeedVersion]
def clauses : List Principle := [decisionEntries, c1, c2, c3, c4]

/-- The canon's general sentences with the reassignable set stated generally. -/
def base : List Principle := sigMeanings ++ general ++ [pRevision]
def full : List Principle := base ++ clauses
def listed : List Principle := base ++ [decisionEntries, c1, c2, c3, c4Lapse]
def oldSet : List Principle := sigMeanings ++ general ++ [pRevision41] ++ clauses

def cellOuts (P : List Principle) (rd : Option Bool) (r : Rec) (s : Sig) (b : Bool) : List (Option Rec) :=
  outs.filter fun o => P.all fun p => p rd r s b o

def succsOver (A : List Sig) (P : List Principle) (rd : Option Bool) (r : Rec) : List Rec :=
  (A.map fun s => (bitsOf s).map fun b => (cellOuts P rd r s b).filterMap id).flatten.flatten

def reachOver (A : List Sig) (P : List Principle) (rd : Option Bool) : Nat → List Rec → List Rec
  | 0, acc => acc
  | n + 1, acc =>
      let nxt := (acc.map (succsOver A P rd)).flatten.foldl (fun a x => if a.contains x then a else a ++ [x]) acc
      if nxt.length == acc.length then acc else reachOver A P rd n nxt

def start : Rec := ⟨idle, false, false⟩
def reachable (P : List Principle) (rd : Option Bool) : List Rec := reachOver allSig P rd 12 [start]
def cells (P : List Principle) (rd : Option Bool) : List (Rec × Sig × Bool) :=
  ((reachable P rd).map fun r => (allSig.map fun s => (bitsOf s).map fun b => (r, s, b)).flatten).flatten
/-- Cells that do not admit exactly one outcome. -/
def notForced (P : List Principle) (rd : Option Bool) : List (Rec × Sig × Bool) :=
  (cells P rd).filter fun ⟨r, s, b⟩ => (cellOuts P rd r s b).length != 1
/-- The forced machine: each reachable cell with its outcome. -/
def machine (P : List Principle) (rd : Option Bool) : List ((Rec × Sig × Bool) × Option Rec) :=
  (cells P rd).map fun k => (k, (cellOuts P rd k.1 k.2.1 k.2.2).headD none)

def without (i : Nat) : List Principle := base ++ clauses.eraseIdx i
def readings : List (Option Bool) := [none, some true, some false]

/-! ### What is checked -/

/-- Under every reading of the lapse's owner, every reachable cell admits exactly one outcome. -/
theorem forced : readings.all (fun rd => (notForced full rd).length == 0) = true := by decide +kernel
/-- …and the lapse is never entered: the same 22 reachable records under each reading. -/
theorem never_lapses :
    readings.all (fun rd => (reachable full rd).length == 22 &&
      (reachable full rd).all (fun r => r.w != lapse)) = true := by decide +kernel
/-- ACCEPT is fatal (§11.4): without it no work, block or delivery record is reachable (C3). -/
theorem accept_fatal :
    (reachOver (allSig.filter (· != ACCEPT)) full none 12 [start]).all
      (fun r => !(r.w == work || r.w == W.block || r.w == deliv)) = true := by decide +kernel
theorem accept_is_the_way_in : (reachable full none).any (fun r => r.w == work) = true := by decide +kernel

end GFSO.LogLanguage
