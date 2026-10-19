"""Q reads its populations off the log, whatever state a node reaches later (§15.4): a declared Dep edge whose
consumer is cancelled stays in q_Dep, and a whole that passed over passed children stays in q_D after a REOPEN
(critic B1, reproduced; both were RED on main 3a9e609)."""
import pytest
import gfso.tools as T
from gfso.core.graph import metrics as M
from gfso.core.types import AgentId, Signal, SignalData, State, TaskId
from tests.support import criterion, instrument_passes, make_engine, REGISTER
from tests.test_a_part_is_checked_again_inside_its_whole import _whole_delivered_over_a_passed_part


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def S(e, sig, tid, src, **kw):
    ent = e.send_signal_sync(SignalData(signal=sig, task_id=TaskId(tid), source=AgentId(src), **kw)); e.wait_idle()
    print(f"  {tid}:{sig.name:15} rejected={bool(ent and ent.rejected)} -> {e.graph.get_state(TaskId(tid)).name}")
    return ent


def test_qdep_declared_edge_survives_consumer_cancel():
    e = make_engine(); e.start()
    try:
        T.create_task(e, "root", {"description": "g", "criteria": [criterion("c1"), criterion("c2"), criterion("c3")],
                                  "accepted_risks": REGISTER}, assignee="boss"); e.wait_idle()
        kids = [{"task_id": "a", "assignee": "wa", "covers": ["c1"], "spec": {"description": "a", "criteria": [criterion("xa")]}},
                {"task_id": "b", "assignee": "wb", "covers": ["c2"], "spec": {"description": "b", "criteria": [
                    criterion("xb"), {**criterion("dep_b"), "depends_on": "a"}]}},
                {"task_id": "c", "assignee": "wc", "covers": ["c3"], "spec": {"description": "c", "criteria": [criterion("xc")]}}]
        out = T.decompose(e, "root", kids, accepted_risks=REGISTER); e.wait_idle()
        print("decompose:", [o.get("id") if isinstance(o, dict) else o for o in (out if isinstance(out, list) else [out])])
        print("edges:", [(str(x.from_id), str(x.to_id), x.discovered) for x in e.graph.dep_edges(closed=True)])
        S(e, Signal.ACCEPT, "c", "wc")
        S(e, Signal.BLOCK, "c", "wc", reason="needs a's output", blocker_task_ids=(TaskId("a"),))
        q0 = M.q_Dep(e.graph); print("q_Dep before cancel:", q0)
        S(e, Signal.CANCEL, "b", "boss", reason="no longer needed")
        S(e, Signal.CONFIRM_CANCEL, "b", "wb", in_flight="nothing")
        q1 = M.q_Dep(e.graph); print("q_Dep after cancel:", q1)
        print("edges:", [(str(x.from_id), str(x.to_id), x.discovered) for x in e.graph.dep_edges(closed=True)])
        assert q1 == q0, "a declared edge left the declared set because its consumer was later cancelled"
    finally:
        e.stop()


def test_qdep_keeps_the_edges_a_dropped_dependency_had():
    """The machine issuer's `drop_dependency` after a producer's cancel reaches `remove_dependency`, which took the
    consumer's dep criterion and the stored record away — q_Dep then lost a declared edge (0.5 → 0.0) and a discovered
    one (→ ⊥). §15.5 removes a discovery only on an adjudication refuting it and has no clause removing a declared
    edge (critic B2, `f1_drop.py`)."""
    e = make_engine(); e.start()
    try:
        T.create_task(e, "root", {"description": "g", "criteria": [criterion("c1"), criterion("c2"), criterion("c3")],
                                  "accepted_risks": REGISTER}, assignee="boss"); e.wait_idle()
        kids = [{"task_id": "a", "assignee": "wa", "covers": ["c1"], "spec": {"description": "a", "criteria": [criterion("xa")]}},
                {"task_id": "b", "assignee": "wb", "covers": ["c2"], "spec": {"description": "b", "criteria": [
                    criterion("xb"), {**criterion("dep_b"), "depends_on": "a"}]}},
                {"task_id": "c", "assignee": "wc", "covers": ["c3"], "spec": {"description": "c", "criteria": [criterion("xc")]}}]
        T.decompose(e, "root", kids, accepted_risks=REGISTER); e.wait_idle()
        S(e, Signal.ACCEPT, "c", "wc")
        S(e, Signal.BLOCK, "c", "wc", reason="needs a's output", blocker_task_ids=(TaskId("a"),))
        S(e, Signal.CANCEL, "a", "boss", reason="producer no longer needed")
        S(e, Signal.CONFIRM_CANCEL, "a", "wa", in_flight="nothing")
        assert M.q_Dep(e.graph) == 0.5
        T.remove_dependency(e, "a", "b"); e.wait_idle()
        assert M.q_Dep(e.graph) == 0.5, "the declared edge left the population with its criterion"
        T.remove_dependency(e, "a", "c"); e.wait_idle()
        assert M.q_Dep(e.graph) == 0.5, "the discovery left the population unrefuted"
        assert not [x for x in e.graph.dep_edges(adopted=True) if str(x.to_id) in ("b", "c")], \
            "a dropped dependency is no edge of E_Dep: nothing waits on it"
    finally:
        e.stop()


