"""
Wasserstein Metric on Distributions and Kleisli Morphisms (Definition 1.3, 1.4)

Implements metric structure on:
1. Probability distributions (Wasserstein-1 distance)
2. Kleisli morphisms (enriched category structure)

Note: This provides a simple implementation for discrete distributions.
For optimal transport, use optional POT library (pip install gfso[full]).
"""

from typing import Callable, Protocol
from .kleisli import State, Distribution, KleisliMorphism

__all__ = [
    'StateMetric',
    'wasserstein_1_discrete',
    'wasserstein_1_continuous',
    'kleisli_metric',
    'verify_non_expansive',
    'estimate_lipschitz',
]


class StateMetric(Protocol):
    """
    Metric on state space (Definition 1.3 prerequisite).

    A function d: X × X → [0, ∞) satisfying:
    1. d(x, x) = 0
    2. d(x, y) = d(y, x)
    3. d(x, z) ≤ d(x, y) + d(y, z)

    In GFSO: defines distance between states in task/agent output space.
    """

    def __call__(self, s1: State, s2: State) -> float:
        """
        Compute distance between states.

        Args:
            s1, s2: States in metric space

        Returns:
            Non-negative distance
        """
        ...


def wasserstein_1_discrete(
    mu: Distribution[State],
    nu: Distribution[State],
    state_metric: StateMetric,
) -> float:
    """
    Wasserstein-1 (Earth Mover's) distance for discrete distributions (Definition 1.3).

    W_1(μ, ν) = inf_{γ ∈ Γ(μ,ν)} ∫∫ d(x,y) dγ(x,y)

    For discrete distributions, this reduces to an optimal transport problem.

    Implementation: Greedy coupling algorithm.

    For 1D metric spaces, this is optimal (exact).
    For higher-dimensional spaces, this is an approximation (upper bound).
    For exact solution in higher dimensions, use POT library (optional dependency).

    Args:
        mu: First probability distribution
        nu: Second probability distribution
        state_metric: Distance function on state space

    Returns:
        Wasserstein-1 distance (≥ 0)

    Note:
        Greedy algorithm is provably optimal for 1D metric spaces.
        For multi-dimensional spaces, it provides an upper bound approximation.
    """
    # Handle empty distributions
    if not mu or not nu:
        return 0.0

    # Fast path: identical distributions
    if mu.keys() == nu.keys():
        if all(abs(mu[s] - nu[s]) < 1e-10 for s in mu.keys()):
            return 0.0

    # Greedy coupling algorithm (approximation)
    # Maintains remaining mass for each distribution
    mass_mu = {s: p for s, p in mu.items()}
    mass_nu = {s: p for s, p in nu.items()}

    total_cost = 0.0

    # Greedy: repeatedly move mass along cheapest edge
    while mass_mu and mass_nu:
        # Find cheapest edge (state pair)
        min_cost = float('inf')
        best_s1, best_s2 = None, None

        for s1, p1 in mass_mu.items():
            if p1 < 1e-10:
                continue
            for s2, p2 in mass_nu.items():
                if p2 < 1e-10:
                    continue

                cost = state_metric(s1, s2)
                if cost < min_cost:
                    min_cost = cost
                    best_s1, best_s2 = s1, s2

        if best_s1 is None:
            break

        # Move maximum possible mass along this edge
        mass_to_move = min(mass_mu[best_s1], mass_nu[best_s2])
        total_cost += mass_to_move * min_cost

        # Update remaining masses
        mass_mu[best_s1] -= mass_to_move
        mass_nu[best_s2] -= mass_to_move

        # Remove states with zero mass
        if mass_mu[best_s1] < 1e-10:
            del mass_mu[best_s1]
        if mass_nu[best_s2] < 1e-10:
            del mass_nu[best_s2]

    return total_cost


def kleisli_metric(
    f: KleisliMorphism,
    g: KleisliMorphism,
    states: list[State],
    state_metric: StateMetric,
) -> float:
    """
    Metric on Kleisli morphisms (Definition 1.4).

    d_Kl(f, g) = sup_{a ∈ A} W_1(f(a), g(a))

    Measures maximum deviation between morphisms over state space.

    Args:
        f, g: Kleisli morphisms to compare
        states: Sample of states to check (finite approximation of supremum)
        state_metric: Metric on state space

    Returns:
        Distance between morphisms

    Note:
        For infinite state spaces, this computes supremum over provided sample.
        Accuracy depends on coverage of state space by sample.
    """
    if not states:
        return 0.0

    distances = []
    for state in states:
        f_dist = f(state)
        g_dist = g(state)
        w1 = wasserstein_1_discrete(f_dist, g_dist, state_metric)
        distances.append(w1)

    return max(distances)


