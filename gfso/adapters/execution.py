"""Where a session or a command runs (`ExecutionPort`): `LocalExecution` — on this host, as every launch ran before
the port existed; `ContainerExecution` — inside one long-lived Linux container per (execution, project), the same server
starting every call through `docker exec`, so a project's work is isolated without a second server. The graph keeps host
paths: a container sees the base's parent as `/gfso-place`, and every path crossing the boundary is mapped both ways."""
from __future__ import annotations

import ipaddress
import os
import re
import shutil
import socket
import stat
import tempfile
import subprocess
import threading
import uuid
from pathlib import Path

from gfso.core.types import ExecutionPort, PlaceUnavailable
from gfso.config import claude_config_dir, host_env
from gfso.adapters import egress
from gfso.adapters.children import adopt, at_exit, kill_tree, release, run, spawn_kw

INSIDE = "/gfso-place"
#: the agent CLI's state inside the container — the image's `CLAUDE_CONFIG_DIR`
STATE_INSIDE = "/home/agent/.claude"
#: Docker Desktop forwards this network to the HOST'S LOOPBACK, :8000 included (probe P8): a session inside could
#: otherwise sign the graph it works under (§10.3)
HOST_NET = "192.168.65.0/24"
#: the switch on a container's way out — set OUTSIDE the system (the execution's declaration, or whoever builds it), never
#: a policy of its own. `open` — everything but the host (other containers on Docker's bridge included), the rule set in
#: the container by root. `allowlist` and `off` — the container stands on an internal network with no route out, so the
#: fence is the network's, out of reach of anything inside, root included; under `allowlist` one gateway container
#: (`egress.py`) joins it and lets a session reach the named hosts on 443, the TLS handshake naming the host asked for.
#: A session's own CLI calls its model from inside, so `off` suits only a provider that calls it from outside. What the
#: allowlist does NOT hold: an allowed host carries whatever the session sends it under any credentials it presents (a
#: model API that stores data is a way out to another tenant's account); inside the encrypted stream the request may
#: still name another site the same front serves — reading it needs the gateway to end TLS itself; the gateway stands on
#: Docker's bridge, so a gateway taken over is the whole way out; and each closed project takes one of Docker's address
#: pools, past which a start fails closed
NETWORK = ("open", "allowlist", "off")
#: the gateway's address and port as a session inside an allowlisted project reaches it
GATEWAY = "gateway"
#: what marks a container as a project's execution of THIS product — the one thing a sweep of leftovers removes
LABEL = "gfso.execution"
#: the containers this server process started — one per (execution, project), whichever object asks for it — with
#: what each was started holding: a project re-created on another base gets a container of its own again
_STARTED: dict = {}
#: each container's switch as last declared — the container's, not an object's: a session keeps its object for its whole
#: life, so any object starting the container must start it under the switch as it stands now (critic 4: a second
#: object of one container started it back under its own)
_SWITCH: dict = {}
_START = threading.RLock()     # a turn stops what a start holds, under the same lock


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

    def copy_tree(self, src: str, dst: str) -> None:
        shutil.copytree(src, dst, symlinks=True)

    def remove_tree(self, path: str) -> None:
        # owned before listed: rmtree neither lists a directory it may not read nor unlinks inside one it may not write
        if not os.path.lexists(path):
            return
        _own(path)
        for d, dirs, _ in os.walk(path):
            for x in dirs:
                if not os.path.islink(p := os.path.join(d, x)):
                    _own(p)
        shutil.rmtree(path, onerror=lambda fn, p, _: (_own(p), fn(p)))

    def shell(self):
        """On Windows Git's own bash (the one Claude Code runs), never WSL's `bash.exe`, where a `C:/…` inputs path does
        not resolve."""
        if (git := shutil.which("git")) and (b := Path(git).resolve().parents[1] / "bin" / "bash.exe").is_file():
            return str(b)
        return shutil.which("bash")


