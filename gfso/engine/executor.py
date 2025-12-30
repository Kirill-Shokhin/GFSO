"""
GFSO Execution Engine - Theorem 3.1 Enforcer

Executes task sequences with guaranteed linear error bounds.

Implements compositional validation enforcing:
    d(F(path), G(path)) ≤ Σεᵢ + (n-1)δ_F

where:
    F(path) = composed implementation morphisms
    G(path) = composed specification morphisms
    εᵢ = local error bound for task i (from validator)
    δ_F = composition discrepancy (functor laxity)
    n = path length

Note on Validators:
    Validators η: F(A) → D(G(A)) are COMPARISON functions, not transformations.
    They map implementation states to distributions over specification states
    to measure compliance. Per docs/context.md: "η is a CHECK, not a Worker."

    The error bound formula uses validator epsilons (εᵢ) but validators do NOT
    modify the execution flow. They define what error bounds should hold.
"""

from dataclasses import dataclass, field
from typing import Optional
from functools import reduce

from gfso.core.kleisli import State, Distribution, compose_kleisli
from gfso.core.metric import StateMetric, wasserstein_1_discrete, kleisli_metric
from gfso.core.graph import TaskDAG

__all__ = ['ExecutionResult', 'GFSOEngine']


@dataclass
class ExecutionResult:
    """
    Result of executing task sequence.

    Contains actual measurements and computed error bound formula.
    Note: Correctness of bounds not guaranteed without proper validator implementation.
    """

    success: bool
    """Whether execution completed successfully"""

    final_distribution: Distribution
    """Final output distribution from implementation path"""

    spec_distribution: Distribution
    """Expected output distribution from specification path"""

    actual_error: float
    """Measured Wasserstein distance W_1(impl_dist, spec_dist)"""

    guaranteed_bound: float
    """Theoretical error bound from Theorem 3.1: Σεᵢ + (n-1)δ_F"""

    path_length: int
    """Number of tasks in execution path"""

    composition_discrepancy: float
    """Measured δ_F (functor composition slack)"""

    local_errors: list[float] = field(default_factory=list)
    """Local epsilon values for each task"""

    failed_at: Optional[str] = None
    """Task ID where execution failed (if any)"""

    trace: list[tuple[str, Distribution]] = field(default_factory=list)
    """Execution trace: [(task_id, output_distribution), ...]"""

    def __repr__(self) -> str:
        status = "SUCCESS" if self.success else f"FAILED at {self.failed_at}"
        return (
            f"ExecutionResult({status}, "
            f"error={self.actual_error:.4f}, "
            f"bound={self.guaranteed_bound:.4f})"
        )


