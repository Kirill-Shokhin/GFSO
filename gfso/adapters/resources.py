"""What this installation holds in Docker, per project and node: its containers — by role, node and agent, standing or
running, busy where a call runs in them, their CPU and memory — and its volumes' sizes on disk. Read from Docker alone,
by the labels the system sets at every making (`execution.identity`, `execution.ROLE`): no project's engine is woken,
nothing an agent wrote is read. What it shows, any part of the page draws. A node's work is ended by the protocol
(CANCEL, `stop_project`), never under it; the one act here removes an ORPHAN's volumes (`remove_orphan`).

An orphan is known by its project's ID (`execution.ID`, made once in the project's record), never by its name: named
by the project's NAME against the registry's files, a held project matched under another spelling (Windows: `Alpha.db`
held, volumes labelled `alpha`) or every project looked nobody's where the data dir could not be listed (critics over
4d4aeed, 8f6dfae, run). So `known` stays a reading for the eye, and removal asks every held record's id at the moment
it removes. A volume made before its project had an id carries none (Docker relabels nothing): shown, its `project_id`
None, never removed here — it goes with its project (`execution.drop_volumes`).

A number Docker did not give is None, never 0: a sum says how many it summed (`…_counted`), a read Docker failed says so
(`read`) — the reading before it served —, and counts no read ever answered are None."""
import atexit
import json
import os
import re
import subprocess
import threading
import time

from gfso.adapters.children import adopt, release, run, spawn_kw
from gfso.adapters.execution import AGENT, HOME, ID, LABEL, NODE, PROJECT, ROLE, installation

#: the processes a container that hosts calls holds while none runs: `--init` and the `sleep` it waits in — a door's
#: or a gateway's own server is its work, never "busy" (measured: an idle door at 3, a judge's `claude -p` at 21)
IDLE_PIDS = 2
HOSTS = ("executor", "judge", "check", "system")
#: seconds a reading stands before Docker is asked again — `docker stats` takes ~2 s, `system df -v` ~0.3–4 s (measured)
FRESH, DISK_FRESH = 5.0, 60.0
#: seconds one Docker read may take: a hung daemon holds every poller behind the lock no longer than this
ASK = 20
_UNITS = {"b": 1, "kb": 10 ** 3, "mb": 10 ** 6, "gb": 10 ** 9, "tb": 10 ** 12,
          "kib": 2 ** 10, "mib": 2 ** 20, "gib": 2 ** 30, "tib": 2 ** 40}
_SIZE = re.compile(r"([\d.]+)\s*([a-z]*)", re.I)
_PS = "\t".join(["{{.ID}}", "{{.Names}}", "{{.State}}", *(f"{{{{.Label \"{k}\"}}}}" for k in (
    HOME, PROJECT, ROLE, NODE, AGENT, "com.docker.compose.service"))])
#: seconds Docker's streams go on after the last reader asked
WATCHED = 300.0
_read: dict = {}
_lock = threading.Lock()
_watch = threading.Event()
_asked = [float("-inf")]
#: who is told each new reading the poller stores — an open page's socket (`/ws/events`, type `resources`)
LISTENERS: list = []


def size(text) -> int | None:
    """Bytes of a size as Docker prints it — `13.6MB`, `752KiB`; None for `N/A` or anything else."""
    m = _SIZE.fullmatch((text or "").strip())
    unit = m and (m[2].lower() or "b")
    return int(float(m[1]) * _UNITS[unit]) if m and unit in _UNITS else None


