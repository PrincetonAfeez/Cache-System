# ADR 0004: CLI state file format — plaintext JSON with monotonic TTL remaining

- **Status:** Accepted
- **Date:** 2026-06-19

## Context

The CacheLab CLI is **stateless between invocations**: each `put`, `get`, or `stats`
command starts a fresh process, performs work, and exits. To persist cache contents across
CLI runs, commands read and write a local state file (default path configurable via
`--state-file`).

The format must be:

- human-readable and easy to inspect or hand-edit for demos;
- safe to parse (no arbitrary code execution);
- stable enough for backward-compatible upgrades;
- consistent with the library's monotonic TTL semantics where possible.

## Decision

### Plaintext JSON state file

State is stored as indented, sorted-key JSON written atomically (temp file + `fsync` +
`os.replace`). A companion `.lock` file provides best-effort exclusive access across
concurrent CLI processes, with stale-lock recovery after crashes.

JSON is parsed with the standard library `json` module — never `pickle` or `eval` — so
malformed files fail cleanly without code execution. Keys and values are plaintext in
memory and on disk; this matches CacheLab's in-process, single-user threat model.

### Save `ttl_remaining`, not absolute wall-clock expiry

Each entry snapshot stores:

```json
{
  "key": "...",
  "value": "...",
  "ttl_remaining": 28.5,
  "hit_count": 3
}
```

`ttl_remaining` is computed from the cache's monotonic clock at save time
(`expires_at - now`). On load, entries are re-inserted with that remaining duration
anchored to the new process's monotonic clock. Entries with `ttl_remaining: null` have
no expiry; omitted `ttl` on `put` uses the configured default TTL.

This aligns CLI persistence with the library's TTL model (ADR 0002) instead of baking in
wall-clock absolute timestamps that break under clock adjustment.

### Top-level structure: config + entries

The state file contains:

- **`config`** — `capacity`, `policy`, `shard_count`, `default_ttl` active when saved;
- **`entries`** — list of entry records as above.

Aggregate hit/miss counters reset on each CLI reload; only per-entry `hit_count` is
restored. A warning is printed when reloaded config differs from the active CLI settings
or when entries are evicted because saved capacity shrank.

Basic CLI commands default to `--shards 1` and do not start worker pools; worker-dependent
settings (`worker_count`, `write_mode = "write-back"`, `active_expiration`) have no effect
on one-shot CLI commands. The state file therefore captures cache contents and sizing
policy, not runtime worker configuration.

### Backward compatibility for legacy `expires_wall`

Older state files stored per-entry `expires_wall` (absolute Unix timestamp). Loaders still
accept this field: remaining TTL is computed as `expires_wall - time.time()` at load time.
A one-time note is printed encouraging re-save to migrate to `ttl_remaining`.

Legacy entries with non-positive remaining TTL or invalid fields are skipped silently.
Re-saving writes the modern format only.

## Consequences

### Positive

- **Inspectable and portable:** JSON is readable in any editor and diff-friendly in reviews.
- **Safe parsing:** no deserialization gadgets beyond JSON literals.
- **Monotonic-aligned TTL:** reloaded entries behave like continuations of the prior
  session rather than depending on wall-clock absolutes.
- **Graceful migration:** existing `expires_wall` files keep working with a clear upgrade path.

### Negative

- **No encryption or auth:** the state file is trusted local input, not a secure store.
- **Aggregate stats not persisted:** CLI `stats` hit ratio reflects the current process only.
- **Legacy wall-clock load path:** `expires_wall` remains subject to clock skew until migrated.
- **Plaintext secrets:** callers must not store sensitive values expecting protection.

## Alternatives considered

| Alternative | Why not chosen |
|-------------|----------------|
| Binary pickle persistence | Unsafe on untrusted files; opaque on disk. |
| Absolute `expires_wall` as primary format | Wall-clock jumps break TTL; contradicts monotonic library design. |
| SQLite or embedded DB | Heavier dependency and tooling for a teaching CLI. |
| In-process-only CLI (no persistence) | Poor demo UX; every command would start from an empty cache. |

## References

- [`README.md`](../../README.md) — Configuration and CLI state file behavior
- [`src/cachelab/cli/commands/basic.py`](../../src/cachelab/cli/commands/basic.py) — load/save and legacy migration
- [`src/cachelab/storage/serialization.py`](../../src/cachelab/storage/serialization.py) — atomic JSON I/O and file lock
- [`docs/adr/0002-ttl-expiration-model.md`](0002-ttl-expiration-model.md) — monotonic TTL rationale
