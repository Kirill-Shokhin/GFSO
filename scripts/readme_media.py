"""Rebuild the README's pictures of the page from a recorded run — one command, the same paths every time.

The README shows the UI on a real run: an animation of the run replayed and stills of its last moment. Re-shot by hand
they drift from the page; this makes them a build product. Each frame is the run cut at a moment T — the db copied,
every row after T dropped, each node in the state its last move before T left it — and the page drawn over that copy
with its clock fixed at T. The page and its API are served from THIS process (the server's own app over the copy, no
port, no model), so nothing live is touched; the sessions running at T, booked only when they end, are put back into
the runtime's in-flight list from the run's ledger.

    python scripts/readme_media.py                    # every shot of SHOTS into docs/
    python scripts/readme_media.py --run <run.db> --only hero.gif

Needs playwright (with chromium) and ffmpeg on PATH. The default run is the `sql_database` · Haiku 4.5 row closed DONE at
held-out 1.000 (EVIDENCE_LOG §13.47); its db lives in the data directory of the machine that ran it, not in the repo.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
RUN = ROOT / "data" / "gb-sql-database-tnha1f292.db"
SIZE = {"width": 1440, "height": 900}          # CSS px: a usual monitor's 16:10, where the graph, the panel and the deck sit
SCALE = 1.25                                    # as on the page; the files stay 1800 px wide, as the README's were
TZ = os.environ.get("MEDIA_TZ", "Asia/Bangkok")  # the zone the default run's stamps were written in (UTC+7)

# What the README shows. `film` = one frame per state change of the run, the last held; `still` = the run's last moment.
SHOTS = {
    "hero.gif":        {"film": True,  "tab": "timeline", "deck": 290},
    "ui-panel.png":    {"film": False, "tab": "timeline", "deck": 290, "task": "root.select"},
    "ui-progress.png": {"film": False, "tab": "progress", "deck": 520},
}
FRAME_S, HOLD_S = 0.7, 3.5


def moments(db: Path) -> list[str]:
    """A frame after each change of a node's state — closer together while parts run at once, wider in long rework."""
    c = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    ts = [dt.datetime.fromisoformat(r[0]) for r in c.execute(
        "select ts from audit_log where rejected=0 and new_state is not null and old_state != new_state order by ts")]
    picked: list[dt.datetime] = []
    first = ts[0] if ts else None
    for t in ts:
        gap = 150 if (t - first).total_seconds() < 3 * 3600 else 420
        if not picked or (t - picked[-1]).total_seconds() >= gap:
            picked.append(t)
    return [f"{p + dt.timedelta(seconds=20):%Y-%m-%d %H:%M:%S}" for p in picked]


# ---- one frame, in a process of its own (the app reads its data directory once, at import) ----

def cut(src: Path, dst: Path, T: str) -> None:
    """The run as it stood at T. The tables stamp differently ('T' in the audit, a space in the ledgers)."""
    sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True).execute(f"VACUUM INTO '{dst.as_posix()}'").connection.close()
    c = sqlite3.connect(dst)
    for table, at in (("audit_log", T.replace(" ", "T")), ("pipeline_log", T), ("llm_usage", T)):
        c.execute(f"delete from {table} where ts > ?", (at,))
    c.execute("delete from tasks where created_at > ?", (T.replace(" ", "T"),))
    for (tid,) in c.execute("select id from tasks").fetchall():
        row = c.execute("select new_state from audit_log where task_id=? and rejected=0 and new_state is not null "
                        "order by ts desc, id desc limit 1", (tid,)).fetchone()
        st = row[0] if row else "IDLE"
        c.execute("update tasks set state=?, done_reason=case when ?='DONE' then done_reason else null end where id=?",
                  (st, st, tid))
    # A stop is a setting with no time of its own (its last value): it stood at T as the last stop or start logged by then.
    last = None
    for ts, msg in c.execute("select ts, message from pipeline_log where source='pause' order by ts, id").fetchall():
        last = (ts, msg) if msg.startswith("STOPPED by ") else None
    c.execute("delete from settings where key in ('paused', 'clock_off_s', 'clock_beat')")
    if last:
        by, _, why = last[1][len("STOPPED by "):].partition(": ")
        c.execute("insert into settings (key, value) values ('paused', ?)",
                  (json.dumps({"by": by, "at": last[0].replace(" ", "T"), "why": why}),))
    # the tech reports filed by T, the same way (one setting, its last value)
    if (rep := c.execute("select value from settings where key='tech_reports'").fetchone()):
        c.execute("update settings set value=? where key='tech_reports'",
                  (json.dumps([r for r in json.loads(rep[0]) if str(r.get("at", "")) <= T.replace(" ", "T")]),))
    # The project's clock (gfso/core/graph/model.py CLOCK_OFF_KEY) adds the time nothing ran it to every date it shows;
    # the record's own value was written by whatever engine loaded it later, and a run stamped on the wall read 6.6 h late
    # (critic). Off is 0 and the beat now: the dates are shown as the run wrote them.
    c.executemany("insert into settings (key, value) values (?, ?)",
                  [("clock_off_s", "0"), ("clock_beat", str(dt.datetime.now().timestamp()))])
    c.commit()
    c.close()


VERB = {"executor": "delegated_execution", "consent": "delegated_consent", "validate_result": "validate_result",
        "validator": "validate_result", "issuer": "issuer_turn"}


