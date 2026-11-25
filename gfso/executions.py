"""WHICH EXECUTION A PROJECT'S WORK RUNS IN: the one its roles declare (`register_agent(execution=)`, read from
`executions.json`), one object per (execution, project, place) bound to the project's record (`where_it_runs`) — else
this host —, refused where binding work there would be wrong (`execution_of`), and gone with the project
(`drop_execution`). The executions themselves are `adapters.execution`'s; which node works where is `workspaces`'."""
from __future__ import annotations

import json

from gfso.adapters.execution import (ContainerExecution, LocalExecution, drop_volumes, held_as_tree, network_of,
                                     stricter)
from gfso.adapters.netrecord import forget
from gfso.config import executions
from gfso.core.graph.model import root_of
from gfso.core.types import THIS_HOST, VOLUME, PlaceUnavailable, hold_places
from gfso.made import carried
from gfso.roster import AgentRegistry


def held_off_the_host(engine, ex):
    """`ex`, unless it is this host for a project whose places stand in volumes: a role lost after the gate gave the reading that binds
    work there the user's machine — its validation, or the system's git making a place in the user's own repository (critic)."""
    if isinstance(ex, LocalExecution) and engine.graph.setting(VOLUME + "places"):
        raise PlaceUnavailable(THIS_HOST, "this project's places stand in volumes and none of its roles declares their execution now: register them back")
    return ex


#: one object per (execution, project): its container is started once and every call of the project goes through it
_EXECUTIONS: dict = {}


def declaring_role(engine, agents: "AgentRegistry | None" = None) -> "dict | None":
    """The role of this project that declares its execution, whether or not the declaration reads now."""
    return next((c for c in (agents or AgentRegistry()).list().values()
                 if c.get("execution") and c.get("project") == engine.project_name and c.get("workdir")), None)


def _declared(engine, agents: "AgentRegistry | None" = None):
    """(the object of the execution this project declares, its declaration) — made once per (execution, project,
    place); (None, None) for this host."""
    if (role := declaring_role(engine, agents)) is None:
        return None, None
    project = engine.project_name
    key = (role["execution"], project, role["workdir"])
    try:
        d = executions()[role["execution"]]
    except (ValueError, KeyError):
        # a declaration that does not read shuts the way out it switched: an operator closing it in a hurry made a typo
        if key in _EXECUTIONS:
            _EXECUTIONS[key].switch({"mode": "off"})
        raise
    if key not in _EXECUTIONS:
        _EXECUTIONS[key] = ContainerExecution(role["execution"], d["image"], d.get("env_file"), d["state"],
                                              role["workdir"], project)
        hold_places(_EXECUTIONS[key].files)
    return _EXECUTIONS[key], d


def execution_of(engine, agents: "AgentRegistry | None" = None):
    """WHERE this project's work runs (`where_it_runs`), never this host for a project whose places stand in volumes
    (`held_off_the_host`): every reading that binds work refuses there, by default — one call site at a time, a role lost
    after a gate still put a validation, a place's git and a plan's reader on the user's machine (critics). Nor a volume
    that holds its base as a live tree (`held_as_tree`): its plan reader, validator and issuer's contact each read it, one
    call site found at a time (critics)."""
    ex = held_off_the_host(engine, where_it_runs(engine, agents))
    if isinstance(ex, ContainerExecution) and (why := held_as_tree(ex)):
        raise PlaceUnavailable(str(ex.base), why)
    return ex


def where_it_runs(engine, agents: "AgentRegistry | None" = None):
    """WHERE this project's sessions and commands run: the execution its roles declare (`register_agent(execution=)`,
    one per project), in the place of the role that declared it — else this host. Its volume's making is the
    project's own record (`Volume.record`): a volume lost under it is the place down, never refilled. Read bare only to
    end or free what runs; work is bound through `execution_of`."""
    ex, d = _declared(engine, agents)
    if ex is None:
        return LocalExecution()
    ex.volume.record = (engine.graph.setting, engine.graph.store_setting)
    ex.volume.carried = lambda dirs: carried(engine, dirs)
    ex.volume.root = lambda: root_key(engine)
    ex.volume.said = lambda text: engine.emit_info("execution", text)
    # the switch as set NOW — the more closed of its execution's declaration and the project's own (`set_mode`), the
    # declaration a ceiling — kept by the container: every holder of any object of it starts it under this one
    own = engine.graph.setting("network")
    try:
        mode, hosts = stricter(network_of(d.get("network")), network_of(json.loads(own)) if own else None)
        network = {"mode": mode, "hosts": list(hosts)}
    except ValueError:
        network = {"mode": "unreadable"}   # either one unreadable shuts the way out, as an unreadable declaration does
    ex.switch(network)
    return ex


def root_key(engine) -> str | None:
    """The project's root as its base's import is keyed (`Volume.import_base`): its id and its making — a root made
    again under the id is another."""
    return root_key_of(r) if (r := root_of(engine.all_tasks())) is not None else None


def root_key_of(root) -> str:
    """A root as its base's import is keyed: its id and its making — a root made again under the id is another."""
    return f"{root.id}@{root.created_at.isoformat()}"


def drop_execution(project: str) -> None:
    """The project is gone: its containers go, and the objects that held them, and every volume of it by its label
    (`drop_volumes`) — the one removal of its places in volumes, its roster read or not (those on this machine go at
    the deletion's end, `workspaces.drop_host_files`)."""
    for key in [k for k in _EXECUTIONS.copy() if k[1] == project]:   # …a copy: other threads make executions
        if not (ex := _EXECUTIONS.pop(key, None)):
            continue
        ex.stop()
        hold_places(ex.files, False)
    drop_volumes(project)
    forget(project)
