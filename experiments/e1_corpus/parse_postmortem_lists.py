#!/usr/bin/env python
"""Parse curated postmortem lists into a unified universe inventory.

Sources:
- danluu/post-mortems (primary, ~200 entries grouped by category)
- upgundecha/howtheysre (companies organized by SRE practice)
- hjacobs/kubernetes-failure-stories (k8s.af, Kubernetes-specific)

Output: data/postmortems/_universe.md with Tier A/B/C breakdown.
"""
from __future__ import annotations

import re
import sys
import urllib.parse
from collections import defaultdict
from pathlib import Path

import requests

UA = "Mozilla/5.0"
ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "postmortems" / "_universe.md"

SOURCES = {
    "danluu": "https://raw.githubusercontent.com/danluu/post-mortems/master/README.md",
    "howtheysre": "https://raw.githubusercontent.com/upgundecha/howtheysre/main/README.md",
    "k8s_af": "https://raw.githubusercontent.com/hjacobs/kubernetes-failure-stories/master/README.md",
}


def fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.text


ENTRY_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def parse_danluu(md: str) -> dict[str, list[tuple[str, str]]]:
    """Returns {category: [(org, url)]}."""
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    current_cat = "uncategorized"
    for line in md.splitlines():
        h = re.match(r"^##\s+(.+?)\s*$", line)
        if h:
            current_cat = h.group(1).strip()
            continue
        # bullets / paragraphs containing [Org](url). description
        matches = ENTRY_RE.findall(line)
        if matches and not line.lstrip().startswith("- **["):
            # First match is the org link if line starts with it (after optional whitespace)
            stripped = line.lstrip()
            if stripped.startswith("["):
                org, url = matches[0]
                out[current_cat].append((org.strip(), url.strip()))
    return out


def parse_howtheysre(md: str) -> dict[str, list[tuple[str, str]]]:
    """Returns {section: [(title, url)]} for sections that mention postmortems/incidents."""
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    current_section = None
    for line in md.splitlines():
        h = re.match(r"^##\s+(.+?)\s*$", line)
        if h:
            current_section = h.group(1).strip()
            continue
        if not current_section:
            continue
        if any(
            k in line.lower()
            for k in ("postmortem", "post-mortem", "incident", "outage", "rca", "retrospective")
        ):
            for title, url in ENTRY_RE.findall(line):
                out[current_section].append((title.strip(), url.strip()))
    return out


