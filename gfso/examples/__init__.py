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
import tempfile

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


DEMOS = {
    "human_only": "the verifier ≠ executor gate, with zero AI (~1s)",
    "async_precompute": "a decomposition computed outside the process, applied as signals (~1s)",
    "mixed_delegation": "one node delegated to a registered LLM executor (~1-2 min, spawns models)",
    "autonomous_org": "a whole graph driven with no human in the loop (~5-10 min, spawns models)",
}

NEEDS_MODEL = ("mixed_delegation", "autonomous_org")
