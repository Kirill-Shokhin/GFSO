# GFSO — Experimental Evidence Log

> Working journal of empirical work on GFSO. Every test, what it measured, what was
> learned, what remained open. Lives in-repo so it survives sessions/compacts/agents.
>
> Source of truth for "what we've actually shown" vs "what is still hypothesis".
> Updated as work progresses.
>
> **Section numbers are as of each entry's date.** Entries written before the v4.0 canon cite the
> numbering then in force (the frozen draft, `applied_gfso_v3.md`); renumbering them would falsify
> the record. Where a later pass corrected a reference inside an older entry, that one reference
> carries the v4 number while its neighbours keep theirs — the entry's date still fixes the period.

---

> **First read `docs/CORE.md`** if you need the GFSO definition. This file
> assumes you already know what GFSO is and need experimental context.

## 0. Why this document exists

GFSO theory (`docs/applied_gfso_v4_en.md`) is comprehensive but the *vision of why it matters*
still floats — even for the author. Individual pieces look like "just composition",
"just good criteria", "just decomposition", and critics regularly latch onto one of
those and dismiss the integration as nothing new. This log keeps:

1. What we **actually** tested (versions, bugs, fixes, results) so future agents and
   future-author don't repeat lost work.
2. What each test **really proved vs didn't** — separating mechanical pipeline
   correctness from theoretical-claim validation.
3. The **vision context** — why GFSO is being built, what it is and isn't, what it
   should give that other frameworks don't. Captured under multiple angles of critique.
4. The **plan ahead** with rationale, so the next concrete step is obvious.

This is the cross-session memory the author asked for. Memory files in
`~/.claude/.../memory/` hold session-style hints; this file holds substantive history.

---

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

### v3 (applied_gfso_v3.md — re-authored as the v4.0 English canon, `applied_gfso_v4_en.md`)
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
this log (see §6 plan).

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
| Theory draft (v3.9, frozen) | `docs/applied_gfso_v3.md` | Provenance record of the canon |
| LCB results r1 | `bench_results_1.json` | First run (with bugs) |
| LCB results r2 | `bench_results.json` | After fixes |
| Perfect results | `bench_results_perfect.json` | criteria=hidden_tests proxy |
| BCB explicit+loop | `bench_results_bcb.json` | E0d |
| BCB zero-shot | `bench_results_zeroshot.json` | **E0e — main result** |
| Per-task logs | `bench_logs*/` | Full LLM traces for every task |
| LCB provider | `bench/providers/livecodebench.py` | |
| BCB provider | `bench/providers/bigcodebench.py` | |
| Subprocess verifier | `gfso/adapters/verifiers/subprocess_verifier.py` | LCB-style |
| Unittest verifier | `gfso/adapters/verifiers/unittest_verifier.py` | BCB-style |
| Runner | `bench/runner.py` | A-vs-B orchestration |
| Zero-shot script | `scripts/run_bcb_zeroshot.py` | E0e |
| LCB script | `scripts/run_livecodebench.py` | E0a/E0b |
| BCB script | `scripts/run_bcb.py` | E0d |

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

## 5. Open empirical roadmap

### E0 (done) — articulation-discipline effect
+34pp on BCB-Hard. Strongest current anchor. Should be written up as standalone
artifact (paper/blog).

### E1 (next) — 7 FM taxonomy validation on real postmortems
**Goal**: validate or falsify the claim that 7 FM are exhaustive for failures of
compositional validation in real software systems.

**Method**: collect ~100 publicly-documented incident reports (Cloudflare, AWS,
GitHub, GitLab, Stripe, Slack, BBC, postmortems repo). For each, classify the
root cause into exactly one of 7 FM. Track confidence (high/medium/low).
Cross-check ambiguous cases with manual review.

**Sources**:
- `github.com/danluu/post-mortems` (curated 100+ links)
- Cloudflare blog, AWS Post-Event Summary
- GitHub status page archives
- Stripe / Slack / GitLab incident reports
- Hacker News by tag `outage`

**Pass criterion**: ≥95% of incidents fit one FM unambiguously → taxonomy
validated empirically. <80% → theory needs revision (new FM or restructure).

**Status**: Protocol document being prepared. One agent per company per call.
Each agent reads protocol + prior session results before classifying.

