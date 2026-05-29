# Scrum ⊂ GFSO — Worked Examples (causal before/after)

> Deepens §17.2 from *structural containment* (Scrum's parts map to GFSO primitives —
> proven in E1 Track B, 0 unmapped) toward a *causal* reading: each rich Scrum case carries
> a **before/after A/B** — a BEFORE failure (pre-Scrum, FM-classifiable) and an AFTER success
> (Scrum, GFSO primitives present). The **DELTA** — the primitive the before lacked that the
> after supplied — is a candidate causal claim "**primitive X guards failure-mode Y**".
>
> Source: 14 `process_case` records (Sutherland, *Scrum*) in the corpus. 4 are rich enough
> for an A/B (confirmed by extraction): FBI Sentinel, house-renovation, Medco, eduScrum.
> Book text is copyright — quotes kept minimal; the value here is the GFSO mapping (our analysis).
>
> **Status of the claim:** illustrative-strong, NOT falsification-grade. Single advocacy
> source ⇒ selection/survivorship bias; the BEFORE FM-labels come from the book's framing,
> not independent postmortems. This deepens §17.2; it does not by itself prove causation.

---

## Method

```
BEFORE (pre-Scrum failure)  →  FM classification (which GFSO mechanism was absent)
AFTER  (Scrum success)      →  which GFSO primitives are present
DELTA  = primitive added    →  "this primitive guards that FM"
```

GFSO primitives in play: **Criteria** (Definition of Done), **T.deadline** (sprint length),
**D** (backlog→sprint decomposition), **Dep** (impediment/dependency tracking), signals
**DELIVER / PASS / FAIL** (Sprint Review = V), **CHALLENGE / BLOCK** (Daily Scrum, impediment
escalation). Per §17.2 Scrum is a *restricted* GFSO: depth(D)≤2, NEGLECTED=∅, CHECK-7/8 not
enforced, informal audit, uniform sprint deadline.

---

## 1. FBI Sentinel (`scrum_cases-001`)

**BEFORE** — Lockheed waterfall: ~10 years, ~$405M, half-done, 6–8 more years projected; the
predecessor (VCF) shipped *nothing usable* after $170M.
**FM:** primary **FM-7 (Feedback)** — a decade-long plan with no working increment means
defects are invisible until the end; no channel surfaces "this is off" in time. Compounded by
**FM-1 (Correspondence)** — the goal was never decomposed into independently *verifiable*
deliverables — and **FM-6 (Feasibility)** — a full upfront D over a 10-year horizon attempts a
decomposition before the information to fix it exists.

**AFTER** — Scrum: 2-week cycles, each producing a fully functioning slice, demonstrated to the
actual users. Productivity tripled; shipped in ~20 months at <5% of remaining budget.
**Primitives present:** short **T.deadline** (2-week sprint), **DELIVER→V every cycle** (a
working increment validated each sprint), **CHALLENGE** via stakeholder demos.

**DELTA → causal claim:** the added primitive is **short-horizon continuous DELIVER→V**.
- It supplies the **FM-7** feedback channel (every 2 weeks, not every decade).
- It forces **FM-1** verifiable increments (each slice has acceptance criteria).
This is §17.1 (adaptive stratification) made operational: short horizon ⇒ concrete criteria ⇒
frequent validation/CHALLENGE. **Primitive `short-sprint + per-sprint V` guards FM-7 and FM-1.**

---

## 2. House renovation (`scrum_cases-005`) — the natural controlled experiment

**BEFORE / control** — a *neighbor* hired the **same workers** for the **same house** without
Scrum: 3 months instead of 6 weeks, ~2× time and cost.
**FM:** **FM-7 (Feedback)** + **FM-5 (Currency)** — no daily coordination, so material
shortages and blockers were discovered *late*, after they already stalled work (stale state
acted upon).

**AFTER** — Elko's crew: daily stand-up (yesterday / today / impediments) + a visible board;
shortages surfaced *before* they blocked. Finished in 6 weeks, on budget.
**Primitives present:** **Daily Scrum** = continuous **CHALLENGE/BLOCK** channel; **board** =
dependency visibility; impediments raised and cleared daily.

**DELTA → causal claim:** **daily stand-up + board**.
- Supplies **FM-7** (impediments have a daily channel) and **FM-5** (dependencies/shortages
  caught before they make the plan stale).
**Why this case matters most:** same house, same workers, only variable = Scrum. It is the
closest thing in the corpus to a controlled experiment isolating the causal effect of the
feedback/currency primitives. **Primitive `daily standup + board` guards FM-7 and FM-5.**

---

## 3. Medco Health Solutions (`scrum_cases-006`)

**BEFORE** — a go-live date committed to Wall Street top-down; the implementers learned of it
afterward; the plan was 1100-page specs that "described a fictional reality"; six months in,
they realized they'd miss by a year.
**FM:** primary **FM-1 (Correspondence)** — 1100 pages but no decomposition into *verifiable
done-units* (volume ≠ criteria); plus **FM-6** (detailed upfront plan as fiction) and **FM-7**
(impediments unsurfaced).

