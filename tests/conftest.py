"""Suite-wide defaults.

THE SUITE NEVER TOUCHES THE INSTALLATION'S OWN STATE. Roles registered by a test used to land in the
REAL roster of this machine — beside live runs' roles, on a file every session shares — and a probe
role called `probe-exec` sat there for a day (found 2026-08-21). The roster is only the visible half:
`GFSO_HOME` also decides where databases and rejected reports go. One session-scoped home, set before
anything imports a path, keeps the suite out of the way of whatever is running.

The Level-2 execution gate (§13.4, gfso/engine/validation.py) is ON in a running system: a child may
not start work while its parent's decomposition has no current causal review. That review is an
LLM-layer instrument, and this suite is substrate-free by design (no model runs) — so the suite
takes the canon's own EXPLORE branch (§13.5) and turns the gate off, exactly as a deployment
without a checker would. `tests/test_l2_gate.py` turns it back ON and owns that behavior end to end.
"""
import os
import tempfile

import pytest


@pytest.fixture(autouse=True, scope="session")
def _own_state_home():
    """A home of the suite's own, for the whole session."""
    prior = os.environ.get("GFSO_HOME")
    os.environ["GFSO_HOME"] = tempfile.mkdtemp(prefix="gfso-suite-")
    yield
    if prior is None:
        os.environ.pop("GFSO_HOME", None)
    else:
        os.environ["GFSO_HOME"] = prior


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
