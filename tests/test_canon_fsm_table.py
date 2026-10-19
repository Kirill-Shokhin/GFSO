"""The engine's transition table against the CANON's own table, parsed from §12.4 at test time.

Why this exists. The FSM table lives in six encodings — the canon (§12.4), `gfso/core/protocol/
fsm.py`, `formal/tla/FsmTable.tla`, `formal/GFSO/Fsm.lean`, `docs/architecture.md` and the
agent-facing `gfso/mcp/ORCHESTRATOR.md` — and until now only two of them were checked against each
other mechanically (`test_model_conformance.py`: code ↔ TLA). Both could agree and both be wrong
about the canon; that is exactly what corners #3 (`VALIDATING+FAIL@max → DONE(fail)`, an edge the
canon denies) and #4 (`REWORKING+BLOCK`, an edge the canon's diagram omitted) were, and both were
found by a human reading prose. v4.0 writes the admissible sets out per state as a markdown table,
so the reading can be mechanical from here on.

Two directions, and the second is the load-bearing one:
  * every canon edge is implemented (a missing edge = a channel the protocol promises and the
    engine refuses);
  * every engine edge is in the canon (an EXTRA edge is the corner-#3 class: the engine inventing a
    transition the canon does not carry).

Out of scope, deliberately: the R′ REOPEN edge out of DONE/ABANDONED. §12.14 states it as a named
extension over the base machine, gated on a GRAPH predicate (consumption) rather than on state, so
it is not a row of this table; it is covered by `tests/test_reopen.py` and the TLA+ model.

THE ENGINE IS AHEAD OF THE CANON TEXT BY ONE AGREED DELTA (E1/E2, the theory stream, 2026-09-24),
and the canon text follows it. Until it does, the parsed table is read THROUGH that delta —
`_through_the_agreed_delta`, which states the delta's complete list — and a test pins that the
delta moves exactly those cells and nothing else. Once §12.4 carries it, the function is a no-op
(it keys on OVERDUE still being in the text) and goes.
"""
import re
from collections import deque
from pathlib import Path

import pytest

from gfso.core.protocol import fsm as F
from gfso.core.protocol.validation import Role, required_role
from gfso.core.protocol.fsm import transition
from gfso.core.types import (NON_TERMINAL_STATES, REASSIGNABLE_STATES, Criteria, GuardContext,
                             Signal, SignalData, Spec, State, TaskId)
from gfso.engine.audit import VERSION_INSTALLING

CANON = Path(__file__).resolve().parents[1] / "docs/applied_gfso_v4_en.md"
ROW = re.compile(r"^\|\s*([A-Z][A-Z ／/,]*[A-Z])\s*\|\s*(.+?)\s*\|\s*$")
#: the canon writes the system trigger in lowercase (`timeout`) to keep it apart from the SIGNAL
#: `TIMEOUT` it shares a name with; both denote the same Signal member here.
TRIGGER = "timeout"
#: the waits whose first timeout E1 hands straight to ESCALATED
E1_WAITS = ("OFFERED", "CHALLENGED", "EXECUTING", "REWORKING")


def _table_after(header: str) -> list[tuple[str, str]]:
    """(first cell, rest) of each row of the canon's markdown table under `header`."""
    lines = CANON.read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(header))
    out = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        if m := ROW.match(line):
            out.append((m.group(1), m.group(2)))
    return out


def _raw_canon_rows() -> dict[str, dict[str, set[str]]]:
    """§12.4's per-state admissible sets, BY NAME as written: {state: {signal: {targets}}}."""
    out: dict[str, dict[str, set[str]]] = {}
    for states, body in _table_after("| State | Admissible signals"):
        if "—" in body or "terminal" in body:          # the terminals row: no base-machine edges
            for s in re.split(r"\s*/\s*", states):
                out[s.strip()] = {}
            continue
        edges: dict[str, set[str]] = {}
        for part in body.split("·"):
            part = re.sub(r"\*\*|`", "", part).strip()
            sig, _, targets = part.partition("→")
            if not targets:
                continue
            sig = sig.strip()
            tset = {re.sub(r"\(.*?\)", "", t).strip() for t in re.split(r"∨", targets)}
            edges["TIMEOUT" if sig == TRIGGER else sig] = tset - {""}
        out[states.strip()] = edges
    return out


