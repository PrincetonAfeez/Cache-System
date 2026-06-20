# ADR 0003: Worker queue and write-back — explicit jobs, backpressure, and versioning

- **Status:** Accepted
- **Date:** 2026-06-19

## Context

CacheLab offloads maintenance work (TTL cleanup, write-back persistence, cache warming,
stat snapshots) from the request path. The library must:

- keep request latency predictable under load;
- distinguish durable work from best-effort maintenance;
- support bounded queues that demonstrate real backpressure behavior;
- guarantee correct write-back semantics when puts, deletes, and flushes race;
- shut down deterministically even when the queue is saturated.

## Decision

### Explicit dataclass worker messages

Workers consume a closed union of frozen dataclass jobs:

- `ExpireShard` — scan one shard for expired keys;
- `FlushWriteBack` — persist a put or delete to the source backend;
- `PreloadKey` — warm the cache on a background thread;
- `SnapshotStats` — capture aggregate stats asynchronously;
- `StopWorker` — best-effort shutdown sentinel.

Message passing replaces ad-hoc callbacks or shared mutable task queues. Each job type
has a known producer, payload shape, and handling path. Unrecognized jobs count as worker
failures rather than being silently dropped.

### Non-critical expiration jobs are droppable

`ExpireShard` (and other best-effort jobs such as `PreloadKey` and `SnapshotStats`) use
`put_nowait` on a bounded queue. When the queue is full, the job is dropped and
`queue_dropped` is incremented. Expiration is eventually consistent: lazy expiration on
the request path remains authoritative, and the next scheduler tick can retry.

This models a common production trade-off: shedding low-priority background work under
pressure instead of blocking callers or unboundedly growing memory.

### Write-back jobs are critical

`FlushWriteBack` jobs use blocking `put` with a configured timeout. If the queue cannot
accept the job within that window, `QueueBackpressureError` is raised and the pending-flush
count for the key is released so version metadata stays prunable.

Critical jobs must not disappear silently; durable persistence is either queued or the
caller is notified. On `close(flush=True)`, remaining dirty entries are flushed
synchronously with retry limits; failures surface as `ShutdownFlushError`.

### Write-back uses monotonic versions and delete tombstones

Every put or delete increments a per-key version on its shard. Each `FlushWriteBack` job
carries the version it was enqueued with. Before applying a flush, workers call
`is_stale_write_back`:

- a **put** flush is skipped if a newer write exists or a tombstone supersedes it;
- a **delete** flush is skipped if a newer put replaced the tombstone.

Tombstones record the version at delete time so a slow in-flight put cannot resurrect a
removed value. Version marks and tombstones are pruned once no pending flushes reference
the key and no live entry remains, keeping metadata bounded.

### Shutdown is driven by a stop event, not the queue

Worker pool shutdown sets a stop `Event` so every worker exits even when the bounded
queue is full and `StopWorker` sentinels cannot be enqueued. `close()` is idempotent
and joins all worker and scheduler threads.

## Consequences

### Positive

- **Request-path isolation:** expiration and write-back I/O do not block cache reads
  except when critical enqueue backpressure propagates to the writer.
- **Observable backpressure:** queue depth, dropped jobs, retries, and stale skips are
  counted in stats.
- **Race-safe write-back:** versions and tombstones prevent resurrection and stale
  overwrites without locking the slow backend on every request.
- **Deterministic shutdown:** stop events guarantee thread join even under saturation.

### Negative

- **Queue tuning matters:** too-small queues increase drops (expiration) or backpressure
  errors (write-back).
- **Write-back complexity:** version/tombstone bookkeeping adds per-shard state beyond
  simple cache-only mode.
- **Eventual persistence:** write-back returns before the source backend is updated;
  callers must accept brief inconsistency windows.

## Alternatives considered

| Alternative | Why not chosen |
|-------------|----------------|
| Synchronous flush on every write | Defeats write-back latency benefits; slow backends block callers. |
| Single undifferentiated queue | Cannot prioritize durable flushes over droppable expiration work. |
| Last-write-wins without versions | Stale async puts can overwrite newer deletes (see `unsafe-write-back-resurrection` demo). |
| Shutdown via queue sentinels only | Fails when the bounded queue is full; workers may never exit. |

## References

- [`README.md`](../../README.md) — Queue and workers, write modes
- [`docs/workers.md`](../workers.md) — worker behavior and shutdown
- [`docs/write_back_semantics.md`](../write_back_semantics.md) — version and tombstone rules
- [`src/cachelab/workers/messages.py`](../../src/cachelab/workers/messages.py) — job dataclasses
- [`src/cachelab/workers/queue.py`](../../src/cachelab/workers/queue.py) — critical vs non-critical enqueue
- [`src/cachelab/workers/write_back_worker.py`](../../src/cachelab/workers/write_back_worker.py) — stale detection
