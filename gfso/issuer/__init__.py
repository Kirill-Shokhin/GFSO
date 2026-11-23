"""THE ISSUER FUNCTION — the issuer's moves, where the issuer is a machine.

In a graph the system holds, the issuer of a node is its parent's executor, and at the root under AUTO
the system moves for the goal's customer, who does not intervene. Every state in which the protocol
waits on an issuer then needs someone to make the move (Inv-8) — and the one such move that existed
(answering a dispute) was made by a model given the node's contract and the complaint, and nothing of
the task or its state. This package is that party: ONE context assembled from the graph, six questions,
and only the canon's moves as answers, each checked by code before anything is signalled.

- plan       a split the plan gate holds (§11.5): fix it, dispute a finding, or refine it once
- dispute    CHALLENGED: accept with the corrected contract, or reject with the reason
- escalation ESCALATED: re-ASSIGN (deadline, budget, criteria, executor), re-decompose the split above it, or CANCEL
- repair     contact refuted the decomposition: revise the covering child, or add one
- split      a childless node judged larger than one session of its executor: its split is owed (§3.7)
- parked     an executor round left the node in its hands twice: re-ASSIGN or CANCEL
- external   BLOCKED on nothing the graph holds: resolve with an action, re-ASSIGN, or CANCEL
- outside    a child's validator saw what no criterion writes: a split move that writes it, or a logged reason not to

`plan`, `repair`, `split` and `outside` are the moves of the node's own executor (the author of its split and the issuer of
its children); the other four are the node's issuer's. Under AUTO the root's criteria are append-only:
the user's contract is changed only by the user — their text; a pinned check is re-pinned by an accepted dispute.
"""
from __future__ import annotations

import contextlib
import dataclasses
import logging
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from gfso import tools as _tools
from gfso import store
from gfso.workspaces import standing
from gfso.adapters.execution import LocalExecution, scratch_of

from gfso.adapters.snapshots import NotTheDelivery, Uncopied, judged_at, snapshot, swap
from gfso.adapters.worktrees import NODES as _NODES
from gfso.adapters.llm.stats import is_limit, refused_by_limit, the_call_was_cut, what_stopped
from gfso.adapters.llm.structured import parse_structured, schema_instruction
from gfso.inflight import being_rewritten
from gfso.config import LIMIT_RETRY_S, agent_id as _config_agent_id
from gfso.core.graph.model import on_the_wall, project_max_iterations, project_now
from gfso.core.graph.mutations import Schedule, producers_of
from gfso.core.handlers.structural import risks_naming_own_criteria
from gfso.core.protocol.procedure import (EXACT_TEXT, INPUTS_TOKEN, as_read, inputs_token, laid as over_dirs,
                                          materialize_inputs, same_probe, shows, PROBE_S, pinned_files, probe_id,
                                          probes_from as _checks_of, unrerunnable, with_named_files, criterionless)
from gfso.core.types import (AgentId, Criteria, IN_THE_WORKS_PATH, PlaceUnavailable, Register, RevisionReason,
                             Signal, SignalData, Spec, Stage, State, TaskId, laid_beside, register_of, set_aside_of,
                             system_decides)
from gfso.decompose.extract import extract_spec
from gfso.decompose.seams import seam_problems
from gfso.engine import findings, loose_finding_key
from gfso.engine.audit import on_current_version
from gfso.engine.frontier import refuted_reading, withheld_over
from gfso.engine.parking import USERS_WAY
from gfso.engine.validation import is_auto_root, party_kind, users_criteria, users_plan
from gfso.packets import SHOWN_FINDINGS, must_show, answered_challenges, answers_given, as_shown, capped, list_key, outside_text
from gfso.engine.events import emit_cb
from gfso.packets import TECH_REPORT, checkout_note, file_tech_reports

log = logging.getLogger("gfso.issuer")

PROMPT = Path(__file__).parent / "issuer.md"


def _prompt() -> str:
    """The issuer's instructions, the per-check bound said from its one owner (`procedure.PROBE_S`)."""
    return PROMPT.read_text(encoding="utf-8").replace("<PROBE_S>", str(PROBE_S))

#: The largest rework budget a re-issued contract may carry, as a multiple of the project's default: an extension, not
#: an open loop.
REWORK_EXTENSION = 2

#: The longest a re-issued contract may run, in hours: an extension, not an open end.
MAX_EXTEND_HOURS = 48

#: The tail of a delivery the issuer reads — the part that says what was done and what was checked.
DELIVERY_TAIL = 4000

#: The trail entries the issuer reads, newest last.
TRAIL = 30

#: The questions whose mover is the node's EXECUTOR (the author of its split); the rest are its issuer's.
SPLIT_QUESTIONS = ("plan", "repair", "split", "outside")

#: What the issuer answering a dispute may use in the node's workspace: the validator's envelope, read and run.
#: A dispute says what the contract's checks do in the world — a fact about S, which only contact reads
#: (SINGLE-SEAM, §3.5). With no tools the issuer rejected a true challenge twelve times on a belief about what
#: GNU `head` prints that one run of it refutes (GB_coreutils_tmiy4m001, 2026-10-07); the holder of the same
#: node under SOLO ran it and repaired the check.
CONTACT_TOOLS = ("Read", "Bash", "Glob", "Grep")

#: The longest one dispute's contact may run, in seconds.
CONTACT_TIMEOUT_S = 900

CONTACT = ("# Contact\nYou are in the node's workspace, `{where}`, with a shell.\n{checkout}What this question turns "
           "on — what "
           "the contract's checks print here, whether anything can pass them, whether a blocker is real — is a fact "
           "of this machine: before you decide, RUN what decides it (the checks in question, and whatever the "
           "executor says they show) and quote in your justification each command you ran and what it printed. A "
           "rejected dispute that ran nothing is refused. A check you write anew is run first too: in a scratch "
           "directory, with the reference it compares against standing in for the work under the name the "
           "criterion's description demands (e.g. `exec -a <name> <reference>`), it must show what it expects — "
           "write no check that what the criterion describes would fail. Change nothing here: what you need to "
           "write goes under `mktemp -d`.\n\n")


class Unavailable(RuntimeError):
    """The model layer did not answer at all (a rate limit, a dropped transport): not the issuer's answer,
    so not counted against the node — the question is asked again later. `limit`: the account's usage limit refused
    it, which lifts at a time of day, not after a doubling (`LIMIT_RETRY_S`)."""

    def __init__(self, why: str, limit: bool = False):
        super().__init__(why)
        self.limit = limit


def unanswered(calls) -> Optional[Unavailable]:
    """A run whose every model call ended in error answered nothing — the same fact for an issuer's turn and for a
    review. Read as an answer that moved nothing, sixteen reviews an account's limit refused spent the free answers,
    and every real answer after it waited 32, 64, 120 min (GB_sql_database_tnb3ow508, 2026-10-22)."""
    errs = [str(c.get("error") or "") if isinstance(c, dict) else "" for c in calls or ()]
    if errs and all(errs):
        return Unavailable(f"every model call ended in error — {errs[-1]}",
                           limit=refused_by_limit(calls))
    return None


@dataclass(frozen=True)
class Verbs:
    """What the issuer calls on the product's own model layer, handed in by the dispatcher that runs it:
    a model, the busy registry a long call announces itself in, the Level-2 review, and one refine
    round. Handed in rather than imported so this package sits below the delegation layer it serves."""
    llm: object          # model name -> a runner with run_agent / tag_last / calls
    busy: object         # name -> a context manager announcing a long call on the server
    review: object       # (engine, node id) -> the review's reply
    refine: object       # (engine, node id) -> the refine round's reply
    place: object = None  # (engine, agents, node id) -> the directory the node's work is in, or None
    execution: object = None  # engine -> where its project's sessions and commands run (`ExecutionPort`), None = here



#: what names an issuer's contact among a node's validation rounds — the rounds' rotation leaves it alone
CONTACT_ROUND = "issuer_"


@contextlib.contextmanager
def _contact_place(where: str, ex, project=None):
    """Where an issuer's contact with a node lays its inputs and its copy of the place: a ROUND OF THAT NODE'S
    VALIDATION SCRATCH, as a validator's run is (`tools_llm`) — its session reads the probes the node's standing
    findings name as the system laid them from its record (`_standing_findings`), writes only its own round, and no
    other node's session reaches it. A root's too where places stand apart: in the base it worked in its executor's
    container and could change the delivery. On this host, for a place that is no node's (the base, a chat's tree),
    the temp its session holds: its copy is read by id there all the same. `project`: whose places hold a base's
    rounds (`scratch_of`). Gone when the contact ends, with
    what was laid beside it (`laid_beside`)."""
    if _NODES not in str(where) and not ex.apart:
        lent = ex.scratch("gfso-issuer-inputs-", dir=ex.temp_of(where))
    else:
        lent = ex.scratch(CONTACT_ROUND, dir=str(scratch_of(where, project)))
    with lent as d:
        yield d

@contextlib.contextmanager
def _round(engine, tmp):
    """A contact's round in the record of the rounds standing (`findings.record_round`) while it stands."""
    if tmp:
        findings.record_round(engine.graph, tmp, True)
    try:
        yield
    finally:
        if tmp:
            findings.record_round(engine.graph, tmp, False)


def _execution(engine, verbs: "Verbs | None"):
    return verbs.execution(engine) if verbs is not None and verbs.execution is not None else None


@system_decides()
def signal_ok(engine, task_id: TaskId, sig: Signal, source: str, _why: "list | None" = None,
              **kw) -> bool:
    """Send one signal for the system; a party's own comes by the door (`tools.signal`). True when the FSM took it. `_why`
    collects the refusal, when a caller intends to SAY it rather than only log it — the reason existed and reached the
    log alone. A PASS over a refuted part whose reopen is open is refused here, by the rule the frontier withholds it by
    (`frontier.withheld_over`): it settles the whole the part would be reopened under (§12.8, §12.14); a FAIL is not."""
    if sig == Signal.PASS and (over := withheld_over(refuted_reading(engine, engine.refuted_passes()), task_id)):
        why = (f"no PASS on {task_id}: {', '.join(r.node for r in over)} below it stand(s) at PASS while the current "
               f"recorded verdict for it is FAIL, and can still be reopened — a PASS here settles the whole it would be "
               f"reopened under; its FAIL signs over nothing (§12.8, §12.14)")
        log.warning(why)
        if _why is not None:
            _why.append(why)
        return False
    entry = engine.send_signal_sync(SignalData(signal=sig, task_id=task_id,
                                               source=AgentId(source), **kw))
    ok = bool(entry and not entry.rejected)
    if not ok:
        log.warning(f"{sig.name} on {task_id} rejected: {entry.error if entry else '?'}")
        if _why is not None:
            _why.append(str(entry.error) if entry is not None and entry.error else "no reason given")
    return ok


def crit_block(c, laid: "dict | None" = None) -> str:
    """A criterion as the issuer must see it to repair it: the text AND the procedure that decides it. `laid` — {probe
    id: the directory its pinned inputs were written to} — renders a probe runnable as shown, as a validator's is."""
    def _line(p):
        d = (laid or {}).get(probe_id(c.name, p))
        return (f"    - decided by `{probe_id(c.name, p)}` — {p.behaviour}: "
                f"`{p.command.replace(INPUTS_TOKEN, d.as_posix()) if d else p.command}`"
                f" → {must_show(p)}"
                + (f" (its {len(p.inputs)} pinned input file(s) are laid down in {d.as_posix()}; in an answer write "
                   f"`{INPUTS_TOKEN}` for that directory)" if d else
                   f" (+{len(p.inputs)} pinned input file(s))" if p.inputs else ""))
    return "\n".join([f"- **{c.name}**: {c.description}"] + [_line(p) for p in (c.check or ())])


def norm_words(text: str) -> set:
    """The words of a name or a reason, lowered — enough to ask "did the dispute name this?".

    A criterion the challenge never mentions is one the issuer would be dropping on his own
    initiative, which is the narrowing this refuses; matching on words rather than on an exact
    substring keeps `parser_accepts_any` inside a sentence about "the parser accepts any program".
    Short tokens are kept: a criterion may be called `c`, and dropping it unasked is the case."""
    return {w for w in re.split(r"[^a-z0-9]+", str(text or "").lower()) if w}


def questioned(engine, task) -> frozenset:
    """The node's criteria its standing dispute questions: those its reason names, and those the FAIL it answers
    cites under the version in force — a CHALLENGE after a FAIL is that FAIL's repair (§11.2). The reason alone
    missed «Comment handling in lexical analysis» in "the root's comment handling criterion" (2026-10-14). And those one
    of whose probes it names (`names_a_probe`)."""
    said = engine.challenge_reason(task.id) or ""
    asked, cited = norm_words(said), set()
    for e in reversed(engine.audit_log(task.id)):
        if e.rejected:
            continue
        if e.signal in (Signal.ASSIGN, Signal.ACCEPT_CHALLENGE):
            break
        if e.signal == Signal.FAIL:
            cited |= set(e.failed_criteria or ())
    return frozenset(c.name for c in task.spec.criteria
                     if c.name in cited or not norm_words(c.name) - asked or names_a_probe(said, c))


def names_a_probe(said: str, c) -> bool:
    """Does a dispute's text name one of `c`'s probes — by its id's hash (`findings.named`), or by its behaviour
    quoted whole? A dispute that misnamed the criterion («runtime-cwd-safe-imports» for «runs-from-any-cwd-and-safe-imports»)
    and quoted its probe's behaviour word for word questioned nothing: the issuer's re-pin of that probe was dropped,
    its acceptance refused as changing nothing, and it rejected a true dispute — two FAIL rounds, ~15 min (s17c). Whole,
    and quoted: a behaviour that is a phrase of the quoted one (`the count is correct`), or said in passing, names no
    probe — a criterion nobody disputed would be re-pinned."""
    flat, norm = " ".join(said.split()).lower(), lambda t: " ".join(str(t or "").split()).lower().rstrip(" .,;:!?")
    return bool(findings.named(said, [probe_id(c.name, p) for p in c.check])) or any(
        (b := norm(p.behaviour)) and re.search(rf"{re.escape(o)}\s*{re.escape(b)}[\s.,;:!?]*{re.escape(e)}", flat)
        for p in c.check for o, e in _QUOTES)


#: the quotes a dispute writes a probe's behaviour between, opener and closer
_QUOTES = (("'", "'"), ('"', '"'), ("«", "»"), ("`", "`"), ("‘", "’"), ("“", "”"))


# === The context: one piece, from the graph ===

def _label(t) -> str:
    return t.label()


def _covers(parent, child_id) -> str:
    return ", ".join(m.criterion_name for m in parent.criterion_mappings
                     if str(m.child_id) == str(child_id)) or "nothing mapped"


def _split_lines(engine, parent, skip=None) -> str:
    return "\n".join(f"- `{k.id}` ({_label(k)}) — {k.state.name}, Del={k.assignee}, covers "
                     f"{_covers(parent, k.id)}" + _SETTLED * _settled(engine, k)
                     for k in engine.graph.get_active_children(parent.id) if str(k.id) != str(skip)) or "- none"


#: A settled child the plan already rests on is not reopened (§12.14: consumed, once logged it stands); what it left
#: uncovered is carried by a new child — told only "the covering child must carry what failed", the issuer was refused
#: on every `revise_child` and the node closed (critic r5, 2026-10-04)
_SETTLED = " — SETTLED and relied on: not revised or reopened; a new child carries what it left (`add_child`)"


def _settled(engine, k) -> bool:
    return k.state in (State.DONE, State.ABANDONED) and engine.graph.is_consumed(k)


def _goal_and_why(engine, task) -> list[str]:
    """The goal as the user stated it, and the chain of criteria that makes this node necessary."""
    chain, node = [], task
    while node.parent_id is not None:
        parent = engine.graph.get_task(node.parent_id)
        chain.append((parent, node))
        node = parent
    out = [f"# The goal\n{node.spec.name or ''}\n\n{node.spec.description}\n"] if chain else []
    if chain:
        lines = [f"- `{p.id}` ({_label(p)}), {p.state.name}; this branch carries: {_covers(p, c.id)}"
                 for p, c in reversed(chain)]
        direct = chain[0][0]
        risks = "\n".join(f"- {n.item}" for n in set_aside_of(direct)) or "- none"
        out.append("# Why this node exists\n" + "\n".join(lines)
                   + f"\n\n## Its siblings in `{direct.id}`'s split\n{_split_lines(engine, direct, task.id)}"
                   + f"\n\n## The split's ACCEPTED_RISKS\n{risks}\n")
    return out


def _what_happened(engine, task) -> list[str]:
    """The node's own record: its trail, the last verdict per criterion, and what was delivered."""
    trail = [f"- {a.timestamp:%Y-%m-%d %H:%M} {a.signal.name} by {a.source}: "
             f"{a.old_state.name if a.old_state else '—'} → {a.new_state.name if a.new_state else '—'}"
             + (f" · failed {', '.join(a.failed_criteria)}" if a.failed_criteria else "")
             + (f" · {a.reason}" if a.reason else "") + (f" · {a.justification}" if a.justification else "")
             for a in engine.audit_log(task.id) if not a.rejected]
    out = ["# What happened to it\n" + ("\n".join(trail[-TRAIL:]) or "- nothing yet")]
    if rec := engine.get_exec_verdict(task.id):
        said = {str(p.get("criterion")): p.get("evidence") for p in rec.get("per_criterion") or []}
        gone = {c for c, ev, cmds in engine.rework_findings(task.id) if said.get(c) and not (ev or cmds)}  # all released
        out.append(f"## The last recorded verdict: {rec.get('verdict')}\n" + "\n".join(
            f"- {p.get('criterion')}: {p.get('verdict') or p.get('result')} — "
            + ("nothing it was refuted by binds the next PASS (a withdrawn pinned probe, a retired finding): not "
               "demanded" if p.get("criterion") in gone else str(p.get("observed") or p.get("evidence") or "")[:400])
            for p in rec.get("per_criterion") or []))
    if delivered := engine.deliver_result(task.id):
        out.append(f"## The last delivery (tail)\n{str(delivered)[-DELIVERY_TAIL:]}")
    # …and why its sessions stopped without a signal: told nothing, the issuer re-issued a root 38 times whose packet no
    # longer fit the executor's window, each session ending `prompt_too_long` (GB_sql_database_tmxu0n436)
    if stopped := [str(r.get("message")) for r in engine.pipeline_log()
                   if str(r.get("message", "")).startswith(f"{task.id}: ")
                   and any(k in str(r.get("message")) for k in ("DID NOT PARSE", "delivery held"))
                   and not is_limit(r.get("message"))]:     # a limit window's probes would evict the real stop reasons
        out.append("## Its sessions that stopped without a signal (latest)\n" + "\n".join(f"- {m}" for m in stopped[-3:]))
    return out


def _standing_findings(engine, task_id, lists: "str | None" = None, ex=None, laid_dirs: "dict | None" = None) -> str:
    """The node's regression set, a line per finding with its id, as run, as the engine demands it — bounded as the
    executor's packet is (`capped`): the whole set inline, 562k characters, would end the dispute's issuer session
    `prompt_too_long` (GB_sql_database_tmxu0n436). `lists`: where its file goes (`list_key`) — the contact's own round,
    where each finding's files are laid from the system's record and its command shown over them
    (`Engine.lay_probe_files`, through `ex`): the contact mounts no earlier round. A command over a pinned probe's
    inputs (`{inputs:<id>}`) is shown over the directory this turn laid them in (`laid_dirs`), as the validator's is."""
    workdir, up = (engine.get_exec_verdict(task_id) or {}).get("workdir"), findings.round_stands(engine.graph)
    # …over the copy the contact works in, which `_ask` makes at `<lists>/place`
    run = lambda p, why: (engine.lay_probe_files(over_dirs(p["as_run"], laid_dirs), lists, ex, Path(lists) / "place")
                          if lists and ex and p.get("as_run") and not why else p.get("seen") or p.get("as_run"))
    return "".join(f"\n- {c}:" + capped([f"[{p.get('id')}] {p.get('behaviour')}: `{run(p, why)}` "
                                         f"(recorded: «{p.get('expect')}»)" + (f" — {why}: shown, not demanded" if why
                                                                               else "")
                                         for p in ps for why in [unrerunnable(p, None, workdir, standing=up)]],
                                        "standing findings", list_key(engine, task_id, c, "issuer", at=lists))
                   for c, ps in engine.regression_probes(task_id).items()).lstrip("\n")


