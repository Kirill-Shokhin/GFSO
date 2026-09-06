"""The verdict RECORD — one shape, one writer.

A verdict on a node's current delivery is written from three places (an independent validator's
report, a person's own review, and the self-check an INTERNAL node carries in its DELIVER packet per
§14.5 D6), and every reader — the self-PASS gate, `get_verdict`, q_V, the replay — depends on the
same keys and on the generation stamp being right. The shape is here so those three cannot drift; the
POLICY about what may be recorded stays with each caller, where it belongs.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from gfso.core.types import TaskId


def store_verdict(storage, task_id: TaskId, task, verdict: str, failed_criteria,
                  validator_id: str, generation: tuple,
                  per_criterion: Optional[list] = None,
                  tools_used: Optional[dict] = None,
                  model: Optional[str] = None, workdir: Optional[str] = None,
                  by_hand: bool = False) -> None:
    """Write the record for THIS delivery — `storage` is the port, handed in by the caller that owns it. `generation` = (iteration, reopens, revisions) as it stood
    when the verdict was earned — a rework, a reopen or a revision under it makes the record stale,
    which is what every reader checks before trusting it."""
    storage.store_exec_verdict(task_id, json.dumps({
        "verdict": verdict, "failed_criteria": list(failed_criteria or ()),
        "validator": validator_id,
        # …and WHICH MODEL it was. The record named the instrument's role and not its tier, so a
        # verdict from a cheap judge and one from an expensive judge were the same row — and the
        # tier of a role has already been wrong twice without anything saying so.
        "validator_model": model,
        # WHAT KIND OF PARTY STOOD BEHIND THIS. The seam gate compares the reviewer's NAME to the
        # executor's, so a name invented in the same breath satisfies it — the canon's named
        # boundary (§13.6: no structural CHECK guards FM-3's false PASS), not something a check can
        # close. What must not happen is laundering: a verdict a person asserted at a door where
        # identity is self-declared read back exactly like an instrument's report (measured on the
        # CLI door 2026-09-02, with the observation "x" against every criterion). Stored at write
        # time, because "is this reviewer a registered role" is a fact about the moment of judging,
        # and the roster is server-wide and mutable.
        "by_hand": bool(by_hand),
        **dict(zip(("iteration", "reopens", "revisions"), generation)),
        "per_criterion": list(per_criterion or ()),
        # The criteria AS THEY STOOD when contact refuted them. Without this snapshot a later
        # revision is unreadable: "the criterion was covered" and "the criterion was lowered to what
        # the children already deliver" have the same shape at the re-delivery, and the second is a
        # false close (corner #5, `formal/README.md`). Records written before this field exist read
        # as "text unknown", which the disposition treats as unchanged — the conservative direction.
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
        "ts": datetime.now().isoformat(sep=" ", timespec="seconds")}))
