# T06 — Search Pass 3

Input: D2 (55-item basis). Only genuinely new holes listed — no restatements of covered items.

---

**H1 · CDC connector cursor-state backup**
CDC pipelines (Debezium, DMS, Kafka Connect source connectors) store their own offset/cursor metadata separately from both the source DB WAL and the consumer-side queue offsets covered by Dep9. Dep9 addresses consumer-side rollback (Kafka consumer group offsets); this is the producer-side connector state (Zookeeper znodes, Kafka Connect internal-offsets topic, Debezium schema-history topic). A restore that does not align CDC cursor state to the DB restore point T1 causes the connector to resume from a stale offset: events committed before T1 are re-emitted (duplicates), or events in [cursor, T1] are skipped (gaps). Distinct falsifier from Dep9.
*Falsifier*: in a restore drill with an active CDC pipeline, verify that the connector's stored cursor/offset is restored or reset to the WAL LSN corresponding to DB restore point T1; post-restore CDC replay for the window [T1, T1+δ] produces zero duplicate events and zero skipped events.

**H2 · Backup size anomaly detection**
D6 checks size > 0 and validates checksum. A backup that is valid (non-zero, correct checksum, non-empty) but represents only a fraction of the expected dataset — due to a misconfigured scope, a silent filter, a truncated export, or a partial flush — is certified healthy and discovered only at restore time. No item in D6 or D7 triggers on an anomalous shrinkage relative to historical baselines.
*Falsifier*: inject a backup artifact that passes all D6 checks (non-zero, correct checksum, non-empty record count) but contains only 10% of the prior backup's row count for the same store; an anomaly-detection alert fires before the artifact is marked usable.

**H3 · Backup job retry idempotency**
If a backup job fails midway and is retried (by scheduler or operator), two outcomes are dangerous: (a) a partial artifact is partially registered in the catalog before retry, leaving a dangling entry that PITR assembly may select over the good artifact; (b) a successful retry creates a second artifact for the same window, and the catalog now has two entries for that time slot, creating ambiguity in restore-set assembly. D5 specifies restore-abort/interrupt recovery; no item specifies the backup-side equivalent.
*Falsifier*: simulate a backup job failure at 50% completion followed by automatic retry; verify the catalog contains exactly one valid, complete artifact for that backup window with no dangling partial entries; the artifact passes all D6 integrity checks; a PITR query targeting that window returns the correct artifact unambiguously.

**H4 · Infrastructure DR handoff SLA as hard input to data RTO**
N6 correctly excludes infrastructure-layer rebuild and cross-references a separate infrastructure DR runbook. However, the total recovery time = infra_ready_time + data_restore_time. If the infra DR runbook has no stated completion SLA, or its SLA is not constrained such that (infra_DR_SLA + p99_data_restore_time ≤ RTO), the data recovery RTO is physically unachievable even when the data regime is fully compliant. The cross-reference is present but the composite inequality is not documented or verified.
*Falsifier*: the regime document records the inequality infra_DR_SLA + p99_data_restore_time ≤ RTO for each failure scenario; the cross-referenced infrastructure DR runbook has a documented completion SLA that satisfies this inequality; a joint drill measures both phases end-to-end against the stated RTO.

**H5 · Application-consistent vs. crash-consistent snapshot classification**
D3 specifies WAL/log-based backup for stores with RPO < 15 min and full/incremental/differential for others. For stores backed up via storage-level or VM snapshots rather than DB-native mechanisms, the snapshot may be crash-consistent (storage view at an instant, potentially mid-write) or application-consistent (DB buffers flushed, in-flight transactions completed). A crash-consistent snapshot of a transactional DB requires crash-recovery on restore; for some engines this is fine; for others it produces an inconsistent state or requires WAL continuation that may not be available. Neither D3 nor D5 requires each store's snapshot type to be declared and the restore path for that type to be tested.
*Falsifier*: for every store using snapshot-based backup, the backup type is classified as crash-consistent or application-consistent in the regime document; if crash-consistent, a drill confirms crash-recovery completes and produces a consistent, queryable state within RTO; if application-consistent, the quiesce mechanism (freeze/thaw, VSS writer, DB flush hook) is documented and exercised in the drill.

