"""`TASK_PACKET.md` promises "the exact keys the engine reads". Three of them were not.

A tester on the HTTP door followed the page and was refused three times in a row (wave 26,
2026-09-06): `edit_accepted_risks(task_id, items)` -- the engine wants `accepted_risks`;
`map_criterion(parent_id, child_id, criterion)` -- it wants `criterion_name`; and `record_verdict`
had no shape on the page at all, so `observed` went out as a list and was refused for it.

The error messages were good enough to recover from, which is the only reason it cost minutes rather
than the session. But a page that says it carries the exact keys and does not is worse than a page
that says nothing, and nothing here was checking it -- one grep apart, as they put it.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

import gfso.tools as T

_DOC = Path(__file__).resolve().parents[1] / "docs" / "TASK_PACKET.md"
_BLOCK = re.search(r"## Authoring calls\n\n```\n(.*?)```", _DOC.read_text(encoding="utf-8"), re.S)

#: Keys of the NESTED payloads a call carries (`children=[{task_id, spec, …}]`,
#: `observed={criterion_name: …}`). They are not parameters of the verb and are documented beside it.
_PAYLOAD_KEYS = {"criterion_name", "child_id", "task_id", "spec", "assignee", "covers"}


def _params(verb: str) -> set:
    return {p.name for p in list(inspect.signature(T.TOOLS[verb]).parameters.values())[1:]
            if not p.name.startswith("_")}


def _documented(verb: str) -> set:
    """The argument names the page prints for `verb`.

    The argument list of THIS call only: parentheses do not nest in this block, so the first closing
    one ends it. An earlier cut of this test sliced to the next `)\\n` instead and read the FOLLOWING
    calls' arguments as this one's -- a check that fails on its own parsing teaches nothing.
    """
    m = re.search(re.escape(verb) + r"\(([^)]*)\)", _BLOCK.group(1), re.S)
    assert m is not None, f"{verb} is not documented in TASK_PACKET.md's authoring block"
    # a name is a token that is followed by `=`, `,` or the end of the list — never one inside a
    # trailing comment, which is prose about the call rather than part of it
    args = m.group(1).split("#")[0]
    return set(re.findall(r"\b([a-z_]+)\s*(?==|,|$)", args, re.M))


@pytest.mark.parametrize("verb", ["create_task", "decompose", "edit_criteria",
                                  "edit_accepted_risks", "map_criterion", "add_dependency",
                                  "record_verdict"])
def test_every_name_the_page_prints_is_a_real_parameter(verb):
    assert _BLOCK, "the authoring-calls block moved; this test cannot check what it cannot find"
    stray = _documented(verb) - _params(verb) - _PAYLOAD_KEYS
    assert not stray, f"{verb}: the page names {sorted(stray)}, the engine takes {sorted(_params(verb))}"


def test_the_three_that_had_drifted_are_right_now():
    text = _DOC.read_text(encoding="utf-8")
    assert "edit_accepted_risks(task_id, accepted_risks)" in text
    assert "map_criterion(parent_id, child_id, criterion_name)" in text
    assert "record_verdict(" in text and "observed={criterion_name:" in text


def test_the_old_spellings_are_gone():
    """The control: a test that only asserts the new text would pass with both spellings present."""
    text = _DOC.read_text(encoding="utf-8")
    assert "edit_accepted_risks(task_id, items)" not in text
    assert "map_criterion(parent_id, child_id, criterion)\n" not in text
