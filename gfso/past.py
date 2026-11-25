"""Work past the system: made in a repository a project works in while no node was taken there. Work before or outside
consent cannot be gated (§16.9 #11, §12.16), and opacity inside the protocol is a measurable defect (Cor. to Thm 11) —
so it is never refused, only measured, from records and never from what an agent says of itself.

One predicate for both catches (`at_work` over `spans`), by the moment: a change is attached to an obligation iff, when
it was made, a node attached to that repository was taken — in a work state (`WORK_STATES`, §12.1), a direction taken
for months as much as a leaf, whoever holds it —, over every project this server holds, open or only on disk (read
there without opening it). Attached: to the repository its ACCEPT recorded (`tools_llm.signal`, a chat's ACCEPT: the
repository it is performed in, by its main worktree, and its HEAD); an ACCEPT that recorded none, or one whose place
no longer stands — every one before that record — of a node its holder performs in their own chat (no role of the
system's roster) to each repository its project works in: the log's, its roles' workdirs, those the person installed
its witness in (`witness.installed` — their act, never what a call names), those a reading was taken in. A node a role
of the system performs reaches the person's repository only through the system's refs and landings, read by content.

- by the artifact (`past_the_system`): the commits on the person's lines — every worktree's HEAD and every branch but
  the system's — made by hand in the repository during the project: those git's reflogs record as committed, amended,
  cherry-picked, rebased, not merely moved to by a checkout, a reset, a merge or a pull. One made while a node attached
  there was taken is the obligation's — listed apart while that node is still taken (`in_work`). One made while none
  was is past the system unless its content is carried — its patch, or every path it changes as it leaves it, left by
  a commit outside its own history (a fold, a squash, an amend, a rebase's copy, a cherry-pick; setting a path back to
  what a commit it stands on left is a change) —: by the system's work (each chat delivery's own range as its DELIVER
  recorded it, what its places' deliveries and its landings recorded with what those reach — never a ref by its name
  alone, which any process can write under the system's), by what was made by hand while a node was taken there, or
  by a commit that existed before the project began. Compared by content, never by descent: this repository folds
  every branch before a push. A commit on those lines no record says was made here nor brought — only a transfer
  brings: a pull, a fetch or a clone a reflog records, never where a commit sits, as the person's own push puts their
  work on a remote's ref — (its worktree removed, its branch deleted, its entries expired before a reading saw them)
  is `undecided`: said apart, never counted and never dropped;
- by the moment (`witness`): a console's write to the repository while its own principal holds no node attached there,
  filed once as the project's record (`Engine.witnessed`) and said to the agent — the console's hook (`gfso.witness`)
  carries it, installed only by the person.

Everything the measure reads of git is kept in the project's record AS IT IS OBSERVED — how each commit was made or
brought, what the system's and the obligations' work held, the content of every carrier, each delivery's range at its
DELIVER —, so git's hygiene after (a worktree removed, a branch deleted, a reflog expired, `gc`) changes no reading
already taken: a reading only grows with new records. What git's records say is whoever works there's to rewrite (a
committer date set back, a reflog edited, work made and removed between two reads): the measure catches work kept
outside the system, not git's records forged. Who made a commit git's reflog does not record: a commit is attached
while any node is taken there, whoever holds it; the witness, which knows its console's principal, asks for that
principal's own."""
from __future__ import annotations

import json
import math
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from gfso.adapters import git as G
from gfso.adapters import worktrees as W
from gfso.adapters.storage.sqlite import peek_work
from gfso.config import CALLER, DEFAULT_PROJECT, agent_id, agents_path, caller_id, db_path, unsigned
from gfso.core.graph.model import LANDED, root_of
from gfso.core.types import TERMINAL_STATES, WORK_STATES, Signal, TaskId
from gfso.places import cheap_to_ask
from gfso.roster import AgentRegistry
from gfso.witness import installed

