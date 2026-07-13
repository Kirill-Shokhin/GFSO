/-
  GFSO — HEAVY spike target: the protocol FSM (§6.3) — totality + determinism.
  Canon `docs/applied_gfso_v3.md` §6.2 (12 signals + system TIMEOUT), §6.3 (the 12-state
  automaton), §6.4 (Инв-5 finiteness, Инв-6 determinism). Ground truth for the transition
  table = `gfso/core/protocol/fsm.py` (states/signals/rows/catch-alls cross-checked verbatim).

  Everything below is finite; results are discharged by `decide` (kernel exhaustion of the
  State×Signal product) or hold definitionally. No mathlib needed.
-/

namespace GFSO.Fsm

/-- The 12 protocol states (§6.3, `enums.py::State`). -/
inductive St
  | IDLE | REVIEW | CHALLENGED | EXECUTING | BLOCKED | VALIDATING | REWORK
  | CANCELLING | DONE | CANCELLED | TIMEOUT | ESCALATED
deriving DecidableEq, Repr

/-- The 12 P2P signals + the system TIMEOUT trigger (§6.2, `enums.py::Signal`). 13 total. -/
inductive Sig
  | ACCEPT | CHALLENGE | BLOCK | DELIVER | CANCEL_ACK           -- Executor → Issuer
  | ASSIGN | ACCEPT_CHALLENGE | REJECT_CHALLENGE | PASS | FAIL | CANCEL | RESOLVE_BLOCK  -- Issuer → Executor
  | TIMEOUT                                                     -- system finiteness trigger
deriving DecidableEq, Repr

open St Sig

/-- Terminal states (§6.3: DONE, CANCELLED, ESCALATED). -/
def isTerminal : St → Bool
  | DONE | CANCELLED | ESCALATED => true
  | _ => false

/-- Reassignable states (§6.4 Инв-1: re-ASSIGN under the same id → REVIEW). Mirrors
    `enums.py::REASSIGNABLE_STATES` (all non-terminals except IDLE, CANCELLING, TIMEOUT). -/
def isReassignable : St → Bool
  | REVIEW | CHALLENGED | EXECUTING | BLOCKED | VALIDATING | REWORK => true
  | _ => false

/--
THE transition function (§6.3), a faithful port of `fsm.py::transition` + `_LOOKUP` + the
catch-alls (universal CANCEL for non-terminals≠CANCELLING; re-ASSIGN for reassignable states).
Written as an explicit per-state matcher (so it reduces in the kernel for `decide`).
`canRework : Bool` = the sole dynamic guard (VALIDATING+FAIL: iteration < max ⇒ REWORK, else
DONE(fail); `fsm.py` line 163), lifted into the function's INPUT — see `step_deterministic`.
`none` = signal not admissible in this state.
-/
def step (s : St) (sig : Sig) (canRework : Bool) : Option St :=
  match s with
  | IDLE => match sig with
    | ASSIGN => some REVIEW
    | CANCEL => some CANCELLING            -- IDLE ∈ non-terminals, ≠ CANCELLING ⇒ CANCEL catch-all
    | _ => none
  | REVIEW => match sig with
    | ACCEPT => some EXECUTING
    | CHALLENGE => some CHALLENGED
    | Sig.TIMEOUT => some St.TIMEOUT
    | CANCEL => some CANCELLING
    | ASSIGN => some REVIEW               -- re-ASSIGN (revision, Инв-1)
    | _ => none
  | CHALLENGED => match sig with
    | ACCEPT_CHALLENGE => some REVIEW
    | REJECT_CHALLENGE => some EXECUTING
    | Sig.TIMEOUT => some St.TIMEOUT
    | CANCEL => some CANCELLING
    | ASSIGN => some REVIEW
    | _ => none
  | EXECUTING => match sig with
    | DELIVER => some VALIDATING
    | BLOCK => some BLOCKED
    | Sig.TIMEOUT => some St.TIMEOUT
    | CANCEL => some CANCELLING
    | ASSIGN => some REVIEW
    | _ => none
  | BLOCKED => match sig with
    | RESOLVE_BLOCK => some EXECUTING
    | Sig.TIMEOUT => some ESCALATED           -- direct-to-terminal (block IS escalation)
    | CANCEL => some CANCELLING
    | ASSIGN => some REVIEW
    | _ => none
  | VALIDATING => match sig with
    | PASS => some DONE
    | FAIL => some (if canRework then REWORK else DONE)  -- guarded (fsm.py:163)
    | Sig.TIMEOUT => some DONE                -- direct auto-pass (§16.7)
    | CANCEL => some CANCELLING
    | ASSIGN => some REVIEW
    | _ => none
  | REWORK => match sig with
    | DELIVER => some VALIDATING
    | BLOCK => some BLOCKED
    | Sig.TIMEOUT => some St.TIMEOUT
    | CANCEL => some CANCELLING
    | ASSIGN => some REVIEW
    | _ => none
  | CANCELLING => match sig with          -- sole staffed exit = CANCEL_ACK; no CANCEL/ASSIGN catch-all
    | CANCEL_ACK => some CANCELLED
    | Sig.TIMEOUT => some CANCELLED            -- direct (cancellation is authoritative)
    | _ => none
  | St.TIMEOUT => match sig with          -- accepts no progress signals; only re-timeout or CANCEL
    | Sig.TIMEOUT => some ESCALATED
    | CANCEL => some CANCELLING
    | _ => none
  | DONE => none
  | CANCELLED => none
  | ESCALATED => none

