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
    "review_decomposition": ("task_id", "split"),
    "add_dependency": ("to_id", "issuer"), "remove_dependency": ("to_id", "issuer"),
    # the roster names no node: under AUTO re-staffing the validator is a move on the work, below it is free
    "register_agent": (None, None), "unregister_agent": (None, None),
}


class Move(NamedTuple):
    """`verb` on `node` (`signal` for a signal) and the words that offer it to whoever may make it."""
    verb: str
    node: Optional[str]
    say: str
    signal: Optional[str] = None


def signal_role(sig: str) -> str:
    """The role the door keys a signal by: the split's for the executor's signals, else the issuer's."""
    return "split" if str(sig).upper() in EXECUTOR_SIGNALS else "issuer"


def door_holder(engine, verb: str, node, signal: Optional[str] = None) -> Optional[str]:
    """Who the mode gives `verb` on `node` to, where the door refuses it from anyone else — None: the door takes it."""
    if verb not in DOOR_KEYS or engine.mode() is None or (verb == "auto_decompose" and not engine.all_tasks()):
        return None                              # stating the goal is the customer's one act
    side, sig = DOOR_KEYS[verb][1], str(signal or "").upper()
    if side == "signal":
        role = signal_role(sig)
    elif side == "risks":
        # a machine Del's own moves are in-process, never through a door: here the caller writes as the issuer (the
        # packet's pre-fill) wherever the Del is a machine, and as the split's decomposer otherwise
        t = engine.graph.get_task(TaskId(node)) if node else None
        role = None if t is None else "issuer" if AgentId(t.assignee) in engine.workforce.executor_pool() else "split"
    else:
        role = side
    return engine.mode_holder(node, role, ruling=verb == "signal" and sig in RULINGS)
