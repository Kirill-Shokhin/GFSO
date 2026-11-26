"""G = (N, E_D, E_Dep, sigma). Wraps StoragePort."""
from __future__ import annotations

import bisect
import copy
import dataclasses

import json
import math
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

from gfso.config import (BOUNDED_STATES, PERSON_BOUNDS, PERSON_DEADLINE_S, PERSONS_NAMES, SYSTEM, agent_id,
                         default_deadline_s, state_bound)

from gfso.core.types import (
    TaskId, AgentId, Task, State, Signal, Verdict,
    GuardContext, GraphContext, CheckResult, Recommendation,
    DispatchPayload, DepEdge, StoragePort, DEFAULT_MAX_ITERATIONS, TERMINAL_STATES,
)


#: WHICH delivery a record is about: a rework moves the first, a REOPEN the second (a pre-reopen pass must not re-open
#: a gate from the past), a revision the third (a validator still running on a voided delivery lands its verdict after
#: it carrying the same first two, §12.10). One owner of the triple — it was spelt out ten times (ortho audit, D-F4).
GENERATION = ("iteration", "reopens", "revisions")


def stamp(generation: tuple) -> dict:
    """A record's generation fields, as stored."""
    return dict(zip(GENERATION, generation))


def stamped_with(rec: dict | None, generation: tuple) -> bool:
    """Was this record made for this generation? A record older than a field reads it as 0."""
    return bool(rec) and all(rec.get(k, 0) == g for k, g in zip(GENERATION, generation))


def recorded_by_an_appointed_observer(rec: dict | None, task, issuer) -> bool:
    """Was this verdict record made by an observer someone APPOINTED — the one kind that binds?

    The instrument (whoever runs it, the issuer or the system), or the node's issuer himself where he is
    not its executor. Never the executor: his own word is a report, and letting it bind would let him
    veto an independent issuer's PASS at a seam. Never a hand record by any other self-named party: that
    is a report too (C-12, 2026-09-27). One owner, because two rules read it — a PASS over a recorded
    FAIL (Inv-2) and the observation a PASS under a mode stands on — and they must not disagree."""
    if not rec or task is None:
        return False
    who = str(rec.get("validator"))
    return who != str(task.assignee) and (not rec.get("by_hand") or signs_as(issuer, who))


def generation_of_task(t) -> tuple:
    """The generation of a node you already HOLD: (iteration, reopens, revisions).

    Same fact as `Graph.generation_of`, for callers that have the object rather than its id — and
    the reason it exists is that they were each spelling it as three defensive `getattr` reads with
    their own defaults. The fields are DECLARED, so they are read as declared: a `getattr` with a
    default over a declared field says the field might not be there, which is a false statement
    about this type and the thing the coupling instrument counts.
    """
    return (t.iteration, t.reopens, t.revisions) if t is not None else (0, 0, 0)



def register_log_key(task_id) -> str:
    """Where the versions of a node's split register are recorded, each with its author and time (Thm 11)."""
    return f"register:{task_id}"


def coverage_history(storage, audit, parent_id) -> list:
    """The split's coverage {(criterion, child)} as each logged act that set it left it, in log order: [(key, coverage)].
    An admission sets it whole — its logged mappings (§11.5); a version of the node itself keeps what its criteria still
    name (§12.10). Coverage is the split's (§2.4), so no child's ASSIGN is a step of it. Keyed for `coverage_at`: an
    admission logged at `log_at` L stands just before entry L, a version on its own entry. Empty where no admission was
    logged — a graph from before admissions were."""
    steps = [((r.get("log_at", 0), -1), r) for r in json.loads(storage.get_critique(admission_key(parent_id)) or "[]")]
    if not steps:
        return []
    steps += [((i, 0), e) for i, e in enumerate(audit.get_entries() if audit is not None else ())
              if e.task_id == parent_id and not e.rejected and e.spec]
    out, cov = [], None
    for key, x in sorted(steps, key=lambda s: s[0]):
        if isinstance(x, dict):
            cov = frozenset((c, k) for c, k in x.get("mappings", ()))
        elif cov is not None:
            names = {c.get("name") for c in logged_criteria(x.spec)}
            cov = frozenset((c, k) for c, k in cov if c in names)
        if cov is not None:
            out.append((key, cov))
    return out


def coverage_at(history: list, at: int):
    """The coverage standing at or before log entry `at` (None before the first admission), and every later one."""
    before = [c for key, c in history if key <= (at, 0)]
    return (before[-1] if before else None), [c for key, c in history if key > (at, 0)]


def admission_key(task_id) -> str:
    """Where a node's split admissions are recorded (§11.5: a logged act of its own) — each with the children it
    issued, its drops, its mappings and its place in the signal log."""
    return f"admission:{task_id}"


def grounds_key(task_id) -> str:
    """{part: the commit of its whole's tree it starts from}: where the whole stood at the first join after the part
    entered its split. The parts joined since are none of its input but by a Dep edge."""
    return f"grounds:{task_id}"


def goal_deps_key(task_id) -> str:
    """Where the declarations of a ROOT's Dep edges are recorded — a root sits in no split to re-admit (§15.2: the goal's
    issuer joins a second goal to it by Dep) — each with its producers as they then stand and its place in the log."""
    return f"goal_deps:{task_id}"


def checker_choices_key(task_id) -> str:
    """Where its issuer's choices of who checks a node are recorded (§10.2: an issuer's decision, Thm 11: each with its
    record) — author, choice, words or none, time and place in the signal log; the chosen set is their projection."""
    return f"checker_choices:{task_id}"


def chosen_checker(storage, task_id) -> Optional[str]:
    """The checker its issuer's latest recorded choice names for `task_id`, or None where none is recorded — the record is
    the decision (Thm 11); the older chosen-set setting stands only for nodes chosen before records were kept."""
    made = json.loads(storage.get_critique(checker_choices_key(task_id)) or "[]")
    return made[-1]["checker"] if made else None


def replaces_key(task_id) -> str:
    """Where the dropped children a node was admitted to stand in for are recorded — whose work it carries on."""
    return f"replaces:{task_id}"


def drops_key(task_id) -> str:
    """Where the children a re-admission of this node's split dropped are recorded, each with its place in the signal
    log (§11.5) — out of the plan at the drop (§12.6), whatever their cancellation's progress."""
    return f"dropped:{task_id}"


def unmaps_key(task_id) -> str:
    """Where the settled parts a re-admission of this node's split left mapped to nothing are recorded — each pair with
    its decomposer, time, place in the log and the part's checks it took off this node's procedure — the act alone; their
    last re-run is read off the verdict records when the row is read (Thm 11: no mechanical gate tells an honest lift from
    an escape; the record does, for who signs)."""
    return f"unmapped:{task_id}"


def root_issuer_key(task_id) -> str:
    """The setting that records a root's issuer — the one spelling both writer and reader use."""
    return f"issuer:{task_id}"


def issuer_moves_key(task_id) -> str:
    """Where every move of a root's issuer after its creation is logged — [{log_at, from, to, by, why}] —: a switch of
    the project's mode handing its live roots' issuer role over (`Engine.set_mode`), or the one-time reading of a root
    an earlier build created under AUTO (`Engine._the_system_party_where_auto_created`)."""
    return f"issuer_moves:{task_id}"


#: The project's STOP, the user's: {by, at, why} while the system starts nothing in it, or absent.
PAUSE_KEY = "paused"
#: The tech reports filed in the project — about the system, not the task (`Engine.tech_report`).
TECH_KEY = "tech_reports"
#: Where a node's deadline moves on the wall are recorded: each a stop's held time, at its lift (`Stops.deadline_moves`).
DEADLINE_MOVES = "deadline_moves:"
#: The writes a console's witness saw in the project's repository while no node of it was at work there (`Engine.witnessed`):
#: work past the system, the project's own record — not the system's defect.
WITNESS_KEY = "witnessed"


