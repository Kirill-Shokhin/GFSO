# BLIND JUDGE VERDICT — T03 / candidate D1

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "specify DDL to add new schema objects (table, columns, indexes, deferred/unenforced FK constraints) without altering or dropping old ones" | additive expand phase |
| D2 | D | — | COVERED | "specify how every mutating operation writes to both old and new schema; covers ALL write entry points" | dual-write phase |
| D3 | D | — | COVERED | "specify the bulk-copy job: chunked and resumable (cursor/watermark persisted durably), rate-limited, idempotent" | backfill, throttled bounded batches |
| D4 | D | — | COVERED | "specify the runtime flag (gradual rollout, per-region or global), gate conditions for enabling it (backfill verified + dark-launch soak), and the path to revert without a new deploy" | read-path cutover, flag-gated |
| D5 | D | — | COVERED | "specify DDL to drop old schema objects" + (D.6) "removal of dual-write shims, migration helpers, old ORM models, and temporary indexes in both application code and DB" | contract + purge references (split across D.5/D.6) |
| D6 | D | — | COVERED | "required indexes on new schema are built (`CONCURRENTLY` or equivalent) and their completion is verified as an explicit gate before the read-path switch" (V.19) + (D.5) "enforce remaining constraints" | online constraint/index installation after backfill |
| D7 | D | FM-7 | COVERED | "specify, for every phase, a tested reversal procedure (DDL reversal + data disposition); includes dry-run requirement" | per-phase rollback design obligation |
| Dep1 | Dep | FM-1 | NOT-COVERED | | expand-fully-deployed-before-dual-write seam + the dual-write-against-missing-column write-error is not named; the D.8 state-machine lists the order but with a generic gate falsifier, not this breakage |
| Dep2 | Dep | FM-1, FM-5 | COVERED | "dual-write must be active on 100% of nodes before backfill starts; any write to old schema occurring before dual-write is universal is missed by both dual-write and backfill" | ordering + concurrent-write-loss window |
| Dep3 | Dep | FM-1 | COVERED | "backfill completion must be verified against the primary database before the read-path switch proceeds" | verify-before-cutover ordering seam |
| Dep4 | Dep | FM-1 | COVERED | "before contract DDL enforces NOT NULL or UNIQUE constraints on new schema, a scan confirms no existing rows violate them" (V.26) | constraints only after data populated |
| Dep5 | Dep | FM-1 | NOT-COVERED | | the rollback-safety spine — "keep writing old until the new read path has SOAKED past read-switch, stop old-write only when rollback abandoned" — is absent; V.11 soak is a dark-launch soak BEFORE read-switch, not old-write persistence AFTER the flip |
| Dep6 | Dep | FM-1, FM-2 | COVERED | "specify which (app-version, schema-version) pairs are simultaneously valid during rolling deploys; define the drain-check procedure to verify all live instances are on a compatible version before each phase advance" | mixed-version fleet on one shared schema |
| Dep7 | Dep | FM-1, FM-2 | COVERED | "a new-schema write failure must be surfaced (raised or alarmed), not silently swallowed; old-schema write must not succeed while a new-schema write failure goes undetected" (V.6), reinforced by reconciler D.11 | old↔new kept consistent (reconciled path; truth-maker allows "same txn or reconciled") |
| Dep8 | Dep | FM-1 | PARTIAL | "contract DDL may not execute until the read-path switch is confirmed complete on all nodes and all in-flight queries against old schema have drained" (Dep.6) | no-old-READER leg met; missing leg: contract gated on no-old-WRITER (dual-write-to-old turned off & fully deployed / write grants revoked) before the drop |
| Dep9 | Dep | FM-1 | NOT-COVERED | | non-app downstream READERS (CDC / warehouse ETL / search index / cache / other services) tolerating both shapes across the window and surviving the contract drop is not named; V.23 only defers a reporting query DURING backfill, not consumer survival of the drop |
| Dep10 | Dep | FM-1 | PARTIAL | "dual-write hooks are applied to every write entry point: service layer, background jobs, admin scripts, event consumers; no secondary path writes old-schema-only" (V.17) | enumerate-all-writers leg met; missing leg: freeze / re-point / revoke-write-grants on every non-app writer BEFORE contract |
| V-I1 | V | FM-1 | COVERED | "every write committed to old schema during the migration window is reflected in new schema before contract phase completes" | no data loss |
| V-I2 | V | FM-1 | COVERED | "at every instant during the migration, the service can serve reads and writes; no phase step requires stopping ingestion or blocking queries" | no downtime |
| V-I3 | V | FM-2 | COVERED | "at each phase boundary, the schema state is readable and writable by both version N and version N−1 application code simultaneously" | compatibility matrix across mixed fleet |
| V-I4 | V | FM-7, FM-1 | COVERED | "until contract phase is committed and cleanup is complete, every phase transition can be reversed to the Baseline state without data loss" | reversibility + no-loss-on-rollback |
| V-I5 | V | FM-3, FM-1 | COVERED | "idempotent (upsert / `INSERT … ON CONFLICT DO UPDATE`)" (D.3) + "verified by count or checksum comparison against the primary" (V.7) | both legs: idempotent AND verified-equal |
| V-I6 | V | FM-4 | COVERED | "specify the legal phase sequence … the gate condition for each transition" (D.8) + "dedicated metrics (dual-write error rate, backfill lag, new-schema vs old-schema row-count parity …) … go/no-go criteria" (D.10) | guarded ordered progression on measured signals |
| V-E1 | V | FM-7 | COVERED | "for every phase, a tested reversal procedure (DDL reversal + data disposition) … addresses disposition of new-schema rows orphaned if dual-write phase is rolled back" (D.7) + "until contract phase is committed … can be reversed" (V.8) | per-phase asymmetry + post-contract point-of-no-return (clears the appendix bar above bare "reversible") |
| V-E2 | V | FM-3 | COVERED | "backfill progress (cursor or watermark) is persisted to a durable store; a job crash resumes from the last committed chunk, not from row 0" | mid-backfill crash/resume |
| V-E3 | V | FM-3 | NOT-COVERED | | a long-running txn/query open ACROSS a DDL step (blocking the DDL or seeing an inconsistent schema) is not named; candidate guards only the DDL's own lock (V-E4), not an in-flight long txn colliding |
| V-E4 | V | FM-3 | COVERED | "lock-safe execution strategy (e.g., `CREATE INDEX CONCURRENTLY`, statement-timeout guards on `ALTER TABLE`)" | large-table online-DDL lock avoidance |
| V-E5 | V | FM-5, FM-3 | COVERED | "backfill must not overwrite a row already written by dual-write with a stale value; conflict resolution always applies latest-write-wins, keyed on `updated_at`" | concurrent-writes-during-backfill row race |
| V-E6 | V | FM-3 | NOT-COVERED | | replica lag SERVING stale/empty new-column reads at cutover (wait-for-replica / RYW routing) is not named; Dep.3 only refuses to trust replica COUNTS for the completion check |
| V-E7 | V | FM-3 | NOT-COVERED | | read-after-write at the cutover instant ("a request reads-new while its own write only landed old") is not named; V.4 asserts not-mixing-reads within a request, a different predicate |
| V-E8 | V | FM-3 | COVERED | "the split operation has an explicit, tested policy for NULLs in the original column (null FK, sentinel row, or error); no NULL silently produces an FK violation or is dropped from new schema" | un-coercible legacy value (NULL is the named V-E8 sub-case) handled non-silently |
| V-F1 | V | FM-2, FM-5 | COVERED | "chunked and resumable … rate-limited" backfill (D.3) + "any step that takes an unguarded table lock blocking all queries" (V.1 falsifier) | lock=de-facto-downtime coupling + batching/throttle mechanism incl. long backfill txn |
| V-F2 | V | FM-3 | COVERED | "expand DDL must not enforce FKs or NOT NULL constraints that old-version app code cannot satisfy … old-version INSERT into old table fails with FK violation" (Dep.5) | a believed-safe step that breaks the other running version + the both-versions guard |
| V-F3 | V | FM-3 | COVERED | "a replica-based completion check is insufficient due to replication lag" (Dep.3); "completion declared based on replica row counts while primary has additional rows" (V.7 falsifier) | the cutover consistency-check can false-PASS on incomplete data; guard = full check vs primary |
| V-F4 | V | FM-3 | COVERED | "a continuous or periodic job that compares old and new schema row-by-row during the dual-write phase; provides the detection mechanism for silent dual-write failures" (D.11) | active divergence detection for silent old-only writes |
| V-F5 | V | FM-3 | NOT-COVERED | | tool/runtime bookkeeping lying about the live schema (INVALID-but-marked-done index, stale prepared-statement/pool plans, ORM drift, refresh-caches-after-DDL) is not named; V.24 staging-skew and V.19 index-gate do not reach the coupling |
| N1 | N | FM-1 | COVERED | "DDL assumed to propagate to replicas automatically via standard replication; replica parity not explicitly managed. Pulled back in if replica lag is high" (N.4) | replication assumed bounded/functioning |
| N2 | N | FM-1 | NOT-COVERED | | no exclusion of a competing concurrent schema change / migration-during-incident |
| N3 | N | FM-1 | NOT-COVERED | | the deploy-pipeline / ordered-rolling-rollout assumption is not declared out of scope |
| N4 | N | FM-1 | COVERED | "pt-online-schema-change, gh-ost, and equivalents are not mandated; the procedure must work without them. Decision is per-table based on lock-sensitivity and table size" (N.2) | engine online/low-lock-DDL (or OSC stand-in) capability declared an input |
| N5 | N | FM-1 | NOT-COVERED | | the enumerable-downstream-consumer-set assumption (twin of Dep9) is not declared |
| N6 | N | FM-1 | NOT-COVERED | | a tested backup/PITR as the past-contract safety net is not declared |
| N7 | N | FM-1 | NOT-COVERED | | single-logical-primary (multi-primary/sharded conflict resolution excluded) is not declared; N.1 excludes XA/2PC across servers, a different assumption |

