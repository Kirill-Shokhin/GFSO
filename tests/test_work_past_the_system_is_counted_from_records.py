"""Work past the system is counted from records, never refused (`past.past_the_system`, served in `metrics`): the
commits made by hand in the repository during the project while no node attached there was taken, whose content no
work of the system carries — a chat delivery's own range, what its places and landings made, by patch or every path's
result — nor a commit that stood before the project, by patch; what is made while a node is taken there is listed
apart while it stays taken (`in_work`).

Work before or outside consent cannot be gated (§16.9 #11, §12.16), and opacity inside the protocol is a measurable
defect (Cor. to Thm 11). Each test is a case of the table the measure was built from; each ran red on main before it
(no such reading), and the mutation named in its docstring turns it red again.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

import gfso.past as P
import gfso.tools as T
import gfso.tools_llm as TL
from gfso.core.types import AgentId, Mode
from tests.support import REGISTER, criterion, make_engine

OLD, LATER = "2001-01-01T00:00:00Z", "2099-01-01T00:00:00Z"


@pytest.fixture(autouse=True)
def _a_roster_of_its_own(tmp_path, monkeypatch):
    monkeypatch.setenv("GFSO_AGENTS_PATH", str(tmp_path / "agents.json"))
    monkeypatch.setenv("GFSO_DATA_DIR", str(tmp_path / "data"))         # …the person's record of where hooks stand


def _git(repo, *a, when=None) -> str:
    env = {**os.environ, **({"GIT_COMMITTER_DATE": when, "GIT_AUTHOR_DATE": when} if when else {})}
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=u", "-c", "user.email=u@x", *a], capture_output=True,
                          text=True, check=True, env=env).stdout.strip()


def _commit(repo, name, text="x\n", when=None) -> str:
    (repo / name).write_text(text)
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", name, when=when)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _commit(r, "README", when=OLD)           # …the repository as it stood before the project
    return r


def _in_chat(place: Path, project="p", take=True, storage=None):
    """A project whose root its holder performs in this repository's chat, taken (ACCEPT) there."""
    e = make_engine(storage, validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = project
    assert not TL.TOOLS["register_agent"](e, f"val-{project}", "llm-validator", workdir=str(place)).get("refused")
    e.set_mode(Mode.SOLO, None, AgentId("user"), hands=None)
    T.create_task(e, "root", {"description": "write f", "accepted_risks": REGISTER,
                              "criteria": [criterion("f", "f.txt says v1")]})
    e.wait_idle()
    if take:
        _take(e)
    return e


def _take(e, node="root"):
    assert TL.TOOLS["signal"](e, node, "ACCEPT", "user")["accepted"]


def _deliver(e):
    assert TL.TOOLS["signal"](e, "root", "DELIVER", "user", result="f.txt", self_validation="PASS")["accepted"]


def _past(e) -> dict:
    got = TL.TOOLS["metrics"](e)["past_the_system"]
    assert len(got) == 1, got
    return got[0]


def test_a_chats_accept_records_where_and_from_which_head_its_node_is_at_work(repo):
    """The one record both catches read: the ACCEPT of a node its holder performs in the repository's chat carries the
    repository and its HEAD; the node is attached there, taken now. CONTROL: `tools_llm.signal` recording nothing at
    ACCEPT — no row names it."""
    head = _git(repo, "rev-parse", "HEAD")
    e = _in_chat(repo)
    row = next(x for x in e.audit_log() if x.signal.name == "ACCEPT")
    assert (row.commit, Path(row.repository).resolve()) == (head, repo.resolve())
    assert [(t.repository, t.node, t.until, t.holder) for t in P.spans(e, TL._delegation().default_agents())] == [
        (P.repository(repo), "root", None, "user")]


def test_a_hand_commit_stays_counted_when_a_delivery_is_built_on_it(repo):
    """A delivery holds its own range, from the HEAD its node's ACCEPT recorded — not the history under it (every hand
    commit a delivery was built on read as delivered). CONTROL: the chat range without `^head` — the count reads 0."""
    e = _in_chat(repo, take=False)
    hand = _commit(repo, "hand.txt")
    time.sleep(1.1)                                            # …the reflog's clock is whole seconds
    _take(e)
    _commit(repo, "f.txt", "v1\n")
    _deliver(e)
    got = _past(e)
    assert (got["count"], got["commits"]) == (1, [hand]), got


def test_a_fold_of_a_delivery_rebased_onto_a_moved_base_is_still_the_delivery(repo, tmp_path):
    """This repository's own practice: two delivered commits, the base moves, a rebase folds them into one — every path
    it changes ends at a blob the delivery wrote, though no patch nor tree is the same. CONTROL: the per-path match
    dropped (patch alone) — the fold counts."""
    up = tmp_path / "up"
    _git(tmp_path, "clone", "-q", str(repo), str(up))
    e = _in_chat(repo)
    _git(repo, "switch", "-q", "-c", "work")
    _commit(repo, "f.txt", "v1\n")
    _commit(repo, "f.txt", "v2\n")
    _commit(repo, "g.txt", "g\n")
    _deliver(e)
    _commit(up, "other.txt")
    _git(repo, "fetch", "-q", str(up), "main:main")                            # …the base moves
    _git(repo, "rebase", "-q", "main")
    _git(repo, "reset", "-q", "--soft", "main")
    _git(repo, "commit", "-q", "-m", "folded")
    got = _past(e)
    assert got["count"] == 0, got


def test_what_a_reflog_no_longer_holds_the_projects_record_keeps(repo):
    """A reflog expires (90 days by default) and took the hand commit with it; the reading it gave before is kept in
    the project's record. A record that begins after the project did says from when (`read_from`). CONTROL: `_kept`
    reading the reflog alone — the count drops to 0."""
    e = _in_chat(repo)
    _deliver(e)
    hand = _commit(repo, "hand.txt")
    assert _past(e)["commits"] == [hand]
    _git(repo, "reflog", "expire", "--expire=now", "--all")
    _commit(repo, "more.txt")                                  # …the refs move: the cached reading is read again
    got = _past(e)
    assert hand in got["commits"] and got["count"] == 2 and "read_from" not in got, got
    later = _in_chat(repo, project="late")
    _deliver(later)
    _git(repo, "reflog", "expire", "--expire=now", "--all")
    _commit(repo, "after.txt", when=LATER)                     # …the oldest entry left is past the project's start
    assert _past(later)["read_from"] >= 4070908800, "the reading does not say from when its record holds"


def test_a_commit_made_after_the_delivery_is_counted_and_the_delivered_and_the_older_are_not(repo):
    """The delivered commit is in its delivery's own range; what stood before the project is outside the window."""
    e = _in_chat(repo)
    a = _commit(repo, "f.txt", "v1\n")
    _deliver(e)
    b = _commit(repo, "g.txt")
    got = _past(e)
    assert (got["count"], got["commits"], got["in_work"]) == (1, [b], []), got
    assert a not in got["commits"] and Path(got["repository"]).resolve() == repo.resolve()


def test_a_squash_an_amend_a_rebase_and_a_cherry_pick_of_the_delivered_work_are_still_the_delivery(repo):
    """A delivery's work under another sha — every path a commit changes ending where the delivery left it, or its
    patch — is covered, as no ancestry can say; an amend that changes the content stays counted. CONTROL: the per-path
    match dropped — the squash counts."""
    e = _in_chat(repo)
    _git(repo, "switch", "-q", "-c", "work")
    _commit(repo, "f.txt", "v1\n")
    _commit(repo, "f2.txt", "v1\n")
    _deliver(e)
    _git(repo, "branch", "-q", "line", "HEAD")
    _git(repo, "reset", "-q", "--soft", "main")
    _git(repo, "commit", "-q", "-m", "squashed")                               # …squash: the delivery's tree
    _git(repo, "commit", "-q", "--amend", "-m", "squashed, reworded")          # …amend: the same tree
    _git(repo, "switch", "-q", "-c", "other", "main")
    mine = _commit(repo, "h.txt")
    _git(repo, "cherry-pick", "line~1")                                        # …cherry-pick: the delivered patch
    _git(repo, "rebase", "-q", "--onto", "other", "line~1", "line")            # …rebase: the delivered patch again
    _git(repo, "switch", "-q", "main")
    changed = _commit(repo, "f.txt", "v1 and more\n")
    got = _past(e)
    assert sorted(got["commits"]) == sorted([mine, changed]) and got["count"] == 2, got


def test_a_pull_brings_no_work_past_the_system_and_a_push_hides_none(repo, tmp_path):
    """A fast-forward pull and a merge move the repository to commits made elsewhere — no reflog of it records making
    them —, while a commit made here and pushed to the person's own remote before any delivery is still made here
    (excluding every remote hid it). CONTROL: `MADE` matching every reflog entry — the pulled commits count."""
    up = tmp_path / "up"
    _git(tmp_path, "clone", "-q", str(repo), str(up))
    e = _in_chat(repo)
    _deliver(e)                                                                # …no node at work from here on
    far = [_commit(up, f"u{i}.txt") for i in range(2)]
    _git(repo, "pull", "-q", "--ff-only", str(up), "main")                    # …fast-forward
    _commit(up, "u3.txt")
    mine = _commit(repo, "mine.txt")
    _git(repo, "pull", "-q", "--no-rebase", "--no-edit", str(up), "main")    # …a merge of what was made elsewhere
    (bare := tmp_path / "own.git").mkdir()
    _git(bare, "init", "-q", "--bare")
    _git(repo, "remote", "add", "own", str(bare))
    _git(repo, "push", "-q", "own", "main")
    got = _past(e)
    assert got["commits"] == [mine] and got["count"] == 1 and not set(far) & set(got["commits"]), got


def test_merging_a_delivered_branch_counts_neither_the_merge_nor_what_it_brings(repo):
    """A merge is no commit made by the person's own act (`MADE`), and no merge is read (`--no-merges`): either alone
    holds it — CONTROL: both dropped, the merge counts; what a conflicted merge's resolution carries is not read."""
    e = _in_chat(repo)
    _git(repo, "switch", "-q", "-c", "side")
    _commit(repo, "f.txt", "v1\n")
    _deliver(e)
    _git(repo, "switch", "-q", "main")
    mine = _commit(repo, "h.txt")
    _git(repo, "merge", "-q", "--no-edit", "side")
    got = _past(e)
    assert got["commits"] == [mine] and got["count"] == 1, got


def test_a_project_the_system_performs_is_read_in_the_repository_its_role_names(repo, tmp_path):
    """A container's or this host's executor delivers in a place of the system's, its DELIVER naming no repository: the
    repository is its role's workdir, where its result lands under the system's refs (it read None, on the main path).
    What the landing holds of the person's own history is not the system's: a hand commit the import carried stays
    counted. CONTROL: `_repositories` reading the log alone — no reading; the landing's range not cut by the hand-made
    (`- made.keys()`) — the carried hand commit reads as landed."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    assert not TL.TOOLS["register_agent"](e, "p-exec-1", "llm-executor", workdir=str(repo)).get("refused")
    T.create_task(e, "root", {"description": "write f", "accepted_risks": REGISTER,
                              "criteria": [criterion("f", "f.txt says v1")]})
    e.wait_idle()
    carried = _commit(repo, "carried.txt")                     # …in the person's HEAD when the base is imported
    _git(tmp_path, "clone", "-q", str(repo), str(box := tmp_path / "volume"))
    landed = _commit(box, "f.txt", "v1\n")                     # …made in the system's place
    _git(repo, "fetch", "-q", str(box), "main:refs/heads/gfso/p/accepted")   # …landed, as `worktrees.land` does
    mine = _commit(repo, "h.txt")
    _git(repo, "merge", "-q", "--no-edit", "gfso/p/accepted")
    got = _past(e)
    assert sorted(got["commits"]) == sorted([mine, carried]) and landed not in got["commits"], got


def _cancelled(e):
    assert TL.TOOLS["signal"](e, "root", "CANCEL", "user", reason="dropped")["accepted"]
    assert TL.TOOLS["signal"](e, "root", "CONFIRM_CANCEL", "user", in_flight="nothing")["accepted"]
    assert e.graph.get_task("root").state.name == "ABANDONED"


def test_a_node_taken_in_the_repository_holds_what_is_made_there_while_it_is_taken_on_any_line(repo, tmp_path,
                                                                                               monkeypatch):
    """Consented work is the node's by the moment it was made, on whatever line — a fork from before the HEAD its
    ACCEPT recorded as much (descent from that HEAD was the rule an amend broke, finding B) —; a node taken in another
    repository holds nothing here (any node at work anywhere read 0 through every run). Cancelled, what was made while
    it was taken stays the obligation's — the cancel records what was in flight (§11.6) — and leaves `in_work`; what is
    made after counts. CONTROL: every span read as attached to the repository measured — the commit after the cancel is
    in work under the other repository's node; a span not closed at its move out of work — what was made under it
    reads past."""
    _commit(repo, "R2", when=OLD)
    _git(repo, "init", "-q", "-b", "main", str(other := tmp_path / "other"))
    _commit(other, "README", when=OLD)
    e, q = _in_chat(repo), _in_chat(other, project="q")
    monkeypatch.setattr(P, "OPEN", lambda: [e, q])
    w = _commit(repo, "f.txt")
    _git(repo, "switch", "-q", "-c", "fork", "HEAD~2")
    fork = _commit(repo, "fork.txt")
    _git(repo, "switch", "-q", "main")
    got = _past(e)
    assert (sorted(got["in_work"]), got["count"]) == (sorted([w, fork]), 0), got
    time.sleep(1.1)                                            # …the reflog's clock is whole seconds
    _cancelled(e)
    after = _commit(repo, "g.txt")
    got = _past(e)
    assert (got["in_work"], got["commits"]) == ([], [after]), got


def test_another_projects_work_on_the_repository_is_the_systems_not_this_ones(repo, monkeypatch):
    """The server holds every project: a second project's chat node at work there holds what is built on its taking,
    and its delivery its own range. CONTROL: `_engines` reading this project alone — the other's commits count."""
    e = _in_chat(repo)
    _deliver(e)
    q = _in_chat(repo, project="q")
    monkeypatch.setattr(P, "OPEN", lambda: [e, q])
    theirs = _commit(repo, "o.txt")
    got = _past(e)
    assert (got["count"], got["in_work"]) == (0, [theirs]), got
    _deliver(q)
    mine = _commit(repo, "mine.txt")
    got = _past(e)
    assert (got["commits"], got["in_work"]) == ([mine], []), got


def test_a_direction_taken_for_months_holds_the_work_built_on_it_and_only_what_came_after_it_was_taken(repo):
    """In work is a taken node, a direction ACCEPTed for months (this repository's dev graph) as much as a leaf: what is
    built on it after it was taken is `in_work`, not past the system; what was made before the ACCEPT on its line is.
    CONTROL: a node with a live child left out of `taken_in` — the hand commit counts past the system; the time test
    dropped — the commit made before the ACCEPT is in work."""
    e = _in_chat(repo, take=False)
    early = _commit(repo, "early.txt")                         # …made before the direction is taken…
    _git(repo, "reset", "-q", "--hard", "HEAD~1")
    time.sleep(1.1)                                            # …the reflog's clock is whole seconds
    _take(e)                                                   # …the direction taken on README…
    _git(repo, "reset", "-q", "--hard", early)                 # …and the line moved back onto it: built on, not after
    T.decompose(e, "root", [{"task_id": "part", "assignee": "user", "covers": ["f"],
                             "spec": {"description": "a part", "criteria": [criterion("g", "g")]}}], accepted_risks=REGISTER)
    e.wait_idle()
    assert e.graph.get_active_children("root"), "the direction has no part"
    hand = _commit(repo, "hand.txt")
    got = _past(e)
    assert got["in_work"] == [hand] and got["commits"] == [early], got


def test_a_finished_project_counts_nothing_made_after_it_ended(repo):
    """The window closes at the root's settling: the repository's later work is no work of this project. CONTROL: the
    window left open — the later commit counts."""
    e = _in_chat(repo)
    _commit(repo, "f.txt", "v1\n")
    _deliver(e)
    during = _commit(repo, "g.txt")
    _cancelled(e)
    _commit(repo, "after.txt", when=LATER)
    got = _past(e)
    assert got["commits"] == [during] and got["count"] == 1, got


def test_a_node_taken_before_its_accept_named_a_repository_is_at_work_where_its_project_works(repo):
    """Finding A: every node taken before an ACCEPT recorded its repository — the dev graph's directions, months long —
    was at work nowhere, and the work made under it read as past the system. Its project works in the repository its
    roles stand in: the node is attached there. CONTROL: attachment read from the ACCEPT row alone — the commit counts."""
    e = _in_chat(repo, take=False)
    assert T.signal(e, "root", "ACCEPT", "user")["accepted"]                   # …the door that records no repository
    assert not next(x for x in e.audit_log() if x.signal.name == "ACCEPT").repository
    w = _commit(repo, "f.txt")
    got = _past(e)
    assert (got["count"], got["in_work"]) == (0, [w]), got


def test_an_amend_of_the_head_a_node_was_taken_on_leaves_the_work_after_it_in_work(repo):
    """Finding B: work is in work by the moment it was made, not by descent from the HEAD the ACCEPT recorded — one amend
    of that HEAD (this repository's practice) turned every later commit on the node into past. CONTROL: in work read as
    descent from the ACCEPT HEAD (1454764) — the amend and the commit after it count."""
    e = _in_chat(repo)
    _git(repo, "commit", "-q", "--amend", "-m", "README, reworded")
    amended = _git(repo, "rev-parse", "HEAD")
    w = _commit(repo, "f.txt")
    got = _past(e)
    assert (got["count"], sorted(got["in_work"])) == (0, sorted([amended, w])), got


def test_a_branch_made_before_the_project_and_rebased_during_it_is_no_work_past_the_system(repo, tmp_path):
    """Finding C: a rebase replays commits that stood before the project began; the reflog dates the copies at the
    rebase, and their content is carried by the commits the rebase replaced. A commit new in content on the same line
    is still counted. CONTROL: the commits that existed before the project not read as content — the copies count."""
    up = tmp_path / "up"
    _git(tmp_path, "clone", "-q", str(repo), str(up))
    _git(repo, "switch", "-q", "-c", "old")
    _commit(repo, "o1.txt", when=OLD)
    _commit(repo, "o2.txt", "two\n", when=OLD)
    _git(repo, "switch", "-q", "main")
    e = _in_chat(repo, take=False)
    _commit(up, "other.txt")
    _git(repo, "pull", "-q", "--ff-only", str(up), "main")                    # …the base moves, made elsewhere
    _git(repo, "rebase", "-q", "main", "old")
    new = _commit(repo, "n.txt")
    got = _past(e)
    assert (got["count"], got["commits"]) == (1, [new]), got


def test_a_node_the_system_performs_holds_no_hand_commit_in_the_persons_repository(repo):
    """A node a registered role of the system performs records no repository at its ACCEPT, as a node taken before that
    record did — but its work reaches the person's repository only through the system's refs and landings, which are
    read by content. Only a node performed in its holder's own chat falls back to where its project works. CONTROL: the
    fallback for every holder — the hand commit is in work while the system's executor holds the node."""
    e = make_engine(validate_signals=True, state_timeout=0)
    e.start()
    e.project_name = "p"
    assert not TL.TOOLS["register_agent"](e, "s-exec-1", "llm-executor", workdir=str(repo)).get("refused")
    T.create_task(e, "root", {"description": "write f", "accepted_risks": REGISTER,
                              "criteria": [criterion("f", "f.txt says v1")]}, assignee="s-exec-1")
    e.wait_idle()
    assert T.signal(e, "root", "ACCEPT", "s-exec-1")["accepted"]
    hand = _commit(repo, "hand.txt")
    got = _past(e)
    assert (got["commits"], got["in_work"]) == ([hand], []), got


def test_a_fold_of_a_branch_made_before_the_project_is_no_work_past_the_system(repo):
    """Commits that stood before the project carry content by every path's result as the system's work does: a fold of
    a pre-project branch changes no patch any of them had. CONTROL: only the patch tested against them — the fold
    counts."""
    _git(repo, "switch", "-q", "-c", "old")
    _commit(repo, "o1.txt", when=OLD)
    _commit(repo, "o2.txt", "two\n", when=OLD)
    e = _in_chat(repo, take=False)
    _git(repo, "reset", "-q", "--soft", "main")
    _git(repo, "commit", "-q", "-m", "folded")
    got = _past(e)
    assert got["count"] == 0, got


def test_work_made_under_a_closed_obligation_carries_its_copy(repo):
    """What was made while a node was taken is the obligation's, delivered or not; once the node is no longer taken, a
    copy of it (a cherry-pick, an amend, a fold) is still that content, by patch or every path's result. CONTROL: the
    commits made under a span not read as carriers — the copy counts."""
    e = _in_chat(repo)
    w = _commit(repo, "f.txt", "v1\n")
    _git(repo, "reset", "-q", "--hard", "HEAD~1")              # …set aside, not delivered
    time.sleep(1.1)                                            # …the reflog's clock is whole seconds
    _deliver(e)
    _git(repo, "cherry-pick", w)
    got = _past(e)
    assert got["count"] == 0, got


def test_a_commit_made_in_a_linked_worktree_is_made_by_hand(repo, tmp_path):
    """HEAD is each worktree's own: a commit made on a linked worktree's HEAD is logged only in that worktree's HEAD
    reflog, and a fast-forward brings it to the main line made nowhere the main HEAD's reflog says. CONTROL: the
    reflogs of the main HEAD and the branches alone — the commit is made by no hand."""
    e = _in_chat(repo, take=False)
    _git(repo, "worktree", "add", "-q", "--detach", str(wt := tmp_path / "wt"))
    hand = _commit(wt, "hand.txt")
    _git(repo, "merge", "-q", "--ff-only", hand)
    got = _past(e)
    assert (got["count"], got["commits"]) == (1, [hand]), got


def test_a_ref_written_under_the_systems_names_holds_nothing_its_log_did_not_record(repo):
    """Any process can write a ref under `refs/gfso/`: what the system made is what its log recorded — its deliveries'
    commits, its landings' —, and a ref's commits only where they are reached through such a commit. CONTROL: the
    system's refs read by their names — a copy of the hand commit under one hides it."""
    e = _in_chat(repo)
    _deliver(e)
    a = _commit(repo, "hand.txt")
    _git(repo, "update-ref", "refs/gfso/p/anything", _git(repo, "commit-tree", f"{a}^{{tree}}", "-p", f"{a}^", "-m", "copy"))
    got = _past(e)
    assert (got["count"], got["commits"]) == (1, [a]), got


def test_a_read_again_asks_git_one_rev_parse(repo, monkeypatch):
    """A page polls the measures. CONTROL: the cache's key compared to nothing — `_measured` runs every read."""
    e = _in_chat(repo)
    _commit(repo, "f.txt")
    ran, measured = [], P._measured
    monkeypatch.setattr(P, "_measured", lambda *a: ran.append(a) or measured(*a))
    _past(e), _past(e)
    assert len(ran) == 1
    _commit(repo, "g.txt")
    _past(e)
    assert len(ran) == 2
