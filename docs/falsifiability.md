# GFSO — Falsifiability Register

> For every load-bearing claim of the canon (`applied_gfso_v4_en.md`): its name and §, its type, and
> **what observation or counterexample would falsify it**. This is the register the README refers
> to.
>
> **Companion, not a replacement.** A claim's text lives only in the canon; an entry names it with its § and
> adds what the canon does not carry — the type, the falsifier, the test status. On any disagreement, the
> canon wins and this file is fixed.

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

A **C**-claim is not a hedge: the premise is named and is itself testable. "Holds under (ii)-faithfulness"
is a strong conditional, and its violation is a *characterized* in-framework failure (§20.2), not an
external gap.

An **M**-claim is not "vacuous because definitional": a characterization theorem (e.g. Theorem 1) is a
real result; its falsifier is mathematical (break the case split), not empirical. Conflating "analytic"
with "empty" is the error the register is built to avoid.

Legend in the "Tested?" column: ✅ a falsification attempt was run and the claim survived ·
✅\* survived, but only under a named, still-movable classification line (not fully independent of
what it validates) · ◪ an adversarial search was run over a structural embedding · ◻ falsifiable but
not yet tested · — analytic (M), no empirical test applies.

Each entry: **Claim** — the claim's name and its home §; **Type**; **Falsifier**; **Tested?**.

**What this register is.** An **anti-vacuity ledger**: for every load-bearing claim it names the
would-be refuter, and flags any claim that has none — the prohibition requirement, the surviving core of
falsifiability (§19.7) — **not** a criterion demarcating science from non-science, an office this
register never holds (§19.7). The E/M/C typing extends the requirement past Popper's *empirical* scope —
admitting a mathematical refuter (M) and a premise-conditional claim (C), while holding the premise itself
to the same requirement — which **names and costs** the immunizing use rather than barring it: where a
premise's own falsifier is dormant (the (ii)-faithfulness flag), the requirement is declared, not enforced.

---

## Part I — The apparatus: axioms, basis, validation, failure modes, standards (Ch. 1–2, 7–9)

