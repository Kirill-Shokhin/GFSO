"""Where each session reached by network, written by the system, under every switch alike (DECISION S6; SECURITY.md).

One listener for each process that starts containers, in a container of the system's own on Docker's host network, holding only the right to
read packets, and only while the installation has work: no process of a session shares anything with it, so none stops or
forges it, and it changes no traffic. The switches differ in where a session can get; this says where it went. It sees
addresses, ports and asked names, not what passed, and nothing the kernel refused before it left a container. A container's
code runs only once the listener stands and knows its address (`admit`); with neither, the project stops with the cause,
unless the installation has said it does without (`GFSO_NETWORK_RECORD=off`)."""
from __future__ import annotations

import collections
import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path

from gfso.adapters import execution as E
from gfso.adapters.execution import HOME, NODE, PROJECT, ROLE, LocalExecution, PlaceUnavailable, ceiling, component, executions, host_env, installation, run
from gfso.config import data_dir, network_record_off

log = logging.getLogger(__name__)
#: how often the watch asks which containers stand
WATCH_S = 2.0
#: a project's record turns over at this size, the last turn kept: what a session asks for fills no disk and erases no one
CAP = 16 * 2 ** 20
#: destinations listed per container: past them it is said once, and its flood takes no one else's room
BUDGET = 2000
#: seconds an ended container keeps its address here: its last flow may be read after it, and a user's container may take it
GRACE_S = 10.0
READY_S = 120.0

#: In the container, its stdin the system's pipe: gone with the server, so is it. A kernel filter passes all but a TCP flow's
#: later packets, whatever else a process can send (SCTP and UDP-Lite open with no capability), so a bulk transfer costs
#: nothing here. A socket per container's link, each read in turn: a flood fills its own buffer alone (one shared blinded
#: every project, critic, ran); a link new to Docker is opened on its kernel notice, before `docker run` returns. Each line one JSON object: a name a session asks is its own text.
_LISTEN = r"""
import ctypes, json, os, select, socket, struct, sys, time
P = [(0x28, 0, 0, 12), (0x15, 0, 6, 0x800), (0x30, 0, 0, 23), (0x15, 0, 10, 6), (0xb1, 0, 0, 14), (0x50, 0, 0, 27),
     (0x54, 0, 0, 0x12), (0x15, 6, 7, 2), (0x15, 0, 6, 0x86dd), (0x30, 0, 0, 20), (0x15, 0, 3, 6), (0x30, 0, 0, 67),
     (0x54, 0, 0, 0x12), (0x15, 0, 1, 2), (0x06, 0, 0, 512), (0x06, 0, 0, 0)]
code = ctypes.create_string_buffer(b"".join(struct.pack("HBBI", *p) for p in P))
def say(**row):
    print(json.dumps(row), flush=True)
def name(b, at):
    parts = []
    while at < len(b) and b[at] and len(parts) < 40:
        parts.append(b[at + 1:at + 1 + b[at]].decode("ascii", "replace"))
        at += b[at] + 1
    return ".".join(parts)[:253]
links, last = {}, {}
changes = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, 0)
changes.bind((0, 1))
def scan():
    for n in os.listdir("/sys/class/net"):
        if n.startswith("veth") and n not in links:
            try:
                k = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
                k.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 ** 20)
                k.setsockopt(socket.SOL_SOCKET, 26, struct.pack("HL", len(P), ctypes.addressof(code)))
                k.bind((n, 3))
                k.setblocking(False)
                links[n] = k
            except OSError:
                pass
scan()
say(ready=True)
said = time.monotonic()
def one(n, k):
    p = k.recv(600)
    if len(p) < 34:
        return
    v6 = p[12:14] == b"\x86\xdd"
    proto, hl = (p[20], 40) if v6 else (p[23], (p[14] & 15) * 4)
    src, dst = ((socket.inet_ntop(socket.AF_INET6, p[22:38]), socket.inet_ntop(socket.AF_INET6, p[38:54])) if v6 else
                (socket.inet_ntoa(p[26:30]), socket.inet_ntoa(p[30:34])))
    last[n] = src
    port = struct.unpack("!H", p[14 + hl + 2:14 + hl + 4])[0] if proto in (6, 17, 132, 136) and len(p) >= 14 + hl + 4 else 0
    asked = name(p, 14 + hl + 8 + 12) if proto == 17 and port == 53 else ""
    say(src=src, proto=proto, to=dst, port=port, asked=asked)
while True:
    ready = select.select([changes, sys.stdin, *links.values()], [], [], 10)[0]
    if sys.stdin in ready and not sys.stdin.buffer.read1(1):
        break
    if changes in ready:
        changes.recv(65536)
        scan()
    for n, k in list(links.items()):
        if k not in ready:
            continue
        try:
            for _ in range(16):      # …each link its turn: a flood on one waits while the others are read
                one(n, k)
        except BlockingIOError:
            pass
        except OSError:              # …its container gone
            k.close()
            del links[n]
    if time.monotonic() - said > 10:
        said = time.monotonic()
        for n, k in links.items():
            dropped = struct.unpack("II", k.getsockopt(263, 6, 8))[1]
            if dropped:
                say(drops=dropped, src=last.get(n))
"""
_KINDS = {6: "tcp", 17: "udp", 1: "icmp", 58: "icmp", 132: "sctp", 136: "udplite"}


