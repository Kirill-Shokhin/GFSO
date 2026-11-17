"""A settled node does not cross R′'s edge while the place its project's volumes stand in does not answer (a volume gone,
Docker down): the node, its verdict and its reopens stay — by `reopen` and by every verb that revises it.

Admitted over a volume gone, it erased the verdict, spent the reopen, and the project stopped "place down" at the node's
first round: §12.16 (ii) lets the engine refuse it, naming the requirement and the person's lift. One door, `_revise`:
a critic reopened the node through `edit_criteria` and `reassign` past a refusal standing in `reopen` alone."""
import pytest

from gfso import tools as T
from gfso.core.types import AgentId, CriterionMapping, Signal, State, TaskId, VOLUME
from tests.support import REGISTER_SPLIT, criterion, make_engine, spec
from tests.test_reopen import _drive_to_done, _parent_child

GONE = "its volume gfso-v is gone: the project's record holds its places there"
VERBS = {
    "reopen": lambda e: T.reopen(e, "n1", "boss"),
    "edit_criteria": lambda e: T.edit_criteria(e, "n1", [criterion("c2", "a new check")], agent="boss"),
    "reassign": lambda e: T.reassign(e, "n1", "w2"),
    "signal ASSIGN": lambda e: T.signal(e, "n1", "ASSIGN", "boss"),       # the raw door (critic: accepted, 0 → 1)
}


@pytest.fixture
def engine():
    e = make_engine(llm=None, check_interval=10_000)
    e.start()
    yield e
    e.stop()


def _call(e, verb):
    try:
        return VERBS[verb](e) or {}
    except ValueError as ex:
        return {"error": str(ex)}


@pytest.mark.parametrize("verb", VERBS)
def test_no_verb_reopens_over_a_place_gone(engine, verb):
    t = _drive_to_done(engine)
    engine.graph.store_setting(VOLUME + "places", "gfso-v")
    engine.probe_the_place_with(lambda p: GONE)
    out = _call(engine, verb)
    after = engine.graph.get_task(TaskId("n1"))
    assert GONE in str(out.get("error")) and "new goal" in str(out.get("error")), out
    assert after.state == State.DONE and after.reopens == t.reopens


def test_a_re_admission_does_not_reissue_a_settled_child_over_a_place_gone(engine):
    """A split re-admitted with a changed DONE child re-issues it under its id — an R′ reopen that never came through
    `_revise` (critic, measured 0 → 1); R′'s gate is what every such door reads, `refusal_for` included."""
    _parent_child(engine)
    engine.graph.store_setting(VOLUME + "places", "gfso-v")
    engine.probe_the_place_with(lambda p: GONE)
    assert GONE in (engine.refusal_for(TaskId("ch"), Signal.ASSIGN).why or "")
    with pytest.raises(Exception, match="gone"):
        engine.decompose_task(TaskId("root"), [(TaskId("ch"), spec("child goal, changed", "cc"), AgentId("w"))],
                              criterion_mappings=[CriterionMapping("rc", TaskId("ch"))], register=REGISTER_SPLIT)
    assert engine.graph.get_state(TaskId("ch")) == State.DONE and engine.graph.get_task(TaskId("ch")).reopens == 0


def test_an_answering_place_is_asked_once_a_minute_and_a_fix_is_read_at_once(engine):
    _drive_to_done(engine)
    engine.graph.store_setting(VOLUME + "places", "gfso-v")
    said, asked = [GONE], []
    engine.probe_the_place_with(lambda p: asked.append(p) or said[0])
    assert engine.reopen_refusal(TaskId("n1"))
    said[0] = None                                  # …the person brought it back
    for _ in range(3):
        assert engine.reopen_refusal(TaskId("n1")) is None
    assert len(asked) == 2


def test_an_edge_shut_for_good_is_not_told_to_bring_the_place_back(engine):
    """Reopens spent: restarting Docker would not lift it, so its own gate's words stand, at every door."""
    _drive_to_done(engine)
    t = engine.graph.get_task(TaskId("n1"))
    t.reopens = t.max_reopens
    engine.graph.save_task(t)
    engine.graph.store_setting(VOLUME + "places", "gfso-v")
    engine.probe_the_place_with(lambda p: GONE)
    assert "spent" in engine.reopen_refusal(TaskId("n1"))
    assert "does not answer" not in str(T.signal(engine, "n1", "ASSIGN", "boss").get("error"))


@pytest.mark.parametrize("probe, in_volume", [
    (lambda p: None, True),
    (None, True),
    (lambda p: "this host runs no dispatched work unattended", False),   # a host's place: a person may work it
])
def test_a_reopen_goes_on_where_the_place_answers(engine, probe, in_volume):
    _drive_to_done(engine)
    if in_volume:
        engine.graph.store_setting(VOLUME + "places", "gfso-v")
    if probe is not None:
        engine.probe_the_place_with(probe)
    out = T.reopen(engine, "n1", "boss")
    assert "error" not in out and engine.graph.get_task(TaskId("n1")).state == State.OFFERED
