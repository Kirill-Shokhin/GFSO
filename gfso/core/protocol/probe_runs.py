"""What a pinned probe's command RUNS, walked as the shell runs it: which Python starts, from which directory, under
which environment, and what the pinned programs it starts import.

Why a module of its own: the two admission rungs it answers (`probes_off_the_workdir`, `probes_unittest_cannot_import`)
are questions about where Python looks for the delivery, and only a walk of the shell's own reading (`shell.commands`)
decides them — a walk with a state of its own (the directory, the pushd stack, the variables) that nothing else in the
pinned procedure reads. `procedure.admission_defects` asks the two rungs; nothing here asks the procedure back.
"""
from __future__ import annotations

import ast
import doctest
import fnmatch
import posixpath
import re
import sys
from pathlib import PurePosixPath
from typing import Iterable, Mapping, Optional

from gfso.core.types import INPUTS_TOKEN, Criteria, Probe
from gfso.core.protocol.shell import commands, substitution_end


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
