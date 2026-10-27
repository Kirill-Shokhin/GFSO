"""SQLite StoragePort — persistent storage."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.request import pathname2url

from gfso import __version__

from gfso.core.types import (
    TaskId, AgentId, Task, State, DoneReason, AutonomyLevel,
    Spec, Criteria, Probe, CriterionMapping, AcceptedRiskItem, Register,
    CheckResult, Recommendation, DepEdge, seams_apart,
    StoragePort, TERMINAL_STATES, RETIRED_STATES, state_named,
)
from gfso.config import PIPELINE_PAGE, USAGE_PAGE
from gfso.core.graph.model import PAUSE_KEY

log = logging.getLogger(__name__)


def _state_of(row: sqlite3.Row) -> "tuple[State, Optional[DoneReason]]":
    # Read-side migration: pre-v3.7 DBs stored cancellation as DONE(reason=CANCELLED); canon v3.7
    # gives it its own terminal state (§12.6). Map on read — no new writes produce the legacy form.
    state = state_named(row["state"])   # a retired name another process wrote still reads
    done_reason = DoneReason[row["done_reason"]] if row["done_reason"] else None
    if state == State.DONE and done_reason == DoneReason.CANCELLED:
        state, done_reason = State.ABANDONED, None
    return state, done_reason


def _epoch(ts) -> Optional[float]:
    try:
        return datetime.fromisoformat(ts).timestamp() if ts else None
    except ValueError:
        return None


def _all(c, sql: str) -> list:
    """The rows of `sql`, or none where an older file lacks the table: that fact is then absent, not the
    whole project."""
    try:
        return c.execute(sql).fetchall()
    except sqlite3.OperationalError:
        return []


def _one(c, sql: str):
    return (_all(c, sql) or [None])[0]


def _json_or_none(value: Optional[str]) -> Optional[dict]:
    try:
        return json.loads(value) if value else None
    except ValueError:
        return None


def _mode_named(value: str) -> Optional[str]:
    try:
        return json.loads(value).get("mode")
    except (ValueError, AttributeError):
        return value or None


def peek_project(db_path: str) -> Optional[dict]:
    """What a project IS, read from a file this process has not opened as a store: its root (goal
    name, state, started), its last protocol event, its spend and its mode — None when there is no
    file or nothing readable (one bad file must not cost a picker the list). A list of projects is
    answered from here and never by building an engine: that starts its dispatcher, and an AUTO
    project's clock and machine issuer then act — paid calls woken by a look (2026-10-24).

    "Last" is the last act of a party or model call in the log, not the file's stamp: an engine
    merely loaded rewrites its file, so by mtime the projects someone LOOKED at today rose above the
    runs actually worked in.

    `immutable` when no WAL lies beside it: a read-only open of a closed WAL database still
    CREATES an empty `-wal` and `-shm` (measured 2026-09-24) — litter in the data dir, on every
    look. With a WAL present its frames are part of the data, so the read-only open reads them;
    it writes no WAL of its own."""
    if not os.path.exists(db_path):
        return None
    how = "mode=ro" if os.path.exists(db_path + "-wal") else "immutable=1"
    try:
        with closing(sqlite3.connect(f"file:{pathname2url(os.path.abspath(db_path))}?{how}",
                                     uri=True)) as c:
            c.row_factory = sqlite3.Row
            root = _one(c, "SELECT state, done_reason, spec_json, created_at FROM tasks "
                              "WHERE parent_id IS NULL ORDER BY created_at LIMIT 1")
            spent = _one(c, "SELECT MAX(ts), SUM(cost_usd) FROM llm_usage")
            # who ran it: the models of its sessions that did work — a refusal spends nothing — costliest first
            models = [r[0] for r in _all(c, "SELECT model FROM llm_usage WHERE model != '' AND (cost_usd > 0 "
                                              "OR input_tokens > 0 OR output_tokens > 0 OR cache_input_tokens > 0) "
                                              "GROUP BY model ORDER BY SUM(cost_usd) DESC")]
            # a party's act, not the clock's: lapses fire on a mere load of an old project's engine
            # (dozens within one minute on 2026-10-24), and a lapse is no one working in it
            acted = ((_one(c, "SELECT MAX(ts) FROM audit_log WHERE source IS NOT NULL") or (None,))[0]
                     or (_one(c, "SELECT MAX(ts) FROM audit_log") or (None,))[0])
            mode = _one(c, "SELECT value FROM settings WHERE key = 'mode'")
            stop = _one(c, f"SELECT value FROM settings WHERE key = '{PAUSE_KEY}'")
    except sqlite3.Error:
        return None
    out = {"goal": None, "last": max(filter(None, (_epoch(spent and spent[0]), _epoch(acted))),
                                     default=None),
           "cost": round(spent[1] or 0.0, 2) if spent else 0.0,
           "mode": mode and _mode_named(mode[0]), "models": models,
           # the stop as set — {by, at, why} — the one record `Engine.paused` reads; None while it runs
           "stopped": _json_or_none(stop and stop[0])}
    if root is not None:
        try:
            state, reason = _state_of(root)
        except KeyError:
            return out
        out["goal"] = {"state": state.name, "done_reason": reason and reason.name,
                       "name": json.loads(root["spec_json"]).get("name") or None,
                       "started": _epoch(root["created_at"])}
    return out


class _ProjectSettings:
    """The project's own settings (the mode) — one small table, its own concern beside the graph's."""

    def store_setting(self, key: str, value: str) -> None:
        with self._write() as c:
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

    def get_setting(self, key: str) -> Optional[str]:
        with self._read() as c:
            row = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


#: a Dep record's columns, in `DepEdge`'s field order
_EDGE_FIELDS = ("from_id", "to_id", "discovered", "glue", "provisional", "closed", "declared_first", "refuted", "removed")
_INSERT_EDGE = f"INSERT INTO dep_edges ({', '.join(_EDGE_FIELDS)}) VALUES ({', '.join('?' * len(_EDGE_FIELDS))})"


def _edge_row(edge: DepEdge) -> tuple:
    return tuple(v if isinstance(v, str) else int(v) for v in (getattr(edge, k) for k in _EDGE_FIELDS))


def _seams_to_edges(conn, spec_of, spec_json, maps_of, maps_json) -> None:
    """An older engine wrote a declared Dep edge as an entry of its consumer's criteria (`dep__<producer>`, its
    `depends_on` and the glue as its description) and derived E_Dep from those entries. Dep is a primitive beside T
    (§2.7, §7.5): each such entry that pins no check becomes the declared edge record it stood for and leaves the
    spec — with its node's mappings onto it — LOGGED AS A MIGRATION, not as a signal; V loses no conjunct (the
    entry was none, `seams_apart`). An entry that pins a check on the producer's result stays a criterion and gains
    its record. One pair is one edge (§2.7), however many entries named it. Idempotent: what it converts is gone, and
    a pair already stored is not stored again."""
    conn.execute("UPDATE dep_edges SET glue = '' WHERE glue IS NULL")
    live = {(r["from_id"], r["to_id"]) for r in
            conn.execute("SELECT from_id, to_id FROM dep_edges WHERE discovered = 0 AND removed = 0")}
    notes = []
    for row in conn.execute("SELECT id, spec_json, criterion_mappings_json FROM tasks").fetchall():
        spec = spec_of(row["spec_json"])
        try:
            kept, edges = seams_apart(spec, row["id"])
        except ValueError:          # a malformed producer (a list) is the signal gate's to refuse, never the open's
            continue
        bare = [c for c in spec.criteria if c not in kept.criteria]
        # one pair one edge, the later entry's glue (`one_per_pair`); a pair already stored is not stored again
        edges = [e for e in {(e.from_id, e.to_id): e for e in edges}.values() if (e.from_id, e.to_id) not in live]
        if not (edges or bare):
            continue
        conn.executemany(_INSERT_EDGE, [_edge_row(e) for e in edges])
        live |= {(e.from_id, e.to_id) for e in edges}
        if bare:
            names = {c.name for c in bare} - {c.name for c in kept.criteria}
            maps = tuple(m for m in maps_of(row["criterion_mappings_json"] or "[]") if m.criterion_name not in names)
            conn.execute("UPDATE tasks SET spec_json = ?, criterion_mappings_json = ? WHERE id = ?",
                         (spec_json(kept), maps_json(maps), row["id"]))
            notes.append(f"{row['id']}: {', '.join(f'{c.name} ({c.depends_on})' for c in bare)} — a Dep edge's "
                         f"declaration an older engine kept among the criteria, now its declared edge record; "
                         f"no conjunct of V changes (a migration, not a signal)")
    conn.executemany("INSERT INTO pipeline_log (ts, source, message) VALUES (?, ?, ?)",
                     [(datetime.now().isoformat(sep=" ", timespec="seconds"), "migration", n) for n in notes])
    if notes:
        log.info("migrated %d node(s)' Dep declarations from criteria to edge records", len(notes))
    conn.commit()


class SqliteStorage(_ProjectSettings, StoragePort):
    def __init__(self, db_path: str = "data/gfso.db"):
        self._db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # One connection is shared by every dispatcher thread (`check_same_thread=False`), so the
        # lock below — not the connection — is what makes a multi-statement write atomic. Reentrant
        # because a reader may call another reader (`get_parent` → `get_task`).
        self._lock = threading.RLock()
        with self._write() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA busy_timeout=5000")
        self._check_schema_version()
        self._init_tables()

    # === The only two ways to reach the connection ===

    @contextmanager
    def _write(self):
        """A whole mutation — every statement of it and its commit — under one lock.

        Without this, `sqlite3` in serialized mode still let a neighbouring thread's `commit()`
        publish THIS thread's half-finished write: `store_check_results` is DELETE + INSERT, and a
        commit landing between them stored a task's checks as an empty set. An exception now rolls
        the partial write back instead of leaving it for whoever commits next."""
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise

    @contextmanager
    def _read(self):
        """A read under the same lock, so a reader never lands between the statements of a write."""
        with self._lock:
            yield self._conn

    def close(self) -> None:
        """Release the file handle (Windows keeps the .db locked until the connection closes —
        project deletion depends on this)."""
        with self._lock:
            self._conn.close()

    # The schema this build of gfso writes. Bumped only when a change is not additive — the
    # migrations below handle additive ones by inspecting `PRAGMA table_info`.
    SCHEMA_VERSION = 1

    # The v4.0 rename migration (2026-08-13) used `PRAGMA user_version = 40` as its "already
    # migrated" mark, before this field carried a schema version at all. Recognised, never written.
    _V4_MIGRATION_MARK = 40

    # The two schema methods below are the ONE exception to "_read/_write own the connection":
    # they run inside `__init__`, before the store exists as a value any other thread could hold,
    # and they are DDL, which sqlite3 does not wrap in an implicit transaction anyway.
    def _check_schema_version(self):
        """Stamp the schema version, and REFUSE a database written by a newer gfso.

        Forward migration is handled below; the other direction was the silent one. A user who
        installs 0.2.0, works, then pins back to an older release opens a database this code does
        not understand: a state name it has never heard of raises `KeyError` deep inside a read, and
        the user sees a blank UI or a 500 rather than "this database is newer than this gfso".
        The stamp costs one PRAGMA and cannot be retrofitted onto databases already written, which
        is why it goes in the first release rather than the first one that needs it.
        """
        found = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if found == self._V4_MIGRATION_MARK:
            # NOT a newer schema — our own marker, in the field this stamp later claimed. The v4.0
            # rename migration wrote `user_version = 40` as its idempotence mark ("this file was
            # migrated") months before `user_version` meant "schema version" here; the refusal below
            # then read every migrated database — the default one and all 149 experiment DBs — as
            # "written by a newer gfso" and the server would not start on them at all. The rows are
            # this build's own schema, so the mark is normalised and the file opens.
            log.info("database %s carries the v4.0 migration mark (user_version=40) — normalising "
                     "it to schema %d; the schema itself is unchanged", self._db_path, self.SCHEMA_VERSION)
            self._conn.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")
            found = self.SCHEMA_VERSION
        if found > self.SCHEMA_VERSION:
            raise RuntimeError(
                f"this database was written by a newer gfso (schema {found}; this build of "
                f"gfso {__version__} understands {self.SCHEMA_VERSION}). Upgrade with "
                f"`pip install -U gfso`, or point GFSO_HOME at a different directory.")
        if found != self.SCHEMA_VERSION:
            self._conn.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")

    #: (table, column, declaration) — applied in order to a database that predates each column.
    #: The comments are the canon rows the columns exist for, kept where the columns are named.
    _ADDITIVE_MIGRATIONS = (
        # what a model session read from the cache and what it wrote to it — priced apart, summed in
        # `cache_input_tokens` — its fullest turn, its model's window, its turns; NULL where not recorded
        ("llm_usage", "cache_read_tokens", "INTEGER"),
        ("llm_usage", "cache_write_tokens", "INTEGER"),
        ("llm_usage", "peak_context", "INTEGER"),
        ("llm_usage", "context_window", "INTEGER"),
        ("llm_usage", "turns", "INTEGER"),
        ("llm_usage", "resumed", "INTEGER"),                            # 1: it continued a conversation (`--resume`)
        ("llm_usage", "ended", "TEXT"),                                 # answered / cut / limit / the CLI's reason
        ("llm_usage", "handover", "INTEGER"),                           # n: this round wrote the session's n-th note
        ("dep_edges", "glue", "TEXT DEFAULT ''"),
        ("dep_edges", "provisional", "INTEGER DEFAULT 0"),
        ("dep_edges", "closed", "INTEGER DEFAULT 0"),                   # a record nobody answered (§15.5)
        ("dep_edges", "declared_first", "INTEGER DEFAULT 0"),           # declared before its first BLOCK (§15.5)
        ("dep_edges", "refuted", "INTEGER DEFAULT 0"),                  # refuted, kept for the order (§15.5)
        ("dep_edges", "removed", "INTEGER DEFAULT 0"),                  # a declaration taken out, still counted (§15.5)
        ("tasks", "verified", "INTEGER DEFAULT 0"),
        ("tasks", "reopens", "INTEGER DEFAULT 0"),                      # R′ (§12.14)
        ("tasks", "max_reopens", "INTEGER DEFAULT 1"),
        ("tasks", "reopened_from_pass", "INTEGER DEFAULT 0"),
        ("tasks", "spec_defect_criteria_change", "INTEGER DEFAULT 0"),  # §15.4 revision-reason typing
        ("tasks", "reassign_reason_typed", "INTEGER DEFAULT 0"),
        ("tasks", "reassign_capability_mismatch", "INTEGER DEFAULT 0"),
        ("tasks", "revisions", "INTEGER DEFAULT 0"),                    # contract generation (Inv-1)
        ("tasks", "state_entered_at", "TEXT"),                          # Inv-5's per-state clock
        ("tasks", "deadline_supplied", "INTEGER DEFAULT 0"),             # §2.5: the default, logged as supplied
        ("tasks", "register_json", "TEXT"),                             # §9.2: the split's register, its decomposer's
        ("check_results", "vacuous", "INTEGER DEFAULT 0"),   # a green over an EMPTY subject differs
        ("audit_log", "spec_json", "TEXT"),                  # Inv-7: the contract each ASSIGN set
        ("audit_log", "revision_reason", "TEXT"),            # §11.3: a re-ASSIGN's reason is signal data
        ("audit_log", "retire_findings_json", "TEXT"),       # §10.2: the ruling an ACCEPT_CHALLENGE makes
        ("audit_log", "artifact", "TEXT"),                   # §11.2: what a DELIVER handed over, by identity
    )

    def _init_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                spec_json TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'IDLE',
                parent_id TEXT,
                assignee TEXT,
                iteration INTEGER DEFAULT 0,
                max_iterations INTEGER,   -- no DDL default: the rule has ONE spelling,
                                          -- core.types.DEFAULT_MAX_ITERATIONS, and every insert writes it
                deadline TEXT,
                created_at TEXT NOT NULL,
                state_entered_at TEXT,
                done_reason TEXT,
                autonomy TEXT DEFAULT 'MANUAL',
                was_challenged INTEGER DEFAULT 0,
                was_reassigned INTEGER DEFAULT 0,
                false_positive INTEGER DEFAULT 0,
                criterion_mappings_json TEXT DEFAULT '[]',
                verified INTEGER DEFAULT 0,
                reopens INTEGER DEFAULT 0,
                max_reopens INTEGER DEFAULT 1,
                reopened_from_pass INTEGER DEFAULT 0,
                spec_defect_criteria_change INTEGER DEFAULT 0,
                reassign_reason_typed INTEGER DEFAULT 0,
                reassign_capability_mismatch INTEGER DEFAULT 0,
                revisions INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS check_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                check_name TEXT NOT NULL,
                passed INTEGER NOT NULL,
                details TEXT DEFAULT '',
                skipped INTEGER DEFAULT 0,
                vacuous INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS recommendations (
                task_id TEXT PRIMARY KEY,
                suggestions_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS dep_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                discovered INTEGER DEFAULT 0,
                glue TEXT DEFAULT '',
                provisional INTEGER DEFAULT 0,
                closed INTEGER DEFAULT 0,
                declared_first INTEGER DEFAULT 0,
                refuted INTEGER DEFAULT 0,
                removed INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS critiques (
                task_id TEXT PRIMARY KEY,
                critique_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS exec_verdicts (
                task_id TEXT PRIMARY KEY,
                verdict_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS deliver_results (
                task_id TEXT PRIMARY KEY,
                result TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS llm_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                stage TEXT NOT NULL,
                model TEXT DEFAULT '',
                node_id TEXT,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_input_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                duration_ms INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS pipeline_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                source TEXT NOT NULL,
                message TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                task_id TEXT NOT NULL,
                signal TEXT NOT NULL,
                old_state TEXT,
                new_state TEXT,
                effects_json TEXT DEFAULT '[]',
                rejected INTEGER DEFAULT 0,
                error TEXT,
                source TEXT,
                reason TEXT,
                justification TEXT,
                result TEXT,
                failed_criteria_json TEXT DEFAULT '[]',
                action TEXT,
                in_flight TEXT,
                spec_json TEXT,
                revision_reason TEXT,
                retire_findings_json TEXT,
                artifact TEXT
            );
        """)
        # Defensive migrations for DBs created before these columns existed. DATA, not twenty
        # near-identical statements: every one of them is the same act — "if this table lacks this
        # column, add it with this default" — and written out longhand the list is where a column
        # gets added to the CREATE above and forgotten here, which is a database that opens and then
        # fails on the first read of a field the code declares.
        for table, column, decl in self._ADDITIVE_MIGRATIONS:
            have = {r["name"] for r in self._conn.execute(f"PRAGMA table_info({table})")}
            if column not in have:
                try:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
                # another process opening the same file added it between the look and the ALTER — it is there
                except sqlite3.OperationalError as ex:
                    if "duplicate column" not in str(ex):
                        raise
                    continue
                if (table, column) == ("dep_edges", "closed"):
                    # a record an older build left open after its node left BLOCKED was never answered:
                    # closed now, or the node's NEXT block is blamed on it (critic, 2026-09-27)
                    self._conn.execute("UPDATE dep_edges SET closed = 1, provisional = 0 WHERE provisional = 1 "
                                       "AND to_id NOT IN (SELECT id FROM tasks WHERE state = 'BLOCKED')")
        self._migrate_retired_states()
        _seams_to_edges(self._conn, self._spec_from_json, self._spec_to_json, self._mappings_from_json,
                        self._mappings_to_json)

    def _migrate_retired_states(self):
        """A node stored in a state this machine no longer has is moved to the state that replaced
        it, once, here — and the move is LOGGED AS A MIGRATION, not as a signal: nobody sent one,
        and an audit row would claim a transition the protocol never made. The node enters its new
        state now, so its bound counts from the migration (a node parked in OVERDUE under the old
        machine reaches ESCALATED with the issuer's whole window ahead of it) — on the project's clocks (`project_now`)."""
        off = float((self._conn.execute("SELECT value FROM settings WHERE key = 'clock_off_s'").fetchone() or [0])[0] or 0)
        now = (datetime.now() - timedelta(seconds=off)).isoformat()
        for old, new in RETIRED_STATES.items():
            ids = [r["id"] for r in self._conn.execute("SELECT id FROM tasks WHERE state = ?", (old,))]
            if not ids:
                continue
            self._conn.execute("UPDATE tasks SET state = ?, state_entered_at = ? WHERE state = ?",
                               (new.name, now, old))
            self._conn.executemany(
                "INSERT INTO pipeline_log (ts, source, message) VALUES (?, ?, ?)",
                [(datetime.now().isoformat(sep=" ", timespec="seconds"), "migration",
                  f"{i}: stored in {old}, a state this machine no longer has — now {new.name} "
                  f"(a migration, not a signal)") for i in ids])
            log.info("migrated %d node(s) from retired state %s to %s: %s",
                     len(ids), old, new.name, ", ".join(ids))
        self._conn.commit()

    # === Serialization ===

    @staticmethod
    def _accepted_risks_to_json(items: tuple[AcceptedRiskItem, ...]) -> list[dict]:
        return [n.to_dict() for n in items]

    @staticmethod
    def _accepted_risks_from_json(raw) -> tuple[AcceptedRiskItem, ...]:
        return tuple(AcceptedRiskItem.of(n) for n in raw or ())   # a plain string is the legacy format

    @staticmethod
    def _spec_to_json(spec: Spec) -> str:
        return json.dumps({
            "description": spec.description,
            "name": spec.name,
            # FULL Criteria roundtrip — input/expected/n/timeout are contract content (a verifier
            # reads them); dropping them silently was a declared leak of the storage contract.
            "criteria": [{"name": c.name, "description": c.description, "depends_on": c.depends_on,
                          "input": c.input, "expected": c.expected, "n": c.n, "timeout": c.timeout,
                          # the pinned decision procedure travels WITH the criterion: a contract that
                          # loses its probes on the way to disk is back to a procedure invented at
                          # validation time, which is the defect the field exists against
                          "check": [p.to_dict() for p in (c.check or ())],
                          # …and so does the composition function CHECK-7 checks under (§9.6): a
                          # declaration lost on the way to disk puts the check back on its assumed sum
                          "composition": c.composition}
                         for c in spec.criteria],
            "accepted_risks": SqliteStorage._accepted_risks_to_json(spec.accepted_risks),
            "risk_components": list(spec.risk_components),
            "covers_risks": list(spec.covers_risks),
            "scope": list(spec.scope),
        })

    @staticmethod
    def _spec_from_json(raw: str) -> Spec:
        d = json.loads(raw)
        return Spec(
            description=d["description"],
            criteria=tuple(Criteria(c["name"], c["description"], depends_on=c.get("depends_on"),
                                    input=c.get("input"), expected=c.get("expected"),
                                    n=c.get("n"), timeout=c.get("timeout"),
                                    check=tuple(Probe.of(p) for p in (c.get("check") or ())),
                                    composition=c.get("composition", ""))
                           for c in d["criteria"]),
            accepted_risks=SqliteStorage._accepted_risks_from_json(d.get("accepted_risks", ())),
            risk_components=tuple(d.get("risk_components", ())),
            scope=tuple(d.get("scope", ())),
            name=d.get("name", ""),
            covers_risks=tuple(d.get("covers_risks", ())),
        )

    @staticmethod
    def _mappings_to_json(mappings: tuple[CriterionMapping, ...]) -> str:
        return json.dumps([{"criterion_name": m.criterion_name, "child_id": m.child_id} for m in mappings])

    @staticmethod
    def _mappings_from_json(raw: str) -> tuple[CriterionMapping, ...]:
        return tuple(CriterionMapping(m["criterion_name"], TaskId(m["child_id"])) for m in json.loads(raw))

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        state, done_reason = _state_of(row)
        t = Task(
            id=TaskId(row["id"]),
            spec=self._spec_from_json(row["spec_json"]),
            state=state,
            parent_id=TaskId(row["parent_id"]) if row["parent_id"] else None,
            assignee=AgentId(row["assignee"]) if row["assignee"] else None,
            iteration=row["iteration"],
            max_iterations=row["max_iterations"],
            deadline=datetime.fromisoformat(row["deadline"]) if row["deadline"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            done_reason=done_reason,
            autonomy=AutonomyLevel[row["autonomy"]],
        )
        # Inv-5's per-state clock, RESTORED rather than restarted. It is set on every transition
        # (`core/graph/mutations.py`) and was stored nowhere, so `default_factory=datetime.now` gave
        # every node the moment of HYDRATION: after a restart the whole graph claimed to have just
        # entered its state. Two things ride on that and both were wrong. Inv-5's state age reset to
        # zero on every restart; and the rework gate compares `child.state_entered_at <=
        # task.state_entered_at` to decide whether a coverer was touched since the FAIL — with all
        # values equal that comparison decides by load order, and an agent watched a freshly added
        # child that had PASSED be called "untouched" (2026-08-20).
        # A row written before this column exists carries NULL: fall back to `created_at`, which is
        # wrong in magnitude but right in the property that matters — it is FIXED, so it neither
        # moves with the process nor collapses the ordering between nodes.
        _sea = row["state_entered_at"] if "state_entered_at" in row.keys() else None
        t.state_entered_at = datetime.fromisoformat(_sea) if _sea else t.created_at
        t.deadline_supplied = bool(row["deadline_supplied"]) if "deadline_supplied" in row.keys() else False
        _reg = json.loads(row["register_json"]) if "register_json" in row.keys() and row["register_json"] else None
        t.register = (Register(self._accepted_risks_from_json(_reg.get("items", ())), tuple(_reg.get("components", ())))
                      if _reg is not None else None)
        t.was_challenged = bool(row["was_challenged"])
        t.was_reassigned = bool(row["was_reassigned"])
        t.false_positive = bool(row["false_positive"])
        t.criterion_mappings = self._mappings_from_json(row["criterion_mappings_json"])
        t.verified = bool(row["verified"])
        t.reopens = row["reopens"]
        t.max_reopens = row["max_reopens"]
        t.reopened_from_pass = bool(row["reopened_from_pass"])
        t.spec_defect_criteria_change = bool(row["spec_defect_criteria_change"])
        t.reassign_reason_typed = bool(row["reassign_reason_typed"])
        t.reassign_capability_mismatch = bool(row["reassign_capability_mismatch"])
        t.revisions = row["revisions"] if "revisions" in row.keys() else 0
        return t

    # === StoragePort ===

    def get_task(self, task_id: TaskId) -> Optional[Task]:
        with self._read() as c:
            row = c.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._row_to_task(row) if row else None

    def save_task(self, task: Task) -> None:
        with self._write() as c:
            c.execute(
                """INSERT OR REPLACE INTO tasks
               (id, spec_json, state, parent_id, assignee, iteration, max_iterations,
                deadline, created_at, state_entered_at, done_reason, autonomy,
                was_challenged, was_reassigned, false_positive, criterion_mappings_json, verified,
                reopens, max_reopens, reopened_from_pass,
                spec_defect_criteria_change, reassign_reason_typed, reassign_capability_mismatch,
                revisions, deadline_supplied, register_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.id,
                    self._spec_to_json(task.spec),
                    task.state.name,
                    task.parent_id,
                    task.assignee,
                    task.iteration,
                    task.max_iterations,
                    task.deadline.isoformat() if task.deadline else None,
                    task.created_at.isoformat(),
                    task.state_entered_at.isoformat() if task.state_entered_at else None,
                    task.done_reason.name if task.done_reason else None,
                    task.autonomy.name,
                    int(task.was_challenged),
                    int(task.was_reassigned),
                    int(task.false_positive),
                    self._mappings_to_json(task.criterion_mappings),
                    int(task.verified),
                    task.reopens,
                    task.max_reopens,
                    int(task.reopened_from_pass),
                    int(task.spec_defect_criteria_change),
                    int(task.reassign_reason_typed),
                    int(task.reassign_capability_mismatch),
                    int(task.revisions),
                    int(task.deadline_supplied),
                    json.dumps({"items": self._accepted_risks_to_json(task.register.items),
                                "components": list(task.register.components)}) if task.register is not None else None,
                ),
            )

    def get_all_tasks(self) -> list[Task]:
        with self._read() as c:
            rows = c.execute("SELECT * FROM tasks").fetchall()
        return [self._row_to_task(r) for r in rows]

    def get_children(self, task_id: TaskId) -> list[Task]:
        with self._read() as c:
            rows = c.execute("SELECT * FROM tasks WHERE parent_id = ?", (task_id,)).fetchall()
        return [self._row_to_task(r) for r in rows]

    def get_parent(self, task_id: TaskId) -> Optional[Task]:
        with self._read() as c:
            row = c.execute("SELECT parent_id FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row and row["parent_id"]:
            return self.get_task(TaskId(row["parent_id"]))
        return None

    def get_active_tasks(self) -> list[Task]:
        terminal = tuple(s.name for s in TERMINAL_STATES)
        placeholders = ",".join("?" * len(terminal))
        with self._read() as c:
            rows = c.execute(
                f"SELECT * FROM tasks WHERE state NOT IN ({placeholders})", terminal
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def get_check_results(self, task_id: TaskId) -> list[CheckResult]:
        with self._read() as c:
            rows = c.execute(
                "SELECT * FROM check_results WHERE task_id = ?", (task_id,)
            ).fetchall()
        # `vacuous` rides the round trip: dropping it here would have made the distinction true in
        # memory and false a moment later, which is the "one field, two doors" defect in miniature.
        return [CheckResult(r["check_name"], bool(r["passed"]), r["details"], bool(r["skipped"]),
                            bool(r["vacuous"])) for r in rows]

    def store_check_results(self, task_id: TaskId, results: list[CheckResult]) -> None:
        # DELETE + INSERT is ONE mutation: a reader landing between them sees a node whose checks
        # are an empty set, and a neighbouring thread's commit between them used to PUBLISH exactly
        # that. `_write` is what makes the pair atomic.
        with self._write() as c:
            c.execute("DELETE FROM check_results WHERE task_id = ?", (task_id,))
            c.executemany(
                "INSERT INTO check_results (task_id, check_name, passed, details, skipped, vacuous) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(task_id, r.check_name, int(r.passed), r.details, int(r.skipped), int(r.vacuous))
                 for r in results],
            )

    def get_recommendation(self, task_id: TaskId) -> Optional[Recommendation]:
        with self._read() as c:
            row = c.execute("SELECT * FROM recommendations WHERE task_id = ?", (task_id,)).fetchone()
        if row:
            return Recommendation(suggestions=tuple(json.loads(row["suggestions_json"])))
        return None

    def store_recommendation(self, task_id: TaskId, rec: Recommendation) -> None:
        with self._write() as c:
            c.execute(
                "INSERT OR REPLACE INTO recommendations (task_id, suggestions_json) VALUES (?, ?)",
                (task_id, json.dumps(list(rec.suggestions))),
            )

    def add_dep_edge(self, edge: DepEdge) -> None:
        with self._write() as c:
            c.execute(_INSERT_EDGE, _edge_row(edge))

    def remove_dep_edge(self, edge: DepEdge) -> None:
        with self._write() as c:
            c.execute(f"DELETE FROM dep_edges WHERE id = (SELECT id FROM dep_edges WHERE "
                      f"{' AND '.join(f'{k} = ?' for k in _EDGE_FIELDS)} LIMIT 1)", _edge_row(edge))

    def get_dep_edges(self) -> list[DepEdge]:
        with self._read() as c:
            return [DepEdge(TaskId(r["from_id"]), TaskId(r["to_id"]), bool(r["discovered"]), r["glue"] or "",
                            *(bool(r[k]) for k in _EDGE_FIELDS[4:]))
                    for r in c.execute("SELECT * FROM dep_edges ORDER BY id").fetchall()]

    def store_critique(self, task_id: TaskId, critique_json: str) -> None:
        with self._write() as c:
            c.execute(
                "INSERT OR REPLACE INTO critiques (task_id, critique_json) VALUES (?, ?)",
                (task_id, critique_json),
            )

    def get_critique(self, task_id: TaskId) -> Optional[str]:
        with self._read() as c:
            row = c.execute("SELECT critique_json FROM critiques WHERE task_id = ?", (task_id,)).fetchone()
        return row["critique_json"] if row else None

    def store_deliver_result(self, task_id: TaskId, result: str) -> None:
        with self._write() as c:
            c.execute(
                "INSERT OR REPLACE INTO deliver_results (task_id, result) VALUES (?, ?)",
                (task_id, result))

    def get_deliver_result(self, task_id: TaskId) -> Optional[str]:
        with self._read() as c:
            row = c.execute(
                "SELECT result FROM deliver_results WHERE task_id = ?", (task_id,)).fetchone()
        return row["result"] if row else None

    def store_exec_verdict(self, task_id: TaskId, verdict_json: str) -> None:
        with self._write() as c:
            c.execute(
                "INSERT OR REPLACE INTO exec_verdicts (task_id, verdict_json) VALUES (?, ?)",
                (task_id, verdict_json))

    def get_exec_verdict(self, task_id: TaskId) -> Optional[str]:
        with self._read() as c:
            row = c.execute(
                "SELECT verdict_json FROM exec_verdicts WHERE task_id = ?", (task_id,)).fetchone()
        return row["verdict_json"] if row else None

    def log_pipeline(self, ts: str, source: str, message: str) -> None:
        with self._write() as c:
            c.execute(
                "INSERT INTO pipeline_log (ts, source, message) VALUES (?, ?, ?)", (ts, source, message))
            # pragmatic cap (designs §6): keep the last 10k rows — one indexed delete, cheap per insert
            c.execute(
                "DELETE FROM pipeline_log WHERE id <= (SELECT MAX(id) FROM pipeline_log) - 10000")

    def get_pipeline(self, limit: int = PIPELINE_PAGE) -> list[dict]:
        with self._read() as c:
            rows = c.execute(
                "SELECT ts, source, message FROM "
                "(SELECT * FROM pipeline_log ORDER BY id DESC LIMIT ?) ORDER BY id ASC", (limit,)).fetchall()
        return [{"ts": r["ts"], "source": r["source"], "message": r["message"]} for r in rows]

    _USAGE_COLS = ("ts", "stage", "model", "node_id", "input_tokens", "output_tokens",
                   "cache_input_tokens", "cost_usd", "duration_ms",
                   "cache_read_tokens", "cache_write_tokens", "peak_context", "context_window", "turns", "ended", "resumed",
                   "handover")
    # an absent reading stays absent — tokens and price too: a provider that does not report them spent an unknown
    # amount, and a 0 read as "spent nothing". Only the duration, which our own adapter measures, is always there.
    _USAGE_KEPT_NULL = ("ts", "stage", "model", "node_id", "input_tokens", "output_tokens", "cache_input_tokens", "cost_usd",
                        "cache_read_tokens", "cache_write_tokens", "peak_context", "context_window", "turns", "ended", "resumed",
                        "handover")

    def log_usage(self, row: dict) -> None:
        with self._write() as conn:
            conn.execute(
                f"INSERT INTO llm_usage ({', '.join(self._USAGE_COLS)}) "
                f"VALUES ({', '.join('?' * len(self._USAGE_COLS))})",
                tuple(row.get(c) if c in self._USAGE_KEPT_NULL else (row.get(c) or 0)
                      for c in self._USAGE_COLS))

    def get_usage(self, limit: int = USAGE_PAGE) -> list[dict]:
        with self._read() as conn:
            rows = conn.execute(
                f"SELECT {', '.join(self._USAGE_COLS)} FROM "
                f"(SELECT * FROM llm_usage ORDER BY id DESC LIMIT ?) ORDER BY id ASC", (limit,)).fetchall()
        return [{c: r[c] for c in self._USAGE_COLS} for r in rows]

    # === Audit log (Thm 11/Inv-7): APPEND-ONLY — insert + full ordered read, no update/delete path ===

    def append_audit(self, row: dict) -> None:
        with self._write() as c:
            c.execute(
                "INSERT INTO audit_log (ts, task_id, signal, old_state, new_state, effects_json, "
                "rejected, error, source, reason, justification, result, failed_criteria_json, "
                "action, in_flight, spec_json, revision_reason, retire_findings_json, artifact) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (row["ts"], row["task_id"], row["signal"], row.get("old_state"), row.get("new_state"),
                 json.dumps(row.get("effects") or []), int(bool(row.get("rejected"))), row.get("error"),
                 row.get("source"), row.get("reason"), row.get("justification"), row.get("result"),
                 json.dumps(row.get("failed_criteria") or []), row.get("action"), row.get("in_flight"),
                 row.get("spec"), row.get("revision_reason"), json.dumps(row.get("retire_findings") or []),
                 row.get("artifact")))

    def load_audit(self) -> list[dict]:
        with self._read() as c:
            rows = c.execute("SELECT * FROM audit_log ORDER BY id ASC").fetchall()
        return [{
            "ts": r["ts"], "task_id": r["task_id"], "signal": r["signal"],
            "old_state": r["old_state"], "new_state": r["new_state"],
            "effects": json.loads(r["effects_json"] or "[]"), "rejected": bool(r["rejected"]),
            "error": r["error"], "source": r["source"], "reason": r["reason"],
            "justification": r["justification"], "result": r["result"],
            "failed_criteria": json.loads(r["failed_criteria_json"] or "[]"),
            "action": r["action"], "in_flight": r["in_flight"],
            "spec": (r["spec_json"] if "spec_json" in r.keys() else None),
            "revision_reason": r["revision_reason"],
            "retire_findings": json.loads(r["retire_findings_json"] or "[]") if "retire_findings_json" in r.keys() else [],
            "artifact": r["artifact"] if "artifact" in r.keys() else None,
        } for r in rows]
