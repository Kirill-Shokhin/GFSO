"""A validation report read against the pinned procedure: what it accounts for, what it owes, and what it leaves.

`procedure.py` says what the procedure IS — a probe's identity and digest, what a contract must pin to be admitted,
where inputs are laid, what a round's files are, how an output is read against `expect`. This module reads a REPORT
over it: which pinned probes a report ran and cited (`canonical_citations`, `unrun_pinned`, `coverage`), which probes
refuted a criterion and stand as findings to re-run (`refuting_probes`, `merge_regression`, `unrun_regression`,
`unrerunnable`), what the system's own runs and the parts' checks add to it (`with_engine_observations`,
`with_part_observations`, `part_credit`), and what a ruling takes off (`pins_ruled_out`). Every question here starts
from a report or a regression set; nothing in `procedure.py` asks one back.
"""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from gfso.core.types import HOST, INPUTS_TOKEN, Criteria, Probe, unprojected
from gfso.core.graph.model import is_its_executor
from gfso.core.protocol.invariants import (ON_NO_DELIVERY, OVER_A_PASS, PAST_BOUND, UNDER_THE_DEFAULT, emits_a_constant,
                                          probe_held, probes_of, spoken_verdict, underprobed)
from gfso.core.protocol.procedure import (PROBE_S, contains, finding_id, inputs_dir_name, inputs_token, layable_over,
                                          pinned_probes, probe_id, probe_key as _norm, procedure_digest, round_of,
                                          runs_a_past_build, same_probe, tokenized)


def canonical_citations(per_criterion: Sequence[Mapping], criteria: Sequence[Criteria],
                        parts: Mapping[str, Sequence[Criteria]] | None = None) -> list:
    """The report with each probe it cites by a spelling the system gave a pinned probe — the name of the directory its
    inputs were laid down in (`inputs_dir_name`), whichever separators the citation kept — cited by that probe's id, the
    node's own or a part's; a spelling two probes share is left as it came. Read once, where a report is recorded, so no
    reader spells it again: a validator citing the directory it ran from had 65 truthful PASS reports refused, part
    probes at a root among them, and its FAILs' runs of pinned probes filed as findings to re-run (E3, 2026-10-22)."""
    ids = {probe_id(c.name, p) for cs in [criteria or ()] + list((parts or {}).values()) for c in cs
           for p in (c.check or ()) if _norm(p.command)}
    by: dict[str, set[str]] = {}
    for pid in ids:
        by.setdefault(inputs_dir_name(pid), set()).add(pid)
    one = {d: next(iter(s)) for d, s in by.items() if len(s) == 1}

    def _cite(q):
        i = str(q.get("id", "")).strip()
        to = one.get(inputs_dir_name(i)) if i and i not in ids else None
        return {**q, "id": to} if to else q
    return [{**e, "probe": [_cite(q) for q in probes_of(e)]} if probes_of(e) else e for e in per_criterion or ()]


def _cited(name: str, cited: str) -> str:
    """The probe id a citation under criterion `name` names: `criterion#hash` as written, a bare hash read inside `name`,
    and the spellings the system itself gave the probe — the directory its inputs were laid down in
    (`inputs_dir_name`), or that name's `#` kept. A validator cited the directory it ran from, `Statements_and_control_flow
    _79bd1260`, and 65 truthful PASS reports over 7 rows were refused as not having run their pinned checks (E3, 2026-10-22)."""
    crit, sep, h = cited.rpartition("#")
    if sep:
        return f"{name}#{h}" if inputs_dir_name(crit) == inputs_dir_name(name) else cited
    pre = inputs_dir_name(name) + "_"
    return f"{name}#{cited[len(pre):]}" if cited.startswith(pre) and len(cited) > len(pre) else f"{name}#{cited}"


def _reported_ids(name: str, probes: Sequence[Mapping], dirs: Iterable[tuple[str, object]] = ()) -> set[str]:
    """The probe ids a report accounts for under criterion `name`: its cited ids — a bare hash read
    inside the criterion it is reported under — and, for each probe, the id of the command it ran.

    One owner for the three readers (pinned, regression, coverage): measured 2026-09-27, a validator
    cited pinned probes as `568a2aaa` and the pinned rule alone learned to read it, while the regression
    rule and the coverage count kept demanding `criterion#hash`."""
    out: set[str] = set()
    for p in probes:
        if (_id := str(p.get("id", "")).strip()):
            out.add(_cited(name, _id))
        # …AND BY THE COMMAND WHEN THE ID IS ABSENT. A report that ran the pinned command and
        # spelled no id has still run it; refusing it would teach the reader to paste ids
        # instead of commands, which is the fabrication this whole module exists against.
        out.add(probe_id(name, p))
        # …AND BY THE FINDING IT RE-RAN: a finding over a validator's own scratch file is named by that file's content
        # too (`finding_id`), read now, where the report's files stand
        out.add(finding_id(name, str(p.get("command", ""))))
        # …over this round's inputs directories too: a regression line is stored with them NAMED, and a pinned
        # probe with its own as `{inputs}`, so the command a validator ran over the directories laid down for it
        # this round is matched in both forms (`tokenized`).
        if dirs := tuple(dirs or ()):
            named = tokenized(str(p.get("command", "")), dirs)
            out.add(probe_id(name, {"command": named}))
            out.add(finding_id(name, named))
            out.add(probe_id(name, {"command": re.sub(r"\{inputs:[^}]*\}", INPUTS_TOKEN, named)}))
    return out


def _read_report(per_criterion: Sequence[Mapping], dirs: Iterable[tuple[str, object]] = ()) -> tuple[dict, dict]:
    """({criterion: its spoken verdict}, {criterion: the probe ids it accounts for}) — what every demand reads."""
    verdicts: dict[str, str] = {}
    reported: dict[str, set[str]] = {}
    for e in per_criterion or ():
        name = _norm(e.get("criterion"))
        verdicts[name] = spoken_verdict(e.get("verdict"))
        reported.setdefault(name, set()).update(_reported_ids(name, probes_of(e), dirs))
    return verdicts, reported


def unrun_pinned(criteria: Sequence[Criteria], per_criterion: Sequence[Mapping],
                 dirs: Iterable[tuple[str, object]] = ()) -> dict[str, list[str]]:
    """{criterion: [pinned probe ids the report does not account for]} — over PASSED criteria only.

    A criterion the report refutes is not asked to have run the rest of its procedure: a refutation
    is already the verdict, and demanding the full sweep before a FAIL may be spoken would buy
    silence, not coverage. A criterion left `undecidable` is likewise not a claim of execution.
    """
    verdicts, reported = _read_report(per_criterion, dirs)
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        name = _norm(c.name)
        if verdicts.get(name) != "pass":
            continue
        missing = [probe_id(c.name, p) for p in (c.check or ())
                   if _norm(p.command) and probe_id(c.name, p) not in reported.get(name, set())]
        if missing:
            out[c.name] = missing
    return out


