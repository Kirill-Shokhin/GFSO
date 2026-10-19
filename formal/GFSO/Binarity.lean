/-
  GFSO — Tier 2: the defense of |L| = 2 against a graded scale (§7.1). Its source is A1 (the `Bool`
  verdict type, `Ontology.Verdict`); here the pigeonhole: for `act : L → Act` with |Act| = 2,
  surjectivity and injectivity — the hypotheses of `L_forced_two`, kind (c) of §20.5 — force |L| = 2.
  |Act| = 2 is the two-constructor type `Act`, kind (b). No mathlib, no `decide` over the abstract `L`.
-/

namespace GFSO.Binarity

/-- Injectivity, mathlib-free (§7.1: distinct values, distinct actions). -/
def Injective {α β : Type} (f : α → β) : Prop := ∀ ⦃x y⦄, f x = f y → x = y

/-- Surjectivity (§7.1: both actions reachable). -/
def Surjective {α β : Type} (f : α → β) : Prop := ∀ b, ∃ a, f a = b

/-- **Act (§7.1)**: intervene, and its negation, waiting. |Act| = 2 is a covering claim (§7.1), carried
    by this type (§20.5 (b)). -/
inductive Act | intervene | wait
deriving DecidableEq, Repr

/-- `|Act| = 2`: two distinct elements, and nothing else. -/
theorem Act_has_two : ∃ a b : Act, a ≠ b ∧ ∀ x : Act, x = a ∨ x = b := by
  refine ⟨Act.intervene, Act.wait, by decide, ?_⟩
  intro x; cases x <;> decide

/--
**|L| = 2 (§7.1, the pigeonhole).** Surjectivity (`complete`) gives two witnesses, |L| ≥ 2; injectivity
(`nonredundant`) pins every value to one of them, |L| ≤ 2.
-/
theorem L_forced_two {L : Type} (act : L → Act)
    (complete : Surjective act) (nonredundant : Injective act) :
    ∃ a b : L, a ≠ b ∧ ∀ x : L, x = a ∨ x = b := by
  -- |L| ≥ 2 : surjectivity gives a preimage of each action.
  obtain ⟨a, ha⟩ := complete Act.intervene   -- act a = intervene
  obtain ⟨b, hb⟩ := complete Act.wait        -- act b = wait
  refine ⟨a, b, ?_, ?_⟩
  · -- a ≠ b, because their images differ (intervene ≠ wait).
    intro hab
    rw [hab] at ha        -- ha : act b = intervene
    rw [ha] at hb         -- hb : intervene = wait
    exact absurd hb (by decide)
  · -- |L| ≤ 2 : every x maps to intervene or wait, and injectivity pins it to a or b.
    intro x
    cases hx : act x with
    | intervene => left;  apply nonredundant; rw [hx, ha]
    | wait      => right; apply nonredundant; rw [hx, hb]

/-! ### Attainment: `Bool` meets the requirements

The pass/fail scale with its decision map is surjective and injective, so two is attained, not only
bounded. -/

/-- The decision map: `pass ↦ wait`, `fail ↦ intervene`. -/
def boolAct : Bool → Act
  | true  => Act.wait
  | false => Act.intervene

theorem boolAct_injective  : Injective boolAct := by
  intro x y h; cases x <;> cases y <;> simp_all [boolAct]

theorem boolAct_surjective : Surjective boolAct := by
  intro a; cases a
  · exact ⟨false, rfl⟩
  · exact ⟨true, rfl⟩

/-- `Bool` meets §7.1's requirements: |L| = 2 is attained. -/
theorem bool_scale_valid :
    ∃ a b : Bool, a ≠ b ∧ ∀ x : Bool, x = a ∨ x = b :=
  L_forced_two boolAct boolAct_surjective boolAct_injective

end GFSO.Binarity
