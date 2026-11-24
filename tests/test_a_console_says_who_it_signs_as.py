"""`gfso whoami`: the name a console's calls sign as, read from the live server by that console's own credential — for a
status line, so it prints one word or nothing, and never an error."""
from __future__ import annotations

import io
import json
import urllib.request

import gfso.cli as CLI


def _answers(monkeypatch, body):
    asked = []

    def urlopen(req, timeout):
        asked.append(req)
        if isinstance(body, Exception):
            raise body
        return io.BytesIO(json.dumps(body).encode())
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(CLI.signin, "credential_header", lambda: {"X-Gfso-Lease": "the-console's"})
    return asked


def test_the_name_its_connection_took_by_its_own_credential(monkeypatch, capsys):
    asked = _answers(monkeypatch, {"name": "engineering", "signs_as": ["engineering"]})
    assert CLI._whoami(None) == 0 and capsys.readouterr().out.strip() == "engineering"
    assert asked[0].full_url.endswith("/api/whoami") and asked[0].get_header("X-gfso-lease") == "the-console's"


def test_a_connection_that_took_no_name_says_so(monkeypatch, capsys):
    _answers(monkeypatch, {"name": "user", "signs_as": []})
    assert CLI._whoami(None) == 0 and capsys.readouterr().out.strip() == "—"


def test_no_server_prints_nothing(monkeypatch, capsys):
    _answers(monkeypatch, OSError("refused"))
    assert CLI._whoami(None) == 2 and capsys.readouterr().out == ""


def test_no_credential_of_its_console_prints_nothing_and_asks_no_one(monkeypatch, capsys):
    asked = _answers(monkeypatch, {"name": "user", "signs_as": []})
    monkeypatch.setattr(CLI.signin, "credential_header", lambda: {})
    assert CLI._whoami(None) == 2 and capsys.readouterr().out == "" and asked == []