def witnessed_count(seen: list[dict]) -> int:
    """How many writes the witness ever recorded: the last kept record's running `n` (records before it count by length)."""
    return seen[-1].get("n", len(seen)) if seen else 0

#: Where the accepted result lies, kept for whoever reads the graph: {branch, sha, path} or {path} (`workspaces.land_accepted`);
#: its sha is a commit the system made, as its deliveries' are (`past`).
LANDED = "landed"
#: The root whose plan the user handed in whole (`auto_decompose` with `spec`): under AUTO it is the user's, as the root's
#: criteria are, and the system does not re-split it (`validation.users_plan`).
USERS_PLAN_KEY = "users_plan"
#: the nodes whose plan was built from a file carrying its own Level-2 review (`Engine.reviewed_in_its_file`): the gate
#: is off under each of them alone — a go on one file turned it off for every goal of a shared graph (s20g1)
REVIEWED_IN_FILE_KEY = "reviewed_in_file"


#: The seconds this project did NOT run, kept off its clocks. ONE RULE: its time runs only while its own monitor ticks
#: over it and it is not stopped — a tick under a stop, a gap between two ticks (a host asleep), the gap since the last
#: beat when its engine starts (a server down, the project not loaded) are left off, each wall second once. A bound times
#: a party's wait (§12.2); where nothing runs the project, no party's move is made, and a deadline spent there was spent
#: by nobody (measured: a row stopped 6.5 h woke with every work node ESCALATED). docs/notes/PROJECT_CLOCK.md.
CLOCK_OFF_KEY = "clock_off_s"
#: The wall time its engine last ticked over it (`loop.timeout_monitor`): the start of a gap nobody ran in.
CLOCK_BEAT_KEY = "clock_beat"


#: A gap between two of its monitor's ticks longer than this is time nobody ran the project in (a host asleep).
NO_TICK_S = 120.0


def kept_off(graph: "Graph") -> float:
    """What the ticks and starts kept off this project's clocks — `clock_off_s` without what is pending."""
    v = graph.setting(CLOCK_OFF_KEY) if graph is not None else None
    return float(v) if v else 0.0


def clock_off_s(graph: "Graph") -> float:
    """How much wall time this project's clocks leave out NOW: what the ticks kept off (`CLOCK_OFF_KEY`), plus what is
    pending since the last beat by the same rule — all of it under a stop, all of a gap too long to be a tick — so a bound
    read between two ticks (a delivery landing right after a wake) already sees the sleep off (critic over the clock, r3)."""
    if graph is None:
        return 0.0
    pending = 0.0
    if beat := graph.setting(CLOCK_BEAT_KEY):
        gap = time.time() - float(beat)
        stopped = bool(json.loads(graph.setting(PAUSE_KEY) or "null"))
        pending = gap if (stopped or gap > NO_TICK_S) and time_holds(graph) else 0.0
    return kept_off(graph) + max(0.0, pending)


def time_holds(graph: "Graph") -> bool:
    """Does wall time nobody ran this project in stay off its clocks — a stop, a server down, a host asleep? Only where
    the system carries its work (`Graph.carries_work`): a bound spent there was spent by nobody, while on a graph people
    hold their deadlines run on the wall as the canon's never-suspended deadline does (§12.2; the author, 2026-11-15:
    «там очевидно и часы вести не для кого»). Read at the moment a gap is left off, so a project changing hands
    mid-stop holds from the tick it carries work and not before. A graph no engine runs: yes, as it always was."""
    return graph.carries_work is None or bool(graph.carries_work())


def keep_off(graph: "Graph", seconds: float) -> None:
    """Leave `seconds` of wall time off this project's clocks, as one act on the store (`Graph.swap_settings`)."""
    graph.swap_settings(lambda get: {CLOCK_OFF_KEY: str(float(get(CLOCK_OFF_KEY) or 0) + seconds)})


def keep_the_beat(graph: "Graph", wall: float) -> Optional[tuple[float, float]]:
    """THE ONE DECISION of how much wall time is held between the project's last kept beat and `wall` — an engine's start
    (a server down) and every tick of its monitor (a host asleep, a stop) ask it alike. Read over the STORED beat and
    off, in one act on the store (`Graph.swap_settings`), never over a caller's memory: any number of monitors and
    engines over one project — a server and a stdio MCP process on one .db — leave each wall second off once, as the
    second to come finds the gap kept (the beat at or past its `wall`) and keeps nothing. Held, by `clock_off_s`'s rule:
    all of it under a stop, all of a gap too long to be a tick, and only where time holds (`time_holds`); the beat moves
    to `wall` either way. Returns the start of a gap held outside a stop and the off kept before it — what the deadlines'
    record names (`Stops.record_the_gap`), by the one caller that kept it — else None."""
    holds, out = time_holds(graph), None    # …who carries the work, read before the act: it is not the clock's to race

    def beat(get):
        """The beat moved to `wall` and the gap held, inside the store's one act — nothing where it is kept already."""
        nonlocal out
        was = get(CLOCK_BEAT_KEY)
        if was and float(was) >= wall:
            return {}
        before, gap = float(get(CLOCK_OFF_KEY) or 0), wall - float(was or wall)
        stopped = bool(json.loads(get(PAUSE_KEY) or "null"))
        held = holds and (stopped or gap > NO_TICK_S)
        out = (float(was), before) if held and not stopped else None   # …under a stop, the stop's lift records it
        return {CLOCK_BEAT_KEY: str(wall), **({CLOCK_OFF_KEY: str(before + gap)} if held else {})}
    graph.swap_settings(beat)
    return out


def project_now(graph: Optional["Graph"]) -> datetime:
    """THE PROJECT'S NOW — the one time every deadline and state bound is written in and read against: the wall clock
    less the time the project did not run. Every stamp a bound is measured from is taken on it, so a stop or a down
    server moves no wait closer to its end."""
    return datetime.now() - timedelta(seconds=clock_off_s(graph))


def door_off_s(graph: Optional["Graph"]) -> float:
    """The off time EVERY DOOR converts with, both ways (`on_the_wall`, `tools._deadline`): `clock_off_s`, except that
    while the project stands stopped it is the one taken at the stop (`Stops.pause`). Under a stop the project's time
    stands while the wall runs, so a date shown grew every tick, and a client feeding it back (an unchanged child
    re-admitted) had it taken off with a larger off — read as changed. Started again, a date reads the stop's length later."""
    stop = json.loads(graph.setting(PAUSE_KEY) or "null") if graph is not None else None
    return float(stop["off_s"]) if stop and stop.get("off_s") is not None else clock_off_s(graph)


def on_the_wall(graph: Optional["Graph"], at: datetime) -> datetime:
    """A time on the project's clocks as it reads outside: on the wall (`project_now`'s inverse at the doors)."""
    return at + timedelta(seconds=door_off_s(graph))


def party_kind(graph: "Graph", party: str, registered=None) -> str:
    """WHO makes a party's issuer moves — the one owner of a question four places answered four ways (D-F9):
    `machine` — the system party (`SYSTEM`: the issuer of a goal handed over whole, recorded at its root's creation),
    or a registered participant;
    `holder` — the user's standing agent under a mode, whose moves the system never makes;
    `person` — the standing agent with no mode set, or anyone else unregistered: the system holds no role of theirs
    (§10.1: Del names the role's holder) and is passive — their moves come only when they write.
    Read off what the party is: the person is never re-typed a machine by the project's mode (§10.4: autonomy is per
    task and role, switching being who occupies it). The standing agent is read first: a role registered under the
    user's own id does not make it a machine.
    `registered` is the registry consulted (the dispatcher's own; the engine's published roster by default)."""
    if str(party) == SYSTEM:
        return "machine"
    if str(party) == str(agent_id()):
        return "holder" if _mode(graph) else "person"
    return "machine" if (registered or {}).get(str(party)) is not None else "person"


