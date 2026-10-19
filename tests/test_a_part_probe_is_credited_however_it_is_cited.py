"""A part's pinned probe is one observation, credited once for every criterion of the whole resting on it, however the
report names it — its full id, a bare hash only it has, or its exact command — unless it is reported not holding or
cited without `held: true` under a criterion the report does not pass. A citation naming two demanded probes credits
neither, and the refusal says so instead of calling the probe "not run".

Measured on the automatic c_compiler root (GB_c_compiler_tmqn88552): 17 reports refused over 55 minutes, four of
which ran all 33 part probes and cited each once, by bare hash or by command, without `held` — and the refusal fed
back said they "were not run", so each retry re-read ~75 probes and dropped a different subset.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from gfso.core.protocol.procedure import part_credit, part_criteria, probe_id, unaccounted_for, unrun_parts
from gfso.core.types import Criteria, Probe

_CAT = part_criteria("root.cat", [Criteria("flags", check=(Probe("cat flags", "cat -n f", "ok"),))])
_WC = part_criteria("root.wc", [Criteria("count", check=(Probe("wc counts", "python {inputs}/t.py", "3"),))])
_PARTS = {"A": _CAT + _WC, "B": _CAT + _WC}          # two criteria of the whole rest on the same two part probes
_CAT_ID, _WC_ID = (probe_id(c.name, c.check[0]) for c in (*_CAT, *_WC))
_DIRS = ((_WC_ID, "/tmp/scratch/probe_inputs/wc"),)


def _report(*probes, b_verdict="pass"):
    return [{"criterion": "A", "verdict": "pass", "probe": list(probes)},
            {"criterion": "B", "verdict": b_verdict, "probe": []}]


def _hash(pid):
    return pid.split("#")[1]


@pytest.mark.parametrize("cat, wc", [
    ({"id": _hash(_CAT_ID)}, {"id": _hash(_WC_ID)}),                                   # bare hashes
    ({"command": "cat -n f"}, {"command": "python /tmp/scratch/probe_inputs/wc/t.py"}),  # commands, over its own dir
    ({"id": _hash(_CAT_ID), "command": "cat -n f"}, {"id": _WC_ID, "held": True}),
])
def test_cited_once_by_hash_or_command_without_held_it_holds_for_every_criterion_on_it(cat, wc):
    assert unrun_parts(_PARTS, _report(cat, wc), _DIRS) == {}


def test_not_cited_at_all_it_is_still_unrun_and_said_so():
    out = unrun_parts(_PARTS, _report({"id": _hash(_CAT_ID)}), _DIRS)
    assert out == {"A": [_WC_ID], "B": [_WC_ID]}
    gaps = unaccounted_for(SimpleNamespace(spec=SimpleNamespace(criteria=()), assignee="x"),
                           _report({"id": _hash(_CAT_ID)}), False, "v", {}, dirs=_DIRS, parts=_PARTS)
    assert "was not run over this delivery — nothing of it" in gaps["B"][0] and _WC_ID in gaps["B"][0]
    assert not any("cannot be credited" in g for g in gaps["B"])


def test_reported_not_holding_it_holds_for_no_criterion_and_the_refusal_says_so():
    report = _report({"id": _hash(_CAT_ID), "held": False}, {"id": _WC_ID, "held": True})
    assert unrun_parts(_PARTS, report, _DIRS) == {"A": [_CAT_ID], "B": [_CAT_ID]}
    assert "held: false" in part_credit(_PARTS, report, _DIRS)[1][_CAT_ID][0]


def test_cited_without_held_under_a_failing_criterion_it_is_not_credited():
    report = [{"criterion": "A", "verdict": "fail", "probe": [{"command": "cat -n f"}, {"id": _WC_ID, "held": True}]},
              {"criterion": "B", "verdict": "pass", "probe": []}]
    assert unrun_parts(_PARTS, report, _DIRS) == {"B": [_CAT_ID]}
    assert "does not pass, without `held: true`" in part_credit(_PARTS, report, _DIRS)[1][_CAT_ID][0]


def test_a_hash_two_demanded_probes_share_credits_neither_and_says_why():
    twin = part_criteria("root.cat2", [Criteria("flags", check=(Probe("cat flags again", "cat -n f", "1"),))])
    twin_id = probe_id(twin[0].name, twin[0].check[0])
    parts = {"A": _CAT + twin, "B": _CAT + twin}
    report = _report({"id": _hash(_CAT_ID), "command": "cat -n f"})
    assert unrun_parts(parts, report) == {"A": [_CAT_ID, twin_id], "B": [_CAT_ID, twin_id]}
    gaps = unaccounted_for(SimpleNamespace(spec=SimpleNamespace(criteria=()), assignee="x"), report, False, "v", {},
                           parts=parts)
    assert any("cannot be credited" in g and "names 2 demanded probes" in g and "full id" in g for g in gaps["B"])
    assert not any("nothing of it" in g for g in gaps["B"])
    # …and its full id disambiguates
    assert unrun_parts(parts, _report({"id": _CAT_ID}, {"id": twin_id})) == {}
