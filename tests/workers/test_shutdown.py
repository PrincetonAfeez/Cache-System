""" Test shutdown """

from __future__ import annotations

import pytest

from cachelab import Cache, FakeClock
from cachelab.core.exceptions import ShutdownFlushError
from cachelab.storage.slow_dict import SlowDictBackend
from cachelab.storage.write_modes import WriteMode
from cachelab.workers.messages import ExpireShard


def test_close_is_idempotent_and_leaves_no_threads() -> None:
    cache = Cache(capacity=8, worker_count=2, scheduler_interval=10)
    cache.start()
    assert cache.alive_threads()
    cache.close(flush=False)
    cache.close(flush=False)
    assert cache.alive_threads() == []


def test_close_stops_workers_even_when_bounded_queue_is_full() -> None:
    # Regression guard: a saturated bounded queue must not prevent shutdown.
    # The worker pool's stop event guarantees exit even if no StopWorker sentinel
    # can be enqueued.
    cache = Cache(capacity=8, worker_count=2, queue_size=1, scheduler_interval=0.001)
    cache.start()
    for _ in range(50):
        cache.job_queue.put(ExpireShard(0), critical=False)
    cache.close(flush=False)
    assert cache.alive_threads() == []


def test_close_flush_true_raises_when_flush_permanently_fails() -> None:
    backend = SlowDictBackend()
    backend.fail_next(100)  # never succeeds within the retry budget
    cache = Cache(
        capacity=8,
        write_mode=WriteMode.WRITE_BACK.value,
        worker_count=0,
        source_backend=backend,
        clock=FakeClock(),
    )
    cache.put("a", "v")
    with pytest.raises(ShutdownFlushError):
        cache.close(flush=True)
    assert cache.stats().shutdown_flush_failures >= 1
    assert cache._shards[0].pending_flushes == {}
    assert cache.alive_threads() == []
