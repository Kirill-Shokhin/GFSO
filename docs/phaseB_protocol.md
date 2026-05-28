# Phase B — Classification Protocol (v2)

Input: `data/postmortems/corpus.json` (230 records, schema v1.1.0).
Output: `runs/phaseB/annotations.json` (one annotation object per record).
Do NOT mutate corpus.json — annotations live in a separate layer (multi-annotator design).

Two tracks, dispatched by `entry_type`:
- **Track A** — `incident` (216 records): classify root cause into the 7 Failure Modes.
- **Track B** — `process_case` (14 Scrum records): map the process narrative onto GFSO primitives (§17.2 embedding). NO failure mode.

This protocol incorporates fixes surfaced by the 13-record trial (runs/phaseB_trial/).

---

## Common rules

- Classify ONLY from the record's verbatim quotes. No external lookup.
- Each record → exactly one annotation object (see output schema below).
- Be honest about poor fits. Low-confidence + explanation is more valuable than a forced label.
- UTF-8 throughout (corpus has non-ASCII + Russian).

---

## Track A — incidents → 7 Failure Modes

### The 7 FM (canonical, from applied_gfso_v3.md §4)

| FM | Name | Definition |
|---|---|---|
| FM-1 | Correspondence | Children of D don't correctly correspond to parent's criteria. *Insufficiency* (a parent criterion has no responsible child) or *redundancy* (a child addresses no parent criterion). |
| FM-2 | Consistency | Two+ children's criteria conflict; joint satisfaction impossible. |
| FM-3 | Verifiability | A node validated PASS but the validation didn't reflect reality — false PASS. |
| FM-4 | Propagation | A child's FAIL didn't propagate up; parent shows PASS while a child is FAIL. |
| FM-5 | Currency | Spec changed but D wasn't updated; children compute on stale assumptions. |
| FM-6 | Feasibility | D attempted before the information needed to decompose correctly existed. |
| FM-7 | Feedback | An executor detected a defect but had no channel to surface/correct it in time. |

### Mapping the incident to GFSO

- parent = the system-level goal ("edge serves traffic", "payroll pays staff correctly")
- children = subsystems / components / the change that was made
- criteria = the (often implicit) acceptance conditions
- validation = whatever pre-release/runtime check was supposed to catch it

### Disambiguation / tie-break rules (NEW — from trial)

The trial found three recurring blurry boundaries. Apply these tie-breaks:

1. **FM-3 vs FM-1** (false-pass vs missing-criterion):
   - A validation step *existed and was executed* but gave the wrong verdict → **FM-3**.
   - No validation/criterion for that case *existed at all* → **FM-1** (insufficiency).
   - If the source doesn't disambiguate → default **FM-1**, confidence ≤ medium.

2. **FM-3 vs FM-7** (false-pass vs broken-feedback):
   - The defect was *never truthfully observed* at the gate → **FM-3**.
   - The defect *was detected* (by someone/some component) but the channel to escalate/act failed or was too slow → **FM-7**.

