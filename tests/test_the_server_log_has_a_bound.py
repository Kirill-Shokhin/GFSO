"""The server's log is bounded, and the one door that opens it uses the bounded opener.

Measured on a developer installation before this existed: `data/server.log` had grown to 61 MB over
nine weeks and nothing in the product would ever have stopped it — it was opened for append at every
start and never rotated. For someone who installed `gfso` from PyPI that is the one file the product
writes to their disk without end, so the bound is a property of the product, not a chore for whoever
notices.
"""
from __future__ import annotations

import pathlib

from gfso import serverctl


def test_a_log_under_the_bound_is_appended_to_not_rotated(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "server.log").write_text("first start\n", encoding="utf-8")
    with serverctl.open_server_log(data, max_bytes=1024) as fh:
        fh.write("second start\n")
    assert (data / "server.log").read_text(encoding="utf-8") == "first start\nsecond start\n", (
        "a log inside its bound must keep what it had — rotating every start loses the run that "
        "just failed, which is the run a reader opens the log for")
    assert not (data / "server.log.1").exists()


def test_a_log_past_the_bound_is_rotated_and_the_new_one_starts_empty(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "server.log").write_text("x" * 2048, encoding="utf-8")
    with serverctl.open_server_log(data, max_bytes=1024) as fh:
        fh.write("after\n")
    assert (data / "server.log").read_text(encoding="utf-8") == "after\n"
    assert (data / "server.log.1").read_text(encoding="utf-8") == "x" * 2048, (
        "the previous generation is kept: a server that died mid-write leaves its reason there")


def test_only_one_generation_is_kept(tmp_path):
    """Two rotations must not leave three files — the bound is on the INSTALLATION, not per run."""
    data = tmp_path / "data"
    data.mkdir()
    for gen in ("one", "two"):
        (data / "server.log").write_text(gen * 1024, encoding="utf-8")
        serverctl.open_server_log(data, max_bytes=1024).close()
    assert sorted(p.name for p in data.iterdir()) == ["server.log", "server.log.1"]
    assert (data / "server.log.1").read_text(encoding="utf-8").startswith("two")


def test_the_door_that_spawns_the_server_uses_the_bounded_opener():
    """`connect.py` is the one place that opens this file; a second `open(..., "a")` re-opens the
    defect silently, so the source is asserted rather than the behaviour of a spawn."""
    src = (pathlib.Path(serverctl.__file__).parent / "mcp" / "connect.py").read_text(encoding="utf-8")
    assert "serverctl.open_server_log(data)" in src
    assert '"server.log", "a"' not in src and "'server.log', 'a'" not in src
