"""Where a node's work stands: the scope one executor's session carries it in (`session_scope`), the node's own git
workspace derived from its executor's roster place (`node_workspace`), entering it, joining its PASSed parts into the
whole (`join_whole`), and clearing them at the root's PASS (`clear_workspaces`). Derived, never stored — save which
places were made (`made`)."""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import uuid
from pathlib import Path
from gfso import store
from gfso.adapters import worktrees as W
from gfso.adapters.snapshots import Uncopied
from gfso.adapters.worktrees import base_of
from gfso.adapters.netrecord import forget
from gfso.adapters.execution import (IMPORTED, ContainerExecution, LocalExecution, component, node_key, drop_volumes,
                                     held_as_tree, network_of, scratch_of, stricter)
from gfso.config import DEFAULT_PROJECT, MODEL_DEFAULT, data_dir, executions
from gfso.llm import llm_factory
from gfso.places import cheap_to_ask, same_place
from gfso.core.graph.model import LANDED, generation_of_task, grounds_key, root_of
from gfso.core.types import HOST, MADE, NODES, SCRATCH, THIS_HOST, VOLUME, PlaceUnavailable, Signal, TaskId, State, base_named, base_of_nodes, hold_places, nodes_root, PLACES
from gfso.core.protocol.procedure import round_of
from gfso.engine.findings import record_round
from gfso.engine.joins import NOT_ON_ITS_BRANCH
from gfso.engine.validation import delivered_repository, hands_of
from gfso.roster import AgentRegistry


def performer(engine, agents: "AgentRegistry", party) -> tuple:
    """(id, roster entry) of the executor whose session performs `party`'s nodes: a registered role itself, the
    standing agent's hands where its mode dispatches (`validation.hands_of`) — else (None, None), a party that performs
    in its own chat, or a person."""
    if (cfg := agents.get(str(party or ""))) is not None:
        return str(party), cfg
    h = hands_of(engine.graph, party)
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
    role = (performer(engine, agents, task.assignee)[1] or {}) if task is not None else {}
    base = role.get("workdir")
    if not base:
        return None
    key, proj = node_key((session_scope(engine, agents, task) or task).id), component(engine.project_name or DEFAULT_PROJECT)
    place = nodes_root(base) / proj / key
    # …a host place made beside its base before the places moved into the installation's own state goes on where it
    # stands (a stat, no subprocess); a role whose execution is declared works in a volume, where its place is a name
    # (`made` reads its record by the old one) and what stands beside the base is no place of it (critic)
    if not role.get("execution") and (old := _laid_out_before(place)) != place and HOST.is_dir(str(old)):
        place = old
    return base, str(place), f"gfso/{proj}/{key}"



#: the places this process asked about where the record had none, and found not made (`made`)
_UNMADE: set = set()


def made(engine, place: str) -> bool:
    """Was `place` made? THE SYSTEM'S RECORD, not the file system: `_ensure_place` adds a place it made,
    `clear_workspaces` drops one it removed, kept with the project's settings (a restart reads it) and read with no subprocess — the
    transition bus asks it. A place may stand nowhere on this host, and what stands where an agent writes decides
    nothing of the protocol."""
    if (got := engine.graph.setting(MADE + place)) is not None or (
            got := engine.graph.setting(MADE + _spelled(place))) is not None or (   # …as a copy-in carried it
            got := engine.graph.setting(MADE + _named_as_before(place))) is not None or (
            got := engine.graph.setting(MADE + str(_laid_out_before(place)))) is not None:   # …recorded beside its base
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


def _laid_out_before(place) -> Path:
    """A place under the installation's places (`nodes_root`) as it was named beside its base before 2026-11-15: the
    record of a project made then keys its places so; any other path as it is."""
    p = Path(place)
    nodes = next((a for a in p.parents if a.name.startswith(NODES)), None)
    if nodes is None or nodes.parent.parent.name != PLACES:
        return p
    return base_of_nodes(nodes).parent / nodes.name / p.relative_to(nodes)


def _laid_out_now(place) -> str:
    """A place or round laid out beside its base before 2026-11-15, as it is named now under the installation's places
    (`nodes_root`) — `_laid_out_before` read the other way; any other path as it is."""
    p = Path(place)
    nodes = next((a for a in p.parents if a.name.startswith(NODES)), None)
    if nodes is None or nodes.parent.parent.name == PLACES:
        return str(p)
    return str(nodes_root(base_of_nodes(nodes)) / p.relative_to(nodes))


def _spelled(place) -> str:
    """One spelling of a place, whichever it arrived in — what a copy-in records it by (`_carried`)."""
    return os.path.normcase(os.path.abspath(place))


def _carried(engine, dirs) -> None:
    """The places and rounds a copy-in carried into the project's volume, recorded as made — before their host copy
    is consumed, which the record of places made before it was kept fell back on (`made`, `round_stands`)."""
    for d in map(_laid_out_now, dirs):        # …carried in from beside the base, recorded by the names they now stand by
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


def _where_it_joins(engine, agents: "AgentRegistry", task, w: tuple | None) -> str | None:
    """Where the node's result joins the whole: its parent's workspace in the same repository once the parent has
    one, else the base. None inside its own scope, whose place is the parent's too, and for a node with no place
    (`w` None, its holder's own tree) whose whole has none either."""
    parent = engine.graph.get_parent(task.id)
    pw = _workspace(engine, agents, parent) if parent is not None else None
    if pw is not None and w is not None and pw[2] == w[2]:
        return None
    if pw is not None and (w is None or same_place(pw[0], w[0])) and made(engine, pw[1]):
        return pw[1]
    return w[0] if w is not None else None


