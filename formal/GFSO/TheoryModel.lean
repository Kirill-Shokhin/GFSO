/-
  GFSO — Tier 7: the theory model (Ch. 3–4). Lemma 1's form (§3.4) and its consequence that no function
  of the formal view yields S; agent necessity (§4.1) as the elimination step over the knowledge
  sources. The three eliminations are hypotheses of `agent_necessary` (kind (c), §20.5): not-apparatus
  (grounded in substance by `no_apparatus_yields_S`, not linked, §20.4), no-declaration (Lemma 2, §3.4)
  and no-luck (d4's residue, §4.1).
-/

namespace GFSO.TheoryModel

/-- A composition edge `(t, {tⱼ})` (§3.1), parent and children as ids. -/
structure Composition where
  parent : Nat
  children : List Nat
deriving DecidableEq, Repr

instance : Inhabited Composition := ⟨⟨0, []⟩⟩

/-- The S-free data the apparatus sees (§3.3), abstracted to one coordinate: its richness is
    irrelevant to Lemma 1's form. -/
structure FormalView where
  formal : Bool

/-- A domain: the formal view plus `S` (§3.1), a predicate over compositions that the view does not
    determine. -/
structure Domain where
  view : FormalView
  S : Composition → Prop

/--
**Lemma 1 (§3.4) — its form.** Two domains share one view and disagree on `S`.

**Honest reading.** `S` is a field independent of `view` and the apparatus is defined to see only
`view` (§3.3: "𝒜 is syntactically S-free"), so the underdetermination is definitional, not derived
from richer premises. What is checked gap-free is the step from S-freeness to "the apparatus cannot
yield S": `no_apparatus_yields_S`, the ground of the not-apparatus premise `agent_necessary` carries
unlinked.
-/
theorem lemma1_S_underdetermined :
    ∃ d₁ d₂ : Domain, d₁.view = d₂.view ∧ ∃ c : Composition, ¬ (d₁.S c ↔ d₂.S c) := by
  refine ⟨⟨⟨true⟩, fun _ => True⟩, ⟨⟨true⟩, fun _ => False⟩, rfl, default, ?_⟩
  intro h
  exact h.mp trivial

/-- No function from the formal view to `S` is right on every domain: the two Lemma-1 witnesses refute
    any candidate. -/
theorem no_apparatus_yields_S :
    ¬ ∃ f : FormalView → (Composition → Prop), ∀ d : Domain, f d.view = d.S := by
  rintro ⟨f, hf⟩
  have h₁ := hf ⟨⟨true⟩, fun _ => True⟩
  have h₂ := hf ⟨⟨true⟩, fun _ => False⟩
  rw [h₁] at h₂
  have hTF : (True : Prop) = False := congrFun h₂ default
  exact hTF ▸ trivial

/-- The candidate grounds of knowledge of `S` (§4.1, d3–d4). -/
inductive KnowledgeSource | apparatus | declaration | luck | contact
deriving DecidableEq, Repr

/--
**Agent necessity (§4.1, d1–d6)** — the elimination step only: given a source and the three exclusions
as hypotheses (`not_apparatus` by Lemma 1, `not_declaration` by Lemma 2, `not_luck` by S's
contingency), the source is contact. The exclusions are the canon's (§4.1), not proved here.
-/
theorem agent_necessary
    (src : KnowledgeSource)
    (not_apparatus : src ≠ .apparatus)
    (not_declaration : src ≠ .declaration)
    (not_luck : src ≠ .luck) :
    src = .contact := by
  cases src <;> simp_all

end GFSO.TheoryModel
