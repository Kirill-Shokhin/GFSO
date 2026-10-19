/-
  GFSO — Tier 1: the primitives (Ch. 2) as Lean types — the task, validation, a correct decomposition
  (§2.4) — and the independence of the basis (§7.5). Thm 1 (`Compositionality`, which imports this
  module) is read off `Decomp`'s two fields; |L| = 2 (`Binarity`) and Thm 2 (`AndUniqueness.and_unique`)
  stand in their own modules.

  Encoding: a task is the list of its criteria's verdicts on the delivered result (`true = pass`). Spec,
  deadline and the result's shape are elided, Thm 1 reading only the verdicts; the list may be empty
  (the canon's criteria are nonempty, §2.2), and V has no ⊥ (§2.3).
-/

namespace GFSO.Ontology

/-- **L (§7.1)** as `Bool`, `true = pass`: |L| = 2 is the type (A1); its defense against a graded scale
    is `Binarity.L_forced_two`. -/
abbrev Verdict := Bool

/-- **Task (§2.2)**, reduced to its criteria's verdicts (module header). -/
structure Task where
  /-- Each criterion's verdict on this task's result. -/
  criteria : List Verdict

/-- **V (§2.3)**: the conjunction of the criteria; induced by T, no primitive (§2.8). -/
def Task.V (t : Task) : Verdict := t.criteria.all id

/-- A task passes exactly when every criterion passes. -/
theorem Task.V_eq_true {t : Task} : t.V = true ↔ ∀ c ∈ t.criteria, c = true := by
  simp [Task.V, List.all_eq_true]

/-- A task fails exactly when some criterion fails. -/
theorem Task.V_eq_false {t : Task} : t.V = false ↔ ∃ c ∈ t.criteria, c = false := by
  simp [Task.V]

/--
**A correct decomposition (§2.4).** A `Decomp` carries proofs of both conditions, so a value IS a
correct decomposition; the fields state them per parent criterion and per child, as §2.4 does.
-/
structure Decomp where
  parent : Task
  children : List Task
  /-- §2.4 (1) joint sufficiency. -/
  joint_sufficiency : ∀ c ∈ parent.criteria, children.all Task.V = true → c = true
  /-- §2.4 (2) non-redundancy. -/
  non_redundancy : ∀ t ∈ children, t.V = false → ∃ c ∈ parent.criteria, c = false

/-! ### §7.5 — independence of the basis {T, D, Dep, Del}

No primitive is a function of the other three, shown as Lemma 1's form is: two structures agreeing on
three coordinates and differing on the fourth. Independence within the four-coordinate presentation
(§2.8) only — not uniqueness, whether a fifth primitive exists being the carve wall's question (§20.7). -/

/-- An HVP by its four basis coordinates (§2.8), each a `Bool`: only their being separate coordinates
    matters. -/
structure HVP where
  T : Bool
  D : Bool
  Dep : Bool
  Del : Bool
deriving DecidableEq, Repr

/-- **T is not determined by (D, Dep, Del)**: two witnesses agree on those and differ on T. -/
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

/-- **Dep is not determined by (T, D, Del)** — as a coordinate; the canon's ground is semantic
    (§2.7, §7.5). -/
theorem Dep_not_determined : ¬ ∃ f : Bool → Bool → Bool → Bool, ∀ s : HVP, f s.T s.D s.Del = s.Dep := by
  rintro ⟨f, hf⟩
  have h₁ := hf ⟨false, false, true, false⟩
  have h₂ := hf ⟨false, false, false, false⟩
  simp at h₁ h₂
  rw [h₁] at h₂; exact Bool.noConfusion h₂

/-- **Del is not determined by (T, D, Dep)** (§2.8: the plane {T, D, Dep, V} is "authority-free by
    construction"). -/
theorem Del_not_determined : ¬ ∃ f : Bool → Bool → Bool → Bool, ∀ s : HVP, f s.T s.D s.Dep = s.Del := by
  rintro ⟨f, hf⟩
  have h₁ := hf ⟨false, false, false, true⟩
  have h₂ := hf ⟨false, false, false, false⟩
  simp at h₁ h₂
  rw [h₁] at h₂; exact Bool.noConfusion h₂

/--
**Independence of the basis (§7.5), structural.**

**Honest reading.** `HVP` is a product of four free bits, so independence is forced by the model: this
checks the shape of §7.5's minimality, not its semantic content (what D and Dep mean, §2.7), and not
uniqueness (§20.7).
-/
theorem basis_independent :
    (¬ ∃ f : Bool → Bool → Bool → Bool, ∀ s : HVP, f s.D s.Dep s.Del = s.T) ∧
    (¬ ∃ f : Bool → Bool → Bool → Bool, ∀ s : HVP, f s.T s.Dep s.Del = s.D) ∧
    (¬ ∃ f : Bool → Bool → Bool → Bool, ∀ s : HVP, f s.T s.D s.Del = s.Dep) ∧
    (¬ ∃ f : Bool → Bool → Bool → Bool, ∀ s : HVP, f s.T s.D s.Dep = s.Del) :=
  ⟨T_not_determined, D_not_determined, Dep_not_determined, Del_not_determined⟩

end GFSO.Ontology
