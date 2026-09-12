"""A reader must see the roster before a write or after it, never during.

The registry is a json file the class invites people to edit by hand and re-reads on every access,
and readers hold no lock — the `.lock` only orders writers. Written in place with a plain
`write_text`, the file is EMPTY for the length of the write: measured, 31% of concurrent reads saw
a partial file during a four-second write loop. In-process that costs only a stale snapshot. A
process killed mid-write costs everything: the shutdown path is `os._exit` a third of a second
after the request, and a truncated roster is permanent — every later load reports "delegation is
OFF", every node answers "Del is not a registered executor", and the run stalls with nothing to
point at.
"""
import json
import os
import threading
import time

import pytest
from pathlib import Path

from gfso.delegate import AgentRegistry


def test_a_concurrent_reader_never_sees_a_partial_roster(tmp_path):
    path = tmp_path / "agents.json"
    work = tmp_path / "w"
    work.mkdir()
    reg = AgentRegistry(str(path))
    for i in range(40):                      # a roster big enough that the write is not atomic by luck
        reg.register(f"exec-{i:02d}", "llm-executor", workdir=str(work))

    torn, reads, stop = [], [0], False

    def _reader():
        while not stop:
            # A BREATH between reads, deliberately. Windows refuses to move a file over one a reader
            # holds open, so four threads reading in a tight loop starve the move for ever — which
            # measures the test, not the product: the real reader is one `_load` per access, not a
            # spin. What is under test is that nothing sees HALF a roster, and the loud-refusal path
            # below is what covers the starved case.
            time.sleep(0.001)
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError:
                continue                      # the file momentarily gone is the same defect class,
            reads[0] += 1                     # but Windows `os.replace` does not expose that window
            if not raw:
                torn.append("empty")
                continue
            try:
                json.loads(raw)
            except json.JSONDecodeError:
                torn.append(raw[:40])

    threads = [threading.Thread(target=_reader, daemon=True) for _ in range(4)]
    for t in threads:
        t.start()
    for i in range(60):
        reg.register(f"exec-{i % 40:02d}", "llm-executor", workdir=str(work))
    time.sleep(0.2)
    stop = True
    for t in threads:
        t.join(timeout=2)

    assert reads[0] > 50, f"the reader did not get to look ({reads[0]} reads)"
    assert not torn, f"{len(torn)} of {reads[0]} reads saw a half-written roster: {torn[:3]}"


def test_a_write_leaves_no_temporary_behind(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    reg = AgentRegistry(str(tmp_path / "agents.json"))
    reg.register("exec-1", "llm-executor", workdir=str(work))
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []


def test_the_roster_still_says_what_was_written(tmp_path):
    """Positive control: moving the write must not change what lands in the file."""
    work = tmp_path / "w"
    work.mkdir()
    path = tmp_path / "agents.json"
    reg = AgentRegistry(str(path))
    reg.register("exec-1", "llm-executor", workdir=str(work))
    reg.register("val-1", "llm-validator", workdir=str(work))
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert set(on_disk) == {"exec-1", "val-1"}
    assert AgentRegistry(str(path)).get("val-1")["kind"] == "llm-validator"


def test_a_removal_reaches_the_file_too(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    path = tmp_path / "agents.json"
    reg = AgentRegistry(str(path))
    reg.register("exec-1", "llm-executor", workdir=str(work))
    reg.unregister("exec-1")
    assert json.loads(path.read_text(encoding="utf-8")) == {}
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


def test_the_temporary_is_named_per_process(tmp_path):
    """Two servers sharing one roster must not write through one another's temporary."""
    work = tmp_path / "w"
    work.mkdir()
    path = tmp_path / "agents.json"
    AgentRegistry(str(path)).register("exec-1", "llm-executor", workdir=str(work))
    assert str(os.getpid()) in str(Path(path).with_name(path.name + f".{os.getpid()}.tmp"))


def test_a_roster_that_cannot_be_replaced_refuses_loudly_and_damages_nothing(tmp_path, monkeypatch):
    """The move can be refused (Windows, a reader holding the destination). Swapping a silent
    corruption for a silent failure would be no repair: nothing is written, the old file stands
    intact, and the caller is told the registration did not happen."""
    work = tmp_path / "w"
    work.mkdir()
    path = tmp_path / "agents.json"
    reg = AgentRegistry(str(path))
    reg.register("exec-1", "llm-executor", workdir=str(work))
    before = path.read_text(encoding="utf-8")

    monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(PermissionError()))
    with pytest.raises(OSError, match="could not put the roster in place"):
        reg.register("exec-2", "llm-executor", workdir=str(work))

    assert path.read_text(encoding="utf-8") == before, "the roster on disk was damaged"
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")], "a temporary was left"