def _through_the_agreed_delta(rows: dict[str, dict[str, set[str]]]) -> dict[str, dict[str, set[str]]]:
    """E1/E2, the complete list. E1: OVERDUE removed — the first timeouts of the four waits go to
    ESCALATED. E2: REJECT_CHALLENGE returns to the wait the challenge interrupted — OFFERED or
    EXECUTING. (Re-ASSIGN in every non-terminal but IDLE and CANCELLING is already the text's.)"""
    if "OVERDUE" not in rows:
        return rows
    out = {s: {sig: set(t) for sig, t in e.items()} for s, e in rows.items() if s != "OVERDUE"}
    for s in E1_WAITS:
        out[s]["TIMEOUT"] = {"ESCALATED"}
    out["CHALLENGED"]["REJECT_CHALLENGE"] = {"OFFERED", "EXECUTING"}
    return out


def _canon_rows() -> dict[State, dict[Signal, set[State]]]:
    """§12.4's per-state admissible sets, through the agreed delta, as engine members."""
    return {State[s]: {Signal[sig]: {State[t] for t in ts} for sig, ts in e.items()}
            for s, e in _through_the_agreed_delta(_raw_canon_rows()).items()}


def _canon_owners() -> dict[State, Role]:
    """§12.13's Inv-8 owner table, parsed, less OVERDUE (the agreed delta removes the state)."""
    out = {}
    for states, body in _table_after("| State | Owner"):
        role = {"executor": Role.EXECUTOR, "issuer": Role.ISSUER}[body.split("|")[0].strip()]
        for s in re.split(r"\s*,\s*", states):
            if s != "OVERDUE":
                out[State[s]] = role
    return out


CANON_ROWS = _canon_rows()
OWNERS = _canon_owners()


_SPEC = Spec("re-issued", (Criteria("c", "d"),), name="n")
#: EVERY PAYLOAD SHAPE `transition()` BRANCHES ON, per signal — the first is the default. The table
#: is not only `_LOOKUP`: BLOCK with blockers, RESOLVE_BLOCK with blockers or `external`,
#: ACCEPT_CHALLENGE with a new spec, and ASSIGN with and without a packet are decided inline, and a
#: property enumerated over payload-free signals never looks at them. (ASSIGN carries a packet by
#: default because Inv-1 makes a revision the new contract; the bare one is ESCALATED's and REOPEN's.)
PAYLOADS = {
    Signal.ASSIGN: ({"spec": _SPEC}, {}),
    Signal.BLOCK: ({}, {"blocker_task_ids": (TaskId("p"),)}),
    Signal.RESOLVE_BLOCK: ({}, {"blocker_task_ids": (TaskId("p"),)}, {"external": True}),
    Signal.ACCEPT_CHALLENGE: ({}, {"new_spec": _SPEC}),
}


def _payloads(signal: Signal) -> tuple:
    return PAYLOADS.get(signal, ({},))


def _engine(state: State, signal: Signal, *, iteration=0, max_iterations=3, consumed=True,
            consented=False, payload=None):
    payload = _payloads(signal)[0] if payload is None else payload
    r = transition(state, SignalData(signal=signal, task_id=TaskId("t"), **payload),
                   GuardContext(iteration=iteration, max_iterations=max_iterations,
                                reopens=0, max_reopens=1, consumed=consumed, consented=consented))
    return r[0] if r else None


#: every input a row reads: both sides of the rework bound and of consent (E2) — per payload
def _sides(signal: Signal):
    return [dict(iteration=it, consented=c, payload=p)
            for it in (0, 9) for c in (False, True) for p in _payloads(signal)]


def test_the_canon_table_parsed():
    """A parser that silently reads nothing would make every assertion below vacuous."""
    assert len(CANON_ROWS) == len(State), f"parsed {len(CANON_ROWS)} of {len(State)} states"
    assert CANON_ROWS[State.IDLE] == {Signal.ASSIGN: {State.OFFERED},
                                      Signal.CANCEL: {State.CANCELLING}}
    assert CANON_ROWS[State.VALIDATING][Signal.FAIL] == {State.REWORKING, State.ESCALATED}


