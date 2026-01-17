"""
Task Dependency Graph - Category I (Paper v7.0)

Represents workflow as a directed acyclic graph (DAG) with:
- Objects: Tasks (with LipschitzMorphism implementations)
- Morphisms: Dependencies (edges)
- Functors: F (implementation), G (specification)
- Natural transformation: η (validators as γ-contractive maps)

Uses NetworkX for efficient graph operations.
"""

from dataclasses import dataclass, field
from typing import Optional, Union
import networkx as nx

from gfso.core.kleisli import KleisliMorphism, State
from gfso.core.metric import StateMetric, verify_non_expansive, estimate_lipschitz
from gfso.core.morphism import LipschitzMorphism
from gfso.contract.validator import Validator

__all__ = ['Task', 'TaskDAG']


@dataclass
class Task:
    """
    Object in Category I with functor images and natural transformation.

    Represents a single task/agent in the workflow with:
    - F(task): Implementation (real/stochastic behavior) - now LipschitzMorphism
    - G(task): Specification (ideal/deterministic behavior)
    - η_task: Validator (γ-contractive map)

    Paper v7.0 changes:
    - implementation can be LipschitzMorphism with known L
    - validator is γ-contractive, not ε-bounded
    """

    task_id: str
    """Unique identifier for this task"""

    implementation: Union[KleisliMorphism, LipschitzMorphism]
    """F(task): Real execution morphism with Lipschitz degree L"""

    specification: KleisliMorphism
    """G(task): Ideal execution morphism (typically deterministic)"""

    validator: Validator
    """η_task: γ-contractive validator"""

    dependencies: list[str] = field(default_factory=list)
    """Incoming edges (tasks that must execute before this one)"""

    metadata: dict = field(default_factory=dict)
    """Optional metadata for task (description, tags, etc.)"""

    def __hash__(self):
        return hash(self.task_id)

    def __eq__(self, other):
        if not isinstance(other, Task):
            return False
        return self.task_id == other.task_id

    @property
    def lipschitz_degree(self) -> float:
        """Get Lipschitz degree L of implementation."""
        if isinstance(self.implementation, LipschitzMorphism):
            return self.implementation.lipschitz_degree
        return 1.0  # Assume non-expansive for legacy morphisms

    @property
    def contraction_degree(self) -> float:
        """Get contraction degree γ of validator."""
        return self.validator.contraction_degree()

    @property
    def stability_product(self) -> float:
        """Compute L·γ for this task."""
        return self.lipschitz_degree * self.contraction_degree

    def is_stable(self) -> bool:
        """Check if task satisfies L·γ ≤ 1."""
        return self.stability_product <= 1.0 + 1e-9


