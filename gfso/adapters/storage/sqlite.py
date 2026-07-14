"""SQLite StoragePort — persistent storage."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Optional

from gfso.core.types import (
    TaskId, AgentId, Task, State, DoneReason, AutonomyLevel, Predictability,
    Spec, Criteria, CriterionMapping, NeglectedItem,
    CheckResult, Recommendation, DepEdge,
    StoragePort, TERMINAL_STATES,
)


class SqliteStorage(StoragePort):
    def __init__(self, db_path: str = "data/gfso.db"):
        if db_path != ":memory:":
            from pathlib import Path
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._init_tables()

    def close(self) -> None:
        """Release the file handle (Windows keeps the .db locked until the connection closes —
        project deletion depends on this)."""
        self._conn.close()

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
                reassign_capability_mismatch INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS check_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                check_name TEXT NOT NULL,
                passed INTEGER NOT NULL,
                details TEXT DEFAULT '',
                skipped INTEGER DEFAULT 0
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
                in_flight TEXT
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
        if "reopens" not in task_cols:  # R′ (§6.3)
            self._conn.execute("ALTER TABLE tasks ADD COLUMN reopens INTEGER DEFAULT 0")
            self._conn.execute("ALTER TABLE tasks ADD COLUMN max_reopens INTEGER DEFAULT 1")
            self._conn.execute("ALTER TABLE tasks ADD COLUMN reopened_from_pass INTEGER DEFAULT 0")
        if "spec_defect_criteria_change" not in task_cols:  # §16.5 revision-reason typing
            self._conn.execute("ALTER TABLE tasks ADD COLUMN spec_defect_criteria_change INTEGER DEFAULT 0")
            self._conn.execute("ALTER TABLE tasks ADD COLUMN reassign_reason_typed INTEGER DEFAULT 0")
            self._conn.execute("ALTER TABLE tasks ADD COLUMN reassign_capability_mismatch INTEGER DEFAULT 0")

    # === Serialization ===

    @staticmethod
    def _neglected_to_json(items: tuple[NeglectedItem, ...]) -> list[dict]:
        return [{
            "item": n.item,
            "predictability": n.predictability.name if n.predictability else None,
            "justification": n.justification,
            "invalidation_condition": n.invalidation_condition,
        } for n in items]

    @staticmethod
    def _neglected_from_json(raw) -> tuple[NeglectedItem, ...]:
        out = []
        for n in raw or ():
            if isinstance(n, str):  # legacy plain-string format
                out.append(NeglectedItem(n))
            else:
                p = n.get("predictability")
                out.append(NeglectedItem(
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
            "neglected": SqliteStorage._neglected_to_json(spec.neglected),
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
            neglected=SqliteStorage._neglected_from_json(d.get("neglected", ())),
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
        # gives it its own terminal state (§6.3). Map on read — no new writes produce the legacy form.
        state = State[row["state"]]
        done_reason = DoneReason[row["done_reason"]] if row["done_reason"] else None
        if state == State.DONE and done_reason == DoneReason.CANCELLED:
            state, done_reason = State.CANCELLED, None
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
        return t

    # === StoragePort ===

    def get_task(self, task_id: TaskId) -> Optional[Task]:
        row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._row_to_task(row) if row else None

    def save_task(self, task: Task) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO tasks
               (id, spec_json, state, parent_id, assignee, iteration, max_iterations,
                deadline, created_at, done_reason, autonomy,
                was_challenged, was_reassigned, false_positive, criterion_mappings_json, verified,
                reopens, max_reopens, reopened_from_pass,
                spec_defect_criteria_change, reassign_reason_typed, reassign_capability_mismatch)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
        return [CheckResult(r["check_name"], bool(r["passed"]), r["details"], bool(r["skipped"])) for r in rows]

    def store_check_results(self, task_id: TaskId, results: list[CheckResult]) -> None:
        self._conn.execute("DELETE FROM check_results WHERE task_id = ?", (task_id,))
        self._conn.executemany(
            "INSERT INTO check_results (task_id, check_name, passed, details, skipped) VALUES (?, ?, ?, ?, ?)",
            [(task_id, r.check_name, int(r.passed), r.details, int(r.skipped)) for r in results],
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

    def get_pipeline(self, limit: int = 500) -> list[dict]:
        rows = self._conn.execute(
            "SELECT ts, source, message FROM "
            "(SELECT * FROM pipeline_log ORDER BY id DESC LIMIT ?) ORDER BY id ASC", (limit,)).fetchall()
        return [{"ts": r["ts"], "source": r["source"], "message": r["message"]} for r in rows]

    # === Audit log (T11/Инв-7): APPEND-ONLY — insert + full ordered read, no update/delete path ===

    def append_audit(self, row: dict) -> None:
        self._conn.execute(
            "INSERT INTO audit_log (ts, task_id, signal, old_state, new_state, effects_json, "
            "rejected, error, source, reason, justification, result, failed_criteria_json, "
            "action, in_flight) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (row["ts"], row["task_id"], row["signal"], row.get("old_state"), row.get("new_state"),
             json.dumps(row.get("effects") or []), int(bool(row.get("rejected"))), row.get("error"),
             row.get("source"), row.get("reason"), row.get("justification"), row.get("result"),
             json.dumps(row.get("failed_criteria") or []), row.get("action"), row.get("in_flight")))
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
        } for r in rows]
