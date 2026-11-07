"""Two ways a run spent sessions whose work could not count (GB_coreutils_tn5lhw152, AUTO haiku 4.5, 2026-10-19).

A scope session started on the first round's nodes while the second round of the same decomposition rebuilt them; the
rebuild re-offered every node, and the session, its validation and their spend were thrown away. And with the session's
cap floored at a minute, sessions were spawned past their deadline and killed before they could report, until the clock
escalated the node — which it would have done without them.
"""
from __future__ import annotations

from types import SimpleNamespace as NS

import gfso.tools as T
from gfso.delegate import Dispatcher
from gfso.inflight import _inflight
from gfso.roster import AgentRegistry
from gfso.sessions import MIN_SESSION_S, _too_late
from tests.support import REGISTER, criterion, make_engine


def _tree(tmp_path):
    e = make_engine()
    e.start()
    e.project_name = "p"
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g")], "accepted_risks": REGISTER},
                  assignee="me")
    T.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "part", "criteria": [criterion("k")]},
                             "assignee": "exec-1", "covers": ["g"]}], accepted_risks=REGISTER)
    e.wait_idle()
    return e, Dispatcher(e, AgentRegistry(path=str(tmp_path / "agents.json")), poll=30)


def test_a_node_under_a_decomposition_in_flight_is_not_dispatched(tmp_path):
    e, d = _tree(tmp_path)
    assert not d._being_rewritten("kid")
    with _inflight("auto_decompose", e, "root"):
        assert d._being_rewritten("kid") and d._being_rewritten("root")
    with _inflight("auto_decompose", e, "kid"):
        assert d._being_rewritten("kid") and not d._being_rewritten("root"), "nothing above the rewritten subtree waits"
    with _inflight("validate_result", e, "root"):
        assert not d._being_rewritten("kid"), "only a decomposition rewrites the subtree"
    e.stop()


def test_a_session_that_cannot_report_before_its_deadline_is_not_spawned():
    said = []
    eng = NS(emit_info=lambda src, msg: said.append(msg))
    assert _too_late(eng, "n", MIN_SESSION_S - 1)["status"] == "too_late" and "no session spawned" in said[0]
    assert _too_late(eng, "n", -300)["status"] == "too_late"
    assert _too_late(eng, "n", MIN_SESSION_S) is None and _too_late(eng, "n", None) is None
