"""Where a node's work stands: the scope one executor's session carries it in (`session_scope`), the node's own git
workspace derived from its executor's roster place (`node_workspace`), entering it, joining its PASSed parts into the
whole (`join_whole`), and clearing them at the root's PASS (`clear_workspaces`). Derived, never stored — save which
places were made (`made`)."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from gfso.adapters import worktrees as W
from gfso.adapters.worktrees import base_of
from gfso.adapters.netrecord import forget
from gfso.adapters.execution import (IMPORTED, ContainerExecution, LocalExecution, component, node_key, drop_volumes,
                                     held_as_tree, network_of, stricter)
from gfso.config import DEFAULT_PROJECT, MODEL_DEFAULT, executions
from gfso.llm import llm_factory
from gfso.places import cheap_to_ask, same_place
from gfso.core.graph.model import generation_of_task, grounds_key, root_of
from gfso.core.types import HOST, MADE, NODES, THIS_HOST, VOLUME, PlaceUnavailable, Signal, TaskId, State, base_named, hold_places, nodes_dir
from gfso.core.protocol.procedure import round_of
from gfso.engine.findings import record_round
from gfso.engine.joins import NOT_ON_ITS_BRANCH
from gfso.roster import AgentRegistry


def performer(engine, agents: "AgentRegistry", party) -> tuple:
    """(id, roster entry) of the executor whose session performs `party`'s nodes: a registered role itself, the
    standing agent's hands where its mode dispatches (`Engine.hands_of`) — else (None, None), a party that performs
    in its own chat, or a person."""
    if (cfg := agents.get(str(party or ""))) is not None:
        return str(party), cfg
    h = engine.hands_of(party)
    return (h, agents.get(h)) if h and agents.get(h) is not None else (None, None)


def session_scope(engine, agents: "AgentRegistry", task):
    """The top of the scope one registered executor's session carries this node in — or None, and the node
    keeps a session and a validation of its own. Every node of the scope is that executor's, and an llm-validator
    is bound to it: the scope's deliveries carry no self-check of their own and wait for its one validation, so
    with no instrument they waited for nothing (critic, 2026-09-28); a scope whose instrument is the hidden-test
    oracle keeps the per-node path the oracle's criteria are mapped to."""
    top = engine.scope_top(task.id) if task is not None else None
    if top is None or (performer(engine, agents, top.assignee)[1] or {}).get("kind") != "llm-executor":
        return None
    if any(str(m.assignee) != str(top.assignee) for m in engine.scope_members(top.id)):
        return None
    vid = agents.validator_for(performer(engine, agents, top.assignee)[0], project=engine.project_name)
    return top if vid and (agents.get(vid) or {}).get("kind") == "llm-validator" else None




def _workspace(engine, agents: "AgentRegistry", task) -> tuple[str, str, str] | None:
    """(base, place, branch) of the node's workspace — derived, never stored: the base is its executor's roster
    workdir when that is a git repository's top, the key its scope's top when one session carries the scope (one
    place for the session and its one validation), else the node. Under the project, since two projects on one
    base both have a `root`. None: no git base, and the node works in the shared directory as before."""
    w = _place_of(engine, agents, task)
    return w if w is not None and cheap_to_ask(w[0]) and W.is_repo_top(w[0]) else None


def _place_of(engine, agents: "AgentRegistry", task) -> tuple[str, str, str] | None:
    """(base, place, branch) as `_workspace` derives them, asking git nothing — so a caller that must not wait on a
    subprocess (the transition bus) can ask whether a place was ever made (`made`)."""
    base = (performer(engine, agents, task.assignee)[1] or {}).get("workdir") if task is not None else None
    if not base:
        return None
    key, proj = node_key((session_scope(engine, agents, task) or task).id), component(engine.project_name or DEFAULT_PROJECT)
    return base, str(Path(base).parent / nodes_dir(Path(base).name) / proj / key), f"gfso/{proj}/{key}"



#: the places this process asked about where the record had none, and found not made (`made`)
_UNMADE: set = set()


