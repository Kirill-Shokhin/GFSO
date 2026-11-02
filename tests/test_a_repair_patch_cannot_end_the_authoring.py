"""A repair patch is read by the admission when it is taken: E2 T03's last round wrote a probe naming an unpinned file while
answering other findings, nothing re-read it, and the build's refusal ended a paid authoring (2026-11-02)."""
import gfso.decompose as D
from tests.support import make_engine


def _ok(name, cmd="./prog --check"):
    return {"name": name, "check": [{"behaviour": "b", "command": cmd, "expect": "0"}]}


_UNPINNED = {"name": "design", "check": [{"behaviour": "b", "command": "cat {inputs}/transcript.md", "expect": "x"}]}
_SPEC = {"root_criteria": [_ok("r")], "subtasks": [{"id": "a", "criteria": [_ok("design")]}], "mappings": []}


def _built(monkeypatch, rounds, spec=_SPEC):
    built, patches = [], iter(rounds)
    monkeypatch.setattr(D, "build_graph_live", lambda sp, *a, **k: built.append(sp) or (None, "root", []))
    monkeypatch.setattr(D, "_problems", lambda *a, **k: [])
    monkeypatch.setattr(D, "_audit_fix", lambda *a, **k: next(patches))
    D._build_verified(spec, "req", make_engine(), "root", "agent", llm=None)
    return built[-1]


def test_the_last_round_s_patch_cannot_carry_a_refused_probe_into_the_build(monkeypatch):
    broken = {**_SPEC, "subtasks": [{"id": "a", "criteria": [_ok("design")]},
                                    {"id": "b", "criteria": [{"name": "open", "check": []}]}]}
    sp = _built(monkeypatch, [{}, {"subtasks": [{"id": "a", "criteria": [_UNPINNED]},
                                                {"id": "b", "criteria": [_ok("open")]}]}], broken)
    assert not D._refused_probes(sp), "the build got nothing the admission refuses"
    assert sp["subtasks"][0]["criteria"] == [_ok("design")], "the rewritten criterion keeps its earlier text"
    assert sp["subtasks"][1]["criteria"] == [_ok("open")], "the patch's sound part stands"


def test_a_criterion_the_patch_adds_refused_leaves_and_one_already_refused_stays_the_repair_s(monkeypatch):
    out = D._patched_admissible(_SPEC, {"subtasks": [{"id": "a", "criteria": [_ok("design"), {**_UNPINNED, "name": "new"}]}]}, "", None)
    assert [c["name"] for c in out["subtasks"][0]["criteria"]] == ["design"]
    bad = {**_SPEC, "subtasks": [{"id": "a", "criteria": [_UNPINNED]}]}
    still = {**_UNPINNED, "check": [{"behaviour": "c", "command": "cat {inputs}/other.md", "expect": "y"}]}
    out = D._patched_admissible(bad, {"subtasks": [{"id": "a", "criteria": [still]}]}, "", None)
    assert out["subtasks"][0]["criteria"] == [still], "no earlier admitted text to go back to"
