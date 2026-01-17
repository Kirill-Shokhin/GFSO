"""
Stability Analysis for GFSO (Paper v7.0, Section 5)

Implements the stability criterion L·γ ≤ 1 and regime classification.

Key concepts:
- L: Lipschitz degree of morphism chain (∏ Lᵢ)
- γ: Contraction degree of validator
- L·γ: Stability product

Regimes:
- L·γ < 1: BOUNDED (errors converge to steady state)
- L·γ = 1: LINEAR (errors grow linearly with chain length)
- L·γ > 1: DIVERGENT (errors grow exponentially)
"""

from dataclasses import dataclass
from typing import Literal, Optional, Sequence

from gfso.core.morphism import LipschitzMorphism, chain_lipschitz_degree
from gfso.contract.validator import Validator

__all__ = [
    'StabilityRegime',
    'StabilityAnalysis',
    'check_stability',
    'check_sparse_stability',
]

StabilityRegime = Literal["bounded", "linear", "divergent"]


@dataclass
class StabilityAnalysis:
    """
    Result of stability analysis for a morphism-validator chain.

    Paper v7.0, Theorem 5.2: Stability criterion L·γ ≤ 1

    Attributes:
        L: Maximum/effective Lipschitz degree of morphisms
        gamma: Contraction degree of validator
        product: L·γ (stability product)
        is_stable: True if L·γ ≤ 1
        regime: "bounded" | "linear" | "divergent"
        steady_state_bound: E'∞ if bounded regime, else None
        validation_interval: k for sparse validation (default 1)
    """
    L: float
    gamma: float
    product: float
    is_stable: bool
    regime: StabilityRegime
    steady_state_bound: Optional[float]
    validation_interval: int = 1

    @property
    def is_bounded(self) -> bool:
        """Check if errors are bounded (L·γ < 1)."""
        return self.regime == "bounded"

    @property
    def is_linear(self) -> bool:
        """Check if errors grow linearly (L·γ = 1)."""
        return self.regime == "linear"

    @property
    def is_divergent(self) -> bool:
        """Check if errors diverge exponentially (L·γ > 1)."""
        return self.regime == "divergent"

    def describe(self) -> str:
        """Human-readable description of stability analysis."""
        stability = "STABLE" if self.is_stable else "UNSTABLE"
        regime_desc = {
            "bounded": "errors converge to steady state",
            "linear": "errors grow linearly",
            "divergent": "errors grow exponentially",
        }

        msg = f"[{stability}] L·γ = {self.product:.4f} ({self.regime}: {regime_desc[self.regime]})"

        if self.steady_state_bound is not None:
            msg += f"\n  Steady-state bound E'∞ ≤ {self.steady_state_bound:.4f}"

        if self.validation_interval > 1:
            msg += f"\n  Sparse validation: every {self.validation_interval} steps"

        return msg

    def __repr__(self) -> str:
        return f"StabilityAnalysis(L={self.L:.3f}, γ={self.gamma:.3f}, L·γ={self.product:.3f}, regime='{self.regime}')"


def check_stability(
    morphisms: Sequence[LipschitzMorphism],
    validator: Validator,
    eps0: float = 0.0,
    delta_F: float = 0.0,
) -> StabilityAnalysis:
    """
    Check stability criterion for morphism chain with validator.

    Paper v7.0, Theorem 5.2:
        Chain is stable iff L·γ ≤ 1
        where L = ∏ Lᵢ (chain Lipschitz) and γ = validator contraction

    For per-step analysis (applying validator after each morphism),
    use L = max(Lᵢ) instead of product.

    Args:
        morphisms: List of LipschitzMorphism in execution order
        validator: γ-contractive validator applied after each morphism
        eps0: Initial error (default 0)
        delta_F: Composition discrepancy (functor laxity)

    Returns:
        StabilityAnalysis with regime classification and bounds
    """
    if not morphisms:
        return StabilityAnalysis(
            L=1.0,
            gamma=validator.contraction_degree(),
            product=validator.contraction_degree(),
            is_stable=True,
            regime="bounded",
            steady_state_bound=0.0,
        )

    # For per-step validation, L is max of individual Lipschitz constants
    L = max(m.lipschitz_degree for m in morphisms)
    gamma = validator.contraction_degree()
    product = L * gamma

    # Determine regime
    if product < 1.0 - 1e-9:
        regime: StabilityRegime = "bounded"
    elif product < 1.0 + 1e-9:
        regime = "linear"
    else:
        regime = "divergent"

    is_stable = product <= 1.0 + 1e-9

    # Compute steady-state bound for bounded regime
    # E'∞ = γ(ε₀ + δ_F) / (1 - Lγ)
    steady_state_bound = None
    if regime == "bounded" and product < 1.0:
        steady_state_bound = gamma * (eps0 + delta_F) / (1.0 - product)

    return StabilityAnalysis(
        L=L,
        gamma=gamma,
        product=product,
        is_stable=is_stable,
        regime=regime,
        steady_state_bound=steady_state_bound,
    )


