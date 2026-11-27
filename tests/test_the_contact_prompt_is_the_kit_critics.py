"""The contact reading's prompt is the kit's outside critic's, near-verbatim: its body is the repository's pinned copy of
`kit-critic.md` with «the author» read as «the person» and «artifact» as «delivery», plus one fixed angle and the three
lines the system needs (design §B.1) — so «не хуже критика» is decided by the prompt and its inputs. The copy is
re-taken on purpose, never drifts: where the kit is installed, its file must still be the one pinned (round-2 finding 7).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import gfso

FIXTURE = Path(__file__).parent / "fixtures" / "kit_critic.md"
CONTACT = Path(gfso.__file__).parent / "mcp" / "prompts" / "contact.md"
INSTALLED = Path.home() / ".claude" / "agents" / "kit-critic.md"
ANGLE = ("Your angle: meaning and behaviour — whether the delivery answers what the goal asks, and what it does when "
         "it is run.")
LINES = ("For each find, say which criterion it contradicts, or that none writes it.",
         "Each find that can be shown: the command that shows it on the delivery and a line its output shows. A find no "
         "command shows — the delivery answers another goal — is reported as read, with what it rests on.",
         "A read of the source shows the source; what the program does is shown by running it.")


def _pinned() -> tuple[str, str]:
    """(the sha256 of the kit file it was taken from, the critic's body without its frontmatter)."""
    head, text = FIXTURE.read_text(encoding="utf-8").split("\n", 1)
    return head.removeprefix("sha256: ").strip(), text.split("---", 2)[2]


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_the_contact_prompt_is_the_pinned_critic_with_its_stated_changes():
    _, critic = _pinned()
    got = CONTACT.read_text(encoding="utf-8")
    for extra in (ANGLE, *LINES):
        assert _flat(extra) in _flat(got), extra
        got = _flat(got).replace(_flat(extra), "")
    assert _flat(got) == _flat(critic.replace("the author", "the person").replace("artifact", "delivery"))


@pytest.mark.skipif(not INSTALLED.exists(), reason="the kit is not installed on this machine (CI)")
def test_the_pinned_copy_is_the_installed_kit_critic():
    assert hashlib.sha256(INSTALLED.read_bytes()).hexdigest() == _pinned()[0], \
        "the kit's critic changed: take its copy again into tests/fixtures/kit_critic.md, on purpose"
