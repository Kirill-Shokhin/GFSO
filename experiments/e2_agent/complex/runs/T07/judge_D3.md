# BLIND JUDGE VERDICT — T07 — candidate D3

## 6.1 Mapping table

| ref-id | category | FM-tag(s) | verdict | candidate evidence (verbatim quote) | note (missing leg / which candidate points) |
|---|---|---|---|---|---|
| D1 | D | — | COVERED | "Each entry carries: key, value, creation timestamp, TTL, last-access timestamp, dirty flag, version counter" (D.1); get/put via D.3/D.4 | keyed store + get/put/delete present |
| D1a | D | — | NOT-COVERED | | no compound-atomic-op API contract (computeIfAbsent/putIfAbsent/replace-CAS/getAndSet with per-op atomicity); the loading placeholder (D.2) is credited at V-F1, not as an RMW-API contract |
| D2 | D | — | COVERED | "Owns the fixed … shard count, the deterministic key → shard hash function, and the per-shard lock" (D.10) | synchronization mechanism (per-shard locks) |
| D3 | D | — | COVERED | "Exactly one eviction policy (LRU, LFU, CLOCK, FIFO, or TTL-first) is chosen and consistently applied" (V.2); engine D.5 | + V.2, V.34 (ballast) |
| D4 | D | — | COVERED | "Lookup key → check existence → check expiry → … return value" (D.3); + sweeper D.6 | per-entry TTL + serve-as-absent + reclamation |
| D5 | D | — | COVERED | "The persistence mode (write-through or write-back) is a single global policy with a well-defined ack point" (V.4); adapter D.7, dirty flag D.1 | + D.8, D.11, V.35 (ballast) |
| D6 | D | — | COVERED | "Receives invalidation signals (local or remote) and removes or marks stale the specified entries" (D.9); emitter D.13 | + D.13 (ballast) |
| D7 | D | — | COVERED | "the deterministic key → shard hash function … Routes every key operation to exactly one shard" (D.10) | sharding + shard-map fn |
| Dep1 | Dep | FM-1 | COVERED | "If an entry is evicted while a reader holds a reference to its value, the value buffer must remain valid for the reader's lifetime (copy semantics or reference counting)" (Dep.15) | evict-vs-in-use; per ref Dep1/Dep10 merge rule this single point credits both |
| Dep2 | Dep | FM-2 | COVERED | "only one must succeed in removing it; double-removal must not corrupt the capacity counter" (Dep.6) | reclaim-exactly-once; + Dep.13 (ballast) |
| Dep3 | Dep | FM-1 | COVERED | "Evicting a dirty entry requires a synchronous flush before removal from the index; if flush fails the entry must not be removed" (Dep.3) | flush-on-evict |
| Dep4 | Dep | FM-1 | NOT-COVERED | | no expiry-vs-flush seam: nothing asserts that TTL-expiring a dirty entry must still flush / must not persist a stale value (distinct from Dep3 evict and Dep6 reclaim) |
| Dep5 | Dep | FM-1 | COVERED | "An invalidation racing an in-flight read must not allow the read to return a value that was invalidated before the read's lock was acquired" (Dep.4) | invalidation-vs-read |
| Dep6 | Dep | FM-1 | COVERED | "the read path must update the entry's access metadata (last-access … for LRU, frequency counter for LFU) atomically inside the shard lock" (Dep.16) | atomic recency/stats; + Dep.17 (ballast) |
| Dep7 | Dep | FM-1 | COVERED | "check capacity → evict if needed → insert/update entry" (D.4); byte budget V.1; "capacity counter accounts for all live data" (V.18) | accounting triggers eviction; byte-cost present |
| Dep8 | Dep | FM-2 | COVERED | "must explicitly declare whether the capacity limit is enforced per-shard or globally … hot shard hits its per-shard limit … effective cache size is a fraction" (V.33) | per-shard↔global bound, skew |
| Dep9 | Dep | FM-2 | COVERED | "If two invalidations for the same key arrive out of order … the late-arriving I1 must not remove or stale the value written by W2" (V.40) | cross-node invalidation ordering / concurrent updates |
| Dep10 | Dep | FM-1 | COVERED | merged with Dep1 via Dep.15 "evicted while a reader holds a reference … buffer must remain valid" | per ref Dep1/Dep10 adjudication: credit one, the other is a non-redundancy merge, NOT a hole |
| Dep11 | Dep | FM-1 | COVERED | "Eviction must complete and the victim must be fully removed … before the new entry is inserted … Falsifier: insert before eviction completes → transient capacity breach" (Dep.1) | insert↔evict ordering on full store |
| Dep12 | Dep | FM-2 | COVERED | "A thread that writes a key and then reads it sees its own write, not a prior value or a stale cache entry" (V.9) | read-your-writes / publication |
| Dep13 | Dep | FM-1 | COVERED | "shard-count changes require a coordinated transition; no thread uses a cached shard-map … key routed to wrong shard during transition" (V.15) | rehash/resize × concurrent ops |
| Dep14 | Dep | FM-1 | COVERED | "An invalidation arriving while an entry is in the 'loading' state must cause the completed load to be discarded rather than inserted" (Dep.9) | delete/invalidation-vs-in-flight-load resurrection; + Dep.11, V.6 (ballast) |
| V-I1 | V | FM-1 | COVERED | "Concurrent writes to the same key resolve to exactly one winner; the losing write is either rejected or explicitly superseded" (V.8) | + Dep.12 (ballast) |
| V-I2 | V | FM-1 | COVERED | "no thread observes an entry in a partial-transition state" (V.5) | no torn read |
| V-I3 | V | FM-1 | COVERED | "all peer cache nodes must receive an invalidation before they serve reads for the updated key … Falsifier: … stale reads despite a durable write" (Dep.7) | no stale read after commit |
| V-I4 | V | FM-1 | COVERED | "At no point does the number (or total byte size) of entries exceed the declared limit, even transiently" (V.7) | + V.1, V.13 (ballast) |
| V-I5 | V | FM-1 | COVERED | "only flushed-and-acknowledged entries may be reclaimed" (Dep.8) | durable-flush-before-reclaim; + V.12 (ballast) |
| V-I6 | V | FM-1 | COVERED | "periodically scans and removes expired entries without waiting for a read or write … Falsifier: lazy-only expiry lets expired entries accumulate" (D.6) | active sweep / no leak |
| V-I7 | V | FM-1 | COVERED | "The capacity counter accounts for all live data including metadata overhead … not just payload bytes" (V.18) | counter/size-accounting accuracy |
| V-I8 | V | FM-4 | COVERED | "Any operation acquiring multiple locks … acquires them in a globally consistent total order" (V.11) | deadlock-freedom; + D.12, Dep.14, V.14, V.19 (ballast) |
| V-I9 | V | FM-2 | NOT-COVERED | | no distinct per-key value-coherence predicate (one current value across all readers/shards); coverage of routing (D7) and no-stale (V-I3) does not separately assert it |
| V-I10 | V | FM-2 | COVERED | "shard A locked, entry removed; before shard B locked, another thread reads the key → key appears absent in both shards" (Dep.5) | key-in-limbo / one-route-per-key |
| V-I11 | V | FM-1 | COVERED | "No entry is returned to a caller after its TTL has elapsed" (V.10) | never-serve-expired |
| V-E1 | V | FM-3 | NOT-COVERED | | the concurrent-get+evict boundary content is credited at Dep1/Dep10; no separate point names it as a boundary case |
| V-E2 | V | FM-3 | COVERED | "The expiry check and the value return must occur within the same lock window; the lock must not be dropped between the check and the return" (Dep.2) | atomic check-and-serve at expiry |
| V-E3 | V | FM-3 | NOT-COVERED | | no full-insert-with-no-evictable-victim / all-pinned corner + fallback |
| V-E4 | V | FM-3 | COVERED | "Under key-skewed access, throughput must not degrade to single-shard serialization … the design must account for hot-key scenarios" (V.26) | hot-key contention |
| V-E5 | V | FM-3 | COVERED | "Mass cache invalidation must not produce O(N) simultaneous backing-store reads; the fill path must include rate-limiting, jitter, or coalescing" (V.29) | mass-reclaim reload stampede (the "and/or reload stampede" leg) |
| V-E6 | V | FM-3 | COVERED | "TTL expiry across nodes must not rely on synchronized wall clocks without declaring a divergence tolerance" (V.27) | clock skew for TTL |
| V-E7 | V | FM-3 | COVERED | "A single entry whose byte size exceeds one shard's byte limit must be rejected cleanly at insert time, not admitted and then immediately evicted in a loop" (V.30) | oversized value, no evict-everything loop |
| V-E8 | V | FM-3 | COVERED | "Two distinct keys mapping to the same shard slot must be stored and retrieved independently; hash equality must not be treated as key equality" (V.28) | collision identity by equality |
| V-E9 | V | FM-3 | PARTIAL | "A TTL of zero or negative must be rejected at insert time or treated as immediate expiry" (V.23) | covers zero/negative leg; MISSING: no-TTL/eternal, TTL==now, far-future conventions |
| V-E10 | V | FM-3 | NOT-COVERED | | no idempotent-delete-of-absent-key boundary (no negative size / spurious flush/invalidate) |
| V-E11 | V | FM-3 | NOT-COVERED | | no update-in-place size-delta (−old+new) boundary; Dep.10/Dep.17 cover TTL/recency refresh, not the size double-count |
| V-F1 | V | FM-4 | COVERED | "other threads block on the same placeholder rather than each issuing their own backing read" (D.2) | single-flight / stampede on miss |
| V-F2 | V | FM-3 | COVERED | "either guarantee delivery or provide a re-sync / TTL-bounded fallback so that stale values do not persist indefinitely after a dropped message" (V.17) | invalidation can silently miss + backstop |
| V-F3 | V | FM-7 | COVERED | "The write-back cache must flush all dirty entries before process exit; the shutdown sequence must not skip the flush" (V.25) | shutdown drain channel; + Dep.18 (ballast) |
| V-F4 | V | FM-3 | COVERED (N/A) | lock-based design — "a single lock is used per shard" (V.39); per-shard locks (D.10) | scope-gated: ref Appendix — N/A / full credit when concurrency control is lock-based (no lock-free CAS reclamation) |
| N1 | N | FM-1 | COVERED | "an in-memory cache is understood to be volatile; durability is delegated to the backing store" (N.2) | backing-store durability assumed |
| N2 | N | FM-1 | COVERED | "strong consistency across nodes requires a consensus protocol … Out of scope" (N.1) | partition/consensus out of scope; + N.3 (ballast) |
| N3 | N | FM-1 | NOT-COVERED | | no allocator/GC-assumed-sound exclusion |
| N4 | N | FM-1 | NOT-COVERED | | no value-immutability-vs-defensive-copy stated assumption |
| N5 | N | FM-1 | NOT-COVERED | | no serialization-out-of-scope / cost-via-named-size-function exclusion |

