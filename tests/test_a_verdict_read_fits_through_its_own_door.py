"""«Why did this carry no verdict?» — asked of the one verb that answers it, and the answer did not fit.

Measured on the delegated `json_parser` cell (2026-09-22): three validations came back with no
verdict, the driving agent called `get_verdict` to find out why, the response was ~85 KB — past the
agent door's own cap — and it escalated BLIND. The refused reports WERE the evidence, and nobody
ever read them; the session that went looking afterwards found the directory deleted.

So the read is bounded. What it may not do is buy that bound by dropping entries: a criterion
missing from the list reads exactly like a criterion nobody validated (⊥, §2.3), which is the very
thing this surface exists to make visible. The prose gives way, the structure does not, the
shortening says so in place, and `criterion=<name>` still returns one entry whole — a cap that
makes a field unreachable is the same blindness with a smaller number.
"""
from __future__ import annotations

import inspect
import json
import re
import threading

import pytest
from fastapi.testclient import TestClient

import gfso.tools as T
from gfso.api.server import create_app
from gfso.config import VERDICT_FIELD_CHARS, VERDICT_RESPONSE_MULTIPLE
from gfso.core.types import TaskId
from tests.support import criterion, make_engine, REGISTER

_RISK = REGISTER
_NAMES = ("alpha", "beta", "gamma")


@pytest.fixture(autouse=True)
def _no_plan_gate(monkeypatch):
    """The L2 plan gate is not what is under test here; it would refuse the ACCEPT before the
    node ever reaches a delivery to validate."""
    monkeypatch.setenv("GFSO_L2_GATE", "0")


def _a_node_validated_at_length(e):
    """A node whose verdict record carries far more prose than one read should return."""
    T.create_task(e, "par", {"description": "parent",
                             "criteria": [criterion("g", "G")],
                             "accepted_risks": _RISK}, assignee="a-human")
    T.decompose(e, "par", [{"task_id": "kid", "spec": {"description": "the work",
                             "criteria": [criterion(n, n.upper()) for n in _NAMES]}, "assignee": "worker", "covers": ["g"]}], accepted_risks=REGISTER)
    T.signal(e, "kid", "ACCEPT", "worker")
    T.signal(e, "kid", "DELIVER", "worker", result="did it")
    e.wait_idle()
    # 40 KB per criterion — the shape the measured cell had, where one contract's evidence ran to
    # tens of thousands of characters because every probe's captured output was kept verbatim.
    rec = T.record_verdict(
        e, "kid", "PASS", reviewer="a-reviewer",
        observed={n: {"note": f"ran the {n} probe and it printed: " + ("x" * 40_000),
                      "ran": [f"check {n}"]} for n in _NAMES})
    assert rec["recorded"], rec
    e.wait_idle()


def test_the_read_is_bounded_and_says_where_it_shortened():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    _a_node_validated_at_length(e)

    out = T.get_verdict(e, "kid")
    size = len(json.dumps(out))
    assert size < 60_000, f"the read came back {size} bytes — the cap did not hold"

    # EVERY criterion is still there. This is the half the cap is not allowed to buy.
    got = [str(x.get("criterion")) for x in out["per_criterion"]]
    assert sorted(got) == sorted(_NAMES), got
    assert out["verdict"] == "PASS"

    # …and the shortening is visible, naming which ones gave way.
    assert "shortened" in out, "a truncation the reader cannot see reads as the whole field"
    for n in _NAMES:
        assert n in out["shortened"], out["shortened"]

    for entry in out["per_criterion"]:
        assert "was shortened for the read" in entry["evidence"]
        assert len(entry["evidence"]) < VERDICT_FIELD_CHARS + 500

    e.stop()


