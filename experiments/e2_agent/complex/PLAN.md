# E2 dataset — PLAN (10 decomposition-quality tasks)

> Experimenter-side document. **Subject agents never read this** (isolation, see `../README.md`).
> This is the PLAN + justification only. The reference decompositions themselves are built **later**,
> with the full GFSO verification cycle. Do NOT build references here.

## 1. Purpose & metric

This dataset is a **neutral measuring instrument**. It fixes **10 single-meta-level design/analysis tasks**;
for each we will later build one **complete, categorized reference decomposition** via the full GFSO cycle.
The references are the yardstick — a fully-populated GFSO decomposition per canonical category. E2 then
**measures** the per-category coverage (joint sufficiency, §2.2.1) and non-redundancy (§2.2.2) of ANY
decomposition — a BARE agent (task only), a GFSO agent (task + the Constitution `docs/method_gfso.md`), or a
human — scored against the reference. **We do not presuppose which categories any agent populates or fails;
that is precisely what E2 measures, not what the dataset asserts.** The tasks below are described only by
their own GFSO-category richness (what the task contains), never by a prediction about any agent's behaviour.

Both correctness conditions are GFSO's own, from canon §2.2, applied **per item-category**:

- **coverage = joint sufficiency** (§2.2.1): per category of required items (sub-goals/passes,
  cross-component interaction-seams, global invariants, NEGLECTED assumptions, failure-modes, edge-cases),
  how many of the reference's canonical items the agent's decomposition closes. A missing required item =
  a coverage hole (FM-1).
- **non-redundancy** (§2.2.2): how many distinct agent-points collapse onto one canonical reference item
  (e.g. 5 near-duplicate points → 1 reference item = a precision penalty / ballast).

### 1.1 What the instrument resolves on — category-structure, NOT raw density

The measurement axis is **not domain knowledge** (assume a competent Opus-4.8 agent already knows each
domain) and it is **not recall on a long list of pairs**. The signal GFSO objectifies (§17.4–§17.5) is a
**categorized, COMPLETE and NON-REDUNDANT** basis. So the reference, and the per-category scoring against
it, resolve a decomposition along the canonical GFSO categories — independent of who produced it:

- **C — components / sub-goals** (the parts / passes);
- **X — Dep-seams: cross-component dependencies written AS explicit, separately-falsifiable Dep edges**
  (§2.2; not "these parts relate" prose, but a named edge with its own truth-maker / criterion — Ст. I.8,
  II.5);
- **I — invariants: parent criteria spanning children** (§2.2 joint sufficiency / §3.1; cross-cutting
  correctness conditions, not per-part checks);
- **N — NEGLECTED: declared scope-exclusions / out-of-scope assumptions** (STD-1, §5; Ст. I.10, II.6);
- **F — failure-modes: the 7 FM classes** (§4), phrased as concrete coverable couplings (§1.3 rule 4).

Therefore each task below states **which canonical categories the task is rich in, with an approximate
item count per category** — a neutral property of the task itself, NOT a prediction that any agent omits or
under-populates any of them. Interaction density is a *necessary backdrop* (so a task has enough real X/I/N
content for coverage to be measurable), **not a metric**. We do not equate raw pair-count with completeness,
and we do not target any C(n,2) / "N²" upper bound anywhere.

### 1.2 Real seams, not nominal pairs (anti-mock count)

Per Ст. II.5 (anti-mock), a **real seam** is an edge where the *output of one node feeds the input of
another and the edge is separately falsifiable* — distinguished from a **nominal pair** (two parts that
merely co-exist but do not exchange a truth-maker). For every task we state the interaction count as the
**REAL cross-component seam set** that survives this anti-mock filter, NOT the pairwise upper bound. The
real seam set for these tasks is far below the pairwise count; most capability pairs do not exchange a
truth-maker. Reference builders list **only** real seams. Any per-task seam count below is the post-filter
real-seam count, not an enumeration cap.

### 1.3 Seam-canonicalization rule (objective coverage & non-redundancy)

Before scoring, every category of the reference is **canonicalized** so coverage and non-redundancy are
objective across near-duplicates:

1. **Group by truth-maker, not by phrasing.** Two seam items are the **same** canonical seam iff they have
   the same *real adjacent pair* and the same falsifying criterion (Ст. II.5). "Proration on plan-change"
   and "credit on downgrade" that break under the *same* money-conservation invariant on the *same* node
   pair collapse to **one** canonical seam. Different node pair or different falsifier ⇒ distinct seams.
2. **Invariants canonicalize by the conserved quantity / enforced predicate**, not by where it is checked
   (one "debits = credits per currency" invariant, however many spokes touch it).
3. **NEGLECTED items canonicalize by the assumption being excluded**, each carrying a
   `predictability_verdict` (Ст. I.10); two phrasings of the same excluded assumption = one item.
4. **Failure-modes are phrased as concrete coverable claims**, never qualitative adjectives: a reference
   F-item reads "names the autoscale-vs-ratelimit double-correction AND assigns an arbiter", not "avoids
   flapping". An agent point covers it iff it names the same concrete coupling and its resolution.
