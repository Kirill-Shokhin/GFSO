"""MCP tool layer — the agent's surface over the CORE upper API.

Pure functions `(engine, *args) -> JSON-able dict` so the logic is testable without the MCP transport.
Every AUTHORING tool desugars to the canonical 12-signal FSM (the lower layer is closed: no mutation
bypasses the audited protocol). The tool DOCSTRINGS are the agent's contract — they state, per tool,
which signals it desugars to, so a model never mistakes an authoring op for a new protocol primitive.
"""
from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path
import uuid

from datetime import datetime
from typing import Optional, Union

from gfso.core.types import (
    TaskId, AgentId, Spec, Criteria, AcceptedRiskItem, CriterionMapping,
    SignalData, Signal, Predictability, Action, EXECUTOR_ACTIONS, SPAWNABLE_ACTIONS, Verdict, State,
    RevisionReason, Register, register_of, settled_positive, passed,
)
from gfso.core.graph.metrics import DIAGNOSTIC_MEANS, Q_MEANS, q_T_numerator, q_V_reversed
from gfso.core.graph.model import root_of
from gfso.core.protocol.invariants import PURE_ASSENT, content_words, is_pure_assent, verdict_word
from gfso.core.protocol.procedure import (INPUTS_TOKEN, materialize_inputs, probe_id,
                                          probes_from as _checks_of)
from gfso.core.protocol.validation import P2P_SIGNALS, Role
from gfso.config import (data_dir as _data_dir, WAIT_MAX_SECONDS, WAIT_POLL_SECONDS,
                         VERDICT_FIELD_CHARS, VERDICT_RESPONSE_MULTIPLE,
                         agent_id as _config_agent_id)
from gfso.engine import Engine


# The verbs that may bring a PROJECT into existence — everything else answers "no such project"
# rather than making one. A read that creates what it reads is how an installation reached 315
# projects, one per typo (measured 2026-08-21). `set_mode` is among them: the mode is chosen BEFORE the
# plan, so on a door with no `use_project` it is the first act on a new project.
PROJECT_CREATING_VERBS = frozenset({"create_task", "auto_decompose", "decompose", "use_project", "set_mode"})

# The verbs that are not about a graph at all: the roster is ONE server-wide file, and asking it to
# name a project made `register_agent` refuse for a project that did not exist yet — while its own
# help says the roster is server-wide. A newcomer hit that as a chicken-and-egg on their first
# command (measured 2026-08-21).
PROJECTLESS_VERBS = frozenset({"register_agent", "unregister_agent", "list_agents"})


# ── serialization helpers ────────────────────────────────────────────────────

def _predictability_from(raw) -> Optional[Predictability]:
    """STD-2's three categories, named when the caller guesses wrong.

    The scale is a legal term of art (§9.3: Ordinary / Statistical / Extraordinary — how the
    burden of proof for omitting a factor is discharged), and every caller who has not read that
    chapter reaches for the obvious ladder instead. `Predictability[p.upper()]` then raised a bare
    `KeyError`, whose whole message is the offending word in quotes — `'HIGH'`, `'MEDIUM'`, `'LOW'`.
    Three separate agents hit exactly this on 2026-08-20 and each had to grep the enum out of the
    source to continue; a user without the repository simply stops. An error that names the word
    the caller typed and nothing else tells them only what they already know.
    """
    if raw is None or raw == "":
        return None
    try:
        return Predictability[str(raw).upper()]
    except KeyError:
        raise ValueError(
            f"predictability {raw!r} is not one of the three STD-2 categories (§9.3): "
            f"ORDINARY = occurs regularly in the domain, so it belongs in the DECOMPOSITION, not "
            f"in accepted_risks · STATISTICAL = P is estimable and the event is infrequent — "
            f"admissible here WITH a justification · EXTRAORDINARY = no precedent and not derivable "
            f"from known models. It is a burden-of-proof scale, not a high/medium/low one.") from None


def _accepted_risks_from(items: list) -> tuple[AcceptedRiskItem, ...]:
    # predictability verdict (ORDINARY/STATISTICAL/EXTRAORDINARY) is MANDATORY per factor on a decomposed
    # node (CHECK-4 record form, §9.2) — plumbed here so agents can classify; a plain string stays unclassified.
    return tuple(AcceptedRiskItem.of(n, _predictability_from) for n in items)


def _dep_of(c: dict) -> Optional[TaskId]:
    """The producer this criterion consumes — ONE node, or none.

    A Dep is criteria-content (§2): the seam lives on the consumer as a criterion naming its
    producer, so two producers are two criteria, not one criterion naming two. A list here used to
    be stored verbatim and surfaced later as a Dep edge whose `from` was a list — which crashed the
    cycle check (`unhashable type: 'list'`) and took down a run mid-flight, four hours in. An
    agent's malformed input must be REFUSED at the door with a sentence it can act on, never
    accepted into the graph to fail somewhere else.
    """
    dep = c.get("depends_on")
    if dep is None or dep == "":
        return None
    if isinstance(dep, (list, tuple, set)):
        raise ValueError(
            f"criterion '{c.get('name')}': depends_on names {len(dep)} producers "
            f"({', '.join(map(str, list(dep)[:4]))}) — a Dep is carried by ONE criterion per seam "
            f"(§2), so declare one `depends_on` criterion for each producer you consume")
    if not isinstance(dep, str):
        raise ValueError(f"criterion '{c.get('name')}': depends_on must be a task id, got "
                         f"{type(dep).__name__}")
    return TaskId(dep)


#: Packet fields Inv-1 names that a SPEC dict cannot carry, and what does carry them. A change to
#: any of these is a revision (§12.3), so a caller putting one here has decided something real —
#: and the reader used to drop it without a word. Probed 2026-09-07: a revision passing a new
#: `deadline` was ACCEPTED (the node went to OFFERED, the executor re-consented) and the deadline
#: did not move. A verb that accepts a decision and discards it is worse than one that refuses.
#: `deadline` has no carrier yet at all — the parameter is missing from every authoring verb and
#: `MutateGraph(APPLY_SPEC)` has nowhere to put it — which is why this names the absence instead of
#: papering over it: half the canon's clocks (CHECK-3, §4.5 item 6) are vacuous without it.
_NOT_IN_A_SPEC = {
    "deadline": "pass it as the verb's own `deadline` argument — `revise(..., deadline=…)` moves "
                "it (Inv-1), a spec dict does not",
    "assignee": "use `reassign` — a Del change is its own revision (§12.3, counted by q_Del)",
    "del": "use `reassign`",
}


def _spec_from(d: dict) -> Spec:
    if strays := [k for k in _NOT_IN_A_SPEC if k in d]:
        raise ValueError(
            "a spec cannot carry " + ", ".join(f"`{k}` ({_NOT_IN_A_SPEC[k]})" for k in strays)
            + ". Nothing was applied: the rest of this call would have gone through and that field "
              "would have been dropped in silence.")
    crits = tuple(Criteria(c["name"], c.get("description", ""), depends_on=_dep_of(c),
                           check=_checks_of(c), composition=str(c.get("composition", "") or ""))
                  for c in d.get("criteria", []))
    # `scope` is read here, not only written back in `task_out`: without it the agent's door could
    # not express a scope BOUNDARY at all, and the only place left to put one was the risk register —
    # which CHECK-4 refuses by design (no materialization P ⟹ not a risk, §9.2). With the Syntactic
    # level gating, that was a dead end: the register the gate demands could not legally hold what the
    # agent had to declare.
    return Spec(d.get("description", ""), crits,
                _accepted_risks_from(d.get("accepted_risks", [])),
                risk_components=tuple(d.get("risk_components", ())),
                scope=tuple(d.get("scope", ())),
                name=d.get("name", ""),
                covers_risks=tuple(d.get("covers_risks", ())))


def task_out(t, engine: Optional[Engine] = None) -> Optional[dict]:
    """The node as a reader sees it — THE one shaping of a node, every door's (the HTTP door kept a second one, and the
    two drifted: a criterion's `depends_on` on one side only, the rework count and deadline on the other — D-F16). `plan_verified` is about the node's DECOMPOSITION (its Level-2
    review is current), never about the work — it used to be called `verified`, and on a leaf that
    passed its validation it read `verified: false`, which a person correctly took as an alarm about
    the RESULT. A leaf has no plan to verify, so with an engine to ask, the field is simply absent
    there rather than false."""
    if t is None:
        return None
    out = {
        "id": t.id, "name": t.spec.name, "description": t.spec.description, "state": t.state.name,
        "assignee": t.assignee, "parent_id": t.parent_id,
        "criteria": [{"name": c.name, "description": c.description,
                      "depends_on": c.depends_on,
                      # …AND THE PROCEDURE IT PINS. Left out, this door's own read-modify-write
                      # pattern DESTROYED it: a caller reads `criteria`, appends one, calls
                      # `edit_criteria` — and every pinned check is gone, the node is refused as
                      # "its own criteria pin no check", and the refusal then asks for the
                      # procedure to be authored NOW, after the work exists, which is the exact
                      # pre-registration defeat this all exists to prevent. The same class the
                      # repo already paid for with `depends_on`.
                      "check": [p.to_dict() for p in (c.check or ())],
                      # …AND THE COMPOSITION FUNCTION IT DECLARES (§2.4), for the same
                      # read-modify-write reason one line up: a field this door does not serve is a
                      # field the next `edit_criteria` silently drops.
                      "composition": c.composition}
                     for c in t.spec.criteria],
        # THE REGISTER AS RECORDED, not its item texts. `edit_accepted_risks` learned to answer this
        # in full on 2026-08-21 and every OTHER read of a node kept returning bare strings — so a
        # caller who classified a risk STATISTICAL, justified it and named its invalidation
        # condition (the classification CHECK-4 demands, and per §9.2 the only thing that makes an
        # accepted risk auditable) got back the sentence they started from, from `create_task`,
        # `get_task` and the HTTP node read alike. Three independent doors reported it in three
        # waves, each as "I cannot tell whether the rest of it was stored" (2026-09-03/04). The
        # ITEM STAYS FIRST-CLASS under its own key, because prose, the UI and every existing reader
        # use it; what is added is the rest of the record beside it.
        # the SPLIT's register — what CHECK-4/5 read (§9.2); the packet's pre-fill beside it, always: since the register
        # no longer falls back to the packet, a pre-fill shown only beside a register was readable on no other node
        "accepted_risks": [n.item for n in register_of(t).items],
        "accepted_risks_recorded": [n.to_dict() for n in register_of(t).items],
        "prefilled_accepted_risks": [n.to_dict() for n in t.spec.accepted_risks],
        "scope": list(t.spec.scope),
        # STD-3's grouped components and, on a child, which of its parent's this node covers — the
        # record CHECK-5 reads (§9.4). Neither was ever served, so the check's subject was
        # invisible from every door that could have repaired it.
        "risk_components": list(register_of(t).components),
        "covers_risks": list(t.spec.covers_risks),
        "done_reason": t.done_reason.name if t.done_reason else None,
        "iteration": t.iteration, "max_iterations": t.max_iterations, "reopens": t.reopens,
        "deadline": t.deadline.isoformat() if t.deadline else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "state_entered_at": t.state_entered_at.isoformat() if t.state_entered_at else None,
        "was_challenged": t.was_challenged,
        "criterion_mappings": [{"criterion_name": m.criterion_name, "child_id": str(m.child_id)}
                               for m in t.criterion_mappings],
    }
    # a leaf has no plan to verify, so the field is absent there; read without an engine, a node with no mapping holds no
    # split (the polled list served `plan_verified: false` on every leaf — critic O2)
    if engine.graph.get_active_children(t.id) if engine is not None else t.criterion_mappings:
        out["plan_verified"] = t.verified
        # …AND WHETHER THAT LETS THE CHILDREN START, which is the question a reader actually has.
        # `plan_verified: true` means the STRUCTURAL levels are current; a caller read it as "the
        # plan is admitted" while `review_decomposition` was answering `execution_admitted: false`
        # about the same node in the same minute, and only that verb's payload carried the
        # disclaimer (measured on the human door 2026-08-22). Two surfaces, one fact.
        if engine is not None:
            out["execution_admitted"] = engine.execution_admitted(t.id)
            if _open := engine.open_l2_findings(t.id):
                out["l2_open"] = _open
    return out


# ── READS ────────────────────────────────────────────────────────────────────

def _blocked_by(engine: Engine, t) -> Optional[dict]:
    """What a BLOCKED node is waiting for, in the node's own answer.

    "clear the blocker, then RESOLVE_BLOCK" — which blocker? `get_task` carried no reason and no
    blocker, `available_actions` listed the signal, and the only full text lived in a discovered Dep
    edge nobody had been pointed at (measured on the human door 2026-08-22). BLOCK records both
    (§11.2): the reason it gave and the nodes it named."""
    if t.state != State.BLOCKED:
        return None
    reason = next((a.reason for a in reversed(engine.audit_log(t.id))
                   if a.signal == Signal.BLOCK and not a.rejected and a.reason), "")
    on = sorted({str(e.from_id) for e in engine.get_dependencies() if str(e.to_id) == str(t.id)
                 and e.discovered})
    # …AND "CLEARS BY ITSELF" ONLY WHERE IT DOES (`Engine.block_clears_itself`): a block naming what cannot
    # finish before it, or held to after an answer, was told to wait for producers that never pass
    return {"reason": reason or "(the executor named none)", "waits_on": on,
            "what_now": (f"finish {', '.join(on)} — when they pass, the block clears by itself"
                         if on and engine.block_clears_itself(t) else
                         f"no producer finishing clears it: {engine.order_refuted_by(t.id) or 'see the reason'} "
                         f"— its issuer answers it (RESOLVE_BLOCK, a re-ASSIGN, or CANCEL, §12.13)" if on
                         else "clear what the reason names, then RESOLVE_BLOCK (the issuer's signal, §12.4)")}


def get_task(engine: Engine, task_id: str) -> Optional[dict]:
    """Read a task node (spec, state, assignee, criteria, ACCEPTED_RISKS)."""
    t = engine.graph.get_task(TaskId(task_id))
    if t is None:
        # `null` for a node that is not there made "no such id" and "nothing to say" the same
        # answer — and over HTTP a 200 with an empty body, which reads as success.
        return {"error": f"unknown task {task_id} — check the id, or `project=` if you meant "
                         f"another graph (`get_graph` lists what this one holds)"}
    out = task_out(t, engine)
    if (blocked := _blocked_by(engine, t)):
        out["blocked_by"] = blocked
    return out


def get_review(engine: Engine, task_id: str) -> dict:
    """The stored L2 review record (review_decomposition's LAST verdict: per-criterion
    sufficient/insufficient/uncertain + conflicts + model + ts) with its freshness: `verified` is
    True while the decomposition is UNCHANGED since the review — any shape change (criteria,
    mappings, deps, a child's re-ASSIGN) auto-stales it. review=null ⇒ never reviewed. Reading is
    free (no LLM); re-run `review_decomposition` to refresh — or for a second opinion pass a
    stronger model (review_decomposition(model="opus"))."""
    t = engine.graph.get_task(TaskId(task_id))
    if t is None:
        return {"error": f"unknown task {task_id}"}
    # …and the EXACT strings `dispute_finding(criterion=)` accepts for what is still open. The key
    # is not always the finding's own text — a conflict is disputed as "conflict: <a>, <b>" and an
    # undecided obligation as "undecided: <obligation>" — and neither prefix appeared anywhere a
    # reader could see it, so the first dispute of each kind was rejected and the ERROR message was
    # what taught the caller the form (measured on the human door 2026-08-21).
    open_findings = engine.open_l2_findings(TaskId(task_id))
    _rec = engine.get_critique(TaskId(task_id))
    out = {"task_id": task_id, "verified": t.verified,
           "review": _rec,
           # …AND WHAT THE RECORD'S OWN `gate_passed` MEANS, here where a reader comes BACK to check.
           # It names a PRE-condition (the structure was clean enough to run the checker), not a
           # verdict on the plan — and the sentence saying so lived only in `review_decomposition`'s
           # reply, so `get_review` alone read as "gate passed, go" while the children could not
           # start (agent door, 2026-09-02). Same fact, same words, whichever door asks.
           "gate_passed_means": ("Level 0/1 only: the structure was clean enough for the Level-2 "
                                 "checker to run. It is not a verdict on the plan — that is "
                                 "`execution_admitted`, and the two disagree whenever the checker "
                                 "ran and returned findings."),
           "execution_admitted": engine.execution_admitted(t.id),
           "open_findings": open_findings,       # null = no current review to be open against
           "dispute_keys": open_findings or [],  # pass one of these verbatim as `criterion`
           }
    # …AND WHY THE LIST IS EMPTY, when it is. A stale review still READS in full — twelve findings,
    # right there — while nothing can be disputed against it, because a dispute answers a CURRENT
    # review. Both documented escapes from the gate then looked closed and neither said so: the
    # tester saw twelve findings beside `dispute_keys: []` and no sentence connecting the two
    # (agent door, 2026-09-02).
    # …AND HOW THE CLOSED ONES WERE CLOSED. A finding leaves the open list two ways — the plan
    # changed, or somebody argued it away — and the summary showed neither, so a gate discharged
    # entirely by argument reads identically to one nobody had to argue with. Both wave-22 testers
    # asked for this line, in the same words, after one of them dismissed eight substantive findings
    # and watched every surface stay green. The disputes were faithfully stored the whole time; they
    # were simply nested where a reader had to already know to look.
    if _disputes := ((_rec or {}).get("disputes") or {}):
        out["discharged_by_dispute"] = sorted(_disputes)
        out["discharged_by_dispute_note"] = (
            f"{len(_disputes)} finding(s) of THIS review were closed by argument rather than by "
            f"changing the plan. A dispute is a legitimate discharge — the checker approximates and "
            f"can be wrong (§9.9) — and it is also the discharge nobody re-checks, so it is named "
            f"here rather than only inside the record. The reasons are under `review.disputes`.")
    if _rec and not open_findings and not t.verified:
        out["dispute_keys_note"] = (
            f"the review below is STALE — the decomposition changed after it was made, so its "
            f"findings are about an earlier plan and nothing can be disputed against them. "
            f"`review_decomposition('{task_id}')` re-runs it; what is still true comes back.")
    return out


#: How much a standing verdict is WORTH, said in words, one entry per kind the engine distinguishes.
#: Kept beside the read rather than inside it so the three readings sit next to each other and a
#: fourth kind cannot be added to the engine without this failing to have a word for it.
_INDEPENDENCE = {
    "none": "no verdict is recorded for this node",
    "by_hand": ("asserted by hand: recorded by a party who named themselves, not produced by a "
                "registered instrument — its weight is the observation text beside each criterion "
                "(§10.3 degenerate case)"),
    "self": ("SELF-REPORTED by the node's own executor — not an independent check. §10.3 makes "
             "an INTERNAL node's own report its record, and the guarantee is carried by the "
             "independent validation of the public result ABOVE it, never by this line"),
    "instrument": "produced by an instrument run — a fresh read-only validator that executed the "
                  "criteria — under the name in `validator`, which is not the node's executor",
}

#: …AND WHETHER THAT NAME IS ANYBODY. The sentence above used to say "the REGISTERED instrument",
#: which the record had never checked: a stranger passed `validator="w23http-ghost-instrument"` — a
#: name invented in that call and in no roster — and the read asserted registration about it, with
#: `by_hand: false` beside (HTTP door, wave 23, 2026-09-03). The validation itself was real, so the
#: verdict is not the defect; the CLAIM about who produced it is. The roster is a fact the engine
#: has, so the reading says which of the two it is instead of assuming the better one.
_UNREGISTERED = (" — NOTE: this name is not on the validator roster (`list_agents`), so it is a "
                 "label chosen by whoever asked for the run, not a standing instrument. The run "
                 "was real; who it is attributed to is not established")


def _shorten(text, keep: int, where: str) -> tuple:
    """(text, was_it_trimmed) — the head of `text`, with what was dropped said IN the value.

    A truncation a reader cannot see is worse than the length it saved: it reads as the whole
    field, and a probe's output that stops mid-line reads as a probe that stopped mid-line.
    """
    s = str(text or "")
    if keep <= 0 or len(s) <= keep:      # keep <= 0 = no bound (the human page, `trim=False`)
        return s, False
    return (s[:keep] + f"\n… [{len(s) - keep} more characters — this field was shortened for the "
                       f"read; `get_verdict(task_id, criterion={where!r})` returns it whole]"), True


def _shorten_into(text, keep: int, trimmed: list, label: str):
    """`_shorten`, with the record of it kept — one call, so the two halves cannot come apart.

    Both defects this exists against were the same shape: a field was shortened and the `shortened`
    line never learned of it, because the caller dropped the second half of the pair (`[0]` on the
    trim, a bare `_shorten` whose flag went nowhere). A truncation the reader is not told about
    reads as the whole value — which is the defect the bound was written to prevent, arrived at
    from the other side.
    """
    out, cut = _shorten(text, keep, label)
    if cut:
        trimmed.append(label)
    return out


def _trim_into(entries, keep: int, trimmed: list, label: str) -> list:
    """`_trim_per_criterion`, with the record kept and the entries' own names carried out."""
    out, cut = _trim_per_criterion(entries, keep)
    trimmed.extend(f"{label}:{n}" for n in cut)
    return out


