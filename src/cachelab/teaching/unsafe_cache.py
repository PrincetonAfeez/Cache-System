""" Unsafe cache utilities for CacheLab """

from __future__ import annotations

import threading
import time
from typing import Any, Hashable


class UnsafeNoLockCache:
    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self.data: dict[Hashable, Any] = {}

    def put(self, key: Hashable, value: Any) -> None:
        if len(self.data) >= self.capacity and self.data:
            first = next(iter(self.data))
            self.data.pop(first, None)
        time.sleep(0.001)
        self.data[key] = value


def unsafe_race_demo(threads: int = 25, capacity: int = 1) -> dict[str, int]:
    cache = UnsafeNoLockCache(capacity=capacity)
    barrier = threading.Barrier(threads)

    def write(index: int) -> None:
        barrier.wait()
        cache.put(f"k{index}", index)

    workers = [threading.Thread(target=write, args=(index,)) for index in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    return {"capacity": capacity, "final_size": len(cache.data), "threads": threads}
