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
import time
import webbrowser
import weakref

from gfso.config import browser as _browser, mark_serving, serving, subprocess_env, windows_allowed

if os.name == "nt":
    from ctypes import wintypes

log = logging.getLogger(__name__)

_LIVE: set[subprocess.Popen] = set()
#: the `shown` children: in the terminal's own session, leading no group their pid could name
_IN_THE_TERMINAL: "weakref.WeakSet[subprocess.Popen]" = weakref.WeakSet()
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


# ── THE ONE DOOR to the person's screen: a page, a console, an app — each read `windows_allowed` here and nowhere else.
# Four places opened windows on their own, so each measurement on an owner's busy screen found one more (2026-11-16).

_NEW_CONSOLE = 0x10                 # CREATE_NEW_CONSOLE

def open_outside(url: str) -> None:
    """Open `url` in the user's browser, OUTSIDE the job: a browser this process happened to start
    must not close with the server. A `BROWSER` the person set is what opens it, as `webbrowser` itself honours: the
    page opened at the go went past it through `start`, onto a screen whose owner had said where links go (2026-11-16)."""
    if not windows_allowed():
        log.info(f"the page is not opened (GFSO_NO_WINDOWS): {url}")
        return
    if _browser():
        webbrowser.open(url)                # it reads BROWSER as every tool does: a list, `%s` in a command
        return
    if os.name == "nt" and _JOB is not None:
        try:
            subprocess.Popen(["cmd", "/c", "start", "", url], creationflags=0x01000000 | 0x08000000)
            return                          # CREATE_BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW
        except OSError as e:                # an outer job that forbids breakaway
            log.warning(f"the browser opens inside the server's job and will close with it ({e})")
    webbrowser.open(url)


def console(argv: list) -> bool:
    """Start `argv` in a console window of its own on Windows, for the person to work in (the sign-in pastes a token
    there); with no windows allowed it is not started — run hidden, it waited at a prompt nobody could see. True: it
    was started; False: the caller says the steps instead."""
    if not windows_allowed():
        log.info(f"not started (GFSO_NO_WINDOWS): {' '.join(map(str, argv))}")
        return False
    subprocess.Popen(argv, creationflags=_NEW_CONSOLE)
    return True


def app(argv: list, timeout: float) -> bool:
    """Run `argv`, which brings up an application of the person's (Docker Desktop), waiting at most `timeout`; with no
    windows allowed it is not run. True: it ran and said so (exit 0); False: the caller asks the person instead."""
    if not windows_allowed():
        log.info(f"not started (GFSO_NO_WINDOWS): {' '.join(map(str, argv))}")
        return False
    return run(argv, timeout=timeout).returncode == 0


def detached(argv: list, out, **kw) -> None:
    """Start `argv` to outlive this process (the shared server, a build longer than its caller's shell call), its output
    to `out`. On Windows in a console of its own that nobody sees: started with none, it and every console program it
    starts in turn would ALLOCATE one and show it (measured over visible top-level windows: 2 per uncontrolled grandchild
    of a console-less parent, 0 under a hidden console, whose descendants attach to it)."""
    if os.name == "nt":
        kw.update(creationflags=_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP, startupinfo=_unseen())
    else:
        kw.update(start_new_session=True)
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=out, **kw)


def _unseen():
    """Windows: a window started hidden (SW_HIDE)."""
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return si


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
        if proc not in _IN_THE_TERMINAL:                   # …a `shown` child leads no group: its pid names none
            _kill_group(proc.pid)
    elif proc.poll() is None:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    if proc.poll() is None:
        proc.kill()


def popen(args, shown: bool = False, **kw) -> subprocess.Popen:
    """A child this process holds while it runs (`end` takes it): adopted, in a group of its own, without the system's
    switches in its environment unless the caller gives them (`config.subprocess_env`), and with no console window — on Windows a console child of a parent with none (the server)
    ALLOCATES one and shows it: every agent run popped an empty, closable `claude` window on the person's screen.
    `shown` (`run`): a program the person works in stays in the terminal's session, where its Ctrl-C reaches it."""
    kw.setdefault("env", subprocess_env())
    if os.name == "nt":
        kw.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    proc = subprocess.Popen(args, **kw, **({} if shown else spawn_kw()))
    if shown:
        _IN_THE_TERMINAL.add(proc)
    return adopt(proc)


def end(proc: subprocess.Popen) -> None:
    """End a child `popen` started, with what it started, and stop remembering it."""
    kill_tree(proc)
    release(proc)


