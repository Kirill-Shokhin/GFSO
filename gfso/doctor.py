"""What this installation is, whether it can work, and the one command that makes it work.

Two commands live here, and they exist for the same reason: every failure this product has on a
machine that is not the author's is SILENT. A port held by something else answers the liveness probe
and the launcher reports success. A missing Claude Code CLI degrades the LLM to a stub, so a
decomposition comes back empty instead of refused. State follows the working directory, so the
graphs of yesterday are simply not in today's list. None of these raise; all of them look like the
product working badly rather than like a machine misconfigured — so the first thing a stranger needs
is not another feature but a report they can read and paste.

`doctor` states the facts and exits non-zero when one of them blocks work. `setup` performs the two
acts a first install needs — register the agent door, bring the server up — and then calls `doctor`,
because a setup that cannot say what it achieved is the same silence one layer up.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
import webbrowser
from pathlib import Path

from gfso import __version__
from gfso import serverctl
from gfso import config as _config
from gfso.config import db_path as _config_db_path
from gfso.config import LOOPBACK as _LOOPBACK


def _address() -> tuple[str, int]:
    return serverctl.BASE, serverctl.PORT


def port_state() -> tuple[str, str]:
    """(state, detail) — `free`, `gfso`, or `foreign`.

    The distinction the launcher does not make: an OPEN port is not a running gfso. When something
    else holds it, `ensure_server` sees a live socket, spawns nothing, and reports the server
    started — measured: 114 seconds of silence and then a success line quoting a code fingerprint
    for a process that does not exist.
    """
    base, port = _address()
    if not serverctl.port_open(_LOOPBACK, port, timeout=1.0):
        return "free", f"nothing is listening on :{port}"
    if serverctl.runtime() is not None:
        return "gfso", f"a gfso server answers at {base}"
    return "foreign", (f":{port} is held by another process ({_port_holder(port)}) that is not a "
                       f"gfso server — stop it, or point GFSO_SHARED_URL elsewhere")


def _port_holder(port: int) -> str:
    """Best effort, and honest when it fails: naming the process is a convenience, not a contract.

    Every child read here names its encoding. `text=True` alone decodes with the console code page,
    and a single byte outside it raised UnicodeDecodeError *inside the diagnostic* — the one command
    whose whole job is to still work when everything else does not.
    """
    try:
        if os.name == "nt":
            out = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=10).stdout
            pids = {line.split()[-1] for line in out.splitlines()
                    if f":{port} " in line and "LISTENING" in line}
            if pids:
                pid = pids.pop()
                name = subprocess.run(["tasklist", "/fi", f"pid eq {pid}", "/nh"],
                                      capture_output=True, text=True, encoding="utf-8",
                                      errors="replace", timeout=10).stdout.split()
                return f"pid {pid}" + (f", {name[0]}" if name else "")
        else:
            pid = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                                 capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=10).stdout.split()
            if pid:
                return f"pid {pid[0]}"
    # who holds the port is a DIAGNOSTIC FIELD — no tasklist/lsof, or one that refuses, gives "pid
    # unknown" below; it must not stop the report the user ran this for
    except Exception:
        pass
    return "pid unknown"


def claude_cli() -> tuple[bool, str]:
    """Is the Claude Code CLI usable? Every LLM role in this product rides it over subprocess.

    Only reachability is checked, never a completion: a probe that asks the model a question costs
    the user tokens for a diagnostic. A CLI that is present but signed out therefore reads as found
    here and fails later — which is why the AI verbs report the provider's silence themselves.
    """
    exe = shutil.which("claude")
    if exe is None:
        return False, ("not on PATH — install Claude Code (https://claude.com/claude-code), or set "
                       "GFSO_PROVIDER=generic with GFSO_GENERIC_BASE_URL for an OpenAI-compatible one")
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30)
        if out.returncode == 0:
            return True, (f"{out.stdout.strip() or 'present'} ({exe}) — reachable; whether it is "
                          "signed in is not checked here, and an AI verb will say so if it is not")
        return False, f"found at {exe} but `claude --version` exited {out.returncode}"
    except Exception as ex:
        return False, f"found at {exe} but did not answer ({type(ex).__name__})"


def mcp_registered() -> tuple[bool | None, str]:
    """Is the agent door registered with Claude Code? None = cannot tell (no CLI to ask).

    The answer is relative to the directory this runs in: a project-scoped registration is real
    inside its own tree and absent everywhere else, which is exactly why `setup` registers at user
    scope. So a "not registered" here means "not reachable from here", which is the useful reading.
    """
    exe = shutil.which("claude")
    if exe is None:
        return None, "no claude CLI to ask"
    try:
        # `claude mcp list` STARTS every configured server to report on it — including this one,
        # whose entry point reconciles THE one server to the probing process's environment. So a
        # `gfso doctor` inside a test suite (temporary home) took the live server down and left its
        # own in its place, twice killing a measurement run. A question may not have that effect;
        # the child is told so.
        out = subprocess.run([exe, "mcp", "list"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30,
                             env=_config.child_env(GFSO_NO_RECONCILE="1"))
        if out.returncode != 0:
            return None, f"`claude mcp list` exited {out.returncode}"
        return ("gfso" in out.stdout), ("registered" if "gfso" in out.stdout else
                                        "not registered — run `gfso setup`")
    except Exception as ex:
        return None, f"could not ask the CLI ({type(ex).__name__})"


def _assets_ok() -> tuple[bool, str]:
    """The eleven files the wheel must carry. A missing one breaks a door with no error at the door."""
    pkg = Path(__file__).parent
    required = ("web/index.html", "web/gfso.css", "web/tokens.css", "web/icon.svg",
                "mcp/ORCHESTRATOR.md", "mcp/prompts/executor.md", "mcp/prompts/validator.md",
                "decompose/prompts/search.md", "decompose/prompts/audit.md",
                "critic/prompts/atomicity.md", "critic/prompts/checker.md")
    missing = [r for r in required if not (pkg / r).exists()]
    return (not missing), ("all present" if not missing else f"MISSING {missing} — reinstall gfso")


def _database_path() -> str:
    """The file the engine WOULD open — through the same resolution the engine uses.

    It was composed here by hand as `home/data/gfso.db`, which ignores `GFSO_DB_PATH` and
    `GFSO_DATA_DIR`; measured with a `GFSO_DB_PATH` on another drive, doctor named the home path
    while the server died on the real one. A diagnostic that composes its own answer is the class
    this module exists to close.
    """
    return str(_config_db_path())


def _home_report() -> tuple[bool, str, Path]:
    home = serverctl.home()
    why = ("GFSO_HOME" if os.environ.get("GFSO_HOME") else
           "a source checkout — state stays in the tree" if (home / "pyproject.toml").exists() else
           "the default for an installed package")
    try:
        (home / "data").mkdir(parents=True, exist_ok=True)
        probe = home / "data" / ".writable"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True, f"{home}  ({why})", home
    except OSError as ex:
        return False, f"{home}  ({why}) — NOT WRITABLE: {ex}", home


def _print_report(serverctl, home_line, assets_line, port_line, claude_line, reg_line,
                  live_notes, live, has_claude, home, script) -> None:
    """Print what this installation IS — one aligned row per fact.

    `doctor` does two things: it establishes the facts (home, assets, port, CLI, registration,
    what the live server is serving) and it prints them. The printing is the part a bug report
    carries, so it is its own function and reads as the report it is."""
    rows = [
        ("gfso", f"{__version__}   (canon v4.0 is a separate line and is not this number)"),
        ("python", f"{platform.python_version()}  {sys.executable}"),
        ("executable", f"{script}" + ("" if script.exists() else "   MISSING")),
        ("platform", f"{platform.system()} {platform.release()}"),
        ("state home", home_line),
        ("database", _database_path()),
        ("address", f"{serverctl.BASE}  — {port_line}"),
        ("live server", "; ".join(live_notes) if live_notes else
         ("matches this installation" if live else "none running")),
        ("assets", assets_line),
        ("claude CLI", claude_line if has_claude else f"NOT USABLE — {claude_line}"),
        ("agent door", reg_line),
    ]
    width = max(len(k) for k, _ in rows)
    print("gfso doctor")
    for key, value in rows:
        print(f"  {key.ljust(width)}  {value}")


def _live_server_report(serverctl, home) -> tuple[dict, list[str], list[str]]:
    """What the LIVE server is, when it is not what this installation would start.

    Not the same question as "what would this process do": a server started from a different
    installation serves a different database, and a diagnostic that prints its own paths as if they
    were the server's asserts a lie with a straight face. Returns (runtime, the notes, the drift line).
    """
    live = serverctl.runtime() or {}
    notes: list[str] = []
    if not live:
        return live, notes, []
    if live.get("version") and live["version"] != __version__:
        notes.append(f"it is version {live['version']}, this is {__version__}")
    if live.get("home") and Path(live["home"]) != home:
        notes.append(f"its state home is {live['home']}, not this one")
    if live.get("code_version") and live["code_version"] != serverctl.source_fingerprint():
        notes.append("it is running older code than is installed — `gfso up` reconciles it")
    if live.get("with_mcp") is False:
        notes.append("it has NO agent door mounted — agent sessions will not reach it")
    if not notes:
        return live, notes, []
    # DRIFT IS NOT A BLOCK. A server running older code answers every verb — the product works — and
    # calling that "blocking" made a first-time user believe nothing would work and reach for
    # `gfso up`, which restarts a server that may be carrying someone else's live runs (measured
    # 2026-08-21: "I was wrong — everything worked"). What STOPS the product and what is merely out
    # of date are two different lines.
    return live, notes, ["the running server is not this installation (" + "; ".join(notes)
                         + "). Everything still works; `gfso up` reconciles it, and refuses while "
                           "another session's run is in flight"]


def doctor() -> int:
    """Print the state of this installation; exit non-zero if something blocks work."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # a non-console host has nothing to reconfigure — the report below prints either way

    blocking: list[str] = []
    drift: list[str] = []      # true, and in nobody's way
    home_ok, home_line, home = _home_report()
    assets_ok, assets_line = _assets_ok()
    port, port_line = port_state()
    has_claude, claude_line = claude_cli()
    registered, reg_line = mcp_registered()

    if not home_ok:
        blocking.append("state directory is not writable")
    if not assets_ok:
        blocking.append("runtime assets are missing from the installation")
    if port == "foreign":
        blocking.append("the address is held by something that is not gfso")

    script = console_script()
    if not script.exists():
        blocking.append("the gfso executable is not where this installation says it is")

    live, live_notes, live_drift = _live_server_report(serverctl, home)
    drift += live_drift

    _print_report(serverctl, home_line, assets_line, port_line, claude_line, reg_line,
                  live_notes, live, has_claude, home, script)

    if not has_claude:
        print("\nThe engine, the UI, the gate and `gfso demo human_only` work without any model.")
        print("What needs the Claude Code CLI: auto_decompose, review_decomposition,")
        print("validate_result, and delegation to agent executors.")
    if drift:
        print("\nout of date (not blocking): " + "; ".join(drift))
    if blocking:
        print("\nblocking: " + "; ".join(blocking))
        return 1
    return 0


