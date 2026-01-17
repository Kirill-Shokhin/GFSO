"""
GFSO: General Framework of Structural Optimization v1.0

Category-theoretic framework for compositional validation of stochastic systems.

Paper v7.0 Key Changes:
- Morphisms are L-Lipschitz (L > 1 allowed)
- Validators are γ-contractive maps (transform, not just check)
- Stability criterion: L·γ ≤ 1
- Error bounds: O(L^n) → bounded if L·γ < 1

Core exports:
    - Kleisli category primitives (compose_kleisli, Distribution, etc.)
    - LipschitzMorphism with known Lipschitz degree
    - Wasserstein metrics and Lipschitz estimation
    - Validator protocol (γ-contractive)
    - Concrete validators (Identity, Scaling, Truncation, Composite)
    - TaskDAG for workflow definition
    - GFSOEngine with stability analysis and validator application
    - Stability analysis (StabilityAnalysis, check_stability)
    - Error bounds (validated_bound, exponential_bound, steady_state_bound)
"""

__version__ = "1.0.0"

# Core Kleisli category
from gfso.core.kleisli import (
    Distribution,
    KleisliMorphism,
    compose_kleisli,
    identity_kleisli,
    dirac_delta,
    normalize_distribution,
    is_valid_distribution,
)

# Lipschitz morphisms
from gfso.core.morphism import (
    LipschitzMorphism,
    compose_lipschitz,
    identity_lipschitz,
    chain_lipschitz_degree,
)

# Metrics
from gfso.core.metric import (
    StateMetric,
    wasserstein_1_discrete,
    wasserstein_1_continuous,
    kleisli_metric,
    verify_non_expansive,
    estimate_lipschitz,
)

# Task graph
from gfso.core.graph import Task, TaskDAG

# Validators (base)
from gfso.contract.validator import Validator, ValidatorProtocol

# Validators (concrete implementations)
from gfso.contract.validators import (
    IdentityValidator,
    ScalingValidator,
    TruncationValidator,
    ThresholdValidator,
    CompositeValidator,
    RetryValidator,
    compose_validators,
)

# Stability analysis
from gfso.engine.stability import (
    StabilityRegime,
    StabilityAnalysis,
    check_stability,
    check_sparse_stability,
    required_gamma_for_stability,
    required_validation_interval,
)

# Error bounds
from gfso.engine.bounds import (
    exponential_bound,
    validated_bound,
    steady_state_bound,
    linear_bound_legacy,
    bound_at_step,
    bound_sequence,
    sparse_validated_bound,
)

# Execution engine
from gfso.engine.executor import (
    ExecutionResult,
    ValidationEvent,
    GFSOEngine,
)

__all__ = [
    # Version
    '__version__',

    # Kleisli
    'Distribution',
    'KleisliMorphism',
    'compose_kleisli',
    'identity_kleisli',
    'dirac_delta',
    'normalize_distribution',
    'is_valid_distribution',

    # Lipschitz morphisms
    'LipschitzMorphism',
    'compose_lipschitz',
    'identity_lipschitz',
    'chain_lipschitz_degree',

    # Metrics
    'StateMetric',
    'wasserstein_1_discrete',
    'wasserstein_1_continuous',
    'kleisli_metric',
    'verify_non_expansive',
    'estimate_lipschitz',

    # Graph
    'Task',
    'TaskDAG',

    # Validators
    'Validator',
    'ValidatorProtocol',
    'IdentityValidator',
    'ScalingValidator',
    'TruncationValidator',
    'ThresholdValidator',
    'CompositeValidator',
    'RetryValidator',
    'compose_validators',

    # Stability
    'StabilityRegime',
    'StabilityAnalysis',
    'check_stability',
    'check_sparse_stability',
    'required_gamma_for_stability',
    'required_validation_interval',

    # Bounds
    'exponential_bound',
    'validated_bound',
    'steady_state_bound',
    'linear_bound_legacy',
    'bound_at_step',
    'bound_sequence',
    'sparse_validated_bound',

    # Engine
    'ExecutionResult',
    'ValidationEvent',
    'GFSOEngine',
]
