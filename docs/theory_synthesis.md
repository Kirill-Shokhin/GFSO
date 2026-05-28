# GFSO — Working Synthesis (live understanding, theory-facing)

> Read this to INHERIT the current thinking, not just the results. The dry record
> (numbers, what-was-run, artifacts) lives in `EVIDENCE_LOG.md` §9. This file is the
> non-dry layer: theory-direction, candidate refinements, standalone ideas, the
> synthesis reached through discussion. Written so a fresh agent reads it and picks
> up exactly where the thinking is — not where the data is.
>
> Confidence is marked. "Proven", "derived", "candidate", "metaphor", "open".
> Do not flatten those — the seams are the point.

---

## 0. Where we are (one paragraph)

E1 (the falsifiable test "are the 7 FM exhaustive?") was built and run: a 230-record
verbatim postmortem corpus (216 incidents + 14 Scrum process-cases) classified by Opus.
Result: in-scope completeness holds, but FM-1 is over-broad (63%) and several boundary
findings emerged. §17.2 (Scrum ⊂ GFSO) held with zero counterexamples on 14 cases.
Everything below is the *interpretation* of that, plus theory moves it suggests.

---

## 1. The two-axis correction (load-bearing — I got this wrong first, then fixed)

The 7 FM are failures of **ONE axis**: compositional validation (the molecule
`V(parent)=AND(V(children))` breaking). There is a **SECOND axis** the FM neither
cover nor should:

- **Compositional axis** → the 7 FM. "Did the decomposition's parts correctly compose?"
- **Boundary/coverage axis** → STD-1 (NEGLECTED), STD-2 (predictability), §2.1, §16.2.
  "Was the right thing inside the decomposition at all, and where is the model's edge?"

**The mistake to NOT repeat:** the 12 NONE incidents (external-dependency, adversarial)
are NOT a GFSO gap, and NEGLECTED is the WRONG lens for them. NEGLECTED (STD-1) =
*conscious abdication* — "I declare I ignore X, with justification" — it shifts
responsibility off the executor and lowers cost, but it does **not solve X**. A
predictable external dependency (power, BGP, upstream DNS) is an STD-2 *ordinary/
statistical* risk that GFSO says must be **decomposed into a mitigation child**
(redundancy/failover). Absence of that child = **FM-1 insufficiency** at the resilience
layer. So most NONE are mis-scoped FM-1 (the classifier took "external trigger" as the
cause instead of "we failed to decompose redundancy against a foreseeable failure").
The prepared forester decomposed "survive" into {knife, spare clothes} — that's
decomposition, not neglect.

**Correct second-dimension classification for NONE = STD-2 triage:**
ordinary → FM-1 (must-decompose) · statistical → FM-1-or-justified-NEGLECTED ·
extraordinary (no precedent AND not derivable) → §2.1 boundary · adversarial → §16.2.
True residual (genuinely out) ≈ adversarial + extraordinary only (~2-3, not 12).

---

## 2. FM taxonomy refinements (concrete theory edits suggested by the run)

- **FM-1 is complete-in-scope but under-discriminating (63% of incidents).** It absorbs
  "any missing safeguard/criterion." Not wrong, coarse. **Edit: sub-taxonomy of FM-1** —
  missing-test / missing-guard / missing-capacity / missing-approval / missing-graceful-
  degradation. Must be done WITHOUT breaking the §4.4 completeness proof (sub-types of
  insufficiency, not new top-level FMs). GitHub worst (79%) partly a writeup artifact
  (availability reports phrase every fix as "added the missing check").
- **FM-3 (Verifiability) covers only false-PASS, not false-FAIL.** A live master judged
  dead → bad failover (github-081, buildkite-001 fail-closed, queensland shipped-despite-
  expected-fail) doesn't fit FM-3's strict false-positive definition. **Edit: FM-3 should
  cover both error directions of validation** (false-pass AND false-fail). Check this
  doesn't disturb the §4.2 "values → truth" derivation — false-fail is still a truth
  defect of V(child), so it should slot in cleanly.

---

## 3. Scrum ⊂ GFSO — split the claim into two; one is proven, one is open

I conflated these; keep them separate.

