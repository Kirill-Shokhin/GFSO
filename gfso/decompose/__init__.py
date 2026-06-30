"""GFSO single-level decomposition function — the E2 search↔audit loop as one button, end to end.

`decompose(request, depth=1)` runs SEARCH↔AUDIT (the AUDIT emits, in one structured call, the prose basis
`basis_markdown` AND the graph spec) and builds the CORE graph from the spec — returning a `DecomposeResult`.
Single-level by definition (one node → its children); recurse by calling it again on a child. The main agent
calls THIS instead of reasoning the graph node-by-node (E2: that under-covers and burns tokens); it may still
tweak pointwise via the FSM upper verbs. `decompose_text`/`decompose_spec` expose the earlier stages.
"""
from __future__ import annotations

from dataclasses import dataclass

from gfso.core.types import TaskId
from gfso.engine import Engine
from gfso.adapters.llm.claude import ClaudeLLM

from .loop import decompose_text, decompose_spec, MODELS
from .build import build_graph_live


@dataclass
class DecomposeResult:
    engine: Engine
    root_id: TaskId
    d_md: str          # the durable markdown basis (basis_markdown)
    spec: dict         # the structured graph spec (root_criteria/subtasks/mappings/deps/neglected)


def decompose(request: str, depth: int = 1, model: str = "sonnet",
              engine: Engine | None = None, root_id: str = "root",
              llm: ClaudeLLM | None = None) -> DecomposeResult:
    """request -> (search↔audit -> prose basis + graph spec -> CORE graph). Sonnet, depth 1 by default. Builds
    THROUGH the FSM (the single build path); if no engine is given, spins a fresh started in-memory one."""
    llm = llm or ClaudeLLM(model=MODELS.get(model, model))
    spec = decompose_spec(request, depth=depth, llm=llm)
    if engine is None:
        from gfso.adapters.storage.memory import MemoryStorage
        from gfso.adapters.agents.human import HumanAgent
        engine = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=True)
        engine.start()
    eng, rid = build_graph_live(spec, request, engine, root_id=root_id)
    return DecomposeResult(eng, rid, spec.get("basis_markdown", ""), spec)


def decompose_into(engine: Engine, request: str, root_id: str = "root", assignee: str = "human",
                   depth: int = 1, model: str = "sonnet", llm: ClaudeLLM | None = None) -> DecomposeResult:
    """Agent-facing: run search↔audit on `request` and build the result INTO a LIVE engine THROUGH the FSM
    (signals), under `root_id`. Every node is authored by a logged ASSIGN (no offline `_graph.save_task`
    bypass); Dep seams are declared as `depends_on` criteria at creation, so no cascade fires. The entry the
    MCP/API surface calls so the agent builds a real graph through the protocol."""
    llm = llm or ClaudeLLM(model=MODELS.get(model, model))
    spec = decompose_spec(request, depth=depth, llm=llm)
    eng, rid = build_graph_live(spec, request, engine, root_id=root_id, assignee=assignee)
    return DecomposeResult(eng, rid, spec.get("basis_markdown", ""), spec)


__all__ = ["decompose", "decompose_into", "decompose_text", "decompose_spec",
           "build_graph_live", "DecomposeResult"]
