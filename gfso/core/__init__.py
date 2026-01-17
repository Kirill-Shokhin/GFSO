"""
Core mathematical primitives for GFSO.

Modules:
    kleisli - Kleisli category of Distribution monad
    metric - Wasserstein metrics and enrichment
    morphism - Lipschitz morphisms with bounded expansion
    graph - Task dependency DAG (Category I)
"""

from .kleisli import *
from .metric import *
from .morphism import *
from .graph import *