**H6 · Data residency compliance for backup storage locations**
D4 covers compliance/legal retention duration floors (GDPR, HIPAA, SOX). D3 mandates cross-region replication for freshness. Neither addresses the geographic placement constraint: some regulated data classes are prohibited from leaving specific jurisdictions regardless of encryption. A cross-region replication target or cold-tier archive location may place regulated data in a non-compliant jurisdiction.
*Falsifier*: for each data class with a data-residency obligation, the backup storage regions for all copies (primary backup, cross-region replica, cold-tier archive) are listed in the regime document and verified against applicable regulation; no backup copy for a residency-constrained data class resides in a non-compliant region; a quarterly audit confirms this.

**H7 · SaaS export round-trip fidelity drill**
D1 requires each in-scope SaaS system to have a "documented export/backup mechanism and verified RPO/RTO." Possessing a periodic export file is not equivalent to demonstrating the data can be imported into a clean environment with full fidelity — referential integrity, binary attachments, custom fields, relationship metadata, and API-only data (not in export schema) may be silently omitted. The drill program (D8) does not enumerate a SaaS-specific round-trip exercise scenario.
*Falsifier*: for each in-scope SaaS system with production RPO/RTO obligations, a drill cycle includes a full export → import into a clean tenant/environment → verification of row count, referential integrity, and a sampled set of records including binary attachments; the drill completion record is the SaaS system's restore-drill evidence for that cycle; a missing round-trip drill for a SaaS system is treated the same as a missing drill for any other Tier-1 store.

**H8 · Store dependency graph currency**
D2 requires priority ordering to be "derived from store dependency graph." D5 specifies a priority sequence consistent with that graph. No V item requires the dependency graph to be a versioned artifact that is updated when the infrastructure changes. As new stores are added or inter-store dependencies change, the graph may silently become stale, causing wrong priority sequencing at restore time.
*Falsifier*: the dependency graph is a versioned artifact referenced by D2 and D5; any in-scope infrastructure change (new store onboarded, dependency modified, store decommissioned) triggers a mandatory graph review with a version bump before the change is approved; the priority sequences in D2 and D5 cite the current graph version; an audit of graph version vs. last infrastructure-change date shows no gap.

**H9 · Multi-person authorization to modify backup immutability policy**
V9 ensures that production IAM credentials cannot delete or overwrite backup artifacts. However, the immutability policy itself (Object Lock bucket configuration, WORM retention settings, retention-lock period) can be modified by sufficiently privileged administrators. A single compromised or coerced admin account could disable immutability before deleting all backups. The regime requires immutability as a mechanism but does not govern who can change the policy.
*Falsifier*: the set of principals authorized to modify backup-storage immutability configuration (Object Lock bucket policy, WORM settings, retention lock period) is smaller than the set of principals with production write access; modification of these settings requires at minimum two-person authorization or an out-of-band approval workflow with an audit trail; an attempted single-actor policy modification is blocked or raises an alert.

**H10 · Connection-pool drain completion seam during failover**
D5 includes "application connection-pool drain sequence" as a step in the failover procedure. Dep8 falsifies write connectivity (time from promotion command to first successful write via new primary endpoint ≤ RTO). These are not the same: Dep8 passes the moment the new primary accepts one write; it does not verify that the application tier has drained all connections to the dead primary. If the drain hangs on a long-running query or a stuck transaction, application instances continue directing writes to the old endpoint address while DNS is already updated, and those writes are silently lost or rejected. No Dep or V item measures time-to-zero-connections at the old primary.
*Falsifier*: failover drill measures the time from DNS update to zero active connections against the old primary endpoint at the application-tier level (not at the DB level); this interval must be ≤ the connection-pool drain timeout specified in the runbook; a stuck long-running query on the old endpoint is treated as a drain failure requiring explicit runbook handling.

---

**Total genuinely new holes: 10**
