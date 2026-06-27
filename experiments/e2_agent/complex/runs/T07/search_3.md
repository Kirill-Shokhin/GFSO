# T07 — Search Pass 3

**Input**: D2.md (77 items). Surface only genuinely new content.

---

## Genuinely new holes

**H3-1 — Invalidation send side (missing component)**
The write path must emit invalidation signals to peer cache nodes after a write; D.9 only covers the receiving/handling side. Dep.7 states the requirement ("all peer cache nodes must receive an invalidation") but no component or Dep seam names the emitter: who constructs the signal, on which write events (write-through? write-back after flush? both?), and via what channel. Without a named send-side component, the interaction between write path and remote D.9 handlers is a gap in the design — not just an implementation detail.
*Falsifier*: write-through completes; no emit step is coded; peer nodes never receive the invalidation and continue serving the stale value indefinitely — identical to Dep.7's falsifier, but caused by a missing component rather than a missing requirement.

**H3-2 — Sliding TTL: read path → expiry timestamp reset (missing Dep seam)**
Dep.10 covers the write path TTL policy (reset vs preserve). Dep.16 covers the read path → LRU/LFU eviction metadata update. Neither covers the symmetric case: when sliding TTL is in effect, a cache hit must atomically update the entry's expiry deadline (not just its last-access timestamp) inside the shard lock before releasing it. The sweeper (D.6) inspects the expiry deadline independently, with no coordination.
*Falsifier*: sliding TTL configured; read hit updates last-access (Dep.16) but does not reset the expiry timestamp; sweeper runs, finds the timestamp past deadline, and evicts an actively-accessed entry; caller receives a spurious cache miss with no error — hit rate silently degrades under read-heavy workload.

**H3-3 — Shard lock scope during dirty flush on eviction (missing protocol + failure)**
Dep.3 requires that a dirty entry be flushed before its index removal. But backing-store I/O cannot block with the shard lock held (shard throughput collapses; V.19 re-entrancy may deadlock if flush tries to clear the dirty flag via the same lock path). The alternative — release the shard lock, flush, then re-acquire to remove the index entry — opens a limbo window where the entry is absent from the index but not yet in the backing store. A concurrent reader misses, goes to the backing store, gets the old value, and inserts it; when the flush then completes with the new value, the cache holds the old version while the backing store has the new one.
*Falsifier*: high-concurrency eviction of a dirty entry; shard lock released before flush completes; concurrent miss reader loads and caches the pre-write backing-store value; flush then writes the new value to the backing store; cache and backing store silently diverge until the cache entry expires or is next evicted.

**H3-4 — Out-of-order invalidation version filtering (missing invariant)**
D.1 includes a version counter per entry. V.6 and Dep.11 apply version ordering to the FLUSH path (a flush must not overwrite a newer backing-store state). Neither covers the INVALIDATION path: if two writes W1 (version 1) and W2 (version 2) each emit an invalidation signal, and I2 arrives and is processed before I1, then I1 — when it arrives late — can remove the value written by W2 (which was already re-inserted after I2). There is no requirement that incoming invalidation signals carry the version that triggered them, or that the handler reject a signal for a version older than the current entry.
*Falsifier*: two rapid writes to the same key; invalidations delivered out of order; late-arriving older invalidation removes the current-version value; subsequent reads are cache misses and load the older value from the backing store with no error or metric surfaced.

**H3-5 — Write path response when flush queue is saturated (missing seam)**
D.8 declares the queue is bounded and "implements back-pressure when the backing store is slow." V.37 declares a degraded-mode policy for backing-store unavailability in general terms. Neither specifies what the WRITE PATH concretely does when the flush queue is at capacity: block the calling thread (risks deadlock if the caller holds any shard lock), return an error to the caller (changes the write API contract), or force a synchronous flush inline (may hold shard lock during backing-store I/O, conflicting with H3-3). Each option has a distinct failure mode and must be an explicit design decision.
*Falsifier*: backing store slow; flush queue fills to capacity; write path blocks caller thread that holds a shard lock; flush worker needs to acquire the same shard lock to dequeue an entry → deadlock; no timeout or error recovery; system hangs with no signal.

**H3-6 — Shard lock release during backing-store miss load (missing protocol)**
On a cache miss, D.2 creates a loading placeholder and D.7 performs the backing-store read. The shard lock must be RELEASED before the backing-store I/O begins; otherwise all concurrent reads and writes to that shard block for the entire backing-store round-trip. Dep.12 covers the race condition when a concurrent write arrives before the load completes (loaded value must not overwrite the newer write), but does not state that the shard lock must be released for the I/O phase nor specify the exact re-acquire protocol. The failure mode of holding the lock is distinct from the race Dep.12 describes.
*Falsifier*: cache miss; shard lock held while backing-store read is in flight; 50 ms backing-store latency; all other threads targeting that shard block for 50 ms per miss; under moderate miss rate, shard becomes a serialization bottleneck indistinguishable from a global lock — detectable only under realistic miss-rate load, not in unit tests.

---

## Summary

| Item | Category | Distinct falsifier |
|------|----------|--------------------|
| H3-1 | D (missing component: invalidation emitter) | peers never invalidated despite requirement |
| H3-2 | Dep (read path → TTL reset for sliding TTL) | sweeper evicts actively-read entry |
| H3-3 | Dep (shard lock scope during dirty eviction flush) | cache/backing-store diverge via concurrent miss during flush |
| H3-4 | V (out-of-order invalidation version filtering) | stale invalidation silently removes current-version entry |
| H3-5 | Dep (write path behavior at flush queue saturation) | shard-lock deadlock under queue full + slow backing store |
| H3-6 | Dep (shard lock release protocol during miss load) | shard serializes to single-thread throughput under miss rate |

**6 genuinely new holes.**
