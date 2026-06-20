""" Test remaining coverage """

from __future__ import annotations

import logging
import time
from unittest.mock import patch

from cachelab import Cache
from cachelab.core.exceptions import QueueBackpressureError
from cachelab.storage.slow_dict import SlowDictBackend
from cachelab.storage.write_modes import WriteMode
from cachelab.teaching.unsafe_cache import UnsafeNoLockCache
from cachelab.teaching.unsafe_wall_clock_ttl import AdjustableWallClock, UnsafeWallClockTTLCache
from cachelab.workers.messages import FlushWriteBack
from cachelab.workers.queue import CacheJobQueue
from cachelab.workers.worker_pool import WorkerPool


def test_unsafe_no_lock_cache_evicts_first_key() -> None:
    cache = UnsafeNoLockCache(capacity=1)
    cache.put("first", 1)
    cache.put("second", 2)
    assert "first" not in cache.data


def test_unsafe_wall_clock_contains_false_for_missing_key() -> None:
    cache = UnsafeWallClockTTLCache(AdjustableWallClock())
    assert cache.contains("missing") is False


def test_enforce_capacity_stops_when_policy_has_no_candidate() -> None:
    from cachelab.core.entry import CacheEntry

    cache = Cache(capacity=1, shard_count=1)
    shard = cache._shards[0]
    with shard.lock:
        for key in ("a", "b"):
            shard.backend.put_entry(
                CacheEntry(
                    key=key,
                    value=key,
                    created_at=0.0,
                    last_accessed_at=0.0,
                    hit_count=0,
                    expires_at=None,
                    ttl=None,
                    version=1,
                )
            )
        with patch.object(shard.policy, "evict_candidate", return_value=None):
            cache._enforce_capacity_locked(shard, cache.clock.now())
        assert shard.backend.size() == 2


def test_enqueue_dirty_releases_pending_when_enqueue_fails() -> None:
    backend = SlowDictBackend()
    cache = Cache(
        capacity=8,
        write_mode=WriteMode.WRITE_BACK.value,
        worker_count=0,
        source_backend=backend,
    )
    cache.put("a", "one")
    cache.put("b", "two")
    shard = cache._shards[0]
    with shard.lock:
        shard.pending_flushes.clear()
    calls = {"count": 0}
    real_enqueue = cache._enqueue_job

    def flaky_enqueue(job: FlushWriteBack, *, critical: bool) -> bool:
        calls["count"] += 1
        if calls["count"] == 2:
            raise QueueBackpressureError("full")
        return real_enqueue(job, critical=critical)

    with patch.object(cache, "_enqueue_job", side_effect=flaky_enqueue):
        cache._enqueue_dirty_write_back_jobs()
    assert shard.pending_flushes.get("b", 0) == 0


def test_worker_pool_idle_continue_before_stop() -> None:
    job_queue = CacheJobQueue(maxsize=2)
    pool = WorkerPool("test", 1, job_queue, lambda job: None, lambda exc: None, logging.getLogger("test"))
    with patch("cachelab.workers.worker_pool._IDLE_POLL_SECONDS", 0.05):
        pool.start()
        time.sleep(0.15)
        pool.stop(2.0)
    assert pool.alive_threads() == []
