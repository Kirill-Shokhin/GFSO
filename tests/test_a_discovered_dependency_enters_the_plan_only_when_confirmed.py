"""A discovered dependency enters E_Dep only on its issuer's confirmation, and not at all if it closes a cycle.

§11.3/§15.5: a BLOCK records a PROVISIONAL edge, adopted into E_Dep only on confirmation; a confirmed discovery
that would close a Dep cycle is not adopted — it refutes the plan's ordering, which only a re-decomposition
restores — and it still counts in q_Dep. The engine ran CHECK-2 over every record, so a BLOCK naming two siblings
that already consumed the blocked node froze every sibling of a live AUTO run (json_parser, 2026-09-25).

CONTROL: let `dep_edges(adopted=True)` keep provisional or cycle-closing records and the first two tests go red.
"""
from gfso import issuer as I
from gfso import tools as T
from gfso.core.graph import q_Dep
from gfso.core.graph.model import dep_order_refutations
from gfso.core.types import TaskId
from tests.support import criterion, make_engine, reviewer_passes, REGISTER


def _plan():
    """root -> {a, b, c}; b consumes a (declared)."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "root", "criteria": [criterion("g", "G")]}, assignee="agent")
    T.decompose(e, "root", [{"task_id": k, "spec": {"description": k, "criteria": [criterion("k" + k, k.upper())]},
                             "assignee": "worker", "covers": ["g"]} for k in ("a", "b", "c")],
                accepted_risks=REGISTER)       # the split admitted whole, its register its decomposer's (§11.5, §9.2)
    T.add_dependency(e, "a", "b", glue="b reads a")
    e.wait_idle()
    return e


def _pairs(edges):
    return {(str(x.from_id), str(x.to_id)) for x in edges}


def test_a_blocks_provisional_record_is_not_an_edge_of_the_plan():
    e = _plan()
    T.signal(e, "a", "ACCEPT", "worker")
    T.signal(e, "a", "BLOCK", "worker", reason="a needs b", blocker_task_ids=["b"])
    e.wait_idle()
    assert ("b", "a") in _pairs(e.get_dependencies())                  # recorded — q_Dep counts it
    assert ("b", "a") not in _pairs(e._graph.dep_edges(adopted=True))       # …and not adopted
    assert not [h for h in T.list_holes(e)["holes"] if h["check"].startswith("CHECK-2")]
    assert _pairs(dep_order_refutations(e._graph)) == {("b", "a")}
    # …asked of the BLOCK's owner, the blocked node's issuer (Inv-8) — not of the split as a reshape
    assert "`a` needs `b`" in (e.order_refuted_by(TaskId("a")) or "") and e.dep_order_refuted(TaskId("root")) is None
    assert (TaskId("a"), "external") in I.open_questions(e)
    e.stop()


def test_a_confirmed_discovery_that_closes_a_cycle_is_not_adopted_and_still_counts():
    e = _plan()
    e.add_dependency(TaskId("b"), TaskId("a"), discovered=True, glue="a needs b")   # a confirmed record
    e.wait_idle()
    assert ("b", "a") not in _pairs(e._graph.dep_edges(adopted=True))
    assert _pairs(dep_order_refutations(e._graph)) == {("b", "a")}
    assert q_Dep(e._graph) is not None and q_Dep(e._graph) < 1.0
    assert "`a` needs `b`" in (e.dep_order_refuted(TaskId("root")) or "")
    e.stop()


def test_a_confirmed_discovery_that_closes_no_cycle_is_adopted():
    """The negative control: confirmation is what adopts, and it does."""
    e = _plan()
    e.add_dependency(TaskId("a"), TaskId("c"), discovered=True, glue="c needs a")
    e.wait_idle()
    assert ("a", "c") in _pairs(e._graph.dep_edges(adopted=True))
    assert not dep_order_refutations(e._graph) and e.dep_order_refuted(TaskId("root")) is None
    e.stop()


def test_a_refuted_order_stops_asking_once_its_block_no_longer_stands():
    """A provisional record asks only while the BLOCK that made it stands. Read as standing forever, a re-ASSIGN
    of the blocked node left the split's issuer a repair question no move could close on a finished split, and the
    machine issuer's bounded settles would have cancelled the goal (critic, 2026-09-27). It stays counted."""
    e = _plan()
    T.signal(e, "a", "ACCEPT", "worker")
    T.signal(e, "a", "BLOCK", "worker", reason="a needs b", blocker_task_ids=["b"])
    e.wait_idle()
    assert e.order_refuted_by(TaskId("a"))
    a = e.graph.get_task(TaskId("a"))
    e.revise(TaskId("a"), a.spec, e.graph.issuer_of(TaskId("a")), reason=None)     # re-presented, nothing adjudicated
    e.wait_idle()
    assert e.graph.get_task(TaskId("a")).state.name == "OFFERED"
    assert e.order_refuted_by(TaskId("a")) is None
    assert ("b", "a") not in _pairs(e.get_dependencies())                     # it waits on nothing now…
    closed = [x for x in e._graph.dep_edges(closed=True) if (str(x.from_id), str(x.to_id)) == ("b", "a")]
    assert closed and closed[0].closed and not closed[0].provisional        # …and q_Dep still counts it
    # …and the node's NEXT block is not blamed on it (critic, 2026-09-27)
    T.signal(e, "a", "ACCEPT", "worker")
    T.signal(e, "a", "BLOCK", "worker", reason="a needs c", blocker_task_ids=["c"])
    e.wait_idle()
    assert e.order_refuted_by(TaskId("a")) is None and e.block_clears_itself(e.graph.get_task(TaskId("a")))
    e.stop()


