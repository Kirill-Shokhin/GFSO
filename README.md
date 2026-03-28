# GFSO (General Framework for Structured Operations)

**A protocol standard for hierarchical task management, derived from first principles.**

---

## What is GFSO?

Task management in hierarchical organizations has no formal standard: assignments, decomposition, acceptance — all ad hoc. GFSO is a formally derived protocol: 6 original theorems (including impossibility results) + 8 propositions/corollaries supported by classical theory.

**The core insight:** from two axioms (verifiability of goals, decomposability of complex tasks), an entire protocol follows — with proofs that key constructions (binary validation, AND aggregation, 7 failure modes) admit no alternatives.

---

## Key Results

**Original theorems:**

| # | Result | Claim | Proof type |
|---|--------|-------|------------|
| T1 | Compositionality | V(parent) = AND(V(children)) under correct D | Constructive |
| T2 | AND uniqueness | AND is the only non-trivial aggregation | Exhaustive enumeration |
| — | \|L\|=2 impossibility | Binary validation is the only option | Pigeonhole |
| — | 7 FM completeness | Failure modes are exhaustive | Exhaustive case split |
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
| — | Minimality | Basis {T, D, Dep, Del} is minimal | Constructive |

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
  → AI layer: Solver + LLM (necessity from P6 + Simon)
```

Every step is motivated by the previous. Design decisions are explicit.

---

## Documents

| File | Purpose |
|------|---------|
| [`docs/applied_gfso_v3.md`](docs/applied_gfso_v3.md) | Formal paper (Russian draft; EN forthcoming) |
| [`docs/applied_gfso_vision.md`](docs/applied_gfso_vision.md) | Vision: case studies, FAQ, per-metric analysis, adoption arguments |
| [`docs/architecture.md`](docs/architecture.md) | Code architecture: FSM invariant, module structure, L1/L2/L3 |

---

## Implementation

```
gfso/
  core/       ← Level 1: protocol standard (pure library)
    types/      State(10), Signal(13), FM(7), effects, ports
    protocol/   FSM transition table, invariants, role validation
    handlers/   CHECK-1-8, System LLM recommend
    graph/      G model, mutations, 5 metrics Q
  engine/     ← Level 2: framework (Engine facade, event loop, audit, events)
  adapters/   ← Level 3: pluggable (MemoryStorage, StubLLM, agents)
```

100 tests. Dependency: `core/ ← engine/ ← adapters/`

---

## Status

- [x] Formal framework: 6 theorems + 8 propositions/corollaries
- [x] Impossibility results on foundations (|L|=2, AND, 7 FM)
- [x] AI layer formalized (Solver + LLM, Chollet Level ≥ 2)
- [x] Vision document with practical illustrations
- [x] Protocol engine: Level 1 (core) + Level 2 (engine)
- [ ] English translation
- [ ] Level 3: production adapters (SQLite, Claude API, HTTP server)
- [ ] Empirical validation (deployment ≥ 6 months)

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