@pytest.mark.parametrize("state", list(State))
def test_every_canon_edge_is_implemented(state):
    for signal, targets in CANON_ROWS[state].items():
        got = {_engine(state, signal, **g) for g in _sides(signal)}   # every guard, every payload
        got.discard(None)
        assert got & targets, (f"canon §12.4 admits {state.name} --{signal.name}--> "
                               f"{{{', '.join(t.name for t in targets)}}}; the engine gives "
                               f"{{{', '.join(t.name for t in got) or 'nothing'}}}")


@pytest.mark.parametrize("state", list(State))
def test_the_engine_invents_no_edge_the_canon_denies(state):
    """The corner-#3 direction: an edge the canon does not carry is a category the engine made up."""
    for signal in Signal:
        for g in _sides(signal):
            target = _engine(state, signal, **g)
            if target is None:
                continue
            if state in (State.DONE, State.ABANDONED) and signal is Signal.ASSIGN:
                continue                        # R′ REOPEN — a named extension, not a base row
            admitted = CANON_ROWS[state].get(signal, set())
            assert target in admitted, (
                f"the engine takes {state.name} --{signal.name}--> {target.name}, which §12.4 does "
                f"not admit (it admits {{{', '.join(t.name for t in admitted) or 'nothing'}}})")


def test_the_terminals_stay_terminal():
    """Two states, and only two: terminal means the WORK IS OVER (accepted, or refused by authority).

    ESCALATED is not among them — it is the issuer's waiting state (§12.5), with a row of its own
    in the canon's table, and `test_every_canon_edge_is_implemented` checks that row like any other."""
    for state in (State.DONE, State.ABANDONED):
        assert CANON_ROWS[state] == {}
        for signal in Signal:
            if state in (State.DONE, State.ABANDONED) and signal is Signal.ASSIGN:
                continue                        # R′ again
            assert _engine(state, signal) is None


# ── the guard's own negative controls ────────────────────────────────────────────────────────────
# A guard is not working until it has gone RED on a planted defect of each class it claims to catch.
# These plant the two classes in-process (the parsed canon on one side, the engine on the other) and
# assert the checks above fail — so a refactor that quietly defuses them fails here first.

def test_control_a_missing_engine_edge_is_caught(monkeypatch):
    monkeypatch.setitem(CANON_ROWS, State.BLOCKED,
                        {**CANON_ROWS[State.BLOCKED], Signal.DELIVER: {State.VALIDATING}})
    with pytest.raises(AssertionError, match="the engine gives"):
        test_every_canon_edge_is_implemented(State.BLOCKED)


def test_control_b_an_invented_engine_edge_is_caught(monkeypatch):
    import tests.test_canon_fsm_table as mod   # itself, by name — never the import block
    monkeypatch.setattr(mod, "_engine",
                        lambda state, signal, **kw: State.DONE
                        if (state is State.BLOCKED and signal is Signal.PASS) else None)
    with pytest.raises(AssertionError, match="does not admit"):
        test_the_engine_invents_no_edge_the_canon_denies(State.BLOCKED)


def test_control_c_a_silent_parser_is_caught(monkeypatch):
    """The vacuity control: if §12.4 is reformatted and the parser reads nothing, everything above
    passes trivially. That is the failure mode this project has hit repeatedly (a falsely green
    guard), so the parse itself is asserted."""
    import tests.test_canon_fsm_table as mod   # itself, by name — never the import block

    class _Empty:                     # a canon whose table header survives but whose rows do not
        def read_text(self, **kw):
            return "| State | Admissible signals (→ target) |\n|---|---|\n"

    monkeypatch.setattr(mod, "CANON", _Empty())
    assert _canon_rows() == {}, "a table with no rows must parse to nothing…"
    monkeypatch.setattr(mod, "CANON_ROWS", _canon_rows())
    with pytest.raises(AssertionError):        # …and the vacuity assertion must then fail
        test_the_canon_table_parsed()


# ---------------------------------------------------------------------------------------------
# Three properties of the TABLE AS A WHOLE, agreed with the theory stream (2026-09-23).
#
# They are engine-side by construction: `formal/GFSO/Forcing.lean` states them over the CANON's
# table (`canonStep`), and the canon↔mirror agreement is a Lean fact about `Fsm.lean`. Nothing in
# Lean reaches `_LOOKUP`, so the only thing that holds these against drift where drift happens —
# a row edited here — is a test here. Each holds today; each is written so that it would not.
# ---------------------------------------------------------------------------------------------

