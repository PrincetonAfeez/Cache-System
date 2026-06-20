""" Test backpressure """

from __future__ import annotations

import pytest

from cachelab import Cache
from cachelab.core.config import CacheConfig
from cachelab.core.exceptions import QueueBackpressureError
from cachelab.storage.write_modes import WriteMode


def _full_write_back_cache() -> Cache:
    config = CacheConfig(
        capacity=8,
        write_mode=WriteMode.WRITE_BACK.value,
        queue_size=1,
        queue_put_timeout=0.01,
    )
    return Cache(config=config)


def test_critical_write_back_job_raises_when_bounded_queue_is_full() -> None:
    cache = _full_write_back_cache()
    cache.put("a", "one")
    with pytest.raises(QueueBackpressureError):
        cache.put("b", "two")


def test_backpressured_put_does_not_leak_pending_flush() -> None:
    # Regression: the pending-flush counter must be released when a critical
    # enqueue is rejected, otherwise the key's version mark/tombstone could never
    # be pruned.
    cache = _full_write_back_cache()
    cache.put("a", "one")  # fills the size-1 queue
    with pytest.raises(QueueBackpressureError):
        cache.put("b", "two")
    shard = cache._shard_for("b")
    assert shard.pending_flushes.get("b", 0) == 0


def test_get_or_compute_returns_value_despite_flush_backpressure() -> None:
    # A backpressured background flush must not fail the get_or_compute caller:
    # the value loaded and is cached, only durability was deferred.
    cache = _full_write_back_cache()
    cache.put("filler", "x")  # saturates the queue
    calls = []

    def loader() -> str:
        calls.append(1)
        return "value"

    assert cache.get_or_compute("k", loader) == "value"
    assert cache.get("k") == "value"
    assert len(calls) == 1
