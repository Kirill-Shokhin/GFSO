"""A call that does not fit a verb is refused in the verb's own words, not Python's.

The generated action surface passed the interpreter's TypeError straight through, so a user driving
GFSO from the CLI or over HTTP got `signal() missing 1 required positional argument: 'source'` — the
implementation's view of a function they never called, with no hint that `source` is who signs the
signal. Measured while driving a real graph through the CLI door. The door holds the signature; it
can name what is missing and what else the verb takes.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gfso.api.server import create_app
from tests.test_integration import _engine


@pytest.fixture()
def client():
    with TestClient(create_app(_engine())) as c:
        yield c


def test_a_missing_argument_is_named_with_the_verb(client):
    r = client.post("/api/run/signal", json={"task_id": "x"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "signal needs" in detail and "source" in detail
    assert "positional argument" not in detail, "the interpreter's phrasing reached the user"


def test_the_refusal_says_what_else_the_verb_takes(client):
    """Naming only the gap leaves the caller guessing at the rest of the contract."""
    detail = client.post("/api/run/signal", json={"task_id": "x"}).json()["detail"]
    assert "it also takes" in detail and "reason" in detail


def test_an_argument_the_verb_does_not_take_is_named_too(client):
    """The other half of the same confusion: `project` is accepted by some doors and not by this
    one, and 'unexpected keyword argument' does not tell a caller which door they are at."""
    r = client.post("/api/run/get_task", json={"task_id": "x", "nonsense": 1})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "does not take" in detail and "nonsense" in detail


def test_a_real_refusal_still_speaks_for_itself(client):
    """The engine's own refusals are already written for a reader — they must pass through
    unchanged, or this help would swallow the message that matters."""
    r = client.post("/api/run/create_task", json={"task_id": "n", "spec": {"name": "x"},
                                                  "assignee": "alice"})
    if r.status_code == 422:
        assert "create_task needs" not in r.json()["detail"]