def _decided_nothing(engine, task, answer: dict) -> str:
    """Why an acceptance that changed and retired nothing is no decision, and the move that is one: where the dispute
    questions a criterion, its re-pin — steered to REJECT there, an issuer rejected a true dispute (s17c)."""
    if said := [str(i) for i in answer.get("retire_findings") or ()]:
        return ("your acceptance retired nothing: " + ", ".join(said) + " names only findings the dispute did not name "
                "— rule only on what it named. Where the disputed probe is not demanded, REJECT the dispute saying so"
                + _LAST_CHECK)
    if asked := sorted(questioned(engine, task)):
        return (f"your acceptance changed no criterion as it will stand and retired no standing finding, so it decided "
                f"nothing. The dispute questions {', '.join(asked)}: where its check fails correct work, ACCEPT with that "
                f"criterion's disputed probe replaced by one whose expectation holds, every other probe carried")
    return ("your acceptance changed no criterion as it will stand and retired no standing finding, so it decided "
            "nothing. Where the disputed probe is not demanded — no standing finding carries it — the dispute has "
            "nothing to take back: REJECT it saying so, and the executor delivers" + _LAST_CHECK)


def _accepted_spec(engine, task, criteria: list, every: bool = False):
    """The contract an acceptance's `criteria` install (`spec_with`) — additions only on the user's criteria, a check
    re-pinned only where the dispute questions it at an AUTO root; `every`: as if it questioned them all."""
    repin = (frozenset(c.name for c in task.spec.criteria) if every
             else questioned(engine, task) if is_auto_root(engine.graph, task) else frozenset())
    return spec_with(task, criteria, additions_only=users_criteria(engine.graph, task), repin=repin,
                     split=_split_of(engine, task))


def _no_decision(engine, task, answer: dict, spec, retire) -> str:
    """Why an acceptance decides nothing, and the move that is one — '' where it decides. A re-pin the contract does not
    take refuses it whole, beside whatever else it changes: taken in part, the impossible pin stayed and the executor
    re-consented to it; told only "changed nothing", an issuer whose re-pin of the disputed probe was left out rejected a
    true dispute, two FAIL rounds on a pin no correct program prints (s17c)."""
    stored, asked = {c.name: len(c.check) for c in task.spec.criteria}, questioned(engine, task)
    if is_auto_root(engine.graph, task) and (fewer := [
            f"{n} with {len(_checks_of(a))} probe(s) where it holds {stored[n]}" for a in answer.get("criteria") or ()
            if (n := str(a.get("name", ""))) in asked and 0 < len(_checks_of(a)) < stored[n]]):
        return (f"your acceptance re-pins {'; '.join(fewer)}, and a root check is never re-pinned with fewer probes, so "
                f"the acceptance is refused whole. Keep every probe: replace the disputed one, carry the others as they "
                f"stand")
    took = {c.name: c for c in spec.criteria}
    every = _accepted_spec(engine, task, answer["criteria"], every=True) if answer.get("criteria") else spec
    left = [c.name for c in every.criteria if c.name in stored and took.get(c.name) != c]
    if left and not is_auto_root(engine.graph, task) and users_criteria(engine.graph, task):
        return (f"your acceptance re-pins {', '.join(left)}, and a node of the user's plan takes additions only: its "
                f"checks are the user's. Add a criterion whose check holds, or REJECT saying why the contract stands")
    if left:
        return (f"your acceptance re-pins {', '.join(left)}, which the dispute does not question — it names neither "
                f"the criterion nor one of its probes, by its id or its behaviour quoted whole — so the acceptance is "
                f"refused whole. A root check is re-pinned only where the dispute questions it "
                f"({', '.join(sorted(asked)) or 'none here'}). Re-pin what it questions; where its ground is a check it "
                f"does not name, REJECT naming that check's id, and the executor disputes it by name")
    # an acceptance that changes no criterion as it will stand and retires no standing finding answers nothing:
    # re-offered unchanged, it was challenged again ten times and the part closed by count (AUTO haiku coreutils,
    # root.build, 2026-10-12) — the criteria echoed back as they stand included (11 of them, same row)
    unchanged = not retire and took == {c.name: c for c in task.spec.criteria}
    return _decided_nothing(engine, task, answer) if unchanged else ""


def _own_split(engine, task) -> str:
    """The node's own split with each child's WHOLE contract. Named only, a plan could not be judged: asked
    what a plan decision rested on, a holder named the children's criteria and checks (3 of 4 forks of one
    decision, 2026-09-25 — one run, small n) — and a criteria edit replaces the whole set, so names alone
    invite a destructive one."""
    return "\n".join(f"- `{k.id}` ({_label(k)}) — {k.state.name}, Del={k.assignee}, covers {_covers(task, k.id)}\n"
                     + "\n".join("  " + line for c in k.spec.criteria for line in crit_block(c).splitlines())
                     for k in engine.graph.get_active_children(task.id)) or "- none"


def seam_findings(engine, task_id) -> list[str]:
    """What the split's own claims of its seams contradict (`decompose.seams`) — the check its authoring ran, read again
    wherever the split is repaired: the plan was checked when written, and a repair fed by contact was not."""
    return seam_problems(extract_spec(engine, str(task_id))) if engine.graph.get_active_children(task_id) else []


def _seams_text(seams: list) -> str:
    """The seam findings as what they are: a report on the split, holding nothing — a child the repair adds or revises
    is where they are met, and nothing waits on them."""
    return ("## What this split's own claims about its seams contradict (reported — nothing waits on these; a child "
            "you add or revise is where one is met)\n" + "\n".join(f"- {s}" for s in seams))


def _gate_findings(engine, task_id) -> str:
    """What the plan gate holds open, each finding WITH its reason; ⊥ said as ⊥. Keys alone gave the issuer
    nothing to act on, and an absent review printed as "none" beside a question claiming findings were open —
    three samples, three invented moves (2026-09-25)."""
    holes = "\n".join(f"- {h.check_name}: {h.details}" for h in engine.split_holes(task_id)) or "- none"
    if seams := seam_findings(engine, task_id):   # reported, never gated (§20.10, form item (4)): beside, not inside
        holes += "\n\n" + _seams_text(seams)
    open_ = engine.open_l2_findings(task_id)
    if open_ is None:
        return (f"Syntactic holes:\n{holes}\n\nLevel-2: no current review of this version of the plan — "
                f"nothing is a Level-2 finding until one runs (the holes come first)")
    rec = engine.get_critique(task_id) or {}
    why = {str(v.get("criterion")): v.get("why", "") for v in rec.get("criteria_verdicts") or ()}
    why.update({"undecided: " + str(g.get("obligation", "")): "admits: " + str(g.get("admits", ""))
                for g in rec.get("undecided_obligations") or ()})
    conflicts = [str(c.get("why") or "") for c in rec.get("conflicts") or ()]
    lines = [f"- `{k}` — " + (why.get(k) or next((w for w in conflicts if k.startswith("conflict:")
                                                   and " ".join(w.split())[:60] in k), ""))
             for k in open_]
    own = sum(str(k).startswith("undecided: ") for k in open_)
    # …and what the review reported without gating — a conflict with a settled child — to the party whose move lifts it:
    # kept only in the stored record, no issuer saw it (critic over 2f8ddcc)
    if told := [l for l in str(rec.get("semantic_findings") or "").splitlines() if l.startswith("[reported, not gating")]:
        holes += ("\n\nReported, not gating, each with its reason (a settled child's criterion against a live one: a new "
                  "pinned check of the contested behaviour on the live child decides which holds; a split deferred on "
                  "nothing it needs: split that part now):\n" + "\n".join(f"- {l}" for l in told))
    return (f"Syntactic holes:\n{holes}\n\nLevel-2 findings (a `dispute` names one EXACTLY as written between "
            f"the backticks):\n" + ("\n".join(lines) or "- none")
            + ("\n\nA finding that no child carries one of this node's own pinned probes is closed by giving a child "
               "a criterion whose probe `carry`s that probe's id (shown after `decided by`) — the system copies it "
               "exactly, its pinned inputs included." if lines else "")
            + (f"\n\n{own} of them (`undecided: …`) are requirements of this node's OWN goal that none of its OWN "
               f"criteria's PINNED CHECKS decides: no move on a child closes one — the next review names it again. "
               f"What closes one is a NEW pinned check of the clause its finding says no check probes — `add_criterion` "
               f"on this node with that check (a criterion over checks already pinned here decides nothing new and is "
               f"refused), then `reshape` with `map` gives it the child that delivers it."
               + ("" if is_auto_root(engine.graph, engine.graph.get_task(task_id)) else
                  " A finding that only names another disguise of what a pinned check already refuses is that "
                  "check's residue: `dispute` it, its reason naming that check's id.")
               if own else ""))


def _users_sentence(engine, task) -> str:
    """The opening of the goal as its user wrote it — the root's description, which no issuer rewrites — the
    reference an answer's language is pinned to. "The language the goal is written in" left the model to infer
    it: on an English goal one plan answer came back in German and put German criteria into the user's goal
    (measured 2026-09-25, with the operator's own language already kept out of the call)."""
    while task.parent_id is not None and (up := engine.graph.get_task(task.parent_id)) is not None:
        task = up
    text = " ".join((task.spec.description or task.spec.name or "").split())
    return re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0][:160] or "(the goal as written above)"


def issuer_context(engine, task_id: TaskId, question: str, refusal: str = "", laid: "dict | None" = None,
                   lists: "str | None" = None, ex=None) -> str:
    """Everything the issuer needs to answer about `task_id`, and nothing twice: the goal, why the node exists,
    its contract, and what the question needs — for the plan and the repair, the split's whole contracts; for the
    plan, the gate's findings with their reasons and nothing of the node's history (a holder asked what its plan
    decision rested on did not use the deadline or the rework count — one decision, 4 forks,
    experiments/e3_specbench/issuer_context_probe.py); for the others, what happened to the node. NOT CARRIED,
    a named residue: the source statement a goal points to and files in the workspace — the issuer has tools
    only on a dispute (`CONTACT`), and the holder used both. `lists`: where a long list's file goes — the contact's
    own round, which its session holds (`list_key`)."""
    task = engine.graph.get_task(task_id)
    out = _goal_and_why(engine, task)
    plan, split = question == "plan", question in SPLIT_QUESTIONS
    out.append(f"# The node: `{task.id}` — {task.spec.name}\n\n{task.spec.description}\n\n"
               f"State {task.state.name} · Del {task.assignee}"
               + ("" if plan else f" · rework {task.iteration}/{task.max_iterations} · deadline "
                                  f"{on_the_wall(engine.graph, task.deadline) if task.deadline else 'none'}")
               + "\n\n## Its contract (the WHOLE obligation)\n"
               + ("\n".join(crit_block(c, laid) for c in task.spec.criteria) or "- (no criteria)"))
    if engine.graph.get_active_children(task.id):
        out.append(f"## Its own split\n{_own_split(engine, task) if split else _split_lines(engine, task)}")
    if not plan:   # a repair needs what was observed failing: the verdict and the delivery ride here
        out += _what_happened(engine, task)
    # …and what validators saw beyond the criteria in the WHOLE split this question's moves lie in: FM-1.f met at contact
    # (§8.3). Shown only the asking node's subtree, a split re-planned by promotions answering a sibling's block never
    # saw the hole another child's validator wrote (critic over 5cad9c4)
    holder = task.id if split or task.parent_id is None else task.parent_id
    rows = engine.outside_the_criteria(holder, own=not split and task.parent_id is None)
    out += [s for s in [outside_text(engine, holder, rows, lists)] if s]
    if question == "plan":
        out.append(f"## What the plan gate holds open\n{_gate_findings(engine, task_id)}")
        # …and the issuer's answers to this node's challenges on the version in force: unseen, a rejected challenge was
        # raised again unchanged, the findings being the same (critic, 2026-10-07) — the executor's packet reads the same
        if said := answered_challenges(engine, task):
            out.append(said.strip())
    if question == "repair":
        out.append("## What contact refuted\n" + (what_contact_refuted(engine, task_id)
                                                   or "- a child consumes a producer that was cancelled (see the split above)"))
        if seams := seam_findings(engine, task_id):
            out.append(_seams_text(seams))
    if question == "unrun":
        out.append("## What its validator could not run\n" + "\n".join(
            f"- {r['criterion']}: [{r['id']}] `{r['as_run']}` — the validator: «{r['why']}»"
            for r in engine.unrun_findings(task_id)))
    if question == "external" and (order := engine.order_refuted_by(task_id)):
        out.append(f"## What its block names cannot come first\n{order}")
    if question == "dispute":
        out.append(f"## THE DISPUTE, in its executor's words\n"
                   f"{engine.challenge_reason(task_id) or '(no reason recorded)'}")
        if given := answers_given(engine, task):
            out.append(given.strip())
        # …AND THE FINDINGS IT MAY BE DISPUTING. A FAIL can rest on a validator's own probe, which no criterion names
        # (a `<wchar.h>` program, a sibling's scope, failed root.pp round after round — GB_c_compiler_tmp5cb096); the
        # issuer judged the challenge with the contract alone in view and none of what was demanded under it
        # …and what retiring one over a part's pinned check does, said wherever it may be ruled: told at an AUTO root
        # only, a node below believed the part's pin was the part's contract and out of its reach (c_compiler pp-rest)
        own = engine.plans_own_findings(task_id)
        lifts = (f" {', '.join(own)} only say a settled part's pinned check does not hold. Run it: where it is false on "
                 "correct work (it held only while a sibling's work was missing), accept, naming those ids in "
                 "`retire_findings`: the part stays as it settled, this node's validation stops running that check under "
                 "the criteria those ids stand on, and a later change of a criterion's text ends the ruling. Where the "
                 "work broke it, reject." if own else "")
        out.append("## The validator's findings standing on this node — every PASS of it must re-run them\n"
                   # …a command copying out of `<round>.laid` reads a directory BESIDE the round, read-only: an issuer
                   # looked for it inside its round and ruled the finding unrunnable (row 4, c_compiler, 2026-10-30)
                   + (f"(A command that starts by copying out of `{laid_beside(lists).as_posix()}` reads the "
                      f"files the system recorded when the finding was filed, laid there beside your round, read-only: "
                      f"run it as shown.)\n" if lists else "")
                   + (_standing_findings(engine, task_id, lists, ex, laid) or "- none")
                   + ("\n\nUnder AUTO this node's criteria are the user's goal: only the user rules a finding of the "
                      "validator outside them — answer without `retire_findings`."
                      + (" Except a check of the plan, not of the goal:" + lifts if lifts else "")
                      if is_auto_root(engine.graph, task) or engine.users_plan() else
                      "\n\nA finding stays demanded until you rule it outside its criterion as written: accept, naming "
                      "in `retire_findings` a finding the dispute named — its full id retires it under that criterion, "
                      "its bare hash under every criterion it stands on. Nothing else retires one — not a reworded "
                      "criterion, not a conceded pinned probe — and a later change of that criterion's text ends the "
                      "ruling." + lifts))
    if question == "plan":
        # …AND THE NODE'S OWN REGISTER, which the context showed only as its parent's: a root has none above it,
        # so a hole on the root's register was asked about with the register itself nowhere in view.
        _own = "\n".join(f"- «{n.item}»" + (" — the split's denial by S: its odds, not an accepted risk; it covers no "
                                             "gap (§9.2)" if n.denial else "")
                         for n in register_of(task).items) or "- none"
        _flag = risks_naming_own_criteria(task)
        out.append(f"## This node's own ACCEPTED_RISKS\n{_own}"
                   + (f"\n\nNaming one of this node's criteria (CHECK-4; `drop_risk` takes them out): "
                      + "; ".join(f"«{i}»" for i in _flag) if _flag else ""))
    q, moves = QUESTIONS[question], moves_for(engine, task, question)
    out.append(f"# The question: {ask_of(engine, task, question)}"
               + ("\n\nIts offer lapsed: its contract never started, and a lapse shows nothing infeasible (an executor "
                  "that finds a contract so challenges it) — continue it with a new contract whose deadline leaves what it "
                  "waits on time; closing it is not a move here."
                  if _offer_lapsed(engine, task) else
                  "\n\nIts delivery stands unvalidated: the validation's bound passed with no verdict, which says "
                  "nothing against the work — `reassign` keeping its contract re-presents it, the executor re-delivers "
                  "the same result and it is validated then; closing it is not a move here."
                  if _validation_lapsed(engine, task) else
                  "\n\nThis is the user's goal under AUTO: closing it is theirs, not yours — continue it with a contract "
                  "the standing findings can be met under; unanswered, it closes by its bound."
                  if "cancel" in q["moves"] and "cancel" not in moves else
                  "\n\nThis node is part of the plan the user handed in: `cancel` does not close it here — it STOPS the "
                  "whole run and tells the user this plan cannot be carried. Choose it only for that; a part that ran "
                  "out of time while it waited on its producer is continued by a new contract."
                  if "cancel" in moves and engine.users_plan() and users_criteria(engine.graph, task) else "")
               + "\n\nAdmissible moves: " + ", ".join(f"`{m}`" for m in moves)
               + f"\n\nWrite every text you return in the same language as this sentence the user wrote: "
                 f"«{_users_sentence(engine, task)}» — even where other text in this packet is in another "
                 f"language"
               + (f"\n\n## Your previous answer was REFUSED\n{refusal}\nAnswer again within the rules."
                  if refusal else ""))
    return "\n\n".join(out) + "\n"


QUESTIONS = {
    "plan": {"ask": "the plan gate holds this node's split (§11.5) — the review's findings, or the "
                    "Syntactic holes, are open. Make the split carry its criteria, or show a finding wrong — "
                    "or, where the defect is in this node's OWN contract (its criteria jointly unsatisfiable, "
                    "one no procedure can decide, or a requirement of its goal no criterion writes), which no "
                    "split repairs, challenge the contract to its issuer.",
             "moves": ("revise_child", "add_child", "drop_child", "reshape", "add_criterion", "drop_risk",
                       "resplit", "dispute", "refine", "challenge")},
    "dispute": {"ask": "the executor CHALLENGED this contract. Can the contract be met as written? A report that the "
                       "work is more than one session names no defect: its sessions continue one another (each hands "
                       "over to the next) until the criteria hold or the deadline; reject it "
                       "saying so, the work goes on under the same contract.",
                "moves": ("accept", "reject")},
    "escalation": {"ask": "the node is ESCALATED — its executor's contract ended without a verdict (the trail says "
                          "which route): the forecast you issued it with, its deadline and rework bound, did not hold. "
                          "Only you decide, by one of: `reassign` — a new contract for it (a later deadline, a larger "
                          "bound, corrected criteria, another executor); `redecompose` — the split you hold, of which it "
                          "is a part, re-made in one act: it leaves, and the `children` you name (each with `replaces` "
                          "naming it where it stands in for it) carry what it covered; `cancel` — close it.",
                   "moves": ("reassign", "redecompose", "cancel")},
    "repair": {"ask": "the split needs repair: contact REFUTED it (the node FAILED on criteria its children "
                      "cover while they passed — the covering child must carry what failed, or, where that "
                      "child is SETTLED, a new child must), or a confirmed dependency of a child runs against the plan's order (a "
                      "producer that cannot finish before it — only a re-decomposition restores it, §15.5). FIRST, "
                      "where a child's BLOCK on the cycle names its own criteria whose checks run its consumers' code "
                      "(a part checked by building and running the whole), `split_off` that child: `child_id` it, "
                      "`items` those criteria — every one its BLOCK names — and, if none of its own would remain, "
                      "`criteria` its own unit is checked by. One act keeps all its work: it is re-authored in "
                      "place without them, its passed parts kept, and a new sibling (`child`: name, description) "
                      "carries them with their checks, after the consumers they run. Otherwise, in ONE `reshape` "
                      "drop the children the cycle runs through and add those that replace them, cut so that none "
                      "waits on one that waits on it. Or a child waits on a producer that was cancelled (drop that "
                      "Dep, and cover what it fed another way).",
               "moves": ("revise_child", "split_off", "add_child", "drop_child", "reshape", "drop_dependency",
                         "resplit")},
    "split": {"ask": "this childless node was judged larger than one session of its executor, so it is not a "
                     "leaf and its split is owed (§3.7, §11.5 deferred decomposition): its DELIVER as a leaf "
                     "is refused. Split it.",
              "moves": ("refine",)},
    "parked": {"ask": "the executor's rounds on this node twice ended without any signal. Decide what "
                      "happens to the node.",
               "moves": ("reassign", "cancel")},
    "external": {"ask": "the node is BLOCKED and no producer finishing will clear it — it names nothing the "
                        "graph still has to produce, or producers that already passed, or producers that "
                        "cannot finish before it (its reason is in the trail). If what it lacks is something "
                        "this project can produce, PROMOTE it — a producer beside it in the split you hold, which "
                        "it then waits for (§11.3: mandatory for a producible blocker). Otherwise resolve it "
                        "(what it names is not what it needs: the record is refuted and it resumes — a block that names "
                        "only the size of its own work names nothing it lacks, and resumes so), re-issue it "
                        "(a contract it can meet without that), or close it.",
                 "moves": ("promote", "resolve_block", "reassign", "cancel")},
    "outside": {"ask": "a validator of a child of this split observed what none of the criteria writes (listed above "
                       "under «What validators observed outside the written criteria»); no verdict rests on it. Judge "
                       "each against the goal: where the goal needs it, write it into the split — revise the child that "
                       "should carry it, or, where that child is SETTLED, add a child (or reshape) that does; where it "
                       "does not, `decline` with why. Either answers every observation listed, once.",
                "moves": ("revise_child", "add_child", "reshape", "decline")},
    "unrun": {"ask": "the validator could not run the standing findings listed above under «What its validator could "
                     "not run» as they were filed — their own setup failed, it says why — so the PASS waits on them, and "
                     "no truthful report of the validator's lifts that. Run each as shown. Where it cannot run on any "
                     "delivery (it reads what no round lays, a copy gone with its round), `retire` it, naming it in "
                     "`retire_findings`: demanded no more, on the record with the validator's reason and yours. Where "
                     "it can, or you cannot tell, `keep` it, naming it the same way: it stays demanded.",
              "moves": ("retire", "keep")},
}

