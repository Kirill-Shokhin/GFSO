# BLIND JUDGE VERDICT — T06 / candidate D3

Reference: `complex/references/T06.md` (frozen gold). Candidate: one decomposition, origin stripped.
Scored categories: D (6), Dep (10), V (18), N (11) = 45 reference items. `Del`/authority not scored.

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "Classify each store as authoritative state or derived/reconstructable" (cand D1) + "specify: maximum tolerable data age (RPO) in time units; maximum tolerable restore/failover duration (RTO)" (cand D2) | objectives+inventory+derived-class split across cand D1/D2 |
| D2 | D | — | COVERED | "Per store: select backup type (full/incremental/differential/WAL-log-based) and cadence such that cadence + p99_backup_duration ≤ RPO_stated" (cand D3) | capture pass |
| D3 | D | — | COVERED | "Define storage tiers (hot/warm/cold) with storage classes and benchmarked restore times per tier" (cand D4); isolation leg in cand V9 | both legs (tiers + isolation) present |
| D4 | D | — | COVERED | "Per failure scenario ... document step-by-step restore or failover procedure" (cand D5) | runbook |
| D5 | D | — | COVERED | "After every backup job: verify completion ... compute and store checksum ... monitor backup age per store" (cand D6) | integrity/freshness; monitoring in cand D7 |
| D6 | D | — | COVERED | "Calendar-enforced mandatory drill frequency per criticality tier" / "Drills have objective pass/fail criteria: restore ≤ RTO, data within RPO, smoke tests pass" (cand D8) | actual measured restore-drill |
| Dep1 | Dep | FM-1,FM-6 | COVERED | "cadence such that cadence + p99_backup_duration ≤ RPO_stated" (cand D3) | cadence derived from RPO |
| Dep2 | Dep | FM-1,FM-6 | COVERED | "Sum of per-step restore/failover timings for each defined failure scenario ≤ RTO_stated. Measured in every drill" (cand V2) | restore/failover time bounded by RTO |
| Dep3 | Dep | FM-1 | COVERED | "Drills have objective pass/fail criteria: restore ≤ RTO, data within RPO, smoke tests pass" (cand D8) | restorability established by actual restore |
| Dep4 | Dep | FM-1 | COVERED | "corrupt a backup byte after integrity check passes; trigger restore from the same declared path; verify the mismatch is detected before restore completes" (cand Dep4) | integrity gates restore |
| Dep5 | Dep | FM-1,FM-2 | COVERED | "specify recovery priority sequence (KMS/secrets → config stores → primary DB → application tier → secondary stores)" (cand D5) | dependency-ordered restore |
| Dep6 | Dep | FM-2 | COVERED | "post-restore referential integrity check between all DB foreign keys referencing object store keys and the T1 object store key listing; zero dangling references" (cand Dep10) | consistent recovery point across stores (also cand Dep7/Dep9/Dep18) |
| Dep7 | Dep | FM-7,FM-5 | COVERED | "finding registry requires a runbook version bump before the finding can be closed; the subsequent drill log cites the updated runbook version" (cand Dep13) | drill→regime update; estate drift via cand Dep11/V28 |
| Dep8 | Dep | FM-2 | COVERED | "Drills run in an isolated environment version-locked to current production spec (same OS/DB version, hardware tier)" (cand D8); "drill environment spec is compared against current production spec before every drill" (cand Dep12) | restore-target parity |
| Dep9 | Dep | FM-1 | NOT-COVERED | | failback / re-sync of DR-side writes back to primary absent; cand D5 partial-failover catches the restored side UP to live (forward), not the return leg |
| Dep10 | Dep | FM-1,FM-6 | COVERED | "derived stores still require a documented rebuild path with timed estimate" + "if derived — a timed rebuild procedure ≤ its RTO" (cand D1) | derived rebuild bound to RTO |
| V-I1 | V | FM-1 | COVERED | "every data store in production is covered by the backup regime. Weekly diff of live infrastructure inventory against backup inventory returns zero gap" (cand V5) | catalog completeness |
| V-I2 | V | FM-6 | COVERED | "Per-step timing is logged; total is compared to RTO" / "objective pass/fail criteria: restore ≤ RTO, data within RPO" (cand D8) | RPO/RTO measured-met |
| V-I3 | V | FM-2 | COVERED | "After simulated primary-region loss, backups are fully accessible from the secondary region using only secondary-region credentials; no primary-region credential, network, or service is required" (cand V3) | isolation invariant |
| V-I4 | V | FM-3 | COVERED | "include post-restore validation checklist (row counts, last-write timestamps, cross-store consistency, application smoke test)" (cand D5) | service-works not bytes-back |
| V-E1 | V | FM-3 | COVERED | "compute and store checksum (SHA-256 or equivalent); verify checksum before marking backup usable" (cand D6); earlier-good-copy via cand V8 retention floor | partial/corrupt backup detected, not used |
| V-E2 | V | FM-6 | COVERED | "Per failure scenario (single-store, multi-store, region-wide, total-loss / no-replica-available ...)" (cand D5) | whole-site / region loss + cross-region (cand V3) |
| V-E3 | V | FM-3 | COVERED | "reroute all read endpoints (read replicas, read-only DNS records, CDN-cached query layers) to the new topology, not only the write endpoint" (cand D5) | restore into new topology; hidden DNS/endpoint couplings reconstructed |
| V-E4 | V | FM-3 | COVERED | "for application-consistent snapshots, document the quiesce mechanism (freeze/thaw, VSS writer, DB flush hook)" (cand D3) | in-flight/live-state consistency (also cand V26) |
| V-E5 | V | FM-3,FM-5 | COVERED | "If key rotation since T1 has not updated the escrow, the backup is unreadable. Applies across all rotation events since backup creation" (cand Dep6) + "key rotation procedure mandates an escrow update" (cand V18) | both legs: key recoverable + rotation does not orphan |
| V-E6 | V | FM-3 | NOT-COVERED | | old-backup-into-newer-app schema skew + forward-migration/backward-compat/version-pin response absent; cand V22 is PITR-boundary schema targeting, cand V19 is engine-version — neither is data-shape-vs-current-app-code |
| V-F1 | V | FM-3 | COVERED | "sample-restore a random set of records from backup and compare against known state (catches correct-checksum but corrupt content)" (cand D6) | false-green capture caught by actual restore |
| V-F2 | V | FM-7,FM-6 | COVERED | "Drill procedure uses the identical document and version as the real recovery runbook" (cand D8) | un-drilled runbook rot guarded |
| V-F3 | V | FM-1,FM-6 | COVERED | "RPO formula compliance ... Automated weekly audit; any violation is an incident" (cand V1) | objectives measured not paper |
| V-F4 | V | FM-1 | COVERED | "Backups cannot be modified or deleted by any actor whose credentials could be compromised along with the production environment. Object Lock / WORM / air-gap enforced" (cand V9) | co-location/mutable-with-primary guard |
| V-F5 | V | FM-1,FM-2 | NOT-COVERED | | backup region itself co-fails (correlated failure domain despite separation) + independent-domain/multi-provider/offline guard absent; cand V3 asserts dependency-independence but presumes the secondary region survives |
| V-F6 | V | FM-2,FM-4 | NOT-COVERED | | runtime partial restore (some stores up, some failed) → all-or-nothing / consistency-group / partial=not-recovered guard absent; cand covers consistent recovery POINT (Dep-cluster) but not partial-failure rollback semantics |
| V-F7 | V | FM-2,FM-4 | NOT-COVERED | | split-brain dual-writable-primaries divergence + fencing/quorum/witness/single-writer guard absent; cand Dep20 drains old-primary connections (write-loss framing), not fencing-against-divergence |
| V-F8 | V | FM-4,FM-6 | COVERED | "if a restore is interrupted midway ... the procedure must return the DB to a known recoverable state ... restart must be idempotent" (cand D5) | re-run/resume safety of a single restore |
| N1 | N | FM-1 | COVERED | "KMS-unavailable: explicit bootstrap procedure — restore KMS infrastructure from its own backup → verify key retrieval → decrypt data backups" (cand D5) | KMS/secret recoverability named (enrolled) |
| N2 | N | FM-1 | COVERED | "every SaaS system ... is either (a) declared in scope with a documented export/backup mechanism ... or (b) declared out of scope with a signed business-acceptance rationale" (cand D1) | external SaaS state declared |
| N3 | N | FM-1 | COVERED | "document ephemeral/transient state disposition (acceptable loss or idempotency design — no silent assumption of zero loss)" (cand D1) | in-flight/transient messages declared excluded |
| N4 | N | FM-1 | COVERED | "Restoring the infrastructure layer (VMs, Kubernetes, networking) is an infrastructure DR concern. This regime assumes infrastructure is available or is being restored by a separate, cross-referenced runbook" (cand N6) | app-vs-infra recovery boundary declared |
| N5 | N | FM-1 | NOT-COVERED | | certificate/clock/token freshness post-restore (re-issued not restored-stale) not declared; cand V16 is NTP on backup hosts for catalog-timestamp trust, a different concern |
| N6 | N | FM-1 | NOT-COVERED | | the meta-assumption "the backup/DR site itself survives this disaster class" not declared as an explicit bounded assumption |
| N7 | N | FM-1 | COVERED | "Per failure scenario (single-store, multi-store, region-wide, total-loss ...)" (cand D5) + "Logical / application-level data corruption ... Out of scope (backup fidelity ≠ data quality)" (cand N1) | in/out disaster-class threat model declared |
| N8 | N | FM-1 | COVERED | "for each data class with a data-residency jurisdiction constraint, document the permitted backup storage regions ... track compliance/legal retention floors separately (GDPR, HIPAA, SOX, etc.)" (cand D4) | compliance/residency declared (also cand V27) |
| N9 | N | FM-1 | NOT-COVERED | | cost/storage-budget ceiling as a declared fixed input bounding achievable RPO/RTO not present (cand V23 is storage-capacity utilization, not a budget ceiling) |
| N10 | N | FM-1 | NOT-COVERED | | platform-managed-vs-self-managed shared-responsibility split (managed backups region-local/account-deletable) not declared; cand SaaS handling (D1)→N2, but managed-DB/infra shared-responsibility absent |
| N11 | N | FM-1 | NOT-COVERED | | deadline-bound regulatory/customer breach-notification obligation not declared; cand D5 "stakeholder notification" RACI is generic, no statutory-deadline obligation |

