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
import os
import shutil
import subprocess
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

from gfso.adapters import execution as E  # noqa: E402
from gfso.adapters.llm import chat as _chat  # noqa: E402


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
        shutil.rmtree(h, ignore_errors=True)


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
    os.environ["GFSO_LOCAL_AGENTS"] = "allow"           # the suite's sessions are fakes on this host, by its own word
    yield
    _sweep(Path(mine))
    if prior is None:
        os.environ.pop("GFSO_HOME", None)
    else:
        os.environ["GFSO_HOME"] = prior


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


#: what a change to a path of the execution layer owes, whichever stream lands it: these live files, by name, under the
#: one lock (`--live-owed <ref>` reads the paths from git) — which controls a change owes is no lander's judgement
LIVE_OWED = {
    "gfso/adapters/execution.py": ("a_container_runs_a_call_with_the_hosts_paths_mapped", "a_container_holds_no_more_than_its_bounds",
                                   "a_session_holds_only_its_own_place", "a_sessions_commands_run_apart_from_its_client",
                                   "a_judges_pinned_inputs_are_the_systems", "the_way_out_is_a_switch_set_outside",
                                   "a_projects_places_stand_in_its_volume"),    # …the judge's whole file: `snapshots.py` and the pin's
    "gfso/adapters/door.py": ("a_projects_places_stand_in_its_volume", "a_container_holds_no_more_than_its_bounds"),
    "gfso/adapters/egress.py": ("the_way_out_is_a_switch_set_outside",),
    "gfso/adapters/shell.py": ("a_sessions_commands_run_apart_from_its_client", "a_container_holds_no_more_than_its_bounds"),
    "gfso/adapters/snapshots.py": ("the_runs_of_a_validation_do_not_share_a_tree", "a_judge_judges_what_was_delivered", "the_system_reads_a_place_where_its_agent_cannot_lead_it_out",
                                   "the_systems_git_runs_in_the_place_it_reads"),
    "gfso/adapters/worktrees.py": ("a_projects_places_stand_in_its_volume", "the_base_is_imported_and_its_result_lands_as_a_branch",
                                   "the_systems_git_runs_in_the_place_it_reads"),
    "gfso/adapters/lfs.py": ("lfs_files_come_in_whole_and_leave_as_pointers", "the_base_is_imported_and_its_result_lands_as_a_branch"),
    "gfso/adapters/agent.Dockerfile": ("a_session_holds_only_its_own_place", "a_sessions_commands_run_apart_from_its_client"),
    "gfso/observe.py": ("a_judges_pinned_inputs_are_the_systems", "a_session_holds_only_its_own_place"),
    "gfso/adapters/resources.py": ("an_orphan_is_known_by_an_id_no_spelling_shares",),
    "gfso/adapters/children.py": ("a_sessions_commands_run_apart_from_its_client",),
    "gfso/config.py": ("a_container_holds_no_more_than_its_bounds",),
}


def owed(paths) -> set:
    """The live test files (by stem, without `test_`) a change to `paths` owes."""
    return {f for p in paths for f in LIVE_OWED.get(p, ())}


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", help="also run the live tests (real containers, ~50 min): one such "
                                                         "run per machine, once before a pin or a push, and CI's job")
    parser.addoption("--live-owed", metavar="REF", help="the default suite and the live files the change since REF owes (`LIVE_OWED`), under the lock; "
                                                       "REF is what the change is measured from: main before it lands")


def pytest_configure(config):
    _NoLiveModel.containers = bool(config.getoption("--live") or config.getoption("--live-owed"))
    config.addinivalue_line("markers", "no_model_path: the test drives the path where no model answers "
                                       "(a spawn attempt is expected and fails as a missing CLI does)")
    config.addinivalue_line("markers", "live: runs real containers (every `test_live_*`, marked here by name, and any "
                                       "other so marked) — not run unless `--live` or `--live-owed` is given")


def pytest_collection_modifyitems(config, items):
    for it in items:
        if it.name.startswith("test_live_"):
            it.add_marker(pytest.mark.live)
    ref = config.getoption("--live-owed")
    files = (owed(subprocess.run(["git", "diff", "--name-only", ref], capture_output=True, text=True, check=True).stdout.split())
             if ref else None)
    if not config.getoption("--live") or ref:
        gone = [it for it in items if it.get_closest_marker("live")
                and not (ref and it.path.stem.removeprefix("test_") in files)]
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
    if session.config.getoption("--live") or session.config.getoption("--live-owed"):
        _take_the_live_lock()
    root = session.config._tmp_path_factory.getbasetemp()
    (root / OWNER).write_text(str(os.getpid()), encoding="utf-8")
    for run in root.parent.glob("pytest-*"):
        if run != root and _dead(run / OWNER):
            shutil.rmtree(run, ignore_errors=True)
    for left in _TMP.iterdir():       # …what tests made and left beside it, a day on: no run lasts that long
        if left.name != root.parent.name and left != LIVE_LOCK and not left.name.startswith("gfso-suite-") \
                and time.time() - left.stat().st_mtime > 86400:
            shutil.rmtree(left, ignore_errors=True) if left.is_dir() else left.unlink(missing_ok=True)


def pytest_terminal_summary(terminalreporter, config):
    if not (config.getoption("--live") or config.getoption("--live-owed")):     # …said under xdist too: its workers collect
        terminalreporter.write_line("live tests NOT run: they need `--live`, or `--live-owed <ref>` for what a change owes")


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
