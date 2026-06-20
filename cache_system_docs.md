# Architecture Decision Record
## App — Cache System
**Cache Infrastructure Group | Document 1 of 5**
**Status: Accepted**

---

## Context

CacheLab is a CLI-first Python caching library that treats a cache as a small systems component rather than a thin dictionary wrapper. The system demonstrates sharded locks, swappable eviction policies, TTL expiration, single-flight loading, worker queues, active expiration, write-through and write-back modes, structured stats, and deliberate unsafe examples.

The project is intentionally local and process-bound. It is not a Redis replacement, not a distributed cache, and not a network service. Its portfolio value comes from making cache internals visible and defensible.

---

## Decision Drivers

- Demonstrate real cache behavior: eviction, TTL, stats, and persistence trade-offs.
- Keep the core library dependency-free and testable.
- Support a required command-line interface.
- Preserve correctness under threads with per-shard atomic sections.
- Use deterministic time for tests and TTL demos.
- Show unsafe patterns separately so the safe design is justified.

---

## Options Considered

### Option A — Simple dictionary cache
Rejected because it would not show eviction metadata, TTL, single-flight, worker queues, write-back semantics, or concurrency trade-offs.

### Option B — Redis-backed cache
Rejected for the core build because it would hide important implementation details and add an external dependency/service.

### Option C — Sharded in-process cache
Accepted because it preserves visibility while introducing realistic contention and lifecycle concerns.

---

## Decisions

### Decision 1 — Use a `Cache` facade over deterministic shards

Each shard owns a backend, eviction policy, lock, single-flight registry, version marks, tombstones, pending flush counters, and stats. The facade routes by stable hash and orchestrates operations.

### Decision 2 — Split capacity across shards

`capacity` must be at least `shard_count`, so every shard can hold at least one entry. This avoids zero-capacity shards and makes behavior easier to explain.

### Decision 3 — Use a stable hash instead of Python `hash()`

Python hash randomization would make routing unstable across processes. CacheLab uses BLAKE2b over a canonical key form and collapses numeric equivalents such as `1`, `1.0`, and `True`.

### Decision 4 — Keep eviction policies pluggable

LRU, LFU, and FIFO share one policy contract: `on_get`, `on_put`, `on_delete`, `evict_candidate`, `clear`, `metadata_size`, and `__len__`.

### Decision 5 — Keep TTL separate from capacity eviction

TTL answers whether an entry is stale. Eviction answers which valid entry should be removed when capacity is exceeded. Lazy expiration happens during public reads and diagnostics; active expiration is scheduled through workers.

### Decision 6 — Use monotonic time

TTL uses an injectable `Clock` protocol. `MonotonicClock` is used normally; `FakeClock` powers deterministic tests and demos.

### Decision 7 — Preserve existing TTL on update when TTL is omitted

Omitting `ttl` updates the value but preserves the old expiry. Explicit `ttl=None` stores without expiration. Explicit positive TTL resets the expiry.

### Decision 8 — Implement single-flight loading

`get_or_compute` uses a per-shard `Flight` so concurrent misses for the same key share one loader execution. Loader exceptions propagate to waiters and do not store partial values.

### Decision 9 — Make workers message-based

Workers consume explicit dataclass messages: `ExpireShard`, `FlushWriteBack`, `PreloadKey`, `SnapshotStats`, and `StopWorker`. Unknown jobs are counted as failures rather than ignored.

### Decision 10 — Treat queue backpressure explicitly

Non-critical jobs can be dropped and counted when the queue is full. Critical write-back jobs block up to `queue_put_timeout` and raise `QueueBackpressureError` rather than disappearing silently.

### Decision 11 — Support cache-only, write-through, and write-back modes

Cache-only writes memory only. Write-through writes the source backend under the shard lock before returning. Write-back updates memory immediately, marks entries dirty, and persists later through worker jobs.

### Decision 12 — Protect write-back with versions and tombstones

Every key gets monotonically increasing versions. Stale put jobs are skipped if a newer write or delete has superseded them. Delete tombstones prevent old puts from resurrecting removed values.

### Decision 13 — Keep unsafe examples isolated

Unsafe demos show capacity overflow, duplicate loaders, write-back resurrection, and wall-clock TTL bugs. They are teaching tools and not part of the production cache path.

