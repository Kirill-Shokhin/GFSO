# T06 — Search pass 1 (exhaustive enumeration, no prior decomposition)

Task: Design the operating regime that continuously keeps a production data estate recoverable
within stated RPO/RTO targets: scope, backup cadence/retention tiers, restore/failover procedure,
periodic restore-drills, integrity/freshness checks. Specify the rules so a recovery would actually succeed.

---

## Domain Primitives

DP1: **RPO definition per store** — Maximum tolerable age of the most recent restorable snapshot for each data store, expressed in time units. *Falsifier*: formula audit shows worst-case time between any failure moment and the nearest prior restorable backup ≤ stated RPO for every store.

DP2: **RTO definition per store** — Maximum tolerable elapsed time from failure declaration to service restored, per store or per failure scenario. *Falsifier*: timed drill sum of all restore steps ≤ stated RTO.

DP3: **Recovery point** — The specific point in time a backup can restore to; distinct from backup completion time. *Falsifier*: restore to a stated recovery point T and verify record state matches expected state at T.

DP4: **PITR capability** — Point-in-time recovery using continuous log shipping; required for low-RPO stores. *Falsifier*: restore to an arbitrary minute within the log-shipping window; verify exact record state.

DP5: **Backup types taxonomy** — Full, incremental, differential, log/WAL-based; each store must declare which type(s) it uses and why. *Falsifier*: regime document lists type per store; no store is undeclared.

DP6: **Recovery tier priority** — Ordering of which stores are recovered first when a multi-store failure occurs; must derive from business criticality. *Falsifier*: restore runbook contains explicit priority sequence with justification.

---

## Scope Determination

SC1: **Authoritative data store inventory** — All production data stores are enumerated and classified: OLTP databases, OLAP / warehouse, caches (Redis, Memcached), message queues (Kafka, RabbitMQ), object stores (S3, GCS, Azure Blob), file systems / NFS mounts, search indices (Elasticsearch, OpenSearch), secrets managers (Vault, AWS Secrets Manager), config stores (etcd, Consul), audit/event logs, session stores. *Falsifier*: diff inventory against live infrastructure; zero unregistered stores.

SC2: **State vs. derived/reconstructable designation** — Each store is classified: authoritative state (must back up), derived/reconstructable (rebuild from upstream is cheaper and faster). Derived stores still need a recovery path documented. *Falsifier*: every store has an explicit classification; "derived" stores have a documented rebuild procedure with timed estimate ≤ its RTO.

SC3: **In-scope environment declaration** — Exactly which environments (prod, prod-replica, prod-adjacent) are covered; dev/staging explicitly declared in or out. *Falsifier*: regime document lists environments; any environment that holds a copy of prod data is in scope.

SC4: **Business criticality tier per store** — Tier drives RPO/RTO target. Must be formally assigned and signed off. *Falsifier*: every store has a tier; tier changes trigger mandatory RPO/RTO review.

SC5: **Transient / ephemeral state** — In-flight messages, in-process jobs, session state not persisted to a durable store: explicitly documented as acceptable loss or handled by idempotency design. *Falsifier*: regime document has a section on ephemeral state; no silent assumption of zero loss.

---

## Backup Cadence Design

BC1: **Cadence per store** — Backup frequency chosen so that worst-case RPO math holds: cadence + max_backup_duration ≤ RPO. *Falsifier*: for every store, verify formula cadence + p99_backup_duration ≤ RPO_stated.

BC2: **Continuous WAL/log shipping for low-RPO stores** — Stores with RPO < 15 min require streaming log replication, not scheduled snapshots. *Falsifier*: measure lag between primary write and log landing in backup store; must be < RPO.

BC3: **Full backup schedule** — Frequency of full backups; determines the depth of the incremental chain and the worst-case restore assembly time. *Falsifier*: restore time from oldest permitted incremental chain ≤ RTO.

BC4: **Incremental / differential schedule** — Defined cadence; chain length bounded so restore time stays within RTO. *Falsifier*: maximum chain length × average incremental restore time ≤ RTO.