def signs_as(issuer, party) -> bool:
    """Does `party` sign as `issuer` — the issuer itself, or the person over the system party acting for him (§10.4:
    the autonomous level's human, «oversight at the level above»)?"""
    return str(party or "") == str(issuer or "") or str(issuer) == SYSTEM and str(party) in PERSONS_NAMES


def is_its_executor(task, who) -> bool:
    """Is `who` the node's own executor — the one a verdict on a seam may not come from (verifier ≠ executor, §10.3)?
    Compared as names, so an id and its string read as one party; no one is nobody's executor."""
    return bool(who) and bool(task.assignee) and str(who) == str(task.assignee)


def persons_over(party):
    """The party a door takes `party`'s move from: the person over the system party acting for him, else `party` — a
    door's caller is a person or an agent, never the system, whose own moves are made in process."""
    return AgentId(agent_id()) if str(party) == SYSTEM else party


def _mode(graph: Optional["Graph"]) -> Optional[dict]:
    """The project's mode record as set (`Engine.set_mode`), or None."""
    return json.loads(graph.setting("mode") or "null") if graph is not None else None


def hands_of(graph: Optional["Graph"], party) -> Optional[str]:
    """The registered executor whose session performs the nodes `party` holds, or None — the party performs them
    itself. Only the standing agent under a mode that DISPATCHES has hands: it consents and stays Del, every signal
    its own (§10.1), and the work runs in a clean session the system starts after its ACCEPT — no seam inside one
    agent (§10.3), so how it performs is its own. In its own chat nothing structural keeps the work inside the
    contract (§16.9 exception 11); a session the system starts only after consent does."""
    m = _mode(graph)
    return m.get("hands") if m and m.get("perform") == "dispatch" and str(party) == str(agent_id()) else None


#: the states whose wait the ASSIGNEE ends (its consent, its handshake); every other bounded state waits on the issuer —
#: its answer to a dispute or a block, its decision on a lapsed node, its signature on a verdict (`Engine.holder_signs`)
_ASSIGNEE_WAITS = ("OFFERED", "CANCELLING")


def waits_on_a_person(graph: Optional["Graph"], party) -> bool:
    """Is `party` one whose moves come only when a person writes — the standing agent, unless AUTO makes it the system's
    customer, or a person the published roster does not carry? Their waits run on a person's scale (`PERSON_BOUNDS`);
    the system's own sessions keep the server's. With no mode the standing agent IS the person (the page's signer, the
    OS owner of a local connection) whatever the roster says; a hung validator is still cut by the server's T_validate
    (`validate._validation_cap`). Before the dispatcher publishes a roster nobody else is taken for a person by
    absence from it."""
    if graph is None or party is None:
        return False
    kind = party_kind(graph, str(party), graph.roster or {})
    return kind == "holder" or kind == "person" and (graph.roster is not None or str(party) == str(agent_id()))


def project_deadline_s(graph: "Graph", assignee=None, issuer=None) -> float:
    """How far ahead a deadline nobody typed is written in this project for a node between `assignee` and `issuer`: its
    own setting, else a person's scale where any wait inside the contract falls on a person (`waits_on_a_person`: the
    consent and the handshake on the assignee, the answers, the verdict and the decision on the issuer — OFFERED,
    CHALLENGED and BLOCKED end at the deadline too, §12.2), else the server's — always some time ahead: a project's 0,
    stored before the door refused one (`tools_llm._settings_given`), reads as unset. The deadline is the
    contract's; the system's session is cut by its own bound (`sessions._session_cap`), never by choosing it shorter."""
    if (v := graph.setting("deadline_s")) is not None and float(v) > 0:
        return float(v)
    person = waits_on_a_person(graph, assignee) or waits_on_a_person(graph, issuer)
    return PERSON_DEADLINE_S if person else default_deadline_s()


def project_bounds(graph: Optional["Graph"]) -> dict:
    """The per-state bounds this project sets for itself (`set_mode(bounds=)`), {STATE: seconds}; {} = the server's.

    The bound values lie outside conformance (§12.16) and differ by who waits: a run's validator answers in minutes, a
    person signing a stream answers in days — so they are the project's, as its deadline is, never the server's alone."""
    raw = graph.setting("bounds") if graph is not None else None
    try:
        kept = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    return {str(k): s for k, v in (kept.items() if isinstance(kept, dict) else ()) if (s := bound_seconds(v)) is not None}


def bound_seconds(v) -> Optional[float]:
    """A bound as the clock reads it — finite seconds above 0 — or None: the one rule the door refuses by and the
    reader keeps by, so no value the door took can stop the clock (Inv-5; critic: 10**400 killed the monitor)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    try:
        s = float(v)
    except OverflowError:
        return None
    return s if 0 < s <= MAX_BOUND_S else None


#: a bound in deed, not only in letter (Inv-5): the longest a project's state may wait — a year
MAX_BOUND_S = 365 * 86_400
#: the most rework rounds a project's default may forecast: an estimate of rounds, not an open loop (§12.15)
MAX_ITERATIONS_CEILING = 1_000


def project_state_bound(graph: Optional["Graph"], state_name: str, task: Optional[Task] = None) -> float:
    """One state's own bound (§12.2) in this project: its setting, else — on `task` — a person's scale where the party
    the state waits on is a person (`waits_on_a_person`), else the server's (`state_bound`)."""
    if own := project_bounds(graph).get(state_name):
        return own
    party = task and (task.assignee if state_name in _ASSIGNEE_WAITS else graph.issuer_of(task.id))
    # …a cancel's handshake is the performer's: under dispatch the system's session answers it in the holder's name
    person = waits_on_a_person(graph, party) and not (state_name == "CANCELLING" and hands_of(graph, party))
    return PERSON_BOUNDS[state_name] if state_name in PERSON_BOUNDS and person else state_bound(state_name)


def bounds_refusal(bounds) -> Optional[str]:
    """Why a project's bounds cannot stand, or None. Inv-5: every waiting state keeps a bound, so none is 0; the work
    states run on the packet deadline (`deadline_s`), not a bound of their own; IDLE has no clock."""
    if not isinstance(bounds, dict):
        return f"bounds is {{STATE: seconds}}, got {bounds!r}"
    for k, v in bounds.items():
        if k not in BOUNDED_STATES:
            return (f"{k!r} has no bound of its own: the bounded states are {', '.join(BOUNDED_STATES)}"
                    + ("; EXECUTING and REWORKING run on the packet deadline — set `deadline_s`"
                       if k in ("EXECUTING", "REWORKING") else ""))
        if bound_seconds(v) is None:
            return (f"{k}'s bound is seconds above 0 and at most a year, {MAX_BOUND_S} (Inv-5: a waiting state is never "
                    f"unbounded), got {v!r}")
    return None


def project_max_iterations(graph: Optional["Graph"]) -> int:
    """The rework bound a node issued here without one gets (§12.15): the project's setting, else the default."""
    v = graph.setting("max_iterations") if graph is not None else None
    return int(v) if v else DEFAULT_MAX_ITERATIONS


