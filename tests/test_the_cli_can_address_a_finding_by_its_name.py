"""Almost every Level-2 finding key contains a comma, and the CLI split values on commas.

`conflict: writer, queue` · `undecided: the goal requires X, not Y` — the keys `get_review` hands back
under `dispute_keys` are sentences. The door split any value for a list-typed parameter on commas, so
a caller who copied the key it was given was told their own key *"is not an open Level-2 finding"*.
A stranger found the workaround (`criterion=@file`, a JSON file holding one string) and reported the
dispute door as effectively closed from the CLI (wave 25, 2026-09-05).

The parameter takes either shape — one key or several — and that is readable off the signature: a
union admitting `str` means a bare value IS the string. What must not change is the rule that made
comma-splitting exist in the first place: `failed_criteria=exact_duplicate_grouping` once arrived as
a plain string, the engine iterated it, and a node came back failed on twenty-four one-letter
"criteria".
"""
from __future__ import annotations

import inspect
import typing

from gfso import tools as T
from gfso.driver import _wants_list


def _param(verb: str, name: str):
    fn = T.TOOLS[verb]
    hints = typing.get_type_hints(fn)
    p = inspect.signature(fn).parameters[name]
    return p.replace(annotation=hints[name]) if name in hints else p


def test_a_parameter_that_takes_either_shape_is_not_split():
    assert _wants_list(_param("dispute_finding", "criterion")) is False


def test_a_parameter_that_takes_only_a_list_still_is():
    """The negative control — the defect comma-splitting was built for must stay closed."""
    assert _wants_list(_param("signal", "failed_criteria")) is True
    assert _wants_list(_param("signal", "blocker_task_ids")) is True
    assert _wants_list(_param("edit_criteria", "criteria")) is True


def test_the_decision_survives_a_raw_string_annotation():
    """`tools.py` carries `from __future__ import annotations`, so a signature read off it is STRINGS.

    The rule resolves them itself. It did not, for one iteration: the door resolved before asking and
    the rule answered False for every string, so any other caller — the suite among them — silently
    un-listed every list parameter. A rule that is only correct when its caller prepares the input is
    half a rule.
    """
    raw = inspect.signature(T.TOOLS["signal"]).parameters["failed_criteria"]
    assert isinstance(raw.annotation, str), "this test guards a resolution that is no longer needed"
    assert _wants_list(raw) is True, "the rule failed on the raw form its own door hands it"
    assert _wants_list(inspect.signature(T.TOOLS["dispute_finding"]).parameters["criterion"]) is False
