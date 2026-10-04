"""The pinned decision procedure: its identity, its digest, and what it is to have RUN it.

Why this module exists at all. A criterion is typed as a decidable predicate (§2.2, A1), but a text
like "for ANY accepted program the output matches gcc" decides nothing on its own — the domain is
infinite. What used to close the gap was the VALIDATOR: it invented a probe set at validation time, a
different one each round, and the engine asked only that every behaviour the validator ITSELF had
named carry a probe (`invariants.underprobed`). So a PASS said "the validator checked what the validator
felt like checking", and the one number the canon makes non-negotiable — when the graph says PASS,
the promise was executed — could not be read off the graph at all. Measured on `c_compiler`
(2026-09-19/20): a root closed PASS by an independent validator, and a 205-probe corpus written from
the same contract found 34 real divergences inside that closed tree.

The procedure is therefore part of the criterion, authored with it and before execution
(pre-registration is Inv-1's, §12.14 — criteria are fixed at ASSIGN and no change is silent), and
the residue is stated rather than closed: behaviour outside P is unchecked — the FM-3 boundary
(Ch. 8), which no structural check guards and this one does not pretend to.
"""
from __future__ import annotations

import ast
import hashlib
import re
import sys
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Optional, Sequence

from gfso.core.types import Criteria, Probe
from gfso.core.protocol.invariants import emits_a_constant, probe_held, probes_of, spoken_verdict, underprobed


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def probe_id(criterion_name: str, probe: Probe | Mapping) -> str:
    """The stable name of one pinned probe: `<criterion>#<8 hex over the command it pins>`.

    The identity is the COMMAND, not the position: a procedure that gains a probe must not rename
    the ones already there, or a report naming what it ran would stop matching what was pinned the
    round before — and the growth of the regression set is the point (§9.9 / the append rule).
    """
    probe = Probe.of(probe)
    # THE COMMAND ALONE, deliberately — the inputs move the procedure's DIGEST, not the probe's
    # NAME. A report is matched to a pinned probe by its id AND, when it spells none, by its command
    # (the schema tells the validator so in as many words), and a report carries no `inputs` — so
    # seeding the id with them broke the fallback for exactly the probes that carry a corpus: an
    # honest validator that ran what the packet told it to run had its PASS demoted to `undecidable`,
    # its probe counted as unrun AND counted again as exploration beyond the procedure. Measured by
    # an outside reviewer; the repo's own history says what that bookkeeping costs — 140 of 151
    # useless reports failed on it.
    # …AND NOT THE VALIDATION ROUND: a validator's own file sits in that round's scratch (`<task>_<epoch>`, beside the
    # delivery — tools_llm `_validation_place`), so one probe filed in four rounds was four findings, each to be re-run
    # and each to be ruled on apart (p_wide.c on root.pp, GB_c_compiler_tmp5cb096)
    seed = _ROUND.sub(r"\1{round}", _norm(probe.command)) or _norm(probe.behaviour)
    return f"{_norm(criterion_name)}#{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:8]}"


#: The round of a validation's scratch in a path: `.gfso-scratch-<delivery>/<task>_<epoch>/`.
_ROUND = re.compile(r"(\.gfso-scratch-[^/\\\s'\"]+[/\\][^/\\\s'\"]*?_)\d+(?=[/\\])")
#: What separates the words of a command that may each be a path.
_WORD = re.compile(r"[\s'\"=<>|;&()`]+")


def finding_id(criterion_name: str, command: str) -> str:
    """The id of a validator's finding as it is FILED — when the files its command names in its round's scratch still
    stand, the validator having just run it. The same probe is the same command over the same files: the round is
    folded out of the id only together with the CONTENT of every scratch file it names, so one program filed in four
    rounds is one finding, and two programs a validator gave one name (`t.c`) in two rounds are two. Where a named
    scratch file is not there to read, the round stays in the id — distinct, never merged with another. A command that
    names no scratch file is identified as `probe_id` identifies it.

    Folding the round alone, a `t.c` testing macros — inside the criterion — took the id of an earlier `t.c` testing
    wide characters that its issuer had ruled outside it, and its FAIL was refused as that ruling's subject (critic over
    3982699): a refutation lost by a name."""
    cmd = _norm(command)
    named = [w for w in _WORD.split(cmd) if _ROUND.search(w)]
    if not named:
        return probe_id(criterion_name, {"command": command})
    digests = [_content(Path(w)) for w in named]
    seed = cmd if None in digests else _ROUND.sub(r"\1{round}", cmd) + "\x00" + "\x00".join(digests)
    return f"{_norm(criterion_name)}#{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:8]}"