5. **Coverage match = canonical-item match.** An agent item covers a reference item iff it maps to the
   **same** canonical item under (1)–(4). Multiple agent items mapping to one canonical item ⇒ one
   coverage credit + a non-redundancy penalty (§2.2.2). No partial credit; binary per canonical item.

This rule is what makes X-, I-, F- and N-coverage binary rather than subjective across synonyms.

Each task obeys the fitness criteria: single meta-level (one agent's decomposition scope, NOT a hierarchy
of delegated sub-projects owned by different functions = E3); a real interaction backbone rich in the
canonical X/I/N categories; competent-domain (not OOD; an auditor can validate the reference);
objectively-decidable items so the reference binary-scores.

## 2. Coverage matrix (diversity proof — no repeated cell)

Axes: **Domain family** (≥6 distinct) · **Interaction topology** (pairwise-dense / chained-pipeline /
hub-and-spoke / cyclic-maintenance / layered) · **Goal type** (achievement→tree/terminates vs
maintenance→cycle/persists; **≥3 maintenance**).

| Task | Domain family | Topology | Goal type | Categories the task is rich in (with the dominant ones) |
|---|---|---|---|---|
| T01 | Software / business-logic (billing) | pairwise-dense | achievement | I (global money/ledger invariants) + N (rounding/tax/fraud exclusions) |
| T02 | Data / ML (training+serving pipeline) | chained-pipeline | achievement | X (data-contract seams) + I |
| T03 | Systems / infra-ops (zero-downtime DB migration) | layered | achievement | I (cross-layer compat) + E (per-phase rollback) |
| T04 | Finance / accounting (multi-currency close & reconciliation) | hub-and-spoke | achievement | X (ordering seams) + I (balance) |
| T05 | Site-reliability / on-call (keep a tier-1 service within SLO) | cyclic-maintenance | **maintenance** | X (mitigation×mitigation) + F |
| T06 | Infra / data-ops (backup & disaster-recovery regime) | hub-and-spoke | **maintenance** | **N (declared scope-exclusions)** + F |
| T07 | Software / systems (concurrent in-memory cache/store) | pairwise-dense | achievement | X (concurrency seams) + I (consistency) |
| T08 | Software / compilers (front-end pipeline) | chained-pipeline | achievement | X (exact inter-stage contracts) + I |
| T09 | Security / access-control (multi-tenant authz model) | layered | achievement | X (escalation seams) + I (isolation) |
| T10 | Operations / facilities (greenhouse climate-control regime) | cyclic-maintenance | **maintenance** | X (actuator coupling) + F |

**Cell-uniqueness check.** No two rows share the same (Domain, Topology, Goal) triple. Domain families:
software-logic, data/ML, infra-ops, finance, SRE, data-ops/DR, systems-concurrency, compilers, security,
facilities = **10 distinct families** (≥6 ✓). Topologies present: pairwise-dense ×2 (T01, T07),
chained-pipeline ×2 (T02, T08), layered ×2 (T03, T09), hub-and-spoke ×2 (T04, T06), cyclic-maintenance ×3
(T05, T06 shares hub-shape but is cyclic-maintenance, T10) — every topology ≥1 ✓. **Maintenance/cyclic:
T05, T06, T10 = 3** ✓. Within-topology twins differ in **defect-class**, not just domain skin (audited
in §4(a)).

Item-categories used across the set (per-task counts in §3): **C = components/sub-goals (passes)**,
**X = real cross-component interaction seams (Dep edges)**, **I = global invariants/correctness
conditions**, **E = edge-cases / boundary states**, **F = failure-modes (phrased as concrete coverable
couplings)**, **N = NEGLECTED assumptions/exclusions**. Every task carries C, X, I and at least two of
{E, F, N}; maintenance tasks emphasize I + F (viability); T06 emphasizes N.

---

## 3. The 10 tasks

> Statements below are the experimenter's scoping notes (with category counts). The **pristine** agent-facing
> text (no rationale, no category hints — leak-free) lives as the per-task input `tasks/T0X.md` (one pristine file per task). Each
> statement is scoped to **design the logic / specify how parts connect**, never "plan and execute / staff /
> deliver" — the wording mitigation against E3 drift is kept in the pristine text.

