/-
  ENVIRONMENT AUDITOR — fail-closed. Run: `lake env lean audit_env.lean`.

  Three things are reported, and `scripts/check_closure.sh` acts on all three:

    DECL_AXIOM  <n>   an `axiom` we declared under GFSO.*
    DECL_OPAQUE <n>   an `opaque` we declared under GFSO.*  (an uninterpreted assumption that
                      `#print axioms` cannot see — always a violation)
    USES        <n>   an axiom actually USED, transitively, by SOME theorem under GFSO.*

  Why all three. Earlier versions were fail-OPEN three times over:
    * `#print axioms` on a HAND-LISTED set of theorems — forget to list a theorem and its axiom hides.
      Fixed: we enumerate every declaration in `GFSO.*` from the environment and collect its axioms.
    * a DECLARATION-KIND filter — we walked `.thmInfo` only, so a proof written as `def foo : P := by
      sorry` (or an `instance`) was never inspected and its `sorryAx` never surfaced. That reinstated
      the same fail-open one level down. Fixed: `.defnInfo` is audited too — the audited set is now
      every GFSO declaration that can carry a proof, not every declaration that happens to be spelled
      `theorem`.
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
  -- Membership is by MODULE, not by namespace: everything this package's modules declare is audited,
  -- whatever its author called it. (A name-prefix filter let a foreign-namespace `sorry` sitting in
  -- our own source file go uninspected — see the header.)
  let ours : Name → Bool := fun n =>
    match env.getModuleIdxFor? n with
    | some idx =>
      match env.header.moduleNames[idx.toNat]? with
      | some m => m == `GFSO || (`GFSO).isPrefixOf m
      | none   => false
    | none => false
  let (declAx, declOp, thms) :=
    env.constants.fold
      (fun (a, o, t) n ci =>
        if n.isInternal || !(ours n) then (a, o, t)
        else match ci with
          | .axiomInfo _  => (a.push n, o, t)
          | .opaqueInfo _ => (a, o.push n, t)
          | .thmInfo _    => (a, o, t.push n)
          | .defnInfo _   => (a, o, t.push n)   -- a `def`/`instance` can carry a proof (and a `sorry`)
          | _             => (a, o, t))
      ((#[] : Array Name), (#[] : Array Name), (#[] : Array Name))

  for n in declAx.qsort (fun a b => toString a < toString b) do
    IO.println s!"DECL_AXIOM  {n}"
  for n in declOp.qsort (fun a b => toString a < toString b) do
    IO.println s!"DECL_OPAQUE {n}"

  -- Transitive axiom footprint of EVERY declaration in this package's modules that can carry a
  -- proof. No hand list, and no namespace filter.
  let mut used : NameSet := {}
  for t in thms do
    let axs ← liftCoreM <| Lean.collectAxioms t
    for a in axs do
      used := used.insert a

  let usedArr := used.toList.toArray.qsort (fun a b => toString a < toString b)
  for a in usedArr do
    IO.println s!"USES        {a}"
  IO.println s!"-- declarations audited: {thms.size}"
