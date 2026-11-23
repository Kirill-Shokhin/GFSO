"""Suite-wide defaults.

THE SUITE NEVER TOUCHES THE INSTALLATION'S OWN STATE. Roles registered by a test used to land in the
REAL roster of this machine — beside live runs' roles, on a file every session shares — and a probe
role called `probe-exec` sat there for a day (found 2026-08-21). The roster is only the visible half:
`GFSO_HOME` also decides where databases and rejected reports go. One session-scoped home, set before
anything imports a path, keeps the suite out of the way of whatever is running.

The Level-2 execution gate (§9.1, gfso/engine/validation.py) is ON in a running system: a child may
not start work while its parent's decomposition has no current causal review. That review is an
LLM-layer instrument, and this suite is substrate-free by design (no model runs) — so the suite
takes the canon's own EXPLORE branch (§9.9) and turns the gate off, exactly as a deployment
without a checker would. `tests/test_l2_gate.py` turns it back ON and owns that behavior end to end.
"""
import atexit
import contextlib
import faulthandler
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import pytest

try:
    import psutil
except ImportError:        # …a dev-only tool: without it no suite is known dead, nothing is ended
    psutil = None
try:
    import fcntl
except ImportError:
    fcntl = None
try:
    import msvcrt
except ImportError:
    msvcrt = None

#: every temporary file of the suite stays inside the project (the author's rule): the ignored `.tmp` at the MAIN tree's top,
#: one for all its worktrees — inside a worktree a run's paths passed Windows' 260 characters and copies failed silently;
#: the ceiling keeps a test's "no repository here" true there: from inside, git would find this one and act on it
_ROOT = Path(__file__).resolve().parent.parent
_COMMON = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], capture_output=True, text=True,
                         cwd=_ROOT).stdout.strip() if shutil.which("git") else ""
_TMP = (Path(_COMMON).parent if _COMMON else _ROOT) / ".tmp"
_TMP.mkdir(exist_ok=True)
tempfile.tempdir = str(_TMP)
os.environ.update(TMP=str(_TMP), TEMP=str(_TMP), TMPDIR=str(_TMP), GIT_CEILING_DIRECTORIES=str(_TMP))


class _Mute:
    write, flush = staticmethod(len), staticmethod(lambda: None)


def _no_thread_writes_through_the_interpreters_end():
    """A daemon thread a test left behind, caught inside a write as the interpreter finalizes, keeps the stream's lock
    for good, and the last flush aborts the process: "could not acquire lock for <stderr>", a green suite's job red with
    exit 127 (CI, Windows, 2026-11-04). Registered before anything else here, so it runs last: what other callbacks say
    is still said. The pause is for a write already under way to end."""
    sys.stdout.flush(), sys.stderr.flush()
    sys.stdout = sys.stderr = _Mute()
    time.sleep(0.2)


atexit.register(_no_thread_writes_through_the_interpreters_end)

from gfso.adapters import execution as E  # noqa: E402
from gfso import config as _config  # noqa: E402
from gfso.config import agents_path  # noqa: E402

#: the person's page word on host execution as the product reads it, before the suite stands in for it
REAL_LOCAL_AGENTS = _config.local_agents
from gfso.decompose import kept as _kept_store  # noqa: E402
from gfso.adapters.llm import chat as _chat  # noqa: E402
from gfso.delegate import _DISPATCHERS, Dispatcher  # noqa: E402
import gfso.delegate as _delegate  # noqa: E402
from gfso.engine import Engine  # noqa: E402
from gfso import signin  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402


#: older than this, a suite's home is a run that was cut short: a whole suite takes under an hour
CUT_RUN_S = 6 * 3600
#: the process a suite's home belongs to, in the home: a run cut short is known at once where the process is gone
OWNER = "suite.pid"


def _dead(pid_file: Path) -> bool | None:
    """Whether the process a file names is gone; None where nothing is known (no file, or no `psutil`, a dev-only tool)."""
    try:
        return None if psutil is None else not psutil.pid_exists(int(pid_file.read_text()))
    except (OSError, ValueError):
        return None