### T01 — Subscription billing logic
**Statement.** Design the *billing logic* (the rules of what to charge a customer and when — not the
infrastructure, not the project) that stays correct under any co-existence of: monthly & annual plans,
mid-period plan change with proration, trial→paid conversion, full & partial refunds, account
credits/balance, country-dependent tax, failed charges & dunning retries, cancellation & reactivation,
pause & resume. Decompose this task.
**Real seams (anti-mock).** Billing seams cluster around **two truth-makers**: (i) money-conservation
(proration ↔ refund ↔ credit ↔ tax must net correctly on a single event) and (ii) state-machine
transitions (pause/cancel/reactivate × proration boundary; trial-convert × dunning). After the §1.2 filter
and §1.3 canonicalization, that is **~8–12 genuine seams**, far below the pairwise upper bound. Most
capability pairs (e.g. annual-plan × tax-jurisdiction, trial × pause) do not exchange a truth-maker and are
nominal, not real, seams.
**Justification & richness.** Achievement goal (a correct rule-set, terminates), pairwise-dense
topology. Billing-with-proration is the **single most-blogged decomposition example** on the web, so the
*component* and even *pair* list is widely recalled — T01 therefore serves as a **calibration task** (its
seam count is not a density discriminator). Where billing is genuinely rich is in **I and N**: the *global*
invariants that span all capabilities (money conservation across credit↔refund, idempotency of retry,
monotonic invoice ledger, tax-at-event-time) and the NEGLECTED policy items (proration rounding policy,
tax engine external, fraud out-of-scope). Those are the categories the reference is densest in.
**Rich-in categories:** **I** (global money/ledger invariants) and **N** (rounding/tax-engine/fraud
exclusions), atop a saturated C and a real (recall-friendly) X.
Categories: **C ≈ 9**, **X ≈ 8–12** (real money-conservation + state-machine seams, canonicalized),
**I ≈ 8** (money conservation, retry idempotency, monotonic ledger, tax-at-event-time), **E ≈ 8**
(mid-period boundary, zero/negative balance, jurisdiction change mid-cycle), **N ≈ 5** (rounding policy,
tax engine external, fraud out-of-scope).
**Cell.** software/business-logic · pairwise-dense · achievement.

### T02 — ML training + serving pipeline (design)
**Statement.** Design the end-to-end logic of a supervised-model pipeline from raw labeled data to a served
prediction endpoint: ingestion & schema validation, feature transforms, train/val/test split, training,
offline evaluation, model registry/versioning, the serving transform path, online inference, and
monitoring. Specify how the stages connect so the *served* model is correct and the offline score predicts
online behavior. Decompose this task.
**Justification & richness.** A **chained pipeline** where the dominant content is *seam* structure, not
stage structure: train/serve feature-transform skew, train/test leakage across the split, schema drift
between ingestion and inference, registry version↔serving binding, eval-metric↔monitoring alignment. These
are **real seams** (output of one stage is the input of another, each individually falsifiable) — the task
is rich in the **inter-stage X category**: each edge carries a named contract on top of the stage list C.
**Rich-in categories:** **X** (directed data/contract seams) and the few global **I** (no leakage,
train/serve parity).
Categories: **C ≈ 9** (stages), **X ≈ 14** (stage→stage data/contract seams, named & individually
falsifiable), **I ≈ 6** (no leakage, train/serve parity, reproducible split, version pinning), **F ≈ 6**
(skew, leakage, silent schema drift, stale model), **N ≈ 4** (label quality assumed, infra/autoscaling
out-of-scope). *Reference-builder note:* do not double-count an F-item that is the negation of an X-seam.
**Cell.** data/ML · chained-pipeline · achievement.

### T03 — Zero-downtime production DB schema migration (design)
**Statement.** Design the *procedure and the invariants* to evolve a relational schema under a
backward-incompatible change (e.g. split a column into a new table) on a live, high-traffic service with
rolling deploys and no downtime: expand/contract phases, dual-write & backfill, read-path switch,
app-version compatibility windows, the rollback path at each phase, and post-migration cleanup. **Design
the migration logic, do not execute it.** Decompose this task.
**Justification & richness.** **Layered** ordering: phases must hold *across layers* (schema ↔ app
code ↔ data ↔ deploy fleet) simultaneously. The task is rich in the **cross-layer compatibility
invariant** (old AND new code each work against every intermediate schema) and the **per-phase rollback**
edge-cases — i.e. dense I and E content atop the phase list C. The seam count is the real phase→phase +
layer-coupling edges (~10–12), not a pairwise product.
**Rich-in categories:** **I** (the old/new-code × intermediate-schema compatibility matrix) and
**E** (per-phase rollback), atop a phase list C.
Categories: **C ≈ 7** (phases), **X ≈ 10–12** (phase→phase + layer-coupling seams), **I ≈ 7** (each
intermediate state readable+writable by both app versions, backfill idempotent, no lost writes), **E ≈ 8**
(rollback at each phase, partial-backfill crash, long-running txn), **N ≈ 4** (replica-lag bound assumed,
no schema-change-during-incident).
**E3 check.** Pristine text says *design the procedure/invariants*, never *coordinate the deploy across
teams*. Single agent, single design scope.
**Cell.** infra-ops · layered · achievement.

