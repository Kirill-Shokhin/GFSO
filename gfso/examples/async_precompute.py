"""Async precompute: structure computed OUTSIDE the process, applied as plain signals.

The embedding pattern for hosts that precompute decomposition with their own machinery (an
external classifier, a planning service, a batch job): the core never knows or cares WHERE the
structure came from — it arrives through the same audited ASSIGN signals as everything else,
passes the same L0/L1 checks, and the graph holds only verified states. No LLM, deterministic."""
from gfso.examples import scratch
from gfso.engine import Engine
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.adapters.agents.human import HumanAgent
from gfso import tools as T


def main() -> None:
    """Run the demo: apply a structure computed elsewhere, then drive it to root DONE.

    The point it proves is negative — nothing here tells the core the plan was precomputed.
    """
    # ── somewhere ELSE (another process, another machine, another planner) ──────────────────────
    precomputed = {
        "root": {"description": "Ship the landing page",
                 "criteria": [{"name": "content", "description": "copy approved"},
                              {"name": "live", "description": "deployed and reachable"}],
                 # STD-1: a decomposed node without a ACCEPTED_RISKS register is a visible hole (CHECK-4)
                 "accepted_risks": [{"item": "traffic spike on launch day", "predictability": "statistical",
                                "justification": "static page behind a CDN",
                                "invalidation_condition": "launch coincides with a campaign"}]},
        "children": [
            {"task_id": "copy", "assignee": "host",
             "spec": {"description": "Write the copy",
                      "criteria": [{"name": "approved", "description": "stakeholder sign-off"}]}},
            {"task_id": "deploy", "assignee": "host",
             "spec": {"description": "Deploy the page",
                      "criteria": [{"name": "reachable", "description": "200 on the public URL"},
                                   {"name": "dep__copy", "description": "renders the approved copy",
                                    "depends_on": "copy"}]}},
        ],
        "mappings": [{"criterion_name": "content", "child_id": "copy"},
                     {"criterion_name": "live", "child_id": "deploy"}],
    }

    # ── the live core: the precomputed structure lands as SIGNALS, nothing else ──────────────────
    e = Engine(store := SqliteStorage(scratch("demo.db")), HumanAgent(), llm=None,
               validate_signals=True, state_timeout=0)
    e.start()

    T.create_task(e, "page", precomputed["root"], assignee="host")
    T.decompose(e, "page", precomputed["children"], mappings=precomputed["mappings"])

    holes = T.list_holes(e, "page")["holes"]
    print("holes after applying the precomputed structure:", holes)
    print("deps:", T.get_dependencies(e))
    for c in T.get_graph(e)["nodes"]:
        print(f"  {c['id']}: {c['state']}")
    e.stop()
    store.close()   # Windows keeps the .db locked until the connection closes


# Importing a module must not RUN it. Without this guard the script body executed on import,
# so anything that walks the package tree — an IDE indexer, a doc tool, a naive test
# collection, `from gfso.examples.x import y` — ran the example; for the two that spawn
# models that meant real tokens off the reader's account and, for one, an endless loop.
if __name__ == "__main__":
    main()
