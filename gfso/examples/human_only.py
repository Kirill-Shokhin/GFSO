"""Human-only: the whole protocol with ZERO AI — and the gate that makes it honest.

Two humans: `ann` issues and executes, `bob` reviews. The engine REJECTS ann's PASS on her own
work until an independent verdict is RECORDED (verifier ≠ executor, §14.5) — the same flow the
web UI drives with the Pass/Fail/Record-verdict buttons."""
from gfso.examples import scratch
from gfso.engine import Engine
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.adapters.agents.human import HumanAgent
from gfso import tools as T


def main() -> None:
    db = scratch("demo.db")
    store = SqliteStorage(db)
    e = Engine(store, HumanAgent(), llm=None, validate_signals=True, state_timeout=0)
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

    # Bob says WHAT HE CHECKED, one line per criterion. A verdict is a claim about the world, and
    # the human door asks for the same thing as the machine one — at human grade: a sentence rather
    # than a re-runnable command. With no independent seam this record IS the guarantee (§14.5).
    print(T.record_verdict(e, "report", "PASS", reviewer="bob", observed={
        "numbers": "totals tie to the ledger export, row by row",
        "sent": "board thread shows it delivered at 09:02"}))
    print("after bob's record:", T.signal(e, "report", "PASS", "ann"))  # now the PASS lands

    print("final:", e.get_state(T.TaskId("report")).name)
    e.stop()
    store.close()   # Windows keeps the .db locked until the connection closes


# Importing a module must not RUN it. Without this guard the script body executed on import,
# so anything that walks the package tree — an IDE indexer, a doc tool, a naive test
# collection, `from gfso.examples.x import y` — ran the example; for the two that spawn
# models that meant real tokens off the reader's account and, for one, an endless loop.
if __name__ == "__main__":
    main()