## 6.2 Ballast list

| ref-id | # candidate points mapped | ballast (count − 1) | the duplicate candidate phrases |
|---|---|---|---|
| D4 | 2 | 1 | D.4 read-path flag + V.11 "the new-schema write path must have sustained real traffic for a defined minimum duration … before the read-switch gate closes" |
| D5 | 4 | 3 | D.5 "drop old schema objects" + D.6 cleanup of shims/ORM + Dep.9 "the cleanup deploy … must be coupled to the contract DDL deployment" + V.22 "all FKs from other tables pointing to the column being split are migrated" |
| Dep2 | 2 | 1 | Dep.1 dual-write-before-backfill + V.15 "no write occurring after the expand DDL and before dual-write is universally deployed is left uncaptured" |
| Dep6 | 2 | 1 | D.9 compat-window + Dep.4 "the read-path flag may be enabled only for app versions confirmed capable of deserializing new-schema responses" |
| V-E5 | 2 | 1 | V.3 monotonicity + Dep.2 "the upsert must pick the winner by `updated_at` timestamp (latest-write-wins)" |
| V-I4 | 3 | 2 | V.8 reversibility + Dep.7 "rollback from the dual-write phase requires an explicit decision about rows already written to new schema" + V.27 "before any cleanup action removes an artifact … the rollback query plan is verified to not depend on it" |
| V-I6 | 3 | 2 | D.8 state-machine + D.10 observability/go-no-go + V.21 "phase gate conditions are evaluated globally across all regions" |
| V-F4 | 2 | 1 | D.11 reconciler + Dep.10 "it must be running during the entire dual-write window, not only at backfill completion" |

