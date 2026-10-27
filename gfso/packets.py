"""What each LLM role is handed: the executor's packet for one node (`_executor_packet`) or for a scope one session
carries (`_scope_packet`, in `_scope_order`), and the validator's for a node (`_validator_packet`) or a scope
(`_scope_validator_packet`) — the contract's criteria, the upstream results, the rework's failed criteria. Text only:
no graph writes, no signals."""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from gfso.core.protocol.procedure import INPUTS_TOKEN, laid, materialize_inputs, probe_id, same_probe, unrerunnable
from gfso.core.types import Signal, TaskId, set_aside_of
from gfso.engine import Engine
from gfso.engine.audit import rejected_on_current_version
from gfso.engine.verdicts import OUTSIDE_NOTE
from gfso.engine.validation import is_auto_root
from gfso.observe import TAIL
from gfso.workspaces import _unjoined_text, base_of, execution_of, node_temp


def _executor_inputs(engine, task) -> dict:
    """{probe id: a copy of its pinned inputs} for the executor, laid down from the contract outside its place.

    The inputs are part of what will be RUN, so part of the contract the executor is held to (Inv-1); named without
    their contents, the root executor of c_compiler searched the file system for them and read the plan's own copies
    (EVIDENCE_LOG §13.34). The validator still lays its own from the contract, so nothing done to this copy reaches a verdict."""
    criteria = task.spec.criteria
    return (materialize_inputs(criteria, tempfile.mkdtemp(prefix="gfso-check-inputs-", dir=node_temp(engine, task)))
            if any(p.inputs for c in criteria or () for p in (c.check or ())) else {})