def made(engine, place: str) -> bool:
    """Was `place` made? THE SYSTEM'S RECORD, not the file system: `_ensure_place` adds a place it made,
    `clear_workspaces` drops one it removed, kept with the project's settings (a restart reads it) and read with no subprocess — the
    transition bus asks it. A place may stand nowhere on this host, and what stands where an agent writes decides
    nothing of the protocol."""
    if (got := engine.graph.setting(MADE + place)) is not None or (
            got := engine.graph.setting(MADE + _spelled(place))) is not None or (   # …as a copy-in carried it
            got := engine.graph.setting(MADE + _named_as_before(place))) is not None:
        return got == "1"
    # …a place made before the record was kept: asked once (once per process where it is not made), then recorded —
    # the record decides from there on. On this host, never by a call into a container from the transition bus: until
    # the places move into volumes they are host directories (a fallback that goes with that move)
    if place in _UNMADE or engine.graph.setting(VOLUME + "places"):     # …moved into a volume: the record alone
        return False
    if HOST.is_dir(place):
        _record(engine, place, True)
        return True
    _UNMADE.add(place)
    return False


def _record(engine, place: str, made: bool) -> None:
    engine.graph.store_setting(MADE + place, "1" if made else "0")


def _named_as_before(place: str) -> str:
    """A place of a base whose name holds what `place_name` escapes, as its record was written before it did."""
    return str(Path(*(NODES + base_named(x) if x.startswith(NODES) else x for x in Path(place).parts)))


def _spelled(place) -> str:
    """One spelling of a place, whichever it arrived in — what a copy-in records it by (`_carried`)."""
    return os.path.normcase(os.path.abspath(place))


def _carried(engine, dirs) -> None:
    """The places and rounds a copy-in carried into the project's volume, recorded as made — before their host copy
    is consumed, which the record of places made before it was kept fell back on (`made`, `round_stands`)."""
    for d in map(str, dirs):
        if round_of(d):
            record_round(engine.graph, d, True)
        elif not Path(d).parent.name.startswith("."):
            _record(engine, _spelled(d), True)


def stands(engine, agents: "AgentRegistry", where: str) -> bool:
    """Does the directory a role works in stand: a node's place by the record (`made`); any other is a base, the user's
    repository, read on this host."""
    return made(engine, where) if base_of(where) else Path(where).is_dir()


def node_workspace(engine, agents: "AgentRegistry", task_id) -> str | None:
    """The node's own workspace, once its first session has made it — where its delivery stands and is validated."""
    w = _workspace(engine, agents, engine.graph.get_task(TaskId(task_id)))
    return w[1] if w is not None and made(engine, w[1]) else None


def _where_it_joins(engine, agents: "AgentRegistry", task, w: tuple) -> str | None:
    """Where the node's result joins the whole: its parent's workspace in the same repository once the parent has
    one, else the base. None inside its own scope, whose place is the parent's too."""
    parent = engine.graph.get_parent(task.id)
    pw = _workspace(engine, agents, parent) if parent is not None else None
    if pw is not None and pw[2] == w[2]:
        return None
    return pw[1] if pw is not None and same_place(pw[0], w[0]) and made(engine, pw[1]) else w[0]


def _before_a_part_joins(engine, whole, base, into, execution) -> None:
    """Where the whole's tree stands before a part joins it is the ground of every part in its split that has none yet:
    what it starts from. From the tree with its joined parts in, a node read a sibling's work with no edge in the plan,
    by the order the parts happened to start in: an input the graph does not say, the plan held by agents who know more
    than it does (M1, §15.5). A part admitted later stands on what the whole held when it entered: its decomposer's
    fixing saw that; an edge declared for one part opens nothing to another."""
    with W.one_at_a_time(base):
        held = json.loads(engine.graph.setting(key := grounds_key(whole.id)) or "{}")
        if new := [str(k.id) for k in engine.graph.get_active_children(whole.id) if str(k.id) not in held]:
            head = W.git(into, "rev-parse", "HEAD", execution=execution).stdout.strip()
            engine.graph.store_setting(key, json.dumps({**held, **dict.fromkeys(new, head)}))


def _has_branch(w: tuple, execution) -> bool:
    """Does the node's work exist to join? Its branch, not its directory: a place removed by hand once let a producer's
    work drop out of every consumer without a word, its commits still in the refs."""
    return W.git(w[0], "rev-parse", "--verify", "--quiet", f"refs/heads/{w[2]}", execution=execution).returncode == 0