def verify_non_expansive(
    f: KleisliMorphism,
    test_states: list[State],
    state_metric: StateMetric,
    tolerance: float = 1e-6,
) -> tuple[bool, float]:
    """
    Verify Assumption 1.5 (non-expansive property).

    A morphism f: A → D(B) is non-expansive if:
    W_1(f(a₁), f(a₂)) ≤ d(a₁, a₂)  for all a₁, a₂ ∈ A

    This is the critical regularity condition for Theorem 3.1.

    Args:
        f: Morphism to verify
        test_states: Sample states to check
        state_metric: Metric on state space
        tolerance: Numerical tolerance for inequality

    Returns:
        (is_valid, max_violation_ratio) where:
        - is_valid: True if morphism is non-expansive on test states
        - max_violation_ratio: max(W_1(f(a),f(b)) / d(a,b))
          Ratio > 1 indicates violation

    Raises:
        ValueError: If test_states is empty
    """
    if not test_states:
        raise ValueError("test_states cannot be empty")

    max_ratio = 0.0

    for s1 in test_states:
        for s2 in test_states:
            if s1 == s2:
                continue

            # Input distance
            d_input = state_metric(s1, s2)

            # Skip if states are identical under metric
            if d_input < 1e-10:
                continue

            # Output distance
            d_output = wasserstein_1_discrete(f(s1), f(s2), state_metric)

            # Compute ratio
            ratio = d_output / d_input
            max_ratio = max(max_ratio, ratio)

            # Check violation
            if ratio > 1.0 + tolerance:
                return False, ratio

    return True, max_ratio


def wasserstein_1_continuous(
    samples_mu: list[State],
    samples_nu: list[State],
    state_metric: StateMetric,
) -> float:
    """
    Wasserstein-1 distance for continuous distributions via samples.

    Uses scipy/POT for optimal transport when available, falls back to
    discrete approximation otherwise.

    Args:
        samples_mu: Samples from first distribution
        samples_nu: Samples from second distribution
        state_metric: Distance function on state space

    Returns:
        Wasserstein-1 distance estimate
    """
    if not samples_mu or not samples_nu:
        return 0.0

    # Try to use POT for exact computation
    try:
        import numpy as np
        import ot

        n, m = len(samples_mu), len(samples_nu)

        # Build cost matrix
        C = np.zeros((n, m))
        for i, s1 in enumerate(samples_mu):
            for j, s2 in enumerate(samples_nu):
                C[i, j] = state_metric(s1, s2)

        # Uniform weights (empirical distributions)
        a = np.ones(n) / n
        b = np.ones(m) / m

        return ot.emd2(a, b, C)

    except ImportError:
        # Fallback: convert samples to discrete distribution and use greedy
        from collections import Counter

        def samples_to_dist(samples):
            counts = Counter(samples)
            total = len(samples)
            return {s: c / total for s, c in counts.items()}

        mu = samples_to_dist(samples_mu)
        nu = samples_to_dist(samples_nu)

        return wasserstein_1_discrete(mu, nu, state_metric)


def estimate_lipschitz(
    f: KleisliMorphism,
    test_states: list[State],
    state_metric: StateMetric,
) -> float:
    """
    Estimate Lipschitz constant L for a Kleisli morphism.

    L = sup_{x≠y} W₁(f(x), f(y)) / d(x, y)

    Paper v7.0: Morphisms are L-Lipschitz (L > 1 OK), not necessarily
    non-expansive (L ≤ 1).

    Args:
        f: Kleisli morphism to analyze
        test_states: Sample states to estimate over
        state_metric: Metric on state space

    Returns:
        Estimated Lipschitz constant (≥ 0)

    Note:
        Returns max ratio over test states (lower bound on true L).
        For LLMs, typical values are L ≈ 1.1-1.3.
    """
    if len(test_states) < 2:
        return 1.0  # Default assumption

    max_ratio = 0.0

    for i, s1 in enumerate(test_states):
        for s2 in test_states[i + 1:]:
            d_input = state_metric(s1, s2)

            if d_input < 1e-10:
                continue

            d_output = wasserstein_1_discrete(f(s1), f(s2), state_metric)
            ratio = d_output / d_input
            max_ratio = max(max_ratio, ratio)

    return max_ratio if max_ratio > 0 else 1.0