def named_beyond_procedure(criteria: Sequence[Criteria], per_criterion: Sequence[Mapping],
                           dirs: Iterable[tuple[str, object]] = ()) -> dict[str, list[str]]:
    """{criterion: behaviours the report named under it without a probe labelled for each} — over PASSED criteria whose
    whole pinned procedure this report ran. Such a criterion is decided by that procedure (A1; Inv-1 pre-registered it
    before the work): what the validator names beyond it is exploration — recorded beside the verdict as named but not
    separately observed, never a conjunct the verdict waits on. Measured (AUTO coreutils, 2026-10-10): four of seven
    refused reports named `\\0NNN`, a mid-line `\\r`, LANG variants — which the criterion's own pinned probe, run and
    cited by id, exercises — and were refused for labelling that probe with one behaviour. A criterion with no pinned
    procedure, one passed short of it, or one whose named behaviour carries a divergence (a FAIL, §12.8) keeps the
    label rule (`underprobed`)."""
    named = underprobed(per_criterion)
    verdicts, _ = _read_report(per_criterion, dirs)
    unrun = unrun_pinned(criteria, per_criterion, dirs)
    return {c.name: named[c.name] for c in criteria or ()
            if c.name in named and c.name not in unrun and verdicts.get(_norm(c.name)) == "pass"
            and any(_norm(p.command) and not emits_a_constant(p.command) for p in (c.check or ()))}


def orphaned_regression(criteria: Iterable[Criteria], regression: Mapping) -> dict[str, list[str]]:
    """{criterion name no longer in the contract: [the probes that once refuted it]}.

    The regression set is keyed by criterion NAME, and a plan repair may rename or replace the
    criterion — which is a NORMAL path here, not a corner: a FAIL that indicts the decomposition is
    answered by repairing it. The obligation then evaporates silently: nothing matches the new
    name, nothing is demanded, and the node passes over a repair that was never re-observed.

    It cannot be fixed by demanding the probe against a criterion that no longer exists — the
    contract legitimately moved. So it is SAID instead: an orphaned refutation is residue, named in
    the closure, exactly like the behaviour outside the pinned set. Found by an outside reviewer
    the day this landed; the silent version is the one this whole change exists against.
    """
    have = {_norm(c.name) for c in (criteria or ())}
    return {name: [p.get("id") for p in probes]
            for name, probes in (regression or {}).items() if _norm(name) not in have}


def coverage(criteria: Sequence[Criteria], per_criterion: Sequence[Mapping],
             dirs: Iterable[tuple[str, object]] = ()) -> dict:
    """What a verdict records about its own reach: the digest, the pinned count, and what was run
    BEYOND the pinned set — the honest half of "checked by P, behaviour outside P unchecked"."""
    pinned = pinned_probes(criteria)
    pinned_ids = {i["id"] for v in pinned.values() for i in v}
    extra = 0
    for e in per_criterion or ():
        name = _norm(e.get("criterion"))
        for p in probes_of(e):
            if not (_reported_ids(name, [p], dirs) & pinned_ids) and _norm(p.get("command", "")):
                extra += 1
    # …AND HOW MANY OF THEM THIS REPORT ACTUALLY ACCOUNTED FOR. `pinned_probes` is a property of
    # the CONTRACT; on its own it answers "how much procedure exists", never "how much was run" —
    # and it was being written identically on every door, including the one that records an
    # internal node's self-report, where nothing pinned runs at all (§10.3). A record that says
    # `pinned_probes: 2` over a closure that ran none is the false green this change exists to
    # remove, on the change's own surface. So the count of what RAN is stored beside it, computed
    # from the report, and the two can be compared by anyone reading the record.
    ran = 0
    for c in criteria or ():
        name = _norm(c.name)
        reported = set()
        for e in per_criterion or ():
            if _norm(e.get("criterion")) != name:
                continue
            reported |= _reported_ids(name, probes_of(e), dirs)
        ran += sum(1 for p in (c.check or ())
                   if _norm(p.command) and probe_id(c.name, p) in reported)
    return {"procedure_digest": procedure_digest(criteria),
            "pinned_probes": sum(len(v) for v in pinned.values()),
            "pinned_probes_run": ran,
            "criteria_with_procedure": sum(1 for v in pinned.values() if v),
            "criteria_total": len(pinned),
            "probes_beyond_the_procedure": extra,
            "named_beyond_the_procedure": named_beyond_procedure(criteria, per_criterion, dirs)}


def without_past_builds(regression: Mapping) -> dict[str, list[dict]]:
    """The regression set less the findings that run a past round's build (`runs_a_past_build`) — read so wherever the
    set is demanded, so one filed before this rule stops failing the node too."""
    return {c: kept for c, ps in (regression or {}).items()
            if (kept := [p for p in ps if not runs_a_past_build(str(p.get("as_run") or p.get("command") or ""))])}


#: what marks a probe that records an act of the SYSTEM's own over the delivery — its build, its copy — failed: the
#: delivery's FAIL with its cause, never a finding that stands (`refuting_probes`). The next delivery's own build and
#: copy are its re-check: kept, a failed `make` was demanded of a redelivery whose tree had no Makefile any more, and
#: only an issuer lifted it (critic over 909e417)
SYSTEMS_ACT = "systems_act"
#: on a probe the system marked `held: false` by running it itself, not by the report's word
SYSTEM_SAW = "system_saw"


def refuting_probes(per_criterion: Sequence[Mapping], dirs: Iterable[tuple[str, object]] = (),
                    texts: Mapping[str, str] | None = None) -> dict[str, list[dict]]:
    """{criterion: [the probes that REFUTED it this round]} — the regression set's new members, each with the text of
    the criterion it refuted as the run validated it (`texts`), which the issuer reads when he rules on it.

    What contact found is bought with the run (§9.9 verify-vs-explore), and dropping it after
    paying is what makes the next round pay again: the executor fixes what was named, the next
    validator writes its own probes, and the same defect walks back in unobserved.

    It is kept as the NODE's history, deliberately not folded into the criterion. The pinned
    procedure is the ISSUER's pre-registered claim (Inv-1, §12.14) and growing it silently at
    validation time would be the contract moving under the executor — the very thing pre-registration
    forbids; an issuer who wants a finding made permanent promotes it with `edit_criteria`, and
    `claim_drift` then shows the promotion. Only refuting probes enter: a passing exploration tells
    a later round nothing it must re-run.
    """
    out: dict[str, list[dict]] = {}
    for e in per_criterion or ():
        if spoken_verdict(e.get("verdict")) != "fail":
            continue
        name = _norm(e.get("criterion"))
        probes = probes_of(e)
        # …nor, beside a probe the entry says did not hold, one it says nothing of: the entry named its refutation, and its
        # own run that matched was filed as one, a shorthand of it standing six rounds (`cat-integrated#2bd5e0d5`,
        # GB_coreutils_tnyzqh948: the run printed vT-same, the report wrote a line that creates no file)
        # …the report's own word: the system's mark on a pin it ran (`with_engine_observations`) names nothing of the rest
        named = any(probe_held(p.get("held")) is False and not p.get(SYSTEM_SAW) for p in probes)
        # …never one the report says HELD (a part's pinned check), nor one of a split run that passed its share
        # (`share`, `validate._fold`); unmarked, a root FAIL with 1 refuting probe of 1,336 grew the store by hundreds a
        # round to 1,414 findings (GB_sql_database_tmxu0n436, 2026-10-15). An unsaid probe of the failing entry is
        # kept: the validator says `held` only of a part's pinned check, never of its own probes
        for p in probes:
            if (not _norm(p.get("command", "")) or probe_held(p.get("held")) is True or p.get("share") == "pass"
                    or p.get(SYSTEMS_ACT) or p.get(NOT_REFUTING) or (named and probe_held(p.get("held")) is None)
                    or (e.get(OVER_A_PASS) and not p.get(SYSTEM_SAW))):
                continue
            # …AS RUN, with this round's inputs directories NAMED rather than spelled: normalizing a multi-line
            # program onto one line left a command no shell runs, and the round's directory is gone the next round
            # — shown that way, the next validator ran its own version and nothing matched (automatic json_parser,
            # 2026-09-28: one pass refused three times). The id is over the named form, so a later round that runs
            # the line over its own directory matches it by command as well as by id.
            run = tokenized(str(p.get("command", "")), dirs)
            if runs_a_past_build(run):     # this round's inputs directories are named by now, never this
                continue
            cited = str(p.get("id", "")).strip()
            out.setdefault(name, []).append(
                {"id": finding_id(name, run), "behaviour": _norm(p.get("behaviour", "")) or "found by contact",
                 "command": _norm(run), "as_run": run, "seen": str(p.get("command", "")),
                 "cited": (cited if "#" in cited else f"{name}#{cited}") if cited else "",
                 "expect": _norm(p.get("expect", "")),
                 **({"refuted_text": texts[name]} if name in (texts or {}) else {})})
    return out


