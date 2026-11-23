"""A guarded run whose node is moved by another party during its preamble spawns no session.

The slot check (`stale`) runs when the run gets its slot; the preamble after it — entering the place, reading it,
observing its checks — takes 10-20 s under load. A node delivered or revised meanwhile is no longer in a work state
for the version the run was queued for (Inv-1, §12.3), so a session spawned on it is work nobody owes: its DELIVER is
refused ("not admitted by state VALIDATING") after it was paid for. The same check is asked again right before the
spawn. The preamble is made to block deterministically: the move happens inside the place's observation.

Control: drop the re-check before `_spawn` in `run_executor`, and the two moved cases go red.
"""
import pytest

import gfso.sessions as S
from gfso.core.types import TaskId
from gfso.delegate import Dispatcher
from gfso.sessions import run_executor
from gfso import tools as T

from tests.test_a_revised_node_does_not_run_twice import _revise
from tests.test_delegate import _AgentLLM, _agents, _eng, _fenced, _node
from tests.test_one_session_carries_a_scope import _LLM, _delivered, _project


def _deliver(e):
    T.signal(e, "t1", "DELIVER", "exec-1", result="delivered from the executor's chat")
    e.wait_idle()


@pytest.mark.parametrize("move, spawned", [(_deliver, False),
                                           (lambda e: _revise(e, "t1", "hammer a DIFFERENT nail"), False),
                                           (lambda e: None, True)], ids=["delivered", "revised", "unmoved"])
def test_a_node_moved_in_the_preamble_gets_no_session(tmp_path, monkeypatch, move, spawned):
    e = _eng()
    agents = _agents(tmp_path, ("exec-1", "llm-executor"))
    _node(e, "t1")
    llm = _AgentLLM(_fenced({"status": "delivered", "summary": "done", "self_validation": "flush: met"}))
    observed = S._observed

    def preamble(engine, node_id, *a):
        move(engine)                                  # another party, while the run reads its place
        return observed(engine, node_id, *a)
    monkeypatch.setattr(S, "_observed", preamble)

    d = Dispatcher(e, agents, runner=lambda en, tid, ex, ag: run_executor(en, tid, ex, ag, _llm=llm))
    t = e.graph.get_task(TaskId("t1"))
    d._run_guarded(TaskId("t1"), "exec-1", (t.iteration, t.reopens, t.revisions))
    e.wait_idle()
    assert bool(llm.packets) is spawned, ("a session was spawned on a node another party moved in its preamble"
                                          if not spawned else "the guard refused the round it was queued for")
    e.stop()


@pytest.mark.parametrize("moved", [(), ("root.a",), ("root", "root.a", "root.b")], ids=["unmoved", "one", "all"])
def test_a_scope_session_works_only_the_nodes_still_its_own(tmp_path, monkeypatch, moved):
    """The scope's side: each node it is about to work is asked again before the session — one another party revised
    in the preamble is not in its packet, and where none is left no session is spawned."""
    e, agents = _project(tmp_path)
    llm = _LLM(_delivered("root.a", "root.b", "root"))
    observed = S._observed

    def preamble(engine, node_id, *a):
        for k in moved:
            _revise(engine, k, f"{k}: a DIFFERENT contract")
        return observed(engine, node_id, *a)
    monkeypatch.setattr(S, "_observed", preamble)

    out = S.run_scope_executor(e, TaskId("root"), "exec-1", agents, _llm=llm)
    e.wait_idle()
    if len(moved) == 3:
        assert out["status"] == "stale" and not llm.packets, "a session was spawned with no node left to work"
    else:
        assert len(llm.packets) == 1, out
        worked = {k for k in ("root", "root.a", "root.b") if f"`{k}` — " in llm.packets[0]}
        assert worked == {"root", "root.a", "root.b"} - set(moved), ("the session was handed a node another party "
                                                                     "moved in its preamble")
    e.stop()
