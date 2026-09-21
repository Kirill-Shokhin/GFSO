/-
  GFSO — HEAVY spike target: the protocol FSM (§14.3) — totality + determinism.
  Canon `docs/applied_gfso_v4_en.md` §14.2 (12 signals + system TIMEOUT), §14.3 (the 12-state
  automaton), §14.4 (Inv-5 finiteness, Inv-6 determinism). Ground truth for the transition
  table = `gfso/core/protocol/fsm.py` (rows/catch-alls/guards cross-checked verbatim).

  WHAT THIS FILE IS, exactly — the two are not the same claim, and where they diverge this file
  follows the CODE and the divergence is FLAGGED, never silently reconciled:
    * the NAMES are the canon's (see NAMES below);
    * the TRANSITION TABLE is `fsm.py`'s. It is a conformance mirror of the engine, so that a change
      to the engine's shape shows up here as a broken proof rather than as prose drift.
  The row that used to diverge here — `(VALIDATING, FAIL, iteration ≥ max)` — is CLOSED: the engine
  now routes the exhausted rework loop to ESCALATED, as canon §14.3 does and as §12.2 requires
  ("DONE is reached through acceptance (PASS ∨ auto_pass), never through fail"), so mirror and canon
  agree on it and the proofs below carry the canon's shape rather than a flagged gap (corner #3 in
  `README.md`, resolved). The engine additionally carries the verdict onto that terminal, which this
  per-node signature does not model: `step` is a state function, and the settlement REASON is graph
  data — the same abstraction under which DONE(pass)/DONE(auto) share one constructor here.

  NAMES: canon and code now spell the states the same way — the enum migration landed, so the
  v3.9→v4.0 lag this banner used to declare is gone and the constructors below are simultaneously
  the canon's names and `enums.py`'s. (The system trigger `Sig.TIMEOUT` keeps its name in both —
  the canon renamed the STATE only, which is what removes the old Signal↔State homograph.)

  Everything below is finite; results are discharged by `decide` (kernel exhaustion of the
  State×Signal product) or hold definitionally. No mathlib needed.
-/

namespace GFSO.Fsm

/-- The 12 protocol states (§14.3, `enums.py::State`). -/
inductive St
  | IDLE | OFFERED | CHALLENGED | EXECUTING | BLOCKED | VALIDATING | REWORKING
  | CANCELLING | DONE | ABANDONED | OVERDUE | ESCALATED
deriving DecidableEq, Repr

/-- The 12 P2P signals + the system TIMEOUT trigger (§14.2, `enums.py::Signal`). 13 total. -/
inductive Sig
  | ACCEPT | CHALLENGE | BLOCK | DELIVER | CONFIRM_CANCEL           -- Executor → Issuer
  | ASSIGN | ACCEPT_CHALLENGE | REJECT_CHALLENGE | PASS | FAIL | CANCEL | RESOLVE_BLOCK  -- Issuer → Executor
  | TIMEOUT                                                     -- system finiteness trigger
deriving DecidableEq, Repr

open St Sig

/-- Terminal states (§14.3: DONE, ABANDONED).

    ESCALATED is NOT one. Terminal means the WORK IS OVER — accepted (DONE) or refused by
    authority (ABANDONED, V = ⊥). ESCALATED is the ISSUER's waiting state (§14.3-bis): the
    executor's contract ended and the issuer's decision begins, which is a HANDOVER and not a
    settlement. Inv-4 forces it — the machine has a state where the EXECUTOR owes an answer
    (OFFERED) and, the two parties being equally accountable, must have its mirror. -/
def isTerminal : St → Bool
  | DONE | ABANDONED => true
  | _ => false

/-- Reassignable states (§14.4 Inv-1: re-ASSIGN under the same id → OFFERED). Mirrors
    `enums.py::REASSIGNABLE_STATES` (all non-terminals except IDLE, CANCELLING, OVERDUE). -/
