# FROZEN BLIND JUDGE — verdict for T06 candidate D1

Reference: T06 (Backup & disaster-recovery regime). Candidate: one decomposition (origin blind).
Matching is meaning-only on each reference item's truth-maker (binding rule §2). `Del`/authority not scored.

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "Enumerate all production data stores ... classify each as authoritative state or derived/reconstructable" + (D2) "maximum tolerable data age (RPO) in time units; maximum tolerable restore/failover duration (RTO)" | objectives + inventory + derived/source classification all named; candidate D2 (RPO/RTO assignment) collapses here = ballast |
| D2 | D | — | COVERED | "select backup type (full/incremental/differential/WAL-log-based) and cadence such that cadence + p99_backup_duration ≤ RPO_stated" | capture pass: type + cadence sized to RPO |
| D3 | D | — | COVERED | "Define storage tiers (hot/warm/cold) ... set per-store per-tier retention durations" + (V9) "Object Lock / WORM / air-gap enforced" | retention-tier leg (cand D4) + isolation leg (cand V9/V3); both legs present |
| D4 | D | — | COVERED | "Per failure scenario ... document step-by-step restore or failover procedure; specify recovery priority sequence" | ordered restore/failover runbook |
| D5 | D | — | COVERED | "After every backup job: verify completion ... compute and store checksum ... monitor backup age per store (alert threshold = RPO − response_buffer)" | integrity + freshness + monitoring detect pass; cand D7/V4/V11/V12/V13/Dep5 collapse here = ballast |
| D6 | D | — | COVERED | "Calendar-enforced mandatory drill frequency per criticality tier ... restore ≤ RTO, data within RPO, smoke tests pass" | periodic actual restore-drill measuring achieved RPO/RTO |
| Dep1 | Dep | FM-1, FM-6 | COVERED | "For every store: cadence + p99_backup_duration ≤ RPO_stated" | cadence derived from RPO (breach = data older than target) |
| Dep2 | Dep | FM-1, FM-6 | COVERED | "Sum of per-step restore/failover timings for each defined failure scenario ≤ RTO_stated. Measured in every drill." | restore+failover time bounded by RTO |
| Dep3 | Dep | FM-1 | COVERED | "sample-restore a random set of records from backup and compare against known state (catches correct-checksum but corrupt content)" + (D8) drill log shows successful restore | restorability established by an actual restore, not job-success |
| Dep4 | Dep | FM-1 | COVERED | "verify checksum before marking backup usable" + (cand Dep4) "corrupt a backup byte after integrity check passes ... verify the mismatch is detected before restore completes" | integrity verdict gates restore; corrupt backup not used |
| Dep5 | Dep | FM-1, FM-2 | COVERED | "specify recovery priority sequence (secrets/KMS → config stores → primary DB → application tier → secondary stores)" | restore follows dependency order |
| Dep6 | Dep | FM-2 | COVERED | "post-restore referential integrity check between all DB foreign keys referencing object store keys and the T1 object store key listing; zero dangling references" + (cand Dep7) "smoke test reads a record known to differ between T1 and T2 — cache returns the T1 value" | cross-store mutual consistency at a coherent recovery point; cand Dep7/Dep9 collapse here = ballast |
| Dep7 | Dep | FM-1, FM-5, FM-7 | COVERED | "finding registry requires a runbook version bump before the finding can be closed; the subsequent drill log cites the updated runbook version" + (cand Dep11) provisioning gate enrolls new store | drill findings + estate drift re-arm the regime; cand Dep11/V15 = ballast |
| Dep8 | Dep | FM-2 | COVERED | "drill environment spec is compared against current production spec before every drill; any discrepancy is a drill finding" + (D8) "version-locked to current production spec (same OS/DB version, hardware tier)" | restore target must be version/spec-compatible to run; cand Dep8 (DNS/LB) = ballast |
| Dep9 | Dep | FM-1 | NOT-COVERED | | failback / return-leg re-sync of DR-side writes to primary absent; cand Dep15 is failover-loss-at-promotion, not the return leg |
| Dep10 | Dep | FM-1, FM-6 | COVERED | "derived stores still require a documented rebuild path with timed estimate" + "if derived — a timed rebuild procedure ≤ its RTO" | derived-store rebuild-from-source bound to RTO |
| V-I1 | V | FM-1 | COVERED | "At all times, every data store in production is covered by the backup regime. Weekly diff of live infrastructure inventory against backup inventory returns zero gap." | catalog completeness over all required artifacts |
| V-I2 | V | FM-6 | COVERED | "Drills have objective pass/fail criteria: restore ≤ RTO, data within RPO ... Per-step timing is logged; total is compared to RTO" | RPO/RTO measured-and-met on drills, not assumed |
| V-I3 | V | FM-2 | COVERED | "After simulated primary-region loss, backups are fully accessible from the secondary region using only secondary-region credentials; no primary-region credential ... required" | backups isolated in independent failure domain |
| V-I4 | V | FM-3 | COVERED | "post-restore validation checklist (row counts, last-write timestamps, cross-store consistency, application smoke test)" + (D8) "smoke tests pass" | recovery success = application-level working service, not bytes |
| V-E1 | V | FM-3 | COVERED | "sample-restore a random set of records from backup and compare against known state (catches correct-checksum but corrupt content)" + "produce a zero-byte artifact → rejected with alert" | partial/corrupt backup detected, not trusted on job-success |
| V-E2 | V | FM-6 | COVERED | "Per failure scenario (single-store, multi-store, region-wide, total-loss / no-replica-available ...)" + (V3) restore from secondary region | whole-site/region loss recovered from off-region isolated copy |
| V-E3 | V | FM-3 | COVERED | "Drills run in an isolated environment version-locked to current production spec" + (D5) "redirect writes, update DNS/LB" | restore into a clean/different environment, reconstruct endpoint couplings |
| V-E4 | V | FM-3 | NOT-COVERED | | no app-consistent/quiesce/crash-consistency stance for backing up a single store under active/in-flight writes |
| V-E5 | V | FM-3, FM-5 | COVERED | "if key rotation since T1 has not updated the escrow, the backup is unreadable" + (V18) "rotation procedure mandates an escrow update ... restore using only the escrowed key" | on-restore decryptability + rotation retains/escrows old key versions for in-retention backups |
| V-E6 | V | FM-3 | NOT-COVERED | | schema/data-version skew (old backup into newer app → forward-migrate / version-pin) not addressed; "migration-backup coordination" is capture-time, not restore-time skew |
| V-F1 | V | FM-3 | COVERED | "Silent corruption of the base makes every dependent unrestorable — the chain appears valid in the catalog but cannot be assembled" + (D8) restore-drills prove restorability | false-green capture (reports success / passes checksum yet won't restore), guarded by drills |
| V-F2 | V | FM-7, FM-6 | COVERED | "Drill procedure uses the identical document and version as the real recovery runbook" + "Findings are tracked to closure — runbook version is bumped before a finding is closed" | un-drilled runbook rots; guard = drill the actual runbook, keep current |
| V-F3 | V | FM-1, FM-6 | COVERED | "Drills have objective pass/fail criteria: restore ≤ RTO, data within RPO ... Per-step timing is logged; total is compared to RTO" | RPO/RTO measured on every drill, not left paper |
| V-F4 | V | FM-1 | COVERED | "Backups cannot be modified or deleted by any actor whose credentials could be compromised along with the production environment. Object Lock / WORM / air-gap enforced" | co-located/mutable-backup defect guarded by isolation/immutability |
| V-F5 | V | FM-1, FM-2 | NOT-COVERED | | backup-region/provider correlated co-failure (control-plane / correlated domain despite separation) not named (per Appendix V-F5 rule) |
| V-F6 | V | FM-2, FM-4 | NOT-COVERED | | runtime partial restore (some stores up, others down) presented as recovered + all-or-nothing/consistency-group guard not named (distinct from Dep6) |
| V-F7 | V | FM-2, FM-4 | NOT-COVERED | | split-brain dual-writable-primary divergence + fencing/quorum/single-writer guard absent |
| V-F8 | V | FM-4, FM-6 | NOT-COVERED | | interrupted-and-rerun restore idempotence/resumability/transactional-rollback not addressed (D1 idempotency is app-layer transient state, not restore re-run) |
| N1 | N | FM-1 | COVERED | "specify recovery priority sequence (secrets/KMS → config stores → primary DB ...)" + (D1) "secrets managers" enrolled | secret/KMS recoverability named — enrolled in-scope (truth-maker: "either enrolled or declared") |
| N2 | N | FM-1 | NOT-COVERED | | DNS/external-SaaS/third-party state not declared as out-of-backup-but-required/re-creatable |
| N3 | N | FM-1 | COVERED | "document ephemeral/transient state disposition (acceptable loss or idempotency design — no silent assumption of zero loss)" | in-flight/transient state declared excluded to last consistent point |
| N4 | N | FM-1 | COVERED | (cand N6) "Restoring the infrastructure layer (VMs, Kubernetes, networking) is an infrastructure DR concern. This regime assumes infrastructure is available or is being restored by a separate, cross-referenced runbook." | explicit app-recovery-vs-infra-recovery boundary |
| N5 | N | FM-1 | NOT-COVERED | | cert/clock/token freshness post-restore not declared (cand V16 is NTP-for-backup-hosts/PITR, a different angle — flagged unmatched) |
| N6 | N | FM-1 | NOT-COVERED | | "the backup/DR site itself survives the disaster" meta-assumption not declared/bounded |
| N7 | N | FM-1 | COVERED | "Per failure scenario (single-store, multi-store, region-wide, total-loss / no-replica-available, table-/collection-level surgical recovery)" | declared disaster-class set the regime is designed against |
| N8 | N | FM-1 | NOT-COVERED | | compliance content (D4 GDPR/HIPAA/SOX retention floors) is the D3 retention-duration side per Appendix N8 rule; data-residency-vs-isolation / compliance-ownership assumption not declared |
| N9 | N | FM-1 | NOT-COVERED | | cost/storage-budget ceiling as a declared fixed input bounding RPO/RTO not stated |
| N10 | N | FM-1 | NOT-COVERED | | platform-managed-vs-self-managed (shared-responsibility; managed backups region-local/account-deletable) not declared |
| N11 | N | FM-1 | NOT-COVERED | | deadline-bound regulatory/breach-notification obligation not declared (D5 "stakeholder notification" is RACI/authority = plane, no credit) |

## 6.2 Ballast list

| ref-id | # candidate points mapped | ballast (count − 1) | duplicate candidate phrases |
|---|---|---|---|
| D1 | 2 | 1 | D2 "RPO/RTO target assignment" |
| D5 | 7 | 6 | D7 (monitoring/alerting); V4 (no silent pipeline failure); V11 (freshness alert threshold); V12 (WAL lag alert threshold); V13 (schedule adherence); Dep5 (alert threshold + on-call response ≤ RPO budget) |
| D6 | 2 | 1 | V14 (drill schedule enforcement / missed drill = incident) |
| Dep1 | 3 | 2 | V17 (PITR restorability for low-RPO stores); Dep14 (replica-lag → effective RPO) |
| Dep2 | 2 | 1 | V7 (catalog queryability within RTO lookup budget) |
| Dep4 | 3 | 2 | Dep1 (WAL→catalog→PITR sequencing gap); Dep2 (base integrity → incremental chain) |
| Dep6 | 3 | 2 | Dep7 (cache cross-store consistency); Dep9 (queue consumer offsets → replay) |
| Dep7 | 3 | 2 | Dep11 (provisioning → backup inventory gate); V15 (RPO/RTO revision triggers review) |
| Dep8 | 2 | 1 | Dep8 (replica promotion → DNS/LB → write connectivity) |
| V-I1 | 3 | 2 | V8 (retention floor: restore chain within RPO exists); Dep3 (retention engine → chain dependency check) |
| V-I2 | 3 | 2 | V10 (regime self-consistency of parameters); Dep15 (replica lag at promotion → transaction-loss acknowledgment) |
| V-E5 | 2 | 1 | V18 (encryption key escrow currency) |
| | | **total = 23** | |

## 6.3 Unmatched candidate points

| candidate phrase (verbatim) | flag |
|---|---|
| N1 "Logical / application-level data corruption — A bug that writes semantically wrong values for weeks; backup faithfully preserves the corrupted data. Out of scope (backup fidelity ≠ data quality)." | UNMATCHED — human review |
| N2 "Active-active replication infrastructure design — Active-active is an architectural choice, not a backup. The replication infrastructure design is out of scope." | UNMATCHED — human review |
| N3 "Full security / ransomware incident response playbook — The complete incident response is a security concern." | UNMATCHED — human review |
| N4 "Application binary / deployment rollback — Rollback of deployment artifacts is a CI/CD concern. This regime covers data state rollback only." | UNMATCHED — human review |
| N5 "Development and staging environments (without prod data) — Out of scope unless an environment holds a copy of production data." | UNMATCHED — human review |
| V16 "Clock synchronization — NTP synchronization is a monitored prerequisite on all backup hosts; clock skew beyond threshold fires an alert. Catalog timestamps used for PITR are trusted only when sync is current." | UNMATCHED — human review |
| | total = 6 |

## 6.4 Score block
```
COVERAGE (fully-COVERED / total):
  by category:   D = 6/6   Dep = 9/10   V = 12/18   N = 4/11
  by FM tag:     FM-1 = 14/23   FM-2 = 4/7   FM-3 = 5/7   FM-4 = 0/3   FM-5 = 2/2   FM-6 = 7/8   FM-7 = 2/2
  PARTIAL counts: D = 0   Dep = 0   V = 0   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 23
  unmatched candidate points (human-review flag):    total = 6
```
