"""A process the server spawns does not outlive the server.

Measured 2026-09-22: a delegated run's server was killed at its ceiling and four `opus` validators it
had started went on running and spending, with nobody left to receive what they found. On Windows
the parent is killed HARD — no exit handler runs — and its child and that child's own child must be
gone. On POSIX a hard kill is the named residue (`gfso.adapters.children`); what is pinned there is
the exit the server itself takes, `os._exit` after `reap`.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from gfso.adapters import children

GRAND = ("import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; "
         "time.sleep(60)']); print(p.pid, flush=True); time.sleep(60)")

PARENT = r"""
import os, subprocess, sys, time
from gfso.adapters import children
children.bind_this_process()
child = children.adopt(subprocess.Popen([sys.executable, "-c", GRAND], stdout=subprocess.PIPE,
                                        text=True, **children.spawn_kw()))
print(child.pid, child.stdout.readline().strip(), flush=True)
if os.name != "nt":
    time.sleep(0.5)
    children.reap()
    os._exit(0)
time.sleep(60)
""".replace("GRAND", repr(GRAND))


def _alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/fi", f"PID eq {pid}", "/nh"],
                             capture_output=True).stdout      # bytes: the console codepage varies
        return str(pid).encode() in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:                                                     # a zombie is not a live child
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return True


def test_the_servers_children_and_theirs_die_with_it():
    parent = subprocess.Popen([sys.executable, "-c", PARENT], stdout=subprocess.PIPE, text=True,
                              cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    child, grand = (int(x) for x in parent.stdout.readline().split())
    if os.name == "nt":
        assert _alive(child) and _alive(grand)
        parent.kill()                                        # hard: nothing of the parent runs
    parent.wait()
    deadline = time.time() + 10
    while time.time() < deadline and (_alive(child) or _alive(grand)):
        time.sleep(0.2)
    assert not _alive(child), "the child outlived the process that spawned it"
    assert not _alive(grand), "the child's own child outlived it"


def test_ending_a_call_ends_what_the_call_started():
    """A timed-out or finished `claude` call is ended with its own shells: killing the leader alone
    left them running (on POSIX they sat in a group nobody remembered once the leader was gone)."""
    leader = children.adopt(subprocess.Popen([sys.executable, "-c", GRAND], stdout=subprocess.PIPE,
                                             text=True, **children.spawn_kw()))
    grand = int(leader.stdout.readline())
    if os.name != "nt":                   # the leader dies first; its group must still be taken
        os.kill(leader.pid, 9)
        leader.wait()
    children.kill_tree(leader)
    children.release(leader)
    deadline = time.time() + 10
    while time.time() < deadline and _alive(grand):
        time.sleep(0.2)
    assert not _alive(grand), "the call's own child outlived the call"


LATE = r"""
import subprocess, sys, time
from gfso.adapters import children
children.bind_this_process()
children.reap()                                # the server has begun to stop
p = children.adopt(subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                    **children.spawn_kw()))
time.sleep(1)
print(p.poll() is not None, flush=True)
"""


def test_a_child_started_after_the_server_reaped_is_ended_at_once():
    """POSIX: a worker thread still running when the server reaps may start the next `claude` call
    a moment later; nothing after the reap would end it. (Windows: the job ends it with the process.)"""
    if os.name == "nt":
        pytest.skip("the job object ends it with the process on Windows")
    out = subprocess.run([sys.executable, "-c", LATE], capture_output=True, text=True,
                         cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).stdout
    assert out.strip() == "True", "a child adopted after the reap was left running"
