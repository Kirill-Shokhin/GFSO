# GFSO Formal Verification Plan

**Purpose:** Track claims, proofs, and empirical validations for GFSO framework.
**Status:** In Progress
**Last Updated:** 2026-01-05

---

## 1. Core Claims

### Claim 1: Deterministic Error Localization

**Statement:** A stochastic LLM agent system can deterministically identify which component failed when a task fails.

**Formal:** For pipeline $P = f_n \circ ... \circ f_1$ with validators $\eta_i$ at each node:
- If $P$ fails, there exists unique $i$ such that $\eta_i$ rejected $f_i$'s output
- All $f_j$ for $j < i$ have been validated (passed $\eta_j$)

**Status:** [ ] Not Started

**Required Evidence:**
- [ ] Experiment: Error Localization Rate on HLE tasks
- [ ] Comparison with baseline (random guess = 1/N)
- [ ] Log analysis from real runs

**Notes:**
- This is the main novelty claim
- Distinguishes GFSO from naive chain-of-thought agents

---

### Claim 2: Linear Error Accumulation

**Statement:** Under non-expansive assumption, errors accumulate linearly (not exponentially) with chain length.

**Formal:** (From mathematics.md, Theorem 3.1)
$$d(F(f_n \circ ... \circ f_1), G(f_n \circ ... \circ f_1)) \leq \sum_{i=1}^n \epsilon_i + \delta_F(n-1)$$

**Status:** [ ] Not Started

**Required Evidence:**
- [ ] Theoretical: Proof is in mathematics.md (complete)
- [ ] Empirical: Show error vs chain length curve is linear
- [ ] Compare with baseline without validators

**Notes:**
- Depends on Assumption 1.5 (non-expansive)
- Need to verify assumption holds for LLM

---

### Claim 3: Fail-Fast Guarantee

**Statement:** GFSO pipeline halts at first error instead of propagating hallucinations.

**Formal:** If $\eta_i(f_i(x)) = \text{FAIL}$, then $f_{i+1}, ..., f_n$ are not executed.

**Status:** [x] Implemented in Code

**Required Evidence:**
- [x] Code inspection: `core.py:375-379` breaks on StepFailure
- [ ] Empirical: Measure compute savings on failed tasks

**Notes:**
- Already implemented
- Need to quantify benefit (tokens saved, time saved)

---

### Claim 4: Validator Consistency (Approximate Non-Expansive)

**Statement:** LLM validator exhibits approximately non-expansive behavior - similar inputs yield similar pass/fail decisions.

**Formal:** For validator $\eta$:
$$|score(\eta(x_1)) - score(\eta(x_2))| \leq L \cdot d(x_1, x_2)$$
with small Lipschitz constant $L$.

**Status:** [ ] Not Started

**Required Evidence:**
- [ ] Experiment: Same (artifact, spec) pair → variance in scores
- [ ] Experiment: Similar pairs → similar scores
- [ ] Threshold: variance < 10% for identical inputs (user observation)

**Notes:**
- User reports observing ~10% variance in practice
- Low temperature (0.1) helps
- Need formal measurement

---

### Claim 5: Validator Calibration

**Statement:** Validator scores correlate with actual correctness.

**Formal:** $P(\text{correct} | score = s) \approx s$

**Status:** [ ] Not Started

**Required Evidence:**
- [ ] Ground truth dataset: (artifact, spec, actual_correct) tuples
- [ ] Calibration curve: predicted score vs empirical pass rate
- [ ] Metrics: Precision, Recall, F1 at threshold

**Notes:**
- Requires manual labeling of ~50-100 samples
- Can use HLE tasks with known answers as ground truth

---

## 2. Scope Limitations (Acknowledged)

### Limitation 1: Visual Perception Tasks

**Statement:** GFSO assumptions (specifically non-expansive) do NOT hold for image understanding tasks.

**Reason:** LLMs exhibit high variance in image interpretation. Same image → different descriptions.

**Mitigation:**
- Use SWARM strategy (N parallel workers)
- Majority vote / consensus
- Relaxed validation (trust swarm, semantic check only)

**In Code:** `agent_architecture.md` Section 3.3:
> "Weak Perception Audit: When checking image tasks, the Validator trusts the Swarm's consensus."

**For Paper:** Honest scope limitation. Show where GFSO works, where it doesn't, and why.

---

### Limitation 2: Creative / Ill-Specified Tasks

**Statement:** GFSO requires formal specifications. Tasks without clear success criteria cannot be validated.

**Reason:** Validator needs spec to compare against. "Write a good story" has no formal spec.

**Mitigation:**
- Restrict to tasks with testable outputs
- Code execution, JSON schema, type checking as validators

**For Paper:** Position as "structured task completion" not "general AI".

---

## 3. Experimental Plan

### Experiment 1: Error Localization Rate

**Objective:** Measure how accurately GFSO identifies failing component.

**Setup:**
1. Run N tasks on HLE benchmark
2. For failed tasks, record which node was blamed
3. Manual verification: was that node actually wrong?

**Metrics:**
- Localization Accuracy = correct_blame / total_failures
- Baseline = 1 / avg_nodes_per_task

**Cost Estimate:** Depends on HLE task count and model

---

### Experiment 2: Linear Error Curve

**Objective:** Show error grows linearly with chain length.

**Setup:**
1. Create synthetic tasks with controllable chain length (2, 3, 5, 7, 10 nodes)
2. Inject known error probability at each node
3. Measure end-to-end success rate

