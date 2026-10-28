"""Whether a node's place was made is the system's record, not what stands on a file system.

The transition bus asks it and must not wait on a subprocess, and a place may stand nowhere on this host (it lives where
its execution keeps it): so the place made is recorded with the project when the system makes it, dropped when the
system removes it, and read back from the record. A place made before the record existed is found once by asking
where it stands, then recorded. Real git.
"""
from __future__ import annotations

import shutil

import pytest

from gfso import workspaces as WS
from gfso.adapters.execution import LocalExecution
from gfso.core.types import HostFiles, TaskId
from tests.test_a_node_works_in_its_own_place import _plan

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="the node places are git repositories")


def _place(e, agents, tid):
    return WS._workspace(e, agents, e.graph.get_task(TaskId(tid)))


def test_a_place_the_system_made_is_read_from_its_record(tmp_path):
    e, agents, _ = _plan(tmp_path)
    w = _place(e, agents, "a")
    assert WS.node_workspace(e, agents, "a") is None
    WS._ensure_place(e, agents, e.graph.get_task(TaskId("a")), w)
    assert e.graph.setting(WS._MADE + w[1]) == "1" and WS.node_workspace(e, agents, "a") == w[1]
    LocalExecution().remove_tree(w[1])                      # …gone by another hand: the record still says made
    assert WS.node_workspace(e, agents, "a") == w[1]


def test_a_place_made_before_the_record_is_found_once_and_recorded(tmp_path, monkeypatch):
    e, agents, _ = _plan(tmp_path)
    w = _place(e, agents, "b")
    WS.W.ensure(*w, w[0])                                   # made with no record kept
    assert e.graph.setting(WS._MADE + w[1]) is None
    assert WS.made(e, w[1]) and e.graph.setting(WS._MADE + w[1]) == "1"
    monkeypatch.setattr(HostFiles, "is_dir", lambda *_: pytest.fail("asked again where it stands"))
    assert WS.made(e, w[1])
