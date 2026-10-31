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

from gfso.adapters import execution as E
from gfso.adapters.llm import chat as _chat


#: older than this, a suite's home is a run that was cut short: a whole suite takes under an hour
CUT_RUN_S = 6 * 3600


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
    _sweep(*[d for d in Path(tempfile.gettempdir()).glob("gfso-suite-*") if time.time() - d.stat().st_mtime > CUT_RUN_S])
    os.environ["GFSO_HOME"] = mine = tempfile.mkdtemp(prefix="gfso-suite-")
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
    def __init__(self, args, *a, **k):
        first = args[0] if isinstance(args, (list, tuple)) and args else args
        if first and "claude" in os.path.basename(str(first)).lower():
            _LIVE_SPAWNS.append(f"[thread {threading.current_thread().name}] {str(args)[:200]}")
            raise OSError("a live model run was attempted inside the test suite")
        super().__init__(args, *a, **k)


def pytest_configure(config):
    config.addinivalue_line("markers", "no_model_path: the test drives the path where no model answers "
                                       "(a spawn attempt is expected and fails as a missing CLI does)")


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
