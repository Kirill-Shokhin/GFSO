"""Deadline coherence gates the ADMISSION that sets the deadlines, and only flags afterwards (v4.1 §11.5, §12.10).

§11.5: the admission gates item (6) — every child's deadline inside a live parent's — and CHECK-3's Dep crossing, over
the deadlines that admission sets, where some choice of them orders the edge; the decomposer lifts both by his own
choice. Met afterwards — a revision, a re-issue, a Dep declared later (a re-author of its consumer) — a crossing is a
flag routed to the consumer's issuer, who may re-ASSIGN it or let it run (§12.10); nothing it refuses. Gating it at the
execution gate refused the consumer's ACCEPT and the parent's PASS over deadlines the machine issuer had written itself,
with no move to lift it (sync audit 2026-10-04, B-F1).

The v4.0 reading this file pinned before — item (6) refuses nothing, CHECK-3 gates execution — is the one v4.1 changed.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import gfso.tools as T
from gfso.core.types import State, TaskId
from gfso.engine.loop import refresh_checks
from gfso.engine.validation import _EXEC_GATING_CHECKS
from tests.support import criterion, make_engine, REGISTER

_RISK = REGISTER


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


#: Dates as OFFSETS from now, not literals: every non-terminal state is bounded since v4.1.
def _in(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).isoformat()


def _root():
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal",
                              "criteria": [criterion("a", "A"), criterion("b", "B")],
                              "accepted_risks": _RISK}, assignee="me", deadline=_in(30))
    return e


def _kid(tid, covers, deadline, depends_on=None):
    crit = criterion(f"{tid[-1]}1", tid)
    crits = [crit] + ([{**criterion(f"dep__{depends_on}", "reads it"), "depends_on": depends_on}] if depends_on else [])
    return {"task_id": tid, "spec": {"description": tid, "criteria": crits}, "assignee": "me", "covers": covers.split(),
            "deadline": deadline}


def _verdicts(e):
    return {c["check"]: c["verdict"] for c in T.get_checks(e, "root")}


def test_a_child_outliving_its_parent_is_refused_at_the_admission():
    e = _root()
    with pytest.raises(ValueError, match=r"item \(6\)"):
        T.decompose(e, "root", [_kid("root.x", "a", _in(60))], accepted_risks=REGISTER)
    assert e.graph.get_task("root.x") is None, "the admission was refused whole"
    e.stop()


def test_a_crossing_the_admission_sets_is_refused():
    e = _root()
    with pytest.raises(ValueError, match="CHECK-3"):
        T.decompose(e, "root", [_kid("root.x", "a", _in(20)), _kid("root.y", "b", _in(10), depends_on="root.x")], accepted_risks=REGISTER)
    e.stop()


def test_a_child_created_into_the_split_is_admitted_through_the_same_gate():
    """`create_task(parent_id=…)` adds a child to the split — a re-admission (§11.5), gated as `decompose` is (critic r7,
    A1). The tools door answers a refusal as `{"error": …}`, not a raise."""
    e = _root()
    T.decompose(e, "root", [_kid("root.p", "a b", _in(20))], accepted_risks=REGISTER)
    out = T.create_task(e, "root.x", {"description": "x", "criteria": [criterion("x1", "X")]}, assignee="me",
                        parent_id="root", deadline=_in(60), covers=["a"])
    assert "item (6)" in out.get("error", ""), out
    out = T.create_task(e, "root.c", {"description": "c", "criteria": [
        criterion("c1", "C"), {**criterion("dep__root.p", "reads p"), "depends_on": "root.p"}]},
        assignee="me", parent_id="root", deadline=_in(10), covers=["b"])
    assert "CHECK-3" in out.get("error", ""), out
    assert e.graph.get_task("root.x") is None and e.graph.get_task("root.c") is None
    e.stop()


def test_no_crossing_is_gated_where_no_choice_orders_every_edge():
    """§11.5: a crossing gates the admission "where some such choice orders every edge". p.a1 reads root.o, due after
    p.a1's parent, so no choice orders that edge — and then p.a1 → p.b1, orderable alone, is a flag too: read per edge,
    it was refused (critic r7, C1)."""
    e = _root()
    T.decompose(e, "root", [_kid("root.p", "a", _in(20)), _kid("root.o", "b", _in(25))], accepted_risks=REGISTER)
    T.decompose(e, "root.p", [_kid("p.a1", "p1", _in(10), depends_on="root.o"),
                              _kid("p.b1", "p1", _in(5), depends_on="p.a1")], accepted_risks=REGISTER)
    assert e.graph.get_task("p.b1") is not None
    e.stop()


def test_an_undated_chain_is_given_defaults_ordered_along_dep_and_check_3_reads_them():
    """§2.5 lets the implementation write a default; §2.7 and §9.5 hold for it. Written equal along build → util → pkg,
    the defaults made every consumer due with its producer, the clock enforcing it and CHECK-3 exempting it as
    "supplied" (critic over session 475ba784)."""
    e = _root()
    T.decompose(e, "root", [_kid("root.b", "a", None), _kid("root.u", "b", None, depends_on="root.b"),
                            _kid("root.p", "b", None, depends_on="root.u")], accepted_risks=REGISTER)
    e.wait_idle()
    b, u, p = (e.graph.get_task(TaskId(k)) for k in ("root.b", "root.u", "root.p"))
    assert b.deadline < u.deadline < p.deadline < e.graph.get_task(TaskId("root")).deadline
    assert b.deadline_supplied and u.deadline_supplied and p.deadline_supplied
    check3 = next(c for c in T.get_checks(e, "root") if c["check"] == "CHECK-3:deadlines")
    assert check3["verdict"] == "met", check3
    e.stop()


def _due_soon(hours: float = 6):
    """A root due inside the default span: every child's default meets the parent's bound, where the doors collided."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("a", "A"), criterion("b", "B")],
                              "accepted_risks": _RISK}, assignee="me",
                  deadline=(datetime.now() + timedelta(hours=hours)).isoformat())
    return e


