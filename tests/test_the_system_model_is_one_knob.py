"""`GFSO_SYSTEM_MODEL` moves every system-side role at once, and the server says which model it runs: a cheaper
model chosen for the system that left one door on the stronger default would have the stronger one hold the work."""
from __future__ import annotations

import inspect
import os
import subprocess
import sys

from fastapi.testclient import TestClient

from gfso import config, issuer
from gfso.api.server import create_app
from tests.test_integration import _engine

PROBE = ("import inspect, gfso.config as c, gfso.tools_llm as t, gfso.issuer as i;"
         "print(c.MODEL_DEFAULT,"
         " inspect.signature(t.auto_decompose).parameters['model'].default,"
         " inspect.signature(t.review_decomposition).parameters['model'].default)")


def _defaults(env_model: str | None) -> list[str]:
    env = {k: v for k, v in os.environ.items() if k != "GFSO_SYSTEM_MODEL"}
    if env_model:
        env["GFSO_SYSTEM_MODEL"] = env_model
    return subprocess.run([sys.executable, "-c", PROBE], env=env, capture_output=True, text=True,
                          check=True).stdout.split()


def test_the_knob_moves_the_plan_author_and_its_reviewer():
    assert _defaults("claude-haiku-5-5") == ["claude-haiku-5-5"] * 3


def test_unset_it_is_the_default_door():
    assert _defaults(None) == ["claude-sonnet-5-5"] * 3


def test_the_issuer_asks_the_same_default():
    assert "MODEL_DEFAULT" in inspect.getsource(issuer._ask)


def test_the_server_says_which_model_plays_the_roles():
    with TestClient(create_app(_engine())) as c:
        assert c.get("/api/runtime").json()["system_model"] == config.MODEL_DEFAULT
