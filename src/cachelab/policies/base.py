""" Base policy utilities for CacheLab """

from __future__ import annotations

from typing import Hashable, Protocol

from cachelab.core.exceptions import ConfigurationError


class EvictionPolicy(Protocol):
    name: str

    def on_get(self, key: Hashable) -> None:
        ...

    def on_put(self, key: Hashable) -> None:
        ...

    def on_delete(self, key: Hashable) -> None:
        ...

    def evict_candidate(self) -> Hashable | None:
        ...

    def clear(self) -> None:
        ...

    def metadata_size(self) -> int:
        ...

    def __len__(self) -> int:
        ...


def make_policy(name: str) -> EvictionPolicy:
    normalized = name.lower()
    if normalized == "fifo":
        from cachelab.policies.fifo import FIFOPolicy

        return FIFOPolicy()
    if normalized == "lru":
        from cachelab.policies.lru import LRUPolicy

        return LRUPolicy()
    if normalized == "lfu":
        from cachelab.policies.lfu import LFUPolicy

        return LFUPolicy()
    raise ConfigurationError(f"unknown eviction policy: {name}")
