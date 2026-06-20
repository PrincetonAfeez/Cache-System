""" Test FIFO """

from __future__ import annotations

from cachelab import Cache


def test_fifo_get_does_not_change_eviction_order() -> None:
    cache = Cache(capacity=2, policy="fifo", shard_count=1)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1
    cache.put("c", 3)
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3
