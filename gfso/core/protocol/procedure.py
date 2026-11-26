"""The pinned decision procedure: its identity, its digest, what a contract must pin, where its inputs are laid, and how
an output is read against `expect`. What a report of RUNNING it accounts for is read in `accounting.py`.

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

import functools
import hashlib
import os
import re
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Optional

from gfso import config as _config
from gfso.core.graph.model import MAX_BOUND_S, bound_seconds
from gfso.core.types import INPUTS_TOKEN, Criteria, Probe, files_at
from gfso.core.protocol.probe_runs import (OFF_THE_WORKDIR, UNITTEST_UNIMPORTABLE, probes_off_the_workdir,
                                           probes_unittest_cannot_import)
from gfso.core.protocol.invariants import emits_a_constant


def probe_key(command) -> str:
    """A command as a probe's identity reads it: whitespace runs as one, the ends stripped. THE one key — the
    regression store, a report matched to its pin, a corpus carried to a re-written probe all look a probe up by it,
    and one spelling apart would lose the match silently."""
    return " ".join(str(command or "").split())


_norm = probe_key


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
    named = [w for w in _WORD.split(cmd) if _ROUND.search(w) and round_of(w) is not None]   # …as `round_words` reads one
    if not named:
        return probe_id(criterion_name, {"command": command})
    digests = [_content(Path(w)) for w in named]
    seed = cmd if None in digests else _ROUND.sub(r"\1{round}", cmd) + "\x00" + "\x00".join(digests)
    return f"{_norm(criterion_name)}#{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:8]}"


def _content(path: Path) -> str | None:
    """A digest of what stands at `path` — a file's bytes, or a directory's files by their place in it — or None. Read
    where the place holding it is (`files_at`): a round's scratch may stand nowhere on this host. Once while the round
    stands (`_read_once`)."""
    try:
        return _read_once("digest", path, lambda: _digest(path))
    except OSError:
        return None                       # unreadable is not there to read: the round stays in the id


#: the most of a file a digest reads: past it, no digest, and the round stays in the id
DIGEST_CAP = 64 << 20


def _digest(path: Path) -> str | None:
    fs = files_at(path)
    if (raw := fs.read_bytes(str(path), DIGEST_CAP + 1)) is not None:     # …an agent writes it: never whole into this process
        return hashlib.sha256(raw).hexdigest() if len(raw) <= DIGEST_CAP else None
    if (tree := fs.read_tree(str(path))) is not None:
        h = hashlib.sha256()
        for rel, raw in sorted(tree.items(), key=lambda x: Path(x[0])):
            h.update(rel.encode("utf-8") + b"\x00" + raw + b"\x00")
        return h.hexdigest()
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
            if p.exact:       # only where set: every digest pinned before the field stays
                h.update(b"\x07")
            if p.bound_s is not None:     # …and the bound it decides within, its issuer's where stated (`Probe.bound_s`)
                h.update(b"\x08" + repr(bound_seconds(p.bound_s)).encode("utf-8"))
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

    A declared Dep edge is no criterion (§2.7), so nothing here asks it for a probe: the coupling holds by the
    producer's own PASS, and the integration implication is the PARENT's (§6.5, §8.7). A criterion that reads a
    producer's result (`depends_on`, `add_dependency(..., check=[…])`) is a criterion like any other.
    """
    return [c.name for c in (criteria or ()) if not any(_norm(p.command) for p in (c.check or ()))]


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


#: what the shell hands a program as written, so a brace inside it is the program's (awk, JSON, a heredoc's C source)
_QUOTED = re.compile(r"""<<-?\s*['"]?(\w+)['"]?[^\n]*\n.*?^\s*\1\s*$|'[^']*'|"(?:\\.|[^"\\])*\"""", re.S | re.M)
#: an unquoted `{name}` no `$` expands and no run fills — the system fills `{inputs}` alone
_PLACEHOLDER = re.compile(r"(?<!\$)\{(?!inputs\})[A-Za-z_]\w*\}")


