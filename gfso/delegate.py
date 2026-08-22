"""Delegation — the registry-driven autostart machinery (designs doc §3.1-7 + §7, author-confirmed).

The issuer's ONLY act is setting Del: a node whose assignee is a REGISTERED llm-executor is picked up
from the frontier by the DISPATCHER, which spawns a headless executor (work tools, scoped cwd), wraps
its single structured report into the canonical FSM signals (ACCEPT/DELIVER/BLOCK/CHALLENGE,
source = the executor's id — the executor itself never touches the graph), then AUTO_PASS-VALIDATES on
DELIVER→VALIDATING with the registered llm-validator instrument and AUTO_PASS-SIGNALS the verdict
(PASS → DONE; FAIL(failed_criteria) → the FSM's own REWORKING loop, bounded by max_iterations).
An unparsed validator report NEVER auto-signals — it escalates to the issuer (the one manual point).
Unregistered ids = human = the system stays passive (the safe default); registered NON-executor kinds
never spawn (kind-guard). Identity/authority stays canon-exact: Del binds at delegation, the
executor's own report IS its Inv-1 consent, no second timeout clock (the FSM monitor owns time)."""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

from gfso.config import LABEL_CHARS, MODEL_DEFAULT, agents_path, validator_retry_model
from gfso.tools_llm import validate_internal_on as _validate_internal_on
from gfso.decompose.loop import _stat_line
from gfso.core.types import (TaskId, AgentId, Signal, SignalData, Stage, Verdict, Action,
                             SPAWNABLE_ACTIONS, passed)

log = logging.getLogger(__name__)

_PROMPTS = Path(__file__).parent / "mcp" / "prompts"
EXECUTOR_TOOLS = ("Read", "Write", "Edit", "Bash", "Glob", "Grep")

EXECUTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["delivered", "blocked", "challenge"]},
        "summary": {"type": "string"},
        "self_validation": {"type": "string"},
        "reason": {"type": "string"},
        "blocker_task_id": {"type": "string"},
        "blocker_task_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "summary"],
}


class AgentRegistry:
    """{agent_id → {kind, model?, workdir?}} — the server-wide roster of NON-human participants.
    kind ∈ llm-executor | llm-validator | external. Persisted as one json file (GFSO_AGENTS_PATH,
    default data/agents.json): survives restarts, editable by hand, no schema migration."""

    def __init__(self, path: str | None = None):
        self._path = Path(path) if path else agents_path()   # one derivation, `gfso.config` (S4)
        self._agents: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._mtime: float | None = None
        self._load()

    @property
    def path(self) -> str:
        """The roster file this registry is bound to — asked whenever a process moves its home."""
        return str(self._path)

    def _load(self) -> bool:
        """Read the roster, and re-read it when the FILE has changed underneath.

        The docstring above promises a roster "editable by hand", and the registry is a per-process
        singleton — so it read the file once, at server start, and every later edit was invisible.
        Measured: a probe rewrote the roster to point two executors at its own workspace, the server
        went on using the entry from the run before it, and both agents worked in a directory that
        belonged to a different experiment. Nothing said so; the graph looked healthy and the verdicts
        judged the wrong tree. One `stat` per access is the price of the promise being true.
        """
        try:
            mtime = self._path.stat().st_mtime
        except OSError:
            return True                # no roster yet is the normal first-run state
        if self._mtime == mtime:
            return True
        try:
            self._agents = json.loads(self._path.read_text(encoding="utf-8"))
            self._mtime = mtime
            return True
        except FileNotFoundError:
            return True               # no roster yet is the normal first-run state
        except Exception as ex:
            # An unreadable roster is not an empty roster. Silent, it disabled delegation whole:
            # every node assigned to an executor simply waited, with no line anywhere — the exact
            # shape that reads as "the agent is not working".
            # stderr, not stdout: `gfso mcp` speaks JSON-RPC on stdout, and a diagnostic printed
            # there corrupts the very door it is diagnosing.
            print(f"gfso: agent registry {self._path} is unreadable ({ex}) — delegation is OFF "
                  f"until it is fixed or removed", file=sys.stderr, flush=True)
            return False

    def register(self, agent_id: str, kind: str, model: str = MODEL_DEFAULT,
                 workdir: str | None = None, validator: str | None = None,
                 oracle_map: str | None = None, max_turns: int | None = None,
                 client: str | None = None, project: str | None = None) -> dict:
        if kind not in ("llm-executor", "llm-validator", "unittest-checker", "external"):
            raise ValueError(f"unknown kind {kind!r} (llm-executor | llm-validator | unittest-checker "
                             f"| external; a human needs no registration — unregistered = human)")
        # An agent role with no working directory cannot work, and the ways it failed were the worst
        # available: the executor's spawn raised into a blanket handler that only logged, and the
        # node was never retried; the validator's error was discarded and the node sat in VALIDATING
        # forever. Neither reached the user. This is the earliest point at which the missing fact
        # can be named, and the only one where naming it costs nothing.
        if kind == "unittest-checker" and not oracle_map:
            # It reads its hidden tests from an issuer-side map, and there was no way to give it
            # one through `register_agent` — so a checker registered through the product's own door
            # ALWAYS returned no verdict, and, being the first registered validator, silently
            # disabled any llm-validator registered after it.
            raise ValueError(
                f"registering {agent_id!r} as unittest-checker needs `oracle_map`: the path to the "
                f"issuer-side map of hidden tests it runs. Without it no verdict can ever be "
                f"produced, and its presence would stop an llm-validator from being used.")
        if kind in ("llm-executor", "llm-validator") and not workdir:
            raise ValueError(
                f"registering {agent_id!r} as {kind} needs `workdir`: the directory of the project "
                f"it works in. Without it the agent would be spawned where the server stands — the "
                f"gfso state home — which contains none of the work it is meant to do or judge.")
        with self._lock:
            self._reread()            # …whatever anyone else wrote since we last looked (see _write)
            self._agents[agent_id] = {"kind": kind, "model": model, "workdir": workdir,
                                      "validator": validator}
            if project:
                # WHOSE ROLE THIS IS. The roster is one server-wide file while the work is per
                # project, and without this the only thing distinguishing another run's validator
                # from yours was the directory it happened to name.
                self._agents[agent_id]["project"] = project
            if oracle_map:
                self._agents[agent_id]["oracle_map"] = oracle_map
            if max_turns:
                # The executor's step budget, declared with the role rather than inherited from
                # whatever the transport defaults to: two runs of "the same agent" under different
                # caps are different agents, and a comparison across them measures the cap.
                self._agents[agent_id]["max_turns"] = int(max_turns)
            if client:
                # WHO this role belongs to — the key of the caller's own lease. A registration is a
                # promise that somebody is there to execute; when that somebody goes, the promise
                # goes with it, and the dispatcher must stop spawning for a role nobody is behind.
                # Measured: a run ended at its ceiling, wrote its record, and the engine went on
                # executing its graph — spending past the envelope and editing the very workspace
                # the recorded result described. Untagged roles stay always-available: this is a
                # lifetime the caller may declare, never one imposed on registrations that predate
                # it or on doors that carry no lease.
                self._agents[agent_id]["client"] = str(client)
            self._write()
        return {"registered": agent_id, **self._agents[agent_id]}

    def unregister(self, agent_id: str, workdir: str | None = None) -> dict:
        """Take a role OUT of the roster — the operation that did not exist.

        Roles accumulated for the life of the installation, and every process that wanted one gone
        hand-edited the shared file, which is how registrations were lost (see `_write`). Optional
        `workdir` makes the removal conditional: withdraw the role only if it still points at the
        directory the caller staffed, so a run tidying up after itself cannot unstaff someone else's
        role that happens to share a name.
        """
        with self._lock:
            self._reread()
            cur = self._agents.get(agent_id)
            if cur is None:
                return {"unregistered": None, "note": f"{agent_id} is not in the roster"}
            if workdir is not None and str(cur.get("workdir") or "") != str(workdir):
                return {"unregistered": None,
                        "note": f"{agent_id} works in {cur.get('workdir')!r}, not {workdir!r} — "
                                f"left alone (a shared roster is not one run's to clear)"}
            del self._agents[agent_id]
            self._write(deleted=(agent_id,))
        return {"unregistered": agent_id}

    def _reread(self) -> bool:
        """Force a re-read of the file, ignoring the mtime cache. Called under the lock, before a
        mutation, so what we write is the file's content plus our one change. False = the file is
        there and could NOT be read, which is the one case a merge must not paper over."""
        self._mtime = None
        return self._load()

    def _write(self, deleted: tuple = ()) -> None:
        """Persist the roster — MERGING into what is on disk, never overwriting it wholesale.

        The roster is one file shared by every session of the one server, and this was a
        read-modify-write over an in-memory snapshot: a process that had loaded the file before
        someone else's registration wrote that registration away. Measured 2026-08-21 — a
        measurement run registered three executors, two test sessions registered their own roles
        minutes later, and by the time the run's node came back for rework NONE of the three
        existed: the dispatcher correctly refused to spawn for an unregistered role, the node stood
        still for twenty-five minutes, and the run ended `graph_stalled`. The roles were not
        withdrawn by anyone; they were overwritten.

        The lock file makes the read-merge-write one step BETWEEN processes as well as inside one.
        Held briefly and broken after ten seconds: a stale lock from a killed process must not take
        delegation down with it, and losing a registration is the failure this exists to prevent —
        so the fallback is to write, not to refuse.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lock = self._path.with_suffix(self._path.suffix + ".lock")
        held = False
        for _ in range(100):
            try:
                fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                held = True
                break
            except FileExistsError:
                try:
                    if time.time() - lock.stat().st_mtime > 10:
                        lock.unlink(missing_ok=True)     # a lock nobody holds any more
                        continue
                except OSError:
                    pass            # the lock vanished under us — the next attempt takes it
                time.sleep(0.05)
        try:
            mine = dict(self._agents)
            # A FAILED READ IS NOT AN EMPTY ROSTER. `_load` keeps the previous in-memory snapshot
            # when the file cannot be parsed — and merging onto a STALE snapshot writes every role
            # registered since it was taken out of existence. That is the same lost-update this
            # merge exists to prevent, arriving through the one path the merge did not check:
            # measured 2026-08-21, two testers' whole rosters (`w7-*`, `w8-*`) gone by the end of the
            # day, and one of them spent the run wondering why no validator ever fired. A partial
            # file under concurrent writes is transient, so it is re-read a few times; if it still
            # cannot be read, this REFUSES rather than writing — losing one registration is
            # recoverable, erasing everyone else's is not.
            ok = self._reread()
            for _ in range(3):
                if ok:
                    break
                time.sleep(0.1)
                ok = self._reread()
            if not ok:
                raise ValueError(
                    f"the roster at {self._path} could not be read, so this registration was NOT "
                    f"written: merging onto what this process last saw would erase every role "
                    f"registered since. Try again in a moment; if it keeps failing the file itself "
                    f"is damaged and needs a look.")
            self._agents.update(mine)                    # …plus every change this process made
            for gone in deleted:                         # …minus what this call removed
                self._agents.pop(gone, None)
            self._path.write_text(json.dumps(self._agents, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
            try:
                self._mtime = self._path.stat().st_mtime
            except OSError:
                self._mtime = None
        finally:
            if held:
                lock.unlink(missing_ok=True)

    def validator_for(self, executor_id: str | None, project: str | None = None) -> str | None:
        """The validation instrument for work done by `executor_id`.

        Order: the executor's own `validator` override → a validator that works in the SAME
        directory → the first registered one.

        The middle step exists because this roster is server-wide while the work is not. "First
        registered" meant the oldest entry on a shared server, so a run's node was judged by another
        run's validator, pointed at another run's workspace: measured 2026-08-20 twice, once with a
        judge whose `workdir` was an experiment's scratch directory. It happened to read the right
        files that time, because the workdir was substituted downstream — a different configuration
        and it would have judged a tree that had nothing to do with the work. Matching on workdir
        picks the instrument that is actually standing where the artifact is; naming `validator=`
        at registration still wins over everything.
        """
        cfg = self.get(executor_id or "") or {}
        if cfg.get("validator"):
            return cfg["validator"]
        self._load()
        # THE PROJECT IS THE ISOLATION BOUNDARY, and the roster is one shared file. A person who
        # registered NOTHING had their nodes judged — and billed — by a validator another run had
        # left in the roster, standing in an experiment's scratch directory: $2.43 of a $4.38 run,
        # four validations nobody asked for (measured on the human door 2026-08-22). A role
        # registered under another project is not this project's instrument.
        if project:
            _judges = {aid: c for aid, c in self._agents.items()
                       if c.get("kind") in ("llm-validator", "unittest-checker")}
            mine = [aid for aid, c in _judges.items() if c.get("project") == project]
            if mine:
                return sorted(mine)[0]
            # A role with NO project is UNSCOPED, not foreign. Excluding it because somebody else's
            # role carried a project left the measurement arm — which registers its roles through
            # the library, without one — with no validator at all: its nodes were never judged and
            # the run ended `validation_stalled` (measured 2026-08-22, my own rule from an hour
            # before). What the project boundary refuses is a role belonging to ANOTHER project.
            unscoped = [aid for aid, c in _judges.items() if not c.get("project")]
            if unscoped:
                return sorted(unscoped)[0]
            if _judges:
                return None      # every judge here belongs to some other project
        wd = cfg.get("workdir")
        if wd:
            same = [aid for aid, c in self._agents.items()
                    if c.get("kind") in ("llm-validator", "unittest-checker") and c.get("workdir") == wd]
            if same:
                return sorted(same)[0]
            # A ROLE THAT WORKS SOMEWHERE ELSE IS NOT THIS WORK'S JUDGE. "First registered" on a
            # server-wide roster means the oldest entry of whoever came first — measured twice on
            # 2026-08-20/21: a run's node judged by another run's validator standing in a scratch
            # directory, and a tester who avoided it only by reading the help. When this executor
            # HAS a workspace and no instrument stands in it, the honest answer is none: the node
            # waits for its issuer, who is told to register one, instead of being judged from a tree
            # that holds none of the work.
            return None
        return self.default_validator()

    def get(self, agent_id: str) -> dict | None:
        self._load()
        return self._agents.get(str(agent_id))

    def list(self) -> dict:
        self._load()
        return dict(self._agents)

    def set_owner_liveness(self, probe) -> None:
        """Install `probe(client_key) -> bool`, the answer to "is the party behind this role still here".

        The leases that answer it live in the HTTP layer, which sits ABOVE this one and which this
        module must not import (the layer gate is a red CI, not a convention). So liveness arrives as
        a function rather than as a lookup: whoever owns the leases installs it, and with nothing
        installed every role is live — the engine keeps working exactly as before for every caller
        that never declared an owner.
        """
        self._owner_live = probe

    def owner_is_live(self, agent_id: str) -> bool:
        """False only when a role NAMES an owner and that owner is gone. Absence of a tag, absence of
        a probe, and a probe that throws all mean "live": a liveness signal nobody supplied must
        never be read as a death, or a missing answer would silently stop work that is fine."""
        cfg = self.get(agent_id) or {}
        client = cfg.get("client")
        probe = getattr(self, "_owner_live", None)
        if not client or probe is None:
            return True
        try:
            return bool(probe(client))
        except Exception:
            return True

    def default_validator(self) -> str | None:
        """The auto-validation instrument: the FIRST registered validator — an `llm-validator` (a fresh
        read-only agent) or a `unittest-checker` (a deterministic hidden-test runner, the issuer's
        oracle). With none registered, validation stays the issuer's manual act."""
        self._load()
        for aid, a in self._agents.items():
            if a.get("kind") in ("llm-validator", "unittest-checker"):
                return aid
        return None


