# T03 — Exhaustive Enumeration (Search Pass 1)

Task: design the procedure and invariants for a backward-incompatible relational schema change
(e.g. split a column into a new table) on a live, high-traffic service with rolling deploys and
no downtime.

---

## 1. Domain Primitives

D-1. **Expand step** — add new schema objects (column, table, FK) without removing old ones, so both old and new app code can run simultaneously. *Falsifier: any DDL that drops or renames the old object before all readers migrate.*

D-2. **Contract step** — remove old schema objects only after zero app instances still reference them. *Falsifier: dropping old column while at least one deployed pod still reads it.*

D-3. **Dual-write** — every mutating operation writes to both old schema and new schema for the duration of the migration window. *Falsifier: a write that reaches the old path but silently skips the new path, leaving new schema stale.*

D-4. **Backfill** — bulk-copy existing rows from old schema representation into new schema representation, covering all rows created before dual-write was enabled. *Falsifier: any pre-dual-write row absent from the new schema after backfill completes.*

D-5. **Read-path switch** — application reads are redirected from old to new schema after new schema is proven complete. *Falsifier: reads still hitting old schema after the switch, or reads hitting new schema before backfill is verified complete.*

D-6. **Phase gate** — a defined, verifiable condition that must be satisfied before advancing to the next phase; no phase is entered speculatively. *Falsifier: phase advanced while gate condition is unverified.*

D-7. **Compatibility window** — the set of app-version/schema-version pairs that are simultaneously valid; rolling deploy means multiple app versions are live at once. *Falsifier: a phase transition that makes a currently-deployed app version unable to read or write.*

D-8. **Rollback path** — for every phase, a defined procedure to revert to the previous stable state without data loss. *Falsifier: a phase with no written rollback procedure, or one that discards writes made in that phase.*

D-9. **Migration state record** — a persistent record (table, flag store, or config) tracking which phase is currently active and when it was entered. *Falsifier: phase state lives only in memory or deployment config, lost on restart.*

D-10. **Cleanup step** — removal of dual-write shims, migration helpers, old columns/tables, and temporary indexes after contract phase completes and the migration is declared done. *Falsifier: cleanup runs while contract phase is incomplete, or cleanup artifacts remain in the codebase indefinitely.*

---

## 2. Lifecycle / State Machine

L-1. **Phase ordering** — the legal sequence is: Baseline → Expand → Dual-write+Backfill → Read-switch → Contract → Cleanup; no phase may be skipped. *Falsifier: advancing directly from Baseline to Contract.*

L-2. **Idempotency of each phase entry** — re-running the DDL or the application step for a given phase is a no-op if already applied (IF NOT EXISTS, upsert backfill). *Falsifier: applying the expand DDL twice raises an error or corrupts data.*

L-3. **Atomicity of phase commitment** — the signal to enter a new phase is a single, transactional write to the migration state record, not a sequence of independent config changes. *Falsifier: partial phase transitions where some nodes see the new phase and others still see the old.*

L-4. **Drain check before phase advance** — before each phase gate closes, verify that all live app instances are on a version compatible with the next phase. *Falsifier: old-version pod still serving traffic when contract phase begins.*

L-5. **Backfill completion verification** — before read-path switch, a count or checksum comparison proves every pre-dual-write row exists in the new schema. *Falsifier: switching reads on assumption of completion without an explicit verification query.*

L-6. **Dark-launch period** — new schema is written to and backfilled but reads are still served from old schema; this period must have a defined minimum duration / traffic volume before read-switch is allowed. *Falsifier: switching reads immediately after backfill with no soak period.*

---

## 3. Components

C-1. **DDL scripts (expand)** — scripts that add new table, new columns, new indexes, new FK constraints (initially deferred or not enforced) without touching old objects. *Falsifier: script that alters old column type or drops old column.*

C-2. **DDL scripts (contract)** — scripts that drop old columns/tables, enforce FKs, remove temporary indexes after all compatibility requirements are met. *Falsifier: contract DDL bundled with expand DDL in one migration file.*

C-3. **Dual-write application layer** — code path (service layer, ORM hooks, or DB trigger) that writes both old and new representations on every INSERT/UPDATE/DELETE. *Falsifier: dual-write only in one code path, missing any secondary write entry points.*

C-4. **Backfill job** — chunked, resumable batch job that reads from old schema and writes to new schema for all existing rows, running concurrently with live traffic. *Falsifier: backfill locks the entire table or runs in a single non-resumable transaction.*

C-5. **Backfill chunk strategy** — partition the table by PK range or cursor; each chunk committed independently so a failure does not require restarting from row 0. *Falsifier: backfill runs as one giant transaction.*

C-6. **Backfill rate limiter** — throttle the backfill job to cap its read/write IOPS impact on the live database. *Falsifier: backfill saturates DB I/O and degrades live query latency.*