def _sweep(*homes: Path) -> None:
    """Suite homes gone, with every container, volume and network labelled with them: a run cut short — the harness
    under memory pressure, a timeout — never reached its fixtures' teardown, and every project its live tests stood up
    stayed (2026-10-31: 97 containers, 160 volumes, 5699 homes left on one machine)."""
    marks = {E._home(h / "data") for h in homes}
    if marks and shutil.which("docker"):
        for kind, ls in (("container", ["ps", "-a"]), ("volume", ["volume", "ls"]), ("network", ["network", "ls"])):
            got = subprocess.run(["docker", *ls, "--format", '{{.ID}} {{.Label "gfso.home"}}'], capture_output=True,
                                 text=True).stdout.splitlines()
            if ids := [i for i, _, h in (r.partition(" ") for r in got) if h in marks]:
                subprocess.run(["docker", kind, "rm", *(["-f"] if kind == "container" else []), *ids], capture_output=True)
    for h in homes:
        shutil.rmtree(h, onerror=_writable_then)


def _writable_then(fn, path, _) -> None:
    """A test repository's packs are read-only, and on Windows `rmtree` cannot unlink those: ignored, its home stayed, and
    every worker of every later suite walked all of them again (2026-11-19: 2134 homes, ~25 s of each worker's setup)."""
    with contextlib.suppress(OSError):
        os.chmod(path, stat.S_IWRITE)
        fn(path)


@pytest.fixture(autouse=True, scope="session")
def _own_state_home():
    """A home of the suite's own, for the whole session."""
    prior = os.environ.get("GFSO_HOME")
    _sweep(*[d for d in Path(tempfile.gettempdir()).glob("gfso-suite-*")
             if _dead(d / OWNER) or (_dead(d / OWNER) is None and time.time() - d.stat().st_mtime > CUT_RUN_S)])
    os.environ["GFSO_HOME"] = mine = tempfile.mkdtemp(prefix="gfso-suite-")
    (Path(mine) / OWNER).write_text(str(os.getpid()), encoding="utf-8")
    os.environ["GFSO_ALLOWED_HOSTS"] = "testserver"     # the name Starlette's TestClient sends; the door refuses others
    E.CEILING_GROUP = "gfso/suite"                      # its live containers under the machine's ceiling, never its limit
    _config.local_agents = lambda: True                 # the suite's sessions are fakes on this host, by its own word;
                                                        # a test without it sets it False, the record is read in its own
    os.environ["GFSO_NETWORK_RECORD"] = "off"           # …a listener for each worker's live tests; its own file asks for it
    os.environ["GFSO_NO_UPDATE_CHECK"] = "1"            # …nor PyPI asked by a doctor or a use_project under test
    os.environ["GFSO_OPEN_PAGE"] = "0"                  # …nor a browser opened by a go under test
    # …nor the person's own Claude state: a host session's state dir is `claude_config_dir()`, and tests wrote their
    # sessions' files into ~/.claude/gfso-sessions (2026-11-15); a test that sets its own keeps it
    prior_cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    os.environ["CLAUDE_CONFIG_DIR"] = str(Path(mine) / "claude")
    # …nor a server's state: a validator's probe running this suite inherits the server's environment, and a data
    # directory or database named there outranks the home — the suite's stores were laid in the live server's data
    prior_state = {n: os.environ.pop(n, None) for n in ("GFSO_DATA_DIR", "GFSO_DB_PATH")}
    E._DISK_WATCH.set()                                 # …nor a watch beside each worker's: a test runs its own
    E._WATCH.set()
    yield
    _sweep(Path(mine))
    for name, was in (("GFSO_HOME", prior), ("CLAUDE_CONFIG_DIR", prior_cfg), *prior_state.items()):
        if was is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = was


