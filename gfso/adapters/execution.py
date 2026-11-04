"""Where a session or a command runs (`ExecutionPort`): `LocalExecution` — on this host, as every launch ran before
the port existed; `ContainerExecution` — inside one long-lived Linux container per (execution, project), the same server
starting every call through `docker exec`, so a project's work is isolated without a second server. The graph keeps host
paths as the system's names: a container sees the base's parent as `/gfso-place`, and every path crossing the boundary
is mapped both ways — while under the project's own directory nothing stands on the host: it is the project's Docker
volume, mounted at the same inside path."""
from __future__ import annotations

import contextlib
import copy
import datetime
import hashlib
import io
import ipaddress
import json
import logging
import os
import re
import shutil
import socket
import stat
import tarfile
import tempfile
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from gfso.core.types import (BATCH, HOST, IN_THE_WORKS_PATH, THIS_HOST, LAID, MADE, NODES, PROJECT_ID, SCRATCH, VOLUME, WORK_PATH, ExecutionPort,
                             FilesPort, PlaceUnavailable, base_named, nodes_dir, place_name)
from gfso.config import (DEFAULT_PROJECT, ROOT_ID, SECRET_ENV, data_dir, claude_config_dir, container_limits, local_agents,
                         memory_ceiling, network_record_off, new_flows, node_disk, executions, executions_path, host_env, subprocess_env)
from gfso.adapters import door, egress, lfs, shell
from gfso.adapters.records import append, said_of
from gfso.places import same_place
from gfso.adapters.children import adopt, at_exit, kill_tree, release, run, run_printing, spawn_kw

log = logging.getLogger(__name__)

INSIDE = "/gfso-place"
#: the agent CLI's state inside the container — the image's `CLAUDE_CONFIG_DIR`
STATE_INSIDE = shell.STATE
#: Docker Desktop forwards this network to the HOST'S LOOPBACK, :8000 included (probe P8): a session inside could
#: otherwise sign the graph it works under (§10.3)
HOST_NET = "192.168.65.0/24"
#: …and on Docker Engine the host's bridge address is the container's default gateway (172.17.0.1): read at seal time
#: from the kernel's own table — no `ip` in an image needed — and shut too; what it routes onward stays open. Its
#: OTHER addresses (its LAN one) are not shut: a host service listening on 0.0.0.0 answers there (the server listens on
#: loopback, out of reach)
_GATEWAY_OF = ("awk 'function h(s){return index(\"0123456789ABCDEF\",substr(s,1,1))*16+"
               "index(\"0123456789ABCDEF\",substr(s,2,1))-17} $2==\"00000000\"{g=$3; print h(substr(g,7,2))\".\""
               "h(substr(g,5,2))\".\"h(substr(g,3,2))\".\"h(substr(g,1,2)); exit}' /proc/net/route")
#: the on-link network of a container (its address's own, where its project's door stands under an open switch), as
#: `dest/mask` read off /proc/net/route like `_GATEWAY_OF`
_SUBNET_OF = ("awk 'function h(s){return index(\"0123456789ABCDEF\",substr(s,1,1))*16+"
              "index(\"0123456789ABCDEF\",substr(s,2,1))-17} function ip(g){return h(substr(g,7,2))\".\"h(substr(g,5,2))"
              "\".\"h(substr(g,3,2))\".\"h(substr(g,1,2))} NR>1 && $2!=\"00000000\" && $3==\"00000000\"{print ip($2)\"/\"ip($8);"
              " exit}' /proc/net/route")
#: what an open switch keeps shut beside the host — the user's own networks: private, carrier-grade NAT (a tailnet),
#: link-local (a cloud's metadata). Open is the way OUT (the author: «рубильниками просто наружу»), not into the
#: network the machine stands on: a front on the machine's tailnet address forwarded a session to the server's door
#: (critic over the stream in use)
#: the system's own calls into a container: by this PATH and an absolute shell, never the image's PATH, which starts at
#: the agent's home: a command laid `sh` there, and the root read of the action record ran it — the record forged,
#: what it held erased (critic over the stream in use, run live)
SYSTEM_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
SYS = ("-e", f"PATH={SYSTEM_PATH}")
#: the band a project's doors listen in (`WayOut.door_port`), below the ports the kernel hands out
DOOR_PORTS = 20000
#: the ports the kernel hands a connection that names none (`ip_local_port_range`, which no session's uid may set)
EPHEMERAL = "32768:60999"
PRIVATE_NETS = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16")
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
#: what marks a container as a project's execution of THIS product — the one thing a sweep of leftovers removes; its
#: volume carries it too, and no sweep removes that: it holds the project's work (`ContainerExecution.drop`)
LABEL = "gfso.execution"
#: the other labels the system sets: whose installation, which project — every making (`identity`); who works in a
#: session's container, on which node, as what (`PlaceContainer`)
HOME, PROJECT, ROLE, NODE, AGENT = "gfso.home", "gfso.project", "gfso.role", "gfso.node", "gfso.agent"
#: the project's id (`PROJECT_ID` of its record) on each volume made for it — what an orphan is known by (`resources`)
ID = "gfso.project_id"
#: the project's directory of its sessions' CLI state — a volume of its own (`Volume`), which only its keeper mounts
#: whole and each session its own place's of (`PlaceContainer`)
STATE_DIR = ".gfso-state"
#: the base inside the project's places volume — mounted wherever the system names the base, at the same inside path
#: the user's repository was: a clone of the user's HEAD imported for the project's root (`Volume.import_base`)
BASE_DIR = ".gfso-base"
#: the base as a session reads it (`_READ_COPY`), and the ref in the base that names what it holds
BASE_READ, READ_REF = ".gfso-base-read", "refs/gfso/read"
#: what keys, in a project's settings, the record of its base's import: {"for": the root, commit, at}
IMPORTED = "imported"
#: a system container's own memory-backed directory — its script laid there by the system, its log written there:
#: nothing of the host is mounted, and `docker cp` writes no read-only root nor sees a tmpfs
OWN = "/gfso-own"


def identity(execution: str, project: str) -> dict:
    """What marks a container, a network or a volume as this installation's, of `project` under `execution` — set by the
    system at its making, out of any agent's reach: what a sweep removes (`end_leftovers`) and what the resource view
    counts (`resources`). Without the home a second installation's start swept the first's running containers."""
    return {LABEL: execution, PROJECT: project, HOME: _home()}


def labelled(execution: str, project: str) -> list[str]:
    """`identity` as `docker run` / `docker network create` flags."""
    return [a for k, v in identity(execution, project).items() for a in ("--label", f"{k}={v}")]


def grouped(project_container: str, role: str) -> list[str]:
    """The labels that show a project's containers as ONE stack in Docker Desktop, subgrouped by role — a row's twenty
    containers hung side by side, alike by name (the author, 2026-10-28: «контейнеры … для одной задачи логично держать в
    группе»). A compose project's name: lower-case letters, digits, `_`, `-`."""
    return ["--label", f"{GROUP}={re.sub(r'[^a-z0-9_-]+', '-', project_container.lower())}",
            "--label", f"com.docker.compose.service={role}"]


#: the label a project's containers share as one stack (`grouped`)
GROUP = "com.docker.compose.project"


#: the base read as a container reads it — through its own mount, nothing written into it: its listing, and its git's
#: HEAD and objects where it has a git
_BASE_READ = ('ls "$1" >/dev/null && { [ ! -e "$1/.git/HEAD" ] || { cat "$1/.git/HEAD" >/dev/null && '
              'ls "$1/.git/objects" >/dev/null; }; }')


#: the image a delegated session works in when the installation declares none of its own (`gfso setup` builds it)
AGENT_DOCKERFILE = Path(__file__).parent / "agent.Dockerfile"
#: the oldest Docker Desktop whose containers cannot reach its Engine API (CVE-2025-9074, fixed in 4.44.3)
DESKTOP_FLOOR = (4, 44, 3)


def below_floor(platform: str) -> "str | None":
    """The floor `platform` (`docker version`'s server platform name) stands below, or None: a Docker Desktop older than
    `DESKTOP_FLOOR`; an engine that is no Desktop has no such API in its containers' reach."""
    if not (m := re.match(r"Docker Desktop (\d+)\.(\d+)\.(\d+)", platform or "")):
        return None
    return None if tuple(map(int, m.groups())) >= DESKTOP_FLOOR else "Docker Desktop " + ".".join(map(str, DESKTOP_FLOOR))


def refused_docker(version: str, platform: str) -> "str | None":
    """Why this Docker (`docker version`: its engine's `version`, its `platform` name) holds none of the boundaries drawn
    with it, or None: a Docker Desktop whose containers reach its own API; a Linux engine whose internal network still
    forwards name lookups out, which is what `off` stands on (CVE-2024-29018: fixed in 23.0.11, 25.0.5 and 26.0.0, the 24
    line never). A version that does not read is no refusal: nothing says it is old."""
    if below := below_floor(platform):
        return (f"{platform} is older than {below}: a container there reaches Docker's own API unauthenticated "
                f"(CVE-2025-9074) — update Docker Desktop")
    if platform.startswith("Docker Desktop") or not (m := re.match(r"(\d+)\.(\d+)\.(\d+)", version or "")):
        return None
    v = tuple(map(int, m.groups()))
    if v >= (26, 0, 0) or (25, 0, 5) <= v < (26, 0, 0) or (23, 0, 11) <= v < (24, 0, 0):
        return None
    return (f"Docker Engine {version} forwards name lookups out of an internal network (CVE-2024-29018), so `off` would "
            f"not hold — update to 25.0.5 or later")


def _unavailable(ex, storage: bool):
    """Why `ex` cannot start a call (`ExecutionPort.unavailable`): the daemon's own words where it does not answer —
    Docker Desktop not running reads "failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine
    …" — else, with `storage`, the storage's: the base read through the running project container's OWN mount (a fresh
    mount of it passed while the standing ones threw I/O errors, engineering 2026-10-28, row 2: the daemon answering,
    every session dying, the probe saying "up" for 35 min); and, by a container of its own, a file written, read and
    removed in the project's places volume where it is made, its base read there — else None."""
    try:
        got = run(["docker", "version", "--format", "{{.Server.Version}}|{{.Server.Platform.Name}}"], timeout=60, text=True)
    except (OSError, subprocess.TimeoutExpired) as e:
        return str(e)
    if got.returncode:
        return (got.stderr or "").strip() or f"docker version exited {got.returncode}"
    engine, _, platform = got.stdout.strip().partition("|")
    if refused := refused_docker(engine, platform):
        return refused
    if not storage:
        return None
    p = ex.project if isinstance(ex, PlaceContainer) else ex
    try:
        if p.container in _STARTED:
            got = run(["docker", "exec", *SYS, p.container, "/bin/sh", "-c", _BASE_READ, "sh", p.to_inside(str(p.base))],
                      timeout=120, text=True)
            if got.returncode and not _GONE.search(got.stderr or ""):
                return f"its storage does not answer: {(got.stderr or got.stdout or '').strip()[-300:]}"
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"its storage does not answer ({e})"
    try:                                     # …its volume asked first, never made by the probe (`Volume.require`)
        p.volume.require(places := p.volume.mount(p.own, False, "/p"))
    except PlaceUnavailable as e:
        return e.why
    except LookupError:
        return None                          # …not made yet: its making is `Volume.ready`'s
    try:
        got = run(["docker", "run", "--rm", *labelled(p.name, p.project_name), "--network", "none", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges", *container_limits(), *ceiling(), *places, p.image,
                   "sh", "-c", 'f=/p/.gfso-probe-$$ && echo ok > "$f" && cat "$f" >/dev/null && rm -f "$f" && '
                   '{ [ ! -d "$1" ] || ' + _BASE_READ + "; } && echo ok", "sh", f"/p/{BASE_DIR}"],
                  timeout=120, text=True)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"its storage does not answer ({e})"
    return None if got.returncode == 0 and got.stdout.strip() == "ok" else \
        f"its storage does not answer: {(got.stderr or got.stdout or '').strip()[-300:]}"


#: the bounds of a door or a gateway: a few small processes of the system's own, no swap past them
_SMALL = ("--memory", "256m", "--memory-swap", "256m", "--pids-limit", "256")

#: the one cgroup of Docker's VM every installation's containers stand in, its memory the machine's ceiling (`ceiling`)
CEILING_GROUP = "gfso"
#: what writes its limit: a shell of an image pinned by digest — not an execution's image, which is trusted only to run
#: agents' code confined, while this container can set or end any cgroup of the VM
CEILING_IMAGE = "busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662"
#: a start re-writes the limit at most this often: a Docker restarted under the server made the group anew, unlimited
CEILING_RELAY_S = 300.0
_CEILING: dict = {}
_CEILING_LOCK = threading.Lock()


def ceiling() -> list[str]:
    """`--cgroup-parent` of every container the system makes: one cgroup of Docker's VM, shared by every installation on
    it, whose memory bounds their SUM (`memory_ceiling`, written by `lay_ceiling`), where each container alone is bounded
    by `container_limits` — so many runaways at once, a delivery's in every batch of its validation, of any number of
    installations, end inside that share. Decided once per server process by Docker's cgroups and never changed by
    laying the limit, so no running container is ever restarted over it: cgroupfs v2 (Docker Desktop's) takes the
    group; anything else — a systemd driver, cgroup v1 — takes none, said in the log, and each container is bounded
    alone. Docker not answering decides nothing yet: then nothing starts either."""
    with _CEILING_LOCK:
        if "flags" not in _CEILING:
            try:
                info = run(["docker", "info", "--format", "{{.CgroupDriver}} {{.CgroupVersion}} {{.MemTotal}}"],
                           timeout=60, text=True)
            except (OSError, subprocess.TimeoutExpired):
                return []
            if info.returncode:
                return []
            driver, version, total = (info.stdout.split() + ["", "", ""])[:3]
            if (driver, version) == ("cgroupfs", "2"):
                _CEILING["flags"] = ["--cgroup-parent", f"/{CEILING_GROUP}"]
            else:
                log.warning(f"no memory ceiling over the system's containers: Docker's cgroups are {driver} v{version};"
                            f" each container is bounded alone")
                _CEILING["flags"] = []
        return _CEILING["flags"]


def lay_ceiling() -> None:
    """The ceiling's limit written into its group, made where it is not — at a start, at most every `CEILING_RELAY_S`
    while it holds. By a container of the system's own on `CEILING_IMAGE`, its own shell: as root with one capability
    (to write the cgroup's files), no network, its root read-only, mounting Docker's cgroup tree, which no other container
    mounts. Every failure is said in the log: until a later one holds, the group stands with no limit of its own."""
    if not ceiling():
        return
    with _CEILING_LOCK:
        if time.monotonic() - _CEILING.get("laid", float("-inf")) < CEILING_RELAY_S:
            return
        try:
            # …of Docker's memory as it is NOW: a Docker given less memory and restarted under the server took it
            info = run(["docker", "info", "--format", "{{.MemTotal}}"], timeout=60, text=True)
            size = memory_ceiling(int(info.stdout.strip()))
            got = run(["docker", "run", "--rm", "--network", "none", "--cap-drop", "ALL", "--cap-add", "DAC_OVERRIDE",
                       "--security-opt", "no-new-privileges", "--read-only", *_SMALL,
                       "--mount", "type=bind,src=/sys/fs/cgroup,dst=/cg", "-u", "0", "--entrypoint", "sh",
                       CEILING_IMAGE, "-c",
                       'mkdir -p "/cg/$1" && echo "$2" > "/cg/$1/memory.max" && echo 0 > "/cg/$1/memory.swap.max"',
                       "sh", CEILING_GROUP, str(size)], timeout=120, text=True)
            why = (got.stderr or "").strip()[-200:] if got.returncode else None
        except (OSError, ValueError, subprocess.TimeoutExpired) as e:
            why = str(e)
        if why is None:
            _CEILING["laid"] = time.monotonic()
        else:
            log.warning(f"the memory ceiling over the system's containers was not written ({why}): their sum stands "
                        f"unbounded until a later start writes it")


#: past this share of the ceiling, in memory no reclaim gives back, the watch ends the work standing furthest over its
#: fair share; how often it reads; what a work must hold to count among those the ceiling is shared by
CEILING_ACT, CEILING_WATCH_S, CEILING_FLOOR = 0.85, 2.0, 64 * 2 ** 20
#: one read of the group: its `memory.max`, then `<name> <memory.current> <file> <shmem>` for the group itself (`.`) and
#: each directory in it, by a reader of the system's own that mounts Docker's cgroup tree read-only
_READ_GROUP = ('[ -d "/cg/$1" ] || exit 0; '     # …no group yet, no work yet: nothing to read, the reader no worse for it
               'cd "/cg/$1" && cat memory.max && for d in . */; do d=${d%/}; [ -f "$d/memory.stat" ] && '
               'echo "$d" "$(cat "$d/memory.current")" "$(awk \'$1=="file"||$1=="shmem"{printf "%s ",$2}\' "$d/memory.stat")"; done')


def _held(current: int, file: int, shmem: int) -> int:
    """What a cgroup holds that no reclaim gives back: all it is charged, less its page cache — save the cache that is
    memory (shmem: tmpfs, a memfd). Read whole, the watch fired on an honest writer's cache the kernel would have
    dropped and ended its neighbour; read as anon alone, a memfd runaway was invisible and a neighbour paid (critic r3)."""
    return current - (file - shmem)


def _over_share(read: str, unit_of) -> list[str]:
    """The containers to end, from a read of the group (`_READ_GROUP`): none while what it holds past reclaim stands
    below `CEILING_ACT` of its max; else every container of the work standing furthest over its fair share, if one
    stands over it — the ceiling over the works holding at least `CEILING_FLOOR`: shared among idle ones too, the share
    shrank and an honest work paid for theirs (critic r3). A work is one node's, whatever number of containers it runs
    in (`unit_of`: ids → {container id: its work}): per container, a runaway spread over several outweighed none of
    them and an honest one paid (critic r2)."""
    lines = read.splitlines()
    try:
        top, rows = int(lines[0]), [x.split() for x in lines[1:]]
        held = {r[0]: _held(*map(int, r[1:4])) for r in rows if len(r) == 4}
    except (ValueError, IndexError):
        return []
    group = held.pop(".", None)
    held = {i: n for i, n in held.items() if re.fullmatch(r"[0-9a-f]{64}", i)}
    if group is None or group < top * CEILING_ACT or not held:
        return []
    units, of = {}, unit_of(list(held))
    for i in held:
        units.setdefault(of.get(i, i), []).append(i)
    sums = {u: sum(held[i] for i in ids) for u, ids in units.items()}
    share = top // max(1, sum(n >= CEILING_FLOOR for n in sums.values()))
    worst = max(sums, key=sums.get)
    return units[worst] if sums[worst] > share else []


#: what names the reader, so a sweep of leftovers knows it for the system's
READER = "gfso.ceiling-reader"


def _units(ids: list) -> dict:
    """{container id: the node's work it belongs to} — read off the labels the system set at its making (`identity`,
    `PlaceContainer._labels`, `Commands`): its installation, project and node; one without a node, a work alone."""
    got = run(["docker", "inspect", "-f", f'{{{{.Id}}}} {{{{index .Config.Labels "{HOME}"}}}}|{{{{index .Config.Labels '
               f'"{PROJECT}"}}}}|{{{{index .Config.Labels "{NODE}"}}}}', *ids], timeout=60, text=True)
    out = {}
    for line in (got.stdout or "").splitlines():
        i, _, key = line.partition(" ")
        if key and "<no value>" not in key:
            out[i] = key
    return out


#: what must know of a container of work before any code of an agent's runs in it (`netrecord`)
ON_START: list = []
_WATCH = threading.Event()
#: the containers the watch ended, by name: what ran in them was ended by a neighbour's pressure, not by what it ran
_WATCH_ENDED: set = set()


def ended_by_watch(ex) -> bool:
    """Was `ex`'s container ended by the ceiling's watch (`_watch_ceiling`)? A judge's copy or build ended so is no
    verdict on its delivery — a neighbour near the ceiling would steer it (critic) — but a copy to make again."""
    return isinstance(ex, ContainerExecution) and ex.container in _WATCH_ENDED


def watch_ceiling() -> None:
    """The ceiling's watch, for this server's life (`_watch_ceiling`) — started by the server, once, whether or not
    Docker answers yet: it asks again each turn."""
    if not _WATCH.is_set():
        _WATCH.set()
        threading.Thread(target=_watch_ceiling, name="gfso-ceiling", daemon=True).start()


def _own_of(ids: list) -> list:
    """Those of the containers `ids` this installation made. Another's is its own server's to end, which reads the same
    group: what a watch ended it remembers in its own memory alone, so a judge ended from beside would read as ended by
    its own bound and FAIL an honest delivery (critic). With no server of its own there, the kernel's limit holds."""
    if not ids:
        return []
    got = run(["docker", "inspect", "-f", f'{{{{.Id}}}} {{{{index .Config.Labels "{HOME}"}}}}', *ids], timeout=60, text=True)
    own = {i for i, _, h in (ln.partition(" ") for ln in (got.stdout or "").splitlines()) if h == _home()}
    return [i for i in ids if i in own]


