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
from gfso.core.types import Mode, TaskId
from gfso.mcp import protocol, server as S
from tests.test_a_solo_chat_writes_its_own_plan_and_the_person_gives_the_go import ASKED, _filled, _gone, no_model  # noqa: F401
from tests.support import hold_a_credential
from tests.test_the_mode_decides_who_holds_what import _engine, _goal


def test_a_delivery_with_nothing_committed_since_the_start_is_refused(no_model):
    e = _engine(Mode.SOLO)
    _gone(e, _filled(TL.plan(e, ASKED)["text"]))
    e.graph.store_setting("chat_start:root", json.dumps({"branch": "main", "head": "a" * 40}))
    no = TL._nothing_committed(e, TaskId("root"), "a" * 40, ["exts.py"])
    assert no and "Commit it, then DELIVER again" in no and "no validator" in no, no
    assert TL._nothing_committed(e, TaskId("root"), "b" * 40, ["notes.txt"]) is None, "a commit made: stray files stay said"
    assert TL._nothing_committed(e, TaskId("root"), "a" * 40, []) is None, "nothing left out: an empty change is its own"


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