PARTIAL: none. Multi-leg ref items present in T06 (D3 retention+isolation; V-E5 key-loss+rotation) are fully COVERED on both legs.

## 6.2 Ballast list (candidate richness collapsing onto one ref item; counts are the principal duplicates)

| ref-id | # candidate points mapped | ballast (count − 1) | duplicate candidate phrases |
|---|---|---|---|
| D1 | 2 | 1 | cand D1 (scope+class) + cand D2 (RPO/RTO assignment) |
| D2 | 2 | 1 | cand D3 (capture) + cand V17 (PITR restorability low-RPO) |
| D3 | 4 | 3 | cand D4 + cand Dep3 (retention-chain dependency) + cand V8 (retention floor) + cand V23 (expiry-vs-accumulation bound) |
| D5 | 7 | 6 | cand D6 + cand D7 (alerting) + cand V4 (no silent pipeline failure) + cand V11 (freshness threshold) + cand V12 (WAL-lag threshold) + cand V13 (schedule adherence) + cand Dep5 (alert-threshold→RPO budget) |
| D6 | 2 | 1 | cand D8 + cand V14 (drill schedule enforcement) |
| Dep1 | 2 | 1 | cand D3 (cadence formula) + cand Dep14 (replica-lag effective RPO) |
| Dep2 | 6 | 5 | cand V2 + cand Dep8 (DNS/LB→write) + cand Dep16 (read-endpoint reroute) + cand Dep20 (pool drain) + cand V20 (bandwidth RTO floor) + cand V25 (infra DR composite RTO) |
| Dep6 | 4 | 3 | cand Dep10 + cand Dep7 (cache) + cand Dep9 (queue offsets) + cand Dep18 (CDC cursor) |
| Dep7 | 3 | 2 | cand Dep13 + cand V15 (SLA-change review) + cand V28 (dependency-graph currency) |
| Dep8 | 2 | 1 | cand Dep12 + cand V19 (engine-upgrade restore gate) |
| V-I1 | 2 | 1 | cand V5 + cand Dep11 (provisioning inventory gate) |
| V-I2 | 2 | 1 | cand D8 + cand V10 (regime self-consistency) |
| V-I4 | 2 | 1 | cand D5 smoke test + cand V6 (restore correctness) |
| V-E1 | 2 | 1 | cand D6 checksum + cand V24 (size-anomaly detection) |
| V-E4 | 2 | 1 | cand D3 quiesce + cand V26 (snapshot-consistency classification) |
| V-E5 | 3 | 2 | cand Dep6 + cand V18 (escrow currency) + cand D6 (escrowed-key pre-rotation decrypt) |
| N7 | 3 | 2 | cand D5 scenarios + cand N1 (logical-corruption out) + cand N3 (security-IR out) |
| N8 | 2 | 1 | cand D4 residency + cand V27 (residency compliance) |