def unfilled_placeholders(criteria: Iterable[Criteria]) -> dict[str, list[str]]:
    """{criterion: the placeholders its pinned commands carry} — `{exec}`, `{workspace}`: run as written, such a command
    runs nothing anyone meant, and no truthful report can cite it as run (§12.16 (ii); `{exec}` ×142 in one AUTO run's
    pins, tmyl10584)."""
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        if found := [m for p in (c.check or ()) for m in _PLACEHOLDER.findall(_QUOTED.sub(" ", p.command or ""))]:
            out[c.name] = list(dict.fromkeys(found))
    return out


#: a file a command names under `{inputs}` — a literal name; a glob or a shell variable names no one file
_NAMED_INPUT = re.compile(re.escape(INPUTS_TOKEN) + r"/([^\s'\";|&<>()]+)")
#: …a file the command itself makes there — a redirect's or an `-o`'s target — which no one has to pin (critic)
_MADE_INPUT = re.compile(r"(?:>>?|-o)\s*" + re.escape(INPUTS_TOKEN) + r"/([^\s'\";|&<>()]+)")
_PATTERN = re.compile(r"[*?\[\]${}`]")


def _segments(path: str) -> str:
    """`path` with its empty and `.` segments dropped: `./fixture//a.txt` is `fixture/a.txt`."""
    return "/".join(x for x in path.split("/") if x not in ("", "."))


def _names_pinned(name: str, have: set) -> bool:
    """Whether `name` under `{inputs}` reaches what the probe pins, read as the path it names: `fixture/.` is the
    directory `fixture` that pinned files under it make (stranger run s17b: the core criterion's `{inputs}/fixture/.`
    was refused twice, then dropped from the plan); one ending in `/` names a directory, never a pinned file
    (`data.csv/.` fails on Linux); a `..` climbs where nothing is pinned, so it is read as written (critic)."""
    k = _segments(name)
    if ".." in k.split("/"):
        return name in have
    return not k or (k in have and not name.endswith(("/", "/."))) or any(h.startswith(k + "/") for h in have)


def inputs_named_not_pinned(criteria: Iterable[Criteria]) -> dict[str, list[str]]:
    """{criterion: [`{inputs}/<file>` its probes name that the probe itself does not pin]}: each probe's inputs are laid
    down in its own directory, so a file pinned under a sibling probe, or nowhere, is "cannot open" at validation — a
    false FAIL of every delivery, correct ones included (V3_cc2's `builtins_memory_setjmp_va`, read on the oracle's
    good trees, 2026-10-31)."""
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        for p in c.check or ():
            have = {_segments(input_name(path)) for path, _ in _input_items(p.inputs)}
            made = set(_MADE_INPUT.findall(p.command or ""))
            bad = [n for n in dict.fromkeys(_NAMED_INPUT.findall(p.command or "")) if n not in made
                   and not _PATTERN.search(n) and not _names_pinned(n, have)]
            if bad:
                out.setdefault(c.name, []).extend(f"{INPUTS_TOKEN}/{n}" for n in bad)
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


def _input_items(inputs) -> list[tuple[str, str]]:
    """A probe's pinned files as (path, body), whichever shape carries them: a spec's dict or pairs, a `Probe`'s tuple, or
    the answer's own [{path, content}] — read as `body`, every file a model wrote that way came out empty and its move
    was refused as pinning EMPTY inputs (9 refusals in GB_c_compiler_tnl51c552); `Probe` reads `content` the same way."""
    if isinstance(inputs, dict):
        return [(str(k), str(v or "")) for k, v in inputs.items()]
    return [(str(x[0]), str(x[1] or "")) if isinstance(x, (list, tuple))
            else (str(x.get("path")), str(x.get("content") or "")) for x in inputs or ()]


def input_name(path: str) -> str:
    """A pinned file's path inside its probe's inputs directory: the `{inputs}` token is the command's, not the path's."""
    return path.replace("\\", "/").removeprefix(INPUTS_TOKEN + "/")


