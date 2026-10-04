/-
  GFSO — the engine's conformance mirror of the protocol machine (§12.4): totality and determinism.
  The NAMES are the canon's (§11.2, §12.1, §12.2). The TRANSITION TABLE is `gfso/core/protocol/fsm.py`'s
  (rows, catch-alls and guards cross-checked verbatim, read 2026-09-25), so a change to the engine's
  shape shows up here as a broken proof. Its agreement with the canon's table (`FsmCanon.canonStep`) is
  `FsmCanon.mirror_agrees_with_canon`; `tests/test_model_conformance.py` compares `fsm.py` with
  `formal/tla/FsmTable.tla` on every cell, both sides of every guard.

  THE v4.1 CELLS, all now in `fsm.py`:
    * (OFFERED | CHALLENGED | EXECUTING | REWORKING, TIMEOUT) → ESCALATED, OVERDUE removed
      (`enums.py::RETIRED_STATES` maps a stored OVERDUE to ESCALATED);
    * (CHALLENGED, REJECT_CHALLENGE, b) → OFFERED at b = false, EXECUTING at b = true, the consent
      datum being the step function's Bool input `b` (`fsm.py`: `ctx.consented`);
    * (EXECUTING | REWORKING, CHALLENGE) → CHALLENGED (C-1) and (VALIDATING, TIMEOUT) → ESCALATED
      (auto_pass removed);
    * the reassignable set: every non-terminal except IDLE and CANCELLING
      (= `enums.py::REASSIGNABLE_STATES`).
  The constructor `St.OVERDUE` is no canon state and no engine state. It stays because `Forcing.lean`'s
  frozen table (`step41`) routes through it and `LogLanguageAgrees` maps the lapse record to it; here
  its row is empty and no cell enters it (`no_cell_enters_overdue`).

  Not modelled: on the exhausted rework loop `(VALIDATING, FAIL, iteration ≥ max)` → ESCALATED
  (`README.md` corner #3) the engine records the consumed FAIL on the node. `step` is a state function
  and the settlement reason is graph data — the abstraction under which ABANDONED by CANCEL and by
  silence share one constructor.

  Everything below is finite; results are discharged by `decide` (kernel exhaustion of the
  State×Signal product) or hold definitionally. No mathlib needed.
-/

namespace GFSO.Fsm

/-- §12.1's eleven states (`enums.py::State`) plus the off-table OVERDUE (header); the canon-side list
    without it is `FsmCanon.canonSt`. -/
inductive St
  | IDLE | OFFERED | CHALLENGED | EXECUTING | BLOCKED | VALIDATING | REWORKING
  | CANCELLING | DONE | ABANDONED | OVERDUE | ESCALATED
deriving DecidableEq, Repr

/-- The 12 P2P signals + the system trigger `Sig.TIMEOUT` (§11.2, §12.2, `enums.py::Signal`). 13 total. -/
inductive Sig
  | ACCEPT | CHALLENGE | BLOCK | DELIVER | CONFIRM_CANCEL           -- Executor → Issuer
  | ASSIGN | ACCEPT_CHALLENGE | REJECT_CHALLENGE | PASS | FAIL | CANCEL | RESOLVE_BLOCK  -- Issuer → Executor
  | TIMEOUT                                                     -- system finiteness trigger
deriving DecidableEq, Repr

open St Sig

/-- Terminal states (§12.1): DONE, ABANDONED. ESCALATED is non-terminal — the issuer's decision (§12.5). -/
def isTerminal : St → Bool
  | DONE | ABANDONED => true
  | _ => false

/-- Reassignable states (§12.3): every canon non-terminal except IDLE and CANCELLING; as a set
    `enums.py::REASSIGNABLE_STATES`. -/
def isReassignable : St → Bool
  | OFFERED | CHALLENGED | EXECUTING | BLOCKED | VALIDATING | REWORKING => true
  -- …and ESCALATED, where re-ASSIGN is the issuer's continuing move (§12.5).
  | ESCALATED => true
  | _ => false

/--
THE transition function (§12.4), a port of `fsm.py::transition` + `_LOOKUP` + the catch-alls
(universal CANCEL for non-terminals ≠ CANCELLING; re-ASSIGN for reassignable states), written as an
explicit per-state matcher so it reduces in the kernel for `decide`.
`b : Bool` = the one state-resident datum the table reads, lifted into the INPUT (see
`step_deterministic`): at FAIL, rounds remain (iteration < max ⇒ REWORKING, else ESCALATED); at
REJECT_CHALLENGE, consent (an ACCEPT) is logged on the current packet version (`ctx.consented`);
ignored elsewhere. `none` = signal not admissible in this state.
-/
def step (s : St) (sig : Sig) (b : Bool) : Option St :=
  match s with
  | IDLE => match sig with
    | ASSIGN => some OFFERED
    | CANCEL => some CANCELLING            -- IDLE ∈ non-terminals, ≠ CANCELLING ⇒ CANCEL catch-all
    | _ => none
  | OFFERED => match sig with
    | ACCEPT => some EXECUTING
    | CHALLENGE => some CHALLENGED
    | Sig.TIMEOUT => some ESCALATED           -- v4.1
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED               -- re-ASSIGN (revision, Inv-1)
    | _ => none
  | CHALLENGED => match sig with
    | ACCEPT_CHALLENGE => some OFFERED
    | REJECT_CHALLENGE => some (if b then EXECUTING else OFFERED)  -- v4.1: the interrupted wait
    | Sig.TIMEOUT => some ESCALATED           -- v4.1
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | EXECUTING => match sig with
    | DELIVER => some VALIDATING
    | BLOCK => some BLOCKED
    | CHALLENGE => some CHALLENGED            -- v4.1 (C-1)
    | Sig.TIMEOUT => some ESCALATED           -- v4.1
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
    | FAIL => some (if b then REWORKING else ESCALATED)  -- guarded: `b` = rounds remain
    | Sig.TIMEOUT => some ESCALATED           -- v4.1
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | REWORKING => match sig with
    | DELIVER => some VALIDATING
    | BLOCK => some BLOCKED
    | CHALLENGE => some CHALLENGED            -- v4.1 (C-1)
    | Sig.TIMEOUT => some ESCALATED           -- v4.1
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | CANCELLING => match sig with          -- no CANCEL / re-ASSIGN catch-all here
    | CONFIRM_CANCEL => some ABANDONED
    | Sig.TIMEOUT => some ABANDONED
    | _ => none
  | OVERDUE => none                    -- no canon state (header)
  -- DONE/ABANDONED: R′'s REOPEN (§12.14), which `fsm.py` admits under its gate, is NOT encoded — the
  -- gate is a predicate over the GRAPH, outside this per-node signature, so this is the base machine's
  -- terminal-absorbing table. The reopen edge is TLC-checked (formal/tla/FsmSpike.tla: WaitsEnd,
  -- NoOwnerlessDivergence, FinalityAbsorbing) and the gate code-tested (tests/test_reopen.py).
  | DONE => none
  | ABANDONED => none
  -- ESCALATED: the issuer's two moves and his silence (§12.5).
  | ESCALATED =>
    match sig with
    | ASSIGN => some OFFERED                  -- continue: re-ASSIGN (Inv-1)
    | CANCEL => some CANCELLING               -- close
    | Sig.TIMEOUT => some CANCELLING           -- silence takes the closing's path
    | _ => none

/-- The declared admissible-signal set per state (`fsm.py::available_signals`: the table rows +
    universal CANCEL for non-terminals ≠ CANCELLING + re-ASSIGN for reassignable states) — Inv-6's
    admissible set. -/
def admissible : St → List Sig
  | IDLE        => [ASSIGN, CANCEL]
  | OFFERED     => [ACCEPT, CHALLENGE, TIMEOUT, CANCEL, ASSIGN]
  | CHALLENGED  => [ACCEPT_CHALLENGE, REJECT_CHALLENGE, TIMEOUT, CANCEL, ASSIGN]
  | EXECUTING   => [DELIVER, BLOCK, CHALLENGE, TIMEOUT, CANCEL, ASSIGN]
  | BLOCKED     => [RESOLVE_BLOCK, TIMEOUT, CANCEL, ASSIGN]
  | VALIDATING  => [PASS, FAIL, TIMEOUT, CANCEL, ASSIGN]
  | REWORKING   => [DELIVER, BLOCK, CHALLENGE, TIMEOUT, CANCEL, ASSIGN]
  | CANCELLING  => [CONFIRM_CANCEL, TIMEOUT]
  | OVERDUE     => []
  | DONE        => []
  | ABANDONED   => []
  | ESCALATED   => [ASSIGN, CANCEL, TIMEOUT]

-- Finite enumerations (used to lift `decide`-checks to genuine ∀ statements).

def allSt : List St :=
  [IDLE, OFFERED, CHALLENGED, EXECUTING, BLOCKED, VALIDATING, REWORKING,
   CANCELLING, DONE, ABANDONED, OVERDUE, ESCALATED]

def allSig : List Sig :=
  [ACCEPT, CHALLENGE, BLOCK, DELIVER, CONFIRM_CANCEL, ASSIGN, ACCEPT_CHALLENGE,
   REJECT_CHALLENGE, PASS, FAIL, CANCEL, RESOLVE_BLOCK, TIMEOUT]

theorem mem_allSt (s : St) : s ∈ allSt := by cases s <;> decide
theorem mem_allSig (g : Sig) : g ∈ allSig := by cases g <;> decide

/-! ### Inv-6 — determinism -/

/-- **Determinism (Inv-6).** Definitional: `step` is a total function. It is trivial BECAUSE the only
    dynamic branches — the VALIDATING+FAIL iteration guard and the REJECT_CHALLENGE consent datum — are
    lifted into the input `b`; the running system reads the first from `GuardContext` and the second off
    the log. The lift makes explicit that the transition is a function of (state, signal, guard). -/
theorem step_deterministic (s : St) (sig : Sig) (g : Bool) {t₁ t₂ : Option St}
    (h₁ : step s sig g = t₁) (h₂ : step s sig g = t₂) : t₁ = t₂ := by
  rw [← h₁, ← h₂]

/-- **Admissible-set correctness (Inv-6, the non-trivial half).** A signal moves the FSM iff
    it is in `admissible`. Discharged by `decide` over State×Signal×guard. -/
theorem step_iff_admissible_check :
    allSt.all (fun s => allSig.all (fun g => [false, true].all (fun b =>
        (step s g b).isSome == decide (g ∈ admissible s)))) = true := by decide

theorem step_iff_admissible (s : St) (g : Sig) (b : Bool) :
    (step s g b).isSome = decide (g ∈ admissible s) := by
  have h1 := List.all_eq_true.mp step_iff_admissible_check s (mem_allSt s)
  have h2 := List.all_eq_true.mp h1 g (mem_allSig g)
  have h3 := List.all_eq_true.mp h2 b (by cases b <;> decide)
  exact eq_of_beq h3

/-! ### Inv-5 — finiteness / totality -/

/-- OVERDUE is off the table: its row is empty and no cell, at either value of `b`, enters it — so the
    statements below that exempt it exempt a state the table never visits. -/
theorem no_cell_enters_overdue :
    allSt.all (fun s => allSig.all (fun g => [false, true].all (fun b =>
      step s g b != some OVERDUE))) = true := by decide

theorem overdue_row_empty :
    allSig.all (fun g => [false, true].all (fun b => (step OVERDUE g b).isNone)) = true := by decide

/-- Every non-terminal state except `IDLE` (and the off-table OVERDUE) has a TIMEOUT transition — Inv-5's
    first sentence (§12.12), IDLE exempt by name (`idle_has_no_timeout`). -/
theorem timeout_defined_check :
    allSt.all (fun s => isTerminal s || (s == IDLE) || (s == OVERDUE)
      || (step s TIMEOUT false).isSome) = true := by decide

theorem timeout_defined (s : St) (h₁ : isTerminal s = false) (h₂ : s ≠ IDLE) (h₃ : s ≠ OVERDUE) :
    (step s TIMEOUT false).isSome = true := by
  have h := List.all_eq_true.mp timeout_defined_check s (mem_allSt s)
  simp only [Bool.or_eq_true] at h
  rcases h with ((h | h) | h) | h
  · simp [h₁] at h
  · exact absurd (eq_of_beq h) h₂
  · exact absurd (eq_of_beq h) h₃
  · exact h

/-- The state the system TIMEOUT reaches; IDLE, the off-table OVERDUE and the terminals are fixpoints. -/
def timeoutStep : St → St
  | OFFERED | CHALLENGED | EXECUTING | REWORKING => ESCALATED
  | BLOCKED => ESCALATED
  | VALIDATING => ESCALATED
  | CANCELLING => ABANDONED
  | ESCALATED => CANCELLING
  | s => s                                   -- IDLE, OVERDUE (off-table), terminals: fixpoint

/-- **Timeout chains end (Inv-5, per node).** From every non-terminal state except IDLE (and the
    off-table OVERDUE), at most THREE consecutive timeouts reach a terminal; the longest chain is
    OFFERED → ESCALATED → CANCELLING → ABANDONED. SCOPE: pure timeout chains. Runs interleaving signals
    (a re-ASSIGN out of ESCALATED restarts the chain) are the TLA+ layer's (`formal/tla`: `WaitsEnd`,
    `NoOwnerlessDivergence`). -/