#: the names the suite's person signs as on the page, beside the standing agent: the parties its HTTP tests act as
SUITE_NAMES = ("dev", "alice", "engineering", "d", "d1", "pm")
#: where a suite's client asks by default: a local client that is no browser, as the person's own scripts are
LOCAL_CLIENT = "http://127.0.0.1:8000"


@pytest.fixture(autouse=True, scope="session")
def _the_suites_person(_own_state_home):
    """THE SUITE'S PAGE IS SIGNED IN, as a person's is: its person is issued its names and a page session the way `gfso
    agent` and `gfso ui` issue them (`signin.issue`, `signin.code` → `redeem`), and every test client carries that
    session — a door no test bypasses — asking a loopback name: where a test moves the state home the session is not held
    there, and its calls are still his page's, admitted as this machine's user (`signin.PAGE`) — a client with no
    credential and no page reads and signs nothing (`signin.BARE`). A test of what a call with no session gets clears
    the cookie (`client.cookies.clear()`) and names its headers; one of another host names it (`base_url`)."""
    for name in SUITE_NAMES:
        signin.issue(name)
    session, made = signin.redeem(signin.code()), TestClient.__init__

    def signed_in(self, app, *a, **k):
        if not a and "base_url" not in k and "headers" not in k:
            k["headers"] = {"Sec-Fetch-Site": "same-origin"}
        made(self, app, *a, **({} if a or "base_url" in k else {"base_url": LOCAL_CLIENT}), **k)
        self.cookies.set(signin.COOKIE, session)
    TestClient.__init__ = signed_in
    yield session
    TestClient.__init__ = made


@pytest.fixture(autouse=True)
def _a_log_in_ends_with_its_test():
    """A connection's log-in (`signin.take`) is the test's own: one live connection holds a name, `user` among them, and
    a holding an earlier test left would be read as another live console's."""
    yield
    with contextlib.suppress(Exception), signin._db() as db:
        db.execute("DELETE FROM holds")


@pytest.fixture(autouse=True, scope="session")
def _the_suites_peer_is_its_own_user():
    """THE SUITE'S CALLS COME FROM ITS OWN OS USER, as a local client's do: a test client has no socket for the OS to
    name an owner of (`peer.ours`), so the door asks this answer; a test of another user's call makes it answer no
    (`monkeypatch.setattr(signin, "peer_is_ours", ...)`), and the OS's own answer is tested on a real socket."""
    asked = signin.peer_is_ours
    signin.peer_is_ours = lambda peer, server: True
    yield
    signin.peer_is_ours = asked


#: engines started and dispatchers made since the current test's setup began — stopped when its body ends
_STARTED: list = []
_start, _made = Engine.start, Dispatcher.__init__


def _recorded_start(self):
    _STARTED.append(self)
    return _start(self)


def _recorded_dispatcher(self, *a, **k):
    _STARTED.append(self)
    return _made(self, *a, **k)


# for the life of the process, as `_no_live_model`'s Popen: what a test starts is known, a dispatcher it made directly too
Engine.start, Dispatcher.__init__ = _recorded_start, _recorded_dispatcher


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item):
    _STARTED.clear()
    item.stash[_BEFORE] = (set(_DISPATCHERS), set(threading.enumerate()))
    return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    """An engine a test started, and the dispatcher attached to it, outlived the test: a validation they queued ran on
    during the next test and its container start was charged to that test (an LFS test failed on the in_chat test's
    validation thread). Whatever the test started is stopped when its body ends — before its fixtures' teardown, so
    while its fakes still stand — and what they had in flight ends there. A thread of its still at gfso's work a minute later fails
    the test that left it: carried on, it is the next test's defect."""
    try:
        out = yield
    except BaseException:
        _stopped(*item.stash[_BEFORE])
        raise
    left = _stopped(*item.stash[_BEFORE])
    assert not left, f"threads this test started are still at gfso's work {_BOUND_S} s after it stopped them: {left}"
    return out


_BEFORE = pytest.StashKey[tuple]()