def isReassignable : St → Bool
  | OFFERED | CHALLENGED | EXECUTING | BLOCKED | VALIDATING | REWORKING => true
  -- …and ESCALATED: a revision there is the ISSUER answering the question the protocol put to him
  -- (§14.3-bis). OVERDUE stays out — there the miss has not been handed to anyone yet.
  | ESCALATED => true
  | _ => false

/--
THE transition function (§14.3), a faithful port of `fsm.py::transition` + `_LOOKUP` + the
catch-alls (universal CANCEL for non-terminals≠CANCELLING; re-ASSIGN for reassignable states).
Written as an explicit per-state matcher (so it reduces in the kernel for `decide`).
`canRework : Bool` = the sole dynamic guard (VALIDATING+FAIL: iteration < max ⇒ REWORKING, else
ESCALATED — the exhausted loop escalates, §14.3), lifted into the function's INPUT — see
`step_deterministic`.
`none` = signal not admissible in this state.
-/
def step (s : St) (sig : Sig) (canRework : Bool) : Option St :=
  match s with
  | IDLE => match sig with
    | ASSIGN => some OFFERED
    | CANCEL => some CANCELLING            -- IDLE ∈ non-terminals, ≠ CANCELLING ⇒ CANCEL catch-all
    | _ => none
  | OFFERED => match sig with
    | ACCEPT => some EXECUTING
    | CHALLENGE => some CHALLENGED
    | Sig.TIMEOUT => some OVERDUE
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED               -- re-ASSIGN (revision, Inv-1)
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
    | Sig.TIMEOUT => some OVERDUE
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | BLOCKED => match sig with
    | RESOLVE_BLOCK => some EXECUTING
    | Sig.TIMEOUT => some ESCALATED           -- direct to the handover (block IS escalation)
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | VALIDATING => match sig with
    | PASS => some DONE
    | FAIL => some (if canRework then REWORKING else ESCALATED)  -- guarded (§14.3)
    | Sig.TIMEOUT => some DONE                -- direct auto-pass (§24.7)
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | REWORKING => match sig with
    | DELIVER => some VALIDATING
    | BLOCK => some BLOCKED
    | Sig.TIMEOUT => some OVERDUE
    | CANCEL => some CANCELLING
    | ASSIGN => some OFFERED
    | _ => none
  | CANCELLING => match sig with          -- sole staffed exit = CONFIRM_CANCEL; no CANCEL/ASSIGN catch-all
    | CONFIRM_CANCEL => some ABANDONED
    | Sig.TIMEOUT => some ABANDONED            -- direct (cancellation is authoritative)
    | _ => none
  | OVERDUE => match sig with          -- accepts no progress signals; only re-timeout or CANCEL
    | Sig.TIMEOUT => some ESCALATED
    | CANCEL => some CANCELLING
    | _ => none
  -- DONE/ABANDONED are QUASI-terminal in the full protocol (R′, §14.3): `fsm.py` admits a
  -- re-ASSIGN (REOPEN) out of them under a DOUBLE graph-side gate (finality of consumption ∧
  -- reopens < max_reopens). That guard is a predicate over the GRAPH, not per-node state —
  -- outside this automaton's signature, so it is NOT encoded here (a named abstraction, not a
  -- drift): this file holds the terminal-absorbing BASE automaton, which R′ preserves in the
  -- limit (max_reopens exhausts). The reopen edge's system-level liveness is TLC-checked
  -- (formal/tla/FsmSpike.tla: Termination = <>[] terminal, FinalityAbsorbing) and the graph
  -- gate is code-tested (tests/test_reopen.py).
  | DONE => none
  | ABANDONED => none
  -- ESCALATED carries the issuer's three answers. Raising the rework bound and changing the
  -- criteria are both packet fields, so Inv-1 makes them ONE act (re-ASSIGN → OFFERED, taken by
  -- the reassignable catch-all below); closing it is the universal CANCEL; and the timeout is
  -- what keeps the wait finite — silence CLOSES (V = ⊥) and never drifts toward a pass, because
  -- nothing is on the table to accept: the executor stopped.
  | ESCALATED =>
    match sig with
    | ASSIGN => some OFFERED                  -- raise the bound / change the criteria (Inv-1)
    | CANCEL => some CANCELLING               -- close it; the cascade settles the live subtree
    | Sig.TIMEOUT => some CANCELLING           -- silence IS his cancellation: it takes the
                                              -- cancel path so the live subtree goes with it
    | _ => none

