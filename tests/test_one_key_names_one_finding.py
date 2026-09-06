"""A dispute answers ONE finding, so a key has to name one.

Conflicts were keyed on their participants alone. An adversary's plan produced three separately
reasoned conflicts between the same two children — three different arguments about one pair — and
they collapsed to a single key: one four-word sentence closed all three, open findings went 13 → 10
on one call, and the stored record could show only that a key had been answered (wave 25,
2026-09-05).

What distinguishes the three is the REASON the checker gave, so the reason distinguishes the key. It
is handed back verbatim under `dispute_keys`, which is where a caller copies it from — nobody types
these from memory, and the CLI door already needs `criterion=@file` for keys containing commas.
"""
from __future__ import annotations

from gfso.core.graph.review import finding_keys

_TWO_CONFLICTS_ONE_PAIR = {
    "semantic_covered": False,
    "criteria_verdicts": [],
    "conflicts": [
        {"between": ["writer", "queue"],
         "why": "writer must fsync before returning while queue promises a non-blocking put"},
        {"between": ["writer", "queue"],
         "why": "writer owns the file handle exclusively while queue reopens it per item"},
    ],
    "undecided_obligations": [],
}


def test_two_conflicts_between_one_pair_are_two_findings():
    keys = finding_keys(_TWO_CONFLICTS_ONE_PAIR)

    assert len(keys) == 2, keys
    assert len(set(keys)) == 2, f"two arguments collapsed into one name: {keys}"
    assert all(k.startswith("conflict: writer, queue") for k in keys), keys


def test_the_reason_is_what_tells_them_apart():
    keys = finding_keys(_TWO_CONFLICTS_ONE_PAIR)

    assert "fsync" in keys[0], keys[0]
    assert "file handle" in keys[1], keys[1]


def test_answering_one_leaves_the_other_open():
    """The consequence that mattered: three arguments could be closed by answering one."""
    rec = {**_TWO_CONFLICTS_ONE_PAIR,
           "disputes": {finding_keys(_TWO_CONFLICTS_ONE_PAIR)[0]: {"why": "the fsync is inside put"}}}

    still_open = finding_keys(rec)

    assert len(still_open) == 1, still_open
    assert "file handle" in still_open[0]
