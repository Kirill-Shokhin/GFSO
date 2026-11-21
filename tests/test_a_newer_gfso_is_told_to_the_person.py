"""A newer gfso on PyPI reaches the person: `doctor` says it, and so does the user-agent's first call of every task.

Nothing in 0.3.0 ever told an installed user a release existed. The index is asked at most once a day, its answer kept
in the home; offline says nothing and spends no day.

CONTROL: make `newer` compare with `<` instead of `<=` and the same-version case goes red; drop the cache read and the
once-a-day case goes red.
"""
from __future__ import annotations

import json

import anyio
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from gfso import updates as U
from gfso.mcp import server as MS
from gfso.runtime import ProjectRegistry


@pytest.fixture
def asking(monkeypatch, tmp_path):
    monkeypatch.delenv("GFSO_NO_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(U, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(U, "__version__", "0.3.0")
    calls = []

    def ask_returning(v):
        def ask():
            calls.append(v)
            if isinstance(v, Exception):
                raise v
            return v
        return ask
    return ask_returning, calls


@pytest.mark.parametrize("published, told", [
    ("0.3.1", True), ("0.4.0", True), ("1.0.0", True),
    ("0.3.0", False), ("0.2.0", False), ("0.3.1rc1", False), ("0.3.0.post1", False),
])
def test_only_a_newer_release_is_told(asking, published, told):
    ask, _ = asking
    said = U.newer(ask=ask(published))
    assert bool(said) is told, said
    if told:
        assert f"gfso {published} is published" in said and "pipx upgrade gfso" in said


def test_the_index_is_asked_once_a_day(asking):
    ask, calls = asking
    clock = [1_000_000.0]
    now = lambda: clock[0]
    assert U.newer(now=now, ask=ask("0.3.1"))
    assert U.newer(now=now, ask=ask("0.3.2")) and calls == ["0.3.1"]      # the day's answer, not a second request
    clock[0] += U.DAY_S + 1
    assert "0.3.2" in U.newer(now=now, ask=ask("0.3.2")) and calls == ["0.3.1", "0.3.2"]


def test_offline_says_nothing_and_asks_again_after_an_hour_not_on_every_call(asking):
    ask, calls = asking
    clock = [1_000_000.0]
    now = lambda: clock[0]
    assert U.newer(now=now, ask=ask(OSError("offline"))) is None
    assert U.newer(now=now, ask=ask("0.3.1")) is None and len(calls) == 1   # a dropped route costs one timeout an hour
    clock[0] += U.MISS_S + 1
    assert U.newer(now=now, ask=ask("0.3.1")) and len(calls) == 2


def test_the_switch_turns_the_asking_off(asking, monkeypatch):
    ask, calls = asking
    monkeypatch.setenv("GFSO_NO_UPDATE_CHECK", "1")
    assert U.newer(ask=ask("9.9.9")) is None and calls == []


@pytest.mark.parametrize("published", [None, "gfso 9.9.9 is published; this is 0.3.0. Offer the person to update"])
def test_the_user_agents_first_call_of_a_task_carries_it(monkeypatch, tmp_path, published):
    """Through the real MCP door, on a registry: `use_project` opens every task, so it is where the person hears it."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GFSO_STORAGE", "memory")
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    monkeypatch.setattr(MS.updates, "newer", lambda **kw: published)

    async def go():
        async with create_connected_server_and_client_session(MS.create_server(ProjectRegistry())._mcp_server) as s:
            await s.call_tool("act_as", {"name": "user"})      # …the person's agent, logged in as him
            return json.loads((await s.call_tool("use_project", {"project": "p1"})).content[0].text)
    out = anyio.run(go)
    assert out.get("newer_gfso") == published
