"""A tool-less one-shot that ended in an API error is asked once more: it changes nothing, and its empty answer was read
as an answer — a plan's search that ended in "API Error: JSON Parse error" was folded as "no findings" and the
authoring went on without it (gb-coreutils-tnrqbl588, 2026-10-31). A limit is no such error (it moves the credential or
stops the project), and an agent run with tools is never re-run here: it changed its place."""
from gfso.llm import llm_factory
from tests.test_a_session_is_launched_the_same_through_its_provider import ANSWER, held, seen  # noqa: F401 — the fake CLI

DROPPED = {"type": "result", "is_error": True, "api_error": "api_error",
           "result": "API Error: JSON Parse error: Unrecognized token", "total_cost_usd": 0, "usage": {}}
LIMIT = {"type": "result", "is_error": True, "api_error": "usage_limit_reached", "result": "You've hit your limit",
         "total_cost_usd": 0, "usage": {}, "rate_limit_info": {"status": "rejected", "resetsAt": 4102444800}}


def _answers(seen, *replies):  # noqa: F811
    queue = list(replies)
    seen.Proc.answer = property(lambda self: queue.pop(0) if queue else ANSWER)


def test_a_dropped_one_shot_is_asked_once_more_and_answers(seen, held):  # noqa: F811
    _answers(seen, DROPPED)
    llm = llm_factory("m")
    assert llm.complete("x", "SYS") and len(seen) == 2


def test_it_is_asked_once_only(seen, held):  # noqa: F811
    _answers(seen, DROPPED, DROPPED, DROPPED)
    assert llm_factory("m").complete("x", "SYS") == "" and len(seen) == 2


def test_a_limit_is_no_dropped_call(seen, held):  # noqa: F811
    _answers(seen, LIMIT)
    llm_factory("m").complete("x", "SYS")
    assert len(seen) == 1


def test_a_neighbours_record_landing_after_it_does_not_decide(seen, held):  # noqa: F811
    """Readings run in parallel on one provider: the call's own record decides, not the shared list's last (critic)."""
    _answers(seen, DROPPED)
    llm = llm_factory("m")
    real = llm._attempt

    def attempt(*a, **kw):
        out = real(*a, **kw)
        llm.calls.append({"error": None, "stage": "a neighbour's reading"})
        return out
    llm._attempt = attempt
    assert llm.complete("x", "SYS") and len(seen) == 2