class _Book:
    """Who holds which address (each container the installation made, by its labels), and each new destination on its
    project's record, once per container, up to its budget."""

    def __init__(self):
        self.holders, self.seen, self.ended = {}, {}, {}

    def learn(self, rows: str, whole: bool = False) -> None:
        """`rows`: `<name>|<project>|<node>|<role>|<address> …` a line. `whole`, all that stand: a holder not among them
        keeps its address `GRACE_S`, then has none: a user's container on a native host takes the next one freed."""
        now, standing = time.monotonic(), set()
        for row in rows.splitlines():
            parts = row.strip().lstrip("/").split("|")
            if len(parts) == 5:
                standing.add(parts[0])
                for ip in parts[4].split():
                    if (old := self.holders.get(ip)) and old["container"] != parts[0]:
                        self.seen.pop(old["container"], None)
                    self.holders[ip] = dict(zip(("container", "project", "node", "role"), parts))
        if whole:
            for ip, who in list(self.holders.items()):
                c = who["container"]
                if c in standing:
                    self.ended.pop(c, None)
                elif now - self.ended.setdefault(c, now) > GRACE_S:
                    del self.holders[ip]
                    self.seen.pop(c, None)
                    self.ended.pop(c, None)

    def heard(self, line: str, now: float) -> None:
        """One line of the listener's, a session's text perhaps inside it. A flow from no container of this installation
        is not recorded: on a Linux host another's containers, or the user's own, are none of this."""
        try:
            row = json.loads(line)
            if not (who := self.holders.get(row.get("src"))):
                return
            if drops := row.get("drops"):
                log.warning(f"the network's record lost {drops} packets of {who['container']}: its flood outran it, and what it sent then is not on the record")
                _append(who["project"], {"at": now, "container": who["container"], "lost_packets": int(drops)})
                return
            seen = self.seen.setdefault(who["container"], set())
            key = (row["proto"], row["to"], row["port"], row["asked"])
            if key in seen or len(seen) > BUDGET:
                return
            seen.add(key)
            if len(seen) > BUDGET:
                _append(who["project"], {"at": now, "container": who["container"], "cut": f"more than {BUDGET} destinations: the rest not listed"})
                return
            _append(who["project"], {"at": now, **{k: who[k] for k in ("container", "node", "role")},
                                     "kind": "dns" if row["asked"] else _KINDS.get(row["proto"], f"ip{row['proto']}"),
                                     "to": str(row["to"]), "port": int(row["port"]), **({"asked": str(row["asked"])} if row["asked"] else {})})
        except (ValueError, KeyError, TypeError, AttributeError, OSError) as e:
            log.warning(f"the network's record passed over a line it could not read ({e})")


def record_path(project: str) -> Path:
    """Where `project`'s record lies, in this installation's data, which no session mounts."""
    return data_dir() / "network" / f"{component(project)}.jsonl"


def forget(project: str) -> None:
    """A project gone: a new one of the name inherits none of its record."""
    for p in (record_path(project), record_path(project).with_suffix(".jsonl.1")):
        p.unlink(missing_ok=True)


def _append(project: str, row: dict) -> None:
    """`row` on `project`'s record, turned over past `CAP` with its last turn kept."""
    path = record_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size >= CAP:
        os.replace(path, path.with_suffix(".jsonl.1"))
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _image() -> "str | None":
    """An image of this installation's: the listener needs python, which the product's holds."""
    return next((d["image"] for d in executions().values() if d.get("image")), None)


def _work_stands() -> "list[str] | None":
    """The ids of this installation's containers; None where Docker did not say."""
    got = run(["docker", "ps", "-q", "--filter", f"label={HOME}={installation()}"], timeout=30, text=True)
    return None if got.returncode else (got.stdout or "").split()


def _holders(ids: list) -> str:
    """Rows for `_Book.learn`."""
    labels = "|".join(f'{{{{index .Config.Labels "{k}"}}}}' for k in (PROJECT, NODE, ROLE))
    got = run(["docker", "inspect", "-f", f"{{{{.Name}}}}|{labels}|{{{{range .NetworkSettings.Networks}}}}{{{{.IPAddress}}}} {{{{.GlobalIPv6Address}}}} {{{{end}}}}",
               *ids], timeout=30, text=True)
    return got.stdout or ""


