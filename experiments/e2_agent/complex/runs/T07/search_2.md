# T07 — Search Pass 2 (holes in D1)

Only genuinely new content — items with no distinct falsifier already captured in D1.

---

## Missing components / sub-goal gaps

**S2-1 Backing-store read path absent from D.7**
D.7 (persistence adapter) specifies only write operations (synchronous put, enqueue). A cache miss requires a READ from the backing store, but no component owns that responsibility. D.2 assumes a backing read happens but names no executor.
*Falsifier*: cache miss calls the backing store directly outside the adapter abstraction → error handling, retry policy, and timeout differ between the read and write paths; a backing-store schema change breaks only one path silently.

**S2-2 Loading placeholder unblock mechanism**
D.2 says competing threads "block on the same placeholder" but specifies no mechanism (condition variable, future/promise, monitor). Without an explicit unblock signal, the implementation defaults to spin-polling or never wakes blocked readers.
*Falsifier*: load completes, placeholder replaced by real entry; blocked readers are never signaled; they spin or sleep indefinitely rather than returning the loaded value.

**S2-3 Per-shard vs global capacity accounting**
D.10 and V.1/V.7 do not decide whether the capacity limit is enforced per-shard or globally. The choice produces qualitatively different failure modes; neither is trivially safe.
*Falsifier (per-shard)*: hot shard hits its per-shard limit and evicts while cold shards have free slots → effective cache size is fraction of declared limit under key skew.
*Falsifier (global)*: global counter is a shared mutable integer updated on every insert/evict under high write load → counter becomes a serialization bottleneck or drifts under concurrent increment/decrement without CAS.

**S2-4 LFU frequency counter aging / decay**
D.5 names LFU as a candidate policy but does not require frequency counters to decay over time. Without decay, entries inserted during a historical access burst permanently dominate eviction order.
*Falsifier*: LFU mode, startup burst inflates counters to 10^6; new entries with counter=1 are always evicted first; cache never adapts to changed access pattern; hit rate collapses under workload shift with no error surfaced.

**S2-5 Bulk / sweep-all operation (clear, resize, get-many)**
No component covers operations that span ALL shards: cache.clear(), capacity resize, or multi-key get. These require acquiring all shard locks in a globally consistent order and flushing all dirty entries.
*Falsifier*: cache.clear() acquires shard locks in arbitrary order; concurrent cross-shard eviction or resize acquires them in a different order → deadlock. Or: clear() wipes the index without draining the flush queue → flush worker later writes already-cleared entries back to the backing store.

---

## Missing cross-component interaction seams

**S2-6 Read path → eviction metadata update (within shard lock)**
On every cache hit, the read path must update the entry's access metadata (last-access timestamp for LRU, frequency counter for LFU) atomically inside the shard lock. No Dep seam captures this interaction between D.3 and D.5.
*Falsifier*: last-access updated after the shard lock is released; eviction engine reads stale metadata and evicts a recently accessed entry; hit rate drops under concurrent read load with no error surfaced.

**S2-7 Write path → eviction policy metadata refresh on update**
Writing to an existing key should refresh its position in the eviction order (move to MRU for LRU; increment counter for LFU). D.4 groups insert and update but neither D.4 nor D.5 specifies this refresh. Different from S2-6 (which is for reads).
*Falsifier*: LRU cache; key is written repeatedly; last-access not updated on write → key sits at the LRU tail and is evicted on the next capacity pressure despite being actively written.

**S2-8 Write-back flush queue ↔ key-level deduplication**
D.8 calls the queue "ordered" but does not require per-key coalescing. N writes to the same key between two flush cycles should produce one flush entry (the latest version), not N entries.
*Falsifier*: hot key updated 10^6 times between flush cycles; queue stores 10^6 entries; queue memory limit reached and back-pressure fires even though backing-store state needs only one write; or flush worker issues 10^6 redundant writes under load.

**S2-9 Flush worker ↔ shutdown sequencing (Dep seam for V.25)**
V.25 states the goal (flush before exit) but no Dep seam specifies the ordering: the shutdown signal must reach the flush worker, the worker must drain the queue completely, and the main thread must wait for that drain before releasing resources.
*Falsifier*: shutdown closes the queue (worker can no longer dequeue), then terminates the worker thread → worker exits immediately without draining; dirty entries silently lost despite V.25 requiring flush completeness.

