"""A Dep edge is a record of its own, written by the act that declares it — never an entry of its consumer's criteria.

Dep is a primitive beside T (§2.7, §7.5): "B builds on A's result … no criterion of B referencing it" is the very class
of plans it exists for. An older engine wrote each declared edge as a fake criterion `dep__<producer>` on the consumer
(`depends_on`, the glue as its description) and derived E_Dep from those entries, so every reader of criteria had to
know which of them were not criteria. Now an admission writes its declared edges (§15.1), `add_dependency` writes one,
and a criterion whose own check reads the producer's result is a criterion that implies its edge. A database written
before is migrated at load — logged as a migration, no conjunct of V changed — and reads as it did."""
import json
from datetime import datetime, timedelta
import sqlite3

import pytest

from gfso import tools as T
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.core.graph import Graph
from gfso.core.graph.model import admission_key, goal_deps_key
from gfso.core.graph.metrics import q_Dep
from gfso.core.protocol.procedure import criteria_without_procedure, criterionless
from gfso.core.types import AgentId, Criteria, CriterionMapping, Signal, SignalData, Spec, Task, TaskId
from gfso.decompose.build import build_graph_live
from tests.support import REGISTER, REGISTER_SPLIT, criterion, make_engine, pinned
from tests.test_decompose_build import SPEC, _eng


def _no_bare_entry(e):
    """No stored contract carries an entry that names a producer and pins no check."""
    bare = [(str(t.id), c.name) for t in e.all_tasks() for c in t.spec.criteria if c.depends_on and not c.check]
    assert bare == [], f"a writer made a bare Dep entry among the criteria: {bare}"


def _declared(e):
    return sorted((str(x.from_id), str(x.to_id), x.glue) for x in e.graph._storage.get_dep_edges() if not x.discovered)


def _split(e, deps=True):
    T.create_task(e, "root", {"description": "parent", "criteria": [criterion("g", "G"), criterion("p", "P")],
                              "accepted_risks": REGISTER}, assignee="agent")
    T.decompose(e, "root", [
        {"task_id": "root.prod", "spec": {"description": "producer", "criteria": [criterion("pp", "PP")]},
         "assignee": "agent", "covers": ["p"]},
        {"task_id": "root.cons", "spec": {"description": "consumer", "criteria": [criterion("c", "C")]},
         "assignee": "agent", "covers": ["g"], **({"deps": [{"from": "root.prod", "glue": "cons reads prod's output"}]} if deps else {})}],
        accepted_risks=REGISTER)
    e.wait_idle()


def test_the_build_writes_its_seams_as_declared_edge_records():
    """…handed to the admission as its edges — not as entries the admission would have to take back out of a spec."""
    e = _eng()
    handed, admit = [], e.decompose_task
    e.decompose_task = lambda pid, kids, *a, **kw: handed.extend(kids) or admit(pid, kids, *a, **kw)
    build_graph_live(SPEC, "build the thing", e, root_id="root", assignee="human")
    e.wait_idle()
    assert handed and not [c.name for _, s, *_ in handed for c in s.criteria if c.depends_on and not c.check]
    _no_bare_entry(e)
    assert _declared(e) == [("root.a", "root.b", "B consumes A's output")]
    assert [c.name for c in e.graph.get_task(TaskId("root.b")).spec.criteria] == ["b1"]
    e.stop()


def test_add_dependency_writes_a_record_and_leaves_the_contract_alone():
    e = make_engine()
    e.start()
    _split(e, deps=False)
    before = e.graph.get_task(TaskId("root.cons")).spec
    T.add_dependency(e, "root.prod", "root.cons", glue="cons reads prod")
    e.wait_idle()
    _no_bare_entry(e)
    assert _declared(e) == [("root.prod", "root.cons", "cons reads prod")]
    assert e.graph.get_task(TaskId("root.cons")).spec == before, "a declared edge is no part of its consumer's contract"
    e.stop()


