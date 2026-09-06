"""The contracts an embedder implements: storage, agents, clock, runner, LLM.

Declared here so the core can be complete without any of them being real. Each carries what a
MISSING implementation costs — a degraded feature, or a voided guarantee — because "optional" and
"optional and it still holds" are different claims.
"""
from __future__ import annotations

import queue
import threading
import time
from abc import ABC, abstractmethod
from typing import Optional

from .primitives import (
    TaskId, AgentId, Task, CheckResult, Recommendation,
    DispatchPayload, SignalData, DepEdge, Spec,
)
from gfso.config import PIPELINE_PAGE, USAGE_PAGE


class StoragePort(ABC):
    """The persistence contract, split explicitly (the embedder's contract):

    MANDATORY CORE (abstract — an adapter cannot exist without them): task/child reads+writes,
    dep edges, check-result cache, AND the append-only signal log (`append_audit`/`load_audit`).
    The log is core, not an extension: the Thm 11/Inv-7 guarantee `state = fold(log)` is CONDITIONED
    on log completeness — an adapter that silently drops entries voids the guarantee, so silence
    is not an option. An adapter whose MEDIUM is ephemeral (in-memory) still implements the log
    honestly for its lifetime; an adapter that consciously chooses not to persist it is a
    DECLARED degraded mode (no Thm 11-over-restart, no replay) — declared in ITS code, never
    defaulted here.

    OPTIONAL EXTENSIONS (defaults below): critique / deliver-result / exec-verdict / pipeline
    records. Missing ones degrade individual features (named in each docstring), never the
    protocol guarantees."""

    @abstractmethod
    def get_task(self, task_id: TaskId) -> Optional[Task]:
        """The node as it stands NOW — its latest version. `None` if this id was never assigned."""
        ...

    @abstractmethod
    def save_task(self, task: Task) -> None:
        """Write the node's current version. The LOG is what records the change (`append_audit`); this
        holds only the projection of it, which is why a lost write here is recoverable and a lost
        log entry is not."""
        ...

    @abstractmethod
    def get_all_tasks(self) -> list[Task]:
        """Every node of this graph, terminal ones included — the frontier and the metrics both read the
        whole set, and a store that hid settled nodes would make `q_V` measure a different question."""
        ...

    @abstractmethod
    def get_children(self, task_id: TaskId) -> list[Task]:
        """The nodes this one was decomposed into (D), in no guaranteed order. Empty for a leaf."""
        ...

    @abstractmethod
    def get_parent(self, task_id: TaskId) -> Optional[Task]:
        """The node this one covers a criterion of — `None` for a root. Its Del is this node's ISSUER
        (§14.1), which is what makes the parent lookup a protocol question and not a convenience."""
        ...

    @abstractmethod
    def get_active_tasks(self) -> list[Task]:
        """All tasks in non-terminal states."""
        ...

    @abstractmethod
    def get_check_results(self, task_id: TaskId) -> list[CheckResult]:
        """The last CHECK battery run for this node. Empty means NOT RUN, never "clean": a caller that
        reads absence as green turns a missing check into a passing one (§11.2)."""
        ...

    @abstractmethod
    def store_check_results(self, task_id: TaskId, results: list[CheckResult]) -> None:
        """Replace the cached battery for this node. Wholesale, because a partial refresh leaves two
        answers about one graph shape and the older one is indistinguishable from the newer."""
        ...

    @abstractmethod
    def get_recommendation(self, task_id: TaskId) -> Optional[Recommendation]:
        """The last AI-layer recommendation for this node, if one was stored. Advisory: nothing in the
        protocol is gated on it."""
        ...

    @abstractmethod
    def store_recommendation(self, task_id: TaskId, rec: Recommendation) -> None:
        """Keep the latest recommendation for this node, replacing any earlier one."""
        ...

    @abstractmethod
    def add_dep_edge(self, edge: DepEdge) -> None:
        """Record a dependency (§10: a Dep is criteria content — the consumer's criterion names the
        producer). Adding one twice is not an error; the edge set is what matters, not the calls."""
        ...

    @abstractmethod
    def remove_dep_edge(self, from_id: TaskId, to_id: TaskId) -> None:
        """Drop one edge. A no-op when it is not there — removal is idempotent because the callers that
        reconcile a plan cannot know which edges a previous round already withdrew."""
        ...

    @abstractmethod
    def get_dep_edges(self) -> list[DepEdge]:
        """Every dependency in this graph, declared and discovered alike. `q_Dep` is the ratio between
        the two, so an adapter that returned only the declared ones would report a perfect score."""
        ...

    @abstractmethod
    def append_audit(self, row: dict) -> None:
        """Append ONE signal-log entry (append-only — the Thm 11/Inv-7 carrier; state = fold(log))."""
        ...

    @abstractmethod
    def load_audit(self) -> list[dict]:
        """The full signal log, oldest-first (hydrates the AuditLog on engine construction)."""
        ...

    # --- OPTIONAL EXTENSIONS (feature-level degraded modes, named per method) ---

    def store_critique(self, task_id: TaskId, critique_json: str) -> None:
        """Persist a node's L2 critique (the validation record). Default no-op so
        existing storages stay valid; memory/sqlite override."""
        ...

    def get_critique(self, task_id: TaskId) -> Optional[str]:
        """The stored Level-2 review record (JSON), or `None` if this plan was never reviewed. Absence
        is what the execution gate reads as "not checked" — it is not an empty review."""
        return None

    def store_deliver_result(self, task_id: TaskId, result: str) -> None:
        """Persist the node's LAST DELIVER result (the deliverable pointer — the validator's input;
        must survive a server restart). Default no-op."""
        ...

    def get_deliver_result(self, task_id: TaskId) -> Optional[str]:
        """What the executor handed over in its last DELIVER — the validator's input, kept because it
        must survive a restart between the delivery and the judging."""
        return None

    def store_exec_verdict(self, task_id: TaskId, verdict_json: str) -> None:
        """Persist a node's EXECUTION-validation verdict (the validate_result record; ≠ critique = the
        PLAN's L2). One record per node — the current delivery's verdict. Default no-op."""
        ...

    def get_exec_verdict(self, task_id: TaskId) -> Optional[str]:
        """The stored execution verdict (JSON) for this node, or `None`. Stamped with the generation it
        judged, so a reader can tell a verdict about THIS delivery from one about an earlier one."""
        return None

    def log_pipeline(self, ts: str, source: str, message: str) -> None:
        """Persist one pipeline observation line (live token TICKS are excluded by the caller —
        they update in place and are WS-only noise). Default no-op so existing storages stay valid."""
        ...

    def get_pipeline(self, limit: int = PIPELINE_PAGE) -> list[dict]:
        """The most recent pipeline lines, oldest-first: [{ts, source, message}]."""
        return []

    def log_usage(self, row: dict) -> None:
        """Persist ONE model call's cost and tokens: {ts, stage, model, node_id, input_tokens,
        output_tokens, cache_input_tokens, cost_usd}.

        What a project cost is a question the system could not answer about itself: the numbers
        existed per call, inside whichever verb happened to run, and were printed into a progress
        line as text. Nothing accumulated them, so "what did this graph cost" had no answer, and an
        experiment measuring cost had to reconstruct it from its own side of the wire — which works
        only for the calls that side makes. Default no-op so existing storages stay valid."""
        ...

    def get_usage(self, limit: int = USAGE_PAGE) -> list[dict]:
        """The recorded model calls, oldest-first."""
        return []


