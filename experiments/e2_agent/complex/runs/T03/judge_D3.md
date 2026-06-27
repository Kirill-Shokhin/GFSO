# BLIND JUDGE VERDICT — T03 / candidate D3

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note (missing leg / which candidate points) |
|---|---|---|---|---|---|
| D1 | D | FM-1 | COVERED | "D.1 Expand-phase design — specify DDL to add new schema objects (table, columns, indexes, deferred/unenforced FK constraints) without altering or dropping old ones" | |
| D2 | D | FM-1 | COVERED | "D.2 Dual-write design — specify how every mutating operation writes to both old and new schema" | |
| D3 | D | FM-1 | COVERED | "D.3 Backfill design — specify the bulk-copy job: chunked and resumable … rate-limited, idempotent … covering all rows" | |
| D4 | D | FM-1 | COVERED | "D.4 Read-path switch design — specify the runtime flag (gradual rollout, per-region or global) … and the path to revert without a new deploy" | |
| D5 | D | FM-1 | COVERED | "D.5 Contract-phase design — specify DDL to drop old schema objects … all dependent DB objects (views, materialized views, procedures, functions, triggers) already migrated or dropped" (+ D.6 cleanup of "dual-write shims, migration helpers, old ORM models") | candidate points: D.5, D.6, D.12, Dep.9, Dep.16, V.22 all collapse here |
| D6 | D | FM-1 | COVERED | "V.19 Index-build gate — required indexes on new schema are built (`CONCURRENTLY` or equivalent) and their completion is verified as an explicit gate before the read-path switch" | online + after-backfill tightening; V.33 also folds here |
| D7 | D | FM-7 | COVERED | "D.7 Per-phase rollback design — specify, for every phase, a tested reversal procedure (DDL reversal + data disposition)" | Dep.7, Dep.12 also map here |
| Dep1 | Dep | FM-1 | COVERED | "V.29 … each application instance must assert that required schema objects (new table, new columns) exist at startup and fail its health check if they do not, preventing silent execution against a schema that was rolled back or not yet applied" | ordering expand→dual-write + the write/schema-error it prevents; V.15 also maps here |
| Dep2 | Dep | FM-1 (+FM-5) | COVERED | "Dep.1 D.2 → D.3 (sequencing): dual-write must be active on 100% of nodes before backfill starts; any write to old schema occurring before dual-write is universal is missed by both dual-write and backfill" | |
| Dep3 | Dep | FM-1 | COVERED | "Dep.3 D.3 → D.4 (backfill verification gate): backfill completion must be verified against the primary database before the read-path switch proceeds" | |
| Dep4 | Dep | FM-1 | COVERED | "V.26 Constraint pre-validation — before contract DDL enforces NOT NULL or UNIQUE constraints on new schema, a scan confirms no existing rows violate them" | constraints-after-backfill ordering |
| Dep5 | Dep | FM-1 | NOT-COVERED | | the post-read-switch soak / keep-old-WRITE-until-rollback-abandoned spine is absent. Candidate's soak (V.11) is *pre*-read-switch; contract gating (Dep.6) is on read-switch-confirmed+drain, not on a rollback-abandoned soak window. V.8 (reversibility) is the invariant (→V-I4), not this seam. |
| Dep6 | Dep | FM-1 + FM-2 | COVERED | "D.9 App-version compatibility window design — specify which (app-version, schema-version) pairs are simultaneously valid during rolling deploys" | Dep.4, Dep.5 also map here |
| Dep7 | Dep | FM-1 + FM-2 | COVERED | "V.28 … an explicit behavioral response when old-schema write succeeds and new-schema write fails within the same transaction: retry with backoff, compensating delete, or async queue with alert" | atomicity/reconciliation of old↔new; V.6 also maps here |
| Dep8 | Dep | FM-1 | COVERED | "Dep.6 D.4 → D.5 (read-switch prerequisite): contract DDL may not execute until the read-path switch is confirmed complete on all nodes and all in-flight queries against old schema have drained" | |
| Dep9 | Dep | FM-1 | COVERED | "N.6 CDC / WAL consumer compatibility — … CDC consumers' schema registry must be updated in coordination with DDL phases, or consumers will fail schema validation" | non-app reader sequenced with DDL; V.32 (cache) also maps here |
| Dep10 | Dep | FM-1 | COVERED | "V.17 All write paths covered — dual-write hooks are applied to every write entry point: service layer, background jobs, admin scripts, event consumers; no secondary path writes old-schema-only" | |
| V-I1 | V | FM-1 | COVERED | "V.2 No data loss — every write committed to old schema during the migration window is reflected in new schema before contract phase completes" | |
| V-I2 | V | FM-1 | COVERED | "V.1 No downtime — at every instant during the migration, the service can serve reads and writes; no phase step requires stopping ingestion or blocking queries" | |
| V-I3 | V | FM-2 | COVERED | "V.5 Schema backward compatibility at every phase boundary — at each phase boundary, the schema state is readable and writable by both version N and version N−1 application code simultaneously" | |
| V-I4 | V | FM-7 + FM-1 | COVERED | "V.8 Full reversibility until cleanup — until contract phase is committed and cleanup is complete, every phase transition can be reversed to the Baseline state without data loss" | |
| V-I5 | V | FM-3 + FM-1 | COVERED | "idempotent (upsert / `INSERT … ON CONFLICT DO UPDATE`)" (D.3) + "V.7 Backfill completeness — … verified by count or checksum comparison against the primary" | both legs: idempotent + verified-equal |
| V-I6 | V | FM-4 | COVERED | "D.8 Phase state-machine design — specify the legal phase sequence … the gate condition for each transition" + "D.10 … metrics … in the exact format and granularity consumed by D.8 gate queries" | guarded ordered progression on measured signals; D.10, V.9, V.10, V.21, Dep.8, Dep.13, Dep.15 all fold here |
| V-E1 | V | FM-7 | COVERED | "V.27 … the removal is deferred until rollback is declared impossible" + per-phase differing reversal procedures (D.7) | point-of-no-return + per-phase asymmetry (Appendix triple-credit rule) |
| V-E2 | V | FM-3 | COVERED | "V.20 Backfill progress durability — … a job crash resumes from the last committed chunk, not from row 0" | V.36 also maps here |
| V-E3 | V | FM-3 | COVERED | "V.30 Idle-transaction draining before DDL — … must include a check for and controlled termination of long-running idle transactions that hold locks the DDL needs" | |
| V-E4 | V | FM-3 | COVERED | "lock-safe execution strategy (e.g., `CREATE INDEX CONCURRENTLY`, statement-timeout guards on `ALTER TABLE`)" (D.1) | online/concurrent DDL to avoid blocking lock |
| V-E5 | V | FM-5 + FM-3 | COVERED | "V.3 Monotonicity — backfill must not overwrite a row already written by dual-write with a stale value; conflict resolution always applies latest-write-wins" | Dep.2 also maps here |
| V-E6 | V | FM-3 | COVERED | "V.37 Replica replication lag at read-switch activation — … the activation gate must verify that replica replication lag is within an acceptable bound" | |
| V-E7 | V | FM-3 | COVERED | "V.40 Request-scoped flag snapshot — the read-path flag is evaluated exactly once at request entry and the result held constant for the entire request lifetime" | per-request-consistent flip; V.4, V.39 also map here |
| V-E8 | V | FM-3 | NOT-COVERED | | only NULL handling is named (V.12 "explicit, tested policy for NULLs"); the general un-coercible/dirty/malformed-legacy-row quarantine-and-continue (dead-letter/exception table) is absent. NULL is a sub-case, not the truth-maker's content. |
| V-F1 | V | FM-2 / FM-5 | COVERED | "V.31 Lock-timeout to prevent lock-queue cascade — … a DDL waiting in the lock queue causes all subsequent queries on the same table to queue behind it, producing cascading latency" | coupling (a correct step's lock = outage) + mechanism (lock_timeout) |
| V-F2 | V | FM-3 | NOT-COVERED | | the compatibility *predicate* is present (V.5 → V-I3) and one concrete constraint guard (Dep.5), but the distinct V-F2 coupling — a step *believed* backward-compatible hides a breaking change, requiring verify-old-binary-against-new-schema-and-vice-versa — is not articulated as such. |
| V-F3 | V | FM-3 | COVERED | "Dep.11 D.11 → D.4 … backfill row-count parity does not detect rows missed by dual-write … 0.01% of rows missed by dual-write; read-switch enabled; those rows read from new schema return NULL or wrong shape" | false-green cutover gate + independent verification |
| V-F4 | V | FM-3 | COVERED | "D.11 Data reconciliation job design — … provides the detection mechanism for silent dual-write failures that neither D.2's error surfacing nor D.3's completion check catches" | silent divergence + active detection scan; Dep.10, Dep.14 also map here |
| V-F5 | V | FM-3 | COVERED | "V.41 ORM/connection-pool schema cache invalidation after expand DDL — … existing database connections with cached schema metadata must be refreshed (via connection-pool flush, forced reconnect, or equivalent); stale caches cause silent write failures" | runtime/tool schema state lies; V.42 (prepared-stmt), V.24 (staging↔prod skew) also fold here |
| N1 | N | FM-1 | COVERED | "N.4 Read-replica DDL propagation — DDL assumed to propagate to replicas automatically via standard replication; replica parity not explicitly managed. Pulled back in if replica lag is high or replicas have diverged" | replication assumed to function, not fixed by the migration |
| N2 | N | FM-1 | NOT-COVERED | | no "single migration at a time / not during an active incident" exclusion declared |
| N3 | N | FM-1 | NOT-COVERED | | the "app deployable in ordered rolling stages, deploy pipeline out of scope" assumption is not declared as an exclusion |
| N4 | N | FM-1 | COVERED | "N.2 Online schema change tools (OSC) — pt-online-schema-change, gh-ost, and equivalents are not mandated; the procedure must work without them. Decision is per-table based on lock-sensitivity and table size" | engine online/low-lock DDL (or OSC) as assumed input axis |
| N5 | N | FM-1 | COVERED | "N.7 … this class of reader is excluded with the assumption that all consumers use the primary service API" | downstream-consumer set assumed enumerable/known |
| N6 | N | FM-1 | NOT-COVERED | | no tested-backup/PITR-as-past-contract-safety-net assumption declared |
| N7 | N | FM-1 | COVERED | "N.1 XA/2PC distributed transactions — out by default … Pulled back in only if old and new schemas reside on different database servers" | assumes single write target (same server); cross-server/distributed conflict excluded |

## 6.2 Ballast list

| ref-id | # candidate points mapped | ballast (count − 1) | the duplicate candidate phrases |
|---|---|---|---|
| D4 | 2 | 1 | V.11 (dark-launch soak before read-switch gate) |
| D5 | 6 | 5 | D.6 (post-migration cleanup of shims/ORM), D.12 (dependent DB-object migration), Dep.9 (cleanup↔contract deployment coupling), Dep.16 (dependent-object gate before contract), V.22 (external FK migration) |
| D6 | 2 | 1 | V.33 (index semantics faithfulness) |
| D7 | 3 | 2 | Dep.7 (rollback state / new-schema-row disposition), Dep.12 (rollback as reverse transitions) |
| Dep1 | 2 | 1 | V.15 (gap-free coverage expand→dual-write window) |
| Dep6 | 3 | 2 | Dep.4 (version gate on read flag), Dep.5 (constraint schedule vs old-version code) |
| Dep7 | 2 | 1 | V.6 (dual-write error visibility) |
| Dep9 | 2 | 1 | V.32 (cache invalidation/warming at read-switch) |
| V-E2 | 2 | 1 | V.36 (backfill cursor on immutable key) |
| V-E5 | 2 | 1 | Dep.2 (conflict protocol latest-write-wins) |
| V-E7 | 3 | 2 | V.4 (intra-request read consistency), V.39 (intra-cluster flag propagation lag) |
| V-F4 | 3 | 2 | Dep.10 (reconciler activation during dual-write window), Dep.14 (reconciler verdict as queryable metric) |
| V-F5 | 3 | 2 | V.42 (prepared-statement invalidation at contract), V.24 (staging-at-production-scale validation) |
| V-I6 | 8 | 7 | D.10 (observability), V.9 (phase-entry idempotency), V.10 (atomic phase commitment), V.21 (global phase-gate evaluation), Dep.8 (state/flag consistency), Dep.13 (metrics/gate contract), Dep.15 (phase-transition audit events) |

**Total ballast = 29.**

## 6.3 Unmatched candidate points

| candidate phrase (verbatim) | flag |
|---|---|
| "V.13 Empty-table correctness — the backfill procedure handles zero-row tables without error" | UNMATCHED — human review |
| "V.14 WAL/log retention sufficiency — … WAL retention settings and replication slot horizons are configured to outlast the backfill window" | UNMATCHED — human review |
| "V.16 Cascade-delete semantics preserved — FK relationships and CASCADE DELETE behavior of the old schema are reproduced correctly in the new schema" | UNMATCHED — human review |
| "V.18 Migration tooling separation — expand and contract DDLs are in separate, sequentially numbered migration files" | UNMATCHED — human review |
| "V.23 No join-completeness dependency during backfill — no executing query may depend on join completeness between old and new schema during the backfill phase" | UNMATCHED — human review |
| "V.25 Read-path flag observability — … a flag service outage must not silently leave reads on old schema without detection" | UNMATCHED — human review |
| "V.34 Access control and grants migration — column-level permissions, row-level security policies, and GRANT/REVOKE statements … must be identified and replicated on the new table" | UNMATCHED — human review |
| "V.35 Sequence starting value for new table — … the new table's sequence must start at a value greater than the current maximum of the old column plus a safety buffer" | UNMATCHED — human review |
| "V.38 Cross-region consistency window during phased flag activation — … cross-region aggregation queries produce inconsistent results during this window" | UNMATCHED — human review |
| "V.43 Multi-table parent-before-child backfill ordering — … the backfill job must insert parent rows before child rows for each chunk" | UNMATCHED — human review |
| "V.44 VACUUM blockage mitigation during long backfill — … active logical replication slots or long-running transactions prevent the VACUUM process from reclaiming dead tuples" | UNMATCHED — human review |
| "N.3 DB-trigger implementation of dual-write — the default design uses application-layer dual-write; the trigger option is documented with tradeoffs but not the baseline" | UNMATCHED — human review |
| "N.5 Business-logic constraint implementation details — domain-specific rules introduced by the split … are enumerated as requirements … but their implementation details are out of scope" | UNMATCHED — human review |

**Total unmatched = 13.**

*(Note: V.12 "NULL policy enforced" maps to ref V-E8 as the closest truth-maker but does not satisfy it — recorded as NOT-COVERED supporting evidence, not unmatched.)*

## 6.4 Score block
```
COVERAGE (fully-COVERED / total):
  by category:   D = 7/7   Dep = 9/10   V = 17/19   N = 4/7
  by FM tag:     FM-1 = 17/21   FM-2 = 4/4   FM-3 = 10/12   FM-4 = 1/1   FM-5 = 3/3   FM-6 = n/a   FM-7 = 3/3
  PARTIAL counts: D = 0   Dep = 0   V = 0   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 29
  unmatched candidate points (human-review flag):    total = 13
```
