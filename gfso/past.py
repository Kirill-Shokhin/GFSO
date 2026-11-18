"""Work past the system: made in a repository a project works in while no node was taken there. Work before or outside
consent cannot be gated (§16.9 #11, §12.16), and opacity inside the protocol is a measurable defect (Cor. to Thm 11) —
so it is never refused, only measured, from records and never from what an agent says of itself.

One predicate for both catches (`at_work` over `spans`), by the moment: a change is attached to an obligation iff, when
it was made, a node attached to that repository was taken — in a work state (`WORK_STATES`, §12.1), a direction taken
for months as much as a leaf, whoever holds it —, over every project this server holds, open or only on disk (read
there without opening it). Attached: to the repository its ACCEPT recorded (`tools_llm.signal`, a chat's ACCEPT: the
worktree it is performed in, its HEAD); an ACCEPT that recorded none — every one before that record — of a node its
holder performs in their own chat (no role of the system's roster) to each repository its project works in: the log's,
its roles' workdirs, those the person installed its witness in (`witness.installed` — their act, never what a call
names). A node a role of the system performs reaches the person's repository only through the system's refs and
landings, read by content below.

- by the artifact (`past_the_system`): the commits made BY HAND in the repository during the project — those git's
  reflogs of the person's own lines — every worktree's HEAD and every branch but the system's — record as committed, amended, cherry-picked, rebased, not merely moved to by a
  checkout, a reset, a fetch or a fast-forward pull; kept in the project's own record once read, as a reflog expires.
  One made while a node attached there was taken is the obligation's — listed apart while that node is still taken
  (`in_work`). One made while none was is past the system unless its content is carried — its patch, or every path it
  changes as it leaves it (a fold, a squash, an amend, a rebase's copy, a cherry-pick) —: by the system's work (each
  chat delivery's own range, from the HEAD its node's ACCEPT recorded to its delivered commit, and what its places'
  deliveries and its landings recorded, with what those reach — never a ref by its name alone, which any process can
  write under the system's), by what was made by hand while a node was taken
  there, or by a commit that existed before the project began. Compared by content, never by descent: this repository
  folds every branch before a push;
- by the moment (`witness`): a console's write to the repository while its own principal holds no node attached there,
  filed once as the project's record (`Engine.witnessed`) and said to the agent — the console's hook (`gfso.witness`)
  carries it, installed only by the person.

What git's records in the repository say is whoever works there's to rewrite (a committer date set back, a reflog
edited, a worktree made and removed between two reads): the measure catches work kept outside the system, not git's
records forged or gone. Who made a commit git's reflog
does not record: a commit is attached while any node is taken there, whoever holds it; the witness, which knows its
console's principal, asks for that principal's own."""
from __future__ import annotations

import json
import math
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from gfso.adapters import children
from gfso.adapters import worktrees as W
from gfso.adapters.storage.sqlite import peek_work
from gfso.config import CALLER, DEFAULT_PROJECT, agent_id, agents_path, caller_id, db_path
from gfso.core.graph.model import LANDED, root_of
from gfso.core.types import TERMINAL_STATES, WORK_STATES, Signal
from gfso.places import cheap_to_ask
from gfso.roster import AgentRegistry
from gfso.witness import installed

#: the reflog actions that make a commit where they are logged; the rest move a ref to one that stood
MADE = re.compile(r"^(commit|cherry-pick|revert|am)\b|\((pick|squash|fixup|reword|edit|continue)\)")
#: the person's own branches: every one but the system's (`_theirs` adds every worktree's HEAD)
THEIRS = ("--exclude=gfso/*", "--branches")
#: the most commits past the system one read lists; `count` says how many there are
LISTED = 50
#: the record of the commits made by hand in a repository, per project (`_kept`)
KEPT = "made-by-hand:"
#: (project, repository) → (its refs, the window, the records; the reading): a page polling it asks git one `rev-parse`
_READ: dict = {}
#: every project this server holds: its engine where open, else its record's path (`ProjectRegistry.projects`, set by
#: the server)
OPEN = lambda: ()  # noqa: E731
#: a record's path → (its stamp, its work): a project on disk read once per write of it
_PEEKED: dict = {}
#: a commit → its change (`_changes`): what a commit changes is its id's to keep
_CHANGES: dict = {}
WORK = frozenset(s.name for s in WORK_STATES)
SAY = ("GFSO: {repo} changed in {tool}, while you hold no node at work in it; the system recorded it as work past the "
       "system (project {project}). Take the node this work is for (ACCEPT it), or stop.")


class Span(NamedTuple):
    """A node taken, attached to a repository: from the second it entered a work state until the second it left one
    (None: taken now), and who holds it now."""
    repository: str
    node: str
    since: int
    until: int | None
    holder: str | None


