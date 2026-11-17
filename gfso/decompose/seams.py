"""The plan's Dep seams read as what they cost and what they claim — over the spec, before anything is built.

A seam is the claim "the consumer's WORK reads the producer's output" (§2.7): the consumer waits for the producer's
PASS, so every seam on the longest chain is wall time (`waves`). A seam that orders work only so a CHECK can run
makes independent work wait for a verdict it never needed (measured: the sql_database plan chained 12 parts into 8
waves because each part's probes ran the whole binary; its three rows spent 9 h each). So a seam names what of the
producer's files the consumer's work reads, and that claim is checked against the files the producer declares it
writes (`seam_problems`) — a finding for the plan's author, never a refusal: §15.5 admits an edge no criterion
references, and only its author can say what it carries."""
from __future__ import annotations

import re


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


#: the reason a deferral the system writes carries, read by the customer in the plan
DEFERRED = ("larger than one session: its split needs what these deliver — their interfaces, formats, what they turn out "
            "to support — so it is made with their accepted results in hand, not guessed before them (FM-6). The cost: "
            "its split round runs after them, on the critical path; `split_after` with `after: []` takes it back")


def with_deferrals(spec: dict) -> dict:
    """The authored spec with the deferral its author did not write, where it is owed: a part judged larger than one
    session waits, through φ, for every producer of it no criterion names (`model.start_waits`), so its split is made
    after those deliver, with their results in hand (FM-6's remedy, §8.6). Written into the plan, the customer reads it
    and a refine may take it back; the split round then runs after the producers, which the run's time pays. Measured:
    Haiku 5.5's own c_compiler plan judged nine parts larger than a session, consumers all, and deferred none."""
    pre, kids = _producers(spec), []
    for k in spec.get("subtasks") or []:
        i = str(k.get("id"))
        named = {str(c["depends_on"]).rsplit(".", 1)[-1] for c in k.get("criteria") or () if c.get("depends_on")}
        if k.get("fits_one_session") is False and "split_after" not in k and (
                ps := sorted(p for p in pre.get(i, set()) if p.rsplit(".", 1)[-1] not in named)):
            k = {**k, "split_after": {"after": ps, "why": DEFERRED}}
        elif "split_after" in k and not (k["split_after"] or {}).get("after"):
            k = {x: v for x, v in k.items() if x != "split_after"}      # the author said: split it now
        kids.append(k)
    return {**spec, "subtasks": kids} if spec.get("subtasks") else spec


def deferral_problems(spec: dict) -> list[str]:
    """Each part whose split waits (`split_after`) on what is no ground for waiting: a producer the plan does not seam
    into it, or no reason — the admission refuses it (`validation.deferral_refused`), so it is repaired before the
    build, its lift the author's own: name the producer whose result the split needs, or split it now (§12.16 (ii))."""
    return list(refused_deferrals(spec).values())


def refused_deferrals(spec: dict) -> dict[str, str]:
    """{part id: why} for each deferral `deferral_problems` names."""
    pre, out = _producers(spec), {}
    for k in spec.get("subtasks") or []:
        after, i = k.get("split_after") or {}, str(k.get("id"))
        if not after:
            continue
        bad = [str(p) for p in after.get("after") or () if str(p) not in pre.get(i, ())]
        if bad or not after.get("after") or not str(after.get("why") or "").strip():
            out[i] = (f"{i} defers its split on " + (f"{', '.join(bad)}, which no seam makes a producer of {i}" if bad
                      else "no producer" if not after.get("after") else "no reason")
                      + f": a split waits only on a producer {i} consumes, saying what of its result the split needs "
                        f"(FM-6's remedy) — name one in `deps` and `split_after`, or split {i} now and drop `split_after`")
    return out


_PATH = re.compile(r"(?<![\w}/.$-])\./([\w.+-][\w./+-]*)")


def _paths(k: dict) -> set[str]:
    """The `./` paths a part's probes name — what its checks run or read in the work's tree."""
    return {_norm(m) for c in k.get("criteria") or () for p in c.get("check") or ()
            for m in _PATH.findall(str(p.get("command") or ""))}


_IMPORT = re.compile(r"^[ \t]*(?:from[ \t]+([\w.]+)[ \t]+import[ \t]+\(?([\w ,\t]+)|import[ \t]+([\w., \t]+))", re.M)


