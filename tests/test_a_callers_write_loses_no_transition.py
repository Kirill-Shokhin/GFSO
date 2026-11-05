"""The log's pump writes a node's state; a verb on a caller's thread writes one field of the same row. Read, then written whole
(`INSERT OR REPLACE`), the caller's copy put back the state the pump had moved meanwhile: a PASS in the log, a DONE lost from
the node. Forced here on the real store, with the transition stepped between the caller's read and its write."""
import threading

import pytest

from gfso import tools as T
from gfso.adapters.llm.stub import StubLLM
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.core.types import AgentId, Signal, SignalData, State, TaskId
from gfso.critic.runner import review_decomposition
from tests.support import REGISTER, REGISTER_SPLIT, criterion, instrument_passes, make_engine

ROOT = TaskId("root")


def _graph(tmp_path):
    e = make_engine(storage=SqliteStorage(str(tmp_path / "g.db")), llm=StubLLM(), validate_signals=True, state_timeout=0)
    e.start()
    e.record_root_issuer(ROOT, AgentId("agent"))
    T.create_task(e, "root", {"description": "the goal", "criteria": [criterion("g", "G"), criterion("h", "H")]},
                  assignee="exec-1")
    T.decompose(e, "root", [{"task_id": t, "assignee": "exec-2", "covers": [c], "spec": {
        "description": f"part {t}", "criteria": [criterion(f"{t}k", "K")]}} for t, c in (("a", "g"), ("b", "h"))],
        accepted_risks=REGISTER)
    e.wait_idle()
    assert "error" not in (o := T.signal(e, "root", "ACCEPT", "exec-1")), o
    return e


def _deliver(e):
    assert "error" not in (o := T.signal(e, "root", "DELIVER", "exec-1", result="out")), o
    e.wait_idle()


def _pass(e):
    assert "error" not in (o := T.signal(e, "root", "PASS", "agent")), o
    e.wait_idle()


def _step_before_the_write(e, move):
    """The caller's next write of the root, past whatever it read: `move` first, on the pump."""
    store, armed, caller = e.graph._storage, [1], threading.current_thread()

    def wrap(write):
        def writing(task, *a, **k):
            if armed and str(getattr(task, "id", task)) == "root" and threading.current_thread() is caller:
                armed.clear()
                move(e)
            return write(task, *a, **k)
        return writing

    for name in ("save_task", "update_task"):
        if hasattr(store, name):
            setattr(store, name, wrap(getattr(store, name)))
    return armed


def _map(e):
    assert "error" not in str(T.map_criterion(e, "root", "a", "h")), "the verb refused"
    assert {(m.criterion_name, str(m.child_id)) for m in e.graph.get_task(ROOT).criterion_mappings} >= {("h", "a")}


def _register(e):
    e.admit_register(ROOT, REGISTER_SPLIT.__class__(REGISTER_SPLIT.items, ("a component",)), AgentId("exec-1"))
    assert e.graph.get_task(ROOT).register.components == ("a component",)


def _stale_review(e):
    e._recompute_checks(ROOT)
    assert e.graph.get_task(ROOT).verified is False


def _review(e):
    review_decomposition(e, ROOT, StubLLM())
    e.wait_idle()


SITES = {"mapping": _map, "register": _register, "a stale review": _stale_review, "a review": _review}


def test_the_stores_read_and_write_of_a_field_are_one_step(tmp_path):
    """The pump sent off between the field's read and its write: it waits on the store's lock, whichever way the wait goes
    it lands after, and the bounded wait here only gives it the chance to land first where nothing holds it."""
    e = _graph(tmp_path)
    store, moved = e.graph._storage._s, threading.Event()
    write, armed = store.save_task, [threading.current_thread()]
    e.on_transition(lambda tid=None, old=None, new=None, signal=None: moved.set() if new == State.VALIDATING else None)

    def writing(task):
        if armed and threading.current_thread() is armed[0]:
            armed.clear()
            e.send_signal(SignalData(signal=Signal.DELIVER, task_id=ROOT, source=AgentId("exec-1"), result="out"))
            moved.wait(0.5)
        write(task)

    store.save_task = writing
    try:
        e.graph.update_task(ROOT, verified=True)
        e.wait_idle()
        t = e.graph.get_task(ROOT)
        assert not armed and t.state == State.VALIDATING and t.verified is True, (t.state, t.verified)
    finally:
        e.stop()


@pytest.mark.parametrize("site", SITES)
@pytest.mark.parametrize("move,before,after", [(_deliver, None, State.VALIDATING), (_pass, _deliver, State.DONE)],
                         ids=["DELIVER", "PASS"])
def test_a_field_written_beside_a_transition_keeps_it(tmp_path, site, move, before, after):
    e = _graph(tmp_path)
    try:
        if before:
            before(e)
            instrument_passes(e, ROOT)
        if site == "a stale review":                 # …the setup's own write is not the one under test
            t = e.graph.get_task(ROOT)
            t.verified = True
            e.graph.save_task(t)
        armed = _step_before_the_write(e, move)
        SITES[site](e)
        assert not armed, "the verb wrote nothing of the root: the interleaving did not happen"
        e.wait_idle()
        assert e.graph.get_state(ROOT) == after, (site, e.graph.get_state(ROOT))
    finally:
        e.stop()
