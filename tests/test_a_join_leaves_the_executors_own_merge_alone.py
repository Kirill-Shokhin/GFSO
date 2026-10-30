"""A part joining a place where the executor's own merge stands unfinished is refused by git — and the abort that undoes a
join's own conflict then undid the executor's merge: MERGE_HEAD gone, its resolutions put back to HEAD, between two
rounds and without any act of its own (GB_c_compiler_ctx3b1285, root.integrate, twice: 16:45 and 17:02).

CONTROL: let `W.merge` abort whatever merge stands and the test goes red."""
from __future__ import annotations

import subprocess

from gfso.adapters import worktrees as W
from tests.test_a_node_works_in_its_own_place import _git, _repo


def test_a_join_does_not_abort_the_merge_the_executor_left_unfinished(tmp_path):
    base = _repo(tmp_path / "ws")
    trunk = _git(base, "rev-parse", "--abbrev-ref", "HEAD")
    for name, path in (("a", "README"), ("b", "README"), ("c", "c.txt")):
        _git(base, "checkout", "-q", "-b", name, trunk)
        (base / path).write_text(f"{name}\n")
        _git(base, "add", "-A"), _git(base, "commit", "-q", "-m", name)
    _git(base, "checkout", "-q", trunk)
    _git(base, "merge", "-q", "--no-edit", "a")
    assert subprocess.run(["git", "merge", "--no-edit", "b"], cwd=base, capture_output=True).returncode  # its conflict
    (base / "README").write_text("resolved by the executor\n")                                            # …its work
    assert W.merge(base, base, "c", "gfso: root.c joins root")                  # a part to join: not joined, and said why
    assert W.merging(base, base) and (base / "README").read_text() == "resolved by the executor\n"


def test_the_packet_tells_the_agent_its_merge_stands_not_that_one_was_aborted():
    """Told "the merge was aborted", an agent whose own merge the join left alone would abort it itself."""
    from gfso.adapters import worktrees as W
    from gfso.workspaces import _unjoined_text
    said = _unjoined_text([("root.p", "gfso/root.p", W.MERGE_STANDS, "gfso/root.p")])
    assert "do NOT abort" in said and "was aborted" not in said
    assert "was aborted" in _unjoined_text([("root.p", "gfso/root.p", "CONFLICT (content)", "gfso/root.p")])