#: the reflog actions that make a commit where they are logged; the rest move a ref to one that stood
MADE = re.compile(r"^(commit|cherry-pick|revert|am)\b|\((pick|squash|fixup|reword|edit|continue)\)")
#: the reflog actions that bring onto a ref commits made elsewhere
BROUGHT = re.compile(r"^(pull|fetch|clone)\b")
#: the person's own branches: every one but the system's (`_theirs` adds every worktree's HEAD)
THEIRS = ("--exclude=gfso/*", "--branches")
#: the most commits one read lists; `count` says how many there are
LISTED = 50
#: what the readings of a repository saw, per project (`_seen`): {from, made: {commit: when}, brought, held}
KEPT = "made-by-hand:"
#: the content of every carrier the readings of a repository saw, per project: {commit: [patch id, [[path, blob]]]}
CARRIED = "carried-by:"
#: where a chat's work on a root taken at the go started: {branch the person stood on, the commit it started from}
CHAT_START = "chat_start:"
#: a project's chat deliveries, each with its own range's content as it stood at its DELIVER (`delivered`)
DELIVERED = "past-delivered"
#: the repositories a project's readings were taken in: {common git directory: its main worktree}
READ_IN = "past-read-in"
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
#: the actor of a witness a call signed by no one sent (`signin.BARE`, a console's hook with no name taken): it is
#: recorded, moving nothing, and never under the person's name
UNSIGNED = "unsigned"
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
    r = G.run(repo, *args, timeout=120, input=input)
    if r.returncode:
        raise OSError(f"`git {args[0]}` could not read {repo}: {r.stderr.strip()[-300:]}")
    return r.stdout


def _lines(xs) -> str:
    return "".join(f"{x}\n" for x in xs)


def repository(path) -> str | None:
    """The repository `path` stands in, one name for all its worktrees (its common git directory); None for none."""
    if not (path and cheap_to_ask(path) and Path(path).is_dir()):
        return None
    r = W.git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return os.path.normcase(str(Path(r.stdout.strip()).resolve())) if r.returncode == 0 and r.stdout.strip() else None


def started(accepts, went=None) -> str:
    """The commit a node's work started from, across every version of it: for a root taken at the go, the go's record
    (`went`); else the first of its accepted ACCEPTs' recorded commits (`accepts`, oldest first). Never a later
    ACCEPT's: a re-ACCEPT after a revision (§12.10) records the HEAD of the work already committed, and the re-delivery
    of that identical artifact, which the re-consent costs, was refused as the start, its range in this record empty
    — a root taken at the go has no ACCEPT before it. So a REOPENed part re-delivers the commit that passed, the
    identical re-delivery too."""
    return went or next((c for c in accepts if c), "")


def start_of(engine, node) -> str:
    """`started` read off `engine`'s record of `node`."""
    accepts = (e.commit for e in engine.audit_log(TaskId(str(node))) if e.signal == Signal.ACCEPT and not e.rejected)
    return started(accepts, json.loads(engine.graph.setting(f"{CHAT_START}{node}") or "{}").get("head"))


