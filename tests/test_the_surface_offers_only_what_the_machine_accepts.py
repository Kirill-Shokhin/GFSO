"""The affordance surface may not name a signal a standing RULE will refuse — as a rule, not again.

`available_actions` answers "what can be done with this node from where you stand". Four times now
the answer has named a signal the engine then refused: DELIVER on a parent with open children
(2026-08-21, the node sat outside the frontier for an hour), ACCEPT under an unadmitted plan, ASSIGN
on a consumed terminal, PASS on a delivered seam with no verdict (2026-08-22, a driver read the bare
list as an invitation and closed a node over a stale FAIL). Each was patched where it was found.

Two more were found on 2026-09-07, and they are the reason this file is a sweep rather than a sixth
patch (a third, the node's own plan gone red, was found by a reviewer of the sweep itself): PASS advertised on a parent whose children have not passed, which Thm 1 (§11.1) forbids
outright, and PASS advertised to anyone on the validator roster with no verdict on the record —
where the surface had grown an exemption for *who signs* directly beneath its own comment saying the
question is not who signs. The first surfaced only as a side effect: the class instrument for
"a node in a state with no exit" stayed green with a real lock restored, because its crude half —
"something advertises a move" — was true, and it was true BECAUSE this surface advertised the
refused signal. A guard reading a lying surface inherits the lie.

The invariant, stated once: **for every shape and every asker, every action the surface advertises
is accepted by the machine, or refused for a reason that is not `rule`.** The three refusal kinds are
distinct facts (`Engine.refusal_of`): `state` = wrong button for this state, `guard` = the transition's
own precondition, `rule` = a standing rule above the FSM (the seam's verdict, the AND over children,
the plan gate). Only `rule` is this file's subject: the state machine's own vocabulary is what
`available_actions` reads to build the list, so it cannot disagree with itself there — a `rule`
refusal is exactly the class where the surface and the machine have separate opinions.

Each advertised action is tried on a FRESHLY BUILT graph, because trying it changes the shape.

WHAT THIS FILE ACTUALLY HOLDS, measured rather than asserted. With every gate in `_gated_out`
removed, four shapes go red: the two 2026-09-07 findings (the conjunction, and the roster exemption
at the seam), the node's own plan gone red, and the plan gate on a child. Two shapes in the table do
NOT go red under that control, and they are kept with their reason rather than dropped or claimed:

  · `"parent still executing, children open"` — DELIVER there is genuinely admissible (§14.3), and
    `_gated_out` withholds it as a RECOMMENDATION, not because the machine would refuse. It can
    never be a `rule` refusal, so this test cannot be its instrument; it is here as the control that
    the sweep does not fail a shape whose surface is merely opinionated.
  · `"delivered seam, no verdict, asked by a stranger"` — now stopped one layer earlier, by the role
    filter in `Engine._roles_of`, so the seam gate it was written for never gets a turn.

The count was two before that was checked, while this docstring already claimed the file held five
prior patches "from one place". A sweep that has not been run against its own subject removed is a
list of scenarios, not an instrument — the same lesson as the class instrument for stuck nodes,
which passed eleven shapes with a real lock restored.
"""
from __future__ import annotations

import pytest

import gfso.tools as T
from tests.support import UNMODELLED_FAULT, make_engine

_RISK = [{"item": UNMODELLED_FAULT.item, "predictability": "EXTRAORDINARY"}]

#: The arguments each signal needs to be *about* something — Inv-3 wants the failed set, CANCEL and
#: the rest want their reason. Missing arguments are a caller's error, not a disagreement between
#: the surface and the machine, and would otherwise fill the sweep with refusals it is not about.
_ARGS = {
    "DELIVER": {"result": "what was produced, and how each criterion is met"},
    "CANCEL": {"reason": "the goal went away"},
    "CHALLENGE": {"reason": "the spec does not say what 'holds' means"},
    "REJECT_CHALLENGE": {"justification": "it says it in the second sentence"},
    "ACCEPT_CHALLENGE": {"reason": "fair — sharpened"},
    "BLOCK": {"reason": "waiting on something outside", "external": True},
    "RESOLVE_BLOCK": {"action": "the outside thing arrived", "external": True},
    "CONFIRM_CANCEL": {"in_flight": "nothing had been started"},
}

