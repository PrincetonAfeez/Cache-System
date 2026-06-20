""" Test sharded cache """

from __future__ import annotations

import threading

from cachelab import Cache


def test_sharded_cache_survives_mixed_concurrent_traffic() -> None:
    cache = Cache(capacity=64, shard_count=8, policy="lru")

    def traffic(worker: int) -> None:
        for index in range(300):
            key = f"{worker}:{index % 100}"
            cache.put(key, index)
            cache.contains(key)
            cache.inspect(key)
            if index % 11 == 0:
                cache.delete(key)
            else:
                cache.get(key)

    threads = [threading.Thread(target=traffic, args=(worker,)) for worker in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    stats = cache.stats()
    assert stats.size <= stats.capacity
    for shard in stats.shards:
        assert shard.size <= shard.capacity
        assert shard.size == shard.policy.tracked_keys
