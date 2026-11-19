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
import doctest
import fnmatch
import hashlib
import itertools
import os
import posixpath
import re
import sys
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Optional, Sequence

from gfso.core.types import HOST, Criteria, Probe, files_at, unprojected
from gfso.core.protocol.shell import commands, substitution_end
from gfso.core.protocol.invariants import (ON_NO_DELIVERY, OVER_A_PASS, PAST_BOUND, emits_a_constant, probe_held,
                                          probes_of, spoken_verdict, underprobed)


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
            cmd = " ".join(str(p.get("command") if isinstance(p, dict) else p.command).split())
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
        name, cmd = str(criterion.get("name")), " ".join(str(p.get("command", "")).split())
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


#: What a probe's command runs, read as the shell would run it (`shell.commands`) — the guard below is about WHERE
#: Python looks for the delivery, which only the shell's own reading decides: which simple commands run, from which
#: directory, under which environment. The state walked is the shell's own: the directory (None in the working
#: directory, else the path inside `{inputs}` — `..` its parent), the one `cd -` returns to, the pushd stack, and its
#: variables — exported (`env`), not (`var`), marked for export before they are set, and `set -a`.
#: the interpreter by its file name: python, python3, python3.11, py, …exe — wherever it lives
_INTERPRETER = re.compile(r"(?:python(?:\d+(?:\.\d+)?)?|py)(?:\.exe)?")
#: options that take the next word as their value: the interpreter's (short, as letters), pytest's, unittest's, a
#: shell's, a wrapper's
_PY_VALUED = set("XW")
_PYTEST_VALUED = {"-k", "-m", "-p", "-c", "-n", "-W", "--rootdir", "--basetemp", "--confcutdir", "--ignore",
                  "--deselect", "--ignore-glob", "--junitxml", "--log-file"}
_UNITTEST_VALUED = {"-k", "-s", "-p", "-t", "--start-directory", "--pattern", "--top-level-directory"}
_SHELL_LONG_VALUED = {"--rcfile", "--init-file"}
_WRAPPER_VALUED = {"-s", "-k", "-n", "-u", "-g", "-C", "--signal", "--kill-after", "--chdir", "--unset"}
#: words that run the command after them (their own options and a duration skipped)
_WRAPPERS = {"env", "timeout", "nice", "nohup", "time", "command", "exec", "stdbuf", "xargs", "sudo",
             "do", "then", "else", "if", "elif", "while", "until"}
_SHELLS = {"bash", "sh", "dash", "zsh", "ksh"}
#: modules run by `-m` that read programs off the current directory as a test runner does
_RUNNERS = {"pytest": "pytest", "py.test": "pytest", "unittest": "unittest", "doctest": "doctest"}
_ASSIGNMENT = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)", re.S)
_VARIABLE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
#: what pytest collects from a directory: its test files, and the conftest it loads with them
_COLLECTED = re.compile(r"(?:^|/)(?:test_[^/]*|[^/]*_test|conftest)\.py$")
#: a pinned script naming itself: `$0`, `${BASH_SOURCE[0]}`, and `${0%/*}` its directory
_OWN_NAME = re.compile(r"\$\{?(?:0|BASH_SOURCE(?:\[0\])?)\}?(?![\w%])")
_OWN_DIR = re.compile(r"\$\{(?:0|BASH_SOURCE(?:\[0\])?)%/\*\}")
#: the current directory as a value, read where the walk stands when the word is
_CWD = re.compile(r"\$\{?PWD\}?|\$\(\s*pwd(?:\s+-[LP])?\s*\)|`\s*pwd\s*`")
#: how deep pinned scripts that run pinned scripts are read
_SCRIPT_DEPTH = 3


def _on_the_path(value: str, here: Optional[str]) -> bool:
    """Does a PYTHONPATH value name the working directory, for a Python started `here` (None in the working
    directory)? An absolute path or a variable names one the contract states; a relative one, the directory Python
    starts in; `{inputs}` names the probe's own."""
    for part in re.split(r"[:;]", value):
        if not part or part.lstrip("${").startswith("PYTHONPATH") or INPUTS_TOKEN in part:
            continue
        if part[0] in "/$~`" or re.match(r"[A-Za-z]:", part) or here is None:
            return True
    return False


