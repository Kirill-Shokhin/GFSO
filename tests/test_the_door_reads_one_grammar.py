"""`--assignee me` was silently read as two positionals, and the node waited forever.

This door's grammar is `key=value`. The flag spelling is what most CLIs take, so it is what a person
tries -- and it fell straight through into DATA. Measured here 2026-09-05:

    gfso run create_task root '{...}' --assignee me

produced a node whose `assignee` was the literal string `"--assignee"` and whose PARENT was `"me"`.
Both silently. The node then sat in OFFERED waiting for signals from a party that does not exist, and
nothing anywhere said why.

The `key=value` typo rule beside this one already refuses by name, and its comment says why: a typo
that does not fail is not a typo that worked. A flag is the same mistake in the other notation.
"""
from __future__ import annotations

import gfso.tools as T
from gfso.driver import _parse_args
from tests.support import make_engine


def _refusal(verb, argv):
    pos, kw, bad = _parse_args(verb, T.TOOLS[verb], argv)
    return bad


def test_a_flag_is_refused_rather_than_stored():
    bad = _refusal("create_task", ["root", '{"description": "g"}', "--assignee", "me"])
    assert bad and bad["refused"] is True
    assert "key=value" in bad["error"]


def test_a_flag_naming_a_real_parameter_is_told_the_spelling():
    bad = _refusal("create_task", ["root", "--assignee", "me"])
    assert "assignee=<value>" in bad["error"]


def test_a_flag_naming_nothing_is_told_what_the_verb_takes():
    bad = _refusal("get_task", ["xyz", "--assignee", "me"])
    assert "not a parameter of get_task" in bad["error"] and "task_id" in bad["error"]


def test_the_grammar_the_door_does_read_still_works():
    """The control: a rule that refuses everything starting with a dash would pass the tests above."""
    pos, kw, bad = _parse_args("get_task", T.TOOLS["get_task"], ["task_id=xyz"])
    assert bad is None and kw == {"task_id": "xyz"}
    pos, kw, bad = _parse_args("get_task", T.TOOLS["get_task"], ["xyz"])
    assert bad is None and pos == ["xyz"]


def test_a_negative_number_is_data_not_a_flag():
    """`-5` is a value someone means to pass. The guard is about flag NAMES, not about the dash."""
    pos, kw, bad = _parse_args("get_task", T.TOOLS["get_task"], ["-5"])
    assert bad is None and pos == ["-5"]     # …typed by the signature, which asks for a str here


def test_a_node_created_with_no_contract_says_what_it_is():
    """`gfso run create_task` with nothing after it CREATES a node -- a generated id, an empty spec,
    in whatever graph the session stands in. That is legal (authoring later is supported and
    `spec` is optional on purpose), and the reply was a success line that said none of it. Typed to
    see the shape of the verb, it leaves an unusable node behind: two such strays sit in this
    machine's `default` project. The node can never be judged -- V is the conjunction over its
    criteria and over an empty set that is vacuously true, which the engine refuses at the record --
    so the reply now says that, and how to author it.
    """
    e = make_engine()
    e.start()
    bare = T.TOOLS["create_task"](e)
    assert "NO criteria" in bare["note"] and "revise(" in bare["note"]
    authored = T.TOOLS["create_task"](e, "x", {"description": "g",
                                               "criteria": [{"name": "c", "description": "C"}]})
    assert "note" not in authored, "a node with a contract must not be lectured about not having one"
    e.stop()
