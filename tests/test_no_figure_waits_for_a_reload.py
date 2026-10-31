"""A figure time moves is never frozen at its draw: what happened is said by its moment, and how long what runs now has
run is set again in place by the page's one display clock (dom.js `since`) — «13s ago» stood until a reload (the author,
2026-10-31: «обновление страницы никогда не должно требоваться вручную»)."""
import re
from pathlib import Path

JS = Path(__file__).resolve().parents[1] / "gfso" / "web" / "js"


def _offences(text):
    text = re.sub(r"(^|\s)//.*", "", text, flags=re.M)        # what a comment says is no figure on screen
    return [m.group(0) for m in re.finditer(r"\bago\b|dur\(\(?\s*(Date\.now\(\)|now)\s*[-/]", text)]


# dom.js owns the clock: `since` is the one place a duration is counted from now
def test_no_view_writes_an_age_or_a_duration_counted_at_its_draw():
    found = {f.name: hits for f in JS.glob("*.js") if f.name != "dom.js" and (hits := _offences(f.read_text(encoding="utf-8")))}
    assert not found, found


def test_the_guard_sees_both_forms():
    assert _offences("`${dur(Date.now() - t)}`") and _offences("${a} ago") and _offences("dur((now - w.since) * 1e3)")
