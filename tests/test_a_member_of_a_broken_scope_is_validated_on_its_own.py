"""A scope one session no longer carries — a member handed to another executor — starts its nodes as their own, each
with a session; each delivery is then validated on its own. Read off its parent's fit alone, a delivered member was
called internal, no validation started and none was owed, and it sat in VALIDATING to its timeout (tn7a14284,
2026-10-20). All with fake runners — no network."""
from gfso.core.types import AgentId, Signal, TaskId
import gfso.delegate as D
from tests.test_one_session_carries_a_scope import _LLM, _dispatcher, _drive, _project


def test_a_member_of_a_broken_scope_is_validated_on_its_own(tmp_path):
    e, agents = _project(tmp_path)
    e.reassign(TaskId("root.b"), AgentId("exec-2"))
    e.wait_idle()
    per_node: list = []
    d = _dispatcher(e, agents, _LLM(), _LLM(), per_node)
    assert d._session_scope(e.graph.get_task(TaskId("root.a"))) is None, "the scope is broken"
    _drive(e, d, lambda: ("exec", "root.a") in per_node, rounds=40)
    assert ("exec", "root.a") in per_node, "its member got a session of its own"
    D._signal(e, TaskId("root.a"), Signal.DELIVER, "exec-1", result="a.py written", self_validation="ran it: holds")
    _drive(e, d, lambda: ("validate", "root.a") in per_node, rounds=40)
    assert e.observed_here(TaskId("root.a"))
    assert ("validate", "root.a") in per_node, "its delivery is validated on its own"
    e.stop()


def test_a_member_of_a_whole_scope_is_still_its_executors_own_work(tmp_path):
    e, _ = _project(tmp_path)
    assert not e.observed_here(TaskId("root.a")) and e.observed_here(TaskId("root"))
    e.stop()
