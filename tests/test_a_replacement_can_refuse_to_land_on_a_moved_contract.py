"""Read-modify-write with no version check is how a concurrent author's work disappears.

Wave 26 (2026-09-06). The MCP door reported "`project()` shows 13 of 17 criteria and my edit
destroyed the five it did not show". Probed: the projection truncates nothing — all seventeen come
back. What actually happened is what the tester themselves allowed for: a background
`auto_decompose` wrote criteria BETWEEN their read and their edit, and `edit_criteria` — whose whole
contract is to REPLACE the set — landed on a contract that had moved, dropping work nobody had seen.

So the refuted finding left a real residue, and this is it: the two wholesale-replacement verbs can
now be made conditional on the set the caller actually read. Opt-in — a caller authoring a fresh
contract has read nothing — and keyed on names, which is what a caller reads and quotes back.
"""
from __future__ import annotations

from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import UNMODELLED_FAULT, make_engine

_RISKS = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]


def _node(e):
    T.create_task(e, "root", {"description": "r",
                              "criteria": [{"name": "c1", "description": "C1"},
                                           {"name": "c2", "description": "C2"}],
                              "accepted_risks": _RISKS}, assignee="agent")
    e.wait_idle()


def test_an_edit_against_a_contract_that_moved_is_refused_and_says_what_moved():
    e = make_engine()
    e.start()
    _node(e)
    read = ["c1", "c2"]                                    # what the caller saw

    # …and somebody else authors a third criterion between the read and the edit
    assert not T.edit_criteria(e, "root", [{"name": "c1", "description": "C1"},
                                           {"name": "c2", "description": "C2"},
                                           {"name": "c3", "description": "C3, added meanwhile"}]
                               ).get("refused")
    e.wait_idle()

    out = T.edit_criteria(e, "root", [{"name": "c1", "description": "C1, reworded"},
                                      {"name": "c2", "description": "C2"}],
                          expect_criteria=read)

    assert out["refused"] is True and out["contract_moved"] is True, out
    assert out["added_since_you_read"] == ["c3"], out
    assert {c.name for c in e.get_task(TaskId("root")).spec.criteria} == {"c1", "c2", "c3"}, (
        "the refusal has to leave the graph exactly as it was")
    e.stop()


def test_an_edit_against_the_set_it_really_read_lands():
    """The negative control: the lock must not refuse the ordinary edit."""
    e = make_engine()
    e.start()
    _node(e)

    out = T.edit_criteria(e, "root", [{"name": "c1", "description": "C1, reworded"},
                                      {"name": "c2", "description": "C2"}],
                          expect_criteria=["c1", "c2"])
    e.wait_idle()

    assert not out.get("refused"), out
    assert [c.description for c in e.get_task(TaskId("root")).spec.criteria][0] == "C1, reworded"
    e.stop()


def test_without_the_token_nothing_changes():
    """Opt-in: a caller who passes no expectation gets the old behaviour, whatever moved."""
    e = make_engine()
    e.start()
    _node(e)

    out = T.edit_criteria(e, "root", [{"name": "only", "description": "the whole set now"}])
    e.wait_idle()

    assert not out.get("refused"), out
    assert {c.name for c in e.get_task(TaskId("root")).spec.criteria} == {"only"}
    e.stop()


def test_revise_carries_the_same_lock():
    """`revise` is the verb whose ENTIRE contract is wholesale replacement — it needed it more."""
    e = make_engine()
    e.start()
    _node(e)
    T.edit_criteria(e, "root", [{"name": "c1", "description": "C1"},
                                {"name": "c2", "description": "C2"},
                                {"name": "c3", "description": "C3, added meanwhile"}])
    e.wait_idle()

    out = T.revise(e, "root", {"description": "r", "criteria": [{"name": "c1", "description": "C1"}],
                               "accepted_risks": _RISKS}, agent="agent",
                   expect_criteria=["c1", "c2"])

    assert out["refused"] is True and out["added_since_you_read"] == ["c3"], out
    e.stop()
