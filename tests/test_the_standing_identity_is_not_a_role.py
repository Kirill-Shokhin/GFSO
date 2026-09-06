"""`agent` is what every door gives an unnamed caller, so it cannot also be a registered role.

Two consequences of the same registration were measured a day apart, both by strangers, neither of
whom was trying to find this:

* As an `llm-validator`, it made the executing identity the one whose signature closes the seam —
  the product's single promise, off, for every node on the server. (Closed at the gate: a
  registration cannot make an id independent of itself. See
  `test_registering_yourself_as_the_judge`.)
* Its registered `workdir` then became the directory unattended validation judged IN. A stranger on
  the MCP door had their delivery judged against another session's project — the temp directory a
  different tester had registered hours earlier — and their fabricated report was caught for
  entirely the wrong reason: *"The actual delivered codebase in the working directory is
  `w23cli_csvjson` — a CSV-to-JSON converter."* (wave 23, 2026-09-03)

A roster entry under the standing id is not a participant; it is a redefinition of the default
identity, for every session and project on a server whose roster is one shared fact. So it is refused
at the registration rather than patched at each consumer — otherwise every reader of the roster has
to know that one id means something else.
"""
from __future__ import annotations

import pytest

from gfso import tools_llm as TL
from gfso.tools import _agent_id
from tests.support import make_engine


@pytest.fixture(autouse=True)
def _own_roster(tmp_path, monkeypatch):
    """The roster is ONE server-wide file, so a test that writes to it must own the file.

    Without this these tests registered into whatever `GFSO_DATA_DIR` the suite happened to be
    pointing at — a temp directory belonging to an earlier test, already deleted — and the write
    came back `KeyError` from inside the registry. Green alone, red in the suite: the classic shape,
    and mine.
    """
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))


def test_registering_the_standing_identity_is_refused():
    e = make_engine()
    e.start()

    out = TL.register_agent(e, _agent_id(), "llm-validator", workdir=".")

    assert out.get("refused") is True, out
    assert "STANDING identity" in out.get("error", ""), out
    e.stop()


def test_the_refusal_hands_over_a_name_that_works():
    """A refusal with no exit is a wall — and the exit here is one word away."""
    e = make_engine()
    e.start()

    err = TL.register_agent(e, _agent_id(), "llm-executor", workdir=".")["error"]

    assert f"{_agent_id()}-val" in err and f"{_agent_id()}-exec" in err, err
    e.stop()


def test_and_the_roster_stays_empty_of_it():
    e = make_engine()
    e.start()

    TL.register_agent(e, _agent_id(), "llm-validator", workdir=".")

    assert _agent_id() not in TL.list_agents(e).get("agents", {})
    e.stop()


def test_an_ordinary_role_registers_exactly_as_before(tmp_path):
    """The negative control: this refusal is about ONE id, not about registration."""
    e = make_engine()
    e.start()

    out = TL.register_agent(e, "w-val-1", "llm-validator", workdir=str(tmp_path))

    assert out.get("refused") is not True, out
    assert "w-val-1" in TL.list_agents(e).get("agents", {})
    e.stop()
