"""The canon — the theory GFSO is built on — as the user-agent reads it: a question "why is it done this way, and does it
hold?" is answered from the chapter it is about, not from guesses (a tester's agent found the theory only through a
link on the README's second screen, and had nowhere to look when asked whether the design made sense).

The text is the one of THIS version: the repository's own file where gfso runs from a checkout, otherwise the file at
this release's tag on GitHub, fetched once and kept in the state directory. No copy lives in the package."""
from __future__ import annotations

import re
import urllib.request
from typing import Callable, Optional

from gfso import __version__
from gfso.config import data_dir
from gfso.serverctl import ROOT

FILE = "docs/applied_gfso_v4_en.md"
URL = "https://raw.githubusercontent.com/Kirill-Shokhin/GFSO/v{version}/" + FILE
CAP = 60_000            # one answer's text; a chapter past it is read by its sections
_HEAD = re.compile(r"^(#{2,3}) (\d+(?:\.\d+)?)\. (.+)$", re.M)


def _fetch(version: str) -> str:
    with urllib.request.urlopen(URL.format(version=version), timeout=20) as r:
        return r.read().decode("utf-8")


def text(fetch: Callable[[str], str] = _fetch) -> Optional[str]:
    """The canon's text for this version, or None when it is neither here nor reachable."""
    if (local := ROOT / FILE).is_file():
        return local.read_text(encoding="utf-8")
    kept = data_dir() / f"canon-{__version__}.md"
    if kept.is_file():
        return kept.read_text(encoding="utf-8")
    try:
        got = fetch(__version__)
    except Exception:       # offline or no such tag: said by the caller, never guessed at
        return None
    try:
        kept.write_text(got, encoding="utf-8")
    except OSError:     # an unwritable home fetches again next time; the text is still this answer's
        return got
    return got


def read(section: str = "", fetch: Callable[[str], str] = _fetch) -> dict:
    """The reading map with every chapter and section heading, or the text of one (`12`, `12.4`, `§9.6`)."""
    body = text(fetch)
    if body is None:
        return {"error": f"the canon is not on this machine and {URL.format(version=__version__)} did not answer"}
    heads = [(m.start(), m.group(2), m.group(3)) for m in _HEAD.finditer(body)]
    want = str(section or "").strip().lstrip("§").rstrip(".")
    if not want:
        intro = body[body.find("## Introduction"):body.find("\n## 0.")]
        return {"source": URL.format(version=__version__), "introduction": intro[:CAP],
                "sections": [f"{n}. {t}" for _, n, t in heads],
                "how": "canon(section='12') for a chapter, canon(section='12.4') for one section"}
    at = next((i for i, (_, n, _t) in enumerate(heads) if n == want), None)
    if at is None:
        return {"error": f"no section {want!r}; the headings are in canon() with no section"}
    level = "." in want
    end = next((s for s, n, _t in heads[at + 1:] if level or "." not in n), len(body))
    out = body[heads[at][0]:end]
    return {"section": want, "text": out[:CAP], **({"cut": f"past {CAP} characters — read it by its sections"}
                                                     if len(out) > CAP else {})}
