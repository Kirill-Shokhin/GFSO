"""A consent session — an executor reading a contract to accept it or not — is booked as `consent`, not as the
executor's work: the panel's «executed by … ×n» counted every consent as an execution (the ui stream's known limit,
2026-10-25). The other roles that share the frame keep the executor's stage.
"""
import types

from gfso import sessions as S
from gfso.core.types import Stage
from tests.support import make_engine


def _booked(monkeypatch, role):
    e, seen = make_engine(), []
    monkeypatch.setattr(e, "record_llm_usage", lambda stage, llm, node: seen.append(stage))
    monkeypatch.setattr(S, "session_calls", lambda llm, stage: seen.append(stage) or [])
    llm = types.SimpleNamespace(calls=[], run_agent=lambda *a, **k: "{}")
    S._spawn(e, "kid", "exec-1", {}, llm, role, "consent.md", "packet", {"type": "object"}, "consent", None, work=False)
    return set(seen)


def test_a_consent_is_booked_as_consent(monkeypatch):
    assert _booked(monkeypatch, "consent") == {Stage.CONSENT}


def test_the_work_keeps_the_executors_stage(monkeypatch):
    assert _booked(monkeypatch, "executor") == {Stage.EXECUTOR}
    assert _booked(monkeypatch, "scope-executor") == {Stage.EXECUTOR}
