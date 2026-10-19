"""The validator's findings standing on a node, and the issuer's RULING that retires one — one definition, read by the
signal gate (`validation.ruling_refusal`), the engine (`regression_probes`, `retired_findings`) and every surface.

A finding speaks to its criterion, and only the issuer's signature decides a criterion (§10.2: the check is the
validator's, the signature the issuer's). So a finding stops being demanded only by his ruling, and the ruling is
part of his ACCEPT_CHALLENGE (§11.2–11.3): the ids it retires ride that signal and land on its log row, the act and
its ruling one entry. It names finding ids the executor's CHALLENGE named — what the dispute was about, nothing
wider — and holds for the criterion's text as the act left it: once a later act rewrites that criterion (a revision,
`edit_criteria`, another accepted challenge, a REOPEN), the ruling LAPSES and the finding is demanded again.

Each proxy for the ruling misfired (critics over f0584f3, ca228e0, 28bd5e7, 868ede5): keyed by the packet's version a
deadline extension erased every finding; by the criterion's text, an accepted challenge leaving the text as it was
kept the disputed finding; by a whole-word criterion name in the CHALLENGE, an incidental mention retired every
finding on it; written after the ACCEPT_CHALLENGE returned, a dispatcher's ACCEPT landing in between left the
challenge accepted and nothing retired; unbounded in time, a ruling on `conf` outlived a tightened `conf`."""
from __future__ import annotations

import json
import re
from typing import Iterable, Optional

from gfso.core.protocol.procedure import pinned_run, probe_id, without_pinned_runs, without_retired
from gfso.core.types import Signal
from .audit import VERSION_INSTALLING
from .verdicts import REGRESSION, criterion_version, ledger_read


def ever_pinned(entries: Iterable, task) -> dict:
    """{id: command} of every pinned probe the node's contract has carried, in force or since withdrawn —
    whoever issued the revision (`without_pinned_runs`). A refutation by a probe the version in force no longer
    carries is not a standing verdict under the current criteria, and a refusal resting on one is liftable only by changing an artifact the
    current contract does not fault (§12.16 (ii)) — whoever issued the revision. Where the issuer is the
    executor this was also his named lift (`observation_binds`), which lifted nothing while the run stayed.
    He could already drop or rename the criterion (its refutations then stand as orphaned, named not
    blocking); what guards a weakened probe is the record, not a refusal — `claim_drift` and the closure's
    `narrowed_after_authoring` name a criterion whose procedure changed after it was refuted. At a
    self-issued root, where nothing above carries the verdict, that record is the whole safeguard."""
    if task is None:
        return {}
    ever: dict = {}
    for e in entries:
        if e.signal in VERSION_INSTALLING and not e.rejected and e.spec:
            try:
                ever.update({probe_id(c.get("name", ""), p): str(p.get("command", ""))
                             for c in json.loads(e.spec).get("criteria") or () for p in c.get("check") or ()})
            except (ValueError, TypeError):
                continue
    ever.update({probe_id(c.name, p): p.command for c in task.spec.criteria for p in (c.check or ())})
    return ever


def released(p: dict, criterion: str, gone: dict, seen: frozenset = frozenset()) -> bool:
    """Is probe `p`, reported under `criterion`, POSITIVELY one the next PASS no longer runs — a run of a pinned probe the
    version in force withdrew, or a finding retired or unable to run (`gone`: {id: command})? Only an identified one
    is: a probe matched by nothing still binds, as the gate reads it (a validator may report a pinned probe by its laid
    path and no id; hidden then, an executor got a bare criterion name and re-delivered blind — critic r4). A finding
    over laid inputs is stored with its directory as a token, so its own run is known by the command as run (`seen`: {(criterion, command)})."""
    pid = probe_id(criterion, p)
    return (bool(pinned_run(p, gone, criterion)) or pid in gone or (criterion, " ".join(str(p.get("command") or "").split())) in seen
            or f"{pid.rsplit('#', 1)[0]}#{p.get('id')}" in gone)


