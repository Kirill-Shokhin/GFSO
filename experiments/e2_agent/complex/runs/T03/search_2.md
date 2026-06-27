# T03 — Search Pass 2 (new holes in D1)

Source: `D1.md` (Audit Pass 1 basis). Only genuinely new content — items not already covered by any D/Dep/V/N entry.

---

## Missing Dependency Seams

**Dep.A — D.11 → D.4 (reconciler verdict as read-switch gate)**
Reconciliation job must confirm zero divergence as an explicit gate condition for the read-path switch, independent of and in addition to backfill completion (Dep.3). Backfill can report 100% rows while dual-write silently missed a fraction.
*Breaks if: backfill completes and row counts match, but 0.01% rows missed by dual-write; read-switch enabled; those rows read from new schema return NULL or wrong shape.*

**Dep.B — D.7 → D.8 (rollback procedures as state-machine reverse transitions)**
Per-phase rollback procedures must be encoded as legal reverse transitions inside the phase state machine (D.8), not only as external runbook steps. A state machine that records only forward transitions cannot atomically reflect a rollback, producing split-brain.
*Breaks if: operator must directly mutate phase state outside D.8 to initiate rollback; some nodes observe the old phase while others observe the new one during the rollback itself.*

**Dep.C — D.10 → D.8 (metrics shape must match gate query expectations)**
The observability design (D.10) must emit metrics in the exact format and granularity that D.8's gate evaluation queries consume. If the two are designed independently, gate conditions are numerically unevaluatable.
*Breaks if: D.8 gate reads `backfill_remaining_rows = 0`; D.10 emits only `backfill_pct_complete`; gate cannot be evaluated and is bypassed manually.*

---

## Missing Global Invariants / Criteria

**V.A — Dual-write partial-failure response policy**
Beyond surfacing the error (V.6), the application must define an explicit behavioral response when old-schema write succeeds and new-schema write fails within the same transaction: retry with backoff, compensating delete, or async queue with alert. "Log and continue" is a policy choice, not a default.
*Falsifier: old-schema commit succeeds; new-schema write throws a transient error; application moves on after logging; divergence accumulates undetected for minutes until reconciler next runs, with no alert and no compensation in the interim.*

**V.B — Application schema assertion at startup**
Each application instance must assert that required schema objects (new table, new columns) exist at startup and fail its health check if they do not, preventing silent execution against a schema that was rolled back or not yet applied.
*Falsifier: expand or dual-write DDL rolled back; new-version app restarts; finds no new table; passes health check; routes live traffic; every affected request throws a runtime schema error with no startup-time warning.*

**V.C — Idle-transaction draining before DDL**
Expand and contract DDL steps must include a check for and controlled termination of long-running idle (not actively executing) transactions that hold locks the DDL needs. Statement-timeout guards apply only to the DDL statement itself; they do not terminate the blocking idle transaction.
*Falsifier: `ALTER TABLE` waits indefinitely behind a six-hour idle reporting session; lock queue grows to hundreds of queries; live traffic stalls; DDL eventually times out but the outage window already occurred.*

**V.D — Lock-timeout to prevent lock-queue cascade**
DDL steps must use `lock_timeout` (fail the DDL immediately if lock is unavailable) rather than only `statement_timeout`. A DDL waiting in the lock queue causes all subsequent queries on the same table to also queue behind it, producing cascading latency even before the DDL statement itself times out.
*Falsifier: `ALTER TABLE` with only `statement_timeout=5s` queues behind a slow query; during those 5 seconds, all new application queries on the same table also queue; service experiences near-downtime even though the DDL is eventually aborted.*

**V.E — Cache invalidation / warming at read-path switch**
If a read-through cache (Redis, Memcached, application-level) sits in front of the database, the migration design must include a cache invalidation and/or cache warming strategy executed at the moment the read-path flag is enabled; otherwise cached old-schema serialized objects continue to be served after the switch.
*Falsifier: cache hit returns old-schema serialized object (new field absent, old field present) after read-path switch; application throws deserialization error or silently drops the new field; divergence is invisible in DB metrics.*