class Graph:
    def __init__(self, storage: StoragePort):
        self._storage = storage
        # the signal log, when a host holds one (`Engine` hands it in): consumption is read off it (`is_consumed`)
        self.audit = None
        # {node: (tree, commit, build)} a check before its delivery is judging now, when a host runs one (`Engine`)
        self.judging: dict = {}
        # WHO MAY SPEAK AS THE ISSUER'S ROLE-V INSTRUMENT (§10.3): the registered `llm-validator` /
        # `unittest-checker` ids, published downward by the dispatcher each round. Declared here
        # because two validation rules read it — who may sign PASS/FAIL at all, and whether a seam's
        # PASS still needs a recorded verdict — and a field born outside `__init__` had both of them
        # reading it defensively, which is how a rule silently becomes "empty set" on any graph the
        # dispatcher never touched.
        self.authorized_validators: set[str] = set()
        # WHO OF THE NON-HUMAN PARTICIPANTS IS WHAT, {id: kind} — published by the dispatcher (`Workforce.publish_roster`);
        # None before it first does, so no party reads as a person by absence from a roster nobody wrote
        self.roster: Optional[dict] = None
        # DO THE SYSTEM'S ROLES CARRY THIS PROJECT'S WORK — handed by its engine (`Engine.system_carries_work`), the one
        # reading `time_holds` asks; None on a graph no engine runs
        self.carries_work = None

    def setting(self, key: str) -> Optional[str]:
        """A setting of this graph's project as stored, or None — the user's choices for it (`set_mode`)."""
        return self._storage.get_setting(key)

    def store_setting(self, key: str, value: str) -> None:
        """Keep a setting of this graph's project — the user's choices, the stop's record."""
        self._storage.store_setting(key, value)

    def swap_settings(self, change) -> None:
        """Read and write settings as one act on the store (`StoragePort.swap_settings`) — the clock's beat, a stop's lift."""
        self._storage.swap_settings(change)

    def get_state(self, task_id: TaskId) -> Optional[State]:
        """The node's current state, or `None` if this id is not in the graph. `None` is what the
        protocol step reads as "unknown node" — it is not a state."""
        task = self._storage.get_task(task_id)
        return task.state if task else None

    def get_task(self, task_id: TaskId) -> Optional[Task]:
        return self._storage.get_task(task_id)

    def get_children(self, task_id: TaskId) -> list[Task]:
        """ALL children incl. ABANDONED tombstones — provenance view (§15.1: nothing deleted)."""
        return self._storage.get_children(task_id)

    def provenance_subtree(self, task_id: TaskId) -> list[Task]:
        """`task_id` and every node beneath it by `get_children`, cancelled ones included: what a dropped node held —
        `subtree` stops at a cancelled node, which has left the decomposition but not the record."""
        out: dict = {}
        todo = [t] if (t := self.get_task(task_id)) is not None else []
        while todo:
            if str((t := todo.pop()).id) not in out:
                out[str(t.id)] = t
                todo += self.get_children(t.id)
        return list(out.values())

    def get_active_children(self, task_id: TaskId) -> list[Task]:
        """Children in the ACTIVE decomposition: every child but an ABANDONED one (§12.6: "a child is active unless
        ABANDONED or dropped by a re-admission … a settled cancellation, or the drop, takes it out of the plan").

        A cancelled node persists in the graph forever (provenance, §15.1 / Prop 6) but leaves the decomposition when
        its cancellation SETTLES, not at CANCEL: until CONFIRM_CANCEL or CANCELLING's bound, it still stands where it
        stood — the AND waits on it, and its coverage still counts (sync audit, A-F9: read as gone at CANCEL, a
        parent could close over a child whose closing had not been acknowledged). A dropped unissued child leaves by
        its CANCEL from IDLE, settled the same way. A child DROPPED by a re-admission is out at the drop (§12.6:
        "unless ABANDONED or dropped by a re-admission"): the re-admission's battery already read the split without it,
        and read back in while its cancellation runs, it was an orphan that refused every later admission (critic r6)."""
        dropped = {d["child"] for d in json.loads(self._storage.get_critique(drops_key(task_id)) or "[]")}
        return [c for c in self._storage.get_children(task_id) if c.state != State.ABANDONED and str(c.id) not in dropped]

    def get_parent(self, task_id: TaskId) -> Optional[Task]:
        return self._storage.get_parent(task_id)


    def dep_edges(self, adopted: bool = False, closed: bool = False) -> list:
        """The dependency records that still SAY something — the declared edges and every discovered one
        open or confirmed. A record CLOSED unanswered asks nothing and waits on nothing: read as live by the
        dispatcher and the RESOLVE_BLOCK rule, it held a re-issued node's next block on a producer it no longer
        names (critic, 2026-09-27); `closed=True` adds those — what q_Dep counts. `adopted=True` reads E_Dep instead (§11.3, §15.5), what the
        plan's checks, the execution order and consumption read: every declared edge, and a discovered
        record only once its issuer CONFIRMED it and only if it closes no cycle. A provisional record is a
        report awaiting that answer — CHECK-2 ran over it, and a BLOCK naming two siblings that already
        consumed the blocked node read as a Dep cycle that froze every sibling of the plan (AUTO
        json_parser, 2026-09-25). A confirmed record that would close a cycle refutes the plan's ordering,
        which only a re-decomposition restores (`dep_order_refutations`), and still counts in q_Dep."""
        return list(self.kept(("dep_edges", adopted, closed), lambda: self._dep_edges(adopted, closed)))

    def _dep_edges(self, adopted: bool, closed: bool) -> list:
        declared, stored = self._dep_records(ever=closed)
        if not closed:
            stored = [e for e in stored if not e.closed]
        if not adopted:
            return declared + stored
        live = {i for i, t in self._storage.task_view().items() if t.state not in (State.CANCELLING, State.ABANDONED)}
        out = list(declared)
        waits = parent_waits(self)     # …a cycle through a parent's wait on its parts too (CHECK-2)
        for e in stored:
            if not e.provisional and str(e.to_id) in live and not _closes_cycle(out + waits, e):
                out.append(e)
        return out

    def declared_edges(self, to_id) -> list:
        """The declared edges standing into `to_id` — the producers its versions read along Dep (§2.7)."""
        return [e for e in self._storage.get_dep_edges()
                if not e.discovered and not e.removed and str(e.to_id) == str(to_id)]

    def _dep_records(self, ever: bool = False) -> tuple[list, list]:
        """(declared, discovered-only). DECLARED edges are records of their own, written by the act that declares
        them (§15.1); DISCOVERED ones by the BLOCK that surfaced them (§11.3). `ever`: the declared edges of cancelled
        consumers too — the plan that was, which q_Dep counts "whatever state it reaches later" (§15.4); filtered,
        a declared edge left the population when its consumer was cancelled and a discovered one never did
        (critic B1: 0.5 → 0.0)."""
        found = self._storage.get_dep_edges()
        # A PAIR ALREADY DISCOVERED STAYS DISCOVERED (§15.5): "a discovered edge never joins" the declared side, so
        # declaring the seam after a BLOCK exposed it leaves the pair discovered — else q_Dep, the share of the
        # discoveries that WERE made that the plan had declared in advance (not a share of S, which nobody
        # observes), rose for the repair.
        pair = lambda e: (str(e.from_id), str(e.to_id))
        records = [e for e in found if e.discovered and not e.refuted]   # a refuted record asks nothing (§15.5)
        _discovered = {pair(e) for e in records}
        if ever:
            # …and q_Dep reads DISCOVERIES, not records: a record whose pair a version had declared before its first
            # BLOCK met a known dependency (declared), and a pair a BLOCK named first and the issuer refuted is in
            # neither half — a later declaration does not make it "declared before any BLOCK named it" (§15.5)
            _discovered = {pair(e) for e in records if not e.declared_first}
            _out = {pair(e) for e in found if e.discovered and e.refuted and not e.declared_first}
        tasks = self._storage.task_view()
        edges = [dataclasses.replace(e, discovered=pair(e) in _discovered) for e in found
                 if not e.discovered and not e.removed and str(e.to_id) in tasks
                 and (ever or tasks[str(e.to_id)].state not in (State.CANCELLING, State.ABANDONED))]  # §12.6
        _have = {pair(e) for e in edges}
        if ever:
            # …and the edges a LATER act took out: a declaration removed (`remove_dependency`, a re-admission) was
            # declared all the same, and §15.5 has no clause taking a declared edge out of the population — its
            # record, or, written by an older engine, every version the log installed (Inv-7)
            for frm, to, glue in [(str(e.from_id), str(e.to_id), e.glue) for e in found if not e.discovered and e.removed] \
                    + logged_declarations(self._storage.load_audit()):
                if (frm, to) not in _have:
                    _have.add((frm, to))
                    edges.append(DepEdge(from_id=TaskId(frm), to_id=TaskId(to), glue=glue,
                                         discovered=(frm, to) in _discovered))
            return ([e for e in edges if pair(e) not in _out],
                    [dataclasses.replace(e, discovered=pair(e) in _discovered) for e in records if pair(e) not in _have])
        return edges, [e for e in records if pair(e) not in _have]

    def subtree(self, root_id: Optional[TaskId] = None) -> list[Task]:
        """`root_id` and every node beneath it, by the parent edges the graph actually holds.

        The relation, not the spelling: scoping by an id prefix is true of the graphs
        `auto_decompose` builds and false of every graph built by hand, where a person names a node
        `parser` and the engine records its parent perfectly well. The prefix is honoured as well,
        so an id that spells its ancestry answers even before its parent edge exists.

        Cancellation is excluded for the same reason `get_active_children` excludes it: a cancelled
        node persists as provenance but has left the decomposition.
        """
        return [copy.copy(t) for t in self.subtree_view(root_id)]

    def subtree_view(self, root_id: Optional[TaskId] = None) -> list[Task]:
        """`subtree` to READ, its nodes the store's own (`task_view`): a copy of every node at every call was the
        quadratic of a large graph's every question (measured 2026-11-13)."""
        if root_id is None:
            return list(self.kept(("live",), lambda: [t for t in self._storage.task_view().values()
                                                      if t.state not in (State.CANCELLING, State.ABANDONED)]))
        return list(self.kept(("subtree", str(root_id)), lambda: subtree_of(live_index(self), str(root_id))))

    def kept(self, key, read):
        """`read()` kept until the store's next write (`StoragePort.kept`): a reading of the whole graph asked at each
        node a question walks is made once."""
        return self._storage.kept(key, read)

    def get_guard_context(self, task_id: TaskId) -> GuardContext:
        """What the FSM needs to decide a transition beyond the state itself: the rework counter and
        its cap, the reopen counter and its cap, and whether this terminal is consumed (§12.14).

        Assembled here because a guard that read the graph itself would make the transition depend on
        storage, and the point of the FSM is that it does not."""
        task = self._storage.get_task(task_id)
        if task is None:
            return GuardContext(iteration=0, max_iterations=DEFAULT_MAX_ITERATIONS)
        return GuardContext(
            iteration=task.iteration,
            max_iterations=task.max_iterations,
            reopens=task.reopens,
            max_reopens=task.max_reopens,
            # Computed HERE, consumed by the pure FSM guard in the SAME process_signal step —
            # gate+edge are one log-serialized atomic act (Inv-7): a concurrent DELIVER that would
            # consume the node is still in the queue, it cannot interleave (no TOCTOU).
            consumed=self.is_consumed(task) if task.state in (State.DONE, State.ABANDONED) else True,
        )

    def is_public(self, task: Task) -> bool:
        """§10.3: public node ⟺ a DELEGATION SEAM — the node's scope of responsibility differs
        from its parent's, operationally Del(child) ≠ Del(parent), OR the node is a root (assigned
        into the graph by an external issuer — the one seam "done" must cross). An INTERNAL node
        (Del(child) = Del(parent)) is the agent's private decomposition: it SELF-verifies (DELIVER
        carries self_validation), and its guarantee is carried by the validation of the agent's
        public result (Thm 1's non-redundancy direction). A missing/unassigned parent reads as a seam
        — fail-closed toward the stricter side. So does a self-assigned root, internal by the canon
        («a root not self-assigned» is the seam): nothing above carries its verdict, and the product
        puts its own check there (§10.2), a stricter admission §12.16 allows."""
        if task.parent_id is None:
            return True
        parent = self.get_parent(task.id)
        if parent is None or parent.assignee is None or task.assignee is None:
            return True
        return parent.assignee != task.assignee

    def is_consumed(self, task: Task, resting: bool = True) -> bool:
        """R′'s finality gate (§12.14): is this terminal CONSUMED — something rests on it, or the plan moved past it —
        so that reversing it would reverse its downstream cone. Read from the first logged moment of THIS terminal
        visit (`at`), and once logged it stands: a parent's FAIL after its DELIVER does not give the child back.

        - the AND leg (DONE only): the parent DELIVERED after the child settled — its aggregate rests on the pass;
        - the Dep leg (DONE only): an adopted consumer stood in work or was validated after the pass (the read is not
          logged, so "in work" is the visible over-approximation the canon chooses);
        - covered around: a re-admission after `at` gives a criterion of the parent's this node is mapped to a
          responsible child it did not have before, read off the logged admissions' mappings on either side (§12.14);
          on a graph whose admissions were not logged, a sibling re-ASSIGNed after `at` now carrying such a criterion
          — the canon's visible over-approximation (a sibling co-covering from before consumes nothing);
        - mapped to no criterion of the parent's current version.
        A root is consumed only through Dep. A settled cascade alone consumes nothing. Without the log (a bare graph)
        `at` is unknown and the legs read the standing state — the stricter side: a parent that ever delivered.
        Past consumption the recovery is the issuer's re-decomposition; within its own rework, the whole's
        executor repairs the artifact it delivers (a part read on that delivery fails there, §8.4).
        `resting=False` reads the plan's legs alone — whether the split has moved past the node, which a pass resting
        on it does not say (a refuted pass the split covered around holds no COMPLETE back, `frontier.uncovered`)."""
        if task.state not in (State.DONE, State.ABANDONED):
            return True                    # no reopen question outside the quasi-terminals — fail-closed
        audit = self.audit
        at = audit.last_at(task.id, new_state=task.state) if audit is not None else -1
        after = (lambda tid, **kw: audit.last_at(TaskId(tid), **kw) > at) if audit is not None else None
        parent = self.get_parent(task.id)
        if task.state == State.DONE and resting:
            if parent is not None and (after(parent.id, signal=Signal.DELIVER) if after else
                                       parent.iteration > 0 or parent.state in (State.VALIDATING, State.DONE)):
                return True
            built_on = {State.EXECUTING, State.BLOCKED, State.VALIDATING, State.REWORKING, State.DONE}
            for e in self.dep_edges(adopted=True):
                if e.from_id != task.id or (consumer := self.get_task(e.to_id)) is None:
                    continue
                if (audit.occupied_since(consumer.id, at) if audit is not None else {consumer.state}) & built_on:
                    return True
        if parent is None:
            return False
        mine = {m.criterion_name for m in parent.criterion_mappings if m.child_id == task.id}
        history = coverage_history(self._storage, audit, parent.id)
        then, later = coverage_at(history, at)
        me = str(task.id)
        if not mine or any(all(k != me for _, k in cov) for cov in later):
            return True                    # mapped to no criterion — now, or as a logged act after it settled left it
        if history:                        # …once logged, it stands: a later remap does not give the node back
            mine = {c for c, k in then if k == me} if then is not None else mine
            # covered around: a re-admission after it settled gave one of its criteria a child it did not have
            return any(c in mine and k != me and (c, k) not in (then or ()) for cov in later for c, k in cov)
        for m in parent.criterion_mappings:   # no admission logged: a sibling re-ASSIGNed after it — the proxy
            if m.criterion_name in mine and m.child_id != task.id and (sib := self.get_task(m.child_id)) is not None \
                    and sib.state not in (State.CANCELLING, State.ABANDONED) \
                    and (after(sib.id, signal=Signal.ASSIGN) if after else True):
                return True                # covered around by a re-admission after it settled
        return False

    def issuer_of(self, task_id: TaskId) -> Optional[AgentId]:
        """WHOSE the node's issuer signals are (§10.1): the parent's Del — or, at a root, the goal's
        issuer, recorded when the root was created. One owner, because the rule was written twice (the
        engine's `issuer_of` and the signal validator's role check) and the two have to agree.

        A root's issuer is the party that created it (§15.2), and it is NOT always the root's Del: a
        user who hands the whole goal to a system executor stays its customer. Reading it as Del(root)
        made that executor its own issuer — answering its own disputes and extending its own contract,
        the self-check §16.13 names as an IC violation. A root created before the record existed has
        none, and reads as it always did: its own Del ("at a self-assigned root the same agent holds
        the role")."""
        parent = self.get_parent(task_id)
        if parent is not None and parent.assignee:
            return parent.assignee
        recorded = self._storage.get_setting(root_issuer_key(task_id))
        if recorded:
            return AgentId(recorded)
        task = self.get_task(task_id)
        return task.assignee if task is not None else None

    def all_tasks(self) -> list[Task]:
        """Every node, settled or not."""
        return self._storage.get_all_tasks()

    def active_tasks(self) -> list[Task]:
        """Every node not in a terminal state. What "settled" means is the graph's to say, and it says
        it once: two spellings of it disagreed about an ESCALATED child and cost a paid run."""
        return self._storage.get_active_tasks()

    def save_task(self, task: Task) -> None:
        self._storage.save_task(task)

    @property
    def one_write(self):
        """The store's lock that makes a read and its write one step (`StoragePort._one_write`)."""
        return self._storage.one_write

    def update_task(self, task_id: TaskId, **fields) -> Task:
        """These fields of the node, off the log's pump (`StoragePort.update_task`)."""
        return self._storage.update_task(task_id, **fields)

    def build_context(self, task_id: TaskId) -> GraphContext:
        """The node plus its neighbourhood — parent, children, dep edges — as the AI layer reads it."""
        task = self._storage.get_task(task_id)
        if task is None:
            raise ValueError(f"task {task_id} not found")
        children = self.get_active_children(task_id)  # solver/checks validate the ACTIVE decomposition
        parent = self._storage.get_parent(task_id)
        check_results = self._storage.get_check_results(task_id)
        recommendation = self._storage.get_recommendation(task_id)
        return GraphContext(
            task=task,
            children=tuple(children),
            parent=parent,
            check_results=tuple(check_results),
            recommendation=recommendation,
        )

    def build_dispatch_payload(self, task_id: TaskId, signal: Signal) -> DispatchPayload:
        """The packet handed to a participant on ASSIGN: the contract, and nothing about how it was
        derived. What is NOT here is deliberate — an executor that could read the plan around it
        would be validated on a contract it did not consent to (Inv-1)."""
        task = self._storage.get_task(task_id)
        if task is None:
            raise ValueError(f"task {task_id} not found")
        check_results = self._storage.get_check_results(task_id)
        recommendation = self._storage.get_recommendation(task_id)
        return DispatchPayload(
            signal=signal,
            task=task,
            check_results=tuple(check_results),
            recommendation=recommendation,
        )

    def generation_of(self, task_id: TaskId) -> tuple:
        """The node's CONTRACT-AND-DELIVERY generation: (iteration, reopens, revisions).

        A verdict is about the delivery a validator READ, so it must be stamped with the generation
        that stood when the run STARTED — stamping at record time makes a late verdict describe
        whatever the node has become since (a rework, a reopen, or a revision under §12.10), which is
        exactly the state the self-PASS gate then reads as current. A graph fact, owned here: the
        engine asks it, the signal pump asks it, and `stamped_with` compares a record against it."""
        t = self.get_task(task_id)
        # A node that is not there has no generation; the fields themselves are declared, so they
        # are read as declared.
        return generation_of_task(t)

    def exec_verdict_record(self, task_id: TaskId) -> Optional[dict]:
        """THE one reader of the stored independent-validation record ({verdict, failed_criteria,
        validator, iteration, ts} or None) — the self-PASS gate, q_V and false_fail_share all
        consume it; parsing lived in three copies before."""
        raw = self._storage.get_exec_verdict(task_id)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    def void_pending_pass(self, task_id: TaskId, reason: str) -> None:
        """Void a recorded PASS whose delivery no longer stands (§12.10/§12.14: a re-ASSIGN "voids the
        pending delivery" — the node re-earns its verdict through ACCEPT→DELIVER→VALIDATE).

        Only a PASS is voided. A recorded FAIL is left exactly as it is: it opens no gate, and it
        carries the refutation the re-delivery disposition reads (the criteria snapshot that tells a
        repair from a lowered criterion). The record is rewritten in place — this store holds the
        CURRENT verdict and always did ("the superseded record is replaced, never trusted forward");
        the event itself stays in the log (Inv-7)."""
        rec = self.exec_verdict_record(task_id)
        if not rec or rec.get("verdict") != Verdict.PASS:
            return
        rec = dict(rec, verdict="VOID", superseded_verdict=Verdict.PASS, voided_because=reason)
        self._storage.store_exec_verdict(task_id, json.dumps(rec))

    def store_check_results(self, task_id: TaskId, results: list[CheckResult]) -> None:
        self._storage.store_check_results(task_id, results)

    def store_recommendation(self, task_id: TaskId, rec: Recommendation) -> None:
        self._storage.store_recommendation(task_id, rec)



