"""Where a path is, as a question that can be answered without waiting on a file server.

One owner for four things the rest of the product kept re-deciding: whether a path is cheap to ask
the filesystem about, what its normal form is as text, what it is once the disk has been consulted,
and whether two spellings name one place. They live here rather than beside the roster because they
are about PATHS, and because the roster is not their only caller - the validation door asks the same
question of the same workdir, and a rule kept in two places moves in one of them.
"""
from __future__ import annotations

import ctypes
import logging
import os
from pathlib import Path

log = logging.getLogger("gfso.places")


def as_path_text(p) -> str:
    """A path argument as text, whatever shape it arrived in.

    `str()` on a `Path` gives the path; on any other `os.PathLike` it gives the object's repr, which
    would be classified and normalized as if it were a filename. One function so that the two places
    that read a path argument cannot disagree about what a path argument is."""
    if p is None:
        return ""
    return os.fspath(p) if hasattr(p, "__fspath__") else str(p)


def _drive_is_local(letter: str) -> bool:
    """Is `X:` a local drive? Answered from the machine's own mapping table (`GetDriveTypeW`), so no
    packet leaves the box; an unreadable answer counts as local, since a guess is not a reason to
    stall the graph."""
    if os.name != "nt":
        return True
    try:
        return ctypes.windll.kernel32.GetDriveTypeW(letter + chr(92)) != 4     # 4 = DRIVE_REMOTE
    except (AttributeError, OSError, ValueError) as ex:
        # NARROW, so the early return above is a real branch and not decoration: with a bare
        # `except Exception` the off-Windows case fell through here anyway (`ctypes.windll` raises
        # AttributeError), and removing the early return changed nothing - an unfalsifiable line.
        log.debug(f"drive type of {letter} unknown ({ex}) - treated as local")
        return True


def cheap_to_ask(p) -> bool:
    """Can this path be asked about without blocking the caller?

    A UNC path to a host that does not answer costs SEVEN TO TWENTY-ONE SECONDS in `is_dir()` on
    this platform - measured, after an earlier probe of mine said 0.000 s because the shell it was
    written through had eaten one of the two leading backslashes and it timed an ordinary relative
    path. The cost matters because the liveness check runs on a worker thread that holds one of the
    dispatcher's concurrency slots, once per pass, and the refusal path would resolve the same path
    a second time.

    So a network path is not asked. What is given up is a check, not a guarantee: the spawn behaves
    exactly as it did before this guard existed, and a share that is genuinely gone still fails
    where it always failed - in the transport. What is bought is that a slow file server cannot
    stall the graph, and cannot have a momentary outage read as "this role has nowhere to work".

    THE NAMED LIMIT: this reads the DRIVE. A directory junction, a symlink or a volume mount sits
    BELOW the drive letter, so a local-looking path can still lead onto a share and `resolve()` will
    walk it - `abspath` does not. `mklink /J` refuses a UNC target outright, so the reachable form
    is a directory symlink (admin or Developer Mode) or a DFS/volume mount; the cost there is a
    stall, not a wrong verdict, and no cheaper question exists that would see it.

    NETWORK, NOT "STARTS WITH TWO SLASHES". Classifying by that prefix alone was wrong in BOTH
    directions, measured. The extended-length and device forms are LOCAL and answer in 0.0 ms, and
    excluding them turned the whole guard off for them - the defect this exists to close, reachable
    free of charge through a prefix; of the extended forms only the UNC one is remote (7.3 s). In
    the other direction, the common way a share is used carries no prefix at all: a MAPPED DRIVE
    LETTER goes through the same redirector for the same seconds, and the local mapping table says
    so without a packet leaving the machine.
    """
    p = as_path_text(p)
    if not p:
        return True
    bs = chr(92)
    # THE LOCATION, NOT THE SPELLING. Read off the path as typed, this classified `work` and
    # `\work` as local without asking anything — and both resolve against the process's CURRENT
    # drive, so on a server whose cwd is a mapped share they carry the full stall through a
    # spelling with no prefix to test. `abspath` costs no filesystem call and turns every shape
    # into one that names its own drive.
    drive = os.path.splitdrive(os.path.abspath(p))[0].replace("/", bs).lower()
    if drive.startswith(bs * 2):
        if drive.startswith(bs * 2 + "?" + bs) or drive.startswith(bs * 2 + "." + bs):
            inner = drive[4:]                           # `c:` · `unc\srv\sh` · `z:` · `pipe`
            if inner == "unc" or inner.startswith("unc" + bs):
                return False                            # the one remote extended form
            if len(inner) >= 2 and inner[1] == ":":
                return _drive_is_local(inner[:2])       # a drive letter behind the prefix
            return True                                 # a device, or extended-length local
        if drive == bs * 2:
            return True                                 # two separators alone name no host
        return False                                    # a plain UNC share
    if len(drive) >= 2 and drive[1] == ":":
        return _drive_is_local(drive[:2])
    return True


