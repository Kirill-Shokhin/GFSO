/-
  GFSO — Tier 4: standards and checks (Ch. 9). The three verification levels, the battery's
  CHECK → mode arrows, and CA-Morris as a named Lean `axiom` (`morris_trichotomy`) over the
  uninterpreted carrier `fullyKnown` — a covering axiom by citation, below CA1's grade (§9.1, §20.5).

  Decided off the table, axiom-free (§20.4): no CHECK lives at the Pragmatic level
  (`level2_has_no_check`); FM-3, FM-4 and FM-6 have no structural guard (`fm3_unguarded`,
  `fm4_unguarded`, `fm6_unguarded`), FM-1, FM-2 and FM-5 have one (`guarded_fms`) (§9.10).
-/

import GFSO.FailureModes

namespace GFSO.Standards

open GFSO.FailureModes

/-- The three verification levels (§9.1); `syntax` is a Lean keyword, hence `syn`. -/
inductive VerifLevel | syn | sem | prag
deriving DecidableEq, Repr

/-- The battery's nine CHECKs (§9.5, §9.6). -/
inductive Check | c1 | c1b | c2 | c3 | c4 | c5 | c6 | c7 | c8
deriving DecidableEq, Repr

open VerifLevel Check

/-- Each CHECK's level (§9.5, §9.6). -/
def checkLevel : Check → VerifLevel
  | c1 | c1b | c2 | c3 | c4 | c5 | c6 => syn   -- Syntactic (Level 0)
  | c7 | c8                           => sem   -- Semantic (Level 1)

/-- Each CHECK's arrows (§9.5, §9.6) at a split's admission, as a list: a CHECK may guard several modes
    or none. A revision's re-run is §12.10's. CHECK-2 carries FM-5 by its Dep clause alone, its D clauses
    guarding none (§12.10, §15.3). -/
def checkGuards : Check → List FM
  | c1  => [.fm1]              -- coverage           → FM-1.a
  | c1b => [.fm1]              -- no-orphan          → FM-1.e
  | c2  => [.fm5]              -- Dep acyclic → FM-5 (D forest, one parent: no FM)
  | c3  => [.fm5]              -- deadline coherence → FM-5
  | c4  => [.fm1]              -- ACCEPTED_RISKS     → FM-1 (FM-1.b's proxy, §9.5)
  | c5  => [.fm1]              -- risk nodes         → FM-1 (FM-1.c's proxy, §9.5)
  | c6  => []                  -- leaf delegation    → no FM (§9.5)
  | c7  => [.fm1]              -- formal sufficiency → FM-1.d
  | c8  => [.fm2]              -- formal consistency → FM-2

/-- `c` guards `f` — membership as a `Bool` test, so every fact below is decided by the kernel with
    no axiom. -/
def Guards (c : Check) (f : FM) : Prop := (checkGuards c).any (· == f) = true

instance (c : Check) (f : FM) : Decidable (Guards c f) :=
  inferInstanceAs (Decidable (_ = true))

def allChecks : List Check := [c1, c1b, c2, c3, c4, c5, c6, c7, c8]

theorem mem_allChecks (c : Check) : c ∈ allChecks := by cases c <;> decide

/-! ### The guard map, decided off the table -/

/-- **No CHECK at the Pragmatic level (§9.1, §20.4).** Every CHECK is Syntactic or Semantic. -/
theorem level2_has_no_check : ∀ c : Check, checkLevel c ≠ prag := by
  intro c; cases c <;> decide

/-- **FM-3 has no structural guard (§9.10).** Its runtime sensor is q_V, the false-PASS direction
    only (§15.7). -/
theorem fm3_unguarded : ∀ c : Check, ¬ Guards c FM.fm3 := by
  intro c; cases c <;> decide

/-- **FM-6 has no structural guard (§9.10)**; its remedy is deferring the split (§8.6). -/
theorem fm6_unguarded : ∀ c : Check, ¬ Guards c FM.fm6 := by
  intro c; cases c <;> decide

/-- **CHECK-6 guards no failure mode (§9.5).** An untrue PASS over a never-issued leaf is FM-3 and FM-4
    at the parent (§12.8), which CHECK-6 holding does not exclude. -/
theorem c6_guards_none : ∀ f : FM, ¬ Guards c6 f := by
  intro f; cases f <;> decide

/-- **FM-4 has no structural guard (§9.10)**; its departure from AND is read off the log (§12.8,
    §15.7). -/
theorem fm4_unguarded : ∀ c : Check, ¬ Guards c FM.fm4 := by
  intro c; cases c <;> decide

/-- FM-1, FM-2 and FM-5 each have a structural guard (§9.10). -/
theorem guarded_fms :
    (∃ c, Guards c FM.fm1) ∧ (∃ c, Guards c FM.fm2) ∧ (∃ c, Guards c FM.fm5) :=
  ⟨⟨c1, by decide⟩, ⟨c8, by decide⟩, ⟨c3, by decide⟩⟩

/-- CHECK-2 guards FM-5 alone, by its Dep clause (§12.10, §15.3). -/
theorem c2_guards_one :
    ∀ f : FM, Guards c2 f ↔ f = .fm5 := by
  intro f; cases f <;> decide

/-! ### CA-Morris — the covering axiom, made an explicit `axiom` -/

/-- Knowledge about a decomposition by the three levels (§9.1). -/
structure Knowledge where
  /-- Syntactic (Level 0). -/
  L0 : Prop
  /-- Semantic (Level 1). -/
  L1 : Prop
  /-- Pragmatic (Level 2). -/
  L2 : Prop

/-- The decomposition fully known. Uninterpreted — its Pragmatic half is domain truth (Lemma 1, §3.4) —
    so no literal refutes the axiom below. -/
axiom fullyKnown : Knowledge → Prop

/--
**CA-Morris (§9.1)**, covering direction only: the three levels suffice. By citation [18], with no
narrowing argument of its own, below CA1's grade (§20.5); each level's irremovability is §9.8's
argument, not this axiom.
-/
axiom morris_trichotomy (k : Knowledge) : (k.L0 ∧ k.L1 ∧ k.L2) → fullyKnown k

/-- A gap in knowledge sits at one of the three levels: CA-Morris by De Morgan. -/
theorem knowledge_gap_located (k : Knowledge) (h : ¬ fullyKnown k) : ¬k.L0 ∨ ¬k.L1 ∨ ¬k.L2 := by
  apply Classical.byContradiction
  intro hc
  apply h
  apply morris_trichotomy k
  refine ⟨?_, ?_, ?_⟩
  · exact Classical.byContradiction (fun hn => hc (Or.inl hn))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inl hn)))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inr hn)))

end GFSO.Standards
