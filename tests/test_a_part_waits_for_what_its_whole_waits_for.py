"""A part waits for the producers its whole reads, through φ (§2.7; row GB_c_compiler_tnpji8716).

`root.cg-body` declared Dep on `root.base`, `root.parse-decl-stmt`, `root.cg-data` — its criteria (compiled C matches
gcc) read their result. Its system split was started at once: the execution order read only each node's OWN edges, and
a part has none toward its whole's producers. 49 of the row's 73 BLOCKs came from a node whose ancestor's declared
producer had not passed; the issuer, asked on each, promoted copies of producers the plan already held
(`cg-body.lexer`, `cg-body.expr_ast_parser`), and the copies' mutual waits were refuted and merged.

The rule (`start_waits`), read over START UNITS — a session's top for every node one session carries, else the node:
- DECLARED waits (E_Dep) always stand. A declared edge closing a cycle with the waits and a parent's wait on its parts
  is refused at declaration (CHECK-2), a discovered one is not adopted and refutes the order (§15.5), and no session is
  formed over a subtree a declared edge leaves and re-enters (`scope_top`): it starts as its own nodes.
- INFERRED waits through φ: an edge p → a binds the parts φ maps a's criteria carrying it to — those naming p, or all
  of a's where none does (always under AUTO) — and their mapped parts below; not a part φ maps nothing of it to, nor
  one below an edge from a's own subtree. One lying on a cycle of live unit waits is not taken, every such one at
  once, and is said: in `waiting` and once in the pipeline.
Every reader of "may it start" asks it (`Engine.producers_awaited`): the spawn, the scope's session, the frontier and
its waits, the ACCEPT reply, the place.

CONTROLS (each goes red): the φ walk takes nothing · the carry set is all of a's criteria · an inferred wait is never
left out · units are nodes · the own-subtree exclusion is dropped · the parent's wait leaves the cycle graph · a
finished producer still waits · CHECK-2 or the adoption reads no parent's wait · a session forms over a subtree a Dep
re-enters · the wait left out is unsaid · each reader reads E_Dep alone.
"""
import pytest

from gfso import tools as T
from gfso.core.types import DepEdge, State, TaskId
from gfso.core.graph.model import dep_order_refutations
from gfso.engine.validation import AdmissionRefused
from gfso.delegate import Dispatcher
from gfso.workspaces import parts_of
from tests.support import REGISTER, criterion
from tests.test_delegate import _agents, _drive_done, _eng, _goal


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")
    monkeypatch.setattr(Dispatcher, "_consent_guarded", lambda *a: None)   # a whole's own consent: no model here
    monkeypatch.setattr(Dispatcher, "_scope_guarded", lambda *a: None)     # …nor a scope's session


def _split(e, parent, kids: dict):
    """`parent` split into {child: [criteria of parent it covers]}, each child with one criterion of its own."""
    T.decompose(e, parent, [{"task_id": k, "spec": {"description": k, "criteria": [criterion(k.replace(".", "_"))]},
                             "assignee": "exec-1", "covers": c} for k, c in kids.items()], accepted_risks=REGISTER)


