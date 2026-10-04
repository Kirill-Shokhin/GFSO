"""Demo seed data — realistic project hierarchy for testing all GFSO features."""
from __future__ import annotations

import logging
from gfso.core.types import (
    Probe,
    TaskId, AgentId, Signal, SignalData, Spec, Criteria,
    CriterionMapping, AcceptedRiskItem, Predictability, Register,
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
                Criteria("api_complete", "All API endpoints implemented and tested", check=(Probe("every endpoint answers", "curl -sf localhost:8000/api/health", "ok"),)),
                Criteria("ui_complete", "Frontend matches design specs", check=(Probe("the built page renders", "test -s dist/index.html && echo built", "built"),)),
                Criteria("data_migrated", "Database schema migrated without data loss", check=(Probe("the new schema is live", "psql -c '\\d orders' | grep -c shipped_at", "1"),)),
                Criteria("docs_updated", "User docs reflect all changes", check=(Probe("the docs name the new verbs", "grep -c 'v2' docs/user_guide.md", "1"),)),
            ),
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
                    Criteria("endpoints", "All CRUD endpoints working", check=(Probe("CRUD answers on each resource", "pytest tests/api -q", "passed"),)),
                    Criteria("tests", "API test coverage > 80%", check=(Probe("coverage is above the bound", "pytest --cov=api --cov-fail-under=80 -q", "passed"),)),
                ),
                accepted_risks=("rate limiting",),
            ), AgentId("dev-alice")),

            (TaskId("frontend-ui"), Spec(
                description="Frontend UI",
                criteria=(
                    Criteria("responsive", "Works on mobile and desktop", check=(Probe("the layout holds at phone width", "npx playwright test --grep viewport", "passed"),)),
                    Criteria("accessible", "WCAG 2.1 AA compliant", check=(Probe("no WCAG violations", "npx axe dist/index.html", "0 violations"),)),
                    # Dep is criteria-content (§2): the UI depends on the backend API's contract.
                    Criteria("uses_backend_api", "UI calls the backend API; breaks if the API contract differs",
                             depends_on=TaskId("backend-api")),
                ),
                accepted_risks=("IE11 support",),
            ), AgentId("dev-bob")),

            (TaskId("db-migration"), Spec(
                description="Database Migration",
                criteria=(
                    Criteria("schema", "New schema deployed", check=(Probe("the migration applied", "alembic current", "head"),)),
                    Criteria("rollback", "Rollback script tested", check=(Probe("the rollback runs clean", "alembic downgrade -1 && alembic upgrade head", "head"),)),
                ),
                accepted_risks=("performance on 10M+ rows",),
            ), AgentId("dev-carol")),

            (TaskId("docs"), Spec(
                description="Documentation",
                criteria=(
                    Criteria("api_docs", "OpenAPI spec updated", check=(Probe("the OpenAPI spec parses and covers the endpoints", "npx @redocly/cli lint openapi.yaml", "0 errors"),)),
                    Criteria("user_guide", "User guide covers new features", check=(Probe("the guide documents the new flow", "grep -c 'shipping' docs/user_guide.md", "1"),)),
                ),
                accepted_risks=("internal architecture docs",),
            ), AgentId("dev-dave")),
        ],
        criterion_mappings=[
            CriterionMapping("api_complete", TaskId("backend-api")),
            CriterionMapping("ui_complete", TaskId("frontend-ui")),
            CriterionMapping("data_migrated", TaskId("db-migration")),
            CriterionMapping("docs_updated", TaskId("docs")),
        ],
        # the split's register, its decomposer's (§9.2), rides the admission (§11.5): one grouped entry per STD-3
        # component (§9.4) and the split's own denial by S (§9.5)
        register=Register((
            AcceptedRiskItem("legacy API backward compat edge cases", Predictability.STATISTICAL,
                             "contract tests cover the main client paths", "a client reports a break", 0.05,
                             "one client integration breaks until patched", component="data_integrity"),
            AcceptedRiskItem("slow queries under production load", Predictability.STATISTICAL,
                             "load-tested at twice the expected traffic", "p95 latency above 500 ms", 0.05,
                             "pages slow down until the query is indexed", component="performance_regression"),
            AcceptedRiskItem.denial_of(0.1, "a four-part release split; no record of comparable splits yet"),
        ), ("data_integrity", "performance_regression")),
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

    # Docs: stays in OFFERED (dave hasn't accepted yet)
    # (already in OFFERED from decompose_task → ASSIGN)
    # Frontend→backend dependency is declared as criteria-content in frontend-ui's spec (above).

    log.info("Demo project seeded.")
    log.info("  You are: PM (top-level issuer for release-v2)")
    log.info("  Tech Lead: issuer for subtasks, executor for release-v2")
    log.info("  Developers: alice (backend), bob (frontend/blocked), carol (db/done), dave (docs/review)")
    log.info("")
    log.info("  Try: click on 'Backend API' → Deliver → then Pass as tech-lead")
    log.info("       click on 'Frontend UI' → Resolve Block as tech-lead")
    log.info("       click on 'Documentation' → Accept as dev-dave")
