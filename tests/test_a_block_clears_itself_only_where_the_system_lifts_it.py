"""A BLOCK on producers clears by itself only where the system makes its issuer's move.

The dispatcher lifts a dependency-ready block by its issuer's RESOLVE_BLOCK, and only where that issuer is a machine's
(§10.1: never a person's). `get_task` told a person's seam «when they pass, the block clears by itself»; its blocker
passed and the seam stayed BLOCKED (ui, 2026-11-26). Every reader asks one rule, `Engine.block_lifts_itself`.

CONTROL: let `block_lifts_itself` drop the issuer's kind and the person's test goes red.
"""
from gfso import tools as T
from gfso.core.types import TaskId
from tests.support import criterion, make_engine, REGISTER


def _blocked(issuer: str):
    """root (held by `issuer`) -> {a, c}; a, taken by a worker, BLOCKs on c."""
    e = make_engine()
    e.start()
    T.create_task(e, "root", {"description": "root", "criteria": [criterion("g", "G")]}, assignee=issuer)
    T.decompose(e, "root", [{"task_id": k, "spec": {"description": k, "criteria": [criterion("k" + k, k.upper())]},
                             "assignee": "worker", "covers": ["g"]} for k in ("a", "c")], accepted_risks=REGISTER)
    e.wait_idle()
    T.signal(e, "a", "ACCEPT", "worker")
    T.signal(e, "a", "BLOCK", "worker", reason="a needs c", blocker_task_ids=["c"])
    e.wait_idle()
    return e, e.graph.get_task(TaskId("a"))


def test_a_persons_block_is_lifted_by_the_person_never_by_itself():
    e, a = _blocked("boss")
    assert e.block_clears_itself(a), "the producer finishing makes the block liftable"
    assert not e.block_lifts_itself(a), "no one lifts a person's block for him"
    said = T.get_task(e, "a")["blocked_by"]["what_now"]
    assert "clears by itself" not in said and "its issuer boss lifts it" in said and "RESOLVE_BLOCK" in said, said
    e.stop()


def test_a_machines_block_clears_by_itself_as_the_dispatcher_lifts_it():
    e, a = _blocked("boss")
    assert e.block_lifts_itself(a, {"boss": object()}), "a registered issuer's block is the system's to lift"
    e.stop()