def _plan(tmp_path, check=False):
    """par → {prod, cons}, Dep prod → cons (bare, or with cons's own check on it: `dep__prod`), cons → {cons.a, cons.b}."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    _goal(e, "par", "agent")
    T.decompose(e, "par", [{"task_id": "prod", "spec": {"description": "prod", "criteria": [criterion("p")]},
                            "assignee": "exec-1", "covers": ["g"]},
                           {"task_id": "cons", "spec": {"description": "cons", "criteria": [criterion("c"), criterion("d")]},
                            "assignee": "exec-1", "covers": ["g"]}], accepted_risks=REGISTER)
    T.add_dependency(e, "prod", "cons", glue="cons's checks run what prod builds",
                     **({"check": criterion("dep__prod")["check"]} if check else {}))
    _split(e, "cons", {"cons.a": ["c", "dep__prod"] if check else ["c"], "cons.b": ["d"]})
    return e, agents


def _spawned(e, agents) -> set:
    return set(Dispatcher(e, agents, runner=lambda *a: None).dispatch_once())


def test_a_part_carrying_its_wholes_criteria_is_not_spawned_before_their_producer_passes(tmp_path):
    e, agents = _plan(tmp_path)
    started = _spawned(e, agents)
    assert "prod" in started and not {"cons.a", "cons.b"} & started, started
    _drive_done(e, "prod")
    assert {"cons.a", "cons.b"} <= _spawned(e, agents)
    e.stop()


def test_a_part_that_is_itself_split_is_not_put_to_work_before_the_producer_either(tmp_path):
    """The frontier offers a split part's ACCEPT ungated (its consent lets its subtree run); the dispatcher's own
    reading is what holds it, as it holds a whole on its own edge."""
    e, agents = _plan(tmp_path)
    _split(e, "cons.a", {"cons.a.1": ["cons_a"], "cons.a.2": ["cons_a"]})
    assert "cons.a" in {s["task_id"] for s in T.next_steps(e)["steps"]}
    assert not {"cons.a", "cons.a.1", "cons.a.2"} & _spawned(e, agents)
    e.stop()


def test_where_the_whole_names_the_criterion_reading_it_only_its_carrier_waits(tmp_path):
    e, agents = _plan(tmp_path, check=True)
    started = _spawned(e, agents)
    assert "cons.b" in started and "cons.a" not in started, started
    e.stop()


def test_the_frontier_neither_offers_nor_hides_the_waiting_part(tmp_path):
    e, _ = _plan(tmp_path)
    ns = T.next_steps(e)
    assert not {"cons.a", "cons.b"} & {s["task_id"] for s in ns["steps"]}
    waits = {w["task_id"]: w for w in ns.get("waiting", ())}
    assert list(waits["cons.a"]["waits_on"]) == ["prod"], waits.get("cons.a")
    _drive_done(e, "prod")
    assert {"cons.a", "cons.b"} <= {s["task_id"] for s in T.next_steps(e)["steps"]}
    e.stop()


def test_the_accept_reply_names_the_producer_its_whole_waits_on(tmp_path):
    e, _ = _plan(tmp_path)
    assert e.unmet_producers(TaskId("cons.a")) == ["prod"]
    e.stop()


def test_a_scope_whose_top_is_a_part_waits_for_the_wholes_producer(tmp_path):
    e, agents = _plan(tmp_path)
    _split(e, "cons.a", {"cons.a.1": ["cons_a"], "cons.a.2": ["cons_a"]})
    for t in ("cons.a", "cons.a.1", "cons.a.2"):
        e.record_session_fit(TaskId(t), "~10 lines", True)
    d = Dispatcher(e, agents, runner=lambda *a: None)
    top = e.graph.get_task(TaskId("cons.a"))
    assert e.scope_top(TaskId("cons.a.1")).id == top.id
    assert not d._scope_ready(top, e.scope_members(top.id))
    _drive_done(e, "prod")
    assert d._scope_ready(top, e.scope_members(top.id))
    e.stop()


def test_a_parts_place_takes_in_the_producer_its_whole_reads(tmp_path):
    e, _ = _plan(tmp_path)
    assert "prod" in parts_of(e, [e.graph.get_task(TaskId("cons.a"))])[0]
    e.stop()


def _three(tmp_path, *kids):
    """par → `kids`, one criterion each."""
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"), ("val-1", "llm-validator"))
    _goal(e, "par", "agent")
    T.decompose(e, "par", [{"task_id": k, "spec": {"description": k, "criteria": [criterion(k.lower())]},
                            "assignee": "exec-1", "covers": ["g"]} for k in kids], accepted_risks=REGISTER)
    return e, agents


def _ring(tmp_path, split_x=False):
    """par → {P, A, Q}: Dep P → A, Q → P, and A's part A.x is what Q reads. A.x waiting on P (A's criteria read P) would
    wait on its own consumer's consumer; with A.x split, A.x.1 would, through A.x's wait on its parts."""
    e, agents = _three(tmp_path, "P", "A", "Q")
    T.add_dependency(e, "P", "A", glue="A's integration runs P")
    T.add_dependency(e, "Q", "P", glue="P reads Q")
    _split(e, "A", {"A.x": ["a"], "A.y": ["a"]})
    if split_x:
        _split(e, "A.x", {"A.x.1": ["A_x"], "A.x.2": ["A_x"]})
    T.add_dependency(e, "A.x", "Q", glue="Q reads A.x's types")
    return e, agents


def test_a_wait_through_its_whole_that_would_close_a_cycle_is_not_taken_and_is_said(tmp_path):
    e, agents = _ring(tmp_path)
    assert e.producers_awaited(TaskId("A.x")) == [] and e.producers_awaited(TaskId("A.y")) == ["P"]
    started = _spawned(e, agents)
    assert "A.x" in started and "A.y" not in started, started
    said = [w for w in T.next_steps(e).get("waiting", ()) if w["task_id"] == "A.x"]
    assert said and "not waited: would close a cycle" in said[0]["why"] and list(said[0]["waits_on"]) == ["P"], said
    told = [x["message"] for x in e.pipeline_log() if x["message"].startswith("A.x: not waiting for P")]
    assert len(told) == 1 and "A.x → Q → P → A.x" in told[0], told      # said once, with its cycle, however often read
    e.stop()


def test_the_cycle_runs_through_a_parents_wait_on_its_parts(tmp_path):
    """A.x.1 → A.x (A.x waits on its parts) → Q → P: A.x.1 waiting on P closes that ring."""
    e, agents = _ring(tmp_path, split_x=True)
    assert "P" not in e.producers_awaited(TaskId("A.x.1"))
    assert "A.x.1" in _spawned(e, agents)
    e.stop()


def test_a_ring_through_a_finished_producer_is_no_wait(tmp_path):
    """Q passed: P no longer waits on it, so nothing returns to A.x — it waits on P as its whole does."""
    e, agents = _ring(tmp_path)
    _drive_done(e, "Q")
    assert e.producers_awaited(TaskId("A.x")) == ["P"]
    assert "A.x" not in _spawned(e, agents)
    e.stop()


def test_a_whole_reading_its_own_part_does_not_hold_its_other_parts(tmp_path):
    e, agents = _plan(tmp_path)
    e._graph._storage.add_dep_edge(DepEdge(from_id=TaskId("cons.a"), to_id=TaskId("cons"), discovered=True))
    assert "cons.a" not in e.producers_awaited(TaskId("cons.b"))
    _drive_done(e, "prod")
    assert {"cons.a", "cons.b"} <= _spawned(e, agents)
    assert e.graph.get_state(TaskId("cons")) != State.DONE
    e.stop()


def test_a_declared_dep_closing_a_ring_through_a_parents_wait_is_refused_at_declaration(tmp_path):
    """par → {a, b}, b → {b.c, b.d}; a reads b, so b.c reading a waits on a part of what a waits on (b on b.c)."""
    e, _ = _three(tmp_path, "a", "b")
    _split(e, "b", {"b.c": ["b"], "b.d": ["b"]})
    T.add_dependency(e, "b", "a", glue="a reads b")
    with pytest.raises(ValueError, match="b.c → b → a"):
        T.add_dependency(e, "a", "b.c", glue="b.c reads a")
    assert ("a", "b.c") not in {(str(x.from_id), str(x.to_id)) for x in e.adopted_dependencies()}
    e.stop()


def test_a_dep_on_ones_own_ancestor_is_refused_at_declaration(tmp_path):
    e, _ = _three(tmp_path, "a", "b")
    with pytest.raises(ValueError, match="a → par"):
        T.add_dependency(e, "par", "a", glue="a reads par")
    e.stop()


def _decomposing(e, parent, kids: dict):
    """`parent` split into {child: the producers its declared deps name}, each covering the parent's one criterion."""
    crit = e.graph.get_task(TaskId(parent)).spec.criteria[0].name
    return T.decompose(e, parent, [{"task_id": k, "spec": {"description": k, "criteria": [criterion(k.replace(".", "_"))]},
                                    "assignee": "exec-1", "covers": [crit],
                                    **({"deps": [{"from": f, "glue": f"{k} reads {f}"} for f in fs]} if fs else {})}
                                   for k, fs in kids.items()], accepted_risks=REGISTER)