def test_two_blocks_naming_each_other_are_a_refuted_order_though_no_seam_was_declared():
    """Read over E_Dep alone the pair was asked by nobody until BLOCKED's bound: the issuer had no question and
    the dispatcher nothing to confirm (critic, 2026-09-27). The waits are E_Dep AND the standing records."""
    e = _plan()
    for me, other in (("a", "c"), ("c", "a")):
        T.signal(e, me, "ACCEPT", "worker")
        T.signal(e, me, "BLOCK", "worker", reason=f"{me} needs {other}", blocker_task_ids=[other])
    e.wait_idle()
    assert "`a` needs `c`" in (e.order_refuted_by(TaskId("a")) or "")
    assert "`c` needs `a`" in (e.order_refuted_by(TaskId("c")) or "")
    assert {(TaskId("a"), "external"), (TaskId("c"), "external")} <= set(I.open_questions(e))
    e.stop()


def test_a_block_naming_its_own_parent_is_asked_of_its_issuer():
    """The parent's PASS waits on this child (Thm 1): a child waiting on its parent waits forever."""
    e = _plan()
    T.signal(e, "c", "ACCEPT", "worker")
    T.signal(e, "c", "BLOCK", "worker", reason="c needs the whole", blocker_task_ids=["root"])
    e.wait_idle()
    assert "`c` needs `root`" in (e.order_refuted_by(TaskId("c")) or "")
    assert (TaskId("c"), "external") in I.open_questions(e)
    e.stop()


def test_a_repeat_block_on_producers_already_passed_is_its_issuers_question_not_a_paid_loop():
    """The dispatcher confirmed such a block again and again, each time a paid executor run that blocked once more
    (critic, 2026-09-27): once one block of the contract was resolved, a block on passed producers is asked."""
    e = _plan()
    T.signal(e, "a", "ACCEPT", "worker")
    T.signal(e, "a", "DELIVER", "worker", result="a done")
    reviewer_passes(e, TaskId("a"))
    T.signal(e, "a", "PASS", str(e.graph.issuer_of(TaskId("a"))))
    T.signal(e, "c", "ACCEPT", "worker")
    T.signal(e, "c", "BLOCK", "worker", reason="c needs a", blocker_task_ids=["a"])
    e.wait_idle()
    assert e.block_clears_itself(e.graph.get_task(TaskId("c")))                 # the first: a's result, never read
    T.signal(e, "c", "RESOLVE_BLOCK", str(e.graph.issuer_of(TaskId("c"))), action="confirm")
    T.signal(e, "c", "BLOCK", "worker", reason="c still needs a", blocker_task_ids=["a"])
    e.wait_idle()
    assert not e.block_clears_itself(e.graph.get_task(TaskId("c")))
    assert (TaskId("c"), "external") in I.open_questions(e)
    e.stop()


def _pass(e, k):
    T.signal(e, k, "ACCEPT", "worker")
    T.signal(e, k, "DELIVER", "worker", result=f"{k} done")
    reviewer_passes(e, TaskId(k))
    T.signal(e, k, "PASS", str(e.graph.issuer_of(TaskId(k))))
    e.wait_idle()


def test_the_machine_issuer_answers_a_block_that_names_what_cannot_come_first():
    """The BLOCK is its node's issuer's (Inv-8): refuting what it names retracts the record and the node resumes —
    no child is dropped for an executor's wrong claim (critic, 2026-09-27: only a reshape could lift it)."""
    e = _plan()
    T.signal(e, "a", "ACCEPT", "worker")
    T.signal(e, "a", "BLOCK", "worker", reason="a needs b", blocker_task_ids=["b"])
    e.wait_idle()
    ok, why = I.apply_move(e, TaskId("a"), "external", str(e.graph.issuer_of(TaskId("a"))),
                           {"move": "resolve_block", "justification": "a's contract does not read b"})
    e.wait_idle()
    assert ok, why
    assert e.graph.get_task(TaskId("a")).state.name == "EXECUTING"
    assert ("b", "a") not in _pairs(e.get_dependencies())            # refuted: an adjudication, not counted
    e.stop()


