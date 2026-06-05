# GFSO — Falsifiability Register

> Systematic pass over every load-bearing claim in the canon (`applied_gfso_v3.md`):
> for each, **what observation or counterexample would falsify it**. This is the
> deliverable the canon's §18 / README referenced; before this file only spot
> falsifiers existed inline.
>
> **Companion, not a replacement.** Claims live in the canon; this register annotates
> them with their falsifier. On any disagreement, the canon wins and this file is fixed.

---

## How to read this

Every GFSO claim is falsifiable. The register classifies the **type** of falsifier —
not whether one exists. A claim with *no* falsifier of any type is the only real defect,
and the pass flags such cases explicitly (§ "Flags", bottom).

| Type | Falsified by | Status of the claim |
|---|---|---|
| **E** — empirical | an observation in the world (incident, deployment datum, run) | a contingent prediction; can be wrong |
| **M** — mathematical | a counterexample to an enumeration / derivation | a theorem; "wrong" = the proof has a hole |
| **C** — conditional | a case satisfying the named premise yet violating the claim | a guarantee *under a stated discipline*; the premise is the empirical hook |

A **C**-claim is not a hedge: the premise is named and is itself testable. Saying "holds
under (ii)-faithfulness" is a strong conditional, and its violation is a *characterized*
in-framework failure (FM-3 / §18.1), not an external gap (canon §18.10, §19).

An **M**-claim is not "vacuous because definitional": a characterization theorem (e.g.
Theorem 1) is a real result; its falsifier is mathematical (break the case split), not
empirical. Conflating "analytic" with "empty" is the error the register is built to avoid.

Legend in the "Tested?" column: ✅ a falsification attempt was run and the claim survived ·
✅\* survived, but only under a named, still-movable classification line (not fully independent of
what it validates) · ◻ falsifiable but not yet tested · — analytic (M), no empirical test applies.

---

## Part I — Foundations (§2–§4)

### A1, A2 (axioms, §2.1)
- **Claim.** A domain's directed activity admits a finite set of decidable pass/fail
  predicates (A1); some goals exceed single-agent capacity and require decomposition (A2).
- **Type.** E — but as a **domain-membership** claim, not a universal truth. GFSO does not
  assert A1∧A2 hold everywhere; it asserts that *where* they hold, the protocol follows.
- **Falsifier.** A domain that **satisfies A1∧A2 yet is not describable as GFSO handoffs**
  (would falsify the "necessarily describes" claim of CORE/§2.1). Conversely, a domain
  asserted in-scope that in fact has no decidable criteria even in principle (¬A1) belongs
  *outside* — misclassifying it is a boundary error, not a falsifier of the axioms.
- **Boundary claim (§2.1).** GFSO applies **⟺** A1∧A2 hold (the iff that P-2 below sharpens).
  Falsifier: a domain governed successfully by GFSO handoffs where A1 or A2 demonstrably fails,
  or an A1∧A2 domain GFSO cannot describe.
- **Tested?** ◻ partially — E1's 216 incidents are all A1∧A2 domains and all map (§4.8
  empirical note); no in-scope case escaped the framework.

### Minimality of the basis {T, D, Dep, Del} (§2.4)
- **Claim.** Removing any one primitive loses a class of expressible HBP; each carries
  unique information; no 6th primitive irreducible to the basis exists.
- **Type.** M (constructive). **Uniqueness is explicitly open (§18.9)** — only minimality
  (necessity of each element) is claimed proven.
- **Falsifier.** (a) An HBP fully expressible after deleting one of the four → that element
  not necessary. (b) A primitive irreducible to {T,D,Dep,Del}, derivable from A1∧A2 →
  basis incomplete — the live one, exactly §18.9's open uniqueness question.
- **Tested?** — analytic; the constructive counterexample table (§2.4) is the proof. No
  6th primitive found to date (search, not proof).

### Basis completeness / axiom-exhaustion (§2.4 «Полнота»)
- **Claim.** Both axioms are exhausted by the basis (A1→T,V; A2→D,Del; T+D→Dep); standard
  organizational concepts (resources, time, risks, statuses) are expressible through it; no
  6th primitive *derivable from A1∧A2 and irreducible to the basis* exists. (Distinct from
  §18.9 *uniqueness* — here it is exhaustion/coverage of the axioms.)
- **Type.** E/M — a coverage claim over the (informal) space of organizational primitives;
  the canon itself notes a strict proof would need that space defined (open), so this is a
  search-backed claim, not a closed theorem.
- **Falsifier.** A canonical org-concept that is **both** (a) genuinely inexpressible via
  {T,D,Dep,Del,V} **and** (b) forced by A1∧A2 — a real gap, not a relabeling of an existing
  primitive. (A concept expressible after re-encoding is not a falsifier.)
- **Tested?** ◻ — corroborated only by the §2.4 reduction table; no adversarial search for a
  missing primitive has been run.

### |L| = 2 — binary validation (§3.2)
- **Claim.** Under (1) |A|=2, (2) act surjective, (3) act injective, the validation scale
  has exactly two values.
- **Type.** M (pigeonhole). Premise (3) injectivity is **forced** by decision-relevance
  (§3.4), not assumed; premise (1) |A|=2 is an **architectural** choice (granularity pushed
  to the tree / FSM retry-state), argued by attribution-purity, not pure logic (§3.2, v3.4).
