"""next_step — the execution forcing-point. Driven deterministically (no LLM): a scripted 'agent' does
exactly what each directive says via real signals, and the graph must reach COMPLETE with children fully
done before the parent aggregates. Proves the linearization + the completion gate — not a mock."""
from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.llm.stub import StubLLM
from gfso.core.types import TaskId, AgentId, Spec, Criteria, CriterionMapping, Signal, SignalData


def _sp(d, *c):
    return Spec(d, tuple(Criteria(n, t) for n, t in c))


def _drive(e: Engine, root: TaskId, agent: AgentId, max_steps: int = 50):
    """Loop next_step; perform each directive via real signals (execute/deliver = self-report). Returns the
    ordered list of (action, task_id) taken."""
    order = []
    for _ in range(max_steps):
        s = e.next_step(root)
        if s.get("complete"):
            return order
        assert not s.get("stuck"), s
        tid = TaskId(s["task_id"])
        order.append((s["action"], s["task_id"]))
        if s["action"] == "accept":
            e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=tid, source=agent))
        elif s["action"] in ("execute", "deliver", "rework"):
            e.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=tid, source=agent, result="ok"))
        elif s["action"] == "validate":
            e.send_signal_sync(SignalData(signal=Signal.PASS, task_id=tid, source=agent))
        e.wait_idle()
    raise AssertionError(f"did not complete in {max_steps} steps; order={order}")


def test_next_step_drives_to_completion_children_before_parent():
    A = AgentId("exec")
    e = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=False)
    e.start()
    # root accepted + decomposed into two leaf children
    e.assign_task(TaskId("root"), _sp("root", ("ra", "a"), ("rb", "b")), A); e.wait_idle()
    e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("root"), source=A)); e.wait_idle()
    e.decompose_task(TaskId("root"),
                     [(TaskId("a"), _sp("a", ("x", "x")), A), (TaskId("b"), _sp("b", ("y", "y")), A)],
                     [CriterionMapping("ra", TaskId("a")), CriterionMapping("rb", TaskId("b"))]); e.wait_idle()

    order = _drive(e, TaskId("root"), A)

    assert e.next_step(TaskId("root"))["complete"]                    # reached COMPLETE
    assert e.get_state(TaskId("root")).name == "DONE"
    # children fully done BEFORE the parent aggregates (deliver)
    root_deliver = next(i for i, (a, t) in enumerate(order) if t == "root" and a == "deliver")
    last_a = max(i for i, (a, t) in enumerate(order) if t == "a")
    last_b = max(i for i, (a, t) in enumerate(order) if t == "b")
    assert last_a < root_deliver and last_b < root_deliver
    # every child reached validate before that
    assert ("validate", "a") in order and ("validate", "b") in order


def test_next_step_gate_blocks_early_completion():
    """While any node is unfinished, next_step never reports complete (the agent cannot stop early)."""
    A = AgentId("exec")
    e = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=False)
    e.start()
    e.assign_task(TaskId("root"), _sp("root", ("ra", "a")), A); e.wait_idle()
    e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("root"), source=A)); e.wait_idle()
    e.decompose_task(TaskId("root"), [(TaskId("a"), _sp("a", ("x", "x")), A)],
                     [CriterionMapping("ra", TaskId("a"))]); e.wait_idle()
    # child still in REVIEW → not complete, directive points at the child
    s = e.next_step(TaskId("root"))
    assert not s.get("complete")
    assert s["task_id"] == "a" and s["action"] == "accept"


def test_next_step_respects_dependency_order():
    """A consumer leaf is not offered for EXECUTE until its producer has PASSED — next_step linearizes by the
    Dep edges, not just by tree position (BUG-5)."""
    A = AgentId("exec")
    e = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=False)
    e.start()
    e.assign_task(TaskId("root"), _sp("root", ("ra", "a"), ("rb", "b")), A); e.wait_idle()
    e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("root"), source=A)); e.wait_idle()
    b_spec = Spec("b", (Criteria("y", "y"), Criteria("dep__a", "needs a's output", depends_on=TaskId("a"))))
    e.decompose_task(TaskId("root"),
                     [(TaskId("a"), _sp("a", ("x", "x")), A), (TaskId("b"), b_spec, A)],
                     [CriterionMapping("ra", TaskId("a")), CriterionMapping("rb", TaskId("b"))]); e.wait_idle()
    for cid in ("a", "b"):  # both EXECUTING leaves now
        e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId(cid), source=A)); e.wait_idle()

    assert e.next_step(TaskId("root"))["task_id"] == "a"              # producer first — b is dep-gated
    e.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("a"), source=A, result="ok")); e.wait_idle()
    e.send_signal_sync(SignalData(signal=Signal.PASS, task_id=TaskId("a"), source=A)); e.wait_idle()
    assert e.next_step(TaskId("root"))["task_id"] == "b"              # a PASSED → consumer b unblocked


def test_next_step_re_accepts_reauthored_parent_first():
    """A re-authored parent drops back to REVIEW with its subtree retained → next_step RE-ACCEPTs it before
    driving the children (obs: else the graph finished all children while the root still showed 'accept')."""
    A = AgentId("exec")
    e = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=False)
    e.start()
    e.assign_task(TaskId("root"), _sp("root", ("ra", "a")), A); e.wait_idle()
    e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("root"), source=A)); e.wait_idle()
    e.decompose_task(TaskId("root"), [(TaskId("a"), _sp("a", ("x", "x")), A)],
                     [CriterionMapping("ra", TaskId("a"))]); e.wait_idle()
    e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("a"), source=A)); e.wait_idle()  # a EXECUTING
    e.reneglect(TaskId("root"), (), A); e.wait_idle()               # re-author → root back to REVIEW, child kept
    s = e.next_step(TaskId("root"))
    assert s["task_id"] == "root" and s["action"] == "accept"       # re-accept parent BEFORE its child executes


