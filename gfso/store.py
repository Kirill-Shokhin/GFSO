"""The project's store: a delivery is the system's from DELIVER on, kept by its commit id whatever becomes of the place
it was made in, and read BY THAT ID by every reader of it — the judge, the issuer, a join, a landing, a rework.

A commit id names its content wherever its objects are, so where they are held is a question of the cache, and the
cache must outlive the place: the person removes or moves their directory, a node's place is cleared, a session
rewrites or prunes the base it works in, and a delivery read from there was a delivery lost. ONE STORE PER PROJECT,
never a copy per executor or per judge, a repository of the system's that no session mounts writable: in a container
the volume's `.gfso-store` beside the base — the base imported into it once, at the base's import —, on this host one
under the data home — the person's own repository is theirs to remove. Its first keep brings the history once, every
later one its new objects alone. The acts over it: `admit` a commit's objects, `keep` it by its id, read it back
(`held`: keep-if-absent from a place it was made in), `give` it into a place, `lay` it there as a ref.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Optional

from gfso.adapters import git as G, hostrepo as H, lfs
from gfso.adapters import worktrees as W
from gfso.adapters.execution import IMPORTED, STORE_DIR, ContainerExecution, LocalExecution, component
from gfso.adapters.snapshots import Source, Uncopied
from gfso.config import DEFAULT_PROJECT, data_dir
from gfso.core.types import PROJECT_ID, VOLUME, Signal

#: the ref a kept commit is named by in the store: set once, never moved — a second keep of one id is the first
KEEP = "refs/gfso/keep/"
#: what keys, in a project's settings, the record of a keep: {"place": where it was made, "in": "volume" for a place of
#: the project's volume, else this host's, "du_kib": what that place held on disk at the act} — the tree-bomb guard's
#: comparator once the place is gone
KEPT = "kept:"
#: how a keep's thread is named (`keep`)
KEEPING = "gfso-keep-"
#: where this host's stores stand under the data home
STORES = "stores"
IN_VOLUME = "volume"
#: how long one read or take of a delivery's history may run — the system's git bound over a large tree (`worktrees`)
TAKE_S = 600
#: what keys, in a project's settings, its repository — by its main worktree, which outlives every linked one
REPOSITORY = "repository"


class Absent(Uncopied):
    """No store holds the commit, and no place it was made in gives it whole: no copy of the delivery and no verdict on
    it — ⊥, the node's bound then its issuer's (re-ASSIGN or CANCEL, §12.5). Never a FAIL: a missing object is the
    system's loss, not the delivery's doing."""


def _where(engine, ex, make: bool = True) -> tuple:
    """(the project's store, the project's container execution — None for this host), made where it is not yet. In a
    container the volume's `STORE_DIR`, its git run in the project's own container (`ContainerExecution.session`): no
    session's container mounts it (`PlaceContainer._mounts`), so no executor deletes a keep or prunes what it names;
    the place brought up first — a chat delivers before any session ever started its container (live
    inchat-live-1113-200443). On this host one under the data home, named by the project's id: a project made again
    under a deleted one's name keeps none of its deliveries. `ex`: the project's execution, as its caller holds it.
    `make` False: nothing written nor started — (None, …) where it does not stand yet on this host, and always in a
    container, whose reading starts it."""
    if isinstance(ex, ContainerExecution):
        if not make:
            return None, ex
        ex.start()
        at, made = ex.own / STORE_DIR, lambda: ex.files.exists(str(ex.own / STORE_DIR / ".git" / "HEAD"))
    else:
        ex, pid = None, engine.graph.setting(PROJECT_ID)
        if not pid and not make:
            return None, None
        if not pid:
            engine.graph.store_setting(PROJECT_ID, pid := uuid.uuid4().hex)
        at = data_dir() / STORES / f"{component(engine.project_name or DEFAULT_PROJECT)}-{pid[:12]}"
        made = lambda: (at / ".git" / "HEAD").is_file()
        if not make:
            return (str(at), None) if made() else (None, None)
        at.parent.mkdir(parents=True, exist_ok=True)
    if not made():
        with W.one_at_a_time(at):         # …a keep and a judge both making it at once: one init, the other waits
            # …no auto gc: nothing a keep names may go
            if not made() and (W.git(at.parent, "init", "-q", str(at), execution=ex).returncode
                               or W.git(at, "config", "gc.auto", "0", execution=ex).returncode):
                raise OSError(f"the project's store {at} could not be made")
    return str(at), ex


def drop(project: str) -> list[str]:
    """This host's stores of a deleted project, gone — every one its name made (each project made under it had its
    own id); [those a process still holds]."""
    root, left = data_dir() / STORES, []
    mine = re.compile(rf"{re.escape(component(project or DEFAULT_PROJECT))}-[0-9a-f]{{12}}")
    for d in (root.iterdir() if root.is_dir() else ()):
        if mine.fullmatch(d.name):
            try:
                LocalExecution().remove_tree(str(d))
            except OSError:
                left.append(str(d))
    return left


def _whole(store: str, ex, commit: str) -> bool:
    """Does the store hold `commit` WHOLE — every object it reaches, down to what another keep holds (each was whole
    when kept)? A fetch that failed leaves the commit behind without its blobs (critic over e59b9d5, run)."""
    return (W.git(store, "cat-file", "-e", f"{commit}^{{commit}}", execution=ex).returncode == 0 and
            W.git(store, "rev-list", "--objects", "--missing=error", commit, "--not", f"--exclude={KEEP}{commit}",
                  "--all", execution=ex).returncode == 0)


class Unreadable(OSError):
    """The sender's cause, which the sender lifts (§12.16 (ii)): its commit is not readable whole in its own git — a
    shallow or partial clone, an object never fetched (`git fetch`, `git lfs fetch`)."""


def _tips(store: str, ex) -> list[str]:
    """What the store's refs name — every keep, the imported commit: what a commit's ancestry need not be read below."""
    return W.git(store, "for-each-ref", "--format=%(objectname)", execution=ex).stdout.split()


def admit(engine, ex, commit: str, src) -> Optional[str]:
    """THE ADMISSION TEST of a chat's DELIVER, READ ONLY OF THE SENDER'S GIT AND OF THE STORE: `commit` whole in the
    user's git at `src` on this host — every object it reaches, down to what the project's store holds already —,
    packed into a directory of the system's temp and HASHED AGAIN there (`index-pack --strict`, every id it names held
    by the pack), else `Unreadable`, the sender's to lift: an object missing (a shallow or partial clone) or not what
    its id names (a corrupted repository). The keep's own check came after DELIVER, and a sender's corruption became
    the system's stop, the sender never told (critic over 4ac5e3a). Works for any git holding the commit: a linked
    worktree, a plain clone, a `--shared` one. Nothing written in the store nor in the sender's git: a DELIVER the
    engine's own rules refuse after this has made no record, no object, no store. The verified pack, returned, is what
    the keep imports (`keep(pack=)`), its directory removed then or by `discard`; None where nothing is to bring. The
    store's tips go in on stdin, never as arguments: a command line is bounded (WinError 206 at ~1200 keeps, critic
    over 60d27c5)."""
    if why := shallow(src):
        raise Unreadable(why)
    store, ex = _where(engine, ex, make=False)
    tips = _tips(store, ex) if store else []
    git = lambda *a, rows=(): G.run(None, *a, timeout=TAKE_S, text=False, input="".join(f"{r}\n" for r in rows).encode())
    got = git("-C", str(src), "rev-list", "--objects", "--missing=error", "--ignore-missing", "--stdin",
              rows=[commit, *(f"^{t}" for t in tips)])
    if got.returncode:
        raise Unreadable(f"{commit[:12]} is not readable whole in {src} (a shallow or partial clone, an object never "
                         f"fetched): {_err(got)} — fetch what it lacks (`git fetch --unshallow`, `git lfs fetch`)")
    if not (ids := {ln.split(b" ", 1)[0].decode() for ln in got.stdout.splitlines() if ln.strip()}):
        return None
    broken = lambda why: Unreadable(f"{commit[:12]} is not what its history names in {src}: {why} — repair the "
                                    f"repository (`git fsck --full` names what is broken; fetch it again from a good "
                                    f"copy)")
    held = git("-C", str(src), "rev-list", "--no-walk", "--ignore-missing", "--stdin", rows=tips).stdout.decode().split()
    read = lambda *a: git("-C", str(src), "rev-parse", *a).stdout.decode().strip()
    host = LocalExecution()               # …the sender's git is on this host: the pack verified in its temp
    at = Path(host.files.mkdtemp("gfso-admit-", host.temp_root()))
    try:
        if git("init", "-q", "--bare", f"--object-format={read('--show-object-format') or 'sha1'}", str(at)).returncode:
            raise OSError(f"no repository could be made in {at} to verify {commit[:12]} in")
        # …the sender's objects read through, never written: what the pack leaves out (the store's tips) links to them
        host.files.write_bytes(str(at / "objects" / "info" / "alternates"),
                               f"{read('--path-format=absolute', '--git-path', 'objects')}\n".encode())
        if (sent := git("-C", str(src), "pack-objects", "--revs", "-q", str(at / "sent"),
                        rows=[commit, *(f"^{h}" for h in held)])).returncode:
            raise broken(_err(sent))
        pack, idx = at / f"sent-{sent.stdout.decode().strip()}.pack", at / "objects" / "pack" / "verified.idx"
        if (v := git("-C", str(at), "index-pack", "--strict", "-o", str(idx), str(pack))).returncode:
            raise broken(_err(v))
        shown = G.run(at, "show-index", timeout=TAKE_S, text=False, input=host.files.read_bytes(str(idx)))
        if lost := ids - {ln.split()[1] for ln in shown.stdout.decode().splitlines() if ln.strip()}:
            raise broken(f"its object {min(lost)} does not hold what its id names")
        return str(pack)
    except BaseException:
        discard(str(at / "sent.pack"))
        raise


def shallow(src) -> Optional[str]:
    """Why the git at `src` delivers nothing — a shallow clone: the store keeps a delivery with its history, which
    joins and landing read, and its boundary failed `index-pack --strict` as a corruption, the sender told to repair a
    whole repository (critic over ac9dcaa) —, or None. Its root is the boundary, so it shares no history either."""
    got = G.run(src, "rev-parse", "--is-shallow-repository", timeout=TAKE_S, text=False)
    if got.stdout.decode().strip() != "true":
        return None
    return (f"{src} is a shallow clone, and the project keeps a delivery with its history: fetch it whole "
            f"(`git fetch --unshallow`)")


def discard(pack: Optional[str]) -> None:
    """The directory an admission verified `pack` in (`admit`), gone — kept from, or its DELIVER not accepted."""
    if pack:
        LocalExecution().remove_tree(str(Path(pack).parent))


def _err(r) -> str:
    return (r.stderr or b"").decode(errors="replace").strip()[-300:]


#: git's own "$1" flags after it, the commit "$2", the file "$3" listing what the store holds — the commit packed but
#: those of them the source holds, run where the source's git runs (bash); its objects only, no ref, no hook nor config
#: of the source's beyond its own repository, nothing of the list on a command line
_PACK = r'''set -o pipefail; k=$1; shift; f=(); while [ "$k" -gt 0 ]; do f+=("$1"); shift; k=$((k-1)); done; c=$1 t=$2
{ printf '%s\n' "$c"; git "${f[@]}" rev-list --no-walk --ignore-missing --stdin < "$t" | sed 's/^/^/'; } |
  git "${f[@]}" pack-objects --revs --thin --stdout -q'''


def _take(engine, ex, commit: str, src, at, pack: Optional[str] = None) -> None:
    """THE SYSTEM'S ACT after admission: `commit` whole in the project's store — streamed from the git at `src` where
    the store lacks it (`at`: the execution whose git reads `src`, this host's where None), with its ancestry back to
    what the store holds, EVERY OBJECT HASHED AGAIN as the store takes it in (`index-pack --strict`). One pipe between
    the two gits (`ExecutionPort.pipe`): nothing of it held by the server, no bound but the store's disk; what the store
    holds laid in the source's temp as a file, the system's write. `pack`: the one its admission verified (`admit`),
    imported first, the source read only where it does not make the commit whole. `OSError` where it could not be
    taken — the keep's failure, retried by the next reader (`held`), never a sender's refusal."""
    store, ex = _where(engine, ex)
    into = ex if ex is not None else LocalExecution()
    if pack and not _whole(store, ex, commit):
        with W.one_at_a_time(store):
            host = LocalExecution()
            host.pipe([host.shell() or "bash", "-c", 'cat "$1"', "sh", Path(pack).as_posix()], cwd=str(Path(pack).parent), into=into,
                      into_cwd=store, into_args=G.argv("index-pack", "--stdin", "--fix-thin", "--strict"),
                      timeout=TAKE_S, into_env=G.env())
    if _whole(store, ex, commit):
        return
    with W.one_at_a_time(store):
        rc, err, r = _stream(at if at is not None else LocalExecution(), src, commit, into, store, _tips(store, ex))
        if rc or r.returncode or not _whole(store, ex, commit):
            raise OSError(f"{commit[:12]} could not be taken from {src} into the project's store: "
                          f"{(err or r.stderr or r.stdout or 'not whole there').strip()[-300:]}")


def _stream(here, src, commit: str, into, dst, tips: list[str]):
    """`commit` and its ancestry down to `tips` streamed from the git at `src` (read where `here` runs) into the one at
    `dst` (where `into` runs), EVERY OBJECT HASHED AGAIN as `dst` takes it in (`index-pack --strict`): one pipe between
    the two gits, no upload-pack — no config of a remote side to carry (a fetch by id from the store was refused `not
    our ref` in a validator's round while the store advertised the commit, 2026-11-24) — and the list of `tips` laid in
    the source's temp as a file, the system's write. (rc, err, result) of the pipe."""
    src_ex = here.session(str(src))
    listed = Path(here.temp_of(str(src))) / f"gfso-held-{uuid.uuid4().hex}"
    with here.system_writes(str(listed.parent)):
        try:
            here.files.write_bytes(str(listed), "".join(f"{t}\n" for t in tips).encode())
            return src_ex.pipe(
                [src_ex.shell() or "bash", "-c", _PACK, "sh", str(len(G.APART)), *G.APART, commit, str(listed)],
                cwd=str(src), into=into,
                into_cwd=str(dst), into_args=G.argv("index-pack", "--stdin", "--fix-thin", "--strict"),
                timeout=TAKE_S, env=G.env(), into_env=G.env())
        finally:
            here.files.remove_matching(str(listed.parent), [listed.name])


def keep(engine, ex, commit: str, src, place, at=None, first=lambda: None, pack: Optional[str] = None
         ) -> threading.Thread:
    """THE KEEP of an admitted delivery, in the background — DELIVER waits on nothing of the system's: the thread
    that keeps it (`_keep`, from `pack`, its admission's verified pack, where one is), after `first`, the caller's own
    write of the act. A failure is said on the feed, never the delivery's undoing: its first reader keeps what is
    absent while the place still holds it (`held`)."""
    def _run():
        try:
            first()
            try:
                _keep(engine, ex, commit, src, place, at, pack)
            except (OSError, subprocess.TimeoutExpired) as e:
                engine.emit_info("delivery", f"{commit[:12]} is not kept in the project's store: {e}")
        finally:
            discard(pack)
    t = threading.Thread(target=_run, daemon=True, name=f"{KEEPING}{commit[:12]}")
    t.start()
    return t


def _keep(engine, ex, commit: str, src, place, at, pack: Optional[str] = None) -> None:
    """`commit` whole in the store (`_take` from `src`: done already, or done now), named `KEEP<commit>` — a name set
    once and never moved, no gc taking it while the project lives —, the LFS objects its tree's pointers name beside
    it, and what `place` held on disk at the act, read where `at` runs (`KEPT`): the measure a judge's checkout is held
    to once the place is gone."""
    _take(engine, ex, commit, src, at, pack)
    store, ex = _where(engine, ex)
    with W.one_at_a_time(store):
        if W.git(store, "rev-parse", "--verify", "-q", f"{KEEP}{commit}", execution=ex).returncode and (
                got := W.git(store, "update-ref", f"{KEEP}{commit}", commit, "", execution=ex)).returncode:
            raise OSError(f"its ref could not be set: {got.stderr.strip()[-300:]}")
    lost = _keep_lfs(engine, store, ex, commit, src, at) if src is not None else []   # …whole already, read from nowhere
    if engine.graph.setting(KEPT + commit) is not None:
        return
    held = W.du_kib((at if at is not None else LocalExecution()).session(str(place)), place)
    with W.one_at_a_time(store):          # …the first record stands: two keeps of one id measured side by side
        if engine.graph.setting(KEPT + commit) is None:
            engine.graph.store_setting(KEPT + commit, json.dumps(
                {"place": str(place), **({"in": IN_VOLUME} if isinstance(at, ContainerExecution) else {}), "du_kib": held,
                 **({"lfs_not_kept": lost} if lost else {})}))


def _keep_lfs(engine, store: str, ex, commit: str, src, at) -> list[str]:
    """The LFS objects `commit`'s pointers name, from the store `src` reads into the project's, each only where it is
    its pointer's object; [what was not kept]. A place of the system's by its own execution (`W.carry_lfs`); a chat's git
    on this host read here (`hostrepo.lfs_held`), an object past what one write carries (`W.BUNDLE_CAP`) not kept. Into the
    store, the system's own write: no node's growth against its disk bound (critic over 60d27c5)."""
    keeper = ex if ex is not None else LocalExecution()
    with keeper.system_writes(store):
        if at is not None:
            want = W.pointed(src, [commit], at)
            return W.carry_lfs(W.base_of(str(src)) or str(src), src, store, want, at) if want else []
        held, lost = H.lfs_held(Path(src), commit)
        into = str(Path(store) / ".git" / "lfs" / "objects")
        for oid, f in held.items():
            if keeper.files.exists(to := lfs.path_in(into, oid)):
                continue
            size = os.path.getsize(f)
            if size > W.BUNDLE_CAP or not lfs.is_object(data := Path(f).read_bytes(), oid, size):
                lost.append(oid)
                continue
            keeper.files.write_bytes(to, data)
        return lost


def via(execution):
    """The execution whose git reads a place of the project's — a container's, None for this host's."""
    return execution if isinstance(execution, ContainerExecution) else None


def _candidates(engine, commit: str, ex) -> list[tuple]:
    """[(place, execution reading it)] a commit may still be read from, the record's first: where its keep recorded it
    made, the repository its DELIVER logged, and the project's own — its volume's base, where a place of the
    system's carried it (`W.commit_all`), or the repository it recorded on this host."""
    rec = json.loads(engine.graph.setting(KEPT + commit) or "{}")
    out = [(rec["place"], ex if rec.get("in") == IN_VOLUME else None)] if rec.get("place") else []
    out += [(e.repository, None) for e in engine.audit_log() if e.commit == commit and e.repository]
    if ex is not None:
        out.append((str(ex.base), ex))
    elif repo := engine.graph.setting(REPOSITORY):
        out.append((repo, None))
    return list(dict.fromkeys((p, x) for p, x in out if p))


def held(engine, ex, commit: str, *places: tuple) -> Source:
    """THE ONE READ OF A DELIVERY BY ITS ID, every reader's: kept if absent — from `places` [(place, execution reading
    it)] the caller knows, else from where the record says it was made (`_candidates`) — then read from the store with
    the comparators its keep recorded. `Absent` where no store holds it and no place gives it whole: no copy, no
    verdict (⊥), never a FAIL of the delivery."""
    store, ex = _where(engine, ex)
    if not (_whole(store, ex, commit) and engine.graph.setting(KEPT + commit) is not None):
        why = []
        for src, at in dict.fromkeys([*places, *_candidates(engine, commit, ex)]):
            try:
                _keep(engine, ex, commit, src, src, at)
                break
            except (OSError, subprocess.TimeoutExpired) as e:
                why.append(str(e))
        else:
            if not _whole(store, ex, commit):
                raise Absent(f"the delivery {commit[:12]} is in no store and no place gives it whole"
                             + (f" ({'; '.join(why)[-600:]})" if why else ""))
    rec = json.loads(engine.graph.setting(KEPT + commit) or "{}")
    return Source(store, rec.get("du_kib"), tuple(_links(engine, store, ex, commit, rec)),
                  *_credit(engine, store, ex, rec))


def imported(engine) -> Optional[str]:
    """The commit the project's volume base was imported from — None where it has none, or no git."""
    got = json.loads(engine.graph.setting(VOLUME + IMPORTED) or "{}").get("commit")
    return got if got and got != "tree" else None


def roots(engine, ex) -> set:
    """The root commits of what the project's store keeps on this host — what a delivery of the project shares (the
    imported history, earlier deliveries); empty where it keeps nothing here, or stands in a volume (read there)."""
    store, ex = _where(engine, ex, make=False)
    if not store or ex is not None:
        return set()
    tips = _tips(store, None)
    return set(G.run(store, "rev-list", "--max-parents=0", "--stdin", timeout=TAKE_S, text=False,
                     input="".join(f"{t}\n" for t in tips).encode()).stdout.decode().split()) if tips else set()


def _links(engine, store: str, ex, commit: str, rec: dict) -> list[str]:
    """The gitlinks a delivery's tree may record: in a volume those of the imported commit — empty in every copy
    alike, they carry nothing of a node's —; on this host those of the base's HEAD for a node's place, and for a chat
    the submodules its delivered commit declares in its own `.gitmodules`."""
    if ex is not None:
        return W.links_of(store, first, ex) if (first := imported(engine)) else []
    try:
        return W.links_of(root, "HEAD", None) if (root := W.base_of(rec.get("place"))) else W.declared_links(store, commit)
    except OSError:                       # …the base gone with the place: no gitlink of it allowed
        return []


def _credit(engine, store: str, ex, rec: dict) -> tuple:
    """(the imported commit credited against a delivery's tree bomb — (where git runs, repository, revision) or None
    —, the base whose LFS store backs the store's): in a volume the imported commit in the store and the volume's base;
    on this host the base's HEAD for a node's place."""
    if ex is not None:
        return ((ex, store, first) if (first := imported(engine)) else None), str(ex.base)
    if root := W.base_of(rec.get("place")):
        return (LocalExecution(), root, "HEAD"), root
    return None, store


def give(engine, ex, commit: str, place, at=None) -> None:
    """`commit`, read by its id (`held`), whole in the git at `place` — objects only, no ref, no checkout: a join, a
    landing, a place made again read it there. `ex`: the project's execution, where its store is; `at`: the one
    `place`'s git runs in — a place of the system's read where it runs, never by this host's git; None for a person's
    repository on this host. Within a container carried by the one path between two repositories (`W.carry`), out of
    one onto this host by a bundle of the store's (`W.to_host`); on this host fetched by `place`'s git from the store, a
    repository of the system's alone, under no hook. `OSError` where it could not be given; `Absent` where no store
    holds it."""
    if W.git(place, "rev-list", "--objects", "--missing=error", "-1", commit, execution=at).returncode == 0:
        return
    store = held(engine, ex, commit).repo
    if isinstance(ex, ContainerExecution):
        if at is not None:
            W.carry(str(ex.base), store, place, commit, ex)
        elif why := W.to_host(store, KEEP + commit, place, ex):
            raise OSError(f"{place} could not take {commit[:12]} from the project's store: {why}")
        return
    rc, err, r = _stream(LocalExecution(), store, commit, at if at is not None else LocalExecution(), place,
                         W.git(place, "for-each-ref", "--format=%(objectname)", execution=at).stdout.split())
    if rc or r.returncode or W.git(place, "rev-list", "--objects", "--missing=error", "-1", commit,
                                   execution=at).returncode:
        raise OSError(f"{place} could not take {commit[:12]} from the project's store: "
                      f"{(err or r.stderr or r.stdout or 'not whole there').strip()[-300:]}")


def lay(engine, ex, commit: str, place, ref: str, at=None) -> None:
    """`commit` put into the git at `place` as `ref` (`give`, then the ref set) — never a checkout, and never a branch
    a worktree there has checked out: moved under a live tree, its next commit undoes what was laid. `OSError` where it
    could not be laid."""
    if W.checked_out(place, ref, execution=at):
        raise OSError(f"`{ref}` is checked out at {place}: nothing is laid under a live tree")
    give(engine, ex, commit, place, at)
    if (got := W.git(place, "update-ref", ref, commit, execution=at)).returncode:
        raise OSError(f"{place} could not name {commit[:12]} `{ref}`: {got.stderr.strip()[-300:]}")


def migrate(engine, ex, repository: Optional[str], unjudged: tuple = ()) -> dict:
    """THE ONE-TIME MOVE of a project made before its store: every commit its log names that is still readable —
    in the repository its DELIVER logged, or the project's own (a volume's base, the repository it recorded: where the
    ref the system once kept a chat's delivery by, `refs/gfso/<p>/delivered/*`, holds it) — kept by its id; the
    volume's imported commit with them, which its guards credit. {"kept": [ids], "lost": [(node, id, why)], "no_commit":
    [(node, state)], "repository": the project's or None}: the deliveries recorded with no commit, which no copy is
    made of — one VALIDATING goes ⊥ to its bound and its issuer, and is delivered again (no verdict without contact) —,
    and a project whose record names no repository at all, said so by name, never silently "no tree"; `unjudged`, the
    roles whose directory no delivery is judged in (`workspaces.unjudged`: no git, or an executor below a work tree's
    top), named under "no_repository" with the lift — the system makes no repository of the person's directory. Run
    once per project, by hand; never at import of a database."""
    out, at = {"kept": [], "lost": [], "no_commit": [], "repository": repository,
               "no_repository": list(unjudged)}, via(ex)
    if at is not None and (first := imported(engine)):
        try:
            _keep(engine, ex, first, str(at.base), str(at.base), at)
            out["kept"].append(first)
        except (OSError, subprocess.TimeoutExpired) as e:
            out["lost"].append(("(the imported base)", first, str(e)))
    for e in engine.audit_log():
        if e.signal != Signal.DELIVER or e.rejected:
            continue
        if not e.commit:
            t = engine.graph.get_task(e.task_id)
            out["no_commit"].append((str(e.task_id), t.state.name if t is not None else "?"))
            continue
        if e.commit in out["kept"]:
            continue
        try:
            held(engine, ex, e.commit)
            out["kept"].append(e.commit)
        except Absent as why:
            out["lost"].append((str(e.task_id), e.commit, str(why)))
    return out
