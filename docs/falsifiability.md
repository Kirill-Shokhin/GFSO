# GFSO — Falsifiability Register

> Systematic pass over every load-bearing claim in the canon (`applied_gfso_v4_en.md`):
> for each, **what observation or counterexample would falsify it**. This is the register the
> canon's §26 and the README refer to.
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
in-framework failure (FM-3 / §8), not an external gap (canon §2–§3, §28).

An **M**-claim is not "vacuous because definitional": a characterization theorem (e.g.
Theorem 1) is a real result; its falsifier is mathematical (break the case split), not
empirical. Conflating "analytic" with "empty" is the error the register is built to avoid.

Legend in the "Tested?" column: ✅ a falsification attempt was run and the claim survived ·
✅\* survived, but only under a named, still-movable classification line (not fully independent of
what it validates) · ◻ falsifiable but not yet tested · — analytic (M), no empirical test applies.

**What this register is.** An **anti-vacuity ledger**: for every load-bearing claim it names the
would-be refuter, and flags any claim that has none. That is the surviving core of falsifiability —
the *prohibition* requirement (a claim compatible with every outcome is empty) — **not** a criterion
demarcating science from non-science, an office this register never holds (canon §6.3). The E/M/C
typing extends the requirement past Popper's *empirical* scope — admitting a mathematical refuter (M)
and a premise-conditional claim (C), while holding the premise itself to the same requirement — which
**names and costs** the immunizing use rather than barring it: where a premise's own falsifier is
dormant (the (ii)-faithfulness flag), the requirement is declared, not enforced.

---

## Part I — The apparatus: axioms, basis, validation, failure modes (§9–§12)

> *(This register's own Part numbering, not the canon's. In v4 these chapters are the canon's
> **Part II — The Apparatus as Consequence**; the foundation it follows from is §2–§8, registered
> in this file's Part III below.)*

### A1, A2 (axioms, §9)
- **Claim.** A domain's directed activity admits a finite set of decidable pass/fail
  predicates (A1); some goals exceed single-agent capacity and require decomposition (A2).
- **Type.** E — but as a **domain-membership** claim, not a universal truth. GFSO does not
  assert A1∧A2 hold everywhere; it asserts that *where* they hold, the protocol follows.
- **Falsifier.** A domain that **satisfies A1∧A2 yet is not describable as GFSO handoffs**
  (would falsify the "necessarily describes" claim of CORE/§9). Conversely, a domain
  asserted in-scope that in fact has no decidable criteria even in principle (¬A1) belongs
  *outside* — misclassifying it is a boundary error, not a falsifier of the axioms.
- **Boundary claim (§9).** GFSO applies **⟺** A1∧A2 hold (the iff that Pred-2 below sharpens).
  Falsifier: a domain governed successfully by GFSO handoffs where A1 or A2 demonstrably fails,
  or an A1∧A2 domain GFSO cannot describe.
- **Tested?** ◻ partially — E1's 216 incidents are all A1∧A2 domains and all map (§12.8
  empirical note); no in-scope case escaped the framework.

### Minimality of the basis {T, D, Dep, Del} (§10.2)
- **Claim.** Removing any one primitive loses a class of expressible HVP; each carries
  unique information; no 6th primitive irreducible to the basis exists.
- **Type.** M (constructive). **Uniqueness is explicitly open (§26.9)** — only minimality
  (necessity of each element) is claimed proven.
- **Falsifier.** (a) An HVP fully expressible after deleting one of the four → that element
  not necessary. (b) A primitive irreducible to {T,D,Dep,Del}, derivable from A1∧A2 →
  basis incomplete — the live one, exactly §26.9's open uniqueness question.
- **Tested?** — analytic; the constructive counterexample table (§10.2) is the proof. No
  6th primitive found to date (search, not proof).

### Basis completeness / axiom-exhaustion (§10.2 "Completeness (a claim)")
- **Claim.** Both axioms are exhausted by the basis (A1→T,V; A2→D,Del; T+D→Dep); standard
  organizational concepts (resources, time, risks, statuses) are expressible through it; no
  6th primitive *derivable from A1∧A2 and irreducible to the basis* exists. (Distinct from
  §26.9 *uniqueness* — here it is exhaustion/coverage of the axioms.)
- **Type.** E/M — a coverage claim over the (informal) space of organizational primitives;
  the canon itself notes a strict proof would need that space defined (open), so this is a
  search-backed claim, not a closed theorem.
- **Falsifier.** A canonical org-concept that is **both** (a) genuinely inexpressible via
  {T,D,Dep,Del,V} **and** (b) forced by A1∧A2 — a real gap, not a relabeling of an existing
  primitive. (A concept expressible after re-encoding is not a falsifier.)
- **Tested?** ◻ — corroborated only by the §10.2 reduction table; no adversarial search for a
  missing primitive has been run.

