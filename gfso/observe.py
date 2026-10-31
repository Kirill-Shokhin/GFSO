"""What a node's pinned checks print on its place as it stands, observed by the system before an executor session works
it (`observe_place`) — an implementation's own check (§10.2), handed to the session as machine state: no verdict, no
signal, nothing written to the graph or to the place.

On the v17 continuation of sql × haiku 4.5 (GB_sql_database_tnjw8j716) six parts whose work was already there spent
15–49 turns each discovering that, building and running checks the system holds and could have run once. What a session
cannot learn from the packet it buys turn by turn, every turn re-reading its whole context.

Nothing is built for the observation: a pin presupposes a build its procedure does not pin (docs/notes/
VALIDATION_BY_CANON.md, "Where three rounds converged"), so a check over a program the tree has not built — or built
from older sources — shows that, not the work. Hence an observation and never a verdict: the validator builds as the
checks say and decides; the packet says so."""
from __future__ import annotations

import subprocess
import time
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Optional

from dataclasses import replace

from gfso.adapters.execution import ended_by_watch
from gfso.adapters.snapshots import WATCHED, snapshot, swap
from gfso.core.protocol.procedure import INPUTS_TOKEN, materialize_inputs, probe_id, shows, unsafe_input_paths
from gfso.workspaces import execution_of

#: Seconds one check may run, and the whole observation of one session's nodes — a quarter of the session's own
#: cap at most (`observe_place`).
PROBE_S, OBSERVE_S = 60, 300
#: …and what starting each check from what the system laid costs it, on top of its own run (`_fresh_run`; 2.35 s a
#: check measured, critic B7): the exact checks of a validation are given it each, so a rich contract's are not cut
FRESH_S = 3
#: Characters of a check's output the packet shows — its tail, where a build or a test reports how it ended: every
#: turn of the session re-reads them.
TAIL = 200


def observing(graph) -> bool:
    """Does this project observe a node's place before a session (`set_mode(observe=)`)? On unless it says no — a
    paired row needs the other arm on the same server."""
    return graph.setting("observe") != "0"


