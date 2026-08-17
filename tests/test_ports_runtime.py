"""ClockPort + RunnerPort — the runtime substrate is swappable WITHOUT touching the core.

Three proofs: (1) a FAKE clock drives Inv-5 state-age timeouts in milliseconds of real time
(an HOUR of virtual staleness — no sleep-based test could afford that); (2) the RunnerPort is
the real spawn seam Engine.start goes through; (3) an asyncio host drives `process_signal`
directly from its own loop — no engine thread, no blocking queue — and the FSM/mutations
underneath behave identically.
"""
import os
import pathlib
import sys
import time

from gfso.engine import Engine
from gfso.engine.loop import process_signal
from gfso.engine.audit import AuditLog
from gfso.engine.events import EventBus
from gfso.adapters.storage.memory import MemoryStorage
from gfso.adapters.agents.human import HumanAgent
from gfso.core.graph import Graph
from gfso.core.types import (
    TaskId, AgentId, Spec, Criteria, Signal, SignalData, ClockPort, ThreadRunner,
)
from gfso import tools as T


class FakeClock(ClockPort):
    """Virtual time: wait() advances the clock instantly (plus a GIL yield). Starts at the real
    epoch so ages computed against datetime-stamped graph fields stay meaningful."""

    def __init__(self):
        self._t = time.time()

    def now(self) -> float:
        return self._t

    def wait(self, seconds: float) -> None:
        self._t += seconds
        time.sleep(0.001)


def _mk(e, tid="n"):
    T.create_task(e, tid, {"description": "x", "criteria": [{"name": "a", "description": "A"}]}, "w")
    e.wait_idle()


def _await_state(e, tid, names, timeout=3.0):
    dl = time.time() + timeout
    while time.time() < dl:
        st = e.get_state(TaskId(tid))
        if st and st.name in names:
            return st.name
        time.sleep(0.01)
    return e.get_state(TaskId(tid)).name


def test_fake_clock_drives_inv5_state_age_in_milliseconds():
    """An HOUR-scale state_timeout enforced through virtual time: the deadline-less node cannot
    sit in OFFERED forever; the sub-FSM escalates (first timeout → OVERDUE, repeat → ESCALATED) —
    all in milliseconds of wall time, because Inv-5 reads the ClockPort, not the wall clock."""
    e = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=True,
               check_interval=1800, state_timeout=3600, clock=FakeClock())
    e.start()
    _mk(e)
    got = _await_state(e, "n", {"OVERDUE", "ESCALATED"})
    assert got in ("OVERDUE", "ESCALATED")
    assert _await_state(e, "n", {"ESCALATED"}) == "ESCALATED"   # repeated virtual timeout
    e.stop()


def test_runner_port_is_the_spawn_seam():
    """Engine.start goes through the RunnerPort — a host substrate sees (and owns) both loops."""
    class RecordingRunner(ThreadRunner):
        def __init__(self):
            self.spawned = []

        def spawn(self, target, name: str) -> None:
            self.spawned.append(name)
            super().spawn(target, name)

    r = RecordingRunner()
    e = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=True, runner=r,
               state_timeout=0)
    e.start()
    assert sorted(r.spawned) == ["gfso-event-loop", "gfso-timeout-monitor"]
    _mk(e)                                             # and the engine WORKS over that substrate
    assert e.get_state(TaskId("n")).name == "OFFERED"
    e.stop()