def _content(path: Path) -> str | None:
    """A digest of what stands at `path` — a file's bytes, or a directory's files by their place in it — or None."""
    try:
        if path.is_file():
            return hashlib.sha256(path.read_bytes()).hexdigest()
        if path.is_dir():
            h = hashlib.sha256()
            for f in sorted(x for x in path.rglob("*") if x.is_file()):
                h.update(f.relative_to(path).as_posix().encode("utf-8") + b"\x00" + f.read_bytes() + b"\x00")
            return h.hexdigest()
    except OSError:
        return None                       # unreadable is not there to read: the round stays in the id
    return None


def inputs_digest(probe: Probe) -> str:
    """'' for a probe that carries no files, so every id and digest pinned before inputs existed stays."""
    if not probe.inputs:
        return ""
    h = hashlib.sha256()
    for path, body in sorted(probe.inputs):
        h.update(b"\x04" + path.encode("utf-8") + b"\x05" + body.encode("utf-8"))
    return h.hexdigest()[:16]


def probes_from(criterion: Mapping) -> tuple[Probe, ...]:
    """The pinned procedure as an authoring door hands it over: `{"check": [{behaviour, command,
    expect}]}`. One reader for every door — the decomposer, the agent door and the HTTP door each
    parse a criterion, and a key one of them silently ignores is a contract that arrives without
    its procedure and gates nothing."""
    raw = (criterion or {}).get("check") or ()
    if isinstance(raw, Mapping):
        raw = [raw]
    return tuple(Probe.of(p) for p in raw if isinstance(p, (Probe, Mapping)))


def pinned_probes(criteria: Iterable[Criteria]) -> dict[str, list[dict]]:
    """{criterion name: [{id, behaviour, command, expect}]} — the procedure as the contract pins it."""
    out: dict[str, list[dict]] = {}
    for c in criteria or ():
        out[c.name] = [dict(p.to_dict(), id=probe_id(c.name, p)) for p in (c.check or ())]
    return out


def procedure_digest(criteria: Iterable[Criteria]) -> str:
    """A 16-hex digest over every pinned probe of a contract, criterion by criterion.

    Recorded with a PASS so the verdict names WHAT was run, not only that something was. It is a
    pure function of the spec, so the audit log's stored spec of every ASSIGN reproduces it — no
    second copy of the contract has to be kept in step with the first.
    """
    h = hashlib.sha256()
    for c in sorted(criteria or (), key=lambda x: _norm(x.name)):
        h.update(b"\x00" + _norm(c.name).encode("utf-8"))
        for p in sorted(c.check or (), key=lambda p: (_norm(p.command), _norm(p.behaviour))):
            h.update(b"\x01" + _norm(p.behaviour).encode("utf-8"))
            h.update(b"\x02" + _norm(p.command).encode("utf-8"))
            h.update(b"\x03" + _norm(p.expect).encode("utf-8"))
            if p.inputs:
                h.update(b"\x06" + inputs_digest(p).encode("utf-8"))
    return h.hexdigest()[:16]


def claim_digest(spec, register=None) -> str:
    """A digest over the WHOLE claim: the criteria, their pinned procedures, the risk register and
    the declared scope.

    `procedure_digest` answers "did the CHECK move"; that is not the same question as "did the
    CLAIM move", and reading the first as the second is a false green. Measured on `c_compiler`
    (2026-09-20/21): the procedures never changed, so the closure read `procedure_moved_since_
    authoring: false` — while the agent grew the accepted-risk register from seven entries to nine
    after the work had started, and six of the divergences an independent corpus later found in
    that closed tree sat behind exactly those entries. Narrowing by exclusion is the cheapest way
    to make a claim true, which is why it is the one that has to be visible.
    """
    h = hashlib.sha256()
    h.update(procedure_digest(spec.criteria or ()).encode("utf-8"))
    # BOTH carriers, each under its own tag: the packet's pre-fill is its issuer's, the split's register its
    # decomposer's (§9.2) — either narrows the claim, and reading one at authoring and the other now was a false move
    for tag, items in ((b"\x10", spec.accepted_risks), (b"\x12", register.items if register is not None else ())):
        for n in sorted(items or (), key=lambda r: _norm(r.item)):
            h.update(tag + _norm(n.item).encode("utf-8"))
    for x in sorted(spec.scope or ()):
        h.update(b"\x11" + _norm(x).encode("utf-8"))
    return h.hexdigest()[:16]