def test_next_step_no_graph_and_complete():
    e = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=False)
    e.start()
    assert e.next_step()["complete"] is False                         # empty → not complete, asks to build
    A = AgentId("exec")
    e.assign_task(TaskId("solo"), _sp("solo", ("c", "c")), A); e.wait_idle()
    _drive(e, TaskId("solo"), A)                                       # a single leaf node drives to done
    assert e.next_step(TaskId("solo"))["complete"]


def test_next_steps_parallel_frontier():
    """v2: next_steps returns the FULL frontier; independent execute-leaves are marked parallel_ok, a
    dep-gated consumer is NOT offered, and the frontier shrinks/unblocks as producers PASS."""
    A = AgentId("exec")
    e = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=False)
    e.start()
    e.assign_task(TaskId("root"), _sp("root", ("ra", "a"), ("rb", "b"), ("rc", "c")), A); e.wait_idle()
    e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("root"), source=A)); e.wait_idle()
    # a and b are independent leaves; c consumes a's output (dep-gated until a PASSES)
    c_spec = Spec("c", (Criteria("z", "z"), Criteria("dep__a", "needs a", depends_on=TaskId("a"))))
    e.decompose_task(TaskId("root"),
                     [(TaskId("a"), _sp("a", ("x", "x")), A), (TaskId("b"), _sp("b", ("y", "y")), A),
                      (TaskId("c"), c_spec, A)],
                     [CriterionMapping("ra", TaskId("a")), CriterionMapping("rb", TaskId("b")),
                      CriterionMapping("rc", TaskId("c"))]); e.wait_idle()
    for cid in ("a", "b", "c"):
        e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId(cid), source=A)); e.wait_idle()

    fr = e.next_steps(TaskId("root"))
    assert not fr["complete"]
    by_id = {s["task_id"]: s for s in fr["steps"]}
    # a and b: independent execute-leaves, offered together, parallel-safe
    assert by_id["a"]["action"] == "execute" and by_id["a"]["parallel_ok"]
    assert by_id["b"]["action"] == "execute" and by_id["b"]["parallel_ok"]
    assert "c" not in by_id                                   # dep-gated: producer a has not PASSED

    # finish a → c joins the frontier; b still there
    e.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("a"), source=A, result="ok")); e.wait_idle()
    e.send_signal_sync(SignalData(signal=Signal.PASS, task_id=TaskId("a"), source=A)); e.wait_idle()
    by_id = {s["task_id"]: s for s in e.next_steps(TaskId("root"))["steps"]}
    assert by_id["c"]["action"] == "execute" and by_id["c"]["parallel_ok"]
    assert by_id["b"]["action"] == "execute"


def test_next_steps_orders_issuer_actions_before_executes():
    """Non-execute steps (validate) come ahead of execute-leaves in the frontier ordering (priority)."""
    A = AgentId("exec")
    e = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=False)
    e.start()
    e.assign_task(TaskId("root"), _sp("root", ("ra", "a"), ("rb", "b")), A); e.wait_idle()
    e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId("root"), source=A)); e.wait_idle()
    e.decompose_task(TaskId("root"),
                     [(TaskId("a"), _sp("a", ("x", "x")), A), (TaskId("b"), _sp("b", ("y", "y")), A)],
                     [CriterionMapping("ra", TaskId("a")), CriterionMapping("rb", TaskId("b"))]); e.wait_idle()
    for cid in ("a", "b"):
        e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId(cid), source=A)); e.wait_idle()
    # a delivers → VALIDATING; frontier = validate(a) BEFORE execute(b)
    e.send_signal_sync(SignalData(signal=Signal.DELIVER, task_id=TaskId("a"), source=A, result="ok")); e.wait_idle()
    steps = e.next_steps(TaskId("root"))["steps"]
    actions = [(s["action"], s["task_id"]) for s in steps]
    assert actions.index(("validate", "a")) < actions.index(("execute", "b"))
    assert not steps[0]["parallel_ok"]                       # validate is issuer-side, not a parallel leaf


def test_frontier_is_del_aware(monkeypatch):
    """Del is REAL on the frontier: with GFSO_AGENT_ID set, my nodes carry mine=true; a node assigned to
    someone else is VISIBLE but its executor-step directive is hands-off — and the FSM would reject my
    executor signal on it anyway (source ≠ Del)."""
    from gfso import tools as T
    from gfso.engine import Engine
    from gfso.adapters.storage.memory import MemoryStorage
    from gfso.adapters.agents.human import HumanAgent
    from gfso.adapters.llm.stub import StubLLM

    e = Engine(MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=True)
    e.start()
    monkeypatch.setenv("GFSO_AGENT_ID", "claude-main")
    T.create_task(e, "mine1", {"description": "agent node",
                               "criteria": [{"name": "a", "description": "A"}]})          # Del=claude-main
    T.create_task(e, "his1", {"description": "human node",
                              "criteria": [{"name": "b", "description": "B"}]}, assignee="kirill")
    steps = T.next_steps(e)["steps"]
    by_id = {s["task_id"]: s for s in steps}
    assert by_id["mine1"]["mine"] is True and by_id["mine1"]["assignee"] == "claude-main"
    assert by_id["his1"]["mine"] is False and "NOT YOURS" in by_id["his1"]["directive"]
    # the FSM enforces it, not just the directive: my ACCEPT on his node is REJECTED
    r = T.signal(e, "his1", "ACCEPT", "claude-main")
    assert r["accepted"] is False and "not executor" in r["error"]
    # and the rightful executor passes
    assert T.signal(e, "his1", "ACCEPT", "kirill")["state"] == "EXECUTING"
    e.stop()