def run(args, *, timeout: float | None, input=None, shown: bool = False, **kw) -> subprocess.CompletedProcess:
    """`subprocess.run` for a child of this process (`popen`), ended with its whole tree however the call ends — a
    `TimeoutExpired` still reaches the caller. `input` is fed to its stdin. `shown`: its streams are this process's own,
    for a program the person reads or answers here (an install's progress, a sign-in) — in this console where there is
    one, no window made for it where there is none."""
    if shown:
        kw.update(stdin=None, stdout=None, stderr=None)
        if os.name == "nt" and ctypes.WinDLL("kernel32").GetConsoleWindow():
            kw.setdefault("creationflags", 0)
    # under `gfso mcp` stdin is the protocol pipe
    kw.setdefault("stdin", subprocess.DEVNULL if input is None else subprocess.PIPE)
    kw.setdefault("stdout", subprocess.PIPE)
    kw.setdefault("stderr", subprocess.PIPE)
    proc = popen(args, shown, **kw)
    try:
        out, err = proc.communicate(input, timeout=timeout)
        return subprocess.CompletedProcess(args, proc.returncode, out, err)
    finally:
        end(proc)


#: the most of one stream of a program whose output nobody bounded that the server keeps in its memory: half its head,
#: half its tail. Held whole, a build or a check looping on print added 100 MiB a second to the server (measured),
#: past every container's limit and the machine's ceiling, which count none of it
PRINTED_CAP = 64 * 2 ** 20
#: what stands in a stream in place of what was dropped
CUT = "bytes printed here, not kept"


def _kept(stream, cap: int, into: list) -> None:
    """`stream` read to its end, its head and tail kept, the rest counted: [head, tail, bytes dropped]."""
    head, tail, half, cut = bytearray(), bytearray(), cap // 2, 0
    while chunk := stream.read(2 ** 16):
        take = chunk[:half - len(head)]
        head += take
        tail += chunk[len(take):]
        if len(tail) > 2 * half:                 # …trimmed by the half, not per chunk: a byte's move per chunk is quadratic
            cut += len(tail) - half
            del tail[:len(tail) - half]
    if len(tail) > half:
        cut += len(tail) - half
        del tail[:len(tail) - half]
    into[:] = [bytes(head), bytes(tail), cut]


def _said(kept: list, encoding: str, errors: str) -> str:
    head, tail, cut = kept
    return (head.decode(encoding, errors) + (f"\n… [{cut} {CUT}] …\n" if cut else "")
            + tail.decode(encoding, errors))


def run_printing(args, *, timeout: float, encoding: str = "utf-8", errors: str = "replace",
                 **kw) -> subprocess.CompletedProcess:
    """`run` of a program that may print without end, as text: each stream kept to `PRINTED_CAP`, what was dropped from
    its middle said in its place."""
    kw.setdefault("stdin", subprocess.DEVNULL)
    proc = popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)
    kept: tuple = ([], [])
    readers = [threading.Thread(target=_kept, args=(s, PRINTED_CAP, k), daemon=True)
               for s, k in zip((proc.stdout, proc.stderr), kept)]
    try:
        until = time.monotonic() + timeout
        for r in readers:
            r.start()
        for r in readers:
            r.join(max(0.0, until - time.monotonic()))
        if any(r.is_alive() for r in readers):
            raise subprocess.TimeoutExpired(args, timeout)
        proc.wait(max(0.0, until - time.monotonic()))
        return subprocess.CompletedProcess(args, proc.returncode, *(_said(k, encoding, errors) for k in kept))
    finally:
        end(proc)


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
    if pgid <= 0:            # killpg(0) is THIS process's own group: a fake child's pid 0 killed pytest and CI's runner
        return
    with contextlib.suppress(ProcessLookupError):         # the group is already gone: the goal
        try:
            os.killpg(pgid, signal.SIGKILL)
        except PermissionError as e:
            log.warning(f"process group {pgid} could not be ended ({e})")


#: what else ends with this process — children it holds that `reap` cannot reach (a container's calls)
_AT_EXIT: list = []


def at_exit(fn) -> None:
    """End `fn`'s children with this process too, however it exits."""
    _AT_EXIT.append(fn)


def _end_all(closing: bool = False) -> None:
    global _CLOSING
    with _LOCK:                      # …what is left to do here runs children of its own: past the reap each died at its spawn, and
        _CLOSING = False             # on Linux no container was removed nor any last reading made (critic, ran)
    for fn in list(_AT_EXIT):
        with contextlib.suppress(Exception):     # one holder failing to end its own never keeps the rest alive
            fn()
    reap(closing)


def end_this_process(code: int = 0) -> None:
    """Exit NOW, children first. `os._exit` skips interpreter exit (and so `atexit`), which is the
    point — nothing waits on a worker thread — and is why the reap is done here, not left to it."""
    _end_all(closing=True)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


atexit.register(_end_all)
