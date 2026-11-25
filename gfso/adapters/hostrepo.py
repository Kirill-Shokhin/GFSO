"""THE PERSON'S OWN REPOSITORY ON THIS HOST, what a project asks of it before and after its work (a landing's moves stay in `worktrees`): is it a top a project can work over (`no_places`), what of it
an import carries in (`carried_in`, `committed`, `lfs_held`) and leaves out (`left_out`), and what a landing takes
into it (`fetched`, `stored`). Every git here is theirs — `G.run` plain, their config as their console reads it —:
over a repository an agent writes the system's runs APART, never through this module.
"""
from __future__ import annotations

import shutil
import tarfile
import tempfile
from pathlib import Path

from gfso.adapters import git as G, lfs
from gfso.config import for_the_hands, write_atomic
from gfso.core.types import PlaceUnavailable
from gfso.places import same_place


def _git(base: Path, **env):
    """git over the user's repository at `base`, run on the host by their own git (`G.run` plain): text out, or bytes
    fed `input`."""
    return lambda *a, input=None: G.run(base, *a, plain=True, extra=env, input=input, text=input is None)


def is_top(base: Path) -> bool:
    """`G.is_top` of the user's own repository, read by their own git as its import is."""
    return G.is_top(base, plain=True)


def no_places(base: Path) -> str | None:
    """Why a container runs no dispatched work over `base`: one that is no repository's top with a commit has no
    places — every session of the project would work in it, sharing one tree and one model client's state, no node's
    work its own and each reading the others'. Asked of the user's own repository on the host, as its import is."""
    if is_top(base):
        return None
    why = (f"{base} is not the top of a git repository with a commit, so its nodes have no places of their "
           f"own: every session would share one tree and read the others' conversations. ")
    # …walking up no further than the user's home: a home kept as a repository of its dotfiles is no work's top, and
    # naming it told the user's agent to import the home (critic)
    git = _git(base, GIT_CEILING_DIRECTORIES=str(Path.home()))
    top = git("rev-parse", "--show-toplevel") if shutil.which("git") and base.is_dir() else None
    # …a repository another account owns, which the user's own git refuses to trust: told to `git init` there, he was
    # sent to make a repository that exists; the trust is his decision, git's own words beside it (critic)
    if top is not None and top.returncode != 0 and "dubious ownership" in (top.stderr or ""):
        return (f"{base} is a git repository another account owns, and your own git does not trust it, so it is not "
                f"imported: git says «{top.stderr.strip().splitlines()[0]}». Trusting it runs that owner's hooks and "
                f"settings as you — your decision: "
                f"{for_the_hands(f'git config --global --add safe.directory {base.as_posix()}')}, then start the "
                f"project again")
    if top is not None and top.returncode != 0 and git("rev-parse", "--is-inside-git-dir").stdout.strip() == "true":
        return why + "It lies inside a repository's own `.git` directory: register that repository's top as the workdir"
    if top is not None and top.returncode == 0 and (at := top.stdout.strip()):
        if same_place(at, base):
            return why + f"It has no commit yet: {for_the_hands('git add -A && git commit -m start')} there"
        return why + (f"It lies inside the repository {at}: register that top as the workdir if the work is "
                      f"that repository's, else make this directory one of its own: "
                      f"{for_the_hands('git init && git add -A && git commit -m start')} there")
    return why + (f"Make it one: {for_the_hands('git init && git add -A && git commit -m start')} there, then start the "
                  f"project again")


def lfs_held(base: Path, rev: str) -> tuple[dict, list]:
    """`_lfs_of` the commit `rev` of the user's repository at `base`, read by their own git on the host — the objects
    a delivery made there is kept with (`store.keep`)."""
    return _lfs_of(base, _git(base), rev)


def _lfs_of(base: Path, git, rev: str = "HEAD") -> tuple[dict, list]:
    """({oid: its object in the user's LFS store}, [the paths whose object it lacks]) of the LFS pointers in `rev`'s
    tree — read as git stores them, so no git-lfs runs: a blob short enough to be a pointer and parsed as one
    (`lfs.parse`). An object counts where its size is the pointer's; its sha256 is checked where it is written (`lfs`).
    Missing ones are not fetched: that is the user's network and credentials, asked from no thread of the system."""
    entries = [e.split("\t", 1) for e in git("ls-tree", "-r", "-l", "-z", rev).stdout.split("\0") if "\t" in e]
    small = [(m[2], path) for meta, path in entries
             if (m := meta.split())[1] == "blob" and m[3].isdigit() and int(m[3]) <= lfs.LONGEST]
    if not small:
        return {}, []
    out = git("cat-file", "--batch", input="".join(f"{sha}\n" for sha, _ in small).encode()).stdout
    pointers, at = [], 0
    for _, path in small:                     # …`<sha> blob <size>\n<content>\n`, in the order asked
        nl = out.index(b"\n", at)
        size = int(out[at:nl].split()[2])
        pointers += [(path, p)] if (p := lfs.parse(out[nl + 1:nl + 1 + size])) else []
        at = nl + 2 + size
    if not pointers:
        return {}, []
    store = _lfs_store(base, git)
    held = {oid: f for _, (oid, size) in pointers
            if (f := Path(lfs.path_in(str(store), oid))).is_file() and f.stat().st_size == size}
    return held, [path for path, (oid, _) in pointers if oid not in held]