#: what a report's probe says of a standing finding it re-ran as filed: why it refutes no criterion, beside what it printed
NOT_REFUTING = "not_refuting"
#: …run as filed: from the directory it was asked to run in, and nothing else around it
_IN_A_DIRECTORY = re.compile(r"""^(?:cd (?:"[^"]*"|'[^']*'|\S+) && )+""")


def _in_any_directory(command) -> str:
    return _IN_A_DIRECTORY.sub("", _norm(command))


def plan_pins(plan: Mapping[str, Sequence[Criteria]]) -> list[tuple[str, Probe]]:
    """[(id, check)] of every check the plan runs ({criterion: criteria}; a check a ruling lifted is no longer in it)."""
    return [(probe_id(c.name, p), p) for cs in (plan or {}).values() for c in cs for p in c.check or () if _norm(p.command)]


def findings_not_reproduced(per_criterion: Sequence[Mapping], regression: Mapping, plan: Mapping[str, Sequence[Criteria]],
                            dirs: Iterable[tuple[str, object]] = ()) -> list[tuple[str, str, dict]]:
    """[(criterion, finding id, what the report said)] — each standing finding of a validator's own this report re-ran AS
    FILED, showed what it printed and said why it refutes no criterion. A finding is his claim about the work, not a
    criterion (§2.2, §12.8): it stands while the next independent run reproduces it. A check of the plan (`plan`:
    {criterion: criteria}), and a run the report says did not hold or did not run, is not such a finding."""
    pins = plan_pins(plan)
    out = []
    for e in per_criterion or ():
        name = _norm(e.get("criterion"))
        for f in (regression or {}).get(name, ()):
            if any(runs_pin(f, i, p) for i, p in pins):
                continue
            filed = _in_any_directory(f.get("as_run") or f.get("command"))
            for p in probes_of(e):
                if (p.get(NOT_REFUTING) and _norm(p.get("printed")) and p.get("ran") is not False
                        and probe_held(p.get("held")) is not False and f.get("id") in _reported_ids(name, [p], dirs)
                        and filed and filed == _in_any_directory(tokenized(str(p.get("command", "")), dirs))):
                    out.append((name, f["id"], {"why": str(p[NOT_REFUTING]), "printed": str(p["printed"])}))
                    break
    return out


def merge_regression(stored: Mapping, found: Mapping) -> dict[str, list[dict]]:
    """The node's regression set, grown by this round and never shrunk (dedup by probe id)."""
    out = {k: list(v) for k, v in (stored or {}).items()}
    for name, probes in (found or {}).items():
        have = {p.get("id") for p in out.get(name, ())}
        # …and a re-run of a standing finding — the report cites its id — under a reworded command is that finding,
        # standing already: filed under a fresh id, 605 of 1,467 entries were such re-runs, chains six deep
        # (GB_sql_database_tmxu0n436, 2026-10-15)
        held_ids = have | {str(i).split("#")[-1] for i in have}
        out.setdefault(name, []).extend(p for p in probes if p.get("id") not in have and not (
            p.get("cited") and (p["cited"] in held_ids or str(p["cited"]).split("#")[-1] in held_ids)))
    return out


def without_retired(regression: Mapping, retired: Iterable[Mapping]) -> dict[str, list[dict]]:
    """The regression set less the findings an issuer's ruling retired, each named by its criterion and id.

    A finding speaks to its CRITERION, and only the issuer's signature decides that criterion (§10.2: the check is the
    validator's, the signature the issuer's) — so only his ruling, naming it, retires it (`engine.findings`).
    Every proxy for that ruling misfired: keyed by node, root.pp carried 271 findings across rewrites of what they
    refuted (GB_c_compiler_tmp5cb096); keyed by the packet's version, a deadline extension erased them all; keyed by the
    criterion's text, an accepted challenge leaving the text as it was kept the disputed finding demanded and the node
    stuck, while one retyped full stop wiped an undisputed criterion's every finding (critics over f0584f3, ca228e0)."""
    gone = {(_norm(r.get("criterion")), r.get("id")) for r in retired or ()}
    return {k: kept for k, v in (regression or {}).items()
            if (kept := [p for p in v if (_norm(k), p.get("id")) not in gone])}


def without_pinned_runs(regression: Mapping, pinned: Mapping[str, str]) -> dict[str, list[dict]]:
    """The regression set less the RUNS OF PINNED PROBES — any the node's contract has carried, in force or since
    withdrawn. It holds the validator's OWN findings: a pinned probe in force is demanded every round anyway
    (`unrun_pinned`), and a run of it under a second id was a second demand no report could meet — one probe
    entry carries one id (automatic json_parser, 2026-09-28: one pass refused three times). A withdrawn one's
    refutation was, by the issuer's revision, of the probe and not of the artifact; kept, it failed the node on
    every later round and the accepted challenge came back in a loop."""
    return {k: [p for p in v if pinned_run(p, pinned or {}, k) is None] for k, v in (regression or {}).items()}


def pinned_run(p: Mapping, pinned: Mapping[str, str], criterion: str = "") -> str | None:
    """The id of the pinned probe `p` is a run of — its id, or its command with the probe's own directory named
    `{inputs}` — else None. Only a probe of the same criterion: another criterion's pinned probe with the same
    command is a different obligation, and its withdrawal says nothing about this one's finding."""
    mine = {w: c for w, c in pinned.items() if not criterion or w.split("#")[0] == _norm(criterion)}
    for key in ("id", "cited"):
        if p.get(key) in mine:
            return str(p[key])
    cmd = str(p.get("as_run") or p.get("command", ""))
    return next((w for w, c in mine.items()
                 if inputs_token(w) in cmd and _norm(cmd.replace(inputs_token(w), INPUTS_TOKEN)) == _norm(c)), None)


def same_expectation(said: str, pinned: str) -> bool:
    """Is `said` what `pinned` expects, whole or one whole line of it? A substring is not: `rc=1` in `rc=10`, `ok` in
    `not ok` (critic over 9c51566). A finding's expectation is stored on one line (`refuting_probes`), so several lines
    of a pin are compared only as all of them."""
    said = _norm(said)
    return bool(said) and (said == _norm(pinned) or said in {_norm(line) for line in str(pinned or "").splitlines()})


def runs_pin(finding: Mapping, pid: str, pin: Probe) -> bool:
    """Does this finding say only what pinned check `pin` (id `pid`) says — its command, over its own inputs directory,
    and the pin's expectation? The same command with an expectation of the validator's own, or none said, is his
    reading of the work, not the pin's."""
    return same_expectation(finding.get("expect"), pin.expect) and _norm(pin.command) == _norm(
        str(finding.get("as_run") or finding.get("command") or "").replace(inputs_token(pid), INPUTS_TOKEN))


