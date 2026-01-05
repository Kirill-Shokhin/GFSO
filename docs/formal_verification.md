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

3. **How to handle partial failures?**
   - Node produces output but it's "mostly correct"
   - Binary PASS/FAIL vs soft scores?

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
