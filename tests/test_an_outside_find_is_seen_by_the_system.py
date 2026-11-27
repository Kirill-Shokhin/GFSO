"""What a validator saw outside the criteria is a suspicion until it is observed: an entry carries `probe: {command,
expect}`, the system runs it itself on a fresh copy of the delivery as it runs a pinned check, and the issuer is told
«observed: …», «not reproduced: …» or «read, not observed» — never a verdict's input (Inv-2; §8.3 FM-1.f). Measured: told
to probe such a find, a live validator wrote «Read from the diff only. I built no scenario and ran nothing for it.»

CONTROL (each run, each red): drop `probe` from `_place_outside`'s entry → the kept-probe test and every observed test;
drop the `_observe_outside` call in `_validation_pass` → every observed test reads «read, not observed»; run the check in
`place` instead of its own copy in `observe._fresh_run` → `planted` lands in the place; give the outside `Probe`
`bound_s=60` → the bound test reads «observed»; append an `outside` entry to the root's `per_criterion` as a fail → the
verdict test is FAIL; revert `outside_text`'s line → the issuer-packet test; catch only `BuildFailed`/`NotTheDelivery` in
`_observe_outside` → the place-down test loses its verdict; run `_observe_outside` before `_record_node` → the
record-first test; drop `({o['observed']})` from `questions_left_standing` → the end test; `.run()` the outside thread in place of
`.start()` → the caller-first test reads «observed» where the run is still held.
"""
from __future__ import annotations

import threading

import gfso.observe as O
import gfso.packets as P
import gfso.tools_llm as TL
import gfso.validate as VAL
from gfso.core.types import State, TaskId
from gfso.engine.closures import questions_left_standing
from gfso.engine.verdicts import BEING_OBSERVED, READ_NOT_OBSERVED
from tests.test_a_small_task_takes_the_canons_acts import (ACCEPTED, ASKED, WORDS, _Validator, _filled, _set_up, _worked, chat,
                                                            pytestmark)

__all__ = ["chat", "pytestmark"]


def _delivered(e, repo, call, monkeypatch, outside: list) -> None:
    """The root delivered and its validation answered, its validator reporting `outside`."""
    monkeypatch.setattr(VAL, "llm_factory", lambda *a, **k: _Validator(e, outside))
    _set_up(call, repo)
    call("auto_decompose", plan=call("plan", plan=_filled(call("plan", ASKED)["text"]))["path"], user_said=WORDS)
    _worked(repo)
    call("signal", "root", "DELIVER", "user", result="f.txt written", self_validation="PASS")
    call("wait", seconds=60)


def _settled() -> None:
    """Every outside run a validation started after its record, ended."""
    for t in [t for t in threading.enumerate() if t.name.startswith(VAL.OUTSIDE_RUN)]:
        t.join(60)


def _seen(e, repo, call, monkeypatch, outside: list) -> list:
    """What `get_verdict` serves of the root's delivery's outside observations once the system's run of them ended."""
    _delivered(e, repo, call, monkeypatch, outside)
    _settled()
    return TL.TOOLS["get_verdict"](e, "root")["outside"]


def test_the_report_keeps_an_entrys_probe():
    said = {"root": {"outside": []}}
    VAL._place_outside({"outside": [{"what": "a", "probe": {"command": "cat f", "expect": "x"}},
                                    {"what": "b", "probe": {"command": "cat f", "expect": ""}}]}, said, own=True)
    assert said["root"]["outside"][0]["probe"] == {"command": "cat f", "expect": "x"}
    assert "probe" not in said["root"]["outside"][1], "a probe expecting nothing is no observation"
    for schema in (VAL._VALIDATOR_SCHEMA, VAL._SCOPE_VALIDATOR_SCHEMA):
        assert "probe" in schema["properties"]["outside"]["items"]["properties"]


def test_the_system_runs_each_probe_on_the_delivered_tree_and_says_what_it_saw(chat, monkeypatch):
    e, repo, call, _ = chat
    rows = _seen(e, repo, call, monkeypatch, [
        {"what": "f.txt says v1", "evidence": "read", "probe": {"command": "echo x > planted; cat f.txt", "expect": "v1"}},
        {"what": "f.txt says v2", "evidence": "read", "probe": {"command": "cat f.txt", "expect": "v2"}},
        {"what": "a hunch", "evidence": "read off the diff"}])
    by = {r["what"]: r["observed"] for r in rows}
    assert by["f.txt says v1"] == "observed: `echo x > planted; cat f.txt` printed «v1»", by
    assert by["f.txt says v2"] == "not reproduced: `cat f.txt` printed «v1», which does not show «v2»", by
    assert by["a hunch"] == READ_NOT_OBSERVED, by
    assert not (repo / "planted").exists(), "the probe ran in the place itself"