def _moved(here: Optional[str], target: str) -> Optional[str]:
    """Where a `cd target` started `here` lands: the path inside `{inputs}` (`..` its parent), or None — the working
    directory, or a place under it."""
    t = target.rstrip("/")
    if t == INPUTS_TOKEN or t.startswith(INPUTS_TOKEN + "/"):
        here, t = "", t[len(INPUTS_TOKEN):].lstrip("/")
    elif here is None or not t or t.startswith(("/", "$", "~", "`")):
        return None
    p = posixpath.normpath(posixpath.join(here or ".", t or "."))
    return p if p == ".." else None if p.startswith("..") else ("" if p == "." else p)


def _runs_off_the_workdir(cmd: str, state: Optional[dict] = None) -> list[tuple]:
    """What `cmd` runs from `{inputs}` with the working directory off Python's path — ("file", name, collect) of a
    program, ("glob", pattern, collect) of the programs a pattern names, ("module", (here, dotted), collect) of a
    module named by its dots, ("code", text, None) of a `-c`, ("script", (name, state), None) of a pinned shell script —
    `collect` naming the runner that picks the files."""
    st = {"here": None, "back": None, "dirs": [], "env": {}, "var": {}, "marked": set(), "all": False,
          **(state or {})}
    out, groups = [], []
    for item in commands(cmd):
        if item[0] == "open":
            groups.append(_copy(st) if item[1] else None)
        elif item[0] == "close":
            saved = groups.pop() if groups else None
            st = saved or st                                   # a subshell's cd and variables end with it
        else:
            saved = _copy(st) if item[2] else None
            for sub in (s for w in item[1] for s in w.subs):
                out += _runs_off_the_workdir(sub, _copy(st))
            out += _one_command(list(item[1]), st)
            st = saved or st
    return out


def _copy(st: dict) -> dict:
    return {**st, "dirs": list(st["dirs"]), "env": dict(st["env"]), "var": dict(st["var"]), "marked": set(st["marked"])}


def _expanded(word: str, st: dict) -> str:
    """A word with the variables the walk knows put in — a loop's as the first pattern it ranges over, so
    `I={inputs}; python $I/t.py` and `for f in {inputs}/*.py; do python "$f"` read as they run; others as they stand.
    The current directory is the one the walk is in NOW — inside `{inputs}` that place, in the working directory left
    as written, an absolute path the contract names."""
    if st["here"] is not None:
        word = _CWD.sub(posixpath.join(INPUTS_TOKEN, st["here"]).rstrip("/"), word)
    values = {**st["var"], **st["env"]}
    return _VARIABLE.sub(lambda m: values.get(m.group(1) or m.group(2), m.group(0)), word)


def _one_command(words: list, st: dict) -> list[tuple]:
    """One simple command over the walked state `st`: what it runs, and what it changes of the state."""
    words, env, assigned = _prefixed([_expanded(w, st) for w in words], st)
    if not words:                                              # assignments alone set the shell's variables
        for name, value in assigned.items():
            _set(st, name, value)
        return []
    if words[:2] in (["uv", "run"], ["coverage", "run"], ["poetry", "run"]):
        words = (["python"] if words[2:3] and words[2].endswith(".py") else []) + words[2:]
    prog, args = PurePosixPath(words[0]).name, words[1:]
    if prog in _BUILTINS:
        _BUILTINS[prog](args, st)
    elif prog == "eval":
        return _runs_off_the_workdir(" ".join(args), _copy(st))
    elif prog in _SHELLS:
        return _shell_run(args, st["here"], env)
    elif _INTERPRETER.fullmatch(prog) or prog in _RUNNERS:
        return _python_run(words, st["here"], env)
    elif "/" in words[0] and (rel := _rel(words[0], st["here"])) and not rel.startswith(".."):
        if rel.endswith(".py"):
            return _python_run(["python", *words], st["here"], env)   # a pinned program run by its `#!`
        return [("script", (rel, {"here": st["here"], "env": env}), None)]
    return []


def _prefixed(words: list, st: dict) -> tuple[list, dict, dict]:
    """The command past its assignments and wrappers (`env`, `timeout 5`, `nice -n 1`, …): (its words, the
    environment it runs with, the assignments that stand before it)."""
    env, assigned = dict(st["env"]), {}
    while words and (_ASSIGNMENT.match(words[0]) or PurePosixPath(words[0]).name in _WRAPPERS):
        w = words.pop(0)
        if m := _ASSIGNMENT.match(w):
            env[m.group(1)] = assigned[m.group(1)] = m.group(2)
            continue
        while words and (words[0].startswith("-") or re.fullmatch(r"[\d.]+[smhd]?", words[0])):
            if words[0] in ("-i", "--ignore-environment"):
                env.clear()
            elif words[0] in ("-u", "--unset") and words[1:2]:
                env.pop(words[1], None)
            words = words[2:] if words[0] in _WRAPPER_VALUED else words[1:]
    return words, env, assigned