**Total ballast = 12.**

(V-I5's two mapped points — D.3 idempotency leg + V.7 verified-equal leg — are distinct required legs of a multi-leg truth-maker, not duplicates; not counted as ballast.)

## 6.3 Unmatched candidate points

| candidate phrase (verbatim) | flag |
|---|---|
| Dep.8 "the migration state record and the read-path feature flag must agree; if the state record says 'read-switch complete' but the flag service disagrees, behavior is undefined" | UNMATCHED — human review |
| V.4 "within a single request or transaction, reads must not mix old-schema and new-schema responses" | UNMATCHED — human review |
| V.9 "re-applying the DDL or application step for any given phase is a no-op; no error or data corruption on re-run (IF NOT EXISTS, upsert semantics throughout)" | UNMATCHED — human review |
| V.10 "a phase transition is a single, transactional write to the migration state record; no partial transitions where some nodes observe the new phase and others the old" | UNMATCHED — human review |
| V.13 "the backfill procedure handles zero-row tables without error; count/checksum completion check passes on empty tables" | UNMATCHED — human review |
| V.14 "WAL retention settings and replication slot horizons are configured to outlast the backfill window" | UNMATCHED — human review |
| V.16 "FK relationships and CASCADE DELETE behavior of the old schema are reproduced correctly in the new schema" | UNMATCHED — human review |
| V.18 "expand and contract DDLs are in separate, sequentially numbered migration files; the migration tool cannot apply them atomically in a single step" | UNMATCHED — human review |
| V.23 "no executing query may depend on join completeness between old and new schema during the backfill phase; such queries are either deferred or rewritten" | UNMATCHED — human review |
| V.24 "the full procedure is validated on a staging environment with production-scale data before live execution" | UNMATCHED — human review |
| V.25 "the flag service has an observable default/fallback behavior; a flag service outage must not silently leave reads on old schema without detection" | UNMATCHED — human review |
| N.1 "XA/2PC distributed transactions — out by default; compensating dual-write + reconciler is used instead. Pulled back in only if old and new schemas reside on different database servers" | UNMATCHED — human review |
| N.3 "DB-trigger implementation of dual-write — the default design uses application-layer dual-write; the trigger option is documented with tradeoffs but not the baseline" | UNMATCHED — human review |
| N.5 "Business-logic constraint implementation details — domain-specific rules introduced by the split … are enumerated as requirements … but their implementation details are out of scope" | UNMATCHED — human review |

**Total unmatched = 14.**

## 6.4 Score block
```
COVERAGE (fully-COVERED / total):
  by category:   D = 7/7   Dep = 5/10   V = 15/19   N = 2/7
  by FM tag:     FM-1 = 11/21   FM-2 = 4/4   FM-3 = 8/12   FM-4 = 1/1   FM-5 = 3/3   FM-6 = n/a   FM-7 = 3/3
  PARTIAL counts: D = 0   Dep = 2   V = 0   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 12
  unmatched candidate points (human-review flag):    total = 14
```