def criteria_without_procedure(criteria: Iterable[Criteria]) -> list[str]:
    """The criteria that pin no runnable probe — i.e. that decide nothing as written (A1).

    A probe with no command pins nothing: the whole defect being repaired here is a procedure
    supplied later out of someone's head, and a behaviour named with no way to observe it is that
    same defect written one line higher.

    A SEAM criterion (`depends_on` — the `dep__<producer>` encoding of a declared Dep) is not in
    this population, and not as a convenience: it is not a claim the consumer decides at all. It
    DECLARES a coupling; what makes the coupling true is the producer's own PASS, and the claim
    that the joined parts constitute the parent is the **integration implication**, which the canon
    attributes to the PARENT and to no child (§6.5; §8.7 "a forgotten glue criterion = FM-1" — at
    the parent's level). Demanding a probe here would put the integration truth-maker on the wrong
    node, and — measured while landing this rule — it made every graph carrying a declared seam
    unexecutable, with no door able to supply what was demanded. A caller who WANTS the seam probed
    from the consumer's side may still pin one (`add_dependency(..., check=[…])`).
    """
    return [c.name for c in (criteria or ())
            if not c.depends_on and not any(_norm(p.command) for p in (c.check or ()))]


INPUTS_TOKEN = "{inputs}"


def inputs_unpinned(criteria: Iterable[Criteria]) -> dict[str, list[str]]:
    """{criterion: [ids of its probes that read `{inputs}` and pin nothing there]}: such a probe runs over an empty
    directory, so its verdict reads what was never pinned. A machine issuer's re-decomposition restated its children
    from the packet, which shows a probe's inputs only as a count, and would have admitted exactly this
    (GB_c_compiler_tmp5cb096)."""
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        if bad := [probe_id(c.name, p) for p in (c.check or ()) if INPUTS_TOKEN in (p.command or "") and not p.inputs]:
            out[c.name] = bad
    return out


def twin_probes(criteria: Iterable[Criteria]) -> dict[str, list[str]]:
    """{criterion: [ids two or more of its probes share]}. A probe's id is its command, so two probes of one
    criterion with one command — `python {inputs}/probe.py` twice over different files — are laid down in one
    directory, the second file over the first, and one report entry accounts for both: one of them is never
    run while the record says it was."""
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        ids = [probe_id(c.name, p) for p in (c.check or ())]
        if twins := sorted({i for i in ids if ids.count(i) > 1}):
            out[c.name] = twins
    return out


def unsafe_input_paths(criteria: Iterable[Criteria]) -> dict[str, list[str]]:
    """{criterion: [input paths that cannot be materialized inside the probe's own directory]}.

    An input is written by the system under a directory the validator owns; a path that is absolute
    or climbs out of it would write somewhere else — into the delivery, say — and a procedure that
    cannot be laid down as pinned decides nothing."""
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        bad = [path for p in (c.check or ()) for path, _ in p.inputs
               if not path.strip() or PurePosixPath(path.replace("\\", "/")).is_absolute()
               or ":" in path or ".." in PurePosixPath(path.replace("\\", "/")).parts]
        if bad:
            out[c.name] = bad
    return out


def unread_inputs(criteria: Iterable[Criteria]) -> dict[str, list[str]]:
    """{criterion: [commands that carry inputs and never name `{inputs}`]} — files pinned and not read,
    so the command still observes whatever the working directory holds at validation time."""
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        bad = [p.command for p in (c.check or ()) if p.inputs and INPUTS_TOKEN not in p.command]
        if bad:
            out[c.name] = bad
    return out


#: A pinned Python program run as a SCRIPT from `{inputs}` — `python {inputs}/x.py`, or bare `pytest {inputs}/…`.
#: Python puts the script's own directory on its path, not the working directory; `python -m …` and `python -c`
#: put the working directory there, so they are not this shape.
_RUNS_A_PINNED_SCRIPT = re.compile(
    r"(?:^|[\s;&|(])(?:(?:python3?|py)(?:\.exe)?(?:\s+-(?![mc]\b)\S+)*|(?<!-m )pytest(?:\s+-\S+)*)"
    r"\s+[\"']?\{inputs\}/([^\s\"';&|)]+\.py)")


def _imports_beyond(body: str, local: set[str]) -> set[str]:
    """Top-level modules a Python source imports that are neither the stdlib nor among `local` — or nothing,
    where it cannot be parsed or arranges its own path (it may put the working directory there itself)."""
    if "sys.path" in body:
        return set()
    try:
        tree = ast.parse(body)
    except (SyntaxError, ValueError):
        return set()
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree)
              if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module}
    return names - set(sys.stdlib_module_names) - local - {"__future__"}


#: The one wording of the refusal, for every door that admits a contract.
OFF_THE_WORKDIR = ("these pinned probes run a program from `{inputs}` that imports what the delivery holds, and "
                   "run as pinned Python searches the probe's own directory, not the working directory — the "
                   "module is found only if the environment happens to hold it, so the probe decides nothing "
                   "the contract fixed; run it as `PYTHONPATH=. python {inputs}/<program>.py`")