def _set(st: dict, name: str, value: str) -> None:
    """A variable assigned: into the environment where it is exported, marked for export, or `set -a` holds."""
    if st["all"] or name in st["env"] or name in st["marked"]:
        st["env"][name] = value
        st["marked"].discard(name)
    else:
        st["var"][name] = value


def _export(args: list, st: dict) -> None:
    for w in (a for a in args if not a.startswith("-")):
        name, eq, value = w.partition("=")
        if eq:
            st["env"][name] = value
        elif name in st["var"]:
            st["env"][name] = st["var"][name]
        else:
            st["marked"].add(name)
        st["var"].pop(name, None)


def _declare(args: list, st: dict) -> None:
    if any(a.startswith("-") and "x" in a for a in args):
        return _export(args, st)
    for name, eq, value in (a.partition("=") for a in args if not a.startswith("-")):
        if eq:
            _set(st, name, value)


def _unset(args: list, st: dict) -> None:
    for name in args:
        st["env"].pop(name, None)
        st["var"].pop(name, None)
        st["marked"].discard(name)


def _set_options(args: list, st: dict) -> None:
    st["all"] = "-a" in args or "allexport" in args or (st["all"] and "+a" not in args)


def _cd(args: list, st: dict) -> None:
    target = next((w for w in args if not w.startswith("-") or w == "-"), "")
    st["here"], st["back"] = (st["back"], st["here"]) if target == "-" else (_moved(st["here"], target), st["here"])


def _pushd(args: list, st: dict) -> None:
    st["dirs"].append(st["here"])
    _cd(args, st)


def _popd(args: list, st: dict) -> None:
    st["here"] = st["dirs"].pop() if st["dirs"] else st["here"]


def _for(args: list, st: dict) -> None:
    if len(args) > 2 and args[1] == "in":
        st["var"][args[0]] = args[2]


#: the shell's own commands that change the state a later program starts in
_BUILTINS = {"cd": _cd, "pushd": _pushd, "popd": _popd, "export": _export, "declare": _declare, "typeset": _declare,
             "unset": _unset, "set": _set_options, "for": _for}


def _shell_run(args: list, here: Optional[str], env: dict) -> list[tuple]:
    """A shell started on a command (`-c`) or a script: what it runs, in a process that inherits only the
    environment."""
    j, opts = 0, []
    while j < len(args) and args[j][:1] in "-+" and args[j] != "--":
        w = args[j]                                            # `-euo pipefail`: each o or O takes the next word
        opts.append(w)
        j += 1 + (w in _SHELL_LONG_VALUED if w.startswith("--") else w[1:].count("o") + w[1:].count("O"))
    if j >= len(args):
        return []
    if any("c" in o[1:] for o in opts if not o.startswith("--")):
        return _runs_off_the_workdir(args[j], {"here": here, "env": dict(env)})
    rel = _rel(args[j], here)
    return [("script", (rel, {"here": here, "env": dict(env)}), None)] if rel and not rel.startswith("..") else []


def _interpreter_options(words: list) -> tuple[set, Optional[str], str, int]:
    """An interpreter's options as Python reads them: (its flag letters, `-m`/`-c` or None, that mode's module or
    code, the index of the first word after them) — `-Im pytest` is the flag I and then `-m pytest`."""
    flags, i = set(), 1
    while i < len(words) and words[i].startswith("-") and words[i] not in ("-", "--"):
        w, i = words[i], i + 1
        for k, ch in enumerate(w[1:] if not w.startswith("--") else "", 1):
            if ch in "mc":
                return flags, "-" + ch, w[k + 1:] or (words[i] if i < len(words) else ""), i + (not w[k + 1:])
            if ch in _PY_VALUED:
                i += not w[k + 1:]
                break
            flags.add(ch)
    return flags, None, "", i


