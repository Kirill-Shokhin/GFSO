"""SQLite StoragePort — persistent storage."""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from gfso import __version__

from gfso.core.types import (
    TaskId, AgentId, Task, State, DoneReason, AutonomyLevel, Predictability,
    Spec, Criteria, CriterionMapping, AcceptedRiskItem,
    CheckResult, Recommendation, DepEdge,
    StoragePort, TERMINAL_STATES,
)
from gfso.config import PIPELINE_PAGE, USAGE_PAGE

log = logging.getLogger(__name__)


class SqliteStorage(StoragePort):
    def __init__(self, db_path: str = "data/gfso.db"):
        self._db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._check_schema_version()
        self._init_tables()

    def close(self) -> None:
        """Release the file handle (Windows keeps the .db locked until the connection closes —
        project deletion depends on this)."""
        self._conn.close()

    # The schema this build of gfso writes. Bumped only when a change is not additive — the
    # migrations below handle additive ones by inspecting `PRAGMA table_info`.
    SCHEMA_VERSION = 1

    # The v4.0 rename migration (2026-08-13) used `PRAGMA user_version = 40` as its "already
    # migrated" mark, before this field carried a schema version at all. Recognised, never written.
    _V4_MIGRATION_MARK = 40

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

    def _init_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                spec_json TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'IDLE',
                parent_id TEXT,
                assignee TEXT,
                iteration INTEGER DEFAULT 0,
                max_iterations INTEGER DEFAULT 3,
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
                provisional INTEGER DEFAULT 0
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
                spec_json TEXT
            );
        """)
        # Defensive migrations for DBs created before these columns existed.
        dep_cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(dep_edges)")}
        if "glue" not in dep_cols:
            self._conn.execute("ALTER TABLE dep_edges ADD COLUMN glue TEXT DEFAULT ''")
        if "provisional" not in dep_cols:
            self._conn.execute("ALTER TABLE dep_edges ADD COLUMN provisional INTEGER DEFAULT 0")
        task_cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(tasks)")}
        if "verified" not in task_cols:
            self._conn.execute("ALTER TABLE tasks ADD COLUMN verified INTEGER DEFAULT 0")
        if "reopens" not in task_cols:  # R′ (§14.3)
            self._conn.execute("ALTER TABLE tasks ADD COLUMN reopens INTEGER DEFAULT 0")
            self._conn.execute("ALTER TABLE tasks ADD COLUMN max_reopens INTEGER DEFAULT 1")
            self._conn.execute("ALTER TABLE tasks ADD COLUMN reopened_from_pass INTEGER DEFAULT 0")
        if "spec_defect_criteria_change" not in task_cols:  # §24.5 revision-reason typing
            self._conn.execute("ALTER TABLE tasks ADD COLUMN spec_defect_criteria_change INTEGER DEFAULT 0")
            self._conn.execute("ALTER TABLE tasks ADD COLUMN reassign_reason_typed INTEGER DEFAULT 0")
            self._conn.execute("ALTER TABLE tasks ADD COLUMN reassign_capability_mismatch INTEGER DEFAULT 0")
        if "revisions" not in task_cols:   # contract generation (Inv-1 revisions)
            self._conn.execute("ALTER TABLE tasks ADD COLUMN revisions INTEGER DEFAULT 0")
        if "state_entered_at" not in task_cols:   # Inv-5's per-state clock (see save/load below)
            self._conn.execute("ALTER TABLE tasks ADD COLUMN state_entered_at TEXT")
        check_cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(check_results)")}
        if "vacuous" not in check_cols:   # a green over an EMPTY subject is not the same green
            self._conn.execute("ALTER TABLE check_results ADD COLUMN vacuous INTEGER DEFAULT 0")
        audit_cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(audit_log)")}
        if "spec_json" not in audit_cols:   # Inv-7: the contract each ASSIGN installed
            self._conn.execute("ALTER TABLE audit_log ADD COLUMN spec_json TEXT")

    # === Serialization ===

    @staticmethod
    def _accepted_risks_to_json(items: tuple[AcceptedRiskItem, ...]) -> list[dict]:
        return [{
            "item": n.item,
            "predictability": n.predictability.name if n.predictability else None,
            "justification": n.justification,
            "invalidation_condition": n.invalidation_condition,
        } for n in items]

    @staticmethod
    def _accepted_risks_from_json(raw) -> tuple[AcceptedRiskItem, ...]:
        out = []
        for n in raw or ():
            if isinstance(n, str):  # legacy plain-string format
                out.append(AcceptedRiskItem(n))
            else:
                p = n.get("predictability")
                out.append(AcceptedRiskItem(
                    n["item"],
                    Predictability[p] if p else None,
                    n.get("justification", ""),
                    n.get("invalidation_condition", ""),
                ))
        return tuple(out)

    @staticmethod
    def _spec_to_json(spec: Spec) -> str:
        return json.dumps({
            "description": spec.description,
            "name": spec.name,
            # FULL Criteria roundtrip — input/expected/n/timeout are contract content (a verifier
            # reads them); dropping them silently was a declared leak of the storage contract.
            "criteria": [{"name": c.name, "description": c.description, "depends_on": c.depends_on,
                          "input": c.input, "expected": c.expected, "n": c.n, "timeout": c.timeout}
                         for c in spec.criteria],
            "accepted_risks": SqliteStorage._accepted_risks_to_json(spec.accepted_risks),
            "risk_components": list(spec.risk_components),
            "scope": list(spec.scope),
        })

    @staticmethod
    def _spec_from_json(raw: str) -> Spec:
        d = json.loads(raw)
        return Spec(
            description=d["description"],
            criteria=tuple(Criteria(c["name"], c["description"], depends_on=c.get("depends_on"),
                                    input=c.get("input"), expected=c.get("expected"),
                                    n=c.get("n"), timeout=c.get("timeout"))
                           for c in d["criteria"]),
            accepted_risks=SqliteStorage._accepted_risks_from_json(d.get("accepted_risks", ())),
            risk_components=tuple(d.get("risk_components", ())),
            scope=tuple(d.get("scope", ())),
            name=d.get("name", ""),
        )

    @staticmethod
    def _mappings_to_json(mappings: tuple[CriterionMapping, ...]) -> str:
        return json.dumps([{"criterion_name": m.criterion_name, "child_id": m.child_id} for m in mappings])

    @staticmethod
    def _mappings_from_json(raw: str) -> tuple[CriterionMapping, ...]:
        return tuple(CriterionMapping(m["criterion_name"], TaskId(m["child_id"])) for m in json.loads(raw))

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        # Read-side migration: pre-v3.7 DBs stored cancellation as DONE(reason=CANCELLED); canon v3.7
        # gives it its own terminal state (§14.3). Map on read — no new writes produce the legacy form.
        state = State[row["state"]]
        done_reason = DoneReason[row["done_reason"]] if row["done_reason"] else None
        if state == State.DONE and done_reason == DoneReason.CANCELLED:
            state, done_reason = State.ABANDONED, None
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
        row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._row_to_task(row) if row else None

    def save_task(self, task: Task) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO tasks
               (id, spec_json, state, parent_id, assignee, iteration, max_iterations,
                deadline, created_at, state_entered_at, done_reason, autonomy,
                was_challenged, was_reassigned, false_positive, criterion_mappings_json, verified,
                reopens, max_reopens, reopened_from_pass,
                spec_defect_criteria_change, reassign_reason_typed, reassign_capability_mismatch,
                revisions)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            ),
        )
        self._conn.commit()

    def get_all_tasks(self) -> list[Task]:
        rows = self._conn.execute("SELECT * FROM tasks").fetchall()
        return [self._row_to_task(r) for r in rows]

    def get_children(self, task_id: TaskId) -> list[Task]:
        rows = self._conn.execute("SELECT * FROM tasks WHERE parent_id = ?", (task_id,)).fetchall()
        return [self._row_to_task(r) for r in rows]

    def get_parent(self, task_id: TaskId) -> Optional[Task]:
        row = self._conn.execute("SELECT parent_id FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row and row["parent_id"]:
            return self.get_task(TaskId(row["parent_id"]))
        return None

    def get_active_tasks(self) -> list[Task]:
        terminal = tuple(s.name for s in TERMINAL_STATES)
        placeholders = ",".join("?" * len(terminal))
        rows = self._conn.execute(
            f"SELECT * FROM tasks WHERE state NOT IN ({placeholders})", terminal
        ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def get_check_results(self, task_id: TaskId) -> list[CheckResult]:
        rows = self._conn.execute(
            "SELECT * FROM check_results WHERE task_id = ?", (task_id,)
        ).fetchall()
        # `vacuous` rides the round trip: dropping it here would have made the distinction true in
        # memory and false a moment later, which is the "one field, two doors" defect in miniature.
        return [CheckResult(r["check_name"], bool(r["passed"]), r["details"], bool(r["skipped"]),
                            bool(r["vacuous"])) for r in rows]

    def store_check_results(self, task_id: TaskId, results: list[CheckResult]) -> None:
        self._conn.execute("DELETE FROM check_results WHERE task_id = ?", (task_id,))
        self._conn.executemany(
            "INSERT INTO check_results (task_id, check_name, passed, details, skipped, vacuous) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(task_id, r.check_name, int(r.passed), r.details, int(r.skipped), int(r.vacuous))
             for r in results],
        )
        self._conn.commit()

    def get_recommendation(self, task_id: TaskId) -> Optional[Recommendation]:
        row = self._conn.execute("SELECT * FROM recommendations WHERE task_id = ?", (task_id,)).fetchone()
        if row:
            return Recommendation(suggestions=tuple(json.loads(row["suggestions_json"])))
        return None

    def store_recommendation(self, task_id: TaskId, rec: Recommendation) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO recommendations (task_id, suggestions_json) VALUES (?, ?)",
            (task_id, json.dumps(list(rec.suggestions))),
        )
        self._conn.commit()

    def add_dep_edge(self, edge: DepEdge) -> None:
        self._conn.execute(
            "INSERT INTO dep_edges (from_id, to_id, discovered, glue, provisional) VALUES (?, ?, ?, ?, ?)",
            (edge.from_id, edge.to_id, int(edge.discovered), edge.glue, int(edge.provisional)),
        )
        self._conn.commit()

    def remove_dep_edge(self, from_id: TaskId, to_id: TaskId) -> None:
        self._conn.execute(
            "DELETE FROM dep_edges WHERE from_id = ? AND to_id = ?", (from_id, to_id)
        )
        self._conn.commit()

    def get_dep_edges(self) -> list[DepEdge]:
        rows = self._conn.execute("SELECT * FROM dep_edges").fetchall()
        return [DepEdge(TaskId(r["from_id"]), TaskId(r["to_id"]), bool(r["discovered"]),
                        r["glue"] or "", bool(r["provisional"])) for r in rows]

    def store_critique(self, task_id: TaskId, critique_json: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO critiques (task_id, critique_json) VALUES (?, ?)",
            (task_id, critique_json),
        )
        self._conn.commit()

    def get_critique(self, task_id: TaskId) -> Optional[str]:
        row = self._conn.execute("SELECT critique_json FROM critiques WHERE task_id = ?", (task_id,)).fetchone()
        return row["critique_json"] if row else None

    def store_deliver_result(self, task_id: TaskId, result: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO deliver_results (task_id, result) VALUES (?, ?)",
            (task_id, result))
        self._conn.commit()

    def get_deliver_result(self, task_id: TaskId) -> Optional[str]:
        row = self._conn.execute(
            "SELECT result FROM deliver_results WHERE task_id = ?", (task_id,)).fetchone()
        return row["result"] if row else None

    def store_exec_verdict(self, task_id: TaskId, verdict_json: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO exec_verdicts (task_id, verdict_json) VALUES (?, ?)",
            (task_id, verdict_json))
        self._conn.commit()

    def get_exec_verdict(self, task_id: TaskId) -> Optional[str]:
        row = self._conn.execute(
            "SELECT verdict_json FROM exec_verdicts WHERE task_id = ?", (task_id,)).fetchone()
        return row["verdict_json"] if row else None

    def log_pipeline(self, ts: str, source: str, message: str) -> None:
        self._conn.execute(
            "INSERT INTO pipeline_log (ts, source, message) VALUES (?, ?, ?)", (ts, source, message))
        # pragmatic cap (designs §6): keep the last 10k rows — one indexed delete, cheap per insert
        self._conn.execute(
            "DELETE FROM pipeline_log WHERE id <= (SELECT MAX(id) FROM pipeline_log) - 10000")
        self._conn.commit()

    def get_pipeline(self, limit: int = PIPELINE_PAGE) -> list[dict]:
        rows = self._conn.execute(
            "SELECT ts, source, message FROM "
            "(SELECT * FROM pipeline_log ORDER BY id DESC LIMIT ?) ORDER BY id ASC", (limit,)).fetchall()
        return [{"ts": r["ts"], "source": r["source"], "message": r["message"]} for r in rows]

    _USAGE_COLS = ("ts", "stage", "model", "node_id", "input_tokens", "output_tokens",
                   "cache_input_tokens", "cost_usd", "duration_ms")

    def log_usage(self, row: dict) -> None:
        self._conn.execute(
            f"INSERT INTO llm_usage ({', '.join(self._USAGE_COLS)}) "
            f"VALUES ({', '.join('?' * len(self._USAGE_COLS))})",
            tuple(row.get(c) if c in ("ts", "stage", "model", "node_id") else (row.get(c) or 0)
                  for c in self._USAGE_COLS))
        self._conn.commit()

    def get_usage(self, limit: int = USAGE_PAGE) -> list[dict]:
        rows = self._conn.execute(
            f"SELECT {', '.join(self._USAGE_COLS)} FROM "
            f"(SELECT * FROM llm_usage ORDER BY id DESC LIMIT ?) ORDER BY id ASC", (limit,)).fetchall()
        return [{c: r[c] for c in self._USAGE_COLS} for r in rows]

    # === Audit log (Thm 11/Inv-7): APPEND-ONLY — insert + full ordered read, no update/delete path ===

    def append_audit(self, row: dict) -> None:
        self._conn.execute(
            "INSERT INTO audit_log (ts, task_id, signal, old_state, new_state, effects_json, "
            "rejected, error, source, reason, justification, result, failed_criteria_json, "
            "action, in_flight, spec_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (row["ts"], row["task_id"], row["signal"], row.get("old_state"), row.get("new_state"),
             json.dumps(row.get("effects") or []), int(bool(row.get("rejected"))), row.get("error"),
             row.get("source"), row.get("reason"), row.get("justification"), row.get("result"),
             json.dumps(row.get("failed_criteria") or []), row.get("action"), row.get("in_flight"),
             row.get("spec")))
        self._conn.commit()

    def load_audit(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM audit_log ORDER BY id ASC").fetchall()
        return [{
            "ts": r["ts"], "task_id": r["task_id"], "signal": r["signal"],
            "old_state": r["old_state"], "new_state": r["new_state"],
            "effects": json.loads(r["effects_json"] or "[]"), "rejected": bool(r["rejected"]),
            "error": r["error"], "source": r["source"], "reason": r["reason"],
            "justification": r["justification"], "result": r["result"],
            "failed_criteria": json.loads(r["failed_criteria_json"] or "[]"),
            "action": r["action"], "in_flight": r["in_flight"],
            "spec": (r["spec_json"] if "spec_json" in r.keys() else None),
        } for r in rows]