def probes_off_the_workdir(criteria: Iterable[Criteria]) -> dict[str, list[str]]:
    """{criterion: [pinned commands that run a program from `{inputs}` which imports the delivery off a path
    that does not hold it]}.

    Run as pinned, `python {inputs}/x.py` searches the probe's own directory, which the system lays down
    apart from the working directory — so `import json_parser` finds the delivery only if the ENVIRONMENT
    happens to (measured, E3 2026-09-28: ten of thirteen such probes raised ModuleNotFoundError in a clean
    interpreter, and an executor had written a `.pth` into the shared environment to make them pass; the
    authoring rule `PYTHONPATH=. python {inputs}/x.py` was in the prompt and broken twelve times of
    thirteen). A command that sets `PYTHONPATH` is out of this shape whatever it sets it to: the path it
    names is then the contract's, visible, not the environment's."""
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        for p in (c.check or ()):
            cmd = p.command or ""
            if not p.inputs or "PYTHONPATH" in cmd:
                continue
            files = {PurePosixPath(path.replace("\\", "/")).as_posix(): body for path, body in p.inputs}
            local = {PurePosixPath(f).parts[0].removesuffix(".py") for f in files if PurePosixPath(f).parts}
            if any(_imports_beyond(files.get(s, ""), local) for s in _RUNS_A_PINNED_SCRIPT.findall(cmd)):
                out.setdefault(c.name, []).append(cmd)
    return out


#: A scratch path every validation run shares — `/tmp/u1`, `/var/tmp/x` — not one made for this run.
#: A scratch place every validation run shares: `/tmp`, `/var/tmp`, `/dev/shm` as a path — written to, `cd`-ed into
#: or named in a variable (`D=/tmp`). Not one made per run: a path carrying the process id (`/tmp/.cu_$$`) or a
#: `mktemp` template or directory (`mktemp /tmp/u.XXXXXX`, `mktemp -p /tmp`). A loop variable (`/tmp/B$sz`) names
#: the same file in every run, so it is shared.
_SHARED_SCRATCH = re.compile(r"(?<![\w$}/.-])/(?:var/tmp|tmp|dev/shm)(?:/[\w.$-]+|/\$\{?\w+\}?)*")


def _shares_scratch(command: str) -> bool:
    return any(not ("$$" in m.group(0) or "XXX" in m.group(0)
                    or "mktemp" in command[max(0, m.start() - 40):m.start()])
               for m in _SHARED_SCRATCH.finditer(command or ""))


#: The one wording of that refusal, for every door that admits a contract.
SHARED_SCRATCH = ("these pinned probes keep scratch files at a fixed path every validation run shares, so two nodes "
                  "validated at once overwrite each other's files and a verdict depends on who ran alongside "
                  "(measured: `tail` and `uniq` of one plan both wrote `/tmp/u1`) — make the scratch the run's own: "
                  "`T=$(mktemp -d); … $T/u1 …`")


def shared_scratch(criteria: Iterable[Criteria]) -> dict[str, list[str]]:
    """{criterion: [pinned commands that write or read scratch at a fixed shared path]}. A procedure is pinned so
    that it decides the same way whoever runs it (Inv-1); one whose files another run can rewrite mid-check
    decides by the schedule instead. `mktemp -d` or the probe's own `{inputs}` is per run."""
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        bad = [p.command for p in (c.check or ()) if _shares_scratch(p.command)]
        if bad:
            out[c.name] = bad
    return out


def criterionless(criteria: Iterable[Criteria]) -> Optional[str]:
    """Why a contract with no criterion the node itself decides is no packet — or None when it has one.

    A task's criteria are a finite NONEMPTY set of decidable predicates (§2.2). Over the empty set
    V is the empty AND: every result passes and "every criterion pins its check" holds of nothing —
    the measured shape (spreadsheet_engine, 2026-10-11): an authoring that came back empty built a
    root with `criteria: []`, a system executor took it, and its delivery waited in VALIDATING for a
    verdict over nothing. A `depends_on` seam is not one (`criteria_without_procedure`): it declares a
    coupling the producer's PASS makes true and decides nothing about this node's result — a node left
    holding only seams ran to DONE over no check at all."""
    if any(not c.depends_on for c in criteria or ()):
        return None
    return ("the contract has no criterion the node itself decides — a task's criteria are a finite NONEMPTY set of "
            "decidable predicates (§2.2, A1), and over none every result passes; give it at least one "
            "criterion with its `check: [{behaviour, command, expect}]`")


