"""
Validator Protocol - Natural Transformation η: F ⇒ G (Definition 2.3)

Defines abstract interface for validators that check implementation
against specification.

This is the core abstraction that gfso_agent will implement with LLMs.
"""

from abc import ABC, abstractmethod
from typing import TypeVar
from gfso.core.kleisli import State, Distribution

__all__ = ['Validator']

State = TypeVar('State')


class Validator(ABC):
    """
    Abstract validator representing natural transformation η: F ⇒ G.

    In category theory: η is a family of morphisms η_A: F(A) → D(G(A))
    satisfying naturality condition (commutativity diagram).

    In GFSO: validator checks if real implementation state F(A) matches
    ideal specification state G(A), returning distribution over possible
    interpretations/corrections.

    Naturality condition (Definition 2.3):
        η_B ∘_K F(f) ≈ G(f) ∘_K η_A  (within ε tolerance)

    Meaning: "validate-then-execute" ≈ "execute-then-validate"

    Implementations:
        - gfso_agent: LLMValidator (critic agent with confidence scores)
        - Deterministic: Simple predicate checks
        - Probabilistic: Statistical tests with uncertainty

    Abstract Methods:
        validate: Apply transformation η_A
        get_epsilon: Local error bound for this validator
    """

    @abstractmethod
    def validate(self, real_state: State) -> Distribution[State]:
        """
        Apply natural transformation component η_A: F(A) → D(G(A)).

        Takes actual implementation output and returns distribution over
        ideal specification states.

        Args:
            real_state: Actual state from implementation functor F(A)

        Returns:
            Distribution over ideal states in G(A)

        Examples:
            - Deterministic pass: {real_state: 1.0}
            - Deterministic fail: {error_state: 1.0}
            - Probabilistic: {ideal_state: 0.8, error_state: 0.2}
            - LLM critic: {corrected_state: confidence, ...}

        Note:
            Returned distribution must satisfy probability axioms:
            - All probabilities ≥ 0
            - Sum of probabilities = 1.0
        """
        pass

    @abstractmethod
    def get_epsilon(self) -> float:
        """
        Local error bound ε for this validator.

        Corresponds to d_Kl(F(f), G(f)) ≤ ε in Definition 2.3.

        This bound represents maximum tolerable deviation between
        implementation and specification for this specific check.

        Returns:
            Non-negative error tolerance

        Note:
            Used in Theorem 3.1 linear bound:
            Total error ≤ Σ εᵢ + (n-1)δ_F

            For LLM validators: this might be empirically measured
            from calibration data or set based on task criticality.
        """
        pass

    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"{self.__class__.__name__}(epsilon={self.get_epsilon():.4f})"
