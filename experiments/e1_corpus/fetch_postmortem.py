#!/usr/bin/env python
"""Fetch a postmortem URL and dump the article body as plain markdown text.

Usage:
    python tools/fetch_postmortem.py <URL> [--out PATH]

Writes the extracted article to stdout (or to PATH if --out given).
The output is suitable for agents to read with the Read tool and copy
verbatim text into postmortem corpus files.

Uses trafilatura for article-body extraction (boilerplate stripping).
Falls back to BeautifulSoup if trafilatura returns empty.
"""
from __future__ import annotations

import argparse
import sys
import urllib.parse
from pathlib import Path

import requests
import trafilatura
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


def fetch_html(url: str, timeout: float = 30.0) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    return r.text


def extract_with_trafilatura(html: str, url: str) -> str | None:
    return trafilatura.extract(
        html,
        url=url,
        include_links=True,
        include_tables=True,
        include_formatting=True,
        favor_precision=False,
        output_format="markdown",
    )


def extract_with_bs(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    main = soup.find("article") or soup.find("main") or soup.body or soup
    text = main.get_text("\n", strip=True)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    try:
        html = fetch_html(args.url)
    except Exception as e:
        print(f"FETCH_ERROR: {e}", file=sys.stderr)
        return 2

    text = extract_with_trafilatura(html, args.url) or ""
    if not text.strip():
        text = extract_with_bs(html)

    if not text.strip():
        print("EXTRACT_ERROR: no content extracted", file=sys.stderr)
        return 3

    header = f"# Source: {args.url}\n# Length: {len(text)} chars\n\n"
    out = header + text

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(out, encoding="utf-8")
        print(f"WROTE {args.out} ({len(out)} chars)")
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