def _pytest_options(rest: list, here: Optional[str]) -> tuple[list, bool]:
    """pytest's arguments (what it collects) and whether its own `pythonpath` setting names the working directory —
    relative to where pytest starts, in any of its spellings (`-o x`, `-ox`, `--override-ini[=]x`)."""
    args, named, j = [], False, 0
    while j < len(rest):
        w, j = rest[j], j + 1
        value = None
        if w in ("-o", "--override-ini"):
            value, j = (rest[j] if j < len(rest) else ""), j + 1
        elif w.startswith(("--override-ini=", "-o")):
            value = w.partition("=")[2] if w.startswith("--") else w[2:]
        elif w in _PYTEST_VALUED:
            j += 1
        if value is not None and value.startswith("pythonpath="):
            named = named or _on_the_path(value.partition("=")[2], here)
        if not w.startswith("-"):
            args.append(w.split("::")[0])
    return args, named


def _python_run(words: list, here: Optional[str], env: dict) -> list[tuple]:
    """One interpreter or test-runner invocation started `here` with environment `env`: what it runs from `{inputs}`
    with the working directory off its path."""
    runner = _RUNNERS.get(PurePosixPath(words[0]).name)
    flags, mode, target, i = (set(), None, "", 1) if runner else _interpreter_options(words)
    pp = env.get("PYTHONPATH")
    named = pp is not None and not flags & {"I", "E"} and _on_the_path(pp, here)
    dropped = bool(flags & {"I", "P"} or (env.get("PYTHONSAFEPATH") and "E" not in flags))
    runner = _RUNNERS.get(target) if mode == "-m" else runner
    if mode and not runner:
        if named or (here is None and not dropped):            # -m and -c put the working directory first
            return []
        return [("code", target, None)] if mode == "-c" else [("module", (here, target), None)]
    if not runner:
        script = words[i] if i < len(words) else ""
        return [m for m in [_in_inputs(script, here, None)] if m and script.endswith(".py") and not named]
    rest = words[i:]
    if runner == "unittest":
        runs = _unittest(rest, here, dropped and not named)
    else:
        args, by_ini = _pytest_options(rest, here)
        named = named or by_ini
        runs = [_in_inputs(a, here, runner) for a in args or ([] if runner == "doctest" else ["."])]
    if named or (mode == "-m" and here is None and not dropped):
        return [r for r in runs if r and r[0] == "unimportable"]
    return [r for r in runs if r]


def _unittest(rest: list, here: Optional[str], dropped: bool) -> list:
    """What `-m unittest` runs: its discovery (from `-s`, default here, files matching `-p`, default `test*.py`), or
    the modules, classes or files it is named."""
    opts, pos, j = {}, [], 0
    while j < len(rest):
        w, j = rest[j], j + 1
        if w in _UNITTEST_VALUED:
            opts[w.lstrip("-")[:1]], j = (rest[j] if j < len(rest) else ""), j + 1
        elif not w.startswith("-"):
            pos.append(w)
    if not pos or pos[0] == "discover":
        p = pos[1:]
        start, pattern = opts.get("s") or (p[0] if p else "."), opts.get("p") or (p[1] if len(p) > 1 else "test*.py")
        return [_in_inputs(start, here, pattern)]
    return [_unittest_file(n, here, dropped) if n.endswith(".py") or "/" in n else ("module", (here, n), None)
            for n in pos]


def _unittest_file(name: str, here: Optional[str], dropped: bool) -> Optional[tuple]:
    """A file unittest is named by path: it imports it as a module named by its path from where it starts, so one
    outside that directory, or any where the start directory is off the path (`-I`, `-P`, PYTHONSAFEPATH), it cannot
    import at all — ("unimportable", name, None), whatever the delivery holds."""
    rel = _rel(name, here)
    if rel is not None and (dropped or here is None
                            or here != ".." and posixpath.relpath(rel, here or ".").startswith("..")):
        return ("unimportable", name, None)
    return _in_inputs(name, here, None)


def _rel(path: str, here: Optional[str]) -> Optional[str]:
    """`path` as a path inside `{inputs}` — "" its top, ".." its parent, "../…" beyond — or None off it."""
    if path.startswith(INPUTS_TOKEN):
        rel = path[len(INPUTS_TOKEN):].lstrip("/")
    elif here is not None and not path.startswith(("/", "$", "~")):
        rel = posixpath.join(here, path)
    else:
        return None
    rel = posixpath.normpath(rel) if rel else "."
    return "" if rel == "." else rel


