"""A refused call writes nothing, and one bad signal does not end the engine.

Found on the agent door 2026-09-02, as one report that looked like three. A tester passed
`depends_on` as a LIST of producers. The rule that forbids it exists and is written down
(`tools._dep_of`: a Dep is carried by ONE criterion per seam, §10, and a list once surfaced as an
edge whose `from` was a list) — but `edit_criteria` spelled the same rule a second time, as
`TaskId(c["depends_on"])`, and `TaskId` is a string alias: it returned the list untouched. So:

* the malformed value entered the graph through a door whose sibling refuses it;
* the DAG check then raised `unhashable type: 'list'` inside the event loop, which died — and with
  it every later signal on that engine;
* and the next verb answered "the FSM refused ASSIGN in OFFERED", which is a sentence about a rule
  that was never consulted. The tester read it as the plan-repair toolkit being closed in the states
  nodes actually occupy, and spent the rest of the run working around a wall that was not there.

The project was unrepairable from that door afterwards. What is pinned here is the entrance and the
survival: the door refuses, and a step that raises is recorded rather than fatal.
"""
import pytest

from gfso import tools as T
from gfso.core.types import AgentId, Criteria, TaskId
from tests.support import make_engine


def _graph():
    e = make_engine(check_interval=10_000)
    e.start()
    T.create_task(e, "root", {"description": "r", "criteria": [{"name": "c", "description": "C"}],
                              "accepted_risks": [{"item": "an unmodelled environment fault",
                                                  "predictability": "EXTRAORDINARY"}]},
                  assignee="agent")
    T.create_task(e, "kid", {"description": "k", "criteria": [{"name": "k1", "description": "K"}]},
                  assignee="agent", parent_id="root")
    T.map_criterion(e, "root", "kid", "c")
    return e


def test_edit_criteria_refuses_a_list_of_producers_at_the_door():
    """The same rule `_spec_from` already enforces — one owner, not one owner and one lookalike."""
    e = _graph()
    out = T.edit_criteria(e, "kid", [{"name": "dep__p", "description": "d",
                                      "depends_on": ["root", "other"]}], agent="agent")
    assert out.get("refused") or out.get("error"), "a list of producers is refused, not stored"
    assert "one criterion" in str(out.get("error", "")).lower() or "§10" in str(out.get("error", ""))
    kept = [c.name for c in e.get_task("kid").spec.criteria]
    assert kept == ["k1"], "…and the contract it refused to change is untouched"
    e.stop()


def test_the_engine_survives_the_step_that_actually_killed_it():
    """The exact value that ended a run: a criterion whose producer is a LIST, straight at the engine.

    The door now refuses it (above), so this comes in past the door — which is where the next
    malformed value will come from too. The DAG check raises `unhashable type: 'list'` on it; what
    must not happen is the pump dying with it, because everything after that answered about a rule
    that was never consulted."""
    e = _graph()
    with pytest.raises(ValueError) as refusal:
        e.edit_criteria(TaskId("kid"), (Criteria("dep__p", "d", depends_on=["root"]),),
                        AgentId("agent"))
    # …and the refusal does not blame a rule that was never consulted
    assert "the FSM refused" not in str(refusal.value)
    assert "dropped" in str(refusal.value)

    T.signal(e, "kid", "ACCEPT", "agent")            # …the engine is still serving
    e.wait_idle()
    assert e.get_task("kid").state.name == "EXECUTING"
    e.stop()


def test_taking_a_node_says_what_it_still_waits_for():
    """§14.3 admits ACCEPT whatever the seams say, and the engine is not narrower than the canon.

    What the reply owed and did not give was the rest of the truth: two testers watched a graph show
    EXECUTING for nodes that provably could not start, and their executor found out by hitting a
    missing input and BLOCKing (2026-09-02, CLI and HTTP doors).
    """
    e = _graph()
    T.add_dependency(e, "root", "kid", glue="kid reads what root writes")
    out = T.signal(e, "kid", "ACCEPT", "agent")
    assert out["accepted"] and out["state"] == "EXECUTING"      # taking it is allowed
    assert out["cannot_start_yet"] == ["root"]
    assert "BLOCK" in out["cannot_start_note"]
    e.stop()
