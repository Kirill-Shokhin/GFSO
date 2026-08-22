"""The bridge a session speaks through: what it keeps so a reconnect lands on a LIVE session."""
from gfso.mcp import connect as C



def test_the_bridge_keeps_the_handshake_so_a_reconnect_has_a_live_session():
    """The reconnect existed and a whole agent-door run still died on "Session terminated".

    A reconnect opens a FRESH upstream session, and the client never sends its handshake again — it
    believes it is already initialized. So the new session was never initialized and every call
    through it failed exactly like the dead one it had just replaced (measured 2026-08-21: an entire
    run driven from the CLI mirror instead, because the agent door answered nothing for fifty
    minutes). What opens a session is kept, and replayed."""

    class _Root:
        def __init__(self, method):
            self.method = method

    class _Msg:
        def __init__(self, method):
            self.root = _Root(method)

    C._HANDSHAKE.clear()
    C._remember_handshake(_Msg("tools/call"))
    assert C._HANDSHAKE == []                      # …ordinary traffic is not a handshake
    init = _Msg("initialize")
    C._remember_handshake(init)
    C._remember_handshake(_Msg("notifications/initialized"))
    assert [m.root.method for m in C._HANDSHAKE] == ["initialize", "notifications/initialized"]
    C._remember_handshake(_Msg("initialize"))      # …a second one replaces, never appends
    assert [m.root.method for m in C._HANDSHAKE] == ["initialize"]
    C._HANDSHAKE.clear()


def test_a_call_that_will_never_be_answered_breaks_the_bridge_instead_of_hanging():
    """Two calls of the two simplest verbs in the product ate a whole session — 30 minutes each.

    The dead-session detector fires only when the server ANSWERS; after a restart the upstream can
    instead go quiet, and the client then waits out its own idle timeout (Claude Code: 1800s) with no
    progress, no error, and no way to tell "working hard" from "will never answer". Measured on the
    agent door 2026-08-22, while the same server answered HTTP in 70 ms. The bridge now times what it
    forwards and breaks — which is the rebuild-and-replay path it already has."""
    class _Msg:
        def __init__(self, rid):
            self.message = type("M", (), {"root": type("R", (), {"id": rid})()})()

    assert C._request_id(_Msg(7)) == 7
    assert C._request_id(object()) is None                # a notification carries no id

    # …and the cap is well under any client's idle timeout: the point is a legible failure, not
    # outlasting a slow verb (the long ones stream progress, which clears the pending entry).
    assert 0 < C._CALL_TIMEOUT_S <= 300