def test_one_criterion_comes_back_whole_when_it_is_named():
    """The drill-down: the reader diagnosing a refusal is exactly who needs the untrimmed field."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    _a_node_validated_at_length(e)

    out = T.get_verdict(e, "kid", criterion="beta")
    whole = out["criterion_in_full"]
    assert whole and len(whole) == 1, out.get("criterion_in_full_note")
    assert len(whole[0]["evidence"]) > 40_000, "the named entry must not be the trimmed one"
    assert "was shortened for the read" not in whole[0]["evidence"]
    # the bounded list is still bounded beside it
    assert all("was shortened for the read" in x["evidence"] for x in out["per_criterion"])

    e.stop()


def test_a_name_that_is_not_a_criterion_is_told_so_not_silently_empty():
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    _a_node_validated_at_length(e)

    out = T.get_verdict(e, "kid", criterion="no-such-criterion")
    assert out["criterion_in_full"] is None
    # …and it names what IS there, so the caller is not left guessing at the spelling.
    for n in _NAMES:
        assert n in out["criterion_in_full_note"], out["criterion_in_full_note"]

    e.stop()


def test_a_short_record_is_returned_untouched():
    """The control: nothing is marked shortened when nothing was, or `shortened` means nothing."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "par", {"description": "parent",
                             "criteria": [criterion("g", "G")],
                             "accepted_risks": _RISK}, assignee="a-human")
    T.decompose(e, "par", [{"task_id": "kid", "spec": {"description": "the work", "criteria": [criterion("alpha", "A")]}, "assignee": "worker", "covers": ["g"]}], accepted_risks=REGISTER)
    T.signal(e, "kid", "ACCEPT", "worker")
    T.signal(e, "kid", "DELIVER", "worker", result="did it")
    e.wait_idle()
    rec = T.record_verdict(e, "kid", "PASS", reviewer="a-reviewer",
                           observed={"alpha": {"note": "ran it, it printed ok",
                                               "ran": ["check alpha"]}})
    assert rec["recorded"], rec
    e.wait_idle()

    out = T.get_verdict(e, "kid")
    assert "shortened" not in out
    assert "was shortened for the read" not in out["per_criterion"][0]["evidence"]

    e.stop()


def test_the_bound_covers_the_no_verdict_case_it_was_written_for():
    """The path the first version of this bound MISSED — and the only one the incident ran through.

    The measured cell asked `get_verdict` why three validations carried NO verdict. No verdict means
    no record: `per_criterion` is empty, so trimming it trims nothing, and the whole 85 KB arrives
    through the REFUSED report's own observations and the delivery text. A bound that covers only
    the recorded-verdict path leaves the blind escalation exactly where it was — which is what an
    outside review measured against the first version of this change (161 KB, no marker).
    """
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "par", {"description": "parent", "criteria": [criterion("g", "G")],
                             "accepted_risks": _RISK}, assignee="a-human")
    T.decompose(e, "par", [{"task_id": "kid", "spec": {"description": "the work",
                             "criteria": [criterion(n, n.upper()) for n in _NAMES]}, "assignee": "worker", "covers": ["g"]}], accepted_risks=REGISTER)
    T.signal(e, "kid", "ACCEPT", "worker")
    T.signal(e, "kid", "DELIVER", "worker", result="the delivery: " + ("d" * 40_000))
    e.wait_idle()
    # a validator whose report was REFUSED as a verdict — evidence, never a verdict (§2.3)
    e.record_rejected_report(
        TaskId("kid"), defects="criterion 'gamma' has no verdict — ⊥ is not pass",
        per_criterion=[{"criterion": n, "verdict": "pass",
                        "evidence": f"ran the {n} probe: " + ("y" * 40_000)} for n in _NAMES])
    e.wait_idle()

    out = T.get_verdict(e, "kid")
    assert out["verdict"] is None, "this is the no-verdict case or it tests nothing"
    size = len(json.dumps(out, default=str))
    assert size < 60_000, f"the no-verdict read came back {size} bytes — the bound missed this path"
    assert "shortened" in out, "the trim must be visible on this path too"

    obs = out["refused_report"]["observed_anyway"]
    assert [str(x.get("criterion")) for x in obs] == list(_NAMES), obs
    for entry in obs:
        assert "was shortened for the read" in entry["evidence"]
    assert "was shortened for the read" in out["delivered"]

    # …and the drill-down reaches the refused report, which is where the evidence IS here.
    full = T.get_verdict(e, "kid", criterion="beta")["criterion_in_full_refused_report"]
    assert full and len(full[0]["evidence"]) > 40_000
    e.stop()


def test_the_human_page_is_not_bounded():
    """The HTTP door serves a BROWSER, which has no cap — and that panel had a 300-character cut
    removed BY NAME, because evidence is the point of it.

    Driven through the real endpoint, not through the function with a flag: the claim is about the
    DOOR, and the first version of this test asserted only on `per_criterion` — so `overruled` and
    `closed_on` were being truncated right beside it, silently, and the test passed anyway. A test
    that inspects one field of a response cannot say the response is unbounded.
    """
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    _a_node_validated_at_length(e)
    _long = {"criterion": "alpha", "verdict": "fail",
             "evidence": "the displaced verdict said: " + ("w" * 40_000)}
    e.overruled_verdict = lambda tid: {"verdict": "FAIL", "validator": "other",
                                       "failed_criteria": ["alpha"], "per_criterion": [_long]}
    e.closing_verdict = lambda tid: {"verdict": "PASS", "validator": "other",
                                     "per_criterion": [_long]}

    r = TestClient(create_app(e)).get("/api/tasks/kid/verdict")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "shortened" not in body, body.get("shortened")
    for entry in body["per_criterion"]:
        assert len(entry["evidence"]) > 40_000
    # …and the DISPLACED verdicts too. These are exactly what a person is on that panel to weigh.
    for where in ("overruled", "closed_on"):
        assert len(body[where]["per_criterion"][0]["evidence"]) > 40_000, where

    # the drill-down query parameter reaches the door as well
    r2 = TestClient(create_app(e)).get("/api/tasks/kid/verdict", params={"criterion": "beta"})
    assert r2.status_code == 200
    assert len(r2.json()["criterion_in_full"][0]["evidence"]) > 40_000
    e.stop()


