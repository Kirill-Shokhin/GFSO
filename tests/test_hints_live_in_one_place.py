"""Every explanation the page gives is written in one module, `gfso/web/js/hints.js`.

The author, 2026-10-27: the hints and popovers must lie «в одном каком-то внятном кодовом месте … чтобы не было потеряно
что мол какие-то из типов подсказок захардкожены где-то в другом месте» — so that working on them, and above all
analysing them, starts and ends in one file. A hover, a tip card, a popover row written anywhere else is that loss.
"""
import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "gfso" / "web"
HINTS = WEB / "js" / "hints.js"

# what writes an explanation: a browser `title` (attribute or property), a `data-tip` written as markup or set on an
# element from a literal, and the markup of a tip card or a popover
WRITES = [
    (re.compile(r"""\btitle\s*=\s*["'`$]"""), "a title attribute"),
    (re.compile(r"""[{,]\s*title\s*:"""), "a title property"),
    (re.compile(r"""\.title\s*=[^=]"""), "a title set on an element"),
    (re.compile(r"""data-tip\s*="""), "a data-tip written as markup"),
    (re.compile(r"""dataset\.tip\s*=\s*["'`]"""), "a data-tip set from a literal"),
    (re.compile(r"""class=["'][^"']*\b(tt-name|tt-row|hq-row|hq-head|hq-means|hd-pop|hp-top|hp-group)\b"""), "a tip card or popover's markup"),
]


def _sources():
    return [p for p in sorted((WEB / "js").glob("*.js")) if p != HINTS] + [WEB / "index.html"]


@pytest.mark.parametrize("path", _sources(), ids=lambda p: p.name)
def test_no_explanation_is_written_outside_the_hints_module(path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".html":
        text = re.sub(r"<title>.*?</title>", "", text, flags=re.S)
    found = [f"{path.name}:{text[:m.start()].count(chr(10)) + 1}: {what} — {m.group(0)!r}"
             for rx, what in WRITES for m in rx.finditer(text)]
    assert not found, "written outside gfso/web/js/hints.js:\n" + "\n".join(found)


def test_every_hint_the_document_names_is_written_in_the_module():
    names = set(re.findall(r'data-hint="(\w+)"', (WEB / "index.html").read_text(encoding="utf-8")))
    frame = re.search(r"const FRAME = \{(.*?)\n\};", HINTS.read_text(encoding="utf-8"), re.S).group(1)
    written = set(re.findall(r"^\s+(\w+):", frame, re.M))
    assert names and names <= written, f"index.html names hints the module does not write: {sorted(names - written)}"


def test_the_guard_reads_each_form_it_forbids():
    """The patterns are red on each form they name: a guard that matches nothing guards nothing."""
    planted = ['<b title="x">', "el('i', {title: 'x'})", "b.title = 'x';", '<i data-tip="x">', "b.dataset.tip = 'x';",
               '<div class="tt-row">x</div>']
    for text, (rx, what) in zip(planted, WRITES):
        assert rx.search(text), f"the pattern for {what} misses {text!r}"
    assert WRITES[-1][0].search('<div class="hd-pop">')
    assert not any(rx.search("tip(card(name, rows), e); const t = e.target.closest('[data-tip]');") for rx, _ in WRITES)