def _in_inputs(path: str, here: Optional[str], collect: Optional[str]) -> Optional[tuple]:
    """("file", name, collect) / ("glob", pattern, collect) where `path` lies in `{inputs}` — named under it, or
    relative from inside it; from its parent, a directory collected whole holds it."""
    rel = _rel(path, here)
    if rel == ".." and collect:
        return ("glob", "*", collect)
    if rel is None or rel.startswith(".."):
        return None
    if not any(ch in rel for ch in "*?[") and (rel.endswith(".py") or collect == "doctest" and rel):
        return ("file", rel, collect)
    return ("glob", rel if any(ch in rel for ch in "*?[") else (rel + "/*" if rel else "*"), collect)


def _added_paths(tree: ast.AST) -> list[str]:
    """The text of each path a source adds to its own `sys.path` — `insert`, `append`, `extend`, an assignment, or
    `site.addsitedir` — its names spelled out through the source's own assignments."""
    names = {t.id: ast.unparse(n.value) for n in ast.walk(tree) if isinstance(n, ast.Assign)
             for t in n.targets if isinstance(t, ast.Name)}
    added = [a for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and (ast.unparse(n.func) in ("sys.path.insert", "sys.path.append", "sys.path.extend", "site.addsitedir"))
             for a in n.args[-1:]]
    assigned = [(n.value, n.targets) for n in ast.walk(tree) if isinstance(n, ast.Assign)]
    assigned += [(n.value, [n.target]) for n in ast.walk(tree) if isinstance(n, ast.AugAssign)]
    added += [v for v, targets in assigned if any("sys.path" in ast.unparse(t) for t in targets)]
    out = []
    for a in added:
        text = ast.unparse(a)
        for _ in range(4):
            text = re.sub(r"\b[A-Za-z_]\w*\b", lambda m: f"({names[m.group(0)]})" if m.group(0) in names else m.group(0),
                          text)
        out.append(text)
    return out


def _imported(body: str) -> Optional[set[str]]:
    """The top-level modules a Python source imports — None where it cannot be parsed, or puts on its own path what
    may be the working directory: the current directory, the environment, anything not taken from where the program
    itself lies (`__file__`, `sys.argv[0]`), which is `{inputs}` or above it, never the delivery. A source too deep to
    parse decides nothing either."""
    # …the whole reading, not the parse alone: Python 3.14 parses a source 3.11 found too deep and then recursed in
    # `ast.unparse` (red on CI's 3.14 legs)
    try:
        tree = ast.parse(body)
        added = _added_paths(tree)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    if any(not re.search(r"__file__|sys\.argv\[0\]", p) or re.search(r"getcwd|cwd\(\)|environ|PWD", p)
           for p in added):
        return None
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    return names | {n.module.split(".")[0] for n in ast.walk(tree)
                    if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module}


def _imports_beyond(files: Mapping[str, str], start: Iterable[str]) -> set[str]:
    """What the sources `start` import, through the probe's own files they import in turn, that is neither the stdlib,
    nor one of those files, nor the test runner — what the delivery would have to hold."""
    local = {PurePosixPath(f).parts[0].removesuffix(".py"): f for f in files if PurePosixPath(f).parts}
    out, seen, todo = set(), set(), list(start)
    while todo:
        body = todo.pop()
        if body in seen:
            continue
        seen.add(body)
        names = _imported(body)
        if names is None:
            continue
        for n in names - set(sys.stdlib_module_names) - {"__future__", "pytest", "_pytest"}:
            if n in local:
                f = local[n]
                todo.append(files.get(f) or files.get(f"{n}/__init__.py", ""))
            else:
                out.add(n)
    return out


def _module_file(where: tuple, files: Mapping[str, str]) -> Optional[str]:
    """The probe file a dotted name started `here` imports — `test_x.Case.test_one` is `test_x.py` — if it is one."""
    here, dotted = where
    if here is None or here == "..":                           # started off `{inputs}`, Python does not look there
        return None
    parts = dotted.split(".")
    for k in range(len(parts), 0, -1):
        base = posixpath.join(here or "", *parts[:k])
        for f in (base + ".py", base + "/__init__.py"):
            if f in files:
                return f
    return None


def _collected(f: str, collect: Optional[str]) -> bool:
    """Whether the runner `collect` picks the file `f` out of a pattern: pytest its test files and conftests, doctest
    and a plain program every Python file, unittest the files its discovery pattern matches."""
    if collect == "pytest":
        return bool(_COLLECTED.search(f))
    if collect in (None, "doctest"):
        return f.endswith(".py")
    return fnmatch.fnmatch(PurePosixPath(f).name, collect)


