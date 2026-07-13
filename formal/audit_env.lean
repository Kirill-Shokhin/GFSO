/-
  ENVIRONMENT AUDITOR — fail-closed. Run: `lake env lean audit_env.lean`.

  Three things are reported, and `scripts/check_closure.sh` acts on all three:

    DECL_AXIOM  <n>   an `axiom` we declared under GFSO.*
    DECL_OPAQUE <n>   an `opaque` we declared under GFSO.*  (an uninterpreted assumption that
                      `#print axioms` cannot see — always a violation)
    USES        <n>   an axiom actually USED, transitively, by SOME theorem under GFSO.*

  Why all three. Earlier versions were fail-OPEN twice over:
    * `#print axioms` on a HAND-LISTED set of theorems — forget to list a theorem and its axiom hides.
      Fixed: we enumerate every theorem in `GFSO.*` from the environment and collect its axioms.
    * a namespace filter — an axiom declared OUTSIDE `GFSO.*` (say `Externals.smuggled : 2 = 3`) but
      used by a GFSO theorem was invisible. Fixed: `USES` reports axioms by USE, wherever they live.
      The script then rejects anything outside {propext, Quot.sound, Classical.choice} ∪ whitelist —
      which also catches `sorryAx` (a hole) and `Lean.ofReduceBool`/`ofReduceNat` (i.e. `native_decide`).

  Note: presence of an axiom in the environment is NOT use. `sorryAx`, `lcProof` and friends are always
  *declared* by Lean core; only `USES` tells you whether a proof leaned on one.
-/
import Lean
import GFSO

open Lean Elab Command

#eval show CommandElabM Unit from do
  let env ← getEnv
  -- What we declared under GFSO.*, and every theorem under GFSO.* whose footprint we must inspect.
  let (declAx, declOp, thms) :=
    env.constants.fold
      (fun (a, o, t) n ci =>
        if n.isInternal || !(`GFSO).isPrefixOf n then (a, o, t)
        else match ci with
          | .axiomInfo _  => (a.push n, o, t)
          | .opaqueInfo _ => (a, o.push n, t)
          | .thmInfo _    => (a, o, t.push n)
          | _             => (a, o, t))
      ((#[] : Array Name), (#[] : Array Name), (#[] : Array Name))

  for n in declAx.qsort (fun a b => toString a < toString b) do
    IO.println s!"DECL_AXIOM  {n}"
  for n in declOp.qsort (fun a b => toString a < toString b) do
    IO.println s!"DECL_OPAQUE {n}"

  -- Transitive axiom footprint of EVERY GFSO theorem, unioned. No hand-maintained list.
  let mut used : NameSet := {}
  for t in thms do
    let axs ← liftCoreM <| Lean.collectAxioms t
    for a in axs do
      used := used.insert a

  let usedArr := used.toList.toArray.qsort (fun a b => toString a < toString b)
  for a in usedArr do
    IO.println s!"USES        {a}"
  IO.println s!"-- theorems audited: {thms.size}"
