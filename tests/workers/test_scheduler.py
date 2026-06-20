""" Test scheduler """

from __future__ import annotations

from cachelab import Cache
from cachelab.workers.messages import ExpireShard


def test_scheduler_tick_enqueues_one_job_per_shard() -> None:
    cache = Cache(capacity=9, shard_count=3, worker_count=0)
    cache.scheduler_tick()
    jobs = [cache.job_queue.get() for _ in range(3)]
    for _ in jobs:
        cache.job_queue.task_done()
    shard_indexes = sorted(job.shard_index for job in jobs if isinstance(job, ExpireShard))
    assert shard_indexes == [0, 1, 2]


def test_scheduler_thread_starts_and_stops() -> None:
    cache = Cache(capacity=8, worker_count=1, scheduler_interval=0.01)
    cache.start()
    assert cache._scheduler.alive()
    cache.close(flush=False)
    assert not cache._scheduler.alive()
    assert cache._scheduler.thread is not None  # the handle survives for inspection
