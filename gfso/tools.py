"""MCP tool layer — the agent's surface over the CORE upper API.

Pure functions `(engine, *args) -> JSON-able dict` so the logic is testable without the MCP transport.
Every AUTHORING tool desugars to the canonical 12-signal FSM (the lower layer is closed: no mutation
bypasses the audited protocol). The tool DOCSTRINGS are the agent's contract — they state, per tool,
which signals it desugars to, so a model never mistakes an authoring op for a new protocol primitive.
"""
from __future__ import annotations

import time
import uuid

from datetime import datetime
from typing import Optional, Union
from urllib.parse import quote

from gfso.core.types import (
    TaskId, AgentId, Spec, Criteria, AcceptedRiskItem, CriterionMapping,
    SignalData, Signal, Predictability, Action, EXECUTOR_ACTIONS, Verdict, State,
    RevisionReason, settled_positive, passed,
)
from gfso.core.graph.metrics import DIAGNOSTIC_MEANS, Q_MEANS, q_V_reversed
from gfso.core.graph.model import verdict_is_current_pass
from gfso.core.protocol.invariants import PURE_ASSENT, content_words, is_pure_assent
from gfso.core.protocol.validation import P2P_SIGNALS, Role
from gfso.config import (MODEL_VALIDATOR_RETRY, WAIT_MAX_SECONDS, WAIT_POLL_SECONDS,
                         agent_id as _config_agent_id)
from gfso.engine import Engine
from gfso.engine.validation import _l0_holes, _l2_undischarged, l2_gate_on


# The entry verbs whose result should tell the caller WHERE TO LOOK. Kept here, on the verb surface
# itself, because both doors need it: the MCP binding attached the link and the CLI/HTTP door did
# not, so a person driving by hand was never once told the address of the page built for them
# (measured 2026-08-20: fourteen calls, no link anywhere, while the agent door repeats it).
UI_LINK_VERBS = frozenset({"use_project", "create_task", "project", "auto_decompose"})

# The verbs that may bring a PROJECT into existence — everything else answers "no such project"
# rather than making one. A read that creates what it reads is how an installation reached 315
# projects, one per typo (measured 2026-08-21).
PROJECT_CREATING_VERBS = frozenset({"create_task", "auto_decompose", "decompose", "use_project"})

# The verbs that are not about a graph at all: the roster is ONE server-wide file, and asking it to
# name a project made `register_agent` refuse for a project that did not exist yet — while its own
# help says the roster is server-wide. A newcomer hit that as a chicken-and-egg on their first
# command (measured 2026-08-21).
PROJECTLESS_VERBS = frozenset({"register_agent", "list_agents"})


def ui_link(project: str | None = None) -> str:
    """The local address of the page that shows this graph (tab-per-project)."""
    # LEFT: `gfso.serverctl` is not in the core distribution (packaging/core_manifest.py) and
    # tools.py is — a module-level import here would put the transport inside the zero-dependency cut.
    from gfso import serverctl
    return f"{serverctl.BASE}/" + (f"?project={quote(str(project))}" if project else "")


# ── serialization helpers ────────────────────────────────────────────────────

def _predictability_from(raw) -> Optional[Predictability]:
    """STD-2's three categories, named when the caller guesses wrong.

    The scale is a legal term of art (§13.2: Ordinary / Statistical / Extraordinary — how the
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
            f"predictability {raw!r} is not one of the three STD-2 categories (§13.2): "
            f"ORDINARY = occurs regularly in the domain, so it belongs in the DECOMPOSITION, not "
            f"in accepted_risks · STATISTICAL = P is estimable and the event is infrequent — "
            f"admissible here WITH a justification · EXTRAORDINARY = no precedent and not derivable "
            f"from known models. It is a burden-of-proof scale, not a high/medium/low one.") from None


def _accepted_risks_from(items: list) -> tuple[AcceptedRiskItem, ...]:
    # predictability verdict (ORDINARY/STATISTICAL/EXTRAORDINARY) is MANDATORY per factor on a decomposed
    # node (CHECK-4 record form, §13.1) — plumbed here so agents can classify; a plain string stays unclassified.
    return tuple(
        AcceptedRiskItem(n) if isinstance(n, str)
        else AcceptedRiskItem(n["item"],
                           _predictability_from(n.get("predictability")),
                           n.get("justification", ""), n.get("invalidation_condition", ""))
        for n in items)


def _dep_of(c: dict) -> Optional[TaskId]:
    """The producer this criterion consumes — ONE node, or none.

    A Dep is criteria-content (§10): the seam lives on the consumer as a criterion naming its
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
            f"(§10), so declare one `depends_on` criterion for each producer you consume")
    if not isinstance(dep, str):
        raise ValueError(f"criterion '{c.get('name')}': depends_on must be a task id, got "
                         f"{type(dep).__name__}")
    return TaskId(dep)


def _spec_from(d: dict) -> Spec:
    crits = tuple(Criteria(c["name"], c.get("description", ""), depends_on=_dep_of(c))
                  for c in d.get("criteria", []))
    # `scope` is read here, not only written back in `_task_out`: without it the agent's door could
    # not express a scope BOUNDARY at all, and the only place left to put one was the risk register —
    # which CHECK-4 refuses by design (no materialization P ⟹ not a risk, §13.1). With the Syntactic
    # level gating, that was a dead end: the register the gate demands could not legally hold what the
    # agent had to declare.
    return Spec(d.get("description", ""), crits,
                _accepted_risks_from(d.get("accepted_risks", [])),
                scope=tuple(d.get("scope", ())),
                name=d.get("name", ""))


