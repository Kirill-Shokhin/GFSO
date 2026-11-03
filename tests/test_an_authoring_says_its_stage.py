"""An authoring in flight says the stage it has reached — `{stage, done, of, since}` on its entry, pushed to an open page
as every entry is: the page could tell its progress only from the narration's prose (ui stream, 2026-10-31)."""
import threading

from gfso import inflight as I
from gfso.decompose import loop as L


def test_the_stage_rides_on_the_entry_of_the_thread_that_runs_it():
    pushed = []
    mine = lambda rows: next(w for w in rows if w["verb"] == "auto_decompose")   # a thread an earlier test left may stand first
    I.LISTENERS.append(pushed.append)
    try:
        with I._inflight("auto_decompose"):
            L._stage(object(), "2/3 repairer")
            assert mine(I.in_flight())["stage"] | {"since": 0} == {"stage": "repairing what the checks refuse", "done": 2, "of": 3, "since": 0}
            assert mine(pushed[-1])["stage"]["stage"] == "repairing what the checks refuse", "pushed, not polled"
            with I._inflight("review_decomposition"):
                I.staged("checker")
            L._stage(object(), "sufficiency 1 auditor")       # the outer entry is this thread's again
            outer = next(w for w in I.in_flight() if w["verb"] == "auto_decompose")
            assert outer["stage"]["stage"] == "writing the checks the goal still lacks" and outer["stage"]["done"] is None
            other = threading.Thread(target=I.staged, args=("elsewhere",))
            other.start(), other.join()
            assert mine(I.in_flight())["stage"]["stage"] == "writing the checks the goal still lacks", "another thread's work is not this one"
    finally:
        I.LISTENERS.remove(pushed.append)
    assert I.MINE.get(threading.get_ident()) is None and not [w for w in I.in_flight() if w["verb"] == "auto_decompose"]
