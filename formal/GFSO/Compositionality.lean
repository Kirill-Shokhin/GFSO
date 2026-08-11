/-
  GFSO — Theorem 1: COMPOSITIONALITY (§11.1). The central property of the system.

  Canon `docs/applied_gfso_v4_en.md` §11.1:

    Thm 1. For a non-atomic t with a CORRECT decomposition D(t) = {t₁..tₙ}:
        V(t) = pass  ⟺  ∀tⱼ ∈ D(t): V(tⱼ) = pass

  This is the crown jewel of the ontology-first approach: T1 is NOT a `decide` exhaustion — it
  is a genuine ~10-line derivation whose two halves are, line for line, the canon's proof:
    (→) joint sufficiency; (←) non-redundancy (by contraposition).
  Both hypotheses come straight out of the `Decomp` record (Ontology.lean = §10). Nothing else
  is used — which is exactly the canon's point: these two conditions are *precisely* what
  compositionality needs (the "Characterization" remark, §11.1).
-/

import GFSO.Ontology

namespace GFSO.Compositionality

open GFSO.Ontology

/--
**Theorem 1 (compositionality, §11.1).**  For a correct decomposition, the parent's validation
equals the AND of the children's validations:  `V(parent) = ⋀ⱼ V(tⱼ)`.

(Here `children.all Task.V` IS the n-ary AND of the children's verdicts — the aggregation whose
*uniqueness* is the separate Theorem 2, `AndUniqueness.lean` §11.3.)

Proof — the canon's two directions, verbatim:
* **(→) all children pass ⟹ parent passes.** By *joint sufficiency*: every parent criterion is
  discharged when all children pass, so `V(parent) = pass`.
* **(←) parent passes ⟹ all children pass**, contrapositive: **some child fails ⟹ parent fails.**
  By *non-redundancy*: a failing child breaks some parent criterion, so `V(parent) = fail`.
-/
theorem T1 (d : Decomp) : d.parent.V = d.children.all Task.V := by
  -- Split on the AND of the children. Both sides are Bool; we show they agree in each case.
  cases hc : d.children.all Task.V with
  | true =>
    -- (→) all children pass. Show V(parent) = pass via joint sufficiency, criterion by criterion.
    rw [Task.V_eq_true]
    intro c hmem
    exact d.joint_sufficiency c hmem hc
  | false =>
    -- (←) some child fails (that is what `all = false` means). Non-redundancy then breaks a
    -- parent criterion, so V(parent) = fail.
    rw [Task.V_eq_false]
    obtain ⟨t, hmem, hfail⟩ := List.all_eq_false.mp hc
    rw [Bool.not_eq_true] at hfail  -- `¬ V t = true`  ↦  `V t = false`
    exact d.non_redundancy t hmem hfail

/-- **Corollary (§11.1).** If every child is validated (`V = pass`), the parent is validated:
    the global check is a consequence of the local ones. -/
theorem corollary_root_from_leaves (d : Decomp)
    (h : ∀ t ∈ d.children, t.V = true) : d.parent.V = true := by
  rw [T1]
  exact List.all_eq_true.mpr h

/-- **Characterization (§11.1): the two conditions are also NECESSARY.** T1 gives them as
    sufficient; here is the converse — if compositionality `V(parent) = ⋀ V(children)` holds,
    then both joint sufficiency and non-redundancy hold. Together with `T1` this makes §10's two
    conditions *exactly* (iff) the conditions for compositionality — the canon's "exact
  characterization", not merely a sufficient recipe. -/
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