def _trim_per_criterion(entries, keep: int = VERDICT_FIELD_CHARS) -> tuple:
    """Shorten the two bulky prose fields of each entry; never drop an entry. (config.VERDICT_FIELD_CHARS)

    EVERY CRITERION COMES BACK. Dropping entries to fit would make a validated criterion indis-
    tinguishable from one nobody spoke to — ⊥ (§2.3) — which is precisely the defect this surface
    reports on. So the count is preserved and the prose is what gives way.
    """
    out, trimmed = [], []
    for e in entries or ():
        if not isinstance(e, dict):
            out.append(e)
            continue
        name = str(e.get("criterion") or "")
        e2 = dict(e)
        # …WITHOUT INVENTING THE KEY. This wrote `evidence` unconditionally, so an entry that
        # carried none came back with an empty one — an unrequested shape change on a surface
        # whose whole point is that absence and presence must not be confusable (§2.3 is the
        # same distinction one level up: an unspoken criterion is not a passing one).
        if "evidence" in e:
            e2["evidence"], cut = _shorten(e.get("evidence"), keep, name)
            if cut:
                trimmed.append(name)
        raw = e.get("probe")
        probes = raw if isinstance(raw, (list, tuple)) else ([raw] if isinstance(raw, dict) else None)
        if probes is not None:
            new = []
            for p in probes:
                if not isinstance(p, dict):
                    new.append(p)
                    continue
                p2 = dict(p)
                p2["output"], cut = _shorten(p.get("output"), keep, name)
                if cut and name not in trimmed:
                    trimmed.append(name)
                new.append(p2)
            e2["probe"] = new if isinstance(raw, (list, tuple)) else new[0]
        out.append(e2)
    return out, trimmed


def _what_there_is_to_decide_with(engine: Engine, task_id: str, out: dict,
                                  trimmed: list, keep: int) -> None:
    """The delivery and any REFUSED report — what an issuer validates from when no verdict exists.

    Both were reachable from no door at all: the frontier tells an issuer to "check the deliverable
    against the criteria" and a person validating a delegated node found out what it had done by
    listing the directory (agent door, 2026-08-21); and a node parked on two refused reports asks
    its issuer to decide with the reports nobody could read.

    THIS IS THE PATH THE BOUND WAS WRITTEN FOR, and the reason it lives here rather than beside the
    recorded verdict: the measured incident was three validations that returned NO VERDICT, so
    `rec` is None, `per_criterion` is empty, trimming it trims nothing, and the whole 85 KB arrived
    through exactly these two fields (outside review of this very change, 2026-09-23).
    """
    if (report := engine.deliver_result(TaskId(task_id))):
        # raw executor prose, with no upper bound on it
        out["delivered"] = _shorten_into(report, keep, trimmed, "delivered")
    if (rej := engine.rejected_report(TaskId(task_id))):
        obs = _trim_into(rej.get("per_criterion") or [], keep, trimmed, "refused")
        out["refused_report"] = {
            # THE BIGGEST FIELD ON THIS PATH, and the first repair walked past it: `defects` is
            # the engine's own refusal prose, which enumerates every criterion and every
            # unobserved behaviour, so it grows with criteria x behaviours. The fold cannot save
            # a read from it BY CONSTRUCTION — folding only touches per-criterion lists — so an
            # oversized `defects` destroyed all the diagnosable detail and sailed through anyway
            # (second outside review, 2026-09-23: 200 KB in repro, on the incident path).
            "why_it_is_not_a_verdict": _shorten_into(rej.get("defects"), keep, trimmed,
                                                    "why_it_is_not_a_verdict"),
            "refusals_on_this_node": rej.get("refusals", 1),   # two = the contract, not the run
            "observed_anyway": obs,
            "ts": rej.get("ts"),
            "note": "this is EVIDENCE, not a verdict: the validator could not decide every criterion, "
                    "and ⊥ is not a pass. Read it, then either run the validation again or record "
                    "your own verdict.",
        }


def _criterion_in_full(engine: Engine, task_id: str, rec, criterion: str) -> dict:
    """ONE criterion's entry, untrimmed — so the bound hides nothing.

    A cap that makes a field unreachable is the same blindness by a smaller number: the reader who
    needs the whole output is exactly the one diagnosing a refusal, which is the case the cap exists
    for. It reaches the REFUSED report too, because when there is no verdict that is where the
    evidence is — and that is the only path the measured incident ran through.
    """
    _rej = (engine.rejected_report(TaskId(task_id)) or {}).get("per_criterion") or []
    _cur = (rec or {}).get("per_criterion") or []
    # …COPIED, not aliased: these are the engine's own stored dicts, and a read surface handing out
    # references into the record is one careless caller away from editing it.
    _pick = (lambda src: [dict(e) for e in src
                          if isinstance(e, dict) and str(e.get("criterion") or "") == criterion])
    named, named_rej = _pick(_cur), _pick(_rej)
    out = {"criterion_in_full": named or None}
    if named_rej:
        out["criterion_in_full_refused_report"] = named_rej
    # …AND IT ANSWERS FOR THE DELIVERY, because the bound's own marker points here for it: a
    # shortened `delivered` says to ask for it by name, and that returned nothing at all with a
    # note reading "the names on this node are none" — the product sending an agent into a dead end
    # down its own instruction. It is checked AFTER the criteria, so a node that really has a
    # criterion called `delivered` still reaches its entry; an earlier version returned first and
    # made that criterion unreachable by name, with nothing saying so.
    if not named and not named_rej and criterion == "delivered":
        if (_report := engine.deliver_result(TaskId(task_id))) is not None:
            return {"criterion_in_full": [{"criterion": "delivered", "delivered": _report}]}
    if not named and not named_rej:
        _all = [str(e.get("criterion")) for src in (_cur, _rej) for e in src if isinstance(e, dict)]
        # …AND THE MISS-NOTE IS BOUNDED LIKE EVERYTHING ELSE. It lists every name on the node, so a
        # TYPO on a 300-criterion node answered with a quarter-megabyte — and it sits under the
        # `criterion_in_full` prefix, which the budget deliberately does not weigh, so nothing
        # downstream would have caught it (fourth outside review, 2026-09-23).
        _names = list(dict.fromkeys(_all))
        _shown, _room = [], _MARKER_CHARS
        for _n in _names:                     # by CHARACTERS: a cap on the COUNT of
            if _room - len(_n) < 0:           # names bounds nothing, names being free text
                break
            _room -= len(_n) + 2
            _shown.append(_n)
        out["criterion_in_full_note"] = (
            f"neither the recorded verdict nor any refused report carries an entry for "
            f"{criterion!r} — the names on this node are " + (", ".join(_shown) or "none")
            + (f" … and {len(_names) - len(_shown)} more" if len(_names) > len(_shown) else ""))
    return out


#: The floors the whole-response shrink will not go below, and the guard on its own loop. A string
#: shorter than this carries no bulk worth taking; a list this short is already a summary.
_SHRINK_STR_FLOOR, _SHRINK_LIST_FLOOR, _SHRINK_PASSES = 300, 8, 200
#: …and how much a MARKER may spend saying what gave way. A marker that grows with the
#: node is the thing it is reporting on.
_MARKER_CHARS = 1200


def _reducible(node, found: list, skip_top=(), skip_ids=frozenset()) -> None:
    """Every leaf of the response that could give way — a long string or a long list, AT ANY DEPTH.

    This is the part three rounds of repair kept getting wrong. Each round bounded the fields it had
    thought of, and each round the bulk arrived through one it had not: `observed_anyway`,
    `delivered`, then `why_it_is_not_a_verdict`. The round after that replaced the enumeration with
    an EXEMPTION list plus a scan of top-level strings — the same enumeration inverted, and it
    missed every list (`failed_criteria`, 441 KB measured), every string nested inside `overruled` /
    `refused_report`, and everything named on the exemption list (`validator`, 200 KB).
    So nothing here knows a field name. It walks the structure it is handed.
    """
    if isinstance(node, dict):
        for k, v in node.items():
            if k in skip_top:
                continue
            if isinstance(v, str) and len(v) > _SHRINK_STR_FLOOR:
                found.append((len(v), node, k, "str"))
            elif isinstance(v, list):
                if id(v) in skip_ids:
                    continue                  # already folded to bare names — not prose
                if len(v) > _SHRINK_LIST_FLOOR:
                    found.append((len(json.dumps(v, default=str)), node, k, "list"))
                _reducible(v, found, skip_ids=skip_ids)
            elif isinstance(v, dict):
                _reducible(v, found, skip_ids=skip_ids)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str) and len(v) > _SHRINK_STR_FLOOR:
                found.append((len(v), node, i, "str"))
            elif isinstance(v, (dict, list)):
                _reducible(v, found, skip_ids=skip_ids)


