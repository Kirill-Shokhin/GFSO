"""
Lipschitz Morphisms for GFSO v1.0 (Paper v7.0)

Wraps Kleisli morphisms with known Lipschitz constant L.

Paper v7.0 key changes:
- Morphisms are L-Lipschitz (L > 1 allowed), not just non-expansive (L ≤ 1)
- Stability requires L·γ ≤ 1, where γ is validator contraction degree
- Error bounds are O(L^n) without validation, bounded if L·γ < 1
"""

from dataclasses import dataclass
from typing import Callable, Optional

from .kleisli import State, Distribution, KleisliMorphism, compose_kleisli

__all__ = [
    'LipschitzMorphism',
    'compose_lipschitz',
    'identity_lipschitz',
]


@dataclass
class LipschitzMorphism:
    """
    Kleisli morphism with known Lipschitz constant L.

    W₁(f(x), f(y)) ≤ L · d(x, y)

    Paper v7.0: L > 1 is allowed; stability depends on L·γ ≤ 1
    where γ is the validator's contraction degree.

    Attributes:
        morphism: Underlying Kleisli morphism A → D(B)
        lipschitz_degree: Lipschitz constant L (≥ 0)
        name: Optional name for debugging/logging
    """
    morphism: KleisliMorphism
    lipschitz_degree: float
    name: Optional[str] = None

    def __post_init__(self):
        if self.lipschitz_degree < 0:
            raise ValueError(f"Lipschitz degree must be non-negative, got {self.lipschitz_degree}")

    def __call__(self, state: State) -> Distribution[State]:
        """Apply morphism to state."""
        return self.morphism(state)

    @property
    def L(self) -> float:
        """Shorthand for lipschitz_degree."""
        return self.lipschitz_degree

    def is_non_expansive(self) -> bool:
        """Check if morphism is non-expansive (L ≤ 1)."""
        return self.lipschitz_degree <= 1.0

    def __repr__(self) -> str:
        name = f"'{self.name}'" if self.name else "anonymous"
        return f"LipschitzMorphism({name}, L={self.lipschitz_degree:.3f})"


def compose_lipschitz(
    g: LipschitzMorphism,
    f: LipschitzMorphism,
) -> LipschitzMorphism:
    """
    Compose two Lipschitz morphisms.

    For f: A → D(B) with L_f and g: B → D(C) with L_g:
    - (g ∘ f): A → D(C) has L = L_f · L_g

    This is a consequence of:
    W₁((g∘f)(x), (g∘f)(y)) ≤ L_g · W₁(f(x), f(y)) ≤ L_g · L_f · d(x,y)

    Args:
        g: Second morphism B → D(C)
        f: First morphism A → D(B)

    Returns:
        Composed morphism with L = L_f · L_g
    """
    composed = compose_kleisli(g.morphism, f.morphism)
    L_composed = f.lipschitz_degree * g.lipschitz_degree

    name = None
    if f.name and g.name:
        name = f"{g.name}∘{f.name}"

    return LipschitzMorphism(
        morphism=composed,
        lipschitz_degree=L_composed,
        name=name,
    )


def identity_lipschitz(name: Optional[str] = None) -> LipschitzMorphism:
    """
    Identity morphism with L = 1.

    The identity morphism id: A → D(A) is trivially 1-Lipschitz
    since W₁(δ_x, δ_y) = d(x, y).
    """
    from .kleisli import identity_kleisli

    return LipschitzMorphism(
        morphism=identity_kleisli,
        lipschitz_degree=1.0,
        name=name or "id",
    )


def chain_lipschitz_degree(morphisms: list[LipschitzMorphism]) -> float:
    """
    Compute Lipschitz degree of composed chain.

    For chain f_n ∘ ... ∘ f_1: L = ∏ L_i

    Args:
        morphisms: List of morphisms [f_1, f_2, ..., f_n] in execution order

    Returns:
        Product of Lipschitz degrees
    """
    if not morphisms:
        return 1.0

    L = 1.0
    for m in morphisms:
        L *= m.lipschitz_degree
    return L