def listener() -> str:
    """The listener's name: this process's own, so another process of the installation, or another installation, stands
    beside it: under one name each removed the other, and what passed between was on no record (critic, ran)."""
    return f"gfso-net-record-{installation()}-{os.getpid()}"


class _Record:
    """The listener's life, one per process that starts containers."""

    def __init__(self):
        self.book, self.proc, self.reader, self.image, self.stood = _Book(), None, None, None, False
        self.ready, self.lock = threading.Event(), threading.RLock()

    def up(self) -> None:
        """The listener stands and reads, else `OSError` with why."""
        with self.lock:
            if self.proc and self.proc.poll() is None and self.reader.is_alive() and self.ready.is_set():
                return
            self.down()
            if not (image := self.image or _image()):
                raise OSError("no execution declares an image to run it in")
            self.ready.clear()
            tail = collections.deque(maxlen=5)
            self.proc = LocalExecution().popen(["docker", "run", "--rm", "-i", "--name", listener(), "--network", "host", "--cap-drop", "ALL",
                                                "--cap-add", "NET_RAW", "--log-driver", "none", "--security-opt", "no-new-privileges", "-u", "0", "--read-only", "--memory", "64m",
                                                "--memory-swap", "64m", "--pids-limit", "16", "--cpus", "0.5", *ceiling(), "--entrypoint", "python3", image, "-u", "-c", _LISTEN],
                                               env=host_env(), cwd=str(data_dir()), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            proc = self.proc

            def read():
                """The listener's lines, while it stands."""
                for line in proc.stdout:
                    if '"ready"' in line[:12]:
                        self.ready.set()
                    elif line.startswith("{"):
                        self.book.heard(line, time.time())
                    else:
                        tail.append(line.strip())
            self.reader = threading.Thread(target=read, name="gfso-net-read", daemon=True)
            self.reader.start()
            end = time.monotonic() + READY_S
            while not self.ready.wait(0.2):
                if proc.poll() is not None or time.monotonic() > end:
                    self.down()
                    raise OSError("; ".join(tail) or "it did not start")
            if self.stood:                       # …what passed since it last stood is on no line: the record says so
                for project in {h["project"] for h in list(self.book.holders.values())}:
                    _append(project, {"at": time.time(), "gap": "the listener stood again: what passed before this may not be on the record"})
            self.stood = True

    def down(self) -> None:
        """No listener."""
        with self.lock:
            if self.proc:
                self.proc.stdin.close()
                self.proc = None
            run(["docker", "rm", "-f", listener()], timeout=60)
            self.ready.clear()

    def admit(self, ex) -> None:
        """Before any code runs in the container `ex` just started: the listener up and the address known, so its first
        packet is on the record. Without them it does not run (`GFSO_NETWORK_RECORD=off` the installation's word)."""
        if network_record_off():
            return
        try:
            with self.lock:
                self.image = ex.image or self.image
                self.up()
            rows = _holders([ex.container])
            if not any(r.split("|")[-1].strip() for r in rows.splitlines()):
                raise OSError(f"Docker gave no address for {ex.container}")
            self.book.learn(rows)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise PlaceUnavailable(ex.name, f"the record of where its sessions reach could not stand ({e}): nothing runs off the record; "
                                            "GFSO_NETWORK_RECORD=off in data/serve.json runs without it") from e

    def turn(self) -> None:
        """One turn of the watch: the system's own containers learned, a listener that died raised, none while no work stands."""
        if network_record_off():
            return
        try:
            with self.lock:                      # …beside an admission: none passes while this takes the listener down
                if (ids := _work_stands()) is None:
                    return
                if not ids:
                    if self.proc:
                        self.down()
                    return
                self.book.learn(_holders(ids), whole=True)
                self.up()
        except (OSError, subprocess.TimeoutExpired) as e:
            log.warning(f"the network's record did not stand ({e}): what passes meanwhile is not on it")


_RECORD = _Record()
_WATCH = threading.Event()


def watch_network() -> None:
    """The record, for this process's life: every container it starts admitted, a watch beside them. Started once."""
    if _WATCH.is_set():
        return
    _WATCH.set()
    E.ON_START.append(_RECORD.admit)

    def watch():
        """A turn each `WATCH_S`."""
        while not time.sleep(WATCH_S):
            try:
                _RECORD.turn()
            except Exception as e:      # …a half-written declaration ended the watch for the process's life (critic, ran)
                log.warning(f"the network's record passed over a turn ({e})")
    threading.Thread(target=watch, name="gfso-net", daemon=True).start()