/-- The declared admissible-signal set per state (mirrors `fsm.py::available_signals`:
    the table rows + universal CANCEL for non-terminals≠CANCELLING + re-ASSIGN for
    reassignable states). This is what Инв-6 calls "the admissible set defined in each state". -/
def admissible : St → List Sig
  | IDLE        => [ASSIGN, CANCEL]
  | REVIEW      => [ACCEPT, CHALLENGE, TIMEOUT, CANCEL, ASSIGN]
  | CHALLENGED  => [ACCEPT_CHALLENGE, REJECT_CHALLENGE, TIMEOUT, CANCEL, ASSIGN]
  | EXECUTING   => [DELIVER, BLOCK, TIMEOUT, CANCEL, ASSIGN]
  | BLOCKED     => [RESOLVE_BLOCK, TIMEOUT, CANCEL, ASSIGN]
  | VALIDATING  => [PASS, FAIL, TIMEOUT, CANCEL, ASSIGN]
  | REWORK      => [DELIVER, BLOCK, TIMEOUT, CANCEL, ASSIGN]
  | CANCELLING  => [CANCEL_ACK, TIMEOUT]
  | St.TIMEOUT  => [TIMEOUT, CANCEL]
  | DONE        => []
  | CANCELLED   => []
  | ESCALATED   => []

-- Finite enumerations (used to lift `decide`-checks to genuine ∀ statements).

def allSt : List St :=
  [IDLE, REVIEW, CHALLENGED, EXECUTING, BLOCKED, VALIDATING, REWORK,
   CANCELLING, DONE, CANCELLED, TIMEOUT, ESCALATED]

def allSig : List Sig :=
  [ACCEPT, CHALLENGE, BLOCK, DELIVER, CANCEL_ACK, ASSIGN, ACCEPT_CHALLENGE,
   REJECT_CHALLENGE, PASS, FAIL, CANCEL, RESOLVE_BLOCK, TIMEOUT]

theorem mem_allSt (s : St) : s ∈ allSt := by cases s <;> decide
theorem mem_allSig (g : Sig) : g ∈ allSig := by cases g <;> decide

/-! ### Инв-6 — determinism -/

/-- **Determinism (Инв-6).** For a fixed (state, signal, guard) the transition is unique.
    This holds DEFINITIONALLY: `step` is a total function, so it cannot return two results.
    HONEST NUANCE: determinism is trivial *because* we lifted the only dynamic branch (the
    VALIDATING+FAIL iteration guard, `fsm.py:163`) into the input `canRework`. In the running
    system that bit is read from `GuardContext`; encoding it as a function argument is the
    faithful move — it makes explicit that the transition is a function of (state, signal, guard),
    which is exactly what Инв-6 asserts ("the admissible set is defined in each state"). -/
theorem step_deterministic (s : St) (sig : Sig) (g : Bool) {t₁ t₂ : Option St}
    (h₁ : step s sig g = t₁) (h₂ : step s sig g = t₂) : t₁ = t₂ := by
  rw [← h₁, ← h₂]

/-- **Admissible-set correctness (Инв-6, the non-trivial half).** A signal moves the FSM iff
    it is in the declared admissible set — the transition table and `admissible` agree on
    exactly which (state, signal) pairs are live. Discharged by `decide` over State×Signal×guard. -/
theorem step_iff_admissible_check :
    allSt.all (fun s => allSig.all (fun g => [false, true].all (fun b =>
        (step s g b).isSome == decide (g ∈ admissible s)))) = true := by decide

theorem step_iff_admissible (s : St) (g : Sig) (b : Bool) :
    (step s g b).isSome = decide (g ∈ admissible s) := by
  have h1 := List.all_eq_true.mp step_iff_admissible_check s (mem_allSt s)
  have h2 := List.all_eq_true.mp h1 g (mem_allSig g)
  have h3 := List.all_eq_true.mp h2 b (by cases b <;> decide)
  exact eq_of_beq h3

/-! ### Инв-5 — finiteness / totality -/

/-- Every non-terminal state EXCEPT `IDLE` has a defined TIMEOUT transition (§6.2 finiteness
    mechanism). `decide`-checked over all states. IDLE is the documented exception — see
    `idle_has_no_timeout` and the divergence note in `formal/README.md`. -/
