""" Test stress """

from __future__ import annotations

import threading

from cachelab import Cache


def test_mixed_operations_under_threads_preserve_invariants() -> None:
    cache = Cache(capacity=128, shard_count=8, policy="lru")

    def loader() -> str:
        return "computed"

    def worker(worker_id: int) -> None:
        for index in range(400):
            key = f"{worker_id}:{index % 60}"
            cache.put(key, index)
            cache.get(key)
            cache.contains(key)
            cache.inspect(key)
            cache.get_or_compute(f"shared:{index % 30}", loader)
            if index % 13 == 0:
                cache.delete(key)

    threads = [threading.Thread(target=worker, args=(worker_id,)) for worker_id in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    stats = cache.stats()
    assert stats.size <= stats.capacity
    for shard in stats.shards:
        assert shard.size <= shard.capacity
        # Backend contents and eviction-policy metadata stay consistent.
        assert shard.size == shard.policy.tracked_keys
