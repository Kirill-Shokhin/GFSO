"""Where a session or a command runs (`ExecutionPort`): `LocalExecution` — on this host, as every launch ran before
the port existed; `ContainerExecution` — inside one long-lived Linux container per (execution, project), the same server
starting every call through `docker exec`, so a project's work is isolated without a second server. The graph keeps host
paths: a container sees the base's parent as `/gfso-place`, and every path crossing the boundary is mapped both ways."""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import subprocess
import threading
import uuid
from pathlib import Path

from gfso.core.types import ExecutionPort
from gfso.config import claude_config_dir, host_env
from gfso.adapters.children import adopt, at_exit, kill_tree, release, run, spawn_kw

INSIDE = "/gfso-place"
#: the agent CLI's state inside the container — the image's `CLAUDE_CONFIG_DIR`
STATE_INSIDE = "/home/agent/.claude"
#: Docker Desktop forwards this network to the HOST'S LOOPBACK, :8000 included (probe P8): a session inside could
#: otherwise sign the graph it works under (§10.3)
HOST_NET = "192.168.65.0/24"
#: what marks a container as a project's execution of THIS product — the one thing a sweep of leftovers removes
LABEL = "gfso.execution"
#: the containers this server process started — one per (execution, project), whichever object asks for it — with
#: what each was started holding: a project re-created on another base gets a container of its own again
_STARTED: dict = {}
_START = threading.Lock()


class LocalExecution(ExecutionPort):
    def which(self, program: str):
        return shutil.which(program)

    def popen(self, args, *, env, cwd, **pipes):
        # Windows: a console child ALLOCATES ITS OWN console when the parent has none (the shared server is spawned
        # detached) — every agent run popped an empty `claude` window on top of the user's screen, accidentally
        # closable (= killing the run). CREATE_NO_WINDOW suppresses the console; all real I/O rides the pipes.
        no_window = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        return adopt(subprocess.Popen(args, env=env, cwd=cwd, **pipes, **no_window, **spawn_kw()))

    def end(self, proc) -> None:
        kill_tree(proc)
        release(proc)

    def temp_root(self):
        return tempfile.gettempdir()

    def state_dir(self):
        return claude_config_dir()

    def run(self, args, *, cwd, timeout, env=None):
        return run(args, timeout=timeout, cwd=cwd, text=True, encoding="utf-8", errors="replace",
                   **({"env": env} if env is not None else {}))

    def shell(self):
        """On Windows Git's own bash (the one Claude Code runs), never WSL's `bash.exe`, where a `C:/…` inputs path does
        not resolve."""
        if (git := shutil.which("git")) and (b := Path(git).resolve().parents[1] / "bin" / "bash.exe").is_file():
            return str(b)
        return shutil.which("bash")


def end_started() -> None:
    """At this server's exit: its project containers, and every call in them — killing a `docker exec` client leaves
    its call running inside (probe P1), so the server's children would outlive it there and go on spending."""
    if ids := list(_STARTED):
        run(["docker", "rm", "-f", *ids], timeout=120)
        _STARTED.clear()


at_exit(end_started)


def end_leftovers() -> None:
    """At a server's start: the project containers of a server that is gone — their calls died with it, and each is
    started afresh on its project's first call."""
    if shutil.which("docker"):
        got = run(["docker", "ps", "-aq", "--filter", f"label={LABEL}"], timeout=60, text=True)
        if ids := (got.stdout or "").split():
            run(["docker", "rm", "-f", *ids], timeout=120)


