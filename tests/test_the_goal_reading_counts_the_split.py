"""What decides a node's goal obligations is what its validation runs — its own pinned checks and its MAPPED children's
(§2.4 joint sufficiency, Thm 1, §8.3; `parts_procedure`). Judged on the node's own pins alone, the Level-2 check opened
16–55 "undecided" findings on plans that reached held-out 1.0 (scratchpad/gatecal, 2026-10-31).

An obligation decided by a child's pin stays decided only while that pin stands: the reading keeps every obligation the
goal carries and the deciders it was judged against, and re-checks the whole list once one of them is gone or changed."""
import dataclasses
import json

from gfso.critic import runner as R
from gfso.core.types import AgentId, CriterionMapping, TaskId
from tests.support import REGISTER_SPLIT, make_engine, spec

import pytest


@pytest.fixture
def engine():
    e = make_engine(llm=None, check_interval=10_000)
    e.start()
    e.assign_task(TaskId("root"), spec("goal", "c1", "c2"), AgentId("agent"))
    e.wait_idle()
    e.decompose_task(TaskId("root"), [(TaskId("kid"), spec("part", "k1"), AgentId("agent")),
                                      (TaskId("aside"), spec("aside", "a1"), AgentId("agent"))],
                     [CriterionMapping("c1", TaskId("kid")), CriterionMapping("c2", TaskId("aside"))],
                     register=REGISTER_SPLIT)
    e.wait_idle()
    # …and `aside` unmapped since, as a remapping leaves a child: still active, its pins no longer run for the root
    r = e.graph.get_task(TaskId("root"))
    e._graph.save_task(dataclasses.replace(r, criterion_mappings=r.criterion_mappings[:1]))
    yield e
    e.stop()


def _root(e):
    return e.graph.get_task(TaskId("root"))


def _repin(e, tid, command):
    """The child's one criterion with its pinned check rewritten — what decided an obligation may be gone."""
    t = e.graph.get_task(TaskId(tid))
    c = t.spec.criteria[0]
    c2 = dataclasses.replace(c, check=tuple(dataclasses.replace(p, command=command) for p in c.check))
    e._graph.save_task(dataclasses.replace(t, spec=dataclasses.replace(t.spec, criteria=(c2,))))


def test_the_split_shown_is_the_mapped_childrens_pins(engine):
    shown = R._split_criteria(engine, _root(engine))
    assert "[kid] k1" in shown and "    " in shown, "a mapped child's criterion with its pinned checks"
    assert "aside" not in shown, "an unmapped child's pins the parent's validation never runs"


def test_a_pin_added_keeps_what_was_decided_and_one_rewritten_reopens_it(engine):
    whole = ({"obligation": "sorts", "admits": "a"}, {"obligation": "stable", "admits": "b"})
    rec = {"undecided_obligations": [whole[1]], "goal_obligations": list(whole), "deciders": R._deciders(engine, _root(engine))}
    assert R._to_recheck(engine, _root(engine), rec) == (whole[1],), "nothing left: only the open one is re-checked"

    _repin(engine, "aside", "echo other")
    assert R._to_recheck(engine, _root(engine), rec) == (whole[1],), "an unmapped child decides nothing, so nothing left"

    _repin(engine, "kid", "echo other")
    assert R._to_recheck(engine, _root(engine), rec) == whole, "the mapped child's pin changed: every obligation again"


def test_a_record_without_the_whole_reading_is_read_afresh(engine):
    """It held only what was still open: what it had decided would be lost for good."""
    rec = {"goal_read": True, "goal_text": _root(engine).spec.description,
           "undecided_obligations": [{"obligation": "x", "admits": "y"}]}
    assert R._goal_changed(rec, _root(engine))
    assert not R._goal_changed({**rec, "goal_obligations": []}, _root(engine))