def _accepted_ref(engine, node, w: tuple, execution) -> tuple[str | None, str | None]:
    """(what to merge of a DONE node's branch, why nothing) — the commit its PASS accepted, not whatever the branch
    holds now: the branch is the agents' to write, and the verdict is about the result as it stood at DELIVER
    (§11.3). A branch moved since is said once; a node whose delivery named no tree joins its branch as before."""
    tree, carried = engine.accepted_delivery(node.id)
    if tree is None:
        return w[2], None
    # the commit recorded at DELIVER, if it still carries that tree; else, for a delivery recorded before commits were,
    # the newest commit of the branch that does
    sha = (carried if carried and W.git(w[0], "rev-parse", "--verify", "--quiet", f"{carried}^{{tree}}",
                                         execution=execution).stdout.strip() == tree
           else None if carried else W.accepted_commit(w[0], w[2], tree, execution=execution))
    if sha is None:
        return None, f"its branch `{w[2]}` no longer carries the tree its PASS accepted ({tree[:12]})"
    tip = W.git(w[0], "rev-parse", f"{w[2]}^{{tree}}", execution=execution).stdout.strip()
    if tip != tree and engine.say_once(f"moved:{node.id}:{tree}"):
        engine.emit_info("delegate", f"{node.id}: its branch `{w[2]}` moved after its PASS — the accepted commit "
                                     f"{sha[:12]} joins, not the branch as it stands")
    return sha, None


def join_whole(engine, agents: "AgentRegistry", task_id) -> str | None:
    """A part joins the whole when it PASSes: its delivery's branch merged `--no-ff` where its parent works. None
    when joined or nothing to join; else why not. A conflict is aborted and the branch left as it is: the whole's
    integration is the whole's work (§8.7, the glue), and the parent's packet names the branch (`_enter_workspace`)."""
    t = engine.graph.get_task(TaskId(task_id))
    w = _workspace(engine, agents, t) if t is not None and t.state == State.DONE else None
    if w is None or not _has_branch(w, execution_of(engine, agents)):
        return None
    parent = engine.graph.get_parent(t.id)
    # …WHERE ITS WHOLE WILL WORK, made now if the whole's session has not started yet: joined straight into the base,
    # the parts stood in the user's tree before any seam passed the whole — a whole that then failed left them there,
    # and a NOT DONE row scored work no root verdict covered (critic r5, 2026-10-04)
    if parent is not None and (pw := _workspace(engine, agents, parent)) is not None and same_place(pw[0], w[0]):
        _ensure_place(engine, agents, parent, pw)
    if (into := _where_it_joins(engine, agents, t, w)) is None:
        return None
    ex = execution_of(engine, agents)
    ref, why = _accepted_ref(engine, t, w, ex)
    if ref is None:         # the accepted work is gone from its branch: nothing to merge, and nobody is told to
        why = f"{why} - {NOT_ON_ITS_BRANCH}: DO NOT merge that branch; its work has to be delivered again (reopen it)"
        if engine.say_once(f"lost:{t.id}:{generation_of_task(t)}"):
            engine.emit_info("delegate", f"{t.id}: PASSED, and {why}")
        return why
    if parent is not None:
        _before_a_part_joins(engine, parent, w[0], into, ex)
    why = W.merge(w[0], into, ref, f"gfso: {t.id} joins {parent.id if parent else 'the base'}", execution=ex)
    if why and engine.say_once(f"unjoined:{t.id}:{generation_of_task(t)}"):
        engine.emit_info("delegate", f"{t.id}: PASSED, and its branch `{w[2]}` did not join {into} ({why}) - "
                                     f"{'' if why == W.MERGE_STANDS else 'the merge was aborted and '}the branch stands unmerged; integrating it is the work "
                                     f"of {'`' + str(parent.id) + '`, whose packet names it' if parent else 'its owner'}")
    return why


def held_off_the_host(engine, ex):
    """`ex`, unless it is this host for a project whose places stand in volumes: a role lost after the gate gave the reading that binds
    work there the user's machine — its validation, or the system's git making a place in the user's own repository (critic)."""
    if isinstance(ex, LocalExecution) and engine.graph.setting(VOLUME + "places"):
        raise PlaceUnavailable(THIS_HOST, "this project's places stand in volumes and none of its roles declares their execution now: register them back")
    return ex


def _ensure_place(engine, agents: "AgentRegistry", task, w: tuple) -> None:
    """The node's place, made if absent from where its whole works — that place made first, up the tree: cut from the
    base while its whole had none, a place missed what had already joined the whole (critic r6, 2026-10-04: a part
    covering its whole's Dep started without the producer that had joined the grandparent)."""
    parent = engine.graph.get_parent(task.id)
    if parent is not None and (pw := _workspace(engine, agents, parent)) is not None and pw[2] != w[2] \
            and same_place(pw[0], w[0]):
        _ensure_place(engine, agents, parent, pw)
    W.ensure(w[0], w[1], w[2], _where_it_joins(engine, agents, task, w) or w[0], execution=execution_of(engine, agents),
             ground=lambda: parent is not None and json.loads(engine.graph.setting(grounds_key(parent.id)) or "{}").get(str(task.id)))
    _record(engine, w[1], True)