def _crit_line(c, dirs: dict) -> str:
    """One criterion as the executor reads it — with the procedure that will decide it.

    Pre-registration means something only if the side being held to it can READ it: the contract says
    what will be RUN, written before the work, so the executor builds against the check rather than
    against its own reading of the criterion."""
    def _probe(p) -> str:
        d = dirs.get(probe_id(c.name, p))
        cmd = p.command.replace(INPUTS_TOKEN, d.as_posix()) if d else p.command
        return (f"    - will be checked by — {p.behaviour}: `{cmd}` → must show: {as_shown(p.expect)}"
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


def snapshot_note(tree: str) -> str:
    """What a validator run in its own copy of the place (`adapters.snapshots`) is told about where it stands."""
    return (f"\nThis run has the delivery to itself: {tree} is a copy of the delivery's directory exactly as it stands "
            f"on disk — uncommitted files, build outputs and links included — made for this run alone, while the "
            f"other runs of this validation work in copies of their own: wherever the contract or the report names "
            f"the delivery's directory, it means this one. Build and clean as the checks say: the delivery's files are "
            f"not reached from here. Git refs, config and worktrees are shared with the delivery: run no git command "
            f"that writes (no commit, checkout -b, gc, worktree prune). You are still READ-ONLY: change no file the delivery holds — the copy is compared with the "
            f"delivery before it goes, and a committed file that differs is recorded as your edit.\n")


def checkout_note(here: Optional[str]) -> str:
    """A node's place checks out its base as committed when the place was made: those paths are here, the rest of the
    base is read there."""
    base = base_of(here)
    return (f"This directory is a checkout of `{base}` as committed when it was made: a path the contract names under "
            f"`{base}` is the same path here. What is not here — uncommitted edits, untracked or ignored files, later "
            f"commits — read in `{base}` if you need it; nothing is ever written there.\n" if base else "")


#: Said once over what the system observed of a place before the session (`observe.observe_place`).
_OBSERVED = ("Before this session the system ran each check pinned to your criteria once, in a copy of your place exactly "
             "as it stands, in the criteria's order, with no build step first: a check over a program the tree has not "
             "built, or built from older sources, shows that and not your work. It is an observation, not a verdict — "
             "the validator builds as it needs and decides. It does not cover what the validator runs beyond these "
             "checks: the standing findings of an earlier round, the parts' own pinned checks, what it explores. Use it "
             "to see where the work stands; confirm with your own run before you deliver. An EXACT check is the "
             "exception: the system runs it again itself, the same way, on a fresh copy of your delivery, and an "
             "output other than its pin fails its criterion whatever the validator says — one that cannot print its "
             "pin on correct work (it does not build what it runs, reads state it does not create) is a pin to "
             "CHALLENGE, not to work around.\n")


#: Said in every executor packet, the first round included: offered only in rework sections, the move was never made —
#: a pin missing `-lm` travelled 24 min as BLOCK + 4 tech reports, 0 CHALLENGE in the row (GB_sql_database_tnkid4876,
#: docs/notes/OWN_PLAN_REPLANNING_MOVES.md; §11.3)
CHALLENGE_WHEN = ("\n## When the contract itself is wrong — CHALLENGE\n"
                  "Report `status: \"challenge\"`, naming the criterion and the defect, the moment contact shows THIS "
                  "contract cannot be met as written: a pinned check that cannot pass on correct work (it does not "
                  "build or link as written, reads an input that is empty or absent, demands what the contract "
                  "contradicts), a criterion no procedure can decide, a scope one session cannot carry. An accepted "
                  "challenge installs a corrected contract and you work to that; a rejected one returns the work "
                  "unchanged. `blocked` leaves the pin as it is, and a tech report goes to the system's maker, not to "
                  "your issuer: neither repairs this contract.\n")


def observed_lines(rows: list) -> str:
    """One line per observed check, by its criterion and command (the criteria above carry the rest): printed exactly
    what it must show, or how it ended and the tail of what it printed, or why it gave nothing — and ONE line where none
    passed and every one ended the same way, the shape of a place with nothing built yet (every turn re-reads them)."""
    if len(rows) > 1 and not any(r.get("matched") for r in rows) and len(
            {(r.get("note"), r.get("rc"), r.get("out")) for r in rows}) == 1:
        r = rows[0]
        return (f"- none of the {len(rows)} checks shows what it must; each "
                + (r["note"] if r.get("note") else f"ended exit {r.get('rc')}, printing «{_flat(r.get('out'))}»") + "\n")

    def _one(r) -> str:
        head = f"- **{r['criterion']}** `{r['command']}` → "
        if r.get("note"):
            return head + r["note"]
        return head + ("printed exactly what it must show" if r.get("matched") else
                       f"exit {r.get('rc')}, printed «{_flat(r.get('out'))}»"
                       + (" — the system's own run of this EXACT check does not match its pin" if r.get("exact") else ""))
    return "".join(_one(r) + "\n" for r in rows)


def as_shown(expect) -> str:
    """A pinned expectation on one line, its lines joined by ⏎ — written raw, an expectation of two lines split the
    packet's line: "must show: ERR" and a stray "(+ " under it, read by executor, validator and issuer as ERR alone
    (sql rows, 2026-10-27: an issuer's dispute round, six tech reports, citations of "ERR" as the expectation)."""
    return " ⏎ ".join(str(expect or "").splitlines())


def _flat(out) -> str:
    return " ⏎ ".join((out or "").splitlines()) or "(nothing)"


def _observed_section(rows: list, heading: str = "##") -> str:
    return f"\n{heading} Your place as the system found it\n{_OBSERVED}{observed_lines(rows)}" if rows else ""


def _executor_packet(engine, task, workdir: str | None, unjoined: list = (), seen: dict | None = None) -> str:
    """The executor's self-contained contract (it has no graph access): spec + criteria + upstream
    inputs (the REAL delivered outputs it consumes) + ACCEPTED_RISKS + rework feedback if any + what its pinned checks
    printed on its place before the session (`seen`, `observe.observe_place`)."""
    tid = str(task.id)
    dirs = _executor_inputs(engine, task)
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
            f"{chr(10).join(sibs) or '- none'}\n{CHALLENGE_WHEN}{rework}{answered_challenges(engine, task)}"
            f"{_observed_section((seen or {}).get(tid, []))}{_unjoined_text(unjoined)}\n"
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
                  + (_through_parts_text(through) if through else "") + _handover(engine, task)
                  + (_REHANDED if own and engine.rehanded(task.id) else ""))
        # …and, where the same criteria failed every round, the other route (§12.4): the frontier says it at the agent
        # door; a system executor saw only "fix exactly them", and its node was split before it could challenge
        if stuck := engine.stuck_on(task.id):
            rework += (f"\n{', '.join(stuck)} failed in each of the last {engine.CONTRACT_SUSPECT_ROUNDS} rounds. If "
                       f"it cannot be met AS WRITTEN, report `status: \"challenge\"` naming it and why, instead of "
                       f"delivering against it again.")
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


