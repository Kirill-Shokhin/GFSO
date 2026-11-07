"""No sentence a surface hands the asker names a move the door refuses him, and every move the door takes from him is
offered: over each mode (none, solo, semi at boundary 1 and 2, auto) and each state a surface explains (a delivery over
a failed part or grandchild, a stuck graph, an escalated root or part, a root closed on a FAIL or abandoned, a producer
being joined, a parked execution, the user's own dispute), every text field of `next_steps` and `available_actions`
is read for the moves it names, and each is put to the door itself (`tools_llm._mode_lock`, dry).

Found sentence by sentence three times over (critics over 9853468 and 25faf94): the lists read the lock, the prose
around them did not, and each fix reached only the sentences its probe printed. The sweep is the rule, not the probes.

What is not read: the tail of a step's directive after "contract was:" — the contract of a step the directive has just
said is NOT YOURS, shown as information. A move a sentence names without its node is put to the door on the node the
field is about (the step's, the wait's, the asked node; the root for the frontier's directive).

CONTROL: let `Engine.offer` ignore the lock and the auto and semi cases go red.
"""
from __future__ import annotations

import inspect
import re

import pytest

import gfso.tools as T
import gfso.tools_llm as TL
from gfso.core.types import AgentId, DoneReason, Mode, Signal, State, TaskId
from tests.support import criterion
from tests.test_a_ruling_is_part_of_the_acceptance import _challenged_with_a_finding
from tests.test_the_mode_decides_who_holds_what import _RISK, _admit, _engine, _kid

ME = "agent"
_SIGNALS = set(Signal.__members__)
_NODE_PARAMS = ("task_id", "parent_id", "root_id", "to_id")


def _call(verb: str, args: str) -> dict:
    """A call as a sentence writes it — `verb('a', x=…, parent_id='p')` — as the door's keyword arguments."""
    names = [p for p in inspect.signature(TL._RAW_TOOLS[verb]).parameters if p != "engine"]
    kw = {}
    for i, a in enumerate(x.strip() for x in args.split(",")):
        if m := re.fullmatch(r"(\w+)='([^']*)'", a):
            kw[m[1]] = m[2]
        elif (m := re.fullmatch(r"'([^']*)'", a)) and i < len(names):
            kw[names[i]] = m[1]
    return kw


#: the patterns a sentence names a move by → (verb, the door's keyword arguments as far as the sentence says them)
_PATTERNS = (
    (re.compile(r"`(\w+)\(([^)`]*)"), lambda m: (m[1], _call(m[1], m[2])) if m[1] in TL._RAW_TOOLS else None),
    (re.compile(r"`(\w+)`(?!\()"), lambda m: (m[1], {}) if m[1] in TL._RAW_TOOLS else None),
    (re.compile(r"\b([A-Z_]{4,})\('([^']+)'\)"), lambda m: ("signal", {"task_id": m[2], "signal": m[1]})),
    (re.compile(r"\b([A-Z_]{4,}) (?:the|it|this)\b"),
     lambda m: ("signal", {"signal": m[1]}) if m[1] in _SIGNALS else (m[1].lower(), {})),
    (re.compile(r"\brevise the parent\b"), lambda m: ("revise", {"task_id": "^"})),
    # …and the prose forms a sentence also names moves in (critic over ad1dfb5: "re-decompose" passed unread)
    (re.compile(r"\bre-?(?:decompose|split)\b(?: '([^']+)')?"),
     lambda m: ("decompose", {"parent_id": m[1]} if m[1] else {})),
    (re.compile(r"\bsignal ([A-Z_]{4,})\b"), lambda m: ("signal", {"signal": m[1]})),
)


def _named(text: str, node: str, e) -> set:
    """Every move `text` names, its node defaulted to the one the field is about."""
    out = set()
    for rx, f in _PATTERNS:
        for m in rx.finditer(text):
            got = f(m)
            if not got or got[0] not in TL._RAW_TOOLS or got[0] == "signal" and got[1].get("signal") not in _SIGNALS:
                continue
            verb, kw = got
            if kw.get("task_id") == "^":
                p = e.graph.get_parent(TaskId(node))
                kw["task_id"] = str(p.id) if p is not None else node
            out.add((verb, tuple(sorted(kw.items()))))
    return out


def _door_takes(e, verb, kw: dict, node: str) -> bool:
    """The door's own answer from the asker, dry: its lock in front of a stub with the verb's own signature, called as
    the sentence names the move (a node it leaves unsaid is the field's)."""
    sig = inspect.signature(TL._RAW_TOOLS[verb])
    call = {p: None for p, d in sig.parameters.items() if d.default is inspect.Parameter.empty}
    call.update({p: node for p in _NODE_PARAMS if p in sig.parameters}, engine=e, **kw)
    if verb == "signal":
        call["source"] = ME
    stub = lambda *a, **k: {"ok": True}
    stub.__signature__ = sig
    try:
        TL._mode_lock(verb, stub)(**call)
        return True
    except ValueError:
        return False


