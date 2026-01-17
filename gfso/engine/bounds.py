"""
Error Bound Computations (Paper v7.0, Section 5)

Implements error bound formulas from the theory:
- Exponential bound O(L^n) for unvalidated chains
- Validated bounds depending on L·γ regime
- Steady-state bounds for bounded regime

Key formulas (Theorem 5.1, Corollary 5.3):
- Unvalidated: E_n ≤ L^n · ε₀ + δ_F · (L^n - 1)/(L - 1)
- Validated (L·γ < 1): E'_n → E'_∞ = γ(ε₀ + δ_F)/(1 - Lγ)
- Validated (L·γ = 1): E'_n ≤ γε₀ + nγδ_F
- Validated (L·γ > 1): E'_n ≤ (Lγ)^n · γε₀ + ...
"""

from typing import Optional
from .stability import StabilityRegime

__all__ = [
    'exponential_bound',
    'validated_bound',
    'steady_state_bound',
    'linear_bound_legacy',
    'bound_at_step',
]


def exponential_bound(
    L: float,
    n: int,
    eps0: float,
    delta_F: float = 0.0,
) -> float:
    """
    Unvalidated error bound O(L^n) (Theorem 5.1).

    Without validation, errors grow exponentially:
        E_n ≤ L^n · ε₀ + δ_F · (L^n - 1)/(L - 1)

    For L = 1 (non-expansive):
        E_n ≤ ε₀ + n · δ_F

    Args:
        L: Lipschitz degree
        n: Chain length (number of morphism applications)
        eps0: Initial error
        delta_F: Composition discrepancy per step

    Returns:
        Upper bound on error after n steps
    """
    if n <= 0:
        return eps0

    L_n = L ** n

    if abs(L - 1.0) < 1e-10:
        # L ≈ 1: geometric series sum is n
        return eps0 + n * delta_F

    # General case: L^n·ε₀ + δ_F·(L^n - 1)/(L - 1)
    geometric_sum = (L_n - 1.0) / (L - 1.0)
    return L_n * eps0 + delta_F * geometric_sum


def validated_bound(
    L: float,
    gamma: float,
    n: int,
    eps0: float,
    delta_F: float = 0.0,
) -> float:
    """
    Validated error bound (Corollary 5.3).

    With validator applied after each morphism:
        E'_n depends on regime L·γ

    - L·γ < 1: E'_n ≤ E'_∞ = γ(ε₀ + δ_F)/(1 - Lγ)
    - L·γ = 1: E'_n ≤ γε₀ + nγδ_F
    - L·γ > 1: E'_n ≤ (Lγ)^n · γε₀ + γδ_F · ((Lγ)^n - 1)/(Lγ - 1)

    Args:
        L: Lipschitz degree
        gamma: Validator contraction degree
        n: Chain length
        eps0: Initial error
        delta_F: Composition discrepancy per step

    Returns:
        Upper bound on error after n validated steps
    """
    if n <= 0:
        return gamma * eps0

    product = L * gamma

    if product < 1.0 - 1e-9:
        # Bounded regime: converges to steady state
        return steady_state_bound(L, gamma, eps0, delta_F)

    elif product < 1.0 + 1e-9:
        # Linear regime: E'_n ≤ γε₀ + nγδ_F
        return gamma * eps0 + n * gamma * delta_F

    else:
        # Divergent regime: exponential in (Lγ)^n
        product_n = product ** n

        if abs(product - 1.0) < 1e-10:
            geometric_sum = n
        else:
            geometric_sum = (product_n - 1.0) / (product - 1.0)

        return product_n * gamma * eps0 + gamma * delta_F * geometric_sum


def steady_state_bound(
    L: float,
    gamma: float,
    eps0: float,
    delta_F: float = 0.0,
) -> float:
    """
    Steady-state error bound for L·γ < 1 regime.

    E'_∞ = γ(ε₀ + δ_F) / (1 - Lγ)

    This is the asymptotic bound that validated errors converge to.

    Args:
        L: Lipschitz degree
        gamma: Validator contraction degree
        eps0: Initial error
        delta_F: Composition discrepancy

    Returns:
        Steady-state bound, or inf if L·γ ≥ 1

    Raises:
        ValueError: If L·γ ≥ 1 (no steady state exists)
    """
    product = L * gamma

    if product >= 1.0:
        raise ValueError(f"Steady state requires L·γ < 1, got {product:.4f}")

    return gamma * (eps0 + delta_F) / (1.0 - product)


def linear_bound_legacy(
    local_errors: list[float],
    n: int,
    delta_F: float = 0.0,
) -> float:
    """
    Legacy linear bound from Paper v0.1 (Theorem 3.1).

    E ≤ Σεᵢ + (n-1)δ_F

    This assumed non-expansive morphisms (L ≤ 1).
    Retained for backwards compatibility.

    Args:
        local_errors: List of ε values for each task
        n: Number of steps
        delta_F: Composition discrepancy

    Returns:
        Linear error bound
    """
    return sum(local_errors) + max(0, n - 1) * delta_F


def bound_at_step(
    L: float,
    gamma: float,
    step: int,
    eps0: float,
    delta_F: float = 0.0,
    with_validation: bool = True,
) -> float:
    """
    Compute error bound at specific step.

    Convenience function combining validated/unvalidated bounds.

    Args:
        L: Lipschitz degree
        gamma: Validator contraction (ignored if with_validation=False)
        step: Step number (0-indexed)
        eps0: Initial error
        delta_F: Composition discrepancy
        with_validation: Whether validation is applied

    Returns:
        Error bound at given step
    """
    n = step + 1

    if with_validation:
        return validated_bound(L, gamma, n, eps0, delta_F)
    else:
        return exponential_bound(L, n, eps0, delta_F)


def bound_sequence(
    L: float,
    gamma: float,
    n_steps: int,
    eps0: float,
    delta_F: float = 0.0,
    with_validation: bool = True,
) -> list[float]:
    """
    Compute error bound trajectory over n steps.

    Useful for plotting/analysis.

    Args:
        L: Lipschitz degree
        gamma: Validator contraction
        n_steps: Number of steps to compute
        eps0: Initial error
        delta_F: Composition discrepancy
        with_validation: Whether validation is applied

    Returns:
        List of bounds [E_0, E_1, ..., E_{n-1}]
    """
    return [
        bound_at_step(L, gamma, i, eps0, delta_F, with_validation)
        for i in range(n_steps)
    ]


def sparse_validated_bound(
    L: float,
    gamma: float,
    n: int,
    k: int,
    eps0: float,
    delta_F: float = 0.0,
) -> float:
    """
    Error bound for sparse validation (every k steps).

    Paper v7.0, Corollary 5.4:
        Effective product is L^k · γ
        Bound computed over n/k validation cycles

    Args:
        L: Lipschitz degree
        gamma: Validator contraction
        n: Total chain length
        k: Validation interval
        eps0: Initial error
        delta_F: Composition discrepancy

    Returns:
        Error bound with sparse validation
    """
    if k <= 0:
        k = 1

    # Number of validation cycles
    cycles = (n + k - 1) // k

    # Effective Lipschitz for k unvalidated steps
    L_effective = L ** k

    # Effective delta_F for k steps
    delta_effective = exponential_bound(L, k, 0.0, delta_F)

    return validated_bound(L_effective, gamma, cycles, eps0, delta_effective)