def _watch_ceiling(stop: threading.Event | None = None) -> None:
    """WHO PAYS WHEN THE MACHINE'S CEILING IS NEAR: the node's work standing furthest over its fair share, not the
    kernel's choice — at the group's max the kernel ends its largest process, an honest one beside a runaway spread over
    many small ones (measured). Past `CEILING_ACT` of the ceiling in memory no reclaim gives back, this ends that work's
    containers; their rounds meet it as their own bound. Nobody over a share, nothing is ended and nothing is slowed:
    the kernel's kill at the ceiling stays the last resort, for a runaway faster than a turn. Every `CEILING_WATCH_S`."""
    group, every = CEILING_GROUP, CEILING_WATCH_S
    reader, stands = f"{group.replace('/', '-')}-ceiling-reader", True     # …one a server before this left, gone at its first turn
    while not (stop or threading.Event()).wait(every):
        if not ceiling():
            continue
        try:
            # …NO WORK ON THE MACHINE, NO READER: an idle server holds no container and reads nothing inside Docker. Up within a
            # turn of work's first container, long before anything in it can press on the ceiling, and gone with its last.
            if not (run(["docker", "ps", "-q", "--filter", f"label={HOME}"], timeout=30, text=True).stdout or "").strip():
                if stands:
                    run(["docker", "rm", "-f", reader], timeout=60)
                    stands = False
                continue
            stands = True
            got = run(["docker", "exec", reader, "sh", "-c", _READ_GROUP, "sh", group], timeout=30, text=True)
            if got.returncode:
                run(["docker", "rm", "-f", reader], timeout=60)
                run(["docker", "run", "-d", "--name", reader, "--label", f"{READER}=1", "--network", "none",
                     "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--read-only", *_SMALL,
                     "--mount", "type=bind,src=/sys/fs/cgroup,dst=/cg,readonly", "--entrypoint", "sleep",
                     CEILING_IMAGE, "infinity"], timeout=120)
                continue
            if ends := _own_of(_over_share(got.stdout, _units)):
                names = run(["docker", "inspect", "-f", "{{.Name}}", *ends], timeout=60, text=True).stdout or ""
                _WATCH_ENDED.update(n.strip().lstrip("/") for n in names.splitlines() if n.strip())
                done = run(["docker", "kill", *ends], timeout=60, text=True)
                log.warning(f"the machine's memory ceiling was near: the work of {len(ends)} container(s) "
                            f"({', '.join(i[:12] for i in ends)}) stood furthest over its share and "
                            + ("was ended, its neighbours left running" if not done.returncode else
                               f"could not be ended ({(done.stderr or '').strip()[-200:]})"))
        except (OSError, subprocess.TimeoutExpired) as e:
            log.warning(f"the memory ceiling's watch did not read the group ({e}); the kernel's limit still holds")


#: how often the disk's watch reads what each node's work holds: what a node writes past its bound before it is ended
DISK_WATCH_S = 10.0
_LAYER = re.compile(r"([\d.]+)\s*([kMGT]?B)")
#: what the disk's watch reads in a volume, per directory: `<kb> <files> <path>` a line
_HELD = ('m=$1; t=$2; shift 2; for d; do [ -d "$d" ] || continue; '
         'find "$d" -maxdepth 0 -xdev -ignore_readdir_race -printf "" 2>/dev/null || { echo "N 0 $d"; continue; }; '
         'if [ -n "$(timeout "$t" find "$d" -xdev -mindepth "$m" -print -quit 2>/dev/null)" ]; then echo "D 0 $d"; '
         'continue; fi; { LC_ALL=C timeout "$t" find "$d" -xdev -ignore_readdir_race -printf "%i %n %b\\n" 2>&1; '
         'echo "rc $?"; } | awk -v d="$d" \'$1 == "find:" {if ($0 ~ /No such file or directory$/) gone = 1; else bad = 1; next} '
         '$1 == "rc" {rc = $2; next} seen[$1]++ {next} '
         '{b += $3; n++} END {if (rc == 0 || (rc == 1 && gone && !bad)) print b * 512, n, d; else if (rc == 124) print "T", 0, d; '
         'else print "U", 0, d}\'; done')
#: deeper than this a directory is no session's to keep unread: honest trees nest tens of levels, and a chain of hundreds
#: of thousands made the reader stall for minutes or stop short and say nothing (critic) — its work is ended for it
DISK_DEPTH = 4096
#: the seconds one directory's reading may take before it is left unread, said, and no other with it — and the readings
#: in a row it may so outrun, or its walk fail, before its work is ended for it: unread, its charge stood frozen below the
#: bound for good (critic; a nest on the Linux runner failed every walk while it stayed running); a million files, the
#: files bound, read in seconds
DISK_READ_S, DISK_SLOW_READS = 60, 3
#: the directories `_read` found nested past `DISK_DEPTH`, until a reading reads them whole; and how many readings in a
#: row each directory was not read whole, its volume's whole reading outrun counting for each
_TOO_DEEP: set = set()
_SLOW: dict = {}