- **Falsifier.** A **decision-relevant** validation outcome that maps to neither `intervene`
  nor `¬intervene` and cannot be relocated into tree-granularity or FSM-state — i.e. a third
  action on a single node that genuinely changes the trajectory in a way the binary split
  cannot encode. (A merely *informational* third value is not a falsifier — §3.4: surplus is
  decision-irrelevant by Blackwell.)
- **Tested?** — analytic. The architectural premise |A|=2 is where an objector would push;
  the register records it as a *named premise*, not a proven necessity.

### Theorem 1 — compositionality V(parent)=AND(V(children)) (§3.1)
- **Claim.** For a **correct** decomposition (joint sufficiency + non-redundancy),
  V(parent)=pass ⟺ all children pass.
- **Type.** M — a **characterization** (the two conditions are *exactly* iff-compositionality
  holds). The theorem is analytic given correctness.
- **Falsifier (mathematical).** A correct decomposition (both conditions met) where the
  equivalence fails — excluded by the proof; finding one means the proof is wrong.
- **Empirical content lives elsewhere.** The contingent question is *whether a real
  decomposition is correct* — i.e. whether joint-sufficiency holds against the world's true
  composition S. That is **not** Theorem 1; it is the §18.1 / Level-2 boundary, falsified by a
  backward signal (children pass, parent undelivered). The canon's §18.10 anatomy gives **two
  distinct falsification signatures**, which fault different claims:
  - **forgotten glue-criterion → FM-1** (a coverage hole; the false PASS is a *consequence*,
    not FM-3 — there is nothing to lie about). Faults decomposition **form**.
  - **existing-but-insensitive integration criterion → FM-3 false-PASS.** Faults value
    **truth** (the criterion exists but doesn't discriminate divergence from S).
- **Tested?** — (theorem) analytic; (correctness-in-practice) ◻ E3 territory.

### Theorem 2 — AND uniqueness (§3.3)
- **Claim.** On {0,1}, under commutativity+associativity+absorbing-0+non-triviality, AND is
  the unique aggregation.
- **Type.** M (exhaustive enumeration of 16 operations).
- **Falsifier.** A second operation satisfying all four constraints → enumeration erred.
- **Tested?** — analytic.

### Informativeness — decision-relevant completeness (§3.4, Утв.1–2)
- **Claim.** Binary V over a decomposition captures **all decision-relevant** information; a
  continuous scale carries strictly more (Blackwell) but the surplus is decision-irrelevant
  (0.73-pass and 1.0-pass both ⟶ ¬intervene). This is what licenses |L|=2 against the
  "continuous is richer" objection.
- **Type.** C — conditional on the §3.4 decision model (validation exists to decide
  intervene/¬intervene; granularity lives in the tree, not the scale).
- **Falsifier.** A **decision-relevant** bit inside the continuous surplus — a case where the
  magnitude (not just pass/fail) of a single node's score changes the intervene/¬intervene
  action *without* that distinction being relocatable into tree-granularity or FSM-state. That
  would show binary V drops decision-relevant information.
- **Tested?** ◻ — analytic under the model; no empirical probe that surplus is ever
  decision-relevant on real tasks.

### 7 Failure Modes — completeness as a basis (§4.4, §4.8)
- **Claim.** Any failure of compositional validation violates ≥1 of FM-1..7 (covering);
  the seven are independent (each isolable, §4.5); one real failure may violate several
  (basis, **not** partition).
- **Type.** **M (analytic), modulo a thin residue.** Both the case-split *and* the covering
  Axiom 1 are **derived** (§4.8: Axiom 1 is "выведенный покрывающий принцип, не постулат" — a
  decidable predicate over a result = content × temporal-position, exhausting the unit). So
  7-FM completeness is analytic given A1∧A2; it is **not** a standalone empirical posit. The
  only residue is thin and local (value/time partition for trace-predicates; + Axiom-2
  single-clock).
- **Falsifier (mathematical).** A failure the case split does not route to any Cᵢ → the split,
  or the §4.8 derivation of Axiom 1, has a hole. This is an *analytic* falsifier (find the
  hole), not an empirical posit about the world.
- **Empirical content is only *synthetic adequacy* (Axiom-1 entry).** The single thing E1
  exercises: do **real** failures instantiate the *derived* categories with no remainder? That
  is corroboration of the derivation's adequacy-to-phenomena (Kantian: categories a priori,
  their fit to experience synthetic) — not a test of structural validity. See next entry.
- **Tested?** — analytic; the adequacy corroboration (E1 0/216) is logged on Axiom 1.

### FM independence (§4.5)
- **Claim.** No FM is derivable from the others; each has an isolated realizing scenario.
- **Type.** M (constructive — the §4.5 scenario table) with E corroboration.
- **Falsifier.** An FMᵢ that cannot occur without some FMⱼ (always co-occurs **necessarily**, not
  just frequently) → not independent; the basis dimension is < 7. Independence is *isolability*,
  established by the §4.5 constructive scenario table (each FM realized alone) — a **M** claim.
- **Tested?** — analytic (the §4.5 scenarios are the witnesses). E1's 117/216 secondary-FM rate
  is **orthogonal** to independence (co-occurrence neither confirms nor threatens isolability);
  it is evidence for *basis-not-partition* (logged under FM-completeness), **not** for
  independence. No ✅ here — there is no falsification attempt specific to isolability.

### §4.8 Axiom 1 (Evaluation Completeness — "no third axis") — *derived; E1 corroborates its adequacy*
- **Claim.** A computation is fully characterized by denotational (function: domain/values/
  rule) ⊕ operational (execution-in-time) semantics; there is no independent third axis.
