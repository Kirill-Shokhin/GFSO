"""`gfso status` answered three questions nobody asked, and lost the one fact it exists to carry.

Wave 26 (2026-09-06), reported by two doors independently and left open:

* the *asserted by hand* mark **disappears while the project still has an unfinished node** — the
  marks were scraped out of `next_steps`, which reports them only on its COMPLETE branch, so the
  qualifier was present exactly when nobody needed it and gone while a run was live;
* `status` **does not take `actor=`** — every other frontier verb does — so a person driving their
  own graph reads `0 step(s) for you` beside a step that is theirs;
* `status <root>` prints that root's subtree and then **counts the whole project**, and asks the
  frontier about the whole project too: two scopes under one heading.

The first is the real one: the closure facts belong to the NODE, and the node now carries them.
"""
from __future__ import annotations

from gfso import driver
from gfso import tools as T
from tests.support import criterion, make_engine, REGISTER

_RISKS = REGISTER


def _one_branch_closed_by_hand(e):
    """One branch closed on a person's word; a sibling branch still in flight beside it.

    Both hang under the project's one root: a project has exactly one parentless node, because the
    root carries the goal's criteria and a second one would be a second verdict with no rule
    composing them. The questions here — the hand mark, the subtree scope, `actor=` — are about a
    SUBTREE against its project, which is exactly what `signed` and `live` are now.
    """
    T.create_task(e, "goal", {"description": "the goal",
                              "criteria": [criterion("c", "C"), criterion("d", "D")]}, assignee="exec-1")
    # …both children are admitted in one act, covering the goal, the split's register with them (§11.5, §9.2)
    T.decompose(e, "goal", [
        {"task_id": "signed", "spec": {"description": "signed off", "criteria": [criterion("c", "C")]},
         "assignee": "exec-1", "covers": ["c"]},
        {"task_id": "live", "spec": {"description": "still going", "criteria": [criterion("d", "D")]},
         "assignee": "somebody-else", "covers": ["d"]}], accepted_risks=_RISKS)
    e.wait_idle()
    T.signal(e, "signed", "ACCEPT", "exec-1")
    T.signal(e, "signed", "DELIVER", "exec-1", result="claimed done")
    # A criterion now carries the procedure that decides it (A1/§2), so the hand closure names
    # WHICH pinned command was run — nothing is decided by a probe invented at validation time.
    T.record_verdict(e, "signed", "PASS", reviewer="inspector",
                     observed={"c": {"note": "I ran it myself and read OK",
                                     "ran": ["check c"]}})
    T.signal(e, "signed", "PASS", "exec-1")
    e.wait_idle()


def _local(monkeypatch, e):
    monkeypatch.setattr(driver, "_through_server", lambda *a, **k: None)
    monkeypatch.setattr(driver, "build_engine_from_env", lambda: e)


def test_a_hand_closure_is_still_marked_while_the_project_is_unfinished(monkeypatch, capsys):
    e = make_engine(check_interval=10_000)
    e.start()
    _one_branch_closed_by_hand(e)
    _local(monkeypatch, e)

    assert driver.status([]) == 0
    out = capsys.readouterr().out

    assert "frontier: COMPLETE" not in out, "the fixture must be an UNFINISHED project"
    assert "ASSERTED BY HAND" in out, (
        "the qualifier vanished exactly while there was still work in the project — it is read "
        "from the node now, not from the completion answer")
    e.stop()


def test_the_counts_and_the_frontier_follow_the_root_the_tree_was_asked_for(monkeypatch, capsys):
    e = make_engine(check_interval=10_000)
    e.start()
    _one_branch_closed_by_hand(e)
    _local(monkeypatch, e)

    assert driver.status(["signed"]) == 0
    out = capsys.readouterr().out

    assert "live" not in out, "a subtree was asked for; the sibling branch is not part of the answer"
    assert "1 nodes under signed" in out, out
    assert "nodes total" not in out, "`total` is a claim about the project, not about this subtree"
    e.stop()


def test_the_frontier_can_be_asked_as_somebody_else(monkeypatch, capsys):
    """`actor=` — the human door's way of saying who is asking, which this verb dropped."""
    e = make_engine(check_interval=10_000)
    e.start()
    _one_branch_closed_by_hand(e)
    _local(monkeypatch, e)

    assert driver.status(["actor=somebody-else"]) == 0
    mine = capsys.readouterr().out

    assert "1 step(s) for you" in mine, mine

    assert driver.status(["actor=a-passer-by"]) == 0
    theirs = capsys.readouterr().out

    assert "0 step(s) for you" in theirs, (
        "the negative control: the step belongs to somebody-else, and asking as a stranger must "
        "not inherit it")
    e.stop()
