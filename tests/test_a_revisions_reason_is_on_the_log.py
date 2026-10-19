"""A re-ASSIGN's reason is signal data logged with it, not a packet field (§11.3): the typed cause (§15.4) is on the
signal's own row of the log (Thm 11), and it survives a restart."""
from __future__ import annotations

from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.core.types import AgentId, RevisionReason, Signal, TaskId
from gfso.engine.audit import AuditLog
import gfso.tools as T
from tests.support import criterion, make_engine


def test_the_typed_reason_of_a_revision_is_on_its_row_of_the_log(tmp_path):
    db = str(tmp_path / "g.db")
    e = make_engine(validate_signals=True, state_timeout=0, storage=SqliteStorage(db))
    e.start()
    T.create_task(e, "r", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    e.wait_idle()
    t = e.graph.get_task(TaskId("r"))
    e.revise(t.id, t.spec, AgentId(str(e.graph.issuer_of(t.id))), reason=RevisionReason.SPEC_DEFECT)
    e.wait_idle()
    rows = [a for a in e.audit_log(t.id) if a.signal == Signal.ASSIGN and not a.rejected]
    assert [a.revision_reason for a in rows] == [None, "SPEC_DEFECT"]
    e.stop()
    again = [a for a in AuditLog(SqliteStorage(db)).get_entries(TaskId("r")) if a.signal == Signal.ASSIGN]
    assert again[-1].revision_reason == "SPEC_DEFECT", "hydrated from the log"
