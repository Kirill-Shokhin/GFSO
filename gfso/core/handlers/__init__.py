from __future__ import annotations

from gfso.core.types import Task, CheckResult, GraphContext, Recommendation, LLMProviderPort
from .structural import run_structural
from .constraint import run_constraints
from .recommend import recommend as _recommend


def run_checks(task: Task, children: list[Task], dep_edges: list[tuple[str, str]] | None = None) -> list[CheckResult]:
    """Run all checks: structural (CHECK-1-6) + constraints (CHECK-7-8)."""
    results = run_structural(task, children, dep_edges)
    results.extend(run_constraints(task, children))
    return results


def recommend(ctx: GraphContext, llm: LLMProviderPort | None = None) -> Recommendation:
    return _recommend(ctx, llm)
