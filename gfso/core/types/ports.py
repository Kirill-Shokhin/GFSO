"""The contracts an embedder implements: storage, agents, clock, runner, LLM.

Declared here so the core can be complete without any of them being real. Each carries what a
MISSING implementation costs — a degraded feature, or a voided guarantee — because "optional" and
"optional and it still holds" are different claims.
"""
from __future__ import annotations

import os
import queue
import re
import sys
import threading
import time
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager, suppress
from pathlib import Path
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
        (§10.1), which is what makes the parent lookup a protocol question and not a convenience."""
        ...

    @abstractmethod
    def get_active_tasks(self) -> list[Task]:
        """All tasks in non-terminal states."""
        ...

    @abstractmethod
    def get_check_results(self, task_id: TaskId) -> list[CheckResult]:
        """The last CHECK battery run for this node. Empty means NOT RUN, never "clean": a caller that
        reads absence as green turns a missing check into a passing one (§2.3)."""
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
        """Record a dependency, declared or discovered — a record of its own (§2.7: Dep is a primitive beside T)."""
        ...

    @abstractmethod
    def remove_dep_edge(self, edge: DepEdge) -> None:
        """Drop one record equal to `edge`: a declared and a discovered record of one pair are two records, and
        rewriting one must not take the other. A no-op when it is not there."""
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
        must survive a restart between the delivery and the validation."""
        return None

    def store_exec_verdict(self, task_id: TaskId, verdict_json: str) -> None:
        """Persist a node's EXECUTION-validation verdict (the validate_result record; ≠ critique = the
        PLAN's L2). One record per node — the current delivery's verdict. Default no-op."""
        ...

    def get_exec_verdict(self, task_id: TaskId) -> Optional[str]:
        """The stored execution verdict (JSON) for this node, or `None`. Stamped with the generation it
        validated, so a reader can tell a verdict about THIS delivery from one about an earlier one."""
        return None

    def store_setting(self, key: str, value: str) -> None:
        """Persist one project-level setting — today the MODE (who holds which nodes). Default no-op:
        a storage without it runs every project with no mode set, which is the behaviour before modes."""
        ...

    def get_setting(self, key: str) -> Optional[str]:
        """A stored project-level setting, or `None` if it was never set."""
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


class PlaceUnavailable(OSError):
    """The execution place cannot start anything now (its container daemon does not answer): a state of the
    environment that stops the whole project, not a call that was cut nor a report that did not parse
    (`Engine.stop_for_the_place`). An OSError, so a door that already falls back on a place it cannot use does."""

    def __init__(self, place: str, why: str):
        super().__init__(f"the execution place {place} is unavailable: {why}")
        self.place, self.why = place, why


class FilesPort(ABC):
    """THE FILES OF A PLACE, read and written where the place is — an execution's (`ExecutionPort.files`): the system
    touches a node's place, a judge's copy, a scratch round, a temp or its own copies through these alone, since a
    place may stand nowhere on this host."""

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Does anything stand at `path` — a link included, even one to nothing?"""
        ...

    @abstractmethod
    def is_dir(self, path: str) -> bool:
        """Is `path` a directory (through a link)?"""
        ...

    @abstractmethod
    def listdir(self, path: str) -> list[str]:
        """The names in the directory `path`; none where it is no directory."""
        ...

    @abstractmethod
    def read_bytes(self, path: str, size: Optional[int] = None) -> Optional[bytes]:
        """The file's bytes — its first `size` where given — or None where no file stands."""
        ...

    @abstractmethod
    def write_bytes(self, path: str, data: bytes) -> None:
        """`data` as the file `path`, its directories made. A failure raises `OSError`."""
        ...

    @abstractmethod
    def mkdir(self, path: str) -> None:
        """The directory `path`, its parents made; there already is fine."""
        ...

    @abstractmethod
    def read_tree(self, path: str) -> Optional[dict]:
        """{path relative to `path`, posix: bytes} of every regular file under the directory `path` — one walk, a link
        not followed — or None where it is no directory."""
        ...

    @abstractmethod
    def subdirs(self, path: str, depth: int) -> list[str]:
        """The directories under `path`, `depth` levels down at most, relative and posix — one walk, a link not
        followed; none where it is no directory."""
        ...

    def read_text(self, path: str) -> Optional[str]:
        """The file as UTF-8 text, undecodable bytes replaced, or None where no file stands."""
        return None if (b := self.read_bytes(path)) is None else b.decode("utf-8", errors="replace")

    def write_files(self, base: str, files: dict) -> None:
        """{path relative to `base`: bytes} written under `base` — one operation where a call costs one."""
        for rel, data in files.items():
            self.write_bytes(str(Path(base) / rel), data)

    def mkdtemp(self, prefix: str, dir: str) -> str:
        """A new empty directory of its own under `dir`, named `prefix` and a random tail."""
        self.mkdir(d := os.path.join(dir, f"{prefix}{uuid.uuid4().hex[:8]}"))
        return d

    def holds(self, path: str) -> bool:
        """Is `path` in a place held apart from this host (`files_at`)? This host holds none apart."""
        return False

    def old_layout(self) -> tuple:
        """The system directories beside a base this holds, as laid out before each named its project (`unprojected`)
        — none on this host, where they still stand as they were."""
        return ()