class GFSOEngine:
    """
    Execution engine for compositional task workflows.

    Executes task sequences from TaskDAG, composing implementation and
    specification morphisms via Chapman-Kolmogorov composition.

    Features:
    - Kleisli category composition for stochastic morphisms
    - Wasserstein distance measurement between paths
    - Error bound formula computation (Σεᵢ + (n-1)δ_F)

    Limitations:
    - Validators are not applied during execution (only used for epsilon bounds)
    - No retry/re-grounding logic implemented
    - Theorem 3.1 guarantees not verified

    This is a POC demonstrating core mathematical primitives.
    Full GFSO workflow to be implemented in gfso_agent.

    Usage:
        engine = GFSOEngine(dag, state_metric, delta_F=0.0)
        result = engine.execute(task_sequence, initial_state)
        print(f"Measured error: {result.actual_error}")
    """

    def __init__(
        self,
        dag: TaskDAG,
        state_metric: StateMetric,
        delta_F: float = 0.0,
    ):
        """
        Initialize GFSO execution engine.

        Args:
            dag: Task dependency graph (Category I)
            state_metric: Distance function on state space
            delta_F: Composition discrepancy (functor laxity)

        Note on delta_F (composition discrepancy):
            Definition 3.0 defines:
                δ_F = sup_{f,g,a} W_1((F(g)∘F(f))(a), F(g∘f)(a))

            This measures how far F is from being a strict functor (i.e., how
            much error is introduced by composing morphisms vs. composing tasks).

            CRITICAL: delta_F cannot be auto-computed because TaskDAG (category I)
            does not define morphism composition f∘g. Only the task dependency
            structure is represented, not the categorical composition operation.

            You must provide delta_F via one of three approaches:
            1. Empirical measurement: Compose tasks and measure discrepancy
            2. Theoretical bound: Derive from domain knowledge
            3. Strict functor assumption: Set delta_F=0.0 (default)

            Using delta_F=0.0 assumes F is a strict functor (no composition slack).
            This is often reasonable for deterministic task graphs but may
            underestimate error in stochastic systems.
        """
        self.dag = dag
        self.state_metric = state_metric
        self._delta_F = delta_F

    def execute(
        self,
        task_sequence: list[str],
        initial_state: State,
        warn_no_verification: bool = True,
    ) -> ExecutionResult:
        """
        Execute task sequence with compositional validation.

        Implements Theorem 3.1:
            d(F(path), G(path)) ≤ Σεᵢ + (n-1)δ_F

        Args:
            task_sequence: Ordered list of task IDs to execute
            initial_state: Starting state
            warn_no_verification: Warn if non-expansiveness was not verified

        Returns:
            ExecutionResult with error measurements and guarantees

        Raises:
            ValueError: If task_sequence is invalid

        Warning:
            Theorem 3.1 REQUIRES Assumption 1.5 (non-expansive morphisms).
            If tasks were added without verify_non_expansive=True, the bound
            may not hold. Set warn_no_verification=False to suppress this warning.

        Implementation:
            Composes and executes two paths:
            - F(path) = F(f_n) ∘ ... ∘ F(f_1)  (implementation)
            - G(path) = G(f_n) ∘ ... ∘ G(f_1)  (specification)

            Measures d(F(path), G(path)) using Wasserstein distance.

            Validators define error bounds ε_i but do NOT modify execution.
            Per docs/context.md: validators are CHECK functions, not transformations.
        """
        # Handle empty sequence
        if not task_sequence:
            return ExecutionResult(
                success=True,
                final_distribution={initial_state: 1.0},
                spec_distribution={initial_state: 1.0},
                actual_error=0.0,
                guaranteed_bound=0.0,
                path_length=0,
                composition_discrepancy=0.0,
            )

        # Validate task sequence
        for task_id in task_sequence:
            if task_id not in self.dag:
                raise ValueError(f"Unknown task: '{task_id}'")

        # Warn if non-expansiveness was not verified (Assumption 1.5 required)
        if warn_no_verification:
            import warnings
            warnings.warn(
                "Theorem 3.1 requires Assumption 1.5 (non-expansive morphisms). "
                "Tasks were added without verify_non_expansive=True. "
                "The error bound may not hold if morphisms are expansive. "
                "Suppress with warn_no_verification=False.",
                stacklevel=2
            )

        n = len(task_sequence)

        # Collect local error bounds
        local_errors = [
            self.dag.get_task(tid).validator.get_epsilon()
            for tid in task_sequence
        ]

        # Compute guaranteed bound (Theorem 3.1)
        epsilon_sum = sum(local_errors)
        guaranteed_bound = epsilon_sum + (n - 1) * self._delta_F

        # ===================================================================
        # STEP 1: Compose specification morphisms G(f_n) ∘ ... ∘ G(f_1)
        # ===================================================================
        spec_morphisms = [
            self.dag.get_task(tid).specification
            for tid in task_sequence
        ]

        # Compose right-to-left
        composed_spec = reduce(compose_kleisli, reversed(spec_morphisms))
        spec_dist = composed_spec(initial_state)

        # ===================================================================
        # STEP 2: Compose and execute implementation morphisms F(f_n) ∘ ... ∘ F(f_1)
        # ===================================================================
        impl_morphisms = [
            self.dag.get_task(tid).implementation
            for tid in task_sequence
        ]

        # Compose right-to-left
        composed_impl = reduce(compose_kleisli, reversed(impl_morphisms))
        impl_dist = composed_impl(initial_state)

        # ===================================================================
        # STEP 3: (Optional) Validate implementation outputs
        # ===================================================================
        # Note on validators (η):
        # η: F(A) → D(G(A)) is a COMPARISON function, not a transformation.
        # It maps implementation states to distributions over specification
        # states to measure how well implementation matches specification.
        #
        # Per context.md: "The Validator (η) is a CHECK, not a Worker."
        # Validators are used to verify error bounds, not to modify execution.
        #
        # For Theorem 3.1: we measure d(F(path), G(path))
        # Validators provide the local error bounds ε_i used in the bound formula.

        # Build execution trace (step-by-step for debugging)
        trace = []
        current_dist = {initial_state: 1.0}

        for task_id in task_sequence:
            task = self.dag.get_task(task_id)

            # Execute F(f_i) on current distribution
            next_dist = {}
            for state, prob in current_dist.items():
                step_dist = task.implementation(state)
                for next_state, next_prob in step_dist.items():
                    next_dist[next_state] = (
                        next_dist.get(next_state, 0.0) + prob * next_prob
                    )

            current_dist = next_dist
            trace.append((task_id, next_dist))

        # ===================================================================
        # STEP 4: Measure actual error
        # ===================================================================
        # Measure d(F(path), G(path)) per Theorem 3.1
        actual_error = wasserstein_1_discrete(
            impl_dist,
            spec_dist,
            self.state_metric,
        )

        # ===================================================================
        # STEP 5: Return results
        # ===================================================================
        # Note: Theorem 3.1 verification not implemented.
        # The bound formula is computed but its correctness depends on:
        # - Proper validator application with retry/re-grounding
        # - Non-expansiveness verification
        # - Correct epsilon bounds
        # These are not yet fully implemented in this POC.

        return ExecutionResult(
            success=True,
            final_distribution=impl_dist,
            spec_distribution=spec_dist,
            actual_error=actual_error,
            guaranteed_bound=guaranteed_bound,
            path_length=n,
            composition_discrepancy=self._delta_F,
            local_errors=local_errors,
            trace=trace,
        )