def pinned_files(criteria: Iterable) -> dict[tuple, str]:
    """The content every probe of these criteria pins, by (criterion, command, file) — and by (criterion, file) only
    where every probe of that criterion pins one content under that name: two probes of one criterion, or two parts'
    criteria of one name, over different files of one name must not lend each other's (critic, 2026-10-22)."""
    by_cmd: dict[tuple, str] = {}
    by_name: dict[tuple, set] = {}
    for c in criteria or ():
        name, check = (c.get("name"), c.get("check")) if isinstance(c, dict) else (c.name, c.check)
        for p in check or ():
            cmd = probe_key(p.get("command") if isinstance(p, dict) else p.command)
            for path, body in _input_items(p.get("inputs") if isinstance(p, dict) else p.inputs):
                if body:
                    by_cmd.setdefault((str(name), cmd, input_name(path)), body)
                    by_name.setdefault((str(name), input_name(path)), set()).add(body)
    return {**{k: next(iter(v)) for k, v in by_name.items() if len(v) == 1}, **by_cmd}


def with_named_files(criterion: dict, files: dict[tuple[str, str], str]) -> dict:
    """The criterion with each probe that NAMES files without their content given the content its plan already pins
    under that criterion (`pinned_files`), every path's `{inputs}` token normalized away. A model writing a probe reads
    a projection that shows its command and never the corpus behind `{inputs}`: re-homing a root's 21 probes into an
    integration node, the machine issuer pinned all 41 files empty under `{inputs}/<name>` paths, the command reworded,
    and every validation read empty inputs for twelve rounds until the ceiling (GB_sql_database_tnajs5800,
    2026-10-22). A body written stands; a probe pinning nothing (`inputs` absent or empty) is not touched."""
    if not isinstance(criterion, dict) or not criterion.get("check"):
        return criterion
    def _probe(p):
        if not isinstance(p, dict) or not p.get("inputs"):
            return p
        name, cmd = str(criterion.get("name")), probe_key(p.get("command"))
        return {**p, "inputs": {input_name(path): body or files.get((name, cmd, input_name(path)))
                                or files.get((name, input_name(path)), "") for path, body in _input_items(p["inputs"])}}
    return {**criterion, "check": [_probe(p) for p in criterion["check"]]}


def unread_inputs(criteria: Iterable[Criteria]) -> dict[str, list[str]]:
    """{criterion: [commands that carry inputs and never name `{inputs}`]} — files pinned and not read,
    so the command still observes whatever the working directory holds at validation time."""
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        bad = [p.command for p in (c.check or ()) if p.inputs and INPUTS_TOKEN not in p.command]
        if bad:
            out[c.name] = bad
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


#: A `cd`/`pushd` into a literal absolute directory — `/…`, `C:\…`, `~` — not a token (`{inputs}`) or a variable (`$T`).
_CD_ABSOLUTE = re.compile(r"(?:^|[;&|(]|\s)(?:cd|pushd)\s+[\"']?(?:/|~|[A-Za-z]:[\\/])")

#: The one wording of that refusal, for every door that admits a contract.
LEAVES_THE_WORKDIR = ("its probe changes into an absolute directory, so it checks whatever stands there rather than the "
                      "work this node delivers — a probe runs in its node's own working directory; name the files by "
                      "relative paths")


def probes_that_leave_the_workdir(criteria: Iterable[Criteria]) -> dict[str, list[str]]:
    """{criterion: [pinned commands that `cd` into an absolute directory]}. A plan is written before the work has a
    place, so any absolute directory a probe names is a guess: a plan's author running where the server stands pinned
    `cd <state home> && …` on all 72 probes, the validators ran their own commands instead, and one following a probe
    removed the project's database (GB_sql_database_tmzgc0724, 2026-10-16). Lifted by the decomposer's re-pin
    (§12.16 (ii))."""
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        if bad := [p.command for p in (c.check or ()) if _CD_ABSOLUTE.search(p.command or "")]:
            out[c.name] = bad
    return out