def _executor_packet(engine, task, workdir: str | None) -> str:
    """The executor's self-contained contract (it has no graph access): spec + criteria + upstream
    inputs (the REAL delivered outputs it consumes) + ACCEPTED_RISKS + rework feedback if any."""
    from gfso.tools_llm import _last_deliver_result
    tid = str(task.id)
    crits = "\n".join(f"- **{c.name}**: {c.description}" for c in task.spec.criteria) or "- (none)"
    ups = []
    for e in engine.get_dependencies():
        if str(e.to_id) == tid:
            prod = engine.get_task(TaskId(e.from_id))
            delivered = _last_deliver_result(engine, TaskId(e.from_id)) or "(not delivered yet)"
            name = (prod.spec.name or prod.spec.description[:LABEL_CHARS]) if prod else "?"
            ups.append(f"- input from `{e.from_id}` ({name})"
                       + (f" — glue: {e.glue}" if e.glue else "") + f"\n  its DELIVER: {delivered}")
    # THE OTHER NODES OF THIS PLAN, by id. The packet listed only DECLARED upstream deps, so an
    # executor blocked on work a SIBLING owns had no id to name — and `blocker_task_ids`, the field
    # that records a DISCOVERED dependency and feeds q_Dep, stayed empty. Measured twice on
    # 2026-08-21: a README node spawned into an empty directory and blocked in prose ("workdir is
    # completely empty"), and a packaging node needed a `__main__.py` another child was writing. Both
    # were real Dep edges the plan never declared, and both went unrecorded because whoever
    # discovered them had nothing to point at.
    sibs = []
    parent = engine.get_parent(task.id)
    for k in (engine.get_active_children(parent.id) if parent is not None else ()):
        if str(k.id) != tid:
            sibs.append(f"- `{k.id}` ({k.spec.name or k.spec.description[:40]}) — {k.state.name}")
    negl = "\n".join(f"- {n.item}" for n in task.spec.accepted_risks)
    rework = ""
    if task.state.name == "REWORKING":
        failed = next((list(a.failed_criteria) for a in reversed(engine.audit_log(task.id))
                       if a.signal == Signal.FAIL and not a.rejected and a.failed_criteria), [])
        rework = (f"\n## REWORKING (iteration {task.iteration}) — the validator FAILED these criteria; "
                  f"fix exactly them:\n" + "\n".join(f"- {f}" for f in failed) + "\n")
    return (f"# Your node: {tid} — {task.spec.name}\n\n{task.spec.description}\n\n"
            f"## Criteria (your ENTIRE obligation; each must really hold)\n{crits}\n\n"
            f"## Inputs (upstream deliveries you consume — use the REAL outputs, no stubs)\n"
            f"{chr(10).join(ups) or '- none'}\n\n"
            f"## ACCEPTED_RISKS (declared plan assumptions — do not gold-plate against these)\n"
            f"{negl or '- none'}\n\n"
            f"## The other nodes of this plan — NOT your work, and you must not do it\n"
            f"They are here for one reason: if you cannot proceed because something one of them owns "
            f"does not exist yet, report `status: \"blocked\"` and NAME it in `blocker_task_ids`. That "
            f"is a real dependency the plan did not declare, and naming it is what records it.\n"
            f"{chr(10).join(sibs) or '- none'}\n{rework}\n"
            f"Working directory: {workdir or os.getcwd()}\n")


