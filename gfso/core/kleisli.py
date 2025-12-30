"""
Kleisli Category of the Distribution Monad (Definition 1.1, 1.2)

Implements the mathematical foundation from docs/mathematics.md:
- Distribution monad D on measurable spaces
- Kleisli category Kl(D) with Chapman-Kolmogorov composition
- Identity morphism (Dirac delta)

Note: This implementation uses discrete distributions (dict[State, float])
for simplicity. Extension to continuous distributions requires measure theory.
"""

from typing import TypeVar, Protocol, Callable
from collections import defaultdict

__all__ = [
    'State',
    'Distribution',
    'KleisliMorphism',
    'compose_kleisli',
    'identity_kleisli',
    'dirac_delta',
]

# Type variables
State = TypeVar('State')

# Definition 1.1: Distribution Monad
# For discrete case: D(X) = probability distributions over X
Distribution = dict[State, float]


class KleisliMorphism(Protocol):
    """
    Morphism in Kleisli category Kl(D) from Definition 1.2.

    A Kleisli morphism f: A → D(B) maps a state in A to a probability
    distribution over states in B.

    In GFSO: represents stochastic agents/processes/transitions.
    """

    def __call__(self, state: State) -> Distribution[State]:
        """
        Apply morphism to state.

        Args:
            state: Input state from domain A

        Returns:
            Probability distribution over codomain B
            (sum of probabilities should equal 1.0)
        """
        ...


def dirac_delta(state: State) -> Distribution[State]:
    """
    Dirac delta distribution (Definition 1.1 - unit of monad).

    Maps state to deterministic distribution concentrated at that state.
    η_X: X → D(X), η(x) = δ_x

    Args:
        state: Point in state space

    Returns:
        Distribution {state: 1.0}
    """
    return {state: 1.0}


def identity_kleisli(state: State) -> Distribution[State]:
    """
    Identity morphism in Kleisli category.

    id_A: A → D(A)
    id_A = η_A (the unit of the monad)

    This is just an alias for dirac_delta for clarity.
    """
    return dirac_delta(state)


def compose_kleisli(
    g: KleisliMorphism,
    f: KleisliMorphism
) -> KleisliMorphism:
    """
    Chapman-Kolmogorov composition in Kleisli category (Definition 1.2).

    For morphisms f: A → D(B) and g: B → D(C), their composition is:
    (g ∘_K f)(a) = ∫_B g(b) df(a)(b)

    In discrete case:
    (g ∘_K f)(a) = Σ_b P(b|a) · g(b)

    where P(b|a) is the probability of b given a under f.

    Args:
        g: Second morphism B → D(C)
        f: First morphism A → D(B)

    Returns:
        Composed morphism A → D(C)

    Note:
        This implements the Kleisli extension (bind operation):
        f* : D(A) → D(B) given f: A → D(B)
        Applied to Dirac delta distributions.
    """
    def composed(state: State) -> Distribution[State]:
        result: dict = defaultdict(float)

        # Step 1: Apply f to get distribution over intermediate states
        f_dist = f(state)

        # Step 2: For each intermediate state b with probability p_b
        for intermediate_state, prob_intermediate in f_dist.items():
            if prob_intermediate < 1e-10:
                continue

            # Step 3: Apply g to intermediate state
            g_dist = g(intermediate_state)

            # Step 4: Accumulate probabilities (Chapman-Kolmogorov)
            # P(c|a) = Σ_b P(c|b) · P(b|a)
            for final_state, prob_final in g_dist.items():
                result[final_state] += prob_intermediate * prob_final

        return dict(result)

    return composed


def normalize_distribution(dist: Distribution[State]) -> Distribution[State]:
    """
    Normalize distribution to sum to 1.0.

    Utility function for ensuring probability axioms.

    Args:
        dist: Unnormalized distribution

    Returns:
        Normalized distribution

    Raises:
        ValueError: If total probability is zero
    """
    total = sum(dist.values())

    if total < 1e-10:
        raise ValueError("Cannot normalize distribution with zero total probability")

    return {state: prob / total for state, prob in dist.items()}


def is_valid_distribution(
    dist: Distribution[State],
    tolerance: float = 1e-6
) -> bool:
    """
    Check if distribution satisfies probability axioms.

    Verifies:
    1. All probabilities are non-negative
    2. Sum of probabilities equals 1.0 (within tolerance)

    Args:
        dist: Distribution to validate
        tolerance: Numerical tolerance for sum check

    Returns:
        True if valid distribution
    """
    # Check non-negativity
    if any(p < -tolerance for p in dist.values()):
        return False

    # Check normalization
    total = sum(dist.values())
    return abs(total - 1.0) < tolerance