def running(src: Path, T: str, project: str) -> list[dict]:
    """Sessions running at T: booked after it, started before it."""
    from zoneinfo import ZoneInfo
    at = lambda s: dt.datetime.fromisoformat(s).replace(tzinfo=ZoneInfo(TZ)).timestamp()   # epoch, as the page's clock
    t, out = at(T), []
    for stage, node, ts, ms in sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True).execute(
            "select stage, node_id, ts, duration_ms from llm_usage where ts > ?", (T,)):
        end = at(ts)
        if ms and end - ms / 1e3 <= t:
            out.append({"verb": VERB.get(stage, stage), "project": project, "task_id": node, "since": round(end - ms / 1e3, 1)})
    return out


def frame(src: Path, T: str, shot: dict, png: Path) -> None:
    home, name = Path(tempfile.mkdtemp(prefix="gfso-media-")), src.stem       # the copy keeps the run's own name
    (home / "data").mkdir()
    cut(src, home / "data" / f"{name}.db", T)
    os.environ.update(GFSO_HOME=str(home), GFSO_DATA_DIR=str(home / "data"))
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient
    from playwright.sync_api import sync_playwright
    from gfso.api.server import create_app
    from gfso.runtime import ProjectRegistry

    reg = ProjectRegistry(default_storage="sqlite", default_llm="stub", seed=False)
    app = TestClient(create_app(reg.engine("default"), registry=reg),   # no `with`: its loops and clocks never start
                     base_url="http://127.0.0.1")   # a name the door answers to
    live = running(src, T, name)

    def fix(o):
        if isinstance(o, dict):
            if "in_flight" in o and isinstance(o["in_flight"], list):
                o["in_flight"] = live
            for v in o.values():
                fix(v)
        elif isinstance(o, list):
            for v in o:
                fix(v)
        return o

    def route(r):
        u = r.request.url
        if not u.startswith("http://gfso.media/"):
            return r.continue_()
        path = u[len("http://gfso.media"):]
        if r.request.method != "GET" and not any(k in path for k in ("next_steps", "tech_reports")):
            return r.abort()                                          # a picture changes nothing
        res = app.request(r.request.method, path, content=r.request.post_data_buffer,
                          headers={"content-type": r.request.headers.get("content-type", "application/json")})
        body, kind = res.content, res.headers.get("content-type", "")
        if path.startswith("/api/") and "json" in kind:
            body = json.dumps(fix(res.json())).encode()
        r.fulfill(status=res.status_code, content_type=kind or "application/octet-stream", body=body)

    # T is the run's wall clock in the zone it ran in; the page reads the same zone (MEDIA_TZ), so its dates are the run's
    from zoneinfo import ZoneInfo
    at = dt.datetime.fromisoformat(T).replace(tzinfo=ZoneInfo(TZ))
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport=SIZE, device_scale_factor=SCALE, locale="en-GB",
                        timezone_id=TZ)
        pg.clock.install(time=at)
        pg.clock.pause_at(at)
        pg.route("**/*", route)
        pg.route_web_socket("**/ws/**", lambda ws: None)              # the live feed: held open, silent — a frame is still
        pg.add_init_script(f"localStorage.setItem('gfso.deck', JSON.stringify({{h: {shot['deck']}}}))")
        pg.goto(f"http://gfso.media/?project={name}" +(f"&task={shot['task']}" if shot.get("task") else ""))
        pg.clock.run_for(5000)
        if shot["tab"] != "timeline":                                 # the deck opens on it; pressing it folds the deck
            pg.locator(f'.dk-tab[data-view="{shot["tab"]}"]').click()
            pg.clock.run_for(1500)
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(png))
        b.close()
    shutil.rmtree(home, ignore_errors=True)


# ---- assembling ----

def gif(frames: list[Path], out: Path) -> None:
    lst = frames[0].parent / "list.txt"
    lst.write_text("".join(f"file '{f.name}'\nduration {HOLD_S if i == len(frames) - 1 else FRAME_S}\n"
                           for i, f in enumerate(frames)) + f"file '{frames[-1].name}'\n")
    pal = frames[0].parent / "palette.png"
    common = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst)]
    subprocess.run(common + ["-vf", "palettegen=max_colors=96:stats_mode=diff", str(pal)], check=True)
    subprocess.run(common + ["-i", str(pal), "-lavfi", "paletteuse=dither=none:diff_mode=rectangle", "-loop", "0", str(out)],
                   check=True)


def png(src: Path, out: Path) -> None:
    from PIL import Image
    Image.open(src).convert("RGB").quantize(colors=128, method=Image.Quantize.MEDIANCUT,
                                            dither=Image.Dither.NONE).save(out, optimize=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", type=Path, default=RUN, help="the recorded run's db (default: %(default)s)")
    ap.add_argument("--only", nargs="*", help="these shots of SHOTS only")
    ap.add_argument("--frame", nargs=4, metavar=("DB", "T", "SHOT", "PNG"), help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.frame:
        db, T, name, out = a.frame
        return frame(Path(db), T, SHOTS[name], Path(out))
    if not a.run.exists():
        sys.exit(f"no run at {a.run} — pass --run <a recorded run's db>")
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is not on PATH")
    times = moments(a.run)
    last = times[-1]
    work = Path(tempfile.mkdtemp(prefix="gfso-media-frames-"))
    for name, shot in SHOTS.items():
        if a.only and name not in a.only:
            continue
        ts = times if shot["film"] else [last]
        frames = []
        for i, T in enumerate(ts):
            f = work / f"{Path(name).stem}-{i:03d}.png"
            subprocess.run([sys.executable, __file__, "--frame", str(a.run), T, name, str(f)], check=True)
            frames.append(f)
            print(f"{name}: {i + 1}/{len(ts)} {T}", flush=True)
        (gif if name.endswith(".gif") else lambda fs, o: png(fs[-1], o))(frames, DOCS / name)
        print(f"{name}: {(DOCS / name).stat().st_size // 1024} KB", flush=True)
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