def test_asyncio_host_drives_process_signal_without_engine_threads():
    """The protocol step is substrate-free: an asyncio host pumps its own queue and calls
    process_signal per item — no Engine.start, no thread, no queue.Queue. Same FSM semantics."""
    import asyncio

    storage = MemoryStorage()
    graph, audit, events = Graph(storage), AuditLog(storage), EventBus()
    agents = HumanAgent()

    class Sink:                                        # the host's follow-up-signal sink
        def __init__(self, q):
            self.q = q

        def put(self, item):
            self.q.put_nowait(item)

    async def host():
        q: asyncio.Queue = asyncio.Queue()
        sink = Sink(q)
        w = AgentId("w")
        spec = Spec("x", (Criteria("a", "A"),))
        for sd in (SignalData(signal=Signal.ASSIGN, task_id=TaskId("n"), source=w,
                              spec=spec, assignee=w),
                   SignalData(signal=Signal.ACCEPT, task_id=TaskId("n"), source=w)):
            sink.put(sd)
        n = 0
        while not q.empty():
            sd = await q.get()
            process_signal(sd, graph, agents, None, sink, audit, events, validate=True)
            n += 1
        return n

    processed = asyncio.run(host())
    assert processed >= 2
    assert graph.get_state(TaskId("n")).name == "EXECUTING"    # ASSIGN → OFFERED → ACCEPT → EXECUTING
    assert len([a for a in audit.get_entries(TaskId("n")) if not a.rejected]) == 2


# ── the one server, kept correct by one command ──────────────────────────────────────────────

def test_source_fingerprint_moves_with_the_tree(tmp_path, monkeypatch):
    """"Is the server current" has to be decidable, or it gets decided by hope: a process holds its
    code in memory, so an edited tree never reaches it and a health check cannot tell."""
    from gfso import serverctl

    pkg = tmp_path / "gfso"
    pkg.mkdir()
    (pkg / "a.py").write_text("x = 1", encoding="utf-8")
    monkeypatch.setattr(serverctl, "ROOT", tmp_path)
    first = serverctl.source_fingerprint()
    assert first == serverctl.source_fingerprint()          # stable while nothing changes
    (pkg / "a.py").write_text("x = 2", encoding="utf-8")
    assert serverctl.source_fingerprint() != first          # and moves the moment a source does
    (pkg / "__pycache__").mkdir()
    (pkg / "__pycache__" / "junk.py").write_text("noise", encoding="utf-8")
    assert serverctl.source_fingerprint() != first          # caches are not sources
    assert serverctl.source_fingerprint() == serverctl.source_fingerprint()


def test_drift_names_every_way_the_live_server_can_be_wrong():
    from gfso.serverctl import drift

    env = {"GFSO_VALIDATE_INTERNAL": "1", "GFSO_L2_GATE": "1", "GFSO_AGENTS_PATH": "/reg.json"}
    correct = {"code_version": "abc", "validate_internal": True, "l2_gate": True,
               "agents_path": "/reg.json"}
    assert drift(correct, env, "abc") == []

    assert any("code" in d for d in drift({**correct, "code_version": "old"}, env, "abc"))
    # the one that cost a 25-minute run: a validator registered, and never consulted
    assert any("validate_internal" in d for d in drift({**correct, "validate_internal": False}, env, "abc"))
    assert any("l2_gate" in d for d in drift({**correct, "l2_gate": False}, env, "abc"))
    assert any("registry" in d for d in drift({**correct, "agents_path": "/other.json"}, env, "abc"))
    # a server predating the version stamp reports nothing — that is drift, not a pass
    assert drift({"validate_internal": True, "l2_gate": True, "agents_path": "/reg.json"}, env, "abc")


def test_declared_switches_fill_gaps_but_never_override(tmp_path, monkeypatch):
    """However the server is raised, it comes up declared — and a deliberate value still wins.

    The switches are per-process and decide what a run measures; a hand-typed `serve` used to drop
    them silently, which cost a run 25 minutes of waiting for a verdict that could not come. Arm G⁻
    exports GFSO_L2_GATE=0 on purpose, so filling gaps must not become overriding. Checked on a
    copy of the environment: a test that writes the real one changes what its neighbours measure
    (this one did, and the neighbour went red).
    """
    from gfso import serverctl
    from gfso.serverctl import declared

    # …and read on a home of its own. It used to read the DEVELOPER's `data/serve.json`, which is
    # untracked and machine-local: green on a fresh clone, red on any machine that had declared a
    # different registry for its own runs — a test whose verdict depends on the environment it
    # happens to run in tests the environment, not the code.
    monkeypatch.setattr(serverctl, "home", lambda: tmp_path)

    env = {"GFSO_L2_GATE": "0"}                                # the deliberate one
    for key, value in declared().items():
        env.setdefault(key, value)                             # what `_serve` does
    assert env["GFSO_L2_GATE"] == "0"                          # the decision is kept
    assert env["GFSO_AGENTS_PATH"].endswith("agents.json")     # the gap is filled
    # GFSO_VALIDATE_INTERNAL is NOT a shipped default: it is the measurement dial, and with it on
    # every internal node gets its own validator agent — the opposite of what the protocol handed
    # to an agent says. A run that wants it says so in serve.json, which this proves is honoured.
    assert "GFSO_VALIDATE_INTERNAL" not in declared()
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "serve.json").write_text('{"GFSO_VALIDATE_INTERNAL": "1"}', encoding="utf-8")
    assert declared()["GFSO_VALIDATE_INTERNAL"] == "1"


