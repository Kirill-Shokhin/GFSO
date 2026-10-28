"""Where a session or a command runs (`ExecutionPort`): `LocalExecution` — on this host, as every launch ran before
the port existed; `ContainerExecution` — inside one long-lived Linux container per (execution, project), the same server
starting every call through `docker exec`, so a project's work is isolated without a second server. The graph keeps host
paths: a container sees the base's parent as `/gfso-place`, and every path crossing the boundary is mapped both ways."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import re
import shutil
import socket
import stat
import tempfile
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from gfso.core.types import ExecutionPort, PlaceUnavailable
from gfso.config import SECRET_ENV, claude_config_dir, host_env
from gfso.adapters import door, egress
from gfso.adapters.children import adopt, at_exit, kill_tree, release, run, spawn_kw

log = logging.getLogger(__name__)

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
#: Under every switch a session's CLI reaches its model through its project's door (`Door`), which holds the credential;
#: under a closed one the door passes the model alone, nothing the provider would fetch or run elsewhere. What the
#: allowlist does NOT hold: an allowed host carries whatever the session sends it under any credentials it presents (a
#: model API that stores data is a way out to another tenant's account); inside the encrypted stream the request may
#: still name another site the same front serves — reading it needs the gateway to end TLS itself; the gateway stands on
#: Docker's bridge, so a gateway taken over is the whole way out; and each closed project takes one of Docker's address
#: pools, past which a start fails closed
NETWORK = ("open", "allowlist", "off")
#: what root holds in a project's container, where only the system's own commands run (every agent session runs in
#: its place's): enough to copy a place whatever modes its executor left on it, owners kept so a judge can work in the
#: copy. No agent process holds them: they run as the image's user, under no-new-privileges
SYSTEM_CAPS = ("CHOWN", "DAC_OVERRIDE", "DAC_READ_SEARCH", "FOWNER")


def network_of(network) -> tuple | None:
    """(mode, hosts) of a switch as given — `{"mode": one of NETWORK, "hosts": [host names]}`, None for none given — or a
    ValueError: one reading for the declaration and for the project's own switch (`set_mode`)."""
    if network is None:
        return None
    # …a value that is not one shuts, never opens: `false` or `[]` meant "no network" and read as "open" (critic)
    try:
        mode, hosts = network.get("mode", "open"), tuple(network.get("hosts") or ())
        ok = isinstance(network, dict) and mode in NETWORK and all(
            isinstance(h, str) and re.fullmatch(r"[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+", h) for h in hosts)
    except (AttributeError, TypeError):
        ok = False
    if not ok:
        raise ValueError(f"network {network!r} — a mode of {NETWORK} and host names only")
    return mode, hosts


def stricter(a: tuple | None, b: tuple | None) -> tuple:
    """The more closed of two switches, (mode, hosts) each or None for open: off < allowlist < open, two allowlists
    reaching only the hosts both name. The operator's declaration is a ceiling a project's own switch can only lower —
    let the project's word win and an operator's emergency `off` missed every project that had set `open` (critic)."""
    a, b = a or ("open", ()), b or ("open", ())
    rank = {"off": 0, "allowlist": 1, "open": 2}
    if a[0] == b[0] == "allowlist":
        both = tuple(h for h in a[1] if h in b[1])
        return ("allowlist", both) if both else ("off", ())   # reaching no host is off, without a gateway (review)
    return min(a, b, key=lambda x: rank[x[0]])
#: the gateway's address and port as a session inside an allowlisted project reaches it
GATEWAY = "gateway"
#: how the key a model client inside holds for its credential begins (`Door`) — it opens one door and nothing else
PLACEHOLDER = "held-by-the-door-"
#: what marks a container as a project's execution of THIS product — the one thing a sweep of leftovers removes
LABEL = "gfso.execution"


