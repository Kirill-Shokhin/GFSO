"""Every verb answers — no traceback reaches a caller, ever.

The doors are generated from one registry, so a verb that raises does not fail politely: over HTTP
it is a 500 with an empty body, over MCP a protocol error, over the CLI a Python traceback printed
at a person. Measured 2026-08-20 on real use: `create_task` with a string `spec` gave exactly that,
and `predictability: "high"` gave a bare `KeyError('HIGH')` — two verbs, one class of defect, and
nothing held the other twenty-six.

So this drives EVERY verb in the registry twice: once on a healthy graph with plausible arguments,
and once with the wrong kind of argument. Both times the requirement is the same and it is weak on
purpose — answer, don't raise, and be JSON — because that is exactly the contract the doors need and
the one nothing was checking. The verbs that spawn a model are exercised for their guards only (no
LLM is available here, and each is refused before it would spend one).
"""
from __future__ import annotations

import inspect
import json

import pytest

from gfso import tools_llm as TL
from tests.support import make_engine

# Verbs whose whole job is to spawn a model run. They are still called (their argument guards are
# the point), with an id that exists and a state that stops them before any transport is touched.
_LLM_VERBS = {"auto_decompose", "review_decomposition", "validate_result"}

_GOOD_SPEC = {"name": "leaf", "description": "a leaf",
              "criteria": [{"name": "c", "description": "C"}]}


def _engine():
    e = make_engine(llm=None, validate_signals=True, state_timeout=0)
    e.start()
    return e


def _seeded(e):
    """A small, ordinary graph: a root with ACCEPTED_RISKS, two children, one mapped criterion."""
    TL.TOOLS["create_task"](e, "root", {
        "name": "root", "description": "the goal",
        "criteria": [{"name": "c1", "description": "the thing"}],
        "accepted_risks": [{"item": "an unmodelled fault", "predictability": "extraordinary",
                            "justification": "accepted here", "invalidation_condition": "never"}]},
        "agent")
    TL.TOOLS["create_task"](e, "kid", dict(_GOOD_SPEC), assignee="agent", parent_id="root")
    TL.TOOLS["map_criterion"](e, "root", "kid", "c1")
    return e


_GOOD: dict[str, dict] = {
    "get_task": {"task_id": "kid"},
    "project": {"task_id": "root"},
    "get_checks": {"task_id": "root"},
    "get_graph": {},
    "list_holes": {"root_id": "root"},
    "get_review": {"task_id": "root"},
    "get_verdict": {"task_id": "kid"},
    "dispute_finding": {"task_id": "root", "criterion": "c1", "why": "it does hold"},
    "available_actions": {"task_id": "kid", "agent": "agent"},
    "get_dependencies": {},
    "metrics": {},
    "usage": {},
    "list_agents": {},
    "register_agent": {"agent_id": "probe-exec", "kind": "external"},   # no workdir needed for these
    "create_task": {"task_id": "fresh", "spec": dict(_GOOD_SPEC), "assignee": "agent",
                    "parent_id": "root"},
    "decompose": {"parent_id": "kid", "children": [{"task_id": "kid.a", "spec": dict(_GOOD_SPEC),
                                                    "covers": ["c"]}]},
    "revise": {"task_id": "kid", "spec": dict(_GOOD_SPEC), "agent": "agent",
               "reason": "spec_defect"},
    "edit_accepted_risks": {"task_id": "root", "agent": "agent",
                            "accepted_risks": [{"item": "another fault",
                                                "predictability": "extraordinary",
                                                "justification": "accepted", "invalidation_condition": "never"}]},
    "edit_criteria": {"task_id": "kid", "agent": "agent",
                      "criteria": [{"name": "c", "description": "C, sharper"}]},
    "reassign": {"task_id": "kid", "assignee": "someone", "reason": "capability_mismatch"},
    "reopen": {"task_id": "kid", "agent": "agent"},
    "add_dependency": {"from_id": "root", "to_id": "kid", "glue": "the input"},
    "remove_dependency": {"from_id": "root", "to_id": "kid"},
    "map_criterion": {"parent_id": "root", "child_id": "kid", "criterion_name": "c1"},
    "signal": {"task_id": "kid", "signal": "ACCEPT", "source": "agent"},
    "record_verdict": {"task_id": "kid", "verdict": "PASS", "reviewer": "someone-else",
                       "observed": {"c": "ran it, it printed what it should"}},
    "next_step": {},
    "next_steps": {},
    "auto_decompose": {"request": "do the thing", "root_id": "root"},
    "review_decomposition": {"task_id": "root"},
    "validate_result": {"task_id": "kid"},
}