/-- The declared admissible-signal set per state (mirrors `fsm.py::available_signals`:
    the table rows + universal CANCEL for non-terminals≠CANCELLING + re-ASSIGN for
    reassignable states). This is what Inv-6 calls "the admissible set defined in each state". -/
def admissible : St → List Sig
  | IDLE        => [ASSIGN, CANCEL]
  | OFFERED     => [ACCEPT, CHALLENGE, TIMEOUT, CANCEL, ASSIGN]
  | CHALLENGED  => [ACCEPT_CHALLENGE, REJECT_CHALLENGE, TIMEOUT, CANCEL, ASSIGN]
  | EXECUTING   => [DELIVER, BLOCK, TIMEOUT, CANCEL, ASSIGN]
  | BLOCKED     => [RESOLVE_BLOCK, TIMEOUT, CANCEL, ASSIGN]
  | VALIDATING  => [PASS, FAIL, TIMEOUT, CANCEL, ASSIGN]
  | REWORKING   => [DELIVER, BLOCK, TIMEOUT, CANCEL, ASSIGN]
  | CANCELLING  => [CONFIRM_CANCEL, TIMEOUT]
  | OVERDUE     => [TIMEOUT, CANCEL]
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

/-- **Determinism (Inv-6).** For a fixed (state, signal, guard) the transition is unique.
    This holds DEFINITIONALLY: `step` is a total function, so it cannot return two results.
    HONEST NUANCE: determinism is trivial *because* we lifted the only dynamic branch (the
    VALIDATING+FAIL iteration guard, `fsm.py:163`) into the input `canRework`. In the running
    system that bit is read from `GuardContext`; encoding it as a function argument is the
    faithful move — it makes explicit that the transition is a function of (state, signal, guard),
    which is exactly what Inv-6 asserts ("the admissible set is defined in each state"). -/
theorem step_deterministic (s : St) (sig : Sig) (g : Bool) {t₁ t₂ : Option St}
    (h₁ : step s sig g = t₁) (h₂ : step s sig g = t₂) : t₁ = t₂ := by
  rw [← h₁, ← h₂]

/-- **Admissible-set correctness (Inv-6, the non-trivial half).** A signal moves the FSM iff
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

/-! ### Inv-5 — finiteness / totality -/

/-- Every non-terminal state EXCEPT `IDLE` has a defined TIMEOUT transition (§14.2 finiteness
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
  | OFFERED | CHALLENGED | EXECUTING | REWORKING => OVERDUE  -- first timeout → intermediate OVERDUE
  | BLOCKED => ESCALATED
  | VALIDATING => DONE
  | CANCELLING => ABANDONED
  | OVERDUE => ESCALATED                                  -- second timeout → the handover
  | ESCALATED => CANCELLING                               -- third: silence = his cancellation
  | s => s                                                -- IDLE + terminals: fixpoint

/-- **Finiteness / termination (Inv-5).** From EVERY non-terminal state except IDLE, at most
    FOUR system timeouts drive the FSM into a terminal state — the deadline path cannot stall.
    This is the real content of Inv-5 (finiteness of every non-terminal). `decide`-checked.

    It was TWO while ESCALATED counted as a terminal. The bound grew because the deadline path now
    ends in a HANDOVER and then in a CANCELLATION before it ends in a settlement:
    OFFERED → OVERDUE → ESCALATED → CANCELLING → ABANDONED. Nothing about finiteness weakened — the
    added steps are the issuer's silence being given its own clock (which is what Inv-5 demands of a
    live state) and that silence being spent, like any cancellation, on the whole subtree. -/
