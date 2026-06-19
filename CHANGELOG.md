# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Runnable examples in `examples/` (`basic_usage.py`, `write_back_demo.py`,
  `concurrent_load.py`).
- Recorded benchmark tables in `docs/benchmark_results.md`.
- Pre-commit hooks (`.pre-commit-config.yaml`) running ruff and mypy.
- Comprehensive test suite: 248 tests across unit, integration, concurrency,
  workers, CLI, and teaching modules; 99%+ line coverage on `cachelab` source
  (CI gate: 99%).

### Fixed
- `close(flush=True)` no longer fails spuriously when workers were never started.
- Job queue is always drained on `close()`, even if the worker pool never started.
- State reload warns when entries are evicted due to capacity mismatch.
- `ShutdownFlushError` reports how many dirty entries remain.
- Saved `default_ttl` is validated on state reload; CLI adds `--default-ttl`.
- Legacy `expires_wall` state files log a one-time migration note.
- `preload()` warns when the cache was never started.
- TTL validation raises `ValidationError` (consistent with other cache errors).
- Delete stats only count successful removals; `clear()` counts each removed key.
- Write-back shutdown sync flush clears pending-flush metadata and skips stale jobs.
- Closed caches reject mutating public API calls; `close()` sets a `CLOSING` state
  so concurrent puts are blocked during shutdown flush.
- Failed shutdown flush clears pending-flush counters (entries may remain dirty).
- CLI state persistence preserves key types, config, `hit_count`, and `ttl_remaining`.
- CLI `get` uses a single read with a miss sentinel (no double hit counting).
- Config constructor rejects conflicting `config=` plus individual parameters.
- `scheduler_tick()` blocked after close; `stats()` remains available for post-mortem reads.
- Write-back warns when workers are configured but `start()` was never called.

### Changed
- **Breaking:** `Cache(...)` is keyword-only; use `Cache(capacity=128)` instead of
  `Cache(128)`.
- Author metadata (Princeton Afeez), LICENSE copyright, and README author line.
- CI runs pre-commit, pytest with coverage (`--cov-fail-under=99`), on Ubuntu and
  Windows with Python 3.11 and 3.12.
- CLI state file v2 adds a persisted `config` block and `hit_count` per entry.
- CLI adds `--key-json`, `--value-json`, and documents that plain keys/values are strings.
- HTML coverage output configured in `pyproject.toml` (`htmlcov/`).

## [0.1.0] - 2026-06-16

Initial release.

### Added
- Eviction policies behind a shared interface: O(1) LRU, O(1) LFU (frequency
  buckets with recency tie-breaking), and FIFO.
- TTL expiration on a monotonic injectable clock: default and per-key TTL, lazy
  expiration on access, and active expiration via a background scheduler.
- Sharded, thread-safe `Cache` with per-shard locks, deterministic key routing,
  and single-flight `get_or_compute`.
- Background workers and a bounded job queue with explicit message types
  (`ExpireShard`, `FlushWriteBack`, `PreloadKey`, `SnapshotStats`, `StopWorker`),
  graceful shutdown, and backpressure handling.
- Storage write modes: `cache-only`, `write-through`, and `write-back` with
  per-key versions, delete tombstones (bounded/pruned), retry, and shutdown flush.
- Observability: immutable stats snapshots (cache/shard/policy) and structured
  logging.
- CLI (`cachelab`): basic key commands, `simulate`, `benchmark`, and `demo`
  (including deliberate-failure teaching demos), plus `--version` and `--config`.
- Declarative TOML configuration with validation.
- Test suite (unit/integration/concurrency/workers/cli/teaching) and a
  `mypy --strict`-clean, fully type-hinted, dependency-free runtime.

[Unreleased]: compare/v0.1.0...HEAD
[0.1.0]: releases/tag/v0.1.0
