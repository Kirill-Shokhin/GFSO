/-
  GFSO — THE CLOSURE: every irreducible postulate the development carries and how it is carried, sorted
  by the (T)/(P) principle into the four kinds of §20.5, and the tier backbone of §20.11 anchored to its
  modules. Premises conditioning single results stand at those results (§20.5); Peirce's three inference
  types, a covering principle no Lean axiom carries, stand at §17.2, outside the development.

  ═══ THE TIERS (§20.11: each tier's kind and chapters there; a stack, not a generation order) ═══

    Tier 0  AXIOMS          A1, A2                                → definitional, kind (b) below
    Tier 1  PRIMITIVES      T, D, Dep, Del (V derived)            → Ontology
    Tier 2  VALIDATION      L (scale), ⊗ (aggregation), Thm 1     → Binarity, AndUniqueness, Compositionality
    Tier 3  FAILURE MODES   FM-1 … FM-6                           → FailureModes
            3b  TIME        the operational axis                  → Time
    Tier 4  STANDARDS       STD-1..4, the nine CHECKs (1, 1b, 2–8), Syntactic/Semantic/Pragmatic → Standards
    Tier 5  PROTOCOL        12 signals, 11 states, Inv-1..8       → Protocol, Fsm, FsmCanon, LogLanguage* (Forcing: a frozen table, no canon claim)
    Tier 6  MEASUREMENT     Q (5 metrics), Thm 10, Thm 11         → Metrics
    Tier 7  THEORY MODEL    S/Ŝ, Contact, Lemma 1, d1–d6          → TheoryModel
            7b  LINKS       the five links                        → Links
    (`Grading`, the order ⪰_dom of §19.6, stands beside the tiers.)

  ═══ THE POSTULATES — four kinds (§20.5): (a)–(c) by how Lean carries them; (d) by the canon's choice ═══

  (a) LEAN AXIOMS, listed by `#print axioms` — three, each with its uninterpreted carrier:
    1. `FailureModes.evaluation_completeness` (+ `FailureModes.correct`)  CA1 (§8.2)       ⟹ 6 FM
    2. `Standards.morris_trichotomy` (+ `Standards.fullyKnown`)           CA-Morris (§9.1) ⟹ 3 levels;
                                                                          by citation, below CA1's grade
    3. `Links.directed_action_completeness` (+ `Links.Directed`)          CA-Links (§5.3)  ⟹ 5 links;
                                                                          carries REACHES-ternarity and
                                                                          START's fold
    CA2, the single clock, once the fourth, is item 10 (§20.5). Items run 1–10 with no gap.

  (b) DEFINITIONAL — in the types, invisible to `#print axioms`:
    4. A1 — `Ontology.Verdict := Bool`, criteria Bool-valued: |L| = 2 is the type (§7.1);
       `Binarity.L_forced_two` is its defense against a graded scale, not its source.
    5. A2 — the existence of `Ontology.Decomp`.
    6. |Act| = 2 — `Binarity.Act`, two constructors; a covering claim over an undelimited space (§7.1, §20.5).
    7. The d3/d4 source space — `TheoryModel.KnowledgeSource`, four constructors {apparatus,
       declaration, luck, contact}, discharged by `cases src` in `agent_necessary`, so the closure is
       load-bearing. Its exhaustiveness is derived (§4.1), unlike item 6's; it is listed for its
       encoding: the kernel takes the split as a type rather than checking it (§20.5 (b)).

  (c) HYPOTHESIS-FORM — premises in a signature, dischargeable; each theorem is axiom-free:
    8. `Binarity.L_forced_two`: `Surjective act`, `Injective act`.
    9. `TheoryModel.agent_necessary`: `not_apparatus` (shown in substance by `no_apparatus_yields_S`,
       not linked, §20.4), `not_declaration` (Lemma 2), `not_luck`.
   10. `Time.op_trichotomy_of_total`: `SingleClock prec` (CA2, §8.2).

  (d) ADOPTED — the design decisions, the adopted clauses and the one alternative reading (§20.5 (d)).
    Where Lean carries one, it is a condition a theorem is stated over (`LogLanguage.clauses`, `pTerminal`)
    or a definition (Inv-4's reading in the canon table `FsmCanon.canonStep`).

  Everything else is derived, and machine-checked as far as §20.4 lists (`formal/README.md` marks the
  rest). Lemma 1 is definitional here; checked is its consequence `no_apparatus_yields_S` (§20.4).

  The (P) items — (a) and item 6 — meet the covering-form boundary (§20.1, §20.7): a taxonomy's
  completeness is not provable from inside it. What the encoding adds is that none hides unnamed: each
  is an `axiom` that `#print axioms` lists, or a type whose placement is disclosed. Run `check_axioms.lean`.
-/

import GFSO.FailureModes
import GFSO.Time
import GFSO.Standards
import GFSO.Links
import GFSO.Binarity
import GFSO.TheoryModel

namespace GFSO.Postulates

-- The three Lean axioms. A GFSO axiom in `#print axioms` output not listed here breaks the closure.

#check @GFSO.FailureModes.evaluation_completeness
#check @GFSO.Standards.morris_trichotomy
#check @GFSO.Links.directed_action_completeness

-- CA2 discharged to the hypothesis `SingleClock` (`Time`'s header): `phases_exhaustive` (coverage, no
-- assumption), `phases_disjoint` (from asymmetry), `asymmetry_necessary`, `asym_of_irrefl_trans`,
-- `op_trichotomy_of_total`, `total_collapses_concurrent`; over the application, `app_phases_exhaustive`
-- and `app_phases_disjoint` (§8.2, §20.5).
#check @GFSO.Time.SingleClock
#check @GFSO.Time.phases_exhaustive
#check @GFSO.Time.op_trichotomy_of_total
#check @GFSO.Time.operational_trichotomy
#check @GFSO.Time.asymmetry_necessary
#check @GFSO.Time.asym_of_irrefl_trans

-- Lemma 1: `S` is a free field and the apparatus is defined S-free, so the underdetermination is
-- definitional; checked is its consequence `no_apparatus_yields_S`, which `agent_necessary` carries as
-- its premise `not_apparatus`, not linked (§20.4).
#check @GFSO.TheoryModel.lemma1_S_underdetermined
#check @GFSO.TheoryModel.no_apparatus_yields_S

end GFSO.Postulates