3. **FM-1 vs FM-6** (missing-criterion vs couldn't-have-known):
   - The needed info *existed* at decomposition time but wasn't used → **FM-1**.
   - The info *did not yet exist* when D was fixed → **FM-6**.

4. **Emergent / capacity cascades** (e.g. handshake-timeout under mass load): §4.6 maps emergent properties to FM-1, but flag these explicitly as low-confidence "applied by rule, not by fit" — they are the taxonomy's stress points and we want them visible.

### Primary + secondary FM (NEW — from trial)

Mono-causal ops incidents usually get one clean FM. But multi-causal records
(`domain` = project_delivery / safety_critical) often co-activate 3+ FMs.
Do NOT force a single label and lose signal:

- `failure_mode` = the PRIMARY (dominant) FM.
- `secondary_failure_modes` = array of other FMs that genuinely co-activate (may be empty).
- In `rationale`, say why primary is dominant.

A record fitting NO FM at all is the most important finding — mark `failure_mode: "NONE"`, confidence high, and explain exactly what doesn't fit. These falsify the exhaustiveness claim and must be loud.

---

## Track B — Scrum process_cases → GFSO primitive embedding

### CRITICAL: where the content is

For `process_case` records, `impact_quotes` / `root_cause_quotes` are **null**.
The verbatim narrative is in `extensions.situation_before_quotes`,
`extensions.what_was_done_quotes`, `extensions.outcome_quotes` — and it is in **RUSSIAN**.
Read those fields. (The trial nearly missed this.)

### What to produce

This is the §17.2 "Scrum ⊂ GFSO" embedding demonstration. For each case:

1. **Scope check first.** Is the narrative actually about a *task-handoff transaction* (a goal delegated, executed, validated)? Some book cases are about organizational CULTURE (Zappos: happiness index, hiring), not handoffs. If it's NOT a handoff:
   - `in_scope: false`, list why, do NOT report "0 primitives" as if it were a Scrum failure. It's simply outside GFSO's unit of analysis (CORE.md). Exclude from the embedding count.

2. **For in-scope cases**, identify which GFSO primitives the narrative exhibits:
   `Spec, Criteria, Deadline, Delegation, Decomposition_D, Dependencies`, and FSM signals (`DELIVER, PASS, FAIL, CHALLENGE, BLOCK`, etc).
   - For each present primitive, cite the Russian narrative feature that shows it.
   - List `unmapped_scrum_elements`: any Scrum element that does NOT map to a GFSO primitive. **This is the falsification target** — if a real Scrum primitive escapes GFSO, §17.2 is wrong. (Refinements that still land inside GFSO, e.g. Scrum Master ≈ CHALLENGE channel, are NOT escapes.)
   - Check the §17.2 constraints hold observably: depth(D)≤2, NEGLECTED=∅, informal audit, uniform sprint deadline.

3. The honest question: does the case map FULLY (all core primitives present, nothing escapes), PARTIALLY, or is it OUT OF SCOPE?

### Be especially careful here ("со скрамом не оплошай")

- Read the Russian. Don't classify from the English one-line title.
- Distinguish "out of scope" (not a handoff) from "Scrum element escapes GFSO" (would falsify §17.2). These are completely different findings.
- The rich cases (FBI Sentinel, Medco, eduScrum, House renovation) have enough narrative for a full mapping — do the full decomposition, don't shortcut.
- Thin/illustrative cases (wedding, NUMMI anecdote) may only support a partial mapping — say so.

---

## Output schema

`runs/phaseB/annotations.json`:

```json
{
  "phase": "B",
  "date": "2026-05-28",
  "protocol_version": "2",
  "scheme": "gfso-7fm + scrum-embedding",
  "annotations": [
    {
      "record_id": "cloudflare-008",
      "entry_type": "incident",
      "scheme": "gfso-7fm",
      "classification": {
        "failure_mode": "FM-3",
        "name": "Verifiability",
        "secondary_failure_modes": ["FM-1"]
      },
      "confidence": "high",
      "rationale": "...",
      "alternatives_considered": "..."
    },
    {
      "record_id": "scrum_cases-001",
      "entry_type": "process_case",
      "scheme": "scrum-embedding",
      "classification": {
        "in_scope": true,
        "mapping": "full | partial | out_of_scope",
        "primitives_present": ["Spec", "Criteria", "..."],
        "unmapped_scrum_elements": [],
        "constraints_observed": ["depth(D)<=2", "NEGLECTED=∅", "..."]
      },
      "confidence": "high",
      "rationale": "..."
    }
  ]
}
```

Each annotation is mergeable into the corresponding corpus record's `annotations[]` (Annotation type in schema.json) at aggregation time.

---

## Aggregation (after all records annotated)

Produce `runs/phaseB/leaderboard.md`:
- FM distribution overall + sliced by `domain`, `company`, `methodology`
- Count of NONE / unclassifiable (the falsification signal — pass criterion: ≥95% fit one FM)
- FM-3/7/1 disagreement rate (the boundary the tie-breaks address)
- Track B: how many Scrum cases mapped full / partial / out_of_scope; any unmapped Scrum element (would be §17.2 counterexample)
