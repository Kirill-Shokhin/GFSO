/-
  GFSO — TIER 3b: the operational axis, CA2, and its exact minimal replacement (§12.8).

  ── The canon as it stands ──────────────────────────────────────────────────────────────────
  The position v3.9 §4.8 held, which v4 §12.8 REFUTES (quoted for contrast, not as v4's claim):
    > **CA2 (the evaluation as one logical event).** The validation of t is one logical event on a
    > single local timer ⟹ local time is totally ordered (which is what yields the trichotomy of the
    > operational axis)… Under concurrent time (happens-before — a partial order) the trichotomy
    > weakens — the **explicit price** of CA2.
    (v4 §12.8 discharges this: the phase COUNT is axiom-free; totality buys only the reading of the
    middle cell. The block above is the position the discharge argues against, kept for contrast.)

  So, on THAT reading, the three operational phases (⟹ FM-6 / FM-5 / FM-7) were made to rest on a
  SINGLE CLOCK. (v4 §12.8 does not: the phase count is axiom-free — see Part 1 below.)

  ── What this module shows instead ──────────────────────────────────────────────────────────
    1. `phases_exhaustive`  — the three cells COVER everything for an ARBITRARY relation.
                              **No assumption whatsoever.** Coverage never needed a clock.
    2. `phases_disjoint`    — pairwise exclusivity holds under ASYMMETRY. *Honest note:* the
                              before-vs-after clause `¬(prec x e ∧ prec e x)` unfolds
                              DEFINITIONALLY to `Asymmetric prec`, so this is an unfolding, not a
                              discovered minimal premise. The point is only that **totality is not
                              used anywhere.**
    3. `asymmetry_necessary` — asymmetry cannot simply be dropped: one symmetric relation already
                              makes "before" and "after" overlap. (One witness — not a claim that
                              asymmetry is the unique weakest sufficient condition.)
    4. `asym_of_irrefl_trans` — EVERY strict order is asymmetric (irreflexive + transitive ⟹ asymmetric).
                              Hence total orders, partial orders, **happens-before**, interval and
                              branching time all qualify. This is the load-bearing step.
    5. `total_collapses_concurrent` — totality (CA2) buys exactly ONE thing: it collapses the
                              middle cell from "concurrent" to "equal", so it may be read as
                              *during* rather than *concurrent*. Nothing else.

  ⇒ **The defensible claim:** CA2 (totality) can be replaced by asymmetry, which every strict
    order — including happens-before — satisfies. The count of operational failure modes stays 3, so
    the 7-FM basis survives concurrency, and FM-5 (freshness) reads as "concurrent with the
    evaluation" — precisely the read/write race of distributed systems. The cost v3.9 declared
    ("the trichotomy weakens") is avoidable — and v4 §12.8 carries that finding.
    NOT claimed: that asymmetry is the unique minimal premise, nor that (2) is a deep theorem.

  This finding is carried by the canon (§12.8): CA2 is redundant for the operational taxonomy.
  The canon is truth; `formal/` exhibits the cost and the exit.
-/

namespace GFSO.Time

/-! ### Part 1 — the general result, over an arbitrary temporal relation -/

variable {α : Type}

/-- Two events are **concurrent** when neither causally precedes the other. Under a total order this
    degenerates to equality; under happens-before it is genuine incomparability. -/
def Concurrent (prec : α → α → Prop) (x e : α) : Prop := ¬ prec x e ∧ ¬ prec e x

/-- A relation is **asymmetric** when nothing both precedes and follows something. -/
def Asymmetric (prec : α → α → Prop) : Prop := ∀ a b, prec a b → ¬ prec b a

/--
**(1) Exhaustiveness needs NO assumption.** For *any* relation `prec` — total, partial, cyclic,
arbitrary — every event `x` is strictly-before `e`, concurrent with `e`, or strictly-after `e`.
Pure excluded middle. Coverage of the operational axis never depended on a clock.
-/
theorem phases_exhaustive (prec : α → α → Prop) (e x : α) :
    prec x e ∨ Concurrent prec x e ∨ prec e x := by
  cases Classical.em (prec x e) with
  | inl h1 => exact Or.inl h1
  | inr h1 =>
    cases Classical.em (prec e x) with
    | inl h2 => exact Or.inr (Or.inr h2)
    | inr h2 => exact Or.inr (Or.inl ⟨h1, h2⟩)

/--
**(2) Disjointness needs EXACTLY asymmetry.** Given asymmetry, the three cells are pairwise
exclusive — a genuine partition. (Note the first two clauses need nothing at all; only
before-vs-after needs asymmetry. That is the entire content of the premise.)
-/
theorem phases_disjoint (prec : α → α → Prop) (h : Asymmetric prec) (e x : α) :
    ¬(prec x e ∧ Concurrent prec x e) ∧
    ¬(Concurrent prec x e ∧ prec e x) ∧
    ¬(prec x e ∧ prec e x) := by
  refine ⟨?_, ?_, ?_⟩
  · intro ⟨hb, hc⟩; exact hc.1 hb           -- concurrent says ¬before
  · intro ⟨hc, ha⟩; exact hc.2 ha           -- concurrent says ¬after
  · intro ⟨hb, ha⟩; exact h x e hb ha       -- ← the only place asymmetry is used

/-- **The operational trichotomy, in full.** For any *asymmetric* temporal relation the three phases
    form an exhaustive, pairwise-disjoint partition. No total order, no global clock. -/
theorem operational_trichotomy (prec : α → α → Prop) (h : Asymmetric prec) (e x : α) :
    (prec x e ∨ Concurrent prec x e ∨ prec e x) ∧
    (¬(prec x e ∧ prec e x)) :=
  ⟨phases_exhaustive prec e x, (phases_disjoint prec h e x).2.2⟩

/--
**(3) The premise is TIGHT: asymmetry cannot be dropped.** For a symmetric relation the "before" and
"after" cells overlap, so the three cases stop being a partition. Witness: the total relation on a
one-point type. Hence the premise cannot simply be DROPPED: some relation satisfying no such
condition breaks the partition. This is one witness, NOT a claim that asymmetry is the unique
weakest sufficient condition (the file header states the same hedge).
-/
theorem asymmetry_necessary :
    ∃ (prec : Unit → Unit → Prop) (e x : Unit),
      prec x e ∧ prec e x ∧ ¬ Asymmetric prec := by
  refine ⟨fun _ _ => True, (), (), trivial, trivial, ?_⟩
  intro h
  exact (h () () trivial) trivial

/--
**(4) Every strict order is asymmetric.** Irreflexive + transitive ⟹ asymmetric. Therefore the
trichotomy holds for total orders, **partial orders (happens-before)**, interval orders and
branching time alike — every reasonable model of evaluation time. This is what makes the
replacement of CA2 safe against concurrency *and* against other kinds of time.
-/
theorem asym_of_irrefl_trans (prec : α → α → Prop)
    (hirr : ∀ a, ¬ prec a a)
    (htr : ∀ a b c, prec a b → prec b c → prec a c) :
    Asymmetric prec := by
  intro a b hab hba
  exact hirr a (htr a b a hab hba)

/-- Corollary: under any strict order the operational axis is a genuine 3-cell partition. -/
theorem trichotomy_of_strict_order (prec : α → α → Prop)
    (hirr : ∀ a, ¬ prec a a) (htr : ∀ a b c, prec a b → prec b c → prec a c) (e x : α) :
    (prec x e ∨ Concurrent prec x e ∨ prec e x) ∧ (¬(prec x e ∧ prec e x)) :=
  operational_trichotomy prec (asym_of_irrefl_trans prec hirr htr) e x

/-! ### Part 2 — the canon as written: CA2, and exactly what it buys

CA2 (the single local timer, §12.8) is **NOT postulated as a covering axiom.** By §12.8 the
phase COUNT is axiom-free — Part 1 derives exhaustiveness with no assumption and the partition from
asymmetry alone (the definition of a strict causal order). Totality is therefore carried as an
explicit HYPOTHESIS `SingleClock`, not an `axiom`: it buys ONLY the rename of the middle cell
("concurrent" ↦ "during"), so postulating it would claim a count-dependency that does not exist. It
stays visible in the type, exactly like the signature hypotheses of `agent_necessary`. Hence this
module contributes NO axiom to `#print axioms` — the operational axis is fully clock-free. -/

/-- **Totality of a temporal order** — "a single local timer" (CA2, §12.8). A property of a
    relation, carried as a hypothesis rather than postulated: per §12.8 it is not a covering
    axiom; it only names the middle phase "during". It FAILS under concurrency. -/
def SingleClock (prec : α → α → Prop) : Prop := ∀ a b, prec a b ∨ a = b ∨ prec b a

/-- The canon's operational trichotomy AS THE CANON DERIVES IT — straight from totality. With
    totality a hypothesis (not an axiom) the result is axiom-free. -/
theorem op_trichotomy_of_total (prec : α → α → Prop) (hc : SingleClock prec) (e x : α) :
    prec x e ∨ x = e ∨ prec e x :=
  hc x e

/--
**What CA2 actually buys — and it is only this.** Under totality the middle cell collapses from
"concurrent" to *equal*, so it may be read as **during** instead of **concurrent**. Coverage and
disjointness never needed totality (Part 1). Drop the clock and the only casualty is the *name* of
the middle phase — FM-5 becomes "concurrent with the evaluation", the standard read/write race.
-/
theorem total_collapses_concurrent (prec : α → α → Prop) (hc : SingleClock prec)
    (e x : α) (h : Concurrent prec x e) : x = e := by
  cases hc x e with
  | inl hb => exact absurd hb h.1
  | inr hr => cases hr with
    | inl heq => exact heq
    | inr ha => exact absurd ha h.2

end GFSO.Time
