# E1 — Classification Protocol (v3.1)

> v3.1 (2026-05-29): aligned to canon v3.3 — FM-3 two-directional (false-PASS ∧ false-FAIL),
> FM-1 sub-taxonomy (a–e), STD-2 predictability router + root-cause GATE for external triggers.
> Annotator: Opus only (consistency). "Track A/B" = classification tracks (not project phases).

Input: `data/postmortems/corpus.json` (230 records, schema v1.1.0).
Output: `runs/e1_results/annotations.json` (one annotation object per record).
Do NOT mutate corpus.json — annotations live in a separate layer (multi-annotator design).

Two tracks, dispatched by `entry_type`:
- **Track A** — `incident` (216 records): classify root cause into the 7 Failure Modes.
- **Track B** — `process_case` (14 Scrum records): map the process narrative onto GFSO primitives (§17.2 embedding). NO failure mode.

This protocol incorporates fixes surfaced by the initial 13-record trial.

---

## Common rules

- Classify ONLY from the record's verbatim quotes. No external lookup.
- Each record → exactly one annotation object (see output schema below).
- Be honest about poor fits. Low-confidence + explanation is more valuable than a forced label.
- UTF-8 throughout (corpus has non-ASCII + Russian).

---

## Track A — incidents → 7 Failure Modes

### The 7 FM (canonical, from the v3.9 draft §4 — v4.0 carries them at §12)

| FM | Name | Definition |
|---|---|---|
| FM-1 | Correspondence | Children of D don't correctly correspond to parent's criteria. *Insufficiency* (a parent criterion has no responsible child) or *redundancy* (a child addresses no parent criterion). **Tag a sub-type** (see below). |
| FM-2 | Consistency | Two+ children's criteria conflict; joint satisfaction impossible. |
| FM-3 | Verifiability | A validation value didn't reflect reality — **either direction**. *false-PASS*: PASS where reality is fail. *false-FAIL*: FAIL where reality is pass (over-rejection, e.g. a healthy node judged dead → needless failover). The defect is at the *value*; if a wrong verdict also mis-propagates, that is additionally FM-4. |
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

5. **External-trigger incidents — run the STD-2 predictability router (NEW v3).** When the trigger is outside the actor (upstream BGP/DNS/power/transit, a vendor outage), do NOT default to NONE. First set the parent goal correctly ("stay available *despite* foreseeable external faults"), then triage by STD-2 predictability:
   - **ordinary** (recurs in this domain, P estimable from data — route leaks, power loss, transit degradation): a mitigation child was REQUIRED → its absence = **FM-1.b** (missing-resilience). If a mitigation child existed and *worked* (resilience absorbed the fault, little/no impact) → there is **no FM** (correct NONE — log as "resilience-worked", not a gap).
   - **statistical** (estimable but rare): FM-1.b *or* a justified NEGLECTED omission.
   - **extraordinary** (no precedent AND not derivable): genuine **§2.1 boundary** — out of scope, mark NONE with reason "boundary".
   - **adversarial** (attacker, compromise, social-engineering): **§16.2** — out of non-adversarial scope, mark NONE with reason "adversarial".
   So most "external" NONE collapse to FM-1.b; true residual NONE = adversarial + extraordinary + resilience-worked only.

   **GATE (v3.1, critical — classify on ROOT CAUSE, not trigger).** An attacker, a vendor
   outage, a fire, a hijack is a **trigger**, not a root cause. Before assigning §16.2
   (adversarial) or §2.1 (boundary), ask: *was a standard domain mitigation missing?* Domains
   routinely defend against these — patching known CVEs, RPKI/route monitoring, rate-limiting,
   dependency isolation, multi-provider/geo-redundancy, fire-suppression, 2FA/session hardening.
   If such a foreseeable mitigation was **absent**, the root cause is **FM-1.b** (missing
   resilience) *regardless of the trigger being external/adversarial*. Reserve the out-of-scope
   buckets strictly:
   - **§16.2 (adversarial)** ONLY when the attack was genuinely novel with no foreseeable
     mitigation, OR the missing mitigation belonged to a **third party** the actor doesn't
     control (e.g. a vendor's compromised endpoint, a customer's hijacked registrar).
   - **§2.1 (boundary/extraordinary)** ONLY when no precedent exists AND it's not derivable from
     known models AND no standard domain mitigation exists. (A datacenter fire does NOT qualify —
     fire-suppression + geo-redundancy are standard → FM-1.b.)
   - **resilience-worked** = a real mitigation existed and absorbed the fault → no FM (evidence
     *for* the framework, a distinct bucket, not a gap).
   Most "adversarial/boundary" NONE fail this gate and are FM-1.b. Expected true residual ≈ 2-3.

### FM-1 sub-types (NEW v3 — set `failure_mode_subtype` when primary = FM-1)

| Sub-type | When |
|---|---|
| FM-1.a missing-criterion | a parent criterion has no responsible child at all (CHECK-1, topological) |
| FM-1.b missing-resilience | a foreseeable external risk (STD-2 ordinary/statistical) had no mitigation child |
| FM-1.c missing-risk-grouping | correlated risks not grouped/systematized (STD-3) |
| FM-1.d insufficient-entailment | children all present but their criteria don't quantitatively *entail* the parent criterion (CHECK-7, e.g. budgets that don't add up) |
| FM-1.e redundancy | a child addresses no parent criterion (non-redundancy) |

Sub-type is a *secondary* tag; primary stays FM-1. Don't collapse FM-1.d into FM-1.a — "present but doesn't entail" ≠ "no child".

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

`runs/e1_results/annotations.json`:

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
        "failure_mode_subtype": null,
        "fm3_direction": "false-PASS | false-FAIL | null",
        "secondary_failure_modes": ["FM-1"],
        "none_reason": "adversarial | boundary | resilience-worked | null"
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

Produce `runs/e1_results/leaderboard.md`:
- FM distribution overall + sliced by `domain`, `company`, `methodology`
- Count of NONE / unclassifiable (the falsification signal — pass criterion: ≥95% fit one FM)
- FM-3/7/1 disagreement rate (the boundary the tie-breaks address)
- Track B: how many Scrum cases mapped full / partial / out_of_scope; any unmapped Scrum element (would be §17.2 counterexample)
