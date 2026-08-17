# E1: Postmortem → 7-FM Taxonomy Mapping — Agent Protocol

> Strict, repeatable protocol for an agent classifying real-world software incident
> postmortems into GFSO's 7 Failure Modes. Designed so multiple agent sessions
> (one company per call) produce consistent, mergeable output.
>
> **Read this entire document before starting.** Then read prior session outputs
> in `runs/e1_results/` (if any) before writing yours. Format must match exactly.

---

## Goal

Validate or falsify the claim that GFSO's **7 Failure Modes** (defined in
the v3.9 draft §4; v4.0 carries them at §12) exhaustively cover failures of compositional
validation in real software systems.

**Pass criterion**: ≥95% of classified incidents fit exactly one FM with high
confidence → taxonomy empirically validated.
**Fail criterion**: <80% fit, or a substantial set requires "Other" → theory
needs revision (new FM, restructure, or scope correction).

---

## The 7 Failure Modes (canonical definitions, from §4)

You MUST classify into exactly one of these. Read carefully.

| FM | Name | Definition |
|---|---|---|
| **FM-1** | **Correspondence** | Decomposition's children **don't correctly correspond to** parent's criteria. Two sub-flavors: *insufficiency* (a criterion of parent has no responsible child) and *redundancy* (a child exists that doesn't address any parent criterion, so its failure can leak through). |
| **FM-2** | **Consistency** | Two or more children's criteria **conflict** — satisfying one violates another. Joint satisfaction is impossible. |
| **FM-3** | **Verifiability** | A node validated as PASS but the validation **didn't reflect reality** — false-positive at validation. The check passed but the artifact was actually broken. |
| **FM-4** | **Propagation** | A child's FAIL **didn't propagate** up to parent. Validation aggregation broken — parent shows PASS while a child is FAIL. |
| **FM-5** | **Currency** | The spec **changed** but the decomposition wasn't updated. Children operate on stale assumptions; their outputs no longer compose to the new parent goal. |
| **FM-6** | **Feasibility** | The decomposition was attempted **before the information needed to decompose correctly was available**. Pre-condition for D was not yet established. |
| **FM-7** | **Feedback** | An error/blocker was detected by some executor but there **was no channel** to communicate it back. Error stayed invisible until too late. |

### Disambiguation rules (apply in order if multiple plausible)

