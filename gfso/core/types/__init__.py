"""The vocabulary the whole system speaks: primitives, enums, effects, ports.

One spelling per notion, on purpose — a word with two definitions is how two halves of a rule
come to disagree, which this package exists to prevent.
"""
from .enums import (
    State, Signal, Action, CriticVerdict, DoneReason, Verdict, Stage, FM,
    AutonomyLevel, Mode, MutationType, Predictability, RevisionReason,
    TERMINAL_STATES, NON_TERMINAL_STATES, REASSIGNABLE_STATES, QUASI_TERMINAL_STATES,
    RETIRED_STATES, state_named,
    EXECUTOR_ACTIONS, SPAWNABLE_ACTIONS,
)
from .primitives import (
    TaskId, AgentId, DEFAULT_MAX_ITERATIONS,
    Criteria, Probe, Spec, Task, AcceptedRiskItem, Register, register_of, set_aside_of,
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
