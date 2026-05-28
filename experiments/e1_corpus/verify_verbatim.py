#!/usr/bin/env python
"""Verify that blockquote text in postmortem corpus files appears verbatim in raw sources.

Methodology:
1. For each corpus file in data/postmortems/<company>.md
2. Parse out blockquote lines (lines starting with `> `)
3. Pool the raw text from data/raw_html/<company>/ (and aliases like wikimedia_wiki)
4. For each blockquote, sample one substantial sentence (10+ words) and string-search in raw
5. Report per-corpus-file: total quotes checked, hits, misses, hit-rate

Loose matching: collapse whitespace, lowercase, remove punctuation. We're checking
intent (did the writer copy-paste vs invent), not byte-identity.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent.parent
PM = ROOT / "data" / "postmortems" / "sources"
RAW = ROOT / "data" / "postmortems" / "raw"

# Map corpus file -> raw_html dir(s). Most are 1:1.
COMPANY_TO_RAW = {
    "aws": ["aws"],
    "arpanet1980": ["arpanet1980"],
    "atlassian": ["atlassian"],
    "azure": ["azure"],
    "browserstack": ["browserstack"],
    "circleci": ["circleci"],
    "cloudflare": ["cloudflare"],
    "crowdstrike": ["crowdstrike"],
    "datadog": ["datadog"],
    "discord": ["discord"],
    "facebook_meta": ["facebook_meta"],
    "gcp": ["gcp"],
    "github": ["github"],
    "gitlab": ["gitlab"],
    "healthcare_gov": ["healthcare_gov"],
    "heroku": ["heroku"],
    "honeycomb": ["honeycomb"],
    "incident_io": ["incident_io"],
    "indian_grid": ["indian_grid"],
    "knight_capital": ["knight_capital"],
    "linkedin": ["linkedin"],
    "mozilla": ["mozilla_addons"],
    "northeast_blackout": ["northeast_blackout"],
    "npm2014": ["npm2014"],
    "roblox": ["roblox"],
    "slack": ["slack"],
    "therac25": ["therac25"],
    "twilio": ["twilio"],
    "wikimedia": ["wikimedia"],
    "wikimedia_wiki": ["wikimedia_wiki"],
    # A.8 additions
    "tsb_migration": ["tsb_migration"],
    "queensland_health": ["queensland_health"],
    "universal_credit": ["universal_credit"],
    "phoenix_pay": ["phoenix_pay"],
    "boeing_737max": ["boeing_737max"],
    "ariane5": ["ariane5"],
    "mars_climate_orbiter": ["mars_climate_orbiter"],
    "london_ambulance": ["london_ambulance"],
    "denver_airport": ["denver_airport"],
    "spotify": ["spotify"],
    "dropbox": ["dropbox"],
    "gocardless": ["gocardless"],
    "fastly": ["fastly"],
    # manual-download additions
    "openai": ["openai"],
    "netflix": ["netflix"],
    "okta": ["okta"],
    "ovh": ["ovh"],
    "buildkite": ["buildkite"],
    "slack_dnssec": ["slack"],
}

# Scrum book cases verify against the book text file, and use `## Case` headings.
SCRUM_CASES_FILE = "scrum_cases"
SCRUM_BOOK_RAW = ROOT / "data" / "postmortems" / "manual" / "_scrum_book_full.txt"


def normalize(s: str) -> str:
    s = s.lower()
    # strip markdown links [text](url) -> text  (Wikipedia/trafilatura decoration)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    # strip bare citation markers [12], [[30]]
    s = re.sub(r"\[+\d+\]+", "", s)
    # strip markdown emphasis asterisks/underscores
    s = re.sub(r"[*_]", "", s)
    # de-hyphenate PDF line-break splits: "про- ходила" -> "проходила"
    s = re.sub(r"-\s+", "", s)
    # unify all dash variants (em/en/hyphen) to nothing so "bina–gwalior" == "binagwalior"
    s = re.sub(r"[‐-―\-]", "", s)
    # collapse whitespace
    s = re.sub(r"\s+", " ", s)
    # remove remaining punctuation
    s = re.sub(r"[^\w\s]", "", s)
    return s.strip()


def extract_blockquotes(text: str) -> list[str]:
    """Return contiguous blockquote blocks as concatenated strings."""
    blocks = []
    current = []
    for line in text.splitlines():
        if line.startswith("> "):
            current.append(line[2:].rstrip())
        elif line.strip() == ">":
            if current:
                current.append("")  # paragraph break within blockquote
        else:
            if current:
                blocks.append(" ".join(l for l in current if l.strip()))
                current = []
    if current:
        blocks.append(" ".join(l for l in current if l.strip()))
    return [b for b in blocks if b.strip()]


def pick_test_phrase(block: str, min_words: int = 8, max_words: int = 18) -> str | None:
    """Pick a substantive sentence/clause from a blockquote for verification."""
    # Split on sentence-ish boundaries
    sentences = re.split(r"(?<=[.!?])\s+", block)
    # Prefer the longest sentence with ≥ min_words
    candidates = [s for s in sentences if len(s.split()) >= min_words]
    if not candidates:
        return None
    # Pick the longest under max_words; if all too long, truncate the first viable
    candidates.sort(key=lambda s: abs(len(s.split()) - (min_words + max_words) // 2))
    chosen = candidates[0]
    words = chosen.split()
    if len(words) > max_words:
        chosen = " ".join(words[:max_words])
    return chosen


def load_raw_pool(company: str) -> str:
    dirs = COMPANY_TO_RAW.get(company, [company])
    pool = []
    for d in dirs:
        rd = RAW / d
        if not rd.exists():
            continue
        for f in rd.glob("*.md"):
            if f.name.startswith("_"):
                continue
            try:
                pool.append(f.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue
    return normalize("\n".join(pool))


def verify_company(company: str) -> dict:
    corpus = PM / f"{company}.md"
    if not corpus.exists():
        return {"company": company, "error": "corpus not found"}
    text = corpus.read_text(encoding="utf-8")
    blocks = extract_blockquotes(text)
    if company == SCRUM_CASES_FILE:
        raw_pool = normalize(SCRUM_BOOK_RAW.read_text(encoding="utf-8", errors="ignore")) if SCRUM_BOOK_RAW.exists() else ""
    else:
        raw_pool = load_raw_pool(company)
    if not raw_pool:
        return {"company": company, "error": "raw pool empty", "blocks": len(blocks)}
    hits = 0
    misses = 0
    skipped = 0
    miss_examples = []
    for b in blocks:
        phrase = pick_test_phrase(b)
        if not phrase:
            skipped += 1
            continue
        norm = normalize(phrase)
        if norm in raw_pool:
            hits += 1
        else:
            misses += 1
            if len(miss_examples) < 3:
                miss_examples.append(phrase[:120])
    total = hits + misses
    return {
        "company": company,
        "blocks": len(blocks),
        "checked": total,
        "skipped_short": skipped,
        "hits": hits,
        "misses": misses,
        "hit_rate": (hits / total * 100) if total else 0,
        "miss_examples": miss_examples,
    }


def main() -> int:
    results = []
    companies = sorted(COMPANY_TO_RAW) + [SCRUM_CASES_FILE]
    for company in companies:
        r = verify_company(company)
        results.append(r)
    print(f"{'Company':<22} {'Blocks':>6} {'Checked':>7} {'Hits':>5} {'Miss':>5} {'Hit%':>6}")
    print("-" * 60)
    total_hits = total_misses = 0
    for r in results:
        if "error" in r:
            print(f"{r['company']:<22} ERROR: {r['error']}")
            continue
        print(
            f"{r['company']:<22} {r['blocks']:>6} {r['checked']:>7} "
            f"{r['hits']:>5} {r['misses']:>5} {r['hit_rate']:>5.1f}%"
        )
        total_hits += r["hits"]
        total_misses += r["misses"]
        if r["misses"] and r["miss_examples"]:
            for ex in r["miss_examples"]:
                print(f"  miss: {ex}")
    total = total_hits + total_misses
    overall = (total_hits / total * 100) if total else 0
    print("-" * 60)
    print(f"{'OVERALL':<22} {'':>6} {total:>7} {total_hits:>5} {total_misses:>5} {overall:>5.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
