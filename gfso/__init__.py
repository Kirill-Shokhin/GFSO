"""
GFSO: General Framework of Structural Optimization

Category-theoretic framework for compositional validation of stochastic systems.

Core exports:
    - Kleisli category primitives (compose_kleisli, Distribution, etc.)
    - Wasserstein metrics
    - Validator protocol
    - TaskDAG for workflow definition
    - GFSOEngine for execution with guaranteed error bounds
"""

__version__ = "0.1.0"

# Core Kleisli category
from gfso.core.kleisli import (
    Distribution,
    KleisliMorphism,
    compose_kleisli,
    identity_kleisli,
    dirac_delta,
)

# Metrics
from gfso.core.metric import (
    StateMetric,
    wasserstein_1_discrete,
    kleisli_metric,
    verify_non_expansive,
)

# Task graph
from gfso.core.graph import Task, TaskDAG

# Validators
from gfso.contract.validator import Validator

# Execution engine
from gfso.engine.executor import ExecutionResult, GFSOEngine

__all__ = [
    # Version
    '__version__',

    # Kleisli
    'Distribution',
    'KleisliMorphism',
    'compose_kleisli',
    'identity_kleisli',
    'dirac_delta',

    # Metrics
    'StateMetric',
    'wasserstein_1_discrete',
    'kleisli_metric',
    'verify_non_expansive',

    # Graph
    'Task',
    'TaskDAG',

    # Validators
    'Validator',

    # Engine
    'ExecutionResult',
    'GFSOEngine',
]
