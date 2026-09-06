"""Drive the UI like a person and report what it does — the door no wave has ever come in by.

Twenty-six waves of strangers have driven the CLI, the HTTP API and the MCP surface. Nobody has
driven the PAGE: it was checked by asserting on response bodies, and the first time anyone rendered
it (2026-09-02) five defects fell out of two looks, and the first click-through (2026-09-06) found
six more — two of them fatal to the flow they were in (a decomposition modal that accepted a plan
with no mapping at all, and criteria fields drawn cream-on-cream, i.e. invisible).

So this is the instrument for that surface: it opens the page against a running server, walks every
node's panel, opens every modal, and reports what the page SAYS — plus every console error, which is
where a broken page confesses first. It is a reporter, not a judge: it prints what it saw and the
reader decides. Run it with the server up:

    python scripts/look_at_the_page.py --project <name> [--out shots/]

`--interact` additionally exercises the forms that change nothing by themselves (opening modals,
reading their fields); it never sends a signal, so it is safe against a live graph.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE = "http://127.0.0.1:8000"


def _look(page, project: str, out: Path, interact: bool) -> dict:
    found: dict = {"console": [], "panels": {}, "modals": {}, "notes": []}
    page.on("console", lambda m: found["console"].append(f"{m.type}: {m.text}")
            if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: found["console"].append(f"pageerror: {e}"))

    page.goto(f"{BASE}/?project={project}", wait_until="networkidle")
    page.wait_for_timeout(1200)
    found["header"] = page.inner_text("#stats-bar")
    found["metrics"] = page.inner_text("#metrics")
    found["nodes"] = page.evaluate(
        "cy.nodes().map(n => ({id: n.id(), label: n.data('label'), state: n.data('state'),"
        " border: n.data('bs') + '/' + n.data('bw')}))")
    if out:
        page.screenshot(path=str(out / "page.png"))

    # EVERY node's panel, through the link the page itself accepts (`?task=`) — the detail surface
    # was unreachable to anything without a mouse until that existed.
    for n in found["nodes"]:
        page.goto(f"{BASE}/?project={project}&task={n['id']}", wait_until="networkidle")
        page.wait_for_timeout(700)
        if not page.is_visible("#sidebar"):
            found["notes"].append(f"{n['id']}: the panel did not open from its own link")
            continue
        found["panels"][n["id"]] = page.inner_text("#sidebar")[:1500]

    if interact:
        page.goto(f"{BASE}/?project={project}", wait_until="networkidle")
        page.wait_for_timeout(700)
        # …the modals, read rather than submitted: what a person can SEE is the half that broke.
        for label, opener, sel in (("decompose", "openDecompose", "#decompose-modal"),
                                   ("edit", "openEdit", "#edit-modal")):
            target = next((n["id"] for n in found["nodes"] if n["state"] in ("OFFERED", "EXECUTING")),
                          None)
            if target is None:
                found["notes"].append(f"{label}: no node in a state that offers it")
                continue
            page.evaluate(f"id => {opener}(id)", target)
            page.wait_for_timeout(600)
            if not page.is_visible(sel):
                found["notes"].append(f"{label}: the modal did not open for {target}")
                continue
            found["modals"][label] = {
                "on": target,
                "text": page.inner_text(sel)[:800],
                # CREAM ON CREAM IS INVISIBLE, and every criteria field in the edit modal was drawn
                # that way (wave 26). A colour a person cannot read is not a field they can fill.
                "field_colours": page.evaluate(
                    f"""Array.from(document.querySelectorAll('{sel} input')).slice(0, 8).map(i => {{
                        const cs = getComputedStyle(i);
                        return {{colour: cs.color, background: cs.backgroundColor,
                                 placeholder: i.placeholder || ''}};
                    }})"""),
            }
            page.evaluate(f"document.querySelector('{sel}').classList.remove('active')")
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default="default")
    ap.add_argument("--out", default="", help="directory for screenshots")
    ap.add_argument("--interact", action="store_true", help="also open the modals and read them")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed here — `pip install playwright && playwright install "
              "chromium`. This instrument is a dev dependency; the product needs none of it.",
              file=sys.stderr)
        return 2

    out = Path(args.out) if args.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 950})
        try:
            found = _look(page, args.project, out, args.interact)
        finally:
            browser.close()
    print(json.dumps(found, ensure_ascii=False, indent=1))
    # A console error is the page confessing; it is the one thing here that is not a judgement call.
    return 1 if any(c.startswith(("error", "pageerror")) for c in found["console"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