def rulings(storage, entries: list, task_id) -> list[dict]:
    """Every ruling on the node's log, oldest first — {criterion, id, command, by, at, why, text, lapsed}: the finding
    retired, the ACCEPT_CHALLENGE that retired it (who, when, why), the criterion's text as that act left it, and
    whether a later act rewrote that text (`lapsed`, the entry's time, else None)."""
    found = {p.get("id"): (c, p) for c, ps in (ledger_read(storage, task_id, REGRESSION, {}) or {}).items() for p in ps}
    in_force: dict = {}
    out: list[dict] = []
    for e in entries:
        if e.rejected:
            continue
        if e.signal in VERSION_INSTALLING and e.spec:
            try:
                in_force = {c.get("name"): criterion_version(c.get("description"), c.get("check"))
                            for c in (json.loads(e.spec).get("criteria") or ()) if c.get("name")}
            except (ValueError, TypeError):
                in_force = {}
            for r in out:
                if r["lapsed"] is None and in_force.get(r["criterion"]) != r["text"]:
                    r["lapsed"] = e.timestamp.isoformat(timespec="seconds")
        if e.signal == Signal.ACCEPT_CHALLENGE and e.retire_findings:
            out += [{"criterion": found[i][0], "id": i, "command": found[i][1].get("command"), "by": str(e.source),
                     "at": e.timestamp.isoformat(timespec="seconds"), "why": e.justification or e.reason or "",
                     "text": in_force.get(found[i][0]), "lapsed": None,
                     "seen": found[i][1].get("seen") or found[i][1].get("as_run")}
                    for i in dict.fromkeys(e.retire_findings) if i in found]
    return out


def standing_rulings(storage, entries: list, task_id) -> list[dict]:
    """The rulings in force: those whose criterion still reads as the ruling act left it."""
    return [r for r in rulings(storage, entries, task_id) if r["lapsed"] is None]


def regression(storage, entries: list, task) -> dict:
    """{criterion: [the validator's findings demanded of this node]} — every refutation recorded, less the runs of
    pinned probes and the findings a ruling in force retired."""
    return without_retired(without_pinned_runs(ledger_read(storage, task.id, REGRESSION, {}) or {},
                                               ever_pinned(entries, task)),
                           standing_rulings(storage, entries, task.id))


def ruling_defect(storage, entries: list, task, ids: Iterable[str]) -> Optional[str]:
    """Why an ACCEPT_CHALLENGE may not retire `ids` on this node, or None. Each must stand on it, and the executor's
    CHALLENGE — the one this act answers — must name it by its id: a ruling answers what was disputed."""
    ids = list(ids)
    standing = {p.get("id") for ps in regression(storage, entries, task).values() for p in ps}
    if gone := [i for i in ids if i not in standing]:
        return (f"no finding {', '.join(gone)} stands on {task.id} — the standing ones are "
                f"{', '.join(sorted(standing)) or 'none'}")
    if wide := [i for i in ids if i not in named(_challenge(entries), standing)]:
        return (f"the challenge of {task.id} does not name {', '.join(wide)} — a ruling retires only the findings "
                f"the dispute named by id")
    return None


def disputed_findings(storage, entries: list, task) -> list[str]:
    """The ids of the findings standing on the node that its latest CHALLENGE names — the ruling it asks for."""
    return named(_challenge(entries), [p.get("id") for ps in regression(storage, entries, task).values() for p in ps])


def _challenge(entries: list) -> str:
    """The reason of the node's latest accepted CHALLENGE, or ''."""
    return next((e.reason or "" for e in reversed(entries) if e.signal == Signal.CHALLENGE and not e.rejected), "")


def named(said: str, standing: Iterable) -> list[str]:
    """The standing finding ids `said` names: a full id as a word of its own names itself; its hash written any other
    way — bare, or after a criterion spelled otherwise (`the_conf_criterion#…`) — names every standing finding that
    ends in it, whatever criterion it stands under. The hash is the probe's COMMAND (`probe_id`), so one hash under two
    criteria is one probe, and a dispute naming it unqualified disputes it wherever it stands. Read as naming neither, a
    true dispute of one probe under two criteria was ruled on four times, each ruling refused whole, and the part
    closed by count (AUTO haiku coreutils, root.tr, 2026-10-12)."""
    ids = [str(s) for s in dict.fromkeys(standing) if s]
    out = {s for s in ids if re.search(rf"(?<![\w#]){re.escape(s)}(?!\w)", said)}
    for h in {s.rsplit("#", 1)[-1] for s in ids}:
        mine = [s for s in ids if s.rsplit("#", 1)[-1] == h]
        if any(not any(said[:m.start()].endswith(s[:-len(h)]) for s in mine)
               for m in re.finditer(rf"(?<!\w){re.escape(h)}(?!\w)", said)):
            out.update(mine)
    return [s for s in ids if s in out]
