"""What a node's pinned checks print on its place as it stands, observed by the system before an executor session works
it (`observe_place`) — an implementation's own check (§10.2), handed to the session as machine state: no verdict, no
signal, nothing written to the graph or to the place.

On the v17 continuation of sql × haiku 4.5 (GB_sql_database_tnjw8j716) six parts whose work was already there spent
15–49 turns each discovering that, building and running checks the system holds and could have run once. What a session
cannot learn from the packet it buys turn by turn, every turn re-reading its whole context.

Nothing is built for the observation: a pin presupposes a build its procedure does not pin (docs/notes/
VALIDATION_BY_CANON.md, "Where three rounds converged"), so a check over a program the tree has not built — or built
from older sources — shows that, not the work. Hence an observation and never a verdict: the validator builds as the
checks say and decides; the packet says so.

The same runner reads a plan's pins once over the base before the go (`on_the_base`, `cannot_run`): a pin whose text
bash refuses, or whose own fixture the place cannot lay by its name, decides nothing on any work (form item (1),
§20.10) — found by running it
where the checks run, a static imitation of bash's grammar having refused valid commands for five sessions."""
from __future__ import annotations

import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional

from dataclasses import replace

from gfso.config import host_env
from gfso.core.types import IN_THE_WORKS_PATH, INPUTS_TOKEN, PlaceUnavailable
from gfso.adapters.execution import ended_by_watch, past_disk
from gfso import store
from gfso.adapters.snapshots import WATCHED, NotTheDelivery, Uncopied, changed_or_unknown, judged_at, on_disk, snapshot, swap

from gfso.core.protocol.procedure import (PROBE_S, contains, materialize_inputs, probe_id, shows,
                                         unsafe_input_paths)
from gfso.executions import execution_of
from gfso.workspaces import standing

#: Seconds one check may run, and the whole observation of one session's nodes — a quarter of the session's own
#: cap at most (`observe_place`).
OBSERVE_S = 300
#: …and what starting each check from what the system laid costs it, on top of its own run (`_fresh_run`; 2.35 s a
#: check measured, critic B7): the exact checks of a validation are given it each, so a rich contract's are not cut
FRESH_S = 3
#: Characters of a check's output the packet shows — its tail, where a build or a test reports how it ended: every
#: turn of the session re-reads them.
TAIL = 200


def bound_of(p) -> float:
    """The seconds the system's run of probe `p` may take: its issuer's stated bound (`Probe.bound_s`), else the default
    — the one place a run's bound is read, so the runner and the budget a validation gives it cannot disagree."""
    return p.bound_s or PROBE_S


def observing(graph) -> bool:
    """Does this project observe a node's place before a session (`set_mode(observe=)`)? On unless it says no — a
    paired row needs the other arm on the same server."""
    return graph.setting("observe") != "0"


