/-
  GFSO — signal minimality of the protocol (§6.2).

  Canon `docs/applied_gfso_v3.md` §6.2 "Минимальность": removing any of the 12 P2P signals leaves
  a named defect. The signals partition by defect type into exactly:
    FM (5): CHALLENGE, BLOCK, ACCEPT_CHALLENGE, FAIL, CANCEL
    FSM deadlock (4): DELIVER, CANCEL_ACK, PASS, RESOLVE_BLOCK
    IC (2): ACCEPT, REJECT_CHALLENGE
    operation (1): ASSIGN
  "12 = минимум. Каждый адресует уникальный дефект."

  We can't prove "removal breaks the system" without a full behavioural model, but we CAN
  machine-check the canon's concrete claim: there are exactly 12 P2P signals, each maps to exactly
  one of four defect classes (a total function), all four classes are addressed (surjectivity), and
  the distribution is exactly 5/4/2/1. That is the checkable content of the minimality table.
  (The system-level "each removal deadlocks/opens an FM" lives in `Fsm.lean` for the FSM-deadlock
  four — `cancel_handshake_terminates`, `step_iff_admissible` — and in the FM basis for the rest.)
-/

namespace GFSO.Protocol

/-- The 12 peer-to-peer signals (§6.2). The system `TIMEOUT` trigger is NOT here — it is not a
    P2P signal (§6.2 "Механизм конечности"), it lives in the FSM finiteness sub-machine. -/
inductive P2PSignal
  | ASSIGN | ACCEPT | CHALLENGE | BLOCK | DELIVER | CANCEL_ACK
  | ACCEPT_CHALLENGE | REJECT_CHALLENGE | PASS | FAIL | CANCEL | RESOLVE_BLOCK
deriving DecidableEq, Repr

/-- The four kinds of defect a missing signal would cause (§6.2). -/
inductive DefectClass | FM | Deadlock | IC | Operation
deriving DecidableEq, Repr

open P2PSignal DefectClass

/-- The §6.2 minimality table: each signal ↦ the unique defect its removal causes. -/
def defectOf : P2PSignal → DefectClass
  | ASSIGN           => Operation   -- no initiation → protocol empty
  | ACCEPT           => IC          -- contract not fixed → later repudiation
  | CHALLENGE        => FM          -- FM-7: can't report a spec defect
  | BLOCK            => FM          -- FM-5/7: can't report a block
  | DELIVER          => Deadlock    -- stuck in EXECUTING
  | CANCEL_ACK       => Deadlock    -- stuck in CANCELLING
  | ACCEPT_CHALLENGE => FM          -- FM-5: spec never updated
  | REJECT_CHALLENGE => IC          -- CHALLENGE pointless without dispute resolution
  | PASS             => Deadlock    -- stuck in VALIDATING
  | FAIL             => FM          -- FM-3: all auto-pass → false validation
  | CANCEL           => FM          -- FM-5: stale tasks never cancelled
  | RESOLVE_BLOCK    => Deadlock    -- stuck in BLOCKED

/-- All 12 signals. -/
def allSignals : List P2PSignal :=
  [ASSIGN, ACCEPT, CHALLENGE, BLOCK, DELIVER, CANCEL_ACK,
   ACCEPT_CHALLENGE, REJECT_CHALLENGE, PASS, FAIL, CANCEL, RESOLVE_BLOCK]

/-- Exactly 12 signals (§6.2 "12 сигналов"). -/
theorem signals_count : allSignals.length = 12 := by decide

/-- The enumeration is exhaustive. -/
theorem mem_allSignals (s : P2PSignal) : s ∈ allSignals := by cases s <;> decide

/-- **The §6.2 distribution: 5 FM / 4 deadlock / 2 IC / 1 operation.** Machine-checked count. -/
theorem defect_distribution :
    (allSignals.countP (fun s => defectOf s == FM)) = 5 ∧
    (allSignals.countP (fun s => defectOf s == Deadlock)) = 4 ∧
    (allSignals.countP (fun s => defectOf s == IC)) = 2 ∧
    (allSignals.countP (fun s => defectOf s == Operation)) = 1 := by
  decide

/-- **Every defect class is addressed (§6.2: each signal addresses a unique defect kind).**
    `defectOf` is surjective onto the four classes — no protocol concern is left without a signal. -/
theorem defect_surjective : ∀ d : DefectClass, ∃ s : P2PSignal, defectOf s = d := by
  intro d; cases d
  · exact ⟨CHALLENGE, rfl⟩
  · exact ⟨DELIVER, rfl⟩
  · exact ⟨ACCEPT, rfl⟩
  · exact ⟨ASSIGN, rfl⟩

end GFSO.Protocol