# The wrong SHAPE, not merely a wrong value: the class of input that used to reach the interpreter.
_BAD: dict[str, dict] = {
    "get_task": {"task_id": "no-such-node"},
    "project": {"task_id": "no-such-node"},
    "get_checks": {"task_id": "no-such-node"},
    "get_graph": {},
    "list_holes": {"root_id": "no-such-node"},
    "get_review": {"task_id": "no-such-node"},
    "get_verdict": {"task_id": "no-such-node"},
    "dispute_finding": {"task_id": "no-such-node", "criterion": "nope", "why": ""},
    "available_actions": {"task_id": "no-such-node"},
    "get_dependencies": {},
    "metrics": {},
    "usage": {},
    "list_agents": {},
    "register_agent": {"agent_id": "probe-exec", "kind": ["not", "a", "kind"]},
    "create_task": {"task_id": "bad", "spec": "just do the thing"},
    "decompose": {"parent_id": "root", "children": "not-a-list"},
    "revise": {"task_id": "kid", "spec": "a sentence", "agent": "agent"},
    "edit_accepted_risks": {"task_id": "root", "accepted_risks": [{"item": "x",
                                                                   "predictability": "HIGH"}],
                            "agent": "agent"},
    "edit_criteria": {"task_id": "kid", "criteria": "one criterion", "agent": "agent"},
    "reassign": {"task_id": "no-such-node", "assignee": "someone"},
    "reopen": {"task_id": "no-such-node", "agent": "agent"},
    "add_dependency": {"from_id": "kid", "to_id": "kid"},          # a self-edge is a cycle
    "remove_dependency": {"from_id": "no-such-node", "to_id": "kid"},
    "map_criterion": {"parent_id": "root", "child_id": "kid", "criterion_name": "no-such-criterion"},
    "signal": {"task_id": "kid", "signal": "NOT_A_SIGNAL", "source": "agent"},
    "record_verdict": {"task_id": "kid", "verdict": "MAYBE", "reviewer": "someone-else"},
    "next_step": {"root_id": "no-such-node"},
    "next_steps": {"root_id": "no-such-node"},
    "auto_decompose": {"request": "", "root_id": "no-such-node"},
    "review_decomposition": {"task_id": "no-such-node"},
    "validate_result": {"task_id": "no-such-node"},
}


def test_the_table_covers_the_whole_registry():
    """A verb added without a row here would be silently unexercised — which is how the registry
    grew twenty-eight verbs with two of them able to hand a caller a traceback."""
    assert set(_GOOD) == set(TL.TOOLS) == set(_BAD), (
        f"registry and table disagree: only in registry {sorted(set(TL.TOOLS) - set(_GOOD))}, "
        f"only in table {sorted(set(_GOOD) - set(TL.TOOLS))}")


@pytest.mark.parametrize("verb", sorted(_GOOD))
@pytest.mark.parametrize("kind", ["good", "bad"])
def test_a_verb_answers_instead_of_raising(verb, kind):
    e = _seeded(_engine())
    args = (_GOOD if kind == "good" else _BAD)[verb]
    try:
        out = TL.TOOLS[verb](e, **args)
    except Exception as ex:                                 # noqa: BLE001 — that is the assertion
        pytest.fail(f"{verb} ({kind} arguments) raised {type(ex).__name__}: {ex}\n"
                    f"A door cannot forward this: HTTP turns it into a 500 with no body, and the "
                    f"CLI prints it at a person. Refuse in the verb's own terms instead.")
    finally:
        e.stop()
    json.dumps(out, default=str)                            # …and every answer must cross a wire


@pytest.mark.parametrize("verb", sorted(_LLM_VERBS))
def test_a_model_spawning_verb_refuses_a_missing_node_before_it_spends_anything(verb):
    """The three verbs that cost money must reach their guards first — a run spent on a node that
    does not exist is a run nobody can read."""
    e = _seeded(_engine())
    try:
        out = TL.TOOLS[verb](e, **_BAD[verb])
        assert isinstance(out, dict) and (out.get("error") or out.get("verdict") is None)
    finally:
        e.stop()


def test_every_verb_carries_a_description():
    """The docstring IS the description on all three doors (MCP tool schema, `gfso run <verb>
    --help`, the HTTP listing). A verb without one is a verb nobody can be told how to use."""
    thin = sorted(n for n, f in TL.TOOLS.items() if len((f.__doc__ or "").strip()) < 60)
    assert not thin, f"verbs with no usable description: {thin}"
