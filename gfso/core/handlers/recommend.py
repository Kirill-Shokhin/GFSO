"""System LLM: recommend_neglected, suggest_decomposition, explain_pattern."""
from __future__ import annotations

from gfso.core.types import GraphContext, Recommendation, LLMProviderPort


# §7.3: Solver (deduction) is deterministic — its findings are the failed CHECKs,
# NOT free-form LLM suggestions. Kept separate so the UI can render solver findings
# as hard warnings and LLM items as soft suggestions.

# CHECK → FM severity (a failed deductive check is always a hard finding).
def solver_findings(ctx: GraphContext) -> list[dict]:
    """Deterministic Solver output: the failed (non-skipped) CHECK results (§7.3)."""
    findings = []
    for r in ctx.check_results:
        if not r.passed and not r.skipped:
            findings.append({
                "kind": "solver",
                "check": r.check_name,
                "text": f"{r.check_name}: {r.details}" if r.details else r.check_name,
                "severity": "high",
            })
    return findings


RECOMMEND_SYSTEM = (
    "You are a concise project oversight assistant. "
    "Output EXACTLY 2-3 short actionable items (one line each). "
    "No preamble, no numbering, no explanations. Just the actions."
)


def recommend(ctx: GraphContext, llm: LLMProviderPort | None = None) -> Recommendation:
    """Generate 2-3 concise actionable recommendations for a task."""
    if llm is None:
        return Recommendation()

    parts = [f"Task: {ctx.task.spec.description} [{ctx.task.state.name}]"]

    if ctx.task.spec.criteria:
        parts.append("Criteria: " + ", ".join(c.name for c in ctx.task.spec.criteria))
    if ctx.task.spec.neglected:
        parts.append("Explicitly neglected: " + ", ".join(n.item for n in ctx.task.spec.neglected))

    if ctx.children:
        child_summary = ", ".join(
            f"{c.spec.description[:20]}({c.state.name})" for c in ctx.children
        )
        parts.append(f"Subtasks: {child_summary}")

    if ctx.check_results:
        failed = [r for r in ctx.check_results if not r.passed and not r.skipped]
        if failed:
            parts.append("FAILED checks: " + ", ".join(
                f"{r.check_name}: {r.details}" for r in failed
            ))

    if ctx.parent:
        parts.append(f"Parent goal: {ctx.parent.spec.description}")

    prompt = "\n".join(parts)
    response = llm.complete(prompt=prompt, context=RECOMMEND_SYSTEM)

    # Parse: strip bullet markers, take max 3 non-empty lines
    lines = []
    for line in response.split("\n"):
        clean = line.strip().lstrip("-•*·123456789.)")
        clean = clean.strip()
        if clean and len(lines) < 3:
            lines.append(clean)

    return Recommendation(suggestions=tuple(lines))


SUGGEST_CRITERIA_SYSTEM = (
    "You are a project specification assistant. "
    "Given a task description, suggest 2-5 concrete acceptance criteria. "
    "Output ONLY lines in format: name | description\n"
    "Where name is a short snake_case identifier and description is one sentence. "
    "No preamble, no numbering, no other text."
)


def suggest_criteria(description: str, llm: LLMProviderPort | None = None) -> list[tuple[str, str]]:
    """Suggest criteria for a task description. Returns [(name, description), ...]."""
    if llm is None:
        return []

    response = llm.complete(prompt=description, context=SUGGEST_CRITERIA_SYSTEM)

    results = []
    for line in response.split("\n"):
        line = line.strip().lstrip("-•*·123456789.)")
        if "|" in line:
            parts = line.split("|", 1)
            name = parts[0].strip().replace(" ", "_").lower()
            desc = parts[1].strip()
            if name and desc:
                results.append((name, desc))
    return results[:5]