def _git(repo, *args, input: str | None = None) -> str:
    r = children.run(["git", *W.APART, *args], timeout=120, cwd=str(repo), input=input, text=True, encoding="utf-8",
                     errors="replace")
    if r.returncode:
        raise OSError(f"`git {args[0]}` could not read {repo}: {r.stderr.strip()[-300:]}")
    return r.stdout


def repository(path) -> str | None:
    """The repository `path` stands in, one name for all its worktrees (its common git directory); None for none."""
    if not (path and cheap_to_ask(path) and Path(path).is_dir()):
        return None
    r = W.git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return os.path.normcase(str(Path(r.stdout.strip()).resolve())) if r.returncode == 0 and r.stdout.strip() else None


def _work_of(x) -> dict:
    """{"name", "taken": {node: holder}, "log": [(node, signal name, old state, new state, commit, repository, signer,
    unix time)] — its accepted ACCEPTs, DELIVERs and moves into or out of a work state, oldest first —, "landed": the
    commit its accepted result landed as or None} of one project:
    from its engine where open, else peeked at in its record (`peek_work`), never opened as a store, as building an
    engine starts its dispatcher."""
    if not isinstance(x, (str, os.PathLike)):
        named = lambda s: s and s.name                                                       # noqa: E731
        return {"name": x.project_name,
                "taken": {str(t.id): str(t.assignee) for t in x.all_tasks() if t.state in WORK_STATES},
                "log": [(str(e.task_id), e.signal.name, named(e.old_state), named(e.new_state), e.commit, e.repository,
                         e.source and str(e.source), math.floor(e.timestamp.timestamp())) for e in x.audit_log()
                        if not e.rejected and (e.signal in (Signal.ACCEPT, Signal.DELIVER)
                                               or {named(e.old_state), named(e.new_state)} & WORK)],
                "landed": json.loads(x.graph.setting(LANDED) or "{}").get("sha")}
    stamp = tuple((st.st_mtime_ns, st.st_size) if (st := _stat(f)) else None for f in (x, f"{x}-wal"))
    if (hit := _PEEKED.get(x)) is None or hit[0] != stamp:
        got = peek_work(str(x)) or {"taken": {}, "log": [], "landed": None}
        mine = os.path.normcase(os.path.abspath(x)) == os.path.normcase(os.path.abspath(db_path()))
        _PEEKED[x] = hit = (stamp, {**got, "name": DEFAULT_PROJECT if mine else Path(x).stem,
                                    "log": [(*r[:-1], math.floor(datetime.fromisoformat(r[-1]).timestamp()))
                                            for r in got["log"]]})
    return hit[1]


def _stat(f):
    try:
        return os.stat(f)
    except OSError:
        return None


def _works(engine) -> list[dict]:
    """The work of every project this server holds, the asking one's from its engine."""
    return [_work_of(x) for x in (engine, *(x for x in OPEN() if x is not engine))]


def _works_in(w, agents, named: dict) -> dict:
    """{repository: a path at its top} one project's work `w` works in: what its log names (a chat's ACCEPT and
    DELIVER), its roles' workdirs — where a place of the system's is cut from and a container's result lands —, and
    where the person installed its witness. `named`: the repositories already asked of git in this reading."""
    paths = [row[5] for row in w["log"] if row[5]] + installed().get(w["name"], []) + [
        c["workdir"] for c in agents.list().values() if c.get("project") == w["name"] and c.get("workdir")]
    out = {}
    for p in dict.fromkeys(paths):
        if (k := named.setdefault(p, repository(p))) and W.is_repo_top(p):
            out.setdefault(k, p)
    return out


def spans(engine, agents) -> list[Span]:
    """Every node taken, over every project held here, with each repository it is attached to (the module says which):
    from its move into a work state to its move out of one, read from its project's log; still taken, held by whom
    its project says now."""
    out, named = [], {}
    for w in _works(engine):
        where = list(_works_in(w, agents, named))
        opened, accepted = {}, {}

        def _attached(node, since, taken_by, until, holder):
            r, signer = taken_by
            keys = [named.setdefault(r, repository(r))] if r else [] if signer and agents.get(signer) else where
            return [Span(k, node, since, until, holder) for k in keys if k]
        for node, s, old, new, _, r, signer, at in w["log"]:
            if s == "ACCEPT":
                accepted[node] = (r, signer)
            if new in WORK and old not in WORK:
                opened[node] = (at, accepted.get(node, (None, None)))
            elif old in WORK and new not in WORK and node in opened:
                out += _attached(node, *opened.pop(node), at, None)
        for node, holder in w["taken"].items():
            since, taken_by = opened.pop(node, (0, accepted.get(node, (None, holder))))
            out += _attached(node, since, taken_by, None, holder)
    return out