def observe_place(engine, tasks, place: Optional[str], cap: Optional[int] = None) -> dict:
    """{task id: [{criterion, behaviour, command, expect, rc, out, matched, note}]} — every check pinned to `tasks`'
    criteria run once, in contract order, in one copy of `place` (`adapters.snapshots`) with its inputs laid from the
    contract, where the project's work runs. A check run already for an earlier node is not run again. {} where there is
    nothing to observe: no place, the project said no, the copy could not be made — the place itself is never run in,
    the session starts on it."""
    probes = [(t, c, p) for t in tasks for c in t.spec.criteria for p in (c.check or ()) if p.command]
    if not (place and probes and observing(engine.graph)):
        return {}
    ex, budget = execution_of(engine), min(OBSERVE_S, (cap or OBSERVE_S) // 4)
    if not ex.shell():
        return {}
    seen = {}
    with ex.scratch("gfso-observe-", system=True) as tmp:
        with snapshot(place, Path(tmp) / "place", ex) as tree:
            for t, row in run_checks(ex, probes, place, tree, tmp, budget):
                seen.setdefault(str(t.id), []).append(row)
    return seen


def run_checks(ex, probes, place: str, tree: Optional[str], tmp, budget: float) -> list:
    """[(key, {criterion, behaviour, command, expect, exact, rc, out, matched, note})] — each `(key, criterion, probe)`
    of `probes` run in `tree`, a copy of `place`, with its inputs laid from the contract under `tmp`: each distinct
    command once, PROBE_S at most and `budget` in all, matched by `printed`. [] where nothing can run: no copy, no shell,
    inputs that cannot be laid as pinned (refused at admission). The one runner of the system's own checks: before a
    session (`observe_place`) and over a fresh copy of a delivery at its validation (`tools_llm._observe_exact`)."""
    if not (tree and probes and (bash := ex.shell())):
        return []
    crits = list({id(c): c for _, c, _ in probes}.values())
    if unsafe_input_paths(crits):                        # …refused at admission: nothing runs over a truncated corpus
        return []
    out, ran, t0, copying = [], {}, time.monotonic(), []
    for key, c, p in probes:
        row = {"criterion": c.name, "behaviour": p.behaviour, "command": p.command, "expect": p.expect,
               "exact": p.exact}
        # …one run per command OVER ITS INPUTS: keyed by the command alone, a second criterion pinning it over other
        # inputs read the first one's output — a false FAIL on correct work, a lost one on wrong work (critic B8)
        if (once := (p.command, p.inputs)) not in ran:
            # …the copies' time not counted: a large delivered tree spent the budget copying, and its later checks —
            # the failing one among them — went unrun, the judge's word deciding (critic B8)
            left = budget - (time.monotonic() - t0 - sum(copying))
            ran[once] = (_fresh_run(ex, bash, c, p, tree, tmp, min(PROBE_S, left), place, copying) if left >= 1
                         else {"note": "not run: the observation's time ran out"})
        # …matched against THIS check's expectation: one command pinned twice with two expectations printed
        # once, and the second inherited the first's match (critic over 27de5f8)
        got = ran[once]
        out.append((key, {**row, **{k: v for k, v in got.items() if k not in ("stdout", "stderr")},
                          **({"matched": printed(got, p.expect)} if "stdout" in got else {})}))
    return out


def _fresh_run(ex, bash: str, c, p, tree: str, tmp, timeout: float, place: str, copying: list) -> dict:
    """One check from what the system laid: the copy's container started anew — every process and file an earlier
    check left outside the copy gone with the last one (`release`) —, the pinned inputs laid afresh, as the system's,
    in a directory no earlier check could know the name of. A check runs the delivery's code, and what it left steered
    the next: a `GNUmakefile` beside a pinned `Makefile` (probe), a `diff` laid first on the image's PATH (critic F5);
    and a check that tidied after it was itself a switch the delivery turned to have every later check "not run"
    (critic B6). And over a copy of the built delivery of its own, gone after it: over one they shared, a check that
    ran the delivered code changed what a later one read, and a forced FAIL turned into the judge's word (critic B7)."""
    ex.release(tree)
    own = str(Path(tmp) / f"run-{uuid.uuid4().hex[:12]}")
    t0 = time.monotonic()
    try:
        with ex.system_writes(own):        # …the system's copy, no check's growth against its disk bound
            ex.copy_tree(tree, own)
    except (OSError, subprocess.TimeoutExpired) as e:
        # …the copy is of the BUILT delivery, whose files are the delivery's to choose: one it makes impossible to copy
        # (a path past the system's limit) is its FAIL, the cause said — as the checkout's (`NotTheDelivery`); read as
        # "not observed" it handed every exact check to the judge's word (critic B9)
        cause = f"the built delivery could not be copied for this check: ...{str(e)[-120:]}"
        return {"rc": 1, "out": cause, "stdout": "", "stderr": cause}
    finally:
        copying.append(time.monotonic() - t0)
    try:
        # …this probe's own inputs alone: every criterion's, laid for each check, cost the square of their number
        with ex.system_writes(laid := str(Path(tmp) / f"inputs-{uuid.uuid4().hex[:12]}")):
            dirs = materialize_inputs([replace(c, check=(p,))], Path(laid), ex.files)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"note": f"not run: its inputs could not be laid ({e})"}
    try:
        d = dirs.get(probe_id(c.name, p))
        got = _run(ex, bash, swap(p.command.replace(INPUTS_TOKEN, d.as_posix()) if d else p.command, place, own), own,
                   timeout, place)
        # …ended by the machine's memory watch: a neighbour's pressure is no observation of this delivery (critic B7)
        return {"note": f"not run: {WATCHED}"} if ended_by_watch(ex.session(own)) else got
    finally:
        t0 = time.monotonic()
        with suppress(OSError):
            ex.remove_tree(own)
        copying.append(time.monotonic() - t0)            # …its removal no more counted than its copy (critic B9)


def printed(got: dict, expect: str) -> bool:
    """Does a run show `expect` as a reader of its terminal would: its standard output alone, or followed by its errors
    — a program's `Error: …` goes to stderr, and a validator's shell shows both (a false FAIL on correct work, critic
    over 38c16f9). Two separate pipes do not keep how the streams interleaved: an output that alternates them is
    pinned with `2>&1` in its command."""
    return shows(got["stdout"], expect) or shows(f"{got['stdout']}\n{got['stderr']}", expect)


def _run(ex, bash: str, cmd: str, tree: str, timeout: float, place: str) -> dict:
    """One check's observation: its exit code, its streams and the tail of all it printed, the copy's path named as the
    place throughout — an expect naming a path in the place reads it there — or why it gave no observation."""
    try:
        # in the copy's own container (`ExecutionPort.session`): a check runs what the agents wrote — the plan's probe,
        # the delivery's scripts — and in the project's container that would reach every node's place (critic over
        # SECURITY.md); there it writes its copy alone
        r = ex.session(tree).run([bash, "-c", cmd], cwd=tree, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"note": f"did not finish in {int(timeout)} s"}
    except OSError as e:
        return {"note": f"could not run ({e})"}
    o, e = (swap(x or "", tree, place) for x in (r.stdout, r.stderr))
    out = "\n".join(x.strip() for x in (o, e) if x.strip())
    return {"rc": r.returncode, "out": out[-TAIL:], "stdout": o, "stderr": e}