def _work_of(engine, agents: "AgentRegistry", node, ex) -> tuple | None:
    """(repository, commit or branch, its name there) of a node's delivered work, WHATEVER PERFORMED IT — what every
    join, merge and naming of a node's result reads. A DONE node whose DELIVER recorded a commit: THAT COMMIT BY ITS ID,
    read from the project's store where it is joined (`join_whole`, `store.give`) — whatever became of its place, its
    branch or the person's directory —, in the repository its work is of: its base for a place of the system's, the
    repository its DELIVER logged (`Engine.accepted_repository`) or the project's for one its holder performed. A node
    with a place of the system's not DONE, or DONE before commits were recorded: its branch in the base (a replaced
    node's work carried on; `_accepted_ref`). None: nothing delivered to join; (repository or None, None, why): its
    accepted work is not there to join."""
    w, sha = _workspace(engine, agents, node), node.state == State.DONE and engine.accepted_delivery(node.id)[1]
    if w is not None and sha:
        ref, why = _accepted_ref(engine, node, w, ex)
        return w[0], ref, (w[2] if ref else why)
    if w is not None:

        if not _has_branch(w, ex):
            return None
        ref, why = _accepted_ref(engine, node, w, ex) if node.state == State.DONE else (w[2], None)
        return w[0], ref, (w[2] if ref else why)
    if not sha:
        return None
    return engine.accepted_repository(node.id) or engine.graph.setting(REPOSITORY), sha, sha


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
    # the commit recorded at DELIVER, read by its id into the base (`_given`) where it still carries that tree; for a
    # delivery recorded before commits were, the newest commit of the branch that does
    if carried and W.git(w[0], "cat-file", "-e", f"{carried}^{{commit}}", execution=execution).returncode and (
            why := _given(engine, carried, w[0], execution)):
        return None, why
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
    integration is the whole's work (§8.7, the glue), and the parent's packet names the branch (`_enter_workspace`).
    ONE RULE, whatever performed the node (`_work_of`): its delivered commit joins its whole's place of the system's;
    a whole with none — its holder's own tree — is named every part to merge (`left_to_merge`); and a root's result
    lands as a branch of the user's (`land_accepted`). On this host no merge of the system's writes the user's
    repository itself — their checked-out branch, its index or its tree."""
    t = engine.graph.get_task(TaskId(task_id))
    if t is None or t.state != State.DONE:
        return None
    parent, ex = engine.graph.get_parent(t.id), execution_of(engine, agents)
    w, pw = _workspace(engine, agents, t), _workspace(engine, agents, parent) if parent is not None else None
    if (work := _work_of(engine, agents, t, ex)) is None:
        return None
    base, ref, name = work
    # …WHERE ITS WHOLE WILL WORK, made now if the whole's session has not started yet: joined straight into the base,
    # the parts stood in the user's tree before any seam passed the whole — a whole that then failed left them there,
    # and a NOT DONE row scored work no root verdict covered (critic r5, 2026-10-04)
    if over := pw is not None and base is not None and same_place(pw[0], base):
        _ensure_place(engine, agents, parent, pw)
    # …a holder's own work joins only a place over the repository it was recorded in; anywhere else it is named
    if (into := _where_it_joins(engine, agents, t, w)) is None or w is None and not over:
        return None
    if ref is None:         # the accepted work is gone from its branch: nothing to merge, and nobody is told to
        why = f"{name} - {NOT_ON_ITS_BRANCH}: DO NOT merge that branch; its work has to be delivered again (reopen it)"
        if engine.say_once(f"lost:{t.id}:{generation_of_task(t)}"):
            engine.emit_info("delegate", f"{t.id}: PASSED, and {why}")
        return why
    if not isinstance(ex, ContainerExecution) and same_place(into, base):
        return None             # …the user's repository: a root lands (`land_accepted`), a part is named (`left_to_merge`)
    if parent is not None:
        _before_a_part_joins(engine, parent, base, into, ex)
    why = _given(engine, ref, into, ex) or W.merge(base, into, ref, f"gfso: {t.id} joins {parent.id if parent else 'the base'}",
                                                   execution=ex)
    if parent is not None:
        # …joined: the base's HEAD for the chat; refused by a conflict: the part's own branch, which the whole is told
        # to merge (critic: named, it stood only in the volume)
        why = (_to_the_chat(engine, agents, parent, ex) if not why else
               _to_the_chat(engine, agents, parent, ex, ref, name) or why)
    if why and engine.say_once(f"unjoined:{t.id}:{generation_of_task(t)}"):
        engine.emit_info("delegate", f"{t.id}: PASSED, and its branch `{name}` did not join {into} ({why}) - "
                                     f"{'' if why == W.MERGE_STANDS else 'the merge was aborted and '}the branch stands unmerged; integrating it is the work "
                                     f"of {'`' + str(parent.id) + '`, whose packet names it' if parent else 'its owner'}")
    return why


def left_to_merge(engine, agents: "AgentRegistry", whole) -> list[tuple[str, str]]:
    """[(part, why)] — `join_whole`'s rule where the system merges nothing: ON THIS HOST THE BASE IS THE USER'S
    REPOSITORY, and a passed part whose whole has no place of the system's over the repository its work is in —
    performed in its holder's own tree, or over another repository — is named for that whole to merge, whatever
    performed the part (`_work_of`), while the tree the whole is performed in lacks its commit — with no place for the
    whole, the part's own repository: no tree is guessed for it. A part a chat delivered is named under a container
    execution too: its commit is where its DELIVER recorded it, on this host. Derived from the record
    and git, never held in memory: a process started since names them as the one that passed them did (critic: a
    restart told the holder to aggregate with no part named)."""
    # …asked by the frontier: read without starting any execution — this host's git over what a chat's DELIVER recorded
    # here, the same under either execution; a place of the system's in a volume joins there (`join_whole`)
    ex, pw, out = LocalExecution(), _workspace(engine, agents, whole), []
    held_off = declaring_role(engine, agents) is not None or bool(engine.graph.setting(VOLUME + "places"))
    if held_off and pw is not None:
        return []
    for k in engine.graph.get_active_children(whole.id):
        if held_off and _workspace(engine, agents, k) is not None or (work := _work_of(engine, agents, k, ex)) is None:
            continue
        base, ref, name = work
        if pw is not None and base is not None and same_place(pw[0], base):
            continue                    # …joined where the whole works (`join_whole`), or said there
        # …the tree the whole is performed in: its place's repository, else the part's own while it stands, else the
        # project's — a part's removed clone leaves its commit in the store alone
        there = pw[0] if pw is not None else base if base and Path(base).is_dir() else repository(engine, agents)
        if ref is None:
            out.append((str(k.id), f"{name} - {NOT_ON_ITS_BRANCH}: nothing of it to merge; it has to be delivered again (reopen it)"))
        # …while the tree the whole works in lacks it: once merged there it is named no more (a whole over another
        # repository was told to merge a part it already had, its AGGREGATE repeating it; an object that repository
        # does not hold yet is not its ancestor either)
        elif there and W.git(there, "merge-base", "--is-ancestor", ref, "HEAD", execution=ex).returncode:
            # …its objects given there by its id from the project's store: the whole's tree reads it whatever became
            # of the part's own place
            out.append((str(k.id), _given(engine, ref, there, None) or (
                f"the system merges nothing into {there}, the user's own repository: its accepted commit {ref}"
                + (f", on `{name}` where it was made, is there" if name != ref else " is there")
                + f" - merge it where {whole.id} is performed (`git merge {ref}`)")))
    return out


def _given(engine, commit: str, place, at) -> str | None:
    """`commit` read by its id into the git at `place` from the project's store (`store.give`) — why not, else None:
    a delivery is the system's from DELIVER on, read where it is joined whatever became of the place it was made in.
    `at`: the execution `place`'s git runs in, None for a person's repository on this host."""
    try:
        store.give(engine, execution_of(engine), commit, place, at)
    except (OSError, subprocess.TimeoutExpired, store.Absent) as e:
        return f"its accepted commit {commit[:12]} could not be read from the project's store into {place}: {e}"
    return None


def standing(engine, task_id, place) -> tuple:
    """(tree, commit, None) a reader of a row with nothing delivered reads by id — a contact on a BLOCK or CHALLENGE,
    the observation before a session: a place of the system's committed whole first (`W.commit_all`, as each
    of its deliveries is), so the files its executor left are read; a chat's tree at its HEAD, what stands uncommitted
    named as no part of it. Said on the feed — what was read, by its id —; its reader keeps it (`held`). `Uncopied`
    where no commit can be read there: no copy, never the directory as it stands. A place of the system's is known by
    the system's own name of it (a node's place under its base's places, or any place of a container's), read where it
    runs (`W.git`), never by this host's git."""
    ex = execution_of(engine)
    try:
        if isinstance(ex, ContainerExecution) or W.base_of(str(place)):
            # …only where something stands uncommitted: an empty commit each session moved the node's branch for nothing
            # …in the place alone, carried nowhere: what is read is kept by its id (`store.held`), not by a branch
            if W.git(place, "status", "--porcelain", execution=ex).stdout.strip():
                W.commit_all(W.base_of(str(place)) or str(place), place, f"gfso: {task_id} as it stood when read",
                             "gfso", execution=ex)
            tree, commit, left = (W.git(place, "rev-parse", "HEAD^{tree}", execution=ex).stdout.strip(),
                                  W.head(place, execution=ex), [])
        else:
            tree, commit, left = W.read_head(place)
    except (OSError, W.NotStaged) as e:
        raise Uncopied(f"{place} holds no commit to read: {e}") from e
    if not commit:
        raise Uncopied(f"{place} holds no commit to read")
    engine.emit_info(
"delivery", f"{task_id}: read at {commit[:12]}, {place} as it stood, nothing delivered"
                                 + (f"; not committed, so not read: {', '.join(left[:10])}" if left else ""))
    return tree, commit, None


