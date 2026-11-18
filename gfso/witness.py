"""The console's witness: a Claude Code hook that, after each tool call, tells the system when the call changed its
repository's working tree, and the agent what the system answered (`past.witness`: recorded where no node of the
project is at work in that repository — «take the node or stop»). It asks one fact and judges none: git's own status
of the tree, each path it names with its size and mtime, read before the call (`PreToolUse`) and after it (`PostToolUse`,
`PostToolUseFailure` — a call that failed may have written), paired by the call's own id, so a person's edit between two
calls is no call's. A write by Bash is seen because the tree is compared, not the command; a checkout, a pull or a merge
that leaves the tree clean changes no status line and is no write. It never blocks: no exit 2, no `decision`.

The person installs it, for one project, in one repository (`gfso witness <project> --install`): into that repository's
own `.claude/settings.local.json`, kept out of git (the command names this machine's interpreter), and recorded in the
state directory as the project working there (`INSTALLED`); nothing installs it for them. A run that fails in any way says nothing: a hook that raises breaks the person's console."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from gfso import serverctl, signin
from gfso.adapters import children
from gfso.config import data_dir

#: the system's own door: a move through it is in the log already, and what it writes is the system's
OWN_DOOR = "mcp__gfso__"
#: what identifies this hook's entries in a settings file, among the person's own
MARK = "gfso.witness"
EVENTS = ("PreToolUse", "PostToolUse", "PostToolUseFailure")
#: how long a reading before a call waits for the call's end: one denied or cut short has none
KEPT_S = 86400
#: the settings file it is installed in, under the repository's top
SETTINGS = Path(".claude") / "settings.local.json"
#: the person's record, in the state directory, of the repositories they installed it in, per project: where a project
#: works by their act (`past.spans`), never by what a call names
INSTALLED = "witness.json"


def git(cwd, *args) -> str | None:
    """What git prints for `args` in `cwd`, or None wherever it fails — taking no optional lock: a status beside the
    console's own `git commit` would hold the index's lock it needs, and write the index."""
    try:
        r = children.run(["git", "--no-optional-locks", "-C", str(cwd), *args], timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None


def tree(top: Path) -> dict:
    """{path: [status, size, mtime]} of every path git's status names in the tree at `top`: a file already modified and
    written again changes no status line, only its stat."""
    parts, out, i = (git(top, "status", "--porcelain=v1", "-z", "--untracked-files=all") or "").split("\0"), {}, 0
    while i < len(parts):
        if len(e := parts[i]) > 3:
            try:
                st = os.stat(top / e[3:])
                out[e[3:]] = [e[:2], st.st_size, st.st_mtime_ns]
            except OSError:
                out[e[3:]] = [e[:2]]
            i += e[0] in "RC"         # …a rename's or copy's source follows it
        i += 1
    return out


def _ask(project: str, body: dict) -> dict:
    """The server's answer (`POST /api/witness`), with this console's credential."""
    req = urllib.request.Request(f"{serverctl.BASE}/api/witness", method="POST",
                                 data=json.dumps({"project": project, **body}).encode(),
                                 headers={"Content-Type": "application/json", **signin.credential_header()})
    return json.loads(urllib.request.urlopen(req, timeout=5).read() or b"null") or {}


def observe(event: dict, project: str, ask=_ask) -> dict:
    """What the hook answers Claude Code for one event: `{}`, or the line for the agent."""
    cwd, kind = event.get("cwd") or os.getcwd(), event.get("hook_event_name")
    top, gitdir = git(cwd, "rev-parse", "--show-toplevel"), git(cwd, "rev-parse", "--absolute-git-dir")
    if not (top and gitdir) or kind not in EVENTS or str(event.get("tool_name", "")).startswith(OWN_DOOR):
        return {}
    top = Path(top.strip())
    state = Path(gitdir.strip()) / "gfso-witness" / (re.sub(r"[^\w.-]", "_", str(event.get("tool_use_id"))) + ".json")
    if kind == "PreToolUse":
        state.parent.mkdir(parents=True, exist_ok=True)
        _drop_stale(state.parent)
        state.write_text(json.dumps(tree(top)), encoding="utf-8")
        return {}
    try:
        before = json.loads(state.read_text(encoding="utf-8"))
        state.unlink()
    except (OSError, ValueError):
        return {}                     # …no reading before this call: nothing to compare
    now = tree(top)
    if not (paths := sorted(p for p in before.keys() | now.keys() if before.get(p) != now.get(p))):
        return {}
    key = hashlib.sha256(json.dumps([[p, now.get(p)] for p in paths]).encode()).hexdigest()   # …one write, however
    said = ask(project, {"repository": str(top), "tool": event.get("tool_name"), "paths": paths,   # many calls saw it
                         "key": key}).get("say")
    return {"hookSpecificOutput": {"hookEventName": kind, "additionalContext": said}} if said else {}


def _drop_stale(d: Path) -> None:
    """The readings in `d` older than `KEPT_S` removed, whatever fails."""
    for f in d.glob("*.json"):
        try:
            if time.time() - f.stat().st_mtime > KEPT_S:
                f.unlink()
        except OSError:
            pass                      # …one gone already or held open: the next call's pruning takes it


def install(top: Path, project: str, remove: bool = False) -> str:
    """This hook for `project` written into (or taken out of) the repository's own settings file at `top`, the person's
    own entries kept, the file kept out of git. Run twice, one entry."""
    path, cmd = top / SETTINGS, f'"{Path(sys.executable).as_posix()}" -m {MARK} {project}'
    s = json.loads(path.read_text(encoding="utf-8") or "{}") if path.exists() else {}
    hooks = s.setdefault("hooks", {})
    for ev in list(hooks):
        hooks[ev] = [g for g in ({**g, "hooks": [h for h in g.get("hooks", []) if h.get("command") != cmd]}
                                 for g in hooks[ev]) if g["hooks"]]
        if not hooks[ev]:
            del hooks[ev]
    if not remove:
        for ev in EVENTS:
            hooks.setdefault(ev, []).append({"matcher": "*", "hooks": [{"type": "command", "command": cmd}]})
    if not hooks:
        del s["hooks"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(s, indent=2) + "\n", encoding="utf-8")
    if git(top, "check-ignore", "-q", str(SETTINGS)) is None and (common := git(top, "rev-parse", "--git-common-dir")):
        exclude = (top / common.strip()) / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with open(exclude, "a", encoding="utf-8") as f:
            f.write(f"\n/{SETTINGS.as_posix()}\n")
    _record(project, str(top), remove)
    return f"{'removed from' if remove else 'installed in'} {path} for project {project}"


def installed() -> dict:
    """{project: [the tops of the repositories the person installed its hook in]}, as `install` recorded them."""
    try:
        return json.loads((data_dir() / INSTALLED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _record(project: str, top: str, remove: bool) -> None:
    rec = installed()
    tops = [t for t in rec.get(project, []) if t != top] + ([] if remove else [top])
    rec = {**rec, project: tops} if tops else {p: t for p, t in rec.items() if p != project}
    (data_dir() / INSTALLED).parent.mkdir(parents=True, exist_ok=True)
    (data_dir() / INSTALLED).write_text(json.dumps(rec, indent=2), encoding="utf-8")


def main() -> None:
    """One hook run: the project in argv, the event on stdin, the answer on stdout, exit 0 whatever happened."""
    try:
        if out := observe(json.load(sys.stdin), sys.argv[1]):
            print(json.dumps(out))
    except BaseException:
        pass                          # …a hook that errors breaks the person's console: the witness stays silent
    sys.exit(0)


if __name__ == "__main__":
    main()