def _destinations():
    """Every (state, signal) -> destination the engine's own table actually takes, every guard side
    and every payload shape."""
    for state in State:
        for signal in Signal:
            for g in _sides(signal):
                target = _engine(state, signal, **g)
                if target is not None:
                    yield state, signal, target


def test_the_delta_moves_exactly_its_own_cells():
    """"Nothing else in the table moves" (E1/E2), as a check rather than a promise: the parsed canon
    and the canon read through the delta differ in the listed cells and in no other."""
    raw, now = _raw_canon_rows(), _through_the_agreed_delta(_raw_canon_rows())
    if "OVERDUE" not in raw:
        assert raw == now
        return
    moved = {(s, sig) for s in raw if s != "OVERDUE"
             for sig in set(raw[s]) | set(now[s]) if raw[s].get(sig) != now[s].get(sig)}
    assert moved == {(s, "TIMEOUT") for s in E1_WAITS} | {("CHALLENGED", "REJECT_CHALLENGE")}
    assert set(raw) - set(now) == {"OVERDUE"} and set(now) <= set(raw)


def test_no_transition_lands_in_idle():
    """Inv-8 read on the EDGES (§12.13's second clause, v4.1).

    Stated per STATE, Inv-8 is satisfied VACUOUSLY by a machine that routes a live node to IDLE:
    IDLE has no owner, nothing having been issued, and by Inv-5's own exemption no clock — so the
    node rests there with neither party owing anything and no wait that ends. That is v4.0's empty
    ESCALATED defect at the one state the per-state clause cannot see.
    """
    landing = [(s.name, sig.name) for s, sig, t in _destinations() if t is State.IDLE]
    assert not landing, (
        f"these rows take a live node back to IDLE, which owes nobody anything and never times "
        f"out (Inv-8 on the edges, §12.13): {landing}")


def test_c1_the_states_that_report_are_entered_only_by_their_own_report():
    """C1 — entry-exclusivity, so the CLOCK may not deliver, dispute, block or accept in a party's
    place (§13.4). A validation state means "a delivery is on the table", a dispute state "the
    executor raised one", a blocked state "he reported a blocker", DONE "the issuer passed it" — so
    each is entered only by that party's own signal; and ABANDONED only out of CANCELLING, the
    handshake in which the executor is told his contract ended.

    The catch-alls are not exceptions: CANCEL goes to CANCELLING and ASSIGN to OFFERED."""
    owed = {State.VALIDATING: Signal.DELIVER, State.CHALLENGED: Signal.CHALLENGE,
            State.BLOCKED: Signal.BLOCK, State.DONE: Signal.PASS}
    wrong = [(s.name, sig.name, t.name) for s, sig, t in _destinations()
             if (t in owed and sig is not owed[t])
             or (t is State.ABANDONED and s is not State.CANCELLING)]
    assert not wrong, (
        f"these rows enter a state that reports a party's own act by some other signal, or settle "
        f"ABANDONED outside the cancellation handshake (C1, §13.4): {wrong}")


def test_c2_besides_the_clock_a_state_moves_only_by_its_owner():
    """C2 — Inv-8's owner is the party whose signals move the state. Apart from the timeout, the
    only moves of a state are its owner's own signals and the two catch-alls (re-ASSIGN, CANCEL).
    The owner table is §12.13's, parsed, less OVERDUE."""
    assert set(OWNERS) == NON_TERMINAL_STATES - {State.IDLE}, (
        f"the owner table must name every live state but IDLE: {sorted(s.name for s in OWNERS)}")
    wrong = [(s.name, sig.name) for s, sig, t in _destinations()
             if sig not in (Signal.TIMEOUT, Signal.ASSIGN, Signal.CANCEL)
             and OWNERS.get(s) is not required_role(sig)]
    assert not wrong, (
        f"these rows move a state on a signal that is not its owner's (C2, Inv-8): {wrong}")


