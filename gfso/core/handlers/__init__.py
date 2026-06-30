from __future__ import annotations

from gfso.core.types import Task, CheckResult, GraphContext, Recommendation, LLMProviderPort, DepEdge
from .structural import run_structural, check_anti_mock
from .constraint import run_constraints
from .recommend import recommend as _recommend, solver_findings


def run_checks(task: Task, children: list[Task], dep_edges: list[tuple[str, str]] | None = None) -> list[CheckResult]:
    """Run all checks: structural (CHECK-1-6) + constraints (CHECK-7-8)."""
    results = run_structural(task, children, dep_edges)
    results.extend(run_constraints(task, children))
    return results


def run_all_checks(task: Task, children: list[Task], dep_edges: list[DepEdge]) -> list[CheckResult]:
    """The single L0/L1 check set (structural + constraints + anti-mock seam), over
    DepEdge objects (so glue is checked). The ONE computation both the engine's cache
    refresh and the event loop use — same result everywhere."""
    results = run_checks(task, children, [(e.from_id, e.to_id) for e in dep_edges])
    results.append(check_anti_mock(children, dep_edges))
    return results


def recommend(ctx: GraphContext, llm: LLMProviderPort | None = None) -> Recommendation:
    return _recommend(ctx, llm)
