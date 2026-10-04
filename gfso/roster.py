"""The roster — who, besides people, takes part: each registered agent's kind, model and place (`AgentRegistry`).

One server-wide json file, re-read when it changes and written whole (`_put_atomically`); a role's registered place
asked again at dispatch (`missing_workdir`). Unregistered ids are people, and the system stays passive for them."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from gfso.config import MODEL_DEFAULT, agents_path
from gfso.places import cheap_to_ask, disk_place, same_place, text_place


def _put_atomically(path: Path, text: str) -> None:
    """Write beside, then move over — never truncate-then-fill in place.

    Readers of the roster hold no lock (the `.lock` orders writers only), and a plain `write_text`
    leaves the file EMPTY for as long as the write takes: 31% of concurrent reads saw a partial file
    in a four-second write loop. In-process that costs a stale snapshot; a process killed mid-write
    — and the shutdown path is `os._exit` a third of a second after the request — leaves the roster
    truncated FOR GOOD, and every later load then reports "delegation is OFF" while every node
    answers "Del is not a registered executor". `os.replace` is atomic on both platforms.

    On Windows the move itself can be refused while a reader holds the destination open, so it is
    retried briefly and then REFUSED OUT LOUD: trading a silent corruption for a silent failure to
    register would be no repair. Nothing is written on that path and the old file stands.
    """
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    for _ in range(25):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.02)
    tmp.unlink(missing_ok=True)
    raise OSError(f"could not put the roster in place: {path} stayed open for half a second of "
                  f"retries. Nothing was written and nothing was damaged; the registration did not "
                  f"happen and can be repeated.")


def _resolution_note(workdir: str) -> str:
    """" (it resolves to X)" — but only when X is a DIFFERENT PLACE, not a different spelling.

    The whole point of the clause is the case a caller cannot see: a POSIX path on Windows lands at
    the current drive root. Compared as raw strings, the ordinary `C:/my/project` also "differs"
    from its resolution and the clause fired there too, which is noise on a path that points exactly
    where it looks. And resolving is not total: `stat` rejects an embedded NUL that `is_dir()`
    swallows, so an unguarded call replaces a crafted refusal with a stat error.
    """
    if not cheap_to_ask(workdir):
        return ""                      # resolving a network path blocks; see `cheap_to_ask`
    try:
        resolved = Path(workdir).resolve()
        same = os.path.normcase(os.path.normpath(str(resolved))) == \
            os.path.normcase(os.path.normpath(str(workdir)))
    except (OSError, ValueError):
        return ""
    return "" if same else f" (it resolves to {resolved})"


def missing_workdir(cfg: dict) -> str | None:
    """The role's registered place, IF it is not there — else `None`. One predicate, two callers.

    Registration answers "does this exist" once, when the role is put on the roster. This answers
    "is it there NOW", which registration cannot: the roster is a hand-editable json re-read on every
    access, so entries arrive without passing `register`, and a directory can be moved or deleted
    between registration and dispatch. Two places need the answer — the dispatcher, BEFORE it fixes
    the obligation with ACCEPT, and `run_executor` for whoever calls it directly — and they share
    this function rather than each spelling the rule, which is how one half of a rule ends up moving
    alone.
    """
    wd = (cfg or {}).get("workdir")
    if not wd or not cheap_to_ask(wd):
        return None                    # a network path is not asked; see `cheap_to_ask`
    return wd if not Path(wd).is_dir() else None


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
        validated the wrong tree. One `stat` per access is the price of the promise being true.
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
        """Put a role on the server-wide roster: its kind, model tier, workdir and bindings.

        Registration is what makes a role addressable by Del — the dispatcher picks a node up
        because its Del names a registered executor, so a mis-registration is silent until a
        node never starts. What can be checked here is checked here.
        """
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
                f"gfso state home — which contains none of the work it is meant to do or validate.")
        # …AND A DIRECTORY THAT DOES NOT EXIST IS THE SAME DEFECT WITH A VALUE IN THE FIELD. The
        # check above reads a non-empty string as an answer, so a path that names nothing passed it
        # and the role was registered against a place no work can happen in: the executor is spawned
        # with `cwd=` this path and dies in the transport, the validator validates an empty tree and
        # FAILs correct work. The case that actually happens on Windows is a POSIX-form path — an
        # agent working through a bash shell registers `/c/Users/…`, which Windows resolves against
        # the current DRIVE ROOT, so `/c/Users/kasho/Work/GFSO` becomes `C:\c\Users\kasho\Work\GFSO`:
        # a real directory gets created there by whatever writes next, outside the project, and the
        # roster looks correct while pointing at it (found 2026-09-08 as litter at the drive root,
        # dated 2026-08-21). Resolved rather than tested as written, because the difference between
        # the two spellings is exactly what the caller cannot see.
        if workdir and cheap_to_ask(workdir) and not Path(workdir).is_dir():
            raise ValueError(
                # The path is quoted, not repr'd: `!r` doubles every backslash, and a Windows path
                # a person has to retype is the last place to print it in an escaped spelling.
                f"registering {agent_id!r}: `workdir` '{workdir}' is not an existing directory"
                # …and the resolution is named only when it is genuinely somewhere ELSE. Compared
                # raw, `C:/my/project` "differs from" `C:\my\project` and the clause fired on the
                # ordinary forward-slash spelling every agent types — noise on exactly the paths
                # that point where they look, in a sentence written for the ones that do not.
                # Resolving can also fail outright (an embedded NUL is rejected by `stat` while
                # `is_dir()` swallows it), and a crafted refusal replaced by a stat error is a worse
                # answer than no clause at all.
                + (_resolution_note(workdir) or "")
                # ASCII only, deliberately: this sentence is raised as an exception and printed by
                # doors that reach a cp1251 Windows console, where a stray em-dash or ellipsis kills
                # the message and takes its diagnosis with it (the instrument that died printing its
                # own report, 2026-09-07).
                + ". A role registered against a place that does not exist is spawned into nothing: "
                  "create the directory first, or name the one the work is really in. A path in "
                  "POSIX form on Windows ('/c/Users/...') is resolved against the current drive "
                  "root, not the C: drive - pass the native path.")
        if workdir:
            # STORED ABSOLUTE. A relative `workdir` is checked here against the SERVER's cwd and
            # would later be resolved against whatever cwd the spawn happens to have — the same
            # ambiguity the guard above exists to end, one step further along. What was validated is
            # what gets written down.
            # (a network path is stored as written — resolving it blocks; see `cheap_to_ask`)
            # …AND FOR EVERY PATH, network ones included: `abspath` makes no filesystem call, so
            # the exemption that spares them a `stat` was never a reason to leave them relative -
            # and it left a drive-relative `Z:work` going into `cwd=` as written.
            # ABSPATH, NOT RESOLVE. The need is relative -> absolute; `resolve()` also walks
            # junctions and symlinks, so a workdir named through a link was silently rewritten to
            # its target - and that target is what the executor is spawned in (`cwd=`) and what the
            # registration advice quotes back. Reconciling two spellings is `same_place`'s job, at
            # comparison time; the roster keeps the place the caller named.
            workdir = os.path.abspath(workdir)
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
            # Compared as PLACES: registration stores the workdir resolved, and the caller hands
            # back what it typed, so `C:/x` against `C:\x` is one directory written two ways.
            # Read raw, the conditional removal stopped firing for the ordinary forward-slash
            # spelling — and this call is a run's budget-stop, whose silent failure is recorded as
            # "a run that ended at its ceiling was still executing minutes later".
            # Two roles with NO place are not two places (`same_place` answers False for an empty
            # side, by design): a placeless role called with an empty workdir used to match, and the
            # conditional removal is a run's budget-stop, so the silent half of the change is undone
            # here rather than by softening the predicate.
            _cur_wd, _both_placeless = cur.get("workdir"), not (cur.get("workdir") or workdir)
            if workdir is not None and not _both_placeless and not same_place(_cur_wd, workdir):
                return {"unregistered": None,
                        # Quoted and ASCII, for the same reason the registration refusal is: `!r`
                        # quadrupled the backslashes of a Windows path a person then has to retype,
                        # and the em-dash died on a cp1251 console.
                        "note": f"{agent_id} works in '{cur.get('workdir')}', not '{workdir}' - "
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
            _put_atomically(self._path, json.dumps(self._agents, ensure_ascii=False, indent=1))
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
        registered" meant the oldest entry on a shared server, so a run's node was validated by another
        run's validator, pointed at another run's workspace: measured 2026-08-20 twice, once with a
        validator whose `workdir` was an experiment's scratch directory. It happened to read the right
        files that time, because the workdir was substituted downstream — a different configuration
        and it would have validated a tree that had nothing to do with the work. Matching on workdir
        picks the instrument that is actually standing where the artifact is; naming `validator=`
        at registration still wins over everything.
        """
        cfg = self.get(executor_id or "") or {}
        if cfg.get("validator") and str(cfg["validator"]) != str(executor_id or ""):
            return cfg["validator"]
        self._load()
        # NEVER THE NODE'S OWN EXECUTOR — the selection rule, one layer above the gate that already
        # refuses such a signature. An id can hold both kinds on this roster, and a stranger did
        # exactly that: registered one id (`w24cli-…`) as an llm-validator and made the SAME id the
        # executor of a root. The dispatcher then bound the instrument to the work it had done
        # itself, recorded the verdict as `provenance: self`, and the root closed — with the
        # engine's own disclosure deferring the guarantee to "the independent validation of the
        # public result ABOVE it", which for a root does not exist (CLI door, wave 24, 2026-09-04).
        # Verifier ≠ executor is a property of the PAIR, so it belongs wherever the pair is chosen:
        # refusing the signature and then handing out the same pairing again is a rule enforced at
        # one door and offered at the next. With no other validator the honest answer is none — the node
        # waits for its issuer, who is told to register one.
        validators = {aid: c for aid, c in self._agents.items()
                  if c.get("kind") in ("llm-validator", "unittest-checker")
                  and str(aid) != str(executor_id or "")}
        # SCOPE FIRST, THEN PLACE — two independent coordinates of ONE choice, in that order.
        # THE PROJECT IS THE ISOLATION BOUNDARY, and the roster is one shared file. A person who
        # registered NOTHING had their nodes validated — and billed — by a validator another run had
        # left in the roster, standing in an experiment's scratch directory: $2.43 of a $4.38 run,
        # four validations nobody asked for (measured on the human door 2026-08-22). A role
        # registered under another project is not this project's instrument. But a role with NO
        # project is UNSCOPED, not foreign: excluding it left the measurement arm — which registers
        # through the library, without one — with no validator at all, and the run ended
        # `validation_stalled` (measured the same day, by my own rule from an hour before).
        candidates = list(validators)
        if project:
            candidates = [aid for aid in validators if validators[aid].get("project") == project]                 or [aid for aid in validators if not validators[aid].get("project")]
            if not candidates:
                return None      # every validator here belongs to some other project
        wd = cfg.get("workdir")
        if wd:
            # A ROLE THAT WORKS SOMEWHERE ELSE IS NOT THIS WORK'S VALIDATOR. "First registered" on a
            # server-wide roster means the oldest entry of whoever came first — measured twice on
            # 2026-08-20/21: a run's node validated by another run's validator standing in a scratch
            # directory, and a tester who avoided it only by reading the help. When this executor
            # HAS a workspace and no instrument stands in it, the honest answer is none: the node
            # waits for its issuer, who is told to register one, instead of being validated from a tree
            # that holds none of the work. Choosing INSIDE the scoped set is what keeps the two
            # rules orthogonal: the project branch used to answer before this one was consulted, so
            # an unscoped validator standing elsewhere beat the validator standing in the work.
            # …A PREFERENCE, NOT A REQUIREMENT — and this is where I got it wrong. A validator's
            # REGISTERED workdir is where it works, not where the work is: `_validate_with` points it at
            # the delivery at call time (the executor's workdir first). Requiring equality therefore
            # measured the wrong thing, and it refused the measurement arm's own validator — which
            # stands in a private scratch on purpose, so one run cannot validate another's leftovers.
            # Cost, measured 2026-09-02: auto-validation never fired, the arm waited 25 minutes for a
            # verdict nobody was going to give, and a $20 run ended `validation_stalled`. What keeps
            # a stranger's validator out is the PROJECT scope above; place is how we break a tie.
            # TEXT OVER THE WHOLE SET, DISK ONLY IF IT FOUND NOBODY. `same_place` asks the
            # filesystem whenever two spellings differ, and here they differ for every validator
            # standing somewhere else — which is most of them: 12.9 ms per call over a roster of 25
            # (measured), on a comparison that runs per delivered node per dispatch pass and once
            # per executor on every `list_agents`. The free pass answers the ordinary case.
            #
            # AND IT IS A PREFERENCE, DECIDED, not merely an optimization: where BOTH a validator whose
            # spelling matches as text and a validator that matches only through the disk stand in the
            # work, the textual one is chosen — even if the other sorts earlier. Measured on random
            # rosters, the two orders disagree in 375 of 3000; the exact spelling is the better
            # answer (it is the one a reader comparing the roster to the workspace would also pick),
            # and the alphabet was never a reason for anything. The paid pass is not a fallback in
            # the apologetic sense: it is what answers when text found nobody at all.
            #
            # AND THE PAID PASS ASKS ABOUT THE EXECUTOR ONCE. `same_place` resolves BOTH sides, so
            # calling it per candidate re-resolved the same `wd` twenty-five times for twenty-five
            # validators — half the cost of the branch, spent re-deriving a value that cannot change
            # inside the loop.
            _here = text_place(wd)
            same = [aid for aid in candidates
                    if (_w := validators[aid].get("workdir")) and text_place(_w) == _here]
            if not same:
                _here_disk = disk_place(wd)
                same = [aid for aid in candidates
                        if _here_disk is not None
                        and disk_place(validators[aid].get("workdir")) == _here_disk]
            if same:
                return sorted(same)[0]
            # WITH NO PROJECT there is nothing else keeping a stranger out, so place is the whole
            # rule and the honest answer is none (measured 2026-08-20/21, twice). WITH a project the
            # scope above has already excluded other runs, and insisting on place as well refused a
            # legitimate validator — the arm's own, which stands in a private scratch by design.
            return None if not project else sorted(candidates)[0] if candidates else None
        if project:
            # An UNSCOPED role stays usable here — the measurement arm registers through the library
            # without a project, and excluding it once left a run with no validator at all. What the
            # fallback cannot do is tell a stranger's leftover from a legitimate library role, and on
            # the CLI door 2026-09-02 a tester who registered NOTHING had every node signed by
            # `val-1`, whose registered workdir points into another run's scratch directory. It only
            # worked because they wrote absolute paths into every delivery. The choice stands; what
            # must not is its silence — `unscoped_validator` below is what the surfaces say about it.
            _mine = [aid for aid in candidates if validators[aid].get("project") == project]
            return sorted(_mine or candidates)[0]
        return self.default_validator()

    def get(self, agent_id: str) -> dict | None:
        """One role's config, or `None` for an id the roster does not know — which is what a HUMAN is
        (§10.4: an unregistered Del is a person, and nothing is dispatched to them)."""
        self._load()
        return self._agents.get(str(agent_id))

    def list(self) -> dict:
        """The whole roster as {id: config}. A copy: a caller that mutated it would be editing the
        registry behind the file's back."""
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