**AFTER** — backlog built by cutting the specs down to "what actually must be done"; a column
explicitly named **"Definition of Done"**; prioritization by value; an impediment list with a
named owner per item, all cleared within days; velocity rose ~4× (20→90).
**Primitives present:** **D** as backlog (coverage + non-redundancy — cut the ballast),
**Criteria** as the explicit DoD column, **BLOCK→RESOLVE_BLOCK** as the owned impediment list.

**DELTA → causal claim:** **explicit Definition of Done (= Criteria) + owned impediment list**.
- The DoD column *is* GFSO Criteria — the cleanest "DoD = Criteria" instance in the corpus.
- It supplies **FM-1** (criteria now exist and are verifiable) and the impediment list supplies
  **FM-7**.
**Primitive `Definition of Done` guards FM-1 (and FM-3: a binary DoD is a real V, not a
rubber-stamp). Primitive `owned impediment list` guards FM-7.**

---

## 4. eduScrum / school (`scrum_cases-010`) — domain transfer

**BEFORE** — passive lecture; students disengage ("checked out") with no signal of who
understood.
**FM:** **FM-1** (no verifiable criterion for "material actually learned") + **FM-7** (no
feedback on per-student understanding). (Softer BEFORE than the others — disengagement, not a
sharp project failure.)

**AFTER** — desks in groups; a board (todo/doing/done); burndown; retrospective; planning
poker; sprints of 4–5 weeks; and a **collective Definition of Done**: a task moves to "done"
only when the material is understood by *all* students. Exam grades +10%; the method spread to
dozens of schools.
**Primitives present:** **collective Criteria** (the all-students DoD), **board + retro** =
feedback/audit, a "joy" criterion (an extra acceptance predicate).

**DELTA → causal claim:** **collective DoD (= Criteria) + board/retro (feedback)** guard
**FM-1 and FM-7** — in a *non-software* domain. Value here is the **domain-transfer evidence**:
GFSO's unit of analysis (a verifiable handoff) and §17.2 containment hold outside software.

---

## Synthesis — primitive → failure-mode it guards

| Scrum primitive | GFSO mapping | Guards FM | Case(s) |
|---|---|---|---|
| Short sprint + per-sprint increment | T.deadline (short horizon) + DELIVER→V each cycle | FM-7, FM-1 | FBI |
| Daily Scrum + board | CHALLENGE/BLOCK channel + dependency visibility | FM-7, FM-5 | House |
| Definition of Done | Criteria (explicit, binary V) | FM-1, FM-3 | Medco, eduScrum |
| Owned impediment list | BLOCK → RESOLVE_BLOCK | FM-7 | Medco |
| Backlog (cut to essentials) | D: coverage + non-redundancy | FM-1 | Medco |
| Stakeholder demo | CHALLENGE (spec defect surfaced early) | FM-7, FM-1 | FBI, eduScrum |

Every *working* Scrum primitive instantiates a GFSO mechanism that guards a specific FM — and
the BEFORE failures cluster on exactly those FMs (FM-1, FM-5, FM-7).

---

## Why this is theory-model evidence (ties to Delta E / §18.1 work)

Scrum is a **restricted GFSO** (§17.2): it omits CHECK-7/8 (so it cannot guard FM-1.d
entailment-insufficiency or FM-2 consistency), omits NEGLECTED (STD-1), caps depth(D)≤2. What
it *keeps* is exactly the cluster {short-horizon Criteria, continuous V, CHALLENGE/BLOCK
feedback} — the mechanisms that guard **FM-1, FM-5, FM-7**.

So the before/after deltas say: **pre-Scrum work failed precisely at FM-1/5/7, and Scrum
succeeded by supplying exactly the GFSO mechanisms that guard them.** This is concrete evidence
for the theory-model thesis (Delta E): work "worked" when it *partially instantiated* GFSO;
Scrum is the documented, repeatable partial instantiation. People weren't following GFSO
knowingly — they reinvented the subset that guards the most common FMs.

**Falsifiable prediction (from the SAME mapping):** Scrum should *fail* where the FMs it does
NOT guard dominate — deep decomposition (depth>2), multi-team quantitative composition (CHECK-7
/ FM-1.d), formal consistency (CHECK-8 / FM-2), compliance audit (NEGLECTED). §17.2 already
names this regime; the worked examples make the mechanism explicit: Scrum's omitted checks =
the FMs it leaves unguarded. A Scrum success in a depth>2 / multi-team / high-FM-1.d setting
*without* reintroducing those checks would be the falsifier.

---

## Caveats (honest)

- **Single source, advocacy framing.** Sutherland's book selects successes; survivorship bias
  is real. The BEFORE FM-labels are read from the book's narrative, not independent RCAs.
- **Negative-ending cases excluded.** `scrum_cases-004` (US Special Forces Iraq — collaboration
  later unwound) and `scrum_cases-013` (Iceland constitution — parliament shelved it) have a
  visible before/after but a *reversed* outcome; not clean success A/Bs. They are arguably the
  more interesting cases for the falsifier above (Scrum-shaped process, FM it didn't guard won).
- **Containment vs causation.** Track B proved containment (parts map). This doc argues
  *causation* at case-study level (which part fixed which FM). That is a step up in claim and a
  step down in rigor — treat as worked examples, not proof.
