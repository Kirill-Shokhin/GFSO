"""The verdict RECORD — one shape, one writer.

A verdict on a node's current delivery is written from three places (an independent validator's
report, a person's own review, and the self-check an INTERNAL node carries in its DELIVER packet per
§10.3), and every reader — the self-PASS gate, `get_verdict`, q_V, the replay — depends on the
same keys and on the generation stamp being right. The shape is here so those three cannot drift; the
POLICY about what may be recorded stays with each caller, where it belongs.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from gfso.core.protocol.invariants import verdict_word
from gfso.core.types import TaskId
from gfso.core.types.enums import Verdict
from gfso.core.graph.model import stamp
from gfso.core.protocol.procedure import coverage as procedure_coverage


#: The records kept BESIDE a node's verdict, each under its own key in the critique store — one table of their names and
#: one reader and writer, where seven hand-built keys were each read and written in their own spelling, three readers
#: guarding a corrupt record and three not (ortho audit, D-F11).
OBSERVATIONS, REFUTED_VERSIONS, CLOSING, OVERRULED, REJECTED_REPORT, REGRESSION, FAILED_THROUGH_PARTS = (
    "observations", "refuted-versions", "closing-verdict", "overruled-verdict", "rejected-report",
    "regression-probes", "failed-through-parts")


def ledger_read(storage, task_id, kind: str, default=None):
    """The `kind` record kept beside this node's verdict, or `default`; one that does not read reads as absent."""
    try:
        raw = storage.get_critique(TaskId(f"{task_id}#{kind}"))
        return json.loads(raw) if raw else default
    except (ValueError, TypeError):
        return default


def ledger_write(storage, task_id, kind: str, rec) -> None:
    """Keep `rec` as this node's `kind` record beside its verdict."""
    storage.store_critique(TaskId(f"{task_id}#{kind}"), json.dumps(rec, default=str))


def store_verdict(storage, task_id: TaskId, task, verdict: str, failed_criteria,
                  validator_id: str, generation: tuple, log_at: int,
                  per_criterion: Optional[list] = None,
                  tools_used: Optional[dict] = None,
                  model: Optional[str] = None, workdir: Optional[str] = None,
                  by_hand: bool = False, validated: Optional[dict] = None,
                  parts_not_shown_holding: Optional[dict] = None, inputs_dirs: tuple = ()) -> None:
    """Write the record for THIS delivery — `storage` is the port, handed in by the caller that owns it. `generation` = (iteration, reopens, revisions) as it stood
    when the verdict was earned — a rework, a reopen or a revision under it makes the record stale,
    which is what every reader checks before trusting it. `log_at` = the length of the signal log when it was
    recorded: whether anything it is built from moved since is a question about the log's order, never the
    clock's (`validation.record_stands`)."""
    # EVERY OBSERVATION OF A DELIVERY IS KEPT, not only the latest record. What binds is an appointed
    # observer's record of THIS delivery (C-12, Inv-2), and reading the latest record alone let a later
    # hand record of anyone's — a FAIL by a passer-by, then a PASS — launder the instrument's refutation
    # away (critic, 2026-09-27). The record below stays the CURRENT verdict every reader already reads.
    # …each with its place in the log: a record's currency is read against the log (`validation.record_stands`), and a
    # ledger row with no place stood for a signature after a part below it was delivered again
    ts = datetime.now().isoformat(sep=" ", timespec="microseconds")
    _ledger = observations(storage, task_id)
    _ledger.append({"verdict": str(verdict), "failed_criteria": list(failed_criteria or ()),
                    "validator": str(validator_id), "by_hand": bool(by_hand), "ts": ts, "log_at": int(log_at),
                    **stamp(generation)})
    ledger_write(storage, task_id, OBSERVATIONS, _ledger)
    storage.store_exec_verdict(task_id, json.dumps({
        "verdict": verdict, "failed_criteria": list(failed_criteria or ()),
        "validator": validator_id,
        # …and WHICH MODEL it was. The record named the instrument's role and not its tier, so a
        # verdict from a cheap validator and one from an expensive validator were the same row — and the
        # tier of a role has already been wrong twice without anything saying so.
        "validator_model": model,
        # WHAT KIND OF PARTY STOOD BEHIND THIS. The seam gate compares the reviewer's NAME to the
        # executor's, so a name invented in the same breath satisfies it — the canon's named
        # boundary (§15.7: no structural CHECK guards FM-3's false PASS), not something a check can
        # close. What must not happen is laundering: a verdict a person asserted at a door where
        # identity is self-declared read back exactly like an instrument's report (measured on the
        # CLI door 2026-09-02, with the observation "x" against every criterion). Stored at write
        # time, because "is this reviewer a registered role" is a fact about the moment of validation,
        # and the roster is server-wide and mutable.
        "by_hand": bool(by_hand),
        **stamp(generation),
        "per_criterion": list(per_criterion or ()),
        # The criteria AS THEY STOOD when contact refuted them. Without this snapshot a later
        # revision is unreadable: "the criterion was covered" and "the criterion was lowered to what
        # the children already deliver" have the same shape at the re-delivery, and the second is a
        # false close (corner #5, `formal/README.md`). Records written before this field exist read
        # as "text unknown", which the disposition treats as unchanged — the conservative direction.
        "parts_not_shown_holding": dict(parts_not_shown_holding or {}),
        "criteria_text": {c.name: c.description for c in task.spec.criteria}
        if task is not None else {},
        # What the validator actually DID, by tool. Its report may claim an execution; this says
        # whether one happened. A FAIL whose evidence cites runs while `Bash` is absent is refuted
        # structurally, without parsing a word of its prose.
        "tools_used": dict(tools_used or {}),
        # WHERE THE PROBES WERE RUN. The record's evidence quotes commands — `cd <dir> && pytest …` —
        # and a rename a minute later made every one of them unreplayable: "a stored verdict I can't
        # re-run is a stored verdict I can't trust later" (measured on the human door 2026-08-22).
        # Naming the tree the verdict was earned in does not make the probes eternal; it makes their
        # staleness diagnosable instead of mysterious.
        "workdir": workdir or "",
        # WHAT THE VERDICT ACTUALLY REACHED. The digest names the procedure the contract pinned at
        # the moment of validating, the counts say how much of the contract carried one and how far
        # the validation went beyond it. This is the honest half of a closure: checked by P — and
        # behaviour outside P unchecked, which is the FM-3 boundary (Ch. 20) stated, never closed.
        # Without it a PASS is a word; with it a later reader can re-run exactly what was run.
        # …counted by the gate's own reader, over the same inputs directories: a probe reported by its laid-down
        # command and no id was ACCEPTED by the gate and recorded "never run" here (GB_c_compiler_tmokgz344, root.vec)
        **(procedure_coverage(task.spec.criteria, per_criterion or (), inputs_dirs) if task is not None else {}),
        "ts": ts, "log_at": int(log_at)}))
    if verdict_word(verdict) == Verdict.FAIL and task is not None:
        _remember_refuted_versions(storage, task_id, task, failed_criteria, validated)


