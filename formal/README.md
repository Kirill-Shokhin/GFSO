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
| **Hypothesis-form** (3 groups) | act-surjectivity + act-injectivity (the \|L\|=2 defense) · no-declaration + no-luck (agent necessity: Lemma 2 regress, luck-instability) · `SingleClock` / CA2 (§12.8, discharged) | premises in the *signature* of `L_forced_two`, `agent_necessary`, `op_trichotomy_of_total` |
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
| Inv-7 the record is the LOG; state = fold(log) | 14.4/22 | ✔ | `Metrics.replay_append`, `.log_append_only` |
| Thm 10 self-measuring Q (constructive core) | 21 | ✔ | `Metrics.Q_self_measuring` |
| Q index set: 5 metrics ↔ 5 components | 15.2 | ◐ structural (enums defined to match) | `Metrics.metrics_components_bijection` |
| Thm 11 structural transparency | 22 | ✔ | `Metrics.replay_append` |
| Ordinal severity ⪰_dom (preorder on nodes · partial · antisymmetric on probe-sets · count-independent) | 6.3 | ✔ axiom-free — reflexivity/transitivity/antisymmetry **universal** (by induction), partiality and count-independence by witness, with a finite carrier + negative control | `Grading.dom_refl_all`, `.dom_trans_all`, `.dom_antisymm_all`; `.dom_partial`, `.dom_count_independent`, `.dom_not_constant_true` |
| 5 constitutive links (3 ⊕ 2) | 4 | ⚠ §4 axiom; the 3⊕2 count axiom-free | `Links.*` |
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

*(Two are LIVE divergences of the ENGINE from the canon, each an engineer obligation: **#3**, where the
code has an edge the canon denies, and **#1**, where the code has a row the canon exempts. The rest are
settled by the canon and kept because the Lean encoding is where they show.)*

1. **IDLE has no timeout — the canon's position; the ENGINE currently disagrees (LIVE, engineer obligation).**
   `gfso/core/protocol/fsm.py` carries an `(IDLE, TIMEOUT)` row, added by the engineering pass under the
   **v3.9** reading in which Inv-5 was TOTAL over non-terminals. The v4.0 canon exempts IDLE **by name**,
   so that row is now against the canon and must be removed — the second obligation beside #3. This file
   and `Fsm.lean` encode the canon, so at this row they are AHEAD of the engine (the opposite direction
   from #3, where they are behind it). The reasoning, unchanged:
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
3. **`(VALIDATING, FAIL, iteration ≥ max) → DONE(fail)` — the code has an edge the canon denies.**
   `Fsm.step VALIDATING FAIL false = DONE` mirrors `fsm.py:163`, and `docs/architecture.md` documents
   the same row. The canon does not carry it: §14.3 routes the exhausted rework loop to **ESCALATED**
   ("the FAIL↔REWORKING loop bounded by max_iterations", with escalation as its exit), and §12.2
   states as fact that **"DONE is reached through acceptance (PASS ∨ auto_pass), never through fail
   (Chapter 14)"**. This is not a naming lag — it is the FSM's shape. It is also **load-bearing**:
   "DONE ⇐ acceptance" is the stated premise of false-FAIL guarantee-safety, which is what licenses
   q_V's one-sidedness (§12.2, §15.2, §24.5) — a DONE reachable through fail would make a false-FAIL
   able to fabricate a terminal acceptance, which is exactly what the canon argues cannot happen.
   **Resolution (derived from the canon, not a doc-status call): the code's row must become
   `→ ESCALATED`.** Four independent canon facts converge on it, none of them "the doc says so":
   (1) the canon has **no** terminal for "V = fail, settled" — its negative terminals are ABANDONED
   (V = ⊥, cancelled) and ESCALATED (attention); DONE(fail) invents a category the canon deliberately
   omits. (2) Exhausting the retry loop IS the escalation trigger by the protocol's purpose (§1.1:
   "trust, but see" — automatic handling failed ⟹ the third mode, attention); marking it DONE
   buries a failure as "completed", the exact anti-pattern GFSO exists to prevent. (3) DONE is
   consumed under R′ (§14.3: a Dep consumer reads-and-builds on the result) — a DONE(fail) would let a
   neighbor build on a failure. (4) The honest state of a parent with an unresolvable child is V = ⊥
   (attention needed), which ESCALATED gives and DONE(fail) wrongly bypasses by auto-computing AND →
   fail. (§12.2's guarantee is NOT the load-bearing reason — it survives either way, since DONE(fail)
   carries V = fail and never enters q_V; the reason is 1–4.) Engineer's action: change `fsm.py`'s
   `(VALIDATING, FAIL, iteration ≥ max)` target from DONE(fail) to ESCALATED (terminal, not
   quasi-terminal — recovery is a human re-issue/revise, not a reopen). Flagged, not patched here:
   this file does not edit `fsm.py`, and the Lean mirror keeps encoding what the code does today so
   the gap stays visible until the engine changes.
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

**Named abstraction (not a drift): the R′ reopen edge is not in the Lean automaton.** `fsm.py`
admits a gated re-ASSIGN out of DONE/ABANDONED (§14.3 R′) whose guard is a GRAPH predicate
(finality of consumption ∧ reopens < max_reopens) — outside the per-node signature this file
models. Lean holds the terminal-absorbing base automaton (which R′ preserves in the limit —
max_reopens exhausts); the reopen edge is TLC-checked at the system level (`formal/tla/FsmSpike.tla`)
and its graph gate is code-tested (`tests/test_reopen.py`).

## Layout

`GFSO/Postulates.lean` is the closure: the named tiers (0–7b), every postulate, and how each is
carried. Start there.
