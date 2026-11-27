"""A part's change no longer all there in its whole's tree is named before the whole's session. On GB_c_compiler_toccc3884
a merge lost one part's long-double code and it surfaced only at the whole's validation, a round later; running the parts'
checks to see it put a question of work on the checks' clock (three critics). The change itself is the evidence."""
import shutil
import subprocess
from pathlib import Path

import pytest

from gfso import sessions as S, tools as T
from gfso.adapters import git as G, worktrees as W
from gfso.core.types import Mode, State, TaskId
from gfso.delegate import AgentRegistry
from gfso.packets import executor_packet
from gfso.workspaces import _enter_workspace, _ensure_place, _workspace, parts_not_there
from tests.support import criterion, make_engine
from tests.test_a_node_works_in_its_own_place import _repo as _repo_of
from tests.test_the_mode_decides_who_holds_what import _admit, _engine, _kid


def _git(d, *a):
    return subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True, text=True).stdout.strip()


def _commit(d):
    _git(d, "add", "-A")
    _git(d, "commit", "-q", "--allow-empty", "-m", "the whole's tree as it stands")


def _repo(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    (d / "a.c").write_bytes(b"int a;\nint b;\nint c;\n")
    (d / "other.c").write_bytes(b"x\n")
    _git(d, "add", ".")
    _git(d, "commit", "-qm", "base")
    base = _git(d, "rev-parse", "HEAD")
    _git(d, "switch", "-qc", "part")
    (d / "a.c").write_bytes(b"int a;\nlong double ld;\nint b;\nint c;\n")
    (d / "new.c").write_bytes(b"part\n")
    _git(d, "add", ".")
    _git(d, "commit", "-qm", "part")
    sha = _git(d, "rev-parse", "HEAD")
    _git(d, "switch", "-q", "main")
    _git(d, "merge", "-q", "--no-ff", "-m", "join", sha)
    return d, base, sha


def test_a_part_whose_change_stands_is_not_named(tmp_path):
    d, base, sha = _repo(tmp_path)
    assert W.change_not_there(d, base, sha) == []
    (d / "a.c").write_bytes(b"int a;\nlong double ld;\nint b;\nint c;\nint mine;\n")   # …the whole's own work beside it
    (d / "other.c").write_bytes(b"y\n")
    _commit(d)
    assert W.change_not_there(d, base, sha) == []


def test_a_part_whose_lines_a_merge_dropped_is_named_by_file(tmp_path):
    d, base, sha = _repo(tmp_path)
    (d / "a.c").write_bytes(b"int a;\nint b;\nint c;\n")            # …the long double gone, as a bad merge leaves it
    _commit(d)
    assert W.change_not_there(d, base, sha) == ["a.c"]
    (d / "new.c").unlink()
    _commit(d)
    assert W.change_not_there(d, base, sha) == ["a.c", "new.c"]


def test_a_part_whose_lines_were_changed_is_named(tmp_path):
    d, base, sha = _repo(tmp_path)
    (d / "a.c").write_bytes(b"int a;\ndouble ld;\nint b;\nint c;\n")
    _commit(d)
    assert W.change_not_there(d, base, sha) == ["a.c"]


def test_what_is_not_a_commit_is_never_put_to_the_shell(tmp_path):
    d, base, _ = _repo(tmp_path)
    assert W.change_not_there(d, base, "HEAD; rm -rf /") == []


@pytest.mark.skipif(shutil.which("git") is None, reason="the node workspaces are git worktrees")
def test_the_wholes_packet_names_a_joined_part_whose_work_is_gone(tmp_path):
    """Through the session's own entry: the part joins the whole's place, the whole's tree loses its line, the packet
    and the person's line say which part and which file — and nothing while the part's work stands."""
    base = _repo_of(tmp_path / "ws")
    e = _engine(Mode.AUTO)
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]})
    _admit(e, "root", _kid("root.part", ["g"], criterion("k", "K holds")), _kid("root.other", ["g"], criterion("o", "O")))
    e.wait_idle()
    agents = AgentRegistry(path=str(tmp_path / "agents.json"))
    for a in ("exec-1", "exec-2"):
        agents.register(a, "llm-executor", workdir=str(base), project="p")
    for tid, name, text in (("root.other", "other.c", "int o;\n"), ("root.part", "ld.c", "long double ld;\n")):
        part = e.graph.get_task(TaskId(tid))       # …two parts: each one's change from where ITS join met the whole
        w = _workspace(e, agents, part)
        _ensure_place(e, agents, part, w)
        (Path(w[1]) / name).write_bytes(text.encode())
        W.commit_all(w[0], w[1], f"{tid} works", "t", branch=w[2])
        part.state = State.DONE
        e.graph.save_task(part)
    root = e.graph.get_task(TaskId("root"))
    place, unjoined, _w = _enter_workspace(e, agents, root, [root])
    assert not unjoined and parts_not_there(e, agents, [root], place) == []
    (Path(place) / "ld.c").write_bytes(b"double ld;\n")                    # …a later merge's resolution, say
    W.commit_all(base, place, "a later merge's resolution", "t")
    lost = parts_not_there(e, agents, [root], place)
    assert [(x, f) for x, f, *_ in lost] == [("root.part", ["ld.c"])]
    text = executor_packet(e, root, place, unjoined, None, lost)
    assert "## Parts whose work is no longer all in your tree" in text and "`ld.c` (last changed by" in text and "`root.part`" in text
    e.stop()


