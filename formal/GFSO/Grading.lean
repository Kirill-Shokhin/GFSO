/-
  GFSO — the ordinal severity skeleton `⪰_dom` (§19.6), machine-checked.

  `Probe(t)` is modelled as a characteristic vector over a fixed finite probe universe, and
  `t ⪰_dom t′` as `Probe(t) ⊇ Probe(t′)` on equal-length vectors (`dom`). Checked: reflexivity,
  transitivity and antisymmetry on probe-sets for every vector, by induction (`dom_refl_all`,
  `dom_trans_all`, `dom_antisymm_all`); over the length-3 carrier `allP3`, the same by `decide`, with
  count-independence and partiality by witness and a negative control. Elementary and axiom-free, no ℝ:
  the cardinal SEV (§19.6) is not here. Not modelled: what a probe is, and the restriction to the
  non-redundant probes.
-/
import GFSO.Fsm   -- only for the namespace-open habits; nothing FSM-specific is used

namespace GFSO.Grading

/-- `Probe(t)` as a characteristic vector: `true` at a slot = the node survived that probe. -/
abbrev ProbeSet := List Bool

/-- `a ⊇ b` on equal-length vectors (∀ slot, `b`-has → `a`-has): `Probe(t) ⊇ Probe(t′)`. -/
def dom : ProbeSet → ProbeSet → Bool
  | [],      []      => true
  | a :: as, b :: bs => ((!b) || a) && dom as bs
  | _,       _       => false          -- length mismatch: not comparable in this model

/-- How many probes a node survived — the count that yields no severity (§19.6). -/
def card (a : ProbeSet) : Nat := (a.filter id).length

/-- The universe of length-3 characteristic vectors (2³ = 8) — the finite carrier for the checks. -/
def allP3 : List ProbeSet :=
  [ [false,false,false], [true,false,false], [false,true,false], [false,false,true],
    [true,true,false],   [true,false,true],  [false,true,true],  [true,true,true] ]

/-! ### (1) ⪰_dom is a PREORDER (reflexive + transitive) — soundness -/

theorem dom_reflexive : allP3.all (fun a => dom a a) = true := by decide

theorem dom_transitive :
    allP3.all (fun a => allP3.all (fun b => allP3.all (fun c =>
      (!(dom a b && dom b c)) || dom a c))) = true := by decide

/-! ### (2) COUNT-INDEPENDENCE — "no probe count yields severity" (§19.6)

    Witness: `a` survived 2 probes, `b` 1, yet `a` does not dominate `b` (b's probe sits in a slot a
    lacks). -/

theorem dom_count_independent :
    ∃ a b : ProbeSet, card a > card b ∧ dom a b = false := by
  refine ⟨[true, true, false], [false, false, true], ?_, ?_⟩ <;> decide

/-- Over the whole carrier: some higher-count vector fails to dominate a lower-count one. -/
theorem dom_count_not_monotone :
    allP3.any (fun a => allP3.any (fun b =>
      decide (card a > card b) && !(dom a b))) = true := by decide

/-! ### (3) PARTIAL — "only nested probe-sets compare" (§19.6) -/

theorem dom_partial :
    allP3.any (fun a => allP3.any (fun b => (!(dom a b)) && (!(dom b a)))) = true := by decide

/-- Concrete incomparable pair: `{p1}` and `{p2}`. -/
theorem dom_incomparable_witness :
    dom [true,false,false] [false,true,false] = false
    ∧ dom [false,true,false] [true,false,false] = false := by decide

/-! ### Antisymmetry up to equal probe-sets (a genuine partial order on the sets themselves) -/

theorem dom_antisymmetric :
    allP3.all (fun a => allP3.all (fun b =>
      (!(dom a b && dom b a)) || decide (a = b))) = true := by decide

/-- NEGATIVE CONTROL — `dom` is not the constant `true` (else the order claims are empty). -/
theorem dom_not_constant_true :
    allP3.any (fun a => allP3.any (fun b => !(dom a b))) = true := by decide

/-! ### The order properties for every `ProbeSet`, by induction on the vector

    These are what §19.6 cites; the `allP3` checks above stay as the concrete carrier and the negative
    control. -/

theorem dom_refl_all : ∀ a : ProbeSet, dom a a = true
  | [] => rfl
  | x :: xs => by
      have ih := dom_refl_all xs
      cases x <;> simp [dom, ih]

theorem dom_trans_all : ∀ a b c : ProbeSet, dom a b = true → dom b c = true → dom a c = true := by
  intro a
  induction a with
  | nil => intro b c h1 h2; cases b <;> cases c <;> simp_all [dom]
  | cons x xs ih =>
    intro b c h1 h2
    cases b with
    | nil => simp [dom] at h1
    | cons y ys =>
      cases c with
      | nil => simp [dom] at h2
      | cons z zs =>
        simp [dom, Bool.and_eq_true] at h1 h2 ⊢
        exact ⟨by cases x <;> cases y <;> cases z <;> simp_all, ih ys zs h1.2 h2.2⟩

theorem dom_antisymm_all : ∀ a b : ProbeSet, dom a b = true → dom b a = true → a = b := by
  intro a
  induction a with
  | nil => intro b h1 h2; cases b <;> simp_all [dom]
  | cons x xs ih =>
    intro b h1 h2
    cases b with
    | nil => simp [dom] at h1
    | cons y ys =>
      simp [dom, Bool.and_eq_true] at h1 h2
      have hxy : x = y := by cases x <;> cases y <;> simp_all
      have htl : xs = ys := ih ys h1.2 h2.2
      rw [hxy, htl]

end GFSO.Grading
