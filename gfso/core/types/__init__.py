"""The vocabulary the whole system speaks: primitives, enums, effects, ports.

One spelling per notion, on purpose — a word with two definitions is how two halves of a rule
come to disagree, which this package exists to prevent.
"""
from .enums import (
    State, Signal, Action, CriticVerdict, DoneReason, Verdict, Stage, FM,
    AutonomyLevel, MutationType, Predictability, RevisionReason,
    TERMINAL_STATES, NON_TERMINAL_STATES, REASSIGNABLE_STATES, QUASI_TERMINAL_STATES,
    EXECUTOR_ACTIONS, SPAWNABLE_ACTIONS,
)
from .primitives import (
    TaskId, AgentId,
    Criteria, Spec, Task, AcceptedRiskItem,
    CriterionMapping, DepEdge,
    GuardContext, CheckResult, Recommendation,
    GraphContext, SignalData, DispatchPayload, Refusal, SignalOutcome, Wait,
    passed, settled_positive,
)
from .effects import (
    MutateGraph, RunChecks, Recommend, Dispatch, EmitSignal, Effect,
)
from .ports import (StoragePort, LLMProviderPort, AgentPort, VerifierPort,
                    ClockPort, SystemClock, RunnerPort, ThreadRunner)