#: ASSIGN is the one advertised action `signal` cannot send: a re-ASSIGN carries a contract
#: (`fsm.py` takes the edge on `spec is not None`) and `signal` has no `spec` parameter, so it is
#: guard-refused on every live node. That is not the surface disagreeing with the machine — it is a
#: different DOOR, and `available_actions` now says which. The sweep sends it through that door, so
#: what it tests stays "is the offer real" rather than "did the sweep call the right function".
_DOORS = {"ASSIGN": lambda e, tid, who: T.revise(
    e, tid, {"description": "the goal, sharpened", "accepted_risks": _RISK,
             "criteria": [{"name": "g", "description": "G holds, measurably"}]},
    who, reason="scope_expansion")}


def _refused(out) -> bool:
    """Did the act happen — asked in every shape the doors answer in.

    The same question `tools._refused` owns for the product; restated here rather than imported so
    the test does not depend on a private helper of the thing it measures."""
    return bool(not isinstance(out, dict) or out.get("error") or out.get("refused")
                or out.get("accepted") is False or out.get("recorded") is False)


def _send(e, task_id, act, who):
    # FAIL names a criterion OF THIS NODE (Inv-3), so the sweep reads it off the node instead of
    # hard-coding the root's. The hard-coded `["g"]` was invisible while every shape asked about the
    # root, and turned the first shape about a CHILD red for a reason that had nothing to do with
    # the subject — a fixture failing in the instrument's own voice.
    if act == "FAIL":
        _t = e.get_task(task_id)
        return T.signal(e, task_id, "FAIL", who,
                        failed_criteria=[_t.spec.criteria[0].name])
    # A RAISE IS A REFUSAL TOO. `tools.py`'s standing rule is that the verbs answer rather than
    # raise — "that is about the SHAPE of the answer, not about pretending the act happened" — and
    # `revise` keeps it for an unknown id (`{"error": …}`) but lets the issuer rule out as a
    # `ValueError`. So the same refusal is a dict through one path and an exception through another.
    # Recorded here rather than worked around silently: for this sweep's purpose both mean the act
    # did not happen. (Filed for the queue; a door that answers in two shapes is the class this
    # repository keeps finding.)
    try:
        if act in _DOORS:
            return _DOORS[act](e, task_id, who)
        return T.signal(e, task_id, act, who, **_ARGS.get(act, {}))
    except (ValueError, PermissionError) as ex:
        return {"error": str(ex), "refused": True}


def _root_only(e, *, assignee="agent"):
    T.create_task(e, "root", {"description": "a goal", "accepted_risks": _RISK,
                              "criteria": [{"name": "g", "description": "G holds"}]},
                  assignee=assignee)


def _with_children(e, *, kid_assignee="agent"):
    _root_only(e)
    for kid in ("a", "b"):
        T.create_task(e, kid, {"description": f"work {kid}",
                               "criteria": [{"name": kid, "description": f"{kid} holds"}]},
                      assignee=kid_assignee, parent_id="root")
        T.map_criterion(e, "root", kid, "g")


def _settle_children(e):
    """Drive both children to DONE/PASS, so the parent's conjunction is satisfied."""
    for kid in ("a", "b"):
        T.signal(e, kid, "ACCEPT", "agent")
        T.signal(e, kid, "DELIVER", "agent", result=f"{kid} is done")
        T.record_verdict(e, kid, "PASS", reviewer="rev",
                         observed={kid: f"ran the check for {kid}; it holds"})
        T.signal(e, kid, "PASS", "agent")


def _deliver_root(e):
    T.signal(e, "root", "ACCEPT", e.get_task("root").assignee)
    T.signal(e, "root", "DELIVER", e.get_task("root").assignee, result="the aggregate")