def _signal(engine, task_id: TaskId, sig: Signal, source: str, **kw) -> bool:
    entry = engine.send_signal_sync(SignalData(signal=sig, task_id=task_id,
                                               source=AgentId(source), **kw))
    ok = bool(entry and not entry.rejected)
    if not ok:
        log.warning(f"delegate: {sig.name} on {task_id} rejected: {entry.error if entry else '?'}")
    return ok


def _settle_internal(engine, task_id: TaskId, self_check: str, _cb) -> None:
    """An INTERNAL node completes on its own self-check — §14.5 D6, read literally.

    The canon does not leave this open. An internal node is one whose Del equals its parent's, and
    of it §14.5 says: it "**self-verifies** — DELIVER carries `self_validation`" — and is "**not**
    independently validated", because "the guarantee for the whole internal decomposition is carried
    by the validation of the agent's public result" (Thm 1, non-redundancy). The agent "stakes all
    internal work on one public validation". There is no second party owed a verdict here: the
    issuer of an internal node IS the same scope as its executor, by the definition that makes the
    node internal. So the PASS the FSM needs is not the system inventing a verdict — it is the
    executor's own verdict, already in the delivery packet, arriving as the signal.

    Without it a subtree delegated to ONE role deadlocks: nothing independent fires (correctly), and
    nothing signs (measured 2026-08-20 on the shipped autonomous demo — a delivery in 57 seconds,
    then half an hour of stillness). Making it wait invents a seam §14.5 says is not there.

    THE THREE CONDITIONS, each from the same passage and none of them negotiable:
      · INTERNAL only. A public node — any root, or any Del ≠ parent's Del — is the seam where the
        independent verdict is the whole point (§14.5: "self-delegation is legitimate iff the
        validating Issuer is independent"). Never relayed there.
      · A DECIDED self-check only. `self_validation` empty ⇒ nothing was checked, and ⊥ is not a
        pass (§11.2). The node then waits for its issuer, and the dispatcher says so.
      · Not when independent validation IS going to run anyway (`GFSO_VALIDATE_INTERNAL=1`, the
        measurement dial) — there the verdict comes from the instrument, and relaying would race it.
    """
    import os
    task = engine.get_task(task_id)
    if task is None or engine._graph.is_public(task):
        return
    if _validate_internal_on():
        return
    if not self_check:
        return
    issuer = str(engine.issuer_of(task_id))
    # …AND IT GOES ON THE RECORD, because a verdict nobody can read afterwards is not evidence that
    # anything was checked. The executor's own words per criterion are what §14.5 asks an internal
    # node to carry, and what the PASS gate below now looks for (measured on the human door
    # 2026-08-21: DELIVER → PASS eight seconds apart, DONE, and `get_verdict` answering "it has not
    # been validated" about the same node).
    # …ONCE. The DELIVER that carried `self_validation` is already recorded by the engine as ONE
    # self-report (`engine/loop.py`), which is what the executor actually said: one word about the
    # delivery as a whole. Re-recording it here fanned that word out into a row per criterion — a
    # stronger claim than the evidence, written over the truthful record, with which of the two
    # survived decided by the route the delivery took (register 2026-08-22, finding 3). So this
    # writes only when nothing is on the record for this delivery.
    if engine.current_exec_verdict(task_id) is None:
        try:
            engine.record_reviewer_verdict(task_id, Verdict.PASS, [], reviewer=str(task.assignee),
                                           observed={c.name: self_check for c in task.spec.criteria})
        except Exception:
            log.warning(f"could not record the internal self-check on {task_id}", exc_info=True)
    if _signal(engine, task_id, Signal.PASS, issuer):
        _cb(f"{task_id}: internal node — PASSED on its own self-check (§14.5 D6: its guarantee is "
            f"carried by the validation of the public result above it)")


def _report_into_signals(engine, task_id, executor_id, task, report: dict, status: str,
                         llm, _cb) -> None:
    """The executor's report, wrapped into the protocol: challenge · block · deliver.

    A delegated round is two jobs — spawn the agent with its packet and account for what it
    cost, then turn what it says into signals the FSM admits. The second is where the
    protocol is actually enforced on a machine executor, and it read as a tail of the first."""
    if status == "challenge":
        # A CHALLENGE is only admissible from OFFERED (§14.3) — the contract is disputed before it
        # is taken, not while reworking under it. An executor reworking a node can still SAY the
        # spec is wrong, and when it does, the signal is refused and the node is left exactly where
        # it was, with its round already spent: nothing spawns it again, ever. Measured 2026-08-21 —
        # a measurement run's leaf challenged during rework at 01:27 and the graph did not move
        # again; the run ended `graph_stalled` twenty-five minutes later. The dispute is not lost
        # and it is not silently converted into work: it is reported where the issuer reads, and the
        # node is put back in the executor's hands so the rework can continue.
        if not _signal(engine, task_id, Signal.CHALLENGE, executor_id,
                       reason=report.get("reason", "")):
            _cb(f"{task_id}: the executor disputes the contract, and a CHALLENGE is not admissible "
                f"in {task.state.name} (§14.3 admits it from OFFERED) — its reason is on the record "
                f"for the ISSUER: {report.get('reason', '')[:400]}. The node stays with its "
                f"executor; to renegotiate, `revise` it (which returns it to OFFERED) — a node "
                f"whose executor has stopped believing in its contract will keep failing it.")
            engine.emit_info("delegate", f"{task_id}: contested during {task.state.name} — "
                                         f"{report.get('reason', '')[:200]}")
            # Not re-spawned: the same executor under the same contract will dispute it again, and
            # that is a paid loop. Recorded as CONTESTED instead, which the frontier hands to the
            # ISSUER as a step of their own — the party who can actually change a contract.
            engine.contest(task_id, report.get("reason", ""))
        else:
            _cb(f"{task_id}: executor CHALLENGED the spec — issuer resolves · {_stat_line(llm)}")
    elif status == "blocked":
        if task.state.name == "OFFERED":  # consent happened (it worked far enough to find the block)
            _signal(engine, task_id, Signal.ACCEPT, executor_id)
        blocker = report.get("blocker_task_id")
        blockers = tuple(TaskId(b) for b in (report.get("blocker_task_ids") or []) if b)
        _signal(engine, task_id, Signal.BLOCK, executor_id, reason=report.get("reason", ""),
                blocker_task_id=TaskId(blocker) if blocker else None,
                blocker_task_ids=blockers)
        _cb(f"{task_id}: executor BLOCKED ({report.get('reason', '')[:80]}) · {_stat_line(llm)}")
    else:  # delivered — the DISPATCHER picks the VALIDATING node up and auto-validates (one path
        # for every delivery, delegated or self-executed; natural node×iteration dedup)
        if task.state.name == "OFFERED":
            _signal(engine, task_id, Signal.ACCEPT, executor_id)
        # THE SELF-CHECK RIDES THE DELIVERY, as §14.2 writes the packet: DELIVER carries
        # `self_validation`. The field was asked for in the report schema, typed in `SignalData`,
        # and then dropped on the floor here — so the one thing §14.5 D6 makes an internal node's
        # completion rest on never reached the graph at all.
        _self = (report.get("self_validation") or "").strip()
        _signal(engine, task_id, Signal.DELIVER, executor_id, result=report["summary"],
                self_validation=Verdict.PASS if _self else None)
        _cb(f"{task_id}: executor DELIVERED · {_stat_line(llm)}")
        _settle_internal(engine, task_id, _self, _cb)


def run_executor(engine, task_id: TaskId, executor_id: str, agents: AgentRegistry,
                 _llm=None) -> dict:
    """ONE delegated execution round: spawn the headless executor with the packet, translate its report
    into FSM signals (its consent = its own report, Inv-1), then auto-validate + auto-verdict if a
    validator instrument is registered. Returns a summary dict (also emitted to the observation field)."""
    from gfso.runtime import llm_factory
    from gfso.adapters.llm.structured import schema_instruction, parse_structured
    from gfso.decompose.loop import _stat_line

    cfg = agents.get(executor_id) or {}
    task = engine.get_task(task_id)
    if task is None:
        return {"error": f"unknown task {task_id}"}

    from gfso.engine.events import emit_cb
    _cb = emit_cb(engine, "delegate")
    llm = _llm or llm_factory(cfg.get("model", MODEL_DEFAULT))
    llm.on_tick = _cb
    llm.stage_hint = f"{task_id} executor({executor_id})"
    # Process cap = the node's deadline when set (§3.5: no second clock — on expiry the process is
    # killed, NO signal forged, the FSM timeout monitor escalates), else the adapter default (15 min).
    cap = None
    if getattr(task, "deadline", None):
        from datetime import datetime
        cap = max(60, int((task.deadline - datetime.now()).total_seconds()))
    _cb(f"{task_id}: executor {executor_id} spawned (workdir={cfg.get('workdir') or 'cwd'}"
        + (f", cap {cap}s" if cap else "") + ")…")
    # The dispatcher's own spawn is the LONGEST thing this server does — up to a fifteen-minute
    # `claude -p` — and it was the one path that never appeared in `busy`, so a reconcile arriving
    # from another session read the server as idle and restarted it mid-run.
    from gfso.tools_llm import _inflight
    system = (_PROMPTS / "executor.md").read_text(encoding="utf-8")
    packet = _executor_packet(engine, task, cfg.get("workdir"))
    with _inflight("delegated_execution"):
        try:
            text = llm.run_agent(system, packet + schema_instruction(EXECUTOR_SCHEMA),
                                 allowed_tools=EXECUTOR_TOOLS, cwd=cfg.get("workdir"), timeout=cap,
                                 max_turns=cfg.get("max_turns"))
        except TypeError:  # a runner without the timeout/turn-cap params (fakes)
            text = llm.run_agent(system, packet + schema_instruction(EXECUTOR_SCHEMA),
                                 allowed_tools=EXECUTOR_TOOLS, cwd=cfg.get("workdir"))
    if hasattr(llm, "tag_last"):
        llm.tag_last(Stage.EXECUTOR)
    engine.record_llm_usage(Stage.EXECUTOR, llm, task_id)      # the work's own spend, per node
    report = parse_structured(text, EXECUTOR_SCHEMA)
    if report is None:
        # No signal is forged on a broken report: the node stays where it is; the FSM's own timeout
        # monitor escalates a stuck node (no second clock). Visible in the observation field.
        _cb(f"{task_id}: executor report DID NOT PARSE — no signals sent; issuer attention needed "
            f"· executor {_stat_line(llm)}")
        return {"task_id": str(task_id), "status": "unparsed", "report_text": text,
                "stats": list(getattr(llm, "calls", []))}

    status = report["status"]
    _report_into_signals(engine, task_id, executor_id, task, report, status, llm, _cb)
    return {"task_id": str(task_id), "status": status,
            "stats": list(getattr(llm, "calls", []))}