def admission_defects(criteria: Iterable[Criteria]) -> list[str]:
    """Every defect a contract's admission refuses, said once each — the ONE ladder: the issuer's ASSIGN
    (`admission.refuse_a_contract_that_pins_nothing`), an installed revision (`loop._validate_effects`), the plan's author
    before a build (`decompose._refused_probes`) and CHECK `A1:procedure` read it. Written three times, the rungs came
    in three orders with three wordings and one copy lacked the first rung (ortho audit, D-F7)."""
    crit = list(criteria or ())
    if why := criterionless(crit):
        return [why]
    out = [f"{k}: the contract would pin no check on it — nothing would decide it but a probe improvised at "
           f"validation time (A1, §2; pre-registration, Inv-1 §12.3); give it `check: [{{behaviour, command, expect}}]`"
           for k in criteria_without_procedure(crit)]
    out += [f"{k}: two probes of one criterion run one command ({', '.join(v)}) — a probe is named by its command, so "
            f"the second would be laid down over the first and never run; give each its own (its own file name under "
            f"{{inputs}})" for k, v in sorted(twin_probes(crit).items())]
    out += [f"{k}: its probe reads {INPUTS_TOKEN} and pins nothing there ({', '.join(v)}) — it would run over an empty "
            f"directory; pin the files it reads in its `inputs`" for k, v in sorted(inputs_unpinned(crit).items())]
    out += [f"{k}: pinned inputs would land outside their own probe's directory ({', '.join(v)}) — the system writes "
            f"them at validation time under a directory the validator owns; give each a relative path inside it"
            for k, v in sorted(unsafe_input_paths(crit).items())]
    out += [f"{k}: {OFF_THE_WORKDIR} — {', '.join(v)}" for k, v in sorted(probes_off_the_workdir(crit).items())]
    out += [f"{k}: {SHARED_SCRATCH} — {', '.join(v)}" for k, v in sorted(shared_scratch(crit).items())]
    out += [f"{k}: every probe it pins emits a constant ({', '.join(v)}) and cannot come out false, so the criterion "
            f"forbids nothing (§1.3, §9.6) and a PASS on it observes no work; pin a command that runs the delivery"
            for k, v in sorted(hollow_procedures(crit).items())]
    return out


def hollow_procedures(criteria: Iterable[Criteria]) -> dict[str, list[str]]:
    """{criterion: its pinned commands} where EVERY one emits a constant — the procedure's fail-extension is empty.

    FORM, not FM-3: whether a probe that runs the work can SEE a divergence is sensitivity, which no structural check
    guards (§9.10), but a procedure that cannot come out false at all is a criterion forbidding nothing on the map —
    decidable for a literal constant emitter (§9.6; its guard is among §20.10's requirements), and lifted by the
    decomposer's own repair, so refusing it conforms (§12.16 (ii)). Named only, an AUTO root on `sql_database` pinned
    `echo 'Complex SELECT test'` on each of four criteria, passed, and read 0.09 held-out (GB_sql_database_tmu9cb784)."""
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        cmds = [p.command for p in (c.check or ()) if _norm(p.command)]
        if cmds and all(emits_a_constant(x) for x in cmds):
            out[c.name] = cmds
    return out


def materialize_inputs(criteria: Iterable[Criteria], base: str | Path) -> dict[str, Path]:
    """Write every pinned probe's inputs under `base/<probe id>/`, from the contract, at validation time.

    {probe id: its directory}. Done by the SYSTEM so nothing the executor writes can stand in for
    the corpus the issuer pinned; unsafe paths were refused at admission and are skipped here."""
    # AND IT REFUSES RATHER THAN SKIPS. Skipping the unsafe entries laid down a STRICT SUBSET of
    # the pinned corpus and said nothing: the command then passed over fewer files than the contract
    # pins, while `pinned_probes_run` counted the probe as run and the digest counted every file —
    # the very shape this module exists against, recreated by its own repair. Admission refuses such
    # a path (`admission.refuse_a_contract_that_pins_nothing`), so reaching here means something got
    # past it, and a corpus that cannot be laid down as pinned decides nothing.
    if unsafe := unsafe_input_paths(criteria):
        raise ValueError(
            "these pinned inputs cannot be laid down inside their probe's own directory: "
            + "; ".join(f"{k}: {', '.join(v)}" for k, v in sorted(unsafe.items()))
            + " — a probe over a truncated corpus is not the procedure the contract pins")
    dirs: dict[str, Path] = {}
    for c in criteria or ():
        for p in (c.check or ()):
            if not p.inputs:
                continue
            pid = probe_id(c.name, p)
            d = Path(base) / inputs_dir_name(pid)
            for path, body in p.inputs:
                f = d / PurePosixPath(path.replace("\\", "/"))
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(body, encoding="utf-8")
            dirs[pid] = d
    return dirs