def test_the_wire_form_of_a_seam_is_read_as_the_edge_it_declares():
    """A door may still be handed `{name, description, depends_on}` with no check — the form an older client writes."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "parent", "criteria": [criterion("g", "G"), criterion("p", "P")],
                              "accepted_risks": REGISTER}, assignee="agent")
    T.decompose(e, "root", [
        {"task_id": "root.prod", "spec": {"description": "producer", "criteria": [criterion("pp", "PP")]},
         "assignee": "agent", "covers": ["p"]},
        {"task_id": "root.cons", "spec": {"description": "consumer", "criteria": [
            criterion("c", "C"), {"name": "dep__root.prod", "description": "reads prod", "depends_on": "root.prod"}]},
         "assignee": "agent", "covers": ["g"]}], accepted_risks=REGISTER)
    e.wait_idle()
    _no_bare_entry(e)
    assert _declared(e) == [("root.prod", "root.cons", "reads prod")]
    T.edit_criteria(e, "root.cons", [criterion("c", "C2"), {"name": "dep__root.prod", "description": "reads prod",
                                                            "depends_on": "root.prod"}], "agent")
    e.wait_idle()
    _no_bare_entry(e)
    assert _declared(e) == [("root.prod", "root.cons", "reads prod")], "one declaration, not two"
    e.stop()


def test_a_criterion_that_checks_the_producers_result_stays_one_and_its_edge_is_stored():
    e = make_engine()
    e.start()
    _split(e, deps=False)
    T.add_dependency(e, "root.prod", "root.cons", glue="cons checks prod", check=[
        {"behaviour": "prod's output parses", "command": "check prod", "expect": "ok"}])
    e.wait_idle()
    cons = e.graph.get_task(TaskId("root.cons"))
    assert [(c.name, c.depends_on, bool(c.check)) for c in cons.spec.criteria][-1] == ("dep__root.prod", "root.prod", True)
    assert _declared(e) == [("root.prod", "root.cons", "cons checks prod")]
    e.stop()


def test_removing_an_edge_marks_its_record_removed_and_q_dep_still_counts_it():
    e = make_engine()
    e.start()
    _split(e)
    T.remove_dependency(e, "root.prod", "root.cons")
    e.wait_idle()
    assert T.get_dependencies(e) == []
    assert [(str(x.from_id), x.removed) for x in e.graph.dep_edges(closed=True)] == [("root.prod", False)]
    assert q_Dep(e.graph) == 1.0
    e.stop()


def test_a_block_naming_a_declared_producer_records_no_discovery_and_leaves_the_declaration_alone():
    """The mutation reads discovered records only: a BLOCK's repeat used to reopen whatever record the pair had — with
    the declared edge stored, it would have turned the declaration into a provisional discovery."""
    e = make_engine()
    e.start()
    _split(e)
    for s in (SignalData(signal=Signal.ACCEPT, task_id=TaskId("root.cons"), source=AgentId("agent")),
              SignalData(signal=Signal.BLOCK, task_id=TaskId("root.cons"), source=AgentId("agent"),
                         reason="prod not done", blocker_task_ids=(TaskId("root.prod"),))):
        e.send_signal(s)
        e.wait_idle()
    assert [(x.discovered, x.provisional) for x in e.graph._storage.get_dep_edges()] == [(False, False)]
    e.stop()


def test_a_decidable_criterion_reading_a_producer_owes_its_procedure():
    """The exemption went with the bare entry: a `depends_on` criterion is a criterion, and one that pins nothing
    decides nothing (A1); one that reads a producer through its check decides something about this node."""
    assert criteria_without_procedure([Criteria("x", "x", depends_on=TaskId("a"))]) == ["x"]
    assert criterionless([Criteria("x", "x", depends_on=TaskId("a"), check=pinned("x"))]) is None


def _old_db(path):
    """A database as an older engine wrote it: the consumer's seam an entry of its criteria, mapped to a child of its
    own split, and a criterion beside it that reads the same producer through its own check."""
    s = SqliteStorage(path)
    g = Graph(s)
    for t in (Task(TaskId("prod"), Spec("producer", (Criteria("pp", "pp", check=pinned("pp")),))),
              Task(TaskId("cons"), Spec("consumer", (Criteria("c", "c", check=pinned("c")),
                                                     Criteria("dep__prod", "cons reads prod", depends_on=TaskId("prod")),
                                                     Criteria("dep__prod2", "cons checks prod", depends_on=TaskId("prod"),
                                                              check=pinned("dep__prod2"))))),
              Task(TaskId("kid"), Spec("kid", (Criteria("k", "k", check=pinned("k")),)), parent_id=TaskId("cons"))):
        g.save_task(t)
    cons = g.get_task(TaskId("cons"))
    cons.criterion_mappings = (CriterionMapping("c", TaskId("kid")), CriterionMapping("dep__prod", TaskId("kid")))
    g.save_task(cons)
    s._conn.execute("DELETE FROM dep_edges")          # …written before the records existed
    s._conn.execute("DELETE FROM pipeline_log")
    s._conn.commit()
    s.close()


def test_an_older_database_is_migrated_once_logged_and_reads_as_before(tmp_path):
    path = str(tmp_path / "old.db")
    _old_db(path)
    s = SqliteStorage(path)
    cons = s.get_task(TaskId("cons"))
    assert [c.name for c in cons.spec.criteria] == ["c", "dep__prod2"], "the bare entry left the spec, the check stayed"
    assert [(m.criterion_name, str(m.child_id)) for m in cons.criterion_mappings] == [("c", "kid")]
    edges = sorted((str(x.from_id), str(x.to_id), x.glue, x.discovered) for x in Graph(s).dep_edges())
    assert edges == [("prod", "cons", "cons checks prod", False)], "one pair is one edge, the later entry's glue"
    notes = [r[0] for r in s._conn.execute("SELECT message FROM pipeline_log WHERE source = 'migration'")]
    assert len(notes) == 1 and "dep__prod (prod)" in notes[0] and "no conjunct of V changes" in notes[0], notes
    s.close()
    again = SqliteStorage(path)                        # idempotent: nothing more to convert, nothing stored twice
    assert len(again.get_dep_edges()) == 1
    assert again._conn.execute("SELECT count(*) FROM pipeline_log WHERE source = 'migration'").fetchone()[0] == 1
    again.close()
    raw = sqlite3.connect(path)
    assert "dep__prod\"" not in raw.execute("SELECT spec_json FROM tasks WHERE id = 'cons'").fetchone()[0]
    assert json.loads(raw.execute("SELECT spec_json FROM tasks WHERE id = 'cons'").fetchone()[0])["criteria"][1]["check"]
    raw.close()


# === critic over the first cut: what the edge being no part of a packet must not lose ===

def _pair(e):
    T.create_task(e, "root", {"description": "parent", "criteria": [criterion("g", "G"), criterion("p", "P")],
                              "accepted_risks": REGISTER}, assignee="agent")
    T.decompose(e, "root", [{"task_id": k, "spec": {"description": k, "criteria": [criterion(k[-1] + "c", k)]},
                             "assignee": "agent", "covers": [c]} for k, c in (("root.A", "p"), ("root.B", "g"))],
                accepted_risks=REGISTER)
    e.wait_idle()


def test_an_edge_a_re_admission_adds_into_a_standing_child_orders_its_deadline():
    """§2.7 coherence: a child the act names unchanged is not re-issued for its contract — but the deadline the engine
    supplied it, crossed by the new producer, is chosen again, a version of its packet."""
    e = make_engine()
    e.start()
    _pair(e)
    T.decompose(e, "root", [{"task_id": "root.B", "spec": {"description": "root.B", "criteria": [criterion("Bc", "root.B")]},
                             "assignee": "agent", "covers": ["g"], "deps": [{"from": "root.A", "glue": "B reads A"}]}],
                accepted_risks=REGISTER)
    e.wait_idle()
    a, b = (e.graph.get_task(TaskId(k)) for k in ("root.A", "root.B"))
    assert a.deadline < b.deadline, (a.deadline, b.deadline)
    e.stop()


def test_an_edge_the_nodes_own_contract_declares_with_its_split_is_held_to_check_2():
    e = make_engine()
    e.start()
    _pair(e)
    T.add_dependency(e, "root.A", "root.B", glue="B reads A")
    a = e.graph.get_task(TaskId("root.A"))
    contract = Spec(a.spec.description, a.spec.criteria + (Criteria("dep__root.B", "A reads B", depends_on=TaskId("root.B")),),
                    accepted_risks=a.spec.accepted_risks)
    with pytest.raises(ValueError, match="Dep cycle"):
        e.decompose_task(TaskId("root.A"), [(TaskId("root.A.x"), Spec("x", (Criteria("xc", "x", check=pinned("xc")),)),
                                             AgentId("agent"))], [CriterionMapping("Ac", TaskId("root.A.x"))],
                         register=REGISTER_SPLIT, contract=contract)
    assert sorted((str(x.from_id), str(x.to_id)) for x in e.graph.dep_edges(adopted=True)) == [("root.A", "root.B")]
    e.stop()


def test_an_edge_stated_again_in_other_words_is_one_edge():
    """q_Dep counts records: a re-wording that wrote a second record raised the declared half (0.5 → 0.667)."""
    e = make_engine()
    e.start()
    _pair(e)
    T.add_dependency(e, "root.A", "root.B", glue="g1")
    T.edit_criteria(e, "root.B", [criterion("Bc", "B2"), {"name": "dep__root.A", "description": "g2", "depends_on": "root.A"}],
                    "agent")
    T.add_dependency(e, "root.A", "root.B", glue="g3", check=[{"behaviour": "b", "command": "check A", "expect": "ok"}])
    e.wait_idle()
    assert [str(x.from_id) for x in e.graph.dep_edges(closed=True)] == ["root.A"]
    e.stop()


# === the act that declares an edge is on the log (Thm 11, §15.1): a re-admission of the consumer's split ===

def _admissions(e, node="root"):
    return json.loads(e.graph._storage.get_critique(admission_key(TaskId(node))) or "[]")


def test_declaring_and_cutting_an_edge_is_a_logged_re_admission_that_re_offers_nobody():
    """Dep is a form item of the SPLIT (§4.5 item 4), changed only by its re-admission (§11.5); no packet field moves,
    so the consumer at work stays at work (§10.1) — a typed deadline, so nothing of its packet has to move."""
    e = make_engine()
    e.start()
    _pair(e)
    due = (datetime.now() + timedelta(days=2)).isoformat()
    T.revise(e, "root.B", {"description": "root.B", "criteria": [criterion("Bc", "root.B")]}, "agent", deadline=due)
    T.signal(e, "root.B", "ACCEPT", "agent")
    e.wait_idle()
    n, log = len(_admissions(e)), len(e.audit_log(TaskId("root.B")))
    out = T.add_dependency(e, "root.A", "root.B", glue="B reads A")
    e.wait_idle()
    assert _admissions(e)[n:] and _admissions(e)[-1]["deps"] == {"root.B": [["root.A", "B reads A"]]}
    assert "consumer_reissued" not in out
    assert e.graph.get_state(TaskId("root.B")).name == "EXECUTING" and len(e.audit_log(TaskId("root.B"))) == log
    out = T.remove_dependency(e, "root.A", "root.B")
    e.wait_idle()
    assert _admissions(e)[-1]["deps"] == {"root.B": []} and "re-authored" not in json.dumps(out)
    assert e.graph.get_state(TaskId("root.B")).name == "EXECUTING" and e.graph.dep_edges() == []
    e.stop()


def test_a_roots_edge_is_recorded_as_its_goals_issuer_joining_it():
    """A root sits in no split (§15.2): the declaration is recorded as that act, and the root's contract is untouched."""
    e = make_engine()
    e.start()
    _pair(e)
    T.add_dependency(e, "root.A", "root", glue="the goal reads A")
    rec = json.loads(e.graph._storage.get_critique(goal_deps_key(TaskId("root"))) or "[]")
    assert [r["deps"] for r in rec] == [[["root.A", "the goal reads A"]]]
    e.stop()


