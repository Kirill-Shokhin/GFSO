from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Union

from .enums import MutationType, Signal, DoneReason, State, RevisionReason
from .primitives import TaskId, Spec, AgentId


@dataclass(frozen=True)
class MutateGraph:
    task_id: TaskId
    mutation: MutationType
    new_state: State | None = None
    done_reason: DoneReason | None = None
    spec: Spec | None = None
    assignee: AgentId | None = None
    parent_id: TaskId | None = None      # CREATE_TASK: parent link
    deadline: datetime | None = None     # CREATE_TASK: T deadline
    max_iterations: int = 3              # CREATE_TASK: rework bound
    covers: tuple[str, ...] = ()        # CREATE_TASK: parent criteria this child maps to (§2.2)
    dep_from: TaskId | None = None       # RECORD_DEP: prerequisite node; ADJUDICATE_DEP: corrected source (§6.2)
    dep_froms: tuple[TaskId, ...] = ()   # ADJUDICATE_DEP: corrected FULL source set (SET semantics, §6.2)
    dep_external: bool = False           # ADJUDICATE_DEP: retract — blocker non-producible (FM-5 line, §6.2)
    glue: str = ""                       # RECORD_DEP: provenance text (the BLOCK reason)
    revision_reason: RevisionReason | None = None  # APPLY_SPEC/REOPEN: causal type of the revision (§16.5)


@dataclass(frozen=True)
class RunChecks:
    task_id: TaskId


@dataclass(frozen=True)
class Recommend:
    task_id: TaskId


@dataclass(frozen=True)
class Dispatch:
    task_id: TaskId
    signal: Signal


@dataclass(frozen=True)
class EmitSignal:
    signal: Signal
    task_id: TaskId


Effect = Union[MutateGraph, RunChecks, Recommend, Dispatch, EmitSignal]