def _consent_walk():
    """Every (state, consented) the engine's table reaches from IDLE, and every edge that enters
    EXECUTING/BLOCKED/VALIDATING with no ACCEPT of the current version behind it.

    Consent is a fact about the path, which a per-cell check cannot see: an ACCEPT sets it, and a
    version-installing signal (ASSIGN in every form, ACCEPT_CHALLENGE) clears it — the rule the
    engine reads off its log (`engine.audit`). The walk feeds that bit into the guard."""
    start = (State.IDLE, False)
    seen, todo, unconsented = {start}, deque([start]), []
    while todo:
        state, ok = todo.popleft()
        for signal in Signal:
            for g in _sides(signal):
                t = _engine(state, signal, iteration=g["iteration"], consumed=False, consented=ok,
                            payload=g["payload"])
                if t is None:
                    continue
                now = False if signal in VERSION_INSTALLING else (ok or signal is Signal.ACCEPT)
                if t in (State.EXECUTING, State.BLOCKED, State.VALIDATING) and not now:
                    unconsented.append((state.name, signal.name, t.name))
                if (t, now) not in seen:
                    seen.add((t, now))
                    todo.append((t, now))
    return seen, unconsented


def test_c3_no_work_without_consent_to_the_current_version():
    """C3 — no transition into EXECUTING, BLOCKED or VALIDATING without an ACCEPT logged on the
    current packet version. v4.1 disclosed the one path that broke it — REJECT_CHALLENGE out of a
    CHALLENGED entered from OFFERED put the executor to work on terms he never accepted — and E2
    closes it by returning such a node to OFFERED."""
    seen, unconsented = _consent_walk()
    reached = {s for s, _ in seen}
    assert reached == set(State), (                    # the walk reaches every state: not vacuous
        f"unreached: {sorted(s.name for s in set(State) - reached)}")
    assert not unconsented, (
        f"these paths put the node to work with no ACCEPT of the current version (C3): "
        f"{sorted(set(unconsented))}")


def test_c4_the_clock_hands_over_and_never_resumes():
    """C4 — what a timeout may do. It may not return a state to itself (every bound fires and no
    wait ends — Φ1 defeated as written); it may not land in a state whose meaning is a party's act
    or a party's wait on the other (OFFERED, EXECUTING, CHALLENGED, BLOCKED, VALIDATING — the clock
    would be issuing, consenting, disputing, blocking or delivering); and only ESCALATED's timeout
    enters CANCELLING, the issuer's silence being the one silence that is a cancellation."""
    forbidden = {State.OFFERED, State.EXECUTING, State.CHALLENGED, State.BLOCKED, State.VALIDATING}
    wrong = [(s.name, t.name) for s, sig, t in _destinations() if sig is Signal.TIMEOUT
             and (t is s or t in forbidden
                  or (t is State.CANCELLING and s is not State.ESCALATED))]
    assert not wrong, f"these timeouts break C4: {wrong}"


def test_re_assign_is_admitted_in_every_live_state_but_idle_and_cancelling():
    """E1's third line. IDLE has no packet to revise (its ASSIGN is the first) and CANCELLING's one
    staffed exit is CONFIRM_CANCEL; everywhere else the issuer may revise."""
    assert REASSIGNABLE_STATES == NON_TERMINAL_STATES - {State.IDLE, State.CANCELLING}
    for s in REASSIGNABLE_STATES:
        assert _engine(s, Signal.ASSIGN) is State.OFFERED, s
    assert _engine(State.CANCELLING, Signal.ASSIGN) is None


# ── the controls: each property flipped by ONE cell of a copy of the table ──────────────────────
# A property test that cannot fail is a green light for nothing — which this project has met more
# than once (a mutation that missed the code under test; a backstop whose whole suite passed with
# the backstop deleted). Each control plants one cell and asserts its property goes red.

def _flip(monkeypatch, state, signal, dest):
    monkeypatch.setitem(F._LOOKUP, (state, signal), lambda tid, ctx: (dest, []))