**Metrics:**
- Plot: chain_length vs error_rate
- Fit: linear vs exponential model
- Compare: with validators vs without validators

**Cost Estimate:** Low (synthetic tasks, can use cheaper model)

---

### Experiment 3: Validator Consistency

**Objective:** Verify validator is approximately non-expansive.

**Setup:**
1. Collect (prompt, artifact, spec) triples from real runs
2. Run same triple through validator K times (K=10)
3. Measure score variance

**Metrics:**
- Mean variance across samples
- Max variance (worst case)
- Flip rate: how often PASS/FAIL changes for same input

**Cost Estimate:** Medium (multiple validator calls per sample)

---

### Experiment 4: Fail-Fast Savings

**Objective:** Quantify compute savings from early termination.

**Setup:**
1. Run tasks with GFSO (fail-fast enabled)
2. Run same tasks with naive chain (no early termination)
3. Compare total tokens/time for failed tasks

**Metrics:**
- Tokens saved per failed task
- Time saved per failed task
- Cost reduction percentage

**Cost Estimate:** Medium (need to run both configurations)

---

### Experiment 5: Soft Validation Curve (Theorem 3.2)

**Objective:** Verify that soft validation provides quantifiable improvement over no validation, and measure empirical degradation factor g(T,M).

**Setup:**
1. Select benchmark tasks with ground truth (e.g., MATH dataset)
2. Run pipeline with varying validation thresholds T ∈ {0.1, 0.2, 0.3, 0.5, 0.8, 1.0}
3. For each T, vary retry count M ∈ {1, 2, 3, 5}
4. For each (T, M) configuration, measure:
   - Success rate (matches ground truth)
   - Average accepted epsilon (from validator scores)
   - Total retry count
   - Token cost

**Metrics:**
- **Primary:** Plot success_rate vs T for each M (should be monotonic increasing)
- **Degradation factor:** g(T,M) = E[accepted_epsilon] / E[epsilon_no_validation]
- **Comparison:** Fit theoretical g(T,M) (Proposition 3.3) vs empirical
- **Distribution:** Histogram of epsilon values → fit Beta/Gamma/Uniform to get P_ε

**Expected Results (from Theorem 3.2):**
- T=0.1, M=3 → ~90% success, low g (~0.15)
- T=0.5, M=1 → ~60% success, medium g (~0.5)
- T=1.0, M=1 → ~30% success, high g (~1.0, no filtering)
- Empirical g should match theoretical within 20%

**Validation of Claims:**
- Monotonicity: ∂g/∂T > 0, ∂g/∂M < 0 (Proposition 3.3.1)
- Minimum 5× improvement at T=0.2μ (Proposition 3.3.4)
- Linear bound: Global error ∝ n·g(T,M) (Theorem 3.2)

**Cost Estimate:** High (need to run 6 thresholds × 4 retry counts × N tasks)
- Suggest: N=20 tasks, total ~480 pipeline runs
- Use haiku-4.5 to reduce cost

**Artifacts:**
- `experiments/soft_validation_curve.py` (runner)
- `outputs/g_factor_empirical.csv` (raw data)
- `outputs/p_epsilon_distribution.png` (histogram + fitted distribution)
- `outputs/theorem_3_2_validation.png` (g theoretical vs empirical)

---

## 4. Evidence Log

### [DATE] - [Experiment/Observation]

(Template for recording results)

**What:**
**Result:**
**Interpretation:**
**Artifacts:** (logs, plots, data files)

---

## 5. Open Questions

1. **How to measure input distance for prompts?**
   - Edit distance? Semantic embedding distance?
   - Need consistent metric for non-expansive verification

2. **What is acceptable variance for "approximate" non-expansive?**
   - User observed ~10% - is this enough?
   - Need theoretical justification or empirical threshold

3. ~~**How to handle partial failures?**~~ **RESOLVED (Theorem 3.2)**
   - ~~Node produces output but it's "mostly correct"~~
   - ~~Binary PASS/FAIL vs soft scores?~~
   - **Solution:** Soft validation with threshold T and retries M
   - **Formalization:** See mathematics.md §3.2-3.3 for degradation factor g(T,M)
   - **Empirical test:** Experiment 5 measures actual improvement

4. **Swarm consensus for perception - is this formally sound?**
   - Majority vote has known properties (Condorcet)
   - How does this interact with GFSO guarantees?

---

## 6. Paper Outline (Draft)

**Title:** Deterministic Error Localization in Stochastic LLM Agents via Topological Validation

**Abstract:** [TODO after experiments]

**1. Introduction**
- Problem: LLM agents fail silently, errors propagate
- Solution: Topological validation at each node
- Contribution: Formal framework + empirical validation

**2. Background**
- LLM agents and their failure modes
- Category theory basics (accessible version)
- Related work: LangGraph, AutoGen, DSPy

**3. GFSO Framework**
- Mathematical foundation (simplified from mathematics.md)
- Architecture (from agent_architecture.md)
- Key insight: validation as natural transformation

**4. Implementation**
- Blueprint (DAG) construction
- Validator design
- Swarm strategy for perception

**5. Theoretical Analysis**
- Linear error bound (Theorem)
- Fail-fast guarantee (Proposition)
- Scope limitations (honest)

**6. Experiments**
- Error localization accuracy
- Linear error curve
- Validator consistency
- Compute savings

**7. Discussion**
- When GFSO works / doesn't work
- Practical recommendations
- Future work

**8. Conclusion**

---

## Changelog

- 2026-01-05: Initial document created with claims and experimental plan
