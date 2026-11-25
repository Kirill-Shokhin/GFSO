"""The graph read carries the depth above which the user-agent holds the plan as the engine computes it: SEMI's default
is the middle of the plan's depth, which the recorded `boundary` (None) never says. The page read the record and
guessed 1, so under SEMI it counted a depth-1 node the user holds as the system's — its calls hidden, its PASS marked as
"closed by hand" (ui critic, 2026-11-13).

CONTROL: serve `engine.mode()` bare in `graph_read` and the first test goes red."""
from gfso import tools as T
from gfso.core.types import AgentId, Mode
from gfso.engine.validation import holder_boundary
from tests.support import REGISTER, criterion, make_engine


def _two_levels(mode, boundary=None):
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.workforce.publish_executor_pool({"exec-1": None, "exec-2": None})
    e.set_mode(mode, boundary, AgentId("user"))
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g")]})
    T.decompose(e, "root", [{"task_id": "root.a", "covers": ["g"], "spec": {"description": "a", "criteria": [criterion("a")]}}],
                accepted_risks=REGISTER)
    T.decompose(e, "root.a", [{"task_id": "root.a.x", "covers": ["a"], "spec": {"description": "x", "criteria": [criterion("x")]}}],
                accepted_risks=REGISTER)
    e.wait_idle()
    return e


def test_semi_by_default_says_the_engines_middle_not_the_records_none():
    e = _two_levels(Mode.SEMI)
    m = T.graph_read(e)["mode"]
    assert m["boundary"] is None and m["holds_above"] == holder_boundary(e.graph) == 1.5, m
    assert e.held_by_the_user_agent(1) is True


def test_a_boundary_set_by_hand_is_said_as_set_and_solo_holds_every_depth():
    assert T.graph_read(_two_levels(Mode.SEMI, 2))["mode"]["holds_above"] == 2
    assert T.graph_read(_two_levels(Mode.SOLO))["mode"]["holds_above"] is None


def test_no_mode_reads_none():
    e = make_engine()
    assert T.graph_read(e)["mode"] is None