### T04 — Multi-currency month-end financial close & reconciliation (design)
**Statement.** Design the logic of a month-end close for a company operating in several currencies:
sub-ledger→general-ledger posting, FX revaluation, intercompany elimination, accruals & deferrals,
bank/sub-ledger reconciliation, and producing a trial balance that nets to zero. Specify the rules and
their ordering so the close is correct and auditable. Decompose this task.
**Statement-shape.** A **hub-and-spoke** flow: the general ledger / trial balance is the hub; each spoke
(FX, intercompany, accruals, reconciliation, sub-ledgers) feeds it and the hub-level invariant (debits =
credits, nets to zero, in every currency and consolidated) constrains all spokes jointly.
**Justification & richness.** The **best-decidability task in the set**: invariants are *arithmetic*
(debits=credits, nets-to-zero per currency and consolidated, elimination completeness) → genuinely binary.
The real seams are **spoke→hub posting** plus **cross-spoke ordering** (FX-revaluation precedes
consolidation; intercompany elimination nets before trial-balance) — order-bearing Dep edges, ~10–12 real,
not a pairwise product. The task is rich in those **ordering edges** and in the **global balance invariant**
atop the spoke/hub list.
**Rich-in categories:** **X** (cross-spoke ordering seams) and **I** (the consolidated balance invariant).
Categories: **C ≈ 6** (close components), **X ≈ 10–12** (spoke→hub + cross-spoke ordering seams), **I ≈ 7**
(double-entry balance, currency conservation, period cutoff, elimination completeness), **E ≈ 6** (rate at
cutoff vs spot, partial-period entity, late adjustment), **N ≈ 4** (rate source authoritative, tax filing
out-of-scope).
**Cell.** finance/accounting · hub-and-spoke · achievement.

### T05 — Keep a tier-1 service within SLO (on-call regime design) [MAINTENANCE]
**Statement.** Design the operating regime that keeps a tier-1 service continuously within its SLO
(latency + error-budget) across normal load, traffic spikes, dependency degradation, and partial outages:
the monitored signals, alerting thresholds, the load-shedding / autoscaling / failover responses, the
escalation path, and how responses interact so one mitigation does not break the SLO via another axis.
Decompose this task.
**Justification & richness.** **Cyclic-maintenance / viability** goal: the system must *persist*
inside the SLO viability region (§18.10.0 cycle↔tree). The task is rich in **mitigation×mitigation
interactions** (autoscale vs rate-limit double-correction, retry-storm vs load-shed, failover vs
cache-warmth, alert-threshold vs autoscale-hysteresis) — real coupling seams atop the response list — plus
a dense **F category** (named, resolved failure-modes).
**Decidability (per §1.3 rule 4).** Each F-item is phrased as a **concrete coverable coupling**, e.g.
"names autoscale-vs-rate-limit double-correction AND assigns an arbiter", "names retry-storm-vs-load-shed
AND a back-pressure rule" — NOT "avoids flapping". This keeps F-coverage binary.
**Rich-in categories:** **X** (mitigation-coupling seams) and **F** (named, resolved failure-modes).
Categories: **C ≈ 7** (signal sets + response mechanisms), **X ≈ 12** (response×response + signal→response
seams), **I ≈ 6** (SLO never violated by a mitigation, error-budget monotonic, bounded hysteresis), **F ≈ 8**
(retry storm, thundering herd, failover loop, alert fatigue — each as a coverable coupling), **N ≈ 3**
(single-region assumed, capacity ceiling fixed). Maintenance emphasis: I + F dominate.
**Cell.** SRE/on-call · cyclic-maintenance · maintenance.

### T06 — Backup & disaster-recovery regime (design) [MAINTENANCE · NEGLECTED-load-bearing]
**Statement.** Design the operating regime that continuously keeps a production data estate **recoverable**
within stated RPO/RTO targets: which data stores and state are in scope, the backup cadence and retention
tiers, the restore/failover procedure, periodic restore-drills, and the integrity/freshness checks that
keep the regime viable over time. Specify the rules so a recovery would actually succeed. Decompose this
task.
**Statement-shape.** **Hub-and-spoke**, cyclic: a central recovery catalog/runbook is the hub; each spoke
(a data store, a secret/credential set, a config source, an external dependency) must be enrolled, and the
hub-invariant (everything required to reconstitute the service is captured and restorable) couples them on
every cycle.
**Justification & richness — NEGLECTED is the dominant category.** This task is engineered so the **densest
category is N (declared scope-exclusions / out-of-scope assumptions)**, the GFSO category currently
under-exercised elsewhere in the set (Ст. I.10 / II.6; §17.5 "no invisible blind spot"). A recovery regime
is correct **only if what it does NOT cover is declared**: secrets/KMS keys assumed restorable elsewhere,
DNS/external SaaS state assumed re-creatable, in-flight queue messages excluded, clock/cert state, IAM/policy
state, the "backups are useless if untested" restore-drill assumption, the implicit "the backup region
itself survives the disaster" assumption. The reference is rich in this **NEGLECTED frontier** — the silent
assumptions whose failure makes a documented restore fail in practice — atop the **backup mechanics C**
(cadence, retention, snapshots). Each N-item carries a `predictability_verdict`. The cyclic restore-drill
makes it a maintenance (viability) goal, not a one-shot.
**Rich-in categories:** **N** (the declared exclusions/assumptions — dominant) and **F**
(silent-restore-failure modes the exclusions correspond to).
Categories: **C ≈ 6** (in-scope stores + backup/restore/drill mechanisms), **X ≈ 8** (spoke→hub enrollment
+ cross-spoke restore-ordering seams), **I ≈ 4** (every required artifact captured, restore reproduces
service, RPO/RTO bound holds), **F ≈ 6** (restore-drill never run, secret/key not backed up, backup region
co-fails, partial-restore inconsistency), **N ≈ 8** (DNS/SaaS state, secrets/KMS, in-flight messages,
IAM/policy, certs/clocks, backup-region survival, ransomware/immutability scope, cost ceiling — each with
`predictability_verdict`). **N is the dominant, load-bearing category.**
**E3 check.** Scoped to *design the regime's logic and assumption-frontier*, not to *run DR across teams*.
**Cell.** infra/data-ops · hub-and-spoke · maintenance.

