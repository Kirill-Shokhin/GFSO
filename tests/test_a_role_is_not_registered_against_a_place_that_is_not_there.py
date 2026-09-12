"""A role whose `workdir` names nothing must not reach the roster.

The registry already refused an EMPTY workdir, and read any non-empty string as an answer. So a
path that names no directory registered cleanly and failed later, twice over: the executor is
spawned with `cwd=` it and dies in the transport, the validator opens an empty tree and FAILs
correct work over every criterion. The case that actually happened is a POSIX-form path on Windows
— `/c/Users/…` resolves against the current DRIVE ROOT, so the roster pointed at `C:\\c\\Users\\…`
while looking correct, and the work that ran there landed outside the project.

The positive controls matter as much: a real directory still registers, and the kinds that need no
workdir are untouched.
"""
import ctypes
import json
import os
import subprocess
from pathlib import Path

import pytest

import gfso.places as P
from gfso import tools as T
from gfso import tools_llm as TL
from gfso.delegate import AgentRegistry, _resolution_note, missing_workdir
from gfso.places import cheap_to_ask, same_place, text_place
from tests.support import make_engine

BS = chr(92)


@pytest.fixture()
def roster(tmp_path):
    return AgentRegistry(str(tmp_path / "roster.json"))


def test_a_workdir_that_names_nothing_is_refused(roster, tmp_path):
    missing = str(tmp_path / "not-created")
    with pytest.raises(ValueError) as ex:
        roster.register("exec-1", "llm-executor", workdir=missing)
    assert "not an existing directory" in str(ex.value)
    assert missing in str(ex.value)


def test_the_refused_role_is_not_on_the_roster(roster, tmp_path):
    with pytest.raises(ValueError):
        roster.register("exec-1", "llm-executor", workdir=str(tmp_path / "not-created"))
    assert roster.get("exec-1") is None


def test_a_posix_form_path_on_windows_is_refused_and_its_resolution_named(roster):
    """`/c/Users/…` is the spelling that looks right and points somewhere else."""
    posix = "/c/Users/nobody/Work/GFSO"
    with pytest.raises(ValueError) as ex:
        roster.register("exec-1", "llm-executor", workdir=posix)
    assert "not an existing directory" in str(ex.value)
    if os.name == "nt":
        # The message must show WHERE it actually points, since that is what the caller cannot see.
        assert "resolves to" in str(ex.value)


def test_a_file_is_not_a_working_directory(roster, tmp_path):
    f = tmp_path / "solution.py"
    f.write_text("# not a directory\n", encoding="utf-8")
    with pytest.raises(ValueError) as ex:
        roster.register("val-1", "llm-validator", workdir=str(f))
    assert "not an existing directory" in str(ex.value)


def test_a_real_directory_still_registers(roster, tmp_path):
    out = roster.register("exec-1", "llm-executor", workdir=str(tmp_path))
    assert out["registered"] == "exec-1"
    assert roster.get("exec-1")["workdir"] == str(tmp_path)


def test_a_kind_that_needs_no_workdir_is_untouched(roster):
    out = roster.register("someone", "external")
    assert out["registered"] == "someone"
    assert roster.get("someone")["workdir"] is None


def test_the_empty_workdir_refusal_still_speaks_its_own_reason(roster):
    """The new guard must not swallow the older one: no workdir at all is a different sentence."""
    with pytest.raises(ValueError) as ex:
        roster.register("exec-1", "llm-executor")
    assert "needs `workdir`" in str(ex.value)


def test_an_oracle_map_checker_with_a_bad_workdir_is_still_refused(roster, tmp_path):
    """A kind that does not REQUIRE a workdir must still not be registered against a fake one."""
    omap = tmp_path / "map.json"
    omap.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError) as ex:
        roster.register("chk", "unittest-checker", oracle_map=str(omap),
                        workdir=str(tmp_path / "gone"))
    assert "not an existing directory" in str(ex.value)


