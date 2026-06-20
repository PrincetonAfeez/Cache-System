""" Test worker pool """

from __future__ import annotations

from cachelab import Cache


def test_worker_lifecycle_is_idempotent() -> None:
    cache = Cache(capacity=4, worker_count=2, scheduler_interval=10)
    cache.start()
    cache.start()
    assert len(cache.alive_threads()) == 3
    cache.close(flush=False)
    cache.close(flush=False)
    assert cache.alive_threads() == []