def at_work(spans_, repository_key: str, at: int, holders=None) -> list[Span]:
    """The one predicate: the spans attached to the repository that held the second `at` — of a holder in `holders`
    where named. A change made when it is empty is attached to no obligation."""
    return [s for s in spans_ if s.repository == repository_key and s.since <= at and (s.until is None or at < s.until)
            and (holders is None or s.holder in holders)]


def _deliveries(engine, key: str, named: dict) -> tuple[list, list]:
    """([(delivered commit, the HEAD its node's ACCEPT recorded or None)] of the chat deliveries into the repository
    `key`, over every project held here; [the commits the deliveries made in places of the system's and the landings
    recorded])."""
    chats, places = [], []
    for w in _works(engine):
        heads, places = {}, places + ([w["landed"]] if w["landed"] else [])
        for node, s, _, _, c, r, _, _ in w["log"]:
            if not c:
                continue
            if s == "ACCEPT" and r:
                heads[node] = (c, r)
            elif s == "DELIVER" and not r:
                places.append(c)
            elif s == "DELIVER" and named.setdefault(r, repository(r)) == key:
                h = heads.get(node)
                chats.append((c, h[0] if h and named.setdefault(h[1], repository(h[1])) == key else None))
    return chats, places


def past_the_system(engine, agents) -> list[dict]:
    """[{repository, count, commits: the newest `LISTED`, in_work, read_from?}] per repository this project works in;
    [] where it works in none. The window is the project's: from its log's first entry to its root's settling, open
    while it is not settled; `read_from` where the record of the repository's hand-made commits begins later."""
    log = [e for e in engine.audit_log() if not e.rejected]
    if not log:
        return []
    root = root_of(engine.all_tasks())
    # …by whole seconds, as the reflog keeps its clock: a commit in the second the project began or ended is in it
    window = (math.floor(log[0].timestamp.timestamp()),
              math.ceil(log[-1].timestamp.timestamp()) if root is not None and root.state in TERMINAL_STATES else None)
    named, taken = {}, spans(engine, agents)
    out = []
    for k, path in _works_in(_work_of(engine), agents, named).items():
        chats, places = _deliveries(engine, k, named)
        mine = tuple(s for s in taken if s.repository == k)
        try:
            key = (k, _git(path, "rev-parse", *_theirs(k), "--all"), window, tuple(chats), tuple(places), mine)
            if (got := _READ.get((engine.project_name, k))) is None or got[0] != key:
                _READ[engine.project_name, k] = got = (key, _measured(engine, k, path, window, chats, places, mine))
        except OSError:
            continue                    # …a repository git cannot read now has no reading, not a zero
        out.append({"repository": path, **got[1]})
    return out


def _measured(engine, k, repo, window, chats, places, taken) -> dict:
    since, until = window
    made, start = _kept(engine, k, repo, window)
    left = [c for c in _git(repo, "rev-list", "--no-merges", *_theirs(k)).split()
            if c in made and since <= made[c] and (until is None or made[c] <= until)]
    under = {c: at_work(taken, k, made[c]) for c in left}
    rest = [c for c in left if not under[c]]
    if rest:
        held = set(_git(repo, "rev-list", "--no-merges", "--ignore-missing", f"--max-age={since}", "--stdin",
                        input="".join(f"{c}\n" for c in places)).split()) - made.keys() if places else set()
        for c, h in chats:
            held |= set(_git(repo, "rev-list", "--no-merges", "--ignore-missing", c, *([f"^{h}"] if h else ["-1"])).split())
        # …and what was made by hand while a node was taken there, delivered or not, the record's as much as git's
        if under_a_node := [c for c, t in made.items() if since <= t and (until is None or t <= until)
                            and at_work(taken, k, t)]:
            held |= set(_git(repo, "rev-list", "--no-walk", "--ignore-missing", "--stdin",
                             input="".join(f"{c}\n" for c in under_a_node)).split())
        rest = _uncarried(repo, [c for c in rest if c not in held], held)
    if rest:
        # …the commits that stood before the project began, those a rebase replaced among them, touching what these do
        stood = _git(repo, "--literal-pathspecs", "rev-list", "--no-merges", "--reflog", f"--min-age={since - 1}",
                     "--stdin", *_theirs(k), input="--\n" + "".join(
                         f"{p}\n" for p in {p for q in _changes(repo, rest).values() for p, _ in q[1]}))
        rest = _uncarried(repo, rest, [c for c in stood.split() if made.get(c, since - 1) < since])
    past = sorted(rest, key=made.get, reverse=True)
    return {"count": len(past), "commits": past[:LISTED],
            "in_work": [c for c in left if any(s.until is None for s in under[c])],
            **({"read_from": start} if start > since else {})}


