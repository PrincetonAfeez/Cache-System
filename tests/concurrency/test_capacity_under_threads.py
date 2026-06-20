""" Test capacity under threads """

from __future__ import annotations

import threading

from cachelab import Cache


def test_capacity_never_exceeds_after_concurrent_puts() -> None:
    cache = Cache(capacity=10, shard_count=1)

    def write(start: int) -> None:
        for index in range(start, start + 100):
            cache.put(f"k{index}", index)
            assert cache.size() <= 10

    threads = [threading.Thread(target=write, args=(offset * 1000,)) for offset in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert cache.size() <= 10