def _oracle_workdir(engine, vcfg: dict):
    """The workspace for this project from the issuer-side oracle map (same map the unittest-checker
    uses), so a criteria-judge validator runs the code where the executor delivered it. None if absent."""
    import json
    from pathlib import Path
    project = getattr(engine, "_project_name", None) or "default"
    try:
        entry = json.loads(Path(vcfg["oracle_map"]).read_text(encoding="utf-8")).get(project)
        return entry.get("workdir") if entry else None
    except Exception:
        return None


def _checker_validate(engine, task_id: TaskId, vcfg: dict) -> dict:
    """Deterministic HIDDEN-TEST validation (the issuer's oracle — the executor never sees the tests).
    Runs the project's hidden unittest suite against the delivered solution.py, maps each test method
    to the criterion of the same name, returns {verdict, per_criterion, failed_criteria}. No LLM, no
    false-PASS. The oracle map (config: `oracle_map`) is issuer-side; the agent has no path to it.
    It has NO default: a shipped default pointed every install at one experiment's map file, which
    on any other machine simply did not exist — a registration that names no map now says so."""
    import json
    from pathlib import Path
    from gfso.adapters.verifiers import evaluate_unittest
    project = getattr(engine, "_project_name", None) or "default"
    try:
        entry = json.loads(Path(vcfg["oracle_map"]).read_text(encoding="utf-8")).get(project)
    except Exception:
        entry = None
    if not entry:
        return {"verdict": None, "note": f"no hidden-test oracle registered for project {project}"}
    crits = entry["criteria"]
    sol = Path(entry["workdir"]) / "solution.py"
    if not sol.exists():
        return {"verdict": Verdict.FAIL, "failed_criteria": list(crits),
                "per_criterion": [{"criterion": c, "verdict": "fail",
                                   "evidence": "no solution.py delivered"} for c in crits]}
    results = evaluate_unittest(sol.read_text(encoding="utf-8"),
                               Path(entry["canonical"]).read_text(encoding="utf-8"))
    by = {r.check_name: r for r in results}
    per, failed = [], []
    for c in crits:
        r = by.get(c)
        ok = bool(r and r.passed)
        per.append({"criterion": c, "verdict": "pass" if ok else "fail",
                    "evidence": ("passed" if ok else (r.details[:400] if r else "test not found in suite"))})
        if not ok:
            failed.append(c)
    return {"verdict": Verdict.PASS if not failed else Verdict.FAIL, "per_criterion": per, "failed_criteria": failed}


def _children_workdir(engine, agents: AgentRegistry, task_id: TaskId) -> str | None:
    """Where this node's work actually lives: the workdir of a registered child executor.

    A parent whose own Del is the unregistered user-agent has no directory of its own, but its
    children do — and their directory is the one holding the artifact the parent aggregates."""
    for kid in engine._graph.get_active_children(task_id):
        if (wd := (agents.get(kid.assignee or "") or {}).get("workdir")):
            return wd
    return None


def _judge_with(engine, agents, task_id, task, validator_id, vcfg, sign, T,
                model_override, _llm) -> dict:
    """Run whichever instrument this node is bound to, and hand back its report.

    Two instruments under one contract (`{verdict, per_criterion, failed_criteria}`) and very
    different economics: the deterministic oracle runs a hidden suite in seconds, the
    read-only validator spends a model run. Which is bound is the roster's business; the
    caller only needs the report."""
    if vcfg.get("kind") == "unittest-checker":
        # deterministic hidden-test oracle — runs the suite the executor never sees, records the
        # per-criterion verdict (the integrity gate applies), then auto-signals below.
        generation = engine.generation_of(task_id)     # the delivery THIS check reads (§14.5 gate)
        out = _checker_validate(engine, task_id, vcfg)
        if out.get("verdict") in (Verdict.PASS, Verdict.FAIL):
            try:
                engine.record_exec_verdict(task_id, out["verdict"], out.get("failed_criteria") or [],
                                           validator_id, per_criterion=out.get("per_criterion"),
                                           generation=generation)
            except Exception as e:  # a malformed report is ⊥, not a verdict (§10) — never auto-signal it
                engine.emit_info("delegate", f"{task_id}: checker verdict refused ({e})")
                out = {"verdict": None}
        f = out.get("failed_criteria") or []
        engine.emit_info("delegate", f"{task_id}: unittest-checker → {out.get('verdict')}"
                         + (f" (failed: {', '.join(f)})" if f else ""))
    else:
        ecfg = agents.get(task.assignee) if task else None   # validate WHERE the executor worked
        # The criteria-judge validator must run the code IN the workspace. When neither the executor nor
        # the validator config pins a workdir (self-execution: the executor is the unregistered user-agent),
        # fall back to the issuer-side oracle map, where setup records this project's workspace.
        # …and when the executor has none, the CHILDREN's workdir before the validator's own. The
        # validator's registered directory is a roster fact; where the work IS is a graph fact, and
        # only the second one is true by construction. Measured 2026-08-21: a stale `val-1` entry
        # from an older experiment pointed at a scratch directory, the root was judged there, the
        # report said "no implementation exists" — and a FALSE FAIL over seventeen criteria drove
        # the run into the rework loop that ended it. The snapshot taken at that same delivery holds
        # every file the validator could not find.
        _wd = ((ecfg or {}).get("workdir") or _children_workdir(engine, agents, task_id)
               or vcfg.get("workdir") or _oracle_workdir(engine, vcfg))
        out = T.TOOLS["validate_result"](engine, str(task_id),
                              model=model_override or vcfg.get("model", MODEL_DEFAULT),
                              workdir=_wd, validator=str(validator_id), _llm=_llm)


    return out