def test_the_resolution_clause_names_the_place_and_not_the_spelling(roster):
    """The clause exists for the path that points somewhere else — and only for it.

    Compared as raw strings, `C:/my/project` "differs from" its backslash form, so the note fired on
    the ordinary forward-slash spelling every agent types: noise on the paths that point exactly
    where they look, inside the sentence written for the ones that do not.
    """
    with pytest.raises(ValueError) as plain:
        roster.register("exec-1", "llm-executor", workdir="C:/my/project"
                        if os.name == "nt" else "/my/project")
    assert "resolves to" not in str(plain.value)


def test_the_named_resolution_is_the_one_that_actually_happens(roster):
    """Asserting only that the words appear would pass on a WRONG resolution."""
    posix = "/c/Users/nobody/Work/GFSO"
    with pytest.raises(ValueError) as ex:
        roster.register("exec-1", "llm-executor", workdir=posix)
    if os.name == "nt":
        assert f"(it resolves to {Path(posix).resolve()})" in str(ex.value)
        # …and WHERE it points is the whole finding: the leading `/c` became a directory named `c`
        # under the current DRIVE ROOT, not the C: drive.
        parts = Path(posix).resolve().parts
        assert parts[1:3] == ("c", "Users"), parts


def test_a_path_that_cannot_be_resolved_still_gets_the_crafted_refusal(roster):
    """`stat` rejects an embedded NUL that `is_dir()` swallows; an unguarded resolve replaced the
    refusal with a stat error, which is a worse answer than the clause it was computing."""
    with pytest.raises(ValueError) as ex:
        roster.register("exec-1", "llm-executor", workdir="C:" + os.sep + "a" + chr(0) + "b")
    assert "not an existing directory" in str(ex.value)


def test_the_refusal_is_ascii_so_a_cp1251_console_can_print_it(roster, tmp_path):
    """This sentence is raised and printed by doors that reach a Windows console."""
    with pytest.raises(ValueError) as ex:
        roster.register("exec-1", "llm-executor", workdir=str(tmp_path / "gone"))
    str(ex.value).encode("cp1251")   # raises UnicodeEncodeError if a dash or ellipsis crept in


