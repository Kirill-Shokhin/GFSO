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
  doc — now WRITTEN at `docs/e1/scrum_worked_examples.md`.

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

> **UPDATE 2026-05-29: deltas A–D are MERGED into canon `applied_gfso_v3.md` v3.3-wip**
> (after 2 critic rounds incl. a neutral ontology-derived one; record in canon Changelog +
> EVIDENCE_LOG §9). Track A was RE-RUN then CORRECTED via the
> v3.1 root-cause gate (`runs/e1_results/rerun_leaderboard_corrected.md`): **fit 97.2%
> (210/216), passes ≥95%** (v2 was 94.4%). FM-1=142 (a71/b53/d13/c5), FM-3 incl. 10 false-FAIL,
> **NONE=6 (3 §16.2 third-party + 3 resilience-worked, 0 uncovered FM)** — true residual = 3,
> matching the ~2-3 prediction (3 independent reads converged). §4.8's operational-axis residue
> was also CLOSED (derived from A1, via a critic round; EVIDENCE_LOG §9.1). **E1 is complete.**
> **Delta E (§18.1 / theory-model) ✅ MERGED 2026-06-01 → canon §18.10 (v3.4)** via
> delta→3-fresh-neutral-critics; record EVIDENCE_LOG §10. (The §4/§4b scaffold was removed —
> dozrelo, ushlo.) Items below remain the live thinking.

1. **Re-analyze the 12 NONE via STD-2 triage** — ✅ DONE (session 2026-05-29). Not the
   binary "most → FM-1" I expected; the cluster splits **three** ways:
   - **6 → FM-1** (resilience-insufficiency, mostly STD-2 missing-mitigation-child): 033
     (high, self-admitted capacity gap), 009 (medium), 022/039 (low; **022≡039 semantic
     duplicate**), 017, 027 (low — prevention is genuinely §2.1, only detect/respond is FM-1).
   - **2 → no FM at all because resilience WORKED** (029 power, netflix-001 AZ-evac) — these
     are *positive* evidence, a third bucket the binary framing missed.
   - **4 → true residual outside non-adversarial scope**: §16.2 adversarial (okta-001,
     cloudflare-019, cloudflare-031) + §2.1 boundary (cloudflare-035, customer-chosen 2-hop dep).
   Net: claim "NONE ≠ a GFSO gap" **holds** (0 cases need an 8th FM), but via three routes,
   not "all FM-1." Key refinement: "external trigger" classifies nothing by itself — the
   **choice of parent goal** + STD-2 predictability is the router. Feeds Delta C (FM-1.b).
2. **FM-1 sub-taxonomy + FM-3 false-FAIL** — ✅ MERGED in canon §4.2; Track A re-run done
   (corrected leaderboard). 
3. **Scrum before/after A/B analysis** — ✅ DONE: `docs/e1/scrum_worked_examples.md` (causal
   primitive→FM, before/after, house natural-experiment). **Track B is CLOSED for E1.** A fuller
   per-case primitive embedding = full-decomposition work → revisit at E3/decomposition only, NOT
   an E1 item; don't stretch it now.
4. **§18.1 / theory-model transition** — ✅ **DONE & MERGED 2026-06-01 → canon §18.10** (agent
   derived necessary; Lemma 1+3; distributed falsifiability; bidirectional attribution; explains
   pre-theoretic success/7 FM/§18.1; predicts substitutability/scope/global-falsifier). Cycle +
   residues in EVIDENCE_LOG §10. Metaphysics route kept out of docs (agent memory only).
5. **(Later) E3** for the compositional theorem T1 — needs a different data source
   (multi-agent decomposition with per-subtask V); postmortems can't test it. **E2 first.**

Also ✅ MERGED: 7-FM completeness as theorem-modulo-axioms (canon §4.8); STD-1/2/3→FM-1 (§5.5).
**Live next (post-theory-model, separate streams):** systematic **falsifiability pass over the
whole canon** (each claim → what falsifies it — only spot instances exist now); principled
FM-1.b↔§2.1 boundary criterion; Axiom-2 single-clock scope. Then E2, E3.

---

## 8. How this file relates to the others

- `CORE.md` — what GFSO IS (anti-drift, 1 page). Unchanged by any of the above.
- `applied_gfso_v3.md` — the formal theory. §4 (FM), §5 (STD), §17.1/17.2 (stratification/
  Scrum), §18.1 (causal correctness, open). The edits in §2/§4 above target these.
- `EVIDENCE_LOG.md` §9 — the dry record (numbers, artifacts, what-was-run).
- THIS file — the live interpretation + theory direction. When a synthesis here gets
  formalized into applied_gfso_v3, move it there and leave a pointer.