theorem timeout_terminates_check :
    allSt.all (fun s =>
        isTerminal s || (s == IDLE) || (s == OVERDUE)
        || isTerminal (timeoutStep (timeoutStep (timeoutStep s)))) = true := by decide

theorem timeout_terminates (s : St) (h₁ : isTerminal s = false) (h₂ : s ≠ IDLE) (h₃ : s ≠ OVERDUE) :
    isTerminal (timeoutStep (timeoutStep (timeoutStep s))) = true := by
  have h := List.all_eq_true.mp timeout_terminates_check s (mem_allSt s)
  simp only [Bool.or_eq_true] at h
  rcases h with ((h | h) | h) | h
  · simp [h₁] at h
  · exact absurd (eq_of_beq h) h₂
  · exact absurd (eq_of_beq h) h₃
  · exact h

/-- …and three is tight: two timeouts from OFFERED leave the node in CANCELLING, still live. -/
theorem timeout_bound_tight : isTerminal (timeoutStep (timeoutStep OFFERED)) = false := by decide

/-- `timeoutStep` agrees with `step … TIMEOUT` wherever the latter is defined (sanity tie
    between the two encodings; `decide`-checked). -/
theorem timeoutStep_matches_check :
    allSt.all (fun s =>
        !(step s TIMEOUT false).isSome || (step s TIMEOUT false == some (timeoutStep s))) = true := by
  decide

