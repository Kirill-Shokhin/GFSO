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
from tests.support import FakeSpec

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
    gaps = unaccounted_for(SimpleNamespace(spec=FakeSpec(criteria=()), assignee="x"),
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
    gaps = unaccounted_for(SimpleNamespace(spec=FakeSpec(criteria=()), assignee="x"), report, False, "v", {},
                           parts=parts)
    assert any("cannot be credited" in g and "names 2 demanded probes" in g and "full id" in g for g in gaps["B"])
    assert not any("nothing of it" in g for g in gaps["B"])
    # …and its full id disambiguates
    assert unrun_parts(parts, _report({"id": _CAT_ID}, {"id": twin_id})) == {}


_S = part_criteria("root.scaffold", [Criteria("build", check=(Probe("clean build", "make build", "0"),))])
_I = part_criteria("root.integrate", [Criteria("scaffold: build", check=(Probe("clean build", "make build", "0"),))])
_S_ID, _I_ID = probe_id(_S[0].name, _S[0].check[0]), probe_id(_I[0].name, _I[0].check[0])


@pytest.mark.parametrize("held", [True, None])
def test_a_hash_two_parts_copies_of_one_check_share_names_both(held):
    """The measured shape: `integrate` copies `scaffold`'s pin (one hash, two ids); the validator cites the hash —
    under a criterion resting on the copy — and every criterion resting on either is observed (the haiku 4.5 sql root,
    2026-10-26: 15 of 16 criteria ⊥ when such a citation named neither)."""
    report = [{"criterion": "A", "verdict": "pass", "probe": [{"id": _hash(_S_ID), **({"held": True} if held else {})}]},
              {"criterion": "B", "verdict": "pass", "probe": [{"id": _hash(_S_ID), **({"held": True} if held else {})}]}]
    assert part_credit({"A": _S, "B": _I}, report)[0] == {_S_ID, _I_ID}
    assert unrun_parts({"A": _S, "B": _I}, report) == {}


def test_a_copy_cited_by_its_own_id_touches_only_itself():
    """A full id names one probe: a copy cited without `held` under a failing criterion voids no original reported holding
    (critic r3, 2026-10-26); a copy reported not holding voids every copy, the original said holding included — one
    observation, a contradiction read as a FAIL (replay mutation, 2026-10-27)."""
    report = [{"criterion": "A", "verdict": "pass", "probe": [{"id": _S_ID, "held": True}]},
              {"criterion": "B", "verdict": "fail", "probe": [{"id": _I_ID}]}]
    assert part_credit({"A": _S, "B": _I}, report)[0] == {_S_ID}
    report[1]["probe"] = [{"id": _I_ID, "held": False}]
    # …but a copy reported NOT holding is the same observation as the original said holding: neither is credited
    assert part_credit({"A": _S, "B": _I}, report)[0] == set()
    assert unrun_parts({"A": _S, "B": _I}, report) == {"A": [_S_ID]}   # A's pass stands on a check reported failing


def test_a_shared_hash_reported_not_holding_voids_every_copy():
    report = [{"criterion": "A", "verdict": "pass", "probe": [{"id": _S_ID, "held": True}]},
              {"criterion": "B", "verdict": "fail", "probe": [{"id": _hash(_S_ID), "held": False}]}]
    assert part_credit({"A": _S, "B": _I}, report)[0] == set()


def test_copies_differing_by_a_space_inside_the_command_are_two_checks():
    twin = part_criteria("root.integrate", [Criteria("t", check=(Probe("t", "test x = 'a  b'", "0"),))])
    one = part_criteria("root.scaffold", [Criteria("t", check=(Probe("t", "test x = 'a b'", "0"),))])
    report = [{"criterion": "A", "verdict": "pass", "probe": [{"id": probe_id(one[0].name, one[0].check[0]), "held": True}]},
              {"criterion": "B", "verdict": "pass", "probe": []}]
    assert unrun_parts({"A": one, "B": twin}, report) == {"B": [probe_id(twin[0].name, twin[0].check[0])]}


def test_a_shared_hash_cited_once_without_held_under_a_criterion_on_one_copy_observes_both():
    """One run of one check over one delivery, under a criterion that passes and rests on one copy, is the observation
    the other copy's criterion rests on too — read over the copies as one, not copy by copy."""
    report = [{"criterion": "A", "verdict": "pass", "probe": []},
              {"criterion": "B", "verdict": "pass", "probe": [{"id": _hash(_S_ID)}]}]
    assert part_credit({"A": _S, "B": _I}, report)[0] == {_S_ID, _I_ID}
    assert unrun_parts({"A": _S, "B": _I}, report) == {}


def test_a_copy_shown_holding_by_its_own_full_id_holds_for_every_copy():
    """One observation, however many ids it is pinned under: a twin shown holding by its copy's full id was read as
    "not run" for the other, and six of seven validations of one sound sql root were refused (2026-10-27)."""
    report = [{"criterion": "A", "verdict": "pass", "probe": [{"id": _I_ID, "held": True}]},
              {"criterion": "B", "verdict": "pass", "probe": []}]
    assert part_credit({"A": _S, "B": _I}, report)[0] == {_S_ID, _I_ID}
    assert unrun_parts({"A": _S, "B": _I}, report) == {}


def test_the_wholes_own_probe_shown_holding_holds_for_a_parts_copy_of_it():
    own = [Criteria("build", check=(Probe("clean build", "make build", "0"),))]
    report = [{"criterion": "build", "verdict": "pass", "probe": [{"id": probe_id("build", own[0].check[0]),
                                                                    "held": True}]}]
    assert part_credit({"build": _I}, report, own=own)[0] == {_I_ID}


def test_a_copy_the_packet_no_longer_lists_is_shown_by_the_wholes_own_probe_under_its_own_criterion():
    """The packet owes a probe once: a part mapped only to criterion X carrying a copy of the whole's own probe under Y
    is not listed again, so the validator cites the own probe under Y, without `held` as the schema asks for own
    probes. That citation is the own probe's run (`unrun_pinned`), so it is the copy's too (critic over the identity)."""
    q, p = Probe("builds", "make && echo OK", "OK"), Probe("query works", "./db < t1.sql", "3")
    own = (Criteria("build", check=(q,)), Criteria("queries", check=(p,)))
    parts = {"build": part_criteria("root.scaffold", (Criteria("smoke", check=(p,)),))}
    report = [{"criterion": "build", "verdict": "pass", "probe": [{"id": probe_id("build", q)}]},
              {"criterion": "queries", "verdict": "pass", "probe": [{"id": probe_id("queries", p)}]}]
    assert unrun_parts(parts, report, own=own) == {}
    report[1]["verdict"] = "fail"                         # under a criterion it does not pass, it vouches for nothing
    assert unrun_parts(parts, report, own=own) == {"build": [probe_id("root.scaffold/smoke", p)]}