def _enter_workspace(engine, agents: "AgentRegistry", top, members: list) -> tuple:
    """(cwd, unjoined, workspace) of a session over `members` keyed by `top`: its worktree, made when its first session
    starts from where its parent stood before its parts joined (`_before_a_part_joins`), and reused on rework;
    every DONE part and producer outside it merged in — its producers are DONE by then (Dep readiness) —, those that conflict listed for its
    packet. With no git base: the roster workdir, shared as before, and said once."""
    wd = (performer(engine, agents, top.assignee)[1] or {}).get("workdir")
    w = _workspace(engine, agents, top)
    if w is None:
        if wd and engine.say_once(f"shared-workdir:{wd}"):
            engine.emit_info("delegate", f"{wd} is not the top of a git repository with a commit, so the executors "
                                         f"registered on it share its live tree, and a validation reads it as it "
                                         f"stands, a sibling's edit included. A git base gives every node its own.")
        return wd, [], None
    base, place, branch = w
    _ensure_place(engine, agents, top, w)
    inside = {str(m.id) for m in members}
    parts, kept = parts_of(engine, members)
    unjoined = []
    for x in parts.values():
        xw = (_workspace(engine, agents, x) if x is not None and str(x.id) not in inside
              and (x.state == State.DONE or str(x.id) in kept) else None)
        if xw is None or xw[2] == branch or not same_place(xw[0], base) or not _has_branch(xw, execution_of(engine, agents)):
            continue
        ex = execution_of(engine, agents)
        ref, why = _accepted_ref(engine, x, xw, ex) if x.state == State.DONE else (xw[2], None)
        if ref is None:     # the accepted work is gone from its branch: no merge of what no PASS accepted is asked for
            if engine.say_once(f"lost:{x.id}:{why}"):
                engine.emit_info("delegate", f"{x.id}: {why} - it does not join {top.id}")
            continue
        if engine.graph.get_parent(x.id) is not None and engine.graph.get_parent(x.id).id == top.id:
            _before_a_part_joins(engine, top, base, place, ex)
        if (why := W.merge(base, place, ref, f"gfso: {x.id} joins {top.id}", execution=ex)):
            unjoined.append((str(x.id), xw[2], why, ref))   # …and the accepted commit: what it merges, held on
            try:
                W.bring(base, place, xw[2], execution=ex)    # …named in its own repository, as its packet says
            except OSError as e:                             # …not carried: the session starts, its packet says why
                unjoined[-1] = (str(x.id), xw[2], f"{why}; {e}", ref)
    return place, unjoined, w


def parts_of(engine, members: list) -> tuple[dict, dict]:
    """({id: node} whose work the members' result carries — their active children, the producers they consume, and the
    work they carry on — , {id: node} of the last alone)."""
    inside = {str(m.id) for m in members}
    parts = {str(k.id): k for m in members for k in engine.graph.get_active_children(m.id)}
    waits = engine.start_waits()   # …and those a member waits on through its whole: a cousin's work it reads
    parts.update({f: engine.graph.get_task(TaskId(f)) for m in members for f in engine.producers_awaited(m.id, waits)
                  if f not in inside})
    # …AND THE WORK OF WHAT IT REPLACES, PASSed or not: a child that replaces dropped ones started from the
    # base and redid what its dropped predecessors had committed (§12.16 (ii): the issuer's move keeps the work)
    kept = {str(x.id): x for m in members for x in engine.carried_work(m.id)}
    parts.update(kept)
    return parts, kept


def still_unjoined(engine, workspace: tuple | None, task_id, unjoined: list) -> list[str]:
    """The parts of `task_id` listed unjoined when its session began whose branch its tree still does not contain."""
    if workspace is None or not unjoined:
        return []
    mine, kept = parts_of(engine, [engine.graph.get_task(TaskId(task_id))])
    # …the parts that PASSed: a replaced node's unfinished work is offered to the whole, not owed by it
    return [x for x, _, _, ref in unjoined if x in mine and (x not in kept or mine[x].state == State.DONE)
            and not W.contains(workspace[0], workspace[1], ref, execution=execution_of(engine))]


