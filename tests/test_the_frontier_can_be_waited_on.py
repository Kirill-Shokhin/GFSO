"""A graph that is working looks exactly like one that is stuck, from a single call away.

Every tester of waves 18-19 wrote the same poll loop by hand — `python -c "time.sleep(20)"` between
`next_steps` calls — and spent 8 to 15 minutes of their run inside it. The frontier already knows
whether it is holding something back (`in_flight`, `waiting`); what it could not do is wait.
"""
import threading
import time

from gfso import tools as T, tools_llm as TL
from tests.support import criterion, make_engine, REGISTER


def _graph():
    e = make_engine(check_interval=10_000)
    e.start()
    T.create_task(e, "root", {"description": "r", "criteria": [criterion("c", "C")]}, assignee="user")
    T.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "k", "criteria": [criterion("k1", "K")]},
                             "assignee": "someone-else", "covers": ["c"]}], accepted_risks=REGISTER)
    return e


def test_it_returns_the_moment_the_frontier_has_something():
    """…and returns the ordinary answer, not a different shape."""
    e = _graph()
    T.signal(e, "kid", "ACCEPT", "someone-else")
    T.signal(e, "kid", "DELIVER", "someone-else", result="did it", self_validation="PASS")
    idle = T.next_steps(e, actor="nobody")
    assert not any(s["mine"] for s in idle["steps"]), "the precondition: nothing here is theirs"

    def _unblock():
        time.sleep(0.4)
        T.signal(e, "kid", "PASS", "user")           # the issuer signs; root becomes actionable

    threading.Thread(target=_unblock, daemon=True).start()
    t0 = time.time()
    out = TL.wait_for_the_customer(e, actor="user", seconds=10)
    assert out.get("steps") or out.get("complete"), "it waited for the answer instead of spinning"
    assert time.time() - t0 < 8, "…and returned as soon as there was one, not at the deadline"
    e.stop()


def test_a_wait_that_finds_nothing_says_so_rather_than_hanging():
    e = _graph()
    out = TL.wait_for_the_customer(e, actor="nobody", seconds=1.0)
    assert out["waited_seconds"] == 1.0 and "nothing needs you yet" in out["waited_note"], out
    e.stop()