def test_state_lives_where_it_can_be_written(tmp_path, monkeypatch):
    """The database, the log and the agent registry follow the INSTALLATION, not the package.

    The state root used to be the package's parent directory, which in a source checkout is the
    repository and in a `pip install` is site-packages — so an installed product put the user's
    graphs inside their virtualenv, where the next upgrade removes them and a system-wide install
    cannot write at all. A checkout still keeps its state in the tree; an installed package keeps it
    in ONE home per user, `~/.gfso`.

    The fallback used to be the working directory, and that was the wrong axis: isolation between
    pieces of work is what projects are, and there is only one server to serve them, so a second
    directory got a second database that nothing could reach — silently.
    """
    from gfso import serverctl

    monkeypatch.delenv("GFSO_HOME", raising=False)
    checkout, installed = tmp_path / "checkout", tmp_path / "site-packages"
    for d in (checkout, installed):
        d.mkdir()
    (checkout / "pyproject.toml").write_text("[project]\nname='gfso'\n", encoding="utf-8")

    monkeypatch.setattr(serverctl, "ROOT", checkout)
    assert serverctl.home() == checkout                        # a source tree keeps its own state

    monkeypatch.setattr(serverctl, "ROOT", installed)
    monkeypatch.chdir(tmp_path)
    home = pathlib.Path.home() / ".gfso"
    assert serverctl.home() == home                            # never inside site-packages…
    assert serverctl.home() != pathlib.Path.cwd()              # …and never the caller's directory
    assert serverctl.declared_path().is_relative_to(home)
    assert serverctl.declared()["GFSO_AGENTS_PATH"].startswith(str(home))

    monkeypatch.setenv("GFSO_HOME", str(checkout))
    assert serverctl.home() == checkout                        # and the knob wins over both


def test_the_one_server_has_one_address():
    """`connect`, `down` and `log` read GFSO_SHARED_URL; `up` read a literal 8000 — so the command
    whose entire job is reconciliation could reconcile a server nobody was talking to."""
    import importlib

    from gfso import serverctl

    os.environ["GFSO_SHARED_URL"] = "http://127.0.0.1:8123/mcp"
    try:
        reloaded = importlib.reload(serverctl)
        assert (reloaded.BASE, reloaded.PORT) == ("http://127.0.0.1:8123", 8123)
    finally:
        del os.environ["GFSO_SHARED_URL"]
        importlib.reload(serverctl)
    assert serverctl.BASE == "http://127.0.0.1:8000"           # and the default is unchanged


