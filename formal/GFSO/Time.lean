/-
  GFSO — Tier 3b: the operational axis (§8.2). The three phases need no clock: coverage holds for any
  relation, disjointness from asymmetry, which every strict causal order has. Totality — CA2, the single
  clock, once the fourth axiom (§20.5) — is the hypothesis `SingleClock` and buys only the reading of the
  middle cell. This module declares no axiom.

  Part 1: the phases around one event `e` — `phases_exhaustive`, `phases_disjoint`,
  `asymmetry_necessary`, `asym_of_irrefl_trans`. Part 2: what `SingleClock` buys —
  `op_trichotomy_of_total`, `total_collapses_concurrent`. Part 3: the phases of the application [f, e]
  (§8.2) — `app_phases_exhaustive`, `app_phases_disjoint`, `app_total_during` — of which Parts 1–2 are
  the case f = e.
  Not claimed: that asymmetry is the unique weakest premise of disjointness (`asymmetry_necessary` is one
  witness), nor that `phases_disjoint` is deep — its before-vs-after clause unfolds to `Asymmetric`.
-/

namespace GFSO.Time

/-! ### Part 1 — the phases around one event, over an arbitrary relation -/

variable {α : Type}

/-- **Concurrent**: neither precedes the other. Under a total order this is equality; under
    happens-before, incomparability. -/
def Concurrent (prec : α → α → Prop) (x e : α) : Prop := ¬ prec x e ∧ ¬ prec e x

/-- **Asymmetric**: nothing both precedes and follows something. -/
def Asymmetric (prec : α → α → Prop) : Prop := ∀ a b, prec a b → ¬ prec b a

/-- **Exhaustiveness needs no assumption.** For any relation, `x` is before, concurrent with or after
    `e` — excluded middle. -/
theorem phases_exhaustive (prec : α → α → Prop) (e x : α) :
    prec x e ∨ Concurrent prec x e ∨ prec e x := by
  cases Classical.em (prec x e) with
  | inl h1 => exact Or.inl h1
  | inr h1 =>
    cases Classical.em (prec e x) with
    | inl h2 => exact Or.inr (Or.inr h2)
    | inr h2 => exact Or.inr (Or.inl ⟨h1, h2⟩)

/-- **Disjointness from asymmetry.** The first two clauses need nothing; before-vs-after is
    `Asymmetric prec` unfolded. -/
theorem phases_disjoint (prec : α → α → Prop) (h : Asymmetric prec) (e x : α) :
    ¬(prec x e ∧ Concurrent prec x e) ∧
    ¬(Concurrent prec x e ∧ prec e x) ∧
    ¬(prec x e ∧ prec e x) := by
  refine ⟨?_, ?_, ?_⟩
  · intro ⟨hb, hc⟩; exact hc.1 hb           -- concurrent says ¬before
  · intro ⟨hc, ha⟩; exact hc.2 ha           -- concurrent says ¬after
  · intro ⟨hb, ha⟩; exact h x e hb ha       -- ← the only place asymmetry is used

/-- **The trichotomy in full**: for any asymmetric relation the three phases are exhaustive and
    before/after exclusive. No total order. -/
theorem operational_trichotomy (prec : α → α → Prop) (h : Asymmetric prec) (e x : α) :
    (prec x e ∨ Concurrent prec x e ∨ prec e x) ∧
    (¬(prec x e ∧ prec e x)) :=
  ⟨phases_exhaustive prec e x, (phases_disjoint prec h e x).2.2⟩

/-- **Asymmetry cannot be dropped**: under a symmetric relation (the total one on `Unit`) before and
    after overlap. One witness, not minimality. -/
theorem asymmetry_necessary :
    ∃ (prec : Unit → Unit → Prop) (e x : Unit),
      prec x e ∧ prec e x ∧ ¬ Asymmetric prec := by
  refine ⟨fun _ _ => True, (), (), trivial, trivial, ?_⟩
  intro h
  exact (h () () trivial) trivial

/-- **Every strict order is asymmetric** — total, partial (happens-before), interval and branching time
    alike: the step that frees the axis from the clock. -/
theorem asym_of_irrefl_trans (prec : α → α → Prop)
    (hirr : ∀ a, ¬ prec a a)
    (htr : ∀ a b c, prec a b → prec b c → prec a c) :
    Asymmetric prec := by
  intro a b hab hba
  exact hirr a (htr a b a hab hba)

/-- Under any strict order the axis is a three-cell partition. -/
theorem trichotomy_of_strict_order (prec : α → α → Prop)
    (hirr : ∀ a, ¬ prec a a) (htr : ∀ a b c, prec a b → prec b c → prec a c) (e x : α) :
    (prec x e ∨ Concurrent prec x e ∨ prec e x) ∧ (¬(prec x e ∧ prec e x)) :=
  operational_trichotomy prec (asym_of_irrefl_trans prec hirr htr) e x