C-7. **Backfill idempotency (upsert)** — each chunk uses INSERT … ON CONFLICT DO UPDATE (or equivalent) so re-running a chunk is safe. *Falsifier: re-running a failed chunk creates duplicate rows or raises a unique-constraint error.*

C-8. **Read-path feature flag** — a runtime flag (per-request, per-region, or global) that controls whether reads go to old or new schema; supports gradual rollout. *Falsifier: read switch is a hard deploy with no ability to cut back without a new deploy.*

C-9. **Rollback scripts per phase** — for every forward DDL or data change, a tested reverse script exists and has been dry-run. *Falsifier: rollback script written but never tested; fails when needed.*

C-10. **Migration runbook** — step-by-step operator procedure for each phase including verification queries, expected outputs, go/no-go criteria, and rollback triggers. *Falsifier: migration executed ad-hoc without documented go/no-go checks.*

C-11. **Monitoring / alerting for migration health** — dedicated metrics: dual-write error rate, backfill lag, new-schema row count vs old-schema row count, read-path flag state. *Falsifier: migration phase advances with no observable difference in metrics from a failed migration.*

C-12. **New-schema FK and constraint enforcement schedule** — FKs and NOT NULL constraints on new table start DEFERRABLE or unenforced, are enforced only after backfill and dual-write are complete. *Falsifier: enforcing FK immediately on expand DDL, blocking inserts that haven't yet populated the new table.*

---

## 4. Global Invariants

G-1. **No downtime** — at every instant during migration, the service can serve reads and writes; no operation requires taking the service offline. *Falsifier: any phase step that requires stopping ingestion or blocking queries.*

G-2. **No data loss** — every write committed to the old schema during the migration window must be reflected in the new schema before contract phase completes. *Falsifier: a committed write to old schema that has no corresponding row in new schema at contract time.*

G-3. **Monotonicity / no backfill overwrites newer data** — backfill must not overwrite a row that was already written by dual-write with a more recent version. *Falsifier: backfill runs after dual-write starts and clobbers a newer value with the stale snapshot.*

G-4. **Read consistency during flag rollout** — a single user's session should not see a mix of old-schema and new-schema responses within the same request or transaction. *Falsifier: load-balanced request with 50% flag hits new schema, 50% hits old schema, returning inconsistent aggregates.*

G-5. **Schema backwards compatibility invariant** — at every phase boundary, the schema state must be readable and writable by both the version N and version N−1 application code simultaneously. *Falsifier: schema state at phase boundary that causes version N−1 to error on read or write.*

G-6. **Dual-write atomicity** — a write to old schema and the corresponding write to new schema must both succeed or both fail (or the failure of the new-schema write must be surfaced and not silently dropped). *Falsifier: new-schema write fails silently, old-schema write succeeds, divergence accumulates without alert.*

G-7. **Backfill must cover all rows, including soft-deleted / archived** — rows that are not "active" but exist in old schema must also be migrated, or a conscious decision not to migrate them must be recorded. *Falsifier: backfill filters on `is_active = true`, leaving soft-deleted rows unmigrated and causing read errors when those rows are later accessed.*

G-8. **Migration is reversible at every phase** — until contract phase is committed and cleanup is done, it must be possible to roll back to the Baseline state. *Falsifier: a phase that destroys old-schema data with no recovery path.*

---

## 5. Cross-Component Interaction Seams

S-1. **Dual-write ↔ Backfill ordering** — dual-write must be fully enabled and stable on all nodes before backfill starts; otherwise rows written between "first dual-write node" and "last dual-write node" may be missed. *Falsifier: backfill starts at T=0, dual-write rolls out to node 10 at T=5, rows written to node 10 between T=0 and T=5 are absent from new schema.*

S-2. **Backfill ↔ Read-path switch sequencing** — read switch must not proceed until backfill completion is verified; if backfill fails mid-run, read switch gate must block. *Falsifier: backfill job exits with a non-zero error code but migration state machine still advances to read-switch.*

S-3. **Backfill timestamp vs dual-write timestamp** — backfill reads a snapshot of the old table; concurrent dual-writes to rows covered by that snapshot produce a race; the upsert strategy must pick the winner correctly (latest-write wins by updated_at, not by write order). *Falsifier: backfill overwrites a dual-written row with an older value because it arrived later in wall time.*

S-4. **Read-path flag ↔ App version compatibility** — the read-path flag must only be enabled for app versions that can interpret new-schema results; enabling it for old-version pods causes query errors. *Falsifier: flag enabled globally, old-version pods receive new-schema response shape and throw deserialization errors.*

S-5. **DDL expand ↔ App version N−1 writes** — the expand DDL may add a NOT NULL column to a new table that version N−1 never writes to; if the FK from old table to new table is enforced at expand time, old-version writes break. *Falsifier: expand DDL adds enforced FK, old-version INSERT into old table fails with FK violation.*

