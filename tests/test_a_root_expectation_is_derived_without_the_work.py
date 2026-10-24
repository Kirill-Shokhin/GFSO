"""Under AUTO an expectation the system re-pins on the user's goal is shown by a derivation that does not run the work.

The executor disputed `50000.0 * 1.1 > 55000` as false; the system, having run only the engine under test, accepted and
re-pinned the root's check to the engine's output, and the root passed on it (GB_sql_database_tn74a0108, 2026-10-20).
The work under test answering its own check is verifier = executor in substance (§10.3); content comes from contact
(d6, §4.1), and the delivery is not the world it is checked against.
"""
from __future__ import annotations

import gfso.tools as T
from gfso import issuer as I
from gfso.core.types import Mode, State, TaskId
from tests.support import criterion
from tests.test_the_mode_decides_who_holds_what import _FakeLLM, _admit, _engine, _kid

OLD = {"behaviour": "b", "command": "./engine < q.sql", "expect": "Alice 55000.000\nBob 60000.000"}
NEW = {"behaviour": "b", "command": "./engine < q.sql", "expect": "Bob 60000.000"}


def _disputed(mode=Mode.AUTO):
    e = _engine(mode)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [
        {"name": "g", "description": "rows over 55000 after the raise", "check": [OLD]}, criterion("h", "H holds")]})
    _admit(e, "root", _kid("kid", ["g", "h"], criterion("k", "K holds"), description="a part"))
    T.signal(e, "root", "ACCEPT", "exec-1")
    T.signal(e, "root", "CHALLENGE", "exec-1", reason="g's pinned check keeps a row where 55000 > 55000 is false")
    e.wait_idle()
    return e


class _Contact(_FakeLLM):
    """An issuer answering from the workspace, as the dispatcher asks it to (its tool ledger: it ran the engine)."""
    last_tool_calls = {"Bash": 1}


def _accept(e, *derivations, task="root", probe=NEW, where=None):
    llm = (_Contact if where else _FakeLLM)({"decision": "accept", "justification": "the check contradicts the specification",
                    "criteria": [{"name": "g", "description": "rows over 55000 after the raise", "check": [probe]}],
                    "derivations": list(derivations)})
    out = I.answer_the_challenge(e, TaskId(task), "agent", _llm=llm, where=where)
    e.wait_idle()
    return out, e.graph.get_task(TaskId(task))


def _derive(cmd, probe=NEW):
    return {"criterion": "g", "probe": probe["command"], "derived_by": cmd}


def test_a_root_re_pin_with_no_derivation_is_refused_and_the_dispute_stands():
    out, t = _accept(_disputed())
    assert out["status"] == "would_narrow" and "derived_by" in out["why"], out
    assert t.state == State.CHALLENGED and [p.expect for p in t.spec.criteria[0].check] == [OLD["expect"]]


#: The rows over 55000 after the raise, computed with no engine at all.
SQL_TRUTH = ("awk 'BEGIN{split(\"Alice Bob Carol\",n,\" \"); s[1]=50000.0*1.1; s[2]=60000; s[3]=70000; "
             "for(i=1;i<=3;i++) if (s[i] > 55000) printf \"%s %.3f\\n\", n[i], s[i]}'")


def test_a_derivation_that_contradicts_the_new_expectation_refuses_it():
    out, t = _accept(_disputed(), _derive(SQL_TRUTH))
    assert out["status"] == "would_narrow" and "Alice 55000.000" in out["why"], out
    assert [p.expect for p in t.spec.criteria[0].check] == [OLD["expect"]], "the user's check stands"


def test_a_derivation_that_prints_the_new_expectation_lets_the_re_pin_land():
    fixed = {"behaviour": "b", "command": "./engine < q.sql",
             "expect": "Alice 55000.000\nBob 60000.000\nCarol 70000.000"}
    out, t = _accept(_disputed(), _derive(SQL_TRUTH, fixed), probe=fixed)
    assert out["status"] == "accepted", out
    assert [p.expect for p in t.spec.criteria[0].check] == [fixed["expect"]]


def test_a_derivation_that_runs_the_work_under_test_is_refused(tmp_path):
    """The measured issuer ran the engine under test and took its output as the truth; an empty place hides nothing a
    path reaches, so the derivation may not name the work's place or the program the probe runs from it."""
    (tmp_path / "engine").write_text("#!/bin/sh\necho 'Bob 60000.000'\n", encoding="utf-8")
    for how in ("./engine < q.sql", f"{tmp_path.as_posix()}/engine < q.sql", "cd .. && engine"):
        out, t = _accept(_disputed(), _derive(how), where=str(tmp_path))
        assert out["status"] == "would_narrow" and "runs the work under test" in out["why"], (how, out)
        assert [p.expect for p in t.spec.criteria[0].check] == [OLD["expect"]]


def test_an_honest_constant_is_a_derivation():
    """`echo PASS` is the true value of a `… && echo PASS` probe; refusing it would leave the repair liftable only by
    disguising the constant (§12.16 (ii)). Writing a value down is the residue the rule names, not a refusal."""
    probe = {"behaviour": "b", "command": "./engine < q.sql | diff - {inputs}/q.out && echo PASS", "expect": "PASS",
             "inputs": [{"path": "q.out", "content": "Alice 55000.000\nBob 60000.000\n"}]}
    out, t = _accept(_disputed(), _derive("echo PASS", probe), _derive(SQL_TRUTH, OLD), probe=probe)
    assert out["status"] == "accepted", out


def test_a_narrower_command_does_not_replace_a_users_probe_that_was_right():
    """The critic's live replay on the measured dispute: the issuer rewrote the query so it no longer reaches the row
    the engine gets wrong, derived the new output honestly, and pinned it. The probe it replaced is derived too, and it
    prints the user's expectation — the user's probe was right."""
    user = {"behaviour": "b", "command": "./engine < q.sql", "expect": "Alice 55000.000\nBob 60000.000\nCarol 70000.000"}
    narrow = {"behaviour": "b", "command": "./engine < q2.sql", "expect": "Bob 60000.000\nCarol 70000.000"}
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [
        {"name": "g", "description": "rows over 55000 after the raise", "check": [user]}, criterion("h", "H holds")]})
    _admit(e, "root", _kid("kid", ["g", "h"], criterion("k", "K holds"), description="a part"))
    T.signal(e, "root", "ACCEPT", "exec-1")
    T.signal(e, "root", "CHALLENGE", "exec-1", reason="g's pinned check keeps a row where 55000 > 55000 is false")
    e.wait_idle()
    narrower = SQL_TRUTH.replace("s[i] > 55000", "s[i] > 55001")
    out, t = _accept(e, _derive(narrower, narrow), _derive(SQL_TRUTH, user), probe=narrow)
    assert out["status"] == "would_narrow" and "was right" in out["why"], out
    assert [p.expect for p in t.spec.criteria[0].check] == [user["expect"]]


def test_below_the_root_a_re_pin_needs_no_derivation():
    """A wrong re-pin on a part is still met by the checks above it; above the root nothing stands."""
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("top", "T holds")]})
    _admit(e, "root", _kid("kid", ["top"], {"name": "g", "description": "rows over 55000", "check": [OLD]},
                           description="a part"))
    kid = e.graph.get_task(TaskId("kid"))
    assert I.underived_at_the_root(e, kid, I.spec_with(kid, [{"name": "g", "description": "rows over 55000",
                                                               "check": [NEW]}]), {}) is None
