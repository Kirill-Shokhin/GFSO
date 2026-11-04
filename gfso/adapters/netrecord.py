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
from gfso.adapters.execution import HOME, NODE, PROJECT, ROLE, LocalExecution, PlaceUnavailable, ceiling, executions, file_record_path, host_env, installation, network_record_path, run
from gfso.adapters.records import append, rows_of
from gfso.config import data_dir, network_record_off

log = logging.getLogger(__name__)
#: how often the watch asks which containers stand
WATCH_S = 2.0
#: a project's record turns over at this size, the last turn kept: what a session asks for fills no disk; about 40 containers
#: at their full budget turn out what came before them, and the turn is said on the record
CAP = 16 * 2 ** 20
#: destinations listed per container: past them it is said once, and its flood takes no one else's room
BUDGET = 2000
#: ports of one host listed one by one per container: past them, one line says there are more
PORTS = 64
#: seconds the listener has to open a container's link when asked
SYNC_S = 30.0
#: seconds an ended container keeps its address here: its last flow may be read after it, and a user's container may take it
GRACE_S = 10.0
READY_S = 120.0

#: In the container, its stdin the system's pipe: gone with the server, so is it. A kernel filter passes all but a TCP flow's
#: later packets, whatever else a process can send (SCTP and UDP-Lite open with no capability), so a bulk transfer costs
#: nothing here. A socket per container's link, each read in turn: a flood fills its own buffer alone (one shared blinded
#: every project, critic, ran); a link new to Docker is opened on its kernel notice, before `docker run` returns. Each line one JSON object: a name a session asks is its own text.
_LISTEN = r"""
import ctypes, json, os, select, socket, struct, sys, time
P = [(0x30, 0, 0, 0xfffff004), (0x15, 17, 0, 4),                   # …what a link carries TO its container: not where it reached
     (0x28, 0, 0, 12), (0x15, 0, 8, 0x800),
     (0x28, 0, 0, 20), (0x45, 13, 0, 0x1fff),                      # …an IP fragment past the first: no header in it, only what looks like one
     (0x30, 0, 0, 23), (0x15, 0, 10, 6), (0xb1, 0, 0, 14), (0x50, 0, 0, 27), (0x54, 0, 0, 0x12), (0x15, 6, 7, 2),
     (0x15, 0, 6, 0x86dd), (0x30, 0, 0, 20), (0x15, 0, 3, 6), (0x30, 0, 0, 67), (0x54, 0, 0, 0x12), (0x15, 0, 1, 2),
     (0x06, 0, 0, 512), (0x06, 0, 0, 0)]
code = ctypes.create_string_buffer(b"".join(struct.pack("HBBI", *p) for p in P))
BUDGET, PORTS = int(sys.argv[1]), int(sys.argv[2])
def say(**row):
    print(json.dumps(row), flush=True)
def name(b, at):
    parts = []
    while at < len(b) and b[at] and len(parts) < 40:
        parts.append(b[at + 1:at + 1 + b[at]].decode("ascii", "replace"))
        at += b[at] + 1
    return ".".join(parts)[:253]
class Link:
    def __init__(self, k):
        self.k, self.seen, self.ports, self.src, self.mac, self.lost, self.cut = k, set(), {}, None, "", 0, False
links = {}
changes = socket.socket(socket.AF_NETLINK, socket.SOCK_RAW, 0)
changes.bind((0, 1))
def tell(link):
    link.lost += struct.unpack("II", link.k.getsockopt(263, 6, 8))[1]
    if link.lost and link.src:
        say(drops=link.lost, src=link.src, mac=link.mac)
        link.lost = 0
def close(n):
    try:
        tell(links[n])
    except OSError:
        pass
    links.pop(n).k.close()
def scan():
    here = set(os.listdir("/sys/class/net"))
    for n in set(links) - here:
        close(n)
    for n in here:
        if n.startswith("veth") and n not in links:
            try:
                # …of no protocol until it is bound: with one it takes every link's frames, unfiltered, from this line on, and a
                # neighbour's flood counted as this new container's loss (ran)
                k = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, 0)
                k.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 ** 20)
                k.setsockopt(socket.SOL_SOCKET, 26, struct.pack("HL", len(P), ctypes.addressof(code)))
                k.bind((n, 3))
                k.setblocking(False)
                links[n] = Link(k)
            except OSError:
                pass
scan()
say(ready=True)
said = time.monotonic()
def one(link):
    p = link.k.recv(600)
    if link.cut or len(p) < 34:
        return
    v6 = p[12:14] == b"\x86\xdd"
    proto, hl = (p[20], 40) if v6 else (p[23], (p[14] & 15) * 4)
    src, dst = ((socket.inet_ntop(socket.AF_INET6, p[22:38]), socket.inet_ntop(socket.AF_INET6, p[38:54])) if v6 else
                (socket.inet_ntoa(p[26:30]), socket.inet_ntoa(p[30:34])))
    link.src, link.mac = src, p[6:12].hex()
    port = struct.unpack("!H", p[14 + hl + 2:14 + hl + 4])[0] if proto in (6, 17, 132, 136) and len(p) >= 14 + hl + 4 else 0
    asked = name(p, 14 + hl + 8 + 12) if proto == 17 and port == 53 else ""
    key = hash((proto, dst, port, asked))    # …a hash: a list of names at their longest would outgrow this container
    if key in link.seen:
        return
    if not asked:
        host = hash((proto, dst))            # …a host's ports spend no room meant for other hosts
        link.ports[host] = n = link.ports.get(host, 0) + 1
        if n > PORTS:
            if n == PORTS + 1:
                say(src=src, mac=link.mac, proto=proto, to=dst, port=-1, asked="")
            link.ports[host] = PORTS + 2
            return
    if len(link.seen) >= BUDGET:
        link.cut = True
        return say(src=src, mac=link.mac, cut=BUDGET)
    link.seen.add(key)
    say(src=src, mac=link.mac, proto=proto, to=dst, port=port, asked=asked)
while True:
    ready = select.select([changes, 0, *(l.k for l in links.values())], [], [], 10)[0]
    if 0 in ready:
        if not os.read(0, 64):
            break
        scan()                               # …the system asks before a container's code runs: its link is read from here on
        say(synced=True)
    if changes in ready:
        changes.recv(65536)
        scan()
    for n, link in list(links.items()):
        if link.k not in ready:
            continue
        try:
            for _ in range(16):      # …each link its turn: a flood on one waits while the others are read
                one(link)
        except BlockingIOError:
            pass
        except OSError:              # …its container gone
            close(n)
    if time.monotonic() - said > 10:
        said = time.monotonic()
        for link in links.values():
            tell(link)
"""
_KINDS = {6: "tcp", 17: "udp", 1: "icmp", 58: "icmp", 132: "sctp", 136: "udplite"}


