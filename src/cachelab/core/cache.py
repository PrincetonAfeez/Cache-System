""" Cache implementation for CacheLab """

from __future__ import annotations

import enum
import logging
import threading
from dataclasses import dataclass, replace
from typing import Any, Callable, Hashable, Iterable, cast

from cachelab.concurrency.hashing import stable_hash
from cachelab.concurrency.shards import CacheShard, shard_capacities
from cachelab.concurrency.singleflight import Flight
from cachelab.core.clock import Clock, MonotonicClock
from cachelab.core.config import CacheConfig
from cachelab.core.entry import CacheEntry, EntrySnapshot
from cachelab.core.exceptions import (
    ConfigurationError,
    QueueBackpressureError,
    ShutdownFlushError,
    UnsupportedWriteModeError,
    ValidationError,
)
from cachelab.core.lifecycle import LifecycleState
from cachelab.core.stats import CacheStatsSnapshot, PolicyStatsSnapshot, ShardStatsSnapshot
from cachelab.observability.logging import get_logger, log_event
from cachelab.policies.base import make_policy
from cachelab.storage.base import StorageBackend
from cachelab.storage.memory import InMemoryBackend
from cachelab.storage.slow_dict import SlowDictBackend
from cachelab.storage.write_modes import WriteMode
from cachelab.workers.expiration_worker import expired_keys
from cachelab.workers.messages import ExpireShard, FlushWriteBack, Job, PreloadKey, SnapshotStats
from cachelab.workers.queue import CacheJobQueue
from cachelab.workers.scheduler import ExpirationScheduler
from cachelab.workers.worker_pool import WorkerPool
from cachelab.workers.write_back_worker import apply_write_back, is_stale_write_back


class _Missing(enum.Enum):
    """Typed sentinel for 'ttl not supplied' so mypy still narrows real values."""

    UNSET = enum.auto()


_TTL_UNSET = _Missing.UNSET
_CONFIG_UNSET = object()


def _make_backend(name: str) -> StorageBackend:
    if name == "memory":
        return InMemoryBackend()
    raise ConfigurationError(f"unsupported backend: {name}")


@dataclass(slots=True)
class _RuntimeStats:
    worker_jobs_completed: int = 0
    worker_jobs_failed: int = 0
    write_back_retries: int = 0
    stale_write_back_jobs_skipped: int = 0
    flush_failures: int = 0
    shutdown_flush_failures: int = 0


