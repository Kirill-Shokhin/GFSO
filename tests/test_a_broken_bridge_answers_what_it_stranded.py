"""A call in flight when the bridge breaks is answered, not left waiting.

Reproduced 2026-09-02 by restarting the server under a live bridge, which is the ordinary way to put
it on new code: a free read through the already-open bridge never returned and had to be killed,
while `curl` answered the same server instantly from a fresh process. The bridge's own healing works —
a watchdog breaks the leg and the relay is rebuilt — but the request id went with the old session, so
the CLIENT went on waiting for a reply that nobody would ever send. A wave reported it as a
thirty-minute hang on a call whose work had already finished.
"""
import anyio
import pytest

from gfso.mcp.connect import _answer_the_orphans


class _Stream:
    def __init__(self, fails=False):
        self.sent, self._fails = [], fails

    async def send(self, msg):
        if self._fails:
            raise ConnectionError("the stdio leg is gone too")
        self.sent.append(msg)


def test_every_stranded_call_gets_an_error_carrying_its_own_id():
    pending = {1: 0.0, "abc": 0.0}
    out = _Stream()
    n = anyio.run(_answer_the_orphans, out, pending, "the server restarted")
    assert n == 2 and pending == {}, "the ids are answered and the register is cleared"
    ids = [m.message.root.id for m in out.sent]
    assert sorted(map(str, ids)) == ["1", "abc"]
    assert all(m.message.root.error.message == "the server restarted" for m in out.sent)


def test_a_dead_stdio_leg_ends_the_attempt_instead_of_raising():
    """Nothing left to answer to is not an error — the bridge is going down either way."""
    pending = {1: 0.0}
    assert anyio.run(_answer_the_orphans, _Stream(fails=True), pending, "gone") == 0