def _pins_lifted(crits: Sequence[Criteria], ruled: Iterable[Mapping], keeps_own: bool) -> set[str]:
    """The ids of the pinned checks in `crits` that `ruled` run (each within what it says stood then, `then`, where said)
    and their copies — or none where the criterion, with no pin of its own (`keeps_own`), would keep no check at all."""
    pins = [(probe_id(c.name, p), p) for c in crits for p in c.check or () if _norm(p.command)]
    gone = {same_probe(p) for i, p in pins for r in ruled
            if runs_pin(r, i, p) and ("then" not in r or same_probe(p) in r["then"])}
    return {i for i, p in pins if same_probe(p) in gone} if keeps_own or any(same_probe(p) not in gone for _, p in pins) else set()


def _pinned_criteria(criteria: Iterable[Criteria]) -> set[str]:
    return {_norm(c.name) for c in criteria or () if any(_norm(p.command) for p in c.check or ())}


def pins_ruled_out(parts: Mapping[str, Sequence[Criteria]], rulings: Iterable[Mapping], own: Iterable[Criteria]) -> dict[str, set[str]]:
    """{criterion of the whole: the ids of its parts' pinned checks these rulings take off it} — ONE decision of what a
    ruling lifts: under the criterion it names only, and never a criterion's last check."""
    pinned = _pinned_criteria(own)
    out = {}
    for name, crits in (parts or {}).items():
        mine = [r for r in rulings or () if _norm(r.get("criterion")) == _norm(name)]
        if mine and (ids := _pins_lifted(crits, mine, _norm(name) in pinned)):
            out[name] = ids
    return out


def without_pins(parts: Mapping[str, Sequence[Criteria]], gone: Mapping[str, set]) -> dict:
    """`parts` less `gone` (`pins_ruled_out`). The part's own contract stays as it settled."""
    out = {}
    for name, crits in (parts or {}).items():
        kept = (replace(c, check=tuple(p for p in c.check or () if probe_id(c.name, p) not in gone.get(name, ()))) for c in crits)
        if left := tuple(c for c in kept if c.check):
            out[name] = left
    return out


def findings_a_ruling_could_lift(regression: Mapping, parts: Mapping[str, Sequence[Criteria]], own: Sequence[Criteria]) -> list[str]:
    """The ids of the findings in `regression` that only say a pinned check of a part THEIR criterion rests on does not
    hold, a check none of `own` pins, and whose ruling that criterion's last check would not hold back."""
    mine = [(probe_id(c.name, p), p) for c in own or () for p in c.check or () if _norm(p.command)]
    named = [{**f, "criterion": k} for k, fs in (regression or {}).items() for f in fs
             if not any(runs_pin(f, i, p) for i, p in mine)]
    lifted = pins_ruled_out(parts, named, own)
    pins = {name: [(i, p) for c in crits for p in c.check or () if (i := probe_id(c.name, p)) in lifted.get(name, ())]
            for name, crits in (parts or {}).items()}
    return [f["id"] for f in named for name, ps in pins.items()
            if _norm(name) == _norm(f["criterion"]) and any(runs_pin(f, i, p) for i, p in ps)]


def unrun_regression(regression: Mapping, per_criterion: Sequence[Mapping],
                     dirs: Iterable[tuple[str, object]] = (), layable: Iterable[str] | None = None,
                     delivery: str | Path | None = None, *, standing) -> dict[str, list[str]]:
    """{criterion: [ids of once-refuting probes this PASS did not re-run]}.

    A criterion that failed here before passes now only if the observation that refuted it was
    made again. Anything else is a pass over an untested repair.
    """
    verdicts, ran = _read_report(per_criterion, dirs)
    out: dict[str, list[str]] = {}
    for name, probes in (regression or {}).items():
        if verdicts.get(_norm(name)) != "pass":
            continue
        missing = [p["id"] for p in probes if p.get("id") not in ran.get(_norm(name), set())
                   and not unrerunnable(p, layable, delivery, standing=standing)]
        if missing:
            out[name] = missing
    return out


#: A word of a command that names a file by an absolute path — POSIX, or a Windows drive. A bare backslash begins no
#: path: `\n#endif` in a printf is an escape, and read as a rooted path it was "gone" on a Windows engine.
_ABSOLUTE = re.compile(r"^(?:/|[A-Za-z]:[\\/])")
#: The system tree every container of an execution carries (FHS): what a command reads there is the environment's.
_ENVIRONMENT = re.compile(r"^/(?:dev|proc|sys|usr|bin|sbin|lib|lib32|lib64|libx32|etc)(?:/|$)")


def unrerunnable(p: Mapping, layable: Iterable[str] | None, delivery: str | Path | None = None, *, standing) -> str:
    """Why a stored finding cannot be re-run as recorded — '' where it can. Such a finding is SHOWN, not demanded: a
    probe that cannot run decides nothing (A1 (i)), and demanding it holds the node `undecidable` whatever is repaired.

    Two ways. It reads the inputs of a probe the contract no longer pins: they are not laid down any more, as a finding
    orphaned by a rename. Or it names a file by an absolute path that is GONE here, now — neither it nor the directory
    it would sit in exists — outside the delivery's own tree, where a missing file is what the finding may be about:
    an earlier validation's pruned scratch (`root.pp_1791646628/dt/hh3.c`, GB_c_compiler_tmp5cb096). Read where the
    place holding it stands (`files_at`), when it is asked. A marker for "some validation's scratch" in its place made
    198 of that node's 271 findings advisory, most of them programs the validator wrote there that still stood and still
    ran (critic over f0584f3): a finding is demanded while it can run."""
    cmd = str(p.get("as_run") or p.get("command") or "")
    if layable is not None and set(re.findall(r"\{inputs:([^}]*)\}", cmd)) - set(layable):
        return "it reads the inputs of a probe the contract no longer pins"
    home = Path(str(delivery)).as_posix().rstrip("/") + "/" if delivery else None
    # a path under a pinned probe's inputs is laid down every round: never gone — cut whole, `{inputs:X}/tests/a.c`
    # left `/tests/a.c` behind, an absolute path that never existed
    gone = [w for w in re.split(r"[\s'\"=<>|;&()`]+", re.sub(r"\{inputs:[^}]*\}[^\s'\"=<>|;&()`]*", "", cmd))
            if _ABSOLUTE.match(w) and not (home and (Path(w).as_posix() + "/").startswith(home)) and _gone(w, standing)]
    return f"it names {', '.join(gone)}, which no longer exist here" if gone else ""


def _gone(path: str, standing) -> bool:
    """Is what `path` names gone? In a round, the round no longer standing and its content not in the system's record
    either (`standing`, asked of (the round's path, its name, `path`)) — kept as it makes and removes rounds and files
    findings, asked of no container; else neither it nor its directory there on this host: the
    base and what lies outside every place are this host's until the places and the base move into volumes. Under a
    system directory of the layout before each named its project, gone: no container mounts it, a re-run would not
    find it (`unprojected`)."""
    if unprojected(path):
        return True
    if (r := round_of(path)) is not None:
        return not standing((*r, path))
    # …the system tree of the environment a command runs in is never gone: asked of a Windows engine, `/dev/stdin` and
    # `/dev/null` did not exist, and a finding kept and laid whole went out raw to judge and executor alike — 429 of
    # one day's findings, c_compiler rows looping on lines no one could run (2026-10-30)
    if _ENVIRONMENT.match(Path(path).as_posix()):
        return False
    return not HOST.exists(path) and not HOST.exists(str(Path(path).parent))


