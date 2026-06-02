# GFSO (General Framework for Structured Operations)

**A formal language for the minimum a verifiable task-handoff transaction must carry — derived from two axioms and proven minimal.**

---

## What is GFSO?

GFSO is a **mathematically defined** structure (primitives, operations, laws), the **smallest possible** (nothing can be removed without losing expressiveness), describing **what must be present** in one handoff of a task from an issuer to an executor so that the handoff can be verified and composed. It is **not chosen** — it is **derived** from two simple statements: that goals are verifiable and that complex work decomposes. If those two statements hold for a domain, GFSO necessarily describes its handoffs. If they don't, GFSO doesn't apply, and that boundary is explicit.

The unit of analysis is **one handoff transaction**, not a project, process, or team. Hierarchy, multi-agent, organization — all are compositions of such transactions.

What a transaction must carry: a Spec, a finite set of decidable Criteria, a Deadline, an explicit NEGLECTED section, a Delegation, and (when decomposed) Dependencies plus a composition function. Drop any of these and a specific failure mode (of the seven proven exhaustive) becomes unavoidable.

**Analog:** TCP/IP for hierarchical work coordination, or Codd 1970 for relational databases — tractable math whose framing enables a domain, not a productivity tool.

**Foundations:** two axioms (A1 verifiability of goals, A2 decomposability of complex tasks), from which the entire protocol follows — including impossibility results that key constructions (binary validation, AND aggregation, 7 failure modes) admit no alternatives. 6 original theorems + 8 propositions/corollaries supported by classical theory.

**Theory-model layer (§18.10):** beyond a standard, GFSO *derives the agent* (human or LLM) as a necessary structural link rather than presuming it — the formal half cannot supply a decomposition's domain-correctness by itself (Lemma 1), nor can pure declaration ground it (Lemma 3), so an empirical-contact carrier is necessary. This lets GFSO *explain* pre-theoretic success (and the 7 FM) and *predict*, falsifiably, agent substitutability and the applicability boundary.

---

## Key Results

**Original theorems:**

| # | Result | Claim | Proof type |
|---|--------|-------|------------|
| T1 | Compositionality | V(parent) = AND(V(children)) under correct D | Constructive |
| T2 | AND uniqueness | AND is the only non-trivial aggregation | Exhaustive enumeration |
| — | \|L\|=2 | Binary validation forced (injectivity from decision-relevance; \|A\|=2 architectural) | Pigeonhole |
| — | 7 FM completeness | Failure modes are exhaustive — proven as an independent basis (residue: single-clock) | Exhaustive case split |
| T10 | Self-measuring | Q computable from execution trace | Constructive |
| T11 | Structural transparency | Every decision has a record | From invariants |

**Propositions (supported by classical theory):**

| # | Result | Claim | Foundation |
|---|--------|-------|------------|
| P3 | Blackwell dominance | GFSO informationally dominates status quo | Blackwell 1953 |
| P4 | Constraint improvement | Constraints improve payoff when Δ > c | Simon 1955 |
| C5 | α-monotonicity | Quality ↑ with adherence | Corollary of P3 |
| P6 | Temporal monotonicity | Quality ↑ over time | Blackwell |
| P7 | Scale bounds | Cascade: errors ≤ (L·γ)ⁿ | Operator composition |
| P8 | Bayesian IC | Honesty optimal when cost(defect) > cost(signal) | Hurwicz 1960 |
| P9 | Decomposition quality | 4 independent improvement mechanisms | P3 + P7 |
| — | Minimality | Basis {T, D, Dep, Del} is minimal — each element necessary (uniqueness open, §18.9) | Constructive |

---

## Logical Chain

```
A1, A2 (axioms)
  → {T, D, Del, Dep, V} (minimal basis)
  → |L|=2 (impossibility), AND (uniqueness)
  → 7 failure modes (completeness proven)
  → Standards + 3 verification levels (CHECK-1–8)
  → Protocol: 12 P2P signals + timeout, 10 states (minimal)
  → Graph G + 5 metrics Q (minimal, self-measuring)
  → AI layer: Solver + LLM (capacity-necessity: Simon + info-volume)
  → Theory-model (§18.10): agent derived necessary, not presumed
                           (GFSO = standard + theory-model)
```

Every step is motivated by the previous. Design decisions are explicit.

---

## Documents

| File | Purpose |
|------|---------|
| [`docs/applied_gfso_v3.md`](docs/applied_gfso_v3.md) | Formal paper (canon, v3.4; Russian draft, EN forthcoming). Incl. §17.1 adaptive stratification, §17.2 Scrum ⊂ GFSO, **§18.10 theory-model (agent derived)** |
| [`docs/CORE.md`](docs/CORE.md) | One-page definition of what GFSO is (read first) |
| [`docs/EVIDENCE_LOG.md`](docs/EVIDENCE_LOG.md) | Dry empirical/derivation record (E1 §9/§9.1, theory-model §10/§10.1) |
| [`docs/applied_gfso_vision.md`](docs/applied_gfso_vision.md) | Vision companion: case studies, FAQ, per-metric analysis, adoption arguments |
| [`docs/architecture.md`](docs/architecture.md) | Code architecture: FSM invariant, module structure, L1/L2/L3 |

