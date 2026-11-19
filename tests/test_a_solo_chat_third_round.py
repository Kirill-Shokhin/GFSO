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
from gfso.mcp import protocol, server as S
from tests.test_a_solo_chat_writes_its_own_plan_and_the_person_gives_the_go import ASKED, _filled, _gone, no_model  # noqa: F401
from tests.support import hold_a_credential
from tests.test_the_mode_decides_who_holds_what import _engine, _goal


def _repo(tmp_path):
    git = lambda *a, at=tmp_path: subprocess.run(["git", "-C", str(at), *a], capture_output=True, text=True,
                                                 check=True).stdout.strip()
    git("init", "-q", "-b", "main")
    git(*IDENT, "commit", "-q", "--allow-empty", "-m", "start")
    return git, git("rev-parse", "HEAD")


IDENT = ("-c", "user.email=a@b", "-c", "user.name=a")


def _started(e, start):
    e.graph.store_setting("chat_start:root", json.dumps({"branch": "main", "head": start}))


def test_a_delivery_of_the_start_with_the_work_elsewhere_names_where_the_work_is(no_model, tmp_path):
    """The work committed on `gfso/<p>/work` in a linked worktree, the person's own file untracked in theirs: the
    refusal is where the work is — never "commit notes.txt", which would put their file on their branch."""
    e = _engine(Mode.SOLO)
    _gone(e, _filled(TL.plan(e, ASKED)["text"]))
    git, start = _repo(tmp_path)
    _started(e, start)
    git("worktree", "add", "-q", "-b", "gfso/p/work", str(tmp_path / "wt"))
    git(*IDENT, "commit", "-q", "--allow-empty", "-m", "work", at=tmp_path / "wt")
    for left in (["notes.txt"], []):               # …a clean tree too: the base was delivered, and FAILed, paid
        no = TL._nothing_committed(e, TaskId("root"), str(tmp_path), start, left)
        assert no and "gfso/p/work" in no and "deliver again" in no and "commit them" not in no, no


def test_a_dirty_tree_with_no_work_elsewhere_is_lifted_by_a_true_word(no_model, tmp_path):
    e = _engine(Mode.SOLO)
    _gone(e, _filled(TL.plan(e, ASKED)["text"]))
    git, start = _repo(tmp_path)
    _started(e, start)
    no = TL._nothing_committed(e, TaskId("root"), str(tmp_path), start, ["exts.py"])
    assert no and "commit them on `gfso/p/work`" in no and "nothing_to_commit=true" in no and "No validator" in no, no
    assert TL._nothing_committed(e, TaskId("root"), str(tmp_path), start, ["notes.txt"], True) is None
    assert TL._nothing_committed(e, TaskId("root"), str(tmp_path), "b" * 40, ["notes.txt"]) is None, "a commit made"
    assert TL._nothing_committed(e, TaskId("root"), str(tmp_path), start, []) is None, "an empty change is its own"


def test_the_persons_own_page_signs_the_root_with_no_words(no_model):
    e = _engine(Mode.SOLO)
    _gone(e, _filled(TL.plan(e, ASKED)["text"]))
    token = CALLER.set(Principal("user", ("user",), "session", "a page", "local"))
    try:
        assert TL._the_persons_verdict(e, TaskId("root"), "PASS") is None
    finally:
        CALLER.reset(token)
    assert TL._the_persons_verdict(e, TaskId("root"), "PASS")["refused"], "an agent's connection still needs their words"


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
    monkeypatch.setattr(D, "validator_workdir", lambda *a, **k: str(tmp_path))
    said = TL.back_to_their_branch(e, TaskId("root"))
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