> *(This register's own Part numbering; the canon has none. The foundation these chapters follow
> from, canon Ch. 3–6, is registered in this file's Part III below.)*

### A1, A2 (axioms, §1.2)
- **Claim.** A1, A2 (§1.2); the boundary claim, the model needed iff A1 ∧ A2 (§2.1), which Pred-2 sharpens (§4.6).
- **Type.** E — of **domain membership**. The axioms themselves are definitional postulates (§1.2, §20.5
  kind (b)); what can be wrong is that a domain meets them and that the protocol then describes it. GFSO
  asserts the protocol *where* A1 ∧ A2 hold, not that they hold everywhere; a goal outside the model is the
  domain-form boundary (§20.1, §20.3).
- **Falsifier.** A domain that **satisfies A1∧A2 yet is not describable as GFSO handoffs** (falsifies the
  "describes" claim of §2.1, with §7.5's completeness — a search-backed claim). A domain asserted in-scope
  that has no decidable criteria even in principle (¬A1) belongs *outside* — misclassifying it is a boundary
  error, not a falsifier of the axioms. Of the boundary claim: a goal governed successfully by GFSO handoffs
  where A1 demonstrably fails, or one above capacity with no split into parts within it; or an A1∧A2 domain
  GFSO cannot describe.
- **Tested?** ◻ partially — E1's 216 incidents are all A1∧A2 domains and all map (`EVIDENCE_LOG`); no in-scope case
  escaped the framework.

### Minimality of the basis {T, D, Dep, Del} (§7.5)
- **Claim.** Basis minimality (§7.5 "Minimality"); global uniqueness is not claimed — the carve wall (§20.7).
- **Type.** M (constructive — §7.5's counterexample table). Only minimality is claimed proven.
- **Falsifier.** (a) An HVP fully expressible after deleting one of the four → that element not necessary.
  (b) A primitive irreducible to {T,D,Dep,Del}, derivable from A1∧A2 → basis incomplete — the live one; that
  none exists is §20.7's global uniqueness question, shown not derivable from inside (§20.7).
- **Tested?** — analytic; the §7.5 table is the proof. No fifth primitive found to date (search, not proof).

### Basis completeness / axiom-exhaustion (§7.5 "Completeness")
- **Claim.** Basis completeness (§7.5 "Completeness") — the axioms' exhaustion by the basis, and the
  search-backed absence of a fifth primitive, whose global form is the basis's uniqueness (§7.5, §20.7).
- **Type.** E/M — the exhaustion derived (§7.5); the absence of a fifth primitive a coverage claim over the
  (informal) space of organizational primitives, search-backed, not derived (§7.5); a strict proof would need
  that space delimited (§20.7, the covering form).
- **Falsifier.** A canonical org-concept that is **both** (a) genuinely inexpressible via
  {T,D,Dep,Del,V} **and** (b) forced by A1∧A2 — a real gap, not a relabeling of an existing
  primitive. (A concept expressible after re-encoding is not a falsifier.)
- **Tested?** ◻ — corroborated only by the §7.5 reductions; no adversarial search for a missing primitive
  has been run.

### |L| = 2 — binary validation (§7.1)
- **Claim.** |L| = 2 (§7.1 "The scale") and its defense against a graded scale (§7.1, `Binarity.L_forced_two`).
- **Type.** M. The *source* is A1 (§7.1 "The scale"). The *defense* rests on |Act| = 2, a covering axiom
  (§7.1, §20.5), with injectivity forced by decision-relevance (§7.1). Sourcing the scale in A1 does not make
  |L| = 2 "derived from nothing" — it moves the load-bearing assumption from |Act| = 2 to A1 and leaves
  |Act| = 2 carrying only the defense.
- **Falsifier.** A **decision-relevant** validation outcome that maps to neither `intervene`
  nor `¬intervene` and cannot be relocated into tree-granularity or FSM-state — i.e. a third
  action on a single node that genuinely changes the trajectory in a way the binary split
  cannot encode. (A merely *informational* third value is not a falsifier — Inf-B, §7.4.)
- **Tested?** — analytic. |Act| = 2 is where an objector would push — but pushing there reaches the
  *defense* only; the scale itself would still stand on A1. The register records |Act| = 2 as a *named
  covering principle* (§7.1, §20.5), not a proven necessity.

### Theorem 1 — compositionality V(parent)=AND(V(children)) (§7.3)
- **Claim.** Theorem 1 and its characterization (§7.3).
- **Type.** M — a **characterization**, analytic given a correct decomposition (§7.3).
- **Falsifier (mathematical).** A correct decomposition (both conditions met) where the
  equivalence fails — excluded by the proof; finding one means the proof is wrong.
- **Empirical content lives elsewhere.** Whether a *real* decomposition is correct is not Theorem 1 but its
  causal correctness (§7.3 "Causal correctness"), the Pragmatic-level boundary (§20.2), falsified by a
  backward signal: the children's criteria holding on the delivered result, the parent undelivered. The
  integration cases give **three distinct falsification signatures**, which fault different claims — (i) the
  coverage hole, (ii) the insensitive edge, (iii) the refuted edge, each with the mode §8.7 names, a denial not
  obtainable at the fixing routed by §8.6 (§8.7).
- **Tested?** — (theorem) analytic; (correctness-in-practice) ◻ E3 territory.

### Theorem 2 — AND uniqueness (§7.2)
- **Claim.** Theorem 2 (§7.2).
- **Type.** M (exhaustive enumeration of 16 operations).
- **Falsifier.** A second operation satisfying all of §7.2's requirements and nontrivial → the enumeration erred.
- **Tested?** — analytic.

### Informativeness — decision-relevant completeness (§7.4, Inf-A / Inf-B)
- **Claim.** Inf-B (§7.4) — what licenses |L| = 2 against the "continuous is richer" objection; Inf-A (§7.4).
- **Type.** C — Inf-B is derived relative to |Act| = 2 and decision-relevance (§7.4, §7.1).
- **Falsifier.** A **decision-relevant** bit inside the continuous surplus — a case where the
  magnitude (not just pass/fail) of a single node's score changes the intervene/¬intervene
  action *without* that distinction being relocatable into tree-granularity or FSM-state. That
  would show binary V drops decision-relevant information.
- **Tested?** ◻ — analytic under the model; no empirical probe that surplus is ever
  decision-relevant on real tasks.

### 6 Failure Modes — completeness as a basis (§8.8, §8.2)
- **Claim.** Completeness as a basis (§8.8 "Theorem (completeness as a basis)"); a basis, **not** a partition
  (§8.2 CA1, §8.8 "Corollary").
- **Type.** **M (analytic), modulo its covering axioms** — graded *(covering axiom)* at §8.8: the external case split derived (§8.6 "External
  completeness"), the internal one a covering axiom (§8.5 "Internal completeness"), CA1 argued (§8.2 "No third
  axis"), its thin residue local and around the canon (§20.9). The single clock is **off** this residue
  (§8.2, §20.5). Not a standalone empirical posit.
- **Falsifier (mathematical).** A failure the case split does not route to any Cᵢ → the split,
  or §8.2's argument for CA1, has a hole. This is an *analytic* falsifier (find the
  hole), not an empirical posit about the world.
- **Empirical content is only *synthetic adequacy* (CA1 entry).** The single thing E1
  exercises: do **real** failures instantiate the *derived* categories with no remainder? That
  is corroboration of the derivation's adequacy-to-phenomena (categories a priori, their fit to
  experience synthetic) — not a test of structural validity. See the CA1 entry.
- **Tested?** — analytic; the adequacy corroboration (E1 0/216) is logged on CA1.

### FM independence (§8.8)
- **Claim.** Independence (§8.8 "Independence"); the verdict face of each lone violation (§8.9).
- **Type.** M (constructive — the §8.8 scenario table) with E corroboration.
- **Falsifier.** An FMᵢ that cannot occur without some FMⱼ (always co-occurs **necessarily**, not
  just frequently) → not independent; the basis dimension is < 6. Or an FMᵢ whose violation, the
  other five held, can never deny a used edge → the rest suffice and FMᵢ is redundant. Independence is
  *isolability*, established by the §8.8 scenarios (each FM realized alone) — an **M** claim.
- **Tested?** — analytic (the §8.8 scenarios are the witnesses). E1's secondary-FM rate (`EVIDENCE_LOG`) is
  **orthogonal** to independence (co-occurrence neither confirms nor threatens isolability); it is evidence
  for *basis-not-partition*, **not** for independence. No ✅ here — there is no falsification attempt
  specific to isolability.
- **Falsifier met, and the claim restated (2026-09-25/27).** With a failure read as a wrong verdict and every
  condition read at the evaluation, FM-1 ∧ FM-3 ∧ FM-4 already gave a correct verdict (Thm 1's own proof), so
  FM-2, FM-5 and FM-6 could not yield a wrong verdict alone — the redundancy this entry's falsifier names. The
  claim now stands on the failure root (§8.1) and on where each condition is read (§8.6); FM-2's harm is the
  route, not the verdict (§8.9).
- **Falsifier met for a seventh mode (2026-09-27) — withdrawn.** The after phase holds no condition (§8.6 "The
  after phase"), so the seventh mode's violation, the other six held, never denied a used edge — this entry's second
  falsifier. What it named is a requirement on the protocol (§12.14), not a condition on the computation;
  the basis is six (§8.8). It had been hidden by reading the verdict on the world as it stands after the
  evaluation, which §1.3, §6.9 and §11.3 do not allow.

### §8.2 CA1 (Evaluation Completeness — "no third axis") — *argued, and still an axiom; E1 corroborates its adequacy*
- **Claim.** CA1 (§8.2).
- **Type.** **M — an *argued* covering axiom**, an axiom still because its argument narrows the candidate
  space without delimiting it (§8.2 "No third axis"), its thin residue named there, the
  single clock **off** it (§8.2, §20.5). So this is **not** the "flagship empirical claim" an earlier draft
  called it — it is analytic-with-a-residue, and what E1 touches is its *adequacy to phenomena*, not its
  validity.
- **Falsifier (M).** A real in-scope failure that is **neither** a defect of what-is-computed
  **nor** of when/how-it-executes — a third evaluative degree of freedom of a single result,
  surfacing as a genuine **mode outside the six** (not §9.3-extraordinary, not §16.15-adversarial, not a
  resilience-success). One such incident would mean the §8.2 derivation has a hole (the two axes
  do not exhaust the unit) — an analytic defect exposed empirically (synthetic-adequacy failure).
- **Tested?** ✅\* **E1: 0/216 incidents need a mode outside the six** (`EVIDENCE_LOG`) — corroborates the *adequacy*
  of the derived basis to real failures (✅\* = survived, but under the movable line below; it confirms a
  derivation, it does not test an empirical posit). Read precisely: this is the figure **after** the v3.1
  root-cause re-triage of the 17 raw NONE (EVIDENCE_LOG §9.1), which moved 11→FM (mostly FM-1.b), leaving
  **6 non-FM cases** = 3 resilience-worked (= evidence-FOR) + 3 delegated-to-third-party. The 3 delegated are
  **in-framework either way** — an admitted risk (its bite FM-5's or FM-6's, §9.3) or FM-1 (an entry missing,
  or one the register does not admit) — never a mode outside the basis (EVIDENCE_LOG §9.1 final positioning).
  Headline numbers: **out-of-scope residual = 0, domain edge (§20.3) = 0** (`EVIDENCE_LOG`). **The partly-subjective
  step is that re-triage, and it does not bear on the count:** the **FM-1.b ↔ extraordinary line (STD-2 entry
  below / Flag 4)** moves a case only within the basis (§9.3), never outside it, so 0/216 does not depend on
  where it is drawn; what the line decides is attribution — the decomposer's FM-1.b or a ground the split
  could not see. Strongest empirical *corroboration* in the canon (of a derived structure's adequacy, not of
  an empirical posit), with that caveat named.

### §8.2 CA2 (operational axis; single clock discharged) — two halves
- **Claim.** The operational axis and CA2's redundancy (§8.2); the machine's composition of several
  evaluation events (§12.4).
- **(i) Phase count is axiom-free.** Type **M** — machine-checked (`Time.app_phases_exhaustive`,
  `Time.app_phases_disjoint`, §20.5; `Time.phases_exhaustive` its single-event case in `Time.lean`).
  **Falsifier:** a real evaluation event whose position relative to the application [f, e] is none of
  {wholly-before, concurrent, wholly-after}. What remains
  outside the taxonomy is verdict *atomicity* (§8.2 "Atomicity"; (ii) below), not axis completeness.
  *(Supersedes the earlier "single-clock scope = cost, routed to E3" framing; see Part III.10.)*
- **(ii) FSM-composes-events.** Type **M.** Falsifier: an **in-scope** re-entrant validation
  (a real DELIVER→FAIL→REWORKING cycle, single clock) that the per-event atomicity does **not**
  cover — i.e. a validation episode the FSM cannot decompose into covered events. That breaks
  the composition half *inside scope*, independently of the distributed boundary. Tested? —
  analytic (the §12.4 FSM cycle is the constructive witness).

### §9.1 — three levels of verifiability are exhaustive ("no 4th dimension")
- **Claim.** The three verification levels and their exhaustiveness (§9.1).
- **Type.** **M — modulo the named covering axiom CA-Morris** (`morris_trichotomy`; §9.1, §20.5), **below
  CA1's grade**: inherited by citation, with no argument of its own narrowing the candidate space (§20.5,
  §20.7). The axiom is named, not hidden.
- **Falsifier (M).** A real verifiability question about a decomposition that is **none** of
  structural (L0) / formal-implication (L1) / causal-pragmatic (L2) — a fourth kind of check →
  the Morris trichotomy / its application here has a hole.
- **Tested?** — analytic; adequacy not tested: E1 surveys failure modes, and a fourth kind of verification
  knowledge would not surface as an uncovered failure (E1 bears on CA1 only).

### STD-2 — predictability admissibility (§9.3, §9.10) — *the FM-1.b ↔ extraordinary hinge*
- **Claim.** STD-2 (§9.3) — the admissibility criterion deciding **whether** a non-coverage of a written criterion's outcome is FM-1.b or a
  licensed omission (an outcome no criterion states being FM-1.f's question, read on the requirement), not a coverage standard (§9.3, §9.10), with FM-1.b's test (§8.3 "FM-1.b and the
  extraordinary"). It carries falsifiable content that does **not** reduce to any FM entry, so it is
  registered as a first-class claim: the line Flag 4 hangs on, deciding attribution inside the basis, not
  CA1's adequacy (E1 above).
- **Type.** E/C — operationalized as §8.3's domain-precedent / faithful-map test.
- **Falsifier.** An incident where the domain-precedent test classifies a missing mitigation as
  **FM-1.b** yet **no** faithful Ŝ could have carried it (truly no S-regularity to be faithful to)
  — or the converse (genuinely extraordinary by the test, yet a standard mitigation existed). Either
  shows the predictability burden-of-proof line is mis-drawn.
- **Tested?** ◻ — and **only as sharp as the precedent threshold (Flag 4)**, which is currently
  subjectively drawn; it decides whether a bite is charged to the decomposer, not whether the basis covers it.
  The burden-of-proof shift (§9.3) is the structural content; the *threshold* is the open empirical residue.

### STD-4 / CHECK-7–8 — formal sufficiency & consistency instruments (§9.5–9.6)
- **Claim.** CHECK-7 and CHECK-8 as instruments (§9.6) for FM-1.d's apparatus face and FM-2's formal half;
  CHECK-7 the a-priori test of FM-1.d (§9.10). Registered separately because it does *not* reduce to another
  entry — unlike STD-1/3.
- **Type.** M-constructive (the §9.6 decidability table is the witness).
- **Falsifier.** A decomposition that CHECK-7 **mis-adjudicates** — passes an under-entailing split
  (children formally fail to entail cᵢ yet CHECK-7 says ⊨) or rejects a sound one; or a CHECK-8 that
  certifies mutually-unsatisfiable children criteria as consistent. Either breaks the instrument's
  soundness.
- **Tested?** — analytic (decision procedures); ◻ no empirical run of CHECK-7/8 against a corpus of
  real decompositions. (E3-adjacent: decompositions HAVE now been GFSO-checked end-to-end on a
  third-party benchmark — EVIDENCE_LOG §13, calibration tier, and §13.6 measures the Level-2 gate's
  discrimination on PLANTED holes. Neither is the corpus run this row asks for.)

---

## Part I.5 — Protocol, graph, AI-layer (Ch. 11–13, 15, 17)

### Protocol minimality — 12 signals, 11 states, 8 invariants (§11.4, Ch. 12)
- **Claim.** Signal minimality and the deletion table's typing of each removal (§11.4,
  `Protocol.defect_distribution`). ACCEPT_CHALLENGE is IC, not FM-5 (§11.4; corrected 2026-08-04).
- **Type.** M (constructive — the deletion table).
- **Falsifier of the split specifically.** A signal whose removal leaves a defect of a class other
  than the one the table assigns it — as ACCEPT_CHALLENGE itself did until its correction; the
  count is machine-checked, so a canon/Lean divergence is caught by `check_claims` (the split is
  read off §11.4's count line at every run).
- **Falsifier.** A P2P signal whose removal causes **no** defect of any of the four kinds (its
  function is covered by the remaining signals) → the set is not minimal. Symmetrically, a
  necessary signalling need with **no** signal addressing it → not complete.
- **Uniqueness is NOT CLAIMED (§13.6).** Minimality is claimed; uniqueness — in behavioural equivalence, the
  currency §13.1 fixes — is not, globally the carve wall (§20.7). **Over bare adequacy it is settled
  negatively:** the falsifier is exhibited (§13.2, `FsmCanon.variant_*`). What is left — uniqueness over a
  fully pinned design vector — is the same wall as basis uniqueness (§20.7). The inner enumeration over the
  fixed alphabet is finite and distinct from that walled outer completeness: the removals' grades (§11.4,
  machine-checked as far as §20.4 lists them), the backbone (§13.3), the cells pinned by Inv-4's reading — a
  design decision (§12.9, §13.3) — and REWORKING ≡ EXECUTING (§12.11). Over bare adequacy the rows force roles,
  not distinct states (§13.3); the states are forced over the log (§13.4), **falsified by a second machine
  meeting its principles**. Whether the log's class of conditions is natural is around the theory (§13.6,
  §20.9). Not a rival: a protocol differing only in `max_iterations`'s value, one protocol with different
  payloads (§12.3, §12.14). Type M. Mirrors the basis minimality-vs-uniqueness split (§7.5 / §20.7).
- **The machine forced over the log (§13.4, `LogLanguage.lean`).** *Claim.* §13.4's forcing, relative to its
  conditions, with the missed bound counted as a channel (`LogLanguageLapse.lean`) and R′ (§13.5,
  `LogLanguageReopen.lean`). *Type.* M (kernel `decide`; loads per clause by exact count). *Falsifier.* A deterministic machine over that vocabulary meeting every listed
  condition and differing from the table in one reachable cell; or a listed condition whose removal leaves no
  cell open (it carries nothing). *Scope.* §13.6.
- **State irredundancy — machine-checked (§12.11, §20.4, `FsmCanon.lean`).** *Claim.* Ten behaviour classes
  over the eleven states (§12.11, §20.4; over the log eleven, derived, §12.11). Type M, machine-checked
  (axiom-free `decide`, with a negative control). Falsifier: two named states other than {EXECUTING,
  REWORKING} behaviourally equivalent over the §12.4 table. This is *irredundancy*, not state **completeness**
  ("no twelfth state") — analytic relative to the alphabet (§12.1) and not touched by this measurement.
- **Tested?** — analytic (signal minimality); state irredundancy machine-checked; uniqueness not claimed —
  globally the carve wall (§20.7, §13.6).

### Q minimality & independence — 5 metrics ↔ the 5 components of the tuple (§15.4)
- **Claim.** Q's minimality and independence (§15.4).
- **Type.** M (constructive — the blind-zone + independence tables).
- **Falsifier.** A q-metric reconstructible from the other four (not independent), or one whose
  removal opens no blind zone → minimality fails. A defect class no q-metric counts is no falsifier:
  Q claims minimality, not coverage; false FAIL is outside q_V by design decision (§15.4, §20.5 (d)), a
  false FAIL over passing children charged by q_D to the split (§16.9, exception 1).
- **Tested?** — analytic; ◻ the *predictive* value of each q vs real outcomes is open (§15.8).

### AI-layer capacity necessity — Simon t\* (§17.1)
- **Claim.** Capacity necessity (§17.1), under its named premise there — distinct from Ch. 4's
  *provenance* necessity (§17.8); the register lists both, they are separate.
- **Type.** E (contingent on real organizations actually crossing t\*).
- **Falsifier.** A non-trivial organization whose accumulated decision-relevant information
  stays permanently within unaided human capacity (no t\* is ever reached) → the capacity
  argument is moot for that class. (This falsifies the *necessity-in-practice*, not the
  conditional "if |I| exceeds capacity then AI needed", which rests on that premise.)
- **Tested?** ◻ — no measurement of |I| growth vs human capacity on a real deployment.

### §17.2 — Chollet Level ≥ 2: capability-class requirement on the LLM
- **Claim.** The LLM's Level ≥ 2 requirement and its "a generalization more training data does not buy" (§17.2).
- **Type.** E — an empirical requirement on the deployed model class.
- **Falsifier.** Either (a) a model demonstrably **below** Level 2 that nonetheless discharges the
  §17.2 role (reliable adaptation to a real org's D_org ∉ D_train) → the requirement is not
  load-bearing; or (b) evidence that scaling D_train **alone** lifts a model into the role → refutes
  "a generalization more training data does not buy".
- **Tested?** ◻ — not run as a GFSO deployment test; adjudicable against frontier models on
  out-of-distribution org task distributions (§20.10). (The realization mechanism, §17.2, is a *how*, not
  the falsifier of the *requirement*.)

### §17.2–17.3 — AI-layer two-components + cross-impossibility (minimality)
- **Claim.** The two components (§17.2) and their cross-impossibility (§17.3).
- **Type.** M for the minimality (cross-impossibility, §17.3) — same family as protocol-minimality (§11.4)
  and Q-minimality (§15.4); the exhaustiveness is a covering placement by citation of Peirce's three
  inference types, carried by no Lean axiom (§17.2, §20.5, §20.7) — not M.
- **Falsifier.** A single component discharging **both** roles (formal-soundness guarantee AND domain
  generalization), or a necessary **third** component irreducible to the two → the 2-component
  enumeration erred.
- **Tested?** — analytic.

### §17.7 — safety-net incompleteness (irreducible domain-silent false-PASS)
- **Claim.** The safety net's incompleteness (§17.7) — the operational face of the Pragmatic-level boundary
  (§20.2). A *negative* claim, the canon's most-cited limitation.
- **Type.** M/structural — it *reduces* to the FM-3 / §20.2 / Theorem-1-correctness entries (registered
  above); listed explicitly because the canon leans on it constantly.
- **Falsifier.** A purely-formal apparatus (no execution, no agent contact) that **does** detect a
  domain-silent false-PASS → contradicts Lemma 1 (§3.4).
- **Tested?** — analytic (same status as the Lemma 1 derivation it follows from); the false-FAIL share,
  outside q_V and a diagnostic (§15.4; Flag 1), is the nearest empirical edge.

## Part II — Main results (Ch. 16; §15.6, §11.6, §17.9)

> **Shared caveat — the (ii)-faithfulness proxy is dormant (applies to every claim tagged
> ⟨ii-dormant⟩ below).** Several results below hold *under the (ii)-faithfulness discipline* (Ch. 4,
> §20.2). That discipline has **no operational outcome-independent proxy yet** (same gap as §4.6
> Pred-1/Pred-3 and Flag 4). So a decline can always be re-attributed to a faithfulness break (in-framework,
> §20.2), and the claim's empirical falsifier **cannot currently fire** — it is non-adjudicable until a proxy
> instrument exists, *identically* to Pred-1/Pred-3. This caveat is propagated uniformly: a
> (ii)-conditioned claim of Ch. 16 is no more testable than the §4.6 predictions.

### Prop 3 — Blackwell information dominance (§16.2)
- **Claim.** Prop 3 (§16.2), gross of the compliance cost.
- **Type.** C — on §16.2's named premises (rationality; invariant, nested channels). Given them, the garbling
  kernel makes dominance analytic (M); the "any utility" reading rests on Blackwell's equivalence direction
  (§16.2), not on garbling alone.
- **Falsifier.** A setting where adopting protocol signals **degrades** a rational agent's
  decision quality — which, given Blackwell, can only happen with a premise violated: the protocol
  *removes/poisons* informal information, or the α₁-share is not "a subset of the α₂-share" (§16.2). So the
  real empirical target is the premises: *find a deployment where introducing GFSO suppresses the informal
  channels it sits on, or where raising α drops tasks the lower α covered.*
- **Tested?** ◻ — needs deployment data (§20.10).

### Prop 4 — constraint improvement (§16.3)
- **Claim.** Prop 4 (§16.3).
- **Type.** C — on Δ > c, with Δ as §16.3 defines it.
- **Falsifier.** A setting with Δ>c where mandatory criteria/ACCEPTED_RISKS/immutability strictly
  *lower* expected payoff → the constraint-payoff inequality fails (read as §16.3 states it — in expectation
  above ℙ(θ_bad) > c/Δ, not a dominance state by state).
- **Tested?** ◻ — E0e (+34pp) is *adjacent* corroboration (explicit criteria help), not a
  direct test of the constraint-payoff inequality.

### Cor 5 — α-monotonicity (§16.5)
- **Claim.** Cor 5 (§16.5) — an information claim; the net-payoff threshold is Prop 4's (§16.3), not this
  entry's.
- **Type.** C (a corollary of Prop 3; inherits its §16.2 premise — *not* the (ii)-proxy; so this one is
  adjudicable in principle). *Why exempt from ⟨ii-dormant⟩ while Prop 6's strict reading is not:* Cor 5
  ranges over α at **fixed information content** (a Blackwell-garbling fact about how much protocol is on);
  Prop 6's weak form is the same kind of fact, and only its strict reading — new signals
  **informative-not-noise** over time — is clause-(ii). Different premise, hence different dormancy.
- **The α premise (§16.5).** Named at the site; its closure is around the theory (§20.9); its measurable half
  and its denominator (§16.5, §20.10) — falsifier of that half in the §20.8 entry.
- **Falsifier.** A rational agent and utility for which more adherence strictly lowers
  expected utility (a "valley" in α) without violating the §16.2 premise.
- **Tested?** ◻ — adjudicable via deployment (premise is observable), unlike the ⟨ii-dormant⟩
  claims.

### Prop 6 — temporal monotonicity (§16.6) — weak form M; its strict reading ⟨ii-dormant⟩
- **Claim.** Prop 6 (§16.6): its weak form, the whole of ℐ under §16.6's premise, and its strict reading.
- **Type.** The weak form is M — garbling alone, no faithfulness premise (§16.6). Its strict reading is C
  **under the (ii)-faithfulness discipline** and on the correctness of D (§16.6, §16.7 "Correctness of D") —
  the ⟨ii-dormant⟩ one.
- **Falsifier.** Weak form, needing no faithfulness clause: an earlier protocol trace
  that is not a garbling of the later (the log losing a record), or a rational agent at fixed α whose
  expected utility on it falls as the log grows. Strict reading: accumulated protocol history adding
  noise rather than information **while criteria faithfully track reality**; a decline traced to a
  faithfulness break is §20.2 (in-framework), not a falsifier of Prop 6.
- **Tested?** ◻ — long-horizon (§20.10). Only the strict reading is **non-adjudicable until the
  (ii)-proxy exists** (shared caveat above): without an outcome-independent faithfulness measure, its
  decline is re-attributable to a faithfulness break, sharing Pred-1/Pred-3's dormancy.

### Prop 7 — scale bounds, ‖eₙ‖ ≤ (Λ·γ)ⁿ‖e₀‖ (§16.7)
- **Claim.** Prop 7 (§16.7).
- **Type.** C — under §16.7's three named model assumptions, and on the correctness of D and the
  (ii)-faithfulness premise (§16.7 "Correctness of D"). Worst-case upper bound.
- **Falsifier.** A validated hierarchy where error grows faster than (Λ·γ)ⁿ, Λ and γ as measured, **with the
  three assumptions holding** → the operator-composition bound is wrong. (Heterogeneous/adaptive
  hierarchies are out of the assumption set, not falsifiers; a measured γ not below 1 where criteria do not
  track reality is the faithfulness premise failing, not a falsifier.)
- **Tested?** ◻ — needs Λ,γ proxy measurement (§20.9). *(The γ<1 hook is the **observable** measurement of
  validator gain — adjudicable independently of the criteria-faithfulness proxy, so the entry is testable
  without waiting on that proxy, not re-graded away from it.)*

### §16.7 corollaries + small-gain stability (Cor 1–3, Zames 1966)
- **Claim.** Cor 1–3 (§16.7) — Cor 3 a claim about the guaranteed bound, not about realized benefit (§16.7) —
  and the small-gain stability of the upward CHALLENGE/BLOCK channel (§16.7, §19.8).
- **Type.** M (operator-norm algebra + Zames small-gain theorem), inheriting Prop 7's three model
  assumptions (so C on those).
- **Falsifier.** A validated cascade where composed damping exceeds γ₁·γ₂ (sub-multiplicativity
  violated), or a CHALLENGE/BLOCK loop that diverges (infinite challenge-override spiral) **with**
  gain↑·gain↓<1 → the small-gain bound is wrong, and the upward channel's stability loses its ground.
- **Tested?** ◻ — same Λ,γ measurement gap (§20.9); the spiral-stability is the concrete
  observable (does a real correction loop converge?).

### Prop 9 — decomposition quality, 4 independent mechanisms (§16.16)
- **Claim.** Prop 9 (§16.16): four mechanisms, each operative, independent.
- **Type.** Mixed, mechanism by mechanism, each under its source result's premises (§16.16): Mech.2 C, on the
  correctness of D and the (ii)-faithfulness premise; Mech.3 C in expectation (Prop 4); Mech.1 and Mech.4
  weakly M (Blackwell, as Prop 3/Prop 6), with no clause (ii); Mech.1's strict reading C ⟨ii-dormant⟩;
  Mech.4, with the LLM as its learner, also carrying §17.6's modelling premise.
- **Falsifier.** A mechanism reducible to another (independence fails); or a setting where Mech.2/3
  fail to improve decomposition with their premises held; or — for Mech.1/4 — a rational agent
  whose decomposition is worse in expectation on the richer history, a falsifier of the weak form that
  needs no clause (ii) (for Mech.4 with the LLM as its learner, the LLM premise too); of Mech.1's strict
  reading, richer-history-yet-not-strictly-better **with faithfulness held** (non-adjudicable until the
  (ii)-proxy exists, shared caveat).
- **Tested?** ◻ — E0e (+34pp) is adjacent corroboration of the constraint mechanism only.

### Prop 8 — IC as a dominant strategy (§16.8–16.11) + §16.12 IC-minimality
- **Claim.** Prop 8 (§16.11) at each signal's detection probability `p` (§16.10), its per-state dominance and
  the different, prior-dependent ex-ante corollary (§16.10); the cone exposure (§16.8); IC-minimality (§16.12);
  the named exceptions (§16.9); the threat model and its imports (§16.15).
- **Non-adversarial sub-domain — dominant-strategy, not merely Bayesian.** Type **M/C-constructive**
  (not "merely awaiting deployment"): §16.10's per-signal payoff argument and §16.12's feature table, each
  feature with its named dishonest behaviour. Detection is **structural** (§16.8, §15.8) — a claim about the
  channel, not `p` = 1 — so for each **detection-covered** signal honest use is a **dominant strategy**,
  established by dominated-strategy elimination against nature θ, not pending data. **Qualifier:** the issuer
  false-FAIL / griefing direction is *not* detection-covered — a named blind zone of q_V (§15.4) — nor are the
  other named exceptions (§16.9), which are not boundaries (§20.1). Falsifier: a feature in the §16.12 table
  whose removal leaves the dishonest behaviour it closes no freer for any agent (the enumeration over-counts),
  or a non-adversarial agent with `p`·cost(undetected defect)>cost(signal) at that signal's `p` for whom
  dishonesty pays. (An agent with cost(undetected defect)>cost(signal) but `p`·cost(undetected
  defect)<cost(signal) for whom dishonesty pays is PREDICTED by Prop 8, not a refutation of it.)
- **Adversarial domain — characterized *stratification* (§16.15), not a gap.** The detectable-incentivized
  core over an authenticated insider lies **around** the theory (§20.9) by the §20.1 criterion — its answer
  changes no claim of the canon; only its zero-exposure limit is a boundary, the value face of the
  Pragmatic-level boundary (§20.2). Type **E** for that core (I); the undetectable part (II) is
  **M**-analytic (§20.2).
- **Localization (§16.15).** *Falsifier (M):* an honest, criterion-**sensitive** cone (every `p_j > 0`, no
  collusion, detections independent) under which a false-PASS survives in-protocol detection with probability
  above `∏(1−p_j)` — would refute the attenuation. *Anti-falsifier note:* a large cone of **insensitive**
  validators surviving is NOT a refutation (it is the sensitivity-sparse frontier, as predicted).
- **Tested?** — (non-adversarial) analytic via §16.12 (dominant-strategy for detection-covered signals);
  ◻ (adversarial core) around the theory, Laffont–Martimort-hard, localized to the sensitivity-sparse
  frontier (§16.15); undetectable part = §20.2.

### Thm 10 — self-measuring (§15.6)
- **Claim.** Thm 10 (§15.6), q_V's later-fail term included once its externally triggered post-hoc run is on
  the trace (§15.6, §15.8).
- **Type.** M (constructive — each q is a count over the log, §15.6).
- **Falsifier.** A Q component that cannot be computed from the log alone (needs out-of-band data)
  → self-measuring breaks. q_V's scope is the acceptance direction by design (§15.4, §20.5 (d)): false FAIL
  is outside q_V, its share a diagnostic (§15.4) — not an instrument incompleteness and not a falsifier of
  Thm 10's computability claim. See the q_V design-decision entry (Part III.10).
- **Tested?** — analytic (constructive: the counts run over the log); ◻ predictive calibration of Q
  vs real outcomes is open (§15.8, §20.10).

### Thm 11 — structural transparency (§11.6)
- **Claim.** Thm 11 (§11.6).
- **Type.** M (definitional, §11.6's proof).
- **Falsifier.** A protocol-compliant decision with no audit record → an invariant is not
  doing what's claimed.
- **Tested?** — analytic (follows from immutability + mandatory fields).

### §17.9 — the two pillars and the feedback loop
- **Claim.** Inseparability (§17.9) at its two grades — outright for the protocol, beyond `t*` for the AI
  layer (§17.9, §17.1) — the loop read at fixed α (§17.5).
- **Type.** C — the "no improvement" is scoped to the GFSO channel; improvement through the informal
  channels (§16.2) lies outside that channel.
- **Falsifier.** A deployment where Q improves **through the GFSO channel** with a pillar removed —
  e.g. q-metrics rise with no AI-layer **past `t*`** and with no informal substitute. (Self-measurement's
  inseparability from the protocol is §17.9's own clause; Q's computability off the log is Thm 10's,
  falsified at its entry.) (Q rising with no AI layer BELOW
  `t*` is not a falsifier — it is what §17.9 states.) (Improvement via informal channels is not a
  falsifier — it is the named scope.) (A rise in Q from rising adherence is not the GFSO channel's: the loop
  is read at fixed α.)
- **Tested?** ◻ — needs an ablation deployment; never run.

---

## Part III — Positioning (Ch. 19) and the theory-model (Ch. 3–4), the foundation

### §19.5 — adaptive stratification by horizon
- **Claim.** Adaptive stratification (§19.5).
- **Type.** C — on the four premises §19.5 names (concreteness, sensitivity, stationarity, routing), not
  derived.
- **Falsifier.** A GFSO system with deadline coherence along D **and** the four premises held where deep
  (short-horizon) tasks do **not** CHALLENGE more often than shallow ones. (Non-stationary
  environments are outside the premise.)
- **Tested?** ◻ — needs CHALLENGE-frequency-by-depth data from a deployment.

### §19.4 — Scrum embedded in GFSO (a relaxation)
- **Claim (structural, the only one made).** The Scrum embedding (§19.4) — a constructive mapping, not an
  exhaustion theorem. **The behavioral derivation (GFSO *generates* Scrum's exploratory dynamics) is
  explicitly NOT claimed — around the theory (§19.4, §20.9).**
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
  that A1∧A2 **generate** Scrum's exploratory dynamics rather than merely **contain** them — its falsifier is
  **E and E3-bound.** Test: run GFSO from A1∧A2 under Scrum's regime with GFSO's requirements kept (§19.4)
  and observe whether the exploratory cadence *emerges from the forced mechanisms* (cf. §18.1 stop-replan /
  front-load) or must be added by hand. **Falsified by** restricted-regime GFSO dynamics that (a) fail to
  reproduce Scrum's cadence (generativity absent), or (b) reproduce it only under an assumption *not
  entailed* by A1∧A2 (contained, not generated). Behavioral ⟹ needs execution/experiment ⟹ **E3** — the
  same execution gate as Pred-1 / §20.2 (E2 gave a decomposition-convergence method, not method-value;
  §19.3). Until E3 this is **characterized-open**: the claim stays unmade, but its falsifier and its
  dependency are named. (The structural entry above is unaffected; nothing here is claimed proven.)

### §20.2 — causal-correctness boundary (the structural anchor)
- **Claim.** The Pragmatic-level boundary (§20.2) — Lemma 1 + Lemma 2 forms (§20.1). Every C-claim below and
  every §4.6 prediction ultimately reduces to it; it is the canon's most-cited limitation (§3.5, §7.3, §17.7,
  §20.2).
- **Type.** **M** for the *non-reducibility* (Lemmas 1 and 2, §3.4). **E** for the *located*
  manifestation — a backward signal at execution where contact reaches the denial (integration case (iii),
  §8.7); the face on the value stays silent even at contact (§20.2), which is its dormancy (§20.8 entry).
- **Falsifier.** (M side) A method that certifies real causal correctness from the formal half
  **alone** (no execution, no agent contact) → breaks Lemma 1. (E side) the backward signal:
  every child's criteria hold on the delivered result yet the parent is undelivered in the world → the
  decomposition was causally wrong, attributed by the mode §8.7 names — FM-1's insufficiency, or FM-6 / FM-5
  by its ground (§8.6); an admitted risk biting acquits the decomposer (§9.3).
- **Tested?** — (M) analytic; (E) ◻ E3 territory (multi-agent decomposition with per-child V).
  This is the boundary the §8.2 CA1 ✅\* sits *inside*: completeness-as-basis holds, but the
  *correctness* of any given decomposition against S is exactly what the apparatus does not
  certify.

### §4.1 — theory-model: agent necessity (the derivation)
- **Claim.** Agent necessity (§4.1, d1–d6).
- **Type.** M — a derivation by elimination (§4.1). The thin local residue is the "luck is unstable" step.
- **Falsifier (mathematical).** Exhibit reliable domain-correct decomposition with **no**
  empirical contact — pure formal derivation of S (contradicts Lemma 1) or grounded
  declaration (contradicts Lemma 2) or *stable* luck (contradicts S-contingency). Any one
  breaks the derivation.
- **Tested?** — analytic; corroborated by pre-theoretic success being explained, not assumed.

### §4.6 — prediction Pred-1: agent substitutability
- **Claim.** Pred-1 (§4.6).
- **Type.** E.
- **Falsifier.** Two agents with **equal** faithfulness-proxy (measured independently of
  outcome) yielding **systematically different** validated outcomes — or equal outcomes from
  unequal faithfulness. The outcome-independence of the proxy is what makes this non-circular
  (§4.6: a proxy defined via success would make it untestable).
- **Tested?** ◻ — **falsifier well-formed but DORMANT.** The canon gives no operational outcome-independent
  faithfulness proxy yet (nearest candidate = §9.3's domain precedent, itself subjectively drawn — Flag 4).
  Non-circular in form, non-operational in fact — same status as Flag 1's missing counter. E2 ran, but
  measured **convergence to a (bare-built) reference**, not faithfulness to the real domain — it did **not**
  build a faithfulness proxy; this locus stays blocked (the value / faithfulness test routes to E3 /
  execution).

### §4.6 — prediction Pred-2: applicability boundary
- **Claim.** Pred-2 (§4.6), sharpening §2.1.
- **Type.** E.
- **Falsifier.** A domain with no structural success-content where GFSO nevertheless governs
  handoffs successfully, or vice versa.
- **Tested?** ◻ — **partially dormant, same proxy as Pred-1/Pred-3.** Insofar as detecting "structural
  success-content present" leans on faithfulness, Pred-2 inherits the same non-adjudicability. The *one* half
  that is plausibly outcome-independent — "does a structural validation half exist at all?" (an architectural
  fact, observable like Simon-t\* capacity) — is testable; the "success-content" half is not, until the
  proxy exists. So Pred-2 is split: structural-presence side ◻-adjudicable, success-content side
  ⟨ii-dormant⟩. The asymmetry with Pred-1/Pred-3 is thus only partial and is stated, not assumed.

### §4.6 — prediction Pred-3: global falsifier (the model's own neck)
- **Claim.** Pred-3 (§4.6).
- **Type.** E — the deliberately-stated global falsifier.
- **Falsifier.** Exactly that: a system that **reliably** succeeds OOD while (a) carrying no
  structural validation half and (b) having demonstrably-low faithfulness **measured
  independently of the success itself**. The independence clause is load-bearing: without it
  any counterexample is re-explained post-hoc, and the claim would be circular (§4.6).
- **Tested?** ◻ — no such system observed; the claim is an open standing bet. Same dormancy as Pred-1:
  refuting it requires faithfulness "measured independently of success", and no such instrument exists
  yet — so the bet is well-posed but not currently adjudicable.

---

## Part III.6 — v3.6 agent-free ontology + methodology (§19.2–19.3, §5, §18.1)

> The register treats this layer on the **same E/M/C discipline** as everything above. Two consistency
> anchors govern these entries and are checked at the bottom: **(α)** structural-completeness claims are
> **M / analytic-modulo-a-named-residue** — the 5-link completeness is the *direct sibling* of the 6-FM
> completeness entry (§8.8) and the §8.2 / §9.1 covering claims, not a new empirical posit; **(β)** the
> **only** irreducible empirical hooks remain the two contact-with-world loci already registered — domain
> membership (§2.1) and **Ŝ-faithfulness to S** (§3.7; the ⟨ii-dormant⟩ locus / §17.7) — and this layer
> relocates nothing into or out of those.

### §5.3 — 5-link completeness of directed action (covering axiom)
- **Claim.** The five links (§5.1), their minimality (§5.2) and completeness by CA-Links (§5.3).
- **Type.** **M — analytic modulo a named covering axiom, and *below* the 6-FM-completeness grade**: the modal
  and realization branches derived, the representational branch modulo REACHES-ternarity, with START's fold
  carrying the count (§5.3). Reject the fold ⟹ 4 representation roles ⟹ the 3⊕2=5
  count breaks. So this is *weaker* than the 6-FM split, whose residue does **not** touch the count (§8.2);
  registered as M-with-a-residue, not as a closed theorem, and not as empirical.
- **Falsifier (M).** §5.4's: a **real directed action** that (a) is missing one of the five links while still
  being directed-and-real — the **minimality** falls (§5.2's per-element argument; the covering axiom is
  postulated in the covering direction only); or (b) exhibits a genuinely **independent 6th structural
  feature** — a third modality, a 4th REACHES role *not* foldable into START, or a 3rd realization direction —
  the **completeness** falls: the covering axiom (or the START-fold) has a hole, open-from-inside (§5.4). Same
  shape as the 6-FM falsifier ("a failure the case split routes to no Cᵢ") and the §7.5 minimality falsifier
  ("an HVP expressible after deleting a primitive") — not a new kind of test.
- **Tested?** — analytic; minimality is at full parity with §7.5 / §8.8 (per-element counterexample).
  Adequacy-to-phenomena would need its own survey of directed actions (a missing-link or 6th-feature action
  would surface there); E1, a survey of failure modes, does not bear on it; not run. The
  START fold is the located weak point — unlike CA1's value/time edge, it carries the count.

### §18.1–18.2 — methodology forced-corollaries (front-load FORM, stop-replan; optimality under Prop 7's model)
- **Claim.** The two mechanisms forced from the FORM ⊕ FAITHFULNESS cut (§18.1, §3.6); their optimality under
  Prop 7's named cost model, with the hedges §18.2 states.
- **Type.** **M — the two mechanisms forced from the ontology; the optimality conditional on Prop 7's cost
  model.** **The cost/probability VALUES are E / contextual** — `c_check`, the FORM-risk, the S-fixed wall-set
  are domain data, exactly as **S itself** is contingent (Lemma 1) and as the Prop 3/4/7 *premises* (Δ, c, Λ,
  γ) are E. This split — **structure forced (M), magnitudes empirical (E)** — is the *same* shape already used
  for Prop 4 (premise named, inequality M) and the §16.7 corollaries (algebra M, Λ·γ measured). Cost composes
  as an edge decoration, **not a 6th link** (§5.1) — consistent with the §5.3 entry.
- **Falsifier (M, on the forcing).** A directed-action failure that is **neither** FORM nor
  FAITHFULNESS (a third epistemic-access class) → the coarse-cut derivation has a hole (this is the
  falsifier of §3.6's FORM ⊕ FAITHFULNESS cut, orthogonal to the 6-FM split (§8.10) —
  it does **not** introduce a new test). Or: a setting where front-load+stop-replan's **guaranteed bound** is
  dominated by that of proceeding on an un-updated plan **with `c_check` and the cascade-compounding (§16.7)
  premises holding** → the optimality derivation (not the value estimates) is wrong; one run's realized cost,
  luck included, refutes no comparison of bounds.
- **Falsifier (E, on the magnitudes).** A domain whose measured `c_check / E_FORM / E_FAITH` make
  the front-load *granularity* or the verify-depth come out elsewhere than predicted — this falsifies
  a **contextual value**, not the forced structure (same status as a wrong Δ or Λ,γ estimate). The
  *free residue* (speed, route among faithful D, front-load granularity above the "executable
  segment" floor) is **forced-free** — orthogonal, so unfalsifiable-by-design and correctly so.
- **Tested?** — (forcing) analytic; (magnitudes) ◻ routed to E3 + the §20.9 Λ,γ measurement (E2 was
  decomposition-convergence, not these magnitudes), the same empirical hooks as the C-claims (Flag 5). No
  run measures THESE magnitudes; the methodology itself has been driven end-to-end on a benchmark at
  calibration tier (EVIDENCE_LOG §13), which is not the same thing.

### §18.1 — verify-vs-explore structure (how far to run the FORM mechanism)
- **Claim.** Verify vs explore (§9.9), applied to how far to discharge FORM (§18.1).
- **Type.** **M-forced structure, E values** — same split as the entry above and same family as the
  §7.4 informativeness reasoning (the *structure* of "decision-relevant vs not" is analytic; what is
  decision-relevant on a real task is E). The existence and *shape* of the tradeoff are forced; the
  **crossover point is the empirical / contextual datum** (`c_check` vs prevented risk), not a hedge on the
  structure.
- **Falsifier.** (M side) a FORM-discharge decision that is neither "verify more" nor "explore /
  proceed" and cannot be located on the §9.9 axis → the tradeoff is mis-structured. (E side) a
  measured `c_check`/risk regime where the predicted crossover sits elsewhere → a wrong value, not a
  broken structure. (As with §7.4, a merely *informational* surplus that never moves the verify
  decision is **not** a falsifier.)
- **Tested?** ◻ — analytic structure; crossover never measured (E3, §20.9).

### §19.2 — honest [known]/[GFSO] ratio (narrow-delta accounting)
- **Claim.** The [known]/[GFSO] ratio (§19.2): planning absorbed, the [GFSO] delta as §19.2 enumerates it,
  standard abstraction/method-learning not subsuming the core.
- **Type.** **M** — an analytic accounting / per-candidate reducibility claim, **distinct** from §19.3's
  E premise (this is about *mechanic-novelty*, not about how organizations actually plan).
- **Falsifier.** Exhibit a standard technique that subsumes one of the delta items **as a
  guaranteed primitive** (not a heuristic): e.g. a method-learner that *guarantees* (not corpus-
  heuristically posits) a faithful new seam, or an option/HTN formalism that **obligates + attributes**
  the set-level integration implication `(⋀ children)⟹Capt(parent)` → the "narrow delta" enumeration
  is wrong (delta narrower, or an item misattributed to [GFSO]).
- **Tested?** — analytic; corroborated by the §19.2 per-candidate reduction (each candidate isolated,
  none subsumes EXTERNALIZE). Lemma 1 yields only *non-derivability-by-apparatus*, **not** a [GFSO] tag for
  bare seam-generation — so the accounting does not inflate the delta.

### §19.3 — value=making-explicit empirical premise
- **Claim (the load-bearing empirical premise of the positioning).** The premise of §19.3 — what makes
  GFSO's primary value making-explicit rather than method-novelty (§19.2's narrow delta).
- **Type.** **E — a contingent claim about how real organizations actually plan,** routed to E3 (§19.3,
  §20.10; E2 gave the convergence *method*, not the discipline's *value*). It is **not** M: nothing in
  A1∧A2 forces that real methodologies are unchecked (unlike the §19.2 *ratio*, an analytic accounting).
- **Falsifier.** A representative sample of real working methodologies that **do** routinely carry an
  internal-consistency check (CHECK-7/8-equivalent) on their assembled plans → the premise is false
  and the "making-explicit is the primary value" positioning loses its empirical base. (A single
  counterexample methodology is not enough — the claim is about the *typical* case, so the falsifier
  is distributional, like the Simon-t\* capacity-necessity entry.)
- **Tested?** ◻ — **E2 ran but did NOT adjudicate this.** E2 measured LLM decomposition *convergence to
  a (bare-built) reference*; by the bare-reference confound (E2, `EVIDENCE_LOG`), coverage cannot read the *value* of
  made-explicit discipline over unchecked assembly (that comparison needs **execution = E3**). E2 did
  establish the convergence *method* (`decompose()` = bare-SEARCH ⊕ gfso-AUDIT). The premise stays a
  genuine, outcome-independent hook (you can audit a methodology for a consistency check without running it
  to success) — routed to E3, plus a survey of real methodologies would bear on it.

### §20.1 — the boundary CRITERION (the meta-rule this register rests on)
- **Claim.** The boundary criterion, the four forms of a boundary's impossibility argument, and the two kinds
  outside it — around the canon, and not yet built (§20.1). Applied entry by entry to §20.8's list and to
  §20.9–20.10.
- **Type.** **M** — a rule about the canon's own classification; checkable by inspection of each entry.
- **Why it is load-bearing.** Without it "boundary" converts any unclosed item into a result by naming:
  "the taxonomy would close itself by fiat" (§20.1).
- **Falsifier.** An entry on §20.8's list for which the canon exhibits no argument of the four forms
  (the label is unearned); an entry in §20.9–20.10 that *does* carry one (a boundary mis-filed); or an item
  filed around the theory whose answer would change a claim of the canon (a stopping point misplaced).
  Each falsifies the **application**. The **criterion** itself falls if a genuine fifth kind of
  non-derivability from inside is exhibited, of none of the four forms — in which case the four-form
  definition is incomplete.
- **Tested?** ◻ — applied across §20.8 and §20.9–20.10; no external audit of that application.

### §15.9 — triage order over the graph
- **Claim.** The triage rule (§15.9).
- **Type.** **M** for the cone — a reachability query over 𝒢 (§15.9), in Thm 10's own currency; **C** for
  the rule — a heuristic under the uniform-repair-cost premise §15.9 names. No optimality is claimed (§15.9).
- **Falsifier.** Not a graph in which following the rule unblocks less work than another ordering: the
  rule orders by the reach a failure holds, not by the work one repair unblocks, and claims no
  optimality (§15.9). The derivation is falsified by a failing node whose failure holds a node outside
  its cone as defined — an ancestor or a consumer reached neither upward through E_D nor forward through
  E_Dep — or a cone not computable as a reachability query over 𝒢. The cone and the deadline order are
  facts of the graph either way.
- **Tested?** ◻ — derived, never exercised; it prescribes an operator behaviour no deployment has run.

### §20.8 — the named boundaries (the faithfulness residue is the irreducible (ii) locus)
- **Claim.** The boundary list (§20.8) — **declared, NOT closed** — each entry tagged by its form under the
  criterion (§20.1; its entry above); what lies around the canon (§20.9) and what is not yet built (§20.10)
  are not on it.
- **Type / routing (consistency-critical).** Each boundary **reduces to an already-registered
  entry** — no boundary of a new *type*:
  - **the faithfulness residue (§20.2, the face on the value) → the irreducible empirical (ii) locus** —
    §8.7 case (ii) / §17.7, registered above as ⟨ii-dormant⟩ and as the Part II shared caveat. Type **C/E,
    DORMANT**: falsifier = a domain-silent false-PASS detected by a purely-formal apparatus (breaks Lemma 1),
    but **non-adjudicable** until an outcome-independent faithfulness proxy exists (Flag 4 / Pred-1). This
    entry asserts **no new test**; the ontology's empirical irreducibility terminates at *exactly* the
    pre-existing (ii) locus — anchor (β).
  - **decomposition-method quality, its faithfulness half (§20.2, the face on production) → §20.2 / §17.7**:
    **M** for the non-reducibility of the faithfulness half, E-on-execution (§20.10) for its measure on a
    real domain; the boundary that *bears on use* (§20.8), not a finalization residue.
  - **Level-2 causal correctness (§20.2) → the §20.2 entry above.** Type **M** for the underivability; its
    manifestation **E** where contact reaches the denial ("(iii) is the apparatus catching the wall", §8.7),
    **C/E DORMANT** only on case (ii), the (ii) locus — no new test.
  - **the completeness-of-the-carve wall (§20.7) → the §20.6–20.7 entries** (M inside a frame — Beth-class
    canonicity, the negative verdict over bare adequacy, the machine forced over the log; the global question
    C, on the undelimited candidate space). No new test. Its disclosed residues route to their entries: the
    representational branch → §5.3 (M, START-fold residue); CA-Morris → §9.1; the inference-type covering →
    §17.2–17.3.
  - **the edge of the domain (§20.3) → the A1/A2 entry and the §6.9 entry (Part III.7)** (M). Falsifier = the
    object apparatus shown to cover a non-finitely-decidable goal without the generator.
  - Routing entries for what lies **around** (§20.9 — because no answer changes a claim), not boundaries:
    **CA1's residue → §8.2 CA1/CA2 entries + Flag 3** (single clock **discharged**, Part III.10); **cardinal
    severity → §19.6** (an import; the ordinal skeleton ⪰_dom stays internal); **adherence dynamics (α) →
    §16.5 + the Cor 5 / Prop 6 entries** — **E** for the measurable half (§16.5, §20.10). Falsifier of that
    half: a deployment where non-adherence inside the protocol cannot be read off the trace.
  Consequence for this register: the adversarial optimum (optimal bond / collusion-proof quorum) lies
  **around** the theory (§16.15, §20.9), its zero-exposure limit alone being the Pragmatic-level boundary.
- **Falsifier.** Per boundary, as in the referenced entry. The **only** way to falsify the
  *boundary inventory itself* is to exhibit an irreducible empirical hook **outside** these three
  (and outside domain membership, §2.1) — which would mean the ontology has an unregistered contact-with-
  world locus. None found; the inventory closes onto the two pre-existing loci (anchor β).
- **Tested?** ◻ — same as the entries each routes to; the faithfulness-residue locus is dormant
  (no proxy); the method-quality locus = **E2 closed the generation procedure (`decompose()`; the logic-free
  positing leap remains, no boundary, §20.2); seam-faithfulness is answerable only on execution (§20.10).**

---

## Part III.7 — continuous-substrate re-grounding + 3-axis faithfulness (§6; the seam half — §3.3–3.7)

> The continuous-substrate layer (Ch. 6) adds **no new empirical hook**: it re-grounds existing claims over a
> borrowed [known] control/viability substrate, and its empirical irreducibility terminates at *exactly* the
> two pre-existing loci (anchor β: domain membership (§2.1) + Ŝ-faithfulness, §3.7). Each item routes to a
> registered entry:

- **Continuous substrate (flow / capture basins / viability), §6.2.** [known] — borrowed, not a GFSO-delta
  (§19.2). Falsifier (M-on-the-borrowed-theory): the domain is not a controlled dynamical system — a
  physics-grade claim outside the GFSO delta. No new GFSO hook.
- **`(t,{tⱼ})∈S` as basin chaining (§6.4–6.5).** Re-expresses the Theorem 1 composition edge over the
  continuous ground (§7.3 "Form and substance"); operative truth-condition and its M-falsifier unchanged. The
  [GFSO]-core is the same narrow delta already registered under Theorem 1.
- **Separators (§6.7) = continuous ground of non-redundancy.** Routes to **non-redundancy (§2.4) /
  Theorem-1-correctness** (M); a demand beyond the goal is no failure of the split (§6.7, §8.10 "Scope").
- **The map's coarsening `≈_G` over `∼_G`'s functional scale (§6.3, §6.8) = continuous ground of
  ACCEPTED_RISKS / the scale faithfulness axis.** Routes to **STD-1**; falsifier = a leak of `≈_G` the split's
  claim risks that no register entry can declare as a risk event, or an entry naming no merge of `≈_G` — the
  operationalized §9.2.
- **A1/A2 as conditions of Contact (§3.7).** Adds no hook: the residue is **≈ the axioms themselves**,
  both already registered (A1 (ii) ↔ the (ii)-faithfulness/FM-3 locus; A2's κ-**cost** ↔ §9.9; A2's
  **decomposability** residue ↔ the domain-membership (§2.1) entry, **not** §9.9). The added role is analytic
  (M); it relocates nothing into or out of the two empirical loci.
- **SINGLE-SEAM / the apparatus operator `𝒜` (§3.3–3.5).** Derived from 𝒜's S-freeness and Contact's
  signature (§3.5), Lemma 1 (§3.4) barring a stand-in for Contact; M, same falsifier as
  the Lemma-1 / agent-derivation entry (a purely-formal operation that reads S breaks it).
- **3-axis faithfulness (edge / node / scale), §6.8.** Re-expression, no new locus: **edge** = the registered
  ⟨ii-dormant⟩ faithfulness locus; **node**, its absent and illusory halves, routed to the modes §8.3 names
  where what was obtainable at the fixing showed them, FM-6 / FM-5 by its ground otherwise (§8.6) — **FM-1.b /
  STD-2**, FM-1.d's and FM-1.e's domain faces, **FM-1.f** — and to no mode of a split where §8.3 and §8.10
  "Scope" say so (the goal vertex's illusory half, an atomic root's unwritten requirement, a maintenance
  generator's missing exit direction, §6.11); **scale** = **STD-1**. Node + scale generate edge (§6.8), so the
  irreducible (ii)-hook stays the single edge/faithfulness locus.
- **Tree/cycle goal topology (§6.9).** [known] control distinction (reachability vs viability/invariance);
  completeness at the class level by citation (§6.9) — M, analytic-modulo-borrowed-[known], not a covering
  claim. Goals outside the two finitely-decidable topologies (`□◇A` recurrence) are the domain-form boundary
  (§20.3), **NOT a falsifier**. Sharper falsifier (M-on-borrowed): a directed action outside the
  safety⊕liveness classification, or a `□◇A`-type goal the achievement-reducing generator cannot represent.
  The forest of D and CHECK-2 (§15.3) are untouched.

**Consistency (anchors α, β).** (α) The new structural-completeness content (separators, 3-axis, tree/cycle) is
**M / analytic-modulo-borrowed-[known]** (the canon's grades: defined, derived or by citation, §6.1–6.12), not a
covering claim like §8.2/§9.1/§5.3 — no new empirical posit. (β) The only irreducible empirical hooks remain
domain membership (§2.1) and Ŝ-faithfulness to S (§3.7); the continuous layer relocates nothing into or out of
them. No new flag.

---

## Flags — claims whose falsifier is weak, missing, or instrument-limited

These are **not** hedges. Each is a precise statement of where the empirical hook is thin,
to be strengthened (named premise / built instrument), never softened.

1. **q_V one-sidedness = a design decision (§20.5 (d); §15.4, §8.4).** q_V's scope is the acceptance
   direction (a recorded PASS later failed, whatever caused it, §15.4); the false-FAIL direction is guarantee-safe (§8.4), outside q_V, its share a diagnostic
   (§15.4); q_D charges one over passing children to the split (§16.9, exception 1). The one missing item is an instrument reading that share — **not** a detection or Q-completeness
   gap. Buildable, deliberately deferred. Previously logged as "counter not built / action: build it";
   re-leveled to a design decision — see Part III.10.
2. **|Act|=2, the covering premise of the defense (§7.1).** |L|=2 is *sourced* in A1; |Act|=2 carries only
   the **defense** against a graded scale (§7.1), a covering axiom (§7.1, §20.5). Honest premise, not a gap —
   but the single place an objector lands. Kept named, not dissolved.
3. **CA2 single-clock (§8.2).** The operational phase **count** is axiom-free (§8.2, §20.5); the single
   clock is the discharged hypothesis `SingleClock`, **not** a covering axiom. What remains outside the
   taxonomy is **verdict atomicity** (§8.2), not axis completeness — no longer an open E3 scope boundary for
   the count. See Part III.10.
4. **FM-1.b ↔ STD-2's extraordinary grade: the threshold's subjectivity (§9.3, §8.3).** The "was a
   foreseeable mitigation missing?" line is operationalized (faithfulness / domain-precedent) but the
   precedent threshold is still subjectively drawn. A principled, less-subjective criterion is an open
   refinement (does not block E1; logged).
5. **C-claims awaiting deployment (Prop 3,4,6,7,8; §19.5).** Every conditional guarantee above
   is currently corroborated only mechanically/adjacently; none has a direct deployment test.
   The premises are all named; the empirical hooks are real but unrun (E3/§20.10; E2 ran — decomposition
   convergence only, see §11 of the evidence log).
6. **Decomposition-method quality (§20.2, §4.5).** EXTERNALIZE does **not** guarantee a seam's faithfulness
   (§4.5, §20.2). **E2 closed the generation procedure** (bare-SEARCH ⊕ gfso-AUDIT → `decompose()`,
   convergence to a completeness-audited reference); **seam-faithfulness to the real domain is measured, not
   derived (§20.10)**, not a finalization residue. It is the located manifestation of the (ii)-faithfulness
   locus on the *production* side; same dormancy until a proxy exists.
7. **START-fold residue (§5.3).** The 5-link count holds modulo START's fold (§5.3). Reject the fold ⟹ the
   3⊕2=5 count breaks. Honest sub-CA1 residue (the analogue of CA1's value/time residue, which carries no
   count), named not dissolved; does not block, logged.

**Scope of this register.** It covers the load-bearing claims of Ch. 1–2 and 7–9 (axioms, basis
minimality+completeness, |L|=2, Theorems 1–2, 6-FM completeness + independence, §8.2 CA1/CA2,
§9.1 level-exhaustiveness), Ch. 11–13, 15, 17 (protocol minimality, Q minimality, Simon capacity-necessity,
Chollet Level≥2 §17.2, AI two-components/cross-impossibility §17.3), Ch. 16 with §15.6, §11.6 (Prop 3–9,
§16.7 corollaries + small-gain, Theorems 10–11, §17.9 indispensability), Ch. 19 (stratification, Scrum
embedding, the [known]/[GFSO] ratio §19.2, value=making-explicit §19.3), and Ch. 3–4 (agent derivation +
predictions Pred-1/Pred-2/Pred-3, **+ Ch. 5 5-link completeness, §20.8 named boundaries, Ch. 18 methodology
forced-corollaries / verify-vs-explore**), Ch. 6 (Part III.7), and the protocol entries of Parts III.8–III.11.
Of the claims **enumerated here**, none has zero falsifier of any type — every entry is E, M, or C, and
the flags above are thin empirical hooks, not vacuous claims.

This is a completeness statement **scoped to the enumerated set**, not a proof that the canon
contains no unfalsifiable claim anywhere. **Deliberate omissions** (assessed as non-load-bearing or
expository, not silently dropped): §7.4 informativeness *commentary* beyond Inf-A / Inf-B; §17.9-style
restatements in the Abstract and the Introduction; the §19.8 comparison table and related-work mappings;
STD-1, STD-3 as *prescriptions* (each guards FM-1 — STD↔FM is §9.10 — so their falsifiers reduce to the
FM-1 entry). **STD-2 and STD-4 are exceptions and ARE registered** (Part I): STD-2 is the admissibility line
(§9.3, §9.10: not coverage), and STD-4/CHECK-7–8 is FM-1.d's a-priori instrument — neither reduces to another
entry. If a reader finds a load-bearing claim outside this set, the register is *incomplete*, not *wrong* —
add it.

---

## Part III.8 — v3.7 protocol rigor (§9.2, §11.3, §11.6, §12.6, §12.10–12.11, §15.5)

> The falsifiers are **M — analytic on the protocol structure** (like the §7.5 minimality / §11.4
> signal-minimality entries), except the discovered-Dep metric, which inherits the **E** hook of q_Dep.

- **Cancellation completeness (two-step handshake).** *Claim.* The cancellation handshake (§12.6);
  CONFIRM_CANCEL's grades (§11.4, §12.13, §12.9); the eleven states complete (induced, §12.1) and, but for
  REWORKING, irredundant (§12.11, §20.4). *Type.* M (analytic, sibling of the §11.4 12-signal minimality
  entry). *Falsifier.* A machine without CONFIRM_CANCEL that still gives the in-flight report "which only the
  executor can give" (§11.4's row) or keeps the executor's channel of Inv-4's reading, clause (2) (§12.9)
  (⟹ CONFIRM_CANCEL non-minimal, drop to 11) — a terminal reached without CONFIRM_CANCEL and its timeout,
  the one-step-cancel fold, is not one: that fold is deadlock-free and CANCELLING is held by Inv-4's reading
  (§12.13); OR a state reachable in
  cancellation that neither CANCELLING nor ABANDONED covers (⟹ the eleven states incomplete). Same shape as the §7.5 "HVP
  expressible after deleting a primitive" falsifier.
- **Revision ≠ abandonment (no-cascade + guard set).** *Claim.* A revision without cascade, and the guards
  that flag what a cascade used to remove (§12.10). *Type.* M/C (conditional on the guard set). *Falsifier.* A
  staleness introduced by a revision — an orphaned `covers` or an uncovered new criterion — that **passes
  the guards** yet corrupts V(parent). One such case ⟹ the guard set is incomplete and cascade (or
  a further guard) is required.
- **Node-identity invariant (Inv-7).** *Claim.* Inv-7 (§12.11). *Type.* M. *Falsifier.*
  A re-identifying revision that preserves all graph edges (E_D/E_Dep/mappings) intact ⟹ stability not
  entailed; OR a T11 provenance query answerable only from immutable *node* criteria (not the log) ⟹ the
  §12.11 relocation is wrong.
- **Discovered-Dep provenance (BLOCK→q_Dep).** *Claim.* BLOCK's provisional discovered-Dep edge and
  its adjudication (§11.3, §15.5). *Type.* E (inherits q_Dep's empirical hook).
  *Falsifier.* A deployment where surprise inter-task dependencies occur (BLOCKs on undeclared
  prerequisites) yet q_Dep stays ≡1 ⟹ the effect isn't recording them; OR discovered edges systematically
  admit misattributed (adjudicated-false) blockers into the denominator ⟹ the two-phase confirm fails.
- **Risk-ledger ≠ scope-boundary.** *Claim.* The register/scope line (§9.2). *Type.* M (analytic on §9.2 +
  CHECK-1). *Falsifier.* A goal-scope boundary that (a) carries a well-defined materialization probability P
  feeding the §9.4 aggregate fold (⟹ it *is* a risk, category not needed), or (b) is admissible/
  inadmissible by a test **not** reducible to CHECK-1 over the goal's criteria (⟹ a genuinely separate
  mechanism is missing, not a routing clause).

---

## Part III.9 — v3.8 metric well-definedness + event-timeliness (§15.4, §15.6, §15.8)

> The falsifiers are **M — analytic on the formulas** plus the **E** deployment hooks the metrics already
> carry (§15.8).

- **q_D non-degeneracy (the FAIL-event formula).** *Claim.* q_D's event formula (§15.4) — it reads the pattern
  a refuted composition claim leaves, not its cause (§15.4, §16.9); the DONE-gated formula it replaced was
  identically 1. *Type.* M + E. *Falsifier.* A live graph exhibiting the event ("non-atomic, own validation
  FAIL while children passed", §15.4, whatever state the node reaches later) on which q_D stays 1 ⟹ the formula/instrument still misses its target; OR
  a graph with no such pattern where q_D < 1 ⟹ the event proxy over-fires (a parent whose children were all
  ABANDONED is excluded by §15.4).
- **Event-timeliness of q_T/q_Del (population = issued contracts).** *Claim.* q_T's and q_Del's events
  counted when they happen, over issued contracts (§15.4, §15.7). *Type.* M (analytic). *Falsifier.* A
  defect trajectory expressible in the protocol (a challenged or mis-delegated node) that the new
  populations still cannot count, OR a demonstration that DONE-gating loses no defect class (⟹ the
  edit was unnecessary).
- **q_V discovery carrier (post-hoc independent validation).** *Claim.* The post-hoc run (`validate_result`)
  and the two later-fail events q_V's numerator reads (§15.4, §15.8), the discovery trigger external (§15.6).
  *Type.* E. *Falsifier.* A deployment where accepted-then-found-wrong results occur and get re-checked, yet
  q_V stays ≡1 ⟹ the carrier misses the event; OR post-hoc fails systematically mark genuinely-correct
  results (over-fire).
- **Named instrument gap (registered debt, §20.10):** reason-typing of revisions — a requirement not yet
  built (§15.8, §20.10); what the metrics read without it is §15.8's. (The false-FAIL share is *not* in
  this debt: a diagnostic outside q_V on a guarantee-safe direction, §15.4.)

---

## Part III.10 — v3.9 canon-status re-levelings + machine-check + sharpened open problems (§20.4–20.5, §19.7, §7.1, §8.2, §20.6–20.7, §16.13, §12.14, §15.4)

> Falsifiers stay **M/C** on the canon structure, plus one **C** machine-checked-closure claim (§20.4). Two of
> the re-levelings — the §7.1 source/defense re-attribution and the §16.13 IC=seam explication — add **no new
> falsifier** and are not separately registered here (they sharpen the referent of the existing |L|=2 / IC
> falsifiers).

### Machine-checked axiomatic closure (Lean 4, §20.4)
- **Claim.** The machine-checked core and its axiom footprint (§20.4), the closure's three covering axioms
  with their carriers (§20.5 kind (a)); CA2 not in the footprint (§20.5).
- **Type.** C — conditional on the three named axioms; the guard makes the *count/identity* of the
  footprint an M-checkable invariant, but each covering axiom is itself the empirical hook.
- **Falsifier.** The closure audit goes red: an axiom "outside the whitelist and Lean's three foundations" appears (§20.4), an `opaque` / `sorryAx` /
  `native_decide` is found in any namespace, or a whitelisted axiom is discharged without the whitelist
  being updated in review. Encoding-relativity is disclosed, not a falsifier: re-encoding `|Act|=2` as an
  axiom moves the count to four *by design* (§20.5).
- **Not falsified by.** A green build alone (a name collision once elaborated a definition to `sorry`
  silently) — hence the guard is fail-closed and semantic conformance stays a human job (§20.4).
- **Tested?** ✅ — guard runs in CI on every `formal/` and canon change.

### §19.7 — scientific method (method core) = GFSO, domain=nature
- **Claim (structural, ◪).** §19.7's mapping: A1 as the decidable form of the falsifiability requirement
  (§1.3, §19.6, §19.7), demarcating the theory's own domain, not science; science a relaxation of GFSO, the same
  method over nature with its theory-model implicit (§19.7).
- **Type.** structural-embedding, same family as §19.4 (Scrum's embedding).
- **Falsifier.** Exhibit an element of the *method* (not institution, not theory-choice, not the cardinal /
  graded-confirmation layer, consilience's confirmational component included (§19.6, §19.7's table); not the
  route among faithful decompositions, left free (§18.2) — a test with a fixed rejection rule is an
  **instance** of the criterion↔truth split, §19.7, not an exclusion) not expressible in GFSO; or a generative contribution to discovery beyond
  the EXTERNALIZE-form; **or an interventionist
  formulation of the Pragmatic-level claim that is also verifiable from inside the apparatus**, which
  would collapse the formulation/verification split of §20.2.
- **Status.** ◪ — **adversarial search RUN** over §19.7's mapping: **no escaping method-primitive** — each candidate is
  caught by existing structure, folds into the two named remainders (the causal Pragmatic-level boundary,
  §20.2; one graded-confirmation import, §19.6) or the ¬A1 domain; causal discovery lands on the causal
  boundary itself (§20.2). Survives under the **two named presuppositions** §19.7 states. Core analyticity
  and the absence of a *behavioral* claim (that GFSO *generates* scientific practice) are preserved. Residue
  routes to the Pragmatic-level boundary (§20.2) — shared with science; the logic-free throw is a shared
  remainder, not a boundary (§20.2).

### §20.6–20.7 reformulation — basis uniqueness as bi-interpretability (basis side only)
- **Claim.** Basis uniqueness posed as bi-interpretability over Mod(A1∧A2) (§20.6).
- **Type.** M (a bi-interpretation is a mathematical object to exhibit/refute) **conditioned on C**
  (the admissible-signature class is undelimited, §20.7).
- **Falsifier (M).** Exhibit an adequate σ′ **not** bi-interpretable with σ.
- **NB — the PROTOCOL side does NOT share this currency (§13.1).** Protocol uniqueness is posed in
  behavioural equivalence; its entry is the "Protocol minimality" block in Part I.5. This entry is basis-only.
- **Un-closable-from-within caveat (C).** The class of admissible signatures must be delimited (§20.7) — so
  the reformulation makes the *form* of an answer checkable and names *where* the undecidability sits, without
  settling it.
- **Two escape routes pushed — wall narrowed to one frame-locus (M/C).** Dep\* and quotient interpretations
  (§20.7): neither yields a falsifier, and the wall is pinned to one stipulation, the FO frame (§20.7).
- **Partial result (M, Beth-class).** σ-canonicity over the Beth class (§20.6), the dual of §7.5 minimality.
  **Falsifier:** exhibit such a τ that determines σ yet is *not* bi-interpretable with it. Residue: §20.6's
  premise (Mod(A1∧A2) an elementary class, which the canon does not state it to be).
- **Status.** ◻ — the Beth-class sub-question is *closed* for that first-order reading and the two escape
  routes are pushed; **global** uniqueness is the carve wall (§20.7, §20.8) — at the frame boundary. The live
  falsifier is only an **adequate non-bi-interpretable σ′ under FO + same domain**, not exhibited. Minimality
  M proven (§7.5).

### §8.2 CA2 — discharged from the covering set (amends the §8.2 CA2 entry / Flag 3)
- **Claim.** The operational axis, CA2 redundant, atomicity outside the taxonomy (§8.2); FM-5 under
  concurrency (§8.6).
- **Type.** M — the phase count is axiom-free (`Time.app_phases_exhaustive` over the application, §20.5;
  `Time.phases_exhaustive` its single-event case); the residual single-clock cost is a discharged
  hypothesis, not a covering axiom.
- **Falsifier (M).** A real event whose position relative to the application [f, e] is none of
  {wholly-before, concurrent, wholly-after} → the excluded-middle partition has a hole; or a concurrency failure that
  is a genuinely new mode outside the 6-FM taxonomy.
- **Supersedes.** The earlier "single-clock scope boundary routed to E3" framing (CA2 (i) entry /
  Flag 3): the *count* no longer depends on a clock. What remains outside the taxonomy is verdict
  atomicity, not axis completeness.
- **Tested?** — analytic (machine-checked axiom-free, §20.5).

### Cancellation irreversibility = a design decision (§12.14; §20.5 (d), terminality)
- **Claim.** Terminality a design decision (§12.14, §20.5 (d)), R′ its named extension (§12.14, §12.16).
- **Type.** C — a declared design decision under the named guarantee premise.
- **Falsifier.** The guarantee premise is the hook: a contract useful as a guarantee whose terminal
  outcome is nevertheless arbitrarily revocable by any party at any time without losing its value → the
  non-arbitrariness derivation is wrong. (Terminality itself is not an empirical claim — it is the
  conservative implementation; refuting "terminality is forced" is *not* a falsifier, because bounded
  REOPEN R′ is guarantee-compatible by construction.)
- **Finality (R′ semantics, §12.14).** The finality criterion and consumption (§12.14).
  - **Falsifier (M).** A terminal *locally reversible* by the finality criterion (§12.14) yet must be final,
    or final by it yet must stay *locally* reversible, not reducible to a post-hoc pass→later-fail (§15.8) or an out-of-graph side
    effect.
  - **Residues** (§12.14, §16.15).
- **Status.** ◻ named design decision — base = terminality, recovery as §12.14 and §15.2 state it; extension
  R′ with a derived finality criterion; not a cascade-rollback. Protocol unchanged (no 13th signal).

### q_V one-sidedness = a design decision (§15.4; §20.5 (d), q_V's scope)
- **Claim.** q_V's scope (§15.4, §20.5 (d)); false FAIL guarantee-safe (§8.4).
- **Type.** C — named design decision.
- **Falsifier.** Exhibit a false-FAIL that is a defect of *acceptance* reliability and is NOT reducible
  to efficiency / a separate FM-4 / an A1 violation.
- **Residue (buildable, deferred).** No instrument yet reads the false-FAIL share, outside q_V and a diagnostic
  (§15.4) — not a detection or guarantee gap. Distinct from the permanent §20.2 false-PASS boundary.
- **Status.** ◻ named design decision. (Re-levels Flag 1 above: the counter is a diagnostic option, not a
  completeness debt.)

---

## Part III.11 — v4.1 ownership, one root, the verdict record, the clock (§10.1, Ch. 12, §15.2–15.3, §9.2, §16.12–16.13, Ch. 13)

> The falsifiers are **M** on the protocol structure, **C** where a claim rests on a named design premise;
> the Ch. 13 re-grading is folded into the protocol-minimality entry (Part I.5).

### Inv-8 — Obligation-Ownership (§12.13)
- **Claim.** Inv-8 (§12.13), its per-state clause derived from Inv-4's reading, its edge clause adopted
  (§12.13, §20.5 (d)).
- **Type.** M over the owner table (a per-state stipulation; the existence of the owner's move is decided off
  the canon table, `inv8_canon`, with the negative control `control_inv8_fails_on_empty_escalated`); C on the
  premise.
- **Falsifier.** A reachable state with work begun and not over whose owner has no admissible own signal, or a
  transition into a state with neither owner nor settlement.
- **Tested?** — analytic; machine-checked over the base table (§20.4).

### A node's issuer is Del(parent) (§10.1, §12.13)
- **Claim.** The issuer role (§10.1, §12.13), its disclosed cost (§16.13).
- **Type.** M (derived relative to the design decisions, §20.5 (d) — its alternatives excluded by Inv-7 and
  §10.3).
- **Falsifier.** A reachable graph state with a live node in an issuer-owned state whose issuer holds no
  admissible move on it.
- **Tested?** — analytic; not model-checked (the formal models carry no Del identities, §12.15).

### One goal, one root; D a forest (§15.2–15.3, CHECK-2)
- **Claim.** One goal, one root (§15.2); D a forest, CHECK-2 operationalizing it (§15.3).
- **Type.** M.
- **Falsifier.** A goal whose verdict is well-defined over two parentless nodes; a node with two parents
  whose issuer and public/internal status are both well-defined; or a cycle in D under which A2's
  κ-recursion still bottoms out in leaves.
- **Tested?** — analytic.

### CHALLENGE after consent (§12.4, §16.12)
- **Claim.** The post-consent CHALLENGE edges (§12.4, §13.3), what they carry (§16.12).
- **Type.** M for what `preC1_adequate_without_the_edges` checks (machine-checked); the row-forcing argued, on
  the per-state reading of §11.2 the canon applies to REWORKING's BLOCK; C on §16.12's feature list.
- **Falsifier.** A work state in which a spec defect cannot be met (⟹ the row does not reach it); or a
  post-consent spec dispute routed through BLOCK that keeps both §16.12 closures (⟹ the edges are not
  IC-forced).
- **Tested?** — analytic (grade machine-checked, §20.4).

### Conformance of an implementation (§12.16, closing paragraph)
- **Claim.** The conformance clause (§12.16).
- **Type.** C — on §16.12's feature list and §12.16's reading of a signal as a report.
- **Falsifier.** An implementation meeting the clause's three conditions in which a §16.12 feature lapses or an
  owner is left without a move (the clause too weak); or a canon requirement that no refusal admitted by its
  refusal condition can operationalize, while one outside it removes no §16.12 feature (the clause too strong).
- **Tested?** ◻ — the reference engine's refusals are the first object it applies to.

### The verdict is binary on every criterion; no register waives one (Inv-2, §12.8, §9.2)
- **Claim.** Inv-2's per-criterion record (§12.8), the register's line (§9.2), the mode of a PASS over a
  waived criterion (§8.4, §12.8).
- **Type.** M (from §7.1's |L| = 2 and §9.2's risk/scope line).
- **Falsifier.** A third per-criterion value that changes the action and reduces neither to pass/fail nor to ⊥
  (⟹ |L| = 2 breaks); or a register entry that exempts a written criterion without a revision while the verdict
  over it stays a true statement of the criteria as written (⟹ the register is a scope instrument after all).
- **Tested?** ◻ — `EVIDENCE_LOG` §13.16 records contract requirements filed as accepted risks after a FAIL, which
  the rule classifies as false passes; a classification, not a test of the rule.

### The protocol attributes no expiry (§12.2)
- **Claim.** No expiry attributed to a party (§12.2), a design decision (§20.5 (d)) on the ground §12.2 states.
- **Type.** M (analytic on §16.10 / §16.12) for "no row rests on attributing one"; the refusal to attribute is
  itself a design decision, on that ground.
- **Falsifier.** A §16.10 or §16.12 row whose dominance argument fails unless an expiry is attributed to a party
  (⟹ attribution is load-bearing); or an expiry-attribution rule that leaves the honest abstention in OFFERED
  unpriced (⟹ the ground for withholding it fails).
- **Tested?** — analytic.

---

## Provenance

The systematic falsifiability pass; tracks canon **v4.1** — every §-citation
is to its Chapters 0–20. The Part III.N headings keep their version labels: they record *when* a claim entered
the register, not where it now lives. Originally written against v3.5, then extended for the v3.6
agent-free-ontology + methodology layer in Part III.6, the continuous-substrate + 3-axis-faithfulness layer in
Part III.7, the v3.7 protocol-rigor edits in Part III.8, the v3.8 metric edits in Part III.9, the v3.9
canon-status re-levelings + Lean machine-check in Part III.10, and the v4.1 ownership / one-root /
verdict-record / clock layer in Part III.11. Since v4.1 an entry names its claim by § instead of restating it
(the restated copies were what drifted).

> *Label note (v3.6).* The §4.6 **predictions** are tagged **Pred-1/Pred-2/Pred-3** (substitutability /
> applicability boundary / global falsifier) to keep them disjoint from canon's reserved **P3** (Blackwell,
> Prop 3 §16.2) and from the agent-necessity **derivation steps d1–d6** (§4.1). Three distinct series, no
> token collision.

On any canon ↔ register disagreement, the canon is authoritative and this file is corrected.