def _refused_whole(e, parent, kids: dict, ring: str):
    edges = sorted((str(x.from_id), str(x.to_id)) for x in e.adopted_dependencies())
    with pytest.raises(AdmissionRefused, match=ring):
        _decomposing(e, parent, kids)
    assert sorted((str(x.from_id), str(x.to_id)) for x in e.adopted_dependencies()) == edges
    assert not e.graph.get_active_children(TaskId(parent)), "nothing of the refused split was written"


def test_a_split_whose_child_reads_what_waits_on_its_parent_is_refused_whole(tmp_path):
    """a reads b, and b waits on its new part b.c: b.c reading a closes the ring through b's wait on it."""
    e, _ = _three(tmp_path, "a", "b")
    T.add_dependency(e, "b", "a", glue="a reads b")
    _refused_whole(e, "b", {"b.c": ["a"], "b.d": []}, "b.c → b → a → b.c")
    e.stop()


def test_a_split_whose_child_reads_its_own_parent_is_refused_whole(tmp_path):
    e, _ = _three(tmp_path, "a", "b")
    _refused_whole(e, "b", {"b.c": ["b"], "b.d": []}, "b.c → b → b.c")
    e.stop()


def test_a_split_closing_a_ring_through_a_standing_parts_wait_is_refused_whole(tmp_path):
    """b → {b.c} stands, a reads b: b.c's new part b.c.1 reading a closes b.c.1 → b.c → b → a, the middle hop a wait
    the graph already holds."""
    e, _ = _three(tmp_path, "a", "b")
    _decomposing(e, "b", {"b.c": [], "b.d": []})
    T.add_dependency(e, "b", "a", glue="a reads b")
    _refused_whole(e, "b.c", {"b.c.1": ["a"], "b.c.2": []}, "b.c.1 → b.c → b → a → b.c.1")
    e.stop()