def test_the_bound_is_not_on_the_agents_menu():
    """A read whose job is to fit the client's cap must not advertise the argument for exceeding it.

    It was spelled `trim` for one round, which put it on the tool surface the MCP door builds from
    the signature — so the model this bound protects could read "trim=False returns everything
    whole" in the tool's own description and re-create the incident. Underscore-prefixed parameters
    are transport-internal and filtered from every generated surface.
    """
    names = [p for p in list(inspect.signature(T.get_verdict).parameters)[1:]]
    assert "trim" not in names, names
    assert "_trim" in names, names
    public = [n for n in names if not n.startswith("_")]
    assert public == ["task_id", "criterion"], public


def test_the_delivery_can_be_read_whole_by_the_route_its_own_marker_names():
    """A route a message names has to exist.

    `delivered` is shortened like everything else and its marker says to ask for it by name — which
    returned nothing at all, and a note reading "the names on this node are none". An agent asking
    what a delegated node actually DID followed the product's own instruction into a dead end.
    """
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "par", {"description": "parent", "criteria": [criterion("g", "G")],
                             "accepted_risks": _RISK}, assignee="a-human")
    T.decompose(e, "par", [{"task_id": "kid", "spec": {"description": "the work", "criteria": [criterion("alpha", "A")]}, "assignee": "worker", "covers": ["g"]}], accepted_risks=REGISTER)
    T.signal(e, "kid", "ACCEPT", "worker")
    T.signal(e, "kid", "DELIVER", "worker", result="what it did: " + ("q" * 40_000))
    e.wait_idle()

    out = T.get_verdict(e, "kid")
    assert "was shortened for the read" in out["delivered"]
    whole = T.get_verdict(e, "kid", criterion="delivered")["criterion_in_full"]
    # the SAME shape as any other drill-down — a list, not a bare string, so a consumer doing
    # `[0]["..."]` does not get silent nonsense on this one path
    assert isinstance(whole, list) and len(whole) == 1, whole
    assert len(whole[0]["delivered"]) > 40_000, "the route the marker names must return it whole"
    e.stop()


def test_one_oversized_field_cannot_sail_past_the_budget():
    """The backstop, and why it is not another field list.

    Folding touches per-criterion LISTS and nothing else, so a single oversized string anywhere
    else passes straight through it — measured twice on this repair, each time a field the previous
    round had not enumerated (`why_it_is_not_a_verdict`, 200 KB, on the incident path). Enumerating
    harder is the fix that already failed twice; the bound has to hold without knowing the names.
    """
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "par", {"description": "parent", "criteria": [criterion("g", "G")],
                             "accepted_risks": _RISK}, assignee="a-human")
    T.decompose(e, "par", [{"task_id": "kid", "spec": {"description": "the work", "criteria": [criterion("alpha", "A")]}, "assignee": "worker", "covers": ["g"]}], accepted_risks=REGISTER)
    T.signal(e, "kid", "ACCEPT", "worker")
    T.signal(e, "kid", "DELIVER", "worker", result="did it")
    e.wait_idle()
    e.record_rejected_report(TaskId("kid"), defects="why it is not a verdict: " + ("D" * 200_000),
                             per_criterion=[{"criterion": "alpha", "verdict": "pass",
                                             "evidence": "short"}])
    e.wait_idle()

    out = T.get_verdict(e, "kid")
    size = len(json.dumps(out, default=str))
    assert size < 80_000, f"a 200 KB field sailed through: {size} bytes"
    # …and what gave way is said, not silently dropped
    assert "shortened" in out or "over_budget" in out, out.keys()
    e.stop()


