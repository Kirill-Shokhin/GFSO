"""The work a chat performs in the person's own repository (`perform="in_chat"`): the branch it goes on, what its
DELIVER names and is refused for, and what it hears at its root's PASS — read in the person's git, written nowhere.

The verb registry reads it at the door's `signal` and at a plan handed in as a file; it reads nothing of the registry.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from gfso import past, store
from gfso.adapters import worktrees as W
from gfso.adapters.execution import component
from gfso.config import DEFAULT_PROJECT
from gfso.engine import Engine
from gfso.places import cheap_to_ask
from gfso.roster import default_agents
from gfso.workspaces import accepted_branch, execution_of, performer, repository, validator_workdir


def work_branch(engine: Engine) -> str:
    """The branch of the person's repository the work performed in their own chat goes on (`in_chat`): the system's, by
    name, so their checked-out branches stay theirs; what its root's PASS accepts is named `accepted_branch` there."""
    return f"gfso/{component(engine.project_name or DEFAULT_PROJECT)}/work"


def switches_branches(engine: Engine, node) -> bool:
    """Does a chat performing `node` switch the person's checkout to the work's branch and back? Not in a mode scope:
    its checkout is shared with the other streams' holders, so a switch would move their work under them — the holder
    commits where it works, and its ask's PASS lands nothing (slice 1's boundary)."""
    return engine.scope_at(node) is None


def on_their_branch(engine: Engine, place) -> str:
    """What a chat performing its work at `place` hears where that repository stands anywhere but the work's branch —
    their own, the accepted one, a detached HEAD — or "". Said, never refused: the repository is the chat's own tools', and no check of where it stands holds what is
    committed next; their branches stay theirs by the work going where the system names (`work_branch`). A client told
    the person "your main did not change" over commits it made on main (s20g1)."""
    if not (place and W.is_repo_top(place)):
        return ""
    on = W.git(place, "symbolic-ref", "-q", "--short", "HEAD").stdout.strip()
    if on == work_branch(engine):
        return ""
    return (f"{place} is the person's own working tree, standing on {f'`{on}`' if on else 'a detached HEAD'}: what you "
            f"commit there lands on it. Work on the system's branch — `git switch -c {work_branch(engine)}` (`git switch "
            f"{work_branch(engine)}` once it exists) before your first commit, which changes their checkout — tell the "
            f"person so in one line, and switch it back to `{on or 'where it stood'}` once the work is delivered")


def _past(place, start: str, head: str) -> bool:
    """Has `head`, read in the git at `place`, moved past `start` — differs and descends from it (any head, where no start
    is recorded)?"""
    return bool(head) and head != start and (not start or W.git(
        place, "merge-base", "--is-ancestor", start, head).returncode == 0)


def _trees(place) -> list:
    """[(path, HEAD, branch or "")] of the work trees of `place`'s repository, its main one first."""
    out = []
    for entry in W.git(place, "worktree", "list", "--porcelain").stdout.split("\n\n"):
        lines = dict(ln.split(" ", 1) for ln in entry.splitlines() if " " in ln)
        if lines.get("worktree") and lines.get("HEAD"):
            out.append((str(Path(lines["worktree"])), lines["HEAD"], lines.get("branch", "").removeprefix("refs/heads/")))
    return out


def _work_tip(engine: Engine, tid, top) -> Optional[tuple]:
    """(where the work's branch is checked out, else `top`; its tip) where the mode works on the system's branch
    (`work_branch`) and the work moved it past where it started — the commit a chat that names none delivers —, or
    None. Never a HEAD by inference: the person's main tree at his own commit was judged as the agent's work, and a
    linked worktree's work went unnamed until the start itself was handed in (critics over ac9dcaa, f96cb2b)."""
    wb = work_branch(engine)
    tip = W.git(top, "rev-parse", "--verify", "-q", f"refs/heads/{wb}^{{commit}}").stdout.strip()
    if not (switches_branches(engine, tid) and _past(top, past.start_of(engine, tid), tip)):
        return None
    return next((p for p, _, b in _trees(top) if b == wb), top), tip


