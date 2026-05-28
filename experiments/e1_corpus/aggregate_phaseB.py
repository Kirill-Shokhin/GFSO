#!/usr/bin/env python
"""Merge Phase B part_*.json annotations and produce the leaderboard.

Reads runs/phaseB/part_*.json (each {part, annotations:[...]}), joins against
corpus.json for domain/company/methodology, validates coverage (all 230 records,
no dupes), and writes:
  runs/phaseB/annotations.json  -- merged flat list
  runs/phaseB/leaderboard.md    -- FM distribution sliced + Track B summary
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PB = ROOT / "runs" / "phaseB"
CORPUS = ROOT / "data" / "postmortems" / "corpus.json"


def main() -> int:
    corpus = {r["id"]: r for r in json.load(CORPUS.open(encoding="utf-8"))["incidents"]}
    anns = []
    for pf in sorted(PB.glob("part_*.json")):
        data = json.load(pf.open(encoding="utf-8"))
        anns.extend(data["annotations"])

    # Coverage check
    ann_ids = [a["record_id"] for a in anns]
    dupes = [k for k, v in Counter(ann_ids).items() if v > 1]
    missing = set(corpus) - set(ann_ids)
    extra = set(ann_ids) - set(corpus)

    incidents = [a for a in anns if a.get("entry_type") == "incident"]
    process = [a for a in anns if a.get("entry_type") == "process_case"]

    def fm(a):
        return a.get("classification", {}).get("failure_mode", "?")

    # Overall FM distribution (incidents)
    overall = Counter(fm(a) for a in incidents)
    none_ids = [a["record_id"] for a in incidents if fm(a) == "NONE"]
    fit = sum(1 for a in incidents if fm(a) != "NONE")
    fit_rate = fit / len(incidents) * 100 if incidents else 0

    # By domain / company / methodology
    by_domain = defaultdict(Counter)
    by_company = defaultdict(Counter)
    by_method = defaultdict(Counter)
    for a in incidents:
        rec = corpus.get(a["record_id"], {})
        by_domain[rec.get("domain", "?")][fm(a)] += 1
        by_company[rec.get("company", "?")][fm(a)] += 1
        by_method[rec.get("methodology", "?")][fm(a)] += 1

    # Secondary usage + confidence
    sec_used = sum(1 for a in incidents if a.get("classification", {}).get("secondary_failure_modes"))
    conf = Counter(a.get("confidence", "?") for a in incidents)

    # Track B
    tb_map = Counter(a.get("classification", {}).get("mapping", "?") for a in process)
    unmapped = []
    for a in process:
        u = a.get("classification", {}).get("unmapped_scrum_elements", [])
        if u:
            unmapped.append((a["record_id"], u))

    # Write merged annotations
    merged = {
        "phase": "B",
        "protocol_version": "2",
        "annotator": "opus",
        "total": len(anns),
        "incidents": len(incidents),
        "process_cases": len(process),
        "annotations": anns,
    }
    (PB / "annotations.json").write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Leaderboard markdown
    FMS = ["FM-1", "FM-2", "FM-3", "FM-4", "FM-5", "FM-6", "FM-7", "NONE"]
    L = []
    L.append("# GFSO Phase B Leaderboard")
    L.append(f"Protocol v2 · annotator: opus · {len(incidents)} incidents + {len(process)} process_cases\n")
    L.append("## Coverage")
    L.append(f"- annotations: {len(anns)} (incidents {len(incidents)}, process_cases {len(process)})")
    L.append(f"- duplicates: {dupes or 'none'}")
    L.append(f"- missing from corpus: {sorted(missing) or 'none'}")
    L.append(f"- extra (not in corpus): {sorted(extra) or 'none'}\n")

    L.append("## Track A — 7 Failure Modes (incidents)")
    L.append(f"- **fit rate: {fit_rate:.1f}%** ({fit}/{len(incidents)} fit a FM; NONE={len(none_ids)})")
    L.append(f"- pass criterion ≥95%: {'PASS' if fit_rate>=95 else 'FAIL — see NONE cluster'}")
    L.append(f"- secondary FM used on {sec_used}/{len(incidents)} records")
    L.append(f"- confidence: {dict(conf)}\n")
    L.append("### Overall distribution (primary FM)")
    tot = len(incidents)
    for f in FMS:
        n = overall.get(f, 0)
        bar = "█" * round(n / tot * 40) if tot else ""
        L.append(f"- {f:5} {n:4} ({n/tot*100:4.1f}%) {bar}")
    L.append("")
    L.append(f"### NONE incidents ({len(none_ids)})")
    L.append("These don't fit any FM — the falsification signal. " + (", ".join(none_ids) if none_ids else "none"))
    L.append("")

    L.append("### By domain")
    for dom in sorted(by_domain):
        c = by_domain[dom]
        t = sum(c.values())
        dist = " ".join(f"{k}={v}" for k, v in sorted(c.items()))
        L.append(f"- **{dom}** (n={t}): {dist}")
    L.append("")
    L.append("### By methodology")
    for m in sorted(by_method):
        c = by_method[m]; t = sum(c.values())
        L.append(f"- **{m}** (n={t}): " + " ".join(f"{k}={v}" for k, v in sorted(c.items())))
    L.append("")
    L.append("### By company")
    for comp in sorted(by_company, key=lambda x: -sum(by_company[x].values())):
        c = by_company[comp]; t = sum(c.values())
        L.append(f"- {comp} (n={t}): " + " ".join(f"{k}={v}" for k, v in sorted(c.items())))
    L.append("")

    L.append("## Track B — Scrum embedding (§17.2)")
    L.append(f"- mapping verdicts: {dict(tb_map)}")
    L.append(f"- **unmapped Scrum elements (would be §17.2 counterexamples): {unmapped or 'NONE FOUND'}**")
    L.append("")

    (PB / "leaderboard.md").write_text("\n".join(L), encoding="utf-8")

    # Console summary
    print(f"merged {len(anns)} annotations | incidents {len(incidents)} process {len(process)}")
    print(f"dupes={dupes or 0} missing={len(missing)} extra={len(extra)}")
    print(f"fit_rate={fit_rate:.1f}% NONE={len(none_ids)}")
    print("FM:", dict(overall))
    print(f"Track B: {dict(tb_map)} unmapped={unmapped or 'none'}")
    print(f"wrote {PB/'annotations.json'} + {PB/'leaderboard.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