@pytest.mark.parametrize("check,cell", [
    (test_no_transition_lands_in_idle, (State.ESCALATED, Signal.TIMEOUT, State.IDLE)),
    # C1: the clock delivering, the clock passing, a settlement outside the handshake
    (test_c1_the_states_that_report_are_entered_only_by_their_own_report,
     (State.EXECUTING, Signal.TIMEOUT, State.VALIDATING)),
    (test_c1_the_states_that_report_are_entered_only_by_their_own_report,
     (State.VALIDATING, Signal.TIMEOUT, State.DONE)),
    (test_c1_the_states_that_report_are_entered_only_by_their_own_report,
     (State.ESCALATED, Signal.TIMEOUT, State.ABANDONED)),
    # C2: the executor moving a state the issuer owns (entering BLOCKED by BLOCK keeps C1 green)
    (test_c2_besides_the_clock_a_state_moves_only_by_its_owner,
     (State.VALIDATING, Signal.BLOCK, State.BLOCKED)),
    # C3: v4.1's REJECT_CHALLENGE — EXECUTING whatever the consent
    (test_c3_no_work_without_consent_to_the_current_version,
     (State.CHALLENGED, Signal.REJECT_CHALLENGE, State.EXECUTING)),
    # C4: a self-loop, the old auto-accept of a dispute, a cancellation by a clock not the issuer's
    (test_c4_the_clock_hands_over_and_never_resumes, (State.ESCALATED, Signal.TIMEOUT, State.ESCALATED)),
    (test_c4_the_clock_hands_over_and_never_resumes, (State.CHALLENGED, Signal.TIMEOUT, State.OFFERED)),
    (test_c4_the_clock_hands_over_and_never_resumes, (State.BLOCKED, Signal.TIMEOUT, State.CANCELLING)),
])
def test_control_each_property_catches_its_own_violation(monkeypatch, check, cell):
    check()                                      # green on the engine's own table…
    _flip(monkeypatch, *cell)
    with pytest.raises(AssertionError):          # …red with one cell flipped
        check()


@pytest.mark.parametrize("check", [test_c1_the_states_that_report_are_entered_only_by_their_own_report,
                                   test_c2_besides_the_clock_a_state_moves_only_by_its_owner,
                                   test_c3_no_work_without_consent_to_the_current_version,
                                   test_c4_the_clock_hands_over_and_never_resumes])
def test_control_an_inline_branch_is_inside_the_properties(monkeypatch, check):
    """The payload branches are table cells too. Widen BLOCK-with-blockers to OFFERED — a cell no
    `_LOOKUP` flip can reach — and C3 goes red (work entered with no ACCEPT). The others are named so
    that which properties see the planted cell is on the record, not assumed."""
    check()
    monkeypatch.setattr(F, "_BLOCKABLE", F._BLOCKABLE + (State.OFFERED,))
    if check is test_c3_no_work_without_consent_to_the_current_version:
        with pytest.raises(AssertionError):
            check()
    else:
        check()          # BLOCK enters BLOCKED, by the executor, owner of OFFERED: C1/C2/C4 hold


def test_a_packet_version_is_entered_only_by_an_issuer_act():
    """Φ2 (§12.15): a packet version enters only through the offer state, and only by his act.

    Keyed to the SENDER'S ROLE, never to signal names. The natural reading of the prose hard-codes
    ASSIGN and ACCEPT_CHALLENGE and thereby forbids RESOLVE_BLOCK → OFFERED, which §13.2 names
    as a FREE choice — the resume-vs-re-consent decoration — so a name-keyed test would gate a
    conformant machine. What the canon actually requires is that no EXECUTOR act, and no clock,
    mint a new version of the contract in the issuer's place. (E2's REJECT_CHALLENGE → OFFERED is
    the issuer's act and mints nothing: the version it returns to is the one standing.)
    """
    minted = [(s.name, sig.name) for s, sig, t in _destinations()
              if t is State.OFFERED and required_role(sig) is not Role.ISSUER]
    assert not minted, (
        f"these rows put the node into OFFERED — a new packet version — on a signal that is not "
        f"the issuer's (Φ2, §12.15): {minted}")


def test_control_an_executor_minting_a_version_is_caught(monkeypatch):
    """The control: DELIVER is the executor's, so a row taking it to OFFERED must go red."""
    _flip(monkeypatch, State.EXECUTING, Signal.DELIVER, State.OFFERED)
    with pytest.raises(AssertionError):
        test_a_packet_version_is_entered_only_by_an_issuer_act()
