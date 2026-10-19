/-
  GFSO — signal minimality of the protocol (§11.4): the minimality table as data.

  Encoded: `defectOf`, each of the 12 P2P signals ↦ its primary type, "the defect its own removal row
  rests on" (§11.4); the second type FSM of ACCEPT, REJECT_CHALLENGE and FAIL is not encoded. Decided
  over this hand-entered table: exactly 12 signals, the typing total and onto the four classes, the
  distribution 4/4/3/1. NOT checked here: that removing a signal yields its defect, a claim about
  behaviour. Of the removals' grades, `FsmCanon.lean` decides on the canon's machine, catch-alls
  (`FsmCanon.isCatchAll`) aside, as far as §11.4 marks them machine-checked: the fatal ones, and of the
  sole-provider ones, FAIL aside, which content edges carry the source to the target, what only the signal
  provides being derived — per signal in the trailing comments of `defectOf`.
-/

namespace GFSO.Protocol

/-- The 12 peer-to-peer signals (§11.2). The system `TIMEOUT` trigger is not one: "a system
    mechanism, not a signal" (§12.2). -/
inductive P2PSignal
  | ASSIGN | ACCEPT | CHALLENGE | BLOCK | DELIVER | CONFIRM_CANCEL
  | ACCEPT_CHALLENGE | REJECT_CHALLENGE | PASS | FAIL | CANCEL | RESOLVE_BLOCK
deriving DecidableEq, Repr

/-- The four kinds of defect a missing signal would cause (§11.4). -/
inductive DefectClass | FM | FSM | IC | Operation
deriving DecidableEq, Repr

open P2PSignal DefectClass

/-- The §11.4 minimality table: each signal ↦ its primary type. Trailing comment: the theorem deciding
    its removal, in `FsmCanon` unless prefixed. -/
def defectOf : P2PSignal → DefectClass
  | ASSIGN           => Operation   -- fatal: `noAssign_strands_start`
  | ACCEPT           => IC          -- also FSM; fatal over the log, `LogLanguage.accept_fatal`
  | CHALLENGE        => FM          -- FM-1/2; fatal: `noChallenge_strands_challenged`
  | BLOCK            => FM          -- FM-5; fatal: `noBlock_strands_blocked`
  | DELIVER          => FSM         -- fatal: `nodeliver_strands_done`
  | CONFIRM_CANCEL   => FSM         -- `noConfirm_only_timeout_into_abandoned`; Inv-8: `noConfirm_breaks_inv8`
  | ACCEPT_CHALLENGE => IC          -- `acceptChallenge_sole_content_reoffer`
  | REJECT_CHALLENGE => IC          -- also FSM; `rejectChallenge_sole_content_resume`
  | PASS             => FSM         -- fatal: `noPass_strands_done`
  | FAIL             => FM          -- FM-3, also FSM; its grade witnessed by no theorem
  | CANCEL           => FM          -- FM-5; `noCancel_leaves_only_the_silence`
  | RESOLVE_BLOCK    => FSM         -- `resolveBlock_sole_content_resume`

/-- All 12 signals. -/
def allSignals : List P2PSignal :=
  [ASSIGN, ACCEPT, CHALLENGE, BLOCK, DELIVER, CONFIRM_CANCEL,
   ACCEPT_CHALLENGE, REJECT_CHALLENGE, PASS, FAIL, CANCEL, RESOLVE_BLOCK]

/-- Exactly 12 signals (§11.2: "The protocol has 12 signals"). -/
theorem signals_count : allSignals.length = 12 := by decide

/-- The enumeration is exhaustive. -/
theorem mem_allSignals (s : P2PSignal) : s ∈ allSignals := by cases s <;> decide

/-- **The §11.4 distribution: 4 FM / 4 FSM / 3 IC / 1 operation.** Machine-checked count. -/
theorem defect_distribution :
    (allSignals.countP (fun s => defectOf s == FM)) = 4 ∧
    (allSignals.countP (fun s => defectOf s == FSM)) = 4 ∧
    (allSignals.countP (fun s => defectOf s == IC)) = 3 ∧
    (allSignals.countP (fun s => defectOf s == Operation)) = 1 := by
  decide

/-- **Every defect class is addressed:** `defectOf` is onto the four classes. -/
theorem defect_surjective : ∀ d : DefectClass, ∃ s : P2PSignal, defectOf s = d := by
  intro d; cases d
  · exact ⟨CHALLENGE, rfl⟩
  · exact ⟨DELIVER, rfl⟩
  · exact ⟨ACCEPT, rfl⟩
  · exact ⟨ASSIGN, rfl⟩

end GFSO.Protocol