def _unnamed(engine: Engine, tid, top, why: str = "no commit of the work is named") -> str:
    """The refusal of a chat's DELIVER that names no commit past where its work started, before any write (§12.16
    (ii)): its lifts — commit on the work's branch where the mode works on one, or name the place or commit — and the
    linked work trees and branches of the repository standing past the start, never the person's main tree nor his
    branches: only the sender knows where its work is committed."""
    start, wb = past.start_of(engine, tid), work_branch(engine)
    trees = _trees(top)
    theirs = {json.loads(engine.graph.setting(f"{past.CHAT_START}{tid}") or "{}").get("branch"),
              *(b for *_, b in trees[:1])}
    there = [f"`place={p}` (at {h[:12]})" for p, h, _ in trees[1:] if _past(top, start, h)]
    held = {b for *_, b in trees}
    there += [f"`place={h}` (branch `{b}`)" for b, h in (ln.split(" ", 1) for ln in W.git(
        top, "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads").stdout.splitlines() if " " in ln)
        if b not in held | theirs and _past(top, start, h)]
    return (f"NOT delivered — {why}: "
            + (f"commit it on `{wb}` and DELIVER again, or " if switches_branches(engine, tid) else "")
            + "name the work tree you committed in: place=<its path>, or the commit: place=<its id>"
            + (f". Of {W.main_worktree(top)}, these stand past where the work started ({start[:12]}): "
               + "; ".join(there) if there else "")
            + ". If the work changed nothing, an empty commit says so. No validator was started")


def chat_place(engine: Engine, source, tid, named):
    """Where `source` performs `tid` in its own chat — the place it names (`named`), else its judge's directory, else
    the project's repository —, or a falsy answer: the git a chat's ACCEPT records the HEAD of and its DELIVER reads
    the commit it names in, or the work's branch (`_work_tip`)."""
    agents = default_agents()
    return performer(engine, agents, source)[0] is None and (
        named or validator_workdir(engine, agents, tid) or repository(engine, agents))


def _roots(repo, rev: str) -> set:
    """The root commits of `rev`'s history in the git at `repo` — empty where it does not hold `rev`."""
    return set(W.git(repo, "rev-list", "--max-parents=0", rev).stdout.split())


def _unrelated(engine: Engine, place, commit: str) -> Optional[str]:
    """Why `commit`, read in the git at `place`, is no commit of the project's repository — it shares no root commit
    with what the project holds: the repository it recorded, its volume's imported commit, the deliveries its store
    keeps — or None. Any git holding a commit of the project delivers it, a plain clone too; an unrelated repository
    named by `place=` became the log's repository, its tree judged against this project's contract (critic over
    4ac5e3a). Nothing the project holds to compare with: admitted, the first delivery stands as its history."""
    rec = repository(engine, default_agents())
    known = ((_roots(rec, "HEAD") if rec and cheap_to_ask(rec) and W.is_repo_top(rec) else set())
             | (_roots(place, first) if (first := store.imported(engine)) else set())
             | store.roots(engine, execution_of(engine)))
    if not known or _roots(place, commit) & known:
        return None
    return (f"NOT delivered — commit {commit[:12]} at {place} shares no history with the project's repository"
            f"{f' {rec}' if rec else ''}: deliver a commit of it, from a work tree or a clone of it (`place=`). No "
            f"validator was started")


def not_its_repository(engine: Engine, place) -> Optional[str]:
    """Why the place a chat names for its DELIVER is no git it can deliver from — not a work tree's top with a commit
    — or None. Any git holding the commit delivers it, a plain clone as a linked worktree: the commit is
    taken into the project's store by its id once admitted, and read there, never in the place."""
    return None if W.is_repo_top(place) else f"{place} is not the top of a git work tree with a commit"


