"""A session's commands, run apart from its model client — in a container of their own beside the client's, sharing its
place and its network, never its processes (`execution.Commands`). Two programs in one file, stdlib only:

- `CLIENT`, the client's shell (`CLAUDE_CODE_SHELL`): laid by the system where no agent process writes, it forwards
  each invocation — argv, cwd, environment — over a unix socket in the network both containers share, writes back
  what the command printed and exits with its code; a signal it gets is passed on, and its end ends the command's
  group. It writes back no file but those it named from its own argv: the CLI's cwd file and its shell snapshot.
- the listener (`python3 shell.py serve <uid>:<gid> <log> <said>`), root in the commands' container, which runs each
  command as `<user>` — under no-new-privileges, with no capability — and holds nothing they reach: they cannot
  signal it, read it, nor write its record. It answers only a connection from outside its own processes' namespace: a
  command of the session cannot ask it for anything.

Why apart: a command run beside the client, as its uid and in its PID namespace, wrote `/proc/<client>/fd/1` and so
forged the stream the system reads as the record of what the session did (S6 probe). The record now has two writers
out of a command's reach: the client's own stream, and this listener's line for each command — attributed, written as
it starts and as it ends, bounded, always on — in its container's memory, which the system alone reads.

What a command still cannot have here: the CLI's task-output files (in the client's /tmp; its Read tool reads them),
its CLI state, and a cwd outside the place both containers share."""
import json
import os
import re
import select
import signal
import socket
import struct
import subprocess
import sys
import threading
import time

#: the socket, in the abstract namespace of the network the two containers share: no file any process can replace
NAME = b"\0gfso-shell"
#: where the system lays the client and its fallback guard in the client's container: root's, no agent process writes
HOME = "/gfso-shell"
CLIENT, BESIDE = f"{HOME}/bash", f"{HOME}/beside"
#: what `BESIDE` says: the client's CLI ran a shell of its own, the command refused (`BASH_ENV`)
REFUSED = "refused: the agent CLI ran this command beside itself, not through the system's shell"
#: `BESIDE`, the `BASH_ENV` of the client's CLI: a bash it starts there — its own fallback where it did not take
#: `CLIENT`, which it does silently — tells the listener so and runs nothing
GUARD = f'{CLIENT} --beside; echo "{REFUSED}" >&2; exit 126\n'
#: the client's `git`, first on its PATH: none. Its CLI's own `git status` ran the repository's clean filter beside it, in
#: reach of its output and its state (critic, live); its commands keep their git, in their own container
NO_GIT = "/usr/local/bin/git"
NONE = '#!/bin/sh\necho "fatal: not a git repository (no git beside the model client)" >&2\nexit 128\n'
REQ, SIG, OUT, ERR, FILE, RC = range(6)
CHUNK = 65536
#: a record past this many bytes keeps a command's head alone and no refusal — a flood of them cannot crowd out the
#: commands; each argument is cut at `ARG` anyway
LOG_CAP, ARG, SHORT = 20 * 2 ** 20, 4096, 200
#: the most of a named file sent back — a cwd file, a snapshot of a few kilobytes
FILE_CAP = 2 ** 20
#: what changed in the place while a command ran, as its record line says it: the paths at most, and the seconds the
#: walk may take — 60 ms over 50 000 files (probe), cut past it and said so
CHANGED_CAP, CHANGED_S = 200, 10
#: the files a client names from its own argv to be written back: the CLI's cwd file and its shell snapshot
NAMED = (re.compile(r"pwd -P >\| ?'?([^'\s]+)"), re.compile(r"SNAPSHOT_FILE='?([^'\s;]+)"))
#: the client's CLI state inside its container — the image's `CLAUDE_CONFIG_DIR`, where no command reaches
STATE = "/home/agent/.claude"
#: …and only of their own shapes: the names are read off the whole argv, the model's command in it, and any path a
#: command named was laid in the client's container as its user — its home, its CLI state, its output through a link
#: (critic, live: a forged hook and a forged stream)
OWN = re.compile(r"/tmp/claude-[0-9a-f]+-cwd|(?P<state>/[\w./-]+)/shell-snapshots/snapshot-[\w.-]+\.sh")


def _frame(s, kind: int, data: bytes = b"") -> None:
    s.sendall(struct.pack(">BI", kind, len(data)) + data)


def _exactly(s, n: int) -> bytes | None:
    got = bytearray()
    while len(got) < n:
        if not (more := s.recv(min(n - len(got), 2 ** 20))):
            return None
        got += more
    return bytes(got)


def _read(s):
    """(kind, data) of the next frame, None at its end — a reset one's too."""
    try:
        head = _exactly(s, 5)
        data = head and _exactly(s, struct.unpack(">BI", head)[1])
    except OSError:
        return None
    return None if head is None or data is None else (head[0], data)