def observe_place(engine, tasks, place: Optional[str], cap: Optional[int] = None) -> dict:
    """{task id: [{criterion, behaviour, command, expect, rc, out, matched, note}]} — every check pinned to `tasks`'
    criteria run once, in contract order, in one checkout of the commit `place` stands on (`workspaces.standing`,
    read by its id: `adapters.snapshots`) with its inputs laid from the contract, where the project's work runs. A
    check run already for an earlier node is not run again. {} where there is
    nothing to observe: no place, nothing in it, the project said no, the copy could not be made — the place itself is never run in,
    the session starts on it."""
    probes = [(t, c, p) for t in tasks for c in t.spec.criteria for p in (c.check or ()) if p.command]
    if not (place and probes and observing(engine.graph)):
        return {}
    ex, budget = execution_of(engine), min(OBSERVE_S, (cap or OBSERVE_S) // 4)
    if not ex.shell():
        return {}
    # …nor a place holding nothing: what each check prints over no work tells a session nothing it does not see, and it
    # cost a person 6:42 of 47 checks before a first line was written (rehearsal, 2026-11-03)
    if not set(ex.files.listdir(place)) - {".git"}:
        return {}
    seen = {}
    with ex.scratch("gfso-observe-", system=True) as tmp:
        try:
            # …the place's commit as it stands, read by its id: never a copy of the live tree
            tree, commit, _ = standing(engine, tasks[0].id, place)
            with snapshot(lambda: store.held(engine, ex, commit, (str(place), ex)), Path(tmp) / "place", ex,
                          delivered=(tree, commit, "")) as tree:
                for t, row in run_checks(ex, probes, place, judged_at(tree, place, ex), budget):
                    seen.setdefault(str(t.id), []).append(row)
        except (Uncopied, NotTheDelivery):   # …an observation, no verdict: the session starts without it
            return {}
    return seen


def run_checks(ex, probes, place: str, tree: Optional[str], budget: float, touched: Optional[set] = None) -> list:
    """[(key, {criterion, behaviour, command, expect, exact, bound_s, bound_supplied, rc, out, printed, matched, note})] —
    each `(key, criterion, probe)` of `probes` run in `tree`, a copy of `place`, with its inputs laid from the contract:
    each distinct command once, its own bound at most (`bound_of`; `bound_supplied` where that is the default, as a
    supplied deadline is logged, §2.5) and `budget` in all — what bounds the caller's state —, matched by `printed`. []
    where nothing can run: no copy, no shell, inputs that cannot be laid as pinned (refused at admission). The one runner of the system's own checks: before a
    session (`observe_place`) and over a fresh copy of a delivery at its validation (`validate._observe_pins`).
    `touched`: gets the delivered files each check changed in its own copy — what a judge running it changes too."""
    if not (tree and probes and (bash := ex.shell())):
        return []
    crits = list({id(c): c for _, c, _ in probes}.values())
    if unsafe_input_paths(crits):                        # …refused at admission: nothing runs over a truncated corpus
        return []
    out, ran, copying = [], {}, []
    base = None
    if touched is not None:          # …the delivered side, read once for every check's copy
        try:
            base = on_disk(tree, ex)
        except Exception:            # noqa: BLE001 — unknown here, read per check as `changed` reads it
            pass
    # …the budget counted from here, as the copies are not: the read above is the system's, and counted it left the
    # first check short of its whole budget by its length — a check whose bound outlasts the budget was then never
    # whole, and re-asked, paid, each time (measured under load, 2026-11-27)
    t0 = time.monotonic()
    for key, c, p in probes:
        row = {"criterion": c.name, "behaviour": p.behaviour, "command": p.command, "expect": p.expect,
               "exact": p.exact, "bound_s": (bound := bound_of(p)), "bound_supplied": p.bound_s is None}
        # …one run per command OVER ITS INPUTS: keyed by the command alone, a second criterion pinning it over other
        # inputs read the first one's output — a false FAIL on correct work, a lost one on wrong work (critic B8); and
        # under its bound, or one stated longer would read a run cut at another's
        if (once := (p.command, p.inputs, bound)) not in ran:
            # …the copies' time not counted: a large delivered tree spent the budget copying, and its later checks —
            # the failing one among them — went unrun, the judge's word deciding (critic B8)
            left = budget - (time.monotonic() - t0 - sum(copying))
            ran[once] = (_fresh_run(ex, bash, c, p, tree, min(bound, left), place, copying, touched,
                                    base) if left >= 1
                         else {"note": "not run: the observation's time ran out"})
            # …not finished in the time it was given — its own bound, or what the observation's budget left it, or none
            # left at all —: it decided nothing in finite time, and the delivery's own code spends that budget, so a
            # looping check placed after slow honest ones fell to "the budget's cause" and the judge's word passed it
            # (critic over the first form, which marked only a check given its whole bound). `with_engine_observations`
            # reads it as ⊥ — no PASS, no FAIL —, and the next validation re-runs only the ⊥ criteria, with the whole budget
            if str(ran[once].get("note", "")).startswith(("did not finish", "not run: the observation's time")):
                # …whole where it had all it could be given — its bound, or the whole budget where that is shorter: a
                # re-ask gives no more, and bounds stated past the validation's own were re-asked, each paid, to its end
                # (critic over the stated bound); one cut behind others is re-run alone next, with the whole budget
                ran[once] = {**ran[once], "timed_out": True, "whole": left >= min(bound, budget) - 1}
        # …matched against THIS check's expectation: one command pinned twice with two expectations printed
        # once, and the second inherited the first's match (critic over 27de5f8)
        got = ran[once]
        out.append((key, {**row, **{k: v for k, v in got.items() if k not in ("stdout", "stderr")},
                          **({"printed": _both(got), "matched": printed(got, p.expect, p.exact)}
                             if "stdout" in got else {})}))
    return out


def _fresh_run(ex, bash: str, c, p, tree: str, timeout: float, place: str, copying: list,
               touched: Optional[set] = None, base: Optional[tuple] = None) -> dict:
    """One check from what the system laid: the copy's container started anew — every process and file an earlier
    check left outside the copy gone with the last one (`release`) —, the pinned inputs laid afresh, as the system's,
    in a directory no earlier check could know the name of. A check runs the delivery's code, and what it left steered
    the next: a `GNUmakefile` beside a pinned `Makefile` (probe), a `diff` laid first on the image's PATH (critic F5);
    and a check that tidied after it was itself a switch the delivery turned to have every later check "not run"
    (critic B6). And over a copy of the built delivery of its own, gone after it: over one they shared, a check that
    ran the delivered code changed what a later one read, and a forced FAIL turned into the judge's word (critic B7)."""
    ex.release(tree)
    t0 = time.monotonic()
    # …in a directory of the system's of its own, its container mounting that alone: under one the copies shared, the
    # first check's code rewrote the built delivery every later one is copied from (a pinned PASS forged, critic, live),
    # and what each left beside its copy outgrew the disk's bound unread (critic, measured). One reading of the disk, by
    # the one write there: ten had cost a person 6:08 of a simple task's checks (rehearsal, 2026-11-03)
    try:
        with ex.scratch("gfso-check-", system=True) as root:
            own, laid = str(Path(root) / "copy"), str(Path(root) / f"inputs-{uuid.uuid4().hex[:12]}")
            with ex.system_writes(root):                # …no check's growth against its disk bound
                try:
                    ex.copy_tree(tree, own)
                except (OSError, subprocess.TimeoutExpired) as e:
                    # …the copy is of the BUILT delivery, whose files are the delivery's to choose: one it makes impossible
                    # to copy (a path past the system's limit) is its FAIL, the cause said — as the checkout's
                    # (`NotTheDelivery`); read as "not observed" it handed every exact check to the judge's word (critic B9)
                    cause = f"the built delivery could not be copied for this check: ...{str(e)[-120:]}"
                    return {"rc": 1, "out": cause, "stdout": "", "stderr": cause}
                try:
                    # …this probe's own inputs alone: every criterion's, laid for each check, cost the square of their number
                    dirs = materialize_inputs([replace(c, check=(p,))], Path(laid), ex.files)
                except (OSError, subprocess.TimeoutExpired) as e:
                    return {"note": f"not run: its inputs could not be laid ({e})"}
            # …nor their time counted: the system's own write left later checks of a rich contract unrun, the judge's word
            # deciding them, as its removal below would (critic B9)
            copying.append(time.monotonic() - t0)
            try:
                d = dirs.get(probe_id(c.name, p))
                got = _run(ex, bash, swap(p.command.replace(INPUTS_TOKEN, d.as_posix()) if d else p.command, place, own),
                           own, timeout, place)
                # …ended by the machine's memory watch: a neighbour's pressure is no observation of this delivery (critic B7)
                if ended_by_watch(ex.session(own)):
                    return {"note": f"not run: {WATCHED}"}
                # …by the disk's: the delivery's own, its cause said, as a build's, where a bare 137 read as any failure
                return {**got, "out": f"the check was ended: {past}"} if (past := past_disk(ex.session(own))) else got
            finally:
                t0 = time.monotonic()
                if touched is not None:
                    touched.update(changed_or_unknown(tree, own, ex, base=base))
    finally:
        copying.append(time.monotonic() - t0)


#: Seconds one pin may run over the base before the go, and all of one authoring round's: the plan is on a person's
#: path (a small task's whole run stated 10–27 min), and over no work a pin fails at once or is cut
BASE_PIN_S, BASE_S = 20, 120


def on_the_base(ex, probes, budget: float = BASE_S) -> dict:
    """{(command, inputs): {rc, out, stdout, stderr} or {note}} — each distinct pin of `probes` [(criterion, probe)] run
    once over a copy of the base `ex` imported (the person's committed tree, before any work), its inputs laid from the
    contract and named `{inputs}` again in what it printed. ONE copy and one container for them all, where an exact check
    of a delivery starts each from what the system laid (`_fresh_run`, 2.35 s a check): over no work, what one pin leaves
    can hide a failure from a later one, never make one — the reader of these (`cannot_run`) only flags. Raises OSError
    (or the execution's own refusal) where the base cannot be copied: then nothing ran."""
    if not (probes and (bash := ex.shell())):
        return {}
    todo = {(p.command, p.inputs): replace(c, check=(p,)) for c, p in probes}
    base, out = str(ex.base), {}
    with ex.scratch("gfso-base-pins-", system=True) as root:
        own = str(Path(root) / "copy")
        with ex.system_writes(root):
            ex.copy_tree(base, own)
            dirs = _laid(ex, Path(root) / f"inputs-{uuid.uuid4().hex[:12]}", todo)
        t0 = time.monotonic()
        try:
            for key, c in todo.items():
                if isinstance(d := dirs[key], dict):
                    out[key] = d
                elif (left := budget - (time.monotonic() - t0)) < 1:
                    out[key] = {"note": f"{NOT_RUN}the time for the plan's pins ran out"}
                else:
                    cmd = c.check[0].command
                    text = swap(cmd.replace(INPUTS_TOKEN, d.as_posix()) if d else cmd, base, own)
                    got = _run(ex, bash, text, own, min(BASE_PIN_S, left), base)
                    if got.get("rc") == 2 and _SYNTAX.search(got.get("stderr") or ""):
                        # …whose words: the pin's own text, or a shell the pin started (`bash -c "[[ $(…) == a ]]"`)
                        got["bash_n"] = _parsed(ex, bash, text, own)
                    out[key] = {k: v.replace(d.as_posix(), INPUTS_TOKEN) if d and isinstance(v, str) else v
                                for k, v in got.items()}
        finally:
            ex.release(own)
    return out


#: the note of a pin whose OWN inputs could not be laid, laid alone — a result of the pin (`cannot_run`), not of the place
NOT_LAID = "its inputs could not be laid"
#: the head of a note of a pin that did not run for the round's reasons — its time, its place — retried by a later round
NOT_RUN = "not run: "


def ran(row: dict) -> bool:
    """Is what this row's pin decides known — it ran, failed on what is its own (its inputs), or bash read its text
    (`parsed`)? Else the place or the time stopped it: nothing of the pin is known."""
    return "rc" in row or "bash_n" in row or str(row.get("note") or "").startswith(("did not finish", NOT_LAID))


def parsed(ex, probes) -> dict:
    """{(command, inputs): {bash_n, stderr} or {note}} — each distinct pin of `probes` [(criterion, probe)] read by
    `bash -n` alone where no place apart from this host holds the project: nothing of it runs — no expansion, no
    program, no file it names — so a text bash refuses is known before the go, while what it does is left to the work
    (the person's word to run agents here covers the work, not a model's text before they read it). No startup file is
    read: an inherited BASH_ENV is the one script a non-interactive bash would source."""
    if not (bash := ex.shell()):
        return {}
    env = {k: v for k, v in host_env().items() if k not in ("BASH_ENV", "ENV")}
    out = {}
    for _, p in probes:
        try:
            r = ex.run([bash, "--norc", "--noprofile", "-O", "extglob", "-n", "-c", p.command], cwd=ex.temp_root(),
                       timeout=10, env=env)
        except (OSError, subprocess.TimeoutExpired) as e:
            out[(p.command, p.inputs)] = {"note": f"{NOT_RUN}bash could not read it ({e})"}
            continue
        # …said as bash in a container says it: this host's bash names itself by its path
        out[(p.command, p.inputs)] = {"bash_n": r.returncode, "stderr": _ITSELF.sub("bash: -c: ", r.stderr or "")}
    return out


_ITSELF = re.compile(r"^[^\n]*?bash(?:\.exe)?: -c: ", re.M)


def _laid(ex, at: Path, todo: dict) -> dict:
    """{key: its inputs' directory, None where it pins none, or {note} where they could not be laid} — every pin's in one
    write (one call into the container: laid apart, 20 pins took 25 s, together 17 s, measured), each apart only where that
    write failed, so one fixture that cannot be laid is said as its own and no other's. The place failing (`PlaceUnavailable`,
    a write cut by its time) is no pin's: its rows are not run."""
    def lay(cs, where: Path):
        """{key: directory} of `cs`' inputs laid under `where`."""
        got = materialize_inputs(cs, where, ex.files)
        return {k: got.get(probe_id(c.name, c.check[0])) for k, c in todo.items() if c in cs}

    def placed(e) -> dict:
        """The row of a pin whose inputs the place, not the pin, failed to lay."""
        return {"note": f"{NOT_RUN}the place could not lay its inputs ({e})"}
    try:
        return lay(list(todo.values()), at)
    except (PlaceUnavailable, subprocess.TimeoutExpired) as e:
        return {k: placed(e) for k in todo}
    except (OSError, ValueError):
        out = {}
        for n, (k, c) in enumerate(todo.items()):
            try:
                out |= lay([c], Path(f"{at}-{n}"))     # …beside what the failed write left, never over it
            except ValueError as e:                    # …a path the procedure refuses to lay: the pin's own name
                out[k] = {"note": f"{NOT_LAID} ({e})"}
            except (OSError, subprocess.TimeoutExpired) as e:
                # …the pin's only where the place names its file's NAME (s16b's 300-byte fixture: tar's "File name too
                # long"); no space, a cut exec, an absent daemon are the place's, whatever pin they met
                out[k] = ({"note": f"{NOT_LAID} ({e})"} if not isinstance(e, PlaceUnavailable) and _NAME.search(str(e))
                          else placed(e))
        return out


#: what the place says of a file NAME it cannot lay — the pin's own, where it lays that pin's inputs alone
_NAME = re.compile(r"File name too long|ENAMETOOLONG")


def _parsed(ex, bash: str, cmd: str, tree: str) -> Optional[int]:
    """`bash -n`'s exit over the pin's text where it ran: 2 when bash refuses the text itself; None where it gave none.
    extglob is on for the parse: a `shopt -s extglob` the run takes is off while bash -n reads the whole text, and a
    sound pin using it with a nested shell over no work was refused by both halves of the rule (critic r4)."""
    try:
        return ex.session(tree).run([bash, "-O", "extglob", "-n", "-c", cmd], cwd=tree, timeout=10).returncode
    except (OSError, subprocess.TimeoutExpired):
        return None


#: bash's own refusal of a command's text — before any of it runs, whatever the work built
_SYNTAX = re.compile(r"^bash: -c: line \d+: (?:syntax error|unexpected EOF)", re.M)
#: …said in all bash's lines about the text: the error, and the line it was in
_SAID = re.compile(r"^bash: -c: line \d+: .*$", re.M)
#: bash's own word that a program it was told to start is not there or not runnable
_NOT_FOUND = re.compile(r"^bash: (?:line \d+: )?(?P<program>[^:\n]+): (?:command not found|Permission denied)$", re.M)
def cannot_run(row: dict) -> Optional[str]:
    """The place's or bash's own message of a pin that can run on no work, as the tool itself says it — nothing read
    into its output: its own input file the place refused to lay by its name, or its text that `bash -n` refuses
    (`bash_n` 2) where the run ended 2 on bash's syntax line. Both, since either alone misreads: a shell the pin
    started refuses ITS text over no work (`bash -c "[[ $(./wordtop) == a ]]"`, `bash -n` 0), and `bash -n` refuses a
    text a run accepts (`shopt -s extglob` then `!(x)`, run 0 — the parse now takes extglob too). A text read and not
    run (`parsed`, no `rc`) has only bash's word: flagged on it. None for any other run: a pin is not expected to pass
    over no work; a failed redirect, a missing program, are no such run — the pin may yet go on, or put the program
    there (`missing_program`): three rounds of reading output flagged sound pins (critics)."""
    note, err = str(row.get("note") or ""), (row.get("stderr") or "").replace(IN_THE_WORKS_PATH, "")
    if note.startswith(NOT_LAID):
        return note
    if row.get("rc", 2) == 2 and row.get("bash_n") == 2 and _SYNTAX.search(err):
        return " ".join(_SAID.findall(err))[:400]
    return None


def missing_program(row: dict) -> Optional[str]:
    """The program, named bare, that bash said is not there when the pin ended on it (126/127) — information for the
    plan's reader, never a flag: over no work it may be one the work or the pin itself puts there."""
    err = (row.get("stderr") or "").replace(IN_THE_WORKS_PATH, "")
    if row.get("rc") in (126, 127):
        return next((m["program"].strip() for m in _NOT_FOUND.finditer(err) if "/" not in m["program"]), None)
    return None


def printed(got: dict, expect: str, exact: bool = True) -> bool:
    """Does a run show `expect` as a reader of its terminal would: its standard output alone, or followed by its errors
    — a program's `Error: …` goes to stderr, and a validator's shell shows both (a false FAIL on correct work, critic
    over 38c16f9). Two separate pipes do not keep how the streams interleaved: an output that alternates them is
    pinned with `2>&1` in its command. `exact`: the whole of it (`shows`); else a part of it (`contains`)."""
    return any((shows if exact else contains)(o, expect) for o in (got["stdout"], _both(got)))


def _both(got: dict) -> str:
    return f"{got['stdout']}\n{got['stderr']}"


def _run(ex, bash: str, cmd: str, tree: str, timeout: float, place: str) -> dict:
    """One check's observation: its exit code, its streams and the tail of all it printed, the copy's path named as the
    place throughout — an expect naming a path in the place reads it there — or why it gave no observation."""
    try:
        # in the copy's own container (`ExecutionPort.session`): a check runs what the agents wrote — the plan's probe,
        # the delivery's scripts — and in the project's container that would reach every node's place (critic over
        # SECURITY.md); there it writes its copy alone
        r = ex.session(tree).run([bash, "-c", IN_THE_WORKS_PATH + cmd], cwd=tree, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"note": f"did not finish in {int(timeout)} s"}
    except OSError as e:
        return {"note": f"could not run ({e})"}
    o, e = (swap(x or "", tree, place) for x in (r.stdout, r.stderr))
    out = "\n".join(x.strip() for x in (o, e) if x.strip())
    return {"rc": r.returncode, "out": out[-TAIL:], "stdout": o, "stderr": e}