def _ordered(e, *chain):
    ts = [e.graph.get_task(TaskId(k)) for k in chain] + [e.graph.get_task(TaskId("root"))]
    assert all(a.deadline < b.deadline for a, b in zip(ts, ts[1:])), [(t.id, t.deadline) for t in ts]
    assert next(c for c in T.get_checks(e, "root") if c["check"] == "CHECK-3:deadlines")["verdict"] == "met"


@pytest.mark.parametrize("hours", [6, 0.2])
def test_one_writer_orders_the_defaults_whatever_door_installs_the_dep(hours):
    """§2.5 with §2.7 at every door that installs a packet with a Dep (critic r2, F3): one writer (`mutations.Schedule`)
    for the admission, a child created into the split after its producer, and a Dep declared later — each wrote its
    own, and a producer standing on the parent's bound left its consumer due with it. Under a parent 12 minutes out a
    chain longer than its margins is still ordered, strictly."""
    e = _due_soon(hours)
    T.decompose(e, "root", [_kid("root.b", "a", None), _kid("root.u", "b", None, depends_on="root.b"),
                            _kid("root.p", "b", None, depends_on="root.u")], accepted_risks=REGISTER)
    e.wait_idle()
    _ordered(e, "root.b", "root.u", "root.p")
    e.stop()
    e = _due_soon(hours)
    T.decompose(e, "root", [_kid("root.x", "a b", None)], accepted_risks=REGISTER)
    T.create_task(e, "root.y", {"description": "y", "criteria": [
        criterion("y1", "Y"), {**criterion("dep__root.x", "reads x"), "depends_on": "root.x"}]},
        assignee="me", parent_id="root", covers=["b"])
    e.wait_idle()
    _ordered(e, "root.x", "root.y")
    e.stop()
    e = _due_soon(hours)
    T.decompose(e, "root", [_kid("root.x", "a", None), _kid("root.y", "b", None)], accepted_risks=REGISTER)
    T.add_dependency(e, "root.x", "root.y", glue="y reads x")
    e.wait_idle()
    _ordered(e, "root.x", "root.y")
    assert e.graph.get_task(TaskId("root.y")).deadline_supplied
    e.stop()


def test_a_typed_consumer_bounds_the_default_of_its_producer():
    """The consumer's typed deadline is a ceiling for the producer the admission dates (critic r2, F3)."""
    e = _due_soon(24 * 5)
    T.decompose(e, "root", [_kid("root.p", "a", None), _kid("root.c", "b", _in(1), depends_on="root.p")], accepted_risks=REGISTER)
    e.wait_idle()
    _ordered(e, "root.p", "root.c")
    e.stop()


