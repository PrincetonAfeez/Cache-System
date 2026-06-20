""" Test active expiration """

from __future__ import annotations

from cachelab import Cache, FakeClock


def test_active_expiration_removes_without_public_read() -> None:
    clock = FakeClock()
    cache = Cache(capacity=4, worker_count=1, scheduler_interval=10, clock=clock)
    cache.start()
    cache.put("a", "one", ttl=5)
    clock.advance(6)
    cache.scheduler_tick()
    assert cache.job_queue.join_until(1)
    assert cache.size() == 0
    cache.close(flush=False)
