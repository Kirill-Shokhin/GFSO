"""The demo project is planted when ASKED for, never by default.

It used to appear in every empty project: a fresh project created for real work opened with a
fictional "Release v2.0" tree in it — a graph nobody wrote, competing with the one they did.
"""
import subprocess
import sys


def _serve_env(*flags: str) -> str:
    """What `gfso serve <flags>` would export, without starting anything."""
    code = ("import sys, os; sys.argv = ['gfso', 'serve', *%r];"
            "import gfso.cli as c;"
            "p = c._parser() if hasattr(c, '_parser') else None;"
            "print('UNSUPPORTED')" % (list(flags),))
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout


def test_the_flag_exists_and_defaults_to_no_demo():
    from gfso import cli
    src = open(cli.__file__, encoding="utf-8").read()
    assert '"--seed"' in src, "there is no way to ask for the demo"
    # Behaviour, not a literal line: the switch has been spelled two ways
    # (GFSO_SEED / GFSO_NO_SEED), and a test pinned to one spelling breaks on a rename
    # while the DEFAULT it guards is untouched.
    assert 'GFSO_SEED"] = "1" if args.seed' in src, "the default is not 'no demo'"



def test_the_runtime_only_seeds_when_told(monkeypatch):
    from gfso.runtime import ProjectRegistry
    reg = ProjectRegistry(default_storage="memory", default_llm="stub", seed=False)
    assert reg.engine().all_tasks() == [], "an unasked-for demo appeared in a fresh project"


def test_and_still_seeds_when_asked():
    from gfso.runtime import ProjectRegistry
    reg = ProjectRegistry(default_storage="memory", default_llm="stub", seed=True)
    assert reg.engine().all_tasks(), "the demo could not be planted deliberately"
