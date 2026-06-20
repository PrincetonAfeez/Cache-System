""" Stats utilities for CacheLab """

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MutableStats:
    hits: int = 0
    misses: int = 0
    puts: int = 0
    deletes: int = 0
    evictions: int = 0
    expirations: int = 0


@dataclass(frozen=True, slots=True)
class PolicyStatsSnapshot:
    name: str
    evictions: int
    tracked_keys: int
    metadata_size: int


@dataclass(frozen=True, slots=True)
class ShardStatsSnapshot:
    index: int
    size: int
    capacity: int
    hits: int
    misses: int
    puts: int
    deletes: int
    evictions: int
    expirations: int
    lock_contention: int
    policy: PolicyStatsSnapshot


@dataclass(frozen=True, slots=True)
class CacheStatsSnapshot:
    hits: int
    misses: int
    hit_ratio: float
    puts: int
    deletes: int
    evictions: int
    expirations: int
    size: int
    capacity: int
    queue_depth: int
    queue_dropped: int
    worker_jobs_completed: int
    worker_jobs_failed: int
    write_back_retries: int
    stale_write_back_jobs_skipped: int
    flush_failures: int
    shutdown_flush_failures: int
    shards: tuple[ShardStatsSnapshot, ...]