### |L| = 2 — binary validation (§11.2)
- **Claim.** The validation scale has exactly two values. **Sourced in A1** (§11.2 "Source versus
  defense"): the criteria are decidable predicates cᵢ : Result → {pass, fail} and V(t) = ⋀ᵢ cᵢ — a
  conjunction of two-valued things is two-valued, with **no appeal to the action space**. The
  act-space argument — under (1) |Act|=2, (2) act surjective, (3) act injective, pigeonhole — is the
  **DEFENSE** against a graded scale, not the derivation.
- **Type.** M. The *source* rests on A1, the axiom the whole basis stands on. The *defense* rests on
  premise (1) |Act|=2, an **architectural** stipulation (granularity pushed to the tree / FSM
  retry-state), argued by attribution-purity, not pure logic; premise (3) injectivity is **forced**
  by decision-relevance (§11.2), not assumed. Moving the derivation onto A1 does not make |L|=2
  "derived from nothing" — it moves the load-bearing assumption from |Act|=2 to A1 and leaves
  |Act|=2 carrying only the defense.
- **Falsifier.** A **decision-relevant** validation outcome that maps to neither `intervene`
  nor `¬intervene` and cannot be relocated into tree-granularity or FSM-state — i.e. a third
  action on a single node that genuinely changes the trajectory in a way the binary split
  cannot encode. (A merely *informational* third value is not a falsifier — §11.4: surplus is
  decision-irrelevant by Blackwell.)
- **Tested?** — analytic. |Act|=2 is where an objector would push — but pushing there reaches the
  *defense* only; the scale itself would still stand on A1. The register records |Act|=2 as a *named
  premise*, not a proven necessity.

### Theorem 1 — compositionality V(parent)=AND(V(children)) (§11.1)
- **Claim.** For a **correct** decomposition (joint sufficiency + non-redundancy),
  V(parent)=pass ⟺ all children pass.
- **Type.** M — a **characterization** (the two conditions are *exactly* iff-compositionality
  holds). The theorem is analytic given correctness.
- **Falsifier (mathematical).** A correct decomposition (both conditions met) where the
  equivalence fails — excluded by the proof; finding one means the proof is wrong.
- **Empirical content lives elsewhere.** The contingent question is *whether a real
  decomposition is correct* — i.e. whether joint-sufficiency holds against the world's true
  composition S. That is **not** Theorem 1; it is the §8 / Level-2 boundary, falsified by a
  backward signal (children pass, parent undelivered). The canon's §3.4 anatomy gives **two
  distinct falsification signatures**, which fault different claims:
  - **forgotten glue-criterion → FM-1** (a coverage hole; the false PASS is a *consequence*,
    not FM-3 — there is nothing to lie about). Tagged **FM-1.f** (§12.2), Pragmatic level, no a-priori CHECK: it violates the *domain* face of the correspondence condition while the apparatus face passes, so by §7's coarse cut it sits on the FAITHFULNESS side, not FORM.
  - **existing-but-insensitive integration criterion → FM-3 false-PASS.** Faults value
    **truth** (the criterion exists but doesn't discriminate divergence from S).
- **Tested?** — (theorem) analytic; (correctness-in-practice) ◻ E3 territory.

### Theorem 2 — AND uniqueness (§11.3)
- **Claim.** On {0,1}, under commutativity+associativity+absorbing-0+non-triviality, AND is
  the unique aggregation.
- **Type.** M (exhaustive enumeration of 16 operations).
- **Falsifier.** A second operation satisfying all four constraints → enumeration erred.
- **Tested?** — analytic.

### Informativeness — decision-relevant completeness (§11.4, Inf-A / Inf-B)
- **Claim.** Binary V over a decomposition captures **all decision-relevant** information; a
  continuous scale carries strictly more (Blackwell) but the surplus is decision-irrelevant
  (0.73-pass and 1.0-pass both ⟶ ¬intervene). This is what licenses |L|=2 against the
  "continuous is richer" objection.
- **Type.** C — conditional on the §11.4 decision model (validation exists to decide
  intervene/¬intervene; granularity lives in the tree, not the scale).
- **Falsifier.** A **decision-relevant** bit inside the continuous surplus — a case where the
  magnitude (not just pass/fail) of a single node's score changes the intervene/¬intervene
  action *without* that distinction being relocatable into tree-granularity or FSM-state. That
  would show binary V drops decision-relevant information.
- **Tested?** ◻ — analytic under the model; no empirical probe that surplus is ever
  decision-relevant on real tasks.

### 7 Failure Modes — completeness as a basis (§12.4, §12.8)
- **Claim.** Any failure of compositional validation violates ≥1 of FM-1..7 (covering);
  the seven are independent (each isolable, §12.5); one real failure may violate several
  (basis, **not** partition).
- **Type.** **M (analytic), modulo a thin residue.** The case-split is **derived**; the covering
  CA1 is **argued** — §12.8: "an **argued** covering principle rather than a bare stipulation — the
  argument narrows the candidate space without delimiting it, which is exactly why it stays an axiom"
  (Ch. 27's (T)/(P) sort; a
  decidable predicate over a result = content × temporal-position, exhausting the unit). So
  7-FM completeness is analytic given A1∧A2; it is **not** a standalone empirical posit. The
  only residue is thin and local: the value/time partition for trace-predicates. (The single clock
  is **off** this residue — discharged, §12.8/§27: the phase count is axiom-free.)
- **Falsifier (mathematical).** A failure the case split does not route to any Cᵢ → the split,
  or the §12.8 derivation of CA1, has a hole. This is an *analytic* falsifier (find the
  hole), not an empirical posit about the world.
- **Empirical content is only *synthetic adequacy* (CA1 entry).** The single thing E1
  exercises: do **real** failures instantiate the *derived* categories with no remainder? That
  is corroboration of the derivation's adequacy-to-phenomena (Kantian: categories a priori,
  their fit to experience synthetic) — not a test of structural validity. See next entry.
- **Tested?** — analytic; the adequacy corroboration (E1 0/216) is logged on CA1.

### FM independence (§12.5)
- **Claim.** No FM is derivable from the others; each has an isolated realizing scenario.
- **Type.** M (constructive — the §12.5 scenario table) with E corroboration.
- **Falsifier.** An FMᵢ that cannot occur without some FMⱼ (always co-occurs **necessarily**, not
  just frequently) → not independent; the basis dimension is < 7. Independence is *isolability*,
  established by the §12.5 constructive scenario table (each FM realized alone) — a **M** claim.
- **Tested?** — analytic (the §12.5 scenarios are the witnesses). E1's 117/216 secondary-FM rate
  is **orthogonal** to independence (co-occurrence neither confirms nor threatens isolability);
  it is evidence for *basis-not-partition* (logged under FM-completeness), **not** for
  independence. No ✅ here — there is no falsification attempt specific to isolability.

### §12.8 CA1 (Evaluation Completeness — "no third axis") — *argued (hence still an axiom); E1 corroborates its adequacy*
- **Claim.** A computation is fully characterized by denotational (function: domain/values/
  rule) ⊕ operational (execution-in-time) semantics; there is no independent third axis.
- **Type.** **M — an *argued* covering principle, which is why it remains an axiom** (§12.8: a decidable predicate
  over a result = content × temporal-position, exhausting the unit; cross-task relations are Dep,
  not a third axis). Thin local residue: the value/time partition for predicates on the execution
  *trace* itself (edge of the definition); the single clock is **off** it (discharged, §12.8/§27).
  So this is **not** the "flagship
  empirical claim" an earlier draft called it — it is analytic-with-a-residue, and what E1 touches
  is its *adequacy to phenomena*, not its validity.
- **Falsifier (M).** A real in-scope failure that is **neither** a defect of what-is-computed
  **nor** of when/how-it-executes — a third evaluative degree of freedom of a single result,
  surfacing as a genuine **8th FM** (not §9-extraordinary, not §24.2-adversarial, not a
  resilience-success). One such incident would mean the §12.8 derivation has a hole (the two axes
  do not exhaust the unit) — an analytic defect exposed empirically (synthetic-adequacy failure).
- **Tested?** ✅\* **E1: 0/216 incidents need an 8th FM** — corroborates the *adequacy* of the
  derived basis to real failures (✅\* = survived, but under the movable line below — see legend;
  and note it confirms a derivation, it does not test an empirical posit). Read precisely: this is
  the figure **after** the v3.1 root-cause
  re-triage of the 17 raw NONE (EVIDENCE_LOG §9.1), which moved 11→FM (mostly FM-1.b), leaving
  **6 non-FM cases** = 3 resilience-worked (= evidence-FOR) + 3 delegated-to-third-party. The 3
  delegated are **in-framework either way**: ACCEPTED_RISKS (no FM) under the *declared* reading,
  FM-1 (missing ACCEPTED_RISKS entry) under the *undeclared* reading — never an 8th mode (EVIDENCE_LOG
  §9.1 final positioning). Headline numbers: **true out-of-scope residual = 3, §9 boundary = 0**
  (after ovh-001 = datacenter fire → FM-1.b: fire-suppression + geo-redundancy are standard
  mitigations). **The load-bearing, partly-subjective step is that re-triage:** the
  falsifier "a genuine 8th mode" is only as sharp as the **FM-1.b ↔ §9 line (STD-2 entry above /
  Flag 4)** — since that line is judgement-drawn, a hard candidate can be absorbed into FM-1.b ("a
  foreseeable mitigation was missing", as the canon does for ovh-001 = datacenter fire), and the
  re-triage that produced 0/216 itself *uses* that absorption rule (so the test is not fully
  independent of the classification it validates). This ✅\* is *corroboration under a movable
  line*, not an unconditional survived falsification. Strongest empirical *corroboration* in the
  canon (of a derived structure's adequacy, not of an empirical posit), with that caveat named.

### §12.8 CA2 (operational axis; single clock discharged) — two halves
- **Claim.** The three operational phases (before / concurrent / after an evaluation event) partition
  events by a strict **causal** order — no single clock is needed (§12.8/§27, CA2 discharged);
  AND the FSM **composes** several such events (DELIVER→VALIDATING→FAIL→REWORKING→DELIVER), each covered.
- **(i) Phase count is axiom-free.** Type **M** — `Time.phases_exhaustive` covers the three cells for
  an arbitrary relation; the partition needs only asymmetry (= a strict order). Under concurrent time
  (Lamport happens-before) the trichotomy does **not** weaken — it generalizes: the middle cell reads
  as "concurrent" and FM-5 becomes a read/write race. **Falsifier:** a real evaluation whose timing
  relative to `e` is none of {wholly-before, concurrent, wholly-after}. What remains outside the
  taxonomy is verdict *atomicity* (protocol dynamics, (ii) below), not axis completeness. *(Supersedes
  the earlier "single-clock scope = cost, routed to E3" framing; see Part III.10.)*
- **(ii) FSM-composes-events.** Type **M.** Falsifier: an **in-scope** re-entrant validation
  (a real DELIVER→FAIL→REWORKING cycle, single clock) that the per-event atomicity does **not**
  cover — i.e. a validation episode the FSM cannot decompose into covered events. That breaks
  the composition half *inside scope*, independently of the distributed boundary. Tested? —
  analytic (the §14.3 FSM cycle is the constructive witness).

### §13.4 — three levels of verifiability are exhaustive ("no 4th dimension")
- **Claim.** Knowledge about a decomposition-as-sign-expression is exhausted by syntax /
  semantics / pragmatics (Morris 1938) → CHECK levels 0/1/2; no fourth dimension (structurally
  parallel to §12.2 "no 4th function component" and §12.8 CA1 "no third axis").
- **Type.** **M — modulo the named covering axiom CA-Morris** (`morris_trichotomy`, §13.4; one of
  the canon's three Lean axioms, §1.4/§27). **Not** CA1's grade: §12.8 *argues* CA1 from the unit of analysis (the "no third
  axis — pinned" argument), whereas the trichotomy is **inherited from
  Morris 1938 by citation** — there is no preceding orthogonality-and-exhaustion theorem, which is
  the same reason §4.2 grades the representational branch below CA1. The axiom is named, not hidden.
- **Falsifier (M).** A real verifiability question about a decomposition that is **none** of
  structural (L0) / formal-implication (L1) / causal-pragmatic (L2) — a fourth kind of check →
  the Morris trichotomy / its application here has a hole.
- **Tested?** — analytic; **adequacy** corroborated by the same E1 evidence as CA1 (a
  fourth-level defect would surface as an uncovered failure; none did), not a posit-test.

### STD-2 — predictability admissibility (§13.2, §13.6) — *the FM-1.b ↔ §9 hinge*
- **Claim.** Non-coverage is licensed *only* if the event is genuinely extraordinary
  (no-precedent **AND** not derivable); otherwise a foreseeable-but-missing mitigation is a
  decomposition defect (FM-1.b). The canon is explicit (§13.6) that STD-2 is **not** a coverage
  standard but the *admissibility criterion* deciding **whether** a non-coverage is FM-1.b or a
  §9 boundary — so it carries falsifiable content that does **not** reduce to any FM entry. This
  is the line the CA1 adequacy ✅\* and Flag 4 both hang on; it is registered here as a
  first-class claim, not absorbed.
- **Type.** E/C — operationalized (§13.2 v3.4) as the domain-precedent / faithfulness test: a
  missing mitigation is FM-1.b iff a *faithful Ŝ* for the domain would have carried it (precedent
  / industry standard / what competent peers did).
- **Falsifier.** An incident where the domain-precedent test classifies a missing mitigation as
  **FM-1.b** yet **no** faithful Ŝ could have carried it (truly no S-regularity to be faithful to)
  — or the converse (genuinely extraordinary by the test, yet a standard mitigation existed). Either
  shows the predictability burden-of-proof line is mis-drawn.
- **Tested?** ◻ — and **only as sharp as the precedent threshold (Flag 4)**, which is currently
  judgement-drawn; this is exactly why the CA1 ✅ is corroboration-under-a-movable-line. The
  burden-of-proof shift itself (predictability presumed; impossibility must be proven, §13.2) is the
  structural content; the *threshold* is the open empirical residue.

### STD-4 / CHECK-7–8 — formal sufficiency & consistency instruments (§13.4)
- **Claim.** At Level 1, CHECK-7 (⋀criteria(children) ⊨ cᵢ) and CHECK-8 (children's criteria
  mutually satisfiable) are decidable instruments that catch **FM-1.d** (insufficient entailment,
  e.g. 150+150 > 200 — invisible to CHECK-1 topological coverage) and the formal half of **FM-2**.
  Registered separately because CHECK-7 is the **sole** operational test of FM-1.d (it does *not*
  reduce to another entry — unlike STD-1/3).
- **Type.** M-constructive (the §13.4 complexity table is the witness; decidable for simple
  criteria, co-NP/SMT in general).
- **Falsifier.** A decomposition that CHECK-7 **mis-adjudicates** — passes an under-entailing split
  (children formally fail to entail cᵢ yet CHECK-7 says ⊨) or rejects a sound one; or a CHECK-8 that
  certifies mutually-unsatisfiable children criteria as consistent. Either breaks the instrument's
  soundness.
- **Tested?** — analytic (decision procedures); ◻ no empirical run of CHECK-7/8 against a corpus of
  real decompositions. (E3-adjacent: decompositions HAVE now been GFSO-checked end-to-end on a
  third-party benchmark — EVIDENCE_LOG §13, calibration tier, and §13.6 measures the Level-2 gate's
  discrimination on PLANTED holes. Neither is the corpus run this row asks for.)

---

## Part I.5 — Protocol, graph, AI-layer (§14–§15)

### Protocol minimality — 12 signals, 12 states, 7 invariants (§14.2, §14.4)
- **Claim.** Removing any one P2P signal produces a defect (FM, FSM-deadlock, IC, or
  operational); the §14.2 table assigns each deletion a unique consequence. 12 is the minimum,
  splitting **4 FM / 4 FSM-deadlock / 3 IC / 1 operation** (`Protocol.defect_distribution`).
  **ACCEPT_CHALLENGE is IC, not FM-5** (corrected 2026-08-04): §14.3 admits ASSIGN from CHALLENGED
  and Inv-1 makes any contract change a re-ASSIGN, so removing the signal does **not** cost the
  spec update — the same argument by which REOPEN is "a named effect of re-ASSIGN, not a thirteenth
  signal". What only ACCEPT_CHALLENGE carries is the dispute's **positive closure**, the arm
  REJECT_CHALLENGE answers in the negative; 12 = the minimum is unaffected, the type is not.
- **Type.** M (constructive — the deletion table).
- **Falsifier of the split specifically.** A signal whose removal leaves a defect of a class other
  than the one the table assigns it — as ACCEPT_CHALLENGE itself did until this correction; the
  count is machine-checked, so a canon/Lean divergence is caught by `check_claims` (the split is
  read off §14.2's count line at every run).
- **Falsifier.** A P2P signal whose removal causes **no** defect of any of the four kinds (its
  function is covered by the remaining signals) → the set is not minimal. Symmetrically, a
  necessary signalling need with **no** signal addressing it → not complete.
- **Uniqueness is OPEN (§26.9(b)).** Minimality (no signal removable) is claimed; **uniqueness**
  (every adequate protocol **behaviourally equivalent** to the GFSO FSM) is **not** — explicitly
  open. The currency is behavioural equivalence, **not** bi-interpretation "≅": the latter, on
  finite structures, is vacuous here (every adequate protocol is rigid, so all are bi-interpretable
  and none distinguished — §26.9(b)). **Over BARE adequacy the question is settled NEGATIVELY:**
  the falsifier is exhibited — a protocol routing VALIDATING-timeout to ESCALATED instead of
  DONE(auto_pass) meets the identical deadlock-freedom + finiteness conditions yet differs behaviourally.
  Machine-checked (`FsmCanon.variant_*`): the shared finiteness, the settlement-distinctness, the
  edge-confinement; the variant's *full* adequacy is inherited from the canon's by a one-edge-perturbation
  argument (only an already-admissible timeout edge's destination changed). Adequacy pins exit
  *existence*, not the *destination* of a free timeout exit (a §14.2/§14.3/§24.7 design choice); `max_iterations`
  is a 2nd orthogonal free cell (an infinite adequate family; argued). What stays **open**: (b)-uniqueness over a
  *fully pinned design vector* (every free cell, not the timeout geometry alone — the invariants provably do NOT
  exhaust the `max_iterations` cell) — then the same wall as basis uniqueness, §26.9(a). **Inner enumeration
  (over the fixed alphabet — finite, distinct from the walled outer completeness):** each signal-destination
  cell is graded on strength (fatal, removal strands the target — `noAssign/noBlock/noChallenge/noCancel/nodeliver_strands_*`
  — vs sole/genuine-provider, target survives via a catch-all — `accept_sole_content_consent`,
  `{resolveBlock,rejectChallenge}_sole_content_*`, `noPass/noConfirm_*`) × function (channel / resolution — existence-forced,
  destination-free / genuineness); ACCEPT_CHALLENGE→OFFERED and re-ASSIGN→OFFERED are Inv-1-forced
  (`acceptChallenge_dest_inv1_forced`, `canon_reassign_to_offered`); CANCELLING is forced by IC not deadlock
  (`oneStepCancel_*`, deadlock-free without it). All are canon-*internal* necessary conditions (negative controls
  included); the over-all-protocols forcedness stays argued (the falsifier for *it* is still an adequate protocol
  dropping a skeleton state — open). **Asymmetric to (a):**
  minimality positive both sides; on uniqueness (a) is canonical over a natural Beth subclass, (b) over none (its
  determination hypothesis coincides with its conclusion — no Beth/Myhill–Nerode bridge). Type M. Mirrors the
  basis minimality-vs-uniqueness split (§10.2 / §26.9).
- **State irredundancy — measured (§14.3, `FsmCanon.lean`).** Over the base machine the twelve
  states carry **eleven** behaviour classes: EXECUTING ≡ REWORKING (an attribution label), and the
  eleven states other than REWORKING pairwise-distinct under the admissible-set-⊕-settlement-mode observable. Type M,
  machine-checked (axiom-free `decide`, with a negative control). Falsifier: two named states other
  than {EXECUTING, REWORKING} behaviourally equivalent over the Ch. 14.3 table. This is
  *irredundancy*, not state **completeness** ("no thirteenth state") — the latter retains its prior
  analytic status and is not touched by this measurement.
- **Tested?** — analytic (signal minimality); state irredundancy machine-checked; uniqueness ◻ open (§26.9(b)).

### Q minimality & independence — 5 metrics ↔ the 5 components of the tuple (§15.2)
- **Claim.** The five q-metrics are in bijection with the five components (T, D, Dep, Del, V — the basis is four primitives, V derived); removing any opens
  a named blind zone; none is expressible from the others (distinct graph inputs).
- **Type.** M (constructive — the blind-zone + independence tables).
- **Falsifier.** A q-metric reconstructible from the other four (not independent), or a
  primitive-level defect class that **no** q-metric detects (a sixth blind zone) → the
  bijection/minimality fails.
- **Tested?** — analytic; ◻ the *predictive* value of each q vs real outcomes is open (§24.5).

### AI-layer capacity necessity — Simon t\* (§15.3.1)
- **Claim.** Information I(α,t) accumulates; human cognitive capacity is finite (Simon 1955);
  hence ∃ t\* beyond which |I| exceeds any human's capacity, making an AI-layer **necessary**
  to keep Prop 6's guarantees from going vacuous. **This is the *capacity* necessity — distinct
  from §2–§3's *provenance* necessity** (§15.3.7); the register lists both, they are separate.
- **Type.** E (contingent on real organizations actually crossing t\*).
- **Falsifier.** A non-trivial organization whose accumulated decision-relevant information
  stays permanently within unaided human capacity (no t\* is ever reached) → the capacity
  argument is moot for that class. (Note: this falsifies the *necessity-in-practice*, not the
  conditional "if |I| exceeds capacity then AI needed", which is near-analytic.)
- **Tested?** ◻ — no measurement of |I| growth vs human capacity on a real deployment.

### §15.3.2 — Chollet Level ≥ 2: capability-class requirement on the LLM
- **Claim.** The LLM component must reach **Chollet Level ≥ 2** (broad-to-extreme generalization;
  Morris et al. General-Emerging+) to adapt to D_org ∉ D_train from context G. This is a **different
  capability class**, **not** buyable by enlarging D_train (developer-aware generalization, Chollet 2019).
- **Type.** E — an empirical requirement on the deployed model class.
- **Falsifier.** Either (a) a model demonstrably **below** Level 2 that nonetheless discharges the
  §15.3.2 role (reliable adaptation to a real org's D_org ∉ D_train) → the requirement is not
  load-bearing; or (b) evidence that scaling D_train **alone** lifts a model into the role → refutes
  "different class, not different volume".
- **Tested?** ◻ — not run as a GFSO deployment test; adjudicable against frontier models on
  out-of-distribution org task distributions. (Realization mechanism for the requirement = Xie et al.
  ICL-as-Bayesian, §15.3.2 — a *how*, not the falsifier of the *requirement*.)

### §15.3.2–§15.3.3 — AI-layer two-components + cross-impossibility (minimality)
- **Claim.** The AI layer has **exactly two** components (Solver + LLM), not three: a Solver supplies
  no domain induction; the LLM guarantees no P(formal-error)=0; neither subsumes the other
  (cross-impossibility); induction-in-isolation collapses to counting.
- **Type.** M — minimality/exhaustiveness, same family as protocol-minimality (§14) and Q-minimality (§15.2).
- **Falsifier.** A single component discharging **both** roles (formal-soundness guarantee AND domain
  generalization), or a necessary **third** component irreducible to the two → the 2-component
  enumeration erred.
- **Tested?** — analytic.

### §15.3.6 — safety-net incompleteness (irreducible domain-silent false-PASS)
- **Claim.** The apparatus catches LLM errors with a **formal signature** (bad D → q_D; bad
  semantic check → CHALLENGE), but a domain-incorrect yet formally-clean D (FM-3 false-PASS) is
  **not** caught — the operational face of the §8 boundary, removable only by execution. This
  is a *negative* claim (the safety-net is NOT complete) and is the canon's most-cited limitation.
- **Type.** M/structural — it *reduces* to the FM-3 / §8 / Theorem-1-correctness entries
  (registered above); listed explicitly because the canon leans on it constantly (§15.3.6, §24.3,
  §8, §2–§3).
- **Falsifier.** A purely-formal apparatus (no execution, no agent contact) that **does** detect a
  domain-silent false-PASS → contradicts §2–§3 Lemma 1 (S not derivable from the formal half).
- **Tested?** — analytic (same status as the §2–§3 derivation it follows from); the q_V
  false-FAIL aggregate (Flag 1, a diagnostic option) is the nearest empirical edge.

## Part II — Main results (§16–§22)

> **Shared caveat — the (ii)-faithfulness proxy is dormant (applies to every claim tagged
> ⟨ii-dormant⟩ below).** Several results below are guaranteed *under (ii)-faithfulness
> discipline* (criteria track reality — canon §2–§3, §24.3). That discipline has **no
> operational outcome-independent proxy yet** (same gap as §2–§3 Pred-1/Pred-3 and Flag 4). So a
> decline can always be re-attributed to a faithfulness break (FM-3, in-framework), and the
> claim's empirical falsifier **cannot currently fire** — it is non-adjudicable until a proxy
> instrument exists, *identically* to Pred-1/Pred-3. This caveat is propagated uniformly: a
> (ii)-conditioned §16–§22 claim is no more testable than the §2–§3 predictions.

### Prop 3 — Blackwell information dominance (§16.2)
- **Claim.** For α₂>α₁, the GFSO experiment Blackwell-dominates the lower-adherence one;
  any rational agent with any utility does weakly better.
- **Type.** C — conditional on the **named premise** "informal channels invariant to α"
  (protocol does not forbid calling). Given the premise, the garbling kernel makes dominance
  analytic (M); the "weakly better for *any* utility" corollary rests on the Blackwell-
  **equivalence** direction (Marschak & Miyasawa 1968, cited §18.1), not on garbling alone.
- **Falsifier.** A setting where adopting protocol signals **degrades** a rational agent's
  decision quality — which, given Blackwell, can only happen if the protocol *removes/poisons*
  informal information (premise violated). So the real empirical target is the premise:
  *find a deployment where introducing GFSO suppresses the informal channels it sits on.*
- **Tested?** ◻ — needs deployment data (§26.5).

### Prop 4 — constraint improvement (§17)
- **Claim.** When Δ>c, protocol constraints raise expected payoff for any P(θ_bad)>c/Δ.
- **Type.** C — conditional on Δ>c (cost of failure > cost of compliance), named at §17.
- **Falsifier.** A setting with Δ>c where mandatory criteria/ACCEPTED_RISKS/immutability strictly
  *lower* expected payoff → the dominated-strategy argument fails.
- **Tested?** ◻ — E0e (+34pp) is *adjacent* corroboration (explicit criteria help), not a
  direct test of the constraint-payoff inequality.

### Cor 5 — α-monotonicity (§18.1)
- **Claim.** E[u|I(α)] non-decreasing in α — an INFORMATION claim, carrying no compliance cost: no information threshold below which more protocol makes a rational agent's evidence worse. The net-payoff threshold is Prop 4's ℙ(θ_bad)>c/Δ (§17), not this entry's.
- **Type.** C (direct corollary of Prop 3; inherits its §16.2 premise — informal channels
  invariant to α — *not* the (ii)-proxy; so this one is adjudicable in principle). *Why exempt
  from ⟨ii-dormant⟩ while Prop 6 is not:* Cor 5 ranges over α at **fixed information content** (a
  Blackwell-garbling fact about how much protocol is on), whereas Prop 6 asserts new signals are
  **informative-not-noise** over time — which is exactly clause-(ii). Different premise, hence
  different dormancy.
- **The α premise, now named at the site (§18.1).** α is **exogenous**: nothing in the model sets
  it, and the result is monotone in it. The premise stands at Cor 5, Prop 6 and §23; its closure is
  a boundary (§8 entry above); its measurable half is derived (α is an observable of the graph).
- **Falsifier.** A rational agent and utility for which more adherence strictly lowers
  expected utility (a "valley" in α) without violating the §16.2 premise.
- **Tested?** ◻ — adjudicable via deployment (premise is observable), unlike the ⟨ii-dormant⟩
  claims.

### Prop 6 — temporal monotonicity (§18.2) ⟨ii-dormant⟩
- **Claim.** At fixed α, information grows with time; signals are observations, not noise.
- **Type.** C — **under (ii)-faithfulness discipline** (canon §2–§3: "signals are not noise"
  is exactly the clause-(ii) requirement that criteria track reality).
- **Falsifier.** A GFSO system where accumulated protocol history makes decisions *worse* over
  time **while criteria faithfully track reality** (discipline held). If decline traces to a
  faithfulness break, that is FM-3 / §8 (in-framework), not a falsifier of Prop 6.
- **Tested?** ◻ — long-horizon (§26.5), **and non-adjudicable until the (ii)-proxy exists**
  (shared caveat above): without an outcome-independent faithfulness measure, any decline is
  re-attributable to FM-3, so this falsifier shares Pred-1/Pred-3's dormancy, not a plain "awaiting
  deployment".

### Prop 7 — scale bounds, ‖eₙ‖ ≤ (Λ·γ)ⁿ‖e₀‖ (§18.3)
- **Claim.** Validation damps error multiplicatively down a feedforward hierarchy; Λ·γ<1 ⟹
  exponential suppression.
- **Type.** C — under three **named model assumptions** (§18.3: uniform Λ, linear operators,
  feedforward/no-adaptation). Worst-case upper bound.
- **Falsifier.** A validated hierarchy where error grows faster than (Λ·γ)ⁿ **with the three
  assumptions holding** → the operator-composition bound is wrong. (Heterogeneous/adaptive
  hierarchies are out of the assumption set, not falsifiers.)
- **Tested?** ◻ — needs Λ,γ proxy measurement (§26.8). *(Note: canon §3.6 names Prop 7 /
  §20-Mech.2 explicitly among the results holding under the (ii)-faithfulness discipline; what the
  γ<1 hook adds is the **observable §26.8 measurement** of validator gain — adjudicable
  independently of the criteria-faithfulness proxy, so the entry is testable without waiting on that
  proxy, not re-graded away from it. The dependency is still disclosed via
  "with the three assumptions holding".)*

### §18.3 corollaries + small-gain stability (Cor 1–3, Zames 1966)
- **Claim.** Sparse validation needs γ≤Λ^{−k} at every k-th level (Cor 1); cascaded validators
  compose γ(V₂∘V₁)≤γ₁·γ₂ (Cor 2); the GUARANTEED bound falls by γⁿ — a guaranteed reduction Λⁿ(1−γⁿ)‖e₀‖, exponential in n —
  against a checking cost linear in n (Cor 3; the difference Λⁿ−(Λ·γ)ⁿ is NOT a bound on realized
  benefit, both terms being upper bounds — the corollary is about the guarantee); the upward CHALLENGE/BLOCK channel is BIBO-stable when gain↑·gain↓<1 (small-gain).
  The small-gain stability is **re-used** by §2–§3's backward-attribution.
- **Type.** M (operator-norm algebra + Zames small-gain theorem), inheriting Prop 7's three model
  assumptions (so C on those).
- **Falsifier.** A validated cascade where composed damping exceeds γ₁·γ₂ (sub-multiplicativity
  violated), or a CHALLENGE/BLOCK loop that diverges (infinite challenge-override spiral) **with**
  gain↑·gain↓<1 → the small-gain bound is wrong, and §2–§3's attribution-stability loses its prop.
- **Tested?** ◻ — same Λ,γ measurement gap (§26.8); the spiral-stability is the concrete
  observable (does a real correction loop converge?).

### Prop 9 — decomposition quality, 4 independent mechanisms (§20)
- **Claim.** GFSO improves decomposition via 4 mechanisms (information enrichment, validator
  composition, space restriction, feedback), each provably operative, **independent** (failure of
  one doesn't void the others).
- **Type.** Mixed. Mech.2 (composition) + Mech.3 (constraint restriction) = M (inherit Cor 2 /
  Prop 4). Mech.1 (enrichment) + Mech.4 (feedback) = C ⟨ii-dormant⟩ — they require the enriched
  information / recorded defects to *faithfully track reality*, the same (ii)-proxy.
- **Falsifier.** A mechanism reducible to another (independence fails); or a setting where Mech.2/3
  (the M ones) fail to improve decomposition with their premises held; or — for Mech.1/4 — a case
  of richer-history-yet-worse-decomposition **with faithfulness held** (non-adjudicable until the
  (ii)-proxy exists, shared caveat).
- **Tested?** ◻ — E0e (+34pp) is adjacent corroboration of the constraint mechanism only.

### Prop 8 — IC as a dominant strategy (§19) + §19.1 IC-minimality
- **Claim.** When `p`·cost(undetected defect) > cost(signal), at that signal's detection probability
  `p` (§19: `p` = 1 on the rows whose consequence the FSM forces — a FAIL on unsatisfiable criteria,
  a timeout on a silent blocker; `p` = 1−∏(1−p_j) over the §26.3 validation cone on the acceptance
  row, whose discovery is q_V's trigger-dependent pass→later-fail term), honest use of each signal is optimal — and
  the canon states this **per state, not ex ante** (§19): the honest policy is **state-contingent**
  ("signal iff you observe the condition" — the reporter knows its own state; θ is hidden from the
  *counterparty*), so under θ₁ honesty strictly beats silence and under θ₂ silence strictly beats a
  false alarm, **with no prior over θ and no Δ/ε ratio needed**. The familiar "for any ℙ(defect) > 0"
  form is the **ex-ante coarse corollary** (§19), not the primary claim. §19.1: removing any one
  IC-critical feature makes honesty cease to dominate for a specific agent.
- **Non-adversarial sub-domain — dominant-strategy, not merely Bayesian.** Type **M/C-constructive**
  (not "merely awaiting deployment"): §19 gives a per-signal payoff argument and §19.1 a **complete
  11-feature enumeration**, each with its named dishonest behavior. Because detection is **structural**
  (verifier≠executor + q_V's pass→later-fail term, plus auto_pass as the
  detector of issuer inaction, §14.3/§24.5/§24.7; a silent BLOCK caught by the timeout) the CHANNEL
  does **not** depend on the counterpart's strategy (structural is a claim about the channel, not `p`=1) — so for each **detection-covered** signal honest use
  is a **dominant strategy** (stronger than the "Bayesian IC" label), established by dominated-strategy
  elimination against nature θ, not pending data. **Qualifier:** this holds for Executor signals + Issuer
  ACCEPTED_RISKS/criteria; the **Issuer false-FAIL / griefing** direction is *not* detection-covered — it is
  the **named q_V boundary** (§24.5: false-FAIL is guarantee-safe but cheap for a griefing Issuer), not
  dominant. Falsifier: a signal in the §19.1 table whose removal leaves honesty still dominant (the
  enumeration over-counts), or a non-adversarial agent with `p`·cost(undetected defect)>cost(signal)
  at that signal's `p` for whom dishonesty pays. (An agent with cost(defect)>cost(signal) but
  `p`·Δ<ε for whom dishonesty pays is PREDICTED by Prop 8 as restated, not a refutation of it.)
- **Adversarial domain — characterized *stratification* (§24.2), not a gap; the incentivized core is an OPEN PROBLEM (§26.3) by the §8 criterion, only its `p = 0` limit a boundary.** Guarantees stratify into
  **adversarial-independent** form-claims (finality criterion §14.3, composition law T1, 7-FM coverage,
  self-measuring T10, the minimalities §10.2/§14.4/**§19.1 IC-feature-set**, FSM determinism — sabotage
  only *instantiates* an FM-form, intent is an orthogonal causal axis, not an 8th FM) and
  **adversarial-conditional** ones, resolved by three imports off the three §14.3 assumptions: dropping
  Prop 8 → mechanism design (bond *restores* the Hurwicz inequality cost(defect)>cost(signal) on the
  incentivized surface); dropping single-Del → crypto-identity; dropping single-sequencer → BFT-consensus
  — where **identity and order are preconditions** of Hurwicz (the arena in which the inequality is even
  formulable), not cost-gradients. **Detection split:** detectable-incentivized (p>0) is where mechanism
  design restores IC (optimal design open); undetectable (p=0) **collapses into the §8 domain-silent
  false-PASS boundary**, not a separate adversarial gap. In the **permissioned** scope (A1∧A2 +
  institutional boundary) single-Del and single-sequencer are protected for free by the substrate;
  Sybil/fork need the boundary removed (permissionless), outside A1∧A2. **Genuinely-open** = the
  detectable-incentivized behavioral core over an **authenticated insider** (optimal collusion-proof
  mechanism design — Laffont–Martimort-hard), not a GFSO-specific gap. Type **E** for that core (I); the
  undetectable part (II) is **M**-analytic (§8).
- **Localization (§26.3).** The collusion residue is redundancy-attenuated along the validation cone:
  a colluding false-PASS survives all in-protocol detection with probability `∏_{j∈cone}(1−p_j)`, `p_j` =
  validator sensitivity (**faithfulness**, Lemma 1 — *not* graph connectivity). The open kernel localizes to
  the **sensitivity-sparse frontier** (non-constructive). *Falsifier (M):* an honest, criterion-**sensitive**
  cone (every `p_j > 0`, no collusion) under which a false-PASS nonetheless survives in-protocol detection —
  would refute the attenuation. *Anti-falsifier note:* a large cone of **insensitive** validators surviving is
  NOT a refutation (it is the sensitivity-sparse frontier, as predicted).
- **Tested?** — (non-adversarial) analytic via §19.1 (dominant-strategy for detection-covered signals);
  ◻ (adversarial core) open, Laffont–Martimort-hard, localized to the sensitivity-sparse frontier (§26.3);
  undetectable part = §8.

### Thm 10 — self-measuring (§21)
- **Claim.** Every Q component is computable from the execution trace with no extra data
  collection.
- **Type.** M (constructive — each q is a graph query, §21).
- **Falsifier.** A Q component that cannot be computed from G alone (needs out-of-band data)
  → self-measuring breaks. **On the false-FAIL direction:** q_V senses the acceptance (false-PASS)
  direction of FM-3 **by design** (§24.5): the false-FAIL direction is guarantee-safe, so an
  aggregated false-FAIL rate is an *optional diagnostic*, not an instrument incompleteness and not a
  falsifier of Theorem 10's computability claim (§21 untouched). See the q_V boundary flag below.
- **Tested?** — analytic (constructive: the queries run on G); ◻ predictive calibration of Q
  vs real outcomes is open (§24.5, §26.2).

### Thm 11 — structural transparency (§22)
- **Claim.** Under protocol compliance, every decision has a record R(d).
- **Type.** M (from invariants §14.4).
- **Falsifier.** A protocol-compliant decision with no audit record → an invariant is not
  doing what's claimed.
- **Tested?** — analytic (follows from immutability + mandatory fields).

### §23 — three-pillar indispensability / feedback loop
- **Claim.** Protocol + self-measuring + AI-layer form a monotone feedback loop; removing any one
  pillar makes *GFSO-channel* improvement impossible — at TWO grades (canon §15.3.5 / §23; Abstract, §28):
  outright for the protocol and for self-measuring, and **only beyond the capacity threshold `t*`**
  for the AI layer, since Prop 6's proof invokes no AI layer and below `t*` the loop runs at human
  capacity (§15.3.1).
- **Type.** C — the "no improvement" is scoped to the GFSO channel; informal channels (§16.2) may
  still yield residual Q (the v3.4 fix to §15.3.5: "no GFSO channel", not literal Q=const).
- **Falsifier.** A deployment where Q improves **through the GFSO channel** with a pillar removed —
  e.g. q-metrics rise with no AI-layer **past `t*`** and with no informal substitute, or adherence
  rises with self-measuring off. (Q rising with no AI layer BELOW `t*` is not a falsifier — it is
  what §23 now states.) (Improvement via informal channels is not a falsifier — it is the named
  scope.)
- **Tested?** ◻ — needs an ablation deployment; never run.

---

## Part III — Positioning (§25) and the theory-model (§2–§3) — v4's own Part I, the foundation

### §25.1 — adaptive stratification by horizon
- **Claim.** CHALLENGE frequency strictly increases with decomposition depth.
- **Type.** C — **explicitly conditional on the stationarity premise** (step 4: environment
  drift-rate independent of level), named in-canon as an empirical posit, not derived.
- **Falsifier.** A GFSO system with deadline coherence along D **and** a stationary environment where deep
  (short-horizon) tasks do **not** CHALLENGE more often than shallow ones. (Non-stationary
  environments are outside the premise.)
- **Tested?** ◻ — needs CHALLENGE-frequency-by-depth data from a deployment.

### §25.2 — Scrum ⊂ GFSO
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
- **Behavioral-generativity frontier — characterized, not a claim.** *Were* the stronger claim made —
  that A1∧A2 **generate** Scrum's exploratory dynamics (short fixed sprints, empirical inspect-adapt,
  self-organizing execution-time decomposition) rather than merely **contain** them — its falsifier is
  **E and E3-bound.** Test: run GFSO from A1∧A2 under Scrum's restriction regime (§25.2: depth≤2,
  weak-A1, small team, low error-cost) and observe whether the exploratory cadence *emerges as a forced
  optimum* (cf. §7 stop-replan / front-load) or must be added by hand. **Falsified by**
  restricted-regime GFSO dynamics that (a) fail to reproduce Scrum's cadence (generativity absent), or
  (b) reproduce it only under an assumption *not entailed* by A1∧A2 (contained, not generated).
  Behavioral ⟹ needs execution/experiment ⟹ **E3** — the same execution gate as Pred-1 / §8 (E2 gave
  a decomposition-convergence method, not method-value; §6.2). Until E3 this is **characterized-open**,
  not merely "unmade": the claim stays unmade, but its falsifier and its dependency are now named. (The
  structural entry above is unaffected; nothing here is claimed proven.)

### §8 — causal-correctness boundary (the structural anchor)
- **Claim.** Level-2 causal correctness — that a real decomposition's children criteria *in the
  world* entail the parent's — is a **characterized boundary**, not an "open algorithm": it is
  not derivable from A1+A2 (the formal half cannot supply S) and not closable by declaration (a
  declaration is itself a decomposition whose correctness is a new instance — regress, Lemma 2).
  Every C-claim below and every §2–§3 prediction ultimately reduces to this boundary; it is the
  canon's most-cited limitation (§11.1, §24.3, §8, §15.3.6).
- **Type.** **M** for the *non-reducibility* (it is the §2–§3 Lemma 1 + Lemma 2 result: S ∉
  language{A1,A2}; declaration regresses). **E** for the *located* manifestation — the boundary
  is crossed only by execution, surfacing as a backward signal.
- **Falsifier.** (M side) A method that certifies real causal correctness from the formal half
  **alone** (no execution, no agent contact) → breaks Lemma 1. (E side) the backward signal:
  all children pass yet the parent is undelivered in the world → the decomposition was causally
  wrong; attributed to the node owning the broken composition claim (FM-1.d / FM-1.b, §2–§3).
- **Tested?** — (M) analytic; (E) ◻ E3 territory (multi-agent decomposition with per-child V).
  This is the boundary the §12.8 CA1 ✅\* sits *inside*: completeness-as-basis holds, but the
  *correctness* of any given decomposition against S is exactly what the apparatus does not
  certify.

### §3.2 — theory-model: agent necessity (the derivation)
- **Claim.** The agent (carrier of empirically-learned domain content Ŝ) is a **necessary**
  structural link — the apparatus cannot supply domain-correctness (Lemma 1), declaration
  cannot ground it (Lemma 2), luck is unstable, so empirical contact is necessary.
- **Type.** M — a derivation (excluded-middle d3 + Lemmas 1–2 + luck-elimination). The thin
  local residue is the "luck is unstable" step, argued from S's contingency.
- **Falsifier (mathematical).** Exhibit reliable domain-correct decomposition with **no**
  empirical contact — pure formal derivation of S (contradicts Lemma 1) or grounded
  declaration (contradicts Lemma 2) or *stable* luck (contradicts S-contingency). Any one
  breaks the derivation.
- **Tested?** — analytic; corroborated by pre-theoretic success being explained, not assumed.

### §3.6 — prediction Pred-1: agent substitutability
- **Claim.** Two agents are interchangeable **relative to an outcome-independent faithfulness
  proxy** (equal faithfulness ⟹ equal validated results).
- **Type.** E.
- **Falsifier.** Two agents with **equal** faithfulness-proxy (measured independently of
  outcome) yielding **systematically different** validated outcomes — or equal outcomes from
  unequal faithfulness. The outcome-independence of the proxy is what makes this non-circular
  (canon flags: a proxy defined via success would make it untestable).
- **Tested?** ◻ — **falsifier well-formed but DORMANT.** The canon (§2–§3, §15.3.7, §13.2) gives
  no operational outcome-independent faithfulness proxy yet (nearest candidate = §13.2
  domain-precedent, itself judgement-drawn — Flag 4). Non-circular in form, non-operational in
  fact — same status as Flag 1's missing counter. E2 ran, but measured **convergence to a
  (bare-built) reference**, not faithfulness to the real domain — it did **not** build a
  faithfulness proxy; this locus stays blocked (the value / faithfulness test routes to E3 / execution).

### §3.6 — prediction Pred-2: applicability boundary
- **Claim.** Structural success-content present ⟺ GFSO applicable (sharpens §9).
- **Type.** E.
- **Falsifier.** A domain with no structural success-content where GFSO nevertheless governs
  handoffs successfully, or vice versa.
- **Tested?** ◻ — **partially dormant, same proxy as Pred-1/Pred-3.** "Structural success-content
  present" is judged by the §2–§3 structural-half apparatus; insofar as that detection leans on
  faithfulness, Pred-2 inherits the same non-adjudicability. The *one* half that is plausibly
  outcome-independent — "does a structural validation half exist at all?" (an architectural fact,
  observable like Simon-t\* capacity) — is testable; the "success-content" half is not, until the
  proxy exists. So Pred-2 is split: structural-presence side ◻-adjudicable, success-content side
  ⟨ii-dormant⟩. The asymmetry with Pred-1/Pred-3 is thus only partial and is now stated, not assumed.

### §3.6 — prediction Pred-3: global falsifier (the model's own neck)
- **Claim.** Sustained out-of-distribution success with **neither** a structural half **nor**
  learned faithfulness is **impossible**.
- **Type.** E — the deliberately-stated global falsifier.
- **Falsifier.** Exactly that: a system that **reliably** succeeds OOD while (a) carrying no
  structural validation half and (b) having demonstrably-low faithfulness **measured
  independently of the success itself**. The independence clause is load-bearing: without it
  any counterexample is re-explained post-hoc, and the claim would be circular (canon §2–§3
  fixes this explicitly).
- **Tested?** ◻ — no such system observed; the claim is an open standing bet. Note the same
  dormancy as Pred-1: refuting it requires faithfulness "measured independently of success", and
  no such instrument exists yet — so the bet is well-posed but not currently adjudicable.

---

## Part III.6 — v3.6 agent-free ontology + methodology (§6.1–§6.2, §4, §7)

> The v3.6 layer adds **no new formal results** (canon: T1/7-FM/minimality/Prop 3–9 untouched);
> it unfolds §2–§3 into an agent-free ontology + a forced methodology + an honest reducibility
> audit. The register treats it on the **same E/M/C discipline** as everything above. Two
> consistency anchors govern these entries and are checked at the bottom: **(α)** structural-
> completeness claims are **M / analytic-modulo-a-named-residue** — the 5-link completeness is
> the *direct sibling* of the 7-FM completeness entry (§12.4) and the §12.8 / §13.4 covering claims,
> not a new empirical posit; **(β)** the **only** irreducible empirical hooks remain the two
> contact-with-world loci already registered — A1∧A2 membership (§9) and **Ŝ-faithfulness to S**
> (§2–§3, the ⟨ii-dormant⟩ locus / §15.3.6) — and v3.6 relocates nothing into or out of those.

### §4.2 — 5-link completeness of directed action (covering axiom)
- **Claim.** Directed action *is* a chain of exactly five constitutive links {Link-1 goal, Link-2 build-Ŝ,
  Link-3 plan-D-over-Ŝ, Link-4 execution, Link-5 contact} (the verification levels they must not be
  confused with are named — Syntactic/Semantic/Pragmatic, §13.4); none removable; **no independent 6th** structural
  feature. Derived by a covering axiom (REACHES-ternarity ⊕ realization-pair = REPRESENTATION
  {Link-1,Link-2,Link-3} ⊕ REALIZATION {Link-4,Link-5}), the modal axis being the model's own Ŝ-vs-S axis.
- **Type.** **M — analytic modulo a named covering axiom, and *below* the 7-FM-completeness grade
  (§12.4)** — the body below states why, and the two must not be read apart. A covering principle does
  the work, and there is a **thin, located residue** rather than a clean theorem on every leg. Per
  canon §4: the **modal** leg (2 relata ⟹ 2 modal sides) and the **realization** leg
  (in/out, no third direction) reach full §12.8-strength (excluded-middle); the **representation**
  leg is **sub-§12.8** — the {goal, Ŝ, D} triple holds only *modulo* the (poorer) REACHES-ternarity
  axiom, which carries a **loaded residue: START** (the source-relatum) is a genuine 4th relatum of
  REACHES, *folded* (not eliminated) into the execution-anchored present by a **stated model
  choice**. Reject the fold ⟹ 4 representation roles ⟹ the 3⊕2=5 count breaks. So this is *weaker*
  than the 7-FM split (whose residue — the value/time trace-edge; the single clock is **off** it,
  discharged §12.8 — is local and does **not**
  touch the count); registered as M-with-a-residue, not as a closed theorem, and not as empirical.
- **Falsifier (M).** A **real directed-yet-real action** that (a) is missing one of the five links
  while still being directed-and-real, or (b) exhibits a genuinely **independent 6th structural
  feature** — a third modality, a 4th REACHES role *not* foldable into START, or a 3rd realization
  direction. Any one means the covering axiom (or the START-fold) has a hole — an analytic defect,
  exposed by a counterexample, **open-from-inside** like §8 (canon's own framing). This mirrors
  the 7-FM falsifier ("a failure the case split routes to no Cᵢ") and the §10.2 minimality falsifier
  ("an HVP expressible after deleting a primitive") — same shape, not a new kind of test.
- **Tested?** — analytic; minimality is at full parity with §10.2 / §12.5 (per-element counterexample).
  Adequacy-to-phenomena would be corroborated by the *same* E1-style evidence as CA1 / §13.4 (a
  missing-link or 6th-feature action would surface as an uncovered action); not separately run. The
  START-fold residue is the located weak point — the analogue of CA1's value/time residue.

### §7 — methodology forced-corollaries (front-load FORM, stop-replan optimum)
- **Claim.** From the ontology a discipline is **forced** (not best-practice): the failure-point
  coarse-cut is **derived** (FORM ⊕ FAITHFULNESS = the validity⊥faithfulness axis of §2–§3), and
  it forces **exactly two** mechanisms — (1) front-load FORM on the executable segment; (2) at a
  contact-wall `e∈Ŝ\S`: STOP → mark locally → re-derive (re-run FORM-check on updated Ŝ) → only then
  proceed. The stop-replan + front-load discipline is shown a **[FORCED] instance** of the optimum
  that minimizes total realized cost-over-the-knowable `c_check + E_FORM + E_FAITH`.
- **Type.** **M — forced from the ontology** (the coarse-cut is derived via excluded-middle on
  "does the edge violate Ŝ's *own* well-formedness", so exactly two classes ⟹ exactly two
  mechanisms). **The cost/probability VALUES are E / contextual** — `c_check`, the FORM-risk, the
  S-fixed wall-set are domain data, exactly as **S itself** is contingent (Lemma 1) and as the
  Prop 3/4/7 *premises* (Δ, c, Λ, γ) are E. This split — **structure forced (M), magnitudes
  empirical (E)** — is the *same* shape already used for Prop 4 (Δ>c and
  ℙ(θ_bad)>c/Δ named, inequality M) and the
  §18.3 corollaries (algebra M, Λ·γ measured). The optimum is stated **precisely**, matching the
  canon's hedges: it is **not** "always E_FORM=0" (only in the cheap-check limit `c_check→0`),
  **not** "never fail" (Lemma 1), **not** a global optimum over all plans, **not** uniqueness among
  faithful D (§2–§3 multiplicity). Cost composes as **edge-decoration**, **not a 6th link** —
  consistent with the §4 entry (the 5-count is closed; methodology adds no relatum).
- **Falsifier (M, on the forcing).** A directed-action failure that is **neither** FORM nor
  FAITHFULNESS (a third epistemic-access class) → the coarse-cut derivation has a hole (this is the
  *same* falsifier as the §7 "FORM ⊕ FAITHFULNESS" cut and reduces to the §12.1 / 7-FM split —
  it does **not** introduce a new test). Or: a setting where front-load+stop-replan is **dominated**
  by proceeding on an un-updated plan **with `c_check` and the cascade-compounding (§18.3) premises
  holding** → the optimality derivation (not the value estimates) is wrong.
- **Falsifier (E, on the magnitudes).** A domain whose measured `c_check / E_FORM / E_FAITH` make
  the front-load *granularity* or the verify-depth come out elsewhere than predicted — this falsifies
  a **contextual value**, not the forced structure (same status as a wrong Δ or Λ,γ estimate). The
  *free residue* (speed, route among faithful D, front-load granularity above the "executable
  segment" floor) is **forced-free** — orthogonal, so unfalsifiable-by-design and correctly so.
- **Tested?** — (forcing) analytic; (magnitudes) ◻ routed to E3 + the §26.8 Λ,γ measurement (E2 was
  decomposition-convergence, not these magnitudes), the same empirical hooks as the C-claims (Flag 5). No
  run measures THESE magnitudes; the methodology itself has been driven end-to-end on a benchmark at
  calibration tier (EVIDENCE_LOG §13), which is not the same thing.

### §7 — verify-vs-explore structure (how far to run the FORM mechanism)
- **Claim.** "How far to discharge FORM" is itself a **structured tradeoff** (verify-vs-explore,
  §13.5): strict domination of front-loading holds **only** in the cheap-check limit
  `c_check→0`; above it the marginal `c_check` is weighed against the marginal prevented FORM-risk.
- **Type.** **M-forced structure, E values** — same split as the entry above and same family as the
  §11.4 informativeness / Blackwell-surplus reasoning (the *structure* of "decision-relevant vs not"
  is analytic; what is decision-relevant on a real task is E). The existence and *shape* of the
  tradeoff are forced; the **crossover point is the empirical / contextual datum** (`c_check` vs
  prevented risk), not a hedge on the structure.
- **Falsifier.** (M side) a FORM-discharge decision that is neither "verify more" nor "explore /
  proceed" and cannot be located on the §13.5 axis → the tradeoff is mis-structured. (E side) a
  measured `c_check`/risk regime where the predicted crossover sits elsewhere → a wrong value, not a
  broken structure. (As with §11.4, a merely *informational* surplus that never moves the verify
  decision is **not** a falsifier.)
- **Tested?** ◻ — analytic structure; crossover never measured (E3, §26.8).

### §6.1 — honest [known]/[GFSO] ratio (narrow-delta accounting)
- **Claim.** Standard planning is **absorbed** as one rewritten sub-step (search over Ŝ = link Link-3;
  **planning ⊂ GFSO**), and the irreducible [GFSO] new-mechanics delta is **exactly five** items
  (joint-suff AND-soundness `(t,{tⱼ})∈S` / failure root `Ŝ\S` + composition law / constitutivity of
  the S/Ŝ split / agent-free recursion / EXTERNALIZE-form). Standard abstraction/method-learning (ABSTRIPS
  [32], HTN-MAKER [33], goal-regression [34], HRL-discovery, LLM-decomposition) does **not** subsume
  the core: bare seam-generation is [known]-heuristic; the only [GFSO] generative residue is
  EXTERNALIZE-form + faithfulness-grade.
- **Type.** **M** — an analytic accounting / per-candidate reducibility claim, **distinct** from §6.2's
  E premise (this is about *mechanic-novelty*, not about how organizations actually plan).
- **Falsifier.** Exhibit a standard technique that subsumes one of the five delta items **as a
  guaranteed primitive** (not a heuristic): e.g. a method-learner that *guarantees* (not corpus-
  heuristically posits) a faithful new seam, or an option/HTN formalism that **obligates + attributes**
  the set-level integration implication `(⋀ children)⟹Capt(parent)` → the "narrow delta" enumeration
  is wrong (delta narrower, or an item misattributed to [GFSO]).
- **Tested?** — analytic; corroborated by the §6.1 per-candidate reduction (each candidate isolated,
  none subsumes EXTERNALIZE). Lemma 1 yields only *non-derivability-by-apparatus*, **not** a [GFSO] tag for
  bare seam-generation — so the accounting does not inflate the delta.

### §6.2 — value=making-explicit empirical premise
- **Claim (the load-bearing empirical premise of the positioning).** "Most real working
  methodologies are **assemblies of prior plans, typically run without an internal-consistency
  check**" — this is what makes GFSO's primary value *making-explicit* (lifting decomposition out of
  private, unchecked, idiosyncratic intuition into one axiom-derived, consistency-checked,
  faithfulness-graded system), rather than method-novelty (the new-mechanics delta is narrow, §6.1).
- **Type.** **E — a contingent claim about how real organizations actually plan,** explicitly
  **routed to E3** (canon §6.2; E2 gave the convergence *method*, not the discipline's *value*). It is **not** M: nothing in
  A1∧A2 forces that real methodologies are unchecked; that is an observation about the world, and is
  correctly typed E (unlike the §6.1 *ratio*, which is an analytic accounting of mechanic-novelty).
- **Falsifier.** A representative sample of real working methodologies that **do** routinely carry an
  internal-consistency check (CHECK-7/8-equivalent) on their assembled plans → the premise is false
  and the "making-explicit is the primary value" positioning loses its empirical base. (A single
  counterexample methodology is not enough — the claim is about the *typical* case, so the falsifier
  is distributional, like the Simon-t\* capacity-necessity entry.)
- **Tested?** ◻ — **E2 ran but did NOT adjudicate this.** E2 measured LLM decomposition *convergence to
  a (bare-built) reference*; by the bare-reference confound, coverage cannot read the *value* of
  made explicit discipline over unchecked assembly (bare ≈ method on coverage — that comparison needs
  **execution = E3**). E2 did establish the convergence *method* (`decompose()` = bare-SEARCH ⊕ gfso-AUDIT).
  The premise stays a genuine, outcome-independent hook (you can audit a methodology for a consistency
  check without running it to success) — routed to E3, plus a survey of real methodologies would bear on it.

### §8 — the boundary/open-problem CRITERION (the meta-rule this register rests on)
- **Claim.** An item is a **boundary** iff the canon exhibits an impossibility argument **from A1 ∧ A2**
  (the Lemma-1 form: the object is not definable in the axioms' language; or the Lemma-2 form: every
  declarative closure is a fresh instance). Hardness, the absence of a construction, and "not yet built"
  are **open problems** (Ch. 26). Applied entry by entry to Ch. 8's list.
- **Type.** **M** — a rule about the canon's own classification; checkable by inspection of each entry.
- **Why it is load-bearing.** Without it "boundary" converts open problems into results by naming, and
  the framework becomes unfalsifiable *in aggregate* — a failure would be either a named failure mode,
  or a named boundary, or outside A1 ∧ A2, with nothing saying when the middle label is earned. §8's
  own lead states exactly this.
- **Falsifier.** An entry on Ch. 8's list for which no A1 ∧ A2 impossibility argument can be exhibited
  (the label is unearned — the entry belongs in Ch. 26); or an entry in Ch. 26 that *does* carry one
  (a boundary mis-filed as an open problem). Both falsify the **application**. The **criterion** itself
  falls if a genuine third kind of closure-unavailability is exhibited, neither Lemma-1 nor Lemma-2 in
  form — in which case the two-form definition is incomplete.
- **Tested?** ◻ — applied across Ch. 8 at the v4.0 closing pass; no external audit of that application.

### §15.4 — triage order over the graph
- **Claim.** Repair first the failing node whose **dependency cone** (upward through E_D by Thm 1,
  forward through E_Dep) blocks the most, nearest binding deadline as the tie-break; ranking by *how
  badly* a node failed is not this rule but the cardinal-severity boundary (Ch. 8).
- **Type.** **M** for the derivation — both inputs are primitives already carried, and the cone is a
  reachability query over 𝒢 in Thm 10's own currency. **C** for the optimality gloss, on the named
  premise that repair cost is roughly uniform across the failing nodes (§15.4 states it).
- **Falsifier.** A graph in which following the rule unblocks strictly less work than an available
  alternative ordering — most naturally where repair costs differ sharply, which is exactly the named
  premise; or a case where cone size and deadline order conflict and the stated tie-break yields the
  worse outcome. Falsifying the gloss leaves the *derivation* standing: the cone and the deadline order
  are facts of the graph either way.
- **Tested?** ◻ — derived, never exercised; it prescribes an operator behaviour no deployment has run.

### §8 — the named boundaries (the faithfulness residue is the irreducible (ii) locus)
- **The criterion (canon §8, stated 2026-08-04).** An item is a **boundary** iff the canon exhibits
  an impossibility argument **from A1 ∧ A2** (Lemma 1 form: the object is not definable in the
  axioms' language; Lemma 2 form: every declarative closure is a fresh instance). Hardness, absence
  of a construction, and "not yet built" are **open problems** (Ch. 26), not boundaries. A second
  kind is tagged separately: **disclosed postulate residues** — the named edges of the covering
  axioms (the representational branch sub-CA1, the CA1 value/time residue), which are declared
  placements rather than impossibilities. Consequence for this register: the adversarial optimum
  (optimal bond / collusion-proof quorum) is re-filed as an **open problem** at §26.3, its `p = 0`
  limit alone being the Pragmatic-level boundary.
- **Claim.** The canon names **eight** boundary-list entries (§8), **declared honestly, NOT closed**. The four
  this entry was written for (the v3.6 inventory): the
  **faithfulness residue** (domain-silent FM-3 false-PASS — a present-but-insensitive integration
  edge, a-priori uncatchable by *any* discipline, Lemma 1); the representational branch (sub-CA1) gap
  (§4.2, above); the CA1 residue (§12.8; the single clock is off it — discharged); and **decomposition-method quality**
  ("how to invent a *faithful* seam" — EXTERNALIZE formats/grades but does not guarantee faithfulness; **E2
  closed the generation procedure (`decompose()`; the logic-free positing leap remains, Reichenbach); seam-faithfulness remains the E3 + engineering blocker**).
  The four that joined §8 since: **Level-2 causal correctness** (relocated into §8 from the
  open-problems list — a boundary of the first kind, not an open task; it is the **Pragmatic-level
  boundary**, of which the faithfulness residue above is *half (ii)* — canon §8, not the converse);
  **goals outside the two finitely-decidable topologies** (`□◇A` recurrence, §5.6); and **cardinal
  severity** (a permanent import — it needs a probability measure over outcomes, §6.3; read at the
  triage decision, §15.4); and **adherence dynamics (α)** — every Part-III guarantee is monotone in
  α and nothing in the model sets it, whose closure needs a utility model over actors that A1 ∧ A2
  do not supply (§18.1). Its *measurable* half is derived and falsifiable: α is an observable of
  the graph (a node without criteria, a PASS without independent validation, a decision without a
  record — Thm 10 / Thm 11), so the exogeneity premise is measured rather than assumed. **Falsifier
  of that half:** a deployment where adherence cannot be read off the trace though the protocol ran.

- **Type / routing (consistency-critical).** Each boundary **reduces to an already-registered
  entry** — no boundary of a new *type*:
  - **faithfulness residue → the irreducible empirical (ii) locus.** Identical to FM-3 / §8-(ii)
    / §15.3.6 — registered above as ⟨ii-dormant⟩ and as the "(ii)-faithfulness proxy is dormant"
    shared caveat (Part II). Type **C/E, DORMANT**: falsifier = a domain-silent false-PASS detected
    by a purely-formal apparatus (breaks §2–§3 Lemma 1), but **non-adjudicable** until an
    outcome-independent faithfulness proxy exists (Flag 4 / Pred-1). This entry asserts **no new test**;
    it confirms the v3.6 ontology terminates its empirical irreducibility at *exactly* the
    pre-existing (ii) locus — anchor (β).
  - **representational branch (sub-CA1) → §4.2 entry above** (M, START-fold residue).
  - **CA1 / single-clock → §12.8 CA1/CA2 entries + Flag 3** (CA1 = M-residue; single-clock **discharged** — no longer a scope-boundary, §12.8/Part III.10).
  - **decomposition-method quality → §8 / §15.3.6 — a SPLIT, not one entry** (canon §8): the
    *faithfulness* half is a **boundary** (Lemma 1 — no a-priori discipline certifies a seam), while the
    *generation-procedure* half is an **open problem** in the Ch. 26 sense, partly E2-closed. M for the
    non-reducibility of the first half, E-on-execution for the located manifestation. Canon flags it the *real
    blocker*, not a finalization residue.
  - **Level-2 causal correctness (the Pragmatic-level boundary) → the same (ii) locus**, of which the
    faithfulness residue is half (ii) (§8): formally underivable from A1 + A2, and unclosable by any
    declarative extension (every declaration is a fresh Pragmatic-level instance — Lemma 2). Type
    **M** for the underivability, **C/E DORMANT** for the manifestation — no new test.
  - **goals outside the two finitely-decidable topologies → §5.6 entry** (M): `□◇A` and other
    non-finitely-decidable goals are named-uncovered by the object apparatus; the generator reaches
    them only as an attainment-reducing handle. Falsifier = the object apparatus shown to cover a
    non-finitely-decidable goal without the generator.
  - **cardinal severity → §6.3 entry** (M, permanent import): the measure is **contingently absent** — importable wherever a probability model exists (A1 is
    `{0,1}` on one outcome, not a distribution; A2 is structure, not measure) — while the finer
    discordance ordering it would be taken over is **unrepresented** here (§11.4 Inf-B). The **ordinal**
    skeleton ⪰_dom stays internal — only the cardinal is imported.
  - **adherence dynamics (α) → §18.1 + the Cor 5 / Prop 6 entries** — routing to the **cardinal-severity
    species**, not to a new type: **M** for the non-derivability (adherence dynamics need a utility model
    over actors, which A1 ∧ A2 do not supply, exactly as they supply no measure over outcomes), and **E**
    for the measurable half — α is an observable of the graph (a node without criteria, a PASS without
    independent validation, a decision without a record: Thm 10 / Thm 11). Falsifier of that half: a
    deployment where adherence cannot be read off the trace though the protocol ran.
- **Falsifier.** Per boundary, as in the referenced entry. The **only** way to falsify the v3.6
  *boundary inventory itself* is to exhibit an irreducible empirical hook **outside** these eight
  (and outside A1∧A2-membership) — which would mean the ontology has an unregistered contact-with-
  world locus. None found; the inventory closes onto the two pre-existing loci (anchor β).
- **Tested?** ◻ — same as the entries each routes to; the faithfulness-residue locus is dormant
  (no proxy); the method-quality locus = **E2 closed the generation procedure (`decompose()`; the logic-free positing leap remains, Reichenbach); seam-faithfulness
  is the open E3 frontier.**

---

## Part III.7 — continuous-substrate re-grounding + 3-axis faithfulness (§5; the seam half — §2.3–§2.6)

> The continuous-substrate layer (§5: controlled flow `ẋ=f(x,u)` + capture basins; discrete `(t,{tⱼ})∈S`
> = derived shadow; `∼_G` functional scale; separators; A1/A2 as conditions of Contact; SINGLE-SEAM/`𝒜`; 3-axis
> faithfulness; tree/cycle goal topology) adds **no new SPINE result** (canon: Thm 1/7-FM/minimality/Prop-series untouched; v3.9 §5 adds class-level completeness of the two goal-topologies)
> and **no new empirical hook**. It re-grounds existing claims over a borrowed [known] control/viability substrate;
> its empirical irreducibility terminates at *exactly* the two pre-existing loci (anchor β: A1∧A2-membership §9
> + Ŝ-faithfulness §2–§3). Each item routes to a registered entry:

- **Continuous substrate (flow / capture basins / viability).** [known] (Sontag control, Aubin viability) —
  borrowed, not a GFSO-delta (§6.1). Falsifier (M-on-the-borrowed-theory): the domain is not a controlled
  dynamical system — a physics-grade claim outside the GFSO delta. No new GFSO hook.
- **`(t,{tⱼ})∈S` = derived shadow of basin-chaining.** Re-expresses the **Theorem 1 / §11.1** composition edge
  over the continuous ground; operative truth-condition and its M-falsifier unchanged. The [GFSO]-core
  (AND-soundness / integration-implication) is the same narrow delta already registered under Theorem 1.
- **Separators `x₀∉Capt_{S∖B}(G)` = continuous ground of non-redundancy.** Routes to **§10 non-redundancy /
  Theorem-1-correctness**; "correct decomposition cuts at joints" is the continuous reading of non-redundancy
  (M; ontic joint = non-removable subgoal).
- **`∼_G` functional-scale coarsening = continuous ground of ACCEPTED_RISKS / the scale faithfulness axis.** Routes to
  **STD-1** (and the scale axis below); falsifier = a declared coarsening that is NOT a bisimulation yet leaks no
  G-relevant future (or the converse) — the operationalized §13.1.
- **A1/A2 re-read as conditions of Contact (status-change, postulate→condition; the axiomatic status stays primary, §2.6).** Adds no hook: the honest
  residue is **≈ the axioms themselves** (A1.ii = FM-3; A2-residue ≈ κ-cost + decomposability), both already
  registered (A1.ii ↔ the (ii)-faithfulness/FM-3 locus; A2 κ-**cost** ↔ §13.5; A2 **decomposability**-residue ↔ the A1∧A2-membership entry, since it ≈ A2 itself — **not** §13.5). The status-change is analytic (M);
  it relocates nothing into/out of the two empirical loci.
- **SINGLE-SEAM / apparatus operator `𝒜:Ŝᵏ→Ŝ`.** Naming of **§2–§3 Lemma 1** (apparatus never reads S); M, same
  falsifier as the Lemma-1 / agent-derivation entry (a purely-formal operation that reads S breaks it).
- **3-axis faithfulness (edge / node / scale).** Re-expression, no new locus: **edge** `Ŝ_used⊆S` = the
  registered ⟨ii-dormant⟩ faithfulness locus; **node** (`Ĝ≠G` / imaginary waypoint) = **FM-1.b / STD-2** (node-gap
  at the posing level); **scale** (`∼_G` leak) = **STD-1**. Node+scale generate edge, so the irreducible (ii)-hook
  stays the single edge/faithfulness locus.
- **Tree/cycle goal topology (v3.9 §5: maintenance brought to parity; class-level completeness).** [known]
  control distinction (reachability vs viability/invariance, Aubin/Blanchini). v3.9 dualizes maintenance
  `Viab_S(Ω)` (safety `□Ω`) to achievement `Capt_S(G)` (liveness `◇G`) and proves completeness **at the class
  level** (Alpern–Schneider: every trace-property = safety ⊕ liveness) — M, analytic-modulo-borrowed-[known], the
  same grade as the other covering claims. The two canonical topologies are the **finitely-decidable (one-sided)
  representatives** of the two classes; goals outside them (`□◇A` recurrence) are a **named-uncovered boundary,
  NOT a falsifier**. Sharper falsifier (M-on-borrowed): a directed action outside the safety⊕liveness
  classification, or a `□◇A`-type goal the achievement-reducing generator cannot represent. Survival = degenerate
  maintenance. The graph-cycle prohibition in `D` (¬A1 via CHECK-2) is untouched.

**Consistency (anchors α, β).** (α) The new structural-completeness content (separators, 3-axis, tree/cycle) is
**M / analytic-modulo-borrowed-[known]**, the same grade as the §12.8/§13.4/§4 covering claims — no new
empirical posit. (β) The only irreducible empirical hooks remain A1∧A2-membership (§9) and Ŝ-faithfulness to S
(§2–§3); the continuous layer relocates nothing into or out of them. No new flag.

---

## Flags — claims whose falsifier is weak, missing, or instrument-limited

These are **not** hedges. Each is a precise statement of where the empirical hook is thin,
to be strengthened (named premise / built instrument), never softened.

1. **q_V one-sidedness = named priority-boundary (§24.5, §12.2, §15.2).** q_V
   senses the acceptance (false-PASS) direction of FM-3 **by design**; the false-FAIL direction is
   guarantee-safe (a false-FAIL can never fabricate an acceptance — DONE⇐PASS §14.3, AND fail-absorbing
   §11.3) and already covered (structure + T11 log). The one missing item is the *aggregated* false-FAIL
   **rate** — a diagnostic scalar (over-strict validator / griefing issuer; nets false-FAIL out of q_D
   contamination at non-atomic nodes), **not** a detection or Q-completeness gap. Buildable, deliberately
   deferred (deployment-instrumentation option, §24.5). Previously logged as "counter not built / action:
   build it"; re-leveled to a resolved-boundary — see Part III.10.
2. **|Act|=2 architectural premise (§11.2).** |L|=2 is *sourced* in A1 — a conjunction of
   two-valued predicates is two-valued, with no appeal to the action space; |Act|=2 carries only
   the **defense** against a graded scale (§11.2 "Source versus defense"). That defense is a
   *choice* (granularity → tree/FSM), argued by attribution-purity, not forced. Honest premise,
   not a gap — but the single place an objector lands. Kept named, not dissolved.
3. **CA2 single-clock (§12.8).** The operational phase **count** is now
   axiom-free (three phases = strict causal order + excluded middle; `Time.phases_exhaustive`, §27):
   CA2 is redundant for the taxonomy and single-clock is carried as a discharged hypothesis
   `SingleClock`, **not** a covering axiom. Under concurrency the trichotomy generalizes (FM-5 → race),
   it does not weaken. What remains outside the taxonomy is **verdict atomicity** = protocol
   liveness/safety dynamics (a distinct object), not axis completeness — no longer an open E3 scope
   boundary for the count. See Part III.10.
4. **FM-1.b ↔ §9 boundary subjectivity (§13.2).** The "was a foreseeable mitigation missing?"
   line is operationalized (faithfulness / domain-precedent) but the precedent threshold is
   still drawn by judgement. A principled, less-subjective criterion is an open refinement
   (does not block E1; logged).
5. **C-claims awaiting deployment (Prop 3,4,6,7,8; §25.1).** Every conditional guarantee above
   is currently corroborated only mechanically/adjacently; none has a direct deployment test.
   The premises are all named; the empirical hooks are real but unrun (E3/§26.5; E2 ran — decomposition
   convergence only, see §11 of the evidence log).
6. **Decomposition-method quality — the real blocker (§8, §7).** EXTERNALIZE *formats and
   grades* a seam but does **not** guarantee its faithfulness (Lemma 1); "how to invent a
   *faithful* seam" is the omitted method-quality layer. **E2 closed the generation procedure**
   (bare-SEARCH ⊕ gfso-AUDIT → `decompose()`, convergence to a completeness-audited reference); **seam-
   faithfulness to the real domain remains the named E3 + engineering blocker**, not a finalization residue.
   It is the located manifestation of the (ii)-faithfulness locus on the *production* side; same dormancy
   until a proxy exists.
7. **START-fold residue (§4).** The 5-link count holds modulo folding REACHES's source-
   relatum (START) into the execution-anchored present by a *stated model choice*. Reject the
   fold ⟹ the representation leg has 4 roles and the 3⊕2=5 count breaks. Honest sub-§12.8 residue
   (the analogue of CA1's value/time residue), named not dissolved; does not block, logged.

**Scope of this register.** It covers the load-bearing claims of §9–§13 (axioms, basis
minimality+completeness, |L|=2, Theorems 1–2, 7-FM completeness + independence, §12.8 CA1/CA2,
§13.4 level-exhaustiveness), §14–§15 (protocol minimality, Q minimality, Simon capacity-necessity, Chollet Level≥2 §15.3.2, AI two-components/cross-impossibility §15.3.3),
§16–§22 (Prop 3–9, §18.3 corollaries + small-gain, Theorems 10–11, §23 indispensability), §25
(stratification, Scrum embedding), §6.1–§6.2 (the [known]/[GFSO] ratio, value=making-explicit —
moved up into the canon's Part I by v4), and §2–§3
(agent derivation + predictions Pred-1/Pred-2/Pred-3, **+ v3.6 §4 5-link completeness, §8 named
boundaries, §7 methodology forced-corollaries / verify-vs-explore**). Of the
claims **enumerated here**, none has zero falsifier of any type — every entry is E, M, or C, and
the flags above are thin empirical hooks, not vacuous claims.

This is a completeness statement **scoped to the enumerated set**, not a proof that the canon
contains no unfalsifiable claim anywhere. **Deliberate omissions** (judged non-load-bearing or
expository, not silently dropped): §11.4 informativeness *commentary* beyond Inf-A / Inf-B (the
methodological framing); §23-style restatements in Abstract/§28; §25.3 comparison table; the
related-work mappings §25; STD-1, STD-3 as *prescriptions* (each guards FM-1, operationalizing
joint-sufficiency — STD↔FM is canon §13.6, so their falsifiers reduce to the FM-1 entry). **STD-2
and STD-4 are exceptions and ARE registered** (Part I): STD-2 is the admissibility line (§13.6: not
coverage), and STD-4/CHECK-7–8 is the sole instrument for FM-1.d — neither reduces to another entry. If a reader finds a load-bearing claim outside
this set, the register is *incomplete*, not *wrong* — add it.

---

## Part III.8 — v3.7 protocol rigor (§14.2–§14.4, §15.1–§15.2, §22)

> Five edits closing protocol↔FSM/metric conflicts. No new formal result; the falsifiers are **M —
> analytic on the protocol structure** (like the §10.2 minimality / §14.2 signal-minimality entries),
> except the discovered-Dep metric, which inherits the **E** hook of q_Dep.

- **Cancellation completeness (two-step handshake).** *Claim.* Cancellation is total and minimal as
  `CANCEL→CANCELLING→CONFIRM_CANCEL→ABANDONED` (+`CANCELLING→timeout→ABANDONED`); CONFIRM_CANCEL is minimal by
  FSM-deadlock (sole CANCELLING-exit); the 12 states are **complete** (analytic) and **irredundant** — the
  latter now the measured behavioural claim (eleven behaviour classes, EXECUTING ≡ REWORKING; §14.3 /
  `FsmCanon.lean`), not a bare "minimal". *Type.* M (analytic, sibling
  of the §14.2 12-signal minimality entry). *Falsifier.* A cancellation run reaching a well-defined
  terminal **without** CONFIRM_CANCEL and **without** the timeout fallback (⟹ CONFIRM_CANCEL non-minimal, drop
  to 11), OR a state reachable in cancellation that neither CANCELLING nor ABANDONED covers (⟹ 12
  incomplete). Same shape as the §10.2 "HVP expressible after deleting a primitive" falsifier.
- **Revision ≠ abandonment (no-cascade + guard set).** *Claim.* A revision (re-ASSIGN, same id — not the CANCEL signal)
  need not cascade: CHECK-1 + non-redundancy + CHECK-3 catch every staleness a cascade would have
  prevented. *Type.* M/C (conditional on the guard set). *Falsifier.* A staleness introduced by a
  revision — an orphaned `covers`, an uncovered new criterion, or a stale Dep-consumer — that **passes
  all three guards** yet corrupts V(parent). One such case ⟹ the guard set is incomplete and cascade (or
  a further guard) is required.
- **Node-identity invariant (Inv-7).** *Claim.* Stable id across revision (re-ASSIGN) is entailed (edges
  N×N orphan under re-id; the LOG, not the node, is the immutable record — T11). *Type.* M. *Falsifier.*
  A re-identifying revision that preserves all graph edges (E_D/E_Dep/mappings) intact ⟹ stability not
  entailed; OR a T11 provenance query answerable only from immutable *node* criteria (not the log) ⟹ the
  §22 relocation is wrong.
- **Discovered-Dep provenance (BLOCK→q_Dep).** *Claim.* BLOCK records a provisional discovered-Dep edge
  (RESOLVE_BLOCK adjudicates), making q_Dep non-vacuous. *Type.* E (inherits q_Dep's empirical hook).
  *Falsifier.* A deployment where surprise inter-task dependencies occur (BLOCKs on undeclared
  prerequisites) yet q_Dep stays ≡1 ⟹ the effect isn't recording them; OR discovered edges systematically
  admit misattributed (adjudicated-false) blockers into the denominator ⟹ the two-phase confirm fails.
- **Risk-ledger ≠ scope-boundary.** *Claim.* ACCEPTED_RISKS holds risk-*events* (P-bearing); a goal-scope
  boundary is a CHECK-1/criteria matter, not a ACCEPTED_RISKS item. *Type.* M (analytic on §11.2 + CHECK-1).
  *Falsifier.* A goal-scope boundary that (a) carries a well-defined materialization probability P
  feeding the §13.1 aggregate fold (⟹ it *is* a risk, category not needed), or (b) is admissible/
  inadmissible by a test **not** reducible to CHECK-1 over the goal's criteria (⟹ a genuinely separate
  mechanism is missing, not a routing clause).

---

## Part III.9 — v3.8 metric well-definedness + event-timeliness (§15.2, §21, §24.5)

> Formula-level repairs of the Q family; no new formal result. The falsifiers are **M — analytic on
> the formulas** plus the **E** deployment hooks the metrics already carry (§24.5).

- **q_D non-degeneracy (the FAIL-event formula).** *Claim.* q_D counts a non-atomic parent whose OWN
  validation returns FAIL while all its active children pass (the false-positive-D defect), at that
  event — the DONE-gated formula was identically 1 (DONE ⟹ pass ⟹ numerator ≡ denominator).
  *Type.* M + E. *Falsifier.* A live graph exhibiting the defect (parent FAIL → REWORKING with all
  active children passing) on which q_D stays 1 ⟹ the formula/instrument still misses its target; OR
  a defect-free graph where q_D < 1 ⟹ the event proxy over-fires.
- **Event-timeliness of q_T/q_Del (population = issued contracts).** *Claim.* The defect events the
  canon itself assigns (§14.6 "CHALLENGE → q_T event"; Inv-1 "re-ASSIGN with a Del change is what
  q_Del counts") are counted when they happen; a defect trajectory ending ABANDONED/ESCALATED stays
  counted (the DONE-gate dropped exactly the worst instances). *Type.* M (analytic). *Falsifier.* A
  defect trajectory expressible in the protocol (a challenged or mis-delegated node) that the new
  populations still cannot count, OR a demonstration that DONE-gating loses no defect class (⟹ the
  edit was unnecessary).
- **q_V discovery carrier (post-hoc independent validation).** *Claim.* A `validate_result` FAIL
  recorded over an already-DONE(pass/auto) node IS the "pass → later found wrong" event; q_V derives
  its numerator from that record (the discovery TRIGGER — complaint / incident / audit — stays
  external per §24.5, but a recorded discovery is counted). *Type.* E. *Falsifier.* A deployment
  where accepted-then-found-wrong results occur and get re-checked, yet q_V stays ≡1 ⟹ the carrier
  misses the event; OR post-hoc FAILs systematically mark genuinely-correct results (over-fire).
- **Named instrument gap (registered debt, §24.5):** reason-typing of revisions
  (capability_mismatch; "criteria changed for a spec defect") is NOT built; until it lands, q_Del
  over-counts (any Del change) and q_T under-counts (challenges only). (The false-FAIL aggregate is
  *not* in this debt: §24.5 — a diagnostic option on a guarantee-safe direction, not required for Q completeness.)

---

## Part III.10 — v3.9 canon-status re-levelings + machine-check + sharpened open problems (§27, §6.3, §11.2, §12.8, §26.9, §14.5, §14.3, §12.2/§24.5/§15.2)

> **No formal result changes** — statuses, attributions, and open-problem framings are corrected to the
> right level. Falsifiers stay **M/C** on the canon structure, plus one new **C** machine-checked-closure
> claim (§27). Same E/M/C discipline as above. Two of the changes — the §11.2 source/defense
> re-attribution and the §14.5 IC=seam explication — add **no new falsifier** and are not separately
> registered here (they sharpen the referent of the existing |L|=2 / IC falsifiers, not add opponents).

### Machine-checked axiomatic closure (Lean 4, §27)
- **Claim.** The formal spine type-checks in Lean-core (no mathlib, no `sorry`, no `native_decide`),
  and its whole-environment axiom footprint is **exactly three** covering axioms — CA1 §12.8, Morris
  §13.4, directed-action §4 (each *yielding a count*) — plus their uninterpreted carriers and
  Lean's own {propext, Quot.sound, Classical.choice}. CA2 (single clock, §12.8) is **not** in the
  footprint: the operational phase count is axiom-free (`Time.phases_exhaustive` — strict causal order
  + excluded middle), so totality is carried as the hypothesis
  `SingleClock`, discharged from the covering set.
- **Type.** C — conditional on the three named axioms; the guard makes the *count/identity* of the
  footprint an M-checkable invariant, but each covering axiom is itself the empirical hook.
- **Falsifier.** the closure audit goes red: a fourth `GFSO.*` axiom appears, an `opaque` / `sorryAx` /
  `native_decide` is found in any namespace, or a whitelisted axiom is discharged without the whitelist
  being updated in review. Encoding-relativity is disclosed, not a falsifier: re-encoding `|Act|=2` as an
  axiom moves the count to four *by design*.
- **Not falsified by.** A green build alone (a name collision once elaborated a definition to `sorry`
  silently) — hence the guard is fail-closed and semantic conformance stays a human job.
- **Tested?** ✅ — guard runs in CI on every `formal/` and canon change.

### §6.3 — scientific method (method core) = GFSO, domain=nature
- **Claim (structural, ◪).** A1 = the decidable form of Popper's falsifiability requirement, its two conjuncts split across the clauses — **decidability** from clause (i), **prohibition** (a non-empty fail-extension) from clause (ii) under the contingency of failure; neither entails the other (§6.3) — a condition on this theory's own domain and, **with A2**, Contact's existence-and-nontriviality condition (§2.6) — A2 supplying the κ-bounded constructibility of the input, clause (ii) being the apparatus-uncertifiable residue §2.6 names; **not** a demarcation criterion ⟹ GFSO core = the formal
  content of the method; science = a special case (domain=nature, theory-model implicit); GFSO makes
  composition / attribution / ACCEPTED_RISKS / theory-model explicit and lifts the domain.
- **Type.** structural-embedding, same family as §25.2 (Scrum ⊂ GFSO).
- **Falsifier.** exhibit an element of the *method* (not institution, not theory-choice, not
  the cardinal / graded-confirmation layer — a test with a fixed rejection rule is an **instance** of the criterion↔truth split, §6.3, not an exclusion) not expressible in GFSO; or a generative contribution to discovery beyond the
  EXTERNALIZE-form; **or a rival faithful decomposition that science's method orders but GFSO's structural
  rankers cannot** (a consilience-choice where unification and `E_FAITH` come apart); **or an interventionist
  formulation of the Pragmatic-level claim that is also verifiable from inside the apparatus**, which
  would collapse the formulation/verification split of §6.3.
- **Status.** ◪ — **adversarial search RUN** (nine slots: prediction/accommodation, novel-fact,
  consilience, explanation/causation/IBE (D-N; interventionist), measurement, replication, theory-ladenness, causal discovery,
  research-programmes/paradigms): **no escaping method-primitive** — each candidate is either caught by
  existing structure (theory-ladenness = SINGLE-SEAM; explanation = composition + the L1/L2 gap; Lakatos's
  correction *dynamics* = backward-attribution + `Λ·γ`) or folds into exactly **two already-named
  remainders** (causal L2 / §8; one graded-confirmation import — where Lakatos's normative *verdict*
  progressive-vs-degenerating also lands) or the §8 discovery boundary / the ¬A1 domain — where **causal discovery** lands: an approach vector to the causal boundary that does not close it, presupposing the carve (CONSTRUCT-Ŝ), which *is* that boundary. Survives under **two named
  presuppositions** (the mapping covers the method only where it has a decidable result / A1; and a
  stable exogenous S + fixed A1 standard ⟹ a rational-reconstruction reading against strong
  incommensurability). Core analyticity and the absence of a *behavioral* claim (that GFSO *generates*
  scientific practice) are preserved. Residue routes to §8 (discovery) — shared with science.

### §26.9 reformulation — basis uniqueness as bi-interpretability (basis side only)
- **Claim.** Uniqueness of the basis is now posed as: is σ = ⟨T,D,Dep,Del⟩ *canonical up to
  bi-interpretability* on Mod(A1∧A2) — i.e. is every adequate signature bi-interpretable with σ?
- **Type.** M (a bi-interpretation is a mathematical object to exhibit/refute) **conditioned on C**
  (the admissible-signature class is undelimited).
- **Falsifier (M).** exhibit an adequate σ′ **not** bi-interpretable with σ.
- **NB — the PROTOCOL side does NOT share this currency (§26.9(b)).** On finite transition systems
  bi-interpretation is vacuous (every adequate protocol is rigid), so protocol uniqueness is posed in
  **behavioural equivalence** instead; its entry is the "Protocol minimality" block in Part I. This
  entry is basis-only.
- **Un-closable-from-within caveat (C).** even this needs the class of *admissible signatures*
  delimited (the "wall": completeness of the markup itself quantifies over an undelimited candidate
  space) — so the reformulation makes the *form* of an answer checkable (a bi-interpretation) and names
  *where* the undecidability sits, without settling it.
- **Two escape routes pushed — wall narrowed to one frame-locus (M/C).** The two candidate falsifiers
  §26.9 itself names are pushed through and neither survives. **(second-order — Dep-reachability Dep\*)**
  under **FO** it is inexpressible (FO ≠ FO+TC, Immerman) ⟹ σ does not interpret σ∪{Dep\*} ⟹ not
  mutually-interpretable ⟹ Dep\* is an *addition*, not an equivalent re-coordinatization ⟹ **not adequate
  ⟹ not a falsifier**; under **FO+TC/MSO** it is **definable-redundant** ⟹ bi-interpretable ⟹ **not a
  falsifier** (Beth is irrelevant here — the definability is direct, not via Beth). **(factor
  interpretations, mutual ≠ bi)** the gap opens only under many-sorted/quotient or weak adequacy; under
  strong adequacy Beth-both-ways ⟹ bi, and no witness for organizational primitives is exhibited. Both
  routes stream into a **single** frame-locus — the unforced FO-vs-FO+TC / same-domain stipulation — so
  the wall is **narrowed and pinned** to that one screw, not the generic "any delimitation is circular".
- **Partial result (M, Beth-class).** Over first-order, same-domain, parameter-free signatures τ that
  are L_σ-definable and structure-determining (σ implicitly definable over τ), σ is canonical up to
  definitional equivalence by **Beth's definability theorem** — decidable as a finite case-split under
  bounded quantifier rank; the dual of §10.2 minimality. **Falsifier:** exhibit such a τ that determines
  σ yet is *not* bi-interpretable with it. Residue: σ-centric, first-order/same-domain (excludes
  second-order primitives like Dep/D-reachability, and quotient interpretations), strong-adequacy reading.
- **Status.** ◻ — the Beth-class sub-question is *closed* (partial result above) and the two escape
  routes are pushed (wall narrowed to a single frame-locus, above); **global** uniqueness stays open
  exactly there — at the frame boundary (unforced choice of axioms / FO-vs-SO — the §9/§2–§3 empirical
  locus). The live falsifier is only an **adequate non-bi-interpretable σ′ under FO + same domain**, not
  exhibited. Minimality M proven (§10.2).

### §12.8 CA2 — discharged from the covering set (amends the §12.8 CA2 entry / Flag 3)
- **Claim.** The three operational phases (before / concurrent / after) are a partition by a strict
  **causal** order under excluded-middle — **zero assumptions**; neither a single clock nor per-event
  atomicity is needed. Single-clock only collapses the middle cell to "during `[s,e]`"; under
  concurrency FM-5 **generalizes** to a read/write race, it does not weaken. Atomicity buys a **clean
  verdict** (protocol dynamics), not taxonomy completeness — and a torn read is itself a failure mode
  (FM-3/FM-5), inside the taxonomy.
- **Type.** M — the phase count is axiom-free (`Time.phases_exhaustive`, §27); the residual
  single-clock cost is now a discharged hypothesis, not a covering axiom.
- **Falsifier (M).** a real evaluation whose event-timing relative to `e` is none of {wholly-before,
  concurrent, wholly-after} → the excluded-middle partition has a hole; or a concurrency failure that
  is a genuinely new mode outside the 7-FM taxonomy.
- **Supersedes.** the earlier "single-clock scope boundary routed to E3" framing (CA2 (i) entry /
  Flag 3): the *count* no longer depends on a clock. What remains outside the taxonomy is verdict
  atomicity = protocol liveness/safety dynamics (a distinct object), not axis completeness.
- **Tested?** — analytic (machine-checked axiom-free, §27).

### Cancellation irreversibility = design boundary (§14.3)
- **Claim.** From the contract guarantee only **non-arbitrariness** of any admissible reversal is
  forced (issuer-authorized + counter-bounded + append-forward); terminality of ABANDONED is a
  *conservative implementation* R (zero in-protocol reversals trivially excludes arbitrariness), **not**
  a theorem. A bounded authorized REOPEN (R′, `max_reopens`) is guarantee-compatible and is a **named,
  parked** extension (undo/rollback-along-log + finality), not the base.
- **Type.** C — a declared design decision under the named guarantee premise.
- **Falsifier.** the guarantee premise is the hook: a contract useful as a guarantee whose terminal
  outcome is nevertheless arbitrarily revocable by any party at any time without losing its value → the
  non-arbitrariness derivation is wrong. (Terminality itself is not an empirical claim — it is the
  conservative implementation R; refuting "terminality is forced" is *not* a falsifier, because bounded
  REOPEN R′ is guarantee-compatible by construction.)
- **Finality (R′ semantics, §14.3).** A terminal outcome is *locally reversible* (bounded authorized
  REOPEN) ⟺ un-consumed in-graph AND reopens-remaining; **final** (loss of *local* reversibility) ⟺
  consumed OR `max_reopens`-exhausted. Consumption is derived — reversal goes non-local through AND/Dep
  (positive) or the settled cascade (negative). No consensus is imported: single-Del authority + a
  single-sequencer append-only log answer "who may reverse" and "which history is canonical"; the
  blockchain machinery (fork-choice, Sybil-resistance, quorum) is only what an adversarial/permissionless
  setting would import. REOPEN reuses re-ASSIGN over a new quasi-terminal→OFFERED edge (DONE→OFFERED positive / ABANDONED→OFFERED negative, §14.3) — not a 13th signal —
  gated by the consumption-check and `max_reopens`.
  - **Falsifier (M).** a terminal that is un-consumed yet must be final, or consumed yet must stay
    *locally* reversible, not reducible to a post-hoc pass→later-fail (§24.5) or an out-of-graph side
    effect (§24.6).
  - **Two residues.** (1) consensus-free finality is contingent on non-adversarial agents (§24.2) +
    single-Del; drop them and a consensus layer must be imported. (2) anti-fake inherits the false-PASS
    residue (§24.5): REOPEN→OFFERED removes the *stale-verdict* surface but earns correctness only through
    the verifier≠executor seam + q_V, no stronger.
- **Status.** ◻ resolved-boundary — base = R (terminality; recovery by re-decomposition), extension R′
  with a derived finality criterion (consumption ∨ counter-exhaustion); not a cascade-rollback (a cascade
  is non-local once settled). Protocol unchanged (no 13th signal).

### q_V one-sidedness = named priority-boundary (§24.5)
- **Claim.** q_V senses the acceptance (false-PASS) direction of FM-3 by design; the false-FAIL
  direction is guarantee-safe (a false-FAIL can never fabricate an acceptance — DONE⇐PASS §14.3, AND
  fail-absorbing §11.3) and already covered (structural CHECK-2/T1 for co-occurring FM-4; A1 for
  non-determinism; T11 log + §24.2 threat-model for systematic griefing).
- **Type.** C — resolved-boundary.
- **Falsifier.** exhibit a false-FAIL that is a defect of *acceptance* reliability and is NOT reducible
  to efficiency / a separate FM-4 / an A1 violation.
- **Residue (buildable, deferred).** no *aggregated* false-FAIL rate in Q — a diagnostic scalar
  (over-strict validator / griefing issuer; nets false-FAIL out of q_D contamination at non-atomic
  nodes), not a detection or guarantee gap. Distinct from the permanent §8 false-PASS boundary.
- **Status.** ◻ resolved-boundary. (Re-levels Flag 1 below: the counter is a diagnostic option, not a
  completeness debt.)

---

## Provenance

The systematic falsifiability pass referenced by canon §26; tracks canon **v4.0** — every §-citation
below is anchored to the v4.0 chapter numbering (the re-anchoring the canon's own policy called for on
acceptance). The Part III.N headings keep their version labels: they record *when* a claim entered the
register, not where it now lives. Originally written against v3.5, then
extended for the v3.6 agent-free-ontology + methodology layer (§6.1–§6.2, §4, §8,
§7) in Part III.6, the continuous-substrate + 3-axis-faithfulness layer (§5, with its seam half at §2.3–§2.6) in Part III.7,
the v3.7 protocol-rigor edits (§14.2–§14.4, §15.1–§15.2, §22) in Part III.8, the v3.8 metric
well-definedness/event-timeliness edits (§15.2, §21, §24.5) in Part III.9, and the v3.9 canon-status
re-levelings + Lean machine-check (§27, §6.3, §11.2, §12.8, §26.9, §14.5, §14.3, §12.2/§24.5/§15.2) in
Part III.10).

> *Label note (v3.6).* The §2–§3 **predictions** are tagged **Pred-1/Pred-2/Pred-3** (substitutability /
> applicability boundary / global falsifier) to keep them disjoint from canon's reserved **P3** (Blackwell,
> Prop 3 §16.2) and from the agent-necessity **derivation steps d1–d6** (§2–§3). Three distinct series, no
> token collision.
On any canon ↔ register disagreement, the canon is authoritative and this file is corrected.
