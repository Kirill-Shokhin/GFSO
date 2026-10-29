"""What this installation holds in Docker, per project and node: its containers — by role, node and agent, standing or
running, busy where a call runs in them, their CPU and memory — and its volumes' sizes on disk. Read from Docker alone,
by the labels the system sets at every making (`execution.identity`, `execution.ROLE`): no project's engine is woken,
nothing an agent wrote is read. What it shows, any part of the page draws; it acts on nothing — a node's work is ended by the protocol
(CANCEL, `stop_project`), never under it. NOT YET: removing an orphan's volumes — named by a project's NAME against the
registry's files, a held project matched under another spelling or an unlistable directory (critics over 4d4aeed,
8f6dfae, run); it waits for an identity no spelling shares (an id the project's record and its volumes both carry).

A number Docker did not give is None, never 0: a sum says how many it summed (`…_counted`), a read Docker failed says so
(`read`) — the reading before it served —, and counts no read ever answered are None."""
import json
import re
import subprocess
import threading
import time

from gfso.adapters.children import run
from gfso.adapters.execution import AGENT, HOME, LABEL, NODE, PROJECT, ROLE, installation

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
_read: dict = {}
_lock = threading.Lock()


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
    """(`read()`, did Docker answer) — asked at most once every `fresh` seconds, whoever asks; a failed read keeps the
    reading before it."""
    at, value, ok = _read.get(key, (0.0, None, False))
    if time.monotonic() - at > fresh:
        got = read()
        ok = got is not None
        _read[key] = (time.monotonic(), value := got if ok else value, ok)
    return value, ok


def _stats() -> dict | None:
    """{id: (cpu %, memory bytes, pids)} of every running container."""
    if (lines := _docker("stats", "--no-stream", "--format", "{{.ID}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.PIDs}}")) is None:
        return None
    out = {}
    for line in lines:
        i, cpu, mem, pids = (line.split("\t") + [""] * 4)[:4]
        out[i] = (float(cpu.rstrip("%")) if re.fullmatch(r"[\d.]+%", cpu) else None,
                  size(mem.split("/")[0]), int(pids) if pids.isdigit() else None)
    return out


def _volumes() -> list[dict] | None:
    """This installation's volumes: name, project, size."""
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
            out.append({"name": v.get("Name"), "project": labels.get(PROJECT),
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


def held(known: set | None = None) -> dict:
    """What this installation holds now, per project — each said `known` where the registry holds it (`known`, None:
    not asked) — what containers of a build that set no home hold, unattributed, and which reads Docker answered."""
    with _lock:
        stats, stats_ok = _cached("stats", FRESH, _stats)
        lines, ps_ok = _cached("ps", FRESH, lambda: _docker("ps", "-a", "--filter", f"label={LABEL}", "--format", _PS))
        volumes, disk_ok = _cached("volumes", DISK_FRESH, _volumes)
        machine, _ = _cached("machine", DISK_FRESH, _machine)
    rows = [_container(line.split("\t"), stats or {}) for line in lines or []]
    volumes = volumes or []
    ours, older = [r for r in rows if r["home"] == installation()], [r for r in rows if not r["home"]]
    projects = sorted(({r["project"] for r in ours} | {v["project"] for v in volumes}) - {None})
    held_as = None if known is None else {k.casefold() for k in known}     # …the registry's files: any spelling
    return {"home": installation(), "machine": machine,
            "read": {"containers": ps_ok, "stats": stats_ok, "disk": disk_ok},
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
