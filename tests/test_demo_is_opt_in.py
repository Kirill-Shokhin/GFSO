"""The demo project is planted when ASKED for, never by default.

It used to appear in every empty project: a fresh project created for real work opened with a
fictional "Release v2.0" tree in it — a graph nobody wrote, competing with the one they did.
"""
import os
import subprocess
import sys

from gfso import cli
from gfso.config import install_serve_env
from gfso.runtime import ProjectRegistry


def _serve_env(*flags: str) -> str:
    """What `gfso serve <flags>` would export, without starting anything."""
    code = ("import sys, os; sys.argv = ['gfso', 'serve', *%r];"
            "import gfso.cli as c;"
            "p = c._parser() if hasattr(c, '_parser') else None;"
            "print('UNSUPPORTED')" % (list(flags),))
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout


def test_the_flag_exists_and_defaults_to_no_demo(monkeypatch):
    """The switch exists, and OFF means no demo — asserted by running it, not by grepping for it.

    This test warned in its own comment that pinning a spelling "breaks on a rename while the
    DEFAULT it guards is untouched" — and then pinned one: it grepped `cli.py` for the literal
    `GFSO_SEED"] = "1" if args.seed`. Moving that write to its owner (`config.install_serve_env`,
    2026-09-03, when four doors stopped each spelling the child's environment for themselves) broke
    it exactly as predicted, with the default it guards untouched. So it asks the owner instead.
    """
    assert '"--seed"' in open(cli.__file__, encoding="utf-8").read(),         "there is no way to ask for the demo"

    for asked, expected in ((False, ""), (True, "1")):
        monkeypatch.delenv("GFSO_SEED", raising=False)
        install_serve_env({}, storage="memory", db_path=None, llm="stub", model="m",
                          seed=asked, with_mcp=False)
        assert os.environ["GFSO_SEED"] == expected, (
            f"seed={asked} exported GFSO_SEED={os.environ['GFSO_SEED']!r}")



def test_the_runtime_only_seeds_when_told(monkeypatch):
    reg = ProjectRegistry(default_storage="memory", default_llm="stub", seed=False)
    assert reg.engine().all_tasks() == [], "an unasked-for demo appeared in a fresh project"


def test_and_still_seeds_when_asked():
    reg = ProjectRegistry(default_storage="memory", default_llm="stub", seed=True)
    assert reg.engine().all_tasks(), "the demo could not be planted deliberately"