- **(A) Structural containment: Scrum's parts ⊂ GFSO's parts.** PROVEN on 14 cases
  (Track B, 0 unmapped). Every mechanic (PO, backlog, sprint, DoD, daily, Scrum Master,
  retro, velocity, burndown, self-org) maps to a primitive / impl-choice / constraint.
- **(B) Dynamical generation: GFSO *derives* Scrum's exploratory power from axioms.**
  NOT shown. We showed the pieces match; not that A1+A2 generate why iterative
  refinement works for the unknown.

**Weak-A1 vs ¬A1 (the membership test):** Scrum lives in **weak-A1** — criteria *exist*
(DoD is a real binary check) but are discovered iteratively, not articulated upfront.
That is INSIDE GFSO. ¬A1 (no decidable criteria possible even in principle — "improve
culture") is the §2.1 boundary, OUTSIDE. Scrum is not ¬A1, so coverage is legitimate,
not forced. And the machinery for "discover criteria iteratively" is DERIVED, not bolted
on: CHALLENGE is one of the 12 signals (from FM-7); §17.1 adaptive stratification is a
corollary of Dep-coherence + A1.

**Honest verdict: ~70% there.** Containment (A) solid and not forced. Sufficiency (B) —
plausible, partly derived (§17.1), not closed. The remaining bar (your bar): show GFSO
*generates* the exploratory dynamics, not just contains the parts.

**Richest untapped analysis — the before/after A/B (DO THIS):** each rich Scrum case has
a BEFORE (failed approach: FBI VCF+Lockheed waterfall ~$575M) and AFTER (Scrum success).
- BEFORE = a failure → FM-classifiable (which primitive was missing?)
- AFTER = working process → embedding (which primitives present?)
- **DELTA = the primitive the before lacked that the after supplied → a causal
  "primitive X fixes failure-mode Y" claim.** This is richer than either incident-FM or
  Scrum-embedding alone, and it's the closest the corpus gets to a causal result. The
  doc `scrum_gfso_worked_examples.md` was proposed but NEVER written — write it here.

---

## 4. The implicit/explicit duality, and a candidate STRUCTURAL closure of §18.1

This is the most promising theory move and the answer to "can we close causal
correctness now, through the fundamental?"

**The duality (strong, and I think correct):**
- **LLM / diffusion**: the domain's causal manifold is **learned from data** — latent,
  in weights, not inspectable, probabilistic. Produces the right answer without being
  able to state *why*.
- **GFSO causal correctness (§18.1)**: the domain structure must be **explicitly
  declared** in the decomposition — inspectable, binary-verifiable. Cannot proceed
  correctly without stating *why* (the decomposition IS the explicit structure).

These are **inverse epistemics**: implicit/learned vs explicit/declared. §7.3 already
puts the LLM as a Level-2 workaround; the duality says *why* that's necessary, not a hack.

**Candidate closure (this is the new bit — mark it CANDIDATE, not proven):**

§18.1 ("how to know a decomposition is causally *correct*, not just formally complete")
may not be an incompleteness of GFSO to be *fixed*, but a **forced coupling-point**,
characterizable structurally:

1. A1 (verifiability) + A2 (decomposability) contain **no domain causal structure**.
   Verifiability says predicates exist; decomposability says tasks split. Neither tells
   you whether a given split *mirrors the domain*. So causal correctness is
   **extra-axiomatic** — not derivable from A1+A2 by construction.
2. Extra-axiomatic domain structure has only two sources: **declared** (which is just
   more GFSO decomposition — recurses, doesn't bottom out at a ground truth) or
   **learned** (empirical/statistical — the LLM paradigm). The declarative regress
   terminates only at empirical knowledge.
3. Therefore causal correctness is **fundamentally empirical**, and GFSO — the explicit/
   declarative half — *structurally cannot* supply it from its own axioms. The implicit/
   learned paradigm is the necessary complement.

If steps 1-3 hold, §18.1 flips from "open problem (find the algorithm)" to
**"characterized boundary: the precise point where GFSO must couple to the inverse
(learned) paradigm; the coupling is forced because the axioms don't contain domain
structure."** That is a *recharacterization*, not a solution — but it might be the
correct one, and it upgrades §7.3.3's cross-impossibility (Solver can't reason about
domain; LLM can't guarantee P=0) into a general statement about the two paradigms.

**What's needed to make it real (not yet done):**
- (a) argue the declare-or-learn dichotomy is exhaustive (like the FM case-split style);
- (b) show the declarative regress provably doesn't bottom out without empirical input;
- (c) connect formally to §7.3.3 and to §10.3 (two fallible structure-estimates compose:
  γ_declared · γ_learned — agreement reduces error but correlated error survives, so
  even the coupling doesn't give P(error)=0 — which is itself the honest limit).

**Seam to watch:** this could become a circular "GFSO is incomplete by design, therefore
complete" rhetorical trick. Guard against it: the claim is only strong if the dichotomy
(a) is genuinely exhaustive and (b) the regress argument is rigorous. If those wobble,
it's just a restatement of "we use an LLM."

---

## 5. Horizon → challenge (the derived chain; keep the metaphor separate)

Horizon comes from decomposition (your point, correct): parent → sequence of children,
each child → its own sequence; with duration + ordering, lower levels are multiples
shorter. This is §17.1's premise + Dep-coherence (`deadline(parent) > deadline(child)`).

**CHALLENGE-the-signal** derives *immediately* from FM-7 (need a back-channel for a
defective spec) — no frequency argument needed. (Your minor correction — noted.)

**CHALLENGE-frequency scaling with depth** is the separate §17.1 corollary:
short horizon → criteria must be concrete → concrete criteria are tightly coupled to
current environment state → environment drifts at some rate → fraction of a task's
horizon hit by drift = Δt/H_k → smaller H_k (deeper) → larger fraction → higher chance
the environment diverges from the criteria *mid-task* → CHALLENGE fires more often.
So horizon (from decomposition) DRIVES challenge frequency. Scrum's "stable vision (long
horizon, rare challenge) + daily-churning tasks (short horizon, frequent challenge)" is
the OBSERVED consequence of this — which is why Scrum connects here structurally.

**Diffusion overlay = METAPHOR, not derivation.** Coarse→fine across horizons resembles
denoising; §10.3 cascade (‖eₙ‖≤(L·γ)ⁿ‖e₀‖) genuinely formalizes "crooked top → unrealistic
result" (large e₀ amplified down the tree unless validation keeps L·γ<1). But the
diffusion framing itself is illustration, not proof. Load-bearing = §17.1 + §10.3. Don't
sell the diffusion connection as established; it's a thinking aid pointing at §18.1
(diffusion *learns* the manifold; GFSO *declares* it — same duality as §4).

---

## 6. Terminology: "leaderboard" → "failure-mode atlas"

There are no leaders (incidents are failures, not a ranking; Scrum cases are mostly
successes). The object is a **failure-mode atlas**: distribution of how real systems
fail, mapped to the formal taxonomy, sliced by domain. Drop "leaderboard."

---

## 7. Open theory questions / next moves (priority order)

1. **Re-analyze the 12 NONE via STD-2 triage** (§1 above). Expect most → FM-1; isolate
   the true §2.1/§16.2 residual. This sharpens the completeness claim honestly.
2. **FM-1 sub-taxonomy + FM-3 false-FAIL** (§2), then re-run Track A. Theory change → re-run
   (the corpus + annotations layer is built for exactly this; annotations re-generate,
   corpus untouched).
3. **Scrum before/after A/B analysis** (§3) — write `scrum_gfso_worked_examples.md`. The
   causal "primitive X fixes FM Y" payload.
4. **Develop the §18.1 structural closure** (§4) — the highest-value pure-theory move.
   Try to make (a)/(b)/(c) rigorous. If it holds, it's a real contribution; if it
   wobbles at the seam, drop it honestly.
5. **(Later) E3** for the compositional theorem T1 — needs a different data source
   (multi-agent decomposition with per-subtask V); postmortems can't test it.

---

## 8. How this file relates to the others

- `CORE.md` — what GFSO IS (anti-drift, 1 page). Unchanged by any of the above.
- `applied_gfso_v3.md` — the formal theory. §4 (FM), §5 (STD), §17.1/17.2 (stratification/
  Scrum), §18.1 (causal correctness, open). The edits in §2/§4 above target these.
- `EVIDENCE_LOG.md` §9 — the dry record (numbers, artifacts, what-was-run).
- THIS file — the live interpretation + theory direction. When a synthesis here gets
  formalized into applied_gfso_v3, move it there and leave a pointer.