BC5: **Backup window vs. peak load** — Backup I/O must not degrade production SLA during peak. *Falsifier*: backup-during-peak load test shows no SLA breach; or backup is explicitly rate-limited with documented ceiling.

BC6: **Cross-region replication cadence** — How quickly backups are copied to the secondary region / account; lag must be within RPO. *Falsifier*: measure secondary region backup freshness at failure simulation; must be ≤ RPO.

BC7: **Schema / DDL change coordination with backups** — Backup taken mid-migration may be partially in old schema, partially new. Procedure for coordinating migrations with backup scheduling. *Falsifier*: migration-backup coordination runbook exists; drill it.

---

## Retention Tiers

RT1: **Tier definition** — Hot (recent, fast restore, costly), warm (medium-term), cold/archive (long-term, cheap, slow restore); defined storage class per tier. *Falsifier*: tier specifications are documented; restore time from cold tier is benchmarked and ≤ RTO if cold restore is a valid path.

RT2: **Retention duration per tier per store** — Minimum retention long enough that at least one full chain to within RPO exists at any moment; maximum retention bounded by cost/compliance. *Falsifier*: audit: min_retention ≥ RPO + operational_response_buffer for every store.

RT3: **Compliance / legal retention floor** — Regulatory requirements (GDPR, HIPAA, SOX, etc.) impose minimum retention that may exceed operational needs; must be tracked separately. *Falsifier*: compliance requirements are documented per data class; retention policy ≥ compliance floor.

RT4: **Automated expiry with dependency awareness** — Retention engine must not delete a full backup that still anchors an active incremental chain. *Falsifier*: attempt to expire a base backup with live dependents; system blocks deletion or chain is pre-sealed.

RT5: **Tiered promotion policy** — Rules for moving backups from hot → warm → cold on a schedule, without breaking restore paths. *Falsifier*: restore from a backup that has been promoted to cold; succeeds within documented cold-restore RTO.

RT6: **Backup count floor monitoring** — Expected number of backups per store per tier is tracked; alert fires if count drops below minimum. *Falsifier*: delete one backup; alert fires before next backup run.

---

## Restore / Failover Procedure

RF1: **Step-by-step restore runbook per failure scenario** — Not generic; covers each store type and each failure class (single-store failure, multi-store, region failure). *Falsifier*: runbook exists, is version-controlled, and drill log shows it was executed successfully within the last drill cycle.

RF2: **Recovery priority sequence** — Documented order: secrets/KMS first, then config stores, then primary DB, then application tier, then secondary stores. Derived from dependency graph. *Falsifier*: dependency graph exists; order is consistent with it.

RF3: **Failover vs. restore decision rule** — Criteria for choosing replica promotion (faster, possibly small data loss) vs. backup restore (slower, zero data loss from backup point). *Falsifier*: decision tree in runbook; drill covers both paths.

RF4: **Replica promotion procedure** — Steps to promote a read replica to primary: stop replication, verify replica lag, promote, redirect writes, update DNS/load balancer, notify app tier. *Falsifier*: end-to-end drill from promotion command to first successful application write ≤ RTO.

RF5: **DNS / load balancer cutover** — After failover, DNS must be updated or load balancer reconfigured before application can reach new primary. TTL must be ≤ RTO. *Falsifier*: measure time from failover decision to DNS propagation completion; must fit RTO.

RF6: **Application-level cutover sequence** — Application connection pools must be drained and re-pointed; in-flight requests handled. *Falsifier*: drill shows zero application errors (or only expected transient errors) during cutover within RTO.

RF7: **Partial failure restore** — One store failed, not all. Runbook covers mixed-state recovery without full-estate restore. *Falsifier*: drill exercises single-store failure; other stores remain live.

RF8: **Table / collection level restore (surgical)** — Accidental drop of one table/collection: recover it without rolling back the entire DB. Requires PITR or snapshot with export capability. *Falsifier*: drill restores a single dropped table; remainder of DB is unaffected.