### T07 — Concurrent in-memory cache / key-value store (design)
**Statement.** Design the logic of a concurrent in-memory cache/store used by many threads or nodes:
the read/write path, an eviction policy, per-entry TTL/expiry, write-through or write-back persistence
backing, invalidation on update, and sharding/partitioning. Specify how these mechanisms interact so the
store stays consistent and bounded under concurrent access. Decompose this task.
**Justification & richness.** **Pairwise-dense** with **constraint coupling that is fully in-zone for
a coding-grade agent** (no specialist hardware knowledge — this replaces the OOD battery-pack task). The
mechanisms genuinely couple: eviction × TTL (which fires first on a contended entry), eviction × write-back
(evicting a dirty entry must flush, not drop), TTL × write-back (expiry of unflushed data = lost write),
invalidation × read (no stale read after a committed write), sharding × invalidation (cross-shard
invalidation ordering), concurrency × every pair (lost update, torn read). These are **real seams** with
**binary invariants**: *no stale read after a committed write, no lost write, bounded memory, no double-free
on eviction*. The task is rich in the **concurrency-coupling seams X** and the **global consistency
invariants I** atop the **mechanisms C**.
**Distinctness from T01 (the other pairwise-dense task).** Different **defect-class**, not just domain
skin: T01's coupling is **money-conservation over a state-machine** (sequential, value-conserving); T07's
coupling is **concurrency/consistency over shared mutable state** (interleaving-sensitive, race-bearing).
T07 absorbs the concurrent-mutation defect-class formerly carried by the warehouse hub task. The two
pairwise-dense tasks share only the *topology word*, not the failure family.
**Rich-in categories:** **X** (concurrency-coupling seams) and **I** (consistency/boundedness invariants).
Categories: **C ≈ 6** (read/write path, eviction, TTL, persistence, invalidation, sharding), **X ≈ 12**
(mechanism×mechanism coupling seams under concurrency), **I ≈ 6** (no stale read after commit, no lost
write, bounded memory, no double-free, dirty-entry flush before evict), **E ≈ 6** (evict-during-write,
TTL-expiry-of-dirty, cross-shard invalidation race), **F ≈ 5** (lost update, stale read, unbounded growth),
**N ≈ 3** (durability of the backing store assumed, network partition handling out-of-scope).
**Cell.** software/systems · pairwise-dense · achievement.

### T08 — Compiler front-end pipeline (design)
**Statement.** Design the end-to-end logic of a compiler front-end for a small statically-typed language:
lexing, parsing, name/scope resolution, type-checking, lowering to a typed intermediate representation
(IR), and code generation. Specify the **contract each stage must satisfy for the next** so the produced
code is well-formed. Decompose this task.
**Justification & richness.** **Chained-pipeline** whose load-bearing items are **exact, decidable
inter-stage contracts** — the OPPOSITE of the replaced hiring task's soft fairness items. Each seam is a
precise predicate: lexer output is a well-formed token stream the parser accepts; parser output is a tree
satisfying the grammar; resolution binds every name or errors; every IR node is well-typed; no later pass
invalidates an invariant established by an earlier one (e.g. lowering preserves type-correctness). These
are **real, individually-falsifiable seams** and **fully in-zone** for a coding-grade agent. The task is
rich in the **inter-stage contract X** and the **pipeline-wide invariants I** (every IR node well-typed; no
pass breaks a prior invariant) atop the **stage list C**.
**Distinctness from T02 (the other chained task).** Different **seam type**: T02's contracts are
**statistical/data** (distribution skew, leakage — probabilistic, monitored) while T08's are **exact formal
contracts** (well-typedness, grammar-conformance — decidable, provable). No redundancy; complementary ends
of the decidability spectrum.
**Rich-in categories:** **X** (exact inter-stage contracts) and **I** (pass-invariant preservation).
Categories: **C ≈ 6** (stages), **X ≈ 10** (stage→stage exact contracts), **I ≈ 6** (every IR node
well-typed, every name resolved, no pass invalidates a prior invariant, source-position preserved for
diagnostics), **E ≈ 6** (recovery on lex/parse error, forward reference, shadowing/scope edge), **F ≈ 4**
(ill-typed IR escapes, dropped error, invalidated invariant), **N ≈ 4** (optimization/backend out-of-scope,
single source file assumed, no macro/preprocessor).
**E3 check.** One agent designs one front-end's logic; stages are *contracts*, not delegated sub-projects.
**Cell.** software/compilers · chained-pipeline · achievement.

