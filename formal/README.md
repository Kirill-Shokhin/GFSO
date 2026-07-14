# GFSO formal core — machine-checked in Lean 4

Machine-checked formalization of the **formal spine** of the GFSO canon
(`../docs/applied_gfso_v3.md`), in Lean 4. **No mathlib** (Lean core only), **no `sorry`**, **no
`native_decide`** — and the assumption set of this encoding is not asserted, it is **enforced by CI**.

## The result, stated honestly

This is **an audit of GFSO's axiomatic surface**, machine-checked: which of the canon's claims are
definitional, which are irreducible postulates, and how many. It is *not* a proof of GFSO's
substantive claims. Ranked by how much each is worth:

1. **The assumptions of this encoding are enumerated and enforced.** Every "why exactly N?" is
   either *definition-unfolding* (the kernel checks it) or a *covering principle* ("there is no third
   kind", over an undelimited space). Type theory forces the latter into an `axiom` — **but only once
   you decide where to put it.** That decision is the encoder's, and this development contains its own
   counterexample: `|A| = 2` ("there is no third action") is a covering principle in substance, yet it
   is encoded as a two-constructor inductive and so never appears in `#print axioms`, while Axiom 1
   ("there is no third evaluation axis") — the same shape — is an explicit axiom.
   **So "three" is a fact about this encoding, not about GFSO.** What is encoding-invariant: the
   covering principles are finitely many, and here is one honest enumeration with every placement
   disclosed. The guard then makes *that* enumeration an invariant the engine defends.
2. **Axiom 2 is discharged: the operational axis is clock-free.** Coverage of a three-cell operational
   classification needs *no assumption at all* (`phases_exhaustive`), and the partition needs only
   asymmetry — which every strict order has. The phase COUNT never depended on the clock, so
   single_clock is carried as a *hypothesis* (`SingleClock`), not an axiom, and is gone from
   `#print axioms`. **The cost is real but is not a covering axiom:** what totality buys is exactly the
   **reading of the middle cell** — it collapses "causally concurrent" to "equal", letting the phase be
   read as *during* the evaluation interval rather than *incomparable with* it
   (`total_collapses_concurrent`, itself axiom-free once totality is a hypothesis). That reading is a
   genuine thing totality buys — it is simply not a postulate about the *count*, so it is not listed as
   a covering axiom (§4.8). The remaining canon clauses of Axiom 2 — per-event atomicity and
   re-entrant validation — are protocol *dynamics* (a clean verdict), a separate object from the
   taxonomy, untouched here. `GFSO/Time.lean`.
3. **The spine compiles.** T1 and its converse, |L|=2, T2 (16-op enumeration), the 4+3 FM geometry
   and its 7 independence witnesses, FSM determinism/finiteness/handshake, the 5/4/2/1 signal count,
   `state = fold(log)`. Correct and faithful — and elementary. The value is the *map*, not the depth.
4. **The guard map is machine-checked.** No CHECK lives at Level 2; **FM-3 and FM-6 are guarded by no
   structural check at all**. The canon states both in passing (§5.4, §5.5); here they are decided
   off the table rather than asserted.

**What is assumed, not proved.** 7-FM completeness, the Morris trichotomy, and the completeness of
the five links are **axioms**. The Lean theorems around them (`fm_basis_covers`,
`knowledge_gap_located`, `missing_link_located`) add only a classical De Morgan localization — they
machine-check the *step from the axiom*, not the axiom. What *is* axiom-free around them: the 4+3
geometry, the 7 witnesses, the 3⊕2 count.

**Read the "honest reading" docstrings.** Three results are true but forced by the modelling choice,
not derived: `lemma1_S_underdetermined` (SOLITUDE's *form*; `S` is a free field and the apparatus is
*defined* S-free), `basis_independent` (a 4-tuple of free bits has four independent coordinates),
`metrics_components_bijection` (two 5-element enums defined to match). Each says so in place.

**What this is not.** Not a proof that GFSO is correct, complete, or empirically valid. Not a
formalization of the classical results it imports (P3–P9). Not a proof that the basis is minimal in
§2.4's semantic sense, nor that Лемма 1 holds for a rich apparatus. The empirical boundary is not
closed — it is *localized*, into one uninterpreted predicate.

## Scope: what "three" is and is not

Three is the number of covering axioms **this encoding chose to make explicit**, within the formalized
fragment. A different faithful encoding moves the line (make `|A|=2` an axiom and it is four). The full picture:

| Kind | Items | Where it lives |
|---|---|---|
| **Covering axioms** (3) | Axiom 1 (§4.8) · Morris (§5.4) · directed-action completeness (§18.10.1) | `axiom` — visible in `#print axioms` |
| **Definitional** (3) | A1, A2 (§2.1), \|A\|=2 | baked into the *types* (`Verdict := Bool`, `Decomp`, `Act`) |
| **Hypothesis-form** (3) | Лемма 3 (declaration regress), luck-instability, single_clock / Axiom 2 (§4.8, discharged by D3) | premises in the *signature* of `agent_necessary`, `op_trichotomy_of_total` |
| **Out of scope** | P3–P9 (Blackwell, Simon, Hurwicz, cascade) | imported classical results; need ℝ/probability = mathlib |

A *definitional* postulate cannot be a Lean axiom without being vacuous: prose says "there is no
third action", the type says "you declared two". A *hypothesis* is dischargeable in principle and is
visible in the theorem's type; an *axiom* is not. Conflating the two is a mistake — `L_forced_two` is
**axiom-free** even though it has premises.

## Coverage — every canon result, accounted for

`✔` machine-checked · `⚠` machine-checked *modulo a named axiom* · `◐` true but **forced by the
modelling choice** (the shape is formalized, the canon's semantic content is not) · `○` out of scope.

| Canon result | § | Status | Where |
|---|---|---|---|
| T1 compositionality (+ its converse) | 3.1 | ✔ | `Compositionality.T1`, `.T1_characterization` |
| \|L\| ≠ 2 impossibility | 3.2 | ✔ axiom-free | `Binarity.L_forced_two` |
| T2 uniqueness of AND | 3.3 | ✔ | `AndUniqueness.and_unique` |
| 7-FM completeness | 4.4/4.8 | ⚠ Axiom 1 | `FailureModes.seven_fm_complete` |
| 7-FM independence (7 witnesses), 4+3 geometry | 4.5/4.6 | ✔ axiom-free | `FailureModes.*` |
| Operational trichotomy | 4.3/4.8 | ✔ axiom-free (Axiom 2 discharged to a hypothesis, §4.8) | `Time.*` |
| Minimality of basis (independence half) | 2.4 | ◐ structural (free-coordinate model) | `Ontology.basis_independent` |
| Uniqueness of basis | 18.9 | ○ open — space of primitives not delimited | — |
| 3 verification levels | 5.4 | ⚠ Morris | `Standards.knowledge_gap_located` |
| CHECK↔FM guard map; Level-2 & FM-3/FM-6 unguarded | 5.4/5.5 | ✔ axiom-free (canon states both in passing) | `Standards.*` |
| Signal defect distribution (12 = 5/4/2/1) | 6.2 | ◐ `decide` over a hand-entered table, not a minimality proof | `Protocol.defect_distribution` |
| Инв-5 finiteness | 6.4 | ✔ (total — IDLE row added per canon) | `Fsm.timeout_terminates` |
| Инв-6 determinism | 6.4 | ✔ | `Fsm.step_deterministic`, `.step_iff_admissible` |
| Инв-1 revision = re-ASSIGN, not cancel | 6.4 | ✔ | `Fsm.reassign_to_review` |
| Cancellation handshake completes | 6.3 | ✔ | `Fsm.cancel_handshake_terminates` |
| Инв-2 binarity of V | 6.4 | ✔ definitional | `Ontology.Verdict := Bool` |
| Инв-3 FAIL ⇒ failed_criteria ≠ ∅ | 6.4 | ○ payload-level, not a state-machine property | — |
| Инв-4 symmetry of obligations | 6.4 | ○ normative, not a state-machine property | — |
| Инв-7 the record is the LOG; state = fold(log) | 6.4/14 | ✔ | `Metrics.replay_append`, `.log_append_only` |
| T10 self-measuring Q (constructive core) | 13 | ✔ | `Metrics.Q_self_measuring` |
| Q index set: 5 metrics ↔ 5 components | 7.2 | ◐ structural (enums defined to match) | `Metrics.metrics_components_bijection` |
| T11 structural transparency | 14 | ✔ | `Metrics.replay_append` |
| 5 constitutive links (3 ⊕ 2) | 18.10.1 | ⚠ §18.10.1 axiom; the 3⊕2 count axiom-free | `Links.*` |
| Лемма 1 (SOLITUDE) — its logical form | 18.10 | ◐ definitional (apparatus is *defined* S-free) | `TheoryModel.lemma1_S_underdetermined` |
| …its consequence: no `FormalView → S` exists | 18.10 | ✔ axiom-free | `TheoryModel.no_apparatus_yields_S` |
| Agent necessity D1–D6 | 18.10 | ✔ elimination (Л.3 + luck are premises) | `TheoryModel.agent_necessary` |
| Лемма 3, luck-instability | 18.10 | hypothesis-form | signature of `agent_necessary` |
| P3 Blackwell dominance | 8 | ○ needs ℝ/information structures — imported (Blackwell 1953) | — |
| P4 constraint improvement | 11 | ○ imported (Simon 1955) | — |
| C5 α-monotonicity, P6 temporal monotonicity | 10 | ○ corollaries of P3 — imported | — |
| P7 cascade ‖eₙ‖ ≤ (L·γ)ⁿ‖e₀‖ | 10.3 | ○ needs ℝ / operator norms | — |
| P8 Bayesian IC | 11 | ○ needs a payoff model — imported (Hurwicz 1960) | — |
| P9 decomposition quality | 12 | ○ composite of P3/P4/P6/P7 | — |
| Level-2 faithfulness (the residue) | 18.1 | permanent boundary — *localized*, not closed | `correct` left uninterpreted |

If a canon result is missing from this table, the table is wrong. That is what makes "complete" falsifiable.

## Build and verify

```sh
export PATH="$HOME/scoop/persist/elan/.elan/bin:$PATH"   # elan via scoop (Windows)
cd formal
lake build                        # ~1–2 min cold, instant warm. No mathlib.
bash scripts/check_closure.sh     # no `sorry`; postulate set == AXIOMS.whitelist
bash scripts/check_refs.sh        # every §-citation still exists in the canon
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

CI runs both guards on every change to `formal/` **and to the canon**.

## Code ↔ canon divergences — both flags RESOLVED (canon is truth)

1. **IDLE timeout — the missing row was in `fsm.py`, added.** IDLE is a non-terminal state (§6.3)
   and Инв-5 asks every non-terminal to time out; the canon's exception list (BLOCKED, CANCELLING,
   VALIDATING) does not include IDLE ⟹ IDLE ─timeout→ TIMEOUT. `fsm.py` now carries the row
   (operationally a node is observable in IDLE only as a crash orphan — creation persisted but the
   SET_STATE→REVIEW of the same effect list did not land; the row is exactly its escape hatch).
   Инв-5 theorems are now TOTAL over non-terminals — the `s ≠ IDLE` hypotheses are gone;
   `Fsm.idle_times_out` records the closed flag with the opposite sign.
2. **IDLE + CANCEL → CANCELLING is canon-conformant, not a divergence.** §6.3's universal CANCEL
   reads "любое нетерминальное" — IDLE included. The edge is vacuous on the happy path (a node
   leaves IDLE within the ASSIGN transition that creates it) and REACHABLE exactly for the same
   crash-orphan IDLE node, where it is the issuer's cleanup path. Encoded faithfully, kept.

**Named abstraction (not a drift): the R′ reopen edge is not in the Lean automaton.** fsm.py
admits a gated re-ASSIGN out of DONE/CANCELLED (§6.3 R′) whose guard is a GRAPH predicate
(finality of consumption ∧ reopens < max_reopens) — outside the per-node signature this file
models. Lean holds the terminal-absorbing base automaton (which R′ preserves in the limit —
max_reopens exhausts); the reopen edge is TLC-checked at the system level (`formal/tla/FsmSpike`)
and its graph gate is code-tested (`tests/test_reopen.py`).

## Layout

`GFSO/Postulates.lean` is the closure: the named tiers (0–7b), every postulate, and how each is
carried. Start there.