def _peer(s) -> tuple:
    """(pid, uid, gid) of the other end — its pid 0 where it is outside this process's PID namespace."""
    return struct.unpack("3i", s.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))


def named(argv: list) -> list:
    """The files the CLI's own invocation names for its shell to leave behind — its cwd file in its own `/tmp` and its
    shell snapshot in its own state (`STATE`), never a directory of the place a command could
    swap under the write (critic), no `..` in them."""
    return [p for p in dict.fromkeys(m[1] for a in argv for r in NAMED for m in r.finditer(a))
            if (o := OWN.fullmatch(p)) and o["state"] in (None, STATE) and ".." not in p.split("/")]


def client(argv: list) -> int:
    """One invocation forwarded; its exit code. Reaching no listener of the system's — root's, outside — it runs
    nothing."""
    files = named(argv)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(NAME)
        if _peer(s)[1] != 0:
            raise OSError("its listener is not the system's")
    except OSError as e:
        print(f"the system's shell is not reachable ({e}): nothing ran", file=sys.stderr)
        return 126
    # …its own path is no shell where the command runs, and its guard is the client's container's alone
    env = {**{k: v for k, v in os.environ.items() if k != "BASH_ENV"}, "SHELL": "/bin/bash"}
    # …the image's PATH: the system's own directories first were for the system's calls (`execution.SYSTEM_PATH`); a
    # command is the agent's own, and a declared image's environment is what it was given to work in
    env["PATH"] = env.pop("GFSO_WORK_PATH", env.get("PATH", ""))
    _frame(s, REQ, json.dumps({"argv": argv, "cwd": os.getcwd(), "env": env, "files": files,
                               "beside": argv == ["--beside"]}).encode())
    for n in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGQUIT):
        signal.signal(n, lambda n, _: _quietly(_frame, s, SIG, str(n).encode()))
    while (got := _read(s)) is not None:
        if got[0] == RC:
            return int(got[1]) if int(got[1]) >= 0 else 128 - int(got[1])
        _written(*got, files)
    print("the system's shell ended before the command did", file=sys.stderr)
    return 126


def _written(kind: int, data: bytes, files: list) -> None:
    """A frame the listener sent, written where it belongs: what the command printed to the client's own stdout or
    stderr, a file the client named to its own path — nothing else."""
    if kind == FILE:
        path, _, body = data.partition(b"\0")
        if (path := path.decode()) in files and os.path.realpath(os.path.dirname(path)) == os.path.dirname(path):
            # …never through a link the command laid, at the file or above it
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "wb") as f:
                f.write(body)
        return
    (out := (sys.stdout if kind == OUT else sys.stderr).buffer).write(data)
    out.flush()


class Record:
    """The listener's record: a line per command as it starts and as it ends, each attributed — the session (`said`),
    the client's call (`run`, its `GFSO_CALL`), a sequence number. A line the disk refuses is dropped, never raised into
    a command."""

    def __init__(self, log: str, said: dict):
        self.log, self.said, self.seq, self._lock = log, said, 0, threading.Lock()

    def begin(self, run, **what) -> int:
        """A command's first line, `what` it is; its sequence number."""
        with self._lock:
            self.seq += 1
            n = self.seq
        self.write({"seq": n, "run": run, **what})
        return n

    def write(self, line: dict) -> None:
        """One line, its arguments cut to the record's room; past its cap, no refusal."""
        try:
            with self._lock, open(self.log, "a", encoding="utf-8") as f:
                if "refused" in line and f.tell() >= LOG_CAP:
                    return
                if "argv" in line:
                    line["argv"] = [str(a)[:SHORT if f.tell() >= LOG_CAP else ARG] for a in line["argv"]]
                f.write(json.dumps({"at": time.time(), **self.said, **line}) + "\n")
        except OSError:          # …its memory full: the command runs all the same, its line lost
            pass


def _quietly(f, *a) -> None:
    try:
        f(*a)
    except OSError:              # …the client gone, or its command's group: nothing is left to tell
        pass


def _to_the_end(f) -> None:
    """What a process a command left running prints, read to its end and dropped: unread, it would block on a full
    pipe, where the CLI's own file took it."""
    while f.read(CHUNK):
        pass
    f.close()