## 6.2 Ballast list

| ref-id | # candidate points mapped | ballast (count − 1) | the duplicate candidate phrases |
|---|---|---|---|
| D3 | 3 | 2 | D.5 (eviction engine); V.2 (eviction policy identity); V.34 (LFU decay) |
| D4 | 2 | 1 | D.3 (read-path expiry check); V.3 (TTL semantics uniformity) |
| D5 | 5 | 4 | D.7 (persistence adapter); D.8 (flush queue); D.11 (background flush worker); V.4 (write mode policy); V.35 (flush coalescing) |
| D6 | 2 | 1 | D.9 (invalidation receive); D.13 (invalidation emit) |
| Dep2 | 2 | 1 | Dep.6 (eviction↔sweeper); Dep.13 (eviction↔invalidation idempotent) |
| Dep6 | 2 | 1 | Dep.16 (read-hit metadata); Dep.17 (write metadata refresh) |
| Dep11 | 2 | 1 | Dep.1 (write→eviction order); D.4 (write path check-capacity-evict-insert) |
| Dep14 | 3 | 2 | Dep.9 (loading↔invalidation discard); Dep.11 (flush↔invalidation version check); V.6 (version ordering on flush) |
| V-I1 | 2 | 1 | V.8 (no-lost-write serialize); Dep.12 (load overwrites newer write) |
| V-I4 | 3 | 2 | V.7 (no transient breach); V.1 (capacity unit uniformity); V.13 (crash-safe dirty bound) |
| V-I5 | 2 | 1 | Dep.8 (reclaim only after flush-ack); V.12 (write-through durability) |
| V-I8 | 5 | 4 | V.11 (multi-lock order); D.12 (bulk all-shard order); Dep.14 (sweeper per-entry lock); V.14 (worker liveness); V.19 (lock re-entrancy) |
| V-F3 | 2 | 1 | V.25 (shutdown flush); Dep.18 (flush worker↔shutdown sequencer) |
| N2 | 2 | 1 | N.1 (consensus); N.3 (network protocol) |
| **total** | | **23** | |

