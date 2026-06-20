""" Test exports and entry """

from __future__ import annotations

import threading

from cachelab.concurrency import Flight, shard_capacities, stable_hash
from cachelab.core.clock import FakeClock
from cachelab.core.entry import CacheEntry, EntrySnapshot
from cachelab.core.exceptions import CacheLabError, ConfigurationError
from cachelab.core.lifecycle import LifecycleState
from cachelab.core.stats import CacheStatsSnapshot, PolicyStatsSnapshot, ShardStatsSnapshot
from cachelab.observability import format_table
from cachelab.observability.logging import get_logger
from cachelab.policies import FIFOPolicy, LFUPolicy, LRUPolicy, make_policy
from cachelab.workers import CacheJobQueue, ExpirationScheduler, WorkerPool
from cachelab.workers.expiration_worker import expired_keys
from cachelab.workloads import benchmark_policies, run_simulation
from cachelab.workloads.patterns import key_stream


def test_entry_snapshot_and_expiry() -> None:
    entry = CacheEntry(
        key="k",
        value="v",
        created_at=0.0,
        last_accessed_at=0.0,
        hit_count=0,
        expires_at=10.0,
        ttl=10.0,
        version=1,
    )
    assert not entry.is_expired(5.0)
    assert entry.is_expired(10.0)
    entry.touch(1.0)
    assert entry.hit_count == 1
    snap = entry.snapshot(2.0)
    assert isinstance(snap, EntrySnapshot)
    assert snap.ttl_remaining == 8.0


def test_expired_keys_helper() -> None:
    entry = CacheEntry(
        key="k",
        value="v",
        created_at=0.0,
        last_accessed_at=0.0,
        hit_count=0,
        expires_at=5.0,
        ttl=5.0,
        version=1,
    )
    assert expired_keys([entry], 6.0) == ["k"]
    assert expired_keys([entry], 4.0) == []


def test_exception_hierarchy() -> None:
    assert issubclass(ConfigurationError, CacheLabError)


def test_lifecycle_state_values() -> None:
    assert LifecycleState.CREATED.name == "CREATED"
    assert LifecycleState.CLOSED.name == "CLOSED"


def test_stats_dataclasses() -> None:
    policy = PolicyStatsSnapshot(name="lru", evictions=0, tracked_keys=0, metadata_size=0)
    shard = ShardStatsSnapshot(
        index=0,
        size=0,
        capacity=4,
        hits=0,
        misses=0,
        puts=0,
        deletes=0,
        evictions=0,
        expirations=0,
        lock_contention=0,
        policy=policy,
    )
    snapshot = CacheStatsSnapshot(
        hits=0,
        misses=0,
        hit_ratio=0.0,
        puts=0,
        deletes=0,
        evictions=0,
        expirations=0,
        size=0,
        capacity=4,
        queue_depth=0,
        queue_dropped=0,
        worker_jobs_completed=0,
        worker_jobs_failed=0,
        write_back_retries=0,
        stale_write_back_jobs_skipped=0,
        flush_failures=0,
        shutdown_flush_failures=0,
        shards=(shard,),
    )
    assert snapshot.shards[0].policy.name == "lru"


def test_package_submodule_exports() -> None:
    assert make_policy("lru").name == "lru"
    assert FIFOPolicy().name == "fifo"
    assert LFUPolicy().name == "lfu"
    assert LRUPolicy().name == "lru"
    assert get_logger().name == "cachelab"
    assert "a" in format_table(["a"], [["b"]])
    rows = benchmark_policies(
        policies=["fifo"],
        pattern="sequential",
        capacity=10,
        requests=20,
        seed=1,
    )
    assert rows[0]["policy"] == "fifo"
    result = run_simulation(
        policy="lru",
        pattern="mixed",
        capacity=10,
        requests=30,
        seed=2,
    )
    writes = result["writes"]
    assert isinstance(writes, int) and writes >= 1
    assert len(list(key_stream("mixed_read_write", 10, capacity=8))) == 10


def test_concurrency_helpers_and_flight() -> None:
    caps = shard_capacities(10, 3)
    assert sum(caps) == 10
    assert stable_hash(1) == stable_hash(1.0)
    flight = Flight(threading.Event())
    assert flight.result is None
    assert flight.exception is None


def test_worker_package_exports_construct() -> None:
    queue = CacheJobQueue(maxsize=2)
    pool = WorkerPool("x", 0, queue, lambda job: None, lambda exc: None, get_logger())
    scheduler = ExpirationScheduler(1.0, 1, queue, FakeClock(), get_logger())
    assert pool.count == 0
    scheduler.stop(0.1)