def _reduce_one(container, key, kind: str) -> bool:
    """Halve one leaf, saying so in its place. False = it could not be made strictly smaller.

    The strictness is the termination proof. A previous version shortened to `max(400, n // 4)` and
    appended a ~130-character marker, so a 400-character floor produced a 530-character value that
    was eligible again on the next pass and became 530 again — a fixed point ABOVE the floor, and
    an infinite loop on the door an agent calls to ask why a validation carried no verdict. Every
    reduction here is checked to have actually shrunk, and the caller stops when one does not.
    """
    cur = container[key]
    if kind == "str":
        target = max(_SHRINK_STR_FLOOR // 2, len(cur) // 2)
        shorter = cur[:target] + f"… [{len(cur) - target} more characters, shortened to fit the read]"
        if len(shorter) >= len(cur):
            return False
        container[key] = shorter
        return True
    n = max(1, len(cur) // 2)
    if n >= len(cur) - 1:
        return False
    container[key] = cur[:n] + [f"… {len(cur) - n} more, dropped to fit the read"]
    return True


def _fold_the_detail(out: dict, task_id: str, budget: int, weigh) -> set:
    """Per-criterion DETAIL folds to the criterion NAMES — the meaningful reduction, done first.

    The names are what tell a reader which entry to ask for, so this gives up the evidence and
    keeps the index. It runs only as far as it is needed: folding all four records unconditionally
    let one oversized field elsewhere destroy every criterion's evidence to make room for itself.

    Returns the ids of the lists it folded, so the blind pass behind it leaves them alone — those
    are bare names now, not prose, and halving them would strand the very route this writes.
    """
    folded_detail, folded_lists = [], set()
    for label, holder, key in (("per_criterion", out, "per_criterion"),
                               ("overruled", out.get("overruled") or {}, "per_criterion"),
                               ("closed_on", out.get("closed_on") or {}, "per_criterion"),
                               ("refused_report", out.get("refused_report") or {}, "observed_anyway")):
        if weigh() <= budget:
            break
        src = holder.get(key)
        if isinstance(src, list) and src:
            names = [str(e.get("criterion")) for e in src if isinstance(e, dict)]
            holder[key] = [{"criterion": n, "folded": True} for n in names]
            folded_lists.add(id(holder[key]))
            folded_detail.append(f"{label} ({len(names)})")
    if folded_detail:
        out["folded_to_fit"] = (
            f"this node's record is larger than one read can carry, so the per-criterion DETAIL of "
            f"{', '.join(folded_detail)} was replaced by the criterion NAMES — their verdicts, "
            f"evidence and probes are not in this response. Read them one at a time with "
            f"`get_verdict {task_id} criterion=<name>`, which is never folded.")
    return folded_lists


def _bound_the_read(out: dict, task_id: str, trimmed: list, keep: int) -> None:
    """Say where prose gave way, and bring the WHOLE response under budget whatever shape it is in.

    Separate from building the record because it is a different operation ON the finished record:
    it has to run last, when every branch that could add bulk has added it. And it may not be a
    list of fields — a per-FIELD bound is not a bound on the response, and every round that named
    the fields leaked through one it had not named.
    """
    # THE MARKER IS BUILT FIRST, BECAUSE IT IS PART OF WHAT THE READ COSTS. It was written after
    # the budget block, and it joins one label PER CRITERION NAME — uncapped in count and in name
    # length — so the measurement never saw the field that grew fastest with the node. Measured on
    # a 200-criterion node with long names: 417 KB out, of which 401 KB was the marker saying the
    # prose had been shortened to fit. A bound enforced on a measurement that excludes its own
    # output is not a bound (sixth outside review, 2026-09-23).
    if trimmed:
        _labels = ", ".join(dict.fromkeys(trimmed))
        out["shortened"] = (
            f"prose was shortened to fit this read (config.VERDICT_FIELD_CHARS): "
            + (_labels if len(_labels) <= _MARKER_CHARS else
               _labels[:_MARKER_CHARS] + f"… and {len(trimmed)} entries in all")
            + f". For one criterion in full: `get_verdict {task_id} criterion=<name>`.")
    if keep <= 0:
        return
    budget = keep * VERDICT_RESPONSE_MULTIPLE
    # …MEASURED WITHOUT THE DRILL-DOWN. `criterion=` is the caller asking for one entry WHOLE,
    # knowing it is long; counting it against the budget would fold everything else as the price of
    # the question, which is the opposite of what the drill-down is for. Everything else counts,
    # including the markers this function writes.
    protect = tuple(k for k in out if isinstance(k, str) and k.startswith("criterion_in_full"))
    weigh = (lambda: len(json.dumps({k: v for k, v in out.items() if k not in protect},
                                    default=str)))
    if weigh() <= budget:
        return
    folded_lists = _fold_the_detail(out, task_id, budget, weigh)
    # …AND THEN THE GUARANTEE, which knows no field names at all — but does know that a list it has
    # already folded to bare names is not prose. The shrink used to halve that list too, so a
    # 200-criterion node came back carrying 8 names while `folded_to_fit` told the reader to ask
    # for the rest BY THOSE NAMES, which were nowhere in the response. That is the ⊥ case
    # `_trim_per_criterion` refuses in as many words — a criterion missing from the list reads
    # exactly like one nobody validated — reintroduced by the pass standing behind it.
    gave_way, last = [], None
    for _ in range(_SHRINK_PASSES):
        size = weigh()
        if size <= budget or (last is not None and size >= last):
            break                             # under budget, or making no progress — never spin
        last = size
        found: list = []
        _reducible(out, found, skip_top=protect, skip_ids=folded_lists)
        if not found:
            break                             # nothing left that may give way
        found.sort(key=lambda f: -f[0])
        _size, container, key, kind = found[0]
        if not _reduce_one(container, key, kind):
            break
        gave_way.append(str(key))
    if gave_way:
        out["over_budget"] = (
            f"this read was still larger than one response can carry, so "
            f"{', '.join(dict.fromkeys(gave_way))} gave way too — each says IN PLACE what was "
            f"dropped, so read those markers rather than the values alone.")
    # …AND IF IT IS STILL OVER, SAY SO, MEASURED WHOLE. A response that goes out over budget while
    # its own markers read "replaced so it fits" tells the reader it fits when it does not, which
    # is the invisible-truncation defect wearing a different hat. The number is the WHOLE response,
    # drill-down included: reporting `weigh()` here understated what the caller actually receives.
    _final = len(json.dumps(out, default=str))
    if weigh() > budget:
        # "AT LEAST", because this sentence is itself part of what the caller receives and cannot
        # count itself. The exact form understated the response by its own length, which is the
        # same species of claim as the marker that says a read fits when it does not.
        out["still_over_budget"] = (
            f"even after that, this read is at least {_final} bytes against a {budget}-byte "
            f"budget: what is left is structure rather than prose. Read one criterion at a time "
            f"(`get_verdict {task_id} criterion=<name>`).")


def get_verdict(engine: Engine, task_id: str, criterion: str = "", _trim: bool = True) -> dict:
    """The stored EXECUTION verdict on a node — the validator's LAST report, read back in full:
    PASS/FAIL, `failed_criteria`, and per criterion the probe that was run, what it printed and the
    behaviours it was labelled with. Free (no LLM). This is the counterpart of `get_review` (which
    reads the Level-2 verdict on the PLAN, not on the work).

    Written because the issuer had no way to READ what the validator said: `validate_result` returns its
    report once, to whoever called it, and a person coming back later — or a second agent, or anyone
    signing PASS/FAIL on the node — had the verdict in the database and no verb to reach it, so they
    were left signing on a summary. `verdict: null` = never validated. `undecidable` names the
    criteria whose declared behaviours were never observed — the INSTRUMENT's gaps, not failures of
    the work, and the reason a report can carry no PASS while refuting nothing (§2.3: ⊥ is not a
    verdict).

    The read is BOUNDED (config.VERDICT_FIELD_CHARS): every criterion comes back, while narrated
    evidence, captured probe output and the delivery text are shortened where they are long,
    `shortened` naming which. `criterion=<name>` returns that one entry whole, from the recorded
    verdict AND from a refused report. A rich contract's full record ran past the agent door's own
    cap and the caller got NOTHING — measured on the delegated cell of 2026-09-22, where the agent
    asked this verb why three validations carried no verdict and escalated blind.

    (The bound is not a caller's option. It was spelled `trim` for one round, which put it on the
    agent door's own menu — so the read that exists to keep a response inside the client's cap
    advertised, in its own description, the argument for exceeding it. Underscore-prefixed
    parameters are transport-internal and filtered from every tool surface; the HTTP door serving
    the human page passes `_trim=False`, because a browser has no cap and that panel shows evidence
    in full BY DESIGN — a 300-character cut there was removed by name.)"""
    t = engine.graph.get_task(TaskId(task_id))
    if t is None:
        return {"error": f"unknown task {task_id}"}
    rec = engine.get_exec_verdict(TaskId(task_id))
    _prov = engine.verdict_provenance(TaskId(task_id))
    # 0 = no bound. One spelling of "is this read bounded", used by every branch below.
    _keep = VERDICT_FIELD_CHARS if _trim else 0
    _per_criterion, _trimmed = _trim_per_criterion((rec or {}).get("per_criterion") or [], _keep)
    out = {"task_id": task_id, "state": t.state.name,
           "verdict": (rec or {}).get("verdict"),
           "validator": (rec or {}).get("validator"),   # the ROLE that validated, when one was registered
           # WHAT KIND OF PARTY IT WAS. A record a person asserted at a door where identity is
           # self-declared read back exactly like an instrument's report, so nothing downstream could
           # tell "a validator ran the work" from "someone typed a name" (measured on the CLI door
           # 2026-09-02). The gate cannot close that — FM-3's false PASS is guarded by no structural
           # CHECK (§15.7) — but the record must not present it as more than it is.
           "by_hand": bool((rec or {}).get("by_hand")),
           # THREE KINDS, not two. The middle one — an internal node's own executor stamping its
           # DELIVER (§10.3) — was being reported as an instrument's work while the evidence line
           # beside it read SELF-REPORTED (MCP door, 2026-09-02). The engine owns the distinction,
           # because the dispatcher already had to make exactly it to stop reusing a self-report as
           # an independent verdict.
           "provenance": _prov,
           # …AND THE PRODUCT'S OWN VERB IS NOT "A LABEL SOMEBODY CHOSE". `validate_result` records
           # under that name when no role was passed, and the unregistered caveat was appended to
           # it — telling an integrator that the instrument the product had just run for them was
           # a name of unestablished provenance (HTTP door, wave 27, 2026-09-06). The caveat is for
           # a name a CALLER supplied that no roster carries.
           "independence": (_INDEPENDENCE[_prov]
                            + (_UNREGISTERED
                               if _prov == "instrument"
                               and str((rec or {}).get("validator") or "") != "validate_result"
                               and str((rec or {}).get("validator") or "")
                               not in engine.graph.authorized_validators else "")),
           "validator_model": (rec or {}).get("validator_model"),
           "failed_criteria": (rec or {}).get("failed_criteria") or [],
           "undecidable": [p.get("criterion") for p in ((rec or {}).get("per_criterion") or [])
                           if p.get("verdict") == "undecidable"],
           "per_criterion": _per_criterion,
           # …and WHERE it was validated, so a probe that no longer reproduces is diagnosable rather
           # than mysterious (a rename after the verdict made every stored command unreplayable).
           "workdir": (rec or {}).get("workdir") or "",
           "ts": (rec or {}).get("ts")}
    # …AND WHAT IT NO LONGER RE-RAN BY ITS ISSUER'S RULING: a PASS read without it reads as wide as one that re-ran all
    if _ret := engine.retired_findings(TaskId(task_id)):
        out["retired_after_refutation"] = [{k: r.get(k) for k in ("criterion", "id", "by", "why")} for r in _ret]
    if criterion:
        out.update(_criterion_in_full(engine, task_id, rec, criterion))
    # …AND SAY IT WHEN THE STATE AND THE RECORD DISAGREE. A node can stand at PASS while this very
    # record says FAIL: the signature landed before the instrument's verdict did, and the FSM
    # correctly refused that verdict on a node already terminal. Both facts were readable — the state
    # here, the verdict beside it — and nothing put them together, so `status` printed DONE for good
    # (CLI door, 2026-09-02). The engine owns the predicate; q_V has always counted exactly this.
    # …AND WHAT IT ACTUALLY CLOSED ON, when a later record has landed on top. Without this the
    # surface that answers "did anything close without proof" is the one surface that can be
    # rewritten after the close, in the closer's favour (HTTP door, 2026-09-02).
    # …AND A CONTRADICTION INSIDE THE VALIDATION WINDOW, which the read simply did not carry. A second
    # verdict on one delivery replaces the first; when the two DISAGREE, the reader is being handed
    # one half of a disagreement and no sign that there was one (CLI door, wave 24, 2026-09-04: a
    # hand-asserted PASS replaced an instrument's FAIL and every summary surface showed an earned
    # green). Overruling is legitimate — the verdict is the issuer's act (§10.2) — and it is not
    # allowed to be invisible.
    if (_over := engine.overruled_verdict(TaskId(task_id))):
        out["overruled"] = {
            "verdict": _over.get("verdict"), "validator": _over.get("validator"),
            "by_hand": bool(_over.get("by_hand")), "ts": _over.get("ts"),
            "failed_criteria": _over.get("failed_criteria") or [],
            "per_criterion": _trim_into(_over.get("per_criterion") or [], _keep, _trimmed,
                                       "overruled")}
        out["overruled_note"] = (
            f"a {_over.get('verdict')} on THIS delivery by {_over.get('validator')!r} was replaced "
            f"by the record above. Two parties validated one delivery and disagreed; the standing "
            f"verdict is the later one, and this is the one it displaced — weigh both. "
            + ("The displaced verdict came from an INSTRUMENT that ran the criteria; the one "
               "standing over it was asserted by hand, which the engine cannot check for "
               "independence (§15.7)."
               if not _over.get("by_hand") and bool((rec or {}).get("by_hand")) else ""))
    if (_closed_on := engine.closing_verdict(TaskId(task_id))):
        out["closed_on"] = {
            "verdict": _closed_on.get("verdict"), "validator": _closed_on.get("validator"),
            "by_hand": bool(_closed_on.get("by_hand")), "ts": _closed_on.get("ts"),
            "per_criterion": _trim_into(_closed_on.get("per_criterion") or [], _keep, _trimmed,
                                       "closed_on"),
            "note": (f"THIS is the record {task_id} closed on. The verdict above arrived AFTER it "
                     f"and did not close anything — a later record is evidence about the same "
                     f"delivery, never a replacement for the one that was acted on."),
        }
    if str(task_id) in engine.refuted_passes():
        out["contradicts_state"] = (
            f"{task_id} is {t.state.name} at PASS, and the verdict above — its CURRENT one — is "
            f"FAIL. The state is showing a signature that landed before this verdict did. This is "
            f"not a green node: recovery is `reopen` if it is not consumed, re-decomposition around "
            f"it if it is.")
    # A verdict belongs to the delivery it validated. A node that has since been reworked or revised
    # carries a record about an EARLIER artifact, and read as current it is exactly the stale
    # evidence this system exists to refuse.
    # WHICH delivery a record validated, and whether that is the one standing now, is the ENGINE's
    # rule (`current_exec_verdict`) — the frontier asks the same question, and two spellings of it
    # would answer differently the first time either moved.
    gen = engine.VERDICT_GENERATION
    _current = engine.current_exec_verdict(TaskId(task_id)) is not None
    if rec is not None:
        # …AND SAY IT WHEN IT IS CURRENT. Only staleness was ever announced, so "no `stale` field"
        # had to be read as "current" — an absence standing for an assertion, which a reader has to
        # know the convention to decode (measured on the agent door 2026-08-21: "the record doesn't
        # assert it"). The generation it validated is what makes it checkable.
        out["current"] = _current
        out["validated_generation"] = {k: rec.get(k, 0) for k in gen}
        out["node_generation"] = {k: getattr(t, k, 0) for k in gen}
        if not _current:
            # The GENERATION, not the iteration alone: a REOPEN moves `reopens` and a revision moves
            # `revisions`, and neither touches the iteration — so a verdict from before a reopen read
            # as current. Measured 2026-08-20: after a reopen and a fresh delivery, the previous
            # delivery's PASS came back with no mark on it at all.
            out["stale"] = ("this verdict validated an EARLIER delivery — recorded at "
                            + ", ".join(f"{k} {rec.get(k, 0)}" for k in gen)
                            + "; the node now stands at "
                            + ", ".join(f"{k} {getattr(t, k, 0)}" for k in gen)
                            + ". Re-validate before signing on it.")
    if rec is None:
        # …AND "NOT VALIDATED" IS THE WRONG WORD WHEN A REPORT WAS REFUSED. A validator ran, reported,
        # and the engine refused the report as ⊥ (§2.3) — which is a different situation from
        # nobody having looked, and it is the one that needs a decision. The note said the node had
        # not been validated while the refused report sat further down the same object, and a
        # tester polled for fifteen minutes before scrolling into it (agent door, 2026-09-02).
        _ref = engine.rejected_report(TaskId(task_id))
        out["note"] = (
            (f"a validator DID report on {task_id} and the engine REFUSED the report as ⊥ — "
             f"{_ref.get('refusals', 1)} time(s) so far; see `refused_report` below for what it "
             f"managed to observe. This is not a verdict and never becomes one: put your own "
             f"observation on the record with `record_verdict`, or narrow what the node promises "
             f"(`edit_criteria`).")
            if _ref else
            (f"no execution verdict recorded for {task_id} — it has not been validated "
             f"(state {t.state.name}). `get_review` reads the verdict on its PLAN."))
        # …AND WHETHER ANYTHING IS STILL COMING. This is the surface the DELIVER reply names ("wait
        # for it — `get_verdict` reads the result"), and it was the one surface that did not know the
        # automatic path had died: an ordinary user polled it every twenty seconds for four minutes
        # while the log had already written "no automatic verdict will arrive", and said plainly that
        # this was where they would have given up (wave 25, 2026-09-05 — asked for as the single
        # change that would have helped them most). The dispatcher parks such a node deliberately;
        # what was missing is that the parking reached the reader.
        if str(task_id) in engine.parking.parked_validations():
            out["automatic_validation"] = "gave up"
            out["note"] += (" AUTOMATIC VALIDATION HAS GIVEN UP on this node: the instrument was run "
                            "and could not produce a verdict, so nothing further will arrive by "
                            "itself (⊥ is not pass, §2.3 — the issuer decides). Narrow what the "
                            "node promises (`edit_criteria`), or record what YOU "
                            "observed (`record_verdict`). Waiting is the one thing that will not "
                            "work.")
    _what_there_is_to_decide_with(engine, task_id, out, _trimmed, _keep)
    _bound_the_read(out, task_id, _trimmed, _keep)
    return out


def dispute_finding(engine: Engine, task_id: str, criterion: Union[str, list], why: str) -> dict:
    """Record why ONE Level-2 finding is wrong — the alternative to fixing the plan (which does not
    discharge a finding: it retires the whole verdict, and `review_decomposition` must speak again). Execution is
    gated on every finding of the CURRENT review being discharged: either the plan changes (which
    stales the review — re-run it) or the finding is disputed HERE, in writing. The checker is an
    a-priori approximation (§9.9) and can be wrong; what the system refuses is skipping it
    silently. `criterion` = the flagged parent criterion exactly as `get_review` names it (a
    conflict is disputed as "conflict: <a>, <b>", and an obligation the sufficiency check named as
    "undecided: <the obligation, in its own words>"); `why` = the reason the entailment does hold.
    `get_review` hands back the exact strings that are open, under `dispute_keys` — copy one.
    The dispute lives in that review record only — a fresh review requires a fresh dispute.

    `criterion` also takes a LIST when one reason answers several findings — a checker that names one
    obligation in three wordings costs three calls otherwise, and a caller who has written the reason
    once should not write it three times (measured on two doors, 2026-09-02). Each is recorded
    separately, with the same reason, and the reply names what is still open."""
    # A DISPUTE THAT SAYS NOTHING DISCHARGES NOTHING. The Level-2 gate is the product's headline
    # feature and it cost one word per finding to defeat: BOTH stranger doors, independently, opened
    # it with "nah" and "nah, its fine" — eight substantive findings on one, three on the other — and
    # both testers named this verb and asked for the rule `record_verdict` already applies. The
    # checker is an approximation and may be wrong (§9.9); what discharges it is a REASON, and
    # "this is fine, trust me" is the conclusion restated, not a reason for it.
    if _is_pure_assent(why):
        return {"refused": True,
                "error": f"a dispute needs to say WHY the entailment holds — what you wrote "
                         f"({str(why).strip()!r}) restates the conclusion rather than giving a "
                         f"reason for it. Name the criterion or the accepted risk that already "
                         f"decides the obligation, or the reading of the plan the checker missed. "
                         f"The other way is to fix the plan, which needs no argument at all — and "
                         f"takes two steps: the fix RETIRES this verdict, so `review_decomposition` "
                         f"has to speak again before execution is admitted."}
    # …AND A FLOOR ON HOW MUCH IS SAID AT ALL, which the rule above cannot supply. The vocabulary
    # test catches a sentence that only restates the conclusion; it has nothing to say about two
    # characters of noise. Three doors bisected this to the same pair — `"no"` refused, `"xy"`
    # accepted, both two characters — and one of them discharged thirteen findings, including three
    # proofs that a contract was jointly unsatisfiable, with about sixty characters of `"Blue
    # kettle."` and `"zz"` (waves 23–25).
    # Three CONTENT words, deliberately low: the shortest honest dispute in this repository's own
    # suite is "uncertainty is about wording, not entailment", which has exactly three, and a rule
    # that refuses honest work is worse than the hole it closes — measured here on 2026-09-04, when a
    # stricter version of this floor was built, run against the suite, and reverted within a minute.
    # This is a floor on FORM. Filler prose of the right length still passes, and saying otherwise
    # would be the same overclaim the old message made.
    _content = content_words(why)
    if len(_content) < 3:
        return {"refused": True, "words_that_carried_meaning": sorted(_content),
                "error": (f"a dispute has to say something: what you wrote carries "
                          f"{len(_content)} word(s) that are not assent, negation or a restatement "
                          f"of the finding. The checker is an approximation and can be wrong "
                          f"(§9.9) — say WHICH criterion or child already carries the obligation, "
                          f"or which reading of the plan it missed. Fixing the plan discharges a "
                          f"finding with no argument at all.")}
    _keys = [str(c) for c in criterion] if isinstance(criterion, (list, tuple)) else [str(criterion)]
    if len(_keys) == 1:      # the single-key contract is unchanged: it raises, and the door wraps it
        _out = engine.dispute_review_finding(TaskId(task_id), _keys[0], why, AgentId(_agent_id()))
        engine.emit_info("dispute", f"{task_id}: Level-2 finding {_keys[0]!r} DISCHARGED BY ARGUMENT "
                                    f"by {_agent_id()} — the plan did not change. Reason: {why}")
        return _out
    out: dict = {}
    for _k in _keys:
        try:
            out = engine.dispute_review_finding(TaskId(task_id), _k, why, AgentId(_agent_id()))
            engine.emit_info("dispute", f"{task_id}: Level-2 finding {_k!r} DISCHARGED BY ARGUMENT "
                                        f"by {_agent_id()} — the plan did not change. "
                                        f"Reason: {why}")
        except ValueError as ex:
            # In a BATCH the refusal is data, not an exception: the caller needs to know which keys
            # were recorded before it, and a raise carries neither.
            out = {"refused": True, "error": str(ex)}
        if isinstance(out, dict) and (out.get("error") or out.get("refused")):
            # …AND STOP AT THE FIRST ONE THAT DOES NOT LAND. A key that names no open finding is the
            # caller's mistake about THIS review, and disputing the rest under the same reason would
            # bury it: the answer says which key failed and which ones were recorded before it.
            out = dict(out)
            out["disputed_before_this"] = _keys[:_keys.index(_k)]
            return out
    if len(_keys) > 1 and isinstance(out, dict):
        out["disputed"] = _keys
    return out


def project(engine: Engine, task_id: str) -> dict:
    """The read-only projection you REASON over before authoring/validating: goal + subtasks + criteria
    + coverage + seams (Dep) + ACCEPTED_RISKS + already-run structural checks.

    Answers `{task_id, markdown}` — the text is under `markdown`. It used to be a BARE STRING, the
    only verb in the registry that answered one, so a client written against any other verb crashed
    on it (`d.get('markdown')` on a `str`; HTTP door, wave 27, 2026-09-06). Nothing is published yet,
    so the shape is fixed now rather than kept for compatibility with nobody."""
    return {"task_id": str(task_id), "markdown": engine.project(TaskId(task_id))}


def get_checks(engine: Engine, task_id: str) -> list[dict]:
    """(Per-node detail — `list_holes` covers the whole graph at once.) The L0/L1 structural checks (compiler-style: coverage / DAG / anti-mock / sufficiency …)."""
    # `verdict` says the three states apart in one word, because `passed: true, skipped: true` reads
    # as green in a list of ten rows and the skip is the FAIL-OPEN direction. Measured 2026-08-21: a
    # driving agent took a skipped check for a satisfied one and covered for it by hand.
    # `passed` is NULL on a skipped check, not true. Both fields were present with disagreeing
    # implications — `verdict: "skipped"` beside `passed: true` — and a reader keying off the older
    # field counts a check that evaluated nothing as one that was satisfied. That is the fail-OPEN
    # direction, and it is the one this pair must not get wrong.
    # …AND "TRUE OVER NOTHING" IS A THIRD ANSWER. A check whose subject set is empty — no Dep edges
    # to order, no risk components to carry — is a conjunction over ∅: it passes vacuously, and a
    # reader counting green ticks reads it as "the dependencies were checked". Same word at both
    # doors (`met_vacuously`), because the pair `verdict`/`passed` disagreeing is the defect this
    # row was built to close in the first place.
    return [{"check": c.check_name,
             "verdict": ("skipped" if c.skipped
                         else "met_vacuously" if (c.vacuous and c.passed)
                         else "met" if c.passed else "unmet"),
             "passed": None if c.skipped else c.passed,
             "vacuous": bool(c.vacuous) and not c.skipped and bool(c.passed),
             "details": c.details, "skipped": c.skipped}
            for c in engine.get_checks(TaskId(task_id))]


def _self_check_verdict(raw) -> Optional[Verdict]:
    """The executor's own verdict from the DELIVER packet — PASS or FAIL, and nothing else.

    A caller told to "carry `self_validation` in the DELIVER packet" sent their whole self-check
    REPORT there: seven criteria with captured stdout. The field took it, the lookup raised, the
    value became None, the delivery was accepted — and their PASS was refused afterwards for
    carrying no self-check, by the same engine whose message had recommended the field (measured on
    the agent door 2026-08-21). A field that cannot hold what you gave it must say so at the door.
    The evidence belongs in `result`, which is what the validator and the record read."""
    if raw is None or raw == "":
        return None
    if (v := verdict_word(raw)) is not None:
        return v
    raise ValueError(
        f"self_validation is your own VERDICT on this delivery — \"PASS\" or \"FAIL\" (§11.2), not a "
        f"report: got {str(raw)[:60]!r}. What you checked and what it printed goes in `result`, per "
        f"criterion; the word here is what you conclude from it.")


def _coverage_lost_by(engine: Engine, task_id: str) -> Optional[dict]:
    """Which of the PARENT's criteria this node was carrying, now that it is a tombstone.

    A cancelled child takes its `covers` with it, and the parent's plan quietly becomes a different
    plan: with the last child gone the node reads as a leaf again, so the coverage checks stop
    applying and `list_holes` is empty — structurally correct and, said that way, indistinguishable
    from "nothing changed". Whoever cancelled is the one who has to decide what now carries those
    criteria (walked by hand 2026-08-21)."""
    parent = engine.graph.get_parent(TaskId(task_id))
    if parent is None:
        return None
    carried = sorted(m.criterion_name for m in parent.criterion_mappings
                     if str(m.child_id) == str(task_id))
    if not carried:
        return None
    left = [str(c.id) for c in engine.graph.get_active_children(parent.id)]
    return {"parent_id": str(parent.id), "criteria_it_carried": carried,
            "children_left": left,
            # NOT "execute it directly" where the engine refuses exactly that: in semi a node the
            # user-agent holds is not worked by it (critic round 15 — the advice invited the degeneration)
            "what_now": (f"nothing carries {carried} any more — decompose '{parent.id}' again" + (
                         ", or execute it directly (with no children it is a leaf, and its criteria are "
                         "its own work)" if engine.held_node_refusal(parent.id, Signal.DELIVER) is None else
                         " (`auto_decompose` on it, with no `executor`): in semi a node you hold is "
                         "executed by the system below it, not by you") if not left else
                         f"{carried} lost the child that covered them — map another child "
                         f"(`map_criterion`) or add one")}


def is_refusal(out) -> bool:
    """Did this verb REFUSE the act — the one question both doors ask, asked in one place.

    The answer used to be read differently by each: the CLI counted `error` ∨ `refused` ∨
    `accepted is False`, while the HTTP door looked only for `refused`/`unexpected` — so
    `record_verdict`'s `{"recorded": False, "error": …}` was exit code 1 over one door and HTTP 200
    OK over the other, for the same act (register 2026-08-22, finding 2). The verbs answer in
    several shapes for good reasons (a signal says `accepted`, a record says `recorded`); what may
    not differ is whether the act happened."""
    if not isinstance(out, dict):
        return False
    return bool(out.get("error") or out.get("refused")
                or out.get("accepted") is False or out.get("recorded") is False)


def _gated_out(engine: Engine, t, task_id: str, who: str, acts: list) -> tuple[list, Optional[str]]:
    """The signals the FSM lists but the machine would refuse, removed — each with the machine's own reason
    (`Engine.refusal_for`, the dry run of the gate the loop runs). Six hand mirrors of the engine's rules lived here,
    each added after a live run found the surface offering what the machine then rejected, and each came apart from
    its original at least once (ortho audit, D-F1); asking the machine is the only copy that cannot.

    What stays is what is not a rule: the advice not to DELIVER an aggregate whose parts are open (admissible, and it
    parks the node), and what ASSIGN does on this node — a REOPEN on a settled one, a REVISION on a live one, whose
    door is `revise`.

    Removals first, then context: a note that says "this signal is gone and here is why" is what a caller acts on.
    `withheld` keys the same fact by signal, for anything that has to ASK which signal was taken out."""
    notes: list[str] = []
    asides: list[str] = []
    withheld: dict[str, str] = {}
    for a in list(acts):
        if (r := engine.refusal_for(TaskId(task_id), Signal[a], None if who == "*" else AgentId(who))) is not None                 and r.kind != "role":
            acts.remove(a)
            notes.append(f"{a} is refused here: {r.why}")
            withheld[a] = notes[-1]
    if Signal.PASS.name in withheld and engine.claims.validation_in_flight(TaskId(task_id)):
        # not a rule — the timing a signer needs: a signature landing before the instrument's verdict meets that verdict
        # at a node already closed, the graph then showing the two contradicting (`refuted_passes`)
        asides.append(f"NOTE: an instrument is validating {task_id}'s delivery RIGHT NOW — wait for its verdict "
                      f"before signing: signed first, its verdict arrives at a node already closed and the graph "
                      f"shows them contradicting (`next_steps` reports it as `refuted_passes`). Waiting costs a "
                      f"minute; the other way costs the node.")
    if Signal.DELIVER.name in acts and (_open := engine.joins.open_parts(TaskId(task_id))):
        # A PARENT DELIVERS ITS CHILDREN'S AGGREGATE (Thm 1): delivering while they are open parks it in VALIDATING,
        # where no verdict can be given yet (human door, 2026-08-21: gone from `next_steps` for an hour). The machine
        # admits it (§12.4); what stops is this surface RECOMMENDING it.
        acts.remove(Signal.DELIVER.name)
        notes.append(f"DELIVER is not the move yet: {task_id} aggregates children that have not passed "
                     f"({', '.join(str(c.id) for c in _open)}), and a parent's verdict is the AND over them (Thm 1). "
                     f"Delivering now parks it in VALIDATING — no verdict can be given, and its own PASS is refused. "
                     f"Drive those children first.")
        withheld[Signal.DELIVER.name] = notes[-1]
    if Signal.ASSIGN.name in acts and t.state.name in ("DONE", "ABANDONED"):
        # …WHEN IT IS OPEN, SAY WHAT IT IS: on a finished root the bare word "ASSIGN" reverted DONE to OFFERED, dropped
        # the verdict and spent a reopen (human door, 2026-08-22; a re-delivery and a $0.60 re-validation to recover).
        asides.append(f"ASSIGN on {task_id} is a REOPEN (R′, §12.14), not a no-op: it returns a "
                      f"finished node to OFFERED, its verdict is GONE (re-earned by fresh contact) "
                      f"and one of its {t.max_reopens} reopens is spent. `reopen` is the same act "
                      f"under its own name, and `revise` is it with a new contract."
                      + (f" Here: {_shut}" if (_shut := engine.reopen_refusal(TaskId(task_id))) else ""))
    if Signal.ASSIGN.name in acts and t.state.name not in ("DONE", "ABANDONED", "IDLE"):
        # …AND ON A LIVE NODE, WHICH DOOR PERFORMS IT: a re-ASSIGN is a REVISION (Inv-1) and carries a packet, which
        # `signal` has no parameter for — refused on every reassignable node through that door (probed 2026-09-07).
        asides.append(f"ASSIGN on {task_id} is a REVISION (a re-ASSIGN under the same id, Inv-1): it "
                      f"returns the node to OFFERED with a NEW contract, which the executor then "
                      f"re-consents to. It carries that contract, so `signal` cannot send it — "
                      f"`revise('{task_id}', …)` is its door for criteria, deadline and "
                      f"accepted_risks; a Del change is `reassign` (its own revision, §12.3, counted "
                      f"by q_Del). Either way a revision does not cascade and the subtree is kept.")
    return acts, ("  ·  ".join(notes + asides) or None), withheld


def available_actions(engine: Engine, task_id: str, agent: Optional[str] = None) -> dict:
    """(Rarely needed — next_steps' directive already names the required action.) The protocol signals
    valid in this node's state for the ASKER's role: {actions, state, role, why_none, gate}.
    Defaults to YOU; `agent=<name>` asks as someone else (the human door names its user), and
    `agent="*"` is the any-role view the UI wants. The list is what would actually be ACCEPTED —
    signals the seam gate (§10.3) or the plan gate (§11.5) would refuse are removed, with `gate`
    saying why and what opens them.

    An EMPTY list is an answer, and it used to be given as a bare `[]`. Measured live: a person held
    a node they had just delivered, asked what they could do with it, and got nothing — while
    `signal` on the same node explained in full that a PASS by the node's own executor needs an
    independent verdict first (§10.3). The list was TRUE; the silence around it was the defect. So
    when nothing is open, the reason is said here too, in the same words the signal would use."""
    # WHOEVER IS ASKING, ASKED AS THEMSELVES. With no `agent` this listed every signal open in the
    # state to ANY role — four actions the caller could not perform, and no `why_none` either. The
    # door pins identity for `signal` ("impersonation is impossible") and forgot it here; measured
    # 2026-08-20 through the MCP door. `agent="*"` is the old any-role view, which the UI wants.
    who = _agent_id() if agent is None else agent
    acts = [s.name for s in engine.available_actions(TaskId(task_id),
                                                     None if who == "*" else AgentId(who))]
    t = engine.graph.get_task(TaskId(task_id))
    if t is None:
        return {"error": f"unknown task {task_id}"}
    # …and what the SEAM would refuse comes out of the list, with the reason. Listing PASS where the
    # verifier ≠ executor gate rejects it is the same lie in the other direction: the affordance
    # surface must agree with the machine, in both directions (§10.3).
    acts, gate_note, withheld = _gated_out(engine, t, task_id, who, acts)
    out = {"task_id": task_id, "state": t.state.name, "actions": acts}
    # WHOSE the open acts are, where the state is about that and not about the acts. ESCALATED
    # admits CANCEL and ASSIGN — both the ISSUER's — and a list of two signals does not say so; a
    # reader who does not know they are his reads "the node admits things" and keeps polling.
    if t.state == State.ESCALATED:
        out["waiting_on"] = "issuer"
        out["recovery"] = engine.issuer_moves_on(TaskId(task_id))
    if gate_note:
        out["gate"] = gate_note
    if withheld:
        # The same thing keyed by signal: `gate` is the sentence a person reads, `withheld` is what
        # anything else has to ask — which signal was taken out, and why. Both come from one place,
        # so they cannot say different things.
        out["withheld"] = withheld
    if not acts and gate_note:
        # THE GATE ALREADY SAID IT. When a gate emptied the list, the generic "why nothing is open"
        # below explains the ROLE rules instead — true in general and wrong about this node, which
        # is exactly the sentence a reader acts on (walked by hand 2026-08-21: a consumed child was
        # explained as a seam problem).
        out["why_none"] = gate_note
        return out
    if not acts:
        anyone = [s.name for s in engine.available_actions(TaskId(task_id))]
        role = engine._role_of(AgentId(who), t) if who != "*" else None
        issuer = engine.graph.issuer_of(TaskId(task_id))
        out["role"] = role.name if role is not None else None
        if not anyone:
            out["why_none"] = (f"{who} has no move on {task_id}: nothing is open to ANY role in "
                               f"{t.state.name} — the state is terminal, or the node waits on the "
                               f"system clock. `next_steps` names what the graph is waiting on.")
            # …and for a settled node, WHICH recovery the canon leaves open, since "terminal" alone
            # sent a person hunting through four verbs for one that was not refused (§12.14 gives a
            # different answer for each terminal; walked by hand 2026-08-21).
            if t.state == State.ESCALATED:
                # NOT a settled node, and this used to say it was ("it is not reopened and takes no
                # revision") — the sentence that sent an agent to build a second root. ESCALATED is
                # the issuer's waiting state (§12.5) and the moves are his.
                out["recovery"] = f"'{task_id}' is waiting: {engine.issuer_moves_on(TaskId(task_id))}"
            elif t.state in (State.DONE, State.ABANDONED):
                out["recovery"] = (
                    f"'{task_id}' is finished. `reopen` puts it back to OFFERED under its standing "
                    f"contract (R′, §12.14) unless the graph has CONSUMED it — the refusal says which "
                    f"gate stopped it; `revise` reopens it WITH a new contract.")
        elif role is None:
            out["why_none"] = (f"{who} holds no role on {task_id}: its executor is "
                               f"{t.assignee or 'nobody'} and its issuer is {issuer}. Each signal "
                               f"belongs to one of those two (§11.2); here {', '.join(anyone)} "
                               f"is/are open to them.")
        else:
            # Both roles on one person is the ordinary solo case, and the role is resolved as
            # EXECUTOR first — so a person who is also the issuer sees nothing at all in VALIDATING
            # and is told nothing about why. The seam rule is the reason, and it is worth stating.
            same = (t.assignee == AgentId(who) and issuer == AgentId(who))
            out["why_none"] = (
                f"{who} is the {role.name.lower()} of {task_id}, and in {t.state.name} the open "
                f"signals ({', '.join(anyone)}) belong to the other side of the seam"
                + (f" — you are BOTH here, and the system still reads you as its executor: a node's "
                   f"own executor cannot sign its verdict (verifier ≠ executor, §10.3). Record an "
                   f"independent one (`record_verdict` with what you observed, or `validate_result`), "
                   f"then signal."
                   if same else
                   # THE OTHER SIDE, named correctly. This said "moves on {issuer}'s signal" for
                   # every role — so a person who WAS the issuer, holding a node whose open signal
                   # belongs to its executor, was told the node waits on themselves. Measured
                   # 2026-08-21 on a CANCELLING node: "dana is the issuer … this one moves on dana's
                   # signal", with the actual other side being `agent`.
                   f". Drive your own nodes; this one moves on "
                   f"{t.assignee if role is Role.ISSUER else issuer}'s signal."))
    return out


def _awaiting(engine: Engine, t) -> Optional[str]:
    """Who the graph is waiting for on this node, when the state name alone does not say.

    `validator` — an independent validation of this delivery is running · `issuer` — a verdict is on
    the record and the signal is owed · `verdict` — delivered, nobody validating yet · `executor` — a
    registered machine holds it. None where the state speaks for itself."""
    if t.state.name == "VALIDATING":
        if engine.claims.validation_in_flight(t.id):
            return "validator"
        return "issuer" if engine.current_exec_verdict(t.id) is not None else "verdict"
    if t.state.name in ("EXECUTING", "REWORKING") and engine.workforce.kind_of(t.assignee) == "llm-executor":
        return "executor"
    return None


def get_graph(engine: Engine) -> dict:
    """The whole graph: nodes (id, name, state, parent) + edges (parent-child and dependency). The bird's-eye
    view — use it to see overall progress / where the frontier is."""
    tasks = engine.all_tasks()
    nodes = [{"id": str(t.id), "name": t.label(), "state": t.state.name,
              "assignee": t.assignee,        # who holds this node — the graph read answered `null` for
                                             # every node while `get_task` named the executor (2026-08-21)
              "done_reason": t.done_reason.name if t.done_reason else None,  # ABANDONED = a tombstone (grey it)
              # …AND WHAT A VALIDATING NODE IS WAITING FOR. "Being validated" and "validated, waiting for
              # your signature" are the same state name and opposite situations: one costs you
              # nothing to wait out, the other waits for YOU. A driver polled `get_graph` for ten
              # minutes on a node whose verdict had been on the record almost the whole time —
              # only `next_steps` said so (measured on the human door 2026-08-22).
              "awaiting": _awaiting(engine, t),
              # …AND HOW A CLOSED NODE CLOSED. `[x]` over an instrument's probes and `[x]` over a
              # name invented in the same command are not the same fact, and the only surfaces that
              # said which were the completion answer's lists — reported when a graph is COMPLETE,
              # i.e. never while there is still work in it (wave 26, 2026-09-06). `null` until the
              # node settles positive: there is nothing to weigh about a node still in flight.
              "closure": engine.closure_of(t.id),
              "parent_id": str(t.parent_id) if t.parent_id else None} for t in tasks]
    edges = [{"source": str(t.parent_id), "target": str(t.id), "type": "parent-child"}
             for t in tasks if t.parent_id]
    # …a dependency edge saying whether execution FOUND it (a BLOCK's discovery) rather than the plan declaring it
    edges += [{"source": str(d.from_id), "target": str(d.to_id), "type": "dependency", "discovered": d.discovered}
              for d in engine.graph.dep_edges()]
    # …and WHO HOLDS WHAT: the mode is part of the state a reader of the graph is owed — under AUTO the
    # customer reads the work's status here, and a mode changed mid-run is visible where the work is.
    # …AND THE MOVE IT WAITS ON, as entering a project and every signal's reply carry it: a SOLO-dispatch holder that
    # entered through this read saw nine nodes OFFERED to it, never heard "ACCEPT; your hands perform it", tried to
    # build them itself without the tools and gave up (GB_coreutils_tmmw26001, 2026-10-09)
    return {"nodes": nodes, "edges": edges, "mode": engine.mode(), **next_for(engine, _agent_id())}


def list_holes(engine: Engine, root_id: Optional[str] = None) -> dict:
    """Every UNMET structural check across the whole graph (or the subtree under root_id) — the full gap list.
    Call this AFTER auto_decompose / before driving execution: a decomposed graph may come back with failing
    checks (coverage/glue/ACCEPTED_RISKS/…); this shows them ALL at once. Each says what it does (`kind`): a `gate`
    refuses the admission of a split that carries it, and one opened after admission is yours to repair — the
    children already issued keep working; a `flag` (a deadline crossing along Dep met after the split was
    admitted) is the consumer's issuer's to re-ASSIGN or let run, refusing nothing (§12.10); `advisory` holds
    nothing. Returns [{task_id, name, check, kind, details}];
    an empty list means the plan passes Level 0/1 — which is NOT the Level-2 verdict (`get_review`
    says whether the causal check has spoken).

    Answers `{holes, count}` — the list is under `holes`. It used to be a bare array, so a client
    reading the scope off every other verb's answer crashed on this one (HTTP door, wave 27,
    2026-09-06), and `count: 0` says "clean" in the same breath as the empty list."""
    _holes = engine.graph_holes(TaskId(root_id) if root_id else None)
    return {"holes": _holes, "count": len(_holes)}


def get_dependencies(engine: Engine) -> list[dict]:
    """All Dep edges (declared = derived from criteria `depends_on`; discovered = BLOCK-surfaced;
    provisional = discovered edge awaiting RESOLVE_BLOCK adjudication)."""
    return [{"from": e.from_id, "to": e.to_id,
             # WHICH END IS WHICH, said rather than conventional. `from`/`to` do not carry a
             # direction on their own, and a competent reader took them for "waits on" — the exact
             # opposite — then read a correct graph as three edges wired backwards and reported it
             # (HTTP door, 2026-09-02; the frontier was gating correctly the whole time, which a
             # probe showed). `add_dependency` says which is which in its help; the READ said
             # nothing, and this is where the direction is actually consumed.
             "producer": e.from_id, "consumer": e.to_id,
             "means": f"{e.to_id} waits for {e.from_id} — it consumes what {e.from_id} produces",
             "discovered": e.discovered,
             "provisional": e.provisional, "glue": e.glue}
            for e in engine.get_dependencies()]




def usage(engine: Engine, detail: bool = False) -> dict:
    """What this project's graph COST in model calls: totals and a per-ROLE split (decomposer /
    l2_review / validator / executor / undecided-obligations), and with `detail=true` the calls
    themselves.

    The money lived on ONE door — the HTTP one, as `/api/usage` — so an agent or a person at the
    shell could not ask what a run had cost, and delegated execution in particular was invisible
    (measured on the agent door 2026-08-21: "for a system whose whole pitch is that the graph is the
    truth, the graph cannot tell me what the run cost"). `costed_calls` sits beside `cost_usd`
    because a transport that reports no price contributes zero, and a total that cannot tell "free"
    from "not reported" is the same ⊥-as-zero error the metrics refuse elsewhere."""
    out = engine.usage_totals()
    if detail:
        # WHICH NODE EACH CALL BELONGED TO, under the name every other verb uses. The rows carry it
        # as `node_id`; a reader looking for `task_id` — the word this whole surface speaks — saw
        # nulls and reconstructed the attribution by hand, correlating durations against the log
        # (measured 2026-08-22: "a $2.75 line item with no node attribution is not an accounting").
        out["calls_detail"] = [{**r, "task_id": r.get("node_id") or None}
                               for r in engine.usage_calls()]
        # …and the same split BY NODE, which is the question a bill actually raises.
        by_node: dict = {}
        for r in out["calls_detail"]:
            row = by_node.setdefault(r["task_id"] or "(no node)", {"calls": 0, "cost_usd": 0.0})
            row["calls"] += 1
            row["cost_usd"] = round(row["cost_usd"] + (r.get("cost_usd") or 0.0), 4)
        out["by_node"] = by_node
    out.update(_where_the_money_went(out))
    return out


def _where_the_money_went(out: dict) -> dict:
    """The biggest stage and its share, said rather than left to be divided.

    The per-stage table has been right all along and the reader still has to compute the one number
    the bill actually raises. This is not hypothetical: on 2026-09-05 I read an instrument's
    `usage_inner_agent_only` as a run's total and was out by 3x, on a measurement whose PRE-REGISTERED
    question was the validator's share of spend — with the true split ($2.33 of $3.44, 68% on validation)
    sitting one division away in the same object. A surface whose doctrine is that a metric arrives
    with what it means owes the division too.
    """
    stages = {k: (v.get("cost_usd") or 0.0) for k, v in (out.get("by_stage") or {}).items()}
    total = out.get("cost_usd") or 0.0
    if not stages or total <= 0:
        return {}
    top = max(stages, key=stages.get)
    return {"largest_stage": {
        "stage": top, "cost_usd": round(stages[top], 4),
        "share": round(stages[top] / total, 3),
        "means": f"{stages[top] / total:.0%} of this project's model spend went to `{top}`"
                 f" (${stages[top]:.2f} of ${total:.2f}). The rest is in `by_stage`."}}


def metrics(engine: Engine) -> dict:
    """Self-measuring quality vector Q = (q_T, q_D, q_V, q_Dep, q_Del), each with what it MEANS.

    A null is ⊥ — an empty population, not a zero (§15.4): no event of that kind has happened yet, and
    the difference matters when the number is read as a health score."""
    out = engine.metrics()
    # WHAT THE NUMBER IS MADE OF, for the one metric people read as an accusation. A bare `q_T: 0.0`
    # over a graph whose plan was honestly repaired on the gate's findings looks like a failing grade
    # for the person doing the repairing (measured on the human door 2026-08-21); the nodes that
    # contributed the event are the answer to "why", and the reader can check them against the log.
    tasks = engine.all_tasks()
    # …AND WHICH KIND OF DEFECT EACH WAS. Both members of the canon's numerator are spec defects
    # (§15.4), and they are found at opposite ends: a CHALLENGE is an executor meeting a broken
    # contract while working under it, and a criteria change is one caught before the work — often
    # by this product's own plan gate. A user who closed nine gate findings correctly read a low
    # q_T as a grade on themselves (agent door, 2026-09-02). The number does not move; what it is
    # made of is now legible without a paragraph of self-defence.
    _challenged, _repaired = q_T_numerator(engine.graph)
    if _challenged or _repaired:
        out["q_T_from"] = {"contracts_issued": len(tasks),
                           "counted_against": _challenged + _repaired,
                           "disputed_by_an_executor": _challenged,
                           "repaired_before_the_work": _repaired,
                           "note": ("both are spec defects and both count (§15.4). The second kind "
                                    "was caught before anyone executed against it — which is the "
                                    "plan gate doing its job, not a grade on whoever closed it.")}
    # …and the same for q_V, which was the one number with no way to see inside it: a reader watched
    # it go 0.5 then 0.8 with nothing naming WHICH pass had been taken back (measured 2026-08-21).
    if reversed_ := q_V_reversed(engine.graph):
        out["q_V_from"] = {"passes": sum(1 for t in tasks if settled_positive(t)),
                           "later_found_wrong": reversed_}
    # BOTH doors serve every number with what it is about — `false_fail_share` runs the
    # OPPOSITE way to every q_* (high is bad) and is the one most easily read backwards.
    return {**out, "means": {k: v for k, v in {**Q_MEANS, **DIAGNOSTIC_MEANS}.items()
                             if k in out}}


# ── AUTHORING (each desugars to the 12-signal FSM — logged, no bypass) ────────

def del_by_mode(engine: Engine, parent_id: Optional[str], asked: Optional[str]) -> AgentId:
    """Del of a node about to be issued: the one the caller named, checked against the project's mode.

    With no mode set it is exactly what it always was — the named party, else the caller. With one,
    the mode decides and a name that contradicts it is REFUSED (a ValueError the verbs return as a
    refusal): the mode is the user's choice of who holds what, and a habitual `assignee=` must not
    quietly re-decide it. A name that agrees — the user-agent where it holds, or another of this
    project's executors where the system holds and it keeps the seam — is kept."""
    want = engine.del_for(TaskId(parent_id) if parent_id else None)
    if want is None:
        return AgentId(asked or _agent_id())
    if not asked or str(asked) == str(want):
        return want
    me = _agent_id()
    parent = engine.graph.get_task(TaskId(parent_id)) if parent_id else None
    system_side = str(want) != me
    if system_side and str(asked) != me and AgentId(asked) in engine.workforce.executor_pool()             and (parent is None or str(asked) != str(parent.assignee)):
        return AgentId(asked)
    mode = engine.mode_kind()
    # the lift is the caller's own (§12.16 (ii)), and `reassign` takes a name it cannot leave out (critic round 10)
    others = [str(a) for a in engine.workforce.executor_pool() if parent is None or str(a) != str(parent.assignee)]
    lift = (f"name one of this project's executors ({', '.join(others) or 'none registered'})"
            if system_side else f"keep it with you ({me})")
    raise ValueError(
        f"this project runs in {mode}: a node here is held by "
        f"{'the system (an executor of this project, not its parent’s)' if system_side else 'you'}, "
        f"so it cannot be given to {asked}. {lift[0].upper() + lift[1:]}, or — where the name is optional — "
        f"leave `assignee` out and the mode assigns it; the mode itself is the user's choice of who holds "
        f"what, and only the user changes it.")


def _agent_id() -> str:
    """The calling agent's standing identity. Identity is TRANSPORT-derived, not configured: this tool
    surface (MCP/CLI) is the AGENT's single entry point — the UI is the human's door and always passes an
    explicit name — so an omitted `assignee` can only mean "the agent itself". Works out of the box as
    `agent`; GFSO_AGENT_ID merely RENAMES it (multi-agent future), it is never required."""
    return _config_agent_id()


def create_task(engine: Engine, task_id: str = "", spec: Optional[dict] = None,
                assignee: Optional[str] = None,
                parent_id: Optional[str] = None, deadline: Optional[str] = None,
                covers: Optional[list] = None) -> Optional[dict]:
    """Create a node. Desugars to ASSIGN (creation IS the ASSIGN effect, logged). `task_id` auto-generated if
    omitted; `deadline` = an ISO-8601 string (completes T=(spec,criteria,deadline), §2). spec =
    {name: short title (≤6 words), description: the full text, criteria: [{name, description}],
    accepted_risks: [{item, predictability, p, impact, justification, invalidation_condition, component?}],
    scope: [str]}.
    `spec.accepted_risks` is the packet's PRE-FILL — risk events the issuer hands down with the task, task data
    (§9.2). The register of a SPLIT is its decomposer's and rides `decompose(accepted_risks=…)`, with the split's
    own {denial: true, p, justification}; CHECK-4 gates the admission on it. Either way an entry is a risk EVENT
    with a materialization probability; a capability the goal deliberately excludes has no such probability
    and goes in `scope` instead. `predictability` is one of exactly three
    (STD-2, §9.3 — a burden-of-proof scale, not high/medium/low): ORDINARY (occurs regularly in the
    domain ⇒ it belongs in the DECOMPOSITION, not here), STATISTICAL (P estimable, event infrequent
    — admissible WITH a justification), EXTRAORDINARY (no precedent, not derivable from known
    models).
    `parent_id` + `covers` ADD ONE CHILD to a split that already stands; `covers` names the parent's criteria
    this child is responsible for (§2.4). A NEW split — a parent's first children — is admitted whole by
    `decompose(parent, children, accepted_risks=…)`: one child alone carries no split register, so its
    admission is refused (§11.5, CHECK-4).
    `assignee` (Del) defaults to `agent` = YOU (this tool surface is the agent's door; the UI is the
    human's and always names its user) — omit it when you will execute the node yourself; name someone
    else ONLY when delegating for real (the FSM then rejects your executor signals on that node)."""

    tid = TaskId(task_id or uuid.uuid4().hex[:8])
    # CREATING AND REVISING ARE NOT THE SAME CALL. `create_task` desugars to ASSIGN, and ASSIGN on a
    # live node is a revision (canon-legal, Inv-1) — so a verb named CREATE silently replaced an
    # existing contract. Measured 2026-08-20: an agent that believed it was creating a root wrote
    # over another session's RUNNING project — name, description, criteria, accepted risks and scope
    # replaced, its children left hanging under a goal that was never theirs — and the original was
    # unrecoverable, because the log keeps the revision EVENT and not the superseded spec.
    # Revision stays available and stays explicit: `revise` / `edit_criteria` / `reassign`.
    if (_existing := engine.graph.get_task(tid)) is not None:
        return {"error": f"'{tid}' already exists — it is '{_existing.spec.name or tid}' in state "
                         f"{_existing.state.name}, owned by {_existing.assignee or 'nobody'}. "
                         f"`create_task` creates; to CHANGE this node use `revise` (whole contract), "
                         f"`edit_criteria` (its criteria) or `reassign` (its executor) — each is a "
                         f"logged revision under the same id (Inv-1, §12.3). If you meant a "
                         f"different node, give it a different id; if you meant another project, "
                         f"pass `project=` explicitly."}
    # A CONTRACT IS NOT A SENTENCE. `spec` given as a plain string crashed inside the parser and
    # came back as a 500 with no body over HTTP — measured live, and the caller had no way to learn
    # that a node is made of criteria rather than a description. Refused in the verb's own terms.
    if spec is not None and not isinstance(spec, dict):
        return {"error": f"`spec` must be the contract object, not {type(spec).__name__}: "
                         f"{{name, description, criteria: [{{name, description}}], accepted_risks, "
                         f"scope}}. A node is defined by its CRITERIA — what would show it done — "
                         f"and a bare sentence names none. What you passed reads as the "
                         f"`description`; write the criteria that would settle it."}
    # ONE ROOT PER PROJECT, refused in the verb's own terms rather than as an internal breach. A
    # parentless node is not a free-standing task — it is THE goal, and V(root) is the project's
    # verdict, so a second one is a second verdict with no rule composing them. The refusal names
    # the two acts that were meant, because a caller told only "no" invents a third.
    if not parent_id:
        _root = root_of(engine.all_tasks())
        if _root is not None and str(_root.id) != str(tid):
            return {"error": (
                f"this project already has its root, '{_root.id}' "
                f"({_root.label(60)}), and a project has exactly one. "
                f"If '{tid}' is part of that goal, it enters the root's split: `decompose('{_root.id}', "
                f"children=[…], accepted_risks=[…])` admits the split whole, each child's `covers` naming the "
                f"criteria it is responsible for; once that split stands, `create_task(parent_id='{_root.id}', "
                f"covers=[…], …)` adds one child to it. If it is a different goal, it belongs in a different project: "
                f"`use_project('<name>')`.")}
    dl = _deadline(deadline)
    # The SPEC is parsed outside the guard below: a malformed packet is the caller's own shape
    # error, and its message (which word was not a predictability, say) is the answer — the guard is
    # for the engine's ADMISSION refusals, which are about a well-formed packet.
    _spec = _spec_from(spec or {})
    try:
        _del = del_by_mode(engine, parent_id, assignee)
        t = engine.assign_task(tid, _spec, _del,
                               parent_id=TaskId(parent_id) if parent_id else None, deadline=dl,
                               # a root under a mode keeps its creator as the goal's issuer even
                               # when the mode hands its execution to the system; with no mode a
                               # root is self-assigned, as before
                               issuer=AgentId(_agent_id()) if not parent_id and engine.mode() else None,
                               covers=tuple(covers or ()))
    except ValueError as ex:
        # AN ADMISSION REFUSAL IS AN ANSWER, NOT A CRASH. The engine refuses a packet whose criteria
        # pin no procedure and a child issued under a parent that is settling or settled (§12.7/
        # §12.16); through this door those are ordinary caller mistakes with a way out written in the
        # message, and a traceback is the one shape that hides it — the same reading the one-root
        # refusal above already had.
        return {"error": str(ex)}
    return task_out(t)


def _deadline(raw):
    """An ISO-8601 string into the `datetime` the graph compares, or None.

    ONE owner, because two verbs feed the same field and only one of them parsed it: `create_task`
    turned the string into a datetime and `decompose` (once it began carrying the field at all)
    would have passed the raw string straight through, so CHECK-3 met `str >= datetime` and RAISED
    inside the structural gate — a crash where a check belongs. A value already a `datetime` is
    returned untouched, which is what the engine's own callers pass.
    """
    if raw is None or raw == "":
        return None
    return raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))


