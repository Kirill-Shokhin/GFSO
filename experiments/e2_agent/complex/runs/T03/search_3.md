# T03 — Search Pass 3 (holes in D2)

D2 is very thorough. After a hard look, 9 genuinely new items remain — no restatements of existing content.

---

## New holes

**H1 — DB-side dependent object migration** — All database-side objects that reference the old column (views, materialized views, stored procedures, functions, triggers) must be identified and migrated as an explicit step before contract DDL; V.22 covers only FKs from sibling tables, not these objects.
*Falsifier: contract DDL drops old column; an existing view referencing that column becomes invalid; every query that hits the view fails with "column does not exist."*

**H2 — Seam D.11 → D.10 (reconciler output into observability)** — The reconciler's zero-divergence verdict must be emitted as a D.10-format queryable metric, not only as an internal state or log entry; without this the D.8 gate cannot be automated and is manually bypassed under time pressure.
*Falsifier: D.11 publishes its verdict only to an internal log; D.10 has no corresponding metric; D.8's gate is checked by hand; gate is skipped on night shift.*

**H3 — Intra-cluster flag propagation lag** — Within a single region/cluster, after the read-path flag is written, each pod observes the new value only after its cache TTL expires; during this window some pods route to new schema and others to old. V.38 covers cross-region phased activation; this is the same-region simultaneous flip case. The design must specify a maximum acceptable propagation window and how cross-pod aggregation queries behave within it.
*Falsifier: flag flipped for the cluster; pod A (TTL=0) reads new schema; pod B (TTL=60s) still reads old schema; a cross-pod aggregate query sums rows from both, returning doubled counts.*

**H4 — Request-scoped flag snapshot** — The read-path flag must be evaluated exactly once at request entry and the result held constant for the request lifetime; evaluating it per-DB-call allows schema mixing within a single request during the activation window and violates V.4. This is the mechanism that makes V.4 satisfiable and must appear in D.4's design.
*Falsifier: feature flag evaluated on each DB call inside a request handler; flag activates between the first and second call; request reads from old schema on the first query and new schema on the second; V.4 violated silently.*

**H5 — ORM / connection-pool schema cache invalidation after expand DDL** — Existing database connections that have cached schema metadata do not see objects created by expand DDL until the cache is refreshed. The migration design must specify a connection-pool invalidation or forced reconnect step after expand DDL, before dual-write code is deployed.
*Falsifier: expand DDL creates new_table; application ORM has a per-connection schema cache that predates the DDL; dual-write INSERT into new_table on an existing connection throws "relation does not exist"; divergence silently accumulates until connections are naturally recycled.*

**H6 — Prepared-statement invalidation at contract DDL** — In PostgreSQL (and equivalent engines), dropping a column invalidates any server-side cached prepared statements that reference it. The migration design must include a plan to drain or explicitly close stale prepared statements before or immediately after contract DDL, or to handle the re-preparation error gracefully.
*Falsifier: contract DDL drops old_column; engine marks the cached plan for `SELECT … WHERE old_column = $1` invalid; the next execution on any connection returns "cached plan must not change result type"; application errors at full traffic rate until all statements are re-prepared.*

**H7 — Multi-table parent-before-child backfill ordering** — When the schema split produces multiple new tables with FK relationships between them (e.g., new_parent and new_detail), the backfill job must insert parent rows before child rows for each chunk. D.3 specifies chunked upsert but not inter-table ordering; V.16 covers cascade semantics but not insertion sequence during bulk copy.
*Falsifier: backfill processes new_detail rows before their corresponding new_parent rows exist; FK violation on insert; backfill fails for the child table with no clear remediation path.*

**H8 — Table bloat from VACUUM blockage during long backfill** — Multi-day backfills under active logical replication slots or long-running transactions prevent the engine's VACUUM process from reclaiming dead tuples on the migrated table, causing progressive bloat and query-plan degradation. V.14 covers WAL retention and replication slot horizons but not the VACUUM/bloat consequence on query performance.
*Falsifier: 5-day backfill runs with an active logical replication slot; dead-tuple accumulation on old_table reaches 10×; the query planner chooses sequential scans; read latency on old_table degrades past SLA during the migration window.*

**H9 — Seam D.8 → D.10 (phase transitions as observable events)** — Each D.8 phase transition must be emitted as a timestamped event into D.10's observability system; without this record there is no automated audit trail for the migration. Dep.13 covers the reverse direction (D.10 format feeding D.8 gate evaluation) but not D.8 emitting its own transitions outward.
*Falsifier: migration completes; a post-incident review requires knowing when each phase was advanced and by whom; D.10 has no record of phase transition events; the audit relies on operator chat logs.*

---

## Count

9 genuinely new holes.