def _texts(e):
    """(text, the node it is about) for every text field of the asker's two surfaces, and the /actions answers."""
    out = T.next_steps(e, actor=ME)
    yield out.get("directive"), "root"
    for s in out.get("steps") or []:
        yield (s.get("directive") or "").split("contract was:")[0], s["task_id"]
    for k in ("stranded", "waiting", "in_flight"):
        for w in out.get(k) or []:
            yield w.get("opens_with"), w["task_id"]
            yield w.get("why"), w["task_id"]
    for t in e.all_tasks():
        aa = T.TOOLS["available_actions"](e, str(t.id), ME)
        for k in ("recovery", "why_none", "gate"):
            yield aa.get(k), str(t.id)


def _set(e, tid, state, reason=None):
    t = e._graph.get_task(TaskId(tid))
    t.state, t.done_reason = state, reason
    e._graph.save_task(t)


def _goal(e):
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds"), criterion("h", "H holds")]})
    e.wait_idle()
    _admit(e, "root", _kid("a", ["g"], criterion("a1", "A holds")), _kid("b", ["h"], criterion("b1", "B holds")))
    T.TOOLS["decompose"](e, "a", [_kid("a.x", ["a1"], criterion("x1", "X holds")), _kid("a.z", ["a1"], criterion("z1", "Z holds"))],
                         accepted_risks=_RISK)
    e.wait_idle()
    assert {str(t.id) for t in e.all_tasks()} >= {"root", "a", "b", "a.x", "a.z"}


def _states(e, **st):
    for tid, s in st.items():
        _set(e, tid.replace("_", "."), *(s if isinstance(s, tuple) else (s,)))
    e.wait_idle()


X, V, D, ESC, AB = State.EXECUTING, State.VALIDATING, State.DONE, State.ESCALATED, State.ABANDONED
PASS, FAIL = (D, DoneReason.PASS), (D, DoneReason.FAIL)
SCENES = {
    "delivered over a failed part": lambda e: _states(e, root=V, a=FAIL, b=X),
    "delivered part over a failed grandchild": lambda e: _states(e, root=X, b=PASS, a=V, a_x=FAIL, a_z=PASS),
    "stuck on a settled grandchild": lambda e: _states(e, root=X, a=X, a_x=FAIL, a_z=X, b=X),
    "escalated root": lambda e: _states(e, root=(ESC, DoneReason.FAIL)),
    "escalated part": lambda e: _states(e, root=X, a=(ESC, DoneReason.FAIL), b=X),
    "root closed on a FAIL": lambda e: _states(e, root=FAIL),
    "root abandoned": lambda e: _states(e, root=AB),
    "producer being joined": lambda e: (T.TOOLS["add_dependency"](e, "b", "a"), _states(e, root=X, b=PASS, a=State.OFFERED),
                                        e.joins.mark_joining("b", True)),
    "parked execution": lambda e: (_states(e, root=X, a=X, a_x=X, a_z=X, b=X), e.parking.park_execution(TaskId("b"))),
    "the user's own dispute": lambda e: (_states(e, root=State.OFFERED), _challenged_with_a_finding(e, "root", "g")),
}
MODES = {"none": (None, None), "solo": (Mode.SOLO, None), "semi1": (Mode.SEMI, None), "semi2": (Mode.SEMI, 2),
         "auto": (Mode.AUTO, None)}


@pytest.fixture(autouse=True)
def _no_l2(monkeypatch):
    monkeypatch.setenv("GFSO_L2_GATE", "0")


@pytest.mark.parametrize("scene", SCENES)
@pytest.mark.parametrize("mode", MODES)
def test_every_move_a_surface_names_is_one_the_door_takes(mode, scene):
    e = _engine(*MODES[mode])
    try:
        _goal(e)
        SCENES[scene](e)
        e.wait_idle()
        refused = sorted({(m, node, text[:200]) for text, node in _texts(e) if text
                          for m in _named(text, node, e) if not _door_takes(e, m[0], dict(m[1]), node)})
        assert not refused, refused
        for t in e.all_tasks():
            n = str(t.id)
            aa = T.TOOLS["available_actions"](e, n, ME)
            if "waiting_on" in aa:
                assert aa["waiting_on"] == (e.mode_holder(n, "issuer") or "issuer"), (n, aa)
            # …and the reverse: what the machine and the door both take from the asker is offered, or withheld for a
            # reason that is not the mode
            fsm = [s.name for s in e.available_actions(TaskId(n), AgentId(ME))]
            takes = [a for a in fsm if _door_takes(e, "signal", {"signal": a}, n)
                     and ((r := e.refusal_for(TaskId(n), Signal[a], AgentId(ME))) is None or r.kind == "role")]
            missing = [a for a in takes if a not in aa["actions"] and "project's mode" in (aa.get("withheld") or {}).get(a, "project's mode")]
            assert not missing, (n, missing, aa)
    finally:
        e.stop()
