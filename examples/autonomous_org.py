"""LLM-company: the fully autonomous org — no human in the loop.

`auto_decompose` authors a VERIFIED task graph from one request; the event-driven dispatcher
spawns a registered executor per free leaf (dep-gated), an independent validator signs every
delivery, and the root completes only when the whole tree is DONE/PASS — nothing completes by
impression. SPAWNS REAL MODEL RUNS (several executors + validators, ~5-10 min) — needs the
Claude Code CLI (`claude`) on PATH."""
import shutil
import sys
import tempfile
import time

if not shutil.which("claude"):
    sys.exit("needs the Claude Code CLI on PATH (the executor/validator transport)")

from gfso.engine import Engine
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.delegate import AgentRegistry, Dispatcher
from gfso import tools as T
from gfso import tools_llm as TL

work = tempfile.mkdtemp(prefix="gfso_company_")
e = Engine(SqliteStorage(tempfile.mktemp(suffix=".db")), HumanAgent(), llm=None,
           validate_signals=True, state_timeout=0)
e.start()

agents = AgentRegistry(path=tempfile.mktemp(suffix=".json"))
agents.register("exec-1", "llm-executor", model="sonnet", workdir=work)
agents.register("val-1", "llm-validator", model="sonnet")
d = Dispatcher(e, agents)

print("authoring the verified graph (auto_decompose, ~2-4 min)…")
out = TL.auto_decompose(
    e, f"A tiny python package in {work}: a slugify(text) function with edge-case handling "
       f"and a test file that passes under pytest", root_id="job", assignee="exec-1")
print("subtasks:", [s["id"] for s in out["subtasks"]], "· holes:", out["holes"])

print("running the org to completion…")
while e.get_state(T.TaskId("job")).name not in ("DONE", "ESCALATED"):
    d.dispatch_once()
    time.sleep(5)
print("root:", e.get_state(T.TaskId("job")).name)
for n in T.get_graph(e)["nodes"]:
    print(f"  {n['id']}: {n['state']}")
print("Q:", T.metrics(e))
e.stop()