def observations(storage, task_id: TaskId) -> list:
    """Every verdict record ever made on this node, oldest first; an unreadable ledger — or one that reads as no list —
    reads empty, so a corrupt record never stops the node taking its next verdict (critic O2)."""
    rec = ledger_read(storage, task_id, OBSERVATIONS, [])
    return list(rec) if isinstance(rec, list) else []


def criterion_version(description, probes) -> list:
    """What a criterion promised, as one comparable value: its text, every probe's whole triple
    (loosening an `expect` under an unchanged command is the cheapest way to loosen a check) AND the
    files each probe pins.

    The corpus belongs in the version for the same reason the `expect` does: swapping a sixty-file
    torture set for a two-file one, under the same command, loosens the check completely — and
    `claim_drift`'s `reprobed` and "rewritten after refutation" both read THIS value, so without the
    inputs the one surface built to catch a loosened check was blind to the loosening the pinned
    corpus makes possible. Found by an outside reviewer with a reproduction."""
    # LISTS, not tuples: this value is STORED as JSON and compared against what is read back, and
    # JSON has no tuple — so a version carrying `sorted(dict.items())` never equalled its own stored
    # copy. Every pinned-inputs criterion that had ever been refuted then read as "rewritten after
    # refutation", which drives `narrowed` to ⊥: the surface added to see a swapped corpus was made
    # blind by the shape of the value it compares. Found by an outside reviewer with a reproduction.
    def _inputs(p) -> list:
        raw = p.get("inputs") or []
        pairs = sorted(raw.items()) if isinstance(raw, dict) else raw
        return [[str(a), str(b)] for a, b in (tuple(x) for x in pairs)]

    return [description or "", [[p.get("behaviour"), p.get("command"), p.get("expect"), _inputs(p)]
                                for p in (probes or ())]]


def _remember_refuted_versions(storage, task_id: TaskId, task, failed_criteria,
                               validated: Optional[dict] = None) -> None:
    """{criterion: [every version of it that a verdict refuted]} — kept at the moment of refuting.

    Whether a criterion was rewritten AFTER it was refuted cannot be read back from positions: a
    verdict alone sends no signal, a reviewer's FAIL may carry no probe, and the issuer may revise
    straight out of VALIDATING. What the refutation validated is known only now, so it is written now.
    """
    have = refuted_versions(storage, task_id)
    for c in task.spec.criteria:
        if c.name in set(failed_criteria or ()):
            # the version the verdict VALIDATED (at the last DELIVER), falling back to the current one
            v = (validated or {}).get(c.name) or criterion_version(
                c.description, [p.to_dict() for p in (c.check or ())])
            if v not in have.setdefault(c.name, []):
                have[c.name].append(v)
    ledger_write(storage, task_id, REFUTED_VERSIONS, have)


def refuted_versions(storage, task_id: TaskId) -> dict:
    """{criterion: [versions a FAIL verdict validated]} as stored; an unreadable record reads empty."""
    return ledger_read(storage, task_id, REFUTED_VERSIONS, {})
