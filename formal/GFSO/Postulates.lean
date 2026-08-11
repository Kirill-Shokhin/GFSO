/-
  GFSO — THE CLOSURE. Every irreducible postulate of the canon, in one place.

  ═══════════════════════════════════════════════════════════════════════════════════════
  The question this module answers: *"Why 7 failure modes and not 8?" we can answer. But
  "why THIS many lists, and not one more?" — nowhere.*

  The answer is a sorting principle, and Lean applies it mechanically:

    (T) DEFINITION-UNFOLDING — N is counted INSIDE an already-delimited space.
        Provable; the kernel checks it (`decide` / `cases`).
        e.g. a function has exactly 3 parts (that IS the definition of a function);
             a set has exactly 2 properties; 16 binary ops; 12×13 transitions;
             |L| = 2 (a conjunction of two-valued criteria is two-valued).

    (P) COVERING PRINCIPLE — "there is no third KIND", where the space of candidate kinds
        is NOT delimited. Unprovable from inside. A postulate.
        e.g. no third axis of evaluation; no fourth dimension of knowledge about a sign;
             no sixth primitive; no third action.

  Everything in GFSO is (T) or (P). **The (P)s are finitely many and they are listed below.**
  That list IS the closure: "here is the beginning, here is the end, inside it is strict."

  ═══════════════════════════════════════════════════════════════════════════════════════
  THE NAMED TIERS (the hierarchy the canon's notation does not currently show)

    Tier 0  AXIOMS          A1, A2
    Tier 1  PRIMITIVES      T, D, Dep, Del   (V derived)         → Ontology.lean
    Tier 2  VALIDATION      L (scale), ⊗ (aggregation), T1       → Binarity, AndUniqueness,
                                                                    Compositionality
    Tier 3  FAILURE MODES   FM-1 … FM-7                          → FailureModes.lean
            3b  TIME        the operational axis                 → Time.lean
    Tier 4  STANDARDS       STD-1..4, the nine CHECKs (1,1b,2-8), Syntactic/Semantic/Pragmatic    → Standards.lean
    Tier 5  PROTOCOL        Signals (12), States (12), Inv-1..7   → Protocol.lean, Fsm.lean
    Tier 6  MEASUREMENT     Q (5 metrics), T10, T11               → Metrics.lean
    Tier 7  THEORY MODEL    S/Ŝ, Contact, Lemma 1, d1–d6          → TheoryModel.lean
            7b  LINKS       the five constitutive links           → Links.lean

  The tiers are a derivation STACK, not parallel lists. The ORDER here is the canon's own tier
  numbering (§1.4), and that table is **direction-neutral**: it does not say tier N+1 is generated
  by tier N. Tier 7 (the theory model) GROUNDS the apparatus — v4 leads with it (§1.5, §2.1):
    A1,A2 → primitives(4) → metrics(5, bijection with the tuple) ;
    the validation formula → 4 denotational ⊕ 3 operational = FM(7) ;
    FM(7) + FSM needs + IC → signals(12: 4/4/3/1) → states(12, "induced, not postulated") ;
    FM(7) → CHECK/STD ; Morris → levels(3) ; REACHES → links(5).
  ═══════════════════════════════════════════════════════════════════════════════════════

  THE POSTULATES — three kinds, by how they can be carried in type theory.

  ── (a) LEAN AXIOMS — postulated constants; they appear in `#print axioms`. THREE. ──────────
    1. `FailureModes.evaluation_completeness`  CA1 (§12.8): evaluation = denotational ⊕
       (+ `FailureModes.correct`)              operational; no third axis.  ⟹ 7 FM.
    2. `Standards.morris_trichotomy`           Morris (§13.4): knowledge of a sign-expression =
       (+ `Standards.fullyKnown`)              syntax ⊕ semantics ⊕ pragmatics; no fourth. ⟹ 3 levels.
    3. `Links.directed_action_completeness`    §4: directed action = REPRESENTATION(3) ⊕
       (+ `Links.Directed`)                    REALIZATION(2). ⟹ 5 links. Sub-§12.8 grade:
                                               rests on REACHES-ternarity + the folded START residue.
    (CA2 / single clock was a FOURTH covering axiom here; the §12.8 amendment discharged it — the phase
     COUNT is axiom-free, so it moved to (c) below, where it is now item 10. The (T)/(P) sort applied
     honestly: a claim that does not cover a count is not a covering axiom, and is not listed as one.
     The enumeration below runs 1–10 with no gap: ten postulates, three kinds, none dropped.)

  ── (b) DEFINITIONAL — baked into the TYPES; cannot be Lean axioms without being vacuous. ─
    4. **A1** (verifiability). Encoded as `Ontology.Verdict := Bool` and criteria being
       Bool-valued: "a criterion is a decidable predicate returning pass/fail". Its binarity is
       therefore not proved here — it IS the type. (This is why |L|=2 follows immediately: a
       conjunction of Bools is a Bool. The §11.2 `act`/pigeonhole argument is a *defence* against
       "why not graded", not the source.)
    5. **A2** (decomposability). Encoded as the mere existence of `Ontology.Decomp` — a parent with
       children and the two correctness proofs.
    6. **|Act| = 2** (two actions). Encoded as `Binarity.Act`, an inductive with two constructors.
       Prose says "there is no third action"; the type says "you declared two". The quantifier
       ranges over an undelimited space — the same wall as the sixth primitive. NOT provable here.
    7. **The d3/d4 source space** (ch.3: how contingent knowledge of S can be grounded). Encoded as
       `TheoryModel.KnowledgeSource`, an inductive with FOUR constructors {apparatus, declaration,
       luck, contact}; `agent_necessary` discharges by `cases src`, so the closure is load-bearing.
       Listed at a DIFFERENT grade from item 6, and canon §1.4 says why: its exhaustiveness is
       *argued* by nested excluded middle (derivable from the apparatus? if not, declared? if
       neither, the residual category is coincidence), where |Act| = 2's candidate space is
       undelimited. Disclosed so the two encodings are not read as one.

  ── (c) HYPOTHESIS-FORM — carried in a theorem's SIGNATURE, dischargeable in principle. ───
    8. `Binarity.L_forced_two`'s premises: `Surjective act` (completeness) and `Injective act`
       (non-redundancy). Visible in the type; the theorem itself is **axiom-free**.
    9. `TheoryModel.agent_necessary`'s premises: `not_declaration` (Lemma 2, the declaration
       regress) and `not_luck` (S is contingent ⟹ luck is eliminated under a demand for
       *reliable* success). Lemma 1 — the third elimination — is **definitional** here (the apparatus is *defined* S-free), and
       what is axiom-free is its consequence `no_apparatus_yields_S`; ch.27: this is NOT "Lemma 1 proved".
   10. `Time.op_trichotomy_of_total`'s premise `SingleClock prec` (CA2, §12.8): totality of the
       evaluation clock. By §12.8 the phase COUNT is axiom-free (Part 1: `phases_exhaustive` +
       asymmetry); totality buys ONLY the middle-cell rename "concurrent" ↦ "during", so it is a
       dischargeable hypothesis, not a covering axiom. The theorem is axiom-free.

  ── WHAT IS NOT A POSTULATE ───────────────────────────────────────────────────────────────
  Everything else: T1, T2, |L|=2 (given A1), the 4+3 geometry, the 7 independence witnesses, the
  FSM invariants, the 4/4/3/1 signal distribution, T10/T11, agent-necessity's elimination step.
  All derived; all machine-checked; several fully axiom-free. (Lemma 1 is NOT in this list: its
  logical form is definitional — ch.27; only its consequence `no_apparatus_yields_S` is derived.)

  ── THE WALL (the honest residue) ─────────────────────────────────────────────────────────
  Postulates (b) and the (P)-axioms in (a) share ONE obstruction:
  **you cannot prove the completeness of a taxonomy from inside that taxonomy.** To ask "is there a
  sixth primitive / a third action / a fourth dimension of knowledge?" you must first delimit the
  space of candidates — and that delimitation is the thing in question. This is not a defect of
  GFSO; it is a general property of axiomatizing a domain. What type theory contributes is that it
  will not let the question be *hidden*: every such claim is forced to become an `axiom`, and
  `#print axioms` enumerates them. Run `check_axioms.lean`.
