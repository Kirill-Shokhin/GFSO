"""A goal the planner authored as one part is a leaf (§3.7), healthy: its log line says so, never "nothing was built",
which the release's fresh clients read on every one-node plan as a failure — a residue on the goal itself included."""
import pytest

import gfso.decompose as D
from gfso import tools as T
from gfso.decompose import _build_verified, built_line
from tests.support import criterion, make_engine as _engine


def test_a_one_part_plan_reads_as_one_part():
    assert built_line(0, [], 0).startswith("builder: one part")
    one = built_line(0, ["root / criterion c: whether its description agrees with its checks is undecided"], 0)
    assert one.startswith("builder: one part") and "1 problem" in one


def test_an_empty_build_still_says_nothing_was_built():
    assert "no subtasks" in built_line(0, ["the authoring proposed no subtasks — nothing was built"], 0)
    assert "admission refused" in built_line(0, ["the admission refused it: CHECK-1"], 3)
    assert "none of the 3 proposed" in built_line(0, ["dropped: x"], 3)


def test_a_build_reads_as_before():
    assert built_line(3, [], 3).startswith("builder: structurally clean")
    assert built_line(3, ["x"], 3) == "builder: honest residue — 1 problem(s)"


def _split_round(folded: bool, monkeypatch) -> list[str]:
    """A split asked of a node held as issued (`contract_fixed`), whose authoring left no part: folded from one, or empty."""
    monkeypatch.setattr(D, "build_graph_live", lambda sp, req, eng, root_id, **k: (eng, root_id, []))
    e = _engine()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("c", "C")]})
    spec = {"root_criteria": [{"name": "c", "description": "C"}], "subtasks": [], "mappings": [], "deps": []}
    return _build_verified(spec, "goal", e, "root", "user", None, contract_fixed=True, folded=folded)[2]


def test_a_split_round_folded_to_one_part_is_not_an_empty_authoring(monkeypatch):
    assert not any("proposed no subtasks" in str(p) for p in _split_round(True, monkeypatch))


def test_a_split_round_that_authored_nothing_still_says_so(monkeypatch):
    """CONTROL: the condition the fold may not silence — a split asked and nothing proposed (the false clean)."""
    assert any("proposed no subtasks" in str(p) for p in _split_round(False, monkeypatch))


@pytest.mark.parametrize("parts, folded", [(1, True), (0, False), (2, False)])
def test_the_authoring_round_tells_the_build_whether_it_folded(monkeypatch, parts, folded):
    """WIRING: `decompose_into` passes `folded` from the authoring it folded, and only from that one."""
    seen = {}
    part = lambda k: {"id": f"p{k}", "criteria": [{"name": f"k{k}", "description": "K"}]}
    monkeypatch.setattr(D, "decompose_spec", lambda *a, **k: {"root_criteria": [], "subtasks": [part(i) for i in range(parts)]})

    def _stop(spec, *a, **k):
        seen.update(k)
        raise RuntimeError("stop at the build")
    monkeypatch.setattr(D, "_build_verified", _stop)
    with pytest.raises(RuntimeError):
        D.decompose_into(_engine(), "goal", llm=object())
    assert seen["folded"] is folded
