# GFSO formal core — machine-checked in Lean 4

Machine-checked formalization of the **formal spine** of the GFSO canon
(`../docs/applied_gfso_v4_en.md`), in Lean 4. **No mathlib** (Lean core only), **no `sorry`**, **no
`native_decide`** — and the assumption set of this encoding is not asserted, it is **enforced by CI**.
What the development is and what it checks is the canon's (§20.4, §20.5); this file maps each canon
result to its Lean names and grade, and records the disclosed corners.

## The result, stated honestly

An audit of GFSO's axiomatic surface, machine-checked — *not* a proof of its substantive claims
(§20.4). Ranked by how much each is worth:

1. **The assumptions of this encoding are enumerated and enforced.** The (T)/(P) sorting and the four
   kinds are §20.5's. Here kind (a) is three `axiom`s — `evaluation_completeness` (CA1),
   `morris_trichotomy` (CA-Morris), `directed_action_completeness` (CA-Links) — over the three carriers
   `correct`, `Directed`, `fullyKnown`. The development contains its own counterexample to "three" being
   a fact about GFSO (§20.5): `|Act| = 2`, a covering principle in substance, is a two-constructor
   inductive and never appears in `#print axioms`. The guard makes *this* enumeration an invariant the
   engine defends.
2. **CA2 is discharged** (§8.2, §20.5). Coverage of the operational classification needs no assumption
   (`app_phases_exhaustive`; `phases_exhaustive` its single-event case), the partition only a strict
   order with the fixing not after e (`app_phases_disjoint`); the clock is the hypothesis `SingleClock`
   of `op_trichotomy_of_total`, buying only the middle cell's reading as *during* the application
   (`app_total_during`; `total_collapses_concurrent` its single-event case). Atomicity of the evaluation
   act belongs to the dynamics (§8.2) and is not encoded. `GFSO/Time.lean`.
3. **The spine compiles.** Thm 1 and its converse, |L|=2, Thm 2 (16-op enumeration), the 4+2 FM geometry
   and its 6 independence witnesses, FSM determinism, obligation-ownership (Inv-8), the termination of
   pure timeout chains, the cancellation handshake, the 4/4/3/1 signal count, `state = fold(log)`.
   Correct and faithful — and elementary. The value is the *map*, not the depth.
4. **The guard map is machine-checked.** That no CHECK lives at the Pragmatic level and that FM-3, FM-4
   and FM-6 are guarded by no structural check (§9.10) is decided off the table here, not asserted.

**What is assumed, not proved.** 6-FM completeness, the Morris trichotomy and the completeness of the
five links are **axioms**; `fm_basis_covers`, `knowledge_gap_located`, `missing_link_located` check only
the De Morgan step *from* the axiom. Axiom-free around them: the 4+2 geometry, the 6 witnesses, the 3⊕2
count (§20.5).

**Read the "honest reading" docstrings.** Four results are true but forced by the modelling choice,
not derived: `lemma1_S_underdetermined` (Lemma 1's *form*; `S` is a free field and the apparatus is
*defined* S-free), `basis_independent` (a 4-tuple of free bits has four independent coordinates),
`metrics_components_bijection` (two 5-element enums defined to match), and the FM independence witnesses
(`FailureModes.fm_independent`: six free conditions, each settable apart). Each says so in place.

**What this is not.** Not a proof that GFSO is correct, complete, or empirically valid. Not a
formalization of the imported classics (Prop 3–9). Not a proof that the basis is minimal in §7.5's
semantic sense or unique (§20.6–§20.7), nor that Lemma 1 holds for a rich apparatus. The empirical
boundary is *localized* into the three carriers, not closed (§20.4).

## Scope: what "three" is and is not

Three is the number of covering axioms **this encoding chose to make explicit** (§20.5); make `|Act|=2`
an axiom and it is four. Where each kind of §20.5 lives here:

| Kind | Items | Where it lives |
|---|---|---|
| **Covering axioms** (3), kind (a) | CA1 (§8.2) · CA-Morris (§9.1) · CA-Links (§5.3) | `axiom` — visible in `#print axioms`, whitelisted with the three carriers |
| **Definitional** (4), kind (b) | A1, A2 (§1.2), \|Act\|=2, the d3/d4 source space | baked into the *types* (`Verdict := Bool`, `Decomp`, `Act`, `KnowledgeSource`), invisible to `#print axioms`, at different grades (§20.5; d4's residual class, coincidence, is §4.1's) |
| **Hypothesis-form** (3 groups), kind (c) | act-surjectivity + act-injectivity · not-apparatus + no-declaration + no-luck · `SingleClock` | premises in the *signatures* of `L_forced_two`, `agent_necessary`, `op_trichotomy_of_total`; the not-apparatus premise is shown in substance by `no_apparatus_yields_S`, not linked to the signature (§20.4) |
| **Adopted**, kind (d) | the eleven design decisions · the adopted clauses · the one alternative reading | not postulates and not in the types; the forcing theorems are stated over the conditions §13.4 names (`LogLanguage.clauses`, `general`, `pTerminal`, `decisionEntries`) |
| **Outside the development** | the AI layer's covering of the inference types (§17.2) | carried by no Lean axiom (§20.5) |
| **Out of scope** | Prop 3–9 | imported classical results; need ℝ/probability = mathlib |