RF9: **Post-restore validation checklist** — Steps to verify restore succeeded: row counts, last-write timestamp, application smoke test, cross-store consistency check. *Falsifier*: runbook contains explicit validation checklist; drill log shows it was completed.

RF10: **Failover communication protocol** — Who declares failure, who initiates restore, who approves cutover, who notifies stakeholders. *Falsifier*: RACI for failover exists; drill exercises the full communication chain.

---

## Integrity and Freshness Checks

IF1: **Backup completion verification** — Each backup job must confirm it finished (not just started) and wrote a non-zero, structurally valid artifact. *Falsifier*: inject a job that exits mid-run; verify catalog marks it incomplete and alert fires.

IF2: **Checksum / hash validation post-write** — SHA-256 or equivalent computed at backup creation and verified before the backup is marked usable. *Falsifier*: flip a byte in a stored backup; integrity check detects mismatch.

IF3: **Backup content sampling (spot-restore test)** — Periodic automated restore of a random sample of records from the backup, compared against a known state. *Falsifier*: corrupt backup data (not just the checksum); spot-restore test catches it.

IF4: **Freshness check per store** — Automated check: age of most recent usable backup ≤ RPO. Fires alert if breached. Alert threshold is RPO minus response-time buffer (not RPO itself). *Falsifier*: stop the backup job; alert fires before RPO elapses.

IF5: **Incremental chain integrity validation** — After each incremental write, verify the chain pointer to the base backup is valid and the base backup exists. *Falsifier*: delete the base backup without updating the chain; chain validator detects broken link.

IF6: **WAL / log shipping lag monitoring** — Continuous check that log shipping lag < RPO. Separate from backup freshness (covers the continuous-write path). *Falsifier*: pause log shipping; alert fires before RPO elapses.

IF7: **Cross-region replication freshness** — Secondary region backup is checked for freshness: age ≤ RPO. *Falsifier*: pause cross-region replication; alert fires before RPO elapses.

IF8: **Catalog integrity scan** — Backup catalog entries are periodically validated: referenced files exist, checksums match, recovery times are correct. *Falsifier*: delete a file from backup storage; catalog scan flags the orphaned entry within one scan cycle.

IF9: **Encryption key escrow validation** — Backups are decryptable using the escrowed key, not just the live key. *Falsifier*: annual drill: restore from backup using escrowed key only (primary key deliberately excluded from test environment).

IF10: **Zero-byte / empty backup detection** — Integrity check explicitly validates size > 0 AND record count > 0 (for structured stores). *Falsifier*: produce a zero-byte backup artifact; it is rejected and alert fires.

---

## Restore Drills

DR1: **Drill schedule** — Mandatory calendar-enforced drill frequency per criticality tier (e.g., Tier-1 stores: quarterly; Tier-2: semi-annual). Not advisory. *Falsifier*: missed drill triggers a formal incident; last drill date is tracked in a registry.

DR2: **Drill scope per iteration** — Each drill cycle must cover: full-estate restore (at least once per year), single-store restore, table-level restore, region-failover. *Falsifier*: drill log shows all scenario types were exercised within the defined cycle.

DR3: **Drill environment specification** — Isolated environment that matches production spec (same OS/DB version, same hardware tier). Production is never the drill target. *Falsifier*: drill environment spec is documented and verified before each drill.

DR4: **Drill success criteria** — Objective pass/fail criteria: restore completes within RTO, data matches known state within RPO, application smoke tests pass. *Falsifier*: drill report contains explicit pass/fail verdict against criteria; no subjective grading.

DR5: **Drill timing measurement** — Each restore step is timed; total is compared to RTO. *Falsifier*: drill log contains per-step timing; sum is computed and compared to RTO.

DR6: **Drill finding registry and remediation** — Gaps found in drills are tracked to closure; runbook version is bumped after each remediation. *Falsifier*: no open drill findings older than one drill cycle; each finding has a ticket and a resolution commit.

