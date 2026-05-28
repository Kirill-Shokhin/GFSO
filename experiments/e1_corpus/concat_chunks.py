#!/usr/bin/env python
"""Concatenate chunked corpus files into a single per-company file.

Renumbers `## Incident N:` headings sequentially across chunks.
Merges file headers, drops duplicate "Skipped" sections (concatenates them).

Usage:
  python tools/concat_chunks.py <company>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PM = ROOT / "data" / "postmortems"


def parse_parts(company: str) -> tuple[list[str], list[str], list[str]]:
    """Return (header_lines, incident_blocks_combined, skipped_blocks_combined)."""
    parts = sorted(PM.glob(f"{company}.part*.md"))
    if not parts:
        raise SystemExit(f"no chunks for {company}")
    header_lines: list[str] = []
    incident_blocks: list[str] = []
    skipped_lines: list[str] = []
    inc_re = re.compile(r"^## Incident \d+:")
    for i, p in enumerate(parts):
        text = p.read_text(encoding="utf-8")
        # Split into header, sections
        lines = text.splitlines()
        cursor = 0
        # Detect header lines (everything before first ## Incident or ## Skipped)
        if i == 0:
            while cursor < len(lines) and not (lines[cursor].startswith("## Incident") or lines[cursor].startswith("## Skipped")):
                header_lines.append(lines[cursor])
                cursor += 1
        else:
            while cursor < len(lines) and not (lines[cursor].startswith("## Incident") or lines[cursor].startswith("## Skipped")):
                cursor += 1
        # Walk sections
        current: list[str] = []
        in_skipped = False
        while cursor < len(lines):
            line = lines[cursor]
            if inc_re.match(line):
                if current and not in_skipped:
                    incident_blocks.append("\n".join(current).rstrip())
                current = [line]
                in_skipped = False
            elif line.startswith("## Skipped"):
                if current and not in_skipped:
                    incident_blocks.append("\n".join(current).rstrip())
                current = []
                in_skipped = True
                skipped_lines.append(f"\n<!-- from {p.name} -->")
            else:
                if in_skipped:
                    skipped_lines.append(line)
                else:
                    current.append(line)
            cursor += 1
        if current and not in_skipped:
            incident_blocks.append("\n".join(current).rstrip())
    return header_lines, incident_blocks, skipped_lines


def renumber(blocks: list[str]) -> list[str]:
    out = []
    for i, b in enumerate(blocks, start=1):
        # Replace first "## Incident N: ..." with "## Incident i: ..."
        new = re.sub(r"^## Incident \d+:", f"## Incident {i}:", b, count=1, flags=re.MULTILINE)
        out.append(new)
    return out


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python tools/concat_chunks.py <company>")
    company = sys.argv[1]
    header, blocks, skipped = parse_parts(company)
    blocks = renumber(blocks)

    out_path = PM / f"{company}.md"
    out = "\n".join(header).rstrip() + "\n\n---\n\n"
    out += "\n\n---\n\n".join(blocks)
    out += "\n\n---\n\n## Skipped\n"
    out += "\n".join(skipped)
    out_path.write_text(out, encoding="utf-8")
    print(f"WROTE {out_path}: {len(blocks)} incidents, {sum(1 for l in skipped if l.strip().startswith('-'))} skipped entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