def _two_with_a_dep(e):
    T.create_task(e, "root", {"description": "g", "criteria": [criterion("c1"), criterion("c2")],
                              "accepted_risks": REGISTER}, assignee="boss"); e.wait_idle()
    kids = [{"task_id": "a", "assignee": "wa", "covers": ["c1"], "spec": {"description": "a", "criteria": [criterion("xa")]}},
            {"task_id": "b", "assignee": "wb", "covers": ["c2"], "spec": {"description": "b", "criteria": [
                criterion("xb"), {**criterion("dep_b"), "depends_on": "a"}]}}]
    T.decompose(e, "root", kids, accepted_risks=REGISTER); e.wait_idle()


def test_a_block_on_a_dropped_declared_edge_waits_and_is_no_discovery():
    """a→b declared, then dropped from b's criteria; b BLOCKs naming a while a is unpassed. The BLOCK's record carries
    the wait (§11.3) — skipped once, b blocked on nothing the graph showed and a plain RESOLVE_BLOCK resumed it past an
    unpassed producer (critic 3) — and it is no discovery: a version had declared the pair before this first BLOCK
    (§15.5; read off the standing criteria q_Dep fell 1.0 → 0.0, critic 1)."""
    e = make_engine(); e.start()
    try:
        _two_with_a_dep(e)
        T.remove_dependency(e, "a", "b"); e.wait_idle()
        S(e, Signal.ACCEPT, "b", "wb")
        S(e, Signal.BLOCK, "b", "wb", reason="needs a's output after all", blocker_task_ids=(TaskId("a"),))
        assert [(str(x.from_id), str(x.to_id)) for x in e.graph.dep_edges()] == [("a", "b")]
        assert e.block_clears_itself(e.graph.get_task(TaskId("b")))
        assert M.q_Dep(e.graph) == 1.0
        ent = S(e, Signal.RESOLVE_BLOCK, "b", "boss", action="go on")
        assert ent.rejected and e.graph.get_state(TaskId("b")) == State.BLOCKED, "it resumed past an unpassed producer"
    finally:
        e.stop()


