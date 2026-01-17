"""
Execution engine with stability-aware validation (v1.0).

Modules:
    executor - GFSOEngine with validator application
    stability - Stability analysis (L·γ ≤ 1 criterion)
    bounds - Error bound computations
"""

from .executor import *
from .stability import *
from .bounds import *