def normalize_org_name(name: str) -> str:
    """Canonicalize org names so 'Github', 'GitHub Inc', 'github.com' merge."""
    n = name.strip()
    # Strip trailing parenthetical like "Cloudflare (2019)"
    n = re.sub(r"\s*\([^)]*\)\s*$", "", n)
    # Common normalizations
    aliases = {
        "google": "Google",
        "google cloud": "Google Cloud",
        "gcp": "Google Cloud",
        "amazon": "AWS",
        "amazon aws": "AWS",
        "aws": "AWS",
        "github": "GitHub",
        "github.com": "GitHub",
        "gitlab": "GitLab",
        "microsoft": "Microsoft",
        "microsoft azure": "Microsoft Azure",
        "azure": "Microsoft Azure",
        "slack": "Slack",
        "cloudflare": "Cloudflare",
        "stripe": "Stripe",
        "discord": "Discord",
        "fastly": "Fastly",
        "atlassian": "Atlassian",
        "sentry": "Sentry",
        "honeycomb": "Honeycomb",
        "datadog": "Datadog",
        "twilio": "Twilio",
        "roblox": "Roblox",
        "heroku": "Heroku",
        "digitalocean": "DigitalOcean",
        "reddit": "Reddit",
        "pagerduty": "PagerDuty",
        "mongodb": "MongoDB",
        "linkedin": "LinkedIn",
        "facebook": "Facebook/Meta",
        "meta": "Facebook/Meta",
        "instagram": "Facebook/Meta",
        "whatsapp": "Facebook/Meta",
        "twitter": "Twitter/X",
        "x": "Twitter/X",
        "circleci": "CircleCI",
        "travis ci": "Travis CI",
        "travis": "Travis CI",
        "buildkite": "Buildkite",
        "wikimedia": "Wikimedia",
        "wikipedia": "Wikimedia",
        "etsy": "Etsy",
        "shopify": "Shopify",
        "spotify": "Spotify",
        "netflix": "Netflix",
        "uber": "Uber",
        "airbnb": "Airbnb",
        "yelp": "Yelp",
        "pinterest": "Pinterest",
        "dropbox": "Dropbox",
        "salesforce": "Salesforce",
        "robinhood": "Robinhood",
        "coinbase": "Coinbase",
        "binance": "Binance",
        "okta": "Okta",
        "auth0": "Auth0",
        "1password": "1Password",
        "buildkite": "Buildkite",
        "vercel": "Vercel",
        "netlify": "Netlify",
        "render": "Render",
        "supabase": "Supabase",
        "planetscale": "PlanetScale",
        "cockroachdb": "CockroachDB",
        "elastic": "Elastic",
        "elasticsearch": "Elastic",
        "redis labs": "Redis",
        "redis": "Redis",
        "confluent": "Confluent",
        "snowflake": "Snowflake",
        "databricks": "Databricks",
        "hashicorp": "HashiCorp",
        "anthropic": "Anthropic",
        "openai": "OpenAI",
        "replicate": "Replicate",
        "anthropic console": "Anthropic",
        "vimeo": "Vimeo",
        "twitch": "Twitch",
        "ebay": "eBay",
        "paypal": "PayPal",
        "square": "Square",
        "doordash": "DoorDash",
        "instacart": "Instacart",
        "lyft": "Lyft",
        "asana": "Asana",
        "notion": "Notion",
        "linear": "Linear",
        "figma": "Figma",
        "miro": "Miro",
        "trello": "Trello",
        "monday.com": "Monday",
        "monday": "Monday",
        "datadoghq": "Datadog",
        "tarsnap": "Tarsnap",
        "joyent": "Joyent",
        "rackspace": "Rackspace",
        "linode": "Linode",
        "ovh": "OVH",
        "ovhcloud": "OVH",
    }
    return aliases.get(n.lower(), n)


def merge_by_org(
    entries: dict[str, list[tuple[str, str]]]
) -> dict[str, list[tuple[str, str, str]]]:
    """Merge by canonical org name. Returns {org: [(category, raw_name, url)]}."""
    by_org: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for cat, lst in entries.items():
        for raw_name, url in lst:
            org = normalize_org_name(raw_name)
            by_org[org].append((cat, raw_name, url))
    return by_org


def tier(count: int) -> str:
    if count >= 5:
        return "A"
    if count >= 2:
        return "B"
    return "C"