def _work_of(x) -> dict:
    """{"name", "taken": {node: holder}, "log": [(node, signal name, old state, new state, commit, repository, signer,
    unix time)] — its accepted ACCEPTs, DELIVERs and moves into or out of a work state, oldest first —, "landed": the
    commit its accepted result landed as or None, "delivered" (`DELIVERED`), "read_in" (`READ_IN`)} of one project:
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
                "landed": json.loads(x.graph.setting(LANDED) or "{}").get("sha"),
                **{f: json.loads(x.graph.setting(key) or "{}") for f, key in (("delivered", DELIVERED),
                                                                               ("read_in", READ_IN))}}
    stamp = tuple((st.st_mtime_ns, st.st_size) if (st := _stat(f)) else None for f in (x, f"{x}-wal"))
    if (hit := _PEEKED.get(x)) is None or hit[0] != stamp:
        got = peek_work(str(x), (DELIVERED, READ_IN)) or {"taken": {}, "log": [], "landed": None, "kept": {}}
        mine = os.path.normcase(os.path.abspath(x)) == os.path.normcase(os.path.abspath(db_path()))
        _PEEKED[x] = hit = (stamp, {**got, "name": DEFAULT_PROJECT if mine else Path(x).stem,
                                    "log": [(*r[:-1], math.floor(datetime.fromisoformat(r[-1]).timestamp()))
                                            for r in got["log"]],
                                    "delivered": json.loads(got["kept"].get(DELIVERED) or "{}"),
                                    "read_in": json.loads(got["kept"].get(READ_IN) or "{}")})
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
    """{repository: its main worktree} one project's work `w` works in: what its log names (a chat's ACCEPT and
    DELIVER), its roles' workdirs — where a place of the system's is cut from and a container's result lands —, where
    the person installed its witness, and where its readings were taken — a linked worktree removed leaves them its
    repository's. `named`: the repositories already asked of git in this reading."""
    paths = [row[5] for row in w["log"] if row[5]] + installed().get(w["name"], []) + [
        c["workdir"] for c in agents.list().values() if c.get("project") == w["name"] and c.get("workdir")]
    out = {}
    for p in dict.fromkeys(paths):
        if (k := named.setdefault(p, repository(p))) and W.is_repo_top(p):
            out.setdefault(k, W.main_worktree(p))
    for k, top in w["read_in"].items():
        if named.setdefault(top, repository(top)) == k:
            out.setdefault(k, top)
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
            k = r and named.setdefault(r, repository(r))
            keys = [k] if k else [] if signer and agents.get(signer) else where
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
    where named. A change made when it is empty is attached to no obligation. Both ends' seconds are in: git keeps its
    clock by whole seconds, and an agent's `commit` and the DELIVER after it fall in one."""
    return [s for s in spans_ if s.repository == repository_key and s.since <= at and (s.until is None or at <= s.until)
            and (holders is None or s.holder in holders)]


def delivered(engine, place, node: str, commit: str):
    """A chat's DELIVER of `commit` in `place`: its own range — from where its node's work started (`start_of`), else
    the commit alone — with each commit's change, as it stands now (a rework, an amend or git's `gc` after it leaves what
    was delivered). Read before the DELIVER is sent, so nothing waits after it; the call it returns keeps it in the
    project's record once the DELIVER is accepted."""
    if not (k := repository(place)):
        return lambda: None
    head = start_of(engine, node)
    shas = _git(place, "rev-list", "--no-merges", commit,
                *([f"^{head}"] if head and _there(place, [head]) else ["-1"])).split()
    got = {"repository": k, "changes": _dumped(_changes(place, shas))}
    return lambda: engine.graph.store_setting(DELIVERED, json.dumps(
        {**json.loads(engine.graph.setting(DELIVERED) or "{}"), commit: got}))


def _deliveries(works, key: str, named: dict) -> tuple:
    """(the commits of the chat deliveries into the repository `key` their DELIVER recorded, over every project held
    here; their content; [(delivered commit, where its node's work started by its ACCEPTs (`started`) or None)] of
    those delivered before that record — in `key`, or in a place that no longer stands —; [the commits the deliveries
    made in places of the system's and the landings recorded])."""
    held, content, live, places = set(), {}, [], []
    for w in works:
        heads, places = {}, places + ([w["landed"]] if w["landed"] else [])
        for node, s, _, _, c, r, _, _ in w["log"]:
            if not c:
                continue
            if s == "ACCEPT" and r:
                heads.setdefault(node, []).append(c)
            elif s == "DELIVER" and not r:
                places.append(c)
            elif s == "DELIVER" and (d := w["delivered"].get(c)) is not None:
                if d["repository"] == key:
                    held |= d["changes"].keys()
                    content.update(_loaded(d["changes"]))
            elif s == "DELIVER" and named.setdefault(r, repository(r)) in (key, None):
                live.append((c, started(heads.get(node, ())) or None))
    return held, content, live, places


