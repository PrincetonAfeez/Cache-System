""" Sharding utilities for CacheLab """

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Hashable

from cachelab.concurrency.locks import MeteredRLock
from cachelab.concurrency.singleflight import Flight
from cachelab.core.stats import MutableStats
from cachelab.policies.base import EvictionPolicy
from cachelab.storage.base import StorageBackend


def shard_capacities(total_capacity: int, shard_count: int) -> list[int]:
    base = total_capacity // shard_count
    remainder = total_capacity % shard_count
    return [base + (1 if index < remainder else 0) for index in range(shard_count)]


@dataclass(slots=True)
class CacheShard:
    index: int
    capacity: int
    backend: StorageBackend
    policy: EvictionPolicy
    lock: MeteredRLock = field(default_factory=MeteredRLock)
    stats: MutableStats = field(default_factory=MutableStats)
    singleflight: dict[Hashable, Flight] = field(default_factory=dict)
    version_marks: dict[Hashable, int] = field(default_factory=dict)
    tombstones: dict[Hashable, int] = field(default_factory=dict)
    pending_flushes: dict[Hashable, int] = field(default_factory=dict)

    def next_version(self, key: Hashable) -> int:
        version = self.version_marks.get(key, 0) + 1
        self.version_marks[key] = version
        return version
