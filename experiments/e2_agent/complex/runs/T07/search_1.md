# T07 — Search Pass 1 (exhaustive, no prior decomposition)

Task: Design the logic of a concurrent in-memory cache/store: read/write path, eviction policy, per-entry TTL/expiry, write-through or write-back persistence backing, invalidation on update, sharding/partitioning — specifying how these mechanisms interact for consistency and bounded capacity under concurrent access.

---

## Group 1 — Domain Primitives

1. **Entry structure** — Each cached entry must carry key, value, creation timestamp, TTL, last-access timestamp, dirty flag, and version counter. — *Falsifier: omitting the dirty flag causes write-back to silently drop unflushable entries on eviction.*

2. **Capacity unit** — Capacity limit must be expressed in a single unit (entry count OR byte budget) applied uniformly. — *Falsifier: mixing count and byte limits in different paths allows silent capacity breach.*

3. **Eviction policy identity** — Exactly one eviction policy (LRU, LFU, CLOCK, FIFO, or TTL-first) must be chosen and consistently applied to every eviction decision. — *Falsifier: two code paths using different policies produce non-deterministic capacity behaviour under load.*

4. **TTL semantics** — TTL must be defined as either fixed (from insertion) or sliding (reset on read); the choice must be uniform across all entries. — *Falsifier: mixing both semantics causes entries to expire at unpredictable times, breaking staleness SLA.*

5. **Write mode** — The persistence mode (write-through vs. write-back) must be a single global policy with a well-defined ack point. — *Falsifier: mixing modes per-entry makes durability guarantees impossible to reason about.*

6. **Shard count and hash function** — Number of shards must be fixed (or explicitly versioned for resize), with a deterministic key → shard mapping. — *Falsifier: non-deterministic routing sends reads and writes to different shards for the same key.*

---

## Group 2 — Entry Lifecycle / State

7. **Entry state machine** — An entry transitions through: absent → loading → present-fresh → present-stale → evicting. All transitions must be atomic from other threads' perspectives. — *Falsifier: a thread observes an entry mid-transition and reads a partial state (e.g., value set but TTL not yet set).*

8. **Loading / population state** — On a cache miss, the entry must move to a "loading" placeholder before the backing read, so other threads block on the same miss rather than each issuing their own backing read. — *Falsifier: N threads all miss the same key and issue N concurrent backing reads (thundering herd).*

9. **Dirty-bit lifecycle** — Dirty bit is set on write, cleared only after successful flush to backing store; eviction of a dirty entry must flush-then-clear atomically. — *Falsifier: dirty bit cleared before flush confirmation → data loss if flush fails or is interrupted.*

10. **Expiry evaluation point** — Expiry must be checked at the moment of value return to the caller, not at the moment the entry is found in the index. — *Falsifier: entry found, TTL checked, then lock dropped and re-acquired for value return — entry appears fresh but is actually expired between the two lock windows.*

11. **Version / generation counter** — Each write to a key increments a monotonic version; reads and flushes must compare versions to detect stale operations. — *Falsifier: two concurrent writes to the same key, slower write flushes after faster one, silently reverting the newer value.*

---

## Group 3 — Components

12. **Read path** — Lookup key → check existence → check expiry → acquire read lock → return value. Must be non-blocking for concurrent readers when no write is in progress. — *Falsifier: global write lock taken on every read → serialised throughput, not concurrent.*

13. **Write path** — Acquire write lock → check capacity → evict if needed → insert/update entry → set dirty or flush → release lock. Must be atomic with respect to readers. — *Falsifier: a reader sees the new key but not the new value (partial write visible).*

14. **Eviction engine** — Selects and removes the victim entry according to the policy; must be callable both inline (on-write) and by a background sweeper. — *Falsifier: eviction only on write path means expired-but-not-written entries never reclaimed (phantom fullness).*

15. **TTL / expiry sweeper** — Background worker that periodically scans entries and removes expired ones without waiting for a read or write to trigger lazy expiry. — *Falsifier: lazy-only expiry lets expired entries accumulate and exhaust capacity even when no writes arrive.*

16. **Persistence adapter** — Abstraction over the backing store (write-through: synchronous put before ack; write-back: async flush queue). — *Falsifier: backing store latency spikes block the write path under write-through with no adapter isolation.*

17. **Write-back flush queue** — Ordered, bounded queue of dirty entries awaiting flush; must handle back-pressure when backing store is slow. — *Falsifier: unbounded queue allows dirty entries to accumulate in memory, defeating the cache's memory bound.*

18. **Invalidation handler** — Receives invalidation signals (from self or remote) and removes or marks stale the specified entries. — *Falsifier: invalidation handler absent → stale entries persist after an authoritative update elsewhere.*