def test_every_door_puts_state_in_the_home_not_in_the_callers_directory(tmp_path, monkeypatch):
    """The door an agent client runs must honour the home too.

    `GFSO_HOME` was documented for exactly the case where the client picks the working directory
    (Claude Desktop starts its servers wherever it likes) — and `gfso connect` was the one door that
    did not read it: it made `data/`, opened `data/server.log` and passed `--db-path data/gfso.db`,
    all against the caller's cwd, then spawned the server with no `cwd=` at all. Measured before the
    fix: with GFSO_HOME set to one directory, the database appeared in another.
    """
    import subprocess

    from gfso.mcp import connect

    home, elsewhere = tmp_path / "home", tmp_path / "elsewhere"
    for d in (home, elsewhere):
        d.mkdir()
    monkeypatch.setenv("GFSO_HOME", str(home))
    monkeypatch.delenv("GFSO_DB_PATH", raising=False)
    monkeypatch.chdir(elsewhere)

    seen = {}

    class _Popen:
        def __init__(self, argv, **kw):
            seen["argv"], seen["cwd"] = argv, kw.get("cwd")

    monkeypatch.setattr(subprocess, "Popen", _Popen)
    monkeypatch.setattr(connect, "_port_open", lambda *a: False)   # so it takes the spawn path
    connect.ensure_server("http://127.0.0.1:8999/mcp", wait_s=0.0)

    assert pathlib.Path(seen["cwd"]) == home
    db = seen["argv"][seen["argv"].index("--db-path") + 1]
    assert pathlib.Path(db).is_relative_to(home)
    assert (home / "data" / "server.log").exists()
    assert not (elsewhere / "data").exists(), "state landed beside the caller, not in the home"


def test_the_first_install_creates_the_home_instead_of_failing_into_it(tmp_path, monkeypatch):
    """On a machine that has never run gfso, `~/.gfso` does not exist yet.

    `ensure_correct` chdirs into the home so the spawned server resolves its db and log paths there,
    and nothing created that directory first: the chdir raised FileNotFoundError before a server was
    ever spawned. `gfso setup` then died with a traceback instead of printing the report it exists to
    print, and `gfso connect` exited — which an agent client shows as a session with no gfso tools at
    all, silently. Invisible from a source checkout, where the home IS the repository and exists.
    """
    import os
    import subprocess

    from gfso import serverctl
    from gfso.mcp import connect

    # `ensure_correct` writes the declared switches straight into os.environ (the spawn inherits this
    # process's environment), which monkeypatch cannot undo for it — so calling it from a test
    # EXPORTS those switches into every test that runs afterwards. Unrestored, this one turned the
    # session's `GFSO_L2_GATE=0` fixture back on and failed tests in other files.
    home = tmp_path / "never-created"                  # the first-install condition, exactly
    monkeypatch.setenv("GFSO_HOME", str(home))
    monkeypatch.delenv("GFSO_DB_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    assert not home.exists()

    spawned = {}

    class _Popen:                                      # the spawn succeeds; nothing real is started
        def __init__(self, argv, **kw):
            spawned["cwd"] = kw.get("cwd")

    monkeypatch.setattr(subprocess, "Popen", _Popen)
    monkeypatch.setattr(connect, "foreign_holder", lambda *a, **k: None)
    monkeypatch.setattr(connect, "_port_open", lambda *a: bool(spawned))
    monkeypatch.setattr(serverctl, "runtime",
                        lambda *a, **k: {"code_version": serverctl.source_fingerprint(),
                                         "switches": {}, "sessions": 0} if spawned else None)

    saved = dict(os.environ)
    try:
        connect.ensure_correct(verbose=False)
    finally:
        os.environ.clear()
        os.environ.update(saved)

    assert home.is_dir(), "the home was not created — the first install still fails into it"
    assert pathlib.Path(spawned["cwd"]) == home


def test_a_port_held_by_something_else_is_not_a_running_server(monkeypatch):
    """An OPEN port was read as a live server everywhere, so the case that actually happens on a
    stranger's machine — anything else already on :8000 — spawned nothing and reported success.
    Measured before the fix: 114 seconds of silence, then a started line quoting a code fingerprint
    for a process that did not exist."""
    from gfso import serverctl
    from gfso.mcp import connect

    # ONE probe for every caller (`serverctl.port_open`): patched here it answers for `connect` and
    # for `doctor` alike. While there were two implementations this test passed only when some
    # unrelated server happened to hold :8000 on the machine running it — green for a reason that
    # had nothing to do with the code under test.
    monkeypatch.setattr(serverctl, "port_open", lambda *a, **k: True)
    monkeypatch.setattr(serverctl, "runtime", lambda *a, **k: None)   # nothing gfso answers there
    assert connect.foreign_holder("127.0.0.1", serverctl.PORT) is True

    from gfso.doctor import port_state
    state, detail = port_state()
    assert state == "foreign" and "not a gfso server" in detail

    monkeypatch.setattr(serverctl, "runtime", lambda *a, **k: {"code_version": "x"})
    assert connect.foreign_holder("127.0.0.1", serverctl.PORT) is False
    assert port_state()[0] == "gfso"


def test_the_desktop_block_setup_prints_is_json(monkeypatch, capsys, tmp_path):
    """`gfso setup` prints a config block for the user to paste, so it has to BE a config block.

    Built by string interpolation, it was not: on Windows every backslash in the path is a JSON
    escape, so the thing offered for pasting could not be parsed by the application it was for.
    """
    import json

    from gfso import doctor

    monkeypatch.setenv("GFSO_HOME", str(tmp_path))
    monkeypatch.setattr(doctor, "port_state", lambda: ("free", "nothing is listening"))
    monkeypatch.setattr(doctor, "webbrowser_open", lambda url: None)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)   # no claude CLI to register with
    monkeypatch.setattr(doctor, "desktop_config_path", lambda: tmp_path)   # Desktop "installed"
    monkeypatch.setattr("gfso.mcp.connect.ensure_correct", lambda *a, **k: {"action": "none"})
    monkeypatch.setattr(doctor, "doctor", lambda: 0)

    doctor.setup()
    out = capsys.readouterr().out
    block = out[out.index("{"):out.rindex("}") + 1]
    parsed = json.loads(block)                       # the assertion IS the parse
    assert "connect" in parsed["mcpServers"]["gfso"]["args"]
    assert parsed["mcpServers"]["gfso"]["env"]["GFSO_HOME"] == str(tmp_path)


