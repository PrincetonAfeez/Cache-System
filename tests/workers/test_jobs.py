""" Test jobs """

from __future__ import annotations

import pytest

from cachelab import Cache


def test_preload_without_workers_raises() -> None:
    cache = Cache(capacity=4)  # worker_count=0
    with pytest.raises(RuntimeError):
        cache.preload("k", lambda: "v")


def test_request_snapshot_without_workers_raises() -> None:
    cache = Cache(capacity=4)
    with pytest.raises(RuntimeError):
        cache.request_snapshot()


def test_preload_warms_key_in_background() -> None:
    cache = Cache(capacity=8, worker_count=1, scheduler_interval=10)
    cache.start()
    assert cache.preload("k", lambda: "warm")
    assert cache.job_queue.join_until(1)
    assert cache.get("k") == "warm"
    cache.close(flush=False)


def test_request_snapshot_populates_last_snapshot() -> None:
    cache = Cache(capacity=8, worker_count=1, scheduler_interval=10)
    cache.start()
    assert cache.last_snapshot() is None
    cache.put("k", "v")
    cache.request_snapshot("req-1")
    assert cache.job_queue.join_until(1)
    snapshot = cache.last_snapshot()
    assert snapshot is not None
    assert snapshot.size == 1
    cache.close(flush=False)


def test_unknown_job_is_counted_as_failed() -> None:
    cache = Cache(capacity=8, worker_count=1, scheduler_interval=10)
    cache.start()
    cache.job_queue.put(object(), critical=False)  # type: ignore[arg-type]
    assert cache.job_queue.join_until(1)
    cache.close(flush=False)
    assert cache.stats().worker_jobs_failed >= 1


def test_queue_is_settled_after_close() -> None:
    cache = Cache(capacity=8, worker_count=2, queue_size=8, scheduler_interval=10)
    cache.start()
    cache.close(flush=False)
    assert cache.stats().queue_depth == 0
