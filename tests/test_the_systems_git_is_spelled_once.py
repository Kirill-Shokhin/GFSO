"""The system's git is spelled once (`gfso.adapters.git`): every git it runs on this host is built by the one runner, and
every script that runs git elsewhere renders the flags that keep a repository's own config, hooks and fsmonitor from
running. A copy spelled by hand drifted — `core.fsmonitor=false` in one script, absent beside it — and a copy that comes
back is red here, as is a script whose git runs under less than the whole set."""
import ast
import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest

from gfso.adapters import execution as E, git as G, worktrees as W

GFSO = Path(__file__).resolve().parents[1] / "gfso"
ADAPTER = GFSO / "adapters" / "git.py"
#: the words that keep a repository's config from running code, and the profile's environment: the adapter's alone
FLAGS = re.compile(r"core\.fsmonitor=|core\.hooksPath=|safe\.directory=|fsckObjects=|GIT_CONFIG_NOSYSTEM|GIT_CONFIG_GLOBAL"
                   r"|GIT_NO_REPLACE_OBJECTS|GIT_NO_LAZY_FETCH")
#: a git call in a shell script: its assignments, then its `-c` flags
CALL = re.compile(r"((?:[A-Z_]+=\S+ )*)(?<![\w./$-])git((?: +-c +(?:'[^']*'|\S+))*)")
#: the scripts the system runs git by inside a container, by the shell
SCRIPTS = {"_EXPORT": E._EXPORT, "_READ_AGAIN": E._READ_AGAIN, "_IMPORT": E._IMPORT}
#: (module, why) of a git command built outside the runner
OUTSIDE = {"adapters/lfs.py": "the LFS filter, a program git itself runs: its git inherits that git's `-c` flags and "
                              "environment, and it carries no import of the product"}


def _gfso():
    return [p for p in GFSO.rglob("*.py") if p != ADAPTER]


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_every_git_a_script_runs_holds_the_whole_set(name):
    calls = CALL.findall(SCRIPTS[name].replace("\\\n", " "))
    assert calls, name
    for assigned, flags in calls:
        said = dict(a.split("=", 1) for a in assigned.split())
        given = shlex.split(flags)[1::2]
        assert said.items() >= {**G.NO_CONFIG, **G.EVERY}.items(), (name, assigned, flags)
        assert set(given) >= set(G.APART[1::2]), (name, assigned, flags)


def test_no_flag_of_the_set_is_spelled_outside_the_adapter():
    spelled = [f"{p.relative_to(GFSO).as_posix()}:{n}" for p in _gfso()
               for n, line in enumerate(p.read_text(encoding="utf-8-sig").splitlines(), 1) if FLAGS.search(line)]
    assert not spelled, spelled


def test_no_git_command_is_built_outside_the_runner():
    built = [f"{rel}:{n.lineno}" for p in _gfso() if (rel := p.relative_to(GFSO).as_posix()) not in OUTSIDE
             for n in ast.walk(ast.parse(p.read_text(encoding="utf-8-sig")))
             if isinstance(n, (ast.List, ast.Tuple)) and n.elts and isinstance(n.elts[0], ast.Constant)
             and n.elts[0].value == "git"]
    assert not built, built


def test_the_guards_are_red_on_a_copy(tmp_path):
    """CONTROL: a script line missing one flag, a hand-spelled flag, a hand-built command — each found."""
    bare = "GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null git -c core.hooksPath=/dev/null -C x bundle create"
    (assigned, flags), = CALL.findall(bare)
    assert not set(shlex.split(flags)[1::2]) >= set(G.APART[1::2])
    assert FLAGS.search('run(["git", "-c", "core.fsmonitor=false"])')
    tree = ast.parse('children.run(["git", "status"])')
    assert any(isinstance(n, ast.List) and n.elts[0].value == "git" for n in ast.walk(tree))



def _repo(at: Path) -> Path:
    at.mkdir()
    for a in (["init", "-q", "-b", "main"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty",
                                          "-m", "x"]):
        subprocess.run(["git", *a], cwd=at, check=True, capture_output=True)
    return at


def test_a_result_branch_checked_out_is_refused_at_the_move_itself(tmp_path):
    """Every landing moves its result by `move_result`, which refuses a branch checked out in any worktree there: the
    check asked beside each caller drifted (`land`, `_name_the_delivery`)."""
    base = _repo(tmp_path / "base")
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=base, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "worktree", "add", "-q", "-b", "gfso/p/accepted", str(tmp_path / "wt")], cwd=base, check=True,
                   capture_output=True)
    with pytest.raises(OSError, match="is checked out there"):
        W.move_result(base, "refs/heads/gfso/p/accepted", sha)
    assert W.move_result(base, "refs/heads/gfso/p/other", sha) is None


def _link(to: Path, at: Path) -> None:
    if os.name == "nt":
        __import__("_winapi").CreateJunction(str(to), str(at))
    else:
        at.symlink_to(to, target_is_directory=True)


def test_a_repository_reached_through_a_link_is_its_top_by_either_question(tmp_path):
    """git names the top by its target: asked through a junction (a symlink off Windows), the text of the two read as
    two directories and the user's repository was refused as no top. Both askers, one rule (`G.is_top`)."""
    _link(_repo(tmp_path / "real"), via := tmp_path / "via")
    W._TOPS.clear()
    assert W.is_repo_top(via) and E._no_places(via) is None
    assert not W.is_repo_top(tmp_path) and E._no_places(tmp_path)


def test_a_repository_another_account_owns_is_refused_with_its_cause(tmp_path, monkeypatch):
    """The person's own git refuses a repository another account owns: the refusal says so and leaves the trust to him —
    it told him to `git init` a repository that exists."""
    repo = tmp_path / "theirs"
    repo.mkdir()
    for a in (("init", "-q"), ("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "s")):
        subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)
    monkeypatch.setenv("GIT_TEST_ASSUME_DIFFERENT_OWNER", "1")
    why = E._no_places(repo)
    assert why and "another account owns" in why and "safe.directory" in why and "git init" not in why, why