---

## Trade-offs Accepted

- The cache is process-local and cannot coordinate across workers or machines.
- CLI basic commands are one-shot processes; simulations and library usage are better for meaningful stats.
- Write-back is intentionally more complex than cache-only and write-through.
- The JSON CLI state file is plaintext and trusted input.
- Sharding splits capacity across sub-caches, so policy comparisons default to one shard.
- `get()` returning `None` is ambiguous unless a sentinel/default or `contains()`/`inspect()` is used.

---

## Consequences

The design provides a strong systems-capstone artifact: cache operations, eviction metadata, thread coordination, TTL, workers, queue pressure, write-back correctness, and structured stats are visible. The system remains honest about non-goals: it is not distributed, not networked, not encrypted, and not a production Redis substitute.

---

*Constitution reference: Article 1, Article 3.3, Article 4, Article 5, Article 6, and Article 7.*

---

# Technical Design Document
## App — Cache System
**Cache Infrastructure Group | Document 2 of 5**

---

## Overview

CacheLab is a Python package and CLI named `cachelab`. The central object is `Cache`, a thread-safe sharded cache with TTL, pluggable eviction policy, single-flight loading, worker-backed maintenance, and optional source-backend write modes.

**Package:** `cachelab`  
**Python:** `>=3.11`  
**Runtime dependencies:** none  
**CLI:** `cachelab`  
**Policies:** LRU, LFU, FIFO  
**Write modes:** cache-only, write-through, write-back  
**Coverage gate:** 99%

---

## System Architecture

```text
CLI / Library Caller
  │
  ▼
Cache facade
  ├── validate lifecycle and TTL
  ├── route key by stable_hash(key) % shard_count
  ├── acquire shard MeteredRLock
  ├── read/write InMemoryBackend
  ├── update eviction policy
  ├── update stats
  ├── coordinate single-flight loaders
  └── enqueue worker jobs
        ├── ExpireShard
        ├── FlushWriteBack
        ├── PreloadKey
        └── SnapshotStats
```

---

## Main Modules

```text
cachelab/
  core/cache.py          Cache facade and write-mode logic
  core/config.py         CacheConfig and TOML loading
  core/entry.py          CacheEntry and EntrySnapshot
  core/stats.py          Mutable and snapshot stats
  core/clock.py          MonotonicClock and FakeClock
  concurrency/hashing.py Stable shard routing
  concurrency/locks.py   MeteredRLock
  concurrency/shards.py  CacheShard and capacity split
  policies/base.py       EvictionPolicy protocol and factory
  policies/lru.py        OrderedDict LRU
  policies/lfu.py        O(1) LFU with recency tie-breaks
  policies/fifo.py       FIFO baseline
  storage/base.py        StorageBackend contract
  storage/memory.py      InMemoryBackend
  storage/slow_dict.py   Slow source backend for demos
  storage/write_modes.py WriteMode enum
  workers/messages.py    Worker message dataclasses
  workers/queue.py       Bounded queue and backpressure
  workers/worker_pool.py Worker lifecycle
  workers/scheduler.py   Active expiration scheduler
  workers/write_back_worker.py Stale-job logic and flush application
  cli/main.py            CLI dispatch
  cli/parser.py          CLI arguments
```

---

## Core Data Structures

### `CacheEntry`

Stores the live value and metadata:

```python
key: Hashable
value: Any
created_at: float
last_accessed_at: float
hit_count: int
expires_at: float | None
ttl: float | None
version: int
dirty: bool
```

It supports `is_expired(now)`, `touch(now)`, and `snapshot(now)`.

### `EntrySnapshot`

A frozen diagnostic view of an entry, including `ttl_remaining`, `version`, and `dirty`.

### `CacheConfig`

Defines capacity, TTL, policy, shard count, worker count, backend, write mode, queue size, retry behavior, shutdown behavior, and active expiration.

Validation rejects invalid capacity, zero shard count, `capacity < shard_count`, unsupported policy/backend/write mode, negative queue/worker counts, and invalid active-expiration timing.

### `CacheShard`

Each shard contains:

- index
- capacity
- backend
- eviction policy
- `MeteredRLock`
- mutable stats
- single-flight registry
- version marks
- tombstones
- pending flush counters

