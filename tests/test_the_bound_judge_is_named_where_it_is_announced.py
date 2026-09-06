"""If the reply announces a judge, it has to say WHICH judge and where it stands.

The roster is one server-wide fact — projects isolate graphs, not roles — so "an independent
validator is bound to this node" can mean a role somebody else registered for another project, in a
directory that holds none of this delivery. It then fails on every node, twice, and the delivery
waits on a verdict that is never coming.

FIVE strangers across three waves reported exactly this, and every one of them had to go read
`gfso log` to find out what had bound itself to their work (waves 23–25). One of them, an ordinary
user shipping a 200-line script, spent four minutes polling and named it as the second-worst thing
about the session: *"Projects are described as the isolation boundary of the whole product; the agent
roster isn't inside it."*

Naming it is not the isolation fix and does not pretend to be. It is the difference between a wait
you can diagnose in one read and one you can only diagnose by knowing which log to open.
"""
from __future__ import annotations

import pathlib
import tempfile

import pytest

from gfso import tools as T
from gfso.core.types import TaskId
from gfso.delegate import AgentRegistry, Dispatcher
from tests.support import UNMODELLED_FAULT, make_engine


@pytest.fixture(autouse=True)
def _own_roster(tmp_path, monkeypatch):
    """This test writes to the roster, so it owns the file rather than the installation's."""
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))


def _delivered_with_a_judge_on_the_roster(e, tmp_path, judge_project=None):
    """A node the announcement is actually made ABOUT: an INTERNAL child of an automated issuer.

    Three preconditions have to hold together or the sentence is never reached, and a test written
    without them would assert nothing at all. The node must not be a SEAM — a seam gets its own
    sentence first, and a root is always one. Its issuer must be automated, which is what makes an
    instrument's verdict the signal too. And an instrument must be published to the graph, which the
    dispatcher does once per round. Getting this wrong is how the first version of this file passed
    while testing nothing.
    """
    reg = AgentRegistry()
    reg.register("stranger-val", "llm-validator", model="sonnet",
                 workdir=str(tmp_path / "someone-elses-tree"), project=judge_project)
    e._graph.authorized_validators = {"stranger-val"}      # what the dispatcher publishes each round
    T.create_task(e, "root", {"description": "the parent",
                              "criteria": [{"name": "g", "description": "G"}],
                              "accepted_risks": [{"item": UNMODELLED_FAULT.item,
                                                  "predictability": "EXTRAORDINARY"}]},
                  assignee="agent")
    T.create_task(e, "root.kid", {"description": "an internal child — same Del as its parent",
                                  "criteria": [{"name": "c", "description": "C"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "root.kid", "g")
    e.wait_idle()
    assert not e.is_seam(e.get_task(TaskId("root.kid"))), "the probe built a seam, not an internal node"
    T.signal(e, "root.kid", "ACCEPT", "agent")
    # The binding is a fact the DISPATCHER owns and publishes; a door may not compose it (the layer
    # gate), so a probe that never runs a round is asking about a state the product never reaches.
    Dispatcher(e, reg, runner=lambda *a: None).dispatch_once()
    return T.signal(e, "root.kid", "DELIVER", "agent", result="built it")


def test_a_judge_from_no_project_is_named_with_its_directory(tmp_path, monkeypatch):
    e = make_engine()
    e.start()
    monkeypatch.setattr(type(e), "project_name", property(lambda self: "mine"), raising=False)

    out = _delivered_with_a_judge_on_the_roster(e, tmp_path)

    said = out.get("awaiting_verdict") or ""
    assert "an independent validator is bound" in said, (
        f"the probe never reached the announcement it is about: {said!r}")
    assert "'stranger-val'" in said, said
    assert "registered for NO project" in said, said
    assert "someone-elses-tree" in said, "the directory it judges in is the diagnosable fact"
    assert "register your own" in said, "the way out is not named"
    e.stop()


def test_a_judge_registered_for_this_project_carries_no_warning(tmp_path, monkeypatch):
    """The negative control: the ordinary case must not grow an alarm it has not earned."""
    e = make_engine()
    e.start()
    monkeypatch.setattr(type(e), "project_name", property(lambda self: "mine"), raising=False)

    out = _delivered_with_a_judge_on_the_roster(e, tmp_path, judge_project="mine")

    said = out.get("awaiting_verdict") or ""
    assert "an independent validator is bound" in said, said
    assert "registered for THIS project" in said, said
    assert "register your own" not in said, said
    e.stop()