19. **Shard manager** — Routes every key operation to exactly one shard; owns lock-per-shard. — *Falsifier: two operations on the same key routed to different shards → two authoritative copies with no reconciliation.*

20. **Background flush worker** — Periodically drains the write-back flush queue to the backing store; must be restartable and report errors. — *Falsifier: worker silently exits on first backing-store error, leaving all subsequent dirty entries unflushable.*

---

## Group 4 — Global Invariants

21. **Capacity invariant** — At no point in time does the number (or total byte size) of entries exceed the declared limit, even transiently between eviction and insertion. — *Falsifier: insert-then-evict ordering allows one extra entry to exist momentarily, which may matter for hard-limit enforcement.*

22. **No-lost-write invariant** — Concurrent writes to the same key must resolve to exactly one winner; the losing write must either be rejected or explicitly superseded. — *Falsifier: two writers both succeed, later reader sees an arbitrary interleaving of partial field updates.*

23. **Read-your-writes** — A thread that writes a key and then reads it must see its own write, not a prior value or a stale cache entry. — *Falsifier: write goes to shard A's write buffer; read hits shard A's read path before buffer is applied → stale read.*

24. **Bounded staleness (TTL)** — No entry is returned to a caller after its TTL has elapsed; tolerance of at most one sweeper interval is acceptable only if declared. — *Falsifier: expired entry returned because expiry check uses wall clock but entry timestamp was set with a different clock source.*

25. **Deadlock freedom** — Any operation that acquires multiple locks (e.g., cross-shard move, flush + eviction) must acquire them in a globally consistent order. — *Falsifier: shard A → shard B in one path and B → A in another → classic deadlock under concurrent cross-shard ops.*

26. **Durability invariant (write-through)** — A successful write-through ack implies the value is in the backing store; crash after ack must not lose the entry. — *Falsifier: cache updated and ack sent before backing-store write completes → crash loses the write.*

27. **Crash-safe dirty bound (write-back)** — Number of dirty entries multiplied by max entry size must not exceed available process memory; flush must be triggered before that bound is reached. — *Falsifier: flush only on eviction with a slow backing store allows dirty entries to fill all memory.*

28. **Liveness of background workers** — Sweeper and flush worker must not be starveable by high-throughput read/write operations. — *Falsifier: sweeper holds a low-priority lock that is never granted under write load → expired entries and dirty data accumulate forever.*

29. **Consistent shard view** — All threads agree on the shard topology at any moment; shard-count changes require a coordinated transition, not a hot-swap. — *Falsifier: one thread rehashes while another is mid-operation → key routed to wrong shard during transition.*

---

## Group 5 — Cross-Component Interaction Seams

30. **Write path ↔ Eviction engine** — Eviction must complete and the victim must be fully removed (and flushed if dirty) before the new entry is inserted; the sequence must be atomic at shard level. — *Falsifier: insert happens before eviction completes → capacity briefly exceeded; or new entry overwrites the victim's slot before dirty flush → data loss.*

31. **TTL expiry ↔ Read path** — Expiry check and value return must occur under the same lock window; releasing the lock between check and return allows a concurrent eviction to remove the entry. — *Falsifier: expiry check passes, lock dropped, entry evicted, value returned is a dangling pointer / use-after-free.*

32. **Write-back flush ↔ Eviction engine** — Evicting a dirty entry must synchronously flush before removal from the index; if flush fails, the entry must not be removed. — *Falsifier: dirty entry evicted and removed from index; backing store flush then fails silently → data permanently lost.*

33. **Invalidation handler ↔ Read path** — An invalidation signal and an in-flight read may race; the read must not return a value that was invalidated before the read's lock was acquired. — *Falsifier: read begins, invalidation removes entry, read returns value from its local snapshot → stale value delivered despite invalidation.*

34. **Shard manager ↔ Lock protocol** — A cross-shard operation (e.g., move entry for rebalancing) must acquire both shard locks before mutating either; partial acquisition is forbidden. — *Falsifier: shard A locked, entry removed; before shard B locked, another thread reads the key → appears absent in both shards.*

35. **Eviction policy ↔ TTL sweeper** — The eviction engine and TTL sweeper may both target the same entry simultaneously; only one must succeed in removing it. — *Falsifier: both remove the entry, decrement capacity counter twice → capacity counter goes negative, allowing more entries than limit.*

36. **Write-through ↔ Invalidation** — After a write-through to the backing store, all peer cache nodes (if multi-node) must receive an invalidation before they serve reads for the updated key. — *Falsifier: write-through completes, peer nodes still serve the old value from their caches → stale reads despite durable write.*