def _cmd_key(command: str) -> str:
    """A command's identity whichever criterion it is reported under — the hash `probe_id` gives it."""
    return probe_id("", {"command": command}).split("#")[1]


def _cited_as(p: Mapping) -> str:
    return f"`{i}`" if (i := str(p.get("id", "")).strip()) else "its command"


def with_part_observations(parts: Mapping[str, Sequence[Criteria]], per_criterion: Sequence[Mapping]) -> list:
    """The report's entries, each part probe it observed written out in full where a criterion rests on it: a citation
    `{id, held}` — the form the validator's packet asks for — given the pinned command and expectation it names, and a
    criterion resting on a part probe another entry of the report observed given that observation. A criterion whose only
    procedure was a part probe carried by another run was refused for "no reproducible probe", and a validator invented
    one whose expectation then disagreed with the pinned one (finder over 190f4db; GB_sql_database_tn03ao788). An entry
    with nothing to write out is returned as it came."""
    pinned = {probe_id(c.name, p): p for cs in (parts or {}).values() for c in cs for p in (c.check or ()) if _norm(p.command)}
    if not pinned:
        return list(per_criterion or ())
    full = lambda q, pid: {**q, "command": pinned[pid].command, "expect": pinned[pid].expect,
                           "behaviour": q.get("behaviour") or pinned[pid].behaviour}
    cited = lambda q: str(q.get("id", "")).strip() in pinned and not _norm(q.get("command", ""))
    out = [{**e, "probe": [full(q, str(q["id"]).strip()) if cited(q) else q for q in probes_of(e)]}
           if any(cited(q) for q in probes_of(e)) else e for e in per_criterion or ()]
    # …never one the report says, anywhere and however cited, did not hold (one observation: `part_credit`)
    failed = {pid for e in out for q in probes_of(e) if probe_held(q.get("held")) is False
              for pid in pinned if str(q.get("id", "")).strip() in (pid, pid.split("#")[-1])}
    failed |= {pid for pid in pinned if same_probe(pinned[pid]) in {same_probe(pinned[x]) for x in failed}}
    seen = {str(q.get("id")): q for e in out for q in probes_of(e) if str(q.get("id", "")) in pinned
            and str(q.get("id")) not in failed and _norm(q.get("command", "")) and probe_held(q.get("held")) is True}
    lent = []
    for e in out:
        rests = [probe_id(c.name, p) for c in (parts or {}).get(str(e.get("criterion")), ()) for p in (c.check or ())]
        got = [seen[i] for i in rests if i in seen]
        if got and not probes_of(e):     # lent only to an entry that cites nothing itself
            e = {**e, "probe": got}
        # …and what such a probe observes is the behaviour the entry names, where it named none
        if not [b for b in (e.get("behaviours") or ()) if str(b).strip()] and                 (named := [q["behaviour"] for q in probes_of(e) if str(q.get("id", "")) in pinned and q.get("behaviour")]):
            e = {**e, "behaviours": named}
        lent.append(e)
    return lent


#: …and whether every one of them had its WHOLE bound (no budget cutting it): then the same tree times out again, and
#: asking the validation again only pays for the same ⊥ (`BOUND_SPENT`, the dispatcher's `no-verdict:bound`)
PAST_WHOLE = "past_bound_whole"
#: a shell's exit when the command could not be run at all — not found, not executable: no observation of the delivery
NOT_RUN_RC = (126, 127)
#: said in a refusal whose every unobserved criterion is PAST_WHOLE — read by the dispatcher, which stops re-asking
BOUND_SPENT = ("NOT ASKED AGAIN: every unobserved check ran past all it could be given on this delivered tree — its own bound, or "
               "the validation's whole budget where that is shorter —, which would "
               "time out again — VALIDATING's bound hands the node to its issuer (§12.2), who may state the bound the "
               f"check needs (its `bound_s`, the default {PROBE_S} s with its build, at most the validation's own bound), "
               "re-pin it to finish inside its bound, or cancel")