def grouped(project_container: str, role: str) -> list[str]:
    """The labels that show a project's containers as ONE stack in Docker Desktop, subgrouped by role — a row's twenty
    containers hung side by side, alike by name (the author, 2026-10-28: «контейнеры … для одной задачи логично держать в
    группе»). A compose project's name: lower-case letters, digits, `_`, `-`."""
    return ["--label", f"com.docker.compose.project={re.sub(r'[^a-z0-9_-]+', '-', project_container.lower())}",
            "--label", f"com.docker.compose.service={role}"]
#: the containers this server process started — one per (execution, project), whichever object asks for it — with
#: what each was started holding: a project re-created on another base gets a container of its own again
_STARTED: dict = {}
#: what names a validation's scratch beside the place it validates (`tools_llm`)
SCRATCH = ".gfso-scratch-"
#: the session containers of each project's places, by (project container, writable root)
_SESSIONS: dict = {}
#: each container's switch as last declared — the container's, not an object's: a session keeps its object for its whole
#: life, so any object starting the container must start it under the switch as it stands now (critic 4: a second
#: object of one container started it back under its own)
_SWITCH: dict = {}
#: each image's answer to `scrubs`
_SCRUBS: dict = {}
#: the model doors this server process started (`Door`) — each holds a credential, so none outlives it
_DOORS: set = set()
#: each project container's doors (`Door`), by its name
_GATES: dict = {}
_START = threading.RLock()     # a turn stops what a start holds, under the same lock


def _env_names(env_file: str) -> list[str]:
    """The variables a Docker env-file sets, by name — none where it does not read."""
    try:
        return [x.split("=", 1)[0].strip() for x in Path(env_file).read_text(encoding="utf-8").splitlines()
                if x.strip() and not x.lstrip().startswith("#")]
    except OSError:
        return []


def scrubs(execution: ExecutionPort) -> bool:
    """Can the agent CLI started by `execution` keep its tools' shells clean of its credential? On Linux its scrub needs
    bubblewrap, and told to scrub without it the CLI exits before its first turn (probed: e3-linux-agent:2, CLI
    2.1.310, every call of a row's planner cut); on Windows and macOS it needs nothing (probed on Windows). A container
    is asked once per image, and a no said in the log."""
    if not isinstance(execution, ContainerExecution):
        return sys.platform != "linux" or bool(shutil.which("bwrap"))
    if execution.image not in _SCRUBS:
        try:
            r = execution.run(["sh", "-c", "command -v bwrap"], cwd=str(execution.base), timeout=60)
        except (PlaceUnavailable, OSError, subprocess.TimeoutExpired):
            return False        # …a place that does not start is the call's to meet, where it is the project's stop
        _SCRUBS[execution.image] = r.returncode == 0
        if not _SCRUBS[execution.image]:
            log.warning(f"{execution.image} has no bubblewrap: the agent CLI cannot scrub its tools' shells there, "
                        "and its tools see its credential")
    return _SCRUBS[execution.image]


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
        run(["docker", "rm", "-f", *ids, *[f"{i}-gw" for i in ids], *_DOORS], timeout=120)
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
                got, ok = network_of(network) or ("open", ()), True
            except ValueError:
                got, ok = ("off", ()), False
            _SWITCH[self.container] = got
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
                *grouped(self.container, "gateway"),
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


