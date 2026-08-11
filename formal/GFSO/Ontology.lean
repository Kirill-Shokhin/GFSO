/-
  GFSO — the ONTOLOGY (§9–10). The "ontological language" the whole formalization speaks.

  Canon `docs/applied_gfso_v4_en.md` §10 (primitives), §10 "Correctness of a decomposition"
  (the two correctness conditions), §10.2 (minimality of the basis).

  Everything downstream (T1 §11.1, |L|=2 §11.2, T2 §11.3) is derived FROM the definitions here —
  no black-box `decide`, the proofs read as the canon's paragraphs. This is the point: the
  meaning lives in the definitions, and the theorems fall out of them.

  Design note (faithfulness): a `Task` in §10 is `(spec, criteria, deadline)` with
  `criteria = {c₁..cₖ}`, each `cᵢ : Result → {pass,fail}`. For the COMPOSITIONAL results
  (T1) neither spec, deadline, nor the internal shape of a Result is load-bearing — only the
  VERDICT each criterion returns on the delivered result. So we model a validated task by the
  list of those verdicts (`true = pass`, `false = fail`). Nothing about T1 depends on more;
  keeping the model this thin is what makes the proof honest and short.
-/

namespace GFSO.Ontology

/-- **Value scale L (§11.2).** `pass`/`fail`. We model it as `Bool` (`true = pass`). That `|L| = 2`
    is not assumed here for its own sake — it is *proved* forced in `Binarity.lean` (§11.2). -/
abbrev Verdict := Bool

/-- **Task (T) — §10.** A task carries a finite list of criteria; here we expose exactly what
    validation needs: each criterion's verdict on the delivered result. `spec`/`deadline` are
    elided (not load-bearing for the compositional theorems — see the design note above). -/
structure Task where
  /-- The verdict `cᵢ ∈ {pass, fail}` of each criterion on this task's result. -/
  criteria : List Verdict

/-- **Validation (V) — §10.** `V(t) = pass  ⟺  ∀ cᵢ ∈ criteria(t): cᵢ = pass`.
    V is not a primitive but a function INDUCED by T (§10.1): the conjunction of the criteria. -/
def Task.V (t : Task) : Verdict := t.criteria.all id

/-- Unfolding of `V`: passing means every criterion passes. (Convenience view of the definition.) -/
theorem Task.V_eq_true {t : Task} : t.V = true ↔ ∀ c ∈ t.criteria, c = true := by
  simp [Task.V, List.all_eq_true]

/-- A task fails exactly when some criterion fails — the dual view of `V`. -/
theorem Task.V_eq_false {t : Task} : t.V = false ↔ ∃ c ∈ t.criteria, c = false := by
  simp [Task.V]

/--
**Decomposition (D) and its CORRECTNESS — §10 (the central definition).**

`D(t) = {t₁,…,tₙ}` is *correct* under exactly two conditions (verbatim §10). We bundle a
decomposition together with proofs of both — a `Decomp` value IS a correct decomposition. This
is the ontological heart: T1 (§11.1) is nothing but reading these two fields back out.

The two conditions, in the canon's own words:
1. **Joint sufficiency (coverage):** `∀cᵢ ∈ criteria(t): [∀tⱼ: V(tⱼ)=pass] → cᵢ=pass`.
   All children pass ⟹ every parent criterion is satisfied.
2. **Non-redundancy (necessity):** `∀tⱼ: V(tⱼ)=fail → ∃cᵢ ∈ criteria(t): cᵢ=fail`.
   No ballast: any child failing breaks at least one parent criterion.
-/
structure Decomp where
  parent : Task
  children : List Task
  /-- §10 (1) joint sufficiency — per parent criterion, as the canon states it. -/
  joint_sufficiency : ∀ c ∈ parent.criteria, children.all Task.V = true → c = true
  /-- §10 (2) non-redundancy — per child, as the canon states it. -/
  non_redundancy : ∀ t ∈ children, t.V = false → ∃ c ∈ parent.criteria, c = false

/-! ### §10.2 — independence of the basis {T, D, Dep, Del}

The canon (§10.2) argues minimality constructively (per-element counterexample) and states that each
primitive carries information not expressible via the others. It flags honestly (§10.2 "Remark",
§26.9) that a *strict* minimality proof would need the space of "all organizational primitives" —
open. So: minimality ≠ uniqueness.

