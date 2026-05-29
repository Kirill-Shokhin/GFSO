"""SQLite StoragePort — persistent storage."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Optional

from gfso.core.types import (
    TaskId, AgentId, Task, State, DoneReason, AutonomyLevel,
    Spec, Criteria, CriterionMapping,
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
                criterion_mappings_json TEXT DEFAULT '[]'
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
                discovered INTEGER DEFAULT 0
            );
        """)

    # === Serialization ===

    @staticmethod
    def _spec_to_json(spec: Spec) -> str:
        return json.dumps({
            "description": spec.description,
            "criteria": [{"name": c.name, "description": c.description} for c in spec.criteria],
            "neglected": list(spec.neglected),
            "risk_components": list(spec.risk_components),
        })

    @staticmethod
    def _spec_from_json(raw: str) -> Spec:
        d = json.loads(raw)
        return Spec(
            description=d["description"],
            criteria=tuple(Criteria(c["name"], c["description"]) for c in d["criteria"]),
            neglected=tuple(d.get("neglected", ())),
            risk_components=tuple(d.get("risk_components", ())),
        )

    @staticmethod
    def _mappings_to_json(mappings: tuple[CriterionMapping, ...]) -> str:
        return json.dumps([{"criterion_name": m.criterion_name, "child_id": m.child_id} for m in mappings])

    @staticmethod
    def _mappings_from_json(raw: str) -> tuple[CriterionMapping, ...]:
        return tuple(CriterionMapping(m["criterion_name"], TaskId(m["child_id"])) for m in json.loads(raw))

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        t = Task(
            id=TaskId(row["id"]),
            spec=self._spec_from_json(row["spec_json"]),
            state=State[row["state"]],
            parent_id=TaskId(row["parent_id"]) if row["parent_id"] else None,
            assignee=AgentId(row["assignee"]) if row["assignee"] else None,
            iteration=row["iteration"],
            max_iterations=row["max_iterations"],
            deadline=datetime.fromisoformat(row["deadline"]) if row["deadline"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            done_reason=DoneReason[row["done_reason"]] if row["done_reason"] else None,
            autonomy=AutonomyLevel[row["autonomy"]],
        )
        t.was_challenged = bool(row["was_challenged"])
        t.was_reassigned = bool(row["was_reassigned"])
        t.false_positive = bool(row["false_positive"])
        t.criterion_mappings = self._mappings_from_json(row["criterion_mappings_json"])
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
                was_challenged, was_reassigned, false_positive, criterion_mappings_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
            "INSERT INTO dep_edges (from_id, to_id, discovered) VALUES (?, ?, ?)",
            (edge.from_id, edge.to_id, int(edge.discovered)),
        )
        self._conn.commit()

    def get_dep_edges(self) -> list[DepEdge]:
        rows = self._conn.execute("SELECT * FROM dep_edges").fetchall()
        return [DepEdge(TaskId(r["from_id"]), TaskId(r["to_id"]), bool(r["discovered"])) for r in rows]
