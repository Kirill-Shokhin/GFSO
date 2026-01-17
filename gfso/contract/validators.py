"""
Concrete Validator Implementations (Paper v7.0)

Provides standard validator types:
- IdentityValidator: No-op (γ = 1)
- ScalingValidator: Pure scaling x → γx (γ < 1)
- TruncationValidator: Rejection sampling with threshold
- ThresholdValidator: Accept/reject based on predicate
- CompositeValidator: Composition V₂∘V₁ with γ = γ₁·γ₂
"""

from typing import Callable, Optional, TypeVar
from collections import defaultdict

from .validator import Validator

__all__ = [
    'IdentityValidator',
    'ScalingValidator',
    'TruncationValidator',
    'ThresholdValidator',
    'CompositeValidator',
    'RetryValidator',
    'compose_validators',
]

State = TypeVar('State')
Distribution = dict[State, float]


class IdentityValidator(Validator):
    """
    Identity validator: V(μ) = μ (no transformation).

    γ = 1 (non-contractive).

    Use when:
    - No validation needed
    - Placeholder for optional validation
    - Testing/debugging
    """

    def __call__(self, dist: Distribution) -> Distribution:
        return dict(dist)

    def contraction_degree(self) -> float:
        return 1.0


class ScalingValidator(Validator):
    """
    Pure scaling validator: contracts distribution towards center.

    For numeric states, applies x → center + γ(x - center).

    Paper v7.0, Proposition 5.2b: Pure scaling achieves exact γ-contraction.

    Args:
        gamma: Contraction factor (0 < γ < 1)
        center: Center point for scaling (default: 0)
    """

    def __init__(self, gamma: float, center: float = 0.0):
        if not 0 < gamma <= 1:
            raise ValueError(f"gamma must be in (0, 1], got {gamma}")
        self._gamma = gamma
        self._center = center

    def __call__(self, dist: Distribution) -> Distribution:
        result = {}
        for state, prob in dist.items():
            if isinstance(state, (int, float)):
                new_state = self._center + self._gamma * (state - self._center)
                result[new_state] = result.get(new_state, 0.0) + prob
            else:
                # Non-numeric states: pass through unchanged
                result[state] = result.get(state, 0.0) + prob
        return result

    def contraction_degree(self) -> float:
        return self._gamma


class TruncationValidator(Validator):
    """
    Rejection sampling validator with threshold.

    Paper v7.0, Proposition 5.2: Rejection achieves γ ≈ threshold.

    Mechanism:
    1. For each state, check if it passes threshold predicate
    2. Passed states keep their probability (normalized)
    3. Failed states are replaced with fallback or removed

    Args:
        predicate: State → bool, True if state passes
        gamma: Declared contraction factor
        fallback: Optional fallback state for rejected samples
    """

    def __init__(
        self,
        predicate: Callable[[State], bool],
        gamma: float = 0.9,
        fallback: Optional[State] = None,
    ):
        self._predicate = predicate
        self._gamma = gamma
        self._fallback = fallback

    def __call__(self, dist: Distribution) -> Distribution:
        passed = {}
        failed_mass = 0.0

        for state, prob in dist.items():
            if self._predicate(state):
                passed[state] = prob
            else:
                failed_mass += prob

        if not passed:
            # All failed: return fallback or original
            if self._fallback is not None:
                return {self._fallback: 1.0}
            return dict(dist)

        # Redistribute failed mass
        if self._fallback is not None and failed_mass > 0:
            passed[self._fallback] = passed.get(self._fallback, 0.0) + failed_mass
        else:
            # Normalize passed states
            total = sum(passed.values())
            if total > 0:
                passed = {s: p / total for s, p in passed.items()}

        return passed

    def contraction_degree(self) -> float:
        return self._gamma


class ThresholdValidator(Validator):
    """
    Threshold-based validator for numeric states.

    Clamps values to [min_val, max_val] range.

    Contraction depends on typical distribution spread relative to bounds.

    Args:
        min_val: Minimum allowed value (None = no lower bound)
        max_val: Maximum allowed value (None = no upper bound)
        gamma: Declared contraction factor
    """

    def __init__(
        self,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
        gamma: float = 0.95,
    ):
        self._min = min_val
        self._max = max_val
        self._gamma = gamma

    def __call__(self, dist: Distribution) -> Distribution:
        result = defaultdict(float)

        for state, prob in dist.items():
            if isinstance(state, (int, float)):
                clamped = state
                if self._min is not None:
                    clamped = max(self._min, clamped)
                if self._max is not None:
                    clamped = min(self._max, clamped)
                result[clamped] += prob
            else:
                result[state] += prob

        return dict(result)

    def contraction_degree(self) -> float:
        return self._gamma


class CompositeValidator(Validator):
    """
    Composition of validators: V = V₂ ∘ V₁.

    Paper v7.0, Lemma 5.7: γ(V₂∘V₁) = γ₁ · γ₂

    Composing two contractive validators gives stronger contraction.

    Args:
        v1: First validator (applied first)
        v2: Second validator (applied second)
    """

    def __init__(self, v1: Validator, v2: Validator):
        self._v1 = v1
        self._v2 = v2
        self._gamma = v1.contraction_degree() * v2.contraction_degree()

    def __call__(self, dist: Distribution) -> Distribution:
        intermediate = self._v1(dist)
        return self._v2(intermediate)

    def contraction_degree(self) -> float:
        return self._gamma

    @classmethod
    def chain(cls, *validators: Validator) -> "CompositeValidator":
        """Compose multiple validators: V_n ∘ ... ∘ V_1."""
        if len(validators) < 2:
            raise ValueError("Need at least 2 validators to compose")

        result = cls(validators[0], validators[1])
        for v in validators[2:]:
            result = cls(result, v)
        return result


class RetryValidator(Validator):
    """
    Validator with retry logic for rejection sampling.

    When state fails predicate, calls retry_fn to generate new candidate.
    Repeats up to max_retries times.

    Paper v7.0, Section 5.3: Retry mechanism for LLM validators.

    Args:
        predicate: State → bool, True if state passes
        retry_fn: State → State, generates new candidate on failure
        gamma: Declared contraction factor
        max_retries: Maximum retry attempts
    """

    def __init__(
        self,
        predicate: Callable[[State], bool],
        retry_fn: Callable[[State], State],
        gamma: float = 0.85,
        max_retries: int = 3,
    ):
        self._predicate = predicate
        self._retry_fn = retry_fn
        self._gamma = gamma
        self._max_retries = max_retries

    def __call__(self, dist: Distribution) -> Distribution:
        result = {}

        for state, prob in dist.items():
            validated_state = self._validate_with_retry(state)
            result[validated_state] = result.get(validated_state, 0.0) + prob

        return result

    def _validate_with_retry(self, state: State) -> State:
        """Validate state with retry on failure."""
        current = state

        for _ in range(self._max_retries + 1):
            if self._predicate(current):
                return current
            current = self._retry_fn(current)

        # Return best effort after max retries
        return current

    def contraction_degree(self) -> float:
        return self._gamma


def compose_validators(*validators: Validator) -> Validator:
    """
    Convenience function to compose multiple validators.

    Args:
        *validators: Validators to compose (applied left-to-right)

    Returns:
        CompositeValidator if multiple, single validator if one, IdentityValidator if none
    """
    if len(validators) == 0:
        return IdentityValidator()
    if len(validators) == 1:
        return validators[0]
    return CompositeValidator.chain(*validators)
