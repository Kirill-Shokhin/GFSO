"""The children this process spawns die with it.

The server runs `claude` executors and validators, and the probe commands they run, as descendants,
and it exits by `os._exit` or by being killed. Neither took a descendant with it: measured
2026-09-22, a harness killed the server of a delegated run at its ceiling and four `opus`
validators it had started went on running, and spending, with their shells holding the workspace
and nobody left to receive their reports. A user's `gfso down` did the same.

Two mechanisms, because the platforms offer different ones:

* WINDOWS — `bind_this_process()` puts the SERVER itself in a job object that kills its members when
  its last handle closes. The handle is this process's own, so it closes however the process ends,
  a hard kill included, and every descendant joins the job inside `CreateProcess`, so none starts
  outside it. A descendant may still leave by asking to (the job allows breakaway, for the browser
  the server opens — `open_outside`); none of the server's own spawn sites asks.
* POSIX — each adopted child starts in a process group of its own and is remembered; `reap()`, run
  on every exit this process controls (`os._exit` through `exit_fn`, the app's lifespan shutdown —
  which uvicorn reaches on Ctrl-C, SIGTERM and in a --reload worker — the return of `serve`, and
  interpreter exit), kills those groups whole, and `kill_tree` takes a group whole when its call
  ends, so a leader's death does not leave its shells behind. A SIGKILL of the server runs nothing, so on POSIX that case is NOT covered:
  the orphaned groups outlive it. The parent-death signal would not close it either — it covers the
  direct child only and is cleared in everything that child forks.

Two more gaps, said rather than implied. On WINDOWS a call's own leftovers — a shell its `claude`
left running after it exited — live on until the server exits: `kill_tree` can walk the tree only
while its leader is alive. And on either platform a process that leaves on purpose (`setsid`, a
`docker run -d` container) is not a descendant any of this can see.
"""
from __future__ import annotations

import atexit
import contextlib
import ctypes
import logging
import os
import signal
import subprocess
import sys
import threading
import webbrowser

from gfso.config import mark_serving, serving, subprocess_env

if os.name == "nt":
    from ctypes import wintypes

log = logging.getLogger(__name__)

_LIVE: set[subprocess.Popen] = set()
_LOCK = threading.RLock()    # re-entrant: `adopt` may reap under it while this process is closing
_CLOSING = False             # once the SERVER reaps, nothing may start after the children were ended
# This process is the server (`bind_this_process`), so its reap is its end. Inherited by a
# `--reload` worker through the environment: uvicorn starts it in a fresh interpreter.
_SERVER = serving()
_JOB = None                      # the job handle, held for the life of this process


def bind_this_process() -> bool:
    """WINDOWS: make every descendant of this process die when it does. True when that holds."""
    global _JOB, _SERVER
    _SERVER = True
    mark_serving()
    if os.name != "nt" or _JOB is not None:
        return _JOB is not None
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    k32.SetInformationJobObject.restype = wintypes.BOOL
    k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                            wintypes.DWORD)
    k32.AssignProcessToJobObject.restype = wintypes.BOOL
    k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    k32.GetCurrentProcess.restype = wintypes.HANDLE

    class _Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _Extended(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _Basic), ("IoInfo", ctypes.c_uint64 * 6),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    job = k32.CreateJobObjectW(None, None)
    info = _Extended()
    # KILL_ON_JOB_CLOSE | BREAKAWAY_OK: a child leaves the job only when started to (`open_outside`)
    info.BasicLimitInformation.LimitFlags = 0x2000 | 0x800
    ok = bool(job) and bool(k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)))
    ok = ok and bool(k32.AssignProcessToJobObject(job, k32.GetCurrentProcess()))
    if not ok:
        log.warning(f"the children of this process will NOT die with it: job object setup failed "
                    f"(WinError {ctypes.get_last_error()})")
        return False
    _JOB = job
    return True


def open_outside(url: str) -> None:
    """Open `url` in the user's browser, OUTSIDE the job: a browser this process happened to start
    must not close with the server."""
    if os.name == "nt" and _JOB is not None:
        try:
            subprocess.Popen(["cmd", "/c", "start", "", url], creationflags=0x01000000 | 0x08000000)
            return                          # CREATE_BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW
        except OSError as e:                # an outer job that forbids breakaway
            log.warning(f"the browser opens inside the server's job and will close with it ({e})")
    webbrowser.open(url)


def spawn_kw() -> dict:
    """Extra `Popen` keywords: on POSIX a process group of its own, so `reap` can take it whole."""
    return {} if os.name == "nt" else {"start_new_session": True}


def adopt(proc: subprocess.Popen) -> subprocess.Popen:
    """Remember a started child until it ends, so an exit of this process can take it along."""
    if os.name != "nt":
        with _LOCK:
            _LIVE.add(proc)
            late = _CLOSING
        if late:                         # a worker thread spawned after the reap: end it at once
            kill_tree(proc)
    return proc


def kill_tree(proc: subprocess.Popen) -> None:
    """End a child AND what it started: its group on POSIX (whether or not the leader is alive),
    its process tree on Windows."""
    if os.name != "nt":
        _kill_group(proc.pid)
    elif proc.poll() is None:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    if proc.poll() is None:
        proc.kill()


def run(args, *, timeout: float, **kw) -> subprocess.CompletedProcess:
    """`subprocess.run` for a child of this process: adopted, in a group of its own, without the
    server's mark in its environment, and ended with its whole tree however the call ends — a
    `TimeoutExpired` still reaches the caller."""
    kw.setdefault("env", subprocess_env(keep_key=True))
    kw.setdefault("stdin", subprocess.DEVNULL)       # under `gfso mcp` stdin is the protocol pipe
    if os.name == "nt":
        kw.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    proc = adopt(subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw,
                                  **spawn_kw()))
    try:
        out, err = proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(args, proc.returncode, out, err)
    finally:
        kill_tree(proc)
        release(proc)


def release(proc: subprocess.Popen) -> None:
    """The child has ended, or was ended: stop remembering it."""
    with _LOCK:
        _LIVE.discard(proc)


def reap(closing: bool = False) -> None:
    """POSIX: kill every adopted child's process group that is still alive. Windows needs no call."""
    global _CLOSING
    with _LOCK:                      # a snapshot, not a clear: a second reap racing this one
        _CLOSING = _CLOSING or closing or _SERVER    # must still see every group (killpg repeats)
        procs = list(_LIVE)
    for p in procs:                  # the leader may be gone while its group is not
        _kill_group(p.pid)


def _kill_group(pgid: int) -> None:
    with contextlib.suppress(ProcessLookupError):         # the group is already gone: the goal
        try:
            os.killpg(pgid, signal.SIGKILL)
        except PermissionError as e:
            log.warning(f"process group {pgid} could not be ended ({e})")


def end_this_process(code: int = 0) -> None:
    """Exit NOW, children first. `os._exit` skips interpreter exit (and so `atexit`), which is the
    point — nothing waits on a worker thread — and is why the reap is done here, not left to it."""
    reap(closing=True)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


atexit.register(reap)