def live_index(graph: Graph) -> tuple[list, dict, list, dict]:
    """(the live nodes in the store's order, {parent id: its live children}, their ids sorted, {id: its place}): the one
    pass over every node each subtree is then walked in (`subtree_of`)."""
    def read():
        """The index, made from the live nodes."""
        tasks = graph.subtree_view(None)
        by_parent: dict = {}
        for t in tasks:
            by_parent.setdefault(str(t.parent_id), []).append(t)
        return tasks, by_parent, sorted(str(t.id) for t in tasks), {str(t.id): j for j, t in enumerate(tasks)}
    return graph.kept(("live_index",), read)


def subtree_of(index: tuple, root: str) -> list[Task]:
    """`root` and every live node beneath it by the parent edges, and every live node whose id spells it as an
    ancestor (`Graph.subtree`), in the store's order — walked over `live_index`, not over every node."""
    tasks, by_parent, ids, at = index
    seen, frontier = {root}, [root]
    while frontier:
        for child in by_parent.get(frontier.pop(), []):
            if str(child.id) not in seen:
                seen.add(str(child.id))
                frontier.append(str(child.id))
    i = bisect.bisect_left(ids, root + ".")       # …the ids spelling its ancestry: one run of the sorted ids
    while i < len(ids) and ids[i].startswith(root + "."):
        seen.add(ids[i])
        i += 1
    return [tasks[j] for j in sorted(at[x] for x in seen if x in at)]


