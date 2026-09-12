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
    """Run the demo: the whole protocol with zero AI, including the refusal that makes it honest.

    The load-bearing moment is the engine REJECTING the issuer's PASS on her own work until an
    independent verdict is on the record.
    """
    db = scratch("demo.db")
    store = SqliteStorage(db)
    e = Engine(store, HumanAgent(), llm=None, validate_signals=True, state_timeout=0)
    e.start()

    T.create_task(e, "report", {
        "description": "Quarterly report",
        # Each criterion carries the procedure that decides it (A1, §10) — written with the
        # criterion and before the work, so nobody has to invent one while judging. A human-grade
        # procedure is still a procedure: it says what to open and what it must show.
        "criteria": [{"name": "numbers", "description": "figures match the ledger",
                      "check": [{"behaviour": "every figure ties to the ledger export",
                                 "command": "open report.pdf beside the Q3 ledger export and "
                                            "compare each total row by row",
                                 "expect": "every row matches; no unexplained difference"}]},
                     {"name": "sent", "description": "mailed to the board",
                      "check": [{"behaviour": "the board received it",
                                 "command": "search the sent folder for the board thread",
                                 "expect": "a sent message to the board list with report.pdf"}]}],
    }, assignee="ann")

    T.signal(e, "report", "ACCEPT", "ann")
    T.signal(e, "report", "DELIVER", "ann", result="report.pdf; figures cross-checked; mailed 09:00")

    blocked = T.signal(e, "report", "PASS", "ann")
    print("ann's self-PASS accepted?", blocked["accepted"], "—", blocked.get("error", "")[:80])

    # Bob says WHAT HE CHECKED, one line per criterion. A verdict is a claim about the world, and
    # the human door asks for the same thing as the machine one — at human grade: a sentence rather
    # than a re-runnable command. With no independent seam this record IS the guarantee (§14.5).
    print(T.record_verdict(e, "report", "PASS", reviewer="bob", observed={
        # …and WHICH of the pinned checks he actually ran. Not a command he had to invent: the
        # contract already said what to do, and he names the one he did.
        "numbers": {"note": "totals tie to the ledger export, row by row",
                    "ran": ["open report.pdf beside the Q3 ledger export and compare each total "
                            "row by row"]},
        "sent": {"note": "board thread shows it delivered at 09:02",
                 "ran": ["search the sent folder for the board thread"]}}))
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
