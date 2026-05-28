"""Persist and aggregate bench results. Replaces entry by task_id, recomputes summary."""
from __future__ import annotations

import json
import os


def load_results(path: str) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"results": []}


def save_result(path: str, result: dict) -> None:
    """Replace existing entry by task_id (or problem_index), recompute summary, write."""
    data = load_results(path)
    key = "task_id" if "task_id" in result else "problem_index"
    data["results"] = [r for r in data["results"] if r.get(key) != result.get(key)]
    data["results"].append(result)
    data["results"].sort(key=lambda r: str(r.get(key)))
    data["summary"] = _summarize(data["results"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _summarize(results: list[dict]) -> dict:
    n = len(results)
    if n == 0:
        return {"total_problems": 0}
    a_solved = sum(1 for r in results if r["oneshot"]["solved"])
    b_solved = sum(1 for r in results if r["gfso"]["solved"])
    return {
        "total_problems": n,
        "oneshot_solved": a_solved,
        "oneshot_solved_pct": round(100 * a_solved / n, 1),
        "gfso_solved": b_solved,
        "gfso_solved_pct": round(100 * b_solved / n, 1),
        "gfso_better": sum(1 for r in results if r["gfso"]["solved"] and not r["oneshot"]["solved"]),
        "gfso_same": sum(1 for r in results if r["gfso"]["solved"] == r["oneshot"]["solved"]),
        "gfso_worse": sum(1 for r in results if not r["gfso"]["solved"] and r["oneshot"]["solved"]),
        "oneshot_total_tokens": sum(r["oneshot"]["tokens"] for r in results),
        "gfso_total_tokens": sum(r["gfso"]["tokens"] for r in results),
    }