def test_setup_desktop_merges_and_keeps_a_backup(tmp_path, monkeypatch):
    """`--desktop` edits ANOTHER application's file, so what it does has to be exactly this: keep
    every other key, replace only `mcpServers.gfso`, and leave the previous file recoverable."""
    import json

    from gfso import doctor

    monkeypatch.setenv("GFSO_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(doctor, "desktop_config_path", lambda: tmp_path)
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "x"}}}),
                   encoding="utf-8")

    report = doctor.install_desktop()
    written = json.loads(cfg.read_text(encoding="utf-8"))
    assert written["theme"] == "dark"                        # every other key untouched
    assert written["mcpServers"]["other"] == {"command": "x"}
    assert written["mcpServers"]["gfso"]["args"] == ["connect"]
    assert json.loads((tmp_path / "claude_desktop_config.json.gfso-backup")
                      .read_text(encoding="utf-8"))["mcpServers"].keys() == {"other"}
    assert "written to" in report

    assert "already configured" in doctor.install_desktop()  # idempotent on a second run


def test_the_argv_the_launcher_spawns_is_argv_the_cli_accepts(tmp_path, monkeypatch):
    """The spawn builds a `gfso serve …` command line, and nothing checked the parser accepts it.

    Measured: a flag renamed on `serve` left the launcher passing the retired spelling, so every
    attempt to start the server died instantly with an argparse usage message inside `server.log`,
    while the launcher reported only that the server had not come up within 25 seconds. The
    reference to the parser is what makes the two sides one fact.
    """
    import subprocess

    from gfso.mcp import connect

    seen = {}

    class _Popen:
        def __init__(self, argv, **kw):
            seen["argv"] = argv

    monkeypatch.setenv("GFSO_HOME", str(tmp_path))
    # The patch is scoped: it has to be gone before this test spawns a real process of its own.
    with monkeypatch.context() as m:
        m.setattr(subprocess, "Popen", _Popen)
        m.setattr("gfso.serverctl.port_open", lambda *a, **k: False)
        connect.ensure_server("http://127.0.0.1:8999/mcp", wait_s=0.0)

    argv = seen["argv"]
    assert argv[1:3] == ["-m", "gfso.cli"], argv
    parser_args = argv[3:]                       # everything after `python -m gfso.cli`
    # Asked of the parser OBJECT, not of a subprocess with `--help` appended: `--help` fires during
    # parsing and exits 0 before argparse ever reports an unrecognized argument, so that spelling of
    # this check was green against the very defect it was written for.
    from gfso.cli import build_parser
    try:
        parsed = build_parser().parse_args(parser_args)
    except SystemExit as ex:
        raise AssertionError(
            f"the launcher spawns `gfso {' '.join(parser_args)}`, which the CLI rejects "
            f"(argparse exited {ex.code})") from None
    assert parsed.command == "serve"