def criterionless(criteria: Iterable[Criteria]) -> Optional[str]:
    """Why a contract with no criterion the node itself decides is no packet — or None when it has one.

    A task's criteria are a finite NONEMPTY set of decidable predicates (§2.2). Over the empty set
    V is the empty AND: every result passes and "every criterion pins its check" holds of nothing —
    the measured shape (spreadsheet_engine, 2026-10-11): an authoring that came back empty built a
    root with `criteria: []`, a system executor took it, and its delivery waited in VALIDATING for a
    verdict over nothing."""
    if criteria:
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
    out += [f"{k}: its probe carries {', '.join(v)}, which no run fills — the system fills {INPUTS_TOKEN} alone, so the "
            f"command would run as written; write out what it stands for (quote it if the program reads it literally)"
            for k, v in sorted(unfilled_placeholders(crit).items())]
    out += [f"{k}: its probe names {', '.join(v)} and does not pin it — each probe's inputs are laid down in its own "
            f"directory, so a file pinned under another probe or nowhere cannot be opened; pin it in THIS probe's `inputs`"
            for k, v in sorted(inputs_named_not_pinned(crit).items())]
    out += [f"{k}: pinned input file(s) it feeds or runs are EMPTY ({', '.join(v)}) — the probe would run over nothing "
            f"and decide nothing; write their content (an empty expected output under `diff`/`cmp` is fine, and an empty "
            f"stdin is `< /dev/null`)" for k, v in sorted(empty_inputs(crit).items())]
    out += [f"{k}: pinned inputs would land outside their own probe's directory ({', '.join(v)}) — the system writes "
            f"them at validation time under a directory the validator owns; give each a relative path inside it"
            for k, v in sorted(unsafe_input_paths(crit).items())]
    out += [f"{k}: {OFF_THE_WORKDIR} — {', '.join(v)}" for k, v in sorted(probes_off_the_workdir(crit).items())]
    out += [f"{k}: {UNITTEST_UNIMPORTABLE} — {', '.join(v)}" for k, v in sorted(probes_unittest_cannot_import(crit).items())]
    out += [f"{k}: {SHARED_SCRATCH} — {', '.join(v)}" for k, v in sorted(shared_scratch(crit).items())]
    out += [f"{k}: {LEAVES_THE_WORKDIR} — {', '.join(v)}" for k, v in sorted(probes_that_leave_the_workdir(crit).items())]
    out += [f"{k}: every probe it pins emits a constant ({', '.join(v)}) and cannot come out false, so the criterion "
            f"forbids nothing (§1.3, §9.6) and a PASS on it observes no work; pin a command that runs the delivery"
            for k, v in sorted(hollow_procedures(crit).items())]
    out += [f"{k}: {UNBOUNDED_CHECK} — {', '.join(v)}" for k, v in sorted(unrunnable_bounds(crit).items())]
    return out


def unrunnable_bounds(criteria: Iterable[Criteria]) -> dict[str, list[str]]:
    """{criterion: [the stated bound]} of each probe whose `bound_s` no validation can run it under: not seconds above 0,
    or past the validation's own bound (`check_bound_limit`). One bounded past it is cut by the validation every time and
    decides nothing (A1 (i)); one unbounded is no finite procedure (§12.15)."""
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        for p in c.check or ():
            if p.bound_s is not None and not ((s := bound_seconds(p.bound_s)) and s <= check_bound_limit()):
                out.setdefault(c.name, []).append(f"bound_s {p.bound_s!r}")
    return out


def check_bound_limit() -> float:
    """The longest bound a check may state: the server's own T_validate (§12.2), whose remainder caps every validation's
    run (`validate._validation_cap`); none set, the longest a bound may be at all (`MAX_BOUND_S`)."""
    return _config.state_bound("VALIDATING") or MAX_BOUND_S


#: A pinned file a probe runs, sources, compiles or feeds on stdin — empty, it runs nothing. An empty file passed as an
#: ARGUMENT is a case of its own (`tail -n 1 a e b`, a coreutils plan's probe) and stays admissible.
_RUN_AS_CODE = re.compile(r"\.(?:c|h|sh|bash|py|sql)$")


