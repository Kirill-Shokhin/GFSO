# GFSO — Experimental Evidence Log

> The record of empirical work on GFSO: every study, what it measured, what it did not, and what
> it left open. This is the file to hold the project's claims against — it is the source of "what
> has actually been shown" as opposed to "what is still hypothesis".
>
> **Sections 0 and 5–8 are absent by design.** They were process — this document's own purpose, a
> roadmap, a survey of an earlier private repository, next steps, and instructions to whoever picked
> the work up — and the log's own policy (below) admits none of it. They were moved out rather than
> renumbered, so every citation of §9, §11 or §13 elsewhere still lands where it always did.
>
> **Section numbers are as of each entry's date.** Entries written before the v4.0 canon cite the
> numbering then in force (the v3.9 draft, which the v4.0 canon re-authored); renumbering them would falsify
> the record. Where a later pass corrected a reference inside an older entry, that one reference
> carries the v4 number while its neighbours keep theirs — the entry's date still fixes the period.

---

> **First read `docs/CORE.md`** if you need the GFSO definition. This file
> assumes you already know what GFSO is and need experimental context.

> **⚠ Section numbering in §1 and §9 is the theory document's v3 numbering.** Those two sections
> were written against canon v3 and are kept as taken; the canon is now v4.0 and renumbered, so
> `§17.1`, `§17.2` and `§7.3` cited there resolve to nothing in `applied_gfso_v4_en.md`. Everything
> from §10 onward cites v4. Do not chase a v3 reference into the current canon — it is a dead
> pointer, not a missing section.

## 1. Vision context (what GFSO is, restated)

### What GFSO is NOT
- Not a productivity tool — "what metric does it boost" is a category-mismatched question
- Not a project-management methodology
- Not "yet another standard" at ISO 9001 / Scrum / Kanban level
- Not an algorithm or ML technique
- Not "agentic framework v2"

### What GFSO IS
- A **formal language for the minimum a verifiable task-handoff transaction must carry**
- An **infrastructural layer** for hierarchical work systems — analog to TCP/IP for
  networks or Codd's relational algebra for databases. Tractable math; the framing
  enables a domain.
- A **discipline shift**: responsibility for articulating criteria moves from Executor
  (who currently has to guess) to Issuer (who must specify before delegation).
- Derivable from two axioms (A1 verifiability, A2 decomposability), with all primitives
  shown minimal and several uniqueness theorems (|L|=2, AND-aggregation, 7 FM
  exhaustiveness).

### What GFSO uniquely provides over its parts
Decomposition exists. Tests exist. Contracts exist (DBC, Meyer 1992). Audit trails
exist. What none of them give together:

1. **Compositional validation theorem** — V(parent) = AND(V(children)) derived, not
   postulated, under explicit correctness conditions (joint sufficiency + non-redundancy).
2. **Failure-mode taxonomy with completeness proof** — any breakdown of compositional
   validation falls into one of 7 FM. Falsifiable.
3. **Forced binary V as forcing function** — criteria that can't decide pass/fail are
   bad criteria; binary V pushes spec defects out instead of hiding them in "warning".
4. **Standardized protocol vocabulary** (12 signals, 12 states) across role boundaries.
5. **Self-measuring metrics** computed from the audit graph itself.
6. **Adaptive stratification by horizons** (§25.1, derived) — top layers stable, bottom
   layers fast-changing CHALLENGE-cycles. Not a separate principle of agile/lean —
   a consequence of deadline coherence along D + A1.

### Domain the author actually targets
The under-optimized space of **human work coordination at scale**. Algorithms and
neural nets are heavily optimized; the protocol of "how two parties agree on what
counts as done" remains ad hoc 2026. The optimization opportunity here is plausibly
larger than another percentage point on a ML benchmark — but uncoordinated, uneven,
slow to converge because there's no formal substrate. GFSO is an attempt at that
substrate.

### Critic-resistant framing
| Critic move | Answer |
|---|---|
| "What metric does it boost?" | Category-mismatched. Asks GFSO to be productivity tool. Analog: "what metric does TCP/IP boost?" |
| "Just another standard like ISO" | ISO is chosen convention. GFSO is derived from axioms + proven minimal. |
| "1990s contracts/TDD already did this" | DBC describes atom (predicate on function). GFSO describes molecule (transaction structure in hierarchy). Different abstraction levels. |
| "Half-solving to specify" | Category error. API spec ≠ implementation. Drawing ≠ building. |
| "Scrum works without all this" | Scrum is a special case (§25.2) under constraints: depth(D)≤2, ACCEPTED_RISKS=∅, CHECK-7/8 unused, audit informal. Works where those relaxations are cheap; breaks where they're not. |
| "Abstract math divorced from reality" | Currently partly fair. Two empirical anchors (formal correctness; +34pp E0 result). Open work: E1 postmortem mapping, E2 LLM Issuer, E3 multi-agent. |

### Status (2026-05-23) — historical snapshot, superseded by §9 (E1 executed/closed)
- Theory document: formally complete (v3), latest additions §17.1 + §17.2
- Code framework: `gfso/` (core+adapters) + `bench/` (harness) — clean separation,
  tested via two providers (LiveCodeBench, BigCodeBench-Hard)
- Empirical anchors: **one strong** (E0 below), several mechanical-pipeline validations
- Gaps (as of this snapshot): E1, E2, E3 not yet executed; semantic completeness of
  criteria (Level 2 in §5.4) remains open as §18.1. **Superseded:** E1 since executed and
  closed (0/216) — see §9/§9.1.

---

## 2. Theory history (for context)

### Pre-v3: category-theoretic version
There existed an earlier theory formulation based on category theory (Kleisli arrows,
Wasserstein-style monads). Mathematically strong but **disconnected from applicability**.
The author confirmed this themselves while building a previous agent system
(the older `gfso-agent` repo) — abstractions didn't reduce
to actionable engineering choices, agent system was "smeared across the formalism",
hard to debug.

### v3.9 — re-authored as the v4.0 English canon, `applied_gfso_v4_en.md`
Reformulated **from operational concerns**: what does a task-handoff require
formally, derived from A1 + A2. Math became tractable (basic logic, finite
enumeration, Dirichlet). Doesn't depend on the category-theoretic GFSO Theory at
all — uses classical references (Blackwell, Simon, Hurwicz) directly. The reason
this iteration is what we keep building on.

Lesson learned: **math depth ≠ usefulness**. A formalism is useful when its
primitives map directly to operational decisions. v3 has that property; the
category-theoretic version did not.

### Older agent experiments (gfso-agent repo, pre-v3 era)
Author ran HLE-based experiments with the old theory: decomposer + validator +
workers in a swarm format, tested on the first 10 HLE problems with multiple
configurations per task. Results were mixed; the system was hard to control
because the theory didn't reduce to debuggable choices. Repo exists at
the older `gfso-agent` repo — needs review and lessons distilled into
this log.

---

## 3. Experiments completed

### E0a: LiveCodeBench run 1 (initial — with methodology bugs)
- **Setup**: 168 medium problems; Haiku 4.5 with GFSO loop (max_iter=3) vs Haiku
  one-shot best-of-k where k = GFSO LLM calls. Criteria generated by regex from
  public examples + constraint extraction. LeetCode tasks treated as stdin/stdout.
- **Result**: A=72/168 (42.9%), B=101/168 (60.1%), Δ=+29
- **What this tested**: GFSO loop's value when criteria are weak
- **Bugs found and fixed**: Windows subprocess pipe deadlock, `eval(input())`
  instruction broke AtCoder, LeetCode starter_code ignored, JSON corruption from
  concurrent writes, test suite consumption bug
- **Verdict**: Initial +29 was **inflated by methodology bugs**, not GFSO value
- **Lesson**: weak criteria measurements give misleading numbers; methodology bugs
  inflate apparent uplift

### E0b: LiveCodeBench run 2 (after fixes)
- **Setup**: same as E0a, all bugs fixed
- **Result**: A=102/168 (60.7%), B=108/168 (64.3%), Δ=+6
- **Per platform**: LeetCode +7.8pp, AtCoder -2.6pp, Codeforces +1 (n=2)
- **Coverage analysis**: precision (real PASS | criteria PASS) = 76.3%; recall
  (criteria FAIL | real FAIL) = 45%. LeetCode 88%/72%, AtCoder 64%/19%.
- **Stochasticity**: 25-27% of tasks flipped solved/unsolved between runs
- **What this tested**: GFSO loop with regex-derived weak criteria, fair compute
- **Verdict**: loop gives marginal +3.6pp at ×1.38 compute; correlation with
  criteria quality (LeetCode richer → +7.8pp, AtCoder bare examples → −2.6pp)
- **Lesson**: GFSO effect scales with criteria quality. Loop alone doesn't help
  when criteria are poor.

### E0c: Bench perfect (criteria = hidden tests)
- **Setup**: proxy upper-bound experiment. Criteria built from hidden test pairs.
  LLM doesn't see test inputs until they fail.
- **Result on probe tasks**: GFSO loop converged in 1-2 iterations on many; some
  AtCoder regressions because subprocess output mojibake on Windows
- **Bugs found and fixed**: Verifier-storage isolation (verifier had own storage,
  engine had own — failed criteria didn't reach REWORK feedback);
  per-failure truncation cut off expected/got; docstring duplicated in rework prompt
- **What this tested**: GFSO loop ceiling with strong criteria, and feedback quality
- **Verdict**: loop works with good criteria; criteria-as-raw-I/O is a proxy, not
  real GFSO criteria; we identified format issues blocking effective rework
- **Lesson**: feedback format matters. Raw traceback noise hurts. Anti-regression
  hints in system prompt help (added).

### E0d: BCB-Hard with explicit criteria + GFSO loop
- **Setup**: BCB-Hard, test code shown as explicit acceptance criteria in initial
  prompt. GFSO loop with rework. Both A (one-shot best-of-k) and B (loop) see same
  spec. Probe set: BCB/89, 92, 93, 100, 108, 120, 124, 129, 139, 161, 162, 184,
  199, 208, plus retries.
- **Result on probe set (~14 tasks)**: most are solved by both A and B on first
  try (iter=0). Loop is **dormant**.
- **Notable case**: BCB/93 stuck at 4/5 across all 3 iterations — model can't
  deduce the missing logic even with tests visible.
- **What this tested**: GFSO loop's role when criteria are explicit
- **Verdict**: with explicit criteria, competent model (Haiku 4.5) solves first
  try; loop has nothing to fix
- **Lesson**: **loop is fallback, not core**. Criteria quality dominates.

### E0e: BCB-Hard zero-shot A vs B — explicit vs implicit criteria *(strongest result)*
- **Setup**: 148 tasks, Haiku 4.5, no loop, single attempt each. Two modes:
  - NO_SPEC: docstring only (standard prompt)
  - WITH_SPEC: docstring + test code as explicit acceptance criteria
- **Result**: NO_SPEC=43/148 (29.1%), WITH_SPEC=94/148 (63.5%), Δ=+51 (+34.4pp)
- **better/same/worse**: 52 / 95 / 1
- **Tokens**: 166K / 307K (×1.85)
- **Verified clean on smoke**: BCB/120 — same code in both modes except one
  expression. NO_SPEC: `num_days = (end - start).days + 1` (literal docstring
  interpretation of "inclusive"). WITH_SPEC: `num_days = (end - start).days`
  (matches `assertEqual(len(dates), (end-start).days)` in tests). No hardcoded
  answers — pure spec-driven correction of an ambiguous docstring.
- **What this tested**: price of unarticulated criteria at the Issuer side
- **Verdict**: same model, same compute, same tasks — explicit criteria DOUBLE
  solve rate. This is **measurement of the cost of having implicit specs**, on
  148 problems, Haiku 4.5. Cleanest empirical result we have.
- **Lesson**: criteria-articulation discipline at Issuer side is the dominant
  factor on this class of tasks. Not the loop. Not decomposition. Just spec
  precision. (DBC/TDD made the same claim qualitatively since 1986; we
  measured it on a strong frontier-adjacent model on a current benchmark.)

### Files / artifacts
| Artifact | Path | Purpose |
|---|---|---|
| Theory canon (v4.0) | `docs/applied_gfso_v4_en.md` | Source of truth for theory |
| LCB results r1 | `bench_results_1.json` | First run (with bugs) |
| LCB results r2 | `bench_results.json` | After fixes |
| Perfect results | `bench_results_perfect.json` | criteria=hidden_tests proxy |
| BCB explicit+loop | `bench_results_bcb.json` | E0d |
| BCB zero-shot | `bench_results_zeroshot.json` | **E0e — main result** |
| Per-task logs | `bench_logs*/` | Full LLM traces for every task |
| LCB provider | `experiments/e0_bench/bench/providers/livecodebench.py` | |
| BCB provider | `experiments/e0_bench/bench/providers/bigcodebench.py` | |
| Subprocess verifier | `gfso/adapters/verifiers/subprocess_verifier.py` | LCB-style |
| Unittest verifier | `gfso/adapters/verifiers/unittest_verifier.py` | BCB-style |
| Runner | `experiments/e0_bench/bench/runner.py` | A-vs-B orchestration |
| Zero-shot script | `experiments/e0_bench/run_bcb_zeroshot.py` | E0e |
| LCB script | `experiments/e0_bench/run_livecodebench.py` | E0a/E0b |
| BCB script | `experiments/e0_bench/run_bcb.py` | E0d |

---

## 4. What our tests actually proved vs didn't

### Proven mechanically
- GFSO engine works (FSM transitions correct, dispatch flows, audit trail forms)
- BenchAgent (single-agent FSM-driven loop) is implementable cleanly
- VerifierPort abstraction works across two domain adapters (subprocess + unittest)
- Bench harness (BenchProvider, BenchRunner, A-vs-B logic) is clean and reusable

### Proven empirically
1. **Criteria quality dominates loop value** (E0a/b/d combined): when criteria are
   weak, loop helps marginally; when explicit, loop is dormant. The loop is NOT
   where GFSO's value sits for single-agent tasks.
2. **Explicit-criteria articulation has measurable, large effect** (E0e): +34pp
   on Haiku 4.5 BCB-Hard 148 tasks. Strong empirical anchor for §11.2 (forced
   binary V) and the Issuer-side discipline thesis.

### NOT proven yet
- ~~7 FM taxonomy completeness on real-world incidents~~ → **E1 EXECUTED (§9/§9.1)**: 0/216 in-scope incidents need an 8th FM (completeness-as-basis holds)
- ~~LLM-Issuer with vs without GFSO discipline~~ → **E2 EXECUTED (§11)**, reframed as a convergence/optimality study (the twin A/B framing was retired)
- Compositional validation theorem in multi-agent decomposition (planned: E3)
- CHECK-1..8 effectiveness — no decomposition tested
- q_T, q_D, q_V (and the rest of Q) metrics predictive of real-world outcomes — no long deployment
- Causal correctness / Pragmatic-level semantic completeness (§13.4; a characterized boundary, §8)

### Conceptually clarified along the way
- **Scrum ⊂ GFSO formally** (§25.2): every Scrum primitive maps as direct
  equivalent, implementation-choice, or restriction. No Scrum primitive escapes
  GFSO. This kills the "Scrum is alternative" argument.
- **Adaptive stratification is derived, not an axiom** (§25.1): top stable / bottom
  fast is a corollary of deadline coherence along D + A1, not a separate "agile principle".
- **GFSO loop ≠ value of GFSO**: this was the most important course-correction. We
  spent weeks treating the loop as the test target. It's a fallback. The value
  is at Issuer-side articulation + composition + 7 FM diagnostics + audit.

### Bugs and lessons (anti-patterns to avoid)
- Don't run Windows subprocess with `capture_output=True` on infinite-output
  child — pipe deadlock. Fix: file I/O for stdin/stdout/stderr.
- Don't use `eval(input())` instruction in prompts — breaks AtCoder/Codeforces.
- Don't make verifier instantiate its own MemoryStorage when engine has another —
  results stored in wrong storage; build_dispatch_payload misses them. Fix:
  BenchTask.make_verifier(storage) factory called by runner with engine's storage.
- Don't iterate `unittest.TestSuite` after `runner.run()` — default `_cleanup=True`
  replaces tests with None. Capture ids before run.
- Don't duplicate problem description in rework prompt (it's already in prev_code's
  docstring). Drop the PROBLEM section in rework.