DR7: **Drill runbook identity with real runbook** — The procedure followed in the drill is identical to the real recovery runbook (same document, same version). *Falsifier*: drill report cites runbook version; real runbook version matches; diff is zero or explicitly annotated.

DR8: **Credential validity pre-check in drill** — Drill procedure includes verification that all credentials, keys, and access tokens required for restore are current and accessible. *Falsifier*: drill log shows credential pre-check step; if a credential is expired, drill halts and raises a finding.

---

## Monitoring and Alerting

MA1: **Backup job failure alert** — Any backup job that fails or produces an invalid artifact triggers an immediate alert. *Falsifier*: kill a backup job mid-run; alert fires within 5 minutes.

MA2: **RPO-proximity alert** — Alert fires when backup age exceeds RPO minus response buffer (not when RPO is already breached). *Falsifier*: stop backup; alert fires while recovery is still possible within RPO.

MA3: **Replication lag alert** — Log shipping / replication lag exceeds threshold (RPO/2) triggers alert. *Falsifier*: pause replication; alert fires before RPO/2 elapses.

MA4: **Storage capacity alert** — Backup storage utilization alert at 75% and 90%; backup jobs must not silently fail at 100%. *Falsifier*: fill storage to 90%; alert fires; backup job at 100% fails noisily (not silently).

MA5: **Backup count floor alert** — Expected number of valid backups per store per tier; alert if count drops below floor. *Falsifier*: delete one backup; alert fires before next scheduled backup.

MA6: **Cross-region replication freshness alert** — Secondary region backup age monitored; alert if stale beyond RPO. *Falsifier*: pause replication; alert fires within RPO window.

MA7: **Catalog integrity alert** — Catalog scan findings trigger alert. *Falsifier*: manually corrupt a catalog entry; alert fires within one scan cycle.

---

## Cross-Component Interaction Seams

XS1: **WAL/log shipping → backup catalog → PITR restore path** — Log shipping deposits segments; catalog records LSN and timestamp; PITR restore queries catalog to assemble the correct sequence. If catalog lags or misses a segment, PITR produces a gap with no error. *Falsifier*: restore to an arbitrary timestamp T; verify record state at T matches a known pre-taken snapshot of that exact moment.

XS2: **Full backup → incremental chain → restore assembly** — Incremental backups reference a base full backup. If the full backup is silently corrupt, all dependents are unrestorable. *Falsifier*: corrupt the base full backup checksum; verify restore attempt fails with explicit error, not silent data corruption.

XS3: **Backup job → retention engine → storage cleanup** — Retention engine may expire a full backup that still anchors an active incremental chain, breaking the only restore path. *Falsifier*: configure retention to target a base backup with live dependents; verify deletion is blocked or chain is explicitly sealed first.

XS4: **Backup write → integrity check → restore input** — If the integrity check validates a stored artifact but the restore reads from a different path or a stale copy, the check is meaningless. *Falsifier*: corrupt a backup byte after integrity check passes; trigger restore from the same path; verify mismatch is caught before restore completes.

XS5: **Freshness alert → on-call response → backup reinvocation** — Alert threshold set at RPO (not RPO minus buffer) means human response time consumes the entire remaining window; RPO is breached before action completes. *Falsifier*: measure median on-call response time; verify alert_threshold + response_time + backup_duration ≤ RPO.

XS6: **DB restore → application secrets/encryption keys → decryptability** — DB is restored to T1; the encryption key version active at T1 may differ from the current live key. Restore produces unreadable data. *Falsifier*: restore DB from a backup taken before the last key rotation; verify application can read all records.

XS7: **DB restore → cache state → cross-store consistency** — Cache is restored to T2, DB is restored to T1 < T2. Cache holds stale (future) entries for rows rolled back in the DB restore. *Falsifier*: post-restore runbook includes mandatory cache invalidation; drill verifies no stale cache reads after restore.

XS8: **Replica promotion → DNS/load balancer → application connectivity** — Replica promoted to primary; DNS TTL too high; clients still direct writes to the dead primary address. *Falsifier*: measure time from promotion command to first successful application write through the new primary endpoint; must be ≤ RTO.

