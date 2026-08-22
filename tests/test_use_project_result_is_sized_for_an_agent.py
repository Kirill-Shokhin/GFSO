"""Switching projects answers "which one am I in", and pays for that answer in the caller's context.

A tool result lands in an agent's context window, which is the scarce resource in the MCP use-case.
Measured on the author's server: `use_project` returned all 270 project names AND a last-active
timestamp for each — several thousand tokens, on every switch, to perform a one-line action. The
inventory verb is `list_projects`; the switch verb should say where you are and what you touched
recently, and say how much it left out rather than trimming silently.
"""
from __future__ import annotations

from gfso.mcp.server import _brief


def _listing(n: int) -> dict:
    return {"projects": [f"p{i}" for i in range(n)],
            "last_active": {f"p{i}": float(i) for i in range(n)}}


def test_the_switch_result_is_bounded_and_says_what_it_left_out():
    out = _brief(_listing(270), "p3")
    assert out["active"] == "p3"
    assert len(out["projects_recent"]) <= 12, "the switch result carries an inventory"
    assert out["projects_total"] == 270, "the trim is silent — nothing says how many exist"
    assert "last_active" not in out, "a timestamp per project is inventory, not an answer"


def test_the_recent_list_is_by_recency_and_always_holds_the_active_one():
    out = _brief(_listing(270), "p3")
    # p269 is the most recently touched by construction; p3 is old but is where the caller now IS,
    # and a switch result that omits the project just switched to answers the wrong question.
    assert out["projects_recent"][0] in ("p3", "p269")
    assert "p3" in out["projects_recent"]


def test_a_small_registry_is_returned_whole():
    out = _brief(_listing(3), "p1")
    assert sorted(out["projects_recent"]) == ["p0", "p1", "p2"]
    assert out["projects_total"] == 3
