"""The seam holds its agent: a Claude Code Stop hook that turns back every stop of a console while the frontier gives
its signer a move of its own, naming those moves — the frontier's directives, verbatim, the most urgent first. An
executor moves by signals alone — ACCEPT, CHALLENGE, BLOCK, DELIVER, CONFIRM_CANCEL (§11.2) —, none of them "stop", and
every live state has an owner with a move (§12.13 Inv-8): the way out is a move, which takes the step off the frontier,
and a question to the person is a CHALLENGE or a BLOCK on the node. No counter of its own: it lets go only where no move
is the console's.

Whose moves it reads is the console's signer — the name its connection took, `user` among them (`act_as`, its log-in)
— through one GET that marks nothing (`GET /api/steps`, `tools_llm.held_steps`), signed as the console's own
connection (`signin.credential_header`). The frontier alone decides: a move that is the person's (`persons`, where the
door would ask his words, `tools.persons_move`), optional or another party's (a customer's in `auto`: the mode gives
them to the system), the observation of a delivery (the seam's validator's step: once delivered, the holder owes
nothing), a stopped run, a settled root, a subagent's stop or a driven CLI hold nothing, nor does a
connection whose taken name was refused or a console that signs as no one (no gfso connection, or one that took no
name); with no server, or no such
project, it says so and lets the console stop. At or above a fill ceiling (`CEILING`, 75% unless `--ceiling` says
otherwise, 0 off; the window the statusline's measure, else `--window`, else `CLAUDE_CTX_WINDOW`, never guessed — with
none it is inert) it lets this one stop through, recording nothing, so a session can close; the next console is held
again. It signals nothing and writes nothing; a run that fails says nothing. The person installs it, in one place
(`gfso hold <project> --install`).

One live connection holds a name, his own as any other: of two consoles of his, the one logged in as `user` is held
on his solo root's moves, the other reads."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from gfso import serverctl, signin
from gfso.config import ctx_window, driven_cli
from gfso.engine.frontier import OBSERVE
from gfso.witness import hook_command, write_hooks

MARK = "gfso.hold"
#: the hook's own bound in Claude Code: one local read of 5 s, well under the 600 s default
TIMEOUT_S = 15
#: the most ids one reminder names in a list; its length, and a rework line's directive head
SHOWN, CAP, GIST = 3, 800, 100
#: the statusline's measure when present — Claude Code hands the window to the statusline, never to a hook: one file a
#: session, {size, used, ts}, read while fresh
STATUSLINE, FRESH_S = Path.home() / ".claude" / "ctx", 120
#: the fill, in percent, past which a stop goes through so a session can close — the person's number; 0 turns it off
CEILING = 75.0


def _ask(project: str) -> dict:
    """The server's frontier for this console (`GET /api/steps`), signed as its own connection."""
    req = urllib.request.Request(f"{serverctl.BASE}/api/steps?project={urllib.parse.quote(project)}",
                                 headers=signin.credential_header())
    return json.loads(urllib.request.urlopen(req, timeout=5).read() or b"null") or {}


