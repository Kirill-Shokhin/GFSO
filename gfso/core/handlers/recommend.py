"""System LLM: recommend_neglected, suggest_decomposition, explain_pattern."""
from __future__ import annotations

from gfso.core.types import GraphContext, Recommendation, LLMProviderPort


def recommend(ctx: GraphContext, llm: LLMProviderPort | None = None) -> Recommendation:
    """Generate recommendations for a task based on graph context.

    Returns empty recommendation when LLM is unavailable (graceful degradation).
    """
    if llm is None:
        return Recommendation()

    # Build prompt from context
    parts = [f"Task: {ctx.task.spec.description}"]
    if ctx.children:
        parts.append(f"Children: {len(ctx.children)}")
    if ctx.check_results:
        failed = [r for r in ctx.check_results if not r.passed and not r.skipped]
        if failed:
            parts.append(f"Failed checks: {', '.join(r.check_name for r in failed)}")
    if ctx.parent:
        parts.append(f"Parent: {ctx.parent.spec.description}")

    prompt = "\n".join(parts)
    response = llm.complete(
        prompt=f"Analyze this task decomposition and suggest improvements:\n{prompt}",
        context="GFSO System LLM — recommend improvements for task decomposition",
    )

    suggestions = tuple(s.strip() for s in response.split("\n") if s.strip())
    return Recommendation(suggestions=suggestions)
