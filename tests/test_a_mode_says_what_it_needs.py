"""A page offering the choice of mode reads what each mode needs from the engine — the rule `set_mode`
enforces — instead of keeping a copy: the page's copy had solo needing only a validator and auto one
executor, while the engine refuses solo-with-dispatch without an executor and auto without two
(2026-10-24, a critic replaying the constructor's payloads)."""
from fastapi.testclient import TestClient

from gfso import tools_llm as L
from gfso.api.server import create_app
from gfso.runtime import ProjectRegistry


def test_the_modes_read_is_the_rule_set_mode_enforces(monkeypatch, tmp_path):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    monkeypatch.setenv("GFSO_STORAGE", "memory")
    reg = ProjectRegistry()
    eng = reg.engine()
    body = TestClient(create_app(eng, registry=reg)).get("/api/modes").json()
    for m in ("solo", "semi", "auto"):
        for p in ("dispatch", "in_chat"):
            read = body["modes"][m][p]
            refused = L.set_mode(eng, m, perform=p)
            # whatever the roster holds, the read predicts the verb: ready ⟺ not refused for staffing
            assert read["ready"] == (not refused.get("refused")), (m, p, read, refused)
            if not read["ready"]:
                assert refused["error"] == read["missing"]
            assert refused.get("refused"), "an empty roster staffs no mode — this test reads refusals only"
    assert body["modes"]["auto"]["dispatch"]["needs_executors"] == 2
    assert body["modes"]["solo"]["dispatch"]["needs_executors"] == 1
    assert body["modes"]["solo"]["in_chat"]["needs_executors"] == 0
