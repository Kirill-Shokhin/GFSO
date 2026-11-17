"""A bridge that left a stale server alone (other sessions on it) said so, then printed "server reconciled" — a restart
that never happened (2026-11-14: :8000 stayed on its code while the line claimed a new one).

CONTROL: drop the `left-alone` condition in `connect._tell` and the first test goes red."""
from gfso.mcp import connect


def test_a_server_left_alone_is_not_called_reconciled(capsys):
    connect._tell({"action": "left-alone", "drift": ["code a != tree b"], "why": "3 other sessions"})
    assert "reconciled" not in capsys.readouterr().err


def test_a_restarted_server_is_said_reconciled(capsys):
    connect._tell({"action": "restarted", "drift": ["code a != tree b"]})
    assert "server reconciled (code a != tree b)" in capsys.readouterr().err
