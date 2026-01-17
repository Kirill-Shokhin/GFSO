"""
GFSO Execution Engine v1.0 (Paper v7.0)

Executes task sequences with:
- Pre-execution stability analysis (L·γ ≤ 1)
- Validator application after each morphism
- Error bound computation (exponential/bounded/linear)
- Retry logic for failed validations

Key changes from v0.1:
- Validators are APPLIED (not just checked)
- Stability criterion L·γ ≤ 1
- Exponential bounds O(L^n) → bounded if L·γ < 1
"""

from dataclasses import dataclass, field
from typing import Optional, Sequence
from functools import reduce

from gfso.core.kleisli import State, Distribution, compose_kleisli
from gfso.core.metric import StateMetric, wasserstein_1_discrete
from gfso.core.morphism import LipschitzMorphism
from gfso.core.graph import TaskDAG
from gfso.contract.validator import Validator
from gfso.contract.validators import IdentityValidator

from .stability import StabilityAnalysis, check_stability, check_sparse_stability
from .bounds import validated_bound, exponential_bound

__all__ = ['ExecutionResult', 'ValidationEvent', 'GFSOEngine']


@dataclass
class ValidationEvent:
    """Record of a single validation application."""
    step: int
    task_id: str
    pre_validation_dist: Distribution
    post_validation_dist: Distribution
    retries: int = 0


@dataclass
class ExecutionResult:
    """
    Result of executing task sequence with validation.

    Extended from v0.1 with stability analysis and validation events.
    """

    success: bool
    """Whether execution completed successfully"""

    final_distribution: Distribution
    """Final output distribution (after all validations)"""

    spec_distribution: Distribution
    """Expected output from specification path"""

    actual_error: float
    """Measured W₁(final, spec)"""

    theoretical_bound: float
    """Error bound from Corollary 5.3"""

    stability: StabilityAnalysis
    """Stability analysis result"""

    path_length: int
    """Number of tasks executed"""

    validation_events: list[ValidationEvent] = field(default_factory=list)
    """Record of all validation applications"""

    total_retries: int = 0
    """Total number of retries across all validations"""

    trace: list[tuple[str, Distribution]] = field(default_factory=list)
    """Execution trace: [(task_id, distribution), ...]"""

    failed_at: Optional[str] = None
    """Task ID where execution failed (if any)"""

    # Legacy fields for backwards compatibility
    guaranteed_bound: float = 0.0
    """Alias for theoretical_bound (v0.1 compatibility)"""

    composition_discrepancy: float = 0.0
    """δ_F value used"""

    local_errors: list[float] = field(default_factory=list)
    """Legacy: local ε values (now derived from γ)"""

    def __post_init__(self):
        self.guaranteed_bound = self.theoretical_bound

    def __repr__(self) -> str:
        status = "SUCCESS" if self.success else f"FAILED at {self.failed_at}"
        return (
            f"ExecutionResult({status}, "
            f"error={self.actual_error:.4f}, "
            f"bound={self.theoretical_bound:.4f}, "
            f"regime={self.stability.regime})"
        )