def _task_out(t, engine: Optional[Engine] = None) -> Optional[dict]:
    """The node as a reader sees it. `plan_verified` is about the node's DECOMPOSITION (its Level-2
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
                      "depends_on": c.depends_on} for c in t.spec.criteria],
        # THE REGISTER AS RECORDED, not its item texts. `edit_accepted_risks` learned to answer this
        # in full on 2026-08-21 and every OTHER read of a node kept returning bare strings — so a
        # caller who classified a risk STATISTICAL, justified it and named its invalidation
        # condition (the classification CHECK-4 demands, and per §13.1 the only thing that makes an
        # accepted risk auditable) got back the sentence they started from, from `create_task`,
        # `get_task` and the HTTP node read alike. Three independent doors reported it in three
        # waves, each as "I cannot tell whether the rest of it was stored" (2026-09-03/04). The
        # ITEM STAYS FIRST-CLASS under its own key, because prose, the UI and every existing reader
        # use it; what is added is the rest of the record beside it.
        "accepted_risks": [n.item for n in t.spec.accepted_risks],
        "accepted_risks_recorded": [
            {"item": n.item,
             "predictability": n.predictability.name if n.predictability else None,
             "justification": n.justification,
             "invalidation_condition": n.invalidation_condition}
            for n in t.spec.accepted_risks],
        "scope": list(t.spec.scope),
        "done_reason": t.done_reason.name if t.done_reason else None,
    }
    if engine is None or engine.get_active_children(t.id):
        out["plan_verified"] = t.verified
        # …AND WHETHER THAT LETS THE CHILDREN START, which is the question a reader actually has.
        # `plan_verified: true` means the STRUCTURAL levels are current; a caller read it as "the
        # plan is admitted" while `review_decomposition` was answering `execution_admitted: false`
        # about the same node in the same minute, and only that verb's payload carried the
        # disclaimer (measured on the human door 2026-08-22). Two surfaces, one fact.
        if engine is not None and (_open := engine.open_l2_findings(t.id)):
            out["execution_admitted"] = False
            out["l2_open"] = _open
        elif engine is not None:
            out["execution_admitted"] = t.verified
    return out


# ── READS ────────────────────────────────────────────────────────────────────

def _blocked_by(engine: Engine, t) -> Optional[dict]:
    """What a BLOCKED node is waiting for, in the node's own answer.

    "clear the blocker, then RESOLVE_BLOCK" — which blocker? `get_task` carried no reason and no
    blocker, `available_actions` listed the signal, and the only full text lived in a discovered Dep
    edge nobody had been pointed at (measured on the human door 2026-08-22). BLOCK records both
    (§14.2): the reason it gave and the nodes it named."""
    if t.state != State.BLOCKED:
        return None
    reason = next((a.reason for a in reversed(engine.audit_log(t.id))
                   if a.signal == Signal.BLOCK and not a.rejected and a.reason), "")
    on = sorted({str(e.from_id) for e in engine.get_dependencies() if str(e.to_id) == str(t.id)
                 and e.discovered})
    return {"reason": reason or "(the executor named none)", "waits_on": on,
            "what_now": (f"finish {', '.join(on)} — when they pass, the block clears by itself"
                         if on else "clear what the reason names, then RESOLVE_BLOCK (the issuer's "
                                    "signal, §14.3)")}


def get_task(engine: Engine, task_id: str) -> Optional[dict]:
    """Read a task node (spec, state, assignee, criteria, ACCEPTED_RISKS)."""
    t = engine.get_task(TaskId(task_id))
    if t is None:
        # `null` for a node that is not there made "no such id" and "nothing to say" the same
        # answer — and over HTTP a 200 with an empty body, which reads as success.
        return {"error": f"unknown task {task_id} — check the id, or `project=` if you meant "
                         f"another graph (`get_graph` lists what this one holds)"}
    out = _task_out(t, engine)
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
    t = engine.get_task(TaskId(task_id))
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
           "execution_admitted": bool(t.verified and not open_findings),
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
            f"can be wrong (§13.5) — and it is also the discharge nobody re-checks, so it is named "
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
                "(§14.5 degenerate case)"),
    "self": ("SELF-REPORTED by the node's own executor — not an independent check. §14.5 D6 makes "
             "an INTERNAL node's own report its record, and the guarantee is carried by the "
             "independent validation of the public result ABOVE it, never by this line"),
    "instrument": "produced by an instrument run — a fresh read-only judge that executed the "
                  "criteria — under the name in `validator`, which is not the node's executor",
}

#: …AND WHETHER THAT NAME IS ANYBODY. The sentence above used to say "the REGISTERED instrument",
#: which the record had never checked: a stranger passed `validator="w23http-ghost-instrument"` — a
#: name invented in that call and in no roster — and the read asserted registration about it, with
#: `by_hand: false` beside (HTTP door, wave 23, 2026-09-03). The judging itself was real, so the
#: verdict is not the defect; the CLAIM about who produced it is. The roster is a fact the engine
#: has, so the reading says which of the two it is instead of assuming the better one.
_UNREGISTERED = (" — NOTE: this name is not on the validator roster (`list_agents`), so it is a "
                 "label chosen by whoever asked for the run, not a standing instrument. The run "
                 "was real; who it is attributed to is not established")


def get_verdict(engine: Engine, task_id: str) -> dict:
    """The stored EXECUTION verdict on a node — the validator's LAST report, read back in full:
    PASS/FAIL, `failed_criteria`, and per criterion the probe that was run, what it printed and the
    behaviours it was labelled with. Free (no LLM). This is the counterpart of `get_review` (which
    reads the Level-2 verdict on the PLAN, not on the work).

    Written because the issuer had no way to READ what the judge said: `validate_result` returns its
    report once, to whoever called it, and a person coming back later — or a second agent, or anyone
    signing PASS/FAIL on the node — had the verdict in the database and no verb to reach it, so they
    were left signing on a summary. `verdict: null` = never validated. `undecidable` names the
    criteria whose declared behaviours were never observed — the INSTRUMENT's gaps, not failures of
    the work, and the reason a report can carry no PASS while refuting nothing (§11.2: ⊥ is not a
    verdict)."""
    t = engine.get_task(TaskId(task_id))
    if t is None:
        return {"error": f"unknown task {task_id}"}
    rec = engine.get_exec_verdict(TaskId(task_id))
    _prov = engine.verdict_provenance(TaskId(task_id))
    out = {"task_id": task_id, "state": t.state.name,
           "verdict": (rec or {}).get("verdict"),
           "validator": (rec or {}).get("validator"),   # the ROLE that judged, when one was registered
           # WHAT KIND OF PARTY IT WAS. A record a person asserted at a door where identity is
           # self-declared read back exactly like an instrument's report, so nothing downstream could
           # tell "a judge ran the work" from "someone typed a name" (measured on the CLI door
           # 2026-09-02). The gate cannot close that — FM-3's false PASS is guarded by no structural
           # CHECK (§13.6) — but the record must not present it as more than it is.
           "by_hand": bool((rec or {}).get("by_hand")),
           # THREE KINDS, not two. The middle one — an internal node's own executor stamping its
           # DELIVER (§14.5 D6) — was being reported as an instrument's work while the evidence line
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
           "per_criterion": (rec or {}).get("per_criterion") or [],
           # …and WHERE it was judged, so a probe that no longer reproduces is diagnosable rather
           # than mysterious (a rename after the verdict made every stored command unreplayable).
           "workdir": (rec or {}).get("workdir") or "",
           "ts": (rec or {}).get("ts")}
    # …AND SAY IT WHEN THE STATE AND THE RECORD DISAGREE. A node can stand at PASS while this very
    # record says FAIL: the signature landed before the instrument's verdict did, and the FSM
    # correctly refused that verdict on a node already terminal. Both facts were readable — the state
    # here, the verdict beside it — and nothing put them together, so `status` printed DONE for good
    # (CLI door, 2026-09-02). The engine owns the predicate; q_V has always counted exactly this.
    # …AND WHAT IT ACTUALLY CLOSED ON, when a later record has landed on top. Without this the
    # surface that answers "did anything close without proof" is the one surface that can be
    # rewritten after the close, in the closer's favour (HTTP door, 2026-09-02).
    # …AND A CONTRADICTION INSIDE THE JUDGING WINDOW, which the read simply did not carry. A second
    # verdict on one delivery replaces the first; when the two DISAGREE, the reader is being handed
    # one half of a disagreement and no sign that there was one (CLI door, wave 24, 2026-09-04: a
    # hand-asserted PASS replaced an instrument's FAIL and every summary surface showed an earned
    # green). Overruling is legitimate — the verdict is the issuer's act (§14.5) — and it is not
    # allowed to be invisible.
    if (_over := engine.overruled_verdict(TaskId(task_id))):
        out["overruled"] = {
            "verdict": _over.get("verdict"), "validator": _over.get("validator"),
            "by_hand": bool(_over.get("by_hand")), "ts": _over.get("ts"),
            "failed_criteria": _over.get("failed_criteria") or [],
            "per_criterion": _over.get("per_criterion") or []}
        out["overruled_note"] = (
            f"a {_over.get('verdict')} on THIS delivery by {_over.get('validator')!r} was replaced "
            f"by the record above. Two parties judged one delivery and disagreed; the standing "
            f"verdict is the later one, and this is the one it displaced — weigh both. "
            + ("The displaced verdict came from an INSTRUMENT that ran the criteria; the one "
               "standing over it was asserted by hand, which the engine cannot check for "
               "independence (§13.6)."
               if not _over.get("by_hand") and bool((rec or {}).get("by_hand")) else ""))
    if (_closed_on := engine.closing_verdict(TaskId(task_id))):
        out["closed_on"] = {
            "verdict": _closed_on.get("verdict"), "validator": _closed_on.get("validator"),
            "by_hand": bool(_closed_on.get("by_hand")), "ts": _closed_on.get("ts"),
            "per_criterion": _closed_on.get("per_criterion") or [],
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
    # A verdict belongs to the delivery it judged. A node that has since been reworked or revised
    # carries a record about an EARLIER artifact, and read as current it is exactly the stale
    # evidence this system exists to refuse.
    # WHICH delivery a record judged, and whether that is the one standing now, is the ENGINE's
    # rule (`current_exec_verdict`) — the frontier asks the same question, and two spellings of it
    # would answer differently the first time either moved.
    gen = engine.VERDICT_GENERATION
    _current = engine.current_exec_verdict(TaskId(task_id)) is not None
    if rec is not None:
        # …AND SAY IT WHEN IT IS CURRENT. Only staleness was ever announced, so "no `stale` field"
        # had to be read as "current" — an absence standing for an assertion, which a reader has to
        # know the convention to decode (measured on the agent door 2026-08-21: "the record doesn't
        # assert it"). The generation it judged is what makes it checkable.
        out["current"] = _current
        out["judged_generation"] = {k: rec.get(k, 0) for k in gen}
        out["node_generation"] = {k: getattr(t, k, 0) for k in gen}
        if not _current:
            # The GENERATION, not the iteration alone: a REOPEN moves `reopens` and a revision moves
            # `revisions`, and neither touches the iteration — so a verdict from before a reopen read
            # as current. Measured 2026-08-20: after a reopen and a fresh delivery, the previous
            # delivery's PASS came back with no mark on it at all.
            out["stale"] = ("this verdict judged an EARLIER delivery — recorded at "
                            + ", ".join(f"{k} {rec.get(k, 0)}" for k in gen)
                            + "; the node now stands at "
                            + ", ".join(f"{k} {getattr(t, k, 0)}" for k in gen)
                            + ". Re-validate before signing on it.")
    if rec is None:
        # …AND "NOT VALIDATED" IS THE WRONG WORD WHEN A REPORT WAS REFUSED. A judge ran, reported,
        # and the engine refused the report as ⊥ (§11.2) — which is a different situation from
        # nobody having looked, and it is the one that needs a decision. The note said the node had
        # not been validated while the refused report sat further down the same object, and a
        # tester polled for fifteen minutes before scrolling into it (agent door, 2026-09-02).
        _ref = engine.rejected_report(TaskId(task_id))
        out["note"] = (
            (f"a validator DID report on {task_id} and the engine REFUSED the report as ⊥ — "
             f"{_ref.get('refusals', 1)} time(s) so far; see `refused_report` below for what it "
             f"managed to observe. This is not a verdict and never becomes one: either run "
             f"`validate_result('{task_id}', model='{MODEL_VALIDATOR_RETRY}')` for a judge with more "
             f"room, or put your own observation on the record with `record_verdict`.")
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
        if str(task_id) in engine.parked_validations():
            out["automatic_validation"] = "gave up"
            out["note"] += (" AUTOMATIC VALIDATION HAS GIVEN UP on this node: the instrument was run "
                            "and could not produce a verdict, so nothing further will arrive by "
                            "itself (⊥ is not pass, §11.2 — the issuer decides). Escalate the judge "
                            f"(`validate_result('{task_id}', model='{MODEL_VALIDATOR_RETRY}')`), "
                            "narrow what the node promises (`edit_criteria`), or record what YOU "
                            "observed (`record_verdict`). Waiting is the one thing that will not "
                            "work.")
    # WHAT WAS DELIVERED, which no verb returned at all. The frontier tells an issuer to "check the
    # deliverable against the criteria", and the deliverable — the executor's own DELIVER report,
    # stored because the validator reads it — was reachable from no door: a person judging a
    # delegated node found out what it had done by listing the directory (measured on the agent door
    # 2026-08-21).
    if (_report := engine.deliver_result(TaskId(task_id))):
        out["delivered"] = _report
    # …and if a report was REFUSED here, what it managed to observe — evidence, never a verdict
    # (§11.2). A node parked on two refused reports asks its issuer to decide; this is what there is
    # to decide with.
    if (rej := engine.rejected_report(TaskId(task_id))):
        out["refused_report"] = {
            "why_it_is_not_a_verdict": rej.get("defects"),
            "refusals_on_this_node": rej.get("refusals", 1),   # two = the contract, not the run
            "observed_anyway": rej.get("per_criterion") or [],
            "ts": rej.get("ts"),
            "note": "this is EVIDENCE, not a verdict: the judge could not decide every criterion, "
                    "and ⊥ is not a pass. Read it, then either run the validation again (a stronger "
                    "model usually closes a coverage gap) or record your own verdict.",
        }
    return out


def dispute_finding(engine: Engine, task_id: str, criterion: Union[str, list], why: str) -> dict:
    """Record why ONE Level-2 finding is wrong — the alternative to fixing the plan (which does not
    discharge a finding: it retires the whole verdict, and `review_decomposition` must speak again). Execution is
    gated on every finding of the CURRENT review being discharged: either the plan changes (which
    stales the review — re-run it) or the finding is disputed HERE, in writing. The checker is an
    a-priori approximation (§13.5) and can be wrong; what the system refuses is skipping it
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
    # checker is an approximation and may be wrong (§13.5); what discharges it is a REASON, and
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
                          f"(§13.5) — say WHICH criterion or child already carries the obligation, "
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
    word = str(raw).strip().upper()
    if word in (Verdict.PASS, Verdict.FAIL):
        return Verdict[word]
    raise ValueError(
        f"self_validation is your own VERDICT on this delivery — \"PASS\" or \"FAIL\" (§14.2), not a "
        f"report: got {str(raw)[:60]!r}. What you checked and what it printed goes in `result`, per "
        f"criterion; the word here is what you conclude from it.")


