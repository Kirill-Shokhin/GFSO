# GFSO formal core — machine-checked in Lean 4

Machine-checked formalization of the **formal spine** of the GFSO canon
(`../docs/applied_gfso_v4_en.md`), in Lean 4. **No mathlib** (Lean core only), **no `sorry`**, **no
`native_decide`** — and the assumption set of this encoding is not asserted, it is **enforced by CI**.

## The result, stated honestly

This is **an audit of GFSO's axiomatic surface**, machine-checked: which of the canon's claims are
definitional, which are irreducible postulates, and how many. It is *not* a proof of GFSO's
substantive claims. Ranked by how much each is worth:

1. **The assumptions of this encoding are enumerated and enforced.** Every "why exactly N?" is
   either *definition-unfolding* (the kernel checks it) or a *covering principle* ("there is no third
   kind", over an undelimited space). Type theory forces the latter into an `axiom` — **but only once
   you decide where to put it.** That decision is the encoder's, and this development contains its own
   counterexample: `|Act| = 2` ("there is no third action") is a covering principle in substance, yet it
   is encoded as a two-constructor inductive and so never appears in `#print axioms`, while CA1
   ("there is no third evaluation axis") — the same shape — is an explicit axiom.
   **So "three" is a fact about this encoding, not about GFSO.** What is encoding-invariant: the
   covering principles are finitely many, and here is one honest enumeration with every placement
   disclosed. The guard then makes *that* enumeration an invariant the engine defends.
2. **CA2 is discharged: the operational axis is clock-free.** Coverage of a three-cell operational
   classification needs *no assumption at all* (`phases_exhaustive`), and the partition needs only
   asymmetry — which every strict order has. The phase COUNT never depended on the clock, so
   single_clock is carried as a *hypothesis* (`SingleClock`), not an axiom, and is gone from
   `#print axioms`. **The cost is real but is not a covering axiom:** what totality buys is exactly the
   **reading of the middle cell** — it collapses "causally concurrent" to "equal", letting the phase be
   read as *during* the evaluation interval rather than *incomparable with* it
   (`total_collapses_concurrent`, itself axiom-free once totality is a hypothesis). That reading is a
   genuine thing totality buys — it is simply not a postulate about the *count*, so it is not listed as
   a covering axiom (§12.8). The remaining canon clauses of CA2 — per-event atomicity and
   re-entrant validation — are protocol *dynamics* (a clean verdict), a separate object from the
   taxonomy, untouched here. `GFSO/Time.lean`.
3. **The spine compiles.** Thm 1 and its converse, |L|=2, Thm 2 (16-op enumeration), the 4+3 FM geometry
   and its 7 independence witnesses, FSM determinism/finiteness/handshake, the 4/4/3/1 signal count,
   `state = fold(log)`. Correct and faithful — and elementary. The value is the *map*, not the depth.
4. **The guard map is machine-checked.** No CHECK lives at the Pragmatic level; **FM-3 and FM-6 are guarded by no
   structural check at all**. The canon states both in passing (§13.4, §13.6); here they are decided
   off the table rather than asserted.

**What is assumed, not proved.** 7-FM completeness, the Morris trichotomy, and the completeness of
the five links are **axioms**. The Lean theorems around them (`fm_basis_covers`,
`knowledge_gap_located`, `missing_link_located`) add only a classical De Morgan localization — they
machine-check the *step from the axiom*, not the axiom. What *is* axiom-free around them: the 4+3
geometry, the 7 witnesses, the 3⊕2 count.

**Read the "honest reading" docstrings.** Three results are true but forced by the modelling choice,
not derived: `lemma1_S_underdetermined` (SINGLE-SEAM's *form*; `S` is a free field and the apparatus is
*defined* S-free), `basis_independent` (a 4-tuple of free bits has four independent coordinates),
`metrics_components_bijection` (two 5-element enums defined to match). Each says so in place.

**What this is not.** Not a proof that GFSO is correct, complete, or empirically valid. Not a
formalization of the classical results it imports (Prop 3–9). Not a proof that the basis is minimal in
§10.2's semantic sense, nor that Lemma 1 holds for a rich apparatus. The empirical boundary is not
closed — it is *localized*, into one uninterpreted predicate.

## Scope: what "three" is and is not

Three is the number of covering axioms **this encoding chose to make explicit**, within the formalized
fragment. A different faithful encoding moves the line (make `|Act|=2` an axiom and it is four). The full picture:

| Kind | Items | Where it lives |
|---|---|---|
| **Covering axioms** (3) | CA1 (§12.8) · Morris (§13.4) · directed-action completeness (§4) | `axiom` — visible in `#print axioms` |
| **Definitional** (4) | A1, A2 (§9), \|Act\|=2, the d3/d4 source space (`KnowledgeSource`) | baked into the *types* (`Verdict := Bool`, `Decomp`, `Act`, `KnowledgeSource`). The last two are covering principles in substance, invisible to `#print axioms` — at DIFFERENT grades: `KnowledgeSource`'s exhaustiveness is argued by nested excluded middle, `\|Act\|=2`'s candidate space is undelimited (canon §1.4) |
| **Hypothesis-form** (3 groups) | act-surjectivity + act-injectivity (the \|L\|=2 defense) · not-apparatus + no-declaration + no-luck (agent necessity: the apparatus arm, Lemma 2's regress, luck-instability — three premises in the signature, the apparatus one *also* discharged separately by `no_apparatus_yields_S`, which is why the canon calls the derivation pinned rather than assumed) · `SingleClock` / CA2 (§12.8, discharged) | premises in the *signature* of `L_forced_two`, `agent_necessary`, `op_trichotomy_of_total` |
| **Out of scope** | Prop 3–9 (Blackwell, Simon, Hurwicz, cascade) | imported classical results; need ℝ/probability = mathlib |

A *definitional* postulate cannot be a Lean axiom without being vacuous: prose says "there is no
third action", the type says "you declared two". A *hypothesis* is dischargeable in principle and is
visible in the theorem's type; an *axiom* is not. Conflating the two is a mistake — `L_forced_two` is
**axiom-free** even though it has premises.

## Coverage — every canon result, accounted for

`✔` machine-checked · `⚠` machine-checked *modulo a named axiom* · `◐` true but **forced by the
modelling choice** (the shape is formalized, the canon's semantic content is not) · `○` out of scope.

| Canon result | § | Status | Where |
|---|---|---|---|
| Thm 1 compositionality (+ its converse) | 11.1 | ✔ | `Compositionality.T1`, `.T1_characterization` |
| \|L\| ≠ 2 impossibility | 11.2 | ✔ axiom-free | `Binarity.L_forced_two` |
| Thm 2 uniqueness of AND | 11.3 | ✔ | `AndUniqueness.and_unique` |
| 7-FM completeness | 12.4/12.8 | ⚠ CA1 | `FailureModes.seven_fm_complete` |
| 7-FM independence (7 witnesses), 4+3 geometry | 12.5/12.6 | ✔ axiom-free | `FailureModes.*` |
| Operational trichotomy | 12.3/12.8 | ✔ axiom-free (CA2 discharged to a hypothesis, §12.8) | `Time.*` |
| Minimality of basis (independence half) | 10.2 | ◐ structural (free-coordinate model) | `Ontology.basis_independent` |
| Uniqueness of basis | 26.9 | ○ globally open — the wall is narrowed and pinned to the FO-frame stipulation; §26.9 proves σ-canonicity over the Beth class | — |
| Uniqueness of protocol | 26.9(b) | ◐ FALSE over bare adequacy (`decide` witness: a VALIDATING-timeout→ESCALATED variant is adequate yet behaviourally distinct — adequacy pins exit existence, not destination; + `max_iterations` a 2nd orthogonal free cell, argued). Open only over a FULLY pinned design vector (same wall as basis uniqueness). **Asymmetric to (a):** minimality positive both sides, but (a) is canonical over a natural Beth subclass while (b) is canonical over none (its determination hypothesis = its conclusion). **Positive core:** adequacy pins a minimality-forced 9-state skeleton (up to behavioural equivalence, argued); the freedom is decorations (REWORKING via max_iterations; OVERDUE + ESCALATED via the timeout geometry — removable on the finiteness axis machine-checked (`noOverdue_*`/`noEscalated_*`), full adequacy argued), partitioning the 11 classes as 9 forced + 2 free + REWORKING≡EXECUTING. Inherited bi-interpretation currency vacuous (every adequate finite protocol is rigid). **Inner enumeration** (over the fixed alphabet — a finite matter distinct from the walled outer completeness): each cell graded on strength (fatal vs sole/genuine-provider) × function (channel/resolution/genuineness); resolution destinations (RESOLVE_BLOCK/REJECT_CHALLENGE) existence-forced but destination-free; ACCEPT_CHALLENGE→OFFERED and re-ASSIGN→OFFERED Inv-1-forced; CANCELLING forced by IC not deadlock (`oneStepCancel`); ~10 canon-internal necessary-condition witnesses, the over-all-protocols forcedness still argued | `FsmCanon.variant_*`, `.noOverdue_*`, `.noEscalated_*`, `.canon_reaches_overdue`, `.canon_reaches_escalated`, `.canon_exec_reaches_done`, `.nodeliver_strands_done`, `.noAssign_strands_start`, `.noBlock_strands_blocked`, `.noChallenge_strands_challenged`, `.noCancel_strands_abandoned`, `.accept_sole_content_consent`, `.accept_not_fatal`, `.resolveBlock_sole_content_resume`, `.rejectChallenge_sole_content_resume`, `.noPass_only_autopass_into_done`, `.noConfirm_only_timeout_into_abandoned`, `.canon_reassign_to_offered`, `.acceptChallenge_dest_inv1_forced`, `.oneStepCancel_*` |
| State irredundancy (12 states → 11 behaviour classes; EXECUTING ≡ REWORKING) | 14.3/26.9(b) | ✔ axiom-free (`decide`, negative control) | `FsmCanon.canon_exec_rework_same`, `.canon_eleven_pairwise_distinct` (all pairs, joint observable), `.canon_others_pairwise_distinct`, `.canon_settlement_separates_terminals` |
| REWORKING and EXECUTING agree on the BLOCK row (the canon derives the edge from §14.2 — no divergence) | 14.3 | ✔ axiom-free (the theorem compares the two rows inside the engine table; the canon-vs-engine identity is read off `canonStep`) | `FsmCanon.engine_agrees_on_rework_row` |
| 3 verification levels | 13.4 | ⚠ Morris | `Standards.knowledge_gap_located` |
| CHECK↔FM guard map; Pragmatic-level & FM-3/FM-6 unguarded | 13.4/13.6 | ✔ axiom-free (the canon's §13.6 row now states A1 fixes FM-3's *form*, not its truth) | `Standards.*` |
| Signal defect distribution (12 = 4/4/3/1) | 14.2 | ◐ `decide` over a hand-entered table, not a minimality proof | `Protocol.defect_distribution` |
| Inv-5 finiteness | 14.4 | ✔ (IDLE exempt by Inv-5, carried as an `s ≠ IDLE` hypothesis) | `Fsm.timeout_terminates` |
| Inv-6 determinism | 14.4 | ✔ | `Fsm.step_deterministic`, `.step_iff_admissible` |
| Inv-1 revision = re-ASSIGN, not cancel | 14.4 | ✔ | `Fsm.reassign_to_offered` |
| Cancellation handshake completes | 14.3 | ✔ | `Fsm.cancel_handshake_terminates` |
| Inv-2 binarity of V | 14.4 | ✔ definitional | `Ontology.Verdict := Bool` |
| Inv-3 FAIL ⇒ failed_criteria ≠ ∅ | 14.4 | ○ payload-level, not a state-machine property | — |
| Inv-4 symmetry of obligations | 14.4 | ○ normative, not a state-machine property | — |
| Inv-7 (Identity-Stability), log clause: the record is the LOG; state = fold(log) | 14.4/22 | ✔ | `Metrics.replay_append`, `.log_append_only` |
| Inv-7, id clause: one id carries the successive versions of a spec (re-ASSIGN, never delete+create) | 14.4 | ○ graph-level, not encoded — the Lean development has no N × N edge model to orphan | — |
| Thm 10 self-measuring Q (constructive core) | 21 | ✔ | `Metrics.Q_self_measuring` |
| Q index set: 5 metrics ↔ 5 components | 15.2 | ◐ structural (enums defined to match) | `Metrics.metrics_components_bijection` |
| Thm 11 structural transparency | 22 | ✔ | `Metrics.replay_append` |
| Ordinal severity ⪰_dom (preorder on nodes · partial · antisymmetric on probe-sets · count-independent) | 6.3 | ✔ axiom-free — reflexivity/transitivity/antisymmetry **universal** (by induction), partiality and count-independence by witness, with a finite carrier + negative control | `Grading.dom_refl_all`, `.dom_trans_all`, `.dom_antisymm_all`; `.dom_partial`, `.dom_count_independent`, `.dom_not_constant_true` |
| 5 constitutive links (3 ⊕ 2) | 4 | ⚠ §4 axiom, and **below CA1 grade**: its representational branch rests on REACHES-ternarity, which has no preceding orthogonality-and-exhaustion theorem and folds START into the execution-anchored present by a declared modeling choice (§4.2, Ch. 8). The 3⊕2 count is axiom-free | `Links.*` |
| Lemma 1 (SINGLE-SEAM) — its logical form | 2.5 | ◐ definitional (apparatus is *defined* S-free) | `TheoryModel.lemma1_S_underdetermined` |
| …its consequence: no `FormalView → S` exists | 2.3 | ✔ axiom-free | `TheoryModel.no_apparatus_yields_S` |
| Agent necessity d1–d6 | 3.2 | ✔ elimination (Lemma 2 + luck are premises) | `TheoryModel.agent_necessary` |
| Lemma 2, luck-instability | 2.5/3.2 | hypothesis-form | signature of `agent_necessary` |
| Prop 3 Blackwell dominance | 16 | ○ needs ℝ/information structures — imported (Blackwell 1953) | — |
| Prop 4 constraint improvement | 17 | ○ imported (Simon 1955) | — |
| Cor 5 α-monotonicity, Prop 6 temporal monotonicity | 18.1/18.2 | ○ corollaries of Prop 3 — imported | — |
| Prop 7 cascade ‖eₙ‖ ≤ (Λ·γ)ⁿ‖e₀‖ | 18.3 | ○ needs ℝ / operator norms | — |
| Prop 8 IC (dominant strategy) | 19 | ○ needs a payoff model — imported (Hurwicz 1960) | — |
| Prop 9 decomposition quality | 20 | ○ composite of Prop 3/4/6/7 | — |
| Pragmatic-level faithfulness (the residue) | 8 | permanent boundary — *localized*, not closed | `correct` left uninterpreted |

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
```

**A green build is not proof of a proof.** During the original spike a name collision silently made a
definition elaborate to `sorry` while the visible errors were only downstream. Hence:

- `check_closure.sh` is **fail-closed**. It does not grep the footprints of a hand-listed set of
  theorems (that is fail-open: forget to list a theorem and its axiom hides). It runs
  `audit_env.lean`, which **walks the whole compiled environment** and reports every `axiom` *and*
  every `opaque` under `GFSO.*` — at any nesting depth, under any name, used or unused. Then it
  diffs against `AXIOMS.whitelist` and rejects any `opaque` outright (an `opaque` constant is an
  uninterpreted assumption that `#print axioms` cannot see). It also fails on `sorryAx`.
  *The postulate set is an invariant the engine rejects violations of, not a claim made once.*
- `check_refs.sh` — fails if `formal/` cites a canon section that no longer exists. It catches
  citation drift; it **cannot** check that a Lean statement still *means* what its section says.

**Disclosed limit.** An assumption moved into a theorem's *signature* (a hypothesis) is invisible to
the guard, by construction and legitimately: a hypothesis is dischargeable and is visible in the
theorem's type. So `axiom-free` certifies *"assumes nothing beyond its stated premises"*, not
*"assumes nothing"*. Semantic conformance between a Lean statement and its canon section remains a
human/agent job — exactly as a passing `pytest` suite does not certify that the right tests were written.

CI runs all four guards on every change to `formal/` **and to the canon**.

## Code ↔ canon corners (flagged, not patched — canon is truth)

*(The three that were LIVE divergences of the ENGINE from the canon — **#3**, an edge the canon denies,
**#1**, a row the canon exempts, and **#5**, a failure mode routed to the wrong repair — are now
CLOSED: the engine carries the canon's shape and each entry records what landed. The rest are settled
by the canon and kept because the Lean encoding is where they show.)*

1. **IDLE has no timeout — the canon's position; the engine now agrees (CLOSED).**
   `gfso/core/protocol/fsm.py` used to carry an `(IDLE, TIMEOUT)` row, added by the engineering pass
   under the **v3.9** reading in which Inv-5 was TOTAL over non-terminals. The v4.0 canon exempts IDLE
   **by name**, so the row was removed. What it had been written for — a crash orphan, observable in
   IDLE because CREATE_TASK persisted while the same ASSIGN's landing did not — is answered where the
   defect actually lives, and a root orphan (no parent whose clock could surface it) is the case that
   made a bare deletion insufficient: `Engine._recover_orphans` re-sends the packet-less ASSIGN at
   startup, so the interrupted transition finishes through the queue — validated, logged (Thm 11),
   never a silent state write (`tests/test_inv5_timeout.py`). The reasoning, unchanged:
   `Fsm.idle_has_no_timeout` proves `step IDLE TIMEOUT _ = none`, and IDLE is a non-terminal — which
   Inv-5 exempts by name ("every non-terminal state **except IDLE**"), as §14.2/§14.3 now state in
   their routing sentences too. v4 §14.3 settles which way: deadlines attach at ASSIGN,
   so "IDLE precedes any contract and carries no clock of its own; **Inv-5 is not breached at this
   corner**" — an IDLE child gates its parent only through the parent's AND, and the parent's contract
   carries the clock. So it is the pre-contract-state disjunct, not a missing `fsm.py` row. The
   finiteness theorems keep their explicit `s ≠ IDLE` hypothesis, which is exactly that fact in the
   type rather than papered over.
2. **IDLE + CANCEL → CANCELLING — settled by the canon, not a divergence.** A not-yet-assigned node can
   be driven into the cancellation handshake via the universal-CANCEL catch-all. §14.3's per-state
   admissible sets carry exactly this row (`IDLE | ASSIGN→OFFERED · CANCEL→CANCELLING`), the catch-all
   being stated over every non-terminal ≠ CANCELLING, of which IDLE is one. Arguably vacuous; encoded
   faithfully because it is what both the canon and the code say.
3. **`(VALIDATING, FAIL, iteration ≥ max)` — the edge the canon denies is GONE (CLOSED).**
   The code, `Fsm.lean`, `FsmTable.tla` and `docs/architecture.md` now all route the exhausted rework
   loop to ESCALATED, and the terminal carries `done_reason=FAIL` so a verdict-escalation stays
   distinguishable from the two timeout routes into ESCALATED — without which the standing-FAIL metric
   populations (q_D's exhausted arm, `false_fail_share`) would have silently emptied, a blind metric
   reading as a clean one. The record of why, unchanged: §14.3 routes the exhausted rework loop to **ESCALATED**
   ("the FAIL↔REWORKING loop bounded by max_iterations", with escalation as its exit), and §12.2
   states as fact that **"DONE is reached through acceptance (PASS ∨ auto_pass), never through fail
   (Chapter 14)"**. This is not a naming lag — it is the FSM's shape. It is also **load-bearing**:
   "DONE ⇐ acceptance" is the stated premise of false-FAIL guarantee-safety, which is what licenses
   q_V's one-sidedness (§12.2, §15.2, §24.5) — a DONE reachable through fail would make a false-FAIL
   able to fabricate a terminal acceptance, which is exactly what the canon argues cannot happen.
   **What forced the target (derived from the canon, not a doc-status call), and still justifies it:**
   four independent canon facts converge on ESCALATED, none of them "the doc says so":
   (1) the canon has **no** terminal for "V = fail, settled" — its negative terminals are ABANDONED
   (V = ⊥, cancelled) and ESCALATED (attention); DONE(fail) invents a category the canon deliberately
   omits. (2) Exhausting the retry loop IS the escalation trigger by the protocol's purpose (§1.1:
   "trust, but see" — automatic handling failed ⟹ the third mode, attention); marking it DONE
   buries a failure as "completed", the exact anti-pattern GFSO exists to prevent. (3) DONE is
   consumed under R′ (§14.3: a Dep consumer reads-and-builds on the result) — a DONE(fail) would let a
   neighbor build on a failure. (4) The honest state of a parent with an unresolvable child is V = ⊥
   (attention needed), which ESCALATED gives and DONE(fail) wrongly bypasses by auto-computing AND →
   fail. (§12.2's guarantee is NOT the load-bearing reason — it survives either way, since DONE(fail)
   carries V = fail and never enters q_V; the reason is 1–4.) What landed: the target is ESCALATED,
   terminal and NOT quasi-terminal — recovery is a human re-issue/revise, not a reopen — and the live
   path is tested through the engine rather than the transition table alone
   (`tests/test_integration.py::test_exhausted_rework_escalates_and_stays_a_verdict`).
4. **`(REWORKING, BLOCK) → BLOCKED` — the engine had an edge the canon's DIAGRAM omitted; RESOLVED in
   favour of the engine by §14.3.** `fsm.py` (and `Fsm.lean`) route BLOCK from REWORKING to BLOCKED;
   the v4 §14.3 diagram drew REWORKING with only `DELIVER`. Not a code divergence but a canon drafting
   gap: §14.2 grounds BLOCK on "the executor can report a blocker", and REWORKING is a work-active
   state under the same contract (Inv-1), so a blocker met during rework must be reportable — without
   the edge it is an unreportable defect (FM-7), exactly what BLOCK precludes. The edge is **derived**,
   the engine is right, and §14.3 now writes the admissible sets out per state (closing the diagram-only
   gap that let this hide). Consequence (`FsmCanon.lean`): with the edge, EXECUTING ≡ REWORKING
   behaviourally — REWORKING is an attribution label, and the twelve states carry eleven behaviour
   classes (§26.9(b)).

5. **The re-DELIVER refusal prescribed the wrong repair for an FM-1 failure (CLOSED).**
   `gfso/engine/validation.py` refuses a parent's re-delivery when its FAILed criteria
   are covered by children untouched since that FAIL — the refusal itself is right, a re-delivery of
   an unchanged aggregate decides nothing — but its message routes the repair DOWNWARD: *"Rework
   flows DOWN: reopen the covering child … and rework it there"*. For this failure mode that is
   prescriptively wrong. A parent's criterion failing while every child passes its own is by the
   canon's own definition the **q_D event** (§15.2, "non-atomic, own validation returned FAIL while
   all active children were passing") and the defect class is **FM-1.d** (children exist but
   `⋀criteria(tⱼ) ⊭ cᵢ`) or **FM-1.f** (the goal needs a criterion nobody wrote) — a defect of the
   DECOMPOSITION, owned by whoever built it. Each child met its contract; asking one to redo what
   its criteria never required is asking it to guess. The canonical repair is a **revision of the
   parent under Inv-1**: re-ASSIGN the parent with a corrected mapping and, where coverage is
   missing, an added covering child. Inv-1 states that a revision does NOT cascade — the subtree is
   retained and staleness surfaces through CHECK-1 + CHECK-1b + CHECK-3 — so no child is reopened
   and the consumption gate is not involved at all.

   Observed live (`EVIDENCE_LOG` §13.3, `markdown_renderer`): following the message's own route the
   arm hit a wall, because `Graph.is_consumed` locks a DONE child on which any Dep-consumer built,
   and a graph with 20 seams over 11 nodes has no unlocked covering child. The wall is a
   consequence of taking the wrong route: on the revision route it is not reached. Two things
   follow for the engineer, and the second is what keeps the fix honest: (a) the refusal message
   must name the parent-revision remedy; (b) adding coverage so that `⋀children ⊨ cᵢ` is the repair,
   while lowering `cᵢ` to what the children already deliver is a false close wearing the same
   shape — the two are told apart by what CHECK-1/CHECK-7 say after the revision and by whether the
   fail-extension of `cᵢ` shrank. Without that discriminator both moves would have to be forbidden,
   and the only legal repair would be lost with them.

   **What landed** (`_refuted_coverage_refusal`, `tests/test_fm1_repair.py` — one planted case per
   class). (a) The refusal names the revision of THIS node under Inv-1. (b) The discriminator reads
   the criteria as they stood when contact refuted them (snapshotted on the verdict record) against
   the criteria now, and disposes of each failed criterion: a criterion REMOVED, or LOOSENED where
   loosening is decidable — same metric, same operator, a bound admitting strictly more, the
   numeric tier where CHECK-7 is O(1) — is refused as a false close, its fail-extension having
   shrunk; a criterion EDITED undecidably is admitted once the revised plan's checks have spoken
   again (L0 clean plus a current, dispositioned L2 verdict — the check must have HAPPENED, never
   that the checker is right, and `GFSO_L2_GATE=0` opts out of that half exactly as it does at the
   execution gate); an UNREPAIRED criterion (unchanged, every coverer untouched) keeps the original
   refusal; a touched coverer passes as before. Two scope notes, each load-bearing: the gate now
   follows the node across the OFFERED→EXECUTING repair route rather than firing in REWORKING alone,
   since a revision leaves REWORKING and the criterion-lowering route would otherwise never be
   examined; and it keys on the node HAVING a decomposition rather than on its mappings, since
   deleting the refuted criterion also deletes the mapping that pointed at it — a mapping-keyed
   trigger would have let exactly the false close through. A leaf stays out of scope: its contract
   belongs to the issuer above, whose CHECK-1 surfaces any hole a rewrite leaves.

   *(Threshold note, parked with a reason: §14.3 names the moment of the consumption threshold as
   the single design freedom and the current point — "consumed while any Dep-consumer exists" — as
   a deliberate over-approximation. A narrower reading derivable from its own predicate is to lock
   on finality IN THE CONE rather than on the existence of a Dep edge. It is not needed while (a)
   and (b) stand; if the wall reappears on the revision route, that is the measurement that would
   justify touching it.)*

6. **The vertical deadline rule now has a pre-exec check — the ENGINE's gap is closed; CHECK-3 is
   unchanged.** §26.5-bis names two "un-operationalized form items": non-redundancy beyond its
   topological proxy, and deadline coherence along D (child < parent, §3.4 item 6), which CHECK-3
   does not guard — it carries only the horizontal Dep rule, and §14.6/§15.4 say so in as many
   words. The vertical one is L0 by construction (two packet fields, no domain knowledge), and
   §15.4's triage tie-break leans on it, so it now rides in the same check function
   (`check_deadlines`, `tests/test_structural.py`): a child whose deadline is not strictly before
   its parent's fails the battery before execution. What closed is the implementation gap, **not**
   CHECK-3's canon definition — the rule enforced here is §3.4 item (6), and any prose that credits
   it to CHECK-3 is wrong about the canon. Absence of deadlines stays silent — a deadline is a
   design decision, not a mandatory field (§10).

7. **Non-redundancy beyond the topological proxy — still open, and now stated where it shows.**
   CHECK-1b tests "every child is mapped to some parent criterion" and is accordingly renamed to
   its honest name, `CHECK-1b:no_orphan` (a decision of the v4.0 naming pass, not a canon §; the
   §10 CONDITION keeps the
   name *non-redundancy*, Round 2). What §10 actually demands — that a child's FAILURE breaks the
   parent — is not decidable from the topology: it asks whether the parent's criteria really
   depend on that child's, which is CHECK-7 territory at the Semantic level and the Pragmatic
   boundary past it. Left open deliberately, with the proxy named as a proxy rather than dressed
   up as the condition.

8. **§15.4's triage ORDER is not what `next_step` implements — named, not silently adopted.**
   The canon orders repair by the failing node's dependency cone with the nearest binding deadline
   as the tie-break, and says it "costs no new machinery" (a reachability query over 𝒢 plus packet
   fields). `Engine._frontier` orders by action priority and then by id. The gap is real and the
   fix is cheap — but it changes the ORDER in which an agent is driven through a graph, which is a
   measured quantity of the E3 arm (C3 cost, and through it C1/C2 attribution). Landing it inside
   a naming migration would confound the next measurement with a behavioural change, so it is
   recorded here and lands as its own change, measured against a run that did not have it.

9. **The execution gate was a SELECTION from the Syntactic level; it is now the level (CLOSED).**
   §13.4 lists CHECK-1, 1b, 2, 3, 4, 5, 6 at Level 0 and rules that "a decomposition that fails the
   Syntactic level is not admitted to execution". The engine gated four of the seven: ACCEPTED_RISKS
   (4), risk nodes (5) and leaf delegation (6) were computed, surfaced by `get_checks`/`list_holes`,
   and never blocked an ACCEPT — so a decomposition with an empty register was admitted, where §13.1
   says one without the register is incomplete by definition. **What was argued for it, and why it
   did not survive:** gating the register had been tried and measured — an agent that cannot start
   until the register is non-empty writes a register in order to start, so the gate bought fabricated
   entries and `edit_accepted_risks` churn. That is a fact about an incentive, not about whose rule
   it is; a fabricated register is a q_T defect with a name and an owner, while an ungated canon level
   is a silent one. The gate is now the level exactly (`gfso/engine/validation.py`), pinned in both
   directions by `tests/test_structural.py` — every canon row gates, and CHECK-1c (anti-mock, an
   engineering addition with no canon row) does not. Cost, measured: 45 test fixtures were building
   decomposed nodes with no register and now carry one.

10. **The pre-execution Level-2 gate is an ENGINEERING corner, declared — not a canon row.**
   The engine refuses a child's first ACCEPT while its parent's decomposition carries no current,
   dispositioned causal review (`GFSO_L2_GATE`, on by default). The canon licenses no such gate and
   could not: §13.4 makes the **Syntactic** level the admission condition and files the **Pragmatic**
   level as "runtime detection + learning", because causal correctness is formally uncheckable from
   inside (Ch. 8, the named boundary). What the gate actually enforces is therefore weaker than its
   name suggested and is stated as such in the code: **not** the checker's verdict but the canon's
   own **verify-vs-explore decision** (§13.5) taken once and made mechanical — the check must have
   HAPPENED over this version of the plan, and each finding must have been either repaired or
   disputed in writing (`dispute_finding`). The verdict stays advisory; contact keeps the last word
   (q_D). `GFSO_L2_GATE=0` is the explicit EXPLORE branch, chosen by configuration rather than by an
   agent skipping a step. The grade: an engineering discipline consistent with §13.5, carrying no
   canon authority, measured on the live substrate (BCB/120: three L0-clean plans, every planted
   entailment hole named, zero false gaps). Two earlier citations claimed more than that — an
   address, **§13.4-bis**, that exists in no version of the canon, and the label "Level 2" used as if
   §13.4 gated the Pragmatic level. Both are corrected in place (`gfso/engine/validation.py`,
   `tests/test_l2_gate.py`); what the gate does is unchanged.

11. **Three §13.4/§14.3 rows the engine read wrongly, and one signal it should never have taken
   (CLOSED).** Repairs, not corners — each is the canon's own sentence, and the code now says it:
   **CHECK-2** verified acyclicity of **Dep** and called it the row for **D**, so §10's "a cycle →
   infinite recursion → an A1 violation" was checked nowhere; a node could be created as its own
   parent through the authoring door (measured). D-acyclicity is now decided where each part of it is
   visible — the split's own shape in `check_dag`, the ancestor chain at the ASSIGN that would close
   a cycle (`Engine._assert_no_d_cycle`). **CHECK-6** quantified over every child where §13.4 says
   "∀ **leaf** t", demanding an executor for nodes that decompose further (accountable through their
   own children, §10) while never checking the one node the canon names — a childless root with no
   parent to check it. **`VALIDATING · ASSIGN→OFFERED`**, a row of §14.3's admissible set that §6.3
   leans on when it grades pre-registration, was refused outright over measured churn; it is admitted
   now, and the price §6.3 names is charged instead — the pending PASS is voided at the revision, so
   the node cannot settle on a verdict about a contract it no longer carries. And **`TIMEOUT`**, which
   §14.2 states "is not a P2P signal (no agent sends it)", was reachable through the tool door: sent
   on a node in VALIDATING it produced `DONE(auto_pass)`, a terminal around the AND gate (Thm 1),
   around verifier ≠ executor (§14.5) and around Inv-3. The door now closes on the twelve P2P signals
   and the engine refuses a system signal that carries a sender.

12. **The composition function `fᵢ` does not exist in the model; CHECK-7 hardcodes ONE of them.**
   §13.4's Semantic level is stated over a declared composition: "for each cᵢ the Issuer declares
   *how* the children's criteria secure cᵢ — a composition function fᵢ", and CHECK-7 then tests
   `⋀{criteria(tⱼ) mapped to cᵢ} ⊨ cᵢ` under it. In the code `CriterionMapping` carries only the pair
   ⟨criterion name, child⟩ — there is nowhere to put fᵢ — and `check_sufficiency` supplies a fixed
   one: it parses numeric bounds and **sums** the children's values, so the canon's own worked
   example (100 + 100 ≤ 200) is checked and, say, a max-composition (`latency = max(a, b)`) or a
   conjunction over booleans is not: such criteria fall into the `beyond_tier` bucket and the check
   reports itself skipped rather than green — the honest half of the present state. The gap is
   therefore not a false PASS but a **missing primitive**: the Semantic level runs only where the
   declaration happens to match the built-in. Closing it is design work, not a patch — fi must be
   authored somewhere an agent can write it (a field on the mapping), typed enough for the solver
   (sum / max / min / conjunction / a formula for SMT), and defaulted for the existing graphs.
   Cost, honestly: a schema field + a migration of 149 stored graphs + the CHECK-7 dispatch + the
   authoring verb and its prompt. **Not started; declared here so the Semantic level is not read as
   more than it is.**

13. **The risk record carries no `estimate⟨P, impact⟩`, so §13.1's roll-up is not computable.**
   §13.1 states the register's aggregation as `P(≥1 of the register) = 1 − ∏(1 − Pᵢ)` over
   independent components. `AcceptedRiskItem` is `⟨item, predictability, justification,
   invalidation_condition⟩` — no P, no impact — so the roll-up exists in the canon and nowhere in the
   code, and what CHECK-4 verifies is the record's FORM (a predictability verdict per factor, no
   self-declared ORDINARY, a justification for STATISTICAL). `invalidation_condition` is stored and
   surfaced but never checked, in either direction: neither its presence nor whether it has fired.
   The discriminator that matters is already carried — an entry with no estimable materialization P
   is a scope boundary and belongs in the goal's criteria (§13.1) — but it is carried by the
   *predictability verdict*, a proxy for the estimate rather than the estimate. Closing it: two
   fields, the roll-up as a graph query beside the metrics, and a decision on what a missing estimate
   means for an existing register (the same migration surface as #12). **Not started.**

14. **`risk_components` is free text matched by substring — not the STD-3 factorization.**
   §13.3 asks for correlated factors grouped into components with a common root cause, covering ≥ 90%
   of historical problems, with a risk node per component. The code holds components as bare strings
   and CHECK-5 counts one covered when its lowercased text appears **inside a child's description** —
   which is neither the grouping nor a coverage relation: it passes on an accidental word match and
   fails on a child that addresses the component under any other wording. It is a placeholder with a
   check-shaped surface. The honest option space is either the real object (components as first-class
   records, factors assigned to them, coverage declared by mapping rather than guessed from prose) or
   a demotion of CHECK-5 to what it can decide. Either way it is a design decision, not a repair.
   **Not started.**

15. **Inv-4 (Obligation-Symmetry) has no code object.** Six of the seven invariants are enforced or
   machine-checked: Inv-1 (revision = re-ASSIGN), Inv-2 (binarity), Inv-3 (FAIL carries criteria),
   Inv-5 (finiteness), Inv-6 (determinism), Inv-7 (stable id + append-only log). Inv-4 — "Issuer and
   Executor are equally accountable to the protocol" — appears in no module, and unlike the others it
   names no single transition to guard: it is a property OF the rule set (both roles are bound, both
   are timed, both are logged), so what it would take is a **meta-check over the FSM tables** — e.g.
   that every state's admissible set gives each role a move, that the timeout applies regardless of
   who is waited on, and that no verb is exempt from the log. That is exactly the shape of
   `FsmCanon.lean`'s per-edge enumeration, and it is where it should live rather than as a runtime
   assertion. **Not started; named so the invariant list is not read as uniformly enforced.**

**Two boundaries the E3 measurement walked into, delineated rather than patched (2026-08-16).**

* **A vacuous Level-2 pass.** The gate reported `semantic_covered: true` over `criteria_judged: 0`
  — truthfully, since the node it was judging carried no criteria at all. The hole is closed on the
  structural side (CHECK-1 now fails a node that has children and no criteria of its own: by A1 an
  empty criteria set makes the node unjudgeable, not covered), but the CHECKER itself still cannot
  tell "nothing to judge" from "nothing to report". Kept as a boundary because the fix belongs to
  the checker's own contract, which is a measured artefact — its wording is calibrated (§13.6) and
  changing it silently would confound the next reading of C1.

* **`ESCALATED` as the exit of the exhausted rework loop.** §14.3 routes it there and §26.9(b) says
  plainly that the retry bound is fixed by fiat and pinned by no failure mode — an infinite adequate
  family. So "the counter ran out" and "the executor says the contract is wrong" (CHALLENGE) settle
  in the same terminal, and the resolution of an escalation lives OUTSIDE the FSM, with the issuer.
  The measurement arm deliberately carries no issuer policy: inventing one would cement a free
  design cell into the thing being measured. The bound itself is now what the canon says it is — a
  term of the CONTRACT, carried on the ASSIGN of each node, defaulting to 3 so that an unattended
  loop cannot retry all night unseen.

**Named abstraction (not a drift): the R′ reopen edge is not in the Lean automaton.** `fsm.py`
admits a gated re-ASSIGN out of DONE/ABANDONED (§14.3 R′) whose guard is a GRAPH predicate
(finality of consumption ∧ reopens < max_reopens) — outside the per-node signature this file
models. Lean holds the terminal-absorbing base automaton (which R′ preserves in the limit —
max_reopens exhausts); the reopen edge is TLC-checked at the system level (`formal/tla/FsmSpike.tla`)
and its graph gate is code-tested (`tests/test_reopen.py`).

## Layout

`GFSO/Postulates.lean` is the closure: the named tiers (0–7b), every postulate, and how each is
carried. Start there.