class TaskDAG:
    """
    Task dependency graph - Category I from Section 2.1.

    Category structure:
    - Objects: Tasks
    - Morphisms: Dependencies (directed edges task_i → task_j)
    - Functors:
        F: I → Kl(D)  maps task → implementation morphism
        G: I → Kl(D)  maps task → specification morphism
    - Natural transformation:
        η: F ⇒ G  maps task → validator

    Invariants:
    - Graph is acyclic (DAG)
    - All task_ids are unique
    - All dependencies reference existing tasks

    Uses NetworkX DiGraph for:
    - Cycle detection
    - Topological sorting
    - Efficient graph algorithms
    """

    def __init__(self, state_metric: Optional[StateMetric] = None):
        """
        Initialize empty task DAG.

        Args:
            state_metric: Distance function on state space.
                         Required for non-expansive verification and
                         Wasserstein computation.
        """
        self.tasks: dict[str, Task] = {}
        self.graph = nx.DiGraph()
        self.state_metric = state_metric

    def add_task(
        self,
        task_id: str,
        implementation: Union[KleisliMorphism, LipschitzMorphism],
        specification: KleisliMorphism,
        validator: Validator,
        *,
        lipschitz_degree: Optional[float] = None,
        estimate_lipschitz_from_states: bool = False,
        verify_non_expansive_impl: bool = False,
        verify_non_expansive_spec: bool = False,
        test_states: Optional[list[State]] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Add task (object) to category I.

        Paper v7.0: Supports LipschitzMorphism with known L > 1.

        Args:
            task_id: Unique task identifier
            implementation: F(task) functor image (KleisliMorphism or LipschitzMorphism)
            specification: G(task) functor image
            validator: η_task (γ-contractive validator)
            lipschitz_degree: Manual L for KleisliMorphism (ignored if LipschitzMorphism)
            estimate_lipschitz_from_states: Estimate L from test_states
            verify_non_expansive_impl: Verify Assumption 1.5 for implementation (legacy)
            verify_non_expansive_spec: Verify Assumption 1.5 for specification
            test_states: States for Lipschitz estimation or verification
            metadata: Optional task metadata

        Raises:
            ValueError: If task_id already exists or verification fails
        """
        if task_id in self.tasks:
            raise ValueError(f"Task '{task_id}' already exists")

        # Handle Lipschitz estimation/wrapping
        final_impl = implementation

        if not isinstance(implementation, LipschitzMorphism):
            # Wrap KleisliMorphism in LipschitzMorphism

            if estimate_lipschitz_from_states:
                if self.state_metric is None:
                    raise ValueError("state_metric required for Lipschitz estimation")
                if not test_states:
                    raise ValueError("test_states required for Lipschitz estimation")

                estimated_L = estimate_lipschitz(
                    implementation, test_states, self.state_metric
                )
                final_impl = LipschitzMorphism(implementation, estimated_L, task_id)

            elif lipschitz_degree is not None:
                final_impl = LipschitzMorphism(implementation, lipschitz_degree, task_id)

            # else: keep as KleisliMorphism (L=1 assumed)

        # Legacy: Verify non-expansive property if requested
        if verify_non_expansive_impl or verify_non_expansive_spec:
            if self.state_metric is None:
                raise ValueError("state_metric required for non-expansive verification")
            if not test_states:
                raise ValueError("test_states required for non-expansive verification")

        if verify_non_expansive_impl:
            morphism_to_verify = (
                implementation.morphism if isinstance(implementation, LipschitzMorphism)
                else implementation
            )
            is_valid, ratio = verify_non_expansive(
                morphism_to_verify, test_states, self.state_metric
            )
            if not is_valid:
                raise ValueError(
                    f"Task '{task_id}' implementation violates Assumption 1.5 "
                    f"(non-expansive property). Max ratio: {ratio:.4f}"
                )

        if verify_non_expansive_spec:
            is_valid, ratio = verify_non_expansive(
                specification, test_states, self.state_metric
            )
            if not is_valid:
                raise ValueError(
                    f"Task '{task_id}' specification violates Assumption 1.5 "
                    f"(non-expansive property). Max ratio: {ratio:.4f}"
                )

        # Create task
        task = Task(
            task_id=task_id,
            implementation=final_impl,
            specification=specification,
            validator=validator,
            dependencies=[],
            metadata=metadata or {},
        )

        self.tasks[task_id] = task
        self.graph.add_node(task_id, task=task)

    def add_dependency(self, from_task: str, to_task: str) -> None:
        """
        Add morphism (edge) in category I.

        Creates dependency: from_task → to_task
        (to_task depends on from_task; from_task must execute first)

        Args:
            from_task: Source task (prerequisite)
            to_task: Target task (dependent)

        Raises:
            ValueError: If tasks don't exist or edge creates cycle
        """
        if from_task not in self.tasks:
            raise ValueError(f"Unknown task: '{from_task}'")
        if to_task not in self.tasks:
            raise ValueError(f"Unknown task: '{to_task}'")

        # Add edge to NetworkX graph
        self.graph.add_edge(from_task, to_task)

        # Check for cycles
        if not nx.is_directed_acyclic_graph(self.graph):
            # Rollback
            self.graph.remove_edge(from_task, to_task)
            raise ValueError(
                f"Adding dependency {from_task}→{to_task} creates cycle"
            )

        # Update task dependencies
        self.tasks[to_task].dependencies.append(from_task)

    def get_topological_order(self) -> list[str]:
        """
        Return topologically sorted task order.

        Returns tasks in execution order: dependencies before dependents.

        Returns:
            List of task_ids in topological order

        Raises:
            ValueError: If graph contains cycle (should not happen)

        Note:
            Uses NetworkX lexicographical topological sort for deterministic ordering.
        """
        try:
            return list(nx.lexicographical_topological_sort(self.graph))
        except nx.NetworkXError as e:
            raise ValueError(f"Graph is not a DAG: {e}")

    def get_task(self, task_id: str) -> Task:
        """
        Retrieve task by ID.

        Args:
            task_id: Task identifier

        Returns:
            Task object

        Raises:
            KeyError: If task doesn't exist
        """
        return self.tasks[task_id]

    def get_dependencies(self, task_id: str) -> list[str]:
        """
        Get direct dependencies (predecessors) of task.

        Args:
            task_id: Task identifier

        Returns:
            List of task IDs that this task depends on

        Raises:
            KeyError: If task doesn't exist
        """
        if task_id not in self.tasks:
            raise KeyError(f"Unknown task: '{task_id}'")
        return list(self.graph.predecessors(task_id))

    def get_dependents(self, task_id: str) -> list[str]:
        """
        Get direct dependents (successors) of task.

        Args:
            task_id: Task identifier

        Returns:
            List of task IDs that depend on this task

        Raises:
            KeyError: If task doesn't exist
        """
        if task_id not in self.tasks:
            raise KeyError(f"Unknown task: '{task_id}'")
        return list(self.graph.successors(task_id))

    def __len__(self) -> int:
        """Number of tasks in DAG."""
        return len(self.tasks)

    def __contains__(self, task_id: str) -> bool:
        """Check if task exists in DAG."""
        return task_id in self.tasks

    def __repr__(self) -> str:
        return f"TaskDAG(tasks={len(self.tasks)}, edges={self.graph.number_of_edges()})"
