"""A question's wait is its own. The sweep's ledger kept one backoff per node version, so when a dispute's turns failed
and its wait doubled to 7 200 s, the TIMEOUT into ESCALATED — the same version — inherited it: the one producer every
other part waited on was never asked its decision before the row's ceiling (series 2 REF 2, GB_c_compiler_ctx2ref_10291339,
root.layout 14:33→16:40)."""
import threading
import time

import gfso.issuer as I
from gfso.core.types import TaskId
from tests.test_the_mode_decides_who_holds_what import _auto_goal


def test_an_escalation_is_asked_at_once_after_the_dispute_backed_off(tmp_path, monkeypatch):
    e, agents = _auto_goal(tmp_path)
    q = {"now": "dispute"}
    asked = []
    monkeypatch.setattr(I, "open_questions", lambda en: [(TaskId("root"), q["now"])])
    monkeypatch.setattr(I, "system_mover", lambda *a, **k: "exec-1")

    def settle(en, ag, t, question, *a, **k):
        asked.append(question)
        return {"status": "unavailable", "why": "the place changed after DELIVER"}
    monkeypatch.setattr(I, "settle", settle)
    ledger, cap = {}, threading.Semaphore(1)

    def sweep():
        before = set(threading.enumerate())
        I.answer_open_questions(e, agents, lambda k: True, lambda *a, **k: None, cap, None, ledger)
        for th in set(threading.enumerate()) - before:
            th.join(5)

    for _ in range(4):   # the dispute's turns fail; each sweep runs past the wait the last one left
        sweep()
        ledger.update({g: (w, 0.0, n) for g, (w, _, n) in ledger.items()})
    sweep()              # …the fifth leaves its doubled wait standing
    assert asked == ["dispute"] * 5
    assert max(nb for _, nb, _ in ledger.values()) - time.monotonic() > 60
    q["now"] = "escalation"   # the version's clock lapsed: the issuer now owes the decision
    sweep()
    assert asked[-1] == "escalation", "the decision waited out the dispute's backoff"
