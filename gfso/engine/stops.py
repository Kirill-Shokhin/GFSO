"""The project's stop: a person's Stop and Start, and the stops the system makes and lifts by itself — the account's
limit, an account refusing authentication, an execution place down — with the time each held left off the project's
clocks and recorded on every deadline it moved.

Why a class of its own: its state is its own — the lock a person's stop and the system's lift never cross on, the
place probe and when it last answered, the credential store's stamp — and nothing else in the engine reads it. The
engine hands it the graph, the store, the log, its event line and its record lists (`Engine.stops`); the stop itself
is a setting (`PAUSE_KEY`), so every reader of "is it stopped" outside reads the record (`readers`' `pause_record`).
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from gfso.config import LIMIT_RETRY_S, caller_via
from gfso.core.types import TERMINAL_STATES, Task, VOLUME
from gfso.core.graph.model import DEADLINE_MOVES, PAUSE_KEY, clock_off_s, keep_the_beat, on_the_wall
from .validation import issuing_condition, pause_record

#: How long after the account's limit says it lifts the system starts the project it stopped: a clock or two apart.
LIFT_MARGIN_S = 30
#: what of a stop's record the system lifts it by: a time, an execution place, a credential store's stamp
LIFTS = ("until", "place", "account")
#: How long what the place probe said stands for R′'s gate (`place_down`): each asking is a container of its own.
PLACE_SEEN_S = 60


def _via() -> dict:
    """The credential the act came through, as the log keeps it beside a signer (`config.caller_via`) — none in process."""
    return {"via": v} if (v := caller_via()) else {}


def _via_said() -> str:
    """…and as an event line says it: a page's stop told from a console's."""
    return f" via {v}" if (v := caller_via()) else ""


class Stops:
    """A project's stops (`pause`/`resume`) and the system's own (`stop_for_the_*`, lifted by `lift_the_system_stop`)."""

    def __init__(self, graph, storage, audit, emit, records, appended):
        self._graph, self._storage, self._audit = graph, storage, audit
        self._emit = emit                   # the engine's event line (`Engine.emit_info`)
        self._records, self._appended = records, appended   # the engine's lists kept in one setting each
        self._stop_lock = threading.Lock()  # a person's stop and the system's start of its own stop never cross
        self._place_probe = None            # where the project runs, asked while it is down (`probe_the_place_with`)
        self._place_seen = None             # when the place probe last said it answers (`place_down`)
        self._account_probe = None          # the credential store's stamp, asked under an account's stop

    def paused(self) -> Optional[dict]:
        """The project's stop as set — {by, at, why} — or None while it runs (`validation.pause_record`)."""
        return pause_record(self._graph)

    def pause(self, by: str, why: str = "", until: Optional[float] = None, place: Optional[str] = None,
              account: Optional[str] = None) -> dict:
        """STOP: the system starts no session of any role here — sessions already running finish and their signals land
        — and the clock fires no timeout; its time is left off the project's clocks, tick by tick. It writes
        nothing into the graph: a stop is the user's act on the run, not a protocol move. A stop standing already is
        kept as it was: a second one would lose the time of the first — except one the system starts again by itself
        (`until`, the account's limit; `place`, an execution place down): a later lift extends it, and any other stop
        over it takes it, keeping its start, so the system never starts what a person stopped. `off_s`: the doors' off
        time while it stands (`model.door_off_s`). `account`: the credential store's stamp an account's stop was made
        on — a person setting a credential changes it, and the stop lifts then (`lift_the_system_stop`)."""
        self.keep_the_beat("the host slept", "the stop")
        with self._stop_lock:
            was = self.paused()
            held = {k: was[k] for k in LIFTS if (was or {}).get(k) or k == "account" and (was or {}).get(k) is not None}
            lifts = {**held, **({"until": max(until, held.get("until", 0))} if until else {}),
                     **({"place": place} if place else {}),
                     **({"account": account} if account is not None else {})} if until or place else {}
            if was and (not held or lifts == held):
                return was
            rec = {**{k: v for k, v in (was or {"at": datetime.now().isoformat(timespec="seconds"),
                                                "off_s": clock_off_s(self._graph)}).items() if k not in held},
                   "by": str(by), "why": str(why or ""), **lifts, **_via()}
            self._storage.store_setting(PAUSE_KEY, json.dumps(rec))
        # …ONE LINE PER STOP: the system's own stop only extended by the same cause says nothing new — one refused
        # authoring booked its calls at once and wrote five STOPPED lines for one missing credential (s20g1)
        if not (was and held and str(by) == "system" and set(lifts) == set(held)):
            self._emit("pause", f"STOPPED by {by}{_via_said()}" + (f": {why}" if why else "") + " — nothing new starts")
        return rec

    def resume(self, by: str) -> Optional[dict]:
        """START again: the stop that stood, or None where none did. Its time is already off the project's clocks: the
        monitor leaves off every tick made under a stop (`project_now`)."""
        self.keep_the_beat("the host slept", "the start")
        with self._stop_lock:
            was = self._take_the_stop()
        if was:
            self._emit("pause", f"STARTED again by {by}{_via_said()} (stopped since {was.get('at')})")
            self._record_the_held_time(was, by)
        return was

    def keep_the_beat(self, cause: str, by: str) -> None:
        """The beat kept NOW, before a start, a stop or its lift reads the clock (`keep_the_beat`): the gap since the last
        beat is decided under the stop as it stood across it — a sleep a Start right after a wake would count once in the
        stop's held time and again at the next tick, and a Stop there would leave off unrecorded — and recorded, `cause`."""
        if gap := keep_the_beat(self._graph, time.time()):
            self.record_the_gap(cause, *gap, by)

    def _take_the_stop(self, standing: Optional[dict] = None) -> Optional[dict]:
        """The stop taken off as one act on the store (`Graph.swap_settings`) — `standing`, where given, only while it is
        the stop that stood: of two engines over one project lifting it, one takes it and records its held time."""
        took = None

        def take(get):
            """The stop cleared inside the store's one act, if it stands (as `standing`, where given)."""
            nonlocal took
            was = json.loads(get(PAUSE_KEY) or "null")
            if not was or standing is not None and was != standing:
                return {}
            took = was
            return {PAUSE_KEY: ""}
        self._graph.swap_settings(take)
        return took

    def record_the_gap(self, cause: str, since: float, before: float, by: str) -> None:
        """A gap nobody ran the project in, left off its clocks — a server down, a host asleep — recorded on the deadlines
        it moves as a stop's held time is (`_record_the_held_time`), `cause` in the stop's place — told by the one caller
        that kept it (`keep_the_beat`)."""
        self._record_the_held_time({"by": cause, "at": datetime.fromtimestamp(since).isoformat(timespec="seconds"),
                                    "off_s": before, "gap": True}, by)

    def _record_the_held_time(self, was: dict, by: str) -> None:
        """THE RECORD OF THE DECLARED DEPARTURE, ON EVERY DEADLINE IT MOVES. Where the system carries the work, the time
        a stop held is left off the project's clocks (`time_holds`) — a decision the canon does not make, its deadline
        "never suspended" (§12.2), declared as the product's (architecture, corner 16) — so each live deadline reads that
        much later on the wall, and Thm 11 asks that decision a record: the node's own says the deadline as it read before
        and after, how long the time held, who or what stopped it and what started it again. Beside the log, as a
        finding's ruling is (corner 18), not a revision: a re-ASSIGN would re-offer every consented node (Inv-1),
        re-present every delivery (§12.10) and make a person's issuer move on his own nodes."""
        if was.get("off_s") is None or (held := clock_off_s(self._graph) - float(was["off_s"])) < 1:
            return
        rec = {"held_s": round(held, 1), "stopped_by": was.get("by"), "why": was.get("why") or "",
               "since": was.get("at"), "started_by": str(by), "at": datetime.now().isoformat(timespec="seconds"),
               "log_at": len(self._audit)}
        for t in self._graph.active_tasks():
            if t.deadline is not None:
                now = on_the_wall(self._graph, t.deadline)
                self._appended(f"{DEADLINE_MOVES}{t.id}", {
                    "was": (t.deadline + timedelta(seconds=float(was["off_s"]))).isoformat(), "now": now.isoformat(), **rec})
                self._emit("clock", f"{t.id}: its deadline reads {held / 60:.0f} min later, {now:%Y-%m-%d %H:%M} — "
                                        f"{'' if was.get('gap') else 'the stop by '}{was.get('by')} since "
                                        f"{was.get('at')}, the project's time held; "
                                        f"its contract and consent stand")

    def deadline_moves(self, task_id) -> list[dict]:
        """How the node's deadline moved on the wall, oldest first (`_record_the_held_time`)."""
        return self._records(f"{DEADLINE_MOVES}{task_id}")

    def stop_for_the_limit(self, role: str, lifts_at: Optional[float]) -> dict:
        """THE ACCOUNT'S LIMIT IS A STOP IN SUBSTANCE: while it refuses every call nobody can move, so no bound may run
        (docs/notes/PROJECT_CLOCK.md, case 10). The system stops the project until the limit lifts — when the CLI said,
        else after LIMIT_RETRY_S, when the next refused call (a second's probe) stops it again."""
        until = float(lifts_at) + LIFT_MARGIN_S if lifts_at else time.time() + LIMIT_RETRY_S
        return self.pause("system", f"the account's usage limit refused {role}'s call — until "
                                    f"{datetime.fromtimestamp(until):%Y-%m-%d %H:%M}", until)

    def stop_for_the_account(self, role: str, why: str, remedy: Optional[str] = None) -> dict:
        """AN ACCOUNT THAT REFUSES AUTHENTICATION IS A STOP IN SUBSTANCE, as the limit is: no call of any role answers
        until a person sets its credential (`remedy`, the provider's words), and the redials of a cut call spent an hour
        on it while every bound ran (GB_c_compiler_tncfs1160, 2026-10-23 11:29–12:29: four nodes timed out). Stopped, and
        asked again after LIMIT_RETRY_S — the next refused call stops it again — or at once when a credential is set: a
        stop timed alone held a project ten minutes past the credential that lifted it (s20g1, 01:47→01:57)."""
        until = time.time() + LIMIT_RETRY_S
        said = remedy or (f"the account refused authentication ({why[:160]}): set its credential again "
                          f"(`gfso credential <provider>`)")
        return self.pause("system", f"{role}'s call: {said}; asked again {datetime.fromtimestamp(until):%Y-%m-%d %H:%M}, "
                                    f"or once a credential is set", until, account=self._account_stamp() or "")

    def probe_the_account_with(self, stamp) -> None:
        """Hand the engine `stamp()`: the credential store's state as one string, changed by any credential set
        (`credentials.stamp`) — from the layer that knows the store, as the place probe is handed."""
        self._account_probe = stamp

    def _account_stamp(self) -> Optional[str]:
        """The credential store's stamp now, or None where no layer handed a probe or it did not answer."""
        try:
            return None if self._account_probe is None else str(self._account_probe())
        except Exception:                               # noqa: BLE001 — a probe that fails says nothing changed
            return None

    def stop_for_the_place(self, place: str, why: str) -> dict:
        """AN EXECUTION PLACE DOWN IS A STOP IN SUBSTANCE, as the limit is: no session of any role can start, so nobody
        can move (PROJECT_CLOCK.md, case 14). Stopped until the place answers its probe (`lift_the_system_stop`)."""
        return self.pause("system", why, place=place)

    def probe_the_place_with(self, probe) -> None:
        """Hand the engine the probe of where its project runs — `probe(place)`: why the place its stop names cannot
        answer a call, or None — the execution's (`ExecutionPort.unavailable`), or a model server's address
        (`chat.answers`) — from the layer that knows the places, as `joins.set_join_owed` is handed."""
        self._place_probe = probe

    def reopen_place_refusal(self, t: Task) -> Optional[str]:
        """Why a settled node may not cross R′'s edge now: the place its project runs in does not answer, so the
        reopened node could not be worked and the reopen would be spent for nothing — or None. §12.16 (ii): it names
        the requirement and the person's lift. Read by R′'s gate (`reopen_refusal`), which every door that reopens asks
        — `reopen`, a re-admission re-issuing a settled child, `refusal_for` — and by `_revise`, the FSM's own door."""
        # …and not where the edge is shut for good: a place brought back would not lift that, its own gate says why
        if t.state not in TERMINAL_STATES or issuing_condition(self._graph.get_parent(t.id), t.id) \
                or self._graph.is_consumed(t) or t.reopens >= t.max_reopens or not (down := self.place_down()):
            return None
        return (f"{t.id} stays {t.state.name}: the place its project runs in does not answer ({down}), so a reopened "
                f"node could not be worked and the reopen would be spent for nothing. Bring the place back and reopen; "
                f"where its volume is gone, what of the work landed is on the branch `gfso/<project>/accepted` of your "
                f"repository, and the goal is taken up again as a new goal from there (§12.14).")

    def place_down(self) -> Optional[str]:
        """Why the volumes this project's places are recorded in cannot answer a call now (its daemon, its storage, a
        volume gone), or None — None too where none is recorded (a host's place is never down: its probe answers whether
        unattended work may run there, which a person's own work does not ask) or no layer handed a probe."""
        if self._place_probe is None or not self._graph.setting(VOLUME + "places"):
            return None
        # …one answer a minute: the R′ gate reads it on every surface that lists a reopen, each a probe container
        # …"answers" kept; "down" asked again each time, so the person's fix is read at once
        if self._place_seen is not None and time.monotonic() - self._place_seen <= PLACE_SEEN_S:
            return None
        if (down := self._probe_says("")) is None:
            self._place_seen = time.monotonic()
        return down

    def _probe_says(self, place: str) -> Optional[str]:
        """The place probe's answer; one that raises did not answer — raised here, it killed the monitor's thread, and
        no bound fired again (Inv-5)."""
        try:
            return self._place_probe(place)
        except Exception as e:                          # noqa: BLE001 — a probe that fails is a place that does not answer
            return f"{type(e).__name__}: {e}"

    def stop_wait_s(self) -> Optional[float]:
        """Seconds until the system's own stop can lift — its `until`; a place's next probe is a tick away and nothing
        starts meanwhile — or None where none stands: a round it refused, parked on a wall timer past the lift, would
        spend project time with nobody moving."""
        stop = self.paused() or {}
        if until := stop.get("until"):
            return max(1.0, float(until) - time.time() + 1.0)
        return 1.0 if stop.get("place") else None

    def lift_the_system_stop(self, wall: float) -> None:
        """START what the system stopped by itself once what stopped it is gone — the limit lifted (`until`), the place
        answering its probe (`place`) — only that stop: a person's never. The monitor asks at every tick under a stop,
        so an engine started over a standing one re-arms it from its record."""
        was = self.paused()
        # …an account's stop lifts too once its credential store moved: a person set what it waited for
        now = self._account_stamp() if was and was.get("account") is not None else None
        moved = now is not None and now != was["account"]
        if not (was and (was.get("until") or was.get("place"))) or (was.get("until") or 0) > wall and not moved:
            return
        if was.get("place") and (self._place_probe is None or self._probe_says(was["place"]) is not None):
            return
        with self._stop_lock:
            if not self._take_the_stop(was):      # a stop made while the place was probed is that stop's
                return
        self._emit("pause", "STARTED again by system: " + " and ".join(
            ([f"the execution place {was['place']} answers"] if was.get("place") else [])
            + ([] if not was.get("until") else ["a credential was set"] if moved else
               ["the time to ask the account again came"] if was.get("account") is not None else
               ["the account's limit lifted"])) + f" (stopped since {was.get('at')})")
        self._record_the_held_time(was, "system")