class _Run:
    """One command as the listener runs it: what it prints passed to the client while the client is there."""

    def __init__(self, c, p):
        self.c, self.p, self.out, self.gone = c, p, 0, False
        self.pipes = {p.stdout.fileno(): (OUT, p.stdout), p.stderr.fileno(): (ERR, p.stderr)}

    def read(self, fd) -> None:
        """What the command printed on `fd`, passed on while the client is there."""
        if not (data := os.read(fd, CHUNK)):
            del self.pipes[fd]
        elif not self.gone:
            self.out += len(data)
            _quietly(_frame, self.c, self.pipes[fd][0], data)

    def heard(self) -> None:
        """A frame from the client: a signal for the command's group; its end — killed, timed out — the group's."""
        if (got := _read(self.c)) is None:
            self.gone = True
            _quietly(os.killpg, self.p.pid, signal.SIGKILL)
        elif got[0] == SIG:
            _quietly(os.killpg, self.p.pid, int(got[1]))

    def through(self) -> int:
        """Its exit code, once it ended and what it printed before that is passed on."""
        ended = os.pidfd_open(self.p.pid)
        while ended not in (ready := select.select([*self.pipes, *([] if self.gone else [self.c]), ended], [], [])[0]):
            if self.c in ready:
                self.heard()
            for fd in [f for f in ready if f in self.pipes]:
                self.read(fd)
        os.close(ended)
        while self.pipes and (ready := select.select(list(self.pipes), [], [], 0)[0]):
            for fd in ready:
                self.read(fd)
        for _, f in self.pipes.values():
            threading.Thread(target=_to_the_end, args=(f,), daemon=True).start()
        return self.p.wait()


def _changed(place: str, since: float, user: dict) -> dict:
    """What in `place` had its status changed since `since` — written, made, chmodded, a directory whose entries were
    added, removed or renamed —, walked as the command's user: by the inode's change time, which no process of a user
    sets (a written file's mtime it does: `touch -d`). Every process of the place in that span changes it, the
    command's own and any left running: the record says where, not who."""
    try:
        got = subprocess.run(["timeout", str(CHANGED_S), "find", place, "-xdev", "-newerct", f"@{since:.3f}",
                              "-printf", "%y %P\n"], capture_output=True, stdin=subprocess.DEVNULL, **user)
    except OSError as e:
        return {"changed_unread": str(e)}
    lines = got.stdout.decode("utf-8", errors="replace").splitlines()
    return {"changed": lines[:CHANGED_CAP], "changed_n": len(lines),
            **({"changed_cut": True} if got.returncode == 124 else {}),
            **({"changed_unread": got.stderr.decode("utf-8", errors="replace")[-300:]}
               if got.returncode not in (0, 124) else {})}


def _one(c, user: dict, record: Record) -> None:
    """One connection: refused where it comes from a command of the session itself; else the command run and recorded,
    its named files sent back after it."""
    with c:
        if _peer(c)[0] != 0:
            return record.write({"refused": "a connection from the commands' own container"})
        if (got := _read(c)) is None or got[0] != REQ:
            return
        req = json.loads(got[1])
        run = req["env"].get("GFSO_CALL")
        if req.get("beside"):
            record.begin(run, beside=REFUSED)
            return _frame(c, RC, b"126")
        # …a tick early: the kernel stamps a file by its coarse clock, a tick behind, and a change in a command's first
        # milliseconds read as older than its start; the span takes the last 50 ms before it in
        seq, t0, since = record.begin(run, argv=req["argv"], cwd=req["cwd"]), time.monotonic(), time.time() - 0.05
        for d in {os.path.dirname(f) for f in req["files"]}:     # …the snapshot's directory: else the CLI goes without
            subprocess.run(["mkdir", "-p", "--", d], capture_output=True, stdin=subprocess.DEVNULL, **user)
        try:
            r = _Run(c, subprocess.Popen(["/bin/bash", *req["argv"]], cwd=req["cwd"], env=req["env"],
                                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         start_new_session=True, **user))
        except OSError as e:
            _frame(c, ERR, f"{e}\n".encode())
            record.write({"seq": seq, "run": run, "rc": 126})
            return _frame(c, RC, b"126")
        rc = r.through()
        record.write({"seq": seq, "run": run, "rc": rc, "ms": int((time.monotonic() - t0) * 1000), "bytes": r.out,
                      **(_changed(place, since, user) if (place := record.said.get("place")) else {})})
        if not r.gone:
            for f in req["files"]:
                if (got := subprocess.run(["head", "-c", str(FILE_CAP), "--", f], capture_output=True,
                                          stdin=subprocess.DEVNULL, **user)).returncode == 0:
                    _quietly(_frame, c, FILE, f.encode() + b"\0" + got.stdout)
            _quietly(_frame, c, RC, str(rc).encode())


def serve(user: str, log: str, said: str) -> None:
    """Listen until the container is removed, each connection on a thread of its own; its commands run as `user`
    (`<uid>:<gid>`), never root — root here holds the record."""
    uid, gid = map(int, user.split(":"))
    if uid == 0:
        sys.exit("the commands would run as root, who holds their record")
    record, s = Record(log, json.loads(said)), socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(NAME)
    s.listen(64)
    while True:
        c, _ = s.accept()
        threading.Thread(target=_one, args=(c, {"user": uid, "group": gid, "extra_groups": []},
                                             record), daemon=True).start()


if __name__ == "__main__":
    if sys.argv[1:2] == ["serve"]:
        serve(*sys.argv[2:5])
    else:
        sys.exit(client(sys.argv[1:]))
