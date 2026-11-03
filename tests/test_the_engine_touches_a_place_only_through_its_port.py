"""The engine touches a place's files only through its execution's port.

A node's place, a judge's copy, a validation's round, a node's temp and the system's own copies are the execution's
(`ExecutionPort`): where it runs them in a container they are its files, read and written there by the system — and
the slice that moves them into Docker's volumes leaves them nowhere on this host. A host call over one of them reads a
directory an agent wrote with the host's eyes (a link it made is followed on the host), or reads nothing once the place
is gone from the host — both silent. So in the modules that work over places no direct file call stands but those
listed below, each of which touches the base (the user's repository, the host's until it moves too) or the host's own
state, never a place.
"""
import ast
from pathlib import Path

GFSO = Path(__file__).resolve().parents[1] / "gfso"
#: the modules that work over places
RADIUS = ("workspaces.py", "adapters/worktrees.py", "adapters/snapshots.py", "tools_llm.py", "delegate.py",
          "issuer/__init__.py", "packets.py", "core/protocol/procedure.py", "adapters/execution.py",
          "adapters/llm/toolloop.py", "adapters/llm/headless.py", "adapters/llm/chat.py", "adapters/llm/conformance.py",
          "roster.py", "observe.py", "sessions.py")
#: a path's own methods that touch the file system, and how many positional arguments the path's form takes — the
#: port's methods of the same name take the path first (`ex.is_dir(p)`), which is what tells the two apart
PATH_CALLS = {**dict.fromkeys(("is_dir", "is_file", "exists", "iterdir", "read_text", "read_bytes", "mkdir", "unlink",
                               "stat", "lstat", "rmdir", "touch", "is_symlink"), 0),
              **dict.fromkeys(("write_text", "write_bytes"), 1), **dict.fromkeys(("glob", "rglob"), None)}
MODULE_CALLS = {"shutil": None, "tempfile": None,
                "os": {"listdir", "scandir", "walk", "remove", "unlink", "mkdir", "makedirs", "rmdir", "chmod", "stat",
                       "lstat", "rename", "replace", "readlink", "symlink"},
                "os.path": {"exists", "isdir", "isfile", "lexists", "islink", "getsize", "getmtime"}}