**S2-10 TTL sweeper → loading placeholder (skip rule)**
D.6 (sweeper) scans the index for expired entries. Entries in "loading" state may have a creation timestamp that exceeds the TTL if the backing store is slow. No rule requires the sweeper to skip loading-state entries.
*Falsifier*: sweeper timestamps a loading placeholder as expired and removes it; the in-flight backing load completes and inserts the value into a vacated slot outside the shard index → capacity counter not decremented on removal; new entry not counted in capacity; effective capacity drifts above limit.

---

## Missing global invariants / criteria

**S2-11 Value serializability gate for write-back**
In write-back mode, values inserted into the cache will eventually be serialized for the backing store. A non-serializable value can be inserted successfully but can never be flushed.
*Falsifier*: application inserts a value containing a live file handle; insert succeeds, dirty flag set; flush worker encounters serialization error on every retry; dirty entry occupies its slot indefinitely; capacity reclamation blocked; no error surfaced to the original caller.

**S2-12 Backing-store degraded mode scope boundary**
When the backing store is unreachable, write-through mode has no fallback; write-back mode allows the flush queue to fill. No component and no scope exclusion declares the required behavior (fail-writes, serve-reads-only, queue indefinitely). This is an unresolved scope boundary, not a safely excluded one.
*Falsifier*: backing store goes down; write-through cache rejects all writes with no declared policy; callers receive errors with no degraded-read-only mode; or write-back queue fills to back-pressure limit and all writes block indefinitely — both behaviors are silent without an explicit policy decision.

**S2-13 Write-through operation order (backing store first vs cache first)**
V.16 assumes cache-is-updated when the backing-store write fails. If the implementation writes to the backing store first (before updating the cache), the opposite failure mode is possible: backing-store write succeeds, local cache update fails.
*Falsifier*: write-through, backing-store-first order; backing store write succeeds; local cache update fails (e.g., hash-table resize OOM); cache still holds the old value; next read triggers a backing-store load that returns the new value — cache and backing store transiently diverge with no error surfaced to the caller.

**S2-14 Loading placeholder timeout (hung backing store)**
V.20 covers cleanup when the backing load returns an ERROR. A hung backing store that never returns (no error, no response) leaves the loading placeholder indefinitely. Blocked readers have no timeout mechanism.
*Falsifier*: backing store hangs (TCP connection open, no data); loading placeholder stays in the index forever; all readers for that key block indefinitely; V.20's falsifier ("no timeout on loading state") names the symptom but the criterion requires only error-path cleanup, not a maximum loading duration.

**S2-15 Lock granularity within a shard (per-shard vs per-entry)**
D.10 specifies one lock per shard. For a shard holding many entries, all writes to ANY key in that shard serialize. The task requires high concurrency; shard-level locking under many distinct-key writes within one shard is a throughput floor not addressed.
*Falsifier*: shard contains 10,000 entries for 10,000 distinct keys; 100 threads each writing a different key in that shard serialize on the single shard lock → write throughput scales as 1/N with thread count rather than 1/shard-count; only detectable under realistic write load.

---

## Scope boundary: missing explicit exclusion

**S2-16 Cache warming / read-repair on miss**
When an entry is not in the cache, the read path loads from the backing store and populates the cache (implicit in D.2). But "read-repair" — detecting that the backing store has a newer value on a read hit — is not addressed and not explicitly excluded. If the system operates in multi-writer mode (multiple processes writing to the backing store), a read hit could return a stale in-cache value even if the backing store is more current.
*Why it matters*: if multi-writer is in scope, read-repair must be included; if single-writer only, excluding it is safe. The task says "many threads or nodes" which does not rule out multi-writer. An explicit exclusion with a reasoning clause is needed, not silence.

---

## Summary count

| Category | New items |
|----------|-----------|
| Missing components | 5 (S2-1 – S2-5) |
| Missing seams | 5 (S2-6 – S2-10) |
| Missing invariants / criteria | 5 (S2-11 – S2-15) |
| Missing scope exclusion | 1 (S2-16) |
| **Total new holes** | **16** |
