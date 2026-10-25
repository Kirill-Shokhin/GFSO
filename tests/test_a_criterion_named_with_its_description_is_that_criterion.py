"""A validator that labels a criterion "Name: what it requires" speaks to that criterion.

Measured on GB_sql_database_tn03ao788 (AUTO, haiku 4.5, 2026-10-16): thirty root reports labelled each criterion by its
name with its description appended were refused whole as naming "a criterion not of this node", four more as
contradicting their own failed list (the list used the bare name), and two root deliveries lapsed with no verdict —
~$120 of validation deciding nothing. Only a label that IS a contract name followed by a separator is read as that name;
anything else stays as written and is refused as before.
"""
from __future__ import annotations

import json
from types import SimpleNamespace as NS

from gfso.core.protocol.invariants import criterion_meant
from gfso.packets import _evidence_short
from gfso.tools_llm import _SCOPE_VALIDATOR_SCHEMA, _VALIDATOR_SCHEMA, _entries_by_node
from tests.support import FakeSpec

NAMES = ["Lexer and parser functionality", "INNER JOIN operations", "INNER JOIN operations chained"]


def _parts(*names_by_node, kept=()):
    """(node, _, criteria left to validate) — `kept` names are in the contract but kept from a refused attempt."""
    return [(NS(id=tid, spec=FakeSpec(criteria=[NS(name=n) for n in (*names, *kept)])), None, [NS(name=n) for n in names])
            for tid, names in names_by_node]


def _report(entries, verdict="FAIL", failed=None):
    return json.dumps({"verdict": verdict, "per_criterion": entries,
                       "failed_criteria": failed if failed is not None else
                       [e["criterion"] for e in entries if e["verdict"] != "pass"]})


def _e(label, verdict="fail", **kw):
    return {"criterion": label, "verdict": verdict, "evidence": "ran it", **kw}


def test_the_decorated_label_is_read_as_its_criterion_on_one_nodes_report():
    out, said = _entries_by_node([_report([_e("Lexer and parser functionality: All SQL statement types parsed", "pass"),
                                           _e("INNER JOIN operations — ON conditions", failed=None)],
                                          failed=["INNER JOIN operations"])],
                                 _parts(("root", NAMES)), _VALIDATOR_SCHEMA, own=True)
    assert [e["criterion"] for e in out["root"]] == ["Lexer and parser functionality", "INNER JOIN operations"]
    assert said["root"]["failed_criteria"] == ["INNER JOIN operations"]


def test_a_scope_report_places_the_decorated_label_and_does_not_contradict_itself():
    report = _report([_e("INNER JOIN operations: joins two tables", task_id="a"), _e("Lexer and parser functionality",
                                                                                   "pass", task_id="b")],
                     failed=["INNER JOIN operations"])
    out, said = _entries_by_node([report], _parts(("a", NAMES[1:2]), ("b", NAMES[:1])), _SCOPE_VALIDATOR_SCHEMA,
                                 own=False)
    assert [e["criterion"] for e in out["a"]] == ["INNER JOIN operations"]
    assert said["a"]["contradiction"] is None, said["a"]


def test_only_an_exact_name_before_a_separator_is_identified():
    assert criterion_meant("INNER JOIN operations chained: x", NAMES) == "INNER JOIN operations chained"  # the longest
    assert criterion_meant("INNER JOIN operations (ON)", NAMES) == "INNER JOIN operations"
    # a name the contract lacks that merely starts with one it has stays foreign (critic: `Build-cache` read as `Build`)
    # …and markup or case, where exactly one criterion is meant (the packet lists criteria as `**Name**: description`)
    for decorated in ("**INNER JOIN operations**", "`INNER JOIN operations`: joins", "inner join operations: x",
                      "1. INNER JOIN operations."):
        assert criterion_meant(decorated, NAMES) == "INNER JOIN operations", decorated
    for foreign in ("INNER JOIN operationsX", "Lexer: parsed", "the tests",
                    "INNER JOIN operations-v2", "INNER JOIN operations(debug)"):
        assert criterion_meant(foreign, NAMES) == foreign
    assert criterion_meant(None, NAMES) is None


def test_one_batch_with_a_slip_does_not_void_the_others_or_their_fail():
    """A root's validation runs ~17 batches; one batch's word `FAILED`, or a PASS beside its own `undecidable` entry,
    refused every batch and the probed FAIL with them (finder over 190f4db). Each batch's red set is its claim."""
    names = ["a", "b", "c"]
    b1 = _report([_e("a", "fail")], verdict="FAILED")
    b2 = _report([_e("b", "undecidable")], verdict="PASS", failed=[])
    b3 = _report([_e("c", "pass")], verdict="PASS", failed=[])
    out, said = _entries_by_node([b1, b2, b3], _parts(("root", names)), _VALIDATOR_SCHEMA, own=True)
    s = said["root"]
    assert s["contradiction"] is None and s["verdict"] == "FAIL" and s["failed_criteria"] == ["a", "b"], s