---

## Shard Routing

`stable_hash(key)` canonicalizes numeric equivalents and hashes the canonical representation with BLAKE2b. The shard is:

```text
stable_hash(key) % shard_count
```

This avoids dependence on Python’s randomized hash seed and keeps equal numeric keys aligned.

---

## Eviction Policies

### LRU

Uses `OrderedDict`. Reads and writes move keys to the recent end. The oldest key is evicted.

### LFU

Uses key-to-frequency and frequency-to-ordered-keys maps. Frequency changes and eviction are O(1). Ties inside one frequency bucket use recency.

### FIFO

Tracks insertion order only. Reads do not affect order. It is useful as a simulation baseline.

---

## Public Operation Flow

### `get`

```text
get(key, default)
  ├── route to shard
  ├── lock shard
  ├── if missing: count miss, return default
  ├── if expired: remove, count expiration + miss, return default
  ├── touch entry
  ├── policy.on_get(key)
  ├── count hit
  └── return value
```

### `put`

```text
put(key, value, ttl)
  ├── validate lifecycle and TTL
  ├── route to shard
  ├── lock shard
  ├── remove expired existing entry
  ├── write-through source update if configured
  ├── increment key version
  ├── clear tombstone
  ├── resolve TTL
  ├── store CacheEntry
  ├── policy.on_put(key)
  ├── enforce shard capacity
  ├── if write-back: mark dirty and create flush job
  └── enqueue flush job after releasing shard lock
```

### `delete`

In write-through mode, deletes the source backend under the shard lock. In write-back mode, records a tombstone and enqueues a delete flush job. The cache entry is removed and policy/single-flight metadata is cleaned.

### `get_or_compute`

Concurrent misses for the same key share one loader execution. The leader runs the loader outside the shard lock. Waiters block on the `Flight` event and receive either the result or the leader’s exception.

---

## TTL Semantics

- Omitted TTL uses default TTL for new entries.
- Omitted TTL preserves old expiry for updates.
- `ttl=None` explicitly disables expiry.
- Positive TTL sets expiry to `now + ttl`.
- Non-positive explicit TTL raises `ValidationError`.
- Lazy expiration occurs during reads/diagnostics.
- Active expiration enqueues `ExpireShard` jobs when workers are configured.

---

## Worker System

`CacheJobQueue` wraps `queue.Queue` and records dropped non-critical jobs. Critical jobs block for a timeout and fail loudly.

`WorkerPool` uses non-daemon threads, a stop event, and best-effort `StopWorker` messages. Shutdown does not rely solely on queue availability.

`ExpirationScheduler` periodically enqueues `ExpireShard` for each shard. Expiration jobs are non-critical because lazy expiration still preserves correctness.

---

## Write-back Semantics

Write-back creates `FlushWriteBack` jobs with key, value, version, operation, retries, and attempt count.

`is_stale_write_back` skips:

- put jobs superseded by newer writes or tombstones
- delete jobs superseded by newer writes
- unknown operations

`close(flush=True)` enqueues dirty jobs, waits for workers when possible, and then performs synchronous fallback flushing. It raises `ShutdownFlushError` if dirty entries remain.

---

## CLI State Model

Basic CLI commands read/write a JSON state file. Entries store remaining TTL and hit count. Aggregate hit/miss counters reset on reload. Legacy wall-clock expiry state is supported for backward compatibility.

`simulate` and `benchmark` run process-local workloads and are the correct surfaces for meaningful hit-ratio comparisons.

---

## Observability

Stats include hits, misses, hit ratio, puts, deletes, evictions, expirations, queue depth, dropped jobs, worker completions/failures, write-back retries, stale write-back skips, flush failures, shutdown flush failures, per-shard stats, policy metadata size, and lock contention.

---

## Known Limits

- Process-local only.
- No network service.
- No authentication/authorization.
- No encryption.
- JSON state file is plaintext and trusted input.
- Core backend support is memory only.
- Basic CLI commands do not run long-lived workers.
- Sharding splits capacity across sub-caches.

---

*Constitution reference: Article 4, Article 6, Article 7, and Article 8.*

---

# Interface Design Specification
## App — Cache System
**Cache Infrastructure Group | Document 3 of 5**

