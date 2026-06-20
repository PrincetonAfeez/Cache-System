# ADR 0001: Cache architecture — sharded in-memory cache with policy abstraction

- **Status:** Accepted
- **Date:** 2026-06-19

## Context

CacheLab is a CLI-first Python caching library that must support:

- thread-safe reads and writes under concurrent access;
- swappable eviction policies (LRU, LFU, FIFO) without changing the cache core;
- TTL expiration via both lazy checks on the request path and active background cleanup;
- single-flight loading so concurrent misses for the same key share one loader;
- optional write-through and write-back persistence to a slow backend;
- structured stats, version markers, and tombstones for write-back correctness;
- use as both a library API and a stateless CLI.

A single global lock would keep the implementation simple but would serialize unrelated
keys and bottleneck read-heavy workloads. A single monolithic backend would also mix
eviction policy logic with storage, TTL, and concurrency concerns.

## Decision

Use a **`Cache` facade** over **deterministic shards**. Each shard owns:

- an `InMemoryBackend` for entry storage;
- a dedicated `MeteredRLock` so unrelated keys usually contend on different locks;
- one `EvictionPolicy` instance (LRU, LFU, or FIFO) selected at construction time;
- per-shard stats counters;
- a single-flight registry for `get_or_compute`;
- monotonic version markers and delete tombstones for write-back safety.

The cache core routes keys to shards with a **process-stable hash** that canonicalizes
the numeric tower, so keys equal under `==` but with different representations
(`1`, `1.0`, `True`) always land on the same shard. Total capacity is split across
shards (`capacity >= shard_count`); each shard enforces its own slice of the budget.

The core **does not branch on policy type**. All policies implement a shared
`EvictionPolicy` contract; backend contents and policy metadata are updated together
under the same shard lock after every mutation.

Background maintenance (active expiration, write-back flushes, preloads, stat snapshots)
is handled by a **bounded job queue** and **worker pool** fed by explicit dataclass
messages, keeping maintenance work off the hot request path.

## Consequences

### Positive

- **Reduced lock contention:** unrelated keys usually acquire different shard locks,
  improving concurrency on read-heavy workloads compared with one global lock.
- **Swappable policies:** new eviction strategies can be added by implementing the
  shared policy contract without modifying `Cache` or `CacheShard`.
- **Clear separation of concerns:** storage, eviction metadata, TTL, single-flight,
  and write-back versioning live at the shard layer; workers handle asynchronous work.
- **Deterministic routing:** stable hashing avoids misses caused by Python's randomized
  `hash()` and by equivalent keys with different types/representations.

### Negative

- **Split capacity:** total capacity is divided across shards, so effective eviction
  behavior depends on key distribution; uneven routing can leave some shards fuller
  than others.
- **Higher structural complexity:** shard routing, per-shard locks, version markers,
  tombstones, and worker queues add more moving parts than a single-dict cache.
- **Routing invariant:** key routing must remain stable for the lifetime of a cache
  instance; changing shard count or hash rules would invalidate existing placement
  assumptions.

## Alternatives considered

| Alternative | Why not chosen |
|-------------|----------------|
| Single global lock + one backend | Simple, but serializes all operations and limits scalability under concurrency. |
| Policy-specific branches inside `Cache` | Would couple the core to each policy and make adding policies error-prone. |
| Python built-in `hash()` for routing | Randomized per process; equivalent keys with different representations could diverge. |
| TTL-only lazy expiration | Stale entries could linger indefinitely without active expiration workers. |

## References

- [`README.md`](../../README.md) — architecture overview, policies, TTL, workers, write modes
- [`docs/architecture.md`](../architecture.md) — composition and shard invariants
- [`src/cachelab/core/cache.py`](../../src/cachelab/core/cache.py) — `Cache` facade
- [`src/cachelab/concurrency/shards.py`](../../src/cachelab/concurrency/shards.py) — `CacheShard` definition
