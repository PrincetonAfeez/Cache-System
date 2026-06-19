# Workers

The scheduler periodically enqueues `ExpireShard` jobs. Workers block on
`queue.Queue.get()` with a short idle timeout: an enqueued job wakes a worker
immediately, and the timeout only bounds how long a fully idle worker waits
before re-checking the shutdown signal (so this is a blocking wait, not a busy
spin).

Non-critical jobs use `put_nowait`; full queues count dropped work in
`queue_dropped`. Critical write-back jobs block up to `queue_put_timeout` and
raise `QueueBackpressureError` if they cannot be accepted, so durable work is
never silently lost. When a critical enqueue is rejected, the key's pending-flush
count is released so its version mark/tombstone stays prunable. An unrecognized
job type is counted as a worker failure rather than silently consumed.

All five job types have producers: the scheduler emits `ExpireShard`; writes emit
`FlushWriteBack`; `cache.preload(key, loader)` emits `PreloadKey` (best-effort
cache warming on a worker); and `cache.request_snapshot()` emits `SnapshotStats`,
whose result is exposed via `cache.last_snapshot()`.

## Shutdown

`close()` stops the scheduler, then stops the worker pool. Worker shutdown is
driven by a stop `Event`, not by the queue: setting the event guarantees every
worker exits even if a bounded queue is still full and a `StopWorker` sentinel
cannot be enqueued. The sentinels are still offered as a best-effort nudge so
idle workers wake promptly instead of waiting out the idle timeout. `close()` is
idempotent and joins every thread, leaving none alive.

In write-back mode, `close(flush=True)` first drains pending flush jobs through
the workers and then performs a synchronous best-effort flush of anything still
dirty. If entries cannot be persisted within the retry budget, the failure is
recorded in `shutdown_flush_failures` and surfaced as `ShutdownFlushError`.
