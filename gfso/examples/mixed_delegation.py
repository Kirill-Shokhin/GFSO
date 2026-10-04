"""Mixed: a human issuer, one node delegated to a REGISTERED LLM executor.

Assignment IS delegation: the dispatcher picks up the node whose Del is a registered
llm-executor, spawns a headless Claude executor with the packet, wraps its report into FSM
signals, and the registered llm-validator signs the verdict. The human keeps every other node.
SPAWNS REAL MODEL RUNS — needs the Claude Code CLI (`claude`) on PATH."""
import shutil
import sys
import tempfile
from gfso.examples import scratch
from gfso.engine import Engine
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.delegate import Dispatcher
from gfso.roster import AgentRegistry
from gfso import tools as T
import time
from gfso.config import MODEL_DEFAULT


def main() -> None:
    """Run the demo: a human issuer with one node delegated to a registered LLM executor.

    Shows that assignment IS delegation — nothing beyond Del tells the dispatcher to pick it up.
    SPAWNS A REAL MODEL RUN.
    """
    if not shutil.which("claude"):
        sys.exit("needs the Claude Code CLI on PATH (the executor/validator transport)")


    work = tempfile.mkdtemp(prefix="gfso_mixed_")
    e = Engine(store := SqliteStorage(scratch("demo.db")), HumanAgent(), llm=None,
               validate_signals=True, state_timeout=0)
    e.start()

    agents = AgentRegistry(path=scratch("agents.json"))
    agents.register("worker-1", "llm-executor", model=MODEL_DEFAULT, workdir=work)
    agents.register("checker-1", "llm-validator", workdir=work, model=MODEL_DEFAULT)

    # THE goal. A project has exactly one root — the node that carries the goal's criteria, so that
    # V(root) is the project's verdict — and the two nodes below are its children, one held by the
    # human and one delegated. They were two roots here, which is a graph with two verdicts and no
    # rule composing them.
    # Every criterion carries the procedure that will decide it (A1): a contract pins its checks before the work.
    check = lambda behaviour, command, expect: [{"behaviour": behaviour, "command": command, "expect": expect}]
    T.create_task(e, "goal", {"description": "Ship the greeting, with a brief to go with it",
                              "criteria": [{"name": "brief", "description": "the brief is written",
                                            "check": check("the brief exists", "test -s brief.txt", "exit 0")},
                                           {"name": "code", "description": "the program runs",
                                            "check": check("it greets", "python hello.py", "hello, graph")}]},
                  assignee="me")
    # The split admitted WHOLE in one act (§11.5): each child names the criterion it covers, and the split carries
    # its register — the risks its claim accepts, and its own odds of being refuted.
    T.decompose(e, "goal", [
        # the human's own node — the system stays passive on it (unregistered id = human)
        {"task_id": "brief", "assignee": "me", "covers": ["brief"],
         "spec": {"description": "Write the one-line brief", "criteria": [
             {"name": "b", "description": "brief.txt exists",
              "check": check("the brief exists", "test -s brief.txt", "exit 0")}]}},
        # the delegated node — naming a registered executor IS the delegation
        {"task_id": "impl", "assignee": "worker-1", "covers": ["code"],
         "spec": {"description": f"Create hello.py in {work} printing 'hello, graph'", "criteria": [
             {"name": "file", "description": f"{work}/hello.py exists",
              "check": check("the file exists", "test -s hello.py", "exit 0")},
             {"name": "runs", "description": "python hello.py prints 'hello, graph'",
              "check": check("it greets", "python hello.py", "hello, graph")}]}}],
        accepted_risks=[{"item": "the executor's environment lacks python", "predictability": "STATISTICAL",
                         "p": 0.02, "impact": "the delegated node cannot run its check",
                         "justification": "a stock machine ships python", "invalidation_condition": "it does not"},
                        {"denial": True, "p": 0.05, "justification": "a two-part split this small rarely fails"}])

    d = Dispatcher(e, agents)
    print("dispatching (a real executor + validator run, ~1-2 min)…")
    d.dispatch_once()
    # ESCALATED is NOT an end — it is the issuer waiting (§12.5), and this loop used to stop
    # there and never stop on ABANDONED. The ends are the settlements.
    while e.graph.get_state(T.TaskId("impl")).name not in ("DONE", "ABANDONED"):
        time.sleep(5)
        d.dispatch_once()
    print("delegated node:", e.graph.get_state(T.TaskId("impl")).name)
    print("human node still waits for the human:", e.graph.get_state(T.TaskId("brief")).name)
    e.stop()
    store.close()   # Windows keeps the .db locked until the connection closes


# Importing a module must not RUN it. Without this guard the script body executed on import,
# so anything that walks the package tree — an IDE indexer, a doc tool, a naive test
# collection, `from gfso.examples.x import y` — ran the example; for the two that spawn
# models that meant real tokens off the reader's account and, for one, an endless loop.
if __name__ == "__main__":
    main()
