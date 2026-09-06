"""`use_project` fell back to `default` after a restart, and said nothing about it.

MCP door, wave 26 (2026-09-06). The mechanism: a session's project lives in memory keyed by the MCP
session object, and a restart gives every reconnecting client a NEW session — so the fallback is the
registry's active project, and the registry started every process at `default` regardless of where
the work had been. Everything the caller then did landed in another graph, silently, which is the
worst shape a scope defect can take.

What is remembered is the SWITCH, not the session: `use_project` writes the name down, and a new
process starts where the last one was pointed. `GFSO_PROJECT` still wins — an explicit environment is
a deployment saying where it points, and a remembered choice must not override it.
"""
from __future__ import annotations

import gfso.config as config
from gfso.config import DEFAULT_PROJECT, active_project, remember_active_project


def test_a_fresh_process_starts_where_the_last_switch_left_it(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)

    assert active_project() == DEFAULT_PROJECT, "nothing chosen yet — `default` is right"

    remember_active_project("w26-ui")

    assert active_project() == "w26-ui", (
        "this is the restart: a new process reading the same data dir, with no memory of any "
        "session — it used to answer `default` and let the caller work in the wrong graph")


def test_an_explicit_environment_still_wins(tmp_path, monkeypatch):
    """The negative control: a deployment that names its project must not inherit a stale choice."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    remember_active_project("w26-ui")
    monkeypatch.setenv("GFSO_PROJECT", "the-deployment-says-this-one")

    assert active_project() == "the-deployment-says-this-one"


def test_an_unwritable_data_dir_does_not_break_the_switch(tmp_path, monkeypatch):
    """Remembering is best-effort: losing the memory is a cost, refusing the switch is a defect."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path / "nested"))
    monkeypatch.delenv("GFSO_PROJECT", raising=False)
    monkeypatch.setattr(config, "data_dir", lambda: (_ for _ in ()).throw(OSError("read-only")))

    remember_active_project("w26-ui")          # must not raise
    assert active_project() == DEFAULT_PROJECT  # …and a data dir it cannot read is not a crash
