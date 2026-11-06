"""A validator's packet says of every EXACT pinned check that it is one, how its output is compared (`EXACT_READ`, the
words its author is given), and what the system's own run of it on this delivery observed (`_observe_exact`).

Told only "must show: a ok", a validator read the pin as a substring of `a` and `ok` on two lines and failed
root.preprocessor.pp-rest six rounds the system's own runs had matched 39 of 39 (gf-cc, 2026-11-06). And the finding
that FAIL left — the pin's own command over its laid inputs, citing the pin — is the pin's run, not a second demand.

CONTROLS: `_exact_said` → "" — both packet tests; drop `observed` from the `_validator_texts` call — the matched and
mismatch tests (the comparator line stays, the observation goes)."""
from __future__ import annotations

import pytest

from gfso.core.protocol.procedure import EXACT_READ, EXACT_TEXT, probe_id, without_pinned_runs
from tests.test_the_system_runs_an_exact_check_itself import _Says, _validated



class _Reads(_Says):
    """The validator of `_Says`, keeping the packet it was handed."""
    packets: list = []

    def run_agent(self, system, user, allowed_tools, cwd=None, timeout=None):
        _Reads.packets.append(user)
        return super().run_agent(system, user, allowed_tools, cwd, timeout)


@pytest.fixture
def read(monkeypatch):
    _Reads.packets = []
    monkeypatch.setattr("tests.test_the_system_runs_an_exact_check_itself._Says", _Reads)
    return _Reads.packets


@pytest.mark.parametrize("batch", ["0", "1"])
def test_an_exact_pin_the_system_matched_is_said_exact_compared_and_matched(tmp_path, monkeypatch, read, batch):
    monkeypatch.setenv("GFSO_VALIDATION_BATCH", batch)
    _validated(tmp_path, "a\nok", expect="a ok")                 # the pp-rest shape: one item per line
    packet = "".join(read)
    assert "EXACT" in packet and EXACT_READ in packet and EXACT_READ in EXACT_TEXT
    assert "it MATCHED" in packet and "it printed «" not in packet


def test_an_exact_pin_the_system_saw_print_otherwise_says_what_it_printed(tmp_path, read):
    _validated(tmp_path, "a\nno", expect="a ok")
    packet = "".join(read)
    assert "it printed «a ⏎ no», not that" in packet and "MATCHED" not in packet


def test_a_pin_not_exact_is_told_nothing_of_the_system(tmp_path, read):
    _validated(tmp_path, "a\nok", expect="a ok", exact=False)
    assert "EXACT:" not in "".join(read)


def test_the_finding_a_pin_s_fail_left_is_the_pin_s_run_and_the_validator_s_own_probe_stands():
    """The ledger rows of pp-rest as stored: the pin's command over its laid inputs as a token, citing the pin."""
    pin = {"command": "make -s >/dev/null && tests/pp_driver {inputs}/n1.c", "expect": "a ok"}
    pid = probe_id("ifndef-elif-nesting", pin)
    run = {"id": "ifndef-elif-nesting#43a425ae", "cited": pid, "expect": "a ok",
           "command": f"make -s >/dev/null && tests/pp_driver {{inputs:{pid}}}/n1.c"}
    own = {"id": "ifndef-elif-nesting#0d0d0d0d", "expect": "a \\n ok",
           "command": f"make -s >/dev/null && tests/pp_driver {{inputs:{pid}}}/n1.c | od -c"}
    kept = without_pinned_runs({"ifndef-elif-nesting": [run, own]}, {pid: pin["command"]})
    assert kept == {"ifndef-elif-nesting": [own]}
