"""A probe its validator says it did not run observed nothing: it meets no demand and refutes nothing.

Series 2 REF 2 (2026-10-29, root.reject): a regression line bound to a past round's scratch could not write there in a
later round; its setup failed, `&&` skipped the compiler and it printed `rejected` — the line it expected — with nothing
judged. Counted, a cited id met the line's demand (`unrun_regression` read `{}`): a PASS with nothing re-observed."""
from gfso.core.protocol.invariants import probes_of
from gfso.core.protocol.procedure import unrun_regression


def _entry(ran):
    return {"criterion": "Builtins", "verdict": "pass", "probe": [
        {"id": "Builtins#167cf8d2", "command": "sh x/cmp.sh", "expect": "cd failed", "ran": ran}]}


def test_a_regression_line_not_run_is_still_owed():
    standing = {"Builtins": [{"id": "Builtins#167cf8d2", "command": "sh x/cmp.sh"}]}
    assert probes_of(_entry(False)) == []
    assert unrun_regression(standing, [_entry(False)], standing=lambda _: True) == {"Builtins": ["Builtins#167cf8d2"]}
    assert unrun_regression(standing, [_entry(True)], standing=lambda _: True) == {}
    assert unrun_regression(standing, [_entry(None)], standing=lambda _: True) == {}, "unsaid is a run, as before"