We formalize exactly the half §10.2 licenses, and we formalize it **properly**: not "the four labels
differ" (that would prove nothing), but **no primitive is a function of the other three** —
exhibited, as in Lemma 1 (§2.5), by two structures that agree on the other three coordinates and
disagree on this one. That is precisely "each carries unique information".

Scope, stated honestly: this is independence *within the four-coordinate presentation* of an HVP
(§10.1). It does **not** show there is no fifth primitive — that is §26.9, and it is open, because the
space of candidate primitives is not delimited (the same wall as `|Act|=2`; see `Postulates.lean`). -/

/-- An HVP presented by its four basis coordinates (§10.1). Each coordinate is abstracted to a `Bool`:
    nothing about independence depends on their internal richness, only on their being **four
    separate coordinates** — i.e. that fixing three does not fix the fourth. -/
structure HVP where
  T : Bool
  D : Bool
  Dep : Bool
  Del : Bool
deriving DecidableEq, Repr

/-- **T is not determined by (D, Dep, Del).** No function of the other three recovers it: the two
    witnesses agree on D, Dep, Del and disagree on T. -/
theorem T_not_determined : ¬ ∃ f : Bool → Bool → Bool → Bool, ∀ s : HVP, f s.D s.Dep s.Del = s.T := by
  rintro ⟨f, hf⟩
  have h₁ := hf ⟨true, false, false, false⟩
  have h₂ := hf ⟨false, false, false, false⟩
  simp at h₁ h₂
  rw [h₁] at h₂; exact Bool.noConfusion h₂

/-- **D is not determined by (T, Dep, Del).** -/
theorem D_not_determined : ¬ ∃ f : Bool → Bool → Bool → Bool, ∀ s : HVP, f s.T s.Dep s.Del = s.D := by
  rintro ⟨f, hf⟩
  have h₁ := hf ⟨false, true, false, false⟩
  have h₂ := hf ⟨false, false, false, false⟩
  simp at h₁ h₂
  rw [h₁] at h₂; exact Bool.noConfusion h₂

/-- **Dep is not determined by (T, D, Del).** The canon's point: Dep carries causal order between
    branches, which the vertical structure D cannot express. -/
theorem Dep_not_determined : ¬ ∃ f : Bool → Bool → Bool → Bool, ∀ s : HVP, f s.T s.D s.Del = s.Dep := by
  rintro ⟨f, hf⟩
  have h₁ := hf ⟨false, false, true, false⟩
  have h₂ := hf ⟨false, false, false, false⟩
  simp at h₁ h₂
  rw [h₁] at h₂; exact Bool.noConfusion h₂

/-- **Del is not determined by (T, D, Dep).** Accountability is orthogonal to the decomposition
    plane — the canon's "decomposition ⊥ authority". -/
theorem Del_not_determined : ¬ ∃ f : Bool → Bool → Bool → Bool, ∀ s : HVP, f s.T s.D s.Dep = s.Del := by
  rintro ⟨f, hf⟩
  have h₁ := hf ⟨false, false, false, true⟩
  have h₂ := hf ⟨false, false, false, false⟩
  simp at h₁ h₂
  rw [h₁] at h₂; exact Bool.noConfusion h₂

/--
**Independence of the basis (§10.2) — structural.** No primitive of {T, D, Dep, Del} is a function of
the other three.

**Honest reading.** `HVP` is a product of four *free* coordinates, so independence is forced by the
model: a 4-tuple of free bits has four independent coordinates. This formalizes the **shape** of
§10.2's claim, not its content — the canon's *semantic* argument ("Dep carries causal order that D
cannot express") is not captured, because that would require modelling what D and Dep actually mean.
Nor is it uniqueness: whether a fifth primitive exists is §26.9, open, because the space of candidate
primitives is not delimited (the same wall as `|Act| = 2`; see `Postulates.lean`).
-/
theorem basis_independent :
    (¬ ∃ f : Bool → Bool → Bool → Bool, ∀ s : HVP, f s.D s.Dep s.Del = s.T) ∧
    (¬ ∃ f : Bool → Bool → Bool → Bool, ∀ s : HVP, f s.T s.Dep s.Del = s.D) ∧
    (¬ ∃ f : Bool → Bool → Bool → Bool, ∀ s : HVP, f s.T s.D s.Del = s.Dep) ∧
    (¬ ∃ f : Bool → Bool → Bool → Bool, ∀ s : HVP, f s.T s.D s.Dep = s.Del) :=
  ⟨T_not_determined, D_not_determined, Dep_not_determined, Del_not_determined⟩

end GFSO.Ontology