theorem timeout_defined_check :
    allSt.all (fun s => isTerminal s || (s == IDLE) || (step s TIMEOUT false).isSome) = true := by decide

theorem timeout_defined (s : St) (h₁ : isTerminal s = false) (h₂ : s ≠ IDLE) :
    (step s TIMEOUT false).isSome = true := by
  have h := List.all_eq_true.mp timeout_defined_check s (mem_allSt s)
  simp only [Bool.or_eq_true] at h
  rcases h with (h | h) | h
  · simp [h₁] at h
  · exact absurd (eq_of_beq h) h₂
  · exact h

/-- The state reached by the system TIMEOUT trigger (IDLE and terminals are fixpoints:
    IDLE has no deadline running; terminals absorb). -/
def timeoutStep : St → St
  | REVIEW | CHALLENGED | EXECUTING | REWORK => TIMEOUT   -- first timeout → intermediate TIMEOUT
  | BLOCKED => ESCALATED
  | VALIDATING => DONE
  | CANCELLING => CANCELLED
  | St.TIMEOUT => ESCALATED                               -- second timeout → terminal
  | s => s                                                -- IDLE + terminals: fixpoint

/-- **Finiteness / termination (Инв-5).** From EVERY non-terminal state except IDLE, at most
    TWO system timeouts drive the FSM into a terminal state — the deadline path cannot stall.
    This is the real content of Инв-5 (finiteness of every non-terminal). `decide`-checked. -/
theorem timeout_terminates_check :
    allSt.all (fun s =>
        isTerminal s || (s == IDLE) || isTerminal (timeoutStep (timeoutStep s))) = true := by decide

theorem timeout_terminates (s : St) (h₁ : isTerminal s = false) (h₂ : s ≠ IDLE) :
    isTerminal (timeoutStep (timeoutStep s)) = true := by
  have h := List.all_eq_true.mp timeout_terminates_check s (mem_allSt s)
  simp only [Bool.or_eq_true] at h
  rcases h with (h | h) | h
  · simp [h₁] at h
  · exact absurd (eq_of_beq h) h₂
  · exact h

/-- `timeoutStep` agrees with `step … TIMEOUT` wherever the latter is defined (sanity tie
    between the two encodings; `decide`-checked). -/
theorem timeoutStep_matches_check :
    allSt.all (fun s =>
        !(step s TIMEOUT false).isSome || (step s TIMEOUT false == some (timeoutStep s))) = true := by
  decide

/-- CODE↔CANON DIVERGENCE (flagged, not hidden): IDLE has NO timeout transition in `fsm.py`
    (no row, no catch-all), yet IDLE is listed as a non-terminal state in §6.3 and Инв-5 asks
    that *every* non-terminal be finite. Provable directly. See README §divergence. -/
theorem idle_has_no_timeout : step IDLE TIMEOUT false = none := by decide

/-! ### Инв-1 — revision (re-ASSIGN) is NOT cancellation (§6.3, §6.4)

The canon's v3.7 subtlety: a revision changes a live node's contract via **re-ASSIGN under the
same id**, sending it to REVIEW (executor must re-ACCEPT/CHALLENGE) — it does NOT cascade or
cancel. Cancellation is a separate two-step handshake. Both are provable on the automaton. -/

/-- **Инв-1 (revision).** From every reassignable state, re-ASSIGN returns the node to REVIEW
    under its stable id — the executor is not silently bound to the new contract. -/
theorem reassign_to_review (s : St) (h : isReassignable s = true) :
    step s ASSIGN false = some REVIEW := by
  cases s <;> simp_all [step, isReassignable]

/-! ### Cancellation is a completing two-step handshake (§6.3), mirror of ASSIGN→ACCEPT -/

/-- CANCEL from any non-terminal (except CANCELLING itself) opens the handshake → CANCELLING. -/
theorem cancel_initiates (s : St) (hnt : isTerminal s = false) (hc : s ≠ CANCELLING) :
    step s CANCEL false = some CANCELLING := by
  cases s <;> simp_all [step, isTerminal]

/-- CANCEL_ACK closes it → CANCELLED (the sole staffed exit of CANCELLING). -/
theorem cancel_ack_completes : step CANCELLING CANCEL_ACK false = some CANCELLED := by decide

/-- …and CANCELLED is terminal — so the cancellation handshake always *completes* (no deadlock):
    every non-terminal ≠ CANCELLING reaches a terminal in exactly two signals. -/
theorem cancel_handshake_terminates (s : St) (hnt : isTerminal s = false) (hc : s ≠ CANCELLING) :
    step s CANCEL false = some CANCELLING ∧
    step CANCELLING CANCEL_ACK false = some CANCELLED ∧
    isTerminal CANCELLED = true :=
  ⟨cancel_initiates s hnt hc, cancel_ack_completes, by decide⟩

end GFSO.Fsm
