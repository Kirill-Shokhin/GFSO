"""The dispatcher's one cap admits work that closes what is delivered or asked before work that opens new
execution (`gfso.delegate.Slots`) — without starving the openers and without admitting more than the cap."""
from __future__ import annotations

import threading
import time

import gfso.delegate as D
from gfso.core.types import TaskId
from gfso.delegate import Dispatcher, Slots
from gfso.roster import AgentRegistry
from tests.support import make_engine


def _until(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while not cond() and time.monotonic() < end:
        time.sleep(0.005)
    return cond()


def _queue(s: Slots, lane, name: str, order: list) -> threading.Thread:
    def run():
        lane.acquire()
        order.append(name)
    th = threading.Thread(target=run, daemon=True)
    th.start()
    return th


def _hold(s: Slots, lane, n: int) -> None:
    """`n` slots taken from `lane` off the test's own thread, so a broken admission fails the test, not hangs it."""
    held = []
    for _ in range(n):
        _queue(s, lane, "held", held)
    assert _until(lambda: len(held) == n), "the cap refused work while slots were free"


def test_with_the_cap_full_of_executors_the_validator_and_the_issuer_go_before_a_new_executor():
    s, order = Slots(2), []
    _hold(s, s.opening, 2)                            # two executors hold the whole cap
    _queue(s, s.opening, "executor", order)           # the worst case: the opener waits FIRST
    time.sleep(0.05)
    _queue(s, s.closing, "validator", order), _queue(s, s.closing, "issuer", order)
    assert _until(lambda: s._closers == 2)
    for n in (1, 2, 3):
        s.opening.release()
        assert _until(lambda: len(order) == n), order
    assert sorted(order[:2]) == ["issuer", "validator"] and order[2] == "executor", order


def test_an_executor_runs_whenever_no_closing_work_waits():
    s, order = Slots(1), []
    _hold(s, s.closing, 1)
    _queue(s, s.opening, "executor", order)
    time.sleep(0.05)
    assert order == []
    s.closing.release()
    assert _until(lambda: order == ["executor"]), order
    s.opening.release()
    _queue(s, s.opening, "next executor", order)      # nothing closing waits: admitted at once
    assert _until(lambda: order == ["executor", "next executor"]), order


def test_a_slot_left_free_by_the_last_admitted_closer_reaches_a_waiting_executor():
    s, order = Slots(2), []
    _hold(s, s.opening, 2)
    _queue(s, s.opening, "executor", order)
    time.sleep(0.05)
    _queue(s, s.closing, "validator", order)
    assert _until(lambda: s._closers == 1)
    with s._cv:                                       # two slots free in one instant
        s.opening.release(), s.opening.release()
    assert _until(lambda: sorted(order) == ["executor", "validator"]), order


def test_the_cap_is_never_exceeded():
    s, lock, live, peak = Slots(3), threading.Lock(), [0], [0]

    def run(lane):
        with lane:
            with lock:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
            time.sleep(0.01)
            with lock:
                live[0] -= 1
    ths = [threading.Thread(target=run, args=(s.closing if i % 3 else s.opening,), daemon=True) for i in range(30)]
    for th in ths:
        th.start()
    for th in ths:
        th.join(10)
    assert peak[0] == 3 and live[0] == 0 and s._free == 3


def test_each_dispatcher_site_draws_from_its_lane(tmp_path, monkeypatch):
    e = make_engine(validate_signals=True, state_timeout=0)
    d = Dispatcher(e, AgentRegistry(path=str(tmp_path / "agents.json")), poll=30,
                   consent_runner=lambda *a, **k: {"status": "accepted"})
    lanes, caps = [], []
    monkeypatch.setattr(d._cap, "acquire", lanes.append)
    monkeypatch.setattr(D, "answer_open_questions", lambda en, ag, cl, rel, cap, *a: caps.append(cap) or [])
    gone = TaskId("gone")
    d._validate_guarded(gone)
    d._run_guarded_body(gone, "exec-1", (0, 0, 0))
    d._consent_guarded(gone, "exec-1")
    d.dispatch_once()
    assert lanes == [True, False, False] and caps == [d._cap.closing], (lanes, caps)
