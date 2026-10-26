"""THE ISSUER FUNCTION — the issuer's moves, where the issuer is a machine.

In a graph the system holds, the issuer of a node is its parent's executor, and at the root under AUTO
the system moves for the goal's customer, who does not intervene. Every state in which the protocol
waits on an issuer then needs someone to make the move (Inv-8) — and the one such move that existed
(answering a dispute) was made by a model given the node's contract and the complaint, and nothing of
the task or its state. This package is that party: ONE context assembled from the graph, six questions,
and only the canon's moves as answers, each checked by code before anything is signalled.

- plan       a split the plan gate holds (§11.5): fix it, dispute a finding, or refine it once
- dispute    CHALLENGED: accept with the corrected contract, or reject with the reason
- escalation ESCALATED: re-ASSIGN (deadline, budget, criteria, executor) or CANCEL
- repair     contact refuted the decomposition: revise the covering child, or add one
- split      a childless node judged larger than one session of its executor: its split is owed (§3.7)
- parked     an executor round left the node in its hands twice: re-ASSIGN or CANCEL
- external   BLOCKED on nothing the graph holds: resolve with an action, re-ASSIGN, or CANCEL

`plan`, `repair` and `split` are the moves of the node's own executor (the author of its split and the issuer of
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
from gfso.adapters.execution import LocalExecution
from gfso.adapters.llm.stats import is_limit, refused_by_limit, the_call_was_cut
from gfso.adapters.llm.structured import parse_structured, schema_instruction
from gfso.config import LIMIT_RETRY_S, agent_id as _config_agent_id
from gfso.core.graph.model import on_the_wall, project_now
from gfso.core.graph.mutations import Schedule, producers_of
from gfso.core.handlers.structural import risks_naming_own_criteria
from gfso.core.protocol.procedure import (INPUTS_TOKEN, materialize_inputs, pinned_files, probe_id,
                                          probes_from as _checks_of, unrerunnable, with_named_files)
from gfso.core.types import (AgentId, Criteria, DEFAULT_MAX_ITERATIONS, Register, RevisionReason, Signal,
                             SignalData, Spec, Stage, State, TaskId, register_of, set_aside_of)
from gfso.decompose.extract import extract_spec
from gfso.decompose.seams import seam_problems
from gfso.engine import findings, loose_finding_key
from gfso.engine.validation import is_auto_root, party_kind, users_criteria, users_plan
from gfso.packets import answered_challenges, answers_given, capped, list_key
from gfso.engine.events import emit_cb
from gfso.packets import TECH_REPORT, checkout_note, file_tech_reports

log = logging.getLogger("gfso.issuer")

PROMPT = Path(__file__).parent / "issuer.md"

#: How many contracts the machine writes for the AUTO ROOT out of ESCALATED before the next must CHANGE what failed — there
#: it stands in for the user, the root's issuer, and nothing above bounds it; below the root no count (§12.15). Not a
#: close by count: §12.15 — "a counter there would, exhausted, leave the owner of a live goal only CANCEL or silence …
#: re-created by fiat" — and under AUTO the machine IS that owner. Past it the issuer is asked, told the count; it may
#: write a contract that changes the criteria, the executor or the budget, or close with its reason (critic over
#: session 475ba784: the count used to close before any issuer turn was asked).
MAX_EXTENSIONS = 2

#: The largest rework budget a re-issued contract may carry: an extension, not an open loop.
MAX_REWORK_BUDGET = 2 * DEFAULT_MAX_ITERATIONS

#: The longest a re-issued contract may run, in hours: an extension, not an open end.
MAX_EXTEND_HOURS = 48

#: The tail of a delivery the issuer reads — the part that says what was done and what was checked.
DELIVERY_TAIL = 4000

#: The trail entries the issuer reads, newest last.
TRAIL = 30

#: The questions whose mover is the node's EXECUTOR (the author of its split); the rest are its issuer's.
SPLIT_QUESTIONS = ("plan", "repair", "split")

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


def _execution(engine, verbs: "Verbs | None"):
    return verbs.execution(engine) if verbs is not None and verbs.execution is not None else None


def signal_ok(engine, task_id: TaskId, sig: Signal, source: str, _why: "list | None" = None,
              **kw) -> bool:
    """Send one signal; True when the FSM took it. `_why` collects the refusal, when a caller
    intends to SAY it rather than only log it — the reason existed and reached the log alone."""
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
        return (f"    - decided by — {p.behaviour}: `{p.command.replace(INPUTS_TOKEN, d.as_posix()) if d else p.command}`"
                f" → must show: {p.expect}"
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
    missed «Comment handling in lexical analysis» in "the root's comment handling criterion" (2026-10-14)."""
    asked, cited = norm_words(engine.challenge_reason(task.id) or ""), set()
    for e in reversed(engine.audit_log(task.id)):
        if e.rejected:
            continue
        if e.signal in (Signal.ASSIGN, Signal.ACCEPT_CHALLENGE):
            break
        if e.signal == Signal.FAIL:
            cited |= set(e.failed_criteria or ())
    return frozenset(c.name for c in task.spec.criteria if c.name in cited or not norm_words(c.name) - asked)


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


def _standing_findings(engine, task_id) -> str:
    """The node's regression set, a line per finding with its id, as run, as the engine demands it — bounded as the
    executor's packet is (`capped`): the whole set inline, 562k characters, would end the dispute's issuer session
    `prompt_too_long` (GB_sql_database_tmxu0n436)."""
    workdir = (engine.get_exec_verdict(task_id) or {}).get("workdir")
    return "".join(f"\n- {c}:" + capped([f"[{p.get('id')}] {p.get('behaviour')}: `{p.get('seen') or p.get('as_run')}` "
                                         f"(recorded: «{p.get('expect')}»)" + (f" — {why}: shown, not demanded" if (
                                             why := unrerunnable(p, None, workdir)) else "") for p in ps],
                                        "standing findings", list_key(engine, task_id, c, "issuer"))
                   for c, ps in engine.regression_probes(task_id).items()).lstrip("\n")


def _standing_ids(engine, task_id, named: list) -> list:
    """The standing findings a ruling names, each by the full id the engine keeps: a bare hash only one of them has is
    that one, and a finding no longer standing names nothing to retire. Unlike a dispute (`findings.named`), a ruling
    is the act itself: a hash two criteria share names neither here, and the issuer is told both to choose from.
    Named by its hash, the ruling was refused whole, the issuer fell back to rejecting a true challenge, and a part was
    disputed and rejected a dozen times over 17 min (AUTO haiku coreutils, root.build, 2026-10-12)."""
    standing = [str(p.get("id")) for ps in engine.regression_probes(task_id).values() for p in ps if p.get("id")]
    out = []
    for i in named:
        hit = [s for s in standing if i in (s, s.split("#")[-1])]
        if len(hit) == 1 and hit[0] not in out:
            out.append(hit[0])
    return out