#: what keys, in a project's settings, its repository (`store.REPOSITORY`)
REPOSITORY = store.REPOSITORY


#: how the person's agent lifts a directory with no git (`no_repository`) — the ignores are theirs to choose
MAKE_IT_ONE = ("make it a git repository and commit what is the work (`git init`, a `.gitignore` for what is not — "
               "builds, caches, secrets —, `git add -A`, `git commit -m start`), then name it again")


def no_repository(place, executor: bool) -> str | None:
    """Why `place`, a directory a role works in on this host, gives no delivery a commit to be judged by — or None. With
    no git at all: the system never makes the person's directory a repository nor commits it blindly (the author,
    2026-11-03: the repository is made by default or the person's agent prepares it), so it is refused with its lift.
    An executor's below a work tree's top too: no place of its own is cut from it, its sessions share the live tree,
    and no verdict could come — refused before a session is paid for. A judge there stands in that directory of the
    commit (`snapshots.judged_at`)."""
    p = Path(place)
    if not cheap_to_ask(place) or not p.is_dir():
        return None                       # …unread, or not made yet: said where it is made
    top = W.git(p, "rev-parse", "--show-toplevel").stdout.strip()
    if not top:
        return f"{place} is no git repository: {MAKE_IT_ONE}"
    if executor and not W.is_repo_top(place):
        return (f"{place} is inside the work tree {top}, not its top: an executor works at the top of a repository "
                f"with a commit — register it at {top}" + ("" if W.is_repo_top(top) else f", once {MAKE_IT_ONE}"))
    return None