#: A command reading a relative path or glob that is not the probe's own `{inputs}` — the shape of
#: the `c_compiler` probes that iterated over `torture_corpus/*.c`. Not every such command is a
#: defect (a probe must name the artefact under test: `./mycc t/hello.c`), which is why this is a
#: NOTE and not a refusal — but the one that moved under a closed node was of exactly this shape and
#: nothing said so.
#: A glob over a PATH — it must carry a separator or an extension. Matching any `*` flagged
#: `python -c "print(2*3)"`, and a note that fires on arithmetic teaches the reader to skip the note
#: that carries the real finding.
_READS_A_SET = re.compile(r"(?<![\w${])(?:\./)?[\w.-]*(?:/[\w.*-]*)*\*(?:\.[\w*]+|/[\w.*-]*)"
                          r"|(?<![\w${])(?:\./)?[\w.-]*/\*")


def reads_an_unpinned_set(criteria: Iterable[Criteria]) -> dict[str, list[str]]:
    """{criterion: [commands that iterate over a set of files the contract does not pin]}.

    A fixed command over a set the EXECUTOR owns is a procedure whose object can grow or shrink
    under it while its digest stays put — measured on `c_compiler`, where two central probes ran
    over corpora that went from 60 and 36 files to 79 while the node closed."""
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        bad = [p.command for p in (c.check or ())
               if not p.inputs and _READS_A_SET.search(_norm(p.command) or "")]
        if bad:
            out[c.name] = bad
    return out


def degenerate_procedures(criteria: Iterable[Criteria]) -> dict[str, list[str]]:
    """{criterion: [pinned commands that cannot observe the artefact at all]}.

    A command like `echo ok` satisfies "a criterion carries its check" and decides nothing: it
    cannot come out false, so the criterion it pins forbids nothing (§1.3 — a criterion without a
    non-empty fail-extension is not a criterion). This does NOT refuse: whether a probe is
    SENSITIVE to a real divergence is FM-3, and §9.10 is explicit that no structural check guards
    it — a regex that pretended to would be the false green one level up. What it does is make the
    obvious floor VISIBLE, so a hollow procedure is named on the node and in the closure instead of
    passing as coverage. The list is deliberately short and literal: constant emitters with no
    pipeline behind them.
    """
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        bad = [p.command for p in (c.check or ())
               if _norm(p.command) and emits_a_constant(p.command)]
        if bad:
            out[c.name] = bad
    return out


def _reported_ids(name: str, probes: Sequence[Mapping], dirs: Iterable[tuple[str, object]] = ()) -> set[str]:
    """The probe ids a report accounts for under criterion `name`: its cited ids — a bare hash read
    inside the criterion it is reported under — and, for each probe, the id of the command it ran.

    One owner for the three readers (pinned, regression, coverage): measured 2026-09-27, a validator
    cited pinned probes as `568a2aaa` and the pinned rule alone learned to read it, while the regression
    rule and the coverage count kept demanding `criterion#hash`."""
    out: set[str] = set()
    for p in probes:
        if (_id := str(p.get("id", "")).strip()):
            out.add(_id if "#" in _id else f"{name}#{_id}")
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
        for p in probes:
            if not _norm(p.get("command", "")):
                continue
            # …AS RUN, with this round's inputs directories NAMED rather than spelled: normalizing a multi-line
            # program onto one line left a command no shell runs, and the round's directory is gone the next round
            # — shown that way, the next validator ran its own version and nothing matched (automatic json_parser,
            # 2026-09-28: one pass refused three times). The id is over the named form, so a later round that runs
            # the line over its own directory matches it by command as well as by id.
            run = tokenized(str(p.get("command", "")), dirs)
            cited = str(p.get("id", "")).strip()
            out.setdefault(name, []).append(
                {"id": finding_id(name, run), "behaviour": _norm(p.get("behaviour", "")) or "found by contact",
                 "command": _norm(run), "as_run": run, "seen": str(p.get("command", "")),
                 "cited": (cited if "#" in cited else f"{name}#{cited}") if cited else "",
                 "expect": _norm(p.get("expect", "")),
                 **({"refuted_text": texts[name]} if name in (texts or {}) else {})})
    return out


def merge_regression(stored: Mapping, found: Mapping) -> dict[str, list[dict]]:
    """The node's regression set, grown by this round and never shrunk (dedup by probe id)."""
    out = {k: list(v) for k, v in (stored or {}).items()}
    for name, probes in (found or {}).items():
        have = {p.get("id") for p in out.get(name, ())}
        out.setdefault(name, []).extend(p for p in probes if p.get("id") not in have)
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


