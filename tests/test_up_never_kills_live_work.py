"""`gfso up` reconciles an idle server and leaves a busy one alone — and the SERVER enforces it.

The standing rule: a newly declared state applies to the NEXT start, it does not take down work in
flight. Lived from both ends. The product tree was edited while a run was executing, so every MCP
reconnect saw a code drift and shut the engine down underneath it, and the run died on a refused
connection with hours of paid work behind it. And keeping the rule in the reconciler alone was not
enough — a client holds its own code in memory, so an older `gfso up` resident on a long-lived
session bridge went on restarting the server, and no fix shipped to the client could reach it.
"""
import gfso.mcp.connect as C
from gfso import serverctl


def _stub(monkeypatch, runtime: dict, calls: list):
    monkeypatch.setattr(serverctl, "runtime", lambda *a, **k: runtime)
    monkeypatch.setattr(serverctl, "declared", lambda: {"GFSO_VALIDATE_INTERNAL": "1"})
    monkeypatch.setattr(serverctl, "source_fingerprint", lambda: "NEW")
    monkeypatch.setattr(serverctl, "drift", lambda *a, **k: ["code OLD != tree NEW"])
    monkeypatch.setattr(C, "ensure_server", lambda *a, **k: calls.append("spawn") or True)


class _FakeResp:
    """Stands in for the stop call's response — a unit test never touches the one live address."""
    def read(self):
        return b"{}"


def test_a_drifted_server_with_other_sessions_is_left_alone(monkeypatch):
    calls: list = []
    _stub(monkeypatch, {"code_version": "OLD", "sessions": 2, "busy": []}, calls)
    out = C.ensure_correct(verbose=False)
    assert out["action"] == "left-alone"
    assert calls == [], "the reconciler restarted a server other sessions were on"


def test_work_in_flight_is_enough_on_its_own(monkeypatch):
    """No other session need hold a lease: a tool still running IS somebody's work."""
    calls: list = []
    _stub(monkeypatch, {"code_version": "OLD", "sessions": 1, "busy": ["root:validate_result"]}, calls)
    out = C.ensure_correct(verbose=False, holds_lease=True)
    assert out["action"] == "left-alone" and calls == []


def test_a_drifted_IDLE_server_is_still_reconciled(monkeypatch):
    """The rule protects work, not staleness: with nobody on it, drift is fixed as before."""
    # The reconciler exports the declared switches into ITS OWN process before spawning, so without
    # this the test leaks `GFSO_VALIDATE_INTERNAL=1` into every test that runs after it — which is
    # exactly how it first broke a neighbour. `setenv` restores what was there before, whatever the
    # code under test does to it.
    for k in ("GFSO_VALIDATE_INTERNAL", "GFSO_AUTOEXIT"):
        monkeypatch.setenv(k, "0")
    calls: list = []
    _stub(monkeypatch, {"code_version": "OLD", "sessions": 0, "busy": []}, calls)
    # The stop is a REAL HTTP call to the one address, and this test used to make it: with a live
    # server on :8000 the suite sent it a forced shutdown and killed whatever was running there —
    # measured, on a paid E3 run. A unit test may not reach the network; the call is captured here
    # and asserted on instead.
    stops: list = []
    import urllib.request as _ur          # the reconciler imports it inside the function
    monkeypatch.setattr(_ur, "urlopen",
                        lambda req, timeout=None: stops.append(req) or _FakeResp())
    monkeypatch.setattr(C, "_port_open", lambda *a, **k: False)   # the graceful stop took effect
    monkeypatch.setattr(C, "foreign_holder", lambda *a, **k: False)
    out = C.ensure_correct(verbose=False)
    assert out["action"] == "restarted" and calls == ["spawn"]
    assert len(stops) == 1 and stops[0].data in (b"{}", b'{}'),         "a routine reconcile must not FORCE a stop — force overrides the server's own refusal"


def test_the_server_itself_refuses_an_unforced_stop_while_clients_work():
    """The one party that cannot be out of date about itself."""
    from fastapi.testclient import TestClient
    from gfso.api.server import create_app
    from tests.test_integration import _engine

    app = create_app(_engine())
    with TestClient(app) as c:
        c.post("/api/lease", json={"id": "arm:run-1"})
        refused = c.post("/api/shutdown", json={})
        assert refused.status_code == 409 and "arm:run-1" in refused.json()["detail"]
        assert c.get("/api/runtime").json()["sessions"] == 1


def test_the_server_is_spawned_with_a_hidden_console_not_without_one(monkeypatch, tmp_path):
    """The window class, closed at its root instead of a fourth time at a spawn site.

    On Windows a console child of a console-LESS parent allocates its own console, which the default
    host shows as a window. The server used to be spawned DETACHED (no console), so every descendant
    we do not control — notably the claude CLI starting its stdio MCP server — popped one. Measured
    with a probe over visible top-level windows: console-less parent → 2 new windows per uncontrolled
    grandchild, hidden-console parent → 0. CREATE_NO_WINDOW at our own spawn sites cannot cover it:
    the flag is not inherited, which is why this recurred each time a new spawn appeared."""
    import os
    import subprocess
    import pytest

    if os.name != "nt":
        pytest.skip("console semantics are Windows-only")

    from gfso.mcp import connect

    seen = {}

    class _P:
        def __init__(self, args, **kw):
            seen["flags"] = kw.get("creationflags")
            seen["si"] = kw.get("startupinfo")

    monkeypatch.setattr(connect.subprocess, "Popen", _P)
    monkeypatch.setattr(connect, "_port_open", lambda h, p: False)
    # …and into a temp HOME: `ensure_server` opens the installation's `data/server.log` for append,
    # and a unit test has no business writing into the user's live state.
    monkeypatch.setenv("GFSO_HOME", str(tmp_path))
    connect.ensure_server("http://127.0.0.1:8000/mcp", wait_s=0.0)

    CREATE_NEW_CONSOLE, DETACHED_PROCESS = 0x00000010, 0x00000008
    assert seen["flags"] & CREATE_NEW_CONSOLE, "the server needs a console of its own"
    assert not (seen["flags"] & DETACHED_PROCESS), "a console-LESS server re-opens the window class"
    assert seen["si"] is not None and seen["si"].dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert seen["si"].wShowWindow == 0, "the console must be hidden (SW_HIDE)"


def test_a_stop_that_did_not_take_is_not_reported_as_a_restart(monkeypatch):
    """`restarted` is a claim about an act. When the stop does not take — a client refused it, the
    request never arrived — nothing was restarted and the drift still stands; saying otherwise tells
    the caller it is talking to current code when it is not."""
    import os

    for k in ("GFSO_VALIDATE_INTERNAL", "GFSO_AUTOEXIT"):
        monkeypatch.setenv(k, "0")
    calls: list = []
    _stub(monkeypatch, {"code_version": "OLD", "sessions": 0, "busy": []}, calls)
    import urllib.request as _ur
    monkeypatch.setattr(_ur, "urlopen", lambda req, timeout=None: _FakeResp())
    monkeypatch.setattr(C, "_port_open", lambda *a, **k: True)      # the server is still there
    out = C.ensure_correct(verbose=False)
    assert out["action"] == "left-alone" and calls == [], "it claimed a restart that did not happen"