def test_a_relative_workdir_is_stored_absolute(roster, tmp_path, monkeypatch):
    """Validated against the server's cwd, then resolved against the spawn's — the same ambiguity
    the guard exists to end, one step further along. What was checked is what is written down."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "work").mkdir()
    roster.register("exec-1", "llm-executor", workdir="work")
    stored = roster.get("exec-1")["workdir"]
    assert Path(stored).is_absolute()
    assert Path(stored) == (tmp_path / "work").resolve()


# ---------------------------------------------------------------------------------------------
# What storing the workdir RESOLVED costs elsewhere. Registration and unregistration were a pair
# matched on the same string; moving one half broke the conditional removal for the ordinary
# forward-slash spelling — and that call is a run's budget-stop, whose silent failure is on record
# as "a run that ended at its ceiling was still executing minutes later".
# ---------------------------------------------------------------------------------------------

def test_unregister_closes_on_the_spelling_that_was_registered(roster, tmp_path):
    place = tmp_path / "work"
    place.mkdir()
    roster.register("exec-1", "llm-executor", workdir=str(place))
    assert roster.unregister("exec-1", workdir=str(place))["unregistered"] == "exec-1"


def test_unregister_closes_on_the_other_spelling_of_the_same_place(roster, tmp_path):
    """`C:/x/y` and its backslash form are one directory written two ways.

    ASYMMETRIC on purpose: registered one way, withdrawn the other. Passing the SAME spelling to
    both calls cannot fail for the reason this test names — it would discriminate only because
    registration stores an absolute path — and a test that cannot fail for its own reason is the
    thing this file exists to avoid.
    """
    place = tmp_path / "work"
    place.mkdir()
    roster.register("exec-1", "llm-executor", workdir=str(place))                    # backslashes
    assert roster.unregister("exec-1",
                             workdir=str(place).replace(os.sep, "/"))["unregistered"] == "exec-1"
    assert roster.get("exec-1") is None


def test_unregister_closes_on_the_backslash_form_of_a_place_registered_with_slashes(roster,
                                                                                    tmp_path):
    """…and the other way round, so neither direction rests on the store step alone."""
    place = tmp_path / "work"
    place.mkdir()
    roster.register("exec-1", "llm-executor", workdir=str(place).replace(os.sep, "/"))
    assert roster.unregister("exec-1", workdir=str(place))["unregistered"] == "exec-1"


def test_unregister_still_refuses_a_genuinely_different_place(roster, tmp_path):
    """Positive control: the conditional removal exists to protect a SHARED roster."""
    mine, theirs = tmp_path / "mine", tmp_path / "theirs"
    mine.mkdir()
    theirs.mkdir()
    roster.register("exec-1", "llm-executor", workdir=str(mine))
    assert roster.unregister("exec-1", workdir=str(theirs))["unregistered"] is None
    assert roster.get("exec-1") is not None


def test_a_hand_written_entry_still_matches_a_registered_one(roster, tmp_path):
    """The roster is hand-editable by design, so one side resolved and the other as typed is a
    live shape — and the workspace match is the rule whose failure is recorded as a false FAIL
    over seventeen criteria."""
    place = tmp_path / "work"
    place.mkdir()
    roster.register("exec-1", "llm-executor", workdir=str(place))
    raw = json.loads(Path(roster._path).read_text(encoding="utf-8"))
    raw["hand-val"] = {"kind": "llm-validator", "workdir": str(place).replace(os.sep, "/")}
    Path(roster._path).write_text(json.dumps(raw), encoding="utf-8")

    fresh = AgentRegistry(str(roster._path))
    assert fresh.validator_for("exec-1") == "hand-val"


def test_no_place_is_not_the_same_place_as_some_place(roster, tmp_path, monkeypatch):
    """An empty side normalizes to the process CWD, and the server normally stands in the project.

    So `same_place(None, <the executor's workdir>)` came out true, and a judge registered with no
    workdir at all joined the set of judges standing in the work — to be picked off it
    alphabetically. That is the rule whose failure is on record as a false FAIL over seventeen
    criteria, reintroduced by an alias.
    """
    monkeypatch.chdir(tmp_path)
    assert not same_place(None, str(tmp_path))
    assert not same_place("", str(tmp_path))
    assert not same_place(str(tmp_path), None)


def test_a_judge_with_no_workdir_does_not_beat_the_judge_standing_in_the_work(roster, tmp_path,
                                                                              monkeypatch):
    place = tmp_path / "work"
    place.mkdir()
    monkeypatch.chdir(place)                      # the server stands where the work is
    roster.register("exec-1", "llm-executor", workdir=str(place))
    roster.register("zzz-real-val", "llm-validator", workdir=str(place))
    raw = json.loads(Path(roster._path).read_text(encoding="utf-8"))
    raw["aaa-checker"] = {"kind": "unittest-checker", "oracle_map": "m.json"}   # NO workdir
    Path(roster._path).write_text(json.dumps(raw), encoding="utf-8")

    fresh = AgentRegistry(str(roster._path))
    assert fresh.validator_for("exec-1") == "zzz-real-val"


def test_unregister_does_not_remove_a_placeless_role_on_a_workdir(roster, tmp_path, monkeypatch):
    """The conditional removal exists so a shared roster is not one run's to clear."""
    monkeypatch.chdir(tmp_path)
    roster.register("noplace", "external")
    assert roster.unregister("noplace", workdir=str(tmp_path))["unregistered"] is None
    assert roster.get("noplace") is not None


