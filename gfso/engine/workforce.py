"""Who works here: the registered participants the dispatcher publishes downward — each one's kind, whose project each
instrument and executor serves, the model each executor runs, the instrument bound to each node.

The roster is the delegation layer's, one server-wide file; the engine may not reach up into it (the layer gate), so
the dispatcher publishes the facts and the surfaces ask them here. It was five fields and ten methods inside `Engine`,
beside the signal machine (sync audit, D-F10)."""
from __future__ import annotations

from typing import Callable, Optional

from gfso.config import DEFAULT_PROJECT
from gfso.core.graph.model import Graph
from gfso.core.types import AgentId, TaskId


class Workforce:
    """The participants one engine's project may be given, as the dispatcher last published them."""

    def __init__(self, graph: Graph, project: Callable[[], Optional[str]]):
        self._graph, self._project = graph, project
        # WHO, OF THE NON-HUMAN PARTICIPANTS, IS WHAT — {id: kind}, published downward by the
        # dispatcher each round. Declared here because three surfaces read it (the frontier's
        # in-flight view, the affordance layer's "a human or a machine holds this", the tool door's
        # wait message) and a field born in the dispatcher had all three reading it defensively —
        # which reads as "nobody is registered" on any engine the dispatcher has not touched yet.
        self._roster: dict[str, str] = {}
        #: WHOSE each published instrument is — `{validator id: project or None}`, written by
        #: the dispatcher beside `_roster`. Declared here rather than read defensively, because
        #: a field a reader has to guess at is a field two readers will guess differently.
        #: `None` for an entry means UNSCOPED, which is shared by design; an empty dict means
        #: no dispatcher has published yet, which is not the same as "no instruments".
        self._validator_projects: dict[str, object] = {}
        self._executor_projects: dict = {}   # the roster's executors and whose each is (`publish_executor_pool`)
        self._executor_sessions: dict = {}   # …and what one session of each is
        #: node id → the instrument bound to it {id, project, workdir}, published by
        #: the dispatcher each round (see `bound_validator`).
        self._bound_validators: dict = {}

    def publish_roster(self, kinds: dict) -> None:
        """The dispatcher's answer to "who of the non-human participants is what" — `{id: kind}`."""
        self._roster = dict(kinds or {})

    def roster(self) -> dict:
        """`{id: kind}` as last published — what `validation.party_kind` reads."""
        return self._roster

    def publish_bound_validator(self, task_id: TaskId, validator: Optional[dict]) -> None:
        """The dispatcher's half of `bound_validator` — who it will send at this node, for the doors.

        A method rather than an attribute the dispatcher writes: the coupling ratchet counts a reach
        into another module's private field, and it was right to — what the doors need is a fact
        this object owns, not a dictionary somebody else keeps in it."""
        if validator and validator.get("id"):
            self._bound_validators[str(task_id)] = dict(validator)
        else:
            self._bound_validators.pop(str(task_id), None)

    def bound_validator(self, task_id: TaskId) -> dict:
        """The instrument the dispatcher bound to this node, as facts a door may read: id, project,
        workdir. `{}` when nothing is bound.

        Published FROM the dispatcher, exactly like `_roster` and `authorized_validators`, because
        the doors may not reach into the delegation layer to ask (the mechanical layer gate) and the
        answer depends on the roster, which is that layer's. What the doors do with it is say WHOSE
        validator is about to read their work — a role registered for another project, standing in a
        directory that holds none of this delivery, was announced as "an independent validator" and
        five strangers had to read the log to find out (waves 23–25)."""
        return dict(self._bound_validators.get(str(task_id)) or {})

    def has_an_instrument(self) -> bool:
        """Is any published instrument one that would be given THIS project's nodes? (`validated_by_instrument` asks
        it first.)

        The roster is one server-wide file, so "an instrument is registered" and "an instrument will
        validate you" are different facts, and this asked the first while every caller meant the second.
        Measured on the HTTP door 2026-09-06: a project that had registered nothing was told on every
        delivery to wait for a bound validator, because other projects' roles filled the set — and the
        same sentence told them that recording their own verdict "would race it". There was nothing
        to race. The scoping is `validator_for`'s, said once more: this project's roles, or UNSCOPED
        ones (which are shared by design), never another project's.
        """
        whose = self._validator_projects
        if not whose:                          # nothing published yet — the set is all we know
            return bool(self._graph.authorized_validators)
        # THE DECLARED SPELLING. This engine carries the project under two names — `project_name`,
        # which every reader in the product uses, and `_project_name`, which `runtime` also sets
        # and calls "the older spelling, still read downstream". A third one written here would
        # be the same defect one turn later.
        mine = self._project() or DEFAULT_PROJECT
        return any(p in (None, "", mine) for aid, p in whose.items()
                   if aid in self._graph.authorized_validators)

    def publish_validator_projects(self, whose: dict) -> None:
        """The dispatcher's answer to "whose is each instrument" — `{validator id: project or None}`.

        A setter rather than an attribute the dispatcher writes into, for the same reason
        `publish_bound_validator` is one: the layer below must not be reached into from the layer above,
        and a field written from outside is a field with no owner.
        """
        self._validator_projects = dict(whose or {})

    def publish_executor_pool(self, whose: dict, sessions: Optional[dict] = None) -> None:
        """The dispatcher's answer to "which executors exist, and whose" — `{executor id: project or
        None}`, published beside the validators' for the same reason: the roster is the layer above's —
        and what one session of each is — its model and turn budget — the fact a decomposer judges one session's
        capacity against."""
        self._executor_projects = dict(whose or {})
        self._executor_sessions = dict(sessions or {})

    def executor_session(self, agent_id) -> str:
        """One session of a registered executor — its model, and its turn budget where the roster names one — or ''
        where the system does not know it (the user's agent)."""
        return str(self._executor_sessions.get(str(agent_id or "")) or "")

    def executor_pool(self) -> list[AgentId]:
        """The executors a mode may hand this project's nodes to: this project's own registrations,
        else unscoped ones — never another project's (the scope `validator_for` already keeps). Parallel
        runs share one server and one roster; a node given to another run's executor would be worked
        in THAT run's directory."""
        whose = self._executor_projects
        mine = sorted(a for a, p in whose.items() if p and p == self._project())
        return [AgentId(a) for a in (mine or sorted(a for a, p in whose.items() if not p))]

    def is_system_executor(self, agent_id) -> bool:
        """Is this id an executor the system starts itself — a registered `llm-executor` of any project?"""
        return str(agent_id or "") in self._executor_projects

    def kind_of(self, agent_id: str) -> Optional[str]:
        """What KIND of participant this id is — `llm-executor` / `llm-validator` / … — or None for
        a human (an unregistered Del IS a human, §10.4). The roster is the dispatcher's, published
        downward; this is the question the read surfaces actually ask, so they ask it rather than
        reading the map."""
        return self._roster.get(str(agent_id))

    def signs_as_instrument(self, agent_id: str) -> bool:
        """Is this id the issuer's authorized role-V instrument (§10.3)? One owner for the question:
        the surfaces that must agree with the seam gate used to read the graph's own field."""
        return str(agent_id) in self._graph.authorized_validators
