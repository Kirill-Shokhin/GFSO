"""What waits on a decision nobody has made yet: a node whose automatic validation gave up, one whose executor stopped
twice without a signal, one whose executor disputes its contract from a state where CHALLENGE is not admissible.

In memory on purpose — each park is exactly as durable as the decision behind it, and a restart re-tries. It was three
fields and eight methods inside `Engine`, beside the signal machine (sync audit, D-F10)."""
from __future__ import annotations

from typing import Callable, Optional

from gfso.core.graph.model import Graph, generation_of_task
from gfso.core.types import State, Task, TaskId


class Parking:
    """The parked nodes of one engine's graph — the issuer's to decide, said on every surface."""

    def __init__(self, graph: Graph, moves: Callable[[TaskId], int]):
        self._graph, self._moves = graph, moves
        # Nodes where AUTOMATIC validation gave up (two reports, no verdict). The dispatcher says so
        # in the log and the node then sits in VALIDATING forever with the frontier still printing
        # "VALIDATE this" — measured 2026-08-20: two nodes stood 9 and 5 minutes, and only a hand
        # `validate_result` moved them. In-memory on purpose: a restarted dispatcher re-tries the
        # validation from scratch, so the parking is exactly as durable as the decision behind it.
        self._validation_parked: set = set()
        # …and nodes whose EXECUTOR's run ended twice with nothing signalled (a run cut at its turn
        # cap, an unreadable report, a crash). The node stays in EXECUTING, where only the deadline
        # moves it; measured on the delegated coreutils run, a leaf sat there to the run's ceiling
        # while its issuer read "executor's move". In memory for the same reason as above.
        # Keyed to the node's Del, generation, state and count of accepted transitions at the park: a
        # park describes THAT executor on THAT packet version with nothing moved since, so a reassign, a
        # revision, or any transition (a BLOCK and its resolution included) ends it by itself — no exit
        # has to remember to clear it.
        self._execution_parked: dict[str, tuple] = {}
        # Nodes whose EXECUTOR disputes the contract from a state where CHALLENGE is not
        # admissible (§12.4 admits it from OFFERED only). The dispute is real and belongs to
        # the issuer; without somewhere to put it the signal was refused and the node stood
        # still with its round spent — a run died that way on 2026-08-21. In memory on
        # purpose, like `_validation_parked`: a restart re-offers the node to its executor,
        # and if the dispute is real it will be raised again.
        self._contested: dict[str, str] = {}

    def park_validation(self, task_id) -> None:
        """The dispatcher's record: automatic validation of this node gave up (two reports, no verdict)."""
        self._validation_parked.add(str(task_id))

    def unpark_validation(self, task_id) -> None:
        """A fresh validation attempt has started — the park no longer describes it."""
        self._validation_parked.discard(str(task_id))

    def uncontest(self, task_id) -> None:
        """The issuer's revision settled the dispute by construction (the node is re-offered)."""
        self._contested.pop(str(task_id), None)

    def contest(self, task_id: TaskId, why: str) -> None:
        """Record that the node's EXECUTOR disputes its contract from a state where CHALLENGE is not
        admissible (§12.4 admits it from OFFERED only). The frontier hands it to the issuer, whose
        `revise` settles it by construction — the node returns to OFFERED to be taken afresh."""
        self._contested[str(task_id)] = (why or "no reason given")[:600]

    def contested_reason(self, task_id: TaskId) -> Optional[str]:
        """Why this node's executor disputes its contract, or None."""
        return self._contested.get(str(task_id))

    def parked_validations(self) -> frozenset:
        """Nodes whose automatic validation has GIVEN UP — read by the doors, written by the dispatcher.

        Asked through a method because a door reaching for the field by `getattr` with a default is
        the duck-typed private reach the coupling ratchet counts, and because the default silently
        turns "the engine has no such idea" into "nothing is parked" — the two are not the same
        answer and only one of them is true."""
        return frozenset(self._validation_parked)

    def park_execution(self, task_id: TaskId) -> None:
        """The dispatcher's record: this node's executor stopped twice without a signal."""
        t = self._graph.get_task(task_id)
        if t is not None:
            self._execution_parked[str(task_id)] = self._park_key(t)

    def unpark_execution(self, task_id: TaskId) -> None:
        """A fresh executor run has started on the node — the park no longer describes it."""
        self._execution_parked.pop(str(task_id), None)

    def _park_key(self, t: Task) -> tuple:
        return (str(t.assignee), generation_of_task(t), t.state, self._moves(t.id))

    def is_execution_parked(self, t: Task) -> bool:
        """Parked = in the work-state visit, under the Del and packet version, the park was recorded for."""
        key = self._execution_parked.get(str(t.id))
        return (key is not None and t.state in (State.OFFERED, State.EXECUTING, State.REWORKING)
                and key == self._park_key(t))

    def parked_executions(self) -> frozenset:
        """Nodes whose delegated executor stopped twice without a signal — the issuer's to decide."""
        return frozenset(str(t.id) for t in self._graph.subtree(None) if self.is_execution_parked(t))
