# Architecture

CacheLab uses composition:

- `Cache` coordinates public APIs and lifecycle.
- `CacheShard` owns one lock, backend, policy, stats counters, single-flight
  registry, version marks, and tombstones.
- `StorageBackend` stores `CacheEntry` objects.
- `EvictionPolicy` implementations track capacity metadata only.
- Worker components communicate with explicit job dataclasses.

The cache core enforces this invariant after every mutation: backend contents
and policy metadata are updated together under the same shard lock.
