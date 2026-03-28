from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from .enums import MutationType, Signal, DoneReason, State
from .primitives import TaskId, Spec, AgentId


@dataclass(frozen=True)
class MutateGraph:
    task_id: TaskId
    mutation: MutationType
    new_state: State | None = None
    done_reason: DoneReason | None = None
    spec: Spec | None = None
    assignee: AgentId | None = None


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
