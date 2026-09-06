"""Every DONE node was drawn the same — the earned one and the one signed for. It is not.

Wave 26 (2026-09-06), the one open item three doors left behind: `/api/tasks/<id>` carried no
verdict provenance and `/api/graph` none either, so the page a person watches could not show that a
hand verdict had DISPLACED an instrument's opposite one — *"all DONE nodes are drawn identically"*.
The engine has known it by name since 2026-09-04 (`closures_by_hand`, `hand_overruled_closures`,
`refuted_passes`), but only as lists over a whole graph, which is a fact about a project and not
about the node under the cursor.

So: one per-node owner (`Engine.closure_of`), the three lists derived from it, and both node reads
carrying it. The negative controls are the point — a node an instrument judged must not acquire a
qualifier it did not earn, and a node that has not settled has no closure at all.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from gfso import tools as T
from gfso.api.server import create_app
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine

_CRIT = [{"name": "c", "description": "C"}]
_RISKS = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]


def _leaf(e, tid, assignee="exec-1"):
    T.create_task(e, tid, {"description": "a leaf", "criteria": _CRIT, "accepted_risks": _RISKS},
                  assignee=assignee)
    e.wait_idle()
    T.signal(e, tid, "ACCEPT", assignee)
    T.signal(e, tid, "DELIVER", assignee, result="claimed done")


def _instrument_verdict(e, tid, verdict="PASS", failed=()):
    e.record_exec_verdict(TaskId(tid), verdict, list(failed), "val-1",
                          per_criterion=[{"criterion": "c",
                                          "verdict": "pass" if verdict == "PASS" else "fail",
                                          "evidence": "ran the check, it printed OK",
                                          "behaviours": ["C holds"],
                                          "probe": [{"command": "check", "expect": "OK",
                                                     "behaviour": "C holds"}]}])


def _client(e) -> TestClient:
    return TestClient(create_app(e))


def _graph_node(c, tid):
    return next(n for n in c.get("/api/graph").json()["nodes"] if n["id"] == tid)


def test_a_node_closed_by_hand_says_so_on_both_reads():
    e = make_engine()
    e.start()
    _leaf(e, "leaf")
    T.record_verdict(e, "leaf", "PASS", reviewer="inspector",
                     observed={"c": "I ran the check myself and read OK"})
    T.signal(e, "leaf", "PASS", "exec-1")
    e.wait_idle()
    c = _client(e)

    detail = c.get("/api/tasks/leaf").json()["closure"]
    drawn = _graph_node(c, "leaf")["closure"]

    assert detail["by_hand"] is True and detail["provenance"] == "by_hand", detail
    assert detail["validator"] == "inspector", detail
    assert drawn == detail, "the picture and the panel read ONE record, not two copies of a rule"
    e.stop()


def test_a_node_an_instrument_judged_carries_no_qualifier():
    """The negative control: an earned green must not be drawn like a signed one."""
    e = make_engine()
    e.start()
    _leaf(e, "ok")
    _instrument_verdict(e, "ok")
    T.signal(e, "ok", "PASS", "exec-1")
    e.wait_idle()
    c = _client(e)

    cl = c.get("/api/tasks/ok").json()["closure"]

    assert cl["provenance"] == "instrument", cl
    assert cl["by_hand"] is False and cl["overruled"] is False and cl["refuted"] is False, cl
    e.stop()


def test_a_node_that_has_not_settled_has_no_closure():
    """⊥ is not a closure. An empty object here would read as `closed, nothing to weigh`."""
    e = make_engine()
    e.start()
    _leaf(e, "open")
    c = _client(e)

    assert c.get("/api/tasks/open").json()["closure"] is None
    assert _graph_node(c, "open")["closure"] is None
    e.stop()


def test_a_hand_verdict_that_displaced_an_instrument_is_visible_on_the_node():
    """The fact wave 26 could not see anywhere: legitimate (§14.5), uncheckable (§13.6), and said."""
    e = make_engine()
    e.start()
    _leaf(e, "over")
    _instrument_verdict(e, "over", "FAIL", failed=["c"])
    T.record_verdict(e, "over", "PASS", reviewer="me",
                     observed={"c": "I looked at it myself and it is fine"})
    T.signal(e, "over", "PASS", "exec-1")
    e.wait_idle()
    c = _client(e)

    cl = c.get("/api/tasks/over").json()["closure"]

    assert cl["overruled"] is True, cl
    assert "FAIL" in str(cl["overruled_verdict"]), cl
    assert e.hand_overruled_closures() == ["over"], "the list is the same predicate, not a second one"
    e.stop()


def test_a_pass_its_own_record_contradicts_is_marked_on_the_node():
    """`refuted_passes` was readable only as a project-wide list; the node itself said nothing."""
    e = make_engine()
    e.start()
    _leaf(e, "green")
    _instrument_verdict(e, "green")
    T.signal(e, "green", "PASS", "exec-1")
    e.wait_idle()
    _instrument_verdict(e, "green", "FAIL", failed=["c"])   # the instrument returns after the close

    cl = e.closure_of(TaskId("green"))

    assert cl["refuted"] is True, cl
    assert e.refuted_passes() == ["green"], "one predicate, both ways of asking it"
    e.stop()
