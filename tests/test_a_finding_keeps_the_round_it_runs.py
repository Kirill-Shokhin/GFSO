"""A validation's scratch round that a standing finding runs is not pruned with the old rounds.

A finding whose named files are gone reads as unrunnable and stops being demanded (`unrerunnable`); the scratch kept
only the 20 newest rounds, so a root refuted over 16+ rounds lost its oldest findings with no ruling (critic,
2026-10-11, on GB_c_compiler's root.pp).
"""
from __future__ import annotations

import time

import gfso.tools_llm as TL
from gfso.adapters.execution import LocalExecution, scratch_of
import gfso.validate as VAL


def _rounds(tmp_path, n: int):
    work = tmp_path / "ws"
    work.mkdir()
    root = scratch_of(work, None, LocalExecution())
    for i in range(n):
        (root / f"kid_{1000 + i}").mkdir(parents=True)
        (root / f"kid_{1000 + i}" / "t.c").write_text("int main(){}", encoding="utf-8")
    return work, root


def test_the_round_a_finding_runs_survives_the_pruning(tmp_path):
    work, root = _rounds(tmp_path, 25)
    named = (f"./cc {root}/kid_1000/t.c; echo exit=$?",)
    VAL._validation_place("kid", str(work), LocalExecution(), named)
    assert (root / "kid_1000" / "t.c").is_file()
    assert not (root / "kid_1001").exists(), "control: a round no finding runs is pruned as before"


def test_a_round_a_validation_may_still_be_running_in_survives_the_pruning(tmp_path):
    """Another validation's round made within VALIDATING's bound may be running: pruned under its batches, their
    directory went mid-run (a flake of the default suite, 2026-11-10, two tests sharing one place)."""
    work, root = _rounds(tmp_path, 25)
    young = root / f"aaa_{int(time.time()) - 5}"                     # sorts first by name, made seconds ago
    young.mkdir()
    VAL._validation_place("kid", str(work), LocalExecution())
    assert young.is_dir()
    assert not (root / "kid_1000").exists(), "control: an old round no finding runs is pruned as before"


def test_the_old_rounds_go_oldest_first_whatever_their_names(tmp_path):
    work, root = _rounds(tmp_path, 25)
    later = root / "aaa_5000"                                         # first by name, newest of the old by epoch
    later.mkdir()
    VAL._validation_place("kid", str(work), LocalExecution())
    assert later.is_dir() and not (root / "kid_1005").exists()


def test_with_no_bound_a_round_still_running_survives_and_goes_once_it_ended(tmp_path, monkeypatch):
    """`GFSO_BOUND_VALIDATING=0` runs a validation with no bound: age proves nothing, the process's record of its
    running rounds does (critic over 13de2b4)."""
    monkeypatch.setenv("GFSO_BOUND_VALIDATING", "0")
    work, root = _rounds(tmp_path, 25)
    running = str(root / "kid_1000")
    VAL._LIVE_ROUNDS.add(running)
    try:
        VAL._validation_place("kid", str(work), LocalExecution())
        assert (root / "kid_1000").is_dir() and not (root / "kid_1001").exists()
    finally:
        VAL._LIVE_ROUNDS.discard(running)
    VAL._validation_place("kid", str(work), LocalExecution())
    assert not (root / "kid_1000").exists(), "ended, it is an old round like any other"