@pytest.mark.parametrize("listed", ["producer first", "consumer first"])
@pytest.mark.parametrize("room", [timedelta(hours=48), timedelta(minutes=1)])
def test_an_untyped_chain_on_a_standing_producer_is_ordered_whichever_way_it_is_listed(listed, room):
    """Solved by recursion memoised along a path, the writer pinned the consumer before it had seen the standing
    producer two links down, and the admission then REFUSED a split nobody had typed a deadline in (critic over F3, A1)
    — or, with a minute of room, wrote a crossing where an order fitted inside it (A2)."""
    e = _due_soon(24 * 5)
    due = e.graph.get_task(TaskId("root")).deadline
    T.decompose(e, "root", [_kid("root.s", "a b", (due - room).isoformat())], accepted_risks=REGISTER)
    kids = [_kid("root.x", "b", None, depends_on="root.s"), _kid("root.c", "b", None, depends_on="root.x")]
    T.decompose(e, "root", kids if listed == "producer first" else kids[::-1], accepted_risks=REGISTER)
    e.wait_idle()
    _ordered(e, "root.s", "root.x", "root.c")
    e.stop()


@pytest.mark.parametrize("dated", [True, False])
def test_a_typed_crossing_is_refused_where_any_order_fits(dated, monkeypatch):
    """§11.5 gates a crossing "where some such choice orders every edge" — inside a minute of room as much as inside
    two hours (critic over F3, A3), and under a parent with no deadline at all, where every order fits (A4)."""
    if not dated:
        monkeypatch.setenv("GFSO_DEFAULT_DEADLINE_S", "0")
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("a", "A"), criterion("b", "B")],
                              "accepted_risks": _RISK}, assignee="me", **({"deadline": _in(1)} if dated else {}))
    due = e.graph.get_task(TaskId("root")).deadline or datetime.now() + timedelta(days=3)
    T.decompose(e, "root", [_kid("root.p", "a b", (due - timedelta(minutes=1)).isoformat())], accepted_risks=REGISTER)
    with pytest.raises(ValueError, match="CHECK-3"):
        T.decompose(e, "root", [_kid("root.c", "b", (due - timedelta(minutes=3)).isoformat(), depends_on="root.p")], accepted_risks=REGISTER)
    e.stop()


def test_past_the_parents_deadline_the_choice_is_unbounded_and_a_typed_crossing_still_gates():
    """§11.5 bounds the choice by the parent's deadline "while the parent's deadline is ahead"; past it the writer read the
    spent deadline as a ceiling, found no order, and admitted an orderable crossing (critic r2 over F3, finding 1)."""
    e = _root()
    T.decompose(e, "root", [_kid("root.p", "a b", _in(2))], accepted_risks=REGISTER)
    e.wait_idle()
    _age(e, "root", datetime.now() - timedelta(hours=1))
    with pytest.raises(ValueError, match="CHECK-3"):
        T.decompose(e, "root", [_kid("root.c", "b", _in(1), depends_on="root.p")], accepted_risks=REGISTER)
    e.stop()


@pytest.mark.parametrize("listed", ["re-issued first", "new first"])
def test_a_re_admission_orders_a_re_issued_child_against_the_new_one_it_reads(listed):
    """The act is every child the admission gives a version: a re-issued child given a new Dep was outside the writer,
    and came out due with the producer it now reads, by list order (critic r2 over F3, finding 2)."""
    e = _due_soon(24)
    T.decompose(e, "root", [_kid("root.b", "a b", None)], accepted_risks=REGISTER)
    e.wait_idle()
    kids = [_kid("root.b", "b", None, depends_on="root.a"), _kid("root.a", "a", None)]
    T.decompose(e, "root", kids if listed == "re-issued first" else kids[::-1], accepted_risks=REGISTER)
    e.wait_idle()
    _ordered(e, "root.a", "root.b")
    e.stop()


def test_where_no_order_exists_the_consumers_ceiling_holds_and_the_producers_floor_gives_way():
    """A revision adding a producer due after everything around it has no ordered answer; the fallback wrote the
    parent's bound and crossed the typed consumer as well (critic r2 over F3, finding 3). The supplied deadline that
    still sits under its consumer stays, and the one crossing is at the new producer's edge."""
    e = _due_soon(24)
    due = e.graph.get_task(TaskId("root")).deadline
    T.decompose(e, "root", [_kid("root.c", "a", None), _kid("root.d", "b", (due - timedelta(minutes=6)).isoformat(),
                                                             depends_on="root.c")], accepted_risks=REGISTER)
    T.decompose(e, "root", [_kid("root.p", "a", (due - timedelta(minutes=3)).isoformat())], accepted_risks=REGISTER)
    before = e.graph.get_task(TaskId("root.c")).deadline
    _age(e, "root.d", due - timedelta(minutes=4))     # room opened above c: what still fits is kept, not re-chosen
    T.add_dependency(e, "root.p", "root.c", glue="c reads p")
    e.wait_idle()
    c, d = (e.graph.get_task(TaskId(k)) for k in ("root.c", "root.d"))
    assert c.deadline == before < d.deadline
    e.stop()