def _lfs_store(base: Path, git) -> Path:
    """The user's LFS store, where their git-lfs keeps objects: `lfs.storage` (in the git dir where relative), else
    `.git/lfs` — its `objects`."""
    common = base / git("rev-parse", "--git-common-dir").stdout.strip()
    return common / (git("config", "--get", "lfs.storage").stdout.strip() or "lfs") / "objects"


def _missing(git) -> list:
    """The objects HEAD's history names that the user's repository does not hold — a partial clone's, never fetched
    (`G.EVERY`)."""
    if not git("config", "--get-regexp", r"^(extensions\.partialclone|remote\..*\.promisor)$").stdout.strip():
        return []
    return [x[1:] for x in git("rev-list", "--objects", "--missing=print", "HEAD").stdout.splitlines()
            if x.startswith("?")]


def left_out(base: Path) -> list[str]:
    """What of the user's repository at `base` the import of its HEAD does not bring into the agents' copy, each said
    with what brings it — asked by their own git on the host, before any import as at one (`carried_in`)."""
    git = _git(base)
    return _left_out(base, git, _lfs_of(base, git)[1]) if is_top(base) else []


def _left_out(base: Path, git, no_object: list) -> list[str]:
    # …`matching`: an ignored directory said once, never walked (7 s against 51 ms on a 450k-file tree — critic)
    status = [x for x in git("status", "--porcelain", "--ignored=matching", "-z").stdout.split("\0") if x.strip()]
    # …the ignored ones apart: data and configs a .gitignore keeps out reached the agents as silently as a build's output
    # (the author, 2026-11-12: agents got a copy without the data and nobody told them) — named, what any checkout
    # regenerates counted only, else the caches sorted first filled the line and hid `data/` (critic)
    ignored = sorted((x[3:] for x in status if x.startswith("!! ") and not _regenerated(x[3:])),
                     key=lambda p: not p.endswith("/"))           # …directories first: data lives in them
    changed = [x for x in status if not x.startswith("!! ")]
    links = [e for e in git("ls-tree", "-r", "-z", "HEAD").stdout.split("\0") if e.startswith("160000 ")]
    missing = _missing(git)
    return [n for n, on in (
        (_unfetched(base, missing), missing),
        (f"{len(changed)} changed or untracked files of {base} are not in the agents' copy - commit them and start "
         f"again for the agents to see them", changed),
        (f"{len(ignored)} paths of {base} ignored by its .gitignore are not in the agents' copy "
         f"({', '.join(ignored[:8])}{', ...' if len(ignored) > 8 else ''}) - if the work needs any of them (data, "
         f"configuration), commit it or say where the agents get it", ignored),
        (f"{len(links)} submodules of {base} stand empty in the agents' copy: their files are not part of the commit",
         links),
        (f"{len(no_object)} files tracked by Git LFS have no object in {base} and stand as pointers in the agents' copy"
         f" - fetch them (`git lfs fetch`) and start again ({', '.join(no_object[:3])}"
         f"{', ...' if len(no_object) > 3 else ''})", no_object)) if on]


#: what a checkout regenerates by convention — caches, environments, build output, editors' state: not the work's inputs
_REGENERATED = {"__pycache__", ".venv", "venv", "env", "node_modules", "build", "dist", ".idea", ".vscode", ".tmp",
                ".DS_Store", ".tox", ".nox", ".eggs", "htmlcov", ".coverage"}


def _regenerated(path: str) -> bool:
    name = path.rstrip("/").rsplit("/", 1)[-1]
    return (name in _REGENERATED or name.endswith((".egg-info", ".pyc", ".pyo"))
            or name.startswith(".") and name.endswith("_cache"))


def _unfetched(base: Path, missing: list) -> str:
    return (f"{len(missing)} objects of the history of {base}'s HEAD are not in it (a partial clone), and the system "
            f"fetches nothing with your credentials, so HEAD cannot be imported - fetch them "
            f"(`git rev-list --objects --missing=print HEAD` lists them) and start again")


