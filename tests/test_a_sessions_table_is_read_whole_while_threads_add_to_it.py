"""The sessions of every project stand in one table of the server's process, and every thread of it starts sessions
into it: a removal that read it live died "dictionary changed size during iteration" — 140 times in one row, issuer
turns failed and verdicts lost (engineering, 2026-10-29). A removal reads a copy, and pops what may be gone already."""
from pathlib import Path
from types import SimpleNamespace

import gfso.adapters.execution as E
from gfso.adapters.execution import ContainerExecution


def test_a_removal_survives_a_session_started_while_it_reads(tmp_path, monkeypatch):
    base = tmp_path / "work" / "ws"
    base.mkdir(parents=True)
    ex = ContainerExecution("t", "img", None, str(tmp_path / "state"), str(base), "p")
    gone = str(tmp_path / "work" / "gone")
    stopped = []
    monkeypatch.setattr(E, "_SESSIONS", {(ex.way.container, f"{gone}/{i}"): SimpleNamespace(
        stop=lambda i=i: stopped.append(i), state=None) for i in range(3)})
    real = E._real

    def another_thread_starts_one(p):
        E._SESSIONS[(ex.way.container, f"{tmp_path}/other/{len(E._SESSIONS)}")] = SimpleNamespace(stop=None, state=None)
        return real(p)
    monkeypatch.setattr(E, "_real", another_thread_starts_one)
    monkeypatch.setattr(E.ContainerFiles, "exists", lambda self, path: False)
    ex.remove_tree(gone)
    assert sorted(stopped) == [0, 1, 2]
    assert all(not k[1].startswith(gone) for k in E._SESSIONS)