class GFSOEngine:
    """
    Execution engine with stability-aware validation (v1.0).

    Features:
    - Pre-execution stability analysis
    - Validator application after each morphism
    - Error bound computation
    - Retry logic for validation failures

    Usage:
        engine = GFSOEngine(dag, state_metric)
        stability = engine.analyze_stability(['task1', 'task2'])
        result = engine.execute(['task1', 'task2'], initial_state)
    """

    def __init__(
        self,
        dag: TaskDAG,
        state_metric: StateMetric,
        delta_F: float = 0.0,
    ):
        """
        Initialize GFSO engine.

        Args:
            dag: Task dependency graph
            state_metric: Distance function on state space
            delta_F: Composition discrepancy (functor laxity)
        """
        self.dag = dag
        self.state_metric = state_metric
        self._delta_F = delta_F

    def analyze_stability(
        self,
        task_sequence: list[str],
        validation_interval: int = 1,
    ) -> StabilityAnalysis:
        """
        Pre-execution stability check.

        Analyzes whether the task sequence with validators is stable.

        Args:
            task_sequence: Ordered list of task IDs
            validation_interval: k for sparse validation (default 1)

        Returns:
            StabilityAnalysis with regime classification
        """
        if not task_sequence:
            return StabilityAnalysis(
                L=1.0, gamma=1.0, product=1.0,
                is_stable=True, regime="bounded",
                steady_state_bound=0.0,
            )

        # Collect morphisms and validators
        morphisms = []
        validators = []

        for task_id in task_sequence:
            task = self.dag.get_task(task_id)

            # Get Lipschitz degree
            impl = task.implementation
            if isinstance(impl, LipschitzMorphism):
                morphisms.append(impl)
            else:
                # Assume L=1 for legacy KleisliMorphism
                morphisms.append(LipschitzMorphism(impl, 1.0, task_id))

            validators.append(task.validator)

        # Use combined validator (composition)
        # For per-step, we use max L and combined γ
        combined_gamma = 1.0
        for v in validators:
            combined_gamma *= v.contraction_degree()

        # Create effective validator with combined gamma
        class _EffectiveValidator(Validator):
            def __init__(self, gamma):
                self._gamma = gamma

            def __call__(self, dist):
                return dist

            def contraction_degree(self):
                return self._gamma

        effective_validator = _EffectiveValidator(combined_gamma ** (1.0 / len(validators)))

        if validation_interval > 1:
            return check_sparse_stability(
                morphisms, effective_validator, validation_interval,
                eps0=0.0, delta_F=self._delta_F
            )
        else:
            return check_stability(
                morphisms, effective_validator,
                eps0=0.0, delta_F=self._delta_F
            )

    def execute(
        self,
        task_sequence: list[str],
        initial_state: State,
        validation_interval: int = 1,
        max_retries: int = 3,
        apply_validators: bool = True,
    ) -> ExecutionResult:
        """
        Execute task sequence with validator application.

        Steps:
        1. Check stability (L·γ ≤ 1)
        2. For each step: execute morphism, apply validator
        3. Compute error bounds
        4. Return result with stability info

        Args:
            task_sequence: Ordered list of task IDs
            initial_state: Starting state
            validation_interval: Apply validator every k steps (default 1)
            max_retries: Max retry attempts on validation failure
            apply_validators: Whether to apply validators (True) or just measure

        Returns:
            ExecutionResult with all metrics and bounds
        """
        # Handle empty sequence
        if not task_sequence:
            return ExecutionResult(
                success=True,
                final_distribution={initial_state: 1.0},
                spec_distribution={initial_state: 1.0},
                actual_error=0.0,
                theoretical_bound=0.0,
                stability=StabilityAnalysis(
                    L=1.0, gamma=1.0, product=1.0,
                    is_stable=True, regime="bounded",
                    steady_state_bound=0.0,
                ),
                path_length=0,
            )

        # Validate task sequence
        for task_id in task_sequence:
            if task_id not in self.dag:
                raise ValueError(f"Unknown task: '{task_id}'")

        # Analyze stability
        stability = self.analyze_stability(task_sequence, validation_interval)

        n = len(task_sequence)

        # Compute specification distribution
        spec_morphisms = [
            self.dag.get_task(tid).specification
            for tid in task_sequence
        ]
        composed_spec = reduce(compose_kleisli, reversed(spec_morphisms))
        spec_dist = composed_spec(initial_state)

        # Execute with validation
        current_dist = {initial_state: 1.0}
        trace = []
        validation_events = []
        total_retries = 0

        for step, task_id in enumerate(task_sequence):
            task = self.dag.get_task(task_id)

            # Step 1: Execute morphism F(f_i)
            next_dist = self._apply_morphism(current_dist, task.implementation)

            # Step 2: Apply validator (if interval matches)
            if apply_validators and (step + 1) % validation_interval == 0:
                pre_val_dist = dict(next_dist)

                # Apply validator with retry
                validated_dist, retries = self._apply_validator_with_retry(
                    next_dist, task.validator, max_retries
                )

                next_dist = validated_dist
                total_retries += retries

                validation_events.append(ValidationEvent(
                    step=step,
                    task_id=task_id,
                    pre_validation_dist=pre_val_dist,
                    post_validation_dist=validated_dist,
                    retries=retries,
                ))

            current_dist = next_dist
            trace.append((task_id, dict(current_dist)))

        # Measure actual error
        actual_error = wasserstein_1_discrete(
            current_dist, spec_dist, self.state_metric
        )

        # Compute theoretical bound
        theoretical_bound = validated_bound(
            stability.L, stability.gamma, n,
            eps0=0.0, delta_F=self._delta_F
        )

        return ExecutionResult(
            success=True,
            final_distribution=current_dist,
            spec_distribution=spec_dist,
            actual_error=actual_error,
            theoretical_bound=theoretical_bound,
            stability=stability,
            path_length=n,
            validation_events=validation_events,
            total_retries=total_retries,
            trace=trace,
            composition_discrepancy=self._delta_F,
        )

    def execute_chain(
        self,
        morphism: LipschitzMorphism,
        validator: Validator,
        initial_state: State,
        chain_length: int,
        max_retries: int = 3,
    ) -> ExecutionResult:
        """
        Execute a homogeneous chain (same morphism repeated).

        Simplified interface for experiments like fact-drift.

        Args:
            morphism: Single morphism to repeat
            validator: Validator to apply after each step
            initial_state: Starting state
            chain_length: Number of repetitions
            max_retries: Max retries per validation

        Returns:
            ExecutionResult
        """
        # Stability analysis
        L = morphism.lipschitz_degree
        gamma = validator.contraction_degree()
        product = L * gamma

        if product < 1.0 - 1e-9:
            regime = "bounded"
        elif product < 1.0 + 1e-9:
            regime = "linear"
        else:
            regime = "divergent"

        stability = StabilityAnalysis(
            L=L, gamma=gamma, product=product,
            is_stable=product <= 1.0 + 1e-9,
            regime=regime,
            steady_state_bound=(
                gamma * self._delta_F / (1.0 - product)
                if product < 1.0 else None
            ),
        )

        # Execute chain
        current_dist = {initial_state: 1.0}
        trace = []
        validation_events = []
        total_retries = 0

        for step in range(chain_length):
            # Apply morphism
            next_dist = self._apply_morphism(current_dist, morphism)

            # Apply validator
            pre_val_dist = dict(next_dist)
            validated_dist, retries = self._apply_validator_with_retry(
                next_dist, validator, max_retries
            )

            next_dist = validated_dist
            total_retries += retries

            validation_events.append(ValidationEvent(
                step=step,
                task_id=f"step_{step}",
                pre_validation_dist=pre_val_dist,
                post_validation_dist=validated_dist,
                retries=retries,
            ))

            current_dist = next_dist
            trace.append((f"step_{step}", dict(current_dist)))

        # Theoretical bound
        theoretical_bound = validated_bound(
            L, gamma, chain_length,
            eps0=0.0, delta_F=self._delta_F
        )

        return ExecutionResult(
            success=True,
            final_distribution=current_dist,
            spec_distribution={initial_state: 1.0},  # Ideal: no drift
            actual_error=0.0,  # Not measured without spec
            theoretical_bound=theoretical_bound,
            stability=stability,
            path_length=chain_length,
            validation_events=validation_events,
            total_retries=total_retries,
            trace=trace,
        )

    def _apply_morphism(
        self,
        dist: Distribution,
        morphism,
    ) -> Distribution:
        """Apply morphism to distribution (Kleisli extension)."""
        result = {}

        for state, prob in dist.items():
            step_dist = morphism(state)
            for next_state, next_prob in step_dist.items():
                result[next_state] = result.get(next_state, 0.0) + prob * next_prob

        return result

    def _apply_validator_with_retry(
        self,
        dist: Distribution,
        validator: Validator,
        max_retries: int,
    ) -> tuple[Distribution, int]:
        """Apply validator with retry logic."""
        # Validators in v1.0 are deterministic transforms
        # Retry is handled internally by RetryValidator if needed
        validated = validator(dist)
        return validated, 0
