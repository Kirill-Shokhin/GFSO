"""The entry doors, as runnable code that SHIPS.

These live inside the package rather than beside it because an example only a cloner can run is not
part of the product: `pip install gfso` used to leave the first command the front page gives you —
run the human-only script and watch the gate refuse a self-signed PASS — with no file to run.

Each module is standalone and prints what the ENGINE says, not what the script narrates. Run one as
`gfso demo human_only`, or as `python -m gfso.examples.human_only`; `gfso demo` with no name lists
them. The two that spawn models cost real tokens and are never run by the test suite.
"""
import atexit
import os
import shutil
import subprocess
import sys
import tempfile

from gfso.adapters.execution import LocalExecution
from gfso.config import DEFAULT_EXECUTION, executions, local_agents, use_agents_path

_SCRATCH = None


def scratch(name: str) -> str:
    """A path inside one temporary directory per run, removed when the process exits.

    The demos named their files with `tempfile.mktemp`, which invents a name and nothing else: every
    run left its database — and, for the delegated ones, its agent registry — in the system temp
    directory for good. A demo is the first thing a stranger runs; it should not litter.
    """
    global _SCRATCH
    if _SCRATCH is None:
        _SCRATCH = tempfile.TemporaryDirectory(prefix="gfso_demo_")
        atexit.register(_SCRATCH.cleanup)
    return os.path.join(_SCRATCH.name, name)


def delegation(prefix: str) -> tuple:
    """(a working directory for a demo's delegated work, the execution it runs in) — the installation's default
    container (`gfso setup`), else this host on the user's word: unattended work runs nowhere else, and where it cannot
    run the demo exits with why. In a container the directory is a repository with a commit, so each node works in a
    place of its own; the demo's roster is the one the system reads (`config.use_agents_path`) — a roster of its own
    was invisible to what finds a project's execution, and its judges ran on this host."""
    if not shutil.which("claude"):
        sys.exit("needs the Claude Code CLI on PATH (the executor/validator transport)")
    execution = DEFAULT_EXECUTION if not local_agents() and DEFAULT_EXECUTION in executions() else None
    if execution is None and (why := LocalExecution().agents_refused()):
        sys.exit(f"its executors run unattended: `gfso setup` declares a container for them, or export "
                 f"GFSO_LOCAL_AGENTS=allow to run them on this host ({why[:80]}…)")
    work = tempfile.mkdtemp(prefix=prefix)
    if execution:
        for args in (["init", "-q"], ["-c", "user.name=gfso-demo", "-c", "user.email=demo@gfso.local", "commit", "-q",
                                      "--allow-empty", "-m", "start"]):
            subprocess.run(["git", "-C", work, *args], check=True, capture_output=True)
    use_agents_path(scratch("agents.json"))
    return work, execution


DEMOS = {
    "human_only": "the verifier ≠ executor gate, with zero AI (~1s)",
    "async_precompute": "a decomposition computed outside the process, applied as signals (~1s)",
    "mixed_delegation": "one node delegated to a registered LLM executor (~1-2 min, spawns models)",
    "autonomous_org": "a whole graph driven with no human in the loop (~5-10 min, spawns models)",
}

NEEDS_MODEL = ("mixed_delegation", "autonomous_org")
