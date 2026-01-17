"""
Validator Protocol - γ-Contractive Maps (Paper v7.0)

Validators in GFSO v1.0 are contractive maps that TRANSFORM distributions,
not just CHECK them (unlike v0.1 where validators were pure checkers).

Key concept (Paper v7.0, Section 5):
- Validator V: D(X) → D(X) is γ-contractive if W₁(V(μ), V(ν)) ≤ γ·W₁(μ,ν)
- Stability requires L·γ ≤ 1, where L is morphism Lipschitz degree
- γ < 1 ensures contraction towards ideal distribution
"""

from abc import ABC, abstractmethod
from typing import TypeVar, Optional, Protocol

__all__ = ['Validator', 'ValidatorProtocol']

State = TypeVar('State')
Distribution = dict[State, float]


class ValidatorProtocol(Protocol):
    """Protocol for validators (structural subtyping)."""

    def __call__(self, dist: Distribution) -> Distribution:
        """Apply validator to distribution."""
        ...

    def contraction_degree(self) -> float:
        """Return γ: contraction factor."""
        ...


class Validator(ABC):
    """
    Abstract γ-contractive validator (Paper v7.0, Definition 5.1).

    V: D(X) → D(X) is a contractive map satisfying:
        W₁(V(μ), V(ν)) ≤ γ · W₁(μ, ν)  for all μ, ν ∈ D(X)

    where γ ∈ [0, 1] is the contraction degree.

    Stability Criterion (Theorem 5.2):
        A chain with Lipschitz morphisms (L) and validator (γ) is stable iff:
        L · γ ≤ 1

    Regimes:
    - L·γ < 1: Bounded errors (converges to steady state)
    - L·γ = 1: Linear error growth
    - L·γ > 1: Exponential error growth (unstable)

    Validators TRANSFORM distributions (unlike v0.1 where they just CHECK).
    This is the key conceptual change in Paper v7.0.

    Subclasses must implement:
        __call__: Apply transformation V(dist) → dist'
        contraction_degree: Return γ value
    """

    @abstractmethod
    def __call__(self, dist: Distribution[State]) -> Distribution[State]:
        """
        Apply validator transformation to distribution.

        Args:
            dist: Input distribution over states

        Returns:
            Transformed distribution (must satisfy probability axioms)

        Note:
            This is a TRANSFORMATION, not just a check.
            The validator actively modifies the distribution towards
            the ideal specification.
        """
        pass

    @abstractmethod
    def contraction_degree(self) -> float:
        """
        Return contraction factor γ ∈ [0, 1].

        W₁(V(μ), V(ν)) ≤ γ · W₁(μ, ν)

        Returns:
            γ value (smaller is more contractive)

        Values:
            γ = 0: Perfect validator (collapses to single point)
            γ < 1: Contractive (required for stability with L > 1)
            γ = 1: Non-contractive (identity-like)
        """
        pass

    @property
    def gamma(self) -> float:
        """Shorthand for contraction_degree()."""
        return self.contraction_degree()

    def is_contractive(self) -> bool:
        """Check if validator is strictly contractive (γ < 1)."""
        return self.contraction_degree() < 1.0

    def verify_contraction(
        self,
        test_dists: list[Distribution[State]],
        state_metric,
    ) -> tuple[bool, float]:
        """
        Empirically verify γ-contractiveness on test distributions.

        Computes max(W₁(V(μ), V(ν)) / W₁(μ, ν)) over pairs.

        Args:
            test_dists: Sample distributions to test
            state_metric: Distance function on state space

        Returns:
            (is_valid, observed_gamma) where:
            - is_valid: True if observed_gamma ≤ declared contraction_degree
            - observed_gamma: Maximum observed contraction ratio
        """
        from gfso.core.metric import wasserstein_1_discrete

        if len(test_dists) < 2:
            return True, 0.0

        max_ratio = 0.0
        declared_gamma = self.contraction_degree()

        for i, mu in enumerate(test_dists):
            for nu in test_dists[i + 1:]:
                d_input = wasserstein_1_discrete(mu, nu, state_metric)

                if d_input < 1e-10:
                    continue

                V_mu = self(mu)
                V_nu = self(nu)
                d_output = wasserstein_1_discrete(V_mu, V_nu, state_metric)

                ratio = d_output / d_input
                max_ratio = max(max_ratio, ratio)

        is_valid = max_ratio <= declared_gamma + 1e-6
        return is_valid, max_ratio

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(γ={self.contraction_degree():.4f})"


# Legacy compatibility alias
def get_epsilon(validator: Validator) -> float:
    """
    Legacy compatibility: Convert γ to ε-like bound.

    In v0.1, validators had ε bounds. In v1.0, they have γ contraction.
    This provides a rough conversion for backwards compatibility.

    Note: This is not mathematically rigorous; use contraction_degree() directly.
    """
    return 1.0 - validator.contraction_degree()
