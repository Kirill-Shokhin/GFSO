#!/usr/bin/env python
"""Process manually-downloaded HTML files into raw verbatim text dumps.

For sources blocked by robots/bot-detection that an agent or requests can't fetch,
the user saves the page from a browser (Ctrl+S, "HTML Only") into data/manual_html/
using the naming convention:

    <company>__<slug>.html

This script extracts each into data/raw_html/<company>/<slug>.md via trafilatura,
exactly like walk_archive.py does, so the writeup agents can consume it identically.

Usage:
  python tools/process_manual_html.py            # process all *.html in manual_html/
  python tools/process_manual_html.py <file>     # process one file
"""
from __future__ import annotations

import sys
from pathlib import Path

import trafilatura

ROOT = Path(__file__).resolve().parent.parent.parent
MANUAL = ROOT / "data" / "manual_html"
RAW = ROOT / "data" / "raw_html"


def process_file(html_path: Path) -> tuple[str, int]:
    name = html_path.stem  # <company>__<slug>
    if "__" not in name:
        print(f"  SKIP {html_path.name}: name must be <company>__<slug>.html", file=sys.stderr)
        return ("", 0)
    company, slug = name.split("__", 1)
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    text = trafilatura.extract(
        html,
        include_links=True,
        include_tables=True,
        include_formatting=True,
        output_format="markdown",
    )
    if not text or not text.strip():
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        main = soup.find("article") or soup.find("main") or soup.body or soup
        text = main.get_text("\n", strip=True)
    n = len(text or "")
    outdir = RAW / company
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{slug}.md"
    header = f"# Source: (manual download) {company}/{slug}\n# Length: {n} chars\n\n"
    out.write_text(header + (text or ""), encoding="utf-8")
    return (str(out), n)


def main() -> int:
    if len(sys.argv) == 2:
        files = [Path(sys.argv[1])]
    else:
        files = sorted(MANUAL.glob("*.html")) + sorted(MANUAL.glob("*.htm"))
    if not files:
        print(f"No HTML files in {MANUAL}. Save pages as <company>__<slug>.html there.")
        return 0
    for f in files:
        out, n = process_file(f)
        if out:
            status = "OK" if n > 500 else "THIN"
            print(f"  [{status}] {f.name} -> {out} ({n} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
