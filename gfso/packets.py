"""What each LLM role is handed: the executor's packet for one node (`_executor_packet`) or for a scope one session
carries (`_scope_packet`, in `_scope_order`), and the validator's for a node (`_validator_packet`) or a scope
(`_scope_validator_packet`) — the contract's criteria, the upstream results, the rework's failed criteria. Text only:
no graph writes, no signals."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

from gfso.core.protocol.procedure import INPUTS_TOKEN, laid, materialize_inputs, probe_id, unrerunnable
from gfso.core.types import Signal, TaskId, set_aside_of
from gfso.engine import Engine
from gfso.workspaces import _unjoined_text, base_of


def _executor_inputs(criteria) -> dict:
    """{probe id: a copy of its pinned inputs} for the executor, laid down from the contract outside its place.

    The inputs are part of what will be RUN, so part of the contract the executor is held to (Inv-1); named without
    their contents, the root executor of c_compiler searched the file system for them and read the plan's own copies
    (EVIDENCE_LOG §13.34). The validator still lays its own from the contract, so nothing done to this copy reaches a verdict."""
    return (materialize_inputs(criteria, tempfile.mkdtemp(prefix="gfso-check-inputs-"))
            if any(p.inputs for c in criteria or () for p in (c.check or ())) else {})


def _crit_line(c, dirs: dict) -> str:
    """One criterion as the executor reads it — with the procedure that will decide it.

    Pre-registration means something only if the side being held to it can READ it: the contract says
    what will be RUN, written before the work, so the executor builds against the check rather than
    against its own reading of the criterion."""
    def _probe(p) -> str:
        d = dirs.get(probe_id(c.name, p))
        cmd = p.command.replace(INPUTS_TOKEN, d.as_posix()) if d else p.command
        return (f"    - will be checked by — {p.behaviour}: `{cmd}` → must show: {p.expect}"
                + (f" (`{{inputs}}` = {d.as_posix()}: the {len(p.inputs)} file(s) pinned with the check — read them, "
                   f"never write there; the validator lays its own copy from the contract)" if d else ""))
    return "\n".join([f"- **{c.name}**: {c.description}"] + [_probe(p) for p in (c.check or ())])


def _upstream(engine, task, inside=frozenset()):
    """(edge, its producer's label, its producer) for every Dep seam the node consumes from outside `inside` — a
    scope's own seams are its listed nodes. One walk for both roles: the executor reads each producer's delivery,
    the validator checks the seam against it."""
    for e in engine.get_dependencies():
        if str(e.to_id) == str(task.id) and str(e.from_id) not in inside:
            prod = engine.graph.get_task(TaskId(e.from_id))
            yield e, (prod.label() if prod else "?"), prod


def _glue(e) -> str:
    return f" — glue: {e.glue}" if e.glue else ""


def _upstream_lines(engine, task, inside=frozenset()) -> list:
    """The inputs a node consumes — each producer's REAL delivery — from outside `inside` only."""
    return [f"- input from `{e.from_id}` ({name}){_glue(e)}\n  its DELIVER: "
            f"{_last_deliver_result(engine, TaskId(e.from_id)) or '(not delivered yet)'}"
            for e, name, _ in _upstream(engine, task, inside)]


def _working_directory(workdir: Optional[str], validating: bool = False) -> str:
    """The one place a role works in. A contract can name a directory too — the harness or a user writes one into the
    goal — and an executor told only "Working directory: <base>" by its contract wrote into the user's base, whose
    uncommitted edits then refused the join while the signed branch lacked them (2026-10-07). The place is the
    system's to say; whatever the contract names is not it. Writing is what the place bounds, not reading: a node's
    place is a checkout of the base as COMMITTED, so the base's committed paths are the same paths here, and what the
    base holds beyond its commits is read there (critics, 2026-10-08: a reader told only "not yours" disputes a
    contract it could fulfil; one told "the same path here" looks for an ignored data file the checkout lacks)."""
    if validating:   # where a validator stands may be the roster's guess (`validator_workdir`): only a node's place,
        # the system's own answer, is asserted — "the delivery is HERE" over a guess drove a false FAIL (critic 3)
        return f"Working directory for your tools: {workdir}\n{checkout_note(workdir)}"
    here = workdir or os.getcwd()
    return (f"Working directory: {here}\nWrite only here and below: this directory is your place in the plan, and the "
            f"plan takes your delivery from it. Any other directory the contract or its statement names you may read, "
            f"never write.\n{checkout_note(here)}")


def checkout_note(here: Optional[str]) -> str:
    """A node's place checks out its base as committed when the place was made: those paths are here, the rest of the
    base is read there."""
    base = base_of(here)
    return (f"This directory is a checkout of `{base}` as committed when it was made: a path the contract names under "
            f"`{base}` is the same path here. What is not here — uncommitted edits, untracked or ignored files, later "
            f"commits — read in `{base}` if you need it; nothing is ever written there.\n" if base else "")


def _executor_packet(engine, task, workdir: str | None, unjoined: list = ()) -> str:
    """The executor's self-contained contract (it has no graph access): spec + criteria + upstream
    inputs (the REAL delivered outputs it consumes) + ACCEPTED_RISKS + rework feedback if any."""
    tid = str(task.id)
    dirs = _executor_inputs(task.spec.criteria)
    crits = "\n".join(_crit_line(c, dirs) for c in task.spec.criteria) or "- (none)"
    ups = _upstream_lines(engine, task)
    # THE OTHER NODES OF THIS PLAN, by id. The packet listed only DECLARED upstream deps, so an
    # executor blocked on work a SIBLING owns had no id to name — and `blocker_task_ids`, the field
    # that records a DISCOVERED dependency and feeds q_Dep, stayed empty. Measured twice on
    # 2026-08-21: a README node spawned into an empty directory and blocked in prose ("workdir is
    # completely empty"), and a packaging node needed a `__main__.py` another child was writing. Both
    # were real Dep edges the plan never declared, and both went unrecorded because whoever
    # discovered them had nothing to point at.
    sibs = []
    parent = engine.graph.get_parent(task.id)
    for k in (engine.graph.get_active_children(parent.id) if parent is not None else ()):
        if str(k.id) != tid:
            sibs.append(f"- `{k.id}` ({k.label()}) — {k.state.name}")
    negl = "\n".join(f"- {n.item}" for n in set_aside_of(task))
    rework = _rework_section(engine, task)
    return (f"# Your node: {tid} — {task.spec.name}\n\n{task.spec.description}\n\n"
            f"## Criteria (your ENTIRE obligation; each must really hold)\n{crits}\n\n"
            f"## Inputs (upstream deliveries you consume — use the REAL outputs, no stubs)\n"
            f"{chr(10).join(ups) or '- none'}\n\n"
            f"## ACCEPTED_RISKS (declared plan assumptions — do not gold-plate against these)\n"
            f"{negl or '- none'}\n\n"
            f"## The other nodes of this plan — NOT your work, and you must not do it\n"
            f"They are here for one reason: if you cannot proceed because something one of them owns "
            f"does not exist yet, report `status: \"blocked\"` and NAME it in `blocker_task_ids`. That "
            f"is a real dependency the plan did not declare, and naming it is what records it.\n"
            f"{chr(10).join(sibs) or '- none'}\n{rework}{_unjoined_text(unjoined)}\n"
            + _working_directory(workdir))


def _rework_section(engine, task) -> str:
    """What failed on this node's contract and why — the order to fix it, or the history a new version keeps."""
    rework = ""
    if engine.in_rework(task):
        failed = next((list(a.failed_criteria) for a in reversed(engine.audit_log(task.id))
                       if a.signal == Signal.FAIL and not a.rejected and a.failed_criteria), [])
        # …WITH WHY: the validator's evidence and the probes that refuted each one. Names alone sent the executor
        # back to its packet's own checks, which were green, and it re-delivered the unchanged file (2026-09-27)
        through = _failed_through_parts(engine, task, failed)
        own = [f for f in failed if f not in through]
        rework = (f"\n## REWORKING (iteration {task.iteration})"
                  + (" — the validator FAILED these criteria; fix exactly them.\n" + _why_it_failed(engine, task, own)
                     if own else "\n")
                  + (_through_parts_text(through) if through else ""))
    elif (last := next((a for a in reversed(engine.audit_log(task.id))
                        if a.signal == Signal.FAIL and not a.rejected and a.failed_criteria), None)):
        # A new version (an escalation's re-ASSIGN, a raised bound) re-validates nothing by itself: that
        # FAIL is settled on the earlier version, so it is history here, not a rework order — but an
        # executor resuming without it restarts blind on the criteria that already failed once, and the next
        # PASS still re-runs every probe that refuted them.
        # …of a criterion still carried, and only while something of it binds the next PASS (`rework_findings`)
        binding = {c for c, ev, cmds in engine.rework_findings(task.id) if ev or cmds}
        if still := [f for f in last.failed_criteria if f in {c.name for c in task.spec.criteria} and f in binding]:
            rework = ("\n## An earlier version of this contract was FAILED on these criteria, which it "
                      "still carries — the delivery must meet them (observed on that version):\n"
                      + _why_it_failed(engine, task, still))
    return rework


def _failed_through_parts(engine, task, failed: list) -> dict:
    """{criterion: [its parts]} for the failed criteria the standing FAIL of this whole cited only because a part
    they are mapped to failed (Thm 1; Inv-3: a FAIL names criteria) — as recorded when that FAIL was signed, never
    inferred: a FAIL of another origin (a holder's, by hand) is read as what it is."""
    return {c: ks for c, ks in engine.failed_through_parts(task.id).items() if c in failed}


def _through_parts_text(through: dict) -> str:
    """The rework order for a whole failed by its parts: nothing of its own to fix; re-delivered with them."""
    kids = sorted({k for ks in through.values() for k in ks})
    return (f"It FAILED through its part(s) {', '.join(f'`{k}`' for k in kids)}: a whole is not attained while a "
            f"part fails (Thm 1). Its own check PASSED the criteria below, which it carries through those parts: "
            f"nothing of the whole's own is to fix for them. It is re-delivered once those parts have PASSED, over "
            f"the result as it then stands — a report on it before that is held back.\n"
            + "".join(f"- {c} (through {', '.join(f'`{k}`' for k in ks)})\n" for c, ks in through.items()))


def _why_it_failed(engine, task, failed: list) -> str:
    """Per failed criterion, what the validator observed and every probe that has refuted it, each as written."""
    why = {c: (ev, cmds) for c, ev, cmds in engine.rework_findings(task.id)}
    out = [("The validator's probes are not the checks above. Run the ones below before you deliver — every probe "
            "that has refuted a criterion; what it observed says which still do. Each is ONE instance: the "
            "criterion is what must hold, and the validator probes beyond these. A probe that asks for what the "
            "criterion as written does not — another node's scope, a requirement no criterion of yours states — is a "
            "finding you dispute, not a dependency: report `status: \"challenge\"` naming that finding by its id "
            "(listed below) and why it lies outside the criterion — your issuer rules on it, and only his ruling "
            "retires it; `blocked` is for another node's output you really need.")]
    standing = engine.regression_probes(task.id)
    workdir = (engine.get_exec_verdict(task.id) or {}).get("workdir")
    settled = engine.rework_settled(task.id)
    for f in failed:
        ev, cmds = why.get(f, ("", []))
        out.append(f"- {f}" + (f"\n  what it observed: {ev}" if ev else "")
                   + (f"\n  settled, NOT demanded — the next PASS does not run them; nothing to dispute: "
                      f"{', '.join(settled[f])}" if settled.get(f) else "")
                   + "".join(f"\n  probe:\n  ```\n  {cmd.replace(chr(10), chr(10) + '  ')}\n  ```" for cmd in cmds)
                   + "".join(f"\n  standing finding [{p.get('id')}]: `{p.get('seen') or p.get('as_run')}`"
                             + (f" — {why_not}: shown, not demanded" if (why_not := unrerunnable(
                                 p, engine.layable(task.id), workdir)) else "")
                             for p in standing.get(f, ())))
    return "\n".join(out) + "\n"


#: The states in which a node's work is still to be done — what an executor session is handed.
_EXECUTOR_STATES = ("OFFERED", "EXECUTING", "REWORKING")


def _scope_order(engine, members: list) -> list:
    """The scope's nodes in the order they are built: every part before the whole it composes into, every Dep
    producer before its consumer — a node is listed once all it waits on inside the scope is."""
    ids = {str(m.id) for m in members}
    deps = [(str(e.from_id), str(e.to_id)) for e in engine.adopted_dependencies() if str(e.from_id) in ids]
    waits = {str(m.id): {str(k.id) for k in engine.graph.get_active_children(m.id)} | {f for f, t in deps if t == str(m.id)}
             for m in members}
    order, done, rest = [], set(), list(members)
    while rest:
        # a cycle the plan gate refuses cannot reach here; were it to, the rest keep their listed order
        m = next((m for m in rest if waits[str(m.id)] <= done), rest[0])
        order.append(m)
        done.add(str(m.id))
        rest.remove(m)
    return order


def _scope_node_block(engine, i: int, t, top, inside: frozenset) -> str:
    """One node of a scope session's packet: its contract, its inputs from outside the scope, its rework."""
    parent = engine.graph.get_parent(t.id)
    role = "the scope's top — the whole" if str(t.id) == str(top.id) else f"a part of `{parent.id}`"
    head = f"## {i}. `{t.id}` — {t.spec.name} ({role})\n\n{t.spec.description}\n\n"
    if t.state.name not in _EXECUTOR_STATES:
        return head + f"Already {t.state.name}: delivered earlier — listed for context, not yours to redo.\n"
    ups = "\n".join(_upstream_lines(engine, t, inside)) or "- none"
    negl = "\n".join(f"- {n.item}" for n in set_aside_of(t)) or "- none"
    dirs = _executor_inputs(t.spec.criteria)
    crits = "\n".join(_crit_line(c, dirs) for c in t.spec.criteria) or "- (none)"
    return (head + f"### Criteria of `{t.id}` — its ENTIRE obligation; the scope's validation runs each\n"
            f"{crits}\n\n"
            f"### Inputs from outside your scope (the REAL outputs, no stubs)\n{ups}\n\n"
            f"### ACCEPTED_RISKS (declared plan assumptions — do not gold-plate against these)\n{negl}\n"
            f"{_rework_section(engine, t)}")


def _scope_packet(engine, top, order: list, workdir: str | None, unjoined: list = ()) -> str:
    """The scope session's contract: every node of the scope in build order, each with its criteria as the
    checklist its validation runs, its inputs from outside the scope and its rework feedback — and the plan's
    nodes outside the scope, to name when blocked on one."""
    inside = frozenset(str(m.id) for m in order)
    parent = engine.graph.get_parent(top.id)
    others = "\n".join(f"- `{k.id}` ({k.label()}) — {k.state.name}"
                       for k in (engine.graph.get_active_children(parent.id) if parent is not None else ())
                       if str(k.id) not in inside) or "- none"
    return (f"# Your scope: {top.id} — {top.spec.name}\n\n"
            f"You hold the {len(order)} nodes below as ONE piece of work. Build them in the order listed — "
            f"the parts before the whole they compose into, a producer before its consumer — and report on "
            f"each node that is yours to do, one entry per node, `task_id` naming it.\n\n"
            + "\n".join(_scope_node_block(engine, i, t, top, inside) for i, t in enumerate(order, 1))
            + f"\n## The other nodes of this plan — NOT your work, and you must not do it\n"
            f"If you cannot proceed because something one of them owns does not exist yet, report that node "
            f"`status: \"blocked\"` and NAME it in `blocker_task_ids`.\n{others}\n{_unjoined_text(unjoined)}\n"
            + _working_directory(workdir))


def _regression_line(p: dict, dirs: dict, workdir: Optional[str] = None) -> str:
    """One once-refuting probe, shown over this round's inputs directories and asked for under its id."""
    cmd = laid(p.get("as_run") or p.get("command", ""), dirs)
    orphan = f"({why} — shown, not demanded) " if (why := unrerunnable(p, dirs, workdir)) else ""
    return (f"    - REGRESSION [{p.get('id')}] (this probe REFUTED this criterion in an earlier round — re-run "
            f"it and report it under this id) — {p.get('behaviour')}: run `{cmd}` {orphan}"
            f"(recorded then: «{p.get('expect')}», which may be what was required or what was "
            f"seen — decide from what it prints now against the criterion's own requirement)")


def owed_probes(engine: Engine, task, crits) -> list:
    """[(criterion, [(probe id, what to show)…])] — what validating `crits` of `task` OWES, criterion by criterion: its
    pinned probes, the pinned probes of the DONE parts it rests on, and the probes that once refuted it.

    A part's probe is owed ONCE, under the first criterion resting on it: one observation serves every criterion on
    it (`procedure.part_credit`). What to show is a (criterion, probe, is a part's) triple for a pinned probe and the
    stored probe for a regression line. THE one enumeration: the packet writes it out and the batching counts it."""
    tid = TaskId(str(task.id))
    reg, parts = engine.regression_probes(tid), engine.parts_procedure(tid)
    shown: set = set()
    out = []
    for c in crits:
        own = [(probe_id(c.name, p), (c, p, False)) for p in (c.check or ())]
        mine = [(pid, (pc, p, True)) for pc in parts.get(c.name, ()) for p in (pc.check or ())
                if p.command.strip() and (pid := probe_id(pc.name, p)) not in shown and not shown.add(pid)]
        pinned = {pid for pid, _ in own}
        out.append((c, own + mine + [(p.get("id"), p) for p in reg.get(c.name, ()) if p.get("id") not in pinned]))
    return out


def _criteria_text(engine: Engine, task, crits, scratch: Optional[str], workdir: Optional[str] = None,
                   carry: Optional[dict] = None) -> str:
    """The criteria one run validates, each with the pinned probes it must run and the once-refuting probes it
    must re-run — over this round's inputs directories, laid down under `scratch` from the contract.

    `carry`: {probe id: the criterion it is written under} for the probes THIS run carries, when one validation is
    split between runs by what it owes (`tools_llm._scope_batches`); None = everything `owed_probes` lists."""
    tid = str(task.id)
    # THE PROCEDURE EACH CRITERION PINS, handed over as part of the contract. It is not advice: a
    # PASS that skips a pinned probe is refused at the record, so the validator has to see them — and
    # seeing them is also what stops it re-inventing a weaker set of its own (A1/§2, Inv-1 §12.3).
    # …AND THE PINNED PROCEDURE OF EVERY DONE PART, under the criterion of this node it rests on: a part's PASS
    # was on its own delivery, and this one may have rewritten it (`validation.parts_procedure`).
    _retired = engine.retired_findings(TaskId(tid))
    _parts = engine.parts_procedure(TaskId(tid))
    _all = engine.validation_procedure(TaskId(tid))
    # A probe's INPUTS are laid down here, from the contract, by the system — never read from the
    # delivery, where the executor could have grown them (the corpus that moved under `c_compiler`).
    _dirs = (materialize_inputs(_all, Path(scratch) / "probe_inputs" if scratch
                                else tempfile.mkdtemp(prefix="gfso-probe-inputs-"))
             if any(p.inputs for c in _all for p in (c.check or ())) else {})
    owed = owed_probes(engine, task, crits)
    if carry is None:
        carry = {pid: c.name for c, items in owed for pid, _ in items}

    def _probe_line(c, p, part: bool = False) -> str:
        pid = probe_id(c.name, p)
        d = _dirs.get(pid)
        # …with forward slashes: the command is read by a shell, and a Windows path dropped into it
        # verbatim turns every separator into an escape — the pinned probe then does not run as
        # shown, which is the one thing a pinned probe may not do.
        cmd = p.command.replace(INPUTS_TOKEN, d.as_posix()) if d else p.command
        return (f"    - {'PART’S ' if part else ''}PINNED CHECK [{pid}] — {p.behaviour}: run `{cmd}` → must show: "
                f"{p.expect}"
                + ("\n      (the part it belongs to passed its own validation on an earlier delivery; its result "
                   "now stands inside THIS delivery, and this criterion rests on it — run it here and report it ONCE, "
                   "under this id, in the probe list of any one criterion that rests on it, with `held`: true if it "
                   "showed what it must, false if not — and then every criterion resting on it fails)" if part else "")
                + (f"\n      (its {len(p.inputs)} input file(s) were written by the system from the "
                   f"contract into {d} — run the command as shown; do not substitute files from "
                   f"the delivery)" if d else ""))

    def _crit_block(c, items) -> str:
        # …A SEAM CRITERION ANSWERED IN ITS OWN ENTRY: reported only under the free-text `seams` note it had no verdict,
        # and the report was refused (AUTO coreutils, 2026-10-10)
        lines = [f"- **{c.name}**: {c.description}"] + (
            ["    - (a SEAM criterion: give it its OWN `per_criterion` entry under this exact name, with a probe over "
             "the producer's real output — the `seams` note is free text and decides no criterion)"]
            if c.depends_on else [])
        # …handed over NEUTRALLY, a regression line. A refuting probe's recorded `expect` is sometimes what the
        # criterion required and sometimes what the failing round printed: "must show" had a repaired delivery FAILed
        # for no longer printing the error (GB_coreutils_tltuq7652), and "it showed" inverted the guard for the
        # majority that recorded the requirement. The criterion decides; the probe is what to run.
        lines += [(_probe_line(*x) if isinstance(x, tuple) else _regression_line(x, _dirs, workdir))
                  for pid, x in items if carry.get(pid) == c.name]
        # A PART'S PROBE WRITTEN ELSEWHERE serves this criterion too: one observation of it, wherever it is made
        again: dict = {}
        for pid in dict.fromkeys(probe_id(pc.name, p) for pc in _parts.get(c.name, ()) for p in (pc.check or ())
                                 if p.command.strip()):
            if carry.get(pid) != c.name:
                again.setdefault(carry.get(pid), []).append(pid)
        lines += [f"    - rests also on the PART’S PINNED CHECKS written out under **{at}**: {', '.join(ids)} — one "
                  f"observation of each serves this criterion too" for at, ids in again.items() if at is not None]
        if None in again:
            lines.append(f"    - rests also on the PART’S PINNED CHECKS {', '.join(again[None])} — observed by another "
                         f"run of this validation: not yours to run, and one observation of each serves this criterion")
        # …AND WHAT IT OWES THAT ANOTHER RUN CARRIES: its verdict is the conjunction of the runs' verdicts on it
        if any(carry.get(pid) != c.name for pid, _ in items):
            lines.append("    - (what this criterion owes is SPLIT between runs of this validation: run what is listed "
                         "here and report this criterion on it — the runs' verdicts on it are conjoined, so one FAIL "
                         "fails it and nothing passes it that a run left undecided)")
        # …AND WHAT ITS ISSUER RULED OUTSIDE IT, with his reason: unseen, the next validator files the same ground again
        lines += [f"    - RULED OUT by its issuer [{r.get('id')}] `{r.get('command')}` — {r.get('why') or 'no reason given'}: "
                  f"not this criterion's; a FAIL resting on it is not a refutation" for r in _retired
                  if r.get("criterion") == c.name]
        return "\n".join(lines)

    return "\n".join(_crit_block(c, items) for c, items in owed) or "- (none)"


def _seam_lines(engine: Engine, task, inside=frozenset()) -> list:
    """The node's upstream Dep seams, to be checked against the producer's real output — those from outside
    `inside` only, where a scope's own seams are its listed nodes."""
    return [f"- consumes `{e.from_id}` ({name}, state {prod.state.name if prod else '?'}){_glue(e)}"
            for e, name, prod in _upstream(engine, task, inside)]


def _scratch_note(scratch: Optional[str]) -> str:
    """Where the validator may write — a fresh scratch of its own, never the delivery."""
    return (f"A private scratch directory, fresh for THIS validation: {scratch}\n"
            f"When you run pytest, pass `-p no:cacheprovider`: its cache directory would "
            f"otherwise be written INTO the delivery, which is the one thing you must not do.\n"
            f"WRITE NOTHING INTO THE DELIVERY. Fixtures, sample inputs, temporary outputs and any "
            f"copy you make go in that scratch — the working directory belongs to the executor, "
            f"and files you leave there become part of what the next validator sees (measured: a "
            f"120 MB fixture and a stray CSV left behind in a delivered tree). Read and RUN "
            f"anything you like in place; create nothing.\n" if scratch else "")


def _validator_packet(engine: Engine, task, deliverable: str, workdir: Optional[str],
                      scratch: Optional[str] = None, criteria=None, carry: Optional[dict] = None) -> str:
    """The validator's self-contained input: contract + seams + ACCEPTED_RISKS + the DELIVER report.
    Embedded by the system — the validator has no graph access (read-only instrument, §10.3).

    `criteria` names the SUBSET this run validates (all of them by default). A rich contract is validated
    in batches whose conjunction is the same verdict (§2 V = ⋀ cᵢ), because the coverage discipline
    is what one report fails when the contract is long. `carry`: the probes this run carries (`_criteria_text`)."""
    tid = str(task.id)
    _crits = tuple(criteria if criteria is not None else task.spec.criteria)
    crits = _criteria_text(engine, task, _crits, scratch, workdir, carry)
    ups = _seam_lines(engine, task)
    # WHAT THE LAST ATTEMPT ON THIS DELIVERY WAS MISSING. Measured across every run this
    # installation has recorded (2026-09-05): the validator is 56.5% of all spend — $441.77 of
    # $782.10 over 904 calls — and 151 of its reports decided NOTHING, of which **140 named
    # behaviours they never probed**. The rule that refuses them is load-bearing (an unobserved
    # conjunct cannot carry a pass, §2.3) and the failure is not capability: the report was
    # well-formed and its commands were real, it simply did not run one per behaviour it had
    # listed. So the retry re-validated the whole node from scratch at a HIGHER tier — paying twice
    # for a bookkeeping gap — while the one thing that would close it, the list of what went
    # unobserved, sat in the record and reached nobody. An ordinary user had all three of their
    # nodes refused on the first report, at a paid round each, and called the validation loop the
    # worst part of the honest path (wave 25).
    _gap = engine.refused_report_for_this_delivery(TaskId(tid)) or {}
    prior = (f"\n## YOUR PREVIOUS REPORT ON THIS DELIVERY WAS REFUSED — read this first\n"
             f"{_gap.get('defects')}\n\n"
             f"Nothing about the work has changed since; what was missing is the EVIDENCE. "
             f"Validate the same delivery again: run every criterion's WHOLE pinned procedure — a "
             f"criterion stands on it — and, under a criterion that pins none, give a labelled probe — a "
             f"command, what its output must show, and the `behaviour` it observes — for every "
             f"behaviour you name. Naming three behaviours and probing one is refused; naming one "
             f"behaviour and probing it is not. This is attempt {int(_gap.get('refusals', 1)) + 1}.\n"
             if _gap else "")
    negl = "\n".join(f"- {n.item}" for n in set_aside_of(task))
    return (f"# Node under validation: {tid} — {task.spec.name}\n\n{task.spec.description}\n{prior}\n"
            + (f"## Contract — the criteria (the ENTIRE obligation; use these EXACT names in your "
               f"report, each criterion — a `dep__*` seam included — in its own `per_criterion` entry)\n" if len(_crits) == len(task.spec.criteria) else
               f"## Contract — the criteria THIS RUN VALIDATES ({len(_crits)} of "
               f"{len(task.spec.criteria)}; the others are validated by their own runs, and the node's "
               f"verdict is their conjunction, §2). Use these EXACT names and report on EVERY "
               f"one, each in its own `per_criterion` entry:\n")
            + f"{crits}\n\n"
            f"## Upstream dependencies (seams — check against the REAL producer output, not a stub)\n"
            f"{chr(10).join(ups) or '- none'}\n\n"
            f"## ACCEPTED_RISKS — risk factors the PLAN set aside. Do not fail the node for a gap "
            f"that lives ONLY here. It retires no criterion above: where an entry and a criterion "
            f"speak of the same behaviour the CRITERION decides, and a divergence from it is that "
            f"criterion's value — fail (Inv-2, §9.2)\n"
            f"{negl or '- none'}\n\n"
            f"## Executor's DELIVER report (where the work lives, how each criterion is claimed met)\n"
            f"{deliverable}\n\n"
            + _working_directory(workdir, validating=True) + _scratch_note(scratch))


def _scope_validator_packet(engine: Engine, batch: list, workdir: Optional[str], scratch: Optional[str],
                            inside: frozenset) -> str:
    """ONE validator's input over a scope's deliveries: every node under its own heading, with its criteria,
    pinned probes and regression lines, its seams from outside the scope, its ACCEPTED_RISKS and its own
    DELIVER report — the single-node packet's content, node by node."""
    blocks = []
    for task, deliverable, crits, *carry in batch:
        tid = str(task.id)
        place = str(Path(scratch) / tid) if scratch else None
        ups = "\n".join(_seam_lines(engine, task, inside)) or "- none"
        negl = "\n".join(f"- {n.item}" for n in set_aside_of(task)) or "- none"
        gap = (engine.refused_report_for_this_delivery(task.id) or {}).get("defects")
        blocks.append(f"## Node `{tid}` — {task.spec.name}\n\n{task.spec.description}\n"
                      + (f"\nYOUR PREVIOUS REPORT ON THIS DELIVERY WAS REFUSED: {gap}\n" if gap else "")
                      + f"\n### Criteria of `{tid}` this run validates — report each with task_id `{tid}`\n"
                      f"{_criteria_text(engine, task, crits, place, workdir, *carry)}\n\n"
                      f"### Upstream dependencies from outside the scope (check against the REAL producer "
                      f"output)\n{ups}\n\n"
                      f"### ACCEPTED_RISKS of `{tid}` — the plan set these aside; none retires a criterion, "
                      f"and a divergence from a criterion is its value, fail (Inv-2, §9.2)\n{negl}\n\n"
                      f"### Executor's DELIVER report for `{tid}`\n{deliverable}\n")
    return ("# One scope under validation — the nodes one executor session delivered, parts before the whole\n\n"
            "Validate EACH node below against ITS OWN criteria, over the artifact as delivered. Every "
            "`per_criterion` entry names its node in `task_id` (the id in the node's heading) and the "
            "criterion by its EXACT name; report on every criterion listed, each in its own entry (a `dep__*` seam "
            "included).A node's verdict is the "
            "conjunction of its own criteria (§2): a part that fails is that part's FAIL.\n\n"
            + "\n".join(blocks)
            + "\n" + _working_directory(workdir, validating=True) + _scratch_note(scratch))


def _last_deliver_result(engine: Engine, task_id: TaskId) -> Optional[str]:
    stored = engine.deliver_result(task_id)                       # persisted on DELIVER — survives restarts
    if stored:
        return stored
    for e in reversed(engine.audit_log(task_id)):                 # in-memory fallback (older DBs)
        if e.signal == Signal.DELIVER and not e.rejected and e.result:
            return e.result
    return None
