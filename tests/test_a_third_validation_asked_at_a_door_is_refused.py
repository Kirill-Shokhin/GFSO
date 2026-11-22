"""Two reports on one delivery that decided nothing are about the contract, not the run: a third validator run asked at
a door is refused, naming the moves that lift it; the system's own asking (VALIDATING's issuer obtaining its verdict,
§16.14) is never refused there. The count is this delivery's — a refusal before a re-delivery counts nothing.

CONTROLS: `>= 2` → `>= 99` in `_refuse_validation` — the door test; drop `CALLER.get() is not None` — the system test;
`refusals_on_this_delivery` reading `rejected_report` raw — the re-delivery test; `known` ignored in `red_set` — the
red-set test."""
from __future__ import annotations

from gfso import tools as T
from gfso import tools_llm as TL
from gfso.config import CALLER, Principal
from gfso.core.protocol.invariants import red_set
from gfso.core.types import TaskId
from tests.support import committed
from tests.test_validate_result import _delivered_node, _eng

_RAN = []


class _Counts:
    """A validator that only counts that it was started."""
    calls, last_tool_calls, on_tick, stage_hint = [], {}, None, ""

    def run_agent(self, *a, **k):
        _RAN.append(1)
        return ""


def _refused_twice(tmp_path):
    e = _eng()
    (tmp_path / "f").write_text("x")
    _delivered_node(e, recorded=committed(tmp_path))
    for why in ("c1 undecided", "c2 undecided"):
        e.record_rejected_report(TaskId("n1"), why)
    return e


def test_a_third_run_asked_at_a_door_is_refused_with_what_lifts_it(tmp_path):
    e, _RAN[:] = _refused_twice(tmp_path), []
    at = CALLER.set(Principal("alice", ("alice",), "session", "signed in"))
    try:
        out = TL.validate_result(e, "n1", _llm=_Counts(), workdir=str(tmp_path))
    finally:
        CALLER.reset(at)
    assert out["verdict"] is None and out["refusals_on_this_node"] == 2 and not _RAN, out
    assert all(w in out["error"] for w in ("edit_criteria", "record_verdict", "reassign")), out
    e.stop()


def test_the_systems_own_asking_is_not_refused(tmp_path):
    e, _RAN[:] = _refused_twice(tmp_path), []
    TL.validate_result(e, "n1", _llm=_Counts(), workdir=str(tmp_path))
    assert _RAN, "the system's own validation was refused"
    e.stop()


def test_a_refusal_before_a_re_delivery_counts_nothing_on_the_new_one(tmp_path):
    e = _refused_twice(tmp_path)
    assert T.get_verdict(e, "n1")["refused_report"]["refusals_on_this_node"] == 2
    T.signal(e, "n1", "FAIL", "alice", failed_criteria=["flush"])
    T.signal(e, "n1", "DELIVER", "alice", result="again")
    assert e.refusals_on_this_delivery(TaskId("n1")) == 0
    assert T.get_verdict(e, "n1")["refused_report"]["refusals_on_this_node"] == 0
    e.stop()


def test_the_red_set_is_over_the_nodes_criteria():
    entries = [{"criterion": "a", "verdict": "pass"}, {"criterion": "b", "verdict": "fail"},
               {"criterion": "a", "verdict": "undecidable"}, {"criterion": "x", "verdict": "fail"}]
    assert red_set(entries) == ["b", "a", "x"]
    assert red_set(entries, ["a", "b"]) == ["b", "a"]
