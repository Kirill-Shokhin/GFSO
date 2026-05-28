#!/usr/bin/env python
"""Build the structured GFSO postmortem corpus (v1.1.0) from ALL markdown files.

Parses every data/postmortems/*.md (excluding _-prefixed) into records matching
the corpus.json format, applies the v1.1.0 tags (entry_type, domain, methodology),
and writes corpus.json + _index.json. Verbatim quotes preserved character-identical.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PM = ROOT / "data" / "postmortems" / "sources"      # verbatim source .md files
OUT = ROOT / "data" / "postmortems"                 # corpus.json / index.json live above sources/
SCHEMA_VERSION = "1.1.0"
COMPILED = "2026-05-28"

# h3 heading (lowercased, normalized) -> record field
SECTION_MAP = {
    "timeline": "timeline_quote",
    "root cause": "root_cause_quotes",
    "contributing factors": "contributing_factors_quotes",
    "what we missed / detection gaps": "detection_gaps_quotes",
    "action items / what's next": "action_items_quotes",
    "notes": "collector_notes",
    # scrum_cases sections
    "situation before": "situation_before_quotes",
    "what was done": "what_was_done_quotes",
    "outcome": "outcome_quotes",
}

# Per-company provenance (source_type, is_primary_source). Mirrors existing corpus
# for the 30 originals; explicit choices for the 19 new + scrum_cases.
PROVENANCE = {
    "arpanet1980": ("rfc_or_standards_doc", False),
    "atlassian": ("engineering_blog", True),
    "aws": ("official_postmortem", True),
    "azure": ("official_postmortem", True),
    "browserstack": ("engineering_blog", True),
    "circleci": ("engineering_blog", True),
    "cloudflare": ("engineering_blog", True),
    "crowdstrike": ("engineering_blog", True),
    "datadog": ("engineering_blog", True),
    "discord": ("engineering_blog", True),
    "facebook_meta": ("engineering_blog", True),
    "gcp": ("official_postmortem", True),
    "github": ("engineering_blog", True),
    "gitlab": ("engineering_blog", True),
    "healthcare_gov": ("wikipedia", False),
    "heroku": ("official_postmortem", True),
    "honeycomb": ("engineering_blog", True),
    "incident_io": ("status_page", True),
    "indian_grid": ("wikipedia", False),
    "knight_capital": ("third_party_reconstruction", False),
    "linkedin": ("engineering_blog", True),
    "mozilla": ("engineering_blog", True),
    "northeast_blackout": ("wikipedia", False),
    "npm2014": ("official_postmortem", True),
    "roblox": ("engineering_blog", True),
    "slack": ("engineering_blog", True),
    "therac25": ("wikipedia", False),
    "twilio": ("engineering_blog", True),
    "wikimedia": ("engineering_blog", True),
    "wikimedia_wiki": ("engineering_blog", True),
    # new (A.8 / manual)
    "tsb_migration": ("wikipedia", False),
    "queensland_health": ("wikipedia", False),
    "universal_credit": ("wikipedia", False),
    "phoenix_pay": ("wikipedia", False),
    "boeing_737max": ("wikipedia", False),
    "ariane5": ("third_party_reconstruction", False),
    "mars_climate_orbiter": ("wikipedia", False),
    "london_ambulance": ("wikipedia", False),
    "denver_airport": ("wikipedia", False),
    "spotify": ("engineering_blog", True),
    "dropbox": ("engineering_blog", True),
    "gocardless": ("engineering_blog", True),
    "fastly": ("engineering_blog", True),
    "openai": ("engineering_blog", True),
    "netflix": ("engineering_blog", True),
    "okta": ("engineering_blog", True),
    "ovh": ("news_article", False),
    "buildkite": ("engineering_blog", True),
    "slack_dnssec": ("engineering_blog", True),
    "robinhood": ("engineering_blog", True),
    "nike_i2": ("wikipedia", False),
    "hertz_accenture": ("news_article", False),
    "scrum_cases": ("other", False),
}

# Domain tags (task mapping). Default ops_incident.
DOMAIN = {}
for c in ["tsb_migration", "queensland_health", "universal_credit", "phoenix_pay",
          "healthcare_gov", "knight_capital", "denver_airport", "nike_i2", "hertz_accenture"]:
    DOMAIN[c] = "project_delivery"
for c in ["therac25", "boeing_737max", "ariane5", "mars_climate_orbiter",
          "london_ambulance", "northeast_blackout", "indian_grid"]:
    DOMAIN[c] = "safety_critical"
for c in ["okta", "crowdstrike"]:
    DOMAIN[c] = "security_incident"
# process_narrative + scrum handled specially for scrum_cases


def split_records(text: str, heading_word: str):
    """Yield (n, title, body) for each '## <heading_word> N: title' section."""
    pat = re.compile(rf"^## {heading_word} (\d+): (.+)$", re.M)
    matches = list(pat.finditer(text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        yield int(m.group(1)), m.group(2).strip(), text[start:end]


def parse_frontmatter(body: str) -> dict:
    """Parse leading '- **Key**: value' lines until first blockquote/heading."""
    fm = {}
    for line in body.splitlines():
        s = line.rstrip()
        if s.startswith(">") or s.startswith("#") or s.startswith("### "):
            break
        m = re.match(r"^- \*\*([^*]+)\*\*:\s*(.*)$", s)
        if m:
            fm[m.group(1).strip().lower()] = m.group(2).strip()
    return fm


def extract_blockquotes(block_text: str) -> list[dict]:
    """Extract blockquote(s) from a section body as a list of Quote dicts.

    Splits into separate Quote objects on a '**Label:**' marker line (Datadog
    deep-dive note pattern). Within a quote, blank '>' lines become paragraph
    breaks (\n\n); code fences inside '> ```' are preserved verbatim.
    Trailing '> — Attribution' line on its own becomes the quote's attribution.
    """
    lines = block_text.splitlines()
    quotes: list[dict] = []
    active_note: str | None = None  # persists across quotes under the same marker
    cur: list[str] | None = None  # accumulated content lines for current quote

    def flush():
        nonlocal cur
        if cur is None:
            return
        # strip leading/trailing blank lines
        while cur and cur[0] == "":
            cur.pop(0)
        while cur and cur[-1] == "":
            cur.pop()
        if not cur:
            cur = None
            return
        attribution = None
        # attribution = trailing line that begins with em-dash (source-quoted attribution)
        if len(cur) >= 2 and cur[-1].startswith("—"):
            attribution = cur[-1].strip()
            cur.pop()
            while cur and cur[-1] == "":
                cur.pop()
        q = {"quote": "\n".join(cur)}
        if attribution:
            q["attribution"] = attribution
        if active_note:
            q["note"] = active_note
        quotes.append(q)
        cur = None

    for raw in lines:
        if raw.startswith("> "):
            content = raw[2:]
            if cur is None:
                cur = []
            cur.append(content)
        elif raw.rstrip() == ">":
            if cur is not None:
                cur.append("")  # paragraph break
        else:
            # a non-quote line: a label/note marker labels the following quote(s)
            stripped = raw.strip()
            mlabel = re.match(r"^\*\*(.+):\*\*$", stripped)
            if cur is not None:
                flush()
            if mlabel:
                active_note = mlabel.group(1).strip()
    flush()
    return quotes


def collapse_paragraphs(quote: str) -> str:
    """Collapse single '' paragraph markers to '\n\n' (we stored breaks as '')."""
    return quote


def clean_quote_text(lines_joined: str) -> str:
    """Turn the line list (joined by \n with '' for breaks) into final text:
    consecutive content lines join with space (prose wraps don't occur here since
    each blockquote line is one logical line); blank line -> paragraph break."""
    out_paras = []
    cur = []
    for ln in lines_joined.split("\n"):
        if ln == "":
            if cur:
                out_paras.append("\n".join(cur) if _has_code(cur) else " ".join(cur))
                cur = []
        else:
            cur.append(ln)
    if cur:
        out_paras.append("\n".join(cur) if _has_code(cur) else " ".join(cur))
    return "\n\n".join(out_paras)


def _has_code(lines: list[str]) -> bool:
    return any(ln.strip().startswith("```") or "```" in ln for ln in lines)


def build_quote(q: dict) -> dict:
    out = {"quote": clean_quote_text(q["quote"])}
    if "attribution" in q:
        out["attribution"] = q["attribution"]
    if "note" in q:
        out["note"] = q["note"]
    return out


def parse_date(raw: str):
    """Return clean date string or {start,end}, or None when no year is present.

    Strips parentheticals/approximation markers (~, approximate). Handles:
      '2018-04-20 (note)'           -> '2018-04-20'
      '2018-10-29 to 2019-03-10'    -> {start,end}
      '~2013'                       -> '2013'
      'approximate 2013-2014 (...)' -> {start:'2013',end:'2014'}
      'unknown (...)' / 'November 18 (year not stated)' -> None
    """
    raw = raw.strip()
    # explicit "X to Y" range
    rng = re.match(r"^[~\s]*(\d{4}(?:-\d{2})?(?:-\d{2})?)\s+to\s+(\d{4}(?:-\d{2})?(?:-\d{2})?)", raw)
    if rng:
        return {"start": rng.group(1), "end": rng.group(2)}
    # "YYYY-YYYY" or "YYYY–YYYY" range (en/em dash or hyphen between two 4-digit years)
    rng2 = re.search(r"(\d{4})\s*[–—-]\s*(\d{4})", raw)
    if rng2:
        return {"start": rng2.group(1), "end": rng2.group(2)}
    # leading clean date (optionally prefixed by ~ / approximate)
    m = re.match(r"^(?:~|approximate\s+|approximately\s+)?(\d{4}(?:-\d{2})?(?:-\d{2})?)", raw)
    if m:
        return m.group(1)
    # any 4-digit year anywhere (e.g. "~2013")
    m2 = re.search(r"(\d{4})", raw)
    if m2:
        return m2.group(1)
    return None


def parse_url(raw: str):
    """Return a single url string or a list of urls. Splits on '; ', strips
    a trailing '(primary)'/parenthetical marker from each entry."""
    raw = raw.strip()
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    cleaned = [re.sub(r"\s*\([^)]*\)\s*$", "", p).strip() for p in parts]
    if len(cleaned) <= 1:
        return cleaned[0] if cleaned else ""
    return cleaned


def parse_files(raw: str) -> list[str]:
    raw = raw.strip()
    return [p.strip() for p in raw.split(";") if p.strip()]


def split_sections(body: str):
    """Split a record body into front-matter region + {field: section_body}."""
    # find h3 headings
    pat = re.compile(r"^### (.+?)\s*$", re.M)
    matches = list(pat.finditer(body))
    fm_region = body[: matches[0].start()] if matches else body
    sections = {}
    for i, m in enumerate(matches):
        head = m.group(1)
        # normalize: lowercase, strip '(verbatim...)' parenthetical
        key = re.sub(r"\s*\(.*?\)\s*$", "", head).strip().lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        field = SECTION_MAP.get(key)
        if field:
            sections[field] = body[start:end]
    return fm_region, sections


def parse_impact(fm_region: str) -> list[dict]:
    """Impact quote(s) live right after the '- **Impact**...' line as blockquotes."""
    return [build_quote(q) for q in extract_blockquotes(fm_region)]


def build_record(company: str, n: int, title: str, body: str, is_scrum: bool) -> dict:
    fm_region, sections = split_sections(body)
    fm = parse_frontmatter(fm_region)

    rec = {
        "schema_version": SCHEMA_VERSION,
        "id": f"{company}-{n:03d}",
        "company": company,
        "title": title,
    }
    if is_scrum:
        rec["entry_type"] = "process_case"
        rec["domain"] = "process_narrative"
        rec["methodology"] = "scrum"
    else:
        rec["entry_type"] = "incident"
        rec["domain"] = DOMAIN.get(company, "ops_incident")
        rec["methodology"] = "unknown"

    if "date" in fm and fm["date"]:
        d = parse_date(fm["date"])
        if d:
            rec["date"] = d
    if "post date" in fm and re.match(r"^\d{4}", fm["post date"]):
        pd = parse_date(fm["post date"])
        if pd:
            rec["post_date"] = pd

    url = parse_url(fm.get("url", ""))
    if url:
        rec["url"] = url
    if "duration" in fm and fm["duration"]:
        rec["duration"] = fm["duration"]

    # impact
    impact = parse_impact(fm_region)
    if impact:
        rec["impact_quotes"] = impact

    # scrum-specific narrative fields kept under extensions to stay schema-clean
    scrum_extra = {}
    for field in ("timeline_quote", "root_cause_quotes", "contributing_factors_quotes",
                  "detection_gaps_quotes", "action_items_quotes",
                  "situation_before_quotes", "what_was_done_quotes", "outcome_quotes"):
        if field not in sections:
            continue
        quotes = [build_quote(q) for q in extract_blockquotes(sections[field])]
        if not quotes:
            continue
        if field == "timeline_quote":
            rec[field] = quotes[0] if len(quotes) == 1 else {
                "quote": "\n\n".join(q["quote"] for q in quotes)}
        elif field in ("situation_before_quotes", "what_was_done_quotes", "outcome_quotes"):
            scrum_extra[field] = quotes
        else:
            rec[field] = quotes

    # For multi-URL records, attach source_url to deep-dive quotes whose note
    # names a specific post (matched against the url slug).
    if isinstance(url, list) and len(url) > 1:
        def match_url(note: str):
            m = re.search(r"from ([\w\- ]+?) post", note or "")
            if not m:
                return None
            slug = m.group(1).strip().lower().replace(" ", "-")
            for u in url:
                if slug in u:
                    return u
            return None
        for field in ("timeline_quote", "root_cause_quotes",
                      "contributing_factors_quotes", "detection_gaps_quotes",
                      "action_items_quotes"):
            v = rec.get(field)
            if not v:
                continue
            qlist = [v] if field == "timeline_quote" else v
            for q in qlist:
                if "note" in q and "source_url" not in q:
                    su = match_url(q["note"])
                    if su:
                        q["source_url"] = su

    # collector notes (plain text, not blockquote)
    if "collector_notes" in sections:
        note = sections["collector_notes"].strip()
        # drop trailing '---' separators
        note = re.sub(r"\n*-{3,}\s*$", "", note).strip()
        if note and note != "[Omitted long context line]":
            rec["collector_notes"] = note

    # source provenance
    st, primary = PROVENANCE[company]
    urls_list = url if isinstance(url, list) else ([url] if url else [])
    src_files = parse_files(fm.get("source file", ""))
    if not src_files and urls_list:
        # derive a source filename from the URL path tail (matches corpus convention)
        tail = re.split(r"[/#?]", urls_list[0].rstrip("/"))[-1]
        if tail:
            src_files = [f"{tail}.md"]
    sp = {
        "urls": urls_list,
        "source_files": src_files,
        "fetched_at": COMPILED,
        "source_type": st,
        "is_primary_source": primary,
        "fetch_status": "ok",
    }
    if company == "arpanet1980":
        sp["extras"] = {"rfc_number": 789}
    rec["source_provenance"] = sp

    if scrum_extra:
        rec["extensions"] = scrum_extra
    rec["annotations"] = []
    return rec


def main():
    files = sorted(f for f in PM.glob("*.md") if not f.name.startswith("_"))
    records = []
    parse_report = []
    for f in files:
        company = f.stem
        text = f.read_text(encoding="utf-8")
        is_scrum = company == "scrum_cases"
        heading_word = "Case" if is_scrum else "Incident"
        recs = list(split_records(text, heading_word))
        # also support files that use 'Incident' even if scrum? no.
        for n, title, body in recs:
            rec = build_record(company, n, title, body, is_scrum)
            records.append(rec)
        parse_report.append((company, len(recs)))

    out = {
        "schema_version": SCHEMA_VERSION,
        "compiled": COMPILED,
        "phase": "A.finalize",
        "total_incidents": len(records),
        "incidents": records,
    }
    (OUT / "corpus.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # index
    by_entry = Counter(r["entry_type"] for r in records)
    by_domain = Counter(r["domain"] for r in records)
    by_company = Counter(r["company"] for r in records)
    by_method = Counter(r["methodology"] for r in records)
    # date range
    years = []
    for r in records:
        d = r.get("date")
        if isinstance(d, str):
            years.append(d[:4])
        elif isinstance(d, dict):
            years.append(d["start"][:4]); years.append(d["end"][:4])
    years = [y for y in years if y.isdigit()]
    index = {
        "schema_version": SCHEMA_VERSION,
        "compiled": COMPILED,
        "phase": "A.finalize",
        "total_incidents": len(records),
        "by_entry_type": dict(sorted(by_entry.items())),
        "by_domain": dict(sorted(by_domain.items())),
        "by_methodology": dict(sorted(by_method.items())),
        "by_company": dict(sorted(by_company.items())),
        "date_range": {"earliest": min(years), "latest": max(years)} if years else {},
    }
    (OUT / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("PARSE REPORT (company: sections):")
    for c, n in parse_report:
        print(f"  {c}: {n}")
    print(f"TOTAL records: {len(records)}")
    print("by_entry_type:", dict(by_entry))
    print("by_domain:", dict(by_domain))


if __name__ == "__main__":
    main()