/-- IDLE: "every non-terminal state **except IDLE** has a timeout" (§12.12). The engine agrees:
    `fsm.py` carries no `(IDLE, TIMEOUT)` row, a test pinning its absence (checked 2026-09-21;
    `formal/README.md` corner #1). -/
theorem idle_has_no_timeout : step IDLE TIMEOUT false = none := by decide

/-! ### Inv-1 — revision (re-ASSIGN) is not cancellation (§12.3, §12.10) -/

/-- **Inv-1 (revision).** From every reassignable state, re-ASSIGN returns the node to OFFERED. -/
theorem reassign_to_offered (s : St) (h : isReassignable s = true) :
    step s ASSIGN false = some OFFERED := by
  cases s <;> simp_all [step, isReassignable]

/-! ### Cancellation is a completing two-step handshake (§12.6) -/

/-- CANCEL from any non-terminal (except CANCELLING itself, and the off-table OVERDUE) opens the
    handshake → CANCELLING. -/
theorem cancel_initiates (s : St) (hnt : isTerminal s = false) (hc : s ≠ CANCELLING)
    (ho : s ≠ OVERDUE) :
    step s CANCEL false = some CANCELLING := by
  cases s <;> simp_all [step, isTerminal]

/-- CONFIRM_CANCEL closes it → ABANDONED. -/
theorem confirm_cancel_completes : step CANCELLING CONFIRM_CANCEL false = some ABANDONED := by decide

/-- …and ABANDONED is terminal: every non-terminal ≠ CANCELLING (OVERDUE off-table) reaches a terminal
    in exactly two signals. -/
theorem cancel_handshake_terminates (s : St) (hnt : isTerminal s = false) (hc : s ≠ CANCELLING)
    (ho : s ≠ OVERDUE) :
    step s CANCEL false = some CANCELLING ∧
    step CANCELLING CONFIRM_CANCEL false = some ABANDONED ∧
    isTerminal ABANDONED = true :=
  ⟨cancel_initiates s hnt hc ho, confirm_cancel_completes, by decide⟩

end GFSO.Fsm