def _docker(*args) -> list[str] | None:
    """Docker's answer, line by line; None where it gave none — not running, not installed, past `ASK`."""
    try:
        got = run(["docker", *args], timeout=ASK, text=True, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (got.stdout or "").splitlines() if got.returncode == 0 else None


def _cached(key: str, fresh: float, read) -> tuple:
    """(`read()`, did Docker answer, when the reading given was taken — epoch seconds, None before any) — asked at most
    once every `fresh` seconds, whoever asks; a failed read keeps the reading before it, and its time. Docker is asked
    outside the lock, which guards the store alone: a reader of the reading never waits on Docker (critic: a page waited
    8.8 s behind a slow `system df`)."""
    at, value, ok, taken = _read.get(key, (0.0, None, False, None))
    if time.perf_counter() - at > fresh:
        got = read()
        with _lock:
            at, value, ok, taken = _read.get(key, (0.0, None, False, None))
            ok = got is not None
            value, taken = (got, time.time()) if ok else (value, taken)
            _read[key] = (time.perf_counter(), value, ok, taken)
    return value, ok, taken


#: one row of `docker stats` per running container
_STATS = "{{.ID}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.PIDs}}"


def _stats() -> dict | None:
    """{id: (cpu %, memory bytes, pids)} of every running container — asked once."""
    if (lines := _docker("stats", "--no-stream", "--format", _STATS)) is None:
        return None
    return _parse_stats(lines)


def _ps() -> list[str] | None:
    return _docker("ps", "-a", "--filter", f"label={LABEL}", "--format", _PS)


def _parse_stats(lines: list) -> dict:
    out = {}
    for line in lines:
        i, cpu, mem, pids = (line.split("\t") + [""] * 4)[:4]
        out[i] = (float(cpu.rstrip("%")) if re.fullmatch(r"[\d.]+%", cpu) else None,
                  size(mem.split("/")[0]), int(pids) if pids.isdigit() else None)
    return out


def _volumes() -> list[dict] | None:
    """This installation's volumes: name, project, its id (None: made before ids — never removable here), size."""
    if not (lines := _docker("system", "df", "-v", "--format", "{{json .}}")):
        return None
    try:
        vols = json.loads(lines[0]).get("Volumes") or []
    except ValueError:
        return None
    out = []
    for v in vols:
        labels = dict(kv.split("=", 1) for kv in (v.get("Labels") or "").split(",") if "=" in kv)
        if labels.get(HOME) == installation():
            out.append({"name": v.get("Name"), "project": labels.get(PROJECT), "project_id": labels.get(ID),
                        "role": "state" if str(v.get("Name")).endswith("-state") else "places",
                        "bytes": size(v.get("Size"))})
    return out


def _machine() -> dict | None:
    if not (lines := _docker("info", "--format", "{{.NCPU}} {{.MemTotal}}")):
        return None
    cpus, mem = (lines[0].split() + [""] * 2)[:2]
    return {"cpus": int(cpus) if cpus.isdigit() else None, "memory_bytes": int(mem) if mem.isdigit() else None}


def _totals(rows) -> dict:
    """CPU and memory summed over `rows` where Docker gave them, and over how many it gave them for."""
    out = {}
    for key in ("cpu_percent", "memory_bytes"):
        got = [r[key] for r in rows if r.get(key) is not None]
        out |= {key: round(sum(got), 2) if got else None, f"{key}_counted": f"{len(got)}/{len(rows)}"}
    return out


def _container(fields: list, stats: dict) -> dict:
    i, name, state, home, project, role, node, agent, service = (fields + [""] * 9)[:9]
    role = role or service or "system"
    # …a stopped container holds nothing: 0, given — not a number Docker failed to give
    cpu, mem, pids = stats.get(i, (None, None, None)) if state == "running" else (0.0, 0, None)
    return {"id": i, "name": name, "state": state, "home": home, "project": project or None, "role": role,
            "node": None if role == "system" else node or None, "agent_id": agent or None,
            "busy": (pids > IDLE_PIDS if pids is not None else None) if role in HOSTS and state == "running" else
            (False if role in HOSTS else None), "cpu_percent": cpu, "memory_bytes": mem}


def refresh() -> None:
    """Every reading asked of Docker once, each at most once every its freshness — the streams' first reading, and a
    test's; never a page's (the author, 2026-10-30: «интерфейс должен подгружать то что есть в бэке а не что то
    тригерить самим чтением»)."""
    _cached("stats", FRESH, _stats)
    _cached("ps", FRESH, _ps)
    _cached("volumes", DISK_FRESH, _volumes)
    _cached("machine", DISK_FRESH, _machine)


def watch() -> None:
    """THE SERVER'S OWN READING OF DOCKER, started once: Docker tells what changes, nobody polls it (the author,
    2026-10-30: «это же сам докер должен отдавать … обновления от него вообще хуком можно сделать»). Its event stream
    says a container or a volume was made, started, ended or removed, and the list is read again then; its stats stream
    sends every running container's figures about once a second, kept as they come; the disk, of which Docker tells
    nothing, is read after a volume's event and otherwise every `DISK_FRESH`. Whatever is new is told to whoever listens
    — an open page — once a second, every container's figures in one message: Docker's own rate, never thinned (the
    author: «зачем слать с уменьшенной частотой что само идет чаще?»). The streams run while somebody reads (a page open, or a read in the
    last `WATCHED` seconds) and stop after: an idle server asks Docker nothing, and a page opened then gets the last
    reading at once, its age said, the streams starting behind it."""
    if _watch.is_set():
        return
    _watch.set()
    live = Live()
    atexit.register(live.stop)                        # …Docker's streams end with the server, on Windows too

    def supervise():
        """Once a second, for the server's life."""
        while True:
            try:
                live.tick()
            except Exception:                         # noqa: BLE001 — a reading not taken is said by its own flags
                pass
            time.sleep(1.0)
    threading.Thread(target=supervise, name="gfso-resources", daemon=True).start()


def _wanted() -> bool:
    return not _read or bool(LISTENERS) or time.perf_counter() - _asked[0] < WATCHED


class Live:
    """Docker's two streams while somebody reads, and what their events made stale."""

    def __init__(self, spawn=None):
        #: what starts one of Docker's streams (argv → a process with `stdout` and `poll`) — Docker's client by default
        self.spawn = spawn or _spawn
        self.procs: list = []
        self.started = self.again = float("-inf")
        self.wait = 1.0
        self.stale = {"ps", "volumes"}
        self.told: dict = {}

    def tick(self) -> None:
        """One second of the server's reading: the streams kept up while wanted, what an event made stale read again,
        the disk on its timer, a new reading told."""
        if not _wanted():
            self.again = float("-inf")                # …stopped for want of a reader, not for failing: next start at once
            return self.stop()
        if (not self.procs or any(p.poll() is not None for p in self.procs)) and time.perf_counter() >= self.again:
            # …a stream that ended soon after its start (Docker down) is tried again later each time, up to a minute
            self.wait = min(2 * self.wait, 60.0) if self.procs and time.perf_counter() - self.started < 10 else 1.0
            self.stop()
            self.start()
            self.started, self.again = time.perf_counter(), time.perf_counter() + self.wait
        stale, self.stale = self.stale, set()
        if "ps" in stale:
            _cached("ps", -1.0, _ps)
        if "volumes" in stale or time.perf_counter() - _read.get("volumes", (float("-inf"),))[0] > DISK_FRESH:
            _cached("volumes", -1.0, _volumes)
        _cached("machine", DISK_FRESH, _machine)
        self.tell()

    def tell(self) -> None:
        """What is new since the last tick, told to the listeners."""
        now = {k: v[0] for k, v in _read.items()}       # …each read's own moment, on a clock fine enough that two differ
        if now != self.told:
            self.told = now
            for tell in list(LISTENERS):
                tell()

    def start(self) -> None:
        """Docker's event and stats streams started, each read by a thread of its own; everything read anew."""
        self.stale |= {"ps", "volumes"}
        # …the system's own, by the label every installation's container and volume carries: another program's volume
        # made on the machine re-read the disk each second (critic)
        events = self.spawn(["docker", "events", "--filter", f"label={HOME}", "--filter", "type=container",
                             "--filter", "type=volume",
                             *[a for e in ("create", "start", "die", "destroy") for a in ("--filter", f"event={e}")],
                             "--format", "{{.Type}}"])
        stats = self.spawn(["docker", "stats", "--format", _STATS])
        self.procs = [events, stats]
        threading.Thread(target=self.events, args=(events.stdout,), daemon=True).start()
        threading.Thread(target=self.stats, args=(stats.stdout,), daemon=True).start()

    def stop(self) -> None:
        """Both streams ended — Docker's client, a process of its own with none under it."""
        for p in self.procs:
            p.kill()
            p.wait()
            release(p)                                # …reaped and forgotten: a restart leaks no process nor its pipe
        self.procs = []

    def events(self, lines) -> None:
        """Each event makes the list stale; a volume's, the disk too."""
        for kind in lines:
            self.stale |= {"ps", "volumes"} if kind.strip() == "volume" else {"ps"}

    def stats(self, lines) -> None:
        """Frames as Docker draws them for a terminal, each opening with the cursor sent home: one reading each."""
        frame: list = []
        for line in lines:
            if "\x1b[H" in line and frame:
                _store("stats", _parse_stats(frame))
                frame = []
            if row := re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line).strip():
                frame.append(row)
        with _lock:                                   # …the stream ended: the last reading stands, said as not fresh
            at, value, _, taken = _read.get("stats", (0.0, None, False, None))
            _read["stats"] = (at, value, False, taken)


