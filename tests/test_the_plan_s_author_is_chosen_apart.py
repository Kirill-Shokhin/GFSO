"""The plan's AUTHOR runs on a model the project names apart from the system's (`set_mode(planner_model=)`): a split's
content is its author's (§4.5) and the form the apparatus's — a plan authored once by a stronger model, then executed,
judged and repaired by the system's (measured 2026-11-01: sonnet's plans lead haiku's on structure, haiku's pipeline
leads on pins). Unset, the author is the system's model, as before."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

import gfso.tools_llm as TL
from gfso.decompose import planning
from tests.support import make_engine


def _e():
    return make_engine()


def test_unset_the_author_is_the_systems_model():
    e = _e()
    TL.set_mode(e, system_model="claude-haiku-5-5")
    assert e.planner_model() == "claude-haiku-5-5"


def test_named_the_author_runs_on_it_and_the_rest_stays_the_systems():
    e = _e()
    TL.set_mode(e, system_model="claude-haiku-5-5", planner_model="claude-sonnet-5-5")
    assert e.planner_model() == "claude-sonnet-5-5" and e.system_model() == "claude-haiku-5-5"
    assert e.settings()["planner_model"] == "claude-sonnet-5-5"


def test_the_authoring_verb_asks_the_authors_model(monkeypatch):
    e = _e()
    TL.set_mode(e, system_model="claude-haiku-5-5", planner_model="claude-sonnet-5-5")
    asked = []
    monkeypatch.setattr(TL._decompose, "default_llm", lambda model, **k: asked.append(model) or (_ for _ in ()).throw(
        RuntimeError("stop after the model is chosen")))
    with pytest.raises(RuntimeError, match="stop after the model is chosen"):
        TL.auto_decompose(e, request="sort a file")
    assert asked == ["claude-sonnet-5-5"]


@pytest.mark.parametrize("verb", ["plan", "refine_plan"])
def test_the_plan_file_is_reviewed_on_the_systems_model_not_its_authors(monkeypatch, verb):
    """A planner named stronger authors the file; its Level-2 review stays the system's — else naming opus as the
    author paid opus for every review too (critic)."""
    e = _e()
    TL.set_mode(e, system_model="claude-haiku-5-5", planner_model="claude-sonnet-5-5")
    got = {}
    monkeypatch.setattr(TL._planning, "author", lambda req, model, ex, depth, review, *a, **k: got.update(
        author=model, review=review) or "")
    monkeypatch.setattr(TL._planning, "refine", lambda text, note, model, review, *a, **k: got.update(
        author=model, review=review) or "")
    monkeypatch.setattr(TL._planning, "text_of", lambda p: p)
    monkeypatch.setattr(TL, "_plan_written", lambda text: {})
    TL.plan(e, "sort a file") if verb == "plan" else TL.refine_plan(e, "x", "a note")
    assert got == {"author": "claude-sonnet-5-5", "review": "claude-haiku-5-5"}


def test_what_a_plan_spends_is_on_the_book_of_the_project_that_asked(monkeypatch):
    """The plan holds no node and its own engine goes with its verb: nothing booked the provider's calls, and a person
    read $0.00 spent over ten minutes of planning (rehearsal, 2026-11-03). Booked though the authoring fail."""
    e = _e()
    llm = type("L", (), {"calls": [{"model": "m", "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.5}]})()
    monkeypatch.setattr(planning._decompose, "default_llm", lambda *a, **k: llm)
    monkeypatch.setattr(planning._decompose, "decompose_into", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("cut")))
    with pytest.raises(RuntimeError, match="cut"):
        planning.author("sort a file", "m", ledger=e.record_llm_usage)
    assert sum(r.get("cost_usd") or 0 for r in e.graph._storage.get_usage()) == 0.5


def test_a_plan_asked_again_joins_the_one_under_way_and_reads_the_one_written(monkeypatch):
    """Its answer can be lost on the way while the verb goes on, no graph shows it, and each resend paid a whole plan."""
    monkeypatch.setattr(TL, "_PLANNING", {})
    calls, release = [], threading.Event()

    def write():
        calls.append(1)
        release.wait(5)
        return {"path": "p"}

    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(TL._once, ("k",), write)
        while not calls:
            time.sleep(0.01)
        second = pool.submit(TL._once, ("k",), write)
        release.set()
        assert first.result() == second.result() == {"path": "p"}
    assert TL._once(("k",), write) == {"path": "p"} and len(calls) == 1


def test_a_plan_that_failed_is_written_again(monkeypatch):
    monkeypatch.setattr(TL, "_PLANNING", {})
    calls = []
    assert TL._once(("k",), lambda: calls.append(1) or {"error": "no"}) == {"error": "no"}
    assert TL._once(("k",), lambda: calls.append(1) or {"path": "p"}) == {"path": "p"} and len(calls) == 2
