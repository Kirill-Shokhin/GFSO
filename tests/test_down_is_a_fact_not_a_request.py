"""`gfso down` returns when the server is actually gone, not when it agreed to go.

The stop is asynchronous — the server answers the request and then exits — so `down` followed by `up`
raced it: the second command reached the dying process, read its runtime, saw a session still on it
and declined to restart. The operator was left with a server that was neither stopped nor current,
and the only clue was a decline message about a session that no longer existed.
"""
from __future__ import annotations

import gfso.cli as C
import gfso.serverctl as S


def test_down_waits_for_the_port_to_close(monkeypatch, capsys):
    class _Resp:
        def read(self):
            return b'{"ok": true, "bye": true}'

    monkeypatch.setattr(C.__dict__.get("urllib", __import__("urllib.request", fromlist=["request"])),
                        "urlopen", lambda *a, **k: _Resp(), raising=False)
    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", lambda *a, **k: _Resp())

    # open for the first few probes, then gone — the shape of a graceful exit
    probes = {"n": 0}

    def _port_open(host="127.0.0.1", port=None, timeout=0.5):
        probes["n"] += 1
        return probes["n"] < 4

    monkeypatch.setattr(S, "port_open", _port_open)
    C._down()
    out = capsys.readouterr().out
    assert "server stopping" in out
    assert probes["n"] >= 4, "down returned while the port was still open"
    assert "still answering" not in out


def test_a_server_that_will_not_die_is_reported(monkeypatch, capsys):
    """Silence here would be the worse failure: the next command would decline for a reason the
    operator cannot see, exactly as it did."""
    class _Resp:
        def read(self):
            return b'{"ok": true}'

    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", lambda *a, **k: _Resp())
    monkeypatch.setattr(S, "port_open", lambda host="127.0.0.1", port=None, timeout=0.5: True)
    C._down()
    assert "still answering" in capsys.readouterr().out


def test_a_server_that_died_between_the_read_and_the_decision_does_not_veto_its_replacement(monkeypatch):
    """The load-bearing half — and it is not in `down` at all.

    The reconciler reads `/api/runtime` ONCE and decides from that snapshot, so a server that was
    exiting when it answered got to veto its own replacement with a session that left with it.
    Waiting inside `down` hides the case it was measured on and leaves every other one: a crash, a
    kill, an operator closing the window between the read and the decision have the same shape.
    """
    import gfso.mcp.connect as C

    reads = {"n": 0}

    def _runtime(*a, **k):
        reads["n"] += 1
        # first read: alive, drifted, somebody on it — the reason to decline
        # second read (the re-probe): gone
        return {"code_version": "OLD", "sessions": 1, "busy": []} if reads["n"] == 1 else None

    monkeypatch.setattr(S, "runtime", _runtime)
    monkeypatch.setattr(S, "source_fingerprint", lambda *a, **k: "NEW")
    monkeypatch.setattr(S, "declared", lambda *a, **k: {})
    monkeypatch.setattr(S, "drift", lambda *a, **k: ["code OLD != tree NEW"])
    monkeypatch.setattr(S, "port_open", lambda *a, **k: False)
    monkeypatch.setattr(C, "_port_open", lambda *a, **k: False)
    monkeypatch.setattr(C, "foreign_holder", lambda *a, **k: False)
    spawned: list = []
    monkeypatch.setattr(C, "ensure_server", lambda *a, **k: spawned.append("spawn") or True)

    out = C.ensure_correct(verbose=False)
    assert out["action"] != "left-alone", "a departed server still vetoed the reconcile"
    assert spawned == ["spawn"], "nothing was started in its place"