def _stopped(dispatchers: set, threads: set) -> list:
    """No new work (its dispatchers stopped), the work in flight finished on engines still running, then the engines:
    stopped first, an engine left a run in flight waiting on it for its whole timeout."""
    for key in set(_DISPATCHERS) - dispatchers:
        _DISPATCHERS.pop(key).stop()
    for d in [x for x in _STARTED if isinstance(x, Dispatcher)]:
        d.stop()
    end, left = time.monotonic() + _BOUND_S, []
    _joined(threads, end, left, but=_ENGINES_OWN)
    for e in [x for x in _STARTED if not isinstance(x, Dispatcher)]:
        e.stop()
    _STARTED.clear()
    _joined(threads, end, left, but=("gfso-timeout-monitor",))
    return left


#: an engine's own loops end with the engine; its timeout monitor is not waited at all — stopped, it does nothing more,
#: and its tick is a sleep no stop wakes (10 s a test, measured by a critic)
#: how long a test's work in flight is waited out — generous: it costs only where work is in flight, and a tight one
#: was itself a flake (a demo's validation deleting its tree past 10 s in a loaded suite)
_BOUND_S = 60
_ENGINES_OWN = ("gfso-event-loop", "gfso-timeout-monitor")


def _joined(threads: set, end: float, left: list, but: tuple) -> None:
    """Join the threads started since `threads` that are at gfso's work, by `end`; each still at it on the last pass is
    named in `left` with where it stands. A library's idle pool thread (a test client's AnyIO workers and portal) is
    not the product's work carried into the next test; a thread only starting cannot be joined."""
    last = but == ("gfso-timeout-monitor",)
    for th in set(threading.enumerate()) - threads:
        if th.ident is None or th.name in but or not _at_gfso(th):
            continue
        th.join(max(0.0, end - time.monotonic()))
        if last and th.is_alive() and _at_gfso(th):
            left.append(f"{th.name} at {' < '.join(_stack(th)[:6])}")


_GFSO = os.path.dirname(sys.modules["gfso"].__file__)   # the package, wherever it is installed


def _stack(th) -> list:
    f, at = sys._current_frames().get(th.ident), []
    while f is not None:
        at.append(f"{Path(f.f_code.co_filename).name}:{f.f_lineno} {f.f_code.co_name}")
        f = f.f_back
    return at


def _at_gfso(th) -> bool:
    """At gfso's work: a gfso frame on its stack, or gfso's code still to run — a timer that has not fired stands in
    the library with no gfso frame (a critic's mutation: the dispatcher's timers outlived it under a green suite)."""
    fn = getattr(th, "function", None) or getattr(th, "_target", None)
    code = getattr(getattr(fn, "__func__", fn), "__code__", None)
    if code is not None and code.co_filename.startswith(_GFSO):
        return True
    f = sys._current_frames().get(th.ident)
    while f is not None:
        if f.f_code.co_filename.startswith(_GFSO):
            return True
        f = f.f_back
    return False


#: a test past this has hung: every thread's stack goes to `.tmp/hung-<pid>.txt` — two hangs in 40 suites left no trace,
#: a worker's stderr being lost under xdist (bb36595; 2026-11-14, validate_result spinning on CPU for 10 min)
HUNG_S = 240


@pytest.fixture(autouse=True)
def _a_hang_leaves_its_stacks(request):
    at = _TMP / f"hung-{os.getpid()}.txt"
    out = open(at, "w", encoding="utf-8")
    out.write(request.node.nodeid + "\n")
    out.flush()
    faulthandler.dump_traceback_later(HUNG_S, file=out)
    real = shutil.copytree

    def _noted(src, dst, *a, **kw):
        """Each directory a copy enters, before it is copied: the one hang caught so far spun 13 levels deep in a
        validation snapshot's copytree, and its stacks could not say what was being copied where."""
        if not out.closed:
            out.write(f"copytree {src} -> {dst}\n")
            out.flush()
        return real(src, dst, *a, **kw)
    shutil.copytree = _noted
    try:
        yield
    finally:
        shutil.copytree = real
        faulthandler.cancel_dump_traceback_later()
        out.close()
        at.unlink(missing_ok=True)     # …kept only by a test that never came back