class Door:
    """A project's doors to its model (`door.py`): one container per credential the project's calls hold — the one
    place each credential is, started by the first call holding it, so a credential changed while older calls run
    starts a door beside theirs rather than cutting them. Each answers only its own KEY, the placeholder its clients
    hold (`PLACEHOLDER` and a random tail): no other container on the machine spends through it. Under a closed way out
    a door stands on the project's network by a name of its own and joins Docker's bridge to reach out, passing the
    model alone; under an open one, on the bridge by its address. Read-only, unprivileged and bounded, nothing of the
    project mounted; the credential laid in its memory-backed `door.RUN`, read once and removed; its log beside the
    gateway's, out of every session's reach. Gone with its project's container and with the server."""

    def __init__(self, way: WayOut):
        self.way, self.held = way, {}            # credential digest -> (container, key)

    def url(self, credential, upstream: str) -> tuple[str, str]:
        """Where a client inside reaches `upstream` with `credential` put in, and the key it presents there."""
        d = self._digest(credential, upstream)
        closed = self.way.network[0] != "open"
        name = f"{self.way.container}-door-{d}"
        if d not in self.held or not (address := self._address(name)):
            try:
                address = self._start(name, credential, upstream, closed)
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                # …no call of the project reaches its model: the place down, its stop said as such (critic 3)
                raise PlaceUnavailable(self.way.name, f"its model door did not start ({e})") from e
        return f"http://{name if closed else address}:{door.PORT}", self.held[d][1]

    def _start(self, name: str, credential, upstream: str, closed: bool) -> str | None:
        """One door started holding `credential`, its key kept; its address on Docker's bridge."""
        run(["docker", "rm", "-f", name], timeout=60)
        self.log().parent.mkdir(parents=True, exist_ok=True)
        key = PLACEHOLDER + uuid.uuid4().hex
        run(["docker", "run", "-d", "--init", "--name", name, "--label", f"{LABEL}={self.way.name}",
             *grouped(self.way.container, "door"),
             "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--read-only", "--memory", "256m",
             "--pids-limit", "256", "--sysctl", "net.ipv4.ip_forward=0", "--tmpfs", f"{door.RUN}:size=64k,mode=1777",
             *(["--network", self.way.net, "--network-alias", name] if closed else []),
             "--mount", f"type=bind,src={Path(door.__file__).resolve()},dst=/gfso-door.py,readonly",
             "--mount", f"type=bind,src={self.log().parent},dst=/log",
             self.way.image, "python3", "/gfso-door.py", upstream, "/log/" + self.log().name,
             name if closed else "0.0.0.0", "1" if closed else "0"], timeout=120).check_returncode()
        _DOORS.add(name)                      # …at once: a start cut after this still ends with the server
        # …laid by a `docker exec` whose environment is its own and gone with it: in no configuration Docker keeps
        laid = json.dumps({"kind": credential.kind, "value": credential.value, "key": key})
        run(["docker", "exec", "-e", "GFSO_DOOR_LAID", name, "sh", "-c",
             f'printf %s "$GFSO_DOOR_LAID" > {door.RUN}/laid && mv {door.RUN}/laid {door.RUN}/credential'],
            timeout=60, env={**host_env(), "GFSO_DOOR_LAID": laid}).check_returncode()
        if closed:
            run(["docker", "network", "connect", "bridge", name], timeout=60).check_returncode()
        self.held[self._digest(credential, upstream)] = (name, key)
        return self._address(name)

    def _digest(self, credential, upstream: str) -> str:
        """What a door holds and how it is shaped — the switch decides where it stands and what it passes."""
        return hashlib.sha256(f"{credential.kind}:{credential.value}:{upstream}:{self.way.network}".encode()).hexdigest()[:12]

    @staticmethod
    def _address(name: str) -> str | None:
        """Its address on Docker's bridge while it runs, else None."""
        got = run(["docker", "inspect", "-f", "{{.State.Running}} {{.NetworkSettings.Networks.bridge.IPAddress}}",
                   name], timeout=30, text=True)
        up, _, address = (got.stdout or "").strip().partition(" ")
        return address or None if got.returncode == 0 and up == "true" else None

    def log(self) -> Path:
        """Every request the doors passed or refused, written by the door as it happens."""
        return self.way.home / "door" / self.way.container / "door.log"

    def close(self) -> None:
        """Every door of the project, and the credentials they hold."""
        if names := [n for n, _ in self.held.values()]:
            run(["docker", "rm", "-f", *names], timeout=60)
            _DOORS.difference_update(names)
        self.held = {}