class ExecutionPort(ABC):
    """WHERE a session or a command runs — this host, or a place isolated from it — as opposed to WHO answers
    (`LLMProviderPort`) and who pumps the signals (`RunnerPort`). A launch touches the host only through it: the
    program it finds, the process it starts and ends, the scratch place it lends, the directory the agent CLI keeps
    its conversations in. One server can then run every project's work isolated without a second server. A launch
    the place cannot start raises `PlaceUnavailable`."""

    #: its places' files, read and written where they are (`FilesPort`)
    files: "FilesPort"
    #: the Python a system script is run with here
    python = sys.executable
    #: does each session stand in a place of its own (`session`)? There a judge never works in its executor's place —
    #: a delivery it could not copy is not judged (§10.3); this host holds no place apart, and a judge without a copy
    #: works in the place, alone
    apart = False

    def to_outside(self, text: str) -> str:
        """`text` with every path spelled as this execution sees it respelled as the host does — a container's mount
        points; on this host, as it is."""
        return text

    def door(self, credential, upstream: str) -> Optional[tuple]:
        """(base URL, key): where a model client started here reaches its provider's `upstream`, through a door that
        holds `credential` itself, and the key the client presents there in its place — so no agent process holds the
        credential; None where the client must hold it (this host)."""
        return None

    def unavailable(self, storage: bool = False) -> Optional[str]:
        """Why this place cannot start a call now, or None where it can — a cheap health check; with `storage`, its
        storage asked too (a probe that costs a call: while the place stands stopped). This host always can."""
        return None

    @abstractmethod
    def which(self, program: str) -> Optional[str]:
        """The program as this execution would start it, or None where it has none."""
        ...

    @abstractmethod
    def popen(self, args: list[str], *, env: dict, cwd: str, **pipes):
        """Start `args` in `cwd` with exactly `env`, with no window and in a group of its own; the process answers
        `subprocess.Popen`'s stdin/stdout/poll/wait/kill/pid."""
        ...

    @abstractmethod
    def end(self, proc) -> None:
        """End the process AND what it started, however far it got, and stop holding it. Repeating it is harmless."""
        ...

    @abstractmethod
    def temp_root(self) -> str:
        """The host directory a temporary file must stand in to be seen where this execution runs — a packet's inputs or
        lists named to an agent are read there, not here."""
        ...

    @contextmanager
    def scratch(self, prefix: str, *, system: bool = False, dir: Optional[str] = None):
        """A context manager lending an empty directory of its own under `dir` — else `temp_root` —, made and removed
        where this execution runs (`FilesPort.mkdtemp`, `remove_tree`; a removal that fails leaves it). `system`: for
        the system's own copies and checks — where an isolated place gives its sessions a temp, one none of them reaches
        but a session handed a directory in it. This host has one temp."""
        d = self.files.mkdtemp(prefix, dir or self._scratch_root(system))
        try:
            yield d
        finally:
            with suppress(OSError):
                self.remove_tree(d)

    def _scratch_root(self, system: bool) -> str:
        """Where `scratch` lends its directories."""
        return self.temp_root()

    def temp_of(self, place: Optional[str]) -> str:
        """The temp a session working in `place` holds — where the system lays what it is to read (its inputs, its
        long lists); an isolated place gives each node one of its own. This host has one temp."""
        return self.temp_root()

    @abstractmethod
    def state_dir(self):
        """Where the agent CLI started here keeps its state — the conversations a session continues live under it."""
        ...

    def state_seen(self) -> str:
        """`state_dir` as a process started here names it — the CLI reads its hooks' paths there, not the host's."""
        return str(self.state_dir())

    @abstractmethod
    def run(self, args: list[str], *, cwd: str, timeout: float, env: Optional[dict] = None):
        """A command to its end in `cwd`: a `CompletedProcess` with text output; past `timeout` it is ended whole and
        `TimeoutExpired` reaches the caller."""
        ...

    @abstractmethod
    def shell(self) -> Optional[str]:
        """The shell the plan's probes are written for, as this execution starts it, or None where it has none."""
        ...


    @abstractmethod
    def copy_tree(self, src: str, dst: str) -> None:
        """`src` as it stands where this execution runs — every file, symlinks as links, times kept — at `dst`, which
        does not exist yet. A failure raises `OSError`."""
        ...

    @abstractmethod
    def remove_tree(self, path: str) -> None:
        """`path` gone, whatever it holds — a read-only directory a test made in it included. Gone already is fine."""
        ...

    def session(self, cwd: str) -> "ExecutionPort":
        """Where an agent's session working in `cwd` runs, as opposed to the system's own commands: an isolated place
        may give each session a boundary of its own. This host is one place for both."""
        return self

    def stop(self) -> None:
        """Release what this execution holds for its project — its goal settled, or the project deleted. The host
        holds nothing."""