#: a spec's keys as `_spec_from` reads them — each the Spec field of the same name
_SPEC_KEYS = ("description", "criteria", "accepted_risks", "risk_components", "scope", "name", "covers_risks")


def _named_spec(engine: Engine, child: dict) -> Spec:
    """A child's spec as this act names it. A standing child's field the caller leaves out stands as it is: a
    re-admission names what changes, and a key left out of a re-listing read as emptied — its packet's pre-fill, say —
    re-issued a child the caller meant to leave alone (critic r15)."""
    spec = _spec_from(child["spec"])
    was = engine.graph.get_task(TaskId(child["task_id"]))
    if was is None:
        return spec
    return dataclasses.replace(spec, **{k: getattr(was.spec, k) for k in _SPEC_KEYS if k not in child["spec"]})


def decompose(engine: Engine, parent_id: str, children: list[dict],
              mappings: Optional[list[dict]] = None,
              max_iterations: Optional[int] = None,
              accepted_risks: Optional[list] = None, risk_components: Optional[list] = None,
              drops: Optional[list] = None) -> list[dict]:
    """(Manual path — `auto_decompose` is the normal way to structure.) Break a node into children.
    `drops`: ids of live children this re-admission leaves out of the split — out of the plan at once, each cancelled
    with its subtree (§11.5, §12.6); how a split sheds a child its revised contract no longer needs. With `mappings`, `drops`
    or `accepted_risks` the re-admission may name no child (`children=[]`): the children at work are not re-issued.
    A standing child named again keeps every `spec` field left out, and is re-issued only where its contract changes;
    its `spec.accepted_risks` is its packet's pre-fill — `prefilled_accepted_risks` on `get_task`, whose
    `accepted_risks` is the register of the child's own split.
    Desugars to one ASSIGN per child. children: [{task_id, spec, assignee, covers, deadline?, max_iterations?}]; an
    omitted assignee = `agent` (you execute it yourself; name someone only to really delegate).

    `accepted_risks` (and its STD-3 `risk_components`) is the SPLIT's register, yours as its decomposer (§9.2):
    it rides this admission, no revision of the node; each entry as `edit_accepted_risks` documents it.

    The split is admitted whole (§11.5): every parent criterion MAPPED to the child that delivers it, every child
    covering one, its register given — or the admission is refused and no child is issued. Declare coverage either way: `covers: ["criterion", …]` on
    the child, or the flat `mappings=[{criterion_name, child_id}, …]`. (This text described `covers`
    while the code read only `mappings`, so a decomposition that used it came back successful with
    the mapping silently dropped, and the refusal arrived later as an unexplained coverage failure.)
    """
    if not children and not (drops or mappings or accepted_risks is not None or risk_components is not None):
        # AN EMPTY DECOMPOSITION IS NOT A MAPPING VERB. Called with `children=[]` and a `mappings=`
        # list, this returned `[]` and REPLACED the parent's whole mapping set — five criteria
        # uncovered and three children orphaned, from a call that looked like a no-op. It was the
        # only way the caller had found out of a dangling mapping, which is a different defect, now
        # closed (measured on the human door 2026-08-21).
        return {"error": f"decompose needs children, `mappings`, `drops` or a register: with none it changes no "
                         f"split. `decompose('{parent_id}', [], mappings=[…])` binds existing children to criteria, "
                         f"`drops=[…]` re-admits the split without children it no longer needs — the ones at work "
                         f"untouched either way — and `edit_criteria` re-authors the contract.",
                "refused": True}
    # THE SHAPE, SAID AS A REFUSAL. `children=parser` — a bare string where a list of objects goes —
    # reached the comprehension and came back as `string indices must be integers, not 'str'`: the
    # one refusal in this product that leaks an interpreter error instead of naming the way out
    # (measured on the human door 2026-08-22). Every other door answers with the shape it wanted.
    # Only the SHAPE here — a dict missing a key is a different refusal, and the one already written
    # for it names the key and points at `--help` (it reads better than anything this branch could).
    _bad = ([children] if isinstance(children, (str, bytes))
            else [c for c in children if not isinstance(c, dict)])
    if _bad:
        _shape = ("[{'task_id': <id>, 'spec': {'description': …, 'criteria': "
                  "[{'name': …, 'description': …}]}, 'assignee': <who>, "
                  "'covers': [<parent criterion>]}]")
        return {"error": (f"decompose needs `children` as a LIST OF OBJECTS, one per child: "
                          f"{_shape}. Got: {_bad[0]!r}. On the CLI a nested value is passed as "
                          f"JSON, or from a file with `children=@children.json`."),
                "refused": True}
    # THE DEADLINE RIDES ALONG. `decompose_task` takes `(id, spec, assignee)` OR
    # `(id, spec, assignee, deadline)`, and this always built the three-tuple — so no child created
    # by the product's own decomposition verb could carry one, and CHECK-3 answered
    # `met — "no child deadlines"` on EVERY decomposition the product builds. A check whose subject
    # cannot exist is vacuously true, which is not a check (audited 2026-09-05, F3). The engine's
    # docstring already named the consequence; what was missing was the field reaching it.
    # Its absence stays silent, by the same rule as everywhere else: a plan that declares no
    # deadlines is not thereby defective (`formal/README.md` #6). What changes is that a plan which
    # DECLARES one is no longer quietly stripped of it.
    kids = [(TaskId(c["task_id"]), _named_spec(engine, c),
             del_by_mode(engine, parent_id, c.get("assignee")), _deadline(c.get("deadline")), c.get("max_iterations"))
            for c in children]
    declared = [CriterionMapping(name, TaskId(c["task_id"]))
                for c in children for name in (c.get("covers") or ())]
    # THIS VERB ADDS CHILDREN; IT DOES NOT RE-AUTHOR THE PARENT'S COVERAGE. `decompose_task` reads a
    # non-None mapping list as the FULL set and prunes everything else — right for the refine path,
    # which passes the whole set, and wrong here, where the list is built from the children of THIS
    # call alone. So a second `decompose` adding one child unmapped every child added before it:
    # measured, `CHECK-1: uncovered criteria: a` and `CHECK-1b: children addressing no parent
    # criterion: k1` immediately after a call that only added `k2` — and those orphaned children can
    # no longer start, because their parent's plan stops passing Level 0. The `children=[]` refusal
    # above was written for exactly this damage and guards only the empty spelling. Merging with what
    # the parent already carries is what "adds children" means; removing a pair is `edit_criteria`
    # (which re-authors the contract) or `map_criterion` (which binds one).
    # …of the ACTIVE children only: a settled cancellation took its child out of the plan (§12.6), and a mapping
    # carried onto it would be read by the admission as coverage by a node that is not there — the re-decomposition
    # covering around a dropped child was refused for the drop it repairs
    _parent = engine.graph.get_task(TaskId(parent_id))
    _active = {str(k.id) for k in engine.graph.get_active_children(TaskId(parent_id))} - {str(d) for d in (drops or ())}
    _existing = [m for m in (_parent.criterion_mappings if _parent is not None else ()) if str(m.child_id) in _active]
    _new = ([CriterionMapping(m["criterion_name"], TaskId(m["child_id"])) for m in (mappings or [])]
            + declared)
    _pairs, maps = set(), []
    for m in _existing + _new:
        if (m.criterion_name, str(m.child_id)) not in _pairs:
            _pairs.add((m.criterion_name, str(m.child_id)))
            maps.append(m)
    maps = maps or None
    # The rework bound rides the ASSIGN of every child: §12.4 bounds the DELIVER→FAIL loop and
    # §12.15 states no failure mode pins the number, so it is a term of the CONTRACT chosen per
    # decomposition — not a property of whichever process happens to be serving.
    register = (Register(_accepted_risks_from(accepted_risks or []), tuple(risk_components or ()))
                if accepted_risks is not None or risk_components is not None else None)
    return [task_out(t) for t in engine.decompose_task(TaskId(parent_id), kids, maps, max_iterations,
                                                       register=register,
                                                       drops=tuple(TaskId(str(d)) for d in (drops or ())))]


