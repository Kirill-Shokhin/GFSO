"""The dispatcher's own validation of a delivery is in flight while it runs, as the verb's door marks it: a restart that
reads `/api/runtime`'s busy, a container's rest and the page read that record."""
from __future__ import annotations

from gfso import inflight
from gfso import roster
from gfso import validate as V
from tests.support import make_engine


def test_the_dispatchers_own_validation_is_in_flight(monkeypatch):
    seen = []
    monkeypatch.setattr(inflight, "LISTENERS", [*inflight.LISTENERS, lambda now: seen.append([w["verb"] for w in now])])
    e = make_engine()
    V._validate_with(e, roster.default_agents(), "nope", None, "val-1", {"kind": "llm-validator"}, True, None, None)
    assert ["validate_result"] in seen, seen