def _coverage_lost_by(engine: Engine, task_id: str) -> Optional[dict]:
    """Which of the PARENT's criteria this node was carrying, now that it is a tombstone.

    A cancelled child takes its `covers` with it, and the parent's plan quietly becomes a different
    plan: with the last child gone the node reads as a leaf again, so the coverage checks stop
    applying and `list_holes` is empty — structurally correct and, said that way, indistinguishable
    from "nothing changed". Whoever cancelled is the one who has to decide what now carries those
    criteria (walked by hand 2026-08-21)."""
    parent = engine.get_parent(TaskId(task_id))
    if parent is None:
        return None
    carried = sorted(m.criterion_name for m in parent.criterion_mappings
                     if str(m.child_id) == str(task_id))
    if not carried:
        return None
    left = [str(c.id) for c in engine.get_active_children(parent.id)]
    return {"parent_id": str(parent.id), "criteria_it_carried": carried,
            "children_left": left,
            "what_now": (f"nothing carries {carried} any more — decompose '{parent.id}' again, or "
                         f"execute it directly (with no children it is a leaf, and its criteria are "
                         f"its own work)" if not left else
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
    """The signals the FSM lists but a GATE would refuse, removed — with the reason and the opener.

    Its own function because the affordance surface has to model three gates (the plan's §13.4, the
    seam's §14.5, and the internal node's own self-check) and every one of them was added after a
    live run found the surface offering what the machine then rejected."""
    gate_note = None
    # …and the PLAN gate, which this verb did not model at all: measured live, it offered ACCEPT on a
    # child whose parent's plan had no current Level-2 verdict, and the signal was refused (§13.4).
    if Signal.DELIVER.name in acts and (_open := [c.id for c in engine.get_active_children(t.id)
                                                 if not passed(c)]):
        # A PARENT DELIVERS ITS CHILDREN'S AGGREGATE (Thm 1), so delivering while they are unfinished
        # only parks it: no validator will judge it (a verdict would be refused at the gate), its own
        # PASS is refused too, and the node then sits in VALIDATING outside the frontier. Measured on
        # the human door 2026-08-21: offered here, accepted by the FSM, and the node was gone from
        # `next_steps` for an hour. The signal stays admissible where §14.3 admits it; what stops is
        # this surface RECOMMENDING it.
        acts = [a for a in acts if a != Signal.DELIVER.name]
        gate_note = (f"DELIVER is not the move yet: {task_id} aggregates children that have not "
                     f"passed ({', '.join(str(c) for c in _open)}), and a parent's verdict is the "
                     f"AND over them (Thm 1). Delivering now parks it in VALIDATING — no verdict can "
                     f"be given, and its own PASS is refused. Drive those children first.")
    if "ACCEPT" in acts:
        if (_shut := engine.execution_blocked_by(TaskId(task_id))) is not None:
            acts = [a for a in acts if a != "ACCEPT"]
            gate_note = (f"ACCEPT is not open yet: this node's parent ('{_shut['parent_id']}') has a "
                         f"plan that is not admitted to execution (§13.4) — {_shut['why']}. "
                         f"{_shut['opens_with']}. The signal would be refused, and the executor's "
                         f"work with it.")
    if (Signal.ASSIGN.name in acts and t.state.name in ("DONE", "ABANDONED")
            and _reopen_gate(engine, t) is None):
        # …AND WHEN IT IS OPEN, SAY WHAT IT IS. On a finished root the ONLY action offered was the
        # bare word "ASSIGN", and taking it — a self-assignment that changed nothing — silently
        # reverted DONE to OFFERED, dropped the verdict and spent a reopen; recovering cost a
        # re-delivery and a $0.60 opus re-validation (measured on the human door 2026-08-22). The
        # signal is legitimately open there (R′ rides on it, §14.3); what was missing is that its
        # name says nothing about what it does to a node that is already finished.
        gate_note = (f"ASSIGN on {task_id} is a REOPEN (R′, §14.3), not a no-op: it returns a "
                     f"finished node to OFFERED, its verdict is GONE (re-earned by fresh contact) "
                     f"and one of its {t.max_reopens} reopens is spent. `reopen` is the same act "
                     f"under its own name, and `revise` is it with a new contract.")
    if Signal.ASSIGN.name in acts and (shut := _reopen_gate(engine, t)) is not None and t.state.name in (
            "DONE", "ABANDONED"):
        # A terminal node lists ASSIGN because §14.3's R′ edge rides on it — but the edge is
        # double-gated, and when the gate is shut the FSM answers "its transition GUARD refused it —
        # the precondition does not hold", which names nothing. Walked by hand 2026-08-21 on a
        # consumed child: `reopen` explained itself perfectly and the affordance list beside it still
        # said ASSIGN.
        acts = [a for a in acts if a != Signal.ASSIGN.name]
        gate_note = shut["error"]
    if (Signal.PASS.name in acts and t.assignee == AgentId(who) and not engine.is_seam(t)
            and not verdict_is_current_pass(engine.get_exec_verdict(TaskId(task_id)), t)):
        # …and the INTERNAL node's own rule, which this surface has to model too. Such a node
        # self-verifies rather than being judged independently (§14.5 D6) — but through the check its
        # DELIVER carries, and a PASS with nothing behind it is ⊥ (§11.2). Offering PASS here while
        # the machine refuses it is the same lie the seam case was fixed for.
        acts = [a for a in acts if a != Signal.PASS.name]
        gate_note = (f"PASS is not open yet: {task_id} is INTERNAL (same Del as its parent), so it "
                     f"self-verifies — but nothing says what was checked for this delivery. "
                     f"`record_verdict('{task_id}', 'PASS', observed={{…}})` with what you ran and "
                     f"what it printed, then signal; a DELIVER carrying `self_validation` records it "
                     f"for you. FAIL is open to you: refusing your own work needs no check."
                     + (f" NOTE: an instrument is judging this delivery RIGHT NOW — if you sign "
                        f"before it lands, its verdict arrives at a node that has already closed, "
                        f"and the graph will show your signature with the instrument's verdict "
                        f"contradicting it (`next_steps` reports that as `refuted_passes`). Waiting "
                        f"costs a minute; the other way costs the node."
                        if engine.validation_in_flight(TaskId(task_id)) else ""))
    if (Signal.PASS.name in acts and engine.is_seam(t)
            and not engine.signs_as_instrument(who)):
        # THE SEAM'S RULE, WHOEVER ASKS. This mirrored the engine's old shape — it dropped PASS only
        # for the node's own executor — so on a delegated node it advertised PASS to the issuer with
        # no verdict on the record and none of the fields this verb documents. Measured on the agent
        # door 2026-08-22: the driver read the bare list as an invitation, signed, and a node went
        # DONE over a STALE FAIL while its validator was still running. The surface follows the
        # machine: at a seam the question is whether a verdict for THIS delivery exists, not who is
        # holding the pen (`engine.current_exec_verdict` is the one owner of that question).
        rec = engine.current_exec_verdict(TaskId(task_id))
        if rec is None or rec.get("verdict") != Verdict.PASS:
            acts = [a for a in acts if a != Signal.PASS.name]
            _mine = t.assignee == AgentId(who)
            _state = ("no verdict for this delivery is on the record" if rec is None
                      else f"the recorded verdict is {rec.get('verdict')}, not PASS")
            gate_note = (f"PASS is not open here: {task_id} is a SEAM (a root, or its Del differs "
                         f"from its parent's), where the result is judged in the scope it crosses "
                         f"into (§14.5) — and {_state}. `validate_result('{task_id}', workdir=…)` "
                         f"runs the instrument, or `record_verdict('{task_id}', 'PASS', "
                         f"observed={{…}})` puts what YOU observed on the record; then signal. FAIL "
                         f"is open"
                         + (" to you: refusing your own work needs no second opinion "
                            "(verifier ≠ executor, §14.5, is about the PASS)."
                            if _mine else ": a refusal needs no independent verdict."))
    return acts, gate_note


def available_actions(engine: Engine, task_id: str, agent: Optional[str] = None) -> dict:
    """(Rarely needed — next_steps' directive already names the required action.) The protocol signals
    valid in this node's state for the ASKER's role: {actions, state, role, why_none, gate}.
    Defaults to YOU; `agent=<name>` asks as someone else (the human door names its user), and
    `agent="*"` is the any-role view the UI wants. The list is what would actually be ACCEPTED —
    signals the seam gate (§14.5) or the plan gate (§13.4) would refuse are removed, with `gate`
    saying why and what opens them.

    An EMPTY list is an answer, and it used to be given as a bare `[]`. Measured live: a person held
    a node they had just delivered, asked what they could do with it, and got nothing — while
    `signal` on the same node explained in full that a PASS by the node's own executor needs an
    independent verdict first (§14.5). The list was TRUE; the silence around it was the defect. So
    when nothing is open, the reason is said here too, in the same words the signal would use."""
    # WHOEVER IS ASKING, ASKED AS THEMSELVES. With no `agent` this listed every signal open in the
    # state to ANY role — four actions the caller could not perform, and no `why_none` either. The
    # door pins identity for `signal` ("impersonation is impossible") and forgot it here; measured
    # 2026-08-20 through the MCP door. `agent="*"` is the old any-role view, which the UI wants.
    who = _agent_id() if agent is None else agent
    acts = [s.name for s in engine.available_actions(TaskId(task_id),
                                                     None if who == "*" else AgentId(who))]
    t = engine.get_task(TaskId(task_id))
    if t is None:
        return {"error": f"unknown task {task_id}"}
    # …and what the SEAM would refuse comes out of the list, with the reason. Listing PASS where the
    # verifier ≠ executor gate rejects it is the same lie in the other direction: the affordance
    # surface must agree with the machine, in both directions (§14.5).
    acts, gate_note = _gated_out(engine, t, task_id, who, acts)
    out = {"task_id": task_id, "state": t.state.name, "actions": acts}
    if gate_note:
        out["gate"] = gate_note
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
        issuer = engine.issuer_of(TaskId(task_id))
        out["role"] = role.name if role is not None else None
        if not anyone:
            out["why_none"] = (f"{who} has no move on {task_id}: nothing is open to ANY role in "
                               f"{t.state.name} — the state is terminal, or the node waits on the "
                               f"system clock. `next_steps` names what the graph is waiting on.")
            # …and for a settled node, WHICH recovery the canon leaves open, since "terminal" alone
            # sent a person hunting through four verbs for one that was not refused (§14.3 gives a
            # different answer for each terminal; walked by hand 2026-08-21).
            if t.state == State.ESCALATED:
                out["recovery"] = (
                    f"'{task_id}' exhausted its rework loop — that is a settled FAIL, and the canon "
                    f"hands it to the ISSUER (§14.3): re-decompose AROUND it, adding a child that "
                    f"carries what it left uncovered. It is not reopened and takes no revision.")
            elif t.state in (State.DONE, State.ABANDONED):
                out["recovery"] = (
                    f"'{task_id}' is finished. `reopen` puts it back to OFFERED under its standing "
                    f"contract (R′, §14.3) unless the graph has CONSUMED it — the refusal says which "
                    f"gate stopped it; `revise` reopens it WITH a new contract.")
        elif role is None:
            out["why_none"] = (f"{who} holds no role on {task_id}: its executor is "
                               f"{t.assignee or 'nobody'} and its issuer is {issuer}. Each signal "
                               f"belongs to one of those two (§14.2); here {', '.join(anyone)} "
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
                   f"own executor cannot sign its verdict (verifier ≠ executor, §14.5). Record an "
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

    `validator` — an independent judgement of this delivery is running · `issuer` — a verdict is on
    the record and the signal is owed · `verdict` — delivered, nobody judging yet · `executor` — a
    registered machine holds it. None where the state speaks for itself."""
    if t.state.name == "VALIDATING":
        if engine.validation_in_flight(t.id):
            return "validator"
        return "issuer" if engine.current_exec_verdict(t.id) is not None else "verdict"
    if t.state.name in ("EXECUTING", "REWORKING") and engine.kind_of(t.assignee) == "llm-executor":
        return "executor"
    return None


def get_graph(engine: Engine) -> dict:
    """The whole graph: nodes (id, name, state, parent) + edges (parent-child and dependency). The bird's-eye
    view — use it to see overall progress / where the frontier is."""
    tasks = engine.all_tasks()
    nodes = [{"id": str(t.id), "name": t.spec.name or t.spec.description[:40], "state": t.state.name,
              "assignee": t.assignee,        # who holds this node — the graph read answered `null` for
                                             # every node while `get_task` named the executor (2026-08-21)
              "done_reason": t.done_reason.name if t.done_reason else None,  # ABANDONED = a tombstone (grey it)
              # …AND WHAT A VALIDATING NODE IS WAITING FOR. "Being judged" and "judged, waiting for
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
    edges += [{"source": str(d.from_id), "target": str(d.to_id), "type": "dependency"}
              for d in engine.graph.dep_edges()]
    return {"nodes": nodes, "edges": edges}


def list_holes(engine: Engine, root_id: Optional[str] = None) -> dict:
    """Every UNMET structural check across the whole graph (or the subtree under root_id) — the full gap list.
    Call this AFTER auto_decompose / before driving execution: a decomposed graph may come back with failing
    checks (coverage/glue/ACCEPTED_RISKS/…); this shows them ALL at once so you can fix ∨ declare them up front,
    instead of discovering them one PASS-rejection at a time. Returns [{task_id, name, check, details}];
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
    question was the judge's share of spend — with the true split ($2.33 of $3.44, 68% on judging)
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

    A null is ⊥ — an empty population, not a zero (§21): no event of that kind has happened yet, and
    the difference matters when the number is read as a health score."""
    out = engine.metrics()
    # WHAT THE NUMBER IS MADE OF, for the one metric people read as an accusation. A bare `q_T: 0.0`
    # over a graph whose plan was honestly repaired on the gate's findings looks like a failing grade
    # for the person doing the repairing (measured on the human door 2026-08-21); the nodes that
    # contributed the event are the answer to "why", and the reader can check them against the log.
    tasks = engine.all_tasks()
    # …AND WHICH KIND OF DEFECT EACH WAS. Both members of the canon's numerator are spec defects
    # (§15.2), and they are found at opposite ends: a CHALLENGE is an executor meeting a broken
    # contract while working under it, and a criteria change is one caught before the work — often
    # by this product's own plan gate. A user who closed nine gate findings correctly read a low
    # q_T as a grade on themselves (agent door, 2026-09-02). The number does not move; what it is
    # made of is now legible without a paragraph of self-defence.
    _challenged = [str(t.id) for t in tasks if t.was_challenged]
    _repaired = [str(t.id) for t in tasks
                 if t.spec_defect_criteria_change and not t.was_challenged]
    if _challenged or _repaired:
        out["q_T_from"] = {"contracts_issued": len(tasks),
                           "counted_against": _challenged + _repaired,
                           "disputed_by_an_executor": _challenged,
                           "repaired_before_the_work": _repaired,
                           "note": ("both are spec defects and both count (§15.2). The second kind "
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

def _agent_id() -> str:
    """The calling agent's standing identity. Identity is TRANSPORT-derived, not configured: this tool
    surface (MCP/CLI) is the AGENT's single entry point — the UI is the human's door and always passes an
    explicit name — so an omitted `assignee` can only mean "the agent itself". Works out of the box as
    `agent`; GFSO_AGENT_ID merely RENAMES it (multi-agent future), it is never required."""
    return _config_agent_id()


def create_task(engine: Engine, task_id: str = "", spec: Optional[dict] = None,
                assignee: Optional[str] = None,
                parent_id: Optional[str] = None, deadline: Optional[str] = None) -> Optional[dict]:
    """Create a node. Desugars to ASSIGN (creation IS the ASSIGN effect, logged). `task_id` auto-generated if
    omitted; `deadline` = an ISO-8601 string (completes T=(spec,criteria,deadline), §10). spec =
    {name: short title (≤6 words), description: the full text, criteria: [{name, description}],
    accepted_risks: [{item, predictability, justification, invalidation_condition}], scope: [str]}.
    ACCEPTED_RISKS holds risk EVENTS with a materialization probability and is MANDATORY on a node you
    decompose (§13.1; CHECK-4 gates execution on it); a capability the goal deliberately excludes has
    no such probability and goes in `scope` instead. `predictability` is one of exactly three
    (STD-2, §13.2 — a burden-of-proof scale, not high/medium/low): ORDINARY (occurs regularly in the
    domain ⇒ it belongs in the DECOMPOSITION, not here), STATISTICAL (P estimable, event infrequent
    — admissible WITH a justification), EXTRAORDINARY (no precedent, not derivable from known
    models).
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
    if (_existing := engine.get_task(tid)) is not None:
        return {"error": f"'{tid}' already exists — it is '{_existing.spec.name or tid}' in state "
                         f"{_existing.state.name}, owned by {_existing.assignee or 'nobody'}. "
                         f"`create_task` creates; to CHANGE this node use `revise` (whole contract), "
                         f"`edit_criteria` (its criteria) or `reassign` (its executor) — each is a "
                         f"logged revision under the same id (Inv-1, §14.4). If you meant a "
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
    dl = _deadline(deadline)
    t = engine.assign_task(tid, _spec_from(spec or {}), AgentId(assignee or _agent_id()),
                           parent_id=TaskId(parent_id) if parent_id else None, deadline=dl)
    out = _task_out(t)
    # A CONTRACT-LESS NODE IS LEGAL AND CANNOT DO ANYTHING, so the reply says so. Authoring later is
    # supported — `spec` is optional on purpose — but the answer to a bare `create_task` was a
    # success line with a generated id and no hint that this node can never be judged (V is the
    # conjunction over its criteria, and over an empty set that is vacuously true, which the engine
    # refuses at the record). Typed to see the shape of the verb, it silently puts an unusable node
    # in a shared graph; two such strays sit in this machine's `default` project (2026-09-05).
    if not t.spec.criteria:
        out["note"] = (f"{t.id} has NO criteria, so nothing can be judged about it and no verdict "
                       f"will ever be admitted (V = the conjunction over a node's criteria, §10). "
                       f"Author it: `revise('{t.id}', {{description, criteria:[{{name, description}}]}})`, "
                       f"or `auto_decompose` from the goal text. Creating it empty is legal — this "
                       f"is what it is.")
    return out


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


def decompose(engine: Engine, parent_id: str, children: list[dict],
              mappings: Optional[list[dict]] = None,
              max_iterations: Optional[int] = None) -> list[dict]:
    """(Manual path — `auto_decompose` is the normal way to structure.) Break a node into children.
    Desugars to one ASSIGN per child. children: [{task_id, spec, assignee, covers, deadline?}]; an omitted
    assignee = `agent` (you execute it yourself; name someone only to really delegate).

    Every parent criterion must be MAPPED to the child that delivers it, or the decomposition fails
    Level-0 coverage and no child may start. Declare it either way: `covers: ["criterion", …]` on
    the child, or the flat `mappings=[{criterion_name, child_id}, …]`. (This text described `covers`
    while the code read only `mappings`, so a decomposition that used it came back successful with
    the mapping silently dropped, and the refusal arrived later as an unexplained coverage failure.)
    """
    if not children:
        # AN EMPTY DECOMPOSITION IS NOT A MAPPING VERB. Called with `children=[]` and a `mappings=`
        # list, this returned `[]` and REPLACED the parent's whole mapping set — five criteria
        # uncovered and three children orphaned, from a call that looked like a no-op. It was the
        # only way the caller had found out of a dangling mapping, which is a different defect, now
        # closed (measured on the human door 2026-08-21).
        return {"error": f"decompose needs children: it creates them. With an empty list this used "
                         f"to REPLACE {parent_id}'s coverage wholesale — `map_criterion` binds one "
                         f"existing child to one criterion, and `edit_criteria` re-authors the "
                         f"contract (which also prunes mappings to children that are gone).",
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
    kids = [(TaskId(c["task_id"]), _spec_from(c["spec"]),
             AgentId(c.get("assignee") or _agent_id()), _deadline(c.get("deadline")))
            for c in children]
    declared = [CriterionMapping(name, TaskId(c["task_id"]))
                for c in children for name in (c.get("covers") or ())]
    maps = ([CriterionMapping(m["criterion_name"], TaskId(m["child_id"])) for m in (mappings or [])]
            + declared) or None
    # The rework bound rides the ASSIGN of every child: §14.3 bounds the DELIVER→FAIL loop and
    # §26.9(b) states no failure mode pins the number, so it is a term of the CONTRACT chosen per
    # decomposition — not a property of whichever process happens to be serving.
    return [_task_out(t) for t in engine.decompose_task(TaskId(parent_id), kids, maps,
                                                       max_iterations)]


#: The closed sets a verb's string parameters accept, as DATA — keyed by VERB and parameter, never by
#: parameter alone. The refusals name them perfectly and the docstrings spell them out, but both are
#: prose, so a caller building against the catalogue had to parse English or be refused once per verb
#: (HTTP door, 2026-09-02: a tester silently no-op'd five edits before a refusal told them).
#:
#: Keyed by verb because the same NAME is not the same set: `signal`'s `reason` is free text — why a
#: node is blocked or cancelled — while `revise`'s is the §24.5 causal type. Keying by name alone
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
    """§24.5 causal typing at the transport boundary: an optional reason string → RevisionReason.
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


def revise(engine: Engine, task_id: str, spec: dict, agent: str,
           reason: Optional[str] = None,
           expect_criteria: Optional[list] = None) -> Optional[dict]:
    """Revise a node's whole spec. Canon v3.7 Inv-1: a spec change = re-ASSIGN under the SAME id → OFFERED
    (NOT a CANCEL — no cascade, no tombstone; the executor re-ACCEPTs the new contract). The subtree is
    RETAINED (revision ≠ abandonment); if a criteria change strands a child's coverage it shows up as a
    CHECK-1/CHECK-1b failure to resolve. `agent` must be the issuer (ASSIGN is an issuer signal).
    `reason` (optional, §24.5): why the revision — spec_defect (criteria were wrong; counts in q_T) |
    scope_expansion (sanctioned §13.1; never counts) | capability_mismatch | other.

    **WHOLE means whole: a key you omit is a key you DELETE.** Passing `{description: …}` alone
    wipes the criteria, the ACCEPTED_RISKS, the scope and every criterion→child mapping — measured
    2026-08-21, where the reply looked like an ordinary success and the loss surfaced later as two
    failing checks. So an omission that would DESTROY something is refused here and named; pass the
    field (even unchanged) to mean it, or use the verb that carries the rest: `edit_criteria`,
    `edit_accepted_risks`, `reassign`.

    `expect_criteria=[<the names you read>]` makes the replacement CONDITIONAL: if the contract
    moved between your read and this call — a background `auto_decompose` refining it is the
    ordinary case — the call is refused and names what changed, instead of silently dropping work
    you never saw."""
    t = engine.get_task(TaskId(task_id))
    if t is None:
        return {"error": f"unknown task {task_id}"}
    if (_moved := _contract_moved_under_you(t, expect_criteria)):
        return _moved
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
    return _task_out(engine.revise(TaskId(task_id), _spec_from(spec), AgentId(agent),
                                   reason=_reason_from(reason)))


def edit_accepted_risks(engine: Engine, task_id: str, accepted_risks: list,
                        agent: str = "") -> Optional[dict]:
    """Replace a node's ACCEPTED_RISKS (the RISK register: events with a materialization P — a scope boundary
    belongs in the goal's criteria, not here), carry the rest. RMW over revise. Each item:
    {item, predictability: ORDINARY|STATISTICAL|EXTRAORDINARY, justification, invalidation_condition} —
    the predictability verdict is mandatory per factor on a decomposed node (CHECK-4 record form)."""
    agent = agent or _agent_id()
    was = engine.get_task(TaskId(task_id))
    out = _task_out(engine.edit_accepted_risks(TaskId(task_id),
                                               _accepted_risks_from(accepted_risks), AgentId(agent)))
    if isinstance(out, dict):
        # THE REGISTER AS RECORDED, not just the item texts. The node projection carries each risk's
        # `item` alone, so a person who classified one as STATISTICAL with a justification and an
        # invalidation condition — the classification CHECK-4 demands — got back the sentence they
        # started from and no way to see whether the rest of it landed (walked by hand 2026-08-21).
        t = engine.get_task(TaskId(task_id))
        out["accepted_risks_recorded"] = [
            {"item": n.item, "predictability": n.predictability.name if n.predictability else None,
             "justification": n.justification, "invalidation_condition": n.invalidation_condition}
            for n in (t.spec.accepted_risks if t is not None else ())]
        out = _said_state_change(engine, task_id, was.state if was is not None else None, out)
    return out


def edit_criteria(engine: Engine, task_id: str, criteria: list[dict], agent: str = "",
                  reason: Optional[str] = None, accept_coverage_loss: bool = False,
                  expect_criteria: Optional[list] = None) -> Optional[dict]:
    """Replace a node's criteria, carry the rest. RMW over revise. (Dep criteria use `depends_on`.)
    `reason` (optional, §24.5): spec_defect = the criteria were WRONG (counts in q_T) |
    scope_expansion = sanctioned growth of the goal (§13.1; never counts) | other.

    A contract change is a REVISION (Inv-1, §14.4): the node re-enters at OFFERED so its executor
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
        crits = tuple(Criteria(c["name"], c.get("description", ""), depends_on=_dep_of(c))
                      for c in criteria)
    except (ValueError, KeyError, TypeError) as ex:
        return {"refused": True, "error": str(ex)}
    before = engine.get_task(TaskId(task_id))
    if (_moved := _contract_moved_under_you(before, expect_criteria)):
        return _moved
    was = before.state if before is not None else None
    _had = tuple((c.name, c.description) for c in before.spec.criteria) if before is not None else ()
    # …and the COVERAGE as it stands now, copied out. `before` is the live Task the engine mutates in
    # place, so reading its mappings after the call reads the post-edit state and reports no loss.
    _had_map = tuple((m.criterion_name, str(m.child_id))
                     for m in ((before.criterion_mappings or ()) if before is not None else ()))
    # …AND SAID BEFORE THE ACT, NOT AFTER IT. Everything the note below explains was already known
    # here — which mappings the new set drops, and which of their children are terminal — and it was
    # computed AFTERWARDS, so the reply told a caller their graph could never close again in the same
    # breath as doing it. One call, no confirmation, no way back: a stranger reworded one criterion on
    # a finished project and left it with a permanent CHECK-1 failure (MCP door, wave 23,
    # 2026-09-03), and the same shape was measured on two other doors a day earlier. A guard that
    # runs after the side effect it guards is not a guard — the fourth time that sentence has had to
    # be written into this codebase in two days.
    # The refusal is only for the IRREVERSIBLE half: while the mapped children are still open,
    # `map_criterion` puts the coverage back, and the note below is enough.
    _doomed = sorted({k for c, k in _had_map if c not in {n["name"] for n in criteria}
                      and (kid := engine.get_task(TaskId(k))) is not None
                      and kid.state.name in ("DONE", "ABANDONED", "ESCALATED")})
    if _doomed and not accept_coverage_loss:
        return {"refused": True, "would_destroy_coverage": _doomed,
                "error": (f"this call would drop the coverage of {', '.join(_doomed)}, and that "
                          f"cannot be undone: a finished node's contract cannot take a new `covers` "
                          f"(Inv-1), so re-adding the criterion will NOT restore the mapping and "
                          f"CHECK-1 fails on '{task_id}' from here on. Three ways forward, in order "
                          f"of how much they keep: name those criteria in this call as well (an "
                          f"omitted one is a removed one — `edit_criteria` REPLACES the set); "
                          f"re-decompose around the finished child (`auto_decompose('{task_id}')`), "
                          f"which is the canon's recovery from a consumed terminal; or, if the "
                          f"coverage is genuinely meant to go, repeat this call with "
                          f"`accept_coverage_loss=true`.")}
    out = _task_out(engine.edit_criteria(TaskId(task_id), crits, AgentId(agent),
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
    # …AND WHAT COVERAGE THIS CALL DESTROYED, which is the half that cannot be undone. A criterion the
    # new set does not name takes its mapping with it — correctly, the criterion is gone — but once
    # the mapped CHILD is terminal the mapping cannot be re-made at all (`map_criterion` refuses:
    # adding a `covers` is a revision of a finished contract, Inv-1). Measured on the MCP door
    # 2026-09-02: a caller replaced ten criteria with one, restored the ten verbatim, and was left
    # with a DONE/PASS root carrying a permanent CHECK-1 coverage failure and no way back. The reply
    # said what was newly uncovered and never that anything had been LOST.
    # Computed from the REQUEST, not from the graph afterwards: the pruning rides the revision's
    # ASSIGN through the event loop, so reading the node back inside this verb sees the mappings
    # still standing and reports no loss at all. What is decidable here and now is the definition —
    # a mapping whose criterion the new set does not name is a mapping that is going.
    _kept_names = {c["name"] for c in criteria}
    _going = [(c, k) for c, k in _had_map if c not in _kept_names]
    _after = engine.get_task(TaskId(task_id))
    if _after is not None and isinstance(out, dict):
        if _lost := sorted(f"{c} -> {k}" for c, k in _going):
            out["coverage_dropped"] = _lost
            _frozen = sorted({k for c, k in _going
                              if (kid := engine.get_task(TaskId(k))) is not None
                              and kid.state.name in ("DONE", "ABANDONED", "ESCALATED")})
            out["coverage_dropped_note"] = (
                f"{len(_lost)} criterion→child mapping(s) went with the criteria this call replaced. "
                + (f"IRREVERSIBLE: {', '.join(_frozen)} {'is' if len(_frozen) == 1 else 'are'} "
                   f"terminal, and a finished node's contract cannot take a new `covers` (Inv-1) — "
                   f"re-adding the criterion will NOT restore its coverage, and CHECK-1 will fail on "
                   f"this node from here on. Recovery is re-decomposition around the finished child."
                   if _frozen else
                   f"`map_criterion` can re-make them while the children are still open."))
        _covered = {m.criterion_name for m in (_after.criterion_mappings or ())}
        if _uncovered := [c.name for c in _after.spec.criteria
                          if c.name not in _covered and not c.depends_on]:
            if engine.get_active_children(TaskId(task_id)):
                out["still_uncovered"] = _uncovered
                out["still_uncovered_note"] = (
                    f"{len(_uncovered)} criterion(s) of this node are covered by no child now — "
                    f"replacing the set dangles the mappings it does not re-name. `map_criterion("
                    f"'{task_id}', <child>, '<criterion>')` binds each; until then CHECK-1 holds the "
                    f"plan and execution is not admitted.")
    if (_gone := [f"{n}: {d}" for n, d in _had if n not in _kept]) and isinstance(out, dict):
        out["removed"] = _gone
        out["removed_note"] = (f"{len(_gone)} criterion(s) are no longer in this contract. "
                               f"`edit_criteria` REPLACES the set — to put one back, include it in "
                               f"the next call; the previous versions stay in the log (Inv-7).")
    return _said_state_change(engine, task_id, was, out)


def _cycle_closed_by(engine: Engine, task_id: str) -> Optional[str]:
    """Did this BLOCK's discovered edge close a dependency cycle — and what that costs the plan.

    The edge is RECORDED even when it does (§14.2: the cycle IS the finding, the world's verdict on
    a declared seam running the other way). What was silent is the consequence: the parent's plan
    fails the Syntactic level, every sibling stops being admitted (§13.4), and the only surface that
    said so was the frontier — six children froze and were diagnosed by hand (human door,
    2026-08-22). The same shape had been refused minutes earlier when asked for by hand."""
    cyc = [h for h in engine.graph_holes()
           if h.get("check", "").startswith("CHECK-2") and task_id in str(h.get("details", ""))]
    if not cyc:
        return None
    return (f"this BLOCK recorded a dependency that closes a cycle: {cyc[0]['details']}. The edge "
            f"stands (the cycle is the finding — the world says a declared seam runs the other "
            f"way), and until it is resolved the plan fails the Syntactic level and NO child of "
            f"'{cyc[0]['task_id']}' is admitted to execution (§13.4). Drop whichever direction is "
            f"wrong (`remove_dependency`), then review the plan again.")


def _said_state_change(engine: Engine, task_id: str, was, out: Optional[dict]) -> Optional[dict]:
    """Name a state change the caller did not ask for, on the reply that caused it.

    A revision (Inv-1) sends the node back to OFFERED for its executor's consent, and an edit to a
    decomposition stales its Level-2 verdict (§13.4). Both are correct and both were silent, so the
    node simply appeared to have moved on its own."""
    if not isinstance(out, dict) or was is None or out.get("state") == was.name:
        return out
    out["state_changed"] = (
        f"{was.name} → {out.get('state')}: a contract change is a REVISION (Inv-1, §14.4), so the "
        f"node re-enters at OFFERED and its executor consents again — signal ACCEPT to put it back "
        f"to work; the subtree is retained.")
    if was.name in ("DONE", "ABANDONED"):
        # …AND WHAT IT COST, when the node was FINISHED. Editing the contract of a settled node is a
        # reopen with a new contract (R′, §14.3): it spends a reopen and its verdict is GONE, to be
        # re-earned by fresh contact. Measured on the human door 2026-08-21 — a passed child was
        # dropped back to OFFERED by an edit, and the recovery cost a plan review, seven disputes, a
        # re-delivery and two validations. `reopen` says this; the edit that does the same did not.
        out["state_changed"] += (
            f" This node was {was.name}: editing a settled contract is a REOPEN with a new one, so "
            f"its verdict is GONE (§14.3 — re-earned by fresh contact, never carried forward) and a "
            f"reopen is spent.")
    if engine.get_active_children(TaskId(task_id)):
        out["state_changed"] += (" The edit also STALES the plan's Level-2 verdict — "
                                 f"review_decomposition('{task_id}') before its children can start "
                                 "(§13.4).")
    return out


def reassign(engine: Engine, task_id: str, assignee: str,
             reason: Optional[str] = None) -> Optional[dict]:
    """Change a node's executor (Del). Canon Inv-1 fixes Del at ASSIGN → a change = revision: re-ASSIGN
    (same id) carrying the new executor (the issuer acts; the subtree is retained — no cascade).
    `reason` (optional, §24.5): capability_mismatch = the executor could not do the work (counts in
    q_Del) | other (load/handoff; does not count). Untyped counts — omit only when genuinely unknown.
    DELEGATING work to a registered executor is `other`: nobody failed at anything, and typing it as
    a capability mismatch would charge q_Del for an ordinary hand-off (measured 2026-08-21 — a caller
    reached for the nearest-looking value and stopped to reason it out)."""
    was = str(engine.get_task(TaskId(task_id)).assignee or "") if engine.get_task(TaskId(task_id)) else ""
    out = _task_out(engine.reassign(TaskId(task_id), AgentId(assignee),
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
    """Why the R′ edge is closed on this node — or None when it is open (§14.3).

    Asked by `reopen`, which refuses in these words, and by the affordance surface, which must not
    OFFER the ASSIGN that carries a reopen while the gate is shut. The FSM refuses it either way, in
    the generic words of a guard ("the precondition does not hold"), which is what this exists to
    replace.""" 
    if t.state.name not in ("DONE", "ABANDONED"):
        return {"error": f"{t.id} is {t.state.name} — reopen is for a node that FINISHED "
                         f"(DONE or ABANDONED). A node still in play is moved by its own signals, "
                         f"and its contract by `revise`.",
                "state": t.state.name}
    if engine.graph.is_consumed(t):
        return {"error": f"{t.id} is CONSUMED — the graph has built on this result (its parent "
                         f"staked its aggregate on it, or a Dep-consumer took it as input), so the "
                         f"terminal is finally locked (§14.3). Recovery is RE-DECOMPOSITION around "
                         f"it by the issuer — auto_decompose on the parent — never a reopen.",
                "consumed": True}
    if t.reopens >= t.max_reopens:
        return {"error": f"{t.id} has spent its reopens ({t.reopens}/{t.max_reopens}) — the "
                         f"counter is what makes the reopened node finite (Inv-5). Re-decompose "
                         f"around it, or re-author it as a new node.",
                "reopens": t.reopens, "max_reopens": t.max_reopens}
    return None


def reopen(engine: Engine, task_id: str, agent: str) -> Optional[dict]:
    """Reopen a DONE/ABANDONED node back to OFFERED under its standing contract (R′, §14.3) — the verdict
    is RE-EARNED by fresh contact, never resurrected. Double-gated by the engine: the node must not be
    CONSUMED (parent staked its aggregate on it / a Dep-consumer built on it / a cancelled node's hole
    was replanned around) and reopens must remain (max_reopens, default 1). A consumed terminal is
    finally locked — recover by re-decomposition, not reopen. `agent` must be the issuer."""
    t = engine.get_task(TaskId(task_id))
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
    out = _task_out(engine.reopen(TaskId(task_id), AgentId(agent)), engine) or {}
    # SAY WHAT WAS DESTROYED. R′ drops the verdict by design — it is re-earned by fresh contact —
    # but the reply was an undifferentiated task dump, and a person who ran this to SEE whether it
    # would be refused found their finished root back in OFFERED, one reopen spent, with nothing in
    # the answer saying so. Measured 2026-08-20: it cost the run a re-accept, a re-delivery and a
    # paid re-validation to get back where it had been.
    out["reopened"] = (f"{task_id} was {was[0]}"
                       + (f"/{was[1]}" if was[1] else "")
                       + f" and is now OFFERED — that verdict is GONE (§14.3: a reopened node "
                         f"re-earns it by fresh contact, it is never carried forward). Reopens "
                         f"spent: {t.reopens}/{t.max_reopens}. The node must be ACCEPTed, worked and "
                         f"validated again.")
    return out


def add_dependency(engine: Engine, from_id: str, to_id: str, glue: str = "") -> dict:
    """Declare `to_id depends on from_id`'s output — **`from_id` is the PRODUCER, `to_id` the
    CONSUMER**, and the arrow runs producer → consumer: `to_id` is the one that waits.

    Dep is criteria-content (§10): desugars to a re-author of the CONSUMER adding the glue
    criterion; the edge is derived. Cycle → rejected. `glue` is the anti-mock truth-maker — what
    the consumer must do with the real output, not "depends on it".

    The direction is worth one sentence because getting it backwards is silent: a person wrote the
    glue "render imports and calls the scan() function delivered by scan", passed them the other way
    round, and made SCAN wait on RENDER — the reply said `ok`, the Level-2 review passed the graph,
    and only `next_steps` (`waits_on`) showed it. So the answer says which way it went."""
    engine.add_dependency(TaskId(from_id), TaskId(to_id), glue=glue)
    return {"ok": True, "from": from_id, "to": to_id,
            "declared": f"'{to_id}' now WAITS for '{from_id}' to pass — '{from_id}' produces, "
                        f"'{to_id}' consumes. If that is backwards, `remove_dependency` and swap."}


def remove_dependency(engine: Engine, from_id: str, to_id: str) -> dict:
    """Drop a dependency (re-authors the consumer to remove the glue criterion).

    Removing an edge REWRITES the consumer's contract (the glue criterion goes with it), which is a
    revision — so it stales the plan's Level-2 verdict and the children stop being admitted to
    execution until the check runs again (§13.4). Both are canon and both were silent: the answer
    was `{"ok": true}` and the graph then simply did not move (measured on the human door
    2026-08-22)."""
    engine.remove_dependency(TaskId(from_id), TaskId(to_id))
    out = {"ok": True, "removed": f"{from_id} -> {to_id}"}
    _parent = engine.get_parent(TaskId(to_id))
    if _parent is not None and not _parent.verified:
        out["plan_verdict_staled"] = (
            f"this re-authored '{to_id}', which is a revision — the Level-2 verdict on "
            f"'{_parent.id}'s plan no longer covers it, so its children are not admitted to "
            f"execution until `review_decomposition('{_parent.id}')` runs again (§13.4).")
    return out


def map_criterion(engine: Engine, parent_id: str, child_id: str, criterion_name: str) -> Optional[dict]:
    """Bind an EXISTING child to a parent criterion (add/repair the coverage mapping). Use this when a child
    covers a parent criterion but wasn't mapped at decompose time, or when a re-authored parent criterion left
    a child's mapping dangling (CHECK-1). `decompose` maps only NEW children — this is the post-hoc verb.

    Answers with the BINDING it made and what is still uncovered: echoing the whole parent made eleven
    successive calls indistinguishable from eleven no-ops (measured on the human door 2026-08-21)."""
    # A COVERAGE REPAIR IS A REVISION OF THE CHILD (§14.4 Inv-1: `covers` is contract content), so it
    # sends that child back to OFFERED for consent. On a child that is mid-flight this DESTROYS work:
    # measured on the human door 2026-08-21, a node in VALIDATING with a validator running was
    # re-opened by a mapping call, and the delivery and the validation were both lost, with nothing
    # in the reply saying a state had changed. What is delivered or judged is not re-opened silently.
    _child = engine.get_task(TaskId(child_id))
    if _child is not None and _child.state.name in ("VALIDATING", "DONE"):
        return {"error": f"cannot map '{criterion_name}' to {child_id} right now: it is "
                         f"{_child.state.name}, and adding a `covers` is a REVISION of its contract "
                         f"(Inv-1, §14.4) — it would drop back to OFFERED and its delivery"
                         + (" and the validation running on it" if _child.state.name == "VALIDATING"
                            else " and its verdict")
                         + f" would be thrown away. Map the criterion to another child, or wait for "
                           f"this one to settle and then `revise` it deliberately.",
                 "refused": True, "child_state": _child.state.name}
    _was = _child.state if _child is not None else None
    parent = engine.map_criterion(TaskId(parent_id), TaskId(child_id), criterion_name)
    _after = engine.get_task(TaskId(child_id))
    _now = _after.state if _after is not None else _was
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
            **({"child_state_changed":
                f"{_was.name} → {_now.name}: `covers` is contract content, so binding it REVISES the "
                f"child (Inv-1, §14.4) and its executor consents again — signal ACCEPT to put it "
                f"back to work."} if _was is not None and _now != _was else {}),
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
        # §14.2: the timeout "is not a P2P signal (no agent sends it) but a system mechanism enforcing
        # finiteness". Sent from here it settled a node in VALIDATING to DONE(auto_pass) — walking
        # around the AND gate (Thm 1), verifier ≠ executor (§14.5) and Inv-3 in one call, because
        # validation returns early for Role.SYSTEM. The door is where the alphabet is closed; the
        # engine refuses a sourced system signal on its own (gfso/engine/validation.py).
        raise ValueError(
            f"{sig.name} is not a P2P signal — no agent sends it (§14.2); it is the system's "
            f"finiteness trigger (Inv-5), emitted by the deadline monitor alone. Send one of: "
            f"{', '.join(s.name for s in P2P_SIGNALS)}")
    return sig


def signal(engine: Engine, task_id: str, signal: str, source: str,
           self_validation: Optional[str] = None,
           reason: Optional[str] = None, result: Optional[str] = None,
           justification: Optional[str] = None, action: Optional[str] = None,
           in_flight: Optional[str] = None, blocker_task_id: Optional[str] = None,
           blocker_task_ids: Optional[list] = None,
           external: bool = False, failed_criteria: Optional[list] = None) -> dict:
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
    provisionals retract), or retracts all (`external=true` — no producer node).

    The alphabet here is the TWELVE P2P signals and nothing else: `TIMEOUT` is the system's finiteness
    trigger (Inv-5), "not a P2P signal (no agent sends it)" — §14.2 — so this door refuses it by name."""
    sig = _p2p_signal(signal)
    entry = engine.send_signal_sync(SignalData(
        signal=sig, task_id=TaskId(task_id), source=AgentId(source),
        reason=reason, result=result,
        # DELIVER's own field (§14.2). It is what an INTERNAL node's completion rests on — §14.5 D6:
        # such a node self-verifies, its DELIVER carries the self-check, and the guarantee is carried
        # by the validation of the public result above it. The packet had the field, the schema asked
        # for it, and no door let a caller fill it in.
        self_validation=_self_check_verdict(self_validation),
        justification=justification, action=action,
        in_flight=in_flight,
        blocker_task_id=TaskId(blocker_task_id) if blocker_task_id else None,
        blocker_task_ids=tuple(TaskId(b) for b in (blocker_task_ids or []) if b),
        external=bool(external),
        failed_criteria=tuple(failed_criteria or ())))
    st = engine.get_state(TaskId(task_id))
    ok = bool(entry and not entry.rejected)
    out = {"accepted": ok, "state": st.name if st else None}
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
        out["plan_now_red"] = _red
    # …AND WHAT AN ACCEPTED NODE IS STILL WAITING FOR. §14.3 admits ACCEPT from OFFERED whatever the
    # seams say, and the engine is not narrower than the canon — but the reply said nothing, so a
    # graph showed EXECUTING for nodes that provably could not start, and their executor found out by
    # hitting a missing input and BLOCKing (CLI and HTTP doors, 2026-09-02). Taking it is fine;
    # starting it is what waits.
    # …AND WHAT A PASS ON A LEAF FREEZES. Once a parent stakes its aggregate on a child, that child
    # is CONSUMED and cannot be reopened (§14.3 finality) — so a defect later found in the code that
    # leaf's contract owns has to be repaired by re-decomposing AROUND it. That is the right rule and
    # it was learnt at the wrong moment: a tester met it only when the root's validator refuted the
    # shared function, four round trips after the leaf had passed (CLI door, 2026-09-02). Said at the
    # PASS, it is a fact someone can plan around; said at the reopen, it is only a wall.
    if sig == Signal.PASS and st is not None and st.name == "DONE":
        _t = engine.get_task(TaskId(task_id))
        if _t is not None and _t.parent_id and not engine.get_active_children(TaskId(task_id)):
            out["frozen_now"] = (
                f"this leaf has passed, so the concern its criteria own is settled for the rest of "
                f"the run: once '{_t.parent_id}' stakes its aggregate on it the node is CONSUMED and "
                f"cannot be reopened (§14.3). A defect found later in the code this contract covers "
                f"is repaired by re-decomposing around it, not by re-working this node.")
    if sig == Signal.ACCEPT and (_open := engine.unmet_producers(TaskId(task_id))):
        out["cannot_start_yet"] = _open
        out["cannot_start_note"] = (
            f"taken — but it consumes {', '.join(_open)}, and they have not passed (§10: a Dep is "
            f"criteria content). Starting now hits a missing input and ends in BLOCK; the dispatcher "
            f"holds spawns until they pass. `next_steps` lists this node under `waiting`.")
    if st is not None and st.name == "VALIDATING":
        # WHAT HAPPENS TO THE DELIVERY NOW, said to the one who just made it. A DELIVER answered with
        # a directive about some OTHER node (the frontier's next move, correctly), and the executor
        # was left not knowing whether a verdict was coming or whether it had to ask for one — one
        # tester waited, another called `validate_result` on a node an instrument was already
        # holding, paying twice for the same artifact (measured on the human door 2026-08-22).
        out["awaiting_verdict"] = (
            "an INDEPENDENT validation of this delivery is already running — its verdict arrives by "
            "itself; do not start a second one"
            if engine.validation_in_flight(TaskId(task_id)) else
            "a verdict is on the record for this delivery — `get_verdict` reads it; the signal is the "
            "issuer's to give"
            if engine.current_exec_verdict(TaskId(task_id)) is not None else
            f"this node now waits for a verdict from its issuer; you cannot sign your own (§14.5). "
            f"`validate_result {task_id}` runs an independent judge on it."
            if engine.is_seam(engine.get_task(TaskId(task_id))) else
            # …AND THE OPPOSITE IS TRUE ON AN INTERNAL NODE, where three surfaces said three things.
            # §14.5 D6: a node whose Del is its parent's SELF-verifies, and the reply that told its
            # executor "you cannot sign your own" was contradicted in the same object by the `next`
            # line telling them to signal PASS, and by `available_actions`, which alone was right
            # (agent door, 2026-09-02). The rule is about the SEAM, so the sentence has to be too.
            # …AND ONLY WHEN NOBODY IS ABOUT TO JUDGE IT FOR YOU. This sentence was added earlier
            # today and immediately sent a user down a path the dispatcher had already closed: an
            # instrument was bound to the node, took it to DONE while they were writing their own
            # observations, and eight calls came back refused (CLI door, 2026-09-02). Which of the
            # two is happening is not visible from outside — so the reply has to say which one it is.
            # …AND WHICH JUDGE IT IS, AND WHERE IT STANDS. The roster is one server-wide fact, so
            # "an independent validator" can be a role somebody else registered for another project,
            # working in a directory that holds none of this delivery — which then fails twice per
            # node and blocks it. FIVE testers across three waves reported the same thing, and every
            # one of them had to go read `gfso log` to find out: the sentence that announced the
            # judge did not name it (waves 23–25). Naming it is not the isolation fix — the roster is
            # server-wide by design — it is the difference between a wait you can diagnose and one
            # you cannot.
            f"an independent validator is bound to this node and judges this delivery by itself — "
            + _bound_judge_note(engine, task_id)
            + f"wait for it (`get_verdict {task_id}` reads the result; `gfso log` shows it running). "
            f"Recording your own verdict here would race it."
            if engine.judged_by_instrument(TaskId(task_id)) else
            f"this node is INTERNAL (its Del is its parent's), so §14.5 D6 lets it self-verify: put "
            f"what you checked on the record — `record_verdict {task_id} PASS observed={{...}}` — "
            f"and then signal. A DELIVER carrying `self_validation` records it for you.")
    # Carry the NEXT directive back in the signal's own response. Agents drive by sending signals,
    # not by polling next_steps between them (observed live: ACCEPT → write code → DELIVER with no
    # frontier call in between — so a directive that only lives in next_steps never reaches them).
    # Returning it here puts the next step — e.g. "before DELIVER, self-check by running" — at the
    # one point the agent always reads: the reply to what it just did. (Enforcement of discipline
    # rides where the agent LOOKS, not where we hope it polls.)
    try:
        # …ASKED OF THE WHOLE GRAPH, not of the node just signalled. Scoped to that node,
        # `next_step` answers about ITS subtree — so a leaf reaching DONE came back "COMPLETE —
        # root 'x.core' is DONE/PASS. Execution finished." while four sibling nodes were still
        # open, on every child in the run. A reader who trusted the reply instead of re-reading
        # the graph ships a half-built package (measured on the agent door 2026-08-21, and it is
        # the one message in this product that could cause that).
        nxt = engine.next_step()
        if nxt.get("complete"):
            out["next"] = nxt.get("directive") or "the graph is complete."
        elif nxt.get("directive"):
            # SAY WHICH NODE IT IS ABOUT. The step that follows a signal is often on a DIFFERENT
            # node — the one just signalled may be waiting on a producer, or done — and the bare
            # directive read as a statement about the node the caller had in hand. Measured:
            # accepting one leaf answered with an instruction about another, which reads as a
            # defect even when it is the honest next move.
            other = nxt.get("task_id") and str(nxt["task_id"]) != str(task_id)
            # …THROUGH THE SAME OWNERSHIP FILTER THE FRONTIER USES. The reply carried the raw
            # directive, so a signal on one node answered "EXECUTE leaf 'X': do the actual work"
            # about a node whose Del is somebody else's registered executor — while `next_steps`
            # on that same node said "NOT YOURS (Del=…) — do NOT execute or signal for it". One
            # tester nearly redid a running executor's work on it (measured on the MCP door
            # 2026-08-21). Del is load-bearing in every surface that speaks about a node, or in
            # none.
            nxt = _mark_mine(engine, dict(nxt), me=source)
            out["next"] = ((f"next on the frontier is '{nxt['task_id']}', not {task_id}: "
                            if other else "") + nxt["directive"])
            if not nxt.get("mine", True):
                out["next_is_mine"] = False
    # the signal is already accepted and recorded; a failure to compute the NEXT step must not
    # come back as a refusal of the one that landed — an agent reading that re-sends a signal it
    # already sent
    except Exception:
        pass


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


def _bound_judge_note(engine: Engine, task_id: str) -> str:
    """Who the bound instrument IS, and where it works — said where the binding is announced.

    Read off what the DISPATCHER published for this node, never composed here. The first spelling of
    this asked the registry directly and the layer gate refused it in the same words its neighbour
    `judged_by_instrument` already carries: a door that composes this for itself reaches into the
    delegation layer. The gate was right, and the fact was already being computed one layer down.

    Empty when there is nothing surprising to say. What is surprising, and what five strangers across
    three waves had to dig out of `gfso log`: the roster is server-wide, so the judge can belong to
    another project and stand in a directory holding none of this work.
    """
    who = (engine.bound_judge(TaskId(task_id)) or {})
    if not who.get("id"):
        return ""
    _mine = who.get("project") == engine.project_name
    _whose = ("registered for THIS project" if _mine
              else f"registered for project '{who['project']}'" if who.get("project")
              else "registered for NO project — the roster is shared by every project of this server")
    return (f"it is '{who['id']}', {_whose}, and it judges in `{who.get('workdir') or '?'}`. "
            + ("" if _mine else
               "If that directory does not hold this delivery, its report will be about the wrong "
               "tree: register your own (`register_agent(<id>, \"llm-validator\", workdir=…)`). "))


def _mark_mine(engine: Engine, out: dict, me: Optional[str] = None) -> dict:
    """Del is LOAD-BEARING on the frontier, not a label: every step carries `mine` (the calling agent is
    the node's executor), and a FOREIGN executor-step's directive is rewritten to hands-off — the FSM
    would reject your executor signals on it anyway (source ≠ Del is a validation error). Foreign steps
    stay VISIBLE (that is the point: you see what the graph waits on).

    VALIDATION IS THE ISSUER'S, NOT THE EXECUTOR'S (§14.1: the issuer forms the task and validates the
    result). SO IS RESOLVE_BLOCK (§14.3 role table): the frontier offered `resolve` to the BLOCKED
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
        if s.get("action") in (Action.VALIDATE, Action.RESOLVE):
            # …THE ENGINE'S RULE, ASKED (`issuer_of`), not a second reading of it. This one read the
            # PARENT alone, so a root — which has none — came back `mine: true` to whoever asked,
            # and the gate then refused their signal because a root's issuer is its own assignee.
            issuer = engine.issuer_of(TaskId(s["task_id"])) if s.get("task_id") else None
            s["mine"] = (issuer == me) or not issuer
            continue
        s["mine"] = (a == me) or not a
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
            # THIS engine's roster, published downward by the dispatcher (`engine._roster`) —
            # never imported from it: this module is the layer below, and `test_layering` holds it.
            _kind = engine.kind_of(a)
            _who = ("a registered " + _kind + " — the dispatcher starts it by itself, so this node "
                    "is in hand, not stuck" if _kind else
                    "a human via the UI, or an external system by its own signals")
            s["directive"] = (f"NOT YOURS (Del={a}) — do NOT execute or signal for it; the graph WAITS "
                              f"for that executor ({_who}). Work your `mine` steps; surface this one "
                              f"to the user if the wait blocks you. | contract was: "
                              + s.get("directive", ""))
    return out


#: Words that RESTATE the verdict instead of recording an observation. A PASS already says "pass";
#: an observation whose whole content is another way of saying so has recorded nothing, and §11.2's
#: rule that a verdict with no check behind it is ⊥ does not stop applying because the ⊥ arrived
#: wearing a mapping. Both stranger doors closed a root this way on the same afternoon
#: (2026-09-02) — `"ok"`, `"looks green"`, `"dave says it works"` — and both testers named this,
#: rather than the identity of the reviewer, as the step the product stops one short of.
#:
#: Deliberately NARROW. This is not authentication and cannot be: at a loopback door a person names
#: themselves, and anyone determined to lie can write a sentence. What it refuses is the case where
#: nothing was written down at all, and it makes the deliberate case require a deliberate lie that
#: the record then carries — which is the guarantee §14.5 says the human door actually has.
# The floor on "this text records nothing" lives in the protocol layer, because the ENGINE
# needs it too: a DELIVER self-check is a verdict record (§14.5 D6), and it was accepted at
# any thinness while THIS door refused the same words from a reviewer (wave 26, 2026-09-06).
# Aliased rather than reimplemented — a second spelling of one rule is how the two came apart.
_PURE_ASSENT = PURE_ASSENT
_is_pure_assent = is_pure_assent


def record_verdict(engine: Engine, task_id: str, verdict: str,
                   failed_criteria: Optional[list] = None, reviewer: str = "human",
                   observed: Optional[dict] = None) -> dict:
    """Record an INDEPENDENT reviewer's verdict on the node's CURRENT delivery — the human
    counterpart of validate_result (no LLM run): it is what unlocks a self-executed node's PASS
    through the verifier≠executor gate. Per-delivery: a rework stales it. The engine REFUSES a
    reviewer who IS the node's executor (recording a verdict on your own work is the self-stamp
    this system exists to catch); FAIL requires failed_criteria (Inv-3). After recording, the
    issuer still sends PASS / FAIL themselves — this is the evidence record, not the signal.
    On an INTERNAL node (its Del is its parent's) the refusal does NOT apply: §14.5 D6 has such a
    node self-verify, and your own observations ARE the record the canon asks for. Observations that
    name no criterion of the node are kept out of the verdict and named back to you, not refused."""
    # SAY WHAT YOU OBSERVED — the same demand the machine door makes, at the grade a person can meet.
    # A validator's report is refused unless every criterion carries a re-runnable probe ("judgment
    # with no re-runnable observation is not evidence"); this door asked for nothing at all, and a
    # PASS with an empty per-criterion list closed a root while every metric read 1.0. Measured
    # 2026-08-20: `reviewer=STAND-IN-not-a-real-reviewer` was accepted without a word of evidence.
    # A person is not asked for commands — they are asked for a SENTENCE per criterion saying what
    # they checked. That is exactly the canon's remaining guarantee where no seam exists (§14.5's
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
    _t = engine.get_task(TaskId(task_id))
    # A NODE WITH NO CRITERIA CANNOT BE JUDGED. V(t) is the conjunction over the node's criteria
    # (§10), and the conjunction over an empty set is vacuously TRUE — so the strongest guard in the
    # product, one observation per criterion, switches itself off when there is nothing to observe.
    # Measured on the HTTP door 2026-09-02: `create_task` with `criteria: []`, then `observed={}`
    # (the exact value refused a minute earlier on a node that had criteria), then PASS. Four
    # seconds from nothing to a green root called "Everything is done".
    # …AND NOT WHILE AN INSTRUMENT IS MID-JUDGEMENT. The DELIVER reply already tells the caller that
    # "recording your own verdict here would race it" — and nothing was behind that sentence, so the
    # race ran: a hand stamp closed a node 35 seconds before the instrument reported, the instrument's
    # signal was then refused for arriving at a terminal node, and its record landed on top of the
    # one that had done the closing (CLI door, 2026-09-02). Advice with nothing behind it is not a
    # rule; the claim it needs already exists, and this asks it without taking it.
    if _t is not None and engine.validation_in_flight(TaskId(task_id)):
        return {"recorded": False,
                "error": f"an instrument is judging {task_id} right now — recording a verdict here "
                         f"would race it, and the loser of that race is whichever arrives second: "
                         f"a verdict landing on a node the other one already closed is refused as a "
                         f"signal and kept only as evidence. Wait for it (`get_verdict {task_id}` "
                         f"shows it when it lands), or judge a different node meanwhile.",
                "validation_in_flight": True}
    if _t is not None and not _t.spec.criteria:
        return {"recorded": False,
                "error": f"{task_id} has no criteria — there is nothing a verdict could be ABOUT. "
                         f"V is the conjunction over a node's criteria (§10), and over an empty set "
                         f"that is vacuously true, which is not a judgement. Give it criteria "
                         f"(`edit_criteria`) and judge those.",
                "criteria": []}
    if verdict == Verdict.PASS and _t is not None:
        _need = [c.name for c in _t.spec.criteria if not c.depends_on]
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
                             f"(§14.5: with no independent seam, the explicit record IS the guarantee)."
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
                     f"person's word, not an instrument's judgement.")
    # …AND WHAT THIS RECORD JUST DISPLACED. An INSTRUMENT had judged this same delivery and said the
    # opposite; a hand verdict replaced it and the reply answered `recorded: true` with a helpful
    # next step, saying nothing. Measured on the HTTP door (wave 26, 2026-09-06): `validate_result`
    # returned FAIL with a re-runnable probe (`test -f … || echo FILE_ABSENT` printed FILE_ABSENT),
    # a PASS typed under an invented reviewer name replaced it, and the node closed COMPLETE with
    # `q_V: 1.0`. Overruling an instrument is LEGITIMATE — the verdict is the issuer's act (§14.5),
    # and §13.6 says no check can establish that a self-named reviewer is independent — so this
    # refuses nothing. What it does is say it at the moment of the act, to the party doing it, in
    # the reply they are already reading. The engine has carried the displaced verdict all along
    # (`overruled_verdict`); it simply never reached here.
    _displaced = engine.overruled_verdict(TaskId(task_id))
    return {"recorded": True, "task_id": task_id, "verdict": verdict, "reviewer": reviewer,
            "state": _t.state.name if _t is not None else None,
            **({"overruled": _displaced,
                "overruled_note":
                    (f"this record REPLACED an instrument's {_displaced.get('verdict')} on the same "
                     f"delivery. That is yours to do (§14.5 keeps the verdict the issuer's act), and "
                     f"it is the one fact about this node a later reader has to weigh: an instrument "
                     f"ran the criteria and disagreed with you. Both are kept — `get_verdict "
                     f"{task_id}` shows the displaced one beside yours.")} if _displaced else {}),
            **({"kept_out_of_the_record": sorted(_extra),
                "kept_out_note": (f"{len(_extra)} observation(s) name no criterion of this node, so they "
                                  f"are not part of the verdict (§10: the criteria ARE the "
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
    "revise": revise, "edit_accepted_risks": edit_accepted_risks, "edit_criteria": edit_criteria, "reassign": reassign,
    "reopen": reopen,
    "add_dependency": add_dependency, "remove_dependency": remove_dependency, "map_criterion": map_criterion,
    "signal": signal, "record_verdict": record_verdict,
    "next_step": next_step, "next_steps": next_steps,
}
