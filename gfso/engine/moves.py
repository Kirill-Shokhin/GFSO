"""A move as the door takes it — a verb on a node, keyed by the role the door reads there — and who the project's mode
gives it to. ONE table: the doors lock by it (`tools_llm._mode_lock`), the lists read it (`available_actions`, the
frontier's `mine`), and every sentence that offers a move is built from it (`Engine.offer`), so no surface can name a
move without the door's own key for it. Prose that named moves by hand read the lock one sentence at a time and
offered the customer refused moves three times over (critics over 9853468 and 25faf94)."""
from __future__ import annotations

from typing import NamedTuple, Optional

from gfso.core.protocol.validation import SIGNAL_ROLES, Role
from gfso.core.types import AgentId, TaskId

#: the executor's signals, read off the one table of who sends what (§11.2) — a hand copy was the second list (D-F18)
EXECUTOR_SIGNALS = frozenset(s.name for s, r in SIGNAL_ROLES.items() if r is Role.EXECUTOR)
#: a ruling on a CHALLENGE — the user's own where it rules a finding out of his goal (`Engine.users_dispute`)
RULINGS = frozenset({"ACCEPT_CHALLENGE", "REJECT_CHALLENGE"})

# WHO MAY MOVE WHAT UNDER A MODE. Each verb names the node its move is about and whose move it is there: the ISSUER's
# (the node's contract, its verdict, its Del) or the SPLIT's (the node's decomposition — its executor's act, §11.5).
DOOR_KEYS = {
    "edit_criteria": ("task_id", "issuer"), "revise": ("task_id", "issuer"),
    "reassign": ("task_id", "issuer"), "reopen": ("task_id", "issuer"),
    "record_verdict": ("task_id", "issuer"),
    "map_criterion": ("parent_id", "split"), "dispute_finding": ("task_id", "split"),
    # the split's register where its Del writes over a split, else the packet's pre-fill — the issuer's (§9.2, §10.1)
    "edit_accepted_risks": ("task_id", "risks"), "create_task": ("parent_id", "split"),
    "decompose": ("parent_id", "split"), "auto_decompose": ("root_id", "split"),
    "signal": ("task_id", "signal"),
    "validate_result": ("task_id", "issuer"), "edit_scope": ("task_id", "issuer"),
    "require_check": ("task_id", "issuer"),
    "review_decomposition": ("task_id", "split"),
    "add_dependency": ("to_id", "issuer"), "remove_dependency": ("to_id", "issuer"),
    # the roster names no node: under AUTO re-staffing the validator is a move on the work, below it is free
    "register_agent": (None, None), "unregister_agent": (None, None),
}


class Move(NamedTuple):
    """`verb` on `node` (`signal` for a signal) and the words that offer it to whoever may make it. `unmade`: where the
    mode locks it nothing in the system makes it either — a settled node's way back, which no question asks."""
    verb: str
    node: Optional[str]
    say: str
    signal: Optional[str] = None
    unmade: bool = False


def signal_role(sig: str) -> str:
    """The role the door keys a signal by: the split's for the executor's signals, else the issuer's."""
    return "split" if str(sig).upper() in EXECUTOR_SIGNALS else "issuer"


#: the argument a structural move is signed by at a door — the name the MCP door pins to its connection
SIGNER = "agent"
#: …where a verb signs by another argument, the one the doors pin for it: a split the system authors names its author
SIGNED_BY = {"auto_decompose": "author"}


def signer_arg(verb: str) -> str:
    """The argument `verb` is signed by at a door."""
    return SIGNED_BY.get(verb, SIGNER)


