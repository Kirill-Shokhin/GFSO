"""The CHECK battery of §13.4 — the a-priori half of correctness, run over the map alone.

Syntactic (topology, coverage, DAG, deadlines) and Semantic (formal entailment, satisfiability).
What they cannot reach is the Pragmatic level, and a check that cannot decide says `skipped`
rather than passing: a fail-open check is worse than an absent one.
"""
from __future__ import annotations

from gfso.core.types import Task, CheckResult, GraphContext, Recommendation, LLMProviderPort, DepEdge
from .structural import run_structural, check_anti_mock
from .constraint import run_constraints
from .recommend import recommend as _recommend, solver_findings


def run_checks(task: Task, children: list[Task], dep_edges: list[tuple[str, str]] | None = None,
               non_leaf_ids: set[str] | None = None) -> list[CheckResult]:
    """Run all checks: structural (CHECK-1-6) + constraints (CHECK-7-8).

    `non_leaf_ids` = the children that decompose further, which only a caller holding the graph can
    know; CHECK-6 quantifies over LEAVES (§13.4) and reads it."""
    results = run_structural(task, children, dep_edges, non_leaf_ids)
    results.extend(run_constraints(task, children))
    return results


def run_all_checks(task: Task, children: list[Task], dep_edges: list[DepEdge],
                   non_leaf_ids: set[str] | None = None) -> list[CheckResult]:
    """The single L0/L1 check set (structural + constraints + anti-mock seam), over
    DepEdge objects (so glue is checked). The ONE computation both the engine's cache
    refresh and the event loop use — same result everywhere."""
    results = run_checks(task, children, [(e.from_id, e.to_id) for e in dep_edges], non_leaf_ids)
    results.append(check_anti_mock(children, dep_edges))
    return results


def recommend(ctx: GraphContext, llm: LLMProviderPort | None = None) -> Recommendation:
    """Criteria suggestions for a node, from the graph alone or with an LLM if one is given.

    The published seam over the private implementation: callers depend on this name, not on where
    the recommendation is computed.
    """
    return _recommend(ctx, llm)