class _Book:
    """Who holds which address (each container the installation made, by its labels), and each line the listener says of
    it on its project's record."""

    def __init__(self):
        self.holders, self.ended = {}, {}

    def learn(self, rows: str, whole: bool = False) -> None:
        """`rows`: `<name>|<project>|<node>|<role>|<address> …` a line. `whole`, all that stand: a holder not among them
        keeps its address `GRACE_S`, then has none: a user's container on a native host takes the next one freed."""
        now, standing = time.monotonic(), set()
        for row in rows.splitlines():
            parts = row.strip().lstrip("/").split("|")
            if len(parts) == 5:
                for at in parts[4].split():
                    ip, _, mac = at.partition("/")
                    if ip:
                        standing.add((ip, mac.replace(":", "")))
                        self.holders[(ip, mac.replace(":", ""))] = dict(zip(("container", "project", "node", "role"), parts))
        if whole:
            for key in list(self.holders):
                if key in standing:
                    self.ended.pop(key, None)
                elif now - self.ended.setdefault(key, now) > GRACE_S:
                    del self.holders[key]
                    self.ended.pop(key, None)

    def heard(self, line: str, now: float) -> None:
        """One line of the listener's, a session's text perhaps inside it. A flow from no container of this installation
        is not recorded: on a Linux host another's containers, or the user's own, are none of this."""
        try:
            row = json.loads(line)
            # …by address and the MAC Docker gave that one start: by the address alone another's container took a freed one in a
            # third of a second and went on this record, a million packets lost with it; by the link first read, a place's next
            # container under its old name was silently off it (critics, ran)
            if not (who := self.holders.get((row.get("src"), row.get("mac", "")))):
                return
            if drops := row.get("drops"):
                log.warning(f"the network's record lost {drops} packets of {who['container']}: its flood outran it, and what it sent then is not on the record")
                _append(who["project"], {"at": now, "container": who["container"], "lost_packets": int(drops)})
                return
            if cut := row.get("cut"):
                log.warning(f"the network's record passed {int(cut)} destinations of {who['container']}: the rest are not on the record")
                _append(who["project"], {"at": now, "container": who["container"], "cut": f"more than {int(cut)} destinations: the rest not listed"})
                return
            _append(who["project"], {"at": now, **{k: who[k] for k in ("container", "node", "role")},
                                     "kind": "dns" if row["asked"] else _KINDS.get(row["proto"], f"ip{row['proto']}"),
                                     "to": str(row["to"]), **({"more_ports": f"more than {PORTS} ports: the rest not listed"} if int(row["port"]) < 0 else {"port": int(row["port"])}),
                                     **({"asked": str(row["asked"])} if row["asked"] else {})})
        except (ValueError, KeyError, TypeError, AttributeError, OSError) as e:
            log.warning(f"the network's record passed over a line it could not read ({e})")


