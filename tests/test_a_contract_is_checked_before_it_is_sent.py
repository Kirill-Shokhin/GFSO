"""A page that lets a person write a contract asks the engine what admission would refuse, before
sending it — the same ladder every ASSIGN runs. A copy of its first two rungs in the page passed a
hollow `echo ok`, which create_task then refused (2026-10-24)."""
from fastapi.testclient import TestClient

from gfso.api.server import create_app
from gfso.runtime import ProjectRegistry


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    monkeypatch.setenv("GFSO_STORAGE", "memory")
    reg = ProjectRegistry()
    return TestClient(create_app(reg.engine(), registry=reg)), tmp_path


def _crit(command):
    return {"name": "works", "description": "it works",
            "check": [{"behaviour": "runs", "command": command, "expect": "exit 0"}]}


def test_admission_is_read_from_the_engine_and_writes_nothing(monkeypatch, tmp_path):
    client, home = _client(monkeypatch, tmp_path)
    say = lambda spec: client.post("/api/admission", json=spec).json()["defects"]
    assert say({"name": "g", "description": "d", "criteria": []}), "no criteria is a defect"
    assert any("check" in d for d in say({"name": "g", "description": "d",
                                          "criteria": [{"name": "works", "description": "it works"}]}))
    assert any("constant" in d for d in say({"name": "g", "description": "d", "criteria": [_crit("echo ok")]}))
    assert say({"name": "g", "description": "d", "criteria": [_crit("test -f out.txt && grep -q done out.txt")]}) == []
    assert not list(home.glob("*.db")), "a read of admission created a project"
