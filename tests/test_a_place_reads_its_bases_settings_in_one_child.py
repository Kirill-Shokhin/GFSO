"""A node's own repository takes on its base's local settings (`worktrees.INHERITED`), read in ONE git child: a read per
key was five children for every place the system makes — in the suite's site map the most frequent git call of a
simulated delivery (2026-11-27).

CONTROL: read each key with its own `config --get` and the count test goes red; drop a key's value and the first does."""
from __future__ import annotations

import subprocess

from gfso.adapters import worktrees as W


def _base(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for k, v in (("core.eol", "lf"), ("core.symlinks", "false"), ("core.autocrlf", "input"), ("user.name", "x")):
        subprocess.run(["git", "-C", str(tmp_path), "config", k, v], check=True)
    return tmp_path


def test_the_settings_read_are_the_bases_own(tmp_path):
    base = _base(tmp_path)
    each = {k: v for k in W.INHERITED if (v := subprocess.run(["git", "-C", str(base), "config", "--local", "--get", k],
                                                               capture_output=True, text=True).stdout.strip())}
    assert W.inherited(base, None) == each and each["core.eol"] == "lf" and each["core.autocrlf"] == "input", each
    assert "user.name" not in W.inherited(base, None)


def test_they_are_read_in_one_git_child(tmp_path, monkeypatch):
    base, calls, git = _base(tmp_path), [], W.git
    monkeypatch.setattr(W, "git", lambda *a, **k: calls.append(a) or git(*a, **k))
    W.inherited(base, None)
    assert len(calls) == 1, calls
