# T06 — Search 2 (Gap pass over D1)

Only genuinely new content — items not already covered by any D/Dep/V/N entry in D1.

---

**H1 — Catalog self-backup and RPO**
The backup catalog is itself a critical data store with its own RPO/RTO; if it is lost or corrupted in the same event that requires recovery, restore cannot proceed without either a catalog backup or a catalog-reconstruction procedure from raw artifact metadata.
*Falsifier*: simulate catalog loss coincident with primary failure; recovery (full catalog reconstruction from artifact metadata OR restore from catalog backup) completes within RTO, and the assembled restore set matches what the live catalog would have returned.

**H2 — DB engine upgrade → post-upgrade restore-drill gate**
D3 addresses schema-migration coordination but not DB engine version upgrades; a major-version upgrade can change WAL format, backup compression, or tool API such that backup jobs appear to succeed but produce unrestorable artifacts.
*Falsifier*: policy mandates a blocking restore-drill from the first backup produced after any DB engine major-version upgrade before the upgrade is declared production-stable; no such upgrade is approved without a drill completion record.

**H3 — Restore network bandwidth as a hard RTO input**
RTO is composed from per-step restore timings (D5, V2) but network bandwidth available during a DR event is never modeled; for large stores, transfer time alone (data_volume / WAN_bandwidth) can exceed RTO while all other steps are within spec.
*Falsifier*: for every store, compute ceil(data_volume / minimum_restore_network_bandwidth) and verify the result ≤ RTO minus all non-transfer steps; this formula appears in the regime document alongside the standard V2 timing model.

**H4 — Read traffic routing after failover**
Dep8 and D5 cover write connectivity after replica promotion (DNS/LB update for the write endpoint), but application read traffic directed to read-replica endpoints, read-only connection strings, or CDN-cached query layers is not rerouted or invalidated; reads silently serve stale or unavailable data after the old primary disappears.
*Falsifier*: after a replica-promotion drill, measure time until all declared read endpoints (read replicas, read-only DNS records, CDN purge) are serving correct data from the new topology; must be ≤ RTO.

**H5 — KMS service restoration runbook**
D5 lists "secrets/KMS → config stores → primary DB → …" as the recovery priority sequence, but specifies no procedure for the case where the KMS service itself must be restored from its own backup before any encrypted backup can be decrypted; the bootstrap ordering (restore KMS infrastructure → verify key retrieval → decrypt data backups) is unspecified.
*Falsifier*: runbook contains an explicit "KMS service unavailable" scenario with step-by-step KMS restore procedure; a dedicated drill exercises this path and completes within RTO with successful decryption of a data backup immediately afterward.

**H6 — Backup agent credential rotation → job continuity seam**
When IAM roles, service-account keys, or storage-access tokens used by backup agents are rotated for security hygiene, backup jobs may silently fail if the agent's credential cache is not updated in lockstep; D7 alerts on job failure only after the credential has already expired and one backup window has been missed.
*Falsifier*: a pre-rotation checklist mandates updating all backup agents before the old credential is revoked; simulate a rotation event and verify zero backup jobs fail during the rotation window.

**H7 — In-transit encryption of backup streams**
D6 covers at-rest encryption (key escrow, V18) but no item requires that backup data is encrypted in transit across all channels (WAL shipping streams, cross-region object-storage copy, backup agent → storage API); an unencrypted stream can be intercepted without triggering any existing check.
*Falsifier*: packet capture during a backup job on each channel (WAL shipping, cross-region copy, catalog sync) shows no plaintext backup data; TLS version ≥ 1.2 enforced and audited.

**H8 — Schema migration WAL/LSN anchor logging for PITR boundary correctness**
D3 requires a "migration-backup coordination procedure" (falsifier: "runbook exists") but does not require logging the exact WAL LSN or timestamp of each schema migration as a named restore anchor; a PITR restore that crosses a migration boundary without knowing the exact LSN may apply the DDL twice (restoring before the migration into a post-migration backup chain) or not at all, producing a corrupt or wrong schema.
*Falsifier*: the migration procedure mandates recording the LSN / commit timestamp of every DDL change as a named catalog anchor; given a migration event at LSN L, restore to L−1 yields the pre-migration schema and restore to L+1 yields the post-migration schema, both verified in a drill.

**H9 — Restore abort and rollback procedure for interrupted restores**
No item specifies what happens if a restore is interrupted midway (network drop, storage failure, operator error): a half-applied restore can leave a DB in an inconsistent state worse than the original failure, and restarting the restore may not be idempotent.
*Falsifier*: interrupt a restore at the 50% mark; verify the system returns to a known recoverable state (either original pre-restore state, or the restore is checkpointed and resumable); the procedure for this is documented in the runbook.

**H10 — SaaS-hosted authoritative state: explicit scope boundary**
D1's store enumeration is a technical taxonomy (OLTP, OLAP, object stores, etc.) that implicitly excludes data residing in SaaS platforms (CRM, ticketing, analytics SaaS, payment processors); if any SaaS system holds authoritative state with production RPO/RTO obligations, it is neither declared in scope nor explicitly excluded with a rationale.
*Falsifier*: the scope document contains an explicit SaaS inventory section: every SaaS system is either (a) declared in scope with a documented export/backup mechanism and verified RPO/RTO, or (b) declared out of scope with a signed business-acceptance rationale for the data-loss exposure.

**H11 — Intentionally empty store exception in integrity checks**
D6 requires "record count > 0" as a validity gate after every backup; a legitimately empty store (newly provisioned, pre-population, or genuinely empty by design) fails this check, causing either false alerts or, if the check is suppressed, a silent gap in coverage for stores that later receive data.
*Falsifier*: provisioning an empty store generates a baseline "intentionally empty" attestation stored in the catalog; the D6 record-count check accepts zero-record artifacts only when this attestation exists and was created within the last backup cycle; a store without an attestation that produces a zero-record artifact triggers the standard rejection alert.

**H12 — Partial failover: restore + concurrent live writes, catch-up and cutover**
D5 covers full-region failover and store-level restore as separate scenarios; a partial failover (one region/store down, another live and accepting writes) requires a restore on the failed side while production writes continue on the live side — creating an ever-widening divergence that must be closed by catch-up replication before cutover; this combined procedure is not in D5.
*Falsifier*: partial failover drill: restore initiated on the failed side while writes continue at a measured rate on the live side; procedure includes a catch-up replication phase; drill passes when the restored side reaches ≤ RPO lag from live and cutover is completed without write loss, all within RTO.

**H13 — Backup storage utilization ceiling vs. retention enforcement timing**
D7 alerts at 75%/90% storage utilization; D4 automates expiry. But there is no item specifying that the retention-engine expiry job must run and complete before the storage utilization alert threshold is reached during normal operation, i.e., the expiry cadence must be fast enough that accumulation never reaches 90% between expiry runs; a slow or stuck expiry job silently drives storage toward 100%, where the next backup fails noisily.
*Falsifier*: compute max_accumulation_rate × expiry_run_interval and verify it is ≤ (90% − steady_state_utilization) × total_capacity; alert if the expiry job has not completed within its scheduled window; this bound appears as a formula in the regime document.

---

**New holes: 13**