def _modules(k: dict) -> set[tuple[str, ...]]:
    """The Python modules a part's probes import — in the files pinned beside them and in their commands — each as
    the paths that would define it, the most specific first: `from myre.parser import parse` is `myre/parser/parse`,
    then `myre/parser`. A pin is a file the check runs, so what it imports is what the check runs, whatever `runs`
    declares (a regex engine's parser pins ran `import myre; myre.compile`, whose package the api part wrote last)."""
    texts = [str(p.get("command") or "") for c in k.get("criteria") or () for p in c.get("check") or ()]
    texts += [str(b) for c in k.get("criteria") or () for p in c.get("check") or ()
              for b in ((p.get("inputs") or {}).values() if isinstance(p.get("inputs"), dict) else ())]
    out = set()
    for t in texts:
        for frm, names, plain in _IMPORT.findall(t.replace("\\n", "\n").replace(";", "\n")):
            for m in ([f"{frm}.{n.strip()}" for n in names.split(",") if n.strip()] if frm else
                      [n.strip().split()[0] for n in plain.split(",") if n.strip()]):
                parts = m.split(".")
                out.add(tuple("/".join(parts[:j]) for j in range(len(parts), 0, -1)))
    return out


def _defines(k: dict, module: str) -> bool:
    """The part writes the file that defines the module (`a/b.py`, `a/b/__init__.py`), at the tree's top or under a
    source root (`src/a/b.py`)."""
    return any(w == f or w.endswith("/" + f) for w in (_norm(x) for x in k.get("writes") or [])
               for f in (module + ".py", module + "/__init__.py"))


def _made_by(k: dict, path: str) -> bool:
    """The part writes the path, or the source a program of that name is built from (`tests/drv` from `tests/drv.c`)."""
    ws = {_norm(w) for w in k.get("writes") or []}
    return _owns(ws, path) or any(w.rsplit(".", 1)[0] == path for w in ws if "." in w.rsplit("/", 1)[-1])


def _runs_of(kids: dict, upstream) -> dict[str, set[str]]:
    """Each declaring part's `runs` with what its own checks name: a path another part writes is that part's result
    (§2.7); a program no part writes — the whole's, built of many — runs what EVERY other part probing through it alone
    says it runs, itself included (the c_compiler plumbing, `runs: []`, probed `./c_compiler` that codegen-core and ten
    others said runs lexer → codegen-core; it waited on none and stood BLOCKED five hours) — but never a part that waits
    on this one: what builds on it is no part of its place, so the first of a chain building one program is not judged
    by its successors. One other part saying `runs: []` of it says the program runs nothing of the others — a multi-call
    `./coreutils`, whose `sort` runs `sort-keys` and whose `cat` does not — and nothing is judged; nor is a program no
    part claims anything of: the base may hold it."""
    def rid(r):
        """The part a `runs` entry names — by its id, or its id under the parent's (`root.lexer` is `lexer`)."""
        return next((i for i in kids if str(r) == i or str(r).endswith("." + i)), None)
    said = {i: {x for r in k.get("runs") or [] if (x := rid(r))} for i, k in kids.items()}
    foreign = {i: {p for p in _paths(k) if not _made_by(k, p)} for i, k in kids.items()}
    out = {}
    for i, k in kids.items():
        if "runs" not in k and "writes" not in k:
            continue
        got = set(said[i])
        for p in foreign[i]:
            if makers := {j for j, o in kids.items() if j != i and _made_by(o, p)}:
                got |= makers
            elif ev := [said[j] and said[j] | {j} for j in kids if j != i and foreign[j] == {p} and "runs" in kids[j]]:
                got |= {x for x in set.intersection(*ev) if i not in upstream(x)}
        for cands in _modules(k):
            # the most specific definition some part writes is the module the probe runs
            if makers := next(({j for j, o in kids.items() if _defines(o, m)} for m in cands
                               if any(_defines(o, m) for o in kids.values())), set()):
                got |= makers if i not in makers else set()
        out[i] = got - {i}
    return out


def _runs_problems(kids: dict, upstream) -> list[str]:
    """§2.7: a criterion whose check runs another part's code references that part's result — a Dep, declared or not.
    Undeclared, the part is checked in a place holding only its own work and what it waits on, and cannot pass (the sql
    lexer, in wave 1 beside the base, probed through `./sql_database` before any parser existed)."""
    out = []
    for i, runs in _runs_of(kids, upstream).items():
        if foreign := sorted(runs - upstream(i)):
            out.append(f"{i}'s probes run the code of {', '.join(foreign)}, which {i} does not wait on: it is checked "
                       f"in a place holding only its own work and what it waits on, so those probes cannot pass. Give "
                       f"{i} probes over its own code (a driver over the interfaces the base declares, or inputs only "
                       f"its code decides) and put the behaviour only the whole shows in the parent's criteria — or, "
                       f"where {i}'s WORK really builds on {', '.join(foreign)}, the seam, at a wave's cost")
    return out