def test_a_discovery_closing_a_ring_through_a_parents_wait_is_not_adopted_and_refutes_the_order(tmp_path):
    e, _ = _three(tmp_path, "a", "b")
    _split(e, "b", {"b.c": ["b"], "b.d": ["b"]})
    T.add_dependency(e, "b", "a", glue="a reads b")
    e._graph._storage.add_dep_edge(DepEdge(from_id=TaskId("a"), to_id=TaskId("b.c"), discovered=True))
    assert ("a", "b.c") not in {(str(x.from_id), str(x.to_id)) for x in e.adopted_dependencies()}
    assert ("a", "b.c") in {(str(x.from_id), str(x.to_id)) for x in dep_order_refutations(e.graph)}
    e.stop()


def _session_over_a_member_the_producer_reads(tmp_path, own: bool):
    """par → {P, A}; A → {A.t, A.u}; A.t → {A.t.m2, A.t.m3}, fit for one session; P reads A.t.m2. A.t waits on P —
    through A (Dep P → A), or on its own edge (Dep P → A.t)."""
    e, agents = _three(tmp_path, "P", "A")
    _split(e, "A", {"A.t": ["a"], "A.u": ["a"]})
    _split(e, "A.t", {"A.t.m2": ["A_t"], "A.t.m3": ["A_t"]})
    T.add_dependency(e, "P", "A.t" if own else "A", glue="A.t's checks run P")
    T.add_dependency(e, "A.t.m2", "P", glue="P reads m2")
    for t in ("A.t", "A.t.m2", "A.t.m3"):
        e.record_session_fit(TaskId(t), "~10 lines", True)
    return e, agents


def test_a_session_does_not_wait_through_its_whole_on_a_producer_that_reads_its_member(tmp_path):
    """The wait A.t's members take from A closes a ring only because the session starts whole: it is not taken, and
    said — node by node it looked acyclic, the session waited on P, P on m2 inside it, and nothing ever started."""
    e, agents = _session_over_a_member_the_producer_reads(tmp_path, own=False)
    assert e.scope_top(TaskId("A.t.m3")).id == TaskId("A.t")
    started = _spawned(e, agents)
    assert "scope:A.t" in started and "P" not in started, started
    assert ("A.t.m3", "P") in e.waits_not_taken()
    e.stop()


def test_a_declared_wait_a_session_would_close_into_a_ring_unforms_the_session(tmp_path):
    """A.t's own Dep on P is declared, so it stands: the subtree P leaves and re-enters is carried by no one session,
    and its nodes start as their own — m2 first, then P, then what reads P."""
    e, agents = _session_over_a_member_the_producer_reads(tmp_path, own=True)
    assert e.scope_top(TaskId("A.t.m3")) is None
    assert e.producers_awaited(TaskId("A.t")) == ["P"]
    started = _spawned(e, agents)
    assert "A.t.m2" in started and not {"scope:A.t", "P", "A.t.m3"} & started, started
    e.stop()