---

## Implementation

```
gfso/
  core/         ← Level 1: protocol standard (pure library)
    types/        State(10), Signal(13), FM(7), effects, ports
    protocol/     FSM transition table, invariants, role validation
    handlers/     CHECK-1-8, System LLM recommend
    graph/        G model, mutations, 5 metrics Q
  engine/       ← Level 2: framework (Engine facade, event loop, audit, events)
  adapters/     ← Level 3: pluggable
    storage/      memory, sqlite
    llm/          claude, stub
    agents/       bench_agent
    verifiers/    subprocess (LCB-style I/O), unittest (BCB-style pytest)
  api/          ← FastAPI app: REST + WebSocket
  web/          ← UI surface (index.html, gfso.css, tokens.css)
  cli.py        ← `python -m gfso.cli serve --reload`

bench/          ← benchmark harness (dataset-agnostic)
  provider.py, task.py, runner.py, oneshot.py, gfso_runner.py, scorer.py
  providers/    livecodebench, bigcodebench

scripts/        ← entry points: run_livecodebench.py, run_bcb.py,
                  run_bcb_zeroshot.py + legacy bench_single/perfect
data/           ← input data (bench_inputs.json)
runs/           ← bench outputs (gitignored except runs/e1_results/)
docs/           ← theory, architecture, evidence log, protocols
tests/          ← unit + integration tests
```

Dependency: `core/ ← engine/ ← adapters/`. `bench/` depends on `gfso/core/`
and `gfso/adapters/` but not vice versa.

---

## Interface

GFSO ships a web interface — the protocol rendered as a workable surface, not
only an API. The task graph, FSM states, validation outcomes `V(t)`,
failure-mode checks and the AND-composition `V(parent) = AND(V(children))` are
all visible and operable.

![GFSO web interface](docs/ui-baseline.png)

> **Baseline interface.** A working reference UI for exercising the protocol —
> not a finished product. It translates the theory directly: status is rendered
> along the `{intervene, ¬intervene} × {pass, fail, ⊥}` axes, checks are grouped
> by failure mode, decomposition surfaces joint sufficiency. Visual design and
> role workflows are out of scope at this stage.

---

## Status

Theory:
- [x] Formal framework: 6 theorems + 8 propositions/corollaries
- [x] Impossibility results on foundations (|L|=2, AND, 7 FM)
- [x] AI layer formalized (Solver + LLM, Chollet Level ≥ 2)
- [x] Vision document with practical illustrations
- [x] §17.1 adaptive stratification by horizons (derived from Dep coherence + A1 + stationarity)
- [x] §17.2 Scrum ⊂ GFSO — structural containment shown (behavioral derivation open)
- [x] §18.10 theory-model: agent derived as a necessary structural link (not presumed); claims calibrated + full-canon falsifiability pass
- [ ] English translation

Implementation:
- [x] Protocol engine: Level 1 (core) + Level 2 (engine)
- [x] Level 3: production adapters (SQLite, Claude API, FastAPI HTTP+WS server)
- [x] Web UI surfacing the protocol (V(t), NEGLECTED, AND-composition, FM-grouped checks)
- [x] Bench harness separated from core (`bench/` with provider abstraction)
- [x] Domain adapters: SubprocessVerifier (LCB) + UnittestVerifier (BCB)

Empirical:
- [x] E0 — measurement on BCB-Hard 148: explicit unit-test criteria
      (Issuer-side spec discipline) raises Haiku 4.5 solve rate from 29.1% to
      63.5% zero-shot, same compute. Illustrates §3.2 forced binary V on a
      current frontier-adjacent model.
- [x] E1 — 7 FM taxonomy validated on 216 public software postmortems:
      **0/216 need an 8th FM** (completeness-as-basis holds). FM-1 sub-typed
      (a/b/c/d), FM-3 shown two-sided; the 6 non-FM cases are in-framework
      (resilience-worked / delegated). Record: EVIDENCE_LOG §9/§9.1.
- [ ] E2 — LLM-Issuer with vs without GFSO discipline (twin experiment)
- [ ] E3 — Compositional validation theorem in multi-agent decomposition
- [ ] Long-horizon deployment validation (≥ 6 months)

---

## Citation

```bibtex
@article{shokhin2026gfso,
  title={GFSO: Formal Guarantees for Compositional Task Validation
         in Hierarchical Organizations},
  author={Shokhin, Kirill},
  year={2026},
  note={Preprint}
}
```

---

## License

MIT