**V.F — Index semantics faithfulness**
New schema must reproduce the full semantics of all indexes on the old column: uniqueness, partial predicate, expression/function, sort direction. V.19 gates on index completion but does not require semantic equivalence.
*Falsifier: old column had `UNIQUE INDEX`; new table's index is non-unique; duplicate values written via dual-write are accepted; data integrity violated after contract phase drops the uniqueness constraint on old schema.*

**V.G — Access control and grants migration**
Column-level permissions, row-level security policies, and GRANT/REVOKE statements on the old table and column must be identified and replicated on the new table before the read-path switch.
*Falsifier: new table missing `GRANT SELECT` for a read-only analytics service account; read-path switch causes permission-denied errors for that service with no prior warning.*

**V.H — Sequence starting value for new table**
If the old column is, or feeds, an auto-increment / sequence-based key, the new table's sequence must start at a value greater than the current maximum of the old column plus a safety buffer, to prevent collision when dual-write begins generating IDs against the new table.
*Falsifier: new table sequence starts at 1; backfill inserts existing rows including ID 1; subsequent dual-write insert generates ID 1 again; primary-key collision.*

**V.I — Backfill cursor on a stable, immutable key**
The backfill cursor or watermark must be based on an immutable ordering key (e.g., primary key surrogate), not on a mutable field such as `updated_at`. If ordered by a mutable field, rows updated during backfill may fall outside all chunk boundaries and never be processed.
*Falsifier: backfill iterates `WHERE updated_at BETWEEN chunk_start AND chunk_end`; a row's `updated_at` is bumped mid-backfill to a value beyond the last processed chunk; it is never backfilled; passes count check only if the reconciler does not catch it.*

**V.J — Replica replication lag at read-switch activation**
When the read-path flag routes reads to read replicas, the activation gate must verify that replica replication lag is within an acceptable bound; backfill rows committed to primary may not yet be visible on a lagging replica.
*Falsifier: read-switch enabled on replica-directed read path; replica 30 seconds behind primary; backfilled rows absent on replica; queries return empty or incorrect results for recently-written data.*

**V.K — Cross-region consistency window during phased flag activation**
In multi-region deployments, gradual activation of the read-path flag region-by-region creates a window in which region A reads from new schema while region B reads from old schema simultaneously. Cross-region aggregation queries produce inconsistent results during this window. V.21 gates the global phase advance but does not govern the per-region activation sequence or its consistency implications.
*Falsifier: region A read-switch active; region B still on old schema; a cross-region aggregate query sums rows from both schemas; total count inflated by double-counted rows.*

---

## Missing Scope Determinations

**N.A — CDC / WAL consumer compatibility (in-scope determination required)**
If the service uses CDC tooling (Debezium, Kafka Connect, logical replication consumers) that reads the database WAL, expand and contract DDL events appear as WAL schema changes; CDC consumers' schema registry must be updated in coordination with DDL phases, or consumers will fail schema validation. This is either an in-scope requirement or must be explicitly excluded with a stated pull-back condition. Currently not mentioned.
*Pulled back in if: any CDC consumer subscribes to the migrated table.*

**N.B — External services reading old schema directly (gate before contract)**
D.9 covers app-version compatibility for the primary service. External analytics pipelines, reporting tools, or other microservices that query the old table/column directly (not via the primary service API) are unaware of the migration and will break when contract DDL drops the old column. A survey and explicit gate on these consumers must be part of the procedure, or their exclusion must be stated.
*Pulled back in if: any external reader has a direct DB connection to the migrated table.*

---

## Count

| Category | New holes |
|---|---|
| Dep seams | 3 |
| V criteria | 11 |
| N scope determinations | 2 |
| **Total** | **16** |
