# BLIND JUDGE VERDICT — T07 / candidate D1

## 6.1 Mapping table

### D — subtasks (8 items)

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "Each entry carries: key, value, creation timestamp, TTL, ... dirty flag, version counter" (D.1) + "Lookup key → check existence ... → return value" (D.3) + "insert/update entry" (D.4) | map + get/put/delete present |
| D1a | D | — | NOT-COVERED |  | no compound atomic-op API (computeIfAbsent/putIfAbsent/replace-CAS/getAndSet) stated; D.2 is single-flight (→V-F1), V.6 is flush-CAS, not an RMW-op API contract |
| D2 | D | — | COVERED | "the per-shard lock" (D.10) + "Acquire write lock" (D.4) | concurrency-control mechanism |
| D3 | D | — | COVERED | "Selects and removes the victim entry per the chosen policy" (D.5) | eviction policy + bookkeeping |
| D4 | D | — | COVERED | "Each entry carries: ... TTL" (D.1) + "check expiry" (D.3) | per-entry TTL + serve-path; reclamation half at V-I6 |
| D5 | D | — | COVERED | "Write-through: synchronous put before ack. Write-back: enqueues to flush queue" (D.7) | backing + write policy + dirty |
| D6 | D | — | COVERED | "Receives invalidation signals (local or remote) and removes or marks stale" (D.9) | invalidation-on-update, local+remote |
| D7 | D | — | COVERED | "the deterministic key → shard hash function ... Routes every key operation to exactly one shard" (D.10) | sharding + shard-map fn |

### Dep — seams (14 items)

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note |
|---|---|---|---|---|---|
| Dep1 | Dep | FM-1 | COVERED | "If an entry is evicted while a reader holds a reference to its value, the value buffer must remain valid for the reader's lifetime (copy semantics or reference counting)" (Dep.15) | evict-vs-access; Appendix Dep1/Dep10 merge applied (one point credits both) |
| Dep2 | Dep | FM-2 | COVERED | "only one must succeed in removing it; double-removal must not corrupt the capacity counter" (Dep.6) | reclaim-exactly-once (eviction↔sweeper) |
| Dep3 | Dep | FM-1 | COVERED | "Evicting a dirty entry requires a synchronous flush before removal from the index; if flush fails the entry must not be removed" (Dep.3) | flush-on-evict |
| Dep4 | Dep | FM-1 | NOT-COVERED |  | TTL-expiry-of-a-dirty-entry-must-flush seam absent (expiry↔flush) |
| Dep5 | Dep | FM-1 | COVERED | "An invalidation racing an in-flight read must not allow the read to return a value that was invalidated before the read's lock was acquired" (Dep.4) | local invalidation-vs-read |
| Dep6 | Dep | FM-1 | NOT-COVERED |  | concurrent update of recency/frequency eviction metadata under concurrency not named (counter-corruption appears only at Dep.6=Dep2) |
| Dep7 | Dep | FM-1 | COVERED | "check capacity → evict if needed → insert/update entry" (D.4) | accounting-triggers-eviction; byte-cost via V.18/V.1 |
| Dep8 | Dep | FM-2 | NOT-COVERED |  | per-shard-vs-global bound / hot-shard skew reconciliation absent |
| Dep9 | Dep | FM-2 | COVERED | "all peer cache nodes must receive an invalidation before they serve reads for the updated key" (Dep.7) | cross-node invalidation ordering |
| Dep10 | Dep | FM-1 | COVERED | "the value buffer must remain valid for the reader's lifetime (copy semantics or reference counting)" (Dep.15) | get-vs-reclaim pin; Appendix-sanctioned merge with Dep1 |
| Dep11 | Dep | FM-1 | COVERED | "Eviction must complete and the victim must be fully removed ... before the new entry is inserted; the sequence must be atomic at the shard level" (Dep.1) | insert↔evict ordering on full store |
| Dep12 | Dep | FM-2 | COVERED | "Atomic with respect to readers" + falsifier "reader sees the new key but not the new value (partial write visible)" (D.4) | atomic publication / no torn publish |
| Dep13 | Dep | FM-1 | COVERED | "shard-count changes require a coordinated transition; no thread uses a cached shard-map from before the transition" + "one thread rehashes while another is mid-operation → key routed to wrong shard" (V.15) | rehash/resize migration race |
| Dep14 | Dep | FM-1 | COVERED | "An invalidation arriving while an entry is in the 'loading' state must cause the completed load to be discarded rather than inserted" (Dep.9) | delete/invalidation vs in-flight load → resurrection |

