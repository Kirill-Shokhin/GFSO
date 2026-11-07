"""Where a passed node's result stands: joined into the place its whole works, or not yet, or refused (§8.7, the glue).

A host that keeps one place per node joins each passed part where its whole works, and a passed root into the base;
until the join lands the whole's place does not hold the part. The engine reads this state for "parts ready" and for
"complete"; it was four fields and eight methods inside `Engine`, beside the signal machine (sync audit, D-F10)."""
from __future__ import annotations

import threading
from typing import Optional

from gfso.core.graph.model import Graph
from gfso.core.types import TaskId, settled_positive


#: The words a refused join carries when what its PASS accepted is no longer on its branch: nothing is merged, and no
#: reader may tell anyone to merge that branch — the work is delivered again.
NOT_ON_ITS_BRANCH = "what its PASS accepted is not on its branch"


class Joins:
    """The joins of one engine's graph, as its host reports them (`mark_joining`)."""

    def __init__(self, graph: Graph):
        self._graph = graph
        self._lock = threading.Lock()
        # nodes whose passed result is being joined into the place their whole works, by a host that keeps one place
        # per node (`mark_joining`): until it lands, the whole's place does not hold it
        self._joining: set[str] = set()
        self._unjoined: dict[str, str] = {}      # a passed node whose result did not land where it joins: why
        # nodes whose join ended with the result in place: {id: its `reopens` then}. A fact of that generation: kept bare, a
        # reopened root read landed at its second DONE, ahead of its join, over a base without what it reopened for
        self._landed: dict[str, int] = {}
        self._join_owed = None                   # the host's word: does this node's result owe a join? (`set_join_owed`)

    def set_join_owed(self, owed) -> None:
        """The host that keeps a place per node says which passed nodes owe a join (`owed(task) -> bool`, asked
        without git). A root that owes one is complete only on the host's word that it LANDED (`mark_joining`)."""
        self._join_owed = owed

    def mark_joining(self, task_id, on: bool, unjoined: Optional[str] = None) -> None:
        """A host's word on a passed node's join where its whole works: running (`on`), or ended — landed, or, for a
        root, not landed (`unjoined`, why). A retry keeps the last refusal standing until a try lands (critic r4: a
        retry erased it, so the root read "being joined" forever). A whole is read over its parts only once theirs
        have (`landed`)."""
        tid, t = str(task_id), self._graph.get_task(TaskId(task_id))
        with self._lock:
            if on:
                self._joining.add(tid)
                return
            self._joining.discard(tid)
            if unjoined is None:
                self._unjoined.pop(tid, None)
                self._landed[tid] = t.reopens if t is not None else 0
            else:
                self._unjoined[tid] = unjoined
                self._landed.pop(tid, None)

    def root_landed(self, root) -> bool:
        """Does the passed root's result stand in the base? Read positively — the host said it landed — wherever a
        join is owed: a DONE visible before the host marked its join (critic r4) or a process restarted since reads
        "being joined", never `complete`."""
        tid, owed = str(root.id), self._join_owed
        with self._lock:
            if tid in self._joining or tid in self._unjoined:
                return False
            if self._landed.get(tid) == root.reopens:
                return True
        return owed is None or not owed(root)

    def joining_nodes(self) -> list[str]:
        """The nodes `mark_joining` holds as joining right now."""
        with self._lock:
            return sorted(self._joining)

    def unjoined_roots(self) -> dict[str, str]:
        """{root: why} — the passed roots whose result did not land in the base."""
        with self._lock:
            left = dict(self._unjoined)
        return {t: why for t, why in left.items() if self._graph.get_parent(TaskId(t)) is None}

    def unjoined_parts(self, whole) -> list[tuple[str, str]]:
        """[(part, why)] — the whole's passed parts whose result did not merge where it works: its integration to do
        (§8.7, the glue), named with the branch that holds each (critic r4: a held whole was told to aggregate with
        nothing naming them)."""
        with self._lock:
            left = dict(self._unjoined)
        return [(str(k.id), left[str(k.id)]) for k in self._graph.get_active_children(whole.id) if str(k.id) in left]

    def landed(self, t) -> bool:
        """Is this node accepted AND has its join where its whole works ended — no join of it in flight. A join that
        ended refused leaves the part on its branch, named to its whole as integration work (`unjoined_parts`).
        Accepted is `settled_positive`: a DONE(AUTO_PASS) row an older build wrote is what a parent's conjunction
        accepts (§16.14) — asking for an EARNED pass locked its whole ancestry with no exit."""
        return settled_positive(t) and str(t.id) not in self._joining

    def open_parts(self, task_id: TaskId) -> list:
        """The whole's active parts that have not landed (`landed`) — empty: its parts are ready for its aggregate, its
        validation and its PASS (Thm 1). ONE owner of "parts ready"; the PASS record and the dispatcher wrote it again
        (ortho audit, D-F3)."""
        return [k for k in self._graph.get_active_children(task_id) if not self.landed(k)]
