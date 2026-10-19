/-
  THE CLOSURE AUDIT — `lake env lean check_axioms.lean` prints the axiom footprint of the development's
  main results, tier by tier (§20.4). Reading it:

  * `sorryAx` ⟹ a hole (it never appears);
  * `propext`, `Quot.sound`, `Classical.choice` ⟹ Lean's three foundations;
  * a `GFSO.*` name ⟹ a postulate — only the three covering axioms of §20.5 (a) and their carriers:

        GFSO.FailureModes.evaluation_completeness   (+ .correct)      CA1        — §8.2  ⟹ 6 FM
        GFSO.Standards.morris_trichotomy            (+ .fullyKnown)   CA-Morris  — §9.1  ⟹ 3 levels
        GFSO.Links.directed_action_completeness     (+ .Directed)     CA-Links   — §5.3  ⟹ 5 links

    Any other breaks the closure (`Postulates.lean`). CA2 is the hypothesis `Time.SingleClock`, no axiom.

  This file is the readable list; the fail-closed guard over the whole environment is `audit_env.lean`.
-/
import GFSO

open GFSO

/-! ## Tier 1 — primitives (Ch. 2, §7.5, §15.4) -/
#print axioms Ontology.basis_independent
#print axioms Ontology.Dep_not_determined
#print axioms Metrics.metrics_components_bijection

/-! ## Tier 2 — validation (§7): T1, |L|=2, AND -/
#print axioms Compositionality.T1
#print axioms Compositionality.corollary_root_from_leaves
#print axioms Compositionality.T1_characterization
#print axioms Binarity.L_forced_two          -- axiom-free; its premises live in the SIGNATURE
#print axioms Binarity.bool_scale_valid
#print axioms AndUniqueness.and_unique

/-! ## Tier 3 — the 6 failure modes (§8). CA1 must appear on the completeness results ONLY. -/
#print axioms FailureModes.locusFM_surjective   -- axiom-free: every FM has a locus (the dissection is fixed by the encoding)
#print axioms FailureModes.locusFM_injective    -- no collision: dimension 6
#print axioms FailureModes.fm_independent       -- the 6 witnesses
#print axioms FailureModes.fm_basis_covers      -- ← CA1 expected here
#print axioms FailureModes.after_holds_none     -- axiom-free: the after phase holds no mode (encoded)
#print axioms FailureModes.six_fm_complete    -- ← CA1 expected here

/-! ## Tier 3b — the operational axis (§8.2). CA2 is a hypothesis; the axis declares no axiom. -/
#print axioms Time.op_trichotomy_of_total     -- totality a hypothesis
#print axioms Time.phases_exhaustive          -- coverage, no assumption
#print axioms Time.phases_disjoint            -- disjointness from asymmetry
#print axioms Time.operational_trichotomy     -- exhaustiveness and before/after exclusion, clock-free
#print axioms Time.asymmetry_necessary        -- asymmetry cannot be dropped (one witness)
#print axioms Time.asym_of_irrefl_trans       -- every strict order qualifies
#print axioms Time.total_collapses_concurrent -- what totality buys: the middle cell's reading
#print axioms Time.app_phases_exhaustive      -- the phases of the application [f, e]
#print axioms Time.app_phases_disjoint        -- strict order + f not after e
#print axioms Time.app_total_during          -- totality reads the middle cell as [f, e]

/-! ## Tier 4 — standards and checks (Ch. 9): the guard map axiom-free, CA-Morris on its De Morgan step. -/
#print axioms Standards.level2_has_no_check   -- no CHECK at the Pragmatic level
#print axioms Standards.fm3_unguarded         -- FM-3: no structural guard (§9.10)
#print axioms Standards.fm6_unguarded         -- FM-6: no structural guard (§9.10)
#print axioms Standards.c6_guards_none        -- CHECK-6 guards no mode
#print axioms Standards.guarded_fms
#print axioms Standards.fm4_unguarded
#print axioms Standards.c2_guards_one         -- CHECK-2 guards FM-5 only, by its Dep clause
#print axioms Standards.knowledge_gap_located -- ← CA-Morris expected here

/-! ## Tier 5 — protocol (Ch. 11–12): the automaton and the signal counts -/
#print axioms Fsm.step_iff_admissible
#print axioms Fsm.step_deterministic
#print axioms Fsm.timeout_terminates
#print axioms Fsm.reassign_to_offered
#print axioms Fsm.cancel_handshake_terminates
#print axioms Protocol.defect_distribution     -- 4 / 4 / 3 / 1
#print axioms Protocol.defect_surjective

/-! ## Tier 6 — measurement (§15.6, §11.6) -/
#print axioms Metrics.replay_append
#print axioms Metrics.log_append_only
#print axioms Metrics.Q_self_measuring

/-! ## Tier 7 — theory model (Ch. 3–4). Lemma 1's form is definitional; checked is its consequence
    `no_apparatus_yields_S` (§20.4). -/
#print axioms TheoryModel.lemma1_S_underdetermined
#print axioms TheoryModel.no_apparatus_yields_S
#print axioms TheoryModel.agent_necessary      -- premises are in the SIGNATURE, not axioms

/-! ## Tier 7b — the five links (§5) -/
#print axioms Links.five_links                 -- axiom-free
#print axioms Links.split_three_two            -- 3 ⊕ 2, axiom-free
#print axioms Links.missing_link_located       -- ← CA-Links expected here

/-! ## The canon FSM table, its forcing and the ordinal grading (§12.4, Ch. 13, §19.6) — results
    §20.4 lists as machine-checked beside the spine. -/
#print axioms FsmCanon.canon_ten_pairwise_distinct      -- 11 states carry 10 behaviour classes
#print axioms FsmCanon.inv8_canon                       -- Inv-8: the owner has a move (canon table)
#print axioms FsmCanon.inv8_mirror                      -- Inv-8 on the engine mirror
#print axioms FsmCanon.inv8_forces_exactly              -- exactly CONFIRM_CANCEL is Inv-8-forced
#print axioms FsmCanon.witnesses_satisfy_inv8           -- every per-cell witness of Ch. 13 keeps Inv-8
#print axioms FsmCanon.mirror_agrees_with_canon         -- the engine mirror = the canon table, every cell
#print axioms LogLanguage.forced                        -- over the log every reachable cell has one outcome
#print axioms LogLanguage.agrees_with_the_canon         -- …and the forced machine is the canon's table
#print axioms Forcing.frozen_differs_only_on_the_changed_cells -- the frozen copy differs on the changed cells only
#print axioms Grading.dom_antisymm_all                  -- antisymmetry on probe-sets, by induction