1. **If the spec was wrong from the start** → FM-1 (insufficiency) or FM-6 (couldn't have known).
   - FM-6 specifically when information needed didn't exist yet at decomposition time.
   - FM-1 when information was available but wasn't used.
2. **If two parts of the system contradicted each other** → FM-2.
3. **If validation said OK but reality wasn't** → FM-3.
4. **If a child component knew it was broken but parent saw OK** → FM-4 (propagation).
5. **If the spec was right at decomposition time but became wrong later** → FM-5.
6. **If someone noticed the issue but couldn't surface it** → FM-7.

### Common confusions
- "Bug in code" → not directly a FM; look at *why* the bug got through. If
  testing should have caught it but didn't → FM-3 (false PASS). If no test for
  that case existed → FM-1 (insufficiency).
- "Hardware failure" → FM-6 if unpredictable, FM-1 if known risk not in NEGLECTED.
- "Race condition" → typically FM-2 (concurrent ops with conflicting requirements)
  or FM-1 (didn't decompose into mutex-safe pieces).
- "Misconfiguration" → FM-1 (config criteria absent) or FM-3 (config validated
  as ok when it wasn't).

---

## Procedure

### Step 0 — Read prior results FIRST
Before starting your assigned company, list `runs/e1_results/`:
```bash
ls runs/e1_results/
```
For each existing file, read its `## Classifications` table to see what kinds of
incidents have been classified and how. This builds shared context across
sessions. **Do NOT duplicate** companies already done.

### Step 1 — Confirm assigned company
Your prompt will specify ONE company. Examples (each their own session):
- Cloudflare (uses `cloudflare.com/blog` post-mortems)
- AWS (uses `aws.amazon.com/premiumsupport/technology/pes/`)
- GitHub (`github.blog/category/engineering/availability/`)
- GitLab (`about.gitlab.com/blog/categories/incident/`)
- Stripe (Stripe status history + engineering blog)
- Slack (slack.engineering tag postmortem)
- BBC (bbc.com/news/technology — outage articles linking to RCAs)
- danluu's curated repo: https://github.com/danluu/post-mortems (organize by
  ORIGINAL company, not just the curator's repo)

### Step 2 — Find incident reports
Use web search to locate 10-15 publicly-documented incidents for the assigned
company. Prefer those with:
- Clear root-cause section (not just timeline)
- Detailed enough to identify what failed structurally
- Last 3-5 years (2021-2026) to be representative of current systems

If fewer than 10 are findable for that company, document why and request a
different company in the output.

### Step 3 — Classify each incident
For each incident, fill in this template:

```
### Incident <N>: <short title>
- **URL**: <link to postmortem>
- **Date**: YYYY-MM-DD
- **One-sentence root cause** (in your words):
- **FM classification**: FM-X
- **Confidence**: high / medium / low
- **Reasoning** (2-4 sentences): explain why this FM and not the others.
  Cite the specific feature of the root cause that maps to this FM's definition.
- **Notes** (optional): edge cases, alternative classifications considered,
  things that don't fit cleanly
```

Confidence rubric:
- **high**: root cause text unambiguously matches one FM definition; no
  reasonable alternative
- **medium**: matches one FM clearly but adjacent FM is plausible if read
  differently
- **low**: doesn't cleanly match any FM, or matches multiple equally well.
  **Document explicitly what doesn't fit.**

### Step 4 — Write summary
At the end of your session output, include:

```
## Summary
- Total incidents classified: <N>
- Distribution:
  - FM-1: <count> (<%>)
  - FM-2: ...
  - ...
  - FM-7: ...
  - Unclassifiable / "Other": <count>
- High confidence: <count>
- Medium confidence: <count>
- Low confidence: <count>

## Findings
- 2-3 bullets on patterns observed
- Specifically call out any incidents that didn't fit any FM — these are
  potential evidence against the taxonomy's completeness claim
- Note any FM that was overused or underused — might suggest definition
  refinement needed
```

### Step 5 — Save and exit
Write your full output to: `runs/e1_results/<company-lowercase>.md`.
Use this exact filename pattern (e.g., `runs/e1_results/cloudflare.md`).

Do not modify any other files. Do not commit. The orchestrator will review and
commit.

---

## Output file template (copy this skeleton)

```markdown
# E1: <Company> Postmortem Classification
Agent session: <date> <agent_id>
Protocol version: 1.0
Prior sessions read: [list of files in runs/e1_results/ before you started]

## Classifications

### Incident 1: <title>
- **URL**: ...
- **Date**: ...
- **One-sentence root cause**: ...
- **FM classification**: FM-X
- **Confidence**: high/medium/low
- **Reasoning**: ...
- **Notes**: ...

### Incident 2: ...
[repeat for all 10-15]

## Summary
- Total: N
- Distribution: FM-1=X, FM-2=Y, ...
- Confidence: high=A, medium=B, low=C

## Findings
- ...
- ...

## Issues / Suggestions
- (anything the orchestrator should know — e.g., "this company's postmortems
  are sparse and didn't yield 10 quality cases"; "incident X seems to
  require a new FM I'd suggest defining as...")
```

---

## What NOT to do

- Don't classify based on the title or summary alone. Read the actual root
  cause section.
- Don't force-fit a FM. If it doesn't match, mark low confidence and
  explain what doesn't fit. We need the negative cases.
- Don't modify the FM definitions to make a case fit. Definitions are fixed.
- Don't classify multiple FMs for one incident — pick the **primary** one. If
  multiple genuinely apply equally, mark low confidence and explain.
- Don't include speculation about company internals beyond what the postmortem
  states.
- Don't paraphrase the postmortem at length — just give one-sentence root cause
  + your reasoning.

---

## Sources for finding postmortems

Authoritative collections:
- `github.com/danluu/post-mortems` — curated index organized by company
- `incident.io/learn` — incident library
- `srebook.com` (Google SRE book examples)
- `verica.io/learning` — incident analysis archives

Company-specific:
- Cloudflare: blog.cloudflare.com (tag: outage / post-mortem)
- AWS: aws.amazon.com/premiumsupport/technology/pes/
- GitHub: github.blog → Engineering → Availability
- GitLab: about.gitlab.com/blog/categories/incident
- Atlassian: atlassian.com → Status → Incident History
- Heroku: status.heroku.com → archive

---

## Goal restated

Produce a clean, consistent classification of 10-15 real incidents per company
session. After ~6-10 sessions across different companies, the orchestrator
aggregates ~100 incidents and computes the validation rate. The goal isn't to
prove GFSO right; it's to **honestly test** whether the 7-FM taxonomy
empirically holds.

If it does → strong scientific positioning for GFSO (falsifiable claim survives).
If it doesn't → the theory gets refined based on the gap.

Either outcome is valuable.