class HostFiles(FilesPort):
    """The files of a place that is this host (`LocalExecution`): plain host calls."""

    def exists(self, path: str) -> bool:
        return os.path.lexists(path)

    def is_dir(self, path: str) -> bool:
        return os.path.isdir(path)

    def listdir(self, path: str) -> list[str]:
        return os.listdir(path) if os.path.isdir(path) else []

    def read_bytes(self, path: str, size: Optional[int] = None) -> Optional[bytes]:
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            return f.read(-1 if size is None else size)

    def write_bytes(self, path: str, data: bytes) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(data)

    def mkdir(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)

    def read_tree(self, path: str) -> Optional[dict]:
        if not os.path.isdir(path):
            return None
        return {Path(d, f).relative_to(path).as_posix(): Path(d, f).read_bytes()
                for d, _, fs in os.walk(path) for f in fs if Path(d, f).is_file() and not Path(d, f).is_symlink()}

    def subdirs(self, path: str, depth: int) -> list[str]:
        return [Path(d, x).relative_to(path).as_posix() for d, xs, _ in os.walk(path)
                if len(Path(d).relative_to(path).parts) < depth for x in xs if not os.path.islink(os.path.join(d, x))]


#: a base's project directories stand beside it, under this prefix and the base's name, each holding its project's
#: places and every system directory of the project (`ContainerExecution`)
NODES = ".gfso-nodes-"
#: what names a validation's scratch beside the place it validates (`scratch_of`)
SCRATCH = ".gfso-scratch-"
#: a system directory as it stood directly beside a base before each named its project


def unprojected(path) -> bool:
    """Is `path` under a system directory laid out before every one named its project — a scratch, a temp, system
    copies directly beside a base an execution holds (`FilesPort.old_layout`), not among a project's places? No
    container mounts one any more: nothing there stands for a check to run. By the holders' bases, never by a name:
    a directory an agent named `.gfso-tmp-x` in its place was read so, its findings no longer demanded (critic)."""
    p = os.path.normcase(os.path.abspath(path))
    return any(p.startswith(os.path.normcase(str(d)) + os.sep) for f in _HOLDERS for d in f.old_layout())


#: the files of the places held apart from this host, latest first — the system's own table of where each place is
_HOLDERS: list = []


def hold_places(files: FilesPort, held: bool = True) -> None:
    """`files` hold their places (`files_at`) from now on — or, `held` False, no longer: their project is gone."""
    with suppress(ValueError):
        _HOLDERS.remove(files)
    if held:
        _HOLDERS.insert(0, files)


def files_at(path) -> FilesPort:
    """The files that reach `path`: those holding the place it lies in (`FilesPort.holds`), else this host's. For a
    reader handed a path the system named — a finding's command over a validation round — and no execution in hand: the
    place is found by the system's table, never by what stands at the path: every system directory names its project,
    so of two projects on one base only the path's own holds it."""
    # …save the base itself, which each project on it holds and either reads alike while it is a host directory: the
    # move into volumes makes it a per-project record
    return next((f for f in _HOLDERS if f.holds(str(path))), HOST)


HOST = HostFiles()


class LLMProviderPort(ABC):
    #: may independent calls run at once (`stats.readings`)? A provider says so only where each call stands alone.
    parallel_safe: bool = False
    #: can it run an AGENT — tools, a place, a conversation (`run_agent`)? A provider of one-shots says no;
    #: `validate_result` reads it to refuse before a paid call, every other agent door raises at `run_agent`.
    runs_agents: bool = False
    #: the work tools the LAST agent run reached for, by name — what a verdict's record and the invariants read of a run;
    #: a provider that runs agents keeps its own, set per run (this empty default is never written)
    last_tool_calls: dict = {}
    #: WHERE its processes and commands run (`ExecutionPort`), or None for a provider that runs none here
    execution: Optional["ExecutionPort"] = None

    def run_agent(self, system: str, user: str, allowed_tools: tuple[str, ...], cwd: Optional[str] = None,
                  timeout: Optional[int] = None, max_turns: Optional[int] = None,
                  session: Optional[str] = None) -> str:
        """One agent run with work tools in `cwd`, continuing `session` where named; its final report."""
        raise NotImplementedError(f"{type(self).__name__} runs no agents (`runs_agents` is False)")

    def forget(self, session: str) -> None:
        """Drop a conversation: the work it served is settled. A provider keeping none has nothing to drop."""

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