# Each shape: a builder, the node to ask about, who is asking, and whether the Level-2 execution gate
# must be ON for the shape to exist at all. The set is not exhaustive over the FSM — it is the shapes
# where surface and machine have historically disagreed, plus the ones the two 2026-09-07 findings
# live in, plus their healthy controls.
#
# THE GATE FLAG IS NOT DECORATION. `tests/conftest.py` turns `GFSO_L2_GATE` OFF suite-wide (the canon's
# EXPLORE branch, §13.5 — the suite is substrate-free and runs no model). The plan-gate shape below was
# written without noticing that, so in the suite's own environment the gate it names did not exist:
# `execution_blocked_by` returned None, ACCEPT was never withheld, and the shape stayed green with
# every surface gate removed. A shape blind to its own subject is the defect it guards against, wearing
# a name — the same lesson the class instrument for stuck nodes had to learn on 2026-09-07.
SHAPES = {
    # …the two found on 2026-09-07.
    "delivered parent, children untouched": (
        lambda e: (_with_children(e), _deliver_root(e),
                   T.record_verdict(e, "root", "PASS", reviewer="rev",
                                    observed={"g": "read the children's output; it holds"})),
        "root", "agent", False),
    "delivered seam, no verdict, asked by the roster": (
        lambda e: (_root_only(e, assignee="worker"),
                   e._graph.authorized_validators.add("val-1"), _deliver_root(e)),
        "root", "val-1", False),
    # …the SECOND who-independent PASS rule, which `_gated_out` did not model until the engine got
    # one owner for both: every child has settled, so the conjunction is satisfied, but the parent's
    # own plan has since gone red (a criterion nothing covers) and §13.4 refuses the aggregate.
    "settled children under a plan that has gone red": (
        lambda e: (_with_children(e), _settle_children(e),
                   T.edit_criteria(e, "root", [{"name": "g", "description": "G holds"},
                                               {"name": "g2", "description": "and G2 holds"}]),
                   _deliver_root(e),
                   T.record_verdict(e, "root", "PASS", reviewer="rev",
                                    observed={"g": "read the children's output; it holds",
                                              "g2": "read it; it holds too"})),
        "root", "agent", False),
    # …and the ones already patched, which this sweep now holds from one place.
    "delivered seam, no verdict, asked by a stranger": (
        lambda e: (_root_only(e, assignee="worker"), _deliver_root(e)),
        "root", "someone", False),
    "parent still executing, children open": (
        lambda e: (_with_children(e), T.signal(e, "root", "ACCEPT", "agent")),
        "root", "agent", False),
    "child under a plan with no Level-2 verdict": (
        lambda e: _with_children(e),
        "a", "agent", True),
    # …the INTERNAL node, asked by the roster. The sweep had a seam-asked-by-the-roster shape and
    # not this one, so when the engine's internal guard stopped keying on the signer's name and the
    # surface's copy did not, nothing here could see it: `['PASS','FAIL']` offered with `gate: None`
    # on a node the engine refuses to everyone. Third time in two days that half a mirror was
    # shipped, and the third time the instrument had no shape for the half that was left.
    "internal node, no record, asked by the roster": (
        lambda e: (_with_children(e),
                   e._graph.authorized_validators.add("val-1"),
                   T.signal(e, "a", "ACCEPT", "agent"),
                   T.signal(e, "a", "DELIVER", "agent", result="I wrote nothing at all")),
        "a", "val-1", False),
    # …the node with NO Del, which is where both role rules go falsy. `validation.py` guards each
    # role as `if <holder> and source != <holder>`, so an unassigned node accepts issuer AND
    # executor signals from anybody; the surface has to match on both halves or it tells a caller
    # they have no move on a node that moves for them. Added because the hiding test above, written
    # for exactly this defect, could not see it: no shape in this table had an unassigned node, so
    # the instrument and its subject had never met.
    "a node with no executor at all": (
        lambda e: e.assign_task(T.TaskId("root"), T._spec_from(
            {"description": "a goal nobody holds", "accepted_risks": _RISK,
             "criteria": [{"name": "g", "description": "G holds"}]}), None),
        "root", "stranger", False),
    # …a node where PASS is genuinely OPEN, which no shape provided until the drop-one control was
    # run signal by signal: dropping PASS silently left the whole sweep green, because every shape
    # that admits PASS also withholds it for a real reason, so the injected removal was invisible.
    # A sweep needs the signal available somewhere or it cannot see that signal go missing.
    "a delivered seam with its verdict on the record": (
        lambda e: (_root_only(e), _deliver_root(e),
                   T.record_verdict(e, "root", "PASS", reviewer="rev",
                                    observed={"g": "ran the check; it holds"})),
        "root", "agent", False),
    # …the healthy controls: if the sweep cannot go green on a node that really can move, it is
    # measuring its own strictness rather than the product.
    "a fresh root nobody has taken": (_root_only, "root", "agent", False),
    "a leaf taken and executing": (
        lambda e: (_root_only(e), T.signal(e, "root", "ACCEPT", "agent")),
        "root", "agent", False),
    # …and the 2026-08-21 patch the docstring credits: ASSIGN on a CONSUMED terminal, which the
    # finality gate refuses (§14.3). It had no shape here at all until the control showed the file
    # was holding two of the five cases it claimed.
    "a consumed terminal offering ASSIGN": (
        lambda e: (_root_only(e), T.signal(e, "root", "ACCEPT", "agent"),
                   T.signal(e, "root", "DELIVER", "agent", result="done"),
                   T.record_verdict(e, "root", "PASS", reviewer="rev",
                                    observed={"g": "ran the check; it holds"}),
                   T.signal(e, "root", "PASS", "agent")),
        "root", "agent", False),
}


