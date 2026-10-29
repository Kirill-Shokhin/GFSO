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

import base64
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Iterable, Optional

from gfso.core.protocol.procedure import (forget_round, pinned_run, probe_id, round_inputs, round_of, round_words,
                                          without_past_builds, without_pinned_runs, without_retired)
from gfso.core.types import HOST, LAID, VOLUME, Signal, TaskId, files_at
from .audit import VERSION_INSTALLING
from .verdicts import REGRESSION, criterion_version, ledger_read


#: what keys a validation or contact round in the record of the rounds standing (`round_stands`), by its name
_ROUND = "round-made:"
#: the rounds this process asked about where the record had none, and found not standing (`round_stands`)
_UNMADE: set = set()


def record_round(graph, path, made: bool) -> None:
    """The system made — or removed — the round `path` lies in: kept with the project's settings, a restart reads it;
    a removal drops what was read of the round's files (`forget_round`). A path in no round records nothing."""
    if (r := round_of(path)) is not None:
        graph.store_setting(_ROUND + r[1], "1" if made else "0")
        if not made:
            forget_round(r[0])


#: what keys, in the project's settings, what the system read of a file a finding's command names in its round, once
#: that round's runs had ended (`keep_files`): {"file": its sha256} or {"tree": {path in it: sha256}} — by the path;
#: {"lost": why} for an input it could not keep, which no re-run can then lay
_KEPT = "probe-file:"
#: …and each content, by its sha256, beside the verdicts
_BLOB = "probe-blob#"
#: the most of one named path the record keeps — a file, or a directory's files together; past it the path is not kept
KEEP_CAP = 16 << 20
#: under a judge's round or batch, where a re-run of a standing finding makes each round it names afresh (`lay_files`)
REGRESSION_DIR = "regression"