def used(transcript_path) -> int | None:
    """The tokens in the window: the usage of the transcript's last main-chain assistant record; None where it cannot be
    read."""
    try:
        with open(transcript_path, "rb") as f:
            f.seek(max(0, f.seek(0, 2) - 400_000))
            lines = f.read().decode("utf-8", "replace").splitlines()
    except (OSError, TypeError):
        return None
    for line in reversed(lines):
        try:
            d = json.loads(line) if '"usage"' in line else {}
        except ValueError:
            continue
        u = ((d.get("message") or {}).get("usage") or {}) if d.get("type") == "assistant" and not d.get("isSidechain") \
            else {}
        if n := sum(u.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")):
            return n
    return None


def measured(event: dict, window: int | None = None) -> float | None:
    """How full the console's window is, in percent, on known numbers only: the statusline's measure when present and
    fresh (`STATUSLINE`, its `size` and `used`), else the window given at install, else `CLAUDE_CTX_WINDOW`, the tokens
    from the transcript; None where either is unknown — never a guessed window."""
    try:
        sl = json.loads((STATUSLINE / f"{event.get('session_id')}.json").read_text(encoding="utf-8"))
        sl = sl if time.time() - float(sl.get("ts") or 0) <= FRESH_S else {}
    except (OSError, ValueError, TypeError, AttributeError):
        sl = {}
    w = sl.get("size") or window or ctx_window()
    n = sl.get("used") or used(event.get("transcript_path"))
    return n * 100.0 / w if w and n else None


def decide(event: dict, project: str, ask=_ask, ceiling: float = CEILING, window: int | None = None) -> dict:
    """What the hook answers Claude Code for one Stop: `{}` to let it stop, or `{"decision": "block", "reason": …}`
    naming the console's own moves."""
    if event.get("agent_id") or driven_cli():
        return {}
    if ceiling and (pct := measured(event, window)) is not None and pct >= ceiling:
        return {}
    try:
        out = ask(project)
    except urllib.error.HTTPError as e:
        return {"systemMessage": f"no project {project} on the server" if e.code == 404 else
                                 f"gfso refused the read of {project} ({e.code})"}
    except (OSError, ValueError):
        return {"systemMessage": "gfso not reachable"}
    if out.get("refused"):
        return {"systemMessage": f"seam not held: this console's gfso connection signs as no one — {out['refused']}"}
    if out.get("unsigned"):
        return {"systemMessage": "seam not held: this console signs as no one — no gfso connection, or one that has "
                                 "taken no name (`act_as('user')` logs it in)"}
    run, own = (out.get("run") or {}).get("state"), own_moves(out)
    if out.get("complete") or run in ("stopping", "stopped") or not own:
        return {}
    return {"decision": "block", "reason": reminder(own, out.get("current"), project)}


def own_moves(out: dict) -> list:
    """The steps of a frontier (`next_steps`) that are its reader's own moves: its own, not optional, not the person's
    (`persons`), not the system's observation of a delivery, not an offer — what holds its stop, and its log-out
    (`act_as('')`). An offer binds no one until ACCEPT (Inv-1) and abstention discharges it, the offer lapsing to its
    issuer (§12.9's named exception): 243 standing offers held a stream's console in a loop (the author, 2026-11-21:
    «это жду по кругу не должно ходить»)."""
    return [s for s in out.get("steps") or () if s.get("mine") and not s.get("optional") and not s.get("persons")
            and s.get("state") != "OFFERED" and not str(s.get("directive") or "").startswith(OBSERVE)]


def reminder(own: list, current, project: str) -> str:
    """The moves of the console's own, ranked off the log, in at most `CAP` characters and one directive whole: the task
    it is on — the node of its latest move, while it owes one there — else the frontier's most urgent; then each node a
    FAIL sent back, one line; then the rest named in one."""
    head = next((s for s in own if s.get("task_id") == current), None)
    first = head or own[0]
    others = [s for s in own if s is not first]
    back = [s for s in others if s.get("state") == "REWORKING"][:SHOWN]
    rest = [str(s.get("task_id")) for s in others if s not in back]
    top = f"Not handed in, in {project} — stopping is no move; make one (DELIVER, CHALLENGE, BLOCK …)."
    lead = f"{'You are on' if head else 'The most urgent:'} {first.get('task_id')}: "
    tail = [f"- {s.get('task_id')} back in rework: {_gist(s.get('directive'))}" for s in back]
    tail += [f"and {len(rest)} more open: {', '.join(rest[:SHOWN])}{' …' if len(rest) > SHOWN else ''}"] if rest else []
    d, room = str(first.get("directive") or ""), CAP - len(top) - len(lead) - sum(len(x) + 1 for x in tail) - 1
    if len(d) > room:                 # …the one directive whole where it fits, else its head and where it is whole
        d = d[:max(room - 60, 0)] + f"… — `get_task('{first.get('task_id')}')` holds it whole"
    return "\n".join([top, lead + d, *tail])


def _gist(directive) -> str:
    """A directive's head: its first sentence, cut short — what failed, where a FAIL sent the node back."""
    d = str(directive or "").split("\n")[0]
    return d if len(d) <= GIST else d[:GIST - 1] + "…"


def install(top: Path, project: str, remove: bool = False, ceiling: float = CEILING, window: int | None = None) -> str:
    """This hook for `project` written into (or taken out of) the settings file of the place at `top`, kept out of git;
    any earlier one of the project there replaced. Run twice, one entry. Said where the ceiling may stand on no
    window."""
    cmd = hook_command(MARK, project, "--ceiling", f"{ceiling:g}", *(["--window", str(int(window))] if window else []))
    ours = re.compile(rf"-m {re.escape(MARK)} {re.escape(project)}(\s|$)").search
    path = write_hooks(top, ours, {} if remove else {
        "Stop": {"hooks": [{"type": "command", "command": cmd, "timeout": TIMEOUT_S}]}})
    inert = (f"\nthe ceiling of {ceiling:g}% stands on the statusline's measure of the window; where there is none it "
             f"is inert — give --window <tokens> (or set CLAUDE_CTX_WINDOW)"
             if ceiling and not remove and not (window or ctx_window()) else "")
    return f"{'removed from' if remove else 'installed in'} {path} for project {project}{inert}"


def main() -> None:
    """One hook run: the project (`--ceiling`, `--window`) in argv, the Stop on stdin, the answer on stdout, exit 0
    whatever happened."""
    try:
        a = sys.argv[1:]
        opt = lambda k, d=None: float(a[a.index(k) + 1]) if k in a else d
        if out := decide(json.load(sys.stdin), a[0], ceiling=opt("--ceiling", CEILING), window=opt("--window")):
            print(json.dumps(out))
    except BaseException:
        pass                          # …a hook that errors breaks the person's console: it lets it stop
    sys.exit(0)


if __name__ == "__main__":
    main()
