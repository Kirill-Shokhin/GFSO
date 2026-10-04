/-
  GFSO — Tier 2: Thm 2, uniqueness of AND (§7.2), by the canon's own enumeration of the 16 binary
  operations on {0, 1}, discharged by `decide`. Encoding: `false` = 0 = fail; an operation is its 4-cell
  truth table. Nontriviality is read as "not constantly 0", the constant 1 being excluded by absorption.
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

-- §7.2's requirements, as Bool predicates over the finite domain.

/-- Commutativity: the only asymmetric pair is (0,1)/(1,0). -/
def commutative (o : Op) : Bool := o.ft == o.tf

/-- Associativity, over all 8 triples. -/
def associative (o : Op) : Bool :=
  let dom := [false, true]
  (dom.flatMap fun a => dom.flatMap fun b => dom.map fun c =>
      o.app (o.app a b) c == o.app a (o.app b c)).all id

/-- 0 (fail) is a two-sided absorbing element. -/
def absorbing0 (o : Op) : Bool := (!o.ff) && (!o.ft) && (!o.tf)

/-- Nontrivial: not the constant 0. -/
def nontrivial (o : Op) : Bool := o.ff || o.ft || o.tf || o.tt

/-- The requirements conjoined. -/
def satisfiesReqs (o : Op) : Bool :=
  commutative o && associative o && absorbing0 o && nontrivial o

/-- All 16 binary operations on {0,1}. -/
def allOps : List Op :=
  let b := [false, true]
  b.flatMap fun ff => b.flatMap fun ft => b.flatMap fun tf => b.map fun tt =>
    ⟨ff, ft, tf, tt⟩

/-- The enumeration is exhaustive. -/
theorem mem_allOps (o : Op) : o ∈ allOps := by
  obtain ⟨ff, ft, tf, tt⟩ := o
  cases ff <;> cases ft <;> cases tf <;> cases tt <;> decide

/-- The finite check: over all 16, meeting the requirements implies being AND (`decide`). -/
theorem and_unique_check :
    allOps.all (fun o => !(satisfiesReqs o) || decide (o = andOp)) = true := by decide

/-- **Thm 2 (§7.2)**, lifted from the finite check to every binary operation on {0,1}. -/
theorem and_unique (o : Op) (h : satisfiesReqs o = true) : o = andOp := by
  have hall := List.all_eq_true.mp and_unique_check o (mem_allOps o)
  rw [h] at hall
  simpa using of_decide_eq_true hall

/-- AND meets the requirements: the theorem is not vacuous. -/
theorem and_satisfies : satisfiesReqs andOp = true := by decide

end GFSO.AndUniqueness