def test_where_an_outside_producer_cannot_be_met_the_acts_own_chain_stays_ordered():
    """The edges among the act's own children never give way; only an outside end's does, the producer's before the
    consumer's. With the producer standing a second before its parent, the fallback wrote the whole chain equal
    (critic r3 over F3, finding 1); the typed consumer it still fits under keeps its ceiling."""
    e = _due_soon(0.2)
    due = e.graph.get_task(TaskId("root")).deadline
    T.decompose(e, "root", [_kid("root.s", "a b", (due - timedelta(seconds=1)).isoformat())], accepted_risks=REGISTER)
    T.decompose(e, "root", [_kid("root.x", "b", None, depends_on="root.s"),
                            _kid("root.c", "b", None, depends_on="root.x"),
                            _kid("root.d", "b", (due - timedelta(minutes=3)).isoformat(), depends_on="root.c")], accepted_risks=REGISTER)
    e.wait_idle()
    x, c, d = (e.graph.get_task(TaskId(k)) for k in ("root.x", "root.c", "root.d"))
    assert datetime.now() < x.deadline < c.deadline < d.deadline and x.deadline_supplied and c.deadline_supplied
    e.stop()


def test_a_short_supplied_deadline_that_still_fits_is_kept_on_a_revision():
    """A deadline a node already stands on is no new contract: kept while it fits, short or not; it was thrown away
    for the parent's bound and a crossing written over its typed consumer (critic r3 over F3, finding 2)."""
    e = _due_soon(24)
    due = e.graph.get_task(TaskId("root")).deadline
    T.decompose(e, "root", [_kid("root.p", "a", None),
                            _kid("root.c", "b", (due - timedelta(hours=2)).isoformat(), depends_on="root.p")], accepted_risks=REGISTER)
    e.wait_idle()
    _age(e, "root.c", datetime.now() + timedelta(minutes=3))
    _age(e, "root.p", datetime.now() + timedelta(minutes=1))
    before = e.graph.get_task(TaskId("root.p")).deadline
    T.revise(e, "root.p", {"description": "p", "criteria": [criterion("p1", "P"), criterion("p2", "more")]},
             agent="me")
    p = e.graph.get_task(TaskId("root.p"))
    assert p.deadline == before and p.deadline_supplied
    e.stop()


def test_a_deadline_the_writer_re_chose_stays_logged_as_supplied():
    """§2.5: a default is logged as supplied. Re-chosen through a re-admission's re-ASSIGN it was stored as typed, and a
    later Dep then left it standing in a crossing instead of re-choosing it (critic r3 over F3, finding 3)."""
    e = _due_soon(24)
    due = e.graph.get_task(TaskId("root")).deadline
    T.decompose(e, "root", [_kid("root.b", "a b", None)], accepted_risks=REGISTER)
    e.wait_idle()
    T.decompose(e, "root", [_kid("root.a", "a", (due - timedelta(minutes=2)).isoformat()),
                            _kid("root.b", "b", None, depends_on="root.a")], accepted_risks=REGISTER)
    e.wait_idle()
    assert e.graph.get_task(TaskId("root.b")).deadline_supplied
    _ordered(e, "root.a", "root.b")
    e.stop()


def test_an_issued_childs_new_dep_is_a_flag_at_every_door():
    """§11.5's choice is of the unissued children's deadlines: an issued child re-issued with a new Dep is a revision,
    flagged (§12.10) — admitted by `add_dependency`, refused by `decompose` (critic r3 over F3, finding 5)."""
    e = _due_soon(24)
    due = e.graph.get_task(TaskId("root")).deadline
    T.decompose(e, "root", [_kid("root.b", "b", (due - timedelta(hours=10)).isoformat()),
                            _kid("root.s", "a", (due - timedelta(hours=2)).isoformat())], accepted_risks=REGISTER)
    e.wait_idle()
    T.decompose(e, "root", [_kid("root.b", "b", None, depends_on="root.s")], accepted_risks=REGISTER)
    assert any(c.depends_on == "root.s" for c in e.graph.get_task(TaskId("root.b")).spec.criteria)
    e.stop()


