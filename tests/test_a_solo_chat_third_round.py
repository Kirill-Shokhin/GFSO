"""A solo chat, third round (fresh client s21, 2026-11-19): a DELIVER with the work uncommitted handed the base to a paid
validation, which FAILed; the go's own say (the work's branch) was replaced by the door's, and the person was left on
`gfso/<p>/work`; the client's PASS of the root was stopped as self-approval while the root is the person's to sign; the
client was led to run the sign-in itself; a stale queued run named a generation equal to itself as its cause."""
from __future__ import annotations

import json
import subprocess
import types

from gfso import delegate as D, doctor, tools_llm as TL
from gfso.adapters.llm import credentials
from gfso.core.graph.model import generation_of_task
from gfso.config import CALLER, Principal
from gfso.core.types import Mode, TaskId
from gfso.places import same_place
from gfso.mcp import protocol, server as S
from tests.test_a_solo_chat_writes_its_own_plan_and_the_person_gives_the_go import ASKED, _filled, _gone, no_model  # noqa: F401
from tests.support import hold_a_credential
from tests.test_the_mode_decides_who_holds_what import _engine, _goal
import gfso.in_chat as IC


def _repo(tmp_path):
    git = lambda *a, at=tmp_path: subprocess.run(["git", "-C", str(at), *a], capture_output=True, text=True,
                                                 check=True).stdout.strip()
    git("init", "-q", "-b", "main")
    git(*IDENT, "commit", "-q", "--allow-empty", "-m", "start")
    return git, git("rev-parse", "HEAD")


IDENT = ("-c", "user.email=a@b", "-c", "user.name=a")


def _started(e, start):
    e.graph.store_setting("chat_start:root", json.dumps({"branch": "main", "head": start}))


def test_a_delivery_of_the_start_with_the_work_elsewhere_carries_the_work(no_model, tmp_path):
    """The work committed on `gfso/<p>/work` in a linked worktree, the person's tree still on the start: the DELIVER
    carries the work's branch — the base was delivered, and FAILed, paid — and its
    notice says nothing of another branch, the commit being the work's."""
    e = _engine(Mode.SOLO)
    _gone(e, _filled(TL.plan(e, ASKED)["text"]))
    git, start = _repo(tmp_path)
    _started(e, start)
    assert IC._work_tip(e, TaskId("root"), str(tmp_path)) is None, "no work's branch: nothing delivered by inference"
    git("worktree", "add", "-q", "-b", "gfso/p/work", str(wt := tmp_path / "wt"))
    assert IC._work_tip(e, TaskId("root"), str(tmp_path)) is None, "the work's branch at the start: not the work"
    git(*IDENT, "commit", "-q", "--allow-empty", "-m", "work", at=wt)
    work = git("rev-parse", "gfso/p/work")
    at, tip = IC._work_tip(e, TaskId("root"), str(tmp_path))
    assert tip == work and same_place(at, wt), (at, tip)
    assert IC.not_the_work(e, at, work) == ""


def test_the_start_is_never_delivered_and_its_refusal_names_the_lifts(no_model, tmp_path):
    """Neither a dirty tree nor a word handed in the start: the refusal names committing on the work's branch, naming
    the place, and an empty commit for a work that changed nothing."""
    e = _engine(Mode.SOLO)
    _gone(e, _filled(TL.plan(e, ASKED)["text"]))
    git, start = _repo(tmp_path)
    _started(e, start)
    no = IC._unnamed(e, TaskId("root"), str(tmp_path))
    assert "commit it on `gfso/p/work`" in no and "place=<its path>" in no and "empty commit" in no, no
    assert "No validator" in no and "stand past" not in no, no


def test_the_persons_own_page_signs_the_root_with_no_words(no_model):
    e = _engine(Mode.SOLO)
    _gone(e, _filled(TL.plan(e, ASKED)["text"]))
    token = CALLER.set(Principal("user", ("user",), "session", "a page", "local"))
    try:
        assert TL._the_persons_move(e, TaskId("root"), "PASS") is None
    finally:
        CALLER.reset(token)
    assert TL._the_persons_move(e, TaskId("root"), "PASS")["refused"], "an agent's connection still needs their words"


def test_the_gos_own_say_survives_the_door():
    out = {"root_id": "root", "goal_as_given": "x", "say": "Work on gfso/p/work."}
    S._link_and_say("auto_decompose", out, "p", None)
    assert "Work on gfso/p/work." in out["say"] and "verbatim" in out["say"], out["say"]


