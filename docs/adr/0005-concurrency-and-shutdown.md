# ADR 0005: Concurrency, backpressure, and shutdown model

- **Status:** Accepted
- **Date:** 2026-06-19

## Context

CacheLab coordinates multiple concurrent actors:

- client threads calling `get`, `put`, `get_or_compute`, and related APIs;
- per-shard `MeteredRLock` instances guarding check-then-act sequences;
- a scheduler thread enqueueing expiration work;
- worker threads draining a bounded job queue;
- optional write-through or write-back interaction with a slow source backend;
- `close()` joining scheduler and worker threads within configured timeouts.

Cache operations must remain thread-safe. Background workers must not make
shutdown unreliable when queues are saturated. Bounded queues can fill under load.
Write-back flushes must not disappear silently. The design must explicitly
acknowledge where **deadlock** and **starvation** risks exist and which trade-offs
mitigate them.

## Decision

### Per-shard locks instead of one global lock

Each `CacheShard` owns a re-entrant `MeteredRLock`. Unrelated keys usually route to
different shards, so concurrent operations on different keys rarely contend on the
same lock. All mutations that must stay atomic — backend updates, policy metadata,
stats, single-flight registration, version marks — run under the owning shard lock.

There is **no lock ordering across shards**: operations never acquire more than one
shard lock at a time, which avoids classic multi-shard deadlock cycles.

### Single-flight events for duplicate concurrent loads

`get_or_compute` registers a per-shard `Flight` (a `threading.Event`) under the
shard lock, then **releases the lock** before running the loader. Waiters block on
`flight.event.wait()` without holding the shard lock. The leader publishes the
result or exception before waking waiters.

This collapses duplicate loader work for the same key while keeping slow I/O off the
critical section.

### Stop event plus best-effort `StopWorker` messages

Worker shutdown sets a `_stop_event` on the pool **before** relying on the queue.
Idle workers poll `queue.get(timeout=0.25)`; when the queue is empty and the stop
event is set, they exit. `StopWorker` sentinels are offered with `put_nowait` as a
best-effort wake-up when the queue has capacity — they are **not** the sole shutdown
mechanism.

This guarantees workers exit even when a bounded queue is full and sentinels cannot
be enqueued.

### Non-critical expiration jobs are droppable

`ExpireShard`, `PreloadKey`, and `SnapshotStats` use non-blocking enqueue. A full
queue increments `queue_dropped` and discards the job. Correctness does not depend
on these jobs completing promptly because lazy expiration on the request path remains
authoritative.

### Write-back jobs are critical

`FlushWriteBack` uses blocking enqueue with `queue_put_timeout`. Failure raises
`QueueBackpressureError` and releases the key's pending-flush count so version
metadata stays prunable. The in-memory cache update has already committed; callers
see explicit backpressure rather than silent data loss.

### Synchronous shutdown flush as a backstop

`close(flush=True)` in write-back mode:

1. enqueues dirty entries;
2. waits for the job queue to drain (`join_until`) within `shutdown_timeout`;
3. performs a synchronous best-effort flush of anything still dirty;
4. stops workers and the scheduler via bounded `join_all`;
5. raises `ShutdownFlushError` if dirty entries remain.

Shutdown favors **reported failure** over pretending all durable writes succeeded.

## Deadlock and starvation risks acknowledged

The following risks are **accepted and mitigated**, not ignored:

| Risk | Description | Mitigation |
|------|-------------|------------|
| **Shard serialization on slow write-through** | Write-through holds the shard lock across `source_backend` I/O, blocking all other operations on that shard until the write completes. | Documented trade-off; use write-back when source latency must not block readers. Not a deadlock — intentional serialization. |
| **Loader starvation on hot keys** | Many threads waiting on one `Flight` block until the leader finishes; other keys on the same shard can proceed once the lock is released. | Single-flight is per-key; loader runs outside the lock so unrelated keys on the shard are not blocked during I/O. |
| **Bounded queue backpressure** | Under sustained load, non-critical jobs are dropped and critical flushes may block or raise. | Expiration is best-effort; lazy TTL keeps reads correct. Write-back raises `QueueBackpressureError` instead of dropping. |
| **Active expiration delay** | Dropped or delayed `ExpireShard` jobs defer memory reclamation for cold stale keys. | Lazy expiration on access remains correct; `expire_all()` offers a synchronous fallback. |
| **Shutdown join timeouts** | `join_all` and `join_until` use bounded waits (`shutdown_timeout`, default 5s). Surviving threads after timeout indicate incomplete shutdown. | Stop event ensures workers eventually exit their loops; `close()` is idempotent. `ShutdownFlushError` surfaces incomplete durable flush. |
| **Write-back queue vs. request path** | A saturated queue does not block caching the loaded value in `get_or_compute`; only the background flush is deferred. | Value is published to waiters; dirty entry persists for `close(flush=True)`. |
| **No cross-shard deadlock** | The design never nests shard locks or waits for another shard while holding a lock. | Single-shard lock scope per operation; workers acquire shard locks one shard at a time per job. |

There is **no global lock** that could invert with shard locks or worker handlers.
Worker handlers acquire a shard lock, perform bounded work, and release — they do not
call back into user code while holding the lock.

## Consequences

### Positive

- Request paths stay **correct under concurrency**: check-then-act sequences are atomic
  per shard; single-flight prevents duplicate loader storms.
- **Shutdown is deterministic** in the sense that stop events and bounded joins give
  a defined protocol; saturated queues cannot strand workers indefinitely.
- **Maintenance delay is acceptable**: dropped expiration jobs do not violate TTL
  semantics visible to callers.
- **Write-back favors explicit failure** over silent loss of durable work.

### Negative

- Write-through mode can **starve a shard** during slow backend writes — by design.
- Under extreme load, **background maintenance lags** (expiration, preload, snapshots).
- **Shutdown may time out** on pathological workloads; callers must handle
  `ShutdownFlushError` and inspect `shutdown_flush_failures` in stats.
- Operators must tune `queue_size`, `queue_put_timeout`, and `shutdown_timeout` for
  their workload.

## Alternatives considered

| Alternative | Why not chosen |
|-------------|----------------|
| Global lock | Eliminates shard-level races simply but serializes all keys. |
| Release lock during write-through | Would allow concurrent readers to observe cache/source divergence mid-write. |
| Queue-only shutdown (sentinels required) | Fails when the bounded queue is full; workers may never exit. |
| Block forever on critical enqueue | Could deadlock shutdown if workers are stuck; bounded timeout surfaces failure. |
| Drop write-back jobs when queue is full | Silent durable data loss; violates explicit-failure requirement. |

## References

- [`README.md`](../../README.md) — Concurrency, Queue and workers sections
- [`docs/concurrency.md`](../concurrency.md) — sharding and single-flight overview
- [`docs/workers.md`](../workers.md) — shutdown and backpressure behavior
- [`docs/adr/0001-cache-architecture.md`](0001-cache-architecture.md) — sharded lock model
- [`docs/adr/0003-worker-queue-and-write-back.md`](0003-worker-queue-and-write-back.md) — job priorities and versioning
- [`src/cachelab/core/cache.py`](../../src/cachelab/core/cache.py) — `get_or_compute`, `close`, write-through lock scope
- [`src/cachelab/workers/worker_pool.py`](../../src/cachelab/workers/worker_pool.py) — stop event shutdown loop
