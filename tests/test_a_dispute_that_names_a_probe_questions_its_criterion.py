"""Stranger run s17c (AUTO, Haiku 5.5): the executor disputed the root's pin «run from inside DIR, planted os.py and
argparse.py there are not imported; the count is correct», which expects `1 a` of a DIR whose own fixture plants two
.py files — a pin no correct program prints. Its dispute misnamed the criterion («runtime-cwd-safe-imports» for
«runs-from-any-cwd-and-safe-imports») and quoted the probe word for word. The machine issuer accepted with the probe
re-pinned to `2 py ⏎ 1 a`; the re-pin was dropped as touching a criterion the dispute did not question, the acceptance
refused twice as «changed no criterion», and the refusal steered it to REJECT a true dispute — two FAIL rounds on the
pin, ~15 min, before the executor disputed again by the probe's id (audit rows 3–13).

A dispute questions the criteria whose probes it names, by id or by behaviour as written (`names_a_probe`); and a
re-pin the contract does not take is named in the refusal with the move that is one (§12.16 (ii))."""
from __future__ import annotations

import pytest

from gfso import issuer as I
import gfso.tools as T
from gfso.core.protocol.procedure import probe_id
from gfso.core.types import Mode, State, TaskId
from tests.support import criterion
from tests.test_the_mode_decides_who_holds_what import _FakeLLM, _admit, _engine, _kid

CWD = "runs-from-any-cwd-and-safe-imports"
SAID = "run from inside DIR, planted os.py and argparse.py there are not imported; the count is correct"
OLD = {"behaviour": SAID, "command": "test -d . && echo 1", "expect": "1"}
NEW = {"behaviour": SAID, "command": "test -d . && echo 2", "expect": "2"}


QUOTED = f"Criterion runtime-cwd-safe-imports, check '{SAID}', expects `1 a`"


def _disputed(reason, other="other holds", cwd=(OLD,)):
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [
        {"name": CWD, "description": "runs from any directory", "check": list(cwd)},
        {"name": "other", "description": "O holds", "check": [{"behaviour": other, "command": "check other",
                                                              "expect": "it holds"}]}]})
    _admit(e, "root", _kid("kid", [CWD, "other"], criterion("k", "K holds"), description="a part"))
    T.signal(e, "root", "ACCEPT", "exec-1")
    T.signal(e, "root", "CHALLENGE", "exec-1", reason=reason)
    e.wait_idle()
    return e


def _accept(e, name, probe, *more):
    """The issuer's acceptance re-pinning `name`'s probe, each expectation derived without the work."""
    llm = _FakeLLM({"decision": "accept", "justification": "the pin contradicts its own fixture",
                    "criteria": [{"name": name, "description": "unchanged", "check": [probe, *more]}],
                    "derivations": [{"criterion": name, "probe": probe["command"], "derived_by": "expr 1 + 1"},
                                    {"criterion": name, "probe": OLD["command"] if name == CWD else f"check {name}",
                                     "derived_by": "expr 1 + 1"}]})
    out = I.answer_the_challenge(e, TaskId("root"), "user", _llm=llm)
    e.wait_idle()
    return out


@pytest.mark.parametrize("names", [QUOTED,
                                   f"the pin #{probe_id(CWD, OLD).rsplit('#', 1)[1]} expects `1 a`"])
def test_a_dispute_naming_the_probe_has_its_re_pin_accepted(names):
    """CONTROL: `names_a_probe` returning False — the re-pin is dropped, the answer refused, and this goes red."""
    e = _disputed(names)
    out = _accept(e, CWD, NEW)
    root = e.graph.get_task("root")
    assert out["status"] == "accepted", out
    assert root.state == State.OFFERED, "the corrected contract is re-consented (Inv-1)"
    assert [p.command for p in root.spec.criteria[0].check] == [NEW["command"]]


def test_a_re_pin_of_what_the_dispute_does_not_question_is_named_with_the_move():
    """CONTROL: the refusal built by `_decided_nothing` alone — it names no re-pin and this goes red."""
    e = _disputed(QUOTED)
    out = _accept(e, "other", {"behaviour": "o", "command": "test -d . && echo 2", "expect": "2"})
    assert out["status"] == "unparsed", out
    assert "re-pins other, which the dispute does not question" in out["why"] and CWD in out["why"], out
    assert e.graph.get_task("root").state == State.CHALLENGED


@pytest.mark.parametrize("other,reason", [("the count is correct", QUOTED),
                                          ("exits 0", QUOTED + "; it exits 0 as it should")])