def with_engine_observations(per_criterion: Sequence[Mapping], criteria: Sequence[Criteria],
                             parts: Mapping[str, Sequence[Criteria]] | None, observed: Mapping | None,
                             edited: Sequence[str] = ()) -> list:
    """The report with what the system itself observed of its pinned probes (`observed`: {probe id: {matched,
    out, note}}, `validate._observe_pins`) put where every reader of `held` reads it: a probe it saw print other than
    its `expect` did NOT hold — each citation of it, by id or bare hash, says `held: false`, and every entry of a
    criterion resting on it or on a copy of it (`same_probe`), the node's own or through a part, is a `fail` citing it
    with what it printed (Inv-2, §12.8: an observed divergence is that criterion's fail; Inv-3). Matched, the report
    stands as it came; not run (a row with a `note` and no `matched`), the entries resting on it stand too, their
    evidence saying the system did not observe it — a run the system could not make decides nothing (A1 (i)), and the
    `held` there is visibly the validator's word. A `held: false` is never raised. Before it the PASS on such a probe
    was the validator's word alone, and FM-3 has no structural guard (§9.10) — a false FAIL costs a round, a false PASS
    closes a node. A pin not `exact` the system saw print no part of its `expect`: `_reproduced`. `edited`: the delivered
    files the judge changed in its copy beyond what the pinned checks change — a PASS the system's run does not decide
    is then ⊥."""
    pinned = {probe_id(c.name, p): p for cs in [criteria or ()] + list((parts or {}).values()) for c in cs
              for p in (c.check or ()) if _norm(p.command)}
    seen = {pid: o for pid, o in (observed or {}).items() if pid in pinned}
    def _the_reports(e: Mapping) -> dict:    # …the system's marks alone: a report cannot ⊥ its own FAIL, nor speak as the system
        e = {k: v for k, v in e.items() if k not in (PAST_BOUND, PAST_WHOLE, UNDER_THE_DEFAULT, OVER_A_PASS, ON_NO_DELIVERY)}
        return {**e, "probe": [{k: v for k, v in q.items() if k != SYSTEM_SAW} for q in probes_of(e)]} if probes_of(e) else e

    def _copies(seen: dict) -> dict:   # every id one observation is of (`same_probe`)
        seen_as = {same_probe(pinned[pid]): o for pid, o in seen.items()}
        return {pid: seen_as[same_probe(p)] for pid, p in pinned.items() if same_probe(p) in seen_as}
    # …an exact pin that printed otherwise, or any pin whose shell said the program it names in the delivery is not there:
    # the delivery's FAIL. A pin not exact that printed some text but no part of what it pins holds a pass only on what
    # the report cites it printing (`_reproduced`); one that printed nothing, or whose bare-named program the shell did
    # not find, observed nothing a substring decides — the validator's word, as before (A1 (i))
    off = _copies({pid: o for pid, o in seen.items() if o.get("matched") is False
                   and (pinned[pid].exact or delivery_lacks(o))})
    unshown = {pid: o for pid, o in _copies({pid: o for pid, o in seen.items() if not pinned[pid].exact
                                              and o.get("matched") is False and o.get("rc") not in NOT_RUN_RC
                                              and str(o.get("printed") or "").strip()}).items() if pid not in off}
    unseen = {pid: o for pid, o in _copies({pid: o for pid, o in seen.items() if "matched" not in o}).items()
              if pid not in off and "matched" not in seen.get(pid, {})}
    if not (off or unshown or unseen or edited):
        return [_the_reports(e) for e in per_criterion or ()]
    decided = {pid for pid, o in _copies(seen).items() if o.get("matched") is True} | set(off) | set(unshown)
    rests: dict[str, list[str]] = {}
    for k, cs in [*((c.name, (c,)) for c in criteria or ()), *(parts or {}).items()]:
        rests.setdefault(_norm(k), []).extend(probe_id(c.name, p) for c in cs for p in (c.check or ()))
    named = lambda q: next((pid for pid in off if str(q.get("id", "")).strip() in (pid, pid.split("#")[-1])), None)
    out = []
    for e in per_criterion or ():
        e = _the_reports(e)
        probes = [{**q, "held": False, SYSTEM_SAW: True} if named(q) else q for q in probes_of(e)]
        on = list(dict.fromkeys(rests.get(_norm(e.get("criterion")), ())))
        if hit := [pid for pid in on if pid in off]:
            why = [f"the system ran pinned check {pid} itself and it printed {off[pid].get('out', '')!r}, not "
                   f"{'the whole output' if pinned[pid].exact else 'what'} it pins, {pinned[pid].expect!r}" for pid in hit]
            cited = {named(q) for q in probes}
            e = {**e, **({OVER_A_PASS: True} if spoken_verdict(e.get("verdict")) != "fail" else {}), "verdict": "fail", "evidence": " | ".join(why + [str(e["evidence"])] if e.get("evidence") else why),
                 "divergences": [*why, *(e.get("divergences") or ())],
                 "probe": probes + [{"id": pid, "behaviour": pinned[pid].behaviour, "command": pinned[pid].command,
                                     "expect": pinned[pid].expect, "held": False, SYSTEM_SAW: True} for pid in hit if pid not in cited]}
        elif (late := [pid for pid in on if unseen.get(pid, {}).get("timed_out")]) and not (
                spoken_verdict(e.get("verdict")) == "fail" and str(e.get("evidence", "")).strip()):
            # …a check that ran past its own bound decided nothing (A1 (i)): ⊥, and no PASS over it (Inv-2) — read as
            # the validator's word, a looping delivery hid from the system's FAIL (security's critic, 2026-10-31). It
            # only LOWERS a pass: a FAIL the validator showed with evidence is a decision this absence does not undo
            why = [f"the system ran {'exact ' * pinned[pid].exact}pinned check {pid} itself and it "
                   f"{unseen[pid].get('note')}: undecided" for pid in late]
            e = {**e, "verdict": "undecidable", "probe": probes, PAST_BOUND: late,
                 PAST_WHOLE: all(unseen[pid].get("whole") for pid in late),
                 **({UNDER_THE_DEFAULT: d} if (d := [pid for pid in late if unseen[pid].get("bound_supplied")]) else {}),
                 "evidence": " | ".join(why + [str(e["evidence"])] if e.get("evidence") else why)}
        else:
            if probes:
                e = {**e, "probe": probes}
            if blind := [f"the system did not run {'exact ' * pinned[pid].exact}pinned check {pid} itself "
                         f"({unseen[pid].get('note')}): its holding is the validator's word" for pid in on if pid in unseen]:
                e = {**e, "evidence": " | ".join([str(e["evidence"])] + blind if e.get("evidence") else blind)}
        e = _reproduced(e, [pid for pid in on if pid in unshown], unshown, pinned)
        # …and where the judge changed a delivered file in its copy, its PASS stands only where the system's own run
        # decided the criterion: what it observed beyond that was observed on no delivered tree
        if edited and spoken_verdict(e.get("verdict")) == "pass" and not (on and set(on) <= decided):
            e = _on_no_delivery(e, [f"the validator changed delivered file(s) in its copy that no pinned check changes "
                                    f"when the system runs it ({', '.join(edited)}), and the system's own run of the "
                                    f"pinned checks does not decide this criterion: the instrument's defect, not the "
                                    f"executor's — undecided"])
        out.append(e)
    return out


def _reproduced(e: dict, unshown: list, seen: Mapping, pinned: Mapping) -> dict:
    """`e`, or — where it passes over pins (`unshown`, not `exact`) the system's run on the delivery printed no part of
    (`seen`) — ⊥ for its criterion (`ON_NO_DELIVERY`): a pass whose cited `expect` that same run does not show either was
    observed on no delivered tree — a judge's copy it changed, state an earlier probe of its left. Not a FAIL: an
    `expect` in words shows in no output, and the judge reads it over the system's run."""
    if spoken_verdict(e.get("verdict")) != "pass":
        return e
    cites = lambda q, pid: (str(q.get("id", "")).strip() in (pid, pid.split("#")[-1])
                            or _norm(q.get("command")) == _norm(pinned[pid].command))
    gone = [pid for pid in unshown if not any(cites(q, pid) and contains(seen[pid].get("printed", ""), q.get("expect"))
                                              for q in probes_of(e))]
    return e if not gone else _on_no_delivery(e, [
        f"the system ran pinned check {pid} on the delivery and it printed {seen[pid].get('out', '')!r}, which shows "
        f"neither {pinned[pid].expect!r} nor what the report cites it printing: undecided" for pid in gone])


def _on_no_delivery(e: dict, why: list) -> dict:
    """`e` as ⊥ for its criterion, `why` its reasons (`ON_NO_DELIVERY`): a pass observed on no delivered tree."""
    return {**e, "verdict": "undecidable", ON_NO_DELIVERY: why,
            "evidence": " | ".join(why + [str(e["evidence"])] if e.get("evidence") else why)}


#: a shell's word that a program a check names by a path — in the delivery, not rooted — is not there or will not run
_LACKS = re.compile(r"(?:^|[\s:])(?!/)[^\s:/]*/[^\s:]*: (?:No such file or directory|Permission denied)", re.M)


def delivery_lacks(o: Mapping) -> bool:
    """Did a check's 126/127 come from the delivery lacking the program it names by a path (`./prog`)? — its FAIL, as an
    exact pin's. A bare name the shell did not find (`check: command not found`) observed nothing of the delivery."""
    return o.get("rc") in NOT_RUN_RC and bool(_LACKS.search(str(o.get("printed") or "")))


def _citable(known: Mapping) -> tuple[dict, dict, dict]:
    """The ways a citation names a pinned probe — by bare hash, by command over its own inputs directory — and each
    probe's copies (`same_probe`), over every probe a report may cite."""
    by_hash: dict[str, set[str]] = {}
    by_cmd: dict[str, set[str]] = {}
    copies: dict[tuple, set[str]] = {}
    for pid, (c, p) in known.items():
        copies.setdefault(same_probe(p), set()).add(pid)
        by_hash.setdefault(pid.split("#")[-1], set()).add(pid)
        by_cmd.setdefault(_cmd_key(p.command.replace(INPUTS_TOKEN, inputs_token(pid))), set()).add(pid)
    return by_hash, by_cmd, copies


def _named_by(p: Mapping, known: Mapping, by_hash: Mapping, by_cmd: Mapping, dirs: tuple) -> tuple[set, set]:
    """(every probe a citation could mean, the ones it names): its full id names one; else hash and command together."""
    i, cmd = str(p.get("id", "")).strip(), str(p.get("command", ""))
    h = set() if "#" in i else by_hash.get(i, set())
    m = {x for k in {_cmd_key(cmd), _cmd_key(tokenized(cmd, dirs))} for x in by_cmd.get(k, ())} if _norm(cmd) else set()
    return h | m, {i} if i in known else (h & m) or (h | m)


def part_credit(parts: Mapping[str, Sequence[Criteria]], per_criterion: Sequence[Mapping],
                dirs: Iterable[tuple[str, object]] = (), own: Sequence[Criteria] = ()) -> tuple[set[str], dict[str, list[str]]]:
    """(the parts' pinned probes this report shows holding, {demanded part probe it cannot credit: why}) — `_part_reading`."""
    return _part_reading(parts, per_criterion, dirs, own)[:2]