def _spawn(argv: list):
    """One of Docker's streams, its lines as text, no console window, ended with the server."""
    return adopt(subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                  errors="replace", **spawn_kw(),
                                  **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {})))


def _store(key: str, value) -> None:
    with _lock:
        _read[key] = (time.perf_counter(), value, True, time.time())


def _stored(key: str) -> tuple:
    """(the reading, did Docker answer its last ask, when the reading was taken) as it stands — None before any."""
    _, value, ok, taken = _read.get(key, (0.0, None, False, None))
    return value, ok, taken


def held(known: set | None = None) -> dict:
    """What this installation holds, per project, as the last reading has it — each said `known` where the registry
    holds it (`known`, None: not asked) —, what containers of a build that set no home hold, unattributed, which reads
    Docker answered and when each was taken. Docker is never asked here (`watch`)."""
    _asked[0] = time.perf_counter()
    watch()
    with _lock:
        stats, stats_ok, stats_at = _stored("stats")
        lines, ps_ok, ps_at = _stored("ps")
        volumes, disk_ok, disk_at = _stored("volumes")
        machine, _, _ = _stored("machine")
    rows = [_container(line.split("\t"), stats or {}) for line in lines or []]
    volumes = volumes or []
    ours, older = [r for r in rows if r["home"] == installation()], [r for r in rows if not r["home"]]
    projects = sorted(({r["project"] for r in ours} | {v["project"] for v in volumes}) - {None})
    held_as = None if known is None else {k.casefold() for k in known}     # …the registry's files: any spelling
    return {"home": installation(), "machine": machine,
            "read": {"containers": ps_ok, "stats": stats_ok, "disk": disk_ok},
            # …and when each reading given was taken (epoch seconds; None: none yet), so a reader can say its age
            "read_at": {"containers": ps_at, "stats": stats_at, "disk": disk_at},
            "projects": [_project(p, [r for r in ours if r["project"] == p] if lines is not None else None,
                                  [v for v in volumes if v["project"] == p], held_as) for p in projects],
            "older_build": {"containers": len(older) if lines is not None else None, **_totals(older)}}