@pytest.fixture(autouse=True)
def _gate_for(request, monkeypatch):
    """Turn the Level-2 gate on for the shapes whose subject IS that gate."""
    shape = request.node.callspec.params.get("shape") if hasattr(request.node, "callspec") else None
    if shape and SHAPES[shape][3]:
        monkeypatch.setenv("GFSO_L2_GATE", "1")


def _build(shape):
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    SHAPES[shape][0](e)
    return e


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_nothing_advertised_is_refused_by_rule(shape: str) -> None:
    _, task_id, who, _gate = SHAPES[shape]
    offered = T.available_actions(_build(shape), task_id, agent=who)
    assert "error" not in offered, offered

    for act in offered["actions"]:
        out = _send(_build(shape), task_id, act, who)
        # NOT `refused_by != "rule"` ALONE. `refused_by` is the SIGNAL door's vocabulary; `revise`,
        # which is where the ASSIGN leg goes, refuses in its own shape (`error` / `refused`) and
        # never sets that key — so the assertion was `None != "rule"` for every ASSIGN this sweep
        # offered, i.e. it asserted nothing at all on the one leg that needed a different door.
        # The subject is "was the offer real", so the test asks that in whatever words the door
        # answers in, and keeps the `rule` distinction where the door draws it.
        assert out.get("refused_by") != "rule" and not _refused(out), (
            f"{shape}: `available_actions` offered {act} on {task_id} to {who}, and the machine "
            f"refused it — {out.get('error')}. The surface and the engine disagree; the engine is "
            f"right by construction, so the gate belongs in `_gated_out`."
        )


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_a_removed_signal_is_removed_with_its_reason(shape: str) -> None:
    """The other half, and the one a reader actually acts on.

    Removing the signal silently is only half the repair: a person looking at a shortened list
    cannot tell "not yours" from "not yet" from "you must record something first", and the empty
    list was itself a measured defect (a delivered node answering `[]` while `signal` explained
    itself in full). So a shape where the gate took something out must say what and how to open it.
    """
    _, task_id, who, _gate = SHAPES[shape]
    e = _build(shape)
    offered = T.available_actions(e, task_id, agent=who)
    full = {s.name for s in e.available_actions(
        T.TaskId(task_id), None if who == "*" else T.AgentId(who))}
    if full - set(offered["actions"]):
        assert offered.get("gate"), (
            f"{shape}: the gate removed {sorted(full - set(offered['actions']))} from {task_id} "
            f"and said nothing about it. A shortened list with no reason is the silence the "
            f"`why_none` work was done for."
        )


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_an_action_whose_door_is_elsewhere_names_that_door(shape: str) -> None:
    """The half the sweep above deliberately routes around, held here instead of assumed.

    ASSIGN is listed on every reassignable node because §14.3 admits it — but its edge is taken on
    `spec is not None`, and `signal` has no `spec` parameter, so `signal <node> ASSIGN` is
    guard-refused in OFFERED, EXECUTING and VALIDATING alike (probed 2026-09-07). Keeping it listed
    is right; leaving the reader to discover that the verb they were shown cannot send it is the same
    silence the terminal case was repaired for, where ASSIGN already says `reopen` / `revise`.
    """
    _, task_id, who, _gate = SHAPES[shape]
    e = _build(shape)
    offered = T.available_actions(e, task_id, agent=who)
    if "ASSIGN" not in offered["actions"] or e.get_task(task_id).state.name in ("DONE", "ABANDONED"):
        pytest.skip("no live ASSIGN offered in this shape")
    assert "revise" in (offered.get("gate") or ""), (
        f"{shape}: ASSIGN is offered on {task_id} and nothing says `revise` is what sends it. "
        f"gate={offered.get('gate')!r}"
    )


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_nothing_the_machine_would_accept_is_hidden(shape: str) -> None:
    """The OTHER direction, which this file did not test at all until it was pointed out.

    The invariant above is offered ⟹ accepted. Its converse — accepted ⟹ offered — is the more
    dangerous failure: a caller told they have no move, on a node that would move for them, does not
    get an error to chase. They stop. Two of the defects this file was written around were exactly
    that shape (`_roles_of` granting nobody the issuer role on an unassigned node; the same for the
    executor), and both were found by a reviewer rather than by this sweep, because every shape here
    asserted only that the list was not too LONG.

    Establishing it in general would mean sending every signal on every shape and seeing which the
    machine takes — which is what the sweep above does for the offered ones. Here it is done for the
    signals the state admits but the asker's role filter dropped: for each, the machine is asked
    directly, and it must agree that the signal is not for this caller.
    """
    _, task_id, who, _gate = SHAPES[shape]
    e = _build(shape)
    _answer = T.available_actions(e, task_id, agent=who)
    offered = set(_answer["actions"])
    offered_note = _answer.get("gate")
    withheld = _answer.get("withheld") or {}
    admitted = {s.name for s in e.available_actions(T.TaskId(task_id))}   # every role's view

    for act in sorted(admitted - offered):
        out = _send(_build(shape), task_id, act, who)
        if _refused(out) or out.get("refused_by"):
            continue                                  # the machine agrees it is not for this caller
        # …AND WHERE THE MACHINE WOULD TAKE IT, THE SURFACE MAY STILL WITHHOLD IT — but only out
        # loud. DELIVER on a parent with open children is exactly that: §14.3 admits the signal, and
        # this surface stops RECOMMENDING it because taking it parks the node in VALIDATING outside
        # the frontier. That is a designed opinion, not a disagreement — and what makes it honest
        # rather than a hide is that the gate names the signal and says what to do instead. A
        # withheld signal with no sentence about it is the silent version, and indistinguishable
        # from "you have no move".
        # …and it is asked of `withheld`, NOT of the prose. The first version substring-matched
        # the joined gate note, and every note about a VALIDATING node ends by saying "FAIL is open
        # to you" — so an injected defect that silently dropped FAIL from every list left this
        # sweep entirely green (37 passed), while the same injection on CANCEL turned 7 red. The
        # instrument accepted a sentence ABOUT the signal as proof the signal had been named. Only
        # the code that removed a signal knows it removed it, so that is what is asked.
        assert act in withheld, (
            f"{shape}: {act} on {task_id} is NOT offered to {who}, the machine ACCEPTS it, and "
            f"nothing says it was withheld (withheld={sorted(withheld)}, gate={offered_note!r}). "
            f"A caller is told they have no move on a node that moves for them — and unlike an "
            f"over-offer, no refusal leads them back."
        )