theorem timeout_terminates_check :
    allSt.all (fun s =>
        isTerminal s || (s == IDLE)
        || isTerminal (timeoutStep (timeoutStep (timeoutStep (timeoutStep s))))) = true := by decide

theorem timeout_terminates (s : St) (h₁ : isTerminal s = false) (h₂ : s ≠ IDLE) :
    isTerminal (timeoutStep (timeoutStep (timeoutStep (timeoutStep s)))) = true := by
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

/-- The canon's own corner: IDLE is a non-terminal state that Inv-5 exempts BY NAME (§14.4,
    "every non-terminal state **except IDLE**"; §14.2/§14.3 say so in their routing sentences —
    the pre-contract state carries no clock, and IDLE starvation surfaces as the PARENT's timeout).
    This encoding follows the canon.

    **The engine agrees, and this note used to say otherwise.** It declared two pending divergences
    — an `(IDLE, TIMEOUT)` row in `fsm.py` and an unretargeted `(VALIDATING, FAIL, iter >= max)` —
    and BOTH had since been closed in the engine (`fsm.py` carries no IDLE row, with a test pinning
    its absence, and the FAIL cell targets ESCALATED). A mirror whose declaration of where it
    diverges from the engine is wrong in both directions is the wrong instrument to check the engine
    with: a stale "known divergence" is exactly where a real one hides. Checked against `fsm.py`
    2026-09-21; there is no pending divergence at this row. -/
theorem idle_has_no_timeout : step IDLE TIMEOUT false = none := by decide

/-! ### Inv-1 — revision (re-ASSIGN) is NOT cancellation (§14.3, §14.4)

The canon's v3.7 subtlety: a revision changes a live node's contract via **re-ASSIGN under the
same id**, sending it to OFFERED (executor must re-ACCEPT/CHALLENGE) — it does NOT cascade or
cancel. Cancellation is a separate two-step handshake. Both are provable on the automaton. -/

/-- **Inv-1 (revision).** From every reassignable state, re-ASSIGN returns the node to OFFERED
    under its stable id — the executor is not silently bound to the new contract. -/
theorem reassign_to_offered (s : St) (h : isReassignable s = true) :
    step s ASSIGN false = some OFFERED := by
  cases s <;> simp_all [step, isReassignable]

/-! ### Cancellation is a completing two-step handshake (§14.3), mirror of ASSIGN→ACCEPT -/

/-- CANCEL from any non-terminal (except CANCELLING itself) opens the handshake → CANCELLING. -/
theorem cancel_initiates (s : St) (hnt : isTerminal s = false) (hc : s ≠ CANCELLING) :
    step s CANCEL false = some CANCELLING := by
  cases s <;> simp_all [step, isTerminal]

/-- CONFIRM_CANCEL closes it → ABANDONED (the sole staffed exit of CANCELLING). -/
theorem confirm_cancel_completes : step CANCELLING CONFIRM_CANCEL false = some ABANDONED := by decide

/-- …and ABANDONED is terminal — so the cancellation handshake always *completes* (no deadlock):
    every non-terminal ≠ CANCELLING reaches a terminal in exactly two signals. -/
theorem cancel_handshake_terminates (s : St) (hnt : isTerminal s = false) (hc : s ≠ CANCELLING) :
    step s CANCEL false = some CANCELLING ∧
    step CANCELLING CONFIRM_CANCEL false = some ABANDONED ∧
    isTerminal ABANDONED = true :=
  ⟨cancel_initiates s hnt hc, confirm_cancel_completes, by decide⟩

end GFSO.Fsm