def desktop_config_path() -> Path | None:
    """Where Claude Desktop keeps its configuration on this platform, if it is installed here."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Claude"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Claude"
    else:
        base = Path.home() / ".config" / "Claude"
    return base if base.is_dir() else None


def desktop_entry() -> dict:
    """The `mcpServers` entry Claude Desktop needs for this installation.

    `GFSO_HOME` is named outright because Desktop starts its servers in a directory of its own
    choosing, and the command is the absolute console script because Desktop resolves no PATH of
    ours. Built as a dict and rendered by a JSON encoder — interpolated by hand, a Windows path is
    not JSON, and the block offered for pasting could not be parsed by the application it was for.
    """
    env = {"GFSO_HOME": str(serverctl.home())}
    if os.environ.get("GFSO_SHARED_URL"):
        # Desktop inherits no shell environment, so an address that is not the default has to be
        # written into the entry or its `gfso connect` would go on talking to :8000.
        env["GFSO_SHARED_URL"] = os.environ["GFSO_SHARED_URL"]
    return {"command": str(console_script()), "args": ["connect"], "env": env}


def console_script() -> Path:
    """The absolute path of THIS installation's `gfso` executable.

    THIS installation's, not whatever the PATH happens to resolve. Two wrong answers were measured
    on the way here: `Path(sys.executable).parent / "gfso"` names a file that does not exist outside
    a virtualenv (on conda, a python.org install or `pip install --user`, scripts live in a separate
    directory), and `shutil.which` names a DIFFERENT installation whenever one is earlier on PATH —
    it reported the development copy while running from a freshly installed venv. Claude Desktop,
    handed either, starts a server that is not this one, or none at all.

    So: this interpreter's own scripts directory, and `which` only as the fallback for an
    installation whose layout `sysconfig` does not describe.
    """
    name = "gfso.exe" if sys.platform == "win32" else "gfso"
    mine = Path(sysconfig.get_path("scripts")) / name
    if mine.exists():
        return mine
    found = shutil.which("gfso")
    return Path(found) if found else mine


def install_desktop() -> str:
    """Merge the gfso entry into `claude_desktop_config.json`, keeping a backup. Returns a report.

    This edits another application's file, so it happens only when asked for by name
    (`gfso setup --desktop`): the existing configuration is read, only the `mcpServers.gfso` key is
    touched, and the previous file is kept beside it as `.gfso-backup`. Claude Desktop reads the
    file at start, so it has to be restarted afterwards.
    """
    base = desktop_config_path()
    if base is None:
        return "Claude Desktop does not appear to be installed for this user — nothing written."
    path = base / "claude_desktop_config.json"
    try:
        current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(current, dict):
            return f"{path} does not contain a JSON object — left untouched."
    except (OSError, ValueError) as ex:
        return f"{path} could not be read ({ex}) — left untouched; paste the block above by hand."
    entry = desktop_entry()
    if current.get("mcpServers", {}).get("gfso") == entry:
        return f"Claude Desktop: already configured ({path})."
    if path.exists():
        # The FIRST backup is the one worth having — it is the file as the user wrote it. Overwriting
        # it on every later run would mean a second `--desktop` (after gfso had already edited the
        # file once) replaces the user's original with our own output, and the restore instruction in
        # the README then restores nothing.
        backup = base / "claude_desktop_config.json.gfso-backup"
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
    current.setdefault("mcpServers", {})["gfso"] = entry
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return (f"Claude Desktop: written to {path} (previous file kept as "
            f"claude_desktop_config.json.gfso-backup). Restart Desktop to load it.")


def setup(desktop: bool = False) -> int:
    """Register the agent door, bring the one server up, open the UI, then report. Idempotent."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # as in `doctor`: nothing to reconfigure is not a failed setup

    port, port_line = port_state()
    if port == "foreign":                      # refuse rather than spend two minutes proving it
        print(f"gfso setup: {port_line}")
        return 1

    exe = shutil.which("claude")
    if exe is None:
        print("Claude Code CLI not found, so the agent door was not registered. After installing it:")
        print(f"  claude mcp add --scope user gfso -- {console_script()} connect")
    else:
        registered, _ = mcp_registered()
        if registered:
            print("agent door: already registered with Claude Code")
        else:
            # --scope user, deliberately. `claude mcp add` defaults to the project the caller stands
            # in, and this door is not a property of one repository: registered locally, it is
            # invisible from every other directory — measured, while a `claude mcp list` run inside
            # the source tree reported it connected.
            # The ABSOLUTE console script, not the bare name: a user-scoped registration is used
            # from every directory and from clients that do not share this PATH — `pip install
            # --user` on Windows puts Scripts\ off PATH entirely, and a venv the user later leaves
            # takes the name with it. The entry would then name a command that does not resolve,
            # and the session would simply have no gfso tools, silently.
            out = subprocess.run([exe, "mcp", "add", "--scope", "user", "gfso", "--",
                                  str(console_script()), "connect"],
                                 capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=120)
            print("agent door: " + ("registered for your user, so it is there in every directory"
                                    if out.returncode == 0 else
                                    f"could not register ({out.stderr.strip()[:200]}); "
                                    f"run `claude mcp add --scope user gfso -- "
                                    f"{console_script()} connect` yourself"))

    # Claude Desktop is a separate application with a configuration file of its own, so it is
    # written ONLY when named: `--desktop`. Otherwise the block is printed and the user decides.
    if desktop:
        print("\n" + install_desktop())
    elif desktop_config_path() is not None:
        print("\nClaude Desktop is installed here. `gfso setup --desktop` adds this to its"
              "\nclaude_desktop_config.json (keeping a backup), or paste it yourself:")
        print(json.dumps({"mcpServers": {"gfso": desktop_entry()}}, indent=2))

    # LEFT: `gfso.mcp.connect` imports the third-party `mcp` SDK at module level, and doctor is
    # the command that must still run on an installation where that dependency is missing.
    from gfso.mcp.connect import ensure_correct
    ensure_correct()
    print(f"\nThe UI is at {serverctl.BASE} — the same graphs, whichever door you came in by.")
    try:
        webbrowser_open(serverctl.BASE)
    # the UI address is printed above; a box with no browser to open is a missing convenience, not a
    # broken install
    except Exception:
        pass
    print()
    return doctor()


def webbrowser_open(url: str) -> None:
    """Open the UI in the machine's browser, if this machine has one to open."""
    webbrowser.open(url)
