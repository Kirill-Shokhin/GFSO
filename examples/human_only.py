"""Human-only: the whole protocol with ZERO AI — and the gate that makes it honest.

Two humans: `ann` issues and executes, `bob` reviews. The engine REJECTS ann's PASS on her own
work until an independent verdict is RECORDED (verifier ≠ executor, §6.5) — the same flow the
web UI drives with the Pass/Fail/Record-verdict buttons."""
import tempfile

from gfso.engine import Engine
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.adapters.agents.human import HumanAgent
from gfso import tools as T

db = tempfile.mktemp(suffix=".db")
e = Engine(SqliteStorage(db), HumanAgent(), llm=None, validate_signals=True, state_timeout=0)
e.start()

T.create_task(e, "report", {
    "description": "Quarterly report",
    "criteria": [{"name": "numbers", "description": "figures match the ledger"},
                 {"name": "sent", "description": "mailed to the board"}],
}, assignee="ann")

T.signal(e, "report", "ACCEPT", "ann")
T.signal(e, "report", "DELIVER", "ann", result="report.pdf; figures cross-checked; mailed 09:00")

blocked = T.signal(e, "report", "PASS", "ann")
print("ann's self-PASS accepted?", blocked["accepted"], "—", blocked.get("error", "")[:80])

print(T.record_verdict(e, "report", "PASS", reviewer="bob"))        # the independent record
print("after bob's record:", T.signal(e, "report", "PASS", "ann"))  # now the PASS lands

print("final:", e.get_state(T.TaskId("report")).name)
e.stop()
