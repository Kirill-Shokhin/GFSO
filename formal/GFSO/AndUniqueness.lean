/-
  GFSO — LIGHT spike target: Theorem 2 (uniqueness of AND).
  Canon `docs/applied_gfso_v4_en.md` §11.2 (|L|=2) + §11.3 (Thm 2).

  Claim (§11.3): on {0,1}, AND is the UNIQUE binary operation satisfying
    (1) commutativity + associativity,
    (2) an absorbing element 0  (∃0: ⊗(0,x)=0 — from non-redundancy: a failed child ⇒ parent fails),
    (3) nontriviality (not constant).
  Canon discharges it by enumerating all 16 binary ops. We do the SAME enumeration
  and discharge by `decide` — a genuine kernel-checked exhaustion, no mathlib needed.

  Encoding: L = Bool (false = 0, true = 1). A binary op is its 4-cell truth table.
-/

namespace GFSO.AndUniqueness

/-- A binary operation on {0,1}, as its truth table: the outputs on the 4 input pairs. -/
structure Op where
  ff : Bool   -- ⊗(0,0)
  ft : Bool   -- ⊗(0,1)
  tf : Bool   -- ⊗(1,0)
  tt : Bool   -- ⊗(1,1)
deriving DecidableEq, Repr

/-- Apply the op. -/
def Op.app (o : Op) : Bool → Bool → Bool
  | false, false => o.ff
  | false, true  => o.ft
  | true,  false => o.tf
  | true,  true  => o.tt

/-- The AND truth table. -/
def andOp : Op := ⟨false, false, false, true⟩

-- The three defining requirements of §11.3, as decidable Bool predicates over the finite domain.

/-- Commutativity: the only asymmetric pair is (0,1)/(1,0). -/
def commutative (o : Op) : Bool := o.ft == o.tf

/-- Associativity: check all 8 triples of the finite domain (no ∀ needed — Bool³ is enumerated). -/
def associative (o : Op) : Bool :=
  let dom := [false, true]
  (dom.flatMap fun a => dom.flatMap fun b => dom.map fun c =>
      o.app (o.app a b) c == o.app a (o.app b c)).all id

/-- 0 (=false) is a (two-sided) absorbing element: ⊗(0,x)=0 and ⊗(x,0)=0. -/
def absorbing0 (o : Op) : Bool := (!o.ff) && (!o.ft) && (!o.tf)

/-- Nontrivial: the op is not the constant 0 (some cell is 1). -/
def nontrivial (o : Op) : Bool := o.ff || o.ft || o.tf || o.tt

/-- The four §11.3 requirements conjoined. -/
def satisfiesReqs (o : Op) : Bool :=
  commutative o && associative o && absorbing0 o && nontrivial o

/-- Enumeration of ALL 16 binary operations on {0,1} (the canon's "16 operations"). -/
def allOps : List Op :=
  let b := [false, true]
  b.flatMap fun ff => b.flatMap fun ft => b.flatMap fun tf => b.map fun tt =>
    ⟨ff, ft, tf, tt⟩

/-- The enumeration is exhaustive: every op appears. -/
theorem mem_allOps (o : Op) : o ∈ allOps := by
  obtain ⟨ff, ft, tf, tt⟩ := o
  cases ff <;> cases ft <;> cases tf <;> cases tt <;> decide

/-- THE finite verification: across all 16 ops, satisfying the requirements ⇒ being AND.
    Discharged by `decide` (kernel-checked exhaustion of the 16-op table — the §11.3 proof). -/
theorem and_unique_check :
    allOps.all (fun o => !(satisfiesReqs o) || decide (o = andOp)) = true := by decide

/-- **Theorem 2 (§11.3): AND is the unique nontrivial aggregation.**
    Lifted from the finite check to a genuine ∀ over all binary ops on {0,1}. -/
theorem and_unique (o : Op) (h : satisfiesReqs o = true) : o = andOp := by
  have hall := List.all_eq_true.mp and_unique_check o (mem_allOps o)
  rw [h] at hall
  simpa using of_decide_eq_true hall

/-- Sanity: AND itself satisfies the requirements (the ∃-witness, so the theorem is non-vacuous). -/
theorem and_satisfies : satisfiesReqs andOp = true := by decide

end GFSO.AndUniqueness