class Cache:
    """Thread-safe sharded cache with TTL, single-flight, and workers."""

    def __init__(
        self,
        *,
        config: CacheConfig | None = None,
        capacity: int | object = _CONFIG_UNSET,
        default_ttl: float | None | object = _CONFIG_UNSET,
        policy: str | object = _CONFIG_UNSET,
        shard_count: int | object = _CONFIG_UNSET,
        worker_count: int | object = _CONFIG_UNSET,
        scheduler_interval: float | object = _CONFIG_UNSET,
        queue_size: int | object = _CONFIG_UNSET,
        write_mode: str | object = _CONFIG_UNSET,
        backend: str | object = _CONFIG_UNSET,
        source_backend: SlowDictBackend | None = None,
        clock: Clock | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if config is not None:
            conflicting = [
                name
                for name, value in (
                    ("capacity", capacity),
                    ("default_ttl", default_ttl),
                    ("policy", policy),
                    ("shard_count", shard_count),
                    ("worker_count", worker_count),
                    ("scheduler_interval", scheduler_interval),
                    ("queue_size", queue_size),
                    ("write_mode", write_mode),
                    ("backend", backend),
                )
                if value is not _CONFIG_UNSET
            ]
            if conflicting:
                joined = ", ".join(conflicting)
                raise ConfigurationError(
                    f"when config= is provided, do not also pass: {joined}"
                )
            self.config = config
        else:
            self.config = CacheConfig(
                capacity=128 if capacity is _CONFIG_UNSET else cast(int, capacity),
                default_ttl=None
                if default_ttl is _CONFIG_UNSET
                else cast(float | None, default_ttl),
                policy="lru" if policy is _CONFIG_UNSET else cast(str, policy),
                shard_count=1 if shard_count is _CONFIG_UNSET else cast(int, shard_count),
                worker_count=0 if worker_count is _CONFIG_UNSET else cast(int, worker_count),
                scheduler_interval=1.0
                if scheduler_interval is _CONFIG_UNSET
                else cast(float, scheduler_interval),
                queue_size=0 if queue_size is _CONFIG_UNSET else cast(int, queue_size),
                write_mode=WriteMode.CACHE_ONLY.value
                if write_mode is _CONFIG_UNSET
                else cast(str, write_mode),
                backend="memory" if backend is _CONFIG_UNSET else cast(str, backend),
            )
        self.clock = clock or MonotonicClock()
        self.logger = logger or get_logger()
        self.write_mode = self._parse_write_mode(self.config.write_mode)
        # The source backend keeps its own clock: its artificial I/O delay must
        # not advance the cache's TTL clock (which would expire entries from
        # inside a backend write).
        self.source_backend = source_backend or SlowDictBackend()
        capacities = shard_capacities(self.config.capacity, self.config.shard_count)
        self._shards = tuple(
            CacheShard(
                index=index,
                capacity=shard_capacity,
                backend=_make_backend(self.config.backend),
                policy=make_policy(self.config.policy),
            )
            for index, shard_capacity in enumerate(capacities)
        )
        self.job_queue = CacheJobQueue(maxsize=self.config.queue_size)
        self._runtime = _RuntimeStats()
        self._runtime_lock = threading.Lock()
        self._last_snapshot: CacheStatsSnapshot | None = None
        self._lifecycle_lock = threading.RLock()
        self._state = LifecycleState.CREATED
        self._cache_not_started_warned = False
        self._worker_pool = WorkerPool(
            "cachelab-worker",
            self.config.worker_count,
            self.job_queue,
            self._handle_job,
            self._record_worker_failure,
            self.logger,
        )
        self._scheduler = ExpirationScheduler(
            self.config.scheduler_interval,
            len(self._shards),
            self.job_queue,
            self.clock,
            self.logger,
        )

    def __enter__(self) -> "Cache":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._state == LifecycleState.STARTED:
                return
            if self._state in (LifecycleState.CLOSED, LifecycleState.CLOSING):
                raise RuntimeError("cannot restart a closed cache")
            self._worker_pool.start()
            if (
                self.config.active_expiration
                and self.config.worker_count > 0
                and self.config.scheduler_interval > 0
            ):
                self._scheduler.start()
            elif self.config.active_expiration and self.config.worker_count == 0:
                # Active expiration needs workers to consume ExpireShard jobs;
                # with none configured only lazy expiration runs. Surface it
                # rather than silently doing nothing.
                self.logger.warning(
                    "cachelab_event active_expiration_inactive reason=no_workers"
                )
            if self.write_mode == WriteMode.WRITE_BACK and self.config.worker_count == 0:
                self.logger.warning(
                    "cachelab_event write_back_inactive reason=no_workers "
                    "note=flush_jobs_queue_until_close"
                )
                self._cache_not_started_warned = True
            self._state = LifecycleState.STARTED

    def close(self, *, flush: bool | None = None, timeout: float | None = None) -> None:
        flush = self.config.shutdown_flush if flush is None else flush
        timeout = self.config.shutdown_timeout if timeout is None else timeout
        with self._lifecycle_lock:
            if self._state == LifecycleState.CLOSED:
                return
            self._state = LifecycleState.CLOSING
            self._scheduler.stop(timeout=timeout)
            flush_failed = False
            if flush and self.write_mode == WriteMode.WRITE_BACK:
                self._enqueue_dirty_write_back_jobs()
                workers_started = self._worker_pool.started
                if workers_started and self.config.worker_count > 0:
                    flush_failed = not self.job_queue.join_until(timeout)
                flush_failed = self._flush_dirty_entries_sync() or flush_failed
                if flush_failed:
                    self._inc_runtime("shutdown_flush_failures")
            self._worker_pool.stop(timeout=timeout)
            self._state = LifecycleState.CLOSED
        if flush_failed:
            dirty_remaining = self._count_dirty_entries()
            raise ShutdownFlushError(
                "not all dirty write-back entries were flushed before shutdown "
                f"({dirty_remaining} still dirty)"
            )

    def get(self, key: Hashable, default: Any = None) -> Any:
        """Return the value for ``key``, or ``default`` on a miss.

        Because the default is ``None``, a stored ``None`` value is
        indistinguishable from a miss via ``get()`` alone; pass a sentinel
        ``default`` (or use ``contains()``/``inspect()``) to tell them apart.
        """
        self._require_not_closed("get")
        shard = self._shard_for(key)
        with shard.lock:
            found, value = self._read_value_locked(shard, key, touch=True, count_stats=True)
            return value if found else default

    def put(self, key: Hashable, value: Any, ttl: float | None | _Missing = _TTL_UNSET) -> None:
        """Store ``value`` under ``key``.

        The in-memory write commits under the shard lock before this returns. In
        write-back mode the durable flush is enqueued afterwards; if a bounded
        queue is full the entry stays cached and marked dirty (and is persisted
        by ``close(flush=True)``) while ``QueueBackpressureError`` is raised so
        the backpressure is never silent.

        A supplied ``ttl`` must be positive; ``ttl=None`` stores without expiry
        and omitting it uses the cache's default TTL.
        """
        self._require_not_closed("put")
        self._maybe_warn_cache_not_started("put")
        self._validate_explicit_ttl(ttl)
        shard = self._shard_for(key)
        flush_job: FlushWriteBack | None = None
        with shard.lock:
            now = self.clock.now()
            existing = shard.backend.get_entry(key)
            if existing is not None and existing.is_expired(now):
                self._remove_entry_locked(shard, key, reason="expire", now=now)
                existing = None
            if self.write_mode == WriteMode.WRITE_THROUGH:
                # Write-through holds the shard lock across the source write so
                # the cache and source-of-truth update atomically (concurrent
                # writers to the same key stay consistent). This deliberately
                # serializes the shard on source latency; write-back trades that
                # consistency for speed by deferring the write to a worker.
                self.source_backend.put_value(key, value)
            version = shard.next_version(key)
            shard.tombstones.pop(key, None)
            effective_ttl, expires_at = self._resolve_ttl(existing, ttl, now)
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=now if existing is None else existing.created_at,
                last_accessed_at=now,
                hit_count=0 if existing is None else existing.hit_count,
                expires_at=expires_at,
                ttl=effective_ttl,
                version=version,
                dirty=self.write_mode == WriteMode.WRITE_BACK,
            )
            shard.backend.put_entry(entry)
            shard.policy.on_put(key)
            shard.stats.puts += 1
            self._enforce_capacity_locked(shard, now)
            if self.write_mode == WriteMode.WRITE_BACK:
                flush_job = FlushWriteBack(
                    shard_index=shard.index,
                    key=key,
                    value=value,
                    version=version,
                    operation="put",
                    retries_left=self.config.write_back_retry_count,
                )
                self._register_pending_locked(shard, key)
            log_event(self.logger, "put", key=key, shard=shard.index, version=version)
        if flush_job is not None:
            self._enqueue_flush_jobs([flush_job])

    def delete(self, key: Hashable) -> bool:
        """Remove ``key`` from the cache.

        Tombstones and per-key versions are only recorded in write-back mode,
        where they are needed to stop a stale pending flush from resurrecting the
        value; in other modes the key's metadata is pruned immediately so it can
        never accumulate.
        """
        self._require_not_closed("delete")
        shard = self._shard_for(key)
        flush_job: FlushWriteBack | None = None
        with shard.lock:
            now = self.clock.now()
            if self.write_mode == WriteMode.WRITE_THROUGH:
                # Held under the shard lock for cache/source consistency; see put().
                self.source_backend.delete_value(key)
            if self.write_mode == WriteMode.WRITE_BACK:
                version = shard.next_version(key)
                shard.tombstones[key] = version
                flush_job = FlushWriteBack(
                    shard_index=shard.index,
                    key=key,
                    value=None,
                    version=version,
                    operation="delete",
                    retries_left=self.config.write_back_retry_count,
                )
                self._register_pending_locked(shard, key)
                log_event(self.logger, "delete", key=key, shard=shard.index, version=version)
            else:
                log_event(self.logger, "delete", key=key, shard=shard.index)
            existed = self._remove_entry_locked(shard, key, reason="delete", now=now)
            if existed:
                shard.stats.deletes += 1
            shard.singleflight.pop(key, None)
        if flush_job is not None:
            self._enqueue_flush_jobs([flush_job])
        return existed

    def contains(self, key: Hashable) -> bool:
        self._require_not_closed("contains")
        shard = self._shard_for(key)
        with shard.lock:
            found, _ = self._read_value_locked(shard, key, touch=False, count_stats=True)
            return found

    def clear(self) -> None:
        self._require_not_closed("clear")
        flush_jobs: list[FlushWriteBack] = []
        for shard in self._shards:
            with shard.lock:
                now = self.clock.now()
                keys = list(shard.backend.keys())
                for key in keys:
                    if self.write_mode == WriteMode.WRITE_THROUGH:
                        # Held under the shard lock for consistency; see put().
                        self.source_backend.delete_value(key)
                    if self.write_mode == WriteMode.WRITE_BACK:
                        version = shard.next_version(key)
                        shard.tombstones[key] = version
                        flush_jobs.append(
                            FlushWriteBack(
                                shard_index=shard.index,
                                key=key,
                                value=None,
                                version=version,
                                operation="delete",
                                retries_left=self.config.write_back_retry_count,
                            )
                        )
                        self._register_pending_locked(shard, key)
                    if self._remove_entry_locked(shard, key, reason="delete", now=now):
                        shard.stats.deletes += 1
                shard.policy.clear()
                shard.singleflight.clear()
        self._enqueue_flush_jobs(flush_jobs)

    def size(self) -> int:
        self._require_not_closed("size")
        return sum(shard.backend.size() for shard in self._locked_shards())

    def inspect(self, key: Hashable) -> EntrySnapshot | None:
        self._require_not_closed("inspect")
        shard = self._shard_for(key)
        with shard.lock:
            now = self.clock.now()
            entry = shard.backend.get_entry(key)
            if entry is None:
                return None
            if entry.is_expired(now):
                # inspect() lazily evicts expired entries (and counts the
                # expiration) but does not count a hit/miss: it is a diagnostic
                # read, not part of the cache's hit-ratio.
                self._remove_entry_locked(shard, key, reason="expire", now=now)
                return None
            return entry.snapshot(now)

    def dump(self, limit: int | None = None) -> list[EntrySnapshot]:
        self._require_not_closed("dump")
        snapshots: list[EntrySnapshot] = []
        for shard in self._shards:
            with shard.lock:
                now = self.clock.now()
                for entry in list(shard.backend.entries()):
                    if entry.is_expired(now):
                        self._remove_entry_locked(shard, entry.key, reason="expire", now=now)
                    else:
                        snapshots.append(entry.snapshot(now))
        if limit is not None:
            return snapshots[:limit]
        return snapshots

    def stats(self) -> CacheStatsSnapshot:
        shard_snapshots: list[ShardStatsSnapshot] = []
        for shard in self._shards:
            with shard.lock:
                policy_stats = PolicyStatsSnapshot(
                    name=shard.policy.name,
                    evictions=shard.stats.evictions,
                    tracked_keys=len(shard.policy),
                    metadata_size=shard.policy.metadata_size(),
                )
                shard_snapshots.append(
                    ShardStatsSnapshot(
                        index=shard.index,
                        size=shard.backend.size(),
                        capacity=shard.capacity,
                        hits=shard.stats.hits,
                        misses=shard.stats.misses,
                        puts=shard.stats.puts,
                        deletes=shard.stats.deletes,
                        evictions=shard.stats.evictions,
                        expirations=shard.stats.expirations,
                        lock_contention=shard.lock.contentions,
                        policy=policy_stats,
                    )
                )
        hits = sum(shard.hits for shard in shard_snapshots)
        misses = sum(shard.misses for shard in shard_snapshots)
        total_reads = hits + misses
        with self._runtime_lock:
            runtime = replace(self._runtime)
        return CacheStatsSnapshot(
            hits=hits,
            misses=misses,
            hit_ratio=(hits / total_reads) if total_reads else 0.0,
            puts=sum(shard.puts for shard in shard_snapshots),
            deletes=sum(shard.deletes for shard in shard_snapshots),
            evictions=sum(shard.evictions for shard in shard_snapshots),
            expirations=sum(shard.expirations for shard in shard_snapshots),
            size=sum(shard.size for shard in shard_snapshots),
            capacity=sum(shard.capacity for shard in shard_snapshots),
            queue_depth=self.job_queue.depth,
            queue_dropped=self.job_queue.dropped,
            worker_jobs_completed=runtime.worker_jobs_completed,
            worker_jobs_failed=runtime.worker_jobs_failed,
            write_back_retries=runtime.write_back_retries,
            stale_write_back_jobs_skipped=runtime.stale_write_back_jobs_skipped,
            flush_failures=runtime.flush_failures,
            shutdown_flush_failures=runtime.shutdown_flush_failures,
            shards=tuple(shard_snapshots),
        )

    def get_or_compute(
        self,
        key: Hashable,
        loader: Callable[[], Any],
        ttl: float | None | _Missing = _TTL_UNSET,
    ) -> Any:
        self._require_not_closed("get_or_compute")
        self._validate_explicit_ttl(ttl)
        shard = self._shard_for(key)
        leader = False
        with shard.lock:
            found, value = self._read_value_locked(shard, key, touch=True, count_stats=True)
            if found:
                return value
            flight = shard.singleflight.get(key)
            if flight is None:
                flight = Flight(event=threading.Event())
                shard.singleflight[key] = flight
                leader = True
        if leader:
            try:
                loaded = loader()
            except BaseException as exc:
                self._fail_flight_locked(shard, key, flight, exc)
                raise
            try:
                self.put(key, loaded, ttl=ttl)
            except QueueBackpressureError:
                # The value loaded and is cached (dirty); only the durable flush
                # could not be enqueued right now. Publish it to the waiters
                # rather than failing every caller for a background-write hiccup.
                log_event(self.logger, "get_or_compute_flush_deferred", key=key)
            except BaseException as exc:
                self._fail_flight_locked(shard, key, flight, exc)
                raise
            with shard.lock:
                flight.result = loaded
                shard.singleflight.pop(key, None)
                flight.event.set()
            return loaded
        flight.event.wait()
        if flight.exception is not None:
            raise flight.exception
        return flight.result

    def expire_all(self) -> int:
        self._require_not_closed("expire_all")
        return sum(self._expire_shard(index) for index in range(len(self._shards)))

    def preload(
        self,
        key: Hashable,
        loader: Callable[[], Any],
        ttl: float | None | _Missing = _TTL_UNSET,
    ) -> bool:
        """Warm ``key`` in the background via a ``PreloadKey`` worker job.

        Requires a worker pool (``worker_count > 0``); the loader runs on a
        worker thread. Returns False if the job was dropped because the queue was
        full (preloading is best-effort, never critical). Omitting ``ttl`` uses
        the cache default; ``ttl=None`` stores without expiry; a positive number
        sets an explicit TTL.
        """
        self._require_not_closed("preload")
        self._validate_explicit_ttl(ttl)
        self._require_workers("preload")
        self._maybe_warn_cache_not_started("preload")
        shard = self._shard_for(key)
        ttl_supplied = not isinstance(ttl, _Missing)
        effective_ttl = None if isinstance(ttl, _Missing) else ttl
        return self._enqueue_job(
            PreloadKey(
                shard_index=shard.index,
                key=key,
                loader=loader,
                ttl=effective_ttl,
                ttl_supplied=ttl_supplied,
            ),
            critical=False,
        )

    def request_snapshot(self, request_id: str = "") -> bool:
        """Ask a worker to capture a stats snapshot, readable via last_snapshot().

        Requires a worker pool (``worker_count > 0``).
        """
        self._require_not_closed("request_snapshot")
        self._require_workers("request_snapshot")
        return self._enqueue_job(SnapshotStats(request_id=request_id), critical=False)

    def last_snapshot(self) -> CacheStatsSnapshot | None:
        """Return the most recent snapshot captured by a ``SnapshotStats`` job."""
        with self._runtime_lock:
            return self._last_snapshot

    def scheduler_tick(self) -> None:
        self._require_not_closed("scheduler_tick")
        self._scheduler.tick_once()

    def alive_threads(self) -> list[threading.Thread]:
        threads = self._worker_pool.alive_threads()
        scheduler_thread = self._scheduler.thread
        if self._scheduler.alive() and scheduler_thread is not None:
            threads.append(scheduler_thread)
        return threads

    def _shard_for(self, key: Hashable) -> CacheShard:
        return self._shards[stable_hash(key) % len(self._shards)]

    def _locked_shards(self) -> Iterable[CacheShard]:
        for shard in self._shards:
            with shard.lock:
                yield shard

    def _read_value_locked(
        self,
        shard: CacheShard,
        key: Hashable,
        *,
        touch: bool,
        count_stats: bool,
    ) -> tuple[bool, Any]:
        now = self.clock.now()
        entry = shard.backend.get_entry(key)
        if entry is None:
            if count_stats:
                shard.stats.misses += 1
            log_event(self.logger, "miss", key=key, shard=shard.index)
            return False, None
        if entry.is_expired(now):
            self._remove_entry_locked(shard, key, reason="expire", now=now)
            if count_stats:
                shard.stats.misses += 1
            log_event(self.logger, "expire_miss", key=key, shard=shard.index)
            return False, None
        if touch:
            entry.touch(now)
            shard.policy.on_get(key)
        if count_stats:
            shard.stats.hits += 1
        log_event(self.logger, "hit", key=key, shard=shard.index)
        return True, entry.value

    def _remove_entry_locked(self, shard: CacheShard, key: Hashable, *, reason: str, now: float) -> bool:
        removed = shard.backend.delete_entry(key)
        shard.policy.on_delete(key)
        if removed and reason == "evict":
            shard.stats.evictions += 1
            log_event(self.logger, "evict", key=key, shard=shard.index)
        elif removed and reason == "expire":
            shard.stats.expirations += 1
            log_event(self.logger, "expire", key=key, shard=shard.index, at=now)
        self._maybe_prune_marks_locked(shard, key)
        return removed

    def _enforce_capacity_locked(self, shard: CacheShard, now: float) -> None:
        while shard.backend.size() > shard.capacity:
            candidate = shard.policy.evict_candidate()
            if candidate is None:
                break
            self._remove_entry_locked(shard, candidate, reason="evict", now=now)

    def _resolve_ttl(
        self,
        existing: CacheEntry | None,
        ttl: float | None | _Missing,
        now: float,
    ) -> tuple[float | None, float | None]:
        # Semantics: an explicit ttl (including None) always wins. With no ttl
        # argument, updating an existing key preserves its original absolute
        # expiry rather than restarting the countdown -- an update rewrites the
        # value, not the lifetime. A brand-new key falls back to the default TTL.
        if isinstance(ttl, _Missing):
            if existing is not None:
                return existing.ttl, existing.expires_at
            ttl_value = self.config.default_ttl
        elif ttl is None:
            ttl_value = None
        else:
            ttl_value = float(ttl)
        if ttl_value is None or ttl_value <= 0:
            return None, None
        return ttl_value, now + ttl_value

    def _expire_shard(self, shard_index: int) -> int:
        shard = self._shards[shard_index]
        expired = 0
        with shard.lock:
            now = self.clock.now()
            for key in expired_keys(list(shard.backend.entries()), now):
                if self._remove_entry_locked(shard, key, reason="expire", now=now):
                    expired += 1
        return expired

    def _enqueue_job(self, job: Job, *, critical: bool) -> bool:
        ok = self.job_queue.put(job, critical=critical, timeout=self.config.queue_put_timeout)
        if ok:
            return True
        if critical:
            raise QueueBackpressureError(f"critical job could not be queued: {job!r}")
        return False

    def _enqueue_flush_jobs(self, jobs: list[FlushWriteBack]) -> None:
        # Each job's pending-flush count was registered under the shard lock. If a
        # critical enqueue is rejected (bounded queue full), release the counts
        # for this job and every not-yet-enqueued one before raising, otherwise
        # their version marks and tombstones could never be pruned.
        for index, job in enumerate(jobs):
            try:
                self._enqueue_job(job, critical=True)
            except QueueBackpressureError:
                for pending in jobs[index:]:
                    shard = self._shards[pending.shard_index]
                    with shard.lock:
                        self._resolve_pending_locked(shard, pending.key)
                raise

    @staticmethod
    def _validate_explicit_ttl(ttl: float | None | _Missing) -> None:
        if isinstance(ttl, _Missing) or ttl is None:
            return
        if float(ttl) <= 0:
            raise ValidationError(f"ttl must be positive when provided, got {ttl!r}")

    def _fail_flight_locked(
        self, shard: CacheShard, key: Hashable, flight: Flight, exc: BaseException
    ) -> None:
        with shard.lock:
            flight.exception = exc
            shard.singleflight.pop(key, None)
            flight.event.set()

    def _handle_job(self, job: Job) -> None:
        if isinstance(job, ExpireShard):
            self._expire_shard(job.shard_index)
            self._inc_runtime("worker_jobs_completed")
            return
        if isinstance(job, FlushWriteBack):
            completed = self._flush_write_back_job(job)
            self._inc_runtime("worker_jobs_completed" if completed else "worker_jobs_failed")
            return
        if isinstance(job, PreloadKey):
            put_ttl: float | None | _Missing = _TTL_UNSET if not job.ttl_supplied else job.ttl
            self.put(job.key, job.loader(), ttl=put_ttl)
            self._inc_runtime("worker_jobs_completed")
            return
        if isinstance(job, SnapshotStats):
            snapshot = self.stats()
            with self._runtime_lock:
                self._last_snapshot = snapshot
            self._inc_runtime("worker_jobs_completed")
            return
        # Defensive: an unrecognized job type is counted as a failure rather than
        # silently consumed. (StopWorker is handled by the worker loop itself.)
        self._inc_runtime("worker_jobs_failed")
        log_event(self.logger, "unknown_job", job=type(job).__name__)

    def _flush_write_back_job(self, job: FlushWriteBack) -> bool:
        shard = self._shards[job.shard_index]
        with shard.lock:
            if is_stale_write_back(shard.version_marks, shard.tombstones, job):
                self._inc_runtime("stale_write_back_jobs_skipped")
                log_event(self.logger, "stale_write_back_skip", key=job.key, version=job.version)
                self._resolve_pending_locked(shard, job.key)
                return True
        try:
            apply_write_back(self.source_backend, job)
        except Exception:
            if job.retries_left > 0:
                self._inc_runtime("write_back_retries")
                self.clock.sleep(self.config.write_back_retry_delay)
                retry = FlushWriteBack(
                    shard_index=job.shard_index,
                    key=job.key,
                    value=job.value,
                    version=job.version,
                    operation=job.operation,
                    retries_left=job.retries_left - 1,
                    attempt=job.attempt + 1,
                )
                try:
                    self._enqueue_job(retry, critical=True)
                except QueueBackpressureError:
                    # Can't reschedule under backpressure: record a flush failure
                    # and release the pending mark rather than leaking it.
                    self._inc_runtime("flush_failures")
                    log_event(self.logger, "write_back_retry_dropped", key=job.key, version=job.version)
                    with shard.lock:
                        self._resolve_pending_locked(shard, job.key)
                    return False
                log_event(self.logger, "write_back_retry", key=job.key, attempt=retry.attempt)
                return True
            self._inc_runtime("flush_failures")
            log_event(self.logger, "write_back_failure", key=job.key, version=job.version)
            with shard.lock:
                self._resolve_pending_locked(shard, job.key)
            return False
        with shard.lock:
            if job.operation == "put":
                entry = shard.backend.get_entry(job.key)
                if entry is not None and entry.version == job.version:
                    entry.dirty = False
            self._resolve_pending_locked(shard, job.key)
        return True

    def _enqueue_dirty_write_back_jobs(self) -> None:
        for shard in self._shards:
            jobs: list[FlushWriteBack] = []
            with shard.lock:
                for entry in shard.backend.entries():
                    if entry.dirty:
                        jobs.append(
                            FlushWriteBack(
                                shard_index=shard.index,
                                key=entry.key,
                                value=entry.value,
                                version=entry.version,
                                operation="put",
                                retries_left=self.config.write_back_retry_count,
                            )
                        )
                        self._register_pending_locked(shard, entry.key)
                for key, version in shard.tombstones.items():
                    jobs.append(
                        FlushWriteBack(
                            shard_index=shard.index,
                            key=key,
                            value=None,
                            version=version,
                            operation="delete",
                            retries_left=self.config.write_back_retry_count,
                        )
                    )
                    self._register_pending_locked(shard, key)
            for index, job in enumerate(jobs):
                try:
                    self._enqueue_job(job, critical=True)
                except QueueBackpressureError:
                    # Shutdown path: the synchronous flush below is the backstop,
                    # so a full queue here is not fatal. Release the pending marks
                    # for the jobs we could not enqueue instead of leaking them.
                    for pending in jobs[index:]:
                        with shard.lock:
                            self._resolve_pending_locked(shard, pending.key)
                    break

    def _flush_dirty_entries_sync(self) -> bool:
        failed = False
        for shard in self._shards:
            with shard.lock:
                put_jobs = [
                    FlushWriteBack(
                        shard_index=shard.index,
                        key=entry.key,
                        value=entry.value,
                        version=entry.version,
                        operation="put",
                        retries_left=self.config.write_back_retry_count,
                    )
                    for entry in shard.backend.entries()
                    if entry.dirty
                ]
                delete_jobs = [
                    FlushWriteBack(
                        shard_index=shard.index,
                        key=key,
                        value=None,
                        version=version,
                        operation="delete",
                        retries_left=self.config.write_back_retry_count,
                    )
                    for key, version in shard.tombstones.items()
                ]
            for job in [*put_jobs, *delete_jobs]:
                with shard.lock:
                    if is_stale_write_back(shard.version_marks, shard.tombstones, job):
                        self._inc_runtime("stale_write_back_jobs_skipped")
                        self._clear_pending_flushes_locked(shard, job.key)
                        continue
                attempts = job.retries_left + 1
                success = False
                for attempt in range(attempts):
                    try:
                        if job.operation == "put":
                            self.source_backend.put_value(job.key, job.value)
                            with shard.lock:
                                entry = shard.backend.get_entry(job.key)
                                if entry is not None and entry.version == job.version:
                                    entry.dirty = False
                        else:
                            self.source_backend.delete_value(job.key)
                        success = True
                        break
                    except Exception:
                        if attempt < attempts - 1:
                            self._inc_runtime("write_back_retries")
                            self.clock.sleep(self.config.write_back_retry_delay)
                if success:
                    with shard.lock:
                        self._clear_pending_flushes_locked(shard, job.key)
                else:
                    self._inc_runtime("flush_failures")
                    with shard.lock:
                        self._clear_pending_flushes_locked(shard, job.key)
                    failed = True
        return failed

    def _parse_write_mode(self, mode: str) -> WriteMode:
        try:
            return WriteMode(mode)
        except ValueError as exc:
            raise UnsupportedWriteModeError(f"unsupported write mode: {mode}") from exc

    def _require_workers(self, operation: str) -> None:
        if self.config.worker_count <= 0:
            raise RuntimeError(
                f"{operation} requires a worker pool; construct the cache with worker_count > 0"
            )

    def _require_not_closed(self, operation: str) -> None:
        with self._lifecycle_lock:
            if self._state in (LifecycleState.CLOSED, LifecycleState.CLOSING):
                raise RuntimeError(f"cannot {operation} on a closed cache")

    def _maybe_warn_cache_not_started(self, operation: str) -> None:
        if self._cache_not_started_warned:
            return
        with self._lifecycle_lock:
            if self._state == LifecycleState.STARTED:
                return
        if self.config.worker_count == 0:
            if self.write_mode == WriteMode.WRITE_BACK:
                self.logger.warning(
                    "cachelab_event write_back_inactive reason=no_workers "
                    "note=flush_jobs_queue_until_close"
                )
                self._cache_not_started_warned = True
            return
        notes: list[str] = ["call_start_before_worker_jobs"]
        if self.config.active_expiration:
            notes.append("active_expiration_inactive")
        if self.write_mode == WriteMode.WRITE_BACK:
            notes.append("write_back_flush_jobs_queue")
        self.logger.warning(
            "cachelab_event cache_not_started operation=%s note=%s",
            operation,
            ",".join(notes),
        )
        self._cache_not_started_warned = True

    def _count_dirty_entries(self) -> int:
        count = 0
        for shard in self._shards:
            with shard.lock:
                count += sum(1 for entry in shard.backend.entries() if entry.dirty)
        return count

    def restore_entry_metadata(self, key: Hashable, *, hit_count: int) -> None:
        """Restore entry fields not set by ``put()`` during state reload."""
        self._require_not_closed("restore_entry_metadata")
        shard = self._shard_for(key)
        with shard.lock:
            entry = shard.backend.get_entry(key)
            if entry is not None:
                entry.hit_count = hit_count

    def _record_worker_failure(self, exc: BaseException) -> None:
        self._inc_runtime("worker_jobs_failed")

    def _register_pending_locked(self, shard: CacheShard, key: Hashable) -> None:
        shard.pending_flushes[key] = shard.pending_flushes.get(key, 0) + 1

    def _resolve_pending_locked(self, shard: CacheShard, key: Hashable) -> None:
        remaining = shard.pending_flushes.get(key, 0) - 1
        if remaining > 0:
            shard.pending_flushes[key] = remaining
        else:
            shard.pending_flushes.pop(key, None)
        self._maybe_prune_marks_locked(shard, key)

    def _clear_pending_flushes_locked(self, shard: CacheShard, key: Hashable) -> None:
        """Drop all outstanding flush counters for ``key`` (shutdown sync path)."""
        shard.pending_flushes.pop(key, None)
        self._maybe_prune_marks_locked(shard, key)

    def _maybe_prune_marks_locked(self, shard: CacheShard, key: Hashable) -> None:
        # Version marks and tombstones may only be dropped once nothing still
        # references them: no in-flight write-back job (pending_flushes) and no
        # live entry. This bounds both maps to the live key set plus keys with
        # outstanding flushes, instead of growing forever.
        if shard.pending_flushes.get(key, 0) > 0:
            return
        if shard.backend.get_entry(key) is not None:
            return
        shard.version_marks.pop(key, None)
        shard.tombstones.pop(key, None)

    def _inc_runtime(self, field: str) -> None:
        with self._runtime_lock:
            current = getattr(self._runtime, field)
            setattr(self._runtime, field, current + 1)