def _own(path: str) -> None:
    os.chmod(path, os.lstat(path).st_mode | stat.S_IRWXU)


def _public_v4(host: str) -> set:
    """`host`'s public IPv4 addresses as this host resolves them; none where it does not resolve."""
    try:
        got = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror:
        return set()
    return {a[4][0] for a in got if ipaddress.ip_address(a[4][0]).is_global}


def end_started() -> None:
    """At this server's exit: its project containers, and every call in them — killing a `docker exec` client leaves
    its call running inside (probe P1), so the server's children would outlive it there and go on spending."""
    if ids := list(_STARTED):
        run(["docker", "rm", "-f", *ids, *[f"{i}-gw" for i in ids]], timeout=120)
        run(["docker", "network", "rm", *[f"{i}-net" for i in ids]], timeout=120)
        _STARTED.clear()


at_exit(end_started)


def end_leftovers() -> None:
    """At a server's start: the project containers of a server that is gone — their calls died with it, and each is
    started afresh on its project's first call."""
    if shutil.which("docker"):
        got = run(["docker", "ps", "-aq", "--filter", f"label={LABEL}"], timeout=60, text=True)
        if ids := (got.stdout or "").split():
            run(["docker", "rm", "-f", *ids], timeout=120)
        run(["docker", "network", "prune", "-f", "--filter", f"label={LABEL}"], timeout=120)


class WayOut:
    """A container's way out, as its switch sets it: open on Docker's bridge with the host shut by root inside; closed on
    an internal network of its own, out of reach of anything inside, with the allowlist's gateway the one member of both
    networks, writing its log under `home`, beside the CLI's state and not in it."""

    def __init__(self, container: str, name: str, image: str, home: Path):
        self.container, self.name, self.image, self.home = container, name, image, home
        self.net, self.gateway = f"{container}-net", f"{container}-gw"

    def switch(self, network) -> None:
        """Turn the way out to `network`. The container holds it, so every holder's next call starts the container
        under it — the calls running in it end, as they must: they were let out under the old switch. Taken
        under the start's lock, so a start seals and records ONE switch; a switch that does not read shuts the way out,
        since a holder that keeps the old one would stay out under a switch someone meant to close."""
        with _START:
            try:
                mode, hosts = (network or {}).get("mode", "open"), tuple((network or {}).get("hosts") or ())
                ok = mode in NETWORK and all(re.fullmatch(r"[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+", h) for h in hosts)
            except (AttributeError, TypeError):
                ok = False
            _SWITCH[self.container] = (mode, hosts) if ok else ("off", ())
        if not ok:
            raise ValueError(f"{self.container}: network {network!r} — a mode of {NETWORK} and host names only")

    @property
    def network(self) -> tuple:
        """This container's switch as last declared; open where none was."""
        return _SWITCH.get(self.container, ("open", ()))

    def gateway_args(self) -> list[str]:
        """`docker run` for the allowlist's gateway: on the project's network first, so it listens there alone (it
        joins Docker's bridge after, to reach out), the execution's own image running `egress.py` read-only,
        unprivileged and bounded, nothing of the project mounted."""
        return ["docker", "run", "-d", "--init", "--name", self.gateway, "--label", f"{LABEL}={self.name}",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--read-only",
                "--sysctl", "net.ipv4.ip_forward=0", "--memory", "256m", "--pids-limit", "256",
                "--network", self.net, "--network-alias", GATEWAY,
                "--mount", f"type=bind,src={Path(egress.__file__).resolve()},dst=/gfso-egress.py,readonly",
                "--mount", f"type=bind,src={self.log().parent},dst=/log",
                self.image, "python3", "/gfso-egress.py", ",".join(self.network[1]), "/log/" + self.log().name,
                GATEWAY]

    def run_args(self) -> list[str]:
        """What `docker run` of the container takes for this way out: NET_ADMIN for the host rule when open; else its
        internal network, no capability at all, no IPv6, and under an allowlist the gateway named its proxy."""
        mode = self.network[0]
        if mode == "open":
            return ["--cap-add", "NET_ADMIN"]
        return ["--network", self.net, "--cap-drop", "ALL", "--sysctl", "net.ipv6.conf.all.disable_ipv6=1",
                *[a for k in ("HTTPS_PROXY", "https_proxy") for a in ("-e", f"{k}=http://{GATEWAY}:{egress.PORT}")
                  if mode == "allowlist"]]

    def seal(self) -> str:
        """What root runs in the container before any call: the host shut when the switch is open; a closed switch's
        container has no route to shut and no capability to set one."""
        return f"iptables -A OUTPUT -d {HOST_NET} -j REJECT" if self.network[0] == "open" else "true"

    def open(self) -> None:
        """A closed switch's internal network, and the allowlist's gateway on it — refused when an allowed host has no
        public address, so a list that would silently differ from the declared one starts nothing (`OSError`)."""
        mode, hosts = self.network
        if mode == "open":
            return
        if missing := [h for h in hosts if not _public_v4(h)]:
            raise OSError(f"no public address for {', '.join(missing)}")
        # isolated: the network's bridge gets no address of the Docker VM's own, which every member would reach on-link
        run(["docker", "network", "create", "--internal", "-o", "com.docker.network.bridge.gateway_mode_ipv4=isolated",
             "--label", f"{LABEL}={self.name}", self.net], timeout=60).check_returncode()
        if mode == "allowlist":
            self.log().parent.mkdir(parents=True, exist_ok=True)
            run(self.gateway_args(), timeout=120).check_returncode()
            run(["docker", "network", "connect", "bridge", self.gateway], timeout=60).check_returncode()

    def log(self) -> Path:
        """Every connection the allowlist's gateway opened or refused, written by the gateway as it happens — in a
        directory of its own, not the CLI's state: the session's container mounts that, and the log is out of its reach."""
        return self.home / "egress" / self.container / "egress.log"

    def close(self) -> None:
        """The gateway and the network."""
        run(["docker", "rm", "-f", self.gateway], timeout=60)
        run(["docker", "network", "rm", self.net], timeout=60)