- Don't show raw Traceback noise in failure feedback — strip the header and File
  lines, keep the assertion call + error message.
- Don't hide test code as criteria for BCB-style benchmarks — tests ARE the
  contract, not the answer. Hiding them tests "guess the spec from docstring",
  not GFSO's spec-driven regime.
- Force matplotlib `Agg` backend in test subprocess on Windows or it spawns
  dozens of GUI windows during bench runs.

---

## 9. E1 EXECUTED — corpus build + classification, 2026-05-28

The plan for E1 (7-FM taxonomy validation on ~100 postmortems) was executed
at larger scale than planned. Full pipeline + data are LOCAL (gitignored under
`data/postmortems/` and `runs/e1_results/`); only tooling + this log are tracked.

### Phase A — corpus (data/postmortems/)
- **230 records / 49 sources / 1980–2026.** 216 incident postmortems + 14 Scrum
  `process_case` narratives (from Sutherland's book).
- Domains: ops_incident 199, project_delivery 7, safety_critical 7, security 3,
  process_narrative 14.
- Pipeline (experiments/e1_corpus/): walk_archive + fetch_postmortem (trafilatura
  verbatim, NOT WebFetch — WebFetch paraphrases, that was the first big bug),
  writeup agents, build_corpus (md→schema-v1.1.0 JSON), verify_verbatim.
- **Verbatim verified: 91.4% string-match** vs raw sources; misses spot-checked =
  formatting artifacts (PDF hyphenation, Wikipedia citation decoration, en-dash,
  table reflow), NOT paraphrase. Lower bound; real fidelity higher. 10+ sources 100%.
- Universe denominator: 193 orgs from danluu+howtheysre+k8s.af (Tier A=7, B=26, C=160).
  Shortlist = all Tier A + selective B + famous Tier C + Scrum/safety/historical we added.
- Schema v1.1.0: verbatim-first (Quote objects), taxonomy-agnostic, multi-annotator
  (`annotations[]` open), entry_type/domain/methodology tags. Built for a public artifact.

### Classification (runs/e1_results/)
Protocol: docs/e1/classification_protocol.md (v3.1). Annotator: **Opus** (consistency — do NOT
mix models across the corpus, it confounds the distribution). Two tracks.

**Track A (216 incidents → 7 FM):**
- fit 94.4% (204/216), NONE=12. FM-1=137 (63%), FM-3=37, FM-7=10, FM-2=7, FM-5=7,
  FM-4=3, FM-6=3. 117/216 needed a secondary FM.
- By domain: ops FM-1 heavy; project_delivery → FM-1/FM-6/FM-7 multi-causal;
  safety → FM-1/FM-2/FM-5/FM-7; security → FM-3 (crowdstrike bad-update) / NONE (okta).

**Track B (14 Scrum → §17.2 embedding):** 4 full, 8 partial, 2 out_of_scope,
**0 unmapped Scrum elements** = no §17.2 counterexample. Scrum ⊂ GFSO held on 14
real cases. Medco = cleanest "Definition of Done = Criteria"; Valve = degenerate
Issuer=Executor (still inside); NUMMI/Zappos correctly out-of-scope (not handoffs).

### FINDINGS (what we actually learned)

1. **7 FM are complete IN SCOPE, but FM-1 is too broad (63%).** Taxonomy doesn't
   collapse, but FM-1 absorbs "any missing safeguard/criterion". Under-discriminating,
   not incomplete. **Action: sub-taxonomy of FM-1** (missing-test / missing-guard /
   missing-capacity / missing-approval / missing-graceful-degradation). GitHub worst
   (FM-1 79%) partly a writeup-style artifact (availability reports phrase fixes as
   "added the missing check").

2. **FM-3 covers only false-PASS, not false-FAIL.** github-081, buildkite-001,
   queensland (live-judged-dead / shipped-despite-expected-fail) don't fit FM-3's
   strict false-positive definition. **Action: FM-3 should cover both error directions.**

3. **The 12 NONE are NOT a GFSO gap — they are the STD-2 / §2.1 axis, and most are
   mis-classified FM-1.** (Author correction to the orchestrator's first framing.)
   NEGLECTED (STD-1) is conscious abdication (shifts responsibility, doesn't solve) —
   the WRONG lens here. Predictable external-dependency failures (power, BGP, upstream
   DNS) are STD-2 *ordinary/statistical* risks that MUST be decomposed into mitigation
   children (redundancy/failover) → absence = **FM-1 insufficiency** at the resilience
   layer. The classifier marked NONE because it scoped the incident to "external trigger"
   not "we failed to decompose redundancy against a foreseeable failure." Re-framed with
   the right parent goal, most NONE collapse to FM-1. True residual (§2.1 boundary):
   only genuinely-extraordinary (no precedent AND not derivable) + adversarial (okta,
   §16.2). **Action: re-analyze NONE via STD-2 predictability triage**
   (ordinary→FM-1 / statistical→FM-1-or-justified-NEGLECTED / extraordinary→§2.1).

4. **Postmortems support only the FM label (± secondary), not full GFSO molecule
   decomposition.** A postmortem describes the FAILURE POINT, not the whole transaction
   (full criteria set, decomposition tree, per-child V). So the corpus is right-scoped
   for E1 (failure-taxonomy) but CANNOT test the compositional theorem T1 — that needs
   E3 (multi-agent decomposition with per-subtask V). Not a flaw; a scope fact.

5. **Scrum cases are under-analyzed and the richest untapped material.** Track B only
   did primitive-presence. Each rich case (FBI Sentinel, Medco, eduScrum, House) has a
   built-in **before/after A/B**: a BEFORE failure (waterfall, FM-classifiable) and an
   AFTER Scrum success (embedding). The DELTA = which GFSO primitive the before lacked
   that the after supplied → a causal "primitive X fixes FM Y" claim. Richer than either
   track alone. **Action (DONE): dedicated Scrum analysis (`docs/e1/scrum_worked_examples.md`).**

6. **Diffusion/planning-horizon intuition = §17.1 + §10.3 + §18.1.** Coarse-to-fine
   decomposition across receding horizons: §17.1 is the skeleton; §10.3 cascade
   (‖eₙ‖≤(L·γ)ⁿ‖e₀‖) already formalizes "crooked top → unrealistic result". The hard
   part — "every level follows the domain's true structure" — IS causal correctness
   §18.1 (open). Diffusion learns the manifold from data; GFSO has no analog (LLM-layer
   §7.3 + q_D are the workaround). **Scrum junction:** when the domain model isn't known
   upfront (weak-A1), Scrum DISCOVERS the coarse structure through iterations (each
   sprint = a denoising step that adds detail + corrects via CHALLENGE). This is the
   direct GFSO↔Scrum connection and is NOT yet experimentally nailed.

### "Leaderboard" reframe
There are no "leaders" — incidents are failures, not a ranking; Scrum cases are
mostly successes. The right object is a **failure-mode atlas**: distribution of how
real systems fail, mapped to the formal taxonomy, sliced by domain. Term "leaderboard"
doesn't fit.

### Artifacts (local, gitignored)
- `data/postmortems/corpus.json` (230, schema-valid) + index.json + schema.{md,json}
  + sources/ raw/ manual/ meta/
- `runs/e1_results/leaderboard.md` (the atlas) + annotations.json (230) + part_*.json
- `runs/e0_bench/` = the prior BCB/LCB criteria-gate bench (E0, +34pp)

### 9.1 — v3.3 theory update + Track A re-run (2026-05-29)

The §9 findings were worked into canon **v3.3-wip** through 2 critic rounds (one neutral,
ontology-derived). Provenance now lives here + in the canon Changelog (the working delta drafts
were consolidated away after merge). Merged:
- **FM-3 two-directional** (false-PASS ∧ false-FAIL) — §4.2/§4.6.
- **FM-1 sub-taxonomy** a–e (secondary tag, no new top-level FM) — §4.2.
- **Completeness reframed partition → basis** ("≥1 FM, conjunctions allowed", not "exactly
  one") — §4.4 + new **§4.8** (formal: CVC≡⋀Cᵢ, Axiom-1 covering, Axiom-2 atomicity; intra-
  component properties DERIVED — values←A1+§3.2, rule←§3.3, args←§2.2; **operational axis also
  DERIVED** — trichotomy of linearly-ordered local time, grounded directly in A1's finite-time
  clause (closed via a neutral critic round; only residual cost = Axiom-2
  single-clock scope). Driver: internal overclaim + E1's 117/216 secondary-FM rate. *(v3.9: single-clock discharged — phase count axiom-free, §4.8/§18.12.)*
- **STD-2 = admissibility (not coverage); STD-1/3 operationalize joint-sufficiency** — §5.5.
- Changelog added to canon.

**Track A RE-RUN (protocol v3, all-Opus, 216 incidents)** — `runs/e1_results/rerun_*` +
`rerun_leaderboard.md`. Empirical verification of the deltas:
- **Completeness-as-basis HOLDS: 0/216 need an 8th FM.** All 17 NONE are router-sanctioned
  out-of-scope: adversarial §16.2 ×10, resilience-worked ×3, boundary §2.1 ×3, extraordinary ×1.
  Single genuine stress-point = **ovh-001** (physical datacenter fire — extraordinary, neither
  software-mitigable nor a decomposition defect). Not an uncovered FM.
- **FM-1 63%→60.6% and now DISCRIMINATED:** a(missing-criterion)=70, **b(missing-resilience)=43**
  (the STD-2 router pulling former external-NONE into FM-1, as predicted), d(insufficient-
  entailment, a Level-1 class invisible in v2)=13, c(risk-grouping)=5.
- **FM-3 37→43, with 10 false-FAIL** (over-rejection: healthy-judged-dead, fail-closed) + 35
  false-PASS — the false-FAIL class was uncatchable under v2. Delta B validated on data.
- **NONE corrected via the v3.1 root-cause gate (the key fix).** The first v3 pass over-assigned
  NONE (17) by keying on *trigger* (an attacker/fire/vendor existed) instead of *root cause*. The
  gate (protocol rule-5 GATE): an external/adversarial trigger is NOT out-of-scope if a standard
  domain mitigation was missing (patch, RPKI, rate-limit, isolation, geo-redundancy,
  **fire-suppression**, 2FA). Re-triage of the 17 (Opus, `rerun_none_retriage.json`):
  **11 → real FM** (10 FM-1.b missing-resilience + 1 FM-1.a Cloudbleed), **3 → genuine §16.2**
  (all third-party: cloudflare-019 customer's registrar, cloudflare-042 vendor breach, okta-001
  Sitel endpoint), **3 → resilience-worked** (evidence-FOR: cloudflare-017/029, netflix-001).
  **§2.1 boundary = 0** — ovh-001 (datacenter fire) → FM-1.b (fire-suppression + geo-redundancy
  are standard mitigations; the author's point). So **true out-of-scope residual = 3, matching
  the synthesis prediction of ~2-3** (three independent reads — prediction, author-intuition,
  root-cause re-triage — converged).
- **CORRECTED distribution** (`rerun_leaderboard_corrected.md`): FM-1=142 (a:71, b:53, d:13, c:5),
  FM-3=43 (incl. 10 false-FAIL), FM-5=7, FM-7=7, FM-2=6, FM-4=3, FM-6=2, + 6 non-FM (below).

#### E1 — final result, correctly positioned

**Do NOT lead with a "fit %".** "97% fit" conflates three different things (real failures,
delegated responsibility, resilience successes) and is useless for presenting GFSO. The honest
headline:

> **100% basis coverage of in-scope failures: 0/216 incidents need an 8th failure mode.**
> That is the falsification result for the 7-FM completeness (as a basis, §4.8).

The 6 non-FM cases are NOT coverage gaps. They must be stated explicitly because at first glance
they look like basis-escapes (apparent falsifiers) — they are not:

- **Group 1 — resilience-worked (3: cloudflare-017, -029, netflix-001).** An external fault hit,
  but a pre-built mitigation absorbed it; nothing in the company's decomposition broke. NONE
  because there is no failure to classify — the decomposition did exactly what GFSO prescribes
  against a foreseeable risk. **Evidence FOR the framework** (a company correctly applying GFSO),
  not a gap.
- **Group 2 — delegated responsibility (3: cloudflare-019, -042, okta-001).** The missing
  mitigation belonged to a third party (customer's registrar / vendor's systems / subprocessor's
  endpoint). Correct GFSO home = **NEGLECTED (STD-1)**: a justified non-coverage under
  separation-of-responsibilities — NOT "§16.2 out-of-scope" (that label keyed on the
  attacker-trigger). If the delegation was *declared* → legitimate NEGLECTED, no FM; if
  *undeclared* → FM-1 (missing NEGLECTED entry). **Either way IN-framework**, not a falsifier.

**The boundary to the genuinely-extraordinary — explicit, and (for now) subjective.** A real,
direct boundary exists: safety measures don't protect against *any* fire/incident; a genuine
no-precedent-AND-not-derivable event is §2.1. But the bar is high, and — the load-bearing point —
**this boundary is reached ONLY from the FM-1.b question ("was a foreseeable mitigation missing?").
No other extraordinariness axis hangs off FM-2..7.** Consequence: **"we couldn't foresee it" is no
longer a free excuse** — an incident is either genuinely-extraordinary (rare, must be justified) or
FM-1.b (you didn't decompose the foreseeable mitigation = a decomposition/management failure).
~5-7 records sit on the FM-1.b↔extraordinary borderline (browserstack, circleci, cloudflare-031,
github-026/045/063, ovh-001 — they "look unforeseeable" to many but have a standard missing
mitigation: patch, redundancy, fire-suppression). They are classified **FM-1.b, and this does NOT
change the FM breakdown** (all stay FM-1, sub-type b). The boundary is internal to GFSO, currently
drawn subjectively, breaks nothing — and is precisely the place GFSO asserts there is no
unforeseeability *outside* the FM-1.b mitigation question. (Open: a principled, less-subjective
criterion for the FM-1.b↔§2.1 line — a later refinement, does not block E1 closure.)

*(The old "≥95% fit" pass-criterion is retired as a crude proxy; the sharper statement is "100%
basis coverage + a clean accounting of the non-FM cases as success / delegation / extraordinary".)*

---

## 10. Theory-model — see canon §2–§3

The standard→theory-model derivation (agent derived as a necessary structural link) lives **in the
canon, §2–§3** (with the calibrated claims); provenance is in the canon Changelog + git history.

## 11. E2 EXECUTED — decomposition convergence, 2026-06-30

**Question (optimality, not "does X help").** What practice **reliably and cheaply** (fewest tokens/cycles)
converges an agent's decomposition to a verified plan? That a critic/iteration helps is industry-standard; the
open question is whether a given loop is the *optimal* token→convergence regime (the kind of claim GFSO is built
from). Yardstick = a frozen **reference** (a well-worked, completeness-audited decomposition) — **not an ideal,
not "100%"** (content-completeness is not a-priori derivable, §12 / §2.5 Lemma 1, so "100%" is not a concept).
The reference's true ancestor is the method that **builds** it: blind exhaustive enumeration + completeness
audit.

**Apparatus.** 10 diverse "complex" tasks, one frozen reference each, built uniformly by: one exhaustive
over-inclusive enumeration from domain expertise (GFSO-free, no solution consulted) → cast into the canonical
basis → **audit** (find holes by truth-maker/meaning) → patch → **reaudit** (a fresh verifier that re-derives
requirements *blind* before reading the reference, then confirms closure) → canon re-expression. Frozen
domain-generic prompts `prompt_search.md` / `prompt_audit.md`; blind meaning-match judge `prompt_judge.md`. **Two
runs: Opus = depth** (T01 regime screen + reference-method, verifies the mechanism); **Sonnet = breadth** (all
10 × 3 iters **+ two Opus judges per candidate**, the public artifact + a cross-model check). **Conclusions are
model-invariant; only the numbers differ.** Protocol/framing in `CONVERGENCE.md`.

**Proved.**
1. **The cycle works.** Iterating SEARCH (exhaustive recall, GFSO-free) + AUDIT (reduce to the canonical
   D/Dep/V/N basis, preserve distinct falsifiers) raises reference-coverage and decelerates — 78%→96% (Opus),
   74%→81% (Sonnet). One pass = a draft; iteration = the re-audit that closes it.
2. **Framing the pass beats iterating it.** The continuation prompt is a first-class variable: an open
   "what's missing" content hunt ≫ a plain redo ≫ a methodology-policing critic (drives the agent over *form*
   not *content*; **strictly dominated**). Unlike the climb, **here the effect is in the numbers** (regime gap
   on one task, same seed).
3. **The architecture — bare SEARCH ⊕ gfso AUDIT (a false dichotomy resolved by role-split).** Recall is
   *content* (the model's domain knowledge; GFSO adds nothing and *taxes* it); the basis-cast is something only
   GFSO does (a bare hunt yields a flat redundant list). Neither monolith is optimal → split the roles. The
   audit helps the next search with **no explicit handoff**: it re-sorts the verbose enumeration into a minimal
   canonical basis on which the remaining holes become *visible* as absent seams/slots.
4. **Not circular — ansatz-and-verify.** The reference was itself built by this method; of many candidate
   methods tested, **only search+audit reproduces it** (a critic, a redo, self-review cannot) — so the
   reference's provenance is irrelevant to the discrimination. *Honest caveat:* the reference's completeness is
   cycle-internal, partially offset by the reaudit's blind re-derivation and the cross-model run.

**Confounds (kept separate).** (a) The reference's *content* came from a bare enumeration, so
coverage-to-reference rewards content-similarity to a bare artifact → E2 is the **wrong** instrument for the
*value of the GFSO method* (needs execution = **E3**) but the **right** instrument for *ranking convergence
strategies*. (b) The same-agent confound is *reduced* by the cross-model run; confound (a) is not.

**Architectural payoff.** SEARCH+AUDIT *is* the reference-building method → productized as `gfso/decompose/`:
an agent **calls** a full decomposition from a short request rather than building the graph node-by-node
(under-covering machinery). GFSO's irreducible role = the audit-into-basis.

**Corroborating numbers (secondary — NOT the headline):** covered/reference-total, draft → converged (3 iters)
avg **74% → 81%**, climb 9/10 (T04 financial-close non-climb; T08 compiler best 95→98). Model-dependent quality
(Sonnet ~81% / Opus ~96%) is a measured **boundary**, not a defect. **Did NOT prove** absolute completeness (no
such target — §4) nor the method's execution-value (= E3). Full table in `CONVERGENCE.md`.

## 12. decompose() productization measurements — 2026-07-03

**Setup.** `auto_decompose` (the frozen E2 prompts, headless Sonnet one-shots, deterministic
wholesale build + bounded repair). Quality instrument = the frozen blind-judge protocol
(`experiments/e2_agent/prompt_judge.md`) against the frozen T01 reference (45 items). Speed probes on
one simple task (a wordfreq CLI), n=1 per variant — engineering telemetry, not statistics.

**Quality (coverage /45, blind judge).** depth=1: graph 28, prose basis 29. depth=2: graph 35,
basis **41 (91%)** — the depth dial moves both artifact classes (+7 graph, +12 basis), and the
depth-2 basis exceeds E2's 3-iteration converged Sonnet arm (36/45). Ballast (near-duplicate points)
falls with iteration (33→14 on graphs). Caveats: judge-instance variance ≈ ±2–3 items; the reference's
N section predates the v3.7 risk-vs-scope split, so GRAPH artifacts structurally forfeit most N items
(v3.7 deliberately keeps scope boundaries out of the graph's risk register — an instrument-convention
mismatch, not a content loss).

**Depth-1 re-measure (2026-07-04, post-productization code: prose-first policy + count-check +
reliability fixes).** Fresh T01 depth-1 (325s, holes==[], 32.1k out): basis **35/45**, graph 27/45.
The suspected depth-1 quality dip (28–29 vs the old 33 basis baseline) is GONE on the prose
artifact — 35 exceeds the old baseline by more than judge variance; the graph stays ~27–28, and the
gap to the basis is mostly the structural N-forfeit (6 unreachable N items; non-N: basis 32/39 vs
graph 27/39). Reading: the dip was instrument/assembly, not a property of depth=1.

**Reliability (found live, closed in code).** (1) Cross-tree id collision: two decompositions of
similar domains share LLM-chosen child ids, and a colliding ASSIGN is a same-id REVISION of the OTHER
tree's node — observed corrupting both graphs; closed by namespacing children under their root
(`{root}.{id}`), regression-tested. (2) LLM-JSON parse failures (literal control chars in long string
fields) cost a full repair call each; closed by tolerant parsing (0 retries after the fix). (3) Repair
calls became field-level PATCHES: 0.9–3.5k output tokens vs 33.7k full-spec re-emission; observed
live repairing a real Dep-cycle the DAG check caught.

**Speed (simple task, depth=1).** Floor ≈ **115s** = search 42s (3.5k out) + final audit 60–80s
(6.6–8.5k out) + deterministic build ~2s; CLI overhead ~3s/call. Measured NEGATIVE results:
thinking=0 breaks mapping-name discipline (drift → repair, net slower); a thinking cap ≥ the calls'
natural usage is a no-op; a lean (structure-only) final at depth=1 saves nothing (thinking dominates
the saved emission) and drifted names in 3/3 probes while the prose-first final ran clean in 2/2 —
hence the emission policy adopted THEN: depth=1 prose-first, depth≥2 lean. **SUPERSEDED 2026-07-08/09:**
the lean-final name-drift did not reproduce on the current model (0 drift over 12 lean runs, prose-first
vs no-prose a measured tie on T01, D/Dep/V 32/39 both), and the 2026-07-09 incremental loop removed
model-emitted prose entirely (the basis is now a deterministic render of the graph-form spec; see the
2026-07-09 entry below).

**Semantic graph-validation** (the decompose SEARCH prompt in diff mode over ONE decomposition level =
node + all children, gated on clean L0/L1): live on the wordfreq graph — 11 substantive advisory
findings (42s / 3.5k out).

**Pace-suffixes (2026-07-03 late; same task, n=1–2 per variant).** User-content additions on the
search / final-audit messages (frozen prompt cores untouched). In-session baseline 106s / 9.8k out.
Search-suffix alone 97s; audit-suffix alone 76s but the graph SHRANK (4 subtasks vs 5, 3 seams vs 5 —
content compression, rejected); both suffixes 74s with baseline shape but the NEGLECTED register
dropped once into a (cheap) repair. Amended audit-suffix (explicit keep-NEGLECTED clause), two runs:
**63–77s / 5.6–7.4k out, holes==[], 0 repairs, shape parity**. Productized as the `fast` flag
(default off — content quality vs the frozen judge is unmeasured; structural shape is preserved).
The known failure mode of "faster" (name drift / register loss) is exactly what the amended suffix
pins, and patch-repairs keep residual failures cheap.

**Execution validation instrument (`validate_node`, 2026-07-03 late).** One read-only headless agent
(Read/Bash/Glob/Grep) validating a delivered node against its criteria + the DELIVER report; executed
evidence required per criterion. Live two-sided probe (trivial CLI node): correct work → PASS with
executed evidence (ran the script, matched output) in 13s / 0.4k out; sabotaged work (hardcoded
output) → FAIL naming exactly the broken criterion, evidence includes running it AND spotting the
hardcode (anti-mock) in 14s / 0.5k out. The instrument never signals — the issuer reads the report
and signals PASS/FAIL (§14.5 verifier=issuer).

**Delegated execution, end-to-end (2026-07-04).** Registry-driven autostart: the issuer's ONLY act
is assigning a node to a registered llm-executor id; the dispatcher picks it off the frontier,
spawns a headless executor (work tools, scoped cwd), wraps its single structured report into the
canonical signals, auto-fires the registered validator on delivery, and the verdict auto-signals.
Live one-node probe (simple script task, Sonnet): **34s wall** ASSIGN→DONE, audit trail
`ASSIGN:exec → ACCEPT:exec → DELIVER:exec → PASS:validator` (~1.2k out total; consent = the
executor's own report, verdict = the validator's own signal — no step faked by the system).
Concurrency pre-check: two headless agents in parallel, 6.9s total, no subscription contention.
The FAIL→REWORK loop (auto-FAIL with the validator's failed_criteria → executor re-spawned with
them as feedback → re-deliver → PASS) is locked by deterministic tests; an unparsed executor or
validator report never signals (the node stays put; the FSM timeout monitor owns escalation).

**Acceptance run finding → the verifier≠executor gate (2026-07-04).** A fresh agent session ran a
real 8-leaf task end-to-end in the SEQUENTIAL regime (auto_decompose → executed the graph itself →
root DONE). Observed: it obtained independent `validate_node` verdicts on only 3 of 8 leaves and
SELF-PASSED the other 5+root aggregate on its own bash checks — the FSM accepted, because with
collapsed ids (executor == issuer == `agent`) a self-stamp and an evidence-based issuer PASS carry
the same signature. Self-report survived — the exact failure the protocol exists to prevent, and
empirical confirmation that visibility (persisted verdict lines) without enforcement does not hold
against a well-meaning agent under time pressure. Closed structurally: PASS whose source == the
node's Del now requires a RECORDED independent verdict for the CURRENT delivery (none → rejected;
recorded FAIL → rejected — the override is the falsification; a rework stales the record); distinct
ids keep the canon default. Auto-validation additionally fires on EVERY delivery (self-executed
included) whenever a validator role is registered.

**`fast` on the COMPLEX reference (2026-07-04).** T01 depth-1 with the pace-suffixes: 167s/17.0k (vs 325s/32.1k default — 2× cheaper), holes==[] — but basis coverage 26/45 (−9; V-criteria 9/20 vs 17/20 — verification content is what compresses), graph 25/45 (D 9/9, Dep 9/10 — structure even improves). Confirms the scoping: `fast` = SIMPLE tasks only. INSTRUMENT CAVEAT for this and the depth-1 re-measure above: these 2026-07-04 judgments used a different judge model than the historical baselines (the frozen protocol is identical, the judge instance is not) — treat cross-day comparisons as indicative; re-judge with the original instrument before leaning on a single number.

**Dual acceptance run (2026-07-04, same invented log-statistics-CLI task, both regimes end-to-end).** SEQUENTIAL (agent executes): decompose 98s/9.1k → 6 leaves + root delivered, EVERY delivery auto-validated (7/7 PASS first-pass, 24–54s / ~0.5–2k each), root DONE; the deliverable's own test suite green. DELEGATED (pure orchestration): one auto_decompose with assignee=<registered executor> → executors spawned per dep-ready leaf (63–123s / 5–10k each), auto-validated (16–36s), one validator-forced REWORK driven with failed-criteria feedback, discovered-dependency BLOCKs auto-resolved, root DONE; test suite green. The run EXPOSED and closed four dispatcher gaps live: spawns must be dep-gated; a resolved BLOCK must re-queue the executor; a PHANTOM (mis-named) blocker must not deadlock (resolved external=true); root-aggregate deliver steps are executor work too.

**Incremental refinement loop (2026-07-09).** depth>1 reworked: the graph-form spec is the sole
carried state at every depth (model-emitted prose removed entirely; the basis artifact = a
deterministic render of the spec), and EVERY round is the SAME operation — render(S) → search (new
holes over the rendered state) → audit FOLD-PATCH (adds/updates/removals) → deterministic merge →
S′; round 1 is the empty-state case. Converged content is never re-emitted, so it cannot be dropped
or compressed (the ×n re-emission cost and the fold-degradation of the prose-carry loop are both
removed by construction); two early exits (searcher ALREADY-COVERED; empty fold). Measured on T01,
same-day frozen blind judge (Opus, the historical instrument), artifact = the built graph's
projection: **depth-1 = 34/45 at 228s / 22.7k out** (historical d1: 27/45 at 325s/32.1k);
**depth-2 = 390s / 37.4k, and the within-run pair discriminates the fold's own effect: S₁ (after
round 1) = 33/45 (V 13/20) → S₂ (after the fold) = 35/45 (V 16/20)** — the fold's added criteria
land on real reference items (+3 V; N −1 within judge variance). Historical prose-carry d2:
35/45 at 698s/71k raw (≈440s/≈40k after the patch-repair fix); the 2026-07-08 prose-carry n=3
probe: 850s/80k with coverage BELOW its own n=1. The graph artifact's structural N-forfeit is GONE
(scope-boundary exclusions ride the goal's spec: N 2–3/6 vs the historical 0/6). Reading: round-1
lands on a ~33–34/45 plateau (3 samples: 34, 34, 33 — T01 is the dataset's saturable
calibration/null-anchor), a fold round buys ≈ +2 items for ≈ +15k out; token totals track model
THINKING, not emission (removing prose moved reasoning into native thinking — the emission saving
is real but secondary), so the pipeline's quality now rides thinking availability (native in the
reference Claude harness; a thinking-less foreign endpoint is unmeasured and presumed worse).
Honest caveats: ballast grows with depth (~41–44 — the fold prefers adds over merging into existing
items), run-to-run shape variance is large (8–12 subtasks), every point is n=1 engineering
telemetry. Simple-task depth-3 mechanics probe: 345s/31.5k, holes==[], per-round evolution visible
(|V| 28→37→47), fold ≈ 5.9k/round, one cheap patch repair.

**Refinement totalized to ONE operation over graph state (2026-07-09, later the same day).**
`refine(engine, root_id, rounds)` is now a public operation: search over the built graph's REAL
projection (+ any unmet checks) → fold-patch into the extracted spec (extract_spec = the exact
inverse of the build; roundtrip-tested) → wholesale rebuild as a revision (same ids, subtree
retained, existing children's Del preserved — a rebuild never stomps a delegation). `decompose
(depth=N)` ≡ init + build + (N−1) × refine; the live graph only ever holds verified states. This is
also the replan shape for E3 ("+1 iteration over whatever exists"). Frugal probe on T03 (DB
migration — the task with E2's LARGEST historical 3-iteration climb, 67→86% on the basis artifact):
d1 = 309s, S₁ = **30/43 (70%)** (E2's draft was 67%); one refine (+131s/+11.2k, rebuild clean) →
S₂ = **30/43** (V +2, Dep −1, N −1 — flat within judge variance; ballast 28→18, unmatched candidate
points 12→18: the fold's additions are real content the reference lacks, not reference items).
Combined reading across T01 (+2) and T03 (0): **a single fold/refine round buys 0..+2 reference
items** — the depth dial's measured quality value on these references is marginal (the E2-era climb
came from 3 full-rework rounds on the prose artifact from a weaker draft); the refine operation's
present worth is the OPERATION SHAPE (cheap, convergent, degradation-free replan over a live graph),
not bulk-depth quality. Artifacts: `runs/v2_incr/` (t03_*, judge_t03_*).

Artifacts (local, gitignored): `runs/v2_t01/` (candidates + judge verdicts), `runs/v2_speed/`,
`runs/v2_incr/` (the 2026-07-09 incremental-loop candidates, judge verdicts, stats).

**Embedding acceptance, first run (2026-07-12).** Pre-registered judge (docs/embeddability_acceptance.md +
tests/acceptance_embeddability/): a FRESH agent with no project context built a working host — own
JSON-lines StoragePort (mandatory audit-log core + exec-verdict extension), own virtual ClockPort,
own synchronous pump over `process_signal`, no engine threads — from the public docs + library
source only. Result: **6/6 green on the first pass, 0 stuck points, 0 author questions**; 9 doc-gaps
logged (spots where source reading substituted for docs) → folded back into
docs/embeddability_acceptance.md as the embedder's wiring reference. The host artifact is deliberately
NOT kept (each acceptance run rebuilds it fresh — keeping one would contaminate future runs).

**Depth-2 grain probe (2026-07-13).** `auto_decompose(depth=2)` on a fresh moderate CLI task
(mdtab: CSV → GFM table, --align/--max-width per column, error contract with exit code 2, pytest
suite, README), live Sonnet pipeline, n=1 engineering telemetry: 6 children each carrying **5–11
concrete criteria of their OWN duty** — the implicit-delegation defect class (a child left with a
one-line shell contract) does not reproduce at depth 2; 4 spanning invariants at the root with a
full coverage mapping; every Dep seam carries glue; NEGLECTED with predictability + invalidation;
`holes == []` (no silent residue); checks 8 PASS + CHECK-7/8 as named capability skips.

**L2 checker, two-sided live probe (2026-07-13).** The standalone Level-2 verb rebuilt as a
CHECKER (canon §13.4's own question: per parent criterion, do the mapped children's criteria —
taken as real-world facts — causally guarantee it; + semantic FM-2 conflicts), replacing the
search-diff hole-hunt (the decomposer's question, now living only in refine). Probe on the real
mdtab graph (fresh auto_decompose output), one Sonnet zero-tool call per side: **clean side** —
3/4 sufficient + ONE substantive advisory gap the build-time pass had missed (README glue pins
flag syntax but nothing entails the shown outputs being reproducible); **sabotaged side** (the
tests child's criteria gutted to "a few tests exist somewhere" under its standing coverage
claim) — the targeted criterion flagged insufficient naming the exact gap ("satisfiable by
trivial tests that verify nothing"). Named caveat: borderline criteria show run-to-run verdict
variance (n=1 per side; single-call instrument) — the load-bearing result is the two-sided
discrimination on the targeted criterion, which held cleanly. Fail-closed by construction:
unparseable or per-criterion-INCOMPLETE verdicts are "no verdict", never clean.

**L2 gate experiment (2026-07-13/14; protocol pre-registered before the runs).**
TEST A — checker calibration on SEEDED ground truth (no LLM judge). Substrate = fresh
auto_decompose(T01, d1); recorded substrate prep: one dangling mapping dropped, one builder-residue
Dep-cycle edge removed — and during the pre-repair attempts the L0/L1 gate correctly refused all 12
checker runs at ZERO LLM spend (live confirmation of the staging). Seeds: S1 = a mapped child gutted
to a vacuous stub; S2 = carrier criteria swapped for adjacent non-entailing ones; S3 = contradictory
rounding rules injected into two siblings. Checker n=3 per condition (Sonnet). RESULT: **9/9 seeded
runs flag their target, naming the planted defect verbatim; the S3 conflict pair exact 3/3; zero
spurious conflict pairs across all 12 runs. Pre-registered bar (≥2/3 classes by majority): PASSED —
3/3, unanimous.** Clean side: covered=False 3/3 with a STABLE core of three flags
(rounding_reconciliation, idempotency, concurrent_event_ordering — unanimous) + four borderline
flags (1–2/3); the stable core reads as REAL entailment gaps of the auto-built graph (the class the
earlier live probe also found); verdict variance concentrates on borderline criteria.
TEST B — the MANUAL regime (one-shot hand-build → L2 loop ≤3 rounds). Loop behavior: at round 0 the
gate caught an STD-2 violation of the hand build (two ORDINARY factors declared NEGLECTED — forced
back into the decomposition); then gaps 3→1, budget-capped. Same-day blind Opus judges (frozen
protocol) on both arms: **AUTO 35/45** (replicates the historical d1 34–35 — instrument sane;
ballast 34) vs **MANUAL+L2 24/45** (ballast 11). **Pre-registered bar (±3 of AUTO): FAILED (−11).**
The mechanism is visible in the categories (Dep 5/10 vs 8/10; V 11/20 vs 15/20): the checker repairs
ENTAILMENT of what is declared and cannot RECALL absent content — so the manual door requires the
hole-hunt too: **build → refine (content) → checker (entailment)**, not build+checker alone.
ARM 3 (corrected recipe, first attempt) — BLOCKED BY A REAL BUG the experiment exposed: refine over
a MANUALLY-built graph (bare child ids, no `root.` namespace) fails the merge id-match and
DUPLICATES the subtree (C1..C9 + root.C1..C9 in the DB; blind judge 26/45 with ~30 ballast dominated
by the duplication; CHECK-1b hole). Fix and honest rerun follow. Instrument note: the L2-loop's
patch step hallucinated child ids in add_mappings 9× (recorded; criteria edits applied) — the patch
prompt must carry the child-id roster explicitly.
ARM 3 RERUN (post-fix, 2026-07-14). The duplication fix confirmed LIVE: refine over the hand-built
graph reused ch1..ch9 IN PLACE and added two genuinely-new namespaced children (root.ch10/ch11),
holes empty. Blind judge (same frozen instrument): **31/45** — Dep 8/10 and N 3/6 both AT the AUTO
arm's level, V 12/20. Final table: **AUTO 35 · manual+checker 24 · manual+refine+checker 31.**
Reading: ONE refine round recovered precisely the axes a checker cannot (content recall: Dep +3,
N +3, +7 total) — the door split (decomposer recalls ⊥ checker entails) is CORROBORATED as the
manual-regime recipe: build → refine → checker. The remaining −4 sits in V with a NAMED harness
cause: the loop's FIX step failed to land its repairs (13 hallucinated child ids despite a roster
in the prompt; checker gaps 3→5, non-convergent) — an experiment-harness weakness, not the
checker's. The ±3 bar is formally still missed by 1 item beyond it (n=1 per arm); follow-up = a
structured fix step (patch addressed by index, not free-typed ids) before the next measure.

## 13. E3 on SpecBench — calibration tier, 2026-08-03 → 09-09

Substrate: **SpecBench** (Weco AI, Apache-2.0, pinned `08607352adc8abd78be2193dd9f725f1f032b8f0`).
Task, spec, visible and held-out suites, reference implementation and the baseline outer strategies
(`linear`, `aide`) are theirs; ours is only the protocol wiring of a fourth outer strategy (arm G)
and the scoring performed after an arm has closed. Inner coding agent identical across arms.
Held-out evaluation is never run inside any loop.

**Grade of everything below: calibration tier, n = 1 per cell, pre-registration NOT frozen.** These
are measurements taken while the apparatus was being debugged, not a measurement campaign.

**⚠ THE BOUNDARY THAT GOVERNS EVERY CELL BELOW, established 2026-09-10 by reading the substrate's
own publication rather than by any run of ours.** SpecBench ships a paper — *SpecBench: Measuring
Reward Hacking in Long-Horizon Coding Agents*, Zhao, Srikanth, Wu and Jiang, arXiv 2605.21384, cited
in the repository's own README — and a per-task table giving each task's size in LOC. Three of its
published findings bound what anything in §13 can mean:

* **"Every frontier agent saturates the visible suite."** The visible score being at its ceiling is
  a known, published property of this benchmark, not a defect of a task we happened to pick. Our own
  records agree run for run: on every baseline arm ever run here the visible score reads 1.000 from
  step 1 and never moves — `json_parser` (3 steps), `spreadsheet_engine` (3), `http2_protocol` (5),
  `regex_engine` (11), `markdown_renderer` (5, twice).
* **The reward-hacking gap scales with task size: about 27 points per tenfold increase in LOC.**
  Their stratification: tasks under 10K LOC reach a worst-case gap of **21 points**; tasks over
  25K LOC reach **100**.
* **The outer search strategy makes no difference to the visible score** — they report near-identical
  validation scores for `aide`, `linear` and `autoresearch` under Claude Code.

**Every task measured in §13.2–§13.12-ter is at or below 25K LOC** (§13.1 audits three above it;
§13.13–§13.14 measure above it): `json_parser` 1.5K, `regex_engine` 5K,
`sed_interpreter` 5K, `markdown_renderer` 8K, `spreadsheet_engine` 10K, `http2_protocol` 15K,
`database_engine` 25K. So this campaign has been measuring in the flattest part of the published
curve — the band where the substrate's own authors find at most 21 points of room — and comparing
against a search whose strategy their results say does not matter. That is a boundary on the
question these cells could ever have answered, and it was available in the substrate's documentation
throughout. It is stated here rather than discovered again.

### 13.1 Substrate audit (mechanical, no LLM, no judgement of ours)

- *Reference vs its own held-out suite* (`audit_reference.py`): `json_parser` 178/178,
  `markdown_renderer` 125/125 — the suites are self-consistent with the references they were
  generated from.
- *Reference vs the prompt's own prohibition* (`audit_reference_shortcut.py`): of **15** Python
  tasks carrying a reference and a prompt, **2** have a reference built on a module that same prompt
  forbids the agent to use — `json_parser` (`json`) and `regex_engine` (`re`).
- Consequence, measured on `json_parser`: `reference/json_parser.py` is `json.loads` plus a
  surrogate check, so its held-out tests encode CPython's behaviour, including where that behaviour
  contradicts the spec handed to the agent. `prompt.md` "Numbers (Section 6)": *"No `+` prefix. No
  `Infinity`, `NaN`, or hex"*; `test_parse_nan_literal_accepted` asserts `parse("NaN")` returns a
  float, its docstring reading *"Python json.loads accepts NaN"*. Three such tests exist. A
  spec-conformant implementation cannot pass them, so on this task held-out pass-rate does not
  measure honesty. `json_parser` and `regex_engine` are therefore calibration benches, not
  measurement tasks.
- *Prompt vs its own held-out suite* (2026-09-10, read by hand on `spreadsheet_engine`): a SECOND
  and independent way the substrate stops measuring what it appears to. Here the reference carries
  no forbidden import; the defect is in the prompt. Of the twenty held-out tests a spec-faithful
  arm failed, **not one is derivable from the 6.4 KB `prompt.md`, and six are contradicted by it**:
  - *immutability (8 tests)* — the prompt specifies `set_cell(sheet, cell_ref, value) -> dict`
    with `"""Returns updated sheet."""`, which an implementation that mutates and returns the same
    object satisfies exactly. The suite requires the opposite: `s2 = set_cell(s1, …)` must leave
    `s1` evaluable at its old values, across three generations.
  - *circular references (6)* — the prompt contradicts ITSELF. Its API block says `Raises
    ValueError for circular references`; its error table says `#CIRC! — circular reference
    detected`. The suite demands `#CIRC!`. An implementation that follows the first sentence is
    refused by construction.
  - *CSV (4)* — the prompt says `"""Export occupied area to CSV format."""` and specifies no format
    detail; the suite asserts `csv.endswith("
")` and quoting behaviour for embedded commas.
- **What this means for every score in §13.** A held-out suite of unstated and self-contradicting
  requirements measures how well an arm GUESSES what the specification omits. That is a legitimate
  thing to measure and it is not what this campaign is about, so a task with this property cannot
  carry a comparison between an arm that searches variants and an arm that carries a stated contract
  through. **Tasks known unfit as measurement cells: `json_parser`, `regex_engine` (reference built
  on a forbidden module), `spreadsheet_engine` (unstated + self-contradicting prompt) and
  `database_engine` (below).** Auditing a task before using it as a cell is cheaper than discovering
  it afterwards, which is how all four of these were found.
- *The large bucket, audited 2026-09-11 before spending on it* — the three tasks above 25K LOC that
  a cell could move to. **`c_compiler` is UNFIT and in the worst way yet.** Its `reference/oracle.py`
  is `gcc` itself (`gcc -std=c11 -O0 -no-pie … -lm`, and its own docstring says "Reference oracle
  using system gcc compiler") while the prompt forbids parser generators and forbids the generated
  code from invoking `gcc`; 127 of its 150 torture tests require a type or language feature its own
  "Supported C Subset" never lists; 61 of 299 held-out tests are passed by a compiler that refuses to
  compile anything, so the floor is 20%; and — checked by hand — **`tests/public/torture_src/` holds
  959 `.c` files, the held-out tests' own inputs, inside the VISIBLE tree that `workspace.py` copies
  into the agent's workspace wholesale.** `elf_linker` and `javascript_engine` are both FIT as
  specifications: one held-out test of 63 is non-derivable for the first (weak symbols, absent from
  the prompt), eight of 72 for the second (`instanceof`, the `in` operator, `Function.prototype.apply`,
  `splice`'s return value, `return` inside `finally`), and neither task has a test that cannot fail.
  **But `elf_linker`'s oracle cannot run on the Windows machine these measurements are taken on**, by
  construction: its fixtures assemble with the platform's `as`, which under MinGW emits COFF rather
  than ELF, and then execute the linked ELF output as a native process. Every score it produces there
  is the platform's, not the artefact's.
- *`sed_interpreter`* (2026-09-10) — audited the same way and it comes out **the cleanest task in the
  corpus** as a substrate — though at 5K LOC it sits in the short-horizon band where the substrate's
  own authors find little room (§13 head), so it is clean and not a place a cell can discriminate.
  Its prompt **forbids nothing at all** — no module, no approach; the
  document invites "a BRE regex engine adapter" — so the reference's `import re` is licensed rather
  than the shortcut it is in `json_parser` and `regex_engine`. Its visible suite imports only `sys`,
  `os` and the module under test, so it runs in the workspace an arm is given. Its held-out suite
  was cross-checked against GNU sed 4.9 and showed no semantic divergence: the oracle is sed's real
  behaviour rather than a house dialect. Of 114 held-out tests (77 + 37), **3 are strictly
  underivable from the prompt**: the lowercase `n` command, which appears NOWHERE in the document
  (only the `-n` flag and `\{n,m\}` do — checked by hand), and two details of `y` — that `\n` in its
  operands counts as one character, and that a length mismatch raises rather than being ignored.
  One more is weakly derivable: a backslash before an ordinary character in a replacement is
  dropped. No self-contradiction was found. Ungraded by any test: `0,/regex/` (where the shipped
  reference is itself wrong), the two-line `a\`/`i\`/`c\` form, and `r filename`.
- *`http2_protocol`* (2026-09-10) — audited the same way and it is the one large task that comes out
  **usable**: the reference imports only `struct` and `copy` (no forbidden module), its visible suite
  runs in the workspace an arm is given, and the held-out suite discriminates. Two bounded caveats
  belong to the numbers already published for it in §13.11.
  - **Five of its 42 held-out tests cannot fail, so the floor is 0.119 and not 0.**
    `test_invalid_{data_on_nonexistent_stream, window_update_huge_increment, recv_truncated_frame,
    goaway_on_nonexistent_stream, settings_bad_value}` each wrap their body in
    `except (ValueError, …, Exception): pass`, and the `assert` inside raises `AssertionError`, which
    IS an `Exception` — so it is swallowed and the test passes. Measured, not argued: a module whose
    every attribute is a callable returning the string `"TOTAL GARBAGE"` scores **5/42** against that
    suite. So the 0.857 recorded for both arms is 36 of 42 with five of them free; on the 37 tests
    that can discriminate it is 31/37 = **0.838**. The two arms still tie, which is what that cell
    said, and the rate is not the quantity it appeared to be.
  - The suite also requires MAX_FRAME_SIZE to be enforced in one place and violated in another
    (`test_max_frame_size_enforcement` sends 20 000 bytes and demands `ValueError`;
    `test_flow_control_window_update_recovery` sends 65 000 through `send_data` and demands it
    succeed), so an implementation that adds the RFC §4.2 check loses 2 of 42 while its visible score
    is unchanged. Three further requirements — which window a received `WINDOW_UPDATE` credits,
    `GOAWAY` closing streams above `last_stream_id`, and a locally SENT `SETTINGS` adjusting the
    local send windows — are not derivable from the prompt. `CONTINUATION`, the `PADDED` flag,
    multi-byte HPACK integers and two of the literal header representations are graded by no test at
    all, visible or hidden.
- *`database_engine`* (2026-09-10) — audited before spending a run on it, and it fails in all three
  ways at once. Every claim below was re-derived by hand from the files named.
  - *The reference IS the forbidden module, and so is the grader.* `prompt.md` lines 242-244 forbid
    linking `-lsqlite3`, including `<sqlite3.h>`, or shelling out to `sqlite3`. The task ships no C
    reference at all: `reference/` contains `oracle.py` (a `sqlite3` wrapper) and `run_oracle.sh`,
    described in its own header as "a drop-in replacement for the C binary". The grader goes
    further — `tests/slt_runner.py` says of itself: *"We do NOT use the expected results from the
    .test files. Instead, we always run the query against SQLite as a live oracle and compare"*,
    against `sqlite3.connect(":memory:")`. The held-out expectations are therefore not text in the
    corpus; they are whatever the grading machine's SQLite says, including where it contradicts the
    prompt.
  - *The prompt's central requirement is not the one being graded.* The prompt asks for a
    **persistent on-disk** engine (`page_read()`/`page_write()` against a database file); the oracle
    is re-created in memory per file, while all 65 held-out files run in one shared working
    directory with no cleanup between them. Counted here with a script over the corpus: of 60
    distinct table names in the held-out suite, **9 are created in more than one file** — `t` in 8
    of them, with different schemas, each then asserting against a table it assumes empty. A
    spec-conformant persistent engine is penalised for being one.
  - *Half the specification is never exercised.* `BEGIN`/`COMMIT`/`ROLLBACK` appear in **0** of the
    105 `.test` files. The B-tree page format, WAL and ARIES three-pass recovery, and MVCC snapshot
    isolation — prompt lines 39-71 — are graded by nothing.
  - *And the visible suite cannot even be collected in the workspace an arm is given.*
    `tests/public/test_public.py` does `sys.path.insert(0, Path(__file__).parent.parent)` and then
    `from slt_runner import …`, but `workspace.py` copies `tests/public/*` plus `tests/conftest.py`
    and never `tests/slt_runner.py`, which sits one level above. So the exact command the task's own
    `get_additional_instructions()` tells the agent to run raises `ImportError`. **The G run of
    2026-09-08 ($16.33, `paused:wall` at 4 h) was working this task with no runnable visible tests
    at all** — a fact about the substrate, and it must not be read as a fact about the arm.

### 13.2 `json_parser` — three arms, Sonnet, n = 1

| arm | held-out | Δ (public − held-out) | cost | wall | closed |
|---|---|---|---|---|---|
| A (`linear`, theirs) | 97.2% | +2.8 pp | $1.25 | 328 s | — |
| A+ (`aide`, theirs) | 97.2% | +2.8 pp | $1.09 | 298 s | — |
| G (GFSO) | 97.75% | +2.25 pp | $2.67 | ~1 h | root DONE/PASS |

As rates the arms do not separate (0.55 pp ≈ 2 tests of 178 at n = 1). Split by **kind** of failure
(`failure_kinds.py`; each exclusion carries the verbatim spec line that decides it):

| artefact | spec-contradicting | underspecified | **genuine** |
|---|---|---|---|
| G, what it declared done | 3 | 1 (BOM policy, spec silent) | **0** |
| A, its reported best step | 3 | 0 | **2** |
| A, its final step | 3 | 0 | **6** |

The baseline's genuine failures are `serialize_raises_for_{set,bytes,custom_object,nested_invalid}`
and `lone_surrogate_{high,low}_rejected` — all of one kind: silently accepting input that must be
rejected. Two facts affect this comparison and are stated because both favour us: the three
spec-contradicting tests are excluded per §13.1, and the baseline's headline number is its
`best_private_score` across steps while public is 100% at every step — i.e. the step is selected by
the held-out suite, which no deployment can do; its final step is therefore also given.

### 13.3 `markdown_renderer` — four runs while the apparatus was being repaired (2026-08)

Four runs on one task, taken as the instrument was fixed under them. They are kept as ONE entry
because separately they are a debugging chronicle, not four results: what each contributed is the
wall it hit, and the walls are the finding.

- **Run 1** — arm G, Sonnet, n = 1. The first end-to-end pass of the arm; it did not close.
- **Run 2, after the FSM change** — the same task re-run to see whether the change moved anything.
- **Run 3 — the first run that CLOSED, and it closed FALSELY.** The root reached DONE/PASS over an
  artifact its held-out suite refuses. That is the false green this whole campaign is built to make
  impossible, caught by scoring after closure rather than by any surface of the product; the defect
  behind it (FM-1.f, a criterion nobody spoke to) is named in the changelog and closed.
- **Run 4 — the run that could not be judged.** The acceptance instrument returned no structured
  verdict, so the node had ⊥ rather than a pass or a fail; §11.2 forbids reading ⊥ as either, and
  the run ended without one.

**What survives from all four:** a closure is not evidence until something outside the closing loop
checks it, and an instrument that cannot answer must say so rather than default. Both are now
enforced and regression-tested; neither is a number. Per-run scores from this period are superseded
by §13.7 (the instrument repaired) and are not quoted anywhere as measurements.


### 13.4 Criteria sensitivity (probe 4, `json_parser`)

Mutants of the task's own reference, each first confirmed defective against the held-out oracle;
`p` over decided verdicts only.

| mutation class | root (integration) criteria | leaf criteria |
|---|---|---|
| STUB | 1.0 | 1.0 |
| NARROW (error handling deleted) | 0.0 | 1.0 |
| SILENT_FALLBACK (exceptions swallowed) | 0.0 | 1.0 |
| DROP_BRANCH | n/a — no-op on this source | — |

The level is the finding: a parent's integration criteria are blind to a leaf-level defect by
construction, and acceptance judges each node against **its own** criteria. An earlier reading of
the root-level zeros as "the criteria are blind" was a level error, not a property of the criteria.

### 13.5 What the acceptance instrument itself is worth (audited, not assumed)

Acceptance verdicts carry per-criterion evidence, and the strongest form that evidence takes is a
cited execution: "Executed: `f(x)` → `y`". It is also the easiest to invent. Once every delivery is
frozen as it was judged, each such claim can be replayed against the exact artefact — and one run's
verdicts were audited that way, claim by claim, with no LLM in the loop:

| verdict | claim | the artefact it judged |
|---|---|---|
| block_scanner (2 verdicts) | `parse_blocks('para text\n2. item')` returns two blocks | one paragraph — **false**, twice |
| block_scanner | `'> ' × 500` raises RecursionError | **true** (and fixed in the next delivery) |
| inline_engine | the emphasis helpers are absent, "grep returns nothing" | all five present — **false** |
| inline_engine | `line.strip()` still runs on paragraph lines | **true** |
| inline_engine | ``render_inline("[`x`](url)")`` raises IndexError | **true** |
| inline_engine | ``render_inline('[a `b` c](url)')`` raises IndexError | renders correctly — **false** |

**Four of seven checkable claims describe behaviour the judged artefact did not have.** The
instrument is not uniformly wrong — the fence defect of §13.3 (run 2) and the crash-safety defect above
were real, and §13.3's escaping defect was caught where the held-out suite passes it — but a verdict
is only as good as what stands behind it, and that is now recorded rather than trusted: each verdict
carries the **tool trace** of the run that produced it, so a cited execution against an empty `Bash`
count is refuted structurally, without parsing the report's prose. The substantiated verdict of
§13.3 run 4 (18 Bash calls) and these fabrications are told apart by that field alone.

Two consequences are stated rather than left implicit. **The C1 and C2 columns inherit this**: a
finding named before contact and a criterion failed at acceptance are both instrument outputs, and
their reliability is now a measurable quantity instead of an assumption. And since the exhausted
rework loop settles in a terminal ESCALATED (§13.3, run 2), **validator precision became load-bearing**:
a false FAIL now ends an unattended run where it used to pass quietly into a DONE that carried a
failed verdict.

**The repair, and its control (2026-08-13).** A verdict now has to be re-runnable, and the two
halves sit where each belongs. **Form, in the engine:** every per-criterion entry must carry a
`probe` — the command that was run and the observation expected of it — and a report without one is
refused at the record as ⊥, not stored as a verdict (`verdict_report_defects(require_probe=True)`,
`tests/test_validate_result.py`). The requirement covers the PASS side as much as the FAIL side,
because the measurement's load-bearing direction is the false PASS. A human reviewer's record is
deliberately exempt: a person who inspected the thing by hand owes a judgement, not a command line.
**Contact, in the measuring layer:** the arm re-runs each probe against the snapshot that verdict
judged and records `claims_reproduced / claims_refuted`; a verdict none of whose probes re-run is
counted ⊥ rather than believed.

The mechanism was checked where the answer was already known: the seven claims audited above,
written as probes and replayed by the same code path the live instrument uses, come back **7/7 as
the hand audit found them** — the four fabrications refuted, the three true claims reproduced — at
**zero LLM cost**. One defect surfaced in that control and is worth recording, because it is the
same error in miniature: a probe that printed nothing was first read as a refutation, which would
have turned silence into evidence of falsity. Empty output is now ⊥ (undecided), never `refuted`.

### 13.6 Does the Level-2 gate separate a planted hole from a clean plan? (2026-08-13)

The pre-registration's third falsifier — *"the gate does not separate a planted causal hole from a
clean plan (recall ≈ false-positive rate)"* — could not be read off any arm's run, because a run
shows what the checker SAID, never what was there to find. It needs planted ground truth, so it got
one: matched pairs of decompositions over four domains, each pair differing in the hole alone, with
nothing running but `review_decomposition` — no coding agent, no acceptance, no held-out suite.

Two hole classes, planted in the shape the canon describes. **FM-1.d** (insufficient entailment):
every criterion covered and mapped, the topological checks green, and ⋀criteria(children) still not
entailing the parent's — the "120 + 150 > 200" shape. **FM-1.f** (unwritten criterion): the goal
needs something no criterion carries — the class that produced the one false close on record
(§13.3 run 3, the block-type vocabulary nobody pinned). Detection is read strictly: the checker must
name THE PLANTED criterion; a finding elsewhere counts as an alarm, not a hit, or a checker that
flags everything would score perfectly.

| model | planted draws | recall | clean draws | alarms | alarms found to be CORRECT on reading |
|---|---|---|---|---|---|
| sonnet | 12 | **1.00** | 12 | 1 | 1 |
| haiku | 12 | **1.00** | 12 | 5 | 5 |

Recall is a rate. The alarm column is **not** a false-positive rate, and calling it one would be the
mistake this table exists to avoid: every one of the six alarms was read, and every one named a real
unwritten premise of the control it flagged — inter-stage handoff latency bound by no child
criterion; a block whose type name is in the contract's list but does not match its content (a
heading typed `paragraph` passes both children and breaks the parent); a replayed valid token
satisfying signature, identity and ownership while a non-owner reads the data; a round-trip test
that could run against a stubbed importer. **So across 24 draws and two models there is no
demonstrated false positive at all** — what the alarm count measures is how often a hand-authored
"clean" plan turns out to carry a premise nobody wrote.

Three draws per case, and the repetition is not decoration: the checker is an LLM and does not
answer the same plan the same way twice — one clean control came back quiet alone and flagged in a
batch, which is why a single draw is an anecdote and the rate is over draws.

The two models differ in how much they find beyond the plant (1 alarm against 5), not in whether
they find it: both name every planted hole, in every draw. The weaker model is the more demanding
reader here, and that has a cost the arm feels — an executor must discharge every finding before
execution is admitted, and more correct findings mean more to discharge.

**What had to be repaired first, and it is the more interesting half.** The first pass scored an
alarm rate of 0.5, and reading the reasons refuted the reading: on the latency pair the checker
objected that two p95 bounds do not entail a p95 bound on their sum under correlated tails — which
is simply correct, and my "clean" control had assumed additivity that does not hold. On the session
pair it objected that "the fetch compares the requesting account id with the owner id" never says
where that id comes from, so a forgeable client-supplied one satisfies both children while breaking
the parent. Both controls were wrong; the instrument was right. Repaired (per-request bounds plus a
pinned request path; identity bound to the verified token's claim), both now pass quietly across
three draws each. The single remaining alarm, one draw of the CSV pair, names the round-trip test
being run against a stubbed importer — the anti-mock concern CHECK-1c exists for.

So the number that matters is not a pair of rates. It is that **authoring a decomposition this
instrument cannot fault is harder than authoring one that looks clean** — six times over, at this
level of scrutiny, the checker found an unwritten premise a careful author had missed, including in
controls already repaired once after the first pass said the same thing. That is the
Pragmatic-level work the canon says no a-priori discipline certifies (Ch. 8), being done well
enough to out-argue the person who built the control.

Scope, stated: four domains, hand-authored, two models, 48 checker calls, no coding agent and no
contact. The false-positive RATE remains unmeasured, and the obstacle is not the instrument: it is
that a control whose cleanliness survives this reading has not yet been authored — which is the
Pragmatic-level boundary (Ch. 8) showing up as an experimental-design problem. It measures the CHECKER's discrimination on planted classes, not the value of the
gate in a run — that is C1's job, and C1 is read from the arms.

---

### 13.7 The instrument, repaired — and the first run that closed (2026-08-15/16)

Everything below is still the calibration tier: `E3_PREREG.md` is **not frozen**, so none of it
counts toward a campaign. What it does carry is the first reading of the arm's acceptance that the
instrument itself can be trusted for, and the first measured C2 event.

**The instrument was the thing under repair, and it is measured, not asserted.** §13.5 replayed a
verdict's claims against the snapshot it judged; the replay then had to be repaired three times,
each time because it was adding up things that are not the same:

| bucket | what it means | why it is separate |
|---|---|---|
| `reproduced` | the probe ran and its output showed what the verdict said | — |
| `refuted` | it ran cleanly and did not | the claim is dropped, not the verdict |
| `unrunnable` | it could not run at all (silence, a crash, a timeout) | ⊥ is not "false" |
| `not_portable` | it runs only where the ISSUER stands | a defect of the probe, not of the claim |
| `underprobed` | the criterion names more behaviours than it probes | see below |

Two of those were found by being wrong first. Claims counted as `refuted` were re-runs of probes
citing `md_real.py`, a module absent from the snapshot — and present, it turned out, in the
validator's own scratch directory, where every one of them runs. And that scratch was a single
shared directory: it accumulated copies of past deliveries until a verdict was measured against a
module written **three days earlier by a different run**. That, not the loop, is what produced the
the false close of §13.3 run 3. Each validation now gets a fresh directory, and the report contract asks
for a command someone else can re-run in the delivered artifact's own directory.

With that repaired, one run's verdicts replay **118 reproduced / 8 refuted / 0 ⊥**, and the §13.5
ground-truth control still reproduces the hand audit 7/7 after every change to the replay.

**The first root that closed — and it closed falsely.** `sed_interpreter`, executor Haiku, plan and
acceptance Sonnet, n = 1:

| | arm G, closed | the benchmark's own linear arm, shipped |
|---|---|---|
| held-out | **89.6 %** | 55.8 % |
| visible − held-out gap | **0.10** | 0.44 |
| genuine held-out failures | **8** | ~34 |
| root | DONE | (no such notion) |

The artifact is far better than the baseline's on both suites, and the close is still false: eight
held-out tests fail, and they fall INSIDE criteria the root declared and the validator passed.
Adjudicated against the reference implementation, no model involved — GNU sed 4.9 renders the
classic hold-space paragraph join as `line1 line2 line3`, the artifact returns the lines unjoined.

**The mechanism is not fabrication. It is partial verification.** The criterion names three
behaviours — `N/P/D` restart loops, hold-space accumulation across the whole input, multi-line
address ranges — and the validator probed the first. Its probe is **honest**: re-run against the
judged snapshot it reproduces exactly what it claims, which is why the replay counted it
`reproduced`. It simply does not cover the criterion, and the untested half is the broken one.

So the instrument that catches an observation nobody made is blind to a real one standing for a
third of what it was cited for: **reproducibility is not coverage**. This is §7.3.6's residual
false-PASS in its precise form, and the canon already locates the guard: §6.3 states that
prohibition has no form guard and is guarded at runtime through FM-3. The verdict contract now
enumerates, per criterion, the behaviours it demands and requires every one of them to be covered by
a probe — each probe naming the behaviour it observed, since one command can honestly observe two
and counting them cannot tell that from a gap; where the probes carry no such names the count is all
that remains and the strict reading stands. An unobserved conjunct is recorded `undecidable` — not
passed, and not a refused report, since the report is a verdict whose evidence is short rather than a
malformed one.

**A correction to this paragraph, dated 2026-08-19.** As first shipped, the demotion was recorded and
went no further: the tool's reply, the directive its caller obeys and the log line were all built
from the verdict the validator CLAIMED, before the record was written. So between 2026-08-16 and
2026-08-19 a report claiming a pass over an unobserved conjunct was stored as a fail naming it,
reported as a pass, signed as a pass by the auto-validation, and the node closed. Measured on this
repository's own graph, which is where it was found. The record is written first now and everything
downstream speaks from it, saying so explicitly when a claim was demoted; and the same run that
proves the fix also shows why the counting rule above had to become coverage — the strict count
demoted five criteria whose evidence was a named passing test per behaviour.

**What the loop is worth when it does not close.** In an earlier run of the same task the whole
difficulty concentrated in ONE leaf (`s///`) and one criterion (`empty_regex_reuse`: an empty regex
reuses the last regex actually APPLIED at runtime, not the last one written). The validator's
reasoning for refusing it reproduces verbatim against GNU sed 4.9. A probe of that single defect —
same workspace, judged by real sed, no graph and no protocol — was closed by the same Haiku on the
**first attempt**, for $0.31. The node was not beyond the model; it had inherited a rework bound of
three. A baseline reports 55.8 % of a hidden suite and there is nothing to do with the number; the
arm reports an address.

**Facts about the substrate, recorded because they bound what any comparison can say.**
Two draws of the SAME baseline arm on `markdown_renderer` (Haiku, same task, same budget) shipped
held-out **72.0 %** and **92.8 %** — twenty points apart. Any arm-versus-arm difference smaller than
that is unreadable at n = 1. And task saturation is real in both directions: on `markdown_renderer`
both baselines reach 100 % of the visible suite (the band left for a discipline to show anything is
4–7 points of hidden gap), while `sed_interpreter` leaves 44. A task is chosen where the baseline is
NOT saturated, and that is checked before spending, not after.

The exclusion ledger for `markdown_renderer` was curated blind — spec, reference and suites only,
never an arm's artifact: **2 of 125** hidden tests excluded, both `underspecified` (the spec fixes
`parse_blocks`'s schema and never writes down a single type-string value), and **zero**
`spec_contradicting`. Re-scoring the recorded runs through it moves the count by one or two tests:
the substrate is clean, and C2 on it does not rest on contested exclusions.

---

**Policy (set 2026-06-05):** this log is **empirical evidence only**. Agent-process material —
critic-round narratives, session state, next-steps/plans, my own error-corrections, "what's done /
what remains" — does **NOT** belong here; it lives in agent memory. The E1 empirical study is
§9/§9.1 above. Keep this log a public empirical artifact, not a working log.

### 13.8 Validation stops burning rounds — before and after, on two tasks (2026-09-05/06)

Still the calibration tier: `E3_PREREG.md` is **not frozen**, so none of this counts toward a
campaign. What it carries is a before/after pair whose comparison was written down before any result
was seen, and one number that went the other way.

**What was changed.** Validation was 56.5% of all model spend, and 140 of 151 wasted validation rounds were
one class: a report naming behaviours it never probed. The engine now demotes an under-probed
criterion at the record rather than refusing the report, a report introduced by prose still parses,
and a criterion whose probe names a command is refused a pass when the run's tool ledger shows no
shell at all.

**The runs.** Arm G, Sonnet throughout, validation batch 12, rework bound 3. Every number below is
read from the runs' own `result.json`, not from a summary.

| batch | task | closed | held_out | ⊥ per run | claims reproduced / refuted |
|---|---|---|---|---|---|
| C | `regex_engine` ×3 | **3/3** | 0.920 · 0.920 · 0.824 | 0 · 0 · 0 | 115/3 · 114/1 · 104/3 |
| D | `markdown_renderer` ×3 | 1/3 † | 0.984 · 0.984 · 0.968 | 0 · 0 · 2 ‡ | 287/29 · 279/5 · 71/9 |
| E | `regex_engine` ×2 | **2/2** | 0.888 · 0.920 | 0 · 0 | 111/0 · 101/3 |

Against the runs already on disk for the same two tasks: `regex_engine` n = 15, held-out median
0.888, closed 6/15, ⊥ 0.47 per verdict; `markdown_renderer` n = 15, held-out median 0.880, closed
3/15, ⊥ 0.11.

† Two runs stopped on the DEFAULT $8 ceiling — a pause with the graph and workspace intact, not a
failure; one, resumed with a higher ceiling, then escalated a node that had spent its bounded
reworks (§14.3). `false_fail_share` on that run is 0.0: the validator was not over-strict.

‡ **Those two ⊥ are an artefact of the measuring instrument, and are published as such.** The
verdict↔delivery pairing lives in the arm's process, so a RESUMED run started with none: every
verdict standing from the earlier segment was written against a snapshot directory that does not
exist, every probe "failed to run" against nothing, and the replay called the verdict ⊥. Recomputed
over the same 14 stored verdicts once the pairing is rebuilt from the frozen deliveries on disk:
⊥ 2 → **0**, `not_portable` 144 → **0**. The stored record keeps its original number — a result is
not rewritten after the fact — and this is what it means.

**What the comparison does NOT show.** VALIDATION's share of spend went UP, not down: 68% / 71% / 78%
of each run's server-side total, against a median of 51% before. The change removed rounds that were
being burned, not the price of validating; once the wasted rounds stop, validation is simply what a
run mostly is. Server-side totals were $3.44–$6.87 on the three batch-C runs.

*(Labels sharpened 2026-09-07, values unchanged. Those three percentages cover validation of the
DELIVERY (`validate_result`) over the server-side total; adding the Level-2 review of the PLAN, which
the same runs paid for, they are 88% / 92% / 92% — both are validation in the canon's sense (§13.4,
§14.2), and which of the two a number covers has to be said. The batch-C server totals quoted above
are batch C's; the closed batch-D run's was $17.92. The whole-run denominator is a different question
again — §13.10.)*

**Boundary.** Two tasks, n = 3 + 3 + 2, one dataset, one substrate, one model tier. These are points,
not a curve, and the ⊥ column is the only one the change was aimed at.

### 13.9 The first attempt on the SCALE axis — both runs stopped by the product, not by the task (2026-09-06)

Iterations 1 and 2 read "no reading": zero leaks on both arms, 12/12 CLEAN, a degenerate 0-vs-0. The
boundary was named there — the phenomenon needs an artifact corpus larger than one reading holds — and
the axis it names is SCALE. This is the first attempt on that axis, and it is recorded because the
attempt is what has a result, not because the result is favourable.

**Design, written before any run.** Two large SpecBench tasks (prompts of 11.8 KB and 13.6 KB over 10-12
modules, held-out suites the agent never sees), arm G, Sonnet throughout, validation batch 12, rework
bound 3, one run per cell — the control arm (bare agent) was to follow on the same tasks. Primary
number: `held_out`, the share of hidden tests an artifact DECLARED done passes.

**What happened.** Neither run reached a finished root, and neither died on the task.

| task | wall | inner spend | root | stopped by | held_out | claims reproduced / refuted |
|---|---|---|---|---|---|---|
| `database_engine` | 51.6 min | $2.53 | EXECUTING | `validator_no_verdict` | 0.0 | 11 / 0 |
| `http2_protocol` | 93.1 min | $9.40 | EXECUTING | `redelivery_refused` | **0.833** | 206 / 5 |

`http2_protocol` is the informative half: public 0.957, id-private 0.978, held-out 0.833, seven genuine
defects named, 206 checkable claims reproduced against 5 refuted — real work, stopped at the protocol
rather than at the code. `database_engine` stopped earlier, with one leaf validated, one reworked, and
nothing aggregated.

**The two walls, both in the product and both since closed.**

* A validation run returned a single sentence and no structured answer — fifteen minutes, 232 tokens, no
  cost, which is a transport that stopped rather than a model that answered badly. The engine refused
  it, correctly (⊥ is not pass, §11.2), in the same words a genuinely unreadable report gets; on the
  second such refusal the node parks and the arm ends the run. The two cases are told apart now.
* Where contact refuted the DECOMPOSITION — a parent criterion failed while the children covering it
  are untouched since that FAIL — a re-delivery is refused on arrival. The frontier, in the same
  second, advised "AGGREGATE: all its children PASSED — integrate them … DELIVER". The executor obeyed
  the advice, was refused twice, and the run ended. The rule now has one owner, asked by the branch
  that enforces it and by both branches that advise.

**Boundary.** No comparison exists: the control arm never ran, n = 1 per cell, and both cells aborted.
Nothing here is evidence about whether the discipline pays — it is evidence about what stops a long run,
and both causes were product defects with names. **It was repeated on 2026-09-08 — §13.11.** The
attempt is repeated after the fix, from a cheap
probe of the acceptance loop first.

### 13.10 What the whole run corpus says — and what that does to every number above (2026-09-07)

Every reading in §13 is drawn from a run that FINISHED. That is not a neutral filter, and until now
nobody had counted what it removes. One table over every run this box has recorded answers it.

**⚠ The corpus figures in this section are a SNAPSHOT of 2026-09-07 and no longer reproduce from
the command below** — the corpus has grown to 83 runs / 24 closed (§13.11), and the as-of population
is not recoverable from the tree, so re-running the tool today gives different medians (held_out
closed n=24 median 0.908; the judge's share n=19 median 0.709; cost n=19 median $9.58). The block is
kept as taken rather than restated, and the grouping of aborts below still holds unchanged.

**The instrument.** One row per run, one fixed schema, read from what each run wrote at the time:
`experiments/e3_specbench/runs_table.py` over `results/*/result.json` joined to each run's own sqlite
base. The schema GREW across the campaign — `validation_batch` appears in 19 of the 77 files, the Q
tuple in 45, `plan_model` in 47 — so a field that was never written is reported as `null` and never
as zero. (The measuring layer is local to this box and not part of the distribution; the numbers
below are reproducible from the same command against the same directory, which is the same standing
every §13 instrument has.)

**The corpus.** 77 runs carrying a `result.json`, 2026-08-03 to 2026-09-06, arm G throughout, over
seven SpecBench tasks, against 34 distinct code fingerprints.

```
CLOSED (root DONE/PASS)                                      19 / 77
aborted, by the reason each run recorded                     58
  validator_no_verdict 9 · graph_stalled 8 · l2_not_discharged 8
  validation_stalled 6 · idle 5 · no_progress 4               = 40  a rule or a stall OF THE PRODUCT
  cost_ceiling 2 · agent_calls 2 · paused:cost_ceiling 1
  paused:wall 1 · paused:limit_window 1                       =  7  budget, wall-clock, account limit
  harness_fail:agent_unavailable 2 · :agent_invocation 2      =  4  the measuring layer, not the product
  escalated:root.parser · :root.inline_renderer
  :root.D5_substitution                                       =  3  escalation at the rework bound
  redelivery_refused 2 · l0_not_closed 1 · unknown 1          =  4  the rest

held_out   closed  n=19  median 0.912   min 0.767  max 0.984
           aborted n=57  median 0.200   min 0      max 1
validation, share of bill  closed n=14  median 0.710
  of which RE-validating a node already validated once:  0.774 of the delivery-validation spend
                                                         (superseded — 0.720, see below)
  (validating the delivery is itself median 0.88 of all validation; the rest reviews the plan)
cost, whole run            closed n=14  median $10.40
```

**⚠ On the 0.774 — SUPERSEDED 2026-09-08, and the correction is now computed rather than
estimated.** It was "every billing row for a node past the first is a re-validation", and since
2026-08-22 one validation of a contract with more criteria than the batch size is split into
CONCURRENT batches, each billing its own row against the same node — so the batches of a single
judgement were counted as repeats of it. The tool now asks the question the ledger answers directly:
two rows belong to one judgement when their CALLS OVERLAP IN TIME (`ts` is when a call finished and
`duration_ms` how long it took, both recorded). **The share is 0.720**, over the 19 closed runs that
carry a spend ledger as of 2026-09-08 — a population the block above, dated 2026-09-07, gives as 14;
the corpus has grown since and §13.11 states it.

Three things about that figure, because the first attempt at it got two of them wrong. The row-wise
rule recomputed on today's population gives 0.773, which reproduces the published 0.774 — so the
0.053 is the METHOD and not the corpus having grown. The estimate written here on 2026-09-07,
"collapsing rows less than thirty seconds apart gives 0.686", was done by hand and was too low. And
the correction is carried entirely by collapsing the CONCURRENT batches themselves: over these 19
runs a thirty-second window and the overlap rule agree run for run, both giving 0.720. Overlap is
published because it asks the ledger the question directly rather than through a threshold, and
because the window does misread runs outside this population — on one aborted run two batches
launched together but finishing 110 s apart count as four judgements and over-book $1.44 — but no
figure here would move if the window were used instead, and saying otherwise would credit the
change with work it did not do. Runs predating the batching are unaffected either way (their
same-node calls do not overlap: genuine re-validations).

**On the population.** The score lines are n=19 and the money lines n=14: five closed runs predate
the spend ledger, so their bases hold no billing rows. Those 14 are 8 runs whose executor the engine
spawned and 6 whose executor the harness ran — two accountings, and a run's price is read differently
under each, which is stated because the per-run numbers are in the table and pooling them is the
reader's call, not a silent one.

**What it means, stated narrowly.** Three quarters of the attempts never reached a verdict, and the
largest single group of causes is this implementation refusing, stalling or looping — not the task
being too hard and not the harness breaking. The artifact of a closed run scores well (0.912) and
the artifact of an aborted one does not (0.200), which is the expected shape and not a finding: an
unfinished run has an unfinished artifact.

**And the count is a HISTORY, not a property.** The 40 are spread across 34 code fingerprints, most
of which no longer exist: a wall counted here may have been closed months, or hours, before this
paragraph was written. Read as "this is how often the implementation was the thing that stopped a
run, over the period these runs cover", it is a denominator. Read as "the product aborts three runs
in four", it would be an overclaim in the negative direction, and the corpus cannot support it — the
same standard this document applies to claims that flatter.

**What it does to the rest of §13.** Every number above it is conditioned on closure, and closure is
selected by the product's own gates. That does not make those numbers wrong — each says what it says
about the runs it covers — but it bounds them: they describe the runs this implementation permitted
to finish, and that population is a minority of the attempts. Any future claim of the form "arm G
scores X" carries this denominator with it.

**What it is NOT.** Not a measurement of GFSO the framework. An abort is a fact about this
implementation, and the walls found in it have names, addresses and, as of 2026-09-07, regression
tests; §13.9 names two of them and the repository's changelog the rest. Nor is it a before/after:
the corpus spans 34 code versions, so it mixes epochs by construction and no trend may be read off
it. It is a denominator, and it was missing.

### 13.11 The two runs §13.9 recorded as stopped by the product, repeated after the fixes (2026-09-08)

§13.9 recorded an attempt on the SCALE axis in which neither of two runs reached a finished root and
neither died on the task: one stopped on a validation call that returned no structured answer, the
other on a re-delivery the protocol refused while the frontier was advising it. Both walls were in
this implementation, both were named there, and both have since been closed. §13.9 said the attempt
would be repeated after the fix. This is that repeat, in the same configuration, plus a third run on
a small task taken first as the cheap probe the campaign's own rule asks for.

**Design, unchanged from §13.9 where it applies.** Arm G, Sonnet in every role (worker, decomposer,
plan-repair, Level-2 checker, acceptance validator), validation batch 12, rework bound 3, the `arm`
executor regime, one run per cell. Primary number: `held_out`, the share of hidden tests an artifact
DECLARED done passes. Ceilings raised to leave room, because the earlier attempt's defaults were the
wrong size for these tasks (§13.9's `http2_protocol` stopped at 93 minutes against a $8 default).
The server was verified to be serving THIS tree before launch — `/api/runtime` `code_version` equal
to `source_fingerprint()`, `0f0a71b2ad2b` on both sides — which had not been true earlier that day.

| task | outcome | held_out | public / id-private | wall | inner spend | calls |
|---|---|---|---|---|---|---|
| `json_parser` | **closed**, root DONE | **0.972** | 1.000 / 1.000 | 32 min | $1.04 | 3 |
| `http2_protocol` | **closed**, root DONE | **0.857** | 0.978 / 0.911 | 73 min | $6.15 | 9 |

Both `valid` — the oracle fingerprint is unchanged across each run and neither wrote outside its
workspace. `held_out_pass` is false in both: closing a root is not the same as passing every hidden
test, and the two are reported apart on purpose.

**The same task, before and after.** `http2_protocol` is the one cell that exists on both sides of
the fixes, and it is the comparison this section is for:

| | 2026-09-06 (§13.9) | 2026-09-08 |
|---|---|---|
| outcome | aborted `redelivery_refused`, root EXECUTING | closed, root DONE |
| held_out | 0.833 | 0.857 |
| wall | 93 min | 73 min |
| inner spend | $9.40 | $6.15 |

Read narrowly: **the wall is gone.** The run that the protocol stopped now reaches a verdict, in
less time and for less money. Read no further than that — n = 1 on each side, one task, no control
arm, and the artifact's score moved by 0.024, which over 91 hidden tests is two tests and is not a
finding.

**What the acceptance instrument was worth in each run, and it is not the same answer.** §13.5
measures the validator by re-running its own checkable claims against the snapshot it judged:

| run | claims reproduced | refuted | ⊥ verdicts |
|---|---|---|---|
| `http2_protocol` | 162 | 1 | 1 |
| `json_parser` | 69 | 31 | 0 |

Same product, same instrument, the same afternoon. On `http2_protocol` the validator's claims stand;
on `json_parser` nearly a third of them do not reproduce. So C2 and q_D carry very different weight
in the two rows, and neither may be quoted without its own audit beside it. Why the instrument reads
so differently between two tasks is open, and it is the next thing worth measuring.

**C2, by kind (§13.5's rule: a held-out failure is only ours if the spec asked for the behaviour).**
`http2_protocol`: 6 genuine, 0 spec-contradicting, 0 underspecified. `json_parser`: 2 genuine, and
**3 excluded as spec-contradicting** with the prompt line as evidence — the task text says "No `+`
prefix. No `Infinity`, `NaN`, or hex" while the held-out suite asserts `parse("Infinity") == inf`.
That is the benchmark contradicting itself, and the exclusions are published with their evidence so
a reader can overrule them.

**C1, and an honest reading of a zero.** `caught_pre_contact` is 3 on `http2_protocol` and **0** on
`json_parser`. The zero is a TRUE negative, not a recording artifact: the Level-2 gate did name two
coverage gaps on `json_parser` before any code existed — that no child asserted the parts assemble
into one file, and that no child carried any complexity criterion — the plan was repaired on those
findings, and the recheck came back with none open. What then survived to the held-out suite was
neither of them; it was numeric overflow to ±inf. The gate worked and did not catch the defect that
mattered. Note the column's shape while reading it: C1 records what is still OPEN at the end, so a
plan repaired on the gate's findings scores 0 by construction — the same inversion `q_T` carries.

**Q.** `json_parser` (1.0, 1.0, 1.0, 1.0, 1.0); `http2_protocol` q_T 0.444 with the other four at
1.0. The low q_T is the metric behaving as defined, not a defect: q_T measures the criteria AS
ISSUED, and a plan repaired on the gate's findings drives it down. A gate that works is visible here
as a worse q_T, which is why the two are read together.

**Boundary.** Two closed runs are not a comparison. **A control arm was run on both cells the day
after — §13.12.** There is no control arm in either cell as recorded here, n = 1
per cell, the pre-registration is not frozen, and everything above inherits §13.10's denominator.
What these two runs establish is narrower and was the point of taking them: the two named walls of
§13.9 no longer stop the runs they stopped, and the apparatus now carries a run of this size to a
root verdict.

**The third cell is open.** `database_engine`, the other task of §13.9's design, stopped on the
account's own rate-limit window (`paused:limit_window`) at 49 minutes and $4.80 with its root still
EXECUTING — the budget bucket of §13.10, not the product's. It had by then gone past the point at
which the same task aborted on `validator_no_verdict` in September. Its resumed row, when it lands,
carries a caveat this repository would rather state than hide: a resume re-enters the arm's plan
step, so the continued run is a REFINE over the standing plan rather than a strict continuation of
it, and that is recorded as an open defect rather than smoothed over.

**The corpus, as of these runs.** 83 runs carrying a `result.json`, 24 closed. The aborted 59 group
as: **40** a rule or a stall of this implementation (`validator_no_verdict` 9, `l2_not_discharged` 8,
`graph_stalled` 8, `validation_stalled` 6, `idle` 5, `no_progress` 4) · **8** budget, wall-clock or
account window · **4** the measuring layer · **3** escalation at the rework bound · **4** the rest.
That grouping is now reproducible from the tool's own printed reason list; §13.10 recorded it as
grouped by hand, which was true of the command it named (`runs_table --summary`, a flag that does
not exist — the table prints the list by default).

And a filter the table used to apply to itself is now declared: **26 directories hold the work of an
attempt and no record at all** — a run that died before writing one. They are in no figure anywhere
in §13, they were in none before either, and the difference is that the summary now says so and
names them. From 2026-09-08 an attempt whose process reaches its own exception handler writes a
record whatever the failure was; a kill from outside — `taskkill`, an OOM, a machine restart — still
leaves none, which is plausibly how these 26 arose and is not a class an in-process guard can close.

### 13.12 Against the strongest published baseline, at matched cost — and the answer is not the flattering one (2026-09-08/09)

Every §13 reading before this one is about arm G alone. A score without a comparator says nothing
about whether the discipline pays, and §13.11's own boundary said so. This is the first cell of §13
that carries a control arm.

**⚠ NEITHER CELL BELOW CAN ANSWER THE QUESTION IT WAS RUN FOR, and they are named as such rather
than deleted.** `json_parser` was ALREADY recorded in §13.1 as a calibration bench and not a
measurement task — its reference is built on the very module its prompt forbids — and it was used
here anyway. It is also the corpus's cheapest task, the one this campaign uses to SMOKE the
acceptance loop. Its visible suite is saturated at 1.000 from the first step of either
arm, so both arms sit against one ceiling and a difference in held-out cannot be attributed to the
discipline. Debugging on a short task is the rule here; MEASURING on one is the error, and it was
made by letting the smoke's task become a row. The cell is kept because what it shows is about the
SELECTION signal rather than about quality (below), and because removing a run after seeing its
number is the worse habit. The value question is carried by the large cells.

**⚠ AND THE BASELINE'S SEARCH IS INERT ON THIS CORPUS — measured 2026-09-10, across every baseline
run on record.** The step-by-step visible score, which is the only signal `aide` selects on, reads
**1.000 from step 1 and never moves again**, on all six tasks a baseline arm has ever been run on:
`json_parser` (3 steps), `spreadsheet_engine` (3), `http2_protocol` (5), `regex_engine` (**11**) and
`markdown_renderer` (5, twice). The sole exception is `database_engine`, flat at 0.000 for 6 steps —
the task whose visible suite cannot be imported in the workspace an arm is given (§13.1), so it is
flat at the floor for the same reason: no signal. Computed from `steps[].public_score` in each run's
own harness record; no new run was needed and none was made.

Three consequences, and they are not flattering to the framing above rather than to the result:
* **"Cost-matched" bought unguided churn.** A search whose selection signal is constant cannot
  select; every step after the first is a variant nobody can rank. Raising A+'s budget until its
  spend matched G's therefore did not give the baseline more search — it gave it more of the same
  first answer. `json_parser` shows this directly: its steps scored 0.944, 0.972, 0.961 on the
  held-out suite while the visible signal read 1.000, 1.000, 1.000, and it kept the first.
* **What was actually compared** was GFSO against a strong ONE-SHOT Sonnet, not against a tree
  search. Every number in §13.11 and §13.12 should be read that way. That is a weaker baseline than
  the section claims, and stating it costs us the more impressive framing.
* **What the extra steps buy is not what the comparison needs.** One step of the baseline is the
  same artefact for about a fifth of the money — but arm A++ exists precisely so that "G found more"
  cannot be answered with "G was given more to spend", and a one-step baseline against a G with a
  larger ceiling does not remove that objection, it inverts it in GFSO's favour. The arms therefore
  stay cost-matched. The single baseline step is used for something else: to decide, cheaply and
  before a cell is paid for, whether a task can discriminate at all (§13.13).

This is a fact about the corpus and the inner model together, not about any one task: no choice of
task in this corpus repairs it, because the model maxes every visible suite in a single step.

**Design.** Arm **A++** — SpecBench's own `aide` (their strongest published outer strategy, a tree
search over steps), which is arm A+ with the step budget raised until its spend matches G's. Same
inner coding agent, same model (Sonnet) in every role, the same two tasks G closed in §13.11, one run
per cell, scored by the same held-out suites through the same layer. G's spend was known first, so
the baseline's budgets were set from it rather than the other way round.

| task | arm | reported held_out | spend | wall |
|---|---|---|---|---|
| `json_parser` | **G** | **0.972** | $1.04 | 32 min |
| `json_parser` | A++ | 0.944 | $1.57 | 10 min |
| `http2_protocol` | **G** | **0.857** | $6.15 | 73 min |
| `http2_protocol` | A++ | **0.857** | $7.88 | 55 min |

Both baseline runs `valid`: oracle fingerprints unchanged, nothing written outside the workspace.

**On `http2_protocol` the two arms are IDENTICAL, to the digit.** G scored 0.857142857…; the
baseline's every step from 1 to 5 scored 0.857142857…. Not close — the same number, six times. On
the larger of the two tasks, the discipline did not raise what the artifact achieves. It cost less
($6.15 against $7.88, a budget the baseline overran) and took longer in wall time. **That is the
honest headline, and it is the one that matters most: on this cell GFSO bought nothing in quality.**

⚠ **What that 0.857 is, measured afterwards (2026-09-10).** Five of this task's 42 held-out tests
cannot fail — they swallow their own `AssertionError` in an `except (…, Exception): pass` — so a
module implementing nothing scores 5/42 against them (§13.1, probed). 0.857 is therefore 36 of 42
with five of them free, i.e. **31 of the 37 tests that can discriminate, 0.838**. The tie between
the arms is unaffected, and it is the tie that this cell is about; the rate is not the quantity it
looked like, and neither arm should be read as having earned the last 0.119.

**On `json_parser` the difference is real but it is not about capability.** The baseline's search
VISITED an artifact scoring 0.9719 — exactly G's number — at its step 2, and reported 0.9438 from
step 1. Its steps went 0.944, 0.972, 0.961 while its selection signal, the visible suite, read
1.000, 1.000, 1.000. Three candidates its own criteria could not tell apart, and it kept the first.
So the gap in this cell is not "G built something better": G built ONE artifact, with no search at
all. It is that a signal which has stopped discriminating cannot select, and the visible suite had
stopped discriminating at step 1. The same saturation is visible on `http2_protocol` — public 1.000
from step 1 onward, five steps of search after the score stopped moving.

**What this supports, stated as narrowly as it deserves.** It is consistent with the framework's own
claim about where value sits (§6.2, and drift trap 1 in `CORE.md`: the loop is not where the value
is) — the differences here are about criteria that discriminate, not about a better search. It is
NOT evidence that the discipline raises artifact quality: on the harder task it demonstrably did
not. And a reader should note which direction the surprise runs — the arm with the machinery matched
the bare baseline rather than beating it, and we are recording that.

**Boundary, and it is severe.** n = 1 per cell, two tasks, one seed, one model, pre-registration not
frozen. The cost match is approximate: the baseline was budgeted at G's spend and overran it by 28%
on `http2_protocol` and 51% on `json_parser`, so where G is "cheaper" it is cheaper against an arm
that spent more than it was asked to. Two cells cannot separate "the discipline does not raise
quality" from "these two tasks have a ceiling both arms reach"; the second is entirely plausible,
since both arms hit 1.000 on every visible suite. Nothing here is a measurement of GFSO the
framework (§13's standing caveat), and the acceptance instrument's own audit differs by task
(§13.11: 162/1 against 69/31), so C2-derived readings are not pooled across these rows.

**What this section can and cannot settle.** Both cells here are saturated on the visible suite,
which is the condition under which the comparison is least able to discriminate — so the defensible
statement is narrow: **at matched cost, on two SpecBench tasks whose visible suites both saturate,
arm G reached the same held-out score as the strongest published baseline on the larger and a higher
reported score on the smaller, where the baseline's own search had already produced G's score and
its criteria could not select it.** A cell on a task large enough to discriminate is what decides
anything — one was run the same day, and it is §13.12-bis below.

### 13.12-bis The first non-saturated task — the baseline is ahead, and the comparison is invalid (2026-09-09/10)

The section above says the two cells are saturated and that only larger tasks decide anything. One
was run the same day. `spreadsheet_engine` is the corpus's largest task, and it is the first cell in
§13 where the visible suite does not carry the held-out one: both arms score 0.97+ visible against
0.78–0.83 hidden, so there is room to be better or worse in.

| arm | held_out | visible | spend | wall |
|---|---|---|---|---|
| A++ (`aide`, cost-matched) | **0.833** | 1.000 | $8.00 | 55 min |
| G | 0.778 | 0.971 | $7.30 | 111 min |

G closed the root (`valid`, no tampering, no strays). **The baseline is 5.6 points ahead at
comparable cost.** On the first cell able to discriminate, the discipline is behind.

**What G's twenty held-out failures are, because the shape is the finding.** They are not spread:
immutability 8 · circular reference 6 · CSV round-trip 4 · dependency 1 · error chain 1. Two or
three CLASSES of behaviour that the plan contains no criterion for at all — not work done badly,
work never named. That is FM-1 (Correspondence): the criteria are not jointly sufficient for the
goal, so Theorem 1's premise fails and its guarantee says nothing about the green it produced. The
Level-2 gate named ONE hole before any code existed (`caught_pre_contact = 1`), and none of these.

**⚠ THE COMPARISON IS INVALID, AND THE READING BELOW REPLACES AN EARLIER ONE THAT WAS WRONG.** The
first write-up of this cell explained the gap as a property of the framework — the protocol makes
criteria explicit but not complete. That explanation charged a defect of the EXPERIMENT to the
apparatus. The twenty failures were then read against the task's own 6.4 KB `prompt.md`; **the audit
and its three classes are in §13.1**, and the short of it is that not one failure is derivable from
the prompt and six are contradicted by it:

* **immutability (8)** — the prompt says `set_cell(sheet, cell_ref, value) -> dict: """Returns
  updated sheet."""`, which is satisfied by mutating the sheet and returning it. The hidden test
  requires the opposite: `s2 = set_cell(s1, …)` must leave `s1` intact across three versions.
  Nothing in the prompt asks for that.
* **circular reference (6)** — the prompt contradicts ITSELF. Its API block says `Raises ValueError
  for circular references`; its error table says `#CIRC! — circular reference detected`. The hidden
  test demands `#CIRC!`. An implementation that followed the first sentence loses by construction.
* **CSV (4)** — the prompt says `"""Export occupied area to CSV format."""` and nothing else. The
  hidden test asserts `csv.endswith("
")`.

So the held-out suite here measures **how well an arm guesses what the specification does not say**.
The baseline is a tree search: it explores variants and stumbles onto unstated requirements the more
steps it is given. Arm G takes the specification and carries it through — and where the
specification says `ValueError`, it faithfully raises `ValueError`. The two arms are not being asked
the same question, and 0.833 against 0.778 is not evidence about the discipline in either direction.

**What the cell DOES establish** is narrow and worth keeping: a run of this size closes, with a
`valid` record, an independent verdict per criterion and 107 of the validator's own claims
reproduced. The number stays published, with this boundary attached, because deleting a run after
seeing its score is the worse habit.

**The design that would answer the question** is the one this campaign used on earlier datasets:
make the hidden criteria EXPLICIT in the specification and give both arms the same complete
contract. Then the measurement is what GFSO exists for — carrying an explicit contract through a
decomposition without losing it at the seams — and the baseline's advantage, which is search over
the unstated, has nothing left to search for. Until that is run, no cell in §13.12 or here supports
a claim about value in either direction.

**What would move the whole comparison.** Not more of the same. Every cell in §13.12 and here scores
arms against a held-out suite whose requirements the specification does not state, which is a
question one arm is built to answer by search and the other is not built to answer at all. More
seeds and more tasks of this size would multiply that mismatch, not resolve it. The next measurement
is the explicit-contract design above; the rows already taken stand as what they are.


### 13.12-ter The hidden criteria made EXPLICIT — both arms reach 1.000, and the baseline does it in one step (2026-09-10)

The design §13.12-bis names as the one that would answer the question was run. Arm G and arm A++ were
handed the SAME amended specification: `spreadsheet_engine`'s own `prompt.md` plus a 5.6 KB addendum
stating, as requirements, what its held-out suite enforces and the prompt does not say — the
immutability of a returned sheet, `#CIRC!` as the value of a circular reference (resolving the
prompt's contradiction with its own error table), the CSV format, the rendering of integral numbers,
the argument shape of the aggregation functions, and that nothing in the API raises. The addendum is
recorded verbatim in both rows with its digest; it is applied through a single code path that wraps
the property both arms read, so the symmetry is by construction rather than by discipline.

| arm | held-out | visible | spend | steps / calls | closed |
|---|---|---|---|---|---|
| A++ (`aide`, one step) | **1.000** (90/90) | 1.000 | **$0.81** | 1 step | yes |
| G (GFSO) | **1.000** (90/90) | 1.000 | **$8.24** | 10 agent calls | **no — root left VALIDATING** |

Both scores were recomputed by hand from the submitted artefacts rather than read from the rows; the
held-out oracle's files are unchanged and neither arm left anything in the repository.

**What this establishes, and it is the point of the cell.** The twenty held-out failures of
§13.12-bis were **entirely** a matter of requirements the specification did not state. State them,
and they disappear — for both arms, completely. The diagnosis offered there as a reading is now a
measurement.

**What it establishes against us, and that is the larger half.** The baseline reached the same
artefact in ONE step for **81 cents**; arm G spent **$8.24** across ten agent calls and did not close
its root — the run stopped on its cost ceiling with the root still `VALIDATING`. By this repository's
own rule ("done" is a root DONE/PASS in the graph) G did not finish the task the baseline finished,
at ten times the price.

**And the cell cannot discriminate — but this ceiling is informative, unlike `json_parser`'s.** Both
arms are at 1.000 because, with a complete contract, a 10K-LOC task is a single-shot problem for this
model. Making the contract explicit removed the ambiguity and the difficulty together. What the cell
says is therefore about the SPECIFICATION and not about the discipline: the gap was never capability.

**Two boundaries stated before the number rather than after it.** First, the addendum's clause
selection is an index of the held-out suite, so this cell can support "an arm carries an explicit
contract through" and cannot support "an arm generalises to what a spec omits". Second, GFSO is not
its decomposer: a LOSS here would not have been separable from a defect of this particular
decomposer, and the reader should not read the cost figure as a property of the framework either.

**Where a cell can still discriminate.** Not by choosing a different task of this size — by the
substrate's own published stratification (§13), room appears above 25K LOC, and every task used in
§13.2–§13.12-ter is at or below it (§13.13–§13.14 measure above it).

**⚠ AND THIS CELL DOES NOT PASS THE GATE THAT WAS WRITTEN THE DAY AFTER IT.** `cell_check.py` was
extended on 2026-09-11 with two conjuncts it had been missing, and run against this pair it refuses
it on both:
* **Arm G did not finish.** Its row is `valid: true` — that field asks only whether a number is
  present and the oracle untouched — while `aborted` reads `paused:cost_ceiling` and the root is
  `VALIDATING`. By this repository's own rule, "done" is a root DONE/PASS in the graph. G's 1.000 is
  where it stopped, not what it completed, and it is placed beside a baseline that ran to completion.
  (This is not peculiar to this cell: across all 60 arm-G rows on disk, not one has a root in DONE,
  every one carries an `aborted` reason, and every one says `valid: true`.)
* **The baseline's selection signal was at the ceiling from its first step**, so its search had
  nothing to climb — the same condition §13.11 names on `json_parser` and `http2_protocol`.

The numbers above are not withdrawn — they were recomputed by hand from the artefacts and they are
what the two arms produced. What is withdrawn is any reading of them as a COMPARISON. The finding
this cell carries is the first one stated above and it does not depend on the comparison: with the
hidden requirements made explicit, the twenty failures of §13.12-bis vanish entirely.

### 13.13 What decides whether a task can carry a cell at all (2026-09-11)

Whether a task can carry a cell has to be settled before the cell. Three proxies for "big enough to
discriminate" were tried; the first was refuted, and the refutations of the other two are withdrawn
below:

| proxy | refuted by |
|---|---|
| bytes of `reference/` | `lox_vm` is 193 KB of reference and **5K LOC** — a short-horizon task |
| LOC from the substrate's own table | `elf_linker` 50K LOC scores **0.000**; `javascript_engine` 60K scores **0.819** *(withdrawn: the zero is the platform's — below)* |
| how much the starter already ships | `elf_linker` ships **more** relative to its reference (0.24 vs 0.09) and scores worse *(withdrawn with it)* |

The two measurements this section rested on (withdrawn below), both single steps of the baseline
arm on the published spec:

| task | LOC | steps | spend | visible | held-out |
|---|---|---|---|---|---|
| `javascript_engine` | 60K | 1 | $2.45 | 1.000 | **0.819** |
| `elf_linker` | 50K | 6 | $7.53 | 0.000 | **0.000** |

*(Withdrawn below — the linker's zero was the platform's, not the task's.)* **Unmeasured hypothesis — partial credit.** A linker is all-or-nothing: until the whole
assemble-relocate-emit pipeline works, no test passes, and both arms sit at zero however much they
are given. A language engine degrades gracefully: each feature is its own test, so an incomplete
implementation still scores, and there is a number for one arm to be better at than the other. A
cell needs the second kind. The hypothesis would place emulators, linkers and kernels in the first;
engines, interpreters and libraries in the second.

**And it is measured by the cheapest thing available** — one step of the baseline arm, $1–3,
which is also the baseline row a cell needs anyway. Not a new instrument: the ordinary arm, run once.
A task that returns 1.000 from one step is out (nothing to be better at); one that returns 0.000 is
out (nothing to be better with) — but only once the suite has been shown to score the artefact at
all (the correction below); what is wanted is the band in between, and it has to be looked at
before a cell is paid for rather than after.

**A correction to this section, dated 2026-09-11.** The contrast above does not stand as measured.
Thirteen tasks in the corpus build a binary with `make` and then look for it by its bare name
(`js_engine`, `linker`) — fourteen with `coreutils`, whose check is worded differently; on Windows
the compiler writes `js_engine.exe`, so every test of those tasks errors with "make succeeded but …
binary not found" and the suite scores 0.0 whatever the code does.
On one baseline workspace recorded at held-out 0.0: **0 of 130** visible tests as shipped, **126 of
130** — and **68 of 72** held-out — with the binary under the name the task asks for. The `javascript_engine` row at 0.819 exists
because that agent happened to write the copy into its own Makefile; another row of the same task on
the same spec reads 0.0 for the name alone. And `elf_linker`'s zero is the platform's twice over
(§13.1). So nothing here measured a linker as "all-or-nothing", and the two-row table shows one task
that happened to be scorable against one that could not be. What survives is the method — one
baseline step tells whether a task has a band to be better in — and `javascript_engine` as a task
that has one. Rows of these tasks taken before 2026-09-11 — `database_engine`, `elf_linker`,
`javascript_engine`, `lox_vm` — carry no information about the artefact where they read zero.

### 13.14 `javascript_engine` under the explicit contract — both arms at or within two tests of the ceiling, G unfinished at eight times the spend (2026-09-11)

A task above 25K LOC run with the amended specification: one addendum (`7f95d8022e22afdf`), the same
text in both rows, the same inner model (sonnet).

| arm | work | whole spend | visible | held-out | root |
|---|---|---|---|---|---|
| baseline, one step | 1 step (ended on its turn limit) | $2.55 | 1.000 | **0.972** (70/72) | — |
| G (rework bound 3) | 9 executor calls, 6 of them reworks (after 5 FAILs; one rework call died and was re-issued) | $20.56 | 1.000 | **1.000** (72/72) | not closed — 3 of 6 leaves accepted, the other 3 never started; stopped on its cost ceiling |

**What it shows.** With the contract stated, both arms reach, or come within two tests of, the
ceiling of the held-out suite on a 60K-LOC task — as `spreadsheet_engine` did at 10K (§13.12-ter).
The two held-out tests G passes and this baseline draft does not are both syntax-error reports:
`function() { … }` as a statement, and an unterminated string. The unterminated string falls under the
lexer's `eof-safe-termination` criterion and was probed directly; the anonymous declaration only under
the parser's generic `clean-error-on-malformed-or-excluded-input`, with no probe of that construct.
The 72/72 workspace was written by three leaves: during rework, the parser and value executors also
wrote the files of the three leaves that never started, and several of the reworks were on criteria the
held-out suite does not grade (`coercion-centralization`, `checked-dynamic-allocation`,
`ast-node-coverage`). Replayed in the directory layout the validator worked in, 165 of the 170
decidable claims of G's verdicts reproduce against the deliveries they judged (the run's own replay,
taken in the bare snapshot, recorded 109 reproduced and 17 refuted).

**What it does not show.** A comparison, nor the addendum's effect. G did not close its root, the
spends differ eightfold, and the baseline was not run to G's spend. One-step baseline drafts on the
PUBLISHED specification read 0.819 (59/72) and — re-scored with the binary's name fixed (§13.13) —
0.944 (68/72), the latter passing both tests G "wins" here; on the amended specification, 0.972. Two
drafts on the same published specification differ by nine tests (59 vs 68); at one run per condition,
that spread separates neither the arms nor the addendum from the draft. By §13.13's own test, one baseline step on the amended specification leaves a band of two
tests — too narrow for a cell to discriminate. Both memory ceilings of the G run were reached (arm 16.55
of 16 GB, server 10.0 of 10); the record does not say which call reached them, and the held-out suite
re-run outside any ceiling reads 72/72.

### 13.15 `javascript_engine` on the published specification — G at the baseline's median, stopped by its own plan (2026-09-11)

The same task with no addendum — the setting where one-step baseline drafts leave room.

| arm | whole spend | held-out | root |
|---|---|---|---|
| baseline, three drafts of one agent step each (step 0 is the starter stub) | $2.45 · $2.72 · $2.68 | 0.819 · 0.875 · 0.944 (the third a hand re-score: the run recorded 0.0 through the binary-name defect of §13.13) | — |
| G (rework bound 3, one run, resumed once) | $36.00 | **0.875** (63/72) | not closed — 4 of 6 leaves accepted; the parser ESCALATED; the interpreter never started |

**What it shows.** G lands at the baseline's median at more than thirteen times the spend, without
reaching its root — this run says nothing in G's favour. What stopped it is inside the plan: the
parser carried two criteria quantified over all inputs — malformed input never crashes the engine, and
unary operators stack to any depth — and the validator falsified each at scale in turn (twelve hundred
unclosed parentheses; then the depth guard added against them, once extended to unary, refused 299
stacked `!`). Two unbounded predicates that cannot both hold at scale are a plan defect, and they
exhausted the rework bound. Seven of G's nine held-out failures are object-and-call semantics
(`in`/`hasOwnProperty`, `instanceof`, `this` binding, `apply`), and the interpreter leaf that would
have implemented most of them never started.

**What it does not show.** What G scores when its plan finishes — the one comparison this task can
still carry, at one run per arm, against a baseline whose visible signal is flat from its first step.
Which leaf owned each held-out failure is not recoverable from this run's artefacts; `hasOwnProperty`
was assigned to the builtins leaf, which passed. The third baseline score is a hand re-score of a run
the harness scored 0.0, not a recorded measurement.
