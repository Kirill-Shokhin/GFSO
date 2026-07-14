"""Observation window backend: emit_info persists non-tick lines (SQLite pipeline_log),
ticks stay WS-only, history survives an engine/storage restart, /api/pipeline serves it."""
import os

from gfso.engine import Engine
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.llm.stub import StubLLM


def _eng(storage=None):
    e = Engine(storage or MemoryStorage(), HumanAgent(), StubLLM(), validate_signals=True)
    e.start()
    return e


def test_emit_info_persists_lines_but_not_ticks():
    e = _eng()
    e.emit_info("decompose", "1/1 searcher…")
    e.emit_info("decompose", "root searcher: 202 tokens · 9s")     # live tick — WS-only
    e.emit_info("decompose", "total: 63s wall · 8.4k out tokens · 3 calls")
    rows = e.pipeline_log()
    assert [r["message"] for r in rows] == ["1/1 searcher…", "total: 63s wall · 8.4k out tokens · 3 calls"]
    assert all(r["source"] == "decompose" and r["ts"] for r in rows)
    e.stop()


def test_pipeline_log_survives_restart(tmp_path):
    db = str(tmp_path / "p.db")
    e = _eng(SqliteStorage(db))
    e.emit_info("validate_result", "wc: validator verdict PASS · done in 10s · 0.4k out · Σ 0.4k out")
    e.stop()
    e2 = _eng(SqliteStorage(db))                                    # fresh process over the same file
    rows = e2.pipeline_log()
    assert len(rows) == 1 and "verdict PASS" in rows[0]["message"]
    e2.stop()


def test_pipeline_log_capped():
    s = MemoryStorage()
    for i in range(10500):
        s.log_pipeline("t", "x", f"m{i}")
    rows = s.get_pipeline(limit=20000)
    assert len(rows) == 10000 and rows[0]["message"] == "m500"      # oldest pruned


def test_api_pipeline_endpoint():
    from fastapi.testclient import TestClient
    from gfso.api.server import create_app

    e = _eng()
    e.emit_info("decompose", "builder: 7 subtasks · 8 deps")
    app = create_app(e)
    with TestClient(app) as c:
        rows = c.get("/api/pipeline").json()
        assert rows and rows[-1]["message"].startswith("builder")
        assert c.get("/api/pipeline?limit=1").json() == rows[-1:]
    e.stop()


def test_deliver_result_survives_restart(tmp_path):
    """The deliverable pointer (DELIVER result) persists — after `gfso down`/restart validate_result's
    default path still has the validator's input (no explicit `deliverable` needed)."""
    from gfso import tools as T
    from gfso.tools_llm import _last_deliver_result
    db = str(tmp_path / "d.db")
    e = _eng(SqliteStorage(db))
    T.create_task(e, "n", {"description": "x", "criteria": [{"name": "a", "description": "A"}]}, "w")
    T.signal(e, "n", "ACCEPT", "w")
    T.signal(e, "n", "DELIVER", "w", result="artifact at out/x.txt; a met by ...")
    e.stop()
    e2 = _eng(SqliteStorage(db))                                   # fresh process, empty audit log
    assert _last_deliver_result(e2, T.TaskId("n")) == "artifact at out/x.txt; a met by ..."
    e2.stop()