def test_the_roots_pass_says_to_switch_the_person_back(no_model, tmp_path, monkeypatch):
    git = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a], capture_output=True, text=True, check=True)
    git("init", "-q", "-b", "main")
    git("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "start")
    git("switch", "-q", "-c", "gfso/p/work")
    e = _engine(Mode.SOLO)
    e.graph.store_setting("chat_start:root", json.dumps({"branch": "main", "head": ""}))
    monkeypatch.setattr(IC, "validator_workdir", lambda *a, **k: str(tmp_path))
    said = IC.back_to_their_branch(e, TaskId("root"))
    assert "git switch main" in said and "gfso/p/accepted" in said, said


def test_the_roots_verdict_under_solo_is_the_persons(no_model):
    e = _engine(Mode.SOLO)
    _gone(e, _filled(TL.plan(e, ASKED)["text"]))
    out = TL.TOOLS["signal"](e, "root", "PASS", "user")
    assert out.get("refused") and "user_said" in out["error"] and "get_verdict" in out["error"], out
    told = []
    real = e.emit_info
    e.emit_info = lambda kind, msg, *a, **k: (told.append(msg), real(kind, msg, *a, **k))[1]
    out = TL.TOOLS["signal"](e, "root", "PASS", "user", user_said="да, принимаю")
    assert "user_said" not in str(out.get("error", "")) and any("да, принимаю" in m for m in told), (out, told)


def test_the_person_runs_the_sign_in():
    assert "the person runs `! gfso credential claude --sign-in`" in protocol.BY_KIND["code"]
    assert len(protocol.BY_KIND["code"].encode()) <= 4080


def test_doctor_has_the_person_run_the_sign_in(monkeypatch, tmp_path):
    hold_a_credential(monkeypatch, tmp_path)
    credentials.put("claude", "token", None)
    monkeypatch.setattr(doctor, "local_word", lambda: False)
    monkeypatch.setattr(doctor, "docker_state", lambda: (True, "ok"))
    monkeypatch.setattr(doctor, "image_present", lambda tag: True)
    monkeypatch.setattr(doctor._config, "executions", lambda: {doctor.DEFAULT_EXECUTION: {"image": "img:1"}})
    assert "the person runs" in dict(doctor._execution_report()[0])["credential"]


def test_a_stale_queued_run_names_what_moved():
    e = _engine(Mode.SOLO)
    root, _ = _goal(e)
    told = []
    e.emit_info = lambda kind, msg, *a, **k: told.append(msg)
    t = e.graph.get_task(root.id)
    D.Dispatcher._fresh(types.SimpleNamespace(_engine=e), root.id, generation_of_task(t), ("DONE",))
    assert told and f"its state is {t.state.name}, not DONE" in told[-1] and "generation" not in told[-1], told


def test_the_work_held_by_a_linked_worktree_is_named_with_the_move_that_works(no_model, tmp_path):
    """`git switch gfso/p/work` at the top fails while a linked worktree holds the branch (rc 128): the notice names
    the move that works — a detached checkout, or the worktree removed first — and that move does work."""
    e = _engine(Mode.SOLO)
    git, start = _repo(tmp_path)
    git("worktree", "add", "-q", "-b", "gfso/p/work", str(tmp_path / "wt"))
    git(*IDENT, "commit", "-q", "--allow-empty", "-m", "work", at=tmp_path / "wt")
    said = IC.not_the_work(e, str(tmp_path), start)
    assert "git switch --detach gfso/p/work" in said and "remove that worktree" in said, said
    git("switch", "-q", "--detach", "gfso/p/work")
    assert git("rev-parse", "HEAD") == git("rev-parse", "gfso/p/work")


def test_a_root_passed_from_the_page_says_the_way_back_on_the_feed(no_model, tmp_path, monkeypatch):
    git, _ = _repo(tmp_path)
    git("switch", "-q", "-c", "gfso/p/work")
    e = _engine(Mode.SOLO)
    _gone(e, _filled(TL.plan(e, ASKED)["text"]))
    _started(e, "")
    monkeypatch.setattr(IC, "validator_workdir", lambda *a, **k: str(tmp_path))
    monkeypatch.setattr(TL._tools, "signal", lambda *a, **k: {"accepted": True})
    told = []
    e.emit_info = lambda kind, msg, *a, **k: told.append(msg)
    token = CALLER.set(Principal("user", ("user",), "session", "a page", "local"))
    try:
        TL.signal(e, "root", "PASS", "user")
    finally:
        CALLER.reset(token)
    assert any("git switch main" in m for m in told), told
