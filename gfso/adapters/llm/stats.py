"""What a model call COST and which stage made it — the bookkeeping every LLM verb does.

These three lived in `decompose/loop.py`, and four modules that have nothing to do with decomposition
imported them from there: the critic, the dispatcher, the LLM verb surface and the loop itself. That
is an off-diagonal element in the plainest sense — a shared concern owned by one of its consumers —
and it finally bit as a circular import the day the decomposer needed something from the critic.

Duck-typed on purpose: only the stat-collecting adapter has `tag_last`/`calls`/`stage_hint`, and a
fake or a third-party provider must stay usable without growing them.
"""
from __future__ import annotations


def _tag(llm, stage: str) -> None:
    """Label the llm's last call with its stage (duck-typed: only stat-collecting adapters have tag_last)."""
    if hasattr(llm, "tag_last"):
        llm.tag_last(stage)


def _stat_line(llm) -> str:
    """One-line cost readout of the llm's LAST call + the running total. Duck-typed on `calls`
    holding stat DICTS (the headless adapter); anything else (fakes, API adapter) → plain 'done'."""
    calls = getattr(llm, "calls", None)
    if not calls or not isinstance(calls[-1], dict):
        return "done"
    c = calls[-1]
    dicts = [x for x in calls if isinstance(x, dict)]
    total = sum((x.get("output_tokens") or 0) for x in dicts)
    retries = sum(1 for x in dicts if x.get("parse_failed"))
    # THE WHOLE CHECK, not its last sub-call. A verb that makes several calls — the checker and its
    # sufficiency readings — reported the LAST one, so a review costing 57 seconds and 0.18 dollars
    # was announced as "done in 2s · 0.0k tokens": the sub-call's numbers, under-reporting the work
    # by thirty times (measured on the human door 2026-08-22).
    secs = sum((x.get("duration_ms") or 0) for x in dicts) / 1000
    line = (f"done in {secs:.0f}s · {(c.get('output_tokens') or 0) / 1000:.1f}k tokens "
            f"· Σ {total / 1000:.1f}k tokens")
    return line + (f" · ⚠ {retries} parse-retry" if retries else "")


def _hint(llm, stage: str) -> None:
    """Tell the adapter which stage is about to run, so its live token ticks carry the stage name."""
    if hasattr(llm, "stage_hint"):
        llm.stage_hint = stage