---

## Public Python Interface

### Imports

```python
from cachelab import Cache, CacheConfig, FakeClock, MonotonicClock
```

Also exported: `CacheEntry`, `EntrySnapshot`, `CacheStatsSnapshot`, `CacheLabError`, `ConfigurationError`, `ValidationError`, `QueueBackpressureError`, `ShutdownFlushError`, and `UnsupportedWriteModeError`.

---

## `Cache` Constructor

```python
Cache(
    *,
    config=None,
    capacity=128,
    default_ttl=None,
    policy="lru",
    shard_count=1,
    worker_count=0,
    scheduler_interval=1.0,
    queue_size=0,
    write_mode="cache-only",
    backend="memory",
    source_backend=None,
    clock=None,
    logger=None,
)
```

Rules:

- pass either `config=` or individual options, not both
- policies: `lru`, `lfu`, `fifo`
- write modes: `cache-only`, `write-through`, `write-back`
- backend: `memory`

---

## Core Methods

### `start() -> None`

Starts worker pool and scheduler when configured.

### `close(flush=None, timeout=None) -> None`

Stops scheduler/workers and flushes dirty write-back entries by default. Safe to call multiple times.

### `put(key, value, ttl=UNSET) -> None`

Stores a value. Explicit TTL must be positive. `ttl=None` means no expiry. Omitted TTL uses default TTL for new entries and preserves existing expiry on update.

### `get(key, default=None) -> Any`

Returns value or default. Counts hit/miss and applies lazy expiration.

### `contains(key) -> bool`

Checks whether a key is present and not expired. Counts hit/miss.

### `delete(key) -> bool`

Removes the key. In write-back mode, records tombstone and enqueues delete flush.

### `clear() -> None`

Clears all shards and policy metadata. In write-back mode, enqueues delete flush jobs.

### `size() -> int`

Returns live entry count.

### `inspect(key) -> EntrySnapshot | None`

Diagnostic read. It may lazily remove expired entries but does not count hit/miss.

### `dump(limit=None) -> list[EntrySnapshot]`

Returns snapshots for live entries.

### `stats() -> CacheStatsSnapshot`

Returns global and per-shard statistics.

### `get_or_compute(key, loader, ttl=UNSET) -> Any`

Single-flight loader. Concurrent misses for the same key share one loader execution.

### `expire_all() -> int`

Expires all currently stale entries.

### `preload(key, loader, ttl=UNSET) -> bool`

Queues a best-effort background preload. Requires `worker_count > 0`.

### `request_snapshot(request_id="") -> bool`

Queues a stats snapshot. Retrieve with `last_snapshot()`.

### `scheduler_tick() -> None`

Runs one scheduler tick for deterministic tests/demos.

---

## CLI Interface

```powershell
cachelab <command> [options]
```

Global options:

- `--version`
- `--capacity`
- `--policy lru|lfu|fifo`
- `--shards`
- `--default-ttl`
- `--state`
- `--config`

---

## Basic Commands

```powershell
cachelab put KEY VALUE [--ttl N] [--no-ttl] [--key-json] [--value-json]
cachelab get KEY [--key-json]
cachelab delete KEY [--key-json]
cachelab contains KEY [--key-json]
cachelab inspect KEY [--key-json]
cachelab dump [--limit N]
cachelab clear
cachelab stats
```

Basic commands persist to a JSON state file, default `.cachelab_state.json`.

---

## Simulation Commands

```powershell
cachelab simulate --policy lru --pattern looping --capacity 100 --requests 10000
cachelab benchmark --policies lru,lfu,fifo --pattern hotspot --requests 50000
```

Patterns:

- `uniform`
- `zipfian`
- `hotspot`
- `sequential`
- `looping`
- `mixed`

`--shards` defaults to `1` for pure policy comparisons.

---

## Demo Commands

```powershell
cachelab demo all
cachelab demo ttl-lazy
cachelab demo ttl-active
cachelab demo single-flight
cachelab demo sharding
cachelab demo worker-queue
cachelab demo backpressure
cachelab demo write-through-vs-write-back
cachelab demo write-back-retry
cachelab demo unsafe-race
cachelab demo unsafe-single-flight
cachelab demo unsafe-write-back-resurrection
cachelab demo wall-clock-ttl-bug
```

