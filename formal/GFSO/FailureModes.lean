/-
  GFSO — Tier 3: the six failure modes as a basis (Ch. 8). The 4+2 geometry and the six independence
  witnesses, axiom-free; completeness modulo CA1 as a named Lean `axiom` (`evaluation_completeness`)
  over the uninterpreted carrier `correct`, so it shows in `#print axioms` of every result leaning on
  it (§20.4, §20.5).

  Encoded, not derived: the dissection — the four denotational loci are the constructors of
  `DenotLocus` (internal completeness, a covering axiom, §8.5), the three phases axiom-free in `Time`
  (§8.2) — and the after phase carrying no mode (`after_holds_none`), which §8.6 derives from what this
  module does not model.
-/

namespace GFSO.FailureModes

/-! ### The 4+2 geometry (§8.10) — axiom-free -/

/-- The six failure modes (§8.3–§8.6). -/
inductive FM | fm1 | fm2 | fm3 | fm4 | fm5 | fm6
deriving DecidableEq, Repr

/-- **Denotational axis (§8.2).** The four loci of the validation function: the arguments' membership
    and relations, the values, the rule. That there are no others is fixed by these constructors and
    carried by CA1 (§8.2, §8.5). -/
inductive DenotLocus | argsMembership | argsRelations | values | rule
deriving DecidableEq, Repr

/-- **Operational axis (§8.2).** The three phases of the application; their count is axiom-free over a
    strict causal order (`Time.app_phases_exhaustive`, `Time.app_phases_disjoint`). -/
inductive OpPhase | before | during | after
deriving DecidableEq, Repr

/-- A failure locus is on one axis or the other (§8.8: formula ⊎ computation). -/
abbrev FailureLocus := DenotLocus ⊕ OpPhase

/-- **The dissection (§8.8): each locus to its mode, where it carries one.** -/
def locusFM : FailureLocus → Option FM
  | .inl .argsMembership  => some .fm1   -- args membership   → FM-1 Correspondence
  | .inl .argsRelations   => some .fm2   -- args relations    → FM-2 Consistency
  | .inl .values          => some .fm3   -- values            → FM-3 Veracity
  | .inl .rule            => some .fm4   -- rule              → FM-4 Propagation
  | .inr .before          => some .fm6   -- phase before      → FM-6 Feasibility
  | .inr .during          => some .fm5   -- phase during      → FM-5 Freshness
  | .inr .after           => none        -- phase after       → no condition (§8.6)

/-- **The after phase holds no mode (§8.6)** — encoded, not derived (module header). -/
theorem after_holds_none : locusFM (.inr .after) = none := rfl

/-- **Every mode has a locus (§8.8).** The surjectivity of the encoding's map, not the completeness of
    the dissection, which the constructors fix (module header). -/
theorem locusFM_surjective : ∀ fm : FM, ∃ l : FailureLocus, locusFM l = some fm := by
  intro fm; cases fm
  · exact ⟨.inl .argsMembership, rfl⟩
  · exact ⟨.inl .argsRelations, rfl⟩
  · exact ⟨.inl .values, rfl⟩
  · exact ⟨.inl .rule, rfl⟩
  · exact ⟨.inr .during, rfl⟩
  · exact ⟨.inr .before, rfl⟩