#: Said to the executor whose last delivery re-handed files a FAIL had already judged (`Engine.rehanded`): the round
#: decided nothing new, and the move that does is his. Re-handing one tree three times while its report said the fix lay
#: in another node's file, a leaf was split over rounds that tried nothing (GB_sql_database_tngo2o700 root.joins).
_REHANDED = ("\nYour last delivery handed in the very files a FAIL had already judged, unchanged, and the FAIL stands "
             "on exactly them: re-handing them again decides nothing new. Change the result; or, where what it lacks "
             "is another node's to make, report `status: \"blocked\"` naming that node; or, where a finding asks for "
             "what your criterion as written does not, report `status: \"challenge\"` naming it by its id. An issuer's "
             "words in a rejection retire no finding — only an acceptance naming its id does.\n")


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
            "(listed below) and why it lies outside the criterion — "
            + ("this node's criteria are the user's goal and only the user retires a finding of it, so your issuer "
               "answers without retiring it: what decides it is the next validation, which runs it again and judges "
               "what it prints against the criterion as written — meet the criterion and deliver"
               if is_auto_root(engine.graph, task) else "your issuer rules on it, and only his ruling retires it")
            + "; `blocked` is for another node's output you really need.")]
    standing = engine.regression_probes(task.id)
    workdir = (engine.get_exec_verdict(task.id) or {}).get("workdir")
    settled = engine.rework_settled(task.id)
    # …EACH BY THE ID IT IS DISPUTED AND RULED ON, and each settled id by what it ran: told "name the finding by its id",
    # an executor met this round's probes bare and the settled ones as ids alone, and disputed a retired finding again
    # because "the packet gives no [id] for it" (GB_sql_database_tngo2o700 root.joins, audit 52)
    ran = {(c, " ".join(str(x).split())): str(p["id"]) for c, ps in standing.items() for p in ps if p.get("id")
           for x in (p.get("seen"), p.get("as_run"), p.get("command")) if x}
    said = {str(r["id"]): str(r.get("seen") or r.get("command") or "") for r in engine.retired_findings(task.id)}
    said.update({str(p["id"]): str(p.get("seen") or p.get("as_run") or p.get("command") or "")
                 for ps in standing.values() for p in ps if p.get("id")})
    for f in failed:
        ev, cmds = why.get(f, ("", []))
        out.append(f"- {f}" + (f"\n  what it observed: {ev}" if ev else "")
                   + (f"\n  settled, NOT demanded — the next PASS does not run them; nothing to dispute (where what "
                      f"it observed still names one, that part is settled):"
                      + capped([f"[{i}]" + (f": `{said[i].replace(chr(10), ' ⏎ ')}`" if said.get(i) else "")
                                for i in settled[f]], "settled findings", list_key(engine, task.id, f, "settled"))
                      if settled.get(f) else "")
                   + capped([f"probe{f' [{i}]' if (i := ran.get((f, ' '.join(cmd.split())))) else ''}: "
                             f"`{cmd.replace(chr(10), ' ⏎ ')}`" for cmd in cmds], "refuting probes",
                            list_key(engine, task.id, f, "probes"))
                   + capped([f"standing finding [{p.get('id')}]: `{p.get('seen') or p.get('as_run')}`"
                             + (f" — {w}: shown, not demanded"
                                if (w := unrerunnable(p, engine.layable(task.id), workdir)) else "")
                             for p in standing.get(f, ())], "standing findings", list_key(engine, task.id, f, "findings")))
    return "\n".join(out) + "\n"


#: Lines of one list — a failed criterion's refuting probes, its standing findings — a packet shows in its text; the
#: whole list is in a file it names. Every one inline, a root's 1,414 findings and 1,152 probes made its packet ~250k
#: tokens and every executor and consent session died `prompt_too_long` (GB_sql_database_tmxu0n436, 2026-10-15).
SHOWN_FINDINGS = 20


def list_key(engine, task_id, *parts) -> str:
    """The file a capped list goes to: one per engine — two projects' roots are both `root`, and two runs of one task
    would overwrite each other's lists — per node, criterion and kind; in the temp of the node's place, so the session
    it is named to reads it and no other node's does (`node_temp`)."""
    name = "-".join(map(str, (os.getpid(), id(engine), task_id, *parts)))
    return str(Path(node_temp(engine, engine.graph.get_task(task_id))) / "gfso-lists"
               / (re.sub(r"[^\w.-]+", "_", name)[:120] + ".md"))