XS9: **Message queue consumer offsets → DB restore → replay correctness** — DB restored to T1; Kafka consumer offsets are at T2 > T1; replay from T1 to T2 re-processes already-committed transactions producing duplicates. *Falsifier*: restore scenario with active queue shows no double-processing of records committed before T1; consumer offset rollback procedure exists and is tested.

XS10: **Object store → DB foreign keys → post-restore referential integrity** — Object store (S3) versioned to T1; DB restored to T1; but DB references object keys written between T1 and T2 that do not exist in the T1 object store. *Falsifier*: post-restore referential integrity check between DB foreign keys and object store key listing; zero dangling references.

XS11: **Backup cadence + backup duration → actual RPO achieved** — Backup runs every 1h; backup takes 45 min; failure occurs 5 min into a backup run; actual data loss window = 1h45m > stated 1h RPO. *Falsifier*: formula: worst_case_RPO = cadence + p99_backup_duration; must be ≤ RPO_stated for every store.

XS12: **KMS/encryption key escrow → backup decryptability over time** — Backups encrypted at rest; key rotated; old backups encrypted under previous key version; without key escrow those backups become unreadable. *Falsifier*: restore from a backup created before the last key rotation event using only the key available at that time.

XS13: **Restore drill findings → runbook update → next drill** — Drill surfaces a procedural gap; gap is not tracked; next drill uses the same flawed runbook; drift accumulates. *Falsifier*: drill finding registry requires a runbook version bump before the finding can be closed; next drill cites updated runbook version.

XS14: **New data store added → backup inventory → RPO coverage** — New store deployed; not added to backup inventory; no backup ever runs; discovered only at recovery time. *Falsifier*: infrastructure provisioning pipeline has a gate: new store is not promoted to production until it appears in the backup inventory with a verified first backup.

XS15: **Restore environment spec → drill execution → runbook applicability** — Drill runs on a lower-spec environment (different DB version, less RAM); procedure succeeds; real restore on prod-spec hardware fails or behaves differently. *Falsifier*: drill environment spec is compared to current prod spec before every drill; discrepancies are findings.

---

## Global Invariants

GI1: **RPO coverage completeness** — For every store in scope, worst_case_RPO = max(cadence + p99_backup_duration) ≤ RPO_stated. No store is exempt. *Falsifier*: automated weekly audit of this formula across all stores; any violation is an incident.

GI2: **RTO coverage completeness** — Sum of all timed restore steps for each defined failure scenario ≤ RTO_stated. *Falsifier*: drill timing log; sum computed and compared to RTO after every drill.

GI3: **Backup independence from failure domain** — Backups are stored in a storage account / region / medium that is logically and physically independent of the systems they protect. A failure that takes down the primary cannot simultaneously take down the backups. *Falsifier*: simulate primary-region loss; verify backups are fully accessible from secondary region without any primary-region credential.

GI4: **No silent backup path failure** — If any component in the backup pipeline fails (agent, network, storage, catalog), an alert fires before RPO elapses. *Falsifier*: kill each pipeline component in turn; verify alert fires within RPO minus response buffer each time.

GI5: **Monotonic inventory coverage** — Every data store currently in production is covered by the backup regime at all times. New stores do not enter a coverage gap. *Falsifier*: diff live infrastructure inventory against backup inventory weekly; zero gap tolerated beyond a defined grace period.

GI6: **Restore correctness** — A restored system agrees with the pre-failure authoritative state on a sampled set of records. *Falsifier*: inject known data immediately before a simulated failure; restore; verify all injected records present and uncorrupted.

GI7: **Catalog queryability** — Given a target recovery time T, the backup catalog can identify the correct backup set within 5 minutes. *Falsifier*: time the catalog query for an arbitrary T; must be < 5 minutes (or whatever time is budgeted in the RTO).

