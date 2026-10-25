"""Where a node's work stands: the scope one executor's session carries it in (`session_scope`), the node's own git
workspace derived from its executor's roster place (`node_workspace`), entering it, joining its PASSed parts into the
whole (`join_whole`), and clearing them at the root's PASS (`clear_workspaces`). Derived, never stored."""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from gfso.adapters import worktrees as W
from gfso.adapters.execution import ContainerExecution, LocalExecution
from gfso.config import DEFAULT_PROJECT, MODEL_DEFAULT, executions
from gfso.llm import llm_factory
from gfso.places import cheap_to_ask, same_place
from gfso.core.graph.model import generation_of_task
from gfso.core.types import Signal, TaskId, State
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


def _safe(s) -> str:
    """A node id or a project name as one path component and one ref component."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(s)).replace("..", "_").strip(".") or "_"


_NODES = ".gfso-nodes-"   # a base's node places stand beside it, under this prefix and the base's name


def _workspace(engine, agents: "AgentRegistry", task) -> tuple[str, str, str] | None:
    """(base, place, branch) of the node's workspace — derived, never stored: the base is its executor's roster
    workdir when that is a git repository's top, the key its scope's top when one session carries the scope (one
    place for the session and its one validation), else the node. Under the project, since two projects on one
    base both have a `root`. None: no git base, and the node works in the shared directory as before."""
    w = _place_of(engine, agents, task)
    return w if w is not None and cheap_to_ask(w[0]) and W.is_repo_top(w[0]) else None


def _place_of(engine, agents: "AgentRegistry", task) -> tuple[str, str, str] | None:
    """(base, place, branch) as `_workspace` derives them, asking git nothing — so a caller that must not wait on a
    subprocess (the transition bus) can ask whether a place was ever made (`Path(place).is_dir()`)."""
    base = (performer(engine, agents, task.assignee)[1] or {}).get("workdir") if task is not None else None
    if not base:
        return None
    key, proj = _safe((session_scope(engine, agents, task) or task).id), _safe(engine.project_name or DEFAULT_PROJECT)
    return base, str(Path(base).parent / f"{_NODES}{Path(base).name}" / proj / key), f"gfso/{proj}/{key}"



def base_of(place: str | None) -> str | None:
    """The base a node's place is a checkout of — `_place_of` read backwards; None for a place that is no node's."""
    p = Path(place) if place else None
    if p is None or len(p.parents) < 3 or not p.parent.parent.name.startswith(_NODES):
        return None
    return str(p.parent.parent.parent / p.parent.parent.name[len(_NODES):])


def node_workspace(engine, agents: "AgentRegistry", task_id) -> str | None:
    """The node's own workspace, once its first session has made it — where its delivery stands and is validated."""
    w = _workspace(engine, agents, engine.graph.get_task(TaskId(task_id)))
    return w[1] if w is not None and Path(w[1]).is_dir() else None


def _where_it_joins(engine, agents: "AgentRegistry", task, w: tuple) -> str | None:
    """Where the node's result joins the whole: its parent's workspace in the same repository once the parent has
    one, else the base. None inside its own scope, whose place is the parent's too."""
    parent = engine.graph.get_parent(task.id)
    pw = _workspace(engine, agents, parent) if parent is not None else None
    if pw is not None and pw[2] == w[2]:
        return None
    return pw[1] if pw is not None and same_place(pw[0], w[0]) and Path(pw[1]).is_dir() else w[0]


def join_whole(engine, agents: "AgentRegistry", task_id) -> str | None:
    """A part joins the whole when it PASSes: its delivery's branch merged `--no-ff` where its parent works. None
    when joined or nothing to join; else why not. A conflict is aborted and the branch left as it is: the whole's
    integration is the whole's work (§8.7, the glue), and the parent's packet names the branch (`_enter_workspace`)."""
    t = engine.graph.get_task(TaskId(task_id))
    w = _workspace(engine, agents, t) if t is not None and t.state == State.DONE else None
    if w is None or not Path(w[1]).is_dir():
        return None
    parent = engine.graph.get_parent(t.id)
    # …WHERE ITS WHOLE WILL WORK, made now if the whole's session has not started yet: joined straight into the base,
    # the parts stood in the user's tree before any seam passed the whole — a whole that then failed left them there,
    # and a NOT DONE row scored work no root verdict covered (critic r5, 2026-10-04)
    if parent is not None and (pw := _workspace(engine, agents, parent)) is not None and same_place(pw[0], w[0]):
        _ensure_place(engine, agents, parent, pw)
    if (into := _where_it_joins(engine, agents, t, w)) is None:
        return None
    why = W.merge(w[0], into, w[2], f"gfso: {t.id} joins {parent.id if parent else 'the base'}",
                  execution=execution_of(engine, agents))
    if why and engine.say_once(f"unjoined:{t.id}:{generation_of_task(t)}"):
        engine.emit_info("delegate", f"{t.id}: PASSED, and its branch `{w[2]}` did not join {into} ({why}) - the "
                                     f"merge was aborted and the branch stands unmerged; integrating it is the work "
                                     f"of {'`' + str(parent.id) + '`, whose packet names it' if parent else 'its owner'}")
    return why