record_path = network_record_path


def forget(project: str) -> None:
    """A project gone: a new one of the name inherits none of its records."""
    for at in (record_path(project), file_record_path(project)):
        for p in (at, at.with_suffix(".jsonl.1"), at.with_suffix(".lock")):
            p.unlink(missing_ok=True)


def _append(project: str, row: dict) -> None:
    """`row` on `project`'s record."""
    append(record_path(project), row, CAP)


def said_apart(project: str) -> list:
    """What the record says of itself: each container that lost lines or passed its budget, and each gap. A row of these
    is where a session may have hidden, so a reader is told without reading every destination."""
    lost, cut, gaps, turned = collections.Counter(), set(), 0, 0
    said_files, bad = [], 0
    for p in (file_record_path(project).with_suffix(".jsonl.1"), file_record_path(project)):
        got, unread = rows_of(p)
        bad += unread
        turned += sum("turned" in r for r in got)
        gaps += sum("gap" in r for r in got)
        said_files += [f"{r.get('session')}: {r.get('dir')}: " + ("what changed could not be read" if "unread" in r else "more changed than a reading names")
                       for r in got if "unread" in r or "cut" in r or r.get("changed_n", 0) > len(r.get("changed", ()))]
    for p in (record_path(project).with_suffix(".jsonl.1"), record_path(project)):
        got, unread = rows_of(p)
        bad += unread
        for row in got:
            lost[row.get("container")] += row.get("lost_packets", 0)
            cut |= {row["container"]} if "cut" in row else set()
            gaps += "gap" in row
            turned += "turned" in row
    return ([f"{c}: {n} packets not read, what it sent then is not listed" for c, n in lost.items() if n]
            + [f"{c}: past its {BUDGET} destinations, the rest not listed" for c in sorted(cut)]
            + ([f"{gaps} times the listener stood again: what passed before each may not be listed"] if gaps else [])
            + ([f"turned over {turned} times: older rows are gone"] if turned else [])
            + list(dict.fromkeys(said_files)) + ([f"{bad} lines of the records could not be read"] if bad else []))


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
    got = run(["docker", "inspect", "-f", f"{{{{.Name}}}}|{labels}|{{{{range .NetworkSettings.Networks}}}}{{{{.IPAddress}}}}/{{{{.MacAddress}}}} {{{{.GlobalIPv6Address}}}}/{{{{.MacAddress}}}} {{{{end}}}}",
               *ids], timeout=30, text=True)
    return got.stdout or ""


