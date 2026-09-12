"""A run whose review claim was reclaimed must not free the claim that replaced it.

`begin_review` keys the in-flight slot on the node's GENERATION, and a TTL reclaim does not move
that generation — so the slow original, returning after the timeout, called `end_review` with the
same key and freed the LIVE claim. A third review could then start on one unchanged plan, each
paying for its own model run and each able to land a verdict over the others.

The claim now carries a token; `end_review` drops the slot only when the token in it is still ours.

Control: have `end_review` pop by key regardless of the token, and the last case goes red.
"""
from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import make_engine, UNMODELLED_FAULT

_RISKS = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]


class _Clock:
    """A clock the test moves by hand — the TTL is 1800 s and no test may wait for it."""

    def __init__(self):
        self.t = 1_000_000.0

    def now(self) -> float:
        return self.t


def _engine():
    clock = _Clock()
    e = make_engine(check_interval=10_000, clock=clock)
    e.start()
    T.create_task(e, "root", {"description": "the whole",
                              "criteria": [{"name": "c1", "description": "C1"}],
                              "accepted_risks": _RISKS}, assignee="agent")
    e.wait_idle()
    return e, clock


def test_a_second_review_is_refused_while_the_first_is_alive():
    e, _ = _engine()
    first = e.begin_review(TaskId("root"))
    assert first is not None
    assert e.begin_review(TaskId("root")) is None, "two model runs over one unchanged plan"
    assert e.review_in_flight(TaskId("root")) is True
    e.stop()


def test_a_claim_nobody_is_behind_any_more_is_reclaimed():
    e, clock = _engine()
    first = e.begin_review(TaskId("root"))
    clock.t += 1801
    assert e.review_in_flight(TaskId("root")) is False, "a claim past its TTL is not a live run"
    assert e.begin_review(TaskId("root")) is not None, "the slot was never reclaimable"
    e.stop()


def test_the_reclaimed_predecessor_does_not_free_the_live_claim():
    e, clock = _engine()
    first = e.begin_review(TaskId("root"))
    clock.t += 1801
    second = e.begin_review(TaskId("root"))          # the slot is taken over
    assert second is not None

    e.end_review(first)                              # …and now the slow original returns
    assert e.review_in_flight(TaskId("root")) is True, \
        "the reclaimed run freed the claim that replaced it — a third review could start"
    assert e.begin_review(TaskId("root")) is None

    e.end_review(second)                             # the live one releases normally
    assert e.review_in_flight(TaskId("root")) is False
    e.stop()