def _ensure_place(engine, agents: "AgentRegistry", task, w: tuple) -> None:
    """The node's place, made if absent from where its whole works — that place made first, up the tree: cut from the
    base while its whole had none, a place missed what had already joined the whole (critic r6, 2026-10-04: a part
    covering its whole's Dep started without the producer that had joined the grandparent)."""
    parent = engine.graph.get_parent(task.id)
    if parent is not None and (pw := _workspace(engine, agents, parent)) is not None and pw[2] != w[2] \
            and same_place(pw[0], w[0]):
        _ensure_place(engine, agents, parent, pw)
    W.ensure(w[0], w[1], w[2], _where_it_joins(engine, agents, task, w) or w[0])


def _enter_workspace(engine, agents: "AgentRegistry", top, members: list) -> tuple:
    """(cwd, unjoined, workspace) of a session over `members` keyed by `top`: its worktree, made from where its
    parent works when its first session starts — its producers are DONE by then (Dep readiness), hence joined —
    and reused on rework; every DONE part and producer outside it merged in, those that conflict listed for its
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
        if xw is None or xw[2] == branch or not same_place(xw[0], base) or not Path(xw[1]).is_dir():
            continue
        if (why := W.merge(base, place, xw[2], f"gfso: {x.id} joins {top.id}", execution=execution_of(engine, agents))):
            unjoined.append((str(x.id), xw[2], why))
    return place, unjoined, w


def parts_of(engine, members: list) -> tuple[dict, dict]:
    """({id: node} whose work the members' result carries — their active children, the producers they consume, and the
    work they carry on — , {id: node} of the last alone)."""
    inside = {str(m.id) for m in members}
    parts = {str(k.id): k for m in members for k in engine.graph.get_active_children(m.id)}
    parts.update({str(e.from_id): engine.graph.get_task(TaskId(e.from_id)) for e in engine.adopted_dependencies()
                  if str(e.to_id) in inside})
    # …AND THE WORK OF WHAT IT REPLACES, PASSed or not: a child merged out of a cycle, or cut again, started from the
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
    return [x for x, b, _ in unjoined if x in mine and (x not in kept or mine[x].state == State.DONE)
            and not W.contains(workspace[0], workspace[1], b)]


def _unjoined_text(unjoined: list) -> str:
    """The parts whose PASSed delivery did not merge into this session's workspace — its integration to do."""
    if not unjoined:
        return ""
    return ("\n## Parts NOT joined into your workspace — integrating them is this whole's work\n"
            "Each stands on its own branch — a part that PASSed, or a node this one replaces, whose work it carries "
            "on — and did not merge here cleanly (the merge was aborted, your tree is as it was). Merge each "
            "(`git merge <branch>`), resolve, and deliver the integrated result. A delivery whose tree does not "
            "contain every branch below is not handed in: your result is the integration of its parts' work, and "
            "rewriting what a part already built in place of merging it loses what its seam passed.\n"
            + "".join(f"- `{x}` on branch `{b}`: {why}\n" for x, b, why in unjoined))


#: the roles whose sessions keep a conversation: one node's round and one scope's — two prompts, two conversations
CONVERSING_ROLES = ("executor", "scope-executor")


#: one object per (execution, project): its container is started once and every call of the project goes through it
_EXECUTIONS: dict = {}


def execution_of(engine, agents: "AgentRegistry | None" = None):
    """WHERE this project's sessions and commands run: the execution its roles declare (`register_agent(execution=)`,
    one per project), in the place of the role that declared it — else this host."""
    role = next((c for c in (agents or AgentRegistry()).list().values()
                 if c.get("execution") and c.get("project") == engine.project_name and c.get("workdir")), None)
    if role is None:
        return LocalExecution()
    key = (role["execution"], engine.project_name, role["workdir"])
    if key not in _EXECUTIONS:
        d = executions()[role["execution"]]
        _EXECUTIONS[key] = ContainerExecution(role["execution"], d["image"], d["env_file"], d["state"],
                                              role["workdir"], engine.project_name)
    return _EXECUTIONS[key]


def drop_execution(engine) -> None:
    """The project is gone: its container goes, and so does the object that held it."""
    execution_of(engine).stop()
    for key in [k for k in _EXECUTIONS if k[1] == engine.project_name]:
        del _EXECUTIONS[key]


def project_llm(engine, model: str, agents: "AgentRegistry | None" = None):
    """The model a session of this project runs on, started where the project's work runs."""
    return llm_factory(model, execution=execution_of(engine, agents))


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
    left, seen, llm = [], set(), project_llm(engine, MODEL_DEFAULT, agents)   # its conversations live where it ran
    for t in engine.all_tasks():
        for role in CONVERSING_ROLES:          # the work its conversations served is settled
            llm.forget(conversation_of(engine, t.id, t.assignee, role))
        w = _workspace(engine, agents, t)
        if w is None or w[2] in seen or not Path(w[1]).is_dir():
            continue
        seen.add(w[2])
        if not (W.contains(w[0], w[0], w[2]) and W.remove(*w)):
            left.append(f"{w[1]} (`{w[2]}`)")
    execution_of(engine, agents).stop()        # the goal is settled: its project's container goes too
    if left:
        engine.emit_info("delegate", f"{root.id}: DONE - node workspaces not joined into the base are kept: "
                                     f"{'; '.join(left)}")
