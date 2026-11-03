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
from dataclasses import asdict
from pathlib import Path

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


def author(request: str, model: str, executor: str = "", depth: int = 1, review_model: str = "",
           progress=None, execution=None, ledger=None) -> str:
    """A plan file for `request`: authored by `model`, its fit judged against `executor`'s session, reviewed. The file
    holds the plan as BUILT (`extract_spec`), the shape a refine and the go read back."""
    e, llm = _scratch(), _decompose.default_llm(model, execution=execution)
    with _booked(ledger, llm):
        res = _decompose.decompose_into(e, request, root_id=ROOT_ID, assignee=agent_id(), depth=depth, model=model,
                                        llm=llm, progress=progress, executor=executor)
    return artifact.render(request, extract_spec(e, str(res.root_id)),
                           _review(e, res.root_id, review_model or model, execution, ledger), executor=executor)


def refine(text: str, note: str, model: str, review_model: str = "", progress=None, execution=None, ledger=None) -> str:
    """The plan file after the customer's `note`: one refine round over it with the note as its finding, the answer
    being what the round changed (or that it changed nothing), the review run again over the result."""
    p = artifact.parse(text)
    e, llm = _scratch(), _decompose.default_llm(model, execution=execution)
    # …a file the admission refuses is this round's to repair, never a dead end: the go's refusal sends the customer
    # here, and the round itself built the file first and died on the same refusal (V3_cc2, 2026-11-01)
    with _booked(ledger, llm):
        spec = _decompose.repaired_before_build(p["spec"], p["goal"], llm, p["executor"], progress, e, ROOT_ID)
    _, rid, _ = build_graph_live(spec, p["goal"], e, root_id=ROOT_ID, assignee=agent_id())
    before = p["spec"]                          # the plan as the customer has it — what the answer says changed
    open_ = [f"[undecided] {g.get('obligation')} — admits: {g.get('admits')}"
             for g in p["review"].get("undecided_obligations") or ()]
    findings = "# THE CUSTOMER'S NOTE ON THIS PLAN\n" + note.strip() + (
        "\n\n# OPEN LEVEL-2 FINDINGS the plan was reviewed with\n" + "\n".join(open_) if open_ else "")
    with _booked(ledger, llm):
        changed, _, problems = _decompose.refine_with(e, p["goal"], rid, agent_id(), llm,
                                                      findings, progress=progress, executor=p["executor"])
    changed = changed or spec != p["spec"]        # …the repair before the build changed it too
    after = extract_spec(e, str(rid))
    # …said as what it is: one round read the note TOGETHER with the review's open findings, so a change is the round's,
    # not proven the note's; and an unchanged plan is the system's answer to the note, the review below its reasons
    head = ("what the round that read this note (with the review's open findings) changed:" if changed else
            "the plan is unchanged: the round that read this note folded nothing into it — the plan as it stands, "
            "and the review below, are the answer; send a sharper note, or name a stronger model")
    answer = [head] + (changes(before, after) if changed else [])
    notes = p["notes"] + [{"note": note, "by": model, "answer": "\n".join(answer + [f"open: {x}" for x in problems])}]
    return artifact.render(p["goal"], after, _review(e, rid, review_model or model, execution, ledger),
                           notes, p["executor"])


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
    pairs = lambda s: {(m["criterion"], m["child_id"]) for m in s.get("mappings") or ()}  # noqa: E731
    deps = lambda s: {(d["from"], d["to"]) for d in s.get("deps") or ()}                  # noqa: E731
    out += [f"mapping added: {c} ← {k}" for c, k in sorted(pairs(new) - pairs(old))]
    out += [f"mapping removed: {c} ← {k}" for c, k in sorted(pairs(old) - pairs(new))]
    out += [f"dependency added: {f} → {t}" for f, t in sorted(deps(new) - deps(old))]
    out += [f"dependency removed: {f} → {t}" for f, t in sorted(deps(old) - deps(new))]
    if old.get("accepted_risks") != new.get("accepted_risks") or old.get("denial") != new.get("denial"):
        out.append("the register changed")
    return out or ["the round folded, but no part, criterion, mapping, dependency or risk differs"]


def text_of(plan: str) -> str:
    """A plan file's text, from its path or as given."""
    return Path(plan).read_text(encoding="utf-8") if "\n" not in plan and Path(plan).is_file() else plan


def kept(text: str) -> Path:
    """The plan file kept in the state directory under its content's hash — the system's own file, no node's place."""
    path = data_dir() / "plans" / f"{hashlib.sha256(text.encode()).hexdigest()[:12]}.gfso"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


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


def _review(e: Engine, rid, model: str, execution=None, ledger=None) -> dict:
    llm = llm_factory(model, execution=execution)
    with _booked(ledger, llm, Stage.L2_CHECK_PLAN):
        c = json.loads(json.dumps(asdict(runner.review_decomposition(e, TaskId(str(rid)), llm=llm)), default=str))
    return {"by": model, **{k: c[k] for k in _REVIEW_KEYS}}