### E2 — LLM-Issuer with vs without GFSO discipline
> **[SUPERSEDED — E2 was EXECUTED; see §11.](#11-e2-executed--decomposition-convergence-2026-06-30)** The
> "twin / with-vs-without GFSO" design below is the **RETIRED A/B framing** (coverage = content = the model's,
> so bare A ≈ GFSO B structurally). The executed E2 is a **convergence / optimality** study: what practice
> converges to a verified plan reliably and cheaply. The text below is kept as the original plan of record.

**Goal**: measure value of mandatory NEGLECTED + CHECK-1..8 + explicit criteria
formation when decomposing tasks.

**Method**: twin experiment. One LLM agent decomposes ad hoc (current SOTA agent
behavior). Another decomposes with mandatory GFSO templates. Run on a set of
multi-step tasks. Measure: coverage of real requirements, defect rate downstream,
escalation count during execution.

**Status**: Not started. Infrastructure already in place (`gfso/`, `bench/`).
Needs Issuer-agent prompt design and a multi-step task set.

### E3 — Compositional validation in multi-agent decomposition
**Goal**: test Theorem 1 (V(parent) = AND(V(children))) in practice. Show that
agents working under joint sufficiency + non-redundancy + CHECK-7 give compositional
guarantees the ad-hoc alternative doesn't.

**Method**: pick a domain with natural decomposition (multi-file refactor, system
design with subcomponents, data pipelines). Two team configurations: GFSO-protocol
agents vs ad-hoc agents. Same task budget. Measure: defect-leak rate at parent
acceptance, integration coherence, time-to-detect.

**Caveat**: hardest to set up. Likely needs custom benchmark — no public dataset
provides reference decomposition + per-subtask criteria. Either manually
annotate ~50 tasks or use SWE-bench trajectories as proxy.

**Status**: Not started. Blocked on benchmark availability + LLM-Issuer (E2) being
demonstrated first.

### E4+ — Long-horizon validation
- Real team deployment over months
- q-metric calibration ("q_D = 0.7 in IT vs construction")
- Adversarial agents threat model
- Causal correctness via domain ontologies + LLM review (§8 — a characterized boundary; approach vector §15.3)

These are §26 open problems. Out of scope until E1-E3 give the empirical baseline.

---

## 6. E-1: Old `gfso-agent` repo — pre-v3 attempts

Located in the author's working directory (the older `gfso-agent` repo).
Built on the **category-theoretic version of GFSO** (Kleisli arrows, Wasserstein
contractions) — the theory the author abandoned in favor of v3 because it didn't
reduce to debuggable engineering.

### Architecture (what was attempted)
A full multi-agent swarm:

```
User Task → Architect (Functor G) → Blueprint DAG → Workers (Functor F)
                ↑                                            ↓
                └────── Head refinement ←── Validators (η) ──┘
```

Roles:
- **Architect**: decomposes task into DAG (Functor G in category-theory terms)
- **Worker**: executes step (code generation; Functor F)
- **Validator**: checks output vs spec (natural transformation η)
- **Head**: global refinement loop on pipeline failure

**Three nested contraction loops**:
1. **SGR** (Self-Generative Refinement) — self-correction on code failure
2. **Validation** — retry with feedback on Validator reject
3. **Head** — global refinement on pipeline failure

**Stability criterion** (explicit in code): `L · γ ≤ 1`, where L = task expansiveness,
γ = validator contraction. Implemented via Wasserstein-style epsilon/laxity scores
from LLM judges.

### Code structure
```
gfso_agent/
  core.py        — GFSOUnit (atomic Monad (F, η) with SGR loop), GFSOHead
  llm.py         — LLMInterface, LLMAgent (KleisliFunctor[Any])
  types.py       — KleisliFunctor, Contract, NodeSpec, Blueprint, RuntimeContext, ...
  config.py      — Prompts, Params, SCHEMAS
  tools/         — PythonExecutor (sandboxed code runner)
experiments/
  loaders/       — MATH, HLE, BBH dataset loaders
  run_benchmark.py
```

### Repo state (per systematic survey)

- Single commit `f579872 "context update"` dated 2026-01-14. No branches, no diffs.
  Snapshot of stable pre-v3 prototype.
- ~2,800 SLOC across 18 files:
  - `gfso_agent/core.py` (508): GFSOUnit + GFSOAgent + 3 phases
  - `gfso_agent/llm.py` (308): LLMInterface, LLMAgent, AnthropicLLM, MockLLM
  - `gfso_agent/config.py` (248): Params, Prompts, SchemaBuilder, SCHEMAS
  - `gfso_agent/types.py` (203): KleisliFunctor, Blueprint, ValidationResult, Contract
  - `gfso_agent/docs/verification.md` (269): theory plan
  - `gfso_agent/docs/architecture.md` (183): mermaid + ontology
  - `experiments/run_benchmark.py` (260): MATH/BBH/HLE runner
  - `experiments/loaders/*.py` (377): dataset loaders
  - Other (logger, executor, smoke_test): 315
- **No `outputs/`, `logs/`, `results/` directories**. All gitignored. Repo has
  zero saved empirical artifacts. Smoke test (29 lines) is the only test
  infrastructure.

### Three-layer architecture (verified)

```
LAYER 1 (Control): GFSOAgent.run() — Head + 3 phases
  ├─ Phase 1: Architect → Blueprint DAG
  ├─ Phase 2: Execution engine (topological DAG walk)
  └─ Phase 3: Head synthesis + retry decision
     MAX_HEAD_RETRIES = 1 (hard-coded)

LAYER 2 (Worker SGR loop): GFSOUnit._execute_lane()
  for try in range(MAX_SELF_CORRECTIONS):
      sgr = functor.lift(task, context, contract)
      ok, feedback = _verify_local_artifact(sgr)
      if ok: return artifact
      context += f"[SELF-CORRECTION]: {feedback}"

LAYER 3 (Swarm X-Master): GFSOUnit._execute_swarm()
  ThreadPoolExecutor with SWARM_SIZE=3 lanes (parallel SGR)
  Synthesizer picks "golden" from valid_artifacts
```

Validation is **separate LLM** (validator_agent) checking artifact:
```python
val_result = ValidationResult(epsilon=..., laxity=...)
if val_result.is_success:  # epsilon <= THRESHOLD & laxity <= THRESHOLD
    commit
else:
    raise StepFailure → retry
```

### What was actually executed (vs planned)

Honest distinction from the verification doc `gfso_agent/docs/verification.md`
(dated 2026-01-14):

**Implemented in code:**
- ✅ Architect/Worker/Validator/Head split
- ✅ Blueprint DAG generation
- ✅ Three-loop refinement (SGR, Validation, Head)
- ✅ Fail-fast on first error (Claim 3 — only one marked implemented)
- ✅ Sandboxed PythonExecutor
- ✅ Dataset loaders for MATH, HLE, BBH

**Planned but NOT executed** (5 of 6 verification claims marked "Not Started"):
- ❌ Claim 1: Error Localization Rate measurement on HLE
- ❌ Claim 2: Bounded Error Accumulation curve (linear vs exponential)
- ❌ Claim 4: Validator Consistency (variance < 10%)
- ❌ Claim 5: Validator Calibration (correlation with ground truth)
- ❌ Experiment 5: Soft Validation Curve (T × M grid)
- ❌ Experiment 6: Phase Transition at L·γ = 1

**Empirical runs that did happen** (preserved outputs recovered from
an author-local outputs directory, 2026-01-05 run, ~5MB):

Pipeline run 2026-01-05, ~90 minutes total wall clock:
- 11 HLE tasks (task_0000..task_0010) — multi-domain PhD-level: Chess, Philosophy,
  Trivia, Math, Physics, Cryptanalysis, Algebraic topology, Moduli spaces
- ~20 MATH tasks (separate batch in `math/` subfolder)
- 3 HLE summary records (in `hle/summary_0000_0002.json`)

**Score on HLE 11 tasks: 0/11 correct.** Pipeline completed without crashing
on all 11 (`success: true` in batch summary), but no final answer matched
ground truth. Several tasks self-reported "N/A" / "cannot determine"
explicitly with low confidence (0.05-0.15); others produced confident but
wrong answers (task_0010: confidence 0.85, wrong concept).

Architecture behavior at runtime (extracted from `gfso_log.txt` per task):
- **Architect**: 11/11 produced valid Blueprints (5-7 nodes avg, SWARM strategy)
- **Worker SGR retries**: visible heavily (task_0000: 13 [FIXING] cycles on one
  node). Retries did NOT improve artifact quality — Lane 1 & 3 marked Failed,
  only Lane 2 Success, but Lane 2's output also broken.
- **Validator**: explicit "[FAILED]" / "[FATAL]" critiques on ≥2 tasks, but
  Head proceeded to FINAL_ANSWER synthesis anyway (false PASS)
- **Head global retry loop**: NOT observed firing on any task. Third
  contraction loop was dormant in practice despite being designed.
- **Per-task time**: 5-89 minutes wall clock. Task_0007: 61 min on a single
  step before SGR exhaustion.

### Mini-E1: classifying 11 HLE failures into v3 7 FM

This is an early test of the taxonomy on our own historical data.
Classifications use v3 §4 definitions strictly:

| Task | Domain | Failure | v3 FM | Confidence |
|---|---|---|---|---|
| 0000 | Chess | Worker artifact GENERATE_CANDIDATES produced wrong output (1 move vs 2-3); Validator flagged "[CRITICAL FAILURE]" but Head synthesized anyway | **FM-3** Verifiability (false PASS) + **FM-4** Propagation (Validator FAIL didn't halt Head) | medium |
| 0001 | Philosophy | Architect minimal blueprint, no artifacts, "N/A" answer | **FM-1** Correspondence (insufficiency — no child addresses criteria) | high |
| 0002 | Trivia | Same as 0001 | **FM-1** | high |
| 0003 | Algebraic topology | Worker hardcoded heuristics instead of computing Smith Normal Form; Adams spectral sequence not implemented | **FM-6** Feasibility (computation infeasible at attempted depth — info wasn't available to decompose correctly) | medium |
| 0004 | Math | "N/A" no artifacts | **FM-1** | high |
| 0005 | Lie algebra cohomology | Wrong Poincaré polynomial; Worker couldn't compute Chevalley-Eilenberg complex | **FM-6** Feasibility (Worker can't execute the math at depth attempted) | high |
| 0006 | Math | "N/A" | **FM-1** | high |
| 0007 | Kaluza-Klein physics | Worker SGR exhausted on step_1_parse_warp_factor, never produced parser | **FM-6** Feasibility (couldn't decompose into executable code at all) | high |
| 0008 | Cryptanalysis | Worker used artificial test string instead of actual problem ciphertext; Validator flagged FATAL but Head synthesized anyway | **FM-3** Verifiability (false PASS on broken input data) + **FM-4** Propagation | high |
| 0009 | Math | "N/A" | **FM-1** | high |
| 0010 | Moduli spaces | Confidence 0.85, plausible derivation (Hurewicz → ℤ/12ℤ), but ground truth ℤ — misinterpreted "reduced" in problem statement | Tricky: **NOT a v3 FM**. This is **conceptual error at problem parsing**, before decomposition. Pre-A1: criteria as stated by Issuer ≠ what Issuer meant. Maps to §5.4 Level 2 (semantic), §18.1 open problem. | medium |

**Mini-E1 distribution**:
- FM-1: 5 tasks (45%)
- FM-3 + FM-4 combo: 2 tasks (18%) — false PASS plus failed propagation
- FM-6: 3 tasks (27%)
- Not in 7 FM (Level 2 semantic): 1 task (9%) — task_0010

**What this is and isn't**:

- **Is**: an exercise of applying the v3 7-FM definitions to 11 known
  failure traces from an internal multi-agent system, recorded for
  reference. 10/11 mapped to one of the 7 FM under strict §4 reading;
  1/11 (task_0010) was a Level-2 semantic case that §5.4/§18.1 already
  marks as out of scope.
- **Is not**: validation of the 7-FM taxonomy. Sample size is 11, all
  from one source, one dataset (HLE), one implementation, one day's run.
  Cannot falsify and cannot confirm the exhaustiveness claim.
- **Is not**: validation of v3 implementation. The old system used a
  category-theoretic base and prompt-engineered Architect/Worker/Validator
  pipeline. Current `gfso/` code is a separate v3 implementation. These
  experiments do not exercise it.
- **Is not**: a result for E0 (criteria explicitness), E2 (LLM-Issuer
  discipline), or E3 (multi-agent composition theorem). Those need their
  own targeted experiments.

The recovery is useful for one specific thing: future agents and future
sessions can see that the 7-FM definitions, when applied strictly to real
multi-agent failure traces, don't immediately collapse. That is a small
operational signal, not evidence. Real E1 with ~100 public postmortems
across diverse sources is what produces falsifiable/confirmable data.

**Do not treat this section as a finding that lets us skip E1 proper or
move ahead on theory validation.** Treat it as a worked example of how
classification should look when E1 runs.

### Honest positioning in current framework

Pre-v3 attempt was **architectural prototype + experimental plan**, **not
empirical validation**. It produced:
1. A working multi-agent pipeline that could be run on HLE (artifact value)
2. A detailed experiment design (6 numbered experiments with metrics + cost
   estimates) — most of which we can now adapt for E1-E3
3. A concrete demonstration of *why* category-theoretic primitives don't
   reduce to debuggable engineering (anti-pattern value)
4. **No empirical evidence for or against the GFSO claims** — the experiments
   that would have provided it were planned but not run

In current framework's terms:
- This was an attempt at **E2 + E3 simultaneously** (LLM-Issuer with discipline
  + multi-agent decomposition), on a domain (HLE) where validation is **judge-based**
  rather than deterministic — making it the hardest possible test substrate.
- The attempt was **correct in ambition, premature in execution**: trying to
  prove composition + validator quality + soft-validation curves at once,
  with non-deterministic validators, with intractable theory, on HLE.
- Lesson: build empirical pyramid bottom-up. Don't test "multi-agent composition
  with soft validators" before validating "explicit criteria boost solve rate"
  (E0e) and "7 FM taxonomy holds on real failures" (E1).

### What we keep from this attempt
- **Role split**: Architect / Worker / Validator / Head — the right
  decomposition of agent responsibilities. Current `gfso/` framework merged
  these into BenchAgent (executor + verifier) for simplicity. To test E2/E3,
  we'll need to re-introduce them, but now with v3's primitives instead of
  Kleisli functors.
- **DAG blueprint as decomposition output** — Architect returns a structured
  DAG, not free text. Maps to GFSO `D: T → P(T)` directly.
- **Three-loop refinement structure** — SGR/Validation/Head loops were designed
  to address different failure surfaces. Maps onto v3 protocol:
  - SGR ≈ Executor-internal retry before DELIVER
  - Validation ≈ Issuer's V → FAIL → REWORK cycle
  - Head ≈ Issuer-level meta-refinement when REWORK budget exhausted
- **`L · γ ≤ 1` as stability invariant** — present in v3 as Утверждение 7 (small
  gain criterion), Section 9. The old implementation made it operational; v3
  formalized it.
- **Sandboxed PythonExecutor with structured output** — directly reusable. Our
  current `SubprocessVerifier` is simpler; for E2/E3 we'd want this back.

### Why this attempt didn't reach clean results
1. **Theoretical primitives didn't map to debuggable code**: Kleisli functors,
   Wasserstein metrics, natural transformations — beautiful math, but when the
   Architect produces a wrong DAG, "the functor G has a coherence issue" is not
   a fixable bug. v3's primitives (T, D, criteria, V, signals) map to concrete
   code decisions.
2. **No formal correctness conditions for decomposition**: the old theory had
   composition (G ∘ F) but not joint sufficiency / non-redundancy as explicit
   checks. Old Architect could produce mathematically-coherent-but-wrong DAGs
   without anything catching it. v3's CHECK-1..8 are the missing piece.
3. **Validators were probabilistic LLM judges**: η as "natural transformation"
   meant an LLM saying "looks ok"/"not ok". Non-deterministic, biased, drifty.
   v3 keeps Verifier deterministic when possible (subprocess test running, etc.).
4. **No audit trail by construction**: old system logged extensively but the
   logs weren't structured around a finite signal set, so post-hoc diagnosis
   was a slog. v3's 12 signals × 12 states give a finite event vocabulary.
5. **Tested on HLE/BBH/MATH**: domains where criteria are inherently judge-based
   (HLE expects free-form answers compared by LLM-judge), making it impossible
   to separate "agent failure" from "validator failure". BCB-style benches with
   deterministic unittest validation are a strictly better test substrate.

### Lessons that drove v3
- Build the theory from operational concerns, not from category-theoretic
  beauty. v3 starts with "what does a handoff transaction need?" not "what
  does a Kleisli arrow give us?"
- Make primitives concrete enough that wrong implementations show up as
  CHECK failures, not as "coherence issues"
- Keep validation deterministic where possible; reserve LLM-judges for
  Level 2 (semantic/pragmatic) where there's no alternative
- Pick benchmarks where ground truth is unambiguous (unittest > LLM-judge)

### Code patterns worth keeping for E2/E3

**Adopt:**
- **SchemaBuilder fluent API** (`config.py`) — centralizes prompt structure;
  decouples LLM prompt template from configuration. Useful when E2 builds
  Issuer prompt templates with mandatory NEGLECTED / CHECK-* sections.
- **Contract abstraction** — passes metadata dict dynamically; scales to new
  schema fields without code changes. Maps directly to v3's `Spec`.
- **Three-loop hierarchy** (SGR ⊂ Validation ⊂ Head) — clean separation of
  contraction levels. SGR is local retry inside Executor; Validation is
  Issuer's FAIL→REWORK; Head is meta-refinement when REWORK budget gone.
  All three already supported by v3 protocol.
- **Artifact kind system** (`kind='blueprint'|'code'|'validation'`) — polymorphic
  verification dispatch. Could be a generalization layer above VerifierPort.
- **Structured logging with depth** — indentation aids trace readability when
  multiple agents nest.
- **PythonExecutor sandbox** — directly reusable for E2/E3 when models generate
  executable code. Better than our current naive subprocess.

**Avoid:**
- **RECURSIVE strategy** (was disabled in old repo per architecture.md) — caused
  "complexity explosion"; deep recursive decomposition without convergence
  guarantees is unstable.
- **Implicit L and γ measurement** — they were "implicit in behavior" but never
  measured. v3 should be designed so L, γ are computable proxy metrics from
  the audit graph, not parameters in a formula.
- **Single validator instance** for both spec generation and validation — keep
  Validator orthogonal to Architect/Worker.
- **Heavy hard-coded field names** — old code had string-coupled metadata; use
  schema registry pattern.

### Action items
- [ ] Plan E2 architecture by re-using Architect/Worker/Validator/Head split
      but with v3 primitives (criteria, CHECK-7, signals)
- [ ] Reuse PythonExecutor sandbox design when E2 starts
- [ ] Consider porting SchemaBuilder + Contract abstractions into `gfso/`

This becomes "E−1" in the experimental sequence: the attempt whose **partial
execution and intractable debugging** produced the v3 reformulation.

---

## 7. Plan ahead (concrete next steps)

In order of priority:

1. **Integrate gfso-agent lessons into this log** — read the old repo, write up
   what was tried, what failed, why. Should explain why v3 looks the way it does.

2. **E1 protocol document + first run** — `docs/e1/collection_protocol.md`
   describing exact procedure for an agent: which company, which incident reports,
   how to classify, what output format. Run on one company (Cloudflare is best
   first because they publish detailed RCAs and root causes are
   well-articulated). Build the dataset incrementally, one company per session,
   each agent reads prior outputs first.

3. **Write up E0 as standalone artifact** — the +34pp result is presentable now.
   Should not be buried in this log; either blog post or short paper.

4. ~~**E2 design** — when E1 is done, design the LLM-Issuer twin experiment.~~
   **DONE / SUPERSEDED — see §11.** E2 was reframed (the twin A/B framing is retired) and run as a
   decomposition-convergence study; the result + apparatus are in §11 and `experiments/e2_agent/CONVERGENCE.md`.

5. **Theory polish** — minor §17.1/§17.2 review, possibly extract §17.2 (Scrum)
   into its own short paper since it's a self-contained formal-mapping result.

---

## 8. How to use this document

- **New agent picking up work**: read §0-2 for vision, §3 for what's tested,
  §5 for what's next. Don't restart from scratch.
- **Author returning after break**: §1 for vision restated, §5.E_X for next step.
- **Critic dialogue**: §1 (vision) + §4 (proven/not) + memory file
  `feedback_critic_rebuttals.md` for prepared answers.
- **Compact in progress**: the substance of conversations should distill INTO this
  document before compact, not be lost in the compact summary.

When the conversation produces a non-trivial finding, **update this file**, not
just memory. Memory is hints; this is record.

---

## 9. E1 EXECUTED — corpus build + classification, 2026-05-28

The plan in §5/§7 (E1 = 7-FM taxonomy validation on ~100 postmortems) was executed
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

---

**Policy (set 2026-06-05):** this log is **empirical evidence only**. Agent-process material —
critic-round narratives, session state, next-steps/plans, my own error-corrections, "what's done /
what remains" — does **NOT** belong here; it lives in agent memory. The E1 empirical study is
§9/§9.1 above. Keep this log a public empirical artifact, not a working log.