GI8: **Retention floor enforced** — At any moment, at least one complete restore chain (full + incrementals + logs) to within RPO exists and has not been expired. *Falsifier*: audit: earliest usable restore point for each store ≤ RPO before now.

GI9: **Immutability / tamper resistance of backups** — Backups cannot be modified or deleted by any actor who can also compromise the production environment (ransomware / insider threat). Object Lock, WORM, or air-gap required. *Falsifier*: attempt to delete or overwrite a backup from a production IAM role; operation is denied.

GI10: **Regime self-consistency** — RPO/RTO targets, backup cadence, retention policy, and drill schedule are internally consistent (no contradiction where one parameter makes another impossible to satisfy). *Falsifier*: formal consistency check: cadence + duration ≤ RPO; min_retention ≥ RPO + buffer; drill_frequency ≤ max_drift_tolerance.

---

## Edge and Boundary Cases

EB1: **Backup runs exactly at schema migration** — Migration commits at T; backup captures pre-migration schema; post-migration data may be unrestorable to the backup schema cleanly. *Falsifier*: migration-backup coordination procedure exists; drill covers a migration that coincides with backup window.

EB2: **Store size exceeds backup window** — A 10 TB table takes 6h to back up; RPO is 4h. Backup duration invalidates RPO math. *Falsifier*: benchmark backup duration for each store at current and projected future size; must satisfy formula in GI1.

EB3: **Maximum elapsed time between drills enforced** — Runbook drift accumulates between drills; maximum gap is a hard calendar gate, not a target. *Falsifier*: a missed drill triggers a formal risk acceptance process, not silent deferral.

EB4: **Multi-store simultaneous failure** — Primary DB and replica fail simultaneously; no warm failover. Runbook must cover cold restore from backup, not just promotion. *Falsifier*: drill exercises total-loss scenario; runbook has an explicit "no replica available" path.

EB5: **Backup storage capacity exhaustion** — Storage hits 100%; new backup jobs fail; nobody notices for hours. *Falsifier*: capacity alert fires at 75% and 90%; backup failure triggers immediate alert regardless of storage state.

EB6: **RPO/RTO target revision** — Business changes SLA; backup cadence not updated; regime silently violates new targets. *Falsifier*: SLA change management process includes mandatory backup regime review before new SLA takes effect.

EB7: **Network partition mid-backup** — Backup agent loses connectivity; writes a partial artifact; catalog marks it complete. *Falsifier*: simulate interrupted backup; verify catalog marks it incomplete and the artifact is never used as a restore base.

EB8: **Clock skew between backup host and catalog** — Catalog timestamp is off by hours; PITR window computed incorrectly; restore lands at wrong point. *Falsifier*: NTP synchronization is a stated, monitored prerequisite for all backup hosts.

EB9: **Restore to a non-identical environment** — Hardware, OS, or DB version differs from production; restore procedure produces a subtly different result. *Falsifier*: drill environment spec is version-locked to current production spec; spec drift is a drill finding.

EB10: **Credentials used in restore expired** — Restore runbook references credentials that rotate on a shorter cycle than drills. *Falsifier*: drill includes an explicit credential-validity pre-check step; expired credentials are a drill blocker.

EB11: **Backup encryption key rotation without escrow update** — Key is rotated; escrow is not updated; old backups become unreadable. *Falsifier*: key rotation procedure includes mandatory escrow update step; verified by next scheduled escrow validation drill.

EB12: **Replica lag at failover decision point** — Replica lag is nonzero at the moment of promotion; last N seconds of transactions are silently lost; application assumes zero loss. *Falsifier*: post-failover transaction audit: last committed transaction ID on old primary (from crash logs) vs. promoted replica; delta is documented and accepted or reprocessed.

---

## Silent Failure Modes

SM1: **Backup reports success, artifact is unrestorable** — Job exits 0; file is corrupt or incomplete; no post-write validation. *Falsifier*: mandatory integrity check (checksum + spot-restore) after every backup job; job success without integrity pass is treated as failure.