def empty_inputs(criteria: Iterable[Criteria]) -> dict[str, list[str]]:
    """{criterion: the names of its pinned input files that are empty and that its command runs, sources, compiles or
    feeds on stdin}. Measured on build 9155db9: the machine's repair parts pinned 0-byte `.sql`, `.c` and `.sh` inputs on
    their first ASSIGN — 40 in GB_sql_database_tncfrm404, 79 in GB_c_compiler_tne9g0864 — and an issuer then re-pinned
    the expectations to what the build printed over them."""
    def fed(n: str, cmd: str) -> bool:
        """Is file `n` code by its name, or what `cmd` sources, runs or reads on stdin?"""
        at =rf"(?:{re.escape(INPUTS_TOKEN)}/)?{re.escape(n)}(?![\w./-])"
        return bool(_RUN_AS_CODE.search(n) or re.search(rf"(?:<|(?:^|[;&|(]\s*)(?:\.|source|bash|sh|python3?))\s+{at}", cmd))
    out: dict = {}
    for c in criteria or ():
        for p in c.check or ():
            if names := [n for n, body in (p.inputs or ()) if not str(body).strip() and fed(n, p.command)]:
                out.setdefault(c.name, []).extend(names)
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


def materialize_inputs(criteria: Iterable[Criteria], base: str | Path, files) -> dict[str, Path]:
    """Write every pinned probe's inputs under `base/<probe id>/`, from the contract, at validation time — where
    `files` (a `FilesPort`) writes, in one operation (`write_files`).

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
    laid: dict[str, bytes] = {}
    for c in criteria or ():
        for p in (c.check or ()):
            if not p.inputs:
                continue
            pid = probe_id(c.name, p)
            for path, body in p.inputs:
                # a path naming `{inputs}` is the same file: the token is the command's (an integration node's 41
                # pinned files were stored so, 2026-10-22) — laid down where the command reads it; byte for byte: a
                # text-mode write on Windows made every newline a CRLF, and a check's `diff` against its expected file
                # failed for every program inside a Linux execution (gb-sql-database-tngdkx244)
                laid[(PurePosixPath(inputs_dir_name(pid)) / input_name(path)).as_posix()] = body.encode("utf-8")
            dirs[pid] = Path(base) / inputs_dir_name(pid)
    if laid:
        # …as the system's (`seal_files`): laid as the agent's, the judged code run beside them rewrote an expected file
        # its own output was then compared with — inside the very command that compared them
        files.seal_files(str(base), laid)
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


def runs_a_past_build(command: str) -> bool:
    """Does the command use a BUILD a past validation round left in its scratch, rather than make it? Re-run on a later
    delivery it runs that round's build of the old source: its outcome no longer depends on what was delivered, and a
    finding kept with it fails every round whatever the executor fixes (root.parse_stmt, 7 FAILs in 33 min on
    `printf … | …/.gfso-scratch-root.parse_stmt/root.parse_stmt_<epoch>/x/chk`, GB_sql_database_tn9kf3836).

    Read off the FILE, not the shell's syntax — a wrapper (`timeout`, `env`, `valgrind`), a second line or a test hides
    a program from any parse, and a script or Makefile there runs the delivery: a word in a round's scratch naming a
    binary the command does not itself write. A scratch source compiled with the delivery, a script, a pinned probe's
    inputs (laid again each round) stay findings; a file no longer there is not identified, so it stays too."""
    return any(_binary(Path(w)) and not _writes(command or "", w) for w in round_words(command))


def round_inputs(command: str) -> list[str]:
    """`round_words` the command reads rather than makes — a compiler's or redirect's output is no input (`_writes`)."""
    return [w for w in round_words(command) if not _writes(command or "", w)]


def round_words(command: str) -> list[str]:
    """The words of `command` naming a file in a validation round's scratch — its judge's own, not a pinned probe's
    inputs, which are laid again each round — once each, in order."""
    return [w for w in dict.fromkeys(_WORD.split(command or ""))
            if _ROUND.search(w) and round_of(w) is not None and "/probe_inputs/" not in w.replace("\\", "/")]


def _binary(path: Path) -> bool:
    """A built program: an executable's header (ELF, PE, Mach-O). Not any file with a NUL in it — a database the delivery
    writes, or an input of NUL bytes, is data the delivery reads, and a finding over it re-runs the delivery (critic)."""
    try:
        head = _read_once("head", path, lambda: files_at(path).read_bytes(str(path), 4))   # where the round stands
    except OSError:
        return False
    return bool(head) and head.startswith((b"\x7fELF", b"MZ", b"\xcf\xfa\xed\xfe"))


#: what was read of a round's files, by (what, path) — every read of the standing findings asks it again
#: (`without_past_builds`, `finding_id`), and a round's files are its judge's, done, until the system removes the round
_READ: dict = {}


def _read_once(what: str, path, read):
    """`read()` of a round's file, once per process while the round stands (`forget_round`)."""
    if (key := (what, os.path.normcase(os.path.normpath(str(path))))) not in _READ:
        _READ[key] = read()
    return _READ[key]