def test_the_reader_sees_what_a_deciding_pin_feeds(engine):
    """A probe over an `{inputs}` file decides what the file holds; named only by `name@hash`, it read as deciding nothing."""
    for tid, sql in (("kid", "SELECT 1 NOT BETWEEN 0 AND 2;"), ("aside", "SELECT 'unmapped';")):
        t = engine.graph.get_task(TaskId(tid))
        c = t.spec.criteria[0]
        c2 = dataclasses.replace(c, check=tuple(dataclasses.replace(p, inputs=(("q.sql", sql),)) for p in c.check))
        engine._graph.save_task(dataclasses.replace(t, spec=dataclasses.replace(t.spec, criteria=(c2,))))
    shown = R._inputs_section(engine, _root(engine))
    assert "NOT BETWEEN" in shown and shown.count("## q.sql@") == 1
    assert "unmapped" not in shown


def test_the_first_reading_is_decided_against_the_pins_files_and_kept_whole(engine, monkeypatch):
    """The goal is read without the files (shown them, the reading fragmented: 125 obligations for 45); what it names is
    then decided against them, and the record keeps every obligation read."""
    mined = [{"obligation": "NOT BETWEEN", "admits": "a"}, {"obligation": "DELETE with no WHERE", "admits": "b"}]
    prompts, rechecked = [], []

    class _LLM:
        def complete(self, prompt, context=""):
            prompts.append(prompt)
            return json.dumps({"gaps": mined})

    monkeypatch.setattr(R, "SUFFICIENCY_READINGS", 1)
    monkeypatch.setattr(R, "_still_undecided", lambda e, t, llm, prior, **k: rechecked.append(prior) or prior[1:])
    plain = R._undecided_obligations(engine, _root(engine), _LLM())
    assert "k1" not in prompts[-1] and "THE CRITERIA" not in prompts[-1], "the goal alone: the list is the goal's"
    assert rechecked == [tuple(mined)] and plain.whole == tuple(mined), "every obligation read is decided, then kept whole"

    test_the_reader_sees_what_a_deciding_pin_feeds(engine)
    found = R._undecided_obligations(engine, _root(engine), _LLM())
    assert "NOT BETWEEN 0 AND 2" not in prompts[-1], "the goal is read without the files"
    assert list(found) == mined[1:] and found.whole == tuple(mined)
    assert R._goal_record(engine, _root(engine), found, None)["goal_obligations"] == mined


def test_authoring_stores_the_whole_reading_with_its_deciders(engine):
    mined = ({"obligation": "sorts", "admits": "a"},)
    R.record_goal_reading(engine, _root(engine), mined)
    rec = json.loads(engine._graph._storage.get_critique(TaskId("root")))
    assert rec["goal_obligations"] == [{"obligation": "sorts", "admits": "a"}]
    assert rec["deciders"] == R._deciders(engine, _root(engine)) and not R._goal_changed(rec, _root(engine))


def test_the_obligations_are_decided_in_batches(engine):
    """~300 obligations in one haiku call: 287 left open where the next reading of the same plan left 43."""
    asked = []

    class _LLM:
        def complete(self, prompt, context=""):
            n = prompt.count("\n" + str(len(asked) and 1) + ". ") and 0
            listed = [l for l in prompt.splitlines() if l[:1].isdigit() and ". " in l]
            asked.append(len(listed))
            return json.dumps({"decided": [l.split(".")[0] for l in listed][1:]})

    prior = tuple({"obligation": f"o{i}", "admits": "x"} for i in range(45))
    left = R._still_undecided(engine, _root(engine), _LLM(), prior)
    assert asked == [R.DECIDE_BATCH, R.DECIDE_BATCH, 45 - 2 * R.DECIDE_BATCH]
    assert [g["obligation"] for g in left] == ["o0", "o20", "o40"], "each batch numbered from 1, kept by its own answer"


def test_the_authoring_s_reading_never_writes_over_a_review(engine):
    """Over a standing review the open list replaced the whole reading, its verdicts and disputes (critic over 68a895d)."""
    stood = {"goal_read": True, "goal_text": _root(engine).spec.description, "criteria_verdicts": [{"criterion": "c1"}],
             "goal_obligations": [{"obligation": "sorts"}, {"obligation": "stable"}], "undecided_obligations": []}
    engine._graph._storage.store_critique(TaskId("root"), json.dumps(stood))
    R.record_goal_reading(engine, _root(engine), ({"obligation": "stable", "admits": "x"},))
    assert json.loads(engine._graph._storage.get_critique(TaskId("root"))) == stood
