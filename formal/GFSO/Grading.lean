/-
  GFSO — the ordinal severity skeleton ⪰_dom (canon §6.3), machine-checked.

  Canon §6.3: FM-3 yields a **dominance preorder** ⪰_dom on passed nodes. `Probe(t)` = the set of
  decidable discriminators a node survived (its own criterion + the integration implication + the
  children's probes, recursively). `t ⪰_dom t′` ⟺ `Probe(t) ⊇ Probe(t′)` — t survived a ⊇-superset of
  t′'s NON-REDUNDANT probes. The canon claims it is: (1) probability-free and SOUND (a genuine preorder on nodes);
  (2) count-INDEPENDENT ("a probe count yields no severity — 10 weak < 1 strong"); (3) PARTIAL
  ("incomparable sets are correctly left unordered", "coarser than Mayo"); (4) ANTISYMMETRIC on
  probe-sets (so a partial order on the sets, not on nodes).

  This file models `Probe(t)` as a characteristic vector over a fixed finite probe universe and
  machine-checks (1)–(3) plus antisymmetry on probe-sets. Elementary, axiom-free `decide`. No ℝ (the point: it is probability-FREE;
  the cardinal SEV over ℝ is the imported half, §6.3, not here).
-/
import GFSO.Fsm   -- only for the namespace-open habits; nothing FSM-specific is used

namespace GFSO.Grading

/-- `Probe(t)` as a characteristic vector over a fixed universe of probes (here 3 probe slots).
    `true` at a slot = that discriminating probe was survived by the node. -/
abbrev ProbeSet := List Bool

/-- `a ⊇ b` on equal-length characteristic vectors: every probe in `b` is also in `a`
    (∀ slot, `b`-has → `a`-has). This is the `⪰_dom` relation `Probe(t) ⊇ Probe(t′)`. -/
def dom : ProbeSet → ProbeSet → Bool
  | [],      []      => true
  | a :: as, b :: bs => ((!b) || a) && dom as bs
  | _,       _       => false          -- length mismatch: not comparable in this model

/-- How many probes a node survived (the *count* the canon says must NOT drive severity). -/
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

/-! ### (2) COUNT-INDEPENDENCE — "a probe count yields no severity (10 weak < 1 strong)"

    A node with a strictly LARGER survived-count does NOT thereby dominate one with fewer: dominance
    is nested-set containment, not cardinality. Witness: `a` survived 2 probes, `b` survived 1, yet
    `a` does NOT dominate `b` (b's probe sits in a slot a lacks). -/

theorem dom_count_independent :
    ∃ a b : ProbeSet, card a > card b ∧ dom a b = false := by
  refine ⟨[true, true, false], [false, false, true], ?_, ?_⟩ <;> decide

/-- Stated over the whole carrier: there EXIST pairs where the higher-count vector fails to dominate
    the lower-count one — so count is not a sound severity order. -/
theorem dom_count_not_monotone :
    allP3.any (fun a => allP3.any (fun b =>
      decide (card a > card b) && !(dom a b))) = true := by decide

/-! ### (3) PARTIAL — incomparable sets are left unordered (⪰_dom is not a total order) -/

theorem dom_partial :
    allP3.any (fun a => allP3.any (fun b => (!(dom a b)) && (!(dom b a)))) = true := by decide

/-- Concrete incomparable pair: `{p1}` and `{p2}` — neither dominates the other (different scope
    regions, "correctly left unordered", §6.3). -/
theorem dom_incomparable_witness :
    dom [true,false,false] [false,true,false] = false
    ∧ dom [false,true,false] [true,false,false] = false := by decide

/-! ### Antisymmetry up to equal probe-sets (a genuine partial order on the sets themselves) -/

theorem dom_antisymmetric :
    allP3.all (fun a => allP3.all (fun b =>
      (!(dom a b && dom b a)) || decide (a = b))) = true := by decide

/-- NEGATIVE CONTROL — `dom` is not vacuously the constant `true` (else the preorder claims are empty). -/
theorem dom_not_constant_true :
    allP3.any (fun a => allP3.any (fun b => !(dom a b))) = true := by decide

/-! ### The order properties, universally — not only over the length-3 carrier

    The `allP3` checks above are exhaustive at one arity. The order claims the canon makes are
    arity-independent, so they are proved here for **every** `ProbeSet`, by induction on the
    characteristic vector. These are what the canon's "preorder on nodes / partial order on
    probe-sets" cites; the finite checks remain as the concrete carrier plus the negative control. -/

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