def test_a_place_matches_the_spelling_it_was_registered_under(roster, tmp_path):
    """Registration stores the path RESOLVED, which sees through 8.3 short names and junctions; a
    comparison built on `abspath` alone failed to match the very string it registered."""
    place = tmp_path / "a long directory name here"
    place.mkdir()
    if os.name != "nt":
        pytest.skip("8.3 short names are a Windows spelling")
    buf = ctypes.create_unicode_buffer(1024)
    if not ctypes.windll.kernel32.GetShortPathNameW(str(place), buf, 1024) or buf.value == str(place):
        # AUDIBLE, not a silent degeneration. Falling back to the long name made this the only case
        # that kills the `resolve()` in `same_place` pass while testing nothing - on a volume with
        # 8.3 creation disabled the whole fix would be invisible.
        pytest.skip("this volume has no 8.3 short names, so the spelling under test does not exist")
    short = buf.value
    roster.register("exec-1", "llm-executor", workdir=short)
    assert roster.unregister("exec-1", workdir=short)["unregistered"] == "exec-1"


def test_case_alone_does_not_make_two_places(tmp_path):
    """`normcase` is load-bearing on Windows.

    The directory must NOT exist: with it on disk, dropping `normcase` is masked - the text pass
    fails, the disk pass runs, and `resolve()` hands back the real on-disk casing for both sides.
    The first version of this test created the directory and therefore killed no mutant.
    """
    place = tmp_path / "Gone" / "Work"                 # never created
    other = str(place).replace("Gone", "gone").replace("Work", "work")
    assert same_place(str(place), other) is (os.name == "nt")


def test_two_spellings_of_one_place_are_settled_without_asking_the_disk(tmp_path, monkeypatch):
    """The text answer must be reached BEFORE `resolve()`, not merely agree with it.

    Otherwise the cost that motivated it is still paid: this comparison runs once per candidate
    judge, on every dispatch pass and every `list_agents`. A disk that refuses to answer proves the
    order.
    """
    place = tmp_path / "work"
    place.mkdir()

    def _forbidden(*_a, **_k):
        raise AssertionError("the filesystem was asked about two spellings text had already settled")

    monkeypatch.setattr(Path, "resolve", _forbidden)
    assert same_place(str(place), str(place).replace(os.sep, "/"))
    assert same_place(str(place) + os.sep, str(place))


def test_a_deleted_directory_is_still_compared_by_text(roster, tmp_path):
    """The fallback exists for exactly this: the disk cannot be asked any more."""
    place = tmp_path / "work"
    place.mkdir()
    roster.register("exec-1", "llm-executor", workdir=str(place))
    place.rmdir()
    assert same_place(str(place), str(place).replace(os.sep, "/"))
    assert roster.unregister("exec-1", workdir=str(place))["unregistered"] == "exec-1"


def test_the_named_limit_two_spellings_of_a_place_that_is_gone(tmp_path):
    """THE BOUNDARY, pinned rather than claimed away.

    Two spellings that only the filesystem can reconcile - an 8.3 short name against its long form -
    read as different places once the directory is gone, because there is nothing left to ask. The
    docstring says so; this holds it to that, so the day it changes is a decision and not a drift.
    """
    if os.name != "nt":
        pytest.skip("8.3 short names are a Windows spelling")
    place = tmp_path / "a long directory name here"
    place.mkdir()
    buf = ctypes.create_unicode_buffer(1024)
    if not ctypes.windll.kernel32.GetShortPathNameW(str(place), buf, 1024) or buf.value == str(place):
        pytest.skip("this volume has no 8.3 short names")
    short = buf.value
    assert same_place(str(place), short), "while it exists the disk reconciles them"
    place.rmdir()
    assert not same_place(str(place), short), "the limit moved - update the docstring, not the test"


