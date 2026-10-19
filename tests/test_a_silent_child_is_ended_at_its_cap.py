"""A model call is ended at its cap whether or not the child speaks.

The cap was checked only as a line of the stream arrived, so a child that goes silent holds the read past any cap —
only the node's own state bound (T_validate, §12.2) ends the wait around it. Seen as a root validation that stood
340 minutes with no answer across a sleep of the machine (AUTO json_parser, 2026-09-28).
"""
import subprocess
import sys
import time

from gfso.adapters.llm.headless import HeadlessClaudeLLM


def test_a_child_that_writes_nothing_is_killed_at_the_cap():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdout=subprocess.PIPE, text=True)
    llm = HeadlessClaudeLLM()
    t0 = time.monotonic()
    envelope, text, _ = llm._read_stream(proc, t0, 2)
    assert time.monotonic() - t0 < 20, "the read ended near its cap, not when the child chose to"
    assert envelope is None and text == []
    assert proc.wait(timeout=10) is not None
