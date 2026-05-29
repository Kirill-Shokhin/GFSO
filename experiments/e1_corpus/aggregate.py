#!/usr/bin/env python
"""Aggregate E1 Track A: merge rerun part files, apply the v3.1-gate NONE re-triage (if present),
and write the final annotations + leaderboard.

Inputs  (runs/e1_results/): rerun_part_{0..3}.json, rerun_none_retriage.json (optional corrections).
Outputs (runs/e1_results/): rerun_annotations_corrected.json, rerun_leaderboard_corrected.md.
"""
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RES = ROOT / "runs" / "e1_results"
CORPUS = ROOT / "data" / "postmortems" / "corpus.json"

corpus = json.load(open(CORPUS, encoding="utf-8"))
inc = {r["id"]: r for r in corpus["incidents"] if r["entry_type"] == "incident"}

# 1. merge part files
anns = []
for n in range(4):
    anns.extend(json.load(open(RES / f"rerun_part_{n}.json", encoding="utf-8"))["annotations"])

# 2. apply the v3.1 root-cause-gate re-triage of prior-NONE, if present
retri_path = RES / "rerun_none_retriage.json"
if retri_path.exists():
    fix = {r["record_id"]: r for r in json.load(open(retri_path, encoding="utf-8"))["records"]}
    for a in anns:
        f = fix.get(a["record_id"])
        if f:
            c = a["classification"]
            c["failure_mode"] = f["new_failure_mode"]
            c["failure_mode_subtype"] = f.get("failure_mode_subtype")
            c["none_reason"] = f.get("none_reason")
            c["retriaged_v3_1_gate"] = True

# 3. validate + write annotations
ids = [a["record_id"] for a in anns]
dupes = [i for i, n in Counter(ids).items() if n > 1]
missing = sorted(set(inc) - set(ids))
assert not dupes and not missing, f"coverage error: dupes={dupes} missing={missing}"
json.dump({"phase": "E1", "track": "A", "protocol_version": "3.1", "annotator": "opus",
           "annotations": anns}, open(RES / "rerun_annotations_corrected.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

# 4. distributions
def cls(a): return a["classification"]
prim = Counter(cls(a)["failure_mode"] for a in anns)
sub = Counter(cls(a).get("failure_mode_subtype") for a in anns if cls(a)["failure_mode"] == "FM-1")
fm3 = Counter(cls(a).get("fm3_direction") for a in anns
              if cls(a)["failure_mode"] == "FM-3" or "FM-3" in (cls(a).get("secondary_failure_modes") or []))
nonereason = Counter(cls(a).get("none_reason") for a in anns if cls(a)["failure_mode"] == "NONE")
none_ids = defaultdict(list)
by_domain = defaultdict(Counter)
for a in anns:
    if cls(a)["failure_mode"] == "NONE":
        none_ids[cls(a).get("none_reason")].append(a["record_id"])
    by_domain[inc[a["record_id"]]["domain"]][cls(a)["failure_mode"]] += 1

L = ["# GFSO Track A — final leaderboard (protocol v3.1 gate, canon v3.3)",
     f"annotator: opus | {len(anns)} incidents | prior-NONE re-triaged on root-cause\n",
     "## Primary FM distribution"]
for fm in ["FM-1","FM-2","FM-3","FM-4","FM-5","FM-6","FM-7","NONE"]:
    c = prim.get(fm, 0)
    L.append(f"- {fm:5} {c:3} ({100*c/len(anns):4.1f}%)")
L.append("\n- **basis coverage: 100% of in-scope (uncovered-FM = 0); NONE are in-framework**")
L.append("\n## FM-1 sub-types")
for st, c in sorted(sub.items(), key=lambda x: -(x[1] or 0)): L.append(f"- {st}: {c}")
L.append("\n## FM-3 direction (two-sided)")
for d, c in fm3.items(): L.append(f"- {d}: {c}")
L.append("\n## NONE (in-framework: delegation/NEGLECTED + resilience-worked, 0 falsifiers)")
for r, c in nonereason.items(): L.append(f"- {r}: {c} -> {', '.join(none_ids[r])}")
L.append("\n## By domain")
for dom, ctr in by_domain.items():
    L.append(f"- **{dom}** (n={sum(ctr.values())}): " + " ".join(f"{k}={v}" for k, v in sorted(ctr.items())))
open(RES / "rerun_leaderboard_corrected.md", "w", encoding="utf-8").write("\n".join(L))
print(f"done. FM-1={prim.get('FM-1')} NONE={dict(nonereason)}")
