"""A solo chat's plan, second round (critic over 354554c): the page shows the agreed checks themselves before the go; a
plan with parts the person read and gave the go on is reviewed by that reading — no unannounced review by the system's
model holds its parts — and the go's say follows the plan's shape; every field of a root's packet, not its criteria
alone, changes only on the person's words (Inv-1); and a DELIVER of a commit off the work's branch is said."""
from __future__ import annotations

import subprocess

import pytest

from gfso import tools_llm as TL
from gfso.core.types import AgentId, Mode, Signal, SignalData, TaskId
from gfso.decompose import artifact as A
from tests.support import UNMODELLED_FAULT
from tests.test_a_solo_chat_writes_its_own_plan_and_the_person_gives_the_go import ASKED, _filled, _gone, no_model  # noqa: F401
from tests.test_the_go_only_adds_to_the_plan import GOAL, _plan
from tests.test_the_mode_decides_who_holds_what import _engine


def test_the_page_shows_the_agreed_checks_before_the_go(no_model):
    e = _engine(Mode.SOLO)
    TL.plan(e, plan=_filled(TL.plan(e, ASKED)["text"]))
    assert TL.written_plan(e.project_name)["root_criteria"] == [
        {"name": "counts", "description": "prints the line count",
         "check": [{"behaviour": "two lines in, 2 out", "command": "seq 2 | ./wc2", "expect": "2", "exact": True}]}]


def test_a_plan_with_parts_the_person_read_is_reviewed_by_that_reading(no_model, monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "1")
    e = _engine(Mode.SOLO)
    out = TL.auto_decompose(e, plan=A.render(GOAL, _plan(), {}), user_said="да, по частям")
    kids = [str(c.id) for c in e.graph.get_active_children(TaskId("root"))]
    assert kids and all(k in out["say"] for k in kids) and "every part has passed" in out["say"], out["say"]
    e.send_signal_sync(SignalData(signal=Signal.ACCEPT, task_id=TaskId(kids[0]), source=AgentId("user")))
    e.wait_idle()
    assert e.graph.get_state(TaskId(kids[0])).name == "EXECUTING", "a part held on a review nobody announced"


@pytest.mark.parametrize("verb,args", [
    ("revise", {"spec": None}),
    ("edit_scope", {"scope": ["no options — not asked"]}),
    ("edit_accepted_risks", {"accepted_risks": [UNMODELLED_FAULT.to_dict()]}),
])
def test_every_field_of_the_roots_packet_is_the_persons(no_model, verb, args):
    e = _engine(Mode.SOLO)
    root, _ = _gone(e, _filled(TL.plan(e, ASKED)["text"]))
    if verb == "revise":
        spec = {"description": "count words instead", "criteria": [
            {"name": c.name, "description": c.description, "check": [p.to_dict() for p in c.check]}
            for c in root.spec.criteria]}
        args = {"spec": spec}
    before = e.graph.get_task(root.id).spec
    out = TL.TOOLS[verb](e, "root", **args)
    assert "user_said" in str(out) and e.graph.get_task(root.id).spec == before, out
    said = []
    real = e.emit_info
    e.emit_info = lambda kind, msg, *a, **k: (said.append(msg), real(kind, msg, *a, **k))[1]
    TL.TOOLS[verb](e, "root", **args, user_said="да, меняй")
    assert e.graph.get_task(root.id).spec != before and any("да, меняй" in m for m in said), said


def test_a_delivery_off_the_works_branch_is_said(tmp_path):
    git = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a], capture_output=True, text=True, check=True).stdout
    ident = ("-c", "user.email=a@b", "-c", "user.name=a")
    git("init", "-q", "-b", "main")
    git(*ident, "commit", "-q", "--allow-empty", "-m", "start")
    start = git("rev-parse", "HEAD").strip()
    git("branch", "gfso/p/work")
    git("worktree", "add", "-q", str(tmp_path / "wt"), "gfso/p/work")
    subprocess.run(["git", "-C", str(tmp_path / "wt"), *ident, "commit", "-q", "--allow-empty", "-m", "work"], check=True)
    said = TL.not_the_work(_engine(Mode.SOLO), str(tmp_path), start)
    assert "`main`" in said and "gfso/p/work" in said and "deliver again" in said, said
    git("worktree", "remove", "--force", str(tmp_path / "wt"))
    git("switch", "-q", "gfso/p/work")
    assert TL.not_the_work(_engine(Mode.SOLO), str(tmp_path), git("rev-parse", "HEAD").strip()) == ""