def unjudged(engine, agents: "AgentRegistry") -> list[tuple]:
    """[(role, why)] of the project's roles whose directory `no_repository` refuses — a role registered before such a
    directory was refused: refused at the go, named by the one-time migration (`store.migrate`)."""
    return [(aid, why) for aid, c in agents.list().items() if c.get("project") == engine.project_name and c.get("workdir")
            and (why := no_repository(c["workdir"], executor=c.get("kind") == "llm-executor" and not c.get("execution")))]


def record_repository(engine, place) -> bool:
    """The project's repository recorded once (`REPOSITORY`): the one `place` is a work tree of, where it is a
    repository's top with a commit and none is recorded yet. Whether one stands recorded now. Tree or no tree is the
    PROJECT's record, never a sender's registration: a chat that registered nowhere delivered no commit, and its judge
    read a directory as it stood. The system never makes a repository of the person's directory: one with no git is
    refused where it is named (`no_repository`), the person's agent making it one."""
    if not engine.graph.setting(REPOSITORY) and place and W.is_repo_top(place):
        engine.graph.store_setting(REPOSITORY, W.main_worktree(place))
    return bool(engine.graph.setting(REPOSITORY))


def repository(engine, agents: "AgentRegistry") -> str | None:
    """The project's repository: recorded at its first role's registration over it — else derived once, for a project
    made before the record, from what its record names: its volume's base, its roles' workdirs, the repositories its
    chats' ACCEPT and DELIVER logged, the first a repository's top. None: none names one."""
    if not (got := engine.graph.setting(REPOSITORY)):
        named = (engine.graph.setting(VOLUME + "base"),
                 *(c.get("workdir") for c in agents.list().values() if c.get("project") == engine.project_name),
                 *(e.repository for e in engine.audit_log() if e.repository))
        any(record_repository(engine, p) for p in named)
        got = engine.graph.setting(REPOSITORY)
    return got or None


def joined_ref(engine, whole) -> str:
    """The branch of the user's repository a whole performed in its chat finds its joined parts on."""
    return f"gfso/{component(engine.project_name or DEFAULT_PROJECT)}/joined/{node_key(whole.id)}"


def _to_the_chat(engine, agents: "AgentRegistry", whole, ex, rev: str = "HEAD", branch: str | None = None) -> str | None:
    """A part joined the base in the volume under a whole its holder performs in its own chat, in the user's
    repository: the base's HEAD, its parts in, lands there as the branch `joined_ref` (`W.land`) for the chat to merge
    as its integration — or, `branch`, a part's own `rev` its join refused, as that branch — no working tree nor branch
    of theirs written. Why not, else None; nothing where the whole's session is the system's or the base is the user's
    repository itself."""
    if not isinstance(ex, ContainerExecution) or performer(engine, agents, whole.assignee)[0] is not None:
        return None
    ref = branch or joined_ref(engine, whole)
    try:
        sha = W.land(ex.base, f"refs/heads/{ref}", ex, json.loads(engine.graph.setting(VOLUME + IMPORTED) or "{}").get("commit"),
                     rev=rev)
    except OSError as e:
        return f"its joined work did not land in {ex.base} as branch `{ref}`: {e}"
    what = "a part that did not join is" if branch else "its parts joined so far are"
    engine.emit_info("landed", f"{whole.id}: {what} on branch `{ref}` ({sha[:12]}) of {ex.base} - "
                               f"written by unattended sessions: read it before you run any of it here, then merge it "
                               f"into your tree (`git merge {ref}`) before you deliver {whole.id}")
    return None


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
    ex = execution_of(engine, agents)
    W.ensure(w[0], w[1], w[2], _where_it_joins(engine, agents, task, w) or w[0], execution=ex,
             ground=lambda: _had(engine, task, w, ex) or parent is not None and json.loads(
                 engine.graph.setting(grounds_key(parent.id)) or "{}").get(str(task.id)))
    _record(engine, w[1], True)


def _had(engine, task, w: tuple, ex) -> str | None:
    """The work a node had, for a place made again once its branch went — with the clearing at the root's PASS, or by
    the person's hand —: its last delivery's commit, read BY ITS ID from the project's store into the base (a rework,
    a REOPEN). A reopen re-earns the verdict over that work (§12.14); started from its whole's ground, or the user's
    HEAD for a root on this host, a reopened root dropped its parts' work and the poorer result passed and moved the
    accepted branch (critic). Asked by `W.ensure` only where the branch is gone; None where nothing gives it back."""
    sha = next((e.commit for e in reversed(engine.audit_log(task.id))
                if e.signal == Signal.DELIVER and not e.rejected and e.commit), None)
    return sha if sha and _given(engine, sha, w[0], ex) is None else None