def test_the_decompose_doors_deps_name_a_node_and_one_pair_is_one_edge():
    e = make_engine()
    e.start()
    _pair(e)
    kid = lambda deps: [{"task_id": "root.B", "spec": {"description": "root.B", "criteria": [criterion("Bc", "root.B")]},
                         "assignee": "agent", "covers": ["g"], "deps": deps}]
    for bad in ([{"glue": "x"}], [{"from": "root.nope", "glue": "x"}]):
        assert T.decompose(e, "root", kid(bad), accepted_risks=REGISTER).get("refused"), bad
    T.decompose(e, "root", kid([{"from": "root.A", "glue": "x"}, {"from": "root.A", "glue": "y"}]), accepted_risks=REGISTER)
    e.wait_idle()
    assert [(str(x.from_id), x.glue) for x in e.graph.dep_edges()] == [("root.A", "y")]
    e.stop()


def test_a_read_of_the_consumer_names_what_it_waits_for():
    e = make_engine()
    e.start()
    _pair(e)
    T.add_dependency(e, "root.A", "root.B", glue="B reads A")
    assert T.get_task(e, "root.B")["deps"] == [{"from": "root.A", "glue": "B reads A"}]
    assert "criteria-content" not in T.add_dependency.__doc__ and "re-author" not in T.remove_dependency.__doc__
    e.stop()