def test_an_executor_round_hands_its_packet_the_parts_not_there(monkeypatch, tmp_path):
    """…its place a directory of its own: given `.`, the session's observation copied and weighed this whole repository
    — its data and the suite's temp — 190 s of the suite's 420 (2026-11-27)."""
    e = make_engine()
    e.start()
    T.TOOLS["create_task"](e, "root", {"description": "the goal", "criteria": [criterion("g", "G holds")]},
                           assignee="me")
    e.wait_idle()
    T.signal(e, "root", "ACCEPT", "me")
    e.wait_idle()
    asked, said = {}, []
    monkeypatch.setattr(S, "_enter_workspace", lambda *a, **k: (str(tmp_path), [], None))
    monkeypatch.setattr(S, "parts_not_there", lambda *a, **k: [("root.part", ["ld.c"], "a" * 12, "b" * 12, {"ld.c": "c0ffee1 a sibling joins"})])
    monkeypatch.setattr(S, "performer", lambda *a, **k: ("me", {"workdir": str(tmp_path)}))
    monkeypatch.setattr(S, "emit_cb", lambda *a, **k: said.append)

    def _stop(engine, node_id, executor_id, cfg, _llm, role, prompt, packet, *a, **k):
        asked["packet"] = packet
        raise RuntimeError("stop at the spawn")
    monkeypatch.setattr(S, "_spawn", _stop)
    try:
        out = S.run_executor(e, TaskId("root"), "me", {})
    except RuntimeError:
        out = None
    assert out is None, out
    assert "`ld.c` (last changed by c0ffee1 a sibling joins)" in asked["packet"] and any("root.part (ld.c)" in s for s in said), said
    e.stop()


def test_an_empty_delivery_and_an_unreadable_answer_claim_nothing(tmp_path):
    """A part whose accepted change is empty joins as a merge too (`commit_all --allow-empty`): git's "No valid
    patches" was named as a lost file (critic)."""
    d, base, _ = _repo(tmp_path)
    _git(d, "commit", "-q", "--allow-empty", "-m", "nothing")
    assert W.change_not_there(d, base, _git(d, "rev-parse", "HEAD~1")) == []
    empty = _git(d, "rev-parse", "HEAD")
    assert W.change_not_there(d, _git(d, "rev-parse", "HEAD~1"), empty) == []


def test_a_file_the_part_created_and_others_extended_is_not_named(tmp_path):
    """Reversing a creation asked the whole file to be exactly the part's: a sibling's appended line named it (critic)."""
    d, base, sha = _repo(tmp_path)
    (d / "new.c").write_bytes(b"#include <x.h>\npart\nmore by a sibling\n")
    _commit(d)
    assert W.change_not_there(d, base, sha) == []
    (d / "new.c").write_bytes(b"#include <x.h>\nmore by a sibling\n")      # …and the part's own line gone
    _commit(d)
    assert W.change_not_there(d, base, sha) == ["new.c"]