def _theirs(k) -> tuple:
    """The person's own lines in the repository `k` (its common git directory): every worktree's HEAD — HEAD is each
    worktree's own, and a commit made on a linked one is logged in its HEAD's reflog alone — and their branches."""
    linked = Path(k) / "worktrees"
    ids = sorted(d.name for d in linked.iterdir() if (d / "HEAD").is_file()) if linked.is_dir() else []
    return ("HEAD", "main-worktree/HEAD", *(f"worktrees/{i}/HEAD" for i in ids), *THEIRS)


def _uncarried(repo, shas, by) -> list:
    """Of `shas`, those whose change no commit of `by` carries: neither its patch nor every path's result."""
    theirs, ours = _changes(repo, by), _changes(repo, shas)
    patches, paths = {p for p, _ in theirs.values()} - {None}, set().union(*(q for _, q in theirs.values()))
    return [c for c in shas if ours[c][0] not in patches and not ours[c][1] <= paths]


def _kept(engine, k, repo, window) -> tuple[dict, int]:
    """({commit: when} made by hand in the repository, from the reflogs of the person's lines and the project's record
    of what they held before — a reflog expires (`gc.reflogExpire`), the record does not —, the time the record
    begins). What falls in the window is kept."""
    rec = json.loads(engine.graph.setting(KEPT + k) or '{"from": null, "made": {}}')
    made, oldest = {}, None
    for line in _git(repo, "log", "-g", "--date=unix", "--format=%H %gd %gs", *_theirs(k)).splitlines():
        sha, at, what = (line.split(" ", 2) + ["", ""])[:3]
        if t := re.search(r"@\{(\d+)\}$", at):
            oldest = min(oldest or int(t[1]), int(t[1]))
            if MADE.search(what):
                made.setdefault(sha, int(t[1]))
    start = min((x for x in (rec["from"], oldest) if x is not None), default=window[0])
    keep = {c: t for c, t in made.items() if t >= window[0]}
    if not keep.keys() <= rec["made"].keys() or rec["from"] != start:
        engine.graph.store_setting(KEPT + k, json.dumps({"from": start, "made": {**rec["made"], **keep}}))
    return {**made, **rec["made"]}, start


def _changes(repo, shas) -> dict:
    """{commit: (its patch id, {(path, the blob it leaves there)})} — the change each commit makes, asked of git once
    per commit."""
    if new := [s for s in dict.fromkeys(shas) if s not in _CHANGES]:
        lines = "".join(f"{s}\n" for s in new)
        paths, sha = {s: set() for s in new}, None
        for ln in _git(repo, "log", "--no-walk=unsorted", "--stdin", "--format=commit %H", "--raw", "--no-renames", "-r",
                       "--no-abbrev", input=lines).splitlines():
            if ln.startswith("commit "):
                sha = ln.split()[1]
            elif ln.startswith(":") and "\t" in ln:
                paths[sha].add((ln.split("\t", 1)[1], ln.split()[3]))
        shown = _git(repo, "log", "-p", "--no-walk=unsorted", "--no-ext-diff", "--no-textconv", "--no-color", "--stdin",
                     input=lines)
        patch = {s: p for p, s in (ln.split() for ln in _git(repo, "patch-id", "--stable", input=shown).splitlines())}
        _CHANGES.update({s: (patch.get(s), frozenset(q)) for s, q in paths.items()})
    return {s: _CHANGES[s] for s in shas}


def witness(engine, repository_path: str, tool: str = "", paths=(), key: str = "") -> dict:
    """A console's write to `repository_path` while its own principal holds no node attached there (`at_work`):
    recorded once per write (`key`, its fingerprint: overlapping calls see one write) as the project's own
    (`Engine.witnessed`), and the line its agent is told — {} where it holds one, or the project has no root or has
    settled (a finished project's repository is no longer its own). What the call names binds nothing: it is answered by
    the records of that repository."""
    root = root_of(engine.all_tasks())
    k = repository(repository_path)
    if root is None or root.state in TERMINAL_STATES or k is None:
        return {}
    p = CALLER.get()
    if at_work(spans(engine, AgentRegistry(agents_path())), k, math.floor(time.time()),
               {p.name, *p.signs_as} if p is not None else {agent_id()}):
        return {}
    if not key or all(r.get("key") != key for r in engine.witnessed_writes()):
        paths = [str(p) for p in paths or ()]
        engine.witnessed(f"{repository_path} changed in {tool or 'a tool call'} with no node of its signer at work "
                         f"there: {len(paths)} path(s): " + ", ".join(paths[:10]) + (" …" if len(paths) > 10 else ""),
                         caller_id(), key)
    return {"say": SAY.format(repo=repository_path, tool=tool or "a tool call", project=engine.project_name)}