_CRITERIA = {"type": "array", "items": {"type": "object", "properties": {
    "name": {"type": "string"}, "description": {"type": "string"},
    "check": {"type": "array", "items": {"type": "object", "properties": {
        "behaviour": {"type": "string"}, "command": {"type": "string"}, "expect": {"type": "string"},
        "exact": {"type": "boolean", "description": EXACT_TEXT},
        "carry": {"type": "string", "description": "the id of one of THIS node's own pinned probes, as shown after "
                  "`decided by` (`criterion#hex`): the system copies that probe into this criterion exactly — command, "
                  "expect and its pinned inputs with their content; the other fields of this probe are then ignored. "
                  "Use it when the plan gate says a child does not carry the parent's probe."},
        "inputs": {"type": "array", "items": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"]}}},
        "required": ["behaviour", "command", "expect"]}}},
    "required": ["name", "description", "check"]}}

#: What shows an expectation pinned on the user's goal without the work (`off_the_goal`) — wherever an answer pins one.
_DERIVATIONS = {"type": "array", "items": {"type": "object", "properties": {
    "criterion": {"type": "string"}, "probe": {"type": "string"}, "derived_by": {"type": "string"}},
    "required": ["criterion", "probe", "derived_by"]}, "description":
    "AT THE ROOT OF AN AUTO PROJECT, for every probe your criteria pin there that is not pinned already — one a "
    "criterion you add carries (an accept, `add_criterion`, `reassign`), and one you change on a criterion that stands "
    "AND the one it replaces: the criterion, the probe's command, and `derived_by` — a command that PRINTS that probe's "
    "true expected output WITHOUT running the work under test (it runs where only the probe's pinned inputs are, "
    "`{inputs}` naming them), e.g. python3 with its standard library, sqlite3 included. A probe you pin must print its "
    "`expect`; a replaced one's must not print its old `expect`."}

MOVE_SCHEMA = {
    "type": "object",
    "properties": {
        "tech_report": TECH_REPORT,
        "move": {"type": "string"},
        "justification": {"type": "string", "description": "why — in terms of the contract and the goal"},
        "criteria": {**_CRITERIA, "description": "reassign / revise_child: the WHOLE criteria set as it "
                     "will then stand, kept ones unchanged and included; split_off: only the criteria the child "
                     "gains"},
        "derivations": _DERIVATIONS,
        "child_id": {"type": "string", "description": "revise_child / drop_child / split_off: which child"},
        "covers": {"type": "array", "items": {"type": "string"},
                   "description": "revise_child: this node's criteria the child carries — maps them to it"},
        "child": {"type": "object", "description": "add_child: {name, description, criteria, covers: "
                  "[this node's criterion names it carries], reads: [ids of this node's children whose "
                  "result its checks read — each becomes a Dep, so it runs after them; in a reshape, also the "
                  "name of a child the same reshape adds], replaces: [ids of children the same reshape drops that "
                  "it stands in for — their consumers then read it; a child named as the one it replaces needs "
                  "none]}; promote: {name, "
                  "description, criteria} of the producer of what the blocked node lacks; split_off: {name, "
                  "description} of the sibling the moved criteria go to (its criteria, covers and reads are the "
                  "system's)"},
        "criterion": {"type": "string", "description": "dispute: the finding's criterion"},
        "items": {"type": "array", "items": {"type": "string"},
                  "description": "drop_risk / reshape: the ACCEPTED_RISKS entries (their text) that name this node's "
                                 "criteria; split_off: the child's criteria moved to the new sibling; challenge: the contract's fields it questions (criterion names, "
                                 "`deadline`)"},
        "children": {"type": "array", "items": {"type": "object"},
                     "description": "reshape / redecompose: the children added, each as `add_child`'s `child`"},
        "drop": {"type": "array", "items": {"type": "string"},
                 "description": "reshape / redecompose: ids of children leaving the split (active, not settled); "
                                "redecompose drops the escalated node itself unasked"},
        "map": {"type": "object", "additionalProperties": {"type": "array", "items": {"type": "string"}},
                "description": "reshape: children standing in the split → this node's criteria each now carries "
                               "(added to what it carries) — the split's mapping, no child revised"},
        # add_criterion reuses `criteria`: the NEW criteria to append to this node's own contract
        "another_executor": {"type": "boolean", "description": "reassign: hand it to a different executor"},
        "extend_hours": {"type": "number", "description": "reassign: the new deadline, hours from now"},
        "max_iterations": {"type": "integer", "description": "reassign: the new contract's rework budget"},
        "action": {"type": "string", "description": "resolve_block: what was done about the blocker"},
        "cause": {"type": "string", "enum": ["spec_defect", "scope_expansion", "capability_mismatch", "other"],
                  "description": "reassign / revise_child / add_criterion: why the contract or its executor changes"},
        "retire_findings": {"type": "array", "items": {"type": "string"},
                            "description": "retire / keep: the ids of the findings the validator could not run you rule on"},
    },
    "required": ["move", "justification"],
}

#: The dispute's own answer: two decisions, the corrected contract on an accept.
ISSUER_SCHEMA = {
    "type": "object",
    "properties": {
        "tech_report": TECH_REPORT,
        "decision": {"type": "string", "enum": ["accept", "reject"]},
        "justification": {"type": "string",
                          "description": "why — in terms of the contract. On a rejection this is "
                                         "what the executor is given to work from."},
        "criteria": {**_CRITERIA, "description":
                     "ON ACCEPT ONLY, and only when the contract changes: on a node of a plan the user gave, only the "
                     "criteria you ADD (the user's stand as written, and one you omit is kept); otherwise the WHOLE set "
                     "as it will then stand, each with its pinned `check` — one you omit is dropped. An accept that "
                     "only rules findings out (`retire_findings`) carries no criteria."},
        "retire_findings": {"type": "array", "items": {"type": "string"}, "description":
                            "ON ACCEPT ONLY: ids of the validator's standing findings (listed in the packet) that the "
                            "dispute named by id and you rule outside the criterion as written — no longer demanded "
                            "of this node while that criterion's text stands; your justification is recorded as why. "
                            "Leave out every finding the criterion does ask for."},
        "derivations": _DERIVATIONS,
    },
    "required": ["decision", "justification"],
}


# === The rules every answer passes before anything is signalled ===

def _probes(stored, answered: tuple) -> tuple:
    """The answer's probes, each carrying the stored probe's pinned inputs where it restates one (same
    command) — the issuer sees only that inputs exist, never their contents, so a restatement must not
    drop the corpus. No probes in the answer = the stored ones stand. A REWRITTEN command that still reads
    `{inputs}` carries the criterion's pinned files: an accepted dispute corrects the command, and dropped
    inputs left `{inputs}/x` unresolved — a probe printing "No such file" and then its `ok` (critic over
    session a597fc08)."""
    if not answered:
        return stored.check
    by_cmd = {pr.command: pr for pr in stored.check}
    pinned = tuple({path: (path, body) for pr in stored.check for path, body in pr.inputs}.values())
    # …and a probe that NAMES the files without their content gets the content this criterion pins (`with_named_files`):
    # an accepted dispute re-pinned an integration node's commands and kept its 41 files named and empty (2026-10-22)
    files = pinned_files([stored])
    named = lambda pr: dataclasses.replace(pr, inputs=tuple(with_named_files(
        {"name": stored.name, "check": [{"command": pr.command, "inputs": list(pr.inputs)}]}, files)["check"][0]
        ["inputs"].items()))
    return tuple(dataclasses.replace(pr, inputs=by_cmd[pr.command].inputs) if pr.command in by_cmd and not pr.inputs
                 else dataclasses.replace(pr, inputs=pinned) if not pr.inputs and INPUTS_TOKEN in pr.command
                 else named(pr) if pr.inputs else pr for pr in answered)


def spec_with(task, criteria: list, additions_only: bool = False, repin: frozenset = frozenset(), split=()) -> Spec:
    """The node's contract with its criteria as the answer states them — merged BY NAME onto the stored
    ones, so what the answer does not speak to (Dep glue, composition, pinned inputs) is carried, not
    silently dropped. A criterion the answer leaves out is dropped, except one whose check reads a producer's result
    (`depends_on`), which carries its Dep edge.
    `additions_only`: every stored criterion's text stands exactly and none is dropped; the answer adds new names, and
    re-pins the check of a criterion named in `repin` — the ones a dispute questioned — never with fewer probes. The
    procedure is the issuer side's instrument, not the user's word: a probe its own criterion's text refutes was
    re-written eight times and dropped each time until the root closed by count (AUTO haiku sql_database, root
    «Comment handling», 2026-10-14); and the same answers restated every other criterion, one of them 3 probes → 1."""
    criteria, why = _carry(task, criteria, split)   # a probe kept by its id is the stored one, never the placeholder beside it
    if why:
        raise ValueError(why)
    stored = {c.name: c for c in task.spec.criteria}
    if additions_only:
        answered = {str(c.get("name", "")): _checks_of(c) for c in criteria}
        pinned = lambda c, new: new if c.name in repin and len(new) >= len(c.check) else c.check
        return dataclasses.replace(task.spec, criteria=tuple(
            dataclasses.replace(c, check=pinned(c, _probes(c, answered.get(c.name, ())))) for c in task.spec.criteria) + tuple(
            Criteria(c.get("name", ""), c.get("description", ""), check=_checks_of(c))
            for c in criteria if c.get("name") not in stored))
    named = {str(c.get("name", "")) for c in criteria}
    kept = tuple(dataclasses.replace(stored[c["name"]], description=c.get("description", ""),
                                     check=_probes(stored[c["name"]], _checks_of(c)))
                 if c.get("name") in stored
                 else Criteria(c.get("name", ""), c.get("description", ""), check=_checks_of(c))
                 for c in criteria)
    glue = tuple(c for c in task.spec.criteria if c.depends_on and c.name not in named)
    return dataclasses.replace(task.spec, criteria=kept + glue)


def held_by_a_holder(engine, party: str) -> bool:
    """Is this party the user's standing agent wherever the system does not move for it — holding its part of the tree
    (SOLO/SEMI), or the person himself with no mode — whose moves the system never makes for it?"""
    return str(party) == str(_config_agent_id()) and party_kind(engine.graph, party) != "machine"


def system_splits(engine, task) -> bool:
    """Is this childless node's owed split (§3.7) the system's to make — the refine round on it? The split is the
    node's executor's move and the round re-authors no contract (`held_contract`), so wherever the system executes
    the node — an AUTO root included — and only under a mode (before modes the system made no split move). Where it
    is not, the node's work goes on as before and its executor's DELIVER as a leaf is refused, the lift his split —
    the system must not stop spawning on a node whose split nobody would then make."""
    return (engine.mode() is not None and not engine.graph.get_active_children(task.id)
            and engine.split_owed(task.id) is not None and not held_by_a_holder(engine, str(task.assignee)))


def split_has_a_mover(engine, agents, task) -> bool:
    """Will someone make this node's owed split — the system (`system_splits`), or its issuer, a party no role
    of the registry stands for (a person, the holder), who is shown it as his step? Only then may the system stop
    spending sessions on it; with nobody to move, the node runs as before (its DELIVER refused, parked, asked)."""
    return system_splits(engine, task) or agents.get(str(engine.graph.issuer_of(task.id))) is None


def narrowing_at_the_root(engine, task, new_spec: Spec) -> Optional[str]:
    """Under AUTO the root's criteria are APPEND-ONLY for the system: the user's contract is changed
    only by the user, and a machine that may drop or reword a root criterion can reach DONE on a goal
    nobody asked for — the false "done" this mode is measured for. The pinned check is not that word: re-pinned only
    by an accepted dispute over the criteria it questioned (`spec_with`), it passes the same admission gates and
    stands on the log as a revision."""
    if not is_auto_root(engine.graph, task):
        return None
    word = lambda c: dataclasses.replace(c, check=())
    new = {c.name: word(c) for c in new_spec.criteria}
    if lost := [c.name for c in task.spec.criteria if new.get(c.name) != word(c)]:
        return (f"under AUTO the root's criteria are the user's contract and are kept exactly; this "
                f"answer drops or changes {', '.join(lost)}. Add criteria if the goal needs more; "
                f"never remove or reword one.")
    return None


#: Seconds a derivation of a re-pinned expectation may run (`underived_at_the_root`).
DERIVE_TIMEOUT_S = 60


def _derived(command: str, criterion, probe, execution=None) -> tuple[Optional[str], str]:
    """(what the command printed, '') run in an EMPTY place holding only the probe's pinned inputs — where the project's
    work runs, so a value is derived on the platform its check is decided on — or (None, why it could not run — with
    its exit code and the tail of its stderr, so the next answer knows what to change)."""
    ex = execution or LocalExecution()
    if not (bash := ex.shell()):
        return None, "could not run: no `bash` here"
    with ex.scratch("gfso-derive-", system=True) as tmp:
        try:
            laid = materialize_inputs((criterion,), Path(tmp) / "inputs", ex.files)
        except ValueError as e:
            return None, f"could not lay down the probe's inputs ({e})"
        cmd = command.replace(INPUTS_TOKEN, laid.get(probe_id(criterion.name, probe), Path(tmp)).as_posix())
        try:
            p = ex.session(tmp).run([bash, "-c", IN_THE_WORKS_PATH + cmd], cwd=tmp, timeout=DERIVE_TIMEOUT_S)   # a proposed command: its own container
        except (OSError, subprocess.TimeoutExpired) as e:
            return None, f"did not finish ({type(e).__name__})"
        if p.returncode:
            return None, f"exited {p.returncode}: {p.stderr.strip()[-200:]!r}"
        return p.stdout, ""


def _runs_the_work(how: str, probe, where: Optional[str]) -> Optional[str]:
    """What of the work under test a derivation names — the place the work stands in, or a program the probe runs from
    it (`./x`) — or None. The empty place it runs in hides nothing a path reaches (critic over the first form: an
    absolute path to the engine under test passed the rule unchanged)."""
    text = how.replace("\\", "/")
    places = {str(Path(where).resolve()).replace("\\", "/"), str(where).replace("\\", "/")} if where else set()
    if hit := next((w for w in places if w and w in text), None):
        return f"the work's place `{hit}`"
    progs = set(re.findall(r"(?:^|[\s;&|(])\./([\w.+-]+)", probe.command or ""))
    return next((f"`{x}`, which the probe runs from the work" for x in progs
                 if re.search(rf"(?:^|[\s/;&|(]){re.escape(x)}\b", text)), None)


def underived_at_the_root(engine, task, new_spec: Spec, answer: dict, where: Optional[str] = None,
                          execution=None) -> Optional[str]:
    """Under AUTO an expectation the system re-pins on a root criterion is a claim about the world made for the user, and
    it is grounded by contact with something other than the delivery it will judge — else the work under test answers
    its own check, verifier = executor in substance (§10.3, d6 §4.1). So each re-pinned probe, and each probe of a criterion the answer adds, names `derived_by`, a
    command that computes the expected output without the delivery; the system runs it where only the pinned inputs
    stand and the output must be the new `expect`. Below the root an ancestor's check still demands what a wrong re-pin
    let through; above the root nothing does. Measured: the executor disputed `50000.0 * 1.1 > 55000` as false, the
    system — having run only the engine under test — accepted and re-pinned the root's check to the engine's output, and
    the root passed (GB_sql_database_tn74a0108, 2026-10-20); of 116 re-pins in the archive two were at a root, that one
    and a true repair (`CASE WHEN a=b` with a = b = 2 is `eq`).

    What it does NOT close, named: an issuer that writes the value down instead of computing it (`print('…')`) passes —
    the rule puts a second, independent statement of the value on the log and catches the one who computes it wrongly
    believed (python gives `50000.0 * 1.1 > 55000` as True), not one who asserts it — in a live replay of that dispute
    on the same model, false re-pins landing went 5 of 5 → 2 of 5, one by a written-down value, one by a narrower
    command, which the replaced probe's own derivation now refuses; and a re-pin that changes only a pinned input file
    (an expected-output `.out` behind `diff`) changes no (command, expect) pair and is not seen."""
    if not is_auto_root(engine.graph, task):
        return None
    old = {c.name: c for c in task.spec.criteria}
    given = {(str(d.get("criterion", "")), " ".join(str(d.get("probe", "")).split())): str(d.get("derived_by", ""))
             for d in answer.get("derivations") or () if isinstance(d, dict)}
    pair = lambda p: (p.command, p.expect)
    wrong = []

    def derive(c, p, owed: str) -> Optional[str]:
        """The probe's expected output computed without the work, or None with why said into `wrong`."""
        how = given.get((c.name, " ".join(p.command.split())), "")
        if not how.strip():
            wrong.append(f"«{c.name}» `{p.command[:120]}`: no `derived_by` for this probe — {owed} (named by its "
                         f"command exactly as pinned)")
        elif used := _runs_the_work(how, p, where):
            wrong.append(f"«{c.name}»: its derivation `{how[:120]}` runs the work under test — {used}")
        else:
            out, why = _derived(how, c, p, execution)
            if out is not None:
                return out
            wrong.append(f"«{c.name}» `{p.command[:80]}`: its derivation `{how[:120]}` {why}")
        return None

    # …A CRITERION THE ANSWER ADDS TOO: it is a claim about the world made for the user no less than a re-pin, and
    # skipping new names let the replay's landing answer add a `\UHHHHHHHH` pin beside the root's `\uHHHH` prose,
    # unchecked (PLAN_CONSISTENT_BEFORE_GO r3, 2026-11-16)
    for c in new_spec.criteria:
        now, was = {pair(p) for p in c.check or ()}, (old[c.name].check or ()) if c.name in old else ()
        for p in (p for p in c.check or () if pair(p) not in {pair(q) for q in was}):
            if (out := derive(c, p, "the expectation it pins")) is not None and not shows(out, p.expect):
                wrong.append(f"«{c.name}» `{p.command[:80]}`: its derivation prints {out.strip()[:200]!r}, not the "
                             f"expectation {p.expect[:200]!r}")
        # …AND THE PROBE IT REPLACES WAS WRONG: a new command can be honestly derived and still check a narrower thing
        # (critic's live replay: `WHERE salary > 55000.0` after a raise, Bob only, the Alice row out of the check)
        for q in (q for q in was if pair(q) not in now):
            if (out := derive(c, q, "the user's probe it replaces must be shown wrong")) is not None \
                    and shows(out, q.expect):
                wrong.append(f"«{c.name}» `{q.command[:80]}`: the probe it replaces was right — its derivation "
                             f"prints its expectation {q.expect[:200]!r}")
    return ("under AUTO an expectation re-pinned or added on the user's goal is shown by a derivation that does not run the "
            "delivery (`derivations`: the criterion, the probe's command, and `derived_by` — e.g. python3 with its "
            "standard library, sqlite3 included); the system runs it with only the pinned inputs and finds: "
            + "; ".join(wrong)) if wrong else None


def off_the_goal(engine, task, new_spec: Spec, answer: dict, where: Optional[str] = None, verbs=None) -> Optional[str]:
    """Why a contract the system installs on this node leaves the user's goal at an AUTO root — narrowed
    (`narrowing_at_the_root`) or pinned with an expectation no derivation shows (`underived_at_the_root`) — or None. One
    rule for every door that installs it: held at the dispute's answer alone, `add_criterion` and the escalation's
    `reassign` landed the same wrong pin unchecked (critic's reproduction, 2026-11-16)."""
    return (narrowing_at_the_root(engine, task, new_spec)
            or underived_at_the_root(engine, task, new_spec, answer, where, _execution(engine, verbs)))


def _turned_off_the_goal(engine, task, new_spec, actor, answer, verbs, where) -> Optional[str]:
    """`off_the_goal` for a move installing the node's own contract, its refusal on the log as a refused re-ASSIGN — where
    the issuer's next turn reads it (`refused_on_this_version`), as the dispute's refusals are (`_turned_back`)."""
    if bad := off_the_goal(engine, task, new_spec, answer, where, verbs):
        engine.record_refused_move(task.id, Signal.ASSIGN, actor, bad)
    return bad


def seam_keeping_executor(engine, task, another: bool) -> Optional[AgentId]:
    """An executor for a re-issued node that keeps every seam around it: from this project's pool,
    not its parent's Del, not any child's Del — else a node would verify itself or its own work."""
    parent = engine.graph.get_task(task.parent_id) if task.parent_id else None
    ok = engine.seam_keepers(parent.assignee if parent else None, task.id)
    if not another and str(task.assignee) in {str(a) for a in ok}:
        return task.assignee
    return ([a for a in ok if str(a) != str(task.assignee)] or ok or [None])[0]


# === The moves — each one the canon gives the mover in that state, checked before it is made ===

def _signalled(engine, task_id, sig, actor, **kw) -> tuple[bool, str]:
    why: list = []
    return signal_ok(engine, task_id, sig, actor, why, **kw), "; ".join(why)


def _offer_lapsed(engine, task) -> bool:
    """Did this node of the user's plan reach the issuer's decision by its offer lapsing (§12.4: OFFERED's timeout)? A
    lapse is the executor's abstention, recorded without its reason (§12.9): it shows nothing infeasible — an executor
    that finds the contract so says it by CHALLENGE — so the honest move is a new contract, and `cancel`, the run's stop
    on this plan, would stop it on a clock: parts' offers lapsed while their producer worked and one was cancelled
    (GB_c_compiler_tnj930660). Read off how the node ENTERED its decision, not off its producers now: one that passed
    while the issuer's turn waited turned the same lapse into "cannot be carried" (critic over 2d7a0e5)."""
    return engine.users_plan() and _lapsed_from(engine, task) == State.OFFERED


def _validation_lapsed(engine, task) -> bool:
    """Did this node reach the issuer's decision with its delivery unvalidated — VALIDATING's bound passed with no verdict
    (§12.4)? That says nothing against the work, and the delivery stands on the log: the move it is owed is the contract
    re-presented, the same result re-delivered and validated (§16.14), and `cancel` would discard work no verdict
    indicts (§12.16 (ii)) — a machine issuer cancelled such a delivery "contract fully satisfied" and re-issued it
    (tn7a14284, 2026-10-20)."""
    return _lapsed_from(engine, task) == State.VALIDATING


def _lapsed_from(engine, task) -> Optional[State]:
    """The state whose bound handed this ESCALATED node to its issuer — read off how it ENTERED its decision — or None."""
    if task is None or task.state != State.ESCALATED:
        return None
    entered = next((e for e in reversed(engine.audit_log(task.id)) if not e.rejected and e.new_state == State.ESCALATED),
                   None)
    return entered.old_state if entered and entered.signal == Signal.TIMEOUT else None


def _cancel(engine, task, actor, answer, why, verbs):
    """CANCEL — or, on a node of the plan the user handed in, the run's STOP with the issuer's reason: that plan is the
    user's to cut (the author, 2026-10-25: «остановка с сигналом … что внутри системы считают что план нерабочий»). A
    part cancelled while its offer lapsed behind a working producer read as a refuted plan (GB_c_compiler_tnj930660);
    without the move at all, a part that really cannot be carried churned to its deadlines (critic over f96e6f8)."""
    if engine.users_plan() and users_criteria(engine.graph, task):
        reason = (f"the system's issuer finds {task.id} cannot be carried as the plan the user gave writes it: "
                  f"{why or 'no reason given'} — only the user re-plans it: hand a corrected plan as a new goal "
                  f"(`refine_plan` on its file, then `auto_decompose(plan=path)` on a new project; or `auto_decompose` with `spec`), or `set_mode` (with `user_said`) to hold the plan "
                  f"yourself; `start_project` alone asks its issuer again")
        # …ALWAYS asked: `pause` keeps a person's stop and takes over one the system lifts by itself (the account's
        # limit, a place down), which would otherwise lift with this verdict lost (critic over bc5fca4)
        engine.pause("system", reason)
        engine.emit_info("issuer", f"{task.id}: {reason}")
        return True, reason
    return _signalled(engine, task.id, Signal.CANCEL, actor, reason=why or "the issuer closes it")


def _resolve_block(engine, task, actor, answer, why, verbs):
    return _signalled(engine, task.id, Signal.RESOLVE_BLOCK, actor, external=True,
                      action=str(answer.get("action") or why))


def _cause(answer, *types: RevisionReason, default=RevisionReason.OTHER) -> RevisionReason:
    """The cause the issuer gives for a change (§15.6 dial 3) — read only where it types this act: a criteria change
    (q_T: spec_defect, or the sanctioned scope_expansion), a change of executor (q_Del: capability_mismatch). Typed
    OTHER by the machine, every cause the issuer meant went unmeasured (critic r7, B3)."""
    cause = RevisionReason.__members__.get(str(answer.get("cause") or "").upper())
    return cause if cause in types else default


def _reassign(engine, task, actor, answer, why, verbs, where=None):
    if (bad := _carry(task, answer.get("criteria"), _split_of(engine, task))[1]):
        return False, bad
    spec = spec_with(task, answer["criteria"], additions_only=users_criteria(engine.graph, task),
                     split=_split_of(engine, task)) if answer.get("criteria") else task.spec
    if bad := _turned_off_the_goal(engine, task, spec, actor, answer, verbs, where):
        return False, bad
    to = seam_keeping_executor(engine, task, bool(answer.get("another_executor")))
    # …never below the node's own bound: an answer that asks no budget change changes none (critic)
    budget = min(max(1, int(answer.get("max_iterations") or task.max_iterations)),
                 max(REWORK_EXTENSION * project_max_iterations(engine.graph), task.max_iterations))
    # …and no count of re-issues (§12.15 Φ3): each version ends by its deadline and the bounds, spend by the account's limit
    if to is None:
        return False, "no executor of this project keeps the seams around this node"
    want = project_now(engine.graph) + timedelta(hours=min(MAX_EXTEND_HOURS, max(1.0, float(answer.get("extend_hours") or 24))))
    # INSIDE the parent's deadline, BEFORE its consumers' and AFTER its producers' along Dep (§4.5 item 6, §2.7) — the
    # one writer of ordered deadlines (`Schedule`): written on the parent's, two Dep-linked siblings re-issued got one
    # equal deadline (critic r7, B2); re-issued before its producer, a consumer lapsed again. No ordered one ahead — the
    # parent already due — the issuer types the one it wants (§2.5), the crossing flagged (§12.10).
    parent = engine.graph.get_task(task.parent_id) if task.parent_id else None
    reads = producers_of(spec, engine.graph.declared_edges(task.id))
    deadline = Schedule(engine.graph, parent, {str(task.id): (None, reads, None)}, want=want).defaults()[str(task.id)] or want
    # TYPED (§15.6 dial 3 — the cause is the issuer's to give): a re-issue out of ESCALATED is routine, and a change
    # of executor to keep the seams is no capability mismatch; untyped, every machine re-issue counted against q_Del
    # (sync audit, C-F3). A criteria change here answers no spec defect the machine could name.
    engine.revise(task.id, spec, AgentId(actor), deadline=deadline, max_iterations=budget,
                  reason=_cause(answer, RevisionReason.SPEC_DEFECT, RevisionReason.SCOPE_EXPANSION)
                  if spec.criteria != task.spec.criteria else RevisionReason.OTHER)
    if str(to) != str(task.assignee):
        engine.reassign(task.id, to, reason=_cause(answer, RevisionReason.CAPABILITY_MISMATCH))
    return True, ""


def _revise_child(engine, task, actor, answer, why, verbs):
    child, bad = _named_child(engine, task, answer)
    if bad:
        return False, bad
    if _settled(engine, child):
        return False, (f"{child.id} is {child.state.name} and the plan rests on it (§12.14) — it is not revised; "
                       f"`add_child` a child that carries what it left, mapped to the criteria that failed")
    # …AND WHICH OF THIS NODE'S CRITERIA IT CARRIES. A criterion added to the node is a coverage hole until a
    # child is mapped to it; with no move to map an existing child, the issuer restated the child that already
    # carried it, was refused, and looped (measured live, AUTO json_parser, after an add_criterion).
    mine = {c.name for c in task.spec.criteria}
    held = {m.criterion_name for m in task.criterion_mappings if str(m.child_id) == str(child.id)}
    covers = [c for c in answer.get("covers") or [] if c in mine and c not in held]
    if not (answer.get("criteria") or covers):
        return False, ("a revised child names its criteria as they will stand (`criteria`), or which of this "
                       "node's criteria it carries (`covers`)")
    crits, why = _carry(task, answer.get("criteria"), _split_of(engine, task))
    if why:
        return False, why
    spec = spec_with(child, crits) if crits else child.spec
    if {c.name: c for c in spec.criteria} == {c.name: c for c in child.spec.criteria} and not covers:
        return False, (f"{child.id} restated unchanged — a fix changes what the child carries (its criteria, or "
                       f"`covers`: which of this node's criteria it carries); a child's dependency criteria are "
                       f"kept whether or not you name them, so to take a dependency out of the split, "
                       f"`drop_child` the child and add the one that replaces it")
    if lost := [c.name for c in child.spec.criteria if c.name not in {k.name for k in spec.criteria}]:
        return False, (f"a revision adds what is needed; it does not remove {', '.join(lost)} from "
                       f"{child.id} — to reshape the split, `drop_child` it and add the child that replaces it")
    # THE CRITERIA IT CARRIES ARE THE SPLIT'S (§2.4): mapped by the split's re-admission, BEFORE the child's contract is
    # touched — revised first, a refused remap left it re-offered and unmapped (critic r16). Two acts, so every refusal
    # of both is read before either writes: a revision refused after the remap left the move half done (critic r17)
    if spec is not child.spec and (no := engine.refusal_for(child.id, Signal.ASSIGN, AgentId(actor), spec=spec)):
        return False, f"{child.id}'s revision would be refused, so nothing of this move was made: {no.why}"
    if covers and not (got := _readmit(engine, task, {"map": {str(child.id): covers}}))[0]:
        return got
    if spec is not child.spec:
        engine.revise(child.id, spec, AgentId(actor),
                      reason=_cause(answer, RevisionReason.SPEC_DEFECT, RevisionReason.SCOPE_EXPANSION))
    return True, ""


def _drop_child(engine, task, actor, answer, why, verbs):
    """The split's own re-decomposition (§11.5: an issued child a re-admission drops is cancelled, a settled one
    stays). Without it the machine issuer could only add: a split whose children were mutually dependent —
    measured live, a tokenizer and a container parser each needing the other, the Dep cycle freezing every
    sibling — had no answer but restating a child it may not narrow. What the dropped child carried is then
    an honest coverage hole the gate holds until a child (`add_child`) carries it."""
    child, bad = _named_child(engine, task, answer)
    if bad:
        return False, bad
    if child.state in (State.DONE, State.ABANDONED, State.CANCELLING):
        return False, f"{child.id} is settled or closing ({child.state.name}) — a settled child stays in the split"
    # …AND A RESHAPE IS NOT A DISSOLUTION: dropping the last active child turns the node into a leaf its own
    # executor then works whole — the split the protocol validates, gone with no record that it went (critic
    # round 19). The replacement comes first; that is the issuer's own move.
    # …counted over the children that STAY: one still closing is active until it settles (§12.6), and leaving
    if [str(k.id) for k in engine.graph.get_active_children(task.id) if k.state != State.CANCELLING] == [str(child.id)]:
        return False, (f"{child.id} is the split's last active child — `add_child` its replacement first, "
                       f"then drop it")
    return _signalled(engine, child.id, Signal.CANCEL, actor, reason=why or f"{task.id}'s split drops it")


def _base_id(task, c: dict) -> str:
    """The id a new child named as `c` is after, before a fresh one is taken (`_child_id`)."""
    return f"{task.id}.{re.sub(r'[^a-z0-9_]+', '_', str(c.get('name') or 'repair').lower())[:40]}"


def _child_id(engine, task, c: dict, leaving: frozenset, taken: set) -> str:
    """The id of a child this act creates under the node: its name's, or a fresh one beside it."""
    cid = _base_id(task, c)
    # A DROPPED CHILD KEEPS ITS ID (Inv-7: the log carries it), so the child replacing it under the same name
    # takes a fresh one — measured live: the replacement of a dropped `container_parser` was refused as "exists";
    # a drop still closing counts too, its CONFIRM_CANCEL may be in flight (critic round 19)
    base, n = cid, 2
    # …and so does a SETTLED one, which no move changes (critic r6: "exists — revise it" and "settled — add one" pointed
    # at each other on a reused name)
    while (_old := engine.graph.get_task(TaskId(cid))) is not None and (_old.state in (State.ABANDONED, State.CANCELLING)
                                                                  or _settled(engine, _old)
                                                                  or str(_old.id) not in _active(engine, task)
                                                                  # …and one THIS act drops: computed before the
                                                                  # drop applies, "root.libc exists" refused the one
                                                                  # reshape that replaced it (GB_c_compiler_tmp5cb096)
                                                                  or str(_old.id) in leaving) or cid in taken:
        cid, n = f"{base}_{n}", n + 1
    return cid


def _in_act(engine, task, ref, ids: dict, standing: set) -> str:
    """The child of `task`'s split a re-admission names: a `standing` one, or one the same act creates (`ids`) — by its
    name as given or as its id would read — else as `_child_ref` reads it.
    `D1` for `root.D1` was "not an active child" and closed a root (G9, 2026-10-15); `root.D3_Parser` for
    `root.d3_parser` refused a reshape on the case of one letter (GB_sql_database_tmx1h7240); and a reshape adding
    `root.build_and_dispatcher` and mapping it in the same act was refused four times running, `map` reading only the
    children already standing, the plan held at the gate for an hour (AUTO haiku coreutils, GB_coreutils_tn73sy660)."""
    r = str(ref)
    return r if r in standing else (ids.get(r) or ids.get(_base_id(task, {"name": r.removeprefix(f"{task.id}.")}))
                                    or _child_ref(engine, task, r))


def _new_child(engine, task, c: dict, cid: str, ids: dict, leaving: frozenset) -> tuple[dict | None, str]:
    """One child `cid` for a re-admission of `task`'s split, as `decompose` takes it: its criteria, its declared Dep
    edges onto the siblings it `reads`, the node's criteria it `covers`. (None, why) refused. `reads` names a standing child,
    or what `ids` resolves — a child the same act creates, by its name, and one it drops, to what replaces it."""
    mine = [k.name for k in task.spec.criteria]
    covers = [x for x in (c.get("covers") or []) if x in mine]
    # …each refusal names its own correction: one sentence for both halves sent a model round 44 times on a child that
    # carried its criteria under another key (GB_c_compiler_tnl51c552)
    if not c.get("criteria"):
        return None, "a new child carries criteria: none were given in this child's `criteria`"
    if not covers:
        stray = [x for x in (c.get("covers") or []) if x not in mine]
        return None, (f"a new child names which of {task.id}'s criteria it covers (`covers`), from: {', '.join(mine)}"
                      + (f" — {', '.join(map(str, stray))} is not one of them" if stray else ""))
    if engine.graph.get_task(TaskId(cid)) is not None:
        return None, (f"{cid} exists — to change it, `revise_child` it (which may not remove what it "
                      f"carries); to reshape the split, `drop_child` it and add the child that replaces it")
    # …AND THE SIBLINGS IT READS, as Dep (Ch. 2: a criterion that references another node's result IS a Dep
    # edge). Without this a machine-added child that checks its siblings' work could only BLOCK on them —
    # measured live: two such guards BLOCKed at once, their provisional edges closed a cycle, the plan froze.
    # …ONE THE SAME ACT ADDS INCLUDED: a reshape adding a producer and its reader had no id to name the producer by,
    # and the reader was refused for reading a child that was not there yet
    standing = _active(engine, task) - leaving
    reads = [_in_act(engine, task, r, ids, standing) for r in c.get("reads") or []]
    if bad := [r for r in reads if r not in standing and r not in set(ids.values())]:
        return None, f"`reads` names {', '.join(bad)} — not an active child of {task.id}, nor one this act adds"
    crits, why = _carry(task, c["criteria"], _split_of(engine, task))
    if why:
        return None, why
    return {"task_id": cid, "covers": covers,
            "deps": list(c.get("deps") or ()) + [{"from": r, "glue": f"reads {r}'s result"} for r in reads],
            "spec": {
        "name": c.get("name", ""), "description": c.get("description", ""),
        "criteria": [with_named_files(_with_corpora(x, _corpora(engine, task)), _files_of(engine, task))
                     for x in crits],
        **({"accepted_risks": c["accepted_risks"]} if c.get("accepted_risks") else {})},
        **{k: c[k] for k in ("deadline", "max_iterations") if c.get(k)}}, ""


def _split_of(engine, task) -> list:
    """The children of the node's split — whose probes an answer may `carry` by id, as the node's own."""
    return list(engine.graph.get_children(task.id))


def _observation(p) -> tuple:
    """What running a pinned probe observes, as a check reads its output — one key for every copy of one probe."""
    cmd, _, inputs = same_probe(p)
    return cmd, as_read(p.expect), inputs, bool(p.exact)   # who decides the output is part of the probe carried


def _carry(task, criteria: list, split=()) -> tuple[list, str]:
    """The answer's criteria with each probe that names one of `task`'s own pinned probes by id (`carry`) replaced by
    that probe EXACTLY — command, expect, its inputs with their content — copied by the system. The plan gate asks a
    child to carry the parent's very probe (its inputs judged by content), and the issuer, shown inputs by name and
    count only, could not write it: a same-named file another child already pinned made the content ambiguous
    (own-plan row 3: 5–8 of 18 root criteria open on it). ([], why) when an id names no probe of `task`.
    …or of a child of its split (`split`): the issuer wrote those too, and a reshape moving `root.head`'s probes onto
    the child replacing it by their ids was refused as "not a probe of root" (GB_coreutils_tnqh4a016)."""
    pinned = {probe_id(c.name, p): p for k in (task, *split) for c in k.spec.criteria for p in (c.check or ())}
    own = {k: p.to_dict() for k, p in pinned.items()}

    def found(ref: str) -> dict | None:
        """The probe `ref` names: by its id, or — the id's identity being its command's hash — by that hash alone where
        every probe carrying it is one observation. A haiku issuer wrote the hash bare (`#6e78ee3b`) or under a sibling
        criterion's name the same command is pinned under (its prose and line breaks apart), and was refused 7 times in
        62 min, the plan held at admission (GB_coreutils_tnq9d1176)."""
        if ref in own:
            return own[ref]
        h = re.search(r"([0-9a-f]{8})\s*$", ref)
        hits = [k for k in pinned if h and k.endswith("#" + h.group(1))]
        return own[hits[0]] if hits and len({_observation(pinned[k]) for k in hits}) == 1 else None

    out = []
    for c in criteria or ():
        if not isinstance(c, dict):
            out.append(c)
            continue
        carried = [str(p["carry"]) for p in c.get("check") or () if isinstance(p, dict) and p.get("carry")]
        if bad := [r for r in carried if found(r) is None]:
            return [], (f"`carry` names {', '.join(bad)} — not one pinned probe of {task.id} or of its split; they are: "
                        + ", ".join(sorted(own)))
        out.append({**c, "check": [dict(found(str(p["carry"]))) if isinstance(p, dict) and p.get("carry") else p
                                   for p in c.get("check") or ()]})
    return out, ""


def _corpora(engine, task) -> dict:
    """{(criterion, command): its files} of every probe this node or a child of its split pinned over a corpus — the
    issuer side's own; a child carrying one of the node's own criteria re-writes its probe (critic r5) — and
    {(None, command): …} where every such pin of the command reads one corpus."""
    pins = [(c.name, " ".join(p.command.split()), p.to_dict()["inputs"])
            for k in [task, *engine.graph.get_children(task.id)] for c in k.spec.criteria for p in (c.check or ())
            if p.inputs]
    by_cmd, by_file = {}, {}
    for name, cmd, files in pins:
        by_cmd.setdefault(cmd, []).append(files)
        for path, body in files.items():
            by_file.setdefault((None, None, path), set()).add(body)
            by_file.setdefault((name, None, path), set()).add(body)
    # …and {(None, None, file): body} where the split pins that file with one content: a new probe naming a sibling's
    # file under `{inputs}` without repeating its pin was 48 of 50 refused probes in one row (GB_c_compiler_tnl51c552)
    return {**{k: next(iter(b)) for k, b in by_file.items() if len(b) == 1},
            **{(None, cmd): fs[0] for cmd, fs in by_cmd.items() if all(f == fs[0] for f in fs)},
            **{(name, cmd): files for name, cmd, files in pins}}


def _files_of(engine, task) -> dict:
    """{(criterion, file): body} every probe of this node and of a child of its split pins with content."""
    return pinned_files(c for k in [task, *engine.graph.get_children(task.id)] for c in k.spec.criteria)


def _with_corpora(criterion, corpora: dict):
    """The criterion with each probe that reads `{inputs}` and pins none carrying the corpus its split pinned under that
    criterion and command — or under that command alone, where it reads one corpus throughout. A repair re-writes a
    probe; the files it reads it cannot re-write, and the child was refused for a probe "that reads {inputs} and pins
    nothing there" — six repairs in a row, the root closed by count (AUTO haiku coreutils, 2026-10-12, two rows)."""
    if not isinstance(criterion, dict) or not criterion.get("check"):
        return criterion

    def carried(p) -> dict:
        """The probe with the corpus its split pinned under this criterion and command, where it reads one and has none."""
        cmd = " ".join(str(p.get("command", "")).split()) if isinstance(p, dict) else ""
        files = corpora.get((criterion.get("name"), cmd), corpora.get((None, cmd)))
        if not files and INPUTS_TOKEN in cmd:
            # every file the command names under `{inputs}`, each pinned in the split with one content — under this
            # criterion first, else under any; and only where `{inputs}` is never read as a directory (a glob, `ls`), or
            # the probe would decide over a subset the system picked (critic)
            refs = re.findall(re.escape(INPUTS_TOKEN) + r"/([\w.-]+(?:/[\w.-]+)*)(?![\w*?$/])", cmd)
            got = {n: corpora.get((criterion.get("name"), None, n), corpora.get((None, None, n))) for n in refs}
            files = got if refs and len(refs) == cmd.count(INPUTS_TOKEN) and None not in got.values() else None
        return {**p, "inputs": files} if INPUTS_TOKEN in cmd and not p.get("inputs") and files else p
    return {**criterion, "check": [carried(p) for p in criterion["check"]]}


def _active(engine, task) -> set:
    return {str(k.id) for k in engine.graph.get_active_children(task.id)}


def _child_ref(engine, task, ref) -> str:
    """The id of `task`'s child an answer names — as stored, or as the issuer named it when it added it (the id is the
    name under the parent, `_base_id`). Named back without the prefix, the issuer's own new child was "not a child of
    root" twice and the root closed by count (AUTO haiku sql_database, GB_sql_database_tmwsep280, 2026-10-15)."""
    # …a LIVE one first: dropped and re-added under one name, the child is `<name>_2`, and the bare name found the dead
    # one (a critic, 2026-10-15)
    ref = str(ref or "")
    if (k := engine.graph.get_task(TaskId(ref))) is not None and str(k.parent_id) == str(task.id):
        return ref                                   # an id as stored names that child, whatever its state
    forms = (f"{task.id}.{ref}", _base_id(task, {"name": ref}))
    live = [str(k.id) for k in engine.graph.get_active_children(task.id) if k.state != State.CANCELLING]
    for cid in forms:
        if hits := [k for k in live if re.fullmatch(rf"{re.escape(cid)}(_\d+)?", k)]:
            return cid if cid in hits else max(hits, key=lambda k: (len(k), k))
    for cid in forms:
        if (k := engine.graph.get_task(TaskId(cid))) is not None and str(k.parent_id) == str(task.id):
            return cid
    return ref


def _named_child(engine, task, answer) -> tuple:
    """(the child of `task` the answer's `child_id` names, '') — or (None, why it names none)."""
    child = engine.graph.get_task(TaskId(_child_ref(engine, task, answer.get("child_id"))))
    if child is None or str(child.parent_id) != str(task.id):
        return None, f"`{answer.get('child_id')}` is not a child of {task.id}"
    return child, ""


def _add_child(engine, task, actor, answer, why, verbs):
    return _readmit(engine, task, {"children": [answer.get("child") or {}]})


def _reshape(engine, task, actor, answer, why, verbs):
    """THE SPLIT CHANGED IN ONE ACT (§11.5: the split, its children and its register change only by a re-admission,
    the battery over the split as it will then stand). The single moves are each a partial re-admission: with two
    holes at once — a revision adding criterion `h` while the register names `h` — `add_child` was refused for the
    register hole it left and `drop_risk` for the coverage hole, though one act lifting both was the decomposer's
    own (sync map, C9-MOVES). Here: `children` added (each as `add_child` takes one), `drop` children leaving the
    split, `items` register entries that name this node's criteria taken out — admitted whole or not at all."""
    decomposer = str(task.assignee)
    if held_by_a_holder(engine, decomposer):
        return False, f"reshaping {task.id}'s split is its decomposer's move ({decomposer}), not the system's"
    return _readmit(engine, task, answer)


def _redecompose(engine, task, actor, answer, why, verbs):
    """ESCALATED refutes the forecast the node was issued with (§12.15 Φ3), and its issuer — the decomposer of the split
    it is a part of — may answer by re-making that split (§4.5: re-decomposition at the attributed level): one
    re-admission dropping it with the children that replace it, the battery over the split as it will stand. His own
    act on his own split; nobody is ordered to split another's node."""
    parent = engine.graph.get_task(task.parent_id) if task.parent_id else None
    if parent is None:
        return False, f"{task.id} is a root: no split stands above it — `reassign` or `cancel`"
    # ITS CONSUMERS NEED A PRODUCER NAMED: left on the dropped node they starve; which new child makes what they read
    # is the decomposer's judgement, so it is asked for, never guessed from the order of the children
    readers = [str(k.id) for k in engine.graph.get_active_children(parent.id) if k.id != task.id
               and k.state not in (State.DONE, State.ABANDONED, State.CANCELLING)
               and str(task.id) in map(str, producers_of(k.spec, engine.graph.declared_edges(k.id)))]
    named = {str(_child_ref(engine, parent, r)) for c in answer.get("children") or () for r in c.get("replaces") or ()}
    if readers and str(task.id) not in named:
        return False, (f"{', '.join(readers)} read {task.id}'s work: name in `replaces` the new child that makes "
                       f"what they read, so they are handed to it in the same act")
    return _reshape(engine, parent, actor, {**answer, "drop": [str(task.id), *(answer.get("drop") or ())]}, why, verbs)


def _readmit(engine, task, answer) -> tuple[bool, str]:
    """The one re-admission behind `reshape`, `add_child` and `drop_child`. A child it drops and replaces — the new
    child named as it was, or naming it in `replaces` — is handed to `decompose` as that child's `replaces`, the one
    mechanism both doors share: its consumers, work and findings go to the replacement there."""
    drop, named = [_child_ref(engine, task, d) for d in answer.get("drop") or []], answer.get("children") or []
    leaving, cids = frozenset(drop), []
    for c in named:
        cids.append(_child_id(engine, task, c, leaving, set(cids)))
    replaced = {str(d): cid for c, cid in zip(named, cids)
                for d in [*(_child_ref(engine, task, r) for r in c.get("replaces") or ()), _base_id(task, c)]
                if str(d) in leaving}
    ids = {**{str(c["name"]): cid for c, cid in zip(named, cids) if c.get("name")}, **{c: c for c in cids}, **replaced}
    kids = []
    for c, cid in zip(named, cids):
        kid, bad = _new_child(engine, task, c, cid, ids, leaving)
        if bad:
            return False, bad
        kids.append({**kid, "replaces": [d for d, x in replaced.items() if x == cid], "onto": c.get("onto") or {}})
    register, asked = register_of(task), [str(i) for i in (answer.get("items") or [])]
    if bad := [i for i in asked if i not in set(risks_naming_own_criteria(task))]:
        return False, f"`items` names {', '.join(bad)} — only register entries naming this node's criteria go"
    kept = [n for n in register.items if n.item not in set(asked)]
    mine, live = {c.name for c in task.spec.criteria}, _active(engine, task) - leaving
    remap = {_in_act(engine, task, k, ids, live): [c for c in v or () if c in mine]
             for k, v in (answer.get("map") or {}).items()}
    if bad := [k for k in remap if k not in live | set(cids)]:
        return False, f"`map` names {', '.join(bad)} — not a child standing in {task.id}'s split, nor one this act adds"
    if not (kids or drop or asked or any(remap.values())):
        return False, ("a reshape adds `children`, `drop`s children, takes register `items` out or `map`s standing "
                       "children to this node's criteria — it named none")
    # …AND IS NOT A DISSOLUTION, as `drop_child` is not (critic round 19): dropping every child that stays, with none
    # in their place, turns the node into a leaf with its split gone and its register vacuous (critic r13)
    if drop and not kids and not {str(k.id) for k in engine.graph.get_active_children(task.id)
                                  if k.state != State.CANCELLING} - set(drop):
        return False, (f"this drops every child of {task.id}'s split and adds none — name in `children` the ones "
                       f"that replace them, in the same reshape")
    bad = _decompose_errors(engine, task, kids, drops=drop,
                            mappings=[{"criterion_name": c, "child_id": k} for k, cs in remap.items() for c in cs],
                            **({"accepted_risks": [n.to_dict() for n in kept],
                                "risk_components": list(register.components)} if asked else {}))
    # …said in this issuer's own moves: the refusal names the tool door's verbs, and the whole act here is one reshape
    return (not bad, "; ".join(bad) + (" — as this node's issuer: everything the split needs in ONE `reshape` "
                                       "(`children`, `drop`, `items`, `map`)" if bad else ""))


def _cycle_in_hand(engine, task) -> Optional[dict]:
    """A refuted order (§15.5) is re-decomposed by its split's decomposer, and the system makes no cut of its own: its
    merge of the cycle into one child folded a whole compiler into one node no executor built (GL_cc_light1). Only
    the wait is the system's. A MEMBER'S DELIVERY AWAITING ITS VERDICT IS WORK IN HAND (§12.16 (ii)): dropped now, it
    would be voided unread; the question waits for the verdict — uncounted, backed off — and is asked after it."""
    if held_by_a_holder(engine, str(task.assignee)) or not engine.dep_order_refuted(task.id):
        return None
    if busy := sorted(m for g in engine.dep_order_cycle_children(task.id) for m in g
                      if engine.graph.get_state(TaskId(m)) == State.VALIDATING):
        return {"status": "waiting", "why": f"{', '.join(busy)} delivered and await a verdict; the re-cut follows it"}
    return None


def _promote(engine, task, actor, answer, why, verbs):
    """§11.3: a blocker that is a producible in-scope artifact is promoted into a node — mandatory, and owed by the
    blocked task's issuer, "by changing the split he holds": a producer beside the blocked node, carrying the same
    criteria of the parent, and the Dep that makes the blocked node wait for it (its re-author re-offers it). The
    machine issuer could only resolve, re-issue or close (sync audit, A-F8). At a root the canon fixes no owner — a
    second goal or the root's own split, a freedom (§15.2) — so it is not this move's."""
    parent = engine.graph.get_task(task.parent_id) if task.parent_id else None
    if parent is None:
        return False, (f"{task.id} is a root: where its prerequisite goes — a second goal, or a child of its own "
                       f"split — the canon leaves to the goal's issuer (§15.2); resolve_block, reassign or cancel")
    covers = [m.criterion_name for m in parent.criterion_mappings if str(m.child_id) == str(task.id)]
    before = {str(k.id) for k in engine.graph.get_active_children(parent.id)}
    # DUE BEFORE THE NODE IT UNBLOCKS (§2.7): the Dep is written after the producer exists, so the one writer of ordered
    # deadlines is told of its consumer now — born with the parent's default, the producer came due after it (critic r2, F3)
    blocked = task.deadline if task.deadline and task.deadline > project_now(engine.graph) else None
    made_by = Schedule(engine.graph, parent, {"(promoted)": (None, (), None),
                                              str(task.id): (blocked, ("(promoted)",), None)}).defaults()["(promoted)"]
    if made_by is None and parent.deadline and parent.deadline <= project_now(engine.graph):
        made_by = project_now(engine.graph) + timedelta(hours=24)   # past the parent's deadline the issuer types one (§12.16)
    # …its producer read under either name the move gives it: the schema's "promote: {name, description, criteria}" sat
    # in `child`'s description, the model wrote it under `promote`, and 44 refusals said the child carried no criteria
    # while it carried two (GB_c_compiler_tnl51c552, 2026-10-28)
    made_of = {**(answer["promote"] if isinstance(answer.get("promote"), dict) else {}),
               **{k: v for k, v in (answer.get("child") or {}).items() if v}}
    if not [c for c in covers if c in {k.name for k in parent.spec.criteria}]:
        # …and a producer of nothing the split states is no promotion: whatever `covers` the move sends is not read, so
        # "name the criteria it covers" could not be lifted (critic, §12.16 (ii))
        return False, (f"{task.id} carries none of {parent.id}'s criteria (no mapping names it), so a producer beside "
                       f"it would carry nothing of the split: resolve_block, reassign or cancel")
    short = str(task.id).removeprefix(f"{parent.id}.")
    if ring := [f for f in seam_findings(engine, parent.id) if f.startswith(f"{short}'s probes run the code of ")]:
        # …WHAT IT WAITS FOR IS A SIBLING'S CODE ITS OWN CHECKS RUN: a producer promoted beside it makes again what that
        # sibling writes and orders nothing — a tester's regex run went promote → BLOCK → cancel around the parser's
        # pins importing the api part's package, which waited on the parser (2026-11-13)
        return False, (f"{ring[0]}. Promoting a producer would make again what that part writes and break no order — "
                       f"answer with that remedy (`reassign` with {short}'s checks re-pinned over its own code, or the "
                       f"seam), not `promote`")
    ok, bad = _add_child(engine, parent, actor, {"child": {**made_of, "covers": covers, "reads": [],
                                                           **({"deadline": made_by} if made_by else {})}},   # a datetime on the project's clock, not a typed date
                         why, verbs)
    if not ok:
        # …and where the producer already stands in the split — two parts that need each other — `promote` is not the
        # move, and a refusal naming only the missing criteria sent the issuer back to it twice (GB_c_compiler_tnqqhf184)
        return False, bad + ("" if made_of.get("criteria") else
                             f"; if what {task.id} waits for is a sibling already in {parent.id}'s split, nothing new is "
                             f"promoted: two parts that need each other are reshaped by {parent.id}'s issuer (merged, or "
                             f"split along an interface each can build against) — answer the BLOCK with resolve_block, "
                             f"or report it")
    made = next(str(k.id) for k in engine.graph.get_active_children(parent.id) if str(k.id) not in before)
    engine.add_dependency(TaskId(made), task.id, glue=f"{task.id} was blocked on what {made} produces: {why}")
    # …and its BLOCK answered by a re-ASSIGN under the contract it has (§11.3): the edge is no part of the contract
    if engine.graph.get_state(task.id) == State.BLOCKED:      # …unless the edge's deadline already re-issued it
        engine.revise(task.id, engine.graph.get_task(task.id).spec, AgentId(engine.graph.issuer_of(task.id)))
    return True, ""


def _add_criterion(engine, task, actor, answer, why, verbs, where=None):
    """An obligation of the node's goal that no criterion decides (FM-1.f) is closed by ADDING the
    criterion — an act of the node's ISSUER on its contract, append-only: nothing standing changes."""
    issuer = str(engine.graph.issuer_of(task.id))
    if held_by_a_holder(engine, issuer):
        return False, (f"adding to {task.id}'s contract is its issuer's move ({issuer}), not the system's — a requirement "
                       f"its criteria do not write (FM-1.f, §9.4) is reported to him: `challenge`")
    if not answer.get("criteria"):
        return False, "name the criterion to add (`criteria`), with its pinned check"
    carried, bad = _carry(task, answer["criteria"], _split_of(engine, task))
    if bad:
        return False, bad
    new = [c for c in carried if c.get("name") not in {k.name for k in task.spec.criteria}]
    if not new:
        return False, "every criterion named already stands; adding means a NEW name"
    # …AND A NEW NAME OVER CHECKS ALREADY PINNED DECIDES NOTHING NEW: the obligation stayed undecided, the root grew from
    # 5 to 40 criteria, ten of them one obligation over the same probes, each a fresh coverage hole (GB_coreutils_tnq9d1176)
    standing = {_observation(p) for k in task.spec.criteria for p in (k.check or ())}
    if (checks := [p for c in new for p in _checks_of(c)]) and all(_observation(p) in standing for p in checks):
        return False, (f"every check of {', '.join(c.get('name', '') for c in new)} is already pinned on {task.id} — "
                       f"the same checks decide nothing new; what the open finding says is still admitted is what a "
                       f"NEW check must probe")
    spec = dataclasses.replace(task.spec, criteria=task.spec.criteria + tuple(
        Criteria(c.get("name", ""), c.get("description", ""), check=_checks_of(c)) for c in new))
    if bad := _turned_off_the_goal(engine, task, spec, actor, answer, verbs, where):
        return False, bad
    # an obligation of the goal no criterion decided is the contract's own defect, unless the issuer says the goal grew
    engine.revise(task.id, spec, AgentId(issuer), reason=_cause(
        answer, RevisionReason.SPEC_DEFECT, RevisionReason.SCOPE_EXPANSION, default=RevisionReason.SPEC_DEFECT))
    return True, ""


def _drop_risk(engine, task, actor, answer, why, verbs):
    """Take out of the split's ACCEPTED_RISKS an entry that names one of this node's own criteria — the one
    plan move that reaches the node's OWN register, and all it may do there.

    Such an entry is CHECK-4's refusal: a unilateral amendment of the contract, not a risk (§9.2). The plan
    moves act on children and on criteria, so the machine answered `revise_child` eighteen times over that
    hole on the root's register and ran out of answers (AUTO json_parser, 2026-09-27). Removing is all it
    may do: an added entry reads as licensed under-coverage to the plan checker, and at an AUTO root that
    would narrow the user's goal where `add_criterion` is the only way to change it; and the rest of the
    register, which the machine did not write, stays as it is. The register is never left empty
    (CHECK-4: every split ignores something)."""
    decomposer = str(task.assignee)      # the register is the split's, its decomposer's (§9.2), not the packet's
    if held_by_a_holder(engine, decomposer):
        return False, f"changing {task.id}'s register is its decomposer's move ({decomposer}), not the system's"
    flagged = set(risks_naming_own_criteria(task))
    asked = [str(i) for i in (answer.get("items") or [])]
    if not asked or not set(asked) <= flagged:
        return False, ("name in `items` the register entries CHECK-4 flags — those that name one of this node's "
                       "criteria: " + ("; ".join(f"«{i}»" for i in sorted(flagged)) or "none is flagged"))
    register = register_of(task)
    kept = [n for n in register.items if n.item not in set(asked)]
    if not kept:
        return False, ("dropping them would empty the register, and a split's register is never empty "
                       "(CHECK-4); what this node's split ignores is its decomposer's to say")
    try:
        engine.admit_register(task.id, Register(tuple(kept), register.components), AgentId(decomposer))
    except ValueError as e:
        return False, str(e)
    return True, ""


def _names_a_check(engine, task, why) -> bool:
    """Does `why` name, by its id, a pinned check of this node or of a child of its split?"""
    nodes = [task, *engine.graph.get_active_children(task.id)]
    return any(probe_id(c.name, p) in str(why or "") for n in nodes
               for c in n.spec.criteria for p in (c.check or ()))


def _dispute(engine, task, actor, answer, why, verbs):
    if is_auto_root(engine.graph, task) and loose_finding_key(str(answer.get("criterion") or "")
                                                                ).replace(" ", "").startswith("undecided:"):
        return False, ("under AUTO an obligation of the user's goal that no criterion decides is closed by "
                       "ADDING the criterion (`add_criterion`) — the user's goal is not argued away")
    key = str(answer.get("criterion") or "")
    # …and below the root it stands on a check: a reason naming none was read as a discharge, an unprobed requirement
    # closing on a model's word (critic over the residue's move)
    if loose_finding_key(key).replace(" ", "").startswith("undecided:") and not _names_a_check(engine, task, why):
        return False, ("an obligation no criterion decides is disputed by naming the pinned check that decides it, by "
                       "its id (shown after `decided by`); with none, `add_criterion` with one")
    # the engine resolves the key — one rule for every caller: exact, else one unambiguous near-match; a finding
    # already disputed is refused there and backs off like any answer that moved nothing
    try:
        engine.dispute_review_finding(task.id, key, why, AgentId(actor))
    except ValueError as e:
        return False, str(e)
    return True, ""


def _challenge(engine, task, actor, answer, why, verbs):
    """The decomposer's report of a defect sourced in the packet — the node's criteria jointly unsatisfiable, one no
    procedure decides — which only the packet's issuer can repair, since only he revises it: a CHALLENGE to him
    (§11.5, §9.7, §12.10). Made as the node's executor, the decomposer; a split move cannot carry it."""
    fields = [str(f) for f in answer.get("items") or () if str(f).strip()]
    if not why:
        return False, "a challenge says what in the contract is defective and why (§11.2: it names the fields)"
    return _signalled(engine, task.id, Signal.CHALLENGE, actor,
                      reason=(f"[{', '.join(fields)}] " if fields else "") + why)


def _refine(engine, task, actor, answer, why, verbs):
    # the round is authored as the node's executor, so it maps onto the contract as issued and re-authors none
    # (`held_contract`, Inv-1) — at an AUTO root (the user's criteria) and under a holder issuer alike
    if held_by_a_holder(engine, str(task.assignee)):
        return False, f"the split of {task.id} is its executor's move ({task.assignee}), not the system's"
    if any(k.state != State.OFFERED for k in engine.graph.get_active_children(task.id)):
        return False, "a refine may drop children, and some of this split's are already at work"
    out = verbs.refine(engine, str(task.id))
    # …and a round the account's limit refused authored nothing: read as "no split can be built", one probe of a limit
    # window lapsed contact's refutation and handed a node that had failed four rounds its single session back (critic)
    if (_stopped := what_stopped(out.get("stats"))):
        raise Unavailable(f"{_stopped}: the refine round was refused", limit=True)
    return not out.get("error"), str(out.get("error") or "")


def ask_of(engine, task, question: str) -> str:
    """The question as THIS node poses it: a park with a cause asks with it (`execution_park_said`)."""
    if question == "parked" and task is not None and (said := engine.parking.execution_park_said(task)):
        return f"{said}. Decide what happens to the node."
    if question == "parked" and task is not None and (note := engine.parking.execution_park_note(task)):
        return f"{QUESTIONS[question]['ask']} Its last: {note}."
    return QUESTIONS[question]["ask"]


def moves_for(engine, task, question: str) -> tuple:
    """The moves this question admits on THIS node: `drop_dependency` only where a child waits on a cancelled
    producer — offered on a dependency-order refutation it could never land, and an AUTO issuer spent four answers on
    it while the one move that could (a re-decomposition, §15.5) went unasked (GB_c_compiler_tmp5cb096).

    No `cancel` at an AUTO root: CANCEL is the refusal of the task (§11.2), and the goal is the user's — the system
    moving for them continues it by a re-ASSIGN, and silence closes it by its bound (§12.5). A machine issuer
    cancelled one "all 22 criteria pass" over the standing FAIL that escalated it (GB_sql_database_tncfrm404). On any
    other node of a plan the user handed in `cancel` is offered and STOPS the run (`_cancel`): the system never cuts
    that plan, and an issuer that finds a part of it cannot be carried says so to the user, who re-plans."""
    moves = QUESTIONS[question]["moves"]
    if question == "parked" and task is not None and engine.parking.execution_park_reason(task):
        # …a session in its place, by any move, is ended again (`execution_park_said`); none where only the user lifts it
        moves = () if users_criteria(engine.graph, task) else ("cancel",)
    if "drop_dependency" in moves and task is not None and not any(
            _cancelled_producers(engine, k) for k in engine.graph.get_active_children(task.id)):
        moves = tuple(m for m in moves if m != "drop_dependency")
    if "split_off" in moves and not (task is not None and _named_by_blocks(engine, task.id)):
        moves = tuple(m for m in moves if m != "split_off")
    if "cancel" in moves and (is_auto_root(engine.graph, task) or _offer_lapsed(engine, task)
                              or _validation_lapsed(engine, task)):
        moves = tuple(m for m in moves if m != "cancel")
    # …nor `refine` on a plan question at an AUTO root (the user's criteria are mapped by the split it re-cuts), nor
    # twice on one node: each is a multi-minute round, and a machine issuer answered the same question with one after
    # another (instruction audit 2026-11-17, row 9)
    if question == "plan" and "refine" in moves and (is_auto_root(engine.graph, task) or refined(engine, task.id)):
        moves = tuple(m for m in moves if m != "refine")
    if "redecompose" in moves and not task.parent_id:
        moves = tuple(m for m in moves if m != "redecompose")
    # …nor `promote` into, nor a Dep dropped from, nor a re-made split of, a plan the user handed in: each a split the
    # user did not make
    if users_plan(engine.graph):
        moves = tuple(m for m in moves if m not in ("promote", "drop_dependency", "redecompose", "split_off"))
    # …nor a finding ruled out of the user's goal, as a dispute's ruling is not (`_USERS_DISPUTE`): that one is theirs
    if question == "unrun" and (is_auto_root(engine.graph, task) or users_plan(engine.graph)):
        moves = ()
    return moves


def refined(engine, task_id) -> bool:
    """Has a plan question on this node been answered by a `refine` that landed — on its log, as `issuer_turn` says a
    move: refused, it is followed by ` REFUSED`."""
    said = re.compile(rf"{re.escape(str(task_id))}: [^,]+, on plan — refine(?=$|:| — )")
    return any(said.match(str(r.get("message") or "")) for r in engine.pipeline_log(about=f"{task_id}: "))


def _drop_dependency(engine, task, actor, answer, why, verbs):
    """A child consuming a producer that was cancelled waits on something that will never come: its
    issuer drops that Dep (the plan changes; the child then works or is re-planned by the next question)."""
    child, bad = _named_child(engine, task, answer)
    if bad:
        return False, bad
    if not (gone := _cancelled_producers(engine, child)):
        return False, f"{child.id} consumes no cancelled producer"
    for producer in gone:
        engine.remove_dependency(TaskId(producer), child.id)          # …the machine issuer's own act, as its promotion's edge
    return True, ""


def _split_off(engine, task, actor, answer, why, verbs):
    """A child on its split's refuted cycle whose backward waits came from its own checks running its consumers' code
    (measured live, AUTO c_compiler × Haiku 5.5, GB_c_compiler_tobsku412: `root.preproc`, 9 of 11 parts passed, its
    BLOCK naming all 8 of its criteria as needing the parser and codegen; `root.decls`, 6 parts, one criterion needing
    floating point). Its only repair was a reshape that cancelled it: the passed work lost, twice. A Dep edge is a
    criterion's reference (§2.7) — move the criterion and the edge goes with it — so in ONE re-decomposition (§15.5)
    the parent's split is re-admitted with a sibling carrying exactly those criteria, pinned checks and all,
    co-covering what the child covers and reading the child and the consumers its checks run (read by nobody, it
    closes no cycle), and the child is re-authored in place without them (Inv-1, §15.1: its subtree kept), gaining
    the issuer's `criteria` of its own unit where none would remain. A wait closes only where every criterion its
    BLOCK names moved. Nothing leaves the plan; the move is recorded as a spec defect with its justification."""
    child, bad = _named_child(engine, task, answer)
    if bad:
        return False, bad
    if not why:
        return False, "criteria moved out of a child say why: the justification is the record of the move"
    if (cycle := cycle_waits(engine, task, child)) is None:
        return False, f"{child.id} lies on no refuted cycle of {task.id}'s split — nothing to split off"
    if _settled(engine, child):
        return False, f"{child.id} is {child.state.name} and the plan rests on it (§12.14) — it is not revised"
    names = list(dict.fromkeys(str(i) for i in answer.get("items") or ()))
    if not names:
        return False, f"`items` names none of {child.id}'s criteria to move"
    if alien := [n for n in names if n not in {c.name for c in child.spec.criteria}]:
        return False, f"`items` names {', '.join(alien)} — not criteria of {child.id}"
    if not any(str(m.child_id) == str(child.id) for m in task.criterion_mappings):
        return False, f"{child.id} carries none of {task.id}'s criteria: a sibling beside it would cover nothing"
    others, waits = cycle
    if unnamed := [n for n in names if not any(n in ns for ns in waits.values())]:
        named = sorted(set().union(*waits.values()))
        return False, (f"no BLOCK of this cycle into {child.id} names {', '.join(unnamed)}: take it out of `items`"
                       + (f" — its BLOCKs name {', '.join(named)}" if named else
                          " — its BLOCKs name none of its criteria, so only a `reshape` restores the order"))
    # …AND ONE CLOSES ONLY WHEN EVERYTHING IT NAMES MOVED: one named criterion of eight closed every wait while seven
    # still ran the consumers (critic over 9a6db3d)
    if not (gone := {pair for pair, ns in waits.items() if ns and ns <= set(names)}):
        left = sorted(set().union(*waits.values()) - set(names))
        return False, f"every wait of this cycle into {child.id} also names {', '.join(left)}: move those too"
    if engine.dep_order_stands_without(task.id, gone, {str(t.id) for t in engine.graph.subtree(child.id)}):
        return False, (f"with the waits into {child.id} these criteria made closed, its cycle still stands (a declared "
                       f"seam, or a wait that names none of them) — only a re-decomposition restores it: `reshape`")
    spec, bad = _narrowed(child, names, answer, _split_of(engine, child))
    if bad:
        return False, bad
    if no := engine.refusal_for(child.id, Signal.ASSIGN, AgentId(actor), spec=spec):
        return False, f"{child.id}'s revision would be refused, so nothing of this move was made: {no.why}"
    reads = [str(child.id), *sorted(m for m, s in others.items() if any(p in s for p, _ in gone))]
    kid = _sibling(engine, task, child, names, reads, answer, why)
    if bad := _decompose_errors(engine, task, [kid]):
        return False, "; ".join(bad) + " — so nothing of this move was made"
    engine.revise(child.id, spec, AgentId(actor), reason=RevisionReason.SPEC_DEFECT)
    for p, c in sorted(gone):
        engine.remove_dependency(TaskId(p), TaskId(c))
    engine.emit_info("issuer", f"{child.id}: {', '.join(names)} moved to {kid['task_id']}, which runs after "
                               f"{', '.join(reads)}; its waits on {', '.join(sorted({p for p, _ in gone}))} closed — {why}")
    return True, ""


def cycle_waits(engine, task, child) -> Optional[tuple[dict, dict]]:
    """({each other member of the refuted cycle of `task`'s split that `child` lies on: its subtree}, {(producer,
    child): the child's criteria that discovered wait's BLOCK reason names}) — None off every refuted cycle. A
    discovered edge's glue is its BLOCK's reason, and it names the criteria that could not pass (live: `macros-and-
    conditionals, conditional-selection-and-undef, …`); a name is matched whole, hyphens included, so `macros` is not
    read inside `macros-and-conditionals`."""
    if not (group := next((set(g) for g in engine.dep_order_cycle_children(task.id) if str(child.id) in g), None)):
        return None
    others = {m: {str(t.id) for t in engine.graph.subtree(TaskId(m))} for m in group - {str(child.id)}}
    declared = {(str(e.from_id), str(e.to_id)) for e in engine.graph.declared_edges(child.id)}
    own = {c.name for c in child.spec.criteria}
    said = lambda text: {n for n in own if re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", text or "")}
    # …AS THE CONTRACT IN FORCE'S BLOCKS SAY IT: a repeated BLOCK reopens its record with the FIRST reason as glue, so a
    # later one naming the criteria, or one after a split_off re-authored the child, was read as naming none and only a
    # reshape was left (critic over 01ac2c7). The log keeps no producer per BLOCK: every wait is read as all of them say
    now = " ".join(a.reason or "" for a in on_current_version(engine.audit_log(child.id)) if a.signal == Signal.BLOCK)
    return others, {(str(e.from_id), str(e.to_id)): said(now if now.strip() else e.glue) for e in engine.graph.dep_edges()
                    if e.discovered and str(e.to_id) == str(child.id)
                    and any(str(e.from_id) in s for s in others.values())
                    and (str(e.from_id), str(e.to_id)) not in declared}


def _narrowed(child, names: list, answer, split=()) -> tuple[Optional[Spec], str]:
    """(the child's contract without `names`, gaining the criteria of its own unit the answer gives, '') or (None, why)."""
    added = [c for c in answer.get("criteria") or () if isinstance(c, dict)]
    if clash := [str(c.get("name")) for c in added if c.get("name") in {k.name for k in child.spec.criteria}]:
        return None, f"`criteria` adds {', '.join(clash)} — already {child.id}'s: name only what it gains"
    fresh, bad = _carry(child, added, split)
    if bad:
        return None, bad
    spec = dataclasses.replace(child.spec, criteria=tuple(c for c in child.spec.criteria if c.name not in names) + tuple(
        Criteria(c.get("name", ""), c.get("description", ""), check=_checks_of(c)) for c in fresh))
    if empty := criterionless(spec.criteria):
        return None, (f"moving {', '.join(names)} leaves {child.id} {empty} — give it in `criteria` what its own "
                      f"unit is checked by")
    return spec, ""


def _sibling(engine, task, child, names: list, reads: list, answer, why) -> dict:
    """The child `split_off` adds beside `child`, as `decompose` takes it: `names` with their checks as they stand,
    covering what `child` covers, reading `reads`."""
    sib = answer.get("child") if isinstance(answer.get("child"), dict) else {}
    name = str(sib.get("name") or f"{str(child.id).rsplit('.', 1)[-1]}_whole")
    # …A NEW NODE, ALWAYS: `_child_id` hands back a standing child's id (a reshape names one so), and a second split_off
    # under the default name, or one named as another sibling, revised that node in place — its criteria out of the plan
    # (critic over 996b1f0)
    return {"task_id": _child_id(engine, task, {"name": name}, frozenset(),
                                 {str(k.id) for k in engine.graph.get_children(task.id)}),
            "covers": [m.criterion_name for m in task.criterion_mappings if str(m.child_id) == str(child.id)],
            "deps": [{"from": r, "glue": f"its checks, moved out of {child.id}, run {r}'s result"} for r in reads],
            "spec": {"name": name, "description": str(sib.get("description")
                                                      or f"{child.id}'s behaviour as the whole runs it: {why}"),
                     "criteria": [c for c in _tools.task_out(child, engine, plan=False)["criteria"]
                                  if c["name"] in names]}}


def _decompose_errors(engine, task, kids: list, **kw) -> list[str]:
    """One re-admission of `task`'s split (`decompose`), answered by the refusals it met — [] where it was admitted."""
    try:
        out = _tools.decompose(engine, str(task.id), kids, **kw)
    except ValueError as e:
        out = {"error": str(e)}
    return [str(o["error"]) for o in (out if isinstance(out, list) else [out]) if isinstance(o, dict) and o.get("error")]


def _resplit(engine, task, actor, answer, why, verbs):
    """Re-issue the node's own contract unchanged: its split then drops the mappings to children that
    were cancelled, so what they covered becomes an honest coverage hole a new child can fill (the
    re-issue is the node's issuer's act, and its executor consents afresh)."""
    issuer = str(engine.graph.issuer_of(task.id))
    if held_by_a_holder(engine, issuer):
        return False, f"re-issuing {task.id} is its issuer's move ({issuer}), not the system's"
    live = {str(k.id) for k in engine.graph.get_active_children(task.id)}
    if not any(str(m.child_id) not in live for m in task.criterion_mappings):
        # …and the move for a split that as a whole does not carry the goal is named too: three answers in a row asked
        # `resplit` to rebuild the split and were sent only to `drop_child` (GB_c_compiler_tnqqhf184)
        return False, ("`resplit` only re-issues the node to prune mappings to children that are gone, and none is — it "
                       "would change nothing. To rebuild the split as a whole, `refine` (the decomposer re-cuts it over "
                       "the gate's findings, while no child is at work); to reshape one part, `drop_child` the child "
                       "that is wrongly cut and add the one that replaces it")
    engine.revise(task.id, task.spec, AgentId(issuer), reason=RevisionReason.OTHER)
    return True, ""


def _decline(engine, task, actor, answer, why, verbs):
    """The issuer's reason not to write what a validator saw outside the criteria into the split: no signal — the
    answer itself, logged and kept with the observations it retires (`issuer_turn`)."""
    return (True, "") if why else (False, "a decline says why the goal does not need what was observed")


def _retire(engine, task, actor, answer, why, verbs, retire=True):
    """The issuer's ruling on the findings a validator could not run (`Engine.rule_unrun`): no signal, the node waits in
    VALIDATING for its next validation, which a retired finding no longer binds."""
    refused = engine.rule_unrun(task.id, answer.get("retire_findings") or (), actor, why, retire)
    return not refused, refused


def _keep(engine, task, actor, answer, why, verbs):
    """…kept: the findings stay demanded (`_retire`)."""
    return _retire(engine, task, actor, answer, why, verbs, retire=False)


MOVES = {"retire": _retire, "keep": _keep, "cancel": _cancel, "decline": _decline, "drop_dependency": _drop_dependency, "drop_child": _drop_child, "resplit": _resplit, "resolve_block": _resolve_block, "reassign": _reassign, "promote": _promote,
         "add_criterion": _add_criterion, "drop_risk": _drop_risk,
         "revise_child": _revise_child, "split_off": _split_off, "add_child": _add_child, "reshape": _reshape, "redecompose": _redecompose, "dispute": _dispute,
         "refine": _refine, "challenge": _challenge}
#: The moves that install the node's OWN contract — at an AUTO root, the user's goal (`off_the_goal`).
_OWN_CONTRACT = (_reassign, _add_criterion)


def apply_move(engine, task_id: TaskId, question: str, actor: str, answer: dict,
               verbs: "Verbs | None" = None, where: "str | None" = None) -> tuple[bool, str]:
    """Carry out ONE answer, or say why it is refused. Returns (done, why-not). `where` — the node's workspace — is what a
    derivation of an expectation pinned on the user's goal may not run (`off_the_goal`)."""
    move, task = str(answer.get("move") or ""), engine.graph.get_task(task_id)
    if move not in (admissible := moves_for(engine, task, question)) or move not in MOVES:
        return False, f"`{move}` is not a move for this question; admissible: {admissible}"
    fn = MOVES[move]
    try:
        return fn(engine, task, actor, answer, str(answer.get("justification") or "").strip(), verbs,
                  **({"where": where} if fn in _OWN_CONTRACT else {}))
    except Exception as e:                              # noqa: BLE001 — a malformed answer is refused, not raised
        return False, f"the answer could not be carried out ({type(e).__name__}: {e})"


# === Asking ===

def _ask(engine, task_id, question, actor, schema, refusal, verbs, _llm, where=None):
    """The issuer's answer, and the ledger of the tools its run used — None where nothing could be run (the agent
    transport, the only one with `run_agent`, keeps the ledger of every run)."""
    # where the project's work runs — a contact run in the node's place, and a zero-tool answer too: it is told the
    # platform it runs on, and the work's is the one it answers about (a plan authored on the host named Windows tools
    # for a Linux project, smoke-exec-1025141852)
    ex = _execution(engine, verbs)
    llm = _llm or (verbs.llm(engine.system_model(), execution=ex) if ex else verbs.llm(engine.system_model()))
    llm.stage_hint = f"{task_id} issuer({actor}) {question}"
    # …WITH THE NODE'S PINNED INPUTS LAID DOWN, as a validator's are: a probe reading `{inputs}` run as written
    # printed "No such file" and then its `ok`, and a rejection "it prints ok" passed the shell rule having checked
    # nothing (critic over session a597fc08). The answer names the directory as `{inputs}` again.
    # …ALL THE VALIDATION LAYS, its parts' too (`validation_procedure`): laid its own alone, an issuer ruling on findings
    # over a settled part's pins found no file and ruled on the text (c_compiler pp-rest, 2026-11-06)
    at_place, text, laid = ex or LocalExecution(), "", {}
    try:
        with (_contact_place(where, at_place, engine.project_name) if where else contextlib.nullcontext()) as tmp,                 _round(engine, tmp):
            laid = materialize_inputs(engine.validation_procedure(task_id), tmp, at_place.files) if tmp else {}
            packet = issuer_context(engine, task_id, question, refusal, laid, tmp, at_place) + schema_instruction(schema)
            with (verbs.busy("issuer_turn", engine, task_id) if verbs else contextlib.nullcontext()):
                if where:
                    # …IN A COPY OF THE PLACE, as a validator's run is: the issuer rules on that delivery and must not be
                    # able to change it (§10.3); its answer reads as run in the place — and where places stand apart,
                    # never in the executor's place, its container and its CLI state (`ExecutionPort.apart`)
                    # …ruled on the delivery as DELIVER recorded it, held to it as a validator's copy is — a dispute on
                    # the one the FAIL judged, any other question too: a copy of the live place carried what the
                    # executor holds now, not what it handed in (critic over the judged tree)
                    # …BY ITS ID, never the live tree: with nothing delivered, the place's commit as it stands —
                    # a place of the system's committed whole — kept and logged
                    held = engine.delivered(task_id) or standing(engine, task_id, where)
                    # …built as its judge built it; a build that failed is no reason to withhold the ruling on the FAIL
                    # it made: the copy comes unbuilt, with the build's output (a dispute refused for it waited forever)
                    built: list = []
                    with snapshot(lambda: store.held(engine, at_place, held[1], (str(where), at_place)),
                                  Path(tmp) / "place", at_place, delivered=held, built=built, unbuilt_ok=True) as copy:
                        copy = judged_at(copy, where, at_place)      # …its own directory of the commit
                        text = llm.run_agent(_prompt(),
                                             CONTACT.format(where=copy, checkout=checkout_note(copy))
                                             + swap(packet, where, copy)
                                             + (f"\n\nBefore you, the system built this copy as its judge did: "
                                                f"{built[0]}\n" if built else ""),
                                             allowed_tools=CONTACT_TOOLS, cwd=copy, timeout=CONTACT_TIMEOUT_S)
                        text = swap(text, copy, where)
                else:
                    # the ZERO-TOOL port: an issuer reads the packet and answers; `run_agent` without a working
                    # directory refused every real call, so no machine issuer ever answered (hidden by fakes that
                    # accepted the missing argument)
                    text = llm.complete(packet, context=_prompt())
    except PlaceUnavailable as e:    # …the place down laying the inputs or copying: booked as a call that could not start
        llm.calls.append({"duration_ms": 0, "ended": "unavailable", "place": e.place, "error": str(e), "at": time.time()})
    except NotTheDelivery as e:
        # …a delivery no copy can be made of, by its own doing (an object missing or rewritten, a nested repository): a
        # cause to rule on, not to wait out — asked again it failed again, forever (critic over 909e417)
        text = llm.complete(packet + f"\n\nNO COPY of this delivery could be made for you, and the delivery itself is "
                                     f"the cause: {e}. Rule on that: there is no tree to run anything in.",
                            context=_prompt())
    except Uncopied as e:            # …no copy for a cause not the delivery's: no ruling yet, asked again
        raise Unavailable(f"no copy of {where} to rule on: {e}") from e
    finally:                         # …booked whatever raises after the model ran (leaving the copy, the swap)
        llm.tag_last(Stage.ISSUER)
        engine.record_llm_usage(Stage.ISSUER, llm, task_id)
    if failed := unanswered(llm.calls[-1:]):
        raise failed
    if not str(text or "").strip():
        raise Unavailable("the model call returned nothing")
    if where and the_call_was_cut(llm, str(text)):   # an agent run of minutes is where calls are severed (critic 8)
        raise Unavailable("the contact run was cut before it answered")
    file_tech_reports(engine, answer := parse_structured(text, schema), "issuer", actor, task_id)
    own = {probe_id(c.name, p) for c in engine.graph.get_task(task_id).spec.criteria for p in c.check or ()}
    answer = _unlaid(answer, {d.as_posix(): INPUTS_TOKEN if i in own else inputs_token(i) for i, d in laid.items()})
    return answer, dict(llm.last_tool_calls) if where else None


def _unlaid(x, dirs: dict):
    """The answer with every directory the inputs were laid down in named by its token again (`dirs`: {directory:
    token}) — `{inputs}` for the node's own probe, `{inputs:<id>}` for a part's — the contract pins the files, not one
    turn's temporary place."""
    if isinstance(x, str):
        for d in sorted(dirs, key=len, reverse=True):
            x = x.replace(d, dirs[d])
        return x
    if isinstance(x, list):
        return [_unlaid(v, dirs) for v in x]
    return {k: _unlaid(v, dirs) for k, v in x.items()} if isinstance(x, dict) else x


#: A plan's check no ruling may lift, as a criterion's last, false on correct work: the one move that changes it.
_LAST_CHECK = (". Where it IS demanded, as a check of the plan a ruling may not lift, and you ran it false on correct work, "
               "ACCEPT with that criterion replaced by one whose check holds")


def _ran_a_shell(ran: dict) -> bool:
    return any(str(k).split("(")[0].strip() == "Bash" for k in ran)


#: Said wherever a dispute at an AUTO root asks to rule a finding out of the user's goal (`Engine.users_dispute`).
_USERS_DISPUTE = ("{0}'s dispute asks to rule {1} outside the user's goal, and under AUTO only the user makes that ruling "
                  "(§10.1): answer it without `retire_findings` — REJECT_CHALLENGE, the finding staying demanded, with "
                  "what the executor must do to meet it, or ACCEPT_CHALLENGE with criteria you add. Your ruling was not "
                  "made; the user's door to it stays open.")


def _ruling(engine, task_id, answer) -> tuple[list, str]:
    """(the standing findings the answer's ruling retires, why it is refused — '' where it is not), read as the gate
    reads it (`findings.ruled`). It lands what the dispute named; the rest stays demanded and the executor may dispute
    it by name — refused whole, the same four ids were ruled on three times and the part closed by count (root.tr,
    2026-10-12). What it names that stands nowhere is refused by name, never dropped: the issuer names it right."""
    standing = [s for ps in engine.regression_probes(task_id).values() for p in ps if (s := p.get("id"))]
    retire, unknown = findings.ruled((answer or {}).get("retire_findings") or (), standing)
    said = findings.named(engine.challenge_reason(task_id) or "", standing)
    # …and what it names past the dispute is SAID to stay, never left for the issuer to believe retired: a ruling that
    # landed in part read as whole, and the node failed four times on what it thought it lifted (GF_cc_full1)
    if kept := [i for i in retire if i not in said]:
        engine.emit_info("issuer", f"{task_id}: the ruling's {', '.join(kept)} stay demanded — the dispute did not name "
                                   f"them; the executor may dispute them by name")
    return [i for i in retire if i in said], (
        f"your ruling names {', '.join(unknown)}, which no finding standing on {task_id} is — the standing ones are "
        f"{', '.join(standing) or 'none'}: name each by its id as shown, or by its bare hash" if unknown else "")


#: the dispute's two answers, as the refusal of either is recorded (`_turned_back`)
_A, _R = Signal.ACCEPT_CHALLENGE, Signal.REJECT_CHALLENGE


def _turned_back(engine, task_id: TaskId, sig, issuer_id: str, out: dict) -> dict:
    """An answer the system's own rule refused before its signal, put on the log with its reason
    (`Engine.record_refused_move`), so the issuer's next turn reads it (`refused_on_this_version`) — and returned."""
    engine.record_refused_move(task_id, sig, issuer_id, str(out.get("why") or out.get("status")))
    return out


def answer_the_challenge(engine, task_id: TaskId, issuer_id: str, _llm=None, _cb=lambda s: None,
                         refusal: str = "", verbs: "Verbs | None" = None, where: "str | None" = None) -> dict:
    """The ISSUER's answer to a dispute (§12.4's CHALLENGED): accept with the corrected contract (a new
    version, re-consented, Inv-1), or reject with the justification §16.12 requires. No signal is forged
    on a report that decides nothing. With the node's workspace (`where`) the issuer answers from contact, and a
    rejection whose run touched nothing is refused: a true challenge rejected stalls the work (§16.9's second
    exception) — accepting is bounded by the narrowing rules below and the executor's fresh consent."""
    task = engine.graph.get_task(task_id)
    if task is None:
        return {"task_id": str(task_id), "status": "gone"}
    answer, ran = _ask(engine, task_id, "dispute", issuer_id, ISSUER_SCHEMA, refusal, verbs, _llm, where)
    decision = str((answer or {}).get("decision", "")).strip().lower()
    retire, unknown = _ruling(engine, task_id, answer)
    if answer is None or decision not in ("accept", "reject"):
        # an acceptance names the contract it installs; falling through to a rejection would send the
        # executor back carrying a justification written to mean the issuer AGREED with him
        _cb(f"{task_id}: the issuer's adjudication decided nothing — the dispute stands")
        return {"task_id": str(task_id), "status": "unparsed"}
    # …AND A RULING THAT RETIRES A FINDING IS HELD TO THE SAME CONTACT: it takes back an observation of the work, and
    # an answer that ran nothing is a guess either way (critic over 28bd5e7)
    if (decision == "reject" or retire) and ran is not None and not _ran_a_shell(ran):
        # the dispute is not adjudicated yet: the question stands, asked again after its backoff
        return _turned_back(engine, task_id, _R if decision == "reject" else _A, issuer_id, {
            "task_id": str(task_id), "status": "uncontacted",
            "why": f"the {'rejection' if decision == 'reject' else 'ruling on the findings'} ran nothing: run the "
                   f"disputed checks in the workspace and decide on what they show, quoting each command and its "
                   f"output"})
    if decision == "reject":
        ok, why = _signalled(engine, task_id, Signal.REJECT_CHALLENGE, issuer_id,
                             justification=str(answer.get("justification", "")) or "the contract stands")
        engine.emit_info("issuer", f"{task_id}: dispute {'REJECTED' if ok else 'reject REFUSED'} by {issuer_id}")
        return {"task_id": str(task_id), "status": "rejected" if ok else "refused", "why": why}
    # …AND A PLAN HANDED IN IS CLOSED AT EVERY DEPTH: ruled below its root the finding went and the check stayed, a loop;
    # the run stops with the signal instead (`settle`)
    if retire and engine.users_plan():
        return _turned_back(engine, task_id, _A, issuer_id, {"task_id": str(task_id), "status": "users",
                                                           "why": _USERS_DISPUTE.format(task_id, ", ".join(retire))})
    if retire and (asked := engine.users_dispute(task_id)):
        # …THE RULING, NOT THE DISPUTE, IS THE USER'S: the system still rejects it or adds to the contract — a rejection
        # is read first, a stray ruling beside it ignored. Barred from every move, the root sat CHALLENGED on a dispute
        # that only said the findings could not be met, until the run's ceiling (GB_sql_database_tn03ao788, 2026-10-16)
        # …A CHECK OF THE PLAN THE SYSTEM WROTE IS NOT THE GOAL: refused its ruling, the 17 criteria resting on one part's
        # stub pin failed round after round, with no exit but the ceiling (GB_coreutils_tnyzqh948, 2026-11-04). What the
        # ruling may not reach stays demanded, and the executor may dispute it again.
        own = engine.plans_own_findings(task_id)
        if not (retire := [i for i in retire if i in own]):
            theirs = [i for i in asked if i not in own]
            return _turned_back(engine, task_id, _A, issuer_id, {"task_id": str(task_id), "status": "users",
                                                               "why": _USERS_DISPUTE.format(task_id, ", ".join(theirs))})
    # …AND WHAT IT NAMES THAT STANDS NOWHERE IS REFUSED BY NAME, never dropped: the issuer names it right (§12.16 (ii))
    if unknown:
        return _turned_back(engine, task_id, _A, issuer_id, {"task_id": str(task_id), "status": "refused", "why": unknown})
    try:
        # …below an AUTO root, a node of the user's plan takes additions only — no re-pin: its expected outputs are the
        # user's, and one re-pinned to what the build printed contradicted the root's own (GB_sql_database_tne9fg736)
        spec = _accepted_spec(engine, task, answer["criteria"]) if answer.get("criteria") else task.spec
    except Exception as e:                              # noqa: BLE001 — a malformed contract is refused
        return _turned_back(engine, task_id, _A, issuer_id, {"task_id": str(task_id), "status": "refused",
                                                           "why": f"the corrected contract is malformed: {e}"})
    if why := _no_decision(engine, task, answer, spec, retire):
        _cb(f"{task_id}: the issuer's acceptance decided nothing — the dispute stands")
        return _turned_back(engine, task_id, _A, issuer_id, {"task_id": str(task_id), "status": "unparsed", "why": why})
    # …AND IT MAY DROP ONLY WHAT THE DISPUTE QUESTIONED (§14.3's FM-2 answer removes one of two that
    # cannot both hold) — at the root under AUTO, nothing at all.
    asked = norm_words(engine.challenge_reason(task_id) or "")
    dropped = [c.name for c in task.spec.criteria if c.name not in {k.name for k in spec.criteria}]
    if unasked := [n for n in dropped if norm_words(n) - asked]:
        _cb(f"{task_id}: the adjudication would DROP {', '.join(unasked)}, which the dispute never "
            f"questioned — refused")
        return _turned_back(engine, task_id, _A, issuer_id, {
            "task_id": str(task_id), "status": "would_narrow", "dropped": unasked,
            "why": f"it would drop {', '.join(unasked)}, which the dispute never questioned"})
    if bad := off_the_goal(engine, task, spec, answer, where, verbs):
        return _turned_back(engine, task_id, _A, issuer_id, {"task_id": str(task_id), "status": "would_narrow",
                                                           "why": bad, "dropped": dropped})
    # the ruling rides the acceptance — one act, refused whole where it may not be made (`validation.ruling_refusal`)
    ok, why = _signalled(engine, task_id, Signal.ACCEPT_CHALLENGE, issuer_id, new_spec=spec,
                         retire_findings=tuple(retire), justification=str(answer.get("justification") or "") or None)
    # …WITH ITS REASON: 35 refusals of one node's acceptance (GB_sql_database_tn8rdk788 `value`, 180 min of re-challenges)
    # left the log saying only "REFUSED", and why could not be read back from the row
    engine.emit_info("issuer", f"{task_id}: dispute {'ACCEPTED' if ok else 'accept REFUSED'} by {issuer_id}"
                               + ("" if ok else f" — {str(why)[:400]}"))
    return {"task_id": str(task_id), "status": "accepted" if ok else "refused", "why": why}


def _contract_checks(engine, task_id: TaskId) -> dict:
    """The node's criteria as their checks stand: what a revision under work in hand rewrites."""
    t = engine.graph.get_task(task_id)
    return {c.name: (c.description, tuple(c.check or ())) for c in (t.spec.criteria if t is not None else ())}


def _checks_changed(before: dict, after: dict) -> int:
    """How many criteria a move added, dropped or re-pinned — said on the log, so a contract rewritten after the
    executor met it reads as that, not as a bare reassign (a tester's run: four pins replaced by ones written over
    the delivered code, visible only in the audit log)."""
    return sum(before.get(k) != after.get(k) for k in before.keys() | after.keys())


def issuer_turn(engine, task_id: TaskId, question: str, actor: str, verbs: "Verbs | None" = None,
                refusal: str = "", _llm=None, where: "str | None" = None) -> dict:
    """ONE issuer answer: assemble, ask, check, act. `where` — the node's workspace — is the answer's contact."""
    if question == "dispute":
        out = answer_the_challenge(engine, task_id, actor, _llm, refusal=refusal, verbs=verbs, where=where)
        return {**out, "status": "applied" if out["status"] in ("accepted", "rejected") else out["status"]}
    ep = episode(engine.graph.get_task(task_id))
    # what an `outside` answer answers: the observations its packet shows INLINE, read as it is built — one recorded
    # during the turn, or past the inline cap (the issuer of a split question has no tool to read the overflow file),
    # was not shown and stays asked: marking all answered lost the earliest, the row's own hole (critic over d6c48ea)
    shown = engine.outside_the_criteria(task_id, own=False)[:SHOWN_FINDINGS] if question == "outside" else ()
    answer, ran = _ask(engine, task_id, question, actor, MOVE_SCHEMA, refusal, verbs, _llm, where)
    if answer is None:
        return {"status": "unparsed", "why": "the answer was not one JSON object by the schema"}
    # …a retirement takes back an observation of the work, held to contact as a dispute's ruling is
    if question == "unrun" and answer.get("move") == "retire" and ran is not None and not _ran_a_shell(ran):
        return {"status": "uncontacted", "why": "the retirement ran nothing: run each finding in the workspace and rule "
                                                "on what it shows, quoting each command and its output"}
    if not _still_open(engine, task_id, question, ep):
        return {"status": "gone"}
    before = _contract_checks(engine, task_id)
    done, why = apply_move(engine, task_id, question, actor, answer, verbs, where)
    if done and shown:
        engine.answer_outside(shown, actor, str(answer.get("move")), str(answer.get("justification") or ""))
    changed = _checks_changed(before, _contract_checks(engine, task_id)) if done else 0
    engine.emit_info("issuer", f"{task_id}: {actor}, on {question} — {answer.get('move')}"   # read by `refined`
                     + (f" — CONTRACT REWRITTEN under work in hand: {changed} check(s) changed" if changed else "")
                     + (f": {str(answer.get('justification'))[:200]}" if done else f" REFUSED: {why}"))
    return {"status": "applied" if done else "refused", "move": answer.get("move"), "why": why}


# === What the graph waits on, and who answers ===

#: The order in which one node's questions are asked — ONE at a time per node, so an escalation's
#: CANCEL and a plan repair never race on the same subtree.
PRIORITY = ("dispute", "escalation", "external", "parked", "unrun", "repair", "split", "plan", "outside")

#: Seconds a node's question waits after a settle no model answered (unavailable, a failed turn) before it is asked
#: again, per such settle already spent — a transport failure gets time to pass, and nothing spins.
BACKOFF_S = 120

#: Seconds between answers that came and moved nothing (refused, unparsed, a review that removed no finding) while they
#: are free (FREE_ANSWERS): the model's own latency paces them, this only keeps an instant no-op from spinning. Backed off
#: as a failed transport, a refusal that names its own correction waited 2, 4, 8, 16, 32 min — an AUTO root's dispute
#: sat CHALLENGED 81 min, 62 of them idle (GB_sql_database_tmvpo1976); ~230 min across four rows.
PACE_S = 15

#: The statuses of a settle in which no model answered.
UNANSWERED = ("unavailable", "error")

#: The longest a node's question waits after settles that moved nothing: the wait doubles from BACKOFF_S
#: per such settle up to this — a transport that keeps failing is retried rarely, never muted (a cap that
#: muted a node's every question left a short outage to cancel the goal by its bounds).
MAX_BACKOFF_S = 2 * 3600


#: Applied answers in a row that leave their question open, taken at the pace they come before each further one waits
#: (`backoff`) — a rate, never a close: the count at which a plan episode used to be CLOSED (MAX_PLAN_ANSWERS).
FREE_ANSWERS = 24


def backoff(waits: int) -> float:
    """Seconds a node's question waits after `waits` settles that moved nothing."""
    return min(BACKOFF_S * 2 ** waits, MAX_BACKOFF_S)


#: How long a question the system owes may stay owed, and how many answers in a row may leave it standing, before the
#: system says it is stuck on it. Inv-8 promises that a move exists, not that it is made or moves anything (§12.13); for
#: the system's own moves that is the implementation's promise: a dispute it failed to rule froze a row 2 h 26 m (series
#: 2 REF 2), and disputes over findings shown without their inputs looped 5 h (series 3) — both found by a human.
STUCK_S, STUCK_ANSWERS = 1800, FREE_ANSWERS


def report_stuck(engine, questions, ledger: dict, owed: dict, now: float) -> list[str]:
    """Each question the system has owed past STUCK_S, or answered STUCK_ANSWERS times in a row without moving it, said
    ONCE per node version as a TECH REPORT — the system reporting itself as an executor does; nothing else changes (the
    clock still owns the lapse, no verdict is invented). `owed` — (node, question) → (since, versions said, last move)
    — is the caller's across sweeps; a question that closes leaves it. A question MOVES when its node takes a new
    version or, where it moves by degrees (`_left_open`), when what it leaves open falls below the least seen on that
    version; both counts — the time owed and the answers that left it standing — run from its last move."""
    for k in set(owed) - set(questions):
        del owed[k]
    said = []
    for task_id, question in questions:
        task = engine.graph.get_task(task_id)
        since, done, move = owed.setdefault((task_id, question), (now, frozenset(), None))
        if task is None or engine.paused():
            continue
        gen = f"{task_id}#{task.iteration}#{task.reopens}#{question}"
        waits, _, answers = ledger.get(gen, (0, 0.0, 0))
        left = _left_open(engine, task_id, question)
        if move is None or move[0] != gen:        # first seen, or a new version: the version is the move
            since = since if move is None else now
            move = (gen, left, answers if move is None else 0)
        elif left is not None and (move[1] is None or left < move[1]):
            since, move = (now, (gen, left, answers)) if move[1] is not None else (since, (gen, left, move[2]))
        if answers < move[2]:                     # the ledger closed and reopened it between sweeps
            move = (move[0], move[1], answers)
        stood = answers - move[2]
        owed[(task_id, question)] = (since, done, move)
        if gen in done or (now - since < STUCK_S and stood < STUCK_ANSWERS):
            continue
        owed[(task_id, question)] = (since, done | {gen}, move)
        engine.tech_report(f"the system is stuck on its own move: it owes the {question} question on {task_id} for "
                           f"{now - since:.0f}s; {stood} answer(s) in a row left it standing, {waits} turn(s) went "
                           f"unanswered", role="system", actor="liveness", task_id=task_id)
        said.append(str(task_id))
    return said


def _left_open(engine, task_id: TaskId, question: str) -> Optional[int]:
    """How much of a question is left open, where answering it moves by degrees: the plan gate's holes and Level-2
    findings — a plan converging 44 → 8 findings over 27 min, each answer changing it, was said stuck at 1814 s
    (gb-c-compiler-tnpji8716, 2026-10-30). None where a question only closes, and while the plan's review is stale (an
    answer changed the plan and no review has run on it): no reading then, not zero."""
    if question != "plan" or (found := engine.open_l2_findings(task_id)) is None:
        return None
    return len(engine.split_holes(task_id)) + len(found)


def _watched(engine, agents, ledger: dict, owed: Optional[dict], now: float) -> list:
    """The open questions, each one the system is stuck on said first (`report_stuck`) where the caller keeps `owed` —
    only those whose mover is the system (`system_mover`): the owner of a move is read off the log (Inv-8), and a
    person's wait is no stall of the system's nor a fault of his (§12.2) — a no-mode root's plan question, the person's,
    was said "the system is stuck on its own move" after 1801 s (rdl tr-1, 2026-11-23)."""
    questions = open_questions(engine)
    if owed is not None:
        report_stuck(engine, [(t, q) for t, q in questions if system_mover(engine, agents, t, q) is not None],
                     ledger, owed, now)
    return questions


def _asked_key(task, question: str) -> str:
    """The ledger's key of one question on one version of a node (`answer_open_questions`)."""
    return f"{task.id}#{task.iteration}#{task.reopens}#{question}"


def _said_moved_nothing(engine, t, q, st, out, n) -> float:
    """An issuer's answer that came and moved nothing: said with what refused it, and the wait to the next — a
    challenged root's issuer answered twelve times over 20 min, each moving nothing, and not one line reached the log
    (s16b, 2026-11-16). The refusal it carries is the next answer's prompt, waited on only past the free count."""
    wait = backoff(n - FREE_ANSWERS - 1) if n > FREE_ANSWERS else PACE_S
    engine.emit_info("issuer", f"{t}: the issuer's answer on {q} moved nothing ({st}) — "
                               f"{out.get('why') or 'no reason given'}; asked again in {wait:.0f}s")
    return wait


def answer_owed_first(engine, agents, ended: set, task) -> Optional[str]:
    """The question on this node the system's issuer has not yet had his say on, or None: his answer and his signature are
    one party's acts, so a machine validation waits for it. Once only: a turn that ended leaving it open, however it ended
    (`ended`, beside the ledger's rate), lets the validation start, the question asked on at its rate; and a turn that never ends waits no
    longer than VALIDATING's own bound, which hands the delivery to him (§16.14). A `gone` or a review still running is no
    turn ended: the next sweep asks."""
    question = dict(open_questions(engine)).get(task.id)
    if question is None or system_mover(engine, agents, task.id, question) is None:
        return None
    return None if _asked_key(task, question) in ended else question


def open_questions(engine) -> list[tuple[TaskId, str]]:
    """Every node the graph waits on an issuer for, with its most pressing question — a read only."""
    found: dict = {}
    parked = engine.parking.parked_executions()
    by_state = {State.CHALLENGED: "dispute", State.ESCALATED: "escalation"}
    for t in engine.all_tasks():
        qs = []
        if t.state in by_state:
            qs.append(by_state[t.state])
        elif (t.state == State.BLOCKED and not engine.block_clears_itself(t) and not _starved(engine, t)
              and not engine.block_is_the_splits(t.id)):
            qs.append("external")
        elif str(t.id) in parked:
            qs.append("parked")
        elif t.state == State.VALIDATING and engine.unrun_findings(t.id):
            qs.append("unrun")
        kids = engine.graph.get_active_children(t.id)
        # …a deferred split only once the results it waits on stand: asked at issue, it is the guess FM-6 names (§8.6)
        if (t.state in (State.OFFERED, State.EXECUTING, State.REWORKING) and system_splits(engine, t)
                and not engine.split_waits_on(t.id)):
            qs.append("split")
        if kids and t.state not in (State.DONE, State.ABANDONED, State.CANCELLING):
            refuted = engine.decomposition_refuted(t.id)
            if (refuted and not awaits_the_plans_review(refuted) or engine.dep_order_refuted(t.id)
                    or any(_starved(engine, k) for k in kids)):
                qs.append("repair")
            elif refuted or engine.split_holes(t.id) or any(
                    k.state in (State.OFFERED, State.CHALLENGED) and engine.execution_blocked_by(k.id) for k in kids):
                qs.append("plan")
            # …and what a child's validator saw that no criterion writes, asked of the split's holder — the child's
            # issuer — once, holding nothing: shown only in a context, it was readable and never delivered: a validator
            # wrote the very hole the held-out suite then failed, the node passed and the root closed DONE (5cad9c4).
            # Not in a plan the user handed in: only its author writes into it
            if not engine.users_plan() and engine.outside_the_criteria(t.id, own=False):
                qs.append("outside")
        if qs:
            found[t.id] = min(qs, key=PRIORITY.index)
    return list(found.items())


def awaits_the_plans_review(refusal: str) -> bool:
    """Does a refuted split's re-delivery wait on its plan's Level-2 check — no current verdict over the revision, or its
    findings open — rather than on a change to the split? That is the plan's question (review, fix, dispute), not a
    repair: asked as repair, the review never ran and the machine issuer added a near-identical child ten times over,
    none started (GB_sql_database_tmyl10584, 2026-10-16), and a finding it believed wrong had no dispute move. Read off
    the gate's own instruction (`validation._refuted_coverage_refusal`), the one wording both branches share."""
    return "review_decomposition(" in refusal


def _starved(engine, child) -> bool:
    """A live child consuming a producer that was cancelled — it waits on something that will not come."""
    return bool(_cancelled_producers(engine, child))


def _cancelled_producers(engine, child) -> list[str]:
    """The cancelled producers a live child consumes."""
    if child.state not in (State.OFFERED, State.BLOCKED, State.EXECUTING):
        return []
    return [str(e.from_id) for e in engine.get_dependencies() if str(e.to_id) == str(child.id)
            and (engine.graph.get_task(TaskId(e.from_id)) or child).state in (State.ABANDONED, State.CANCELLING)]


def _machine_issuer(engine, agents, task_id: TaskId) -> Optional[str]:
    """The node's ISSUER when the system makes its moves — a registered participant, or the standing
    agent under AUTO (the customer, who does not intervene) — else None."""
    return str(engine.graph.issuer_of(task_id)) if engine.issuer_kind(task_id, agents) == "machine" else None


def system_mover(engine, agents, task_id: TaskId, question: str) -> Optional[str]:
    """Who moves for the SYSTEM on this question — or None when the move is a person's or a holder's.

    A split question is the node's executor's (a registered one). An issuer question is the machine
    issuer's (`_machine_issuer`); with NO mode set only its disputes are — the one issuer move the system made before
    modes existed. A person's issuer moves, the standing agent's with no mode included, are never the system's: it holds
    no role there (§10.1), and answering would be a party outside Del deciding the contract under his name (§11.6)."""
    task = engine.graph.get_task(task_id)
    if engine.mode() is None:
        # …a registered machine issuing to itself included: it has no other live mover
        return _machine_issuer(engine, agents, task_id) if question == "dispute" else None
    if question in SPLIT_QUESTIONS:
        return str(task.assignee) if agents.get(str(task.assignee)) is not None else None
    return _machine_issuer(engine, agents, task_id)


def episode(task) -> str:
    """The key of one visit of the question: a new state entry or a new version is a new question."""
    return f"{task.id}#{task.state.name}#{task.state_entered_at}#{task.iteration}#{task.reopens}"


def _still_open(engine, task_id: TaskId, question: str, ep: str) -> bool:
    task = engine.graph.get_task(task_id)
    return task is not None and episode(task) == ep and (task_id, question) in open_questions(engine)


def review_due(engine, task_id: TaskId) -> bool:
    """No Syntactic hole and no current review: the plan's next answer is its review, not an issuer's turn."""
    return engine.open_l2_findings(task_id) is None and not engine.split_holes(task_id)


def _review(engine, task_id: TaskId, verbs: Verbs) -> dict:
    """Run the plan's review; applied where it moved the gate."""
    before = engine.stored_review_findings(task_id)
    answered = set((engine.get_critique(task_id) or {}).get("disputes") or {})
    out = verbs.review(engine, str(task_id)) or {}
    # …a review already running answers this question when it lands: no transport failed, so nothing is backed off.
    # Read as one, every plan fix (whose own review starts at once) doubled the wait — 32, 64, 120 min idle on an
    # own-plan root between its fixes, no part started in 4.6 h (GB_sql_database_tnb3ow508, 2026-10-22)
    if out.get("inflight"):
        return {"status": "inflight", "kind": "review"}
    if not out.get("stats"):
        raise Unavailable("no review ran (the model layer did not answer)")
    if failed := unanswered(out["stats"]):
        raise failed
    after = engine.open_l2_findings(task_id)
    # progress = the gate opened, or at least one standing finding is gone (sets, not counts: two
    # closed and two new is movement); a review with no readable verdict, or one that removed
    # nothing, moved nothing — backed off, so a checker that never lands a verdict is asked rarely
    # …and a review that raises again ONLY what was answered in writing is the checker's reading of a plan
    # that changed since, not an issuer that failed to move: counted so, three re-issued children closed a
    # converging AUTO root (critic, 2026-09-27); the dispute that answers it again closes nothing
    moved = after is not None and (not after or before is None or not set(after) >= set(before)
                                   or set(after) <= answered)
    return {"status": "applied" if moved else "unproductive", "kind": "review"}


def what_contact_refuted(engine, task_id: TaskId) -> str:
    """What contact refuted in this node's split, each of the three ways a repair is owed: its FAIL over passing
    children, its order, a child waiting on a producer that was cancelled."""
    starved = [f"{k.id} waits on {', '.join(ps)}, cancelled — drop that Dep and cover what it fed another way"
               for k in engine.graph.get_active_children(task_id) if (ps := _cancelled_producers(engine, k))]
    return "\n".join(filter(None, (engine.decomposition_refuted(task_id), engine.dep_order_refuted(task_id),
                                   *_named_by_blocks(engine, task_id), *starved)))


def _named_by_blocks(engine, task_id: TaskId) -> list[str]:
    """For each child on a refuted cycle, the criteria of its own its BLOCKs from the cycle name — the `items` a
    `split_off` takes, which the refutation's line alone never showed (the BLOCK's reason lives on the edge). None on a
    plan the user handed in, where no such move is the system's."""
    task = engine.graph.get_task(task_id)
    if task is None or users_plan(engine.graph):
        return []
    return [f"{k.id}'s BLOCK from {', '.join(sorted({p for p, _ in waits}))} names these of its criteria as unable to "
            f"pass before them: {', '.join(sorted(set().union(*waits.values())))} — `split_off` moves them (every "
            f"one its BLOCK names) to a sibling, with their checks, keeping its work"
            for k in engine.graph.get_active_children(task_id)
            if (cycle := cycle_waits(engine, task, k)) and (waits := {w: ns for w, ns in cycle[1].items() if ns})]


@system_decides()
def settle(engine, agents, task_id: TaskId, question: str, actor: str, verbs: Verbs) -> dict:
    """Answer one question: the review first where the plan has none current, else the issuer's answer,
    and one retry with its refusal quoted — each only while the question is still the one that was asked.
    A node no answer moves is backed off by the sweep (`answer_open_questions`) and ends by its clock."""
    ep = episode(engine.graph.get_task(task_id))
    if not _still_open(engine, task_id, question, ep):
        return {"status": "gone"}
    if question == "plan" and review_due(engine, task_id):
        return _review(engine, task_id, verbs)
    # …A SPLIT OF THE USER'S PLAN IS NOT THE SYSTEM'S TO REMAKE: owed where contact refuted it or a leaf proved larger
    # than a session, and only its author re-plans it — the run stops, its sessions finishing, its record whole
    if question in SPLIT_QUESTIONS and engine.users_plan():
        # …"refuted" only where contact refuted it: a part closed without a verdict (its bound, a person) leaves the
        # plan unable to go on, which is not the same news (critic over f96e6f8, E)
        said = ("is refuted" if engine.decomposition_refuted(task_id) or engine.dep_order_refuted(task_id)
                or question == "split" else "cannot go on")
        why = (f"the plan the user gave {said} at {task_id} ({question}: "
               f"{what_contact_refuted(engine, task_id) or QUESTIONS[question]['ask'][:200]}) — only the user re-plans "
               f"it: hand a corrected plan as a new goal (`auto_decompose` with `spec`, closed as this one; or `refine_plan` on its file, then `auto_decompose(plan=path)` on a new project, which contact may then repair),or `set_mode` "
               f"(with `user_said`) to hold the plan yourself; `start_project` alone stops it here again")
        engine.pause("system", why)
        return {"status": "users", "why": why}
    if question == "parked" and not moves_for(engine, (t := engine.graph.get_task(task_id)), question):
        # …no move of the system's lifts it (an AUTO root past its disk bound: cancelling is the user's): the user told
        why = f"{task_id}: {engine.parking.execution_park_said(t)}; {USERS_WAY}"
        engine.pause("system", why)
        return {"status": "users", "why": why}
    if question == "unrun" and not moves_for(engine, engine.graph.get_task(task_id), question):
        why = (f"{task_id}'s validator could not run " + "; ".join(
            f"{r['id']} ({r['why']})" for r in engine.unrun_findings(task_id)) + ", so its PASS waits on them; only the "
            f"user rules a finding out of the user's goal or plan: `rule_unrun_finding(task_id, findings, ruling, why)`, then "
            f"`start_project` — the node waits in VALIDATING")
        engine.pause("system", why)
        return {"status": "users", "why": why}
    if question == "split":
        # ONE admissible move, and it is not a judgement: the refine round authors the split (SEARCH + the
        # form audit), the same verb a plan question may call; a model turn would only choose it
        done, why = _refine(engine, engine.graph.get_task(task_id), actor, {"move": "refine"}, "", verbs)
        # …and a round that split nothing moved nothing: backed off, never read as progress (a refine
        # that built no child "applied" twelve times in three seconds, then the node was closed)
        split = done and engine.split_owed(task_id) is None
        if not done:   # …SAID, where it was not: a refused split left root.tr OFFERED 2 h 35 min with no line (tn73sy660)
            engine.emit_info("issuer", f"{task_id}: the split owed here was REFUSED — {why}")
        return {"status": "applied" if split else "refused" if not done else "unproductive", "move": "refine",
                "why": why or ("" if split else "the refine round built no split")}
    if question == "repair" and (out := _cycle_in_hand(engine, engine.graph.get_task(task_id))):
        return out
    # an issuer's question is about the contract against the world — what failed, what blocks — and is answered from
    # contact; the split's questions are the executor's planning over the map
    where = (verbs.place(engine, agents, task_id)
             if verbs and verbs.place and question not in SPLIT_QUESTIONS else None)
    out = issuer_turn(engine, task_id, question, actor, verbs, where=where, refusal=(
        "Its place is past its disk bound, so no next contract runs there: `cancel` with the reason."
        if question == "parked" and engine.parking.execution_park_reason(engine.graph.get_task(task_id)) else
        "" if question in SPLIT_QUESTIONS else refused_on_this_version(engine, task_id, actor)))
    if out["status"] != "applied" and _still_open(engine, task_id, question, ep):
        out = issuer_turn(engine, task_id, question, actor, verbs, where=where,
                          refusal=str(out.get("why") or out["status"]))
    # …A DISPUTE A CLOSED PLAN CANNOT ANSWER IS THE USER'S: asked of a model again it was thrown away again, no line said,
    # 29 calls in 27 min (tracker, 2026-11-03); and so is one its issuer twice asked to rule out, which he may not there
    if question == "dispute" and out["status"] in ("unparsed", "users") and engine.users_plan():
        why = (f"the plan the user gave cannot go on at {task_id}: its executor disputes a check, and only the user "
               f"changes a check of that plan, by handing a corrected plan as a new goal (`auto_decompose` with `spec`): "
               f"{str(engine.challenge_reason(task_id) or '')[:300]}")
        engine.pause("system", why)
        return {"status": "users", "why": why}
    return out


def refused_on_this_version(engine, task_id: TaskId, actor: str) -> str:
    """The engine's last refusal of this issuer's move on the node's CURRENT contract, read off the log — handed to its
    next turn, not only to the retry inside one settle: a sweep's first ask started blind, and one refusal (a probe
    rewrite admission refuses) came back 33 times over 180 min while each turn fell back to rejecting the dispute
    (GB_sql_database_tn8rdk788 `value`). A contract installed since (ASSIGN, ACCEPT_CHALLENGE) starts clean."""
    for e in reversed(engine.audit_log(task_id)):
        if not e.rejected and e.signal in (Signal.ASSIGN, Signal.ACCEPT_CHALLENGE):
            return ""
        if e.rejected and str(e.source or "") == str(actor) and e.error:
            return f"An earlier {e.signal.name} of yours on this contract was refused: {e.error}"
    return ""


def answer_open_questions(engine, agents, claim, release, cap, verbs: Verbs, ledger: dict,
                          owed: Optional[dict] = None, ended: Optional[set] = None) -> list[str]:
    """One sweep: each node's open question the SYSTEM answers is taken by ONE thread at a time (a claim
    on the node, released when the answer is in). The ledger keeps, per node generation, how many settles
    moved nothing, how many applied answers in a row left the same question open, and when the node may be asked
    again. A count sets the RATE, never closes: a settle that moved nothing backs off, and so does an answer past
    FREE_ANSWERS that left its question standing (without it a question its own answer brings straight back was asked
    at the model's latency for a whole version). Each version ends by its clock, the node by its issuer's
    act (§12.15 Φ2, Φ3 — "the counters are not finiteness devices"; every count-close measured on AUTO hid the
    engine's own refusals of a correct move, GB_sql_database 2026-10-14/15)."""
    started = []
    now = time.monotonic()
    for task_id, question in _watched(engine, agents, ledger, owed, now):
        task = engine.graph.get_task(task_id)
        actor = system_mover(engine, agents, task_id, question)
        # a revision the machine makes itself must not reset its own backoff — and a new question on the same version
        # owes none of the old one's: a dispute's doubled wait kept the TIMEOUT into ESCALATED from asking the decision
        # for 2 h (series 2 REF 2)
        gen = _asked_key(task, question) if task else ""
        waits, not_before, answers = ledger.get(gen, (0, 0.0, 0))
        if (actor is None or task is None or now < not_before or being_rewritten(engine, task_id)
                or not claim(f"q:{task_id}")):
            continue
        started.append(str(task_id))

        def _run(t=task_id, q=question, a=actor, g=gen, w=waits, n=answers):
            out = {"status": "error"}
            with cap:
                try:
                    # …stopped while it waited for its slot: nothing starts, the question asked again after the start
                    out = {"status": "gone"} if engine.paused() else settle(engine, agents, t, q, a, verbs)
                except Unavailable as e:
                    out = {"status": "unavailable", "why": str(e), "limit": e.limit}
                except Exception as e:                  # noqa: BLE001 — a failed turn is not a signal
                    engine.emit_info("issuer", f"{t}: the issuer turn on {q} FAILED — {type(e).__name__}: {e}")
                finally:
                    st, now_ = out.get("status"), time.monotonic()
                    if st not in ("gone", "inflight") and ended is not None:
                        (ended.add if (t, q) in open_questions(engine) else ended.discard)(g)
                    # `w` counts the settles in a row no model answered — a transport's failures; any answer ends the
                    # run (an account's limit window left it raised for the rest of a version, every later wait doubled)
                    review = out.get("kind") == "review"
                    if st == "applied":
                        # An answer that left its question open counts toward the rate; a review (the plan's reader,
                        # not an answer to it) and a dispute do not; a question that closed starts the count over
                        counted = not review and (q != "plan" or out.get("move") != "dispute")
                        n = n + counted if (t, q) in open_questions(engine) else 0
                        paced = backoff(n - FREE_ANSWERS - 1) if n > FREE_ANSWERS else 0
                        # …but the plan's READER is owed at once, and the rate is laid AFTER it: an own-plan root's
                        # admitting review waited 32 min behind its issuer's count (GB_c_compiler_tnl51c552,
                        # 2026-10-28); dropped instead of moved, a review rewording its findings after every fix let
                        # fix and review alternate at the model's pace (critic over that fix)
                        wait = ((0 if q == "plan" and review_due(engine, t) else paced) if counted
                                else paced if review else 0)
                        ledger[g] = (0, now_ + wait, n)
                    elif st in UNANSWERED:
                        wait = (engine.stop_wait_s() or min(backoff(w), LIMIT_RETRY_S)) if out.get("limit") else backoff(w)
                        ledger[g] = (w + 1, now_ + wait, n)
                        # …SAID (a failed turn is, above): a parked leaf's issuer met a dead Docker daemon at every ask,
                        # and 40 min passed with not one line in the log (GB_sql_database_tnij0m952)
                        if st == "unavailable":
                            engine.emit_info("issuer", f"{t}: the issuer's turn on {q} was not answered — "
                                                       f"{out.get('why')}; asked again in {wait:.0f}s")
                    elif st == "inflight":
                        # a review running (started outside this sweep) is the read: the answer's rate is laid after it
                        ledger[g] = (w, now_ + max(PACE_S, backoff(n - FREE_ANSWERS - 1) if n > FREE_ANSWERS else 0), n)
                    elif st != "gone":
                        # an answer came and moved nothing: one more answer at the model's pace, its wait only past
                        # the free count — the refusal it carries is the next answer's prompt, not a reason to wait
                        n = n + (not review) if (t, q) in open_questions(engine) else 0
                        ledger[g] = (0, now_ + _said_moved_nothing(engine, t, q, st, out, n), n)
                    release(t, redispatch=st == "applied" and q == "dispute")
        threading.Thread(target=_run, daemon=True).start()
    return started