def _unjoined_text(unjoined: list) -> str:
    """The parts whose PASSed delivery did not merge into this session's workspace — its integration to do."""
    if not unjoined:
        return ""
    return ("\n## Parts NOT joined into your workspace — integrating them is this whole's work\n"
            "Each stands on its own branch — a part that PASSed, or a node this one replaces, whose work it carries "
            "on — and did not merge here: " + ("a merge you began stands unfinished in your tree, kept as it stands — "
            "resolve and commit it first (do NOT abort it: it holds your resolutions), then merge each below. "
            if any(why == W.MERGE_STANDS for _, _, why, _ in unjoined) else
            "the system's merge was aborted, your tree is as it was. ") + "Merge each "
            "(`git merge <the commit named, else the branch>`), resolve, and deliver the integrated result. A delivery whose tree does not "
            "contain every branch below is not handed in: your result is the integration of its parts' work, and "
            "rewriting what a part already built in place of merging it loses what its seam passed.\n"
            + "".join(f"- `{x}` on branch `{b}`{'' if ref == b else f' — merge its accepted commit `{ref}`'}: {why}\n"
                      for x, b, why, ref in unjoined))


#: the roles whose sessions keep a conversation: one node's round and one scope's — two prompts, two conversations
CONVERSING_ROLES = ("executor", "scope-executor")


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
    ex.volume.carried = lambda dirs: _carried(engine, dirs)
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


def root_created(engine, agents: "AgentRegistry", root) -> None:
    """A root of the project was made: its base's import is ITS — the act of the system at the root's creation, never
    of a container's start (`Volume.import_base`). One made before any root (the project's first start) is adopted
    as it stands; one of an earlier root is made again from the user's HEAD — unless that root still works there,
    which is refused and said, or the base has no git, whose import is never written over (said)."""
    ex = execution_of(engine, agents)
    rec = json.loads(engine.graph.setting(VOLUME + IMPORTED) or "{}")
    if not isinstance(ex, ContainerExecution) or not rec or rec.get("for") == (key := root_key(engine)):
        return
    if rec.get("for") is not None:
        old = engine.graph.get_task(TaskId(rec["for"].rsplit("@", 1)[0]))
        if old is not None and root_key_of(old) == rec["for"] and old.state not in (State.DONE, State.ABANDONED):
            engine.emit_info("execution", f"{root.id}: its base was not imported again - the root {old.id} still "
                                          f"works there ({old.state.name})")
            return
        if ex.volume.import_base(ex.image, again=True):
            return
        engine.emit_info("execution", f"{root.id}: its base has no git and was imported once - it works on that base "
                                      f"as the earlier root left it")
    engine.graph.store_setting(VOLUME + IMPORTED, json.dumps({**rec, "for": key}))


def root_key_of(root) -> str:
    """A root as its base's import is keyed: its id and its making — a root made again under the id is another."""
    return f"{root.id}@{root.created_at.isoformat()}"


LANDED = "landed"   # where the accepted result lies, kept for whoever reads the graph: {branch, sha, path} or {path}


def land_accepted(engine, agents: "AgentRegistry", root) -> str | None:
    """At the root's PASS, its result where the user reads it — why not, else None. Under a container execution the
    base is the project's import, and its HEAD, the root joined, lands in the user's repository as the branch
    `gfso/<project>/accepted` (`W.land`), the LFS objects its new pointers name written into their LFS store
    (`W.land_lfs`) — a file whose object could not be carried, said: never their working tree nor their branches; a
    base with no git lands its tree in `<parent>/.gfso-accepted-<base>/<project>/` beside it. On this host the base
    IS the user's repository: nothing to land."""
    ex = execution_of(engine, agents)
    if not isinstance(ex, ContainerExecution):
        return None
    rec = json.loads(engine.graph.setting(VOLUME + IMPORTED) or "{}")
    if rec.get("commit") == "tree":
        to = ex.parent / f".gfso-accepted-{ex.base.name}" / ex.project_name
        try:
            notes = ex.volume.land_tree(ex.image, to)
        except OSError as e:
            return f"its accepted result did not land in {to}: {e}"
        engine.graph.store_setting(LANDED, json.dumps({"path": str(to)}))
        engine.emit_info("landed", f"{root.id}: its accepted result is in {to}"
                                     + (f" (not written as it stood: {'; '.join(notes[:5])})" if notes else ""))
        return None
    ref = f"gfso/{ex.project_name}/accepted"
    try:
        sha = W.land(ex.base, f"refs/heads/{ref}", ex, rec.get("commit"), engine.accepted_delivery(root.id)[0])
    except OSError as e:
        return f"its accepted result did not land in {ex.base} as branch `{ref}`: {e}"
    try:
        lost = W.land_lfs(ex.base, sha, rec.get("commit"), ex)
    except OSError as e:
        lost = [f"(its LFS pointers could not be read: {e})"]
    engine.graph.store_setting(LANDED, json.dumps({"branch": ref, "sha": sha, "path": str(ex.base)}))
    engine.emit_info("landed", f"{root.id}: its accepted result {sha[:12]} is on branch `{ref}` of {ex.base}" + (
        f"; {len(lost)} files tracked by Git LFS have no object carried into its LFS store and read as pointers there "
        f"({', '.join(lost[:5])}{', ...' if len(lost) > 5 else ''})" if lost else ""))
    return None