def root_of(tasks: list[Task]) -> Optional[Task]:
    """THE root of this project — the one node that carries the goal, or None before there is one.

    A project has exactly one. The derivation is the composition rule, not taste: the root carries the
    goal's criteria, so V(root) IS the goal's verdict, and the canon's one composition rule is
    V(parent) = AND(V(children)), which needs a parent. Two parentless nodes have no parent, so a
    project holding two has no object that says whether the PROJECT is done. Two tasks that share
    nothing compose to nothing — those are two projects; two that share something have the thing they
    share as their parent, and that parent is the root. There is no third case, and so no version of
    this where a second root means something.

    Read rather than stored, so it cannot disagree with the graph it describes; a free function over
    the node list rather than a method, because `Graph` is at its class-size limit and this is a shape
    question like `dep_scope` and `non_leaf_ids` beside it. It takes EVERY node, tombstones included:
    a cancelled root is still this project's root, and skipping it would re-open the very path the
    rule closes — refuse the goal, then build a fresh root beside its corpse."""
    roots = [t for t in tasks if t.parent_id is None]
    if not roots:
        return None
    # A graph written BEFORE the rule can hold several, and the measured run that motivated the rule
    # produced exactly that. Nothing here can decide which of them was the goal, so this at least
    # does not decide it DIFFERENTLY on each read: oldest first, ties by id. An arbitrary answer
    # that changes between calls is how one reader's "the root" stops being another's.
    return min(roots, key=lambda t: (t.created_at, str(t.id)))