def forget_round(path: str) -> None:
    """The round at `path` is gone: what was read of its files goes with it."""
    under = os.path.normcase(os.path.normpath(str(path)))
    for k in [k for k in _READ if k[1] == under or k[1].startswith(under + os.sep)]:
        _READ.pop(k, None)


def _writes(cmd: str, path: str) -> bool:
    """Does the command make `path` itself — a compiler's or redirect's output, a copy's target, or a build run over its
    directory?"""
    p, end = re.escape(path), r"(?=$|[\s'\"`;&|)<>])"
    name = re.escape(path.replace("\\", "/").rsplit("/", 1)[-1])
    # `-o chk` after a `cd` into its directory makes it too; not the `-o` inside a word (`pytest-of-…`)
    return bool(re.search(rf"(?:(?<![\w-])-o\s*|--output[= ]\s*|>\s*)['\"]?(?:{p}|{name}){end}", cmd)
                or re.search(rf"\b(?:cp|mv|install|ln)\b[^;&|\n]*\s['\"]?{p}{end}", cmd)
                or (re.search(r"\b(?:make|cmake|ninja|meson)\b", cmd)
                    and path.replace("\\", "/").rsplit("/", 1)[0] in cmd.replace(path, "")))


def inputs_dir_name(pid: str) -> str:
    """The directory a pinned probe's inputs are laid down in — named after the probe, one spelling."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", pid)


def laid_down_dirs(criteria: Iterable[Criteria], base: str | Path | None) -> tuple[tuple[str, Path], ...]:
    """(probe id, directory) for every pinned probe's inputs laid down under `base` this round — in its `probe_inputs`,
    and in each batch's, a directory of its own (`materialize_inputs`): where the system lays them, read where the
    round stands (`files_at`), not wherever a run made a directory of that name."""
    if not base:
        return ()
    fs, names = files_at(base), {inputs_dir_name(probe_id(c.name, p)): probe_id(c.name, p)
                                 for c in criteria or () for p in (c.check or ()) if p.inputs}
    laid = [Path(base, d) for d in fs.subdirs(str(base), 3)              # one walk: [<batch>/]probe_inputs/<probe>
            if d.split("/")[-2:-1] == ["probe_inputs"]]
    return tuple((names[d.name], d) for d in sorted(laid) if d.name in names)


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


def shows(printed: str, expect: str) -> bool:
    """Does `printed` show exactly what a check must, as a check reads a printed output: written `\\t`/`\\n` escapes as
    the characters, whitespace runs as one."""
    return as_read(printed) == as_read(expect)


def contains(printed: str, expect: str) -> bool:
    """Does `printed` show `expect` as a part of it, read as `shows` reads both — a pin that is not `exact`. Nothing
    expected shows nothing."""
    return bool(want := as_read(expect)) and want in as_read(printed)


def as_read(s: str) -> str:
    """A printed text as a check reads it: written `\\t`/`\\n` escapes as the characters, whitespace runs as one."""
    return " ".join(str(s or "").replace("\\t", "\t").replace("\\n", "\n").split())


#: How an exact check's output is compared with its `expect` (`as_read`) — said in these words to its author and to
#: its validator alike: told nothing of it, a validator read `a ok` against `a` and `ok` on two lines as no substring
#: and failed six rounds the system's own runs had matched (gf-cc root.preprocessor.pp-rest, 2026-11-06).
EXACT_READ = "whitespace runs count as one, `\\n` as a newline"

#: What an author is told `exact` means — one text for every schema that pins a probe (`Probe.exact`).
EXACT_TEXT = ("true when `expect` is the COMPLETE output the command prints on correct work (" + EXACT_READ
              + ") — its standard output, or that followed by its errors; where the two streams "
              "alternate, merge them in the command (`2>&1`). The system then runs the command itself, as written, on "
              "the delivered tree in a fresh copy, and a different output fails the criterion whatever the validator "
              "says. So an exact command builds what it runs (`make -s prog && ./prog …`), creates any state it reads "
              "(starts from a fresh temp file, not one an earlier run may have left), and prints the same every time it "
              "runs; a build that records its own directory (a CMake or autotools build tree) is built afresh in the "
              "command, not reused from the tree; a probe that cannot is left false. false also when `expect` "
              "describes the output in words or "
              "names only part of it")


#: a scratch directory and the round under it, anywhere in a path
_SCRATCH_ROUND = re.compile(r"[\\/](\.gfso-scratch-[^\\/]+)[\\/]+([^\\/]+)")


def round_of(path) -> Optional[tuple[str, str]]:
    """(the round's own path, its name in the record — `.gfso-scratch-<place>/<round>`, one spelling whatever separators
    the path came in) of the validation or contact round `path` lies in; None for no round's. The outermost that does not
    hold this installation's own data directory: a delivery that itself runs gfso — this repository, judged — lays its
    tests' installations, their rounds and their temp below the judge's round, which is none of theirs; and to the judge,
    a round its delivery's run left inside its own copy is content of that copy, never a round of its own."""
    s, home = str(path), _home()
    for m in _SCRATCH_ROUND.finditer(s):
        rnd = _spelled(s[:m.end()])
        if not any(h == rnd or h.startswith(rnd + "/") for h in home):
            return s[:m.end()], f"{m.group(1)}/{m.group(2)}"
    return None