def check_sparse_stability(
    morphisms: Sequence[LipschitzMorphism],
    validator: Validator,
    validation_interval: int,
    eps0: float = 0.0,
    delta_F: float = 0.0,
) -> StabilityAnalysis:
    """
    Check stability for sparse validation (validator applied every k steps).

    Paper v7.0, Corollary 5.4:
        For sparse validation every k steps, stability requires:
        L^k · γ ≤ 1

        where L^k accounts for k unvalidated morphism applications.

    Args:
        morphisms: List of LipschitzMorphism in execution order
        validator: γ-contractive validator
        validation_interval: k (apply validator every k steps)
        eps0: Initial error
        delta_F: Composition discrepancy

    Returns:
        StabilityAnalysis with sparse validation parameters
    """
    if not morphisms or validation_interval < 1:
        return check_stability(morphisms, validator, eps0, delta_F)

    # For sparse validation, effective L is L^k
    L = max(m.lipschitz_degree for m in morphisms)
    L_effective = L ** validation_interval
    gamma = validator.contraction_degree()
    product = L_effective * gamma

    if product < 1.0 - 1e-9:
        regime: StabilityRegime = "bounded"
    elif product < 1.0 + 1e-9:
        regime = "linear"
    else:
        regime = "divergent"

    is_stable = product <= 1.0 + 1e-9

    steady_state_bound = None
    if regime == "bounded" and product < 1.0:
        # Adjusted for sparse validation
        steady_state_bound = gamma * (eps0 + validation_interval * delta_F) / (1.0 - product)

    return StabilityAnalysis(
        L=L_effective,
        gamma=gamma,
        product=product,
        is_stable=is_stable,
        regime=regime,
        steady_state_bound=steady_state_bound,
        validation_interval=validation_interval,
    )


def required_gamma_for_stability(L: float, target_product: float = 0.9) -> float:
    """
    Compute required γ for stability given Lipschitz constant L.

    For L·γ ≤ target_product (default 0.9 for safety margin).

    Args:
        L: Lipschitz degree
        target_product: Target L·γ value (default 0.9)

    Returns:
        Maximum allowed γ for stability
    """
    if L <= 0:
        return 1.0
    return target_product / L


def required_validation_interval(L: float, gamma: float) -> int:
    """
    Compute maximum validation interval k such that L^k · γ ≤ 1.

    Args:
        L: Lipschitz degree
        gamma: Validator contraction

    Returns:
        Maximum k, or -1 if no valid k exists (L ≥ 1/γ)
    """
    import math

    if L <= 0 or gamma <= 0:
        return -1

    if L * gamma <= 1.0:
        # Any interval works for stable single-step
        return 1_000_000  # Effectively infinite

    if L >= 1.0:
        # L^k grows, need L^k · γ ≤ 1 → L^k ≤ 1/γ
        # k ≤ log(1/γ) / log(L)
        if gamma >= 1.0:
            return -1  # Impossible
        max_k = math.log(1.0 / gamma) / math.log(L)
        return max(1, int(max_k))

    # L < 1: L^k shrinks, always stable for large enough k
    return 1_000_000