def text_place(p) -> str:
    """One directory path, normalized as far as TEXT goes - case, separators, `..`, a trailing
    separator, and the process cwd for a relative one. No filesystem call, so it is free to run over
    a whole roster; what it cannot see is 8.3 short names, junctions and `subst` drives, which is
    exactly the residue `same_place` spends a `resolve()` on."""
    return os.path.normcase(os.path.abspath(os.path.normpath(as_path_text(p))))


def disk_place(p):
    """The same normal form as `text_place`, but with the filesystem consulted - or `None` when it
    cannot be. This is the half that sees through 8.3 short names, junctions and `subst` drives, and
    the half that costs something, so it is named separately: a caller comparing ONE path against
    many (the judge tie-break) derives its own side once instead of per candidate."""
    if not p or not cheap_to_ask(p):
        return None                    # see `cheap_to_ask`: a network path answers by text alone
    try:
        return text_place(Path(p).resolve())
    except (OSError, ValueError):
        return None            # a path the OS will not resolve has already given its text answer


def same_place(a, b) -> bool:
    """Do these two path strings name the same directory - as PATHS, not as text.

    Registration stores a workdir resolved (`AgentRegistry.register`), while callers hand back the
    spelling they typed: `C:/x/y` against its backslash form is one place written two ways, and a raw
    `!=` reads it as two. That comparison is what `unregister(workdir=...)` and the validator-to-
    executor workspace match are made of, so the register/unregister pair silently stopped closing
    and a hand-written roster entry stopped matching a registered one.

    TEXT FIRST, DISK ONLY IF THAT FAILS. Case, separators, `..` and trailing separators are settled
    without asking the filesystem; only when the two still differ is `resolve()` spent, which is what
    sees through 8.3 short names, junctions and `subst` drives. The order is not a micro-optimization:
    this runs once per candidate judge inside `validator_for`, which runs on every dispatch pass and
    on every `list_agents`, and resolving unconditionally cost 12.9 ms per call against a roster of
    25 (measured) where the text answer costs 0.05 ms.

    THE NAMED LIMIT: two spellings of a directory that no longer EXISTS can only be compared as text.
    A path registered under its 8.3 short name and unregistered after its directory was removed
    therefore reads as a different place - no answer better than that one is available without a
    disk to ask, and the alternative (calling two spellings the same on a hunch) loses roles that
    are still in use.
    """
    # NO PLACE IS NOT A PLACE. An empty side normalizes to the process cwd - and the server normally
    # stands in the project, so `same_place(None, <the executor's workdir>)` came out TRUE and a
    # judge with no workdir at all joined the set of judges standing in the work, to be picked off it
    # alphabetically. The question "one place written two ways" is undefined for "no place", and the
    # honest answer is no.
    if not a or not b:
        return False

    if text_place(a) == text_place(b):
        return True
    ra, rb = disk_place(a), disk_place(b)
    return ra is not None and ra == rb