@pytest.fixture(autouse=True)
def _the_screen_is_the_tests_own(monkeypatch):
    """No test's outcome reads the shell it ran from: its screen is closed (`GFSO_NO_WINDOWS=1`) and opens no person's
    browser (`BROWSER`, `GFSO_OPEN_PAGE` unset) whatever was exported. Closed, not unset: a test that forgot to fake a
    start puts nothing on the screen of the person running the suite; a test of opening sets "0" and fakes the start."""
    monkeypatch.setenv("GFSO_NO_WINDOWS", "1")
    for k in ("BROWSER", "GFSO_OPEN_PAGE"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(autouse=True)
def _no_consent_round_of_its_own(request, monkeypatch):
    """A dispatcher a test builds asks a system-held parent for its consent in a thread of its own (`run_consent`), and
    a real round finds no credential in the suite's home and pauses the project at a moment the scheduler picks: a test
    driving a second round then started nothing (measured 3 of 96 under -n 16; six tests ran the real round). So a
    test's dispatcher is answered "not offered" unless the test asks for the real round (`@pytest.mark.real_consent`)
    or passes a `consent_runner` of its own."""
    if request.node.get_closest_marker("real_consent") is None:
        monkeypatch.setattr(_delegate, "run_consent", lambda *a, **k: {"status": "not_offered"})


@pytest.fixture(autouse=True)
def _no_role_outlives_its_test():
    """What a test registers on the suite's roster goes with it. Shared by a worker's session, a validator one test
    registered at `.` stood first for every later test's executor — the next validation's place was the repository
    itself, its scratch beside the repository, and a snapshot copied the whole tree for minutes: the suite's one hang
    (2026-11-14, `test_a_connection_signs_as_its_principal` before `test_validate_result`, 33,944 directories entered).
    The file is emptied, not moved: a test that reads which roster an environment names keeps reading the default."""
    roster = agents_path()
    roster.unlink(missing_ok=True)
    yield
    roster.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _no_plan_outlives_its_test():
    """A written plan is kept on disk (`decompose.kept`) under its handle, the hash of its call's arguments: kept from one
    test, the same request in the next would be answered by it, never written. Its own directory per worker: xdist's
    workers share the suite's state directory."""
    root = _TMP / f"kept-{os.getpid()}"
    real, _kept_store.data_dir = _kept_store.data_dir, lambda: root
    shutil.rmtree(root, ignore_errors=True)
    try:
        yield
    finally:
        shutil.rmtree(root, ignore_errors=True)
        _kept_store.data_dir = real


@pytest.fixture(autouse=True)
def _the_ceiling_decided_per_test():
    """What a test's fake Docker answered decides nothing for the next: `execution.ceiling` asks again."""
    E._CEILING.clear()


@pytest.fixture(autouse=True, scope="session")
def _the_suite_does_not_reconcile_the_one_server():
    """…AND IT NEVER RESTARTS THE INSTALLATION'S SERVER, unless a run asks for it in as many words.

    Reconciling is right for the verbs that mean it (`gfso up`, the MCP door after an upgrade) and
    wrong for everything incidental — a health probe, an import, this suite. It was neither: the
    suite reconciled by DEFAULT, with the suite's own temporary home, and twice took down a live
    server and killed a paid measurement run mid-flight (2026-08-22).

    What was done about it then was `GFSO_NO_RECONCILE=1` in front of the command — a guard the
    person running the suite has to remember, which is to say a guard that protects the invocations
    that did not need protecting. Every session since has typed it, this one included, and the four
    tests that DO exercise reconciling have been failing under it all day, which is how a habit
    turns into a blind spot. Here the dangerous path requires an affirmative act (`GFSO_RECONCILE=1`)
    and the tests that want it say so themselves.
    """
    prior = os.environ.get("GFSO_NO_RECONCILE")
    if not os.environ.get("GFSO_RECONCILE"):
        os.environ["GFSO_NO_RECONCILE"] = "1"
    yield
    if prior is None:
        os.environ.pop("GFSO_NO_RECONCILE", None)
    else:
        os.environ["GFSO_NO_RECONCILE"] = prior


@pytest.fixture
def reconciling(monkeypatch):
    """For the tests whose SUBJECT is the reconciler. Everything else stays behind the default."""
    monkeypatch.delenv("GFSO_NO_RECONCILE", raising=False)


@pytest.fixture(autouse=True, scope="session")
def _l2_gate_off():
    prior = os.environ.get("GFSO_L2_GATE")
    os.environ["GFSO_L2_GATE"] = "0"
    yield
    if prior is None:
        os.environ.pop("GFSO_L2_GATE", None)
    else:
        os.environ["GFSO_L2_GATE"] = prior


#: every attempt to start a model inside the suite — a test's teardown fails on any made during it
_LIVE_SPAWNS: list = []
#: attempts that landed outside any test's window — the session fails on them
_UNATTRIBUTED: list = []


def pytest_sessionfinish(session, exitstatus):
    left = _UNATTRIBUTED + _LIVE_SPAWNS
    if left:
        print(f"LIVE MODEL SPAWN ATTEMPTS OUTSIDE ANY TEST ({len(left)}), first: {left[0]}")
        session.exitstatus = 1


class _NoLiveModel(subprocess.Popen):          # a subclass: callers subscript it (`Popen[bytes]`)
    #: real containers are `--live`'s: outside it a test starting one fails, so nothing heavy enters the default suite by its name
    containers = False

    def __init__(self, args, *a, **k):
        first = args[0] if isinstance(args, (list, tuple)) and args else args
        if (not self.containers and first and os.path.basename(str(first)).lower().removesuffix(".exe") == "docker"
                and (list(args[1:2]) == ["run"] or list(args[1:3]) == ["volume", "create"])):
            _LIVE_SPAWNS.append(f"[thread {threading.current_thread().name}] {str(args)[:200]}")
            raise OSError("a real container was started outside `--live`: mark the test `live`")
        if first and "claude" in os.path.basename(str(first)).lower():
            _LIVE_SPAWNS.append(f"[thread {threading.current_thread().name}] {str(args)[:200]}")
            raise OSError("a live model run was attempted inside the test suite")
        super().__init__(args, *a, **k)


#: THE LIVE TESTS, BY WHAT THEY CHECK: each file in one group, a group run alone by `--live-group <name>[,<name>]`, the
#: group what the change is about, under the one lock. The whole of them, `--live`, is CI's at a push
LIVE_GROUPS = {
    "judge": ("a_judge_judges_what_was_delivered", "a_judges_pinned_inputs_are_the_systems", "the_runs_of_a_validation_do_not_share_a_tree",
              "a_pin_that_cannot_run_is_repaired_before_the_go"),
    "places": ("a_projects_places_stand_in_its_volume", "a_session_holds_only_its_own_place", "a_part_starts_with_no_siblings_work_but_by_an_edge"),
    "landing": ("the_base_is_imported_and_its_result_lands_as_a_branch", "lfs_files_come_in_whole_and_leave_as_pointers",
                "what_is_refused_before_it_is_touched"),
    "commands": ("a_sessions_commands_run_apart_from_its_client", "a_chat_providers_commands_run_apart"),
    "network": ("the_way_out_is_a_switch_set_outside", "where_a_session_reached_is_on_the_record"),
    "bounds": ("a_container_holds_no_more_than_its_bounds", "what_a_program_prints_is_bounded_in_the_server"),
    "git": ("the_systems_git_runs_in_the_place_it_reads", "the_system_reads_a_place_where_its_agent_cannot_lead_it_out",
            "a_container_runs_a_call_with_the_hosts_paths_mapped"),
    "resources": ("an_orphan_is_known_by_an_id_no_spelling_shares",),
}


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", help="also run every live test (real containers, ~50 min): CI's job")
    parser.addoption("--live-group", metavar="NAMES", help=f"only these groups' live tests, comma-separated: {', '.join(LIVE_GROUPS)}")


def pytest_configure(config):
    _NoLiveModel.containers = bool(config.getoption("--live") or config.getoption("--live-group"))
    config.addinivalue_line("markers", "no_model_path: the test drives the path where no model answers "
                                       "(a spawn attempt is expected and fails as a missing CLI does)")
    config.addinivalue_line("markers", "real_consent: the dispatcher's consent rounds run the real `run_consent` (by default "
                                       "a test's dispatcher is answered \"not offered\", `_no_consent_round_of_its_own`)")
    config.addinivalue_line("markers", "live: runs real containers (every `test_live_*`, marked here by name, and any "
                                       "other so marked) — not run unless `--live` or `--live-group` is given")


def pytest_collection_modifyitems(config, items):
    for it in items:
        if it.name.startswith("test_live_"):
            it.add_marker(pytest.mark.live)
    names = (config.getoption("--live-group") or "")
    if unknown := [n for n in names.split(",") if n and n not in LIVE_GROUPS]:
        raise pytest.UsageError(f"no live group {', '.join(unknown)}: {', '.join(LIVE_GROUPS)}")
    if names:
        files = {f for n in names.split(",") for f in LIVE_GROUPS[n]}
        gone = [it for it in items if not it.get_closest_marker("live") or it.path.stem.removeprefix("test_") not in files]
    else:
        gone = [] if config.getoption("--live") else [it for it in items if it.get_closest_marker("live")]
    if gone:
        config.hook.pytest_deselected(items=gone)
        items[:] = [it for it in items if it not in set(gone)]


#: held by the one suite running live tests on this machine, by the OS, so it goes with its process and two starts at once
#: cannot both take it: two such runs are hours of disk under every stream's work
LIVE_LOCK = _TMP / "gfso-live-suite.lock"
_LOCK_BYTE = 2 ** 20        # …away from the pid the file shows: a locked byte reads as an error on Windows
_held = []


def _take_the_live_lock() -> None:
    f = open(LIVE_LOCK, "a+", encoding="utf-8")
    f.seek(_LOCK_BYTE)
    try:
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1) if msvcrt else fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.seek(0)
        pytest.exit(f"a live suite already runs on this machine: pid {f.read(20).strip() or '?'}", returncode=75)
    f.seek(0), f.truncate(), f.write(str(os.getpid())), f.flush()
    _held.append(f)


