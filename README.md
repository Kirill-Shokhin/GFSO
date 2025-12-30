# GFSO: General Framework of Structural Optimization

Framework for compositional validation of stochastic processes using category-theoretic foundations.

## Overview

GFSO provides mathematical guarantees for error propagation in agent chains and workflow systems. By modeling tasks as morphisms in an enriched Kleisli category, we prove linear (rather than exponential) error accumulation under explicit regularity conditions.

**Core idea:** Transform reliability from an agent property to a topological property of the control structure.

## Theoretical Foundation

- **Mathematical proof**: [docs/mathematics.md](docs/mathematics.md)
  Rigorous formulation via Wasserstein metric and natural transformations

- **Conceptual guide**: [docs/context.md](docs/context.md)
  Engineering interpretation and operational semantics

## Structure

```
gfso/
├── core/       # Graph abstractions, topological sorting
├── contract/   # Validators (unit + integration)
└── engine/     # Execution runtime with error bounds
```

## Status

**Mathematical foundation**: Publication-ready (see [docs/mathematics.md](docs/mathematics.md)).

**Implementation**: Early POC - mathematical primitives only.

**Current state:**
- ✓ Kleisli category composition (Chapman-Kolmogorov) - working
- ✓ Wasserstein metric on distributions - working
- ✓ DAG structure with NetworkX - working
- ✗ Validator application with retry/re-grounding - **not implemented**
- ✗ Theorem 3.1 error bound guarantees - **not verified**

**What works:** Core mathematical building blocks for compositional validation.

**What doesn't:** Full GFSO workflow with validators, retry logic, and proven error bounds.

This is a foundation for `gfso_agent` (concrete LLM agent implementation).

## Reference Implementation

See `examples/simple_demo.py` for demonstration:
- Kleisli composition (Chapman-Kolmogorov)
- Wasserstein metric on distributions
- TaskDAG construction
- Error bound formula computation

Note: Demo shows primitives only, not full GFSO workflow.

## License

MIT
