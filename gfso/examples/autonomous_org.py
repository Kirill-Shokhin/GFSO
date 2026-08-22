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
from gfso.examples import scratch
from gfso.engine import Engine
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.delegate import AgentRegistry, Dispatcher
from gfso import tools as T
from gfso import tools_llm as TL
from gfso.config import MODEL_DEFAULT


def main() -> None:
    if not shutil.which("claude"):
        sys.exit("needs the Claude Code CLI on PATH (the executor/validator transport)")


    work = tempfile.mkdtemp(prefix="gfso_company_")
    e = Engine(store := SqliteStorage(scratch("demo.db")), HumanAgent(), llm=None,
               validate_signals=True, state_timeout=0)
    e.start()

    agents = AgentRegistry(path=scratch("agents.json"))
    # TWO executors, and that is the point rather than a detail. A subtree delegated entirely to ONE
    # role has no SEAM in it: every child's Del equals its parent's, which §14.5 D6 calls an internal
    # node — it self-verifies, no independent validator fires, and the node then waits for its issuer
    # to sign. Measured 2026-08-20 with a single role: the delivery landed in 57 seconds and the
    # graph stood still for half an hour. An org with one worker is a degenerate org; this one has
    # a second, so the children are public and the verifier ≠ executor gate has something to hold.
    agents.register("exec-1", "llm-executor", model=MODEL_DEFAULT, workdir=work)
    agents.register("exec-2", "llm-executor", model=MODEL_DEFAULT, workdir=work)
    agents.register("val-1", "llm-validator", workdir=work, model=MODEL_DEFAULT)
    d = Dispatcher(e, agents)

    print("authoring the verified graph (auto_decompose, ~2-4 min)…")
    out = TL.auto_decompose(
        e, f"A tiny python package in {work}: a slugify(text) function with edge-case handling "
           f"and a test file that passes under pytest", root_id="job", assignee="exec-1")
    print("subtasks:", [s["id"] for s in out["subtasks"]], "· holes:", out["holes"])
    # …and the children go to the OTHER worker, which is what makes each of them a seam.
    for kid in out["subtasks"]:
        T.reassign(e, kid["id"], "exec-2", reason="capability_mismatch")

    # THE COORDINATOR'S OWN STEP, which this demo used to skip. `auto_decompose` verifies the plan
    # STRUCTURALLY (Level 0: coverage, mappings, the DAG); execution is gated on Level 2 as well
    # (§13.4 — do the children's criteria causally carry the parent's?), and nothing starts until
    # that verdict exists. Measured 2026-08-20: without this call the demo sat with two children in
    # OFFERED and an empty workspace until its own clock ran out, while the frontier was saying
    # "CHECK THE PLAN of 'job'" the whole time and the loop below never asked it.
    print("checking the plan (Level 2) before any child may start…")
    for attempt in range(3):
        rev = TL.review_decomposition(e, "job")
        if rev.get("gate_passed") and rev.get("semantic_covered"):
            print("plan check: passed")
            break
        # THE SYSTEM CLOSES ITS OWN HOLES. A named gap is not a question for the reader — it is the
        # next round of the same authoring method, and `auto_decompose` on an already-decomposed
        # node IS that round (findings fold in as a verified revision). Measured 2026-08-20: without
        # this, the checker named gaps, the gate stayed shut, and the "autonomous" demo waited half
        # an hour for a coordinator that was never going to come.
        print(f"plan check: {'L0/L1 not clean' if not rev.get('gate_passed') else 'gaps named'}"
              f" — refining, round {attempt + 1} (`get_review('job')` has the detail)")
        TL.auto_decompose(e, root_id="job", depth=1)
    else:
        print("plan check: still open after 3 rounds — the graph below is what stands; "
              "`get_review('job')` names what the checker will not pass.")

    print("running the org to completion…")
    # BOUNDED, because a graph can legitimately stop without reaching a terminal: a node whose
    # automatic validation gave up is PARKED for its issuer (⊥ is not a pass — the engine will not
    # invent a verdict), and this loop would then spin for as long as the reader let it. The example
    # says what it is waiting on and returns.
    deadline = time.monotonic() + 1800
    while e.get_state(T.TaskId("job")).name not in ("DONE", "ESCALATED"):
        d.dispatch_once()
        if time.monotonic() > deadline:
            print("stopped after 30 min without a terminal root — the graph as it stands:")
            break
        time.sleep(5)
    print("root:", e.get_state(T.TaskId("job")).name)
    if parked := sorted(getattr(e, "_validation_parked", ())):
        print("nodes whose automatic validation gave up (they need their issuer):", ", ".join(parked))
    for n in T.get_graph(e)["nodes"]:
        print(f"  {n['id']}: {n['state']}")
    print("Q:", T.metrics(e))
    e.stop()
    store.close()   # Windows keeps the .db locked until the connection closes


# Importing a module must not RUN it. Without this guard the script body executed on import,
# so anything that walks the package tree — an IDE indexer, a doc tool, a naive test
# collection, `from gfso.examples.x import y` — ran the example; for the two that spawn
# models that meant real tokens off the reader's account and, for one, an endless loop.
if __name__ == "__main__":
    main()
