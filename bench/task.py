"""BenchTask: dataset-agnostic representation of one benchmark problem.

A bench provides three things to test GFSO Phase 1:
  - Task statement (prompt for LLM)
  - GFSO Spec with criteria (visible to model during loop, used by VerifierPort)
  - Hidden evaluator (ground truth, never seen by model)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from gfso.core.types import Spec, CheckResult, VerifierPort, StoragePort


@dataclass(frozen=True)
class BenchTask:
    task_id: str
    title: str

    # LLM-facing
    problem_prompt: str        # full task description with examples
    is_function: bool          # adapts agent system prompt (function-completion vs stdin)

    # GFSO loop
    spec: Spec                                                # criteria + neglected
    make_verifier: Callable[[StoragePort], VerifierPort]      # built with the engine's storage at run time

    # Ground truth (hidden from agent)
    evaluate_hidden: Callable[[str], list[CheckResult]]

    metadata: dict = field(default_factory=dict)