def _auto_validate(engine, task_id: TaskId, agents: AgentRegistry, _llm=None,
                   model_override: str | None = None, sign: bool = True) -> str | None:
    """DELIVER→VALIDATING auto-fires the registered validator instrument; the verdict AUTO_PASS-SIGNALS
    (PASS → DONE; FAIL(failed_criteria) → REWORKING — the rework loop lives in the FSM, max_iterations
    bounds it). verdict:null NEVER auto-signals — the one escalation to the issuer. Returns the
    outcome for the dispatcher: 'pass'/'fail' (signed), 'rejected' (the FSM refused the verdict —
    ≠ no-verdict: the graph wasn't ready, revalidate on its next change), 'no-verdict'."""
    from gfso import tools_llm as T

    task = engine.get_task(task_id)
    _proj = engine.project_name
    validator_id = agents.validator_for(task.assignee if task else None, project=_proj)
    # A node whose executor is the UNREGISTERED user-agent (the root, and every node the agent keeps
    # for itself) has no workdir of its own, so the workspace-matching rule above has nothing to
    # match on and falls back to "first registered" — which is another run's judge. Measured
    # 2026-08-20: a root was judged by `val-1` from an experiment, whose workdir pointed at that
    # experiment's scratch directory. The graph knows what the right answer is: this project's
    # CHILDREN are delegated to registered executors, and their workdir is where the work lives.
    if task is not None and not (agents.get(task.assignee or "") or {}).get("workdir"):
        for kid in engine._graph.get_active_children(task_id):
            if (wd := (agents.get(kid.assignee or "") or {}).get("workdir")):
                if (near := agents.validator_for(kid.assignee, project=_proj)):
                    validator_id = near
                break
    if validator_id is None:
        engine.emit_info("delegate", f"{task_id}: no llm-validator registered — validation stays manual")
        # …AND SAID AS ITSELF, not as a failure. This returned a bare None, which the caller reads as
        # "the run died", so a graph that simply never had an instrument was given a retry (one paid
        # model run) and then PARKED for its issuer as "validator produced no verdict twice". An
        # absence of an instrument and an instrument that failed are opposite facts.
        return "no-instrument"
    # A FRESH recorded verdict for the CURRENT generation (e.g. the agent already ran a manual
    # validate_result) is signed directly — spawning another validator run would duplicate minutes
    # of agent work for the same evidence (observed live: one duplicate per rework cycle).
    # BUT a deterministic hidden-test oracle (unittest-checker) is CHEAP (runs the suite in seconds)
    # and AUTHORITATIVE (the issuer's ground truth) — it must NOT be pre-empted by a recorded LLM
    # verdict. Observed live (floor_17): the checker returned FAIL, the agent then ran validate_result
    # which returned a shallow PASS over its own incomplete mock, and reuse signed that PASS — a false
    # close. So reuse applies only when the assigned validator is the expensive LLM kind; for a
    # unittest-checker the oracle always runs, and only ITS OWN verdict is ever reused.
    _vkind = (agents.get(validator_id) or {}).get("kind")
    rec = engine._graph.exec_verdict_record(task_id)
    # …and "current" means the SAME thing here as at the gate that will judge this verdict — one
    # owner (`verdict_is_current_pass`), plus the FAIL case this reuse also covers. It compared
    # iteration and reopens and not revisions, so a verdict from before a revision could be reused
    # for a delivery under a different contract.
    _gen_ok = (rec is not None and task is not None
               and all(rec.get(k, 0) == getattr(task, k, 0)
                       for k in ("iteration", "reopens", "revisions")))
    if (_vkind != "unittest-checker" and _gen_ok
            and rec.get("verdict") in (Verdict.PASS, Verdict.FAIL)):
        if not sign:
            # A verdict for THIS delivery already stands and the signature is not ours to give, so
            # there is nothing left to do — and certainly not another paid run over the same
            # delivery, which is what happened while this path went on to signal (measured on the
            # human door 2026-08-22).
            engine.emit_info("delegate", f"{task_id}: already judged for this delivery — verdict "
                                         f"{rec['verdict']} stands on the record; signing is yours.")
            return "recorded"
        engine.emit_info("delegate", f"{task_id}: fresh recorded verdict {rec['verdict']} reused — "
                                     f"no duplicate validator run")
        sig = Signal.PASS if rec["verdict"] == Verdict.PASS else Signal.FAIL
        if _signal(engine, task_id, sig, validator_id,
                   **({"failed_criteria": tuple(rec.get("failed_criteria") or ())}
                      if sig == Signal.FAIL else {})):
            return "pass" if sig == Signal.PASS else "fail"
        engine.emit_info("delegate", f"{task_id}: reused verdict {rec['verdict']} REJECTED by the "
                                     f"FSM — the node revalidates on the graph's next change")
        return "rejected"
    vcfg = agents.get(validator_id) or {}
    out = _judge_with(engine, agents, task_id, task, validator_id, vcfg, sign, T,
                      model_override, _llm)
    if out.get("inflight") or out.get("waiting_on"):
        # Neither of these is a failed judgement, so neither may cost the node its one
        # no-verdict retry: `inflight` = another validator run (e.g. a manual `validate_result`)
        # already holds this generation; `waiting_on` = the node aggregates children that have
        # not settled, so there is nothing to judge yet (Thm 1). Both behave like a rejected
        # verdict — free the dedup key and revalidate on the graph's next change.
        engine.emit_info(
        "delegate",
        f"{task_id}: validator already in flight — duplicate spawn suppressed"
        if out.get("inflight") else
        f"{task_id}: not judged yet — waiting on {', '.join(out['waiting_on'])}")
        return "rejected"
    verdict = out.get("verdict")
    if not sign:
        # THE INSTRUMENT RAN; THE SIGNATURE IS NOT THE INSTRUMENT'S TO GIVE. A human issuer who
        # registers a validator has asked for the judging, not for the decision — §14.5 keeps the
        # verdict the issuer's act, and what the instrument owes them is the record. Measured on two
        # doors 2026-08-21: both testers registered an `llm-validator`, kept the root for themselves,
        # and watched nothing happen at all, because the path was skipped whole rather than split at
        # the signature. `register_agent` had promised it fires "on EVERY delivery".
        if verdict:
            engine.emit_info(
                "delegate",
                f"{task_id}: validated for you — the verdict is {verdict}, on the record "
                f"(`get_verdict {task_id}`). Signing is yours: `signal {task_id} {verdict} <you>` "
                f"when you agree with it.")
        return "recorded" if verdict else "no-verdict"
    if verdict == Verdict.PASS:
        if _signal(engine, task_id, Signal.PASS, validator_id):
            return "pass"
    elif verdict == Verdict.FAIL:
        if _signal(engine, task_id, Signal.FAIL, validator_id,
                   failed_criteria=tuple(out.get("failed_criteria") or ())):
            return "fail"
    else:  # null/error — never auto-signal an unparsed verdict
        # The report is kept on disk, not merely "in the tool's output": under delegation the tool's
        # caller is this dispatcher, which reads a verdict and nothing else, so the old wording named
        # a place no one could look — and the evidence for why a validator could not state a verdict
        # was gone by the time anyone asked.
        engine.emit_info("delegate",
                         f"{task_id}: validator verdict UNPARSED/error — issuer must decide"
                         + (f" (report: {out['report_kept_at']})" if out.get("report_kept_at")
                            else " (report not kept — see the validate_result output)"))
        return "no-verdict"
    engine.emit_info("delegate", f"{task_id}: validator verdict {verdict} REJECTED by the FSM — "
                     f"the node revalidates on the graph's next change")
    return "rejected"