def past_the_system(engine, agents) -> list[dict]:
    """[{repository, count, commits: the newest `LISTED`, in_work, undecided?, read_from?}] per repository this project
    works in; [] where it works in none. The window is the project's: from its log's first entry to its root's
    settling, open while it is not settled; `read_from` where the record of the repository's hand-made commits begins
    later; `undecided` ({count, commits}) the commits no record decides."""
    log = [e for e in engine.audit_log() if not e.rejected]
    if not log:
        return []
    root = root_of(engine.all_tasks())
    # …by whole seconds, as the reflog keeps its clock: a commit in the second the project began or ended is in it
    window = (math.floor(log[0].timestamp.timestamp()),
              math.ceil(log[-1].timestamp.timestamp()) if root is not None and root.state in TERMINAL_STATES else None)
    named, taken, works = {}, spans(engine, agents), _works(engine)
    if (repos := _works_in(works[0], agents, named)).items() - works[0]["read_in"].items():
        engine.graph.store_setting(READ_IN, json.dumps({**works[0]["read_in"], **repos}))
    out = []
    for k, path in repos.items():
        delivered_ = _deliveries(works, k, named)
        mine = tuple(s for s in taken if s.repository == k)
        try:
            key = (k, _git(path, "rev-parse", *_theirs(k), "--all"), window, tuple(sorted(delivered_[0])),
                   tuple(delivered_[2]), tuple(delivered_[3]), mine)
            if (got := _READ.get((engine.project_name, k))) is None or got[0] != key:
                _READ[engine.project_name, k] = got = (key, _measured(engine, k, path, window, delivered_, mine))
        except OSError:
            continue                    # …a repository git cannot read now has no reading, not a zero
        out.append({"repository": path, **got[1]})
    return out


def _measured(engine, k, repo, window, delivered_, taken) -> dict:
    since, until = window
    inside = lambda t: since <= t and (until is None or t <= until)                         # noqa: E731
    held_now, content, live, places = delivered_
    rec, made, brought, start = _seen(engine, k, repo, since)
    # …the commits on the person's lines in the window: made here when its record says, else — no record made it nor
    # brought it — at the date git gave it, undecided
    when = {c: made.get(c, int(t)) for c, t in (ln.split() for ln in _git(
        repo, "log", "--no-merges", "--format=%H %ct", *_theirs(k)).splitlines()) if c in made or c not in brought}
    left = [c for c, t in when.items() if inside(t)]
    under = {c: at_work(taken, k, when[c]) for c in left}
    # …what the system made and what was made while a node was taken there, the record's as much as git's
    held = set(rec["held"]) | held_now | {c for c, t in {**when, **made}.items() if inside(t) and at_work(taken, k, t)}
    if there := _there(repo, places):
        held |= set(_git(repo, "rev-list", "--no-merges", f"--max-age={since}", "--stdin",
                         input=_lines(there)).split()) - made.keys()
    for c, h in live:
        if c in (got := _there(repo, [c, h])):
            held |= set(_git(repo, "rev-list", "--no-merges", c, *([f"^{h}"] if h in got else ["-1"])).split())
    # …and every commit that stood before the project began, those a rebase replaced among them
    stood = set(_git(repo, "rev-list", "--no-merges", "--reflog", f"--min-age={since - 1}", *_theirs(k)).split()) - {
        c for c, t in made.items() if t >= since}
    carried = _loaded(json.loads(engine.graph.setting(CARRIED + k) or "{}"))
    if new := _there(repo, [c for c in held | stood if c not in carried]):
        carried.update(_changes(repo, new))
        engine.graph.store_setting(CARRIED + k, json.dumps(_dumped(carried)))
    if not held <= set(rec["held"]):
        engine.graph.store_setting(KEPT + k, json.dumps({**rec, "held": sorted(held | set(rec["held"]))}))
    rest = _uncarried(repo, [c for c in left if not under[c] and c not in held], {**carried, **content})
    past, undecided = sorted((c for c in rest if c in made), key=made.get, reverse=True), [c for c in rest
                                                                                           if c not in made]
    return {"count": len(past), "commits": past[:LISTED],
            "in_work": [c for c in left if c in made and any(s.until is None for s in under[c])],
            **({"undecided": {"count": len(undecided), "commits": undecided[:LISTED]}} if undecided else {}),
            **({"read_from": start} if start > since else {})}


def _theirs(k) -> tuple:
    """The person's own lines in the repository `k` (its common git directory): every worktree's HEAD — HEAD is each
    worktree's own, and a commit made on a linked one is logged in its HEAD's reflog alone — and their branches."""
    linked = Path(k) / "worktrees"
    ids = sorted(d.name for d in linked.iterdir() if (d / "HEAD").is_file()) if linked.is_dir() else []
    return ("HEAD", "main-worktree/HEAD", *(f"worktrees/{i}/HEAD" for i in ids), *THEIRS)