def dep_order_refutations(graph: Graph) -> list:
    """The discovered records that ASK and sit on a cycle of live WAITS: contact found a consumer needs a
    producer that cannot finish before it (§15.5). The waits are E_Dep, the asking records and a parent's
    wait on its children (its PASS is their AND, Thm 1), each only while its producer is unfinished — a
    wait on a DONE node is over. So two blocks naming each other, or a block naming its own ancestor or
    itself, is on such a cycle (critic, 2026-09-27: read over E_Dep alone, the pair was asked by nobody).

    A record ASKS while it is open — the BLOCK that made it stands — or confirmed, not adopted, and both ends
    live. An open one is its blocked node's issuer's to answer (the BLOCK is his, Inv-8); a confirmed one
    refutes the plan's ORDER, which only its split's issuer can restore by re-decomposing."""
    asking, waits = _live_waits(graph)
    return [e for e in asking if e in waits and _closes_cycle(waits, e)]


def _live_waits(graph: Graph) -> tuple[list, list]:
    """(the discovered records that ASK, every live WAIT) — the population `dep_order_refutations` reads its cycles in."""
    adopted = graph.dep_edges(adopted=True)
    have = {(str(e.from_id), str(e.to_id)) for e in adopted}
    live = {str(t.id): t for t in graph.subtree_view(None)}
    unfinished = {i for i, t in live.items() if t.state != State.DONE}
    asking = [e for e in graph.dep_edges()
              if (str(e.from_id), str(e.to_id)) not in have and str(e.from_id) in live and str(e.to_id) in live]
    return asking, [e for e in adopted + asking if str(e.from_id) in unfinished] + [
        DepEdge(from_id=t.id, to_id=t.parent_id) for i, t in live.items()
        if i in unfinished and t.parent_id is not None]


def parent_waits(graph: Graph) -> list:
    """(child → parent) for every live node under a parent: a parent waits on its parts, its PASS being their AND
    (Thm 1). Read beside E_Dep wherever a cycle of waits is asked — a Dep closing one through it is a wait no order
    ends (CHECK-2, §9.5)."""
    return list(graph.kept(("parent_waits",), lambda: _parent_waits(graph)))


def _parent_waits(graph: Graph) -> list:
    live = {str(t.id): t for t in graph.subtree_view(None) if t.state not in (State.CANCELLING, State.ABANDONED)}
    return [DepEdge(from_id=t.id, to_id=t.parent_id) for t in live.values()
            if t.parent_id is not None and str(t.parent_id) in live]


def start_waits(graph: Graph, unit: Callable[[Task], str]) -> tuple[dict, dict]:
    """({node: the producers whose pass its start waits on}, {(node, producer): the cycle that wait would close}),
    read over START UNITS: `unit(t)` is what starts with t — the top of the one session that carries it, else t.

    DECLARED waits are E_Dep (§11.3): a node always waits for its own adopted sources — CHECK-2 refuses at declaration
    an edge closing a cycle with them and the parents' waits, and a session is not formed over a subtree a declared
    edge leaves and re-enters (`validation.scope_top`), so they close none. INFERRED waits are what a part takes from
    a whole through φ (§2.7): an adopted edge p → a says a's criteria read p's result, and the part φ maps the
    criterion carrying it to carries that reference, so it waits for p as a does — the carrying criteria a's on p
    (`depends_on`), or all of a's where none names p (always under AUTO, whose plans write none: every mapped part
    then waits for every producer of its whole, no stricter than the unsplit node); below the first part, every
    criterion of the part. Not a part φ maps nothing of it to, nor one below an edge from a's own subtree or from its
    ancestor (the whole reading its own part).

    An inferred wait is not taken where it lies on a cycle of live unit waits — declared, parents', inferred, each
    while its producer is unfinished — since no order ends it. Every such wait is left out at once, not one chosen by
    an order, and returned with its cycle for the readers to say."""
    live = {str(t.id): t for t in graph.subtree_view(None) if t.state not in (State.CANCELLING, State.ABANDONED)}
    u = {i: unit(t) for i, t in live.items()}

    def chain(i: str) -> list[str]:
        """The live node `i` and its live ancestors, nearest first."""
        out = []
        while i in live:
            out.append(i)
            i = str(live[i].parent_id) if live[i].parent_id else ""
        return out
    adopted = graph.dep_edges(adopted=True)
    declared = {(str(e.from_id), str(e.to_id)) for e in adopted if str(e.to_id) in live}
    inferred: set = set()
    for e in adopted:
        p, a = str(e.from_id), live.get(str(e.to_id))
        if a is None or str(a.id) in chain(p) or p in chain(str(a.id)):
            continue
        stack = [(a, {c.name for c in a.spec.criteria if str(c.depends_on or "") == p}
                  or {c.name for c in a.spec.criteria})]
        while stack:
            n, carrying = stack.pop()
            for k in sorted({str(m.child_id) for m in n.criterion_mappings if m.criterion_name in carrying}):
                if ((part := live.get(k)) is not None and str(part.parent_id) == str(n.id)
                        and (p, k) not in declared | inferred):
                    inferred.add((p, k))
                    stack.append((part, {c.name for c in part.spec.criteria}))

    def waiting(p: str, t: str) -> bool:
        """Does `t`'s start unit still wait on `p` — live, unfinished, in another unit?"""
        return p in live and live[p].state != State.DONE and u[p] != u[t]
    adj: dict[str, set] = {}
    for p, t in declared | inferred | {(str(e.from_id), str(e.to_id)) for e in parent_waits(graph)}:
        if waiting(p, t):
            adj.setdefault(u[p], set()).add(u[t])
    out: dict[str, set] = {}
    for p, t in declared:
        out.setdefault(t, set()).add(p)
    dropped = {}
    for p, t in inferred:
        if waiting(p, t) and (path := _path(adj, u[t], u[p])):
            dropped[(t, p)] = path
        else:
            out.setdefault(t, set()).add(p)
    return out, dropped


def _path(adj: dict, start: str, goal: str) -> list:
    """The shortest path `adj` leads along from `start` to `goal` (ties by id), or []."""
    prev, todo = {start: None}, [start]
    while todo:
        n = todo.pop(0)
        if n == goal:
            out = []
            while n is not None:
                out.append(n)
                n = prev[n]
            return out[::-1]
        for m in sorted(adj.get(n, ())):
            if m not in prev:
                prev[m] = n
                todo.append(m)
    return []


def _reach(adj: dict, start: str) -> set:
    """Every node `adj` leads to from `start`, `start` included."""
    seen, stack = set(), [start]
    while stack:
        if (n := stack.pop()) not in seen:
            seen.add(n)
            stack.extend(adj.get(n, ()))
    return seen


def _closes_cycle(edges: list, e) -> bool:
    """Would adding `e` let its consumer reach its producer along `edges` (or is it its own producer)?"""
    adj: dict[str, list[str]] = {}
    for x in edges:
        adj.setdefault(str(x.from_id), []).append(str(x.to_id))
    return str(e.from_id) in _reach(adj, str(e.to_id))