def _spelled(p: str) -> str:
    return os.path.normcase(p).replace("\\", "/").rstrip("/")


def _home() -> tuple[str, ...]:
    return _spellings(str(_config.data_dir()))


@functools.lru_cache(maxsize=8)
def _spellings(data: str) -> tuple[str, ...]:
    return tuple({_spelled(os.path.abspath(data)), _spelled(os.path.realpath(data))})


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


#: the seconds one pinned check the system runs may take, its build included, where its issuer stated none
#: (`Probe.bound_s`) — the default every reader names, logged as supplied where it is the one a run took
PROBE_S = 60

#: What an author is told a check's `bound_s` is — one text for every schema that pins a probe, the default from its owner.
BOUND_TEXT = (f"the seconds the system's own run of this command may take, its build included; left out, {PROBE_S}. A "
              "command still running then decides nothing and leaves its criterion undecided, so state the bound a slow "
              "check needs (a whole test suite, a large corpus), at most the validation's own bound")
#: …and what a refusal of one says it must be
UNBOUNDED_CHECK = ("a check's `bound_s` is seconds above 0 and at most the validation's own bound, T_validate (§12.2): "
                   "past it the validation cuts the run every time and it decides nothing, unbounded it is no finite "
                   "procedure (§12.15); state seconds inside it, or leave it out for the default")


def same_probe(p: Probe) -> tuple:
    """What makes two pinned probes ONE observation over a delivery — the same command, expectation and inputs, as
    `integrate` copying `scaffold`'s check or the root's: whatever ids they are pinned under, running one is running
    each. THE one identity: the packet owes such a probe once (`packets.owed_probes`) and a citation of any of its ids
    credits all of them (`part_credit`)."""
    # …NOT `exact`: it says who can decide the output, not what running the command observes — told apart by it, one
    # run of a command pinned twice would be owed twice and credit only the copy it was cited by
    return p.command.strip(), (p.expect or "").strip(), tuple(p.inputs or ())