class ContainerExecution(ExecutionPort):
    #: does a session's CLI run here, its state mounted? Not in the project's container: every session runs in its
    #: place's (`session`), and the project's runs the plan's probes, written by agents — with the state mounted they
    #: read every place's conversations under it (critic over the CLI state per place)
    holds_sessions = False
    apart = True

    """`image` with an optional `env_file` (settings of the image, never a credential: the provider gives its own to its
    process, `_exec_argv`) and the CLI's `state` dir, holding `base`'s parent's four directories
    of this project — the base, its node places, its scratch, a temp of its own — at `/gfso-place/<name>`. Nothing else
    of the host is mounted, the host's network is shut at start, and the rest of the way out is as `network` switches it
    (`{"mode": one of NETWORK, "hosts": [...]}`: the container's switch, kept by its name; open where none was
    given)."""

    def __init__(self, name: str, image: str, env_file: str | None, state: str, base: str, project: str,
                 network=None):
        self.base, self.parent = Path(base).resolve(), Path(base).resolve().parent
        if not self.parent.drive or self.parent.drive.startswith("\\\\"):
            raise ValueError(f"execution {name!r}: {base} is not on a local drive — a container cannot mount it")
        if env_file and (held := sorted(k for k in _env_names(env_file) if SECRET_ENV.search(k))):
            # …a second place for a credential, live in every call the system itself makes inside — its probes, git, a
            # pinned `make test` running the executor's scripts: the token reached them all (critic over S4)
            raise ValueError(f"execution {name!r}: its env_file holds {', '.join(held)} — a credential is its "
                             f"provider's, set by `gfso credential <provider>`, never the container's")
        self.name, self.image, self.env_file = name, image, env_file
        self.container = re.sub(r"[^a-zA-Z0-9_.-]+", "-", f"gfso-{name}-{project}").lower()
        self.way = WayOut(self.container, name, image, Path(state))
        # …one per container, whichever object of it asks: two roles' objects kept a door each, and a switch one turned
        # left the other's standing in the old shape (critic over the door v2)
        self.gate = _GATES.setdefault(self.container, Door(self.way))
        if network is not None:
            self.switch(network)
        # THE CLI'S STATE IS THE PROJECT'S: shared by an execution's projects, every E3 row (all at /gfso-place/ws) read
        # and appended to another row's conversation (critic over d5c8f7a, measured on two containers)
        self.state = Path(state) / self.container
        b = self.base.name
        # the last is the system's own: its copies and checks, which no session but the one handed a copy reaches
        self.mounts = [b, f".gfso-nodes-{b}", f".gfso-scratch-{b}", f".gfso-tmp-{b}", f".gfso-sys-{b}"]
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

    def _inside_cwd(self, cwd: str) -> str:
        """The container's path of a place the call runs in — inside what it mounts, else refused: the agent would
        stand where nothing of the project is, or the call would reach outside what the container holds."""
        here = Path(cwd).resolve()
        if not any(here.is_relative_to(src) for src, _ in self._mounts()):
            raise ValueError(f"{cwd} is not inside {self.container}'s mounts ({', '.join(self.mounts)} of {self.parent})")
        return INSIDE + "/" + here.relative_to(self.parent).as_posix()

    def run_args(self) -> list[str]:
        """`docker run` for this project's container: sealed (`--init`, its own mounts only, no new privileges, its way
        out as switched), sleeping until the server calls into it."""
        mounts = [a for src, ro in self._mounts() for a in (
            "--mount", f"type=bind,src={src},dst={self.to_inside(str(src))}" + (",readonly" if ro else ""))]
        return ["docker", "run", "-d", "--init", "--name", self.container, "--label", f"{LABEL}={self.name}",
                *grouped(self.way.container, "places" if self.holds_sessions else "system"),
                *self.way.run_args(), *([] if self.holds_sessions else [a for c in SYSTEM_CAPS for a in ("--cap-add", c)]),
                "--security-opt", "no-new-privileges",
                *(["--env-file", self.env_file] if self.env_file else []), *mounts,
                *(["--mount", f"type=bind,src={self.state},dst={STATE_INSIDE}"] if self.holds_sessions else []),
                "--add-host", "host.docker.internal:0.0.0.0", self.image, "sleep", "infinity"]

    def _mounts(self) -> list:
        """(host directory, read-only?) for each directory the container holds: the project's four, all writable."""
        return [(self.parent / m, False) for m in self.mounts]

    def session(self, cwd: str) -> "ExecutionPort":
        """The container of the place a session works in (`PlaceContainer`): it writes there alone, reads the base,
        and never sees another node's place."""
        try:
            rw = _writable_root(Path(cwd).resolve(), self)
        except ValueError:
            return self        # refused where the call starts, after the place's own health — a dead place stops first
        for gone in [k for k in list(_SESSIONS) if k[0] == self.container and not os.path.isdir(k[1])]:
            if s := _SESSIONS.pop(gone, None):            # a round, a contact, a no-place call: its directory is gone
                s.stop()
                shutil.rmtree(s.state, ignore_errors=True)   # …and its CLI's state with it: nothing will resume there
        with _START:
            return _SESSIONS.setdefault((self.container, os.path.normcase(rw)), PlaceContainer(self, rw))

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
                self._open_the_way()
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

    def _open_the_way(self) -> None:
        self.way.open()


    def stop(self) -> None:
        """The project's container, its sessions' and its way out."""
        for key in [k for k in _SESSIONS if k[0] == self.container]:
            _SESSIONS.pop(key).stop()
        run(["docker", "rm", "-f", self.container], timeout=60)
        self.gate.close()                                 # …first: a network with a member is not removed
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

    def _exec_argv(self, args, env, cwd, call: str, root: bool = False) -> tuple[list[str], dict]:
        """`docker exec` of one call, and the environment of the `docker` client that runs it. What the call itself sets
        goes in, not the host's environment — its PATH is the container's own; a credential by its NAME alone, its value
        in the client's environment, so no process list on the host shows it (`docker exec -e NAME`) — given to this
        call's process only, never to the container (S4: the provider's credential, one process)."""
        self.start()
        here = host_env()
        # …a credential even when the host holds the same value: the container has no other way to it
        own = {k: v for k, v in (env or {}).items()
               if here.get(k) != v or k.startswith("ANTHROPIC_") or SECRET_ENV.search(k)}
        secret = {k: v for k, v in own.items() if SECRET_ENV.search(k)}
        return (["docker", "exec", "-i", *(["-u", "0"] if root else []), "-w", self._inside_cwd(cwd), "-e", f"GFSO_CALL={call}",
                 *[a for k, v in own.items() for a in ("-e", k if k in secret else f"{k}={self.to_inside(v)}")],
                 self.container, "sh", "-c", f'echo $$ >/tmp/gfso-calls/{call}; exec "$@"', "sh",
                 *map(self.to_inside, args)], {**here, **secret})

    def popen(self, args, *, env, cwd, **pipes):
        call = uuid.uuid4().hex
        argv, client = self._exec_argv(args, env, cwd, call)
        return _Call(LocalExecution().popen(argv, env=client, cwd=str(self.parent), **pipes), self, call)

    def run(self, args, *, cwd, timeout, env=None, root: bool = False):
        call = uuid.uuid4().hex
        argv, client = self._exec_argv(args, env, cwd, call, root)
        try:
            done = run(argv, timeout=timeout, cwd=str(self.parent), env=client, text=True,
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
        # …by root, in the project's container (`SYSTEM_CAPS`): as the agent, one unreadable file the executor left in
        # its place failed every copy and kept its delivery from being judged (critic over the judges slice) — and only
        # where nothing stands: into a directory or a link left there, `cp -a` copies INTO it (critic 3)
        if os.path.lexists(dst):
            raise OSError(f"{dst} already exists: a copy is made only where nothing stands")
        r = self.run(["cp", "-a", "--", src, dst], cwd=src, timeout=1800, root=True)
        if r.returncode != 0:
            raise OSError(f"cp -a {src} {dst} failed in {self.container}: {r.stderr.strip()[-300:]}")

    def remove_tree(self, path: str) -> None:
        if not os.path.lexists(path):
            return
        for key in [k for k in _SESSIONS if k[0] == self.container and Path(k[1]).is_relative_to(Path(path).resolve())]:
            _SESSIONS.pop(key).stop()                     # a place going takes its session's container with it
        r = self.run(["sh", "-c", 'chmod -R u+rwX -- "$1" 2>/dev/null; rm -rf -- "$1"', "sh", path],
                     cwd=str(Path(path).parent), timeout=600)
        if r.returncode != 0:
            raise OSError(f"rm -rf {path} failed in {self.container}: {r.stderr.strip()[-300:]}")

    def end(self, proc) -> None:
        """The call's group inside, and whatever it started that left the group (`setsid`), found by its mark — killing
        the `docker exec` client alone leaves them all running (probe P1)."""
        if isinstance(proc, _Call) and proc.execution is not self:
            return proc.execution.end(proc)               # in the container the call ran in, a session's own
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

    def temp_of(self, place) -> str:
        """The temp of the node `place` belongs to (`_owner`): its executor, its validations, its issuer's contacts
        share it, and no other node's session holds it. A path outside the project's places: the temp itself."""
        try:
            owner = _owner(_writable_root(Path(place).resolve(), self)) if place else None
        except ValueError:
            owner = None
        if owner is None:
            return self.temp_root()
        if owner.is_relative_to(self.parent / self.mounts[3]):
            return str(owner)                            # a directory of the temp lent to one call is its own temp
        d = self.parent / self.mounts[3] / f"node-{hashlib.sha1(os.path.normcase(owner).encode()).hexdigest()[:12]}"
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    def scratch(self, prefix: str, *, system: bool = False):
        (d := Path(self.temp_root()) if not system else self.parent / self.mounts[4]).mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(prefix=prefix, dir=str(d), ignore_cleanup_errors=True)

    def state_dir(self):
        return self.state

    def state_seen(self) -> str:
        return STATE_INSIDE


def _writable_root(cwd: Path, project: "ContainerExecution") -> Path:
    """What a session working in `cwd` may write: a validation's round of the scratch it stands in, whole (its copy
    of the delivery and its own files) — `.gfso-scratch-<place>/<round>`, beside the base or beside a node's clone;
    else the place itself — the base for a root, a node's clone (`.gfso-nodes-<base>/<project>/<key>`), a temp
    directory of its own."""
    rel = cwd.relative_to(project.parent) if cwd.is_relative_to(project.parent) else None
    if rel is None or not rel.parts or rel.parts[0] not in project.mounts:
        raise ValueError(f"{cwd} is not inside {project.container}'s mounts ({', '.join(project.mounts)})")
    if (at := next((i for i, p in enumerate(rel.parts) if p.startswith(SCRATCH)), None)) is not None:
        return project.parent.joinpath(*rel.parts[:at + 2])
    depth = {project.mounts[0]: 1, project.mounts[1]: 3, project.mounts[3]: 2, project.mounts[4]: 2}[rel.parts[0]]
    return project.parent.joinpath(*rel.parts[:depth])


def _owner(rw: Path) -> Path:
    """The place a writable root serves: a validation's round, the node it validates; else itself."""
    return rw.parent.parent / rw.parent.name[len(SCRATCH):] if rw.parent.name.startswith(SCRATCH) else rw


def _scratch_of(place: Path) -> Path:
    """Where a validation of the delivery in `place` keeps its rounds — beside it (`tools_llm`'s scratch)."""
    return place.parent / f"{SCRATCH}{place.name}"


class PlaceContainer(ContainerExecution):
    """One session's container: its place writable (`rw`), the base read-only — a node's clone borrows the base's
    objects, and nothing it does reaches the base's refs — a validation's earlier rounds read-only, nothing of another
    node's place nor of the system's own checks. Its way out is its project's; the system's own commands stay in the
    project's container. Started on its session's first call, gone with its directory, its place or its project. Its
    temp is its node's own (`temp_of`): what the system lays for the node's sessions, no other node's reads — save that
    whatever works in the base shares the base's: every node with no git base, a root's sessions, a parent's consent
    before its own place is made. Its CLI's state is its place's own, under its project's. No judge shares a place with
    its executor: a validation and an issuer's contact, a root's included, work each in a round of their own, on a copy,
    and a delivery that could not be copied is not judged — the place down (`apart`). NOT HELD YET: the sessions that work in the base
    share its CLI state — a root's executor and a parent's consent before its own place is made; a tool-loop provider's
    issuer reads a node's inputs by its shell only; a round's container stands until its round is pruned, a done node's until its directories go or the
    project stops."""

    def __init__(self, project: ContainerExecution, rw: Path):
        self.__dict__.update(project.__dict__)
        self.project, self.rw = project, rw
        key = hashlib.sha1(os.path.normcase(rw).encode()).hexdigest()[:12]
        self.container = f"{project.container}-s-{key}"
        # the CLI's state of THIS place, under its project's — mounted here alone: the others' conversations, the
        # system's notes on them and the CLI's own memory of another place are not in reach of any container
        self.state, self.holds_sessions = project.state / "places" / key, True

    def _mounts(self) -> list:
        """The base read-only unless the place is the base; a validation's round writable, its earlier rounds
        read-only beneath it; a place writable, its validations' scratch read-only — a node's standing findings name
        probes there; the temp writable."""
        tmp, system = self.parent / self.mounts[3], self.parent / self.mounts[4]
        if self.rw.parent.name.startswith(SCRATCH):
            own = [(self.rw.parent, True), (self.rw, False)]
        elif self.rw.is_relative_to(tmp):
            return [*([] if self.rw == self.base else [(self.base, True)]), (self.rw, False)]
        elif self.rw.is_relative_to(system):
            own = [(self.rw, False)]                     # the one directory of the system's a session is handed
        else:
            # its validations' scratch read-only beside its place, a root's base as a node's clone: its rounds hold the
            # probes the node's standing findings re-run, which the node's own executor must not rewrite (critic 3 over
            # the session slice); no judge works here (`apart`)
            (scratch := _scratch_of(self.rw)).mkdir(parents=True, exist_ok=True)
            own = [(self.rw, False), (scratch, True)]
        return [*([] if self.rw == self.base else [(self.base, True)]), *own, (Path(self.temp_root()), False)]

    def temp_root(self):
        """Its node's own temp (`ContainerExecution.temp_of`), not the project's."""
        return self.project.temp_of(str(self.rw))


    def session(self, cwd: str) -> "ExecutionPort":
        return self if Path(cwd).resolve().is_relative_to(self.rw) else self.project.session(cwd)

    def door(self, credential, upstream: str):
        """Its project's door (`Door`), once the project's network stands."""
        with _START:
            self.project.start()
            return self.gate.url(credential, upstream)

    def _open_the_way(self) -> None:
        self.project.start()                              # the project's network and gateway stand before any session
        # …and a project started here stopped its sessions first, this one among them: it is tracked again
        _SESSIONS[(self.project.container, os.path.normcase(self.rw))] = self

    def stop(self) -> None:
        """This session's container only: the way out is its project's."""
        run(["docker", "rm", "-f", self.container], timeout=60)
        _STARTED.pop(self.container, None)


class _Call:
    """A call inside, as the host's code reads a process: what it is fed goes in with container paths, what it prints
    comes out with host paths."""

    def __init__(self, client, execution: ContainerExecution, call: str):
        self.client, self.call, self.execution = client, call, execution
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
        self.execution.end(self)


class _Mapped:
    def __init__(self, stream, mapping):
        self._s, self._map = stream, mapping

    def write(self, text: str):
        """Write `text` mapped."""
        return self._s.write(self._map(text))

    def close(self):
        """Close the stream underneath."""
        self._s.close()