---

## Config File Interface

```toml
[cache]
capacity = 128
policy = "lru"
shard_count = 4
default_ttl = 60
worker_count = 2
write_mode = "cache-only"
active_expiration = true
```

Accepted aliases:

- `default TTL` → `default_ttl`
- `default_ttl_seconds` → `default_ttl`
- `shards` → `shard_count`
- `workers` → `worker_count`
- `queue_maxsize` → `queue_size`
- `retry_count` → `write_back_retry_count`
- `retry_delay` → `write_back_retry_delay`

Unknown keys raise `ConfigurationError`.

---

## Exit Codes

| Code | Meaning |
|---:|---|
| 0 | Success |
| 1 | Runtime error |
| 2 | Usage error from argparse |

---

## Side Effects

- Basic CLI commands read/write JSON state.
- `simulate` and `benchmark` run in-memory workloads.
- Write-through writes source backend synchronously.
- Write-back enqueues/flushes background jobs.
- Active expiration enqueues `ExpireShard` jobs.
- `close(flush=True)` flushes dirty entries.

---

*Constitution reference: Article 4, Article 6, and Article 8.*

---

# Runbook
## App — Cache System
**Cache Infrastructure Group | Document 4 of 5**

---

## Requirements

Runtime:

- Python 3.11+
- no required third-party dependencies

Development:

- pytest
- pytest-cov
- mypy
- ruff
- pre-commit

---

## Installation

```powershell
python -m pip install -r requirements-dev.txt
```

Runtime-only:

```powershell
python -m pip install -r requirements.txt
```

Editable package:

```powershell
python -m pip install -e .
```

---

## Smoke Test

```powershell
cachelab put user:1 Ada --ttl 30
cachelab get user:1
cachelab stats
```

Expected:

- put succeeds
- get returns `Ada`
- stats prints current process/state summary

---

## Common Operations

Store JSON:

```powershell
cachelab put user:1 '{"name":"Ada"}' --value-json
```

Use typed JSON key and value:

```powershell
cachelab put true 42 --key-json --value-json
```

Store without expiry despite default TTL:

```powershell
cachelab --default-ttl 60 put user:1 Ada --no-ttl
```

Inspect entry:

```powershell
cachelab inspect user:1
```

Dump entries:

```powershell
cachelab dump --limit 20
```

Clear state:

```powershell
cachelab clear
```

---

## Simulations and Benchmarks

```powershell
cachelab simulate --policy lru --pattern looping --capacity 100 --requests 10000
cachelab simulate --policy lfu --pattern hotspot --capacity 100 --requests 50000
cachelab benchmark --policies lru,lfu,fifo --pattern hotspot --requests 50000
```

Use simulation/benchmark output for exploration, not proof of correctness.

---

## Library Usage

```python
from cachelab import Cache

with Cache(capacity=100, policy="lfu", shard_count=4, worker_count=2, default_ttl=60) as cache:
    cache.put("session:1", {"user": "Ada"})
    value = cache.get_or_compute("profile:1", lambda: {"name": "Ada"})
    print(value)
    print(cache.stats())
```

Write-back:

```python
from cachelab import Cache

with Cache(capacity=100, write_mode="write-back", worker_count=2) as cache:
    cache.put("user:1", {"name": "Ada"})
```

---

## Config Use

```toml
[cache]
capacity = 128
policy = "lru"
shard_count = 4
default_ttl = 60
worker_count = 2
write_mode = "cache-only"
```

CLI:

```powershell
cachelab --config configs/default.toml put user:1 Ada
cachelab --config configs/default.toml stats
```

Library:

```python
from cachelab import Cache, CacheConfig

config = CacheConfig.from_file("configs/default.toml")
with Cache(config=config) as cache:
    cache.put("user:1", "Ada")
```

---

## Quality Checks

```powershell
python -m pytest
python -m pytest --cov=cachelab --cov-report=term-missing --cov-report=html
mypy src tests
ruff check src tests
pre-commit run --all-files
```

Coverage gate:

```text
99%
```

---

## CI Parity