/-! ### Part 2 — CA2 and what it buys

The single clock is carried as the hypothesis `SingleClock`, not an `axiom`: the phase count is
axiom-free (Part 1), so postulating totality would claim a dependency the count does not have
(§8.2, §20.5 (c)). It stays visible in the type, as `agent_necessary`'s premises do. -/

/-- **Totality of a temporal order** — CA2, the single clock (§8.2). A hypothesis, no covering axiom
    (§20.5); false under concurrency. -/
def SingleClock (prec : α → α → Prop) : Prop := ∀ a b, prec a b ∨ a = b ∨ prec b a

/-- The trichotomy under the single clock, axiom-free (totality a hypothesis). Not the canon's
    derivation, which needs only a strict causal order (`app_phases_exhaustive`, `app_phases_disjoint`). -/
theorem op_trichotomy_of_total (prec : α → α → Prop) (hc : SingleClock prec) (e x : α) :
    prec x e ∨ x = e ∨ prec e x :=
  hc x e

/-- **What CA2 buys around one event**: the middle cell collapses from concurrent to equal, read as
    *during*. Nothing else (Part 1). -/
theorem total_collapses_concurrent (prec : α → α → Prop) (hc : SingleClock prec)
    (e x : α) (h : Concurrent prec x e) : x = e := by
  cases hc x e with
  | inl hb => exact absurd hb h.1
  | inr hr => cases hr with
    | inl heq => exact heq
    | inr ha => exact absurd ha h.2

/-! ### Part 3 — the phases of the application [f, e] (§8.2)

Relative to the split's fixing `f` and the evaluation event `e`: wholly before `f` (FM-6's phase),
neither before `f` nor after `e` (FM-5's), wholly after `e` (no mode, §8.6). -/

/-- Wholly before the application: the event precedes the fixing. -/
def BeforeApp (prec : α → α → Prop) (f x : α) : Prop := prec x f
/-- Over the application: neither before the fixing nor after the evaluation. -/
def DuringApp (prec : α → α → Prop) (f e x : α) : Prop := ¬ prec x f ∧ ¬ prec e x
/-- Wholly after the application: the event follows the evaluation. -/
def AfterApp (prec : α → α → Prop) (e x : α) : Prop := prec e x

/-- **Exhaustiveness over the application needs no assumption** — excluded middle, as in Part 1. -/
theorem app_phases_exhaustive (prec : α → α → Prop) (f e x : α) :
    BeforeApp prec f x ∨ DuringApp prec f e x ∨ AfterApp prec e x := by
  cases Classical.em (prec x f) with
  | inl h1 => exact Or.inl h1
  | inr h1 =>
    cases Classical.em (prec e x) with
    | inl h2 => exact Or.inr (Or.inr h2)
    | inr h2 => exact Or.inr (Or.inl ⟨h1, h2⟩)

/-- **Disjointness over the application.** The middle cell excludes the others by definition;
    before-vs-after needs a strict order and §8.2's "f is not after e", encoded as `f = e ∨ prec f e` —
    stronger than `¬ prec e f`, which with transitivity would also suffice. -/
theorem app_phases_disjoint (prec : α → α → Prop)
    (hirr : ∀ a, ¬ prec a a) (htr : ∀ a b c, prec a b → prec b c → prec a c)
    (f e : α) (hfe : f = e ∨ prec f e) (x : α) :
    ¬(BeforeApp prec f x ∧ DuringApp prec f e x) ∧
    ¬(DuringApp prec f e x ∧ AfterApp prec e x) ∧
    ¬(BeforeApp prec f x ∧ AfterApp prec e x) := by
  refine ⟨fun ⟨hb, hd⟩ => hd.1 hb, fun ⟨hd, ha⟩ => hd.2 ha, ?_⟩
  intro ⟨hb, ha⟩
  cases hfe with
  | inl hEq => subst hEq; exact hirr x (htr x f x hb ha)
  | inr hfe => exact hirr x (htr x e x (htr x f e hb hfe) ha)

/-- **What a single clock buys over the application**: the middle cell is the closed interval `[f, e]`,
    read as *during*, rather than "causally not outside it". Nothing else. -/
theorem app_total_during (prec : α → α → Prop) (hc : SingleClock prec) (f e x : α)
    (h : DuringApp prec f e x) : (x = f ∨ prec f x) ∧ (x = e ∨ prec x e) := by
  refine ⟨?_, ?_⟩
  · cases hc x f with
    | inl hb => exact absurd hb h.1
    | inr hr => cases hr with
      | inl heq => exact Or.inl heq
      | inr ha => exact Or.inr ha
  · cases hc x e with
    | inl hb => exact Or.inr hb
    | inr hr => cases hr with
      | inl heq => exact Or.inl heq
      | inr ha => exact absurd ha h.2

end GFSO.Time