- **Type.** **M — a *derived* covering principle, not a postulate** (§4.8: a decidable predicate
  over a result = content × temporal-position, exhausting the unit; cross-task relations are Dep,
  not a third axis). Thin local residue: the value/time partition for predicates on the execution
  *trace* itself (edge of the definition) + Axiom-2 single-clock. So this is **not** the "flagship
  empirical claim" an earlier draft called it — it is analytic-with-a-residue, and what E1 touches
  is its *adequacy to phenomena*, not its validity.
- **Falsifier (M).** A real in-scope failure that is **neither** a defect of what-is-computed
  **nor** of when/how-it-executes — a third evaluative degree of freedom of a single result,
  surfacing as a genuine **8th FM** (not §2.1-extraordinary, not §16.2-adversarial, not a
  resilience-success). One such incident would mean the §4.8 derivation has a hole (the two axes
  do not exhaust the unit) — an analytic defect exposed empirically (synthetic-adequacy failure).
- **Tested?** ✅\* **E1: 0/216 incidents need an 8th FM** — corroborates the *adequacy* of the
  derived basis to real failures (✅\* = survived, but under the movable line below — see legend;
  and note it confirms a derivation, it does not test an empirical posit). Read precisely: this is
  the figure **after** the v3.1 root-cause
  re-triage of the 17 raw NONE (EVIDENCE_LOG §9.1), which moved 11→FM (mostly FM-1.b), leaving
  **6 non-FM cases** = 3 resilience-worked (= evidence-FOR) + 3 delegated-to-third-party. The 3
  delegated are **in-framework either way**: NEGLECTED (no FM) under the *declared* reading,
  FM-1 (missing NEGLECTED entry) under the *undeclared* reading — never an 8th mode (EVIDENCE_LOG
  §9.1 final positioning). Headline numbers: **true out-of-scope residual = 3, §2.1 boundary = 0**
  (after ovh-001 = datacenter fire → FM-1.b: fire-suppression + geo-redundancy are standard
  mitigations). **The load-bearing, partly-subjective step is that re-triage:** the
  falsifier "a genuine 8th mode" is only as sharp as the **FM-1.b ↔ §2.1 line (STD-2 entry above /
  Flag 4)** — since that line is judgement-drawn, a hard candidate can be absorbed into FM-1.b ("a
  foreseeable mitigation was missing", as the canon does for ovh-001 = datacenter fire), and the
  re-triage that produced 0/216 itself *uses* that absorption rule (so the test is not fully
  independent of the classification it validates). This ✅\* is *corroboration under a movable
  line*, not an unconditional survived falsification. Strongest empirical *corroboration* in the
  canon (of a derived structure's adequacy, not of an empirical posit), with that caveat named.

### §4.8 Axiom 2 (single logical evaluation event / single clock) — two halves
- **Claim.** Validation of t is one logical event with one local clock ⟹ operational
  trichotomy (before/during/after) is total; AND the FSM **composes** several such events
  (DELIVER→VALIDATING→FAIL→REWORK→DELIVER), each covered.
- **(i) Single-clock scope.** Type **C** — explicit named cost. Under concurrent time (Lamport
  happens-before, no global clock) the trichotomy weakens. Falsifier: not a falsifier of GFSO
  but a **scope boundary** — a distributed-validation setting with no single-clock ordering
  shows where Axiom 2 stops. Routed to **E3**. Tested? ◻ — boundary, not yet probed.
- **(ii) FSM-composes-events.** Type **M.** Falsifier: an **in-scope** re-entrant validation
  (a real DELIVER→FAIL→REWORK cycle, single clock) that the per-event atomicity does **not**
  cover — i.e. a validation episode the FSM cannot decompose into covered events. That breaks
  the composition half *inside scope*, independently of the distributed boundary. Tested? —
  analytic (the §6.3 FSM cycle is the constructive witness).

### §5.4 — three levels of verifiability are exhaustive ("no 4th dimension")
- **Claim.** Knowledge about a decomposition-as-sign-expression is exhausted by syntax /
  semantics / pragmatics (Morris 1938) → CHECK levels 0/1/2; no fourth dimension (structurally
  parallel to §4.2 "no 4th function component" and §4.8 Axiom-1 "no third axis").
- **Type.** **M — a derived covering claim, same family as Axiom 1** (which is itself derived,
  not a postulate, §4.8). Modulo the same kind of thin residue as Axiom 1.
- **Falsifier (M).** A real verifiability question about a decomposition that is **none** of
  structural (L0) / formal-implication (L1) / causal-pragmatic (L2) — a fourth kind of check →
  the Morris trichotomy / its application here has a hole.
- **Tested?** — analytic; **adequacy** corroborated by the same E1 evidence as Axiom 1 (a
  fourth-level defect would surface as an uncovered failure; none did), not a posit-test.

### STD-2 — predictability admissibility (§5.2, §5.5) — *the FM-1.b ↔ §2.1 hinge*
- **Claim.** Non-coverage is licensed *only* if the event is genuinely extraordinary
  (no-precedent **AND** not derivable); otherwise a foreseeable-but-missing mitigation is a
  decomposition defect (FM-1.b). The canon is explicit (§5.5) that STD-2 is **not** a coverage
  standard but the *admissibility criterion* deciding **whether** a non-coverage is FM-1.b or a
  §2.1 boundary — so it carries falsifiable content that does **not** reduce to any FM entry. This
  is the line the Axiom-1 adequacy ✅\* and Flag 4 both hang on; it is registered here as a
  first-class claim, not absorbed.
- **Type.** E/C — operationalized (§5.2 v3.4) as the domain-precedent / faithfulness test: a
  missing mitigation is FM-1.b iff a *faithful K̂* for the domain would have carried it (precedent
  / industry standard / what competent peers did).
- **Falsifier.** An incident where the domain-precedent test classifies a missing mitigation as
  **FM-1.b** yet **no** faithful K̂ could have carried it (truly no S-regularity to be faithful to)
  — or the converse (genuinely extraordinary by the test, yet a standard mitigation existed). Either
  shows the predictability burden-of-proof line is mis-drawn.
- **Tested?** ◻ — and **only as sharp as the precedent threshold (Flag 4)**, which is currently
  judgement-drawn; this is exactly why the Axiom-1 ✅ is corroboration-under-a-movable-line. The
  burden-of-proof shift itself (predictability presumed; impossibility must be proven, §5.2) is the
  structural content; the *threshold* is the open empirical residue.

### STD-4 / CHECK-7–8 — formal sufficiency & consistency instruments (§5.4)
- **Claim.** At Level 1, CHECK-7 (⋀criteria(children) ⊨ cᵢ) and CHECK-8 (children's criteria
  mutually satisfiable) are decidable instruments that catch **FM-1.d** (insufficient entailment,
  e.g. 150+150 > 200 — invisible to CHECK-1 topological coverage) and the formal half of **FM-2**.
  Registered separately because CHECK-7 is the **sole** operational test of FM-1.d (it does *not*
  reduce to another entry — unlike STD-1/3).
- **Type.** M-constructive (the §5.4 complexity table is the witness; decidable for simple
  criteria, co-NP/SMT in general).
- **Falsifier.** A decomposition that CHECK-7 **mis-adjudicates** — passes an under-entailing split
  (children formally fail to entail cᵢ yet CHECK-7 says ⊨) or rejects a sound one; or a CHECK-8 that
  certifies mutually-unsatisfiable children criteria as consistent. Either breaks the instrument's
  soundness.
- **Tested?** — analytic (decision procedures); ◻ no empirical run of CHECK-7/8 against a corpus of
  real decompositions (E3-adjacent — no decomposition has been GFSO-checked end-to-end yet).

---

## Part I.5 — Protocol, graph, AI-layer (§6–§7)

### Protocol minimality — 12 signals, 10 states, 6 invariants (§6.2, §6.4)
- **Claim.** Removing any one P2P signal produces a defect (FM, FSM-deadlock, IC, or
  operational); the §6.2 table assigns each deletion a unique consequence. 12 is the minimum.
- **Type.** M (constructive — the deletion table).
- **Falsifier.** A P2P signal whose removal causes **no** defect of any of the four kinds (its
  function is covered by the remaining signals) → the set is not minimal. Symmetrically, a
  necessary signalling need with **no** signal addressing it → not complete.
- **Uniqueness is OPEN (§18.9).** Minimality (no signal removable) is claimed; **uniqueness**
  (any protocol addressing the 7 FM under the §6.4 invariants is ≅ the GFSO FSM) is **not** —
  explicitly open. Type M, untested. Falsifier of the *open* question: a non-isomorphic protocol
  meeting the same spec (would settle it negatively). Mirrors the basis minimality-vs-uniqueness
  split (§2.4 / §18.9).
- **Tested?** — analytic (minimality); uniqueness ◻ open (§18.9).

### Q minimality & independence — 5 metrics ↔ 5 primitives (§7.2)
- **Claim.** The five q-metrics are in bijection with the five primitives; removing any opens
  a named blind zone; none is expressible from the others (distinct graph inputs).
- **Type.** M (constructive — the blind-zone + independence tables).
- **Falsifier.** A q-metric reconstructible from the other four (not independent), or a
  primitive-level defect class that **no** q-metric detects (a sixth blind zone) → the
  bijection/minimality fails.
- **Tested?** — analytic; ◻ the *predictive* value of each q vs real outcomes is open (§16.5).

### AI-layer capacity necessity — Simon t\* (§7.3.1)
- **Claim.** Information I(α,t) accumulates; human cognitive capacity is finite (Simon 1955);
  hence ∃ t\* beyond which |I| exceeds any human's capacity, making an AI-layer **necessary**
  to keep Утв.6's guarantees from going vacuous. **This is the *capacity* necessity — distinct
  from §18.10's *provenance* necessity** (§7.3.7); the register lists both, they are separate.
- **Type.** E (contingent on real organizations actually crossing t\*).
- **Falsifier.** A non-trivial organization whose accumulated decision-relevant information
  stays permanently within unaided human capacity (no t\* is ever reached) → the capacity
  argument is moot for that class. (Note: this falsifies the *necessity-in-practice*, not the
  conditional "if |I| exceeds capacity then AI needed", which is near-analytic.)
- **Tested?** ◻ — no measurement of |I| growth vs human capacity on a real deployment.

### §7.3.6 — safety-net incompleteness (irreducible domain-silent false-PASS)
- **Claim.** The apparatus catches LLM errors with a **formal signature** (bad D → q_D; bad
  semantic check → CHALLENGE), but a domain-incorrect yet formally-clean D (FM-3 false-PASS) is
  **not** caught — the operational face of the §18.1 boundary, removable only by execution. This
  is a *negative* claim (the safety-net is NOT complete) and is the canon's most-cited limitation.
- **Type.** M/structural — it *reduces* to the FM-3 / §18.1 / Theorem-1-correctness entries
  (registered above); listed explicitly because the canon leans on it constantly (§7.3.6, §16.3,
  §18.1, §18.10).
- **Falsifier.** A purely-formal apparatus (no execution, no agent contact) that **does** detect a
  domain-silent false-PASS → contradicts §18.10 Lemma 1 (S not derivable from the formal half).
- **Tested?** — analytic (same status as the §18.10 derivation it follows from); the q_V
  false-FAIL instrument gap (Flag 1) is the nearest empirical edge.

## Part II — Main results (§8–§14)

> **Shared caveat — the (ii)-faithfulness proxy is dormant (applies to every claim tagged
> ⟨ii-dormant⟩ below).** Several results below are guaranteed *under (ii)-faithfulness
> discipline* (criteria track reality — canon §18.10, §16.3). That discipline has **no
> operational outcome-independent proxy yet** (same gap as §18.10 P-1/P-3 and Flag 4). So a
> decline can always be re-attributed to a faithfulness break (FM-3, in-framework), and the
> claim's empirical falsifier **cannot currently fire** — it is non-adjudicable until a proxy
> instrument exists, *identically* to P-1/P-3. This caveat is propagated uniformly: a
> (ii)-conditioned §8–§14 claim is no more testable than the §18.10 predictions.

### Утв.3 — Blackwell information dominance (§8.2)
- **Claim.** For α₂>α₁, the GFSO experiment Blackwell-dominates the lower-adherence one;
  any rational agent with any utility does weakly better.
- **Type.** C — conditional on the **named premise** "informal channels invariant to α"
  (protocol does not forbid calling). Given the premise, the garbling kernel makes dominance
  analytic (M); the "weakly better for *any* utility" corollary rests on the Blackwell-
  **equivalence** direction (Marschak & Miyasawa 1968, cited §10.1), not on garbling alone.
- **Falsifier.** A setting where adopting protocol signals **degrades** a rational agent's
  decision quality — which, given Blackwell, can only happen if the protocol *removes/poisons*
  informal information (premise violated). So the real empirical target is the premise:
  *find a deployment where introducing GFSO suppresses the informal channels it sits on.*
- **Tested?** ◻ — needs deployment data (§18.5).

### Утв.4 — constraint improvement (§9)
- **Claim.** When Δ>c, protocol constraints raise expected payoff for any P(θ_bad)>c/Δ.
- **Type.** C — conditional on Δ>c (cost of failure > cost of compliance), named at §16.6.
- **Falsifier.** A setting with Δ>c where mandatory criteria/NEGLECTED/immutability strictly
  *lower* expected payoff → the dominated-strategy argument fails.
- **Tested?** ◻ — E0e (+34pp) is *adjacent* corroboration (explicit criteria help), not a
  direct test of the constraint-payoff inequality.

### Следствие 5 — α-monotonicity (§10.1)
- **Claim.** E[u|I(α)] non-decreasing in α; no adoption threshold below which protocol harms.
- **Type.** C (direct corollary of Утв.3; inherits its §8.2 premise — informal channels
  invariant to α — *not* the (ii)-proxy; so this one is adjudicable in principle). *Why exempt
  from ⟨ii-dormant⟩ while Утв.6 is not:* Сл.5 ranges over α at **fixed information content** (a
  Blackwell-garbling fact about how much protocol is on), whereas Утв.6 asserts new signals are
  **informative-not-noise** over time — which is exactly clause-(ii). Different premise, hence
  different dormancy.
- **Falsifier.** A rational agent and utility for which more adherence strictly lowers
  expected utility (a "valley" in α) without violating the §8.2 premise.
- **Tested?** ◻ — adjudicable via deployment (premise is observable), unlike the ⟨ii-dormant⟩
  claims.

### Утв.6 — temporal monotonicity (§10.2) ⟨ii-dormant⟩
- **Claim.** At fixed α, information grows with time; signals are observations, not noise.
- **Type.** C — **under (ii)-faithfulness discipline** (canon §18.10: "signals are not noise"
  is exactly the clause-(ii) requirement that criteria track reality).
- **Falsifier.** A GFSO system where accumulated protocol history makes decisions *worse* over
  time **while criteria faithfully track reality** (discipline held). If decline traces to a
  faithfulness break, that is FM-3 / §18.1 (in-framework), not a falsifier of Утв.6.
- **Tested?** ◻ — long-horizon (§18.5), **and non-adjudicable until the (ii)-proxy exists**
  (shared caveat above): without an outcome-independent faithfulness measure, any decline is
  re-attributable to FM-3, so this falsifier shares P-1/P-3's dormancy, not a plain "awaiting
  deployment".

### Утв.7 — scale bounds, ‖eₙ‖ ≤ (L·γ)ⁿ‖e₀‖ (§10.3)
- **Claim.** Validation damps error multiplicatively down a feedforward hierarchy; L·γ<1 ⟹
  exponential suppression.
- **Type.** C — under three **named model assumptions** (§10.3: uniform L, linear operators,
  feedforward/no-adaptation). Worst-case upper bound.
- **Falsifier.** A validated hierarchy where error grows faster than (L·γ)ⁿ **with the three
  assumptions holding** → the operator-composition bound is wrong. (Heterogeneous/adaptive
  hierarchies are out of the assumption set, not falsifiers.)
- **Tested?** ◻ — needs L,γ proxy measurement (§18.8). *(Note: canon §18.10 groups Утв.7 /
  §12-Mech.2 loosely under (ii)-faithfulness; here the γ<1 hook is the **observable §18.8
  measurement** of validator gain — adjudicable independently of the criteria-faithfulness proxy —
  so these are C-on-model-assumptions, **not** ⟨ii-dormant⟩. The dependency is still disclosed via
  "with the three assumptions holding".)*

### §10.3 corollaries + small-gain stability (Сл.1–3, Zames 1966)
- **Claim.** Sparse validation needs γ≤L^{−k} at every k-th level (Сл.1); cascaded validators
  compose γ(V₂∘V₁)=γ₁·γ₂ (Сл.2); net benefit Lⁿ−(L·γ)ⁿ grows superlinearly vs linear cost
  (Сл.3); the upward CHALLENGE/BLOCK channel is BIBO-stable when gain↑·gain↓<1 (small-gain).
  The small-gain stability is **re-used** by §18.10's backward-attribution.
- **Type.** M (operator-norm algebra + Zames small-gain theorem), inheriting Утв.7's three model
  assumptions (so C on those).
- **Falsifier.** A validated cascade where composed damping exceeds γ₁·γ₂ (sub-multiplicativity
  violated), or a CHALLENGE/BLOCK loop that diverges (infinite challenge-override spiral) **with**
  gain↑·gain↓<1 → the small-gain bound is wrong, and §18.10's attribution-stability loses its prop.
- **Tested?** ◻ — same L,γ measurement gap (§18.8); the spiral-stability is the concrete
  observable (does a real correction loop converge?).

### Утв.9 — decomposition quality, 4 independent mechanisms (§12)
- **Claim.** GFSO improves decomposition via 4 mechanisms (information enrichment, validator
  composition, space restriction, feedback), each provably operative, **independent** (failure of
  one doesn't void the others).
- **Type.** Mixed. Mech.2 (composition) + Mech.3 (constraint restriction) = M (inherit Сл.2 /
  Утв.4). Mech.1 (enrichment) + Mech.4 (feedback) = C ⟨ii-dormant⟩ — they require the enriched
  information / recorded defects to *faithfully track reality*, the same (ii)-proxy.
- **Falsifier.** A mechanism reducible to another (independence fails); or a setting where Mech.2/3
  (the M ones) fail to improve decomposition with their premises held; or — for Mech.1/4 — a case
  of richer-history-yet-worse-decomposition **with faithfulness held** (non-adjudicable until the
  (ii)-proxy exists, shared caveat).
- **Tested?** ◻ — E0e (+34pp) is adjacent corroboration of the constraint mechanism only.

### Утв.8 — Bayesian incentive compatibility (§11) + §11.1 IC-minimality
- **Claim.** When cost(undetected defect) > cost(signal), honest use of each signal maximizes
  expected payoff for any P(defect)>0. §11.1: removing any one IC-critical feature makes
  honesty cease to dominate for a specific agent.
- **Non-adversarial sub-domain.** Type **M/C-constructive** (not "merely awaiting deployment"):
  §11 gives a per-signal payoff argument and §11.1 a **complete 9-feature enumeration**, each
  with its named dishonest behavior. On the non-adversarial domain (under the two §11 cost
  conditions) the claim is established by dominated-strategy elimination, not pending data.
  Falsifier: a signal in the §11.1 table whose removal leaves honesty still dominant (the
  enumeration over-counts), or a non-adversarial agent with cost(defect)>cost(signal) for whom
  dishonesty pays.
- **Adversarial domain.** Type **E, genuinely open.** Collusion/gaming/criteria-lowballing is
  explicitly out of scope (§16.2); the formal threat model is §18.3. IC is **not** claimed here.
- **Tested?** — (non-adversarial) analytic via §11.1; ◻ (adversarial) blocked on §18.3.

### Теорема 10 — self-measuring (§13)
- **Claim.** Every Q component is computable from the execution trace with no extra data
  collection.
- **Type.** M (constructive — each q is a graph query, §13).
- **Falsifier.** A Q component that cannot be computed from G alone (needs out-of-band data)
  → self-measuring breaks. **Note a known half-gap:** q_V currently counts only false-PASS;
  the false-FAIL counter (FM-3 is two-sided, §4.2) is **not built** (owner: §7.2 / §16.5).
  This is an *instrument* incompleteness, not a falsifier of Theorem 10's computability claim
  (§13 is untouched), but it is the nearest thing to one and is logged as a flag below.
- **Tested?** — analytic (constructive: the queries run on G); ◻ predictive calibration of Q
  vs real outcomes is open (§16.5, §18.2).

### Теорема 11 — structural transparency (§14)
- **Claim.** Under protocol compliance, every decision has a record R(d).
- **Type.** M (from invariants §6.4).
- **Falsifier.** A protocol-compliant decision with no audit record → an invariant is not
  doing what's claimed.
- **Tested?** — analytic (follows from immutability + mandatory fields).

### §15 — three-pillar indispensability / feedback loop
- **Claim.** Protocol + self-measuring + AI-layer form a monotone feedback loop; removing any one
  pillar makes *GFSO-channel* improvement impossible (canon §7.3.5 / §15; Abstract, §19).
- **Type.** C — the "no improvement" is scoped to the GFSO channel; informal channels (§8.2) may
  still yield residual Q (the v3.4 fix to §7.3.5: "no GFSO channel", not literal Q=const).
- **Falsifier.** A deployment where Q improves **through the GFSO channel** with a pillar removed —
  e.g. q-metrics rise with no AI-layer and no informal substitute, or adherence rises with
  self-measuring off. (Improvement via informal channels is not a falsifier — it is the named
  scope.)
- **Tested?** ◻ — needs an ablation deployment; never run.

---

## Part III — Positioning (§17) and theory-model (§18.10)

### §17.1 — adaptive stratification by horizon
- **Claim.** CHALLENGE frequency strictly increases with decomposition depth.
- **Type.** C — **explicitly conditional on the stationarity premise** (step 4: environment
  drift-rate independent of level), named in-canon as an empirical posit, not derived.
- **Falsifier.** A GFSO system with Dep-coherence **and** a stationary environment where deep
  (short-horizon) tasks do **not** CHALLENGE more often than shallow ones. (Non-stationary
  environments are outside the premise.)
- **Tested?** ◻ — needs CHALLENGE-frequency-by-depth data from a deployment.

### §17.2 — Scrum ⊂ GFSO
- **Claim (structural, the only one made).** Every Scrum primitive maps to a GFSO primitive /
  implementation-choice / restriction; no Scrum element escapes. **The behavioral derivation
  (GFSO *generates* Scrum's exploratory dynamics) is explicitly NOT claimed — open frontier.**
- **Type.** E (structural-embedding claim, testable case-by-case).
- **Falsifier.** A Scrum element (a ceremony, role, artifact, rule) with **no** GFSO
  mapping — an unmapped primitive.
- **Tested?** ◻ corroborated — **E1 Track B: 0 unmapped elements across 12 in-scope Scrum cases**
  (14 total, 2 ruled out-of-scope: NUMMI/Zappos). But this was a **presence-only** mapping
  (EVIDENCE_LOG §9 finding 5), not an adversarial hunt for an unmapped ceremony/rule — so it
  corroborates rather than survives a real falsification attempt; ✅ withheld until a deliberate
  search for an escaping Scrum element is run. The behavioral claim, being unmade, has nothing to
  falsify yet (and must not be smuggled in as if proven).

### §18.1 — causal-correctness boundary (the structural anchor)
- **Claim.** Level-2 causal correctness — that a real decomposition's children criteria *in the
  world* entail the parent's — is a **characterized boundary**, not an "open algorithm": it is
  not derivable from A1+A2 (the formal half cannot supply S) and not closable by declaration (a
  declaration is itself a decomposition whose correctness is a new instance — regress, Lemma 3).
  Every C-claim below and every §18.10 prediction ultimately reduces to this boundary; it is the
  canon's most-cited limitation (§3.1, §16.3, §18.1, §7.3.6).
- **Type.** **M** for the *non-reducibility* (it is the §18.10 Lemma-1 + Lemma-3 result: S ∉
  language{A1,A2}; declaration regresses). **E** for the *located* manifestation — the boundary
  is crossed only by execution, surfacing as a backward signal.
- **Falsifier.** (M side) A method that certifies real causal correctness from the formal half
  **alone** (no execution, no agent contact) → breaks Lemma 1. (E side) the backward signal:
  all children pass yet the parent is undelivered in the world → the decomposition was causally
  wrong; attributed to the node owning the broken composition claim (FM-1.d / FM-1.b, §18.10).
- **Tested?** — (M) analytic; (E) ◻ E3 territory (multi-agent decomposition with per-child V).
  This is the boundary the §4.8 Axiom-1 ✅\* sits *inside*: completeness-as-basis holds, but the
  *correctness* of any given decomposition against S is exactly what the apparatus does not
  certify.

### §18.10 — theory-model: agent necessity (the derivation)
- **Claim.** The agent (carrier of empirically-learned domain content K̂) is a **necessary**
  structural link — the apparatus cannot supply domain-correctness (Lemma 1), declaration
  cannot ground it (Lemma 3), luck is unstable, so empirical contact is necessary.
- **Type.** M — a derivation (excluded-middle P3 + Lemmas 1,3 + luck-elimination). The thin
  local residue is the "luck is unstable" step, argued from S's contingency.
- **Falsifier (mathematical).** Exhibit reliable domain-correct decomposition with **no**
  empirical contact — pure formal derivation of S (contradicts Lemma 1) or grounded
  declaration (contradicts Lemma 3) or *stable* luck (contradicts S-contingency). Any one
  breaks the derivation.
- **Tested?** — analytic; corroborated by pre-theoretic success being explained, not assumed.

### §18.10 — prediction P-1: agent substitutability
- **Claim.** Two agents are interchangeable **relative to an outcome-independent faithfulness
  proxy** (equal faithfulness ⟹ equal validated results).
- **Type.** E.
- **Falsifier.** Two agents with **equal** faithfulness-proxy (measured independently of
  outcome) yielding **systematically different** validated outcomes — or equal outcomes from
  unequal faithfulness. The outcome-independence of the proxy is what makes this non-circular
  (canon flags: a proxy defined via success would make it untestable).
- **Tested?** ◻ — **falsifier well-formed but DORMANT.** The canon (§18.10, §7.3.7, §5.2) gives
  no operational outcome-independent faithfulness proxy yet (nearest candidate = §5.2
  domain-precedent, itself judgement-drawn — Flag 4). Non-circular in form, non-operational in
  fact — same status as Flag 1's missing counter. The E2 probe is a target, not readiness:
  it is blocked until a proxy instrument is built.

### §18.10 — prediction P-2: applicability boundary
- **Claim.** Structural success-content present ⟺ GFSO applicable (sharpens §2.1).
- **Type.** E.
- **Falsifier.** A domain with no structural success-content where GFSO nevertheless governs
  handoffs successfully, or vice versa.
- **Tested?** ◻ — **partially dormant, same proxy as P-1/P-3.** "Structural success-content
  present" is judged by the §18.10 structural-half apparatus; insofar as that detection leans on
  faithfulness, P-2 inherits the same non-adjudicability. The *one* half that is plausibly
  outcome-independent — "does a structural validation half exist at all?" (an architectural fact,
  observable like Simon-t\* capacity) — is testable; the "success-content" half is not, until the
  proxy exists. So P-2 is split: structural-presence side ◻-adjudicable, success-content side
  ⟨ii-dormant⟩. The asymmetry with P-1/P-3 is thus only partial and is now stated, not assumed.

### §18.10 — prediction P-3: global falsifier (the model's own neck)
- **Claim.** Sustained out-of-distribution success with **neither** a structural half **nor**
  learned faithfulness is **impossible**.
- **Type.** E — the deliberately-stated global falsifier.
- **Falsifier.** Exactly that: a system that **reliably** succeeds OOD while (a) carrying no
  structural validation half and (b) having demonstrably-low faithfulness **measured
  independently of the success itself**. The independence clause is load-bearing: without it
  any counterexample is re-explained post-hoc, and the claim would be circular (canon §18.10
  fixes this explicitly).
- **Tested?** ◻ — no such system observed; the claim is an open standing bet. Note the same
  dormancy as P-1: refuting it requires faithfulness "measured independently of success", and
  no such instrument exists yet — so the bet is well-posed but not currently adjudicable.

---

## Flags — claims whose falsifier is weak, missing, or instrument-limited

These are **not** hedges. Each is a precise statement of where the empirical hook is thin,
to be strengthened (named premise / built instrument), never softened.

1. **q_V false-FAIL counter not built (§16.5, Theorem 10).** FM-3 is two-sided since v3.3,
   but the self-measuring instrument only counts false-PASS. Until the false-FAIL counter
   exists, the *over-rejection* half of FM-3 is asserted-but-not-measured. **Action: build the
   counter** (code, not theory) — then Theorem 10's coverage matches FM-3's two-sidedness.
2. **|A|=2 architectural premise (§3.2).** The whole |L|=2 result rests on |A|=2, which is a
   *choice* (granularity → tree/FSM), argued by attribution-purity, not forced. Honest premise,
   not a gap — but the single place an objector lands. Kept named, not dissolved.
3. **Axiom-2 single-clock (§4.8).** Operational trichotomy is total only under one clock;
   distributed validation weakens it. Routed to E3 as a scope boundary, not closed.
4. **FM-1.b ↔ §2.1 boundary subjectivity (§5.2).** The "was a foreseeable mitigation missing?"
   line is operationalized (faithfulness / domain-precedent) but the precedent threshold is
   still drawn by judgement. A principled, less-subjective criterion is an open refinement
   (does not block E1; logged).
5. **C-claims awaiting deployment (Утв.3,4,6,7,8; §17.1).** Every conditional guarantee above
   is currently corroborated only mechanically/adjacently; none has a direct deployment test.
   The premises are all named; the empirical hooks are real but unrun (E2/E3/§18.5).

**Scope of this register.** It covers the load-bearing claims of §2–§5 (axioms, basis
minimality+completeness, |L|=2, Theorems 1–2, 7-FM completeness + independence, §4.8 Axioms 1–2,
§5.4 level-exhaustiveness), §6–§7 (protocol minimality, Q minimality, Simon capacity-necessity),
§8–§14 (Утв.3–9, §10.3 corollaries + small-gain, Theorems 10–11, §15 indispensability), §17
(stratification, Scrum embedding), and §18.10 (agent derivation + predictions P-1/P-2/P-3). Of the
claims **enumerated here**, none has zero falsifier of any type — every entry is E, M, or C, and
the flags above are thin empirical hooks, not vacuous claims.

This is a completeness statement **scoped to the enumerated set**, not a proof that the canon
contains no unfalsifiable claim anywhere. **Deliberate omissions** (judged non-load-bearing or
expository, not silently dropped): §3.4 informativeness *commentary* beyond Утв.1–2 (the
methodological framing); §15-style restatements in Abstract/§19; §17.3 comparison table; the
related-work mappings §17; STD-1, STD-3 as *prescriptions* (each guards FM-1, operationalizing
joint-sufficiency — STD↔FM is canon §5.5, so their falsifiers reduce to the FM-1 entry). **STD-2
and STD-4 are exceptions and ARE registered** (Part I): STD-2 is the admissibility line (§5.5: not
coverage), and STD-4/CHECK-7–8 is the sole instrument for FM-1.d — neither reduces to another entry. If a reader finds a load-bearing claim outside
this set, the register is *incomplete*, not *wrong* — add it.

---

## Provenance

The systematic falsifiability pass referenced by canon §18; ships with canon v3.5. On any
canon ↔ register disagreement, the canon is authoritative and this file is corrected.