def _enter_workspace(engine, agents: "AgentRegistry", top, members: list) -> tuple:
    """(cwd, unjoined, workspace) of a session over `members` keyed by `top`: its worktree, made when its first session
    starts from where its parent stood before its parts joined (`_before_a_part_joins`), and reused on rework;
    every DONE part and producer outside it merged in — its producers are DONE by then (Dep readiness) —, those that conflict listed for its
    packet. With no git base — a project made before such a base was refused (`no_repository`) —: the roster workdir,
    shared as before, and said once; no delivery from it gets a verdict."""
    wd = (performer(engine, agents, top.assignee)[1] or {}).get("workdir")
    w = _workspace(engine, agents, top)
    if w is None:
        if wd and engine.say_once(f"shared-workdir:{wd}"):
            engine.emit_info("delegate", f"{wd} is not the top of a git repository with a commit, so the executors "
                                         f"registered on it share its live tree, and no judge reads a directory as it "
                                         f"stands: its deliveries get no verdict. A git base gives every node its own.")
        return wd, [], None
    base, place, branch = w
    _ensure_place(engine, agents, top, w)
    inside = {str(m.id) for m in members}
    parts, kept = parts_of(engine, members)
    unjoined = []
    ex = execution_of(engine, agents)
    for x in parts.values():
        if x is None or str(x.id) in inside or not (x.state == State.DONE or str(x.id) in kept):
            continue
        xw = _workspace(engine, agents, x)
        if xw is not None and xw[2] == branch or (work := _work_of(engine, agents, x, ex)) is None \
                or not (work[0] and same_place(work[0], base)):
            continue
        _, ref, name = work
        if ref is None:     # the accepted work is gone from its branch: no merge of what no PASS accepted is asked for
            if engine.say_once(f"lost:{x.id}:{name}"):
                engine.emit_info("delegate", f"{x.id}: {name} - it does not join {top.id}")
            continue
        if engine.graph.get_parent(x.id) is not None and engine.graph.get_parent(x.id).id == top.id:
            _before_a_part_joins(engine, top, base, place, ex)
        if (why := W.merge(base, place, ref, f"gfso: {x.id} joins {top.id}", execution=ex)):
            unjoined.append((str(x.id), name, why, ref))    # …and the accepted commit: what it merges, held on
            try:                                             # …a branch named in its own repository, as its packet says;
                if xw is not None:                           # a holder's recorded commit its objects already reach
                    W.bring(base, place, name, execution=ex)
            except OSError as e:                             # …not carried: the session starts, its packet says why
                unjoined[-1] = (str(x.id), name, f"{why}; {e}", ref)
    return place, unjoined, w


def parts_not_there(engine, agents: "AgentRegistry", members: list, place) -> list[tuple]:
    """[(part, [files], from, to, {file: the commit that changed it last})] — the accepted parts joined into `place` whose own change is no longer all there in its tree:
    each part's delivery from where its join met the whole to its accepted commit (`W.change_not_there`). A merge lost
    a part's code, and it surfaced only at the whole's validation, a round later (GB_c_compiler_toccc3884). Read-only."""
    ex, out, inside = execution_of(engine, agents), [], {str(m.id) for m in members}
    if not place or (mw := _workspace(engine, agents, members[0])) is None:
        return []
    # …the joins in the place's history: {part's commit: the whole's commit it was merged onto}
    onto = {p[1]: p[0] for ln in W.git(place, "log", "--merges", "--format=%P", "HEAD", execution=ex).stdout.splitlines()
            if len(p := ln.split()) >= 2}
    for x in parts_of(engine, members)[0].values():
        if x is None or str(x.id) in inside or x.state != State.DONE \
                or (work := _work_of(engine, agents, x, ex)) is None or work[1] is None \
                or not same_place(work[0], mw[0]):
            continue
        # …named in the base, as its join named it (`W.merge`): the place's own repository holds no other node's branch
        sha = W.git(work[0], "rev-parse", "--verify", "--quiet", f"{work[1]}^{{commit}}", execution=ex).stdout.strip()
        if sha not in onto:
            continue                                # …not joined here: an unjoined part's packet section says so
        met = W.git(place, "merge-base", onto[sha], sha, execution=ex).stdout.strip()
        if files := W.change_not_there(place, met, sha, execution=ex):
            # …and what changed each last: a later part's legitimate edit and a lost merge read alike (critic); along the
            # join's ancestry, else git's simplification drops the very merge that kept the whole's side
            by = {f: W.git(place, "--literal-pathspecs", "log", "-1", "--ancestry-path", "--format=%h %s", f"{sha}..HEAD", "--", f,
                           execution=ex).stdout.strip() for f in files}
            out.append((str(x.id), files, met, sha, by))
    return out


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


def land_accepted(engine, agents: "AgentRegistry", root) -> str | None:
    """At the root's PASS, its result where the user reads it — why not, else None. Under a container execution the
    base is the project's import, and its HEAD, the root joined, lands in the user's repository as the branch
    `gfso/<project>/accepted` (`W.land`), the LFS objects its new pointers name written into their LFS store
    (`W.land_lfs`) — a file whose object could not be carried, said: never their working tree nor their branches; a
    base with no git lands its tree in `<parent>/.gfso-accepted-<base>/<project>/` beside it. On this host the base
    IS the user's repository, and the root worked in a place of the system's (`_land_from_its_place`)."""
    ex = execution_of(engine, agents)
    if not isinstance(ex, ContainerExecution):
        return _land_from_its_place(engine, agents, root, ex)
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
    if (said := _name_the_delivery(engine, root)) is not False:
        return said         # …the base's HEAD holds only its parts
    ref, (tree, sha) = accepted_branch(engine), engine.accepted_delivery(root.id)
    # …the commit its PASS accepted, by its id: the base's HEAD is the root session's to move after it
    if sha and (why := _given(engine, sha, ex.base, ex)):
        return why
    try:
        sha = W.land(ex.base, f"refs/heads/{ref}", ex, rec.get("commit"), tree, rev=sha or "HEAD")
    except OSError as e:
        return f"its accepted result did not land in {ex.base} as branch `{ref}`: {e}"
    try:
        lost = W.land_lfs(ex.base, sha, rec.get("commit"), ex)
    except OSError as e:
        lost = [f"(its LFS pointers could not be read: {e})"]
    return _landed(engine, root, ref, sha, ex.base, (
        f"; {len(lost)} files tracked by Git LFS have no object carried into its LFS store and read as pointers there "
        f"({', '.join(lost[:5])}{', ...' if len(lost) > 5 else ''})" if lost else ""))


def accepted_branch(engine) -> str:
    """The branch of the user's repository a root's accepted result lands on."""
    return f"gfso/{component(engine.project_name or DEFAULT_PROJECT)}/accepted"