### T09 — Multi-tenant authorization model (design)
**Statement.** Design the access-control logic for a multi-tenant SaaS: the principal/role/permission model,
tenant isolation, resource hierarchy & permission inheritance, delegation/impersonation (e.g. support
acting as a user), API-key & service-account scoping, and the audit trail. Specify the rules so that no
principal can ever reach a resource outside its grants or its tenant. Decompose this task.
**Statement-shape.** **Layered** authz: each layer (authentication → tenant scoping → role/permission →
resource-hierarchy inheritance → delegation) must compose so the *conjunction* enforces isolation; the hard
items are the **cross-layer leak conditions** (inheritance × delegation × tenant-boundary).
**Justification & richness.** The dominant content is **privilege-escalation paths *created by
interaction*** — delegation crossing a tenant boundary, inherited permission overriding a deny,
service-account scope vs impersonation, audit gaps. The task is rich in these emergent **cross-layer seams**
atop the component list, and the invariants are **crisp and binary** ("no principal reaches a resource
outside its grants/tenant"). Competent-domain (every coding agent knows SaaS authz).
**Distinct from T03** (also layered) by defect-class: escalation-path vs compatibility-window.
**Rich-in categories:** **X** (cross-layer escalation seams) and **I** (the isolation invariant).
Categories: **C ≈ 6** (authz components), **X ≈ 12** (cross-layer composition/leak seams), **I ≈ 7**
(tenant isolation, deny-overrides-allow or stated precedence, least privilege, every access audited),
**E ≈ 8** (impersonation across tenant, orphaned resource, inherited grant on moved resource), **F ≈ 6**
(privilege escalation, confused-deputy, audit gap), **N ≈ 3** (identity provider trusted, network-layer
security out-of-scope).
**Cell.** security/access-control · layered · achievement.

### T10 — Greenhouse climate-control regime (design) [MAINTENANCE]
**Statement.** Design the control regime that keeps a commercial greenhouse continuously within the crop's
viable envelope (temperature, humidity, CO₂, light, irrigation) across day/night and weather swings: the
sensed variables, the actuators (heating, ventilation, shading, CO₂ injection, irrigation, supplemental
light), and the rules coupling them so that correcting one variable does not push another out of bounds.
Decompose this task.
**Justification & richness.** **Cyclic-maintenance / viability** goal: the regime must *hold* the
state inside the viability kernel indefinitely (§18.10.0), regenerating corrective sub-tasks each cycle.
The task is rich in **actuator-coupling interactions**: ventilation cools but vents CO₂ and drops
humidity; CO₂ injection conflicts with venting; shading lowers temp but cuts photosynthesis; irrigation
raises humidity vs ventilation — real cross-actuator seams atop the actuator list.
**Decidability (per §1.3 rule 4).** F- and X-items are phrased as **concrete coverable couplings**, e.g.
"names vent-cools-but-vents-CO₂ AND a coordination rule", not "avoids instability". The coupling structure
is physics a generalist reasons about from the actuator list, so the category richness is in completeness
of the coupling structure, not exotic agronomy.
**Distinct from T05** (also cyclic) by coupling physics: continuous-physical actuator conflict vs
discrete-event SRE mitigation conflict.
**Rich-in categories:** **X** (actuator-coupling seams) and **F** (named coupling failures).
Categories: **C ≈ 6** (sensed-variable loops + actuators), **X ≈ 12** (actuator×variable cross-coupling
seams), **I ≈ 6** (each variable within envelope, no actuator-induced out-of-bound on another, energy
bound), **F ≈ 6** (actuator-fights-actuator, sensor failure, runaway humidity→disease — each as a coverable
coupling), **N ≈ 3** (crop model fixed, pest control out-of-scope, grid power assumed). Maintenance
emphasis: I + F dominate.
**Cell.** facilities/agriculture · cyclic-maintenance · maintenance.

---

## 4. Diversity & fitness self-audit

I critiqued the set against the failure modes the prompt warns about, then resolved.

**(a) Any two tasks the same shape?** Topology repeats in pairs/triples — flagged and distinguished by
**defect-class**, not domain skin:
- pairwise-dense **T01** (money-conservation over a sequential state-machine) vs **T07** (concurrency/
  consistency over shared mutable state — interleaving-sensitive races). Different failure family. ✓
- chained **T02** (statistical/data contracts: skew, leakage) vs **T08** (exact formal contracts:
  well-typedness, grammar-conformance). Opposite ends of the decidability spectrum. ✓
- layered **T03** (temporal compatibility-window across layers, *completes*) vs **T09** (enforcement
  invariant that *holds* on every access — escalation paths). ✓
- hub-and-spoke **T04** (balanced ledger, arithmetic, achievement, no concurrency) vs **T06** (recovery
  catalog hub, cyclic-maintenance, N-dominant). Different goal-type AND dominant category. ✓
- cyclic **T05** (discrete-event SRE mitigation coupling) vs **T06** (assumption-frontier recoverability)
  vs **T10** (continuous-physical actuator coupling). Three different defect families. ✓
No two tasks share a (domain, topology, goal) cell, and within-topology pairs differ in defect-class.
**Resolved: no clones; the former T01/T07 "pairwise twins in costumes" risk is closed by the cache swap.**

**(b) Does any task drift into an E3 hierarchy?** The two former E3 risks are removed/hardened:
- **T08 (hiring) REPLACED by compiler front-end** — stages are now *exact contracts* between passes of one
  agent's single design, not org-handoffs owned by different functions. E3 drift eliminated at the source.
- **T03 (migration)** scoped explicitly to *design the procedure/invariants*, with an E3-check line; the
  pristine text says nothing about coordinating teams.
- **T06 (DR)** scoped to *design the regime's logic and assumption-frontier*, not run DR.
- **T02 (pipeline)** scoped to *the connective design* (stage contracts), one meta-level.
**Resolved: all single meta-level.**

**(c) Resolving on the right axis (category-structure, not raw density)?** Each task now names the
**canonical categories it is rich in** (§2 matrix, last column) — a property of the task content, NOT a
prediction about any agent: I+N (T01), X+I (T02/T04/T08/T09), I+E (T03), X+F (T05/T10), N+F (T06). Density
is the *backdrop* that makes per-category coverage measurable, never a metric. The saturation-prone famous
task (T01) is a **calibration task**; its richness is in I+N. **Resolved: the measurement axis is
category-structure throughout, asserted of the tasks, not of any agent.**

**(d) Competent-domain (not OOD)?** The OOD violation is removed: **battery-pack REPLACED by concurrent
cache/store**, fully in-zone for a coding-grade agent, with a reference an auditor can validate (consistency
invariants, not EV-physics). Every remaining domain (billing, ML, DB migration, financial close, SRE, DR,
cache, compilers, authz, greenhouse) is standard generalist knowledge; T10's agronomy is reduced to
actuator-coupling physics a generalist reasons about. **Resolved: no OOD, all references auditable.**

**(e) Objectively decidable items?** Canonicalization (§1.3) makes coverage binary: an agent item covers a
reference item iff it maps to the **same canonical item** (same truth-maker / conserved quantity / excluded
assumption). Soft failure-modes (T05, T10) are phrased as **concrete coverable couplings** (rule 4), not
adjectives. Hard-binary tasks (T04 arithmetic, T08 well-typedness, T09 logical) anchor the high-decidability
end. **Resolved: binary-scorable via canonicalization; the decidability bimodality is acknowledged and the
soft end is phrased to stay coverable.**

**(f) Goal-type balance.** **3 maintenance/cyclic** (T05, T06, T10) vs 7 achievement — the lopsided 2/8
is fixed (must-fix #7). The cycle goal-type now also carries the NEGLECTED-load-bearing task (T06).

**(g) NEGLECTED-completeness exercised?** **T06 is engineered so N is the dominant category** (N≈8, each
with `predictability_verdict`) — the GFSO category otherwise under-exercised in the set (Ст. I.10 / II.6,
§17.5). **Resolved: NEGLECTED is the dominant category on at least one task, so per-category N-coverage is
measurable.**

**Resolved status: PASS.** 10 tasks, 10 domain families, all 5 topologies, **3 maintenance**, unique cells,
all single-meta-level, all competent-domain and binary-scorable via the seam-canonicalization rule, each
with explicit *rich-in* canonical categories and a real (anti-mock) seam count.
Ready for reference-building (later step).

---

## Revision log

Mapping of each critique must-fix to its resolution.

1. **T07 battery-pack REPLACED** (OOD / un-auditable reference) → **T07 concurrent in-memory cache/store**.
   In-zone for a coding-grade agent, physical-constraint-coupled (keeps the pairwise-dense slot), binary
   invariants (no stale read after commit, no lost write, bounded memory) an auditor can validate. The OOD
   domain-recall confound and the un-auditable-reference problem are removed. (§3 T07, §4(d).)

2. **T08 hiring-pipeline REPLACED** (E3 drift + soft/non-decidable) → **T08 compiler front-end**
   (lex→parse→resolve→typecheck→IR→codegen). Each inter-stage seam is an **exact, decidable contract**
   (well-typedness, grammar-conformance, pass-invariant preservation); stages are passes of one agent's
   design, not org-handoffs owned by different functions. Kills both E3 and the soft-decidability problem.
   (§3 T08, §4(a)/(b).)

3. **T01 billing FIXED** (saturation + inflated density). Cut X from the C(9,2)=36 upper bound to the
   **real ~8–12 seam set** (money-conservation + state-machine truth-makers), added the canonicalization
   note inline, and **re-pointed the discriminator to I + N** (global invariants + NEGLECTED) where billing
   actually separates. Explicitly demoted to **calibration, not a load-bearing density discriminator**, with
   the run-2 saturation risk named. (§3 T01.)

4. **Core re-orientation (ALL tasks): density → category-structure.** Added §1.1 (what discriminates =
   categories a bare agent structurally omits: X seams-as-edges / I global invariants / N NEGLECTED, while it
   saturates C) and §1.2 (real seams vs nominal pairs, anti-mock per Ст. II.5). Every task now states its
   interaction count as the **real cross-component seam set** (post-filter, below n²/2) and names **which
   category the bare agent structurally omits** (new matrix column in §2, per-task "Bare agent structurally
   omits" line in §3). Removed all "≈N² (≈25–35) seams" upper-bound targets.

5. **Seam-canonicalization rule ADDED** (§1.3): canonicalize by truth-maker (seams), conserved
   quantity/predicate (invariants), excluded assumption (NEGLECTED); failure-modes phrased as concrete
   coverable claims; coverage match = canonical-item match, binary, with non-redundancy penalty for many→one.
   This makes X/I/F/N coverage objective across near-synonyms (closes the §0.3 / item-3 critique threat for
   T01/T02/T05/T10).

6. **NEGLECTED-load-bearing task ADDED** → **T06 backup & disaster-recovery regime**, engineered so **N is
   the dominant category** (N≈8, each with `predictability_verdict`): the silent assumptions (secrets/KMS,
   DNS/SaaS state, in-flight messages, backup-region survival, restore-drill) whose omission makes a
   documented restore fail. Tests the previously-untested GFSO differentiator (Ст. I.10 / II.6, §17.5).
   (§3 T06, §4(g).)

7. **Goal-type rebalanced to 3 maintenance** (T05 SLO, T06 DR, T10 greenhouse) vs 7 achievement, fixing the
   lopsided 2/8. T06 doubles as the new maintenance task and the NEGLECTED carrier (DRY). (§2, §4(f).)

8. **Strong tasks KEPT** (T02 ML-pipeline, T04 reconciliation, T09 authz) and the caveated keeps (T03
   migration with E3-wording check, T06's predecessor concurrency value relocated, T10 greenhouse with
   concrete-coupling F-phrasing). T03/T08/T06 carry explicit E3-check lines; T05/T10 F-items are phrased as
   coverable couplings per §1.3 rule 4.

**Secondary critique items also resolved:** seam-canonicalization (#4 in critique's secondary list → §1.3);
NEGLECTED task (#5 → T06); soft-F phrasing for T05/T10 (#6 → §1.3 rule 4 + per-task decidability notes);
T01/T07 pairwise-twin distinctness re-confirmed by **defect-class** (money-conservation-state-machine vs
concurrency-consistency), not domain skin (#7 → §4(a)).

**Residual concerns (for the reference-building step, not blockers):**
- **Decidability bimodality persists by design.** T04/T08/T09 are hard-binary; T05/T06/T10 stay softer even
  after concrete-coupling phrasing. The judge should weight soft-category coverage (F on T05/T10, some N on
  T06) as noisier signal, or the reference must be especially disciplined in phrasing those items.
- **Hub-and-spoke count dropped to 2 of the original "×2 each topology"** because T06 is now cyclic-
  maintenance; topology coverage still has all 5 present and every cell unique, but the symmetry of two
  achievement hubs (old T04+T06) is traded for the maintenance/NEGLECTED gain. Judged worth it.
- **F-vs-X double-counting** (a failure that is the negation of a seam) remains a reference-builder hazard on
  T02/T05/T07/T10 — flagged inline; the reference must not credit the same defect twice.
- **T06 reference auditability**: the NEGLECTED frontier is broad; the auditor must ensure the canonical
  N-list is the *genuinely-required* exclusions, not an open-ended "anything could be assumed" list, or
  N-coverage becomes unfalsifiable (the same inflation risk, moved from X to N). Cap N to assumptions whose
  failure provably breaks the documented restore.

---

**9. Neutralization pass — removed two biased framings (supersedes entries 1–8 where they conflict).**
Two framings pre-judged the experiment and were removed so the dataset stays a neutral instrument:
- **"N²-density" dropped as a metric.** "N² / C(n,2)" is not a canon quantity — it is a loose combinatorial
  upper bound, and most component pairs share no truth-maker. Every interaction count is now stated as the
  **real-seam count** — genuine cross-component dependencies, each with an identifiable §2.2 Dep truth-maker,
  after the §1.2 anti-mock filter and §1.3 canonicalization. Residual "C(9,2)=36 / pairwise" mentions are
  kept only as the bound we explicitly do NOT target.
- **A-priori "what a bare agent structurally omits" removed.** Whether any agent under-populates a category
  is the experiment's HYPOTHESIS — what E2 MEASURES — not a property of the task. Baking it into task design
  pre-judged the result and biased the test toward GFSO (the sin of the prior failed runs). Replaced
  throughout (preamble §1/§1.1, the §2 matrix column, every per-task "Rich-in categories" line, the §4(c)/(g)
  self-audit, the PASS summary) with a **neutral description of the task's own GFSO-category richness** —
  which canonical categories (**Dep-seams** §2.2 · **invariants** §2.2/§3.1 · **NEGLECTED** STD-1/§5 ·
  **failure-modes** §4) the task is rich in, with approximate per-category item counts. The preamble now
  states explicitly that E2 measures per-category coverage + non-redundancy of ANY decomposition (agent or
  human) against the references and presupposes nothing about which categories any agent fails.
*Unchanged:* the set of 10 tasks (none added/removed), the coverage matrix, the §2.2 metric, the
seam-canonicalization rule, and the §4 fitness/diversity self-audit. Rationale: avoid pre-judging or biasing
the test — the references and per-category scoring are the instrument; the verdict is the measurement.
