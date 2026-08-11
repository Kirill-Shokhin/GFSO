/-
  THE CLOSURE AUDIT — run:  lake env lean check_axioms.lean

  A green `lake build` is NOT proof of a proof. `#print axioms` is. This file prints the axiom
  footprint of every named result in the development. Reading it:

  * `sorryAx` anywhere  ⟹ a proof is a HOLE. Stop. (It never appears.)
  * `propext`, `Quot.sound`, `Classical.choice` ⟹ Lean's own foundations. Normal, healthy.
  * ANY `GFSO.*` name ⟹ a GFSO POSTULATE. There are exactly THREE (plus their uninterpreted
    carriers), and they are the ones documented in `GFSO/Postulates.lean`:

        GFSO.FailureModes.evaluation_completeness   (+ .correct)      CA1  — §12.8  ⟹ 7 FM
        GFSO.Standards.morris_trichotomy            (+ .fullyKnown)   Morris   — §13.4  ⟹ 3 levels
        GFSO.Links.directed_action_completeness     (+ .Directed)     §4 ⟹ 5 links

    CA2 (§12.8, single clock) is NOT here: by §12.8 the operational phase COUNT is axiom-free
    (Part 1 of `Time.lean`), so totality is carried as the hypothesis `Time.SingleClock`, not an
    axiom — it buys only the middle-cell rename "concurrent" ↦ "during".
    If a GFSO name appears below that is NOT one of those three (or their carriers), the closure is
    broken and `Postulates.lean` must be updated. That is the whole point of this file.

  Everything else in the development is DERIVED. Many results are fully axiom-free.
-/
import GFSO

open GFSO

/-! ## Tier 1 — primitives (§9–10) -/
#print axioms Ontology.basis_independent
#print axioms Ontology.Dep_not_determined
#print axioms Metrics.metrics_components_bijection

/-! ## Tier 2 — validation (§11): T1, |L|=2, AND -/
#print axioms Compositionality.T1
#print axioms Compositionality.corollary_root_from_leaves
#print axioms Compositionality.T1_characterization
#print axioms Binarity.L_forced_two          -- axiom-free; its premises live in the SIGNATURE
#print axioms Binarity.bool_scale_valid
#print axioms AndUniqueness.and_unique

/-! ## Tier 3 — the 7 failure modes (§12). CA1 must appear on the completeness results ONLY. -/
#print axioms FailureModes.locusFM_surjective   -- axiom-free: the case split covers all 7
#print axioms FailureModes.locusFM_injective    -- dimension is exactly 7
#print axioms FailureModes.fm_independent       -- the 7 witnesses
#print axioms FailureModes.fm_basis_covers      -- ← CA1 expected here
#print axioms FailureModes.seven_fm_complete    -- ← CA1 expected here

/-! ## Tier 3b — the operational axis (§12.8). CA2 is DISCHARGED; the axis is clock-free. -/
#print axioms Time.op_trichotomy_of_total     -- ★ axiom-free: totality is a hypothesis, not CA2
#print axioms Time.phases_exhaustive          -- ★ NO axiom: coverage needs no assumption at all
#print axioms Time.phases_disjoint            -- ★ NO axiom: disjointness needs EXACTLY asymmetry
#print axioms Time.operational_trichotomy     -- ★ the full partition, clock-free
#print axioms Time.asymmetry_necessary        -- ★ the premise is TIGHT (symmetric counterexample)
#print axioms Time.asym_of_irrefl_trans       -- ★ every strict order qualifies (happens-before too)
#print axioms Time.total_collapses_concurrent -- ★ axiom-free: what totality buys is only the rename

/-! ## Tier 4 — standards & checks (§13). Morris, and two sharp axiom-free facts. -/
#print axioms Standards.level2_has_no_check   -- pragmatics is not mechanically checkable
#print axioms Standards.fm3_unguarded         -- FM-3 has NO structural check (A1 guards it)
#print axioms Standards.fm6_unguarded         -- FM-6 has NO structural check (the protocol does)
#print axioms Standards.guarded_fms
#print axioms Standards.knowledge_gap_located -- ← Morris expected here

/-! ## Tier 5 — protocol (§14): the automaton and signal minimality -/
#print axioms Fsm.step_iff_admissible
#print axioms Fsm.step_deterministic
#print axioms Fsm.timeout_terminates
#print axioms Fsm.reassign_to_offered
#print axioms Fsm.cancel_handshake_terminates
#print axioms Protocol.defect_distribution     -- 4 / 4 / 3 / 1
#print axioms Protocol.defect_surjective

/-! ## Tier 6 — measurement (§21–§22) -/
#print axioms Metrics.replay_append
#print axioms Metrics.log_append_only
#print axioms Metrics.Q_self_measuring

/-! ## Tier 7 — theory model (§2–§3). Lemma 1's logical FORM is definitional (ch.27: this is NOT
    "Lemma 1 proved"); what is axiom-free is its consequence `no_apparatus_yields_S`. -/
#print axioms TheoryModel.lemma1_S_underdetermined
#print axioms TheoryModel.no_apparatus_yields_S
#print axioms TheoryModel.agent_necessary      -- premises are in the SIGNATURE, not axioms

/-! ## Tier 7b — the five links (§4) -/
#print axioms Links.five_links                 -- axiom-free
#print axioms Links.split_three_two            -- 3 ⊕ 2, axiom-free
#print axioms Links.missing_link_located       -- ← §4 covering axiom expected here

/-! ## The canon FSM table and the ordinal grading (§14.3 / §26.9(b), §6.3) — the two tiers
    Chapter 27 cites as machine-checked beside the spine. Listed here so this file's opening
    claim ("every named result") is true of it. -/
#print axioms FsmCanon.canon_eleven_pairwise_distinct   -- 12 states carry 11 behaviour classes
#print axioms Grading.dom_antisymm_all                  -- antisymmetry on probe-sets, by induction