def pytest_sessionstart(session):
    """`--live` taken by one suite per machine; the run directories of suites that died before their teardown gone (a
    numbered directory stays three days by its own `.lock`): known by the process each names."""
    if hasattr(session.config, "workerinput"):
        return
    if session.config.getoption("--live") or session.config.getoption("--live-group"):
        _take_the_live_lock()
    root = session.config._tmp_path_factory.getbasetemp()
    (root / OWNER).write_text(str(os.getpid()), encoding="utf-8")
    for run in root.parent.glob("pytest-*"):
        if run != root and _dead(run / OWNER):
            shutil.rmtree(run, ignore_errors=True)
    for left in _TMP.iterdir():       # …what tests made and left beside it, a day on: no run lasts that long
        try:
            old = time.time() - left.stat().st_mtime > 86400
        except FileNotFoundError:     # a neighbour's running suite removed its own under this walk
            continue
        if old and left.name != root.parent.name and left != LIVE_LOCK and not left.name.startswith("gfso-suite-"):
            shutil.rmtree(left, ignore_errors=True) if left.is_dir() else left.unlink(missing_ok=True)


def pytest_terminal_summary(terminalreporter, config):
    if not (config.getoption("--live") or config.getoption("--live-group")):     # …said under xdist too: its workers collect
        terminalreporter.write_line("live tests NOT run: they need `--live-group <name>` for what a change is about, or `--live`")


