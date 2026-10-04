"""Who is running a model over a node right now: the validator's claim on a delivery, the plan check's on a split.

A claim keeps a second paid run off the same generation of the same node, and expires: a run that dies without
unwinding cannot release it, and a claim nobody is behind must not park a node (`VALIDATION_CLAIM_TTL`). It was
three fields and six methods inside `Engine`, beside the signal machine (sync audit, D-F10)."""
from __future__ import annotations

import logging
import threading
from typing import NamedTuple

from gfso.config import VALIDATION_CLAIM_TTL
from gfso.core.graph.model import Graph
from gfso.core.types import TaskId

log = logging.getLogger(__name__)


class ValidationClaim(NamedTuple):
    """A validator run's claim on one delivery (`Claims.begin_validation`): the slot it holds, and where the signal
    log stood when it began — the run's own, carried with it, since its verdict is on the artifact as it was then.
    Kept in a slot shared by generation, a second run reclaiming it after the TTL overwrote the first run's place,
    and the slow run's PASS then stood over a part fixed after it had read (critic, 2026-09-28)."""
    key: tuple
    log_at: int


class Claims:
    """The in-flight claims of one engine's model runs — validation of a delivery, Level-2 review of a plan."""

    def __init__(self, graph: Graph, clock, audit):
        self._graph, self._clock, self._audit = graph, clock, audit
        self._lock = threading.Lock()
        #: in-flight validator runs — {(node, *generation): when it was claimed}, where the
        #: generation is (iteration, reopens, revisions), so the key is a 4-tuple. The
        #: TIME is what makes an abandoned claim recoverable: a run that dies without
        #: unwinding cannot release it, and a claim nobody is behind must not park a node.
        self._val_inflight: dict = {}
        #: validations the dispatcher has taken on and not yet run — waiting for a slot under its concurrency cap
        self._val_queued: dict = {}
        # …and the same for the PLAN's check. `validate_result` has suppressed a duplicate spawn for
        # a while; `review_decomposition` had nothing of the kind, so the frontier went on telling a
        # driver to run it while one was running — a duplicate paid round for the same plan
        # (measured on the human door 2026-08-22, where the two surfaces disagreed about it).
        # A TIMESTAMP PER CLAIM, not a bare membership set — the same shape and the same TTL the
        # validation claim next to it has carried since 2026-09-02. A review claim that was never
        # released (see `begin_review`) made the node read "a check is already running" for ever,
        # on every surface, with nothing running.
        self._review_inflight: dict = {}
        #: A monotonic id per review claim, so `end_review` can tell ITS claim from the one that
        #: replaced it after a TTL reclaim (a key alone cannot: the generation does not move).
        self._review_claims = 0

    def validation_in_flight(self, task_id: TaskId) -> bool:
        """Is an instrument validating THIS generation right now — asked without claiming the slot.

        `begin_validation` answers the same question by taking the slot, which a read must not do.
        Same TTL rule, so a leaked claim does not make a node permanently "being validated": a claim
        older than any run this product waits for is not a run.
        """
        key = (str(task_id), *self._graph.generation_of(task_id))
        with self._lock:
            if key in self._val_queued:   # a live round always stands behind it, and its end always releases it
                return True
            since = self._val_inflight.get(key)
            return since is not None and self._clock.now() - since <= VALIDATION_CLAIM_TTL

    def queue_validation(self, task_id: TaskId):
        """The system has taken this delivery's validation on and will run it when a slot frees: it is in flight for
        every reader — a validation queued behind other sessions read as "nobody validating", and a holder was told
        the observation was its own move (critic, 2026-10-09). Returns the key `dequeue_validation` releases."""
        key = (str(task_id), *self._graph.generation_of(task_id))
        with self._lock:
            self._val_queued[key] = self._clock.now()
        return key

    def dequeue_validation(self, key) -> None:
        """The queued validation's round has ended, whatever it produced. Idempotent."""
        with self._lock:
            self._val_queued.pop(key, None)

    def begin_validation(self, task_id: TaskId):
        """Claim the in-flight validator slot for the node's CURRENT generation (node, iteration,
        reopens). Returns the claimed key, or None if a run is already in flight — concurrent
        spawns (manual validate_result × the dispatcher's auto-validation, observed live: three
        parallel validators on one VALIDATING node) duplicate minutes of agent work whose losing
        verdict the FSM rejects anyway. Release with end_validation(key)."""
        key = (str(task_id), *self._graph.generation_of(task_id))
        with self._lock:
            if (since := self._val_inflight.get(key)) is not None:
                # …UNLESS NOBODY IS BEHIND IT ANY MORE. The claim is released in a `finally`, so an
                # ORDERLY end always frees it — and a run that dies without unwinding (a killed
                # subprocess, a torn-down thread) left it set forever. The node then reads as "being
                # validated" on every surface while nothing is running, `validate_result` refuses the
                # re-run its own refusal advises, and polling never ends: measured on the agent door
                # 2026-09-02, ~15 minutes on each of two nodes with the reports already refused.
                # A claim older than any run this product will wait for is not a run; it is a leak.
                if self._clock.now() - since <= VALIDATION_CLAIM_TTL:
                    return None
                log.warning(f"the validation claim on {task_id} is older than "
                            f"{VALIDATION_CLAIM_TTL:.0f}s with nothing behind it — reclaiming")
            self._val_inflight[key] = self._clock.now()
            return ValidationClaim(key, len(self._audit))

    def end_validation(self, key) -> None:
        """Release the in-flight validator claim taken by `begin_validation`. Idempotent: a key that is
        no longer held (reclaimed after its run died without unwinding) simply has nothing to drop."""
        with self._lock:
            self._val_inflight.pop(key.key, None)

    def begin_review(self, task_id: TaskId):
        """Claim the in-flight slot for THIS version of the node's plan, or None if one is running.

        …AND A CLAIM NOBODY IS BEHIND ANY MORE IS NOT A RUN. This was a bare set with no expiry, so
        a claim that was never released held the slot until the process ended: `review_decomposition`
        answered "a check is already running, its verdict lands by itself", the frontier reported
        the node as WAITING with `opens_with: nothing`, and the execution gate went on refusing its
        children for want of a Level-2 verdict — a node no signal could advance, presented to an
        unattended driver as a healthy wait. The only escapes were revising the node (which moves
        the key) or restarting the server. Same TTL as the validation claim beside it, and the same
        loud reclaim, because the two are the same fact about the same kind of run.
        """
        key = (str(task_id), *self._graph.generation_of(task_id))
        with self._lock:
            held = self._review_inflight.get(key)
            if held is not None:
                if self._clock.now() - held[1] <= VALIDATION_CLAIM_TTL:
                    return None
                log.warning(f"the Level-2 review claim on {task_id} is older than "
                            f"{VALIDATION_CLAIM_TTL:.0f}s with nothing behind it — reclaiming")
            # A TOKEN PER CLAIM, so a reclaimed run cannot release the claim that replaced it. The
            # key is the node's generation, which does not move when a stale claim is taken over —
            # so the slow original, returning after the TTL, ran `end_review` and freed the LIVE
            # claim, and a third review could start on the same plan. The token says which claim
            # this is; `end_review` drops it only if it is still the one held.
            self._review_claims += 1
            token = (key, self._review_claims)
            self._review_inflight[key] = (self._review_claims, self._clock.now())
            return token

    def end_review(self, token) -> None:
        """Release the slot — whether the check answered or died, so a failed round is retryable.

        Idempotent, and it releases only THIS claim: a run whose claim was reclaimed after the TTL
        finds a different token in the slot and leaves it alone, instead of freeing the live claim
        that replaced it."""
        if token is None:
            return
        key, mine = token
        with self._lock:
            if (held := self._review_inflight.get(key)) is not None and held[0] == mine:
                del self._review_inflight[key]

    def review_in_flight(self, task_id: TaskId) -> bool:
        """Is a Level-2 check already running over THIS version of the plan? — asked without
        claiming the slot, and under the same TTL, so a leaked claim never reads as a live run."""
        key = (str(task_id), *self._graph.generation_of(task_id))
        with self._lock:
            held = self._review_inflight.get(key)
            return held is not None and self._clock.now() - held[1] <= VALIDATION_CLAIM_TTL