def _path_key(path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def keep_files(graph, storage, commands: Iterable[str]) -> None:
    """Each file the `commands` name in a validation round (`round_words`) kept in the system's record as it stands
    now — the first reading of a path stands, whatever is written there after. Called as findings are filed, their
    round's runs ended and every process of them with their containers (`ExecutionPort.release`); a re-run lays these
    from the record (`lay_files`) and reads nothing of the round. An input that cannot be read, or passes `KEEP_CAP`,
    is kept as LOST: re-run over an empty directory it refuted every delivery (`No such file`, critic over 909e417),
    so its finding is shown, not demanded (`round_stands`). A file the command itself writes is no input to lose."""
    for c in commands:
        inputs = set(round_inputs(c))
        for w in round_words(c):
            if graph.setting(_KEPT + _path_key(w)) is not None:
                continue
            try:
                fs = files_at(w)
                got = {"": raw} if (raw := fs.read_bytes(w, KEEP_CAP + 1)) is not None else fs.read_tree(w)
            except OSError as e:
                got = f"unreadable when its finding was filed ({e})"
            if not isinstance(got, dict) or sum(map(len, got.values())) > KEEP_CAP:
                if w in inputs:
                    graph.store_setting(_KEPT + _path_key(w), json.dumps({"lost": got if isinstance(got, str) else
                                        "not there when its finding was filed" if got is None else
                                        f"larger than the {KEEP_CAP >> 20} MiB the record keeps"}))
                continue
            sums = {rel: _keep_blob(storage, raw) for rel, raw in got.items()}
            graph.store_setting(_KEPT + _path_key(w), json.dumps({"file": sums[""]} if "" in sums else {"tree": sums}))


def _keep_blob(storage, raw: bytes) -> str:
    if storage.get_critique(TaskId(_BLOB + (d := hashlib.sha256(raw).hexdigest()))) is None:
        storage.store_critique(TaskId(_BLOB + d), base64.b64encode(raw).decode("ascii"))
    return d


def _blob(storage, d: str) -> Optional[bytes]:
    """The content kept under `d`, only where it still hashes to it."""
    raw = base64.b64decode(storage.get_critique(TaskId(_BLOB + d)) or "")
    return raw if hashlib.sha256(raw).hexdigest() == d else None


def lay_files(graph, storage, command: str, at, execution) -> str:
    """`command` as its re-run runs under `at`, a judge's own round or batch: each validation round it names
    (`round_of`) respelled as a directory of `at`'s own (`REGRESSION_DIR`), made afresh by the command itself from
    what the system lays for it in `<at>.laid` (`LAID`): the files of that round the record holds (`keep_files`; those
    of a round still standing kept now, first). From the record alone, and read-only to the judge: the delivered code
    its run executes — a `make`, a test, a process either left — cannot rewrite what the re-run starts from, and no
    earlier round is mounted to be read (critic over the judged tree: a forged `../probe.sh`, rc 0). A command naming
    no round is returned as it is."""
    if not (words := round_words(command)):
        return command
    keep_files(graph, storage, [command])
    laid_root, fresh, out, rounds = Path(str(at) + LAID), [], command, {}
    execution.files.mkdir(str(laid_root))           # …by the system, where no session writes
    for w in words:
        prefix = round_of(w)[0]
        rounds.setdefault(_path_key(prefix), []).append((w, prefix))
    for key, named in rounds.items():
        k = hashlib.sha256(key.encode()).hexdigest()[:12]
        src, work, laid = laid_root / k, Path(at) / REGRESSION_DIR / k, {}
        for w, prefix in named:
            rel = w[len(prefix):].replace("\\", "/").strip("/")
            rec = json.loads(graph.setting(_KEPT + _path_key(w)) or "{}")
            for sub, d in ({"": rec["file"]} if "file" in rec else rec.get("tree") or {}).items():
                if (raw := _blob(storage, d)) is not None:
                    laid["/".join(x for x in (rel, sub) if x)] = raw
            out = re.sub(re.escape(prefix) + r"(?=[\\/])", lambda _: work.as_posix(), out)   # …not `<round>9`
        execution.files.mkdir(str(src))             # …laid even when nothing was kept: the copy below reads it
        execution.files.write_files(str(src), laid)
        # …and the directory of every path it names, kept or not: a command writing its own output there found none
        # (critic over the judged tree: `cc ok.c -o <round>/batch1/prog` refuted every later delivery)
        dirs = sorted({(work / w[len(p):].replace("\\", "/").strip("/")).parent.as_posix() for w, p in named})
        fresh.append(f'rm -rf "{work.as_posix()}" && mkdir -p "{work.as_posix()}" && '
                     f'cp -a "{src.as_posix()}/." "{work.as_posix()}/" && '
                     + " && ".join(f'mkdir -p "{d}"' for d in dirs))
    execution.release(str(laid_root))           # …written: nothing of the system's runs there on
    return " && ".join(fresh) + f" && ( {out} )"


def round_stands(graph):
    """`unrerunnable`'s `standing`: does the round stand — or does the system's record hold what the path named there
    (`keep_files`), which a re-run lays from it (`lay_files`)? THE SYSTEM'S RECORD — it alone makes and removes rounds
    (`tools_llm._validation_place`, `issuer._contact_place`) and keeps their files — read with no subprocess, whoever
    asks: a verdict's record included. A round made before the record was kept is found once on this host, where rounds
    are directories until the places move into volumes (a fallback that goes with that move), then recorded."""
    def standing(r: tuple) -> bool:
        """Does the round `r` — (its path, its name in the record[, the path named in it]) — stand, or its file kept?"""
        if len(r) > 2 and (kept := graph.setting(_KEPT + _path_key(r[2]))) is not None:
            return "lost" not in json.loads(kept)
        if (got := graph.setting(_ROUND + r[1])) is not None:
            return got == "1"
        if r[0] in _UNMADE or graph.setting(VOLUME + "places"):         # …moved into a volume: the record alone
            return False
        if HOST.is_dir(r[0]):
            graph.store_setting(_ROUND + r[1], "1")
            return True
        _UNMADE.add(r[0])
        return False
    return standing


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
    pinned probes, the findings a ruling in force retired and those that run a past round's build."""
    return without_retired(without_pinned_runs(without_past_builds(ledger_read(storage, task.id, REGRESSION, {}) or {}),
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