def _part_reading(parts: Mapping[str, Sequence[Criteria]], per_criterion: Sequence[Mapping],
                  dirs: Iterable[tuple[str, object]] = (), own: Sequence[Criteria] = ()) -> tuple[set, dict, set]:
    """(the parts' pinned probes this report shows holding over the delivery, {demanded part probe it names but cannot
    credit: why}, the ones it shows not holding) — THE one reading of a part probe's credit: "was it run"
    (`unrun_parts`), "was it shown holding" (`parts_not_shown_holding`), the refusal's words (`unaccounted_for`) and
    what an unmap's record says of its part (`parts_read`) all read this.

    ONE OBSERVATION, HOWEVER IT IS CITED: a part's probe — its command, its expectation, this delivery — is one fact
    whichever criterion of the whole rests on it. A citation names it by its full id, by a bare hash only it has, or by
    its exact command (over its own inputs directory); one naming two demanded probes — two parts', or the whole's own
    and a part's — names neither. Named with `held: true` anywhere, or with no `held` under a criterion the report
    passes that rests on it, and nowhere reported `held: false` nor cited without `held: true` under a criterion it does not pass, it was
    observed holding for every criterion that rests on it. Credited across criteria only by full id with `held: true`,
    the c_compiler root (GB_c_compiler_tmqn88552) had 17 reports refused, four of which ran every part probe and cited
    each once by bare hash or command — and the refusal said they "were not run"."""
    demanded = {probe_id(c.name, p): (c, p) for cs in (parts or {}).values() for c in cs for p in (c.check or ())
                if _norm(p.command)}
    known = {**{probe_id(c.name, p): (c, p) for c in own or () for p in (c.check or ()) if _norm(p.command)}, **demanded}
    by_hash, by_cmd, copies = _citable(known)
    dirs = tuple(dirs or ())
    # which part probes each criterion of the whole RESTS on: a passed criterion vouches, without `held`, only for those —
    # a command met under an unrelated criterion that passes (its own exploration, "3 failed") is no observation of it
    # …and on its OWN pinned probes: cited there it is their run (`unrun_pinned`), so of every copy of them a part carries
    # — which the packet no longer lists again (critic over the probe identity, 2026-10-27)
    rests: dict[str, set[str]] = {}
    for k, cs in [*(parts or {}).items(), *((c.name, (c,)) for c in own or ())]:
        rests.setdefault(_norm(k), set()).update(probe_id(c.name, p) for c in cs for p in (c.check or ()) if _norm(p.command))
    good: set[str] = set()
    bad: set[str] = set()
    why: dict[str, list[str]] = {}
    for e in per_criterion or ():
        name, verdict = _norm(e.get("criterion")), spoken_verdict(e.get("verdict"))
        for p in probes_of(e):
            cand, named = _named_by(p, known, by_hash, by_cmd, dirs)
            if len({same_probe(known[x][1]) for x in named}) > 1:
                for pid in named & set(demanded):
                    why.setdefault(pid, []).append(f"cited by {_cited_as(p)} under '{name}', which names {len(named)} "
                                                   f"demanded probes ({', '.join(sorted(named))}) — cite it by its full id")
                continue
            # …one observation, cited by any of its ids, is each copy's: SHOWN HOLDING it holds for each (the sql root,
            # 2026-10-27: six of seven validations ⊥ on one sound delivery, a twin cited by its copy's full id read as
            # "not run"), reported NOT holding it voids each (a contradiction errs to a false FAIL — replay mutation,
            # 2026-10-27); cited short of either it speaks only of the id it names (critic r3, 2026-10-26)
            each = set().union(*(copies[same_probe(known[x][1])] for x in named))
            for pid in (cand - each) & set(demanded):
                why.setdefault(pid, []).append(f"its hash or command, cited under '{name}', was read as {', '.join(named)} "
                                               "— cite this one by its own full id")
            if not each & set(demanded):
                continue
            held = probe_held(p.get("held"))
            if held is True or (held is None and verdict == "pass" and each & rests.get(name, set())):
                good |= each & set(demanded)
                continue
            if held is False:                                # one observation said failing: no copy of it holds
                named = each
            for pid in named & set(demanded):
                if held is None and verdict == "pass":
                    why.setdefault(pid, []).append(f"cited by {_cited_as(p)} under '{name}', which does not rest on it, "
                                                   "without `held: true` — say whether it held")
                    continue
                bad.add(pid)
                why.setdefault(pid, []).append(
                    f"reported `held: false` under '{name}' — it did not hold, and every criterion resting on it fails"
                    if held is False else f"cited by {_cited_as(p)} under '{name}', which the report does not pass, "
                                          "without `held: true` — say whether it held")
    credited = good - bad
    return credited, {pid: w for pid, w in why.items() if pid not in credited}, bad


def parts_read(parts: Mapping[str, Sequence[Criteria]], per_criterion: Sequence[Mapping],
               dirs: Iterable[tuple[str, object]] = (), own: Sequence[Criteria] = (),
               beside: Mapping[str, Sequence[Criteria]] | None = None) -> dict[str, str]:
    """{part probe the report speaks of: `held` | `failing`} — `part_credit`'s own reading kept with the record: shown
    holding; or reported not holding under any criterion, cited under one it fails without `held: true`, or — a probe
    of `parts`, the demanded procedure — not shown holding under a criterion it fails that rests on it
    (`parts_not_shown_holding`'s reading). `beside`: probes no longer demanded (an unmapped settled part's) read only as
    the report cites them: a run that began before their unmap may still speak of them. Read when the verdict is
    recorded, over that round's inputs directories, which a later reader no longer has."""
    # …under a key no criterion bears: a criterion's pass vouches only for the probes resting on it
    read = {**(parts or {}), **{f"(no longer demanded under {n})": cs for n, cs in (beside or {}).items()}}
    credited, _, bad = _part_reading(read, per_criterion, dirs, own)
    failed = {_norm(e.get("criterion")) for e in per_criterion or () if spoken_verdict(e.get("verdict")) == "fail"}
    unshown = {probe_id(c.name, p) for n, cs in (parts or {}).items() if _norm(n) in failed
               for c in cs for p in (c.check or ()) if _norm(p.command)} - credited
    return {**{p: "held" for p in credited}, **{p: "failing" for p in bad | unshown}}


def unrun_parts(parts: Mapping[str, Sequence[Criteria]], per_criterion: Sequence[Mapping],
                dirs: Iterable[tuple[str, object]] = (), own: Sequence[Criteria] = ()) -> dict[str, list[str]]:
    """{criterion of the whole: [its parts' pinned probe ids this PASS did not show holding]} — over PASSED criteria only.

    A whole's result is its subtree's artifact as it stands when the WHOLE is delivered (§11.3); a part's PASS
    is a verdict on the part's own, earlier delivery (§10.2) and silent about the part as it stands inside this
    one — which another session may have rewritten since (E3, 2026-09-28: the whole's executor rewrote a passed
    part's module, the whole's check read only the whole's criteria, and the root closed DONE over four held-out
    failures). The parts' criteria are what secure the whole's criteria mapped to them (§2.4, §4.3), so on the
    whole's result the procedure deciding such a criterion includes the part's pinned one, credited once for every
    criterion resting on it (`part_credit`)."""
    verdicts, _ = _read_report(per_criterion, dirs)
    credited, _ = part_credit(parts, per_criterion, dirs, own)
    out: dict[str, list[str]] = {}
    for name, crits in (parts or {}).items():
        if verdicts.get(_norm(name)) != "pass":
            continue
        if missing := [pid for c in crits for p in (c.check or ())
                       if _norm(p.command) and (pid := probe_id(c.name, p)) not in credited]:
            out[name] = missing
    return out