def _validated(e, names=("alpha",), record=None):
    """A node in VALIDATING whose recorded verdict is whatever the caller wants to put there."""
    T.create_task(e, "par", {"description": "parent", "criteria": [criterion("g", "G")],
                             "accepted_risks": _RISK}, assignee="a-human")
    T.decompose(e, "par", [{"task_id": "kid", "spec": {"description": "the work",
                             "criteria": [criterion(n, n.upper()) for n in names]}, "assignee": "worker", "covers": ["g"]}], accepted_risks=REGISTER)
    T.signal(e, "kid", "ACCEPT", "worker")
    T.signal(e, "kid", "DELIVER", "worker", result="did it")
    e.wait_idle()
    if record is not None:
        e.get_exec_verdict = lambda tid: record
    return e


def test_the_bound_terminates_and_holds_on_bulk_nobody_named():
    """The guarantee, stated as the thing three rounds of repair failed to be.

    Rounds one to three bounded the fields they had thought of and each leaked through one they had
    not. The round after that swapped the enumeration for an EXEMPTION list plus a scan of
    TOP-LEVEL STRINGS — which missed every list, every string nested one level down, and everything
    named on the exemption list; and its loop could not terminate, because shortening to a floor and
    appending a marker produced a value above the floor that was eligible again forever.

    So this test does not name a field either. It puts bulk in four shapes the code has no
    knowledge of and asks only two things: does the call RETURN, and is the answer bounded.
    """
    cases = {
        "a string on the old exemption list": {
            "verdict": "PASS", "validator": "V" * 200_000, "per_criterion": []},
        "a long list of short strings": {
            "verdict": "FAIL", "failed_criteria": [f"c-{i:04d}-" + "z" * 200 for i in range(500)],
            "per_criterion": []},
        "a string nested inside a per-criterion entry": {
            "verdict": "PASS", "per_criterion": [
                {"criterion": "alpha", "verdict": "pass", "notes_nobody_trims": "N" * 200_000}]},
        "a probe field that is not evidence or output": {
            "verdict": "PASS", "per_criterion": [
                {"criterion": "alpha", "verdict": "pass",
                 "probe": [{"behaviour": "b", "command": "C" * 200_000, "expect": "e"}]}]},
    }
    for label, rec in cases.items():
        e = make_engine(validate_signals=True, state_timeout=0)
        e.start()
        try:
            _validated(e, record=rec)
            done = []
            th = threading.Thread(target=lambda: done.append(T.get_verdict(e, "kid")), daemon=True)
            th.start()
            th.join(timeout=20)
            assert done, f"{label}: get_verdict did not return — the bound's own loop hung"
            size = len(json.dumps(done[0], default=str))
            assert size < 60_000, f"{label}: {size} bytes came back"
            # …and the reader is TOLD. A response that goes out shortened in silence is the defect
            # this whole surface exists against, arrived at from the other side.
            assert any(k in done[0] for k in ("shortened", "folded_to_fit", "over_budget",
                                              "still_over_budget")), f"{label}: no marker"
        finally:
            e.stop()


def test_a_typo_is_not_answered_with_a_quarter_megabyte():
    """`criterion=` on a name that is not there lists what IS there — and that list is bounded.

    The miss-note enumerates every criterion of the node, and it sits under the `criterion_in_full`
    prefix, which the budget deliberately does NOT weigh (the drill-down is asked for by name). So a
    mistyped name on a rich contract answered with the whole name list and nothing downstream could
    catch it.
    """
    names = tuple(f"criterion-{i:03d}-" + "n" * 400 for i in range(300))
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    try:
        _validated(e, names=("alpha",),
                record={"verdict": "PASS",
                        "per_criterion": [{"criterion": n, "verdict": "pass"} for n in names]})
        out = T.get_verdict(e, "kid", criterion="a-name-with-a-typo")
        assert out["criterion_in_full"] is None
        note = out["criterion_in_full_note"]
        assert len(note) < 25_000, f"the miss answered with {len(note)} characters"
        assert "more" in note, "it must say how many names it did not print"
    finally:
        e.stop()


def test_the_marker_does_not_claim_what_the_fold_has_undone():
    """`shortened` said "every criterion is present and every verdict is whole" — beside a folded
    list where none of that survived. An assertion the response itself contradicts is the same
    defect as an invisible truncation, told the other way round."""
    names = tuple(f"c{i:02d}" for i in range(50))
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    try:
        _validated(e, names=("alpha",),
                record={"verdict": "FAIL", "failed_criteria": ["c00"],
                        "per_criterion": [{"criterion": n, "verdict": "pass",
                                           "evidence": "E" * 40_000} for n in names]})
        out = T.get_verdict(e, "kid")
        assert "folded_to_fit" in out
        assert all(x.get("folded") for x in out["per_criterion"])
        if "shortened" in out:
            assert "every verdict" not in out["shortened"], out["shortened"]
            assert "is whole" not in out["shortened"], out["shortened"]
    finally:
        e.stop()