-/

import GFSO.FailureModes
import GFSO.Time
import GFSO.Standards
import GFSO.Links
import GFSO.Binarity
import GFSO.TheoryModel

namespace GFSO.Postulates

-- The three Lean axioms, named and reachable. If a fourth ever appears in `#print axioms` output
-- that is not listed here, the closure has been broken and this file must be updated.

#check @GFSO.FailureModes.evaluation_completeness
#check @GFSO.Standards.morris_trichotomy
#check @GFSO.Links.directed_action_completeness

-- ★ The CA2 exit, TAKEN: single_clock is discharged to a hypothesis (`SingleClock`), so this
--   module postulates nothing. The canon carries this at §12.8: CA2 demoted from a covering
--   axiom. The exit is TIGHT, not merely "one axiom fewer":
--   `phases_exhaustive`      — coverage needs NO assumption at all;
--   `phases_disjoint`        — disjointness needs EXACTLY asymmetry (not totality);
--   `asymmetry_necessary`    — and asymmetry cannot be dropped (symmetric counterexample);
--   `asym_of_irrefl_trans`   — every strict order is asymmetric ⇒ total, partial, happens-before,
--                              interval and branching time all qualify;
--   `op_trichotomy_of_total` — the canon's own derivation, now axiom-free (totality a hypothesis);
--   `total_collapses_concurrent` — totality buys ONLY the rename "concurrent" ↦ "during".
#check @GFSO.Time.SingleClock
#check @GFSO.Time.phases_exhaustive
#check @GFSO.Time.op_trichotomy_of_total
#check @GFSO.Time.operational_trichotomy
#check @GFSO.Time.asymmetry_necessary
#check @GFSO.Time.asym_of_irrefl_trans

-- Lemma 1 is carried as a theorem, but read its docstring: `S` is a free field and the apparatus is
-- DEFINED to see only the formal view, so the underdetermination is definitional, not derived. What
-- is genuinely machine-checked is the CONSEQUENCE (`no_apparatus_yields_S`) used by step D4a.
#check @GFSO.TheoryModel.lemma1_S_underdetermined
#check @GFSO.TheoryModel.no_apparatus_yields_S

end GFSO.Postulates