Total ballast (principal) ≈ **34**. (Reporting collapse of distinct candidate claims onto single ref items; not folded into coverage.)

## 6.3 Unmatched candidate points (no reference item — flagged, not scored)

| candidate phrase (verbatim) | flag |
|---|---|
| "D9 · Backup catalog backup and recovery ... The backup catalog is itself a critical data store; its loss or corruption coincident with a primary failure blocks all recovery" | UNMATCHED — human review |
| "Dep1 · WAL/log shipping → backup catalog → PITR restore path ... If the catalog lags, missequences, or drops a segment, PITR silently produces a gap without erroring" | UNMATCHED — human review |
| "V7 · Catalog queryability — Given any target recovery time T, the backup catalog identifies the correct backup set ... within the time budget allocated for catalog lookup in the RTO" | UNMATCHED — human review |
| "Dep19 · Backup job partial failure → catalog partial registration → PITR assembly ambiguity" | UNMATCHED — human review |
| "Dep17 · Backup agent credential rotation → job continuity ... backup agents may silently fail if their credential cache is not updated in lockstep" | UNMATCHED — human review |
| "Dep15 · Replica lag at promotion → unacknowledged transaction loss ... the last N seconds of committed primary transactions are permanently lost" | UNMATCHED — human review |
| "V16 · Clock synchronization — NTP synchronization is a monitored prerequisite on all backup hosts; clock skew beyond threshold fires an alert" | UNMATCHED — human review |
| "V21 · In-transit encryption of backup streams ... TLS version ≥ 1.2 enforced and audited on each channel" | UNMATCHED — human review |
| "V22 · Schema migration PITR boundary integrity ... a PITR restore targeting LSN L−1 produces the pre-migration schema and targeting L+1 produces the post-migration schema" | UNMATCHED — human review |
| "N2 · Active-active replication infrastructure design ... The replication infrastructure design is out of scope" | UNMATCHED — human review |
| "N4 · Application binary / deployment rollback ... This regime covers data state rollback only" | UNMATCHED — human review |
| "N5 · Development and staging environments (without prod data) — Out of scope unless an environment holds a copy of production data" | UNMATCHED — human review |
| "V29 · Multi-person authorization for immutability policy modification ... any modification to immutability configuration requires at minimum two-person authorization" | AUTHORITY PLANE (Del) — ignored per §1/§3 (neither credited nor penalized) |

## 6.4 Score block
```
COVERAGE (fully-COVERED / total):
  by category:   D = 6/6   Dep = 9/10   V = 14/18   N = 6/11
  by FM tag:     FM-1 = 9/11   FM-2 = 4/7   FM-3 = 6/7   FM-4 = 1/3   FM-5 = 2/2   FM-6 = 8/8   FM-7 = 2/2
                 (FM tags computed over the explicitly-tagged V + Dep items; N is the FM-1.b register, scored as the N category)
  PARTIAL counts: D = 0   Dep = 0   V = 0   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 34
  unmatched candidate points (human-review flag):    total = 12   (+1 authority-plane item ignored)
```