def test_a_fail_claimed_over_entries_that_all_pass_still_decides_nothing():
    out, said = _entries_by_node([_report([_e("a", "pass")], verdict="FAIL", failed=["a"]),
                                  _report([_e("b", "pass")], verdict="PASS", failed=[])],
                                 _parts(("root", ["a", "b"])), _VALIDATOR_SCHEMA, own=True)
    assert "contradict" in (said["root"]["contradiction"] or "")


def test_a_scope_report_that_fails_a_criterion_by_name_and_passes_it_by_entry_decides_nothing():
    """Read past, the node owning `y` was recorded PASS on its entry while the same report failed `y` by name (critic
    over the round, 2026-10-19)."""
    report = _report([_e("x", "fail", task_id="A"), _e("y", "pass", task_id="B")], failed=["y"])
    out, said = _entries_by_node([report], _parts(("A", ["x"]), ("B", ["y"])), _SCOPE_VALIDATOR_SCHEMA, own=False)
    assert "no entry of its node fails" in (said["B"]["contradiction"] or "") and said["A"]["contradiction"] is None, said


def test_the_retry_after_a_naming_refusal_speaks_of_the_form():
    assert not _evidence_short("'X: d' is not a criterion of this node; criterion 'X' has no verdict — {probe, behaviours}")
    assert _evidence_short("criterion 'X' carries no reproducible probe")


def test_a_listed_fail_routed_to_another_node_does_not_leave_its_owner_passing():
    """`b_ok` is root.b's; an entry failing it under root.a's id went to root.a, and root.b passed on its own entry
    though the report failed b_ok by name (critic over the round — also in 190f4db)."""
    report = _report([_e("a_ok", "pass", task_id="A"), _e("b_ok", "fail", task_id="A"), _e("b_ok", "pass", task_id="B")],
                     failed=["b_ok"])
    out, said = _entries_by_node([report], _parts(("A", ["a_ok"]), ("B", ["b_ok"])), _SCOPE_VALIDATOR_SCHEMA, own=False)
    assert "no entry of its node fails" in (said["B"]["contradiction"] or ""), said


def test_an_entry_naming_a_node_outside_the_validation_is_credited_to_no_node_by_name():
    report = _report([_e("dep__a", "pass", task_id="C")], verdict="PASS", failed=[])
    out, _ = _entries_by_node([report], _parts(("B", ["dep__a"])), _SCOPE_VALIDATOR_SCHEMA, own=False)
    assert out["B"] == [], out


def test_a_fail_under_a_non_owners_id_holds_its_owner_whatever_the_list_says():
    """`b_ok` failed under root.a's id with a list naming something else: the owner passed (critic r4 — HEAD refused it)."""
    for failed in (["zz"], ["a_ok"], []):
        report = _report([_e("a_ok", "pass", task_id="A"), _e("b_ok", "fail", task_id="A"),
                          _e("b_ok", "pass", task_id="B")], failed=failed)
        out, said = _entries_by_node([report], _parts(("A", ["a_ok"]), ("B", ["b_ok"])), _SCOPE_VALIDATOR_SCHEMA,
                                     own=False)
        assert "no entry of its node fails" in (said["B"]["contradiction"] or ""), (failed, said)


def test_a_batch_with_no_red_entry_failing_anothers_criterion_by_name_holds_that_owner():
    """Critic r4 (also in 190f4db): batches all-pass, one listing `b_ok` failed — b_ok's node passed."""
    b1 = _report([_e("a_ok", "pass", task_id="A")], verdict="FAIL", failed=["b_ok"])
    b2 = _report([_e("b_ok", "pass", task_id="B")], verdict="PASS", failed=[])
    out, said = _entries_by_node([b1, b2], _parts(("A", ["a_ok"]), ("B", ["b_ok"])), _SCOPE_VALIDATOR_SCHEMA, own=False)
    assert "no entry of its node fails" in (said["B"]["contradiction"] or ""), said


def test_a_criterion_kept_from_a_refused_attempt_still_has_its_owner():
    """Critic r5: `b_ok` passed in a refused attempt and kept; the next report lists it failed, or fails it with no
    task_id — with `owners` built from the criteria left to validate, nothing held it and the kept pass was recorded."""
    listed = _report([_e("dep__a", "pass", task_id="B"), _e("g", "fail", task_id="R")], failed=["g", "b_ok"])
    out, said = _entries_by_node([listed], _parts(("R", ["g"])) + _parts(("B", ["dep__a"]), kept=["b_ok"]),
                                 _SCOPE_VALIDATOR_SCHEMA, own=False)
    assert "no entry of its node fails" in (said["B"]["contradiction"] or ""), said
    unrouted = _report([_e("dep__a", "pass", task_id="B"), _e("b_ok", "fail")], failed=[])
    out, said = _entries_by_node([unrouted], _parts(("B", ["dep__a"]), kept=["b_ok"]), _SCOPE_VALIDATOR_SCHEMA, own=False)
    assert [e["criterion"] for e in out["B"]] == ["dep__a", "b_ok"], out
