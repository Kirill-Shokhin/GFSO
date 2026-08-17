#!/usr/bin/env python
"""Negative controls for the two text guards, one per class they claim to catch.

A guard that has never gone red on a planted defect is a claim, not a guard — this project has
shipped three falsely-green ones (a character-class `[–-]`, a two-byte `§?`, a literal backspace in
a heredoc), and every one was found this way rather than by reading the script.

Each control plants ONE defect, runs the guard, restores the file byte-for-byte (verified by hash)
and reports RED/GREEN against what the control expects. The four GREEN-expected controls are the
over-firing half: a guard that fires on the licensed compat shim, on the kept homographs, or on a
foreign citation is as broken as one that fires on nothing.

    python formal/scripts/nc_guards.py            # all controls
"""
from __future__ import annotations

import hashlib
import io
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# (name, file, line-anchor to append after | None = append at end, planted text, guard, expect_red)
CONTROLS = [
    ("retired STATE in the engine", "gfso/core/protocol/fsm.py",
     "\n# NC: State.REVIEW\n", "check_naming.sh", True),
    ("retired name in a UI string", "gfso/web/index.html",
     "\n<!-- NC: n.state === 'CANCELLED' -->\n", "check_naming.sh", True),
    # The FM patterns wanted the mode and the retired word ADJACENT, so the UI's own table shape —
    # `'FM-3': 'Verifiability'` — slipped between them and shipped two retired failure-mode names
    # in the page. The patterns now tolerate quotes and colons; this plants exactly that shape.
    ("a retired FM name in a table, mode and word separated", "gfso/web/index.html",
     "\n<!-- NC: 'FM-5': 'Currency' -->\n", "check_naming.sh", True),
    ("retired name in an agent-facing prompt", "gfso/mcp/prompts/validator.md",
     "\nNC: NEGLECTED\n", "check_naming.sh", True),
    ("retired name in the TLA+ table", "formal/tla/FsmTable.tla",
     '\n\\* NC: "REVIEW"\n', "check_naming.sh", True),
    ("retired name in the MCP instructions", "gfso/mcp/ORCHESTRATOR.md",
     "\nNC: CANCEL_ACK\n", "check_naming.sh", True),
    ("the code-side contract: a stale tool verb in a shipped prompt", "gfso/mcp/prompts/validator.md",
     "\nNC: reneglect\n", "check_naming.sh", True),
    # The guard listed prompt directories one by one and missed this one — and the miss shipped: the
    # decomposer's prompt still asked the model for the retired register key, so once the reader
    # stopped accepting it, a decomposition came back with an empty risk register and nothing said
    # so. The FILES list is now a glob over every .md in the package; this control is what keeps it.
    ("a retired key in the DECOMPOSER's prompt (the model's wire contract)",
     "gfso/decompose/prompts/search.md", "\nNC: neglected\n", "check_naming.sh", True),
    ("a dangling canon § in the product tree", "gfso/core/graph/metrics.py",
     "\n# NC: §99.9\n", "check_refs.sh", True),
    ("a non-ascending § range in a test docstring", "tests/test_metrics.py",
     "\n# NC: §14.4–2.1\n", "check_refs.sh", True),
    ("a fabricated result label in a tool docstring", "gfso/tools.py",
     "\n# NC: FM-9\n", "check_refs.sh", True),
    # ── over-firing controls: these must stay GREEN ──────────────────────────────────────────────
    ("the kept homographs (Signal.TIMEOUT, DoneReason.CANCELLED, action 'review')",
     "gfso/core/protocol/fsm.py",
     "\n# NC-green: Signal.TIMEOUT / DoneReason.CANCELLED / action = \"review\"\n",
     "check_naming.sh", False),
    # (The control for "a retired name inside a licensed compat block" is GONE with the block: the
    # v3.9 read-shim was removed once the migration was over, and its license came out of
    # check_naming.sh with it. A green-expected control for a license that no longer exists would
    # pass only by permitting exactly the regression the guard is now there to catch.)
    ("a foreign citation (EVIDENCE_LOG §13.3)", "gfso/engine/validation.py",
     "\n# NC-green: EVIDENCE_LOG §13.3\n", "check_refs.sh", False),
]


def run(guard: str) -> bool:
    """True = the guard is RED."""
    r = subprocess.run(["bash", guard], cwd=ROOT / "formal/scripts",
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode != 0


def refuse_while_the_server_is_working() -> str | None:
    """These controls plant defects into the REAL tree — including files the running server hashes.

    `gfso up` compares the served code's fingerprint against the tree's and restarts on a mismatch,
    so a plant that lands between those two reads is a legitimate-looking reason to kill a server
    that has paid work in flight. The plant lasts under a second and the window is small, which is
    exactly why it would be found the expensive way. Refuse instead; `gfso down` first, or run this
    when nothing is working.
    """
    try:
        sys.path.insert(0, str(ROOT))
        from gfso import serverctl
        rt = serverctl.runtime()
    except Exception:
        return None                                    # no server, no import, no risk
    if not rt:
        return None
    busy, sessions = list(rt.get("busy") or []), int(rt.get("sessions") or 0)
    if busy or sessions:
        return (f"a server is up with {sessions} session(s)"
                + (f" and work in flight ({', '.join(busy)})" if busy else "")
                + " — these controls edit the tree it fingerprints, and a reconcile would then "
                  "restart it under that work. `gfso down` first.")
    return None


def main() -> int:
    if (why := refuse_while_the_server_is_working()):
        print(f"refusing to run: {why}", file=sys.stderr)
        return 3
    failures = 0
    for name, rel, planted, guard, expect_red in CONTROLS:
        p = ROOT / rel
        original = p.open(encoding="utf-8", newline="").read()
        digest = hashlib.sha256(original.encode()).hexdigest()
        try:
            p.open("a", encoding="utf-8", newline="").write(planted)
            red = run(guard)
        finally:
            p.open("w", encoding="utf-8", newline="").write(original)
            back = hashlib.sha256(p.open(encoding="utf-8", newline="").read().encode()).hexdigest()
            if back != digest:
                print(f"FATAL: {rel} was not restored byte-for-byte — restore it by hand", file=sys.stderr)
                return 2
        ok = red == expect_red
        failures += not ok
        want = "RED" if expect_red else "GREEN"
        got = "RED" if red else "GREEN"
        print(f"{'PASS' if ok else 'FAIL'}  [{guard:<16} want {want:<5} got {got:<5}] {name}")
    print("ALL CONTROLS BEHAVE" if not failures else f"{failures} CONTROL(S) MISBEHAVED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
