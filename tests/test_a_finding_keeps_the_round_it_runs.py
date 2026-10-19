"""A validation's scratch round that a standing finding runs is not pruned with the old rounds.

A finding whose named files are gone reads as unrunnable and stops being demanded (`unrerunnable`); the scratch kept
only the 20 newest rounds, so a root refuted over 16+ rounds lost its oldest findings with no ruling (critic,
2026-10-11, on GB_c_compiler's root.pp).
"""
from __future__ import annotations

import gfso.tools_llm as TL


def _rounds(tmp_path, n: int):
    work = tmp_path / "ws"
    work.mkdir()
    root = tmp_path / ".gfso-scratch-ws"
    for i in range(n):
        (root / f"kid_{1000 + i}").mkdir(parents=True)
        (root / f"kid_{1000 + i}" / "t.c").write_text("int main(){}", encoding="utf-8")
    return work, root


def test_the_round_a_finding_runs_survives_the_pruning(tmp_path):
    work, root = _rounds(tmp_path, 25)
    named = (f"./cc {root}/kid_1000/t.c; echo exit=$?",)
    TL._validation_place("kid", str(work), named)
    assert (root / "kid_1000" / "t.c").is_file()
    assert not (root / "kid_1001").exists(), "control: a round no finding runs is pruned as before"
