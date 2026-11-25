"""A missing credential stops the project once, says so once, ends the authoring at the first refused call, and lifts
the moment a person sets one — named as what lifted it. Measured on a fresh client's solo run (s20g1, 2026-11-19): the
stop held ten minutes past the credential (01:47→01:57), its lift said "the account's limit lifted", five STOPPED lines
stood for one cause, and the repairer ran two rounds more over an empty fold. And `gfso doctor` told that person their
own chat's work needs no credential, while the plan's calls are the system's and need one in every mode."""
from __future__ import annotations

import threading

from gfso import decompose as DEC, doctor, tools_llm as TL
from gfso.adapters.llm import credentials, headless as H
from tests.support import carried_by_the_system, hold_a_credential, make_engine, written
from tests.test_a_refused_account_stops_the_project import REFUSED_STREAM, _cli


def _said(e) -> list[str]:
    lines = []
    real = e.emit_info
    e.emit_info = lambda kind, msg, *a, **k: (lines.append(f"{kind}: {msg}"), real(kind, msg, *a, **k))[1]
    return lines


def _no_credential(monkeypatch, tmp_path):
    hold_a_credential(monkeypatch, tmp_path)
    credentials.put("claude", "token", None)


def test_one_missing_credential_is_one_stop_one_line_and_one_refused_call(monkeypatch, tmp_path):
    _no_credential(monkeypatch, tmp_path)
    monkeypatch.setattr(DEC, "_default_llm", lambda model, execution=None: H.ClaudeCodeProvider(model, execution=execution))
    _cli(monkeypatch, REFUSED_STREAM)
    e = carried_by_the_system(make_engine(llm=None))
    said, calls = _said(e), []
    real = e.record_llm_usage
    e.record_llm_usage = lambda stage, llm, *a, **k: (calls.extend(getattr(llm, "calls", None) or llm), real(stage, llm, *a, **k))[1]
    box = {}
    t = threading.Thread(target=lambda: box.update(out=written(TL.TOOLS["plan"], e, request="count the words of a file")))
    t.start(), t.join()
    assert "no credential of 'claude'" in str(box["out"].get("error")), box
    stages = [c.get("stage") for c in calls if isinstance(c, dict) and c.get("ended") == "unauthorized"]
    assert stages and not {"audit_fold", "repair"} & {str(s).lower() for s in stages}, stages     # …the search alone
    assert len(stages) <= 2, stages
    assert len([x for x in said if "STOPPED" in x]) == 1, said


def test_a_credential_set_lifts_the_account_stop_at_once_and_says_so(monkeypatch, tmp_path):
    _no_credential(monkeypatch, tmp_path)
    e = carried_by_the_system(make_engine(llm=None))
    e.stops.probe_the_account_with(credentials.stamp)            # …as the dispatcher hands it (`delegate.Dispatcher`)
    said = _said(e)
    e.record_llm_usage("plan", [{"ended": "unauthorized", "error": "no credential of 'claude' is in force"}], None)
    e.record_llm_usage("plan", [{"ended": "unauthorized", "error": "no credential of 'claude' is in force"}], None)
    stop = e.stops.paused()
    assert stop and stop.get("until"), stop
    e.stops.lift_the_system_stop(0)                               # …long before its time
    assert e.stops.paused(), "nothing changed: the stop stands"
    credentials.put("claude", "token", "t-new", name="new")
    e.stops.lift_the_system_stop(0)
    assert e.stops.paused() is None, "a credential set did not lift the stop it was waited on for"
    started = [x for x in said if "STARTED" in x]
    assert started and "credential" in started[-1] and "limit" not in started[-1], said
    assert len([x for x in said if "STOPPED" in x]) == 1, said


def test_the_limits_own_lift_still_names_the_limit(monkeypatch, tmp_path):
    hold_a_credential(monkeypatch, tmp_path)
    e = carried_by_the_system(make_engine(llm=None))
    said = _said(e)
    e.stops.stop_for_the_limit("executor", None)
    e.stops.lift_the_system_stop(e.stops.paused()["until"] + 1)
    assert e.stops.paused() is None and "the account's limit lifted" in said[-1], said


def test_doctor_does_not_tell_a_chat_its_work_needs_no_credential(monkeypatch, tmp_path):
    _no_credential(monkeypatch, tmp_path)
    monkeypatch.setattr(doctor, "local_word", lambda: False)
    monkeypatch.setattr(doctor, "docker_state", lambda: (True, "ok"))
    monkeypatch.setattr(doctor, "image_present", lambda tag: True)
    monkeypatch.setattr(doctor._config, "executions", lambda: {doctor.DEFAULT_EXECUTION: {"image": "img:1"}})
    rows, _ = doctor._execution_report()
    line = dict(rows)["credential"]
    assert "in every mode" in line and "uses your CLI" not in line, line
