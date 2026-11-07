"""`GFSO_SYSTEM_MODEL` moves every system-side role at once where a project sets none of its own, and the server says
which model it runs: a cheaper model chosen for the system that left one door on the stronger default would have the
stronger one hold the work. Every door asks one place, `Engine.system_model()` — the project's choice, else the knob."""
from __future__ import annotations

import inspect
import os
import subprocess
import sys

from fastapi.testclient import TestClient

from gfso import config, issuer, tools_llm
from gfso.api.server import create_app
from gfso.engine import Engine
from tests.test_integration import _engine

PROBE = ("import gfso.config as c; from tests.support import make_engine;"
         "print(c.MODEL_DEFAULT, make_engine().system_model())")


def _defaults(env_model: str | None) -> list[str]:
    env = {k: v for k, v in os.environ.items() if k != "GFSO_SYSTEM_MODEL"}
    if env_model:
        env["GFSO_SYSTEM_MODEL"] = env_model
    return subprocess.run([sys.executable, "-c", PROBE], env=env, capture_output=True, text=True,
                          check=True).stdout.split()


def test_the_knob_moves_the_plan_author_and_its_reviewer():
    assert _defaults("claude-haiku-5-5") == ["claude-haiku-5-5"] * 2


def test_unset_it_is_the_default_door():
    assert _defaults(None) == ["claude-sonnet-5-5"] * 2


def test_the_issuer_the_plans_author_and_its_reviewer_ask_the_one_place():
    for door in (issuer._ask, tools_llm.review_decomposition):
        assert "engine.system_model()" in inspect.getsource(door), door.__name__
    # …the plan's author through its own setting, which falls back to the one place (`planner_model`)
    assert "engine.planner_model()" in inspect.getsource(tools_llm.auto_decompose)
    assert "self.system_model()" in inspect.getsource(Engine.planner_model)


def test_the_server_says_which_model_plays_the_roles():
    with TestClient(create_app(_engine())) as c:
        assert c.get("/api/runtime").json()["system_model"] == config.MODEL_DEFAULT