def node_temp(engine, task) -> str:
    """The temp of the place `task`'s sessions work in (`ExecutionPort.temp_of`) — where the system lays what they
    are to read, and no other node's session holds; the place as a session finds it NOW: its own once made, else the
    roster's workdir (`node_workspace`) — a parent's consent runs before its own executor made its place (critic over
    the node temps: its inputs went where its session could not reach)."""
    if task is None:
        return execution_of(engine).temp_of(None)
    agents = AgentRegistry()
    here = node_workspace(engine, agents, task.id) or (performer(engine, agents, task.assignee)[1] or {}).get("workdir")
    return execution_of(engine, agents).temp_of(here)


def drop_execution(project: str) -> None:
    """The project is gone: its containers go, and the objects that held them, and every volume of it by its label
    (`drop_volumes`) — the one removal of its places, its roster read or not."""
    for key in [k for k in _EXECUTIONS.copy() if k[1] == project]:   # …a copy: other threads make executions
        if not (ex := _EXECUTIONS.pop(key, None)):
            continue
        ex.stop()
        hold_places(ex.files, False)
    drop_volumes(project)
    forget(project)


def project_llm(engine, model: str, agents: "AgentRegistry | None" = None):
    """The model a session of this project runs on, started where the project's work runs: held at this one reading to what the gate holds a
    start to. The roster read again after the gate, a place's making later, and a role just taken by another project's registration moved the
    session onto the user's machine, under `off`, reaching the internet and the server's door, on no record (critic, ran)."""
    ex = execution_of(engine, agents)
    if why := ex.agents_refused():
        raise PlaceUnavailable(THIS_HOST, why)
    return llm_factory(model, execution=ex)


def session_key(*parts) -> str:
    """The id of ONE conversation per (project, node — its first issue, so a later goal reusing the id is another —,
    its executor, the role's session): a round cut at its turn cap is continued by the next one instead of starting
    from zero — measured on three sql_database rows (haiku 4.5, 2026-10-21), 9 of 56 executor sessions ended at the cap
    mid-work. Every other round starts clean (the provider forgets the rest). A new Del is a new conversation."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "gfso:" + "/".join(map(str, parts))))


def conversation_of(engine, task_id, executor_id, role: str) -> str:
    """The conversation a role's session on this node continues: keyed by the node's FIRST issue as well as its id, so
    a later goal in the same project reusing the id (a root that never passed keeps its transcripts) is another."""
    first = next((e.timestamp for e in engine.audit_log(task_id) if e.signal == Signal.ASSIGN and not e.rejected), "")
    return session_key(engine.project_name, task_id, first, executor_id, role)


def clear_workspaces(engine, agents: "AgentRegistry", root) -> None:
    """At the root's PASS every joined part is in the base: its worktree, branch and executor's conversation go (a node's tree is a whole
    checkout, so kept they cost the base's size each), and what did not join stays where it is, named."""
    left, seen, llm = [], set(), llm_factory(MODEL_DEFAULT, execution=where_it_runs(engine, agents))   # its conversations live where it ran
    for t in engine.all_tasks():
        for role in CONVERSING_ROLES:          # the work its conversations served is settled
            llm.forget(conversation_of(engine, t.id, t.assignee, role))
        w = _workspace(engine, agents, t)
        if w is None or w[2] in seen or not made(engine, w[1]):
            continue
        seen.add(w[2])
        ex = execution_of(engine, agents)
        if not (W.settled(*w, execution=ex) and W.remove(*w, execution=ex)):
            left.append(f"{w[1]} (`{w[2]}`)")
        else:
            _record(engine, w[1], False)
    where_it_runs(engine, agents).stop()        # the goal is settled: its project's container goes too
    if left:
        engine.emit_info("delegate", f"{root.id}: DONE - node workspaces not joined into the base are kept: "
                                     f"{'; '.join(left)}")