def test_a_probe_runs_within_a_checks_bound(chat, monkeypatch):
    e, repo, call, _ = chat
    monkeypatch.setattr(O, "PROBE_S", 2)
    (row,) = _seen(e, repo, call, monkeypatch, [{"what": "slow", "probe": {"command": "sleep 6; echo late", "expect": "late"}}])
    assert row["observed"].startswith(f"{READ_NOT_OBSERVED}: `sleep 6; echo late` did not finish"), row


def test_no_observation_is_a_verdict(chat, monkeypatch):
    e, repo, call, _ = chat
    _seen(e, repo, call, monkeypatch, [{"what": "f.txt says v2", "probe": {"command": "cat f.txt", "expect": "v2"}},
                                       {"what": "f.txt says v1", "probe": {"command": "cat f.txt", "expect": "v1"}}])
    rec = e.current_exec_verdict(TaskId("root"))
    assert rec["verdict"] == "PASS" and not rec["failed_criteria"], rec
    assert e.graph.get_state(TaskId("root")) == State.VALIDATING
    assert "observed: `cat f.txt` printed «v1»" in e.persons_verdict("root"), "the person signing is not told what was seen"


def test_the_issuer_is_told_what_the_system_saw(tmp_path):
    rows = [{"node": "root.a", "what": "f.txt says v2", "evidence": "ran it",
             "observed": "not reproduced: `cat f.txt` printed «v1», which does not show «v2»"}]
    text = P.outside_text(None, "root", rows, str(tmp_path))
    assert "`root.a`: f.txt says v2 — not reproduced: `cat f.txt` printed «v1»" in text, text


def _for_outside(monkeypatch, then):
    """`_on_the_delivery` with its run of outside probes (keys `(node, n)`) replaced by `then(probes)`; pins run as ever."""
    real = VAL._on_the_delivery
    monkeypatch.setattr(VAL, "_on_the_delivery", lambda engine, parts, workdir, probes, *a, **k: (
        then(engine, probes) if isinstance(probes[0][0][1], int) else real(engine, parts, workdir, probes, *a, **k)))


def test_a_failed_outside_run_costs_no_verdict(chat, monkeypatch):
    e, repo, call, _ = chat

    def down(engine, probes):
        raise OSError("the place went down")
    _for_outside(monkeypatch, down)
    (row,) = _seen(e, repo, call, monkeypatch, [{"what": "f.txt says v1", "probe": {"command": "cat f.txt", "expect": "v1"}}])
    assert e.current_exec_verdict(TaskId("root"))["verdict"] == "PASS", "the paid verdict was lost"
    assert row["observed"] == f"{READ_NOT_OBSERVED}: `cat f.txt` not run: the place went down", row


def test_the_verdict_is_recorded_before_the_outside_run(chat, monkeypatch):
    e, repo, call, _ = chat
    at = []

    def first(engine, probes):
        at.append(engine.current_exec_verdict(TaskId("root")))
        return {k: {"rc": 0, "out": "v1", "printed": "v1", "matched": True} for k, _, _ in probes}
    _for_outside(monkeypatch, first)
    (row,) = _seen(e, repo, call, monkeypatch, [{"what": "f.txt says v1", "probe": {"command": "cat f.txt", "expect": "v1"}}])
    assert at and at[0] and at[0]["verdict"] == "PASS", f"the outside run started before the record: {at}"
    assert row["observed"] == "observed: `cat f.txt` printed «v1»", row


def test_the_end_says_what_was_seen_of_a_question_left_standing(chat, monkeypatch):
    e, repo, call, _ = chat
    _seen(e, repo, call, monkeypatch, [{"what": "f.txt says v2", "probe": {"command": "cat f.txt", "expect": "v2"}}])
    assert call("signal", "root", "PASS", "user", user_said=ACCEPTED)["accepted"]
    left = questions_left_standing(e)
    assert left == ["root: root saw f.txt says v2 (not reproduced: `cat f.txt` printed «v1», which does not show «v2»)"], left

def test_the_caller_is_answered_while_the_outside_run_still_runs(chat, monkeypatch):
    e, repo, call, _ = chat
    go = threading.Event()

    def held(engine, probes):
        go.wait(30)
        return {k: {"rc": 0, "out": "v1", "printed": "v1", "matched": True} for k, _, _ in probes}
    _for_outside(monkeypatch, held)
    _delivered(e, repo, call, monkeypatch, [{"what": "f.txt says v1", "probe": {"command": "cat f.txt", "expect": "v1"}}])
    assert e.current_exec_verdict(TaskId("root"))["verdict"] == "PASS"
    (row,) = TL.TOOLS["get_verdict"](e, "root")["outside"]
    # …and says it is being observed, not «read, not observed»: told the latter, a person signed over a find about to be
    # observed (critic over 6b8475ea)
    assert row["observed"] == BEING_OBSERVED, f"the validation waited for the outside run, or says nothing pends: {row}"
    go.set()
    _settled()
    (row,) = TL.TOOLS["get_verdict"](e, "root")["outside"]
    assert row["observed"] == "observed: `cat f.txt` printed «v1»", row