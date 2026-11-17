"""«должно ставиться одной командой» (the author, 2026-11-13): `pipx run gfso setup` / `uvx gfso setup` runs setup from
a throwaway environment, which installs this release to stay with the same tool and runs the installed setup — the
agent door must name an executable that outlives the throwaway one."""
import subprocess
from types import SimpleNamespace as NS

from gfso import __version__
from gfso.doctor import stay, throwaway


def test_a_throwaway_environment_is_told_from_an_installed_one():
    assert throwaway("/home/u/.local/pipx/.cache/9f2a1b/") == "pipx"
    assert throwaway(r"C:\Users\u\pipx\.cache\9f2a1b") == "pipx"
    assert throwaway("/home/u/.cache/uv/archive-v0/AbC123") == "uv"
    assert throwaway("/home/u/.local/pipx/venvs/gfso") is None
    assert throwaway(r"C:\Users\u\anaconda3\envs\GFSO") is None


def test_it_installs_this_release_to_stay_then_runs_the_installed_setup(monkeypatch):
    monkeypatch.delenv("GFSO_INSTALL_SPEC", raising=False)
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        return NS(returncode=0, stdout="/home/u/.local/bin\n")
    assert stay("pipx", False, run) == 0
    assert calls[0] == ["pipx", "install", "--force", f"gfso=={__version__}"]
    assert calls[-1][1:] == ["setup"] and calls[-1][0].replace("\\", "/").startswith("/home/u/.local/bin/gfso")
    assert ["pipx", "ensurepath"] in calls, "a fresh shell finds the bare `gfso` the next lines name"
    calls.clear()
    assert stay("uv", True, run) == 0 and calls[0][:3] == ["uv", "tool", "install"] and calls[-1][-1] == "--desktop"
    assert stay("pipx", False, lambda argv, **kw: NS(returncode=2, stdout="")) == 2