37. **Write-back flush queue ↔ Capacity bound** — Dirty entries in the flush queue still count toward capacity; flushed-and-acknowledged entries may be reclaimed. — *Falsifier: capacity computed from index only (not queue) → entries in flight not counted → actual memory usage exceeds declared limit.*

38. **Loading placeholder ↔ Invalidation** — If an invalidation arrives while an entry is in the "loading" state, the completed load must be discarded rather than inserted. — *Falsifier: invalidation received, marked for removal, load completes and inserts stale value anyway → invalidation silently reverted.*

39. **TTL ↔ Write (TTL reset)** — A write to an existing key must explicitly define whether it resets the TTL to full or preserves remaining TTL; ambiguity causes entries to expire at unexpected times. — *Falsifier: write resets TTL when it should not → entries live longer than their SLA; or write preserves TTL when it should not → immediately-inserted values expire before being used.*

40. **Write-back flush ↔ Invalidation handler** — A dirty entry that receives an invalidation while queued for flush must not be flushed (the invalidation supersedes the write, or must be reconciled with a version check). — *Falsifier: invalidation arrives, entry removed from index, flush worker then writes old value to backing store → backing store reverted to stale state.*

41. **Read path ↔ Write-back persistence (on miss)** — A cache miss triggers a load from backing store; the loaded value must be inserted into the cache under the same lock that prevents a concurrent write from being overwritten by the load. — *Falsifier: cache miss, backing load starts; concurrent write updates the key; load completes and inserts old value, overwriting the newer write.*

42. **Eviction engine ↔ Invalidation handler** — An entry being evicted and an invalidation for the same entry arriving simultaneously must be idempotent; double-removal must not corrupt the capacity counter or index. — *Falsifier: eviction and invalidation both remove the entry; capacity counter decremented twice; index becomes inconsistent.*

43. **Shard manager ↔ TTL sweeper** — Sweeper must acquire the shard lock before removing expired entries; it must not hold the lock across the entire sweep of all entries in a shard. — *Falsifier: sweeper holds shard lock for full scan → all reads and writes to that shard blocked for O(n) time.*

44. **Write path ↔ Version counter** — Version increment and value update must be atomic; a reader that sees version N must see the corresponding value, not a value from version N-1 or N+1. — *Falsifier: version incremented before value written → reader sees new version but old value.*

---

## Group 6 — Edge / Boundary Cases

45. **Capacity = 1** — With a single-entry cache, every write must evict the existing entry; evict-then-insert must not deadlock or leave the cache empty after the write. — *Falsifier: eviction of the only entry triggers a cascade that also removes the newly inserted entry.*

46. **TTL = 0 or negative** — Must be rejected at insert time, or treated as immediate expiry (entry never stored or immediately evicted). — *Falsifier: TTL=0 entry stored, read returns it before sweeper runs → effective TTL is sweeper interval, not zero.*

47. **Value = null / zero-length** — Must be representable and distinguishable from a cache miss; a null value is a valid cached result (negative caching). — *Falsifier: null value treated as absent → every read for a null-valued key triggers a backing-store load (stampede).*

48. **Simultaneous eviction + active read** — If an entry is evicted while a reader holds a reference to its value, the value must remain valid for the reader's lifetime (copy semantics or reference counting). — *Falsifier: eviction frees underlying buffer; reader dereferences freed memory → crash or corrupt data.*

49. **All entries dirty at shutdown** — Write-back cache must flush all dirty entries before process exit; shutdown sequence must not skip the flush. — *Falsifier: process exits, dirty entries lost, backing store is out of date with no error logged.*

50. **Hot-key / shard hotspot** — A single key that receives disproportionate traffic causes one shard's lock to become a serial bottleneck. — *Falsifier: throughput scales linearly with shard count in tests but degrades to single-shard throughput in production due to a hot key.*

51. **Clock skew (multi-node)** — TTL expiry based on wall clock behaves inconsistently across nodes with different system clocks. — *Falsifier: an entry expires on node A before node B due to clock skew; node B serves stale value after node A has rejected it.*

52. **Hash collision (same shard slot)** — Two distinct keys mapping to the same shard slot must be stored and retrieved independently (not conflated). — *Falsifier: key2 lookup returns key1's value because hash equality is treated as key equality.*

53. **Invalidation storm** — Mass invalidation of all keys simultaneously causes a thundering herd on the backing store as all misses are filled concurrently. — *Falsifier: cache flushed, all threads simultaneously miss all keys, backing store receives O(N) simultaneous reads and collapses.*

54. **Entry size > shard capacity** — A single entry whose byte size exceeds one shard's byte limit must be rejected cleanly, not silently admitted and then immediately evicted in a loop. — *Falsifier: oversized entry inserted and immediately evicted, insert returns success, but the value is unretrievable.*