#: The closed sets a verb's string parameters accept, as DATA — keyed by VERB and parameter, never by
#: parameter alone. The refusals name them perfectly and the docstrings spell them out, but both are
#: prose, so a caller building against the catalogue had to parse English or be refused once per verb
#: (HTTP door, 2026-09-02: a tester silently no-op'd five edits before a refusal told them).
#:
#: Keyed by verb because the same NAME is not the same set: `signal`'s `reason` is free text — why a
#: node is blocked or cancelled — while `revise`'s is the §15.4 causal type. Keying by name alone
#: made the catalogue tell callers that a BLOCK reason must be one of four words, which is exactly
#: the kind of confident falsehood this whole surface exists to stop emitting.
#:
#: Values derived from the enums that enforce them, so a member added to the vocabulary cannot fail
#: to appear here.
_REVISION_REASONS = [r.name.lower() for r in RevisionReason]
_VERDICT_WORDS = [str(Verdict.PASS), str(Verdict.FAIL)]
PARAM_CHOICES = {
    "edit_criteria": {"reason": _REVISION_REASONS},
    "reassign": {"reason": _REVISION_REASONS},
    "revise": {"reason": _REVISION_REASONS},
    "record_verdict": {"verdict": _VERDICT_WORDS},
    "signal": {"self_validation": _VERDICT_WORDS},   # `reason` here is FREE TEXT — see above
}


def _reason_from(reason: Optional[str]):
    """§15.4 causal typing at the transport boundary: an optional reason string → RevisionReason.
    Unknown strings are refused loudly (a mistyped reason silently untyped would corrupt q_T/q_Del)."""
    if not reason:
        return None
    try:
        return RevisionReason[reason.upper()]
    except KeyError:
        valid = ", ".join(r.name.lower() for r in RevisionReason)
        raise ValueError(f"unknown revision reason {reason!r} — valid: {valid}")


def _contract_moved_under_you(before, expect_criteria) -> Optional[dict]:
    """Refuse a WHOLESALE replacement written against a contract that has since changed.

    `revise` and `edit_criteria` are read-modify-write by construction: a caller reads the node,
    edits the set it saw, and sends the whole thing back. Nothing checked that the set it saw is
    still the set that is there — so a concurrent author (the dispatcher's own `auto_decompose`
    refining in the background is the ordinary case) has its criteria overwritten by a caller who
    never knew they existed. This is what wave 26's "`project()` truncates the criteria" turned out
    to be when it was probed: the projection showed all seventeen, and five were written between the
    reader's read and their edit (2026-09-06).

    Opt-in, and keyed on the NAMES a caller actually reads: `expect_criteria=[…]` says "these are
    the criteria I saw". No argument = the old behaviour, because a caller authoring a fresh
    contract has nothing to have read.
    """
    if expect_criteria is None or before is None:
        return None
    seen = {str(c.get("name") if isinstance(c, dict) else c) for c in expect_criteria}
    now = {c.name for c in before.spec.criteria}
    if seen == now:
        return None
    _added, _gone = sorted(now - seen), sorted(seen - now)
    return {"refused": True, "contract_moved": True,
            "you_expected": sorted(seen), "it_now_carries": sorted(now),
            **({"added_since_you_read": _added} if _added else {}),
            **({"gone_since_you_read": _gone} if _gone else {}),
            "error": (f"the contract changed after you read it, and this call REPLACES the whole "
                      f"set — sending it would drop "
                      + (f"{', '.join(_added)} (added since)" if _added else "nothing that was added")
                      + (f" and re-add {', '.join(_gone)} (removed since)" if _gone else "")
                      + f". Read the node again, merge what you meant to change into the set it "
                        f"carries now, and re-send with the new `expect_criteria`.")}


def revise(engine: Engine, task_id: str, spec: Optional[dict] = None, agent: str = "",
           reason: Optional[str] = None,
           expect_criteria: Optional[list] = None,
           deadline: Optional[str] = None,
           max_iterations: Optional[int] = None,
           block_sources: Optional[list] = None, block_refuted: bool = False) -> Optional[dict]:
    """Revise a node's whole spec. Canon v3.7 Inv-1: a spec change = re-ASSIGN under the SAME id → OFFERED
    (NOT a CANCEL — no cascade, no tombstone; the executor re-ACCEPTs the new contract). The subtree is
    RETAINED (revision ≠ abandonment); if a criteria change strands a child's coverage it shows up as a
    CHECK-1/CHECK-1b failure to resolve. `agent` must be the issuer (ASSIGN is an issuer signal).
    `reason` (optional, §15.4): why the revision — spec_defect (criteria were wrong; counts in q_T) |
    scope_expansion (sanctioned §15.4; never counts) | capability_mismatch | other.

    **WHOLE means whole: a key you omit is a key you DELETE.** Passing `{description: …}` alone
    wipes the criteria, the ACCEPTED_RISKS, the scope and every criterion→child mapping — measured
    2026-08-21, where the reply looked like an ordinary success and the loss surfaced later as two
    failing checks. So an omission that would DESTROY something is refused here and named; pass the
    field (even unchanged) to mean it, or use the verb that carries the rest: `edit_criteria`,
    `edit_accepted_risks`, `reassign`.

    `expect_criteria=[<the names you read>]` makes the replacement CONDITIONAL: if the contract
    moved between your read and this call — a background `auto_decompose` refining it is the
    ordinary case — the call is refused and names what changed, instead of silently dropping work
    you never saw.

    A revision of a BLOCKED node may answer its block as RESOLVE_BLOCK does (§15.5): `block_sources` = the
    prerequisites you confirm (the rest refuted), `block_refuted=true` = none was a real prerequisite. Unanswered,
    the block's records close and still count in q_Dep."""
    t = engine.graph.get_task(TaskId(task_id))
    if t is None:
        return {"error": f"unknown task {task_id}"}
    if (_moved := _contract_moved_under_you(t, expect_criteria)):
        return _moved
    # A REVISION THAT CHANGES ONLY A NON-SPEC PACKET FIELD NEEDS NO SPEC. The bound and the deadline
    # are packet fields like the criteria (Inv-1), and the issuer of an ESCALATED node most often
    # means exactly one of them — "the forecast was short, take more attempts". Demanding the whole
    # contract back to say that made the move the product ITSELF names unreachable: `revise` had no
    # `max_iterations` at all, and passing it inside `spec` was accepted and did nothing.
    if spec is None:
        if max_iterations is None and deadline is None:
            return {"refused": True,
                    "error": (f"`revise` needs either the new `spec` (the WHOLE contract) or a packet "
                              f"field to change on its own — `max_iterations` or `deadline`. To change "
                              f"one part of the contract and carry the rest, use `edit_criteria` or "
                              f"`edit_accepted_risks`.")}
    if isinstance(spec, dict):
        _loses = [name for name, key in (("criteria", "criteria"), ("ACCEPTED_RISKS", "accepted_risks"),
                                         ("scope", "scope"))
                  if getattr(t.spec, key, ()) and not spec.get(key)]
        if _loses:
            return {"error": f"this revision would DELETE {', '.join(_loses)} from {task_id}: "
                             f"`revise` replaces the WHOLE contract, and a key you omit is a key you "
                             f"remove. Pass them (unchanged is fine) if you mean to keep them — or "
                             f"use the verb that carries the rest: `edit_criteria` for criteria, "
                             f"`edit_accepted_risks` for the register, `reassign` for the executor. "
                             f"Its criterion→child mappings go with the criteria.",
                    # `refused` = the verb did not act (the marker the HTTP door reads for its
                    # status). A verb's other `{error: …}` answers report an OUTCOME — `signal`
                    # reaching the FSM and being told no is a successful call — and stay 200.
                    "refused": True, "would_delete": _loses}
    # spec=None carries the node's OWN contract unchanged — the bound-only revision above.
    return task_out(engine.revise(TaskId(task_id),
                                   _spec_from(spec) if spec is not None else t.spec,
                                   AgentId(agent),
                                   reason=_reason_from(reason), deadline=_deadline(deadline),
                                   max_iterations=max_iterations, block_sources=tuple(block_sources or ()),
                                   block_refuted=block_refuted))


def edit_accepted_risks(engine: Engine, task_id: str, accepted_risks: list,
                        agent: str = "") -> Optional[dict]:
    """Replace a node's ACCEPTED_RISKS (the RISK register: events with a materialization P — a scope
    boundary has no P and belongs in `scope`, via `edit_scope`, not here). Whose word it is decides where it lands:
    the node's Del — its decomposer — writes the SPLIT's register, admitted with the split, no revision (§9.2, §11.5);
    its issuer writes the packet's pre-filled ACCEPTED_RISKS, a revision the executor re-accepts (§10.1, §12.3). Each item:
    {item, predictability: STATISTICAL|EXTRAORDINARY, p: in (0, 1], impact, justification, invalidation_condition,
    component: the STD-3 component it accepts as a group, if any} — every field is mandatory per factor on a
    decomposed node (CHECK-4), and the register carries the split's own denial by S as one more entry:
    {denial: true, p: the recorded refutation rate of comparable splits, else your estimate, justification} (§9.5)."""
    agent = agent or _agent_id()
    was = engine.graph.get_task(TaskId(task_id))
    items = _accepted_risks_from(accepted_risks)
    # the split's register where there is a split and its decomposer writes; else the packet's pre-fill (a leaf's
    # register is vacuous, §9.2) — the issuer's revision, refused to anyone else
    decomposer = (was is not None and str(agent) == str(was.assignee)
                  and bool(engine.graph.get_active_children(TaskId(task_id))))
    out = task_out(engine.admit_register(TaskId(task_id), Register(items, register_of(was).components), AgentId(agent))
                    if decomposer else engine.edit_accepted_risks(TaskId(task_id), items, AgentId(agent)))
    if isinstance(out, dict):
        # THE REGISTER AS RECORDED, not just the item texts. The node projection carries each risk's
        # `item` alone, so a person who classified one as STATISTICAL with a justification and an
        # invalidation condition — the classification CHECK-4 demands — got back the sentence they
        # started from and no way to see whether the rest of it landed (walked by hand 2026-08-21).
        t = engine.graph.get_task(TaskId(task_id))
        out["accepted_risks_recorded"] = [
            n.to_dict()
            for n in ((register_of(t).items if decomposer else t.spec.accepted_risks) if t is not None else ())]
        out["written_as"] = ("the split's register (its decomposer's, §9.2)" if decomposer
                             else "the packet's pre-filled ACCEPTED_RISKS (its issuer's, a revision, §10.1)")
        out = _said_state_change(engine, task_id, was.state if was is not None else None, out)
    return out


def edit_scope(engine: Engine, task_id: str, scope: list, agent: str = "") -> Optional[dict]:
    """Replace a node's declared SCOPE BOUNDARIES — capabilities the goal deliberately does NOT
    include — carrying the rest of the spec. RMW over revise.

    §9.2 draws the line this verb exists for: ACCEPTED_RISKS holds uncertain EVENTS with a
    materialization P; a scope boundary has no P (its `estimate` field would be vacuous, breaking
    the roll-up), so it is objectified ON THE GOAL instead — visible in the graph rather than an
    implicit absence. The doctrine was already in the product and pointed two ways: the decomposer
    writes such an exclusion to `scope`, while this door's neighbour told a caller to put it in the
    goal's criteria, and there was no verb that could reach `scope` at all except a wholesale
    `revise`. One concept, one destination, one door.
    """
    agent = agent or _agent_id()
    was = engine.graph.get_task(TaskId(task_id))
    if was is None:
        return {"refused": True, "error": f"unknown task {task_id}"}
    if not isinstance(scope, (list, tuple)):
        return {"refused": True,
                "error": "`scope` is a LIST of excluded capabilities (each a line saying what is "
                         "out and why it is safely out), not a " + type(scope).__name__}
    items = tuple(str(x.get("item", "")) + (f" — {x['why_out']}" if x.get("why_out") else "")
                  if isinstance(x, dict) else str(x) for x in scope)
    spec = was.spec
    out = task_out(engine.revise(
        TaskId(task_id),
        dataclasses.replace(spec, scope=items),
        AgentId(agent), reason="scope_expansion"))
    if isinstance(out, dict):
        t = engine.graph.get_task(TaskId(task_id))
        out["scope_recorded"] = list(t.spec.scope) if t is not None else []
        out = _said_state_change(engine, task_id, was.state, out)
    return out


