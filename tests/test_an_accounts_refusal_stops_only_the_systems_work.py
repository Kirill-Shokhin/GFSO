"""A refused account (its credential, its limit, its place) stops a project only where the system's own roles carry the
work: the stop keeps their calls from burning the clocks while nobody can answer. A graph people hold spends nothing by
itself, and a stop there froze the people's clocks for one person's AI review (ui's human-door probe, 2026-11-14).

CONTROL: make `Engine.system_carries_work` answer True always and the first test goes red."""
import pytest

from gfso import tools as T, tools_llm as TL
from gfso.adapters.llm import headless as H
from gfso.core.types import TaskId
from tests.support import REGISTER, criterion, hold_a_credential, make_engine
from tests.test_a_refused_account_stops_the_project import REFUSED_STREAM, _cli


@pytest.fixture
def people():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g")]}, assignee="alice")
    T.decompose(e, "root", [{"task_id": "root.a", "assignee": "bob", "covers": ["g"],
                             "spec": {"description": "a", "criteria": [criterion("a")]}}], accepted_risks=REGISTER)
    e.wait_idle()
    yield e
    e.stop()


@pytest.mark.parametrize("ended", ["unauthorized", "limit", "unavailable"])
def test_a_graph_people_hold_goes_on_past_a_refused_call(people, ended):
    people.record_llm_usage("L2-checker", [{"ended": ended, "error": "api_error: 403 Failed to authenticate"}],
                            TaskId("root"))
    assert people.paused() is None, people.paused()
    assert not people.system_carries_work()


def test_a_live_node_the_system_moves_for_stops_it(people):
    people.workforce.publish_roster({"bob": "llm-executor"})
    assert people.system_carries_work()
    people.record_llm_usage("executor", [{"ended": "unauthorized", "error": "403"}], TaskId("root.a"))
    assert people.paused() and "authentication" in people.paused()["why"], people.paused()


def test_a_finished_systems_node_carries_nothing(people):
    people.workforce.publish_roster({"bob": "llm-executor"})
    T.signal(people, "root.a", "CANCEL", "alice", reason="not needed")
    people.wait_idle()
    T.signal(people, "root.a", "CONFIRM_CANCEL", "bob", in_flight="nothing")
    people.wait_idle()
    assert not people.system_carries_work()


def test_the_ai_review_of_a_peoples_graph_answers_the_refusal_and_stops_nothing(people, monkeypatch, tmp_path):
    """The page's «AI review» button, through the real provider whose CLI says the account refused."""
    hold_a_credential(monkeypatch, tmp_path)
    _cli(monkeypatch, REFUSED_STREAM)
    monkeypatch.setattr(TL, "llm_factory", lambda model=None, execution=None: H.ClaudeCodeProvider(model))
    out = TL.TOOLS["review_decomposition"](people, task_id="root")
    assert people.paused() is None, people.paused()
    said = str(out)
    assert "authenticat" in said or "refused" in said, said[:600]