def _script_runs(where: tuple, files: Mapping[str, str], depth: int) -> list:
    """What a pinned shell script runs, its own name and directory put in for `$0` and `$(dirname "$0")`."""
    name, state = where
    if depth >= _SCRIPT_DEPTH or name not in files:
        return []
    own_dir = posixpath.join(INPUTS_TOKEN, posixpath.dirname(name)).rstrip("/")
    text = _OWN_DIR.sub(own_dir, files[name])
    return _runs_off_the_workdir(_OWN_NAME.sub(f"{INPUTS_TOKEN}/{name}", _own_place(text, own_dir)), state)


def _own_place(text: str, own_dir: str) -> str:
    """A pinned script's text with each substitution that asks where the script itself lies put in as that place —
    the script's directory where it takes a `dirname` (`$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)`,
    `$(dirname "$(readlink -f "$0")")`, …), the script itself where it does not — however the asking is wrapped."""
    out, i = [], 0
    while (k := text.find("$(", i)) >= 0:
        end = substitution_end(text, k + 2)
        inner = text[k:end]
        mine = _OWN_NAME.search(inner) and not inner.startswith("$((")
        out.append(text[i:k] + ((own_dir if "dirname" in inner else _OWN_NAME.search(inner).group(0)) if mine else inner))
        i = end
    return "".join(out) + text[i:]


def _examples(text: str) -> str:
    """The Python a doctest runs out of `text` — nothing where its examples cannot be read."""
    try:
        return "\n".join(e.source for e in doctest.DocTestParser().get_examples(text))
    except ValueError:
        return ""


def _with_scripts(runs: list, files: Mapping[str, str], depth: int = 0) -> list:
    """The runs with each pinned shell script's own runs in its place, read from its pinned text."""
    out = []
    for r in runs:
        out += _with_scripts(_script_runs(r[1], files, depth), files, depth + 1) if r[0] == "script" else [r]
    return out


def _bodies_run(runs: list, files: Mapping[str, str]) -> list[str]:
    """The sources the runs execute: a program's own, a pattern's matches as its runner collects them, a module's, a
    `-c`'s text, a doctest's examples, a pinned script's own runs, and the conftests pytest loads beside what it runs —
    none of pytest's where one of those conftests arranges the path itself."""
    runs = _with_scripts(runs, files)
    conftests = {f: b for f, b in files.items() if PurePosixPath(f).name == "conftest.py"}
    if any(r[2] == "pytest" for r in runs) and any(_imported(b) is None for b in conftests.values()):
        runs = [r for r in runs if r[2] != "pytest"]
    out = []
    for kind, what, collect in runs:
        if kind == "unimportable":
            continue
        if kind == "code":
            out.append(what)
            continue
        if kind == "module":
            what, kind = _module_file(what, files) or "", "file"
        found = [what] if kind == "file" else [f for f in files if fnmatch.fnmatch(f, what) and _collected(f, collect)]
        out += [files.get(f, "") for f in found]
        if collect == "doctest":
            out += [_examples(files.get(f, "")) for f in found]
        if collect == "pytest":
            d = posixpath.dirname(what.split("*")[0].split("?")[0].split("[")[0])
            out += [b for f, b in conftests.items() if (posixpath.dirname(f) + "/") in ("/", d + "/")
                    or d.startswith(posixpath.dirname(f) + "/")]
    return out


def _files_of(probe: Probe) -> dict[str, str]:
    """A probe's pinned files by their path inside `{inputs}`."""
    return {PurePosixPath(path.replace("\\", "/")).as_posix(): body for path, body in probe.inputs or ()}


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
    thirteen). A command that sets `PYTHONPATH` is out of this shape whatever it sets it to — the path it
    names is then the contract's, visible, not the environment's — unless the interpreter ignores it (`-I`, `-E`)
    or a relative one set inside `{inputs}` names the probe's own directory (`_runs_off_the_workdir`)."""
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        for p in (c.check or ()):
            cmd = p.command or ""
            if not p.inputs:
                continue
            files = _files_of(p)
            if _imports_beyond(files, _bodies_run(_runs_off_the_workdir(cmd), files)):
                out.setdefault(c.name, []).append(cmd)
    return out