class Dispatcher:
    """The autostart engine: EVENT-DRIVEN — every graph transition (the same bus the UI/WS listens on)
    wakes a frontier re-evaluation, so an executor-actionable step whose Del is a REGISTERED llm-executor
    is picked up within milliseconds (dedup per node×iteration; small concurrency cap). The periodic wait
    is only a safety net for an event missed while a run was in flight — dispatch_once is idempotent, so an
    extra pass is free."""

    def __init__(self, engine, agents: AgentRegistry, poll: float = 15.0, max_concurrent: int = 4,
                 runner=run_executor, validator_runner=None):
        self._engine, self._agents, self._poll = engine, agents, poll   # poll = safety-net interval
        self._cap = threading.Semaphore(max_concurrent)
        self._runner = runner
        self._validate = validator_runner or _auto_validate
        self._retry_model: dict = {}   # round key → the tier its RETRY should use
        self._seen: set[str] = set()      # "{task}#{iter}" / "v:{task}#{iter}" — one run per round
        self._lapsed_said: set[str] = set()   # roles whose owner's departure is already on the record
        # …and the claim on a key is ATOMIC. The dedup was a bare check-then-add over a set, and
        # `dispatch_once` runs from two places by design — the poll loop and the transition wake — so
        # two rounds could both read "not seen" before either wrote, and the node was executed TWICE:
        # two paid agent runs on one contract, writing the same files. Measured live (an unrelated
        # timing change in the roster read was enough to open the window every time), which is what a
        # latent race does — it waits for the schedule to shift.
        self._claim_lock = threading.Lock()
        self._retried: set[str] = set()   # validator no-verdict retries (one per node×iteration)
        self._stop = threading.Event()
        self._dirty = threading.Event()   # set by every transition → the loop re-evaluates the frontier
        # Subscribed HERE, not in `start()`: the callback no longer only sets a flag — it is what
        # makes a cleared block executable again (see `_on_bus`), and that must not depend on
        # whether this dispatcher's poll loop was ever started.
        self._engine.on_transition(self._on_bus)

    def _deps_ready(self, task_id: TaskId) -> bool:
        """An executor spawn is useless before the node's Dep PRODUCERS deliver — it hits a missing
        input and BLOCKs (observed live). Gate accept-step spawns on producer DONE. A producer node
        that does not EXIST yet counts as NOT ready: during a build the consumer's ASSIGN can land
        milliseconds before its producer's (observed live — the consumer slipped the gate and burned
        a doomed run); the producer's own ASSIGN wakes the loop, so no liveness is lost."""
        tid = str(task_id)
        for e in self._engine.get_dependencies():
            if str(e.to_id) == tid:
                prod = self._engine.get_task(TaskId(e.from_id))
                if prod is None or prod.state.name != "DONE":
                    return False
        return True

    def _resolve_ready_blocks(self) -> None:
        """Auto BLOCK resolution: BLOCKED-on-nodes resolves once every EXISTING producer is DONE.
        Adjudication follows the PROVISIONAL edges this node's BLOCK recorded: all sources real →
        confirm all; some mis-named PHANTOM sources (nonexistent nodes — observed live) → the corrected
        set = the real sources (SET semantics drops only the bogus edges, never the real ones); all
        phantom → external=True. External blocks stay for a human. The unblocked node's spawn-dedup
        key is dropped so a FRESH executor run picks it up."""
        from gfso.core.types import State
        for t in self._engine.tasks_by_state(State.BLOCKED):
            if not self._issuer_is_automated(t.id):
                continue
            deps_in = [e for e in self._engine.get_dependencies() if str(e.to_id) == str(t.id)]
            if not deps_in:
                continue
            existing = [e.from_id for e in deps_in
                        if self._engine.get_task(TaskId(e.from_id)) is not None]
            if all(self._engine.get_task(TaskId(x)).state.name == "DONE" for x in existing):
                # keyed on the BLOCKED EPISODE, not the iteration: the guard exists to stop a
                # second signal inside one episode, and a node may block twice under the same
                # contract — with `#iteration` the second block found the key spent and was never
                # auto-resolved at all.
                key = f"rb:{t.id}#{getattr(t, 'state_entered_at', None)}"
                if key in self._seen:
                    continue
                self._seen.add(key)
                issuer = str(self._engine.issuer_of(t.id))
                prov = [e.from_id for e in deps_in if getattr(e, "provisional", False)]
                prov_real = [x for x in prov
                             if self._engine.get_task(TaskId(x)) is not None]
                if len(prov_real) == len(prov):
                    _signal(self._engine, t.id, Signal.RESOLVE_BLOCK, issuer, action="confirm")
                elif prov_real:
                    _signal(self._engine, t.id, Signal.RESOLVE_BLOCK, issuer,
                            blocker_task_ids=tuple(TaskId(x) for x in prov_real))
                else:
                    _signal(self._engine, t.id, Signal.RESOLVE_BLOCK, issuer, external=True)
                self._seen.discard(self._round_key(t))
                self._engine.emit_info("delegate",
                                       f"{t.id}: producers DONE — RESOLVE_BLOCK (auto), executor re-queued")

    def _validate_here(self, task) -> bool:
        """D6 (§14.5) — validation-at-the-seam: the independent validator instrument auto-fires on
        PUBLIC nodes (a root, or Del(child) ≠ Del(parent)); an INTERNAL node (the executor's own
        private decomposition) self-verifies via its DELIVER self_validation, and its guarantee is
        carried by the public result's validation (Thm 1). NOT validate-every-node — per-node
        instrumenting stays available as an OPT-IN dial: GFSO_VALIDATE_INTERNAL=1 restores the
        every-delivery behavior (useful for measurement runs, harmless for correctness)."""
        import os
        if task is None:
            return True
        if _validate_internal_on():
            return True
        return self._engine._graph.is_public(task)

    def _issuer_is_automated(self, task_id: TaskId) -> bool:
        """Is this node's ISSUER automated — the standing agent id, or a registered participant?

        A person is any OTHER name: their node is judged and recorded and then waits for them to
        signal (§14.5 keeps the verdict the issuer's act). The line falls exactly there and nowhere
        else — which matters, because the default identity on every door is the standing agent, so a
        person who never names themselves IS the standing agent as far as this question goes, and
        their nodes auto-sign. Measured 2026-08-22: a tester driving the CLI as the default identity
        watched six of six nodes signed for them while the roster's own help promised the opposite.
        Naming yourself (`source=<your name>`, and an `assignee` of your own) is what makes you a
        person here."""
        from gfso.tools import _agent_id
        issuer = str(self._engine.issuer_of(task_id))
        return issuer == _agent_id() or self._agents.get(issuer) is not None

    def _drop_keys(self, tid: str) -> None:
        """Forget every dedup key of a node — targeted discards (a concurrent worker may be
        discarding its own key at the same moment; never rebuild the sets wholesale)."""
        heads = (tid, f"v:{tid}", f"rb:{tid}")
        for bag in (self._seen, self._retried):
            for k in [k for k in bag if k.rsplit("#", 1)[0] in heads]:
                bag.discard(k)

    def _children_settled(self, task_id: TaskId) -> bool:
        """A parent's verdict is structurally rejected until ALL its children PASS (Theorem-1 gate) —
        a validator run before that is a guaranteed-wasted spawn (observed live: two doomed PASSes)."""
        kids = self._engine.get_active_children(task_id)
        return all(passed(k) for k in kids)

    def _round_key(self, task, prefix: str = "") -> str:
        """The dedup key of a node's CURRENT round: id + the generation that makes it a round.

        It used to be id + iteration only, and a revision moves neither iteration nor reopens — so a
        revised node kept a key that was already spent and was never re-executed. That was patched by
        MARKING revised nodes and dropping their keys on the next pass, and the patch had its own
        defect: the mark fired on EVERY ASSIGN, creation included, so a node's key could be dropped
        moments after its first claim and the node was executed TWICE (two paid runs, one contract —
        measured live). Putting the generation IN the key removes both: a revision is a new round by
        construction, and nothing has to be un-remembered."""
        return (f"{prefix}{task.id}#{getattr(task, 'iteration', 0)}"
                f"#{getattr(task, 'reopens', 0)}#{getattr(task, 'revisions', 0)}")

    def _admissible(self, task_id: TaskId) -> bool:
        """Would the node's first execution step be ADMITTED? Asked before paying for it.

        The execution gate lives on the ACCEPT signal, and the dispatcher spawns the executor BEFORE
        that signal exists — the run's report is what produces it. So a leaf under a plan the gate
        refuses had its executor spawned, worked, and reported, and only then was the ACCEPT rejected:
        a paid call thrown away, repeatedly, while the plan sat unfixed. This asks the gate's own
        question first, exactly as `_deps_ready` asks the dependency one."""
        return self._engine.execution_blocked_by(task_id) is None

    def _claim(self, key: str) -> bool:
        """Claim a round for a node ONCE: True to the first caller, False to everyone after.

        The check and the write have to be one step. `dispatch_once` is called from the poll loop AND
        from the transition wake (that is the point of an event-driven dispatcher), so a bare
        `if key not in seen: seen.add(key)` lets two rounds through — and each spends a real agent
        call on the same contract."""
        with self._claim_lock:
            if key in self._seen:
                return False
            self._seen.add(key)
            return True

    def _dispatch_steps(self, out: dict, started: list) -> None:
        """Act on each frontier step: fire the instrument on a delivery, or spawn work.

        `dispatch_once` is one poll ROUND — publish the roster, resolve ready blocks, then
        act — and the acting had grown to a hundred and thirty statements inside it, so the
        round's own shape was invisible. This is the acting; the round is what calls it."""
        for s in out.get("steps", []):
            task = self._engine.get_task(TaskId(s["task_id"]))
            it = getattr(task, "iteration", 0)
            _proj = self._engine.project_name
            if (s.get("action") == Action.VALIDATE
                    and self._agents.validator_for(s.get("assignee"), project=_proj) is not None):
                # A HUMAN ISSUER KEEPS THEIR VERDICT — and not the judging. Skipping the whole path
                # meant a person who had registered an `llm-validator` and bound it to their executor
                # got nothing at all: the node sat in VALIDATING with the instrument idle, on both
                # doors, while `register_agent` promised it fires "on EVERY delivery" (measured
                # 2026-08-21). Registering an instrument IS asking for the judging; §14.5 keeps only
                # the signature theirs. So it runs and RECORDS, and the person signs.
                _sign = self._issuer_is_automated(TaskId(s["task_id"]))
                if not self._validate_here(task):
                    # D6 (§14.5): an INTERNAL node (its Del is its parent's) self-verifies, and no
                    # independent validator is spawned — but nothing then SIGNS it either, so the
                    # node sits in VALIDATING until its issuer acts. Measured 2026-08-20 on the
                    # shipped autonomous demo, whose whole subtree is delegated to ONE executor:
                    # every child is internal by construction, the delivery landed in 57 seconds,
                    # and the graph then stood still for half an hour with nothing to read. Said
                    # once per delivery; the decision itself stays the issuer's.
                    _key = f"internal:{self._round_key(task, 'v:')}"
                    if _key not in self._lapsed_said:
                        self._lapsed_said.add(_key)
                        self._engine.emit_info(
                            "delegate",
                            f"{s['task_id']}: delivered and NOT auto-validated — it is an internal "
                            f"node (its Del is its parent's), which §14.5 D6 lets self-verify: its "
                            f"guarantee is carried by the validation of the public result above it. "
                            f"It waits for its issuer ({self._engine.issuer_of(TaskId(s['task_id']))}) "
                            f"to signal PASS/FAIL. To have every node independently judged instead, "
                            f"set GFSO_VALIDATE_INTERNAL=1; to make it a seam, give it a different "
                            f"executor from its parent's.")
                    continue
                if not self._children_settled(TaskId(s["task_id"])):
                    # …and say which children, once. Skipping is right — the verdict would be
                    # rejected at the gate (Thm 1: the parent is the AND over its children) — but in
                    # silence a delivered parent looks like a validator that never came. Measured
                    # 2026-08-20 on a live run: a root sat in VALIDATING for nineteen minutes after
                    # its own repair added a child, with `busy: []` and nothing to read.
                    _open = [f"'{k.id}' is {k.state.name}"
                             for k in self._engine.get_active_children(TaskId(s["task_id"]))
                             if not passed(k)]
                    _key = f"kids:{s['task_id']}#{','.join(sorted(_open))}"
                    if _open and _key not in self._lapsed_said:
                        self._lapsed_said.add(_key)
                        self._engine.emit_info(
                            "delegate",
                            f"{s['task_id']}: delivered, but not validated yet — it aggregates "
                            f"children that have not settled ({'; '.join(_open)}). A verdict now "
                            f"would be refused at the gate, so none is spent. Drive those nodes; "
                            f"validation follows by itself.")
                    continue
                if self._claim(self._round_key(task, "v:")):
                    started.append(f"validate:{s['task_id']}")
                    threading.Thread(target=self._validate_guarded,
                                     args=(TaskId(s["task_id"]), it, _sign), daemon=True).start()
                continue
            if s.get("action") not in SPAWNABLE_ACTIONS:
                continue
            if not self._deps_ready(TaskId(s["task_id"])):
                continue                   # spawning before the producers deliver ⇒ instant BLOCK
                                           # EVERY executor spawn, not the first one only: the gate
                                           # asked its question on `accept` alone, so a node already
                                           # past that step — resumed after a cleared block, re-queued
                                           # out of REWORKING, or given a Dep AFTER it started — was
                                           # spawned against an input that does not exist yet, and
                                           # blocked itself on arrival. A paid run whose only possible
                                           # outcome is the BLOCK it already reported.
            if s.get("action") == Action.ACCEPT and not self._admissible(TaskId(s["task_id"])):
                # …and SAY SO, once per node. The gate is right (§13.4: a plan that has not passed
                # its checks does not start, and the ACCEPT would be refused with the executor's
                # work), but silence made it indistinguishable from a dead dispatcher. Measured on
                # the shipped `autonomous_org` demo, which drives only this loop and never the
                # frontier's own review step: two children sat in OFFERED for half an hour over an
                # empty workspace, with nothing anywhere saying why.
                _p = self._engine._graph.get_parent(TaskId(s["task_id"]))
                _key = f"gate:{s['task_id']}"
                if _p is not None and _key not in self._lapsed_said:
                    self._lapsed_said.add(_key)
                    self._engine.emit_info(
                        "delegate",
                        f"{s['task_id']}: not started — its parent's plan ('{_p.id}') is not "
                        f"admitted to execution yet (§13.4). `next_steps` names the step that opens "
                        f"it: review_decomposition('{_p.id}'), or closing the holes it lists. "
                        f"Nothing is lost; dispatch resumes the moment the plan passes.")
                continue
            cfg = self._agents.get(s.get("assignee") or "")
            if cfg is None:
                # Unregistered Del = a human (or an external system): the dispatcher stays passive,
                # correctly — but said once, because a node that simply never starts looks like a
                # broken dispatcher. The live case that made this matter: a plan repair ADDED a
                # child, which was created with its author's own id rather than a registered
                # executor's, and in a delegated run it landed on nobody at all.
                _key = f"unowned:{s['task_id']}#{s.get('assignee')}"
                if _key not in self._lapsed_said:
                    self._lapsed_said.add(_key)
                    self._engine.emit_info(
                        "delegate",
                        f"{s['task_id']}: not started — Del is '{s.get('assignee')}', which is not a "
                        f"registered executor, so this node waits for THAT party's own signals. "
                        f"If it was meant to be delegated, `reassign` it to a registered role; if "
                        f"it is yours, drive it yourself (`next_steps` carries its directive).")
                continue
            if cfg.get("kind") != "llm-executor":
                self._engine.emit_info("delegate",
                                       f"{s['task_id']}: Del={s['assignee']} is a registered "
                                       f"{cfg.get('kind')} — not an executor kind, nothing to start")
                continue
            if not self._agents.owner_is_live(s.get("assignee") or ""):
                # The party that registered this role is gone. Nothing is cancelled and no state
                # moves — the node keeps its place and resumes the moment the owner returns; what
                # stops is the spawning of work nobody is waiting for. Said ONCE per role, because
                # the alternative is a line per dispatch cycle for as long as the project sits.
                if (s.get("assignee") or "") not in self._lapsed_said:
                    self._lapsed_said.add(s.get("assignee") or "")
                    self._engine.emit_info(
                        "delegate",
                        f"{s['task_id']}: {s['assignee']}'s owner ({cfg.get('client')}) is gone — "
                        f"dispatch for that role stops here; nothing is cancelled, and it resumes "
                        f"when the same owner returns")
                continue
            self._lapsed_said.discard(s.get("assignee") or "")
            if not self._claim(self._round_key(task)):
                continue
            started.append(s["task_id"])
            threading.Thread(target=self._run_guarded,
                             args=(TaskId(s["task_id"]), s["assignee"], it), daemon=True).start()

    def dispatch_once(self) -> list[str]:
        """One poll round (the testable unit): spawn executor runs for executor-ready steps AND the
        auto-validation for EVERY freshly delivered node (delegated or self-executed — one path;
        fires only when an llm-validator is registered AND the node's issuer is automated, else
        validation stays the issuer's act)."""
        if getattr(self._engine, "_dispatch_quiesce", 0):
            return []      # a wholesale build/rebuild is mid-burst — dispatch on the settled graph only
        # the FSM accepts a registered validator's PASS/FAIL as the issuer's role-V instrument (§14.5) —
        # both the LLM validator (a fresh read-only agent) and the deterministic unittest-checker
        _roster = self._agents.list()
        self._engine._graph.authorized_executors = {
            aid for aid, cfg in _roster.items() if cfg.get("kind") == "llm-executor"}
        self._engine._graph.authorized_validators = {
            aid for aid, cfg in _roster.items()
            if cfg.get("kind") in ("llm-validator", "unittest-checker")}
        # …and WHO ELSE is registered, published downward for the read surfaces. `gfso.tools` is the
        # layer below this one (core+engine only, held by `test_layering`) and must not import the
        # dispatcher to find out that a node's Del is a machine — but it is the difference between
        # "the graph waits for a person" and "the dispatcher has it in hand", and a driving agent
        # reported itself blocked on a human over exactly that (2026-08-20).
        self._engine._roster = {aid: cfg.get("kind") for aid, cfg in _roster.items()}
        self._resolve_ready_blocks()
        started = []
        out = self._engine.next_steps()
        # A NODE THE PLAN GATE HOLDS BACK IS NOT A STEP — it is in `waiting`, because offering an
        # ACCEPT the engine refuses cost whoever obeyed it a call (measured on the MCP door
        # 2026-08-21). It still has to be SAID, once per node: a gate that only refuses is
        # indistinguishable from a dead dispatcher (the `autonomous_org` case, half an hour of
        # silence over an empty workspace).
        for w in out.get("waiting", []):
            # THE KIND, not the shape of a neighbouring field. This skipped an entry that had no
            # `opens_with`, on the assumption that dep-order waits carry none — they do, so a
            # dependency wait was narrated as a plan-gate hold, with a list repr and the wrong
            # canon citation (register 2026-08-22, finding 1).
            if w.get("kind") == "dependency" or not (_opens := w.get("opens_with")):
                continue                       # dep-order waits are read from `waits_on` instead
            _key = f"gate:{w['task_id']}"
            if _key in self._lapsed_said:
                continue
            self._lapsed_said.add(_key)
            self._engine.emit_info(
                "delegate",
                f"{w['task_id']}: not started — {', '.join(w['waits_on'])} is not admitted to "
                f"execution yet "
                f"(§13.4): {w['why']}. The step that opens it: {_opens}. Nothing is lost; dispatch "
                f"resumes the moment the plan passes.")
        self._dispatch_steps(out, started)
        return started

    _EXECUTOR_STATES = ("OFFERED", "EXECUTING", "REWORKING")

    def _fresh(self, task_id: TaskId, expect_iter: int, states: tuple,
               executor_id: str | None = None) -> bool:
        """TOCTOU guard: the dispatch decision can be minutes older than the semaphore slot (observed
        live — a queued second-generation run fired on a node that had DELIVERED meanwhile). Re-check
        the node right before spending an LLM run; a stale slot is dropped silently — if the node is
        genuinely actionable again, a later pass re-dispatches it under a fresh key.

        DEL IS PART OF WHAT GOES STALE. The check looked at the state and the iteration only, so a
        node REASSIGNED between the queue and the slot was still run as the old executor — and every
        signal that run made came back "exec-1 is not executor for root.matcher (executor=exec-2)".
        Measured on a live E3 run 2026-08-22: an ACCEPT, a second ACCEPT and a DELIVER all refused,
        the run paid for, and the graph stalled for ten minutes with the frontier repeating a step
        the dispatcher could not take."""
        t = self._engine.get_task(task_id)
        if t is None or t.state.name not in states or getattr(t, "iteration", 0) != expect_iter:
            self._engine.emit_info("delegate",
                                   f"{task_id}: queued run is stale (state {t.state.name if t else '?'}"
                                   f") — slot released")
            return False
        if executor_id is not None and str(t.assignee) != str(executor_id):
            # …and the ROUND is freed with it. A reassignment moves no generation counter, so the
            # round key is unchanged and a released slot would otherwise be a claim nobody ever
            # spends: the node would sit forever, which is the same stall by another road.
            self._seen.discard(self._round_key(t))
            self._engine.emit_info(
                "delegate", f"{task_id}: queued run is stale — it was queued for '{executor_id}' and "
                            f"Del is now '{t.assignee}'; slot released, the next pass dispatches it "
                            f"to the executor that holds it")
            return False
        return True

    def _run_guarded(self, task_id: TaskId, executor_id: str, expect_iter: int = 0) -> None:
        with self._cap:
            if not self._fresh(task_id, expect_iter, self._EXECUTOR_STATES, executor_id):
                return
            # ACCEPT FIXES THE START OF THE OBLIGATION (§14.2) — so it is sent when the work
            # STARTS, not when the report comes back. Wrapping the finished report into
            # ACCEPT+DELIVER put both signals at the END: the node sat in OFFERED for its entire
            # working life and crossed EXECUTING in an instant. Measured 2026-08-20 on three leaves
            # — ACCEPT and DELIVER carried the IDENTICAL timestamp on every first delivery, and
            # files were on disk 25-53 s before the graph admitted the node had started. No view,
            # the UI included, could show work in progress, because no interval held that fact:
            # "trust, but see" (§1.1) has nothing to see. The executor's consent is still its own
            # report — a spawned executor that never reports leaves the node in EXECUTING, where
            # the dispatcher's own `_EXECUTOR_STATES` picks it up again exactly as before.
            _t = self._engine.get_task(task_id)
            if _t is not None and _t.state.name == "OFFERED":
                _signal(self._engine, task_id, Signal.ACCEPT, executor_id)
            try:
                out = self._runner(self._engine, task_id, executor_id, self._agents)
                # An UNPARSED report sends no signal — correctly, nothing may be forged from it — so
                # the node stays exactly where it was and the dispatcher's spent key means it is
                # never picked up again. Measured live: one leaf of a delegated run sat in OFFERED
                # for the rest of the run on a single unreadable report, while the arm watched a
                # graph that was, as far as it could tell, simply waiting. One retry, then the node
                # is left alone and SAID so — a parked node with a reason beats a silent one.
                if isinstance(out, dict) and out.get("status") == "unparsed":
                    t = self._engine.get_task(task_id)
                    key = self._round_key(t, "u:") if t is not None else None
                    if key and key not in self._retried:
                        self._retried.add(key)
                        self._seen.discard(self._round_key(t))
                        self._dirty.set()
                        self._engine.emit_info(
                            "delegate", f"{task_id}: unreadable executor report — one retry")
                    else:
                        self._engine.emit_info(
                            "delegate", f"{task_id}: unreadable executor report twice — the node is "
                                        f"PARKED where it stands and needs its issuer; nothing was "
                                        f"signalled on its behalf")
            except Exception as e:
                # Into the OBSERVATION FIELD, not only a log record. This handler catches the whole
                # spawn path, and a node whose dispatch raised is never retried — its key stays in
                # `_seen` until a re-ASSIGN. Logged alone, that is a graph which simply stops.
                log.warning(f"delegate run failed on {task_id}: {e}")
                try:
                    self._engine.emit_info("delegate", f"{task_id}: dispatch failed — {e}")
                except Exception:
                    pass

    def _validate_guarded(self, task_id: TaskId, expect_iter: int = 0, sign: bool = True) -> None:
        with self._cap:
            _t0 = self._engine.get_task(task_id)
            if not self._fresh(task_id, expect_iter, ("VALIDATING",)):
                if _t0 is not None:
                    self._seen.discard(self._round_key(_t0, "v:"))
                return
            ret = None
            self._engine._validation_parked.discard(str(task_id))   # a fresh attempt un-parks it
            try:
                _t0 = self._engine.get_task(task_id)
                _mo = self._retry_model.get(self._round_key(_t0, "v:")) if _t0 is not None else None
                # …AND WHAT THIS NODE HAS ALREADY COST. A refused report is kept beside the node with
                # a count (§11.2: ⊥ is evidence, not a verdict), and that count survives a restart
                # and a fresh delivery — where the in-process retry key does not. Measured across the
                # recent runs: 44 refused reports against 57 recorded verdicts, one node reaching
                # FIVE refusals. Spending the cheap tier again on a node that has already refused
                # once buys the same refusal; the retry tier is where the coverage discipline gets
                # met, so a node with a refusal behind it starts there.
                if _mo is None and (self._engine.rejected_report(task_id) or {}).get("refusals", 0):
                    _mo = validator_retry_model()
                _kw = {"sign": sign} if not sign else {}
                ret = (self._validate(self._engine, task_id, self._agents, model_override=_mo, **_kw)
                       if _mo else self._validate(self._engine, task_id, self._agents, **_kw))
            except Exception as e:
                log.warning(f"auto-validate failed on {task_id}: {e}")
            t = self._engine.get_task(task_id)
            if ret == "rejected":
                # the FSM refused the verdict (e.g. children not settled yet) — NOT a validator
                # failure: free the key so the node revalidates when the graph next changes,
                # and never burn the one no-verdict retry on it (observed live: a rejected PASS
                # was misread as no-verdict → the retry was wasted → the node stuck for good).
                if t is not None:
                    self._seen.discard(self._round_key(t, "v:"))
                return
            if ret == "no-instrument":
                # Nothing was spawned and nothing failed: this project has no registered judge, so
                # the verdict is the issuer's own act (§14.5) and the node waits for them, which the
                # frontier already says. Neither a retry nor a park belongs here.
                return
            if ret == "recorded":
                # JUDGED, AND DELIBERATELY NOT SIGNED — a human issuer's node (§14.5 keeps the
                # signature theirs). The node stays in VALIDATING BY DESIGN, and the branch below
                # reads that state as "the validator died" and queues a retry: measured on the human
                # door 2026-08-22, every recorded verdict was followed by "validator returned no
                # verdict — one retry queued" and a SECOND paid run over the same delivery, minutes
                # after the first had already answered. A settled outcome is settled whoever signs.
                return
            # a validator run that died/unparsed leaves VALIDATING with no verdict — ONE retry
            if t is not None and t.state.name == "VALIDATING":
                key = self._round_key(t, "v:")
                if key not in self._retried:
                    self._retried.add(key)
                    self._seen.discard(key)
                    # …AND ON A STRONGER MODEL. The usual reason a report carries no verdict is
                    # coverage discipline — the judge names three behaviours and probes two, or
                    # labels one command for two of them — and that is exactly what a bigger model
                    # gets right first time (measured 2026-08-20: opus wrote a probe per label and
                    # passed, sonnet fused labels and was refused twice). Retrying the same tier
                    # mostly reproduces the same gap: a run ended `validator_no_verdict` after three
                    # calls and $4.40 with the artifact scoring 0.86 on the held-out suite. The
                    # retry is the moment to spend more, because it is the last one before the node
                    # parks and a person is needed.
                    # …UNLESS THE INSTALLATION SAID NO. The escalation is the right default and it
                    # was also unrefusable: `GFSO_VALIDATOR_RETRY_MODEL=off` runs the retry on the
                    # node's own tier, and the tier is named in the log either way, because a bill
                    # nobody announced is how this was found.
                    _tier = validator_retry_model()
                    if _tier:
                        self._retry_model[key] = _tier
                    self._engine.emit_info(
                        "delegate", f"{task_id}: validator returned no verdict — one retry queued, "
                                    + (f"on {_tier} (a fuller report is usually a coverage-discipline "
                                       f"gap; GFSO_VALIDATOR_RETRY_MODEL=off keeps its own tier)"
                                       if _tier else
                                       "on its OWN tier — the escalation is off "
                                       "(GFSO_VALIDATOR_RETRY_MODEL)"))
                else:
                    # The retry produced no verdict either, and ⊥ is not pass (§2.2): the node cannot
                    # complete, and until now nothing said so — it simply stayed in VALIDATING. That
                    # is the canon's exhausted-automation case, whose answer is ATTENTION (§1.1's
                    # third mode), not silence and not auto-acceptance: auto-passing a node no one
                    # could judge would manufacture exactly the false close this system exists to
                    # prevent. Measured live (markdown_renderer, 2026-08-12): two unparsed reports,
                    # then a root sat in VALIDATING until the harness's own wall clock ended the run
                    # — the protocol's finiteness could not help, the per-state clock being opt-in
                    # and off by default. What is NOT done here: sending the system timeout, which
                    # (VALIDATING, TIMEOUT) routes to DONE(auto_pass) — auto-accepting a node no one
                    # could judge is the false close this measurement exists to detect; and there is
                    # no VALIDATING→ESCALATED edge in the canon to reach for instead. So the engine
                    # says it loudly and the ISSUER decides, which is what the canon prescribes for
                    # a ⊥ verdict; an unattended caller reads this line and ends its run by it.
                    self._engine.emit_info("delegate",
                                           f"{task_id}: validator produced no verdict twice — the ISSUER "
                                           f"must decide (⊥ is not pass, §11.2); the node stays in "
                                           f"VALIDATING and no automatic verdict will arrive")
                    # …and say it where the DRIVER looks, not only in the log: the frontier kept
                    # printing "VALIDATE this" while nothing was ever going to come.
                    self._engine._validation_parked.add(str(task_id))

    def _on_bus(self, tid=None, old=None, new=None, signal=None) -> None:
        """The transition-bus callback — trivial (set a flag), never blocks the signal path nor
        re-enters dispatch (the loop thread runs the real pass).

        It used to also mark ASSIGNed nodes so their dedup keys would be dropped — the way a REVISED
        node became fresh work. The generation now rides in the key itself (`_round_key`), so a
        revision is a new round with nothing to un-remember, and the mark is gone along with the
        double dispatch it caused on a node's FIRST assign.

        RESOLVE_BLOCK is the exception, and it has to be here rather than in the auto-sweep: a
        cleared block makes the node executable again WITHOUT moving its generation (no iteration,
        no reopen, no revision), so its round key stays spent and the dispatcher never looks at it
        again. The sweep dropped the key itself, so the automatic path worked and the HAND-sent
        signal did not — measured live: a node cleared by its issuer sat in EXECUTING for thirteen
        minutes with nothing running inside it. Every RESOLVE_BLOCK passes here, whoever sent it."""
        if signal == Signal.RESOLVE_BLOCK and tid is not None:
            t = self._engine.get_task(tid)
            if t is not None:
                self._seen.discard(self._round_key(t))
        self._dirty.set()

    def start(self) -> None:
        # (the transition bus is subscribed in __init__ — the callback is load-bearing, not a wake)
        # the quiesce-end poke: a wholesale build clears engine._dispatch_quiesce and calls this
        self._engine._dispatch_wake = self._dirty.set

        def _loop():
            while not self._stop.is_set():
                self._dirty.clear()                    # clear BEFORE the pass: a transition during it re-arms
                try:
                    self.dispatch_once()
                except Exception as e:
                    log.warning(f"dispatcher run failed: {e}")
                self._dirty.wait(self._poll)           # woken instantly by a transition, else safety-net poll
        threading.Thread(target=_loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self._dirty.set()                              # wake the loop so it exits promptly


_DISPATCHERS: dict[int, Dispatcher] = {}
_DEFAULT_AGENTS: AgentRegistry | None = None


def default_agents() -> AgentRegistry:
    """The server-wide roster singleton (one json file, shared by every project engine).

    Keyed by the PATH it was built for, so a process that moves its state home — every test that
    does, and every embedding that runs two homes in one process — gets the roster of the home it is
    in now. As a plain singleton it kept the first path forever: the suite registered its probe roles
    into the REAL roster of this installation, beside live runs' roles (found 2026-08-21)."""
    global _DEFAULT_AGENTS
    path = str(agents_path())
    if _DEFAULT_AGENTS is None or _DEFAULT_AGENTS.path != path:
        _DEFAULT_AGENTS = AgentRegistry(path)
    return _DEFAULT_AGENTS


def ensure_dispatcher(engine, agents: AgentRegistry | None = None) -> Dispatcher:
    """One dispatcher per engine (lazy, idempotent). Attached at ENGINE creation (runtime), so
    delegation works identically under every entry point (stdio MCP, unified serve, tests)."""
    key = id(engine)
    if key not in _DISPATCHERS:
        d = Dispatcher(engine, agents or default_agents())
        d.start()
        _DISPATCHERS[key] = d
    return _DISPATCHERS[key]