# === critic over a39bb52: a deadline moves only where forced; every declaration is the one act; one pair, one edge ===

def test_cutting_an_edge_never_moves_a_deadline_nor_re_offers_the_consumer_at_work():
    e = make_engine()
    e.start()
    _pair(e)
    T.add_dependency(e, "root.A", "root.B", glue="B reads A")      # siblings due together: the new order forces a move
    T.signal(e, "root.B", "ACCEPT", "agent")
    e.wait_idle()
    b = e.graph.get_task(TaskId("root.B"))
    due, n = b.deadline, len(e.audit_log(TaskId("root.B")))
    out = T.remove_dependency(e, "root.A", "root.B")
    e.wait_idle()
    b = e.graph.get_task(TaskId("root.B"))
    assert (b.state.name, b.deadline, len(e.audit_log(TaskId("root.B")))) == ("EXECUTING", due, n), out
    e.stop()


def test_an_edge_written_through_a_revision_is_declared_by_the_one_act_and_keeps_check_3():
    """A bare `depends_on` entry handed to `edit_criteria`: the edge by the split's re-admission, before the version's
    deadline is read, so the order it leaves holds (CHECK-3); at a root, by its goal's issuer joining it."""
    e = make_engine()
    e.start()
    _pair(e)
    n = len(_admissions(e))
    T.edit_criteria(e, "root.B", [criterion("Bc", "B"), {"name": "dep__root.A", "description": "B reads A",
                                                          "depends_on": "root.A"}], "agent")
    e.wait_idle()
    assert _admissions(e)[n:] and _admissions(e)[-1]["deps"] == {"root.B": [["root.A", "B reads A"]]}
    a, b = (e.graph.get_task(TaskId(k)) for k in ("root.A", "root.B"))
    assert a.deadline < b.deadline
    assert {c["check"]: c["verdict"] for c in T.get_checks(e, "root")}["CHECK-3:deadlines"] != "unmet"
    T.revise(e, "root", {"description": "parent", "criteria": [criterion("g", "G"), criterion("p", "P"), {
        "name": "dep__root.A", "description": "the goal reads A", "depends_on": "root.A"}], "accepted_risks": REGISTER},
        "agent")
    assert [r["deps"] for r in json.loads(e.graph._storage.get_critique(goal_deps_key(TaskId("root"))) or "[]")] == [
        [["root.A", "the goal reads A"]]]
    e.stop()


def test_a_pair_named_by_deps_and_by_a_criterion_reading_it_is_one_edge():
    e = make_engine()
    e.start()
    _pair(e)
    T.decompose(e, "root", [{"task_id": "root.B", "deps": [{"from": "root.A", "glue": "schema"}], "assignee": "agent",
                             "covers": ["g"], "spec": {"description": "root.B", "criteria": [
                                 criterion("Bc", "root.B"), criterion("reads", "B runs A's binary", depends_on="root.A")]}}],
                accepted_risks=REGISTER)
    e.wait_idle()
    assert [str(x.from_id) for x in e.graph.dep_edges(closed=True)] == ["root.A"]
    e.stop()