def capped(lines: list, what: str, key: str) -> str:
    """`lines`, each one line of text: the first SHOWN_FINDINGS inline and, where there are more, every one — those too —
    in the file `key` names (`list_key`: outside the place, where the reader runs; rewritten each build), so none is
    withheld and the text fits a window."""
    text = "".join(f"\n  {x}" for x in lines[:SHOWN_FINDINGS])
    if len(lines) > SHOWN_FINDINGS:
        path = Path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"- {x}\n" for x in lines), encoding="utf-8", newline="")
        text += (f"\n  … and {len(lines) - SHOWN_FINDINGS} more {what} — all {len(lines)}, one per line with its id, in "
                 f"{path.as_posix()}: grep it for what you need, do not read it whole")
    return text


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


def _scope_node_block(engine, i: int, t, top, inside: frozenset, seen: dict | None = None) -> str:
    """One node of a scope session's packet: its contract, its inputs from outside the scope, its rework, what its
    checks printed on the scope's place before the session."""
    parent = engine.graph.get_parent(t.id)
    role = "the scope's top — the whole" if str(t.id) == str(top.id) else f"a part of `{parent.id}`"
    head = f"## {i}. `{t.id}` — {t.spec.name} ({role})\n\n{t.spec.description}\n\n"
    if t.state.name not in _EXECUTOR_STATES:
        return head + f"Already {t.state.name}: delivered earlier — listed for context, not yours to redo.\n"
    ups = "\n".join(_upstream_lines(engine, t, inside)) or "- none"
    negl = "\n".join(f"- {n.item}" for n in set_aside_of(t)) or "- none"
    dirs = _executor_inputs(engine, t)
    crits = "\n".join(_crit_line(c, dirs) for c in t.spec.criteria) or "- (none)"
    return (head + f"### Criteria of `{t.id}` — its ENTIRE obligation; the scope's validation runs each\n"
            f"{crits}\n\n"
            f"### Inputs from outside your scope (the REAL outputs, no stubs)\n{ups}\n\n"
            f"### ACCEPTED_RISKS (declared plan assumptions — do not gold-plate against these)\n{negl}\n"
            f"{_rework_section(engine, t)}{answered_challenges(engine, t)}"
            f"{_observed_section((seen or {}).get(str(t.id), []), '###')}")


def _scope_packet(engine, top, order: list, workdir: str | None, unjoined: list = (), seen: dict | None = None) -> str:
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
            + "\n".join(_scope_node_block(engine, i, t, top, inside, seen) for i, t in enumerate(order, 1))
            + f"\n## The other nodes of this plan — NOT your work, and you must not do it\n"
            f"If you cannot proceed because something one of them owns does not exist yet, report that node "
            f"`status: \"blocked\"` and NAME it in `blocker_task_ids`.\n{others}\n{CHALLENGE_WHEN}{_unjoined_text(unjoined)}\n"
            + _working_directory(workdir))


def _regression_line(p: dict, dirs: dict, workdir: Optional[str] = None) -> str:
    """One once-refuting probe, shown over this round's inputs directories and asked for under its id."""
    cmd = laid(p.get("as_run") or p.get("command", ""), dirs)
    orphan = f"({why} — shown, not demanded) " if (why := unrerunnable(p, dirs, workdir)) else ""
    return (f"    - REGRESSION [{p.get('id')}] (this probe REFUTED this criterion in an earlier round — re-run "
            f"it and report it under this id) — {p.get('behaviour')}: run `{cmd}` {orphan}"
            f"(recorded then: «{p.get('expect')}», which may be what was required or what was "
            f"seen — decide from what it prints now against the criterion's own requirement)")