def edit_criteria(engine: Engine, task_id: str, criteria: list[dict], agent: str = "",
                  reason: Optional[str] = None, accept_coverage_loss: bool = False,
                  expect_criteria: Optional[list] = None) -> Optional[dict]:
    """Replace a node's criteria, carry the rest. RMW over revise. (Dep criteria use `depends_on`.)
    `reason` (optional, §15.4): spec_defect = the criteria were WRONG (counts in q_T) |
    scope_expansion = sanctioned growth of the goal (§15.4; never counts) | other.

    A contract change is a REVISION (Inv-1, §12.3): the node re-enters at OFFERED so its executor
    consents to the new contract, and its plan's Level-2 verdict is staled by the edit. Both are
    canon, and neither was said — a person watched a node they had just been working go from
    EXECUTING back to OFFERED with nothing in the reply about it (measured 2026-08-21).

    `expect_criteria=[<the names you read>]` makes the replacement CONDITIONAL: the call is refused,
    naming what moved, if the set changed after you read it (read-modify-write with no version check
    is how a concurrent author's criteria get dropped by a caller who never saw them)."""
    # WHO IS ASKING, when they do not say. There is no `whoami` on this door and no default was
    # named anywhere, so a person answered "edit_criteria needs agent" by guessing a name that
    # happened to work (measured 2026-08-21). The caller's standing identity is the answer the
    # agent door has always used; a person naming themselves still overrides it.
    agent = agent or _agent_id()
    # …THROUGH THE OWNER OF THE RULE, not a second spelling of it. `TaskId` is a string alias, so
    # `TaskId(["a", "b"])` hands the list straight back: this door accepted the very value
    # `_spec_from` refuses, the DAG check then raised `unhashable type: 'list'` inside the event
    # loop, and the loop died with it (agent door, 2026-09-02 — the project could not be repaired
    # from any verb afterwards, and every one of them blamed the FSM).
    try:
        crits = tuple(Criteria(c["name"], c.get("description", ""), depends_on=_dep_of(c),
                               check=_checks_of(c),
                               composition=str(c.get("composition", "") or ""))
                      for c in criteria)
    except (ValueError, KeyError, TypeError) as ex:
        return {"refused": True, "error": str(ex)}
    before = engine.graph.get_task(TaskId(task_id))
    if (_moved := _contract_moved_under_you(before, expect_criteria)):
        return _moved
    was = before.state if before is not None else None
    _had = tuple((c.name, c.description) for c in before.spec.criteria) if before is not None else ()
    # …and the COVERAGE as it stands now, copied out. `before` is the live Task the engine mutates in
    # place, so reading its mappings after the call reads the post-edit state and reports no loss.
    _had_map = tuple((m.criterion_name, str(m.child_id))
                     for m in ((before.criterion_mappings or ()) if before is not None else ()))
    # WHAT THE EDIT DROPS IS SAID, AND IT CAN BE PUT BACK: a mapping is the split's (§2.4), so `map_criterion` re-makes
    # it onto any active child, a passed one included — the refusal that stood here ("a finished node's contract
    # cannot take a new `covers`") read the mapping as the child's contract (critic r15). `accept_coverage_loss` is
    # accepted and no longer needed.
    out = task_out(engine.edit_criteria(TaskId(task_id), crits, AgentId(agent),
                                         reason=_reason_from(reason)))
    # WHAT THIS REPLACED, IN THE REPLY. The verb REPLACES the set — that is its contract — and the
    # answer showed only the new one, so five authored criteria vanished in a call whose reply said
    # nothing about them, with no history verb to recover from: the caller had to invent a contract
    # from the node's description (measured on the human door 2026-08-22). The old set is in the
    # log (Inv-7) and now in the reply, which is where a mistaken call is read.
    # …AND WHAT SURVIVED IS READ OFF THE RESULT, not off the request. A `dep__*` criterion the new
    # set does not name is CARRIED OVER by the engine (the edge it holds may not be cut by omission)
    # — and this list was computed from what the caller sent, so the reply announced a removal that
    # had not happened, in the same object whose own `criteria` still showed it (CLI door,
    # 2026-09-02: "I spent a beat believing I had silently severed a dependency edge").
    _kept = {c.get("name") for c in (out.get("criteria") or ())} if isinstance(out, dict)         else {c["name"] for c in criteria}
    # …AND WHAT THE EDIT LEFT UNCOVERED, in the same breath. Replacing the set dangles every mapping
    # it does not re-name: a caller who added five criteria to a root found — one paid review round
    # later, from a `CHECK-1:coverage` line in a raw body — that all six were unmapped, including the
    # ones they had not touched (agent and HTTP doors, 2026-09-02, five rebuild calls each). The verb
    # that creates the obligation is the one that has to name it, and `map_criterion` already speaks
    # this vocabulary (`still_uncovered`), so the answer is the same word in both places.
    # …AND WHAT COVERAGE THIS CALL DROPPED. A criterion the new set does not name takes its mapping with
    # it — correctly, the criterion is gone — and while `map_criterion` read a `covers` as the child's
    # revision, a mapping onto a terminal child could not be re-made at all (it can now: the mapping is the
    # split's, §2.4 — critic r15). Measured on the MCP door
    # 2026-09-02: a caller replaced ten criteria with one, restored the ten verbatim, and was left
    # with a DONE/PASS root carrying a permanent CHECK-1 coverage failure and no way back. The reply
    # said what was newly uncovered and never that anything had been LOST.
    # Computed from the REQUEST, not from the graph afterwards: the pruning rides the revision's
    # ASSIGN through the event loop, so reading the node back inside this verb sees the mappings
    # still standing and reports no loss at all. What is decidable here and now is the definition —
    # a mapping whose criterion the new set does not name is a mapping that is going.
    _kept_names = {c["name"] for c in criteria}
    _going = [(c, k) for c, k in _had_map if c not in _kept_names]
    _after = engine.graph.get_task(TaskId(task_id))
    if _after is not None and isinstance(out, dict):
        if _lost := sorted(f"{c} -> {k}" for c, k in _going):
            out["coverage_dropped"] = _lost
            out["coverage_dropped_note"] = (
                f"{len(_lost)} criterion→child mapping(s) went with the criteria this call replaced; "
                f"`map_criterion` can re-make them onto the children still in the split, a passed one included.")
        _covered = {m.criterion_name for m in (_after.criterion_mappings or ())}
        if _uncovered := [c.name for c in _after.spec.criteria
                          if c.name not in _covered and not c.depends_on]:
            if engine.graph.get_active_children(TaskId(task_id)):
                out["still_uncovered"] = _uncovered
                out["still_uncovered_note"] = (
                    f"{len(_uncovered)} criterion(s) of this node are covered by no child now — "
                    f"replacing the set dangles the mappings it does not re-name. One `decompose("
                    f"'{task_id}', [], mappings=[…])` binds them all (`map_criterion` binds one where it is the "
                    f"only hole); until then CHECK-1 holds the "
                    f"plan and execution is not admitted.")
    if (_gone := [f"{n}: {d}" for n, d in _had if n not in _kept]) and isinstance(out, dict):
        out["removed"] = _gone
        out["removed_note"] = (f"{len(_gone)} criterion(s) are no longer in this contract. "
                               f"`edit_criteria` REPLACES the set — to put one back, include it in "
                               f"the next call; the previous versions stay in the log (Inv-7).")
    return _said_state_change(engine, task_id, was, out)


def _cycle_closed_by(engine: Engine, task_id: str) -> Optional[str]:
    """Did this BLOCK name a producer that already waits on the blocked node — and what that costs.

    The record is PROVISIONAL (§11.3/§15.5): it enters E_Dep only on its issuer's confirmation, and a
    confirmed one that would close a cycle is not adopted. The engine used to run CHECK-2 over it, so the
    parent's plan went red and every sibling froze (human door 2026-08-22; AUTO json_parser 2026-09-25).
    What stays true is that no wait ends this one — so the sender is told, at the signal that found it."""
    if not (order := engine.order_refuted_by(TaskId(task_id))):
        return None
    return (f"this BLOCK names a producer that cannot finish before it: {order}. The record is provisional — "
            f"not an edge of the plan's Dep, so no sibling stops — but no wait resolves it: this node's issuer "
            f"answers the block (refutes what it names, re-issues the node, or closes it), or the split is "
            f"reshaped — or `remove_dependency` drops a declared seam that runs the wrong way.")


def _said_state_change(engine: Engine, task_id: str, was, out: Optional[dict]) -> Optional[dict]:
    """Name a state change the caller did not ask for, on the reply that caused it.

    A revision (Inv-1) sends the node back to OFFERED for its executor's consent, and an edit to a
    decomposition stales its Level-2 verdict (§9.1). Both are correct and both were silent, so the
    node simply appeared to have moved on its own."""
    if not isinstance(out, dict) or was is None or out.get("state") == was.name:
        return out
    out["state_changed"] = (
        f"{was.name} → {out.get('state')}: a contract change is a REVISION (Inv-1, §12.3), so the "
        f"node re-enters at OFFERED and its executor consents again — signal ACCEPT to put it back "
        f"to work; the subtree is retained.")
    if was.name in ("DONE", "ABANDONED"):
        # …AND WHAT IT COST, when the node was FINISHED. Editing the contract of a settled node is a
        # reopen with a new contract (R′, §12.14): it spends a reopen and its verdict is GONE, to be
        # re-earned by fresh contact. Measured on the human door 2026-08-21 — a passed child was
        # dropped back to OFFERED by an edit, and the recovery cost a plan review, seven disputes, a
        # re-delivery and two validations. `reopen` says this; the edit that does the same did not.
        out["state_changed"] += (
            f" This node was {was.name}: editing a settled contract is a REOPEN with a new one, so "
            f"its verdict is GONE (§12.14 — re-earned by fresh contact, never carried forward) and a "
            f"reopen is spent.")
    if engine.graph.get_active_children(TaskId(task_id)):
        out["state_changed"] += (" The edit also STALES the plan's Level-2 verdict — "
                                 f"review_decomposition('{task_id}') before its children can start "
                                 "(§9.1).")
    return out


def reassign(engine: Engine, task_id: str, assignee: str,
             reason: Optional[str] = None) -> Optional[dict]:
    """Change a node's executor (Del). Canon Inv-1 fixes Del at ASSIGN → a change = revision: re-ASSIGN
    (same id) carrying the new executor (the issuer acts; the subtree is retained — no cascade).
    `reason` (optional, §15.4): capability_mismatch = the executor could not do the work (counts in
    q_Del) | other (load/handoff; does not count). Untyped counts — omit only when genuinely unknown.
    DELEGATING work to a registered executor is `other`: nobody failed at anything, and typing it as
    a capability mismatch would charge q_Del for an ordinary hand-off (measured 2026-08-21 — a caller
    reached for the nearest-looking value and stopped to reason it out)."""
    was = str(engine.graph.get_task(TaskId(task_id)).assignee or "") if engine.graph.get_task(TaskId(task_id)) else ""
    # …AND UNDER A MODE THE NEW DEL IS THE MODE'S TO AGREE WITH: a holder that re-assigns a system node to
    # itself undoes the mode node by node, with the mode record untouched (measured 2026-09-24: a
    # semi-auto holder took three repair nodes back and edited the program itself)
    if engine.mode() is not None and (t := engine.graph.get_task(TaskId(task_id))) is not None:
        del_by_mode(engine, str(t.parent_id) if t.parent_id else None, assignee)
    out = task_out(engine.reassign(TaskId(task_id), AgentId(assignee),
                                    reason=_reason_from(reason)))
    # Say what the untyped act COSTS, at the moment of the act. The verb's help has said this since
    # 2026-08-21 and the caller still has to be reading help to see it; measured 2026-09-02 on a live
    # delegated run, whose DEL read 25% in red because three ordinary hand-offs to the run's own
    # executors went untyped. The over-approximation is deliberate (a metric must never improve by
    # omitting a reason) — so the fix is to tell the caller, not to soften the count.
    if isinstance(out, dict) and reason is None and was and was != str(assignee):
        out["counts_against_q_Del"] = (
            f"Del changed {was} → {assignee} with no reason given, so it counts as a delegation "
            f"defect (the untyped case is counted on purpose — the metric must not improve by "
            f"leaving the reason out). If nobody failed here, say reason='other'; reserve "
            f"reason='capability_mismatch' for an executor that could not do the work.")
    return out


def _reopen_gate(engine: Engine, t) -> Optional[dict]:
    """Why the R′ edge is closed on this node — or None when it is open (§12.14).

    Asked by `reopen`, which refuses in these words, and by the affordance surface, which must not
    OFFER the ASSIGN that carries a reopen while the gate is shut. The FSM refuses it either way, in
    the generic words of a guard ("the precondition does not hold"), which is what this exists to
    replace.""" 
    if t.state.name not in ("DONE", "ABANDONED"):
        return {"error": f"{t.id} is {t.state.name} — reopen is for a node that FINISHED "
                         f"(DONE or ABANDONED). A node still in play is moved by its own signals, "
                         f"and its contract by `revise`.",
                "state": t.state.name}
    # WHICH GATE, IN THE ENGINE'S WORDS: the issuing condition (§12.7) and the finality gate (§12.14) are the engine's
    # (`Engine.reopen_refusal`); this verb kept its own copy of both, and `reopen` threw where the engine refused a case
    # the copy did not know (outside review, 2026-09-23; ortho audit, D-F1).
    if why := engine.reopen_refusal(t.id):
        return {"error": why, "consumed": engine.graph.is_consumed(t), "reopens": t.reopens, "max_reopens": t.max_reopens}
    return None


def reopen(engine: Engine, task_id: str, agent: str) -> Optional[dict]:
    """Reopen a DONE/ABANDONED node back to OFFERED under its standing contract (R′, §12.14) — the verdict
    is RE-EARNED by fresh contact, never resurrected. Double-gated by the engine: the node must not be
    CONSUMED since it settled (its parent delivered over it / a Dep-consumer worked on it / a re-admission
    covered around it / the parent's version maps it to nothing — once logged, standing) and reopens must remain (max_reopens, default 1). A consumed terminal is
    finally locked — recover by re-decomposition, not reopen. `agent` must be the issuer."""
    t = engine.graph.get_task(TaskId(task_id))
    if t is None:
        return {"error": f"unknown task {task_id}"}
    # ASK THE TWO GATES BY NAME, before the FSM refuses the edge without saying which one bit. The
    # engine's generic refusal named the wrong verb ("revise"), offered a three-way disjunction of
    # possible reasons, and — over HTTP — arrived as JSON quoted inside JSON. Measured live: a person
    # could not tell "this node is locked forever" from "you sent it wrong". Each branch here says
    # what is true of THIS node and what the recovery actually is.
    if (shut := _reopen_gate(engine, t)) is not None:
        return shut
    was = t.state.name, (t.done_reason.name if t.done_reason else None)
    out = task_out(engine.reopen(TaskId(task_id), AgentId(agent)), engine) or {}
    # SAY WHAT WAS DESTROYED. R′ drops the verdict by design — it is re-earned by fresh contact —
    # but the reply was an undifferentiated task dump, and a person who ran this to SEE whether it
    # would be refused found their finished root back in OFFERED, one reopen spent, with nothing in
    # the answer saying so. Measured 2026-08-20: it cost the run a re-accept, a re-delivery and a
    # paid re-validation to get back where it had been.
    out["reopened"] = (f"{task_id} was {was[0]}"
                       + (f"/{was[1]}" if was[1] else "")
                       + f" and is now OFFERED — that verdict is GONE (§12.14: a reopened node "
                         f"re-earns it by fresh contact, it is never carried forward). Reopens "
                         f"spent: {t.reopens}/{t.max_reopens}. The node must be ACCEPTed, worked and "
                         f"validated again.")
    return out


def add_dependency(engine: Engine, from_id: str, to_id: str, glue: str = "",
                   check: Optional[list] = None) -> dict:
    """Declare `to_id depends on from_id`'s output — **`from_id` is the PRODUCER, `to_id` the
    CONSUMER**, and the arrow runs producer → consumer: `to_id` is the one that waits.

    Dep is criteria-content (§2): desugars to a re-author of the CONSUMER adding the glue
    criterion; the edge is derived. Cycle → rejected. `glue` is the anti-mock truth-maker — what
    the consumer must do with the real output, not "depends on it". `check` optionally PINS the
    seam's own probe from the consumer's side ([{behaviour, command, expect}]) — the integration
    implication itself is the PARENT's claim (§6.5), which is why a seam criterion is not required
    to carry one.

    The direction is worth one sentence because getting it backwards is silent: a person wrote the
    glue "render imports and calls the scan() function delivered by scan", passed them the other way
    round, and made SCAN wait on RENDER — the reply said `ok`, the Level-2 review passed the graph,
    and only `next_steps` (`waits_on`) showed it. So the answer says which way it went."""
    engine.add_dependency(TaskId(from_id), TaskId(to_id), glue=glue,
                          check=_checks_of({"check": check}) if check else ())
    return {"ok": True, "from": from_id, "to": to_id,
            "declared": f"'{to_id}' now WAITS for '{from_id}' to pass — '{from_id}' produces, "
                        f"'{to_id}' consumes. If that is backwards, `remove_dependency` and swap."}


def remove_dependency(engine: Engine, from_id: str, to_id: str) -> dict:
    """Drop a dependency (re-authors the consumer to remove the glue criterion).

    Removing an edge REWRITES the consumer's contract (the glue criterion goes with it), which is a
    revision — so it stales the plan's Level-2 verdict and the children stop being admitted to
    execution until the check runs again (§9.1). Both are canon and both were silent: the answer
    was `{"ok": true}` and the graph then simply did not move (measured on the human door
    2026-08-22)."""
    engine.remove_dependency(TaskId(from_id), TaskId(to_id))
    out = {"ok": True, "removed": f"{from_id} -> {to_id}"}
    _parent = engine.graph.get_parent(TaskId(to_id))
    if _parent is not None and not _parent.verified:
        out["plan_verdict_staled"] = (
            f"this re-authored '{to_id}', which is a revision — the Level-2 verdict on "
            f"'{_parent.id}'s plan no longer covers it, so its children are not admitted to "
            f"execution until `review_decomposition('{_parent.id}')` runs again (§9.1).")
    return out


def map_criterion(engine: Engine, parent_id: str, child_id: str, criterion_name: str) -> Optional[dict]:
    """Bind an EXISTING child to a parent criterion (add/repair the coverage mapping) — a re-admission of the parent's
    split, the child's contract and work untouched, whatever its state. Use this when a child covers a parent criterion
    but wasn't mapped at decompose time, or when a re-authored parent criterion left the coverage short (CHECK-1).
    Several holes at once are bound in one act: `decompose(parent, [], mappings=[…])`.

    Answers with the BINDING it made and what is still uncovered: echoing the whole parent made eleven
    successive calls indistinguishable from eleven no-ops (measured on the human door 2026-08-21)."""
    # A COVERAGE REPAIR IS A RE-ADMISSION OF THE PARENT'S SPLIT (§11.5): the mapping is the split's (§2.4), no field of
    # the child's packet (§10.1), so the child — working, delivered or passed — keeps its contract and its work. Read as
    # the child's revision it sent a node in VALIDATING back to OFFERED, its delivery and running validation lost
    # (human door, 2026-08-21), and a passed child could never be mapped at all (critic r15).
    _child = engine.graph.get_task(TaskId(child_id))
    if _child is None:
        return {"error": f"child {child_id} not found", "refused": True}
    try:
        parent = engine.map_criterion(TaskId(parent_id), {str(child_id): (criterion_name,)})
    except ValueError as ex:
        # …WHOLE OR NOTHING, as any re-admission: with another hole standing, this one binding leaves the split short
        # of the Syntactic level, and the act that lifts both is one `decompose` naming every pair
        return {"error": f"{ex} — to bind several at once: `decompose('{parent_id}', [], mappings=[{{criterion_name, "
                         f"child_id}}, …])`, one re-admission", "refused": True}
    covered = {m.criterion_name for m in parent.criterion_mappings}
    uncovered = [c.name for c in parent.spec.criteria if c.name not in covered]
    return {"mapped": f"{parent_id}.{criterion_name} is covered by {child_id}",
            "criterion": criterion_name, "covered_by": str(child_id), "parent_id": str(parent_id),
            # NAMED FOR WHAT IT IS: the PARENT's criteria that now have a coverer. Read as "what
            # this child covers now" by a tester who then believed one child carried five criteria
            # (MCP door, wave 26, 2026-09-06). `covers_now` stays as an alias for one release.
            "parent_criteria_covered": sorted(covered),
            "covers_now": sorted(covered),   # DEPRECATED alias of the above
            "still_uncovered": uncovered,          # empty = CHECK-1 (coverage) has nothing left to hold
            # …and NOT the whole parent node. Seven calls came to 33.9 KB of echoed criteria text
            # (measured on the human door 2026-08-21) for a verb whose whole answer is which
            # criterion is now carried by which child. `get_task('<parent>')` is one call away.
            "parent_state": parent.state.name}