def test_a_criterion_really_called_delivered_is_still_reachable():
    """The delivery route may not shadow a real criterion of that name.

    An earlier version returned the delivery before looking, so a node whose criterion IS called
    `delivered` had that entry unreachable by name — and nothing said so.
    """
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    try:
        _validated(e, names=("delivered",),
                record={"verdict": "PASS",
                        "per_criterion": [{"criterion": "delivered", "verdict": "pass",
                                           "evidence": "the CRITERION's own evidence"}]})
        whole = T.get_verdict(e, "kid", criterion="delivered")["criterion_in_full"]
        assert whole and whole[0].get("evidence") == "the CRITERION's own evidence", whole
    finally:
        e.stop()


_BUDGET = VERDICT_FIELD_CHARS * VERDICT_RESPONSE_MULTIPLE


@pytest.mark.parametrize("label,record", [
    ("400 ordinary criteria", {"verdict": "PASS", "per_criterion": [
        {"criterion": f"c{i:03d}", "verdict": "pass", "evidence": "E" * 4_000} for i in range(400)]}),
    ("200 criteria with 2000-char names", {"verdict": "PASS", "per_criterion": [
        {"criterion": f"c{i:03d}-" + "n" * 2_000, "verdict": "pass", "evidence": "E" * 4_000}
        for i in range(200)]}),
    ("2000 criteria", {"verdict": "PASS", "per_criterion": [
        {"criterion": f"c{i:04d}", "verdict": "pass", "evidence": "E" * 200} for i in range(2_000)]}),
    ("60 failed criteria", {"verdict": "FAIL",
                            "failed_criteria": [f"failed-{i:03d}" for i in range(60)],
                            "per_criterion": [{"criterion": f"failed-{i:03d}", "verdict": "fail"}
                                              for i in range(60)]}),
])
def test_the_read_is_under_budget_or_says_it_is_not(label, record):
    """THE INVARIANT, asserted against the number the code itself enforces.

    Every earlier test here picked a hand-chosen threshold — `< 60_000` against a 24 000-byte
    budget — so a response at 1.1× budget with no over-budget marker passed all of them, and three
    separate leaks survived a green suite. This asserts what the code's own comments claim and
    nothing more: the read is inside its budget, or it SAYS it is not. No shape is named.
    """
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    try:
        _validated(e, record=record)
        out = T.get_verdict(e, "kid")
        size = len(json.dumps(out, default=str))
        assert size <= _BUDGET or "still_over_budget" in out, (
            f"{label}: {size} bytes against a {_BUDGET}-byte budget, and the response does not say "
            f"so — markers present: {[k for k in out if k in ('shortened', 'folded_to_fit', 'over_budget', 'still_over_budget')]}")
        # …AND THE NUMBER IT REPORTS IS THE ONE THE CALLER RECEIVES. It reported the budget-side
        # measurement, which excludes the drill-down — so the marker admitting the read is too big
        # could itself understate how big.
        if "still_over_budget" in out:
            claimed = int(re.search(r"at least (\d+) bytes", out["still_over_budget"]).group(1))
            assert claimed <= size, (
                f"{label}: the marker claims at least {claimed} bytes while the response is "
                f"{size} — a marker may understate itself, never the response")
    finally:
        e.stop()


def test_a_folded_criterion_list_keeps_every_name_it_promises():
    """`folded_to_fit` routes the reader through the criterion NAMES, so the names must be there.

    The shrink pass behind the fold treated that list like any other long list and halved it: a
    200-criterion node came back with 8 names while the marker said to ask for the rest by name.
    That is the ⊥ case `_trim_per_criterion` refuses in as many words — a criterion missing from
    the list reads exactly like one nobody validated (§2.3) — reintroduced one pass later.
    """
    names = [f"c{i:03d}-" + "n" * 2_000 for i in range(200)]
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    try:
        _validated(e, record={"verdict": "PASS", "per_criterion": [
            {"criterion": n, "verdict": "pass", "evidence": "E" * 4_000} for n in names]})
        out = T.get_verdict(e, "kid")
        if "folded_to_fit" in out:
            got = [str(x.get("criterion")) for x in out["per_criterion"]]
            assert got == names, (
                f"the fold promises these names and the response carries {len(got)} of "
                f"{len(names)}")
    finally:
        e.stop()
