/-
  ENVIRONMENT AUDITOR — fail-closed. Run: `lake env lean audit_env.lean`; `scripts/check_closure.sh` acts
  on its three reports (§20.4):

    DECL_AXIOM  <n>   an `axiom` declared in a GFSO module
    DECL_OPAQUE <n>   an `opaque` declared in a GFSO module (an assumption `#print axioms` cannot see —
                      always a violation)
    USES        <n>   an axiom used, transitively, by some GFSO declaration

  Each design choice closes a fail-open path: every declaration is enumerated from the environment, not
  a hand list (a forgotten theorem would hide its axiom); `def`/`instance` bodies are audited beside
  theorems (they can hold a `sorry`); axioms are reported by use, wherever declared, not by namespace —
  the script then rejects anything outside {propext, Quot.sound, Classical.choice} ∪ whitelist, which
  catches `sorryAx` and `native_decide`'s `Lean.ofReduceBool`/`ofReduceNat`.

  An axiom present in the environment is not one used: Lean core always declares `sorryAx`, `lcProof`
  and friends; only `USES` says a proof leaned on one.
-/
import Lean
import GFSO

open Lean Elab Command

#eval show CommandElabM Unit from do
  let env ← getEnv
  -- Membership is by module, not namespace: a foreign-namespace declaration in our own source is
  -- audited too.
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

  -- Transitive axiom footprint of every declaration in our modules that can carry a proof.
  let mut used : NameSet := {}
  for t in thms do
    let axs ← liftCoreM <| Lean.collectAxioms t
    for a in axs do
      used := used.insert a

  let usedArr := used.toList.toArray.qsort (fun a b => toString a < toString b)
  for a in usedArr do
    IO.println s!"USES        {a}"
  IO.println s!"-- declarations audited: {thms.size}"