#: EVERY VERB'S SIGNER ARGUMENTS, the one table every door reads: the name a move is signed by is the call's credential's,
#: never the caller's word (docs/notes/SIGN_IN.md). The MCP door drops them from its schema; at every door a name the
#: credential may not sign as is refused, and an omitted one is its default (`tools_llm._signed`). A verb's READ of
#: "whose view" (`next_step(s).actor`, `available_actions.agent`) signs nothing and is not here.
SIGNERS = {"signal": ("source",), "record_verdict": ("reviewer",), "stop_project": ("by",), "start_project": ("by",),
           "tech_report": ("actor",), **{v: (a,) for v, a in SIGNED_BY.items()},
           **{v: (SIGNER,) for v in ("revise", "edit_accepted_risks", "edit_criteria", "set_mode", "reopen",
                                     "rule_unrun_finding", "return_finding", "decompose", "reassign", "map_criterion",
                                     "add_dependency", "remove_dependency", "dispute_finding", "create_task",
                                     "edit_scope", "require_check")}}

#: the verbs that change nothing a party answers for — the rest are moves, refused to a call no credential signs
#: verbs that write nothing and make no project — what a call no credential names may still call. `probe_inputs` is
#: not one: it lays the pinned inputs down as files (a hand validator's preparation, signed like any check)
READS = frozenset({"get_task", "project", "get_checks", "get_graph", "list_holes", "get_review", "get_verdict",
                   "available_actions", "get_dependencies", "metrics", "usage", "claim_drift",
                   "next_step", "next_steps", "tech_reports", "list_agents", "canon"})


#: checks, not moves: anyone may run a check on a delivery (§10.2) — the signature is the issuer's signal
CHECKS = frozenset({"validate_result", "review_decomposition", "record_verdict"})


def door_role(engine, verb: str, node, signal: Optional[str] = None) -> Optional[str]:
    """The role `verb` on `node` is keyed by at the door — "issuer" or "split" — or None where it names no node."""
    side = DOOR_KEYS[verb][1]
    if side == "signal":
        return signal_role(str(signal or "").upper())
    if side == "risks":
        # a machine Del's own moves are in-process, never through a door: here the caller writes as the issuer (the
        # packet's pre-fill) wherever the Del is a machine, and as the split's decomposer otherwise
        t = engine.graph.get_task(TaskId(node)) if node else None
        return None if t is None else "issuer" if AgentId(t.assignee) in engine.workforce.executor_pool() else "split"
    return side


def door_holder(engine, verb: str, node, signal: Optional[str] = None) -> Optional[str]:
    """Who the mode gives `verb` on `node` to, where the door refuses it from anyone else — None: the door takes it."""
    if verb not in DOOR_KEYS or engine.mode() is None or (verb == "auto_decompose" and not engine.all_tasks()):
        return None                              # stating the goal is the customer's one act
    if DOOR_KEYS[verb][0] is None and engine.nothing_left():
        return None                              # the roster outlives a goal that ended: its roles are anyone's to free
    role = door_role(engine, verb, node, signal)
    return engine.mode_holder(node, role, ruling=verb == "signal" and str(signal or "").upper() in RULINGS)


def signer_due(engine, verb: str, node) -> Optional[str]:
    """Who alone may sign `verb` on `node` at a door: the holder of the role the verb is keyed by — the node's issuer
    for its contract, its Del for its split (§10.1, Inv-8: a state moves only by its owner's moves) — or None where the
    verb is a check, a signal (its `source` is checked by the engine) or names no node that stands."""
    if verb not in DOOR_KEYS or verb in CHECKS or DOOR_KEYS[verb][1] in (None, "signal"):
        return None
    return role_holder(engine, verb, node)


def role_holder(engine, verb: str, node, signal: Optional[str] = None) -> Optional[str]:
    """Who holds the role `verb` on `node` is keyed by — the node's issuer, or its Del for a split — or None where the
    verb names no node that stands. A page session's omitted signer defaults to it where the person owns the name."""
    t = engine.graph.get_task(TaskId(node)) if engine is not None and node else None
    if t is None or (role := door_role(engine, verb, node, signal)) is None:
        return None
    return str(engine.graph.issuer_of(t.id) if role == "issuer" else t.assignee or "") or None