55. **Reinsert of just-evicted key** — A key evicted in the same operation must be re-insertable immediately; eviction must not leave a residual "ghost" entry that blocks re-insertion. — *Falsifier: evicted key still present in eviction bookkeeping → second insert fails or creates duplicate.*

56. **Write-back flush partial failure** — Backing store accepts some entries in a batch flush but rejects others; successfully flushed entries must be cleared dirty, failed ones must remain dirty and retried. — *Falsifier: all-or-nothing retry of a batch — re-flushes already-committed entries, causing duplicate writes or overwriting newer backing-store state.*

---

## Group 7 — Silent Failure Modes

57. **Eviction drops dirty entry without flush** — Eviction policy selects a dirty entry but flush is skipped (e.g., backing store temporarily unavailable); entry is removed from index with no error surfaced to the original writer. — *Falsifier: no error returned to writer; backing store silently missing the last write; only detected on next read-through.*

58. **Sweeper exits on first error** — Background TTL sweeper or flush worker catches an error and exits its loop without restart; expired entries and dirty data accumulate with no observable signal. — *Falsifier: backing store rejects one flush; worker exits; dirty entries grow unboundedly; no alert until memory exhaustion.*

59. **Stale routing after shard resize** — Shard count changes; threads using a cached shard-map route operations to the old shard; key exists in new shard, appears absent in old. — *Falsifier: read returns "miss" and triggers unnecessary backing load; write creates a second copy in the old shard.*

60. **Write-through partial success** — Backing store write fails after cache is updated; cache shows new value, backing store retains old value; no rollback is performed. — *Falsifier: cache and backing store diverge; future cache eviction causes reads to return the old backing-store value without error.*

61. **Invalidation message lost** — In a multi-node or async invalidation path, the invalidation event is dropped (network partition, queue overflow); receiving nodes continue serving stale values indefinitely. — *Falsifier: stale reads persist after update with no timeout or re-sync mechanism to detect divergence.*

62. **Capacity counter undercount** — Byte-size counting ignores metadata overhead (key length, timestamps, pointers); actual memory usage exceeds declared limit without triggering eviction. — *Falsifier: OOM kill despite capacity appearing below limit; detected only post-mortem.*

63. **Lock re-entrancy deadlock** — A component acquires shard lock A, then calls a function that also tries to acquire shard lock A (non-reentrant); results in deadlock. — *Falsifier: single-threaded trace shows deadlock on self; hard to detect in code review because call chain is indirect.*

64. **Version counter not checked on flush** — Write-back flush writes entry version N to backing store, but a newer write (version N+1) has already been flushed; version N flush silently reverts the backing store. — *Falsifier: backing store ends up with an older value after a flush completes successfully, with no error.*

65. **Loading placeholder not cleaned on error** — A cache miss triggers a backing load that fails; the loading placeholder is left in the index; subsequent reads block forever waiting for the load to complete. — *Falsifier: all readers for that key hang indefinitely; no timeout on the loading state.*

66. **Approximate LRU admits stale eviction order** — Clock/approximate-LRU algorithms may evict recently-used entries due to approximation; under high load this silently degrades hit rate. — *Falsifier: cache hit rate drops under load but no error is raised; only detectable via metrics.*

---

## Group 8 — Scope Boundaries

67. **Distributed consensus (Raft/Paxos)** — Out of scope: strong consistency across nodes requires a consensus protocol, which is a full subsystem. Pulled back in if the requirement is "all nodes agree on every write before ack." — *Why safely out: the task specifies in-memory store with sharding, not replicated state machine.*

68. **Write-ahead log / crash recovery** — Out of scope for write-back unless the durability SLA requires recovery after crash; if required, a WAL or journal must be explicitly designed. — *Why safely out: in-memory cache is understood to be volatile; durability is delegated to the backing store.*

69. **Network protocol between shards/nodes** — Out of scope if sharding is within a single process (thread-per-shard); pulled in if nodes are separate processes or machines. — *Why safely out: the task does not specify distributed deployment; "nodes" may mean CPU cores.*

70. **Cache warming / pre-loading** — Out of scope: pre-populating the cache on startup is an operational concern, not a correctness mechanism. — *Why safely out: does not affect the logic of read/write/evict/invalidate paths.*

71. **Authentication / access control** — Out of scope: no per-key ACL or caller identity requirement stated. — *Why safely out: the task is about internal store logic, not multi-tenant isolation.*

72. **Observability / metrics** — Out of scope as a delivered feature, but hit rate, eviction rate, and dirty-queue depth are required instrumentation points for verifying correctness of all the above. — *Why safely out: metrics are not part of the cache logic; pulled in as test harness.*
