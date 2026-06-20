# ADR 0002: TTL expiration model — monotonic clock, lazy checks, and active workers

- **Status:** Accepted
- **Date:** 2026-06-19

## Context

CacheLab must support time-to-live (TTL) expiration alongside capacity-based eviction.
TTL correctness must be testable without real-time sleeps, resilient to wall-clock
adjustments, and efficient on the request path. Stale entries that are never read again
should not occupy memory indefinitely.

TTL is separate from eviction policy: a key can expire due to time even when the cache
is under capacity, and capacity eviction can remove a key before its TTL elapses.

## Decision

### Injected monotonic clock

All TTL calculations use an injected `Clock` protocol backed by `time.monotonic()` in
production and `FakeClock` in tests. Entries store `expires_at` as a monotonic timestamp;
`snapshot()` derives `ttl_remaining` as `max(0, expires_at - now)`.

Wall-clock time (`time.time()`) is **not** used for TTL correctness in the library API.

### Lazy expiration on every public touch

Public read/write paths (`get`, `contains`, `get_or_compute`, `put`, etc.) check
`CacheEntry.is_expired(now)` under the shard lock and remove stale entries before
returning. This keeps the hot path simple and guarantees that callers never observe
expired values.

Lazy expiration alone is **always** enabled; there is no mode that skips it.

### Active expiration via scheduled worker jobs

When `active_expiration` is enabled, an `ExpirationScheduler` periodically enqueues
`ExpireShard` jobs for workers. Workers scan the shard backend and remove expired keys
without waiting for a client access. This reclaims memory for cold keys that lazy
expiration would never touch.

Active expiration is **best-effort maintenance**, not a correctness requirement: lazy
checks remain authoritative for what callers see.

### Wall-clock timestamps as legacy CLI state only

Early CLI state files stored absolute `expires_wall` timestamps. Current saves use
`ttl_remaining` derived from the cache's monotonic clock at save time. Loaders accept
both formats: `ttl_remaining` is preferred; `expires_wall` is converted using wall clock
with a one-time migration note printed to stderr.

## Consequences

### Positive

- **Deterministic tests:** `FakeClock.advance()` replaces `sleep()` in correctness tests.
- **Immune to clock skew:** NTP adjustments and daylight-saving changes do not shorten
  or extend entry lifetimes in the library.
- **Low request-path cost:** lazy checks are a single comparison per touched entry.
- **Memory reclamation:** active expiration removes cold stale entries between accesses.

### Negative

- **Dual expiration paths:** lazy and active expiration must agree on the same
  `expires_at` semantics; both depend on the injected clock.
- **CLI persistence nuance:** saving `ttl_remaining` and reloading in a new process
  re-anchors expiry to that process's monotonic clock, which is correct for CLI
  session continuity but differs from wall-clock absolute expiry.
- **Legacy migration:** old `expires_wall` files remain loadable but are less robust
  to wall-clock jumps; users are prompted to re-save.

## Alternatives considered

| Alternative | Why not chosen |
|-------------|----------------|
| Wall-clock `expires_at` everywhere | Vulnerable to system clock changes; hard to test without real delays. |
| Lazy expiration only | Stale cold entries linger until capacity pressure or process exit. |
| Active expiration only | Would require workers on every read path or allow stale reads. |
| Absolute wall-clock in CLI state | Same skew problems the library deliberately avoids; replaced by `ttl_remaining`. |

## References

- [`README.md`](../../README.md) — TTL section
- [`src/cachelab/core/clock.py`](../../src/cachelab/core/clock.py) — `Clock`, `MonotonicClock`, `FakeClock`
- [`src/cachelab/core/entry.py`](../../src/cachelab/core/entry.py) — `is_expired`, `ttl_remaining`
- [`src/cachelab/workers/scheduler.py`](../../src/cachelab/workers/scheduler.py) — `ExpirationScheduler`
- [`src/cachelab/teaching/unsafe_wall_clock_ttl.py`](../../src/cachelab/teaching/unsafe_wall_clock_ttl.py) — teaching demo