def _bytes(size: str) -> int:
    """Docker's `12.3MB` as bytes."""
    m = _LAYER.match(size or "")
    return int(float(m[1]) * {"B": 1, "kB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12}[m[2]]) if m else 0


def _disk_works(home: str) -> dict:
    """{(project, node, role, session): {"names", "running", "layers", "dirs"}} — each session's work of the installation
    `home` — a node's executor's and each of its judges' rounds and batches apart: one validation's batches each build
    their own copy (critic: an honest delivery's batches FAILed together) —, on Docker's disk as its containers say it: their names, whether one runs, each one's
    own layer by name, stopped ones' included (`ps -a -s`), and every directory any of them mounts writable, as (volume,
    subpath) — read from what Docker mounted, not from the system's naming: a dotted directory a name rule left out was
    filled uncounted (critic over the first watch). The system's own keepers, which mount a volume whole, are none."""
    got = run(["docker", "ps", "-a", "-s", "--filter", f"label={NODE}", "--filter", f"label={HOME}={home}", "--format",
               f'{{{{.ID}}}}\t{{{{.Names}}}}\t{{{{.State}}}}\t{{{{.Size}}}}\t{{{{.Label "{PROJECT}"}}}}\t'
               f'{{{{.Label "{NODE}"}}}}\t{{{{.Label "{ROLE}"}}}}\t{{{{.Image}}}}'], timeout=300, text=True)
    if got.returncode:           # …Docker not answering is no installation with no work: every directory would read as left
        raise OSError(f"Docker did not list its containers: {(got.stderr or '').strip()[-200:]}")
    rows = [r.split("\t") for r in (got.stdout or "").splitlines() if r.count("\t") == 7]
    rows = [r for r in rows if r[6] != "system"]
    mounts = run(["docker", "inspect", "-f", "{{.Id}}\t{{json .HostConfig.Mounts}}", *(r[0] for r in rows)],
                 timeout=120, text=True).stdout if rows else ""
    by_id = {i[:12]: json.loads(m or "null") or [] for i, _, m in (ln.partition("\t") for ln in mounts.splitlines())}
    works: dict = {}
    for cid, name, state, size, project, node, role, image in rows:
        session = re.sub(r"(-(client|commands))+$", "", name)
        w = works.setdefault((project, node, role, session), {"names": [], "running": False, "layers": {}, "dirs": set(),
                                                              "image": image})
        w["names"].append(name)
        w["running"] |= state == "running"
        w["layers"][cid] = (_bytes(size), _layer_files(cid, _bytes(size)))     # …by id: a name outlives its container
        w["dirs"] |= {(m["Source"], (m.get("VolumeOptions") or {}).get("Subpath") or ".")
                      for m in by_id.get(cid[:12], []) if m.get("Type") == "volume" and not m.get("ReadOnly")}
    return works


#: id → (its layer's bytes, its paths) when its paths were last counted: counted again once the layer grew a step
_LAYER_FILES: dict = {}
LAYER_STEP = 8 * 2 ** 20


def _layer_files(cid: str, size: int) -> int:
    """How many paths a container's own layer changed (`docker diff`), counted again only once its bytes grew a step:
    empty files cost no bytes, and a million of them in /tmp ran Docker's disk out of inodes uncounted (critic)."""
    seen = _LAYER_FILES.get(cid, (-LAYER_STEP, 0))
    if size - seen[0] >= LAYER_STEP:
        got = run(["docker", "diff", cid], timeout=300, text=True)
        seen = (size, len((got.stdout or "").splitlines())) if got.returncode == 0 else seen
        _LAYER_FILES[cid] = seen
    return seen[1]


def _disk_read(works: dict) -> dict:
    """{(volume, subpath): (bytes, files)} of every directory the works mount writable, each volume read once (`_read`)."""
    sizes: dict = {}
    for vol in {v for w in works.values() for v, _ in w["dirs"]}:
        image = next((w["image"] for w in works.values() if any(v == vol for v, _ in w["dirs"])), None)
        try:
            sizes.update(_read(vol, sorted({s for w in works.values() for v, s in w["dirs"] if v == vol}), image))
        except (OSError, subprocess.TimeoutExpired) as e:
            log.warning(f"the disk's watch did not read {vol} ({e}): its charges stand as they were")
            if isinstance(e, subprocess.TimeoutExpired):  # …outrun as a whole: each of its directories so (critic)
                for k in {(v, sp) for w in works.values() for v, sp in w["dirs"] if v == vol}:
                    _SLOW[k] = _SLOW.get(k, 0) + 1
    return sizes


def _read(vol: str, subs: list, image: "str | None" = None) -> dict:
    """{(vol, subpath): (bytes, files)} of `subs` of the volume `vol` — one standing nowhere holds nothing —, read-only,
    in a container of its own (a stopped project's has none), as root past every mode (one `chmod 700` or `000` hid a
    directory from a reader without it, critic), in `image`, the work's own — the product's has GNU find, which walks
    past the path-length limit busybox's stops at (a deep nest hid its whole contents, critic) —, else busybox. Bytes
    by allocated blocks, each inode once; a file vanishing mid-walk is no stop (a parallel build's temp churn). A
    directory not read whole is left out, said in the log — its charge stands, never nothing (critic: a failed read
    charged a node with its whole place) —, and no other with it (critic: one session's unreadable directory stopped
    its whole project's bounds); asked for alone, or the volume not read at all, `OSError`."""
    if not subs:
        return {}
    name = f"gfso-disk-reader-{uuid.uuid4().hex[:12]}"
    try:
        got = run(["docker", "run", "--rm", "--name", name, "--network", "none", "-u", "0", "--cap-drop", "ALL",
                   "--cap-add", "DAC_READ_SEARCH", "--read-only", *_SMALL, *ceiling(), "--mount",
                   f"type=volume,src={vol},dst=/v,readonly", "--entrypoint", "sh", image or CEILING_IMAGE, "-c", _HELD,
                   "sh", str(DISK_DEPTH + 1), str(DISK_READ_S), *(f"/v/{s}" for s in subs)],
                  timeout=2 * DISK_READ_S * len(subs) + 60, text=True)    # …each directory's two walks
    except subprocess.TimeoutExpired:
        _end_cut(name)                                       # …the CLI ended, not its container (critic: one leaked)
        raise
    if got.returncode:
        raise OSError(f"{vol} was not read: {(got.stderr or '').strip()[-200:]}")
    sizes, unread = {}, []
    for b, files, at in (ln.split(" ", 2) for ln in (got.stdout or "").splitlines() if ln.count(" ") >= 2):
        key = (vol, at.strip()[3:] or ".")
        if b in ("T", "U"):       # …not `N`: an image whose `find` cannot do this says nothing of the node's directory
            _SLOW[key] = _SLOW.get(key, 0) + 1
        if b in ("U", "D", "T", "N"):
            unread.append(key[1])
            if b == "D":
                _TOO_DEEP.add(key)
        elif b.isdigit() and files.isdigit():
            _SLOW.pop(key, None)
            _TOO_DEEP.discard(key)                   # …read whole: its nest is gone
            sizes[(vol, at.strip()[3:] or ".")] = (int(b), int(files))
    for sub in unread:
        log.warning(f"the disk's watch could not read {sub} of {vol} whole: its charge stands as it was")
    if unread and len(subs) == 1:
        raise OSError(f"{unread[0]} of {vol} was not read whole")
    return sizes


class DiskLedger:
    """What each directory and each container's layer has ADDED: what it holds now, less its baseline, less what the
    system itself wrote or removed there — each such write measured just before and after it (`Volume.writes`), so a
    child's commit carried into the base, a join into a parent's place, a judge's or a check's copy and its removal are
    never a node's, and nothing a node writes beside them is forgiven with them (critic over the re-baselining ledger: a
    mark every 10 s forgave a node everything). Never below nothing. A directory the system makes is baselined as it
    leaves it, a container's layer made after the first reading from nothing; what stood before the first reading,
    from there. A directory the system writes into while a reading runs keeps its last charge until the next."""

    def __init__(self):
        self.base: dict = {}             # (volume, subpath) or a container's id → (bytes, files) its baseline
        self.system: dict = {}           # (volume, subpath) → (bytes, files) the system's own writes there since
        self.charged: dict = {}          # …→ (bytes, files) the work added there at its last reading
        self.busy: dict = {}             # (volume, subpath) → how many of the system's writes are in it now
        self.touched: set = set()        # (volume, subpath) the system wrote into since the current reading began
        self.lost: set = set()           # (volume, subpath) a system write into which was not measured: baseline again
        self.put: dict = {}              # ((volume, subpath), path under it) → (bytes, files) the system booked there
        self.read = False                # a first reading made: a layer seen after it is of a container made since
        self.lock = threading.Lock()

    def writing(self, at: tuple, start: bool) -> int:
        """The system starts or ends a write into `at`; how many of its writes stand there now."""
        with self.lock:
            n = self.busy.get(at, 0) + (1 if start else -1)
            self.busy[at] = n
            if n <= 0:
                del self.busy[at]
            self.touched.add(at)
            return n

    def made(self, at: tuple) -> None:
        """The system made `at` just now, empty: nothing it holds from here on stood before."""
        with self.lock:
            self.base.setdefault(at, (0, 0))

    def lose(self, at: tuple) -> None:
        """A system write into `at` that was not measured: its charge stands, its baseline taken again at the next
        reading."""
        with self.lock:
            self.lost.add(at)

    def wrote(self, at: tuple, before: tuple, after: tuple, under: str = ".") -> None:
        """The system's own write into `at`, under its path `under`, as `at` stood `before` and `after` it — `after` its
        baseline where it had none (the system made it)."""
        with self.lock:
            if at not in self.base:
                self.base[at], self.system[at] = after, (0, 0)
            else:
                s, p = self.system.get(at, (0, 0)), self.put.get((at, under), (0, 0))
                self.system[at] = (s[0] + after[0] - before[0], s[1] + after[1] - before[1])
                self.put[(at, under)] = (p[0] + after[0] - before[0], p[1] + after[1] - before[1])

    def removed(self, at: tuple, under: str) -> None:
        """The system removed its path `under` of `at`: what IT put there comes off its own account, and nothing else —
        what a session wrote there leaves what `at` holds by itself (critic: booking the measured removal charged every
        check with all the outputs of the checks before it)."""
        with self.lock:
            gone = [k for k in self.put if k[0] == at and (under == "." or k[1] == under or k[1].startswith(under + "/"))]
            took = [self.put.pop(k) for k in gone]
            s = self.system.get(at, (0, 0))
            self.system[at] = (s[0] - sum(t[0] for t in took), s[1] - sum(t[1] for t in took))

    def begin(self) -> None:
        """A reading starts: what the system writes into a directory from now on keeps that directory's last charge."""
        with self.lock:
            self.touched = set(self.busy)

    def added(self, works: dict, sizes: dict) -> dict:
        """{work: (bytes, files)} each work added — over the directories it mounts now and its containers' layers —, of
        the reading `begin` started and `sizes` (with the layers in `works`) holds."""
        with self.lock:
            dirty = self.touched | set(self.busy)
            now = {**sizes, **{n: v for w in works.values() for n, v in w["layers"].items()}}
            for k, v in now.items():
                if k in dirty:
                    continue                         # …half the system's write may be in what was read
                if k not in self.base:
                    self.base[k] = (0, 0) if self.read and k not in sizes else v
                elif k in self.lost:
                    c, s = self.charged.get(k, (0, 0)), self.system.get(k, (0, 0))
                    self.base[k] = (v[0] - s[0] - c[0], v[1] - s[1] - c[1])
                self.lost.discard(k)
                b, s = self.base[k], self.system.get(k, (0, 0))
                self.charged[k] = (max(0, v[0] - b[0] - s[0]), max(0, v[1] - b[1] - s[1]))
            self.read = True
            return {key: tuple(sum(self.charged.get(k, (0, 0))[i] for k in [*w["dirs"], *w["layers"]]) for i in (0, 1))
                    for key, w in works.items()}


_LEDGER = DiskLedger()
#: (volume, subpath) → the lock its system writes' measurement is taken under, and what it held before their span
_KEY_LOCKS: dict = {}
_BEFORE: dict = {}


def _past_bound(added: dict, running: set, bound: tuple) -> list:
    """The works with a container running that added more than `bound` (bytes, files) — each against its own bound
    alone: who holds the most, who grew by a fall in free space, what its neighbours wrote or what disk Docker shows,
    none of it moves the answer."""
    return [k for k, (b, n) in added.items() if k in running and (b > bound[0] or n > bound[1])]


_DISK_WATCH, _NO_WATCH_SAID = threading.Event(), threading.Event()
#: the containers the disk's watch ended, by name, with what their work added: a judge's copy or build so ended is its
#: delivery's FAIL, its cause said (`past_disk`)
_DISK_ENDED: dict = {}


def past_disk(ex) -> "str | None":
    """Why `ex`'s container was ended by the disk's watch, if it was: its work past its own bound — the delivery's own."""
    return _DISK_ENDED.get(ex.container) if isinstance(ex, ContainerExecution) else None


def ended_past_disk(ex) -> "str | None":
    """Why the disk's watch ended the session that worked in `ex`'s place, if it did — taken off once said: the place's
    next session runs in containers of the same names, and an older end is not its."""
    if not isinstance(ex, ContainerExecution):
        return None
    mine = [n for n in _DISK_ENDED if n == ex.container or n.startswith(ex.container + "-")]
    return next(iter({_DISK_ENDED.pop(n) for n in mine}), None)


def place_past_disk(ex) -> "str | None":
    """Do the directories of `ex`'s place — the ones its sessions write and that outlive them — hold more than its
    node's bound of what its work added, by the disk's ledger as it stands now? The cause, else None. Asked of the
    system's record, never of an end remembered (critic: one never read named an ordinary cut later), and of the
    directories alone: a container's own layer goes with it, so an end its layer caused the next session is free of."""
    if not isinstance(ex, PlaceContainer):
        return None
    at = {ex.volume.key(d) for d in ex.writable()}
    with _LEDGER.lock:
        held = tuple(sum(_LEDGER.charged.get(k, (0, 0))[i] for k in at) for i in (0, 1))
    bound = node_disk()
    if held[0] <= bound[0] and held[1] <= bound[1]:
        return None
    return (f"the directories of its place hold {held[0] // 2 ** 20} MiB and {held[1]} files its work added, past its "
            f"bound of {bound[0] // 2 ** 20} MiB and {bound[1]} files (GFSO_NODE_DISK, GFSO_NODE_FILES)")


def watch_disk() -> None:
    """The disk's watch, for this server's life (`_watch_disk`) over this installation's nodes, started once."""
    if not _DISK_WATCH.is_set():
        _DISK_WATCH.set()
        threading.Thread(target=_watch_disk, args=(None, None, _home()), name="gfso-disk", daemon=True).start()


#: what a reading of a volume's directories for what changed says of each, at most `FILES_BYTES`: `\0\1<dir>\1<its clock>\0`, or
#: `\2\0` where this image's `find` cannot, then `<type> <path>\0`, `\3` last where the walk did not finish. By the inode's
#: change time, which no process of a user sets
_CHANGED = ('m=$1; t=$2; shift 2; while [ $# -gt 0 ]; do d=$1; s=$2; shift 2; printf \'\\0\\1%s\\1\' "$d"; date +%s.%N | tr -d "\\n"; printf \'\\0\'; '
            '[ -d "/v/$d" ] || continue; find "/v/$d" -maxdepth 0 -newerct @0 -printf "" 2>/dev/null || { printf \'\\2\\0\'; continue; }; '
            '[ "$s" = new ] && s=$(( $(date +%s) - 60 )); '
            '{ timeout "$t" find "/v/$d" -xdev -ignore_readdir_race -newerct "@$s" -printf \'%y %P\\0\' 2>/dev/null; '
            '[ $? = 0 ] || printf \'\\3\'; } | head -c "$m"; done')
FILES_BYTES = 4 * 2 ** 20
#: (volume, subpath) → {"since", the clock the next reading reads from; "work", whose it is; "left", read once more, then dropped}
_FILES: dict = {}
_FILES_LOCK = threading.Lock()


def network_record_path(project: str) -> Path:
    """Where `project`'s record of where its sessions reached lies, in this installation's data, which no session mounts."""
    return data_dir() / "network" / f"{component(project)}.jsonl"


def file_record_path(project: str) -> Path:
    """Where `project`'s record of what changed in its sessions' directories lies, in this installation's data."""
    return data_dir() / "files" / f"{component(project)}.jsonl"


def _end_cut(name: str) -> None:
    """The container of a `docker run` cut by its time. Cut while Docker makes it, it appears after a removal that answered
    0 (13 of 80 cuts at 50–100 ms, within 1.5 s), holding its mounts: removed again until that time has passed; later still,
    a server's next start sweeps it (`end_leftovers`)."""
    for wait in (0, 0.5, 1, 2):
        time.sleep(wait)
        run(["docker", "rm", "-f", name], timeout=60)


def release_rounds(ex, place: str) -> None:
    """Every session of project `ex` standing in a validation's round of the delivery in `place`: filing a finding reads what
    its command names in the round, in the round's own container, after its run ended it. A host's has none."""
    if isinstance(ex, ContainerExecution):
        under = os.path.normcase(scratch_of(_real(place), ex.project_name)) + os.sep
        for s in [s for (c, rw), s in _SESSIONS.copy().items() if c == ex.container and rw.startswith(under)]:
            s.stop()


def _files_changed(vol: str, since: dict, image: "str | None") -> dict:
    """{subpath: (its clock now, its entries, cut?) or None where this image cannot say} of the volume `vol`, read-only, in a
    container of its own as `_read`'s, as root past every mode, each bounded in what reaches this process."""
    name = f"gfso-disk-reader-{uuid.uuid4().hex[:12]}"
    try:
        got = run(["docker", "run", "--rm", "--name", name, "--network", "none", "-u", "0", "--cap-drop", "ALL",
                   "--cap-add", "DAC_READ_SEARCH", "--read-only", *_SMALL, *ceiling(), "--mount",
                   f"type=volume,src={vol},dst=/v,readonly", "--entrypoint", "sh", image or CEILING_IMAGE, "-c", _CHANGED,
                   "sh", str(FILES_BYTES), str(DISK_READ_S), *(x for sub, s in since.items() for x in (sub, s))],
                  timeout=DISK_READ_S * len(since) + 60)
    except subprocess.TimeoutExpired:
        _end_cut(name)
        raise
    if got.returncode:           # …killed partway: what it read is not all, and the clock must not move over it
        raise OSError(f"its reader exited {got.returncode}: {(got.stderr or b'').decode(errors='replace').strip()[-200:]}")
    said = {}
    for part in (got.stdout or b"").split(b"\0\1")[1:]:
        head, _, rest = part.partition(b"\0")
        sub, _, clock = head.partition(b"\1")
        said[sub.decode(errors="replace")] = None if rest.startswith(b"\2") else (
            clock.decode(), [e if e[2:] else "d ." for e in rest.rstrip(b"\3").decode(errors="replace").split("\0") if e],
            len(rest) >= FILES_BYTES or rest.endswith(b"\3"))
    return said


def _note_files(ex) -> None:
    """A session's directories known from its start: one that begins and ends between two readings is seen by neither (critic, ran)."""
    if isinstance(ex, PlaceContainer):
        # …by the clock of Docker's VM, which stamps the files, a second early: a watch delayed past a guess lost the first writes
        at = run(["docker", "inspect", "-f", "{{.State.StartedAt}}", ex.container], timeout=30, text=True).stdout or ""
        try:
            since = f"{datetime.datetime.fromisoformat(at.strip()[:19]).replace(tzinfo=datetime.timezone.utc).timestamp() - 1:.3f}"
        except ValueError:
            since = "new"
        for d in ex.writable():
            with _FILES_LOCK:
                _FILES.setdefault(ex.volume.key(d), {"since": since}).update(
                    work=(ex.project_name, ex.node, ex.role, ex.container), image=ex.image, left=False, noted=time.monotonic())


def _record_files(works: dict, asked: "float | None" = None) -> None:
    """S6's file half: what changed in every directory a session mounts writable, on its project's record on the host, read
    from outside the session (the disk's watch): nothing a session does to its own containers, its memory or its processes
    reaches this, whichever way it wrote and whether or not it ran a command. Where, not who: the system's own writes there
    show too. A directory whose work left is read once more; one cut says so, and the next reads on from its clock.
    `asked`: when `works` was asked of Docker: what was noted since is not gone for being absent from it."""
    with _FILES_LOCK:
        for k, w in works.items():
            for d in w["dirs"]:
                _FILES.setdefault(d, {"since": "new"}).update(work=k, image=w["image"], left=False)
        standing = {d for w in works.values() for d in w["dirs"]}
        for d, f in _FILES.items():
            f["left"] = d not in standing and f.get("noted", 0) < (time.monotonic() if asked is None else asked)
        now = dict(_FILES)
    for vol in {v for v, _ in now}:
        mine = {s: f for (v, s), f in now.items() if v == vol}
        if any(f["left"] for f in mine.values()) and (there := run(["docker", "volume", "inspect", vol], timeout=60, text=True)).returncode:
            if "no such volume" in (there.stderr or "").lower():      # …gone with its project: asking would have Docker make it again, empty
                for s in mine:
                    _FILES.pop((vol, s), None)
            continue                                                  # …or Docker did not answer: the clocks stand for when it does
        try:
            said = _files_changed(vol, {s: f["since"] for s, f in mine.items()}, next(iter(mine.values()))["image"])
        except (OSError, subprocess.TimeoutExpired) as e:
            log.warning(f"what changed in {vol} was not read now ({e}): the next reading reads it")
            continue
        for s, f in mine.items():
            got, (project, node, role, session) = said.get(s, ()), f["work"]
            row = {"at": time.time(), "node": node, "role": role, "session": session, "dir": s}
            if not got:
                append(file_record_path(project), {**row, "unread": "this image's `find` cannot say what changed"})
            else:
                clock, entries, cut = got
                if entries or cut:
                    append(file_record_path(project), {**row, **said_of(entries), **({"cut": True} if cut else {})})
                # …past a cut too: what stood would stop every later reading at the same place, and an honest install past the
                # bound would say so every ten seconds and turn the record over (critic, ran). What it did not reach, it said
                f["since"] = f"{float(clock) - 0.05:.3f}"
            if f["left"]:
                _FILES.pop((vol, s), None)


def _watch_disk(stop: threading.Event | None, every: float | None, scope: str, ledger: "DiskLedger | None" = None
                ) -> None:
    """WHO PAYS WHEN ONE NODE FILLS DOCKER'S DISK: that node, by a bound of its own (`config.node_disk`). Docker Desktop's
    disk takes no quota and one node filling it stopped every project on the machine. Every `DISK_WATCH_S` it reads what
    each node's work of the installation `scope` added (`DiskLedger`); a work with a container running past its bound has
    its containers removed — their layers with them, its directories kept —, said in the log. A judge's copy or build so
    ended FAILs its delivery, the bound named (`past_disk`). What its place's directories hold stays charged, so an
    executor whose place stays past it parks its node, the cause said to its issuer (`place_past_disk`); one its own
    container's layer took past it goes on, that layer gone with its container."""
    ledger = ledger or _LEDGER
    while not (stop or threading.Event()).wait(every or DISK_WATCH_S):
        try:
            bound = node_disk()
            ledger.begin()
            asked = time.monotonic()
            works = _disk_works(scope)
            added = ledger.added(works, _disk_read(works))
            try:
                _record_files(works, asked)
            except Exception as e:      # …the record's failure costs no one's bound
                log.warning(f"what changed on Docker's disk was not recorded now ({e})")
            with ledger.lock:
                busy = set(ledger.busy)
            # …never while the system writes into one of its directories: its git would be ended halfway
            free = {k for k, w in works.items() if w["running"] and not w["dirs"] & busy}
            deep = {k for k in free if works[k]["dirs"] & _TOO_DEEP
                    or any(_SLOW.get(d, 0) >= DISK_SLOW_READS for d in works[k]["dirs"])}
            for k in [*deep, *(k for k in _past_bound(added, free, bound) if k not in deep)]:
                why = (f"node {k[1]}'s {k[2]} work ({k[3]}) holds a directory the system cannot read — nested deeper "
                       f"than {DISK_DEPTH} levels, or its walk failed or outran {DISK_READ_S} s at {DISK_SLOW_READS} "
                       f"readings in a row" if k in deep else
                       f"node {k[1]}'s {k[2]} work ({k[3]}) added {added[k][0] // 2 ** 20} MiB and {added[k][1]} files to "
                       f"Docker's disk, past its bound of {bound[0] // 2 ** 20} MiB and {bound[1]} files "
                       f"(GFSO_NODE_DISK, GFSO_NODE_FILES)")
                _DISK_ENDED.update(dict.fromkeys(works[k]["names"], why))
                _keep_logs(works[k]["names"])        # …a session past its bound on purpose took its commands' record with it (critic, ran)
                done = run(["docker", "rm", "-f", *works[k]["names"]], timeout=120, text=True)
                log.warning(f"{k[0]}: {why}: " + ("its containers were ended, its directories kept" if not done.returncode
                                                  else f"it could not be ended ({(done.stderr or '').strip()[-200:]})"))
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as e:
            log.warning(f"the disk's watch did not read Docker's disk ({e})")


def _system_run(name: str, image: str, flags: list, script: Path, args: list, mirror: Path, mode: str = "1777") -> None:
    """A system container (a door, a gateway, a session's commands) running `script` with `args`: started waiting for
    it, the script laid whole into its `OWN` through one `docker exec`, so nothing of the host is mounted into it. Its
    `OWN` (of `mode`) holds its log well past the log's cap on refusals, room left for what it passes; the log's host
    `mirror` named on it, so any removal of it keeps the log first (`_keep_logs`). Bounded in memory and processes by
    its `flags`, or it does not start: one unbounded container can starve every project on the machine
    (`container_limits`)."""
    if not {"--memory", "--pids-limit"} <= set(flags):
        raise ValueError(f"{name}: a system container starts bounded in memory and processes")
    run(["docker", "run", "-d", "--init", "--name", name, *flags, *ceiling(), "--label", f"gfso.log={mirror}",
         "--tmpfs", f"{OWN}:size={3 * door.LOG_CAP // 2 ** 20}m,mode={mode}", image,
         "/bin/sh", "-c", f'export PATH={SYSTEM_PATH}:$PATH; until [ -f {OWN}/run.py ]; do sleep 0.1; done; exec python3 {OWN}/run.py "$@"', "sh", *args],
        timeout=120).check_returncode()
    run(["docker", "exec", *SYS, "-i", name, "/bin/sh", "-c", f"cat > {OWN}/laid && mv {OWN}/laid {OWN}/run.py"],
        input=script.read_bytes(), timeout=60).check_returncode()


def _log_out(names, mirror: Path) -> str:
    """What the system containers `names` logged in their `OWN`, appended to the host's `mirror` before they go —
    the mirror read with them: what they logged outlives them. One that can start no process — ended by its memory, or a
    command holding every pid its container has — is read from what its listener printed, which takes none (critic, ran:
    a session so emptied the record of its own commands)."""
    def out(n):
        """What `n` logged."""
        got = run(["docker", "exec", *SYS, n, "/bin/sh", "-c", f"cat {OWN}/*.log 2>/dev/null; true"], timeout=60, text=True,
                  encoding="utf-8", errors="replace")
        return (got if not got.returncode else run(["docker", "logs", n], timeout=60, text=True, encoding="utf-8", errors="replace")).stdout or ""
    kept = mirror.read_text(encoding="utf-8") if mirror.is_file() else ""
    return kept + "".join(out(n) for n in names)


def _mirror(names, mirror: Path) -> None:
    if text := _log_out(names, mirror):
        mirror.parent.mkdir(parents=True, exist_ok=True)
        mirror.write_text(text, encoding="utf-8")


def _keep_logs(names) -> None:
    """Each system container of `names` that names its log's mirror (`_system_run`) has its log kept there — before a
    sweep removes it, at this server's exit or the next one's start."""
    got = run(["docker", "inspect", "-f", '{{.Name}} {{index .Config.Labels "gfso.log"}}', *names], timeout=60,
              text=True) if names else None
    for n, _, m in [x.partition(" ") for x in (got.stdout or "").splitlines()] if got else []:
        if m.strip() and m.strip() != "<no value>":
            _mirror([n.lstrip("/")], Path(m.strip()))


#: each file operation inside (`ContainerFiles`), over "$1" the path — no bound of its own: the container it runs in is
#: the bound (`ContainerFiles._where`); a non-zero exit below 125 is the operation's own "not there"
_FILE_OPS = {
    "exists": '[ -e "$1" ] || [ -L "$1" ]',
    "is_dir": '[ -d "$1" ]',
    "listdir": '[ -d "$1" ] && find -H "$1" -mindepth 1 -maxdepth 1 -printf "%f\\0"',
    "read_bytes": '[ -f "$1" ] && if [ -n "$2" ]; then head -c "$2" -- "$1"; else cat -- "$1"; fi',
    "write_bytes": 'mkdir -p -- "$(dirname -- "$1")" && cat > "$1"',
    "mkdir": 'mkdir -p -- "$1"',
    "write_files": 'mkdir -p -- "$1" && tar -x -m -C "$1" -f -',
    # as root, over "$1" the base and then every directory from the writable root down to it: each made the system's, a
    # link refused — checked after it is the system's, when no agent can swap it any more — then the files, 0444 root's,
    # every directory under them root's 1777: code beside them adds its own, and moves none of the system's
    "seal_files": 'b=$1; shift; for d; do { [ -L "$d" ] || mkdir -p -- "$d"; } && chown -h 0:0 -- "$d" && '
                  'chmod 1777 -- "$d" && [ -d "$d" ] && [ ! -L "$d" ] && [ "$(stat -c %u -- "$d")" = 0 ] || '
                  '{ echo "$d: not the system\'s directory" >&2; exit 1; }; done; '
                  'tar -x -m -C "$b" -f - && find "$b" -mindepth 1 -type d -exec chmod 1777 {} +',
    "read_tree": '[ -d "$1" ] && { tar -c -C "$1" . || echo gfso-tar-failed >&2; } | head -c "$2"',
    "subdirs": '[ -d "$1" ] && find "$1" -mindepth 1 -maxdepth "$2" -type d -printf "%P\\0"',
    "remove_matching": 'r=$1; shift; [ -d "$r" ] || exit 0; '
                       'for g; do find -P "$r" -mindepth 1 -path "$r/$g" ! -type d -delete || exit 1; done',
}
#: `Volume.bring_in` inside, as root: "$1" `made` where the record says so, "$2" the image's user, "$3" the origin,
#: then (old key, new name) pairs; exit 3: a volume lost. Each kind of entry counted on both sides of the copy
_BRING_IN = r'''u="$(id -u "$1"):$(id -g "$1")" && shift || exit 1
find /to /state -mindepth 1 -delete || exit 1
kinds() { (cd "$1" && find . -printf '%y\n' | sort | uniq -c); }
if [ -d /from ]; then
  cp -a /from/. /to/ || exit 1
  [ "$(kinds /from)" = "$(kinds /to)" ] || { echo "the copy differs: $(kinds /from | tr '\n' ' ')/ $(kinds /to | tr '\n' ' ')" >&2; exit 1; }
fi
if [ -d /old ]; then
  for f in /old/* /old/.[!.]*; do [ -e "$f" ] && [ "$f" != /old/places ] && { cp -a "$f" /state/ || exit 1; }; done
  while [ $# -gt 1 ]; do
    [ -d "/old/places/$1" ] && { mkdir -p "/state/$2" && cp -a "/old/places/$1/." "/state/$2/" || exit 1; }
    shift 2
  done
fi
chown -R "$u" /to /state'''
#: `Volume.export` inside, as the image's user — never root — over the places at /from: a copy in the container's own
#: file system; in it every repository made inert — the agent's config and hooks dropped for a config of the format
#: alone, so nothing it wrote runs, here nor on the host that reads the export — and each node's clone dissociated
#: from the base ("$1", its directory in the volume): its borrowed objects repacked in, by git under no config but its
#: own, its alternates gone; the base's HEAD and its `gfso/*` branches bundled beside them (`gfso-refs.bundle`, for
#: the user's `git fetch`). What could not be done is said on stderr ("NOTE: …"), the rest exported
_EXPORT = r'''b=$1
note() { printf 'NOTE: %s\n' "$*" >&2; }
mkdir -p /tmp/x || exit 1
(cd /from && tar -c --exclude=./.gfso-sys --exclude=./.gfso-tmp .) | tar -x -C /tmp/x || note "files it could not read are not exported"
chmod -R u+rwX /tmp/x 2>/dev/null
find /tmp/x -iname .git ! -type d -print -delete | while read -r g; do note "${g#/tmp/x/}: a .git that is no directory, removed"; done
cat > /tmp/one <<'ONE'
note() { printf 'NOTE: %s\n' "$*" >&2; }
has() { d=$1; p=$2; set -- "$d"/$p; [ -e "$1" ] || [ -L "$1" ]; }
b=$1; shift
for g; do
  [ -d "$g" ] || continue
  case "${g##*/}" in
    .[gG][iI][tT]) ;;
    *) has "$g" '[hH][eE][aA][dD]' || continue
       has "$g" '[cC][oO][mM][mM][oO][nN][dD][iI][rR]' || { has "$g" '[oO][bB][jJ][eE][cC][tT][sS]' && has "$g" '[rR][eE][fF][sS]'; } || continue ;;
  esac
  mv "$g/config" /tmp/theirs 2>/dev/null || : > /tmp/theirs
  find "$g" -mindepth 1 -maxdepth 1 \( -iname config -o -iname config.worktree -o -iname commondir -o -iname hooks \) -exec rm -rf -- {} +
  for k in core.repositoryformatversion:0:1 core.bare:true:false extensions.objectformat:sha1:sha256 extensions.refstorage:files:reftable; do
    n=${k%%:*}; o=${k#*:}
    v=$(git config --file /tmp/theirs --get "$n" </dev/null 2>/dev/null)
    case "$v" in "${o%:*}"|"${o#*:}") git config --file "$g/config" "$n" "$v" </dev/null ;; esac
  done
  a=$g/objects/info/alternates
  [ -f "$a" ] || continue
  cp "$a" /tmp/alternates
  printf '%s\n' "$b/.git/objects" > "$a"
  if GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.fsmonitor=false -c core.hooksPath=/dev/null \
      --git-dir="$g" repack -a -d -q </dev/null; then
    rm -f "$a"
  else
    cp /tmp/alternates "$a" && note "${g#/tmp/x/}: not repacked — exported as it stands, its objects still the base's"
  fi
done
exit 0
ONE
find /tmp/x -type d -exec sh /tmp/one "$b" {} +
if [ -d /tmp/x/.gfso-base/.git ]; then
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -C /tmp/x/.gfso-base bundle create -q /tmp/x/gfso-refs.bundle \
    HEAD --branches='gfso/*' </dev/null || note "the base's branches could not be bundled"
fi
[ -n "$(ls -A /tmp/x)" ] || { note "nothing to export"; exit 1; }
tar -c -C /tmp/x .'''
#: WHAT EVERY SESSION READS AS THE BASE: a copy beside it holding what the base was imported with, never a delivery. Each delivery is carried into the base as a branch, and a session mounting the base read
#: every sibling's commit by its name or its id, judged or not, for its whole life (critic, live). Hard links: the
#: base's files as they are, nothing doubled; git replaces a file, never writes one in place. `read_copy` makes it, or at
#: a new root's import brings it to the commit imported by what that reaches alone (its LFS objects laid there by the import
#: itself), and names what it holds in the base (`READ_REF`). Nothing moves it between imports: a root's next one starts from
#: the user's repository again.
_READ_COPY = r'''g() { GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c safe.directory='*' -c core.hooksPath=/dev/null \
  -c core.fsmonitor=false -c "$fc" -c "$fs" -C "$d" "$@" </dev/null; }
read_copy() {
  b=$d r=${d%/*}/''' + BASE_READ + r'''
  if [ ! -d "$r" ] || { [ -d "$b/.git" ] && [ ! -d "$r/.git" ]; }; then
    rm -rf "$r" "$r.new" && cp -al "$b" "$r.new" || return 1
    if [ -d "$b/.git" ]; then       # …its HEAD detached, a new file: linked, a write would be the base's; on a node branch it would name nothing
      s=$(g rev-parse HEAD) && rm -f "$r.new/.git/HEAD" && echo "$s" > "$r.new/.git/HEAD" && rm -rf "$r.new/.git/refs/heads/gfso" || return 1
    fi
    [ ! -f "$r.new/.git/packed-refs" ] || sed -i '\# refs/heads/gfso/#d' "$r.new/.git/packed-refs" || return 1
    mv "$r.new" "$r" || return 1
  elif [ -d "$b/.git" ]; then
    d=$r; g fetch -q --no-tags "$b" HEAD && g reset -q --hard FETCH_HEAD || return 1
    d=$b
  fi
  [ ! -d "$b/.git" ] || { s=$(d=$r; g rev-parse HEAD) && g update-ref ''' + READ_REF + r''' "$s"; }
}
'''
#: `Volume.read_again` inside: "$1" the base's directory in the volume, "$2" "$3" the system's LFS filter
_READ_AGAIN = "d=/to/$1 fc=$2 fs=$3\n" + _READ_COPY + "read_copy"
#: `Volume.import_base` inside, as the image's user, the places volume at /to, what the host carried on stdin (a tar:
#: `bundle`, `branch`, `exclude`, `attributes`, `lfs/<oid>` — or `tree`, a base with no git): "$1" the commit (empty: no
#: git), "$2" the base's directory in the volume, "$3" the project, "$4" "$5" the system's LFS filter (`lfs`), which
#: writes each LFS file's content from the objects carried, verified — written into the base's own config too, so the
#: root's agent's own git agrees. Its git reads no config but the clone's own, runs no hook; a node branch that stands in
#: the volume is never overwritten, a base with no git never removed
_IMPORT = r'''c=$1 d=/to/$2 p=$3 fc=$4 fs=$5
''' + _READ_COPY + r'''mkdir -p /tmp/in && tar -x -C /tmp/in || exit 1
if [ -z "$c" ]; then
  mkdir -p "$d" && { [ ! -d /tmp/in/tree ] || cp -a /tmp/in/tree/. "$d/"; } && read_copy
  exit
fi
if [ -d "$d/.git" ]; then       # …its config, hooks and rules anew: nothing a volume kept runs at this import (each a new file: the read copy's are links)
  rm -rf "$d/.git/config" "$d/.git/hooks" "$d/.git/info/attributes" && g init -q || exit 1
else
  rm -rf "$d" && mkdir -p "$d" && g init -q || exit 1
fi
g fetch -q --update-head-ok /tmp/in/bundle HEAD "+refs/heads/gfso/$p/*:refs/gfso-import/*" || exit 1
g for-each-ref --format='%(refname:lstrip=2) %(objectname)' refs/gfso-import/ | while read -r n s; do
  g update-ref "refs/heads/gfso/$p/$n" "$s" "" 2>/dev/null
  g update-ref -d "refs/gfso-import/$n" || exit 1
done
g cat-file -e "$c^{commit}" || { echo "the bundle holds no commit $c" >&2; exit 1; }
for n in exclude attributes; do
  [ ! -f "/tmp/in/$n" ] || { mkdir -p "$d/.git/info" && cp "/tmp/in/$n" "$d/.git/info/$n"; } || exit 1
done
for f in /tmp/in/lfs/*; do
  [ -f "$f" ] || continue
  o=${f##*/} a=${f##*/}; a=${a#??}; b=${a#??}; s=$d/.git/lfs/objects/${o%"$a"}/${a%"$b"}
  mkdir -p "$s" && mv -f "$f" "$s/$o" || exit 1
  q=${d%/*}/''' + BASE_READ + r'''/.git/lfs/objects/${o%"$a"}/${a%"$b"}
  [ ! -d "${d%/*}/''' + BASE_READ + r'''/.git" ] || { mkdir -p "$q" && ln -f "$s/$o" "$q/$o"; } || exit 1
done
for kv in "$fc" "$fs"; do g config "${kv%%=*}" "${kv#*=}" || exit 1; done
g checkout -q -f -B "$(cat /tmp/in/branch)" "$c" && g clean -q -ffdx && read_copy'''
#: what the docker client says where the daemon does not answer — the place down (`PlaceUnavailable`)
_DOWN = re.compile(r"failed to connect to the docker API|Cannot connect to the Docker daemon|error during connect", re.I)
#: …and where the container is gone or stopped under a live server — started again, once
_GONE = re.compile(r"No such container|is not running", re.I)
#: what a place's storage says when it fails under a live daemon (`unavailable(storage=True)` decides)
_STORAGE = re.compile(r"Input/output error", re.I)
#: the containers this server process started — one per (execution, project), whichever object asks for it — with
#: what each was started holding: a project re-created on another base gets a container of its own again
_STARTED: dict = {}
#: the session containers of each project's places, by (project container, writable root)
_SESSIONS: dict = {}
#: each node temp's owner place (`temp_of`), whose session container mounts it
_TEMPS: dict = {}
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
#: each project's own lock over its volume's making — a copy-in of one project stalls no other
_VOLUMES: dict = {}


def component(s) -> str:
    """A node id or a project name as one path component and one ref component — never starting with a dot."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(s)).replace("..", "_").strip(".") or "_"


def _mount_field(key: str, path: str) -> str:
    """One field of a `--mount`, which Docker reads as CSV: a path that is the user's — the base's own name, a parent's
    — may hold a comma or a quote."""
    return f'"{key}={path.replace(chr(34), chr(34) * 2)}"' if re.search(r'[,"]', path) else f"{key}={path}"


def scratch_of(place, project) -> Path:
    """Where the validations and contacts of the delivery in `place` keep their rounds, one directory each: beside a
    node's clone, among its project's places already; beside any other directory — a base — in its project's places
    too, so two projects on one base keep their rounds apart. The dot: no node's key starts with one (`component`), so
    no node's scratch is a base's."""
    p = Path(place)
    if p.parent.parent.name.startswith(NODES):
        return p.parent / f"{SCRATCH}{p.name}"
    return p.parent / nodes_dir(p.name) / component(project or DEFAULT_PROJECT) / f"{SCRATCH}.{place_name(p.name)}"


def _real(path) -> Path:
    """A place's path as the system names it, absolute — the one seam a test of another platform's paths replaces."""
    return Path(path).resolve()


def _host_paths(parents, mounts) -> re.Pattern:
    """A mounted directory under a parent, in any spelling a path may arrive in — each of `parents` (as given and as
    resolved: a link in it); on Windows C:\\ or C:/, either drive case, a doubled backslash too (a path inside JSON),
    caseless; a POSIX path exactly, not inside a longer one — and the rest of that path, up to a list's separator, in
    `rest`. Never a parent alone: a root's or a drive's maps nothing else of it."""
    win = bool(parents[0].drive)
    sep, stop = (r"[\\/]{1,2}", r"\s\"'`<>|*?;") if win else ("/", r"\s\"'`<>|*?:")
    heads = dict.fromkeys((re.escape(p.drive[:1]) + ":" if win else "") + "".join(sep + re.escape(q) for q in p.parts[1:])
                          for p in parents if p.is_absolute())
    mounted = "|".join(sep.join(map(re.escape, Path(m).parts)) for m in mounts)
    return re.compile(("" if win else r"(?<![\w.~/-])") + "(?:" + "|".join(heads) + ")(?P<rest>" + sep + "(?:" + mounted
                      + r")(?:" + sep + "[^" + stop + r"]*)?)(?![\w.-])", re.IGNORECASE if win else 0)


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
    files = HOST

    def agents_refused(self):
        """Unattended work runs in a container; this host runs it only on its user's word, given where the server
        starts (`config.local_agents`) — no session can give it. Work a person does in their own chat, and what judges
        it, runs here as before: it is attended."""
        if local_agents():
            return None
        return ("this host runs no dispatched work unattended: an executor's commands would run as you, on your "
                "machine, with nothing between them and the rest of it. Run the project in a container (its executor "
                "registered with `execution=\"default\"`, which `gfso setup` declares, or another of "
                "data/executions.json), or allow it on this host: "
                "\"GFSO_LOCAL_AGENTS\": \"allow\" in data/serve.json, then `gfso up`")

    def unavailable(self, storage: bool = False):
        # …so a project this refusal stopped stays stopped until the word is given or an execution is declared
        return self.agents_refused()

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
        return run_printing(args, timeout=timeout, cwd=cwd, **({"env": env} if env is not None else {}))

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


def _short(*parts: str) -> str:
    """Six hex of `parts` — the tail that keeps a short container name apart from every other on the machine."""
    return hashlib.sha1("\0".join(parts).encode()).hexdigest()[:6]


def gateway_of(container: str) -> str:
    """The allowlist's gateway of a project's `container`, named by its role within the project's group."""
    return f"gateway-{_short(container)}"


def end_started() -> None:
    """At this server's exit: its project containers, and every call in them — killing a `docker exec` client leaves
    its call running inside (probe P1), so the server's children would outlive it there and go on spending."""
    if ids := list(_STARTED):
        _keep_logs([*ids, *map(gateway_of, ids), *_DOORS])          # …a session's commands among `ids`
        run(["docker", "rm", "-f", *ids, *map(gateway_of, ids), *_DOORS], timeout=120)
        run(["docker", "network", "rm", *[f"{i}-net" for i in ids]], timeout=120)
        _STARTED.clear()
    if _DISK_WATCH.is_set() and _FILES:              # …what changed since the last reading, the work now gone: else on no record, nothing said (critic, ran)
        try:
            _record_files(_disk_works(_home()))
        except (OSError, ValueError, subprocess.TimeoutExpired) as e:
            log.warning(f"what changed last on Docker's disk was not recorded ({e})")


at_exit(end_started)


def end_leftovers() -> None:
    """At a server's start: the project containers of a server that is gone — their calls died with it, and each is
    started afresh on its project's first call. This installation's alone (`identity`) — and those of a build that set
    no home, whichever installation's: a server started while another installation's older build runs ends its run. Its
    listener went with it while they ran on, so their projects' records say a gap (critic, ran: nothing did)."""
    if shutil.which("docker"):
        got = run(["docker", "ps", "-a", "--filter", f"label={LABEL}", "--format",
                   f'{{{{.ID}}}} {{{{.Label "{HOME}"}}}} {{{{.Label "{PROJECT}"}}}}'], timeout=60, text=True)
        rows = [r.split(" ") + [""] * 2 for r in (got.stdout or "").splitlines()]
        if ids := [r[0] for r in rows if r[1] in ("", _home())]:
            _keep_logs(ids)
            for project in {r[2] for r in rows if r[1] == _home() and r[2]}:
                for record in (network_record_path(project), file_record_path(project)):
                    append(record, {"at": time.time(), "gap": "a server went with its work standing: what that work did since may not be on the record"})
            run(["docker", "rm", "-f", *ids], timeout=120)
        run(["docker", "network", "prune", "-f", "--filter", f"label={HOME}={_home()}"], timeout=120)


class WayOut:
    """A container's way out, as its switch sets it: open on Docker's bridge with the host shut by root inside; closed on
    an internal network of its own, out of reach of anything inside, with the allowlist's gateway the one member of both
    networks, writing its log under `home`, beside the CLI's state and not in it."""

    def __init__(self, container: str, name: str, image: str, home: Path, project: str):
        self.container, self.name, self.image, self.home, self.project = container, name, image, home, project
        self.net, self.gateway = f"{container}-net", gateway_of(container)
        #: its doors' port, the project's own and under the kernel's choice of ports: on Docker's bridge, under an open
        #: switch, the seal lets a session open this port on the bridge's addresses, and a fixed well-known one reached
        #: any container of the user's listening there
        self.door_port = DOOR_PORTS + int(_short(container), 16) % 10000

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

    def gateway_args(self) -> tuple[list, list]:
        """(flags, args) of the allowlist's gateway (`_system_run`): on the project's network first, so it listens
        there alone (it joins Docker's bridge after, to reach out), the execution's own image running `egress.py`
        read-only, unprivileged and bounded, nothing of the host mounted."""
        return ([*labelled(self.name, self.project), *grouped(self.container, "gateway"),
                 "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--read-only",
                 "--sysctl", "net.ipv4.ip_forward=0", *_SMALL,
                 "--network", self.net, "--network-alias", GATEWAY],
                [",".join(self.network[1]), f"{OWN}/egress.log", GATEWAY])

    def run_args(self) -> list[str]:
        """What `docker run` of the container takes for this way out: NET_ADMIN for root's seal (`seal`); when closed its
        internal network, no IPv6, and under an allowlist the gateway named its proxy."""
        mode = self.network[0]
        if mode == "open":
            # …no IPv6 under it either: the seal is IPv4's, and a bridge with IPv6 on passed around it (critic)
            return ["--cap-add", "NET_ADMIN", "--sysctl", "net.ipv6.conf.all.disable_ipv6=1"]
        return ["--network", self.net, "--cap-drop", "ALL", "--cap-add", "NET_ADMIN",
                "--sysctl", "net.ipv6.conf.all.disable_ipv6=1",
                *[a for k in ("HTTPS_PROXY", "https_proxy") for a in ("-e", f"{k}=http://{GATEWAY}:{egress.PORT}")
                  if mode == "allowlist"]]

    def seal(self) -> str:
        """What root runs in the container before any call, under every switch: no connection opened TO it — its own
        loopback and the answers to what it opened aside —, so no other container reaches what runs inside: on one
        project network a session reached another node's judge by its name and read the server the judge was testing
        (critic F5). Under an open switch the host shut too — Docker Desktop's host network and the default gateway,
        Docker Engine's host, a seal finding none failing. Root alone holds the capability, at the seal: no agent's
        process runs as root."""
        inbound = ("iptables -A INPUT -i lo -j ACCEPT && iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED "
                   "-j ACCEPT && iptables -A INPUT -j DROP")
        # …and on its own network nothing but its project's door and gateway, opened by TCP from a port the kernel picks:
        # two sessions each sending to the other were each other's «answers» past the inbound seal (UDP, or both ends of
        # one port pair), a channel between nodes under a closed switch (critic over the stream in use, run live)
        to_own = 'iptables -A OUTPUT -d "$sn"'
        own = " && ".join((f'sn=$({_SUBNET_OF}) && [ -n "$sn" ]', "iptables -A OUTPUT -o lo -j ACCEPT",
                           f"{to_own} -m conntrack --ctstate ESTABLISHED -j ACCEPT",
                           *(f"{to_own} -p tcp --dport {port} --sport {EPHEMERAL} -m conntrack --ctstate NEW -j ACCEPT"
                             for port in (self.door_port, *(() if self.network[0] == "open" else (egress.PORT,)))),
                           f"{to_own} -j REJECT"))
        # …Docker's own resolver is on its loopback, past every other rule here, under every switch (critic, ran: 60 of 60 under `off`)
        resolver = (f"iptables -N gfso-names && iptables -A gfso-names -m limit --limit {new_flows()}/second --limit-burst {min(10000, 10 * new_flows())} -j RETURN && "
                    "iptables -A gfso-names -j DROP && iptables -A OUTPUT -o lo -d 127.0.0.11 -j gfso-names && ")
        if self.network[0] != "open":
            return f"{resolver}{own} && {inbound}"
        # …its resolvers answer names (on Linux often the router's, a private address); every other private address is
        # shut, after the host and the gateway themselves
        dns = ("for n in $(awk '/^nameserver [0-9.]+$/{print $2}' /etc/resolv.conf); do iptables -A OUTPUT -d $n -p "
               "udp --dport 53 -j ACCEPT && iptables -A OUTPUT -d $n -p tcp --dport 53 -j ACCEPT || exit 1; done && ")
        shut = " && ".join(f"iptables -A OUTPUT -d {n} -j REJECT" for n in PRIVATE_NETS)
        # ...one session's new flows, as fast as it could open them, stopped Docker Desktop's backend and every project with it
        # (critic, measured). An unanswered UDP stream stays NEW on every packet, so one past the rate is limited too: this
        # kernel has no way to count a flow's first packet alone (`connbytes`, measured absent)
        flows = (f"iptables -N gfso-flows && iptables -A gfso-flows -m limit --limit {new_flows()}/second --limit-burst {min(10000, 10 * new_flows())} -j RETURN && "
                 "iptables -A gfso-flows -j DROP && iptables -A OUTPUT -o lo -j ACCEPT && iptables -A OUTPUT -m conntrack --ctstate NEW -j gfso-flows && "
                 # …and all that leaves but TCP, which paces itself: an answered flow is not new, and passed the bound whole (critic, ran: 300 of 300)
                 f"iptables -N gfso-udp && iptables -A gfso-udp -m limit --limit {min(10000, 25 * new_flows())}/second --limit-burst 10000 -j RETURN && "
                 "iptables -A gfso-udp -j DROP && iptables -A OUTPUT ! -p tcp -j gfso-udp && ")
        return (f'{resolver}{flows}{dns}iptables -A OUTPUT -d {HOST_NET} -j REJECT && gw=$({_GATEWAY_OF}) && [ -n "$gw" ] && '
                f'iptables -A OUTPUT -d "$gw" -j REJECT && {own} && {shut} && {inbound}')

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
             *labelled(self.name, self.project), self.net], timeout=60).check_returncode()
        if mode == "allowlist":
            flags, args = self.gateway_args()
            _system_run(self.gateway, self.image, flags, Path(egress.__file__), args, self.log())
            run(["docker", "network", "connect", "bridge", self.gateway], timeout=60).check_returncode()

    def log(self) -> Path:
        """The host's mirror of every connection the allowlist's gateway opened or refused — written by the gateway in
        its own memory as it happens, out of every session's reach, and kept here as it goes (`log_text`)."""
        return self.home / "egress" / self.container / "egress.log"

    def log_text(self) -> str:
        """The gateway's log: what the mirror kept and what the running gateway wrote since."""
        return _log_out([self.gateway], self.log())

    def close(self) -> None:
        """The gateway, its log kept in the mirror, and the network."""
        _mirror([self.gateway], self.log())
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
        name = f"door-{_short(self.way.container, d)}"
        if d not in self.held or not (address := self._address(name)):
            try:
                address = self._start(name, credential, upstream, closed)
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                # …no call of the project reaches its model: the place down, its stop said as such (critic 3)
                raise PlaceUnavailable(self.way.name, f"its model door did not start ({e})") from e
        return f"http://{name if closed else address}:{self.way.door_port}", self.held[d][1]

    def _start(self, name: str, credential, upstream: str, closed: bool) -> str | None:
        """One door started holding `credential`, its key kept; its address on Docker's bridge."""
        run(["docker", "rm", "-f", name], timeout=60)
        key = PLACEHOLDER + uuid.uuid4().hex
        _DOORS.add(name)                      # …before it runs: a start cut after this still ends with the server
        _system_run(name, self.way.image, [
            *labelled(self.way.name, self.way.project), *grouped(self.way.container, "door"),
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--read-only", *_SMALL,
            "--sysctl", "net.ipv4.ip_forward=0", "--tmpfs", f"{door.RUN}:size=64k,mode=1777",
            *(["--network", self.way.net, "--network-alias", name] if closed else [])],
            Path(door.__file__), [upstream, f"{OWN}/door.log", name if closed else "0.0.0.0", "1" if closed else "0",
                                  str(self.way.door_port)],
            self.log())
        # …laid by a `docker exec` whose environment is its own and gone with it: in no configuration Docker keeps
        laid = json.dumps({"kind": credential.kind, "value": credential.value, "key": key})
        run(["docker", "exec", *SYS, "-e", "GFSO_DOOR_LAID", name, "/bin/sh", "-c",
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
        """The host's mirror of every request the doors passed or refused — written by each door in its own memory as
        it happens, and kept here as they go (`log_text`)."""
        return self.way.home / "door" / self.way.container / "door.log"

    def log_text(self) -> str:
        """The doors' log: what the mirror kept and what the running doors wrote since."""
        return _log_out([n for n, _ in self.held.values()], self.log())

    def close(self) -> None:
        """Every door of the project, its log kept in the mirror, and the credentials they hold."""
        if names := [n for n, _ in self.held.values()]:
            _mirror(names, self.log())
            run(["docker", "rm", "-f", *names], timeout=60)
            _DOORS.difference_update(names)
        self.held = {}


def _ending(call: str) -> str:
    """What ends a call inside a container: its group, by the pid it wrote, and whatever left the group (`setsid`),
    found by its mark in the environment."""
    return (f"p=$(cat /tmp/gfso-calls/{call} 2>/dev/null) && kill -KILL -$p; "
            f"for e in /proc/[0-9]*/environ; do grep -qz GFSO_CALL={call} $e 2>/dev/null && "
            f"q=${{e#/proc/}} && kill -KILL ${{q%/environ}}; done; rm -f /tmp/gfso-calls/{call}")


def _up(name: str) -> bool:
    got = run(["docker", "inspect", "-f", "{{.State.Running}}", name], timeout=30, text=True)
    return got.returncode == 0 and (got.stdout or "").strip() == "true"


class Commands:
    """A SESSION'S COMMANDS, APART FROM ITS MODEL CLIENT (`shell.py`). Run beside the client, as its uid in its PID
    namespace, a command wrote the client's stdout through `/proc` and forged the stream the system reads as the record
    of what the session did (S6 probe). So the client's CLI takes the system's `shell.CLIENT` for its shell, and each
    command runs in a container of its own beside the session's: the place mounted as the session mounts it — never its
    CLI state —, the session's network and so its way out, a PID namespace of its own, as the image's user with no
    capability under no-new-privileges. Its listener is root there, holding SETUID, SETGID and KILL alone: no command
    signals it, reads it, or writes its record, which it keeps in its memory, the system reading it (`record`) and
    mirroring it beside the door's log when it goes. A bash the CLI starts beside itself — it takes no shell it finds
    wrong, silently — runs nothing (`shell.GUARD`) and is on the record as such. Started by the session's first model
    client, checked by one command through it; gone with the session's container."""

    #: what the listener holds: each command run as the image's user, and its group ended
    CAPS = ("SETUID", "SETGID", "KILL")

    def __init__(self, session: "PlaceContainer"):
        self.session, self.name, self.user = session, f"{session.container}-commands", None

    def start(self, flags: list) -> None:
        """Running with the session's `flags` (its labels and mounts), the client laid in the session's container
        (running already) and answering through it."""
        s = self.session
        if self.name in _STARTED and _up(self.name):
            return
        # …the session's own user, as numbers: the listener refuses root, who would reach what holds the record
        user = ":".join(run(["docker", "exec", *SYS, s.container, "/bin/sh", "-c", "id -u; id -g"], timeout=60,
                            text=True).stdout.split())
        self.close()
        run(["docker", "rm", "-f", self.name], timeout=60)
        _STARTED[self.name], self.user = s.container, user     # …before it runs: a cut start ends with the server
        said = {PROJECT: s.project_name, NODE: s.node, ROLE: s.role, AGENT: s.agent, "session": s.container,
                "place": s.to_inside(str(s.rw))}
        _system_run(self.name, s.image, [
            *labelled(s.name, s.project_name), "--label", f"{NODE}={s.node}", *flags, "-u", "0", "--cap-drop", "ALL",
            *[a for c in self.CAPS for a in ("--cap-add", c)], "--security-opt", "no-new-privileges",
            "--log-opt", "max-size=20m", *container_limits(), "--network", f"container:{s.container}"],
            Path(shell.__file__), ["serve", user, f"{OWN}/commands.log", json.dumps(said)], self.log(), "0700")
        laid = io.BytesIO()
        with tarfile.open(fileobj=laid, mode="w") as t:
            for name, mode, data in ((shell.CLIENT, 0o555, b"#!/usr/bin/env -S python3 -I\n"
                                      + Path(shell.__file__).read_bytes()), (shell.BESIDE, 0o444, shell.GUARD.encode()),
                                     (shell.NO_GIT, 0o555, shell.NONE.encode())):
                (i := tarfile.TarInfo(Path(name).name)).size, i.mode = len(data), mode
                t.addfile(i, io.BytesIO(data))
        run(["docker", "exec", "-i", "-u", "0", *SYS, s.container, "/bin/sh", "-c",
             f"/bin/mkdir -p -m 755 {shell.HOME} && /bin/tar -x -C {shell.HOME} -f - && /bin/cp "
             f"{shell.HOME}/{Path(shell.NO_GIT).name} {shell.NO_GIT} && /bin/chmod 755 {shell.NO_GIT}"],
            input=laid.getvalue(), timeout=60).check_returncode()   # …by path: root's PATH starts at the agent's home
        # …and one command through it, as the CLI will send them: a listener not up yet is waited for, never passed
        run(["docker", "exec", *SYS, "-u", user, s.container, "/bin/sh", "-c",
             'for i in $(seq 100); do "$0" -c true 2>/dev/null && exit; sleep 0.1; done; exit 1', shell.CLIENT],
            timeout=60).check_returncode()

    def record(self) -> list[dict]:
        """Each line the listener wrote — its mirror's first, from the containers it stood in before."""
        lines = _log_out([self.name] if self.name in _STARTED else [], self.log()).splitlines()
        return [r for r in map(_json_or_none, lines) if isinstance(r, dict)]

    def end(self, call: str, every: bool = False) -> None:
        """What the client's call `call` left running here, ended as its user: the listener holds no command's uid.
        `every`: the place's last client gone — every command's process ends, one that left its call's group and
        dropped its mark (`setsid`, `env -u`) with them: nothing an agent started outlives the session it ran in."""
        if self.name in _STARTED and self.user:
            run(["docker", "exec", *SYS, "-u", self.user, self.name, "/bin/sh", "-c",
                 _ending(call) + ("; kill -KILL -1" if every else "")], timeout=60)

    def log(self) -> Path:
        """The host's mirror of the record, beside the door's log."""
        return self.session.way.home / "commands" / self.session.way.container / f"{self.session.container}.log"

    def close(self) -> None:
        """Gone, its record kept in the mirror."""
        if _STARTED.pop(self.name, None) is not None:
            _mirror([self.name], self.log())
            run(["docker", "rm", "-f", self.name], timeout=60)


def _json_or_none(line: str):
    try:
        return json.loads(line)
    except ValueError:
        return None


class Volume:
    """A project's own directory as two Docker volumes — its places (`name`) and its sessions' CLI state (`state`,
    `.gfso-state`), which the project's container never mounts: the system's own git runs there over places an agent
    wrote, and a hook it planted read and rewrote another place's conversation (critic over 6202d19).

    ONE RULE, here alone. A volume's name carries all that identifies it — this installation's state home, the
    execution, the project, the base — so two installations, two bases or two executions never share one. It is
    made in `ready` alone, labelled with this home, and one standing under its name without that label — another
    home's, or Docker's own making — is refused, never emptied nor used. Every container that mounts it — the
    project's, a session's, the keeper, the storage probe, the copy-in, an export — asks `require` first, and the
    project's and a session's ask again once started: Docker makes a missing volume, empty and unlabelled, wherever
    one is named. Which volume holds each role is the project's own record (`VOLUME` + `places` / `state` in its
    settings, the system's: it survives the server): the record's volume missing is the place down, never refilled;
    the record naming another volume than this execution would mount (a state home moved, the execution declared on
    another base) is the place down too, both names said; no record, not made yet. Kept across every stop and every
    sweep of leftovers — it holds the project's work —, removed with the project alone (`drop_volumes`)."""

    def __init__(self, container: str, execution: str, own: Path, base: Path, project: str,
                 image: "str | None" = None):
        key = f"{_home()}-{hashlib.sha1(os.path.normcase(base).encode()).hexdigest()[:6]}"
        self.name, self.state = f"{container}-{key}-v", f"{container}-{key}-state"
        self.execution, self.own, self.base, self.project = execution, own, base, project
        self.labels = identity(execution, project)
        made: dict = {}
        #: (read, write) of the project's own settings, where the record of its volumes is kept — set by whoever holds
        #: the project (`workspaces.execution_of`), with what a copy-in `carried` (the places and rounds it moved in);
        #: none held, this process's alone
        self.record, self.carried = (made.get, made.__setitem__), lambda dirs: None
        #: the project's root as its base's import is keyed (`import_base`) — set by whoever holds the project; None
        #: before it has one
        self.root = lambda: None
        #: where what the system says of the volume goes — the project's log, set by whoever holds it
        self.said = lambda text: None
        self.copy_time = 1800                            # seconds a copy-in may take
        #: the image its directories are read in for the disk's watch (`_read`) — its execution's
        self.image = image

    def mount(self, src: Path, ro: bool, dst: str) -> list[str]:
        """`--mount` of the directory the system names `src` at `dst`: its CLI state's volume under `.gfso-state`, the
        places' under the rest of the project's own directory (`own`), whole or a subpath, and under the base (its
        `BASE_DIR`). Nothing of the host. A spec, nothing asked: whoever starts a container on it asks `require`."""
        states = self.own / STATE_DIR
        vol, sub = ((self.state, src.relative_to(states)) if src.is_relative_to(states) else
                    (self.name, src.relative_to(self.own)) if src.is_relative_to(self.own) else
                    (self.name, (BASE_READ if ro else BASE_DIR) / src.relative_to(self.base)))
        spec = f"type=volume,src={vol},{_mount_field('dst', dst)}" + ("" if sub == Path(".") else f",volume-subpath={sub.as_posix()}")
        return ["--mount", spec + (",readonly" if ro else "")]

    def key(self, root: Path) -> tuple:
        """(volume, subpath) the directory `root` is, as Docker mounts it — the disk's ledger's key (`DiskLedger`)."""
        spec = self.mount(root, False, "/x")[1]
        return re.search(r"src=([^,]+)", spec)[1], (re.search(r"volume-subpath=([^,]+)", spec) or [None, "."])[1]

    @contextlib.contextmanager
    def writes(self, root: Path, path: "Path | None" = None, removing: bool = False):
        """The system writing into the directory `root` of this volume, at its `path` (`root` itself where none):
        measured just before and after, what it wrote there no node's (`DiskLedger.wrote`); `removing` it, what the
        system had put under `path` comes off (`DiskLedger.removed`); not read against any node meanwhile."""
        under = Path(path).relative_to(root).as_posix() if path is not None and Path(path) != Path(root) else "."
        at = self.key(root)
        held = lambda: _read(at[0], [at[1]], self.image).get(at, (0, 0))
        # ONE MEASUREMENT PER SPAN OF THE SYSTEM'S WRITES THERE: read before the first starts and after the last ends,
        # under the directory's own lock for the reading alone — a write nested in another (a bring's carry) or beside
        # it (two joins into one parent) counted twice banked credit (critic); none of it held across the write itself
        with _KEY_LOCKS.setdefault(at, threading.Lock()):
            if _LEDGER.writing(at, True) == 1 and not removing:
                try:
                    _BEFORE[at] = held() if at in _LEDGER.base else (0, 0)
                except (OSError, subprocess.TimeoutExpired):
                    _BEFORE[at] = None
        try:
            yield
        finally:
            with _KEY_LOCKS[at]:
                if _LEDGER.busy.get(at) == 1 and removing and at not in _BEFORE:
                    _LEDGER.removed(at, under)
                elif _LEDGER.busy.get(at) == 1:     # …the last: measured and booked while still marked
                    before = _BEFORE.pop(at, None)
                    try:
                        after = held()
                    except (OSError, subprocess.TimeoutExpired):
                        after = None
                    if before is None or after is None:
                        _LEDGER.lose(at)
                    else:
                        _LEDGER.wrote(at, before, after, under)
                _LEDGER.writing(at, False)

    def _roles(self) -> dict:
        return {"places": self.name, "state": self.state}

    @staticmethod
    def _labels(v: str):
        """The labels of the volume `v` as it stands, None where it does not."""
        got = run(["docker", "volume", "inspect", "-f", "{{json .Labels}}", v], timeout=60, text=True)
        if got.returncode:
            return None
        with contextlib.suppress(ValueError):
            if isinstance(labels := json.loads(got.stdout or "{}"), dict):
                return labels
        return {}

    def require(self, args: list) -> None:
        """Each of this project's volumes `args` mount stands as the project's record names it, made by this
        installation — else no container runs on it: the place down (`PlaceUnavailable`), or, with no record and no
        volume, not made yet (`LookupError`)."""
        for role, v in self._roles().items():
            if not any(f"type=volume,src={v}," in a for a in args):
                continue
            if (named := self.record[0](VOLUME + role)) and named != v:
                raise PlaceUnavailable(self.execution, f"the project's record holds its {role} in the volume {named}, "
                                       f"and this execution would mount {v}: declare the execution back as it was, or "
                                       f"remove the project's `{VOLUME}` settings to start it on new, empty volumes")
            if (labels := self._labels(v)) is None:
                if named:
                    raise PlaceUnavailable(self.execution, f"its volume {v} is gone: the project's record holds its "
                                                           f"{role} there")
                raise LookupError(f"its volume {v} is not made yet")
            if labels.get(HOME) != _home():
                raise PlaceUnavailable(self.execution, f"the volume {v} is not this installation's making (its labels: "
                                                       f"{labels or 'none'}): nothing runs on it")

    def ready(self, image: str, host: Path, old: Path, places: dict, dirs: list) -> None:
        """Both volumes as the project's record names them, else made now, ONCE. Made: each created with its labels,
        what stood in them emptied (a copy cut midway), a project's directory that stood on the `host` before it moved
        in copied whole by a container of its own (Linux reads an agent's links as links there; Docker Desktop's
        `docker cp` skipped every one and exited 0, critic over 71b49ad), checked by the count of each kind of entry,
        and each place's CLI state from the `old` per-project state carried to its new name (`places`: {old key: new
        name}); then the places and rounds it carried (`dirs`) recorded as made, the volumes recorded, and the sources
        CONSUMED — renamed `<dir>.copied-in-<time>`, at each start until it took — so neither a lost volume nor a
        project made again under the name refills from them. A copy that fails, differs or outruns its time records
        nothing, its container removed, and the next start tries again. To roll back to the host: export the places
        (`gfso export-places`) — what the project did since lives in the volume alone —, remove both volumes and the
        project's `volume:` settings, and rename each `.copied-in-<time>` directory back."""
        both = [f"type=volume,src={v}," for v in (self.name, self.state)]
        try:
            self.require(both)
            if all(self.record[0](VOLUME + r) for r in self._roles()):
                self._keep(image)
                self.import_base(image)
                return self._consume(host, old)
        except LookupError:                  # …not made yet: made below
            pass
        # …and the project's id from its record: Docker relabels no volume, so one made before the project had an id
        # carries none for its life, and no removal of an orphan's volumes ever takes it (`resources.remove_orphan`)
        labels = {**self.labels, **({ID: i} if (i := self.record[0](PROJECT_ID)) else {})}
        for v in (self.name, self.state):
            if self._labels(v) is None:
                run(["docker", "volume", "create", *[a for k, x in labels.items() for a in ("--label", f"{k}={x}")],
                     v], timeout=60).check_returncode()
        self.require(both)
        user = run(["docker", "image", "inspect", "-f", "{{.Config.User}}", image], timeout=60, text=True).stdout.strip()
        got = self._one_shot(image, [*[a for p, at in ((host, "/from"), (old, "/old")) if p.is_dir()
                                       for a in ("--mount", f"type=bind,{_mount_field('src', str(p))},dst={at},readonly")],
                                     "--mount", f"type=volume,src={self.name},dst=/to",
                                     "--mount", f"type=volume,src={self.state},dst=/state"],
                             [_BRING_IN, "sh", user or "0", *[x for k, v in places.items() for x in (k, v)]],
                             "bring-in", text=True)
        if got.returncode:
            raise OSError(f"{self.name}: the volume could not take its places ({(got.stderr or '').strip()[-300:]})")
        self.import_base(image, made=True)
        self.carried(dirs)
        for role, v in self._roles().items():
            self.record[1](VOLUME + role, v)
        self._keep(image)
        self._consume(host, old)

    def import_base(self, image: str, made: bool = False, again: bool = False) -> bool:
        """`_import_base`, the system's own write into the base: no node's growth against its disk bound."""
        with self.writes(self.base):
            return self._import_base(image, made, again)

    def _import_base(self, image: str, made: bool = False, again: bool = False) -> bool:
        """The base in the volume (`BASE_DIR`) as the user's repository stands — imported where nothing of it stands
        yet: by the project's first container start (`made`: its volumes made now), or, `again`, by THE CREATION OF A
        NEW ROOT of the project (`workspaces.root_created`). NEVER BY A START OVER A RECORD: a restart, a switch turned,
        Docker restarted keep what the root's work made there. Recorded `IMPORTED` — the root it serves (`root`, None
        before the project has one: the first root adopts it), the commit — and said (`said`): which commit, what of
        the user's did not come in. On the host only the user's own git runs: `git bundle` of their HEAD and of the
        project's node branches left from before (`gfso/<p>/*` but `accepted`), carried in through the port (a
        container's stdin), fetched inside by git under no config but its own — checked out LF, Linux modes and links,
        none of the user's hooks or config, a branch that stands in the volume never overwritten; their `info/exclude`
        and `info/attributes` with it. A base with no git: a tar of its tree, imported ONCE — a root's work there is
        never written over. True where it imported."""
        rec = json.loads(self.record[0](VOLUME + IMPORTED) or "{}")
        if rec and not made and (not again or rec.get("commit") == "tree"):
            if not rec.get("read"):              # …a volume from before sessions read a copy
                self.read_again(image)
                self.record[1](VOLUME + IMPORTED, json.dumps({**rec, "read": 1}))
            return False
        root = self.root()
        with tempfile.TemporaryDirectory(prefix="gfso-import-") as d:
            commit, carried, notes = _carried_in(self.base, self.project, Path(d))
            user = run(["docker", "image", "inspect", "-f", "{{.Config.User}}", image], timeout=60,
                       text=True).stdout.strip()
            with open(carried, "rb") as stream:
                got = self._one_shot(image, ["--mount", f"type=volume,src={self.name},dst=/to"],
                                     [_IMPORT, "sh", commit or "", BASE_DIR, self.project,
                                      *lfs.filter_args(ContainerExecution.python)[1::2]], "import", user or "0",
                                     stdin=stream, interactive=True)
        if got.returncode:
            raise OSError(f"{self.name}: the base could not be imported "
                          f"({(got.stderr or b'').decode(errors='replace').strip()[-300:]})")
        self.record[1](VOLUME + IMPORTED, json.dumps({"for": root, "commit": commit or "tree", "read": 1,
                                                       "at": time.strftime("%Y-%m-%dT%H:%M:%S")}))
        self.said(f"the base is imported into the project's volume from {self.base}: "
                  + (f"its commit {commit[:12]}" if commit else "its tree (no git: imported once)")
                  + "".join(f"; {n}" for n in notes))
        return True

    def read_again(self, image: str) -> None:
        """The copy of the base sessions read, made or brought to the base's HEAD (`_READ_COPY`), by git under no config
        of a repository's."""
        user = run(["docker", "image", "inspect", "-f", "{{.Config.User}}", image], timeout=60, text=True).stdout.strip()
        got = self._one_shot(image, ["--mount", f"type=volume,src={self.name},dst=/to"],
                             [_READ_AGAIN, "sh", BASE_DIR, *lfs.filter_args(ContainerExecution.python)[1::2]], "read",
                             user or "0")
        if got.returncode:
            raise OSError(f"{self.name}: the base's read copy could not be brought up "
                          f"({(got.stderr or b'').decode(errors='replace').strip()[-300:]})")

    def land_tree(self, image: str, to: Path) -> list:
        """A base with no git as it stands in the volume, written to the host directory `to` in place of what stood
        there — a root's accepted result, where its user reads it; what could not be written as it stood
        (`_untar`)."""
        with self._read_out(image, [f"tar -c -C /from/{BASE_DIR} ."], "land", to) as (got, held):
            if got.returncode:
                raise OSError(f"{self.name}: its base could not be read out "
                              f"({(got.stderr or b'').decode(errors='replace').strip()[-300:]})")
            if to.exists():
                shutil.rmtree(to)
            return _untar(held, to)

    @contextlib.contextmanager
    def _read_out(self, image: str, script: list, role: str, to: Path):
        """(the run of `script` over the places, read-only and as the image's user; what it printed): a tar stream, in a
        file on the disk it is about to land on, gone after: all a project holds passes through no process's memory."""
        user = run(["docker", "image", "inspect", "-f", "{{.Config.User}}", image], timeout=60, text=True).stdout.strip()
        to.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=to.parent) as held, tempfile.TemporaryFile(dir=to.parent) as said:
            got = self._one_shot(image, ["--mount", f"type=volume,src={self.name},dst=/from,readonly"], script, role,
                                 user or "0", stdout=held, stderr=said)
            # …its last megabyte: what tar says of each file it cannot read is of a size the session chose (critic, ran)
            said.seek(max(0, said.seek(0, os.SEEK_END) - 2 ** 20))
            got.stderr = said.read()
            held.seek(0)
            yield got, held

    def _keep(self, image: str) -> None:
        """Beside the volumes in the record, what an export reads them by: the base and the image they stand over."""
        for k, v in (("base", str(self.base)), ("image", image)):
            if self.record[0](VOLUME + k) != v:
                self.record[1](VOLUME + k, v)

    def _one_shot(self, image: str, mounts: list, script: list, role: str, user: str = "0", interactive: bool = False,
                  **kw) -> subprocess.CompletedProcess:
        """`script` in a container of the system's own over `mounts` — no network, its volumes asked first; as root with
        the system's capabilities, or as `user` with none; fed its stdin where `interactive` — named by its `role`, so a
        cut one is removed with the cut and a server's next start sweeps one left (`end_leftovers`)."""
        self.require(mounts)
        one = f"{self.name}-{role}"
        run(["docker", "rm", "-f", one], timeout=60)
        try:
            got = run(["docker", "run", "--rm", *(["-i"] if interactive else []), "--name", one,
                       *labelled(self.execution, self.project), "--network", "none", "--cap-drop", "ALL",
                       *[a for c in SYSTEM_CAPS if user == "0" for a in ("--cap-add", c)],
                       "--security-opt", "no-new-privileges", *container_limits(), *ceiling(), "-u", user, *mounts, image,
                       "sh", "-c", *script],
                      timeout=self.copy_time, **kw)
        except subprocess.TimeoutExpired:
            _end_cut(one)                                       # …a copy cut by its time must not go on writing
            raise
        if got.returncode:
            run(["docker", "rm", "-f", one], timeout=60)
        return got

    @staticmethod
    def _consume(host: Path, old: Path) -> None:
        """The copy-in's sources renamed aside; one the host will not rename now (a file held open) is tried again at
        the next start."""
        for p in (host, old):
            if p.is_dir():
                try:
                    p.rename(p.with_name(f"{p.name}.copied-in-{time.strftime('%Y%m%dT%H%M%S')}"))
                except OSError as e:
                    log.warning(f"{p} was copied in and could not be moved aside now ({e}): tried again at the next start")

    def export(self, image: str, to: Path) -> list:
        """The places as they stand, written to the host directory `to`, INERT — no repository carries its agent's
        config or hooks, so nothing an agent wrote runs where the export is read — each node's clone made whole on the
        way (`_EXPORT`), in a copy and never in the place, so it reads with the volume and the base both gone. What
        could not be carried as it stood — a clone not repacked, an entry the host refused, a link leading out of
        `to`, kept as a file naming its target — is said in `.gfso-export-notes` beside `to`, and returned; nothing
        exported at all is an `OSError`. Its CLI state is not exported."""
        with self._read_out(image, [_EXPORT, "sh", f"/from/{BASE_DIR}"], "export", to) as (got, held):
            said = [x[6:] for x in (got.stderr or b"").decode(errors="replace").splitlines() if x.startswith("NOTE: ")]
            if got.returncode:
                raise OSError(f"{self.name}: its places could not be exported ({'; '.join(said) or got.returncode})")
            try:
                notes = said + _untar(held, to) + _left_inert(to)
            except OSError as e:
                shutil.rmtree(to, ignore_errors=True)
                raise OSError(f"{self.name}: an exported repository could not be made inert, nothing is left of the export ({e})")
        if notes:
            (to.parent / ".gfso-export-notes").write_text("\n".join(notes) + "\n", encoding="utf-8")
        return notes

    def remove(self) -> None:
        """Both gone, with every place in them."""
        run(["docker", "volume", "rm", "-f", self.name, self.state], timeout=120)

    @classmethod
    def of_record(cls, project: str, record: dict) -> tuple["Volume", str]:
        """(the volume `project`'s own record names, asked against that record, the image it stands over)."""
        if not (named := record.get(VOLUME + "places")):
            raise LookupError("the project's record names no volume of its places: none was made for it")
        if (labels := cls._labels(named)) is None:
            raise PlaceUnavailable(project, f"its volume {named} is gone: the project's record holds its places there")
        execution = labels.get(LABEL, "")
        if not (base := record.get(VOLUME + "base") or _base_of_places(record)):
            raise LookupError(f"the project's record names no base its volume {named} stands over")
        if not (image := record.get(VOLUME + "image") or executions().get(execution, {}).get("image")):
            raise LookupError(f"the project's record names no image, and its execution {execution!r} is declared "
                              f"nowhere here ({executions_path()})")
        b, name = Path(base), component(project)
        v = cls(container_name(execution, project), execution, b.parent / nodes_dir(b.name) / name, b, name)
        v.record = (record.get, None)     # …asked against the record: a base that names another volume, refused
        return v, image


def export_places(project: str, record: dict, to: str) -> list:
    """The places of `project` as they stand, written under the host directory `to` in a directory named by the
    project — read with its volumes and its base gone, inert (`Volume.export`); what it could not carry. By the
    project's own record (`record`, its settings) alone — the volume it names, the base and image kept beside it —, never
    by the roster or declarations of whoever asks, which may be another server's or none (measured: a project with a
    volume exported "nothing"). No volume recorded, none was made (`LookupError`); the recorded one gone, the place down."""
    v, image = Volume.of_record(project, record)
    return v.export(image, Path(to) / v.project)


def _base_of_places(record: dict) -> str | None:
    """The base, by a place the record holds made (`<parent>/<NODES><base>/<project>/<node>`) — a volume recorded before
    its base was kept beside it; the volume's own name then confirms it (`Volume.require`)."""
    for k in record:
        if k.startswith(MADE):
            p = Path(k[len(MADE):])
            return str(p.parents[2] / base_named(p.parents[1].name))
    return None


def _untar(data, to: Path) -> list:
    """A tar stream's entries (bytes, or a file holding them) under `to`, none outside it — a link whose target, read from its own directory, leaves
    `to`, or one the host cannot make, written as a file naming its target; an entry the host refuses passed over —
    and what was not written as it stood, said. On a disk that folds names, an entry whose name this disk would read
    as another is not written: a `.git.` or `git~1` beside a neutralised `.git` wrote into it (critic, live), a `CONFIG`
    over its config, an `X/` through a link `x`."""
    to.mkdir(parents=True, exist_ok=True)
    root, notes, spelled = to.resolve(), [], {}
    with tarfile.open(fileobj=io.BytesIO(data) if isinstance(data, bytes) else data) as t:
        for m in t.getmembers():
            at = Path(os.path.abspath(root / m.name))
            if at == root:
                continue
            try:
                # …where it really leads, through the links laid so far: a stream folded by a case-blind disk wrote through one
                if not at.is_relative_to(root) or not at.parent.resolve().is_relative_to(root):
                    raise OSError("outside the export")
                # …of the name as the stream spells it: `abspath` above has already trimmed it, on Windows
                if _FOLDING and _folds_onto_another([c for c in m.name.split("/") if c not in ("", ".")], spelled):
                    raise OSError("a name this disk would read as another")
                if m.islnk() and not (root / m.linkname).resolve().is_relative_to(root):
                    raise OSError("a hard link through a link out of the export")
                if not m.issym():
                    t.extract(m, to, filter="tar")
                    continue
                at.parent.mkdir(parents=True, exist_ok=True)
                if not Path(os.path.abspath(at.parent / m.linkname)).is_relative_to(root) or os.path.isabs(m.linkname):
                    notes.append(f"{m.name}: a link out of the export, kept as a file naming {m.linkname}")
                    at.write_text(m.linkname, encoding="utf-8")
                    continue
                try:
                    os.symlink(m.linkname, at)
                except OSError:
                    at.write_text(m.linkname, encoding="utf-8")
            except (OSError, ValueError, tarfile.TarError) as e:
                notes.append(f"{m.name}: not written ({e})")
    # …and where each link really leads, all of them laid: a chain, each of its links inside by its text, read a host
    # file through the export and had the sweep after it act out there (critic, ran)
    for d, dirs, files in os.walk(root):
        for p in (Path(d) / n for n in (*dirs, *files)):
            if p.is_symlink() and not Path(os.path.realpath(p)).is_relative_to(root):
                target = os.readlink(p)
                p.unlink()
                p.write_text(target, encoding="utf-8")
                notes.append(f"{p.relative_to(root).as_posix()}: a link out of the export, kept as a file naming {target}")
    return notes


#: a host whose disk reads two spellings as one name
_FOLDING = os.name == "nt" or sys.platform == "darwin"
#: all a neutralised repository's config holds (`_EXPORT`)
_INERT_LINE = re.compile(r"\s*(\[core\]|\[extensions\]|(repositoryformatversion|bare|objectformat|refstorage)\s*=\s*\w+)?\s*", re.I)


def _folds_onto_another(parts: list, spelled: dict) -> bool:
    """Would this disk read the path `parts` as another than it says? A name it trims or takes a stream of (Windows), a
    backslash it takes for a separator, its short name for `.git`, or a spelling differing from one laid before; what it
    lays is noted in `spelled`."""
    at = ""
    for c in parts:
        if c[-1] in ". " or ":" in c or chr(92) in c or re.fullmatch(r"git~\d+", c, re.I):
            return True
        at = f"{at}/{c.casefold()}"
        if spelled.setdefault(at, c) != c:
            return True
    return False


def _left_inert(to: Path) -> list:
    """The export as it landed on this host's disk, whatever spelled it there: no directory git would take for a
    repository holds what git would run or follow — a `.git` file, hooks, a `commondir`, a config beyond the format, an
    alternates file (a path of the agent's, which git opens: a share, a connection). What the container left behind for
    any cause is removed and said; what cannot be removed is an `OSError`: then no export."""
    notes = []

    def gone(p: Path, why: str) -> None:
        """`p` removed, whatever its modes, and said."""
        for d, _, fs in os.walk(p) if p.is_dir() and not p.is_symlink() else ():
            os.chmod(d, stat.S_IRWXU)
            for f in fs:
                with contextlib.suppress(OSError):
                    if not os.path.islink(os.path.join(d, f)):
                        os.chmod(os.path.join(d, f), stat.S_IRUSR | stat.S_IWUSR)
        shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
        notes.append(f"{p.relative_to(to).as_posix()}: {why}, removed")

    for d, dirs, files in os.walk(to):
        here, names = Path(d), {n.lower(): n for n in (*dirs, *files)}
        if ".git" in names and not (here / names[".git"]).is_dir():
            gone(here / names[".git"], "a .git that is no directory")
            dirs[:] = [n for n in dirs if n != names[".git"]]
        shaped = "head" in names and ("commondir" in names or ("objects" in names and "refs" in names))
        if here.name.lower() != ".git" and not shaped:
            continue
        for k in ("hooks", "commondir", "config.worktree"):
            if k in names:
                gone(here / names[k], "what git would follow in a repository")
                dirs[:] = [n for n in dirs if n != names[k]]
        if (cfg := here / names.get("config", "config")).is_dir() or cfg.is_symlink() or (
                cfg.is_file() and not all(_INERT_LINE.fullmatch(ln) for ln in cfg.read_text("utf-8", "replace").splitlines())):
            gone(cfg, "a repository's config beyond its format")
            dirs[:] = [n for n in dirs if n != cfg.name]
        if (alt := here / names.get("objects", "objects") / "info" / "alternates").exists() or alt.is_symlink():
            gone(alt, "a path git would open for objects")
    return notes


#: the environment of the user's git the system runs: an object a partial clone lacks is never fetched — its promisor
#: is the user's network, reached with their credentials, from no thread of the system's
NO_LAZY_FETCH = {"GIT_NO_LAZY_FETCH": "1"}


def _host_git(base: Path, **env):
    """git over the user's repository at `base`, run on the host by their own git: text out, or bytes fed `input`."""
    def git(*a, input=None):
        """One git call over `base`."""
        return run(["git", "-c", "safe.directory=*", "-C", str(base), *a], timeout=600, input=input,
                   env=subprocess_env(extra={**NO_LAZY_FETCH, **env}),
                   **({} if input is not None else {"text": True, "encoding": "utf-8", "errors": "replace"}))
    return git


def _is_top(base: Path, git) -> bool:
    """The question `worktrees.is_repo_top` asks: is `base` the top of a work tree with a commit?"""
    got = git("rev-parse", "--show-toplevel", "--verify", "HEAD") if shutil.which("git") and base.is_dir() else None
    top = got.stdout.splitlines()[:1] if got and got.returncode == 0 else []
    return bool(top) and same_place(top[0], base)          # …as places: git names a junction's or 8.3 name's target


def _no_places(base: Path) -> str | None:
    """Why a container runs no dispatched work over `base`: one that is no repository's top with a commit has no
    places — every session of the project would work in it, sharing one tree and one model client's state, no node's
    work its own and each reading the others'. Asked of the user's own repository on the host, as its import is."""
    git = _host_git(base)
    if _is_top(base, git):
        return None
    why = (f"{base} is not the top of a git repository with a commit, so its nodes have no places of their "
           f"own: every session would share one tree and read the others' conversations. ")
    # …walking up no further than the user's home: a home kept as a repository of its dotfiles is no work's top, and
    # naming it told the user's agent to import the home (critic)
    git = _host_git(base, GIT_CEILING_DIRECTORIES=str(Path.home()))
    top = git("rev-parse", "--show-toplevel") if shutil.which("git") and base.is_dir() else None
    if top is not None and top.returncode != 0 and git("rev-parse", "--is-inside-git-dir").stdout.strip() == "true":
        return why + "It lies inside a repository's own `.git` directory: register that repository's top as the workdir"
    if top is not None and top.returncode == 0 and (at := top.stdout.strip()):
        if same_place(at, base):
            return why + "It has no commit yet: `git add -A` and `git commit -m start` there"
        return why + (f"It lies inside the repository {at}: register that top as the workdir if the work is "
                      f"that repository's, else make this directory one of its own (`git init`, `git add -A`, "
                      f"`git commit -m start` there)")
    return why + "Make it one (`git init`, `git add -A`, `git commit -m start` there), then start the project again"



def _lfs_of(base: Path, git) -> tuple[dict, list]:
    """({oid: its object in the user's LFS store}, [the paths whose object it lacks]) of the LFS pointers in HEAD's
    tree — read as git stores them, so no git-lfs runs: a blob short enough to be a pointer and parsed as one
    (`lfs.parse`). An object counts where its size is the pointer's; its sha256 is checked where it is written (`lfs`).
    Missing ones are not fetched: that is the user's network and credentials, asked from no thread of the system."""
    entries = [e.split("\t", 1) for e in git("ls-tree", "-r", "-l", "-z", "HEAD").stdout.split("\0") if "\t" in e]
    small = [(m[2], path) for meta, path in entries
             if (m := meta.split())[1] == "blob" and m[3].isdigit() and int(m[3]) <= lfs.LONGEST]
    if not small:
        return {}, []
    out = git("cat-file", "--batch", input="".join(f"{sha}\n" for sha, _ in small).encode()).stdout
    pointers, at = [], 0
    for _, path in small:                     # …`<sha> blob <size>\n<content>\n`, in the order asked
        nl = out.index(b"\n", at)
        size = int(out[at:nl].split()[2])
        pointers += [(path, p)] if (p := lfs.parse(out[nl + 1:nl + 1 + size])) else []
        at = nl + 2 + size
    if not pointers:
        return {}, []
    store = _lfs_store(base, git)
    held = {oid: f for _, (oid, size) in pointers
            if (f := Path(lfs.path_in(str(store), oid))).is_file() and f.stat().st_size == size}
    return held, [path for path, (oid, _) in pointers if oid not in held]


def _lfs_store(base: Path, git) -> Path:
    """The user's LFS store, where their git-lfs keeps objects: `lfs.storage` (in the git dir where relative), else
    `.git/lfs` — its `objects`."""
    common = base / git("rev-parse", "--git-common-dir").stdout.strip()
    return common / (git("config", "--get", "lfs.storage").stdout.strip() or "lfs") / "objects"


def _missing(git) -> list:
    """The objects HEAD's history names that the user's repository does not hold — a partial clone's, never fetched
    (`NO_LAZY_FETCH`)."""
    if not git("config", "--get-regexp", r"^(extensions\.partialclone|remote\..*\.promisor)$").stdout.strip():
        return []
    return [x[1:] for x in git("rev-list", "--objects", "--missing=print", "HEAD").stdout.splitlines()
            if x.startswith("?")]


def left_out(base: Path) -> list[str]:
    """What of the user's repository at `base` the import of its HEAD does not bring into the agents' copy, each said
    with what brings it — asked by their own git on the host, before any import as at one (`_carried_in`)."""
    git = _host_git(base)
    return _left_out(base, git, _lfs_of(base, git)[1]) if _is_top(base, git) else []


def _left_out(base: Path, git, no_object: list) -> list[str]:
    changed = [x for x in git("status", "--porcelain", "-z").stdout.split("\0") if x.strip()]
    links = [e for e in git("ls-tree", "-r", "-z", "HEAD").stdout.split("\0") if e.startswith("160000 ")]
    missing = _missing(git)
    return [n for n, on in (
        (_unfetched(base, missing), missing),
        (f"{len(changed)} changed or untracked files of {base} are not in the agents' copy - commit them and start "
         f"again for the agents to see them", changed),
        (f"{len(links)} submodules of {base} stand empty in the agents' copy: their files are not part of the commit",
         links),
        (f"{len(no_object)} files tracked by Git LFS have no object in {base} and stand as pointers in the agents' copy"
         f" - fetch them (`git lfs fetch`) and start again ({', '.join(no_object[:3])}"
         f"{', ...' if len(no_object) > 3 else ''})", no_object)) if on]


def _unfetched(base: Path, missing: list) -> str:
    return (f"{len(missing)} objects of the history of {base}'s HEAD are not in it (a partial clone), and the system "
            f"fetches nothing with your credentials, so HEAD cannot be imported - fetch them "
            f"(`git rev-list --objects --missing=print HEAD` lists them) and start again")


def _carried_in(base: Path, project: str, d: Path) -> tuple:
    """(the commit, a tar under `d`, what of the user's it leaves out) of what the base imports (`_IMPORT`) — made on
    the host by the user's own git, reading their repository and nothing else: a bundle of HEAD and of the project's
    node branches left from before the base moved in, but `accepted`, with the LFS objects HEAD's pointers name that
    their store holds (`_lfs_of`); else, no git, its tree. Left out, said (`left_out`)."""
    out, git = d / "in.tar", _host_git(base)
    with tarfile.open(out, "w") as t:
        if not _is_top(base, git):
            if base.is_dir():
                t.add(base, arcname="tree")
            return None, out, []
        commit = git("rev-parse", "--verify", "HEAD^{commit}").stdout.strip()
        if missing := _missing(git):
            raise OSError(_unfetched(base, missing))
        (d / "branch").write_text(git("symbolic-ref", "-q", "--short", "HEAD").stdout.strip() or "main")
        if (got := git("bundle", "create", "-q", str(d / "bundle"), "HEAD", f"--exclude=gfso/{project}/accepted",
                       f"--branches=gfso/{project}/*")).returncode:
            raise OSError(f"{base}: its HEAD could not be bundled ({got.stderr.strip()[-300:]})")
        for n in ("bundle", "branch"):
            t.add(d / n, arcname=n)
        for n in ("exclude", "attributes"):
            if (p := base / git("rev-parse", "--git-path", f"info/{n}").stdout.strip()).is_file():
                t.add(p, arcname=n)
        held, no_object = _lfs_of(base, git)
        for oid, f in held.items():
            t.add(f, arcname=f"lfs/{oid}")
    return commit, out, _left_out(base, git, no_object)


def fetched_on_host(base: Path, bundle: bytes) -> str:
    """The objects of `bundle` taken into the user's repository at `base` by their own git — `fetch` of it alone, no
    ref written, no `FETCH_HEAD` —; git's words where it refused, else ''. Only a bundle: the bytes come out of a temp
    the base's sessions write, and handed anything else the host's git takes it for a repository it names and opens it,
    a network path too (critic over a99ea34)."""
    if not bundle.startswith((b"# v2 git bundle\n", b"# v3 git bundle\n")):
        return "what came out is no git bundle"
    with tempfile.TemporaryDirectory(prefix="gfso-land-") as d:
        (f := Path(d) / "accepted.bundle").write_bytes(bundle)
        # …every object it carries checked as git takes it (`fsckObjects`): the pack is made where an agent writes, and
        # the user's git parses it on the host (critic over the stream in use)
        got = run(["git", "-c", "fetch.fsckObjects=true", "-c", "transfer.fsckObjects=true", "-C", str(base), "fetch",
                   "-q", "--no-recurse-submodules", "--no-write-fetch-head", str(f), "HEAD"], timeout=600,
                  text=True, encoding="utf-8", errors="replace")
    return "" if got.returncode == 0 else (got.stderr or "").strip()[-300:] or f"git fetch exited {got.returncode}"


def stored_on_host(base: Path, want: dict, read) -> list[str]:
    """Each LFS object `want` names ({oid: (size, path)}) that the user's LFS store at `base` (`_lfs_store`) lacks, read
    (`read(oid, size)`: its bytes, verified, or None) and written there whole — by the system, as git-lfs lays it out:
    no git-lfs runs, nor any filter of the user's config. [The paths whose object could not be carried]."""
    store, lost = _lfs_store(base, _host_git(base)), []
    for oid, (size, path) in want.items():
        if (at := Path(lfs.path_in(str(store), oid))).is_file() and at.stat().st_size == size:
            continue
        if (data := read(oid, size)) is None or not lfs.is_object(data, oid, size):
            lost.append(path)
            continue
        at.parent.mkdir(parents=True, exist_ok=True)
        (tmp := at.with_name(f"{oid}.gfso-{uuid.uuid4().hex}")).write_bytes(data)
        os.replace(tmp, at)
    return lost


def container_name(execution: str, project: str) -> str:
    """The project's container under `execution` — the stem its volumes are named by."""
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", f"gfso-{execution}-{project}").lower()


def _home(data: Path | None = None) -> str:
    """This installation's state home — or the one whose state directory is `data` —, as a volume's label names it: two
    servers on one machine delete theirs alone."""
    return hashlib.sha1(str((data or data_dir()).resolve()).encode()).hexdigest()[:8]


#: `_home`, read from outside: the resource view attributes what Docker holds by it
installation = _home


def drop_volumes(project: str) -> None:
    """Every volume of the project — of this installation, whatever execution or base it was made for, its roster
    read or not: a new project of the name inherits none of its places."""
    got = run(["docker", "volume", "ls", "-q", "--filter", f"label={PROJECT}={component(project)}",
               "--filter", f"label={HOME}={_home()}"], timeout=60, text=True)
    for v in (got.stdout or "").split():
        if ids := (run(["docker", "ps", "-aq", "--filter", f"volume={v}"], timeout=60, text=True).stdout or "").split():
            run(["docker", "rm", "-f", *ids], timeout=120)
        run(["docker", "volume", "rm", "-f", v], timeout=120)


class _SystemWrites:
    """What the disk's watch is told by an execution in containers: the system's own writes into its nodes'
    directories (`DiskLedger`), its removals among them."""

    def system_writes(self, path: str, removing: bool = False):
        """`ExecutionPort.system_writes`: the writable root `path` stands in, marked in its project's volume."""
        try:
            root = _writable_root(_real(path), self)
        except ValueError:
            return contextlib.nullcontext()      # …no node's directory: nothing of it is counted against a node
        return self.volume.writes(root, _real(path), removing)

    def system_made(self, path: str) -> None:
        """The system has just made the directory `path`, empty: a writable root's baseline without reading it. Inside
        a root with no baseline, that root is read as it stands: what it holds may be older than this server."""
        with contextlib.suppress(ValueError):
            root = _writable_root(p := _real(path), self)
            if root == p:
                _LEDGER.made(self.volume.key(root))
            elif self.volume.key(root) not in _LEDGER.base:
                with self.volume.writes(root, p):
                    pass

    def remove_tree(self, path: str) -> None:
        """`ExecutionPort.remove_tree`, what the system had put there coming off its account."""
        with self.system_writes(path, removing=True):
            self._remove_tree(path)


def _run_and_admit(ex) -> None:
    """The container of `ex` running, its volumes asked again, and known to what watches it, before any agent's code runs."""
    if (got := run(ex.run_args(), timeout=120, text=True)).returncode:
        if down := ex.storage_down(got.stderr):     # …a new directory failing to mount (case 15)
            raise PlaceUnavailable(ex.name, down)
        raise subprocess.CalledProcessError(got.returncode, "docker run", got.stdout, got.stderr)
    ex.volume.require(ex.run_args())                 # …again: one made by Docker between the asking and the run
    if not ON_START and not network_record_off():    # …a list left empty admitted anything: `gfso run`, a reload worker (critic)
        raise PlaceUnavailable(ex.name, "nothing here keeps the record of where its sessions reach: nothing runs off it")
    _note_files(ex)
    if not _DISK_WATCH.is_set() and not _NO_WATCH_SAID.is_set():
        _NO_WATCH_SAID.set()
        log.warning("no server watches this work: no bound on what it writes to Docker's disk, no record of what it changed")
    for admit in ON_START:
        admit(ex)


class ContainerExecution(_SystemWrites, ExecutionPort):
    python = "python3"
    #: does a session's CLI run here, its state mounted? Not in the project's container: every session runs in its
    #: place's (`session`), and the project's runs the plan's probes, written by agents — with the state mounted they
    #: read every place's conversations under it (critic over the CLI state per place)
    holds_sessions = False
    #: a session container started with no model client's state (`PlaceContainer.client`)
    bare = False
    apart = True

    """`image` with an optional `env_file` (settings of the image, never a credential: the provider gives its own to its
    process, `_exec_argv`) and a host `state` dir (the mirrors of its door's and gateway's logs), holding the
    directories of THIS project beside `base`, at `/gfso-place/<path under base's parent>`: the base and the project's
    own directory beside it — its node places, every validation's rounds, its temp (`.gfso-tmp`), its system copies
    (`.gfso-sys`), its sessions' CLI state (`.gfso-state`) — both the project's Docker volume (`volume`), on no host
    file system: the base a clone of the user's repository imported for the project's root (`Volume.import_base`), its
    accepted result landed back there as a branch at the root's PASS (`land_accepted`) — so two projects on one base
    hold none of each other's and no host file sharing stands between a session and its files. `base`'s parent is any
    absolute directory, a POSIX one or a Windows drive's; a network share is refused as it was when the base was
    bind-mounted (nothing mounts it now: lifting that is a check of the paths' mapping over a share, not made). Nothing else of the host is mounted, the host's network is shut at start, and the rest of the way out is as
    `network` switches it (`{"mode": one of NETWORK, "hosts": [...]}`: the container's switch, kept by its name; open
    where none was given)."""

    def __init__(self, name: str, image: str, env_file: str | None, state: str, base: str, project: str,
                 network=None):
        self.base = _real(base)
        self.parent = self.base.parent
        if self.parent.drive.startswith("\\\\"):
            raise ValueError(f"execution {name!r}: {base} is on a network share — a container cannot mount it")
        if env_file and (held := sorted(k for k in _env_names(env_file) if SECRET_ENV.search(k))):
            # …a second place for a credential, live in every call the system itself makes inside — its probes, git, a
            # pinned `make test` running the executor's scripts: the token reached them all (critic over S4)
            raise ValueError(f"execution {name!r}: its env_file holds {', '.join(held)} — a credential is its "
                             f"provider's, set by `gfso credential <provider>`, never the container's")
        self.name, self.image, self.env_file = name, image, env_file
        # …and this installation's: by name alone a second one removed a first's running container and its network
        self.container = f"{container_name(name, project)}-{_home()}"
        b, self.project_name = self.base.name, component(project or DEFAULT_PROJECT)
        self.way = WayOut(self.container, name, image, Path(state), self.project_name)
        # …one per container, whichever object of it asks: two roles' objects kept a door each, and a switch one turned
        # left the other's standing in the old shape (critic over the door v2)
        self.gate = _GATES.setdefault(self.container, Door(self.way))
        self.files = ContainerFiles(self)
        if network is not None:
            self.switch(network)
        self.mounts = [b, f"{nodes_dir(b)}/{self.project_name}"]
        self.own = self.parent / self.mounts[1]
        self.volume = Volume(container_name(name, project), name, self.own, self.base, self.project_name, image)
        # dotted, as no node's key is (`component`): the system's own among the project's places — the copies and
        # checks no session but the one handed a copy reaches; THE CLI'S STATE THE PROJECT'S, each place's under it
        # (`PlaceContainer`): shared by an execution's projects, every E3 row (all at /gfso-place/ws) read and appended
        # to another row's conversation (critic over d5c8f7a, measured on two containers)
        self.tmp, self.sys, self.state = self.own / ".gfso-tmp", self.own / ".gfso-sys", self.own / STATE_DIR
        self._host = _host_paths((self.parent, type(self.base)(base).parent), self.mounts)

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
        root = self.parent.as_posix().rstrip("/")           # …a root's or a drive's parent: `/a`, not `//a`
        return re.sub(re.escape(INSIDE) + r"(?![\w.-])",
                      lambda m: root if m.string.startswith("/", m.end()) else self.parent.as_posix(), text)

    def _inside_cwd(self, cwd: str) -> str:
        """The container's path of a place the call runs in — inside what it mounts, else refused: the agent would
        stand where nothing of the project is, or the call would reach outside what the container holds."""
        here = _real(cwd)
        if not any(here.is_relative_to(src) for src, _ in self._mounts()):
            raise ValueError(f"{cwd} is not inside {self.container}'s mounts ({', '.join(self.mounts)} of {self.parent})")
        return INSIDE + "/" + here.relative_to(self.parent).as_posix()

    def run_args(self) -> list[str]:
        """`docker run` for this project's container: sealed (`--init`, its own mounts only, no new privileges, its way
        out as switched), bounded in memory and processes (`container_limits`), sleeping until the server calls into
        it."""
        mounts = [a for src, ro in self._mounts() for a in self._mount(src, ro)]
        return ["docker", "run", "-d", "--init", "--name", self.container, *labelled(self.name, self.project_name),
                *self._labels(), *self.way.run_args(),
                *([] if self.holds_sessions else [a for c in SYSTEM_CAPS for a in ("--cap-add", c)]),
                "--security-opt", "no-new-privileges", *container_limits(), *ceiling(),
                *(["--env-file", self.env_file] if self.env_file else []), *mounts,
                *(self._mount(self.state, False) + self._mount(self.state, False, STATE_INSIDE)
                  if self.holds_sessions and self.state and not self.bare else []),
                "--add-host", "host.docker.internal:0.0.0.0", self.image, "sleep", "infinity"]

    def _labels(self) -> list[str]:
        return [*grouped(self.way.container, "system"), "--label", f"{ROLE}=system"]

    def _mounts(self) -> list:
        """(directory, read-only?) for each directory the container holds: the base and the project's own, both writable."""
        return [(self.parent / m, False) for m in self.mounts]

    def _mount(self, src: Path, ro: bool, dst: str | None = None) -> list[str]:
        """`--mount` of one directory at `dst`, else where the system's name of it maps inside (`Volume.mount`)."""
        return self.volume.mount(src, ro, dst or self.to_inside(str(src)))

    def session(self, cwd: str, agent: str | None = None) -> "ExecutionPort":
        """The container of the place a session works in (`PlaceContainer`): it writes there alone, reads the base,
        and never sees another node's place. `agent`: who works there, labelled on it where it starts by this call."""
        try:
            rw = _writable_root(_real(cwd), self)
        except ValueError:
            return self        # refused where the call starts, after the place's own health — a dead place stops first
        with _START:
            s = _SESSIONS.setdefault((self.container, os.path.normcase(rw)), PlaceContainer(self, rw, agent))
            for c in (s, s.paired or s):     # …the record's word, whoever started the container first (a system's git)
                c.agent = agent or c.agent
            return s

    def start(self) -> None:
        """The project's container, running and sealed — started once per server process, whoever asks first — on its
        volume as the project left it (`Volume.bring_in`)."""
        _volume_ready(self)
        with _START:
            if _STARTED.get(self.container) == (self.run_args(), self.way.network) and self._running():
                return
            if why := self.unavailable():
                raise PlaceUnavailable(self.name, why)
            lay_ceiling()
            self.stop()                                                  # what a server that is gone left
            try:
                self.volume.require(self.run_args())              # …before Docker makes a missing one, empty
                self._open_the_way()
                _run_and_admit(self)
            except PlaceUnavailable:
                self.stop()
                raise
            except (OSError, LookupError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                self.stop()
                raise RuntimeError(f"{self.container}: {e} — no call runs unsealed") from e
            seal = run(["docker", "exec", "-u", "0", *SYS, self.container, "/bin/sh", "-c",       # uid 0: the rule is root's
                        f"{self.way.seal()} && mkdir -p /tmp/gfso-calls && chmod 1777 /tmp/gfso-calls"], timeout=60)
            if seal.returncode != 0:
                self.stop()
                raise RuntimeError(f"{self.container}: the network could not be switched — no call runs unsealed "
                                   f"({(seal.stderr or b'').decode(errors='replace')[-300:]})")
            _STARTED[self.container] = (self.run_args(), self.way.network)

    def _open_the_way(self) -> None:
        self.way.open()

    def stop(self) -> None:
        """The project's container, its sessions' and its way out — every container of its stack, one an earlier server
        started too; its volumes kept, where its work stands, and its next call makes them again over them."""
        for s in filter(None, [_SESSIONS.pop(k, None) for k in _SESSIONS.copy() if k[0] == self.container]):
            s.stop()
        run(["docker", "rm", "-f", self.container], timeout=60)
        self.gate.close()                                 # …first: a network with a member is not removed
        self.way.close()
        _STARTED.pop(self.container, None)
        # …and what is left of its stack after the doors' and the way's logs are kept (`_mirror`)
        if ids := (run(["docker", "ps", "-aq", "--filter", f"label={grouped(self.way.container, '')[1]}", "--filter",
                        f"label={HOME}={_home()}"], timeout=60, text=True).stdout or "").split():
            run(["docker", "rm", "-f", *ids], timeout=120)

    def _running(self) -> bool:
        """Is the container still up — and its allowlist's gateway, whose death would leave the project hanging on
        proxy errors with no cause said? A Docker restart (the host slept, an update) removes them under a live server,
        and every later call of the project then failed `No such container` (critic over d5c8f7a)."""
        return all(map(_up, [self.container] + ([self.way.gateway] if self.way.network[0] == "allowlist" else [])))

    def unavailable(self, storage: bool = False):
        return _unavailable(self, storage)

    #: dispatched work refused over a base that has no places (`_no_places`)
    agents_refused = lambda self: _no_places(self.base)  # noqa: E731

    def storage_down(self, why: str):
        """`why` an I/O error AND the system's own probe of the storage failing: a place down — never the words alone,
        which a session's output or a link of its own to `/proc/self/mem` can print."""
        return _STORAGE.search(why or "") and self.unavailable(storage=True)

    def which(self, program: str):
        return program                         # resolved on the container's PATH when the call starts

    def _exec_argv(self, args, env, cwd, call: str, root: bool = False, start: bool = True) -> tuple[list[str], dict]:
        """`docker exec` of one call, and the environment of the `docker` client that runs it. What the call itself sets
        goes in, not the host's environment — its PATH is the container's own; a credential by its NAME alone, its value
        in the client's environment, so no process list on the host shows it (`docker exec -e NAME`) — given to this
        call's process only, never to the container (S4: the provider's credential, one process). `start` False: the
        caller has the container running (`ContainerFiles`)."""
        if start:
            self.start()
        here = host_env()
        # …a credential even when the host holds the same value: the container has no other way to it
        own = {k: v for k, v in (env or {}).items()
               if here.get(k) != v or k.startswith("ANTHROPIC_") or SECRET_ENV.search(k)}
        secret = {k: v for k, v in own.items() if SECRET_ENV.search(k)}
        return (["docker", "exec", "-i", *(["-u", "0"] if root else []), "-w", self._inside_cwd(cwd), "-e", f"GFSO_CALL={call}",
                 *[a for k, v in own.items() for a in ("-e", k if k in secret else f"{k}={self.to_inside(v)}")],
                 self.container, "/bin/sh", "-c",
                 f'export {WORK_PATH}="$PATH" PATH={SYSTEM_PATH}:$PATH; echo $$ >/tmp/gfso-calls/{call}; exec "$@"', "sh",
                 *map(self.to_inside, args)], {**here, **secret})

    def popen(self, args, *, env, cwd, **pipes):
        call = uuid.uuid4().hex
        argv, client = self._exec_argv(args, env, cwd, call)
        return _Call(LocalExecution().popen(argv, env=client, cwd=str(self.parent), **pipes), self, call)

    def run(self, args, *, cwd, timeout, env=None, root: bool = False):
        call = uuid.uuid4().hex
        argv, client = self._exec_argv(args, env, cwd, call, root)
        try:
            done = run_printing(argv, timeout=timeout, cwd=str(self.parent), env=client)
        except subprocess.TimeoutExpired:
            self._end_inside(call)
            raise
        if done.returncode and (down := self.storage_down(done.stderr)):
            raise PlaceUnavailable(self.name, down)
        return subprocess.CompletedProcess(args, done.returncode, self.to_outside(done.stdout or ""),
                                           self.to_outside(done.stderr or ""))

    def shell(self):
        return "bash"

    def bytes_call(self, args, *, cwd, input: bytes | None = None, root: bool = False) -> subprocess.CompletedProcess:
        """`args` to its end here as the image's user — or root —, bytes in and out as they are — a file's, never a path
        to map; the container started only where this process has not started it, no `docker inspect` per call
        (`ContainerFiles`, which starts it again where it went)."""
        if self.container not in _STARTED:
            self.start()
        call = uuid.uuid4().hex
        argv, client = self._exec_argv(args, None, cwd, call, root, start=False)
        try:
            return run(argv, timeout=600, cwd=str(self.parent), env=client, input=input)
        except subprocess.TimeoutExpired:
            self._end_inside(call)
            raise

    def copy_tree(self, src: str, dst: str) -> None:
        # inside, as the place was made: a symlink a session made in here is no link on the host (probe P5)
        # …by root, in the project's container (`SYSTEM_CAPS`): as the agent, one unreadable file the executor left in
        # its place failed every copy and kept its delivery from being judged (critic over the judges slice) — and only
        # where nothing stands: into a directory or a link left there, `cp -a` copies INTO it (critic 3) — made fresh
        # by the same call that copies, so nothing can stand there between a look and the copy
        r = self.run(["sh", "-c", 'mkdir -- "$2" || exit 3; cp -a -- "$1/." "$2/"', "sh", src, dst], cwd=src,
                     timeout=1800, root=True)
        if r.returncode == 3:
            raise OSError(f"{dst} already exists or cannot be made: a copy is made only where nothing stands "
                          f"({r.stderr.strip()[-200:]})")
        if r.returncode != 0:
            raise OSError(f"cp -a {src} {dst} failed in {self.container}: {r.stderr.strip()[-300:]}")

    def _remove_tree(self, path: str) -> None:
        # a place going takes its session's container with it, and its CLI's state: nothing will resume there — the
        # system's removal is what ends a session, not a directory found gone (a round's, a contact's, a no-place call's)
        # …over a copy, popped with a default: every thread of the server starts sessions into the one table, and a
        # removal iterating it live died "dictionary changed size during iteration" 140 times in one row (engineering)
        for s in filter(None, [_SESSIONS.pop(k, None) for k in _SESSIONS.copy() if k[0] == self.way.container
                               and Path(k[1]).is_relative_to(_real(path))]):   # …the project's, a session's too
            s.stop()
            if s.state:
                with contextlib.suppress(OSError):
                    s.project.remove_tree(str(s.state))
        if not self.files.exists(path):
            return
        at = self.session(str(self.own / STATE_DIR)) if Path(path).is_relative_to(self.own / STATE_DIR) else self
        # …by root in the project's: what the system laid as its own (`ContainerFiles.seal_files`) no agent's uid removes
        r = at.run(["sh", "-c", 'chmod -R u+rwX -- "$1" 2>/dev/null; rm -rf -- "$1"', "sh", path],
                   cwd=str(Path(path).parent), timeout=600, root=at is self and not self.holds_sessions)
        if r.returncode != 0:
            raise OSError(f"rm -rf {path} failed in {self.container}: {r.stderr.strip()[-300:]}")

    def end(self, proc) -> None:
        """The call's group inside, and whatever it started that left the group (`setsid`), found by its mark — killing
        the `docker exec` client alone leaves them all running (probe P1)."""
        if isinstance(proc, _Call) and proc.execution is not self:
            return proc.execution.end(proc)               # in the container the call ran in, a session's own
        if isinstance(proc, _Call):
            try:
                self._end_inside(proc.call)
            finally:      # …a Docker slow to answer left the client standing and whoever reads it waiting: 24 min of `plan`
                LocalExecution().end(proc.client)
            return
        LocalExecution().end(proc)

    def _end_inside(self, call: str) -> None:
        run(["docker", "exec", *SYS, self.container, "/bin/sh", "-c", _ending(call)], timeout=60)

    def temp_root(self):
        return str(self.tmp)            # …a name: made where it is written, in the volume (`FilesPort.mkdtemp`)

    def temp_of(self, place) -> str:
        """The temp of the writable root `place` stands in (`_writable_root`): a node's place's, its executor's alone;
        a judge's round or batch, and a directory of the system's, each one of its own — a judge shared its node's, and a
        delivered link into it read what the executor wrote there after DELIVER (critic over the judged tree). A path
        outside the project's places: the temp itself."""
        try:
            owner = _writable_root(_real(place), self) if place else None
        except ValueError:
            owner = None
        if owner is None:
            return self.temp_root()
        # …a directory of the temp lent to one call is its own temp, and one of the system's: gone with it, where what a
        # check left in a temp of its own stood through every later one, on no bound (critic)
        if owner.is_relative_to(self.tmp) or owner.parent == self.sys:
            return str(owner)
        d = self.tmp / f"node-{hashlib.sha1(os.path.normcase(owner).encode()).hexdigest()[:12]}"
        _TEMPS[os.path.normcase(d)] = owner        # …whose session's container mounts it, made at its start (`ContainerFiles`)
        return str(d)

    def _scratch_root(self, system: bool) -> str:
        return str(self.sys) if system else self.temp_root()

    def state_dir(self):
        return self.state

    def state_seen(self) -> str:
        return STATE_INSIDE


#: the most of a directory the server reads into its memory
TREE_CAP = 64 << 20


class ContainerFiles(FilesPort):
    """The files of a project's places (`ContainerExecution.files`), each operation one `docker exec` as the image's
    user, never root — IN THE CONTAINER THE SYSTEM'S OWN RECORD OF THE PATH NAMES (`_writable_root`, a name the system
    chose, never what stands there): a path inside a place runs in that place's own session container, whose mounts
    are the bound — a link an agent made out of its place leads nowhere there, whenever it is made; a place's root and
    what stands above it, which only the system writes, in the project's."""

    def __init__(self, ex: "ContainerExecution"):
        self.ex = ex

    def _where(self, path: str) -> tuple:
        """(container, its working directory) a file operation over `path` runs in — None for the container where the
        place `path` lies inside is not there: nothing of it can be read, nor written."""
        p = Path(os.path.abspath(path))
        try:
            rw = _writable_root(p, self.ex)
        except ValueError:
            self.ex.start()                 # …a dead place stops first: refused for its own health, then for the path
            raise
        if rw == (st := self.ex.state) or rw.parent == st:
            # …the CLI state: its keeper's, never the project's — nor a place's own container, which mounts none of it
            # (`PlaceContainer.client`)
            return self.ex.session(str(st)), str(st)
        if p == rw:
            return self.ex, str(self.ex.base)
        rw = _served(rw, self.ex)
        s = _SESSIONS.get((self.ex.container, os.path.normcase(rw)))
        if (s is None or s.container not in _STARTED) and self._run(self.ex, str(self.ex.base), "is_dir", str(rw)).returncode:
            return None, None
        return self.ex.session(str(rw)), str(rw)

    def _run(self, at, cwd: str, op: str, *args: str, data: bytes | None = None,
             root: bool = False) -> subprocess.CompletedProcess:
        """One operation in `at`: started where it is not, and once more where it is gone under a live server (a Docker
        restart) — no `docker inspect` per operation. A failure of the exec itself is no "not there": the daemon down
        raises `PlaceUnavailable`, any other `OSError`."""
        for again in (False, True):
            done = at.bytes_call(["sh", "-c", _FILE_OPS[op], "sh", *args], cwd=cwd, input=data, root=root)
            why = (done.stderr or b"").decode(errors="replace").strip()
            if done.returncode and _GONE.search(why) and not again:
                _STARTED.pop(at.container, None)
                continue
            if done.returncode and (_DOWN.search(why) or (down := self.ex.storage_down(why))):
                raise PlaceUnavailable(at.name, why if _DOWN.search(why) else down)
            if done.returncode >= 125 or (done.returncode and _GONE.search(why)):
                raise OSError(f"{op} {args[0]} did not run in {at.container} (exit {done.returncode}): {why[-300:]}")
            return done

    def _file(self, op: str, path: str, *more: str, data: bytes | None = None):
        """The operation's run, or None where the place it lies inside is not there."""
        at, cwd = self._where(path)
        return None if at is None else self._run(at, cwd, op, path, *more, data=data)

    def _wrote(self, r, path: str) -> None:
        if r is None or r.returncode:
            raise OSError(f"{path} could not be written in {self.ex.container}"
                          + (f": {(r.stderr or b'').decode(errors='replace').strip()[-300:]}" if r else ": no such place"))

    def exists(self, path: str) -> bool:
        return (r := self._file("exists", path)) is not None and r.returncode == 0

    def is_dir(self, path: str) -> bool:
        return (r := self._file("is_dir", path)) is not None and r.returncode == 0

    def listdir(self, path: str) -> list[str]:
        r = self._file("listdir", path)
        return [n for n in r.stdout.decode("utf-8", errors="replace").split("\0") if n] if r and not r.returncode else []

    def read_bytes(self, path: str, size: int | None = None) -> bytes | None:
        r = self._file("read_bytes", path, "" if size is None else str(size))
        return r.stdout if r is not None and r.returncode == 0 else None

    def write_bytes(self, path: str, data: bytes) -> None:
        self._wrote(self._file("write_bytes", path, data=data), path)

    def mkdir(self, path: str) -> None:
        self._wrote(self._file("mkdir", path), path)

    def write_files(self, base: str, files: dict) -> None:
        """One `tar -x` inside, the files fed through its stdin."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as t:
            for rel, data in files.items():
                (i := tarfile.TarInfo(rel)).size = len(data)
                t.addfile(i, io.BytesIO(data))
        self._wrote(self._file("write_files", base, data=buf.getvalue()), base)

    def seal_files(self, base: str, files: dict) -> None:
        """As root, in the project's container (`SYSTEM_CAPS`): the files root's 0444, and every directory from the
        writable root a session there mounts down to `base` root's 1777 (`_FILE_OPS`). Root's files under one directory
        an agent owned were nothing: it renamed that directory away and laid a forged one in its place — a sticky one's
        own owner too (probe, image f400b818). The base of a project's root is never made the system's: its agent works
        there, and nothing is laid in it."""
        b = Path(os.path.abspath(base))
        rw = _writable_root(b, self.ex)
        chain = [*([] if rw == self.ex.base else [rw]), *reversed([p for p in b.parents if p.is_relative_to(rw)
                                                                   and p != rw]), b]
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as t:
            for rel, data in files.items():
                (i := tarfile.TarInfo(rel)).size, i.mode = len(data), 0o444
                t.addfile(i, io.BytesIO(data))
        self._wrote(self._run(self.ex, str(rw), "seal_files", str(b), *map(str, chain), data=buf.getvalue(),
                              root=True), base)

    def read_tree(self, path: str) -> dict | None:
        """One `tar -c` inside, its regular files read out of the stream; None past `TREE_CAP`: a directory an agent filled
        stood whole in the server's memory, every project's with it."""
        if ((r := self._file("read_tree", path, str(TREE_CAP + 1))) is None or r.returncode or len(r.stdout) > TREE_CAP
                or b"gfso-tar-failed" in (r.stderr or b"")):      # …a directory with an unreadable file is not read whole
            return None
        with tarfile.open(fileobj=io.BytesIO(r.stdout)) as t:
            return {m.name.removeprefix("./"): t.extractfile(m).read() for m in t.getmembers() if m.isreg()}

    def subdirs(self, path: str, depth: int) -> list[str]:
        r = self._file("subdirs", path, str(depth))
        return [n for n in r.stdout.decode("utf-8", errors="replace").split("\0") if n] if r and not r.returncode else []

    def remove_matching(self, path: str, patterns: list) -> None:
        self._wrote(self._file("remove_matching", path, *patterns), path)

    def holds(self, path: str) -> bool:
        try:
            return bool(_writable_root(Path(os.path.abspath(path)), self.ex))
        except ValueError:
            return False

    def old_layout(self) -> tuple:
        return tuple(self.ex.parent / f".gfso-{k}-{self.ex.base.name}" for k in ("scratch", "tmp", "sys"))


def _volume_ready(ex) -> None:
    """The volume of `ex`'s project made, or found as the project left it, before its container first starts in this
    process — under the project's own lock, never the start's: a copy-in may take minutes."""
    p = ex.project if isinstance(ex, PlaceContainer) else ex          # …a session's: its project's
    with _VOLUMES.setdefault(p.container, threading.Lock()):
        if p.container in _STARTED:
            return
        if why := p.unavailable():
            raise PlaceUnavailable(p.name, why)
        try:
            p.volume.ready(p.image, p.own, p.way.home / p.container, *_left(p))
        except PlaceUnavailable:
            raise
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            raise RuntimeError(f"{p.container}: {e} — no call runs on a volume half made") from e


def _left(ex) -> tuple:
    """What the host's leftover of the project's directory holds: ({a place's key in the per-project CLI state of
    before the volume: its name in `.gfso-state`} for the base and every place there, [each place and round there])."""
    rels = [(d.name, *([x.name] if d.name.startswith(".") else [])) for d in
            (ex.own.iterdir() if ex.own.is_dir() else ()) if d.is_dir()
            for x in (d.iterdir() if d.name.startswith(".") else [d]) if x.is_dir()]
    return ({hashlib.sha1(os.path.normcase(ex.own.joinpath(*r) if r else ex.base).encode()).hexdigest()[:12]:
             "+" + "+".join(r) for r in [(), *rels]}, [ex.own.joinpath(*r) for r in rels])


def _writable_root(cwd: Path, project: "ContainerExecution") -> Path:
    """What a session working in `cwd` may write — read off the system's names at fixed depths, never off what stands
    there: the base whole, for a root; in the project's own directory (`.gfso-nodes-<base>/<project>`) a node's clone,
    or one entry of a dotted directory, the system's (no key starts with a dot): a round of the scratch it stands in
    (`scratch_of`/<round>, an issuer's contact whole) — one batch of it, where it stands in one (`<round>/batch<N>`:
    a process one batch's validator left behind reaches no other's copy) —, a temp of its own, a copy."""
    rel = cwd.relative_to(project.parent).parts if cwd.is_relative_to(project.parent) else ()
    if rel[:1] == (project.mounts[0],):
        return project.base
    if rel[:2] != Path(project.mounts[1]).parts:
        raise ValueError(f"{cwd} is not inside {project.container}'s mounts ({', '.join(project.mounts)})")
    dotted = len(rel) > 2 and rel[2].startswith(".")
    batch = dotted and rel[2].startswith(SCRATCH) and len(rel) > 4 and rel[4].startswith(BATCH)
    return project.parent.joinpath(*rel[:3 + dotted + batch])


def _scratch_above(rw: Path) -> "Path | None":
    """The scratch whose round — or a round's batch — the writable root `rw` is; None for any other root."""
    return next((p for p in (rw.parent, rw.parent.parent) if p.name.startswith(SCRATCH)), None)


def _served(rw: Path, project: "ContainerExecution") -> Path:
    """The place whose session's container mounts the writable root `rw`: a node's temp its node's (`temp_of`); a
    place's CLI state its place's, read off its name (`PlaceContainer.state`), so a restarted server finds it too; else
    itself."""
    if rw.parent == project.state:
        return project.base if rw.name == "+" else project.own.joinpath(*rw.name[1:].split("+"))
    return _TEMPS.get(os.path.normcase(rw), rw)


def _kind_of(rel: tuple, systems: tuple) -> tuple:
    """(role, node, the rest) of a place by its path in the project's directory (`_writable_root`), the base's ():
    the base and a node's clone its executor's, a validation's or a contact's round a validator's, a directory the system
    lends a call (`systems`) a check's."""
    if not rel:
        return "executor", ROOT_ID, ()
    if rel == (STATE_DIR,):
        return "system", "state", ()
    if rel[0].startswith(SCRATCH):
        return "validator", ROOT_ID if rel[0][len(SCRATCH):].startswith(".") else rel[0][len(SCRATCH):], rel[1:]
    return ("check", rel[-1], ()) if rel[0] in systems else ("executor", rel[0], ())


class _ClientFiles(ContainerFiles):
    """A model's file tools where its provider runs them itself: in the place's client container, as a client's own run —
    no system's call there for a link they follow to reach, and the base as the session reads it, the copy."""

    def _where(self, path: str) -> tuple:
        c = self.ex.client()
        return c, str(c.rw)


class PlaceContainer(ContainerExecution):
    """One session's container: its place writable (`rw`), the base read-only — a node's clone borrows the base's
    objects, and nothing it does reaches the base's refs — nothing of another node's place nor of the system's own
    checks. Its way out is its project's; the system's own commands stay in the project's container. Started on its
    session's first call, gone with its directory, its place or its project. Its temp is its place's own (`temp_of`):
    what the system lays for the node's sessions, no other node's reads — save that whatever works in the base shares
    the base's: every node with no git base, and the reader of the places a plan is made from. Its
    CLI's state is its place's own, under its project's. No judge shares a place with its executor: a validation and an
    issuer's contact, a root's included, work each in a round of their own, on a checkout of the delivery — a
    validation's batches each in a batch of its own —, mounting that and a temp of their own alone (`_mounts`), and a
    delivery that could not be checked out is not judged (`apart`). The base's CLI state is its root executor's alone:
    a parent consents in its own place, the plan's place reader works in a temp of its own, a base that is no git
    repository is refused. NOT HELD YET: a tool-loop provider's issuer reads a node's inputs by its shell only. A judge's
    container ends with its run (`ExecutionPort.release`), and again with its node if a read of its round started it since; a
    node's when it passed and joined or was cancelled (`delegate.Dispatcher._released`)."""
    commands_apart = True

    def __init__(self, project: ContainerExecution, rw: Path, agent: str | None = None):
        self.__dict__.update(project.__dict__)
        self.project, self.rw, self.agent = project, rw, agent
        rel = () if rw == self.base else rw.relative_to(self.own).parts
        # named as the system names the place — its role, its node, its round — the hash keeping two spellings apart
        self.role, self.node, sub = _kind_of(rel, (self.tmp.name, self.sys.name))
        # …and nothing of its project's name: the project's group names that once (the author, 2026-10-29: «почему имена
        # контейнеров все еще дурацкие») — the role first, so a group lists who acts together; the hash, over the project
        # too, keeps every name on the machine apart
        key = _short(project.container, os.path.normcase(rw))
        self.container = re.sub(r"[^a-zA-Z0-9_.-]+", "-", ".".join((self.role, self.node, *sub))) + f"-{key}"
        # the CLI's state of THIS place, under its project's, named by the place — mounted here alone: the others'
        # conversations, the system's notes on them and the CLI's own memory of another place are in no session's reach
        self.state = None if rw == project.state else project.state / ("+" + "+".join(rel))
        self.holds_sessions = True
        #: the system's container of the place mounts no model client's state; its client's does (`client`)
        self.bare, self.paired, self.system = True, None, self
        self.commands = Commands(self)
        #: the model clients' calls running in this place now — its commands are ended whole when the last one ends
        self.clients: set = set()

    def client(self) -> "PlaceContainer":
        """The container the place's model clients run in — the place's mounts and its CLI state, and no git: the
        repository's own configuration (a clean filter its agent or a delivered build wrote) ran in the client's
        `git status` and in the system's git beside the client and its state, and forged a judge's PASS (critic, live).
        Everything the system runs over the place — its git, a build — runs in the place's own container, which mounts
        no state; the client's commands run in their own (`Commands`)."""
        if self.paired is None:
            c = copy.copy(self)
            c.container, c.bare, c.clients, c.paired = self.container + "-client", False, set(), c
            c.commands = Commands(c)
            self.paired = c
        return self.paired

    def _labels(self) -> list[str]:
        """Its project's stack, subgrouped by role (`grouped`); who works here, which node, as what."""
        return [*grouped(self.way.container, self.role + "s"), "--label", f"{ROLE}={self.role}",
                "--label", f"{NODE}={self.node}", *(["--label", f"{AGENT}={self.agent}"] if self.agent else [])]

    def _mounts(self) -> list:
        """(directory, read-only?) for each directory the container holds. A judge's round or batch writable with a
        temp of its own, and what the system laid for it from its record read-only beside it (`laid_beside`): a standing
        finding's files — never an earlier round, whose files the delivered code run there could rewrite after its
        judge ran them, and whose container outlived its run (critic over the judged tree: a forged `../probe.sh`
        re-run, rc 0); a directory of the system's checks, writable with a temp of its own and what was laid beside it read-only. Nothing else: no base, no
        node's temp, no place, no other round or batch. A judge runs the delivered tree it was handed, and anything more
        it mounts is a way for that tree to read what the executor holds now — a delivered link into the node's temp, a
        root's base (the root's executor's live place), a sibling batch's copy (critic over the judged tree). A temp of
        the system's: the base read-only and itself. A place writable, the base read-only, its validations' scratch
        read-only, its temp writable."""
        tmp, own_temp = self.tmp, (Path(self.temp_root()), False)
        if self.state is None:
            return [(self.rw, False)]                    # the keeper of the CLI state: it alone, nothing of a place
        laid = [] if self.rw.name.endswith(LAID) else [(self.rw.with_name(self.rw.name + LAID), True)]
        if _scratch_above(self.rw) or self.rw.is_relative_to(self.sys):
            return [(self.rw, False), *laid, *([own_temp] if own_temp[0] != self.rw else [])]
        if self.rw.is_relative_to(tmp):
            return [*([] if self.rw == self.base else [(self.base, True)]), (self.rw, False)]
        # its validations' scratch read-only beside its place, a root's base as a node's clone: its rounds hold the
        # probes the node's standing findings re-run, which the node's own executor must not rewrite (critic 3 over the
        # session slice); no judge works here (`apart`)
        own = [(self.rw, False), (scratch_of(self.rw, self.project_name), True)]
        return [*([] if self.rw == self.base else [(self.base, True)]), *own, (Path(self.temp_root()), False)]

    def writable(self) -> set:
        """The directories its sessions write that outlive them: what it mounts writable, and its CLI state."""
        return {d for d, ro in self._mounts() if not ro} | ({self.state} if self.state else set())

    def temp_root(self):
        """Its node's own temp (`ContainerExecution.temp_of`), not the project's."""
        return self.project.temp_of(str(self.rw))

    def session(self, cwd: str, agent: str | None = None) -> "ExecutionPort":
        return self if _real(cwd).is_relative_to(self.rw) else self.project.session(cwd, agent)

    def door(self, credential, upstream: str):
        """Its project's door (`Door`), once the project's network stands."""
        _volume_ready(self)                          # …before the start's lock is taken
        with _START:
            self.project.start()
            return self.gate.url(credential, upstream)

    def commands_env(self) -> dict:
        """Its commands' container started (`Commands`), and the CLI pointed at it; a CLI that runs a bash of its own
        beside itself refused there (`shell.GUARD`)."""
        _volume_ready(self)
        with _START:
            self.start()
            try:
                self.commands.start([*self._labels(), *[a for src, ro in self._mounts() for a in self._mount(src, ro)]])
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                self.commands.close()
                raise PlaceUnavailable(self.name, f"its commands' container did not start ({e})") from e
        return {"CLAUDE_CODE_SHELL": shell.CLIENT, "BASH_ENV": shell.BESIDE}

    def commands_of(self, proc) -> list:
        return [r for r in self.commands.record() if r.get("run") == proc.call]

    def command(self, command: str, *, cwd: str, timeout: float, env=None):
        """Through the system's shell in the place's client container, as a client's commands come (`Commands`): in the
        place's own container it ran beside the system's git, in reach of what that prints, and on no record."""
        c = self.client()
        c.commands_env()
        return c.run([shell.CLIENT, "-c", command], cwd=cwd, timeout=timeout, env=env)

    @property
    def tool_files(self):
        return _ClientFiles(self)

    def commands_ended(self) -> None:
        c = self.client()
        with contextlib.suppress(subprocess.TimeoutExpired):        # …a Docker that hangs costs the place, not this run's answer
            c.commands.end(uuid.uuid4().hex, every=not c.clients)

    def popen(self, args, *, env, cwd, **pipes):
        proc = super().popen(args, env=env, cwd=cwd, **pipes)
        if "CLAUDE_CODE_SHELL" in (env or {}):            # …a model client's, its shell the system's (`commands_env`)
            self.clients.add(proc.call)
        return proc

    def _end_inside(self, call: str) -> None:
        run(["docker", "exec", *SYS, self.container, "/bin/sh", "-c", _ending(call)], timeout=60)
        last = call in self.clients and self.clients <= {call}
        self.clients.discard(call)
        self.commands.end(call, every=last)

    def _open_the_way(self) -> None:
        self.project.start()                              # the project's network and gateway stand before any session
        # …and a project started here stopped its sessions first, this one among them: it is tracked again
        _SESSIONS[(self.project.container, os.path.normcase(self.rw))] = self.system
        # a volume's subpath mounts once it stands: what the system lends it made by the project's container — its place
        # not, which the system made, or the session is refused where nothing of its place stands
        lent = [str(s) for s, _ in self._mounts() if s.is_relative_to(self.own) and s != self.rw]
        if self.state is None:
            return                                       # …the keeper's own: the state volume whole, nothing lent
        keeper = self.project.session(str(self.project.state))
        for at, cwd, wanted in ((self.project, self.base, lent), (keeper, keeper.rw, [str(self.state)])):
            if not wanted:
                continue
            # …nothing measured around it: one that stands is not written, and one made now holds nothing, its baseline
            r = at.run(["sh", "-c", 'i=0; for d; do i=$((i+1)); [ -d "$d" ] && continue; mkdir -p -- "$d" || exit 1; '
                                    'echo "$i"; done', "sh", *wanted], cwd=str(cwd), timeout=60)
            if r.returncode:
                raise OSError(f"{self.container}: its directories could not be made ({r.stderr.strip()[-300:]})")
            for i in (r.stdout or "").split():
                self.project.system_made(wanted[int(i) - 1])

    def _say_the_bound(self) -> None:
        """What the bound on new flows dropped of this session's, on its project's record as it goes: a program failing on a
        refused send read as its own failure, and a flooder that hit the bound was named nowhere (critic, ran)."""
        got = run(["docker", "exec", *SYS, "-u", "0", self.container, "/bin/sh", "-c",
                   "for c in gfso-flows gfso-udp gfso-names; do iptables -L $c -v -n -x 2>/dev/null; done"], timeout=30, text=True)
        if not got.returncode and (dropped := _flows_dropped(got.stdout)):
            append(network_record_path(self.project_name), {"at": time.time(), "container": self.container, "flows_dropped": dropped})

    def stop(self) -> None:
        """This session's container and its commands', its client's with them: the way out is its project's."""
        if self.paired not in (None, self):
            self.paired.stop()
        self._say_the_bound()
        self.commands.close()
        run(["docker", "rm", "-f", self.container], timeout=60)
        _STARTED.pop(self.container, None)


def _flows_dropped(listing: str) -> int:
    """What the seal's bounds dropped, by what `iptables -L <chain> -v -x` lists of each; 0 where it lists none."""
    return sum(int(n) for n in re.findall(r"^\s*(\d+)\s+\d+\s+DROP", listing or "", re.M))


class _Call:
    """A call inside, as the host's code reads a process: what it is fed goes in with container paths, what it prints
    comes out with host paths."""

    def __init__(self, client, execution: ContainerExecution, call: str):
        self.client, self.call, self.execution = client, call, execution
        self.stdin = _Mapped(client.stdin, execution.to_inside) if client.stdin else None
        # …a byte stream as it is, a file's or a pack's: no line of it is a path to map (`ExecutionPort.pipe`)
        self.stdout = (client.stdout if not client.text_mode else (execution.to_outside(line) for line in client.stdout)
                       ) if client.stdout else None
        self.stderr = client.stderr
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
