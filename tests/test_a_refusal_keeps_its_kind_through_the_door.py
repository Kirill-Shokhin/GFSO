"""A refusal's KIND is a fact about where the refusal came from, and it survived one round trip.

`Engine.refusal_of` publishes three kinds and its own docstring says why they are not decoration:
`state` = this signal is the wrong button here, `guard` = the state admits it but the transition's
precondition does not hold, `rule` = a standing rule above the FSM said no (the seam's verdict, the
AND over children, the plan gate). "A caller who cannot tell them apart cannot tell 'wrong button'
from 'not yet' from 'not yours'."

They could not be told apart. `refusal_of` decided the kind from whether an error SENTENCE existed:
an entry with any error at all became `rule` whenever the state admitted the signal. The FSM path
writes its sentence into the log too, so a GUARD refusal coming back through `signal` was relabelled
`rule` — while the same refusal computed directly answered `guard`, under the identical words "its
transition GUARD refused it". Probed 2026-09-07.

The kind is now taken from where the refusal came from, and the FSM's two sentences have one author
(`not_admissible_here`) instead of a hand-written second copy inside `refusal_of` — which is what
made the drift possible in the first place.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from gfso.core.types import Signal, TaskId
from tests.support import UNMODELLED_FAULT, make_engine

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]


def _root(state: str):
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    T.create_task(e, "root", {"description": "a goal", "accepted_risks": _RISK,
                              "criteria": [{"name": "g", "description": "G holds"}]},
                  assignee="agent")
    if state != "OFFERED":
        T.signal(e, "root", "ACCEPT", "agent")
    if state == "VALIDATING":
        T.signal(e, "root", "DELIVER", "agent", result="the aggregate")
    return e


# ASSIGN is admitted in every one of these states (§14.3: a re-ASSIGN is the revision edge) and its
# guard wants a contract, which `signal` cannot carry — so it is the refusal that is a GUARD in every
# state the FSM reassigns from, and the one the round trip corrupted.
@pytest.mark.parametrize("state", ["OFFERED", "EXECUTING", "VALIDATING"])
def test_the_door_reports_the_kind_the_engine_computed(state: str) -> None:
    direct = _root(state).refusal_of(TaskId("root"), Signal.ASSIGN, None).as_dict()
    through = T.signal(_root(state), "root", "ASSIGN", "agent")

    assert direct["refused_by"] == "guard", direct
    assert through["refused_by"] == direct["refused_by"], (
        f"in {state} the same refusal is '{direct['refused_by']}' computed directly and "
        f"'{through['refused_by']}' through `signal` — the kind changed on the round trip, and the "
        f"sentence under both is the same one. A caller routing on `refused_by` reads 'a rule above "
        f"the FSM refused this' where the FSM's own guard did."
    )
    assert through["error"] == direct["error"], (through["error"], direct["error"])


def test_a_rule_refusal_is_still_a_rule_refusal() -> None:
    """The control in the other direction: tightening the classifier must not swallow the real ones.

    A PASS on a delivered seam with no verdict is refused by `validate_signal` — a rule above the
    FSM, and the kind the whole distinction exists to name."""
    e = _root("VALIDATING")
    out = T.signal(e, "root", "PASS", "agent")
    assert out["refused_by"] == "rule", out
    assert "independent verdict" in out["error"]


def test_a_signal_the_state_does_not_admit_is_a_state_refusal() -> None:
    """And the third kind, so all three are held by this file rather than two of them."""
    out = T.signal(_root("OFFERED"), "root", "PASS", "agent")
    assert out["refused_by"] == "state", out
    assert "not admitted by state OFFERED" in out["error"]


def test_a_signal_on_a_node_that_is_not_there_still_says_why() -> None:
    """The headline case of the repair, which the first version of this file did not hold.

    `loop.py` returns without writing an audit entry for an unknown id, so `refusal_of` is called
    with `entry=None` AND no state — and an earlier spelling let the reason fall through as None,
    which `SignalOutcome.as_dict` renders as `error: ""`. A typo'd task id on any door is the most
    ordinary way to reach a refusal in this product, and it answered with an empty string."""
    out = T.signal(_root("OFFERED"), "ghost", "PASS", "agent")

    assert out["refused_by"] == "state", out
    assert out["error"], "a refusal with an empty reason is the silence `refusal_of` exists to end"
    assert "no task 'ghost'" in out["error"], out["error"]
    assert "project" in out["error"], (
        "pointing at the wrong project is the other way to reach this, and looks identical "
        "from the caller's side — an empty graph and a graph you are not pointed at read the same"
    )