def a_chats_delivery(engine: Engine, tid, top, rev: Optional[str]) -> tuple[Optional[dict], dict]:
    """(why a chat's DELIVER of `rev` — named by its sender: a place's HEAD or a commit id —, read in the git at `top`,
    a repository's top, is refused — the answer's fields — or None; what it delivers: `_recorded`, the act that `keep`s
    it once accepted, and what its answer says besides). Named nothing (`rev` None): the work's branch past the start
    (`_work_tip`), else refused, its lifts named (`_unnamed`). REFUSED ONLY ON WHAT ITS SENDER LIFTS, EVERY REFUSAL
    BEFORE ANY WRITE (§12.16 (ii)): the admission test reads the commit whole in the sender's git and writes nothing
    (`store.admit`); a system's failure is no refusal — its keep, the system's act once the DELIVER is accepted, is
    retried by the first reader (`store.held`)."""
    place = top
    if rev is None:
        if not (work := _work_tip(engine, tid, top)):
            return {"refused": True, "error": _unnamed(engine, tid, top)}, {}
        place, rev = work
    elif rev != "HEAD" and not W.git(place, "rev-parse", "--verify", "-q", f"{rev}^{{commit}}").stdout.strip():
        return {"refused": True, "error": f"NOT delivered — {rev} is no commit of {place}: name one of the project's "
                                          f"repository, or the work tree it is committed in (`place=<its path>`). "
                                          f"No validator was started"}, {}
    try:
        tree, commit, left = W.read_head(place, rev)
        left = left if W.git(place, "rev-parse", "HEAD").stdout.strip() == commit else []   # …another tree's files
    except OSError as ex:
        return {"error": f"NOT delivered — the commit at {place} could not be recorded: {ex}"}, {}
    if inner := W.nested(place, commit):        # …refused where its sender lifts it, not FAILed at the copy
        return {"error": f"NOT delivered — {W.nested_cause(inner)}"}, {}
    if why := store.shallow(place):     # …before its roots are read: its boundary is one, shared with nothing
        return {"refused": True, "error": f"NOT delivered — {why}, and DELIVER again. No validator was started"}, {}
    if no := _unrelated(engine, place, commit):
        return {"refused": True, "error": no}, {}
    if not _past(place, start := past.start_of(engine, tid), commit):   # …the start judged FAILed true work (s21)
        return {"refused": True, "error": _unnamed(engine, tid, place, (
            f"{commit[:12]} is the commit the work started from" if commit == start else
            f"{commit[:12]} does not descend from {start[:12]}, the commit the work started from")
            + (f", and these stand uncommitted at {place}: {', '.join(left[:10])}{', …' if len(left) > 10 else ''}"
               if left else ""))}, {}
    pack = None
    try:
        pack = store.admit(engine, execution_of(engine), commit, place)
    except store.Unreadable as ex:
        return {"refused": True, "error": f"NOT delivered — {ex}, and DELIVER again. No validator was started"}, {}
    except (OSError, subprocess.TimeoutExpired) as ex:   # …the system's own reading failed: no cause of the sender's
        engine.emit_info("delivery", f"{tid}: the admission read of {commit[:12]} failed on the system's side ({ex}): "
                                     f"admitted, its keep reads it again")
    got = {"_recorded": (tree, commit, W.main_worktree(place)),
           "keep": lambda: store.keep(engine, execution_of(engine), commit, place, place, pack=pack),
           "drop": lambda: store.discard(pack)}
    if switches_branches(engine, tid) and (notice := not_the_work(engine, place, commit)):
        got["notice"] = notice
    if left:
        got["not_delivered"] = (f"delivered: commit {commit[:12]}; not committed, so no part of it: "
                                f"{', '.join(left[:10])}{', …' if len(left) > 10 else ''}")
    return None, got


def back_to_their_branch(engine: Engine, tid) -> str:
    """What a chat hears at its root's PASS where the person's repository was left on the work's branch: switch it back."""
    start = json.loads(engine.graph.setting(f"{past.CHAT_START}{tid}") or "{}")
    place = validator_workdir(engine, default_agents(), tid)
    if not (place and W.is_repo_top(place) and switches_branches(engine, tid)):
        return ""
    on = W.git(place, "symbolic-ref", "-q", "--short", "HEAD").stdout.strip()
    if on != work_branch(engine) or not (was := start.get("branch")) or was == on:
        return ""
    return (f"{place} still stands on `{on}`: switch it back to theirs, `git switch {was}`, and tell them the result is "
            f"`{accepted_branch(engine)}` (or tell them how, if they would rather do it)")


def not_the_work(engine: Engine, place, commit: str) -> str:
    """What a chat's DELIVER hears where the commit it recorded — what `place`, the registered top, stands on — is not
    on the work's branch: an agent working in a linked worktree on `work_branch` delivered the person's start commit,
    and its judge FAILed true work (critic over 354554c). A notice, never a refusal: the report may be true. A commit
    named by its id is told as named, never as what `place` stands on (critic over 1d84a75). Or ""."""
    wb = work_branch(engine)
    if (there := W.git(place, "rev-parse", "--verify", "-q", f"refs/heads/{wb}^{{commit}}").stdout.strip()) == commit:
        return ""
    if W.git(place, "rev-parse", "HEAD").stdout.strip() != commit:
        return (f"delivered: commit {commit[:12]}, named by its id, not the tip of `{wb}`"
                + (f" ({there[:12]}): if your work is there, DELIVER naming nothing" if there else "")
                + ". The judge reads this commit.")
    on = W.git(place, "symbolic-ref", "-q", "--short", "HEAD").stdout.strip()
    return (f"delivered: commit {commit[:12]}, what {place} stands on ({f'`{on}`' if on else 'a detached HEAD'}), not "
            f"`{wb}`" + (f", which stands at {there[:12]}: if your work is there, `git switch --detach {wb}` at {place} "
                         f"(a branch a linked worktree holds cannot be checked out twice — or remove that worktree "
                         f"first, then `git switch {wb}`), and deliver again" if there else "")
            + ". The judge reads this commit.")
