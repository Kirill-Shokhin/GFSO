/-
  GFSO — Tier 2: Thm 1, compositionality (§7.3), and its converse (`T1_characterization`). Derived from
  `Decomp`'s two fields (`Ontology`, §2.4), no `decide`: (←) by joint sufficiency, (→) by
  non-redundancy, as §7.3's proof runs.
  Encoding: V has no ⊥ (Thm 1 reads only V ≠ ⊥, §7.3), and `Decomp` admits an empty child list, which
  §7.3's non-atomic t excludes.
-/

import GFSO.Ontology

namespace GFSO.Compositionality

open GFSO.Ontology

/--
**Thm 1 (§7.3).** For a correct decomposition `V(parent)` is the AND of the children's verdicts,
`children.all Task.V` (its uniqueness is Thm 2, `AndUniqueness`).
-/
theorem T1 (d : Decomp) : d.parent.V = d.children.all Task.V := by
  -- Split on the AND of the children; both sides are Bool.
  cases hc : d.children.all Task.V with
  | true =>
    -- (←) all children pass: joint sufficiency, criterion by criterion.
    rw [Task.V_eq_true]
    intro c hmem
    exact d.joint_sufficiency c hmem hc
  | false =>
    -- (→) some child fails: non-redundancy breaks a parent criterion.
    rw [Task.V_eq_false]
    obtain ⟨t, hmem, hfail⟩ := List.all_eq_false.mp hc
    rw [Bool.not_eq_true] at hfail  -- `¬ V t = true`  ↦  `V t = false`
    exact d.non_redundancy t hmem hfail

/-- **Corollary (§7.3).** Every child passing, the parent passes. -/
theorem corollary_root_from_leaves (d : Decomp)
    (h : ∀ t ∈ d.children, t.V = true) : d.parent.V = true := by
  rw [T1]
  exact List.all_eq_true.mpr h

/-- **Characterization (§7.3)**: compositionality implies both conditions; with `T1`, §2.4's two
    conditions are exactly those under which it holds. -/
theorem T1_characterization (parent : Task) (children : List Task)
    (hcomp : parent.V = children.all Task.V) :
    (∀ c ∈ parent.criteria, children.all Task.V = true → c = true) ∧
    (∀ t ∈ children, t.V = false → ∃ c ∈ parent.criteria, c = false) := by
  constructor
  · -- joint sufficiency ← compositionality
    intro c hmem hall
    have : parent.V = true := by rw [hcomp]; exact hall
    exact (Task.V_eq_true.mp this) c hmem
  · -- non-redundancy ← compositionality
    intro t hmem hfail
    have hallfalse : children.all Task.V = false :=
      List.all_eq_false.mpr ⟨t, hmem, by rw [Bool.not_eq_true]; exact hfail⟩
    have : parent.V = false := by rw [hcomp]; exact hallfalse
    exact Task.V_eq_false.mp this

end GFSO.Compositionality