def test_a_file_the_part_deleted_and_someone_recreated_is_not_named(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    (d / "old.c").write_bytes(b"old\n")
    _commit(d)
    base = _git(d, "rev-parse", "HEAD")
    (d / "old.c").unlink()
    _commit(d)
    sha = _git(d, "rev-parse", "HEAD")
    (d / "old.c").write_bytes(b"back\n")
    _commit(d)
    assert W.change_not_there(d, base, sha) == []


def test_what_is_staged_is_not_the_committed_tree(tmp_path):
    """The place's index may hold what a handover staged: HEAD is what is read (critic, both ways)."""
    d, base, sha = _repo(tmp_path)
    (d / "a.c").write_bytes(b"int a;\nint b;\nint c;\n")
    _git(d, "add", "a.c")                                     # …staged, not committed: HEAD still has the line
    assert W.change_not_there(d, base, sha) == []
    _commit(d)
    (d / "a.c").write_bytes(b"int a;\nlong double ld;\nint b;\nint c;\n")
    _git(d, "add", "a.c")                                     # …HEAD lost it, a staged edit restores it
    assert W.change_not_there(d, base, sha) == ["a.c"]


def test_the_repositorys_own_diff_config_hides_no_loss(tmp_path):
    d, base, sha = _repo(tmp_path)
    for k, v in (("diff.noprefix", "true"), ("color.diff", "always"), ("diff.renames", "copies"), ("core.quotePath", "true")):
        _git(d, "config", k, v)
    (d / "a.c").write_bytes(b"int a;\nint b;\nint c;\n")
    _commit(d)
    assert W.change_not_there(d, base, sha) == ["a.c"]


class _ShHere:
    """An execution whose place's container is this host's `sh`: the container path's one shell, run as written."""
    python = "python"

    def session(self, repo):
        return self

    def run(self, args, *, cwd, timeout, env=None):
        return subprocess.run(args, cwd=cwd, timeout=timeout, env=env, capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("sh") is None, reason="the container path is one sh pipeline")
def test_the_container_path_answers_as_the_host_one(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "apart", lambda execution: G.APART)
    d, base, sha = _repo(tmp_path)
    ex = _ShHere()
    assert W.change_not_there(d, base, sha, execution=ex) == []
    (d / "a.c").write_bytes(b"int a;\nint b;\nint c;\n")
    _commit(d)
    assert W.change_not_there(d, base, sha, execution=ex) == ["a.c"]


def test_a_line_inserted_inside_a_parts_block_is_not_a_loss(tmp_path):
    """A zero-context reversal demanded the part's block contiguous: a field a sibling inserted named it (critic)."""
    d, base, sha = _repo(tmp_path)
    (d / "a.c").write_bytes(b"int a;\nlong double ld;\nint sibling;\nint b;\nint c;\n")
    _commit(d)
    assert W.change_not_there(d, base, sha) == []


def test_a_name_that_globs_names_nothing_else(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    (d / "t1.c").write_bytes(b"one\n")
    _commit(d)
    base = _git(d, "rev-parse", "HEAD")
    (d / "t[1].c").write_bytes(b"part\n")
    _commit(d)
    sha = _git(d, "rev-parse", "HEAD")
    (d / "t1.c").write_bytes(b"changed\n")
    _commit(d)
    assert W.change_not_there(d, base, sha) == []


def test_a_deleted_comment_line_is_no_file_header_and_a_spaced_name_is_read_whole(tmp_path):
    """A content line "-- …" deleted read as a header and dropped the file's later hunks; git ends a spaced path's
    header with a TAB (critic)."""
    d = tmp_path / "r"
    d.mkdir()
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    (d / "my q.sql").write_bytes(b"-- a comment\nselect 1;\n")
    _commit(d)
    base = _git(d, "rev-parse", "HEAD")
    (d / "my q.sql").write_bytes(b"-- a comment\nselect 1;\nselect 2;\n")
    _commit(d)
    sha = _git(d, "rev-parse", "HEAD")
    (d / "my q.sql").write_bytes(b"select 1;\n")                  # …the comment removed, the part's line lost
    _commit(d)
    assert W.change_not_there(d, base, sha) == ["my q.sql"]


def test_the_commit_named_is_the_join_that_lost_it(tmp_path):
    """`log -1 -- f` simplified away the merge that kept the whole's side and named the whole's own edit (critic)."""
    d, base, _ = _repo(tmp_path)
    _git(d, "reset", "-q", "--hard", base)
    _git(d, "switch", "-qc", "p2")
    (d / "a.c").write_bytes(b"int a;\nint part2;\nint b;\nint c;\n")
    _commit(d)
    sha = _git(d, "rev-parse", "HEAD")
    _git(d, "switch", "-q", "main")
    (d / "a.c").write_bytes(b"int a;\nint whole;\nint b;\nint c;\n")
    _git(d, "commit", "-qam", "the whole's own edit")
    _git(d, "merge", "-q", "-s", "ours", "-m", "the join that kept the whole's side", sha)
    assert W.change_not_there(d, base, sha) == ["a.c"]
    by = W.git(d, "--literal-pathspecs", "log", "-1", "--ancestry-path", "--format=%s", f"{sha}..HEAD", "--",
               "a.c").stdout.strip()
    assert by == "the join that kept the whole's side"
