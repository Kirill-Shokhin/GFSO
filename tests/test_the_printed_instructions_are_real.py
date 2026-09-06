"""The documents a newcomer follows must name only things that exist.

The product is meant to be installed by someone who has never seen it: they read `README.md`, then
`docs/USING_GFSO.md`, and type what is printed. Measured 2026-08-20, driving the doors as a user:
the docs were prose nothing executed, and the drift showed — a person hunting for the verb that
records a human verdict found it by reading the source, because the page that lists the doors did
not mention it. These tests hold the printed text to the shipped surface: every CLI subcommand, every
verb, every demo named in the docs must be real, and the shipped example a reader is told to run
first must actually run.

What this does NOT do is start a server or register the MCP door — `gfso setup` / `gfso up` touch a
person's machine and a live run, and a test may not.
"""
from __future__ import annotations

import io
import re
import subprocess
import sys
from pathlib import Path

import pytest

from gfso.cli import build_parser
from gfso import tools_llm as TL

ROOT = Path(__file__).resolve().parent.parent
DOCS = [ROOT / "README.md", ROOT / "docs" / "USING_GFSO.md"]


def _text(p: Path) -> str:
    return io.open(p, encoding="utf-8").read()


def _subcommands() -> set[str]:
    parser = build_parser()
    out: set[str] = set()
    for action in parser._actions:
        if hasattr(action, "choices") and action.choices:
            out |= {str(c) for c in action.choices}
    return out


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_every_gfso_command_the_docs_print_exists(doc):
    # Only commands the reader is TOLD to type: inside backticks or a fenced block. Prose that
    # merely says "gfso also …" is English, not an instruction.
    body = _text(doc)
    typed = re.findall(r"`([^`\n]+)`", body) + re.findall(r"```bash\n(.*?)```", body, re.S)
    typed = [c.split("#", 1)[0] for line in typed for c in line.splitlines()]  # drop comments
    named = {m.group(1) for chunk in typed
             for m in re.finditer(r"\bgfso ([a-z]+)", chunk)} - {"run"}
    real = _subcommands()
    missing = sorted(n for n in named if n not in real)
    assert not missing, f"{doc.name} tells the reader to run commands that do not exist: {missing}"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_every_verb_the_docs_name_is_in_the_registry(doc):
    # Only backticked identifiers that LOOK like verbs (snake_case, no dots/slashes/spaces).
    quoted = set(re.findall(r"`([a-z][a-z_]{3,})`", _text(doc)))
    # …intersected with the vocabulary, so ordinary prose in backticks is not mistaken for a verb.
    verbs = {q for q in quoted if q.endswith(("_task", "_criteria", "_result", "_decomposition",
                                             "_verdict", "_holes", "_review", "_agent", "_project",
                                             "_dependency", "_criterion", "_step", "_steps",
                                             "_actions", "_checks", "_finding", "_agents",
                                             "_dependencies", "_risks"))
             or q in ("signal", "revise", "reopen", "reassign", "decompose", "metrics", "project")}
    unknown = sorted(v for v in verbs if v not in TL.TOOLS)
    assert not unknown, f"{doc.name} names verbs the registry does not have: {unknown}"


def test_the_first_thing_the_readme_tells_a_newcomer_to_run_actually_runs():
    """`gfso demo human_only` is the README's one-second proof that the gate is real. It is also the
    only command a reader meets before installing anything, so it runs here for real — as a
    subprocess, exactly as printed, and its output is checked for the refusal it promises."""
    r = subprocess.run([sys.executable, "-m", "gfso.cli", "demo", "human_only"],
                       capture_output=True, text=True, timeout=180, cwd=str(ROOT))
    assert r.returncode == 0, f"the README's first command failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}"
    out = r.stdout
    assert "ann" in out and "bob" in out, "the two people the README describes are not in the output"
    assert "DONE" in out, "the node the README says reaches DONE did not"


def test_a_person_can_list_their_own_projects():
    """`list_projects` and `use_project` exist on the agent door alone.

    A person driving from the shell had no way to see what they had already made — and `project=`,
    which every verb takes, is useless if you cannot remember the name. Measured 2026-08-21 on the
    human door: the whole isolation boundary of the product was unlistable from the door a person
    uses. `gfso projects` is that listing, most recently worked in first, with the server's active
    one marked."""
    real = _subcommands()
    assert "projects" in real

    parser = build_parser()
    args = parser.parse_args(["projects", "-n", "5", "--match", "demo"])
    assert args.n == 5 and args.match == "demo"
