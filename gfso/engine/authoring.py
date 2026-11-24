"""The subtrees an authoring writes now: one writer each, held from the call that asked for it to the end of its writing,
wherever that runs, and nothing else moves there meanwhile — a scope session started on round 1's nodes while round 2
rebuilt them (GB_coreutils_tn5lhw152, 2026-10-19), and the machine issuer answered the plan question on a root the
authoring was still converging on the gate: two writers on one split, the authoring died (gb-coreutils-tnq7tv040,
2026-10-30)."""
from __future__ import annotations

import contextlib
import contextvars
import threading
from typing import Optional

from gfso.core.graph import Graph
from gfso.core.types import TaskId, Wait


#: the nodes whose subtree this context writes: it reads its own subtree unheld — the go's answer read its own step
_MINE = contextvars.ContextVar("gfso_authoring_mine", default=frozenset())


class Authorings:
    """{node: handle} of the authorings writing in one engine's graph; a handle names one written past its call."""

    def __init__(self, graph: Graph):
        self._graph, self._lock, self._held = graph, threading.Lock(), {}

    def lineage(self, node) -> list:
        """`node` and every node above it, nearest first."""
        out, t = [str(node)], self._graph.get_task(TaskId(str(node)))
        while t is not None and t.parent_id:
            out.append(str(t.parent_id))
            t = self._graph.get_task(t.parent_id)
        return out

    def _over(self, node, above: bool) -> Optional[tuple]:
        """`over`, under the lock."""
        mine = self.lineage(node)
        return next(((n, h) for n, h in self._held.items() if n in mine or above and str(node) in self.lineage(n)), None)

    def over(self, node, above: bool = False) -> Optional[tuple]:
        """(node, handle) of the authoring writing `node` or a node above it — and, `above`, one below it —, or None;
        never this context's own."""
        with self._lock:
            return None if (w := self._over(node, above)) is None or w[0] in _MINE.get() else w

    @staticmethod
    def mine(node) -> bool:
        """Does this context write `node`'s subtree (`writing`)?"""
        return str(node) in _MINE.get()

    @contextlib.contextmanager
    def writing(self, node):
        """This context writes `node`'s subtree, claimed for it (`take`), and lets it go at its end."""
        token = _MINE.set(_MINE.get() | {str(node)})
        try:
            yield
        finally:
            _MINE.reset(token)
            self.let_go(node)

    def held(self) -> dict:
        """{node: handle} of the authorings writing now."""
        with self._lock:
            return dict(self._held)

    def take(self, node, handle: Optional[str] = None) -> Optional[tuple]:
        """Claim `node`'s subtree for one authoring: None where it is taken, else the authoring on it, above or below."""
        with self._lock:
            if (other := self._over(node, True)) is None:
                self._held[str(node)] = handle
            return other

    def let_go(self, node) -> None:
        """The authoring of `node` has ended: its subtree is free."""
        with self._lock:
            self._held.pop(str(node), None)

    @contextlib.contextmanager
    def holding(self, node, handle: Optional[str] = None):
        """`node`'s subtree held for an authoring while the block runs; ValueError where another holds it."""
        if (other := self.take(node, handle)) is not None:
            raise ValueError(f"an authoring is writing {other[0]} now")
        try:
            yield
        finally:
            self.let_go(node)

    @staticmethod
    def _opens(h: Optional[str]) -> str:
        return "nothing: it ends by itself" + (f", `auto_decompose(writing=\"{h}\")` answering it" if h else "")

    def in_flight(self) -> list[dict]:
        """The authorings as `Engine.in_flight_nodes` names work under way."""
        return [{"task_id": n, "state": t.state.name if (t := self._graph.get_task(TaskId(n))) else None,
                 "why": "has its subtree being written — an authoring is running", "opens_with": self._opens(h),
                 **({"writing": h} if h else {})} for n, h in self.held().items()]

    def wait(self, t) -> Optional[dict]:
        """Why `t` takes no step while an authoring writes over it — the wait waits on the authoring, not on its owner —
        or None."""
        if (w := self.over(t.id)) is None:
            return None
        return Wait(task_id=str(t.id), state=t.state.name, assignee=t.assignee, kind="authoring",
                    waits_on=(f"the authoring of {w[0]}",), why=f"an authoring is writing {w[0]}, over this node",
                    opens_with=self._opens(w[1])).as_dict()
