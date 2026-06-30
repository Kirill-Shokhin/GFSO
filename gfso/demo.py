"""Demo seed data — realistic project hierarchy for testing all GFSO features."""
from __future__ import annotations

import logging
from gfso.core.types import (
    TaskId, AgentId, Signal, SignalData, Spec, Criteria,
    CriterionMapping,
)
from gfso.engine import Engine

log = logging.getLogger(__name__)


def seed_demo(engine: Engine) -> None:
    """Populate engine with a realistic v2.0 release project."""
    log.info("Seeding demo project...")

    # === Root task: Release v2.0 ===
    root = engine.assign_task(
        TaskId("release-v2"),
        Spec(
            description="Release v2.0",
            criteria=(
                Criteria("api_complete", "All API endpoints implemented and tested"),
                Criteria("ui_complete", "Frontend matches design specs"),
                Criteria("data_migrated", "Database schema migrated without data loss"),
                Criteria("docs_updated", "User docs reflect all changes"),
            ),
            neglected=("legacy API backward compat edge cases",),
            risk_components=("data_integrity", "performance_regression"),
        ),
        AgentId("tech-lead"),
    )
    engine.wait_idle()

    # Tech Lead accepts the task
    engine.send_signal(SignalData(
        signal=Signal.ACCEPT, task_id=TaskId("release-v2"),
        source=AgentId("tech-lead"),
    ))
    engine.wait_idle()

    # === Decompose into 4 subtasks ===
    engine.decompose_task(
        TaskId("release-v2"),
        [
            (TaskId("backend-api"), Spec(
                description="Backend API",
                criteria=(
                    Criteria("endpoints", "All CRUD endpoints working"),
                    Criteria("tests", "API test coverage > 80%"),
                ),
                neglected=("rate limiting",),
            ), AgentId("dev-alice")),

            (TaskId("frontend-ui"), Spec(
                description="Frontend UI",
                criteria=(
                    Criteria("responsive", "Works on mobile and desktop"),
                    Criteria("accessible", "WCAG 2.1 AA compliant"),
                    # Dep is criteria-content (§2.2): the UI depends on the backend API's contract.
                    Criteria("uses_backend_api", "UI calls the backend API; breaks if the API contract differs",
                             depends_on=TaskId("backend-api")),
                ),
                neglected=("IE11 support",),
            ), AgentId("dev-bob")),

            (TaskId("db-migration"), Spec(
                description="Database Migration",
                criteria=(
                    Criteria("schema", "New schema deployed"),
                    Criteria("rollback", "Rollback script tested"),
                ),
                neglected=("performance on 10M+ rows",),
            ), AgentId("dev-carol")),

            (TaskId("docs"), Spec(
                description="Documentation",
                criteria=(
                    Criteria("api_docs", "OpenAPI spec updated"),
                    Criteria("user_guide", "User guide covers new features"),
                ),
                neglected=("internal architecture docs",),
            ), AgentId("dev-dave")),
        ],
        criterion_mappings=[
            CriterionMapping("api_complete", TaskId("backend-api")),
            CriterionMapping("ui_complete", TaskId("frontend-ui")),
            CriterionMapping("data_migrated", TaskId("db-migration")),
            CriterionMapping("docs_updated", TaskId("docs")),
        ],
    )
    engine.wait_idle()

    # === Progress each subtask to different states ===

    # Backend API: ACCEPT → EXECUTING (alice is working)
    engine.send_signal(SignalData(
        signal=Signal.ACCEPT, task_id=TaskId("backend-api"),
        source=AgentId("dev-alice"),
    ))
    engine.wait_idle()

    # Frontend UI: ACCEPT → EXECUTING → BLOCK (bob hit a blocker)
    engine.send_signal(SignalData(
        signal=Signal.ACCEPT, task_id=TaskId("frontend-ui"),
        source=AgentId("dev-bob"),
    ))
    engine.wait_idle()
    engine.send_signal(SignalData(
        signal=Signal.BLOCK, task_id=TaskId("frontend-ui"),
        source=AgentId("dev-bob"),
        reason="Waiting for design team to finalize mobile mockups",
    ))
    engine.wait_idle()

    # DB Migration: ACCEPT → DELIVER → PASS (carol finished)
    engine.send_signal(SignalData(
        signal=Signal.ACCEPT, task_id=TaskId("db-migration"),
        source=AgentId("dev-carol"),
    ))
    engine.wait_idle()
    engine.send_signal(SignalData(
        signal=Signal.DELIVER, task_id=TaskId("db-migration"),
        source=AgentId("dev-carol"),
        result="Migration script v2 + rollback tested on staging",
    ))
    engine.wait_idle()
    engine.send_signal(SignalData(
        signal=Signal.PASS, task_id=TaskId("db-migration"),
        source=AgentId("tech-lead"),
    ))
    engine.wait_idle()

    # Docs: stays in REVIEW (dave hasn't accepted yet)
    # (already in REVIEW from decompose_task → ASSIGN)
    # Frontend→backend dependency is declared as criteria-content in frontend-ui's spec (above).

    log.info("Demo project seeded.")
    log.info("  You are: PM (top-level issuer for release-v2)")
    log.info("  Tech Lead: issuer for subtasks, executor for release-v2")
    log.info("  Developers: alice (backend), bob (frontend/blocked), carol (db/done), dave (docs/review)")
    log.info("")
    log.info("  Try: click on 'Backend API' → Deliver → then Pass as tech-lead")
    log.info("       click on 'Frontend UI' → Resolve Block as tech-lead")
    log.info("       click on 'Documentation' → Accept as dev-dave")