def _app_with_leases():
    """A live app object, so the lease bookkeeping is exercised rather than described."""
    from fastapi.testclient import TestClient

    from gfso.api.server import create_app
    from gfso.engine import Engine
    from gfso.adapters.storage.memory import MemoryStorage
    from gfso.adapters.agents.human import HumanAgent
    e = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=True, state_timeout=0)
    e.start()
    return e, TestClient(create_app(e))


def test_a_lease_expires_on_its_own_so_a_dead_session_cannot_block_an_upgrade():
    """The whole upgrade path hangs off this number.

    Leases were pruned only by the self-exit reaper, which is opt-in — so a session that ended
    without dropping its lease (a killed client; the drop rides a daemon thread) left an entry that
    never expired. `ensure_correct` reads `sessions` to decide whether a restart would interrupt
    somebody, so one stale entry made every later upgrade decline to take effect, silently and
    permanently: exactly the defect the reconcile was added to close, one layer up.
    """
    import time as _t

    e, client = _app_with_leases()
    try:
        assert client.post("/api/lease", json={"id": "alive"}).json()["sessions"] == 1
        assert client.get("/api/runtime").json()["sessions"] == 1

        app = client.app                       # a session that died without dropping its lease
        app.state.leases["ghost"] = _t.monotonic() - 60           # past the grace window
        assert client.get("/api/runtime").json()["sessions"] == 1, "the ghost still counts"
        assert "ghost" not in app.state.leases                     # …and was pruned on the way

        client.delete("/api/lease/alive")
        assert client.get("/api/runtime").json()["sessions"] == 0
    finally:
        e.stop()


def test_busy_counts_concurrent_calls_of_one_verb():
    """`busy` decides whether a reconcile leaves the server alone. As a SET, the first of two
    concurrent validations to finish cleared the flag while the second was still running — and
    since every tool now runs in its own thread, concurrent calls of one verb are ordinary."""
    from gfso import tools_llm as TL

    with TL._inflight("validate_result"):
        with TL._inflight("validate_result"):
            assert sorted(TL.INFLIGHT) == ["validate_result"]
        assert sorted(TL.INFLIGHT) == ["validate_result"], "the inner exit cleared the outer's flag"
    assert sorted(TL.INFLIGHT) == []


def test_a_reconcile_leaves_an_occupied_server_alone_but_force_does_not():
    """Restarting the one server ends whatever it is doing for somebody else, and the model
    subprocesses it spawned outlive it. So drift on an occupied server is reported, not acted on —
    unless the caller says otherwise."""
    from gfso import serverctl
    from gfso.mcp import connect

    stale = {"code_version": "old", "validate_internal": False, "l2_gate": True,
             "agents_path": "", "with_mcp": True, "sessions": 2, "busy": ["auto_decompose"]}
    calls = []

    import unittest.mock as mock
    with mock.patch.object(serverctl, "runtime", lambda *a, **k: stale), \
         mock.patch.object(serverctl, "declared", lambda: {}), \
         mock.patch.object(serverctl, "source_fingerprint", lambda: "new"), \
         mock.patch.object(connect, "ensure_server", lambda *a, **k: calls.append("spawn") or True):
        out = connect.ensure_correct(verbose=False)
        assert out["action"] == "left-alone" and out["drift"], out
        assert calls == [], "it restarted a server with another session's work in flight"
