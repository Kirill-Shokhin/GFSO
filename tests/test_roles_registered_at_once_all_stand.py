"""Two runs staffing their projects in the same second both get their roles. A reload by one thread replaced the roster
with a file read before another thread's write, and that registration's own answer raised KeyError — a 422 that killed
the second of two runs launched at once (series 3 REF 2, 2026-10-30; 75 of 180 concurrent registrations in a probe).

CONTROL: take `_load` out from under the lock, or read `register`'s answer after it, and this goes red."""
import os
import threading

from gfso.roster import AgentRegistry


def test_concurrent_registrations_all_answer_and_all_stand(tmp_path):
    reg = AgentRegistry(path=str(tmp_path / "agents.json"))
    errs, want = [], set()

    def staff(p):
        d = tmp_path / p
        d.mkdir()
        for k in range(5):
            for role, kind in (("exec", "llm-executor"), ("val", "llm-validator")):
                aid = f"{p}-{role}-{k}"
                want.add(aid)
                try:
                    reg.register(aid, kind, workdir=str(d), project=p)
                except Exception as ex:      # noqa: BLE001 — the failure under test
                    errs.append(f"{aid}: {type(ex).__name__}: {ex}")
                reg.list()                    # the other threads' reads that raced the writes

    ts = [threading.Thread(target=staff, args=(f"p{i}",)) for i in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs, errs[:3]
    assert want <= set(AgentRegistry(path=str(tmp_path / "agents.json")).list()), "a registration was lost on disk"