GitHub Actions runs on Ubuntu and Windows with Python 3.11 and 3.12. The workflow installs dev dependencies, runs pre-commit, runs pytest with coverage, enforces `--cov-fail-under=99`, and reports test count on Ubuntu/Python 3.11.

---

## Troubleshooting

### `get` misses after `put`

Check:

- same state file path
- same key representation
- consistent `--key-json`
- TTL has not expired
- config mismatch did not shrink capacity and evict entries

### Stored `None` ambiguity

Use a sentinel default or `contains()` / `inspect()`.

### Config worker settings seem ignored in CLI

Basic CLI commands are one-shot processes. Worker settings such as `worker_count`, `write-back`, and active expiration are best exercised through the library API.

### Queue drops jobs

Increase `queue_size`, increase `worker_count`, or lower scheduler frequency. Non-critical jobs may drop; lazy expiration still preserves read correctness.

### Write-back shutdown fails

Increase `shutdown_timeout`, inspect `stats()`, check source backend failures, or use write-through for synchronous durability.

---

## Maintenance Notes

- Keep unsafe demos isolated.
- Preserve monotonic TTL semantics.
- Add tests before changing write-back stale detection.
- Add tests before changing stable hash canonicalization.
- Keep JSON state safe: never pickle/eval.
- Avoid distributed or network-service claims unless those features are implemented.
- Preserve CLI exit codes.

---

*Constitution reference: Article 6, Article 5, and Article 8.*

---

# Lessons Learned
## App — Cache System
**Cache Infrastructure Group | Document 5 of 5**

---

## Why This Design Was Chosen

This design was chosen because caching becomes interesting when time, concurrency, eviction, and persistence interact. A dictionary can store values, but it does not explain cache correctness. CacheLab shows the pieces that make a cache a system: shard locks, policy metadata, TTL, single-flight loaders, queue pressure, active maintenance, and write-back safety.

The `Cache` facade keeps the public API simple while the internal model stays realistic. Each shard owns its own lock, storage, policy, metadata, and stats. That makes unrelated-key operations less likely to block each other and keeps check-then-act operations atomic within a shard.

The unsafe demos make the architecture defendable. They show exactly what goes wrong when writes are not locked, loaders are not single-flight, write-back jobs are stale, or TTL depends on wall-clock time.

---

## What Was Intentionally Omitted

- Distributed cache behavior.
- Redis/Memcached backend.
- Network server mode.
- Authentication and authorization.
- Encryption.
- Asyncio API.
- Production-grade persistent state file.
- Cross-process stats.
- Advanced policies such as ARC, TinyLFU, or segmented LRU.

---

## Biggest Weakness

The biggest weakness is that the cache is process-local. It demonstrates strong local behavior, but cannot coordinate across multiple processes or machines. A production cache would need shared storage, distributed invalidation, durable metrics, replication strategy, and stronger operational tooling.

The second weakness is write-back complexity. Versions and tombstones make stale jobs safe, but deferred persistence always requires careful reasoning.

The third weakness is that basic CLI commands are one-shot. They are useful for persistence demos, but long-lived worker behavior is better demonstrated through the library API and demos.

---

## Scaling Considerations

If this grew into a bigger system, the next steps would be:

- add Redis or SQLite storage behind a stable backend interface
- define serialization and schema versioning
- add cross-process invalidation rules
- move stats into a shared collector
- add structured job latency metrics
- implement a stronger state-file writer with atomic replace and corruption recovery
- add more policy benchmarks

---

## Next Refactor

1. Add a shared storage backend interface for Redis/SQLite.
2. Add per-job metrics for queue latency and worker duration.
3. Add atomic state-file writing and schema migration.
4. Add structured benchmark report export.
5. Consider an `AsyncCache` wrapper as a separate facade, not mixed into the sync core.

---

## What This Project Taught

- Caches are concurrency systems, not just key-value maps.
- TTL and eviction are separate concerns.
- Eviction policy belongs behind a contract.
- Monotonic time is necessary for interval correctness.
- Single-flight prevents duplicated expensive work.
- Write-back needs versions and tombstones to prevent stale writes.
- Bounded queues make pressure visible.
- Unsafe demos are powerful proof that the safe design matters.

---

*Constitution v2.0 checklist: This document satisfies Article 5, Article 6, and Article 7 for Cache System.*
