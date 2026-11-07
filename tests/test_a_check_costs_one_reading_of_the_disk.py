"""A directory the system made now is empty, read not at all, and one inside an older root does not charge what stood
there; a check's own root is measured by its one write (a simple task's 47 checks spent 6:08 on ten readings each,
rehearsal 2026-11-03).

CONTROLS: baseline an inner directory's root at nothing and the older root is charged whole; measure a new root at nothing
and it reads a baseline it never had."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from gfso.adapters import execution as E

V = "vol"


@pytest.fixture
def disk(monkeypatch, tmp_path):
    """A volume over a dictionary of what each subpath holds, each reading noted."""
    held, reads = {}, []

    def read(vol, subs, image=None):
        reads.append(subs)
        return {(vol, s): held[s] for s in subs if s in held}
    monkeypatch.setattr(E, "_read", read)
    monkeypatch.setattr(E, "_LEDGER", E.DiskLedger())
    monkeypatch.setattr(E, "_BEFORE", {})
    monkeypatch.setattr(E, "_real", lambda p: Path(p))
    v = E.Volume.__new__(E.Volume)
    v.image = None
    v.key = lambda d: (V, "r")
    host = E._SystemWrites.__new__(E._SystemWrites)
    host.volume = v
    return SimpleNamespace(v=v, host=host, root=tmp_path / "r", at=(V, "r"), held=held, reads=reads)


def charged(disk):
    E._LEDGER.begin()
    return E._LEDGER.added({"w": {"dirs": [disk.at], "layers": {}}}, {disk.at: disk.held["r"]})["w"]


def test_a_new_root_written_once_is_read_once_and_charges_nothing(disk):
    with disk.v.writes(disk.root):
        disk.held["r"] = (1500, 15)
    assert disk.reads == [["r"]] and charged(disk) == (0, 0)
    disk.held["r"] = (1500 + 700, 15 + 7)
    assert charged(disk) == (700, 7), "what the check writes after is its own"


def test_a_root_made_now_has_its_baseline_with_no_reading(disk, monkeypatch):
    monkeypatch.setattr(E, "_writable_root", lambda p, x: p)
    disk.host.system_made(str(disk.root))
    assert disk.reads == [] and E._LEDGER.base[disk.at] == (0, 0)


def test_a_directory_made_inside_a_root_older_than_this_server_does_not_charge_what_stood_there(disk, monkeypatch):
    disk.held["r"] = (5000, 50)
    monkeypatch.setattr(E, "_writable_root", lambda p, x: disk.root)
    disk.host.system_made(str(disk.root / "sub"))
    assert E._LEDGER.base[disk.at] == (5000, 50) and charged(disk) == (0, 0)