#: The one wording of that refusal, for every door that admits a contract.
UNITTEST_UNIMPORTABLE = ("its probe has unittest import a file by a path outside the directory it starts in, which "
                         "unittest cannot import whatever is delivered — every run fails and decides nothing; from the "
                         "working directory, run it as `python -m unittest discover -s {inputs} -p test_x.py` or "
                         "`python -m pytest {inputs}/test_x.py`")


def probes_unittest_cannot_import(criteria: Iterable[Criteria]) -> dict[str, list[str]]:
    """{criterion: [pinned commands that have unittest import a file outside the directory it starts in]}. unittest
    turns such a path into a module name it cannot import, so the probe fails over any delivery (critic over the probe
    guard, run in a container, 2026-11-14): a check that cannot pass forbids nothing a delivery could change."""
    out: dict[str, list[str]] = {}
    for c in criteria or ():
        if bad := [p.command for p in (c.check or ()) if any(
                r[0] == "unimportable" for r in _with_scripts(_runs_off_the_workdir(p.command or ""), _files_of(p)))]:
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
    return out


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
            if _ROUND.search(w) and "/probe_inputs/" not in w.replace("\\", "/")]


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
        # (`share`, `tools_llm._fold`); unmarked, a root FAIL with 1 refuting probe of 1,336 grew the store by hundreds a
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


def round_of(path) -> Optional[tuple[str, str]]:
    """(the round's own path, its name in the record — `.gfso-scratch-<place>/<round>`, one spelling whatever separators
    the path came in) of the validation or contact round `path` lies in; None for no round's."""
    m = re.match(r"(.*?[\\/](\.gfso-scratch-[^\\/]+)[\\/]+([^\\/]+))", str(path))
    return (m.group(1), f"{m.group(2)}/{m.group(3)}") if m else None


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


#: the seconds one exact pinned check the system runs may take, its build included — the bound every reader names
PROBE_S = 60
#: …and whether every one of them had its WHOLE bound (no budget cutting it): then the same tree times out again, and
#: asking the validation again only pays for the same ⊥ (`BOUND_SPENT`, the dispatcher's `no-verdict:bound`)
PAST_WHOLE = "past_bound_whole"
#: a shell's exit when the command could not be run at all — not found, not executable: no observation of the delivery
NOT_RUN_RC = (126, 127)
#: said in a refusal whose every unobserved criterion is PAST_WHOLE — read by the dispatcher, which stops re-asking
BOUND_SPENT = ("NOT ASKED AGAIN: every unobserved check ran past its whole own bound on this delivered tree, which would "
               "time out again — VALIDATING's bound hands the node to its issuer (§12.2), who may re-pin the check to finish "
               f"inside the system's fixed per-check bound, {PROBE_S} s with its build (a slow corpus split across "
               "checks), or cancel")


def with_engine_observations(per_criterion: Sequence[Mapping], criteria: Sequence[Criteria],
                             parts: Mapping[str, Sequence[Criteria]] | None, observed: Mapping | None,
                             edited: Sequence[str] = ()) -> list:
    """The report with what the system itself observed of its pinned probes (`observed`: {probe id: {matched,
    out, note}}, `tools_llm._observe_pins`) put where every reader of `held` reads it: a probe it saw print other than
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
        e = {k: v for k, v in e.items() if k not in (PAST_BOUND, PAST_WHOLE, OVER_A_PASS, ON_NO_DELIVERY)}
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


def same_probe(p: Probe) -> tuple:
    """What makes two pinned probes ONE observation over a delivery — the same command, expectation and inputs, as
    `integrate` copying `scaffold`'s check or the root's: whatever ids they are pinned under, running one is running
    each. THE one identity: the packet owes such a probe once (`packets.owed_probes`) and a citation of any of its ids
    credits all of them (`part_credit`)."""
    # …NOT `exact`: it says who can decide the output, not what running the command observes — told apart by it, one
    # run of a command pinned twice would be owed twice and credit only the copy it was cited by
    return p.command.strip(), (p.expect or "").strip(), tuple(p.inputs or ())


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
                f"the time they were given — undecided")
        if e.get(ON_NO_DELIVERY):     # …nor a pass observed on no delivered tree: the same ⊥, the report's to redo
            gaps.setdefault(str(e.get("criterion")), []).extend(map(str, e[ON_NO_DELIVERY]))
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