def listener() -> str:
    """The listener's name: this process's own, so another process of the installation, or another installation, stands
    beside it: under one name each removed the other, and what passed between was on no record (critic, ran)."""
    return f"gfso-net-record-{installation()}-{os.getpid()}"


class _Record:
    """The listener's life, one per process that starts containers."""

    def __init__(self):
        self.book, self.proc, self.reader, self.image, self.stood, self.watched = _Book(), None, None, None, False, False
        self.ready, self.synced, self.lock = threading.Event(), threading.Event(), threading.RLock()

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
                                                "--memory-swap", "64m", "--pids-limit", "16", "--cpus", "0.5", *ceiling(), "--entrypoint", "python3", image, "-u", "-c", _LISTEN, str(BUDGET), str(PORTS)],
                                               env=host_env(), cwd=str(data_dir()), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            proc = self.proc

            def read():
                """The listener's lines, while it stands."""
                for line in proc.stdout:
                    if '"ready"' in line[:12]:
                        self.ready.set()
                    elif '"synced"' in line[:12]:
                        self.synced.set()
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

    def _sync(self) -> None:
        """Back once the listener has opened every link there is now, a container's just started among them."""
        self.synced.clear()
        self.proc.stdin.write("s")
        self.proc.stdin.flush()
        if not self.synced.wait(SYNC_S):
            raise OSError("the listener did not open its link in time")

    def admit(self, ex) -> None:
        """Before any code runs in the container `ex` just started: the listener up, its link open and the address known,
        so its first packet is on the record. Without them it does not run (`GFSO_NETWORK_RECORD=off` the installation's
        word)."""
        if network_record_off():
            return
        try:
            with self.lock:
                self._watch()
                self.image = ex.image or self.image
                self.up()
                rows = _holders([ex.container])
                if not any(a.split("/")[0] for r in rows.splitlines() for a in r.split("|")[-1].split()):
                    raise OSError(f"Docker gave no address for {ex.container}")
                self.book.learn(rows)
                self._sync()
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
                    if self.proc and self.proc.poll() is not None:     # …no one took it down: Docker went, and the work with it
                        for project in {h["project"] for h in self.book.holders.values()}:
                            _append(project, {"at": time.time(), "gap": "Docker went with this work standing: what it did last may not be on the record"})
                    if self.proc:
                        self.down()
                    self.book, self.stood = _Book(), False     # …taken down on purpose, holding no one: no gap to say
                    return
                self.book.learn(_holders(ids), whole=True)
                self.up()
        except (OSError, subprocess.TimeoutExpired) as e:
            log.warning(f"the network's record did not stand ({e}): what passes meanwhile is not on it")


    def _watch(self) -> None:
        """A turn each `WATCH_S`, started by the process's first admission: a process that starts no container stands no
        listener (three bridges beside one server stood three, each writing every row)."""
        if self.watched:
            return
        self.watched = True

        def watch():
            """A turn each `WATCH_S`."""
            while not time.sleep(WATCH_S):
                try:
                    self.turn()
                except Exception as e:      # …a half-written declaration ended the watch for the process's life (critic, ran)
                    log.warning(f"the network's record passed over a turn ({e})")
        threading.Thread(target=watch, name="gfso-net", daemon=True).start()


#: every container this process starts is admitted: the module's import is the registration, and a list left empty refuses
E.ON_START.append(_Record().admit)
