"""On Windows a file another process holds for a moment refuses its delete. Raised midway, it left a place half gone with the
system's record still saying it stands, and a reopened root worked in what was left of it."""
import os

import pytest

from gfso.adapters import execution as X


def _place(tmp_path):
    a = tmp_path / "place" / ".git" / "hooks"
    a.mkdir(parents=True)
    (a / "held").write_text("x", encoding="utf-8")
    return tmp_path / "place"


def _held(monkeypatch, times):
    real, refused = os.unlink, []

    def unlink(p, *a, **k):
        if str(p).endswith("held") and len(refused) < times:
            refused.append(p)
            raise PermissionError(13, "held by another process", str(p))
        return real(p, *a, **k)
    monkeypatch.setattr(os, "unlink", unlink)
    monkeypatch.setattr(X.time, "sleep", lambda s: None)
    return refused


def test_a_lock_that_passes_does_not_leave_the_place_half_gone(tmp_path, monkeypatch):
    place, refused = _place(tmp_path), _held(monkeypatch, 2)
    X.LocalExecution().remove_tree(str(place))
    assert not place.exists() and len(refused) == 2


def test_a_lock_that_stays_is_still_reported(tmp_path, monkeypatch):
    """The caller keeps the place on the record only because this raises."""
    place = _place(tmp_path)
    _held(monkeypatch, 10 ** 6)
    with pytest.raises(OSError):  # Python 3.13's rmtree on Linux reports it as the directory left not empty
        X.LocalExecution().remove_tree(str(place))