def test_a_wait_on_a_finished_producer_is_over():
    """A cycle through a DONE node waits on nothing: c already passed, so a's block on it clears itself."""
    e = _plan()
    _pass(e, "c")
    e.add_dependency(TaskId("a"), TaskId("c"), discovered=True, glue="c reads a")    # a confirmed wait a → c
    T.signal(e, "a", "ACCEPT", "worker")
    T.signal(e, "a", "BLOCK", "worker", reason="a needs c's output", blocker_task_ids=["c"])
    e.wait_idle()
    assert e.order_refuted_by(TaskId("a")) is None
    assert e.block_clears_itself(e.graph.get_task(TaskId("a")))
    e.stop()


def test_a_block_closed_unanswered_does_not_hold_the_nodes_next_block():
    """Read as live by the dispatcher and the RESOLVE_BLOCK rule, the closed record held the re-issued node's next
    block on a producer it no longer names — nobody asked, the issuer's own RESOLVE refused (critic, 2026-09-27)."""
    e = _plan()
    T.signal(e, "a", "ACCEPT", "worker")
    T.signal(e, "a", "BLOCK", "worker", reason="a needs b", blocker_task_ids=["b"])
    e.wait_idle()
    a = e.graph.get_task(TaskId("a"))
    e.revise(TaskId("a"), a.spec, e.graph.issuer_of(TaskId("a")), reason=None)
    _pass(e, "c")
    T.signal(e, "a", "ACCEPT", "worker")
    T.signal(e, "a", "BLOCK", "worker", reason="a needs c", blocker_task_ids=["c"])
    e.wait_idle()
    out = T.signal(e, "a", "RESOLVE_BLOCK", str(e.graph.issuer_of(TaskId("a"))), action="confirm")
    assert out.get("accepted"), out
    e.stop()


def test_a_block_held_to_after_it_was_refuted_is_the_splits_question():
    """The executor re-raised what its issuer refuted: the report is not what stands refuted — the plan's order is,
    and only the split's issuer can reshape it (critic, 2026-09-27: each refute bought another paid run)."""
    e = _plan()
    issuer = str(e.graph.issuer_of(TaskId("a")))
    T.signal(e, "a", "ACCEPT", "worker")
    T.signal(e, "a", "BLOCK", "worker", reason="a needs b", blocker_task_ids=["b"])
    e.wait_idle()
    assert I.apply_move(e, TaskId("a"), "external", issuer, {"move": "resolve_block", "justification": "no"})[0]
    T.signal(e, "a", "BLOCK", "worker", reason="a really needs b", blocker_task_ids=["b"])
    e.wait_idle()
    qs = set(I.open_questions(e))
    assert (TaskId("root"), "repair") in qs and (TaskId("a"), "external") not in qs
    assert "`a` needs `b`" in (e.dep_order_refuted(TaskId("root")) or "")
    e.stop()


def test_what_a_reader_is_told_about_a_block_no_wait_ends():
    """`get_task` told the executor "when they pass, the block clears by itself" for a block on what cannot finish
    before it, and the Level-2 review read an unanswered BLOCK as "ground truth" (critic, 2026-09-27)."""
    e = _plan()
    T.signal(e, "a", "ACCEPT", "worker")
    T.signal(e, "a", "BLOCK", "worker", reason="a needs b", blocker_task_ids=["b"])
    e.wait_idle()
    told = T.get_task(e, "a")["blocked_by"]["what_now"]
    assert "clears by itself" not in told and "its issuer answers it" in told, told
    seams = e.project(TaskId("root"))
    assert "ground truth" not in seams and "not yet answered by its issuer" in seams
    e.stop()


def test_a_root_blocked_on_itself_stays_its_issuers_question_after_an_answer():
    """No split sits above a root: once one block of its contract was answered, the next one went to a split that
    does not exist and was asked of nobody (critic, 2026-09-27)."""
    e = _plan()
    T.signal(e, "root", "ACCEPT", "agent")
    for _ in range(2):
        T.signal(e, "root", "BLOCK", "agent", reason="the goal needs itself", blocker_task_ids=["root"])
        e.wait_idle()
        assert (TaskId("root"), "external") in I.open_questions(e)
        T.signal(e, "root", "RESOLVE_BLOCK", str(e.graph.issuer_of(TaskId("root"))), external=True)
        e.wait_idle()
    e.stop()