def _land_from_its_place(engine, agents: "AgentRegistry", root, ex) -> str | None:
    """The root's accepted commit — in the user's repository under the root's own branch since its DELIVER
    (`W.commit_all`) — named `accepted_branch` there (`W.land`: a ref alone, the tree its PASS accepted checked), merged
    into no branch of theirs. A root held in its holder's chat has no place: the commit it delivered is named so, as
    under a container (`_name_the_delivery`); one with a commit recorded and no repository is said, never landed unsaid."""
    if (w := _workspace(engine, agents, root)) is None:
        if (said := _name_the_delivery(engine, root)) is not False:
            return said
        sha = engine.accepted_delivery(root.id)[1]
        return (f"its accepted commit {sha[:12]} was recorded before the log named its repository - {NOT_ON_ITS_BRANCH}: "
                f"reopen the root and deliver its work again" if sha else None)
    sha, why = _accepted_ref(engine, root, w, ex)
    if sha is None:
        return why
    if engine.accepted_delivery(root.id)[1] and (why := _given(engine, sha, w[0], None)):
        return why
    ref = accepted_branch(engine)
    try:
        sha = W.land(w[0], f"refs/heads/{ref}", ex, None, engine.accepted_delivery(root.id)[0], rev=sha)
    except OSError as e:
        return f"its accepted result did not land in {w[0]} as branch `{ref}`: {e}"
    return _landed(engine, root, ref, sha, w[0])


def _name_the_delivery(engine, root):
    """A root its holder performed in their own chat: what its PASS accepted is the commit its DELIVER recorded
    (`tools_llm.signal`), read BY ITS ID from the project's store into the user's repository — the one the log names
    (`Engine.accepted_repository`) — and named `accepted_branch` there by one ref, their checked-out branch
    untouched: the directory it was made in may be gone. None when named, why not, or False: no commit was recorded
    by a chat in a repository (a chat's delivery from before the log named one is said by its caller)."""
    sha, repo = engine.accepted_delivery(root.id)[1], engine.accepted_repository(root.id)
    if not (sha and repo):
        return False
    if not Path(repo).is_dir():          # …the directory it was made in removed: the project's repository holds it now
        repo = engine.graph.setting(REPOSITORY) or repo
    if not cheap_to_ask(repo) or (why := _given(engine, sha, repo, None)):
        return why or f"its accepted result {sha[:12]} cannot be read into {repo}"
    try:
        kept = W.move_result(repo, f"refs/heads/{(ref := accepted_branch(engine))}", sha)
    except W.CheckedOut as ex:
        return str(ex)
    except OSError as ex:
        return f"its accepted result {sha[:12]} could not be named `{ref}` in {repo}: {ex}"
    return _landed(engine, root, ref, sha, repo,
                   f" (the earlier result it does not contain is kept as `{kept.removeprefix('refs/heads/')}`)" if kept else "")