SM2: **Replication lag exceeds RPO, no alert** — Read replica lag grows; backup is taken from the lagging replica; effective RPO = RPO_stated + lag; no alert fires. *Falsifier*: replica lag monitoring with alert threshold at RPO/2.

SM3: **Retention deletes a backup early due to policy bug** — A clock or policy bug expires backups before the stated retention period; nobody notices until recovery is needed. *Falsifier*: backup count floor monitoring; expected count per store per tier; alert fires on undershoot.

SM4: **Catalog corrupts silently** — Catalog entries point to moved, deleted, or corrupted files; catalog scan runs only at restore time. *Falsifier*: scheduled catalog integrity scan (at least daily); findings are alerted.

SM5: **Incremental chain pointer is wrong without detection** — Incremental backup uploads; chain pointer references wrong base LSN; chain is unrestorable but catalog shows green. *Falsifier*: chain-validation step runs after every incremental write; verifies base backup exists and is accessible.

SM6: **Cross-region replication silently stops** — Replication jobs stop days or weeks ago; primary region backups are current; secondary has old copies; DR test would fail. *Falsifier*: cross-region freshness check runs on schedule; secondary backup age ≤ RPO enforced by alert.

SM7: **Backup immutability misconfigured** — Object Lock set on bucket but objects uploaded without the lock flag; backups are deletable. *Falsifier*: audit: attempt to delete a backup using production credentials; verify deletion is rejected.

SM8: **Monitoring itself fails** — The system that checks backup freshness and fires alerts is down; backup jobs fail; no alerts fire. *Falsifier*: monitoring system has its own watchdog; dead-man's switch fires if no heartbeat within RPO window.

SM9: **Application silently reads stale cache post-restore** — DB restored to T1; cache invalidation step missed; application serves stale data from T2 cache with no error. *Falsifier*: post-restore application smoke test includes a read of a record known to differ between T1 and T2; stale read is detected.

SM10: **Backup job schedule drifts** — Scheduler clock drift or leap-second handling causes backups to run 61 minutes apart instead of 60; RPO math is silently violated. *Falsifier*: backup job actual start times are logged and compared to scheduled times; drift > threshold triggers alert.

---

## Scope Boundaries

SB1: **Logical / application-level data corruption** — A bug writes wrong values for weeks; backup faithfully preserves the corrupted data. OUT OF SCOPE for the backup regime (backup fidelity ≠ data quality). Back IN scope only if the regime explicitly commits to supporting logical corruption recovery via PITR + data quality checkpoints. *Falsifier*: scope document explicitly states this exclusion.

SB2: **Active-active replication as DR** — Active-active is an architectural choice, not a backup. Where it serves as the failover mechanism for a specific store, the regime must document it as such and verify its RPO/RTO; the replication infrastructure design itself is out of scope. *Falsifier*: regime document lists which stores use replication-as-failover vs. backup-and-restore; both paths have tested RPO/RTO.

SB3: **Ransomware / security incident full response** — The backup immutability and air-gap requirement IS in scope; the full incident response playbook is NOT. *Falsifier*: immutability setting (S3 Object Lock or equivalent) is explicitly specified and audited; cross-reference to the security incident runbook exists.

SB4: **Application binary rollback** — Rollback of a deployment artifact is a CI/CD concern. Data state rollback (DB restore) is in scope; code rollback is not. *Falsifier*: regime document explicitly delimits the boundary: "this regime restores data state, not application binaries."

SB5: **Development and staging environments** — Out of scope unless they hold a copy of production data (e.g., prod-clone staging), in which case that data is in scope. *Falsifier*: regime document lists in-scope environments; any environment that runs prod data is verified to be included.

SB6: **Disaster recovery network / infrastructure rebuild** — Restoring the compute, networking, and orchestration layer is an infrastructure DR concern. This regime covers data recovery only; it assumes infrastructure is available or restored by a separate runbook. Cross-reference required. *Falsifier*: restore runbook has an explicit prerequisite: "infrastructure layer is operational"; cross-reference to infrastructure DR runbook exists.