def _p2p_signal(signal: str) -> Signal:
    """The signal named, or a refusal — the alphabet is the TWELVE P2P signals and nothing else.

    The door is where the alphabet is closed. Both refusals are here because they are one
    question asked twice: is this a signal an agent may send?
    """
    try:
        sig = Signal[signal]
    except KeyError:
        raise ValueError(f"unknown signal '{signal}' — the alphabet is the 12 P2P signals: "
                         f"{', '.join(s.name for s in P2P_SIGNALS)}")
    if sig not in P2P_SIGNALS:
        # §12.2: the timeout "is not a P2P signal (no agent sends it) but a system mechanism enforcing
        # finiteness". Sent from here it settled a node in VALIDATING by the clock — walking
        # around the AND gate (Thm 1), verifier ≠ executor (§10.3) and Inv-3 in one call, because
        # validation returns early for Role.SYSTEM. The door is where the alphabet is closed; the
        # engine refuses a sourced system signal on its own (gfso/engine/validation.py).
        raise ValueError(
            f"{sig.name} is not a P2P signal — no agent sends it (§12.2); it is the system's "
            f"finiteness trigger (Inv-5), emitted by the deadline monitor alone. Send one of: "
            f"{', '.join(s.name for s in P2P_SIGNALS)}")
    return sig


def signal(engine: Engine, task_id: str, signal: str, source: str,
           self_validation: Optional[str] = None,
           reason: Optional[str] = None, result: Optional[str] = None,
           justification: Optional[str] = None, action: Optional[str] = None,
           in_flight: Optional[str] = None, blocker_task_id: Optional[str] = None,
           blocker_task_ids: Optional[list] = None,
           external: bool = False, failed_criteria: Optional[list] = None,
           retire_findings: Optional[list] = None) -> dict:
    """Send a raw protocol signal (the lifecycle transaction): ACCEPT / DELIVER / PASS / FAIL / BLOCK /
    RESOLVE_BLOCK / CHALLENGE / ACCEPT_CHALLENGE / REJECT_CHALLENGE / CANCEL / CONFIRM_CANCEL. The lower-layer
    primitive. On the AGENT door signals are signed as you automatically (`agent` — the MCP door pins
    the source and impersonation is impossible); from the CLI, where a person names themselves the
    way the UI always has, `source=<your name>` is that name — the same field, written by hand. The
    FSM validates the ROLE: executor signals require the node's
    Del == you, issuer signals require the parent's Del == you — a node delegated to someone else only
    moves on THEIR signals. DELIVER carries `result` (paths + how each criterion is met — the
    validator's input).
    FAIL requires `failed_criteria` (Inv-3). CANCEL opens the two-step abandon handshake (→ CANCELLING);
    the executor settles it with CONFIRM_CANCEL (pass `in_flight` = the state of work at cancellation) →
    ABANDONED. BLOCK on undeclared prerequisites that are EXISTING nodes: pass `blocker_task_ids` with
    EVERY node you actually need (never collapse several blockers into one — each records a provisional
    discovered-Dep edge, feeds q_Dep; `blocker_task_id` = single-blocker shorthand); RESOLVE_BLOCK then
    confirms them (default), re-attributes with the corrected FULL set (`blocker_task_ids` — unlisted
    provisionals retract), or retracts all (`external=true` — no producer node). A CANCEL ending a BLOCKED node
    may carry the same answer (`blocker_task_ids` confirmed, or `external=true` refuted); without one the block's
    records close unanswered and still count in q_Dep (§15.5).

    The alphabet here is the TWELVE P2P signals and nothing else: `TIMEOUT` is the system's finiteness
    trigger (Inv-5), "not a P2P signal (no agent sends it)" — §12.2 — so this door refuses it by name.

    ACCEPT_CHALLENGE may carry `retire_findings`: ids of the validator's findings standing on the node (`get_task`'s
    `regression_probes`, the dispute packet's list) that this ruling holds outside the criterion as written — retired
    with it, `justification` the recorded why; the only way a finding stops being demanded. The CHALLENGE must have
    named each by its id, and the ruling holds while its criterion reads as this act leaves it."""
    sig = _p2p_signal(signal)
    entry = engine.send_signal_sync(SignalData(
        signal=sig, task_id=TaskId(task_id), source=AgentId(source),
        reason=reason, result=result,
        # DELIVER's own field (§11.2). It is what an INTERNAL node's completion rests on — §10.3:
        # such a node self-verifies, its DELIVER carries the self-check, and the guarantee is carried
        # by the validation of the public result above it. The packet had the field, the schema asked
        # for it, and no door let a caller fill it in.
        self_validation=_self_check_verdict(self_validation),
        justification=justification, action=action,
        in_flight=in_flight,
        blocker_task_id=TaskId(blocker_task_id) if blocker_task_id else None,
        blocker_task_ids=tuple(TaskId(b) for b in (blocker_task_ids or []) if b),
        external=bool(external),
        failed_criteria=tuple(failed_criteria or ()), retire_findings=tuple(map(str, retire_findings or ()))))
    st = engine.graph.get_state(TaskId(task_id))
    ok = bool(entry and not entry.rejected)
    out = {"accepted": ok, "state": st.name if st else None}
    if ok and retire_findings:
        out["retired_findings"] = list(dict.fromkeys(map(str, retire_findings)))
    if ok:
        _what_an_ACCEPTED_signal_owes_its_sender(engine, task_id, sig, st, source, out)
    else:
        _what_a_REFUSED_signal_owes_its_sender(engine, task_id, sig, entry, out)
    return out


# …named once, in the vocabulary (`core.types.enums`). This was the third of three lists that had to
# agree about the same nine words and did not.
_EXECUTOR_ACTIONS = EXECUTOR_ACTIONS


def _what_an_ACCEPTED_signal_owes_its_sender(engine: Engine, task_id: str, sig, st, source, out: dict) -> None:
    """Everything the reply to a landed signal must carry besides the new state name.

    Each branch here was measured at a door: a coverage loss learnt one step too late, a node
    shown EXECUTING that provably could not start, a leaf frozen by a rule its executor met four
    round trips later, a delivery whose author could not tell whether a verdict was coming. They
    are independent of each other and of the sending — which is why they live beside it rather
    than inside it — and every one answers the same question: what just became true for the party
    that sent this signal."""
    if st is not None and st.name == "CANCELLING":
        # BEFORE the point of no return, not after. CANCELLING admits only CONFIRM_CANCEL, so by the
        # time the coverage loss was reported the decision had already been made (measured on the
        # human door 2026-08-21: "that is exactly the information I needed one step earlier").
        if (_at_stake := _coverage_lost_by(engine, task_id)):
            out["coverage_at_stake"] = _at_stake
    if st is not None and st.name == "ABANDONED":
        _lost = _coverage_lost_by(engine, task_id)
        if _lost:
            out["coverage_lost"] = _lost
    if sig == Signal.BLOCK and (_red := _cycle_closed_by(engine, task_id)):
        out["plan_order_refuted"] = _red
    # …AND WHAT AN ACCEPTED NODE IS STILL WAITING FOR. §12.4 admits ACCEPT from OFFERED whatever the
    # seams say, and the engine is not narrower than the canon — but the reply said nothing, so a
    # graph showed EXECUTING for nodes that provably could not start, and their executor found out by
    # hitting a missing input and BLOCKing (CLI and HTTP doors, 2026-09-02). Taking it is fine;
    # starting it is what waits.
    # …AND WHAT A PASS ON A LEAF FREEZES. Once a parent stakes its aggregate on a child, that child
    # is CONSUMED and cannot be reopened (§12.14 finality) — so a defect later found in the code that
    # leaf's contract owns has to be repaired by re-decomposing AROUND it. That is the right rule and
    # it was learnt at the wrong moment: a tester met it only when the root's validator refuted the
    # shared function, four round trips after the leaf had passed (CLI door, 2026-09-02). Said at the
    # PASS, it is a fact someone can plan around; said at the reopen, it is only a wall.
    if sig == Signal.PASS and st is not None and st.name == "DONE":
        _t = engine.graph.get_task(TaskId(task_id))
        if _t is not None and _t.parent_id and not engine.graph.get_active_children(TaskId(task_id)):
            out["frozen_now"] = (
                f"this leaf has passed, so the concern its criteria own is settled for the rest of "
                f"the run: once '{_t.parent_id}' stakes its aggregate on it the node is CONSUMED and "
                f"cannot be reopened (§12.14). A defect found later in the code this contract covers "
                f"is repaired by re-decomposing around it, not by re-working this node.")
    if sig == Signal.ACCEPT and (_open := engine.unmet_producers(TaskId(task_id))):
        out["cannot_start_yet"] = _open
        out["cannot_start_note"] = (
            f"taken — but it consumes {', '.join(_open)}, and they have not passed (§2: a Dep is "
            f"criteria content). Starting now hits a missing input and ends in BLOCK; the dispatcher "
            f"holds spawns until they pass. `next_steps` lists this node under `waiting`.")
    if st is not None and st.name == "VALIDATING":
        # WHAT HAPPENS TO THE DELIVERY NOW, said to the one who just made it. A DELIVER answered with
        # a directive about some OTHER node (the frontier's next move, correctly), and the executor
        # was left not knowing whether a verdict was coming or whether it had to ask for one — one
        # tester waited, another called `validate_result` on a node an instrument was already
        # holding, paying twice for the same artifact (measured on the human door 2026-08-22).
        out["awaiting_verdict"] = (
            # …AND WHERE THE USER'S AGENT HOLDS THE NODE, the observation is the instrument's and the
            # verdict is the agent's: the issuer decides, the validator observes (SOLO/SEMI).
            ("the project's validator observes this delivery now" if engine.claims.validation_in_flight(TaskId(task_id))
             else f"the project's validator observes this delivery by itself — or `validate_result {task_id}` "
                  f"observes it now" if engine.validated_by_instrument(TaskId(task_id)) or engine.workforce.has_an_instrument()
             else f"no validator is registered in this project, so `validate_result {task_id}` observes it (pass "
                  f"`workdir=` if it asks where the work is)")
            + f"; then YOU sign it as its issuer: read `get_verdict {task_id}` and signal PASS or FAIL. A "
              f"PASS over a divergence the observer recorded is refused (Inv-2); if you hold it wrong, FAIL "
              f"saying why, and where its pinned probe is what is wrong, revise the criterion"
            if engine.holder_signs(TaskId(task_id)) else
            "an INDEPENDENT validation of this delivery is already running — its verdict arrives by "
            "itself; do not start a second one"
            if engine.claims.validation_in_flight(TaskId(task_id)) else
            "a verdict is on the record for this delivery — `get_verdict` reads it; the signal is the "
            "issuer's to give"
            if engine.current_exec_verdict(TaskId(task_id)) is not None else
            f"this node now waits for a verdict from its issuer; you cannot sign your own (§10.3). "
            f"`validate_result {task_id}` runs an independent validator on it."
            if engine.is_seam(engine.graph.get_task(TaskId(task_id))) else
            # …AND THE OPPOSITE IS TRUE ON AN INTERNAL NODE, where three surfaces said three things.
            # §10.3: a node whose Del is its parent's SELF-verifies, and the reply that told its
            # executor "you cannot sign your own" was contradicted in the same object by the `next`
            # line telling them to signal PASS, and by `available_actions`, which alone was right
            # (agent door, 2026-09-02). The rule is about the SEAM, so the sentence has to be too.
            # …AND ONLY WHEN NOBODY IS ABOUT TO VALIDATE IT FOR YOU. This sentence was added earlier
            # today and immediately sent a user down a path the dispatcher had already closed: an
            # instrument was bound to the node, took it to DONE while they were writing their own
            # observations, and eight calls came back refused (CLI door, 2026-09-02). Which of the
            # two is happening is not visible from outside — so the reply has to say which one it is.
            # …AND WHICH VALIDATOR IT IS, AND WHERE IT STANDS. The roster is one server-wide fact, so
            # "an independent validator" can be a role somebody else registered for another project,
            # working in a directory that holds none of this delivery — which then fails twice per
            # node and blocks it. FIVE testers across three waves reported the same thing, and every
            # one of them had to go read `gfso log` to find out: the sentence that announced the
            # validator did not name it (waves 23–25). Naming it is not the isolation fix — the roster is
            # server-wide by design — it is the difference between a wait you can diagnose and one
            # you cannot.
            f"an independent validator is bound to this node and validates this delivery by itself — "
            + _bound_validator_note(engine, task_id)
            + f"wait for it (`get_verdict {task_id}` reads the result; `gfso log` shows it running). "
            f"Recording your own verdict here would race it."
            if engine.validated_by_instrument(TaskId(task_id)) else
            f"this node is INTERNAL (its Del is its parent's), so §10.3 lets it self-verify: put "
            f"what you checked on the record — `record_verdict {task_id} PASS observed={{...}}` — "
            f"and then signal. A DELIVER carrying `self_validation` records it for you.")
    # Carry the NEXT directive back in the signal's own response. Agents drive by sending signals,
    # not by polling next_steps between them (observed live: ACCEPT → write code → DELIVER with no
    # frontier call in between — so a directive that only lives in next_steps never reaches them).
    # Returning it here puts the next step — e.g. "before DELIVER, self-check by running" — at the
    # one point the agent always reads: the reply to what it just did. (Enforcement of discipline
    # rides where the agent LOOKS, not where we hope it polls.)
    # The signal is already accepted and recorded; a failure to compute the NEXT step must not
    # come back as a refusal of the one that landed — an agent reading that re-sends a signal it
    # already sent.
    try:
        out.update(next_for(engine, source, about=task_id))
    except Exception:   # gives up only the hint; the signal stands
        pass


def next_for(engine: Engine, me: Optional[str], about: Optional[str] = None, entering: bool = False) -> dict:
    """{next[, next_is_mine]}: the move the graph waits on, said to `me` — carried in the reply to what the caller just
    did (a signal on `about`, or entering a project), where it always reads, not only in `next_steps` it may never
    poll: an agent on claude-sonnet-5-5 switched into an empty project, heard no next move, and did the whole task
    outside the graph (GB_coreutils_tmlowg001, 2026-10-09)."""
    # …ASKED OF THE WHOLE GRAPH, not of the node just signalled. Scoped to that node,
    # `next_step` answers about ITS subtree — so a leaf reaching DONE came back "COMPLETE —
    # root 'x.core' is DONE/PASS. Execution finished." while four sibling nodes were still
    # open, on every child in the run. A reader who trusted the reply instead of re-reading
    # the graph ships a half-built package (measured on the agent door 2026-08-21, and it is
    # the one message in this product that could cause that).
    nxt = engine.next_step()
    if nxt.get("complete") and entering:
        # "Execution finished" is about work just done; said to one ENTERING the project it is about a goal that is
        # not theirs, and reads as the very "done" no verdict of theirs stands behind (critic, 2026-10-09)
        return {"next": "this project's graph is finished — " + (nxt.get("directive") or "its root is settled")
                        + ". A new goal is a new root: `auto_decompose(request, root_id='<new id>')`, or a fresh "
                          "project."}
    if nxt.get("complete"):
        return {"next": nxt.get("directive") or "the graph is complete."}
    if not nxt.get("directive"):
        return {}
    # SAY WHICH NODE IT IS ABOUT. The step that follows a signal is often on a DIFFERENT
    # node — the one just signalled may be waiting on a producer, or done — and the bare
    # directive read as a statement about the node the caller had in hand. Measured:
    # accepting one leaf answered with an instruction about another, which reads as a
    # defect even when it is the honest next move.
    other = about is not None and nxt.get("task_id") and str(nxt["task_id"]) != str(about)
    # …THROUGH THE SAME OWNERSHIP FILTER THE FRONTIER USES. The reply carried the raw
    # directive, so a signal on one node answered "EXECUTE leaf 'X': do the actual work"
    # about a node whose Del is somebody else's registered executor — while `next_steps`
    # on that same node said "NOT YOURS (Del=…) — do NOT execute or signal for it". One
    # tester nearly redid a running executor's work on it (measured on the MCP door
    # 2026-08-21). Del is load-bearing in every surface that speaks about a node, or in
    # none.
    nxt = _mark_mine(engine, dict(nxt), me=me)
    out = {"next": (f"next on the frontier is '{nxt['task_id']}', not {about}: " if other else "")
                   + nxt["directive"]}
    if not nxt.get("mine", True):
        out["next_is_mine"] = False
    return out


def _what_a_REFUSED_signal_owes_its_sender(engine: Engine, task_id: str, sig, entry, out: dict) -> None:
    """The one shape for "the system answered no", plus the structural gate the sender cannot see."""
    # ONE SHAPE FOR "THE SYSTEM ANSWERED NO". Four places used to author that answer — the FSM's
    # bare `None`, the validation layer's free-form raise, the log's row, and this branch — so
    # the same act came back as a sentence, a silence, or a different sentence depending on which
    # door refused it. `SignalOutcome`/`Refusal` are the record; this is where it is built, and
    # `as_dict` is the wire form every door already speaks (`accepted` / `state` / `error`).
    _outcome = engine.refusal_of(TaskId(task_id), sig, entry)
    out.update(_outcome.as_dict())
    # …and the structural gate the executor cannot see from its own side: which CHECK is unmet.
    fails = [f"{c.check_name}: {c.details}" for c in engine.get_checks(TaskId(task_id))
             if not c.passed and not c.skipped]
    if fails:
        out["failing_checks"] = fails


def _bound_validator_note(engine: Engine, task_id: str) -> str:
    """Who the bound instrument IS, and where it works — said where the binding is announced.

    Read off what the DISPATCHER published for this node, never composed here. The first spelling of
    this asked the registry directly and the layer gate refused it in the same words its neighbour
    `validated_by_instrument` already carries: a door that composes this for itself reaches into the
    delegation layer. The gate was right, and the fact was already being computed one layer down.

    Empty when there is nothing surprising to say. What is surprising, and what five strangers across
    three waves had to dig out of `gfso log`: the roster is server-wide, so the validator can belong to
    another project and stand in a directory holding none of this work.
    """
    who = (engine.workforce.bound_validator(TaskId(task_id)) or {})
    if not who.get("id"):
        return ""
    _mine = who.get("project") == engine.project_name
    _whose = ("registered for THIS project" if _mine
              else f"registered for project '{who['project']}'" if who.get("project")
              else "registered for NO project — the roster is shared by every project of this server")
    return (f"it is '{who['id']}', {_whose}, and it validates in `{who.get('workdir') or '?'}`. "
            + ("" if _mine else
               "If that directory does not hold this delivery, its report will be about the wrong "
               "tree: register your own (`register_agent(<id>, \"llm-validator\", workdir=…)`). "))


def _mark_mine(engine: Engine, out: dict, me: Optional[str] = None) -> dict:
    """Del is LOAD-BEARING on the frontier, not a label: every step carries `mine` (the calling agent is
    the node's executor), and a FOREIGN executor-step's directive is rewritten to hands-off — the FSM
    would reject your executor signals on it anyway (source ≠ Del is a validation error). Foreign steps
    stay VISIBLE (that is the point: you see what the graph waits on).

    VALIDATION IS THE ISSUER'S, NOT THE EXECUTOR'S (§10.1: the issuer forms the task and validates the
    result). SO IS RESOLVE_BLOCK (§11.2 role table): the frontier offered `resolve` to the BLOCKED
    node's own executor, who then read "worker is not issuer for kid" from the FSM — the affordance
    and the machine disagreeing about the same act, found by walking the protocol 2026-08-21. Marking a `validate` step by the node's Del said the opposite: a delegated node waiting
    for its verdict came back `mine: false` to the very agent who owes that verdict, and its directive
    said both "VALIDATE this" and "NOT YOURS" at once. An agent that filters by `mine` — which is what
    the field is for — then skips its own obligation and the graph stops. So for `validate` the owner
    is the node's ISSUER: its parent's executor, or for a root the agent that assigned it.
    """
    me = me or _agent_id()
    for s in (out.get("steps") or ([out] if out.get("task_id") else [])):
        a = s.get("assignee")
        # …AND THE REVISION ONLY THE ISSUER CAN MAKE: an ESCALATED node (Inv-8: the issuer owns it) and a
        # node whose executor stopped without a signal. Marked by Del, both told their issuer "NOT
        # YOURS" about the one decision only he holds. A REVISE that repairs a node's own split stays
        # its executor's (§11.5: the split is authored by the node's executor).
        _t = engine.graph.get_task(TaskId(s["task_id"])) if s.get("task_id") else None
        if s.get("action") in (Action.VALIDATE, Action.RESOLVE) or (
                s.get("action") == Action.REVISE and _t is not None
                and (_t.state.name == "ESCALATED" or engine.parking.is_execution_parked(_t))):
            # …THE ENGINE'S RULE, ASKED (`issuer_of`), not a second reading of it. This one read the
            # PARENT alone, so a root — which has none — came back `mine: true` to whoever asked,
            # and the gate then refused their signal because a root's issuer is its own assignee.
            issuer = engine.graph.issuer_of(TaskId(s["task_id"])) if s.get("task_id") else None
            s["mine"] = (issuer == me) or not issuer
            continue
        s["mine"] = (a == me) or not a
        if s["mine"] and s.get("action") in SPAWNABLE_ACTIONS and (hands := engine.hands_of(a)):
            # DISPATCH: consent is the holder's, the work its hands' — told so, or it builds the node in its chat
            s["directive"] = ((f"ACCEPT it (consent is yours); then {hands} performs it in a clean session in the "
                               f"node's place — do not build it yourself. | contract: ")
                              if s.get("action") == Action.ACCEPT else
                              f"PERFORMED BY {hands} — your consent stands and a clean session of the system does "
                              f"the work and reports in your name; WAIT for it, do not build it yourself. Your moves "
                              f"here are the issuer's and the plan's. | contract was: ") + s.get("directive", "")
            s["parallel_ok"] = False
            continue
        if not s["mine"]:
            # …AND IT IS NOT A STEP TO FAN OUT EITHER. `parallel_ok` is documented as "delegate each
            # to its own executor subagent CONCURRENTLY", and it sat `true` on a node whose own
            # directive in the same object read "NOT YOURS (Del=…) — do NOT execute or signal for
            # it". A driver taking the field literally duplicates work the dispatcher is already
            # doing (measured on the agent door 2026-08-22).
            s["parallel_ok"] = False
        if not s["mine"] and s.get("action") in _EXECUTOR_ACTIONS:
            # WHO that executor IS decides whether waiting means anything. Saying "a human via the
            # UI" about a registered llm-executor made a driving agent report itself blocked on a
            # person for a node that autostarted thirty seconds later (measured 2026-08-20).
            # THIS engine's roster, published downward by the dispatcher (`engine.workforce.roster()`) —
            # never imported from it: this module is the layer below, and `test_layering` holds it.
            _kind = engine.workforce.kind_of(a)
            _who = ("a registered " + _kind + " — the dispatcher starts it by itself, so this node "
                    "is in hand, not stuck" if _kind else
                    "a human via the UI, or an external system by its own signals")
            s["directive"] = (f"NOT YOURS (Del={a}) — do NOT execute or signal for it; the graph WAITS "
                              f"for that executor ({_who}). Work your `mine` steps; surface this one "
                              f"to the user if the wait blocks you. | contract was: "
                              + s.get("directive", ""))
    return out