/-- **No collision (§8.8: 6 is the basis's dimension).** Distinct loci carrying a mode carry distinct
    modes. -/
theorem locusFM_injective : ∀ l l' : FailureLocus,
    locusFM l = locusFM l' → locusFM l ≠ none → l = l' := by
  intro l l' h _
  cases l with
  | inl d => cases d <;> (cases l' with
      | inl d' => cases d' <;> simp_all [locusFM]
      | inr o' => cases o' <;> simp_all [locusFM])
  | inr o => cases o <;> (cases l' with
      | inl d' => cases d' <;> simp_all [locusFM]
      | inr o' => cases o' <;> simp_all [locusFM])

/-! ### Completeness with CA1 explicit (§8.8) -/

/--
A validation computation (§8.1), abstracted to six free conditions: `Cᵢ` holds iff FM-`i` is absent.
`C1`–`C6` are this encoding's field names; the canon names each condition by its mode (§8.3–§8.6):
`C1` correspondence, `C2` compatibility, `C3` truth, `C4` propagation, `C5` freshness, `C6`
definability. Their content is not modelled: each is a bare `Prop`.
-/
structure Computation where
  C1 : Prop
  C2 : Prop
  C3 : Prop
  C4 : Prop
  C5 : Prop
  C6 : Prop

/-- The condition guarding each mode. -/
def Computation.cond (c : Computation) : FM → Prop
  | .fm1 => c.C1
  | .fm2 => c.C2
  | .fm3 => c.C3
  | .fm4 => c.C4
  | .fm5 => c.C5
  | .fm6 => c.C6

/-- **`correct(t)` (§8.1):** "no edge that t's validation uses lies in Ŝ∖S". Domain truth, not derivable
    from the apparatus (Lemma 1, §3.4), so declared an uninterpreted constant: no computation literal
    evaluates it, and the covering axiom below cannot be refuted by construction. -/
axiom correct : Computation → Prop

/--
**CA1 (Evaluation Completeness, §8.2)**, covering direction only: the six conditions suffice for
`correct` (§8.8); the converse is not postulated (§8.8, §8.9). Since `correct` reads the verdict as it
stands after the evaluation, the axiom also carries that nothing after makes a verdict wrong (§8.6,
§20.5). CA2 is not bundled: the clock is the hypothesis `Time.SingleClock` (§8.2, §20.5).
-/
axiom evaluation_completeness (c : Computation) :
    (c.C1 ∧ c.C2 ∧ c.C3 ∧ c.C4 ∧ c.C5 ∧ c.C6) → correct c

/-- **6-FM completeness (§8.8).** A failure of correctness violates at least one condition: CA1 by
    classical De Morgan, no further assumption. -/
theorem fm_basis_covers (c : Computation) (h : ¬ correct c) :
    ¬c.C1 ∨ ¬c.C2 ∨ ¬c.C3 ∨ ¬c.C4 ∨ ¬c.C5 ∨ ¬c.C6 := by
  -- De Morgan over the 6-fold conjunction by hand (no mathlib `tauto`).
  apply Classical.byContradiction
  intro hc
  apply h
  apply evaluation_completeness c
  refine ⟨?_, ?_, ?_, ?_, ?_, ?_⟩
  · exact Classical.byContradiction (fun hn => hc (Or.inl hn))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inl hn)))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inr (Or.inl hn))))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inr (Or.inr (Or.inl hn)))))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inr (Or.inr (Or.inr (Or.inl hn))))))
  · exact Classical.byContradiction (fun hn => hc (Or.inr (Or.inr (Or.inr (Or.inr (Or.inr hn))))))

/-- The same with named modes: a failure means some mode is present. -/
theorem six_fm_complete (c : Computation) (h : ¬ correct c) :
    ∃ fm : FM, ¬ c.cond fm := by
  apply Classical.byContradiction
  intro hall
  apply h
  apply evaluation_completeness c
  exact ⟨ Classical.byContradiction (fun hn => hall ⟨.fm1, hn⟩),
          Classical.byContradiction (fun hn => hall ⟨.fm2, hn⟩),
          Classical.byContradiction (fun hn => hall ⟨.fm3, hn⟩),
          Classical.byContradiction (fun hn => hall ⟨.fm4, hn⟩),
          Classical.byContradiction (fun hn => hall ⟨.fm5, hn⟩),
          Classical.byContradiction (fun hn => hall ⟨.fm6, hn⟩) ⟩

/-! ### Independence — the six witnesses (§8.8), axiom-free

Per mode, a computation violating exactly that condition: `Cₖ := (k ≠ fm)`. This shows isolability
over six free conditions; that §8.8's scenarios realize the witnesses, a lone violation breaking
`correct`, is argued (§20.4), not derived — `correct` is uninterpreted and CA1 gives only sufficiency. -/

/-- The witness isolating one failing condition. -/
def isolatedFailure (fm : FM) : Computation where
  C1 := FM.fm1 ≠ fm
  C2 := FM.fm2 ≠ fm
  C3 := FM.fm3 ≠ fm
  C4 := FM.fm4 ≠ fm
  C5 := FM.fm5 ≠ fm
  C6 := FM.fm6 ≠ fm

/-- **Independence (§8.8).** Each mode's witness violates that mode's guard and satisfies every other.
    Honest reading: six free conditions, each settable apart (section header). -/
theorem fm_independent (fm : FM) :
    ¬ (isolatedFailure fm).cond fm ∧ ∀ fm', fm' ≠ fm → (isolatedFailure fm).cond fm' := by
  constructor
  · -- the fm-th guard is `fm ≠ fm`, false.
    cases fm <;> simp [isolatedFailure, Computation.cond]
  · -- any other guard is `fm' ≠ fm`, true by hypothesis.
    intro fm' hne
    cases fm' <;> simp_all [isolatedFailure, Computation.cond]

end GFSO.FailureModes
