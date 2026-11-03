"""A module of the page calling another's export it does not import throws only when that line runs: a whole facet went
blank with every other guard green. Modules of the page are checked as text, since no browser runs in the suite."""
import re
from pathlib import Path

JS = Path(__file__).resolve().parents[1] / "gfso" / "web" / "js"
EXPORT = re.compile(r"export (?:async )?(?:const|let|function|class)\s+(\w+)")
IMPORT = re.compile(r"import\s*\{([^}]*)\}\s*from")
DECLARED = re.compile(r"(?:const|let|var|function|class)\s+(\w+)")
BOUND = re.compile(r"[,{(\[]\s*(\w+)\s*(?=[,)}\]=]|=>)")          # a parameter or a destructured name


def strip_comments(s):
    return re.sub(r"(?m)^\s*//.*$|\s//\s.*$", "", s)


def unbound_calls(sources):
    exports = {name: f for f, s in sources.items() for name in EXPORT.findall(s)}
    found = []
    for f, s in sources.items():
        code = strip_comments(s)
        known = {x.strip().split(" as ")[-1].strip() for m in IMPORT.findall(s) for x in m.split(",")}
        known |= set(DECLARED.findall(code)) | set(BOUND.findall(code))
        for name, home in exports.items():
            if home != f and name not in known and re.search(rf"(?<![.\w'\"-]){name}\(", code):
                found.append(f"{f} calls {name} of {home}")
    return found


def page():
    return {p.name: p.read_text(encoding="utf-8") for p in JS.glob("*.js")}


def test_every_module_imports_what_it_calls():
    assert unbound_calls(page()) == []


def test_the_check_sees_an_import_dropped():
    sources = page()
    sources["panel.js"] = sources["panel.js"].replace(", enteredWord}", "}")
    assert "panel.js calls enteredWord of vocab.js" in unbound_calls(sources)