#: Words that RESTATE the verdict instead of recording an observation. A PASS already says "pass";
#: an observation whose whole content is another way of saying so has recorded nothing, and §2.3's
#: rule that a verdict with no check behind it is ⊥ does not stop applying because the ⊥ arrived
#: wearing a mapping. Both stranger doors closed a root this way on the same afternoon
#: (2026-09-02) — `"ok"`, `"looks green"`, `"dave says it works"` — and both testers named this,
#: rather than the identity of the reviewer, as the step the product stops one short of.
#:
#: Deliberately NARROW. This is not authentication and cannot be: at a loopback door a person names
#: themselves, and anyone determined to lie can write a sentence. What it refuses is the case where
#: nothing was written down at all, and it makes the deliberate case require a deliberate lie that
#: the record then carries — which is the guarantee §10.3 says the human door actually has.
# The floor on "this text records nothing" lives in the protocol layer, because the ENGINE
# needs it too: a DELIVER self-check is a verdict record (§10.3), and it was accepted at
# any thinness while THIS door refused the same words from a reviewer (wave 26, 2026-09-06).
# Aliased rather than reimplemented — a second spelling of one rule is how the two came apart.
_PURE_ASSENT = PURE_ASSENT
_is_pure_assent = is_pure_assent


def claim_drift(engine: Engine, task_id: str) -> dict:
    """How the node's CLAIM moved between the contract it was authored with and the one it holds
    now — criteria added / dropped / reworded, procedures changed, with the recorded revision
    reasons. Nothing here refuses anything: an agent MAY sharpen a criterion or record what contact
    revealed (a criterion can be a false mock, and only contact shows it), and must never leave the
    plan worse. This is the record that makes the movement readable instead of anecdotal."""
    return engine.claim_drift(TaskId(task_id))


def probe_inputs(engine: Engine, task_id: str) -> dict:
    """Lay this node's pinned probe inputs down and say where, with each command already resolved.

    A criterion's probe may pin the files it reads, and the SYSTEM writes them — so that nothing the
    executor wrote can stand in for the corpus the issuer pinned. The LLM validator gets them
    written into its packet; whoever validates BY HAND got a command with a literal `{inputs}` in it
    and the only resolution available was to point it at the delivery — which is the very defect the
    pinned corpus exists against, at the door where this project's false passes were measured. Call
    this first, run the commands as returned, and report them as you ran them."""
    t = engine.graph.get_task(TaskId(task_id))
    if t is None:
        return {"error": f"unknown task {task_id}"}
    # under the STATE directory: the home of a source checkout is the repository itself
    base = _data_dir() / "probe_inputs" / f"{task_id}_{int(time.time())}"
    # …the DONE parts' too, each reported under the criterion of this node it rests on (`Engine.parts_procedure`)
    under = [(c.name, c) for c in t.spec.criteria] + [
        (name, pc) for name, pcs in engine.parts_procedure(TaskId(task_id)).items() for pc in pcs]
    try:
        dirs = materialize_inputs([c for _, c in under], base)
    except ValueError as ex:
        return {"error": str(ex)}
    if not dirs:
        return {"task_id": task_id, "probes": [],
                "note": "no criterion of this node pins files with its check — every command reads "
                        "the delivered artefact as it stands"}
    return {"task_id": task_id, "probes": [
        {"criterion": name, "id": (pid := probe_id(c.name, p)),
         "command": p.command.replace(INPUTS_TOKEN, dirs[pid].as_posix()),
         "expect": p.expect, "inputs_dir": dirs[pid].as_posix(),
         "files": [x for x, _ in p.inputs]}
        for name, c in under for p in (c.check or ()) if p.inputs]}


def record_verdict(engine: Engine, task_id: str, verdict: str,
                   failed_criteria: Optional[list] = None, reviewer: Optional[str] = None,
                   observed: Optional[dict] = None) -> dict:
    """Record an INDEPENDENT reviewer's verdict on the node's CURRENT delivery — the human
    counterpart of validate_result (no LLM run): it is what unlocks a self-executed node's PASS
    through the verifier≠executor gate. Per-delivery: a rework stales it. The engine REFUSES a
    reviewer who IS the node's executor (recording a verdict on your own work is the self-stamp
    this system exists to catch); FAIL requires failed_criteria (Inv-3). After recording, the
    issuer still sends PASS / FAIL themselves — this is the evidence record, not the signal.
    On an INTERNAL node (its Del is its parent's) the refusal does NOT apply: §10.3 has such a
    node self-verify, and your own observations ARE the record the canon asks for. Observations that
    name no criterion of the node are kept out of the verdict and named back to you, not refused.
    An entry may carry `divergences: [...]` — what you saw that differs from what the criterion
    states. A criterion carrying one cannot be recorded `pass`: the divergence IS its value, and no
    register entry empties the list (Inv-2, §12.8)."""
    # SAY WHAT YOU OBSERVED — the same demand the machine door makes, at the grade a person can meet.
    # A validator's report is refused unless every criterion carries a re-runnable probe ("assessment
    # with no re-runnable observation is not evidence"); this door asked for nothing at all, and a
    # PASS with an empty per-criterion list closed a root while every metric read 1.0. Measured
    # 2026-08-20: `reviewer=STAND-IN-not-a-real-reviewer` was accepted without a word of evidence.
    # A person is not asked for commands — they are asked for a SENTENCE per criterion saying what
    # they checked. That is exactly the canon's remaining guarantee where no seam exists (§10.3's
    # degenerate case: making-explicit, plus the log), and it is what the log then carries.
    if observed is not None and not isinstance(observed, dict):
        return {"recorded": False,
                "error": f"`observed` is a mapping from CRITERION NAME to what you checked and what "
                         f"it showed — {{'<criterion>': 'ran X, it printed Y'}} — not "
                         f"{type(observed).__name__}. One line per criterion: the record has to say "
                         f"which criterion each observation settles, or it settles none of them."}
    # THE WORD, WHATEVER CASE IT WAS TYPED IN. `verdict=pass` was refused with "must be PASS or FAIL,
    # got 'pass'" — true, and a rule about capitalisation is not a rule about anything (measured on
    # the human door 2026-08-21). Anything that is NOT one of the two words still refuses, because
    # that is a real disagreement about what is being recorded.
    verdict = str(verdict).strip().upper()
    # WHO RECORDS IS THE CALLER, NOT A WORD THE CALLER MAY LEAVE OUT. The default was "human", so an
    # executor who did not name himself recorded a verdict on his own delivery AS someone else — the
    # refusal of reviewer == executor below compares names, and an omitted name never matched. The
    # misattribution was the default path, not a forgery (found by the theory stream's review of the
    # root seam, 2026-09-24). An omitted reviewer is the door's standing identity, as it is for every
    # other act on this surface (`_agent_id`); a person names themselves, as they do with `source`.
    reviewer = reviewer or _agent_id()
    _t = engine.graph.get_task(TaskId(task_id))
    # A NODE WITH NO CRITERIA CANNOT BE VALIDATED. V(t) is the conjunction over the node's criteria
    # (§2), and the conjunction over an empty set is vacuously TRUE — so the strongest guard in the
    # product, one observation per criterion, switches itself off when there is nothing to observe.
    # Measured on the HTTP door 2026-09-02: `create_task` with `criteria: []`, then `observed={}`
    # (the exact value refused a minute earlier on a node that had criteria), then PASS. Four
    # seconds from nothing to a green root called "Everything is done".
    # …AND NOT WHILE AN INSTRUMENT IS MID-VALIDATION. The DELIVER reply already tells the caller that
    # "recording your own verdict here would race it" — and nothing was behind that sentence, so the
    # race ran: a hand stamp closed a node 35 seconds before the instrument reported, the instrument's
    # signal was then refused for arriving at a terminal node, and its record landed on top of the
    # one that had done the closing (CLI door, 2026-09-02). Advice with nothing behind it is not a
    # rule; the claim it needs already exists, and this asks it without taking it.
    if _t is not None and engine.claims.validation_in_flight(TaskId(task_id)):
        return {"recorded": False,
                "error": f"an instrument is validating {task_id} right now — recording a verdict here "
                         f"would race it, and the loser of that race is whichever arrives second: "
                         f"a verdict landing on a node the other one already closed is refused as a "
                         f"signal and kept only as evidence. Wait for it (`get_verdict {task_id}` "
                         f"shows it when it lands), or validate a different node meanwhile.",
                "validation_in_flight": True}
    if _t is not None and not _t.spec.criteria:
        return {"recorded": False,
                "error": f"{task_id} has no criteria — there is nothing a verdict could be ABOUT. "
                         f"V is the conjunction over a node's criteria (§2), and over an empty set "
                         f"that is vacuously true, which is not a verdict. Give it criteria "
                         f"(`edit_criteria`) and validate those.",
                "criteria": []}
    if verdict == Verdict.PASS and _t is not None:
        # A GLUE CRITERION IS NOT SOMETHING THE EXECUTOR OBSERVES — its truth is the producer's
        # passing — so it is excluded from what a PASS must speak to. But a node whose criteria are
        # ALL glue has nothing of its own left to observe, and the floor then passes over an empty
        # requirement: the rule that is vacuously true at zero X, which is the rule's absence
        # wearing its name. Reproduced 2026-09-07: `edit_criteria(B, [])` wiped the contract, the
        # engine kept the `dep__A` criterion it had authored itself, and a PASS observing nothing
        # met a floor that asked for nothing. That is a defect of the CONTRACT, not of the verdict,
        # so it is named as one rather than papered over by demanding evidence for the glue.
        _need = [c.name for c in _t.spec.criteria if not c.depends_on]
        if not _need:
            return {"recorded": False,
                    "error": f"{task_id} carries no obligation of its own: every criterion it has "
                             f"is a dependency link the engine authored ("
                             + ", ".join(c.name for c in _t.spec.criteria) +
                             f"), so there is nothing a PASS could report having observed. A "
                             f"verdict cannot repair a contract — give the node criteria of its "
                             f"own (`edit_criteria`), or remove it if the work belongs elsewhere.",
                    "criteria": [c.name for c in _t.spec.criteria]}
        _said = {k for k, v in (observed or {}).items() if str(v).strip()}
        # …AND AN OBSERVATION THAT RESTATES THE VERDICT IS NOT ONE. Treated as unsaid, so the refusal
        # below names it in the same breath as one that was left out entirely — which is what it is.
        _empty = {k for k, v in (observed or {}).items() if _is_pure_assent(v)}
        _said -= _empty
        if (_missing := [c for c in _need if c not in _said]):
            return {"recorded": False,
                    "error": f"a PASS needs to say what was OBSERVED, one line per criterion — "
                             f"nothing recorded for: {', '.join(_missing)}. Pass "
                             f"`observed={{'<criterion>': 'what you checked and what it showed'}}`. "
                             f"The machine door is refused a verdict with no re-runnable probe; this "
                             f"is the same demand at human grade, and it is what the log will carry "
                             f"(§10.3: with no independent seam, the explicit record IS the guarantee)."
                             + (f" {', '.join(sorted(_empty))}: what you wrote restates the verdict "
                                f"rather than recording a check — name the command you ran and what "
                                f"it printed, the file you opened and what was in it, or the number "
                                f"you got. A PASS already says \"pass\"."
                                if _empty else "")}
    # AN EXTRA OBSERVATION IS NOT A DEFECT IN THE REPORT. The integrity rule refuses a report that
    # speaks of something that is not a criterion of this node — because such a report answers
    # another contract — and it is right about the MACHINE validator. A person adding a line about
    # the suite they ran alongside the criteria is not answering another contract, and the round
    # trip it cost them bought nothing: what protects against the real case is the OTHER half of the
    # rule, that every criterion must be spoken for, and that half still stands (agent door,
    # 2026-09-02).
    _known = {c.name for c in _t.spec.criteria} if _t is not None else set()
    _extra = {k: v for k, v in (observed or {}).items() if k not in _known}
    try:
        engine.record_reviewer_verdict(TaskId(task_id), verdict,
                                       list(failed_criteria or []), reviewer,
                                       observed={k: v for k, v in (observed or {}).items()
                                                 if k in _known} or None)
    except ValueError as e:
        return {"recorded": False, "error": str(e)}
    # …AND WHAT NOW. Recording a verdict changes nothing in the graph on its own — the node stays
    # in VALIDATING until someone SIGNALS. The reply said `recorded: true` and stopped, so a person
    # watched a node that had visibly not moved and had to find the next step in a docstring.
    _sig = (str(Verdict.PASS) if verdict == Verdict.PASS
            else f"{Verdict.FAIL} failed_criteria={list(failed_criteria or [])}")
    # AN ACT WITH CONSEQUENCES LEAVES A TRACE IN THE TRAIL A PERSON READS. `/api/audit` is the SIGNAL
    # trail by definition (the 12 P2P signals plus ASSIGN), and this is not a signal — but it is what
    # closes nodes, and a tester grepping for it found nothing while the verb's own help sells
    # durability ("it is what the log will carry"). Measured on the HTTP door 2026-09-02. The
    # observation strip already carries non-signal events, so the fact lands where it is looked for
    # without redefining what the audit IS.
    engine.emit_info("verdict",
                     f"{task_id}: {verdict} ASSERTED BY HAND by {reviewer} — "
                     f"{len(observed or {})} criterion observation(s) on the record. This is a "
                     f"person's word, not an instrument's verdict.")
    # …AND WHAT THIS RECORD JUST DISPLACED. An INSTRUMENT had validated this same delivery and said the
    # opposite; a hand verdict replaced it and the reply answered `recorded: true` with a helpful
    # next step, saying nothing. Measured on the HTTP door (wave 26, 2026-09-06): `validate_result`
    # returned FAIL with a re-runnable probe (`test -f … || echo FILE_ABSENT` printed FILE_ABSENT),
    # a PASS typed under an invented reviewer name replaced it, and the node closed COMPLETE with
    # `q_V: 1.0`. Overruling an instrument is LEGITIMATE — the verdict is the issuer's act (§10.3),
    # and §15.7 says no check can establish that a self-named reviewer is independent — so this
    # refuses nothing. What it does is say it at the moment of the act, to the party doing it, in
    # the reply they are already reading. The engine has carried the displaced verdict all along
    # (`overruled_verdict`); it simply never reached here.
    _displaced = engine.overruled_verdict(TaskId(task_id))
    return {"recorded": True, "task_id": task_id, "verdict": verdict, "reviewer": reviewer,
            "state": _t.state.name if _t is not None else None,
            **({"overruled": _displaced,
                "overruled_note":
                    (f"this record REPLACED an instrument's {_displaced.get('verdict')} on the same "
                     f"delivery. That is yours to do (§10.3 keeps the verdict the issuer's act), and "
                     f"it is the one fact about this node a later reader has to weigh: an instrument "
                     f"ran the criteria and disagreed with you. Both are kept — `get_verdict "
                     f"{task_id}` shows the displaced one beside yours.")} if _displaced else {}),
            **({"kept_out_of_the_record": sorted(_extra),
                "kept_out_note": (f"{len(_extra)} observation(s) name no criterion of this node, so they "
                                  f"are not part of the verdict (§2: the criteria ARE the "
                                  f"obligation) — the verdict itself was recorded.")} if _extra else {}),
            "next": (f"this is the RECORD, not the move: the node is still "
                     f"{_t.state.name if _t is not None else 'where it was'}. Signal it — "
                     f"`signal {task_id} {_sig} <issuer>` — and read the record back any time with "
                     f"`get_verdict {task_id}`.")}


def next_step(engine: Engine, root_id: Optional[str] = None, actor: Optional[str] = None) -> dict:
    """(Single-step view — `next_steps` is the PRIMARY driver; prefer it.) The EXECUTION forcing-point — call this in a LOOP and do EXACTLY what `directive` says, until it
    returns complete=True. It hands you the single next required action for the current frontier node
    (children before parents): accept / execute / deliver / validate / rework / confirm_cancel. You CANNOT stop
    until the root is DONE/PASS — the graph drives, you execute. Returns {complete, task_id, name, state,
    action, assignee, mine, criteria, directive}; `mine=false` = the node belongs to ANOTHER executor
    (human/external) — hands off, it waits for them. For PARALLEL delegation use next_steps.

    `actor=<name>` asks the question AS SOMEONE ELSE — the human door, where a person names
    themselves the way the UI always has. Without it the caller is the standing agent identity, and
    a person driving their own graph from the CLI was told `NOT YOURS (Del=<their own name>)` on
    every step of it (measured live: they stopped at the first node, reading it literally)."""
    return _mark_mine(engine, engine.next_step(TaskId(root_id) if root_id else None), actor)


def next_steps(engine: Engine, root_id: Optional[str] = None, actor: Optional[str] = None,
               wait: float = 0.0) -> dict:
    """The PARALLEL frontier: EVERY currently actionable node at once, priority-ordered. Steps with
    parallel_ok=true are independent execute-leaves (their Dep producers PASSED) — delegate each to its own
    executor subagent CONCURRENTLY. Do the non-parallel steps (accept/validate/rework/resolve/deliver)
    yourself in the returned order; `mine=false` steps belong to OTHER executors (human/external) — visible
    but hands-off. Loop until complete=True (root DONE/PASS). Returns {complete, steps}.
    `actor=<name>` asks as someone else — for a person driving their own graph from the CLI.

    `wait=<seconds>` BLOCKS until the frontier has something to hand back (or the root completes, or
    the time runs out) instead of returning "nothing to take right now". Every tester of the last two
    waves wrote the same poll loop by hand and spent 8–15 minutes of their run inside it, because a
    graph that is working looks exactly like a graph that is stuck from one call away. The answer is
    the same object either way; what changes is that the caller is not the one spinning."""
    _out = _mark_mine(engine, engine.next_steps(TaskId(root_id) if root_id else None), actor)
    if wait and not _mine_to_do(_out):
        _out = _waited(engine, root_id, actor, float(wait))
    return _out


def _mine_to_do(out: dict) -> bool:
    """Is there anything in this answer for the CALLER to do — or is the graph busy elsewhere?

    "Nothing to take" is not the same as "no steps": the frontier lists what OTHER executors hold
    too, precisely so a supervisor can see the graph working. What a waiting caller is waiting for is
    a step of their own.
    """
    return bool(out.get("complete")) or any(s.get("mine") for s in (out.get("steps") or ()))


def _waited(engine: Engine, root_id: Optional[str], actor: Optional[str], seconds: float) -> dict:
    """Ask again, on the engine's own clock, until the frontier answers or the time is gone.

    The clock is the ENGINE's (`ClockPort`), so a fake-clock host does not sit through a real wall
    wait; the sleep is the runner's. Bounded by `WAIT_MAX_SECONDS` — a call that never returns is a
    worse surface than one that returns "nothing yet", and a transport with its own ceiling would
    cut it anyway.
    """
    deadline = engine.now() + min(float(seconds), WAIT_MAX_SECONDS)
    while engine.now() < deadline:
        time.sleep(min(WAIT_POLL_SECONDS, max(0.0, deadline - engine.now())))
        out = _mark_mine(engine, engine.next_steps(TaskId(root_id) if root_id else None), actor)
        if _mine_to_do(out):
            out["waited_seconds"] = round(min(float(seconds), WAIT_MAX_SECONDS), 1)
            return out
    out = _mark_mine(engine, engine.next_steps(TaskId(root_id) if root_id else None), actor)
    out["waited_seconds"] = round(min(float(seconds), WAIT_MAX_SECONDS), 1)
    out["waited_note"] = ("nothing became actionable in that time — the graph may be working "
                          "(`in_flight`) or waiting on a person (`waiting`). Both are in this answer.")
    return out


# Registry: name -> function — the STRUCTURAL surface (this module is L1: core+engine only).
# The verbs that spawn LLM runs (auto_decompose / validate / validate_result) live in gfso.tools_llm,
# whose TOOLS dict is the COMPLETE transport registry (structural ∪ LLM) the binding layers use.
TOOLS = {
    "get_task": get_task, "project": project, "get_checks": get_checks, "get_graph": get_graph,
    "list_holes": list_holes, "get_review": get_review, "get_verdict": get_verdict,
    "dispute_finding": dispute_finding,
    "available_actions": available_actions, "get_dependencies": get_dependencies, "metrics": metrics,
    "usage": usage,
    "create_task": create_task, "decompose": decompose,
    "revise": revise, "edit_accepted_risks": edit_accepted_risks, "edit_scope": edit_scope,
    "edit_criteria": edit_criteria, "reassign": reassign,
    "reopen": reopen,
    "add_dependency": add_dependency, "remove_dependency": remove_dependency, "map_criterion": map_criterion,
    "signal": signal, "record_verdict": record_verdict, "claim_drift": claim_drift,
    "probe_inputs": probe_inputs,
    "next_step": next_step, "next_steps": next_steps,
}
