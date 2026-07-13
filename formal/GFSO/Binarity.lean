/-
  GFSO — Binarity of validation: the impossibility of |L| ≠ 2 (§3.2).

  Canon `docs/applied_gfso_v3.md` §3.2:

    V: T → L, act: L → A. Требования:
      (1) |A| = 2                       (excluded middle on "changes trajectory")
      (2) Полнота: act сюръективна       (both actions reachable)
      (3) Неизбыточность: act инъективна (distinct V-values → distinct actions)
    Тогда |L| = 2.  Доказательство: |L|≥2 из (2); |L|≤2 из (3) по принципу Дирихле.

  We formalize this as a genuine structural argument — no mathlib, no `decide` over the abstract
  scale `L`. `|A|=2` is the architectural input (§3.2: excluded middle gives the two actions,
  granularity of action is pushed into the tree, not into extra L-values); injectivity is forced
  by decision-relevance (§3.2 "Инъективность — вынужденная"). We take (2),(3) as the hypotheses
  the canon names and derive that `L` has EXACTLY two elements.
-/

namespace GFSO.Binarity

/-- Injectivity, spelled out (mathlib-free): different inputs ⟹ different outputs, in the
    contrapositive form Lean likes. This is §3.2 requirement (3), "неизбыточность". -/
def Injective {α β : Type} (f : α → β) : Prop := ∀ ⦃x y⦄, f x = f y → x = y

/-- Surjectivity, spelled out: every action is reached by some verdict. §3.2 requirement (2),
    "полнота". -/
def Surjective {α β : Type} (f : α → β) : Prop := ∀ b, ∃ a, f a = b

/-- **Action space A (§3.2).** Exactly two actions — the excluded middle on "does the agent
    action change the task trajectory or not". `|A| = 2` is architectural (the canon's design
    choice: action granularity lives in the decomposition tree, retry-hysteresis in the FSM
    state — not in extra values of the validation scale). -/
inductive Act | intervene | wait
deriving DecidableEq, Repr

/-- `|A| = 2`, stated elementarily as "two distinct elements, and nothing else". -/
theorem Act_has_two : ∃ a b : Act, a ≠ b ∧ ∀ x : Act, x = a ∨ x = b := by
  refine ⟨Act.intervene, Act.wait, by decide, ?_⟩
  intro x; cases x <;> decide

/--
**Theorem (impossibility of |L| ≠ 2, §3.2).**  Let `act : L → Act` be the decision map from a
validation scale `L` into the two-element action space. If

* `complete` — `act` is **surjective** (requirement (2): both actions are actually reachable), and
* `nonredundant` — `act` is **injective** (requirement (3): different verdicts must drive
  different actions — forced by decision-relevance, §3.2),

then `L` has **exactly two** elements. `|L| ≥ 2` comes from surjectivity onto the 2-element `Act`;
`|L| ≤ 2` from injectivity (Dirichlet / pigeonhole). Here both directions are one elementary
argument: surjectivity hands us two witnesses, injectivity forces everything to be one of them.
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

/-! ### The matching existence half (|L| ≥ 2 is realizable): `Bool` is a valid scale

The impossibility above is the *upper* pressure (can't exceed 2). The canon also needs both
actions genuinely reachable (else the system is defective, §3.2 table row (2)). The canonical
scale `L = Bool` (pass/fail) with the obvious decision map realizes this — so 2 is not merely an
upper bound but achieved. Together: the validation scale is forced to be exactly two-valued. -/

/-- The canonical decision map: `pass ↦ wait` (no intervention needed), `fail ↦ intervene`. -/
def boolAct : Bool → Act
  | true  => Act.wait
  | false => Act.intervene

theorem boolAct_injective  : Injective boolAct := by
  intro x y h; cases x <;> cases y <;> simp_all [boolAct]

theorem boolAct_surjective : Surjective boolAct := by
  intro a; cases a
  · exact ⟨false, rfl⟩
  · exact ⟨true, rfl⟩

/-- `Bool` (the pass/fail scale) satisfies the §3.2 requirements — so |L| = 2 is attained. -/
theorem bool_scale_valid :
    ∃ a b : Bool, a ≠ b ∧ ∀ x : Bool, x = a ∨ x = b :=
  L_forced_two boolAct boolAct_surjective boolAct_injective

end GFSO.Binarity
