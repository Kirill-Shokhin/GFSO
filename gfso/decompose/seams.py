"""The plan's Dep seams read as what they cost and what they claim — over the spec, before anything is built.

A seam is the claim "the consumer's WORK reads the producer's output" (§2.7): the consumer waits for the producer's
PASS, so every seam on the longest chain is wall time (`waves`). A seam that orders work only so a CHECK can run
makes independent work wait for a verdict it never needed (measured: the sql_database plan chained 12 parts into 8
waves because each part's probes ran the whole binary; its three rows spent 9 h each). So a seam names what of the
producer's files the consumer's work reads, and that claim is checked against the files the producer declares it
writes (`seam_problems`) — a finding for the plan's author, never a refusal: §15.5 admits an edge no criterion
references, and only its author can say what it carries."""
from __future__ import annotations


def _ids(spec: dict) -> list[str]:
    return [str(k.get("id")) for k in spec.get("subtasks") or []]


def _producers(spec: dict) -> dict[str, set[str]]:
    pre = {i: set() for i in _ids(spec)}
    for d in spec.get("deps") or []:
        if str(d.get("to")) in pre and str(d.get("from")) in pre:
            pre[str(d["to"])].add(str(d["from"]))
    return pre


def waves(spec: dict) -> list[list[str]]:
    """The subtasks by the earliest wave they can run in: wave k waits for every producer in waves < k. A Dep cycle
    (CHECK-2's to name) puts its members in no wave."""
    pre, level = _producers(spec), {}

    def lvl(i, path=()):
        """Its wave: one past its latest producer's; None on a ring."""
        if i not in level:
            if i in path:
                return None
            ups = [lvl(p, path + (i,)) for p in pre[i]]
            level[i] = None if None in ups else 1 + max(ups, default=0)
        return level[i]
    for i in pre:
        lvl(i)
    n = max((v for v in level.values() if v), default=0)
    return [[i for i in pre if level.get(i) == k] for k in range(1, n + 1)]


def critical_path(spec: dict) -> list[str]:
    """One longest producer chain, ending in the last wave."""
    pre, ws = _producers(spec), waves(spec)
    at = {i: k for k, w in enumerate(ws) for i in w}
    if not ws:
        return []
    chain = [ws[-1][0]]
    while ups := [p for p in pre[chain[-1]] if at.get(p) == at[chain[-1]] - 1]:
        chain.append(ups[0])
    return chain[::-1]


def _norm(path: str) -> str:
    return str(path).strip().lstrip("./").rstrip("/")


def _owns(writes: set[str], path: str) -> bool:
    """A declared file, or one under a declared directory."""
    p = _norm(path)
    return any(p == w or p.startswith(w + "/") for w in writes)


def seam_problems(spec: dict) -> list[str]:
    """What the seams claim that the plan's own declarations contradict — read part by part, over what each part said: a
    part that declared nothing (a plan written before the field, a child an issuer's repair added by hand) is not judged,
    and leaves every other part judged as before. The declarations ride the graph (`Engine.record_seam_claim`), so a
    plan read back for a refine or a repair is read the same way as the one first authored."""
    kids = {str(k.get("id")): k for k in spec.get("subtasks") or []}
    pre = _producers(spec)

    def upstream(i, seen=None):
        """Every subtask `i` waits on, through any chain of seams."""
        seen = set() if seen is None else seen
        for p in pre[i] - seen:
            seen.add(p)
            upstream(p, seen)
        return seen
    out = _runs_problems(kids, upstream)
    writes = {i: {_norm(w) for w in k.get("writes") or []} for i, k in kids.items() if k.get("writes")}
    named = {w for ws in writes.values() for w in ws}
    dirs = {_norm(w) for k in kids.values() for w in k.get("writes") or [] if str(w).rstrip().endswith("/")} | {
        d for d in named if any(x.startswith(d + "/") for x in named)}   # `tests` beside `tests/x.py` is a directory
    for d in spec.get("deps") or []:
        f, t = str(d.get("from")), str(d.get("to"))
        if f not in writes or t not in kids or "reads" not in d:
            continue
        reads = [r for r in d.get("reads") or [] if str(r).strip()]
        foreign = [r for r in reads if not _owns(writes[f], r)]
        if not reads or foreign:
            out.append(f"seam {f} → {t}: {'names nothing' if not reads else 'names ' + ', '.join(map(str, foreign))} "
                       f"as what {t}'s work reads of {f}, and {f} writes {sorted(writes[f]) or 'no file'}. A seam is "
                       f"{t}'s WORK reading {f}'s output; one that orders the two only so {t}'s CHECK can run makes "
                       f"independent work wait — give {t}'s probes inputs that exercise its own code over what its real "
                       f"producers provide, or move that criterion to the parent; else name the file {t} reads")
    ids = list(writes)
    for a_i, a in enumerate(ids):
        for b in ids[a_i + 1:]:
            # files, not directories: two parts each adding a file under `src/` share no file, and a finding there
            # would push toward the seam that orders them — the opposite of what it is for
            shared = sorted((writes[a] & writes[b]) - dirs)
            if shared and a not in upstream(b) and b not in upstream(a):
                out.append(f"{a} and {b} both write {', '.join(shared)} with no seam ordering them: run at the same "
                           f"time, the later write takes the earlier one's work — give each its own file, or the seam "
                           f"that orders them")
    return out


def _runs_problems(kids: dict, upstream) -> list[str]:
    """§2.7: a criterion whose check runs another part's code references that part's result — a Dep, declared or not.
    Undeclared, the part is checked in a place holding only its own work and what it waits on, and cannot pass (the sql
    lexer, in wave 1 beside the base, probed through `./sql_database` before any parser existed)."""
    out = []
    for i, k in kids.items():
        if foreign := [str(r) for r in k.get("runs") or [] if str(r) in kids and str(r) != i
                       and str(r) not in upstream(i)]:
            out.append(f"{i}'s probes run the code of {', '.join(foreign)}, which {i} does not wait on: it is checked "
                       f"in a place holding only its own work and what it waits on, so those probes cannot pass. Give "
                       f"{i} probes over its own code (a driver over the interfaces the base declares, or inputs only "
                       f"its code decides) and put the behaviour only the whole shows in the parent's criteria — or, "
                       f"where {i}'s WORK really builds on {', '.join(foreign)}, the seam, at a wave's cost")
    return out