class ContainerExecution(ExecutionPort):
    """`image` with `env_file` (the agent's auth) and the CLI's `state` dir, holding `base`'s parent's four directories
    of this project — the base, its node places, its scratch, a temp of its own — at `/gfso-place/<name>`. Nothing else
    of the host is mounted, the host's network is shut at start, and the rest of the way out is as `network` switches it
    (`{"mode": one of NETWORK, "hosts": [...]}`: the container's switch, kept by its name; open where none was
    given)."""

    def __init__(self, name: str, image: str, env_file: str, state: str, base: str, project: str, network=None):
        self.base, self.parent = Path(base).resolve(), Path(base).resolve().parent
        if not self.parent.drive or self.parent.drive.startswith("\\\\"):
            raise ValueError(f"execution {name!r}: {base} is not on a local drive — a container cannot mount it")
        self.name, self.image, self.env_file = name, image, env_file
        self.container = re.sub(r"[^a-zA-Z0-9_.-]+", "-", f"gfso-{name}-{project}").lower()
        self.way = WayOut(self.container, name, image, Path(state))
        if network is not None:
            self.switch(network)
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

    def switch(self, network) -> None:
        """Turn the container's way out (`WayOut.switch`); a turn ends the running container at once, every call in it
        with it. Whoever turns it decides when: the declaration is turned at the project's next lookup."""
        with _START:
            before = self.way.network
            try:
                self.way.switch(network)
            finally:
                if self.way.network != before and self.container in _STARTED:
                    self.stop()

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
        """`docker run` for this project's container: sealed (`--init`, its own mounts only, no new privileges, its way
        out as switched), sleeping until the server calls into it."""
        mounts = [a for m in self.mounts for a in ("--mount", f"type=bind,src={self.parent / m},dst={INSIDE}/{m}")]
        return ["docker", "run", "-d", "--init", "--name", self.container, "--label", f"{LABEL}={self.name}",
                *self.way.run_args(),
                "--security-opt", "no-new-privileges",
                "--env-file", self.env_file, *mounts, "--mount", f"type=bind,src={self.state},dst={STATE_INSIDE}",
                "--add-host", "host.docker.internal:0.0.0.0", self.image, "sleep", "infinity"]

    def start(self) -> None:
        """The project's container, running and sealed — started once per server process, whoever asks first."""
        with _START:
            if _STARTED.get(self.container) == (self.run_args(), self.way.network) and self._running():
                return
            if why := self.unavailable():
                raise PlaceUnavailable(self.name, why)
            for d in [self.parent / m for m in self.mounts] + [self.state]:
                d.mkdir(parents=True, exist_ok=True)
            self.stop()                                                  # what a server that is gone left
            try:
                self.way.open()
                run(self.run_args(), timeout=120).check_returncode()
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                self.stop()
                raise RuntimeError(f"{self.container}: {e} — no call runs unsealed") from e
            seal = run(["docker", "exec", "-u", "0", self.container, "sh", "-c",       # uid 0: the rule is root's
                        f"{self.way.seal()} && mkdir -p /tmp/gfso-calls && chmod 1777 /tmp/gfso-calls"], timeout=60)
            if seal.returncode != 0:
                self.stop()
                raise RuntimeError(f"{self.container}: the network could not be switched — no call runs unsealed "
                                   f"({(seal.stderr or b'').decode(errors='replace')[-300:]})")
            _STARTED[self.container] = (self.run_args(), self.way.network)

    def stop(self) -> None:
        """The project's container and its way out."""
        run(["docker", "rm", "-f", self.container], timeout=60)
        self.way.close()
        _STARTED.pop(self.container, None)

    def _running(self) -> bool:
        """Is the container still up — and its allowlist's gateway, whose death would leave the project hanging on
        proxy errors with no cause said? A Docker restart (the host slept, an update) removes them under a live server,
        and every later call of the project then failed `No such container` (critic over d5c8f7a)."""
        for c in [self.container] + ([self.way.gateway] if self.way.network[0] == "allowlist" else []):
            got = run(["docker", "inspect", "-f", "{{.State.Running}}", c], timeout=30, text=True)
            if got.returncode != 0 or (got.stdout or "").strip() != "true":
                return False
        return True

    def unavailable(self):
        """The daemon's own words where it does not answer — Docker Desktop not running reads "failed to connect to the
        docker API at npipe:////./pipe/dockerDesktopLinuxEngine …" — else None."""
        try:
            got = run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=60, text=True)
        except (OSError, subprocess.TimeoutExpired) as e:
            return str(e)
        return None if got.returncode == 0 else ((got.stderr or "").strip() or f"docker info exited {got.returncode}")

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

    def copy_tree(self, src: str, dst: str) -> None:
        # inside, as the place was made: a symlink a session made in here is no link on the host (probe P5)
        r = self.run(["cp", "-a", "--", src, dst], cwd=src, timeout=1800)
        if r.returncode != 0:
            raise OSError(f"cp -a {src} {dst} failed in {self.container}: {r.stderr.strip()[-300:]}")

    def remove_tree(self, path: str) -> None:
        if not os.path.lexists(path):
            return
        r = self.run(["sh", "-c", 'chmod -R u+rwX -- "$1" 2>/dev/null; rm -rf -- "$1"', "sh", path],
                     cwd=str(Path(path).parent), timeout=600)
        if r.returncode != 0:
            raise OSError(f"rm -rf {path} failed in {self.container}: {r.stderr.strip()[-300:]}")

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