def committed(base: Path, rel: str) -> bytes | None:
    """One file as the import carries it: `rel` at the user's HEAD, read by their own git on the host — None where HEAD
    holds no such file. What a new root imports, never what a volume's earlier root left nor an uncommitted edit; and
    only of a top with a commit, as only one is imported (`carried_in`): git walks up from any other, and a home kept as
    a repository of its dotfiles gave the contract its committed token for a project's own file (critic, ran)."""
    if not is_top(base):
        return None
    got = _git(base)("cat-file", "blob", f"HEAD:{rel}", input=b"")
    return got.stdout if got.returncode == 0 else None


def carried_in(base: Path, project: str, d: Path) -> tuple:
    """(the commit, a tar under `d`, what of the user's it leaves out) of what the base imports (`execution._IMPORT`) — made on
    the host by the user's own git, reading their repository and nothing else: a bundle of HEAD and of the project's
    node branches left from before the base moved in, but `accepted`, with the LFS objects HEAD's pointers name that
    their store holds (`_lfs_of`). Left out, said (`left_out`). A base that is no repository's top with a commit is refused
    by the cause every session over it is (`no_places`): carried in as its live tree, its ignored files and `.env` went
    into the volume and the plan's reader carried them to the provider (critic, ran)."""
    out, git = d / "in.tar", _git(base)
    if not is_top(base):
        raise PlaceUnavailable(str(base), no_places(base) or f"{base} is not the top of a git repository with a commit")
    with tarfile.open(out, "w") as t:
        commit = git("rev-parse", "--verify", "HEAD^{commit}").stdout.strip()
        if missing := _missing(git):
            raise OSError(_unfetched(base, missing))
        (d / "branch").write_text(git("symbolic-ref", "-q", "--short", "HEAD").stdout.strip() or "main")
        if (got := git("bundle", "create", "-q", str(d / "bundle"), "HEAD", f"--exclude=gfso/{project}/accepted",
                       f"--exclude=gfso/{project}/accepted-*", f"--branches=gfso/{project}/*")).returncode:
            raise OSError(f"{base}: its HEAD could not be bundled ({got.stderr.strip()[-300:]})")
        for n in ("bundle", "branch"):
            t.add(d / n, arcname=n)
        for n in ("exclude", "attributes"):
            if (p := base / git("rev-parse", "--git-path", f"info/{n}").stdout.strip()).is_file():
                t.add(p, arcname=n)
        held, no_object = _lfs_of(base, git)
        for oid, f in held.items():
            t.add(f, arcname=f"lfs/{oid}")
    return commit, out, _left_out(base, git, no_object)


def fetched(base: Path, bundle: bytes, ref: str = "HEAD") -> str:
    """The objects of `bundle` taken into the user's repository at `base` by their own git — `fetch` of it alone, no
    ref written, no `FETCH_HEAD` —; git's words where it refused, else ''. Only a bundle: the bytes come out of a temp
    the base's sessions write, and handed anything else the host's git takes it for a repository it names and opens it,
    a network path too (critic over a99ea34). `ref`: the bundle's ref fetched."""
    if not bundle.startswith((b"# v2 git bundle\n", b"# v3 git bundle\n")):
        return "what came out is no git bundle"
    with tempfile.TemporaryDirectory(prefix="gfso-land-") as d:
        (f := Path(d) / "accepted.bundle").write_bytes(bundle)
        # …every object it carries checked as git takes it (`G.FSCK`): the user's git parses it on the host (critic over
        # the stream in use)
        got = G.run(base, *G.FSCK, "fetch", "-q", "--no-recurse-submodules", "--no-write-fetch-head", str(f), ref,
                    plain=True)
    return "" if got.returncode == 0 else (got.stderr or "").strip()[-300:] or f"git fetch exited {got.returncode}"


def stored(base: Path, want: dict, read) -> list[str]:
    """Each LFS object `want` names ({oid: (size, path)}) that the user's LFS store at `base` (`_lfs_store`) lacks, read
    (`read(oid, size)`: its bytes, verified, or None) and written there whole — by the system, as git-lfs lays it out:
    no git-lfs runs, nor any filter of the user's config. [The paths whose object could not be carried]."""
    store, lost = _lfs_store(base, _git(base)), []
    for oid, (size, path) in want.items():
        if (at := Path(lfs.path_in(str(store), oid))).is_file() and at.stat().st_size == size:
            continue
        if (data := read(oid, size)) is None or not lfs.is_object(data, oid, size):
            lost.append(path)
            continue
        write_atomic(at, data)
    return lost