def parts_not_shown_holding(parts: Mapping[str, Sequence[Criteria]], per_criterion: Sequence[Mapping],
                            dirs: Iterable[tuple[str, object]] = (), own: Sequence[Criteria] = ()) -> dict[str, list[str]]:
    """{criterion of the whole the report FAILED: [the direct parts demanded under it that it did not show holding]}.

    "Every mapped child passes while the parent fails" is the pattern a refuted split leaves (§15.4 q_D, §8.5) — and
    since a whole's validation reads its parts on the WHOLE's delivered result, a child passes there only as far as
    the report shows its demanded probes holding (`part_credit`). A part it did not show holding — reported failing,
    or cited under a failing criterion without `held: true`, as a hand record cannot say it — has no recorded value of
    the delivered work (§8.4): the FAIL may be the whole's delivery breaking it, which its executor repairs, and a
    refusal resting on the pattern would ask him for an untrue revision of a sound split (§12.16 (ii); critic r2,
    2026-10-04). Read when the verdict is recorded, with that round's inputs directories, and stored with it."""
    credited, _ = part_credit(parts, per_criterion, dirs, own)
    out: dict[str, list[str]] = {}
    for e in per_criterion or ():
        name = _norm(e.get("criterion"))
        if spoken_verdict(e.get("verdict")) != "fail":
            continue
        crits = next((cs for n, cs in (parts or {}).items() if _norm(n) == name), ())
        if left := sorted({c.name.split("/", 1)[0] for c in crits for p in (c.check or ())
                           if _norm(p.command) and probe_id(c.name, p) not in credited}):
            out[name] = left
    return out


def unaccounted_for(task, per_criterion: Sequence[Mapping], by_hand: bool, validator_id,
                    regression: Mapping, internal: bool = False,
                    dirs: Iterable[tuple[str, object]] = (),
                    parts: Mapping[str, Sequence[Criteria]] | None = None,
                    delivery: str | Path | None = None, *, standing) -> dict[str, list[str]]:
    """{criterion: [what this report did not account for]} — ONE owner for that question.

    Four sources, one answer: the behaviours the report itself named and did not probe
    (`underprobed`), the procedure the CONTRACT pinned and the report skipped, the probes that
    already REFUTED this node once, and the pinned procedure of every part `parts` names under the
    criterion it is mapped to (`unrun_parts`). They are ways of saying the same thing — a conjunct
    nobody observed cannot carry a pass (§2.3) — and they lived as appended blocks inside a
    verdict recorder that had grown past the size the suite's FORM ratchet holds at zero. That
    ratchet is not decoration: a rule appended to a long function is a rule nobody finds later.

    The one exemption is the canon's own degenerate case: on an INTERNAL node (its Del is its
    parent's) §10.3 has the executor self-verify, and the guarantee is the validation of the
    public result ABOVE it. There is no seam, so there is no independent party whose procedure this
    would be — and demanding it there froze every internal node in VALIDATING, which is the worse
    defect. The demand stands wherever the verdict is somebody else's: every seam, every instrument.
    """
    # …the behaviours named beyond a pinned procedure the report ran whole are exploration, not gaps — unless the
    # criterion falls short on another count below, where the refusal names everything it is short of, as before
    stood = named_beyond_procedure(task.spec.criteria, per_criterion, dirs) if task is not None else {}
    gaps = underprobed(per_criterion)
    # …and an exact check the SYSTEM ran and left unfinished in the time it was given (`with_engine_observations`): it
    # decided nothing in finite time (A1 (i)), whoever validates — no PASS over it, and no FAIL either: an honest slow
    # check is no defect of the work (the first form landed it in `failed_criteria` and reworked honest work)
    for e in per_criterion or ():
        if e.get(PAST_BOUND):
            gaps.setdefault(str(e.get("criterion")), []).append(
                f"the system ran its pinned check(s) {', '.join(map(str, e[PAST_BOUND]))} and they did not finish within "
                f"the time they were given — undecided"
                + (f"; {', '.join(map(str, d))} under the system's default bound, {PROBE_S} s, their issuer having "
                   f"stated none (`bound_s`)" if (d := e.get(UNDER_THE_DEFAULT)) else ""))
        if e.get(ON_NO_DELIVERY):     # …nor a pass observed on no delivered tree: the same ⊥, the report's to redo
            gaps.setdefault(str(e.get("criterion")), []).extend(map(str, e[ON_NO_DELIVERY]))
    # The internal-node exemption (§10.3) is narrowed to the case that HAS it: §10.3 lets an INTERNAL node
    # self-verify; at a seam independence is owed and a self-validation is not a verdict at all. The
    # caller guarantees that upstream today, and the repo's own recurring class is a rule that
    # holds at one door and not at the next — so it is checked here, where the rule lives.
    if task is None or (bool(by_hand) and internal and is_its_executor(task, validator_id)):
        return {c: b for c, b in gaps.items() if b != stood.get(c)}
    for name, ids in unrun_pinned(task.spec.criteria, per_criterion, dirs).items():
        gaps.setdefault(name, []).append(
            "the procedure this criterion PINS was not run: " + ", ".join(ids)
            + " — the contract fixed these before the work (Inv-1, §12.3); a pass that skips them "
              "is a pass on a procedure invented at validation time")
    # What contact already found here was paid for with a round (§9.9). Re-running it is what makes
    # a repair CHECKED rather than asserted: the loop this closes is the executor fixing what was
    # named while the next validator writes fresh probes and never looks there again.
    layable = layable_over(task.spec.criteria, parts)
    for name, ids in unrun_regression(regression, per_criterion, dirs, layable, delivery, standing=standing).items():
        gaps.setdefault(name, []).append(
            "a probe that REFUTED this criterion in an earlier round was not re-run: "
            + ", ".join(ids)
            + " — a pass over a repair nobody re-observed is not a verdict on the repair")
    # …SAID AS IT IS: a probe the report names but cannot be credited with is not a probe "not run" — told so, the
    # validator re-read every probe and dropped a different subset each round (GB_c_compiler_tmqn88552)
    _, why = part_credit(parts, per_criterion, dirs, task.spec.criteria)
    for name, ids in unrun_parts(parts, per_criterion, dirs, own=task.spec.criteria).items():
        if unseen := [i for i in ids if i not in why]:
            gaps.setdefault(name, []).append(
                "the pinned procedure of a part this criterion rests on was not run over this delivery — nothing of "
                "it (its id, its hash or its command) appears in the report: " + ", ".join(unseen)
                + " — the part passed on its own earlier delivery; its result as it stands inside this one "
                  "is what this criterion decides (§11.3, §4.3)")
        if cited := [i for i in ids if i in why]:
            gaps.setdefault(name, []).append(
                "the pinned procedure of a part this criterion rests on appears in the report but cannot be credited: "
                + "; ".join(f"{i} — {' and '.join(dict.fromkeys(why[i]))}" for i in cited)
                + " — one citation serves every criterion resting on it when it names that probe alone (its full "
                  "id, a hash or a command no other demanded probe has) with `held: true`, or without `held` under a "
                  "criterion the report passes")
    return {c: b for c, b in gaps.items() if b != stood.get(c)}