@pytest.fixture(autouse=True, scope="session")
def _the_suites_volumes_go_with_it():
    """Every project volume a test named (`Volume`) goes at the session's end, with any container still using it —
    no sweep of the product removes a volume (it holds a project's work), so none would. Set by hand, as below."""
    made, init, labels, docker = set(), E.Volume.__init__, E.Volume._labels, E.run

    def recorded(self, *a, **k):
        init(self, *a, **k)
        made.update((self.name, self.state))

    def faked(v):
        # …a test that fakes the docker client answers every inspect alike: its volumes are this installation's
        got = labels(v)
        return {"gfso.home": E._home()} if got == {} and E.run is not docker else got
    E.Volume.__init__, E.Volume._labels = recorded, staticmethod(faked)
    yield
    E.Volume.__init__, E.Volume._labels = init, staticmethod(labels)
    there = subprocess.run(["docker", "volume", "ls", "-q"], capture_output=True, text=True).stdout.split() if made else []
    for v in made & set(there):
        using = subprocess.run(["docker", "ps", "-aq", "--filter", f"volume={v}"], capture_output=True, text=True)
        if ids := using.stdout.split():
            subprocess.run(["docker", "rm", "-f", *ids], capture_output=True)
        subprocess.run(["docker", "volume", "rm", "-f", v], capture_output=True)