def inputs_dir_name(pid: str) -> str:
    """The directory a pinned probe's inputs are laid down in — named after the probe, one spelling."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", pid)


def without_pinned_runs(regression: Mapping, pinned: Mapping[str, str]) -> dict[str, list[dict]]:
    """The regression set less the RUNS OF PINNED PROBES — any the node's contract has carried, in force or since
    withdrawn. It holds the validator's OWN findings: a pinned probe in force is demanded every round anyway
    (`unrun_pinned`), and a run of it under a second id was a second demand no report could meet — one probe
    entry carries one id (automatic json_parser, 2026-09-28: one pass refused three times). A withdrawn one's
    refutation was, by the issuer's revision, of the probe and not of the artifact; kept, it failed the node on
    every later round and the accepted challenge came back in a loop."""
    return {k: [p for p in v if pinned_run(p, pinned or {}, k) is None] for k, v in (regression or {}).items()}


def laid_down_dirs(criteria: Iterable[Criteria], base: str | Path | None) -> tuple[tuple[str, Path], ...]:
    """(probe id, directory) for every pinned probe's inputs laid down anywhere under `base` this round —
    batches lay them in subdirectories of their own."""
    if not base or not Path(base).is_dir():
        return ()
    names = {inputs_dir_name(probe_id(c.name, p)): probe_id(c.name, p)
             for c in criteria or () for p in (c.check or ()) if p.inputs}
    return tuple((names[d.name], d) for d in sorted(Path(base).rglob("*"))
                 if d.is_dir() and d.parent.name == "probe_inputs" and d.name in names)


def inputs_token(pid: str) -> str:
    """The name a stored command gives the directory a pinned probe's inputs were laid down in, any round."""
    return "{inputs:" + pid + "}"


def tokenized(command: str, dirs: Iterable[tuple[str, object]] = ()) -> str:
    """`command` with each directory THIS round laid a pinned probe's inputs down in, literally as it was laid,
    named by that probe. The directory is fresh every round: a command stored with it named a path the next
    round does not have, and a span guessed back out of the text swallowed the words around it."""
    for pid, d in dirs or ():
        for form in sorted({str(d), Path(str(d)).as_posix(), str(Path(str(d)))}, key=len, reverse=True):
            command = command.replace(form, inputs_token(pid))
    return command


def laid(command: str, dirs: Mapping[str, object]) -> str:
    """A stored command over THIS round's directories — the inverse of `tokenized`."""
    for pid, d in (dirs or {}).items():
        command = command.replace(inputs_token(pid), Path(str(d)).as_posix())
    return command


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


def unrun_regression(regression: Mapping, per_criterion: Sequence[Mapping],
                     dirs: Iterable[tuple[str, object]] = (), layable: Iterable[str] | None = None,
                     delivery: str | Path | None = None) -> dict[str, list[str]]:
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
                   and not unrerunnable(p, layable, delivery)]
        if missing:
            out[name] = missing
    return out


#: A word of a command that names a file by an absolute path — POSIX, or a Windows drive. A bare backslash begins no
#: path: `\n#endif` in a printf is an escape, and read as a rooted path it was "gone" on a Windows engine.
_ABSOLUTE = re.compile(r"^(?:/|[A-Za-z]:[\\/])")


def unrerunnable(p: Mapping, layable: Iterable[str] | None, delivery: str | Path | None = None) -> str:
    """Why a stored finding cannot be re-run as recorded — '' where it can. Such a finding is SHOWN, not demanded: a
    probe that cannot run decides nothing (A1 (i)), and demanding it holds the node `undecidable` whatever is repaired.

    Two ways. It reads the inputs of a probe the contract no longer pins: they are not laid down any more, as a finding
    orphaned by a rename. Or it names a file by an absolute path that is GONE here, now — neither it nor the directory
    it would sit in exists — outside the delivery's own tree, where a missing file is what the finding may be about:
    an earlier validation's pruned scratch (`root.pp_1791646628/dt/hh3.c`, GB_c_compiler_tmp5cb096). Read where the
    engine stands, when it is asked. A marker for "some validation's scratch" in its place made 198 of that node's
    271 findings advisory, most of them programs the validator wrote there that still stood and still ran (critic over
    f0584f3): a finding is demanded while it can run."""
    cmd = str(p.get("as_run") or p.get("command") or "")
    if layable is not None and set(re.findall(r"\{inputs:([^}]*)\}", cmd)) - set(layable):
        return "it reads the inputs of a probe the contract no longer pins"
    home = Path(str(delivery)).as_posix().rstrip("/") + "/" if delivery else None
    # a path under a pinned probe's inputs is laid down every round: never gone — cut whole, `{inputs:X}/tests/a.c`
    # left `/tests/a.c` behind, an absolute path that never existed
    gone = [w for w in re.split(r"[\s'\"=<>|;&()`]+", re.sub(r"\{inputs:[^}]*\}[^\s'\"=<>|;&()`]*", "", cmd))
            if _ABSOLUTE.match(w) and not (home and Path(w).as_posix().startswith(home))
            and not Path(w).exists() and not Path(w).parent.exists()]
    return f"it names {', '.join(gone)}, which no longer exist here" if gone else ""


