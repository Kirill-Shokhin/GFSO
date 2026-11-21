"""Who checks a node is its issuer's decision (§10.2), and a decision has its record (Thm 11): each choice is kept with its
author, the choice, the words or none, the time and its place in the signal log — the chosen set its projection — so a
choice made with no words leaves no less than one made with them, and a fresh engine on the same store reads the same."""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.adapters.storage.sqlite import SqliteStorage
from gfso.core.types import AgentId, Mode, TaskId
from tests.support import criterion, make_engine, REGISTER


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _engine(path):
    e = make_engine(storage=SqliteStorage(str(path)), validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    return e


def test_a_choice_of_who_checks_is_kept_with_its_author_and_time_words_or_none(tmp_path):
    e = _engine(tmp_path / "g.db")
    e.set_mode(Mode.SOLO, None, AgentId("user"))
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g")]})
    T.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "part", "criteria": [criterion("k")]},
                             "assignee": "user", "covers": ["g"]}], accepted_risks=REGISTER)
    e.set_checker(TaskId("kid"), "validator", AgentId("user"), "")
    e.set_checker(TaskId("kid"), "self", AgentId("user"), "хватит")
    made = e.checker_choices(TaskId("kid"))
    assert [(m["by"], m["checker"], m["said"]) for m in made] == [("user", "validator", ""), ("user", "self", "хватит")]
    assert all(m["at"] and isinstance(m["log_at"], int) for m in made)
    assert made[0]["log_at"] <= made[1]["log_at"]
    assert T.get_task(e, "kid")["checker_chosen"] == made
    # …the record decides, not the older chosen-set setting: a stale setting naming the node changes nothing
    e._storage.store_setting("validator_chosen", '["kid"]')
    assert "kid" not in e.validators_chosen() and not e.observed_here(TaskId("kid"))
    e.stop()
    again = _engine(tmp_path / "g.db")
    assert again.checker_choices(TaskId("kid")) == made
    assert (str(TaskId("kid")) in again.validators_chosen()) == (made[-1]["checker"] == "validator")
    again.stop()


def test_a_refused_choice_leaves_no_record(tmp_path):
    e = _engine(tmp_path / "g.db")
    e.set_mode(Mode.SOLO, None, AgentId("user"))
    T.create_task(e, "root", {"description": "goal", "criteria": [criterion("g")]})
    T.decompose(e, "root", [{"task_id": "kid", "spec": {"description": "part", "criteria": [criterion("k")]},
                             "assignee": "user", "covers": ["g"]}], accepted_risks=REGISTER)
    with pytest.raises(ValueError):
        e.set_checker(TaskId("kid"), "validator", AgentId("someone"), "")
    assert e.checker_choices(TaskId("kid")) == []
    e.stop()