#: The one optional field every role's answer carries for a TECH REPORT (`Engine.tech_report`): said small, so it is
#: used where the system itself leaves no honest move, not as a second place for complaints about the task. Opened with
#: "Leave it out: that is the normal answer", it was left out by every role of all 8 smokes of 2026-10-25, the joins
#: executor among them, who met three of the cases below in one node (GB_sql_database_tngo2o700 root.joins).
TECH_REPORT = {"type": "string", "description":
               "Usually absent: it moves nothing in this run, it goes to the system's maker, and \"no defect found\" "
               "is no report. One line, when the SYSTEM, not the task, left you no honest move — you re-deliver an "
               "unchanged result because the fix lies in another node's file; a finding you are held to shows no id "
               "to dispute it by; a ruling contradicts itself (calls a finding out of scope while it keeps binding); a "
               "tool cannot run; an answer ignored what you showed. A defect of THIS task's contract — a pinned check "
               "that cannot pass on correct work, a criterion that cannot be decided — is no tech report: it is the "
               "executor's CHALLENGE, which the task's issuer answers."}


def file_tech_reports(engine: Engine, report, role: str, actor: str, task_id) -> None:
    """Every tech report a role's answer carries — at its top and in each node entry of a scope's report — filed."""
    nodes = report.get("nodes") if isinstance(report, dict) else None
    for r in [report] + list(nodes if isinstance(nodes, list) else ()):
        if isinstance(r, dict) and str(r.get("tech_report") or "").strip():
            engine.tech_report(r["tech_report"], role, actor, r.get("task_id") or task_id)


