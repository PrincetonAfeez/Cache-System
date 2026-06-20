""" Test LRU """

from __future__ import annotations

from cachelab import Cache


def test_lru_get_marks_recent() -> None:
    cache = Cache(capacity=2, policy="lru", shard_count=1)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1
    cache.put("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3


def test_lru_update_does_not_duplicate_metadata() -> None:
    cache = Cache(capacity=2, policy="lru", shard_count=1)
    cache.put("a", 1)
    cache.put("a", 2)
    assert cache.size() == 1
    assert cache.stats().shards[0].policy.tracked_keys == 1