def cycle_stands_without(graph: Graph, refuted: list, gone: set, through: set) -> bool:
    """Would one of the `refuted` records still close a cycle of live waits running through a node of `through`, once
    the waits of the `gone` (producer, consumer) pairs are taken out?"""
    adj: dict[str, list[str]] = {}
    back: dict[str, list[str]] = {}
    for w in _live_waits(graph)[1]:
        if (p := str(w.from_id), c := str(w.to_id)) not in gone:
            adj.setdefault(p, []).append(c)
            back.setdefault(c, []).append(p)
    return any((p := str(e.from_id), c := str(e.to_id)) not in gone and p in _reach(adj, c)
               and _reach(adj, c) & _reach(back, p) & through for e in refuted)


def cycle_children(graph: Graph, parent_id, refuted: list) -> list[list[str]]:
    """The parent's live children each refuted wait's cycle runs through — every child on a path of live waits from the
    consumer's child back to the producer's, the waits read between the children that contain their ends — grouped
    where cycles share a child, each group sorted. A wait whose ends sit in one child, or outside the parent's
    children (a block naming its own ancestor), puts no group here: no merge of children restores it."""
    kids = {str(k.id) for k in graph.get_active_children(parent_id)}

    def child(x) -> str | None:
        """The parent's child that `x` is or sits under, or None."""
        t = graph.get_task(TaskId(str(x)))
        while t is not None and str(t.id) not in kids:
            t = graph.get_task(t.parent_id) if t.parent_id else None
        return str(t.id) if t is not None else None
    fwd: dict[str, set] = {}
    back: dict[str, set] = {}
    for w in _live_waits(graph)[1]:
        a, b = child(w.from_id), child(w.to_id)
        if a and b and a != b:
            fwd.setdefault(a, set()).add(b)
            back.setdefault(b, set()).add(a)
    groups: list[set] = []
    for e in refuted:
        p, c = child(e.from_id), child(e.to_id)
        if not (p and c) or p == c:
            continue
        g = (_reach(fwd, c) & _reach(back, p)) | {p, c}
        for h in [h for h in groups if h & g]:
            groups.remove(h)
            g |= h
        groups.append(g)
    return [sorted(g) for g in groups]

def dep_scope(graph: Graph, root_id: TaskId) -> tuple[list, dict[str, object]]:
    """The Dep pairs a node's plan checks quantify over, and the deadlines of their endpoints.

    ONE owner, because there were two and they disagreed. The cached computation
    (`Engine._recompute_checks`) handed the checks EVERY edge in the graph; the execution gate
    (`validation._l0_holes`) handed them only edges with both endpoints among the node's direct
    children. The checks themselves then silently dropped whatever fell outside the sibling set,
    so a Dep edge between two nodes under DIFFERENT parents — the ordinary shape of a seam once
    a plan has two branches — was examined by nobody: `list_holes` said `count: 0`, the plan gate
    admitted execution, and `check_dag` over the whole graph named the very cycle those surfaces
    called clean. The canon quantifies CHECK-2 and CHECK-3 over Dep itself (§9.5), so the
    population is the SUBTREE: at the root that is the whole relation, and below it the seams
    that decomposition owns. Reported at the node whose plan declares them.
    """
    edges, deadlines = graph.kept(("dep_scope", str(root_id)), lambda: _dep_scope(graph, root_id))
    return list(edges), dict(deadlines)


def _by_end(edges: list) -> tuple[list, dict]:
    """(edges, {node id: the places in `edges` of those it is an end of})."""
    by_end: dict = {}
    for i, e in enumerate(edges):
        for x in {str(e.from_id), str(e.to_id)}:
            by_end.setdefault(x, []).append(i)
    return edges, by_end


def _dep_scope(graph: Graph, root_id: TaskId) -> tuple[list, dict[str, object]]:
    inside = {str(t.id): t for t in graph.subtree_view(root_id)}
    known = live_index(graph)[3]
    adopted, by_end = graph.kept(("adopted_by_end",), lambda: _by_end(graph.dep_edges(adopted=True)))
    edges = []
    # …only the edges with an end inside can count: read off their ends, not by a pass over every edge at every node
    for e in (adopted[i] for i in sorted({i for x in inside for i in by_end.get(x, ())})):
        ends = (str(e.from_id), str(e.to_id))
        if all(x in inside for x in ends):
            edges.append(e)
        elif any(x in inside for x in ends) and not all(x in known for x in ends):
            # A DANGLING endpoint is not "outside this population", it is a plan naming a producer
            # that does not exist — the node's own defect, and the node's own checks must see it.
            # Filtering purely on membership swallowed it: a criterion whose `depends_on` was a LIST
            # (the malformed value that ended a live run) stringifies to an id no node has, so the
            # edge silently left every population and the contract carrying it was stored clean.
            # Skipping an edge because it is outside a subtree is right; skipping one because its
            # endpoint is nowhere is the same "not examined by anybody" this function exists to end.
            edges.append(e)
    # EVERY LIVE DEADLINE, a supplied default included: §9.5's CHECK-3 is over every Dep pair, and §2.5 lets an
    # implementation write a default inside the parent's — it does not waive §2.7 for it. Exempting them left every
    # undated plan's Dep time guard inert while the clock still enforced deadlines written equal along a chain (critic
    # over session 475ba784; every door now writes them ordered, `mutations.Schedule`). A SETTLED node's
    # deadline orders nothing still to come, and CHECK-3 reads no edge with a settled end (§11.5).
    return edges, {i: (None if t.state in TERMINAL_STATES else t.deadline)
                   for i, t in inside.items()}


def standing_split(graph, node):
    """(node, its active children) with the node's mappings onto those children only — the split as it stands (§12.6:
    a settled cancellation takes its child out of the plan, and the battery reads the active children). A mapping left
    onto a child out of the plan covers nothing: read as coverage it was an "invalid mapping" no repair but a whole
    re-decomposition cleared, while the admission, reading the active children, had already covered around it."""
    kids = graph.get_active_children(node.id)
    ids = {str(k.id) for k in kids}
    return dataclasses.replace(node, criterion_mappings=tuple(
        m for m in node.criterion_mappings if str(m.child_id) in ids)), kids


def non_leaf_ids(graph: Graph, children: list[Task]) -> set[str]:
    """Which of these children decompose further — the fact CHECK-6 needs and a single split does
    not carry (§9.5 quantifies over LEAVES). A node that splits is accountable through its own
    children; demanding an executor for it reads Del as a label rather than as §2's per-node
    accountability.

    A derived question over the public surface, so it lives beside the graph rather than on it: a
    class that answers every question ABOUT a thing is how a facade stops being one.
    """
    return {str(c.id) for c in children if graph.get_active_children(c.id)}


def logged_criteria(raw) -> list[dict]:
    """A logged version's criteria (its `spec` JSON) as the contract it installed: an entry an older engine wrote there
    to declare a Dep edge — a `depends_on` pinning no check — is that edge (`logged_declarations`), no criterion
    (`seams_apart`). Read as one, every node with a seam reads as having dropped a criterion since its authoring."""
    try:
        crits = json.loads(raw).get("criteria") or []
    except (TypeError, ValueError, AttributeError):
        return []
    return [c for c in crits if isinstance(c, dict) and not (c.get("depends_on") and not c.get("check"))]


def logged_declarations(log: list) -> list[tuple[str, str, str]]:
    """(producer, consumer, glue) for every `depends_on` entry of every packet version the log (`load_audit` rows)
    installed — the declarations an older engine kept among the criteria, and a criterion's reference since."""
    out = []
    for row in log:
        if row.get("rejected") or not row.get("spec"):
            continue
        try:
            crits = json.loads(row["spec"]).get("criteria") or []
        except (TypeError, ValueError, AttributeError):
            continue
        out += [(str(c["depends_on"]), str(row.get("task_id")), str(c.get("description") or ""))
                for c in crits if isinstance(c, dict) and c.get("depends_on")]
    return out
