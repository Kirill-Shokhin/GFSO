"""What a graph COST — the question the system could not answer about itself.

The numbers existed per call, inside whichever verb happened to run, and were summarised into a
progress line as text and then dropped. So "what did this decomposition cost" had no answer, and
anything that needed one (a user asking why a plan was expensive; an experiment's cost column) had
to reconstruct it from its own side of the wire — which only ever sees the calls it makes itself,
never the ones the engine makes for it.

Two rules the tests pin, because both are ways a money column lies:
  * cost is what the TRANSPORT reported, never a number derived from tokens here;
  * a provider that reports no price contributes zero AND is counted apart (`costed_calls`), so a
    total can never present "not reported" as "free" (the ⊥-as-zero error, §21 conventions).
"""
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.llm.stub import StubLLM
from gfso.engine import Engine
from gfso.core.types import TaskId


class _Provider:
    """A provider shaped like the real ones: per-call records, drained by the engine."""

    def __init__(self, calls):
        self.calls = list(calls)


def _engine(storage=None):
    e = Engine(storage or MemoryStorage(), HumanAgent(), llm=StubLLM(), check_interval=10_000)
    return e


def test_usage_is_recorded_per_role_and_totalled():
    e = _engine()
    e.record_llm_usage("decomposer", _Provider([
        {"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.5, "model": "sonnet",
         "cache_read_input_tokens": 40, "duration_ms": 1200}]), TaskId("root"))
    e.record_llm_usage("executor", _Provider([
        {"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.25, "model": "haiku"},
        {"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.25, "model": "haiku"}]), TaskId("root.a"))

    tot = e.usage_totals()
    assert tot["calls"] == 3 and tot["costed_calls"] == 3
    assert tot["cost_usd"] == 1.0
    assert tot["output_tokens"] == 30 and tot["cache_input_tokens"] == 40
    assert tot["by_stage"]["decomposer"] == {"calls": 1, "cost_usd": 0.5, "output_tokens": 20}
    assert tot["by_stage"]["executor"]["calls"] == 2


def test_a_provider_that_reports_no_price_is_counted_apart():
    """`cost_usd: None` is "not reported", not "free" — and the split is what says so."""
    e = _engine()
    e.record_llm_usage("l2_review", _Provider([
        {"input_tokens": 10, "output_tokens": 5, "cost_usd": None, "model": "local"}]))
    tot = e.usage_totals()
    assert tot["calls"] == 1 and tot["costed_calls"] == 0 and tot["cost_usd"] == 0.0


def test_draining_is_idempotent_per_call():
    """The records are CONSUMED: a second drain of the same provider cannot double-count them —
    the dispatcher reuses a provider across nodes, and a double count is silent."""
    e = _engine()
    p = _Provider([{"input_tokens": 1, "output_tokens": 1, "cost_usd": 0.1}])
    assert e.record_llm_usage("executor", p) == 1
    assert e.record_llm_usage("executor", p) == 0
    assert e.usage_totals()["calls"] == 1


def test_a_list_of_call_records_is_accepted_too():
    """`auto_decompose` returns the RECORDS, not the provider that made them."""
    e = _engine()
    e.record_llm_usage("decomposer", [{"output_tokens": 7, "cost_usd": 0.3}])
    assert e.usage_totals()["by_stage"]["decomposer"]["output_tokens"] == 7


def test_usage_survives_a_restart(tmp_path):
    """A run is hours long and a server restart is an ordinary event; a cost that lives in memory
    answers the question only until the moment someone needs it."""
    db = str(tmp_path / "u.db")
    e = _engine(SqliteStorage(db))
    e.record_llm_usage("validator", _Provider([{"output_tokens": 9, "cost_usd": 0.2}]), TaskId("n1"))
    e._graph._storage.close()

    again = _engine(SqliteStorage(db))
    tot = again.usage_totals()
    assert tot["calls"] == 1 and tot["cost_usd"] == 0.2
    assert again._graph._storage.get_usage()[0]["node_id"] == "n1"
    again._graph._storage.close()


def test_the_endpoint_serves_totals_and_detail():
    from fastapi.testclient import TestClient
    from gfso.api.server import create_app

    e = _engine()
    e.record_llm_usage("executor", _Provider([{"output_tokens": 3, "cost_usd": 0.4}]), TaskId("n"))
    with TestClient(create_app(e)) as c:
        body = c.get("/api/usage").json()
        assert body["cost_usd"] == 0.4 and "calls" not in body.get("by_stage", {})
        assert c.get("/api/usage?detail=true").json()["calls"][0]["stage"] == "executor"
