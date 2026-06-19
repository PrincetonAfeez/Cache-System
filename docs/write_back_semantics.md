# Write-Back Semantics

Write-back mode keeps request latency low by storing cache mutations first and
persisting later. Correctness depends on versions:

- every put/delete increments the key version;
- put flush jobs are skipped when their version is no longer current;
- delete jobs are skipped when a newer put has replaced the tombstone;
- tombstones keep stale put jobs from resurrecting deleted values.

## Bounded metadata

Version marks and tombstones only exist to police in-flight flushes, so they
must not grow forever. Each shard counts the flush jobs still pending for a key;
once that count returns to zero and no live entry remains, the key's version
mark and tombstone are pruned. In `cache-only` and `write-through` modes no
flush jobs exist, so this metadata is dropped the moment a key is removed. The
maps are therefore bounded by the live key set plus keys with outstanding
flushes, never by total history. The pending count is also released when a flush
job is *rejected* under backpressure (a full bounded queue) or when a retry can
no longer be rescheduled, so the bound holds even on the failure paths.

## Shutdown flush

`close(flush=True)` enqueues and synchronously attempts final dirty flushes. If
dirty entries cannot be persisted before timeout or retry exhaustion, stats are
updated (`shutdown_flush_failures`) and `ShutdownFlushError` is raised.