def layable_pids(criteria: Iterable[Criteria]) -> set[str]:
    """The pinned probes whose inputs this contract lays down — what a stored `{inputs:<id>}` can be shown over."""
    return {probe_id(c.name, p) for c in criteria or () for p in (c.check or ()) if p.inputs}


def layable_over(criteria: Iterable[Criteria], parts: Mapping | None) -> set[str]:
    """`layable_pids` of a node's validation: its own criteria and its parts' (`parts`: {criterion: their criteria})."""
    return layable_pids(tuple(criteria or ()) + tuple(c for cs in (parts or {}).values() for c in cs))


def part_criteria(part_id, criteria: Iterable[Criteria]) -> tuple[Criteria, ...]:
    """A part's criteria as its whole's validation demands them, each named `<part>/<criterion>` — so every
    probe id, inputs directory and `{inputs:<id>}` token is the part's own and never the whole's, whose
    probe may pin the same command under a criterion of the same name."""
    return tuple(replace(c, name=f"{part_id}/{c.name}") for c in criteria or ()
                 if any(_norm(p.command) for p in (c.check or ())))


def _cmd_key(command: str) -> str:
    """A command's identity whichever criterion it is reported under — the hash `probe_id` gives it."""
    return probe_id("", {"command": command}).split("#")[1]


def _cited_as(p: Mapping) -> str:
    return f"`{i}`" if (i := str(p.get("id", "")).strip()) else "its command"


def part_credit(parts: Mapping[str, Sequence[Criteria]], per_criterion: Sequence[Mapping],
                dirs: Iterable[tuple[str, object]] = (), own: Sequence[Criteria] = ()) -> tuple[set[str], dict[str, list[str]]]:
    """(the parts' pinned probes this report shows holding over the delivery, {demanded part probe it names but cannot
    credit: why}) — THE one reading of a part probe's credit: "was it run" (`unrun_parts`), "was it shown holding"
    (`parts_not_shown_holding`) and the refusal's words (`unaccounted_for`) all read this.

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
    by_hash: dict[str, set[str]] = {}
    by_cmd: dict[str, set[str]] = {}
    for pid, (c, p) in known.items():
        by_hash.setdefault(pid.split("#")[-1], set()).add(pid)
        by_cmd.setdefault(_cmd_key(p.command.replace(INPUTS_TOKEN, inputs_token(pid))), set()).add(pid)
    dirs = tuple(dirs or ())
    # which part probes each criterion of the whole RESTS on: a passed criterion vouches, without `held`, only for those —
    # a command met under an unrelated criterion that passes (its own exploration, "3 failed") is no observation of it
    rests = {_norm(k): {probe_id(c.name, p) for c in cs for p in (c.check or ()) if _norm(p.command)}
             for k, cs in (parts or {}).items()}
    good: set[str] = set()
    bad: set[str] = set()
    why: dict[str, list[str]] = {}
    for e in per_criterion or ():
        name, verdict = _norm(e.get("criterion")), spoken_verdict(e.get("verdict"))
        for p in probes_of(e):
            i, cmd = str(p.get("id", "")).strip(), str(p.get("command", ""))
            h = set() if "#" in i else by_hash.get(i, set())
            m = {x for k in {_cmd_key(cmd), _cmd_key(tokenized(cmd, dirs))} for x in by_cmd.get(k, ())} if _norm(cmd) else set()
            cand = h | m
            named = {i} if i in known else (h & m) or cand
            if len(named) > 1:
                for pid in named & set(demanded):
                    why.setdefault(pid, []).append(f"cited by {_cited_as(p)} under '{name}', which names {len(named)} "
                                                   f"demanded probes ({', '.join(sorted(named))}) — cite it by its full id")
                continue
            for pid in (cand - named) & set(demanded):
                why.setdefault(pid, []).append(f"its hash or command, cited under '{name}', was read as {', '.join(named)} "
                                               "— cite this one by its own full id")
            if not named & set(demanded):
                continue
            pid, held = next(iter(named)), probe_held(p.get("held"))
            if held is True or (held is None and verdict == "pass" and pid in rests.get(name, ())):
                good.add(pid)
                continue
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
    return credited, {pid: w for pid, w in why.items() if pid not in credited}


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
                    delivery: str | Path | None = None) -> dict[str, list[str]]:
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
    # The internal-node exemption (§10.3) is narrowed to the case that HAS it: §10.3 lets an INTERNAL node
    # self-verify; at a seam independence is owed and a self-validation is not a verdict at all. The
    # caller guarantees that upstream today, and the repo's own recurring class is a rule that
    # holds at one door and not at the next — so it is checked here, where the rule lives.
    if task is None or (bool(by_hand) and internal and str(validator_id) == str(task.assignee)):
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
    for name, ids in unrun_regression(regression, per_criterion, dirs, layable, delivery).items():
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