class LLMProviderPort(ABC):
    @abstractmethod
    def complete(self, prompt: str, context: str = "") -> str:
        """One zero-tool completion. The whole of this port: an adapter that cannot run tools is still a
        valid provider for the checker, and the verbs that need `run_agent` say so rather than
        failing halfway through a paid call."""
        ...

    def complete_structured(self, system: str, user: str, schema: dict) -> dict:
        """Native structured output: model fills `schema` (fields defined upfront).
        Default = degraded empty (no client); real provider overrides. Returns {} on failure."""
        return {}


class AgentPort(ABC):
    @abstractmethod
    def dispatch(self, agent_id: AgentId, payload: DispatchPayload) -> Optional[SignalData]:
        """Hand a packet to a participant and return their answering signal, or `None` when there is
        nobody to call — a person is an id the engine knows and cannot dispatch to, and the graph
        waits for their own signal rather than inventing one."""
        ...


class VerifierPort(ABC):
    """Runs deterministic verification of a deliverable against a Spec's criteria.

    Implementations are domain-specific (subprocess+stdin, pytest, schema-check, etc).
    Returns one CheckResult per criterion in spec.criteria, in the same order.
    """

    @abstractmethod
    def verify(self, task_id: TaskId, deliverable: str, spec: Spec) -> list[CheckResult]:
        """Check a delivery against the node's criteria deterministically — the issuer's oracle. Returns
        one result per criterion it could decide; what it could not decide it must SKIP, because a
        verifier that passes what it did not run is the false green this system exists to refuse."""
        ...


class ClockPort(ABC):
    """The runtime's time source — Inv-5 (finiteness) enforcement reads THIS, never the wall clock
    directly, so a host can substitute virtual time (tests) or an anchored/tamper-resistant source
    (a real deployment; the clock-anchoring question is a DECLARED open end for implementors —
    the port is the seam, not the answer)."""

    @abstractmethod
    def now(self) -> float:
        """Seconds on this clock — monotonic, and never the wall clock: a fake-clock host drives Inv-5
        timeouts in milliseconds, and a test that slept for real would be measuring the runner."""
        """Current time as epoch seconds (comparable with datetime.timestamp())."""
        ...

    @abstractmethod
    def wait(self, seconds: float) -> None:
        """Block for that long on THIS clock. A host with a virtual clock advances it instead."""
        """Park the calling monitor for `seconds` (virtual time may return immediately)."""
        ...


class SystemClock(ClockPort):
    """The stdlib default. Trivial zero-dependency defaults live WITH their port (the engine may
    import core only — the layer gate); heavier substrates are adapters."""

    def now(self) -> float:
        return time.time()

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)


class RunnerPort(ABC):
    """The execution substrate: WHO pumps the signal queue and ticks the timeout monitor. The
    protocol step itself (validate → transition → effects → audit → events) is a pure function
    of one signal (`engine.loop.process_signal`) — this port only decides how it is driven, so
    an asyncio/distributed host swaps the substrate without touching the core."""

    @abstractmethod
    def new_queue(self):
        """A queue with `put`/`get`/`task_done` — the signal channel the protocol step reads from."""
        """A queue with put/get/task_done/join semantics for SignalData items."""
        ...

    @abstractmethod
    def spawn(self, target, name: str) -> None:
        """Run `target` concurrently. Whether that is a thread, a task or a process is the host's
        business; the protocol only needs it to run and to not block the caller."""
        """Run `target()` on the substrate (daemon semantics: dies with the host)."""
        ...


class ThreadRunner(RunnerPort):
    """The stdlib default: one daemon thread per loop, a thread-safe queue."""

    def new_queue(self):
        return queue.Queue()

    def spawn(self, target, name: str) -> None:
        threading.Thread(target=target, name=name, daemon=True).start()