#: (module, function, call) -> why it touches no place
HOSTS_OWN = {
    ("tools_llm.py", "_in_the_default", "os.path.isdir(c.get('workdir') or '')"): "a registered workdir on this host, as the roster checks it at registration",
    ("adapters/execution.py", "_no_places", "base.is_dir()"): "the user's own repository on the host, read as its import is",
    ("adapters/execution.py", "_no_places", "shutil.which('git')"): "the user's own git on the host, as its import uses",
    ("workspaces.py", "stands", "Path(where).is_dir()"): "a directory that is no node's place is a base",
    ("workspaces.py", "made", "HOST.is_dir(place)"): "the legacy record's fallback, a host directory until V2",
    ("core/protocol/procedure.py", "_gone", "HOST.exists(path)"): "a path in no round: the base or outside the places",
    ("core/protocol/procedure.py", "_gone", "HOST.exists(str(Path(path).parent))"): "a path in no round, as above",
    ("adapters/worktrees.py", "is_repo_top", "shutil.which('git')"): "this host's git",
    ("adapters/worktrees.py", "is_repo_top", "Path(base).is_dir()"): "the base",
    ("adapters/execution.py", "Volume._import_base", "open(carried, 'rb')"): "the user's repository, carried in",
    ("adapters/execution.py", "Volume._import_base", "tempfile.TemporaryDirectory(prefix='gfso-import-')"):
        "the user's repository, carried in",
    ("adapters/execution.py", "_carried_in",
     "(d / 'branch').write_text(git('symbolic-ref', '-q', '--short', 'HEAD').stdout.strip() or 'main')"):
        "the user's repository, carried in",
    ("adapters/execution.py", "_carried_in",
     "(p := (base / git('rev-parse', '--git-path', f'info/{n}').stdout.strip())).is_file()"):
        "the user's repository, carried in",
    ("adapters/execution.py", "_carried_in", "base.is_dir()"): "the user's repository, carried in",
    ("adapters/execution.py", "_is_top", "base.is_dir()"): "the user's repository, carried in",
    ("adapters/execution.py", "_is_top", "shutil.which('git')"): "this host's git",
    ("adapters/execution.py", "_lfs_of", "(f := Path(lfs.path_in(str(store), oid))).is_file()"):
        "the user's repository, carried in",
    ("adapters/execution.py", "_lfs_of", "f.stat()"): "the user's repository, carried in",
    **{("adapters/execution.py", "stored_on_host", call): "the user's LFS store, the accepted result's objects landing"
       for call in ("(at := Path(lfs.path_in(str(store), oid))).is_file()", "at.stat()", "os.replace(tmp, at)",
                    "(tmp := at.with_name(f'{oid}.gfso-{uuid.uuid4().hex}')).write_bytes(data)",
                    "at.parent.mkdir(parents=True, exist_ok=True)")},
    ("adapters/execution.py", "Volume.land_tree", "shutil.rmtree(to)"): "a host directory of the user's: the result",
    ("adapters/execution.py", "Volume.land_tree", "to.exists()"): "a host directory of the user's: the result",
    ("adapters/execution.py", "fetched_on_host", "(f := (Path(d) / 'accepted.bundle')).write_bytes(bundle)"):
        "the accepted result, landing in the user's repository",
    ("adapters/execution.py", "fetched_on_host", "tempfile.TemporaryDirectory(prefix='gfso-land-')"):
        "the accepted result, landing in the user's repository",
    ("tools_llm.py", "_keep_rejected_report", "d.mkdir(parents=True, exist_ok=True)"): "the server's state",
    ("tools_llm.py", "_keep_rejected_report",
     "f.write_text('# refused as a verdict: ' + defects + '\\n\\n' + text, encoding='utf-8')"): "the server's state",
    ("tools_llm.py", "_validator_texts",
     "(Path(__file__).parent / 'mcp' / 'prompts' / 'validator.md').read_text(encoding='utf-8')"): "the product's prompt",
    ("tools_llm.py", "_named_documents", "Path(tok).is_file()"): "a name in the user's request; only one in a base is read",
    ("tools_llm.py", "_named_documents", "p.is_file()"): "a file of a base",
    ("tools_llm.py", "_named_documents", "p.stat()"): "a file of a base",
    ("tools_llm.py", "_named_documents", "p.read_bytes()"): "a file of a base",
    ("tools_llm.py", "_work_places", "Path(w).is_dir()"): "a role's workdir: a base",
    ("delegate.py", "_oracle_workdir", "Path(vcfg['oracle_map']).read_text(encoding='utf-8')"): "the issuer's oracle map",
    ("delegate.py", "_checker_validate", "Path(vcfg['oracle_map']).read_text(encoding='utf-8')"): "the issuer's oracle map",
    ("delegate.py", "_checker_validate", "Path(entry['canonical']).read_text(encoding='utf-8')"): "the hidden tests",
    ("issuer/__init__.py", "_prompt", "PROMPT.read_text(encoding='utf-8')"): "the product's prompt",
    ("sessions.py", "_spawn", "(_PROMPTS / prompt).read_text(encoding='utf-8')"): "the product's prompt",
    ("roster.py", "_put_atomically", "tmp.write_text(text, encoding='utf-8')"): "the roster file",
    ("roster.py", "_put_atomically", "tmp.unlink(missing_ok=True)"): "the roster file",
    ("roster.py", "_put_atomically", "os.replace(tmp, path)"): "the roster file",
    ("roster.py", "missing_workdir", "Path(wd).is_dir()"): "a role's workdir: a base",
    ("roster.py", "AgentRegistry._load_locked", "self._path.stat()"): "the roster file",
    ("roster.py", "AgentRegistry._load_locked", "self._path.read_text(encoding='utf-8')"): "the roster file",
    ("roster.py", "AgentRegistry.register", "Path(workdir).is_dir()"): "a role's workdir: a base",
    ("roster.py", "AgentRegistry._write", "self._path.parent.mkdir(parents=True, exist_ok=True)"): "the roster file",
    ("roster.py", "AgentRegistry._write", "lock.stat()"): "the roster's lock",
    ("roster.py", "AgentRegistry._write", "lock.unlink(missing_ok=True)"): "the roster's lock",
    ("roster.py", "AgentRegistry._write", "self._path.stat()"): "the roster file",
    ("adapters/llm/headless.py", "ClaudeCodeProvider._read_stream", "Path(tdir).mkdir(parents=True, exist_ok=True)"):
        "the audit trace",
    ("adapters/llm/headless.py", "ClaudeCodeProvider._read_stream", "open(Path(tdir) / f\"{time.strftime('%Y%m%dT%H%M%S')}-"
     "{uuid.uuid4().hex[:8]}-{''.join((c if c.isalnum() else '_' for c in self.stage_hint or 'call'))[-60:]}.jsonl\", "
     "'w', encoding='utf-8', buffering=1)"): "the audit trace",
    ("adapters/llm/headless.py", "_Hooks.arm", "_HOOK.read_bytes()"): "the system's own hook script",
    ("adapters/llm/toolloop.py", "_open_trace", "Path(tdir).mkdir(parents=True, exist_ok=True)"): "the audit trace",
    ("adapters/llm/toolloop.py", "_open_trace", "open(Path(tdir) / f\"{time.strftime('%Y%m%dT%H%M%S')}-"
     "{uuid.uuid4().hex[:8]}-{tag}.jsonl\", 'w', encoding='utf-8', buffering=1)"): "the audit trace",
    ("adapters/execution.py", "_env_names", "Path(env_file).read_text(encoding='utf-8')"): "the operator's env-file",
    ("adapters/execution.py", "scrubs", "shutil.which('bwrap')"): "this host's bubblewrap",
    ("adapters/execution.py", "LocalExecution.which", "shutil.which(program)"): "this host's PATH",
    ("adapters/execution.py", "LocalExecution.temp_root", "tempfile.gettempdir()"): "this host IS the place",
    ("adapters/execution.py", "LocalExecution.copy_tree", "shutil.copytree(src, dst, symlinks=True)"): "this host IS the place",
    ("adapters/execution.py", "LocalExecution.remove_tree", "os.path.lexists(path)"): "this host IS the place",
    ("adapters/execution.py", "LocalExecution.remove_tree", "os.walk(path)"): "this host IS the place",
    ("adapters/execution.py", "LocalExecution.remove_tree", "os.path.islink((p := os.path.join(d, x)))"): "this host IS the place",
    ("adapters/execution.py", "LocalExecution.remove_tree",
     "shutil.rmtree(path, onerror=lambda fn, p, _: (_own(p), fn(p)))"): "this host IS the place",
    ("adapters/execution.py", "LocalExecution.shell", "shutil.which('git')"): "this host's git",
    ("adapters/execution.py", "LocalExecution.shell",
     "(b := (Path(git).resolve().parents[1] / 'bin' / 'bash.exe')).is_file()"): "this host's bash",
    ("adapters/execution.py", "LocalExecution.shell", "shutil.which('bash')"): "this host's bash",
    ("adapters/execution.py", "_own", "os.chmod(path, os.lstat(path).st_mode | stat.S_IRWXU)"): "this host IS the place",
    ("adapters/execution.py", "_own", "os.lstat(path)"): "this host IS the place",
    ("adapters/execution.py", "end_leftovers", "shutil.which('docker')"): "this host's docker client",
    ("adapters/execution.py", "_system_run", "script.read_bytes()"): "the system's own script",
    ("adapters/execution.py", "Commands.start", "Path(shell.__file__).read_bytes()"): "the system's own script",
    ("adapters/execution.py", "_log_out", "mirror.is_file()"): "the host's mirror of a system container's log",
    ("adapters/execution.py", "_log_out", "mirror.read_text(encoding='utf-8')"): "the host's mirror of a log",
    ("adapters/execution.py", "_mirror", "mirror.parent.mkdir(parents=True, exist_ok=True)"): "the host's mirror of a log",
    ("adapters/execution.py", "_mirror", "mirror.write_text(text, encoding='utf-8')"): "the host's mirror of a log",
    # …a project's places as they stood on the host before its volume, read once to be copied in
    ("adapters/execution.py", "Volume.ready", "p.is_dir()"): "the host's leftover, or its CLI state of before",
    ("adapters/execution.py", "_left", "ex.own.is_dir()"): "the host's leftover of a project's places",
    ("adapters/execution.py", "_left", "ex.own.iterdir()"): "the host's leftover of a project's places",
    ("adapters/execution.py", "_left", "d.is_dir()"): "the host's leftover of a project's places",
    ("adapters/execution.py", "_left", "d.iterdir()"): "the host's leftover of a project's places",
    ("adapters/execution.py", "_left", "x.is_dir()"): "the host's leftover of a project's places",
    ("adapters/execution.py", "Volume._consume", "p.is_dir()"): "the host's leftover, consumed by its copy-in",
    ("adapters/execution.py", "Volume.export", "shutil.rmtree(to, ignore_errors=True)"): "an export's host directory",
    ("adapters/execution.py", "_left_inert", "(alt := (here / names.get('objects', 'objects') / 'info' / 'alternates')).exists()"): "an export's host directory",
    ("adapters/execution.py", "_left_inert", "(cfg := (here / names.get('config', 'config'))).is_dir()"): "an export's host directory",
    ("adapters/execution.py", "_left_inert", "(here / names['.git']).is_dir()"): "an export's host directory",
    ("adapters/execution.py", "_left_inert", "alt.is_symlink()"): "an export's host directory",
    ("adapters/execution.py", "_left_inert", "cfg.is_file()"): "an export's host directory",
    ("adapters/execution.py", "_left_inert", "cfg.is_symlink()"): "an export's host directory",
    ("adapters/execution.py", "_left_inert", "os.walk(to)"): "an export's host directory",
    ("adapters/execution.py", "_left_inert.gone", "os.chmod(d, stat.S_IRWXU)"): "an export's host directory",
    ("adapters/execution.py", "_left_inert.gone", "os.chmod(os.path.join(d, f), stat.S_IRUSR | stat.S_IWUSR)"): "an export's host directory",
    ("adapters/execution.py", "_left_inert.gone", "os.walk(p)"): "an export's host directory",
    ("adapters/execution.py", "_left_inert.gone", "p.is_dir()"): "an export's host directory",
    ("adapters/execution.py", "_left_inert.gone", "p.is_symlink()"): "an export's host directory",
    ("adapters/execution.py", "_left_inert.gone", "p.unlink()"): "an export's host directory",
    ("adapters/execution.py", "_left_inert.gone", "shutil.rmtree(p)"): "an export's host directory",
    ("adapters/execution.py", "_left_inert.gone", "os.path.islink(os.path.join(d, f))"): "an export's host directory",
    ("adapters/execution.py", "_untar", "os.readlink(p)"): "an export's host directory",
    ("adapters/execution.py", "_untar", "os.walk(root)"): "an export's host directory",
    ("adapters/execution.py", "_untar", "p.is_symlink()"): "an export's host directory",
    ("adapters/execution.py", "_untar", "p.unlink()"): "an export's host directory",
    ("adapters/execution.py", "_untar", "p.write_text(target, encoding='utf-8')"): "an export's host directory",
    ("adapters/execution.py", "_untar", "to.mkdir(parents=True, exist_ok=True)"): "an export's host directory",
    ("adapters/execution.py", "Volume.export",
     "(to.parent / '.gfso-export-notes').write_text('\\n'.join(notes) + '\\n', encoding='utf-8')"): "an export's notes",
    ("adapters/execution.py", "_untar", "at.parent.mkdir(parents=True, exist_ok=True)"): "an export's host directory",
    ("adapters/execution.py", "_untar", "os.symlink(m.linkname, at)"): "an export's host directory",
    ("adapters/execution.py", "_untar", "at.write_text(m.linkname, encoding='utf-8')"): "an export's host directory",
}


