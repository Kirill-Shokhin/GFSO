"""The user-agent protocol (`ORCHESTRATOR.md`), by client kind: each kind's instructions are the head of the file with
the lines marked for the other kind left out, served at `initialize`; the reference past `<!-- reference -->` is read
by section (`protocol(section)`). A client cuts instructions at 4096 characters, so a kind's text holds only what a
fresh agent of that kind needs before its first call."""
from __future__ import annotations

import re
from pathlib import Path

from gfso.config import CLIENT_KINDS

#: Read UNGUARDED: a swallowed OSError handed an agent an empty protocol on a wheel that lacked the file
#: (tests/test_packaging.py keeps it in the distribution).
TEXT = (Path(__file__).parent / "ORCHESTRATOR.md").read_text(encoding="utf-8")
_MARK = re.compile(r"<!-- (code|chat|both) -->\n?")
_HEAD, _REFERENCE = TEXT.split("<!-- reference -->\n")


def instructions(kind: str) -> str:
    """The instructions a client of `kind` is served: the head, its own lines and the shared ones."""
    parts, said, out = _MARK.split(_HEAD), "both", []
    for i, part in enumerate(parts):
        if i % 2:
            said = part
        elif said in ("both", kind):
            out.append(part)
    return "".join(out)


#: every kind's text, by kind — what the session at `initialize` recognises as this server's own
BY_KIND = {k: instructions(k) for k in CLIENT_KINDS}


def reference(section: str = "") -> dict:
    """The reference past the instructions: no `section`, its headings; else the section whose heading holds it."""
    sections = {m.group(1): m.group(0) for m in re.finditer(r"(?ms)^## (.+?)$.*?(?=^## |\Z)", _REFERENCE)}
    if not section:
        return {"sections": list(sections)}
    hit = [h for h in sections if str(section).lower() in h.lower()]
    return {"section": hit[0], "text": sections[hit[0]].strip()} if hit else {
        "error": f"no section of the protocol names {section!r}: {', '.join(sections)}", "refused": True}