def test_a_behaviour_said_in_part_or_in_passing_questions_nothing(other, reason):
    """CONTROL: the behaviour matched anywhere at word boundaries — `other` is questioned, its re-pin lands, red."""
    e = _disputed(reason, other=other)
    assert I.questioned(e, e.graph.get_task("root")) == {CWD}
    assert _accept(e, "other", {"behaviour": other, "command": "test -d . && echo 2", "expect": "2"})["status"]         == "unparsed"


def test_a_re_pin_with_fewer_probes_is_told_to_keep_them():
    """CONTROL: `_no_decision` without its fewer-probes clause — the refusal names no count and this goes red."""
    two = {"behaviour": "importing it prints nothing", "command": "test -d . && echo 0", "expect": "0"}
    e = _disputed(QUOTED, cwd=(OLD, two))
    out = _accept(e, CWD, NEW)
    assert out["status"] == "unparsed", out
    assert f"{CWD} with 1 probe(s) where it holds 2" in out["why"] and "Keep every probe" in out["why"], out
    assert _accept(e, CWD, NEW, two)["status"] == "accepted"


def test_an_unchanged_answer_to_a_questioned_criterion_is_steered_to_its_re_pin_not_to_reject():
    """CONTROL: `_decided_nothing` without its questioned clause — the steer is REJECT and this goes red."""
    e = _disputed(QUOTED)
    out = _accept(e, CWD, OLD)
    assert out["status"] == "unparsed", out
    assert f"The dispute questions {CWD}" in out["why"] and "REJECT" not in out["why"], out


EXTRA = {"name": "extra", "description": "E holds", "check": [{"behaviour": "e", "command": "test -d . && echo 2",
                                                             "expect": "2"}]}


def _answer(e, *criteria, derived=()):
    llm = _FakeLLM({"decision": "accept", "justification": "the pin contradicts its own fixture",
                    "criteria": list(criteria), "derivations": [
                        {"criterion": n, "probe": c, "derived_by": "expr 1 + 1"} for n, c in derived]})
    out = I.answer_the_challenge(e, TaskId("root"), "user", _llm=llm)
    e.wait_idle()
    return out


@pytest.mark.parametrize("case", ["S7", "S8"])
def test_a_re_pin_not_taken_refuses_the_acceptance_whole_beside_an_addition(case):
    """S7: an unquestioned criterion re-pinned; S8: the hash-named one with 1 of its 2 probes — each beside a new
    criterion, which made the acceptance land and the impossible pin stay. CONTROL: `_no_decision` run only on an
    unchanged spec — both are accepted and this goes red."""
    two = {"behaviour": "importing it prints nothing", "command": "test -d . && echo 0", "expect": "0"}
    by_hash = f"the pin #{probe_id(CWD, OLD).rsplit('#', 1)[1]} expects `1 a`"
    e = _disputed(QUOTED if case == "S7" else by_hash, cwd=(OLD, two))
    repin = ({"name": "other", "description": "O holds", "check": [NEW]} if case == "S7"
             else {"name": CWD, "description": "unchanged", "check": [NEW]})
    out = _answer(e, repin, EXTRA, derived=[(repin["name"], NEW["command"]), (CWD, OLD["command"]),
                                            ("other", "check other"), ("extra", EXTRA["check"][0]["command"])])
    root = e.graph.get_task("root")
    assert out["status"] == "unparsed" and "refused whole" in out["why"], out
    assert root.state == State.CHALLENGED and "extra" not in {c.name for c in root.spec.criteria}


def test_an_unchanged_answer_in_another_order_below_the_root_is_no_re_pin():
    """S10: below the root a system plan's child takes the answer's order; read by position, the same criteria in
    another order were "re-pinned" and told the node takes additions only. CONTROL: compared by position, red."""
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("kid", ["g"], criterion("k1", "K1 holds"), criterion("k2", "K2 holds")))
    T.signal(e, "kid", "ACCEPT", "exec-2")
    T.signal(e, "kid", "CHALLENGE", "exec-2", reason="k1 and k2 cannot both hold")
    e.wait_idle()
    kid = e.graph.get_task("kid")
    llm = _FakeLLM({"decision": "accept", "justification": "both stand",
                    "criteria": [criterion("k2", "K2 holds"), criterion("k1", "K1 holds")]})
    out = I.answer_the_challenge(e, kid.id, "exec-1", _llm=llm)
    assert out["status"] == "unparsed", out
    assert "changed no criterion" in out["why"] and "additions only" not in out["why"], out