@pytest.fixture(autouse=True, scope="session")
def _no_live_model():
    """…AND IT NEVER STARTS A REAL MODEL. The suite is substrate-free by design, yet paths that resolve
    their own client (`decompose_into`'s default, `llm_factory` behind `review_decomposition`, an agent
    run behind `validate_result`, `doctor`'s probes) spawned a live `claude` from inside it — paid, and
    hanging for as long as the model took (measured 2026-09-23, on HEAD as well). Closed at the one place
    every such spawn passes, for the whole session (a thread a test left behind spawns too). A test that
    fakes the spawn to inspect the argv installs its own patch over this one. Set BY HAND, not through
    `monkeypatch`: an autouse fixture requesting it reorders every module fixture's teardown, and
    `test_l2_gate`'s gate then leaked ON into every later module (measured: 37 failures)."""
    # installed for the life of the PROCESS, never restored: a worker thread a test left behind may spawn
    # after the last teardown, and a restored Popen would hand it the real binary
    subprocess.Popen = _NoLiveModel
    # …nor a model behind an API: a wire may talk only to a server the test itself stands up on this machine
    _post = _chat.OpenAIWire._post

    def _local_only(self, body, timeout):
        if urlparse(self.address).hostname not in ("127.0.0.1", "localhost"):
            _LIVE_SPAWNS.append(f"[thread {threading.current_thread().name}] {self.address}")
            raise OSError("a live model API was called inside the test suite")
        return _post(self, body, timeout)
    _chat.OpenAIWire._post = _local_only
    yield


@pytest.fixture(autouse=True)
def _a_spawn_attempt_fails_the_test(request):
    """The adapter swallows the refused spawn and answers as for a missing CLI, so a test that reached
    one would PASS — hiding the very defect. It fails here instead, unless it declares that path."""
    _UNATTRIBUTED.extend(_LIVE_SPAWNS)          # landed between tests (a leaked thread): kept, reported at the end
    _LIVE_SPAWNS.clear()
    yield
    hit = list(_LIVE_SPAWNS)                   # this test's own attempts, taken whether or not it may make them
    _LIVE_SPAWNS.clear()
    if hit and request.node.get_closest_marker("no_model_path") is None:
        pytest.fail(f"this test tried to start a live model ({len(hit)}×, first: {hit[0]}); "
                    f"give it a stub, or mark it `no_model_path` if the no-model answer is what it tests")