def _age(e, tid, dl, state=None):
    t = e.graph.get_task(TaskId(tid))
    t.deadline, t.state = dl, state or t.state
    e._graph.save_task(t)


def test_a_version_with_no_live_deadline_is_refused_until_the_issuer_types_one():
    """§2.5, §12.16: under a parent whose deadline has passed the issuer types one. A re-ASSIGN typing none kept the
    spent deadline and entered OFFERED overdue (critic r7, A3); a child under a parent with minutes left got none (B-F5)."""
    e = _root()
    T.decompose(e, "root", [_kid("root.x", "a b", _in(20))], accepted_risks=REGISTER)
    e.wait_idle()
    past = datetime.now() - timedelta(hours=1)
    _age(e, "root", past)
    _age(e, "root.x", past, State.ESCALATED)        # where the lapse leaves it: the issuer's decision (§12.5)
    with pytest.raises(ValueError, match="types one"):
        T.revise(e, "root.x", {"description": "x again", "criteria": [criterion("x1", "X")]}, agent="me")
    out = T.revise(e, "root.x", {"description": "x again", "criteria": [criterion("x1", "X")]}, agent="me",
                   deadline=_in(1))
    assert "error" not in out, out
    _age(e, "root", datetime.now() + timedelta(minutes=2))
    out = T.create_task(e, "root.y", {"description": "y", "criteria": [criterion("y1", "Y")]}, assignee="me",
                        parent_id="root", covers=["a"])
    assert "no time inside" in out.get("error", ""), out
    e.stop()


def test_a_crossing_met_after_the_admission_is_a_flag_and_refuses_nothing():
    """A Dep declared after the split is a re-author of its consumer: its crossing is CHECK-3's flag, not a gate."""
    e = _root()
    T.decompose(e, "root", [_kid("root.x", "a", _in(20)), _kid("root.y", "b", _in(10))], accepted_risks=REGISTER)
    T.add_dependency(e, "root.x", "root.y", glue="y reads x")
    e.wait_idle()
    assert _verdicts(e)["CHECK-3:deadlines"] == "unmet", "the crossing went unsaid"
    step = next(s for s in T.next_steps(e, actor="me")["steps"] if s["task_id"] == "root")
    assert "DEADLINE FLAG for the consumer's issuer" in step["directive"], "the flag reaches nobody (critic r7, B2)"
    assert {h["check"].split(":")[0]: h["kind"] for h in T.list_holes(e)["holes"]}["CHECK-3"] == "flag",         "list_holes told the flag's reader to fix it before execution (critic r7, C2)"
    assert T.signal(e, "root.x", "ACCEPT", "me").get("accepted") is True
    e.stop()


def test_the_gate_holds_the_canons_level_0_less_the_rules_that_gate_only_at_admission():
    """The mechanism: the gate is a name filter, so the names are the boundary."""
    assert {p.rstrip(":") for p in _EXEC_GATING_CHECKS} == {
        "CHECK-1", "CHECK-1b", "CHECK-2", "CHECK-4", "CHECK-5", "CHECK-6"}


def test_an_edge_with_a_settled_end_is_not_read():
    """§11.5: CHECK-3 reads no edge one of whose ends is settled — a settled node's deadline orders nothing to come."""
    e = _root()
    T.decompose(e, "root", [_kid("root.x", "a", _in(20)), _kid("root.y", "b", _in(10))], accepted_risks=REGISTER)
    T.add_dependency(e, "root.x", "root.y", glue="y reads x")
    e.wait_idle()
    assert _verdicts(e)["CHECK-3:deadlines"] == "unmet"
    x = e.graph.get_task(TaskId("root.x"))
    x.state = State.DONE
    e._graph.save_task(x)
    refresh_checks(e._graph, TaskId("root"))
    assert _verdicts(e)["CHECK-3:deadlines"] in ("met", "met_vacuously")
    e.stop()


def test_a_spent_deadline_refuses_the_whole_split_before_any_child_is_issued():
    """Refused one ASSIGN at a time, `decompose` returned [k1, None] and left a criterion uncovered (critic r7, A2)."""
    e = _root()
    with pytest.raises(ValueError, match="already passed"):
        T.decompose(e, "root", [_kid("root.x", "a", _in(2)), _kid("root.y", "b", _in(-1))], accepted_risks=REGISTER)
    assert e.graph.get_task("root.x") is None
    e.stop()
