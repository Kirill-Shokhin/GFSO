"""The judge stood in a different directory depending on which door called it.

The dispatcher asked the graph first — the executor's registered directory, then the children's —
and only then the roster. The manual `validate_result` asked the roster first. Probed 2026-09-07
with an executor registered against `WORK` and a validator against `SCRATCH`: for one and the same
node the dispatcher sent the judge to `WORK` and `validate_result(node, validator="val-1")` sent it
to `SCRATCH`; on a node held by an unregistered person the manual door went to `SCRATCH` even with
no validator named.

The dispatcher's order is the one already paid for. Its own comment records the price: a stale
`val-1` from an older experiment pointed at a scratch directory, the root was judged there, the
report said "no implementation exists", and a false FAIL over seventeen criteria drove the run into
the rework loop that ended it (2026-08-21). The correction reached one of the two copies.

Both halves survive here. The graph answers first, because where the work IS is a fact about the
graph and the validator's registered directory is a fact about the roster, and only the first is
true by construction. The roster still answers — second — because a root is normally held by the
caller themselves, an id the roster does not know, and then the named validator's own directory is
what saves the call (HTTP door, 2026-09-02).
"""
from __future__ import annotations

import pytest

import gfso.tools as T
import gfso.tools_llm as TL
from gfso.delegate import AgentRegistry, judging_workdir
from gfso.core.types import TaskId
from tests.support import make_engine

_RISK = [{"item": "an unmodelled environment fault", "predictability": "EXTRAORDINARY"}]


@pytest.fixture
def box(tmp_path, monkeypatch):
    """An executor and a validator registered against DIFFERENT directories — the whole point."""
    (tmp_path / "WORK").mkdir()
    (tmp_path / "SCRATCH").mkdir()
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))
    reg = AgentRegistry(path=str(tmp_path / "agents.json"))
    reg.register("exec-1", "llm-executor", workdir=str(tmp_path / "WORK"))
    reg.register("val-1", "llm-validator", workdir=str(tmp_path / "SCRATCH"))
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "par", {"description": "parent", "accepted_risks": _RISK,
                             "criteria": [{"name": "g", "description": "G holds"}]},
                  assignee="a-human")
    T.create_task(e, "kid", {"description": "the work",
                             "criteria": [{"name": "k", "description": "K holds"}]},
                  assignee="exec-1", parent_id="par")
    T.map_criterion(e, "par", "kid", "g")
    yield e, reg, tmp_path
    e.stop()


@pytest.mark.parametrize("node", ["kid", "par"])
@pytest.mark.parametrize("named", [None, "val-1"])
def test_the_two_doors_agree_on_where_the_work_is(box, node, named):
    e, reg, tmp_path = box
    owner = judging_workdir(e, reg, TaskId(node), named_validator=named,
                            vcfg=(reg.get(named) if named else None))
    door = TL._registered_workdir(e, node, named)
    assert owner == door == str(tmp_path / "WORK"), (
        f"{node} with validator={named}: the owner says {owner}, the manual door says {door}. "
        f"A judge run against a directory that does not hold the delivery reports "
        f"'no implementation exists' — a false FAIL, which is worse than no validation at all")


def test_the_roster_still_answers_when_the_graph_cannot(box):
    """The other half. A node nobody registered, with no registered children either, has no graph
    fact to offer — and then the named validator's own directory is the answer, not a refusal."""
    e, reg, tmp_path = box
    T.create_task(e, "orphan", {"description": "held by a person", "accepted_risks": _RISK,
                                "criteria": [{"name": "o", "description": "O holds"}]},
                  assignee="a-person-not-on-the-roster")
    assert TL._registered_workdir(e, "orphan", "val-1") == str(tmp_path / "SCRATCH"), \
        "with nothing in the graph to go on, refusing while the roster holds the answer is the " \
        "call that was measured failing on the HTTP door"