S-6. **Contract DDL ↔ Read-path switch completion** — old column/table must not be dropped until read-path switch is confirmed on all nodes and all in-flight queries against old schema have drained. *Falsifier: contract DDL runs while a slow query still references old column, causing query failure.*

S-7. **Rollback ↔ Dual-write** — rolling back from the dual-write phase means disabling dual-write; writes made to new schema during dual-write phase become orphaned; rollback plan must address whether to delete those new-schema rows or leave them. *Falsifier: rollback procedure re-enables old-only writes but leaves new-schema rows in place, causing confusion on next attempt.*

S-8. **Backfill job ↔ DB replication lag** — if backfill reads from a replica for performance, replication lag may cause it to miss recent dual-write data already committed on primary. *Falsifier: backfill finishes cleanly against replica, but replica is 30s behind primary, leaving those rows unmigrated.*

S-9. **Feature flag ↔ Migration state record** — the read-path feature flag and the migration state record must agree; if state record says "read-switch complete" but flag is off in the flag service, divergence in behavior occurs. *Falsifier: migration state says Phase=Contract, flag service still serves "old schema" to 100% of traffic.*

S-10. **Cleanup ↔ Application code removal** — old-schema ORM models, dual-write shims, and compatibility adapters in application code must be removed in the same deployment that follows contract DDL; if code is cleaned first, a rollback of the DDL causes runtime errors. *Falsifier: application code cleaned of dual-write shim, DDL rollback attempted, old write path no longer exists in code.*

S-11. **Rolling deploy ↔ Dual-write enablement** — during a rolling deploy that enables dual-write, some pods have dual-write on and some do not; writes from non-dual-write pods to old schema are not replicated to new schema; backfill must start only after 100% of pods are on dual-write version. *Falsifier: backfill starts with only 80% pods dual-write enabled; 20% of writes during that window only land on old schema.*

S-12. **DDL lock acquisition ↔ Live traffic** — ALTER TABLE / CREATE INDEX operations take locks; on high-traffic tables, lock acquisition may queue behind long-running transactions and itself block all subsequent queries. *Falsifier: expand DDL runs unguarded on a table with a 60-second OLAP query in flight, causing a lock pile-up that degrades all reads for 60+ seconds.*

---

## 6. Edge / Boundary Cases

E-1. **NULL values in source column** — the split operation must have an explicit policy for NULLs in the original column: do they produce a NULL FK, a sentinel row in the new table, or an error? *Falsifier: NULLs silently produce an FK violation or are dropped from new schema.*

E-2. **Zero-row table** — backfill of a table with zero rows must not be treated as an error; the procedure must handle empty tables gracefully and still verify completion. *Falsifier: backfill job's count-check fails on empty table.*

E-3. **Extremely large table** — backfill duration may span hours or days; procedure must account for weeks-long dual-write window and any implications for log/WAL retention. *Falsifier: WAL is truncated before backfill finishes, causing replication failure or inability to roll back.*

E-4. **Row inserted between expand DDL and dual-write enablement** — if any write occurs after expand DDL but before dual-write code is deployed, that row is missed by both dual-write and backfill (if backfill reads from a snapshot taken at dual-write start). *Falsifier: a row inserted in this gap is absent from new schema at read-switch.*

E-5. **Cascade deletes** — if the old column being split has downstream FK dependencies, splitting it into a new table may break CASCADE DELETE semantics unless the new FK is also set to CASCADE. *Falsifier: delete on parent row cascades correctly in old schema, but leaves orphan rows in new table.*

E-6. **Application code with multiple write paths** — background jobs, admin scripts, data importers, and event consumers may write directly to old schema via separate code paths not covered by the main dual-write shim. *Falsifier: nightly ETL job inserts rows into old schema, none of those rows are reflected in new schema.*

E-7. **Schema migration tool conflicts** — if Flyway/Liquibase/Alembic is managing schema versions, the expand and contract DDLs must be separate numbered migrations; combining them in one file prevents the intermediate stable state. *Falsifier: migration tool refuses to apply partial migrations, forcing expand and contract in one step.*

E-8. **Index on new column / table** — new schema may require indexes that are large and slow to build; CREATE INDEX CONCURRENTLY must be used, and its completion is a gate before reads switch. *Falsifier: index build is skipped, read-path switch causes full-table scans that degrade performance.*

E-9. **Partial backfill resumption after crash** — if backfill job crashes at chunk N, resumption must start from chunk N, not chunk 0; a cursor or watermark table must persist the progress. *Falsifier: crash at 90% completion restarts from row 1, re-processing 90% of the table unnecessarily.*

E-10. **Multi-region / multi-datacenter** — each region may be on a different app version during rolling deploy; phase gates must be evaluated globally, not per-region. *Falsifier: region A completes read-switch, region B still on old version; contract DDL drops old column globally, breaking region B.*

