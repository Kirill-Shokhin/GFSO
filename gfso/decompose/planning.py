"""Planning with no project: the plan authored, reviewed and refined as its own artifact (`artifact`), before anyone has
agreed to execute it.

The theory separates the plan from its execution: the plane {T, D, Dep, V} references no agent (§2.8), and a split may
be drafted and the battery run over the draft before any issue (§11.5). So the authoring runs on a graph of its own
in memory — built through the same FSM a project's would be, reviewed by the same Level-2 check — and leaves nothing
behind but the file. The customer reads it whole and either sends a note (a refine whose answer is what changed in
the plan, stated mechanically, and the review run again) or gives the go: a project built from the file as it stands.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import gfso.decompose as _decompose
from gfso.adapters.agents.human import HumanAgent
from gfso.adapters.storage.memory import MemoryStorage
from gfso.config import ROOT_ID, agent_id, data_dir
from gfso.core.types import Stage, TaskId
from gfso.critic import runner
from gfso.decompose import artifact
from gfso.decompose.build import build_graph_live
from gfso.decompose.extract import extract_spec
from gfso.engine import Engine
from gfso.llm import llm_factory

_REVIEW_KEYS = ("gate_passed", "l0l1_failures", "semantic_covered", "semantic_findings", "criteria_verdicts",
                "conflicts", "undecided_obligations")
#: the review's key for what the plan's pins did over the base before the go (`PinsOnTheBase.review`)
PINS = "pins_on_the_base"
#: the review's key for the criteria the request does not ask (`decompose.beyond_the_request`)
BEYOND = "beyond_the_request"


def author(request: str, model: str, executor: str = "", depth: int = 1, review_model: str = "",
           progress=None, execution=None, ledger=None) -> str:
    """A plan file for `request`: authored by `model`, its fit judged against `executor`'s session, reviewed. The file
    holds the plan as BUILT (`extract_spec`), the shape a refine and the go read back, its pins run over the base where
    the checks run (`PinsOnTheBase`) — those that cannot run on any work repaired, what stays said in its review."""
    e, llm, back = _scratch(), _decompose.default_llm(model, execution=execution), _TakenBack(progress)
    pins = _decompose.PinsOnTheBase(execution)
    with _booked(ledger, llm):
        res = _decompose.decompose_into(e, request, root_id=ROOT_ID, assignee=agent_id(), depth=depth, model=model,
                                        llm=llm, progress=back, executor=executor, pins=pins)
    spec = _asked_kept(extract_spec(e, str(res.root_id)), res.spec)
    return artifact.render(request, spec, back.into(_review(e, res.root_id, review_model or model, execution, ledger,
                                                            beyond=beyond_said(spec, request),
                                                            pins=pins.review(spec)), spec), executor=executor)


def refine(text: str, note: str, model: str, review_model: str = "", progress=None, execution=None, ledger=None) -> str:
    """The plan file after the customer's `note`: one refine round over it with the note as its finding, the answer
    being what the round changed (or that it changed nothing), the review run again over the result."""
    p = artifact.parse(text)
    # …ONE keeper for every authoring call of the round: the note's own round got the raw callback, and what it took back
    # never reached the file (critic over 1cfd354)
    e, llm, back = _scratch(), _decompose.default_llm(model, execution=execution), _TakenBack(progress)
    pins = _decompose.PinsOnTheBase(execution)
    # …a file the admission refuses is this round's to repair, never a dead end: the go's refusal sends the customer
    # here, and the round itself built the file first and died on the same refusal (V3_cc2, 2026-11-01)
    with _booked(ledger, llm):
        spec = _decompose.repaired_before_build(p["spec"], p["goal"], llm, p["executor"], back, e, ROOT_ID, pins)
    _, rid, _ = build_graph_live(spec, p["goal"], e, root_id=ROOT_ID, assignee=agent_id())
    before = p["spec"]                          # the plan as the customer has it — what the answer says changed
    # …the review's verdicts on the root criteria too: handed only the goal's undecided obligations, the round never
    # learnt which criterion its children leave unsecured, and answered each note with more root criteria the next
    # review marked insufficient, the children's criteria as they were (regex, haiku, 2026-11-13)
    gaps = {v["criterion"]: v for v in p["review"].get("criteria_verdicts") or ()
            if v.get("verdict") in ("insufficient", "uncertain")}
    split = [f"[{v['verdict']}] {c} — {v.get('why', '')}" for c, v in gaps.items()]
    open_ = [f"[undecided] {g.get('obligation')} — admits: {g.get('admits')}"
             for g in p["review"].get("undecided_obligations") or ()]
    # …AND WHAT THE NOTES REQUIRE, read as obligations by the gate's own question: handed only the note's prose, a round
    # carried seven of the eight operations it named, and no review read the eighth (`sub`): the reviews read the goal
    # alone, the AUTO run delivered an engine without it (FM-1.f, regex, haiku, 2026-11-13). Every note, since a later
    # round may drop what carried an earlier one's.
    with _booked(ledger, llm):
        noted = "\n\n".join(f"Note {i}: {n}" for i, n in enumerate(
            (n for n in [*(n.get("note", "") for n in p["notes"]), note] if n.strip()), 1))
        # …blank notes read nothing: with none, the goal-only reading ran and the goal's duties were said the note's
        asked = runner.goal_obligations(llm, p["goal"], notes=noted) if noted else []
    findings = "# THE CUSTOMER'S NOTE ON THIS PLAN\n" + note.strip() + (
        "\n\n# WHAT THE CUSTOMER'S NOTES REQUIRE (a criterion with a pinned check probing it carries each)\n"
        + "\n".join(f"- {g.get('obligation')} — breaks if: {g.get('admits')}" for g in asked) if asked else "") + (
        f"\n\n# ROOT CRITERIA THE PARTS DO NOT SECURE (the plan's review)\n{_decompose.SPLIT_DEFECT}\n"
        + "\n".join(split) if split else "") + (
        "\n\n# OBLIGATIONS OF THE GOAL NO PINNED CHECK DECIDES (the plan's review)\nA pinned check closes each: on "
        "the criterion that already states the clause — the root's, or that of the part that builds it; a new root "
        "criterion only where none states it.\n" + "\n".join(open_) if open_ else "")
    with _booked(ledger, llm):
        changed, made, problems = _decompose.refine_with(e, p["goal"], rid, agent_id(), llm,
                                                      findings, progress=back, executor=p["executor"], pins=pins)
    changed = changed or spec != p["spec"]        # …the repair before the build changed it too
    after = _asked_kept(_exact_kept(before, extract_spec(e, str(rid))), made, before)
    pinned = pins.review(after)
    # …said as what it is: one round read the note TOGETHER with the review's open findings, so a change is the round's,
    # not proven the note's; and an unchanged plan is the system's answer to the note, the review below its reasons
    head = ("what the round that read this note (with the review's open findings) changed:" if changed else
            "the plan is unchanged: the round that read this note folded nothing into it — the plan as it stands, "
            "and the review below, are the answer; send a sharper note, or name a stronger model")
    answer = [head] + (changes(before, after) if changed else [])
    review = _review(e, rid, review_model or model, execution, ledger, asked, pinned,
                     beyond_said(after, p["goal"] + "\n\n" + noted))
    if left := unrepaired(before, after, [c for c, v in gaps.items() if v["verdict"] == "insufficient"]):
        wider = [c["name"] for c in after.get("root_criteria") or () if c["name"] not in _crits(_parts(before)[ROOT_ID])]
        answer.append(f"NOT REPAIRED — the review found the parts do not secure {', '.join(left)}, and the round "
                      "changed no criterion of a part mapped to it" + (f" (it added root criteria {', '.join(wider)})"
                                                                       if wider else "")
                      + ": the split's defect is repaired at the parts, by criteria with pinned checks mapped to it")
    if left := still_open(note, before, after, review) + [
            f"[uncarried] {g.get('obligation')} — {g.get('admits')}"[:300] for g in review.get("undecided_obligations") or ()
            if g.get("of") == "note"]:
        answer.append("NOT ANSWERED — the review still finds open what this note is about: " + "; ".join(left)
                      + ". The note is not spent: refine again with it (a sharper wording, or a stronger `model`)")
    notes = p["notes"] + [{"note": note, "by": model, "answer": "\n".join(answer + [f"open: {x}" for x in problems])}]
    return artifact.render(p["goal"], after, back.into(review, after), notes, p["executor"])


def still_open(note: str, before: dict, after: dict, review: dict) -> list[str]:
    """The root criteria the note names, or the round added, that the review run after it still finds the children do
    not secure. A round that answered a note asking to give the parts the checks a root criterion needs by adding one
    more root criterion — which the review then marked insufficient — had answered nothing, and the one note was spent
    (a tester's regex run, 2026-11-13)."""
    names = {c["name"] for c in after.get("root_criteria") or ()}
    asked = {n for n in names if n in note} | (names - {c["name"] for c in before.get("root_criteria") or ()})
    found = [x.strip() for x in str(review.get("semantic_findings") or "").splitlines()]
    return [x[:200] for x in found if x.startswith(("[insufficient]", "[uncertain]"))
            and x.split("]", 1)[1].strip().split(" ", 1)[0] in asked]


def unrepaired(before: dict, after: dict, gaps: list[str]) -> list[str]:
    """The root criteria of `gaps` — those the review found the parts do not secure — the round left as the review
    read them: still the root's, and no part mapped to one was mapped anew or had its criteria changed."""
    a, b, old = _parts(before), _parts(after), _pairs(before)
    touched = {c for c, k in _pairs(after) if (c, k) not in old or _crits(a.get(k, {})) != _crits(b.get(k, {}))}
    return [c for c in gaps if c in _crits(b[ROOT_ID]) and c not in touched]


def _pairs(s: dict) -> set:
    """{(root criterion, part id)} of a spec's mappings."""
    return {(m["criterion"], m["child_id"]) for m in s.get("mappings") or ()}


def _asked_kept(spec: dict, *authored: dict) -> dict:
    """`spec` (as built, `extract_spec`) with each criterion's `asked` as `authored` wrote it, the first that names it:
    the graph keeps no such field, and the plan file is where the person reads whose demand each criterion is."""
    said = {}
    for a in reversed(authored):
        said |= {(n, c.get("name")): c["asked"] for n, x in _parts(a or {}).items() for c in x.get("criteria") or ()
                 if "asked" in c}
    for n, x in _parts(spec).items():
        for c in x.get("criteria") or ():
            if (n, c.get("name")) in said:
                c["asked"] = said[(n, c.get("name"))]
    return spec


def beyond_said(spec: dict, request: str) -> list[str]:
    """Each criterion of `spec` the request (with the customer's notes) does not ask, as the plan file says it: the
    system's own requirement, not the person's (`decompose.beyond_the_request`). Never a gate."""
    return [f"{n} / {c.get('name')}: {c.get('description', '')[:200]}"
            for n, c in _decompose.beyond_the_request(spec, request)]


def _exact_kept(before: dict, after: dict) -> dict:
    """`after`, each check the round left as it was (one command, one expectation) still `exact` where it was: a model
    re-emitting a criterion left the flag out, and a note about two checks silently loosened six others (tracker,
    Sonnet, 2026-11-03). What the system runs exactly is no less so for a round that did not mean to change it."""
    exact = {(p.get("command"), p.get("expect")) for x in _parts(before).values() for c in x.get("criteria") or ()
             for p in c.get("check") or () if p.get("exact") is True}
    for x in _parts(after).values():
        for c in x.get("criteria") or ():
            for p in c.get("check") or ():
                if (p.get("command"), p.get("expect")) in exact:
                    p["exact"] = True
    return after


def _parts(s: dict) -> dict:
    """{part id: part} of a spec, the root's own criteria under the root's id."""
    return {ROOT_ID: {"criteria": s.get("root_criteria") or []}, **{x["id"]: x for x in s.get("subtasks") or ()}}


def _crits(x: dict) -> dict:
    """{criterion name: criterion} of a part."""
    return {c["name"]: c for c in x.get("criteria") or ()}


def changes(old: dict, new: dict) -> list[str]:
    """What a refine changed in the plan, part by part and criterion by criterion — read off the two specs."""
    a, b, out = _parts(old), _parts(new), []
    out += [f"part added: {k} — {b[k].get('name', '')}" for k in b if k not in a]
    out += [f"part removed: {k}" for k in a if k not in b]
    for k in (k for k in b if k in a):
        ca, cb = _crits(a[k]), _crits(b[k])
        out += [f"{k}: criterion added: {n}" for n in cb if n not in ca]
        out += [f"{k}: criterion removed: {n}" for n in ca if n not in cb]
        out += [f"{k}: criterion changed: {n}" for n in cb if n in ca and cb[n] != ca[n]]
        if k != ROOT_ID and {f: a[k].get(f) for f in ("name", "description", "writes", "runs")} != \
                {f: b[k].get(f) for f in ("name", "description", "writes", "runs")}:
            out.append(f"{k}: contract text changed")
        if k != ROOT_ID and a[k].get("split_after") != b[k].get("split_after"):
            out.append(f"{k}: split deferred until {', '.join(b[k]['split_after'].get('after') or ())} deliver"
                       if b[k].get("split_after") else f"{k}: no longer deferred — split now")
    deps = lambda s: {(d["from"], d["to"]) for d in s.get("deps") or ()}                  # noqa: E731
    out += [f"mapping added: {c} ← {k}" for c, k in sorted(_pairs(new) - _pairs(old))]
    out += [f"mapping removed: {c} ← {k}" for c, k in sorted(_pairs(old) - _pairs(new))]
    out += [f"dependency added: {f} → {t}" for f, t in sorted(deps(new) - deps(old))]
    out += [f"dependency removed: {f} → {t}" for f, t in sorted(deps(old) - deps(new))]
    if old.get("accepted_risks") != new.get("accepted_risks") or old.get("denial") != new.get("denial"):
        out.append("the register changed")
    return out or ["the round folded, but no part, criterion, mapping, dependency or risk differs"]


def text_of(plan: str) -> str:
    """A plan file's text, from its path or as given."""
    return Path(plan).read_text(encoding="utf-8") if "\n" not in plan and Path(plan).is_file() else plan


def kept(text: str) -> Path:
    """The plan file kept in the state directory under its content's hash — the system's own file, no node's place — its
    bytes that text's on every platform: a text mode wrote CRLF on Windows, so what an answer held was not the file."""
    path = data_dir() / "plans" / f"{hashlib.sha256(data := text.encode()).hexdigest()[:12]}.gfso"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def mark_reviewed(text: str) -> None:
    """Record that the system's own review was run over exactly `text` — keyed to its content, beside the kept file."""
    (at := _reviewed_at(text)).parent.mkdir(parents=True, exist_ok=True)
    at.write_text("", encoding="utf-8")


def was_reviewed(text: str) -> bool:
    """Did the system's own review run over exactly this text (`mark_reviewed`)? A `[review]` line in a file is no
    such record: the agent's own file could carry one (critic over f5b1f88)."""
    return _reviewed_at(text).is_file()


def _reviewed_at(text: str) -> Path:
    return data_dir() / "plans" / f"{hashlib.sha256(text.encode()).hexdigest()}.reviewed"


def _scratch() -> Engine:
    e = Engine(MemoryStorage(), HumanAgent(), llm=None, validate_signals=True, state_timeout=0)
    e.start()
    return e


@contextlib.contextmanager
def _booked(ledger, llm, stage=Stage.DECOMPOSER):
    """What `llm` spends here, on `ledger`, the book of the project that asked (`Engine.record_llm_usage`), though the
    call fail: no node holds a plan, and a person read $0.00 spent over ten minutes of planning (rehearsal, 2026-11-03)."""
    try:
        yield
    finally:
        if ledger is not None:
            ledger(stage, llm, TaskId(ROOT_ID))


class _TakenBack:
    """The authoring's progress, passed on, with what its repair took back kept — a criterion back to its admitted text,
    or one that never had any and left — for the plan file the customer reads before the go. Stranger run s17b: the core
    criterion left, said only on a progress line, and the go was given without hearing it."""

    def __init__(self, progress):
        self.progress, self.said = progress, []

    def __call__(self, msg: str) -> None:
        if "is taken back:" in msg:
            self.said += msg.split("is taken back:", 1)[1].strip().split(" | ")
        if self.progress is not None:
            self.progress(msg)

    def into(self, review: dict, spec: Optional[dict] = None) -> dict:
        """`review` with what was taken back, where there was any — of what left, only what is not in the final plan
        `spec`: the lines accumulate over the rounds, and one a later round wrote again, admitted, is not gone."""
        said = [x for x in dict.fromkeys(self.said) if spec is None or not _back_in(x, spec)]
        return {**review, "taken_back": said} if said else review


def _back_in(line: str, spec: dict) -> bool:
    """Is what this taken-back line says left — a node's criterion (`<node> / <name> leaves: …`) or a part (`<part>
    leaves: the part …`) — in the plan `spec`?"""
    parts = {str(k.get("id")): k for k in spec.get("subtasks") or ()}
    if m := re.match(r"(.+?) / (.+?) leaves: ", line):
        node = spec.get("root_criteria") if m[1] == ROOT_ID else (parts.get(m[1]) or {}).get("criteria")
        return m[2] in {c.get("name") for c in node or ()}
    return bool((m := re.match(r"(\S+) leaves: the part", line)) and m[1] in parts)


def _review(e: Engine, rid, model: str, execution=None, ledger=None, asked=(), pins: dict | None = None,
            beyond: list | None = None) -> dict:
    """The Level-2 review of the plan, its open obligations those of the goal and those of `asked` — what the customer's
    notes require (`refine`) — that no pinned check decides, the latter marked `of = "note"`; with what its pins did over
    the base (`pins_on_the_base`, `PinsOnTheBase.review`) — written where the customer reads the plan, never a gate."""
    llm = llm_factory(model, execution=execution)
    with _booked(ledger, llm, Stage.L2_CHECK_PLAN):
        c = json.loads(json.dumps(asdict(runner.review_decomposition(e, TaskId(str(rid)), llm=llm)), default=str))
        noted = runner.undecided_of(e, e.graph.get_task(TaskId(str(rid))), llm, asked) if asked else ()
    c["undecided_obligations"] = [*(c["undecided_obligations"] or ()), *({**g, "of": "note"} for g in noted)]
    return {"by": model, **{k: c[k] for k in _REVIEW_KEYS}, **({PINS: pins} if pins else {}),
            **({BEYOND: beyond} if beyond else {})}
