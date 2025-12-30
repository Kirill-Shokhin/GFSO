"""
Simple GFSO Demo - Core Primitives

Demonstrates basic GFSO building blocks:
- Kleisli morphisms (stochastic functions)
- Chapman-Kolmogorov composition
- Wasserstein distance measurement
- Error bound formula computation

Note: This is a POC demonstrating mathematical primitives.
Full validator logic with retry/re-grounding not yet implemented.
"""

from gfso import (
    Distribution,
    TaskDAG,
    GFSOEngine,
    Validator,
)


# ============================================================================
# Define simple state space: integers
# ============================================================================

def simple_state_metric(s1: int, s2: int) -> float:
    """Distance between integers."""
    return abs(s1 - s2)


# ============================================================================
# Define simple tasks with Implementation and Specification
# ============================================================================

def add_one_impl(state: int) -> Distribution[int]:
    """
    Implementation: Add 1 with small noise.

    Returns distribution: {state+1: 0.9, state+2: 0.1}
    """
    return {
        state + 1: 0.9,
        state + 2: 0.1,
    }


def add_one_spec(state: int) -> Distribution[int]:
    """
    Specification: Perfect add 1.

    Returns deterministic: {state+1: 1.0}
    """
    return {state + 1: 1.0}


def add_three_impl(state: int) -> Distribution[int]:
    """
    Implementation: Add 3 with noise.

    Returns distribution: {state+3: 0.85, state+4: 0.15}
    """
    return {
        state + 3: 0.85,
        state + 4: 0.15,
    }


def add_three_spec(state: int) -> Distribution[int]:
    """
    Specification: Perfect add 3.

    Returns deterministic: {state+3: 1.0}
    """
    return {state + 3: 1.0}


# ============================================================================
# Define simple validators
# ============================================================================

class SimpleValidator(Validator):
    """
    Simple deterministic validator.

    Always passes state through (identity natural transformation).
    """

    def __init__(self, epsilon: float):
        self.epsilon = epsilon

    def validate(self, real_state: int) -> Distribution[int]:
        """Pass through unchanged."""
        return {real_state: 1.0}

    def get_epsilon(self) -> float:
        """Return local error bound."""
        return self.epsilon


# ============================================================================
# Build and execute workflow
# ============================================================================

def main():
    print("=" * 70)
    print("GFSO Simple Demo")
    print("=" * 70)

    # Create DAG
    dag = TaskDAG(state_metric=simple_state_metric)

    # Add tasks
    print("\nAdding tasks...")

    dag.add_task(
        task_id="add_one",
        implementation=add_one_impl,
        specification=add_one_spec,
        validator=SimpleValidator(epsilon=0.1),
    )

    dag.add_task(
        task_id="add_three",
        implementation=add_three_impl,
        specification=add_three_spec,
        validator=SimpleValidator(epsilon=0.15),
    )

    # Add dependency: add_one -> add_three
    dag.add_dependency("add_one", "add_three")

    print(f"Created DAG: {dag}")
    print(f"Topological order: {dag.get_topological_order()}")

    # Create engine
    print("\nCreating GFSO engine...")
    engine = GFSOEngine(
        dag=dag,
        state_metric=simple_state_metric,
        delta_F=0.0,  # Assume strict functor for simplicity
    )

    # Execute
    print("\nExecuting task sequence: ['add_one', 'add_three']")
    print("Initial state: 5")
    print("\nNote: Suppressing non-expansiveness warning (integer arithmetic is trivially non-expansive)")

    result = engine.execute(
        task_sequence=["add_one", "add_three"],
        initial_state=5,
        warn_no_verification=False,  # Suppress warning (simple integer arithmetic)
    )

    # Display results
    print("\n" + "=" * 70)
    print("Results")
    print("=" * 70)

    print(f"\nSuccess: {result.success}")
    print(f"Path length: {result.path_length}")

    print(f"\nFinal distribution (implementation):")
    for state, prob in sorted(result.final_distribution.items()):
        print(f"  {state}: {prob:.3f}")

    print(f"\nExpected distribution (specification):")
    for state, prob in sorted(result.spec_distribution.items()):
        print(f"  {state}: {prob:.3f}")

    print(f"\nError Analysis:")
    print(f"  Local errors (epsilon): {result.local_errors}")
    print(f"  Composition discrepancy (delta_F): {result.composition_discrepancy:.4f}")
    print(f"  Computed bound formula: {result.guaranteed_bound:.4f}")
    print(f"  Measured Wasserstein distance: {result.actual_error:.4f}")

    print("\n" + "=" * 70)
    print("Note: This demo shows mathematical primitives (Kleisli composition,")
    print("Wasserstein metric, bound formula). Full validation logic with")
    print("retry/re-grounding is not yet implemented.")
    print("=" * 70)


if __name__ == "__main__":
    main()
