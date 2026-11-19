"""A dependency is declared only by its consumer's issuer, and nothing of it is written before the act's refusals.

Dep is a form item of the consumer's parent split (§4.5 item 4), changed only by that split's re-admission (§11.5) — the
act of Del(parent), the consumer's issuer (§10.1). Two doors let anyone write one: a revision carrying a bare
`depends_on` entry declared its edge before the ASSIGN's own refusals, so a revision refused left the edge standing (and
one changing nothing else ran no issuer check at all); `add_dependency` and `remove_dependency` never asked who called."""
import pytest

from gfso import tools as T
from gfso.core.types import AgentId, State, TaskId
from tests.support import REGISTER, criterion, make_engine


def _split(e):
    T.create_task(e, "root", {"description": "parent", "criteria": [criterion("g", "G"), criterion("p", "P")],
                              "accepted_risks": REGISTER}, assignee="user")
    T.decompose(e, "root", [
        {"task_id": "root.prod", "spec": {"description": "producer", "criteria": [criterion("pp", "PP")]},
         "assignee": "user", "covers": ["p"]},
        {"task_id": "root.cons", "spec": {"description": "consumer", "criteria": [criterion("c", "C")]},
         "assignee": "worker", "covers": ["g"]}], accepted_risks=REGISTER)
    e.wait_idle()


def _edges(e):
    return sorted((str(x.from_id), str(x.to_id)) for x in e.graph._storage.get_dep_edges()
                  if not x.discovered and not getattr(x, "removed", False))


def _with_bare_entry(spec):
    return {"description": spec.description, "accepted_risks": list(spec.accepted_risks),
            "criteria": [{"name": c.name, "description": c.description,
                          "check": [{"behaviour": k.behaviour, "command": k.command, "expect": k.expect} for k in c.check]}
                         for c in spec.criteria] + [{"name": "reads_prod", "description": "reads prod",
                                                     "depends_on": "root.prod"}]}


@pytest.fixture
def e():
    e = make_engine()
    e.start()
    _split(e)
    yield e
    e.stop()


def test_add_dependency_from_anyone_but_the_issuer_is_refused_and_writes_nothing(e):
    with pytest.raises(ValueError, match="not the issuer of root.cons"):
        T.add_dependency(e, "root.prod", "root.cons", glue="cons reads prod", agent="worker")
    assert _edges(e) == []
    T.add_dependency(e, "root.prod", "root.cons", glue="cons reads prod", agent="user")
    assert _edges(e) == [("root.prod", "root.cons")]


def test_remove_dependency_from_anyone_but_the_issuer_is_refused(e):
    T.add_dependency(e, "root.prod", "root.cons", glue="cons reads prod", agent="user")
    with pytest.raises(ValueError, match="not the issuer of root.cons"):
        T.remove_dependency(e, "root.prod", "root.cons", agent="intruder")
    assert _edges(e) == [("root.prod", "root.cons")]
    T.remove_dependency(e, "root.prod", "root.cons", agent="user")
    assert _edges(e) == []


@pytest.mark.parametrize("deadline", [None, "+1d"])
def test_a_revision_with_a_bare_entry_from_an_intruder_leaves_no_edge(e, deadline):
    """Edges alone, and edges beside a packet change: both refused before anything is written."""
    spec = e.graph.get_task(TaskId("root.cons")).spec
    with pytest.raises(ValueError, match="not the issuer"):
        e.revise(TaskId("root.cons"), _engine_spec(_with_bare_entry(spec)), AgentId("intruder"),
                 **({"max_iterations": 5} if deadline else {}))
    assert _edges(e) == []


def test_the_issuers_revision_with_a_bare_entry_declares_the_edge(e):
    spec = e.graph.get_task(TaskId("root.cons")).spec
    e.revise(TaskId("root.cons"), _engine_spec(_with_bare_entry(spec)), AgentId("user"))
    assert _edges(e) == [("root.prod", "root.cons")]


def test_a_revision_refused_by_its_own_rule_leaves_no_edge(e):
    """The issuer's revision that a rule above the FSM refuses (a contract pinning nothing) writes no edge either."""
    spec = e.graph.get_task(TaskId("root.cons")).spec
    hollow = {"description": spec.description, "criteria": [{"name": "c", "description": "C"},
                                                            {"name": "reads_prod", "description": "reads prod",
                                                             "depends_on": "root.prod"}]}
    with pytest.raises(ValueError):
        e.revise(TaskId("root.cons"), _engine_spec(hollow), AgentId("user"), max_iterations=5)
    assert _edges(e) == []


def _engine_spec(d):
    return T._spec_from(d)


def test_a_revision_whose_split_cannot_take_its_edge_changes_nothing(e):
    """The edge is declared by a re-admission of the consumer's parent split, which a node no longer live refuses (§12.7)
    — read before the ASSIGN, so the refusal leaves the contract as it was, not rewritten with its edge missing."""
    root = e._graph.get_task(TaskId("root"))
    root.state = State.CANCELLING
    e._graph.save_task(root)
    spec = e.graph.get_task(TaskId("root.cons")).spec
    rewritten = {**_with_bare_entry(spec), "description": "rewritten"}
    with pytest.raises(ValueError):
        e.revise(TaskId("root.cons"), _engine_spec(rewritten), AgentId("user"))
    assert e.graph.get_task(TaskId("root.cons")).spec.description == "consumer"
    assert _edges(e) == []
