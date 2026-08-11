/-
  GFSO — TIER 4: Standards & Checks (§13). The three verification levels and the CHECK↔FM guard map.

  Canon `docs/applied_gfso_v4_en.md` §13.4:
    Level 0 syntax     — graph topology / mapping           → CHECK-1, 1b, 2–6
    Level 1 semantics  — formal implication + compatibility → CHECK-7, 8
    Level 2 pragmatics — causal correctness in the world    → NOT mechanically checkable
    "Exhaustiveness of the levels": knowledge about a sign-expression is exhausted by
    syntax ⊕ semantics ⊕ pragmatics (Morris 1938). "There is no fourth dimension."

  That last sentence is a COVERING PRINCIPLE, not a theorem — same shape as CA1 (§12.8).
  Here it becomes an explicit named axiom (`morris_trichotomy`) over an uninterpreted predicate,
  so it shows up in `#print axioms` and cannot be refuted by a literal.

  Two facts fall out and are machine-checked (axiom-free), both worth seeing:
    * `level2_has_no_check`   — Level 2 has NO CHECK. Pragmatics is not mechanically checkable.
    * `fm3_unguarded`, `fm6_unguarded` — FM-3 and FM-6 are guarded by NO structural check.
      (§13.6: A1 fixes FM-3's verdict *form*, not its truth — no CHECK guards it; FM-6 is
      answered by the protocol's deferred decomposition.)
-/

import GFSO.FailureModes

namespace GFSO.Standards

open GFSO.FailureModes

/-- The three levels of verifiability (§13.4). `syntax`/`prag` abbreviated — `syntax` is a Lean keyword. -/
inductive VerifLevel | syn | sem | prag
deriving DecidableEq, Repr

/-- The structural checks of STD-4 (§13.4). -/
inductive Check | c1 | c1b | c2 | c3 | c4 | c5 | c6 | c7 | c8
deriving DecidableEq, Repr

open VerifLevel Check

/-- Which level each check lives at (§13.4 table). -/
def checkLevel : Check → VerifLevel
  | c1 | c1b | c2 | c3 | c4 | c5 | c6 => syn   -- Level 0: topology only
  | c7 | c8                           => sem   -- Level 1: formal implication / consistency

/-- Which failure mode each check guards (§13.4 / §13.6 tables). -/
def checkGuards : Check → FM
  | c1  => .fm1   -- coverage         → FM-1.a
  | c1b => .fm1   -- non-redundancy   → FM-1.e
  | c2  => .fm4   -- DAG acyclicity   → FM-4
  | c3  => .fm5   -- deadline coherence → FM-5
  | c4  => .fm1   -- ACCEPTED_RISKS         → FM-1
  | c5  => .fm1   -- risk-nodes        → FM-1
  | c6  => .fm7   -- leaf delegation  → FM-7
  | c7  => .fm1   -- formal sufficiency → FM-1.d
  | c8  => .fm2   -- formal consistency → FM-2

def allChecks : List Check := [c1, c1b, c2, c3, c4, c5, c6, c7, c8]

theorem mem_allChecks (c : Check) : c ∈ allChecks := by cases c <;> decide

/-! ### Two axiom-free facts that the canon states in prose -/

/-- **Level 2 has no CHECK (§13.4).** Pragmatics — causal correctness in the real world — is not
    mechanically checkable. Every check is Level 0 or Level 1. This is the structural face of
    §8: the apparatus stops at the semantic level. -/
theorem level2_has_no_check : ∀ c : Check, checkLevel c ≠ prag := by
  intro c; cases c <;> decide

/-- **FM-3 is guarded by no structural check (§13.6).** A1 (criteria are decidable predicates)
    fixes the verdict's *form*, not its truth: clause (i) buys decidability and binarity, never
    sensitivity, and clause (ii) is apparatus-uncertifiable (§2.6, §3.2 d6). No check stands here.
    Its runtime detection is q_V, which (§24.5) only catches false-PASS. -/
theorem fm3_unguarded : ∀ c : Check, checkGuards c ≠ FM.fm3 := by
  intro c; cases c <;> decide

/-- **FM-6 is guarded by no structural check (§13.6).** Feasibility (can D even be determined) is
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

/-- Knowledge about a decomposition, split by the three Morris dimensions (§13.4). -/
structure Knowledge where
  /-- Level 0 — syntax: graph structure and mapping are correct. -/
  L0 : Prop
  /-- Level 1 — semantics: formal implication and compatibility hold. -/
  L1 : Prop
  /-- Level 2 — pragmatics: causal correctness against the real domain. -/
  L2 : Prop

/-- "The decomposition is fully known/correct." Uninterpreted: its Level-2 half is domain truth,
    not derivable from the apparatus (Lemma 1) — so no literal may compute it. -/
axiom fullyKnown : Knowledge → Prop

/--
**Morris trichotomy (covering principle, §13.4).** Knowledge about a sign-expression is exhausted by
syntax ⊕ semantics ⊕ pragmatics; *there is no fourth dimension*. This is a covering principle of the
same kind as CA1 (§12.8): the partition WITHIN each dimension is derived, but "these three
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