def main() -> int:
    try:
        danluu_md = fetch(SOURCES["danluu"])
    except Exception as e:
        print(f"danluu fetch failed: {e}", file=sys.stderr)
        return 2

    try:
        howtheysre_md = fetch(SOURCES["howtheysre"])
    except Exception as e:
        print(f"howtheysre fetch failed: {e}", file=sys.stderr)
        howtheysre_md = ""

    try:
        k8s_md = fetch(SOURCES["k8s_af"])
    except Exception as e:
        print(f"k8s_af fetch failed: {e}", file=sys.stderr)
        k8s_md = ""

    danluu_entries = parse_danluu(danluu_md)
    howtheysre_entries = parse_howtheysre(howtheysre_md) if howtheysre_md else {}
    k8s_entries = parse_danluu(k8s_md) if k8s_md else {}  # similar format

    # Merge all into one entries dict
    all_entries: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for cat, lst in danluu_entries.items():
        all_entries[f"danluu:{cat}"].extend(lst)
    for cat, lst in howtheysre_entries.items():
        all_entries[f"howtheysre:{cat}"].extend(lst)
    for cat, lst in k8s_entries.items():
        all_entries[f"k8s.af:{cat}"].extend(lst)

    by_org = merge_by_org(all_entries)

    # Dedup URLs within each org
    for org in list(by_org.keys()):
        seen_urls = set()
        deduped = []
        for cat, raw, url in by_org[org]:
            key = url.split("#")[0]
            if key in seen_urls:
                continue
            seen_urls.add(key)
            deduped.append((cat, raw, url))
        by_org[org] = deduped

    # Sort orgs by count desc
    sorted_orgs = sorted(by_org.items(), key=lambda x: -len(x[1]))

    # Already in shortlist
    SHORTLIST = {
        "Cloudflare", "AWS", "GitHub", "Slack", "Google Cloud", "Microsoft Azure",
        "Honeycomb", "GitLab", "Discord", "Datadog", "Twilio", "Roblox",
    }

    tier_a, tier_b, tier_c = [], [], []
    for org, entries in sorted_orgs:
        t = tier(len(entries))
        if t == "A":
            tier_a.append((org, entries))
        elif t == "B":
            tier_b.append((org, entries))
        else:
            tier_c.append((org, entries))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Universe Inventory — Public Software Incident Postmortems")
    lines.append("Compiled: 2026-05-27 (automated parse of curated lists)")
    lines.append("")
    lines.append("**Sources parsed:**")
    lines.append(f"- danluu/post-mortems: {sum(len(v) for v in danluu_entries.values())} entries across {len(danluu_entries)} categories")
    if howtheysre_md:
        lines.append(f"- upgundecha/howtheysre: {sum(len(v) for v in howtheysre_entries.values())} postmortem-relevant entries")
    if k8s_md:
        lines.append(f"- hjacobs/kubernetes-failure-stories: {sum(len(v) for v in k8s_entries.values())} entries")
    lines.append("")
    lines.append("## Headline numbers")
    lines.append(f"- Unique organizations identified: **{len(by_org)}**")
    lines.append(f"- Tier A (≥5 postmortem entries indexed): **{len(tier_a)}**")
    lines.append(f"- Tier B (2-4 entries): **{len(tier_b)}**")
    lines.append(f"- Tier C (1 entry): **{len(tier_c)}**")
    lines.append("")
    lines.append("**Note on tier semantics:** these counts come from curated lists. They are a LOWER BOUND on actual archive size — the lists are not exhaustive of each company's own publishing. E.g., Cloudflare's actual archive is ~50, danluu lists ~10.")
    lines.append("")
    lines.append("**Already in shortlist (Phase A.3 in progress):** " + ", ".join(sorted(SHORTLIST)))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Tier A — strong candidates (≥5 indexed entries)")
    lines.append("")
    for org, entries in tier_a:
        marker = " *(in shortlist)*" if org in SHORTLIST else ""
        lines.append(f"### {org}{marker}  — {len(entries)} entries")
        for cat, raw, url in entries[:10]:
            lines.append(f"- [{raw}]({url}) — *{cat}*")
        if len(entries) > 10:
            lines.append(f"- ... and {len(entries) - 10} more")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Tier B — supplementary (2-4 entries)")
    lines.append("")
    for org, entries in tier_b:
        marker = " *(in shortlist)*" if org in SHORTLIST else ""
        lines.append(f"### {org}{marker}  — {len(entries)} entries")
        for cat, raw, url in entries:
            lines.append(f"- [{raw}]({url}) — *{cat}*")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Tier C — single-incident historical/one-offs")
    lines.append("")
    lines.append(f"Total Tier C orgs: {len(tier_c)}. Listed compactly:")
    lines.append("")
    for org, entries in tier_c:
        cat, raw, url = entries[0]
        marker = " *(in shortlist)*" if org in SHORTLIST else ""
        lines.append(f"- **{org}**{marker} — [{raw}]({url}) — *{cat}*")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Sources notes")
    lines.append("")
    lines.append("- **VOID (Verica Open Incident Database)** — not parsed automatically; their stated count is ~10,000 incidents from ~600 orgs as of 2022. Most are status-page entries below RCA quality bar; the database is JS-rendered.")
    lines.append("- **PagerDuty postmortems collection** — methodology guide, not own incidents.")
    lines.append("- **Status pages aggregators** (statuspage.io, incident.io) — would require per-company JS scraping.")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"WROTE {OUT}")
    print(f"  Tier A: {len(tier_a)}, Tier B: {len(tier_b)}, Tier C: {len(tier_c)}, Total: {len(by_org)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