def test_the_advice_names_the_spelling_that_actually_binds(tmp_path, monkeypatch):
    """`register_agent` tells the caller how to register the matching judge. The roster binds on the
    RESOLVED workdir, so advice quoting the caller's own relative argument names a different place
    when run from a different directory."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "work").mkdir()
    e = make_engine()
    monkeypatch.setattr(TL, "_roster", lambda _e: AgentRegistry(str(tmp_path / "roster.json")))
    # A transport with no `run_agent`: the door returns its own error right AFTER the workdir
    # pre-check and before anything is spawned, which is the window under test.
    monkeypatch.setattr(TL, "llm_factory", lambda *a, **k: object())
    out = TL.register_agent(e, "exec-1", "llm-executor", workdir="work")
    assert Path(out["workdir"]).is_absolute()
    assert "workdir='work'" not in str(out.get("will_be_judged_by", ""))
    assert out["workdir"] in str(out.get("will_be_judged_by", ""))


def test_the_judge_whose_spelling_matches_wins_over_one_that_needs_the_disk(tmp_path):
    """WHICH judge, decided rather than fallen into.

    Where two judges both stand in the work - one written the same way as the executor's workdir,
    one reachable only through a spelling the disk must reconcile - the textual one is chosen, even
    when the other sorts earlier. The alphabet was never a reason for anything; the exact spelling
    is what a reader comparing the roster to the workspace would also pick.

    Through a JUNCTION rather than an 8.3 short name: 8.3 creation is off by default on Windows
    Server and on many secondary volumes, and there this decision would have had no witness at all.
    """
    if os.name != "nt" or not _junction(tmp_path / "link", tmp_path / "real"):
        pytest.skip("no junction available here")
    place = tmp_path / "real"

    roster = AgentRegistry(str(tmp_path / "r.json"))
    roster.register("exec-1", "llm-executor", workdir=str(place))
    roster.register("zzz-same-spelling", "llm-validator", workdir=str(place))
    raw = json.loads(Path(roster._path).read_text(encoding="utf-8"))
    raw["aaa-needs-the-disk"] = {"kind": "llm-validator",
                                 "workdir": str(tmp_path / "link")}      # sorts FIRST
    Path(roster._path).write_text(json.dumps(raw), encoding="utf-8")

    fresh = AgentRegistry(str(roster._path))
    assert same_place(str(tmp_path / "link"), str(place)), "the link must really name the same place"
    assert fresh.validator_for("exec-1") == "zzz-same-spelling"


def test_a_network_path_is_not_asked_about(monkeypatch):
    """A UNC path to a host that does not answer costs 7-21 s in `is_dir()` on this platform.

    That call would sit on the DISPATCHER thread holding a concurrency slot, once per pass. Network
    paths are not asked - what is given up is a check, never a guarantee: the spawn behaves as it
    did before the guard existed.
    """
    if os.name != "nt":
        pytest.skip("a UNC share is a Windows spelling; on POSIX there is no remote path to withhold "
                    "the question about")
    unc = chr(92) * 2 + "host-that-does-not-answer" + chr(92) + "share" + chr(92) + "work"
    asked = []
    real_is_dir, real_resolve = Path.is_dir, Path.resolve

    def _spy_is_dir(self):
        asked.append(str(self))
        return real_is_dir(self)

    def _spy_resolve(self, *a, **k):
        asked.append(str(self))
        return real_resolve(self, *a, **k)

    monkeypatch.setattr(Path, "is_dir", _spy_is_dir)
    monkeypatch.setattr(Path, "resolve", _spy_resolve)
    assert missing_workdir({"workdir": unc}) is None
    assert _resolution_note(unc) == ""
    assert not same_place(unc, "C:" + os.sep + "elsewhere")
    assert not any(a.startswith(chr(92) * 2) for a in asked), asked


def test_a_network_path_registers_without_being_asked_about(tmp_path, monkeypatch):
    if os.name != "nt":
        pytest.skip("a UNC share is a Windows spelling; on POSIX this path is an ordinary "
                    "relative name and the registry is right to refuse it as missing")
    unc = chr(92) * 2 + "server" + chr(92) + "share" + chr(92) + "work"
    roster = AgentRegistry(str(tmp_path / "r.json"))
    roster.register("warm", "external")           # let the file be created before the spy goes on

    asked = []
    real_is_dir, real_resolve = Path.is_dir, Path.resolve
    monkeypatch.setattr(Path, "is_dir", lambda self: (asked.append(str(self)), real_is_dir(self))[1])
    monkeypatch.setattr(Path, "resolve",
                        lambda self, *a, **k: (asked.append(str(self)), real_resolve(self))[1])
    out = roster.register("exec-1", "llm-executor", workdir=unc)
    assert out["workdir"] == unc, "a network path is stored as written"
    assert not any(a.startswith(chr(92) * 2) for a in asked), asked


def test_a_local_path_is_still_asked_about(tmp_path):
    """Positive control: `cheap_to_ask` must not turn the guard off for ordinary paths."""
    assert cheap_to_ask(str(tmp_path))
    if os.name == "nt":          # a UNC share is a Windows spelling (see the classifier above)
        assert not cheap_to_ask(chr(92) * 2 + "server" + chr(92) + "share")
        assert not cheap_to_ask("//server/share")
    with pytest.raises(ValueError):
        AgentRegistry(str(tmp_path / "r.json")).register(
            "exec-1", "llm-executor", workdir=str(tmp_path / "gone"))


class _NotAPath:
    """An `os.PathLike` that is not a `Path`: `str()` would give its repr, and a repr classified as
    a filename is neither the right answer nor a detectable wrong one."""

    def __init__(self, p):
        self._p = p

    def __fspath__(self):
        return self._p


@pytest.mark.parametrize("path, askable, what", [
    (BS * 2 + "?" + BS + "C:" + BS + "Users", True, "extended-length LOCAL, 0.0 ms to stat"),
    ("//?/C:/Users", True, "the same in forward slashes"),
    (BS * 2 + "." + BS + "pipe" + BS + "x", True, "a device path is local"),
    (BS * 2 + "?" + BS + "UNC" + BS + "srv" + BS + "sh", False, "the one remote extended form"),
    (BS * 2 + "srv" + BS + "share", False, "a plain UNC share"),
    ("//srv/share", False, "a UNC share in forward slashes"),
    ("C:" + BS + "Users", True, "an ordinary local path"),
    ("work", True, "a relative path"),
    (BS * 2 + "server", False, "a bare UNC host with no share"),
    (BS * 2, True, "two separators alone name no host"),
    (BS * 2 + "?" + BS, True, "the extended prefix alone is local"),
    (BS * 2 + "?/UNC" + BS + "srv", False, "extended UNC written with mixed separators"),
    (BS * 2 + "?" + BS + "unc" + BS + "srv", False, "extended UNC in lower case"),
    (BS * 2 + "?" + BS + "UNC", False, "the extended UNC prefix with no host named"),
    ("C:", True, "a drive with no separator"),
    ("Q:" + BS + "x", True, "a drive letter that does not exist"),
    (Path("C:" + BS + "Users"), True, "a Path object rather than a string"),
    (_NotAPath(BS * 2 + "srv" + BS + "sh"), False, "an os.PathLike that is not a Path"),
])
def test_what_counts_as_too_expensive_to_ask_about(path, askable, what):
    """NETWORK, not "starts with two slashes".

    Classifying by the prefix alone was wrong in both directions: the extended-length and device
    forms are local and instant, and excluding them turned the whole registration guard off for
    them — the defect this exists to close, reachable free of charge through a prefix.

    EVERY ROW IS A WINDOWS SPELLING. A UNC share, a drive letter and the extended-length prefix are
    facts about one platform; on POSIX a backslash is an ordinary character in a filename and
    `//srv/share` is an ordinary absolute path, so nothing here is remote and the guard must never
    withhold the question. Asserted rather than skipped, because "no path is expensive" is the real
    POSIX behaviour and a guard that grew a second opinion there would be a defect nobody was
    watching for.
    """
    assert cheap_to_ask(path) is (askable if os.name == "nt" else True), what


def test_a_drive_letter_is_asked_of_the_mapping_table_not_the_network():
    """A share is commonly used through a MAPPED DRIVE LETTER, which carries no prefix at all and
    blocks for the same seconds. The local mapping table answers what a letter is without a packet
    leaving the machine."""
    if os.name != "nt":
        pytest.skip("drive letters are a Windows spelling")
    sysdrive = os.environ.get("SystemDrive", "C:")
    assert ctypes.windll.kernel32.GetDriveTypeW(sysdrive + os.sep) != 4, "the system drive is local"
    assert cheap_to_ask(sysdrive + os.sep + "Users")


def _junction(link, target):
    """Creates the TARGET too — `mklink /J` succeeds against a target that does not exist, and a
    link to nothing is not two spellings of one place.

    A junction — two spellings the DISK reconciles, on any NTFS volume, 8.3 or not. Needs no
    admin rights, unlike a symlink."""
    Path(target).mkdir(parents=True, exist_ok=True)
    return subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                          capture_output=True).returncode == 0


def test_the_disk_pass_reconciles_a_junction(tmp_path):
    """Every other witness for the paid pass is an 8.3 test, and 8.3 creation is off by default on
    Windows Server and on many secondary volumes — there the whole `resolve()` branch would be
    untested. A junction works everywhere."""
    if os.name != "nt" or not _junction(tmp_path / "link", tmp_path / "real"):
        pytest.skip("no junction available here")
    assert same_place(str(tmp_path / "link"), str(tmp_path / "real"))
    assert not same_place(str(tmp_path / "link"), str(tmp_path))


def test_the_spelling_that_was_typed_is_the_one_stored(tmp_path):
    """`resolve()` walks junctions, so a workdir named through a link was silently rewritten to its
    target — and that target is what the executor is spawned in and what the advice quotes back.
    Reconciling spellings is the comparison's job, not the roster's."""
    if os.name != "nt" or not _junction(tmp_path / "link", tmp_path / "real"):
        pytest.skip("no junction available here")
    roster = AgentRegistry(str(tmp_path / "r.json"))
    out = roster.register("exec-1", "llm-executor", workdir=str(tmp_path / "link"))
    assert out["workdir"] == str(tmp_path / "link")
    assert roster.unregister("exec-1", workdir=str(tmp_path / "real"))["unregistered"] == "exec-1"


def test_a_placeless_role_is_still_withdrawn_by_an_empty_workdir(roster):
    """Two roles with no place are not two places, but they are the same nothing — and this call is
    a run's budget-stop, so the silent half of moving the comparison is undone rather than lived
    with."""
    roster.register("noplace", "external")
    assert roster.unregister("noplace", workdir="")["unregistered"] == "noplace"


def test_a_path_argument_is_read_as_a_path_whatever_shape_it_arrives_in():
    """`str()` on a non-Path `os.PathLike` yields its repr, which would then be normalized as if it
    were a filename - a wrong answer that nothing downstream could detect."""
    weird = _NotAPath("C:" + BS + "Users" + BS + "x")
    assert text_place(weird) == text_place("C:" + BS + "Users" + BS + "x")


def _say_remote(monkeypatch, *letters):
    """Make `GetDriveTypeW` report those drive letters as DRIVE_REMOTE, without a network."""
    want = {ell.rstrip(BS).upper() for ell in letters}

    # ONLY `GetDriveTypeW` is replaced. Swapping `windll` wholesale hid every other kernel32 call
    # for the duration - and three tests in this file use `GetShortPathNameW`. Sequentially that
    # never overlapped; it is one worker thread away from an AttributeError, and the narrower patch
    # costs nothing.
    real = P.ctypes.windll.kernel32

    class _K:
        def __getattr__(self, name):
            return getattr(real, name)

        @staticmethod
        def GetDriveTypeW(root):
            return 4 if str(root).rstrip(BS).upper() in want else real.GetDriveTypeW(root)

    monkeypatch.setattr(P.ctypes, "windll", type("W", (), {"kernel32": _K()}))


def test_a_mapped_drive_letter_is_a_network_path(monkeypatch):
    """The most ordinary way a share is used, and the half of the rule nothing witnessed: deleting
    the drive-type branch left every case green, because the fallthrough also answers True."""
    if os.name != "nt":
        pytest.skip("drive letters are a Windows spelling")
    _say_remote(monkeypatch, "Z:")
    assert not cheap_to_ask("Z:" + BS + "work")
    assert not cheap_to_ask("Z:work"), "drive-relative is the same drive"
    assert not cheap_to_ask(BS * 2 + "?" + BS + "Z:" + BS + "work"), "and behind the extended prefix"
    assert cheap_to_ask("C:" + BS + "work"), "a local letter is still asked about"


def test_a_relative_workdir_inherits_the_drive_it_will_resolve_against(monkeypatch, tmp_path):
    r"""THE LOCATION, NOT THE SPELLING. `work` and `\work` carry no prefix and no letter, and resolve
    against the process's CURRENT drive - so on a server whose cwd is a mapped share they carry the
    full stall through a spelling the classifier never asked about."""
    if os.name != "nt":
        pytest.skip("drive letters are a Windows spelling")
    here = os.path.splitdrive(os.getcwd())[0]
    _say_remote(monkeypatch, here)
    assert not cheap_to_ask("work")
    assert not cheap_to_ask("." + BS + "work")
    assert not cheap_to_ask(BS + "work")


def test_the_guard_still_fires_when_the_cwd_is_local(monkeypatch, tmp_path):
    """Positive control: the drive lookup must not turn every relative path into "do not ask"."""
    assert cheap_to_ask("work")
    with pytest.raises(ValueError):
        AgentRegistry(str(tmp_path / "r.json")).register(
            "exec-1", "llm-executor", workdir=str(tmp_path / "gone"))


def test_a_network_workdir_is_still_stored_absolute(tmp_path, monkeypatch):
    """Skipping the `stat` was never a reason to leave the path relative: `abspath` asks nothing."""
    if os.name != "nt":
        pytest.skip("drive letters are a Windows spelling")
    _say_remote(monkeypatch, "Z:")
    roster = AgentRegistry(str(tmp_path / "r.json"))
    out = roster.register("exec-1", "llm-executor", workdir="Z:work")
    assert out["workdir"] == "Z:" + BS + "work"


def test_the_validation_door_asks_the_same_question_of_the_same_directory(monkeypatch, tmp_path):
    """The rule kept in two places is the defect this repository keeps paying for.

    `validate_result`'s pre-check stats the workdir and then ENUMERATES it, and either against a
    share whose host does not answer costs 7-21 s on the caller's own thread - the cost the
    dispatcher's guard exists to avoid, at the one other door that asks about the same directory.
    """
    if os.name != "nt":
        pytest.skip("drive letters are a Windows spelling")
    _say_remote(monkeypatch, "Z:")

    # A NODE THAT REALLY REACHES THE CHECK. The first version of this test named a task that does
    # not exist, so the door refused on that and returned long before the workdir was looked at -
    # the mutation that removes the guard left it green, which is how it was caught. The spies go
    # on AFTER the graph is built, or they answer for the store as well.
    e = make_engine(validate_signals=True)
    e.start()
    T.create_task(e, "n1", {"name": "Nail", "description": "hammer a nail",
                            "criteria": [{"name": "flush", "description": "nail is flush"}]}, "alice")
    T.signal(e, "n1", "ACCEPT", "alice")
    assert T.signal(e, "n1", "DELIVER", "alice", result="done")["state"] == "VALIDATING"
    monkeypatch.setattr(TL, "_roster", lambda _e: AgentRegistry(str(tmp_path / "roster.json")))

    asked = []
    real_is_dir, real_iterdir = Path.is_dir, Path.iterdir
    monkeypatch.setattr(Path, "is_dir", lambda self: (asked.append(str(self)), real_is_dir(self))[1])
    monkeypatch.setattr(Path, "iterdir",
                        lambda self: (asked.append(str(self)), real_iterdir(self))[1])
    TL.validate_result(e, "n1", workdir="Z:" + BS + "work")
    e.stop()
    assert not any(a.upper().startswith("Z:") for a in asked), asked