def _there(repo, shas) -> list:
    """Of `shas`, the commits the repository holds now."""
    if not (shas := [s for s in dict.fromkeys(shas) if s]):
        return []
    return [ln.split()[0] for ln in _git(repo, "cat-file", "--batch-check", input=_lines(shas)).splitlines()
            if ln.split()[1:2] == ["commit"]]


def _uncarried(repo, shas, by: dict) -> list:
    """Of `shas`, those whose change no commit of `by` ({commit: its change}) carries: neither its patch nor every
    path's result — that one left by a commit outside its own history: a copy (a fold, a squash, a rebase's) replaces
    what it copies, while a commit that stands on one and sets a path back to what it left makes a change."""
    ours, left = _changes(repo, shas), {}
    for c, (_, q) in by.items():
        for x in q:
            left.setdefault(x, set()).add(c)
    patches = {p for p, _ in by.values()} - {None}

    def _carried(c):
        q = ours[c][1]
        if not q <= left.keys():
            return False
        history = set(_git(repo, "rev-list", c).split())
        return all(left[x] - history for x in q)
    return [c for c in shas if ours[c][0] not in patches and not _carried(c)]


def _seen(engine, k, repo, since) -> tuple[dict, dict, set, int]:
    """(the record; {commit: when} made by hand in the repository — git's reflogs of the person's lines —; {commit}
    brought in the window by a pull, a fetch or a clone onto any ref — what the ref did not reach before, all it
    reaches where the transfer first wrote it, a push excluded; the time the record begins), each the record's as much as git's: what a reading saw stays seen once git forgets it."""
    rec = {"from": None, "made": {}, "brought": [], "held": [], **json.loads(engine.graph.setting(KEPT + k) or "{}")}
    made, oldest, moves, mine = {}, None, {}, set(_theirs(k))
    for line in _git(repo, "log", "-g", "--date=unix", "--format=%gD %H %gs", *_theirs(k), "--all").splitlines():
        ref, sha, what = (line.split(" ", 2) + ["", ""])[:3]
        if t := re.search(r"^(.+)@\{(\d+)\}$", ref):
            name, at = t[1], int(t[2])
            if name in mine or name.startswith("refs/heads/") and not name.startswith("refs/heads/gfso/"):
                oldest = min(oldest or at, at)
                if MADE.search(what):
                    made.setdefault(sha, at)
            moves.setdefault(name, {}).setdefault((at, sha), bool(BROUGHT.search(what)))
    brought = set()
    for line in moves.values():
        line = list(line.items())                                     # …newest first: an entry's old value is the next's
        for ((at, sha), transfer), ((_, was), _) in zip(line, [*line[1:], ((0, None), False)]):
            if transfer and at >= since:
                brought |= set(_git(repo, "rev-list", "--no-merges", f"--max-age={since}", sha,
                                    *([f"^{was}"] if was else [])).split())
    start = min((x for x in (rec["from"], oldest) if x is not None), default=since)
    keep = {c: t for c, t in made.items() if t >= since}
    if not (keep.keys() <= rec["made"].keys() and brought <= set(rec["brought"])) or rec["from"] != start:
        rec = {**rec, "from": start, "made": {**rec["made"], **keep}, "brought": sorted(brought | set(rec["brought"]))}
        engine.graph.store_setting(KEPT + k, json.dumps(rec))
    return rec, {**made, **rec["made"]}, brought | set(rec["brought"]), start


def _dumped(changes: dict) -> dict:
    return {c: [p, sorted(q)] for c, (p, q) in changes.items()}


def _loaded(kept: dict) -> dict:
    return {c: (p, frozenset(map(tuple, q))) for c, (p, q) in kept.items()}


def _changes(repo, shas) -> dict:
    """{commit: (its patch id, {(path, the blob it leaves there)})} — the change each commit makes, asked of git once
    per commit."""
    if new := [s for s in dict.fromkeys(shas) if s not in _CHANGES]:
        lines = _lines(new)
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
                         caller_id() if unsigned() is None else UNSIGNED, key)
    return {"say": SAY.format(repo=repository_path, tool=tool or "a tool call", project=engine.project_name)}