def _landed(engine, root, ref: str, sha: str, base, note: str = "") -> None:
    """The root's result on `ref` of the user's repository at `base`: kept for whoever reads the graph, and said."""
    engine.graph.store_setting(LANDED, json.dumps({"branch": ref, "sha": sha, "path": str(base)}))
    engine.emit_info("landed", f"{root.id}: its accepted result {sha[:12]} is on branch `{ref}` of {base}{note}")


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
    (`drop_volumes`) — the one removal of its places in volumes, its roster read or not (those on this machine go at
    the deletion's end, `drop_host_files`)."""
    for key in [k for k in _EXECUTIONS.copy() if k[1] == project]:   # …a copy: other threads make executions
        if not (ex := _EXECUTIONS.pop(key, None)):
            continue
        ex.stop()
        hold_places(ex.files, False)
    drop_volumes(project)
    forget(project)


def drop_node_branches(project: str, bases) -> list[str]:
    """A deleted project's own refs in the person's repositories — every `gfso/<project>/*` branch but `accepted`, the
    result that is theirs, and the system's `refs/gfso/<project>/*` — removed: kept, a project made again under the name
    started its nodes from the old attempt's branches (`worktrees._start`); the author, 2026-11-18: «Давай удалять, это
    разумно». The repositories: `bases` (its roles') and every base the system made a place of it beside (its record
    under `<data>/places`, which a moved or project-less role is not on). A branch checked out in a worktree is the
    person's in hand and stays; nothing here raises. The refs it removed."""
    name, gone, here = component(project or DEFAULT_PROJECT), [], LocalExecution()
    keep, places = f"refs/heads/gfso/{name}/accepted", data_dir() / PLACES
    below = lambda d: [d / x for x in here.files.listdir(str(d))] if here.files.is_dir(str(d)) else []
    made = [str(base_of_nodes(n)) for h in below(places) for n in below(h) if here.files.is_dir(str(n / name))]
    for base in {str(b) for b in [*bases, *made] if b and here.files.is_dir(str(b)) and cheap_to_ask(str(b))}:
        try:
            refs = W.git(base, "for-each-ref", "--format=%(refname) %(worktreepath)", f"refs/heads/gfso/{name}/",
                         f"refs/gfso/{name}/")
            if refs.returncode:         # …a git older than `%(worktreepath)`: nothing removed, and said
                logging.getLogger(__name__).warning(f"{base}: {name}'s node branches not read, kept: {refs.stderr.strip()}")
            for ref, *held in (r.split(" ", 1) for r in (refs.stdout.splitlines() if refs.returncode == 0 else ())):
                if ref != keep and not re.fullmatch(re.escape(keep) + r"-\d{8}T\d{6}Z", ref) and not "".join(held).strip() and W.git(base, "update-ref", "-d", ref).returncode == 0:
                    gone.append(f"{base}: {ref}")
        except (OSError, subprocess.SubprocessError):
            continue                    # …no git here, or one that hung: the deletion completes, the refs stay
    return gone


def rejected_reports_dir(project: str) -> Path:
    """Where a project's reports refused as verdicts are kept (`validate._keep_rejected_report`): under the project's
    own name, a node's id naming a node in every project."""
    return data_dir() / "rejected_verdicts" / component(project or DEFAULT_PROJECT)


def drop_host_files(project: str) -> list[str]:
    """A deleted project's files in the installation's own state: its places on this machine under every base
    (`<data>/places/<base's parent>/<base>/<project>`), its refused reports, its hand-laid probe inputs and its store
    of deliveries (`store.drop`) — a volume holds the rest. Each directory
    on its own: one a process still holds (a lock on Windows) stays, and is returned, while the rest go."""
    name, places, left, here = component(project or DEFAULT_PROJECT), data_dir() / PLACES, [], LocalExecution()
    below = lambda d: [d / x for x in here.files.listdir(str(d))] if here.files.is_dir(str(d)) else []
    ours = [b / name for h in below(places) for b in below(h) if here.files.is_dir(str(b / name))]
    for d in ours + [rejected_reports_dir(project), data_dir() / "probe_inputs" / name]:
        try:
            here.remove_tree(str(d))
        except OSError:
            left.append(str(d))
    return left + store.drop(project)


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


def _clear_what_nothing_reads(engine, ex, base) -> list:
    """At the close, with no node open and no validation running (`_clear_places`), the project's validation and contact
    rounds and its temp serve nothing: each removed, every round out of the record of the rounds standing — a finding's
    files the record kept (`findings.keep_files`) re-lay them. Kept: the base and its read copy, unjoined places, the
    sessions' state. Returns what could not be removed."""
    own, left = scratch_of(base, engine.project_name).parent, []
    if not ex.files.is_dir(str(own)):
        return left
    temp = [ex.tmp] if isinstance(ex, ContainerExecution) else []
    for d in [own / s for s in ex.files.listdir(str(own)) if s.startswith(SCRATCH)] + temp:
        try:
            for r in ex.files.listdir(str(d)) if ex.files.is_dir(str(d)) else []:
                ex.remove_tree(str(d / r))
                record_round(engine.graph, str(d / r), False)
            ex.remove_tree(str(d))
        except OSError:
            left.append(f"{d.name} (rounds and temp)")
    return left


def _remove_joined_places(engine, agents: "AgentRegistry") -> list:
    """Every node's place whose work the base holds removed, with its branch and its sessions' conversations; the
    names of those that did not join, kept."""
    left, seen, llm = [], set(), llm_factory(MODEL_DEFAULT, execution=where_it_runs(engine, agents))   # its conversations live where it ran
    for t in engine.all_tasks():
        for role in CONVERSING_ROLES:          # the work its conversations served is settled
            llm.forget(conversation_of(engine, t.id, t.assignee, role))
        w = _workspace(engine, agents, t)
        if w is None or w[2] in seen or not made(engine, w[1]):
            continue
        seen.add(w[2])
        ex = execution_of(engine, agents)
        # …on this host the root's result is a branch of the user's repository, its HEAD theirs (`_land_from_its_place`)
        acc = f"refs/heads/{accepted_branch(engine)}"
        onto = acc if not isinstance(ex, ContainerExecution) and W.git(
            w[0], "rev-parse", "--verify", "--quiet", acc, execution=ex).returncode == 0 else "HEAD"
        if not (W.settled(*w, execution=ex, onto=onto) and W.remove(*w, execution=ex, onto=onto)):
            left.append(f"{w[1]} (`{w[2]}`)")
        else:
            _record(engine, w[1], False)
    return left


def clear_workspaces(engine, agents: "AgentRegistry", root) -> None:
    """At the root's PASS every joined part is in where its result landed: its worktree, branch and executor's conversation go (a node's tree is a whole
    checkout, so kept they cost the base's size each), and what did not join stays where it is, named."""
    try:                                         # …the stop below is owed however the clearing ends (a place gone mid-way)
        left = _remove_joined_places(engine, agents)
        ex = execution_of(engine, agents)
        # …the base the root's holder works over, else the one its execution holds: a root held by the person has none
        base = at[0] if (at := _place_of(engine, agents, root)) is not None else \
            ex.base if isinstance(ex, ContainerExecution) else None
        if base is not None and (kept := _clear_what_nothing_reads(engine, ex, str(base))):
            engine.emit_info("delegate", f"{root.id}: DONE - not removed, a file in them held: {'; '.join(kept)}")
    finally:
        where_it_runs(engine, agents).stop()    # the goal is settled: its project's container goes too
    if left:
        engine.emit_info("delegate", f"{root.id}: DONE - node workspaces not joined into the base are kept: "
                                     f"{'; '.join(left)}")


#: characters of the producers' delivered files a deferred split is handed — its author reads text, not a tree
SPLIT_CONTACT_MAX = 120_000


def results_a_split_waits_on(engine, agents: "AgentRegistry", task_id) -> str:
    """What the results a deferred split waited on (`Engine.split_waits_on`) turned out to be, for the round that makes
    it: each named part's contract, its verdict criterion by criterion, and the files it wrote as its accepted delivery
    holds them — read by git at that delivery's commit in the place it was made, so a sibling mid-edit is not what is
    read. The split's author is a zero-tool completion: handed "the parser passed", it would split as blind as before
    the result came, which is what deferring was for (FM-6, §8.6). '' where the node defers nothing."""
    ex, out, room = execution_of(engine, agents), [], SPLIT_CONTACT_MAX
    for p in engine.split_waits_on(TaskId(task_id), standing=True):
        t = engine.graph.get_task(TaskId(p))
        if t is None or t.state != State.DONE:   # …a part replaced or cancelled since delivered nothing to split on
            continue
        rec = engine.get_exec_verdict(t.id) or {}
        per = "\n".join(f"- {c.get('criterion')}: {c.get('verdict')} — {str(c.get('evidence') or c.get('reason') or '')[:300]}"
                        for c in rec.get("per_criterion") or ())
        commit = next((a.commit for a in reversed(engine.audit_log(t.id))
                       if a.signal == Signal.DELIVER and not a.rejected and a.commit), None)
        files = []
        parent = engine.graph.get_parent(t.id)
        place = node_workspace(engine, agents, t.id) or (node_workspace(engine, agents, parent.id) if parent else None)
        if commit and place:
            for w in engine.seam_claim(t.id).get("writes") or ():
                listed = W.git(place, "ls-tree", "-r", "-z", "--name-only", commit, "--", str(w).rstrip("/"),
                               execution=ex)
                for path in ([x for x in listed.stdout.split(chr(0)) if x] if listed.returncode == 0 else ()):  # a name with a space
                    if room <= 0:
                        break
                    shown = W.git(place, "show", f"{commit}:{path}", execution=ex)
                    if shown.returncode == 0 and "\0" not in shown.stdout:
                        files.append(f"### {path}\n\n{shown.stdout[:room]}")
                        room -= len(files[-1])
        out.append(f"## {t.id} — {t.spec.name or t.spec.description[:80]} ({t.state.name}, verdict {rec.get('verdict')})\n"
                   + (f"Its criteria as its validator found them:\n{per}\n" if per else "")
                   + (f"Its delivery: commit {commit}\n" if commit else "")
                   + ("\n".join(files) if files else "(its files could not be read from its place)"))
        # …said where the person reads the run: that the split waited, and on what it is made
        engine.emit_info("decompose", f"{task_id}: its split is made with what {t.id} delivered — " + (
            f"{len(files)} file(s), {sum(map(len, files))} chars at {commit[:12]}" if files else
            "its verdicts only: its files could not be read from its place"))
    return ("# THE RESULTS THIS SPLIT WAITED ON — the contact that makes it definable (FM-6, §8.6)\n"
            "Split this node over what these parts actually delivered: their interfaces, files and verdicts below, "
            "not over what the plan guessed they would be. They are inputs to the split, not requirements of this node: "
            "its criteria are its contract above.\n\n" + "\n\n".join(out)) if out else ""


def _oracle_workdir(engine, vcfg: dict):
    """The workspace for this project from the issuer-side oracle map (same map the unittest-checker
    uses), so a criteria validator runs the code where the executor delivered it. None if absent."""
    project = getattr(engine, "project_name", None) or DEFAULT_PROJECT
    try:
        entry = json.loads(Path(vcfg["oracle_map"]).read_text(encoding="utf-8")).get(project)
        return entry.get("workdir") if entry else None
    except Exception:
        return None


def _children_workdir(engine, agents: AgentRegistry, task_id: TaskId) -> str | None:
    """Where this node's work actually lives: the workdir of a registered child executor.

    A parent whose own Del is the unregistered user-agent has no directory of its own, but its
    children do — and their directory is the one holding the artifact the parent aggregates."""
    for kid in engine.graph.get_active_children(task_id):
        if (wd := (agents.get(kid.assignee or "") or {}).get("workdir")):
            return wd
    return None


def validator_workdir(engine, agents: AgentRegistry, task_id: TaskId,
                    named_validator: str | None = None, vcfg: dict | None = None) -> str | None:
    """WHERE THE VALIDATOR OF THIS NODE STANDS — one answer, whichever door asked.

    There were two, and they disagreed. Probed 2026-09-07 with an executor registered against
    `WORK` and a validator against `SCRATCH`: the dispatcher sent the validator to `WORK`, a manual
    `validate_result(node, validator="val-1")` sent it to `SCRATCH`, and on a node held by an
    unregistered person the manual door sent it to `SCRATCH` even with no validator named. Three
    orders of priority for one question.

    The order below is the dispatcher's, and it is the one a run already paid for: **the graph
    before the roster**. The validator's registered directory is a roster fact; where the work IS is
    a graph fact, and only the second is true by construction (measured 2026-08-21 — a stale `val-1`
    from an older experiment pointed at a scratch directory, the root was validated there, the report
    said "no implementation exists", and a false FAIL over seventeen criteria drove the run into the
    rework loop that ended it).

    The roster is still asked, and that is the OTHER fix this keeps: a root is normally held by the
    caller themselves, an id the roster does not know, so the graph answers nothing and the named
    validator's own directory is what saves the call (measured on the HTTP door 2026-09-02, where
    the refusal "agent has no registered workdir" stood while a validator with the right directory sat
    in the same roster). It answers second, not first.
    """
    task = engine.graph.get_task(task_id)
    executor = task.assignee if task is not None else None
    roster_side = (named_validator, executor,
                   agents.validator_for(executor, project=engine.project_name))
    # …and before the roster's directory, the node's OWN place when it has one: the roster names the base every
    # executor branches from, where a sibling may be mid-edit — the torn read a node workspace exists against
    # …and last but the oracle the repository its last DELIVER recorded (its main worktree's top): a chat registered
    # nowhere is validated with no workdir passed by hand, while a judge registered below that top keeps its directory
    recorded = delivered_repository(engine.graph.audit, task)
    return (node_workspace(engine, agents, task_id)
            or (agents.get(executor or "") or {}).get("workdir")
            or _children_workdir(engine, agents, task_id)
            or next((wd for who in roster_side
                     if who and (wd := (agents.get(str(who)) or {}).get("workdir"))), None)
            or (recorded if recorded and execution_of(engine, agents).files.is_dir(recorded) else None)
            or _oracle_workdir(engine, vcfg or {}))
