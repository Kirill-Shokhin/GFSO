"""A call on the ledger carries the context budget its session ran under — the threshold a handover is drawn against
(the author, 2026-10-31, on the timeline's cuts: «есть точка бюджета есть фактическая остановка и все это относительно
полного доступного контекста»). Read back from the roster, a later change of the setting rewrote every past cut."""
from gfso.adapters.llm.base import RecordingProvider, record
from gfso.adapters.storage.sqlite import SqliteStorage
from tests.support import make_engine


class _P(RecordingProvider):
    def __init__(self, budgeted, budget):
        super().__init__("m")
        self.budgeted, self.context_budget = budgeted, budget


def test_the_budget_is_booked_with_the_call_and_outlives_the_setting(tmp_path):
    work, check = _P(True, 70_000), _P(False, 70_000)
    work._book(record(turns=3, peak_context=71_000, context_window=200_000))
    check._book(record(turns=1))
    work.context_budget = 120_000                               # the setting changed afterwards
    assert work.calls[0]["context_budget"] == 70_000
    assert check.calls[0]["context_budget"] is None, "a one-round role runs under no budget"

    for storage in (None, SqliteStorage(str(tmp_path / "s.db"))):
        e = make_engine(storage) if storage else make_engine()
        e.record_llm_usage("executor", [dict(c) for c in work.calls], "n")   # a drain marks what it booked
        assert [r["context_budget"] for r in e._storage.get_usage()] == [70_000]