A *definitional* postulate cannot be a Lean axiom without being vacuous: prose says "there is no
third action", the type says "you declared two". A *hypothesis* is dischargeable in principle and is
visible in the theorem's type; an *axiom* is not. Conflating the two is a mistake — `L_forced_two` is
**axiom-free** even though it has premises.

## Coverage — every canon result, accounted for

`✔` machine-checked · `⚠` machine-checked *modulo a named axiom* · `◐` true but **forced by the
modelling choice** (the shape is formalized, the canon's semantic content is not) · `○` out of scope.
What each claim states is at its §.

| Canon result | § | Status | Where |
|---|---|---|---|
| Thm 1 compositionality (+ its converse) | 7.3 | ✔ | `Compositionality.T1`, `.T1_characterization` |
| \|L\| ≠ 2 impossibility | 7.1 | ✔ axiom-free | `Binarity.L_forced_two` |
| Thm 2 uniqueness of AND | 7.2 | ✔ | `AndUniqueness.and_unique` |
| 6-FM completeness | 8.2/8.8 | ⚠ CA1 | `FailureModes.six_fm_complete`, `.fm_basis_covers` |
| 6-FM independence (6 witnesses), 4+2 geometry; the after phase mapped to no mode | 8.8/8.10 | ◐ structural: the witnesses hold of any six free conditions (`correct` uninterpreted, CA1 one-way); that §8.8's scenarios realize each isolation is argued; the after phase's mapping encoded, not proved (§20.5) | `FailureModes.*`, `.fm_independent`, `.after_holds_none` |
| Operational trichotomy | 8.2 | ✔ axiom-free (CA2 a hypothesis) | `Time.*` |
| Minimality of basis (independence half) | 7.5 | ◐ structural (free-coordinate model) | `Ontology.basis_independent` |
| Uniqueness of basis | 20.6/20.7 | ○ the carve wall (§20.7); σ-canonicity over the Beth class (§20.6) not formalized | — |
| Uniqueness of protocol: bare adequacy pins no destination; the backbone; the removals' grades | 13.2/13.3/11.4/20.7 | ✔ axiom-free (`decide`) as far as §20.4 lists: bare adequacy pins no destination, derived (§13.2); the auto_pass witness (VALIDATING's timeout → DONE(auto_pass), v4.0's cell) keeps the timeout exits and Inv-8 and is behaviourally distinct; the folds `noEscalated_*`, `oneStepCancel_*` give every non-terminal state but IDLE a timeout and keep Inv-8, their deadlock-freedom derived (§20.4); the fatal and content-edge removals canon-internal necessary conditions, FAIL's grade not machine-checked. On the bit-abstracted table ACCEPT is only the sole content edge into consent (`accept_sole_content_consent`); it is fatal over the log (`LogLanguage.accept_fatal`). Every witness satisfies Inv-8 over its reachable states. ○ over a fully pinned design vector: the carve wall (§20.7) | `FsmCanon.variant_*`, `.canon_never_enters_overdue`, `.canon_first_timeouts_hand_over`, `.canon_reject_returns_to_the_wait`, `.noEscalated_*`, `.canon_reaches_escalated`, `.canon_exec_reaches_done`, `.nodeliver_strands_done`, `.noAssign_strands_start`, `.noBlock_strands_blocked`, `.noChallenge_strands_challenged`, `.noCancel_keeps_the_silence`, `.noCancel_leaves_only_the_silence`, `.accept_sole_content_consent`, `.resolveBlock_sole_content_resume`, `.acceptChallenge_sole_content_reoffer`, `.rejectChallenge_sole_content_resume`, `.noConfirm_only_timeout_into_abandoned`, `.canon_confirm_is_genuine`, `.canon_reassign_to_offered`, `.acceptChallenge_dest_inv1_forced`, `.oneStepCancel_*`, `.witnesses_satisfy_inv8`, `.witnesses_inv8_tablewide` |
| PASS is fatal (no timeout enters DONE) | 11.4/13.2 | ✔ axiom-free (`decide`; contrast: the auto_pass variant reaches DONE without PASS only through auto_pass) | `FsmCanon.noPass_strands_done`, `.canon_reaches_done`, `.canon_pass_is_genuine`, `.variant_noPass_keeps_done`, `.variant_noPass_only_autopass_into_done` |
| Inv-8-forced signals: exactly CONFIRM_CANCEL | 12.13/16.12 | ✔ axiom-free (`decide`; canon-internal) | `FsmCanon.noConfirm_breaks_inv8`, `.inv8_forces_exactly` |
| Post-consent CHALLENGE (EXECUTING, REWORKING → CHALLENGED) and its grade | 13.3/16.12 | ✔ axiom-free (`decide`: the table without those cells "keeps every timeout and Inv-8", §13.3; its deadlock-freedom and finiteness derived there) | `FsmCanon.canon_challenge_after_consent`, `.preC1_differs_only_on_the_c1_cells`, `.preC1_adequate_without_the_edges` |
| State irredundancy (11 states → 10 behaviour classes; EXECUTING ≡ REWORKING) | 12.11 | ✔ axiom-free (`decide` over `canonSt`, negative control), under the table's bit abstraction; the count over the log, eleven, is derived (§12.11). The Lean enum keeps an OVERDUE constructor for the engine: empty row, owner `none`, entered by no cell | `FsmCanon.canonSt_eleven`, `.canon_exec_rework_same`, `.canon_ten_pairwise_distinct` (all pairs, joint observable), `.canon_others_pairwise_distinct`, `.canon_settlement_separates_terminals` |
| REWORKING and EXECUTING agree on the BLOCK row | 12.4 | ✔ axiom-free (compares the two rows inside the engine table; the canon-vs-engine identity is read off `canonStep`) | `FsmCanon.engine_agrees_on_rework_row` |
| 3 verification levels | 9.1 | ⚠ Morris | `Standards.knowledge_gap_located` |
| CHECK↔FM guard map; Pragmatic level and FM-3/FM-4/FM-6 unguarded | 9.5/9.10/12.10 | ✔ axiom-free (A1 fixes FM-3's *form*, not its truth; `c6_guards_none` certifies the table entry, the argument is §9.5's) | `Standards.Guards`, `.c2_guards_one`, `.c6_guards_none`, `.guarded_fms`, `.fm3_unguarded`, `.fm4_unguarded`, `.fm6_unguarded`, `.level2_has_no_check` |
| Signal defect distribution (12 = 4/4/3/1) | 11.4 | ◐ `decide` over a hand-entered table, not a minimality proof | `Protocol.defect_distribution`, `.defectOf` |
| Inv-5 finiteness (Φ1): pure timeout chains end | 12.12 | ✔ (≤ 3 timeouts reach a terminal, tight; IDLE exempt by Inv-5, carried as `s ≠ IDLE`; the off-table OVERDUE constructor as `s ≠ OVERDUE`). Scoped to chains in which nobody moves | `Fsm.timeout_defined`, `.timeout_terminates`, `.timeout_bound_tight`, `.no_cell_enters_overdue` |
| Run-level finiteness (Φ1–Φ3) | 12.15 | TLC over bounded models, not Lean (negative controls: a dead monitor violates `WaitsEnd`; a contract with no deadline loops within one version). What the models check less and admit is §12.15's last paragraph | `tla/`: `WaitsEnd`, `NoOwnerlessDivergence` |
| Inv-6 determinism | 12.4 | ✔ | `Fsm.step_deterministic`, `.step_iff_admissible` |
| Inv-1 revision = re-ASSIGN, not cancel | 12.3 | ✔ | `Fsm.reassign_to_offered` |
| Inv-8 (Obligation-Ownership) | 12.13 | ✔ axiom-free (`decide`, over the canon table and the engine mirror, at both values of the bit; the owner map a per-state stipulation, the move's existence what is checked; negative control: v4.0's empty ESCALATED row fails Inv-8, and only there). TLC checks the same as `OwnerHasMoveInv`. "A node's issuer is Del(parent)" is not modelled (no Del identities) | `FsmCanon.owner_domain`, `.inv8_canon`, `.inv8_mirror`, `.control_inv8_fails_on_empty_escalated` |
| Canon table ↔ engine mirror agree on every cell | 12.4 | ✔ axiom-free (the cells v4.1 changed from v4.0 are named in the mirror's header; the engine's own conformance is `tests/test_model_conformance.py`) | `FsmCanon.mirror_agrees_with_canon` |
| The table forced over the log | 13.4 | ✔ axiom-free (`decide +kernel`), relative to §13.4's conditions, scope §13.6; each clause's load by exact counts | `LogLanguage.forced`, `.never_lapses`, `.readings_agree`, `.agrees_with_the_canon` (LogLanguageAgrees), `.the_lapse_as_a_channel_leaves_cells_open` (LogLanguageLoads), `.loads_none`/`_executor`/`_issuer`, `.accept_fatal` |
| R′ over the log | 13.5 | ✔ axiom-free (`decide +kernel`; at a gate that never holds the form is `pTerminal`) | `LogLanguageReopen.forced`, `.off_the_settlements_nothing_moves`, `.the_only_exit_is_an_offer`, `.admission_carries_five`, `.the_form_is_chosen` |
| The missed bound as a channel of its own admits no second machine | 13.4 | ✔ axiom-free (`decide +kernel`; the routes read by `isPartyWait`) | `LogLanguageLapse.the_lapse_as_a_channel_admits_no_second_machine`, `.the_lapse_has_no_timeout` |
| The signals' meanings with the general sentences and the reassignable set leave the machine open | 13.4 | ✔ axiom-free (`decide +kernel`) | `LogLanguage.general_sentences_leave_it_open` (LogLanguageLoads) |
| The reassignable set's former exception carries nothing | — (no canon claim) | ✔ axiom-free (`decide +kernel`) | `LogLanguage.the_old_exception_is_idle` (LogLanguageLoads) |
| Authoritative cancellation, added back, changes no cell | 12.12/13.4 | ✔ axiom-free (`decide +kernel`) | `LogLanguage.authority_is_derived` (LogLanguageAgrees) |
| The one-cell perturbation measurement (frozen table, with OVERDUE) | — (no canon claim; the table is not the canon's) | ✔ axiom-free (`decide`), about the frozen table only; it tests local stability, not forcing | `Forcing.frozen_differs_only_on_the_changed_cells`, `.the_partition`, `.rows_force_twenty_seven`, `.canon_satisfies_all`, `.canon_waits_end`, `.five_are_independent`, `.the_vector_does_not_pin_the_machine`, `.timeouts_collapse`, `.cancelling_timeout_freedom`, `.resolutions_collapse`, `.roles_are_extensionally_the_labels`, `.the_fail_cell_is_measured_guard_free` |
| With every timeout chain settling, two timeout cells forced | — (no canon claim) | ✔ axiom-free (`decide`), about the frozen table only | `Forcing.waitsEnd_forces_two_timeout_cells` |
| Inv-5's first sentence is weaker than "waits end"; Inv-8's edge clause refuses the park, not the self-loop | 12.12/12.13 (derived there) | ✔ axiom-free (`decide`), witnessed by one-cell edits of the frozen table | `Forcing.the_two_machines_in_the_gap` |
| Cancellation handshake completes | 12.6 | ✔ (from every canon non-terminal ≠ CANCELLING) | `Fsm.cancel_handshake_terminates` |
| Inv-2 binarity of V | 12.8 | ✔ definitional | `Ontology.Verdict := Bool` |
| Inv-3 FAIL ⇒ failed_criteria ≠ ∅ | 12.8 | ○ payload-level, not a state-machine property | — |
| Inv-4 symmetry of obligations | 12.9 | ○ normative; its checkable content under the reading §12.9 adopts is Inv-8 (row above) | — |
| Inv-7, log clause: state = fold(log) | 12.11/11.6 | ✔ | `Metrics.replay_append`, `.log_append_only` |
| Inv-7, id clause | 12.11 | ○ graph-level, not encoded — the development has no N × N edge model to orphan | — |
| Thm 10 self-measuring Q (constructive core) | 15.6 | ◐ (a generic event count; q_D's state-conditional event, the ratios and ⊥ not modelled) | `Metrics.Q_self_measuring` |
| Q index set: 5 metrics ↔ 5 components | 15.4 | ◐ structural (enums defined to match) | `Metrics.metrics_components_bijection` |
| Thm 11 structural transparency | 11.6 | ◐ (a fold identity; the record's content not modelled) | `Metrics.replay_append` |
| Ordinal severity ⪰_dom | 19.6 | ✔ axiom-free — reflexivity/transitivity/antisymmetry **universal** (by induction), partiality and count-independence by witness, with a finite carrier + negative control | `Grading.dom_refl_all`, `.dom_trans_all`, `.dom_antisymm_all`; `.dom_partial`, `.dom_count_independent`, `.dom_not_constant_true` |
| 5 constitutive links (3 ⊕ 2) | 5.3 | ⚠ CA-Links, **below CA1's grade** (§20.7); the 3⊕2 count axiom-free | `Links.*` |
| Lemma 1 — its logical form | 3.4 | ◐ definitional (apparatus is *defined* S-free) | `TheoryModel.lemma1_S_underdetermined` |
| …its consequence: no `FormalView → S` exists | 3.3 | ✔ axiom-free | `TheoryModel.no_apparatus_yields_S` |
| Agent necessity d1–d6 | 4.1 | ✔ elimination (not-apparatus, no-declaration and no-luck are premises) | `TheoryModel.agent_necessary` |
| Lemma 2, luck-instability | 3.4/4.1 | hypothesis-form | signature of `agent_necessary` |
| Prop 3 Blackwell dominance | 16.2 | ○ imported (Blackwell 1953) | — |
| Prop 4 constraint improvement | 16.3 | ○ imported (Simon 1955) | — |
| Cor 5 α-monotonicity, Prop 6 temporal monotonicity | 16.5/16.6 | ○ imported | — |
| Prop 7 cascade ‖eₙ‖ ≤ (Λ·γ)ⁿ‖e₀‖ | 16.7 | ○ needs ℝ / operator norms | — |
| Prop 8 IC (dominant strategy) | 16.11 | ○ needs a payoff model — imported (Hurwicz 1960) | — |
| Prop 9 decomposition quality | 16.16 | ○ composite of Prop 3/4/6/7 | — |
| Universal Improvement (corollary) | 16.4 | ○ imported | — |
| IC-minimality of the eleven features | 16.12 | ○ a payoff argument per row — needs the payoff model | — |
| Inseparability of the two pillars | 17.9 | ○ an argument over the feedback loop, not modelled | — |
| The two methodological mechanisms and their optimality under the named cost model | 18.1/18.2 | ○ needs ℝ and Prop 7's cost model | — |
| Pragmatic-level faithfulness (the residue) | 20.2 | permanent boundary — *localized*, not closed | `correct` left uninterpreted |

If a canon result is missing from this table, the table is wrong. That is what makes "complete" falsifiable.

## Build and verify

```sh
export PATH="$HOME/scoop/persist/elan/.elan/bin:$PATH"   # elan via scoop (Windows)
cd formal
lake build                        # ~1–2 min cold, instant warm. No mathlib.
bash scripts/check_closure.sh     # no GFSO-reachable `sorry`; postulate set == AXIOMS.whitelist
bash scripts/check_naming.sh      # no name the v4 contract retired survives (read off the canon)
bash scripts/check_refs.sh        # every §-citation still exists in the canon
bash scripts/check_claims.sh      # counts read off the canon at run time; no retired formulation
                                  #   survives in the canon or a mirror
bash scripts/check_lean_refs.sh   # every Lean/TLA name the canon and the mirrors cite exists
```

**A green build is not proof of a proof.** During the original spike a name collision silently made a
definition elaborate to `sorry` while the visible errors were only downstream. Hence:

- `check_closure.sh` is **fail-closed**. It does not grep the footprints of a hand-listed set of
  theorems (that is fail-open: forget to list a theorem and its axiom hides). It runs
  `audit_env.lean`, which **walks the whole compiled environment** and reports every `axiom` *and*
  every `opaque` under `GFSO.*` — at any nesting depth, under any name, used or unused. Then it
  diffs against `AXIOMS.whitelist` and rejects any `opaque` outright (an `opaque` constant is an
  uninterpreted assumption that `#print axioms` cannot see). It also fails on any axiom a GFSO
  declaration uses outside Lean's three foundations (`propext`, `Quot.sound`, `Classical.choice`) and the
  whitelist — `sorryAx` (a hole), `native_decide`'s `Lean.ofReduceBool`, an axiom in a foreign namespace.
  *The postulate set is an invariant the engine rejects violations of, not a claim made once.*
- `check_refs.sh` — fails if `formal/` cites a canon section that no longer exists. It catches
  citation drift; it **cannot** check that a Lean statement still *means* what its section says.

**Disclosed limit.** An assumption moved into a theorem's *signature* (a hypothesis) is invisible to
the guard, by construction and legitimately: a hypothesis is dischargeable and is visible in the
theorem's type. So `axiom-free` — no GFSO axiom, Lean's three foundations admitted — certifies *"assumes nothing beyond its stated premises"*, not
*"assumes nothing"*. Semantic conformance between a Lean statement and its canon section remains a
human/agent job — exactly as a passing `pytest` suite does not certify that the right tests were written.

CI runs all five guards on every change to `formal/` **and to the canon**.

## Code ↔ canon corners (flagged, not patched — canon is truth)

*(The three that were LIVE divergences of the ENGINE from the canon — **#3**, an edge the canon denies,
**#1**, a row the canon exempts, and **#5**, a failure mode routed to the wrong repair — are now
CLOSED or landed in part: the engine carries the canon's shape and each entry records what landed. The rest
are settled by the canon and kept because the Lean encoding is where they show, or are engine gaps.)*

1. **IDLE has no timeout — the canon's position; the engine now agrees (CLOSED).**
   `gfso/core/protocol/fsm.py` used to carry an `(IDLE, TIMEOUT)` row, added under the **v3.9**
   reading in which Inv-5 was total over non-terminals; v4 exempts IDLE by name (§12.2, §12.12), so the
   row was removed. What it had been written for — a crash orphan, observable in IDLE because
   CREATE_TASK persisted while the same ASSIGN's landing did not, and at a root with no parent whose
   clock could surface it — is answered where the defect lives: `Engine._recover_orphans` re-sends the
   packet-less ASSIGN at startup, so the interrupted transition finishes through the queue — validated,
   logged (Thm 11), never a silent state write (`tests/test_inv5_timeout.py`). In Lean
   `Fsm.idle_has_no_timeout` proves `step IDLE TIMEOUT _ = none`, and the finiteness theorems keep their
   explicit `s ≠ IDLE` hypothesis — the exemption in the type rather than papered over.
2. **IDLE + CANCEL → CANCELLING — settled by the canon, not a divergence.** §12.4's IDLE row carries it;
   arguably vacuous, encoded faithfully because it is what both the canon and the code say.
3. **`(VALIDATING, FAIL, iteration ≥ max)` — the edge the canon denies is GONE (CLOSED).**
   The code, `Fsm.lean`, `FsmTable.tla` and `docs/architecture.md` now route the exhausted rework loop
   to ESCALATED, the canon's target (§12.4, §12.5); before, it entered DONE, which §12.4 enters only
   through PASS. The record carries `done_reason=FAIL`, so a verdict-escalation stays distinguishable
   from the timeout routes into ESCALATED — without which the standing-FAIL metric populations (q_D's
   exhausted arm, `false_fail_share`) would have silently emptied, a blind metric reading as a clean
   one. The live path is tested through the engine, not the table alone
   (`tests/test_integration.py::test_exhausted_rework_escalates_and_stays_a_verdict`).
4. **`(REWORKING, BLOCK) → BLOCKED` — the engine had an edge the v4.0 DIAGRAM omitted; RESOLVED in
   favour of the engine.** `fsm.py` and `Fsm.lean` route BLOCK from REWORKING to BLOCKED; the edge is
   derived (§12.4's rules), and §12.4 now writes the admissible sets out per state, closing the
   diagram-only gap that let this hide. Consequence (`FsmCanon.canon_exec_rework_same`): EXECUTING ≡
   REWORKING behaviourally — REWORKING an attribution label (§12.11).

5. **The re-DELIVER refusal prescribed the wrong repair for an FM-1 failure (OPEN on (a); (b) landed).**
   `gfso/engine/validation.py` refuses a parent's re-delivery when its FAILed criteria
   are covered by children untouched since that FAIL — an engine gap of its own: after a re-presentation
   (a false FAIL among its cases) the canon admits "the re-delivery of an identical artifact" (§12.10), so
   the refusal does not conform to §12.16 (ii) — and its message routed the repair DOWNWARD: *"Rework
   flows DOWN: reopen the covering child … and rework it there"*. A parent's criterion failing while
   every child passes its own is q_D's event, "whatever caused it" (§15.4; the cause is not q_D's to read,
   §16.9); where the cause is the split, the defect is the decomposition's, its repair a **re-admission of the parent's
   split** (§11.5) by its decomposer, who owns it (§9.7). A re-admission reopens no child, so the
   finality gate is not involved.

   Observed live (`EVIDENCE_LOG` §13.3, `markdown_renderer`): following the message's own route the
   arm hit a wall, because `Graph.is_consumed` locks a DONE child on which any Dep-consumer built,
   and a graph with 20 seams over 11 nodes has no unlocked covering child. On the re-admission route
   the wall is not reached. Two things follow for the engineer, and the second is what keeps the fix
   honest: (a) the refusal message must name the re-admission remedy; (b) adding coverage so that
   `⋀children ⊨ cᵢ` is the repair, while lowering `cᵢ` to what the children already deliver is a false
   close wearing the same shape — the two are told apart by what CHECK-1/CHECK-7 say after the repair
   and by whether the fail-extension of `cᵢ` shrank. Without that discriminator both moves would have
   to be forbidden, and the only legal repair would be lost with them.

   **What landed** (`_refuted_coverage_refusal`, `tests/test_fm1_repair.py` — one planted case per
   class). (a) Not landed: the refusal still names a revision of the parent under Inv-1 (`validation.py`), a
   packet change that repairs no mapping — the split changes only by a re-admission (§11.5); the message is
   engineering's to change. (b) The discriminator reads
   the criteria as they stood when contact refuted them (snapshotted on the verdict record) against
   the criteria now, and disposes of each failed criterion: a criterion REMOVED, or LOOSENED where
   loosening is decidable — same metric, same operator, a bound admitting strictly more, the
   numeric tier where CHECK-7 is O(n) — is refused as a false close, its fail-extension having
   shrunk; a criterion EDITED undecidably is admitted once the revised plan's checks have spoken
   again (L0 clean plus a current, dispositioned L2 verdict — the check must have HAPPENED, never
   that the checker is right, and `GFSO_L2_GATE=0` opts out of that half exactly as it does at the
   execution gate); an UNREPAIRED criterion (unchanged, every coverer untouched) keeps the original
   refusal — the engine's non-conformance above, which this gate carries across the OFFERED→EXECUTING
   route of a re-presentation, where §12.10 admits the identical re-delivery; a touched coverer passes
   as before. Two scope notes on the engine's design: the gate follows the node across that route
   rather than firing in REWORKING alone, since a revision leaves REWORKING and the criterion-lowering
   route would otherwise never be examined; and it keys on the node HAVING a decomposition rather than on its mappings, since
   deleting the refuted criterion also deletes the mapping that pointed at it — a mapping-keyed
   trigger would have let exactly the false close through. A leaf stays out of scope: its contract
   belongs to the issuer above, whose CHECK-1 surfaces any hole a rewrite leaves.

   *(Threshold note, parked with a reason: the engine's point — "consumed while any Dep-consumer
   exists" — locks earlier than the moment §12.14 adopts. Moving it is not needed once (a) and (b)
   stand; if the wall reappears on the re-admission route, that is the measurement that would justify
   touching it.)*

6. **The vertical deadline rule now has a pre-exec check; CHECK-3 is unchanged.** Deadline coherence along D is form item (6) (§4.5), which CHECK-3 does not guard
   (§9.5, §20.10). It is L0 by construction (two packet fields, no domain knowledge), so it rides in a check of its own (`check_vertical_deadlines`,
   `tests/test_structural.py`): a child whose deadline is not strictly before its parent's is flagged
   at the battery — flagged, not refused. §11.5 gates it over an admission's unissued children while the parent's deadline is ahead; there
   the engine's flag is an engine gap. What the check adds is the implementation's guard, **not** CHECK-3's canon definition — the rule enforced here is §4.5 item (6), and any prose that
   credits it to CHECK-3 is wrong about the canon. A packet with no deadline does not conform; a logged
   default is admissible (§12.16).

7. **Non-redundancy beyond the topological proxy — still open, and stated where it shows.**
   CHECK-1b tests "every child is mapped to some parent criterion" and is renamed to its honest name,
   `CHECK-1b:no_orphan` (a decision of the v4.0 naming pass, not a canon §; form item (3) keeps the name
   *non-redundancy*). No pre-execution CHECK tests non-redundancy's formal face (§9.6, §20.10). Left open
   deliberately, with the proxy named as a proxy rather than dressed up as the condition.

8. **§15.9's triage ORDER is not what `next_step` implements — named, not silently adopted.**
   `Engine._frontier` orders by action priority and then by id, not by §15.9's order. The gap is real
   and the fix is cheap — but it changes the ORDER in which an agent is driven through a graph, which is
   a measured quantity of the E3 arm (C3 cost, and through it C1/C2 attribution). Landing it inside a
   naming migration would confound the next measurement with a behavioural change, so it is recorded
   here and lands as its own change, measured against a run that did not have it.

9. **The execution gate was a SELECTION from the Syntactic level; it is now the level (CLOSED, with two
   gaps open).** §11.5 makes the Syntactic level (§9.5) the admission condition, save what no act of the
   decomposer lifts, which is reported. The engine gated four of the seven rows: ACCEPTED_RISKS (4),
   risk nodes (5) and leaf delegation (6) were computed, surfaced by `get_checks`/`list_holes`, and
   never blocked an ACCEPT — so a decomposition with an empty register was admitted. **What was argued
   for it, and why it did not survive:** gating the register had been tried and measured — an agent
   that cannot start until the register is non-empty writes a register in order to start, so the gate
   bought fabricated entries and `edit_accepted_risks` churn. That is a fact about an incentive, not
   about whose rule it is; a fabricated register is evidence against its author (§16.9, exception 7),
   while an ungated canon level is a silent one. The gate now runs every row of the level
   (`gfso/engine/validation.py`), pinned in both directions by `tests/test_structural.py` — every canon
   row gates, and CHECK-1c (anti-mock, an engineering addition with no canon row) does not. Cost,
   measured: 45 test fixtures were building decomposed nodes with no register and now carry one.
   **Open — not the level exactly:** §11.5's reported exception is not implemented (the engine examines a
   Dep edge at a split holding both its ends and routes no report to an outside consumer's issuer); and
   the engine's CHECK-4 is narrower than §9.5's (corner 13), so it admits a register the canon's
   Syntactic level refuses. **Open, on placement:** the canon puts the level at the split's admission,
   the decomposer's own act (§11.5); the engine refuses the child's ACCEPT instead, a refusal its sender
   can lift by no move of his own wherever the decomposer and the child's executor are different parties
   — non-conforming there under §12.16 (ii) (§16.12).

10. **The pre-execution Level-2 gate is an ENGINEERING corner, declared — not a canon row.**
   The engine refuses a child's first ACCEPT while its parent's decomposition carries no current,
   dispositioned causal review (`GFSO_L2_GATE`, on by default). The canon licenses no such gate:
   admission is the Syntactic level (§11.5), and the Pragmatic level is checkable only by execution
   (§9.1, §20.2). What the gate enforces is therefore weaker than its name suggested and is stated as
   such in the code: **not** the checker's verdict but the verify-vs-explore decision (§9.9) taken once
   and made mechanical — the check must have HAPPENED over this version of the plan, and each finding
   must have been either repaired or disputed in writing (`dispute_finding`). The verdict stays
   advisory; contact keeps the last word (q_D). `GFSO_L2_GATE=0` is the explicit EXPLORE branch, chosen
   by configuration rather than by an agent skipping a step. The grade: an engineering discipline
   consistent with §9.9 in what it asks, carrying no canon authority, and placed like corner 9's gate on
   the child's ACCEPT — conforming only where the decomposer is the child's executor (§12.16 (ii));
   measured on the live substrate (BCB/120: three L0-clean plans, every planted entailment hole named,
   zero false gaps). Two earlier citations claimed more — an address, **13.4-bis**, that exists in no
   version of the canon, and the label "Level 2" used as if §9.5 gated the Pragmatic level. Both are
   corrected in place (`gfso/engine/validation.py`, `tests/test_l2_gate.py`); what the gate does is
   unchanged.

11. **Three §9.5/§12.4 rows the engine read wrongly, and one signal it should never have taken
   (CLOSED).** Repairs, not corners — each is the canon's own sentence, and the code now says it:
   **CHECK-2** verified acyclicity of Dep and called it the row for D, so D-acyclicity (§9.5, §15.3) was
   checked nowhere; a node could be created as its own parent through the authoring door (measured). It
   is now decided where each part of it is visible — the split's own shape in `check_dag`, the ancestor
   chain at the ASSIGN that would close a cycle (`Engine._assert_no_d_cycle`). **CHECK-6** quantified
   over every child where §9.5 quantifies over the split's leaves (a root names its executor at its
   creation, §15.2). **`VALIDATING · ASSIGN→OFFERED`**, a row of §12.4 that §12.14 leans on for
   pre-registration, was refused outright over measured churn; it is admitted now, and the
   re-presentation price §12.10 names is charged instead — the pending PASS is voided at the revision,
   so the node cannot settle on a verdict about a contract it no longer carries. And **`TIMEOUT`**, a
   system mechanism, not a signal (§12.2), was reachable through the tool door: sent on a node in
   VALIDATING it produced `DONE(auto_pass)`, a terminal around the AND gate (Thm 1), around verifier ≠
   executor (§10.3) and around Inv-3. The door now closes on the twelve P2P signals and the engine
   refuses a system signal that carries a sender.

12. **The composition function `fᵢ` does not exist in the model; CHECK-7 hardcodes ONE of them.**
   The canon's split may declare "the **composition function** fᵢ by which its responsible children's
   criteria secure it" (§2.4), which the Semantic level reads (§9.1) and CHECK-7 tests under (§9.6). In
   the code `CriterionMapping` carries only the pair ⟨criterion name, child⟩ — there is nowhere to put
   fᵢ — and `check_sufficiency` supplies a fixed one: it parses numeric bounds and **sums** the
   children's values, so the canon's own worked example (100 + 100 ≤ 200) is checked and, say, a
   max-composition (`latency = max(a, b)`) or a conjunction over booleans is not: such criteria fall into
   the `beyond_tier` bucket and the check reports itself skipped rather than green — the honest half of
   the present state. The gap is therefore not a false PASS but a **missing primitive**: CHECK-7 runs
   mechanically only where the intended fᵢ happens to match the built-in sum (CHECK-8, joint
   satisfiability, reads no fᵢ). Closing it is design work, not a patch — fᵢ must be authored somewhere
   an agent can write it (a field on the mapping), typed enough for the solver (sum / max / min /
   conjunction / a formula for SMT), and defaulted for the existing graphs. Cost, honestly: a schema
   field + a migration of 149 stored graphs + the CHECK-7 dispatch + the authoring verb and its prompt.
   **Not started; declared here so the Semantic level is not read as more than it is.**

13. **The risk record carries no `estimate⟨P, impact⟩`, so §9.4's roll-up is not computable.**
   `AcceptedRiskItem` is `⟨item, predictability, justification, invalidation_condition⟩` — no P, no
   impact — so the roll-up exists in the canon (§9.4) and nowhere in the code, and what the engine's
   CHECK-4 verifies is a form of its own (a predictability verdict per factor, no self-declared
   ORDINARY, a justification for STATISTICAL). `invalidation_condition` is stored and surfaced but never
   checked, in either direction: neither its presence nor whether it has fired. The canon's CHECK-4
   (§9.5) refuses admission without the four STD-1 fields and the estimate (§11.5): an entry with no
   estimate passes the engine's CHECK-4 and fails the canon's — the engine diverges from the canon here,
   not the canon from it. The discriminator between a scope boundary, an entry and an omissible
   extraordinary event (§9.2, §9.3) is carried by the *predictability verdict*, a proxy for the
   estimate rather than the estimate. Closing it: two fields, the roll-up as a graph query beside the
   metrics, and a decision on what a missing estimate means for an existing register (the same
   migration surface as #12). **Not started.**

14. **`risk_components` is free text matched by substring — not the STD-3 factorization.**
   STD-3 (§9.4) groups correlated factors into components, each handled as §9.4 states. The code holds components as bare strings, and CHECK-5 once counted one
   covered when its lowercased text appeared **inside a child's description** — which is neither the
   grouping nor a coverage relation: it passes on an accidental word match and fails on a child that
   addresses the component under any other wording. It is a placeholder with a check-shaped surface.
   The honest option space is either the real object (components as first-class records, factors
   assigned to them, coverage declared by mapping rather than guessed from prose) or a demotion of
   CHECK-5 to what it can decide. Either way it is a design decision, not a repair. **Not started.**

15. **Inv-4 (Obligation-Symmetry) has no code object; its checkable content is Inv-8.** Of the eight
   invariants, seven are enforced or machine-checked: Inv-1, Inv-2, Inv-3, Inv-5 (pure timeout chains in
   Lean, run level in TLC), Inv-6, Inv-7, and Inv-8 (`FsmCanon.inv8_canon`, `inv8_mirror`). Inv-4
   operates only through the reading §12.9 adopts: its clause (1) is what Inv-8 checks, its clause (2)
   pins CANCELLING and ESCALATED (§12.13). The meta-check this entry used to ask for — "every state gives
   EACH role a move" — was the wrong shape: in the issuer's waits (CHALLENGED, BLOCKED, VALIDATING) only
   the issuer has one, correctly. Inv-8 asks for the OWNER's move, which is what is decided. The
   engine's own conformance to it is the test suite's (`tests/test_model_conformance.py`), not Lean's.

**Two boundaries the E3 measurement walked into, delineated rather than patched (2026-08-16).**

* **A vacuous Level-2 pass.** The gate reported `semantic_covered: true` over `criteria_checked: 0`
  — truthfully, since the node it was checking carried no criteria at all. The hole is closed on the
  structural side (CHECK-1 now fails a node that has children and no criteria of its own: by A1 an
  empty criteria set makes the node unverifiable, not covered), but the CHECKER itself still cannot
  tell "nothing to check" from "nothing to report". Kept as a boundary because the fix belongs to
  the checker's own contract, which is a measured artefact — its wording is calibrated (`EVIDENCE_LOG` §13.6) and
  changing it silently would confound the next reading of C1.

* **`ESCALATED` — the issuer's waiting state, not a settlement (§12.5).** Its entries, owner, moves and
  silent closing are §12.5 and §12.13's; the engine's re-ASSIGN out of it may omit the spec, never a live
  deadline. "The executor says the contract is wrong" does not come here: that is CHALLENGE (§12.4). The
  rework bound is a packet field (§12.3), finite, its value unfixed (§12.15).

**Named abstraction (not a drift): the R′ reopen edge is not in the per-node Lean automaton.** `fsm.py`
admits a gated re-ASSIGN out of DONE/ABANDONED (R′, §12.14) whose gate is a GRAPH predicate (§12.14;
`fsm.py` reads the consumption and counter halves from its GuardContext) — outside the per-node
signature this file models. Lean holds the terminal-absorbing base automaton (under R′ a terminal is
absorbing once final, §12.14); over the log, with the gate an input at the settlements, R′'s cells are
machine-checked forced (`LogLanguageReopen.forced`, §13.5); the reopen edge is TLC-checked at one
node (`formal/tla/FsmSpike.tla`) and its graph gate is code-tested (`tests/test_reopen.py`).

## Layout

`GFSO/Postulates.lean` is the closure: the named tiers (0–7b), every postulate, and how each is
carried. Start there.