## 6.3 Unmatched candidate points

| candidate phrase (verbatim) | flag |
|---|---|
| "A write to an existing key must have an explicitly defined TTL behavior: either reset to full TTL or preserve the remaining TTL" (Dep.10) | UNMATCHED — human review |
| "The sweeper must skip entries whose state is 'loading' even if their creation timestamp exceeds the TTL" (Dep.19) | UNMATCHED — human review |
| "When sliding TTL is in effect, a cache hit must atomically reset the entry's expiry deadline" (Dep.20) | UNMATCHED — human review |
| "releasing the lock before flush creates a limbo window … cache and backing store silently diverge" (Dep.21) | UNMATCHED — human review |
| "The write path must declare a concrete response when the flush queue is at capacity" (Dep.22) | UNMATCHED — human review |
| "On a cache miss, the shard lock must be released before the backing-store I/O begins" (Dep.23) | UNMATCHED — human review |
| "If the backing-store write fails after the cache is updated, the cache must either roll back or surface the failure" (V.16) | UNMATCHED — human review |
| "A failed backing load must remove the loading placeholder and unblock waiting readers … a maximum loading duration must be declared" (V.20) | UNMATCHED — human review |
| "If an approximate eviction policy … is used, the implementation must declare the accuracy bound" (V.21) | UNMATCHED — human review |
| "With a single-entry cache, every write evicts the current occupant … must not leave the cache empty" (V.22) | UNMATCHED — human review |
| "A null or zero-length value must be representable and distinguishable from a cache miss" (V.24) | UNMATCHED — human review |
| "A key evicted in the same operation must be immediately re-insertable; eviction must leave no residual bookkeeping ('ghost' entry)" (V.31) | UNMATCHED — human review |
| "A partial batch flush where some entries succeed and others fail must clear the dirty flag only for successful entries" (V.32) | UNMATCHED — human review |
| "In write-back mode, a value that cannot be serialized for the backing store must be rejected at insert time" (V.36) | UNMATCHED — human review |
| "The required behavior when the backing store is unreachable must be explicitly declared" (V.37) | UNMATCHED — human review |
| "The write-through implementation must declare which write completes first — backing-store or local cache" (V.38) | UNMATCHED — human review |
| "If a single lock is used per shard, the implementation must declare the expected throughput floor under many-distinct-key concurrent writes" (V.39) | UNMATCHED — human review |
| "Cache warming / pre-loading … Out of scope" (N.4) | UNMATCHED — human review |
| "Observability / metrics … Out of scope as a delivered feature" (N.6) | UNMATCHED — human review |
| "Read-repair / multi-writer mode … Out of scope if the system operates in single-writer mode" (N.7) | UNMATCHED — human review |

> Out-of-plane note (not scored, not unmatched): "Authentication / access control … Out of scope" (N.5) is the orthogonal authority/`Del` plane (ref §3) — neither credited nor penalized.

## 6.4 Score block
```
COVERAGE (fully-COVERED / total):
  by category:   D = 7/8   Dep = 13/14   V = 20/26   N = 2/5
  by FM tag:     FM-1 = 19/23   FM-2 = 5/6   FM-3 = 8/13   FM-4 = 2/2   FM-5 = n/a   FM-6 = n/a   FM-7 = 1/1
  PARTIAL counts: D = 0   Dep = 0   V = 1   N = 0
NON-REDUNDANCY:
  ballast points (duplicate candidate→one ref item): total = 23
  unmatched candidate points (human-review flag):    total = 20
```