def _decided_nothing(engine, task_id, answer: dict) -> str:
    """Why an acceptance that changed and retired nothing is no decision, and the move that is one."""
    standing = [str(p.get("id")) for ps in engine.regression_probes(task_id).values() for p in ps if p.get("id")]
    named = [str(i) for i in answer.get("retire_findings") or ()]
    if unresolved := {i: [s for s in standing if i in (s, s.split("#")[-1])] for i in named}:
        return ("your acceptance retired nothing: " + "; ".join(
            f"{i} names " + (" and ".join(c) + " — name the one you rule on by its full id" if len(c) > 1 else
                             "a finding the dispute did not name — rule only on what it named" if c else
                             "no standing finding")
            for i, c in unresolved.items()) + ". Where the disputed probe is not demanded, REJECT the dispute saying so")
    return ("your acceptance changed no criterion as it will stand and retired no standing finding, so it decided "
            "nothing. Where the disputed probe is not demanded — no standing finding carries it — the dispute has "
            "nothing to take back: REJECT it saying so, and the executor delivers")


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
    return (f"Syntactic holes:\n{holes}\n\nLevel-2 findings (a `dispute` names one EXACTLY as written between "
            f"the backticks):\n" + ("\n".join(lines) or "- none")
            + (f"\n\n{own} of them (`undecided: …`) are requirements of this node's OWN goal that none of its OWN "
               f"criteria writes: no move on a child closes one — the next review names it again word for word. "
               f"`add_criterion` on this node closes them — one criterion listing the requirements of one component "
               f"closes every one it lists — and `reshape` with `map` then gives it the child that delivers them."
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


def issuer_context(engine, task_id: TaskId, question: str, refusal: str = "", laid: "dict | None" = None) -> str:
    """Everything the issuer needs to answer about `task_id`, and nothing twice: the goal, why the node exists,
    its contract, and what the question needs — for the plan and the repair, the split's whole contracts; for the
    plan, the gate's findings with their reasons and nothing of the node's history (a holder asked what its plan
    decision rested on did not use the deadline or the rework count — one decision, 4 forks,
    experiments/e3_specbench/issuer_context_probe.py); for the others, what happened to the node. NOT CARRIED,
    a named residue: the source statement a goal points to and files in the workspace — the issuer has tools
    only on a dispute (`CONTACT`), and the holder used both."""
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
        out.append("## The validator's findings standing on this node — every PASS of it must re-run them\n"
                   + (_standing_findings(engine, task_id) or "- none")
                   + ("\n\nUnder AUTO this node's criteria are the user's goal: only the user rules a finding of the "
                      "validator outside them — answer without `retire_findings`."
                      if is_auto_root(engine.graph, engine.graph.get_task(task_id)) else
                      "\n\nA finding stays demanded until you rule it outside its criterion as written: accept, naming "
                      "in `retire_findings` the id of a finding the dispute named by its id. Nothing else retires one "
                      "— not a reworded criterion, not a conceded pinned probe — and a later change of that "
                      "criterion's text ends the ruling."))
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
    out.append(f"# The question: {q['ask']}"
               + ("\n\nThis is the user's goal under AUTO: closing it is theirs, not yours — continue it with a contract "
                  "the standing findings can be met under; unanswered, it closes by its bound."
                  if "cancel" in q["moves"] and "cancel" not in moves else "")
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
    "dispute": {"ask": "the executor CHALLENGED this contract. Can the contract be met as written?",
                "moves": ("accept", "reject")},
    "escalation": {"ask": "the node is ESCALATED — its executor's contract ended without a verdict "
                          "(the trail says which route). Only you decide: a new contract, or close it.",
                   "moves": ("reassign", "cancel")},
    "repair": {"ask": "the split needs repair: contact REFUTED it (the node FAILED on criteria its children "
                      "cover while they passed — the covering child must carry what failed, or, where that "
                      "child is SETTLED, a new child must), or a confirmed dependency of a child runs against the plan's order (a "
                      "producer that cannot finish before it: drop the child that is cut wrongly and add "
                      "what replaces it, reading what it needs), or a child waits on a producer that was "
                      "cancelled (drop that Dep, and cover what it fed another way).",
               "moves": ("revise_child", "add_child", "drop_child", "reshape", "drop_dependency", "resplit")},
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
                        "(what it names is not what it needs: the record is refuted and it resumes), re-issue it "
                        "(a contract it can meet without that), or close it.",
                 "moves": ("promote", "resolve_block", "reassign", "cancel")},
}

_CRITERIA = {"type": "array", "items": {"type": "object", "properties": {
    "name": {"type": "string"}, "description": {"type": "string"},
    "check": {"type": "array", "items": {"type": "object", "properties": {
        "behaviour": {"type": "string"}, "command": {"type": "string"}, "expect": {"type": "string"},
        "inputs": {"type": "array", "items": {"type": "object", "properties": {
            "path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"]}}},
        "required": ["behaviour", "command", "expect"]}}},
    "required": ["name", "description", "check"]}}

MOVE_SCHEMA = {
    "type": "object",
    "properties": {
        "tech_report": TECH_REPORT,
        "move": {"type": "string"},
        "justification": {"type": "string", "description": "why — in terms of the contract and the goal"},
        "criteria": {**_CRITERIA, "description": "reassign / revise_child: the WHOLE criteria set as it "
                     "will then stand, kept ones unchanged and included"},
        "child_id": {"type": "string", "description": "revise_child / drop_child: which child"},
        "covers": {"type": "array", "items": {"type": "string"},
                   "description": "revise_child: this node's criteria the child carries — maps them to it"},
        "child": {"type": "object", "description": "add_child: {name, description, criteria, covers: "
                  "[this node's criterion names it carries], reads: [ids of this node's children whose "
                  "result its checks read — each becomes a Dep, so it runs after them; in a reshape, also the "
                  "name of a child the same reshape adds], replaces: [ids of children the same reshape drops that "
                  "it stands in for — their consumers then read it; a child named as the one it replaces needs "
                  "none]}; promote: {name, "
                  "description, criteria} of the producer of what the blocked node lacks"},
        "criterion": {"type": "string", "description": "dispute: the finding's criterion"},
        "items": {"type": "array", "items": {"type": "string"},
                  "description": "drop_risk / reshape: the ACCEPTED_RISKS entries (their text) that name this node's "
                                 "criteria; challenge: the contract's fields it questions (criterion names, "
                                 "`deadline`)"},
        "children": {"type": "array", "items": {"type": "object"},
                     "description": "reshape: the children added, each as `add_child`'s `child`"},
        "drop": {"type": "array", "items": {"type": "string"},
                 "description": "reshape: ids of children leaving the split (active, not settled)"},
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
        "derivations": {"type": "array", "items": {"type": "object", "properties": {
            "criterion": {"type": "string"}, "probe": {"type": "string"}, "derived_by": {"type": "string"}},
            "required": ["criterion", "probe", "derived_by"]}, "description":
            "ON ACCEPT AT THE ROOT OF AN AUTO PROJECT, for every probe you change on a criterion that stands — the new "
            "one AND the one it replaces: the criterion, the probe's command, and `derived_by` — a command that PRINTS "
            "that probe's true expected output WITHOUT running the work under test (it runs where only the probe's "
            "pinned inputs are, `{inputs}` naming them), e.g. python3 with its standard library, sqlite3 included. "
            "The new probe's must print its `expect`; the replaced one's must not print its old `expect`."},
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


def spec_with(task, criteria: list, additions_only: bool = False, repin: frozenset = frozenset()) -> Spec:
    """The node's contract with its criteria as the answer states them — merged BY NAME onto the stored
    ones, so what the answer does not speak to (Dep glue, composition, pinned inputs) is carried, not
    silently dropped. A criterion the answer leaves out is dropped, except the engine-authored Dep glue.
    `additions_only`: every stored criterion's text stands exactly and none is dropped; the answer adds new names, and
    re-pins the check of a criterion named in `repin` — the ones a dispute questioned — never with fewer probes. The
    procedure is the issuer side's instrument, not the user's word: a probe its own criterion's text refutes was
    re-written eight times and dropped each time until the root closed by count (AUTO haiku sql_database, root
    «Comment handling», 2026-10-14); and the same answers restated every other criterion, one of them 3 probes → 1."""
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
    """Is this party the user-agent holding its part of the tree (SOLO/SEMI) — whose moves the system
    never makes for it?"""
    return party_kind(engine.graph, party) in ("holder", "legacy")


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


def _same(a: str, b: str) -> bool:
    """Equal as a check reads a printed output: written `\\t`/`\\n` escapes as the characters, whitespace runs as one."""
    u = lambda s: " ".join(s.replace("\\t", "\t").replace("\\n", "\n").split())
    return u(a) == u(b)


def _derived(command: str, criterion, probe, execution=None) -> tuple[Optional[str], str]:
    """(what the command printed, '') run in an EMPTY place holding only the probe's pinned inputs — where the project's
    work runs, so a value is derived on the platform its check is decided on — or (None, why it could not run — with
    its exit code and the tail of its stderr, so the next answer knows what to change)."""
    ex = execution or LocalExecution()
    if not (bash := ex.shell()):
        return None, "could not run: no `bash` here"
    with ex.scratch("gfso-derive-") as tmp:
        try:
            laid = materialize_inputs((criterion,), Path(tmp) / "inputs")
        except ValueError as e:
            return None, f"could not lay down the probe's inputs ({e})"
        cmd = command.replace(INPUTS_TOKEN, laid.get(probe_id(criterion.name, probe), Path(tmp)).as_posix())
        try:
            p = ex.run([bash, "-c", cmd], cwd=tmp, timeout=DERIVE_TIMEOUT_S)
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
    its own check, verifier = executor in substance (§10.3, d6 §4.1). So each re-pinned probe names `derived_by`, a
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

    for c in new_spec.criteria:
        if c.name not in old:
            continue
        now, was = {pair(p) for p in c.check or ()}, old[c.name].check or ()
        for p in (p for p in c.check or () if pair(p) not in {pair(q) for q in was}):
            if (out := derive(c, p, "the expectation it pins")) is not None and not _same(out, p.expect):
                wrong.append(f"«{c.name}» `{p.command[:80]}`: its derivation prints {out.strip()[:200]!r}, not the "
                             f"expectation {p.expect[:200]!r}")
        # …AND THE PROBE IT REPLACES WAS WRONG: a new command can be honestly derived and still check a narrower thing
        # (critic's live replay: `WHERE salary > 55000.0` after a raise, Bob only, the Alice row out of the check)
        for q in (q for q in was if pair(q) not in now):
            if (out := derive(c, q, "the user's probe it replaces must be shown wrong")) is not None \
                    and _same(out, q.expect):
                wrong.append(f"«{c.name}» `{q.command[:80]}`: the probe it replaces was right — its derivation "
                             f"prints its expectation {q.expect[:200]!r}")
    return ("under AUTO a re-pinned expectation of the user's goal is shown by a derivation that does not run the "
            "delivery (`derivations`: the criterion, the probe's command, and `derived_by` — e.g. python3 with its "
            "standard library, sqlite3 included); the system runs it with only the pinned inputs and finds: "
            + "; ".join(wrong)) if wrong else None


def seam_keeping_executor(engine, task, another: bool) -> Optional[AgentId]:
    """An executor for a re-issued node that keeps every seam around it: from this project's pool,
    not its parent's Del, not any child's Del — else a node would verify itself or its own work."""
    parent = engine.graph.get_task(task.parent_id) if task.parent_id else None
    ok = engine.seam_keepers(parent.assignee if parent else None, task.id)
    if not another and str(task.assignee) in {str(a) for a in ok}:
        return task.assignee
    return ([a for a in ok if str(a) != str(task.assignee)] or ok or [None])[0]


def what_can_change(engine, task) -> str:
    """What a next contract may change once re-issues are spent — the executor only where another keeps the seams: at a
    root, whose pool is its own executor and its children's, the hint sent the issuer after a move refused every time
    (finder over 190f4db)."""
    other = seam_keeping_executor(engine, task, True)
    return ("the criteria, the executor (`another_executor`) or the rework budget (`max_iterations`)"
            if other is not None and str(other) != str(task.assignee) else
            "the criteria or the rework budget (`max_iterations`) — no other executor keeps this node's seams")


def extensions_spent(engine, task) -> bool:
    """Are the AUTO root's re-issues out of ESCALATED spent (`MAX_EXTENSIONS`)? Below the AUTO root never (§12.15): the
    one rule `settle` tells the issuer and `_reassign` holds it to."""
    return is_auto_root(engine.graph, task) and extensions_granted(engine, task.id) >= MAX_EXTENSIONS


def extensions_granted(engine, task_id: TaskId) -> int:
    """How many contracts this issuer RE-issued for this node (`_reassign`), across generations — kept
    with the project where the move is made. A plan repair is not a re-issue and does not spend this; a
    budget reset by the move it bounds bounds nothing (a leaf cut at its turn cap looped park → re-issue)."""
    return engine.tally(f"reissue:{task_id}")


# === The moves — each one the canon gives the mover in that state, checked before it is made ===

def _signalled(engine, task_id, sig, actor, **kw) -> tuple[bool, str]:
    why: list = []
    return signal_ok(engine, task_id, sig, actor, why, **kw), "; ".join(why)


def _cancel(engine, task, actor, answer, why, verbs):
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


def _changes_what_failed(task, spec, to, budget) -> bool:
    """Does this re-issue change more than the date — the criteria, the executor it will REALLY have, or the budget as
    clamped? Asked of the request, `another_executor` with nobody else to take it and a budget past the cap passed as
    changes while nothing changed (critic r2, F2)."""
    return spec.criteria != task.spec.criteria or str(to) != str(task.assignee) or budget != task.max_iterations


def _reassign(engine, task, actor, answer, why, verbs):
    spec = spec_with(task, answer["criteria"], additions_only=users_criteria(engine.graph, task)) \
        if answer.get("criteria") else task.spec
    if bad := narrowing_at_the_root(engine, task, spec):
        return False, bad
    to = seam_keeping_executor(engine, task, bool(answer.get("another_executor")))
    budget = min(max(1, int(answer.get("max_iterations") or task.max_iterations)), MAX_REWORK_BUDGET)
    # …AT THE AUTO ROOT ONLY: below it the parent's deadline bounds every re-issue (`Schedule`), and §12.15 counts no
    # re-ASSIGN out of ESCALATED; at the AUTO root nothing above bounds the machine standing in for the user's patience
    if extensions_spent(engine, task) and not _changes_what_failed(task, spec, to, budget):
        return False, (f"{MAX_EXTENSIONS} contracts were already written for this node and none reached a verdict: "
                       f"another must change what failed — {what_can_change(engine, task)} — not only the date; or "
                       f"close it with the reason")
    if to is None:
        return False, "no executor of this project keeps the seams around this node"
    want = project_now(engine.graph) + timedelta(hours=min(MAX_EXTEND_HOURS, max(1.0, float(answer.get("extend_hours") or 24))))
    # INSIDE the parent's deadline, BEFORE its consumers' and AFTER its producers' along Dep (§4.5 item 6, §2.7) — the
    # one writer of ordered deadlines (`Schedule`): written on the parent's, two Dep-linked siblings re-issued got one
    # equal deadline (critic r7, B2); re-issued before its producer, a consumer lapsed again. No ordered one ahead — the
    # parent already due — the issuer types the one it wants (§2.5), the crossing flagged (§12.10).
    parent = engine.graph.get_task(task.parent_id) if task.parent_id else None
    deadline = Schedule(engine.graph, parent, {str(task.id): (None, producers_of(spec), None)}, want=want).defaults()[
        str(task.id)] or want
    # TYPED (§15.6 dial 3 — the cause is the issuer's to give): a re-issue out of ESCALATED is routine, and a change
    # of executor to keep the seams is no capability mismatch; untyped, every machine re-issue counted against q_Del
    # (sync audit, C-F3). A criteria change here answers no spec defect the machine could name.
    engine.revise(task.id, spec, AgentId(actor), deadline=deadline, max_iterations=budget,
                  reason=_cause(answer, RevisionReason.SPEC_DEFECT, RevisionReason.SCOPE_EXPANSION)
                  if spec.criteria != task.spec.criteria else RevisionReason.OTHER)
    engine.tally(f"reissue:{task.id}", add=1)
    if str(to) != str(task.assignee):
        engine.reassign(task.id, to, reason=_cause(answer, RevisionReason.CAPABILITY_MISMATCH))
    return True, ""


def _revise_child(engine, task, actor, answer, why, verbs):
    child = engine.graph.get_task(TaskId(_child_ref(engine, task, answer.get("child_id"))))
    if child is None or str(child.parent_id) != str(task.id):
        return False, f"`{answer.get('child_id')}` is not a child of {task.id}"
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
    spec = spec_with(child, answer["criteria"]) if answer.get("criteria") else child.spec
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
    child = engine.graph.get_task(TaskId(_child_ref(engine, task, answer.get("child_id"))))
    if child is None or str(child.parent_id) != str(task.id):
        return False, f"`{answer.get('child_id')}` is not a child of {task.id}"
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
    """One child `cid` for a re-admission of `task`'s split, as `decompose` takes it: its criteria with the Dep seams
    of the siblings it `reads`, the node's criteria it `covers`. (None, why) refused. `reads` names a standing child,
    or what `ids` resolves — a child the same act creates, by its name, and one it drops, to what replaces it."""
    covers = [x for x in (c.get("covers") or []) if x in {k.name for k in task.spec.criteria}]
    if not (c.get("criteria") and covers):
        return None, "a new child carries criteria and names which of this node's criteria it covers"
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
    seams = [{"name": f"dep__{r.rsplit('.', 1)[-1]}", "description": f"reads {r}'s result", "depends_on": r}
             for r in reads]
    return {"task_id": cid, "covers": covers, "spec": {
        "name": c.get("name", ""), "description": c.get("description", ""),
        "criteria": [with_named_files(_with_corpora(x, _corpora(engine, task)), _files_of(engine, task))
                     for x in c["criteria"]] + seams,
        **({"accepted_risks": c["accepted_risks"]} if c.get("accepted_risks") else {})},
        **{k: c[k] for k in ("deadline", "max_iterations") if c.get(k)}}, ""


def _corpora(engine, task) -> dict:
    """{(criterion, command): its files} of every probe this node or a child of its split pinned over a corpus — the
    issuer side's own; a child carrying one of the node's own criteria re-writes its probe (critic r5) — and
    {(None, command): …} where every such pin of the command reads one corpus."""
    pins = [(c.name, " ".join(p.command.split()), p.to_dict()["inputs"])
            for k in [task, *engine.graph.get_children(task.id)] for c in k.spec.criteria for p in (c.check or ())
            if p.inputs]
    by_cmd: dict = {}
    for _, cmd, files in pins:
        by_cmd.setdefault(cmd, []).append(files)
    return {**{(None, cmd): fs[0] for cmd, fs in by_cmd.items() if all(f == fs[0] for f in fs)},
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


def _readmit(engine, task, answer) -> tuple[bool, str]:
    """The one re-admission behind `reshape`, `add_child` and `drop_child`. A child it drops and replaces — the new
    child named as it was, or naming it in `replaces` — hands its consumers to the replacement (`_repointed`)."""
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
        kids.append(kid)
    kids += _repointed(engine, task, replaced, leaving)
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
    try:
        out = _tools.decompose(engine, str(task.id), kids, drops=drop,
                               mappings=[{"criterion_name": c, "child_id": k} for k, cs in remap.items() for c in cs],
                               **({"accepted_risks": [n.to_dict() for n in kept],
                                   "risk_components": list(register.components)} if asked else {}))
    except ValueError as e:
        out = {"error": str(e)}
    bad = [str(o["error"]) for o in (out if isinstance(out, list) else [out]) if isinstance(o, dict) and o.get("error")]
    # …AND WHAT EACH REPLACEMENT CARRIES ON: the dropped children's work (`carried_work`) and their standing findings,
    # each under the names its criterion has in the replacement
    onto = {cid: c.get("onto") or {} for c, cid in zip(named, cids)}
    for d, cid in ([] if bad else replaced.items()):
        engine.record_replacement(TaskId(cid), [d])
        if n := engine.carry_findings(TaskId(cid), TaskId(d), onto[cid].get(d, {})):
            engine.emit_info("issuer", f"{cid}: carries {n} finding(s) standing on {d}, which it replaces")
    # …said in this issuer's own moves: the refusal names the tool door's verbs, and the whole act here is one reshape
    return (not bad, "; ".join(bad) + (" — as this node's issuer: everything the split needs in ONE `reshape` "
                                       "(`children`, `drop`, `items`, `map`)" if bad else ""))


def _repointed(engine, task, replaced: dict, leaving: frozenset) -> list[dict]:
    """Each unsettled child standing in the split that consumes one `replaced` takes out, named again in the same act
    with its seams onto the replacement — its issuer's revision of his own child. Left on the dropped producer it waited
    on a cancelled node and starved, a repair nobody needed. Seams onto one producer collapse to one; its deadline and
    rework bound ride as they stand (`deadlines_the_act_sets` keeps a re-issued child's that still fits)."""
    out = []
    for k in engine.graph.get_active_children(task.id):
        if (str(k.id) in leaving or k.state in (State.DONE, State.ABANDONED, State.CANCELLING)
                or not any(str(c.depends_on) in replaced for c in k.spec.criteria if c.depends_on)):
            continue
        crits = _onto_once(str(k.id), _tools.task_out(k, engine, plan=False)["criteria"], replaced)
        out.append({"task_id": str(k.id), "assignee": str(k.assignee), "spec": {"criteria": [c for _, c in crits]}})
    return out


def _onto_once(owner: str, crits: list, onto: dict, skip=frozenset(), seen: set | None = None) -> list[tuple]:
    """(owner, criterion) for `crits` as `task_out` gives them, each seam moved by `onto` (producer → its stand-in),
    a seam onto `skip` dropped, and one producer read once (across calls sharing `seen`)."""
    seen, out = set() if seen is None else seen, []
    for c in crits:
        dep = onto.get(str(c["depends_on"]), str(c["depends_on"])) if c["depends_on"] else None
        if dep in skip or (dep and dep in seen):
            continue
        if dep:
            seen.add(dep)
        out.append((owner, {**c, "depends_on": dep}))
    return out


def _merged(engine, task, members: list[str]) -> dict:
    """The one child that carries a refuted cycle's `members` (§15.5: two units that each need the other are one): their
    criteria BY REFERENCE, as `task_out` gives them — check with its inputs, composition, seams — their seams onto one
    another dropped and onto any one producer kept once, a name two members share told apart by its member's; the
    node's criteria they were mapped to; `replaces` them, so their consumers are handed to it in the same act and their
    work is its start (`carried_work`). Its terms are the members' widest, the work being theirs together: the latest of
    their live deadlines, the largest rework bound, every risk their packets set aside. `onto` says where each member's
    criterion went, for its standing findings (`carry_findings`): a seam onto another member, dropped, to every
    criterion of the member's own it carries — the integration it asked for is now that work's — or, where it has
    none, to those of the members that read it, else to every criterion of the merged child; a seam onto a producer
    another member's seam already reads, to that seam."""
    kids = [engine.graph.get_task(TaskId(m)) for m in members]
    short = {m: m.rsplit(".", 1)[-1] for m in members}
    seen: set = set()
    crits = [x for k in kids for x in _onto_once(str(k.id), _tools.task_out(k, engine, plan=False)["criteria"], {}, set(members), seen)]
    names = [c["name"] for _, c in crits]
    renames: dict = {}
    for m, c in crits:
        if names.count(c["name"]) > 1:
            renames.setdefault(m, {})[c["name"]] = f"{c['name']} ({short[m]})"
    final = {(m, c["name"]): renames.get(m, {}).get(c["name"], c["name"]) for m, c in crits}
    reads = {c["depends_on"]: final[(m, c["name"])] for m, c in crits if c["depends_on"]}
    whole = {m: _tools.task_out(k, engine, plan=False)["criteria"] for m, k in zip(members, kids)}
    own = {m: [final[(x, c["name"])] for x, c in crits if x == m and not c["depends_on"]] for m in members}
    # a member all of whose criteria read other members: its work feeds the members that read it, and failing those,
    # the merged child as a whole — never a name the merged child lacks
    fed = {m: own[m] or [n for x in members if any(str(c["depends_on"]) == m for c in whole[x]) for n in own[x]]
           or list(final.values()) for m in members}
    onto: dict = {}
    for m in members:
        for c in whole[m]:
            dep = str(c["depends_on"]) if c["depends_on"] else None
            onto.setdefault(m, {})[c["name"]] = ([final[(m, c["name"])]] if (m, c["name"]) in final
                                                 else fed[m] if dep in members else [reads[dep]])
    due = max((k.deadline for k in kids if k.deadline and k.deadline > project_now(engine.graph)), default=None)
    return {"deadline": due, "max_iterations": max(k.max_iterations for k in kids),
            "accepted_risks": list({n.item: n.to_dict() for k in kids for n in k.spec.accepted_risks}.values()),
            "name": "_".join(short[m] for m in members),
            "description": "\n\n".join(f"{short[str(k.id)]}: {k.spec.description}" for k in kids),
            "criteria": [{**c, "name": renames.get(m, {}).get(c["name"], c["name"])} for m, c in crits],
            "covers": list(dict.fromkeys(m.criterion_name for m in task.criterion_mappings
                                         if str(m.child_id) in members)),
            "replaces": list(members), "onto": onto}


def merge_the_refuted_cycle(engine, task, actor: str) -> Optional[dict]:
    """The canon's one restoring move for a dependency order contact refuted (§15.5: a re-decomposition), made by the
    system where the split is a system executor's: the children on each refuted cycle merged into one, in ONE
    re-admission. None where it is not this move's — no refuted order, a holder's split, a cycle through a done child
    or one no merge of children closes (a block naming its own ancestor) — and the question goes on to its mover.

    Asked of a model, it was not made: GB_c_compiler_tmp5cb096's root, its pp and libc each needing the other, took six
    repairs from its machine issuer, every one refused, and was cancelled with 8 of its 10 parts passed. Nothing in the
    move is a judgement — which children, their criteria, what they covered and who consumes them are the graph's."""
    if held_by_a_holder(engine, str(task.assignee)) or not engine.dep_order_refuted(task.id):
        return None
    groups = engine.dep_order_cycle_children(task.id)
    if not groups or any(engine.graph.get_state(TaskId(m)) == State.DONE for g in groups for m in g):
        return None
    # A MEMBER'S DELIVERY AWAITING ITS VERDICT IS WORK IN HAND (§12.16 (ii)): dropped now, it would be voided unread;
    # the move waits for the verdict — uncounted, backed off — and the question is asked again after it
    if busy := sorted(m for g in groups for m in g if engine.graph.get_state(TaskId(m)) == State.VALIDATING):
        return {"status": "waiting", "why": f"{', '.join(busy)} delivered and await a verdict; the merge follows it"}
    ok, why = _readmit(engine, task, {"drop": [m for g in groups for m in g],
                                      "children": [_merged(engine, task, g) for g in groups]})
    engine.emit_info("issuer", f"{task.id}: contact refuted its split's order — "
                     + "; ".join(" + ".join(g) for g in groups) + " each wait on the other; merged into one child by "
                     f"the system, {actor} (§15.5)" + ("" if ok else f" — REFUSED: {why}; the question goes to its mover"))
    return {"status": "applied", "move": "merge"} if ok else None


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
    ok, bad = _add_child(engine, parent, actor, {"child": {**(answer.get("child") or {}), "covers": covers, "reads": [],
                                                           **({"deadline": made_by} if made_by else {})}},   # a datetime on the project's clock, not a typed date
                         why, verbs)
    if not ok:
        return False, bad
    made = next(str(k.id) for k in engine.graph.get_active_children(parent.id) if str(k.id) not in before)
    engine.add_dependency(TaskId(made), task.id, glue=f"{task.id} was blocked on what {made} produces: {why}")
    return True, ""


def _add_criterion(engine, task, actor, answer, why, verbs):
    """An obligation of the node's goal that no criterion decides (FM-1.f) is closed by ADDING the
    criterion — an act of the node's ISSUER on its contract, append-only: nothing standing changes."""
    issuer = str(engine.graph.issuer_of(task.id))
    if held_by_a_holder(engine, issuer):
        return False, (f"adding to {task.id}'s contract is its issuer's move ({issuer}), not the system's — a requirement "
                       f"its criteria do not write (FM-1.f, §9.4) is reported to him: `challenge`")
    if not answer.get("criteria"):
        return False, "name the criterion to add (`criteria`), with its pinned check"
    new = [c for c in answer["criteria"] if c.get("name") not in {k.name for k in task.spec.criteria}]
    if not new:
        return False, "every criterion named already stands; adding means a NEW name"
    spec = dataclasses.replace(task.spec, criteria=task.spec.criteria + tuple(
        Criteria(c.get("name", ""), c.get("description", ""), check=_checks_of(c)) for c in new))
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


def _dispute(engine, task, actor, answer, why, verbs):
    if is_auto_root(engine.graph, task) and loose_finding_key(str(answer.get("criterion") or "")
                                                                ).replace(" ", "").startswith("undecided:"):
        return False, ("under AUTO an obligation of the user's goal that no criterion decides is closed by "
                       "ADDING the criterion (`add_criterion`) — the user's goal is not argued away")
    key = str(answer.get("criterion") or "")
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
    if refused_by_limit(out.get("stats")):
        raise Unavailable("the account's usage limit refused the refine round", limit=True)
    return not out.get("error"), str(out.get("error") or "")


def moves_for(engine, task, question: str) -> tuple:
    """The moves this question admits on THIS node: `drop_dependency` only where a child waits on a cancelled
    producer — offered on a dependency-order refutation it could never land, and an AUTO issuer spent four answers on
    it while the one move that could (a re-decomposition, §15.5) went unasked (GB_c_compiler_tmp5cb096).

    No `cancel` at an AUTO root: CANCEL is the refusal of the task (§11.2), and the goal is the user's — the system
    moving for them continues it by a re-ASSIGN, and silence closes it by its bound (§12.5). A machine issuer
    cancelled one "all 22 criteria pass" over the standing FAIL that escalated it (GB_sql_database_tncfrm404)."""
    moves = QUESTIONS[question]["moves"]
    if "drop_dependency" in moves and task is not None and not any(
            _cancelled_producers(engine, k) for k in engine.graph.get_active_children(task.id)):
        moves = tuple(m for m in moves if m != "drop_dependency")
    if "cancel" in moves and is_auto_root(engine.graph, task):
        moves = tuple(m for m in moves if m != "cancel")
    # …nor `promote` into a plan the user handed in: a node it adds is a split the user did not make
    if "promote" in moves and users_plan(engine.graph):
        moves = tuple(m for m in moves if m != "promote")
    return moves


def _drop_dependency(engine, task, actor, answer, why, verbs):
    """A child consuming a producer that was cancelled waits on something that will never come: its
    issuer drops that Dep (the plan changes; the child then works or is re-planned by the next question)."""
    child = engine.graph.get_task(TaskId(_child_ref(engine, task, answer.get("child_id"))))
    if child is None or str(child.parent_id) != str(task.id):
        return False, f"`{answer.get('child_id')}` is not a child of {task.id}"
    if not (gone := _cancelled_producers(engine, child)):
        return False, f"{child.id} consumes no cancelled producer"
    for producer in gone:
        _tools.remove_dependency(engine, producer, str(child.id))
    return True, ""


def _resplit(engine, task, actor, answer, why, verbs):
    """Re-issue the node's own contract unchanged: its split then drops the mappings to children that
    were cancelled, so what they covered becomes an honest coverage hole a new child can fill (the
    re-issue is the node's issuer's act, and its executor consents afresh)."""
    issuer = str(engine.graph.issuer_of(task.id))
    if held_by_a_holder(engine, issuer):
        return False, f"re-issuing {task.id} is its issuer's move ({issuer}), not the system's"
    live = {str(k.id) for k in engine.graph.get_active_children(task.id)}
    if not any(str(m.child_id) not in live for m in task.criterion_mappings):
        return False, ("no mapping points at a child that is gone — a re-issue would prune nothing; to reshape "
                       "the split, `drop_child` the child that is wrongly cut first")
    engine.revise(task.id, task.spec, AgentId(issuer), reason=RevisionReason.OTHER)
    return True, ""


MOVES = {"cancel": _cancel, "drop_dependency": _drop_dependency, "drop_child": _drop_child, "resplit": _resplit, "resolve_block": _resolve_block, "reassign": _reassign, "promote": _promote,
         "add_criterion": _add_criterion, "drop_risk": _drop_risk,
         "revise_child": _revise_child, "add_child": _add_child, "reshape": _reshape, "dispute": _dispute,
         "refine": _refine, "challenge": _challenge}


def apply_move(engine, task_id: TaskId, question: str, actor: str, answer: dict,
               verbs: "Verbs | None" = None) -> tuple[bool, str]:
    """Carry out ONE answer, or say why it is refused. Returns (done, why-not)."""
    move, task = str(answer.get("move") or ""), engine.graph.get_task(task_id)
    if move not in (admissible := moves_for(engine, task, question)) or move not in MOVES:
        return False, f"`{move}` is not a move for this question; admissible: {admissible}"
    try:
        return MOVES[move](engine, task, actor, answer,
                           str(answer.get("justification") or "").strip(), verbs)
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
    with ((ex or LocalExecution()).scratch("gfso-issuer-inputs-") if where else contextlib.nullcontext()) as tmp:
        laid = materialize_inputs(engine.graph.get_task(task_id).spec.criteria, tmp) if tmp else {}
        packet = issuer_context(engine, task_id, question, refusal, laid) + schema_instruction(schema)
        with (verbs.busy("issuer_turn", engine, task_id) if verbs else contextlib.nullcontext()):
            if where:
                text = llm.run_agent(PROMPT.read_text(encoding="utf-8"), CONTACT.format(where=where, checkout=checkout_note(where)) + packet,
                                     allowed_tools=CONTACT_TOOLS, cwd=where, timeout=CONTACT_TIMEOUT_S)
            else:
                # the ZERO-TOOL port: an issuer reads the packet and answers; `run_agent` without a working
                # directory refused every real call, so no machine issuer ever answered (hidden by fakes that
                # accepted the missing argument)
                text = llm.complete(packet, context=PROMPT.read_text(encoding="utf-8"))
    llm.tag_last(Stage.ISSUER)
    engine.record_llm_usage(Stage.ISSUER, llm, task_id)
    if failed := unanswered(llm.calls[-1:]):
        raise failed
    if not str(text or "").strip():
        raise Unavailable("the model call returned nothing")
    if where and the_call_was_cut(llm, str(text)):   # an agent run of minutes is where calls are severed (critic 8)
        raise Unavailable("the contact run was cut before it answered")
    file_tech_reports(engine, answer := parse_structured(text, schema), "issuer", actor, task_id)
    return _unlaid(answer, [d.as_posix() for d in laid.values()]), dict(llm.last_tool_calls) if where else None


def _unlaid(x, dirs: list):
    """The answer with every directory the inputs were laid down in named `{inputs}` again — the contract pins the
    files, not one turn's temporary place."""
    if isinstance(x, str):
        for d in dirs:
            x = x.replace(d, INPUTS_TOKEN)
        return x
    if isinstance(x, list):
        return [_unlaid(v, dirs) for v in x]
    return {k: _unlaid(v, dirs) for k, v in x.items()} if isinstance(x, dict) else x


def _ran_a_shell(ran: dict) -> bool:
    return any(str(k).split("(")[0].strip() == "Bash" for k in ran)


#: Said wherever a dispute at an AUTO root asks to rule a finding out of the user's goal (`Engine.users_dispute`).
_USERS_DISPUTE = ("{0}'s dispute asks to rule {1} outside the user's goal, and under AUTO only the user makes that ruling "
                  "(§10.1): answer it without `retire_findings` — REJECT_CHALLENGE, the finding staying demanded, with "
                  "what the executor must do to meet it, or ACCEPT_CHALLENGE with criteria you add. Your ruling was not "
                  "made; the user's door to it stays open.")


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
    retire = _standing_ids(engine, task_id, [str(i) for i in (answer or {}).get("retire_findings") or ()])
    # the ruling lands what the dispute named; the rest stays demanded and the executor may dispute it by name. Refused
    # whole, the same four ids were ruled on three times and the part closed by count (root.tr, 2026-10-12)
    said = findings.named(engine.challenge_reason(task_id) or "", [s for ps in engine.regression_probes(task_id).values()
                                                                    for p in ps if (s := p.get("id"))])
    retire = [i for i in retire if i in said]
    if answer is None or decision not in ("accept", "reject"):
        # an acceptance names the contract it installs; falling through to a rejection would send the
        # executor back carrying a justification written to mean the issuer AGREED with him
        _cb(f"{task_id}: the issuer's adjudication decided nothing — the dispute stands")
        return {"task_id": str(task_id), "status": "unparsed"}
    # …AND A RULING THAT RETIRES A FINDING IS HELD TO THE SAME CONTACT: it takes back an observation of the work, and
    # an answer that ran nothing is a guess either way (critic over 28bd5e7)
    if (decision == "reject" or retire) and ran is not None and not _ran_a_shell(ran):
        # the dispute is not adjudicated yet: the question stands, asked again after its backoff
        return {"task_id": str(task_id), "status": "uncontacted",
                "why": f"the {'rejection' if decision == 'reject' else 'ruling on the findings'} ran nothing: run the "
                       f"disputed checks in the workspace and decide on what they show, quoting each command and its "
                       f"output"}
    if decision == "reject":
        ok, why = _signalled(engine, task_id, Signal.REJECT_CHALLENGE, issuer_id,
                             justification=str(answer.get("justification", "")) or "the contract stands")
        engine.emit_info("issuer", f"{task_id}: dispute {'REJECTED' if ok else 'reject REFUSED'} by {issuer_id}")
        return {"task_id": str(task_id), "status": "rejected" if ok else "refused", "why": why}
    if retire and (asked := engine.users_dispute(task_id)):
        # …THE RULING, NOT THE DISPUTE, IS THE USER'S: the system still rejects it or adds to the contract — a rejection
        # is read first, a stray ruling beside it ignored. Barred from every move, the root sat CHALLENGED on a dispute
        # that only said the findings could not be met, until the run's ceiling (GB_sql_database_tn03ao788, 2026-10-16)
        return {"task_id": str(task_id), "status": "users", "why": _USERS_DISPUTE.format(task_id, ", ".join(asked))}
    try:
        # …below an AUTO root, a node of the user's plan takes additions only — no re-pin: its expected outputs are the
        # user's, and one re-pinned to what the build printed contradicted the root's own (GB_sql_database_tne9fg736)
        spec = (spec_with(task, answer["criteria"], additions_only=users_criteria(engine.graph, task),
                          repin=questioned(engine, task) if is_auto_root(engine.graph, task) else frozenset())
                if answer.get("criteria") else task.spec)
    except Exception as e:                              # noqa: BLE001 — a malformed contract is refused
        return {"task_id": str(task_id), "status": "refused", "why": f"the corrected contract is malformed: {e}"}
    # an acceptance that changes no criterion as it will stand and retires no standing finding answers nothing:
    # re-offered unchanged, it was challenged again ten times and the part closed by count (AUTO haiku coreutils,
    # root.build, 2026-10-12) — the criteria echoed back as they stand included (11 of them, same row)
    if not retire and {c.name: c for c in spec.criteria} == {c.name: c for c in task.spec.criteria}:
        _cb(f"{task_id}: the issuer's acceptance changed nothing and retired nothing — the dispute stands")
        return {"task_id": str(task_id), "status": "unparsed", "why": _decided_nothing(engine, task_id, answer)}
    # …AND IT MAY DROP ONLY WHAT THE DISPUTE QUESTIONED (§14.3's FM-2 answer removes one of two that
    # cannot both hold) — at the root under AUTO, nothing at all.
    asked = norm_words(engine.challenge_reason(task_id) or "")
    dropped = [c.name for c in task.spec.criteria if c.name not in {k.name for k in spec.criteria}]
    if unasked := [n for n in dropped if norm_words(n) - asked]:
        _cb(f"{task_id}: the adjudication would DROP {', '.join(unasked)}, which the dispute never "
            f"questioned — refused")
        return {"task_id": str(task_id), "status": "would_narrow", "dropped": unasked}
    if bad := (narrowing_at_the_root(engine, task, spec)
               or underived_at_the_root(engine, task, spec, answer, where, _execution(engine, verbs))):
        return {"task_id": str(task_id), "status": "would_narrow", "why": bad, "dropped": dropped}
    # the ruling rides the acceptance — one act, refused whole where it may not be made (`validation.ruling_refusal`)
    ok, why = _signalled(engine, task_id, Signal.ACCEPT_CHALLENGE, issuer_id, new_spec=spec,
                         retire_findings=tuple(retire), justification=str(answer.get("justification") or "") or None)
    # …WITH ITS REASON: 35 refusals of one node's acceptance (GB_sql_database_tn8rdk788 `value`, 180 min of re-challenges)
    # left the log saying only "REFUSED", and why could not be read back from the row
    engine.emit_info("issuer", f"{task_id}: dispute {'ACCEPTED' if ok else 'accept REFUSED'} by {issuer_id}"
                               + ("" if ok else f" — {str(why)[:400]}"))
    return {"task_id": str(task_id), "status": "accepted" if ok else "refused", "why": why}


def issuer_turn(engine, task_id: TaskId, question: str, actor: str, verbs: "Verbs | None" = None,
                refusal: str = "", _llm=None, where: "str | None" = None) -> dict:
    """ONE issuer answer: assemble, ask, check, act. `where` — the node's workspace — is the answer's contact."""
    if question == "dispute":
        out = answer_the_challenge(engine, task_id, actor, _llm, refusal=refusal, verbs=verbs, where=where)
        return {**out, "status": "applied" if out["status"] in ("accepted", "rejected") else out["status"]}
    ep = episode(engine.graph.get_task(task_id))
    answer, _ = _ask(engine, task_id, question, actor, MOVE_SCHEMA, refusal, verbs, _llm, where)
    if answer is None:
        return {"status": "unparsed", "why": "the answer was not one JSON object by the schema"}
    if not _still_open(engine, task_id, question, ep):
        return {"status": "gone"}
    done, why = apply_move(engine, task_id, question, actor, answer, verbs)
    engine.emit_info("issuer", f"{task_id}: {actor}, on {question} — {answer.get('move')}"
                     + (f": {str(answer.get('justification'))[:200]}" if done else f" REFUSED: {why}"))
    return {"status": "applied" if done else "refused", "move": answer.get("move"), "why": why}


# === What the graph waits on, and who answers ===

#: The order in which one node's questions are asked — ONE at a time per node, so an escalation's
#: CANCEL and a plan repair never race on the same subtree.
PRIORITY = ("dispute", "escalation", "external", "parked", "repair", "split", "plan")

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
        kids = engine.graph.get_active_children(t.id)
        if t.state in (State.OFFERED, State.EXECUTING, State.REWORKING) and system_splits(engine, t):
            qs.append("split")
        if kids and t.state not in (State.DONE, State.ABANDONED, State.CANCELLING):
            refuted = engine.decomposition_refuted(t.id)
            if (refuted and not awaits_the_plans_review(refuted) or engine.dep_order_refuted(t.id)
                    or any(_starved(engine, k) for k in kids)):
                qs.append("repair")
            elif refuted or engine.split_holes(t.id) or any(
                    k.state == State.OFFERED and engine.execution_blocked_by(k.id) for k in kids):
                qs.append("plan")
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
    issuer's (`_machine_issuer`); with NO mode set the standing agent's disputes are still answered by
    the system — the one issuer move it made before modes existed — and nothing else of it is."""
    task = engine.graph.get_task(task_id)
    if engine.mode() is None:
        # before modes, the only issuer move the system made was answering a dispute — kept exactly
        issuer = str(engine.graph.issuer_of(task_id))
        return issuer if question == "dispute" and (agents.get(issuer) is not None
                                                    or issuer == _config_agent_id()) else None
    if question in SPLIT_QUESTIONS:
        return str(task.assignee) if agents.get(str(task.assignee)) is not None else None
    if (issuer := _machine_issuer(engine, agents, task_id)) is not None:
        return issuer
    return _config_agent_id() if engine.issuer_kind(task_id, agents) == "legacy" and question == "dispute" else None


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
                                   *starved)))


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
        why = (f"the plan the user gave is refuted at {task_id} ({question}: "
               f"{what_contact_refuted(engine, task_id) or QUESTIONS[question]['ask'][:200]}) — only the user re-plans "
               f"it: hand a corrected plan as a new goal (`auto_decompose` with `spec` on a new project), or `set_mode` "
               f"(with `user_said`) to hold the plan yourself; `start_project` alone stops it here again")
        if not engine.paused():
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
    # A REFUTED ORDER IS REPAIRED BEFORE ANY MODEL IS ASKED: its one move is computed from the graph
    if question == "repair" and (out := merge_the_refuted_cycle(engine, engine.graph.get_task(task_id), actor)):
        return out
    spent = question in ("escalation", "parked") and extensions_spent(engine, engine.graph.get_task(task_id))
    # an issuer's question is about the contract against the world — what failed, what blocks — and is answered from
    # contact; the split's questions are the executor's planning over the map
    where = (verbs.place(engine, agents, task_id)
             if verbs and verbs.place and question not in SPLIT_QUESTIONS else None)
    out = issuer_turn(engine, task_id, question, actor, verbs, where=where, refusal=(
        f"{MAX_EXTENSIONS} contracts were already written for this node and none reached a verdict. Decide: a next "
        f"contract that changes what failed ({what_can_change(engine, engine.graph.get_task(task_id))})"
        + ("." if "cancel" not in moves_for(engine, engine.graph.get_task(task_id), question)
           else ", or `cancel` with the reason.") if spent else "" if question in SPLIT_QUESTIONS else refused_on_this_version(
            engine, task_id, actor)))
    if out["status"] != "applied" and _still_open(engine, task_id, question, ep):
        out = issuer_turn(engine, task_id, question, actor, verbs, where=where,
                          refusal=str(out.get("why") or out["status"]))
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


def answer_open_questions(engine, agents, claim, release, cap, verbs: Verbs, ledger: dict) -> list[str]:
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
    for task_id, question in open_questions(engine):
        task = engine.graph.get_task(task_id)
        actor = system_mover(engine, agents, task_id, question)
        gen = f"{task_id}#{task.iteration}#{task.reopens}" if task else ""   # a revision the machine makes
        # itself must not reset its own backoff
        waits, not_before, answers = ledger.get(gen, (0, 0.0, 0))
        if actor is None or task is None or now < not_before or not claim(f"q:{task_id}"):
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
                    # `w` counts the settles in a row no model answered — a transport's failures; any answer ends the
                    # run (an account's limit window left it raised for the rest of a version, every later wait doubled)
                    review = out.get("kind") == "review"
                    if st == "applied":
                        # An answer that left its question open counts toward the rate; a review (the plan's reader,
                        # not an answer to it) and a dispute do not; a question that closed starts the count over
                        counted = not review and (q != "plan" or out.get("move") != "dispute")
                        n = n + counted if (t, q) in open_questions(engine) else 0
                        ledger[g] = (0, now_ + (backoff(n - FREE_ANSWERS - 1) if counted and n > FREE_ANSWERS else 0), n)
                    elif st in UNANSWERED:
                        ledger[g] = (w + 1, now_ + ((engine.limit_wait_s() or min(backoff(w), LIMIT_RETRY_S)) if out.get("limit") else backoff(w)), n)
                    elif st == "inflight":
                        ledger[g] = (w, now_ + PACE_S, n)
                    elif st != "gone":
                        # an answer came and moved nothing: one more answer at the model's pace, its wait only past
                        # the free count — the refusal it carries is the next answer's prompt, not a reason to wait
                        n = n + (not review) if (t, q) in open_questions(engine) else 0
                        ledger[g] = (0, now_ + (backoff(n - FREE_ANSWERS - 1) if n > FREE_ANSWERS else PACE_S), n)
                    release(t, redispatch=st == "applied" and q == "dispute")
        threading.Thread(target=_run, daemon=True).start()
    return started
