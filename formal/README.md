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

## Code ↔ canon corners

Where the engine departs from the canon, and how each departure was settled, is the engineering layer's record, kept in
[`docs/architecture.md`](../docs/architecture.md) under the same heading and the same numbers the Lean comments cite
(`corner #1`, `corner #3`). The Lean development encodes the canon, not the engine.

## Layout

`GFSO/Postulates.lean` is the closure: the named tiers (0–7b), every postulate, and how each is
carried. Start there.