class ContainerExecution(ExecutionPort):
    """`image` with `env_file` (the agent's auth) and the CLI's `state` dir, holding `base`'s parent's four directories
    of this project — the base, its node places, its scratch, a temp of its own — at `/gfso-place/<name>`. Nothing else
    of the host is mounted, and the host's network is shut at start."""

    def __init__(self, name: str, image: str, env_file: str, state: str, base: str, project: str):
        self.base, self.parent = Path(base).resolve(), Path(base).resolve().parent
        if not self.parent.drive or self.parent.drive.startswith("\\\\"):
            raise ValueError(f"execution {name!r}: {base} is not on a local drive — a container cannot mount it")
        self.name, self.image, self.env_file = name, image, env_file
        self.container = re.sub(r"[^a-zA-Z0-9_.-]+", "-", f"gfso-{name}-{project}").lower()
        # THE CLI'S STATE IS THE PROJECT'S: shared by an execution's projects, every E3 row (all at /gfso-place/ws) read
        # and appended to another row's conversation (critic over d5c8f7a, measured on two containers)
        self.state = Path(state) / self.container
        b = self.base.name
        self.mounts = [b, f".gfso-nodes-{b}", f".gfso-scratch-{b}", f".gfso-tmp-{b}"]
        # the parent in any spelling a path may arrive in — C:\ or C:/, either drive case — and the rest of that path
        # (a doubled backslash too: a path inside JSON); Windows paths are caseless
        sep = r"[\\/]{1,2}"
        self._host = re.compile(re.escape(self.parent.drive[0]) + r":" + sep
                                + sep.join(re.escape(p) for p in self.parent.parts[1:])
                                + r"(?P<rest>(?:" + sep + r"[^\s\"'`<>|*?]*)?)(?![^\s\"'`<>|*?\\/])", re.IGNORECASE)

    def to_inside(self, text: str) -> str:
        """`text` with every host path under the parent spelled as the container sees it."""
        return self._host.sub(lambda m: INSIDE + re.sub(r"[\\/]+", "/", m.group("rest")), text)

    def to_outside(self, text: str) -> str:
        """`text` with every container path spelled as the host sees it (forward slashes: valid inside JSON too)."""
        return re.sub(re.escape(INSIDE) + r"(?![\w.-])", self.parent.as_posix(), text)

    def inside_cwd(self, cwd: str) -> str:
        """The container's path of a place the call runs in — one of the mounted four, else refused: the agent would
        stand where nothing of the project is, or the call would reach outside what the container holds."""
        rel = Path(cwd).resolve().relative_to(self.parent) if Path(cwd).resolve().is_relative_to(self.parent) else None
        if rel is None or not rel.parts or rel.parts[0] not in self.mounts:
            raise ValueError(f"{cwd} is not inside {self.container}'s mounts ({', '.join(self.mounts)} of {self.parent})")
        return INSIDE + "/" + rel.as_posix()

    def run_args(self) -> list[str]:
        """`docker run` for this project's container: sealed (`--init`, its own mounts only, NET_ADMIN for the rule
        `start` adds as root), sleeping until the server calls into it."""
        mounts = [a for m in self.mounts for a in ("--mount", f"type=bind,src={self.parent / m},dst={INSIDE}/{m}")]
        return ["docker", "run", "-d", "--init", "--name", self.container, "--label", f"{LABEL}={self.name}",
                "--cap-add", "NET_ADMIN",
                "--env-file", self.env_file, *mounts, "--mount", f"type=bind,src={self.state},dst={STATE_INSIDE}",
                "--add-host", "host.docker.internal:0.0.0.0", self.image, "sleep", "infinity"]

    def start(self) -> None:
        """The project's container, running and sealed — started once per server process, whoever asks first."""
        with _START:
            if _STARTED.get(self.container) == self.run_args() and self._running():
                return
            for d in [self.parent / m for m in self.mounts] + [self.state]:
                d.mkdir(parents=True, exist_ok=True)
            run(["docker", "rm", "-f", self.container], timeout=60)      # a container of a server that is gone
            run(self.run_args(), timeout=120).check_returncode()
            seal = run(["docker", "exec", "-u", "0", self.container, "sh", "-c",       # uid 0: the rule is root's
                        f"iptables -A OUTPUT -d {HOST_NET} -j REJECT && mkdir -p /tmp/gfso-calls && "
                        f"chmod 1777 /tmp/gfso-calls"], timeout=60)
            if seal.returncode != 0:
                self.stop()
                raise RuntimeError(f"{self.container}: the host's network could not be shut — no call runs unsealed "
                                   f"({(seal.stderr or b'').decode(errors='replace')[-300:]})")
            _STARTED[self.container] = self.run_args()

    def _running(self) -> bool:
        """Is the container still up? A Docker restart (the host slept, an update) removes it under a live server, and
        every later call of the project then failed `No such container` (critic over d5c8f7a)."""
        got = run(["docker", "inspect", "-f", "{{.State.Running}}", self.container], timeout=30, text=True)
        return got.returncode == 0 and (got.stdout or "").strip() == "true"

    def stop(self) -> None:
        run(["docker", "rm", "-f", self.container], timeout=60)
        _STARTED.pop(self.container, None)

    def which(self, program: str):
        return program                         # resolved on the container's PATH when the call starts

    def _exec_argv(self, args, env, cwd, call: str) -> list[str]:
        self.start()
        # what the call itself sets, not the host's environment: auth came with the container, its PATH is its own
        here = host_env()
        own = {k: v for k, v in (env or {}).items() if here.get(k) != v or k.startswith("ANTHROPIC_")}
        return ["docker", "exec", "-i", "-w", self.inside_cwd(cwd), "-e", f"GFSO_CALL={call}",
                *[a for k, v in own.items() for a in ("-e", f"{k}={self.to_inside(v)}")], self.container,
                "sh", "-c", f'echo $$ >/tmp/gfso-calls/{call}; exec "$@"', "sh", *map(self.to_inside, args)]

    def popen(self, args, *, env, cwd, **pipes):
        call = uuid.uuid4().hex
        return _Call(LocalExecution().popen(self._exec_argv(args, env, cwd, call), env=host_env(),
                                            cwd=str(self.parent), **pipes), self, call)

    def run(self, args, *, cwd, timeout, env=None):
        call = uuid.uuid4().hex
        try:
            done = run(self._exec_argv(args, env, cwd, call), timeout=timeout, cwd=str(self.parent), text=True,
                       encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            self._end_inside(call)
            raise
        return subprocess.CompletedProcess(args, done.returncode, self.to_outside(done.stdout or ""),
                                           self.to_outside(done.stderr or ""))

    def shell(self):
        return "bash"

    def end(self, proc) -> None:
        """The call's group inside, and whatever it started that left the group (`setsid`), found by its mark — killing
        the `docker exec` client alone leaves them all running (probe P1)."""
        if isinstance(proc, _Call):
            self._end_inside(proc.call)
            proc = proc.client
        LocalExecution().end(proc)

    def _end_inside(self, call: str) -> None:
        run(["docker", "exec", self.container, "sh", "-c",
             f"p=$(cat /tmp/gfso-calls/{call} 2>/dev/null) && kill -KILL -$p; "
             f"for e in /proc/[0-9]*/environ; do grep -qz GFSO_CALL={call} $e 2>/dev/null && "
             f"q=${{e#/proc/}} && kill -KILL ${{q%/environ}}; done; rm -f /tmp/gfso-calls/{call}"], timeout=60)

    def temp_root(self):
        (d := self.parent / self.mounts[3]).mkdir(parents=True, exist_ok=True)
        return str(d)

    def state_dir(self):
        return self.state


class _Call:
    """A call inside, as the host's code reads a process: what it is fed goes in with container paths, what it prints
    comes out with host paths."""

    def __init__(self, client, execution: ContainerExecution, call: str):
        self.client, self.call, self._ex = client, call, execution
        self.stdin = _Mapped(client.stdin, execution.to_inside) if client.stdin else None
        self.stdout = (execution.to_outside(line) for line in client.stdout) if client.stdout else None
        self.pid = client.pid

    @property
    def returncode(self):
        """The `docker exec` client's: the call's own exit code once it ended."""
        return self.client.returncode

    def poll(self):
        """As `Popen.poll`, on the client."""
        return self.client.poll()

    def wait(self, timeout=None):
        """As `Popen.wait`, on the client."""
        return self.client.wait(timeout=timeout)

    def kill(self):
        """Ended inside, not only the client."""
        self._ex.end(self)


class _Mapped:
    def __init__(self, stream, mapping):
        self._s, self._map = stream, mapping

    def write(self, text: str):
        """Write `text` mapped."""
        return self._s.write(self._map(text))

    def close(self):
        """Close the stream underneath."""
        self._s.close()
