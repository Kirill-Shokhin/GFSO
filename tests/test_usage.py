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
from fastapi.testclient import TestClient

from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.api.server import create_app
from gfso.runtime import ProjectRegistry
from gfso.adapters.llm.stub import StubLLM
from gfso.core.types import TaskId
from tests.support import make_engine


class _Provider:
    """A provider shaped like the real ones: per-call records, drained by the engine."""

    def __init__(self, calls):
        self.calls = list(calls)


def _engine(storage=None):
    e = make_engine(storage, llm=StubLLM(), check_interval=10_000)
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
    e = _engine()
    e.record_llm_usage("executor", _Provider([{"output_tokens": 3, "cost_usd": 0.4}]), TaskId("n"))
    with TestClient(create_app(e)) as c:
        body = c.get("/api/usage").json()
        assert body["cost_usd"] == 0.4 and "calls" not in body.get("by_stage", {})
        assert c.get("/api/usage?detail=true").json()["calls"][0]["stage"] == "executor"


def test_the_money_total_names_its_scope_on_a_multi_project_server(monkeypatch, tmp_path):
    """The endpoint has to answer WHOSE money it is — and on the real server it stopped answering at all.

    A money total that cannot name its scope was already a measured defect (a person read $0.54 for a
    run that had spent $7.08, 2026-08-21), which is why `project` is in the body. The naming step
    reads the per-request `?project=` scope, and that lookup is only reached when a REGISTRY exists —
    so a single-engine app takes the other branch and the endpoint stayed green in the suite while
    `/api/usage` returned 500 on every real server for a week. The scope is the point of the field;
    the test has to exercise the path that computes it.
    """
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    monkeypatch.setenv("GFSO_STORAGE", "memory")
    reg = ProjectRegistry()
    reg.engine().record_llm_usage("executor", _Provider([{"output_tokens": 3, "cost_usd": 0.4}]),
                                  TaskId("n"))
    with TestClient(create_app(reg.engine(), registry=reg)) as c:
        body = c.get("/api/usage")
        assert body.status_code == 200, body.text
        assert body.json()["project"] == "default"
        # `beta` is AUTHORED first, because a read no longer creates the project it names: asking
        # about money on a name that does not exist is a typo, and answering $0.00 for it is the
        # same confusion as reporting another project's total. The point here is unchanged — the
        # answer is scoped to the tab, not to the server-wide active project.
        reg.engine("beta", create=True)
        named = c.get("/api/usage?project=beta").json()
        assert named["project"] == "beta"          # the tab's scope, not the server-wide active one
        assert c.get("/api/usage?project=nosuchproject").status_code == 404
    for e in list(reg._engines.values()):
        e.stop()