def _touches(path: Path, module: str) -> set:
    """(module, function, call) of every direct file call in `path`."""
    out, stack = set(), []

    class _V(ast.NodeVisitor):
        def generic_visit(self, n):
            named = isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            stack.append(n.name) if named else None
            if isinstance(n, ast.Call) and _direct(n.func, len(n.args)):
                out.add((module, ".".join(stack), ast.unparse(n)))
            super().generic_visit(n)
            stack.pop() if named else None
    _V().visit(ast.parse(path.read_text(encoding="utf-8-sig")))
    return out


def _direct(f, positional: int) -> bool:
    if isinstance(f, ast.Name):
        return f.id == "open"
    if not isinstance(f, ast.Attribute):
        return False
    if (mod := ast.unparse(f.value)) == "HOST":
        return True                                   # …this host's files by name: never a place's
    if mod in MODULE_CALLS:
        return MODULE_CALLS[mod] is None or f.attr in MODULE_CALLS[mod]
    return f.attr in PATH_CALLS and PATH_CALLS[f.attr] in (None, positional)


def test_no_direct_file_call_over_a_place_in_the_modules_that_work_over_places():
    found = set().union(*(_touches(GFSO / m, m) for m in RADIUS))
    stray = sorted(found - set(HOSTS_OWN))
    assert not stray, ("a direct file call where places are worked over — go through the execution's port "
                       f"(`ExecutionPort.read_bytes` & co.), or list it with why it is no place's: {stray}")
    assert not set(HOSTS_OWN) - found, f"listed but no longer called: {sorted(set(HOSTS_OWN) - found)}"


def test_the_guard_sees_a_host_call_and_passes_the_port(tmp_path):
    p = tmp_path / "m.py"
    p.write_text("def f(ex, place):\n    Path(place).is_dir()\n    ex.is_dir(place)\n    ex.write_bytes(place, b'')\n"
                 "    (Path(place) / 'x').write_bytes(b'')\n    os.listdir(place)\n    open(place)\n    HOST.is_dir(place)\n")
    assert {c for _, _, c in _touches(p, "m.py")} == {"Path(place).is_dir()", "(Path(place) / 'x').write_bytes(b'')",
                                                       "os.listdir(place)", "open(place)", "HOST.is_dir(place)"}
