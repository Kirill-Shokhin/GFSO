"""What a model child — a validator, an executor, an issuer — and every command it runs on the work start with holds none of
the system's own switches: a check measures the work, not the server it runs under (`config.env_without_secrets`).

Measured 2026-11-26: the validator ran this repository's default suite on a delivery and got failures where the same
commit in the tree passes; the server's own `GFSO_AGENTS_PATH`, set in the environment, failed two tests alone. Every
`GFSO_*` the server installed had reached the work's commands by inheritance. A key `data/serve.json` declares under
another name is declared for those commands and reaches them: an experiment's PYTHONPATH shim, without which its judge
scores make-built tasks 0 on Windows.

CONTROL: let `env_without_secrets` keep `GFSO_*` and the first test goes red."""
import os

import pytest

from gfso import config as C


@pytest.fixture
def env():
    was = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(was)


def _serve(tmp_path):
    """What `gfso serve` installs, under a declaration naming a switch of its own and a shim under another name."""
    C.install_serve_env({"GFSO_AGENTS_PATH": str(tmp_path / "agents.json"), "GFSO_L2_GATE": "1",
                         "PYTHONPATH": str(tmp_path / "shim")},
                        storage="sqlite", db_path=None, llm="claude", model="haiku", seed=False, with_mcp=True)
    C.mark_serving()
    C.select_project("p")


def test_judge_env_withholds_the_systems_switches_and_keeps_the_persons(env, tmp_path):
    os.environ.pop("PYTHONPATH", None)
    os.environ.update(HTTPS_PROXY="http://proxy:3128", SOMEONES_OWN="v")
    _serve(tmp_path)
    for got in (C.subprocess_env(credential={"ANTHROPIC_API_KEY": "k"}, extra={"GFSO_CALL": "c"}), C.env_without_secrets()):
        assert not {k for k in got if k.startswith("GFSO_")} - {"GFSO_CALL"}, "the server's switches reach the work"
        assert (got["HTTPS_PROXY"], got["SOMEONES_OWN"]) == ("http://proxy:3128", "v") and got.get("PATH")
    got = C.subprocess_env(credential={"ANTHROPIC_API_KEY": "k"}, extra={"GFSO_CALL": "c"})
    assert (got["ANTHROPIC_API_KEY"], got["GFSO_CALL"]) == ("k", "c"), "what a child is given by name is given"


def test_judge_env_keeps_what_the_installation_declared_for_its_runs(env, tmp_path):
    os.environ.pop("PYTHONPATH", None)
    _serve(tmp_path)
    assert C.subprocess_env()["PYTHONPATH"] == str(tmp_path / "shim"), "the declared shim does not reach the judge"
    os.environ["PYTHONPATH"] = "his"
    _serve(tmp_path)
    assert C.subprocess_env()["PYTHONPATH"] == "his", "an export wins over the declaration"