def owed_probes(engine: Engine, task, crits) -> list:
    """[(criterion, [(probe id, what to show)…])] — what validating `crits` of `task` OWES, criterion by criterion: its
    pinned probes, the pinned probes of the DONE parts it rests on, and the probes that once refuted it.

    A part's probe is owed ONCE, under the first criterion resting on it: one observation serves every criterion on
    it (`procedure.part_credit`) — and not at all where the same probe is already owed, the whole's own or another
    part's (`procedure.same_probe`): a copy owed again was the same command run two or three times under ids a weak
    validator mixed, and a whole's functional checks copied into a part landed under its first criterion, "build and
    hygiene", where the validator read them as out of scope (the sql root, 2026-10-27: six ⊥ validations of one sound
    delivery). What to show is a (criterion, probe, is a part's) triple for a pinned probe and the stored probe for a
    regression line. THE one enumeration: the packet writes it out and the batching counts it."""
    tid = TaskId(str(task.id))
    reg, parts = engine.regression_probes(tid), engine.parts_procedure(tid)
    shown = {same_probe(p) for c in crits for p in (c.check or ())}
    out = []
    for c in crits:
        own = [(probe_id(c.name, p), (c, p, False)) for p in (c.check or ())]
        mine = [(probe_id(pc.name, p), (pc, p, True)) for pc in parts.get(c.name, ()) for p in (pc.check or ())
                if p.command.strip() and same_probe(p) not in shown and not shown.add(same_probe(p))]
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
    _part_probes = {probe_id(pc.name, p): (pc, p) for pcs in _parts.values() for pc in pcs for p in (pc.check or ())}
    _all = engine.validation_procedure(TaskId(tid))
    # A probe's INPUTS are laid down here, from the contract, by the system — never read from the
    # delivery, where the executor could have grown them (the corpus that moved under `c_compiler`).
    _dirs = (materialize_inputs(_all, Path(scratch) / "probe_inputs" if scratch
                                else tempfile.mkdtemp(prefix="gfso-probe-inputs-",
                                                      dir=execution_of(engine).temp_of(workdir)))
             if any(p.inputs for c in _all for p in (c.check or ())) else {})
    owed = owed_probes(engine, task, crits)
    if carry is None:
        carry = {pid: c.name for c, items in owed for pid, _ in items}

    def _cmd(c, p) -> str:
        d = _dirs.get(probe_id(c.name, p))
        # …with forward slashes: the command is read by a shell, and a Windows path dropped into it
        # verbatim turns every separator into an escape — the pinned probe then does not run as
        # shown, which is the one thing a pinned probe may not do.
        return p.command.replace(INPUTS_TOKEN, d.as_posix()) if d else p.command

    def _probe_line(c, p, part: bool = False) -> str:
        pid = probe_id(c.name, p)
        d = _dirs.get(pid)
        return (f"    - {'PART’S ' if part else ''}PINNED CHECK [{pid}] — {p.behaviour}: run `{_cmd(c, p)}` → must show: "
                f"{as_shown(p.expect)}"
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
        # …ONE CARRIED BY ANOTHER RUN, shown as the contract pins it: named by id alone, a validator read it as owed and
        # unrunnable, rebuilt it from its expected file — an unsorted diff of a sorting check — and filed held: false,
        # which failed every criterion resting on it (GB_sql_database_tngtvm580 root, 2026-10-25)
        if None in again:
            lines.append("    - rests also on the PART’S PINNED CHECKS below, each observed by ANOTHER run of this "
                         "validation — shown as the contract pins them so you know what they run and must show; not "
                         "yours to run or report, and one observation of each serves this criterion:")
            lines += [f"      · [{pid}] — {p.behaviour}: `{_cmd(pc, p)}` → must show: {as_shown(p.expect)}"
                      for pid in again[None] for pc, p in [_part_probes[pid]]]
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


def _evidence_short(defects: str) -> bool:
    """Was the refusal about what the report observed (probes, behaviours) — else about its form (a name, a verdict word)?
    Told "what was missing is the EVIDENCE" after a refusal for a label, validators re-ran the probes and kept the label
    (GB_sql_database_tn03ao788)."""
    if "is not a criterion of this node" in defects or "contradict" in defects:
        return False
    return any(k in defects for k in ("probe", "behaviour", "observ", "pinned", "divergence"))


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
             f"Nothing about the work has changed since; "
             + ("what was missing is the EVIDENCE. " if _evidence_short(str(_gap.get("defects"))) else
                f"what was wrong is the report's FORM — name each criterion exactly as this packet lists it, "
                f"and give its verdict on its own entry; then, as before: ")
             + f"Validate the same delivery again: run every criterion's WHOLE pinned procedure — a "
             f"criterion stands on it — and, under a criterion that pins none, give a labelled probe — a "
             f"command, what its output must show, and the `behaviour` it observes — for every "
             f"behaviour you name. Naming three behaviours and probing one is refused; naming one "
             f"behaviour and probing it is not. This is attempt {int(_gap.get('refusals', 1)) + 1}.\n"
             if _gap else "")
    negl = "\n".join(f"- {n.item}" for n in set_aside_of(task))
    return (f"# Node under validation: {tid} — {task.spec.name}\n\n{task.spec.description}\n{prior}\n"
            + (f"## Contract — the criteria (the ENTIRE obligation; use these EXACT names in your "
               f"report, each criterion in its own `per_criterion` entry; a dependency below is an edge, not a criterion)\n" if len(_crits) == len(task.spec.criteria) else
               f"## Contract — the criteria THIS RUN VALIDATES ({len(_crits)} of "
               f"{len(task.spec.criteria)}; the others are validated by their own runs, and the node's "
               f"verdict is their conjunction, §2). Use these EXACT names and report on EVERY "
               f"one, each in its own `per_criterion` entry:\n")
            + f"{crits}\n\n"
            f"## Upstream dependencies (edges, not criteria — a stub where one should be goes in the `seams` advisory)\n"
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
                      f"### Upstream dependencies from outside the scope (edges, not criteria — a stub where "
                      f"one should be goes in the `seams` advisory)\n{ups}\n\n"
                      f"### ACCEPTED_RISKS of `{tid}` — the plan set these aside; none retires a criterion, "
                      f"and a divergence from a criterion is its value, fail (Inv-2, §9.2)\n{negl}\n\n"
                      f"### Executor's DELIVER report for `{tid}`\n{deliverable}\n")
    return ("# One scope under validation — the nodes one executor session delivered, parts before the whole\n\n"
            "Validate EACH node below against ITS OWN criteria, over the artifact as delivered. Every "
            "`per_criterion` entry names its node in `task_id` (the id in the node's heading) and the "
            "criterion by its EXACT name; report on every criterion listed, each in its own entry. A node's verdict is the "
            "conjunction of its own criteria (§2): a part that fails is that part's FAIL.\n\n"
            + "\n".join(blocks)
            + "\n" + _working_directory(workdir, validating=True) + _scratch_note(scratch))


def outside_text(engine: Engine, task_id, rows: list) -> str:
    """The issuer's section of rows of `Engine.outside_the_criteria`, bounded as a packet's lists are (`capped`), each
    evidence by its tail as an observed check's is (`observe.TAIL`; the whole stays on the record): one evidence of 5000
    characters took an issuer packet from 1.4k to 7k. Empty where there are none."""
    return ("## What validators observed outside the written criteria\nThese are " + OUTSIDE_NOTE
            + capped([f"`{r['node']}`: {r['what']}" + (f" — seen: {_flat(_tail(r['evidence']))}" if r["evidence"] else "")
                      for r in rows], "observations", list_key(engine, task_id, "outside"))) if rows else ""


