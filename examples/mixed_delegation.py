"""Mixed: a human issuer, one node delegated to a REGISTERED LLM executor.

Assignment IS delegation: the dispatcher picks up the node whose Del is a registered
llm-executor, spawns a headless Claude executor with the packet, wraps its report into FSM
signals, and the registered llm-validator signs the verdict. The human keeps every other node.
SPAWNS REAL MODEL RUNS — needs the Claude Code CLI (`claude`) on PATH."""
import shutil
import sys
import tempfile

if not shutil.which("claude"):
    sys.exit("needs the Claude Code CLI on PATH (the executor/validator transport)")

from gfso.engine import Engine
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.delegate import AgentRegistry, Dispatcher
from gfso import tools as T

work = tempfile.mkdtemp(prefix="gfso_mixed_")
e = Engine(SqliteStorage(tempfile.mktemp(suffix=".db")), HumanAgent(), llm=None,
           validate_signals=True, state_timeout=0)
e.start()

agents = AgentRegistry(path=tempfile.mktemp(suffix=".json"))
agents.register("worker-1", "llm-executor", model="sonnet", workdir=work)
agents.register("checker-1", "llm-validator", model="sonnet")

# the human's own node — the system stays passive on it (unregistered id = human)
T.create_task(e, "brief", {"description": "Write the one-line brief",
                           "criteria": [{"name": "b", "description": "brief.txt exists"}]},
              assignee="me")
# the delegated node — naming a registered executor IS the delegation
T.create_task(e, "impl", {
    "description": f"Create hello.py in {work} printing 'hello, graph'",
    "criteria": [{"name": "file", "description": f"{work}/hello.py exists"},
                 {"name": "runs", "description": "python hello.py prints 'hello, graph'"}]},
    assignee="worker-1")

d = Dispatcher(e, agents)
print("dispatching (a real executor + validator run, ~1-2 min)…")
d.dispatch_once()
import time
while e.get_state(T.TaskId("impl")).name not in ("DONE", "ESCALATED"):
    time.sleep(5)
    d.dispatch_once()
print("delegated node:", e.get_state(T.TaskId("impl")).name)
print("human node still waits for the human:", e.get_state(T.TaskId("brief")).name)
e.stop()