def test_a_pair_a_block_named_first_is_never_declared():
    """b BLOCKs naming a (undeclared) → the issuer refutes it → a revision declares a→b → the dependency is dropped → b
    BLOCKs naming a again. §15.5: Dep_declared is "the edges the plan declared before any BLOCK named them"; a refuted
    discovery leaves the population and "a repeated BLOCK naming it reopens it". Deleted on refutation, the record lost
    the order, and the later declaration read the second BLOCK as a declared edge (critic 2)."""
    e = make_engine(); e.start()
    try:
        T.create_task(e, "root", {"description": "g", "criteria": [criterion("c1"), criterion("c2")],
                                  "accepted_risks": REGISTER}, assignee="boss"); e.wait_idle()
        T.decompose(e, "root", [
            {"task_id": "a", "assignee": "wa", "covers": ["c1"], "spec": {"description": "a", "criteria": [criterion("xa")]}},
            {"task_id": "b", "assignee": "wb", "covers": ["c2"], "spec": {"description": "b", "criteria": [criterion("xb")]}}],
            accepted_risks=REGISTER); e.wait_idle()
        S(e, Signal.ACCEPT, "b", "wb")
        S(e, Signal.BLOCK, "b", "wb", reason="needs a", blocker_task_ids=(TaskId("a"),))
        assert M.q_Dep(e.graph) == 0.0
        S(e, Signal.RESOLVE_BLOCK, "b", "boss", action="not a's to give", external=True)
        assert M.q_Dep(e.graph) is None, "a refuted discovery is in neither half"
        T.add_dependency(e, "a", "b"); e.wait_idle()
        assert any(str(c.depends_on) == "a" for c in e.graph.get_task(TaskId("b")).spec.criteria)
        assert M.q_Dep(e.graph) is None, "declared AFTER a BLOCK named it: not declared before any BLOCK"
        T.remove_dependency(e, "a", "b"); e.wait_idle()
        if e.graph.get_state(TaskId("b")) == State.OFFERED:
            S(e, Signal.ACCEPT, "b", "wb")
        S(e, Signal.BLOCK, "b", "wb", reason="needs a after all", blocker_task_ids=(TaskId("a"),))
        assert M.q_Dep(e.graph) == 0.0, "the repeated BLOCK reopens the discovery"
    finally:
        e.stop()


def test_a_repeated_block_on_a_pair_declared_since_reopens_its_discovery():
    """b BLOCKs naming a → refuted → a revision declares a→b → b BLOCKs naming a again. The pair is declared NOW, and
    asked first, that returned before the existing record was reopened: the refutation stood and q_Dep read ⊥ where
    §15.5 gives a discovery — "a repeated BLOCK naming it reopens it" (critic 4)."""
    e = make_engine(); e.start()
    try:
        T.create_task(e, "root", {"description": "g", "criteria": [criterion("c1"), criterion("c2")],
                                  "accepted_risks": REGISTER}, assignee="boss"); e.wait_idle()
        T.decompose(e, "root", [
            {"task_id": "a", "assignee": "wa", "covers": ["c1"], "spec": {"description": "a", "criteria": [criterion("xa")]}},
            {"task_id": "b", "assignee": "wb", "covers": ["c2"], "spec": {"description": "b", "criteria": [criterion("xb")]}}],
            accepted_risks=REGISTER); e.wait_idle()
        S(e, Signal.ACCEPT, "b", "wb")
        S(e, Signal.BLOCK, "b", "wb", reason="needs a", blocker_task_ids=(TaskId("a"),))
        S(e, Signal.RESOLVE_BLOCK, "b", "boss", action="not a's to give", external=True)
        T.add_dependency(e, "a", "b"); e.wait_idle()
        if e.graph.get_state(TaskId("b")) == State.OFFERED:
            S(e, Signal.ACCEPT, "b", "wb")
        S(e, Signal.BLOCK, "b", "wb", reason="needs a after all", blocker_task_ids=(TaskId("a"),))
        assert M.q_Dep(e.graph) == 0.0
    finally:
        e.stop()


def _blocked_on_an_undeclared_a(e):
    T.create_task(e, "root", {"description": "g", "criteria": [criterion("c1"), criterion("c2")],
                              "accepted_risks": REGISTER}, assignee="boss"); e.wait_idle()
    T.decompose(e, "root", [
        {"task_id": "a", "assignee": "wa", "covers": ["c1"], "spec": {"description": "a", "criteria": [criterion("xa")]}},
        {"task_id": "b", "assignee": "wb", "covers": ["c2"], "spec": {"description": "b", "criteria": [criterion("xb")]}}],
        accepted_risks=REGISTER); e.wait_idle()
    S(e, Signal.ACCEPT, "b", "wb")
    S(e, Signal.BLOCK, "b", "wb", reason="needs a", blocker_task_ids=(TaskId("a"),))


@pytest.mark.parametrize("answer,want", [({}, 0.0), ({"external": True}, None)])
def test_a_cancel_answers_the_block_it_ends(answer, want):
    """§15.5: a discovery leaves q_Dep on its latest adjudication — "RESOLVE_BLOCK's action or a re-ASSIGN's or CANCEL's
    reason". A CANCEL out of BLOCKED carrying the refutation refutes the record; one carrying none leaves it
    unanswered, closed and counted (sync map C-q)."""
    e = make_engine(); e.start()
    try:
        _blocked_on_an_undeclared_a(e)
        S(e, Signal.CANCEL, "b", "boss", reason="no longer needed", **answer)
        assert M.q_Dep(e.graph) == want
    finally:
        e.stop()