### V — criteria (26 items)

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note |
|---|---|---|---|---|---|
| V-I1 | V | FM-1 | COVERED | "concurrent writes to the same key resolve to exactly one winner; the losing write is either rejected or explicitly superseded" (V.8) | no lost update |
| V-I2 | V | FM-1 | COVERED | "no thread observes an entry in a partial-transition state" (V.5) | no torn read |
| V-I3 | V | FM-1 | COVERED | "A thread that writes a key and then reads it sees its own write, not a prior value or a stale cache entry" (V.9) | no stale read after commit |
| V-I4 | V | FM-1 | COVERED | "At no point does the number (or total byte size) of entries exceed the declared limit, even transiently" (V.7) | bounded |
| V-I5 | V | FM-1 | PARTIAL | "flush must be triggered before that bound is reached" (V.13) | covers flush-before-mem-exhaustion leg; MISSING leg: guaranteed durable flush of a dirty entry on TTL-expiry reclaim (and a unified across-all-reclaim-paths assertion) |
| V-I6 | V | FM-1 | COVERED | "Background worker that periodically scans and removes expired entries without waiting for a read or write to trigger lazy expiry" (D.6) | active sweep, no cold-expired leak |
| V-I7 | V | FM-1 | COVERED | "The capacity counter accounts for all live data including metadata overhead ... not just payload bytes" (V.18) | size-accounting accuracy (the bound-bearing leg) |
| V-I8 | V | FM-4 | COVERED | "Any operation acquiring multiple locks ... acquires them in a globally consistent total order" (V.11) | deadlock-freedom; progress leg also at V.14 |
| V-I9 | V | FM-2 | NOT-COVERED |  | per-key coherence / single-key linearizability (readers/shards agree on one value) not asserted; D.10 "two authoritative copies" credited at V-I10 (routing) |
| V-I10 | V | FM-2 | COVERED | "Routes every key operation to exactly one shard" + falsifier "two authoritative copies with no reconciliation" (D.10) | one route/home per key |
| V-I11 | V | FM-1 | COVERED | "No entry is returned to a caller after its TTL has elapsed" (V.10) | never-serve-expired |
| V-E1 | V | FM-3 | NOT-COVERED |  | concurrent-get+evict boundary not framed as a distinct case beyond the Dep1/Dep10 seams (both consumed) |
| V-E2 | V | FM-3 | COVERED | "The expiry check and the value return must occur within the same lock window; the lock must not be dropped between the check and the return" (Dep.2) | atomic check-and-serve at expiry crossing |
| V-E3 | V | FM-3 | NOT-COVERED |  | full-insert with no eligible victim (all pinned/equally hot) fallback absent |
| V-E4 | V | FM-3 | COVERED | "throughput must not degrade to single-shard serialization ... the design must account for hot-key scenarios" (V.26) | hot-key contention |
| V-E5 | V | FM-3 | COVERED | "Mass cache invalidation must not produce O(N) simultaneous backing-store reads; the fill path must include rate-limiting, jitter, or coalescing" (V.29) | mass-reclaim reload-stampede leg of expiry-storm |
| V-E6 | V | FM-3 | COVERED | "TTL expiry across nodes must not rely on synchronized wall clocks without declaring a divergence tolerance" (V.27) | clock skew / time source |
| V-E7 | V | FM-3 | COVERED | "A single entry whose byte size exceeds one shard's byte limit must be rejected cleanly at insert time, not admitted and then immediately evicted in a loop" (V.30) | oversized value, no evict-everything loop |
| V-E8 | V | FM-3 | COVERED | "hash equality must not be treated as key equality" (V.28) | collision identity by equality |
| V-E9 | V | FM-3 | PARTIAL | "A TTL of zero or negative must be rejected at insert time or treated as immediate expiry" (V.23) | covers zero/negative leg; MISSING legs: absent/eternal, TTL==now, far-future conventions |
| V-E10 | V | FM-3 | NOT-COVERED |  | idempotent delete of absent/already-evicted key (no negative size, no spurious flush/invalidate) absent |
| V-E11 | V | FM-3 | NOT-COVERED |  | update-in-place size-delta accounting (−old+new) absent; Dep.10 covers only TTL-reset-on-write, not the cost delta |
| V-F1 | V | FM-4 | COVERED | "other threads block on the same placeholder rather than each issuing their own backing read" (D.2) | single-flight / stampede guard |
| V-F2 | V | FM-3 | COVERED | "must either guarantee delivery or provide a re-sync / TTL-bounded fallback so that stale values do not persist indefinitely after a dropped message" (V.17) | silent-invalidation backstop |
| V-F3 | V | FM-7 | COVERED | "The write-back cache must flush all dirty entries before process exit" (V.25) | shutdown drain |
| V-F4 | V | FM-3 | COVERED | "Any operation acquiring multiple locks" (V.11) + "the per-shard lock" (D.10) | N/A — D2 is lock-based; auto-covered per Appendix (ABA bites only on a lock-free design) |

