"""A repair patch is read by the admission when it is taken: E2 T03's last round wrote a probe naming an unpinned file while
answering other findings, nothing re-read it, and the build's refusal ended a paid authoring (2026-11-02). Through the real
build: a stubbed one hid that a rewrite under a new name still ended the authoring (critic, same day)."""
import pytest

import gfso.decompose as D
from tests.support import make_engine


def _ok(name, cmd="./prog --check"):
    return {"name": name, "description": name, "check": [{"behaviour": "b", "command": cmd, "expect": "0"}]}


def _bad(name):
    return {"name": name, "description": name, "check": [{"behaviour": "b", "command": "cat {inputs}/transcript.md", "expect": "x"}]}


_RISK = [{"factor": "f", "estimate": {"P": 0.1, "impact": "low"}, "justification": "j", "invalidation_condition": "c"}]


def _plan():
    return {"name": "g", "root_criteria": [_ok("r", "./prog --r")], "accepted_risks": _RISK, "deps": [],
            "subtasks": [{"id": "a", "name": "a", "writes": ["a.c"], "criteria": [_ok("design", "./prog --a")]},
                         {"id": "b", "name": "b", "writes": ["b.c"], "criteria": [{"name": "open", "description": "o", "check": []}]}],
            "mappings": [{"criterion": "r", "child_id": "a"}, {"criterion": "r", "child_id": "b"}]}


_FIXED_B = {"id": "b", "name": "b", "writes": ["b.c"], "criteria": [_ok("open", "./prog --b")]}


def _authored(monkeypatch, *rounds):
    patches = iter(rounds)
    monkeypatch.setattr(D, "_audit_fix", lambda *a, **k: next(patches, {}))
    e = make_engine()
    e.start()
    try:
        _, spec, _problems = D._build_verified(_plan(), "req", e, "root", "agent", llm=None)
    finally:
        e.stop()
    return spec, {k["id"]: k for k in spec["subtasks"]}


@pytest.mark.parametrize("a_after,kept", [
    ([_bad("design")], ["design"]),                         # rewritten under its own name
    ([_bad("renamed")], ["design"]),                        # …under another, the part's only criterion
    ([_ok("second", "./prog --s"), _bad("renamed")], ["design"]),  # …beside a sound one: nothing ties it to the old
])
def test_the_last_round_s_patch_cannot_end_the_authoring_at_its_build(monkeypatch, a_after, kept):
    spec, kids = _authored(monkeypatch, {}, {"subtasks": [{**kids_a(), "criteria": a_after}, _FIXED_B]})
    assert not D._refused_probes(spec), "the build got nothing the admission refuses"
    assert [c["name"] for c in kids["a"]["criteria"]] == kept
    assert kids["b"]["criteria"] == [_ok("open", "./prog --b")], "another node's sound patch stands"


def kids_a():
    return {"id": "a", "name": "a", "writes": ["a.c"]}


def test_a_part_the_patch_adds_with_nothing_admitted_leaves_with_its_seams(monkeypatch):
    spec, kids = _authored(monkeypatch, {}, {"subtasks": [_FIXED_B, {"id": "c", "name": "c", "writes": ["c.c"], "criteria": [_bad("x")]}],
                                             "mappings": _plan()["mappings"] + [{"criterion": "r", "child_id": "c"}],
                                             "deps": [{"from": "a", "to": "c", "why": "w", "reads": ["a.c"]}]})
    assert "c" not in kids and not D._refused_probes(spec)
    assert not [m for m in spec["mappings"] if m["child_id"] == "c"] and not spec["deps"]


def test_a_criterion_refused_before_the_patch_too_stays_the_repair_s():
    bad = {"root_criteria": [], "subtasks": [{"id": "a", "criteria": [_bad("design")]}]}
    still = {**_bad("design"), "check": [{"behaviour": "c", "command": "cat {inputs}/other.md", "expect": "y"}]}
    out = D._patched_admissible(bad, {"subtasks": [{"id": "a", "criteria": [still]}]}, "", None)
    assert out["subtasks"][0]["criteria"] == [still], "no earlier admitted text to go back to"