E-11. **Foreign key to the split column from another table** — if another table has an FK pointing to the column being split, that FK must be migrated as part of the procedure, not left pointing to a dropped column. *Falsifier: contract DDL drops old column; FK from sibling table now points to non-existent column.*

E-12. **Reads during backfill that join old and new schema** — queries that JOIN old table to new table during backfill will see partial data; queries must not be written to depend on join completeness during the backfill phase. *Falsifier: reporting query joins old and new table, runs during backfill, returns incorrect aggregates that feed a dashboard.*

E-13. **Test / staging environment parity** — the procedure must be validated on a staging environment with production-scale data before live execution; a procedure tested only on small data may behave differently under volume. *Falsifier: procedure works on staging (10k rows) but backfill job times out on production (500M rows).*

---

## 7. Silent Failure Modes

F-1. **Dual-write swallowed exception** — new-schema write fails (constraint violation, timeout, deadlock) and the exception is caught-and-logged rather than raised; old-schema write succeeds; divergence accumulates. *Falsifier: error rate on new-schema writes is unmonitored; divergence only discovered at read-switch.*

F-2. **Backfill reports success on partial run** — job exits 0 because the chunk loop completes, but some chunks were skipped due to a caught exception; row count never verified. *Falsifier: no post-backfill row-count comparison between old and new schema.*

F-3. **Read-path flag silently defaulting** — flag service outage causes all reads to fall back to old schema even after flag is set to new; the migration appears to have worked but reads never actually switched. *Falsifier: flag service has no circuit-breaker observable; migration assumed complete while reads silently remain on old schema.*

F-4. **Version leak** — one pod is on an old version that bypasses dual-write because the old code path is behind a feature branch not included in the release; it writes to old schema only. *Falsifier: no assertion that 100% of write-path code goes through the dual-write shim.*

F-5. **Constraint enforcement timing error** — NOT NULL or UNIQUE constraint on new table is added during contract phase, but a row that violates it was written by a legacy code path and now blocks the DDL. *Falsifier: contract DDL fails with constraint violation, requiring manual data repair under live traffic.*

F-6. **Backfill reads stale snapshot from replica and marks complete** — backfill runs against a replica that is arbitrarily behind; completion is declared based on replica counts, but primary has newer rows the replica hasn't received. *Falsifier: new-schema row count from replica matches old-schema row count from replica, but primary has 1000 more rows.*

F-7. **Cleanup removes helper index needed for rollback** — post-migration cleanup drops a temporary index that was also the only efficient path for the rollback query; rollback is now prohibitively slow. *Falsifier: rollback query plan not tested after cleanup; rollback takes hours instead of seconds.*

F-8. **Orphaned dual-write code after cleanup deploy** — cleanup removes old schema from the DB but a background worker was not redeployed and still tries to write to the old column; it begins throwing errors silently. *Falsifier: no deployment coupling between contract DDL and application cleanup deploy.*

---

## 8. Scope Boundaries

B-1. **Application-level transaction spanning old and new schema** — writing to both schemas atomically within one DB transaction is IN scope as a design decision; using a distributed transaction or saga to coordinate them is an option that must be explicitly evaluated and chosen. *Why safely out: XA/2PC adds significant complexity; a compensating approach (dual-write + reconciler) is simpler. Pulled back in if the old and new schemas are on different databases.*

B-2. **Online schema change tools (pt-online-schema-change, gh-ost)** — using OSC tools for the underlying DDL is IN scope as an option for tables that cannot accept even a brief lock; this must be decided per table. *Why safely out: not all environments have these tools; procedure must work without them. Pulled back in if table > N rows and lock-free DDL is unavailable.*

B-3. **Data validation / reconciliation job** — a continuous or periodic reconciler that compares old and new schema row-by-row is IN scope as a safety net during the dual-write phase. *Why: silent F-1 failure mode above makes this load-bearing, not optional.*

B-4. **Application-level migration vs DB-level trigger** — dual-write can be implemented at the application layer or via a DB trigger on the old table; both options are in scope and the choice must be documented with tradeoffs. *Why safely out: triggers add DB-level coupling; application layer is more observable. Pulled back in if multiple heterogeneous app services write to old schema independently.*

B-5. **Schema migration for read replicas** — read replicas must receive the same DDL changes; procedure must verify replicas are caught up before read-switch. *Why safely out: most replication setups propagate DDL automatically. Pulled back in if replica lag is high or replicas have diverged.*

B-6. **Business-logic invariants specific to the split column** — domain-specific rules (e.g., "a customer must always have exactly one billing address") that the split introduces must be enforced in new schema; they are IN scope to enumerate even if their implementation details are out. *Falsifier: new schema allows states that business rules forbid, noticed only in production after read-switch.*
