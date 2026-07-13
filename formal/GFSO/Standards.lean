/-
  GFSO — TIER 4: Standards & Checks (§5). The three verification levels and the CHECK↔FM guard map.

  Canon `docs/applied_gfso_v3.md` §5.4:
    Level 0 syntax     — graph topology / mapping           → CHECK-1, 1b, 2–6
    Level 1 semantics  — formal implication + compatibility → CHECK-7, 8
    Level 2 pragmatics — causal correctness in the world    → NOT mechanically checkable
    "Исчерпывающесть уровней": knowledge about a sign-expression is exhausted by
    syntax ⊕ semantics ⊕ pragmatics (Morris 1938). "Четвёртого измерения не существует."

  That last sentence is a COVERING PRINCIPLE, not a theorem — same shape as Axiom 1 (§4.8).
  Here it becomes an explicit named axiom (`morris_trichotomy`) over an uninterpreted predicate,
  so it shows up in `#print axioms` and cannot be refuted by a literal.

  Two facts fall out and are machine-checked (axiom-free), both worth seeing:
    * `level2_has_no_check`   — Level 2 has NO CHECK. Pragmatics is not mechanically checkable.
    * `fm3_unguarded`, `fm6_unguarded` — FM-3 and FM-6 are guarded by NO structural check.
      (§5.5: FM-3 is guaranteed axiomatically by A1; FM-6 by the protocol's deferred decomposition.)
-/

import GFSO.FailureModes

namespace GFSO.Standards

open GFSO.FailureModes

/-- The three levels of verifiability (§5.4). `syntax`/`prag` abbreviated — `syntax` is a Lean keyword. -/
inductive VerifLevel | syn | sem | prag
deriving DecidableEq, Repr

/-- The structural checks of STD-4 (§5.4). -/
inductive Check | c1 | c1b | c2 | c3 | c4 | c5 | c6 | c7 | c8
deriving DecidableEq, Repr

open VerifLevel Check

/-- Which level each check lives at (§5.4 table). -/
def checkLevel : Check → VerifLevel
  | c1 | c1b | c2 | c3 | c4 | c5 | c6 => syn   -- Level 0: topology only
  | c7 | c8                           => sem   -- Level 1: formal implication / consistency

/-- Which failure mode each check guards (§5.4 / §5.5 tables). -/
def checkGuards : Check → FM
  | c1  => .fm1   -- покрытие          → FM-1.a
  | c1b => .fm1   -- неизбыточность    → FM-1.e
  | c2  => .fm4   -- ацикличность DAG  → FM-4
  | c3  => .fm5   -- согласованность сроков → FM-5
  | c4  => .fm1   -- NEGLECTED         → FM-1
  | c5  => .fm1   -- risk-nodes        → FM-1
  | c6  => .fm7   -- делегирование листьев → FM-7
  | c7  => .fm1   -- formal sufficiency → FM-1.d
  | c8  => .fm2   -- formal consistency → FM-2

def allChecks : List Check := [c1, c1b, c2, c3, c4, c5, c6, c7, c8]

theorem mem_allChecks (c : Check) : c ∈ allChecks := by cases c <;> decide

/-! ### Two axiom-free facts that the canon states in prose -/

/-- **Level 2 has no CHECK (§5.4).** Pragmatics — causal correctness in the real world — is not
    mechanically checkable. Every check is Level 0 or Level 1. This is the structural face of
    §18.1: the apparatus stops at the semantic level. -/
theorem level2_has_no_check : ∀ c : Check, checkLevel c ≠ prag := by
  intro c; cases c <;> decide

/-- **FM-3 is guarded by no structural check (§5.5).** Verifiability (truth of a verdict) is
    guaranteed *axiomatically* by A1 (criteria are decidable predicates) — not by a check.
    Its runtime detection is q_V, which (§16.5) only catches false-PASS. -/
theorem fm3_unguarded : ∀ c : Check, checkGuards c ≠ FM.fm3 := by
  intro c; cases c <;> decide

/-- **FM-6 is guarded by no structural check (§5.5).** Feasibility (can D even be determined) is
    handled by the *protocol* (deferred decomposition), not by a pre-execution check. -/
theorem fm6_unguarded : ∀ c : Check, checkGuards c ≠ FM.fm6 := by
  intro c; cases c <;> decide

/-- Everything else IS guarded: FM-1, FM-2, FM-4, FM-5, FM-7 each have at least one check. -/
theorem guarded_fms :
    (∃ c, checkGuards c = FM.fm1) ∧ (∃ c, checkGuards c = FM.fm2) ∧
    (∃ c, checkGuards c = FM.fm4) ∧ (∃ c, checkGuards c = FM.fm5) ∧
    (∃ c, checkGuards c = FM.fm7) :=
  ⟨⟨c1, rfl⟩, ⟨c8, rfl⟩, ⟨c2, rfl⟩, ⟨c3, rfl⟩, ⟨c6, rfl⟩⟩

/-! ### Morris trichotomy — the covering principle, made an explicit axiom -/

/-- Knowledge about a decomposition, split by the three Morris dimensions (§5.4). -/
structure Knowledge where
  /-- Level 0 — syntax: graph structure and mapping are correct. -/
  L0 : Prop
  /-- Level 1 — semantics: formal implication and compatibility hold. -/
  L1 : Prop
  /-- Level 2 — pragmatics: causal correctness against the real domain. -/
  L2 : Prop

/-- "The decomposition is fully known/correct." Uninterpreted: its Level-2 half is domain truth,
    not derivable from the apparatus (Лемма 1) — so no literal may compute it. -/
axiom fullyKnown : Knowledge → Prop

/--
**Morris trichotomy (covering principle, §5.4).** Knowledge about a sign-expression is exhausted by
syntax ⊕ semantics ⊕ pragmatics; *there is no fourth dimension*. This is a covering principle of the
same kind as Axiom 1 (§4.8): the partition WITHIN each dimension is derived, but "these three
exhaust" cannot be proved from inside — the space of candidate dimensions is not delimited.
Named here so it appears in `#print axioms`.
-/
axiom morris_trichotomy (k : Knowledge) : fullyKnown k ↔ (k.L0 ∧ k.L1 ∧ k.L2)

/-- Any gap in knowledge sits at exactly one of the three levels. Derived from the axiom. -/
theorem knowledge_gap_located (k : Knowledge) (h : ¬ fullyKnown k) : ¬k.L0 ∨ ¬k.L1 ∨ ¬k.L2 := by
  rw [morris_trichotomy] at h
  apply Classical.byContradiction
  intro hc
  apply h
  refine ⟨?_, ?_, ?_⟩
  · exact Classical.byContradiction (fun hn => hc (Or.inl hn))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inl hn)))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inr hn)))

end GFSO.Standards