### N — scope-exclusions (5 items)

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note |
|---|---|---|---|---|---|
| N1 | N | FM-1 | COVERED | "an in-memory cache is understood to be volatile; durability is delegated to the backing store" (N.2) | backing durability assumed |
| N2 | N | FM-1 | COVERED | "strong consistency across nodes requires a consensus protocol, a full subsystem" / "Out of scope" (N.1) | partition/consensus out of scope |
| N3 | N | FM-1 | NOT-COVERED |  | allocator/GC assumed-sound exclusion absent |
| N4 | N | FM-1 | NOT-COVERED |  | value-immutability-vs-defensive-copy stated-choice exclusion absent (copy/refcount appears only as a Dep.15 mechanism) |
| N5 | N | FM-1 | NOT-COVERED |  | serialization-out-of-scope + cost=named-size-function exclusion absent |

## 6.2 Ballast list

| ref-id | # candidate points mapped | ballast (count − 1) | the duplicate candidate phrases |
|---|---|---|---|
| D3 | 2 | 1 | V.2 "Exactly one eviction policy ... is chosen and consistently applied" |
| D5 | 5 | 4 | D.8 (write-back flush queue); D.11 (background flush worker); V.4 "persistence mode ... single global policy"; V.12 "successful write-through ack implies the value is in the backing store" |
| Dep2 | 2 | 1 | Dep.13 "Concurrent eviction and invalidation ... must be idempotent; double-removal must not corrupt the capacity counter" |
| Dep14 | 4 | 3 | Dep.11 "dirty entry that receives an invalidation while queued for flush must not be flushed ... version check"; Dep.12 "load completes and inserts old value, overwriting the newer write"; V.6 "flushes must compare versions ... older flush cannot revert a newer one" |
| V-I4 | 2 | 1 | Dep.8 "Dirty entries in the flush queue count toward the capacity limit" |
| V-I8 | 5 | 4 | V.14 (liveness of background workers); V.19 (lock re-entrancy safety); Dep.5 "must acquire both shard locks before mutating"; Dep.14 "must not hold the lock for the entire scan of a shard" |
| V-F1 | 2 | 1 | V.20 "A failed backing load must remove the loading placeholder and unblock waiting readers" |
| N2 | 2 | 1 | N.3 "Network protocol between shards/nodes ... Out of scope" |

Total ballast = 1+4+1+3+1+4+1+1 = **16**.

## 6.3 Unmatched candidate points

| candidate phrase (verbatim) | flag |
|---|---|
| Dep.10 "A write to an existing key must have an explicitly defined TTL behavior: either reset to full TTL or preserve the remaining TTL" | UNMATCHED — human review |
| V.1 "The capacity limit is expressed in a single unit (entry count or byte budget) applied uniformly across all paths" | UNMATCHED — human review |
| V.3 "TTL is defined as either fixed (from insertion) or sliding (reset on read) and the choice is uniform" | UNMATCHED — human review |
| V.16 "If the backing-store write fails after the cache is updated, the cache must either roll back or surface the failure" | UNMATCHED — human review |
| V.21 "If an approximate eviction policy ... is used, the implementation must declare the accuracy bound" | UNMATCHED — human review |
| V.22 "With a single-entry cache, every write evicts the current occupant ... must not leave the cache empty" | UNMATCHED — human review |
| V.24 "A null or zero-length value must be representable and distinguishable from a cache miss" | UNMATCHED — human review |
| V.31 "A key evicted in the same operation must be immediately re-insertable; eviction must leave no residual bookkeeping" | UNMATCHED — human review |
| V.32 "A partial batch flush ... must clear the dirty flag only for successful entries; failed entries must remain dirty and be retried" | UNMATCHED — human review |
| N.4 "Cache warming / pre-loading ... Out of scope" | UNMATCHED — human review |
| N.6 "Observability / metrics ... Out of scope as a delivered feature" | UNMATCHED — human review |

> Note (not scored): N.5 "Authentication / access control ... Out of scope" maps to the orthogonal authority plane (`Del`, reference §3) — neither credited nor penalized.

## 6.4 Score block

```
COVERAGE (fully-COVERED / total):
  by category:   D = 7/8   Dep = 11/14   V = 19/26   N = 2/5
  by FM tag:     FM-1 = 17/23   FM-2 = 4/6   FM-3 = 8/13   FM-4 = 2/2   FM-5 = n/a   FM-6 = n/a   FM-7 = 1/1
  PARTIAL counts: D = 0   Dep = 0   V = 2   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 16
  unmatched candidate points (human-review flag):    total = 11
```