@pytest.mark.parametrize("answer,want,adopted", [({"block_refuted": True}, None, False),
                                                 ({"block_sources": ("a",)}, 0.0, True),
                                                 ({}, 0.0, False)])
def test_a_reassign_answers_the_block_it_ends(answer, want, adopted):
    """The same for a re-ASSIGN out of BLOCKED: refuted, the record leaves q_Dep; confirmed, it is adopted into E_Dep
    as RESOLVE_BLOCK's confirmation adopts it (§11.3); unanswered, it closes and stays counted."""
    e = make_engine(); e.start()
    try:
        _blocked_on_an_undeclared_a(e)
        b = e.graph.get_task(TaskId("b"))
        e.revise(TaskId("b"), b.spec, AgentId("boss"), **answer); e.wait_idle()
        assert e.graph.get_state(TaskId("b")) == State.OFFERED
        assert M.q_Dep(e.graph) == want
        assert (("a", "b") in {(str(x.from_id), str(x.to_id)) for x in e.graph.dep_edges(adopted=True)}) == adopted
    finally:
        e.stop()


@pytest.mark.parametrize("answer", [{"block_refuted": True}, {"cancel": True}])
def test_the_issuer_answers_a_lapsed_block_from_escalated(answer):
    """A block that lapsed hands its issuer the decision at ESCALATED (§12.4, §12.5), its records closed unanswered. His
    re-ASSIGN or CANCEL there is the adjudication §15.5 reads — accepted and dropped before (critic 5)."""
    e = make_engine(); e.start()
    try:
        _blocked_on_an_undeclared_a(e)
        e.send_signal_sync(SignalData(signal=Signal.TIMEOUT, task_id=TaskId("b"), source=None)); e.wait_idle()
        assert e.graph.get_state(TaskId("b")) == State.ESCALATED and M.q_Dep(e.graph) == 0.0
        if answer.get("cancel"):
            assert not S(e, Signal.CANCEL, "b", "boss", reason="not needed", external=True).rejected
        else:
            e.revise(TaskId("b"), e.graph.get_task(TaskId("b")).spec, AgentId("boss"), **answer); e.wait_idle()
        assert M.q_Dep(e.graph) is None
    finally:
        e.stop()


def test_an_answer_to_a_block_only_where_a_block_ends_and_only_with_a_real_source():
    """Carried where no block ends, the answer was dropped while the door said success; a source naming the node or
    an ancestor was adopted as a discovery no BLOCK named (critic 5)."""
    e = make_engine(); e.start()
    try:
        _blocked_on_an_undeclared_a(e)
        for bad in ("b", "root"):
            assert S(e, Signal.CANCEL, "b", "boss", reason="x", blocker_task_ids=(TaskId(bad),)).rejected
            assert S(e, Signal.RESOLVE_BLOCK, "b", "boss", blocker_task_ids=(TaskId(bad),)).rejected
        S(e, Signal.RESOLVE_BLOCK, "b", "boss", action="a was not needed", external=True)
        assert e.graph.get_state(TaskId("b")) == State.EXECUTING
        assert S(e, Signal.CANCEL, "b", "boss", reason="x", external=True).rejected, "no block ends here"
    finally:
        e.stop()


def test_qd_pass_arm_survives_reopen():
    e = _whole_delivered_over_a_passed_part()
    try:
        instrument_passes(e, "root", "validator")
        print("PASS:", T.signal(e, "root", "PASS", "me").get("accepted"), e.graph.get_state(TaskId("root")))
        q0 = M.q_D(e.graph); print("q_D after the whole's PASS over passed children:", q0)
        print("reopen:", str(T.reopen(e, "root", "me"))[:160]); e.wait_idle()
        print("state:", e.graph.get_state(TaskId("root")))
        q1 = M.q_D(e.graph); print("q_D after REOPEN:", q1)
        assert q1 == q0
    finally:
        e.stop()