def _busy(rows) -> dict:
    """How many of `rows` a call runs in, over how many that was read for."""
    got = [r["busy"] for r in rows if r["busy"] is not None]
    return {"busy": sum(got) if got else None, "busy_counted": f"{len(got)}/{len(rows)}"}


def _project(name: str, rows: list | None, volumes: list, held_as) -> dict:
    """One project's reading; `rows` None where Docker never listed the containers — their counts None, not 0."""
    sized = [v["bytes"] for v in volumes if v["bytes"] is not None]
    disk = {"project": name, "known": None if held_as is None else name.casefold() in held_as,
            "disk_bytes": sum(sized) if sized else None, "disk_counted": f"{len(sized)}/{len(volumes)}",
            # …the ids its volumes carry: what `remove_orphan` takes, for a project no record holds
            "project_ids": sorted({v["project_id"] for v in volumes if v.get("project_id")}),
            "volumes": volumes}
    if rows is None:
        return {**disk, "containers": None, "by_role": None, "nodes": None, "system": None}
    return {**disk, **_totals(rows),
            "containers": {"standing": len(rows), "running": sum(r["state"] == "running" for r in rows), **_busy(rows)},
            "by_role": {k: {"standing": len(of), **_busy(of)}
                        for k in sorted({r["role"] for r in rows}) if (of := [r for r in rows if r["role"] == k])},
            "nodes": [{"node": n, **_totals(of), "containers": of}
                      for n in sorted({r["node"] for r in rows} - {None}) if (of := [r for r in rows if r["node"] == n])],
            "system": [r for r in rows if r["node"] is None]}


def remove_orphan(project_id: str, held) -> dict:
    """{removed: [volume], refused: {volume: why}} — the volumes of this installation carrying `project_id`, each removed
    by its exact name where it is still an orphan's at its removal: no project of `held()` ([(name, id or None)], every
    record the registry holds, read whole at each call — `ProjectRegistry.ids`; read again before each volume, so a
    project opened meanwhile under the volume's name keeps it — critic over the act, a hook opening it mid-loop) carries
    the id, and none is held under the name the volume is labelled with (a held project mounts its volumes by NAME,
    `Volume.require`: a project made again under an old name took the old one's volumes, its id another). Docker itself
    refuses to remove a volume any container uses, started or not. Held are the projects of this data dir and this
    process: a memory store of another process is none of them. ValueError where the id is held or Docker did not
    answer; LookupError where no volume of ours carries it."""
    if not re.fullmatch(r"[0-9a-f]{32}", project_id):
        raise LookupError(f"{project_id!r} is no project's id")
    if owner := [n for n, i in held() if i == project_id]:
        raise ValueError(f"{project_id} is the project {owner[0]}'s: its volumes are held")
    lines = _docker("volume", "ls", "--filter", f"label={HOME}={installation()}", "--filter", f"label={ID}={project_id}",
                    "--format", f"{{{{.Name}}}}\t{{{{.Label \"{PROJECT}\"}}}}")
    if lines is None:
        raise ValueError("Docker did not answer: nothing removed")
    if not lines:
        raise LookupError(f"no volume of this installation carries {project_id}")
    removed, refused = [], {}
    for name, project in ((line.split("\t") + [""])[:2] for line in lines):
        try:
            now = held()
        except OSError as e:
            refused[name] = f"the registry did not read: {e}"
            continue
        if owner := [n for n, i in now if i == project_id or n.casefold() == project.casefold()]:
            refused[name] = f"labelled {project!r}: the project {owner[0]} is held under that name now and mounts its volumes by it"
        elif _docker("volume", "rm", name) is None:
            refused[name] = "mounted by a container: Docker refused its removal"
        else:
            removed.append(name)
    _cached("volumes", -1.0, _volumes)              # …the sizes' reading shows what stands now: the act asks, not a read
    return {"project_id": project_id, "removed": removed, "refused": refused}