def _tail(text: str) -> str:
    return text if len(text) <= TAIL else "…" + text[-TAIL:]


#: distinct rejected challenges a packet shows, newest last — each WHOLE: a ruling binds, and one cut at 1500 characters
#: lost the reserved set it ruled on, the part the rework turned on (GB_sql_database_tng5od544 root.parse_stmt)
SHOWN_ANSWERS = 5


def _distinct_answers(pairs: list) -> list:
    """[(asked, answer, times)] — one line per distinct exchange, the newest last: a loop asks the same thing forty times."""
    seen: dict = {}
    for asked, answer in pairs:
        k = (" ".join(asked.split()), " ".join(answer.split()))
        seen[k] = seen.pop(k, 0) + 1
    return [(a, j, n) for (a, j), n in list(seen.items())[-SHOWN_ANSWERS:]]


def answered_challenges(engine: Engine, task) -> str:
    """For the one who challenged: his challenges of the contract that stands and his issuer's rejections of them.

    Unseen, the answer cannot end the dispute: the rework order says "dispute a finding, only his ruling retires it",
    and an executor whose ruling never reached him raised the same challenge again 40 times, one every 24 s, the
    issuer rejecting each within seconds (GB_sql_database_tn9nii608 root.parse_stmt). Nothing is refused for asking
    again — a rejected CHALLENGE forces nothing and the dispute has no counter (§11.3, §12.15 Φ2)."""
    got = _distinct_answers(rejected_on_current_version(engine.audit_log(task.id)))
    if not got:
        return ""
    return ("\n## Your challenges of this contract that its issuer REJECTED — each is answered\n"
            "A rejected challenge leaves the contract as written, and the next validation runs what it disputed again, "
            "judging what it prints against the criterion as written — your delivery is where that is decided. The "
            "same ground raised again is a question already answered and gets the same answer. Challenge again only "
            "with what the answer below does not meet — a new observation, quoted; otherwise meet the criteria as "
            "written and deliver.\n"
            + "".join(f"- you said{f' ({n} times)' if n > 1 else ''}: «{a or '(no reason recorded)'}»\n"
                      f"  your issuer answered: «{j or '(no justification)'}»\n" for a, j, n in got))


def answers_given(engine: Engine, task) -> str:
    """For the issuer of a dispute: his own rejections of challenges on the contract that stands — the same ground
    answered the same way, a new observation in the challenge being what is new to judge."""
    got = _distinct_answers(rejected_on_current_version(engine.audit_log(task.id)))
    if not got:
        return ""
    return ("## Challenges of this contract you already REJECTED — judge what the dispute above adds to them\n"
            + "".join(f"- asked{f' ({n} times)' if n > 1 else ''}: «{a or '(no reason recorded)'}»\n"
                      f"  you answered: «{j or '(no justification)'}»\n" for a, j, n in got))


#: how much of the last report a rework round is handed: a note, not the conversation
HANDOVER_LINES = 40


def _handover(engine: Engine, task) -> str:
    """The last delivery's own report, as its executor wrote it — what was built, where, how it was checked. Each round
    starts clean; without this note a fresh session re-read the code it had written to find where it stood (32% of its
    tool calls before the first edit, three sql_database rows, 2026-10-21), and continuing the whole conversation instead
    cost more than every fresh round together (GB_sql_database_tn9nii608)."""
    said = (_last_deliver_result(engine, task.id) or "").strip().splitlines()
    if not said:
        return ""
    cut = len(said) > HANDOVER_LINES
    return ("\n## Your last delivery, as you reported it (the work stands in your directory; start from here, not from "
            "re-reading the code)\n" + "\n".join(said[:HANDOVER_LINES])
            + (f"\n… ({len(said) - HANDOVER_LINES} more lines of that report)" if cut else "") + "\n")


def _last_deliver_result(engine: Engine, task_id: TaskId) -> Optional[str]:
    stored = engine.deliver_result(task_id)                       # persisted on DELIVER — survives restarts
    if stored:
        return stored
    for e in reversed(engine.audit_log(task_id)):                 # in-memory fallback (older DBs)
        if e.signal == Signal.DELIVER and not e.rejected and e.result:
            return e.result
    return None
