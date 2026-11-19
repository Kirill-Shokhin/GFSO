"""Under `solo` with `perform="in_chat"` the person's own agent holds the work, so the plan's criteria are its own,
written with the person (§4.5, §11.5): `plan(request)` calls no model and hands the file to fill, and the go on it calls
none either. The go under `solo` and `semi` carries the person's own words, recorded with it: told "write to the person
now, before any other call", a fresh client summarized the plan in the go's own turn (s20g1). The work goes on the
branch the system names, said where the repository stands on one of theirs. AUTO keeps the system's planner.

Measured (s20g1, 2026-11-19): bare agent 0.5 min; solo in_chat 17.8 min, 10.25 of them the system writing a plan whose 9
criteria grew from 3 asked."""
from __future__ import annotations

import subprocess
import time

import pytest

from gfso import decompose as DEC, tools_llm as TL
from gfso.core.types import Mode, TaskId
from gfso.decompose import artifact as A
from tests.test_the_mode_decides_who_holds_what import _engine

ASKED = "Build ./wc2: it prints the number of lines it reads."
FILLED = {'name = ""\n\n#': 'name = "wc2"\n\n#', 'name = ""\ndescription = ""': 'name = "counts"\ndescription = "prints the line count"',
          'behaviour = ""': 'behaviour = "two lines in, 2 out"', 'command = ""': "command = 'seq 2 | ./wc2'",
          'expect = ""': 'expect = "2"'}


@pytest.fixture
def no_model(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the system's planner was asked")
    monkeypatch.setattr(TL._planning, "author", refuse)
    monkeypatch.setattr(TL._decompose, "default_llm", lambda *a, **k: type("NoModel", (), {"calls": []})())


def _filled(text: str) -> str:
    for a, b in FILLED.items():
        assert a in text, a
        text = text.replace(a, b, 1)
    return text


def test_plan_in_a_solo_chat_hands_the_file_to_fill_and_calls_no_model(no_model):
    out = TL.plan(_engine(Mode.SOLO), ASKED)
    assert out["yours"] and "user_said" in out["say"], out
    with pytest.raises(ValueError):
        A.parse(out["text"])                            # …unfilled, the go's own reading refuses it
    assert A.parse(_filled(out["text"]))["goal"] == ASKED, "the goal stays the person's words"


def test_the_go_on_the_filled_file_is_the_persons_and_calls_no_model(no_model):
    e = _engine(Mode.SOLO)
    text = _filled(TL.plan(e, ASKED)["text"])
    with pytest.raises(ValueError, match="user_said"):
        TL.auto_decompose(e, plan=text)
    assert not e.all_tasks(), "nothing is built on a go the person did not give"
    out = TL.auto_decompose(e, plan=text, user_said="да, делай так")
    root = e.graph.get_task(TaskId(out["root_id"]))
    assert [c.name for c in root.spec.criteria] == ["counts"] and not e.graph.get_active_children(root.id)
    assert root.spec.criteria[0].check[0].command == "seq 2 | ./wc2", "the check the person agreed is fixed as written"
    assert out["user_said"] == "да, делай так" and "gfso/p/work" in out["say"], out


def test_auto_keeps_the_systems_planner(monkeypatch):
    asked = []
    monkeypatch.setattr(TL._planning, "author", lambda request, *a, **k: asked.append(request) or "")
    TL.plan(_engine(Mode.AUTO), ASKED)
    TL.plan(_engine(Mode.SOLO), ASKED, model="claude-haiku-5-5")      # …and a solo chat that names a model
    for _ in range(200):
        if len(asked) == 2:
            break
        time.sleep(0.01)
    assert len(asked) == 2, asked


def test_a_chat_on_their_branch_hears_the_systems_branch(tmp_path):
    git = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a], capture_output=True, text=True, check=True)
    git("init", "-q", "-b", "main")
    git("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "start")
    e = _engine(Mode.SOLO)
    said = TL.on_their_branch(e, str(tmp_path))
    assert "`main`" in said and "git switch -c gfso/p/work" in said and "switch it back" in said, said
    git("switch", "-q", "-c", "gfso/p/work")
    assert TL.on_their_branch(e, str(tmp_path)) == ""


def _gone(e, text):
    out = TL.auto_decompose(e, plan=text, user_said="да, делай так")
    return e.graph.get_task(TaskId(out["root_id"])), out


def test_the_agreed_checks_change_only_on_the_persons_words(no_model):
    """After the go the agent rewrote the root's exact check into one an empty repository passes, the root went back to
    OFFERED, and nothing asked the person (critic over f5b1f88). One door: the revision of the packet."""
    e = _engine(Mode.SOLO)
    root, _ = _gone(e, _filled(TL.plan(e, ASKED)["text"]))
    weaker = [{"name": "counts", "description": "prints the line count",
               "check": [{"behaviour": "two", "command": "seq 2 | wc -l", "expect": "2", "exact": True}]}]
    out = TL.TOOLS["edit_criteria"](e, "root", weaker)
    assert "user_said" in str(out) and e.graph.get_task(root.id).spec.criteria[0].check[0].command == "seq 2 | ./wc2", out
    said = []
    real = e.emit_info
    e.emit_info = lambda kind, msg, *a, **k: (said.append(msg), real(kind, msg, *a, **k))[1]
    TL.TOOLS["edit_criteria"](e, "root", weaker, user_said="да, так проще")
    assert e.graph.get_task(root.id).spec.criteria[0].check[0].command == "seq 2 | wc -l"
    assert any("да, так проще" in m for m in said), said


def test_every_route_of_a_new_roots_go_passes_one_gate(no_model):
    e = _engine(Mode.SOLO)
    out = TL.auto_decompose(e, ASKED)
    assert out.get("yours") and not e.all_tasks(), "the request route in a solo chat asks no model either"
    spec = A.parse(_filled(out["text"]))["spec"]
    with pytest.raises(ValueError, match="user_said"):
        TL.auto_decompose(e, ASKED, spec=spec)
    assert not e.all_tasks()


def test_the_go_says_the_checks_did_not_run_over_the_base_on_this_host(no_model):
    e = _engine(Mode.SOLO)
    _, out = _gone(e, _filled(TL.plan(e, ASKED)["text"]))
    assert "this host" in str(out[TL._planning.PINS]["not_run"]), out


def test_a_check_that_already_holds_on_the_base_is_named(monkeypatch):
    monkeypatch.setattr(DEC, "on_the_base", lambda ex, todo: {
        (p.command, p.inputs): {"rc": 0, "stdout": "2\n", "stderr": "", "out": "2\n"} for _, p in todo})
    spec = A.parse(_filled(TL.YOURS.format(goal='"x"')).replace("./wc2", "wc -l"))["spec"]
    review = DEC.PinsOnTheBase(type("Place", (), {"files": "volume"})()).review(spec)
    assert review["holds_on_the_base"] and "decides nothing" in review["holds_on_the_base"][0], review


def test_the_accepted_branch_is_not_the_works(tmp_path):
    git = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a], capture_output=True, text=True, check=True)
    git("init", "-q", "-b", "gfso/p/accepted")
    git("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "start")
    assert "switch it back" in TL.on_their_branch(_engine(Mode.SOLO), str(tmp_path))
